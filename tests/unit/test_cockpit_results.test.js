/**
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 * tests/unit/test_cockpit_results.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ermittlungsergebnis
 *
 * Testsuite fuer management/server/static/cockpit_results.js (Build 395).
 * Prueft den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitResults).
 *
 * RS01 — API verfuegbar.
 * RS02 — headline: DIE Hauptaussage steht in Klartext ("Von N Faellen sind M
 *        noch GAR NICHT bewertet") und faerbt die Kopfzeile rot.
 * RS03 — toRows/ampelOf: nie bewertet = rot und "ALLE (nie bewertet)" — die
 *        Luecke wird BENANNT, nicht durch einen Strich versteckt.
 * RS04 — filterRows/counts: alle / nie / unvollstaendig / vollstaendig.
 * RS05 — confidenceOption: x-Achse aus dem KATALOG (nicht aus den Daten);
 *        zwei Serien (schwerste/beste); fehlende Stufen sind 0, nicht Luecken.
 * RS06 — criterionNote: die SEMANTIK-Beschreibung reist mit (Schwere vs.
 *        Praezision); Kriterien ohne Skala sagen das.
 * RS07 — render: Kopfzeile, Vermerk, Tabelle; Standardsortierung ist
 *        ABDECKUNG, NICHT Score (mc).
 * RS08 — render: EIN Diagramm je Kriterium, KEIN Gesamtdiagramm; die ersten
 *        drei offen, der Rest eingeklappt.
 * RS09 — render: aufklappen ruft resize() (sonst bleibt das Diagramm leer und
 *        der Nutzer haelt das fuer "keine Daten").
 * RS10 — render ohne Statistik (Scope 'eigene' -> 403): die Sicht SAGT es,
 *        statt eine leere Flaeche zu zeigen; die Tabelle steht trotzdem.
 */

import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_results.js",
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
function _api() { return _ctx().AIWCockpitResults; }

function _fakeTabulator() {
  return function (container, options) {
    const self = this;
    this.options = options;
    this.data = options.data;
    this.replaceData = function (d) { self.data = d; };
    this.destroy = function () {};
  };
}

/** Fake-ECharts: merkt sich Optionen und resize()-Aufrufe. */
function _fakeEcharts() {
  const instances = [];
  return {
    instances,
    init: function (el) {
      const inst = {
        el,
        option: null,
        resized: 0,
        setOption: function (o) { inst.option = o; },
        resize: function () { inst.resized += 1; },
        dispose: function () {},
      };
      instances.push(inst);
      return inst;
    },
  };
}

const CRITERIA = [
  { code: "identification", label: "Identifizierung des Kontoinhabers",
    quality_scale: null, quality_label: null, quality_beschreibung: null,
    quality_items: [] },
  { code: "location_identification", label: "Ortsbestimmung",
    quality_scale: "location_quality", quality_label: "Ortsbestimmung",
    quality_beschreibung: "ordinal misst die PRAEZISION.",
    quality_items: [] },
  { code: "abuser", label: "Missbrauchshandlung",
    quality_scale: "abuser_quality", quality_label: "Missbrauchsbeziehung",
    quality_beschreibung:
      "ACHTUNG — ANDERE SEMANTIK: ordinal misst hier SCHWERE/AKTUALITAET, "
      + "NICHT Praezision.",
    quality_items: [] },
  { code: "cp_possession", label: "CP: Besitz", quality_scale: null,
    quality_items: [] },
];

function _stats() {
  return {
    faelle: 2,
    faelle_gesamt: 4,
    faelle_unbewertet: 2,
    hinweis: "Mittelwerte je KRITERIUM ...",
    criteria: {
      abuser: {
        schwerste: { n: 2, conf_hist: { verdacht: 1, gerichtsfest: 1 },
                     conf_mittel: 4.0, qual_hist: {}, qual_n: 0 },
        beste: { n: 1, conf_hist: { verdacht: 1 }, conf_mittel: 3.0,
                 qual_hist: {}, qual_n: 0 },
      },
    },
    catalog: {
      catalog_version: 1,
      confidence_items: [
        { code: "unbestimmt", label: "unbestimmt", ordinal: 0 },
        { code: "verdacht", label: "Verdacht", ordinal: 3 },
        { code: "gerichtsfest", label: "gerichtsfest", ordinal: 5 },
      ],
      criteria: CRITERIA,
    },
  };
}

