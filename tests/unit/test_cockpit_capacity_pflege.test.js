/**
 * tests/unit/test_cockpit_capacity_pflege.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 559: die Pflegeflaeche der Kapazitaet.
 *
 * Die Konformitaet der vier Tabellen (Werkzeugleiste, Filter, Trefferzahl,
 * Hilfe-Anker) prueft bereits test_cockpit_tabellen_ux.test.js ueber vier
 * Register-Eintraege. HIER steht das, was DIESE Sicht ausmacht:
 *
 * CP01 — wochenSumme addiert die sieben Wochentage und vertraegt Luecken.
 * CP02 — wertText zeigt Prozent ODER Minuten, nie beides, nie "null".
 * CP03 — ein Grund, den es im Katalog nicht (mehr) gibt, wird als
 *        "code (unbekannt)" AUSGEWIESEN und nicht zu einer leeren Zelle.
 * CP04 — die Rechenart-Auswahl kommt aus data.kinds (Server), nicht aus einer
 *        im Frontend nachgebauten Liste.
 * CP05 — scope 'eigene': keine Personenauswahl, KEINE Schreibformulare fuer
 *        Feiertage/Gruende — und die Tabellen stehen trotzdem.
 * CP06 — scope 'eigene': der Grund fuer die fehlenden Formulare STEHT DA.
 * CP07 — der Append-only-Hinweis steht an den Arbeitszeiten.
 * CP08 — ohne Tabellenmechanik: Ersatzmeldung MIT Zeilenzahl je Abschnitt
 *        (Grundregel 1) statt leerer Flaeche.
 * CP09 — die Schreib-Rueckrufe bekommen genau das, was der Endpunkt erwartet;
 *        leere Zahlenfelder werden zu null und NICHT zu 0.
 * CP10 — Freitext wird als Text gesetzt, nicht als Auszeichnung (XSS).
 * CP11 — der Formularzustand ueberlebt das Neuzeichnen (Befund mc, B560):
 *        Stichtag, Personenauswahl und Minutenwerte stehen wieder da.
 * CP12 — ohne Zustand ist der Stichtag mit HEUTE vorbelegt, nicht leer.
 * CP13 — markiereFeld setzt die Markierung genau auf das genannte Feld und
 *        raeumt eine vorherige weg; ein unbekanntes Feld markiert NICHTS.
 * CP14 — die Tagesvorgaben setzen Mo-Fr und nullen Sa/So.
 * CP15 — Bearbeitungsmodus: Knopfbeschriftung, Warnhinweis, Abbruch, und das
 *        Speichern geht auf ERSETZEN statt auf Anlegen.
 * CP16 — uebernahmeText schreibt aus, WAS uebernommen wurde.
 * CP17 — die Aktionsspalte bietet Bearbeiten UND Entfernen je Zeile.
 * CP18 — die Zahl ausgeblendeter Zeilen steht da, AUCH wenn der Schalter aus
 *        ist — sonst ahnt niemand, dass es etwas einzublenden gibt.
 * CP19 — ist nichts entfernt, steht auch kein Hinweis (kein "0 Zeilen").
 * CP20 — eingeschalteter Schalter: Spalte 'Stand', Zeilenklasse, und die
 *        Aktionsknoepfe entfallen auf entfernten Zeilen.
 * CP21 — Umschalten ruft den Rueckruf mit dem neuen Zustand.
 *
 * Version: v0.8.563 · Build: 563 · 2026-07-29
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);
const _src = readFileSync(
  "management/server/static/cockpit_capacity_pflege.js",
  "utf-8"
);

/** Tabulator-Attrappe: ruft die Spalten-Formatter auf, damit die Knoepfe der
 *  Aktionsspalte wirklich entstehen (die Lehre aus Build 555). */
