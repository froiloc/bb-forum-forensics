/**
 * tests/unit/test_cockpit_vorlage_vorschau.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Dokumentvorlagen
 * VORSCHAU einer ganzen Vorlage, Build 705
 *
 * Gegenstand: management/server/static/cockpit_vorlage_vorschau.js
 * Ticket b47ce019 ("Schritt 3"), Teil 1 von 2 — nur die VORSCHAU; die
 * Eingabe folgt in einem eigenen Build.
 *
 * ---------------------------------------------------------------------------
 * WAS HIER GEPRUEFT WIRD UND WAS NICHT
 * ---------------------------------------------------------------------------
 * Die Vorschau ist schreibgeschuetzt: sie liest nichts zurueck und kann
 * folglich nichts verlieren. Geprueft wird deshalb nicht die Datentreue eines
 * Rueckwegs (den gibt es nicht), sondern:
 *   - dass die Umbenennung block_type -> type VERLUSTFREI ist (VV01),
 *   - dass kein Block still ausgelassen wird (VV02, VV03),
 *   - dass die Meldung ueber der Flaeche die richtigen Bloecke nennt und
 *     die richtige Sorge ausraeumt (VV04-VV06),
 *   - dass ein Ausfall GESAGT wird, statt als leere Vorlage auszusehen
 *     (VV07, VV08).
 * VV09 faehrt das echte Buendel.
 *
 * ---------------------------------------------------------------------------
 * Testfaelle
 * ---------------------------------------------------------------------------
 *   VV01 — bloeckeAus benennt nur um; block_data geht als DASSELBE Objekt
 *          weiter, nicht als Kopie.
 *   VV02 — ein Block ohne Art wird NICHT uebersprungen (Grundregel 1).
 *   VV03 — die Blockzahl bleibt gleich; aus n Bloecken werden n.
 *   VV04 — nichtDarstellbare zaehlt ab 1 und nennt die Art.
 *   VV05 — 'marker' STEHT in der Werkzeugliste (Inline-Werkzeug) und gilt
 *          trotzdem als nicht darstellbar. Ohne diese Unterscheidung meldete
 *          die Vorschau Entwarnung fuer genau den Fall, wegen dem es sie gibt.
 *   VV06 — meldungText: Einzahl/Mehrzahl, und die Entwarnung steht im
 *          SELBEN Satz wie der Befund.
 *   VV07 — fehlt eine geteilte Datei, wird sie GENANNT und kein Editor gebaut.
 *   VV08 — eine leere Vorlage sagt, dass sie leer ist, statt leer auszusehen.
 *   VV09 — AM ECHTEN BUENDEL: eine Vorlage mit allen neun Blockarten wird
 *          aufgebaut, 'evidence' bekommt den deutschen Platzhalter, und die
 *          Meldung nennt genau die nicht darstellbaren Bloecke.
 *
 * Version: 0.1.0 · Build: 705 · 2026-08-12
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _vorschau = readFileSync(
  "management/server/static/cockpit_baustein_vorschau.js", "utf-8");
const _unbek = readFileSync(
  "management/server/static/cockpit_unbekannter_block.js", "utf-8");
const _src = readFileSync(
  "management/server/static/cockpit_vorlage_vorschau.js", "utf-8");

function _ctx() {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body><div id='h'></div></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(_unbek);
  dom.window.eval(_vorschau);
  dom.window.eval(_src);
  return dom.window;
}
const _meld = (w) => w.document.querySelector(".aiw-dtpl-vorschau-meldung");

/** Ein Editor-Stub, der nur festhaelt, womit er gebaut wurde. */
function _stub() {
  const gesehen = [];
  function Stub(cfg) { gesehen.push(cfg); this.destroy = () => {}; }
  return { Stub, gesehen };
}

