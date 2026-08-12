/**
 * tests/unit/test_cockpit_baustein_blindfelder.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Baustein-Module (W1) — WERKZEUGBLINDE FELDER, Build 704
 *
 * Gegenstand: management/server/static/cockpit_baustein_eingabe.js
 *
 * ---------------------------------------------------------------------------
 * DER BEFUND, DER DAZU GEFUEHRT HAT
 * ---------------------------------------------------------------------------
 * Gemessen am 12.08.2026 am laufenden Bauteil mit dem echten Buendel: Ein
 * Zitatblock
 *     { "text": "...", "caption": "Vernehmung vom 03.04.2026",
 *       "alignment": "left" }
 * kam nach setze() -> lies() - also nach blossem OEFFNEN UND SPEICHERN, ohne
 * dass jemand etwas veraendert haette - zurueck als
 *     { "text": "...", "type": "quotationMark" }
 *
 * 'caption' und 'alignment' waren weg. Beide sind keine erfundenen Felder:
 * editor/html_renderer.py:127-151 rendert 'caption' als <cite> und
 * 'alignment' als Klasse; klartextAus() liest 'caption' ebenfalls, der
 * body-Spiegel schrumpfte also mit.
 *
 * URSACHE: das gebuendelte Zitatwerkzeug ist '@cychann/editorjs-quote'
 * (Datenmodell {text, type}), der Renderer ist auf '@editorjs/quote'
 * geschrieben (Datenmodell {text, caption, alignment}). Zwei Datenmodelle
 * fuer denselben Block. Die Zusammenfuehrung ist ein eigener Vorgang - HIER
 * geht es allein darum, dass nichts mehr lautlos verschwindet.
 *
 * WARUM DAS NICHT DER VERGLEICH AUS BUILD 656 ABGEFANGEN HAT: Der laeuft nur
 * beim Moduswechsel Roh -> Komfort. Der alltaegliche Weg - Datensatz
 * oeffnen, etwas ganz anderes aendern, speichern - lief ohne jeden Vergleich.
 *
 * ---------------------------------------------------------------------------
 * DAS VERFAHREN, DAS HIER GEPRUEFT WIRD
 * ---------------------------------------------------------------------------
 * Unmittelbar nach dem Aufbau des Editors - BEVOR ein Mensch etwas anfassen
 * konnte - wird er sofort wieder ausgelesen und mit den geladenen Daten
 * verglichen. Was in dieser Sekunde schon fehlt, kann das Werkzeug nicht
 * halten: es ist WERKZEUGBLIND. Nur diese Felder werden spaeter beim Lesen
 * zurueckgeschrieben.
 *
 * DER MESSZEITPUNKT IST DER GANZE TRICK, und BF05 ist der Fall, der ihn
 * rechtfertigt: Loescht der Bearbeiter spaeter den zweiten Punkt einer
 * Aufzaehlung, fehlt 'items.1' EBENSO. Ein pauschales Zurueckschreiben
 * wuerde ihn wieder auferstehen lassen - aus einem Datenverlust wuerde eine
 * Datenfaelschung. Die Messung vor der ersten Eingabe trennt beides: sie
 * sieht nur, was das WERKZEUG nicht kann, nie das, was der MENSCH wollte.
 *
 * ---------------------------------------------------------------------------
 * Testfaelle
 * ---------------------------------------------------------------------------
 *   BF01 — blindeFelderAus nimmt NUR Entfallenes; Ergaenzungen des Werkzeugs
 *          (table.stretched, delimiter.style) und Umformungen bleiben aussen
 *          vor. Bewahrt wird, was fehlt - nicht, was dazukommt.
 *   BF02 — setzeNachPfad: Feld setzen, verschachtelt setzen, ans Listenende
 *          anfuegen.
 *   BF03 — setzeNachPfad schlaegt NIE still fehl: fehlendes Zwischenglied,
 *          belegtes Feld, Listenplatz mitten drin - jedes Mal mit Grund.
 *   BF04 — DER KERNFALL: ein Feld, das das Werkzeug nicht halten kann,
 *          ueberlebt setze() -> lies() und wird als 'bewahrt' ausgewiesen.
 *   BF05 — DIE GRENZE: was der BEARBEITER nach der Messung entfernt, wird
 *          NICHT zurueckgeschrieben. Sonst waere aus dem Schutz eine
 *          Faelschung geworden.
 *   BF06 — die Blockart wechselt: die Messung der alten Art wird nicht auf
 *          die neue angewandt.
 *   BF07 — schnelles Speichern direkt nach dem Oeffnen wartet die Messung ab
 *          (und liefert nicht den geladenen Stand statt des Editorstands).
 *   BF08 — schlaegt die Messung fehl, wird das GESAGT und nichts bewahrt.
 *   BF09 — der Rohmodus braucht keine Bewahrung und meldet auch keine.
 *   BF10 — AM ECHTEN BUENDEL: der Zitatfall aus dem Befund oben, mit
 *          editor.bundle.js statt einem Stub. Der einzige Fall hier, der
 *          anschlagen wuerde, wenn das Buendel getauscht wird.
 *
 * Version: 0.1.0 · Build: 704 · 2026-08-12
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
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

/**
 * Ein Editor-Stub, dessen save() sich von Aufruf zu Aufruf UNTERSCHEIDEN
 * kann. Genau das braucht BF05: der erste Aufruf ist die Blindprobe, der
 * zweite steht fuer den Stand nach einer Bearbeitung. Ein Stub mit
 * immergleicher Antwort koennte die entscheidende Grenze nicht abbilden.
 *
 * antworten: Funktion (daten, nummer) -> Daten fuer diesen save()-Aufruf.
 */
