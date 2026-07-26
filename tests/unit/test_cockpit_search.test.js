/**
 * =============================================================================
 * tests/unit/test_cockpit_search.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7 · AP-3E · Build 563
 * =============================================================================
 * Testsuite fuer die Sicht der fallübergreifenden Volltextsuche
 * (cockpit_search.js).
 *
 * EIGENE DATEI, NICHT ANHANG AN EINE BESTEHENDE SUITE: mc entwickelt parallel
 * Oberflaechenverbesserungen als eigenen Branch, und Instanz A arbeitet
 * gleichzeitig am selben Repository (Parallelbetrieb §4). Eine neue Datei
 * laesst sich zusammenfuehren, ein Einschub mitten in eine bestehende Suite
 * erzeugt Konflikte.
 *
 *   CS01 — STUFE 1 ZEIGT KEINEN TEXT. Der gerenderte Knoten enthaelt keinen
 *          Annotationstext — der Kern des Freigabemodells, als Anker
 *          festgehalten.
 *   CS02 — Die drei Fassungen stehen NEBENEINANDER und werden nie summiert;
 *          'aktuell' steht immer, auch bei 0.
 *   CS03 — Der Indexstand steht im Kopf, und ein NICHT belastbarer Stand wird
 *          hervorgehoben.
 *   CS04 — Der Zeitraum nennt die Zahl der Saetze OHNE Zeitstempel; sonst
 *          saehe er vollstaendiger aus, als er ist.
 *   CS05 — Sichtbarkeit: 'inhalt' bei Erlaubnis, 'anfragen' bei Sperre,
 *          'keiner' ohne Handelnden — drei unterscheidbare Ausgaenge.
 *   CS06 — Eine Sperre erzeugt einen KNOPF, keine blosse Fehlermeldung: die
 *          Anfrage ist der vorgesehene naechste Schritt.
 *   CS07 — Die Zweckangabe ist Pflicht; bei 'sonstiges' zusaetzlich der
 *          Freitext. eingabeFehler nennt den Grund im Klartext.
 *   CS08 — Der Teilstringmodus verlangt drei Zeichen — vor dem Absenden.
 *   CS09 — Eine gekappte Trefferliste wird GEMELDET (keine stille Kappung).
 *   CS10 — Der Leerbefund wird als solcher benannt UND als protokolliert
 *          ausgewiesen; 'noch nicht gesucht' ist etwas ANDERES.
 *   CS11 — Stufe 2: ein Treffer OHNE Bestaetigung erscheint MIT Befund und
 *          OHNE Text — er wird nicht weggelassen.
 *   CS12 — Stufe 2 gesperrt: kein Text, aber der Weg zur Freigabe.
 *   CS13 — sonstigesAnteil ist die Kennzahl aus E-3; ohne Grundgesamtheit
 *          liefert sie null und ausdruecklich NICHT 0.
 *   CS14 — Alle Texte laufen ueber textContent: ein HTML-artiger Begriff
 *          erzeugt KEIN Element (der Bestand ist multilingual und enthaelt
 *          von Beschuldigten geschriebene Zeichenfolgen).
 * =============================================================================
 */

import { describe, it, expect, beforeEach } from "vitest";
import { JSDOM } from "jsdom";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const HIER = dirname(fileURLToPath(import.meta.url));
const QUELLE = resolve(HIER, "../../management/server/static/cockpit_search.js");

/** Laedt den ECHTEN Code (UMD-Ausgang) — kein Nachbau. */
function _api() {
  const code = readFileSync(QUELLE, "utf8");
  const modul = { exports: {} };
  // eslint-disable-next-line no-new-func
  new Function("module", "window", "document", "console", code)(
    modul, globalThis.window, globalThis.document, console);
  return modul.exports;
}

function domSetzen() {
  const dom = new JSDOM('<!doctype html><html><body>'
    + '<div id="aiw-main"></div></body></html>');
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  return dom.window.document.getElementById("aiw-main");
}

