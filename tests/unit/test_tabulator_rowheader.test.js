/**
 * test_tabulator_rowheader.test.js
 * Unit-Tests: extractTabulatorRows() aus userinfo.js — Zeilenkopf-<th>.
 *
 * BELEG: Ticket 1ad6bd69-730e-46d3-a2a3-aecfbd5a0a8f (Alex, 2026-08-11),
 *        "Userinfo - Aktivitaetstimeline ohne Eintrag bei Monat",
 *        betroffene Version 0.8.686.
 *
 * NACHGESTELLTER BEFUND: Die Timeline-Tabelle des Preppers
 * (stage1/phase_b_html_renderer.py:1324) setzt den Monat als ZEILENKOPF
 * "<th>Mär</th>". Die alte Auslese nahm nur <td> — die erste Zelle fiel weg,
 * alle Werte rutschten eine Spalte nach links, die Summenspalte blieb leer.
 *
 * ANTI-"GRUEN ABER TOT" (B4-S12): Der Test extrahiert die ECHTE Funktion per
 * Klammer-Matching aus userinfo.js und fuehrt sie im jsdom-Kontext aus. Eine
 * Divergenz zwischen Testkopie und Produktivcode kann so nicht entstehen.
 *
 * Muster wie test_toc_build.test.js: eigenes JSDOM je Test.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

// --- Echte Funktion aus userinfo.js per Klammer-Matching extrahieren --------
function extractFn(src, name) {
    const start = src.indexOf("function " + name);
    if (start < 0) throw new Error("Funktion nicht gefunden: " + name);
    const braceStart = src.indexOf("{", start);
    let depth = 0, i = braceStart;
    for (; i < src.length; i++) {
        const c = src[i];
        if (c === "{") depth++;
        else if (c === "}") { depth--; if (depth === 0) { i++; break; } }
    }
    return src.slice(start, i);
}

const SRC = readFileSync(join(__dirname, "../../userinfo/userinfo.js"), "utf-8");
const FN_SRC = extractFn(SRC, "extractTabulatorRows");

/**
 * Baut ein JSDOM mit der uebergebenen Tabelle, injiziert die ECHTE Funktion
 * und ruft sie dort auf. console.warn wird mitgeschnitten, damit Grundregel 1
 * (kein stilles Uebergehen) pruefbar ist.
 */
function runOn(tableHtml, columnCount) {
    const dom = new JSDOM(
        `<!DOCTYPE html><html><body>${tableHtml}</body></html>`,
        { url: "http://127.0.0.2:8080" }
    );
    const win = dom.window;
    const warnungen = [];
    win.console.warn = (...a) => warnungen.push(a.join(" "));
    // eslint-disable-next-line no-new-func
    const factory = new win.Function(
        "console",
        `${FN_SRC}\nreturn extractTabulatorRows;`
    );
    const fn = factory(win.console);
    const table = win.document.querySelector("table");
    return { rows: fn(table, columnCount), warnungen, table };
}

// --- Originalgetreuer Auszug der Prepper-Ausgabe ---------------------------
// Nachgebildet aus _render_timeline_agg(): <thead> mit "Monat", je Zeile ein
// <th> als Monatskopf, danach die Quellspalten als <td>, zuletzt die Summe.
// Zahlen aus dem DOM-Auszug des Tickets (Zeile mit Summe 9).
const TIMELINE_HTML = `
<table class="forensic-data" id="forensic-tabulator-0">
  <thead><tr>
    <th>Monat</th><th>Bearbeitungen</th><th>Private Nachrichten</th>
    <th>PN-Gespräche</th><th>Abstimmungen</th><th>Beiträge</th><th>∑</th>
  </tr></thead>
  <tbody>
    <tr><th>Mär</th><td>1</td><td></td><td>1</td><td>7</td><td></td>
        <td><strong>9</strong></td></tr>
    <tr><th>Apr</th><td></td><td></td><td></td><td>10</td><td></td>
        <td><strong>10</strong></td></tr>
  </tbody>
</table>`;

