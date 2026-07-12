/**
 * tests/unit/test_cockpit_calendar.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kalender & Wiedervorlage
 *
 * Testsuite fuer management/server/static/cockpit_calendar.js (Build 386).
 * Prueft den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitCalendar).
 *
 * KA01 — API verfuegbar.
 * KA02 — Datumsrechnung: monthRange/shiftMonth ueber Jahres- und
 *        Monatsgrenzen (inkl. Schaltjahr) — UTC-basiert, kein Sommerzeit-Drift.
 * KA03 — gridDays: Montag zuerst, volle Wochen, imMonat korrekt.
 * KA04 — entriesByDay: ein ZEITRAUM erscheint an JEDEM Tag, auf den
 *        Ausschnitt begrenzt; ein ZEITPUNKT nur an seinem Tag.
 * KA05 — outsideOverdue: UEBERFAELLIGES vor dem Monat wird herausgezogen
 *        (sonst waere es beim Blaettern unsichtbar — Grundregel 1).
 * KA06 — availableActions spiegelt MatterStatus; abgeschlossen -> KEINE Aktion.
 * KA07 — deferRequest: OHNE GRUND kein POST (Fehlermeldung statt Anfrage).
 * KA08 — createRequest/closeRequest: Pflichtfelder, kein sicher scheiternder POST.
 * KA09 — render: Stichtagsvermerk, HINWEISE und UEBERFAELLIG-Block erscheinen.
 * KA10 — render: Monatsraster + Chips; Navigation ruft onMonth.
 * KA11 — render: Verschieben ist zweistufig; ohne Grund wird NICHT geschrieben.
 * KA12 — render: Abschluss nennt die Unwiderruflichkeit; Abbrechen schreibt nichts.
 * KA13 — render: ohne external.edit gibt es keine Aktionen (nur Lesen).
 */

import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_calendar.js",
  "utf-8"
);

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api() { return _ctx().AIWCockpitCalendar; }

/** Fake-Tabulator: haelt die Daten und macht rowClick ansteuerbar. */
function _fakeTabulator() {
  return function (container, options) {
    const self = this;
    this.data = options.data;
    this.options = options;
    this.replaceData = function (d) { self.data = d; };
    this.destroy = function () {};
  };
}

function _cal() {
  return {
    von: "2026-07-01",
    bis: "2026-07-31",
    stichtag: "2026-07-12",
    zeitzone: "Europe/Berlin",
    stichtag_text:
      "Faelligkeiten berechnet zum 2026-07-12 (Zeitzone: Europe/Berlin).",
    quellen: [
      { key: "external", label: "Externe Vorgaenge", count: 2, ok: true },
      { key: "availability", label: "Verfuegbarkeit", count: 1, ok: true },
      { key: "holiday", label: "Feiertage", count: 1, ok: true },
    ],
    hinweise: [
      "Abwesenheiten werden NICHT angezeigt: die Faehigkeit 'capacity.edit' fehlt.",
    ],
    count: 4,
    counts: { rot: 1, gelb: 1, gruen: 0, neutral: 2 },
    entries: [
      // UEBERFAELLIG, liegt VOR dem Monat -> darf nicht untergehen.
      { source: "external", ref_id: 2, von: "2026-06-01", bis: "2026-06-01",
        ist_zeitpunkt: true, titel: "Beschluss: Alter Beschluss",
        subject_kind: "case", subject_id: 19, subject_label: "boarder19",
        ampel: "rot", ampel_grund: "Ueberfaellig seit 41 Tag(en).",
        ziel: "external" },
      { source: "external", ref_id: 1, von: "2026-07-16", bis: "2026-07-16",
        ist_zeitpunkt: true, titel: "Bestandsdatenauskunft: Kennung xy",
        subject_kind: "case", subject_id: 18, subject_label: "boarder18",
        ampel: "gelb", ampel_grund: "Faellig in 4 Tag(en) am 2026-07-16.",
        ziel: "external" },
      { source: "availability", ref_id: 7, von: "2026-07-15",
        bis: "2026-07-17", ist_zeitpunkt: false,
        titel: "Einschraenkung 100 % (urlaub)", subject_kind: "person",
        subject_id: 2, subject_label: "Mueller", ampel: "neutral",
        ampel_grund: "", ziel: "capacity" },
      { source: "holiday", ref_id: 3, von: "2026-07-16", bis: "2026-07-16",
        ist_zeitpunkt: true, titel: "Testfeiertag", subject_kind: "global",
        subject_id: null, subject_label: "", ampel: "neutral",
        ampel_grund: "", ziel: "capacity" },
    ],
  };
}

