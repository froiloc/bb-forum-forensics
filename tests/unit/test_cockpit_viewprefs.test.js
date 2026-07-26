/**
 * tests/unit/test_cockpit_viewprefs.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3G (Build 546)
 *
 * Testsuite fuer management/server/static/cockpit_viewprefs.js UND die neuen
 * reinen Funktionen in cockpit.js. Getestet wird der ECHTE Code (readFileSync
 * + JSDOM) — KEIN dupliziertes Logik-Abbild ('gruen-aber-tot'-Falle).
 *
 * REINE FUNKTIONEN DER SHELL (cockpit.js):
 *   VF01 — applyViewPrefs() ohne Vorliebe: Katalogfolge, nichts versteckt,
 *          und der Katalog bleibt UNBERUEHRT.
 *   VF02 — applyViewPrefs() ordnet um und markiert 'versteckt'.
 *   VF03 — SICHTEN, DIE DIE VORLIEBE NICHT KENNT, STEHEN HINTEN UND SIND
 *          SICHTBAR. Das ist die wichtigste Zusicherung der Funktion: eine
 *          spaeter hinzugekommene Sicht darf nicht dadurch unsichtbar werden,
 *          dass jemand vor Monaten etwas eingerichtet hat.
 *   VF04 — DER RECHTEFILTER LAEUFT ZULETZT: eine Vorliebe kann keine Sicht
 *          einblenden, fuer die das Recht fehlt.
 *   VF05 — navViews() laesst versteckte Sichten weg; hiddenCount() zaehlt
 *          NUR rechte-sichtbare.
 *   VF06 — 'viewprefs' ist ohne jedes Recht sichtbar ('immer') und steht im
 *          Katalog.
 *
 * REINE FUNKTIONEN DES MODULS:
 *   VF07 — verschiebe(): tauscht Nachbarn, laesst die Eingabe unberuehrt,
 *          ein Zug ueber den Rand ist wirkungslos (kein Fehler).
 *   VF08 — umschalten(): kippt 'versteckt', ohne die Eingabe zu veraendern.
 *   VF09 — zuNutzlast(): Reihenfolge des Arrays = Reihenfolge; 'sichtbar'
 *          ist die Umkehrung von 'versteckt'.
 *   VF10 — zusammenfassung() zaehlt richtig.
 *   VF11 — istGeaendert(): erkennt Reihenfolge- UND Sichtbarkeitsaenderung.
 *   VF12 — entwurfAnwenden() fuegt NICHTS hinzu; neue Zeilen landen hinten
 *          und sichtbar.
 *
 * ENTWURF + WARNUNG:
 *   VF13 — Ein Entwurf, der dasselbe sagt wie der gespeicherte Stand, wird
 *          verworfen statt als 'ungespeichert' angezeigt.
 *   VF14 — Nach einer Aenderung meldet hatUngespeichertes() true und der
 *          Entwurf liegt im localStorage; nachErfolg() raeumt beides ab.
 *   VF15 — Faellt localStorage aus, bricht nichts (nur die Bequemlichkeit
 *          fehlt).
 *
 * RENDER:
 *   VF16 — renderViewPrefs() zeichnet je Bereich eine Zeile mit Schalter,
 *          Pfeilen und Gruppe; Ausgeblendetes bleibt SICHTBAR in der Liste
 *          (markiert), statt zu verschwinden.
 *   VF17 — Der Speichern-Knopf ist ohne Aenderung gesperrt und meldet das.
 *   VF18 — onSave() bekommt die Nutzlast in der bearbeiteten Reihenfolge.
 *
 * Version: v0.8.546 · Build: 546 · 2026-07-26
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _shell = readFileSync("management/server/static/cockpit.js", "utf-8");
const _mod = readFileSync(
  "management/server/static/cockpit_viewprefs.js",
  "utf-8"
);

// Frischer JSDOM-Kontext pro Test. Bewusst OHNE fetch, damit der Auto-Boot in
// cockpit.js nicht anlaeuft (Guard dort).
function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_shell);
  dom.window.eval(_mod);
  return dom.window;
}

function _shellApi() {
  return _ctx().AIWCockpit;
}
function _modApi(win) {
  return (win || _ctx()).AIWCockpitViewPrefs;
}

const CAPS = {
  "dashboard.view": "alle",
  "escalation.view": "alle",
  "ops.view": "alle",
};

describe("cockpit.js — Ansichtseinstellung anwenden (Build 546)", () => {
  // VF01 ---------------------------------------------------------------------
  it("VF01: ohne Vorliebe Katalogfolge, nichts versteckt, Katalog unberuehrt", () => {
    const A = _shellApi();
    const vorher = A.VIEW_CATALOG.map((v) => v.id);
    const out = A.applyViewPrefs(A.VIEW_CATALOG, []);
    expect(out.map((v) => v.id)).toEqual(vorher);
    expect(out.every((v) => v.versteckt === false)).toBe(true);
    // Der Katalog darf keine 'versteckt'-Marke abbekommen haben.
    expect(A.VIEW_CATALOG.some((v) => "versteckt" in v)).toBe(false);
    expect(A.VIEW_CATALOG.map((v) => v.id)).toEqual(vorher);
  });

  // VF02 ---------------------------------------------------------------------
  it("VF02: ordnet um und markiert versteckt", () => {
    const A = _shellApi();
    const out = A.applyViewPrefs(A.VIEW_CATALOG, [
      { key: "audit", sichtbar: true },
      { key: "dashboard", sichtbar: false },
    ]);
    expect(out[0].id).toBe("audit");
    expect(out[1].id).toBe("dashboard");
    expect(out[1].versteckt).toBe(true);
    expect(out[0].versteckt).toBe(false);
  });

  // VF03 ---------------------------------------------------------------------
  it("VF03: unbekannte Sichten stehen hinten und sind SICHTBAR", () => {
    const A = _shellApi();
    const out = A.applyViewPrefs(A.VIEW_CATALOG, [
      { key: "audit", sichtbar: true },
    ]);
    expect(out[0].id).toBe("audit");
    // Alle uebrigen folgen in Katalogfolge und sind sichtbar — eine spaeter
    // hinzugekommene Sicht darf nicht still verschwinden.
    const rest = out.slice(1);
    expect(rest.every((v) => v.versteckt === false)).toBe(true);
    expect(rest.length).toBe(A.VIEW_CATALOG.length - 1);
    const katalogOhneAudit = A.VIEW_CATALOG.filter((v) => v.id !== "audit").map(
      (v) => v.id
    );
    expect(rest.map((v) => v.id)).toEqual(katalogOhneAudit);
  });

  // VF04 ---------------------------------------------------------------------
  it("VF04: der Rechtefilter laeuft ZULETZT — Vorliebe berechtigt nicht", () => {
    const A = _shellApi();
    // 'policy' verlangt policy.view, das die Person NICHT hat.
    const ids = A.navViews(CAPS, [
      { key: "policy", sichtbar: true },
      { key: "dashboard", sichtbar: true },
    ]).map((v) => v.id);
    expect(ids).not.toContain("policy");
    expect(ids).toContain("dashboard");
  });

  // VF05 ---------------------------------------------------------------------
  it("VF05: navViews laesst Verstecktes weg, hiddenCount zaehlt nur Erlaubtes", () => {
    const A = _shellApi();
    const prefs = [
      { key: "escalation", sichtbar: false },
      // 'policy' darf die Person gar nicht sehen -> zaehlt NICHT als
      // 'ausgeblendet'; sonst waere die Zahl eine Auskunft ueber fremde Rechte.
      { key: "policy", sichtbar: false },
    ];
    expect(A.navViews(CAPS, prefs).map((v) => v.id)).not.toContain(
      "escalation"
    );
    expect(A.hiddenCount(CAPS, prefs)).toBe(1);
    expect(A.hiddenCount(CAPS, [])).toBe(0);
  });

  // VF06 ---------------------------------------------------------------------
  it("VF06: 'viewprefs' ist ohne jedes Recht sichtbar", () => {
    const A = _shellApi();
    const eintrag = A.VIEW_CATALOG.filter((v) => v.id === "viewprefs");
    expect(eintrag.length).toBe(1);
    expect(eintrag[0].immer).toBe(true);
    expect(A.visibleViews({}).map((v) => v.id)).toEqual(["viewprefs"]);
    expect(A.navViews({}, []).map((v) => v.id)).toEqual(["viewprefs"]);
  });
});

describe("cockpit_viewprefs.js — reine Funktionen (Build 546)", () => {
  const ROWS = [
    { id: "a", label: "A", group: "G1" },
    { id: "b", label: "B", group: "G1" },
    { id: "c", label: "C", group: "G2" },
  ];

  // VF07 ---------------------------------------------------------------------
  it("VF07: verschiebe tauscht Nachbarn, Rand ist wirkungslos, Eingabe unberuehrt", () => {
    const M = _modApi();
    expect(M.verschiebe(ROWS, "c", -1).map((r) => r.id)).toEqual([
      "a",
      "c",
      "b",
    ]);
    expect(M.verschiebe(ROWS, "a", 1).map((r) => r.id)).toEqual(["b", "a", "c"]);
    // Ueber den Rand: unveraendert, KEIN Fehler.
    expect(M.verschiebe(ROWS, "a", -1).map((r) => r.id)).toEqual([
      "a",
      "b",
      "c",
    ]);
    expect(M.verschiebe(ROWS, "c", 1).map((r) => r.id)).toEqual([
      "a",
      "b",
      "c",
    ]);
    // Unbekannter Schluessel: unveraendert.
    expect(M.verschiebe(ROWS, "gibtsnicht", 1).map((r) => r.id)).toEqual([
      "a",
      "b",
      "c",
    ]);
    // Die Eingabe ist unberuehrt.
    expect(ROWS.map((r) => r.id)).toEqual(["a", "b", "c"]);
  });

  // VF08 ---------------------------------------------------------------------
  it("VF08: umschalten kippt 'versteckt' ohne die Eingabe zu veraendern", () => {
    const M = _modApi();
    const out = M.umschalten(ROWS, "b");
    expect(out[1].versteckt).toBe(true);
    expect(M.umschalten(out, "b")[1].versteckt).toBe(false);
    expect(ROWS[1].versteckt).toBeUndefined();
  });

  // VF09 ---------------------------------------------------------------------
  it("VF09: zuNutzlast — Arrayfolge ist die Reihenfolge", () => {
    const M = _modApi();
    const out = M.zuNutzlast(M.umschalten(M.verschiebe(ROWS, "c", -1), "a"));
    expect(out).toEqual([
      { key: "a", sichtbar: false },
      { key: "c", sichtbar: true },
      { key: "b", sichtbar: true },
    ]);
    // Keine Positionsangabe — sie gaebe es sonst zweimal.
    expect(Object.keys(out[0]).sort()).toEqual(["key", "sichtbar"]);
  });

  // VF10 ---------------------------------------------------------------------
  it("VF10: zusammenfassung zaehlt", () => {
    const M = _modApi();
    expect(M.zusammenfassung(ROWS)).toEqual({
      gesamt: 3,
      sichtbar: 3,
      versteckt: 0,
    });
    expect(M.zusammenfassung(M.umschalten(ROWS, "b"))).toEqual({
      gesamt: 3,
      sichtbar: 2,
      versteckt: 1,
    });
    expect(M.zusammenfassung([])).toEqual({
      gesamt: 0,
      sichtbar: 0,
      versteckt: 0,
    });
  });

  // VF11 ---------------------------------------------------------------------
  it("VF11: istGeaendert erkennt Reihenfolge und Sichtbarkeit", () => {
    const M = _modApi();
    const gespeichert = [
      { key: "a", sichtbar: true },
      { key: "b", sichtbar: true },
      { key: "c", sichtbar: true },
    ];
    expect(M.istGeaendert(ROWS, gespeichert)).toBe(false);
    expect(M.istGeaendert(M.verschiebe(ROWS, "c", -1), gespeichert)).toBe(true);
    expect(M.istGeaendert(M.umschalten(ROWS, "a"), gespeichert)).toBe(true);
    // Gegen einen leeren gespeicherten Stand ist alles eine Aenderung.
    expect(M.istGeaendert(ROWS, [])).toBe(true);
  });

  // VF12 ---------------------------------------------------------------------
  it("VF12: entwurfAnwenden fuegt nichts hinzu; Neues landet hinten+sichtbar", () => {
    const M = _modApi();
    const out = M.entwurfAnwenden(ROWS, [
      { key: "c", sichtbar: false },
      // 'weg' gibt es in den Zeilen NICHT -> darf nichts erzeugen.
      { key: "weg", sichtbar: true },
    ]);
    expect(out.map((r) => r.id)).toEqual(["c", "a", "b"]);
    expect(out[0].versteckt).toBe(true);
    // 'a'/'b' kannte der Entwurf nicht -> hinten, sichtbar.
    expect(out[1].versteckt).toBeUndefined();
    expect(out.length).toBe(3);
  });
});

describe("cockpit_viewprefs.js — Entwurf und Warnung (Build 546)", () => {
  const ROWS = [
    { id: "a", label: "A", group: "G" },
    { id: "b", label: "B", group: "G" },
  ];
  const GESPEICHERT = [
    { key: "a", sichtbar: true },
    { key: "b", sichtbar: true },
  ];

  // VF13 ---------------------------------------------------------------------
  it("VF13: ein deckungsgleicher Entwurf wird verworfen, nicht angezeigt", () => {
    const win = _ctx();
    const M = _modApi(win);
    M.entwurfSchreiben(GESPEICHERT); // sagt dasselbe wie die Datenbank
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    M.renderViewPrefs(main, { rows: ROWS, gespeichert: GESPEICHERT }, {});
    expect(M.hatUngespeichertes()).toBe(false);
    expect(M.entwurfLesen()).toBe(null);
    expect(main.textContent).not.toContain("wiederhergestellt");
  });

  // VF14 ---------------------------------------------------------------------
  it("VF14: Aenderung -> ungespeichert + Entwurf; nachErfolg raeumt ab", () => {
    const win = _ctx();
    const M = _modApi(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    M.renderViewPrefs(main, { rows: ROWS, gespeichert: GESPEICHERT }, {});
    expect(M.hatUngespeichertes()).toBe(false);

    // Sichtbarkeit von 'a' abschalten (erste Checkbox).
    const cb = main.querySelector(".aiw-vp-schalter");
    cb.checked = false;
    cb.dispatchEvent(new win.Event("change"));

    expect(M.hatUngespeichertes()).toBe(true);
    expect(M.entwurfLesen()).toEqual([
      { key: "a", sichtbar: false },
      { key: "b", sichtbar: true },
    ]);
    expect(main.textContent).toContain("Nicht gespeichert");

    M.nachErfolg();
    expect(M.hatUngespeichertes()).toBe(false);
    expect(M.entwurfLesen()).toBe(null);
  });

  // VF15 ---------------------------------------------------------------------
  it("VF15: ohne localStorage bricht nichts", () => {
    const win = _ctx();
    const M = _modApi(win);
    Object.defineProperty(win, "localStorage", {
      get() {
        throw new Error("abgeschaltet");
      },
      configurable: true,
    });
    expect(M.entwurfLesen()).toBe(null);
    expect(M.entwurfSchreiben([{ key: "a", sichtbar: true }])).toBe(false);
    expect(() => M.entwurfVerwerfen()).not.toThrow();
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    expect(() =>
      M.renderViewPrefs(main, { rows: ROWS, gespeichert: GESPEICHERT }, {})
    ).not.toThrow();
    // Die Warnung greift trotzdem, weil sie nicht am Speicher haengt.
    const cb = main.querySelector(".aiw-vp-schalter");
    cb.checked = false;
    cb.dispatchEvent(new win.Event("change"));
    expect(M.hatUngespeichertes()).toBe(true);
  });
});

describe("cockpit_viewprefs.js — Render (Build 546)", () => {
  const ROWS = [
    { id: "a", label: "Alpha", group: "Ueberblick" },
    { id: "b", label: "Beta", group: "Verwaltung", versteckt: true },
  ];
  const GESPEICHERT = [
    { key: "a", sichtbar: true },
    { key: "b", sichtbar: false },
  ];

  // VF16 ---------------------------------------------------------------------
  it("VF16: je Bereich eine Zeile; Ausgeblendetes bleibt sichtbar in der Liste", () => {
    const win = _ctx();
    const M = _modApi(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    M.renderViewPrefs(main, { rows: ROWS, gespeichert: GESPEICHERT }, {});

    const zeilen = main.querySelectorAll(".aiw-vp-zeile");
    expect(zeilen.length).toBe(2);
    expect(main.textContent).toContain("Alpha");
    // Der ausgeblendete Bereich VERSCHWINDET NICHT — er wird markiert. Sonst
    // muesste man raten, was fehlt.
    expect(main.textContent).toContain("Beta");
    expect(zeilen[1].className).toContain("is-versteckt");
    expect(zeilen[1].querySelector(".aiw-vp-schalter").checked).toBe(false);
    // Zahlen in der Kopfzeile.
    expect(main.textContent).toContain("1 sichtbar");
    expect(main.textContent).toContain("1 ausgeblendet");
    // Pfeile an den Raendern sind gesperrt.
    const pfeile0 = zeilen[0].querySelectorAll(".aiw-vp-pfeil");
    expect(pfeile0[0].disabled).toBe(true);
    expect(pfeile0[1].disabled).toBe(false);
  });

  // VF17 ---------------------------------------------------------------------
  it("VF17: Speichern ist ohne Aenderung gesperrt und sagt das", () => {
    const win = _ctx();
    const M = _modApi(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    M.renderViewPrefs(main, { rows: ROWS, gespeichert: GESPEICHERT }, {});
    const btn = main.querySelector(".aiw-btn-primary");
    expect(btn.disabled).toBe(true);
    expect(main.textContent).toContain("Keine ungespeicherten");
  });

  // VF18 ---------------------------------------------------------------------
  it("VF18: onSave bekommt die bearbeitete Reihenfolge", () => {
    const win = _ctx();
    const M = _modApi(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    let gesehen = null;
    M.renderViewPrefs(
      main,
      { rows: ROWS, gespeichert: GESPEICHERT },
      { onSave: (n) => { gesehen = n; } }
    );
    // 'b' nach oben.
    main.querySelectorAll(".aiw-vp-zeile")[1]
      .querySelectorAll(".aiw-vp-pfeil")[0]
      .dispatchEvent(new win.Event("click"));
    const btn = main.querySelector(".aiw-btn-primary");
    expect(btn.disabled).toBe(false);
    btn.dispatchEvent(new win.Event("click"));
    expect(gesehen).toEqual([
      { key: "b", sichtbar: false },
      { key: "a", sichtbar: true },
    ]);
  });
});
