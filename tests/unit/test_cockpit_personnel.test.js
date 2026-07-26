/**
 * tests/unit/test_cockpit_personnel.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Personalverwaltung
 *
 * Testsuite fuer management/server/static/cockpit_personnel.js.
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitPersonnel)
 * mit einer TABULATOR-ATTRAPPE, die die Spalten-Formatter UND den
 * rowFormatter aufruft — Muster tests/unit/test_cockpit_cases.test.js.
 *
 * WARUM DIE ATTRAPPE DIE FORMATTER AUFRUFEN MUSS: saemtliche Bedienelemente
 * der Sicht (Flag-Kaestchen, Rollen-Chips mit Widerruf, Zuweisen-Auswahl)
 * entstehen IN den Formattern. Eine Attrappe, die nur Daten haelt, wuerde den
 * ganzen Schreibweg nicht beruehren und die Suite waere 'gruen aber tot'.
 * Der rowFormatter traegt zusaetzlich die Zeilenmarkierung (eigene Person,
 * deaktiviert) — auch sie waere sonst ungeprueft.
 *
 * PS01 — API verfuegbar (renderPersonnel + reine Funktionen).
 * PS02 — statusText: aktiv / inaktiv seit Datum (Grund).
 * PS03 — assignableRoles: nur noch nicht aktive Rollen; isSelf/canEditRow
 *        (Selbstschutz: eigene Zeile nie editierbar, auch mit can_edit).
 * PS04 — renderPersonnel: Zeilen; eigene Zeile '(ich)' ohne Bedienelemente;
 *        XSS-sicher (textContent).
 * PS05 — Flag-Checkbox -> onFlags({person_id, <flag>}); Rollen-x ->
 *        onRevoke({person_role_id}); Auswahl -> onAssign.
 * PS06 — can_edit=false: keine Checkboxen/keine Auswahl/kein x.
 * PS07 — AD-Abschnitt nur bei can_sync; Knopf laedt lazy (onAdsyncLoad mit
 *        Container) und sperrt sich; adsyncOpen=true laedt sofort.
 *
 * BUILD 548 (Tabulator + gemeinsames Tabellen-Werkzeug):
 * PS08 — toRows: abgeleitete Felder. Insbesondere 'ja'/'nein' statt
 *        true/false — ein Filter, den man nicht lesen kann, wird nicht
 *        benutzt.
 * PS09 — spalten(): sieben Spalten in fester Folge, jede mit Filterfeld.
 * PS10 — rowFormatter markiert eigene und deaktivierte Zeilen.
 * PS11 — Werkzeugleiste: Trefferzahl und 'Filter zuruecksetzen' sind da.
 * PS12 — OHNE Tabellenbibliothek: ausdrueckliche Meldung MIT Anzahl, keine
 *        leere Flaeche (die saehe aus wie 'keine Anwender vorhanden').
 * PS13 — HILFE-ANKER: Spaltenkoepfe und Bedienelemente tragen stabile
 *        data-hilfe-id, alle eindeutig und im Muster.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_personnel.js",
  "utf-8"
);
const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

/** Tabulator-Attrappe: haelt die Daten, ruft die Spalten-Formatter UND den
 *  rowFormatter auf und haengt die erzeugten Knoten in den Container, damit
 *  die Bedienelemente im DOM anklickbar sind. */
function _fakeTabulator(doc) {
  return function (container, options) {
    const self = this;
    this.container = container;
    this.options = options;
    this.data = options.data;
    this._filters = [];

    this._render = function (rows) {
      container.textContent = "";
      (rows || []).forEach(function (d) {
        const tr = doc.createElement("div");
        tr.setAttribute("data-row-id", String(d.id));
        (options.columns || []).forEach(function (col) {
          if (typeof col.formatter !== "function") { return; }
          const node = col.formatter({ getData: function () { return d; } });
          if (node && node.nodeType) { tr.appendChild(node); }
        });
        container.appendChild(tr);
        if (typeof options.rowFormatter === "function") {
          options.rowFormatter({
            getData: function () { return d; },
            getElement: function () { return tr; },
          });
        }
      });
    };

    this._render(this.data);
    this.getDataCount = function () { return self.data.length; };
    this.setHeaderFilterValue = function (f, v) {
      self._filters.push([f, v]);
    };
    this.clearHeaderFilter = function () { self._filters = []; };
    this.clearFilter = function () { self._filters = []; };
    this.getHeaderFilters = function () {
      return self._filters.map(function (x) {
        return { field: x[0], value: x[1] };
      });
    };
    this.getSorters = function () { return []; };
    this.getColumns = function () { return []; };
    this.setSort = function () {};
    this.replaceData = function (d) { self.data = d; self._render(d); };
    this.destroy = function () {};
  };
}

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  // Das gemeinsame Tabellen-Werkzeug MUSS zuerst da sein — genau wie im
  // Browser (cockpit.html, Ladereihenfolge).
  dom.window.eval(_tkSrc);
  dom.window.eval(_src);
  return dom.window;
}

