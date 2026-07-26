/**
 * tests/unit/test_cockpit_tabellen_ux.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: UX/Tabellen (Build 549)
 *
 * DIE KONFORMITAETSSUITE DER LISTENSICHTEN.
 *
 * WARUM ES SIE GIBT: mc 2026-07-26 — "Einmal Erlerntes soll immer wieder
 * verwendet werden." Das laesst sich nicht durch guten Willen sichern. Jede
 * hier eingetragene Sicht muss DIESELBEN Zusicherungen erfuellen; wer eine
 * Sicht umbaut und die Werkzeugleiste vergisst, bricht diese Datei statt
 * unbemerkt eine zwoelfte Variante zu erzeugen.
 *
 * Sie ist damit zugleich die maschinelle Fassung der Abnahme-Checkliste aus
 * Bauplan UX/Tabellen Abschnitt 4 (Build 556) — eine Checkliste, die niemand
 * abhakt, ist eine Bitte.
 *
 * JE SICHT WIRD GEPRUEFT:
 *   UX01 — Es gibt eine Werkzeugleiste mit der erwarteten Kennung.
 *   UX02 — 'Filter zuruecksetzen' ist da UND wirkt auf die Tabelle.
 *   UX03 — Die Trefferzahl steht da und nennt die tatsaechliche Zeilenzahl.
 *   UX04 — JEDE Spalte mit Feld traegt einen Kopffilter.
 *   UX05 — Die Hilfe-Anker sind gesetzt, eindeutig und im Muster.
 *   UX06 — OHNE Tabellenbibliothek: ausdrueckliche Meldung MIT Anzahl —
 *          keine leere Flaeche (die saehe aus wie 'keine Daten vorhanden',
 *          Grundregel 1).
 *
 * NEUE SICHTEN werden in REGISTER eingetragen — mehr ist nicht zu tun.
 *
 * Version: v0.8.549 · Build: 549 · 2026-07-26
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

function _src(name) {
  return readFileSync("management/server/static/" + name, "utf-8");
}

/** Tabulator-Attrappe: haelt die Daten, ruft die Spalten-Formatter und den
 *  rowFormatter auf und beantwortet die Fragen, die tablekit stellt. */
function _fakeTabulator(doc) {
  return function (host, options) {
    const self = this;
    this.options = options;
    this.data = options.data || [];
    this._filters = [];
    (this.data || []).forEach(function (d) {
      const tr = doc.createElement("div");
      tr.className = "fake-row";
      (options.columns || []).forEach(function (col) {
        if (typeof col.formatter !== "function") { return; }
        let node = null;
        try {
          node = col.formatter({
            getData: function () { return d; },
            getValue: function () { return d[col.field]; },
          });
        } catch (e) { /* Formatter ohne Daten -> hier unerheblich */ }
        if (node && node.nodeType) { tr.appendChild(node); }
      });
      host.appendChild(tr);
      if (typeof options.rowFormatter === "function") {
        try {
          options.rowFormatter({
            getData: function () { return d; },
            getElement: function () { return tr; },
          });
        } catch (e) { /* s. o. */ }
      }
    });
    this.getDataCount = function () { return self.data.length; };
    this.setHeaderFilterValue = function (f, v) { self._filters.push([f, v]); };
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
    this.destroy = function () {};
  };
}

/** REGISTER der umgebauten Listensichten.
 *  datei/global/render = wie die Sicht heisst und wie sie gezeichnet wird.
 *  sicht  = Kennung (Praefix der Hilfe-Anker, Schluessel der Sicherung).
 *  zeilen = erwartete Zeilenzahl aus 'daten'. */
