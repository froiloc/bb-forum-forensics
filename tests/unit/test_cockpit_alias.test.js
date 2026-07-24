/**
 * tests/unit/test_cockpit_alias.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Aliasse (AP-2A/A1)
 *
 * Testsuite fuer management/server/static/cockpit_alias.js (Build 505).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitAlias) —
 * keine Logik-Duplikation (B4-S12: „gruen, aber tot" vermeiden).
 *
 * AS01 — API verfuegbar; KINDS_FALLBACK deckungsgleich mit der DDL-Menge.
 * AS02 — reine Helfer: entries/kinds/counts/countsText/kindLabel/statusClass.
 * AS03 — buildAddPayload: subject_id NUR bei vollstaendig ganzzahliger Eingabe
 *        ('47xy' -> null, NICHT 47 — sonst landete der Alias am falschen Konto).
 * AS04 — validateAdd deckt alle drei Pflichtfelder ab.
 * AS05 — leerer Katalog -> Platzhalter; Suchmodus hat einen EIGENEN Leertext;
 *        Formular nur mit canEdit.
 * AS06 — mit Eintraegen: Tabelle, Status-Klassen, Widerrufsgrund sichtbar,
 *        Aktionen statusabhaengig (aktiv: Ändern/Widerrufen; widerrufen:
 *        Zurücknehmen).
 * AS07 — Widerruf verlangt einen Grund: leeres Feld -> KEIN onRetract,
 *        stattdessen Fehlermeldung; mit Grund -> onRetract({alias_id, reason}).
 * AS08 — XSS: ein Alias mit Markup landet als TEXT, nicht als DOM.
 * AS09 — Ladefehler wird als FEHLER angezeigt, nicht als leerer Katalog
 *        (Grundregel 1).
 *
 * Version: v0.8.505 · Build: 505 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/cockpit_alias.js", "utf-8");

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api() {
  return _win().AIWCockpitAlias;
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
          subject_id: 4711,
          alias: "Panther",
          alias_norm: "panther",
          kind_code: "forenname",
          kind_label: "weiterer Forenname",
          basis: "Signatur in Post 12",
          note: null,
          is_active: true,
          retracted_reason: null,
          created_at: 1700000000,
          updated_at: 1700000100,
          audit_seq: 5,
          created_audit_seq: 5,
        },
        {
          id: 2,
          subject_id: 90210,
          alias: "Luchs",
          alias_norm: "luchs",
          kind_code: "handle",
          kind_label: "Handle/Nickname ausserhalb des Forums",
          basis: "",
          note: null,
          is_active: false,
          retracted_reason: "Verwechslung mit Konto 99",
          created_at: 1700000000,
          updated_at: 1700000200,
          audit_seq: 9,
          created_audit_seq: 6,
        },
      ],
      counts: { total: 2, aktiv: 1, widerrufen: 1, subjects: 1 },
      mode: "all",
      kinds: [
        { code: "forenname", label: "weiterer Forenname" },
        { code: "handle", label: "Handle/Nickname ausserhalb des Forums" },
      ],
    },
    over || {}
  );
}

describe("cockpit_alias.js (Build 505, AP-2A/A1)", () => {
  // AS01 ---------------------------------------------------------------------
  it("AS01: API verfuegbar, Fallback-Arten decken die DDL-Menge", () => {
    const api = _api();
    expect(typeof api.renderAlias).toBe("function");
    expect(typeof api.buildAddPayload).toBe("function");
    // Deckungsgleich mit ALIAS_KINDS (subject_alias_repo.py) und dem
    // CHECK in m022 — eine Auswahl, die der Server ablehnte, waere ein Bug.
    expect(api.KINDS_FALLBACK.map((k) => k.code)).toEqual([
      "forenname",
      "handle",
      "signatur",
      "kontakt",
      "sonstiges",
    ]);
  });

  // AS02 ---------------------------------------------------------------------
  it("AS02: reine Helfer sind robust gegen fehlende Felder", () => {
    const api = _api();
    expect(api.entries(null)).toEqual([]);
    expect(api.entries({ entries: "nope" })).toEqual([]);
    // Fehlt die Server-Liste, greift der Fallback (nie eine LEERE Auswahl).
    expect(api.kinds({}).length).toBe(5);
    expect(api.kinds({ kinds: [{ code: "x", label: "X" }] }).length).toBe(1);

    expect(api.counts(null)).toEqual({
      total: 0,
      aktiv: 0,
      widerrufen: 0,
      subjects: 0,
    });
    expect(api.countsText(_data())).toContain("1 aktiv");
    expect(api.countsText(_data())).toContain("1 widerrufen");

    expect(api.kindLabel("forenname")).toBe("weiterer Forenname");
    expect(api.kindLabel("gibtsnicht")).toBe("gibtsnicht");
    expect(api.statusClass(true)).toBe("aiw-alias-aktiv");
    expect(api.statusClass(false)).toBe("aiw-alias-widerrufen");
    expect(api.fmtTs(0)).toBe("—");
    expect(api.fmtTs("quatsch")).toBe("—");
  });

  // AS03 ---------------------------------------------------------------------
  it("AS03: buildAddPayload parst subject_id streng", () => {
    const api = _api();
    expect(api.buildAddPayload({ subject_id: "4711" }).subject_id).toBe(4711);
    expect(api.buildAddPayload({ subject_id: " 4711 " }).subject_id).toBe(4711);
    // Der entscheidende Fall: parseInt('47xy') waere 47 — ein FALSCHES Konto.
    expect(api.buildAddPayload({ subject_id: "47xy" }).subject_id).toBeNull();
    expect(api.buildAddPayload({ subject_id: "" }).subject_id).toBeNull();
    expect(api.buildAddPayload({}).subject_id).toBeNull();

    const b = api.buildAddPayload({
      subject_id: "1",
      alias: "  Panther  ",
      kind_code: "handle",
      basis: "  Fund  ",
      note: "   ",
    });
    expect(b.alias).toBe("Panther");
    expect(b.basis).toBe("Fund");
    // Leere Notiz wird weggelassen (der Server behandelt sie dann als null).
    expect("note" in b).toBe(false);

    const c = api.buildAddPayload({ subject_id: "1", note: " x " });
    expect(c.note).toBe("x");
  });

  // AS04 ---------------------------------------------------------------------
  it("AS04: validateAdd deckt alle Pflichtfelder ab", () => {
    const api = _api();
    expect(api.validateAdd(null)).toMatch(/subject_id/);
    expect(api.validateAdd({ subject_id: null })).toMatch(/subject_id/);
    expect(api.validateAdd({ subject_id: 1, alias: "" })).toMatch(/Alias/);
    expect(
      api.validateAdd({ subject_id: 1, alias: "P", kind_code: "" })
    ).toMatch(/Art/);
    expect(
      api.validateAdd({ subject_id: 1, alias: "P", kind_code: "handle" })
    ).toBeNull();
  });

  // AS05 ---------------------------------------------------------------------
  it("AS05: Leerbefund und Rechte-Abhaengigkeit des Formulars", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;

    const el1 = _mount(win);
    api.renderAlias(el1, { entries: [], counts: {} }, { doc: win.document });
    expect(el1.querySelector("table")).toBeNull();
    expect(el1.querySelector(".aiw-placeholder").textContent).toBe(
      "Noch kein Alias im Katalog."
    );
    // Ohne canEdit: kein Anlage-Formular, dafuer der Hinweis auf das Recht.
    expect(el1.querySelector("#aiw-alias-add")).toBeNull();
    expect(el1.querySelector(".aiw-alias-readonly")).toBeTruthy();

    // Im SUCHMODUS ist der Leerbefund eine ANDERE Aussage.
    const el2 = _mount(win);
    api.renderAlias(
      el2,
      { entries: [], counts: {} },
      { doc: win.document, query: "Panther" }
    );
    expect(el2.querySelector(".aiw-placeholder").textContent).toBe(
      "Kein Konto führt diesen Namen."
    );

    const el3 = _mount(win);
    api.renderAlias(
      el3,
      { entries: [], counts: {} },
      { doc: win.document, canEdit: true }
    );
    expect(el3.querySelector("#aiw-alias-add")).toBeTruthy();
    expect(el3.querySelector(".aiw-alias-readonly")).toBeNull();
  });

  // AS06 ---------------------------------------------------------------------
  it("AS06: Tabelle, Status-Klassen und statusabhaengige Aktionen", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    api.renderAlias(el, _data(), { doc: win.document, canEdit: true });

    const rows = el.querySelectorAll("tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0].className).toBe("aiw-alias-aktiv");
    expect(rows[1].className).toBe("aiw-alias-widerrufen");

    // Der Widerrufsgrund gehoert sichtbar in die Zeile.
    expect(rows[1].textContent).toContain("Verwechslung mit Konto 99");

    // Aktive Zeile: Ändern + Widerrufen, KEIN Zurücknehmen.
    expect(rows[0].querySelector(".aiw-alias-change")).toBeTruthy();
    expect(rows[0].querySelector(".aiw-alias-retract")).toBeTruthy();
    expect(rows[0].querySelector(".aiw-alias-reinstate")).toBeNull();
    // Widerrufene Zeile: nur Zurücknehmen.
    expect(rows[1].querySelector(".aiw-alias-reinstate")).toBeTruthy();
    expect(rows[1].querySelector(".aiw-alias-retract")).toBeNull();

    // Ohne canEdit gibt es gar keine Aktionen.
    const el2 = _mount(win);
    api.renderAlias(el2, _data(), { doc: win.document });
    expect(el2.querySelectorAll(".aiw-alias-retract").length).toBe(0);
  });

  // AS07 ---------------------------------------------------------------------
  it("AS07: Widerruf ohne Grund wird im UI abgefangen", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    const calls = [];
    api.renderAlias(el, _data(), {
      doc: win.document,
      canEdit: true,
      onRetract: (b) => calls.push(b),
    });

    const row = el.querySelectorAll("tbody tr")[0];
    row.querySelector(".aiw-alias-retract").click();
    const reasonRow = el.querySelector(".aiw-alias-reasonrow");
    expect(reasonRow).toBeTruthy();

    // Leerer Grund -> kein Aufruf, aber eine sichtbare Meldung.
    reasonRow.querySelector(".aiw-alias-retract-go").click();
    expect(calls.length).toBe(0);
    const res = el.querySelector("#aiw-alias-result");
    expect(res.textContent).toMatch(/Grund ist Pflicht/);
    expect(res.classList.contains("error")).toBe(true);

    // Mit Grund -> genau ein Aufruf mit den erwarteten Feldern.
    reasonRow.querySelector(".aiw-alias-reason").value = "  Irrtum  ";
    reasonRow.querySelector(".aiw-alias-retract-go").click();
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({ alias_id: 1, reason: "Irrtum" });
  });

  // AS08 ---------------------------------------------------------------------
  it("AS08: Fremdtext ist XSS-sicher (textContent, kein Markup)", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    const boese = '<img src=x onerror="alert(1)">Panther';
    const d = _data();
    d.entries[0].alias = boese;
    d.entries[0].basis = "<script>alert(2)</script>";
    api.renderAlias(el, d, { doc: win.document, canEdit: true });

    const cell = el.querySelector(".aiw-alias-name-cell");
    expect(cell.textContent).toBe(boese);
    // Kein eingeschleustes Element im gesamten Baum.
    expect(el.querySelector("img")).toBeNull();
    expect(el.querySelector("script")).toBeNull();
  });

  // AS09 ---------------------------------------------------------------------
  it("AS09: Ladefehler ist kein Leerbefund", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    api.renderAlias(el, { error: "HTTP 503" }, { doc: win.document });

    const err = el.querySelector(".aiw-alias-error");
    expect(err).toBeTruthy();
    expect(err.textContent).toContain("HTTP 503");
    // ... und ausdruecklich NICHT der harmlose "noch kein Alias"-Text.
    expect(el.querySelector(".aiw-placeholder")).toBeNull();
    expect(el.querySelector("table")).toBeNull();
  });
});
