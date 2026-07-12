/**
 * tests/unit/test_cockpit_cases.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit "Fall-Erkennung"
 *
 * Testsuite fuer management/server/static/cockpit_cases.js (Build 384).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitCases) — kein
 * nachgebautes Logik-Abbild ("gruen aber tot"-Falle).
 *
 * FE01 — API verfuegbar (UMD-Ausgang).
 * FE02 — isSelectable: NUR 'neu' MIT Benutzername ist aufnehmbar (spiegelt
 *        CaseDetector.importable(), Build 383).
 * FE03 — toRows: Zustands-Label, Arbeitsstand-Spalten, Auswahl-Flag.
 * FE04 — filterByStatus + countsText + dirsText.
 * FE05 — warningRows/warningLine: 'vermisst' und 'unlesbar' MIT Grund
 *        (GRUNDREGEL 1 — nichts wird verschwiegen).
 * FE06 — importRequest: nie ein Leer-POST; nie {all:true}.
 * FE07 — resultText: imported MIT Beleg-Nr., skipped MIT Grund; ein
 *        uebersprungener Fall ist ein BEFUND (error=true).
 * FE08 — renderCases: Kopf, Zaehler, Verzeichnisse, Filter, Aktionsfeld;
 *        Aufnahme-Knopf startet DEAKTIVIERT (nichts ausgewaehlt).
 * FE09 — renderCases: WARNBEREICH wird gerendert und nennt jeden Missstand.
 * FE10 — renderCases: Auswahl -> Bestaetigung -> Ausfuehren (zweistufig);
 *        Abbrechen schreibt NICHTS.
 * FE11 — renderCases ohne Tabellenbibliothek: Warnbereich und Zaehler stehen
 *        TROTZDEM (die Warnung darf nicht an einer Bibliothek scheitern).
 */

import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_cases.js",
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
function _api() { return _ctx().AIWCockpitCases; }

/** Fake-Tabulator: haelt die Daten UND ruft die Spalten-Formatter auf.
 *  Das ist wichtig: das Auswahlkaestchen der Fall-Erkennung entsteht in einem
 *  EIGENEN Formatter (nicht in Tabulators 'rowSelection'). Ohne Formatter-Aufruf
 *  wuerde der Test den Auswahl-/Bestaetigungsweg gar nicht beruehren — genau die
 *  'gruen aber tot'-Falle. Der Fake haengt die vom Formatter erzeugten Knoten in
 *  den Container, sodass das Kaestchen im DOM anklickbar ist. */
function _fakeTabulator(doc) {
  return function (container, options) {
    const self = this;
    this.container = container;
    this.options = options;
    this.data = options.data;

    this._render = function (rows) {
      container.textContent = "";
      (rows || []).forEach(function (d) {
        const tr = doc.createElement("div");
        tr.className = "fake-row";
        tr.setAttribute("data-row-id", String(d.user_id));
        (options.columns || []).forEach(function (col) {
          if (typeof col.formatter !== "function") { return; }
          const node = col.formatter({ getData: function () { return d; } });
          if (node && node.nodeType) { tr.appendChild(node); }
        });
        container.appendChild(tr);
      });
    };

    this._render(this.data);
    this.replaceData = function (d) { self.data = d; self._render(d); };
    this.destroy = function () {};
  };
}

function _data() {
  return {
    forensic_dir: "./data/forensic",
    evidence_dir: "./data/evidence",
    assets_dir: "./data/assets",
    count: 5,
    counts: { ok: 1, neu: 2, vermisst: 1, unlesbar: 1 },
    cases: [
      { user_id: 18, status: "ok", username: "b18", in_cases: true,
        has_forensic_db: true, has_evidence_db: true, has_assets_db: true,
        detail: null },
      { user_id: 19, status: "neu", username: "b19", in_cases: false,
        has_forensic_db: true, has_evidence_db: false, has_assets_db: false,
        detail: null },
      { user_id: 20, status: "neu", username: "b20", in_cases: false,
        has_forensic_db: true, has_evidence_db: true, has_assets_db: false,
        detail: null },
      { user_id: 21, status: "vermisst", username: "b21", in_cases: true,
        has_forensic_db: false, has_evidence_db: true, has_assets_db: true,
        detail: "forensic_21.db fehlt im Verzeichnis ./data/forensic" },
      { user_id: 22, status: "unlesbar", username: null, in_cases: false,
        has_forensic_db: true, has_evidence_db: false, has_assets_db: false,
        detail: "Tabelle 'uid_profile' fehlt" },
    ],
  };
}

function _main(win) {
  const el = win.document.createElement("div");
  win.document.body.appendChild(el);
  return el;
}