/** renderPersonnel mit eingespritzter Attrappe. */
function _render(win, main, data, opts) {
  return win.AIWCockpitPersonnel.renderPersonnel(
    main,
    data,
    Object.assign(
      { doc: win.document, Tabulator: _fakeTabulator(win.document) },
      opts || {}
    )
  );
}

function _data(overrides) {
  return Object.assign(
    {
      persons: [
        {
          id: 1,
          system_username: "h0chef",
          display_name: "Chefin",
          is_investigator: true,
          is_supervisor: true,
          is_support: false,
          is_active: true,
          deactivated_at: null,
          deactivated_reason: null,
          roles: [
            { person_role_id: 11, role_code: "supervisor",
              label: "Chef-Ermittlerin / Aufsicht", assigned_at: 1 },
          ],
        },
        {
          id: 2,
          system_username: "h0erm",
          display_name: "KHK <b>Muster</b>",
          is_investigator: true,
          is_supervisor: false,
          is_support: false,
          is_active: true,
          deactivated_at: null,
          deactivated_reason: null,
          roles: [
            { person_role_id: 22, role_code: "investigator",
              label: "Ermittler:in", assigned_at: 1 },
          ],
        },
        {
          id: 3,
          system_username: "h0weg",
          display_name: "KOK Weg",
          is_investigator: true,
          is_supervisor: false,
          is_support: false,
          is_active: false,
          deactivated_at: 1753300000,
          deactivated_reason: "Nicht mehr im Active-Directory gefuehrt",
          roles: [],
        },
      ],
      roles_catalog: [
        { code: "investigator", label: "Ermittler:in" },
        { code: "supervisor", label: "Chef-Ermittlerin / Aufsicht" },
        { code: "searchagent", label: "Recherche mit Volltextsuche" },
      ],
      actor_person_id: 1,
      can_edit: true,
      can_sync: true,
    },
    overrides || {}
  );
}