const REGISTER = [
  {
    name: "overview", datei: "cockpit_overview.js",
    global: "AIWCockpitOverview", render: "renderOverview", sicht: "overview",
    zeilen: 2,
    daten: () => ({
      scope: "alle", count: 2,
      cases: [
        { subject_id: 18, username: "b18", status: "open", ampel: "rot",
          ampel_reason: "offen_nicht_zugewiesen", priority: 3,
          assigned_to: null, assigned_display_name: null,
          last_activity_at: 1000, event_count: 1, has_note: false,
          support_active: false, support_count: 0 },
        { subject_id: 19, username: "b19", status: "in_progress",
          ampel: "gruen", ampel_reason: "laeuft", priority: 2,
          assigned_to: 2, assigned_display_name: "Mueller",
          last_activity_at: 2000, event_count: 3, has_note: true,
          support_active: false, support_count: 0 },
      ],
    }),
  },
  {
    name: "mycases", datei: "cockpit_mycases.js",
    global: "AIWCockpitMyCases", render: "renderMyCases", sicht: "mycases",
    zeilen: 2,
    daten: () => ({
      count: 2,
      cases: [
        { subject_id: 18, username: "b18", status: "open", ampel: "rot",
          priority: 3, last_activity_at: 1000, event_count: 1 },
        { subject_id: 19, username: "b19", status: "in_progress",
          ampel: "gruen", priority: 2, last_activity_at: 2000,
          event_count: 2 },
      ],
    }),
  },
  {
    name: "myhistory", datei: "cockpit_myhistory.js",
    global: "AIWCockpitMyHistory", render: "renderMyHistory",
    sicht: "myhistory", zeilen: 3,
    daten: () => ({
      person_id: 2, limit: 200, count: 3, my_case_count: 1,
      events: [
        { seq: 50, ts: 1000, actor_id: 2, event_type: "case_note_set",
          target_type: "case", target_id: "18", mine: true, mycase: true },
        { seq: 40, ts: 900, actor_id: 1, event_type: "case_assigned",
          target_type: "case", target_id: "18", mine: false, mycase: true },
        { seq: 30, ts: 800, actor_id: 2, event_type: "rbac_granted",
          target_type: "grant", target_id: "7", mine: true, mycase: false },
      ],
    }),
  },
  {
    name: "mentoring", datei: "cockpit_mentoring.js",
    global: "AIWCockpitMentoring", render: "renderMentoring",
    sicht: "mentoring", zeilen: 2,
    daten: () => ({
      scope: "alle", stale_sec: 30, count: 2,
      sessions: [
        { id: 7, subject_id: 19, username: "b19", supporter_id: 3,
          supporter_system_username: "h003", supporter_display_name: "Gamma",
          started_at: 1000, last_heartbeat: 1100, heartbeat_age_sec: 150,
          started_ago_sec: 300, live: false },
        { id: 5, subject_id: 18, username: "b18", supporter_id: 2,
          supporter_system_username: "h002", supporter_display_name: "Mueller",
          started_at: 1400, last_heartbeat: 1490, heartbeat_age_sec: 5,
          started_ago_sec: 65, live: true },
      ],
    }),
  },
  {
    name: "personnel", datei: "cockpit_personnel.js",
    global: "AIWCockpitPersonnel", render: "renderPersonnel",
    sicht: "personnel", zeilen: 2, brauchtDoc: true,
    daten: () => ({
      persons: [
        { id: 1, system_username: "h0chef", display_name: "Chefin",
          is_investigator: false, is_supervisor: true, is_support: false,
          is_active: true, roles: [] },
        { id: 2, system_username: "h0erm", display_name: "Mueller",
          is_investigator: true, is_supervisor: false, is_support: false,
          is_active: true, roles: [] },
      ],
      roles_catalog: [{ code: "investigator", label: "Ermittler:in" }],
      actor_person_id: 1, can_edit: true, can_sync: false,
    }),
  },
  // --- Build 550 ------------------------------------------------------------
  // Support: DREI Abschnitte in EINER Sicht, jeder mit eigener Kennung. Sie
  // sind hier als getrennte Eintraege gefuehrt, weil jeder eine eigene
  // Werkzeugleiste, eigene Hilfe-Anker und einen eigenen gesicherten
  // Bedienzustand hat.
  {
    name: "support (meine)", datei: "cockpit_support.js",
    global: "AIWCockpitSupport", render: "renderSupport",
    sicht: "support_mine", zeilen: 2, index: 0,
    daten: () => _supportDaten(),
  },
  {
    name: "support (an meinen Faellen)", datei: "cockpit_support.js",
    global: "AIWCockpitSupport", render: "renderSupport",
    sicht: "support_oncase", zeilen: 1, index: 1,
    daten: () => _supportDaten(),
  },
  {
    name: "policy (Grants)", datei: "cockpit_policy.js",
    global: "AIWCockpitPolicy", render: "renderPolicy",
    sicht: "policy_grants", zeilen: 2, index: 0,
    daten: () => _policyDaten(),
  },
  {
    name: "policy (Zuweisungen)", datei: "cockpit_policy.js",
    global: "AIWCockpitPolicy", render: "renderPolicy",
    sicht: "policy_assign", zeilen: 1, index: 1,
    daten: () => _policyDaten(),
  },
  {
    name: "reports", datei: "cockpit_reports.js",
    global: "AIWCockpitReports", render: "renderReports",
    sicht: "reports", zeilen: 2,
    daten: () => ({
      scope: "alle", evidence_dir: "./data/evidence/", case_db_count: 2,
      rescanned: 0, count: 2,
      reports: [
        { subject_id: 18, username: "b18", id: 1, report_type: "interim",
          sequence_nr: 1, title: "Zwischenbericht", created_by: "h002",
          created_at: 1783000000, status: "submitted", approvals: [] },
        { subject_id: 19, username: "b19", id: 1, report_type: "final",
          sequence_nr: 1, title: "Abschlussbericht", created_by: "h003",
          created_at: 1783100000, status: "approved", approvals: [] },
      ],
    }),
  },
  {
    name: "results", datei: "cockpit_results.js",
    global: "AIWCockpitResults", render: "renderResults",
    sicht: "results", zeilen: 2,
    daten: () => _resultsCov(),
    aufruf: (api, main, opts) => api.renderResults(main, _resultsCov(),
                                                  null, opts),
  },
];

