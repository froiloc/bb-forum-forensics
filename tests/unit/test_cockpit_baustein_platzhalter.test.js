/**
 * tests/unit/test_cockpit_baustein_platzhalter.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Baustein-Module (W1) — PLATZHALTER-TABELLE, Build 654 (Ticket 4b032177)
 *
 * Testsuite fuer management/server/static/cockpit_baustein_platzhalter.js.
 * Getestet wird der ECHTE Code (readFileSync + JSDOM), und zwar ZUSAMMEN mit
 * seinen beiden echten Quellen: userinfo/placeholder_chips.js (Zerlegung) und
 * management/server/static/cockpit_templates.js (Regelpruefung). Gegen
 * Nachbauten zu pruefen hiesse, die Doppelwahrheit zu pruefen, die dieser
 * Bauteil gerade vermeiden soll.
 *
 * PT01 — katalogIndex: Liste -> Index, beide Antwortformen.
 * PT02 — musterAus: die BEIDEN Formen des fuenften Feldes (rule: / Base64).
 * PT03 — verdaechtige: Token, die keine Platzhalter sind (V1).
 * PT04 — zerlege: Verdichtung je (Typ, Name), Vorkommen, Varianten.
 * PT05 — pruefe V2: a-Platzhalter unbekannt / abgeschaltet / falscher Typ.
 * PT06 — pruefe V3: m/o-Typ weicht vom Katalog ab.
 * PT07 — pruefe V4: unbrauchbares Pruefmuster.
 * PT08 — pruefe V5/V6: Abweichung vom Katalog, Mehrfachvergabe.
 * PT09 — teste: Eingabe gegen BEIDE Regeln, samt Abweichung.
 * PT10 — erzeuge: die Tabelle im DOM, leerer Text, fehlende Kataloge.
 *
 * Build 681 (Vorgang 7c1f2a94), das Zurueckschreiben:
 * PT11 — ohne Rueckruf bleibt die Tabelle ANZEIGE. Kein Eingabefeld, das
 *        nirgends ankommt.
 * PT12 — mit Rueckruf: vier beschreibbare Felder, der NAME nicht. Die
 *        Aenderung geht bei 'change' hinaus, nicht bei 'input' (F3).
 * PT13 — F1: ein Trennzeichen wird abgewiesen, das Feld faellt zurueck, der
 *        Grund steht an der Zelle - und der Rueckruf wird NICHT gerufen.
 * PT14 — F2: Mehrfachvorkommen. Die dauerhafte Anzeige steht da, die
 *        Rueckfrage kommt, und ein Nein aendert nichts.
 *
 * Build 683 (Vorgang 5a7d4e21), die Lesequelle:
 * PT15 — zerlegeBlock: alle Textstellen eines Blocks in EINEN Bestand, der
 *        Verdacht aber je Textstelle.
 * PT16 — zeigeBlock im DOM, mit der GEGENPROBE gegen den Klartextspiegel und
 *        dem benannten Rueckfall.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _chips = readFileSync("userinfo/placeholder_chips.js", "utf-8");
const _tpl = readFileSync(
  "management/server/static/cockpit_templates.js", "utf-8");
const _src = readFileSync(
  "management/server/static/cockpit_baustein_platzhalter.js", "utf-8");

function _ctx() {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body><div id='host'></div></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  // FORENSIC_DEBUG aus: placeholder_chips.js loggt sonst bei jedem Aufbau.
  dom.window.FORENSIC_DEBUG = false;
  dom.window.eval(_chips);
  dom.window.eval(_tpl);
  dom.window.eval(_src);
  return dom.window;
}
function _api(win) { return (win || _ctx()).AIWBausteinPlatzhalter; }

// Der Regelkatalog aus config.yaml (validation.rules) — der echte Eintrag.
const REGELN = {
  spurennummer: {
    pattern: "^(AIW|R3X|FBL|AMZ|BRU)\\d+$",
    transform: "upper",
    hint: "Behoerdenkuerzel gefolgt von Ziffern",
  },
};

const KATALOG_ROH = [
  { id: "username", type: "a", is_active: 1, title: "Benutzername",
    sql_query: "SELECT 1", validation: null, validation_type: null },
  { id: "spurennummer", type: "m", is_active: 1, title: "Spurennummer",
    validation: "^AIW\\d+$", validation_type: "regex", validation_ci: 0 },
  { id: "abgeschaltet", type: "a", is_active: 0, title: "Alt",
    sql_query: "SELECT 1" },
  { id: "kategorie", type: "m", is_active: 1, title: "Kategorie",
    validation: '["rot","gelb"]', validation_type: "list", validation_ci: 1 },
];

// Base64 einer Regex — so, wie es die Altform im fuenften Feld tut.
const B64_ZIFFERN = Buffer.from("^\\d+$", "utf-8").toString("base64");

describe("cockpit_baustein_platzhalter — reine Funktionen (Build 654)", () => {
  // PT01 ---------------------------------------------------------------
  it("PT01: katalogIndex nimmt beide Antwortformen", () => {
    const api = _api();
    const a = api.katalogIndex(KATALOG_ROH);
    const b = api.katalogIndex({ count: 4, placeholders: KATALOG_ROH });
    expect(Object.keys(a).sort()).toEqual(Object.keys(b).sort());
    expect(a.spurennummer.validation_type).toBe("regex");
    // ALLE Typen, nicht nur m/o: die Existenz eines a-Platzhalters ist
    // gerade das, was hier geprueft werden soll.
    expect(a.username.type).toBe("a");
    // Unbrauchbare Eintraege werden uebergangen, nicht eingebaut.
    expect(Object.keys(api.katalogIndex([null, {}, { id: null }]))).toEqual([]);
    expect(Object.keys(api.katalogIndex(undefined))).toEqual([]);
  });

  // PT02 ---------------------------------------------------------------
  it("PT02: musterAus kennt BEIDE Formen des fuenften Feldes", () => {
    const api = _api();

    // Kein Feld ist kein Fehler.
    expect(api.musterAus("", REGELN)).toEqual({
      form: "", muster: null, quelle: "", hinweis: "", fehler: null });

    // Neue Form: Verweis in den Katalog aus config.yaml (seit Build 388).
    const r = api.musterAus("rule:spurennummer", REGELN);
    expect(r.form).toBe("regel");
    expect(r.muster).toBe(REGELN.spurennummer.pattern);
    expect(r.quelle).toBe("spurennummer");
    expect(r.hinweis).toContain("Behoerdenkuerzel");
    expect(r.fehler).toBe(null);

    // Verweis ins Leere — GRUNDREGEL 1: nicht still durchwinken.
    const tot = api.musterAus("rule:gibtesnicht", REGELN);
    expect(tot.muster).toBe(null);
    expect(tot.fehler).toContain("gibtesnicht");
    expect(tot.fehler).toContain("validation.rules");

    // Altform: Base64 (OP-B6-5). SIE MUSS WEITER GEHEN — im Bestand stehen
    // beide Formen nebeneinander, und ein Fehlalarm auf der Mehrzahl der
    // Eintraege machte die ganze Tabelle wertlos.
    const b = api.musterAus(B64_ZIFFERN, REGELN);
    expect(b.form).toBe("base64");
    expect(b.muster).toBe("^\\d+$");
    expect(b.fehler).toBe(null);

    // Weder das eine noch das andere.
    const kaputt = api.musterAus("!!!kein base64!!!", REGELN);
    expect(kaputt.muster).toBe(null);
    expect(kaputt.fehler).toContain("weder ein Verweis");

    // UTF-8 ueberlebt: das Forum ist multilingual, und atob allein wuerde
    // Mehrbyte-Zeichen zerlegen.
    const umlaut = Buffer.from("^[äöüß]+$", "utf-8").toString("base64");
    expect(api.musterAus(umlaut, REGELN).muster).toBe("^[äöüß]+$");
  });

  // PT03 ---------------------------------------------------------------
  it("PT03: verdaechtige findet, was wie ein Platzhalter aussieht (V1)", () => {
    const api = _api();
    const win = _ctx();
    const text = "gut {{m:name}} — schlecht {{m:na me}} {{x:foo}} {{ohnetyp}} "
      + "{{m:a|1|2|3|4}}";
    const z = api.zerlege(text, win.PlaceholderChips);

    // Der gueltige faellt NICHT in den Verdacht.
    const rohe = z.verdaechtige.map((v) => v.roh);
    expect(rohe).not.toContain("{{m:name}}");

    expect(rohe).toContain("{{m:na me}}");
    expect(rohe).toContain("{{x:foo}}");
    expect(rohe).toContain("{{ohnetyp}}");
    expect(rohe).toContain("{{m:a|1|2|3|4}}");

    // Und JEDER bekommt einen Grund im Klartext, keine blosse Markierung.
    const grund = (roh) => z.verdaechtige.find((v) => v.roh === roh).grund;
    expect(grund("{{x:foo}}")).toContain("Typkuerzel");
    expect(grund("{{ohnetyp}}")).toContain("Doppelpunkt");
    expect(grund("{{m:a|1|2|3|4}}")).toContain("Zu viele");
    expect(grund("{{m:na me}}")).toContain("unzulaessige Zeichen");

    // Sauberer Text ergibt keinen Verdacht — sonst waere die Meldung Lärm.
    expect(api.zerlege("nur {{a:x}} und Text", win.PlaceholderChips)
      .verdaechtige).toEqual([]);
  });

  // PT04 ---------------------------------------------------------------
  it("PT04: zerlege verdichtet je Typ und Name", () => {
    const win = _ctx();
    const api = _api(win);
    const z = api.zerlege(
      "{{a:u}} und {{m:s|A|Erste}} und nochmal {{m:s|B|Zweite}} und {{m:s|A|Erste}}",
      win.PlaceholderChips);

    expect(z.eintraege.map((e) => e.typ + ":" + e.name))
      .toEqual(["a:u", "m:s"]);
    const s = z.eintraege[1];
    expect(s.vorkommen).toBe(3);
    // DREI Vorkommen, aber nur ZWEI verschiedene Auspraegungen — das ist
    // der Unterschied, aus dem V6 entsteht.
    expect(s.varianten.length).toBe(2);
    expect(s.rohtoken.length).toBe(3);
    // Die erste Auspraegung fuehrt die Zeile.
    expect(s.vorgabe).toBe("A");
    expect(s.beschreibung).toBe("Erste");

    // Ohne Zerlegewerkzeug wird NICHT geraten, sondern null geliefert.
    // Der zweite Parameter ist nur die EINSPEISUNG fuer die Pruefung; fehlt
    // er, greift window.PlaceholderChips (Hausmuster). Der Ausfall tritt
    // also erst ein, wenn es auch das nicht gibt - und genau so wird es
    // hier gemessen, statt sich auf ein uebergebenes null zu verlassen.
    const leer = _ctx();
    delete leer.PlaceholderChips;
    expect(leer.AIWBausteinPlatzhalter.zerlege("{{a:x}}", null)).toBe(null);
    expect(api.zerlege("{{a:x}}", null)).not.toBe(null);   // Rueckfall greift
    expect(api.zerlege("", win.PlaceholderChips).eintraege).toEqual([]);
  });

  // PT05 ---------------------------------------------------------------
  it("PT05: V2 — a-Platzhalter gegen den Katalog", () => {
    const win = _ctx();
    const api = _api(win);
    const kat = api.katalogIndex(KATALOG_ROH);
    const eins = (t) => api.zerlege(t, win.PlaceholderChips).eintraege[0];

    // Bekannt, aktiv, richtiger Typ -> keine Beanstandung.
    expect(api.pruefe(eins("{{a:username}}"), kat, REGELN).stufe).toBe("ok");

    // Unbekannt.
    const unbekannt = api.pruefe(eins("{{a:gibtsnicht}}"), kat, REGELN);
    expect(unbekannt.stufe).toBe("fehler");
    expect(unbekannt.befunde[0].kennung).toBe("V2");
    expect(unbekannt.befunde[0].text).toContain("bleibt im Vermerk leer");

    // Abgeschaltet.
    const aus = api.pruefe(eins("{{a:abgeschaltet}}"), kat, REGELN);
    expect(aus.stufe).toBe("fehler");
    expect(aus.befunde.some((b) => b.text.includes("abgeschaltet"))).toBe(true);

    // Im Katalog ist 'spurennummer' ein Eingabefeld, nicht automatisch.
    const falsch = api.pruefe(eins("{{a:spurennummer}}"), kat, REGELN);
    expect(falsch.stufe).toBe("fehler");
    expect(falsch.befunde[0].text).toContain("verpflichtend");
  });

  // PT06 ---------------------------------------------------------------
  it("PT06: V3 — m/o weicht vom Katalogtyp ab", () => {
    const win = _ctx();
    const api = _api(win);
    const kat = api.katalogIndex(KATALOG_ROH);
    const eins = (t) => api.zerlege(t, win.PlaceholderChips).eintraege[0];

    // {{o:...}} auf einem Pflichtfeld: kein Fehler, aber meldepflichtig —
    // beim Ausfuellen entscheidet der Katalog.
    const o = api.pruefe(eins("{{o:spurennummer}}"), kat, REGELN);
    expect(o.stufe).toBe("hinweis");
    expect(o.befunde[0].kennung).toBe("V3");
    expect(o.befunde[0].text).toContain("entscheidet der Katalog");

    // {{m:...}} auf einem AUTOMATISCHEN Platzhalter ist ein Fehler: der
    // Wert wird abgefragt, nicht eingegeben.
    const m = api.pruefe(eins("{{m:username}}"), kat, REGELN);
    expect(m.stufe).toBe("fehler");
    expect(m.befunde[0].kennung).toBe("V3");

    // Ein Name, den der Katalog gar nicht kennt, ist bei m/o KEIN Fehler —
    // die Regel darf am Token stehen. Sonst waere jeder freie Platzhalter
    // ein Alarm, und die Tabelle bestuende aus Fehlalarmen.
    expect(api.pruefe(eins("{{m:freitext}}"), kat, REGELN).stufe).toBe("ok");
  });

  // PT07 ---------------------------------------------------------------
  it("PT07: V4 — unbrauchbares Pruefmuster", () => {
    const win = _ctx();
    const api = _api(win);
    const kat = api.katalogIndex(KATALOG_ROH);
    const eins = (t) => api.zerlege(t, win.PlaceholderChips).eintraege[0];

    const tot = api.pruefe(eins("{{m:x|||rule:gibtesnicht}}"), kat, REGELN);
    expect(tot.stufe).toBe("fehler");
    expect(tot.befunde[0].kennung).toBe("V4");

    // Gueltiges Base64, aber keine uebersetzbare Regex.
    const kaputteRe = Buffer.from("^[a-", "utf-8").toString("base64");
    const re = api.pruefe(eins("{{m:y|||" + kaputteRe + "}}"), kat, REGELN);
    expect(re.stufe).toBe("fehler");
    expect(re.befunde[0].text).toContain("nicht uebersetzen");

    // Eine brauchbare Regel schlaegt NICHT an.
    expect(api.pruefe(eins("{{m:z|||rule:spurennummer}}"), kat, REGELN).stufe)
      .toBe("ok");
  });

  // PT08 ---------------------------------------------------------------
  it("PT08: V5 und V6 — Abweichung vom Katalog, Mehrfachvergabe", () => {
    const win = _ctx();
    const api = _api(win);
    const kat = api.katalogIndex(KATALOG_ROH);

    // V5: Token traegt rule:spurennummer (fuenf Kuerzel), der Katalog nur
    // ^AIW\d+$. Kein Fehler — aber beim Ausfuellen gilt der Katalog.
    const v5 = api.pruefe(
      api.zerlege("{{m:spurennummer|||rule:spurennummer}}",
                  win.PlaceholderChips).eintraege[0], kat, REGELN);
    expect(v5.stufe).toBe("hinweis");
    expect(v5.befunde[0].kennung).toBe("V5");
    expect(v5.befunde[0].text).toContain("gilt der Katalog");

    // V6: derselbe Name, verschiedene Angaben.
    const v6 = api.pruefe(
      api.zerlege("{{m:frei|A}} … {{m:frei|B}}",
                  win.PlaceholderChips).eintraege[0], kat, REGELN);
    expect(v6.stufe).toBe("fehler");
    expect(v6.befunde[0].kennung).toBe("V6");
    expect(v6.befunde[0].text).toContain("2-mal");

    // Zweimal DASSELBE ist kein Befund — Wiederholung allein ist erlaubt.
    expect(api.pruefe(
      api.zerlege("{{m:frei|A}} … {{m:frei|A}}",
                  win.PlaceholderChips).eintraege[0], kat, REGELN).stufe)
      .toBe("ok");
  });

  // PT09 ---------------------------------------------------------------
  it("PT09: teste prueft gegen BEIDE Regeln und meldet die Abweichung", () => {
    const win = _ctx();
    const api = _api(win);
    const kat = api.katalogIndex(KATALOG_ROH);
    const tpl = win.AIWCockpitTemplates;
    const e = api.zerlege("{{m:spurennummer|||rule:spurennummer}}",
                          win.PlaceholderChips).eintraege[0];

    // Beide sagen ja.
    const ja = api.teste(e, kat, REGELN, "AIW123", tpl);
    expect(ja.chip.passt).toBe(true);
    expect(ja.katalog.passt).toBe(true);
    expect(ja.chip.quelle).toContain("spurennummer");

    // DER FALL, DER HEUTE UNSICHTBAR IST: der Verweis erlaubt BRU, der
    // Katalogeintrag nicht. Beide Urteile stehen einzeln da.
    const geteilt = api.teste(e, kat, REGELN, "BRU9", tpl);
    expect(geteilt.chip.passt).toBe(true);
    expect(geteilt.katalog.passt).toBe(false);

    // Beide sagen nein.
    const nein = api.teste(e, kat, REGELN, "XYZ", tpl);
    expect(nein.chip.passt).toBe(false);
    expect(nein.katalog.passt).toBe(false);

    // Listenpruefung mit Gross-/Kleinschreibung (validation_ci, Build 497)
    // — sie laeuft ueber testRule und wird hier NICHT nachgebaut.
    const k = api.zerlege("{{m:kategorie}}", win.PlaceholderChips).eintraege[0];
    expect(api.teste(k, kat, REGELN, "ROT", tpl).katalog.passt).toBe(true);
    expect(api.teste(k, kat, REGELN, "blau", tpl).katalog.passt).toBe(false);

    // Ein a-Platzhalter wird nicht eingegeben — also auch nicht getestet.
    const a = api.zerlege("{{a:username}}", win.PlaceholderChips).eintraege[0];
    expect(api.teste(a, kat, REGELN, "egal", tpl))
      .toEqual({ chip: null, katalog: null });

    // Ohne Pruefwerkzeug wird das GESAGT, nicht stillschweigend ausgelassen.
    // Wie oben: der Parameter ist die Einspeisung, der Rueckfall ist
    // window.AIWCockpitTemplates. Fehlt auch das, muss die Zelle sprechen.
    const ohneWin = _ctx();
    delete ohneWin.AIWCockpitTemplates;
    const apiO = ohneWin.AIWBausteinPlatzhalter;
    const ohne = apiO.teste(
      apiO.zerlege("{{m:spurennummer}}", ohneWin.PlaceholderChips).eintraege[0],
      apiO.katalogIndex(KATALOG_ROH), REGELN, "AIW1", null);
    expect(ohne.katalog.geprueft).toBe(false);
    expect(ohne.katalog.fehler).toContain("cockpit_templates.js");
  });
});

describe("cockpit_baustein_platzhalter — die Tabelle (Build 654)", () => {
  // PT10 ---------------------------------------------------------------
  it("PT10: erzeuge baut die Tabelle, zaehlt und warnt", () => {
    const win = _ctx();
    const api = _api(win);
    const host = win.document.getElementById("host");
    const kat = api.katalogIndex(KATALOG_ROH);
    const t = api.erzeuge(host, { tpl: win.AIWCockpitTemplates,
                                  chips: win.PlaceholderChips });

    // (a) leerer Text: eine Aussage, keine leere Flaeche.
    t.zeige("", kat, REGELN);
    expect(host.querySelector(".aiw-mod-ph-meldung").textContent)
      .toBe("Keine Platzhalter im Bausteintext.");
    expect(host.querySelector(".aiw-mod-ph-tabelle")).toBe(null);

    // (b) echter Text.
    t.zeige("Hallo {{a:username}}, Spur {{m:spurennummer|||rule:spurennummer}} "
      + "und {{a:gibtsnicht}} sowie {{q:kaputt}}", kat, REGELN);

    const zeilen = host.querySelectorAll(".aiw-mod-ph-tabelle tbody tr");
    expect(Array.prototype.map.call(zeilen,
      (r) => r.getAttribute("data-name")))
      .toEqual(["a:username", "m:spurennummer", "a:gibtsnicht"]);
    expect(zeilen[0].className).toBe("ist-ok");
    expect(zeilen[1].className).toBe("ist-hinweis");
    expect(zeilen[2].className).toBe("ist-fehler");

    // Acht Spalten, wie im Ticket verlangt ("alle Parameter", plus
    // Verifikation und Testeingabe).
    expect(host.querySelectorAll(".aiw-mod-ph-tabelle thead th").length)
      .toBe(8);

    // Das Pruefmuster steht DEKODIERT da — Base64 hilft beim Nachsehen nicht.
    expect(zeilen[1].querySelector(".aiw-mod-ph-muster").textContent)
      .toContain(REGELN.spurennummer.pattern);

    // Der verdaechtige Token steht AUSSERHALB der Tabelle: er ist gerade
    // kein Platzhalter. Er verschwindet aber nicht.
    expect(host.querySelector(".aiw-mod-ph-verdacht").textContent)
      .toContain("{{q:kaputt}}");

    // DIE ZAHL STEHT IMMER DA, mit dem Substantiv dieser Sicht.
    const meldung = host.querySelector(".aiw-mod-ph-meldung").textContent;
    expect(meldung).toContain("3 Platzhalter");
    expect(meldung).toContain("1 mit Fehler");
    expect(meldung).toContain("1 mit Hinweis");

    // (c) Testeingabe: nur fuer m/o, und sie urteilt zweifach.
    const felder = host.querySelectorAll(".aiw-mod-ph-eingabe");
    expect(felder.length).toBe(1);      // nur die m-Zeile
    felder[0].value = "BRU9";
    felder[0].dispatchEvent(new win.Event("input"));
    const urteil = zeilen[1].querySelector(".aiw-mod-ph-urteil").textContent;
    expect(urteil).toContain("passt — Formatregel");
    expect(urteil).toContain("passt NICHT — Katalog");
    expect(urteil).toContain("urteilen VERSCHIEDEN");

    // (d) ohne Katalog wird geurteilt, aber es wird auch gesagt.
    const win2 = _ctx();
    const api2 = _api(win2);
    const host2 = win2.document.getElementById("host");
    api2.erzeuge(host2, { tpl: win2.AIWCockpitTemplates,
                          chips: win2.PlaceholderChips })
        .zeige("{{a:username}}", null, null);
    expect(host2.querySelector(".aiw-mod-ph-meldung").textContent)
      .toContain("Katalog ist NICHT geladen");
    expect(host2.querySelectorAll(".aiw-mod-ph-tabelle tbody tr").length)
      .toBe(1);

    // (e) aus() raeumt auf.
    t.aus();
    expect(host.querySelector(".aiw-mod-ph-tabelle")).toBe(null);
    expect(host.querySelector(".aiw-mod-ph-meldung").textContent).toBe("");
  });
});

// ===========================================================================
// BUILD 681 (Vorgang 7c1f2a94): DAS ZURUECKSCHREIBEN
// ===========================================================================
// Geprueft wird die BEDIENUNG. Was beim Zurueckschreiben gerechnet wird,
// prueft test_cockpit_baustein_ph_schreiben.test.js - hier geht es darum, ob
// die Tabelle das Richtige RUFT und das Falsche NICHT.

const _schr = readFileSync(
  "management/server/static/cockpit_baustein_ph_schreiben.js", "utf-8");

/** Fenster MIT dem Rechenwerk zum Zurueckschreiben. */
function _ctxS() {
  const win = _ctx();
  win.eval(_schr);
  return win;
}

