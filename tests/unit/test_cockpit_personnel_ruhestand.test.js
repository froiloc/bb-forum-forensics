/**
 * tests/unit/test_cockpit_personnel_ruhestand.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ruhestand von Hand
 *
 * Testsuite fuer die Ruhestands-Bedienung in
 * management/server/static/cockpit_personnel.js (Build 701, Ticket
 * 95139d2a). EIGENE DATEI und keine Erweiterung von
 * test_cockpit_personnel.test.js: die dortige Suite prueft die LISTE, diese
 * hier den SCHREIBWEG einer Handlung mit Bestaetigung. Das sind zwei
 * Gegenstaende, und eine Datei, die beides fuehrt, sagt beim Fehlschlag
 * weniger darueber, was kaputt ist.
 *
 * WORAUF DIESE SUITE ZIELT: Der Knopf nimmt einem Menschen den Zugang zur
 * Anlage. Geprueft wird deshalb vor allem, was NICHT passiert — kein Vollzug
 * ohne Grund, kein Vollzug ohne exaktes Wort, kein Knopf an der eigenen
 * Zeile.
 *
 * RU01 — die reinen Funktionen sind exportiert.
 * RU02 — confirmWords nimmt die Worte vom Server; Rueckfall nur ohne Feld.
 * RU03 — validateWort vergleicht EXAKT (kein trim, keine Normalisierung).
 * RU04 — ruhestandFrage: aktiv -> 'Inaktiv setzen' mit Grundpflicht,
 *        inaktiv -> 'Reaktivieren' ohne; eigene Zeile und fehlendes Recht
 *        -> gar keine Frage (Selbstschutz).
 * RU05 — offeneFaelleText: Entwarnung, Warnung mit Zahl, und "nicht bekannt"
 *        statt einer erfundenen Null.
 * RU06 — die Spalte 'Ruhestand' traegt je Zeile den richtigen Knopf bzw.
 *        einen Strich MIT Begruendung im Tooltip.
 * RU07 — Klick oeffnet den Bestaetigungsblock; ohne Grund und mit falschem
 *        Wort wird NICHT vollzogen, und die Rueckmeldung sagt warum.
 * RU08 — mit Grund und exaktem Wort -> onSetActive mit vollstaendigem Koerper.
 * RU09 — immer nur EINE Frage offen; 'Abbrechen' raeumt sie folgenlos weg.
 * RU10 — der Hinweis auf nicht feststellbare Fallzahlen erscheint in der
 *        Sicht (nicht erst im Block).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_personnel.js",
  "utf-8"
);
const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

/** Tabulator-Attrappe (wie in test_cockpit_personnel.test.js): sie MUSS die
 *  Formatter aufrufen — der Ruhestands-Knopf entsteht in einem Formatter. */
function _fakeTabulator(doc) {
  return function (container, options) {
    const self = this;
    this.container = container;
    this.options = options;
    this.data = options.data;
    this._filters = [];
    this._render = function (rows) {
      container.textContent = "";
      (rows || []).forEach(function (d) {
        const tr = doc.createElement("div");
        tr.setAttribute("data-row-id", String(d.id));
        (options.columns || []).forEach(function (col) {
          if (typeof col.formatter !== "function") { return; }
          const node = col.formatter({ getData: function () { return d; } });
          if (node && node.nodeType) { tr.appendChild(node); }
        });
        container.appendChild(tr);
      });
    };
    this._render(this.data);
    this.getDataCount = function () { return self.data.length; };
    this.setHeaderFilterValue = function (f, v) { self._filters.push([f, v]); };
    this.clearHeaderFilter = function () { self._filters = []; };
    this.clearFilter = function () { self._filters = []; };
    this.getHeaderFilters = function () { return []; };
    this.getSorters = function () { return []; };
    this.getColumns = function () { return []; };
    this.setSort = function () {};
    this.replaceData = function (d) { self.data = d; self._render(d); };
    this.destroy = function () {};
  };
}

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_tkSrc);
  dom.window.eval(_src);
  return dom.window;
}

