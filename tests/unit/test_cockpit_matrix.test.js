/**
 * =============================================================================
 * tests/unit/test_cockpit_matrix.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 539 (AP-3B): die Cockpit-Sicht
 * "Dringlichkeit & Erkenntnislage" (cockpit_matrix.js).
 *
 * Der Rechenkern ist in Build 536 geprueft, der Sammler in 537, die
 * Fristkomponente in 538. Diese Suite prueft AUSSCHLIESSLICH, was die SICHT
 * behauptet — und vor allem, was sie NICHT behaupten darf.
 *
 *   MV01 — API-Oberflaeche vollstaendig (ein fehlender Ausgang bricht
 *          cockpit.js erst zur Laufzeit).
 *   MV02 — DIE ZWECKBINDUNG WIRD NICHT IM FRONTEND FORMULIERT. Der angezeigte
 *          Text ist der des Backends, ZEICHENGLEICH. Eine zweite Formulierung
 *          waere eine zweite Wahrheitsquelle (§ 261 StPO).
 *   MV03 — Fehlt 'ist_keine_beweiswuerdigung' oder die Zweckbindung, MELDET
 *          die Sicht das in eigener Auszeichnung — sie behauptet die
 *          Zweckbindung NICHT stillschweigend.
 *   MV04 — Dasselbe fuer 'schreibt_keine_prioritaet'.
 *   MV05 — DAS FUENFTE FELD: eine nicht bestimmbare Dringlichkeit zeigt
 *          'mind. N' und NIEMALS eine 0 als Wert. Der Grund haengt an der
 *          Zelle.
 *   MV06 — Die DREI FRISTZUSTAENDE bekommen DREI verschiedene Texte:
 *          nicht geladen / geladen-ohne-Aussage / geladen-und-gerechnet.
 *   MV07 — 'nicht_geladen' und 'keine_aussage' ergeben VERSCHIEDENE
 *          Zellentexte. Sie gleich aussehen zu lassen waere die
 *          folgenschwerste Vereinfachung dieser Sicht.
 *   MV08 — Die Frontend-Quadrantentabelle deckt genau die QUADRANTEN des
 *          Backends ab (aus urgency_matrix.py GELESEN, nicht abgeschrieben).
 *   MV09 — Dasselbe fuer BELASTBARKEITEN.
 *   MV10 — Ein UNBEKANNTER Quadrant wird als solcher gekennzeichnet
 *          (is-unbekannt) und NICHT auf einen bekannten abgebildet.
 *   MV11 — Die Gruppen stehen in der Reihenfolge der Beachtung:
 *          'nicht_bestimmbar' ZUERST, nicht am Ende.
 *   MV12 — Innerhalb einer Gruppe bleibt die Reihenfolge des BACKENDS
 *          erhalten — die Sicht sortiert NICHT nach.
 *   MV13 — 'nicht_bestimmbar' und 'gefaehrlich' werden AUCH MIT 0 genannt.
 *   MV14 — Die Begruendung steht in einem <details> und ist beim Aufbau
 *          GESCHLOSSEN (mc: die Oberflaeche soll klar bleiben).
 *   MV15 — Die Punkte der Beitraege summieren sich zum ausgewiesenen Wert;
 *          weicht das ab, wird die Zelle als UNSTIMMIG markiert.
 *   MV16 — Die Vermerke des Backends erscheinen WORTGLEICH (u. a. der
 *          § 78c-Vorbehalt) und werden nicht neu formuliert.
 *   MV17 — Der Massstab (Stichtag, Gewichtungsstand, Maxima, Schwellen,
 *          ausgeschlossene Kriterien, Laufzeit) steht IMMER da — auch beim
 *          Leerbefund.
 *   MV18 — Ausgefallene Quellen erscheinen VOR den Gruppen und nennen die
 *          Fehlerrichtung ('harmloser aussehen, als er ist'). Ohne
 *          Ausfall: nicht da.
 *   MV19 — Unbekannte Konfidenz-Codes werden benannt und sagen ausdruecklich,
 *          dass eine FACHLICHE Entscheidung faellig ist.
 *   MV20 — Fehlerzustand: ausdruecklich KEIN Leerbefund.
 *   MV21 — Der Fristen-Schalter erscheint nur mit wirkendem Rueckruf und ruft
 *          ihn mit true/false auf; er ist der EINZIGE Knopf der Sicht.
 *   MV22 — Kontonamen mit Markup bleiben Text (textContent), UTF-8 erhalten.
 *   MV23 — Die Bezugsgroesse der Y-Achse steht IN der Zeile ('von N') — sonst
 *          liesse sich der Wert nicht gegen /api/results/coverage halten, das
 *          ueber ZEHN Kriterien rechnet.
 *   MV24 — Fehlen die Vorbehalte ganz, ist das ein gemeldeter Verdachtsmoment
 *          und kein Leerbefund.
 *   MV25 — Der Fristanteil wird NICHT geraten: ohne 'frist_max' steht '?'.
 * =============================================================================
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/cockpit_matrix.js", "utf-8");

// Die Listen des BACKENDS — aus dem Python-Quelltext GELESEN, nicht
// abgeschrieben. Von Hand gepflegt koennten sie auseinanderlaufen, und genau
// das sollen MV08/MV09 verhindern (dasselbe Muster wie LV08 in Build 525).
const _py = readFileSync("management/results/urgency_matrix.py", "utf-8");

function backendListe(name) {
  const m = _py.match(new RegExp(name + "[^=]*=\\s*\\(([\\s\\S]*?)\\)"));
  if (!m) {
    throw new Error(name + " nicht in urgency_matrix.py gefunden");
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

// EINE Fensterinstanz fuer API UND Rendern. Zwei Instanzen waeren zwei Welten
// (Build 530, LV-Kommentar) — Vergleiche waeren stillschweigend bedeutungslos.
function _both() {
  const win = _win();
  return { win: win, api: win.AIWCockpitMatrix };
}

function _api() {
  return _win().AIWCockpitMatrix;
}

/** Eine Matrixzelle mit sinnvollen Vorgaben. */
function Z(over) {
  return Object.assign(
    {
      subject_id: 101,
      username: "nutzer101",
      dringlichkeit: 55,
      dringlichkeit_mindestens: 15,
      dringlichkeit_bestimmbar: true,
      dringlichkeit_belastbarkeit: "vorlaeufig",
      dringlichkeit_grund: null,
      erkenntnislage: 30,
      erkenntnislage_bestimmbar: true,
      n_kriterien_matrix: 9,
      quadrant: "arbeitsreif",
      quadrant_bedeutung: "Hohe Dringlichkeit bei belastbarer Erkenntnislage.",
      beitraege: [
        {
          achse: "dringlichkeit",
          code: "frist",
          punkte: 40,
          grund: "Restlaufzeit 311 Tage (Schwelle 365).",
        },
        {
          achse: "dringlichkeit",
          code: "unzugewiesen",
          punkte: 10,
          grund: "Der Fall ist niemandem zugewiesen.",
        },
        {
          achse: "dringlichkeit",
          code: "liegezeit",
          punkte: 5,
          grund: "Seit 120 Tagen kein Ereignis (Schwelle 90).",
        },
        {
          achse: "erkenntnislage",
          code: "abdeckung",
          punkte: 30,
          grund: "5 von 9 Kriterien bewertet.",
        },
      ],
      vermerke: [],
      unbekannte_codes: [],
    },
    over || {}
  );
}

