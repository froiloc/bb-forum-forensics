/**
 * tests/unit/test_cockpit_tablekit.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit (Build 534)
 *
 * Testsuite fuer management/server/static/cockpit_tablekit.js — das GEMEINSAME
 * Tabellen-Werkzeug von Zuweisung und Fall-Erkennung.
 * Getestet wird der ECHTE Code (readFileSync + JSDOM, window.AIWTableKit).
 *
 * TK01 — API verfuegbar.
 * TK02 — eindeutigeWerte: Zahlen numerisch, Text nach Sprachregeln, null == ''.
 * TK03 — filterArt: Schwelle 10 (9 Werte -> Auswahl, 10 -> Freitext).
 * TK04 — mehrfachFilter: LEERE Auswahl filtert NICHT (die wichtigste Regel).
 * TK05 — filterFuer / spaltenMitFilter: jede Spalte bekommt einen Filter,
 *        'kein_filter' bleibt ausgenommen, 'filter_text' erzwingt Freitext.
 * TK06 — statZelle: '—' statt 0 bei nicht gelesenen Faellen; Abweichung wird
 *        markiert. Das ist der Grundregel-1-Test dieser Datei.
 * TK07 — statSpalten: unbekannte Schluessel werden GEMELDET, nicht geschluckt.
 * TK08 — statFelder: Kennzahl als ZAHL an der Zeile (sonst nicht sortierbar).
 * TK09 — Bedienzustand: schreiben/lesen/verwerfen (localStorage).
 * TK10 — zustandAnwenden: unbekannte Felder werden gemeldet, nicht gesetzt.
 * TK11 — Spaltenwahl (DOM): Haekchen melden die Auswahl.
 * TK12 — Werkzeugleiste (DOM): 'Filter zuruecksetzen' und Trefferanzeige.
 *
 * Version: v0.8.534 · Build: 534 · 2026-07-26
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api() { return _ctx().AIWTableKit; }

const _ROWS = [
  { subject_id: 18, username: "bravo", status_label: "offen", priority: 3 },
  { subject_id: 19, username: "alpha", status_label: "in Arbeit", priority: 1 },
  { subject_id: 200, username: "charlie", status_label: "offen", priority: 3 },
  { subject_id: 3, username: null, status_label: "offen", priority: 5 },
];

/** Kennzahlen wie /api/assignable/stats sie liefert. Fall 19 ist bewusst
 *  NICHT gelesen — genau daran haengt TK06. */
const _STATS = {
  "18": { befund: "gelesen", werte: {
    posts_total: { c: 123, r: 130, d: 7 },
    pm_posts_total: { c: 4, r: null, d: null },
  } },
  "19": { befund: "ohne_forensic_db", werte: {} },
  "200": { befund: "gelesen", werte: {
    posts_total: { c: 9, r: 9, d: 0 },
  } },
};
const _KATALOG = [
  { key: "pm_posts_total", faelle: 1 },
  { key: "posts_total", faelle: 2 },
];