function _stubCtor(antworten, opt) {
  const o = opt || {};
  return function Stub(cfg) {
    const b = (cfg.data && cfg.data.blocks && cfg.data.blocks[0]) || {};
    this._type = b.type || "paragraph";
    this._data = b.data || {};
    this._n = 0;
    this.isReady = o.isReadyFehlt ? undefined : Promise.resolve();
    const self = this;
    const save = function () {
      self._n += 1;
      if (o.saveWirft) { return Promise.reject(new Error("kaputt")); }
      return Promise.resolve({ blocks: [{
        type: self._type,
        data: antworten(self._data, self._n),
      }] });
    };
    // saveSpaeter bildet Editor.js 2.31.6 nach: save() wird erst NACH
    // isReady angehaengt. Ohne diesen Fall bliebe unbemerkt, dass eine
    // Pruefung auf save() vor dem Warten die Messung ueberspringt.
    if (o.saveSpaeter) { this.isReady.then(() => { self.save = save; }); }
    else { this.save = save; }
    this.destroy = () => { self._zerstoert = true; };
  };
}

function _bau(win, antworten, opt) {
  const host = win.document.getElementById("host");
  const steuer = win.AIWBausteinEingabe.erzeuge(host, {
    EditorCtor: _stubCtor(antworten, opt), tools: {},
  });
  return { host, steuer, api: win.AIWBausteinEingabe };
}
const _meldung = (host) => host.querySelector(".aiw-mod-eing-meldung");
const _tick = () => new Promise((r) => setTimeout(r, 0));

