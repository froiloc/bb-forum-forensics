/**
 * @vitest-environment jsdom
 *
 * tests/unit/test_cockpit_datumspaar.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 663: der Datumspaar-Baustein (Ticket d3f933cd).
 *
 * DP01 — istIsoDatum nimmt YYYY-MM-DD an und sonst nichts.
 * DP02 — uebernehmen=true: ein LEERES Bis-Feld bekommt das Von-Datum.
 * DP03 — uebernehmen=true: ein GEFUELLTES Bis-Feld wird NICHT ueberschrieben.
 *        Das ist der Kern der Zusage "keine Eingabe wird unter der Hand
 *        ersetzt" und deshalb ein eigener Fall.
 * DP04 — uebernehmen=false (Vorgabe): das leere Bis-Feld bleibt leer. Der
 *        Gegenbeweis zu DP02 — ohne ihn koennte die Vorgabe unbemerkt kippen
 *        und einen Filter auf einen Tag zusammenziehen.
 * DP05 — die untere Schranke steht am Bis-Feld und wandert mit.
 * DP06 — wird Von geleert, verschwindet die Schranke wieder.
 * DP07 — Widerspruch (Bis vor Von): der Wert bleibt UNANGETASTET, das Feld
 *        wird markiert, und onWarnung wird gerufen. Es wird nichts berichtigt.
 * DP08 — loest sich der Widerspruch, verschwindet die Markierung.
 * DP09 — beim Aufbau mit vorhandenem Von-Datum gilt die Schranke sofort, aber
 *        es wird NICHTS uebernommen: die Uebernahme ist eine Reaktion auf eine
 *        Eingabe, nicht auf das Zeichnen einer Maske.
 * DP10 — abmelden() beendet die Kopplung wirklich.
 * DP11 — fehlt ein Feld, gibt es keinen Absturz und eine benutzbare Steuerung.
 * DP12 — onUebernahme meldet das gesetzte Datum (damit die Sicht die nicht
 *        angeforderte Wertaenderung erklaeren kann).
 *
 * Version: v0.8.663 · Build: 663 · 2026-08-04
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_datumspaar.js",
  "utf-8"
);

/** Frisches Fenster mit dem ECHTEN Baustein (kein Nachbau — "gruen aber tot"). */
function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

/** Zwei Datumsfelder im Dokument, wahlweise vorbelegt. */
function _paar(win, vonWert, bisWert) {
  const von = win.document.createElement("input");
  von.type = "date";
  von.id = "von";
  if (vonWert) { von.value = vonWert; }
  const bis = win.document.createElement("input");
  bis.type = "date";
  bis.id = "bis";
  if (bisWert) { bis.value = bisWert; }
  win.document.body.appendChild(von);
  win.document.body.appendChild(bis);
  return { von, bis };
}

/** Das Von-Feld setzen und 'change' feuern — genau der Weg der Bedienung. */
function _setze(win, feld, wert) {
  feld.value = wert;
  feld.dispatchEvent(new win.Event("change"));
}

