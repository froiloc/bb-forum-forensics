/**
 * test_anker_meldung.test.js
 * Unit-/Regressionstests: Ein Ankersprung, der sein Ziel verfehlt, wird gemeldet
 * Baustelle 2/3 · Build 699 · 2026-08-12 · Vorgang f5956e6b-6eee-428f-bdcc-ed525ac88399
 *
 * ---------------------------------------------------------------------------
 * WAS HIER GEMESSEN WIRD UND WARUM
 *
 * Der Vorgang meldet, dass Verweise auf einen Beitrag in einem mehrseitigen
 * Thema stets die ERSTE Seite lieferten; der Beitrag steht dort nicht, "daher
 * wird auch das ID-Element nicht gefunden". Die Seitenwahl ist Sache des
 * Servers (blob_handler.py / forensic_db.py, dort gemessen durch T23-T30 und
 * R01-R11). HIER geht es um den zweiten Teil desselben Befundes: Was tut die
 * Oberflaeche, wenn das ID-Element trotzdem nicht da ist?
 *
 * BIS BUILD 698: nichts. 'if (target) target.scrollIntoView(...)' — kein
 * Zweig fuer das fehlende Ziel. Die Seite blieb oben stehen. Wer einem
 * Verweis auf einen belastenden Beitrag folgte und oben landete, las dort
 * FREMDE Beitraege, ohne Anhaltspunkt, dass er nicht das Gesuchte sieht.
 * Ein nicht angezeigter Befund ist von einem nicht erhobenen nicht zu
 * unterscheiden (Grundregel 1).
 *
 * GEMESSEN WIRD AM SICHTBAREN ERGEBNIS, nicht an internen Aufrufen: die
 * Meldung im Toast-Bereich ist das Einzige, was die Ermittlerin erreicht.
 *
 * FAELLE
 *   AS01  Anker vorhanden -> Sprung, KEINE Meldung (Regelfall)
 *   AS02  Anker fehlt, fragment_source='unaufgeloest' -> Meldung zum
 *         ERFASSUNGSUMFANG, bleibt bis zum Schliessen stehen
 *   AS03  Anker fehlt, keine Herkunftsangabe -> allgemeine Meldung
 *   AS04  kein Anker im Envelope -> keine Meldung (Regression)
 *   AS05  fragment_source='unpruefbar' -> eigene Meldung (fehlender BLOB)
 *   AS06  fragment_source='gemessen' und Anker vorhanden -> keine Meldung;
 *         das ist der Zustand, den der Serverfix herstellt
 * ===========================================================================*/

import { describe, it, expect, vi } from "vitest";
import { JSDOM } from "jsdom";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TOOLBAR_SRC = readFileSync(
  join(__dirname, "../../toolbar/toolbar.js"), "utf-8"
);

/**
 * Envelope einer erfolgreich ausgelieferten Seite.
 * @param o.html            Rumpf-HTML (enthaelt den Anker oder eben nicht)
 * @param o.fragment        envelope.fragment (Ankername ohne '#')
 * @param o.fragmentSource  envelope.fragment_source (Build 699)
 */
function envelopeResponse(o = {}) {
  const env = {
    in_scope:        true,
    fetch_failed:    false,
    html:            o.html === undefined ? "<p>ok</p>" : o.html,
    head: { title: "T", base_href: "/forum/", stylesheets: [], inline_styles: [] },
    scrape_context:  "user",
    http_status:     200,
    url_canonical:   "/forum/viewtopic.php?id=500",
    fragment:        o.fragment === undefined ? null : o.fragment,
    fragment_source: o.fragmentSource === undefined ? null : o.fragmentSource,
    trace_elements:  [],
  };
  return { ok: true, json: () => Promise.resolve(env) };
}

/**
 * Fenster mit geladener toolbar.js; der Startaufruf liefert den Envelope.
 *
 * scrollIntoView wird von Hand gesetzt: jsdom kennt die Methode nicht, ein
 * geglueckter Sprung wuerde sonst mit einem TypeError enden — und der Test
 * maesse den Pruefstand statt der Anwendung.
 */
async function fensterMitEnvelope(envOpts) {
  const dom = new JSDOM(
    `<!DOCTYPE html><html><head></head><body>
       <div id="forensic-toolbar"></div>
       <div id="forensic-viewport"></div>
     </body></html>`,
    { url: "http://127.0.0.2:8080/forum/viewtopic.php?id=500",
      runScripts: "dangerously", resources: "usable" }
  );
  const { window } = dom;

  const scrollMock = vi.fn();
  window.Element.prototype.scrollIntoView = scrollMock;
  window.fetch = vi.fn().mockResolvedValue(envelopeResponse(envOpts));
  window.requestAnimationFrame = (cb) => setTimeout(cb, 0);

  window.eval(TOOLBAR_SRC);

  if (window.document.readyState === "loading") {
    await new Promise((r) =>
      window.document.addEventListener("DOMContentLoaded", r, { once: true }));
  } else {
    window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
  }
  await new Promise((r) => setTimeout(r, 80));

  return { window, scrollMock };
}

