/**
 * tests/unit/test_cockpit_releases.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Externe Fallfreigabe
 *
 * Testsuite fuer management/server/static/cockpit_releases.js (Build 463).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitReleases).
 *
 * RL01 — API verfuegbar.
 * RL02 — Helfer: countsModel (fehlende -> 0), statusDotClass, allowedRevoke.
 * RL03 — renderReleases: Kopf, Kennzahlen, Freigaben-Tabelle; mit Recht
 *        Freigabe-Formular, ohne Recht Nur-Lesend-Hinweis (kein Formular).
 * RL04 — Grant-Formular: ungueltige user_id / leere Grundlage -> kein onGrant +
 *        Fehlermeldung; gueltig -> onGrant mit korrektem Body.
 * RL05 — leere Empfaenger-Allowlist -> Hinweis statt Formular (Default-Deny).
 * RL06 — Widerruf: nur an aktiver Freigabe; Panel; leerer Grund -> kein
 *        onRevoke + Fehler; mit Grund -> onRevoke({release_id, grund}).
 * RL07 — widerrufene Freigabe: kein Widerruf-Button; Freitext XSS-sicher.
 *
 * Version: v0.7.463 · Build: 463 · 2026-07-20
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_releases.js",
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
  return _win().AIWCockpitReleases;
}

function _data() {
  return {
    count: 2,
    counts: { freigegeben: 1, widerrufen: 1 },
    umfang_catalog: [
      { code: "bericht", label: "Ermittlungsbericht (gesiegelt)" },
      { code: "akte", label: "vollstaendige Ermittlungsakte" },
    ],
    recipients: [{ kennung: "h0b1234", display_name: "KHK Muster" }],
    ad_group: "SEC-Extern",
    releases: [
      { id: 1, user_id: 18, fall_username: "boarder18",
        recipient_kennung: "h0b1234", recipient_display: "KHK Muster",
        umfang: "bericht", umfang_label: "Ermittlungsbericht (gesiegelt)",
        status: "freigegeben", status_label: "freigegeben" },
      { id: 2, user_id: 19, fall_username: "boarder19",
        recipient_kennung: "h0c9999", recipient_display: "KOKin Beispiel",
        umfang: "akte", umfang_label: "vollstaendige Ermittlungsakte",
        status: "widerrufen", status_label: "widerrufen" },
    ],
  };
}

describe("cockpit_releases.js — Externe Fallfreigabe (Build 463)", () => {
  // RL01 -------------------------------------------------------------------
  it("RL01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.renderReleases).toBe("function");
    expect(typeof api.allowedRevoke).toBe("function");
    expect(typeof api.countsModel).toBe("function");
  });

  // RL02 -------------------------------------------------------------------
  it("RL02: Helfer", () => {
    const api = _api();
    const m = api.countsModel({ counts: { freigegeben: 3 } });
    expect(m.map((c) => c.status)).toEqual(["freigegeben", "widerrufen"]);
    expect(m[0].count).toBe(3);
    expect(m[1].count).toBe(0);
    expect(api.statusDotClass("freigegeben")).toBe("gruen");
    expect(api.statusDotClass("widerrufen")).toBe("grau");
    expect(api.allowedRevoke("freigegeben")).toBe(true);
    expect(api.allowedRevoke("widerrufen")).toBe(false);
  });

  // RL03 -------------------------------------------------------------------
  it("RL03: renderReleases mit/ohne Recht", () => {
    const win = _win();
    const api = win.AIWCockpitReleases;
    const doc = win.document;

    const main = doc.createElement("main");
    api.renderReleases(main, _data(), { canEdit: true, doc: doc });
    expect(main.querySelector(".aiw-pagehead").textContent).toContain(
      "Externe Fallfreigabe"
    );
    expect(main.querySelectorAll(".aiw-rel-table tbody tr").length).toBe(2);
    expect(main.querySelector(".aiw-rel-grant")).toBeTruthy();
    expect(main.querySelector("#aiw-rel-grant-submit")).toBeTruthy();

    const main2 = doc.createElement("main");
    api.renderReleases(main2, _data(), { canEdit: false, doc: doc });
    expect(main2.querySelector(".aiw-rel-readonly")).toBeTruthy();
    expect(main2.querySelector("#aiw-rel-grant-submit")).toBe(null);
  });

  // RL04 -------------------------------------------------------------------
  it("RL04: Grant-Formular validiert", () => {
    const win = _win();
    const api = win.AIWCockpitReleases;
    const doc = win.document;
    const main = doc.createElement("main");
    const calls = [];
    api.renderReleases(main, _data(), {
      canEdit: true, doc: doc, onGrant: (b) => calls.push(b),
    });

    // ungueltige user_id
    main.querySelector("#aiw-rel-grant-user").value = "abc";
    main.querySelector("#aiw-rel-grant-grundlage").value = "ok";
    main.querySelector("#aiw-rel-grant-submit").click();
    expect(calls.length).toBe(0);
    expect(main.querySelector("#aiw-rel-result").className).toContain("error");

    // gueltige user_id, aber leere Grundlage
    main.querySelector("#aiw-rel-grant-user").value = "18";
    main.querySelector("#aiw-rel-grant-grundlage").value = "   ";
    main.querySelector("#aiw-rel-grant-submit").click();
    expect(calls.length).toBe(0);

    // gueltig
    main.querySelector("#aiw-rel-grant-user").value = "18";
    main.querySelector("#aiw-rel-grant-grundlage").value = "StA-Freigabe 12/26";
    main.querySelector("#aiw-rel-grant-submit").click();
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({
      user_id: 18, recipient_kennung: "h0b1234", umfang: "bericht",
      unbedenklichkeit_grundlage: "StA-Freigabe 12/26",
    });
  });

  // RL05 -------------------------------------------------------------------
  it("RL05: leere Empfaenger-Allowlist -> Hinweis, kein Formular", () => {
    const win = _win();
    const api = win.AIWCockpitReleases;
    const doc = win.document;
    const main = doc.createElement("main");
    const data = _data();
    data.recipients = [];
    api.renderReleases(main, data, { canEdit: true, doc: doc });
    expect(main.querySelector("#aiw-rel-grant-submit")).toBe(null);
    expect(main.querySelector(".aiw-rel-warn").textContent).toContain(
      "Default-Deny"
    );
  });

  // RL06 -------------------------------------------------------------------
  it("RL06: Widerruf mit Grund-Pflicht", () => {
    const win = _win();
    const api = win.AIWCockpitReleases;
    const doc = win.document;
    const main = doc.createElement("main");
    const calls = [];
    api.renderReleases(main, _data(), {
      canEdit: true, doc: doc, onRevoke: (b) => calls.push(b),
    });

    // aktive Freigabe (id=1) hat einen Widerruf-Button.
    main.querySelector('button[data-id="1"][data-act="revoke"]').click();
    // ohne Grund -> kein onRevoke + Fehler
    main.querySelector("#aiw-rel-revoke-confirm").click();
    expect(calls.length).toBe(0);
    expect(main.querySelector("#aiw-rel-result").className).toContain("error");

    // erneut oeffnen, Grund setzen
    main.querySelector('button[data-id="1"][data-act="revoke"]').click();
    main.querySelector("#aiw-rel-revoke-grund").value = "Zustaendigkeit weg";
    main.querySelector("#aiw-rel-revoke-confirm").click();
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({ release_id: 1, grund: "Zustaendigkeit weg" });
  });

  // RL07 -------------------------------------------------------------------
  it("RL07: widerrufene Freigabe hat keinen Button; XSS-sicher", () => {
    const win = _win();
    const api = win.AIWCockpitReleases;
    const doc = win.document;
    const main = doc.createElement("main");
    api.renderReleases(main, _data(), { canEdit: true, doc: doc });
    // id=2 ist widerrufen -> kein Widerruf-Button.
    expect(main.querySelector('button[data-id="2"][data-act="revoke"]')).toBe(
      null
    );

    const xss = doc.createElement("main");
    api.renderReleases(xss, {
      count: 1, counts: {}, recipients: [], umfang_catalog: [],
      releases: [{ id: 3, user_id: 5, recipient_kennung: "h0b",
        recipient_display: "<img src=x onerror=alert(1)>",
        umfang: "bericht", umfang_label: "b", status: "freigegeben",
        status_label: "freigegeben" }],
    }, { canEdit: false, doc: doc });
    expect(xss.querySelector("img")).toBe(null);
    expect(xss.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