/** Fixtures, die von mehreren Register-Eintraegen geteilt werden. */
function _supportDaten() {
  const S = (o) => Object.assign({
    session_id: 1, subject_id: 18, username: "b18", supporter_id: 2,
    supporter_system_username: "h002", supporter_display_name: "Mueller",
    started_at: 1000, ended_at: 1600, duration_sec: 600,
    end_reason: "closed", mine_as_supporter: false, on_my_case: false,
  }, o);
  return {
    scope: "eigene", count: 3,
    sessions: [
      S({ session_id: 1, mine_as_supporter: true, on_my_case: true }),
      S({ session_id: 2, supporter_id: 3, supporter_display_name: "Gamma",
          mine_as_supporter: false, on_my_case: true }),
      S({ session_id: 3, subject_id: 19, username: "b19",
          mine_as_supporter: true, on_my_case: false }),
    ],
  };
}

function _policyDaten() {
  return {
    scope: "alle",
    roles: [{ code: "supervisor", label: "Chef-Ermittlerin" },
            { code: "investigator", label: "Ermittler:in" }],
    capabilities: [{ code: "policy.view", label: "RBAC-Richtlinie einsehen" },
                   { code: "mycases.view", label: "Eigene Faelle sehen" }],
    grants: [
      { role_code: "supervisor", capability_code: "policy.view",
        scope: "alle", audit_seq: 42, note: "" },
      { role_code: "investigator", capability_code: "mycases.view",
        scope: "eigene", audit_seq: 43, note: "PoC" },
    ],
    assignments: [
      { person_id: 5, system_username: "h0a2898", display_name: "Chefin",
        role_code: "supervisor", audit_seq: 37 },
    ],
    counts: { grants: 2, assignments: 1 },
  };
}