function _fakeTabulator(doc) {
  return function (host, options) {
    this.options = options;
    this.data = options.data || [];
    (this.data || []).forEach(function (d) {
      const tr = doc.createElement("div");
      tr.className = "fake-row";
      (options.columns || []).forEach(function (col) {
        let node = null;
        if (typeof col.formatter === "function") {
          try {
            node = col.formatter({
              getData: () => d,
              getValue: () => d[col.field],
            });
          } catch (e) { /* unerheblich */ }
        } else {
          node = doc.createElement("span");
          node.textContent = String(d[col.field] === undefined ? "" : d[col.field]);
        }
        if (node && node.nodeType) { tr.appendChild(node); }
      });
      host.appendChild(tr);
    });
    this.setFilter = function () {};
    this.clearFilter = function () {};
    this.clearHeaderFilter = function () {};
    this.getHeaderFilters = function () { return []; };
    this.getSorters = function () { return []; };
    this.getDataCount = function (m) { return m ? this.data.length : this.data.length; };
    this.on = function () {};
    this.getColumns = function () { return []; };
  };
}

function _win(mitTk) {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  if (mitTk !== false) { dom.window.eval(_tkSrc); }
  dom.window.eval(_src);
  return dom.window;
}

function _daten(scope) {
  return {
    scope: scope || "alle",
    person_id: scope === "eigene" ? 2 : null,
    persons: [
      { id: 2, system_username: "h002", display_name: "Mueller" },
      { id: 3, system_username: "h003", display_name: "Gamma" },
    ],
    worktimes: [
      { id: 1, person_id: 2, display_name: "Mueller", mon_min: 480,
        tue_min: 480, wed_min: 480, thu_min: 480, fri_min: 480, sat_min: 0,
        sun_min: 0, effective_from: "2026-01-01", effective_to: null,
        audit_seq: 11 },
    ],
    availability: [
      { id: 5, person_id: 2, display_name: "Mueller",
        period_start: "2026-07-06", period_end: "2026-07-10",
        kind: "einschraenkung", value_pct: 50, value_minutes: null,
        reason_code: "urlaub", note: "Jahresurlaub", audit_seq: 13 },
    ],
    holidays: [
      { id: 9, day: "2026-07-08", label: "Testfeiertag", region: null,
        audit_seq: 14 },
    ],
    reasons: [{ code: "urlaub", label: "Urlaub", sort: 10, audit_seq: 15 }],
    counts: { worktimes: 1, availability: 1, holidays: 1, reasons: 1,
              persons: 2 },
    kinds: [
      { code: "einschraenkung", label: "Einschraenkung" },
      { code: "garantie", label: "Garantie (Mindestboden)" },
    ],
  };
}

function _zeichne(win, opts) {
  const main = win.document.createElement("div");
  win.document.body.appendChild(main);
  const o = Object.assign({ Tabulator: _fakeTabulator(win.document) },
                          opts || {});
  const view = win.AIWCockpitCapacityPflege.renderCapacityPflege(
    main, o._daten || _daten("alle"), o);
  return { main, view };
}