describe("userinfo.js — extractTabulatorRows() (Ticket 1ad6bd69)", () => {

    it("Zeilenkopf <th> landet in col0 — die Spalte 'Monat' bleibt nicht leer", () => {
        const { rows } = runOn(TIMELINE_HTML, 7);
        expect(rows).toHaveLength(2);
        expect(rows[0].col0).toBe("Mär");
        expect(rows[1].col0).toBe("Apr");
    });

    it("kein Spaltenversatz: Werte stehen unter ihrer eigenen Kopfspalte", () => {
        const { rows } = runOn(TIMELINE_HTML, 7);
        // Kopf:  col0 Monat | col1 Bearbeitungen | col2 PN | col3 PN-Gespräche
        //        col4 Abstimmungen | col5 Beiträge | col6 Summe
        expect(rows[0].col1).toBe("1");
        expect(rows[0].col3).toBe("1");
        expect(rows[0].col4).toBe("7");
    });

    it("die Summenspalte ist besetzt (vorher: letzte Spalte leer)", () => {
        const { rows } = runOn(TIMELINE_HTML, 7);
        expect(rows[0].col6).toBe("<strong>9</strong>");
        expect(rows[1].col6).toBe("<strong>10</strong>");
    });

    it("Zellenzahl je Zeile entspricht der Zahl der Kopfspalten", () => {
        const { rows } = runOn(TIMELINE_HTML, 7);
        rows.forEach(r => expect(Object.keys(r)).toHaveLength(7));
    });

    it("Grundregel 1: abweichende Zellenzahl wird vermerkt, Zeile bleibt erhalten", () => {
        const kaputt = `
        <table class="forensic-data" id="t-kaputt">
          <thead><tr><th>A</th><th>B</th><th>C</th></tr></thead>
          <tbody><tr><td>1</td><td>2</td></tr></tbody>
        </table>`;
        const { rows, warnungen } = runOn(kaputt, 3);
        expect(rows).toHaveLength(1);              // NICHT verworfen
        expect(rows[0].col0).toBe("1");
        expect(warnungen.length).toBe(1);
        expect(warnungen[0]).toContain("t-kaputt");
        expect(warnungen[0]).toContain("2 Zellen bei 3 Kopfspalten");
    });

    it("reine <td>-Tabellen bleiben unveraendert (keine Nebenwirkung)", () => {
        const nurTd = `
        <table class="forensic-data">
          <thead><tr><th>A</th><th>B</th></tr></thead>
          <tbody><tr><td>x</td><td>y</td></tr></tbody>
        </table>`;
        const { rows, warnungen } = runOn(nurTd, 2);
        expect(rows[0]).toEqual({ col0: "x", col1: "y" });
        expect(warnungen).toHaveLength(0);
    });

    it("HTML-Inhalt der Zellen bleibt erhalten (Links/Spans im BLOB)", () => {
        const mitHtml = `
        <table class="forensic-data">
          <thead><tr><th>A</th><th>B</th></tr></thead>
          <tbody><tr><th><span class="forensic-ts" data-ts="1700000000">x</span></th>
                     <td><a href="#">y</a></td></tr></tbody>
        </table>`;
        const { rows } = runOn(mitHtml, 2);
        expect(rows[0].col0).toContain('data-ts="1700000000"');
        expect(rows[0].col1).toBe('<a href="#">y</a>');
    });

    it("verschachtelte Tabelle schleust keine Zellen in die Elternzeile ein", () => {
        // :scope-Selektor. Kuenftige Schachtelung darf die Zuordnung nicht
        // verschieben — dieselbe Fehlerklasse wie der Ticketbefund.
        const geschachtelt = `
        <table class="forensic-data">
          <thead><tr><th>A</th><th>B</th></tr></thead>
          <tbody><tr><th>kopf</th>
            <td><table><tbody><tr><td>innen1</td><td>innen2</td></tr></tbody></table></td>
          </tr></tbody>
        </table>`;
        const { rows } = runOn(geschachtelt, 2);
        expect(rows).toHaveLength(1);              // NICHT die innere Zeile mit
        expect(rows[0].col0).toBe("kopf");
        expect(rows[0].col2).toBeUndefined();
    });

    it("ohne Pruefmass wird nicht gewarnt (Aufruf ohne columnCount)", () => {
        const { rows, warnungen } = runOn(TIMELINE_HTML);
        expect(rows[0].col0).toBe("Mär");
        expect(warnungen).toHaveLength(0);
    });
});
