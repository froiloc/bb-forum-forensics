/**
 * tests/unit/test_cockpit_dashboard_charts.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Überblick
 * =============================================================================
 * Testsuite für Build 570: die Diagramme der Überblick-Kacheln.
 *
 * WARUM DAS PRÜFBAR IST: eine ECharts-Option ist ein DATENOBJEKT. Der Test
 * schaut in die Option — Serientyp, Farben, Achsen, Reihenfolge der Eimer —
 * und nicht auf Pixel. Damit wird der ECHTE Code bewertet und nicht eine
 * Nachbildung ("grün aber tot" vermieden).
 *
 * DC01 — ampelEimer zählt feste Eimer; ein unbekannter Ampelwert landet unter
 *        'sonst' und NICHT unter 'grün'.
 * DC02 — alterEimer: eine fehlende Liegezeit ist keine kurze Liegezeit.
 * DC03 — restEimer: eine Zeile ohne mögliche Aussage landet in KEINEM
 *        Restlaufzeit-Eimer.
 * DC04 — Eimer bleiben in fester Reihenfolge und mit Wert 0 erhalten; die
 *        Form der Kachel springt nicht von Abruf zu Abruf.
 * DC05 — der Ampelring trägt die Gesamtzahl in der Mitte und die
 *        projektweiten Ampelfarben in dieser Reihenfolge.
 * DC06 — der Anteilsbalken zeigt Teil UND Ganzes; teil > gesamt wird
 *        abgefangen statt einen negativen Rest zu zeichnen.
 * DC07 — Lastbalken: Färbung nach Stufe, Rückstauzeile fällt heraus,
 *        absteigend sortiert, Grenzlinie nur bei bekannter Grenze.
 * DC08 — DIE WICHTIGSTE: die Fristenkachel bekommt KEIN Diagramm, wenn keine
 *        Aussage möglich ist. Eine Form wäre eine unbelegte Rechtsbehauptung.
 * DC09 — optionFuer liefert für jede Kachel entweder eine Option oder ein
 *        begründetes null; ein Abrufausfall ergibt nie eine Option.
 * DC10 — jede Kachel des Katalogs ist entschieden: entweder Option oder
 *        Eintrag in DIAGRAMMLOS. Keine bleibt unbeantwortet.
 * DC11 — animation ist überall aus (ein Überblick soll stehen, nicht wachsen).
 * DC12 — zeichne(): fehlt die Bibliothek, sagt die Kachel das statt leer zu
 *        bleiben; ist sie da, wird init+setOption gerufen.
 *
 * Version: v0.8.570 · Build: 570 · 2026-07-29
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _charts = readFileSync(
  "management/server/static/cockpit_dashboard_charts.js", "utf-8");
const _katalog = readFileSync(
  "management/viewprefs/viewpref_katalog.py", "utf-8");

function _api() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(_charts);
  return { win: dom.window, api: dom.window.AIWCockpitDashboardCharts };
}

describe("Kacheldiagramme (Build 570)", () => {
  // DC01 --------------------------------------------------------------------
  it("DC01: ampelEimer verbucht Unbekanntes nicht als grün", () => {
    const { api } = _api();
    const z = api.ampelEimer([
      { ampel: "rot" }, { ampel: "rot" }, { ampel: "gelb" },
      { ampel: "gruen" }, { ampel: "violett" }, {}, { ampel: null },
    ]);
    expect(z).toEqual({ rot: 2, gelb: 1, gruen: 1, sonst: 3 });
  });

  // DC02 --------------------------------------------------------------------
  it("DC02: fehlende Liegezeit ist keine kurze Liegezeit", () => {
    const { api } = _api();
    const z = api.alterEimer([
      { days_inactive: 1 }, { days_inactive: 3 }, { days_inactive: 4 },
      { days_inactive: 14 }, { days_inactive: 40 }, { days_inactive: null }, {},
    ]);
    expect(z).toEqual({ bis3: 2, bis7: 1, bis14: 1, ueber: 1, unbekannt: 2 });
    // Der Kern: die zwei ohne Angabe sind NICHT in 'bis3' gelandet.
    expect(z.bis3).toBe(2);
  });

  // DC03 --------------------------------------------------------------------
  it("DC03: Frist ohne mögliche Aussage landet in keinem Eimer", () => {
    const { api } = _api();
    const z = api.restEimer([
      { aussage_moeglich: true, restlaufzeit_tage: 3 },
      { aussage_moeglich: true, restlaufzeit_tage: 20 },
      { aussage_moeglich: true, restlaufzeit_tage: 60 },
      { aussage_moeglich: true, restlaufzeit_tage: 400 },
      { aussage_moeglich: false, restlaufzeit_tage: 1 },
      { aussage_moeglich: true, restlaufzeit_tage: null },
    ]);
    expect(z).toEqual({ bis7: 1, bis30: 1, bis90: 1, ueber90: 1,
                        ohne_aussage: 2 });
  });

  // DC04 --------------------------------------------------------------------
  it("DC04: Eimer behalten Reihenfolge und Nullwerte", () => {
    const { api } = _api();
    const opt = api.optionAlterBalken({ bis3: 0, bis7: 0, bis14: 2, ueber: 0 });
    expect(opt.xAxis.data).toEqual(
      ["bis 3 Tage", "4–7 Tage", "8–14 Tage", "über 14 Tage"]);
    expect(opt.series[0].data.map((d) => d.value)).toEqual([0, 0, 2, 0]);
    // Eine leere Kachel hat dieselbe Form wie eine volle.
    const leer = api.optionAlterBalken({});
    expect(leer.xAxis.data).toEqual(opt.xAxis.data);
    expect(leer.series[0].data.map((d) => d.value)).toEqual([0, 0, 0, 0]);
  });

  // DC05 --------------------------------------------------------------------
  it("DC05: Ampelring trägt die Gesamtzahl und die Ampelfarben", () => {
    const { api } = _api();
    const opt = api.optionAmpelRing({ rot: 2, gelb: 1, gruen: 5, sonst: 0 }, 8);
    const s = opt.series[0];
    expect(s.type).toBe("pie");
    expect(s.label.formatter).toBe("8");          // Gesamt im Loch
    expect(s.data.map((d) => d.itemStyle.color)).toEqual(
      [api.FARBE.rot, api.FARBE.gelb, api.FARBE.gruen, api.FARBE.grau]);
    // Ohne uebergebene Gesamtzahl wird die Summe der Eimer genommen.
    const ohne = api.optionAmpelRing({ rot: 1, gelb: 2, gruen: 0, sonst: 1 });
    expect(ohne.series[0].label.formatter).toBe("4");
  });

  // DC06 --------------------------------------------------------------------
  it("DC06: Anteilsbalken zeigt Teil und Ganzes, ohne negativen Rest", () => {
    const { api } = _api();
    const opt = api.optionAnteilBalken(7, 42, "blau");
    expect(opt.xAxis.max).toBe(42);
    expect(opt.series[0].data).toEqual([7]);
    expect(opt.series[1].data).toEqual([35]);

    // Widerspruechliche Zahlen duerfen keinen negativen Balken erzeugen.
    const krumm = api.optionAnteilBalken(9, 4, "rot");
    expect(krumm.series[1].data[0]).toBe(0);
    expect(krumm.series[0].data[0]).toBe(9);
    // Und ein leerer Bestand keine Division durch Null in der Achse.
    expect(api.optionAnteilBalken(0, 0, "blau").xAxis.max).toBe(1);
  });

  // DC07 --------------------------------------------------------------------
  it("DC07: Lastbalken färbt nach Stufe und lässt den Rückstau weg", () => {
    const { api } = _api();
    const daten = {
      loads: [
        { display_name: "Mueller", active_cases: 12 },
        { display_name: "Gamma", active_cases: 4 },
        { display_name: "Rueckstau", active_cases: 99, is_backlog: true },
      ],
      overload_assessments: [
        { name: "Mueller", level: "overload" },
        { name: "Gamma", level: "ok" },
      ],
      max_active_cases: 10,
    };
    const zeilen = api.lastZeilen(daten);
    expect(zeilen.map((z) => z.name)).toEqual(["Mueller", "Gamma"]);
    expect(zeilen[0].aktiv).toBe(12);          // absteigend
    expect(zeilen[0].stufe).toBe("overload");

    const opt = api.optionLastBalken(zeilen, 10);
    expect(opt.yAxis.data).toEqual(["Mueller", "Gamma"]);
    expect(opt.series[0].data[0].itemStyle.color).toBe(api.FARBE.rot);
    expect(opt.series[0].data[1].itemStyle.color).toBe(api.FARBE.gruen);
    // Die Grenzlinie ist der eigentliche Gewinn — ohne sie sieht man Balken,
    // aber nicht, ob sie zu lang sind.
    expect(opt.series[0].markLine.data).toEqual([{ xAxis: 10 }]);
    // Ohne bekannte Grenze KEINE erfundene Linie.
    expect(api.optionLastBalken(zeilen, null).series[0].markLine)
      .toBeUndefined();
  });

  // DC08 --------------------------------------------------------------------
  it("DC08: keine Form ohne Aussage bei den Fristen", () => {
    const { api } = _api();
    expect(api.optionFuer("fristen", {
      params_bestaetigt: false, rows: [{ aussage_moeglich: true,
                                         restlaufzeit_tage: 2 }],
    })).toBeNull();
    expect(api.optionFuer("fristen", {
      aussage_moeglich: false, rows: [{ aussage_moeglich: true,
                                        restlaufzeit_tage: 2 }],
    })).toBeNull();
    // Mit Aussage sehr wohl.
    const opt = api.optionFuer("fristen", {
      params_bestaetigt: true, aussage_moeglich: true,
      rows: [{ aussage_moeglich: true, restlaufzeit_tage: 2 }],
    });
    expect(opt).not.toBeNull();
    expect(opt.series[0].data[0].value).toBe(1);
  });

  // DC09 --------------------------------------------------------------------
  it("DC09: ein Abrufausfall ergibt nie eine Option", () => {
    const { api } = _api();
    ["fallampel", "eskalationen", "fristen", "lastverteilung",
     "meine_auftraege", "wiedervorlage", "naechste_aktion"].forEach((k) => {
      expect(api.optionFuer(k, { fehler: "HTTP 404" })).toBeNull();
      expect(api.optionFuer(k, null)).toBeNull();
    });
  });

  // DC10 --------------------------------------------------------------------
  it("DC10: jede Kachel des Katalogs ist entschieden", () => {
    const { api } = _api();
    const keys = [..._katalog.matchAll(/key="([a-z_]+)"/g)].map((m) => m[1]);
    expect(keys.length).toBe(8);
    // Beispieldaten, mit denen jede Kachel eine Option liefern KANN.
    const proben = {
      fallampel: { count: 1, cases: [{ ampel: "rot" }] },
      eskalationen: { items: [{ days_inactive: 5 }] },
      naechste_aktion: { actionable: 2, total_cases: 9 },
      wiedervorlage: { matters: [{ ampel: "rot" }], counts: { rot: 1 } },
      fristen: { params_bestaetigt: true, aussage_moeglich: true,
                 rows: [{ aussage_moeglich: true, restlaufzeit_tage: 5 }] },
      lastverteilung: { loads: [{ display_name: "A", active_cases: 3 }],
                        max_active_cases: 10 },
      meine_auftraege: { count: 1, cases: [{ ampel: "gelb" }] },
      kettenzustand: { ok: true, tip_seq: 42 },
    };
    keys.forEach((k) => {
      const opt = api.optionFuer(k, proben[k]);
      const begruendet = Object.prototype.hasOwnProperty.call(
        api.DIAGRAMMLOS, k);
      // Entweder eine Option ODER eine Begruendung — niemals beides fehlend.
      expect(!!opt || begruendet).toBe(true);
      if (!opt) { expect(String(api.DIAGRAMMLOS[k]).length)
        .toBeGreaterThan(10); }
    });
    // Der Zustand der Audit-Kette bekommt ausdruecklich KEINS.
    expect(api.optionFuer("kettenzustand", proben.kettenzustand)).toBeNull();
    expect(api.DIAGRAMMLOS.kettenzustand).toBeTruthy();
  });

  // DC11 --------------------------------------------------------------------
  it("DC11: keine Animation in irgendeiner Option", () => {
    const { api } = _api();
    [api.optionAmpelRing({ rot: 1 }, 1),
     api.optionAlterBalken({ bis3: 1 }),
     api.optionRestlaufzeit({ bis7: 1 }),
     api.optionAnteilBalken(1, 2, "blau"),
     api.optionLastBalken([{ name: "A", aktiv: 1, stufe: "ok" }], 5),
    ].forEach((o) => { expect(o.animation).toBe(false); });
  });

  // DC12 --------------------------------------------------------------------
  it("DC12: zeichne() meldet eine fehlende Bibliothek", () => {
    const { win, api } = _api();
    const host = win.document.createElement("div");

    // Ohne Bibliothek: die Kachel SAGT es, statt leer zu bleiben.
    expect(api.zeichne(host, api.optionAmpelRing({ rot: 1 }, 1), null))
      .toBeNull();
    expect(host.textContent).toContain("nicht geladen");

    // Mit Bibliothek: init und setOption werden gerufen.
    const host2 = win.document.createElement("div");
    let gesetzt = null;
    let entsorgt = false;
    const fake = { init: () => ({
      setOption: (o) => { gesetzt = o; },
      dispose: () => { entsorgt = true; },
    }) };
    const inst = api.zeichne(host2, api.optionAlterBalken({ bis3: 2 }), fake);
    expect(gesetzt.series[0].data[0].value).toBe(2);
    api.entsorge(inst);
    expect(entsorgt).toBe(true);
    // entsorge vertraegt Unfug, damit cleanupView nie daran scheitert.
    expect(() => api.entsorge(null)).not.toThrow();
    expect(() => api.entsorge({})).not.toThrow();
  });
});
