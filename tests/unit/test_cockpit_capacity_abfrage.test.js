/**
 * tests/unit/test_cockpit_capacity_abfrage.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Die Adresse des Stammdaten-Abrufs — Build 709 · Vorgang 75f84fee
 *
 * ---------------------------------------------------------------------------
 * WOZU EIN EIGENER FALL FUER DREI ZEILEN ZEICHENKETTE:
 *
 * Die Pflegesicht hat seit Build 709 ZWEI unabhaengige Umschaltungen —
 * 'Auch entfernte Zeilen anzeigen' (Build 563) und 'Auch historische Daten
 * anzeigen'. Beide wirken ueber einen Abfrageparameter desselben Abrufs.
 *
 * Der naheliegende Weg waere gewesen, den zweiten Parameter genauso
 * anzuhaengen wie den ersten:
 *     '/api/capacity/stammdaten'
 *       + (entfernte ? '?include_deleted=1' : '')
 *       + (historie  ? '?include_historic=1' : '')
 * Bei BEIDEN Schaltern stuenden dann ZWEI Fragezeichen in der Adresse. Der
 * Server saehe den zweiten Parameter nie, die Umschaltung bliebe wirkungslos
 * — und nichts wuerde davon berichten: die Liste saehe aus, als gaebe es
 * nichts einzublenden. Ein stiller Fehlschlag genau der Art, gegen die
 * Grundregel 1 steht.
 *
 * Gemessen wird gegen den ECHTEN Code (cockpit.js im jsdom, Aufruf ueber die
 * Test-Oberflaeche des Moduls) und nicht gegen eine Abschrift.
 *
 * FAELLE
 *   CQ01  ohne Umschaltung: die nackte Adresse, kein Fragezeichen
 *   CQ02  nur entfernte Zeilen
 *   CQ03  nur historische Daten
 *   CQ04  BEIDE: genau EIN Fragezeichen, beide Parameter kommen an
 *   CQ05  fehlende Uebergabe faellt nicht um
 * ===========================================================================*/

import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/cockpit.js", "utf-8");

let API;
beforeAll(() => {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body><div id='aiw-main'></div>"
    + "<nav id='aiw-nav'></nav></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.fetch = () => Promise.resolve({ ok: false, status: 500,
                                             text: () => Promise.resolve("") });
  dom.window.eval(_src);
  API = dom.window.AIWCockpit;
});

describe("Stammdaten-Abruf der Kapazitaetspflege (Vorgang 75f84fee)", () => {

  it("CQ01: ohne Umschaltung steht kein Fragezeichen in der Adresse", () => {
    expect(API.stammdatenUrl({})).toBe("/api/capacity/stammdaten");
  });

  it("CQ02: nur entfernte Zeilen", () => {
    expect(API.stammdatenUrl({ entfernte: true }))
      .toBe("/api/capacity/stammdaten?include_deleted=1");
  });

  it("CQ03: nur historische Daten", () => {
    expect(API.stammdatenUrl({ historie: true }))
      .toBe("/api/capacity/stammdaten?include_historic=1");
  });

  it("CQ04: beide zusammen — EIN Fragezeichen, beide Parameter", () => {
    // DER KERNFALL. Ein zweites Fragezeichen waere hier eine wirkungslose
    // Umschaltung ohne jede Fehlermeldung.
    const url = API.stammdatenUrl({ entfernte: true, historie: true });
    expect(url).toBe(
      "/api/capacity/stammdaten?include_deleted=1&include_historic=1");
    expect(url.split("?").length).toBe(2);
    expect(url).toContain("include_deleted=1");
    expect(url).toContain("include_historic=1");
  });

  it("CQ05: fehlende Uebergabe faellt nicht um", () => {
    // Der Lader wird auch ohne Uebergabe gerufen (erster Aufruf der Sicht).
    expect(API.stammdatenUrl(undefined)).toBe("/api/capacity/stammdaten");
    expect(API.stammdatenUrl(null)).toBe("/api/capacity/stammdaten");
  });
});
