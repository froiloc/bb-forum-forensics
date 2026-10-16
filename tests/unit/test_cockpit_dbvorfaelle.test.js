/**
 * tests/unit/test_cockpit_dbvorfaelle.test.js
 * IT-Forensisches Ermittlungswerkzeug — Cockpit: Register Datenbank-Vorfaelle
 *
 * Testsuite fuer management/server/static/cockpit_dbvorfaelle.js (Build 777).
 * Getestet wird der ECHTE Code (readFileSync + JSDOM,
 * window.AIWCockpitDbVorfaelle) — mit dem gemeinsamen Tabellen-Werkzeug im
 * Kontext, damit die Tabelle wirklich gebaut wird (Lehre Build 557).
 *
 * DV-JS01 — API verfuegbar.
 * DV-JS02 — fmtTs deterministisch (UTC), leer -> Gedankenstrich.
 * DV-JS03 — ergebnisStufe: nicht freigegeben/verweigert rot, freigegeben
 *           gelb, unbekannt grau.
 * DV-JS04 — pufferModell: Fehler rot, wartend rot mit Liste, leer gruen.
 * DV-JS05 — toRows: Felder, '(nachgetragen)', Gedankenstriche.
 * DV-JS06 — render: Kopf, Zaehler, Puffer; mit Recht Pruefknopf nur an
 *           offenen Vorfaellen; ohne Recht Hinweis und KEIN Pruefknopf.
 * DV-JS07 — Pruefung: leere Notiz -> KEIN onPruefen + Fehlermeldung;
 *           mit Notiz -> onPruefen({id, notiz}).
 * DV-JS08 — Befund: als Text (textContent), unlesbarer Befund mit
 *           Fehlerangabe; Pruefvermerk wird genannt.
 * DV-JS09 — Filter ruft onFilter mit dem gewaehlten Wert.
 *
 * Version: v0.8.777 · Build: 777 · 2026-10-14
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_dbvorfaelle.js", "utf-8");
const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js", "utf-8");

/** Tabulator-Attrappe (Muster test_cockpit_promotion.test.js). */
function _fakeTabulator(doc) {
  return function (host, options) {
    const self = this;
    this.options = options;
    this.data = options.data || [];
    this._filters = [];
    this.data.forEach(function (d) {
      const tr = doc.createElement("div");
      tr.className = "fake-row";
      tr.setAttribute("data-id", String(d.id));
      (options.columns || []).forEach(function (col) {
        if (typeof col.formatter !== "function") {
          const sp = doc.createElement("span");
          sp.textContent = String(d[col.field] == null ? "" : d[col.field]);
          tr.appendChild(sp);
          return;
        }
        const node = col.formatter({
          getData: function () { return d; },
          getValue: function () { return d[col.field]; },
        });
        if (node && node.nodeType) { tr.appendChild(node); }
      });
      host.appendChild(tr);
    });
    this.getDataCount = function () { return self.data.length; };
    this.setHeaderFilterValue = function (f, v) { self._filters.push([f, v]); };
    this.clearHeaderFilter = function () { self._filters = []; };
    this.clearFilter = function () { self._filters = []; };
    this.getHeaderFilters = function () { return self._filters; };
    this.getSorters = function () { return []; };
    this.getColumns = function () { return []; };
    this.on = function () {};
    this.destroy = function () {};
  };
}

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously", url: "http://localhost",
  });
  dom.window.eval(_tkSrc);
  dom.window.eval(_src);
  return dom.window;
}

function _render(win, main, data, opts) {
  return win.AIWCockpitDbVorfaelle.renderDbVorfaelle(
    main, data,
    Object.assign({ doc: win.document, Tabulator: _fakeTabulator(win.document) },
                  opts || {}));
}

