/**
 * tests/unit/test_cockpit_modules.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Baustein-Module (W1), FRONTEND (Build 427)
 *
 * Testsuite fuer management/server/static/cockpit_modules.js. Testet den ECHTEN
 * Code (readFileSync + JSDOM, window.AIWCockpitModules) — reine Funktionen UND
 * das DOM-Rendering inkl. Vorschau/Save.
 *
 * MO01 — API verfuegbar (reine + DOM-Funktionen); ROLES hat 6 Eintraege.
 * MO02 — roleLabel / moduleLabel.
 * MO03 — sortModules: nach role/sort_order/key, mutiert nicht.
 * MO04 — isValidKey: Spiegel der Server-Regel.
 * MO05 — buildPayload: trimmt key/title/topic; body NICHT; sort_order Zahl.
 * MO06 — summaryText / errorsText.
 * MO07 — renderModules: Liste (sortiert) + Klick fuellt Formular.
 * MO08 — Vorschau-Button ruft onDryRun mit Payload (inkl. body).
 * MO09 — Speichern-Button ruft onSave mit Payload.
 * MO10 — renderDryRun: Fehler (rot) vs. OK mit Platzhalter-Zusammenfassung (gruen).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_modules.js",
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
function _api(win) { return (win || _ctx()).AIWCockpitModules; }

function _data() {
  return {
    count: 2,
    modules: [
      { id: 2, module_key: "body.aktiv", title: "Aktivitaet", description: "",
        role: "body", topic: "Aktivitaet", body: "Text {{a:x}}.", sort_order: 1,
        is_active: 1, created_by: "red01", created_at: 1, updated_at: 1 },
      { id: 1, module_key: "intro.std", title: "Standard-Einleitung",
        description: "d", role: "intro", topic: "Allgemein",
        body: "Guten Tag {{a:username}}.", sort_order: 1,
        is_active: 1, created_by: "red01", created_at: 1, updated_at: 1 },
    ],
  };
}

describe("cockpit_modules", () => {
  it("MO01 API verfuegbar", () => {
    const api = _api();
    ["roleLabel", "moduleLabel", "sortModules", "isValidKey", "buildPayload",
     "summaryText", "errorsText", "renderModules", "renderDryRun",
     "dryRunError", "saved", "saveError", "cleanup"].forEach((fn) => {
      expect(typeof api[fn]).toBe("function");
    });
    expect(api.ROLES.length).toBe(6);
  });

  it("MO02 Labels", () => {
    const api = _api();
    expect(api.roleLabel("legal")).toContain("legal");
    expect(api.roleLabel("xyz")).toBe("xyz");
    expect(api.moduleLabel({ module_key: "a.b", title: "T" })).toBe("T (a.b)");
    expect(api.moduleLabel({ module_key: "k", title: "" })).toBe("k");
  });

  it("MO03 sortModules mutiert nicht", () => {
    const api = _api();
    const input = _data().modules;
    const out = api.sortModules(input);
    // role 'body' < 'intro' -> body.aktiv zuerst.
    expect(out.map((x) => x.module_key)).toEqual(["body.aktiv", "intro.std"]);
    expect(input.map((x) => x.module_key)).toEqual(["body.aktiv", "intro.std"]);
    expect(api.sortModules(undefined)).toEqual([]);
  });

  it("MO04 isValidKey", () => {
    const api = _api();
    expect(api.isValidKey("intro.std-1_x")).toBe(true);
    expect(api.isValidKey("hat leer")).toBe(false);
    expect(api.isValidKey("")).toBe(false);
  });

  it("MO05 buildPayload", () => {
    const api = _api();
    const p = api.buildPayload({
      module_key: "  k ", title: " T ", description: "d", role: "legal",
      topic: " Thema ", body: "  Text mit Rand  ", sort_order: "3",
    });
    expect(p.module_key).toBe("k");
    expect(p.title).toBe("T");
    expect(p.topic).toBe("Thema");
    expect(p.role).toBe("legal");
    // body NICHT getrimmt (Freitext exakt erhalten).
    expect(p.body).toBe("  Text mit Rand  ");
    expect(p.sort_order).toBe(3);
  });

  it("MO06 summaryText / errorsText", () => {
    const api = _api();
    expect(api.summaryText([{ kind: "auto", count: 2 },
                           { kind: "mandatory", count: 1 }]))
      .toBe("auto×2, mandatory×1");
    expect(api.summaryText([])).toBe("");
    expect(api.errorsText(["a", "b"])).toBe("a; b");
    expect(api.errorsText([])).toBe("");
  });

  it("MO07 renderModules: Liste + Klick fuellt Formular", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    api.renderModules(main, _data(), {});
    const items = main.querySelectorAll(".aiw-mod-item");
    expect(items.length).toBe(2);
    expect(items[0].getAttribute("data-key")).toBe("body.aktiv");

    // Neu-Modus: key leer + editierbar.
    const keyField = main.querySelector(".aiw-mod-key");
    expect(keyField.value).toBe("");
    expect(keyField.disabled).toBe(false);

    // Klick laedt Baustein (key fix, role/body gesetzt).
    items[1].dispatchEvent(new win.Event("click"));
    expect(keyField.value).toBe("intro.std");
    expect(keyField.disabled).toBe(true);
    expect(main.querySelector(".aiw-mod-role").value).toBe("intro");
    expect(main.querySelector(".aiw-mod-bodytext").value).toContain(":username");
    expect(items[1].classList.contains("is-active")).toBe(true);
  });

  it("MO08 Vorschau-Button ruft onDryRun mit Payload", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    let seen = null;
    api.renderModules(main, _data(), {
      onDryRun: function (payload) { seen = payload; },
    });
    main.querySelector(".aiw-mod-key").value = "neu.key";
    main.querySelector(".aiw-mod-title").value = "Neu";
    main.querySelector(".aiw-mod-topic").value = "Thema";
    main.querySelector(".aiw-mod-bodytext").value = "Hallo {{a:x}} {{m:y}}";
    main.querySelector(".aiw-mod-drybtn").dispatchEvent(new win.Event("click"));
    expect(seen).toBeTruthy();
    expect(seen.module_key).toBe("neu.key");
    expect(seen.body).toContain("{{a:x}}");
  });

  it("MO09 Speichern-Button ruft onSave mit Payload", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    let saved = null;
    api.renderModules(main, _data(), {
      onSave: function (payload) { saved = payload; },
    });
    main.querySelector(".aiw-mod-key").value = "s.key";
    main.querySelector(".aiw-mod-title").value = "S";
    main.querySelector(".aiw-mod-topic").value = "T";
    main.querySelector(".aiw-mod-bodytext").value = "Body";
    main.querySelector(".aiw-mod-save").dispatchEvent(new win.Event("click"));
    expect(saved).toBeTruthy();
    expect(saved.module_key).toBe("s.key");
    expect(saved.body).toBe("Body");
  });

  it("MO10 renderDryRun: Fehler vs. OK mit Zusammenfassung", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    api.renderModules(main, _data(), {});
    api.renderDryRun({ ok: false, errors: ["body fehlt."] });
    let dry = main.querySelector(".aiw-mod-dry");
    expect(dry.classList.contains("is-err")).toBe(true);
    api.renderDryRun({ ok: true, errors: [],
      summary: [{ kind: "auto", count: 2 }, { kind: "mandatory", count: 1 }] });
    dry = main.querySelector(".aiw-mod-dry");
    expect(dry.classList.contains("is-ok")).toBe(true);
    expect(dry.textContent).toContain("auto×2, mandatory×1");
  });

  // --- Browser-Zwischenspeicher (Build 488) -----------------------------
  it("MO11 Eingaben werden im localStorage gesichert", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderModules(main, _data(), {});
    const key = main.querySelector(".aiw-mod-key");
    key.value = "wip.key";
    key.dispatchEvent(new win.Event("input", { bubbles: true }));
    const bodyt = main.querySelector(".aiw-mod-bodytext");
    bodyt.value = "In Arbeit {{a:x}}";
    bodyt.dispatchEvent(new win.Event("input", { bubbles: true }));
    const raw = win.localStorage.getItem(api.DRAFT_KEY);
    expect(raw).toBeTruthy();
    const d = JSON.parse(raw);
    expect(d.fields.module_key).toBe("wip.key");
    expect(d.fields.body).toBe("In Arbeit {{a:x}}");
  });

  it("MO12 Entwurf wird beim erneuten Betreten wiederhergestellt", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderModules(main, _data(), {});
    const bodyt = main.querySelector(".aiw-mod-bodytext");
    bodyt.value = "Erhaltener Text";
    bodyt.dispatchEvent(new win.Event("input", { bubbles: true }));
    api.cleanup();
    api.renderModules(main, _data(), {});
    expect(main.querySelector(".aiw-mod-bodytext").value).toBe("Erhaltener Text");
  });

  it("MO13 erfolgreiches Speichern verwirft den Zwischenspeicher", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderModules(main, _data(), {});
    const title = main.querySelector(".aiw-mod-title");
    title.value = "X";
    title.dispatchEvent(new win.Event("input", { bubbles: true }));
    expect(win.localStorage.getItem(api.DRAFT_KEY)).toBeTruthy();
    api.saved({ created: true, target_id: "m.x" });
    expect(win.localStorage.getItem(api.DRAFT_KEY)).toBeNull();
  });
});
