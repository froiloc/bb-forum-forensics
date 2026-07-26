/**
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 * tests/unit/test_cockpit_support.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Support-Historie
 *
 * Testsuite fuer management/server/static/cockpit_support.js (Build 367).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitSupport).
 *
 * SP01 — API verfuegbar.
 * SP02 — bucketize: nicht-ueberlappende Aufteilung (mine Vorrang).
 * SP03 — markLabel + supporterLabel.
 * SP04 — detailPairs + buildDetailNode: volle Feldliste als dl.
 * SP05 — createModalRoot/showDetail/hideDetail: Anzeige-Umschaltung.
 * SP06 — renderSupport: nur nicht-leere Abschnitte + Modal + Tabellen.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_support.js",
  "utf-8"
);

// Build 550: das gemeinsame Tabellen-Werkzeug MUSS im Kontext liegen — genau
// wie im Browser (cockpit.html laedt cockpit_tablekit.js vor den Sichten).
// Ohne es faellt die Sicht in ihren Ersatzpfad und der Test wuerde die
// Tabelle gar nicht mehr beruehren ('gruen aber tot').
const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_tkSrc);
  dom.window.eval(_src);
  return dom.window;
}
function _api() { return _ctx().AIWCockpitSupport; }

function S(over) {
  return Object.assign({
    session_id: 1, subject_id: 18, username: "b18",
    supporter_id: 2, supporter_system_username: "h002",
    supporter_display_name: "Mueller",
    started_at: 1000, ended_at: 1600, duration_sec: 600,
    reason: null, status: "beendet",
    started_seq: 40, ended_seq: 41, started_ts: 1000, ended_ts: 1600,
    started_actor_id: 2, ended_actor_id: 2, anomaly: null,
    mine_as_supporter: false, on_my_case: false,
  }, over);
}

function _data() {
  return {
    scope: "eigene", count: 3,
    sessions: [
      S({ session_id: 1, subject_id: 18, supporter_id: 2,
          mine_as_supporter: true, on_my_case: true }),   // mine
      S({ session_id: 2, subject_id: 18, supporter_id: 3,
          supporter_display_name: "Gamma",
          mine_as_supporter: false, on_my_case: true }),  // oncase
      S({ session_id: 3, subject_id: 19, supporter_id: 2,
          mine_as_supporter: true, on_my_case: false }),  // mine
    ],
  };
}

describe("cockpit_support.js — Support-Historie (Build 367)", () => {
  it("SP01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.bucketize).toBe("function");
    expect(typeof api.renderSupport).toBe("function");
    expect(typeof api.showDetail).toBe("function");
  });

  it("SP02: bucketize nicht-ueberlappend", () => {
    const api = _api();
    const b = api.bucketize(_data());
    expect(b.mine.map((s) => s.session_id)).toEqual([1, 3]); // mine Vorrang
    expect(b.oncase.map((s) => s.session_id)).toEqual([2]);
    expect(b.weitere.length).toBe(0);
  });

  it("SP03: markLabel + supporterLabel", () => {
    const api = _api();
    expect(api.markLabel({ mine_as_supporter: true, on_my_case: true }))
      .toContain("meine Sitzung");
    expect(api.markLabel({ mine_as_supporter: false, on_my_case: true }))
      .toBe("an meinem Fall");
    expect(api.supporterLabel(S({}))).toBe("Mueller");
    expect(api.supporterLabel(S({ supporter_display_name: null,
      supporter_system_username: null, supporter_id: null }))).toBe("herrenlos");
  });

  it("SP04: detailPairs + buildDetailNode", () => {
    const win = _ctx();
    const api = win.AIWCockpitSupport;
    const pairs = api.detailPairs(S({}));
    // Enthaelt Status, Anomalie und Beleg-seq (volle Serialisierung).
    const labels = pairs.map((p) => p[0]);
    expect(labels).toContain("Status");
    expect(labels).toContain("Anomalie");
    expect(labels).toContain("Beleg Start (seq)");
    const dl = api.buildDetailNode(win.document, S({}));
    expect(dl.querySelectorAll("dt").length).toBe(pairs.length);
    expect(dl.querySelectorAll("dd").length).toBe(pairs.length);
  });

  it("SP05: Modal zeigen/verbergen", () => {
    const win = _ctx();
    const api = win.AIWCockpitSupport;
    const root = api.createModalRoot(win.document);
    expect(root.style.display).toBe("none");
    api.showDetail(root, win.document, S({}));
    expect(root.style.display).toBe("flex");
    expect(root.querySelector(".aiw-modal-body dl")).toBeTruthy();
    api.hideDetail(root);
    expect(root.style.display).toBe("none");
  });

  it("SP06: renderSupport — nur nicht-leere Abschnitte + Modal", () => {
    const win = _ctx();
    const api = win.AIWCockpitSupport;
    const main = win.document.createElement("main");
    const made = [];
    function StubTab(container, opts) { this.opts = opts; made.push(this); }
    StubTab.prototype.destroy = function () {};

    const tables = api.renderSupport(main, _data(), { Tabulator: StubTab });
    // scope eigene: mine (2) + oncase (1) -> zwei Abschnitte, keine "weitere".
    expect(tables.length).toBe(2);
    const heads = Array.from(main.querySelectorAll(".aiw-subhead"))
      .map((h) => h.textContent);
    expect(heads.some((t) => t.startsWith("Meine Sitzungen"))).toBe(true);
    expect(heads.some((t) => t.startsWith("An meinen Faellen"))).toBe(true);
    expect(heads.some((t) => t.startsWith("Weitere"))).toBe(false);
    // Modal vorhanden (versteckt).
    expect(main.querySelector(".aiw-modal")).toBeTruthy();
    // decorate hat Anzeige-Hilfsfelder ergaenzt, Record bleibt vollstaendig.
    expect(made[0].opts.data[0]._supporter).toBeTruthy();
    expect(made[0].opts.data[0].status).toBe("beendet");
  });
});
