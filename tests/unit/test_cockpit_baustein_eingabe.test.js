/**
 * tests/unit/test_cockpit_baustein_eingabe.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Baustein-Module (W1) — EINGABE: Editor.js + Rohmodus, Build 656
 *
 * Gegenstand: management/server/static/cockpit_baustein_eingabe.js
 * (Ticket 8f2b64d9).
 *
 * WAS HIER GEPRUEFT WIRD UND WAS NICHT: Der KERN des Tickets ist nicht der
 * Editor, sondern der VERGLEICH beim Moduswechsel — "Unterschiede werden
 * GEMELDET, statt sie zu schlucken". Genau der ist hier vollstaendig
 * gemessen, und zwar gegen einen Editor-Stub, der das tut, was Editor.js
 * wirklich tut: er gibt beim Auslesen nur zurueck, was seine Werkzeuge
 * kennen. Dass Editor.js selbst zeichnet, ist in der VM zu sehen.
 *
 * ED01 — tiefVergleich: entfallen / geaendert / neu, MIT PFAD.
 * ED02 — jsonPruefen: Zeile und Spalte bei einem Fehler; nur Objekte gelten.
 * ED03 — klammerbilanz: fehlend, ueberkreuzt, in Zeichenketten nicht zaehlen.
 * ED04 — formatiere: rueckt ein, ohne den Inhalt anzutasten.
 * ED05 — klartextAus: der body-Spiegel je Blockart, Platzhalter bleiben.
 * ED06 — Moduswechsel Komfort -> Roh und zurueck, VERLUSTFREI.
 * ED07 — DER KERNFALL: ein Wechsel MIT Verlust wird gemeldet und wartet auf
 *        eine Bestaetigung; 'Im Rohmodus bleiben' aendert nichts.
 * ED08 — der Entwurfsrueckruf feuert (die Bruecke zum Entwurfsspeicher).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _chips = readFileSync("userinfo/placeholder_chips.js", "utf-8");
const _src = readFileSync(
  "management/server/static/cockpit_baustein_eingabe.js", "utf-8");

function _ctx() {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body><div id='host'></div></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.FORENSIC_DEBUG = false;
  dom.window.eval(_chips);
  dom.window.eval(_src);
  return dom.window;
}
function _api(win) { return (win || _ctx()).AIWBausteinEingabe; }

/**
 * Ein Editor-Stub, der sich wie Editor.js verhaelt: beim Auslesen gibt er
 * NUR die Felder zurueck, die sein Werkzeug kennt. 'kennt' bildet genau das
 * ab — ohne diese Eigenschaft waere der ganze Vergleich nicht pruefbar.
 */
function _stubCtor(kennt) {
  return function Stub(cfg) {
    this.cfg = cfg;
    const b = (cfg.data && cfg.data.blocks && cfg.data.blocks[0]) || {};
    this._type = b.type || "paragraph";
    this._data = b.data || {};
    this.isReady = Promise.resolve();
    this.save = () => {
      let d = this._data;
      if (Array.isArray(kennt)) {
        d = {};
        kennt.forEach((k) => {
          if (Object.prototype.hasOwnProperty.call(this._data, k)) {
            d[k] = this._data[k];
          }
        });
      }
      return Promise.resolve({ blocks: [{ type: this._type, data: d }] });
    };
    this.destroy = () => { this._zerstoert = true; };
  };
}

