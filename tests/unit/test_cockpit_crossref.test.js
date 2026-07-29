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

// Build 555: das gemeinsame Tabellen-Werkzeug MUSS im Kontext liegen — genau
// wie im Browser (cockpit.html laedt es vor den Sichten). Ohne es faellt die
// Sicht in ihren Ersatzpfad, und der Test wuerde die Tabelle gar nicht mehr
// beruehren ('gruen aber tot').
const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

/** Tabulator-Attrappe: haelt die Daten, ruft die Spalten-Formatter auf und
 *  haengt die erzeugten Knoten in den Container, damit die Bedienelemente im
 *  DOM anklickbar sind. Ohne den Formatter-Aufruf wuerde der Revidieren-Weg
 *  gar nicht beruehrt. */
function _fakeTabulator(doc) {
  return function (host, options) {
    const self = this;
    this.options = options;
    this.data = options.data || [];
    this._filters = [];
    this.data.forEach(function (d) {
      const tr = doc.createElement("div");
      tr.className = "fake-row";
      tr.setAttribute("data-subject", String(d.subject_id));
      (options.columns || []).forEach(function (col) {
        // Spalten OHNE Formatter gibt Tabulator als Text aus — die Attrappe
        // muss das nachbilden, sonst fehlten genau die Textspalten im
        // geprueften DOM (und der XSS-Test liefe ins Leere).
        if (typeof col.formatter !== "function") {
          const sp = doc.createElement("span");
          sp.textContent = String(
            d[col.field] === undefined || d[col.field] === null
              ? "" : d[col.field]
          );
          tr.appendChild(sp);
          return;
        }
        const node = col.formatter({
          getData: function () { return d; },
          getValue: function () { return d[col.field]; },
        });
        if (node && node.nodeType) { tr.appendChild(node); }
      });
      host.appendChild(tr);
    });
    this.getDataCount = function () { return self.data.length; };
    this.setHeaderFilterValue = function (f, v) { self._filters.push([f, v]); };
    this.clearHeaderFilter = function () { self._filters = []; };
    this.clearFilter = function () { self._filters = []; };
    this.getHeaderFilters = function () { return self._filters; };
    this.getSorters = function () { return []; };
    this.getColumns = function () { return []; };
    this.on = function () {};
    this.destroy = function () {};
  };
}

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_tkSrc);
  dom.window.eval(_src);
  return dom.window;
}