function _daten(kannPruefen) {
  return {
    status_filter: "alle",
    zaehler: { offen: 1, geprueft: 1 },
    kann_pruefen: kannPruefen,
    puffer: { verzeichnis: "G:\\sich\\defekt\\ausstehende_vorfaelle",
              anzahl: 0, eintraege: [], fehler: null },
    vorfaelle: [
      { id: 2, vorfall_uid: "b".repeat(32), erkannt_at: 1760000000,
        erfasst_at: 1760000300, nachgetragen: true,
        art: "startpruefung_evidence", art_klartext: "Startprüfung",
        ergebnis: "repariert_nicht_freigegeben",
        ergebnis_klartext: "NICHT freigegeben", subject_id: 4711,
        datei: "D:\\data\\evidence_4711.db", host: "VM1", person_id: 2,
        person_name: "Beta", befund: { verloren: { annotations: 3 },
          text: "<b>kein HTML</b>" },
        befund_fehler: null, status: "offen", audit_seq: 50,
        geprueft_von: null, geprueft_von_name: null, geprueft_at: null,
        pruef_notiz: null, pruef_audit_seq: null },
      { id: 1, vorfall_uid: "a".repeat(32), erkannt_at: 1750000000,
        erfasst_at: 1750000000, nachgetragen: false,
        art: "startpruefung_evidence", art_klartext: "Startprüfung",
        ergebnis: "repariert_freigegeben", ergebnis_klartext: "freigegeben",
        subject_id: null, datei: "", host: null, person_id: null,
        person_name: null, befund: null, befund_roh: "{kaputt",
        befund_fehler: "Befund ist kein gueltiges JSON: x",
        status: "geprueft", audit_seq: 40, geprueft_von: 1,
        geprueft_von_name: "Leitung", geprueft_at: 1750000500,
        pruef_notiz: "Protokoll gelesen", pruef_audit_seq: 41 },
    ],
  };
}