describe("Vorlagenvorschau — reine Funktionen (Build 705)", () => {
  // VV01 -------------------------------------------------------------------
  it("VV01: bloeckeAus benennt nur um, block_data bleibt dasselbe Objekt", () => {
    const api = _ctx().AIWVorlagenVorschau;
    const daten = { withHeadings: false, content: [["a", "b"]] };
    const raus = api.bloeckeAus([{ block_type: "table", block_data: daten }]);

    expect(raus).toEqual([{ type: "table", data: daten }]);
    // IDENTITAET: eine Kopie waere die Stelle, an der ein Feld unbemerkt
    // normalisiert werden koennte. Diese Vorschau soll ANZEIGEN, nicht
    // anfassen.
    expect(raus[0].data).toBe(daten);
  });

  // VV02 -------------------------------------------------------------------
  it("VV02: ein Block ohne Art wird nicht uebersprungen", () => {
    const api = _ctx().AIWVorlagenVorschau;
    const raus = api.bloeckeAus([
      { block_type: "paragraph", block_data: { text: "a" } },
      { block_data: { text: "ohne Art" } },
      { block_type: null, block_data: { text: "null" } },
    ]);
    // Grundregel 1: eine Luecke im Aufbau der Vorlage darf nicht durch
    // Weglassen verschwinden - sie wird sichtbar und zaehlbar.
    expect(raus.length).toBe(3);
    expect(raus[1].type).toBe("");
    expect(raus[2].type).toBe("");
    expect(raus[1].data).toEqual({ text: "ohne Art" });
  });

  // VV03 -------------------------------------------------------------------
  it("VV03: aus n Bloecken werden n — auch bei kaputten Eintraegen", () => {
    const api = _ctx().AIWVorlagenVorschau;
    expect(api.bloeckeAus([{}, null, { block_type: "header" }]).length).toBe(3);
    expect(api.bloeckeAus([]).length).toBe(0);
    expect(api.bloeckeAus(null).length).toBe(0);
    // block_data, das kein Objekt ist, wird zu {} - aber der Block bleibt.
    expect(api.bloeckeAus([{ block_type: "x", block_data: "kaputt" }]))
      .toEqual([{ type: "x", data: {} }]);
  });

  // VV04 -------------------------------------------------------------------
  it("VV04: nichtDarstellbare zaehlt ab 1 und nennt die Art", () => {
    const api = _ctx().AIWVorlagenVorschau;
    const liste = [
      { type: "paragraph" }, { type: "evidence" }, { type: "" },
    ];
    const f = api.nichtDarstellbare(liste, ["paragraph", "evidence"],
                                    ["evidence"]);
    // Der Redakteur zaehlt seine Bloecke von oben, nicht ab null.
    expect(f).toEqual([
      { nummer: 2, art: "evidence" },
      { nummer: 3, art: "(ohne Art)" },
    ]);
  });

  // VV05 -------------------------------------------------------------------
  it("VV05: 'marker' steht in der Werkzeugliste und gilt trotzdem als "
    + "nicht darstellbar", () => {
      const api = _ctx().AIWVorlagenVorschau;
      const liste = [{ type: "marker" }];
      // 'marker' IST registriert - aber als INLINE-Werkzeug. Ein BLOCK
      // dieser Art faellt auf den eingebauten Ersatz von Editor.js.
      // OHNE die Ersatzliste saehe er darstellbar aus:
      expect(api.nichtDarstellbare(liste, ["marker"], [])).toEqual([]);
      // MIT ihr wird er genannt - und nur so erfaehrt der Redakteur, warum
      // dort ein englischer Satz steht.
      expect(api.nichtDarstellbare(liste, ["marker"], ["marker"]))
        .toEqual([{ nummer: 1, art: "marker" }]);
    });

  // VV06 -------------------------------------------------------------------
  it("VV06: meldungText unterscheidet Einzahl und Mehrzahl und entwarnt", () => {
    const api = _ctx().AIWVorlagenVorschau;
    expect(api.meldungText([])).toBe("");
    expect(api.meldungText(null)).toBe("");

    const eins = api.meldungText([{ nummer: 5, art: "evidence" }]);
    expect(eins).toContain("Ein Block lässt sich");
    expect(eins).toContain("Block 5 («evidence»)");

    const viele = api.meldungText([{ nummer: 1, art: "evidence" },
                                   { nummer: 4, art: "marker" }]);
    expect(viele).toContain("2 Blöcke lassen sich");

    // DIE ENTWARNUNG GEHOERT IN DENSELBEN SATZ. Der graue Ersatzblock wird
    // sonst als Datenverlust gelesen - das ist die einzige Sorge, die er
    // ausloest, und die einzige, die dieser Text ausraeumen muss.
    for (const t of [eins, viele]) {
      expect(t).toContain("vollständig vorhanden");
      expect(t).toContain("gespeichert");
    }
  });
});

