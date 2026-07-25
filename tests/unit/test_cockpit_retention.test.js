/**
 * tests/unit/test_cockpit_retention.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Aufbewahrung
 *
 * Testsuite fuer Build 521 (AP-2G / Idee 29): management/server/static/
 * cockpit_retention.js, Frontend zu /api/retention. Getestet wird der ECHTE
 * Code (readFileSync + JSDOM, window.AIWCockpitRetention).
 *
 * Der wichtigste Test ist RV02: die Sicht darf KEINE Bedienelemente haben.
 * Sie kann nicht löschen, und es soll auch nichts danach aussehen.
 *
 * RV01 — API vollstaendig verfuegbar
 * RV02 — KEINE Knoepfe, KEINE Eingabefelder, KEINE Auswahlfelder — in
 *        keinem der drei Zustaende
 * RV03 — der LOESCHVORBEHALT steht ganz oben, VOR der Liste
 * RV04 — fehlt die Zusicherung, wird das GEMELDET statt sie stillschweigend
 *        zu behaupten (rote Auszeichnung)
 * RV05 — 'without_reference' wird als UNGEPRUEFT benannt, nicht als 0-Wert
 *        weggelassen
 * RV06 — die angewandte Frist steht dabei — und ihr Fehlen wird benannt
 * RV07 — das Bezugsfeld steht im Klartext in der Zeile
 * RV08 — 'genau auf der Frist' (over_by_days 0) ist kein Leerwert
 * RV09 — drei unterscheidbare Zustaende: Fehler / Leerbefund / Befund
 * RV10 — der Leerbefund nennt die ungeprueften Faelle mit, sonst laese er
 *        sich als 'alles geprueft und in Ordnung'
 * RV11 — Reihenfolge des Backends bleibt; fehlender Zeitstempel ist '—'
 * RV12 — Markup in Benutzernamen bleibt Text, UTF-8 erhalten
 *
 * Version: v0.8.521 · Build: 521 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_retention.js",
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
  return _makeContext().AIWCockpitRetention;
}

function C(over) {
  return Object.assign(
    {
      subject_id: 4001,
      username: "kekz",
      status: "closed",
      reference_ts: 1690000000,
      reference_field: "updated_at",
      days_retained: 750,
      over_by_days: 20,
    },
    over
  );
}

function D(over) {
  return Object.assign(
    {
      generated_at: 1750000000,
      retention_days: 730,
      total_cases: 12,
      closed_cases: 5,
      without_reference: 0,
      candidate_count: 1,
      deletes_nothing: true,
      candidates: [C()],
    },
    over
  );
}

describe("cockpit_retention.js (Build 521)", () => {
  // RV01 --------------------------------------------------------------------
  it("RV01: API vollstaendig", () => {
    const api = _api();
    [
      "vorbehaltText",
      "vorbehaltOk",
      "fristText",
      "countsText",
      "referenceLabel",
      "fmtTs",
      "overText",
      "candidates",
      "renderRetention",
    ].forEach((n) => {
      expect(typeof api[n], n).toBe("function");
    });
  });

  // RV02 --------------------------------------------------------------------
  it("RV02: KEINE Bedienelemente — die Sicht kann nicht loeschen", () => {
    const win = _makeContext();
    const api = win.AIWCockpitRetention;
    const faelle = [
      D(),
      D({ candidates: [], candidate_count: 0 }),
      { error: "HTTP 503" },
    ];
    faelle.forEach((daten, i) => {
      const main = win.document.createElement("main");
      api.renderRetention(main, daten, {});
      expect(main.querySelectorAll("button").length, "Fall " + i).toBe(0);
      expect(main.querySelectorAll("input").length, "Fall " + i).toBe(0);
      expect(main.querySelectorAll("select").length, "Fall " + i).toBe(0);
      expect(main.querySelectorAll("form").length, "Fall " + i).toBe(0);
      expect(main.querySelectorAll("a").length, "Fall " + i).toBe(0);
    });
  });

  // RV03 --------------------------------------------------------------------
  it("RV03: der Loeschvorbehalt steht ganz oben", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitRetention.renderRetention(main, D(), {});
    const kinder = Array.from(main.children);
    const iVorbehalt = kinder.findIndex((e) =>
      e.className.includes("aiw-rt-vorbehalt")
    );
    const iTabelle = kinder.findIndex((e) =>
      e.className.includes("aiw-rt-table")
    );
    expect(iVorbehalt).toBeGreaterThan(-1);
    expect(iTabelle).toBeGreaterThan(-1);
    expect(iVorbehalt).toBeLessThan(iTabelle);
    const t = main.querySelector(".aiw-rt-vorbehalt");
    expect(t.className).toContain("is-ok");
    expect(t.textContent).toContain("PRÜFVORSCHLAG");
    expect(t.textContent).toContain("kann nicht löschen");
  });

  // RV04 --------------------------------------------------------------------
  it("RV04: fehlende Zusicherung wird gemeldet, nicht behauptet", () => {
    const api = _api();
    expect(api.vorbehaltOk(D({ deletes_nothing: true }))).toBe(true);
    expect(api.vorbehaltOk(D({ deletes_nothing: undefined }))).toBe(false);
    const t = api.vorbehaltText(D({ deletes_nothing: undefined }));
    expect(t).toContain("ACHTUNG");
    expect(t).toContain("keinesfalls als Arbeitsauftrag");

    const win = _makeContext();
    const main = win.document.createElement("main");
    const daten = D();
    delete daten.deletes_nothing;
    win.AIWCockpitRetention.renderRetention(main, daten, {});
    expect(main.querySelector(".aiw-rt-vorbehalt").className).toContain(
      "is-fehlt"
    );
  });

  // RV05 --------------------------------------------------------------------
  it("RV05: 'ungeprueft' wird benannt", () => {
    const api = _api();
    const t = api.countsText(
      D({
        candidate_count: 2,
        without_reference: 3,
        closed_cases: 5,
        total_cases: 12,
      })
    );
    expect(t).toContain("2 über der Frist");
    expect(t).toContain("3 ohne ermittelbaren");
    expect(t).toContain("UNGEPRÜFT");
    expect(t).toContain("weder Kandidat noch unverdächtig");
    expect(t).toContain("5");
    expect(t).toContain("12");
    // Auch eine 0 wird genannt, nicht weggelassen.
    expect(api.countsText(D({ without_reference: 0 }))).toContain(
      "0 ohne ermittelbaren"
    );
  });

  // RV06 --------------------------------------------------------------------
  it("RV06: die angewandte Frist — und ihr Fehlen", () => {
    const api = _api();
    expect(api.fristText(D({ retention_days: 730 }))).toContain("730");
    const ohne = api.fristText({ candidates: [] });
    expect(ohne).toContain("nicht mitgeliefert");
    expect(ohne).toContain("NICHT nachrechenbar");
  });

  // RV07 --------------------------------------------------------------------
  it("RV07: das Bezugsfeld steht im Klartext", () => {
    const api = _api();
    expect(api.referenceLabel("approved_at")).toContain("Freigabe");
    expect(api.referenceLabel("updated_at")).toContain("letzte Änderung");
    expect(api.referenceLabel(null)).toBe("(nicht erfasst)");
    expect(api.referenceLabel("erledigt_am")).toContain("unbekannt");

    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitRetention.renderRetention(
      main,
      D({ candidates: [C({ reference_field: "approved_at" })] }),
      {}
    );
    expect(main.querySelector(".aiw-rt-field").textContent).toContain(
      "approved_at"
    );
  });

  // RV08 --------------------------------------------------------------------
  it("RV08: 'genau auf der Frist' ist kein Leerwert", () => {
    const api = _api();
    expect(api.overText(C({ over_by_days: 0 }))).toBe("genau auf der Frist");
    expect(api.overText(C({ over_by_days: 20 }))).toBe("+20 T");
    expect(api.overText(C({ over_by_days: null }))).toBe("—");
  });

  // RV09 --------------------------------------------------------------------
  it("RV09: drei unterscheidbare Zustaende", () => {
    const win = _makeContext();
    const api = win.AIWCockpitRetention;

    const mErr = win.document.createElement("main");
    expect(api.renderRetention(mErr, { error: "HTTP 503" }, {}).state).toBe(
      "error"
    );
    expect(mErr.textContent).toContain("KEIN Leerbefund");

    const mLeer = win.document.createElement("main");
    const rLeer = api.renderRetention(
      mLeer,
      D({ candidates: [], candidate_count: 0 }),
      {}
    );
    expect(rLeer.state).toBe("leer");
    expect(rLeer.vorbehalt).toBe(true);

    const mBefund = win.document.createElement("main");
    expect(api.renderRetention(mBefund, D(), {}).count).toBe(1);
  });

  // RV10 --------------------------------------------------------------------
  it("RV10: der Leerbefund nennt die ungeprueften Faelle mit", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitRetention.renderRetention(
      main,
      D({
        candidates: [],
        candidate_count: 0,
        closed_cases: 9,
        without_reference: 2,
      }),
      {}
    );
    const t = main.querySelector(".aiw-rt-leer").textContent;
    expect(t).toContain("9");
    expect(t).toContain("2");
    expect(t).toContain("NICHT prüfen");
    // Die Frist steht auch beim Leerbefund darunter.
    expect(main.querySelector(".aiw-rt-foot").textContent).toContain("730");
  });

  // RV11 --------------------------------------------------------------------
  it("RV11: Reihenfolge bleibt; fehlender Zeitstempel ist '—'", () => {
    const api = _api();
    expect(api.fmtTs(null)).toBe("—");
    expect(api.fmtTs(1690000000)).toMatch(/^\d{4}-\d{2}-\d{2}$/);

    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitRetention.renderRetention(
      main,
      D({
        candidates: [
          C({ subject_id: 3 }),
          C({ subject_id: 1 }),
          C({ subject_id: 2 }),
        ],
      }),
      {}
    );
    const ids = Array.from(main.querySelectorAll(".aiw-rt-row")).map((r) =>
      r.getAttribute("data-subject")
    );
    expect(ids).toEqual(["3", "1", "2"]);
  });

  // RV12 --------------------------------------------------------------------
  it("RV12: Markup bleibt Text, UTF-8 erhalten", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    const name = '<img src=x onerror="1">Пётр';
    win.AIWCockpitRetention.renderRetention(
      main,
      D({ candidates: [C({ username: name })] }),
      {}
    );
    expect(main.querySelector("img")).toBe(null);
    expect(main.querySelector(".aiw-rt-case").textContent).toContain(name);
    expect(main.textContent).toContain("Пётр");
  });
});