describe("Datumspaar (Build 663, Ticket d3f933cd)", () => {
  // DP01 ---------------------------------------------------------------------
  it("DP01: istIsoDatum nimmt nur YYYY-MM-DD an", () => {
    const api = _win().AIWDatumspaar;
    expect(api.istIsoDatum("2026-08-04")).toBe(true);
    expect(api.istIsoDatum("2026-8-4")).toBe(false);
    expect(api.istIsoDatum("")).toBe(false);
    expect(api.istIsoDatum("04.08.2026")).toBe(false);
    expect(api.istIsoDatum(null)).toBe(false);
    expect(api.istIsoDatum(20260804)).toBe(false);
  });

  // DP02 ---------------------------------------------------------------------
  it("DP02: uebernehmen=true fuellt ein LEERES Bis-Feld", () => {
    const win = _win();
    const { von, bis } = _paar(win);
    win.AIWDatumspaar.koppeln(von, bis, { uebernehmen: true });
    _setze(win, von, "2026-09-15");
    expect(bis.value).toBe("2026-09-15");
  });

  // DP03 ---------------------------------------------------------------------
  it("DP03: ein gefuelltes Bis-Feld wird NIE ueberschrieben", () => {
    const win = _win();
    const { von, bis } = _paar(win, "", "2026-12-24");
    win.AIWDatumspaar.koppeln(von, bis, { uebernehmen: true });
    _setze(win, von, "2026-09-15");
    // Die Angabe der Bedienerin bleibt stehen. Eine Bequemlichkeitsfunktion,
    // die Eingaben ersetzt, macht jede Eingabe pruefungsbeduerftig.
    expect(bis.value).toBe("2026-12-24");
  });

  // DP04 ---------------------------------------------------------------------
  it("DP04: ohne uebernehmen bleibt das Bis-Feld leer (Vorgabe)", () => {
    const win = _win();
    const { von, bis } = _paar(win);
    // Vorgabe: KEINE Uebernahme. In Filtern heisst leer "ohne obere Grenze";
    // ein stiller Sprung auf den Von-Tag zoege die Auswertung zusammen.
    win.AIWDatumspaar.koppeln(von, bis, {});
    _setze(win, von, "2026-09-15");
    expect(bis.value).toBe("");
  });

  // DP05 ---------------------------------------------------------------------
  it("DP05: die untere Schranke steht am Bis-Feld und wandert mit", () => {
    const win = _win();
    const { von, bis } = _paar(win);
    win.AIWDatumspaar.koppeln(von, bis, {});
    _setze(win, von, "2026-09-15");
    expect(bis.getAttribute("min")).toBe("2026-09-15");
    _setze(win, von, "2026-10-01");
    expect(bis.getAttribute("min")).toBe("2026-10-01");
  });

  // DP06 ---------------------------------------------------------------------
  it("DP06: wird Von geleert, faellt die Schranke weg", () => {
    const win = _win();
    const { von, bis } = _paar(win);
    win.AIWDatumspaar.koppeln(von, bis, {});
    _setze(win, von, "2026-09-15");
    expect(bis.getAttribute("min")).toBe("2026-09-15");
    _setze(win, von, "");
    // Eine Schranke ohne Anfangsdatum haette keinen Grund mehr und wuerde
    // eine Eingabe verhindern, die niemand verboten hat.
    expect(bis.getAttribute("min")).toBe(null);
  });

  // DP07 ---------------------------------------------------------------------
  it("DP07: Bis vor Von wird gemeldet, aber NICHT berichtigt", () => {
    const win = _win();
    const { von, bis } = _paar(win, "", "2026-01-05");
    let gemeldet = null;
    win.AIWDatumspaar.koppeln(von, bis, {
      uebernehmen: true,
      onWarnung: (t) => { gemeldet = t; },
    });
    _setze(win, von, "2026-09-15");
    expect(bis.value).toBe("2026-01-05");
    expect(bis.classList.contains("aiw-feldfehler")).toBe(true);
    expect(gemeldet).toBeTruthy();
    // Die Meldung muss BEIDE Daten nennen — sonst weiss die Bedienerin nicht,
    // welches der beiden Felder sie ansehen soll.
    expect(gemeldet).toContain("2026-01-05");
    expect(gemeldet).toContain("2026-09-15");
  });

  // DP08 ---------------------------------------------------------------------
  it("DP08: loest sich der Widerspruch, verschwindet die Markierung", () => {
    const win = _win();
    const { von, bis } = _paar(win, "", "2026-01-05");
    win.AIWDatumspaar.koppeln(von, bis, {});
    _setze(win, von, "2026-09-15");
    expect(bis.classList.contains("aiw-feldfehler")).toBe(true);
    _setze(win, von, "2026-01-01");
    expect(bis.classList.contains("aiw-feldfehler")).toBe(false);
  });

  // DP09 ---------------------------------------------------------------------
  it("DP09: beim Aufbau gilt die Schranke, aber es wird nichts uebernommen", () => {
    const win = _win();
    const { von, bis } = _paar(win, "2026-05-01", "");
    let uebernommen = null;
    win.AIWDatumspaar.koppeln(von, bis, {
      uebernehmen: true,
      onUebernahme: (d) => { uebernommen = d; },
    });
    expect(bis.getAttribute("min")).toBe("2026-05-01");
    // Das Zeichnen einer Maske ist keine Eingabe. Wuerde hier uebernommen,
    // bekaeme jedes Neuladen der Sicht (Build 561: Formularzustand) ein
    // Bis-Datum geschenkt, das niemand gesetzt hat.
    expect(bis.value).toBe("");
    expect(uebernommen).toBe(null);
  });

  // DP10 ---------------------------------------------------------------------
  it("DP10: abmelden beendet die Kopplung", () => {
    const win = _win();
    const { von, bis } = _paar(win);
    const steuerung = win.AIWDatumspaar.koppeln(von, bis, { uebernehmen: true });
    steuerung.abmelden();
    _setze(win, von, "2026-09-15");
    expect(bis.value).toBe("");
    expect(bis.getAttribute("min")).toBe(null);
  });

  // DP11 ---------------------------------------------------------------------
  it("DP11: ein fehlendes Feld stuerzt nicht ab", () => {
    const win = _win();
    const { von } = _paar(win);
    const a = win.AIWDatumspaar.koppeln(von, null, { uebernehmen: true });
    const b = win.AIWDatumspaar.koppeln(null, null, {});
    expect(typeof a.abmelden).toBe("function");
    expect(typeof b.abmelden).toBe("function");
    expect(() => { a.abmelden(); b.abmelden(); }).not.toThrow();
  });

  // DP12 ---------------------------------------------------------------------
  it("DP12: onUebernahme meldet das gesetzte Datum", () => {
    const win = _win();
    const { von, bis } = _paar(win);
    let gemeldet = null;
    win.AIWDatumspaar.koppeln(von, bis, {
      uebernehmen: true,
      onUebernahme: (d) => { gemeldet = d; },
    });
    _setze(win, von, "2026-09-15");
    expect(gemeldet).toBe("2026-09-15");
    // Zweites Setzen: Bis ist jetzt gefuellt -> keine erneute Meldung.
    gemeldet = null;
    _setze(win, von, "2026-09-16");
    expect(gemeldet).toBe(null);
  });
});
