/**
 * tests/unit/test_cockpit_assignment.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Zuweisung
 *
 * Testsuite fuer management/server/static/cockpit_assignment.js.
 * Getestet wird der ECHTE Code (readFileSync + JSDOM,
 * window.AIWCockpitAssignment) mit einer Tabulator-ATTRAPPE, die die
 * Spalten-Formatter WIRKLICH aufruft — sonst wuerde der Auswahl- und
 * Vormerkungsweg im Test gar nicht beruehrt ("gruen aber tot"-Falle; dasselbe
 * Muster wie in test_cockpit_cases.test.js, Build 384).
 *
 * ANKERANPASSUNG BUILD 534 — BITTE LESEN:
 *   AZ05 und AZ06 pruefen seit Build 534 eine TABULATOR-Tabelle statt einer
 *   HTML-Tabelle mit drei <select> je Zeile. Dass die alten Fassungen dieser
 *   beiden Tests fehlgeschlagen sind, ist die GEWOLLTE Wirkung eines Ankers:
 *   die Sicht wurde bewusst umgebaut (Kopffilter, Spaltenwahl, Sammelmodus).
 *   Die uebrigen Anker (AZ01-AZ04) sind UNVERAENDERT geblieben — die reinen
 *   Funktionen sollten der Umbau ueberstehen, und sie haben es.
 *
 * AZ01 — API verfuegbar.
 * AZ02 — toRows + assigneeLabel (inkl. nicht zugewiesen).
 * AZ03 — investigatorOptions: '(nicht zugewiesen)' + Ermittler mit Last.
 * AZ04 — changeRequest: assign/priority/status; '' -> person_id null.
 * AZ05 — renderAssignment: Tabelle, Werkzeugleiste, Sammel-Steuerkopf.
 * AZ06 — setMessage: Rueckmeldung (Erfolg/Fehler) sichtbar.
 * AZ07 — batchAnfrage: Kopfauswahl gilt fuer alle, Vormerkung schlaegt Kopf,
 *        Faelle OHNE Aenderungswunsch werden BENANNT (Grundregel 1).
 * AZ08 — batchMeldung: nennt geschrieben, unveraendert UND die Belegspanne.
 * AZ09 — Sammelmodus: Kaestchenspalte erscheint, Auswahl lebt im Zustand.
 * AZ10 — Auswahl umkehren wirkt auf die SICHTBAREN Zeilen.
 * AZ11 — Einzelaenderung: KEIN optimistisches UI (alter Wert bleibt stehen,
 *        bis der Server bestaetigt) — der forensische Kern dieser Sicht.
 * AZ12 — bestaetige() aktualisiert NUR die betroffene Zeile.
 * AZ13 — fehlerMeldung nennt die Einzelbeanstandungen des Servers.
 *
 * Version: v0.8.534 · Build: 534 · 2026-07-26
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _srcKit = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);
const _src = readFileSync(
  "management/server/static/cockpit_assignment.js",
  "utf-8"
);

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_srcKit);      // das Werkzeug MUSS zuerst da sein
  dom.window.eval(_src);
  dom.window.localStorage.clear();
  return dom.window;
}
function _api() { return _ctx().AIWCockpitAssignment; }

/** Tabulator-Attrappe: haelt die Daten, ruft die Spalten-Formatter auf und
 *  haengt deren Knoten in den Container, sodass Kaestchen anklickbar sind. */