function lage(ueber = {}) {
  return Object.assign({
    stufe: "lage",
    begriff: "birnenmus",
    modus: "wort",
    zweck_code: "kreuzbezug_nickname",
    zweck_klartext: "Kreuzbezug zu einem Nickname",
    befund: "ok",
    befund_klartext: "Abfrage durchgefuehrt.",
    gekappt: false,
    grenze: 5000,
    treffer_gesamt: 4,
    faelle: [{
      subject_id: 5023,
      treffer_gesamt: 4,
      nach_fassung: { aktuell: 3, ueberholt: 1, zurueckgenommen: 0 },
      arten: [{ code: "annotation_text", label: "Annotation (Text)", count: 3 }],
      urheber: [{ kuerzel: "h002", count: 4 }],
      von_ts: 1700000000, bis_ts: 1700600000, ohne_ts: 1,
      sichtbarkeit: { erlaubt: false, grund: "gesperrt",
                      klartext: "Inhalt gesperrt — Freigabe erforderlich." }
    }],
    indexstand: { indexzeitpunkt: 1700600000, belastbar: true,
                  hinweis: "Der Index ist belegt aktuell und vollstaendig.",
                  veraendert_seit_index: 0, veraenderte_faelle: [],
                  noch_nie_indiziert: [], unvollstaendig: [] },
    audit_seq: 42
  }, ueber);
}