describe("cockpit_baustein_eingabe — reine Funktionen (Build 656)", () => {
  // ED01 -----------------------------------------------------------------
  it("ED01: tiefVergleich benennt jeden Unterschied MIT PFAD", () => {
    const api = _api();

    expect(api.tiefVergleich({ text: "a" }, { text: "a" })).toEqual([]);

    const u = api.tiefVergleich(
      { text: "alt", extra: 1, tief: { a: 1, b: 2 } },
      { text: "neu", tief: { a: 1 }, dazu: 9 });
    const nach = {};
    u.forEach((x) => { nach[x.pfad] = x.art; });
    // DER GEFAEHRLICHE FALL zuerst: was der Editor nicht kennt, faellt weg.
    expect(nach.extra).toBe("entfallen");
    expect(nach["tief.b"]).toBe("entfallen");
    expect(nach.text).toBe("geaendert");
    expect(nach.dazu).toBe("neu");
    // Eine Meldung 'die Daten haben sich geaendert' hilft niemandem -
    // 'tief.b ist entfallen' schon. Deshalb der Pfad.
    expect(u.find((x) => x.pfad === "tief.b").alt).toBe(2);

    // Reihenfolge in Arrays IST bedeutungstragend (Tabellenzeilen).
    const t = api.tiefVergleich(
      { content: [["a", "b"], ["c", "d"]] },
      { content: [["a", "b"]] });
    expect(t.length).toBe(1);
    expect(t[0].pfad).toBe("content.1");
    expect(t[0].art).toBe("entfallen");

    // Typwechsel ist eine Aenderung, keine Gleichheit.
    expect(api.tiefVergleich({ a: 1 }, { a: "1" })[0].art).toBe("geaendert");
    expect(api.tiefVergleich({ a: null }, { a: {} })[0].art).toBe("geaendert");
  });

  // ED02 -----------------------------------------------------------------
  it("ED02: jsonPruefen nennt Zeile und Spalte", () => {
    const api = _api();

    const gut = api.jsonPruefen('{"text": "hallo"}');
    expect(gut.ok).toBe(true);
    expect(gut.wert).toEqual({ text: "hallo" });

    // Der Fehler steht in Zeile 2 — eine Zeichenposition in einem langen
    // Text hilft beim Suchen nicht, Zeile und Spalte schon.
    const schlecht = api.jsonPruefen('{"a": 1,\n  "b" 2}');
    expect(schlecht.ok).toBe(false);
    expect(schlecht.zeile).toBe(2);
    expect(schlecht.spalte).toBeGreaterThan(1);

    // Gueltiges JSON, aber kein Objekt: Editor.js reicht je Block ein
    // Objekt an sein Werkzeug durch.
    expect(api.jsonPruefen("[1,2]").ok).toBe(false);
    expect(api.jsonPruefen("[1,2]").meldung).toContain("OBJEKT");
    expect(api.jsonPruefen("42").ok).toBe(false);
    expect(api.jsonPruefen("null").ok).toBe(false);

    // Leer ist ein eigener Befund und keine stille Null.
    expect(api.jsonPruefen("   ").meldung).toContain("leer");
  });

  // ED03 -----------------------------------------------------------------
  it("ED03: klammerbilanz beantwortet die erste Frage beim Suchen", () => {
    const api = _api();

    expect(api.klammerbilanz('{"a": [1, 2]}').ok).toBe(true);

    const fehlt = api.klammerbilanz('{"a": [1, 2]');
    expect(fehlt.ok).toBe(false);
    expect(fehlt.offen).toBe(1);
    expect(fehlt.meldung).toContain("nicht geschlossen");

    const kreuz = api.klammerbilanz('{"a": [1, 2}');
    expect(kreuz.ok).toBe(false);
    expect(kreuz.meldung).toContain("überkreuzen");

    expect(api.klammerbilanz('}').meldung).toContain("ohne öffnende");

    // KLAMMERN IN ZEICHENKETTEN ZAEHLEN NICHT MIT — sonst waere die Bilanz
    // Laerm statt Auskunft. Das Forum ist multilingual, geschweifte
    // Klammern im Text sind keine Seltenheit.
    expect(api.klammerbilanz('{"a": "} kein Ende {"}').ok).toBe(true);
    expect(api.klammerbilanz('{"a": "\\" auch nicht }"}').ok).toBe(true);

    // Offene Zeichenkette ist ein eigener, hilfreicherer Befund.
    expect(api.klammerbilanz('{"a": "offen}').meldung)
      .toContain("Anführungszeichen");
  });

  // ED04 -----------------------------------------------------------------
  it("ED04: formatiere rueckt ein, ohne den Inhalt anzutasten", () => {
    const api = _api();
    const f = api.formatiere('{"b":2,"a":[1,2]}');
    expect(f.ok).toBe(true);
    expect(f.text).toContain("\n");
    // AM INHALT AENDERT SICH NICHTS - nur an der Darstellung.
    expect(JSON.parse(f.text)).toEqual({ b: 2, a: [1, 2] });

    const kaputt = api.formatiere("{nicht");
    expect(kaputt.ok).toBe(false);
    // Der Text bleibt UNVERAENDERT stehen: wer gerade tippt, soll seine
    // Arbeit nicht durch einen Knopfdruck verlieren.
    expect(kaputt.text).toBe("{nicht");
    expect(kaputt.fehler).toBeTruthy();
  });

  // ED05 -----------------------------------------------------------------
  it("ED05: klartextAus erzeugt den body-Spiegel", () => {
    const win = _ctx();
    const api = _api(win);
    const chips = win.PlaceholderChips;

    expect(api.klartextAus("paragraph", { text: "Hallo" }, chips))
      .toBe("Hallo");
    expect(api.klartextAus("header", { text: "Titel" }, chips)).toBe("Titel");

    // Auszeichnung faellt weg, PLATZHALTER BLEIBEN - sonst zaehlt der
    // Validator sie nicht mehr, und die Platzhalter-Tabelle findet nichts.
    expect(api.klartextAus("paragraph",
      { text: "Hallo <b>Welt</b> {{m:name}}" }, chips))
      .toBe("Hallo Welt {{m:name}}");

    expect(api.klartextAus("table",
      { content: [["A", "B"], ["c", "{{a:x}}"]] }, chips))
      .toBe("A\tB\nc\t{{a:x}}");

    expect(api.klartextAus("list",
      { items: [{ content: "eins", items: [{ content: "unter" }] },
                { content: "zwei" }] }, chips))
      .toBe("eins\n  unter\nzwei");
    // Die flache Altform kommt ebenfalls vor.
    expect(api.klartextAus("list", { items: ["a", "b"] }, chips)).toBe("a\nb");

    expect(api.klartextAus("quote", { text: "Zitat", caption: "Quelle" },
      chips)).toBe("Zitat\nQuelle");

    // Ein Trenner hat keinen Text - body ist aber NOT NULL, und ein leerer
    // faellt beim Validator durch ('body fehlt').
    expect(api.klartextAus("delimiter", {}, chips)).toBe("---");

    // Eine Blockart, die dieser Spiegel nicht kennt, wird NICHT still leer
    // gelassen: was an Text da ist, kommt mit.
    expect(api.klartextAus("wasneues", { text: "trotzdem" }, chips))
      .toBe("trotzdem");
  });
});