function _fakeTabulator(doc) {
  return function (container, options) {
    const self = this;
    this.container = container;
    this.options = options;
    this.data = (options.data || []).slice();
    this._handler = {};
    this._sort = [];
    this._filter = [];

    this._render = function () {
      container.textContent = "";
      (self.data || []).forEach(function (d) {
        const tr = doc.createElement("div");
        tr.className = "fake-row";
        tr.setAttribute("data-row-id", String(d.subject_id));
        (self.options.columns || []).forEach(function (col) {
          if (typeof col.formatter !== "function") { return; }
          const el = doc.createElement("span");
          const node = col.formatter({
            getData: function () { return d; },
            getElement: function () { return el; },
            getField: function () { return col.field; },
            getColumn: function () {
              return { getDefinition: function () { return col; } };
            },
          });
          if (node && node.nodeType) { tr.appendChild(node); }
          else if (node !== undefined && node !== null) {
            el.textContent = String(node);
            el.setAttribute("data-field", col.field);
            tr.appendChild(el);
          }
        });
        container.appendChild(tr);
      });
      // Spaltenkoepfe mit eigener Beschriftung (titleFormatter).
      (self.options.columns || []).forEach(function (col) {
        if (typeof col.titleFormatter !== "function") { return; }
        const node = col.titleFormatter();
        if (node && node.nodeType) { container.appendChild(node); }
      });
    };

    this.on = function (name, fn) { self._handler[name] = fn; };
    this.getData = function () { return self.data; };
    this.setColumns = function (cols) {
      self.options.columns = cols; self._render();
    };
    this.getColumnDefinitions = function () { return self.options.columns; };
    this.replaceData = function (d) { self.data = d; self._render(); };
    this.updateData = function (list) {
      (list || []).forEach(function (u) {
        const i = self.data.findIndex(function (r) {
          return r.subject_id === u.subject_id;
        });
        if (i >= 0) { self.data[i] = u; }
      });
      self._render();
    };
    this.redraw = function () { self._render(); };
    this.setSort = function (s) { self._sort = s; };
    this.getSorters = function () { return self._sort; };
    this.setHeaderFilterValue = function (f, v) {
      self._filter.push({ field: f, value: v });
    };
    this.getHeaderFilters = function () { return self._filter; };
    this.clearHeaderFilter = function () { self._filter = []; };
    this.clearFilter = function () {};

    this._render();
    // 'tableBuilt' feuert synchron, damit der Test nicht auf Zeitgeber wartet.
    const built = this._handler.tableBuilt;
    setTimeout(function () { if (built) { built(); } }, 0);
  };
}

function _data() {
  return {
    cases: [
      { subject_id: 18, username: "b18", assigned_to: 2,
        assigned_display_name: "Mueller", priority: 3, status: "in_progress",
        ampel: "gruen" },
      { subject_id: 19, username: "b19", assigned_to: null,
        assigned_display_name: null, priority: 5, status: "open",
        ampel: "rot" },
    ],
    investigators: [
      { person_id: 1, system_username: "h0a2898", display_name: "Chefin",
        case_count: 0 },
      { person_id: 2, system_username: "h002", display_name: "Mueller",
        case_count: 1 },
    ],
    statuses: ["open", "in_progress", "approved", "closed"],
    priority_min: 1, priority_max: 5,
  };
}

function _render(win, opts) {
  const main = win.document.createElement("main");
  win.document.body.appendChild(main);
  const view = win.AIWCockpitAssignment.renderAssignment(
    main, _data(),
    Object.assign({ Tabulator: _fakeTabulator(win.document) }, opts || {})
  );
  return { main, view };
}