describe("Kapazitaetspflege (Build 559)", () => {
  // CP01 --------------------------------------------------------------------
  it("CP01: wochenSumme addiert sieben Tage und vertraegt Luecken", () => {
    const api = _win().AIWCockpitCapacityPflege;
    expect(api.wochenSumme({
      mon_min: 480, tue_min: 480, wed_min: 480, thu_min: 480, fri_min: 480,
      sat_min: 0, sun_min: 0,
    })).toBe(2400);
    // Fehlende und unbrauchbare Werte zaehlen als 0 — die Summe bleibt eine
    // Zahl und wird nicht zu NaN, das in der Zelle als "NaN" stuende.
    expect(api.wochenSumme({ mon_min: 60 })).toBe(60);
    expect(api.wochenSumme({ mon_min: "viel" })).toBe(0);
    expect(api.wochenSumme(null)).toBe(0);
  });

  // CP02 --------------------------------------------------------------------
  it("CP02: wertText zeigt Prozent ODER Minuten, nie 'null'", () => {
    const api = _win().AIWCockpitCapacityPflege;
    expect(api.wertText({ value_pct: 50, value_minutes: null })).toBe("50 %");
    expect(api.wertText({ value_pct: null, value_minutes: 600 }))
      .toBe("600 min");
    expect(api.wertText({ value_pct: null, value_minutes: null })).toBe("");
    // 0 ist eine ANGABE und darf nicht als "keine Angabe" durchfallen.
    expect(api.wertText({ value_pct: 0, value_minutes: null })).toBe("0 %");
  });

  // CP03 --------------------------------------------------------------------
  it("CP03: unbekannter Grund wird ausgewiesen, nicht verschwiegen", () => {
    const api = _win().AIWCockpitCapacityPflege;
    const katalog = [{ code: "urlaub", label: "Urlaub" }];
    expect(api.reasonLabel("urlaub", katalog)).toBe("Urlaub");
    expect(api.reasonLabel("stillgelegt", katalog))
      .toBe("stillgelegt (unbekannt)");
    expect(api.reasonLabel(null, katalog)).toBe("");
  });

  // CP04 --------------------------------------------------------------------
  it("CP04: die Rechenart-Auswahl stammt aus data.kinds", () => {
    const win = _win();
    const daten = _daten("alle");
    daten.kinds = [{ code: "sonderart", label: "Sonderart vom Server" }];
    const { main } = _zeichne(win, { _daten: daten });
    const sel = main.querySelector("#aiw-capp-av-art");
    expect(sel).toBeTruthy();
    const werte = Array.prototype.map.call(sel.options, (o) => o.value);
    // Genau das, was der Server geschickt hat — keine eingebaute Liste.
    expect(werte).toEqual(["sonderart"]);
  });

  // CP05 --------------------------------------------------------------------
  it("CP05: scope 'eigene' ohne Personenauswahl und ohne anlagenweite Formulare", () => {
    const win = _win();
    const { main } = _zeichne(win, { _daten: _daten("eigene") });
    expect(main.querySelector("#aiw-capp-wt-person")).toBeNull();
    expect(main.querySelector("#aiw-capp-av-person")).toBeNull();
    expect(main.querySelector("#aiw-capp-ho-save")).toBeNull();
    expect(main.querySelector("#aiw-capp-re-save")).toBeNull();
    // Die TABELLEN stehen trotzdem — ohne den Gruendekatalog waere der
    // reason_code in den eigenen Zeilen ein nackter Code.
    expect(main.querySelector("#aiw-capacity_holiday-tk")).toBeTruthy();
    expect(main.querySelector("#aiw-capacity_reason-tk")).toBeTruthy();
  });

  // CP06 --------------------------------------------------------------------
  it("CP06: der Grund fuer die fehlenden Formulare steht da", () => {
    const win = _win();
    const { main } = _zeichne(win, { _daten: _daten("eigene") });
    const text = main.textContent;
    expect(text).toContain("nur die eigene Kapazitaet");
    // Nicht nur \"geht nicht\", sondern WARUM: Wirkung auf alle Personen.
    expect(text).toContain("wirken auf alle Personen");
  });

  // CP07 --------------------------------------------------------------------
  it("CP07: der Append-only-Hinweis steht an den Arbeitszeiten", () => {
    const win = _win();
    const { main } = _zeichne(win, {});
    const text = main.textContent;
    expect(text).toContain("NEUE Zeile");
    expect(text).toContain("bleibt stehen");
  });

  // CP08 --------------------------------------------------------------------
  it("CP08: ohne Tabellenmechanik steht die Zahl je Abschnitt", () => {
    const win = _win(false);           // tablekit NICHT geladen
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    win.AIWCockpitCapacityPflege.renderCapacityPflege(main, _daten("alle"), {});
    const platz = main.querySelectorAll(".aiw-placeholder");
    expect(platz.length).toBe(4);      // vier Abschnitte, vier Meldungen
    const texte = Array.prototype.map.call(platz, (p) => p.textContent);
    // Jede Meldung nennt Zahl UND Substantiv — "1 Feiertage", nicht
    // "keine Daten".
    expect(texte.some((t) => /1 Arbeitszeit-Regeln/.test(t))).toBe(true);
    expect(texte.some((t) => /1 Feiertage/.test(t))).toBe(true);
  });

  // CP09 --------------------------------------------------------------------
  it("CP09: die Schreib-Rueckrufe liefern die Nutzlast des Endpunkts", () => {
    const win = _win();
    let wt = null, av = null;
    const { main } = _zeichne(win, {
      onWorktimeSet: (b) => { wt = b; },
      onAvailabilitySet: (b) => { av = b; },
    });

    main.querySelector("#aiw-capp-wt-ab").value = "2026-08-01";
    main.querySelector("#aiw-capp-wt-mon_min").value = "420";
    main.querySelector("#aiw-capp-wt-save").dispatchEvent(
      new win.Event("click"));
    expect(wt.effective_from).toBe("2026-08-01");
    expect(wt.mon_min).toBe(420);
    expect(wt.person_id).toBe(2);      // erster Eintrag der Auswahlliste

    main.querySelector("#aiw-capp-av-von").value = "2026-09-01";
    main.querySelector("#aiw-capp-av-bis").value = "2026-09-05";
    main.querySelector("#aiw-capp-av-min").value = "600";
    main.querySelector("#aiw-capp-av-save").dispatchEvent(
      new win.Event("click"));
    expect(av.value_minutes).toBe(600);
    // LEER heisst null, nicht 0: eine 0 waere die Angabe "null Prozent" und
    // verstiesse gegen die Regel 'genau EINES von beiden'.
    expect(av.value_pct).toBeNull();
    expect(av.kind).toBe("einschraenkung");
  });

  // CP10 --------------------------------------------------------------------
  it("CP10: Freitext wird als Text gesetzt, nicht als Auszeichnung", () => {
    const win = _win();
    const daten = _daten("alle");
    daten.availability[0].note = "<img src=x onerror=alert(1)>";
    daten.holidays[0].label = "<script>boom()</script>";
    const { main } = _zeichne(win, { _daten: daten });
    expect(main.querySelector("img")).toBeNull();
    expect(main.querySelector("script")).toBeNull();
    expect(main.textContent).toContain("onerror=alert(1)");
  });

  // CP11 --------------------------------------------------------------------
  it("CP11: der Formularzustand ueberlebt das Neuzeichnen", () => {
    const win = _win();
    const { main } = _zeichne(win, {
      formular: { worktime: { person_id: 3, effective_from: "2026-08-01",
                              mon_min: 478, tue_min: 478 } },
    });
    // Genau der Fall, an dem mc haengenblieb: nach dem Speichern war das
    // Stichtagsfeld leer, und jede weitere Eingabe scheiterte am Server.
    expect(main.querySelector("#aiw-capp-wt-ab").value).toBe("2026-08-01");
    expect(main.querySelector("#aiw-capp-wt-person").value).toBe("3");
    expect(main.querySelector("#aiw-capp-wt-mon_min").value).toBe("478");
  });

  // CP12 --------------------------------------------------------------------
  it("CP12: ohne Zustand ist der Stichtag mit heute vorbelegt", () => {
    const win = _win();
    const { main } = _zeichne(win, {});
    const wert = main.querySelector("#aiw-capp-wt-ab").value;
    expect(wert).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(wert).toBe(win.AIWCockpitCapacityPflege.heuteIso());
  });

  // CP13 --------------------------------------------------------------------
  it("CP13: markiereFeld trifft genau ein Feld und raeumt vorher auf", () => {
    const win = _win();
    const { main, view } = _zeichne(win, {});
    view.markiereFeld("effective_from");
    expect(main.querySelectorAll(".aiw-feldfehler").length).toBe(1);
    expect(main.querySelector(".aiw-feldfehler").id)
      .toBe("aiw-capp-wt-ab");

    view.markiereFeld("mon_min");
    expect(main.querySelectorAll(".aiw-feldfehler").length).toBe(1);
    expect(main.querySelector(".aiw-feldfehler").id)
      .toBe("aiw-capp-wt-mon_min");

    // Ein unbekanntes Feld markiert NICHTS — ein geratenes rotes Feld waere
    // schlimmer als gar keines.
    view.markiereFeld("gibtesnicht");
    expect(main.querySelectorAll(".aiw-feldfehler").length).toBe(0);
  });

  // CP14 --------------------------------------------------------------------
  it("CP14: die Tagesvorgaben setzen Mo-Fr und nullen das Wochenende", () => {
    const win = _win();
    const { main } = _zeichne(win, {});
    main.querySelector("#aiw-capp-wt-vorgabe-angestellte")
      .dispatchEvent(new win.Event("click"));
    expect(main.querySelector("#aiw-capp-wt-mon_min").value).toBe("478");
    expect(main.querySelector("#aiw-capp-wt-fri_min").value).toBe("478");
    expect(main.querySelector("#aiw-capp-wt-sat_min").value).toBe("0");

    main.querySelector("#aiw-capp-wt-vorgabe-beamte")
      .dispatchEvent(new win.Event("click"));
    expect(main.querySelector("#aiw-capp-wt-mon_min").value).toBe("492");
    // Der Hinweis nennt beide Zahlen auch im Text.
    expect(main.textContent).toContain("478");
    expect(main.textContent).toContain("492");
  });

  // CP15 --------------------------------------------------------------------
  it("CP15: Bearbeitungsmodus ersetzt, statt anzulegen", () => {
    const win = _win();
    let ersetzt = null, angelegt = null, abgebrochen = false;
    const { main } = _zeichne(win, {
      formular: { worktime: { person_id: 2, effective_from: "2026-01-01",
                              mon_min: 480, _ersetzt_id: 7 } },
      onWorktimeReplace: (b) => { ersetzt = b; },
      onWorktimeSet: (b) => { angelegt = b; },
      onWorktimeEditAbort: () => { abgebrochen = true; },
    });
    // Der Modus MUSS sichtbar sein: das Speichern hat hier eine andere
    // Wirkung als sonst.
    expect(main.querySelector("#aiw-capp-wt-save").textContent)
      .toBe("Zeile ersetzen");
    expect(main.textContent).toContain("ERSETZT Zeile #7");

    main.querySelector("#aiw-capp-wt-save").dispatchEvent(new win.Event("click"));
    expect(angelegt).toBeNull();
    expect(ersetzt.worktime_id).toBe(7);
    expect(ersetzt.mon_min).toBe(480);

    main.querySelector("#aiw-capp-wt-abbrechen")
      .dispatchEvent(new win.Event("click"));
    expect(abgebrochen).toBe(true);
  });

  // CP16 --------------------------------------------------------------------
  it("CP16: uebernahmeText schreibt aus, was uebernommen wurde", () => {
    const api = _win().AIWCockpitCapacityPflege;
    const t = api.uebernahmeText("Mueller", "2026-01-01",
      { mon_min: 478, tue_min: 478, wed_min: 478, thu_min: 478,
        fri_min: 478, sat_min: 0, sun_min: 0 }, 41, false);
    expect(t).toContain("Mueller");
    expect(t).toContain("2026-01-01");
    expect(t).toContain("Mo 478");
    expect(t).toContain("Woche 2390 min");
    expect(t).toContain("Beleg #41");

    const e = api.uebernahmeText("Mueller", "2026-01-01",
      { mon_min: 478 }, 42, true);
    expect(e).toMatch(/^Ersetzt/);
    expect(e).toContain("alte Zeile bleibt");
  });

  // CP17 --------------------------------------------------------------------
  it("CP17: die Aktionsspalte bietet Bearbeiten und Entfernen", () => {
    const win = _win();
    let bearbeitet = null, entfernt = null;
    const { main } = _zeichne(win, {
      onWorktimeEdit: (z) => { bearbeitet = z; },
      onWorktimeRemove: (id) => { entfernt = id; },
    });
    const knoepfe = Array.prototype.filter.call(
      main.querySelectorAll(".aiw-aktionen .aiw-btn-klein"),
      () => true);
    expect(knoepfe.length).toBe(2);
    knoepfe[0].dispatchEvent(new win.Event("click"));
    expect(bearbeitet.id).toBe(1);
    knoepfe[1].dispatchEvent(new win.Event("click"));
    expect(entfernt).toBe(1);
  });

  // CP18 --------------------------------------------------------------------
  it("CP18: ausgeblendete Zeilen werden gezaehlt, auch wenn sie fehlen", () => {
    const win = _win();
    const daten = _daten("alle");
    daten.include_deleted = false;
    daten.entfernt = { worktimes: 2, availability: 1, holidays: 0,
                       reasons: 0 };
    const { main } = _zeichne(win, { _daten: daten });

    // Im Kopf die Gesamtzahl ...
    expect(main.querySelector(".aiw-capp-schalter").textContent)
      .toMatch(/3 entfernte Zeile\(n\) sind derzeit ausgeblendet/);
    // ... und je Abschnitt die eigene. Eine Gesamtzahl allein sagt nicht, WO
    // etwas fehlt.
    const hinweise = Array.prototype.map.call(
      main.querySelectorAll(".aiw-capp-ausgeblendet"), (e) => e.textContent);
    expect(hinweise.length).toBe(2);
    expect(hinweise.some((t) => /2 entfernte Zeilen.*Arbeitszeit-Regeln/.test(t)))
      .toBe(true);
    expect(hinweise.some((t) => /1 entfernte Zeile .*Abwesenheiten/.test(t)))
      .toBe(true);
    expect(main.querySelector("#aiw-capp-entfernte").checked).toBe(false);
  });

  // CP19 --------------------------------------------------------------------
  it("CP19: ist nichts entfernt, steht auch kein Hinweis", () => {
    const win = _win();
    const daten = _daten("alle");
    daten.entfernt = { worktimes: 0, availability: 0, holidays: 0,
                       reasons: 0 };
    const { main } = _zeichne(win, { _daten: daten });
    expect(main.querySelectorAll(".aiw-capp-ausgeblendet").length).toBe(0);
    expect(main.querySelector(".aiw-capp-schalter").textContent)
      .toContain("Es ist nichts entfernt.");
    // Kein Hinweis ueber null Zeilen.
    expect(win.AIWCockpitCapacityPflege.ausgeblendetText(0, "X")).toBeNull();
  });

  // CP20 --------------------------------------------------------------------
  it("CP20: eingeblendete entfernte Zeilen sind gekennzeichnet und gesperrt", () => {
    const win = _win();
    const daten = _daten("alle");
    daten.include_deleted = true;
    daten.entfernt = { worktimes: 1, availability: 0, holidays: 0,
                       reasons: 0 };
    daten.worktimes[0].deleted_at = 1785000000;
    let entfernt = null;
    const { main } = _zeichne(win, {
      _daten: daten, onWorktimeRemove: (id) => { entfernt = id; },
    });

    expect(main.querySelector("#aiw-capp-entfernte").checked).toBe(true);
    // Die Aufbereitung markiert sie ...
    const zeilen = win.AIWCockpitCapacityPflege.worktimeRows(daten);
    expect(zeilen[0].stand).toBe("entfernt");
    expect(zeilen[0]._entfernt).toBe(true);
    // ... und die Aktionsspalte gibt keine Knoepfe her: ein zweites Entfernen
    // wiese der Server ohnehin ab.
    expect(main.querySelectorAll(".aiw-aktionen .aiw-btn-klein").length).toBe(0);
    expect(main.querySelector(".aiw-aktionen").textContent).toBe("entfernt");
    expect(entfernt).toBeNull();

    // Solange nichts eingeblendet ist, gibt es die Spalte 'Stand' nicht -
    // eine Spalte, in der ausnahmslos "aktiv" steht, ist Ballast.
    const ohne = _daten("alle");
    ohne.include_deleted = false;
    const zweit = _zeichne(_win(), { _daten: ohne });
    expect(zweit.main.textContent).not.toContain("Stand");
  });

  // CP21 --------------------------------------------------------------------
  it("CP21: Umschalten meldet den neuen Zustand", () => {
    const win = _win();
    let zustand = null;
    const { main } = _zeichne(win, {
      onEntfernteUmschalten: (an) => { zustand = an; },
    });
    const box = main.querySelector("#aiw-capp-entfernte");
    box.checked = true;
    box.dispatchEvent(new win.Event("change"));
    expect(zustand).toBe(true);
    box.checked = false;
    box.dispatchEvent(new win.Event("change"));
    expect(zustand).toBe(false);
  });
});