describe("cockpit_search — Stufe 1", () => {
  let main;
  beforeEach(() => { main = domSetzen(); });

  it("CS01: Stufe 1 zeigt KEINEN Textausschnitt", () => {
    const api = _api();
    // Ein Fall, in dessen Daten NIRGENDS ein Annotationstext steht — der
    // Server liefert in Stufe 1 keinen. Der Test haelt fest, dass die Sicht
    // auch keinen erfindet und keine Textfelder anlegt.
    const erg = api.renderSearch(main, lage(), {});
    expect(erg.state).toBe("befund");
    expect(main.querySelectorAll(".aiw-search-text").length).toBe(0);
    expect(main.textContent).not.toContain("Thread");
  });

  it("CS02: die drei Fassungen stehen nebeneinander, nie summiert", () => {
    const api = _api();
    expect(api.fassungText({ aktuell: 3, ueberholt: 1, zurueckgenommen: 0 }))
      .toBe("aktuell: 3 · überholt: 1");
    // 'aktuell' steht IMMER — auch bei 0. Sonst bliebe offen, ob es daneben
    // noch gueltige Treffer gibt.
    expect(api.fassungText({ aktuell: 0, zurueckgenommen: 2 }))
      .toBe("aktuell: 0 · zurückgenommen: 2");
    expect(api.fassungText(null)).toBe("aktuell: 0");
    // Und nirgends eine Summe.
    expect(api.fassungText({ aktuell: 3, ueberholt: 1 })).not.toContain("4");
  });

  it("CS03: Indexstand im Kopf; nicht belastbar wird hervorgehoben", () => {
    const api = _api();
    expect(api.standIstWarnung({ belastbar: true })).toBe(false);
    expect(api.standIstWarnung({ belastbar: false })).toBe(true);
    expect(api.standIstWarnung(null)).toBe(false);

    api.renderSearch(main, lage(), {});
    expect(main.querySelectorAll(".aiw-search-stand--warn").length).toBe(0);

    main = domSetzen();
    const api2 = _api();
    api2.renderSearch(main, lage({
      indexstand: { indexzeitpunkt: 1700000000, belastbar: false,
                    hinweis: "2 Datenbank(en) haben sich geaendert.",
                    veraendert_seit_index: 2 }
    }), {});
    expect(main.querySelectorAll(".aiw-search-stand--warn").length).toBe(1);
    expect(main.textContent).toContain("geaendert");
  });

  it("CS04: der Zeitraum nennt die Saetze ohne Zeitstempel", () => {
    const api = _api();
    expect(api.zeitraumText({ von_ts: 1700000000, bis_ts: 1700600000,
                              ohne_ts: 1 })).toContain("1 ohne Zeitpunkt");
    expect(api.zeitraumText({ von_ts: 1700000000, bis_ts: 1700000000,
                              ohne_ts: 0 })).not.toContain("bis");
    // Nur Saetze ohne Zeitpunkt: das ist NICHT '—', sondern eine Aussage.
    expect(api.zeitraumText({ von_ts: null, bis_ts: null, ohne_ts: 3 }))
      .toBe("kein Zeitpunkt erfasst");
    expect(api.zeitraumText({ von_ts: null, bis_ts: null, ohne_ts: 0 }))
      .toBe("—");
  });

  it("CS05/CS06: Sperre erzeugt einen Knopf, keine blosse Meldung", () => {
    const api = _api();
    expect(api.sichtbarkeitsKnopf({ erlaubt: true, grund: "eigener_fall" }))
      .toBe("inhalt");
    expect(api.sichtbarkeitsKnopf({ erlaubt: false, grund: "gesperrt" }))
      .toBe("anfragen");
    expect(api.sichtbarkeitsKnopf({ erlaubt: false, grund: "unbekannt_wer" }))
      .toBe("keiner");
    expect(api.sichtbarkeitsKnopf(null)).toBe("keiner");

    let angefragt = null;
    api.renderSearch(main, lage(), {
      onAnfrage: function (uid) { angefragt = uid; }
    });
    const knoepfe = Array.from(main.querySelectorAll("button"))
      .filter((b) => b.textContent === "Freigabe anfragen");
    expect(knoepfe.length).toBe(1);
    knoepfe[0].dispatchEvent(new globalThis.window.Event("click"));
    expect(angefragt).toBe(5023);
  });

  it("CS07/CS08: Zweckangabe und Teilstringlaenge werden vorab geprueft", () => {
    const api = _api();
    const zwecke = [
      { code: "kreuzbezug_nickname", label: "Kreuzbezug", freitext_pflicht: false },
      { code: "sonstiges", label: "Sonstiges", freitext_pflicht: true }
    ];
    expect(api.eingabeFehler({ begriff: "" }, zwecke))
      .toContain("Suchbegriff");
    expect(api.eingabeFehler({ begriff: "x" }, zwecke))
      .toContain("Zweckangabe");
    expect(api.eingabeFehler(
      { begriff: "x", zweck_code: "sonstiges", zweck_freitext: "  " }, zwecke))
      .toContain("Begründung");
    expect(api.eingabeFehler(
      { begriff: "ab", zweck_code: "kreuzbezug_nickname",
        modus: "teilstring" }, zwecke)).toContain("3 Zeichen");
    // Alles beisammen -> kein Fehler.
    expect(api.eingabeFehler(
      { begriff: "birnenmus", zweck_code: "kreuzbezug_nickname",
        modus: "wort" }, zwecke)).toBe(null);
    expect(api.zweckBrauchtFreitext(zwecke, "sonstiges")).toBe(true);
    expect(api.zweckBrauchtFreitext(zwecke, "kreuzbezug_nickname")).toBe(false);
    expect(api.zweckBrauchtFreitext(zwecke, "gibt_es_nicht")).toBe(false);
  });

  it("CS09: eine gekappte Trefferliste wird gemeldet", () => {
    const api = _api();
    expect(api.gekapptHinweis({ gekappt: false })).toBe(null);
    const h = api.gekapptHinweis({ gekappt: true, grenze: 5000 });
    expect(h).toContain("5000");
    expect(h).toContain("UNVOLLSTAENDIG");
    api.renderSearch(main, lage({ gekappt: true, grenze: 5000 }), {});
    expect(main.textContent).toContain("UNVOLLSTAENDIG");
  });

  it("CS10: Leerbefund und 'noch nicht gesucht' sind verschieden", () => {
    const api = _api();
    const leer = api.renderSearch(main, lage({ faelle: [], treffer_gesamt: 0 }),
                                  {});
    expect(leer.state).toBe("leer");
    expect(main.textContent).toContain("protokolliert");

    main = domSetzen();
    const api2 = _api();
    const bereit = api2.renderSearch(main, {}, {});
    expect(bereit.state).toBe("bereit");
    expect(main.textContent).toContain("Noch keine Abfrage");
    expect(main.textContent).not.toContain("Kein Treffer");
  });

  it("CS13: sonstigesAnteil ist eine Kennzahl, kein erfundenes Null", () => {
    const api = _api();
    expect(api.sonstigesAnteil([])).toBe(null);
    expect(api.sonstigesAnteil(null)).toBe(null);
    expect(api.sonstigesAnteil([{ zweck_code: "sonstiges" },
                                { zweck_code: "wiedervorlage" }])).toBe(50);
    expect(api.sonstigesAnteil([{ zweck_code: "wiedervorlage" }])).toBe(0);
  });

  it("CS14: Texte laufen ueber textContent — kein Element aus Eingabe", () => {
    const api = _api();
    const boese = '<img src=x onerror="1">';
    api.renderSearch(main, lage({
      zweck_klartext: boese,
      faelle: [Object.assign({}, lage().faelle[0], {
        urheber: [{ kuerzel: boese, count: 1 }]
      })]
    }), {});
    expect(main.querySelectorAll("img").length).toBe(0);
    expect(main.textContent).toContain("onerror");
  });
});

