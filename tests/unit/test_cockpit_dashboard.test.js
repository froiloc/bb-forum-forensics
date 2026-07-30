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
 *   DB18 — Build 570: der Diagramm-Steckplatz entsteht GENAU fuer die Kacheln
 *          mit Option; der Rueckruf bekommt Schluessel, Element und Option.
 *   DB19 — Build 570: die Reihenfolge im Kachelrumpf ist Zahl -> Diagramm ->
 *          Liste. Der Blick soll von der Groessenordnung zum Detail gehen.
 *   DB20 — Build 570: eine ausgefallene Kachel bekommt KEIN Diagramm, auch
 *          wenn eine Option mitgeliefert wuerde.
 *   DB21 — Build 570: 'tonung' faerbt die ganze Kachel (fuer die
 *          diagrammlose Ja/Nein-Aussage der Audit-Kette).
 *   DB24 — Build 573: DIE WICHTIGSTE. Beim Aufruf von onDiagramm MUSS das
 *          Zielelement im Dokument haengen (isConnected). Vorher wurde es
 *          gerufen, WAEHREND die Kachel noch nicht eingehaengt war -
 *          echarts.init() misst dann 0x0 und zeichnet eine leere Leinwand.
 *          Von aussen sah das aus wie "keine Diagramme".
 *   DB25 — Build 573: die drei Pflichthinweise stehen in EINER Fusszeile, der
 *          volle Wortlaut im title. Nichts verschwindet.
 *   DB26 — Build 573: kurzHinweis verdichtet '3 von 9 angezeigt' zu '3/9' und
 *          laesst Unbekanntes unveraendert durch.
 *   DB22 — Build 572: AUCH DIE STECKPLATZ-KACHEL bekommt ihr Diagramm, und
 *          zwar VOR der eingebetteten Tabelle. Der Steckplatz-Zweig stieg
 *          vorher vor dem Diagrammblock aus der Funktion aus; DB18 fiel das
 *          nicht auf, weil es mit Kacheln OHNE Steckplatz prueft.
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
    // BUILD 573: die drei Pflichtangaben stehen nicht mehr als drei Absaetze
    // untereinander, sondern verdichtet in EINER Fusszeile — der Wortlaut
    // liegt im title. Die ZUSICHERUNG dieser Pruefung ist unveraendert: keine
    // der drei Angaben darf verschwinden. Nur ihre Form hat sich geaendert
    // (Befund mc: als drei Absaetze wurde die Kachel ein Beipackzettel).
    const fuss = k.querySelector(".aiw-kachel-fuss");
    expect(fuss).not.toBe(null);
    // Reduktionshinweis: sichtbar als Kurzform (3 von 9 nach MAX_ZEILEN=3).
    expect(fuss.textContent).toContain("3/9");
    // Grundlage und Vorbehalt: als Marke sichtbar ...
    expect(fuss.textContent).toContain("Auswahl");
    expect(fuss.textContent).toContain("Vorbehalt");
    // ... und im Wortlaut erhalten.
    const voll = fuss.getAttribute("title");
    expect(voll).toContain("3 von 9 angezeigt");
    expect(voll).toContain("von 20");
    expect(voll).toContain("Unterbrechungen");
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

  // DB18 ---------------------------------------------------------------------
  it("DB18: Diagramm-Steckplatz nur fuer Kacheln mit Option", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);
    const gerufen = [];
    const opt = { animation: false, series: [] };

    D.renderDashboard(
      main,
      {
        kacheln: [
          { key: "eskalationen", label: "Eskalationen" },
          { key: "kettenzustand", label: "Audit-Kette" },
        ],
        modelle: {
          eskalationen: D.reduceEskalationen({ items: [{ severity: "hoch",
            days_inactive: 5, label: "X" }] }),
          kettenzustand: D.reduceKettenzustand({ ok: true, tip_seq: 7 }),
        },
        // NUR die Eskalationskachel hat eine Option.
        diagramme: { eskalationen: opt },
        katalog: KAT,
      },
      { onDiagramm: (k, el, o) => { gerufen.push([k, el, o]); } }
    );

    expect(gerufen.length).toBe(1);
    expect(gerufen[0][0]).toBe("eskalationen");
    expect(gerufen[0][2]).toBe(opt);
    expect(main.querySelectorAll(".aiw-kachel-chart").length).toBe(1);
    expect(main.querySelector('[data-chart-key="eskalationen"]')).toBeTruthy();
    // Die diagrammlose Kachel bekommt keinen leeren Behaelter — ein leerer
    // Kasten saehe wie ein nicht geladenes Diagramm aus.
    expect(main.querySelector('[data-widget-key="kettenzustand"] '
      + '.aiw-kachel-chart')).toBeNull();
  });

  // DB19 ---------------------------------------------------------------------
  it("DB19: Reihenfolge im Rumpf ist Zahl, Diagramm, Liste", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);

    D.renderDashboard(
      main,
      {
        kacheln: [{ key: "eskalationen", label: "Eskalationen" }],
        modelle: {
          eskalationen: D.reduceEskalationen({
            items: [{ severity: "hoch", days_inactive: 9, label: "A" }],
            count_hoch: 1, count_mittel: 0, count_niedrig: 0,
          }),
        },
        diagramme: { eskalationen: { animation: false, series: [] } },
        katalog: KAT,
      },
      { onDiagramm: () => {} }
    );

    const kachel = main.querySelector('[data-widget-key="eskalationen"]');
    const klassen = [...kachel.children].map((c) => c.className);
    const iZahl = klassen.indexOf("aiw-kachel-zahl");
    const iChart = klassen.indexOf("aiw-kachel-chart");
    const iListe = klassen.indexOf("aiw-kachel-liste");
    expect(iZahl).toBeGreaterThanOrEqual(0);
    expect(iChart).toBeGreaterThan(iZahl);
    expect(iListe).toBeGreaterThan(iChart);
  });

  // DB20 ---------------------------------------------------------------------
  it("DB20: eine ausgefallene Kachel bekommt kein Diagramm", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);
    let gerufen = 0;

    D.renderDashboard(
      main,
      {
        kacheln: [{ key: "eskalationen", label: "Eskalationen" }],
        modelle: { eskalationen: D.fehlerModell("HTTP 404") },
        diagramme: { eskalationen: { animation: false, series: [] } },
        katalog: KAT,
      },
      { onDiagramm: () => { gerufen += 1; } }
    );

    // Ein Diagramm auf ausgefallenen Daten waere eine Form ohne Grundlage.
    expect(gerufen).toBe(0);
    expect(main.querySelectorAll(".aiw-kachel-chart").length).toBe(0);
    expect(main.querySelector(".aiw-kachel-fehler").textContent)
      .toContain("HTTP 404");
  });

  // DB21 ---------------------------------------------------------------------
  it("DB21: tonung faerbt die ganze Kachel", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);

    D.renderDashboard(main, {
      kacheln: [{ key: "kettenzustand", label: "Audit-Kette" }],
      modelle: { kettenzustand: D.reduceKettenzustand({ ok: true,
                                                        tip_seq: 7 }) },
      katalog: KAT,
    }, {});
    expect(main.querySelector('[data-widget-key="kettenzustand"]').className)
      .toContain("ton-gruen");

    const main2 = _mount(win);
    D.renderDashboard(main2, {
      kacheln: [{ key: "kettenzustand", label: "Audit-Kette" }],
      modelle: { kettenzustand: D.reduceKettenzustand({ ok: false,
                                                        first_bad_seq: 12 }) },
      katalog: KAT,
    }, {});
    const kachel2 = main2.querySelector('[data-widget-key="kettenzustand"]');
    expect(kachel2.className).toContain("ton-rot");
    expect(kachel2.querySelector(".aiw-kachel-zahl").textContent).toBe("BRUCH");
  });

  // DB22 ---------------------------------------------------------------------
  it("DB22: auch die Steckplatz-Kachel bekommt ihr Diagramm", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);
    const gerufen = [];
    let slotEl = null;
    const opt = { animation: false, series: [] };

    D.renderDashboard(
      main,
      {
        kacheln: [{ key: "fallampel", label: "Fall-Übersicht", slot: true }],
        modelle: {
          fallampel: D.reduceFallampel({ count: 2,
            cases: [{ ampel: "rot" }, { ampel: "gelb" }] }),
        },
        diagramme: { fallampel: opt },
        katalog: KAT,
      },
      {
        onDiagramm: (k, el, o) => { gerufen.push([k, o]); },
        onSlot: (k, el) => { slotEl = el; },
      }
    );

    // Der Ring MUSS kommen — vorher blieb die Kachel die nackte Tabelle.
    expect(gerufen.length).toBe(1);
    expect(gerufen[0][0]).toBe("fallampel");
    expect(gerufen[0][1]).toBe(opt);
    expect(slotEl).not.toBe(null);

    // Und die Reihenfolge: erst der Eindruck, dann das Detail.
    const kachel = main.querySelector('[data-widget-key="fallampel"]');
    const klassen = [...kachel.children].map((c) => c.className);
    expect(klassen.indexOf("aiw-kachel-chart"))
      .toBeLessThan(klassen.indexOf("aiw-kachel-slot"));

    // Ohne Option bleibt es beim alten Verhalten (kein leerer Behaelter).
    const main2 = _mount(win);
    let gerufen2 = 0;
    D.renderDashboard(main2, {
      kacheln: [{ key: "fallampel", label: "Fall-Übersicht", slot: true }],
      modelle: { fallampel: D.reduceFallampel({ count: 0, cases: [] }) },
      katalog: KAT,
    }, { onDiagramm: () => { gerufen2 += 1; }, onSlot: () => {} });
    expect(gerufen2).toBe(0);
    expect(main2.querySelectorAll(".aiw-kachel-chart").length).toBe(0);
  });

  // DB23 ---------------------------------------------------------------------
  it("DB23: das Raster begrenzt die Spaltenzahl und streckt nicht", () => {
    const css = readFileSync("management/server/static/cockpit.css", "utf-8");
    // Der gemessene Fehler: 8 Spalten a 272px auf 2261px, alle Kacheln auf
    // 923px gestreckt. Beide Ursachen muessen im Stylesheet behoben sein.
    const bloecke = [...css.matchAll(/\.aiw-db-raster\s*\{[^}]*\}/g)]
      .map((m) => m[0]);
    const zusammen = bloecke.join("\n");
    expect(bloecke.length).toBeGreaterThan(0);
    expect(zusammen).toMatch(/align-items:\s*start/);
    const min = [...zusammen.matchAll(/minmax\((\d+)px/g)]
      .map((m) => parseInt(m[1], 10));
    expect(min.length).toBeGreaterThan(0);
    // Das WIRKSAME (letzte) Minimum muss deutlich ueber 260px liegen, sonst
    // maximiert 'auto-fill' auf breiten Schirmen wieder die Spaltenzahl.
    expect(min[min.length - 1]).toBeGreaterThanOrEqual(400);
    // Und die eingebettete Tabelle bekommt einen Deckel.
    expect(css).toMatch(/\.aiw-kachel-slot\s*\{[^}]*max-height/);
  });

  // DB24 ---------------------------------------------------------------------
  it("DB24: beim Diagramm-Aufruf haengt das Ziel im Dokument", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);
    const zustand = [];

    D.renderDashboard(
      main,
      {
        kacheln: [
          { key: "fallampel", label: "Fall-Übersicht", slot: true },
          { key: "eskalationen", label: "Eskalationen" },
          { key: "meine_auftraege", label: "Meine Aufträge" },
        ],
        modelle: {
          fallampel: D.reduceFallampel({ count: 1, cases: [{ ampel: "rot" }] }),
          eskalationen: D.reduceEskalationen({
            items: [{ severity: "hoch", days_inactive: 4, label: "A" }] }),
          meine_auftraege: D.reduceMeineAuftraege({ count: 1,
            cases: [{ ampel: "gelb", username: "x" }] }),
        },
        diagramme: {
          fallampel: { animation: false, series: [] },
          eskalationen: { animation: false, series: [] },
          meine_auftraege: { animation: false, series: [] },
        },
        katalog: KAT,
      },
      {
        onSlot: () => {},
        onDiagramm: (k, el) => {
          zustand.push({ key: k, verbunden: el.isConnected });
        },
      }
    );

    expect(zustand.length).toBe(3);
    // OHNE diese Zusicherung misst echarts.init() 0x0 und zeichnet ins Nichts.
    zustand.forEach((z) => {
      expect(z.verbunden).toBe(true);
    });
  });

  // DB25 ---------------------------------------------------------------------
  it("DB25: Pflichthinweise in einer Fusszeile, voller Wortlaut im title", () => {
    const win = _ctx();
    const D = _api(win);
    const main = _mount(win);

    D.renderDashboard(main, {
      kacheln: [{ key: "fristen", label: "Fristen" }],
      modelle: {
        fristen: D.reduceFristen({
          params_bestaetigt: true, aussage_moeglich: true,
          vorwarn_tage: 90, faelle_gesamt: 84,
          vorbehalte: ["Ruhenszeiten sind nicht berücksichtigt."],
          rows: [1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => ({
            aussage_moeglich: true, restlaufzeit_tage: n,
            username: "nutzer_" + n, ampel: "rot",
          })),
        }),
      },
      katalog: KAT,
    }, {});

    const kachel = main.querySelector('[data-widget-key="fristen"]');
    // Genau EINE Fusszeile — nicht drei Absaetze (der Beipackzettel-Befund).
    const fuesse = kachel.querySelectorAll(".aiw-kachel-fuss");
    expect(fuesse.length).toBe(1);
    expect(kachel.querySelectorAll(".aiw-kachel-grundlage").length).toBe(0);
    expect(kachel.querySelectorAll(".aiw-kachel-vorbehalt").length).toBe(0);

    const fuss = fuesse[0];
    // Kurzform sichtbar ...
    expect(fuss.textContent).toContain("3/9");
    expect(fuss.textContent).toContain("Vorbehalt");
    expect(fuss.className).toContain("hat-vorbehalt");
    // ... voller Wortlaut erhalten. NICHTS verschwindet.
    expect(fuss.getAttribute("title")).toContain("Ruhenszeiten");
    expect(fuss.getAttribute("title")).toContain("belegtem Anker");

    // Und die Liste ist auf drei Zeilen begrenzt.
    expect(kachel.querySelectorAll(".aiw-kachel-zeile").length).toBe(3);
  });

  // DB26 ---------------------------------------------------------------------
  it("DB26: kurzHinweis verdichtet und raet nicht", () => {
    const D = _api(_ctx());
    expect(D.kurzHinweis("3 von 9 angezeigt")).toBe("3/9");
    expect(D.kurzHinweis("12 von 248 angezeigt")).toBe("12/248");
    // Passt das Muster nicht, bleibt der Text UNVERAENDERT — Raten waere
    // schlimmer als Laenge.
    expect(D.kurzHinweis("nur fällige Vorgänge")).toBe("nur fällige Vorgänge");
    expect(D.kurzHinweis("")).toBe("");
    expect(D.kurzHinweis(null)).toBe("");
  });
});