function _ext() {
  return {
    scope: "alle",
    stichtag: "2026-07-12",
    kinds: [
      { code: "bestandsdaten", label: "Bestandsdatenauskunft" },
      { code: "beschluss", label: "Beschluss (StA / Ermittlungsrichter)" },
    ],
    count: 3,
    counts: { rot: 1, gelb: 1, gruen: 0, neutral: 1 },
    matters: [
      { id: 2, user_id: 19, fall_username: "boarder19", kind: "beschluss",
        kind_label: "Beschluss (StA / Ermittlungsrichter)",
        betreff: "Alter Beschluss", adressat: "StA Essen", aktenzeichen: null,
        angefordert_am: "2026-05-01", wiedervorlage_am: "2026-06-01",
        vorwarnfrist_tage: 7, status: "offen", status_label: "offen",
        ergebnis: null, case_status: "in_progress", ampel: "rot",
        ampel_grund: "Ueberfaellig seit 41 Tag(en)." },
      { id: 1, user_id: 18, fall_username: "boarder18",
        kind: "bestandsdaten", kind_label: "Bestandsdatenauskunft",
        betreff: "Kennung xy", adressat: "Telekom AG", aktenzeichen: "Az-1",
        angefordert_am: "2026-07-01", wiedervorlage_am: "2026-07-16",
        vorwarnfrist_tage: 7, status: "beantwortet",
        status_label: "beantwortet", ergebnis: "Auskunft da",
        case_status: "in_progress", ampel: "gelb",
        ampel_grund: "Faellig in 4 Tag(en) am 2026-07-16." },
      { id: 3, user_id: 18, fall_username: "boarder18", kind: "osint",
        kind_label: "OSINT", betreff: "Recherche", adressat: "",
        aktenzeichen: null, angefordert_am: "2026-06-01",
        wiedervorlage_am: "2026-06-20", vorwarnfrist_tage: 7,
        status: "erledigt", status_label: "erledigt", ergebnis: "fertig",
        case_status: "in_progress", ampel: "neutral",
        ampel_grund: "Abgeschlossen (erledigt)." },
    ],
  };
}

function _main(win) {
  const el = win.document.createElement("div");
  win.document.body.appendChild(el);
  return el;
}