function _resultsCov() {
  return {
    faelle_gesamt: 2, nie_bewertet: 1, n_kriterien: 4, catalog_version: 1,
    vermerk: "PROVISORISCH", scope: "alle",
    summary: { faelle_gesamt: 2, nie_bewertet: 1, voll_bewertet: 0,
               abdeckung_mittel: 0.25 },
    faelle: [
      { subject_id: 20, username: "b20", status: "open", assigned_to: null,
        n_bewertet: 0, n_kriterien: 4, abdeckung: 0.0, n_beste: 0,
        unbewertet: ["identification"], score: 0, hoechste_konfidenz: null,
        zuletzt_bewertet: null, nie_bewertet: true, ampel: "rot" },
      { subject_id: 21, username: "b21", status: "open", assigned_to: 2,
        n_bewertet: 2, n_kriterien: 4, abdeckung: 0.5, n_beste: 1,
        unbewertet: ["abuser"], score: 3, hoechste_konfidenz: "hoch",
        zuletzt_bewertet: 1783000000, nie_bewertet: false, ampel: "gelb" },
    ],
  };
}

function _ctx(datei) {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_tkSrc);
  dom.window.eval(_src(datei));
  return dom.window;
}

function _zeichne(eintrag, win, main, mitTabulator) {
  const api = win[eintrag.global];
  const opts = {};
  if (mitTabulator) { opts.Tabulator = _fakeTabulator(win.document); }
  if (eintrag.brauchtDoc) { opts.doc = win.document; }
  // 'aufruf' fuer Sichten mit abweichender Signatur (renderResults nimmt
  // Abdeckung UND Statistik). Der Regelfall bleibt (main, daten, opts).
  if (typeof eintrag.aufruf === "function") {
    return eintrag.aufruf(api, main, opts);
  }
  return api[eintrag.render](main, eintrag.daten(), opts);
}

/** Die Tabelle einer bestimmten Sicht aus dem Rueckgabewert holen.
 *  Sichten mit MEHREREN Tabellen liefern ein Array; dann entscheidet der
 *  Index im Register. */
function _tabelleVon(eintrag, view) {
  if (Array.isArray(view)) { return view[eintrag.index || 0]; }
  if (view && view.table) { return view.table; }
  return view;
}