describe("cockpit_assignment.js — Zuweisung (Build 534)", () => {
  it("AZ01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.changeRequest).toBe("function");
    expect(typeof api.renderAssignment).toBe("function");
    expect(typeof api.batchAnfrage).toBe("function");
    expect(typeof api.batchMeldung).toBe("function");
  });

  it("AZ02: toRows + assigneeLabel", () => {
    const api = _api();
    const rows = api.toRows(_data());
    expect(rows.length).toBe(2);
    expect(rows[0].assignee).toBe("Mueller");
    expect(rows[0].status_label).toBe("in Arbeit");
    expect(rows[1].assignee).toBe("(nicht zugewiesen)");
    expect(rows[1].assigned_to).toBe(null);
    // Build 534: die Ampel faehrt mit (Zeilenfaerbung wie Fall-Erkennung).
    expect(rows[1].ampel).toBe("rot");
  });

  it("AZ03: investigatorOptions", () => {
    const api = _api();
    const opts = api.investigatorOptions(_data());
    expect(opts[0]).toEqual({ value: "", label: "(nicht zugewiesen)" });
    expect(opts[1].value).toBe("1");
    expect(opts[2].label).toBe("Mueller (1)"); // mit aktueller Last
  });

  it("AZ04: changeRequest", () => {
    const api = _api();
    expect(api.changeRequest("assign", 18, "2")).toEqual({
      path: "/api/case/assign", body: { subject_id: 18, person_id: 2 },
    });
    // Entziehen: '' -> null
    expect(api.changeRequest("assign", 18, "")).toEqual({
      path: "/api/case/assign", body: { subject_id: 18, person_id: null },
    });
    expect(api.changeRequest("priority", 18, "1")).toEqual({
      path: "/api/case/priority", body: { subject_id: 18, priority: 1 },
    });
    expect(api.changeRequest("status", 18, "closed")).toEqual({
      path: "/api/case/status", body: { subject_id: 18, status: "closed" },
    });
    expect(api.changeRequest("pfui", 18, "x")).toBe(null);
  });

  it("AZ05: renderAssignment baut Kopf, Werkzeugleiste und Tabelle", () => {
    const win = _ctx();
    const { main, view } = _render(win);
    expect(view).toBeTruthy();
    expect(view.table).toBeTruthy();

    expect(main.querySelector(".aiw-pagehead").textContent).toBe("Zuweisung");
    expect(main.querySelector("#aiw-assign-sub").textContent)
      .toContain("2 Faelle");
    // Der Steuerkopf ist EIN Behaelter (wird per CSS fixiert).
    expect(main.querySelector("#aiw-assign-kopf")).toBeTruthy();
    // Gemeinsame Werkzeugleiste: Spaltenwahl + Filter zuruecksetzen.
    expect(main.querySelector("#aiw-assign-spalten")).toBeTruthy();
    expect(main.querySelector("#aiw-assign-tk-clear")).toBeTruthy();
    // Sammel-Steuerkopf existiert, ist aber zunaechst verborgen.
    const bar = main.querySelector("#aiw-assign-batchbar");
    expect(bar).toBeTruthy();
    expect(bar.hidden).toBe(true);
    // Zwei Datenzeilen.
    expect(main.querySelectorAll("#aiw-assign-table .fake-row"))
      .toHaveLength(2);
  });

  it("AZ06: setMessage zeigt Rueckmeldung", () => {
    const win = _ctx();
    const { main, view } = _render(win);
    view.setMessage("Gespeichert (Beleg #42).", false);
    const msg = main.querySelector("#aiw-assign-msg");
    expect(msg.textContent).toContain("Beleg #42");
    expect(msg.classList.contains("error")).toBe(false);
    view.setMessage("Fehler: kaputt", true);
    expect(msg.classList.contains("error")).toBe(true);
  });

  it("AZ07: batchAnfrage — Kopf gilt, Vormerkung schlaegt Kopf", () => {
    const api = _api();
    const rows = [
      { subject_id: 18 },
      { subject_id: 19, vormerk_person: "1" },
      { subject_id: 20, vormerk_priority: "2" },
      { subject_id: 21 },                       // nicht ausgewaehlt
    ];
    const gewaehlt = { 18: true, 19: true, 20: true };

    const a = api.batchAnfrage(rows, gewaehlt,
                               { person: "2", priority: "3" });
    expect(a.changes).toEqual([
      { subject_id: 18, person_id: 2, priority: 3 },
      { subject_id: 19, person_id: 1, priority: 3 },   // Vormerkung schlaegt
      { subject_id: 20, person_id: 2, priority: 2 },   // Vormerkung schlaegt
    ]);
    expect(a.ohneWunsch).toEqual([]);

    // Kopf auf '(nicht aendern)' -> nur die Vorgemerkten haben einen Wunsch,
    // die uebrigen werden BENANNT statt still zu verschwinden.
    const b = api.batchAnfrage(rows, gewaehlt, {
      person: api.KEINE_AENDERUNG, priority: api.KEINE_AENDERUNG,
    });
    expect(b.changes).toEqual([
      { subject_id: 19, person_id: 1 },
      { subject_id: 20, priority: 2 },
    ]);
    expect(b.ohneWunsch).toEqual([18]);

    // 'Zuweisung entziehen' ist ein eigener Wunsch (person_id: null) und darf
    // nicht mit '(nicht aendern)' verwechselt werden.
    const c = api.batchAnfrage([{ subject_id: 18 }], { 18: true },
                               { person: "", priority: api.KEINE_AENDERUNG });
    expect(c.changes).toEqual([{ subject_id: 18, person_id: null }]);
  });

  it("AZ08: batchMeldung nennt alle Zahlen und die Belegspanne", () => {
    const api = _api();
    const m = api.batchMeldung({
      ok: true, eingereicht: 3, geschrieben: 2, unveraendert: 1, belege: 3,
      results: [
        { subject_id: 18, ergebnis: "geschrieben", audit_seqs: [10, 11] },
        { subject_id: 19, ergebnis: "geschrieben", audit_seqs: [12] },
        { subject_id: 20, ergebnis: "unveraendert", audit_seqs: [] },
      ],
    });
    expect(m.error).toBe(false);
    expect(m.text).toContain("2 Fall/Faelle geschrieben");
    expect(m.text).toContain("3 Beleg(e)");
    // 'unveraendert' wird ausdruecklich genannt — sonst raetselt der Anwender,
    // warum die Belegzahl kleiner ist als die Zahl der ausgewaehlten Faelle.
    expect(m.text).toContain("1 Fall/Faelle waren bereits");
    expect(m.text).toContain("#10–#12");
  });

  it("AZ09: Sammelmodus blendet die Kaestchenspalte ein", () => {
    const win = _ctx();
    const { main, view } = _render(win);
    expect(view.istSammelmodus()).toBe(false);
    expect(main.querySelectorAll("input[type=checkbox]")).toHaveLength(0);

    main.querySelector("#aiw-assign-batchmode")
      .dispatchEvent(new win.Event("click"));
    expect(view.istSammelmodus()).toBe(true);
    expect(main.querySelector("#aiw-assign-batchbar").hidden).toBe(false);

    const boxen = main.querySelectorAll(
      "#aiw-assign-table input[type=checkbox]");
    expect(boxen).toHaveLength(2);

    boxen[0].checked = true;
    boxen[0].dispatchEvent(new win.Event("change"));
    expect(view.getAuswahl()).toEqual([18]);
    expect(main.querySelector("#aiw-assign-batch-stand").textContent)
      .toContain("1 ausgewaehlt");
    // Ohne Kopfauswahl gibt es nichts zu schreiben -> Absenden gesperrt,
    // und der Grund steht daneben.
    expect(main.querySelector("#aiw-assign-batch-send").disabled).toBe(true);
    expect(main.querySelector("#aiw-assign-batch-stand").textContent)
      .toContain("ohne Aenderungswunsch");

    // Kopfauswahl setzen -> Absenden frei.
    const person = main.querySelector("#aiw-assign-batch-person");
    person.value = "1";
    person.dispatchEvent(new win.Event("change"));
    expect(main.querySelector("#aiw-assign-batch-send").disabled).toBe(false);

    // Abbrechen verwirft die Auswahl und beendet den Modus.
    main.querySelector("#aiw-assign-batch-cancel")
      .dispatchEvent(new win.Event("click"));
    expect(view.istSammelmodus()).toBe(false);
    expect(view.getAuswahl()).toEqual([]);
    expect(main.querySelector("#aiw-assign-msg").textContent)
      .toContain("nichts geschrieben");
  });

  it("AZ10: Auswahl umkehren wirkt auf die sichtbaren Zeilen", () => {
    const win = _ctx();
    const { main, view } = _render(win);
    view.setSammelmodus(true);

    const boxen = main.querySelectorAll(
      "#aiw-assign-table input[type=checkbox]");
    boxen[0].checked = true;
    boxen[0].dispatchEvent(new win.Event("change"));
    expect(view.getAuswahl()).toEqual([18]);

    main.querySelector("#aiw-assign-invert")
      .dispatchEvent(new win.Event("click"));
    // 18 war gewaehlt -> raus; 19 war es nicht -> rein.
    expect(view.getAuswahl()).toEqual([19]);
  });

  it("AZ11: Einzelaenderung — KEIN optimistisches UI", () => {
    const win = _ctx();
    const gerufen = [];
    const { main, view } = _render(win, {
      onChange: function (kind, sid, wert) { gerufen.push([kind, sid, wert]); },
    });

    // Bearbeitung einer Zelle nachstellen: die Attrappe reicht cellEdited
    // durch, wie Tabulator es taete.
    const table = view.table;
    let zurueckgenommen = 0;
    const spalte = table.options.columns.filter(function (c) {
      return c.field === "priority";
    })[0];
    table._handler.cellEdited({
      getField: function () { return "priority"; },
      getValue: function () { return "1"; },
      getData: function () { return { subject_id: 18 }; },
      getColumn: function () {
        return { getDefinition: function () { return spalte; } };
      },
      restoreOldValue: function () { zurueckgenommen += 1; },
    });

    // DER KERN: der alte Wert wurde SOFORT wiederhergestellt — die Sicht zeigt
    // nichts Ungeschriebenes. Erst die Serverantwort setzt den neuen Stand.
    expect(zurueckgenommen).toBe(1);
    expect(gerufen).toEqual([["priority", 18, "1"]]);
    expect(main.querySelector("#aiw-assign-msg").textContent)
      .toContain("Schreibe");
  });

  it("AZ12: bestaetige aktualisiert NUR die betroffene Zeile", () => {
    const win = _ctx();
    const { view } = _render(win);
    const vorher = view.table.getData().map(function (r) {
      return r.priority;
    });
    expect(vorher).toEqual([3, 5]);

    view.bestaetige(18, { priority: 1 }, "Gespeichert (Beleg #7).");
    const nachher = view.table.getData();
    expect(nachher[0].priority).toBe(1);
    expect(nachher[1].priority).toBe(5);      // unberuehrt

    view.bestaetige(19, { assigned_to: 2 }, null);
    expect(view.table.getData()[1].assignee).toBe("Mueller");

    // Eine Bestaetigung fuer einen unbekannten Fall wird GEMELDET, nicht
    // stillschweigend verworfen.
    view.bestaetige(999, { priority: 1 }, null);
    expect(win.document.querySelector("#aiw-assign-msg").textContent)
      .toContain("unbekannten Fall");
  });

  it("AZ13: fehlerMeldung nennt die Einzelbeanstandungen", () => {
    const api = _api();
    const err = new Error("2 Beanstandung(en) — es wurde NICHTS geschrieben.");
    err.zeilen = ["Fall 999 existiert nicht.", "Person 3 ist kein Ermittler."];
    const t = api.fehlerMeldung(err);
    expect(t).toContain("999");
    expect(t).toContain("kein Ermittler");
    // Ohne Zeilen bleibt die reine Meldung.
    expect(api.fehlerMeldung(new Error("kaputt"))).toBe("Fehler: kaputt");
  });

  it("AZ14: ohne Tabellenbibliothek bleibt die Sicht ehrlich", () => {
    const win = _ctx();
    const main = win.document.createElement("main");
    const view = win.AIWCockpitAssignment.renderAssignment(main, _data(), {});
    expect(view.table).toBe(null);
    // Kein stiller Funktionsverlust: der Grund steht in der Sicht.
    expect(main.querySelector(".aiw-placeholder").textContent)
      .toContain("nichts veraendert");
  });
});
