/**
 * =============================================================================
 * tests/unit/test_cockpit_planung_pdf.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 522 (AP-3F / Idee 40): die Verweise auf den
 * Prognosebericht in der Sicht 'Prognose & Gantt'.
 *
 * Warum diese Datei getrennt von test_cockpit_planung.test.js liegt:
 *   Die bestehende Suite (PL01-PL08) belegt das Verhalten der Sicht aus
 *   Build 448. Sie bleibt UNVERAENDERT — so ist an der Regression ablesbar,
 *   dass dieser Build nichts an der bisherigen Zusicherung geaendert hat.
 *   Die neuen Belege stehen daneben, nicht darin.
 *
 *   FP01 — reportUrl ist Teil der oeffentlichen API.
 *   FP02 — reportUrl: Vorgabe ist 'pdf'; leerer/fehlender Wert ebenso.
 *   FP03 — reportUrl: 'html' wird uebernommen.
 *   FP04 — reportUrl: ein UNBEKANNTES Format wird DURCHGEREICHT (nicht heimlich
 *          zu 'pdf' korrigiert) — der Server soll es mit 400 beantworten.
 *   FP05 — reportUrl: lookback_days nur bei positiver ganzer Zahl; 0, negativ,
 *          gebrochen, 'abc', null, undefined haengen NICHTS an.
 *   FP06 — reportUrl: der Formatwert wird kodiert (keine Parameter-Injektion
 *          ueber '&').
 *   FP07 — renderPlanung: genau ZWEI Verweise, beide mit target=_blank und
 *          rel=noopener, in der Reihenfolge PDF -> HTML.
 *   FP08 — renderPlanung: der PDF-Verweis traegt das Rueckblickfenster der
 *          ANGEZEIGTEN Prognose (Beleg und Sicht zeigen denselben Ausschnitt).
 *   FP09 — renderPlanung: bei duenner Datenlage steht ein Hinweis AN den
 *          Verweisen — bevor jemand einen Beleg erzeugt, den er vorlegt.
 *   FP10 — renderPlanung: bei belastbarer Datenlage KEIN Hinweis (die Warnung
 *          soll etwas bedeuten, wenn sie erscheint).
 *   FP11 — renderPlanung: die Verweise stehen VOR der Szenariotabelle im DOM.
 *   FP12 — renderPlanung: kein globales '.aiw-btn' — die Klassen sind
 *          sichtgebunden ('.aiw-fc-*'), wie cockpit.css es verlangt.
 * =============================================================================
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_planung.js",
  "utf-8"
);

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

function _api() {
  return _win().AIWCockpitPlanung;
}

function _forecast(over) {
  return Object.assign(
    {
      now_day: "2026-07-25",
      backlog: 12,
      lookback_days: 30,
      completions_observed: 6,
      observed_rate_per_day: 0.2,
      data_sufficient: true,
      scenarios: [
        { name: "optimistisch", factor: 1.25, rate_per_day: 0.25,
          days_to_clear: 48, finish_day: "2026-09-11" },
        { name: "erwartet", factor: 1.0, rate_per_day: 0.2,
          days_to_clear: 60, finish_day: "2026-09-23" },
        { name: "pessimistisch", factor: 0.75, rate_per_day: 0.15,
          days_to_clear: 80, finish_day: "2026-10-13" },
      ],
      assumptions: ["Backlog = Faelle mit status in open, in_progress."],
      capacity_context: null,
    },
    over || {}
  );
}

function _gantt() {
  return { lanes: [] };
}

// Ein ECharts-Doppel: init() gibt ein Objekt mit setOption/dispose zurueck.
// Die Sicht darf ohne echte Bibliothek geprueft werden — sie faellt sonst in
// den Platzhalter-Zweig und die Verweise waeren nicht mitgeprueft.
function _fakeECharts() {
  return {
    init: function () {
      return { setOption: function () {}, dispose: function () {} };
    },
  };
}

function _render(win, fc) {
  const main = win.document.createElement("div");
  win.AIWCockpitPlanung.renderPlanung(
    main,
    { forecast: fc, gantt: _gantt() },
    { ECharts: _fakeECharts() }
  );
  return main;
}

describe("Build 522 — Prognosebericht-Verweise (AP-3F)", () => {
  it("FP01: reportUrl ist Teil der API", () => {
    expect(typeof _api().reportUrl).toBe("function");
  });

  it("FP02: Vorgabe ist pdf (auch bei leer/fehlend)", () => {
    const api = _api();
    expect(api.reportUrl()).toBe("/api/forecast/report?format=pdf");
    expect(api.reportUrl("")).toBe("/api/forecast/report?format=pdf");
    expect(api.reportUrl(null)).toBe("/api/forecast/report?format=pdf");
  });

  it("FP03: html wird uebernommen", () => {
    expect(_api().reportUrl("html")).toBe("/api/forecast/report?format=html");
  });

  it("FP04: unbekanntes Format wird DURCHGEREICHT, nicht korrigiert", () => {
    // Absicht: der Server antwortet mit 400 und nennt die gueltigen Werte.
    // Ein Frontend, das Eingaben heimlich korrigiert, verbirgt den Fehler.
    expect(_api().reportUrl("xlsx")).toBe("/api/forecast/report?format=xlsx");
  });

  it("FP05: lookback_days nur bei positiver ganzer Zahl", () => {
    const api = _api();
    expect(api.reportUrl("pdf", 7)).toContain("&lookback_days=7");
    expect(api.reportUrl("pdf", "14")).toContain("&lookback_days=14");
    [0, -5, 2.5, "abc", null, undefined, NaN, Infinity].forEach((bad) => {
      expect(api.reportUrl("pdf", bad)).not.toContain("lookback_days");
    });
  });

  it("FP06: Formatwert wird kodiert (keine Parameter-Injektion)", () => {
    const url = _api().reportUrl("pdf&lookback_days=999");
    expect(url).not.toContain("pdf&lookback_days=999");
    expect(url).toContain("pdf%26lookback_days%3D999");
  });

  it("FP07: genau zwei Verweise, PDF vor HTML, target/rel gesetzt", () => {
    const win = _win();
    const main = _render(win, _forecast());
    const links = main.querySelectorAll("a.aiw-fc-reportlink");
    expect(links.length).toBe(2);
    expect(links[0].getAttribute("href")).toContain("format=pdf");
    expect(links[1].getAttribute("href")).toContain("format=html");
    for (const a of links) {
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toBe("noopener");
      expect(a.getAttribute("title")).toBeTruthy();
    }
  });

  it("FP08: Verweis traegt das Rueckblickfenster der Sicht", () => {
    const win = _win();
    const main = _render(win, _forecast({ lookback_days: 7 }));
    const href = main
      .querySelector("a.aiw-fc-reportlink")
      .getAttribute("href");
    expect(href).toContain("lookback_days=7");
  });

  it("FP09: duenne Datenlage -> Hinweis an den Verweisen", () => {
    const win = _win();
    const main = _render(win, _forecast({ data_sufficient: false }));
    const note = main.querySelector(".aiw-fc-note");
    expect(note).not.toBeNull();
    expect(note.textContent).toContain("keine belastbare Prognose");
  });

  it("FP10: belastbare Datenlage -> kein Hinweis", () => {
    const win = _win();
    const main = _render(win, _forecast({ data_sufficient: true }));
    expect(main.querySelector(".aiw-fc-note")).toBeNull();
  });

  it("FP11: Verweise stehen VOR der Szenariotabelle", () => {
    const win = _win();
    const main = _render(win, _forecast());
    const actions = main.querySelector(".aiw-fc-actions");
    const table = main.querySelector("table.aiw-forecast");
    expect(actions).not.toBeNull();
    expect(table).not.toBeNull();
    // compareDocumentPosition: 4 = 'folgt im Dokument'.
    expect(
      actions.compareDocumentPosition(table) &
        win.Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it("FP12: kein globales .aiw-btn (Klassen sind sichtgebunden)", () => {
    const win = _win();
    const main = _render(win, _forecast({ data_sufficient: false }));
    expect(main.querySelectorAll(".aiw-btn").length).toBe(0);
    // Zusaetzlich am QUELLTEXT: keine ZUWEISUNG einer Klasse, die 'aiw-btn'
    // enthaelt. Bewusst nicht 'enthaelt den String aiw-btn' — der Dateikopf
    // ERWAEHNT die verbotene Klasse in seiner Begruendung, und eine
    // Begruendung darf nicht als Verstoss gezaehlt werden.
    expect(_src).not.toMatch(/className\s*=\s*['"][^'"]*aiw-btn/);
  });
});
