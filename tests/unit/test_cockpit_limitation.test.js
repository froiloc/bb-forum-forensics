/**
 * =============================================================================
 * tests/unit/test_cockpit_limitation.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 525 (AP-3A / Idee 32): die Cockpit-Sicht
 * "Fristen (Verjaehrung)".
 *
 *   LV01 — API-Oberflaeche vollstaendig.
 *   LV02 — DAS WORT 'VERJAEHRT' KOMMT IN KEINEM ZUSTAND VOR. Geprueft wird der
 *          gerenderte Text in ALLEN Zustaenden UND der Quelltext des Moduls
 *          (ausser dort, wo das Wort Teil des Vorbehalts 'stellt keine
 *          Verjaehrung fest' ist).
 *   LV03 — Der Verjaehrungsvorbehalt steht VOR der Tabelle (die Reihenfolge ist
 *          die Aussage).
 *   LV04 — Fehlt 'stellt_keine_verjaehrung_fest', MELDET die Sicht das in
 *          eigener Auszeichnung — sie behauptet den Vorbehalt nicht
 *          stillschweigend.
 *   LV05 — Stummer Zustand (aussage_moeglich=false): der GRUND wird gezeigt,
 *          KEINE Ampelverteilung, KEINE Schwellenauswahl — aber die Tabelle und
 *          die Datenlage BLEIBEN sichtbar.
 *   LV06 — 'ohne_tatzeit' bekommt eine EIGENE Auszeichnung (is-ungeprueft) und
 *          ist ausdruecklich NICHT 'is-offen' und nicht 'is-stumm'.
 *   LV07 — Ein UNBEKANNTER Ampelwert wird als solcher gekennzeichnet
 *          (is-unbekannt) und NICHT auf einen bekannten abgebildet.
 *   LV08 — Die Frontend-Zustandstabelle deckt genau die ACHT Zustaende des
 *          Backends ab (AMPEL_ZUSTAENDE in management/deadlines/limitation.py).
 *   LV09 — restText: null -> '—' (NIE '0'); 0 -> '0 T (heute)'; negativ ->
 *          benannt als ueberschritten.
 *   LV10 — Der Massstab (Stichtag, Vorwarnschwelle, Parametersatz-Stand,
 *          geprüfte Tatbestände) steht IMMER da — auch im stummen Zustand und
 *          beim Leerbefund.
 *   LV11 — 'ueberschritten' und 'knapp' werden AUCH MIT 0 genannt (die
 *          Abwesenheit einer Fristgefahr ist eine eigene Aussage).
 *   LV12 — Vorbehalte/Hinweise des Backends erscheinen WORTGLEICH; fehlen sie
 *          ganz, ist das ein gemeldeter Verdachtsmoment und kein Leerbefund.
 *   LV13 — Fehlerzustand: ausdruecklich KEIN Leerbefund.
 *   LV14 — Die Schwellenauswahl erscheint nur mit wirkendem Rueckruf und ruft
 *          ihn mit der Tageszahl auf; sie ist der EINZIGE Knopf der Sicht.
 *   LV15 — Kontonamen mit Markup bleiben Text (textContent), UTF-8 erhalten.
 *   LV16 — Die Datenlage steht IN der Zeile (erklaert, warum die Frist leer
 *          bleibt), als KLARTEXT (Build 527), und wird aufgeschluesselt.
 *
 * BUILD 527 — Befunde aus der PROD-Messung (uid_posts ohne Spalte 'posted'):
 *   LV17 — Ein NEUER Befund faellt NICHT aus der Zaehlung. Vorher waren die vier
 *          bekannten Befunde einzeln addiert; ein fuenfter waere unbemerkt
 *          verschwunden und die Sicht haette zu wenige ungepruefte Faelle
 *          gemeldet. Jetzt wird 'ohne Tatzeitpunkt' als REST gerechnet und jeder
 *          gelieferte Schluessel gelistet — auch ein unbekannter.
 *   LV18 — 'belegt_unvollstaendig' zaehlt als MIT Tatzeitpunkt, wird aber
 *          ausdruecklich als EINGESCHRAENKT benannt.
 *   LV19 — Der Lesefehler-Ausfall steht in eigenem Bereich VOR der Tabelle,
 *          nennt Zahl und SQLite-Ursache, sagt bei 'alle Faelle betroffen'
 *          ausdruecklich, dass das auf das SCHEMA deutet — und der Grund haengt
 *          am Titel der betroffenen Zelle. Ohne Ausfall erscheint er NICHT.
 *   LV20 — Die Frontend-Labels decken genau die DATENLAGE_BEFUNDE des Backends
 *          ab (aus limitation_repo.py gelesen, nicht abgeschrieben) — wie LV08
 *          fuer die Ampelzustaende.
 *
 * BUILD 530 — Grundlage der Zahl (Ersatzanker, vorlaeufig/festgestellt):
 *   LV21 — Die Spalte 'Grundlage' steht in JEDER Zeile und nennt Feststellung
 *          UND Ankerart. Eine vorlaeufige Zeile ist gekennzeichnet — und zwar
 *          ZUSAETZLICH zur Ampel, nicht anstelle: eine rote Zeile bleibt rot.
 *   LV22 — Die Vermerke des Backends haengen WORTGLEICH am title der Zelle;
 *          die Sicht formuliert sie NICHT neu.
 *   LV23 — Fehlt 'nur_festgestellte_zitierfaehig', MELDET die Sicht das in
 *          eigener Auszeichnung (wie LV04 fuer den Verjaehrungsvorbehalt).
 *   LV24 — Der Ersatzanker-Hinweis erscheint nur, wenn es Ersatzanker gibt,
 *          nennt die Zahl je Art und die FEHLERRICHTUNG (zu frueh, wirkt
 *          dringender). Ohne Ersatzanker erscheint er NICHT.
 *   LV25 — Die Feststellungs-Verteilung wird GENERISCH gezaehlt: ein
 *          unbekannter Wert faellt nicht aus der Summe, sondern wird mit
 *          seinem Rohnamen genannt (wie LV17 fuer die Datenlage).
 *   LV26 — Die Frontend-Labels decken genau ANKER_ARTEN und FESTSTELLUNGEN des
 *          Backends ab (aus limitation.py gelesen) — wie LV08 und LV20.
 *   LV27 — 'ohne_anker' ist ein UNGEPRUEFT-Zustand und ausdruecklich nicht
 *          'is-offen': ein unzulaessiger Ersatzanker macht einen Fall nicht
 *          unverdaechtig.
 * =============================================================================
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_limitation.js",
  "utf-8"
);

// Die Zustandsliste des BACKENDS — aus dem Python-Quelltext gelesen, nicht
// abgeschrieben. Waere sie hier von Hand gepflegt, koennte sie auseinander
// laufen, und genau das soll LV08 verhindern.
const _py = readFileSync("management/deadlines/limitation.py", "utf-8");
function backendZustaende() {
  const m = _py.match(/AMPEL_ZUSTAENDE[^=]*=\s*\(([\s\S]*?)\)/);
  if (!m) {
    throw new Error("AMPEL_ZUSTAENDE nicht in limitation.py gefunden");
  }
  return (m[1].match(/"([a-z_]+)"/g) || []).map((s) => s.replace(/"/g, ""));
}

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

function _api() {
  return _win().AIWCockpitLimitation;
}

// Build 530: dieselbe Fensterinstanz fuer API UND Rendern. Zwei Instanzen
// waeren zwei Welten — ein in der einen erzeugtes Element gehoerte nicht zur
// anderen, und die Vergleiche waeren stillschweigend bedeutungslos.
function _api2() {
  const win = _win();
  return { win: win, api: win.AIWCockpitLimitation };
}

function R(over) {
  return Object.assign(
    {
      subject_id: 101,
      username: "nutzer101",
      tatzeit_befund: "belegt",
      tatzeit_detail: "Fristbeginn = spaeteste belegte Tathandlung",
      frueheste_ts: 1600000000,
      spaeteste_ts: 1647216000,
      quellen: ["uid_posts.posted"],
      ampel: "knapp",
      befund: "Restlaufzeit 232 Tage",
      tatzeit_tag: "2022-03-14",
      massgeblich_norm: "§ 184b Abs. 3 StGB",
      massgeblich_ablauf_tag: "2027-03-14",
      restlaufzeit_tage: 232,
      deadlines: [],
      ohne_fassung: [],
      feststellung: "vorlaeufig",
      anker_art: "aktivitaet",
      anker_vermerke: ["VORLAEUFIG — das zugrunde liegende Datum ist von "
                       + "KEINER Ermittlerin festgestellt worden."],
      ohne_anker: [],
      zitierfaehig: false,
    },
    over || {}
  );
}

function D(over) {
  return Object.assign(
    {
      stichtag: "2026-07-25",
      vorwarn_tage: 365,
      aussage_moeglich: true,
      verweigerungsgrund: null,
      params_stand: "2026-07-25",
      params_bestaetigt: true,
      params_bestaetigt_von: "StA Musterperson",
      params_bestaetigt_am: "2026-07-25",
      vorgabe_tatbestaende: ["184b_abs3", "184c_abs1"],
      vorbehalte: ["UNTERBRECHUNGEN NICHT BERUECKSICHTIGT: § 78c StGB ..."],
      hinweise: ["Teilungsakte (share_id) gehen NICHT in den Fristbeginn ein."],
      faelle_gesamt: 1,
      zaehler: { knapp: 1 },
      datenlage: { belegt: 1 },
      stellt_keine_verjaehrung_fest: true,
      nur_festgestellte_zitierfaehig: true,
      anker_verteilung: { aktivitaet: 1 },
      feststellung_verteilung: { vorlaeufig: 1 },
      ersatzfehler: {},
      rows: [R()],
    },
    over || {}
  );
}

function _render(win, data, opts) {
  const main = win.document.createElement("div");
  win.AIWCockpitLimitation.renderLimitation(main, data, opts || {});
  return main;
}

describe("Build 525 — Cockpit-Sicht Fristen (AP-3A)", () => {
  it("LV01: API-Oberflaeche vollstaendig", () => {
    const api = _api();
    [
      "ampelInfo", "ampelZustaende", "vorbehaltText", "vorbehaltOk",
      "stummText", "massstabText", "datenlageText", "zaehlerText",
      "restText", "quellenText", "rows", "renderLimitation",
      "grundlageText", "grundlageTitle", "zitierhinweisText",
      "zitierhinweisOk", "ersatzankerText", "feststellungText",
      "feststellungLabel", "ankerLabel", "istErsatzanker",
    ].forEach((k) => expect(typeof api[k]).toBe("function"));
    expect(typeof api.AMPEL).toBe("object");
  });

  it("LV02: das Wort 'verjährt' kommt nirgends vor", () => {
    const win = _win();
    const faelle = [
      D(),
      D({ aussage_moeglich: false, verweigerungsgrund: "nicht bestätigt",
          zaehler: { keine_aussage: 1 },
          rows: [R({ ampel: "keine_aussage", restlaufzeit_tage: null })] }),
      D({ rows: [R({ ampel: "ueberschritten", restlaufzeit_tage: -12,
                     befund: "rechnerisch überschritten" })],
          zaehler: { ueberschritten: 1 } }),
      D({ rows: [R({ ampel: "ruht", restlaufzeit_tage: null })] }),
      D({ rows: [], faelle_gesamt: 0, zaehler: {}, datenlage: {} }),
      D({ error: "Serverfehler" }),
    ];
    for (const d of faelle) {
      const text = _render(win, d).textContent.toLowerCase();
      // Der Vorbehalt selbst enthaelt 'keine verjährung fest' — das ist die
      // EINZIGE zulaessige Verwendung. Sie wird vor der Pruefung entfernt.
      const rest = text
        .replace(/stellt keine verjährung fest/g, "")
        .replace(/keine verjährung fest/g, "")
        .replace(/als feststellung einer verjährung/g, "")
        .replace(/verjährung §§ 78 ff\. stgb/g, "")
        .replace(/verjährungs-parametersatz/g, "");
      expect(rest).not.toContain("verjährt");
      expect(rest).not.toContain("ist verjähr");
    }
    // Und im Quelltext: kein Vorkommen von 'verjährt' ausser in Kommentaren
    // ueber genau diese Regel.
    const codeOhneKommentare = _src
      .split("\n")
      .filter((l) => !l.trim().startsWith("//"))
      .join("\n");
    expect(codeOhneKommentare.toLowerCase()).not.toContain("verjährt'");
  });

  it("LV03: Vorbehalt steht VOR der Tabelle", () => {
    const win = _win();
    const main = _render(win, D());
    const vb = main.querySelector(".aiw-lim-vorbehalt");
    const tbl = main.querySelector("table.aiw-lim-table");
    expect(vb).not.toBeNull();
    expect(tbl).not.toBeNull();
    expect(
      vb.compareDocumentPosition(tbl) &
        win.Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it("LV04: fehlende Zusicherung wird GEMELDET", () => {
    const win = _win();
    const api = win.AIWCockpitLimitation;
    const d = D();
    delete d.stellt_keine_verjaehrung_fest;
    expect(api.vorbehaltOk(d)).toBe(false);
    expect(api.vorbehaltText(d)).toContain("ACHTUNG");
    const main = _render(win, d);
    const vb = main.querySelector(".aiw-lim-vorbehalt");
    expect(vb.className).toContain("is-fehlt");
    expect(vb.textContent).toContain("ACHTUNG");
  });

  it("LV05: stummer Zustand — Grund ja, Ampel nein, Tabelle ja", () => {
    const win = _win();
    const main = _render(
      win,
      D({
        aussage_moeglich: false,
        verweigerungsgrund: "ENTWURF — NICHT JURISTISCH BESTAETIGT.",
        params_bestaetigt: false,
        params_bestaetigt_von: null,
        params_bestaetigt_am: null,
        zaehler: { keine_aussage: 2 },
        datenlage: { belegt: 1, ohne_forensic_db: 1 },
        faelle_gesamt: 2,
        rows: [
          R({ ampel: "keine_aussage", restlaufzeit_tage: null,
              massgeblich_norm: null, massgeblich_ablauf_tag: null }),
          R({ subject_id: 102, username: "ohne_datei", ampel: "keine_aussage",
              tatzeit_befund: "ohne_forensic_db", tatzeit_tag: null,
              restlaufzeit_tage: null, quellen: [] }),
        ],
      }),
      { onVorwarn: () => {} }
    );
    const stumm = main.querySelector(".aiw-lim-stumm");
    expect(stumm).not.toBeNull();
    expect(stumm.textContent).toContain("KEINE FRISTAUSSAGE MÖGLICH");
    expect(stumm.textContent).toContain("NICHT JURISTISCH BESTAETIGT");
    // Keine Ampelverteilung und keine Schwellenauswahl im stummen Zustand.
    expect(main.querySelector(".aiw-lim-zaehler")).toBeNull();
    expect(main.querySelector(".aiw-lim-actions")).toBeNull();
    // ABER: Tabelle und Datenlage bleiben vollstaendig.
    expect(main.querySelectorAll("tbody tr").length).toBe(2);
    expect(main.textContent).toContain("OHNE belegten Tatzeitpunkt");
  });

  it("LV06: 'ohne_tatzeit' hat eine eigene Auszeichnung", () => {
    const win = _win();
    const api = win.AIWCockpitLimitation;
    expect(api.ampelInfo("ohne_tatzeit").cls).toBe("is-ungeprueft");
    expect(api.ampelInfo("ohne_tatzeit").label).toContain("UNGEPRÜFT");
    expect(api.ampelInfo("ohne_tatzeit").cls).not.toBe("is-offen");
    expect(api.ampelInfo("ohne_tatzeit").cls).not.toBe("is-stumm");
    const main = _render(
      win,
      D({
        zaehler: { ohne_tatzeit: 1 },
        datenlage: { ohne_tatzeit: 1 },
        rows: [R({ ampel: "ohne_tatzeit", tatzeit_befund: "ohne_tatzeit",
                   tatzeit_tag: null, restlaufzeit_tage: null,
                   massgeblich_norm: null, massgeblich_ablauf_tag: null,
                   quellen: [] })],
      })
    );
    const tr = main.querySelector("tbody tr");
    expect(tr.className).toContain("is-ungeprueft");
    expect(tr.getAttribute("data-ampel")).toBe("ohne_tatzeit");
  });

  it("LV07: unbekannter Zustand wird als solcher gekennzeichnet", () => {
    const win = _win();
    const api = win.AIWCockpitLimitation;
    const info = api.ampelInfo("voellig_neu");
    expect(info.cls).toBe("is-unbekannt");
    expect(info.label).toContain("unbekannter Zustand");
    const main = _render(
      win,
      D({ zaehler: { voellig_neu: 3 },
          rows: [R({ ampel: "voellig_neu" })] })
    );
    expect(main.querySelector("tbody tr").className).toContain("is-unbekannt");
    // Auch in der Verteilung wird er genannt statt verschwiegen.
    expect(main.querySelector(".aiw-lim-zaehler").textContent)
      .toContain("unbekannt (voellig_neu): 3");
  });

  it("LV08: Frontend deckt genau die Backend-Zustaende ab", () => {
    const fe = _api().ampelZustaende().sort();
    const be = backendZustaende().sort();
    expect(be.length).toBe(8);
    expect(fe).toEqual(be);
  });

  it("LV09: restText — null ist nicht 0", () => {
    const api = _api();
    expect(api.restText({ restlaufzeit_tage: null })).toBe("—");
    expect(api.restText({})).toBe("—");
    expect(api.restText({ restlaufzeit_tage: 0 })).toBe("0 T (heute)");
    expect(api.restText({ restlaufzeit_tage: -12 }))
      .toContain("überschritten");
    expect(api.restText({ restlaufzeit_tage: 232 })).toBe("232 T");
  });

  it("LV10: der Massstab steht immer da", () => {
    const win = _win();
    for (const d of [
      D(),
      D({ rows: [], faelle_gesamt: 0, zaehler: {}, datenlage: {} }),
      D({ aussage_moeglich: false, verweigerungsgrund: "x",
          params_bestaetigt: false, rows: [] }),
    ]) {
      const foot = _render(win, d).querySelector(".aiw-lim-foot");
      expect(foot).not.toBeNull();
      expect(foot.textContent).toContain("Stichtag");
      expect(foot.textContent).toContain("Vorwarnschwelle");
      expect(foot.textContent).toContain("Parametersatz");
      expect(foot.textContent).toContain("Tatbestände");
    }
    // Fehlt die Schwelle in der Antwort, wird das benannt statt eine Zahl
    // erfunden.
    const api = _api();
    expect(api.massstabText({ stichtag: "2026-07-25" }))
      .toContain("nicht mitgeliefert");
  });

  it("LV11: 'ueberschritten' und 'knapp' werden auch mit 0 genannt", () => {
    const t = _api().zaehlerText({ zaehler: { offen: 5 } });
    expect(t).toContain("Frist rechnerisch abgelaufen: 0");
    expect(t).toContain("unter der Vorwarnschwelle: 0");
    expect(t).toContain("Frist läuft: 5");
    // Zustaende mit 0, die KEINE Fristgefahr sind, werden weggelassen.
    expect(t).not.toContain("ruht möglicherweise");
  });

  it("LV12: Vorbehalte wortgleich; fehlen sie, ist es ein Verdachtsmoment", () => {
    const win = _win();
    const d = D({
      vorbehalte: ["Vorbehalt A mit § 78c StGB", "Vorbehalt B"],
      hinweise: ["Hinweis C zu share_id"],
    });
    const main = _render(win, d);
    const items = Array.from(
      main.querySelectorAll(".aiw-lim-vorbehalte li")
    ).map((li) => li.textContent);
    expect(items).toEqual([
      "Vorbehalt A mit § 78c StGB", "Vorbehalt B", "Hinweis C zu share_id",
    ]);
    expect(main.querySelector(".aiw-lim-vorbehalte summary").textContent)
      .toContain("(3)");

    const ohne = _render(win, D({ vorbehalte: [], hinweise: [] }));
    const meldungen = Array.from(
      ohne.querySelectorAll(".aiw-lim-vorbehalt.is-fehlt")
    ).map((e) => e.textContent);
    expect(meldungen.some((m) => m.includes("KEINE Vorbehalte"))).toBe(true);
  });

  it("LV13: Fehlerzustand ist kein Leerbefund", () => {
    const win = _win();
    const main = _render(win, { error: "Zeitüberschreitung" });
    expect(main.textContent).toContain("KEIN Leerbefund");
    expect(main.textContent).toContain("Zeitüberschreitung");
    expect(main.querySelector("table.aiw-lim-table")).toBeNull();
  });

  it("LV14: Schwellenauswahl nur mit Wirkung; einziger Knopf der Sicht", () => {
    const win = _win();
    // OHNE Rueckruf: kein Bedienelement (ein Knopf ohne Wirkung waere
    // schlimmer als keiner).
    const ohne = _render(win, D());
    expect(ohne.querySelectorAll("button").length).toBe(0);

    const gerufen = [];
    const mit = _render(win, D(), {
      onVorwarn: (t) => gerufen.push(t),
    });
    const btns = mit.querySelectorAll("button.aiw-lim-schwelle");
    expect(btns.length).toBe(3);
    // Die aktive Schwelle ist markiert.
    const aktiv = mit.querySelector("button.aiw-lim-schwelle.is-active");
    expect(aktiv.getAttribute("data-tage")).toBe("365");
    btns[0].dispatchEvent(new win.Event("click"));
    expect(gerufen).toEqual([180]);
    // Es gibt KEINE weiteren Bedienelemente (kein Schreibpfad in dieser Sicht).
    expect(mit.querySelectorAll("input, select, form").length).toBe(0);
    expect(mit.querySelectorAll("button").length).toBe(3);
  });

  it("LV15: Markup in Kontonamen bleibt Text, UTF-8 erhalten", () => {
    const win = _win();
    const main = _render(
      win,
      D({ rows: [R({ username: "<img src=x onerror=alert(1)> Ünïcødé" })] })
    );
    expect(main.querySelector("img")).toBeNull();
    expect(main.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(main.textContent).toContain("Ünïcødé");
  });

  it("LV16: die Datenlage steht in der Zeile und wird aufgeschluesselt", () => {
    const win = _win();
    const main = _render(
      win,
      D({
        faelle_gesamt: 4,
        datenlage: { belegt: 1, ohne_forensic_db: 1, nicht_lesbar: 1,
                     ohne_tatzeit: 1 },
        zaehler: { knapp: 1, keine_aussage: 3 },
        rows: [
          R(),
          R({ subject_id: 102, tatzeit_befund: "ohne_forensic_db" }),
          R({ subject_id: 103, tatzeit_befund: "nicht_lesbar" }),
          R({ subject_id: 104, tatzeit_befund: "ohne_tatzeit" }),
        ],
      })
    );
    // Build 527: die Zelle zeigt KLARTEXT statt des Rohcodes — der Rohcode
    // sagte einer Ermittlerin nichts.
    const api = win.AIWCockpitLimitation;
    const zellen = Array.from(
      main.querySelectorAll("td.aiw-lim-datenlage")
    ).map((td) => td.textContent);
    expect(zellen).toEqual([
      api.datenlageLabel("belegt"),
      api.datenlageLabel("ohne_forensic_db"),
      api.datenlageLabel("nicht_lesbar"),
      api.datenlageLabel("ohne_tatzeit"),
    ]);
    const sub = main.querySelector(".aiw-pagesub").textContent;
    expect(sub).toContain("3 davon OHNE belegten Tatzeitpunkt");
    expect(sub).toContain("keine forensic-Datei: 1");
    expect(sub).toContain("Datei nicht lesbar: 1");
    expect(sub).toContain("kein Zeitstempel gesetzt: 1");
    // Die Quelle des Fristbeginns steht ebenfalls in der Zeile.
    expect(main.querySelector("td.aiw-lim-quelle").textContent)
      .toBe("uid_posts.posted");
  });

  // ===========================================================================
  // Build 527 — die Befunde aus der PROD-Messung (uid_posts ohne 'posted').
  // ===========================================================================

  it("LV17: ein NEUER Befund fällt nicht aus der Zählung", () => {
    // Der eigentliche Regressionsschutz: vor Build 527 waren die vier damals
    // bekannten Befunde EINZELN addiert. Ein neuer Befund waere aus der Summe
    // gefallen, und die Sicht haette weniger ungepruefte Faelle gemeldet, als
    // es gab. Hier steht ein frei erfundener Befund — die Rechnung muss
    // trotzdem aufgehen.
    const api = _api();
    const t = api.datenlageText({
      faelle_gesamt: 10,
      datenlage: { belegt: 4, voellig_neuer_befund: 6 },
    });
    expect(t).toContain("6 davon OHNE belegten Tatzeitpunkt");
    expect(t).toContain("4 mit");
    // Und der unbekannte Befund wird BENANNT statt weggelassen.
    expect(t).toContain("unbekannter Befund (voellig_neuer_befund): 6");
  });

  it("LV18: 'belegt_unvollstaendig' zählt als MIT Tatzeitpunkt", () => {
    const api = _api();
    expect(api.BEFUNDE_MIT_TATZEIT).toEqual(["belegt",
                                             "belegt_unvollstaendig"]);
    const t = api.datenlageText({
      faelle_gesamt: 5,
      datenlage: { belegt: 2, belegt_unvollstaendig: 3 },
    });
    expect(t).toContain("0 davon OHNE belegten Tatzeitpunkt");
    expect(t).toContain("5 mit");
    // Aber die Einschraenkung wird ausdruecklich benannt.
    expect(api.datenlageLabel("belegt_unvollstaendig"))
      .toContain("EINGESCHRÄNKT");
  });

  it("LV19: der Lesefehler-Ausfall steht oben und nennt die Ursache", () => {
    const win = _win();
    const api = win.AIWCockpitLimitation;
    const d = D({
      faelle_gesamt: 3,
      faelle_mit_quellenfehler: 3,
      quellenfehler: { "uid_posts.posted: no such column: posted": 3 },
      datenlage: { zeitspalte_unlesbar: 3 },
      rows: [R({ ampel: "ohne_tatzeit", tatzeit_befund: "zeitspalte_unlesbar",
                 quellen: [], restlaufzeit_tage: null,
                 quellen_fehler: ["uid_posts.posted: no such column: posted"] })],
    });
    // Reine Funktion: der Satz nennt Zahl, Ursache und die Schlussfolgerung.
    const t = api.quellenfehlerText(d);
    expect(t).toContain("DATENLAGE EINGESCHRÄNKT");
    expect(t).toContain("no such column");
    expect(t).toContain("bei ALLEN");        // 3 von 3 -> Schema-Befund
    expect(t).toContain("Ursache zu klären");
    // Ohne Fehler gibt es den Satz NICHT (er soll etwas bedeuten).
    expect(api.quellenfehlerText(D())).toBeNull();

    // Im DOM: eigener Bereich, und er steht VOR der Tabelle.
    const main = _render(win, d);
    const box = main.querySelector(".aiw-lim-quellenfehler");
    expect(box).not.toBeNull();
    const tbl = main.querySelector("table.aiw-lim-table");
    expect(
      box.compareDocumentPosition(tbl) &
        win.Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    // Und der SQLite-Grund haengt an der Zelle der betroffenen Zeile.
    const zelle = main.querySelector("td.aiw-lim-datenlage");
    expect(zelle.className).toContain("is-eingeschraenkt");
    expect(zelle.getAttribute("title")).toContain("no such column");
  });

  it("LV20: Frontend-Labels deckeln die Backend-Befunde ab", () => {
    // Wie LV08 fuer die Ampel: die Liste im Python-Modul ist die Wahrheit.
    const py = readFileSync("management/deadlines/limitation_repo.py", "utf-8");
    const m = py.match(/DATENLAGE_BEFUNDE[^=]*=\s*\(([\s\S]*?)\)/);
    expect(m).not.toBeNull();
    const be = (m[1].match(/"([a-z_]+)"/g) || [])
      .map((x) => x.replace(/"/g, ""))
      .sort();
    const fe = Object.keys(_api().DATENLAGE_LABEL).sort();
    expect(be.length).toBe(7);
    expect(fe).toEqual(be);
  });

  // ===========================================================================
  // BUILD 530 — Grundlage der Zahl.
  // ===========================================================================

  it("LV21: die Grundlage steht in der Zeile, ZUSAETZLICH zur Ampel", () => {
    const { win } = _api2();
    const main = _render(
      win,
      D({
        zaehler: { ueberschritten: 1 },
        rows: [
          R({
            ampel: "ueberschritten",
            feststellung: "vorlaeufig",
            anker_art: "registrierung",
          }),
        ],
      })
    );
    const zelle = main.querySelector("td.aiw-lim-grundlage");
    expect(zelle).not.toBeNull();
    expect(zelle.textContent).toContain("VORLÄUFIG");
    expect(zelle.textContent).toContain("ERSATZANKER");
    expect(zelle.className).toContain("is-vorlaeufig");
    expect(zelle.className).toContain("is-ersatzanker");
    // DIE ENTSCHEIDENDE ZUSICHERUNG: die Ampel bleibt unberuehrt. Genau diese
    // Kombination — rechnerisch abgelaufen UND nie festgestellt — waere in
    // einer einzigen Farbskala nicht darstellbar gewesen.
    const zeile = main.querySelector("tr.aiw-lim-row");
    expect(zeile.className).toContain("is-ueberschritten");
    expect(zeile.getAttribute("data-ampel")).toBe("ueberschritten");
  });

  it("LV22: die Vermerke haengen wortgleich am title", () => {
    const { win, api } = _api2();
    const vermerk = "VORLAEUFIG — ein ganz bestimmter Wortlaut des Backends.";
    const row = R({ anker_vermerke: [vermerk] });
    expect(api.grundlageTitle(row)).toBe(vermerk);
    const main = _render(win, D({ rows: [row] }));
    expect(
      main.querySelector("td.aiw-lim-grundlage").getAttribute("title")
    ).toBe(vermerk);
  });

  it("LV23: fehlende Zitier-Zusicherung wird GEMELDET", () => {
    const { win, api } = _api2();
    expect(api.zitierhinweisOk(D())).toBe(true);
    const ohne = D();
    delete ohne.nur_festgestellte_zitierfaehig;
    expect(api.zitierhinweisOk(ohne)).toBe(false);
    expect(api.zitierhinweisText(ohne)).toContain("ACHTUNG");
    const main = _render(win, ohne);
    const box = main.querySelector(".aiw-lim-zitierhinweis");
    expect(box).not.toBeNull();
    expect(box.className).toContain("is-fehlt");
  });

  it("LV24: Ersatzanker-Hinweis nur mit Ersatzankern, mit Fehlerrichtung", () => {
    const { win, api } = _api2();
    // Ohne Ersatzanker: kein Hinweis (er soll etwas bedeuten).
    expect(api.ersatzankerText(D())).toBeNull();
    expect(_render(win, D()).querySelector(".aiw-lim-ersatzanker")).toBeNull();

    const d = D({
      faelle_gesamt: 5,
      anker_verteilung: { aktivitaet: 2, registrierung: 2, anmeldung: 1 },
      feststellung_verteilung: { vorlaeufig: 5 },
    });
    const t = api.ersatzankerText(d);
    expect(t).toContain("3 von 5");
    expect(t).toContain("Registrierung: 2");
    expect(t).toContain("Anmeldung: 1");
    // Die Fehlerrichtung MUSS dastehen, sonst liest jemand die Liste falsch.
    expect(t).toContain("ZU FRÜH");
    expect(t).toContain("DRINGENDER");
    expect(t).toContain("§ 78a StGB");
    const box = _render(win, d).querySelector(".aiw-lim-ersatzanker");
    expect(box).not.toBeNull();
  });

  it("LV25: unbekannte Feststellung faellt nicht aus der Summe", () => {
    const api = _api();
    const t = api.feststellungText(
      D({ feststellung_verteilung: { vorlaeufig: 3, zukunftswert: 2 } })
    );
    expect(t).toContain("VORLÄUFIG: 3");
    // Der unbekannte Wert wird GENANNT statt weggelassen.
    expect(t).toContain("zukunftswert");
    expect(t).toContain("2");
    // Ohne Verteilung gibt es den Satz nicht.
    expect(api.feststellungText(D({ feststellung_verteilung: {} }))).toBeNull();
  });

  it("LV26: Frontend-Labels decken ANKER_ARTEN und FESTSTELLUNGEN ab", () => {
    // Wie LV08/LV20: die Listen im Python-Modul sind die Wahrheit.
    const py = readFileSync("management/deadlines/limitation.py", "utf-8");
    const lies = (name) => {
      const m = py.match(
        new RegExp(name + "[^=]*=\\s*\\(([\\s\\S]*?)\\)")
      );
      expect(m).not.toBeNull();
      return (m[1].match(/"([a-z_]+)"/g) || [])
        .map((x) => x.replace(/"/g, ""))
        .sort();
    };
    const api = _api();
    expect(Object.keys(api.ANKER_LABEL).sort()).toEqual(lies("ANKER_ARTEN"));
    expect(Object.keys(api.FESTSTELLUNG_LABEL).sort()).toEqual(
      lies("FESTSTELLUNGEN")
    );
    expect(api.ERSATZANKER_ARTEN.slice().sort()).toEqual(
      lies("ERSATZANKER_ARTEN")
    );
  });

  it("LV27: 'ohne_anker' ist ungeprueft, nicht offen", () => {
    const { win, api } = _api2();
    expect(api.ampelInfo("ohne_anker").cls).toBe("is-ungeprueft");
    expect(api.ampelInfo("ohne_anker").label).toContain("UNGEPRÜFT");
    const main = _render(
      win,
      D({
        zaehler: { ohne_anker: 1 },
        rows: [R({ ampel: "ohne_anker", anker_art: "registrierung",
                   restlaufzeit_tage: null, massgeblich_norm: null })],
      })
    );
    const zeile = main.querySelector("tr.aiw-lim-row");
    expect(zeile.className).toContain("is-ungeprueft");
    expect(zeile.className).not.toContain("is-offen");
    expect(zeile.className).not.toContain("is-stumm");
  });
});