describe("cockpit_cases (Build 384)", () => {
  it("FE01 — API verfuegbar", () => {
    const api = _api();
    expect(typeof api.renderCases).toBe("function");
    expect(typeof api.toRows).toBe("function");
    expect(typeof api.importRequest).toBe("function");
  });

  it("FE02 — isSelectable: nur 'neu' MIT Benutzername", () => {
    const api = _api();
    expect(api.isSelectable({ status: "neu", username: "b19" })).toBe(true);
    // 'neu' ohne Namen -> der Server wuerde ihn zwingend abweisen.
    expect(api.isSelectable({ status: "neu", username: null })).toBe(false);
    expect(api.isSelectable({ status: "ok", username: "b18" })).toBe(false);
    expect(api.isSelectable({ status: "vermisst", username: "b21" })).toBe(false);
    expect(api.isSelectable({ status: "unlesbar", username: "x" })).toBe(false);
    expect(api.isSelectable(null)).toBe(false);

    expect(api.selectableIds(_data())).toEqual([19, 20]);
  });

  it("FE03 — toRows: Label, Arbeitsstand, Auswahl-Flag", () => {
    const rows = _api().toRows(_data());
    expect(rows).toHaveLength(5);

    const r19 = rows.find((r) => r.user_id === 19);
    expect(r19.status_label).toBe("neu (aufnehmbar)");
    expect(r19.selectable).toBe(true);
    expect(r19.evidence).toBe("\u2014");   // Arbeitsstand: noch nichts
    expect(r19.forensic).toBe("ja");

    const r21 = rows.find((r) => r.user_id === 21);
    expect(r21.status_label).toBe("VERMISST");
    expect(r21.forensic).toBe("\u2014");
    // Arbeitsstand ist da, die Quelle fehlt -> das ist der ernste Fall.
    expect(r21.evidence).toBe("ja");
    expect(r21.selectable).toBe(false);

    const r22 = rows.find((r) => r.user_id === 22);
    expect(r22.status_label).toBe("UNLESBAR");
    expect(r22.username).toBe("");
    expect(r22.detail).toContain("uid_profile");
  });

  it("FE04 — filterByStatus, countsText, dirsText", () => {
    const api = _api();
    const rows = api.toRows(_data());
    expect(api.filterByStatus(rows, "")).toHaveLength(5);
    expect(api.filterByStatus(rows, "neu")).toHaveLength(2);
    expect(api.filterByStatus(rows, "vermisst")).toHaveLength(1);

    const t = api.countsText(_data());
    expect(t).toContain("5 Fall/Faelle");
    expect(t).toContain("2 neu");
    expect(t).toContain("1 vermisst");
    expect(t).toContain("1 unlesbar");

    // WORUEBER wurde gemessen? Ohne das ist "nichts gefunden" wertlos.
    const d = api.dirsText(_data());
    expect(d).toContain("./data/forensic");
    expect(d).toContain("./data/evidence");
    expect(d).toContain("./data/assets");
  });

  it("FE05 — warningRows/warningLine: Missstaende MIT Grund (Grundregel 1)", () => {
    const api = _api();
    const warns = api.warningRows(_data());
    expect(warns.map((c) => c.user_id)).toEqual([21, 22]);

    const l21 = api.warningLine(warns[0]);
    expect(l21).toContain("VERMISST");
    expect(l21).toContain("21");
    expect(l21).toContain("forensic_21.db fehlt");

    const l22 = api.warningLine(warns[1]);
    expect(l22).toContain("UNLESBAR");
    expect(l22).toContain("uid_profile");
  });

  it("FE06 — importRequest: kein Leer-POST, kein {all:true}", () => {
    const api = _api();
    expect(api.importRequest([])).toBeNull();
    expect(api.importRequest(null)).toBeNull();
    expect(api.importRequest(["x"])).toBeNull();

    const req = api.importRequest([19, "20"]);
    expect(req.path).toBe("/api/cases/import");
    expect(req.body).toEqual({ user_ids: [19, 20] });
    expect(req.body.all).toBeUndefined();
  });

  it("FE07 — resultText: imported mit Beleg, skipped mit Grund", () => {
    const api = _api();

    const ok = api.resultText({
      imported: [{ user_id: 19, username: "b19", audit_seq: 77 }],
      skipped: [], count: 1,
    });
    expect(ok.error).toBe(false);
    expect(ok.text).toContain("Beleg #77");
    expect(ok.text).toContain("b19");

    // Ein uebersprungener Fall ist ein BEFUND, kein Erfolg.
    const mixed = api.resultText({
      imported: [{ user_id: 19, username: "b19", audit_seq: 77 }],
      skipped: [{ user_id: 22, reason: "Benutzername unlesbar" }],
      count: 1,
    });
    expect(mixed.error).toBe(true);
    expect(mixed.text).toContain("NICHT aufgenommen");
    expect(mixed.text).toContain("Benutzername unlesbar");

    const none = api.resultText({ imported: [], skipped: [], count: 0 });
    expect(none.text).toContain("Kein Fall aufgenommen");
  });

  it("FE08 — renderCases: Kopf, Zaehler, Filter, Knopf startet deaktiviert", () => {
    const win = _ctx();
    const api = win.AIWCockpitCases;
    const main = _main(win);

    const view = api.renderCases(main, _data(), {
      Tabulator: _fakeTabulator(win.document),
    });
    expect(view).toBeTruthy();
    expect(view.table).toBeTruthy();

    expect(main.querySelector(".aiw-pagehead").textContent)
      .toBe("Fall-Erkennung");
    expect(main.querySelector("#aiw-cases-counts").textContent)
      .toContain("2 neu");
    expect(main.querySelector("#aiw-cases-dirs").textContent)
      .toContain("./data/forensic");

    // Filter: alle + vier Zustaende.
    const sel = main.querySelector("#aiw-cases-filter");
    expect(sel.options).toHaveLength(5);

    // Nichts ausgewaehlt -> kein Schreibvorgang moeglich.
    const btn = main.querySelector("#aiw-cases-import");
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toContain("(0)");
    expect(view.getSelection()).toEqual([]);
  });

  it("FE09 — renderCases: WARNBEREICH nennt jeden Missstand", () => {
    const win = _ctx();
    const api = win.AIWCockpitCases;
    const main = _main(win);
    api.renderCases(main, _data(), { Tabulator: _fakeTabulator(win.document) });

    const warn = main.querySelector("#aiw-cases-warn");
    expect(warn).toBeTruthy();
    expect(warn.textContent).toContain("VERMISST");
    expect(warn.textContent).toContain("UNLESBAR");
    expect(warn.textContent).toContain("forensic_21.db fehlt");
    expect(warn.querySelectorAll("li")).toHaveLength(2);

    // Der Warnbereich steht VOR der Tabelle (er darf nicht untergehen).
    const tbl = main.querySelector("#aiw-cases-table");
    const pos = warn.compareDocumentPosition(tbl);
    expect(pos & win.Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Ohne Missstaende: kein Warnbereich.
    const clean = _data();
    clean.cases = clean.cases.filter(
      (c) => c.status !== "vermisst" && c.status !== "unlesbar");
    clean.counts = { ok: 1, neu: 2, vermisst: 0, unlesbar: 0 };
    clean.count = 3;
    const main2 = _main(win);
    api.renderCases(main2, clean, { Tabulator: _fakeTabulator(win.document) });
    expect(main2.querySelector("#aiw-cases-warn")).toBeNull();
  });

  it("FE10 — Auswahlkaestchen NUR bei aufnehmbaren Faellen", () => {
    const win = _ctx();
    const api = win.AIWCockpitCases;
    const main = _main(win);
    api.renderCases(main, _data(), { Tabulator: _fakeTabulator(win.document) });

    const boxes = main.querySelectorAll("#aiw-cases-table input[type=checkbox]");
    const ids = Array.from(boxes).map((b) => b.getAttribute("data-user-id"));
    // Nur 19 und 20 sind 'neu' MIT Namen. 18 (ok), 21 (vermisst) und 22
    // (unlesbar) bekommen KEIN Kaestchen — die Oberflaeche bietet keine
    // Aktion an, die serverseitig zwingend scheitern wuerde.
    expect(ids).toEqual(["19", "20"]);
  });

  it("FE10b — Auswahl -> Bestaetigung -> Ausfuehren (zweistufig)", () => {
    const win = _ctx();
    const api = win.AIWCockpitCases;
    const main = _main(win);
    const onImport = vi.fn();

    api.renderCases(main, _data(), {
      Tabulator: _fakeTabulator(win.document), onImport: onImport,
    });

    const btn = main.querySelector("#aiw-cases-import");
    const confirm = main.querySelector("#aiw-cases-confirm");
    expect(btn.disabled).toBe(true);

    // 1) Auswaehlen -> Knopf wird scharf, Zaehler stimmt.
    const box19 = main.querySelector("input[data-user-id='19']");
    box19.checked = true;
    box19.dispatchEvent(new win.Event("change"));
    expect(btn.disabled).toBe(false);
    expect(btn.textContent).toContain("(1)");

    // 2) Knopf -> BESTAETIGUNG, aber noch KEIN Schreibvorgang.
    btn.dispatchEvent(new win.Event("click"));
    expect(onImport).not.toHaveBeenCalled();
    expect(confirm.textContent).toContain("Beleg im audit_log");
    expect(confirm.textContent).toContain("Fall 19");
    expect(confirm.textContent).toContain("b19");

    // 3) Erst die Bestaetigung schreibt.
    main.querySelector("#aiw-cases-confirm-yes")
      .dispatchEvent(new win.Event("click"));
    expect(onImport).toHaveBeenCalledTimes(1);
    expect(onImport).toHaveBeenCalledWith([19]);
    expect(confirm.textContent).toBe("");   // Frage ist beantwortet
  });

  it("FE10c — Abbrechen schreibt NICHTS; Abwaehlen sperrt den Knopf wieder", () => {
    const win = _ctx();
    const api = win.AIWCockpitCases;
    const main = _main(win);
    const onImport = vi.fn();

    const view = api.renderCases(main, _data(), {
      Tabulator: _fakeTabulator(win.document), onImport: onImport,
    });

    const btn = main.querySelector("#aiw-cases-import");
    const box19 = main.querySelector("input[data-user-id='19']");
    const box20 = main.querySelector("input[data-user-id='20']");

    box19.checked = true;
    box19.dispatchEvent(new win.Event("change"));
    box20.checked = true;
    box20.dispatchEvent(new win.Event("change"));
    expect(view.getSelection()).toEqual([19, 20]);
    expect(btn.textContent).toContain("(2)");

    btn.dispatchEvent(new win.Event("click"));
    main.querySelector("#aiw-cases-confirm-no")
      .dispatchEvent(new win.Event("click"));
    expect(onImport).not.toHaveBeenCalled();
    expect(main.querySelector("#aiw-cases-result").textContent)
      .toContain("Es wurde nichts geschrieben");

    // Abwaehlen -> Knopf sperrt wieder (kein Schreiben ohne Auswahl).
    box19.checked = false;
    box19.dispatchEvent(new win.Event("change"));
    box20.checked = false;
    box20.dispatchEvent(new win.Event("change"));
    expect(view.getSelection()).toEqual([]);
    expect(btn.disabled).toBe(true);

    // Rueckmeldewege der Shell (nach POST/Reload) muessen tragen.
    view.setResult("Gespeichert.", false);
    expect(main.querySelector("#aiw-cases-result").classList
      .contains("ok")).toBe(true);
    view.showResult({
      imported: [], skipped: [{ user_id: 22, reason: "unlesbar" }], count: 0,
    });
    const res = main.querySelector("#aiw-cases-result");
    expect(res.classList.contains("error")).toBe(true);
    expect(res.textContent).toContain("unlesbar");
  });

  it("FE10d — Filterwechsel verliert die Auswahl NICHT still", () => {
    const win = _ctx();
    const api = win.AIWCockpitCases;
    const main = _main(win);

    const view = api.renderCases(main, _data(), {
      Tabulator: _fakeTabulator(win.document),
    });

    const box19 = main.querySelector("input[data-user-id='19']");
    box19.checked = true;
    box19.dispatchEvent(new win.Event("change"));
    expect(view.getSelection()).toEqual([19]);

    // Auf 'vermisst' filtern -> Fall 19 ist nicht mehr sichtbar.
    const sel = main.querySelector("#aiw-cases-filter");
    sel.value = "vermisst";
    sel.dispatchEvent(new win.Event("change"));
    expect(main.querySelectorAll("#aiw-cases-table .fake-row")).toHaveLength(1);

    // Die AUSWAHL lebt im Zustand, nicht im DOM -> sie bleibt bestehen.
    expect(view.getSelection()).toEqual([19]);
    expect(main.querySelector("#aiw-cases-import").textContent).toContain("(1)");
  });

  it("FE11 — ohne Tabellenbibliothek: Warnung und Zaehler stehen trotzdem", () => {
    const win = _ctx();
    const api = win.AIWCockpitCases;
    const main = _main(win);

    // Kein Ctor injiziert, window.Tabulator existiert nicht.
    const view = api.renderCases(main, _data(), {});
    expect(view.table).toBeNull();

    expect(main.querySelector("#aiw-cases-warn")).toBeTruthy();
    expect(main.querySelector("#aiw-cases-counts").textContent)
      .toContain("1 vermisst");
    expect(main.querySelector(".aiw-placeholder").textContent)
      .toContain("Tabellenbibliothek nicht verfuegbar");
    // Ohne Tabelle gibt es keine Auswahl -> kein Schreibvorgang.
    expect(main.querySelector("#aiw-cases-import").disabled).toBe(true);
  });
});