describe("Vorlagenvorschau — am Bauteil (Build 705)", () => {
  // VV07 -------------------------------------------------------------------
  it("VV07: eine fehlende geteilte Datei wird genannt, kein Editor gebaut",
    () => {
      const win = _ctx();
      const { Stub, gesehen } = _stub();
      // Kein EditorJS, kein PlaceholderChips im Fenster -> fehlendeTeile()
      // der Bausteinvorschau meldet sie.
      const st = win.AIWVorlagenVorschau.erzeuge(
        win.document.getElementById("h"), { EditorCtor: Stub, win: win });
      const erg = st.zeige([{ block_type: "paragraph", block_data: { text: "a" } }]);

      expect(erg).toBeNull();
      expect(gesehen.length).toBe(0);
      // KEIN STILLER AUSFALL: die fehlende Datei steht da. Eine leere
      // Flaeche saehe wie eine leere Vorlage aus.
      expect(_meld(win).textContent).toContain("es fehlt");
      expect(_meld(win).textContent).toContain("EditorJS");
      expect(st.istOffen()).toBe(false);
    });

  // VV08 -------------------------------------------------------------------
  it("VV08: eine leere Vorlage sagt, dass sie leer ist", () => {
    const win = _ctx();
    const { Stub, gesehen } = _stub();
    // Die geteilten Teile vortaeuschen, damit fehlendeTeile() zufrieden ist.
    win.EditorJS = Stub;
    win.EditorTools = {};
    win.PlaceholderChips = { hydrateChips: function (s) { return s; } };

    const st = win.AIWVorlagenVorschau.erzeuge(
      win.document.getElementById("h"), { EditorCtor: Stub, win: win });
    st.zeige([]);

    expect(gesehen.length).toBe(0);
    expect(_meld(win).textContent).toContain("keinen Block");
    expect(st.istOffen()).toBe(false);
  });
});

describe("Vorlagenvorschau — am echten Buendel (Build 705)", () => {
  // VV09 -------------------------------------------------------------------
  //
  // Alle Faelle oben fahren Stubs, weil sich nur so gezielt herstellen laesst,
  // was zu pruefen ist. Dieser eine fuehrt das ECHTE editor.bundle.js - er ist
  // der einzige, der anschlaegt, wenn das Buendel getauscht wird oder ein
  // Werkzeug daraus verschwindet.
  it("VV09: eine Vorlage mit allen neun Blockarten, mit editor.bundle.js",
    async () => {
      const dom = new JSDOM(
        "<!DOCTYPE html><html><body><div id='h'></div></body></html>",
        { runScripts: "outside-only", pretendToBeVisual: true,
          url: "http://localhost" });
      const w = dom.window;
      w.matchMedia = w.matchMedia
        || (() => ({ matches: false, addListener() {}, removeListener() {} }));
      if (!w.Range.prototype.getBoundingClientRect) {
        w.Range.prototype.getBoundingClientRect = () => ({
          top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 });
      }
      if (!w.Range.prototype.getClientRects) {
        w.Range.prototype.getClientRects = () => [];
      }
      ["warn", "error", "log"].forEach((k) => { w.console[k] = () => {}; });

      w.eval(readFileSync("static/editor/editor.bundle.js", "utf-8"));
      w.eval(readFileSync("userinfo/placeholder_chips.js", "utf-8"));
      w.eval(_unbek);
      w.eval(_vorschau);
      w.eval(_src);

      const vorlage = [
        { block_type: "paragraph", block_data: { text: "Nutzer {{a:user.username}}" } },
        { block_type: "header",    block_data: { text: "Abschnitt", level: 3 } },
        { block_type: "list",      block_data: { style: "unordered",
                                                 items: [{ content: "A", items: [] }] } },
        { block_type: "table",     block_data: { withHeadings: false,
                                                 content: [["a", "b"]] } },
        { block_type: "quote",     block_data: { text: "Zitat" } },
        { block_type: "image",     block_data: { url: "kopf.png", caption: "Briefkopf" } },
        { block_type: "delimiter", block_data: {} },
        { block_type: "marker",    block_data: { text: "Marker als Block" } },
        { block_type: "evidence",  block_data: { evidence_ids: [], group_label: "Belege" } },
      ];

      const st = w.AIWVorlagenVorschau.erzeuge(
        w.document.getElementById("h"), {});
      st.zeige(vorlage);
      await new Promise((r) => setTimeout(r, 400));

      expect(st.istOffen()).toBe(true);

      // GENAU ZWEI Blockarten sind nicht darstellbar - und die Meldung nennt
      // beide mit ihrer Nummer.
      const m = w.document.querySelector(".aiw-dtpl-vorschau-meldung").textContent;
      expect(m).toContain("2 Blöcke lassen sich");
      expect(m).toContain("Block 8 («marker»)");
      expect(m).toContain("Block 9 («evidence»)");
      expect(m).toContain("vollständig vorhanden");

      // 'evidence' bekommt den DEUTSCHEN Platzhalter, nicht den englischen
      // Ersatz von Editor.js. Das ist der sichtbare Zweck dieses Builds.
      const rumpf = w.document.querySelector(".aiw-dtpl-vorschau-rumpf");
      expect(rumpf.textContent).toContain("Blockart «evidence»");
      expect(rumpf.querySelector(".aiw-unbekannter-block")).not.toBeNull();

      // Und der Inhalt der darstellbaren Bloecke steht wirklich da.
      expect(rumpf.textContent).toContain("{{a:user.username}}");
      expect(rumpf.textContent).toContain("Abschnitt");
    }, 20000);
});