describe("cockpit_tablekit.js — gemeinsames Tabellen-Werkzeug (Build 534)", () => {
  it("TK01: API verfuegbar", () => {
    const api = _api();
    ["eindeutigeWerte", "filterArt", "mehrfachFilter", "filterFuer",
     "spaltenMitFilter", "statZelle", "statSpalten", "statFelder",
     "zustandLesen", "zustandSchreiben", "zustandAusTabelle",
     "zustandAnwenden", "spaltenwahl", "werkzeugleiste", "filterLoeschen"]
      .forEach((n) => expect(typeof api[n]).toBe("function"));
    expect(api.SCHWELLE_AUSWAHL).toBe(10);
  });

  it("TK02: eindeutigeWerte sortiert richtig und fasst 'leer' zusammen", () => {
    const api = _api();
    // Zahlen NUMERISCH — sonst stuende '200' vor '3'.
    expect(api.eindeutigeWerte(_ROWS, "subject_id"))
      .toEqual(["3", "18", "19", "200"]);
    // Text nach Sprachregeln; null wird zu '' (EIN Eintrag, nicht zwei).
    expect(api.eindeutigeWerte(_ROWS, "username"))
      .toEqual(["", "alpha", "bravo", "charlie"]);
    expect(api.eindeutigeWerte(_ROWS, "status_label"))
      .toEqual(["in Arbeit", "offen"]);
  });

  it("TK03: filterArt entscheidet an der Schwelle 10", () => {
    const api = _api();
    expect(api.filterArt(_ROWS, "status_label")).toBe("auswahl");

    const neun = Array.from({ length: 9 }, (_, i) => ({ f: "w" + i }));
    expect(api.filterArt(neun, "f")).toBe("auswahl");   // 9 < 10
    const zehn = Array.from({ length: 10 }, (_, i) => ({ f: "w" + i }));
    expect(api.filterArt(zehn, "f")).toBe("text");      // 10 -> Freitext
  });

  it("TK04: mehrfachFilter — LEERE Auswahl filtert NICHT", () => {
    const api = _api();
    // Die wichtigste Zeile des Moduls: die andere Auslegung wuerde die Liste
    // leeren, sobald jemand das letzte Haekchen entfernt.
    expect(api.mehrfachFilter([], "offen")).toBe(true);
    expect(api.mehrfachFilter(null, "offen")).toBe(true);
    expect(api.mehrfachFilter(undefined, "offen")).toBe(true);

    expect(api.mehrfachFilter(["offen"], "offen")).toBe(true);
    expect(api.mehrfachFilter(["offen"], "in Arbeit")).toBe(false);
    expect(api.mehrfachFilter(["offen", "in Arbeit"], "in Arbeit")).toBe(true);
    // Zahlen kommen als Zahl an, die Auswahl als Text — beides muss treffen.
    expect(api.mehrfachFilter(["3"], 3)).toBe(true);
    // Einzelwert (ohne Mehrfachauswahl) funktioniert ebenfalls.
    expect(api.mehrfachFilter("offen", "offen")).toBe(true);
    expect(api.mehrfachFilter("", "offen")).toBe(true);
  });

  it("TK05: spaltenMitFilter belegt jede Spalte", () => {
    const api = _api();
    const spalten = api.spaltenMitFilter(_ROWS, [
      { title: "", field: "auswahl", kein_filter: true },
      { title: "Fall", field: "subject_id", filter_text: true },
      { title: "Zustand", field: "status_label" },
    ]);
    // Auswahlspalte: KEIN Filter (und die Steuer-Eigenschaften sind entfernt).
    expect(spalten[0].headerFilter).toBeUndefined();
    expect(spalten[0].kein_filter).toBeUndefined();
    // 'filter_text' erzwingt Freitext, obwohl nur 4 verschiedene Werte da sind.
    expect(spalten[1].headerFilter).toBe("input");
    expect(spalten[1].filter_text).toBeUndefined();
    // Wenige Werte -> Auswahlliste MIT Mehrfachauswahl und eigener Funktion.
    expect(spalten[2].headerFilter).toBe("list");
    expect(spalten[2].headerFilterParams.multiselect).toBe(true);
    expect(spalten[2].headerFilterFunc).toBe(api.mehrfachFilter);
    // Die Eingabe wurde NICHT veraendert (neue Objekte).
    expect(spalten[2].title).toBe("Zustand");
  });

  it("TK06: statZelle zeigt '—' statt 0 und markiert Abweichungen", () => {
    const api = _api();

    // Gelesen, mit Abweichung 130 gemeldet / 123 gezaehlt -> Stern + Hinweis.
    const a = api.statZelle(_STATS, 18, "posts_total");
    expect(a.wert).toBe(123);
    expect(a.text).toBe("123*");
    expect(a.titel).toContain("130");

    // DER KERN (Grundregel 1): Fall 19 hat keine lesbare forensic-DB.
    // Er zeigt '—', NICHT 0 — eine 0 saehe aus wie eine Feststellung.
    const b = api.statZelle(_STATS, 19, "posts_total");
    expect(b.text).toBe(api.UNBEKANNT_TEXT);
    expect(b.text).not.toBe("0");
    expect(b.wert).toBe(null);
    expect(b.titel).toContain("ohne_forensic_db");
    expect(b.titel).toContain("NICHT dasselbe wie 0");

    // Ein Fall, der gar nicht abgerufen wurde.
    expect(api.statZelle(_STATS, 999, "posts_total").text)
      .toBe(api.UNBEKANNT_TEXT);
    // Eine Kennzahl, die dieser Fall nicht fuehrt.
    expect(api.statZelle(_STATS, 200, "pm_posts_total").text)
      .toBe(api.UNBEKANNT_TEXT);
    // Ohne Abweichung: kein Stern.
    expect(api.statZelle(_STATS, 200, "posts_total").text).toBe("9");
    // Echte 0 bleibt 0 — sie ist eine Feststellung.
    const null_stats = { "1": { befund: "gelesen",
                                werte: { posts_total: { c: 0, r: 0, d: 0 } } } };
    expect(api.statZelle(null_stats, 1, "posts_total").text).toBe("0");
  });

  it("TK07: statSpalten meldet unbekannte Schluessel", () => {
    const api = _api();
    const s = api.statSpalten(_KATALOG, ["posts_total", "gibtsnicht"], _STATS);
    expect(s.spalten).toHaveLength(1);
    expect(s.spalten[0].field).toBe("stat_posts_total");
    expect(s.spalten[0].title).toBe("posts_total");   // technische Bezeichnung
    // NICHT still geschluckt:
    expect(s.unbekannt).toEqual(["gibtsnicht"]);
  });

  it("TK08: statFelder haengt die ZAHL an die Zeile (Sortierbarkeit)", () => {
    const api = _api();
    const zeilen = api.statFelder(_ROWS, _STATS, ["posts_total"]);
    expect(zeilen[0].stat_posts_total).toBe(123);
    // Nicht gelesen -> null, damit die Spalte sortierbar bleibt und die
    // Zeile NICHT als 0 einsortiert wird.
    expect(zeilen[1].stat_posts_total).toBe(null);
    // Die Eingabe bleibt unberuehrt.
    expect(_ROWS[0].stat_posts_total).toBeUndefined();
  });

  it("TK09: Bedienzustand wird gesichert und gelesen", () => {
    const win = _ctx();
    const api = win.AIWTableKit;
    win.localStorage.clear();

    expect(api.zustandLesen("assignment")).toBe(null);
    expect(api.zustandSchreiben("assignment", {
      sort: [{ column: "priority", dir: "asc" }],
      filter: [{ field: "status_label", value: ["offen"] }],
      spalten: ["posts_total"],
    })).toBe(true);

    const z = api.zustandLesen("assignment");
    expect(z.sort[0].column).toBe("priority");
    expect(z.filter[0].value).toEqual(["offen"]);
    expect(z.spalten).toEqual(["posts_total"]);
    expect(win.localStorage.getItem(api.schluessel("assignment"))).toBeTruthy();

    // Ein fremdformatiger Stand wird VERWORFEN, nicht repariert.
    win.localStorage.setItem(api.schluessel("assignment"),
                             JSON.stringify({ v: 99, sort: [] }));
    expect(api.zustandLesen("assignment")).toBe(null);
    // Unlesbarer Inhalt ebenso — ohne Absturz.
    win.localStorage.setItem(api.schluessel("assignment"), "{kaputt");
    expect(api.zustandLesen("assignment")).toBe(null);

    api.zustandLoeschen("assignment");
    expect(api.zustandLesen("assignment")).toBe(null);
  });

  it("TK10: zustandAnwenden uebergeht unbekannte Felder und meldet sie", () => {
    const api = _api();
    const gesetzt = [];
    const sortiert = [];
    const table = {
      setHeaderFilterValue: (f, v) => gesetzt.push([f, v]),
      setSort: (s) => sortiert.push(s),
    };
    const weg = api.zustandAnwenden(table, {
      filter: [{ field: "status_label", value: ["offen"] },
               { field: "stat_weg", value: "x" }],
      sort: [{ column: "priority", dir: "desc" },
             { column: "stat_weg", dir: "asc" }],
    }, ["status_label", "priority"]);

    expect(gesetzt).toEqual([["status_label", ["offen"]]]);
    expect(sortiert).toEqual([[{ column: "priority", dir: "desc" }]]);
    expect(weg).toEqual(["stat_weg", "stat_weg"]);
  });

  it("TK11: Spaltenwahl meldet die Auswahl", () => {
    const win = _ctx();
    const api = win.AIWTableKit;
    const meldungen = [];
    const wahl = api.spaltenwahl(win.document, {
      katalog: _KATALOG, gewaehlt: ["posts_total"],
      onChange: (keys) => meldungen.push(keys),
    });
    win.document.body.appendChild(wahl.el);

    const boxen = wahl.el.querySelectorAll("input[type=checkbox]");
    expect(boxen).toHaveLength(2);
    // Die Zahl dahinter sagt, in wie vielen Faellen die Kennzahl vorliegt.
    expect(wahl.el.textContent).toContain("(2)");

    const pm = wahl.el.querySelector("input[data-stat-key='pm_posts_total']");
    expect(pm.checked).toBe(false);
    pm.checked = true;
    pm.dispatchEvent(new win.Event("change"));
    expect(meldungen[meldungen.length - 1])
      .toEqual(["posts_total", "pm_posts_total"]);
    expect(wahl.getGewaehlt()).toHaveLength(2);

    // Ein Katalogwechsel entfernt eine nicht mehr vorhandene Kennzahl.
    wahl.setKatalog([{ key: "posts_total", faelle: 2 }]);
    expect(wahl.getGewaehlt()).toEqual(["posts_total"]);
  });

  it("TK12: Werkzeugleiste — Filter loeschen und Trefferanzeige", () => {
    const win = _ctx();
    const api = win.AIWTableKit;
    let geloescht = 0;
    const leiste = api.werkzeugleiste(win.document, {
      id: "aiw-test",
      spaltenwahl: { katalog: _KATALOG, gewaehlt: [] },
      onFilterLoeschen: () => { geloescht += 1; },
    });
    win.document.body.appendChild(leiste.el);

    const knopf = leiste.el.querySelector("#aiw-test-clear");
    expect(knopf.textContent).toContain("Filter");
    knopf.dispatchEvent(new win.Event("click"));
    expect(geloescht).toBe(1);

    leiste.setTreffer(4, 4);
    const t = leiste.el.querySelector("#aiw-test-treffer");
    expect(t.textContent).toBe("4 Zeilen");
    expect(t.classList.contains("gefiltert")).toBe(false);
    leiste.setTreffer(2, 4);
    expect(t.textContent).toContain("2 von 4");
    expect(t.classList.contains("gefiltert")).toBe(true);
  });

  it("TK13: filterLoeschen ruft beide Tabulator-Wege auf", () => {
    const api = _api();
    const gerufen = [];
    const table = {
      clearHeaderFilter: () => gerufen.push("header"),
      clearFilter: () => gerufen.push("filter"),
    };
    expect(api.filterLoeschen(table)).toBe(true);
    expect(gerufen).toEqual(["header", "filter"]);
    // Ohne Tabelle: kein Absturz, aber auch keine Erfolgsmeldung.
    expect(api.filterLoeschen(null)).toBe(false);
  });

  // ==========================================================================
  // Build 548 — Anker fuer die spaetere Schnellhilfe
  // ==========================================================================

  // TK14 ---------------------------------------------------------------------
  it("TK14: hilfeGueltig erzwingt das Muster <sicht>.<bereich>.<name>", () => {
    const TK = _api();
    expect(TK.hilfeGueltig("personnel.werkzeug.filter_entfernen")).toBe(true);
    expect(TK.hilfeGueltig("personnel.spalte.rollen")).toBe(true);
    expect(TK.hilfeGueltig("a.b")).toBe(true);
    // Zu wenig Abschnitte, Grossbuchstaben, Bindestriche, Leerzeichen,
    // fuehrende Ziffern, leere Abschnitte: alles unzulaessig.
    ["einteilig", "Personnel.werkzeug.x", "a.b-c", "a.b c", "1a.b",
     "a..b", "a.", ".b", "", null, undefined, 42].forEach((id) => {
      expect(TK.hilfeGueltig(id), String(id)).toBe(false);
    });
  });

  // TK15 ---------------------------------------------------------------------
  it("TK15: hilfeAnker setzt gueltige Kennungen und VERWIRFT krumme", () => {
    const win = _ctx();
    const TK = win.AIWTableKit;
    const doc = win.document;

    const gut = TK.hilfeAnker(doc.createElement("span"), "x.y.z");
    expect(gut.getAttribute("data-hilfe-id")).toBe("x.y.z");

    // Eine krumme Kennung wird NICHT gesetzt. Begruendung im Modulkopf: die
    // Schnellhilfe umrandete das Element spaeter, faende aber keinen Text —
    // lieber kein Rahmen als ein Rahmen ohne Inhalt.
    const warnungen = [];
    win.console.warn = (m) => warnungen.push(m);
    const schlecht = TK.hilfeAnker(doc.createElement("span"), "KRUMM");
    expect(schlecht.hasAttribute("data-hilfe-id")).toBe(false);
    // Und der Fehlgriff ist nicht still.
    expect(warnungen.length).toBe(1);
    expect(warnungen[0]).toContain("KRUMM");

    // Kein Element -> kein Absturz.
    expect(() => TK.hilfeAnker(null, "x.y.z")).not.toThrow();
  });

  // TK16 ---------------------------------------------------------------------
  it("TK16: die Werkzeugleiste vergibt die Anker selbst", () => {
    const win = _ctx();
    const TK = win.AIWTableKit;

    // MIT Sichtkennung: die Anker entstehen automatisch. Das ist der Gewinn
    // des gemeinsamen Werkzeugs — jede kuenftige Sicht erbt sie, ohne dass
    // jemand daran denken muss.
    const mit = TK.werkzeugleiste(win.document, { id: "t", sicht: "demo" });
    expect(TK.hilfeIds(mit.el)).toEqual([
      "demo.werkzeug.filter_entfernen",
      "demo.werkzeug.trefferzahl",
    ]);

    // OHNE Sichtkennung: LIEBER GAR KEIN ANKER als ein falscher. Ein
    // 'undefined.werkzeug.…' waere ein toter Link.
    const ohne = TK.werkzeugleiste(win.document, { id: "t" });
    expect(TK.hilfeIds(ohne.el)).toEqual([]);
  });

  // TK17 ---------------------------------------------------------------------
  it("TK17: titelMitHilfe — Spaltenkopf mit Anker und Tooltip, XSS-sicher", () => {
    const win = _ctx();
    const TK = win.AIWTableKit;
    const f = TK.titelMitHilfe(
      win.document, "Rollen <b>x</b>", "demo.spalte.rollen", "Erklärung"
    );
    const el = f();
    expect(el.getAttribute("data-hilfe-id")).toBe("demo.spalte.rollen");
    expect(el.title).toBe("Erklärung");
    // Der Titel ist TEXT, kein Markup.
    expect(el.textContent).toBe("Rollen <b>x</b>");
    expect(el.querySelector("b")).toBeNull();
  });
});