/**
 * Baut eine Tabelle mit Rueckruf und gibt alles zurueck, was die Pruefung
 * braucht. 'rufe' sammelt jeden Auftrag - eine Behauptung "es wurde
 * geschrieben" ist damit belegbar und nicht nur plausibel.
 */
function _mitSchreiben(text, opts) {
  opts = opts || {};
  const win = _ctxS();
  const host = win.document.getElementById("host");
  const rufe = [];
  const t = _api(win).erzeuge(host, {
    tpl: win.AIWCockpitTemplates,
    chips: win.PlaceholderChips,
    schr: win.AIWBausteinPhSchreiben,
    frage: opts.frage || (() => true),
    schreibe: (auftrag) => {
      rufe.push(auftrag);
      return opts.antwort || { ok: true, meldung: "Ein Vorkommen geändert." };
    },
  });
  t.zeige(text, {}, REGELN);
  return { win, host, rufe, t };
}

function _feld(host, schluessel, welches) {
  const trs = host.querySelectorAll(".aiw-mod-ph-tabelle tbody tr");
  for (const tr of trs) {
    if (tr.getAttribute("data-name") === schluessel) {
      return tr.querySelector('[data-feld-eingabe="' + welches + '"]');
    }
  }
  return null;
}
function _meldung(host, schluessel, welches) {
  const trs = host.querySelectorAll(".aiw-mod-ph-tabelle tbody tr");
  for (const tr of trs) {
    if (tr.getAttribute("data-name") === schluessel) {
      return tr.querySelector('[data-feld="' + welches + '"]');
    }
  }
  return null;
}

