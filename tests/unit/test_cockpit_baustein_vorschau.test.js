/**
 * tests/unit/test_cockpit_baustein_vorschau.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite für Build 577: die Vorschau eines Textbausteins (Ticket 64edd18a).
 *
 * BV01 — blockAus baut aus dem Freitext einen Absatz und macht die Platzhalter
 *        zu Chips (der Chip-Renderer ist injizierbar).
 * BV02 — ohne Chip-Renderer bleibt der ROHTEXT stehen; die Vorschau fällt
 *        nicht aus, sie wird nur schlichter.
 * BV03 — ZUKUNFTSFEST: liegen block_type und block_data vor (ab Build 578),
 *        werden sie unverändert benutzt — die Vorschau muss dann nicht neu
 *        gebaut werden.
 * BV04 — fehlendeTeile NENNT die fehlende Datei, statt nur "geht nicht".
 * BV05 — werkzeuge() trägt nur ein, was das Bündel wirklich mitbringt; ein
 *        undefiniertes Werkzeug ließe Editor.js beim Start scheitern.
 * BV06 — fehlt ein Teil, sagt die Fläche das und baut KEINEN Editor.
 * BV07 — die Vorschau baut den Editor auf und übergibt readOnly:true.
 * BV08 — unveränderter Inhalt baut NICHT neu auf (kein Flackern beim Tippen).
 * BV09 — bei Änderung wird die alte Instanz ABGEBAUT (destroy), sonst sammeln
 *        sich Instanzen und Horcher an.
 * BV10 — wirft der Aufbau, wird das gemeldet und nicht verschluckt.
 *
 * Version: v0.8.577 · Build: 577 · 2026-07-30
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_baustein_vorschau.js", "utf-8");

function _api() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(_src);
  return { win: dom.window, api: dom.window.AIWBausteinVorschau };
}

/** Chip-Renderer wie in Baustelle 6: {{a:x}} -> <span class="ph-chip ...">x</span> */
const chips = {
  hydrateChips: (roh) => String(roh).replace(
    /\{\{a:([a-z_]+)\}\}/g,
    '<span class="ph-chip ph-chip-auto" data-chip-raw="{{a:$1}}">$1</span>'),
};

/** Minimal-Editor: merkt sich die Konfiguration, zählt destroy(). */
function _fakeEditor(protokoll) {
  return function (cfg) {
    protokoll.push(cfg);
    this.destroy = function () { protokoll.abbau = (protokoll.abbau || 0) + 1; };
  };
}

function _vollesFenster(win) {
  win.EditorJS = function () { this.destroy = function () {}; };
  win.EditorTools = { Paragraph: function () {}, Table: function () {} };
  win.PlaceholderChips = chips;
  return win;
}

