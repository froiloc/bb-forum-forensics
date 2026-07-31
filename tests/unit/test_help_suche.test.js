/**
 * tests/unit/test_help_suche.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle H: Hilfesysteme (H6)
 *
 * Testsuite fuer management/server/static/help.js (Build 593) — die
 * Kapitelsuche im Hilfefenster. Testet den ECHTEN Code (readFileSync + JSDOM).
 *
 * HQ01 — API verfuegbar; leerer Begriff liefert eine KOPIE der Liste.
 * HQ02 — Teilstring, gross/klein egal.
 * HQ03 — mehrere Woerter sind ein UND.
 * HQ04 — Treffer im Label stehen vor Treffern nur in den Stichworten.
 * HQ05 — Stichworte aus dem VIEW_CATALOG werden mitgesucht, auch wenn sie im
 *        Kapiteltitel gar nicht vorkommen (der eigentliche Gewinn des
 *        serverseitigen Index).
 * HQ06 — kein Treffer -> leere Liste, kein Fehler.
 * HQ07 — trefferText: alle / keine / Teilmenge.
 * HQ08 — init blendet das Suchfeld ein (vorher 'hidden').
 * HQ09 — Tippen blendet die nicht passenden Verzeichniseintraege aus.
 * HQ10 — leer werdende Gruppen samt Ueberschrift verschwinden mit.
 * HQ11 — Escape leert das Feld und zeigt wieder alles.
 * HQ12 — unlesbarer Index -> keine Ausnahme, Suche bleibt still (und die
 *        Konsole sagt es).
 */

import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/help.js", "utf-8");

const INDEX = [
  { id: "dashboard", label: "Dashboard", gruppe: "Ueberblick", offen: true,
    worte: "dashboard ueberblick kacheln startseite lage zusammenfassung" },
  { id: "faelle", label: "Fallübersicht", gruppe: "Fallsteuerung", offen: false,
    worte: "fallübersicht fall uebersicht tabelle ampel liste bestand "
         + "die dringlichkeits-ampel die spalten" },
  { id: "limitation", label: "Fristen (Verjaehrung)", gruppe: "Auswertung",
    offen: true, worte: "fristen (verjaehrung) frist verjaehrung stgb" },
];