describe("PT11 ohne Rueckruf bleibt die Tabelle Anzeige", () => {
  it("baut kein einziges beschreibbares Feld", () => {
    const win = _ctxS();
    const host = win.document.getElementById("host");
    // KEIN opts.schreibe - der Stand von Build 654.
    _api(win).erzeuge(host, { tpl: win.AIWCockpitTemplates,
                              chips: win.PlaceholderChips })
             .zeige("{{m:x|v}}", {}, {});
    expect(host.querySelectorAll(".aiw-mod-ph-schreibfeld").length).toBe(0);
    // Und sie sagt es, statt es den Redakteur ausprobieren zu lassen.
    expect(host.querySelector(".aiw-mod-ph-meldung").textContent)
      .toContain("schreibt nicht");
  });
});

describe("PT12 mit Rueckruf: vier Felder, und 'change' statt 'input'", () => {
  it("macht Art, Vorgabe, Beschreibung und Prüfmuster beschreibbar", () => {
    const { host } = _mitSchreiben("{{m:x|v|b|rule:spurennummer}}");
    ["typ", "vorgabe", "beschreibung", "regelfeld"].forEach((w) => {
      expect(_feld(host, "m:x", w)).not.toBe(null);
    });
    // Der NAME ist KEIN Eingabefeld (Entscheidung mc): er ist die Identitaet
    // des Platzhalters.
    expect(_feld(host, "m:x", "name")).toBe(null);
    expect(host.querySelector(".aiw-mod-ph-name").textContent).toBe("x");

    // Im Feld steht die TEXTFORM, darunter die Aufloesung.
    expect(_feld(host, "m:x", "regelfeld").value).toBe("rule:spurennummer");
    expect(host.querySelector(".aiw-mod-ph-muster-klartext").textContent)
      .toContain(REGELN.spurennummer.pattern);

    // Die Hilfe-Marken sitzen literal an den Bedienelementen (BD09/BD10).
    expect(_feld(host, "m:x", "typ").getAttribute("data-hilfe-id"))
      .toBe("modules.bedienung.phart");
    expect(_feld(host, "m:x", "vorgabe").getAttribute("data-hilfe-id"))
      .toBe("modules.bedienung.phvorgabe");
  });

  it("schreibt bei 'change' und NICHT bei 'input' (F3)", () => {
    const { win, host, rufe } = _mitSchreiben("{{m:x|v}}");
    const feld = _feld(host, "m:x", "vorgabe");
    expect(feld.value).toBe("v");

    feld.value = "neu";
    feld.dispatchEvent(new win.Event("input"));
    expect(rufe).toHaveLength(0);      // F3: beim Tippen passiert NICHTS

    feld.dispatchEvent(new win.Event("change"));
    expect(rufe).toHaveLength(1);
    expect(rufe[0].alt).toEqual({ typ: "m", name: "x" });
    expect(rufe[0].neu).toEqual({ typ: "m", name: "x", vorgabe: "neu",
                                  beschreibung: "", regelfeld: "" });
  });

  it("ruft nicht, wenn sich nichts geaendert hat", () => {
    const { win, host, rufe } = _mitSchreiben("{{m:x|v}}");
    const feld = _feld(host, "m:x", "vorgabe");
    feld.dispatchEvent(new win.Event("change"));
    expect(rufe).toHaveLength(0);
  });

  it("reicht auch eine umgestellte Art durch", () => {
    const { win, host, rufe } = _mitSchreiben("{{m:x}}");
    const wahl = _feld(host, "m:x", "typ");
    expect(wahl.value).toBe("m");
    wahl.value = "o";
    wahl.dispatchEvent(new win.Event("change"));
    expect(rufe).toHaveLength(1);
    expect(rufe[0].neu.typ).toBe("o");
  });

  it("meldet einen Fehlschlag an der Zelle und setzt das Feld zurueck", () => {
    const { win, host, rufe } = _mitSchreiben("{{m:x|v}}",
      { antwort: { ok: false, meldung: "Nicht mehr zu finden." } });
    const feld = _feld(host, "m:x", "vorgabe");
    feld.value = "neu";
    feld.dispatchEvent(new win.Event("change"));
    expect(rufe).toHaveLength(1);
    return Promise.resolve().then(() => {
      expect(feld.value).toBe("v");
      expect(_meldung(host, "m:x", "vorgabe").textContent)
        .toContain("Nicht mehr zu finden.");
    });
  });
});

