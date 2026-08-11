/**
 * test_rechtetrennung_falluebersicht.test.js
 *
 * Unit-Tests: 'dashboard.view' traegt nur noch den RAHMEN, die Falluebersicht
 * haengt an 'caseoverview.view' (Build 698, Vorgang 60fe72fb).
 *
 * DER ANLASS (Alex, 31.07.2026): Mit dem Umbau des Dashboards auf das
 * Kachelsystem ergibt es keinen Sinn mehr, das Recht 'dashboard.view' an die
 * Falluebersicht zu koppeln. Es soll auf das Kachel-Dashboard beschraenkt
 * werden; fuer die Sicht 'Fallübersicht' und die Kachel 'Fall-Übersicht
 * (Ampel)' kommt 'caseoverview.view'.
 *
 * WAS DARAN MEHR IST ALS EINE UMBENENNUNG: Die Kachel war die EINZIGE ohne
 * eigenes Recht - sie lief auf dem Recht des Rahmens mit, waehrend jede andere
 * Kachel ihr eigenes fuehrt. Damit bekam jede Person, die den Ueberblick
 * oeffnen durfte, die vollstaendige Fallliste mit den Beschuldigten-Kontonamen
 * ungefragt dazu. Das ist eine Zweckbindungsfrage, keine Aufraeumarbeit.
 *
 * Testfaelle (JS-Seite, Sichtbarkeit in der Navigation):
 *   RT01 — Mit 'dashboard.view' allein erscheint 'faelle' NICHT.
 *   RT02 — Mit 'caseoverview.view' allein erscheint 'faelle', 'dashboard' NICHT.
 *   RT03 — Der Umfang der Sicht folgt dem NEUEN Recht, nicht dem alten.
 *   RT04 — Gegenprobe: mit beiden Rechten ist alles wie vorher. Eine Trennung,
 *          die den gemeinsamen Fall kaputtmacht, waere keine.
 *
 * Die Serverseite (Endpunkte, Kachelkatalog, Hilfe, Migration, Uebernahme der
 * bestehenden Rechte) prueft tests/test_rechtetrennung_falluebersicht.py.
 *
 * Version: 0.1.0 · Build: 698 · 2026-08-11
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/cockpit.js", "utf-8");

// Frischer JSDOM-Kontext je Test, bewusst ohne fetch (der Auto-Boot in
// cockpit.js laeuft dann nicht an) - dieselbe Bauart wie test_cockpit_nav.
function _api() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window.AIWCockpit;
}

function ids(api, caps) {
  return api.visibleViews(caps).map((v) => v.id);
}

describe("Rechtetrennung Falluebersicht (Vorgang 60fe72fb)", () => {

  // -- RT01 ------------------------------------------------------------------
  it("RT01: mit 'dashboard.view' allein erscheint die Fallübersicht nicht",
     () => {
    const api = _api();
    const sichtbar = ids(api, { "dashboard.view": "alle" });

    expect(sichtbar).toContain("dashboard");
    // DER KERN DES VORGANGS. Bis Build 696 stand 'faelle' hier mit drin.
    expect(sichtbar).not.toContain("faelle");
    // 'viewprefs' faehrt immer mit - das ist die bekannte Ausnahme und kein
    // Nebenbefund dieser Aenderung.
    expect(sichtbar).toEqual(["dashboard", "viewprefs"]);
  });

  // -- RT02 ------------------------------------------------------------------
  it("RT02: mit 'caseoverview.view' allein erscheint nur die Fallübersicht",
     () => {
    const api = _api();
    const sichtbar = ids(api, { "caseoverview.view": "alle" });

    expect(sichtbar).toContain("faelle");
    // Die Gegenrichtung gehoert dazu: das neue Recht darf den Rahmen NICHT
    // mitoeffnen, sonst waere es dasselbe Recht unter anderem Namen.
    expect(sichtbar).not.toContain("dashboard");
    expect(sichtbar).toEqual(["faelle", "viewprefs"]);
  });

  // -- RT03 ------------------------------------------------------------------
  it("RT03: der Umfang der Sicht folgt dem neuen Recht", () => {
    const api = _api();
    const sicht = api.viewById("faelle");
    expect(sicht).toBeTruthy();
    expect(sicht.cap).toBe("caseoverview.view");

    // Ein Umfang am ALTEN Recht darf sich auf die Sicht nicht mehr auswirken.
    // Ohne diesen Fall koennte 'faelle' zwar am neuen Recht haengen, seinen
    // Umfang aber weiter vom alten beziehen - die Sicht waere sichtbar und
    // zeigte den falschen Ausschnitt des Bestands.
    const caps = { "dashboard.view": "alle", "caseoverview.view": "eigene" };
    expect(api.scopeTag("caseoverview.view", caps)).toBe("eigene");
    expect(api.scopeTag(sicht.cap, caps)).toBe("eigene");

    // Und die Sicht 'dashboard' haengt weiterhin am alten Recht.
    expect(api.viewById("dashboard").cap).toBe("dashboard.view");
  });

  // -- RT04 ------------------------------------------------------------------
  it("RT04: mit beiden Rechten ist die Navigation wie vor der Trennung", () => {
    const api = _api();
    const sichtbar = ids(api, { "dashboard.view": "alle",
                                "caseoverview.view": "alle" });

    // Genau die Menge, die bis Build 696 'dashboard.view' allein ergab.
    expect(sichtbar).toEqual(["dashboard", "faelle", "viewprefs"]);
    // Und die Reihenfolge folgt weiterhin dem Katalog, nicht der Reihenfolge
    // der Rechte.
    expect(sichtbar.indexOf("dashboard")).toBeLessThan(
      sichtbar.indexOf("faelle"));
  });
});
