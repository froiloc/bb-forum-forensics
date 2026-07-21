/**
 * tests/unit/test_cockpit_doctemplates.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Dokumentvorlagen (W3), FRONTEND (Build 425)
 *
 * Testsuite fuer management/server/static/cockpit_doctemplates.js. Testet den
 * ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitDocTemplates) — reine
 * Funktionen UND das DOM-Rendering inkl. Blocklisten-Editor und Vorschau/Save.
 *
 * DT01 — API verfuegbar (reine + DOM-Funktionen).
 * DT02 — reportTypeLabel / templateLabel / sortTemplates (mutiert nicht).
 * DT03 — isValidKey: Spiegel der Server-Regel.
 * DT04 — parseBlockData: leer->{}, gueltiges Objekt, Array/Zahl/kaputt -> Fehler.
 * DT05 — collectBlocks: meldet jeden fehlerhaften Block; leere Liste -> Fehler.
 * DT06 — buildPayload: Kopf-Felder + Bloecke, sort_order als Zahl.
 * DT07 — summaryText / errorsText.
 * DT08 — renderDocTemplates: Liste (sortiert) + Klick fuellt Formular + Bloecke.
 * DT09 — "+ Block" fuegt eine Zeile hinzu; Vorschau ruft onDryRun mit Payload.
 * DT10 — kaputte block_data -> KEIN onSave-Aufruf, Fehler im Vorschaubereich.
 * DT11 — renderDryRun: Fehler (rot) vs. OK mit Blocktyp-Zusammenfassung (gruen).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_doctemplates.js",
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
function _api(win) { return (win || _ctx()).AIWCockpitDocTemplates; }

function _blocksJson() {
  return JSON.stringify([
    { block_type: "header", block_data: { text: "Einleitung", level: 2 } },
    { block_type: "paragraph", block_data: { text: "Text {{a:name}}." } },
  ]);
}
function _data() {
  return {
    count: 2,
    documents: [
      { id: 2, template_key: "b.zweite", title: "Zweite", description: "",
        report_type: "interim", blocks_json: _blocksJson(), sort_order: 2,
        is_active: 1, created_by: "red01", created_at: 1, updated_at: 1 },
      { id: 1, template_key: "a.erste", title: "Erste", description: "d",
        report_type: "final", blocks_json: _blocksJson(), sort_order: 1,
        is_active: 1, created_by: "red01", created_at: 1, updated_at: 1 },
    ],
  };
}

describe("cockpit_doctemplates", () => {
  it("DT01 API verfuegbar", () => {
    const api = _api();
    ["reportTypeLabel", "templateLabel", "sortTemplates", "isValidKey",
     "parseBlockData", "collectBlocks", "buildPayload", "summaryText",
     "errorsText", "renderDocTemplates", "renderDryRun", "dryRunError",
     "saved", "saveError", "cleanup"].forEach((fn) => {
      expect(typeof api[fn]).toBe("function");
    });
    expect(api.BLOCK_TYPES.length).toBe(9);
  });

  it("DT02 Labels + sortTemplates mutiert nicht", () => {
    const api = _api();
    expect(api.reportTypeLabel("final")).toContain("final");
    expect(api.reportTypeLabel("xyz")).toBe("xyz");
    expect(api.templateLabel({ template_key: "a.b", title: "T" })).toBe("T (a.b)");
    const input = _data().documents;
    const out = api.sortTemplates(input);
    // nach sort_order: a.erste (1) vor b.zweite (2).
    expect(out.map((x) => x.template_key)).toEqual(["a.erste", "b.zweite"]);
    // Eingabe unveraendert.
    expect(input.map((x) => x.template_key)).toEqual(["b.zweite", "a.erste"]);
  });

  it("DT03 isValidKey", () => {
    const api = _api();
    expect(api.isValidKey("standard.final-1_x")).toBe(true);
    expect(api.isValidKey("hat leer")).toBe(false);
    expect(api.isValidKey("")).toBe(false);
  });

  it("DT04 parseBlockData", () => {
    const api = _api();
    expect(api.parseBlockData("").ok).toBe(true);
    expect(api.parseBlockData("   ").data).toEqual({});
    const good = api.parseBlockData('{"text":"x"}');
    expect(good.ok).toBe(true);
    expect(good.data.text).toBe("x");
    expect(api.parseBlockData("[1,2]").ok).toBe(false); // Array kein Objekt
    expect(api.parseBlockData("42").ok).toBe(false);    // Zahl kein Objekt
    expect(api.parseBlockData("{kaputt").ok).toBe(false); // kein JSON
  });

  it("DT05 collectBlocks meldet jeden Fehler", () => {
    const api = _api();
    const r = api.collectBlocks([
      { type: "header", dataText: '{"text":"x"}' },
      { type: "", dataText: "{}" },              // kein Typ
      { type: "paragraph", dataText: "{kaputt" }, // kaputtes JSON
    ]);
    expect(r.blocks.length).toBe(2); // die zwei parsebaren
    expect(r.errors.some((e) => e.includes("Block 1"))).toBe(true);
    expect(r.errors.some((e) => e.includes("Block 2"))).toBe(true);
    // leere Liste -> Fehler.
    expect(api.collectBlocks([]).errors.length).toBeGreaterThan(0);
    // saubere Liste -> keine Fehler.
    const ok = api.collectBlocks([{ type: "paragraph", dataText: '{"text":"a"}' }]);
    expect(ok.errors).toEqual([]);
    expect(ok.blocks[0]).toEqual({ block_type: "paragraph", block_data: { text: "a" } });
  });

  it("DT06 buildPayload", () => {
    const api = _api();
    const p = api.buildPayload(
      { template_key: "  k ", title: " T ", description: "d",
        report_type: "final", sort_order: "5" },
      [{ block_type: "paragraph", block_data: { text: "x" } }]
    );
    expect(p.template_key).toBe("k");
    expect(p.title).toBe("T");
    expect(p.report_type).toBe("final");
    expect(p.sort_order).toBe(5);
    expect(p.blocks.length).toBe(1);
  });

  it("DT07 summaryText / errorsText", () => {
    const api = _api();
    expect(api.summaryText([{ block_type: "header", count: 1 },
                            { block_type: "paragraph", count: 2 }]))
      .toBe("header×1, paragraph×2");
    expect(api.summaryText([])).toBe("");
    expect(api.errorsText(["a", "b"])).toBe("a; b");
    expect(api.errorsText([])).toBe("");
  });

  it("DT08 renderDocTemplates: Liste + Klick fuellt Formular und Bloecke", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    api.renderDocTemplates(main, _data(), {});
    const items = main.querySelectorAll(".aiw-dtpl-item");
    expect(items.length).toBe(2);
    // sortiert: a.erste vor b.zweite.
    expect(items[0].getAttribute("data-key")).toBe("a.erste");

    // Neu-Modus: key leer + editierbar, keine Bloecke.
    const keyField = main.querySelector(".aiw-dtpl-key");
    expect(keyField.value).toBe("");
    expect(keyField.disabled).toBe(false);
    expect(main.querySelectorAll(".aiw-dtpl-block").length).toBe(0);

    // Klick laedt Vorlage: key fix, 2 Bloecke, report_type gesetzt.
    items[0].dispatchEvent(new win.Event("click"));
    expect(keyField.value).toBe("a.erste");
    expect(keyField.disabled).toBe(true);
    expect(main.querySelector(".aiw-dtpl-rt").value).toBe("final");
    expect(main.querySelectorAll(".aiw-dtpl-block").length).toBe(2);
    expect(items[0].classList.contains("is-active")).toBe(true);
  });

  it("DT09 + Block + Vorschau ruft onDryRun mit Payload", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    let seen = null;
    api.renderDocTemplates(main, _data(), {
      onDryRun: function (payload) { seen = payload; },
    });
    main.querySelector(".aiw-dtpl-key").value = "neu.key";
    main.querySelector(".aiw-dtpl-title").value = "Neu";
    // Einen Block hinzufuegen (Default paragraph mit Vorlagentext).
    main.querySelector(".aiw-dtpl-addblock").dispatchEvent(new win.Event("click"));
    expect(main.querySelectorAll(".aiw-dtpl-block").length).toBe(1);
    main.querySelector(".aiw-dtpl-drybtn").dispatchEvent(new win.Event("click"));
    expect(seen).toBeTruthy();
    expect(seen.template_key).toBe("neu.key");
    expect(seen.blocks.length).toBe(1);
    expect(seen.blocks[0].block_type).toBe("paragraph");
  });

  it("DT10 kaputte block_data verhindert onSave", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    let saveCalled = false;
    api.renderDocTemplates(main, _data(), {
      onSave: function () { saveCalled = true; },
    });
    main.querySelector(".aiw-dtpl-key").value = "k";
    main.querySelector(".aiw-dtpl-title").value = "T";
    main.querySelector(".aiw-dtpl-addblock").dispatchEvent(new win.Event("click"));
    // block_data kaputt machen.
    const data = main.querySelector(".aiw-dtpl-bdata");
    data.value = "{kaputt";
    data.dispatchEvent(new win.Event("input"));
    main.querySelector(".aiw-dtpl-save").dispatchEvent(new win.Event("click"));
    expect(saveCalled).toBe(false);
    // Fehler im Vorschaubereich sichtbar.
    const dry = main.querySelector(".aiw-dtpl-dry");
    expect(dry.classList.contains("is-err")).toBe(true);
    expect(dry.textContent).toContain("Block 0");
  });

  it("DT11 renderDryRun: Fehler vs. OK mit Zusammenfassung", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    api.renderDocTemplates(main, _data(), {});
    api.renderDryRun({ ok: false, errors: ["template_key fehlt."] });
    let dry = main.querySelector(".aiw-dtpl-dry");
    expect(dry.classList.contains("is-err")).toBe(true);
    api.renderDryRun({ ok: true, errors: [],
      summary: [{ block_type: "header", count: 1 },
                { block_type: "paragraph", count: 2 }] });
    dry = main.querySelector(".aiw-dtpl-dry");
    expect(dry.classList.contains("is-ok")).toBe(true);
    expect(dry.textContent).toContain("header×1, paragraph×2");
  });

  // --- Browser-Zwischenspeicher + Textareahoehe (Build 487) --------------
  it("DT12 Eingaben werden im localStorage gesichert", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderDocTemplates(main, _data(), {});

    const key = main.querySelector(".aiw-dtpl-key");
    key.value = "neu.key";
    key.dispatchEvent(new win.Event("input", { bubbles: true }));
    const title = main.querySelector(".aiw-dtpl-title");
    title.value = "Neuer Titel";
    title.dispatchEvent(new win.Event("input", { bubbles: true }));
    // Einen Block hinzufuegen (persistiert ueber den Knopf-Handler).
    main.querySelector(".aiw-dtpl-addblock").dispatchEvent(new win.Event("click"));

    const raw = win.localStorage.getItem(api.DRAFT_KEY);
    expect(raw).toBeTruthy();
    const d = JSON.parse(raw);
    expect(d.fields.template_key).toBe("neu.key");
    expect(d.fields.title).toBe("Neuer Titel");
    expect(d.blocks.length).toBe(1);
    expect(d.blocks[0].type).toBe("paragraph");
  });

  it("DT13 Entwurf wird beim erneuten Betreten wiederhergestellt (Fensterwechsel)", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();

    // Erster Besuch: etwas eingeben.
    api.renderDocTemplates(main, _data(), {});
    const key = main.querySelector(".aiw-dtpl-key");
    key.value = "wip.key";
    key.dispatchEvent(new win.Event("input", { bubbles: true }));
    const title = main.querySelector(".aiw-dtpl-title");
    title.value = "In Arbeit";
    title.dispatchEvent(new win.Event("input", { bubbles: true }));
    main.querySelector(".aiw-dtpl-addblock").dispatchEvent(new win.Event("click"));

    // Sicht verlassen ...
    api.cleanup();
    // ... und erneut betreten (gleiches Fenster/localStorage) -> Restore.
    api.renderDocTemplates(main, _data(), {});
    expect(main.querySelector(".aiw-dtpl-key").value).toBe("wip.key");
    expect(main.querySelector(".aiw-dtpl-title").value).toBe("In Arbeit");
    expect(main.querySelectorAll(".aiw-dtpl-block").length).toBe(1);
  });

  it("DT14 erfolgreiches Speichern verwirft den Zwischenspeicher", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderDocTemplates(main, _data(), {});
    const title = main.querySelector(".aiw-dtpl-title");
    title.value = "X";
    title.dispatchEvent(new win.Event("input", { bubbles: true }));
    expect(win.localStorage.getItem(api.DRAFT_KEY)).toBeTruthy();

    api.saved({ created: true, target_id: "x.key" });
    expect(win.localStorage.getItem(api.DRAFT_KEY)).toBeNull();
  });

  it("DT15 Block-Textarea ist mind. 5 Zeilen hoch", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderDocTemplates(main, _data(), {});
    main.querySelector(".aiw-dtpl-addblock").dispatchEvent(new win.Event("click"));
    const ta = main.querySelector(".aiw-dtpl-bdata");
    expect(Number(ta.rows)).toBe(5);
  });
});
