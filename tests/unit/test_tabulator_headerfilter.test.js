/**
 * test_tabulator_headerfilter.test.js
 * Unit-Tests: sichtbarerText() und htmlHeaderFilter() aus userinfo.js.
 *
 * BELEG: Entscheidung Alex 2026-08-11 (E4), Vorgang 8f2c19aa.
 *
 * DER BEFUND, GEMESSEN AN DER AUSGELIEFERTEN BIBLIOTHEK:
 * Tabulators Standardvergleich arbeitet auf dem ROHEN Feldwert —
 *   static/vendor/tabulator/tabulator.min.js:
 *   like:function(e,t,i,s){ ... String(t).toLowerCase().indexOf(e.toLowerCase())>-1 ...}
 * Der Feldwert ist hier das innerHTML der Zelle, einschliesslich des
 * versteckten Sortierschluessels <span class="forensic-ts" data-ts="…">.
 * Wer im Monatsfeld "7" eintippt, trifft damit auch jede Zeile, deren
 * Zeitstempel eine 7 enthaelt.
 *
 * ANTI-"GRUEN ABER TOT" (B4-S12): Der Test extrahiert die ECHTEN Funktionen
 * per Klammer-Matching aus userinfo.js und fuehrt sie im jsdom-Kontext aus.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

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
const FN_SRC = extractFn(SRC, "sichtbarerText")
             + "\n" + extractFn(SRC, "htmlHeaderFilter");

// Eigenes JSDOM, damit DOMParser und console echt sind.
const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>",
                      { url: "http://127.0.0.2:8080" });
const win = dom.window;
const warnungen = [];
win.console.warn = (...a) => warnungen.push(a.join(" "));
// eslint-disable-next-line no-new-func
const factory = new win.Function(
    "DOMParser", "console",
    `${FN_SRC}\nreturn { sichtbarerText, htmlHeaderFilter };`
);
const { sichtbarerText, htmlHeaderFilter } = factory(win.DOMParser, win.console);

// --- Originalgetreue Zellinhalte aus dem Prepper ---------------------------
// Monatszelle ab Prepper-Build 131 (_month_cell): unsichtbarer Schluessel +
// sichtbares Kuerzel. 1772323200 = 2026-03-01 UTC.
const MONAT_MAERZ =
    '<span class="forensic-ts" data-ts="1772323200" style="display:none"></span>Mär';
// Zeitstempelzelle seit Prepper-Build 060 (_ts): der Schluessel steht dort aus
// historischen Gruenden auch als TEXT im Span.
const ZEITSTEMPEL =
    '<span class="forensic-ts" data-ts="1700000000" style="display:none">1700000000</span>'
    + 'Di 14.11.2023 22:13 UTC';

describe("userinfo.js — sichtbarerText()", () => {

    it("entfernt den versteckten Sortierschluessel der Monatszelle", () => {
        expect(sichtbarerText(MONAT_MAERZ)).toBe("Mär");
    });

    it("entfernt ihn auch dort, wo er zusaetzlich als Text steht", () => {
        expect(sichtbarerText(ZEITSTEMPEL)).toBe("Di 14.11.2023 22:13 UTC");
    });

    it("erhaelt den Text von Links und Auszeichnungen", () => {
        expect(sichtbarerText('<a href="#" data-forensic-url="x">Thema 42</a>'))
            .toBe("Thema 42");
        expect(sichtbarerText("<strong>9</strong>")).toBe("9");
    });

    it("laesst reinen Text unveraendert (Schnellweg ohne Parser)", () => {
        expect(sichtbarerText("Beschuldigter")).toBe("Beschuldigter");
        expect(sichtbarerText("7")).toBe("7");
        expect(sichtbarerText("  7  ")).toBe("7");
    });

    it("kommt mit leeren Werten zurecht", () => {
        expect(sichtbarerText("")).toBe("");
        expect(sichtbarerText(null)).toBe("");
        expect(sichtbarerText(undefined)).toBe("");
    });

    it("fasst Leerraum zusammen", () => {
        expect(sichtbarerText("<td>a\n\n   b</td>")).toBe("a b");
    });

    it("spitze Klammern in Attributwerten werfen den Parser nicht", () => {
        // Genau daran waere ein Tag-Regex gescheitert.
        expect(sichtbarerText('<a title="Herz <3 gemeint">Titel</a>'))
            .toBe("Titel");
    });

    it("HTML-Entitaeten werden aufgeloest (der Ermittler sieht das Zeichen)", () => {
        expect(sichtbarerText("<td>PN &amp; Beitr&auml;ge</td>"))
            .toBe("PN & Beiträge");
    });
});

describe("userinfo.js — htmlHeaderFilter()", () => {

    it("DER BEFUND: eine Ziffer aus dem Zeitstempel trifft NICHT mehr", () => {
        // '7' kommt in 1772323200 vor, aber nicht in 'Mär'.
        expect(htmlHeaderFilter("7", MONAT_MAERZ)).toBe(false);
    });

    it("Gegenprobe: der Standardvergleich von Tabulator wuerde treffen", () => {
        // Nachbau von tabulator.min.js 'like' — belegt, dass der Test einen
        // ECHTEN Unterschied misst und nicht nur sich selbst bestaetigt.
        const like = (e, t) =>
            String(t).toLowerCase().indexOf(String(e).toLowerCase()) > -1;
        expect(like("7", MONAT_MAERZ)).toBe(true);
        expect(htmlHeaderFilter("7", MONAT_MAERZ)).toBe(false);
    });

    it("der sichtbare Text trifft weiterhin", () => {
        expect(htmlHeaderFilter("Mär", MONAT_MAERZ)).toBe(true);
        expect(htmlHeaderFilter("mär", MONAT_MAERZ)).toBe(true);
        expect(htmlHeaderFilter("ä", MONAT_MAERZ)).toBe(true);
    });

    it("Teiltreffer im sichtbaren Datum bleiben moeglich", () => {
        expect(htmlHeaderFilter("14.11.2023", ZEITSTEMPEL)).toBe(true);
        expect(htmlHeaderFilter("UTC", ZEITSTEMPEL)).toBe(true);
        // …aber nicht mehr ueber den versteckten Schluessel.
        expect(htmlHeaderFilter("1700000000", ZEITSTEMPEL)).toBe(false);
    });

    it("Markup ist nicht durchsuchbar (kein Filtern nach 'span' oder 'href')", () => {
        expect(htmlHeaderFilter("span", MONAT_MAERZ)).toBe(false);
        expect(htmlHeaderFilter("href", '<a href="#">Thema</a>')).toBe(false);
        expect(htmlHeaderFilter("data-ts", MONAT_MAERZ)).toBe(false);
    });

    it("leerer Suchbegriff trifft alles (wie Tabulators 'like')", () => {
        expect(htmlHeaderFilter("", MONAT_MAERZ)).toBe(true);
        expect(htmlHeaderFilter(null, MONAT_MAERZ)).toBe(true);
        expect(htmlHeaderFilter(undefined, MONAT_MAERZ)).toBe(true);
    });

    it("leere Zelle trifft nur bei leerem Suchbegriff", () => {
        expect(htmlHeaderFilter("", "")).toBe(true);
        expect(htmlHeaderFilter("x", "")).toBe(false);
    });

    it("reine Zahlenspalten verhalten sich unveraendert", () => {
        expect(htmlHeaderFilter("9", "<strong>9</strong>")).toBe(true);
        expect(htmlHeaderFilter("10", "<strong>9</strong>")).toBe(false);
    });
});