/** Alle sichtbaren Meldungstexte des Toast-Bereichs. */
function meldungen(window) {
  return Array.from(
    window.document.querySelectorAll(".forensic-toast__msg")
  ).map((el) => el.textContent);
}

/** Meldungen, die den Anker betreffen (die uebrigen gehen uns hier nichts an). */
function ankerMeldungen(window) {
  return meldungen(window).filter(
    (t) => t.includes("Sprungziel") || t.includes("verlinkte Beitrag")
  );
}

describe("toolbar.js — Meldung bei verfehltem Ankersprung (Vorgang f5956e6b)", () => {

  it("AS01: vorhandener Anker wird angesprungen und NICHT gemeldet", async () => {
    const { window, scrollMock } = await fensterMitEnvelope({
      html: '<div id="p777">der gesuchte Beitrag</div>',
      fragment: "p777",
    });
    expect(scrollMock).toHaveBeenCalled();
    expect(ankerMeldungen(window)).toEqual([]);
  });

  it("AS02: fehlender Anker mit 'unaufgeloest' meldet den Erfassungsumfang", async () => {
    // Die Aussage des Servers lautet hier: ich habe gesucht, KEINE erfasste
    // Seite traegt diesen Beitrag. Das ist eine Aussage ueber den Bestand,
    // nicht ueber die Anzeige — und deshalb die wichtigere der beiden.
    const { window, scrollMock } = await fensterMitEnvelope({
      html: '<div id="p100">ein anderer Beitrag</div>',
      fragment: "p777",
      fragmentSource: "unaufgeloest",
    });
    expect(scrollMock).not.toHaveBeenCalled();
    const m = ankerMeldungen(window);
    expect(m.length).toBe(1);
    expect(m[0]).toContain("p777");
    expect(m[0]).toContain("erfassten Seite");
    expect(m[0]).toContain("NICHT");
  });

  it("AS03: fehlender Anker ohne Herkunftsangabe meldet den Darstellungsbefund", async () => {
    const { window } = await fensterMitEnvelope({
      html: '<div id="p100">ein anderer Beitrag</div>',
      fragment: "p777",
    });
    const m = ankerMeldungen(window);
    expect(m.length).toBe(1);
    expect(m[0]).toContain("Sprungziel #p777");
    expect(m[0]).toContain("nicht gefunden");
  });

  it("AS04: ohne Anker wird nichts gemeldet (Regression)", async () => {
    const { window, scrollMock } = await fensterMitEnvelope({
      html: "<p>Seite ohne Anker</p>",
    });
    expect(scrollMock).not.toHaveBeenCalled();
    expect(ankerMeldungen(window)).toEqual([]);
  });

  it("AS05: 'unpruefbar' nennt den fehlenden Seiteninhalt als Grund", async () => {
    // Der Server setzt diesen Wert, wenn der BLOB fehlt (fehlgeschlagener
    // Abruf). Im Regelfall bricht _handleEnvelope schon bei fetch_failed ab;
    // der Fall steht hier, damit die Meldung auch dann stimmt, wenn er auf
    // einem anderen Weg doch bis hierher durchkommt.
    const { window } = await fensterMitEnvelope({
      html: "<p>Rumpf ohne den Beitrag</p>",
      fragment: "p777",
      fragmentSource: "unpruefbar",
    });
    const m = ankerMeldungen(window);
    expect(m.length).toBe(1);
    expect(m[0]).toContain("nicht pruefbar");
  });

  it("AS06: 'gemessen' mit vorhandenem Anker bleibt still (Ziel des Serverfixes)", async () => {
    // Genau dieser Zustand ist es, den der Fix in blob_handler.py herstellt:
    // die ausgelieferte Seite TRAEGT den Beitrag. Bliebe hier eine Meldung
    // stehen, waere der Fix an der Oberflaeche nicht angekommen.
    const { window, scrollMock } = await fensterMitEnvelope({
      html: '<div id="p777">der gesuchte Beitrag</div>',
      fragment: "p777",
      fragmentSource: "gemessen",
    });
    expect(scrollMock).toHaveBeenCalled();
    expect(ankerMeldungen(window)).toEqual([]);
  });
});