describe("cockpit_baustein_eingabe — der Moduswechsel (Build 656)", () => {
  function _bau(win, kennt, opts) {
    const host = win.document.getElementById("host");
    const api = win.AIWBausteinEingabe;
    const steuer = api.erzeuge(host, Object.assign({
      EditorCtor: _stubCtor(kennt),
      tools: {},
    }, opts || {}));
    return { host, api, steuer };
  }
  const _modusBtn = (host) => host.querySelector(".aiw-mod-eing-modus");
  const _roh = (host) => host.querySelector(".aiw-mod-eing-roh");
  const _kasten = (host) => host.querySelector(".aiw-mod-eing-vergleich");
  const _meldung = (host) => host.querySelector(".aiw-mod-eing-meldung");

  // ED06 -----------------------------------------------------------------
  it("ED06: Komfort -> Roh -> Komfort ist verlustfrei", async () => {
    const win = _ctx();
    const { host, steuer } = _bau(win, null);   // Stub kennt ALLES
    steuer.setze("table", { content: [["A", "B"]] });
    expect(steuer.modus()).toBe("komfort");

    _modusBtn(host).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(steuer.modus()).toBe("roh");
    // Im Rohmodus stehen NUR die Daten - die Blockart steht links und ist
    // dort gesperrt, damit sie nicht an zwei Stellen bearbeitbar ist.
    expect(JSON.parse(_roh(host).value)).toEqual({ content: [["A", "B"]] });
    expect(host.querySelector(".aiw-mod-eing-typ").disabled).toBe(true);

    _modusBtn(host).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(steuer.modus()).toBe("komfort");
    expect(_kasten(host).hidden).toBe(true);
    expect(_meldung(host).textContent).toContain("verlustfrei");

    const gelesen = await steuer.lies();
    expect(gelesen.type).toBe("table");
    expect(gelesen.data).toEqual({ content: [["A", "B"]] });
  });

  // ED07 -----------------------------------------------------------------
  it("ED07: ein Wechsel MIT Verlust wird gemeldet und wartet", async () => {
    const win = _ctx();
    // Der Stub kennt NUR 'content' - 'sonderfeld' ueberlebt sein save()
    // nicht. Genau das tut Editor.js mit einem Feld, das sein Werkzeug
    // nicht kennt: es verschwindet, OHNE Fehlermeldung.
    const { host, steuer } = _bau(win, ["content"]);
    steuer.setze("table", { content: [["A"]] });

    _modusBtn(host).click();
    await new Promise((r) => setTimeout(r, 0));
    // Im Rohmodus ein Feld ergaenzen, das kein Werkzeug kennt.
    _roh(host).value = JSON.stringify(
      { content: [["A"]], sonderfeld: "wichtig" });

    _modusBtn(host).click();
    await new Promise((r) => setTimeout(r, 0));

    // NICHT GESCHLUCKT, SONDERN GEMELDET.
    expect(_kasten(host).hidden).toBe(false);
    const text = _kasten(host).textContent;
    expect(text).toContain("sonderfeld");
    expect(text).toContain("entfällt");
    expect(text).toContain("wichtig");     // der Wert steht dabei
    expect(_meldung(host).textContent).toContain("NICHT verlustfrei");

    // 'Im Rohmodus bleiben' aendert NICHTS.
    host.querySelector(".aiw-mod-eing-zurueck").click();
    await new Promise((r) => setTimeout(r, 0));
    expect(steuer.modus()).toBe("roh");
    expect(JSON.parse(_roh(host).value).sonderfeld).toBe("wichtig");
    expect(_meldung(host).textContent).toContain("Nichts ist verändert");

    // Und der andere Weg: uebernehmen heisst uebernehmen, samt Verlust.
    _modusBtn(host).click();
    await new Promise((r) => setTimeout(r, 0));
    host.querySelector(".aiw-mod-eing-uebernehmen").click();
    await new Promise((r) => setTimeout(r, 0));
    const gelesen = await steuer.lies();
    expect(gelesen.data.sonderfeld).toBeUndefined();
    expect(gelesen.data.content).toEqual([["A"]]);
  });

  // ED07b ----------------------------------------------------------------
  it("ED07b: defektes JSON verhindert den Wechsel und sagt wo", async () => {
    const win = _ctx();
    const { host, steuer } = _bau(win, null);
    steuer.setze("paragraph", { text: "x" });

    _modusBtn(host).click();
    await new Promise((r) => setTimeout(r, 0));
    _roh(host).value = '{"text": "x",\n  "y" 1}';

    _modusBtn(host).click();
    await new Promise((r) => setTimeout(r, 0));

    // Der Wechsel findet NICHT statt - und die Meldung sagt, wo es klemmt.
    expect(steuer.modus()).toBe("roh");
    const m = _meldung(host).textContent;
    expect(m).toContain("Zeile 2");
    expect(m).toContain("Spalte");
  });

  // ED08 -----------------------------------------------------------------
  it("ED08: der Entwurfsrueckruf feuert", async () => {
    const win = _ctx();
    let n = 0;
    const { host, steuer } = _bau(win, null, { onChange: () => { n += 1; } });
    steuer.setze("paragraph", { text: "x" });

    // DIE BRUECKE ZUM ENTWURFSSPEICHER. cockpit_modules.js sichert bei
    // 'input'/'change' auf dem Formular - Editor.js erzeugt beides NICHT.
    // Ohne diesen Rueckruf setzte der Entwurf stillschweigend aus, und ein
    // Neuladen kostete die Arbeit. Genau die Art Fehler, die Build 575 am
    // Schluesselfeld gekostet hat.
    _modusBtn(host).click();
    await new Promise((r) => setTimeout(r, 0));
    const vorher = n;

    _roh(host).value = '{"text": "geaendert"}';
    _roh(host).dispatchEvent(new win.Event("input"));
    expect(n).toBeGreaterThan(vorher);

    host.querySelector(".aiw-mod-eing-format").click();
    expect(n).toBeGreaterThan(vorher + 1);
  });

  // ED08b ----------------------------------------------------------------
  it("ED08b: ohne Editor.js bleibt der Rohmodus der Weg", async () => {
    const win = _ctx();
    const host = win.document.getElementById("host");
    // Kein Konstruktor - weder ueber opts noch am Fenster.
    const steuer = win.AIWBausteinEingabe.erzeuge(host, { tools: {} });
    steuer.setze("paragraph", { text: "x" });

    // KEIN STILLER AUSFALL: die Flaeche sagt, was fehlt.
    const komfort = host.querySelector(".aiw-mod-eing-komfort");
    expect(komfort.textContent).toContain("editor.bundle.js");
    expect(komfort.className).toContain("ist-warnung");

    // Und der Rohmodus traegt weiter.
    _modusBtn(host).click();
    await new Promise((r) => setTimeout(r, 0));
    expect(steuer.modus()).toBe("roh");
    expect(JSON.parse(_roh(host).value)).toEqual({ text: "x" });
  });
});
