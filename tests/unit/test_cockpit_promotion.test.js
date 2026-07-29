/**
 * tests/unit/test_cockpit_promotion.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Fremdforum-Promotion
 *
 * Testsuite fuer management/server/static/cockpit_promotion.js (Build 461).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitPromotion).
 *
 * PP01 — API verfuegbar.
 * PP02 — allowedActions: offen -> 4 Ziele; gesichtet -> 3 (kein Selbst-Ueber-
 *        gang); zurueckgestellt enthaelt 'gesichtet' (Wiederaufgriff); End-
 *        zustaende -> [].
 * PP03 — reasonRequired/isFinal korrekt.
 * PP04 — countsModel: geordnet, fehlende Schluessel -> 0.
 * PP05 — statusDotClass: uebernommen=gruen, fremdzustaendig=rot, sonst gelb.
 * PP06 — renderPromotion: Kopf, Kennzahlen, Kandidatenzeilen; mit Recht
 *        Aktions-Buttons, ohne Recht Nur-Lesend-Hinweis und KEINE Buttons.
 * PP07 — Panel: grund-pflichtiges Ziel ohne Grund -> onDecide NICHT gerufen +
 *        Fehlermeldung; mit Grund -> onDecide mit korrektem Body.
 * PP08 — Panel: nicht-grund-pflichtiges Ziel (uebernommen) ohne Grund ->
 *        onDecide gerufen; Endzustand zeigt Warnung.
 * PP09 — leere Kandidatenliste -> Platzhalter; grund/herkunft via textContent
 *        (XSS-sicher).
 *
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 2026-07-20
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_promotion.js",
  "utf-8"
);

// Build 557: das gemeinsame Tabellen-Werkzeug MUSS im Kontext liegen — genau
// wie im Browser (cockpit.html laedt es vor den Sichten). Ohne es faellt die
// Sicht in ihren Ersatzpfad, und der Test wuerde die Tabelle gar nicht mehr
// beruehren ('gruen aber tot').
const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

/** Tabulator-Attrappe: haelt die Daten und ruft die Spalten-Formatter auf,
 *  damit die Aktions-Knoepfe im DOM anklickbar sind. Spalten OHNE Formatter
 *  gibt sie als Text aus — sonst fehlten genau die Textspalten im geprueften
 *  DOM (Lehre aus Build 555). */
