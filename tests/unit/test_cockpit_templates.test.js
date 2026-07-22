/**
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
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
 * TT06 — buildPayload: trimmt, uebernimmt test_subject_id/tags nur wenn gesetzt.
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

// Build 490: der Server (489) liefert 'placeholders' inkl. Typ/Validierung.
function _data() {
  return {
    count: 3,
    placeholders: [
      { id: "beitraege_gesamt", title: "Beitraege gesamt",
        description: "Anzahl der Beitraege", type: "a", sql_query:
          "SELECT COUNT(*) FROM fdb.posts WHERE poster_id = :uid",
        default_value: null, validation: null, validation_type: null,
        tags: "aktivitaet", return_type: "scalar", is_active: 1,
        created_by: "red01", created_at: 1, updated_at: 1 },
      { id: "alias_liste", title: "Aliasse",
        description: "", type: "a", sql_query:
          "SELECT username FROM fdb.uid_profile WHERE id = :uid",
        default_value: null, validation: null, validation_type: null,
        tags: null, return_type: "list", is_active: 1,
        created_by: "red01", created_at: 1, updated_at: 1 },
      { id: "spurennummer", title: "Spurennummer",
        description: "", type: "m", sql_query: null,
        default_value: "unbekannt", validation: "^[A-Z]{2}-\\d{4}$",
        validation_type: "regex", tags: null, return_type: "scalar",
        is_active: 1, created_by: "red01", created_at: 1, updated_at: 1 },
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
        "  SELECT 1  ", return_type: "list", tags: "  t ", test_subject_id: " 42 ",
    });
    expect(p.id).toBe("q1");
    expect(p.title).toBe("Titel");
    expect(p.description).toBe("  "); // description bewusst nicht getrimmt
    expect(p.sql_query).toBe("SELECT 1");
    expect(p.return_type).toBe("list");
    expect(p.tags).toBe("t");
    expect(p.test_subject_id).toBe("42");

    // Leere test_subject_id/tags -> Felder fehlen (kein Dry-Run, kein leeres Tag).
    const p2 = api.buildPayload({ id: "q", title: "t", sql_query: "SELECT 1" });
    expect(p2.test_subject_id).toBeUndefined();
    expect(p2.tags).toBeUndefined();
    expect(p2.return_type).toBe("scalar");
  });

  it("TT07 dryRunSummary deckt alle Faelle ab", () => {
    const api = _api();
    expect(api.dryRunSummary({ ran: false, reason: "kein test_subject_id." }))
      .toContain("kein test_subject_id");
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
    expect(items.length).toBe(3);
    // Sortiert nach id: 'alias_liste' vor 'beitraege_gesamt' vor 'spurennummer'.
    expect(items[0].getAttribute("data-id")).toBe("alias_liste");
    expect(items[1].getAttribute("data-id")).toBe("beitraege_gesamt");
    expect(items[2].getAttribute("data-id")).toBe("spurennummer");
    // Build 490: Typ-Praefix im Listenlabel.
    expect(items[2].textContent).toContain("[m]");

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
    expect(seen.test_subject_id).toBe("700");
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

  // --- Browser-Zwischenspeicher (Build 488) -----------------------------
  it("TT13 Eingaben werden im localStorage gesichert", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderTemplates(main, _data(), {});
    const id = main.querySelector(".aiw-tpl-id");
    id.value = "q_wip";
    id.dispatchEvent(new win.Event("input", { bubbles: true }));
    const title = main.querySelector(".aiw-tpl-title");
    title.value = "In Arbeit";
    title.dispatchEvent(new win.Event("input", { bubbles: true }));
    const raw = win.localStorage.getItem(api.DRAFT_KEY);
    expect(raw).toBeTruthy();
    const d = JSON.parse(raw);
    expect(d.fields.id).toBe("q_wip");
    expect(d.fields.title).toBe("In Arbeit");
  });

  it("TT14 Entwurf wird beim erneuten Betreten wiederhergestellt", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderTemplates(main, _data(), {});
    const sql = main.querySelector(".aiw-tpl-sql");
    sql.value = "SELECT 42 WHERE :uid = :uid";
    sql.dispatchEvent(new win.Event("input", { bubbles: true }));
    api.cleanup();
    api.renderTemplates(main, _data(), {});
    expect(main.querySelector(".aiw-tpl-sql").value)
      .toBe("SELECT 42 WHERE :uid = :uid");
  });

  it("TT15 erfolgreiches Speichern verwirft den Zwischenspeicher", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderTemplates(main, _data(), {});
    const title = main.querySelector(".aiw-tpl-title");
    title.value = "X";
    title.dispatchEvent(new win.Event("input", { bubbles: true }));
    expect(win.localStorage.getItem(api.DRAFT_KEY)).toBeTruthy();
    api.saved({ created: true, target_id: "q.x" });
    expect(win.localStorage.getItem(api.DRAFT_KEY)).toBeNull();
  });

  // --- Platzhalter-Neuordnung (Build 490) --------------------------------
  it("TT16 typeLabel + validateRule (regex/list/like)", () => {
    const api = _api();
    expect(api.typeLabel("a")).toContain("{{a:}}");
    expect(api.typeLabel("m")).toContain("verpflichtend");
    expect(api.typeLabel("o")).toContain("optional");
    // regex: gueltig / ungueltig (JS-Dialekt ist hier die Autoritaet).
    expect(api.validateRule("regex", "^[A-Z]{2}-\\d{4}$").ok).toBe(true);
    expect(api.validateRule("regex", "([").ok).toBe(false);
    // list: JSON-Array aus Strings, nicht leer.
    expect(api.validateRule("list", '["ja","nein"]').ok).toBe(true);
    expect(api.validateRule("list", "kein json").ok).toBe(false);
    expect(api.validateRule("list", "[]").ok).toBe(false);
    expect(api.validateRule("list", '[1,2]').ok).toBe(false);
    // like: nicht leer; keine Regel (beides leer) ist ok.
    expect(api.validateRule("like", "SP-%").ok).toBe(true);
    expect(api.validateRule("like", "  ").ok).toBe(false);
    expect(api.validateRule("", "").ok).toBe(true);
    // Art ohne Regel (und umgekehrt) -> ungueltig.
    expect(api.validateRule("regex", "").ok).toBe(false);
    expect(api.validateRule("", "^x$").ok).toBe(false);
  });

  it("TT17 testRule: Beispiel-Eingabe gegen die Regel", () => {
    const api = _api();
    expect(api.testRule("regex", "^[A-Z]{2}-\\d{4}$", "NW-2026").match)
      .toBe(true);
    expect(api.testRule("regex", "^[A-Z]{2}-\\d{4}$", "nw-2026").match)
      .toBe(false);
    expect(api.testRule("list", '["ja","nein"]', "ja").match).toBe(true);
    expect(api.testRule("list", '["ja","nein"]', "vielleicht").match)
      .toBe(false);
    // like: Full-Match; % beliebig, _ genau ein Zeichen.
    expect(api.testRule("like", "SP-%", "SP-0815").match).toBe(true);
    expect(api.testRule("like", "SP-%", "XSP-0815").match).toBe(false);
    expect(api.testRule("like", "A_C", "ABC").match).toBe(true);
    expect(api.testRule("like", "A_C", "ABBC").match).toBe(false);
    // Kaputte Regel -> ok false, kein match.
    expect(api.testRule("regex", "([", "x").ok).toBe(false);
  });

  it("TT18 buildPayload: Typregeln (a ohne Validierung, m/o scalar)", () => {
    const api = _api();
    // a: keine Validierungs-/Default-Felder im Payload.
    const pa = api.buildPayload({ id: "q1", title: "T", type: "a",
      sql_query: "SELECT 1", return_type: "list",
      validation: "^x$", validation_type: "regex", default_value: "d" });
    expect(pa.type).toBe("a");
    expect(pa.return_type).toBe("list");
    expect("validation" in pa).toBe(false);
    expect("default_value" in pa).toBe(false);
    // m: return_type wird auf scalar gezwungen; Validierung nur PAARWEISE.
    const pm = api.buildPayload({ id: "q2", title: "T", type: "m",
      return_type: "table", default_value: "unbekannt",
      validation: "^[A-Z]+$", validation_type: "regex" });
    expect(pm.return_type).toBe("scalar");
    expect(pm.validation).toBe("^[A-Z]+$");
    expect(pm.validation_type).toBe("regex");
    expect(pm.default_value).toBe("unbekannt");
    const pm2 = api.buildPayload({ id: "q3", title: "T", type: "o",
      validation: "", validation_type: "regex" });
    expect("validation" in pm2).toBe(false);
    expect("validation_type" in pm2).toBe(false);
  });

  it("TT21 Case-Insensitivity (Build 497): testRule + buildPayload", () => {
    const api = _api();
    // testRule mit ci=true ignoriert Gross-/Kleinschreibung (alle drei Arten).
    expect(api.testRule("regex", "^[A-Z]{2}-\\d{4}$", "nw-2026", true).match)
      .toBe(true);
    expect(api.testRule("list", '["Ja","Nein"]', "ja", true).match).toBe(true);
    expect(api.testRule("like", "SP-%", "sp-0815", true).match).toBe(true);
    // ohne ci bleibt es case-sensitive.
    expect(api.testRule("like", "SP-%", "sp-0815", false).match).toBe(false);
    // likeToRegExp ci-Flag.
    expect(api.likeToRegExp("abc", true).test("ABC")).toBe(true);
    // buildPayload: validation_ci nur paarweise mit aktiver Validierung.
    const pm = api.buildPayload({ id: "q", title: "T", type: "m",
      validation: "^[A-Z]+$", validation_type: "regex", validation_ci: 1 });
    expect(pm.validation_ci).toBe(1);
    const pm0 = api.buildPayload({ id: "q", title: "T", type: "m",
      validation: "^[A-Z]+$", validation_type: "regex" });
    expect(pm0.validation_ci).toBe(0);
    // ohne Validierung kein validation_ci.
    const pm2 = api.buildPayload({ id: "q", title: "T", type: "m",
      validation: "", validation_type: "" });
    expect("validation_ci" in pm2).toBe(false);
  });

  it("TT22 Maske: ci-Checkbox landet in _currentFields/Payload", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    let saved = null;
    api.renderTemplates(main, _data(), { onSave: (p) => { saved = p; } });
    // Auf Typ 'm' schalten (Validierungsblock sichtbar), Regel + ci setzen.
    const fType = main.querySelector(".aiw-tpl-type");
    fType.value = "m";
    fType.dispatchEvent(new win.Event("change"));
    main.querySelector(".aiw-tpl-id").value = "spur";
    main.querySelector(".aiw-tpl-title").value = "Spur";
    main.querySelector(".aiw-tpl-vtype").value = "like";
    main.querySelector(".aiw-tpl-validation").value = "SP-%";
    const ci = main.querySelector(".aiw-tpl-vci");
    expect(ci).not.toBeNull();
    ci.checked = true;
    main.querySelector(".aiw-tpl-save").click();
    expect(saved).not.toBeNull();
    expect(saved.validation_ci).toBe(1);
  });

  it("TT19 Maske: Typ-Dropdown steuert Sichtbarkeit + return_type-Sperre", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderTemplates(main, _data(), {});

    const fType = main.querySelector(".aiw-tpl-type");
    const valWrap = main.querySelector(".aiw-tpl-valwrap");
    const rt = main.querySelector(".aiw-tpl-rt");
    // Startzustand (Neu-Modus, Typ a): Validierungsblock versteckt, rt frei.
    expect(fType.value).toBe("a");
    expect(valWrap.classList.contains("aiw-tpl-hidden")).toBe(true);
    expect(rt.disabled).toBe(false);
    // Dialekt-Hinweis steht in der Maske (mc-Wunsch).
    expect(main.querySelector(".aiw-tpl-valnote").textContent)
      .toContain("JavaScript-Dialekt");

    // Umschalten auf m: Block sichtbar, rt fest 'scalar'.
    fType.value = "m";
    fType.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(valWrap.classList.contains("aiw-tpl-hidden")).toBe(false);
    expect(rt.disabled).toBe(true);
    expect(rt.value).toBe("scalar");

    // Klick auf den m-Eintrag der Liste laedt Validierung + Default.
    const items = main.querySelectorAll(".aiw-tpl-item");
    items[2].dispatchEvent(new win.Event("click"));
    expect(main.querySelector(".aiw-tpl-vtype").value).toBe("regex");
    expect(main.querySelector(".aiw-tpl-validation").value)
      .toBe("^[A-Z]{2}-\\d{4}$");
    expect(main.querySelector(".aiw-tpl-default").value).toBe("unbekannt");
    // Regel-Gueltigkeit wird live gemeldet.
    expect(main.querySelector(".aiw-tpl-valcheckmsg").textContent)
      .toContain("gueltig");
  });

  it("TT20 Testfeld prueft live; kaputte Regel wird rot gemeldet", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderTemplates(main, _data(), {});
    // m-Eintrag laden (Regex ^[A-Z]{2}-\d{4}$).
    main.querySelectorAll(".aiw-tpl-item")[2]
      .dispatchEvent(new win.Event("click"));

    const testIn = main.querySelector(".aiw-tpl-valtest");
    testIn.value = "NW-2026";
    testIn.dispatchEvent(new win.Event("input", { bubbles: true }));
    let out = main.querySelector(".aiw-tpl-valtestmsg");
    expect(out.classList.contains("is-ok")).toBe(true);
    expect(out.textContent).toContain("BESTEHT");

    testIn.value = "kaputt";
    testIn.dispatchEvent(new win.Event("input", { bubbles: true }));
    out = main.querySelector(".aiw-tpl-valtestmsg");
    expect(out.classList.contains("is-err")).toBe(true);
    expect(out.textContent).toContain("NICHT");

    // Kaputte Regel: Gueltigkeitsmeldung rot, Test nicht moeglich.
    const fVal = main.querySelector(".aiw-tpl-validation");
    fVal.value = "([";
    fVal.dispatchEvent(new win.Event("input", { bubbles: true }));
    const chk = main.querySelector(".aiw-tpl-valcheckmsg");
    expect(chk.classList.contains("is-err")).toBe(true);
    expect(chk.textContent).toContain("Regex ungueltig");
  });
});
