/**
 * tests/unit/test_cockpit_crossref.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Kreuzbezug (AP-2A)
 *
 * Testsuite fuer management/server/static/cockpit_crossref.js (Build 471).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitCrossref) —
 * keine Logik-Duplikation (B4-S12: „gruen, aber tot" vermeiden).
 *
 * CX01 — API verfuegbar.
 * CX02 — reine Helfer: confidenceLabel/confidenceClass, entries(), fmtTs().
 * CX03 — buildPayload: subject_id-Parsing, Trim, leere Notiz weggelassen.
 * CX04 — leerer Katalog -> Platzhalter, keine Tabelle; Formular nur mit canEdit.
 * CX05 — mit Eintraegen: Tabelle, Konfidenz-Badge-Klasse, Zellinhalte.
 * CX06 — Speichern: ungueltige subject_id -> kein onSet; gueltig -> onSet(body).
 * CX07 — Freitext (reale Person) XSS-sicher (textContent, kein Markup).
 *
 * Version: v0.8.471 · Build: 471 · 2026-07-20
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_crossref.js",
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
  return _win().AIWCockpitCrossref;
}
function _mount(win) {
  const el = win.document.createElement("div");
  win.document.body.appendChild(el);
  return el;
}
function _entries() {
  return {
    entries: [
      { id: 2, subject_id: 993008244, real_identity: "Max Mustermann",
        confidence_code: "gesichert", confidence_ordinal: 30, basis: "Zahlung",
        note: null, created_by: 1, updated_by: 1,
        created_at: 1700000000, updated_at: 1700000500,
        audit_seq: 12, created_audit_seq: 12 },
      { id: 1, subject_id: 5, real_identity: "Unbekannt A",
        confidence_code: "verdacht", confidence_ordinal: 10, basis: "",
        note: "nur ein Indiz", created_by: 1, updated_by: 1,
        created_at: 1700000000, updated_at: 1700000100,
        audit_seq: 8, created_audit_seq: 8 },
    ],
  };
}

describe("cockpit_crossref", () => {
  // CX01 --------------------------------------------------------------------
  it("CX01: API-Oberflaeche vorhanden", () => {
    const api = _api();
    expect(api).toBeTruthy();
    ["confidenceLabel", "confidenceClass", "entries", "fmtTs",
     "buildPayload", "renderCrossref"].forEach((fn) => {
      expect(typeof api[fn]).toBe("function");
    });
    expect(api.CONFIDENCE).toEqual(["verdacht", "wahrscheinlich", "gesichert"]);
  });

  // CX02 --------------------------------------------------------------------
  it("CX02: reine Helfer bilden korrekt ab", () => {
    const api = _api();
    expect(api.confidenceLabel("gesichert")).toBe("gesichert");
    expect(api.confidenceLabel("verdacht")).toBe("Verdacht");
    expect(api.confidenceLabel("xyz")).toBe("xyz");
    expect(api.confidenceClass("gesichert")).toBe("aiw-conf-gesichert");
    expect(api.confidenceClass("wahrscheinlich")).toBe("aiw-conf-wahrscheinlich");
    expect(api.confidenceClass("verdacht")).toBe("aiw-conf-verdacht");
    expect(api.confidenceClass("xyz")).toBe("aiw-conf-unbekannt");
    expect(api.entries(null)).toEqual([]);
    expect(api.entries({ entries: [{ subject_id: 1 }] }).length).toBe(1);
    expect(api.fmtTs(0)).toBe("—");
    expect(api.fmtTs(null)).toBe("—");
    expect(typeof api.fmtTs(1700000000)).toBe("string");
    expect(api.fmtTs(1700000000)).not.toBe("—");
  });

  // CX03 --------------------------------------------------------------------
  it("CX03: buildPayload parst/trimmt und laesst leere Notiz weg", () => {
    const api = _api();
    const ok = api.buildPayload({
      subject_id: "42", real_identity: "  Max  ",
      confidence_code: "wahrscheinlich", basis: " x ", note: "  "
    });
    expect(ok.subject_id).toBe(42);
    expect(ok.real_identity).toBe("Max");
    expect(ok.confidence_code).toBe("wahrscheinlich");
    expect(ok.basis).toBe("x");
    expect("note" in ok).toBe(false); // leere Notiz weggelassen

    const withNote = api.buildPayload({
      subject_id: "7", real_identity: "A", confidence_code: "verdacht",
      note: " Hinweis "
    });
    expect(withNote.note).toBe("Hinweis");

    // Ungueltige subject_id -> null (der Handler faengt das ab).
    expect(api.buildPayload({ subject_id: "12x", real_identity: "A" })
      .subject_id).toBe(null);
    expect(api.buildPayload({ subject_id: "", real_identity: "A" })
      .subject_id).toBe(null);
  });

  // CX04 --------------------------------------------------------------------
  it("CX04: leerer Katalog -> Platzhalter; Formular nur mit canEdit", () => {
    const win = _win();
    const api = win.AIWCockpitCrossref;
    const doc = win.document;

    const el1 = _mount(win);
    api.renderCrossref(el1, { entries: [] }, { doc, canEdit: true });
    expect(el1.querySelector(".aiw-xref-table")).toBeNull();
    expect(el1.querySelector(".aiw-placeholder")).toBeTruthy();
    expect(el1.querySelector(".aiw-xref-form")).toBeTruthy(); // Recht -> Formular

    const el2 = _mount(win);
    api.renderCrossref(el2, { entries: [] }, { doc, canEdit: false });
    expect(el2.querySelector(".aiw-xref-form")).toBeNull(); // kein Recht
    expect(el2.querySelector(".aiw-xref-readonly")).toBeTruthy();
  });

  // CX05 --------------------------------------------------------------------
  it("CX05: Katalog rendert Tabelle, Badge-Klasse, Zellinhalte", () => {
    const win = _win();
    const api = win.AIWCockpitCrossref;
    const el = _mount(win);
    api.renderCrossref(el, _entries(), { doc: win.document, canEdit: false });

    const rows = el.querySelectorAll(".aiw-xref-table tbody tr");
    expect(rows.length).toBe(2);
    // Erste Zeile = gesichert (staerkste zuerst kommt aus dem Server; hier
    // pruefen wir nur die Badge-Klasse anhand des Codes).
    const badge = rows[0].querySelector(".aiw-conf-badge");
    expect(badge.className).toContain("aiw-conf-gesichert");
    expect(rows[0].getAttribute("data-subject")).toBe("993008244");
    expect(rows[0].textContent).toContain("Max Mustermann");
    // Ohne Recht keine Revidieren-Buttons.
    expect(el.querySelector(".aiw-xref-revise")).toBeNull();
  });

  // CX06 --------------------------------------------------------------------
  it("CX06: Speichern — ungueltige subject_id kein onSet; gueltig -> onSet", () => {
    const win = _win();
    const api = win.AIWCockpitCrossref;
    const doc = win.document;
    const el = _mount(win);

    let called = null;
    api.renderCrossref(el, { entries: [] }, {
      doc, canEdit: true,
      onSet: (body) => { called = body; },
    });

    const sid = doc.getElementById("aiw-xref-sid");
    const real = doc.getElementById("aiw-xref-real");
    const conf = doc.getElementById("aiw-xref-conf");
    const save = doc.getElementById("aiw-xref-save");

    // Ungueltige subject_id -> onSet NICHT gerufen, Fehlermeldung sichtbar.
    sid.value = "abc";
    real.value = "Max";
    conf.value = "verdacht";
    save.click();
    expect(called).toBeNull();
    expect(doc.getElementById("aiw-xref-result").classList.contains("error"))
      .toBe(true);

    // Gueltig -> onSet mit korrektem Body.
    sid.value = "993008244";
    real.value = "Max Mustermann";
    conf.value = "gesichert";
    save.click();
    expect(called).toEqual({
      subject_id: 993008244, real_identity: "Max Mustermann",
      confidence_code: "gesichert", basis: "",
    });
  });

  // CX07 --------------------------------------------------------------------
  it("CX07: reale Person XSS-sicher (textContent, kein Markup)", () => {
    const win = _win();
    const api = win.AIWCockpitCrossref;
    const el = _mount(win);
    const evil = '<img src=x onerror=alert(1)>';
    api.renderCrossref(el, {
      entries: [{ subject_id: 9, real_identity: evil,
        confidence_code: "verdacht", confidence_ordinal: 10, basis: "",
        note: null, updated_at: 1700000000 }],
    }, { doc: win.document, canEdit: false });

    // Der boesartige String erscheint als TEXT, nicht als <img>-Element.
    expect(el.querySelector("img")).toBeNull();
    expect(el.textContent).toContain(evil);
  });
});