function _cov() {
  return {
    faelle_gesamt: 4,
    nie_bewertet: 2,
    n_kriterien: 4,
    catalog_version: 1,
    vermerk: "PROVISORISCH — Gewichtung und Struktur dieser Formel sind mit "
      + "Chef-Ermittlerin und Staatsanwaltschaft NICHT abgestimmt.",
    scope: "alle",
    summary: { faelle_gesamt: 4, nie_bewertet: 2, voll_bewertet: 1,
               abdeckung_mittel: 0.38 },
    faelle: [
      { subject_id: 20, username: "b20", status: "open", assigned_to: null,
        n_bewertet: 0, n_kriterien: 4, abdeckung: 0.0, n_beste: 0,
        unbewertet: ["identification", "location_identification", "abuser",
                     "cp_possession"],
        score: 0, hoechste_konfidenz: null, zuletzt_bewertet: null,
        nie_bewertet: true },
      { subject_id: 21, username: "b21", status: "open", assigned_to: null,
        n_bewertet: 0, n_kriterien: 4, abdeckung: 0.0, n_beste: 0,
        unbewertet: ["identification", "location_identification", "abuser",
                     "cp_possession"],
        score: 0, hoechste_konfidenz: null, zuletzt_bewertet: null,
        nie_bewertet: true },
      { subject_id: 19, username: "b19", status: "in_progress",
        assigned_to: "h002", n_bewertet: 2, n_kriterien: 4, abdeckung: 0.5,
        n_beste: 1, unbewertet: ["location_identification", "cp_possession"],
        score: 8, hoechste_konfidenz: "gerichtsfest",
        zuletzt_bewertet: 1783000000, nie_bewertet: false },
      { subject_id: 18, username: "b18", status: "in_progress",
        assigned_to: "h002", n_bewertet: 4, n_kriterien: 4, abdeckung: 1.0,
        n_beste: 2, unbewertet: [], score: 14,
        hoechste_konfidenz: "gerichtsfest", zuletzt_bewertet: 1783100000,
        nie_bewertet: false },
    ],
  };
}

function _main(win) {
  const el = win.document.createElement("div");
  win.document.body.appendChild(el);
  return el;
}