const ZWECK =
  "BEARBEITUNGSDRINGLICHKEIT, KEINE BEWEISWUERDIGUNG. § 261 StPO ordnet die " +
  "freie Beweiswuerdigung dem Gericht zu.";

/** Eine vollstaendige Antwort von GET /api/matrix. */
function D(over) {
  return Object.assign(
    {
      stichtag: "2026-07-26",
      faelle_gesamt: 1,
      fristen_geladen: true,
      fristen_angefordert: true,
      fristen_kopf: {
        aussage_moeglich: true,
        verweigerungsgrund: null,
        params_bestaetigt: true,
      },
      faelle_ohne_fristzeile: 0,
      quadranten: { arbeitsreif: 1 },
      belastbarkeit_verteilung: { vorlaeufig: 1 },
      unbekannte_codes: {},
      fehlende_quellen: [],
      hinweise: ["Ein Hinweis des Backends."],
      dauer_gesamt_ms: 42,
      dauer_fristen_ms: 30,
      gewichte_stand: "2026-07-26",
      zweckbindung: ZWECK,
      vorbehalte: ["Ein Vorbehalt des Backends."],
      dringlichkeit_max: 90,
      frist_max: 40,
      erkenntnislage_max: 100,
      schwelle_dringlichkeit: 45.0,
      schwelle_erkenntnislage: 50.0,
      ausgeschlossene_kriterien: ["identification"],
      konfidenz_punkte: {},
      identitaet_punkte: {},
      ist_keine_beweiswuerdigung: true,
      schreibt_keine_prioritaet: true,
      zellen: [Z()],
    },
    over || {}
  );
}

