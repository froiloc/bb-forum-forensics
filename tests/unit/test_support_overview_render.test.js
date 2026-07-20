/**
 * tests/unit/test_support_overview_render.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Support-Historie (Frontend)
 *
 * Testsuite fuer management/support_overview/frontend/support_overview.js.
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWSupportOverview) —
 * KEIN dupliziertes Logik-Abbild (vermeidet die 'gruen-aber-tot'-Falle).
 *
 * SR01 -- API nach dem Laden verfuegbar (window.AIWSupportOverview)
 * SR02 -- statusClass(): beendet/orphan/offen/herrenlos + unknown
 * SR03 -- statusLabel(): bekannte Codes gemappt
 * SR04 -- supporterLabel(): display > system > (id N) > 'unbekannt'
 * SR05 -- caseUserLabel(): username sonst '(kein cases-Eintrag)'
 * SR06 -- formatDuration(): h/m/s; null -> Gedankenstrich
 * SR07 -- formatTs(): UTC-Format; null -> Gedankenstrich
 * SR08 -- anchorTs(): started_at > started_ts > ended_at > ended_ts > 0
 * SR09 -- sortRecords(): default anchor asc, nach Feld, desc, Tiebreak, no mutate
 * SR10 -- filterRecords(): Teilstring ueber Felder, leer -> alle, case-insensitiv
 * SR11 -- renderInto(): Reihenfolge, Statusklassen, Anomalie-Zeile, XSS-sicher
 *
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 2026-07-20
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/support_overview/frontend/support_overview.js",
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
  return _makeContext().AIWSupportOverview;
}

// Record-Erzeuger mit sinnvollen Defaults (eine sauber beendete Sitzung).
function R(over) {
  return Object.assign(
    {
      session_id: 1,
      subject_id: 100,
      username: "u",
      supporter_id: 1,
      supporter_system_username: "h001",
      supporter_display_name: "Support Eins",
      started_at: 1000,
      ended_at: 1060,
      duration_sec: 60,
      reason: null,
      status: "beendet",
      started_seq: 3,
      ended_seq: 4,
      started_ts: 1000,
      ended_ts: 1060,
      started_actor_id: 1,
      ended_actor_id: 1,
      anomaly: null,
    },
    over
  );
}

describe("support_overview.js — Support-Historie Render-Schicht", () => {
  it("SR01 API verfuegbar", () => {
    const A = _api();
    expect(typeof A.sortRecords).toBe("function");
    expect(typeof A.filterRecords).toBe("function");
    expect(typeof A.renderInto).toBe("function");
  });

  it("SR02 statusClass mappt", () => {
    const A = _api();
    expect(A.statusClass("beendet")).toBe("aiw-status-beendet");
    expect(A.statusClass("orphan_timeout")).toBe("aiw-status-orphan");
    expect(A.statusClass("offen")).toBe("aiw-status-offen");
    expect(A.statusClass("herrenlos")).toBe("aiw-status-herrenlos");
    expect(A.statusClass("irgendwas")).toBe("aiw-status-unknown");
  });

  it("SR03 statusLabel mappt", () => {
    const A = _api();
    expect(A.statusLabel("beendet")).toBe("beendet");
    expect(A.statusLabel("orphan_timeout")).toBe("Zeitueberschreitung");
    expect(A.statusLabel("herrenlos")).toBe("herrenlos");
  });

  it("SR04 supporterLabel Praezedenz", () => {
    const A = _api();
    expect(A.supporterLabel(R({}))).toBe("Support Eins");
    expect(
      A.supporterLabel(R({ supporter_display_name: null }))
    ).toBe("h001");
    expect(
      A.supporterLabel(
        R({ supporter_display_name: null, supporter_system_username: null, supporter_id: 9 })
      )
    ).toBe("(id 9)");
    expect(
      A.supporterLabel(
        R({ supporter_display_name: null, supporter_system_username: null, supporter_id: null })
      )
    ).toBe("unbekannt");
  });

  it("SR05 caseUserLabel", () => {
    const A = _api();
    expect(A.caseUserLabel(R({ username: "beschuldigter" }))).toBe("beschuldigter");
    expect(A.caseUserLabel(R({ username: null }))).toBe("(kein cases-Eintrag)");
    expect(A.caseUserLabel(R({ username: "" }))).toBe("(kein cases-Eintrag)");
  });

  it("SR06 formatDuration", () => {
    const A = _api();
    expect(A.formatDuration(null)).toBe("\u2014");
    expect(A.formatDuration(0)).toBe("0s");
    expect(A.formatDuration(59)).toBe("59s");
    expect(A.formatDuration(65)).toBe("1m 05s");
    expect(A.formatDuration(3661)).toBe("1h 01m 01s");
  });

  it("SR07 formatTs UTC", () => {
    const A = _api();
    expect(A.formatTs(null)).toBe("\u2014");
    // 1609459200 = 2021-01-01 00:00:00 UTC
    expect(A.formatTs(1609459200)).toBe("2021-01-01 00:00Z");
  });

  it("SR08 anchorTs Praezedenz", () => {
    const A = _api();
    expect(A.anchorTs(R({ started_at: 5, started_ts: 9 }))).toBe(5);
    expect(A.anchorTs(R({ started_at: null, started_ts: 9 }))).toBe(9);
    expect(
      A.anchorTs(R({ started_at: null, started_ts: null, ended_at: 7 }))
    ).toBe(7);
    expect(
      A.anchorTs(
        R({ started_at: null, started_ts: null, ended_at: null, ended_ts: 3 })
      )
    ).toBe(3);
    expect(
      A.anchorTs(
        R({ started_at: null, started_ts: null, ended_at: null, ended_ts: null })
      )
    ).toBe(0);
  });

  it("SR09 sortRecords default/feld/desc/tiebreak/no-mutate", () => {
    const A = _api();
    const input = [
      R({ session_id: 61, started_at: 300 }),
      R({ session_id: 62, started_at: 100 }),
      R({ session_id: 63, started_at: 200 }),
    ];
    const snapshot = input.map((r) => r.session_id);
    const asc = A.sortRecords(input);
    expect(asc.map((r) => r.session_id)).toEqual([62, 63, 61]);
    // Eingabe unveraendert (keine Mutation).
    expect(input.map((r) => r.session_id)).toEqual(snapshot);
    // Absteigend.
    const desc = A.sortRecords(input, "anchor", "desc");
    expect(desc.map((r) => r.session_id)).toEqual([61, 63, 62]);
    // Tiebreak session_id (gleicher Anker).
    const tie = A.sortRecords(
      [R({ session_id: 5, started_at: 100 }), R({ session_id: 2, started_at: 100 })],
      "anchor",
      "asc"
    );
    expect(tie.map((r) => r.session_id)).toEqual([2, 5]);
  });

  it("SR10 filterRecords", () => {
    const A = _api();
    const recs = [
      R({ session_id: 1, username: "alice", supporter_display_name: "Support Eins" }),
      R({ session_id: 2, username: "bob", supporter_display_name: "Support Zwei" }),
    ];
    expect(A.filterRecords(recs, "").length).toBe(2);
    expect(A.filterRecords(recs, "alice").map((r) => r.session_id)).toEqual([1]);
    // Case-insensitiv + Supporter-Feld.
    expect(A.filterRecords(recs, "zwei").map((r) => r.session_id)).toEqual([2]);
    // subject_id als Zahl filterbar.
    expect(
      A.filterRecords([R({ session_id: 9, subject_id: 4242 })], "4242").length
    ).toBe(1);
  });

  it("SR11 renderInto Reihenfolge/Klassen/Anomalie/XSS", () => {
    const win = _makeContext();
    const A = win.AIWSupportOverview;
    const doc = win.document;
    const root = doc.createElement("div");
    doc.body.appendChild(root);

    const recs = [
      R({ session_id: 1, status: "herrenlos", anomaly: "doppeltes_ended" }),
      R({ session_id: 2, status: "beendet" }),
    ];
    const res = A.renderInto(root, recs, {});
    expect(res.rows).toBe(2);

    const bodyRows = root.querySelectorAll("tbody tr");
    expect(bodyRows.length).toBe(2);
    // Reihenfolge bleibt wie uebergeben (renderInto sortiert NICHT selbst).
    expect(bodyRows[0].getAttribute("data-session-id")).toBe("1");
    expect(bodyRows[0].className).toContain("aiw-status-herrenlos");
    expect(bodyRows[0].className).toContain("aiw-has-anomaly");
    expect(bodyRows[1].className).toContain("aiw-status-beendet");

    // XSS-sicher: ein '<img>' aus dem Benutzernamen wird NICHT als Element
    // erzeugt (textContent statt innerHTML).
    const root2 = doc.createElement("div");
    doc.body.appendChild(root2);
    A.renderInto(root2, [R({ username: "<img src=x onerror=alert(1)>" })], {});
    expect(root2.querySelector("img")).toBeNull();
  });
});