describe("cockpit_results (Build 395)", () => {
  it("RS01 — API verfuegbar", () => {
    const api = _api();
    expect(typeof api.renderResults).toBe("function");
    expect(typeof api.confidenceOption).toBe("function");
  });

  it("RS02 — headline: die blinden Flecken sind die Hauptaussage", () => {
    const api = _api();
    const h = api.headline(_cov());
    expect(h).toContain("Von 4 Faellen sind 2 noch GAR NICHT bewertet");
    expect(h).toContain("Vollstaendig bewertet: 1");
    expect(api.hasBlindSpots(_cov())).toBe(true);

    // Ohne blinde Flecken: gruene Aussage.
    const sauber = _cov();
    sauber.summary.nie_bewertet = 0;
    expect(api.headline(sauber)).toContain("Alle 4 Faelle sind bewertet");
    expect(api.hasBlindSpots(sauber)).toBe(false);

    expect(api.headline({ summary: { faelle_gesamt: 0 } }))
      .toContain("Keine Faelle");
  });

  it("RS03 — die Luecke wird BENANNT, nicht versteckt", () => {
    const api = _api();
    const rows = api.toRows(_cov());
    expect(rows).toHaveLength(4);

    const r20 = rows.find((r) => r.subject_id === 20);
    expect(r20.ampel).toBe("rot");
    // NICHT "-" und nicht leer.
    expect(r20.fehlend).toBe("ALLE (nie bewertet)");
    expect(r20.abdeckung_txt).toBe("0/4");
    expect(r20.assigned_to).toBe("\u2014");

    const r19 = rows.find((r) => r.subject_id === 19);
    expect(r19.ampel).toBe("gelb");
    expect(r19.fehlend).toContain("location_identification");
    expect(r19.abdeckung_txt).toBe("2/4");

    const r18 = rows.find((r) => r.subject_id === 18);
    expect(r18.ampel).toBe("gruen");
    expect(r18.fehlend).toBe("\u2014");

    expect(api.ampelOf({ nie_bewertet: true })).toBe("rot");
    expect(api.ampelOf({ n_bewertet: 4, n_kriterien: 4 })).toBe("gruen");
    expect(api.ampelOf({ n_bewertet: 1, n_kriterien: 4 })).toBe("gelb");
  });

  it("RS04 — Filter und Zaehler", () => {
    const api = _api();
    const rows = api.toRows(_cov());
    expect(api.filterRows(rows, "")).toHaveLength(4);
    expect(api.filterRows(rows, "nie")).toHaveLength(2);
    expect(api.filterRows(rows, "teil")).toHaveLength(1);
    expect(api.filterRows(rows, "voll")).toHaveLength(1);

    expect(api.counts(rows)).toEqual({ alle: 4, nie: 2, teil: 1, voll: 1 });
  });

  it("RS05 — confidenceOption: x-Achse aus dem KATALOG", () => {
    const api = _api();
    const opt = api.confidenceOption("abuser", _stats());

    // Die Achse kommt aus confidence_items — NICHT aus den vorkommenden
    // Werten. Sonst verschoebe sie sich je nach Datenlage und zwei Diagramme
    // waeren nicht vergleichbar.
    expect(opt.xAxis.data).toEqual([
      "unbestimmt (0)", "Verdacht (3)", "gerichtsfest (5)"]);

    expect(opt.series).toHaveLength(2);
    expect(opt.series[0].name).toBe("schwerste");
    // unbestimmt=0 (kommt nicht vor), verdacht=1, gerichtsfest=1
    expect(opt.series[0].data).toEqual([0, 1, 1]);
    expect(opt.series[1].name).toBe("beste");
    expect(opt.series[1].data).toEqual([0, 1, 0]);

    expect(opt.title.text).toBe("Missbrauchshandlung");

    // Ein Kriterium OHNE Daten: alle Balken 0 — aber die Achse steht.
    const leer = api.confidenceOption("identification", _stats());
    expect(leer.series[0].data).toEqual([0, 0, 0]);
    expect(leer.xAxis.data).toHaveLength(3);
  });

  it("RS06 — die Semantik-Beschreibung reist mit", () => {
    const api = _api();
    const note = api.criterionNote(CRITERIA[2]);   // abuser
    expect(note).toContain("SCHWERE");
    expect(note).toContain("NICHT Praezision");

    expect(api.criterionNote(CRITERIA[1])).toContain("PRAEZISION");

    // Ohne Skala wird das GESAGT, nicht verschwiegen.
    expect(api.criterionNote(CRITERIA[0]))
      .toContain("Kein Qualitaetsmass hinterlegt");
  });

  it("RS07 — render: Kopfzeile rot, Vermerk fest, Sortierung nach Abdeckung", () => {
    const win = _ctx();
    const api = win.AIWCockpitResults;
    const main = _main(win);

    const res = api.renderResults(main, _cov(), _stats(), {
      Tabulator: _fakeTabulator(), echarts: _fakeEcharts() });

    const head = main.querySelector("#aiw-res-headline");
    expect(head.textContent).toContain("2 noch GAR NICHT bewertet");
    expect(head.classList.contains("warn")).toBe(true);

    // Der Vermerk steht fest unter der Tabelle.
    const v = main.querySelector("#aiw-res-vermerk");
    expect(v).toBeTruthy();
    expect(v.textContent).toContain("NICHT abgestimmt");

    // STANDARDSORTIERUNG: Abdeckung — NICHT Score (mc 2026-07-12). Eine
    // Voreinstellung nach der provisorischen Kennzahl wuerde eine
    // Priorisierung suggerieren, die niemand abgesegnet hat.
    expect(res.table.options.initialSort).toEqual([
      { column: "abdeckung", dir: "asc" }]);
    expect(res.table.options.initialSort[0].column).not.toBe("score");

    // Filter: vier Einträge.
    expect(main.querySelectorAll("#aiw-res-filter option")).toHaveLength(4);
  });

  it("RS08 — ein Diagramm je Kriterium, KEIN Gesamtdiagramm", () => {
    const win = _ctx();
    const api = win.AIWCockpitResults;
    const main = _main(win);
    const E = _fakeEcharts();

    const res = api.renderResults(main, _cov(), _stats(), {
      Tabulator: _fakeTabulator(), echarts: E });

    const boxes = main.querySelectorAll(".aiw-res-chartbox");
    expect(boxes).toHaveLength(4);              // = Zahl der Kriterien
    expect(res.charts).toHaveLength(4);         // fuer cleanupView()
    expect(E.instances).toHaveLength(4);

    // Jedes Diagramm haengt an GENAU EINEM Kriterium.
    const codes = Array.from(boxes).map(
      (b) => b.getAttribute("data-criterion"));
    expect(codes).toEqual(["identification", "location_identification",
                           "abuser", "cp_possession"]);

    // Die ersten drei offen, der Rest eingeklappt (mc).
    expect(boxes[0].open).toBe(true);
    expect(boxes[2].open).toBe(true);
    expect(boxes[3].open).toBe(false);

    // Die Semantik-Warnung steht UNTER dem Diagramm.
    expect(boxes[2].querySelector(".aiw-res-note").textContent)
      .toContain("SCHWERE");

    // Und der Hinweis, dass es KEIN Gesamtdiagramm gibt.
    expect(main.textContent).toContain("KEIN Gesamtdiagramm");
  });

  it("RS09 — Aufklappen ruft resize()", () => {
    const win = _ctx();
    const api = win.AIWCockpitResults;
    const main = _main(win);
    const E = _fakeEcharts();

    api.renderResults(main, _cov(), _stats(), {
      Tabulator: _fakeTabulator(), echarts: E });

    const zu = main.querySelectorAll(".aiw-res-chartbox")[3];
    expect(zu.open).toBe(false);
    expect(E.instances[3].resized).toBe(0);

    // ECharts rendert in einem geschlossenen <details> mit Groesse 0. Ohne
    // resize() bliebe das Diagramm LEER — und der Nutzer haelt das fuer
    // "keine Daten". Genau das waere ein stiller Fehlschluss.
    zu.open = true;
    zu.dispatchEvent(new win.Event("toggle"));
    expect(E.instances[3].resized).toBe(1);
  });

  it("RS10 — ohne Statistik (Scope 'eigene'): die Sicht SAGT es", () => {
    const win = _ctx();
    const api = win.AIWCockpitResults;
    const main = _main(win);

    const res = api.renderResults(main, _cov(), null, {
      Tabulator: _fakeTabulator(), echarts: _fakeEcharts() });

    // Keine leere Flaeche, sondern eine Begruendung.
    const hint = main.querySelector("#aiw-res-nostats");
    expect(hint).toBeTruthy();
    expect(hint.textContent).toContain("results.view");
    expect(hint.textContent).toContain("alle");

    expect(res.charts).toHaveLength(0);
    expect(main.querySelectorAll(".aiw-res-chartbox")).toHaveLength(0);

    // Kopfzeile, Tabelle und Vermerk stehen TROTZDEM — die Abdeckung der
    // eigenen Faelle sieht der Ermittler vollstaendig.
    expect(main.querySelector("#aiw-res-headline")).toBeTruthy();
    expect(res.table).toBeTruthy();
    expect(main.querySelector("#aiw-res-vermerk")).toBeTruthy();
  });
});
