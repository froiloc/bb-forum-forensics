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
import { readFileSync, readdirSync } from "fs";
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
    // Build 551: Tabulator v6 haengt Zeilenklicks ueber .on() an, nicht ueber
    // eine Konstruktoroption. Die Attrappe merkt sich, was registriert wurde.
    this.handler = {};
    this.on = function (ev, fn) { self.handler[ev] = fn; };
  };
}

/** REGISTER der umgebauten Listensichten.
 *  datei/global/render = wie die Sicht heisst und wie sie gezeichnet wird.
 *  sicht  = Kennung (Praefix der Hilfe-Anker, Schluessel der Sicherung).
 *  weiterePraefixe = weitere zulaessige Ankerpraefixe derselben Datei
 *           (Build 592: die Sicht-Kennung aus dem VIEW_CATALOG, wenn die
 *           Tabelle anders heisst als die Sicht).
 *  zeilen = erwartete Zeilenzahl aus 'daten'. */
const REGISTER = [
  {
    name: "overview", datei: "cockpit_overview.js",
    global: "AIWCockpitOverview", render: "renderOverview", sicht: "overview",
    // Build 592 (Baustelle H / H5): Die Datei traegt ZWEI Praefixe. Die
    // Tabellenanker heissen weiterhin 'overview.*' (so heisst die Tabelle
    // seit Build 548, und daran haengt auch der gespeicherte Bedienzustand);
    // die beiden Marken der Sicht selbst — Ueberschrift und Umfangszeile —
    // tragen dagegen die SICHT-Kennung 'faelle' aus dem VIEW_CATALOG, denn
    // sie gehoeren zur Sicht und nicht zur Tabelle. Die Zuordnung beider
    // Praefixe zur Sicht 'faelle' steht in management/help/anker_katalog.py.
    weiterePraefixe: ["faelle"],
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
    name: "support (meine)", zeilenklick: true, datei: "cockpit_support.js",
    global: "AIWCockpitSupport", render: "renderSupport",
    sicht: "support_mine", zeilen: 2, index: 0,
    daten: () => _supportDaten(),
  },
  {
    name: "support (an meinen Faellen)", zeilenklick: true, datei: "cockpit_support.js",
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
    name: "reports", zeilenklick: true, datei: "cockpit_reports.js",
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
  // --- Build 557 ------------------------------------------------------------
  {
    name: "promotion", datei: "cockpit_promotion.js",
    global: "AIWCockpitPromotion", render: "renderPromotion",
    sicht: "promotion", zeilen: 2, brauchtDoc: true,
    ohneFilter: ["aktion"],   // Knoepfe — ein Filter darauf waere sinnlos
    daten: () => ({
      candidate_count: 2,
      counts: { offen: 1, gesichtet: 0, uebernommen: 1,
                zurueckgestellt: 0, fremdzustaendig: 0 },
      statuses: ["gesichtet", "uebernommen", "zurueckgestellt",
                 "fremdzustaendig"],
      candidates: [
        { subject_id: 77, status: "offen", status_label: "offen",
          grund: null, herkunft: null, is_final: false },
        { subject_id: 99, status: "uebernommen",
          status_label: "in Ermittlung uebernommen", grund: "geprüft",
          herkunft: "Forum X", is_final: true },
      ],
      decisions: [],
    }),
  },

  // --- Build 555 ------------------------------------------------------------
  // Kreuzbezug: ERSTE Sicht der Gruppe C — vorher eine handgebaute <table>.
  {
    name: "crossref", datei: "cockpit_crossref.js",
    global: "AIWCockpitCrossref", render: "renderCrossref",
    sicht: "crossref", zeilen: 2, brauchtDoc: true,
    // Die Aktionsspalte traegt Knoepfe — ein Filter darauf waere sinnlos.
    ohneFilter: ["aktion"],
    daten: () => ({
      entries: [
        { id: 2, subject_id: 993008244, real_identity: "Max Mustermann",
          confidence_code: "gesichert", confidence_ordinal: 30,
          basis: "Zahlung", note: null, updated_at: 1700000500 },
        { id: 1, subject_id: 5, real_identity: "Unbekannt A",
          confidence_code: "verdacht", confidence_ordinal: 10, basis: "",
          note: "nur ein Indiz", updated_at: 1700000100 },
      ],
    }),
  },

  // --- Build 554 ------------------------------------------------------------
  // Chef-Freigabe: letzte Sicht der Gruppe B. Wie das Lektorat mit
  // handgesetzten Filtern und Blaetterung.
  {
    name: "approval", zeilenklick: true, ueberGetTable: true,
    datei: "cockpit_approval.js",
    global: "AIWCockpitApproval", render: "renderApproval",
    sicht: "approval", zeilen: 3,
    daten: () => ({
      scope: "alle", count: 3,
      reports: [
        { subject_id: 18, username: "b18", id: 1, report_type: "interim",
          sequence_nr: 1, title: "Zwischenbericht", status: "submitted",
          created_by: "h002", created_at: 1783000000, approvals: [] },
        { subject_id: 19, username: "b19", id: 2, report_type: "final",
          sequence_nr: 3, title: "Abschlussbericht", status: "approved",
          created_by: "h003", created_at: 1783100000, approvals: [] },
        { subject_id: 20, username: "b20", id: 1, report_type: "addendum",
          sequence_nr: 2, title: "Nachtrag", status: "submitted",
          created_by: "h002", created_at: 1783200000, approvals: [] },
      ],
    }),
  },

  // --- Build 553 ------------------------------------------------------------
  // Lektorat: eine der beiden Sichten mit HANDGESETZTEN Filtern (exakter
  // Full-Match beim Typ, Statusfilterung ueber den ROH-Status). UX04 belegt,
  // dass die Automatik sie NICHT ueberschrieben hat — spaltenMitFilter fuellt
  // nur, was nicht ausdruecklich gesetzt ist.
  {
    name: "lectorate", zeilenklick: true, ueberGetTable: true,
    datei: "cockpit_lectorate.js",
    global: "AIWCockpitLectorate", render: "renderLectorate",
    sicht: "lectorate", zeilen: 3,
    daten: () => ({
      scope: "alle", count: 3,
      reports: [
        { subject_id: 18, username: "b18", id: 1, report_type: "interim",
          sequence_nr: 1, title: "Zwischenbericht", status: "submitted" },
        { subject_id: 19, username: "b19", id: 2, report_type: "final",
          sequence_nr: 3, title: "Abschlussbericht", status: "approved" },
        { subject_id: 20, username: "b20", id: 1, report_type: "addendum",
          sequence_nr: 2, title: "Nachtrag", status: "submitted" },
      ],
    }),
  },

  // --- Build 552 ------------------------------------------------------------
  // Statistiken: die Sicht besteht ueberwiegend aus Diagrammen; nur der Reiter
  // 'Ermittler' fuehrt eine Tabelle. Sie bekommt eine eigene Kennung
  // ('stats_assign'), damit spaetere Tabellen in derselben Sicht nicht mit ihr
  // um Hilfe-Anker und Bedienzustand streiten.
  {
    name: "stats (Ermittler)", datei: "cockpit_stats.js",
    global: "AIWCockpitStats", render: "renderStats",
    sicht: "stats_assign", zeilen: 3,
    daten: () => ({
      scope: "alle", generated_at: 1000,
      totals: { cases: 4, assigned: 3, unassigned: 1, events: 12 },
      by_status: { open: 2, in_progress: 1, approved: 1, closed: 0 },
      by_priority: { "1": 0, "2": 1, "3": 3, "4": 0, "5": 0 },
      by_ampel: { gruen: 2, gelb: 1, rot: 1 },
      by_assignee: [
        { person_id: 2, display_name: "Mueller", count: 2 },
        { person_id: 3, display_name: "Gamma", count: 1 },
      ],
      throughput_by_day: [{ day: "2026-07-09", count: 3 }],
    }),
  },

  // --- Build 551 ------------------------------------------------------------
  {
    name: "calendar", zeilenklick: true, datei: "cockpit_calendar.js",
    global: "AIWCockpitCalendar", render: "renderCalendar",
    sicht: "calendar", zeilen: 2,
    // renderCalendar nimmt VIER Argumente: Kalenderraster UND externe
    // Vorgaenge. Deshalb ein eigener Aufruf — die Zeilen der Tabelle stammen
    // aus dem DRITTEN Argument.
    daten: () => _calendarExt(),
    aufruf: (api, main, opts) => api.renderCalendar(
      main, { von: "2026-07-01", bis: "2026-07-31", entries: [] },
      _calendarExt(), Object.assign({ ym: "2026-07" }, opts)
    ),
  },
  {
    name: "results", datei: "cockpit_results.js",
    global: "AIWCockpitResults", render: "renderResults",
    sicht: "results", zeilen: 2,
    daten: () => _resultsCov(),
    aufruf: (api, main, opts) => api.renderResults(main, _resultsCov(),
                                                  null, opts),
  },
  // --- Build 559: Kapazitaetspflege, VIER Tabellen in EINER Sicht ----------
  // Muster 'policy (Grants)'/'policy (Zuweisungen)': eine Datei, ein Render,
  // mehrere Register-Eintraege mit 'index'. Die Sicht liefert ihre Tabellen
  // in 'tables'.
  {
    name: "capacity_pflege (Arbeitszeiten)",
    datei: "cockpit_capacity_pflege.js",
    global: "AIWCockpitCapacityPflege", render: "renderCapacityPflege",
    sicht: "capacity_worktime", zeilen: 2, index: 0,
    daten: () => _cappDaten(),
  },
  {
    name: "capacity_pflege (Abwesenheiten)",
    datei: "cockpit_capacity_pflege.js",
    global: "AIWCockpitCapacityPflege", render: "renderCapacityPflege",
    sicht: "capacity_availability", zeilen: 1, index: 1,
    daten: () => _cappDaten(),
  },
  {
    name: "capacity_pflege (Feiertage)",
    datei: "cockpit_capacity_pflege.js",
    global: "AIWCockpitCapacityPflege", render: "renderCapacityPflege",
    sicht: "capacity_holiday", zeilen: 1, index: 2,
    daten: () => _cappDaten(),
  },
  {
    name: "capacity_pflege (Gruende)",
    datei: "cockpit_capacity_pflege.js",
    global: "AIWCockpitCapacityPflege", render: "renderCapacityPflege",
    sicht: "capacity_reason", zeilen: 2, index: 3,
    daten: () => _cappDaten(),
  },
];

/** Stammdaten-Antwort (GET /api/capacity/stammdaten), scope 'alle'. */
function _cappDaten() {
  return {
    scope: "alle", person_id: null,
    persons: [
      { id: 2, system_username: "h002", display_name: "Mueller" },
      { id: 3, system_username: "h003", display_name: "Gamma" },
    ],
    worktimes: [
      { id: 1, person_id: 2, display_name: "Mueller", system_username: "h002",
        mon_min: 480, tue_min: 480, wed_min: 480, thu_min: 480, fri_min: 480,
        sat_min: 0, sun_min: 0, effective_from: "2026-01-01",
        effective_to: null, audit_seq: 11 },
      { id: 2, person_id: 3, display_name: "Gamma", system_username: "h003",
        mon_min: 300, tue_min: 300, wed_min: 300, thu_min: 300, fri_min: 300,
        sat_min: 0, sun_min: 0, effective_from: "2026-02-01",
        effective_to: null, audit_seq: 12 },
    ],
    availability: [
      { id: 5, person_id: 2, display_name: "Mueller",
        period_start: "2026-07-06", period_end: "2026-07-10",
        kind: "einschraenkung", value_pct: 50, value_minutes: null,
        reason_code: "urlaub", note: "Jahresurlaub", audit_seq: 13 },
    ],
    holidays: [
      { id: 9, day: "2026-07-08", label: "Testfeiertag", region: null,
        audit_seq: 14 },
    ],
    reasons: [
      { code: "urlaub", label: "Urlaub", sort: 10, audit_seq: 15 },
      { code: "krank", label: "Krank", sort: 20, audit_seq: 16 },
    ],
    counts: { worktimes: 2, availability: 1, holidays: 1, reasons: 2,
              persons: 2 },
    kinds: [
      { code: "einschraenkung", label: "Einschraenkung" },
      { code: "garantie", label: "Garantie (Mindestboden)" },
    ],
  };
}

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

function _calendarExt() {
  return {
    scope: "alle", stichtag: "2026-07-26", stichtag_text: "26.07.2026",
    zeitzone: "Europe/Berlin", count: 2,
    counts: { rot: 1, gelb: 1, gruen: 0, neutral: 0 },
    kinds: [{ code: "anfrage", label: "Anfrage" }],
    matters: [
      { id: 1, subject_id: 18, kind: "anfrage", kind_label: "Anfrage",
        betreff: "Auskunft A", adressat: "StA", status: "offen",
        status_label: "Offen", wiedervorlage_am: "2026-07-01",
        ampel: "rot", ampel_grund: "ueberfaellig" },
      { id: 2, subject_id: 19, kind: "anfrage", kind_label: "Anfrage",
        betreff: "Auskunft B", adressat: "StA", status: "offen",
        status_label: "Offen", wiedervorlage_am: "2026-07-27",
        ampel: "gelb", ampel_grund: "faellig" },
    ],
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

/** Sichten mit handgebauter Tabelle, die BEWUSST nicht umgebaut werden.
 *  Jeder Eintrag braucht einen Grund — eine wortlose Ausnahmeliste waere eine
 *  Hintertuer. UX10 haelt die Liste gegen den tatsaechlichen Baumzustand. */
const AUSGENOMMEN = {
  // --- Feste Zeilenmenge, bedeutungstragende Reihenfolge (Regel §2.2) -------
  "cockpit_planung.js":
    "Szenarien-Tabelle der Prognose: forecast.py:98-105 erzeugt IMMER genau " +
    "drei Zeilen (optimistisch/erwartet/pessimistisch). Ein Filter ueber drei " +
    "feste Zeilen grenzt nichts ein, und eine Sortierung zerstoerte die " +
    "Reihenfolge, die die Aussage traegt.",
  "cockpit_onboarding.js":
    "Checkliste mit fester Schrittfolge: checklist_status.py:43-58 friert je " +
    "Art GENAU FUENF Schritte ein. Beim Offboarding ist die Reihenfolge " +
    "fachlich zwingend (Rechte entziehen VOR Zugang sperren, Faelle " +
    "umverteilen VOR dem Sperren). Eine Sortierspalte laedt dazu ein, genau " +
    "diese Ordnung aufzuloesen — bei einer Liste, deren Zweck es ist, " +
    "vergessene Schritte sichtbar zu machen. Zudem zeigt die Sicht immer nur " +
    "EINE Checkliste fuer EINE Person: es gibt nichts zu durchsuchen.",

  // --- Serverseitige Filterung/Blaetterung (Regel §2) -----------------------
  "cockpit_audit.js":
    "Der Audit-Explorer filtert und blaettert SERVERSEITIG " +
    "(/api/audit/facets, offset). Ein client-seitiger Kopffilter durchsuchte " +
    "nur die geladene Seite und meldete '3 Treffer', waehrend auf dem Server " +
    "300 liegen — eine falsche Aussage in einem Beweismittelwerkzeug. Ein " +
    "Umbau braucht zuerst einen serverseitigen Filterweg.",

  // --- Noch offen (Regel erfuellt, Umbau steht aus) -------------------------
  // Diese Eintraege sind KEINE dauerhaften Ausnahmen. Sie stehen hier, damit
  // UX10 greift, und verschwinden mit dem jeweiligen Umbau.
  "cockpit_alias.js":
    "NOCH OFFEN (kein Ausnahmegrund): variable Aliasliste, Umbau steht aus.",
  "cockpit_crossfindings.js":
    "NOCH OFFEN (kein Ausnahmegrund): variable Querfundliste, Umbau steht aus.",
  "cockpit_merge.js":
    "NOCH OFFEN (kein Ausnahmegrund): variable Gruppenliste, Umbau steht aus.",
  "cockpit_releases.js":
    "NOCH OFFEN (kein Ausnahmegrund): wachsende Liste externer Fallfreigaben, " +
    "Umbau steht aus.",
};

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
function _tabelleVon(eintrag, view, win) {
  // Manche Sichten geben ihr Wrapper-Element zurueck und halten die Tabelle im
  // Modulzustand; sie legen sie ueber getTable() offen.
  if (eintrag.ueberGetTable) { return win[eintrag.global].getTable(); }
  if (Array.isArray(view)) { return view[eintrag.index || 0]; }
  if (view && view.table) { return view.table; }
  // Sichten, die mehrere Artefakte zurueckgeben (Statistiken: Diagramme UND
  // Tabellen), liefern ihre Tabellen in einem Feld 'tables'.
  if (view && Array.isArray(view.tables)) {
    return view.tables[eintrag.index || 0];
  }
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
        const table = _tabelleVon(e, view, win);

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
        const table = _tabelleVon(e, view, win);

        const cols = table.options.columns || [];
        expect(cols.length).toBeGreaterThan(0);

        // AUSNAHMEN SIND ZULAESSIG, ABER SIE MUESSEN BENANNT SEIN. Ein Filter
        // auf einer Spalte mit Knoepfen waere sinnlos; eine Spalte, die
        // STILLSCHWEIGEND keinen Filter bekommt, waere dagegen ein Versehen.
        // Deshalb steht die Ausnahme im Register und nicht im Code der Sicht.
        const erlaubtOhne = e.ohneFilter || [];
        const ohne = cols
          .filter((c) => c.field && !c.headerFilter)
          .map((c) => c.field);
        expect(
          ohne.filter((f) => erlaubtOhne.indexOf(f) === -1),
          e.name + ": Spalten ohne Filter"
        ).toEqual([]);

        // Und die Ausnahmeliste ist nicht veraltet: jede genannte Spalte gibt
        // es auch. Sonst bliebe eine Ausnahme stehen, deren Spalte laengst
        // umbenannt wurde — und die naechste Luecke faellt durch.
        const felder = cols.map((c) => c.field);
        erlaubtOhne.forEach((f) => {
          expect(felder.indexOf(f) >= 0, e.name + ": '" + f
            + "' steht in ohneFilter, existiert aber nicht").toBe(true);
        });
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
          .reduce(
            (acc, x) => acc.concat([x.sicht], x.weiterePraefixe || []),
            []);
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

      // UX08 -----------------------------------------------------------------
      it("UX08: kein 'rowClick' in den Konstruktoroptionen", () => {
        const win = _ctx(e.datei);
        const main = win.document.createElement("div");
        win.document.body.appendChild(main);
        const view = _zeichne(e, win, main, true);
        const table = _tabelleVon(e, view, win);

        // ROWCLICK IST IN TABULATOR v6.4.0 KEINE KONSTRUKTOROPTION. Wer ihn
        // dort hineinschreibt, bekommt KEINEN Fehler — der Handler wird
        // schlicht ignoriert und der Zeilenklick tut nichts. Genau so war die
        // Detailansicht der Support-Historie seit Build 367 tot und die
        // Zeilenauswahl der Berichts-Abnahme seit Build 378. Diese Pruefung
        // macht aus dem Wissen eine Zusicherung.
        expect(
          "rowClick" in table.options,
          e.name + ": rowClick gehoert an tabelleAufbauen(opts.onRowClick)"
        ).toBe(false);

        // UX09: und wo ein Zeilenklick VERSPROCHEN wird, muss er auch
        // ankommen. Die blosse Abwesenheit der falschen Option beweist noch
        // nicht, dass der Handler haengt — genau diese Luecke hat den Fehler
        // jahrelang unsichtbar gehalten.
        if (e.zeilenklick) {
          expect(
            typeof table.handler.rowClick,
            e.name + ": kein rowClick-Handler angehaengt"
          ).toBe("function");
        }
      });
    });
  });

  // Übergreifend --------------------------------------------------------------

  // UX10 -----------------------------------------------------------------------
  it("UX10: keine handgebaute Tabelle entkommt unbemerkt", () => {
    // DIE REGEL (Bauplan UX/Tabellen §2.2, Build 556):
    //   Eine Tabelle bekommt Filter und Sortierung nur, wenn ihre Zeilenzahl
    //   VARIABEL ist und ihre Reihenfolge KEINE Aussage traegt. Feste, fachlich
    //   geordnete Zeilenmengen bleiben schlichte <table>.
    //
    // Diese Pruefung macht aus der Regel eine Zusicherung: jede Datei, die noch
    // eine handgebaute Tabelle enthaelt, muss AUSDRUECKLICH ausgenommen sein —
    // mit Grund. Ohne sie bliebe eine uebersehene Sicht einfach liegen und
    // saehe aus wie eine Entscheidung. Verfahren wie _BEWUSST_OHNE_EXPORT beim
    // Akten-Export (VE08).
    const alle = readdirSync("management/server/static")
      .filter((f) => f.startsWith("cockpit_") && f.endsWith(".js"));
    const mitHandtabelle = alle.filter((f) =>
      readFileSync("management/server/static/" + f, "utf-8")
        .indexOf("createElement('table')") >= 0
    );
    expect(mitHandtabelle.length).toBeGreaterThan(0); // sonst greift nichts

    const offen = mitHandtabelle.filter(
      (f) => !Object.prototype.hasOwnProperty.call(AUSGENOMMEN, f)
    );
    expect(
      offen,
      "Handgebaute Tabelle ohne Eintrag in AUSGENOMMEN — entweder umbauen " +
        "oder die Ausnahme begruenden"
    ).toEqual([]);

    // Und die Ausnahmeliste veraltet nicht: eine Datei, die keine Handtabelle
    // mehr hat (weil sie umgebaut wurde), darf nicht als Ausnahme stehen
    // bleiben — sonst deckt der Eintrag spaeter eine neue Luecke zu.
    const veraltet = Object.keys(AUSGENOMMEN).filter(
      (f) => mitHandtabelle.indexOf(f) === -1
    );
    expect(veraltet, "Ausnahme ohne Handtabelle (veraltet)").toEqual([]);

    // Jede Ausnahme traegt einen Grund im Klartext.
    Object.keys(AUSGENOMMEN).forEach((f) => {
      expect(AUSGENOMMEN[f].length, f + " ohne Begruendung").toBeGreaterThan(30);
    });
  });

  it("UX07: das Register ist widerspruchsfrei", () => {
    const namen = REGISTER.map((e) => e.name);
    const sichten = REGISTER.map((e) => e.sicht);
    expect(new Set(namen).size).toBe(namen.length);
    // Zwei Sichten mit derselben Kennung teilten sich Hilfe-Anker UND den
    // gesicherten Bedienzustand — sie wuerden sich gegenseitig ueberschreiben.
    expect(new Set(sichten).size).toBe(sichten.length);
  });
});