describe("PT13 F1 — Trennzeichen werden abgewiesen", () => {
  it("weist ab, setzt zurueck, begruendet — und ruft NICHT", () => {
    const { win, host, rufe } = _mitSchreiben("{{m:x|v}}");
    const feld = _feld(host, "m:x", "beschreibung");
    feld.value = "a|b";
    feld.dispatchEvent(new win.Event("change"));

    // DER KERN: der Rueckruf wird gar nicht erst erreicht.
    expect(rufe).toHaveLength(0);
    // Das Feld faellt auf seinen alten Wert zurueck (hier: leer).
    expect(feld.value).toBe("");
    // Und der Grund steht an DER Zelle, in der die Eingabe stand.
    const m = _meldung(host, "m:x", "beschreibung");
    expect(m.textContent).toContain("senkrechter Strich");
    expect(m.className).toContain("ist-fehler");
  });

  it("weist auch die geschweifte Klammer ab", () => {
    const { win, host, rufe } = _mitSchreiben("{{m:x}}");
    const feld = _feld(host, "m:x", "vorgabe");
    feld.value = "x}y";
    feld.dispatchEvent(new win.Event("change"));
    expect(rufe).toHaveLength(0);
    expect(_meldung(host, "m:x", "vorgabe").textContent)
      .toContain("geschweifte Klammer");
  });
});

