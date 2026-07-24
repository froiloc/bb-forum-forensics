/**
 * tests/unit/test_cockpit_escalation.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Eskalationen
 *
 * Testsuite fuer Build 516 (AP-2G / Idee 23): management/server/static/
 * cockpit_escalation.js, Frontend zu /api/escalations (Build 515). Getestet
 * wird der ECHTE Code (readFileSync + JSDOM, window.AIWCockpitEscalation).
 *
 * Der Schwerpunkt liegt auf den drei Entscheidungen aus dem Dateikopf und auf
 * Grundregel 1 — was gesagt und was verschwiegen wird.
 *
 * ES01 — API vollstaendig verfuegbar
 * ES02 — Entscheidung (1): subject_id === null wird als "systemisch (kein
 *        Einzelfall)" ausgewiesen, NICHT als leere Zelle oder Fall 0
 * ES03 — days_inactive === null wird als '—' ausgewiesen ("nie erfasst" ist
 *        etwas anderes als "0 Tage inaktiv")
 * ES04 — countsText nennt ALLE drei Schweren, auch die mit 0, plus die Zahl
 *        der bewerteten Faelle (Beleg, dass erhoben wurde)
 * ES05 — Entscheidung (2): thresholdText nennt alle drei Schwellen — und
 *        sagt es AUSDRUECKLICH, wenn der Massstab fehlt
 * ES06 — Entscheidung (3): der fehlende Quittierungsweg wird BENANNT
 * ES07 — drei unterscheidbare Zustaende: Fehler / Leerbefund / Befund
 * ES08 — Fehler ist KEIN Leerbefund: die Sicht behauptet nicht "nichts liegt an"
 * ES09 — Reihenfolge des Backends bleibt unangetastet (keine zweite Sortierung)
 * ES10 — die Begruendung steht woertlich in der Zeile; Markup bleibt Text
 * ES11 — Massstab und Quittierungs-Ansage stehen AUCH beim Leerbefund
 * ES12 — eine unbekannte Schwere faellt AUF, statt still wie 'niedrig'
 *        auszusehen
 *
 * Version: v0.8.516 · Build: 516 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_escalation.js",
  "utf-8"
);

function _makeContext() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

function _api() {
  return _makeContext().AIWCockpitEscalation;
}

// Eine Meldung in der Form aus escalation_to_dict.
function I(over) {
  return Object.assign(
    {
      rule_code: "fall_ueberfaellig",
      label: "Fall ueberfaellig",
      severity: "hoch",
      subject_id: 7001,
      message: "Fall 7001 (kekz): rote Ampel, 34 Tage inaktiv (>= 30).",
      days_inactive: 34,
    },
    over
  );
}

// Vollstaendige /api/escalations-Antwort.
function D(over) {
  return Object.assign(
    {
      generated_at: 1750000000,
      total_cases: 47,
      count_hoch: 0,
      count_mittel: 0,
      count_niedrig: 0,
      items: [],
      thresholds: {
        red_overdue_days: 30,
        stale_open_days: 14,
        backlog_high: 10,
      },
      acknowledgeable: false,
    },
    over
  );
}

describe("cockpit_escalation.js (Build 516)", () => {
  // ES01 --------------------------------------------------------------------
  it("ES01: API vollstaendig", () => {
    const api = _api();
    [
      "severityClass",
      "severityLabel",
      "itemTarget",
      "inactiveText",
      "countsText",
      "thresholdText",
      "ackText",
      "items",
      "renderEscalation",
    ].forEach((n) => {
      expect(typeof api[n], n).toBe("function");
    });
  });

  // ES02 --------------------------------------------------------------------
  it("ES02: subject_id null ist eine Aussage, keine Luecke", () => {
    const api = _api();
    expect(api.itemTarget(I({ subject_id: null }))).toBe(
      "systemisch (kein Einzelfall)"
    );
    expect(api.itemTarget(I({ subject_id: undefined }))).toBe(
      "systemisch (kein Einzelfall)"
    );
    expect(api.itemTarget(I({ subject_id: 7001 }))).toBe("Fall 7001");
    // Und im DOM steht es auch so.
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitEscalation.renderEscalation(
      main,
      D({
        count_hoch: 1,
        items: [I({ rule_code: "rueckstau_hoch", subject_id: null,
                    days_inactive: null })],
      }),
      {}
    );
    const zelle = main.querySelector(".aiw-esk-target");
    expect(zelle.textContent).toContain("systemisch");
    expect(zelle.textContent).not.toBe("");
  });

  // ES03 --------------------------------------------------------------------
  it("ES03: days_inactive null ist nicht 0", () => {
    const api = _api();
    expect(api.inactiveText(I({ days_inactive: null }))).toBe("—");
    expect(api.inactiveText(I({ days_inactive: 0 }))).toBe("0 T");
    expect(api.inactiveText(I({ days_inactive: 34 }))).toBe("34 T");
  });

  // ES04 --------------------------------------------------------------------
  it("ES04: countsText nennt alle drei Schweren und die Fallzahl", () => {
    const api = _api();
    const t = api.countsText(
      D({ count_hoch: 2, count_mittel: 0, count_niedrig: 0, total_cases: 47 })
    );
    expect(t).toContain("2 hoch");
    expect(t).toContain("0 mittel");
    expect(t).toContain("0 niedrig");
    expect(t).toContain("47");
  });

  // ES05 --------------------------------------------------------------------
  it("ES05: der Massstab wird genannt — oder sein Fehlen", () => {
    const api = _api();
    const t = api.thresholdText(D());
    expect(t).toContain("30");
    expect(t).toContain("14");
    expect(t).toContain("10");
    // Fehlt er, wird das AUSDRUECKLICH gesagt.
    const ohne = api.thresholdText({ items: [] });
    expect(ohne).toContain("nicht mitgeliefert");
    expect(ohne).toContain("NICHT nachrechenbar");
  });

  // ES06 --------------------------------------------------------------------
  it("ES06: der fehlende Quittierungsweg wird benannt", () => {
    const api = _api();
    expect(api.ackText(D({ acknowledgeable: false }))).toContain(
      "nicht möglich"
    );
    // Kommt der Schreibpfad, verschwindet die Ansage von selbst.
    expect(api.ackText(D({ acknowledgeable: true }))).toBe("");
  });

  // ES07 --------------------------------------------------------------------
  it("ES07: drei unterscheidbare Zustaende", () => {
    const win = _makeContext();
    const api = win.AIWCockpitEscalation;

    const mErr = win.document.createElement("main");
    expect(api.renderEscalation(mErr, { error: "HTTP 503" }, {}).state).toBe(
      "error"
    );

    const mLeer = win.document.createElement("main");
    const rLeer = api.renderEscalation(mLeer, D(), {});
    expect(rLeer.state).toBe("leer");
    expect(mLeer.querySelector(".aiw-esk-leer")).toBeTruthy();

    const mBefund = win.document.createElement("main");
    const rBefund = api.renderEscalation(
      mBefund,
      D({ count_hoch: 1, items: [I()] }),
      {}
    );
    expect(rBefund.state).toBe("befund");
    expect(rBefund.count).toBe(1);
    expect(mBefund.querySelectorAll(".aiw-esk-row").length).toBe(1);
  });

  // ES08 --------------------------------------------------------------------
  it("ES08: ein Fehler behauptet nicht 'nichts liegt an'", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitEscalation.renderEscalation(
      main,
      { error: "HTTP 503" },
      {}
    );
    const text = main.textContent;
    expect(text).toContain("nicht verfügbar");
    expect(text).toContain("KEIN Leerbefund");
    // Der Leerbefund-Block darf hier NICHT erscheinen.
    expect(main.querySelector(".aiw-esk-leer")).toBe(null);
    expect(main.querySelectorAll(".aiw-esk-row").length).toBe(0);
  });

  // ES09 --------------------------------------------------------------------
  it("ES09: Reihenfolge des Backends bleibt unangetastet", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    // Absichtlich NICHT nach Schwere sortiert uebergeben: das Frontend darf
    // nicht heimlich umsortieren, sonst gaebe es zwei Wahrheitsquellen.
    const reihenfolge = [
      I({ subject_id: 1, severity: "mittel" }),
      I({ subject_id: 2, severity: "hoch" }),
      I({ subject_id: 3, severity: "niedrig" }),
    ];
    win.AIWCockpitEscalation.renderEscalation(
      main,
      D({ items: reihenfolge, count_hoch: 1, count_mittel: 1, count_niedrig: 1 }),
      {}
    );
    const ziele = Array.from(main.querySelectorAll(".aiw-esk-target")).map(
      (e) => e.textContent
    );
    expect(ziele).toEqual(["Fall 1", "Fall 2", "Fall 3"]);
  });

  // ES10 --------------------------------------------------------------------
  it("ES10: Begruendung woertlich, Markup bleibt Text", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    const boese =
      'Fall 9 (<img src=x onerror="1">Пётр): rote Ampel, 40 Tage inaktiv.';
    win.AIWCockpitEscalation.renderEscalation(
      main,
      D({ count_hoch: 1, items: [I({ message: boese })] }),
      {}
    );
    expect(main.querySelector("img")).toBe(null);
    expect(main.querySelector(".aiw-esk-msg").textContent).toBe(boese);
    expect(main.textContent).toContain("Пётр");
  });

  // ES11 --------------------------------------------------------------------
  it("ES11: Massstab und Ansage stehen auch beim Leerbefund", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitEscalation.renderEscalation(main, D(), {});
    expect(main.querySelector(".aiw-esk-foot").textContent).toContain("30");
    expect(main.querySelector(".aiw-esk-ack").textContent).toContain(
      "nicht möglich"
    );
    // Und der Leerbefund sagt, worauf er sich stuetzt.
    expect(main.querySelector(".aiw-esk-leer").textContent).toContain("47");
  });

  // ES12 --------------------------------------------------------------------
  it("ES12: unbekannte Schwere faellt auf", () => {
    const api = _api();
    expect(api.severityClass("kritisch")).toBe("is-unbekannt");
    expect(api.severityLabel("kritisch")).toContain("unbekannt");
    expect(api.severityLabel("kritisch")).toContain("kritisch");
    // Bekannte Werte bleiben unveraendert.
    expect(api.severityClass("hoch")).toBe("is-hoch");
    expect(api.severityLabel("mittel")).toBe("mittel");
  });
});
