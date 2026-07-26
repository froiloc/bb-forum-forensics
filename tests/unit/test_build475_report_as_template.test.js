/**
 * tests/unit/test_build475_report_as_template.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * "Bericht als Vorlage uebernehmen" — FRONTEND (Build 475)
 *
 * Testet den ECHTEN Code (readFileSync + JSDOM) der beiden beruehrten Module:
 *   cockpit_doctemplates.js — draftToRows/findingsText (rein) + initialDraft.
 *   cockpit_lectorate.js    — Uebernahme-Knopf (nur mit Callback) + transferError.
 *
 * BT01 — doctemplates: API-Erweiterung (draftToRows, findingsText) vorhanden.
 * BT02 — draftToRows: {block_type,block_data}-Objekte -> [{type,dataText}] (JSON).
 * BT03 — findingsText: verdichtet Befunde; '' bei keiner.
 * BT04 — renderDocTemplates(initialDraft): fuellt Kopf/Bloecke, key EDITIERBAR,
 *        Befund sichtbar (Grundregel 1).
 * BT05 — lectorate: OHNE onTransferToTemplate KEIN Uebernahme-Knopf.
 * BT06 — lectorate: MIT Callback -> Knopf da, erst nach Auswahl aktiv, Klick
 *        ruft Callback mit (uid, rid).
 * BT07 — lectorate: transferError reaktiviert den Knopf (kein toter Zustand).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _srcDt = readFileSync(
  "management/server/static/cockpit_doctemplates.js", "utf-8");
const _srcLe = readFileSync(
  "management/server/static/cockpit_lectorate.js", "utf-8");
// Build 553: das gemeinsame Tabellen-Werkzeug MUSS im Kontext liegen — genau
// wie im Browser (cockpit.html laedt es vor den Sichten). Ohne es faellt das
// Lektorat in seinen Ersatzpfad und die Tabelle, an der die Auswahl haengt,
// entsteht gar nicht erst.
const _srcTk = readFileSync(
  "management/server/static/cockpit_tablekit.js", "utf-8");

function _win(src) {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body><div id='aiw-main'></div></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(_srcTk);
  dom.window.eval(src);
  return dom.window;
}

function _draft() {
  return {
    template_key: "vorlage-aus-bericht",
    title: "Vorlage aus Bericht: Haupt",
    report_type: "final",
    blocks: [
      { block_type: "header", block_data: { text: "Kapitel", level: 2 } },
      { block_type: "paragraph", block_data: { text: "Text {{a:name}}." } },
      { block_type: "evidence", block_data: { evidence_ids: [], text: "" } },
    ],
  };
}

function _reportsData() {
  return {
    scope: "alle", count: 1,
    reports: [
      { id: 7, subject_id: 700, username: "b700", report_type: "final",
        sequence_nr: 1, status: "submitted", created_at: 1000 },
    ],
  };
}

describe("cockpit_doctemplates (Build 475)", () => {
  it("BT01 API-Erweiterung vorhanden", () => {
    const api = _win(_srcDt).AIWCockpitDocTemplates;
    expect(typeof api.draftToRows).toBe("function");
    expect(typeof api.findingsText).toBe("function");
  });

  it("BT02 draftToRows: Objekte -> Zeilen mit JSON-dataText", () => {
    const api = _win(_srcDt).AIWCockpitDocTemplates;
    const rows = api.draftToRows(_draft());
    expect(rows.length).toBe(3);
    expect(rows[0].type).toBe("header");
    // dataText ist ein JSON-String, der die block_data traegt.
    expect(JSON.parse(rows[0].dataText)).toEqual({ text: "Kapitel", level: 2 });
    expect(rows[1].dataText).toContain("{{a:name}}");
    // Nicht-Array/leer -> leere Liste (defensiv).
    expect(api.draftToRows(null)).toEqual([]);
    expect(api.draftToRows({ blocks: "x" })).toEqual([]);
  });

  it("BT03 findingsText verdichtet Befunde", () => {
    const api = _win(_srcDt).AIWCockpitDocTemplates;
    expect(api.findingsText([])).toBe("");
    const t = api.findingsText([
      { block_index: 0, block_type: "paragraph",
        action: "placeholder_values_cleared", detail: "2 Werte" },
      { block_index: 2, block_type: "evidence",
        action: "evidence_ids_cleared", detail: "3 Verweise" },
    ]);
    expect(t).toContain("Block 0");
    expect(t).toContain("paragraph");
    expect(t).toContain("2 Werte");
    expect(t).toContain("Block 2");
  });

  it("BT04 renderDocTemplates(initialDraft) fuellt Maske, key editierbar, Befund sichtbar", () => {
    const win = _win(_srcDt);
    const api = win.AIWCockpitDocTemplates;
    const main = win.document.getElementById("aiw-main");
    api.renderDocTemplates(main, { count: 0, documents: [] }, {
      initialDraft: _draft(),
      initialFindings: [
        { block_index: 2, block_type: "evidence",
          action: "evidence_ids_cleared", detail: "3 Verweis(e) entfernt" },
      ],
    });
    const key = main.querySelector(".aiw-dtpl-key");
    expect(key.value).toBe("vorlage-aus-bericht");
    // NEU-Modus: der Schluessel bleibt editierbar (kein stilles Ueberschreiben).
    expect(key.disabled).toBe(false);
    // Titel + report_type uebernommen.
    expect(main.querySelector(".aiw-dtpl-title").value)
      .toContain("Vorlage aus Bericht");
    expect(main.querySelector(".aiw-dtpl-rt").value).toBe("final");
    // Drei Blockzeilen.
    expect(main.querySelectorAll(".aiw-dtpl-block").length).toBe(3);
    // Befund-Panel gerendert (Grundregel 1: Entfernung sichtbar).
    const befund = main.querySelector(".aiw-dtpl-befund");
    expect(befund.textContent).toContain("Unverfaenglichkeits-Befund");
    expect(befund.textContent).toContain("evidence");
  });
});

describe("cockpit_lectorate (Build 475)", () => {
  it("BT05 ohne Callback KEIN Uebernahme-Knopf", () => {
    const win = _win(_srcLe);
    const api = win.AIWCockpitLectorate;
    const main = win.document.getElementById("aiw-main");
    api.renderLectorate(main, _reportsData(), { status: "submitted" });
    expect(main.querySelector(".aiw-lectorate-xfer")).toBeNull();
  });

  // Build 481: Auswahl erfolgt jetzt ueber den Tabulator-rowClick (statt einer
  // Button-Liste). Der Tabulator-Ctor wird als Stub injiziert; die Auswahl wird
  // durch direkten Aufruf von opts.rowClick simuliert.
  function _stubTab() {
    let made = null;
    function StubTab(container, opts) {
      made = { container, opts, handlers: {} };
      // Build 486: rowClick wird via table.on() angehaengt.
      this.on = function (ev, fn) { made.handlers[ev] = fn; };
      this.replaceData = function (d) { made.replaced = d; };
      this.destroy = function () {};
    }
    return { StubTab: StubTab, get: () => made };
  }
  function _pickFirst(made) {
    const row = made.opts.data[0];
    made.handlers.rowClick({}, { getData: () => row, getElement: () => null });
  }

  it("BT06 mit Callback: Knopf da, erst nach Auswahl aktiv, Klick ruft (uid,rid)", () => {
    const win = _win(_srcLe);
    const api = win.AIWCockpitLectorate;
    const main = win.document.getElementById("aiw-main");
    const tab = _stubTab();
    let called = null;
    api.renderLectorate(main, _reportsData(), {
      status: "submitted",
      onTransferToTemplate: function (uid, rid) { called = [uid, rid]; },
      Tabulator: tab.StubTab,
    });
    const btn = main.querySelector(".aiw-lectorate-xfer");
    expect(btn).not.toBeNull();
    expect(btn.disabled).toBe(true);          // vor Auswahl aus
    // Bericht auswaehlen (rowClick) -> Knopf aktiv.
    _pickFirst(tab.get());
    expect(btn.disabled).toBe(false);
    // Uebernehmen -> Callback mit dem gewaehlten Bericht.
    btn.click();
    expect(called).toEqual([700, 7]);
  });

  it("BT07 transferError reaktiviert den Knopf", () => {
    const win = _win(_srcLe);
    const api = win.AIWCockpitLectorate;
    const main = win.document.getElementById("aiw-main");
    const tab = _stubTab();
    api.renderLectorate(main, _reportsData(), {
      status: "submitted",
      onTransferToTemplate: function () {},
      Tabulator: tab.StubTab,
    });
    _pickFirst(tab.get());
    const btn = main.querySelector(".aiw-lectorate-xfer");
    btn.click();                       // setzt disabled=true (busy)
    expect(btn.disabled).toBe(true);
    api.transferError("Serverfehler");
    expect(btn.disabled).toBe(false);  // wieder versuchbar
    expect(main.querySelector(".aiw-lectorate-xfermsg").textContent)
      .toContain("fehlgeschlagen");
  });
});