describe("Bausteinvorschau (Build 577)", () => {
  // BV01 --------------------------------------------------------------------
  it("BV01: Freitext wird Absatz, Platzhalter werden Chips", () => {
    const { api } = _api();
    const b = api.blockAus({ body: "Guten Tag {{a:username}}." }, chips);
    expect(b.length).toBe(1);
    expect(b[0].type).toBe("paragraph");
    expect(b[0].data.text).toContain('class="ph-chip ph-chip-auto"');
    expect(b[0].data.text).toContain(">username<");
    // Der Rohtext bleibt im Chip erhalten — sonst waere die Rueckrichtung weg.
    expect(b[0].data.text).toContain('data-chip-raw="{{a:username}}"');
  });

  // BV02 --------------------------------------------------------------------
  it("BV02: ohne Chip-Renderer bleibt der Rohtext stehen", () => {
    const { api } = _api();
    const b = api.blockAus({ body: "Hallo {{a:username}}" }, null);
    expect(b[0].data.text).toBe("Hallo {{a:username}}");
    // Auch ein kaputter Renderer darf die Vorschau nicht kosten.
    const kaputt = { hydrateChips: () => { throw new Error("boom"); } };
    expect(api.blockAus({ body: "X {{a:y}}" }, kaputt)[0].data.text)
      .toBe("X {{a:y}}");
  });

  // BV03 --------------------------------------------------------------------
  it("BV03: vorhandene Blockdaten werden unveraendert benutzt", () => {
    const { api } = _api();
    const daten = { withHeadings: true,
                    content: [["Feld", "Wert"], ["Name", "{{a:username}}"]] };
    const b = api.blockAus({ block_type: "table", block_data: daten }, chips);
    expect(b.length).toBe(1);
    expect(b[0].type).toBe("table");
    // UNVERAENDERT: kein Chip-Durchlauf, keine Umformung. Ab Build 578 traegt
    // ein Baustein seine Blockdaten selbst; die Vorschau ist darauf schon
    // vorbereitet und muss nicht neu gebaut werden.
    expect(b[0].data).toBe(daten);
  });

  // BV04 --------------------------------------------------------------------
  it("BV04: fehlende Teile werden benannt", () => {
    const { api } = _api();
    expect(api.fehlendeTeile({})).toEqual([
      "editor.bundle.js (EditorJS)",
      "editor.bundle.js (EditorTools)",
      "placeholder_chips.js",
    ]);
    expect(api.fehlendeTeile({
      EditorJS: function () {}, EditorTools: {}, PlaceholderChips: chips,
    })).toEqual([]);
    // Halb geladen: nur das Fehlende wird genannt.
    expect(api.fehlendeTeile({ EditorJS: function () {}, EditorTools: {} }))
      .toEqual(["placeholder_chips.js"]);
  });

  // BV05 --------------------------------------------------------------------
  it("BV05: werkzeuge traegt nur ein, was das Buendel mitbringt", () => {
    const { api } = _api();
    const w = { EditorTools: { Paragraph: function () {},
                               Table: function () {} } };
    const t = api.werkzeuge(w);
    expect(Object.keys(t).sort()).toEqual(["paragraph", "table"]);
    expect(t.paragraph.class).toBe(w.EditorTools.Paragraph);
    // Ein undefiniertes Werkzeug liesse Editor.js beim Start scheitern -
    // deshalb steht es gar nicht in der Konfiguration.
    expect(t.header).toBeUndefined();
    expect(api.werkzeuge({})).toEqual({});
  });

  // BV06 --------------------------------------------------------------------
  it("BV06: fehlt ein Teil, sagt die Flaeche das und baut keinen Editor", () => {
    const { win, api } = _api();
    const host = win.document.createElement("div");
    win.document.body.appendChild(host);
    const vs = api.erzeuge(host, { win: {} });   // nichts geladen
    expect(vs.zeige({ body: "x" })).toBeNull();
    expect(vs.istOffen()).toBe(false);
    const m = host.querySelector(".aiw-mod-vorschau-meldung");
    expect(m.textContent).toContain("placeholder_chips.js");
    expect(m.className).toContain("ist-warnung");
  });

  // BV07 --------------------------------------------------------------------
  it("BV07: der Editor wird mit readOnly aufgebaut", () => {
    const { win, api } = _api();
    _vollesFenster(win);
    const host = win.document.createElement("div");
    win.document.body.appendChild(host);
    const prot = [];
    const vs = api.erzeuge(host, { win: win, chips: chips,
                                   EditorCtor: _fakeEditor(prot) });
    expect(vs.zeige({ body: "Guten Tag {{a:username}}." })).not.toBeNull();
    expect(prot.length).toBe(1);
    // Nur-Lese-Modus ist der Kern: die Vorschau darf nichts verändern.
    expect(prot[0].readOnly).toBe(true);
    expect(prot[0].data.blocks[0].data.text).toContain("ph-chip");
    expect(Object.keys(prot[0].tools)).toContain("paragraph");
  });

  // BV08 --------------------------------------------------------------------
  it("BV08: unveraenderter Inhalt baut nicht neu auf", () => {
    const { win, api } = _api();
    _vollesFenster(win);
    const host = win.document.createElement("div");
    win.document.body.appendChild(host);
    const prot = [];
    const vs = api.erzeuge(host, { win: win, chips: chips,
                                   EditorCtor: _fakeEditor(prot) });
    vs.zeige({ body: "gleich" });
    vs.zeige({ body: "gleich" });
    vs.zeige({ body: "gleich" });
    // Sonst flackerte die Vorschau bei jedem Tastendruck, auch ohne Aenderung.
    expect(prot.length).toBe(1);
  });

  // BV09 --------------------------------------------------------------------
  it("BV09: bei Aenderung wird die alte Instanz abgebaut", () => {
    const { win, api } = _api();
    _vollesFenster(win);
    const host = win.document.createElement("div");
    win.document.body.appendChild(host);
    const prot = [];
    const vs = api.erzeuge(host, { win: win, chips: chips,
                                   EditorCtor: _fakeEditor(prot) });
    vs.zeige({ body: "eins" });
    vs.zeige({ body: "zwei" });
    expect(prot.length).toBe(2);
    // Ohne destroy() sammeln sich Instanzen und Dokument-Horcher an.
    expect(prot.abbau).toBe(1);
    vs.aus();
    expect(prot.abbau).toBe(2);
    expect(vs.istOffen()).toBe(false);
  });

  // BV10 --------------------------------------------------------------------
  it("BV10: ein Fehler beim Aufbau wird gemeldet", () => {
    const { win, api } = _api();
    _vollesFenster(win);
    const host = win.document.createElement("div");
    win.document.body.appendChild(host);
    const vs = api.erzeuge(host, {
      win: win, chips: chips,
      EditorCtor: function () { throw new Error("Werkzeug fehlt"); },
    });
    expect(vs.zeige({ body: "x" })).toBeNull();
    const m = host.querySelector(".aiw-mod-vorschau-meldung");
    expect(m.textContent).toContain("Werkzeug fehlt");
    expect(m.className).toContain("ist-warnung");
  });
});
