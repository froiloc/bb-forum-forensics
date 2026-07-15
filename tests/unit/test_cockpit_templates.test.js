/**
 * tests/unit/test_cockpit_templates.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Platzhalter & Queries (W2), FRONTEND (Build 423)
 *
 * Testsuite fuer management/server/static/cockpit_templates.js. Testet den
 * ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitTemplates) — reine
 * Funktionen UND das DOM-Rendering inkl. der Dry-Run-/Speichern-Ausloeser.
 *
 * TT01 — API verfuegbar (reine + DOM-Funktionen).
 * TT02 — returnTypeLabel: deutsche Bezeichnungen + Fallback.
 * TT03 — queryLabel: "Titel (id)" bzw. Fallbacks.
 * TT04 — sortQueries: nach id, mutiert die Eingabe NICHT.
 * TT05 — isValidId: Spiegel der Server-Regel.
 * TT06 — buildPayload: trimmt, uebernimmt test_user_id/tags nur wenn gesetzt.
 * TT07 — dryRunSummary: nicht gelaufen / OK mit Wert / OK ohne Zeile.
 * TT08 — errorsText: join bzw. ''.
 * TT09 — renderTemplates: Liste (sortiert) + Editor; Klick fuellt das Formular.
 * TT10 — Dry-Run-Button ruft onDryRun mit dem gebauten Payload (inkl. uid).
 * TT11 — Speichern-Button ruft onSave mit dem gebauten Payload.
 * TT12 — renderDryRun zeigt Fehler (rot) bzw. OK-Zusammenfassung.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_templates.js",
  "utf-8"
);

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body><div id='aiw-main'></div></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api(win) { return (win || _ctx()).AIWCockpitTemplates; }

function _data() {
  return {
    count: 2,
    queries: [
      { id: "beitraege_gesamt", title: "Beitraege gesamt",
        description: "Anzahl der Beitraege", sql_query:
          "SELECT COUNT(*) FROM fdb.posts WHERE poster_id = :uid",
        tags: "aktivitaet", return_type: "scalar", is_active: 1,
        created_by: "red01", created_at: 1, updated_at: 1 },
      { id: "alias_liste", title: "Aliasse",
        description: "", sql_query:
          "SELECT username FROM fdb.uid_profile WHERE id = :uid",
        tags: null, return_type: "list", is_active: 1,
        created_by: "red01", created_at: 1, updated_at: 1 },
    ],
  };
}

describe("cockpit_templates", () => {
  it("TT01 API verfuegbar", () => {
    const api = _api();
    expect(typeof api.returnTypeLabel).toBe("function");
    expect(typeof api.queryLabel).toBe("function");
    expect(typeof api.sortQueries).toBe("function");
    expect(typeof api.isValidId).toBe("function");
    expect(typeof api.buildPayload).toBe("function");
    expect(typeof api.errorsText).toBe("function");
    expect(typeof api.dryRunSummary).toBe("function");
    expect(typeof api.renderTemplates).toBe("function");
    expect(typeof api.renderDryRun).toBe("function");
    expect(typeof api.dryRunError).toBe("function");
    expect(typeof api.saved).toBe("function");
    expect(typeof api.saveError).toBe("function");
    expect(typeof api.cleanup).toBe("function");
  });

  it("TT02 returnTypeLabel", () => {
    const api = _api();
    expect(api.returnTypeLabel("scalar")).toContain("scalar");
    expect(api.returnTypeLabel("list")).toContain("list");
    expect(api.returnTypeLabel("table")).toContain("table");
    // Fallback: unbekannter Rohwert bleibt sichtbar (kein stiller Verlust).
    expect(api.returnTypeLabel("xyz")).toBe("xyz");
    expect(api.returnTypeLabel(undefined)).toBe("scalar");
  });

  it("TT03 queryLabel", () => {
    const api = _api();
    expect(api.queryLabel({ id: "a.b", title: "Titel" })).toBe("Titel (a.b)");
    expect(api.queryLabel({ id: "nur_id", title: "" })).toBe("nur_id");
    expect(api.queryLabel({ id: "", title: "nur_titel" })).toBe("nur_titel");
    expect(api.queryLabel(null)).toBe("?");
  });

  it("TT04 sortQueries mutiert nicht", () => {
    const api = _api();
    const input = [{ id: "b" }, { id: "A" }, { id: "c" }];
    const out = api.sortQueries(input);
    expect(out.map((x) => x.id)).toEqual(["A", "b", "c"]);
    // Eingabe unveraendert (neue Liste).
    expect(input.map((x) => x.id)).toEqual(["b", "A", "c"]);
    expect(api.sortQueries(undefined)).toEqual([]);
  });

  it("TT05 isValidId spiegelt die Server-Regel", () => {
    const api = _api();
    expect(api.isValidId("beitraege.gesamt-1_x")).toBe(true);
    expect(api.isValidId("hat leerzeichen")).toBe(false);
    expect(api.isValidId("umlaut_ä")).toBe(false);
    expect(api.isValidId("")).toBe(false);
  });

  it("TT06 buildPayload trimmt + optionale Felder", () => {
    const api = _api();
    const p = api.buildPayload({
      id: "  q1 ", title: " Titel ", description: "  ", sql_query:
        "  SELECT 1  ", return_type: "list", tags: "  t ", test_user_id: " 42 ",
    });
    expect(p.id).toBe("q1");
    expect(p.title).toBe("Titel");
    expect(p.description).toBe("  "); // description bewusst nicht getrimmt
    expect(p.sql_query).toBe("SELECT 1");
    expect(p.return_type).toBe("list");
    expect(p.tags).toBe("t");
    expect(p.test_user_id).toBe("42");

    // Leere test_user_id/tags -> Felder fehlen (kein Dry-Run, kein leeres Tag).
    const p2 = api.buildPayload({ id: "q", title: "t", sql_query: "SELECT 1" });
    expect(p2.test_user_id).toBeUndefined();
    expect(p2.tags).toBeUndefined();
    expect(p2.return_type).toBe("scalar");
  });

  it("TT07 dryRunSummary deckt alle Faelle ab", () => {
    const api = _api();
    expect(api.dryRunSummary({ ran: false, reason: "kein test_user_id." }))
      .toContain("kein test_user_id");
    expect(api.dryRunSummary({ ran: true, columns: 1, sample: 7 }))
      .toContain("Beispielwert: 7");
    const noRow = api.dryRunSummary({ ran: true, columns: 1, sample: null });
    expect(noRow).toContain("keine Beispielzeile");
  });

  it("TT08 errorsText", () => {
    const api = _api();
    expect(api.errorsText(["a", "b"])).toBe("a; b");
    expect(api.errorsText([])).toBe("");
    expect(api.errorsText(undefined)).toBe("");
  });

  it("TT09 renderTemplates: Liste + Klick fuellt das Formular", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    api.renderTemplates(main, _data(), {});
    const items = main.querySelectorAll(".aiw-tpl-item");
    expect(items.length).toBe(2);
    // Sortiert nach id: 'alias_liste' vor 'beitraege_gesamt'.
    expect(items[0].getAttribute("data-id")).toBe("alias_liste");
    expect(items[1].getAttribute("data-id")).toBe("beitraege_gesamt");

    // Startzustand: Neu-Modus -> id-Feld leer und editierbar.
    const idField = main.querySelector(".aiw-tpl-id");
    expect(idField.value).toBe("");
    expect(idField.disabled).toBe(false);

    // Klick auf einen Eintrag laedt ihn (Editier-Modus: id fix).
    items[1].dispatchEvent(new win.Event("click"));
    expect(idField.value).toBe("beitraege_gesamt");
    expect(idField.disabled).toBe(true);
    expect(main.querySelector(".aiw-tpl-sql").value).toContain(":uid");
    expect(main.querySelector(".aiw-tpl-rt").value).toBe("scalar");
    expect(items[1].classList.contains("is-active")).toBe(true);
  });

  it("TT10 Dry-Run-Button ruft onDryRun mit Payload", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    let seen = null;
    api.renderTemplates(main, _data(), {
      onDryRun: function (payload) { seen = payload; },
    });
    // Felder befuellen.
    main.querySelector(".aiw-tpl-id").value = "q_neu";
    main.querySelector(".aiw-tpl-title").value = "Neu";
    main.querySelector(".aiw-tpl-sql").value = "SELECT 1 WHERE :uid = :uid";
    main.querySelector(".aiw-tpl-testuid").value = "700";
    main.querySelector(".aiw-tpl-drybtn").dispatchEvent(new win.Event("click"));
    expect(seen).toBeTruthy();
    expect(seen.id).toBe("q_neu");
    expect(seen.test_user_id).toBe("700");
    expect(seen.sql_query).toContain(":uid");
  });

  it("TT11 Speichern-Button ruft onSave mit Payload", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    let saved = null;
    api.renderTemplates(main, _data(), {
      onSave: function (payload) { saved = payload; },
    });
    main.querySelector(".aiw-tpl-id").value = "q_save";
    main.querySelector(".aiw-tpl-title").value = "S";
    main.querySelector(".aiw-tpl-sql").value = "SELECT 1";
    main.querySelector(".aiw-tpl-save").dispatchEvent(new win.Event("click"));
    expect(saved).toBeTruthy();
    expect(saved.id).toBe("q_save");
    expect(saved.title).toBe("S");
  });

  it("TT12 renderDryRun: Fehler vs. OK", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    api.renderTemplates(main, _data(), {});
    // Fehlerfall (Validierung): rote Meldung, kein OK.
    api.renderDryRun({ ok: false, errors: ["id fehlt."], dry_run: { ran: false } });
    let dry = main.querySelector(".aiw-tpl-dry");
    expect(dry.classList.contains("is-err")).toBe(true);
    expect(dry.textContent).toContain("id fehlt.");
    // OK-Fall: gruene Zusammenfassung.
    api.renderDryRun({ ok: true, errors: [], dry_run: { ran: true, columns: 1, sample: 5 } });
    dry = main.querySelector(".aiw-tpl-dry");
    expect(dry.classList.contains("is-ok")).toBe(true);
    expect(dry.textContent).toContain("Beispielwert: 5");
  });
});
