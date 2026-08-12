/**
 * tests/unit/test_cockpit_unbekannter_block.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * ERSATZWERKZEUG fuer Blockarten ohne echtes Werkzeug, Build 705
 *
 * Gegenstand: management/server/static/cockpit_unbekannter_block.js
 * Ticket b47ce019 ("Schritt 3"), Teil 1 von 2.
 *
 * ---------------------------------------------------------------------------
 * WARUM ES DIESES WERKZEUG GIBT
 * ---------------------------------------------------------------------------
 * Dokumentvorlagen duerfen neun Blockarten fuehren (report_source.py:59-62).
 * Fuer 'evidence' bringt das Buendel kein Werkzeug mit; Editor.js setzt dann
 * seinen eigenen Ersatz und schreibt "The block can not be displayed
 * correctly." - englisch, ohne die Blockart zu nennen, und ohne zu sagen, ob
 * der Inhalt noch da ist.
 *
 * GEMESSEN am 12.08.2026 (Editor.js 2.31.6): der Inhalt IST noch da, alle
 * Daten kamen byteweise identisch zurueck. Die naheliegende Vermutung beim
 * Anblick des Ersatzblocks ist also die falsche - und genau das ist der
 * Schaden, den dieses Werkzeug behebt.
 *
 * PRAEZEDENZFALL: UnknownBlock in editor/html_renderer.py:206-226 rendert
 * '[Block-Typ: <typ>]' statt still zu verwerfen. Dieselbe Haltung.
 *
 * ---------------------------------------------------------------------------
 * Testfaelle
 * ---------------------------------------------------------------------------
 *   UB01 — der Text NENNT die Blockart und beantwortet die drei Fragen:
 *          was ist das, ist mein Inhalt weg, wie aendere ich es.
 *   UB02 — eine fehlende Blockart faellt nicht durch: 'unbekannt' statt einer
 *          Luecke im Satz.
 *   UB03 — DIE EIGENTLICHE ZUSICHERUNG: save() gibt die Daten UNVERAENDERT
 *          und als DASSELBE Objekt zurueck - keine Kopie, in der ein Feld
 *          normalisiert werden koennte.
 *   UB04 — validate() sagt 'true'. Ohne diese Zusage wuerfe Editor.js den
 *          Block als leer weg - ausgerechnet das Werkzeug gegen den Verlust
 *          loeste ihn aus.
 *   UB05 — render() erzeugt den Platzhalter ueber textContent (multilingual,
 *          XSS-sicher) und traegt die Blockart als data-Attribut.
 *
 * Version: 0.1.0 · Build: 705 · 2026-08-12
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_unbekannter_block.js", "utf-8");

function _ctx() {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(_src);
  return dom.window;
}

describe("Ersatzwerkzeug fuer unbekannte Blockarten (Build 705)", () => {
  // UB01 -------------------------------------------------------------------
  it("UB01: der Text nennt die Blockart und beantwortet die drei Fragen", () => {
    const t = _ctx().AIWUnbekannterBlock.platzhalterText("evidence");
    // WAS ist das?
    expect(t).toContain("evidence");
    expect(t).toContain("nicht darstellbar");
    // IST MEIN INHALT WEG? - die Entwarnung MUSS im selben Text stehen,
    // sonst liest man den Ersatzblock als Verlust.
    expect(t).toContain("bleibt unverändert erhalten");
    expect(t).toContain("mitgespeichert");
    // WIE aendere ich es?
    expect(t).toContain("Rohansicht");
  });

  // UB02 -------------------------------------------------------------------
  it("UB02: fehlende Blockart wird benannt, nicht ausgelassen", () => {
    const api = _ctx().AIWUnbekannterBlock;
    for (const leer of [undefined, null, ""]) {
      const t = api.platzhalterText(leer);
      expect(t).toContain("unbekannt");
      // Kein Satz mit einer Luecke - «» ohne Inhalt waere schlimmer als
      // gar keine Angabe.
      expect(t).not.toContain("«»");
    }
  });

  // UB03 -------------------------------------------------------------------
  it("UB03: save() gibt die Daten unveraendert und als dasselbe Objekt", () => {
    const win = _ctx();
    const daten = { evidence_ids: [], group_label: "Belege",
                    display_mode: "list", eigenes: { tief: [1, 2] } };
    const w = new win.AIWUnbekannterBlock.UnbekannterBlock({
      data: daten, block: { name: "evidence" } });

    const raus = w.save();
    expect(raus).toEqual(daten);
    // IDENTITAET, nicht nur Gleichheit: eine Kopie waere die Stelle, an der
    // ein Feld unbemerkt normalisiert werden koennte. Genau so ist der
    // Zitatverlust aus Build 704 entstanden.
    expect(raus).toBe(daten);
  });

  // UB04 -------------------------------------------------------------------
  it("UB04: validate() bejaht - sonst wuerfe Editor.js den Block weg", () => {
    const win = _ctx();
    const w = new win.AIWUnbekannterBlock.UnbekannterBlock({
      data: {}, block: { name: "evidence" } });
    // Ein Ersatzblock hat kein Textfeld und sieht fuer die Leerpruefung von
    // Editor.js leer aus. Ohne diese Zusage loeste das Werkzeug gegen den
    // Verlust den Verlust aus.
    expect(w.validate()).toBe(true);
    // Und es ist ein BLOCK-Werkzeug, kein Inline-Werkzeug.
    expect(win.AIWUnbekannterBlock.UnbekannterBlock.isInline).toBe(false);
    expect(win.AIWUnbekannterBlock.UnbekannterBlock.isReadOnlySupported)
      .toBe(true);
  });

  // UB05 -------------------------------------------------------------------
  it("UB05: render() setzt den Text sicher und traegt die Blockart", () => {
    const win = _ctx();
    const w = new win.AIWUnbekannterBlock.UnbekannterBlock({
      data: {}, block: { name: "evidence" } });
    const el = w.render();

    expect(el.getAttribute("data-blockart")).toBe("evidence");
    expect(el.className).toContain("aiw-unbekannter-block");
    expect(el.textContent).toBe(
      win.AIWUnbekannterBlock.platzhalterText("evidence"));

    // XSS: die Blockart stammt aus den Daten, und das Forum ist multilingual.
    // Ueber textContent gesetzt, darf nichts davon zu Markup werden.
    const boese = new win.AIWUnbekannterBlock.UnbekannterBlock({
      data: {}, block: { name: '<img src=x onerror="alert(1)">' } });
    const el2 = boese.render();
    expect(el2.querySelector("img")).toBeNull();
    expect(el2.textContent).toContain("<img");
  });
});