describe("cockpit_dbvorfaelle.js — Register Datenbank-Vorfaelle (Build 777)", () => {
  it("DV-JS01: API verfuegbar", () => {
    const api = _win().AIWCockpitDbVorfaelle;
    expect(typeof api.renderDbVorfaelle).toBe("function");
    expect(typeof api.toRows).toBe("function");
    expect(api.FILTER.map((f) => f.wert)).toEqual(["alle", "offen", "geprueft"]);
  });

  it("DV-JS02: fmtTs", () => {
    const api = _win().AIWCockpitDbVorfaelle;
    expect(api.fmtTs(0)).toBe("1970-01-01 00:00:00 UTC");
    expect(api.fmtTs(1760000000)).toBe("2025-10-09 08:53:20 UTC");
    expect(api.fmtTs(null)).toBe("—");
    expect(api.fmtTs("abc")).toBe("abc");
  });

  it("DV-JS03: ergebnisStufe", () => {
    const api = _win().AIWCockpitDbVorfaelle;
    expect(api.ergebnisStufe("repariert_nicht_freigegeben")).toBe("rot");
    expect(api.ergebnisStufe("start_verweigert")).toBe("rot");
    expect(api.ergebnisStufe("repariert_freigegeben")).toBe("gelb");
    // Build 778: unterbrochener Schreibvorgang zurueckgerollt.
    expect(api.ergebnisStufe("journal_zurueckgerollt")).toBe("gelb");
    expect(api.ergebnisStufe("neu_und_unbekannt")).toBe("grau");
  });

  it("DV-JS04: pufferModell", () => {
    const api = _win().AIWCockpitDbVorfaelle;
    const f = api.pufferModell({ puffer: { fehler: "OSError: weg" } });
    expect(f.stufe).toBe("rot");
    expect(f.text).toContain("OSError: weg");
    const w = api.pufferModell({ puffer: { anzahl: 2, verzeichnis: "P",
      eintraege: [{ datei: "x" }, { datei: "y", fehler: "kaputt" }] } });
    expect(w.stufe).toBe("rot");
    expect(w.text).toContain("2 Vorfälle warten");
    expect(w.eintraege.length).toBe(2);
    const e = api.pufferModell({ puffer: { anzahl: 0 } });
    expect(e.stufe).toBe("gruen");
    expect(api.pufferModell({}).stufe).toBe("gruen");
  });

  it("DV-JS05: toRows", () => {
    const api = _win().AIWCockpitDbVorfaelle;
    const r = api.toRows(_daten(true));
    expect(r[0].erkannt).toBe("2025-10-09 08:53:20 UTC (nachgetragen)");
    expect(r[0].subject_id).toBe(4711);
    expect(r[0].stufe).toBe("rot");
    expect(r[0].person).toBe("Beta");
    expect(r[0].offen).toBe(true);
    expect(r[1].subject_id).toBe("—");
    expect(r[1].datei).toBe("—");
    expect(r[1].rechner).toBe("—");
    expect(r[1].person).toBe("—");
    expect(r[1].status).toBe("geprüft");
    expect(api.toRows({})).toEqual([]);
  });

  it("DV-JS06: render mit und ohne Recht", () => {
    const win = _win();
    const main = win.document.createElement("div");
    _render(win, main, _daten(true));
    expect(main.querySelector('[data-hilfe-id="dbvorfaelle.titel"]').textContent)
      .toBe("Datenbank-Vorfälle");
    const zaehler = main.querySelector('[data-hilfe-id="dbvorfaelle.zahlen"]');
    expect(zaehler.textContent).toContain("offen: 1");
    expect(zaehler.querySelector('[data-status="offen"] .dot').className)
      .toContain("rot");
    expect(main.querySelector("#aiw-dbv-puffer").className).toContain("gruen");
    const pruef = main.querySelectorAll('button[data-aktion="pruefen"]');
    expect(pruef.length).toBe(1);                 // nur der offene Vorfall
    expect(pruef[0].getAttribute("data-id")).toBe("2");
    expect(main.querySelectorAll('button[data-aktion="befund"]').length).toBe(2);
    expect(main.querySelector(".aiw-dbv-readonly")).toBeNull();

    const main2 = win.document.createElement("div");
    _render(win, main2, _daten(false));
    expect(main2.querySelectorAll('button[data-aktion="pruefen"]').length).toBe(0);
    expect(main2.querySelector(".aiw-dbv-readonly").textContent)
      .toContain("wartung.durchfuehren");

    // Wartender Puffer wird mit Liste gezeigt.
    const d = _daten(true);
    d.puffer = { verzeichnis: "P", anzahl: 1, fehler: null, eintraege: [
      { datei: "P/db_vorfall_x.json", erkannt_at: 0, subject_id: 9,
        ergebnis: "start_verweigert", fehler: null }] };
    const main3 = win.document.createElement("div");
    _render(win, main3, d);
    const p = main3.querySelector("#aiw-dbv-puffer");
    expect(p.className).toContain("rot");
    expect(p.querySelectorAll("li").length).toBe(1);
    expect(p.textContent).toContain("Fall 9");
  });

  it("DV-JS07: Pruefung — Notiz ist Pflicht", () => {
    const win = _win();
    const main = win.document.createElement("div");
    const gerufen = [];
    _render(win, main, _daten(true), { onPruefen: (b) => gerufen.push(b) });
    main.querySelector('button[data-aktion="pruefen"]').click();
    const ta = main.querySelector("#aiw-dbv-notiz");
    expect(ta.getAttribute("data-hilfe-id")).toBe("dbvorfaelle.bedienung.notiz");
    ta.value = "   ";
    main.querySelector("#aiw-dbv-bestaetigen").click();
    expect(gerufen).toEqual([]);
    expect(main.querySelector("#aiw-dbv-result").textContent)
      .toContain("Pflicht");
    ta.value = " Protokoll gelesen ";
    main.querySelector("#aiw-dbv-bestaetigen").click();
    expect(gerufen).toEqual([{ id: 2, notiz: "Protokoll gelesen" }]);
    // Abbrechen schreibt nichts.
    main.querySelector('button[data-aktion="pruefen"]').click();
    main.querySelector("#aiw-dbv-abbrechen").click();
    expect(gerufen.length).toBe(1);
    expect(main.querySelector("#aiw-dbv-panel").textContent).toBe("");
  });

  it("DV-JS08: Befund als Text, unlesbarer Befund mit Fehler", () => {
    const win = _win();
    const main = win.document.createElement("div");
    _render(win, main, _daten(true));
    const knoepfe = main.querySelectorAll('button[data-aktion="befund"]');
    knoepfe[0].click();
    const pre = main.querySelector("pre.aiw-dbv-befund");
    expect(pre.textContent).toContain('"annotations": 3');
    expect(pre.textContent).toContain("<b>kein HTML</b>");
    expect(pre.querySelector("b")).toBeNull();     // kein innerHTML
    knoepfe[1].click();
    const pre2 = main.querySelector("pre.aiw-dbv-befund");
    expect(pre2.textContent).toContain("kein gueltiges JSON");
    expect(pre2.textContent).toContain("{kaputt");
    expect(main.querySelector(".aiw-dbv-vermerk").textContent)
      .toContain("Geprüft von Leitung");
    main.querySelector("#aiw-dbv-schliessen").click();
    expect(main.querySelector("#aiw-dbv-panel").textContent).toBe("");
  });

  it("DV-JS09: Filter", () => {
    const win = _win();
    const main = win.document.createElement("div");
    const gewaehlt = [];
    const d = _daten(true);
    d.status_filter = "offen";
    _render(win, main, d, { onFilter: (w) => gewaehlt.push(w) });
    const sel = main.querySelector("#aiw-dbv-filter");
    expect(sel.value).toBe("offen");
    sel.value = "geprueft";
    sel.dispatchEvent(new win.Event("change"));
    expect(gewaehlt).toEqual(["geprueft"]);
  });
});
