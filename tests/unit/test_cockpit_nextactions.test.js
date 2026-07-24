/**
 * tests/unit/test_cockpit_nextactions.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Arbeitsschlange
 *
 * Testsuite fuer Build 519 (AP-2F / Idee 22): management/server/static/
 * cockpit_nextactions.js, Frontend zu /api/next_actions. Getestet wird der
 * ECHTE Code (readFileSync + JSDOM, window.AIWCockpitNextActions).
 *
 * NX01 — API vollstaendig verfuegbar
 * NX02 — Entscheidung (1): die Begruendung steht WOERTLICH und als eigene
 *        Spalte im DOM — nicht gekuerzt, nicht in einem Attribut versteckt
 * NX03 — Entscheidung (2): countsText nennt ALLE DREI Zahlen
 * NX04 — Entscheidung (3): scopeText benennt den Umfang — und sagt es
 *        ausdruecklich, wenn er fehlt
 * NX05 — Entscheidung (4): die Reihenfolge des Backends bleibt unangetastet
 * NX06 — drei unterscheidbare Zustaende: Fehler / Leerbefund / Befund
 * NX07 — ein Fehler behauptet NICHT 'nichts zu tun'
 * NX08 — der Leerbefund nennt seine Grundlage (geprüfte und abgeschlossene
 *        Faelle) statt nur 'keine Eintraege'
 * NX09 — 'NICHT zugewiesen' wird als Klartext ausgewiesen (die Aussage, auf
 *        die es in dieser Sicht ankommt)
 * NX10 — eine unbekannte Dringlichkeit faellt AUF, statt still wie 'routine'
 *        auszusehen
 * NX11 — fehlender Zeitstempel -> '—', nicht 1970
 * NX12 — Markup in Benutzernamen/Begruendung bleibt Text, UTF-8 erhalten
 *
 * Version: v0.8.519 · Build: 519 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_nextactions.js",
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
  return _makeContext().AIWCockpitNextActions;
}

function I(over) {
  return Object.assign(
    {
      subject_id: 6001,
      username: "kekz",
      action: "ueberfaellig — sichten/bearbeiten",
      reason: "rote Ampel (inaktiv_lang), seit 34 Tagen keine Aktivität",
      urgency: "dringend",
      priority: 3,
      ampel: "rot",
      status: "open",
      assigned: true,
      last_activity_at: 1750000000,
    },
    over
  );
}

function D(over) {
  return Object.assign(
    {
      generated_at: 1750000000,
      scope: "alle",
      granted_scope: "alle",
      total_cases: 12,
      actionable: 1,
      done_excluded: 4,
      items: [I()],
    },
    over
  );
}

describe("cockpit_nextactions.js (Build 519)", () => {
  // NX01 --------------------------------------------------------------------
  it("NX01: API vollstaendig", () => {
    const api = _api();
    [
      "urgencyClass",
      "urgencyLabel",
      "ampelClass",
      "assignedText",
      "fmtTs",
      "scopeText",
      "countsText",
      "items",
      "renderNextActions",
    ].forEach((n) => {
      expect(typeof api[n], n).toBe("function");
    });
  });

  // NX02 --------------------------------------------------------------------
  it("NX02: die Begruendung steht woertlich und sichtbar", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    const grund = "rote Ampel (inaktiv_lang), seit 34 Tagen keine Aktivität";
    win.AIWCockpitNextActions.renderNextActions(
      main,
      D({ items: [I({ reason: grund })] }),
      {}
    );
    const zelle = main.querySelector(".aiw-na-reason");
    expect(zelle).toBeTruthy();
    // WOERTLICH — nicht gekuerzt, nicht umformuliert.
    expect(zelle.textContent).toBe(grund);
    // Und die Handlung steht daneben, nicht anstelle der Begruendung.
    expect(main.querySelector(".aiw-na-action").textContent).toContain(
      "sichten"
    );
  });

  // NX03 --------------------------------------------------------------------
  it("NX03: alle drei Zahlen", () => {
    const api = _api();
    const t = api.countsText(
      D({ actionable: 3, total_cases: 12, done_excluded: 4 })
    );
    expect(t).toContain("3");
    expect(t).toContain("12");
    expect(t).toContain("4");
    expect(t).toContain("abgeschlossen");
    // Auch Nullen werden genannt.
    const leer = api.countsText(
      D({ actionable: 0, total_cases: 0, done_excluded: 0 })
    );
    expect(leer).toContain("0 handlungsbedürftig");
  });

  // NX04 --------------------------------------------------------------------
  it("NX04: der Umfang wird benannt — auch sein Fehlen", () => {
    const api = _api();
    expect(api.scopeText(D({ scope: "alle" }))).toContain("Dienststelle");
    expect(api.scopeText(D({ scope: "eigene" }))).toContain("eigenen");
    const ohne = api.scopeText({ items: [] });
    expect(ohne).toContain("nicht angegeben");
    expect(ohne).toContain("unklar");
  });

  // NX05 --------------------------------------------------------------------
  it("NX05: Reihenfolge des Backends bleibt", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    // Absichtlich NICHT nach Dringlichkeit sortiert uebergeben.
    win.AIWCockpitNextActions.renderNextActions(
      main,
      D({
        actionable: 3,
        items: [
          I({ subject_id: 1, urgency: "routine" }),
          I({ subject_id: 2, urgency: "dringend" }),
          I({ subject_id: 3, urgency: "bald" }),
        ],
      }),
      {}
    );
    const ids = Array.from(main.querySelectorAll(".aiw-na-row")).map((r) =>
      r.getAttribute("data-subject")
    );
    expect(ids).toEqual(["1", "2", "3"]);
  });

  // NX06 --------------------------------------------------------------------
  it("NX06: drei unterscheidbare Zustaende", () => {
    const win = _makeContext();
    const api = win.AIWCockpitNextActions;

    const mErr = win.document.createElement("main");
    expect(api.renderNextActions(mErr, { error: "HTTP 503" }, {}).state).toBe(
      "error"
    );

    const mLeer = win.document.createElement("main");
    expect(
      api.renderNextActions(mLeer, D({ items: [], actionable: 0 }), {}).state
    ).toBe("leer");
    expect(mLeer.querySelector(".aiw-na-leer")).toBeTruthy();

    const mBefund = win.document.createElement("main");
    const r = api.renderNextActions(mBefund, D(), {});
    expect(r.state).toBe("befund");
    expect(r.count).toBe(1);
  });

  // NX07 --------------------------------------------------------------------
  it("NX07: ein Fehler behauptet nicht 'nichts zu tun'", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitNextActions.renderNextActions(
      main,
      { error: "HTTP 500" },
      {}
    );
    expect(main.textContent).toContain("nicht verfügbar");
    expect(main.textContent).toContain("KEIN Leerbefund");
    expect(main.querySelector(".aiw-na-leer")).toBe(null);
    expect(main.querySelectorAll(".aiw-na-row").length).toBe(0);
  });

  // NX08 --------------------------------------------------------------------
  it("NX08: der Leerbefund nennt seine Grundlage", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitNextActions.renderNextActions(
      main,
      D({ items: [], actionable: 0, total_cases: 12, done_excluded: 12 }),
      {}
    );
    const t = main.querySelector(".aiw-na-leer").textContent;
    expect(t).toContain("12");
    expect(t).toContain("abgeschlossen");
  });

  // NX09 --------------------------------------------------------------------
  it("NX09: 'NICHT zugewiesen' als Klartext", () => {
    const api = _api();
    expect(api.assignedText(I({ assigned: false }))).toBe("NICHT zugewiesen");
    expect(api.assignedText(I({ assigned: true }))).toBe("zugewiesen");

    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitNextActions.renderNextActions(
      main,
      D({ items: [I({ assigned: false })] }),
      {}
    );
    expect(main.querySelector(".aiw-na-assigned").textContent).toBe(
      "NICHT zugewiesen"
    );
  });

  // NX10 --------------------------------------------------------------------
  it("NX10: unbekannte Dringlichkeit faellt auf", () => {
    const api = _api();
    expect(api.urgencyClass("sofort")).toBe("is-unbekannt");
    expect(api.urgencyLabel("sofort")).toContain("unbekannt");
    expect(api.urgencyLabel("sofort")).toContain("sofort");
    expect(api.urgencyClass("dringend")).toBe("is-dringend");
    expect(api.urgencyLabel("routine")).toBe("routine");
    // Auch eine unbekannte Ampel wird nicht stillschweigend eingeordnet.
    expect(api.ampelClass("blau")).toBe("unbekannt");
    expect(api.ampelClass("rot")).toBe("rot");
  });

  // NX11 --------------------------------------------------------------------
  it("NX11: fehlender Zeitstempel ist kein 1970", () => {
    const api = _api();
    expect(api.fmtTs(null)).toBe("—");
    expect(api.fmtTs(undefined)).toBe("—");
    expect(api.fmtTs(1750000000)).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });

  // NX12 --------------------------------------------------------------------
  it("NX12: Markup bleibt Text, UTF-8 erhalten", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    const name = '<img src=x onerror="1">Пётр';
    win.AIWCockpitNextActions.renderNextActions(
      main,
      D({ items: [I({ username: name, reason: "Grund mit <b>Markup</b>" })] }),
      {}
    );
    expect(main.querySelector("img")).toBe(null);
    expect(main.querySelector("b")).toBe(null);
    expect(main.querySelector(".aiw-na-case").textContent).toContain(name);
    expect(main.textContent).toContain("Пётр");
  });
});