function _seite(indexJson) {
  const roh = (indexJson === undefined)
    ? JSON.stringify(INDEX) : indexJson;
  const html = `<!DOCTYPE html><html><body class="aiw-h">
    <div class="aiw-h-rahmen">
      <nav class="aiw-h-verzeichnis">
        <div class="aiw-h-suchfeld" id="aiw-h-suchfeld" hidden>
          <label for="aiw-h-suche">Kapitel suchen</label>
          <input type="search" id="aiw-h-suche">
          <span class="aiw-h-suchzahl" id="aiw-h-suchzahl"></span>
        </div>
        <h3 data-gruppe="Ueberblick">Ueberblick</h3>
        <ul data-gruppe="Ueberblick">
          <li data-sicht="dashboard"><a href="#dashboard">Dashboard</a></li>
        </ul>
        <h3 data-gruppe="Fallsteuerung">Fallsteuerung</h3>
        <ul data-gruppe="Fallsteuerung">
          <li data-sicht="faelle"><a href="#faelle">Fallübersicht</a></li>
        </ul>
        <h3 data-gruppe="Auswertung">Auswertung</h3>
        <ul data-gruppe="Auswertung">
          <li data-sicht="limitation"><a href="#limitation">Fristen</a></li>
        </ul>
      </nav>
    </div>
    <script type="application/json" id="aiw-h-index">${roh}</script>
  </body></html>`;
  const dom = new JSDOM(html, { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(_src);
  const api = dom.window.AIWHilfeSuche;
  // init AUSDRUECKLICH aufrufen. Im Browser tut das die Selbststartlogik am
  // Ende der Datei (DOMContentLoaded bzw. sofort); in jsdom haengt der
  // Zeitpunkt davon ab, wann das Dokument fertig geparst ist - und ein Test,
  // der von einer Wettlaufsituation abhaengt, ist kein Test.
  api.init(dom.window.document);
  return { win: dom.window, doc: dom.window.document, api: api };
}

function _tippe(doc, wert) {
  const feld = doc.getElementById("aiw-h-suche");
  feld.value = wert;
  feld.dispatchEvent(new doc.defaultView.Event("input", { bubbles: true }));
}

function _sichtbar(doc) {
  return Array.from(doc.querySelectorAll("li[data-sicht]"))
    .filter((li) => !li.hidden)
    .map((li) => li.getAttribute("data-sicht"));
}

describe("Kapitelsuche — reine Funktion", () => {
  const api = _seite().api;

  it("HQ01 — leerer Begriff liefert eine Kopie", () => {
    const alles = api.filtereKapitel(INDEX, "");
    expect(alles).toHaveLength(3);
    expect(alles).not.toBe(INDEX);
    expect(api.filtereKapitel(INDEX, "   ")).toHaveLength(3);
    expect(api.filtereKapitel(null, "x")).toEqual([]);
  });

  it("HQ02 — Teilstring, Gross-/Kleinschreibung egal", () => {
    expect(api.filtereKapitel(INDEX, "AMPEL").map((e) => e.id))
      .toEqual(["faelle"]);
    expect(api.filtereKapitel(INDEX, "kachel").map((e) => e.id))
      .toEqual(["dashboard"]);
  });

  it("HQ03 — mehrere Woerter sind ein UND", () => {
    expect(api.filtereKapitel(INDEX, "ampel tabelle").map((e) => e.id))
      .toEqual(["faelle"]);
    // 'ampel' gibt es, 'kachel' auch — aber nicht im selben Kapitel
    expect(api.filtereKapitel(INDEX, "ampel kachel")).toEqual([]);
  });

  it("HQ04 — Label-Treffer vor Stichwort-Treffer", () => {
    // 'fall' steht im Label von 'Fallübersicht' und in den Stichworten
    // beider. Das Label gewinnt.
    const treffer = api.filtereKapitel(INDEX, "fall");
    expect(treffer[0].id).toBe("faelle");
  });

  it("HQ05 — Stichworte werden mitgesucht", () => {
    // 'stgb' steht NICHT im Kapiteltitel, nur in den Stichworten des
    // VIEW_CATALOG. Genau dafuer gibt es den serverseitigen Index.
    expect(api.filtereKapitel(INDEX, "stgb").map((e) => e.id))
      .toEqual(["limitation"]);
  });

  it("HQ06 — kein Treffer -> leere Liste", () => {
    expect(api.filtereKapitel(INDEX, "gibtsnicht")).toEqual([]);
  });

  it("HQ07 — trefferText", () => {
    expect(api.trefferText(3, 3)).toBe("3 Kapitel");
    expect(api.trefferText(0, 3)).toBe("kein Kapitel gefunden");
    expect(api.trefferText(1, 3)).toBe("1 von 3 Kapiteln");
  });
});

describe("Kapitelsuche — Oberflaeche", () => {
  it("HQ08 — init blendet das Suchfeld ein", () => {
    const { doc } = _seite();
    expect(doc.getElementById("aiw-h-suchfeld").hidden).toBe(false);
    expect(doc.getElementById("aiw-h-suchzahl").textContent)
      .toBe("3 Kapitel");
  });

  it("HQ09 — Tippen filtert das Verzeichnis", () => {
    const { doc } = _seite();
    expect(_sichtbar(doc)).toEqual(["dashboard", "faelle", "limitation"]);
    _tippe(doc, "ampel");
    expect(_sichtbar(doc)).toEqual(["faelle"]);
    expect(doc.getElementById("aiw-h-suchzahl").textContent)
      .toBe("1 von 3 Kapiteln");
  });

  it("HQ10 — leere Gruppen verschwinden samt Ueberschrift", () => {
    const { doc } = _seite();
    _tippe(doc, "ampel");
    const h3Ueberblick = doc.querySelector('h3[data-gruppe="Ueberblick"]');
    const h3Fall = doc.querySelector('h3[data-gruppe="Fallsteuerung"]');
    expect(h3Ueberblick.hidden).toBe(true);
    expect(h3Fall.hidden).toBe(false);
    expect(doc.querySelector('ul[data-gruppe="Ueberblick"]').hidden).toBe(true);
  });

  it("HQ11 — Escape leert das Feld", () => {
    const { doc } = _seite();
    _tippe(doc, "ampel");
    expect(_sichtbar(doc)).toEqual(["faelle"]);
    const feld = doc.getElementById("aiw-h-suche");
    feld.dispatchEvent(new doc.defaultView.KeyboardEvent(
      "keydown", { key: "Escape", bubbles: true }));
    expect(feld.value).toBe("");
    expect(_sichtbar(doc)).toEqual(["dashboard", "faelle", "limitation"]);
  });

  it("HQ12 — unlesbarer Index bricht nichts", () => {
    const fehler = vi.spyOn(console, "error").mockImplementation(() => {});
    const { doc } = _seite("{kein json");
    // Ohne Index gibt es keine Treffer — aber auch keine Ausnahme.
    expect(doc.getElementById("aiw-h-suchzahl").textContent)
      .toBe("0 Kapitel");
    expect(fehler).toHaveBeenCalled();
    fehler.mockRestore();
  });
});