describe("PT14 F2 — Mehrfachvorkommen", () => {
  const TEXT = "{{m:x|v}} dazwischen {{m:x|v}} und noch {{m:x|v}}";

  it("sagt DAUERHAFT, dass alle Vorkommen betroffen sind", () => {
    const { host } = _mitSchreiben(TEXT);
    const zelle = host.querySelector(".aiw-mod-ph-zahl");
    expect(zelle.className).toContain("ist-mehrfach");
    expect(zelle.textContent).toContain("3");
    expect(host.querySelector(".aiw-mod-ph-mehrfach").textContent)
      .toBe("ändert alle 3");
  });

  it("fragt VOR dem Schreiben zurueck und zaehlt die Stellen auf", () => {
    const gefragt = [];
    const { win, host, rufe } = _mitSchreiben(TEXT, {
      frage: (t) => { gefragt.push(t); return true; },
    });
    const feld = _feld(host, "m:x", "vorgabe");
    feld.value = "neu";
    feld.dispatchEvent(new win.Event("change"));

    expect(gefragt).toHaveLength(1);
    expect(gefragt[0]).toContain("3-mal");
    expect(gefragt[0]).toContain("ALLE 3 Vorkommen");
    // Die betroffenen Stellen stehen im WORTLAUT in der Rueckfrage.
    expect(gefragt[0]).toContain("{{m:x|v}}");
    expect(rufe).toHaveLength(1);
  });

  it("aendert NICHTS, wenn die Rueckfrage verneint wird", () => {
    const { win, host, rufe } = _mitSchreiben(TEXT, { frage: () => false });
    const feld = _feld(host, "m:x", "vorgabe");
    feld.value = "neu";
    feld.dispatchEvent(new win.Event("change"));
    expect(rufe).toHaveLength(0);
    expect(feld.value).toBe("v");
    expect(_meldung(host, "m:x", "vorgabe").textContent)
      .toContain("Rückfrage wurde verneint");
  });

  it("fragt bei einem einzigen Vorkommen NICHT", () => {
    const gefragt = [];
    const { win, host, rufe } = _mitSchreiben("{{m:x|v}}", {
      frage: (t) => { gefragt.push(t); return true; },
    });
    const feld = _feld(host, "m:x", "vorgabe");
    feld.value = "neu";
    feld.dispatchEvent(new win.Event("change"));
    expect(gefragt).toHaveLength(0);
    expect(rufe).toHaveLength(1);
  });
});

