/**
 * tests/unit/test_cockpit_crossfindings.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Querfunde (AP-2A)
 *
 * Testsuite fuer management/server/static/cockpit_crossfindings.js (Build 478).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitCrossfindings).
 *
 * QF01 — API verfuegbar.
 * QF02 — reine Helfer: statusLabel/statusClass, findings(), fmtTs().
 * QF03 — mit Funden: counts-Kopf, Tabelle, Status-Badge-Klasse.
 * QF04 — echter Leerbefund: „Keine Querfunde" / „Keine offenen Querfunde".
 * QF05 — Fehlerzustand ({error}): Meldung, KEINE Tabelle (Grundregel 1).
 * QF06 — Steuerung: Checkbox spiegelt onlyOpen; Toggle/Aktualisieren -> onReload.
 * QF07 — XSS-sicher; nicht zuordenbarer Ermittler (source_name null) -> iid.
 *
 * BUILD 508 (Rueckkanal, Idee 7):
 * QF08 — reine Rueckkanal-Helfer: feedbackLabel/feedbackClass/allowedNext/
 *        feedbackCountsText (inkl. Robustheit gegen fehlende Felder).
 * QF09 — Rueckkanal-Spalte: Badge, Entscheider und Begruendung sichtbar;
 *        Zeilenklasse nach Zustand.
 * QF10 — Aktion nur mit canEdit; ein Endzustand bietet KEINE Aktion an; fehlt
 *        allowed_next (alter Server), wird auch nichts angeboten statt geraten.
 * QF11 — die Auswahl enthaelt AUSSCHLIESSLICH die vom Server gelieferten
 *        Folgezustaende — das Frontend erfindet keine Uebergaenge.
 * QF12 — das Pflichtfeld erscheint/verschwindet zustandsabhaengig und traegt
 *        die richtige Beschriftung (Basis vs. Grund).
 * QF13 — Entscheidung ohne Pflichtangabe wird im UI abgefangen (kein
 *        onDecide); mit Angabe -> genau ein Aufruf mit den erwarteten Feldern.
 * QF14 — zweiter Filter „nur unquittierte" spiegelt den Zustand und liefert
 *        BEIDE Filterwerte an onReload.
 *
 * Version: v0.8.508 · Build: 508 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_crossfindings.js",
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
function _mount(win) {
  const el = win.document.createElement("div");
  win.document.body.appendChild(el);
  return el;
}
// Vom Server geliefertes allowed_next fuer einen noch offenen Fund.
const _NEXT_OFFEN = [
  { code: "zugestellt", label: "zugestellt (Kenntnisnahme ausstehend)",
    reason_required: false, reason_meaning: "" },
  { code: "quittiert", label: "quittiert (zur Kenntnis genommen)",
    reason_required: false, reason_meaning: "" },
  { code: "verwertet", label: "verwertet",
    reason_required: true,
    reason_meaning: "Basis (wo ist die Erkenntnis eingeflossen?)" },
  { code: "nicht_relevant", label: "nicht relevant",
    reason_required: true,
    reason_meaning: "Grund (warum traegt der Fund nicht?)" },
];

function _data() {
  return {
    counts: { total: 2, offen: 1, integriert: 1 },
    feedback_counts: { offen: 1, zugestellt: 0, quittiert: 0, verwertet: 1,
                       nicht_relevant: 0, gesamt: 2 },
    findings: [
      { id: 2, subject_id: 800, source_iid: 1, source_name: "Chefin",
        has_case: true, annotation_local_id: "a1", db_path: "/x/e1.db",
        created_at: 1700000000, integrated_at: null, status: "offen",
        feedback_status: "offen", feedback_label: "offen (noch nicht quittiert)",
        feedback_final: false, feedback_reason: null, decided_by: null,
        decided_name: null, decided_at: null, allowed_next: _NEXT_OFFEN },
      { id: 1, subject_id: 801, source_iid: 9, source_name: null,
        has_case: false, annotation_local_id: "a2", db_path: "/x/e2.db",
        created_at: 1700000100, integrated_at: 1700000500,
        status: "integriert",
        feedback_status: "verwertet", feedback_label: "verwertet",
        feedback_final: true, feedback_reason: "Vermerk 7, Bl. 214",
        decided_by: 1, decided_name: "Chefin", decided_at: 1700000600,
        allowed_next: [] },
    ],
  };
}

describe("cockpit_crossfindings", () => {
  // QF01 --------------------------------------------------------------------
  it("QF01: API-Oberflaeche vorhanden", () => {
    const api = _win().AIWCockpitCrossfindings;
    expect(api).toBeTruthy();
    ["statusLabel", "statusClass", "findings", "fmtTs",
     "renderCrossfindings"].forEach((fn) => {
      expect(typeof api[fn]).toBe("function");
    });
  });

  // QF02 --------------------------------------------------------------------
  it("QF02: reine Helfer", () => {
    const api = _win().AIWCockpitCrossfindings;
    expect(api.statusLabel("offen")).toBe("offen");
    expect(api.statusLabel("integriert")).toBe("integriert");
    expect(api.statusClass("offen")).toBe("aiw-cf-offen");
    expect(api.statusClass("integriert")).toBe("aiw-cf-integriert");
    expect(api.statusClass("xyz")).toBe("aiw-cf-unbekannt");
    expect(api.findings(null)).toEqual([]);
    expect(api.findings({ findings: [{ id: 1 }] }).length).toBe(1);
    expect(api.fmtTs(0)).toBe("—");
    expect(typeof api.fmtTs(1700000000)).toBe("string");
  });

  // QF03 --------------------------------------------------------------------
  it("QF03: Funde -> counts-Kopf, Tabelle, Badge-Klasse", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    api.renderCrossfindings(el, _data(), { doc: win.document });

    expect(el.querySelector(".aiw-cf-counts").textContent).toContain("offen: 1");
    expect(el.querySelector(".aiw-cf-counts").textContent)
      .toContain("gesamt: 2");
    const rows = el.querySelectorAll(".aiw-cf-table tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0].querySelector(".aiw-cf-badge").className)
      .toContain("aiw-cf-offen");
    expect(rows[0].getAttribute("data-subject")).toBe("800");
    expect(rows[1].querySelector(".aiw-cf-badge").className)
      .toContain("aiw-cf-integriert");
  });

  // QF04 --------------------------------------------------------------------
  it("QF04: echter Leerbefund", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;

    const el1 = _mount(win);
    api.renderCrossfindings(el1, { counts: { total: 0, offen: 0, integriert: 0 },
      findings: [] }, { doc: win.document, onlyOpen: false });
    expect(el1.querySelector(".aiw-cf-table")).toBeNull();
    expect(el1.querySelector(".aiw-placeholder").textContent)
      .toBe("Keine Querfunde.");

    const el2 = _mount(win);
    api.renderCrossfindings(el2, { counts: { total: 0, offen: 0, integriert: 0 },
      findings: [] }, { doc: win.document, onlyOpen: true });
    expect(el2.querySelector(".aiw-placeholder").textContent)
      .toBe("Keine offenen Querfunde.");
  });

  // QF05 --------------------------------------------------------------------
  it("QF05: Fehlerzustand zeigt Meldung, KEINE Tabelle (Grundregel 1)", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    api.renderCrossfindings(el, { error: "crossfindings_unavailable" },
      { doc: win.document });
    expect(el.querySelector(".aiw-cf-table")).toBeNull();
    expect(el.querySelector(".aiw-placeholder")).toBeNull();
    const err = el.querySelector(".aiw-cf-result.error");
    expect(err).toBeTruthy();
    expect(err.textContent).toContain("nicht verfügbar");
  });

  // QF06 --------------------------------------------------------------------
  it("QF06: Steuerung spiegelt onlyOpen und loest onReload aus", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const doc = win.document;
    const el = _mount(win);
    const calls = [];
    api.renderCrossfindings(el, _data(), {
      doc, onlyOpen: true, onReload: (v) => calls.push(v),
    });

    const cb = doc.getElementById("aiw-cf-onlyopen");
    expect(cb.checked).toBe(true); // spiegelt onlyOpen
    cb.checked = false;
    cb.dispatchEvent(new win.Event("change"));
    expect(calls[calls.length - 1]).toBe(false);

    doc.getElementById("aiw-cf-refresh").click();
    expect(calls.length).toBe(2);
  });

  // QF07 --------------------------------------------------------------------
  it("QF07: XSS-sicher; nicht zuordenbarer Ermittler -> iid", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    const evil = '<img src=x onerror=alert(1)>';
    api.renderCrossfindings(el, {
      counts: { total: 1, offen: 1, integriert: 0 },
      findings: [{ id: 1, subject_id: 5, source_iid: 42, source_name: evil,
        created_at: 1700000000, integrated_at: null, status: "offen" }],
    }, { doc: win.document });
    expect(el.querySelector("img")).toBeNull();      // kein Markup
    expect(el.textContent).toContain(evil);          // als Text

    // source_name null -> "iid 42" (Zeile bleibt aussagekraeftig).
    const el2 = _mount(win);
    api.renderCrossfindings(el2, {
      counts: { total: 1, offen: 1, integriert: 0 },
      findings: [{ id: 1, subject_id: 5, source_iid: 42, source_name: null,
        created_at: 1700000000, integrated_at: null, status: "offen" }],
    }, { doc: win.document });
    expect(el2.textContent).toContain("iid 42");
  });

  // ======================= Build 508 — Rueckkanal ==========================

  // QF08 --------------------------------------------------------------------
  it("QF08: reine Rueckkanal-Helfer sind robust", () => {
    const api = _win().AIWCockpitCrossfindings;
    expect(api.feedbackLabel("nicht_relevant")).toBe("nicht relevant");
    expect(api.feedbackLabel("quatsch")).toBe("quatsch");
    expect(api.feedbackLabel(null)).toBe("");

    expect(api.feedbackClass("offen")).toBe("aiw-cff-offen");
    expect(api.feedbackClass("verwertet")).toBe("aiw-cff-verwertet");
    expect(api.feedbackClass("nicht_relevant")).toBe("aiw-cff-nichtrelevant");
    expect(api.feedbackClass("quatsch")).toBe("aiw-cff-unbekannt");

    // Fehlt allowed_next (alter Server), wird NICHTS geraten.
    expect(api.allowedNext(null)).toEqual([]);
    expect(api.allowedNext({})).toEqual([]);
    expect(api.allowedNext({ allowed_next: "nope" })).toEqual([]);
    expect(api.allowedNext({ allowed_next: _NEXT_OFFEN }).length).toBe(4);

    // Ohne feedback_counts KEINE erfundene Nullzeile.
    expect(api.feedbackCountsText({})).toBe("");
    expect(api.feedbackCountsText(_data())).toContain("offen: 1");
    expect(api.feedbackCountsText(_data())).toContain("verwertet: 1");
  });

  // QF09 --------------------------------------------------------------------
  it("QF09: Rueckkanal-Spalte zeigt Stand, Entscheider und Begruendung", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    api.renderCrossfindings(el, _data(), { doc: win.document, canEdit: true });

    const rows = el.querySelectorAll("tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0].className).toBe("aiw-cff-offen");
    expect(rows[1].className).toBe("aiw-cff-verwertet");

    // Der Server-Label gewinnt vor dem lokalen Rueckfall.
    expect(rows[0].textContent).toContain("offen (noch nicht quittiert)");
    // Entscheider und Begruendung stehen sichtbar in der Zeile.
    expect(rows[1].textContent).toContain("Chefin");
    expect(rows[1].querySelector(".aiw-cff-reason").textContent).toBe(
      "Vermerk 7, Bl. 214"
    );
    // Rueckkanal-Kopfzeile ist da.
    expect(el.querySelector(".aiw-cff-counts")).toBeTruthy();
  });

  // QF10 --------------------------------------------------------------------
  it("QF10: Aktion nur mit canEdit, nie im Endzustand, nie geraten", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;

    // ohne canEdit: gar keine Aktion
    const el1 = _mount(win);
    api.renderCrossfindings(el1, _data(), { doc: win.document });
    expect(el1.querySelectorAll(".aiw-cff-decide").length).toBe(0);

    // mit canEdit: nur die offene Zeile bekommt eine Aktion
    const el2 = _mount(win);
    api.renderCrossfindings(el2, _data(), { doc: win.document, canEdit: true });
    const rows = el2.querySelectorAll("tbody tr");
    expect(rows[0].querySelector(".aiw-cff-decide")).toBeTruthy();
    expect(rows[1].querySelector(".aiw-cff-decide")).toBeNull();
    expect(rows[1].textContent).toContain("abgeschlossen");

    // fehlt allowed_next (alter Server), wird NICHTS angeboten
    const d = _data();
    delete d.findings[0].allowed_next;
    const el3 = _mount(win);
    api.renderCrossfindings(el3, d, { doc: win.document, canEdit: true });
    expect(el3.querySelectorAll(".aiw-cff-decide").length).toBe(0);
  });

  // QF11 --------------------------------------------------------------------
  it("QF11: Auswahl enthaelt NUR die Server-Folgezustaende", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    api.renderCrossfindings(el, _data(), { doc: win.document, canEdit: true });

    el.querySelector(".aiw-cff-decide").click();
    const sel = el.querySelector(".aiw-cff-target");
    expect(sel).toBeTruthy();
    const codes = Array.from(sel.options).map((o) => o.value);
    expect(codes).toEqual([
      "zugestellt",
      "quittiert",
      "verwertet",
      "nicht_relevant",
    ]);
    // 'offen' ist kein Ziel und darf nicht auftauchen.
    expect(codes).not.toContain("offen");
    // Die Beschriftung kommt vom Server.
    expect(sel.options[1].textContent).toBe("quittiert (zur Kenntnis genommen)");
  });

  // QF12 --------------------------------------------------------------------
  it("QF12: Pflichtfeld erscheint zustandsabhaengig mit richtiger Beschriftung",
     () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    api.renderCrossfindings(el, _data(), { doc: win.document, canEdit: true });
    el.querySelector(".aiw-cff-decide").click();

    const sel = el.querySelector(".aiw-cff-target");
    const lbl = el.querySelector(".aiw-cff-reasonlbl");

    // 'zugestellt' (Vorauswahl) verlangt nichts -> Feld ausgeblendet.
    expect(sel.value).toBe("zugestellt");
    expect(lbl.style.display).toBe("none");

    // 'verwertet' verlangt die BASIS.
    sel.value = "verwertet";
    sel.dispatchEvent(new win.Event("change"));
    expect(lbl.style.display).toBe("");
    expect(lbl.textContent).toContain("Basis");

    // 'nicht_relevant' verlangt den GRUND.
    sel.value = "nicht_relevant";
    sel.dispatchEvent(new win.Event("change"));
    expect(lbl.textContent).toContain("Grund");

    // zurueck auf 'quittiert' -> wieder ausgeblendet.
    sel.value = "quittiert";
    sel.dispatchEvent(new win.Event("change"));
    expect(lbl.style.display).toBe("none");
  });

  // QF13 --------------------------------------------------------------------
  it("QF13: fehlende Pflichtangabe wird im UI abgefangen", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    const calls = [];
    api.renderCrossfindings(el, _data(), {
      doc: win.document,
      canEdit: true,
      onDecide: (b) => calls.push(b),
    });
    el.querySelector(".aiw-cff-decide").click();

    const sel = el.querySelector(".aiw-cff-target");
    sel.value = "nicht_relevant";
    sel.dispatchEvent(new win.Event("change"));

    // Ohne Grund: KEIN Serveraufruf, aber eine sichtbare Meldung.
    el.querySelector(".aiw-cff-decide-go").click();
    expect(calls.length).toBe(0);
    const res = el.querySelector("#aiw-cff-result");
    expect(res.textContent).toMatch(/Pflichtangabe fehlt/);
    expect(res.classList.contains("error")).toBe(true);

    // Mit Grund: genau ein Aufruf, Felder wie erwartet.
    el.querySelector(".aiw-cff-reasoninput").value = "  Namensdoppel  ";
    el.querySelector(".aiw-cff-decide-go").click();
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({
      finding_id: 2,
      status_code: "nicht_relevant",
      reason: "Namensdoppel",
    });

    // Ein Zustand OHNE Pflichttext geht auch ohne Eingabe durch.
    const el2 = _mount(win);
    const calls2 = [];
    api.renderCrossfindings(el2, _data(), {
      doc: win.document,
      canEdit: true,
      onDecide: (b) => calls2.push(b),
    });
    el2.querySelector(".aiw-cff-decide").click();
    el2.querySelector(".aiw-cff-decide-go").click();
    expect(calls2.length).toBe(1);
    expect(calls2[0].status_code).toBe("zugestellt");
    expect(calls2[0].reason).toBe("");
  });

  // QF14 --------------------------------------------------------------------
  it("QF14: zweiter Filter liefert BEIDE Werte an onReload", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    const calls = [];
    api.renderCrossfindings(el, _data(), {
      doc: win.document,
      onlyOpen: true,
      onlyUnacknowledged: true,
      onReload: (o, u) => calls.push([o, u]),
    });

    // Beide Umschalter spiegeln den Zustand.
    expect(el.querySelector("#aiw-cf-onlyopen").checked).toBe(true);
    expect(el.querySelector("#aiw-cf-onlyunack").checked).toBe(true);
    // ... und sind unterscheidbar beschriftet (Verwechslungsschutz).
    expect(el.textContent).toContain("nur offene (Transport)");
    expect(el.textContent).toContain("nur unquittierte (Rückkanal)");

    // Rueckkanal-Filter abwaehlen -> Transportfilter bleibt erhalten.
    const cb2 = el.querySelector("#aiw-cf-onlyunack");
    cb2.checked = false;
    cb2.dispatchEvent(new win.Event("change"));
    expect(calls[calls.length - 1]).toEqual([true, false]);

    // Aktualisieren reicht beide unveraendert durch.
    el.querySelector("#aiw-cf-refresh").click();
    expect(calls[calls.length - 1]).toEqual([true, true]);
  });
});