function _render(win, main, data, opts) {
  return win.AIWCockpitPersonnel.renderPersonnel(
    main,
    data,
    Object.assign(
      { doc: win.document, Tabulator: _fakeTabulator(win.document) },
      opts || {}
    )
  );
}

/** Drei Personen: 1 = eigene (Chefin), 2 = aktiv mit 2 offenen Faellen,
 *  3 = bereits inaktiv. */
function _data(overrides) {
  return Object.assign(
    {
      persons: [
        { id: 1, system_username: "h0chef", display_name: "Chefin",
          is_investigator: false, is_supervisor: true, is_support: false,
          is_active: true, deactivated_at: null, deactivated_reason: null,
          offene_faelle: 0, roles: [] },
        { id: 2, system_username: "h0erm", display_name: "KHK Muster",
          is_investigator: true, is_supervisor: false, is_support: false,
          is_active: true, deactivated_at: null, deactivated_reason: null,
          offene_faelle: 2, roles: [] },
        { id: 3, system_username: "h0weg", display_name: "KOK Weg",
          is_investigator: true, is_supervisor: false, is_support: false,
          is_active: false, deactivated_at: 1753300000,
          deactivated_reason: "ausgeschieden", offene_faelle: 0, roles: [] },
      ],
      roles_catalog: [{ code: "investigator", label: "Ermittler:in" }],
      actor_person_id: 1,
      can_edit: true,
      can_sync: false,
      confirm: { deactivate: "Entfernen", reactivate: "Reaktivieren" },
      offene_faelle_hinweis: null,
    },
    overrides || {}
  );
}

/** Die Zeile im gerenderten Baum (die Attrappe setzt data-row-id). */
function _zeile(main, id) {
  return main.querySelector('[data-row-id="' + id + '"]');
}