describe("Blindfelder — die reinen Funktionen (Build 704)", () => {
  // BF01 -------------------------------------------------------------------
  it("BF01: blindeFelderAus nimmt nur Entfallenes", () => {
    const api = _ctx().AIWBausteinEingabe;

    // Der gemessene Zitatfall: zwei Felder weg, eines dazu.
    expect(api.blindeFelderAus(
      { text: "T", caption: "C", alignment: "left" },
      { text: "T", type: "quotationMark" }))
      .toEqual([{ pfad: "alignment", wert: "left" },
                { pfad: "caption", wert: "C" }]);

    // Reine Ergaenzungen des Werkzeugs sind KEINE Blindheit - table.stretched
    // und delimiter.style sind beide am echten Buendel gemessen.
    expect(api.blindeFelderAus(
      { withHeadings: true, content: [["a"]] },
      { withHeadings: true, stretched: false, content: [["a"]] })).toEqual([]);
    expect(api.blindeFelderAus({}, { style: "star" })).toEqual([]);

    // Eine Umformung ebenfalls nicht: ob sie gewollt war, weiss nur ein
    // Mensch - deshalb meldet sie der Vergleich, statt sie zu heilen.
    expect(api.blindeFelderAus({ level: 2 }, { level: 3 })).toEqual([]);

    // Verschachtelt wird der Pfad mitgefuehrt, sonst waere die Meldung
    // wertlos und das Zurueckschreiben unmoeglich.
    expect(api.blindeFelderAus(
      { a: { b: 1, c: 2 } }, { a: { b: 1 } }))
      .toEqual([{ pfad: "a.c", wert: 2 }]);
  });

  // BF02 -------------------------------------------------------------------
  it("BF02: setzeNachPfad legt Werte ab, auch verschachtelt und in Listen",
    () => {
      const api = _ctx().AIWBausteinEingabe;

      const flach = { text: "T" };
      expect(api.setzeNachPfad(flach, "caption", "C")).toEqual({ ok: true });
      expect(flach).toEqual({ text: "T", caption: "C" });

      const tief = { a: { b: 1 } };
      expect(api.setzeNachPfad(tief, "a.c", 2).ok).toBe(true);
      expect(tief).toEqual({ a: { b: 1, c: 2 } });

      // In einer Liste ist der Pfad ein Index; angefuegt wird am ENDE.
      const liste = { items: ["x"] };
      expect(api.setzeNachPfad(liste, "items.1", "y").ok).toBe(true);
      expect(liste.items).toEqual(["x", "y"]);
    });

  // BF03 -------------------------------------------------------------------
  it("BF03: setzeNachPfad schlaegt nie still fehl", () => {
    const api = _ctx().AIWBausteinEingabe;

    // Fehlendes Zwischenglied wird NICHT angelegt: ein Werkzeug, das ein
    // ganzes Unterobjekt fallen laesst, hat den Block umgebaut - dort etwas
    // einzuhaengen hiesse raten.
    const ohne = { text: "T" };
    const e1 = api.setzeNachPfad(ohne, "a.b", 1);
    expect(e1.ok).toBe(false);
    expect(e1.grund).toContain("fehlt");
    expect(ohne).toEqual({ text: "T" });      // unangetastet

    // Was der Editor liefert, hat Vorrang vor dem Bewahrten.
    const belegt = { caption: "neu" };
    const e2 = api.setzeNachPfad(belegt, "caption", "alt");
    expect(e2.ok).toBe(false);
    expect(e2.grund).toContain("bereits belegt");
    expect(belegt.caption).toBe("neu");

    // Mitten in eine Liste einzufuegen wuerde die Reihenfolge der uebrigen
    // Eintraege verschieben - und in einer Tabellenzeile ist die Reihenfolge
    // bedeutungstragend.
    const liste = { items: ["x", "y", "z"] };
    const e3 = api.setzeNachPfad(liste, "items.1", "neu");
    expect(e3.ok).toBe(false);
    expect(e3.grund).toContain("nicht das Ende");
    expect(liste.items).toEqual(["x", "y", "z"]);

    // Unbrauchbare Pfade ebenfalls mit Grund, nicht mit einer Ausnahme.
    expect(api.setzeNachPfad({}, "", 1).ok).toBe(false);
    expect(api.setzeNachPfad({}, "(Wurzel)", 1).ok).toBe(false);
    expect(api.setzeNachPfad({ l: [] }, "l.nixzahl", 1).grund)
      .toContain("kein Listenindex");
  });
});