function _render(data, opts) {
  const b = _both();
  const el = b.win.document.createElement("div");
  b.win.document.body.appendChild(el);
  const r = b.api.renderMatrix(el, data, Object.assign({ doc: b.win.document }, opts || {}));
  return { win: b.win, api: b.api, el: el, res: r };
}

describe("cockpit_matrix (Build 539)", () => {
  // MV01 ---------------------------------------------------------------------
  it("MV01: API-Oberflaeche vollstaendig", () => {
    const api = _api();
    [
      "QUADRANT", "BELASTBARKEIT", "GRUND", "BEITRAG_LABEL",
      "quadrantInfo", "quadrantIds", "belastbarkeitInfo", "belastbarkeitIds",
      "beitragLabel", "zweckbindungText", "zweckbindungOk", "prioritaetText",
      "prioritaetOk", "fristenText", "fristAnteilMax", "dringlichkeitText",
      "grundText", "erkenntnislageText", "beitraegeJeAchse", "summeBeitraege",
      "beitragStimmig", "quadrantenText", "belastbarkeitText", "massstabText",
      "quellenText", "codesText", "gruppen", "renderMatrix",
    ].forEach((k) => {
      expect(api[k], "fehlender Ausgang: " + k).toBeDefined();
    });
  });

  // MV02 ---------------------------------------------------------------------
  it("MV02: Zweckbindung ZEICHENGLEICH aus dem Backend, nicht neu formuliert", () => {
    const api = _api();
    expect(api.zweckbindungText(D())).toBe(ZWECK);

    // Und der Quelltext enthaelt die Zweckbindung NICHT als eigenen Satz:
    // saehe er sie, waere sie eine zweite Wahrheitsquelle.
    expect(_src.indexOf("BEARBEITUNGSDRINGLICHKEIT, KEINE")).toBe(-1);
  });

  // MV03 ---------------------------------------------------------------------
  it("MV03: fehlende Zweckbindung wird GEMELDET, nicht behauptet", () => {
    const api = _api();
    expect(api.zweckbindungOk(D())).toBe(true);
    expect(api.zweckbindungOk(D({ ist_keine_beweiswuerdigung: false }))).toBe(false);
    expect(api.zweckbindungOk(D({ zweckbindung: "" }))).toBe(false);
    expect(api.zweckbindungText(D({ zweckbindung: "" }))).toMatch(/ACHTUNG/);
    expect(api.zweckbindungText(D({ zweckbindung: "" }))).toMatch(/261/);

    const r = _render(D({ ist_keine_beweiswuerdigung: false }));
    const box = r.el.querySelector(".aiw-mx-zweck");
    expect(box.className).toMatch(/is-fehlt/);
  });

  // MV04 ---------------------------------------------------------------------
  it("MV04: fehlende Zusicherung 'schreibt keine Prioritaet' wird GEMELDET", () => {
    const api = _api();
    expect(api.prioritaetOk(D())).toBe(true);
    expect(api.prioritaetOk(D({ schreibt_keine_prioritaet: false }))).toBe(false);
    expect(api.prioritaetText(D({ schreibt_keine_prioritaet: false }))).toMatch(
      /ACHTUNG/
    );
    const r = _render(D({ schreibt_keine_prioritaet: false }));
    expect(r.el.querySelector(".aiw-mx-prio").className).toMatch(/is-fehlt/);
  });

  // MV05 ---------------------------------------------------------------------
  it("MV05: nicht bestimmbare Dringlichkeit zeigt 'mind. N', NIE eine 0", () => {
    const api = _api();
    const z = Z({
      dringlichkeit: null,
      dringlichkeit_bestimmbar: false,
      dringlichkeit_grund: "nicht_geladen",
      dringlichkeit_mindestens: 15,
      quadrant: "nicht_bestimmbar",
    });
    expect(api.dringlichkeitText(z)).toBe("mind. 15");
    expect(api.dringlichkeitText(z)).not.toBe("0");

    // Auch bei 0 Restpunkten steht 'mind. 0' und nicht '0' — der Unterschied
    // zwischen einer Untergrenze und einer Aussage bleibt sichtbar.
    expect(
      api.dringlichkeitText(
        Object.assign({}, z, { dringlichkeit_mindestens: 0 })
      )
    ).toBe("mind. 0");

    const r = _render(D({ zellen: [z], quadranten: { nicht_bestimmbar: 1 } }));
    const zelle = r.el.querySelector(".aiw-mx-x");
    expect(zelle.textContent).toBe("mind. 15");
    expect(zelle.className).toMatch(/is-unbestimmt/);
    expect(zelle.getAttribute("title")).toMatch(/nicht nachgesehen|NICHT geladen/);
  });

  // MV06 ---------------------------------------------------------------------
  it("MV06: die drei Fristzustaende haben DREI verschiedene Texte", () => {
    const api = _api();
    const nichtGeladen = api.fristenText(
      D({ fristen_geladen: false, fristen_kopf: null })
    );
    const ohneAussage = api.fristenText(
      D({
        fristen_geladen: true,
        fristen_kopf: {
          aussage_moeglich: false,
          verweigerungsgrund: "Parametersatz nicht bestaetigt.",
        },
      })
    );
    const gerechnet = api.fristenText(D());

    expect(nichtGeladen).toMatch(/NICHT geladen/);
    expect(nichtGeladen).toMatch(/UNTERGRENZE/);
    expect(ohneAussage).toMatch(/OHNE AUSSAGE/);
    expect(ohneAussage).toMatch(/Parametersatz nicht bestaetigt/);
    expect(gerechnet).toMatch(/geladen und gerechnet/);

    // Alle drei verschieden — das ist der Punkt.
    expect(new Set([nichtGeladen, ohneAussage, gerechnet]).size).toBe(3);
  });

  // MV07 ---------------------------------------------------------------------
  it("MV07: 'nicht_geladen' und 'keine_aussage' sehen VERSCHIEDEN aus", () => {
    const api = _api();
    const a = api.grundText(
      Z({ dringlichkeit_bestimmbar: false, dringlichkeit_grund: "nicht_geladen" })
    );
    const b = api.grundText(
      Z({ dringlichkeit_bestimmbar: false, dringlichkeit_grund: "keine_aussage" })
    );
    expect(a).not.toBe(b);
    expect(a).toMatch(/nicht nachgesehen/);
    expect(b).toMatch(/nachgesehen/);
    expect(b).toMatch(/VERWEIGERT/);

    // Bei bestimmbarer Dringlichkeit gibt es keinen Grund.
    expect(api.grundText(Z())).toBe(null);

    // Ein unbekannter Grund wird BENANNT und nicht verschwiegen.
    const u = api.grundText(
      Z({ dringlichkeit_bestimmbar: false, dringlichkeit_grund: "haltdiewelt" })
    );
    expect(u).toMatch(/haltdiewelt/);
    expect(u).toMatch(/nicht bekannt/);
  });

  // MV08 ---------------------------------------------------------------------
  it("MV08: Frontend-Quadranten decken genau QUADRANTEN des Backends", () => {
    const api = _api();
    const backend = backendListe("QUADRANTEN");
    expect(backend.length).toBeGreaterThan(3);
    expect(api.quadrantIds().slice().sort()).toEqual(backend.slice().sort());
  });

  // MV09 ---------------------------------------------------------------------
  it("MV09: Frontend-Belastbarkeiten decken genau BELASTBARKEITEN", () => {
    const api = _api();
    const backend = backendListe("BELASTBARKEITEN");
    expect(backend.length).toBe(3);
    expect(api.belastbarkeitIds().slice().sort()).toEqual(backend.slice().sort());
  });

  // MV10 ---------------------------------------------------------------------
  it("MV10: unbekannter Quadrant wird gekennzeichnet, nicht abgebildet", () => {
    const api = _api();
    const i = api.quadrantInfo("voellig_neu");
    expect(i.cls).toBe("is-unbekannt");
    expect(i.label).toMatch(/voellig_neu/);

    const r = _render(
      D({
        zellen: [Z({ quadrant: "voellig_neu" })],
        quadranten: { voellig_neu: 1 },
      })
    );
    const sec = r.el.querySelector(".aiw-mx-gruppe");
    expect(sec.className).toMatch(/is-unbekannt/);
    // Und in der Verteilung taucht er ebenfalls auf.
    expect(api.quadrantenText(D({ quadranten: { voellig_neu: 1 } }))).toMatch(
      /voellig_neu/
    );
  });

  // MV11 ---------------------------------------------------------------------
  it("MV11: 'nicht_bestimmbar' steht ZUERST, nicht am Ende", () => {
    const api = _api();
    const g = api.gruppen({
      zellen: [
        Z({ subject_id: 1, quadrant: "nachrangig" }),
        Z({ subject_id: 2, quadrant: "nicht_bestimmbar" }),
        Z({ subject_id: 3, quadrant: "gefaehrlich" }),
      ],
    });
    expect(g.map((x) => x.quadrant)).toEqual([
      "nicht_bestimmbar",
      "gefaehrlich",
      "nachrangig",
    ]);
  });

  // MV12 ---------------------------------------------------------------------
  it("MV12: innerhalb einer Gruppe bleibt die Reihenfolge des Backends", () => {
    const api = _api();
    const g = api.gruppen({
      zellen: [
        Z({ subject_id: 30, quadrant: "gefaehrlich" }),
        Z({ subject_id: 10, quadrant: "gefaehrlich" }),
        Z({ subject_id: 20, quadrant: "gefaehrlich" }),
      ],
    });
    expect(g[0].zellen.map((z) => z.subject_id)).toEqual([30, 10, 20]);
  });

  // MV13 ---------------------------------------------------------------------
  it("MV13: 'nicht_bestimmbar' und 'gefaehrlich' auch mit 0 genannt", () => {
    const api = _api();
    const t = api.quadrantenText({ quadranten: { nachrangig: 4 } });
    expect(t).toMatch(/NICHT BESTIMMBAR: 0/);
    expect(t).toMatch(/dünner Erkenntnislage: 0/);
    // Die uebrigen mit 0 werden weggelassen.
    expect(t).not.toMatch(/Arbeitsreif/);
  });

  // MV14 ---------------------------------------------------------------------
  it("MV14: die Begruendung steht in einem GESCHLOSSENEN <details>", () => {
    const r = _render(D());
    const det = r.el.querySelector(".aiw-mx-details");
    expect(det).toBeTruthy();
    expect(det.tagName.toLowerCase()).toBe("details");
    expect(det.hasAttribute("open")).toBe(false);
    // Der Summary nennt die Zahl der Beitraege (3 + 1).
    expect(det.querySelector("summary").textContent).toMatch(/Begründung \(4\)/);
    // Und die Begruendungstexte des Backends stehen darin.
    expect(det.textContent).toMatch(/Restlaufzeit 311 Tage/);
  });

  // MV15 ---------------------------------------------------------------------
  it("MV15: Beitragssumme wird nachgerechnet; Abweichung wird SICHTBAR", () => {
    const api = _api();
    expect(api.beitragStimmig(Z())).toBe(true);

    // Eine Zelle, deren Wert nicht zu ihren Beitraegen passt.
    const kaputt = Z({ dringlichkeit: 99 });
    expect(api.beitragStimmig(kaputt)).toBe(false);
    const r = _render(D({ zellen: [kaputt] }));
    const zelle = r.el.querySelector(".aiw-mx-x");
    expect(zelle.className).toMatch(/is-unstimmig/);
    expect(zelle.getAttribute("title")).toMatch(/WARNUNG/);

    // Bei UNBESTIMMBARER Dringlichkeit wird gegen 'mindestens' geprueft.
    const unb = Z({
      dringlichkeit: null,
      dringlichkeit_bestimmbar: false,
      dringlichkeit_mindestens: 15,
      beitraege: [
        { achse: "dringlichkeit", code: "unzugewiesen", punkte: 10, grund: "x" },
        { achse: "dringlichkeit", code: "liegezeit", punkte: 5, grund: "y" },
      ],
    });
    expect(api.beitragStimmig(unb)).toBe(true);
  });

  // MV16 ---------------------------------------------------------------------
  it("MV16: Vermerke des Backends erscheinen WORTGLEICH", () => {
    const satz =
      "Der Fristablauf ist nach der UNUNTERBROCHENEN Frist rechnerisch " +
      "ueberschritten — juristische Pruefung erforderlich (§ 78c StGB ist " +
      "diesem Werkzeug nicht bekannt).";
    const r = _render(D({ zellen: [Z({ vermerke: [satz] })] }));
    const li = r.el.querySelectorAll(".aiw-mx-vermerke li");
    expect(li.length).toBe(1);
    expect(li[0].textContent).toBe(satz);
  });

  // MV17 ---------------------------------------------------------------------
  it("MV17: der Massstab steht IMMER da, auch beim Leerbefund", () => {
    const api = _api();
    const t = api.massstabText(D());
    expect(t).toMatch(/Stichtag: 2026-07-26/);
    expect(t).toMatch(/Gewichtungssatz: Stand 2026-07-26/);
    expect(t).toMatch(/Dringlichkeit 90/);
    expect(t).toMatch(/identification/);
    expect(t).toMatch(/42 ms/);
    expect(t).toMatch(/davon Fristen 30 ms/);

    // Ohne Fristanteil wird das AUSDRUECKLICH gesagt und keine 0 gezeigt.
    expect(api.massstabText(D({ dauer_fristen_ms: null }))).toMatch(
      /ohne Fristanteil/
    );

    const leer = _render(D({ zellen: [], faelle_gesamt: 0, quadranten: {} }));
    expect(leer.el.querySelector(".aiw-mx-foot")).toBeTruthy();
    expect(leer.el.querySelector(".aiw-mx-leer").textContent).toMatch(
      /Leerbefund über die FALLLISTE/
    );
    expect(leer.res.state).toBe("leer");
  });

  // MV18 ---------------------------------------------------------------------
  it("MV18: ausgefallene Quellen stehen VOR den Gruppen und nennen die Richtung", () => {
    const api = _api();
    expect(api.quellenText(D())).toBe(null);

    const data = D({ fehlende_quellen: ["Fristen (Datei kaputt)"] });
    expect(api.quellenText(data)).toMatch(/harmloser aussehen, als er ist/);

    const r = _render(data);
    const kinder = Array.prototype.slice.call(r.el.children);
    const iQuelle = kinder.findIndex((k) =>
      k.className && k.className.indexOf("aiw-mx-quellen") >= 0
    );
    const iGruppe = kinder.findIndex((k) =>
      k.className && k.className.indexOf("aiw-mx-gruppe") >= 0
    );
    expect(iQuelle).toBeGreaterThan(-1);
    expect(iGruppe).toBeGreaterThan(-1);
    expect(iQuelle).toBeLessThan(iGruppe);

    // Ohne Ausfall erscheint der Bereich NICHT.
    expect(_render(D()).el.querySelector(".aiw-mx-quellen")).toBe(null);
  });

  // MV19 ---------------------------------------------------------------------
  it("MV19: unbekannte Konfidenz-Codes werden benannt (fachliche Entscheidung)", () => {
    const api = _api();
    expect(api.codesText(D())).toBe(null);
    const t = api.codesText(D({ unbekannte_codes: { neuer_code: 3 } }));
    expect(t).toMatch(/neuer_code \(3×\)/);
    expect(t).toMatch(/NICHT mit 0/);
    expect(t).toMatch(/fachliche Entscheidung/);
    expect(
      _render(D({ unbekannte_codes: { neuer_code: 3 } })).el.querySelector(
        ".aiw-mx-codes"
      )
    ).toBeTruthy();
  });

  // MV20 ---------------------------------------------------------------------
  it("MV20: Fehlerzustand ist ausdruecklich KEIN Leerbefund", () => {
    const r = _render({ error: "500 matrix_failed" });
    expect(r.res.state).toBe("error");
    expect(r.el.textContent).toMatch(/KEIN Leerbefund/);
    expect(r.el.textContent).toMatch(/500 matrix_failed/);
    // Keine Tabelle, kein Quadrant.
    expect(r.el.querySelector(".aiw-mx-table")).toBe(null);
  });

  // MV21 ---------------------------------------------------------------------
  it("MV21: der Fristen-Schalter erscheint nur mit wirkendem Rueckruf", () => {
    // Ohne Rueckruf: kein Knopf. Ein Bedienelement ohne Wirkung waere
    // schlimmer als keines.
    expect(_render(D()).el.querySelector(".aiw-mx-schalter")).toBe(null);

    const gesehen = [];
    const r = _render(D({ fristen_geladen: false, fristen_kopf: null }), {
      onFristen: function (v) {
        gesehen.push(v);
      },
    });
    const knoepfe = r.el.querySelectorAll(".aiw-mx-schalter");
    expect(knoepfe.length).toBe(2);
    // Der aktive Knopf spiegelt den TATSAECHLICHEN Zustand.
    expect(knoepfe[1].className).toMatch(/is-active/);
    expect(knoepfe[0].className).not.toMatch(/is-active/);

    knoepfe[0].dispatchEvent(new r.win.Event("click"));
    knoepfe[1].dispatchEvent(new r.win.Event("click"));
    expect(gesehen).toEqual([true, false]);

    // Es ist der EINZIGE Knopf der Sicht (die <summary> sind keine Buttons).
    expect(r.el.querySelectorAll("button").length).toBe(2);
  });

  // MV22 ---------------------------------------------------------------------
  it("MV22: Kontonamen bleiben Text; UTF-8 bleibt erhalten", () => {
    const name = "<img src=x onerror=alert(1)> Ünïcødé ✓ Ω 日本語";
    const r = _render(D({ zellen: [Z({ username: name })] }));
    const td = r.el.querySelector(".aiw-mx-case");
    expect(td.textContent).toContain(name);
    expect(td.querySelector("img")).toBe(null);
    // Der Nachweis ist die MASKIERUNG, nicht die Abwesenheit der Zeichenfolge:
    // textContent laesst '<' zu '&lt;' werden, der Rest des Namens bleibt als
    // TEXT stehen (und muss das auch — es ist ein Kontoname aus einem
    // beschlagnahmten Forum und damit ein Beweismittel, das nicht beschnitten
    // werden darf).
    expect(r.el.innerHTML).not.toContain("<img");
    expect(r.el.innerHTML).toContain("&lt;img");
  });

  // MV23 ---------------------------------------------------------------------
  it("MV23: die Bezugsgroesse der Y-Achse steht IN der Zeile", () => {
    const api = _api();
    const r = _render(D());
    expect(r.el.querySelector(".aiw-mx-krit").textContent).toBe("von 9");
    // Fehlt sie, wird '—' gezeigt und keine Zahl erfunden.
    const ohne = _render(D({ zellen: [Z({ n_kriterien_matrix: null })] }));
    expect(ohne.el.querySelector(".aiw-mx-krit").textContent).toBe("—");
    // Und eine nicht bestimmbare Erkenntnislage wird benannt.
    expect(
      api.erkenntnislageText(
        Z({ erkenntnislage: null, erkenntnislage_bestimmbar: false })
      )
    ).toBe("nicht bestimmbar");
  });

  // MV24 ---------------------------------------------------------------------
  it("MV24: fehlende Vorbehalte sind ein gemeldeter Verdachtsmoment", () => {
    const mit = _render(D());
    expect(mit.el.querySelector(".aiw-mx-vorbehalte")).toBeTruthy();
    expect(mit.el.querySelector(".aiw-mx-vorbehalte").textContent).toMatch(
      /Ein Vorbehalt des Backends/
    );

    const ohne = _render(D({ vorbehalte: [], hinweise: [] }));
    expect(ohne.el.querySelector(".aiw-mx-vorbehalte")).toBe(null);
    expect(ohne.el.textContent).toMatch(/enthält KEINE Vorbehalte/);
  });

  // MV25 ---------------------------------------------------------------------
  it("MV25: der Fristanteil wird nicht geraten", () => {
    const api = _api();
    expect(api.fristAnteilMax(D())).toBe("40");
    expect(api.fristAnteilMax(D({ frist_max: null }))).toBe("?");
    // Und im Satz taucht er auf, statt dass eine Zahl erfunden wird.
    expect(
      api.fristenText(D({ fristen_geladen: false, fristen_kopf: null }))
    ).toMatch(/bis zu 40 der 90 möglichen Punkte/);
  });
});
