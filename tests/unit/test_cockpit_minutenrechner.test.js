/**
 * tests/unit/test_cockpit_minutenrechner.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 561: der Minutenrechner.
 *
 * MR01 — deutsche Eingabe: '7,5' ist 7.5 und nicht 7. Der Fehler waere ein
 *        DATENfehler (ein halber Arbeitstag), kein Schoenheitsfehler.
 * MR02 — Prozent-Vorgabe ist 100; leeres Feld heisst 100, nicht 0.
 * MR03 — Leere Stunden/Minuten sind 0, aber Unsinn ('abc') ist ein FEHLER mit
 *        Feldangabe, kein stilles 0.
 * MR04 — Rundung wird BENANNT ('gerundet von ...'), nicht verschluckt.
 * MR05 — Prozent bezieht sich auf die GESAMTE Dauer (h*60+m), nicht nur auf
 *        die Minuten.
 * MR06 — negative Eingaben werden zurueckgewiesen.
 * MR07 — Uebernehmen ohne gewaehltes Ziel meldet das, statt nichts zu tun.
 * MR08 — Uebernehmen schreibt in das gemerkte Feld und nennt es.
 * MR09 — das Fenster schliesst NUR ueber das X: Klick daneben und Escape
 *        lassen es offen (sonst koennte man kein Formularfeld anklicken).
 * MR10 — Ziehen an der Titelzeile verschiebt, Ziehen im Eingabefeld nicht.
 * MR11 — die Zielanzeige folgt dem FOKUS ausserhalb des Rechners (Befund mc
 *        zu Build 561: sie wurde erst beim Uebernehmen aufgefrischt).
 * MR12 — ein Fokuswechsel INNERHALB des Rechners aendert das Ziel nicht, und
 *        nach dem Schliessen horcht nichts mehr.
 *
 * Version: v0.8.565 · Build: 565 · 2026-07-29
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_minutenrechner.js",
  "utf-8"
);

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

describe("Minutenrechner (Build 561)", () => {
  // MR01 --------------------------------------------------------------------
  it("MR01: deutsche Kommaeingabe wird korrekt gelesen", () => {
    const api = _win().AIWMinutenrechner;
    expect(api.zahlLesen("7,5")).toBe(7.5);
    expect(api.zahlLesen("7.5")).toBe(7.5);
    // Der Kernfall: 7,5 h = 450 min. parseFloat('7,5') waere 7 gewesen —
    // also 30 Minuten weniger, jeden Tag.
    expect(api.rechnen("7,5", "", "").minuten).toBe(450);
  });

  // MR02 --------------------------------------------------------------------
  it("MR02: Prozent leer bedeutet 100, nicht 0", () => {
    const api = _win().AIWMinutenrechner;
    expect(api.rechnen("8", "", "").minuten).toBe(480);
    expect(api.rechnen("8", "", "100").minuten).toBe(480);
    expect(api.rechnen("8", "", "50").minuten).toBe(240);
    // 0 % ist eine ANGABE und wird nicht als "leer" behandelt.
    expect(api.rechnen("8", "", "0").minuten).toBe(0);
  });

  // MR03 --------------------------------------------------------------------
  it("MR03: Unsinn ist ein Fehler mit Feldangabe, kein stilles 0", () => {
    const api = _win().AIWMinutenrechner;
    expect(api.rechnen("", "", "").minuten).toBe(0);
    const r = api.rechnen("abc", "", "");
    expect(r.ok).toBe(false);
    expect(r.feld).toBe("stunden");
    const r2 = api.rechnen("8", "xx", "");
    expect(r2.feld).toBe("minuten");
  });

  // MR04 --------------------------------------------------------------------
  it("MR04: Rundung wird benannt, nicht verschluckt", () => {
    const api = _win().AIWMinutenrechner;
    const glatt = api.rechnen("7,5", "", "100");
    expect(glatt.gerundet).toBe(false);
    expect(glatt.text).not.toMatch(/gerundet/);

    const krumm = api.rechnen("7,31", "", "100");   // 438,6
    expect(krumm.minuten).toBe(439);
    expect(krumm.gerundet).toBe(true);
    expect(krumm.text).toMatch(/gerundet von 438,60/);
  });

  // MR05 --------------------------------------------------------------------
  it("MR05: Prozent bezieht sich auf die gesamte Dauer", () => {
    const api = _win().AIWMinutenrechner;
    // (2*60 + 60) * 50 % = 90. Nicht 2*60 + 60*0,5 = 150.
    expect(api.rechnen("2", "60", "50").minuten).toBe(90);
  });

  // MR06 --------------------------------------------------------------------
  it("MR06: negative Eingaben werden zurueckgewiesen", () => {
    const api = _win().AIWMinutenrechner;
    expect(api.rechnen("-1", "", "").ok).toBe(false);
    expect(api.rechnen("1", "", "-5").feld).toBe("prozent");
  });

  // MR07 --------------------------------------------------------------------
  it("MR07: Uebernehmen ohne Ziel meldet das, statt nichts zu tun", () => {
    const win = _win();
    let geschrieben = null;
    const r = win.AIWMinutenrechner.oeffnen({
      host: win.document.body,
      zielGeben: () => null,
      uebernehmen: (m) => { geschrieben = m; },
    });
    r.wurzel.querySelector("#aiw-rechner-h").value = "8";
    r.aktualisieren();
    r.wurzel.querySelector("#aiw-rechner-uebernehmen")
      .dispatchEvent(new win.Event("click"));
    expect(geschrieben).toBeNull();
    expect(r.wurzel.querySelector("#aiw-rechner-ergebnis").textContent)
      .toMatch(/kein Zielfeld/);
  });

  // MR08 --------------------------------------------------------------------
  it("MR08: Uebernehmen schreibt ins gemerkte Feld und nennt es", () => {
    const win = _win();
    let geschrieben = null;
    const r = win.AIWMinutenrechner.oeffnen({
      host: win.document.body,
      zielGeben: () => ({ id: "aiw-capp-wt-mon_min", label: "Montag" }),
      uebernehmen: (m) => { geschrieben = m; },
    });
    r.wurzel.querySelector("#aiw-rechner-h").value = "7,5";
    r.aktualisieren();
    r.wurzel.querySelector("#aiw-rechner-uebernehmen")
      .dispatchEvent(new win.Event("click"));
    expect(geschrieben).toBe(450);
    // Der Rechner SAGT, wohin er geschrieben hat — blindes Uebernehmen
    // waere bei sieben gleichartigen Feldern gefaehrlich.
    expect(r.wurzel.querySelector("#aiw-rechner-ergebnis").textContent)
      .toMatch(/Montag/);
  });

  // MR09 --------------------------------------------------------------------
  it("MR09: schliesst nur ueber das X", () => {
    const win = _win();
    const r = win.AIWMinutenrechner.oeffnen({ host: win.document.body });
    expect(r.istOffen()).toBe(true);

    // Klick daneben: bleibt offen — sonst koennte man kein Formularfeld
    // anklicken, um das Ergebnis dorthin zu uebernehmen (mc).
    win.document.body.dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(r.istOffen()).toBe(true);

    // Escape: bleibt ebenfalls offen.
    const esc = new win.KeyboardEvent("keydown", { key: "Escape",
                                                   bubbles: true });
    win.document.dispatchEvent(esc);
    expect(r.istOffen()).toBe(true);

    r.wurzel.querySelector("#aiw-rechner-zu")
      .dispatchEvent(new win.Event("click"));
    expect(r.istOffen()).toBe(false);
  });

  // MR10 --------------------------------------------------------------------
  it("MR10: Ziehen nur an der Titelzeile", () => {
    const win = _win();
    const r = win.AIWMinutenrechner.oeffnen({
      host: win.document.body, position: { links: 40, oben: 80 },
    });
    const kopf = r.wurzel.querySelector(".aiw-rechner-kopf");

    function maus(ziel, typ, x, y) {
      const ev = new win.MouseEvent(typ, { bubbles: true, clientX: x,
                                           clientY: y });
      ziel.dispatchEvent(ev);
    }
    maus(kopf, "mousedown", 100, 100);
    maus(win.document, "mousemove", 160, 140);
    maus(win.document, "mouseup", 160, 140);
    const nachher = r.wurzel.style.left;
    expect(nachher).not.toBe("40px");

    // Ein Zug im Eingabefeld darf das Fenster NICHT verschieben, sonst
    // rutscht es beim Markieren von Text weg.
    const vorher = r.wurzel.style.left;
    maus(r.wurzel.querySelector("#aiw-rechner-h"), "mousedown", 300, 300);
    maus(win.document, "mousemove", 400, 400);
    maus(win.document, "mouseup", 400, 400);
    expect(r.wurzel.style.left).toBe(vorher);
  });

  // MR11 --------------------------------------------------------------------
  it("MR11: die Zielanzeige folgt dem Fokus ausserhalb des Rechners", () => {
    const win = _win();
    const doc = win.document;
    const a = doc.createElement("input");
    a.id = "aiw-capp-wt-mon_min";
    const b = doc.createElement("input");
    b.id = "aiw-capp-wt-fri_min";
    doc.body.appendChild(a);
    doc.body.appendChild(b);

    let ziel = a;
    a.addEventListener("focusin", () => { ziel = a; });
    b.addEventListener("focusin", () => { ziel = b; });

    const r = win.AIWMinutenrechner.oeffnen({
      host: doc.body,
      zielGeben: () => ({ id: ziel.id,
                          label: win.AIWMinutenrechner.zielName(ziel.id) }),
    });
    const zeile = r.wurzel.querySelector("#aiw-rechner-ziel");
    expect(zeile.textContent).toContain("Montag");

    // Fokus auf ein anderes Feld — die Anzeige muss SOFORT folgen, nicht
    // erst beim Uebernehmen.
    b.dispatchEvent(new win.Event("focusin", { bubbles: true }));
    expect(zeile.textContent).toContain("Freitag");
    expect(zeile.textContent).not.toContain("Montag");
  });

  // MR12 --------------------------------------------------------------------
  it("MR12: Fokus im Rechner aendert nichts, nach dem Schliessen ist Ruhe", () => {
    const win = _win();
    const doc = win.document;
    let abfragen = 0;
    const r = win.AIWMinutenrechner.oeffnen({
      host: doc.body,
      zielGeben: () => { abfragen += 1; return { id: "x", label: "Ziel" }; },
    });
    const nachStart = abfragen;

    // Ein Klick ins Stunden-Feld ist KEIN Zielwechsel — sonst ueberschriebe
    // die Bedienung des Rechners die Zielanzeige.
    r.wurzel.querySelector("#aiw-rechner-h")
      .dispatchEvent(new win.Event("focusin", { bubbles: true }));
    expect(abfragen).toBe(nachStart);

    r.wurzel.querySelector("#aiw-rechner-zu")
      .dispatchEvent(new win.Event("click"));
    // Nach dem Schliessen darf kein Horcher zurueckbleiben.
    const c = doc.createElement("input");
    doc.body.appendChild(c);
    c.dispatchEvent(new win.Event("focusin", { bubbles: true }));
    expect(abfragen).toBe(nachStart);
  });
});
