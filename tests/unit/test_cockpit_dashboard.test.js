/**
 * tests/unit/test_cockpit_dashboard.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3G (Build 547)
 *
 * Testsuite fuer management/server/static/cockpit_dashboard.js — die
 * Kachelflaeche des Ueberblicks. Getestet wird der ECHTE Code (readFileSync +
 * JSDOM), kein Logik-Abbild.
 *
 * DIE TESTDATEN SPIEGELN DIE GEMESSENEN ANTWORTFORMEN der acht Endpunkte
 * (aufgerufen gegen eine Wegwerf-coordinator.db am 2026-07-26, nicht aus dem
 * Quelltext geraten). Wo ein Feldname hier steht, steht er auch dort:
 * z.B. 'priority' (nicht 'prioritaet'), 'loads[].is_backlog',
 * 'overload.overloaded_count', 'items[].severity', 'matters[].kind_label'.
 *
 *   DB01 — hinweisReduktion(): nennt das Abschneiden, schweigt sonst.
 *   DB02 — aktiveKacheln(): null = Werkseinstellung, [] = ausdruecklich
 *          nichts. Wer beides gleich behandelt, gibt jemandem die
 *          Werkseinstellung zurueck, der sie abgewaehlt hat.
 *   DB03 — aktiveKacheln(): DER RECHTEFILTER LAEUFT ZULETZT.
 *   DB04 — reduceFallampel(): zaehlt je Ampel, BENENNT unbekannte Werte und
 *          behauptet KEINE Reduktion (die Kachel bettet die volle Tabelle
 *          ein — 'gesamt' bleibt null).
 *   DB05 — reduceEskalationen(): nach Schwere sortiert, schneidet ab und
 *          sagt es.
 *   DB06 — reduceNextActions(): Kopfzahl aus 'actionable'.
 *   DB07 — reduceWiedervorlage(): FILTERT auf faellig/ueberfaellig und
 *          benennt die Grundlage.
 *   DB08 — reduceFristen(): unbestaetigter Parametersatz -> KEINE Zahl,
 *          sondern der Grund. Eine Zahl waere eine unbelegte
 *          Rechtsbehauptung.
 *   DB09 — reduceFristen(): bestaetigt -> Zahl, aber der Vorbehalt faehrt
 *          MIT.
 *   DB10 — reduceLastverteilung(): die Rueckstauzeile ist keine Person.
 *   DB11 — reduceMeineAuftraege(): nach Ampel, dann Prioritaet.
 *   DB12 — reduceKettenzustand(): unversehrt vs. Bruch.
 *   DB13 — FEHLER IST NICHT LEER: fuer JEDEN Reduzierer.
 *   DB14 — DIE ZUSICHERUNG, ueber alle Reduzierer: wer abschneidet, liefert
 *          einen Hinweis; wer filtert, eine Grundlage.
 *   DB15 — reduziere(): unbekannte Kachel -> ausdruecklicher Fehler, kein
 *          stilles Nichts.
 *   DB16 — renderDashboard(): Kacheln, Steckplatz-Rueckruf, und eine
 *          ausgefallene Kachel sieht anders aus als eine leere.
 *   DB17 — renderDashboard(): Reduktionshinweise und Vorbehalt erscheinen.
 *   DB18 — Kachelwaehler: onSpeichern bekommt Auswahl UND Reihenfolge.
 *
 * Version: v0.8.547 · Build: 547 · 2026-07-26
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_dashboard.js",
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
function _api(win) {
  return (win || _ctx()).AIWCockpitDashboard;
}

const KATALOG = {
  standard_widgets: ["fallampel"],
  widgets: [
    { key: "fallampel", label: "Fall-Übersicht", cap: "dashboard.view", erlaubt: true },
    { key: "eskalationen", label: "Eskalationen", cap: "escalation.view", erlaubt: true },
    { key: "fristen", label: "Fristen", cap: "limitation.view", erlaubt: false },
  ],
};

describe("cockpit_dashboard.js — Auswahl und Hinweise (Build 547)", () => {
  // DB01 ---------------------------------------------------------------------
  it("DB01: hinweisReduktion nennt das Abschneiden und schweigt sonst", () => {
    const D = _api();
    expect(D.hinweisReduktion(5, 23)).toBe("5 von 23 angezeigt");
    expect(D.hinweisReduktion(5, 5)).toBe("");
    expect(D.hinweisReduktion(5, 3)).toBe("");
    expect(D.hinweisReduktion(0, null)).toBe("");
    expect(D.hinweisReduktion(0, undefined)).toBe("");
  });

  // DB02 ---------------------------------------------------------------------
  it("DB02: null = Werkseinstellung, [] = ausdruecklich nichts", () => {
    const D = _api();
    expect(D.aktiveKacheln(null, KATALOG).map((w) => w.key)).toEqual([
      "fallampel",
    ]);
    expect(D.aktiveKacheln(undefined, KATALOG).map((w) => w.key)).toEqual([
      "fallampel",
    ]);
    // Wer alles abwaehlt, bekommt NICHT die Werkseinstellung zurueck.
    expect(D.aktiveKacheln([], KATALOG)).toEqual([]);
    // Ebenso wenig, wenn alles auf unsichtbar steht.
    expect(
      D.aktiveKacheln([{ key: "fallampel", sichtbar: false }], KATALOG)
    ).toEqual([]);
  });

  // DB03 ---------------------------------------------------------------------
  it("DB03: der Rechtefilter laeuft ZULETZT", () => {
    const D = _api();
    // 'fristen' ist gespeichert und sichtbar, aber NICHT erlaubt.
    const out = D.aktiveKacheln(
      [
        { key: "fristen", sichtbar: true },
        { key: "eskalationen", sichtbar: true },
      ],
      KATALOG
    ).map((w) => w.key);
    expect(out).toEqual(["eskalationen"]);
    // Und die gespeicherte Reihenfolge wird respektiert.
    const out2 = D.aktiveKacheln(
      [
        { key: "eskalationen", sichtbar: true },
        { key: "fallampel", sichtbar: true },
      ],
      KATALOG
    ).map((w) => w.key);
    expect(out2).toEqual(["eskalationen", "fallampel"]);
  });
});

describe("cockpit_dashboard.js — Reduzierer (Build 547)", () => {
  // DB04 ---------------------------------------------------------------------
  it("DB04: Fall-Uebersicht zaehlt, benennt Unbekanntes, behauptet keine Reduktion", () => {
    const D = _api();
    const m = D.reduceFallampel({
      scope: "alle",
      count: 4,
      cases: [
        { ampel: "rot" }, { ampel: "gelb" }, { ampel: "gruen" },
        { ampel: "violett" },
      ],
    });
    expect(m.kopf).toBe("4");
    expect(m.unterzeile).toContain("1 rot");
    // Ein unbekannter Ampelwert wird NICHT still unter 'gruen' verbucht.
    expect(m.unterzeile).toContain("1 ohne Einstufung");
    // Die Kachel bettet die volle Tabelle ein -> KEIN Reduktionshinweis.
    expect(m.hinweis).toBe("");
    expect(m.gesamt).toBe(null);
    expect(D.reduceFallampel({ count: 0, cases: [] }).leer).toBe(true);
  });

  // DB05 ---------------------------------------------------------------------
  it("DB05: Eskalationen nach Schwere, abgeschnitten UND benannt", () => {
    const D = _api();
    const items = [];
    for (let i = 0; i < 7; i++) {
      items.push({
        rule_code: "fall_unbearbeitet",
        label: "Fall unbearbeitet",
        severity: i === 6 ? "hoch" : "niedrig",
        subject_id: 100 + i,
        message: "x",
        days_inactive: i,
      });
    }
    const m = D.reduceEskalationen(
      { items, count_hoch: 1, count_mittel: 0, count_niedrig: 6 },
      5
    );
    expect(m.kopf).toBe("7");
    expect(m.unterzeile).toBe("1 hoch · 0 mittel · 6 niedrig");
    // Das 'hoch'-Element steht vorn, obwohl es zuletzt kam.
    expect(m.zeilen[0].stufe).toBe("hoch");
    expect(m.zeilen.length).toBe(5);
    expect(m.hinweis).toBe("5 von 7 angezeigt");
    expect(m.zeilen[0].text).toContain("Fall 106");
  });

  // DB06 ---------------------------------------------------------------------
  it("DB06: Naechstbeste Aktion — Kopfzahl aus 'actionable'", () => {
    const D = _api();
    const m = D.reduceNextActions({
      actionable: 3,
      total_cases: 12,
      items: [
        { subject_id: 1, username: "alpha", action: "zuweisen", ampel: "rot" },
        { subject_id: 2, username: "beta", action: "prüfen", ampel: "gelb" },
      ],
    });
    expect(m.kopf).toBe("3");
    expect(m.unterzeile).toBe("von 12 Fällen");
    expect(m.zeilen[0].text).toBe("alpha: zuweisen");
    expect(m.hinweis).toBe("");
  });

  // DB07 ---------------------------------------------------------------------
  it("DB07: Wiedervorlagen werden GEFILTERT — und das steht in der Kachel", () => {
    const D = _api();
    const m = D.reduceWiedervorlage({
      count: 4,
      counts: { rot: 1, gelb: 1, gruen: 2, neutral: 0 },
      matters: [
        { id: 1, kind_label: "Anfrage", betreff: "A", ampel: "rot" },
        { id: 2, kind_label: "Anfrage", betreff: "B", ampel: "gelb" },
        { id: 3, kind_label: "Anfrage", betreff: "C", ampel: "gruen" },
        { id: 4, kind_label: "Anfrage", betreff: "D", ampel: "gruen" },
      ],
    });
    expect(m.kopf).toBe("2");
    // OHNE diesen Satz waere die '2' eine Aussage ueber ALLE Vorgaenge.
    expect(m.grundlage).toBe(
      "nur fällige und überfällige Vorgänge (von 4)"
    );
    expect(m.zeilen.length).toBe(2);
    expect(m.zeilen[0].text).toBe("Anfrage: A");
  });

  // DB08 ---------------------------------------------------------------------
  it("DB08: Fristen ohne bestaetigte Parameter zeigen KEINE Zahl", () => {
    const D = _api();
    const m = D.reduceFristen({
      params_bestaetigt: false,
      aussage_moeglich: false,
      verweigerungsgrund: "Der Parametersatz ist nicht bestätigt.",
      vorbehalte: ["Unterbrechungen nach § 78c sind nicht berücksichtigt."],
      rows: [{ subject_id: 1, restlaufzeit_tage: 5, aussage_moeglich: true }],
      vorwarn_tage: 180,
    });
    // Eine Zahl waere hier eine unbelegte Rechtsbehauptung.
    expect(m.kopf).toBe("\u2014");
    expect(m.unterzeile).toContain("nicht bestätigt");
    expect(m.grundlage).toContain("nicht bestätigt");
    expect(m.vorbehalt).toContain("§ 78c");
    expect(m.zeilen).toEqual([]);
  });

  // DB09 ---------------------------------------------------------------------
  it("DB09: Fristen mit Zahl — der Vorbehalt faehrt trotzdem mit", () => {
    const D = _api();
    const m = D.reduceFristen({
      params_bestaetigt: true,
      aussage_moeglich: true,
      vorwarn_tage: 100,
      faelle_gesamt: 9,
      vorbehalte: ["Unterbrechungen nicht berücksichtigt."],
      rows: [
        { subject_id: 1, username: "a", restlaufzeit_tage: 20,
          aussage_moeglich: true, ampel: "rot" },
        { subject_id: 2, username: "b", restlaufzeit_tage: 5,
          aussage_moeglich: true, ampel: "rot" },
        // Ausserhalb der Vorwarnung -> nicht gezaehlt.
        { subject_id: 3, username: "c", restlaufzeit_tage: 900,
          aussage_moeglich: true, ampel: "gruen" },
        // Ohne Aussage -> nicht gezaehlt.
        { subject_id: 4, username: "d", restlaufzeit_tage: 1,
          aussage_moeglich: false },
      ],
    });
    expect(m.kopf).toBe("2");
    // Aufsteigend: die knappste Frist zuerst.
    expect(m.zeilen[0].text).toBe("b: 5 Tage");
    expect(m.grundlage).toContain("von 9");
    expect(m.vorbehalt).toContain("Unterbrechungen");
  });

  // DB10 ---------------------------------------------------------------------
  it("DB10: Lastverteilung — die Rueckstauzeile ist keine Person", () => {
    const D = _api();
    const m = D.reduceLastverteilung({
      count: 3,
      loads: [
        { display_name: "A", active_cases: 4, is_backlog: false },
        { display_name: "B", active_cases: 9, is_backlog: false },
        { display_name: "(unzugewiesen)", active_cases: 40, is_backlog: true },
      ],
      overload: { overloaded_count: 1, warned_count: 2, backlog_size: 40 },
    });
    expect(m.kopf).toBe("1");
    expect(m.unterzeile).toContain("Rückstau 40");
    expect(m.zeilen.map((z) => z.text)).toEqual(["B: 9 aktiv", "A: 4 aktiv"]);
    expect(m.gesamt).toBe(2);
  });

  // DB11 ---------------------------------------------------------------------
  it("DB11: Meine Auftraege — nach Ampel, dann Prioritaet", () => {
    const D = _api();
    const m = D.reduceMeineAuftraege({
      count: 3,
      cases: [
        { subject_id: 1, username: "gruen1", ampel: "gruen", priority: 1 },
        { subject_id: 2, username: "rot2", ampel: "rot", priority: 2 },
        { subject_id: 3, username: "rot1", ampel: "rot", priority: 1 },
      ],
    });
    expect(m.kopf).toBe("3");
    expect(m.zeilen.map((z) => z.text)).toEqual(["rot1", "rot2", "gruen1"]);
  });

  // DB12 ---------------------------------------------------------------------
  it("DB12: Kettenzustand — unversehrt vs. Bruch", () => {
    const D = _api();
    const ok = D.reduceKettenzustand({ ok: true, tip_seq: 412,
      first_bad_seq: null, detail: "" });
    expect(ok.kopf).toBe("unversehrt");
    expect(ok.unterzeile).toContain("412");

    const bruch = D.reduceKettenzustand({ ok: false, first_bad_seq: 77,
      detail: "Hashkette gebrochen", tip_seq: 412 });
    expect(bruch.kopf).toBe("BRUCH");
    expect(bruch.unterzeile).toContain("77");
    expect(bruch.zeilen[0].text).toBe("Hashkette gebrochen");
  });

  // DB13 ---------------------------------------------------------------------
  it("DB13: FEHLER IST NICHT LEER — fuer jeden Reduzierer", () => {
    const D = _api();
    Object.keys(D.REDUZIERER).forEach((key) => {
      const m = D.REDUZIERER[key]({ fehler: "Zeitüberschreitung" });
      expect(m.fehler, key).toBe("Zeitüberschreitung");
      // Entscheidend: 'leer' bleibt FALSCH. Ein Ausfall darf nie wie ein
      // Leerbefund aussehen (Grundregel 1).
      expect(m.leer, key).toBe(false);
      expect(m.zeilen, key).toEqual([]);
    });
  });

  // DB14 ---------------------------------------------------------------------
  it("DB14: wer abschneidet, sagt es; wer filtert, nennt die Grundlage", () => {
    const D = _api();
    // Je Reduzierer ein Datensatz, der GARANTIERT abschneidet (>5 Zeilen)
    // oder filtert. 'fallampel' und 'kettenzustand' tun beides nicht.
    const viele = (n, f) => Array.from({ length: n }, (_, i) => f(i));
    const proben = {
      eskalationen: {
        daten: {
          items: viele(9, (i) => ({ label: "L", severity: "hoch",
            subject_id: i, days_inactive: i })),
          count_hoch: 9, count_mittel: 0, count_niedrig: 0,
        },
        filtert: false,
      },
      naechste_aktion: {
        daten: {
          actionable: 9, total_cases: 9,
          items: viele(9, (i) => ({ subject_id: i, username: "u" + i,
            action: "tun", ampel: "rot" })),
        },
        filtert: false,
      },
      wiedervorlage: {
        daten: {
          counts: { rot: 9, gelb: 0, gruen: 1, neutral: 0 },
          matters: viele(9, (i) => ({ id: i, kind_label: "K",
            betreff: "B" + i, ampel: "rot" }))
            .concat([{ id: 99, kind_label: "K", betreff: "grün",
              ampel: "gruen" }]),
        },
        filtert: true,
      },
      fristen: {
        daten: {
          params_bestaetigt: true, aussage_moeglich: true, vorwarn_tage: 500,
          faelle_gesamt: 20, vorbehalte: ["V"],
          rows: viele(9, (i) => ({ subject_id: i, username: "u" + i,
            restlaufzeit_tage: i, aussage_moeglich: true, ampel: "rot" })),
        },
        filtert: true,
      },
      lastverteilung: {
        daten: {
          count: 9,
          loads: viele(9, (i) => ({ display_name: "P" + i,
            active_cases: i, is_backlog: false })),
          overload: { overloaded_count: 0, warned_count: 0, backlog_size: 0 },
        },
        filtert: true,
      },
      meine_auftraege: {
        daten: {
          count: 9,
          cases: viele(9, (i) => ({ subject_id: i, username: "u" + i,
            ampel: "rot", priority: 1 })),
        },
        filtert: true,
      },
    };

    Object.keys(proben).forEach((key) => {
      const m = D.reduziere(key, proben[key].daten, 5);
      expect(m.zeilen.length, key).toBe(5);
      // ABGESCHNITTEN -> es steht dort.
      expect(m.hinweis, key).toBe("5 von 9 angezeigt");
      if (proben[key].filtert) {
        // GEFILTERT/SORTIERT -> die Grundlage steht dort.
        expect(m.grundlage.length, key).toBeGreaterThan(0);
      }
    });

    // Die beiden Kacheln, die weder filtern noch abschneiden, behaupten auch
    // nichts dergleichen.
    expect(
      D.reduceFallampel({ count: 99, cases: [{ ampel: "rot" }] }).hinweis
    ).toBe("");
    expect(D.reduceKettenzustand({ ok: true, tip_seq: 1 }).hinweis).toBe("");
  });

  // DB15 ---------------------------------------------------------------------
  it("DB15: unbekannte Kachel -> ausdruecklicher Fehler, kein stilles Nichts", () => {
    const D = _api();
    const m = D.reduziere("gibtsnicht", {});
    expect(m.fehler).toContain("gibtsnicht");
    expect(m.leer).toBe(false);
  });
});

describe("cockpit_dashboard.js — Render (Build 547)", () => {
  const KAT = {
    standard_widgets: ["fallampel"],
    widgets: [
      { key: "fallampel", label: "Fall-Übersicht", beschreibung: "Alle Fälle",
        erlaubt: true },
      { key: "eskalationen", label: "Eskalationen", beschreibung: "Schwellen",
        erlaubt: true },
      { key: "fristen", label: "Fristen", beschreibung: "Verjährung",
        erlaubt: false },
    ],
  };

  function _mount(win) {
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    return main;
  }

  // DB16 ---------------------------------------------------------------------
  it("DB16: Steckplatz-Rueckruf; ausgefallen sieht anders aus als leer", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);
    let slotKey = null;
    let slotEl = null;

    D.renderDashboard(
      main,
      {
        kacheln: [
          { key: "fallampel", label: "Fall-Übersicht", slot: true },
          { key: "eskalationen", label: "Eskalationen" },
          { key: "fristen", label: "Fristen" },
        ],
        modelle: {
          fallampel: D.reduceFallampel({ count: 2, cases: [{ ampel: "rot" },
            { ampel: "gelb" }] }),
          eskalationen: D.reduceEskalationen({ items: [], count_hoch: 0,
            count_mittel: 0, count_niedrig: 0 }),
          fristen: D.fehlerModell("Zeitüberschreitung"),
        },
        katalog: KAT,
      },
      { onSlot: (k, e) => { slotKey = k; slotEl = e; } }
    );

    expect(main.querySelectorAll(".aiw-kachel").length).toBe(3);
    // Der Steckplatz wird gemeldet — hier haengt der Fall-Sprung dran.
    expect(slotKey).toBe("fallampel");
    expect(slotEl).not.toBe(null);
    expect(
      main.querySelector('[data-widget-key="fallampel"]').className
    ).toContain("is-breit");

    // LEER: sagt ausdruecklich, dass nichts anliegt.
    const leer = main.querySelector('[data-widget-key="eskalationen"]');
    expect(leer.textContent).toContain("Es liegt nichts an");
    expect(leer.className).not.toContain("is-fehler");

    // AUSGEFALLEN: anderer Text, andere Klasse. Nie verwechselbar.
    const fehler = main.querySelector('[data-widget-key="fristen"]');
    expect(fehler.className).toContain("is-fehler");
    expect(fehler.textContent).toContain("Nicht abrufbar");
    expect(fehler.textContent).not.toContain("Es liegt nichts an");
  });

  // DB17 ---------------------------------------------------------------------
  it("DB17: Reduktionshinweise und Vorbehalt erscheinen in der Kachel", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);
    const m = D.reduceFristen({
      params_bestaetigt: true, aussage_moeglich: true, vorwarn_tage: 500,
      faelle_gesamt: 20, vorbehalte: ["Unterbrechungen nicht berücksichtigt."],
      rows: Array.from({ length: 9 }, (_, i) => ({ subject_id: i,
        username: "u" + i, restlaufzeit_tage: i, aussage_moeglich: true,
        ampel: "rot" })),
    });
    D.renderDashboard(
      main,
      { kacheln: [{ key: "fristen", label: "Fristen" }],
        modelle: { fristen: m }, katalog: KAT },
      {}
    );
    const k = main.querySelector('[data-widget-key="fristen"]');
    expect(k.querySelector(".aiw-kachel-hinweis").textContent).toBe(
      "5 von 9 angezeigt"
    );
    expect(k.querySelector(".aiw-kachel-grundlage").textContent).toContain(
      "von 20"
    );
    expect(k.querySelector(".aiw-kachel-vorbehalt").textContent).toContain(
      "Unterbrechungen"
    );
  });

  // DB18 ---------------------------------------------------------------------
  it("DB18: der Kachelwaehler meldet Auswahl UND Reihenfolge", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);
    let gesehen = null;
    D.renderDashboard(
      main,
      {
        kacheln: [{ key: "fallampel", label: "Fall-Übersicht", slot: true }],
        modelle: { fallampel: D.reduceFallampel({ count: 0, cases: [] }) },
        katalog: KAT,
      },
      { onSlot: () => {}, onSpeichern: (n) => { gesehen = n; } }
    );

    // Waehler oeffnen.
    main.querySelector(".aiw-btn").dispatchEvent(new win.Event("click"));
    const zeilen = main.querySelectorAll(".aiw-db-wzeile");
    // Nur ERLAUBTE Kacheln stehen zur Wahl — 'fristen' fehlt.
    expect(zeilen.length).toBe(2);
    expect(main.querySelector(".aiw-db-waehler").textContent).not.toContain(
      "Verjährung"
    );

    // 'eskalationen' zuschalten und nach oben ziehen.
    zeilen[1].querySelector("input").checked = true;
    zeilen[1].querySelector("input").dispatchEvent(new win.Event("change"));
    zeilen[1]
      .querySelectorAll(".aiw-vp-pfeil")[0]
      .dispatchEvent(new win.Event("click"));

    main
      .querySelector(".aiw-btn-primary")
      .dispatchEvent(new win.Event("click"));
    expect(gesehen).toEqual([
      { key: "eskalationen", sichtbar: true },
      { key: "fallampel", sichtbar: true },
    ]);
  });
});
