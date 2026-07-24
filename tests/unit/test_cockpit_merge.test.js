/**
 * tests/unit/test_cockpit_merge.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Identitaet (AP-2A/A3)
 *
 * Testsuite fuer management/server/static/cockpit_merge.js (Build 510).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitMerge) —
 * keine Logik-Duplikation (B4-S12: „gruen, aber tot" vermeiden).
 *
 * MS01 — API verfuegbar; CONFIDENCE_FALLBACK deckt die DDL-Menge (dieselbe
 *        Achse wie im Identitaetskatalog M018).
 * MS02 — reine Helfer: entries/confidence/counts/countsText/confidenceLabel/
 *        confidenceClass/statusClass — robust gegen fehlende Felder.
 * MS03 — buildMergePayload parst BEIDE subject_ids streng ('47xy' -> null,
 *        nicht 47: ein falsches Konto waere eine falsche Identitaetsaussage).
 * MS04 — validateMerge deckt alle Pflichtfelder ab, inkl. Selbstverschmelzung.
 * MS05 — groupText: eine echte Gruppe wird benannt; ein Konto OHNE Gruppe ist
 *        ein BEFUND ("keiner Gruppe zugeordnet"), kein Leerbefund.
 * MS06 — Rendern: Tabelle, Konfidenz-Badge, Statusklassen; getrennte Zeile
 *        zeigt Grund und Zeitpunkt; Formular nur mit canEdit.
 * MS07 — Aktionen sind statusabhaengig (aktiv: Revidieren/Trennen; getrennt:
 *        Zurücknehmen); Trennen verlangt einen Grund im UI; Revidieren
 *        verlangt eine nicht-leere Basis.
 * MS08 — XSS: Basis und Trennungsgrund landen als TEXT, nicht als DOM;
 *        Ladefehler ist kein Leerbefund.
 *
 * Version: v0.8.510 · Build: 510 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/cockpit_merge.js", "utf-8");

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api() {
  return _win().AIWCockpitMerge;
}
function _mount(win) {
  const el = win.document.createElement("div");
  win.document.body.appendChild(el);
  return el;
}
function _data(over) {
  return Object.assign(
    {
      entries: [
        {
          id: 1,
          primary_subject_id: 4711,
          merged_subject_id: 90210,
          basis: "Schreibstil + Zeitmuster",
          confidence_code: "wahrscheinlich",
          confidence_ordinal: 20,
          is_active: true,
          split_reason: null,
          merged_by: 1,
          split_by: null,
          created_at: 1700000000,
          updated_at: 1700000100,
          split_at: null,
          audit_seq: 7,
          created_audit_seq: 7,
        },
        {
          id: 2,
          primary_subject_id: 4711,
          merged_subject_id: 555,
          basis: "gleiche IP",
          confidence_code: "verdacht",
          confidence_ordinal: 10,
          is_active: false,
          split_reason: "Bestandsauskunft war fehlerhaft",
          merged_by: 1,
          split_by: 1,
          created_at: 1700000000,
          updated_at: 1700000300,
          split_at: 1700000300,
          audit_seq: 9,
          created_audit_seq: 8,
        },
      ],
      counts: { total: 2, aktiv: 1, getrennt: 1, konten: 2 },
      confidence: [
        { code: "verdacht", label: "Verdacht", ordinal: 10 },
        { code: "wahrscheinlich", label: "wahrscheinlich", ordinal: 20 },
        { code: "gesichert", label: "gesichert", ordinal: 30 },
      ],
      mode: "all",
    },
    over || {}
  );
}

describe("cockpit_merge.js (Build 510, AP-2A/A3)", () => {
  // MS01 ---------------------------------------------------------------------
  it("MS01: API verfuegbar, Konfidenz-Fallback deckt die DDL-Menge", () => {
    const api = _api();
    expect(typeof api.renderMerge).toBe("function");
    // Deckungsgleich mit _CONFIDENCE (subject_merge_repo.py), der CHECK in
    // m025 UND der Achse aus M018 — eine zweite Skala waere eine Fehlerquelle.
    expect(api.CONFIDENCE_FALLBACK.map((c) => c.code)).toEqual([
      "verdacht",
      "wahrscheinlich",
      "gesichert",
    ]);
    expect(api.CONFIDENCE_FALLBACK.map((c) => c.ordinal)).toEqual([10, 20, 30]);
  });

  // MS02 ---------------------------------------------------------------------
  it("MS02: reine Helfer sind robust gegen fehlende Felder", () => {
    const api = _api();
    expect(api.entries(null)).toEqual([]);
    expect(api.entries({ entries: "nope" })).toEqual([]);
    expect(api.confidence({}).length).toBe(3);
    expect(api.confidence({ confidence: [{ code: "x", label: "X" }] }).length)
      .toBe(1);
    expect(api.counts(null)).toEqual({
      total: 0,
      aktiv: 0,
      getrennt: 0,
      konten: 0,
    });
    expect(api.countsText(_data())).toContain("1 aktive");
    expect(api.countsText(_data())).toContain("1 getrennt");

    expect(api.confidenceLabel("gesichert")).toBe("gesichert");
    expect(api.confidenceLabel("gibtsnicht")).toBe("gibtsnicht");
    // Dieselben Badge-Klassen wie in der Kreuzbezug-Sicht.
    expect(api.confidenceClass("gesichert")).toBe("aiw-conf-gesichert");
    expect(api.confidenceClass("quatsch")).toBe("aiw-conf-unbekannt");
    expect(api.statusClass(true)).toBe("aiw-merge-aktiv");
    expect(api.statusClass(false)).toBe("aiw-merge-getrennt");
    expect(api.fmtTs(0)).toBe("—");
  });

  // MS03 ---------------------------------------------------------------------
  it("MS03: buildMergePayload parst BEIDE subject_ids streng", () => {
    const api = _api();
    const ok = api.buildMergePayload({
      primary_subject_id: " 4711 ",
      merged_subject_id: "90210",
      basis: "  Indizien  ",
      confidence_code: "verdacht",
    });
    expect(ok.primary_subject_id).toBe(4711);
    expect(ok.merged_subject_id).toBe(90210);
    expect(ok.basis).toBe("Indizien");

    // Der entscheidende Fall: parseInt('47xy') waere 47 — ein FALSCHES Konto
    // und damit eine falsche Identitaetsaussage.
    expect(
      api.buildMergePayload({ primary_subject_id: "47xy" }).primary_subject_id
    ).toBeNull();
    expect(
      api.buildMergePayload({ merged_subject_id: "9 0" }).merged_subject_id
    ).toBeNull();
    expect(api.buildMergePayload({}).primary_subject_id).toBeNull();
  });

  // MS04 ---------------------------------------------------------------------
  it("MS04: validateMerge deckt alle Pflichtfelder ab", () => {
    const api = _api();
    expect(api.validateMerge(null)).toMatch(/Primärkonto/);
    expect(
      api.validateMerge({ primary_subject_id: 1, merged_subject_id: null })
    ).toMatch(/Einzugliederndes/);
    // Selbstverschmelzung wird schon im Browser abgefangen.
    expect(
      api.validateMerge({ primary_subject_id: 5, merged_subject_id: 5 })
    ).toMatch(/mit sich selbst/);
    expect(
      api.validateMerge({
        primary_subject_id: 1,
        merged_subject_id: 2,
        basis: "",
      })
    ).toMatch(/Basis ist Pflicht/);
    expect(
      api.validateMerge({
        primary_subject_id: 1,
        merged_subject_id: 2,
        basis: "x",
        confidence_code: "",
      })
    ).toMatch(/Konfidenz/);
    expect(
      api.validateMerge({
        primary_subject_id: 1,
        merged_subject_id: 2,
        basis: "x",
        confidence_code: "verdacht",
      })
    ).toBeNull();
  });

  // MS05 ---------------------------------------------------------------------
  it("MS05: groupText benennt Gruppe bzw. Nicht-Zugehoerigkeit", () => {
    const api = _api();
    expect(
      api.groupText({
        primary_subject_id: 4711,
        members: [4711, 90210, 555],
        queried_subject_id: 90210,
      })
    ).toContain("Primärkonto 4711");

    // Ein Konto ohne Gruppe ist ein BEFUND, kein Leerbefund.
    const allein = api.groupText({
      primary_subject_id: 999,
      members: [999],
      queried_subject_id: 999,
    });
    expect(allein).toContain("999");
    expect(allein).toContain("keiner Identitäts-Gruppe");
    expect(api.groupText(null)).toBe("");
  });

  // MS06 ---------------------------------------------------------------------
  it("MS06: Tabelle, Badges, Statusklassen, Rechteabhaengigkeit", () => {
    const win = _win();
    const api = win.AIWCockpitMerge;

    const el = _mount(win);
    api.renderMerge(el, _data({ include_split: true }), {
      doc: win.document,
      canEdit: true,
    });
    const rows = el.querySelectorAll("tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0].className).toBe("aiw-merge-aktiv");
    expect(rows[1].className).toBe("aiw-merge-getrennt");
    // Konfidenz-Badge nutzt die geteilten .aiw-conf-*-Klassen.
    expect(
      rows[0].querySelector(".aiw-conf-wahrscheinlich")
    ).toBeTruthy();
    // Trennungsgrund UND Zeitpunkt stehen sichtbar in der Zeile.
    expect(rows[1].textContent).toContain("Bestandsauskunft war fehlerhaft");
    expect(rows[1].textContent).toContain("getrennt am");

    // Ohne canEdit: kein Formular, kein Knopf, dafuer der Rechtehinweis.
    const el2 = _mount(win);
    api.renderMerge(el2, _data(), { doc: win.document });
    expect(el2.querySelector("#aiw-merge-add")).toBeNull();
    expect(el2.querySelector(".aiw-merge-readonly")).toBeTruthy();
    expect(el2.querySelectorAll(".aiw-merge-split").length).toBe(0);

    // Leerbefund unterscheidet Gesamtliste und Gruppenabfrage.
    const el3 = _mount(win);
    api.renderMerge(el3, { entries: [], counts: {} }, { doc: win.document });
    expect(el3.querySelector(".aiw-placeholder").textContent).toBe(
      "Noch keine Zusammenführung erfasst."
    );
    const el4 = _mount(win);
    api.renderMerge(
      el4,
      { entries: [], counts: {} },
      { doc: win.document, query: "4711" }
    );
    expect(el4.querySelector(".aiw-placeholder").textContent).toBe(
      "Keine Zusammenführung für dieses Konto."
    );
  });

  // MS07 ---------------------------------------------------------------------
  it("MS07: statusabhaengige Aktionen mit Pflichtfeld-Abfang", () => {
    const win = _win();
    const api = win.AIWCockpitMerge;
    const el = _mount(win);
    const splits = [];
    const revs = [];
    api.renderMerge(el, _data(), {
      doc: win.document,
      canEdit: true,
      onSplit: (b) => splits.push(b),
      onRevise: (b) => revs.push(b),
    });

    const rows = el.querySelectorAll("tbody tr");
    // aktiv -> Revidieren + Trennen, kein Zurücknehmen
    expect(rows[0].querySelector(".aiw-merge-revise")).toBeTruthy();
    expect(rows[0].querySelector(".aiw-merge-split")).toBeTruthy();
    expect(rows[0].querySelector(".aiw-merge-remerge")).toBeNull();
    // getrennt -> nur Zurücknehmen
    expect(rows[1].querySelector(".aiw-merge-remerge")).toBeTruthy();
    expect(rows[1].querySelector(".aiw-merge-split")).toBeNull();

    // Trennen ohne Grund -> kein Aufruf, sichtbare Meldung.
    rows[0].querySelector(".aiw-merge-split").click();
    const reasonRow = el.querySelector(".aiw-merge-reasonrow");
    reasonRow.querySelector(".aiw-merge-split-go").click();
    expect(splits.length).toBe(0);
    const res = el.querySelector("#aiw-merge-result");
    expect(res.textContent).toMatch(/Grund ist Pflicht/);
    expect(res.classList.contains("error")).toBe(true);
    // Mit Grund -> genau ein Aufruf.
    reasonRow.querySelector(".aiw-merge-reason").value = "  Irrtum  ";
    reasonRow.querySelector(".aiw-merge-split-go").click();
    expect(splits).toEqual([{ merge_id: 1, reason: "Irrtum" }]);

    // Revidieren mit geleerter Basis -> abgefangen.
    rows[0].querySelector(".aiw-merge-revise").click();
    const editRow = el.querySelector(".aiw-merge-editrow");
    editRow.querySelector(".aiw-merge-edit-basis").value = "   ";
    editRow.querySelector(".aiw-merge-edit-save").click();
    expect(revs.length).toBe(0);
    expect(el.querySelector("#aiw-merge-result").textContent).toMatch(
      /Basis darf nicht geleert werden/
    );
    // Mit Basis -> Aufruf mit gewaehlter Konfidenz.
    editRow.querySelector(".aiw-merge-edit-basis").value = "neue Indizien";
    editRow.querySelector(".aiw-merge-edit-conf").value = "gesichert";
    editRow.querySelector(".aiw-merge-edit-save").click();
    expect(revs).toEqual([
      { merge_id: 1, confidence_code: "gesichert", basis: "neue Indizien" },
    ]);
  });

  // MS08 ---------------------------------------------------------------------
  it("MS08: XSS-sicher; Ladefehler ist kein Leerbefund", () => {
    const win = _win();
    const api = win.AIWCockpitMerge;

    const d = _data();
    d.entries[0].basis = '<img src=x onerror="alert(1)">Indiz';
    d.entries[1].split_reason = "<script>alert(2)</script>";
    const el = _mount(win);
    api.renderMerge(el, d, { doc: win.document, canEdit: true });
    expect(el.querySelector("img")).toBeNull();
    expect(el.querySelector("script")).toBeNull();
    expect(el.textContent).toContain('<img src=x onerror="alert(1)">Indiz');

    const el2 = _mount(win);
    api.renderMerge(el2, { error: "HTTP 500" }, { doc: win.document });
    const err = el2.querySelector(".aiw-merge-error");
    expect(err).toBeTruthy();
    expect(err.textContent).toContain("HTTP 500");
    // ... und ausdruecklich NICHT der harmlose "noch keine"-Text.
    expect(el2.querySelector(".aiw-placeholder")).toBeNull();
    expect(el2.querySelector("table")).toBeNull();
  });
});
