/**
 * tests/unit/test_dashboard_render.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ampel-Dashboard (Frontend)
 *
 * Testsuite fuer management/dashboard/frontend/dashboard.js.
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWDashboard) — KEIN
 * dupliziertes Logik-Abbild (vermeidet die 'gruen-aber-tot'-Falle).
 *
 * DR01 -- API nach dem Laden verfuegbar (window.AIWDashboard)
 * DR02 -- ampelClass(): rot/gelb/gruen + unknown
 * DR03 -- sortForDisplay(): Schwere zuerst (rot < gelb < gruen)
 * DR04 -- sortForDisplay(): Tiebreak Prioritaet, dann last_activity desc, dann user_id
 * DR05 -- sortForDisplay(): mutiert die Eingabe nicht
 * DR06 -- supportLabel(): 'Support aktiv (N)' bzw. leer
 * DR07 -- assigneeLabel(): display_name > system_username > Gedankenstrich
 * DR08 -- daysSince(): Tage seit Zeitstempel (nowSec injizierbar); null bei fehlend
 * DR09 -- reasonLabel(): bekannte Codes gemappt
 * DR10 -- renderInto(): Tabelle in Schwere-Reihenfolge, Ampelklassen, XSS-sicher
 *
 * Version: v0.7.322 · Build: 322 · 2026-07-04
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

// dashboard.js einmalig lesen (Pfad relativ zum Repo-Wurzelverzeichnis).
const _src = readFileSync(
  "management/dashboard/frontend/dashboard.js",
  "utf-8"
);

// Frischer JSDOM-Kontext pro Test (keine Interferenzen zwischen Tests).
function _makeContext() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

function _api() {
  return _makeContext().AIWDashboard;
}

// Kleiner Fall-Erzeuger mit sinnvollen Defaults.
function C(over) {
  return Object.assign(
    {
      user_id: 1,
      username: "u",
      status: "open",
      priority: 3,
      assigned_display_name: null,
      assigned_system_username: null,
      has_note: false,
      event_count: 0,
      last_event_kind: null,
      last_activity_at: 0,
      support_active: false,
      support_count: 0,
      ampel: "gruen",
      ampel_reason: "aktiv",
    },
    over
  );
}

describe("dashboard.js — Ampel-Dashboard Render-Schicht", () => {
  it("DR01 API verfuegbar", () => {
    const D = _api();
    expect(typeof D.sortForDisplay).toBe("function");
    expect(typeof D.renderInto).toBe("function");
  });

  it("DR02 ampelClass mappt korrekt", () => {
    const D = _api();
    expect(D.ampelClass("rot")).toBe("aiw-ampel-rot");
    expect(D.ampelClass("gelb")).toBe("aiw-ampel-gelb");
    expect(D.ampelClass("gruen")).toBe("aiw-ampel-gruen");
    expect(D.ampelClass("irgendwas")).toBe("aiw-ampel-unknown");
  });

  it("DR03 Sortierung: Schwere zuerst", () => {
    const D = _api();
    const out = D.sortForDisplay([
      C({ user_id: 400, ampel: "gruen", priority: 1 }),
      C({ user_id: 300, ampel: "gelb", priority: 1 }),
      C({ user_id: 100, ampel: "rot", priority: 1 }),
    ]);
    expect(out.map((c) => c.ampel)).toEqual(["rot", "gelb", "gruen"]);
  });

  it("DR04 Sortierung: Tiebreaks (Prio, last_activity desc, user_id)", () => {
    const D = _api();
    const out = D.sortForDisplay([
      C({ user_id: 200, ampel: "rot", priority: 2 }),
      C({ user_id: 600, ampel: "rot", priority: 1, last_activity_at: 100 }),
      C({ user_id: 500, ampel: "rot", priority: 1, last_activity_at: 900 }),
      C({ user_id: 101, ampel: "rot", priority: 1, last_activity_at: 900 }),
    ]);
    // prio 1 vor prio 2; bei prio 1: neuere Aktivitaet (900) zuerst;
    // bei gleicher Aktivitaet: kleinere user_id zuerst.
    expect(out.map((c) => c.user_id)).toEqual([101, 500, 600, 200]);
  });

  it("DR05 Sortierung mutiert Eingabe nicht", () => {
    const D = _api();
    const input = [
      C({ user_id: 2, ampel: "gruen" }),
      C({ user_id: 1, ampel: "rot" }),
    ];
    const before = input.map((c) => c.user_id).join(",");
    D.sortForDisplay(input);
    expect(input.map((c) => c.user_id).join(",")).toBe(before);
  });

  it("DR06 supportLabel", () => {
    const D = _api();
    expect(D.supportLabel(C({ support_active: true, support_count: 2 }))).toBe(
      "Support aktiv (2)"
    );
    expect(D.supportLabel(C({ support_active: false }))).toBe("");
  });

  it("DR07 assigneeLabel Vorrang", () => {
    const D = _api();
    expect(
      D.assigneeLabel(C({ assigned_display_name: "N, V", assigned_system_username: "h1" }))
    ).toBe("N, V");
    expect(D.assigneeLabel(C({ assigned_system_username: "h1" }))).toBe("h1");
    expect(D.assigneeLabel(C({}))).toBe("\u2014");
  });

  it("DR08 daysSince", () => {
    const D = _api();
    const now = 1000000;
    expect(D.daysSince(now - 3 * 86400, now)).toBe(3);
    expect(D.daysSince(0, now)).toBe(null);
  });

  it("DR09 reasonLabel", () => {
    const D = _api();
    expect(D.reasonLabel("inaktiv_lang")).toBe("lange inaktiv");
    expect(D.reasonLabel("offen_nicht_zugewiesen")).toBe("offen, nicht zugewiesen");
  });

  it("DR10 renderInto: Reihenfolge, Klassen, XSS-sicher", () => {
    const win = _makeContext();
    const D = win.AIWDashboard;
    const container = win.document.createElement("div");
    win.document.body.appendChild(container);

    const evil = '<img src=x onerror="window.__pwned=1">';
    const res = D.renderInto(
      container,
      [
        C({ user_id: 400, ampel: "gruen", priority: 1 }),
        C({ user_id: 100, ampel: "rot", priority: 1, username: evil }),
        C({ user_id: 300, ampel: "gelb", priority: 1 }),
      ],
      { nowSec: 1000000 }
    );

    const rows = container.querySelectorAll("tbody tr");
    expect(res.rows).toBe(3);
    expect(rows.length).toBe(3);
    // Schwere-Reihenfolge: rot(100), gelb(300), gruen(400)
    expect(rows[0].getAttribute("data-user-id")).toBe("100");
    expect(rows[2].getAttribute("data-user-id")).toBe("400");
    // Ampelklasse an der Zeile
    expect(rows[0].className).toContain("aiw-ampel-rot");
    // XSS-Sicherheit: Benutzername als Text, NICHT als HTML interpretiert.
    const uname = rows[0].querySelector(".aiw-username");
    expect(uname.textContent).toBe(evil);
    expect(uname.querySelector("img")).toBe(null);
    expect(win.__pwned).toBeUndefined();
  });
});