/** renderCrossref mit eingespritzter Attrappe. */
function _render(win, main, data, opts) {
  return win.AIWCockpitCrossref.renderCrossref(
    main, data,
    Object.assign({ doc: win.document, Tabulator: _fakeTabulator(win.document) },
                  opts || {})
  );
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
  it("CX05: Katalog rendert Zeilen, Badge-Klasse, Zellinhalte", () => {
    const win = _win();
    const el = _mount(win);
    _render(win, el, _entries(), { canEdit: false });

    // Build 555: die Zeilen entstehen jetzt in Tabulator, nicht in einer
    // handgebauten <table>. Geprueft wird dieselbe Zusicherung an der neuen
    // Struktur.
    const rows = el.querySelectorAll(".fake-row");
    expect(rows.length).toBe(2);
    // Erste Zeile = gesichert. Die REIHENFOLGE DES SERVERS bleibt erhalten
    // (staerkste Konfidenz zuerst) — die Tabelle setzt bewusst kein
    // initialSort.
    const badge = rows[0].querySelector(".aiw-conf-badge");
    expect(badge.className).toContain("aiw-conf-gesichert");
    expect(rows[0].getAttribute("data-subject")).toBe("993008244");
    expect(rows[0].textContent).toContain("Max Mustermann");
    // Ohne Recht keine Revidieren-Knoepfe.
    expect(el.querySelector(".aiw-xref-revise")).toBeNull();
  });

  // CX05b -------------------------------------------------------------------
  it("CX05b: mit Recht ein Revidieren-Knopf je Zeile, der das Formular fuellt", () => {
    const win = _win();
    const doc = win.document;
    const el = _mount(win);
    _render(win, el, _entries(), { canEdit: true });

    const knoepfe = el.querySelectorAll(".aiw-xref-revise");
    expect(knoepfe.length).toBe(2);
    knoepfe[0].dispatchEvent(new win.Event("click"));
    // Der Knopf uebertraegt die Zeile ins Formular (Revision vorbereiten).
    expect(doc.getElementById("aiw-xref-sid").value).toBe("993008244");
    expect(doc.getElementById("aiw-xref-real").value).toBe("Max Mustermann");
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
    const el = _mount(win);
    const evil = '<img src=x onerror=alert(1)>';
    _render(win, el, {
      entries: [{ subject_id: 9, real_identity: evil,
        confidence_code: "verdacht", confidence_ordinal: 10, basis: "",
        note: null, updated_at: 1700000000 }],
    }, { canEdit: false });

    // Der boesartige String erscheint als TEXT, nicht als <img>-Element.
    expect(el.querySelector("img")).toBeNull();
    expect(el.textContent).toContain(evil);
  });

  // ==========================================================================
  // Build 555 — Tabulator + gemeinsames Tabellen-Werkzeug
  // ==========================================================================

  // CX08 ---------------------------------------------------------------------
  it("CX08: toRows — abgeleitete Felder, Reihenfolge des Servers bleibt", () => {
    const api = _api();
    const rows = api.toRows(_entries());
    expect(rows.length).toBe(2);

    // DIE REIHENFOLGE IST EINE AUSSAGE: der Server liefert die staerkste
    // Konfidenz zuerst. toRows sortiert NICHT um.
    expect(rows.map((r) => r.subject_id)).toEqual([993008244, 5]);

    expect(rows[0].konfidenz).toBe("gesichert");
    expect(rows[0].konfidenz_rang).toBe(30);
    expect(rows[1].konfidenz).toBe("Verdacht");
    expect(rows[1].konfidenz_rang).toBe(10);

    // Leere Freitexte werden zum Gedankenstrich: eine leere Zelle sieht aus
    // wie ein Anzeigefehler, '—' sagt 'nichts hinterlegt'.
    expect(rows[1].basis).toBe("—");
    expect(rows[0].basis).toBe("Zahlung");

    // Der Rohzeitpunkt bleibt neben dem formatierten stehen (Sortierung).
    expect(rows[0].updated_at).toBe(1700000500);
    expect(typeof rows[0].geaendert).toBe("string");

    // Ein UNBEKANNTER Code verschwindet nicht, er bekommt Rang 0 und
    // sortiert zuletzt (Grundregel 1).
    const fremd = api.toRows({
      entries: [{ subject_id: 1, confidence_code: "quatsch", updated_at: 1 }],
    });
    expect(fremd[0].konfidenz).toBe("quatsch");
    expect(fremd[0].konfidenz_rang).toBe(0);
  });

  // CX09 ---------------------------------------------------------------------
  it("CX09: die Konfidenz sortiert nach BEWEISSTAERKE, nicht alphabetisch", () => {
    const win = _win();
    const api = win.AIWCockpitCrossref;
    const cols = api.spalten(win.document, false);
    const konf = cols.find((c) => c.field === "konfidenz");
    expect(typeof konf.sorter).toBe("function");

    const zeile = (code) => ({
      getData: () => ({ konfidenz_rang: api.confidenceRang(code) }),
    });

    // ALPHABETISCH stuende 'gesichert' vor 'Verdacht' vor 'wahrscheinlich'.
    // Eine Spalte, die nach Beweisstaerke aussieht und alphabetisch sortiert,
    // waere in einem Beweismittelwerkzeug irrefuehrend.
    expect(konf.sorter(null, null, zeile("verdacht"),
                       zeile("gesichert"))).toBeLessThan(0);
    expect(konf.sorter(null, null, zeile("gesichert"),
                       zeile("wahrscheinlich"))).toBeGreaterThan(0);
    expect(konf.sorter(null, null, zeile("wahrscheinlich"),
                       zeile("wahrscheinlich"))).toBe(0);
    // Unbekannt sortiert unter allem Bekannten.
    expect(konf.sorter(null, null, zeile("quatsch"),
                       zeile("verdacht"))).toBeLessThan(0);
  });

  // CX10 ---------------------------------------------------------------------
  it("CX10: 'geaendert' sortiert ueber den Rohwert, nicht ueber den Text", () => {
    const win = _win();
    const api = win.AIWCockpitCrossref;
    const cols = api.spalten(win.document, false);
    const sp = cols.find((c) => c.field === "geaendert");
    expect(typeof sp.sorter).toBe("function");

    // Eine Textsortierung ueber '01.12.2025' vs. '02.01.2026' waere falsch
    // herum. Geprueft wird deshalb der Rohwert.
    const a = { getData: () => ({ updated_at: 1700000000 }) };
    const b = { getData: () => ({ updated_at: 1800000000 }) };
    expect(sp.sorter(null, null, a, b)).toBeLessThan(0);
    expect(sp.sorter(null, null, b, a)).toBeGreaterThan(0);
    // Fehlender Zeitpunkt -> 0, also ganz unten statt NaN.
    const leer = { getData: () => ({}) };
    expect(sp.sorter(null, null, leer, a)).toBeLessThan(0);
  });

  // CX11 ---------------------------------------------------------------------
  it("CX11: die Aktionsspalte traegt keinen Filter", () => {
    const win = _win();
    const api = win.AIWCockpitCrossref;
    const cols = api.spalten(win.document, true);
    const akt = cols.find((c) => c.field === "aktion");
    expect(akt.kein_filter).toBe(true);
    // Und das gemeinsame Werkzeug haelt sich daran.
    const mitFilter = win.AIWTableKit.spaltenMitFilter(
      api.toRows(_entries()), cols
    );
    const aktMF = mitFilter.find((c) => c.field === "aktion");
    expect(aktMF.headerFilter).toBeUndefined();
    // Alle uebrigen Spalten haben einen.
    mitFilter.filter((c) => c.field && c.field !== "aktion")
      .forEach((c) => { expect(c.headerFilter, c.field).toBeTruthy(); });
  });
});