describe("cockpit_personnel — Ruhestand (Build 701)", () => {
  // RU01 ---------------------------------------------------------------------
  it("RU01: reine Funktionen exportiert", () => {
    const api = _ctx().AIWCockpitPersonnel;
    for (const fn of ["confirmWords", "validateWort", "ruhestandFrage",
                      "offeneFaelleText", "activeBody",
                      "renderRuhestandBlock"]) {
      expect(typeof api[fn], fn).toBe("function");
    }
  });

  // RU02 ---------------------------------------------------------------------
  it("RU02: Bestaetigungsworte kommen vom Server", () => {
    const api = _ctx().AIWCockpitPersonnel;
    expect(api.confirmWords(_data())).toEqual({
      deactivate: "Entfernen", reactivate: "Reaktivieren",
    });
    // Der Server ist die Wahrheitsquelle: ein anderes Wort wird uebernommen,
    // nicht durch das eingebaute ersetzt.
    expect(api.confirmWords({ confirm: { deactivate: "Weg" } }).deactivate)
      .toBe("Weg");
    // Rueckfall NUR ohne Feld (Altserver).
    expect(api.confirmWords({}).reactivate).toBe("Reaktivieren");
  });

  // RU03 ---------------------------------------------------------------------
  it("RU03: validateWort vergleicht exakt", () => {
    const api = _ctx().AIWCockpitPersonnel;
    expect(api.validateWort("Entfernen", "Entfernen")).toBe(true);
    // Eine grosszuegigere Pruefung waere schlimmer als gar keine: sie liesse
    // durch, was der Server dann doch abweist.
    expect(api.validateWort("Entfernen", "entfernen")).toBe(false);
    expect(api.validateWort("Entfernen", " Entfernen")).toBe(false);
    expect(api.validateWort("Entfernen", "Entfernen ")).toBe(false);
    expect(api.validateWort("Entfernen", null)).toBe(false);
    expect(api.validateWort("Entfernen", undefined)).toBe(false);
  });

  // RU04 ---------------------------------------------------------------------
  it("RU04: ruhestandFrage — Richtung, Grundpflicht, Selbstschutz", () => {
    const api = _ctx().AIWCockpitPersonnel;
    const rows = api.toRows(_data());
    const words = api.confirmWords(_data());
    const je = {};
    rows.forEach((r) => { je[r.id] = r; });

    const aktiv = api.ruhestandFrage(je[2], words);
    expect(aktiv.aktion).toBe("deactivate");
    expect(aktiv.active).toBe(false);
    expect(aktiv.wort).toBe("Entfernen");
    expect(aktiv.braucht_grund).toBe(true);

    const inaktiv = api.ruhestandFrage(je[3], words);
    expect(inaktiv.aktion).toBe("reactivate");
    expect(inaktiv.active).toBe(true);
    expect(inaktiv.wort).toBe("Reaktivieren");
    // Beim Reaktivieren gibt es nichts zu begruenden — der alte Grund steht
    // im Beleg der Deaktivierung.
    expect(inaktiv.braucht_grund).toBe(false);

    // SELBSTSCHUTZ: die eigene Zeile bietet gar nichts an.
    expect(api.ruhestandFrage(je[1], words)).toBe(null);
    // Ohne Aenderungsrecht ebenfalls nichts.
    const ohneRecht = api.toRows(_data({ can_edit: false }));
    expect(api.ruhestandFrage(ohneRecht[1], words)).toBe(null);
  });

  // RU05 ---------------------------------------------------------------------
  it("RU05: offeneFaelleText — Entwarnung, Warnung, Unkenntnis", () => {
    const api = _ctx().AIWCockpitPersonnel;
    expect(api.offeneFaelleText({ offene_faelle: 0 }))
      .toBe("Keine offenen Fälle zugewiesen.");
    const zwei = api.offeneFaelleText({ offene_faelle: 2 });
    expect(zwei).toContain("ACHTUNG");
    expect(zwei).toContain("2 offene Fälle");
    expect(api.offeneFaelleText({ offene_faelle: 1 })).toContain("1 offenen Fall");
    // KEINE ERFUNDENE NULL: fehlt die Angabe, wird das gesagt.
    const unbekannt = api.offeneFaelleText({});
    expect(unbekannt).toContain("nicht bekannt");
    expect(unbekannt).not.toContain("Keine offenen");
  });

  // RU06 ---------------------------------------------------------------------
  it("RU06: die Spalte traegt je Zeile den richtigen Knopf", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    w.document.body.appendChild(main);
    _render(w, main, _data());

    const knopf2 = _zeile(main, 2).querySelector(".aiw-pers-ruhe-btn");
    expect(knopf2.textContent).toBe("Inaktiv setzen");
    expect(knopf2.getAttribute("data-hilfe-id"))
      .toBe("personnel.bedienung.ruhestand_inaktiv");

    const knopf3 = _zeile(main, 3).querySelector(".aiw-pers-ruhe-btn");
    expect(knopf3.textContent).toBe("Reaktivieren");
    expect(knopf3.getAttribute("data-hilfe-id"))
      .toBe("personnel.bedienung.ruhestand_reaktivieren");

    // Eigene Zeile: kein Knopf — aber der Grund wird BENANNT. Eine leere
    // Zelle liesse offen, ob die Funktion fehlt oder das Recht.
    expect(_zeile(main, 1).querySelector(".aiw-pers-ruhe-btn")).toBe(null);
    const titel = Array.from(_zeile(main, 1).querySelectorAll("span"))
      .map((s) => s.title || "").join(" | ");
    expect(titel).toContain("Lockout-Schutz");
  });

  // RU07 ---------------------------------------------------------------------
  it("RU07: kein Vollzug ohne Grund und ohne exaktes Wort", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    w.document.body.appendChild(main);
    const gerufen = [];
    const view = _render(w, main, _data(), {
      onSetActive: (b) => gerufen.push(b),
    });

    _zeile(main, 2).querySelector(".aiw-pers-ruhe-btn")
      .dispatchEvent(new w.Event("click"));
    const block = main.querySelector(".aiw-pers-ruhestand");
    expect(block, "kein Bestaetigungsblock").toBeTruthy();
    // Er nennt die offenen Faelle — sonst waere die Zahl im Paket nutzlos.
    expect(block.textContent).toContain("2 offene Fälle");

    const grund = block.querySelector(".aiw-pers-grund");
    const wort = block.querySelector(".aiw-pers-wort");
    const vollzug = block.querySelector(".aiw-pers-ruhe-btn.vollzug");
    const ergebnis = main.querySelector(".aiw-pers-result");

    // (a) nichts eingegeben -> kein Vollzug, Rueckmeldung nennt den Grund.
    vollzug.dispatchEvent(new w.Event("click"));
    expect(gerufen.length).toBe(0);
    expect(ergebnis.textContent).toContain("Grund ist Pflicht");

    // (b) Grund da, Wort falsch geschrieben -> weiterhin kein Vollzug.
    grund.value = "ausgeschieden zum 31.08.";
    wort.value = "entfernen";
    vollzug.dispatchEvent(new w.Event("click"));
    expect(gerufen.length).toBe(0);
    expect(ergebnis.textContent).toContain("Bestätigungswort");
    expect(view).toBeTruthy();
  });

  // RU08 ---------------------------------------------------------------------
  it("RU08: mit Grund und exaktem Wort -> vollstaendiger Koerper", () => {
    const w = _ctx();
    const api = w.AIWCockpitPersonnel;
    const main = w.document.createElement("div");
    w.document.body.appendChild(main);
    const gerufen = [];
    _render(w, main, _data(), { onSetActive: (b) => gerufen.push(b) });

    _zeile(main, 2).querySelector(".aiw-pers-ruhe-btn")
      .dispatchEvent(new w.Event("click"));
    const block = main.querySelector(".aiw-pers-ruhestand");
    block.querySelector(".aiw-pers-grund").value = "ausgeschieden";
    block.querySelector(".aiw-pers-wort").value = "Entfernen";
    block.querySelector(".aiw-pers-ruhe-btn.vollzug")
      .dispatchEvent(new w.Event("click"));

    expect(gerufen).toEqual([{
      person_id: 2, active: false, reason: "ausgeschieden",
      confirmation: "Entfernen",
    }]);

    // Und das Gegenstueck: beim Reaktivieren wandert KEIN reason mit.
    expect(api.activeBody(3, true, "", "Reaktivieren")).toEqual({
      person_id: 3, active: true, confirmation: "Reaktivieren",
    });
  });

  // RU09 ---------------------------------------------------------------------
  it("RU09: nur EINE Frage offen; Abbrechen ist folgenlos", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    w.document.body.appendChild(main);
    const gerufen = [];
    _render(w, main, _data(), { onSetActive: (b) => gerufen.push(b) });

    _zeile(main, 2).querySelector(".aiw-pers-ruhe-btn")
      .dispatchEvent(new w.Event("click"));
    _zeile(main, 3).querySelector(".aiw-pers-ruhe-btn")
      .dispatchEvent(new w.Event("click"));
    // Zwei Bloecke mit je einer Wort-Eingabe waeren die perfekte Falle:
    // tippen im einen, druecken im anderen.
    const bloecke = main.querySelectorAll(".aiw-pers-ruhestand");
    expect(bloecke.length).toBe(1);
    // Der zuletzt geoeffnete gilt — hier die Reaktivierung, also OHNE
    // Grundfeld.
    expect(bloecke[0].querySelector(".aiw-pers-grund")).toBe(null);

    bloecke[0].querySelector(".aiw-pers-ruhe-btn.abbruch")
      .dispatchEvent(new w.Event("click"));
    expect(main.querySelectorAll(".aiw-pers-ruhestand").length).toBe(0);
    expect(gerufen.length).toBe(0);
  });

  // RU10 ---------------------------------------------------------------------
  it("RU10: unbekannte Fallzahlen werden in der Sicht benannt", () => {
    const w = _ctx();
    const main = w.document.createElement("div");
    w.document.body.appendChild(main);
    _render(w, main, _data({
      offene_faelle_hinweis: "Offene Faelle je Person nicht feststellbar (x)",
    }));
    const warn = main.querySelector(".aiw-pers-hint.warn");
    expect(warn, "kein Hinweis auf die Luecke").toBeTruthy();
    expect(warn.textContent).toContain("nicht feststellbar");
  });
});