// ===========================================================================
// BUILD 683 (Vorgang 5a7d4e21): GELESEN WIRD DIE QUELLE, NICHT DER SPIEGEL
// ===========================================================================

const _eing = readFileSync(
  "management/server/static/cockpit_baustein_eingabe.js", "utf-8");

/** Fenster MIT dem Eingabe-Bauteil - fuer die Gegenprobe am Spiegel. */
function _ctxE() {
  const win = _ctx();
  win.eval(_eing);
  return win;
}

describe("PT15 zerlegeBlock — alle Textstellen eines Blocks", () => {
  it("zaehlt ueber Absatz, Liste und Tabellenzelle hinweg ZUSAMMEN", () => {
    const win = _ctx();
    const api = _api(win);

    // Tabelle: derselbe Platzhalter in zwei Zellen ist EIN Eintrag mit ZWEI
    // Vorkommen - nicht zwei Eintraege. Beim Zurueckschreiben aendert eine
    // Zeile beide, und genau das muss die Zahl sagen.
    const z = api.zerlegeBlock(
      { content: [["{{m:x|v}}", "frei"], ["{{m:x|v}}", "{{o:y}}"]] },
      win.PlaceholderChips);
    expect(z.eintraege.map((e) => e.typ + ":" + e.name))
      .toEqual(["m:x", "o:y"]);
    expect(z.eintraege[0].vorkommen).toBe(2);
    expect(z.eintraege[0].rohtoken).toEqual(["{{m:x|v}}", "{{m:x|v}}"]);

    // Liste, flach und verschachtelt.
    const l = api.zerlegeBlock(
      { items: ["{{m:x}}", { content: "{{m:x}}", items: ["{{o:tief}}"] }] },
      win.PlaceholderChips);
    expect(l.eintraege[0].vorkommen).toBe(2);
  });

  it("erkennt V6 ueber Zellen hinweg — verschiedene Angaben, ein Name", () => {
    const win = _ctx();
    const z = _api(win).zerlegeBlock(
      { content: [["{{m:x|eins}}"], ["{{m:x|zwei}}"]] },
      win.PlaceholderChips);
    expect(z.eintraege).toHaveLength(1);
    expect(z.eintraege[0].varianten).toHaveLength(2);
    // Und der Befund faellt: beim Ausfuellen gewinnt eine Fassung.
    const erg = _api(win).pruefe(z.eintraege[0], {}, {});
    expect(erg.befunde.some((b) => b.kennung === "V6")).toBe(true);
  });

  it("prueft den Verdacht JE TEXTSTELLE, nicht ueber alle hinweg", () => {
    // DER FALL, DER DIE REGEL BEGRUENDET: in einer Zelle steht der
    // Platzhalter richtig, in der anderen vertippt. Wuerde der Verdacht
    // gegen die Rohtoken ALLER Stellen geprueft, bliebe der Tippfehler
    // unentdeckt - er stuende dann woertlich im Vermerk.
    const win = _ctx();
    const z = _api(win).zerlegeBlock(
      { content: [["{{m:name}}"], ["{{m:na me}}"]] }, win.PlaceholderChips);
    expect(z.verdaechtige.map((v) => v.roh)).toEqual(["{{m:na me}}"]);
  });

  it("nimmt gerenderte Chips zurueck, statt sie doppelt zu zaehlen", () => {
    const win = _ctx();
    const html = win.PlaceholderChips.hydrateChips("Text {{m:x|v}} Ende");
    expect(html).toContain("data-chip-raw");
    const z = _api(win).zerlegeBlock({ text: html }, win.PlaceholderChips);
    expect(z.eintraege).toHaveLength(1);
    expect(z.eintraege[0].vorkommen).toBe(1);
    expect(z.verdaechtige).toEqual([]);
  });

  it("liefert null ohne collectBlockTexts — der Aufrufer faellt zurueck", () => {
    const win = _ctx();
    const ohne = Object.assign({}, win.PlaceholderChips);
    delete ohne.collectBlockTexts;
    expect(_api(win).zerlegeBlock({ text: "{{m:x}}" }, ohne)).toBe(null);
  });
});