describe("Blindfelder — am Bauteil (Build 704)", () => {
  // BF04 -------------------------------------------------------------------
  it("BF04: ein werkzeugblindes Feld ueberlebt setze -> lies", async () => {
    const win = _ctx();
    // Ein Werkzeug wie @cychann/editorjs-quote: 'caption' faellt weg,
    // 'type' kommt dazu.
    const { host, steuer } = _bau(win,
      (d) => ({ text: d.text, type: "quotationMark" }));

    steuer.setze("quote", { text: "Der Zeuge sagte aus.",
                            caption: "Vernehmung vom 03.04.2026" });
    await _tick();

    // Der Bearbeiter erfaehrt es, BEVOR er speichert - stillschweigend
    // bewahren waere die andere Haelfte desselben Fehlers.
    expect(_meldung(host).textContent).toContain("caption");
    expect(_meldung(host).textContent).toContain("Rohmodus");

    const g = await steuer.lies();
    expect(g.data.caption).toBe("Vernehmung vom 03.04.2026");
    expect(g.data.text).toBe("Der Zeuge sagte aus.");
    expect(g.data.type).toBe("quotationMark");      // die Ergaenzung bleibt
    expect(g.bewahrt.map((f) => f.pfad)).toEqual(["caption"]);
    expect(g.nichtBewahrt).toEqual([]);

    // Und der body-Spiegel schrumpft dadurch nicht mehr mit.
    const api = win.AIWBausteinEingabe;
    expect(api.klartextAus("quote", g.data, null))
      .toBe("Der Zeuge sagte aus.\nVernehmung vom 03.04.2026");
  });

  // BF05 -------------------------------------------------------------------
  it("BF05: was der Bearbeiter entfernt, kehrt NICHT zurueck", async () => {
    const win = _ctx();
    // Erster save() = Blindprobe: das Werkzeug haelt beide Punkte, es ist
    // also fuer nichts blind. Zweiter save() = nach der Bearbeitung: der
    // zweite Punkt ist weg, WEIL DER MENSCH ihn geloescht hat.
    const { steuer } = _bau(win, (d, n) => (n === 1
      ? d
      : { style: d.style, items: [d.items[0]] }));

    steuer.setze("list", { style: "unordered",
                           items: [{ content: "A" }, { content: "B" }] });
    await _tick();

    const g = await steuer.lies();
    // DIE ENTSCHEIDENDE ZEILE DIESER DATEI: aus einem Datenverlust darf
    // keine Datenfaelschung werden.
    expect(g.data.items).toEqual([{ content: "A" }]);
    expect(g.bewahrt).toEqual([]);
    expect(g.nichtBewahrt).toEqual([]);
  });

  // BF06 -------------------------------------------------------------------
  //
  // Wozu die Blockart ueberhaupt mitgefuehrt wird: Editor.js kann einen Block
  // unter einer ANDEREN Art zurueckgeben, als er gebaut wurde - der
  // Bearbeiter kann die Art im Editor selbst umstellen, und ein unbekannter
  // Typ wird von Editor.js umgedeutet. Die gemessenen Felder gehoerten dann
  // zum Werkzeug der alten Art. Sie in den neuen Block zu heben ergaebe einen
  // Block, den so nie jemand geschrieben hat - eine dritte Fassung, weder die
  // gespeicherte noch die bearbeitete.
  it("BF06: kommt der Block unter anderer Blockart zurueck, wird nichts "
    + "zurueckgeschrieben", async () => {
      const win = _ctx();
      // Erster save() (Blindprobe): noch 'quote', 'caption' faellt weg.
      // Zweiter save(): der Block kommt als 'header' zurueck.
      const host = win.document.getElementById("host");
      const steuer = win.AIWBausteinEingabe.erzeuge(host, {
        tools: {},
        EditorCtor: function Stub(cfg) {
          const b = (cfg.data && cfg.data.blocks && cfg.data.blocks[0]) || {};
          const daten = b.data || {};
          let n = 0;
          this.isReady = Promise.resolve();
          this.save = () => {
            n += 1;
            return Promise.resolve({ blocks: [{
              type: n === 1 ? "quote" : "header",
              data: { text: daten.text },
            }] });
          };
          this.destroy = () => {};
        },
      });

      steuer.setze("quote", { text: "T", caption: "C" });
      await _tick();
      // Die Messung hat 'caption' sehr wohl gefunden ...
      expect(_meldung(host).textContent).toContain("caption");

      const g = await steuer.lies();
      // ... aber sie wird auf den header-Block NICHT angewandt.
      expect(g.type).toBe("header");
      expect(g.data.caption).toBeUndefined();
      expect(g.bewahrt).toEqual([]);
      expect(g.nichtBewahrt).toEqual([]);
    });

  // BF07 -------------------------------------------------------------------
  it("BF07: Speichern direkt nach dem Oeffnen wartet die Messung ab",
    async () => {
      const win = _ctx();
      // saveSpaeter: save() wird erst NACH isReady angehaengt - so verhaelt
      // sich Editor.js 2.31.6 wirklich. Bis Build 704 pruefte das Bauteil
      // auf save() VOR dem Warten und lieferte dann den GELADENEN Stand
      // zurueck statt des Editorstands. Das fiel nicht auf, weil beide
      // meist gleich sind - aber eben nur meist.
      const { steuer } = _bau(win,
        (d) => ({ text: d.text + " (aus dem Editor)" }),
        { saveSpaeter: true });

      steuer.setze("paragraph", { text: "geladen" });
      // KEIN Abwarten - genau der eilige Fall.
      const g = await steuer.lies();
      expect(g.data.text).toBe("geladen (aus dem Editor)");
    });

  // BF08 -------------------------------------------------------------------
  it("BF08: eine fehlgeschlagene Messung wird gesagt, nicht verschwiegen",
    async () => {
      const win = _ctx();
      const { host, steuer } = _bau(win, (d) => d, { saveWirft: true });

      steuer.setze("quote", { text: "T", caption: "C" });
      await _tick();
      await _tick();

      // Wer sich faelschlich fuer geschuetzt haelt, sieht nicht nach.
      expect(_meldung(host).textContent).toContain("fehlgeschlagen");
      expect(_meldung(host).textContent).toContain("Rohmodus");
      expect(_meldung(host).className).toContain("ist-fehler");
    });

  // BF09 -------------------------------------------------------------------
  it("BF09: der Rohmodus braucht keine Bewahrung", async () => {
    const win = _ctx();
    const { host, steuer } = _bau(win, (d) => ({ text: d.text }));

    steuer.setze("quote", { text: "T", caption: "C" });
    await _tick();
    host.querySelector(".aiw-mod-eing-modus").click();   // -> Rohmodus
    await _tick();

    // Das Textfeld haelt alle Felder - auch die bewahrten. Nur so ist das
    // bewahrte Feld ueberhaupt aenderbar; genau darauf verweist die Meldung.
    expect(JSON.parse(host.querySelector(".aiw-mod-eing-roh").value).caption)
      .toBe("C");

    const g = await steuer.lies();
    expect(g.data.caption).toBe("C");
    expect(g.bewahrt).toEqual([]);
    expect(g.nichtBewahrt).toEqual([]);
  });
});