describe("cockpit_personnel", () => {
  // PS01 --------------------------------------------------------------------
  it("PS01: API verfuegbar", () => {
    const api = _ctx().AIWCockpitPersonnel;
    expect(api).toBeTruthy();
    for (const fn of [
      "renderPersonnel",
      "statusText",
      "assignableRoles",
      "isSelf",
      "canEditRow",
      "toRows",
      "spalten",
    ]) {
      expect(typeof api[fn]).toBe("function");
    }
    expect(api.FLAGS.length).toBe(3);
  });

  // PS02 --------------------------------------------------------------------
  it("PS02: statusText", () => {
    const api = _ctx().AIWCockpitPersonnel;
    expect(api.statusText(_data().persons[0])).toBe("aktiv");
    const t = api.statusText(_data().persons[2]);
    expect(t).toContain("inaktiv seit 2025");
    expect(t).toContain("Active-Directory");
  });

  // PS03 --------------------------------------------------------------------
  it("PS03: assignableRoles + Selbstschutz-Logik", () => {
    const api = _ctx().AIWCockpitPersonnel;
    const d = _data();
    const forChef = api.assignableRoles(d.persons[0], d.roles_catalog);
    expect(forChef.map((r) => r.code)).toEqual([
      "investigator",
      "searchagent",
    ]);
    expect(api.isSelf(d.persons[0], d)).toBe(true);
    expect(api.isSelf(d.persons[1], d)).toBe(false);
    expect(api.canEditRow(d.persons[0], d)).toBe(false); // eigene Zeile!
    expect(api.canEditRow(d.persons[1], d)).toBe(true);
    expect(
      api.canEditRow(d.persons[1], _data({ can_edit: false }))
    ).toBe(false);
  });

  // PS04 --------------------------------------------------------------------
  it("PS04: renderPersonnel — Zeilen, (ich), XSS", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    const view = _render(w, main, _data());
    expect(typeof view.setResult).toBe("function");
    expect(view.table).toBeTruthy();
    const rows = main.querySelectorAll(".aiw-pers-row");
    expect(rows.length).toBe(3);
    // Eigene Zeile: '(ich)', markiert, KEINE Bedienelemente.
    expect(rows[0].textContent).toContain("h0chef (ich)");
    expect(rows[0].classList.contains("self")).toBe(true);
    expect(rows[0].querySelectorAll("input,select,button").length).toBe(0);
    // Inaktive Zeile ist markiert.
    expect(rows[2].classList.contains("inactive")).toBe(true);
    // XSS: HTML im Anzeigenamen bleibt TEXT. Der Anzeigename laeuft ueber
    // Tabulators 'plaintext'-Formatter, steht also nicht im Attrappen-DOM —
    // geprueft wird deshalb, dass NIRGENDS ein <b> entsteht.
    expect(main.querySelector("b")).toBeNull();
    const zeile = w.AIWCockpitPersonnel.toRows(_data())[1];
    expect(zeile.display_name).toBe("KHK <b>Muster</b>");
  });

  // PS05 --------------------------------------------------------------------
  it("PS05: Callbacks flags/revoke/assign", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    const flags = [], revoked = [], assigned = [];
    _render(w, main, _data(), {
      onFlags: (b) => flags.push(b),
      onRevoke: (b) => revoked.push(b),
      onAssign: (b) => assigned.push(b),
    });
    const row2 = main.querySelectorAll(".aiw-pers-row")[1];
    // Flag: erste Checkbox (is_investigator, aktuell true) abwaehlen.
    const cb = row2.querySelector("input[type=checkbox]");
    cb.checked = false;
    cb.dispatchEvent(new w.Event("change"));
    expect(flags).toEqual([{ person_id: 2, is_investigator: false }]);
    // Rollen-x -> Widerruf mit exakter person_role_id.
    row2.querySelector(".aiw-pers-chip-x")
      .dispatchEvent(new w.Event("click"));
    expect(revoked).toEqual([{ person_role_id: 22 }]);
    // Dropdown -> Zuweisung.
    const sel = row2.querySelector(".aiw-pers-assign-sel");
    sel.value = "searchagent";
    sel.dispatchEvent(new w.Event("change"));
    expect(assigned).toEqual([{ person_id: 2, role_code: "searchagent" }]);
  });

  // PS06 --------------------------------------------------------------------
  it("PS06: ohne can_edit keine Bedienelemente", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    _render(w, main, _data({ can_edit: false, can_sync: false }));
    // In der TABELLE gibt es keine Bedienelemente. (Die Werkzeugleiste hat
    // einen Knopf 'Filter zuruecksetzen' — der ist kein Schreibvorgang und
    // deshalb hier ausdruecklich ausgenommen.)
    const tabelle = main.querySelector("#aiw-personnel-table");
    expect(tabelle.querySelectorAll("input,select").length).toBe(0);
    expect(main.querySelectorAll(".aiw-pers-chip-x").length).toBe(0);
  });

  // PS07 --------------------------------------------------------------------
  it("PS07: AD-Abschnitt lazy / adsyncOpen", () => {
    const w = _ctx();
    const api = w.AIWCockpitPersonnel;
    // can_sync=false -> kein Abschnitt.
    const m0 = w.document.createElement("div");
    api.renderPersonnel(m0, _data({ can_sync: false }), { doc: w.document });
    expect(m0.querySelector(".aiw-pers-adsync")).toBeNull();

    // can_sync=true -> Abschnitt, Laden erst auf Klick.
    const m1 = w.document.createElement("div");
    const loads = [];
    api.renderPersonnel(m1, _data(), {
      doc: w.document,
      onAdsyncLoad: (box) => loads.push(box),
    });
    expect(m1.querySelector(".aiw-pers-adsync")).toBeTruthy();
    expect(loads.length).toBe(0); // lazy: noch kein LDAP-Abruf
    const btn = m1.querySelector(".aiw-pers-adsync-load");
    btn.dispatchEvent(new w.Event("click"));
    expect(loads.length).toBe(1);
    expect(loads[0].classList.contains("aiw-pers-adsync")).toBe(true);
    expect(btn.disabled).toBe(true);

    // adsyncOpen=true -> laedt sofort (nach eigener AD-Aktion).
    const m2 = w.document.createElement("div");
    const loads2 = [];
    api.renderPersonnel(m2, _data(), {
      doc: w.document,
      adsyncOpen: true,
      onAdsyncLoad: (box) => loads2.push(box),
    });
    expect(loads2.length).toBe(1);
  });

  // ==========================================================================
  // Build 548 — Tabulator + gemeinsames Tabellen-Werkzeug
  // ==========================================================================

  // PS08 ---------------------------------------------------------------------
  it("PS08: toRows — abgeleitete Felder, 'ja'/'nein' statt true/false", () => {
    const api = _ctx().AIWCockpitPersonnel;
    const rows = api.toRows(_data());
    expect(rows.length).toBe(3);

    const chefin = rows[0];
    expect(chefin.status).toBe("aktiv");
    expect(chefin.ist_selbst).toBe(true);
    expect(chefin.editierbar).toBe(false);          // Selbstschutz
    expect(chefin.rollen_text).toBe("supervisor");

    // DER PUNKT: der Filterwert ist lesbar. Eine Auswahlliste mit
    // 'true'/'false' wuerde niemand benutzen.
    expect(chefin.f_is_investigator).toBe("ja");
    expect(chefin.f_is_support).toBe("nein");
    // Der Wahrheitswert bleibt fuer den Formatter erhalten.
    expect(chefin.is_investigator).toBe(true);

    const weg = rows[2];
    expect(weg.status).toBe("inaktiv");
    // Der volle Text steht separat und taugt nicht als Filterwert (er lautet
    // bei jeder Person anders) — deshalb ist er NICHT das Filterfeld.
    expect(weg.status_detail).toContain("inaktiv seit 2025");
    expect(weg.status_detail).toContain("Active-Directory");
    expect(weg.rollen_text).toBe("");

    // toRows fasst die Eingabe nicht an.
    const d = _data();
    api.toRows(d);
    expect(d.persons[0].roles.length).toBe(1);
  });

  // PS09 ---------------------------------------------------------------------
  it("PS09: spalten — feste Folge, jede Spalte hat ein Feld", () => {
    const w = _ctx();
    const cols = w.AIWCockpitPersonnel.spalten(w.document, _data(), {});
    expect(cols.map((c) => c.field)).toEqual([
      "system_username",
      "display_name",
      "status",
      "f_is_investigator",
      "f_is_supervisor",
      "f_is_support",
      "rollen_text",
    ]);
    // Ohne Feld gaebe es weder Filter noch Sortierung.
    expect(cols.every((c) => !!c.field)).toBe(true);

    // Und das gemeinsame Werkzeug haengt an jede Spalte einen Filter — das
    // ist der eigentliche Gewinn des Umbaus.
    const rows = w.AIWCockpitPersonnel.toRows(_data());
    const mitFilter = w.AIWTableKit.spaltenMitFilter(rows, cols);
    expect(mitFilter.every((c) => !!c.headerFilter)).toBe(true);
    // Die Filterart folgt der ANZAHL VERSCHIEDENER WERTE, nicht der Spalte:
    // wenige -> Auswahlliste, viele -> Eingabefeld (tablekit,
    // SCHWELLE_AUSWAHL). Das ist der Grund, warum die Entscheidung nicht je
    // Spalte von Hand steht — eine Dienststelle mit 6 Kennungen braucht eine
    // Liste, eine mit 60 ein Suchfeld.
    const status = mitFilter.find((c) => c.field === "status");
    expect(status.headerFilter).toBe("list");
    // Mit nur drei Personen ist auch die Kennung eine Auswahlliste ...
    const kennungWenig = mitFilter.find((c) => c.field === "system_username");
    expect(kennungWenig.headerFilter).toBe("list");

    // ... und ab der Schwelle kippt dieselbe Spalte auf ein Eingabefeld.
    const viele = [];
    for (let i = 0; i < w.AIWTableKit.SCHWELLE_AUSWAHL + 2; i++) {
      viele.push({
        id: 100 + i, system_username: "nutzer" + i, display_name: "N" + i,
        is_investigator: true, is_supervisor: false, is_support: false,
        is_active: true, roles: [],
      });
    }
    const rowsViele = w.AIWCockpitPersonnel.toRows({
      persons: viele, roles_catalog: [], actor_person_id: 1, can_edit: true,
    });
    const kennungViel = w.AIWTableKit
      .spaltenMitFilter(rowsViele, cols)
      .find((c) => c.field === "system_username");
    expect(kennungViel.headerFilter).toBe("input");
    // 'Status' bleibt eine Liste — dort gibt es weiterhin nur zwei Werte.
    const statusViel = w.AIWTableKit
      .spaltenMitFilter(rowsViele, cols)
      .find((c) => c.field === "status");
    expect(statusViel.headerFilter).toBe("list");
  });

  // PS10 ---------------------------------------------------------------------
  it("PS10: rowFormatter markiert eigene und deaktivierte Zeilen", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    _render(w, main, _data());
    const rows = main.querySelectorAll(".aiw-pers-row");
    expect(rows[0].classList.contains("self")).toBe(true);
    expect(rows[0].classList.contains("inactive")).toBe(false);
    expect(rows[1].classList.contains("self")).toBe(false);
    expect(rows[2].classList.contains("inactive")).toBe(true);
  });

  // PS11 ---------------------------------------------------------------------
  it("PS11: Werkzeugleiste mit Trefferzahl und 'Filter zuruecksetzen'", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    const view = _render(w, main, _data());
    expect(view.leiste).toBeTruthy();
    const leiste = main.querySelector("#aiw-personnel-tk");
    expect(leiste).toBeTruthy();
    expect(main.querySelector("#aiw-personnel-tk-treffer").textContent)
      .toBe("3 Zeilen");
    const clear = main.querySelector("#aiw-personnel-tk-clear");
    expect(clear).toBeTruthy();
    // Der Knopf wirkt auf die Tabelle (Attrappe merkt sich das).
    view.table.setHeaderFilterValue("status", "aktiv");
    expect(view.table.getHeaderFilters().length).toBe(1);
    clear.dispatchEvent(new w.Event("click"));
    expect(view.table.getHeaderFilters().length).toBe(0);
  });

  // PS12 ---------------------------------------------------------------------
  it("PS12: ohne Tabellenbibliothek — Meldung MIT Anzahl, keine Leere", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    // Kein Ctor injiziert, window.Tabulator existiert nicht.
    const view = w.AIWCockpitPersonnel.renderPersonnel(main, _data(), {
      doc: w.document,
    });
    expect(view.table).toBeNull();
    const hinweis = main.querySelector(".aiw-placeholder");
    expect(hinweis).toBeTruthy();
    // ENTSCHEIDEND: die Anzahl steht da. Eine leere Flaeche saehe aus wie
    // 'keine Anwender vorhanden' (Grundregel 1).
    expect(hinweis.textContent).toContain("3 Anwender");
    expect(hinweis.textContent).toContain("nicht verfügbar");
  });

  // PS13 ---------------------------------------------------------------------
  it("PS13: Hilfe-Anker sind gesetzt, eindeutig und im Muster", () => {
    const w = _ctx();
    const TK = w.AIWTableKit;
    const main = w.document.createElement("div");
    _render(w, main, _data());

    // Aus der Werkzeugleiste (vom gemeinsamen Werkzeug vergeben).
    const ausLeiste = TK.hilfeIds(main.querySelector("#aiw-personnel-tk"));
    expect(ausLeiste).toContain("personnel.werkzeug.filter_entfernen");
    expect(ausLeiste).toContain("personnel.werkzeug.trefferzahl");

    // Aus den Bedienelementen der Zeilen (von dieser Sicht vergeben).
    const alle = TK.hilfeIds(main);
    expect(alle).toContain("personnel.bedienung.flag_investigator");
    expect(alle).toContain("personnel.bedienung.flag_supervisor");
    expect(alle).toContain("personnel.bedienung.flag_support");
    expect(alle).toContain("personnel.bedienung.rolle_widerrufen");
    expect(alle).toContain("personnel.bedienung.rolle_zuweisen");

    // Aus den Spaltenkoepfen (titleFormatter).
    const cols = w.AIWCockpitPersonnel.spalten(w.document, _data(), {});
    const kopfIds = cols
      .filter((c) => typeof c.titleFormatter === "function")
      .map((c) => c.titleFormatter().getAttribute("data-hilfe-id"));
    expect(kopfIds.length).toBe(7);
    expect(kopfIds).toContain("personnel.spalte.rollen");

    // JEDE Kennung folgt dem Muster — eine krumme waere ein toter Link,
    // sobald es die Schnellhilfe gibt.
    alle.concat(kopfIds).forEach((id) => {
      expect(TK.hilfeGueltig(id), id).toBe(true);
    });
    // Und die Spaltenkennungen sind untereinander eindeutig.
    expect(new Set(kopfIds).size).toBe(kopfIds.length);
  });
});