describe("PT16 zeigeBlock — die Sicht liest die Quelle", () => {
  it("GEGENPROBE: findet, was der Klartextspiegel verliert", () => {
    // Der Beleg fuer den ganzen Vorgang. 'checklist' ist eine Blockart, die
    // klartextAus() NICHT kennt; sie faellt dort auf d.text/d.caption
    // zurueck und liefert eine leere Zeichenkette. collectBlockTexts geht
    // dagegen in .items[]. Eine kuenftige Blockart mit Text in items waere
    // also in der Tabelle unsichtbar UND trotzdem beschreibbar gewesen.
    const win = _ctxE();
    const daten = { items: ["{{m:versteckt|v}}"] };

    const spiegel = win.AIWBausteinEingabe.klartextAus("checklist", daten);
    expect(spiegel).toBe("");          // Vorbedingung: der Spiegel verliert ihn

    const host = win.document.getElementById("host");
    const t = _api(win).erzeuge(host, { tpl: win.AIWCockpitTemplates,
                                        chips: win.PlaceholderChips });
    t.zeigeBlock(daten, spiegel, {}, {});

    const zeilen = host.querySelectorAll(".aiw-mod-ph-tabelle tbody tr");
    expect(Array.prototype.map.call(zeilen,
      (r) => r.getAttribute("data-name"))).toEqual(["m:versteckt"]);

    // Und die Gegenrichtung, damit die Gegenprobe eine ist: ueber den
    // Spiegel gelesen bleibt die Tabelle leer.
    const win2 = _ctxE();
    const host2 = win2.document.getElementById("host");
    _api(win2).erzeuge(host2, { tpl: win2.AIWCockpitTemplates,
                                chips: win2.PlaceholderChips })
              .zeige(spiegel, {}, {});
    expect(host2.querySelector(".aiw-mod-ph-tabelle")).toBe(null);
  });

  it("faellt auf den Spiegel zurueck und SAGT es", () => {
    const win = _ctx();
    // collectBlockTexts entfernen - der Rueckfall muss greifen UND sich
    // melden. Ein stiller Rueckfall waere die Falschaussage, gegen die
    // dieser Vorgang gebaut ist.
    delete win.PlaceholderChips.collectBlockTexts;
    const host = win.document.getElementById("host");
    _api(win).erzeuge(host, { tpl: win.AIWCockpitTemplates,
                              chips: win.PlaceholderChips })
             .zeigeBlock({ text: "{{m:x}}" }, "{{m:x}} {{o:y}}", {}, {});

    // Gelesen wurde der Spiegel: er fuehrt ZWEI Platzhalter, die Quelle nur
    // einen.
    expect(host.querySelectorAll(".aiw-mod-ph-tabelle tbody tr").length)
      .toBe(2);
    const meldung = host.querySelector(".aiw-mod-ph-meldung").textContent;
    expect(meldung).toContain("KLARTEXTSPIEGEL");
    expect(meldung).toContain("Tabellenzelle");
  });

  it("meldet den Spiegel NICHT, wenn die Quelle gelesen wurde", () => {
    const win = _ctx();
    const host = win.document.getElementById("host");
    _api(win).erzeuge(host, { tpl: win.AIWCockpitTemplates,
                              chips: win.PlaceholderChips })
             .zeigeBlock({ text: "{{m:x}}" }, "{{m:x}}", {}, {});
    expect(host.querySelector(".aiw-mod-ph-meldung").textContent)
      .not.toContain("KLARTEXTSPIEGEL");
  });
});