describe("cockpit_calendar (Build 386)", () => {
  it("KA01 — API verfuegbar", () => {
    const api = _api();
    expect(typeof api.renderCalendar).toBe("function");
    expect(typeof api.deferRequest).toBe("function");
    expect(typeof api.gridDays).toBe("function");
  });

  it("KA02 — Datumsrechnung ueber Monats-/Jahresgrenzen", () => {
    const api = _api();
    expect(api.monthRange("2026-07")).toEqual({
      von: "2026-07-01", bis: "2026-07-31" });
    // Schaltjahr: 2028 ist eines.
    expect(api.monthRange("2028-02").bis).toBe("2028-02-29");
    expect(api.monthRange("2026-02").bis).toBe("2026-02-28");

    expect(api.shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(api.shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(api.ymOf("2026-07-16")).toBe("2026-07");
    expect(api.monthLabel("2026-07")).toBe("Juli 2026");
  });

  it("KA03 — gridDays: Montag zuerst, volle Wochen", () => {
    const days = _api().gridDays("2026-07");
    // 2026-07-01 ist ein Mittwoch -> 2 Tage Vorlauf (Mo/Di aus Juni).
    expect(days[0].iso).toBe("2026-06-29");
    expect(days[0].imMonat).toBe(false);
    expect(days[2].iso).toBe("2026-07-01");
    expect(days[2].imMonat).toBe(true);
    // Immer volle Wochen.
    expect(days.length % 7).toBe(0);
    // Der letzte Tag des Monats ist enthalten.
    expect(days.some((d) => d.iso === "2026-07-31" && d.imMonat)).toBe(true);
  });

  it("KA04 — entriesByDay: Zeitraum an JEDEM Tag, Zeitpunkt nur an einem", () => {
    const api = _api();
    const map = api.entriesByDay(_cal().entries, "2026-07-01", "2026-07-31");

    // Abwesenheit 15.-17.: an allen drei Tagen (so sieht man, dass der
    // Ermittler am Tag der Wiedervorlage im Urlaub ist).
    expect(map["2026-07-15"].some((e) => e.source === "availability")).toBe(true);
    expect(map["2026-07-16"].some((e) => e.source === "availability")).toBe(true);
    expect(map["2026-07-17"].some((e) => e.source === "availability")).toBe(true);
    expect(map["2026-07-18"]).toBeUndefined();

    // Am 16. treffen Wiedervorlage + Urlaub + Feiertag zusammen — genau das
    // ist der Nutzen der gemeinsamen Sicht.
    expect(map["2026-07-16"]).toHaveLength(3);

    // Der ueberfaellige Eintrag vom 1. Juni liegt AUSSERHALB des Ausschnitts.
    expect(map["2026-06-01"]).toBeUndefined();
  });

  it("KA05 — outsideOverdue zieht Ueberfaelliges heraus", () => {
    const api = _api();
    const alt = api.outsideOverdue(_cal().entries, "2026-07-01");
    expect(alt).toHaveLength(1);
    expect(alt[0].ref_id).toBe(2);
    expect(alt[0].ampel).toBe("rot");

    // Nur ROTES zaehlt: ein gruener Vorgang aus der Vergangenheit gibt es
    // nicht, ein neutraler (abgeschlossener) darf nicht auftauchen.
    const mixed = [
      { ampel: "neutral", bis: "2026-05-01" },
      { ampel: "gelb", bis: "2026-05-01" },
    ];
    expect(api.outsideOverdue(mixed, "2026-07-01")).toHaveLength(0);
  });

  it("KA06 — availableActions spiegelt das Statusmodell", () => {
    const api = _api();
    const kinds = (status) =>
      api.availableActions({ status }, true).map((a) => a.kind);

    // offen: verschieben, beantwortet, ohne Ergebnis abschliessen.
    // 'erledigt' ist hier BEWUSST NICHT dabei (Build 385).
    expect(kinds("offen")).toEqual(["defer", "answer", "erfolglos"]);
    expect(kinds("beantwortet")).toEqual(["defer", "erledigt", "erfolglos"]);

    // Abgeschlossen -> UNWIDERRUFLICH, keine Aktion.
    expect(kinds("erledigt")).toEqual([]);
    expect(kinds("erfolglos")).toEqual([]);

    // Ohne Schreibrecht gar nichts.
    expect(api.availableActions({ status: "offen" }, false)).toEqual([]);
  });

  it("KA07 — deferRequest: OHNE GRUND kein POST", () => {
    const api = _api();
    const bad = api.deferRequest(1, "2026-08-01", "   ");
    expect(bad.error).toContain("Grund ist Pflicht");
    expect(bad.path).toBeUndefined();

    expect(api.deferRequest(1, "", "Grund").error).toContain("datum");

    const ok = api.deferRequest(1, "2026-08-01", "Provider bittet um Frist");
    expect(ok.path).toBe("/api/external/defer");
    expect(ok.body).toEqual({
      matter_id: 1, wiedervorlage_am: "2026-08-01",
      grund: "Provider bittet um Frist" });
  });

  it("KA08 — createRequest/closeRequest: Pflichtfelder", () => {
    const api = _api();
    expect(api.createRequest({}).error).toContain("Fall");
    expect(api.createRequest({ user_id: 18 }).error).toContain("Vorgangsart");
    expect(api.createRequest({ user_id: 18, kind: "osint", betreff: " " })
      .error).toContain("Betreff");
    expect(api.createRequest({ user_id: 18, kind: "osint", betreff: "x" })
      .error).toContain("Wiedervorlagedatum");

    const ok = api.createRequest({
      user_id: "18", kind: "osint", betreff: " Recherche ",
      wiedervorlage_am: "2026-08-01", vorwarnfrist_tage: "3" });
    expect(ok.path).toBe("/api/external/create");
    expect(ok.body.user_id).toBe(18);
    expect(ok.body.betreff).toBe("Recherche");
    expect(ok.body.vorwarnfrist_tage).toBe(3);
    // Unsinnige Frist faellt auf den Standard 7 zurueck.
    expect(api.createRequest({ user_id: 1, kind: "osint", betreff: "x",
      wiedervorlage_am: "2026-08-01", vorwarnfrist_tage: "-5" })
      .body.vorwarnfrist_tage).toBe(7);

    expect(api.closeRequest(1, "quatsch").error).toBeTruthy();
    expect(api.closeRequest(1, "erledigt", "fertig").body)
      .toEqual({ matter_id: 1, status: "erledigt", ergebnis: "fertig" });

    // Der Bestaetigungstext nennt die Unwiderruflichkeit beim Namen.
    expect(api.confirmText("erfolglos", { id: 1, user_id: 18 }))
      .toContain("ENDGUELTIG");
  });

  it("KA09 — render: Stichtag, HINWEISE und UEBERFAELLIG-Block", () => {
    const win = _ctx();
    const api = win.AIWCockpitCalendar;
    const main = _main(win);
    api.renderCalendar(main, _cal(), _ext(), {
      ym: "2026-07", canEdit: true, Tabulator: _fakeTabulator() });

    // Die Rechengrundlage steht sichtbar da.
    expect(main.querySelector("#aiw-cal-stichtag").textContent)
      .toContain("Faelligkeiten berechnet zum 2026-07-12");

    // Der Kalender SAGT, dass er schweigt.
    const hints = main.querySelector("#aiw-cal-hints");
    expect(hints).toBeTruthy();
    expect(hints.textContent).toContain("NICHT vollstaendig");
    expect(hints.textContent).toContain("capacity.edit");

    // UEBERFAELLIG ausserhalb des Monats — der wichtigste Block.
    const od = main.querySelector("#aiw-cal-overdue");
    expect(od).toBeTruthy();
    expect(od.textContent).toContain("UEBERFAELLIGE");
    expect(od.textContent).toContain("2026-06-01");
    expect(od.textContent).toContain("boarder19");
    // Er steht VOR dem Raster.
    const grid = main.querySelector("#aiw-cal-grid");
    expect(od.compareDocumentPosition(grid)
      & win.Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("KA10 — render: Raster, Chips, Monatsnavigation", () => {
    const win = _ctx();
    const api = win.AIWCockpitCalendar;
    const main = _main(win);
    const onMonth = vi.fn();
    api.renderCalendar(main, _cal(), _ext(), {
      ym: "2026-07", canEdit: true, Tabulator: _fakeTabulator(),
      onMonth: onMonth });

    expect(main.querySelector("#aiw-cal-month").textContent).toBe("Juli 2026");

    // Am 16. liegen drei Eintraege (Wiedervorlage, Urlaub, Feiertag).
    const td = main.querySelector('td[data-day="2026-07-16"]');
    expect(td.querySelectorAll(".aiw-cal-chip")).toHaveLength(3);
    expect(td.querySelector(".aiw-a-gelb")).toBeTruthy();

    // Der Stichtag ist markiert.
    expect(main.querySelector('td[data-day="2026-07-12"]')
      .classList.contains("aiw-cal-today")).toBe(true);

    main.querySelector("#aiw-cal-prev")
      .dispatchEvent(new win.Event("click"));
    expect(onMonth).toHaveBeenCalledWith("2026-06");
    main.querySelector("#aiw-cal-next")
      .dispatchEvent(new win.Event("click"));
    expect(onMonth).toHaveBeenCalledWith("2026-08");
    main.querySelector("#aiw-cal-today")
      .dispatchEvent(new win.Event("click"));
    expect(onMonth).toHaveBeenCalledWith("2026-07");
  });

  it("KA11 — Verschieben ist zweistufig; ohne Grund wird NICHT geschrieben", () => {
    const win = _ctx();
    const api = win.AIWCockpitCalendar;
    const main = _main(win);
    const onDefer = vi.fn();

    const view = api.renderCalendar(main, _cal(), _ext(), {
      ym: "2026-07", canEdit: true, Tabulator: _fakeTabulator(),
      onDefer: onDefer });

    // Vorgang 2 (offen) waehlen.
    view.selectRow(api.toMatterRows(_ext())[0]);
    const btn = main.querySelector("#aiw-cal-act-defer");
    expect(btn).toBeTruthy();

    // Stufe 1: Bestaetigung, noch KEIN Schreibvorgang.
    btn.dispatchEvent(new win.Event("click"));
    expect(onDefer).not.toHaveBeenCalled();
    expect(main.querySelector("#aiw-cal-confirm")).toBeTruthy();
    expect(main.querySelector(".aiw-cal-confirm-title").textContent)
      .toContain("audit_log");

    // Stufe 2 OHNE Grund -> Fehlermeldung, KEIN POST.
    main.querySelector("#aiw-cal-defer-grund").value = "";
    main.querySelector("#aiw-cal-confirm-yes")
      .dispatchEvent(new win.Event("click"));
    expect(onDefer).not.toHaveBeenCalled();
    expect(main.querySelector("#aiw-cal-result").textContent)
      .toContain("Grund ist Pflicht");

    // Mit Grund -> POST.
    main.querySelector("#aiw-cal-defer-datum").value = "2026-08-01";
    main.querySelector("#aiw-cal-defer-grund").value = "StA bittet um Frist";
    main.querySelector("#aiw-cal-confirm-yes")
      .dispatchEvent(new win.Event("click"));
    expect(onDefer).toHaveBeenCalledTimes(1);
    expect(onDefer).toHaveBeenCalledWith({
      matter_id: 2, wiedervorlage_am: "2026-08-01",
      grund: "StA bittet um Frist" });
  });

  it("KA12 — Abschluss nennt die Unwiderruflichkeit; Abbrechen schreibt nichts", () => {
    const win = _ctx();
    const api = win.AIWCockpitCalendar;
    const main = _main(win);
    const onClose = vi.fn();

    const view = api.renderCalendar(main, _cal(), _ext(), {
      ym: "2026-07", canEdit: true, Tabulator: _fakeTabulator(),
      onClose: onClose });

    // Vorgang 1 ist 'beantwortet' -> darf 'erledigt' werden.
    const beantwortet = api.toMatterRows(_ext())[1];
    view.selectRow(beantwortet);
    main.querySelector("#aiw-cal-act-erledigt")
      .dispatchEvent(new win.Event("click"));
    expect(main.querySelector(".aiw-cal-confirm-title").textContent)
      .toContain("ENDGUELTIG");

    // Abbrechen -> es wird NICHTS geschrieben.
    main.querySelector("#aiw-cal-confirm-no")
      .dispatchEvent(new win.Event("click"));
    expect(onClose).not.toHaveBeenCalled();
    expect(main.querySelector("#aiw-cal-result").textContent)
      .toContain("Es wurde nichts geschrieben");

    // Erneut, diesmal ausfuehren.
    main.querySelector("#aiw-cal-act-erledigt")
      .dispatchEvent(new win.Event("click"));
    main.querySelector("#aiw-cal-close-erg").value = "ausgewertet";
    main.querySelector("#aiw-cal-confirm-yes")
      .dispatchEvent(new win.Event("click"));
    expect(onClose).toHaveBeenCalledWith({
      matter_id: 1, status: "erledigt", ergebnis: "ausgewertet" });

    // Ein ABGESCHLOSSENER Vorgang bietet KEINE Aktion mehr an.
    view.selectRow(api.toMatterRows(_ext())[2]);   // 'erledigt'
    expect(main.querySelector("#aiw-cal-act-defer")).toBeNull();
    expect(main.querySelector(".aiw-placeholder").textContent)
      .toContain("NEUEN Vorgang");
  });

  it("KA13 — ohne external.edit: nur Lesen", () => {
    const win = _ctx();
    const api = win.AIWCockpitCalendar;
    const main = _main(win);

    const view = api.renderCalendar(main, _cal(), _ext(), {
      ym: "2026-07", canEdit: false, Tabulator: _fakeTabulator() });

    // Kein "Neuer Vorgang".
    expect(main.querySelector("#aiw-cal-new")).toBeNull();

    // Und am Vorgang keine Aktion — mit Begruendung statt stiller Leere.
    view.selectRow(api.toMatterRows(_ext())[0]);
    expect(main.querySelector("#aiw-cal-act-defer")).toBeNull();
    expect(main.querySelector(".aiw-placeholder").textContent)
      .toContain("external.edit");

    // Das Raster und die Warnungen stehen trotzdem.
    expect(main.querySelector("#aiw-cal-grid")).toBeTruthy();
    expect(main.querySelector("#aiw-cal-overdue")).toBeTruthy();
  });
});