describe("Blindfelder — am echten Buendel (Build 704)", () => {
  // BF10 -------------------------------------------------------------------
  //
  // Alle Faelle oben fahren einen Stub, weil sich nur so gezielt herstellen
  // laesst, was geprueft werden soll. Dieser eine Fall fuehrt das ECHTE
  // editor.bundle.js - er ist der Grund, warum der Befund ueberhaupt gefunden
  // wurde, und der einzige hier, der anschlaegt, wenn das Buendel getauscht
  // oder das Zitatwerkzeug ausgewechselt wird.
  it("BF10: der gemessene Zitatfall, mit editor.bundle.js", async () => {
    const bundle = readFileSync("static/editor/editor.bundle.js", "utf-8");
    const dom = new JSDOM(
      "<!DOCTYPE html><html><body><div id='host'></div></body></html>",
      { runScripts: "outside-only", pretendToBeVisual: true,
        url: "http://localhost" });
    const w = dom.window;
    // Editor.js braucht ein paar Browserbauteile, die jsdom nicht mitbringt.
    w.matchMedia = w.matchMedia
      || (() => ({ matches: false, addListener() {}, removeListener() {} }));
    if (!w.Range.prototype.getBoundingClientRect) {
      w.Range.prototype.getBoundingClientRect = () => ({
        top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 });
    }
    if (!w.Range.prototype.getClientRects) {
      w.Range.prototype.getClientRects = () => [];
    }
    w.FORENSIC_DEBUG = false;
    ["warn", "error", "log"].forEach((k) => { w.console[k] = () => {}; });

    w.eval(bundle);
    w.eval(readFileSync(
      "management/server/static/cockpit_baustein_vorschau.js", "utf-8"));
    w.eval(_chips);
    w.eval(_src);

    const host = w.document.getElementById("host");
    const steuer = w.AIWBausteinEingabe.erzeuge(host, {});

    const ausDerDatenbank = { text: "Der Zeuge sagte aus.",
                              caption: "Vernehmung vom 03.04.2026",
                              alignment: "left" };
    steuer.setze("quote", ausDerDatenbank);
    await new Promise((r) => setTimeout(r, 400));

    const g = await steuer.lies();
    // GENAU DIE BEIDEN FELDER AUS DEM BEFUND.
    expect(g.data.caption).toBe("Vernehmung vom 03.04.2026");
    expect(g.data.alignment).toBe("left");
    expect(g.bewahrt.map((f) => f.pfad).sort())
      .toEqual(["alignment", "caption"]);
    expect(g.nichtBewahrt).toEqual([]);

    // Gegenprobe, damit dieser Fall nicht bloss "irgendwas ist gleich"
    // prueft: OHNE die Bewahrung waere genau das hier verloren.
    expect(w.AIWBausteinEingabe.tiefVergleich(ausDerDatenbank, g.data)
      .filter((u) => u.art === "entfallen")).toEqual([]);
  }, 20000);
});