function _fakeTabulator(doc) {
  return function (host, options) {
    const self = this;
    this.options = options;
    this.data = options.data || [];
    this._filters = [];
    this.data.forEach(function (d) {
      const tr = doc.createElement("div");
      tr.className = "fake-row";
      tr.setAttribute("data-uid", String(d.subject_id));
      (options.columns || []).forEach(function (col) {
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

/** renderPromotion mit eingespritzter Attrappe. */
function _render(win, main, data, opts) {
  return win.AIWCockpitPromotion.renderPromotion(
    main, data,
    Object.assign({ doc: win.document, Tabulator: _fakeTabulator(win.document) },
                  opts || {})
  );
}

function _api() {
  return _win().AIWCockpitPromotion;
}

function _sampleData() {
  return {
    candidate_count: 3,
    counts: { offen: 1, gesichtet: 1, zurueckgestellt: 1 },
    statuses: ["gesichtet", "uebernommen", "zurueckgestellt", "fremdzustaendig"],
    candidates: [
      { subject_id: 77, status: "offen", status_label: "offen (unentschieden)",
        grund: null, herkunft: null, is_final: false },
      { subject_id: 88, status: "gesichtet", status_label: "gesichtet",
        grund: null, herkunft: "Nachbarforum", is_final: false },
      { subject_id: 99, status: "uebernommen", status_label: "uebernommen",
        grund: null, herkunft: null, is_final: true },
    ],
    decisions: [],
  };
}

describe("cockpit_promotion.js — Fremdforum-Promotion (Build 461)", () => {
  // PP01 -------------------------------------------------------------------
  it("PP01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.allowedActions).toBe("function");
    expect(typeof api.renderPromotion).toBe("function");
    expect(typeof api.countsModel).toBe("function");
  });

  // PP02 -------------------------------------------------------------------
  it("PP02: allowedActions spiegelt die Zustandsmaschine", () => {
    const api = _api();
    expect(api.allowedActions("offen").sort()).toEqual(
      ["fremdzustaendig", "gesichtet", "uebernommen", "zurueckgestellt"]
    );
    // gesichtet: kein Selbst-Uebergang.
    expect(api.allowedActions("gesichtet")).not.toContain("gesichtet");
    expect(api.allowedActions("gesichtet").sort()).toEqual(
      ["fremdzustaendig", "uebernommen", "zurueckgestellt"]
    );
    // Wiederaufgriff.
    expect(api.allowedActions("zurueckgestellt")).toContain("gesichtet");
    // Endzustaende: keine Aktion.
    expect(api.allowedActions("uebernommen")).toEqual([]);
    expect(api.allowedActions("fremdzustaendig")).toEqual([]);
    // Unbekannt -> leer, kein Fehler.
    expect(api.allowedActions("quatsch")).toEqual([]);
  });

  // PP03 -------------------------------------------------------------------
  it("PP03: reasonRequired/isFinal", () => {
    const api = _api();
    expect(api.reasonRequired("zurueckgestellt")).toBe(true);
    expect(api.reasonRequired("fremdzustaendig")).toBe(true);
    expect(api.reasonRequired("uebernommen")).toBe(false);
    expect(api.isFinal("uebernommen")).toBe(true);
    expect(api.isFinal("fremdzustaendig")).toBe(true);
    expect(api.isFinal("gesichtet")).toBe(false);
  });

  // PP04 -------------------------------------------------------------------
  it("PP04: countsModel geordnet, fehlende -> 0", () => {
    const api = _api();
    const m = api.countsModel({ counts: { offen: 2 } });
    expect(m.map((c) => c.status)).toEqual(
      ["offen", "gesichtet", "zurueckgestellt", "uebernommen", "fremdzustaendig"]
    );
    expect(m[0].count).toBe(2);
    expect(m[3].count).toBe(0); // uebernommen fehlt -> 0
  });

  // PP05 -------------------------------------------------------------------
  it("PP05: statusDotClass-Ampel", () => {
    const api = _api();
    expect(api.statusDotClass("uebernommen")).toBe("gruen");
    expect(api.statusDotClass("fremdzustaendig")).toBe("rot");
    expect(api.statusDotClass("offen")).toBe("gelb");
    expect(api.statusDotClass("zurueckgestellt")).toBe("gelb");
  });

  // PP06 -------------------------------------------------------------------
  it("PP06: renderPromotion mit/ohne Recht", () => {
    const win = _win();
    const api = win.AIWCockpitPromotion;
    const doc = win.document;

    // mit Recht: Aktions-Buttons vorhanden (offen -> 4).
    const main = doc.createElement("main");
    _render(win, main, _sampleData(), { canEdit: true });
    expect(main.querySelector(".aiw-pagehead").textContent).toContain(
      "Fremdforum-Promotion"
    );
    // Build 557: die Zeilen entstehen jetzt in Tabulator, nicht in einer
    // handgebauten <table>. Dieselbe Zusicherung an der neuen Struktur.
    expect(main.querySelectorAll(".fake-row").length).toBe(3);
    const btns77 = main.querySelectorAll('button[data-uid="77"]');
    expect(btns77.length).toBe(4);
    // Endgueltiger Kandidat 99 -> keine Aktions-Buttons.
    expect(main.querySelectorAll('button[data-uid="99"]').length).toBe(0);

    // ohne Recht: Hinweis + keine Buttons.
    const main2 = doc.createElement("main");
    _render(win, main2, _sampleData(), { canEdit: false });
    expect(main2.querySelector(".aiw-promo-readonly")).toBeTruthy();
    expect(main2.querySelectorAll("button[data-target]").length).toBe(0);
  });

  // PP07 -------------------------------------------------------------------
  it("PP07: Grund-Pflicht im Panel", () => {
    const win = _win();
    const api = win.AIWCockpitPromotion;
    const doc = win.document;
    const main = doc.createElement("main");
    const calls = [];
    _render(win, main, _sampleData(), {
      canEdit: true,
      onDecide: (body) => calls.push(body),
    });

    // 'zurueckgestellt' an Kandidat 77 -> Panel oeffnen.
    main.querySelector(
      'button[data-uid="77"][data-target="zurueckgestellt"]'
    ).click();
    // Bestaetigen OHNE Grund -> kein onDecide, Fehlermeldung.
    main.querySelector("#aiw-promo-confirm").click();
    expect(calls.length).toBe(0);
    expect(main.querySelector("#aiw-promo-result").className).toContain(
      "error"
    );

    // Panel erneut oeffnen, Grund setzen, bestaetigen.
    main.querySelector(
      'button[data-uid="77"][data-target="zurueckgestellt"]'
    ).click();
    main.querySelector("#aiw-promo-herkunft").value = "Forum Y";
    main.querySelector("#aiw-promo-grund").value = "kein Fallbezug";
    main.querySelector("#aiw-promo-confirm").click();
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({
      subject_id: 77, status: "zurueckgestellt",
      grund: "kein Fallbezug", herkunft: "Forum Y",
    });
  });

  // PP08 -------------------------------------------------------------------
  it("PP08: nicht-grund-pflichtiges Ziel + Endzustands-Warnung", () => {
    const win = _win();
    const api = win.AIWCockpitPromotion;
    const doc = win.document;
    const main = doc.createElement("main");
    const calls = [];
    _render(win, main, _sampleData(), {
      canEdit: true,
      onDecide: (body) => calls.push(body),
    });

    // 'uebernommen' (endgueltig, aber KEIN Grund noetig) an 88.
    main.querySelector(
      'button[data-uid="88"][data-target="uebernommen"]'
    ).click();
    // Endzustand zeigt Warnung.
    expect(main.querySelector(".aiw-promo-warn")).toBeTruthy();
    // Ohne Grund bestaetigen -> onDecide gerufen (herkunft aus Vorbelegung).
    main.querySelector("#aiw-promo-confirm").click();
    expect(calls.length).toBe(1);
    expect(calls[0].subject_id).toBe(88);
    expect(calls[0].status).toBe("uebernommen");
    expect(calls[0].grund).toBe("");
  });

  // PP09 -------------------------------------------------------------------
  it("PP09: leere Liste -> Platzhalter; Freitext XSS-sicher", () => {
    const win = _win();
    const api = win.AIWCockpitPromotion;
    const doc = win.document;

    // Build 557: der Leerzustand ist jetzt Tabulators 'placeholder' statt
    // eines Absatzes ANSTELLE der Tabelle. Die Tabelle steht also auch bei
    // null Kandidaten — samt Werkzeugleiste und Trefferzahl, damit die Sicht
    // nicht anders aussieht als alle anderen.
    const empty = doc.createElement("main");
    const leerView = _render(win, empty,
      { candidate_count: 0, counts: {}, candidates: [] }, { canEdit: true });
    expect(leerView.table).toBeTruthy();
    expect(empty.querySelectorAll(".fake-row").length).toBe(0);
    expect(empty.querySelector("#aiw-promotion-tk-treffer").textContent)
      .toBe("0 Zeilen");
    // Der ERKLAERENDE Wortlaut ist erhalten geblieben — er sagt, WARUM nichts
    // da ist. (Die Attrappe zeichnet ihn nicht; geprueft wird die Vorgabe an
    // Tabulator.)
    expect(leerView.table.options.placeholder)
      .toContain("keine Fremdforum-Kandidaten");

    const main = doc.createElement("main");
    _render(win, main, {
      candidate_count: 1, counts: {},
      candidates: [{ subject_id: 5, status: "zurueckgestellt",
        status_label: "zurueckgestellt",
        grund: "<img src=x onerror=alert(1)>", herkunft: null }],
    }, { canEdit: false });
    expect(main.querySelector("img")).toBe(null);
    expect(main.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  // ==========================================================================
  // Build 557 — Tabulator + gemeinsames Tabellen-Werkzeug
  // ==========================================================================

  // PP10 ---------------------------------------------------------------------
  it("PP10: statusRang folgt dem ARBEITSABLAUF, nicht dem Alphabet", () => {
    const api = _api();
    // ALPHABETISCH stuende 'fremdzustaendig' vor 'gesichtet' vor 'offen' —
    // also der Endzustand vor dem Handlungsbedarf. Genau das waere fuer die
    // Chef-Ermittlerin irrefuehrend, die sehen will, was noch zu tun ist.
    expect(api.statusRang("offen")).toBeLessThan(api.statusRang("gesichtet"));
    expect(api.statusRang("gesichtet"))
      .toBeLessThan(api.statusRang("zurueckgestellt"));
    expect(api.statusRang("zurueckgestellt"))
      .toBeLessThan(api.statusRang("uebernommen"));
    expect(api.statusRang("uebernommen"))
      .toBeLessThan(api.statusRang("fremdzustaendig"));

    // null == 'offen' (die implizite Eingangslage).
    expect(api.statusRang(null)).toBe(api.statusRang("offen"));
    // Unbekannt sortiert HINTER allem Bekannten — es verschwindet nicht.
    expect(api.statusRang("quatsch"))
      .toBeGreaterThan(api.statusRang("fremdzustaendig"));
  });

  // PP11 ---------------------------------------------------------------------
  it("PP11: toRows — abgeleitete Felder, Gedankenstrich statt leerer Zelle", () => {
    const api = _api();
    const rows = api.toRows({
      candidates: [
        { subject_id: 7, status: "offen", grund: "", herkunft: "" },
        { subject_id: 8, status: "uebernommen",
          status_label: "in Ermittlung uebernommen",
          grund: "geprueft", herkunft: "EK" },
      ],
    });
    expect(rows.map((r) => r.subject_id)).toEqual([7, 8]);
    expect(rows[0].zustand).toBe("offen (unentschieden)");
    expect(rows[0].zustand_rang).toBe(0);
    expect(rows[0].is_final).toBe(false);
    // Leere Freitexte -> '—'. Eine leere Zelle sieht aus wie ein
    // Anzeigefehler.
    expect(rows[0].grund).toBe("—");
    expect(rows[0].herkunft).toBe("—");

    expect(rows[1].zustand).toBe("in Ermittlung uebernommen");
    expect(rows[1].is_final).toBe(true);
    expect(rows[1].grund).toBe("geprueft");

    // Die Eingabe bleibt unberuehrt.
    const d = { candidates: [{ subject_id: 1, status: "offen" }] };
    api.toRows(d);
    expect(d.candidates[0].grund).toBeUndefined();
  });

  // PP12 ---------------------------------------------------------------------
  it("PP12: spalten — feste Folge; die Aktionsspalte traegt keinen Filter", () => {
    const win = _win();
    const api = win.AIWCockpitPromotion;
    const cols = api.spalten(win.document, true, () => {});
    expect(cols.map((c) => c.field)).toEqual([
      "subject_id", "zustand", "grund", "herkunft", "aktion",
    ]);
    const akt = cols.find((c) => c.field === "aktion");
    expect(akt.kein_filter).toBe(true);
    expect(akt.headerSort).toBe(false);

    // Der Sortierer der Zustandsspalte greift auf den Rang zu.
    const zustand = cols.find((c) => c.field === "zustand");
    const zeile = (r) => ({ getData: () => ({ zustand_rang: r }) });
    expect(zustand.sorter(null, null, zeile(0), zeile(3))).toBeLessThan(0);

    // Und das gemeinsame Werkzeug haengt an alle uebrigen Spalten Filter.
    const mitFilter = win.AIWTableKit.spaltenMitFilter(
      api.toRows(_sampleData()), cols
    );
    expect(mitFilter.find((c) => c.field === "aktion").headerFilter)
      .toBeUndefined();
    mitFilter.filter((c) => c.field && c.field !== "aktion")
      .forEach((c) => { expect(c.headerFilter, c.field).toBeTruthy(); });
  });
});