describe("cockpit_search — Stufe 2", () => {
  let main;
  beforeEach(() => { main = domSetzen(); });

  it("CS11: unbestaetigte Treffer erscheinen MIT Befund und OHNE Text", () => {
    const api = _api();
    const daten = {
      stufe: "inhalt", subject_id: 5023, erlaubt: true,
      sichtbarkeit: { erlaubt: true, grund: "eigener_fall", klartext: "frei" },
      befund: "ok", treffer_gesamt: 2, gegen_quelle_bestaetigt: 1,
      nicht_bestaetigt: 1,
      verifikationshinweis: "1 von 2 Treffern konnten NICHT gegen die Quelle "
        + "bestaetigt werden; fuer sie wird kein Text angezeigt.",
      treffer: [
        { satz_art: "annotation_text", satz_art_label: "Annotation (Text)",
          quell_tabelle: "annotations", quell_spalte: "text",
          quell_schluessel: "1", fassung: "aktuell", ts: 1700000000,
          urheber: "h002", verifikation: "bestaetigt",
          verifikation_klartext: "gegen die Quelle bestaetigt",
          ausschnitt: "Nickname birnenmus taucht auf",
          ausschnitt_gekuerzt: false },
        { satz_art: "annotation_text", satz_art_label: "Annotation (Text)",
          quell_tabelle: "annotations", quell_spalte: "text",
          quell_schluessel: "2", fassung: "aktuell", ts: 1700000100,
          urheber: "h002", verifikation: "abweichend",
          verifikation_klartext: "Index veraltet — der Datensatz existiert, "
            + "sein Text lautet in der Quelle anders.",
          ausschnitt: null, ausschnitt_gekuerzt: false }
      ],
      indexstand: { indexzeitpunkt: 1700600000, belastbar: true, hinweis: "ok" }
    };
    const erg = api.renderInhalt(main, daten, {});
    expect(erg.state).toBe("befund");
    expect(erg.count).toBe(2);
    // Der bestaetigte Treffer zeigt Text ...
    expect(main.textContent).toContain("Nickname birnenmus taucht auf");
    // ... der unbestaetigte NICHT, aber er ist da und traegt seinen Grund.
    expect(main.querySelectorAll(".aiw-search-text").length).toBe(1);
    expect(main.textContent).toContain("Index veraltet");
    expect(main.querySelectorAll(".aiw-search-treffer").length).toBe(2);
  });

  it("CS12: gesperrte Stufe 2 zeigt keinen Text, aber den Weg", () => {
    const api = _api();
    let angefragt = null;
    const erg = api.renderInhalt(main, {
      stufe: "inhalt", subject_id: 6114, erlaubt: false,
      sichtbarkeit: { erlaubt: false, grund: "gesperrt",
                      klartext: "Inhalt gesperrt — Freigabe erforderlich." },
      treffer: [],
      indexstand: { indexzeitpunkt: 1700600000, belastbar: true, hinweis: "ok" }
    }, { onAnfrage: function (uid) { angefragt = uid; } });
    expect(erg.state).toBe("gesperrt");
    expect(main.querySelectorAll(".aiw-search-text").length).toBe(0);
    const b = Array.from(main.querySelectorAll("button"))
      .filter((x) => x.textContent === "Freigabe anfragen");
    expect(b.length).toBe(1);
    b[0].dispatchEvent(new globalThis.window.Event("click"));
    expect(angefragt).toBe(6114);
  });

  it("verifikationText faellt nie auf eine leere Zelle zurueck", () => {
    const api = _api();
    expect(api.verifikationText(null)).toBe("—");
    expect(api.verifikationText({ verifikation: "irgendwas" }))
      .toContain("irgendwas");
    expect(api.verifikationText({ verifikation_klartext: "X" })).toBe("X");
  });
});