describe("Konformitaet der Listensichten (Build 549)", () => {
  REGISTER.forEach((e) => {
    describe(e.name, () => {
      // UX01/UX03 ------------------------------------------------------------
      it("UX01+UX03: Werkzeugleiste mit richtiger Trefferzahl", () => {
        const win = _ctx(e.datei);
        const main = win.document.createElement("div");
        win.document.body.appendChild(main);
        _zeichne(e, win, main, true);

        const leiste = main.querySelector("#aiw-" + e.sicht + "-tk");
        expect(leiste, e.name + ": keine Werkzeugleiste").toBeTruthy();

        const treffer = main.querySelector(
          "#aiw-" + e.sicht + "-tk-treffer"
        );
        expect(treffer).toBeTruthy();
        expect(treffer.textContent).toBe(e.zeilen + " Zeilen");
      });

      // UX02 -----------------------------------------------------------------
      it("UX02: 'Filter zuruecksetzen' ist da und wirkt", () => {
        const win = _ctx(e.datei);
        const main = win.document.createElement("div");
        win.document.body.appendChild(main);
        const view = _zeichne(e, win, main, true);
        const table = _tabelleVon(e, view);

        const knopf = main.querySelector("#aiw-" + e.sicht + "-tk-clear");
        expect(knopf, e.name + ": kein Zuruecksetzen-Knopf").toBeTruthy();
        expect(knopf.textContent).toContain("Filter");

        table.setHeaderFilterValue("x", "y");
        expect(table.getHeaderFilters().length).toBe(1);
        knopf.dispatchEvent(new win.Event("click"));
        expect(table.getHeaderFilters().length).toBe(0);
      });

      // UX04 -----------------------------------------------------------------
      it("UX04: jede Spalte mit Feld traegt einen Kopffilter", () => {
        const win = _ctx(e.datei);
        const main = win.document.createElement("div");
        win.document.body.appendChild(main);
        const view = _zeichne(e, win, main, true);
        const table = _tabelleVon(e, view);

        const cols = table.options.columns || [];
        expect(cols.length).toBeGreaterThan(0);
        const ohne = cols
          .filter((c) => c.field && !c.headerFilter)
          .map((c) => c.field);
        expect(ohne, e.name + ": Spalten ohne Filter").toEqual([]);
      });

      // UX05 -----------------------------------------------------------------
      it("UX05: Hilfe-Anker gesetzt, eindeutig, im Muster", () => {
        const win = _ctx(e.datei);
        const TK = win.AIWTableKit;
        const main = win.document.createElement("div");
        win.document.body.appendChild(main);
        _zeichne(e, win, main, true);

        const ids = TK.hilfeIds(main);
        // Die Werkzeugleiste vergibt sie automatisch — sie MUESSEN da sein.
        expect(ids, e.name).toContain(e.sicht + ".werkzeug.filter_entfernen");
        expect(ids, e.name).toContain(e.sicht + ".werkzeug.trefferzahl");
        // Jeder Anker gehoert zu EINER der Kennungen DIESER Datei. Ein
        // fremdes Praefix waere ein Kopierfehler und spaeter ein falscher
        // Hilfetext.
        //
        // Geprueft wird gegen die Kennungen der DATEI und nicht gegen die
        // eine Kennung des Eintrags: eine Sicht mit mehreren Abschnitten
        // (Support, Policy) zeichnet in einem Durchgang alle Abschnitte und
        // erzeugt damit zwangslaeufig auch deren Anker. Die erste Fassung
        // dieser Pruefung hat genau das uebersehen.
        const erlaubtePraefixe = REGISTER
          .filter((x) => x.datei === e.datei)
          .map((x) => x.sicht);
        ids.forEach((id) => {
          expect(TK.hilfeGueltig(id), e.name + ": " + id).toBe(true);
          expect(
            erlaubtePraefixe.indexOf(id.split(".")[0]) >= 0,
            e.name + ": fremdes Praefix in " + id
          ).toBe(true);
        });
        // EINDEUTIGKEIT GILT NUR FUER DIE WERKZEUGLEISTE. Zeilen- und
        // Spaltenanker wiederholen sich naturgemaess (drei Flag-Kaestchen mal
        // zwei Personen = sechs Vorkommen desselben Ankers) — und das ist
        // richtig so: alle drei Kaestchen bekommen denselben Hilfetext. Eine
        // Leiste, die ihre Anker zweimal vergibt, waere dagegen ein Fehler.
        ["werkzeug.filter_entfernen", "werkzeug.trefferzahl"].forEach((t) => {
          const voll = e.sicht + "." + t;
          const n = ids.filter((x) => x === voll).length;
          expect(n, e.name + ": " + voll + " kommt " + n + "x vor").toBe(1);
        });
      });

      // UX06 -----------------------------------------------------------------
      it("UX06: ohne Tabellenbibliothek — Meldung MIT Anzahl", () => {
        const win = _ctx(e.datei);
        const main = win.document.createElement("div");
        win.document.body.appendChild(main);
        _zeichne(e, win, main, false);   // kein Ctor

        const hinweise = Array.from(
          main.querySelectorAll(".aiw-placeholder")
        ).map((n) => n.textContent);
        expect(hinweise.length, e.name + ": kein Hinweis").toBeGreaterThan(0);
        // ENTSCHEIDEND: die Zahl steht da. Eine leere Flaeche saehe aus wie
        // 'keine Daten vorhanden'.
        //
        // Sichten mit MEHREREN Abschnitten (Support, Policy) erzeugen je
        // Abschnitt einen Hinweis — geprueft wird deshalb, ob IRGENDEINER die
        // erwartete Zahl nennt, nicht der erste.
        const trifft = hinweise.some((t) => t.indexOf(String(e.zeilen)) >= 0);
        expect(trifft, e.name + ": " + JSON.stringify(hinweise)).toBe(true);
      });
    });
  });

  // Übergreifend --------------------------------------------------------------
  it("UX07: das Register ist widerspruchsfrei", () => {
    const namen = REGISTER.map((e) => e.name);
    const sichten = REGISTER.map((e) => e.sicht);
    expect(new Set(namen).size).toBe(namen.length);
    // Zwei Sichten mit derselben Kennung teilten sich Hilfe-Anker UND den
    // gesicherten Bedienzustand — sie wuerden sich gegenseitig ueberschreiben.
    expect(new Set(sichten).size).toBe(sichten.length);
  });
});
