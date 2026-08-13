/**
 * tests/unit/test_cockpit_baustein_ph_schreiben.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Baustein-Module (W1) — ZURUECKSCHREIBEN, Build 681 (Vorgang 7c1f2a94)
 *
 * Testsuite fuer management/server/static/cockpit_baustein_ph_schreiben.js.
 * Geprueft wird der ECHTE Code (readFileSync + JSDOM) ZUSAMMEN mit seiner
 * echten Quelle userinfo/placeholder_chips.js. Ein Nachbau von parse() haette
 * genau die Doppelwahrheit geprueft, die dieses Bauteil vermeiden soll.
 *
 * PS01 — feldPruefen: F1, die Trennzeichen werden ABGEWIESEN.
 * PS02 — typPruefen / namePruefen.
 * PS03 — tokenBauen: leere Felder am Ende fallen weg, dazwischen nicht.
 * PS04 — tokenProbe: die Rueckprobe schlaegt an, wenn sie muss.
 * PS05 — ersetzeInText: zeichengenau, alle Vorkommen, Sonderzeichen.
 * PS06 — ersetzeInText: Chip-HTML (data-chip-raw) wird nicht zerschnitten.
 * PS07 — ersetzeInBlock: Absatz, Liste (flach + verschachtelt), TABELLE.
 * PS08 — schreibe: der ganze Vorgang, und jeder Abbruch ohne Wirkung.
 * PS09 — schreibe: UTF-8 und multilinguale Werte bleiben unangetastet.
 * PS10 — GEGENPROBE: ein Token, das die Rueckprobe nicht besteht, wird
 *        NICHT geschrieben (V1 wuerde sonst hier ENTSTEHEN).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _chips = readFileSync("userinfo/placeholder_chips.js", "utf-8");
const _src = readFileSync(
  "management/server/static/cockpit_baustein_ph_schreiben.js", "utf-8");

function _ctx() {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.FORENSIC_DEBUG = false;
  dom.window.eval(_chips);
  dom.window.eval(_src);
  return dom.window;
}
function _api(win) { return (win || _ctx()).AIWBausteinPhSchreiben; }
function _pc(win) { return win.PlaceholderChips; }

describe("PS01 feldPruefen — F1: abweisen, nicht entschaerfen", () => {
  it("weist den senkrechten Strich ab und benennt ihn", () => {
    const r = _api().feldPruefen("a|b", "Die Vorgabe");
    expect(r.ok).toBe(false);
    expect(r.meldung).toContain("senkrechter Strich");
    expect(r.meldung).toContain("Die Vorgabe");
    // Die Meldung sagt AUSDRUECKLICH, dass nichts uebernommen wird.
    expect(r.meldung).toContain("NICHT übernommen");
  });

  it("weist die geschweifte Klammer und den Zeilenumbruch ab", () => {
    expect(_api().feldPruefen("x}y").ok).toBe(false);
    expect(_api().feldPruefen("x\ny").ok).toBe(false);
    expect(_api().feldPruefen("x\ry").ok).toBe(false);
  });

  it("laesst alles andere durch — auch Sonderzeichen und fremde Schrift", () => {
    ["", "Müller & Söhne", "日本語のテキスト", "a-b_c.d", "50 % / 3 €",
     "<script>", "\"quoted\"", "{einfach"].forEach((w) => {
      expect(_api().feldPruefen(w).ok).toBe(true);
    });
  });
});

describe("PS02 typPruefen / namePruefen", () => {
  it("kennt genau a, m und o", () => {
    ["a", "m", "o"].forEach((t) => expect(_api().typPruefen(t).ok).toBe(true));
    // Die LANGFORM ist hier bewusst NICHT zulaessig: geschrieben wird die
    // Kurzform, weil parse() ohnehin auf sie normalisiert.
    ["mandatory", "x", "", "A"].forEach((t) => {
      expect(_api().typPruefen(t).ok).toBe(false);
    });
  });

  it("laesst nur Namen zu, die _CHIP_RE auch wiederfindet", () => {
    expect(_api().namePruefen("spuren.nr_1-a").ok).toBe(true);
    expect(_api().namePruefen("").ok).toBe(false);
    expect(_api().namePruefen("na me").ok).toBe(false);
    expect(_api().namePruefen("naüme").ok).toBe(false);
  });
});

describe("PS03 tokenBauen", () => {
  const b = (o) => _api().tokenBauen(o);

  it("laesst leere Felder am Ende weg", () => {
    expect(b({ typ: "m", name: "x" })).toBe("{{m:x}}");
    expect(b({ typ: "m", name: "x", vorgabe: "v" })).toBe("{{m:x|v}}");
    expect(b({ typ: "o", name: "x", vorgabe: "v", beschreibung: "b" }))
      .toBe("{{o:x|v|b}}");
  });

  it("laesst leere Felder DAZWISCHEN stehen — sonst rutscht das Muster", () => {
    expect(b({ typ: "m", name: "x", regelfeld: "rule:a" }))
      .toBe("{{m:x|||rule:a}}");
    expect(b({ typ: "m", name: "x", vorgabe: "v", regelfeld: "rule:a" }))
      .toBe("{{m:x|v||rule:a}}");
  });
});

describe("PS04 tokenProbe — die Rueckprobe", () => {
  it("nimmt ein Token an, das sich zeichengleich zurueckliest", () => {
    const w = _ctx();
    const soll = { typ: "m", name: "x", vorgabe: "v", beschreibung: "b",
                   regelfeld: "rule:a" };
    const t = _api(w).tokenBauen(soll);
    expect(_api(w).tokenProbe(t, soll, _pc(w)).ok).toBe(true);
  });

  it("schlaegt an, wenn Text neben dem Token stuende", () => {
    const w = _ctx();
    const r = _api(w).tokenProbe("{{m:x}} Rest",
      { typ: "m", name: "x" }, _pc(w));
    expect(r.ok).toBe(false);
  });

  it("nennt bei einer Abweichung das FELD, nicht nur die Tatsache", () => {
    const w = _ctx();
    const r = _api(w).tokenProbe("{{m:x|anders}}",
      { typ: "m", name: "x", vorgabe: "v" }, _pc(w));
    expect(r.ok).toBe(false);
    expect(r.meldung).toContain("die Vorgabe");
  });

  it("schreibt nicht, wenn die Zerlegung fehlt (Grundregel 1)", () => {
    // OHNE placeholder_chips.js im Fenster - der Rueckfall auf
    // window.PlaceholderChips greift dann ins Leere. Genau dieser Fall darf
    // NICHT als 'in Ordnung' durchgehen.
    const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>",
      { runScripts: "dangerously", url: "http://localhost" });
    dom.window.eval(_src);
    const r = dom.window.AIWBausteinPhSchreiben.tokenProbe(
      "{{m:x}}", { typ: "m", name: "x" }, null);
    expect(r.ok).toBe(false);
    expect(r.meldung).toContain("nicht geladen");
  });
});

describe("PS05 ersetzeInText", () => {
  it("ersetzt ALLE Vorkommen und zaehlt sie", () => {
    const w = _ctx();
    const t = "A {{m:x}} B {{m:x|alt}} C {{o:y}}";
    const r = _api(w).ersetzeInText(t, "m", "x", "{{m:x|neu}}", _pc(w));
    expect(r.ersetzt).toBe(2);
    expect(r.text).toBe("A {{m:x|neu}} B {{m:x|neu}} C {{o:y}}");
  });

  it("laesst den Text unangetastet, wenn nichts passt", () => {
    const w = _ctx();
    const t = "nur Text {{o:y}}";
    const r = _api(w).ersetzeInText(t, "m", "x", "{{m:x}}", _pc(w));
    expect(r.ersetzt).toBe(0);
    expect(r.text).toBe(t);
  });

  it("faellt nicht auf Sonderzeichen herein (kein Suchen-und-Ersetzen)", () => {
    const w = _ctx();
    // Der alte Wert enthaelt Zeichen, die als regulaerer Ausdruck etwas
    // anderes bedeuten wuerden. Ueber parse() ist das ohne Belang.
    const t = "vor {{m:x|a.*b[c]$}} nach";
    const r = _api(w).ersetzeInText(t, "m", "x", "{{m:x|neu}}", _pc(w));
    expect(r.ersetzt).toBe(1);
    expect(r.text).toBe("vor {{m:x|neu}} nach");
  });

  it("erzeugt keine Kettenreaktion, wenn das neue Token wieder passt", () => {
    const w = _ctx();
    const t = "{{m:x}} {{m:x}}";
    const r = _api(w).ersetzeInText(t, "m", "x", "{{m:x|1}}", _pc(w));
    expect(r.ersetzt).toBe(2);
    expect(r.text).toBe("{{m:x|1}} {{m:x|1}}");
  });
});

describe("PS06 Chip-HTML wird nicht zerschnitten", () => {
  it("nimmt einen gerenderten Chip vor dem Ersetzen zurueck", () => {
    const w = _ctx();
    const html = w.PlaceholderChips.hydrateChips("Hallo {{m:x|alt}}!");
    // Vorbedingung: es ist wirklich Chip-HTML und kein Token mehr.
    expect(html).toContain("ph-chip");
    expect(html).toContain("data-chip-raw");

    const r = _api(w).ersetzeInText(html, "m", "x", "{{m:x|neu}}", _pc(w));
    expect(r.ersetzt).toBe(1);
    // Das Attribut ist nicht zerschnitten worden, und der Chip ist zur
    // Token-Form zurueckgenommen - der Speicherform.
    expect(r.text).toContain("{{m:x|neu}}");
    expect(r.text).not.toContain("ph-chip");
  });
});

describe("PS07 ersetzeInBlock — ueber ALLE Textstellen", () => {
  it("fasst Absatz, Liste und Tabellenzelle an", () => {
    const w = _ctx();
    const api = _api(w);
    const neu = "{{m:x|neu}}";

    const absatz = api.ersetzeInBlock(
      { text: "a {{m:x}} b" }, "m", "x", neu, _pc(w));
    expect(absatz.ersetzt).toBe(1);
    expect(absatz.daten.text).toBe("a {{m:x|neu}} b");

    const liste = api.ersetzeInBlock(
      { items: ["{{m:x}}", { content: "{{m:x}}", items: ["{{m:x}}"] }] },
      "m", "x", neu, _pc(w));
    // MITGEZOGEN IN BUILD 710 - und dieser Fall hat genau getan, wofuer
    // er geschrieben wurde.
    //
    // Bis Build 710 stand hier 'toBe(2)' mit der Begruendung, die
    // verschachtelte Ebene falle mit, weil mapBlockTexts nur eine Ebene tief
    // gehe: "das ist die Vorschrift des Bestandes, und dieser Test schreibt
    // sie fest, damit eine Aenderung dort auffaellt." Sie ist aufgefallen.
    //
    // Die Vorschrift des Bestandes war ein FEHLER, kein Entwurf: derselbe
    // Waechter, der hier die Zahl festhielt, hat verdeckt, dass ein
    // {{m:...}} in einem verschachtelten Listeneintrag dem Ermittler nie
    // zum Ausfuellen angeboten wurde (placeholder_wizard.js:241,636) und
    // serverseitig nie geprueft wurde (forensic_api/report.py:2063). Seit
    // Build 710 geht mapBlockTexts rekursiv - und damit greift auch das
    // Zurueckschreiben aus der Platzhalter-Tabelle bis in die Verschachtelung.
    expect(liste.ersetzt).toBe(3);
    expect(liste.daten.items[0]).toBe(neu);
    expect(liste.daten.items[1].content).toBe(neu);
    expect(liste.daten.items[1].items[0]).toBe(neu);

    // Build 710: die Quellenangabe eines Zitats ist ebenfalls eine
    // Textstelle. html_renderer.py:127-151 rendert sie als <cite> in den
    // Vermerk; seit Build 704 ueberlebt sie den Komfortmodus.
    const zitat = api.ersetzeInBlock(
      { text: "Zitat {{m:x}}", caption: "Quelle {{m:x}}" },
      "m", "x", neu, _pc(w));
    expect(zitat.ersetzt).toBe(2);
    expect(zitat.daten.text).toBe("Zitat " + neu);
    expect(zitat.daten.caption).toBe("Quelle " + neu);

    const tabelle = api.ersetzeInBlock(
      { content: [["{{m:x}}", "frei"], ["nichts", "{{m:x|alt}}"]] },
      "m", "x", neu, _pc(w));
    expect(tabelle.ersetzt).toBe(2);
    expect(tabelle.daten.content[0][0]).toBe(neu);
    expect(tabelle.daten.content[1][1]).toBe(neu);
  });

  it("laesst die Eingabedaten unberuehrt (neue block_data)", () => {
    const w = _ctx();
    const alt = { text: "{{m:x}}" };
    const r = _api(w).ersetzeInBlock(alt, "m", "x", "{{m:x|n}}", _pc(w));
    expect(alt.text).toBe("{{m:x}}");
    expect(r.daten.text).toBe("{{m:x|n}}");
  });
});

describe("PS08 schreibe — der ganze Vorgang", () => {
  const auftrag = (w, daten, neu, alt) => _api(w).schreibe({
    daten: daten,
    alt: alt || { typ: "m", name: "x" },
    neu: Object.assign({ typ: "m", name: "x", vorgabe: "", beschreibung: "",
                         regelfeld: "" }, neu),
    chips: _pc(w)
  });

  it("schreibt und meldet die Zahl der Vorkommen", () => {
    const w = _ctx();
    const r = auftrag(w, { text: "{{m:x}} und {{m:x}}" }, { vorgabe: "v" });
    expect(r.ok).toBe(true);
    expect(r.ersetzt).toBe(2);
    expect(r.token).toBe("{{m:x|v}}");
    expect(r.daten.text).toBe("{{m:x|v}} und {{m:x|v}}");
    expect(r.meldung).toContain("2 Vorkommen");
  });

  it("F1: bricht bei einem Trennzeichen ab, OHNE Wirkung", () => {
    const w = _ctx();
    const daten = { text: "{{m:x}}" };
    const r = auftrag(w, daten, { beschreibung: "a|b" });
    expect(r.ok).toBe(false);
    expect(r.ersetzt).toBe(0);
    expect(daten.text).toBe("{{m:x}}");
    expect(r.meldung).toContain("senkrechter Strich");
  });

  it("bricht bei unbekannter Art ab", () => {
    const w = _ctx();
    const r = auftrag(w, { text: "{{m:x}}" }, { typ: "z" });
    expect(r.ok).toBe(false);
    expect(r.meldung).toContain("Unbekannte Art");
  });

  it("meldet es, wenn der Platzhalter gar nicht mehr da ist", () => {
    // GRUNDREGEL 1: kein stiller Fehlschlag. Ein 'gespeichert', nach dem
    // nichts anders ist, waere die schaedlichste aller Antworten.
    const w = _ctx();
    const r = auftrag(w, { text: "hier steht nichts" }, { vorgabe: "v" });
    expect(r.ok).toBe(false);
    expect(r.ersetzt).toBe(0);
    expect(r.meldung).toContain("nicht mehr zu finden");
    expect(r.meldung).toContain("NICHTS geändert");
  });

  it("kann die Art umstellen — der Schluessel aendert sich mit", () => {
    const w = _ctx();
    const r = auftrag(w, { text: "{{m:x|v}}" },
      { typ: "o", vorgabe: "v" }, { typ: "m", name: "x" });
    expect(r.ok).toBe(true);
    expect(r.daten.text).toBe("{{o:x|v}}");
  });

  it("schreibt nicht ohne Blockdaten und nicht ohne Werkzeug", () => {
    const w = _ctx();
    expect(_api(w).schreibe({ daten: null, alt: {}, neu: {},
                              chips: _pc(w) }).ok).toBe(false);
    expect(_api(w).schreibe({ daten: { text: "" }, alt: { typ: "m", name: "x" },
                              neu: { typ: "m", name: "x" },
                              chips: null }).ok).toBe(false);
  });
});

describe("PS09 UTF-8 und Mehrsprachigkeit", () => {
  it("traegt fremde Schrift unveraendert durch das Token", () => {
    const w = _ctx();
    // Das Forum ist multilingual; ein Bauteil, das hier umkodiert, faellt
    // erst im fertigen Vermerk auf.
    const werte = ["Bräutigam", "Ελληνικά", "日本語", "Ссылка", "🙂 Emoji"];
    werte.forEach((v) => {
      const r = _api(w).schreibe({
        daten: { text: "vor {{m:x}} nach" },
        alt: { typ: "m", name: "x" },
        neu: { typ: "m", name: "x", vorgabe: v, beschreibung: v,
               regelfeld: "" },
        chips: _pc(w)
      });
      expect(r.ok).toBe(true);
      expect(r.daten.text).toBe("vor {{m:x|" + v + "|" + v + "}} nach");
      // Und die Gegenprobe: die Zerlegung liest genau das zurueck.
      const seg = _pc(w).parse(r.daten.text).filter((s) => s.type === "chip");
      expect(seg).toHaveLength(1);
      expect(seg[0].defaultVal).toBe(v);
      expect(seg[0].description).toBe(v);
    });
  });
});

describe("PS10 GEGENPROBE — die Rueckprobe verhindert einen V1-Befund", () => {
  it("erzeugt kein Token, das der Bestand nicht mehr lesen kann", () => {
    // Eine Pruefung, die nie anschlaegt, belegt nichts (TE5). Hier wird der
    // Name absichtlich unbrauchbar gemacht: kaeme das Token trotzdem in den
    // Text, stuende es woertlich im Vermerk - genau der Befund V1, vor dem
    // die Tabelle daneben warnt.
    const w = _ctx();
    const daten = { text: "{{m:x}}" };
    const r = _api(w).schreibe({
      daten: daten,
      alt: { typ: "m", name: "x" },
      neu: { typ: "m", name: "na me", vorgabe: "", beschreibung: "",
             regelfeld: "" },
      chips: _pc(w)
    });
    expect(r.ok).toBe(false);
    expect(daten.text).toBe("{{m:x}}");
    expect(r.meldung).toContain("unzulässige Zeichen");
  });
});
