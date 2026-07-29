/**
 * tests/unit/test_cockpit_gruppen.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 568: zweistufige Ordnung (Ticket ffbfb7f5).
 *
 * GRP01 — nachGruppenOrdnen macht eine VERSCHRAENKTE Liste gruppenrein. Das
 *         ist der Kern: bis Build 567 erzeugte genau so eine Liste denselben
 *         Gruppenkopf mehrfach in der Navigation.
 * GRP02 — die Reihenfolge INNERHALB einer Gruppe bleibt unangetastet.
 * GRP03 — eine vorgegebene Gruppenfolge wird eingehalten; Gruppen, die darin
 *         fehlen, werden ANGEHAENGT statt verworfen (Grundregel 1).
 * GRP04 — buildNav zeichnet danach jeden Gruppenkopf genau EINMAL.
 * GRP05 — GROUP_ORDER deckt alle Gruppen des Katalogs ab; keine Gruppe faellt
 *         hinten heraus, weil jemand sie zu ergaenzen vergass.
 * GRP06 — kein Katalogeintrag hat eine leere oder fehlende Gruppe.
 * GRP07 — navViews liefert gruppenreine Sichten (mit und ohne Vorliebe).
 * GRP08 — Gruppen einklappen: Zustandsrechnung und Wirkung im DOM.
 * GRP09 — eine eingeklappte Gruppe mit der AKTIVEN Sicht wird aufgeklappt.
 * GRP10 — gruppeVerschieben bewegt den ganzen Block, nicht eine Zeile.
 * GRP11 — verschiebeInGruppe endet am GRUPPENrand, nicht am Listenrand.
 * GRP12 — beide Bewegungen erhalten die Gruppenreinheit; die Nutzlast bleibt
 *         eine flache Liste (keine Schemaaenderung).
 *
 * Version: v0.8.568 · Build: 568 · 2026-07-29
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _cockpit = readFileSync("management/server/static/cockpit.js", "utf-8");
const _prefs = readFileSync(
  "management/server/static/cockpit_viewprefs.js", "utf-8");

function _win(src) {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body><nav id='n'></nav></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(src);
  return dom.window;
}

const V = (id, group) => ({ id: id, group: group, label: id, cap: null });

describe("Zweistufige Ordnung (Build 568)", () => {
  // GRP01 -------------------------------------------------------------------
  it("GRP01: verschraenkte Liste wird gruppenrein", () => {
    const api = _win(_cockpit).AIWCockpit;
    const roh = [V("a", "X"), V("b", "Y"), V("c", "X"), V("d", "Y")];
    const out = api.nachGruppenOrdnen(roh, null);
    expect(out.map((v) => v.id)).toEqual(["a", "c", "b", "d"]);
    // Jede Gruppe genau einmal am Stueck.
    const folgen = out.map((v) => v.group);
    expect(folgen).toEqual(["X", "X", "Y", "Y"]);
  });

  // GRP02 -------------------------------------------------------------------
  it("GRP02: die Ordnung innerhalb einer Gruppe bleibt erhalten", () => {
    const api = _win(_cockpit).AIWCockpit;
    const roh = [V("b", "X"), V("z", "Y"), V("a", "X"), V("c", "X")];
    const out = api.nachGruppenOrdnen(roh, null);
    // b vor a vor c — so stand es in der Eingabe, und daran wird nicht
    // stillschweigend sortiert.
    expect(out.map((v) => v.id)).toEqual(["b", "a", "c", "z"]);
  });

  // GRP03 -------------------------------------------------------------------
  it("GRP03: vorgegebene Gruppenfolge gilt, Unbekanntes wird angehaengt", () => {
    const api = _win(_cockpit).AIWCockpit;
    const roh = [V("a", "X"), V("b", "Y"), V("c", "Z")];
    const out = api.nachGruppenOrdnen(roh, ["Y", "X"]);
    // Y, X wie vorgegeben — und Z hinten dran statt verschwunden.
    expect(out.map((v) => v.group)).toEqual(["Y", "X", "Z"]);

    // Eine Gruppe in der Vorgabe, die es gar nicht gibt, stoert nicht.
    const out2 = api.nachGruppenOrdnen(roh, ["Q", "Z", "X", "Y"]);
    expect(out2.map((v) => v.group)).toEqual(["Z", "X", "Y"]);
  });

  // GRP04 -------------------------------------------------------------------
  it("GRP04: buildNav zeichnet jeden Gruppenkopf genau einmal", () => {
    const win = _win(_cockpit);
    const api = win.AIWCockpit;
    const nav = win.document.getElementById("n");
    const roh = [V("a", "X"), V("b", "Y"), V("c", "X")];

    // Vorher (ungeordnet): drei Koepfe fuer zwei Gruppen — der gemeldete
    // Fehler, hier zur Absicherung festgehalten.
    api.buildNav(nav, roh, {}, "a", () => {});
    const vorher = [...nav.querySelectorAll(".aiw-navgroup")]
      .map((e) => e.getAttribute("data-group"));
    expect(vorher.length).toBeGreaterThan(new Set(vorher).size);

    // Nachher: geordnet, jeder Kopf einmal.
    api.buildNav(nav, api.nachGruppenOrdnen(roh, null), {}, "a", () => {});
    const nachher = [...nav.querySelectorAll(".aiw-navgroup")]
      .map((e) => e.getAttribute("data-group"));
    expect(nachher).toEqual(["X", "Y"]);
  });

  // GRP05 -------------------------------------------------------------------
  it("GRP05: GROUP_ORDER deckt alle Gruppen des Katalogs ab", () => {
    const api = _win(_cockpit).AIWCockpit;
    const imKatalog = new Set(api.VIEW_CATALOG.map((v) => v.group));
    const inFolge = new Set(api.GROUP_ORDER);
    // Eine Gruppe, die jemand einfuehrt und hier zu ergaenzen vergisst,
    // rutschte sonst kommentarlos ans Ende der Navigation.
    [...imKatalog].forEach((g) => {
      expect(inFolge.has(g)).toBe(true);
    });
    // Und umgekehrt keine Karteileichen in der Vorgabe.
    [...inFolge].forEach((g) => {
      expect(imKatalog.has(g)).toBe(true);
    });
  });

  // GRP06 -------------------------------------------------------------------
  it("GRP06: kein Katalogeintrag ohne Gruppe", () => {
    const api = _win(_cockpit).AIWCockpit;
    api.VIEW_CATALOG.forEach((v) => {
      expect(typeof v.group).toBe("string");
      expect(v.group.trim().length).toBeGreaterThan(0);
    });
  });

  // GRP07 -------------------------------------------------------------------
  it("GRP07: navViews liefert gruppenreine Sichten", () => {
    const api = _win(_cockpit).AIWCockpit;
    const caps = { "dashboard.view": "alle", "assignment.edit": "alle",
                   "workload.view": "alle", "crossref.view": "alle" };

    function gruppenrein(views) {
      const gesehen = [];
      let letzte = null;
      views.forEach((v) => {
        if (v.group !== letzte) {
          expect(gesehen.includes(v.group)).toBe(false);
          gesehen.push(v.group);
          letzte = v.group;
        }
      });
      return gesehen;
    }

    // Ohne Vorliebe: Vorgabefolge.
    const ohne = api.navViews(caps, null);
    const folgeOhne = gruppenrein(ohne);
    expect(folgeOhne[0]).toBe("Ueberblick");

    // Mit einer VERSCHRAENKTEN Vorliebe: trotzdem gruppenrein.
    const prefs = ohne.map((v) => ({ key: v.id, sichtbar: true })).reverse();
    gruppenrein(api.navViews(caps, prefs));
  });

  // GRP08 -------------------------------------------------------------------
  it("GRP08: Gruppen lassen sich einklappen", () => {
    const win = _win(_cockpit);
    const api = win.AIWCockpit;

    expect(api.navGruppeUmschalten({}, "X")).toEqual({ X: true });
    expect(api.navGruppeUmschalten({ X: true }, "X")).toEqual({ X: false });
    // Andere Gruppen bleiben unberuehrt.
    expect(api.navGruppeUmschalten({ Y: true }, "X")).toEqual(
      { Y: true, X: true });

    const nav = win.document.getElementById("n");
    const views = api.nachGruppenOrdnen(
      [V("a", "X"), V("b", "X"), V("c", "Y")], null);
    api.buildNav(nav, views, {}, "c", () => {});
    const kopfX = nav.querySelector('[data-group="X"]');
    expect(kopfX.getAttribute("aria-expanded")).toBe("true");

    kopfX.dispatchEvent(new win.Event("click"));
    const kopfX2 = nav.querySelector('[data-group="X"]');
    expect(kopfX2.getAttribute("aria-expanded")).toBe("false");
    expect(nav.querySelector('[data-group-body="X"]').hidden).toBe(true);
    // Die andere Gruppe bleibt offen.
    expect(nav.querySelector('[data-group-body="Y"]').hidden).toBe(false);
  });

  // GRP09 -------------------------------------------------------------------
  it("GRP09: die Gruppe der aktiven Sicht klappt auf", () => {
    const win = _win(_cockpit);
    const api = win.AIWCockpit;
    const nav = win.document.getElementById("n");
    const views = api.nachGruppenOrdnen(
      [V("a", "X"), V("c", "Y")], null);

    api.buildNav(nav, views, {}, "c", () => {});
    nav.querySelector('[data-group="X"]').dispatchEvent(new win.Event("click"));
    expect(nav.querySelector('[data-group-body="X"]').hidden).toBe(true);

    // Jetzt wird eine Sicht AUS der eingeklappten Gruppe aktiv: sie muss
    // sichtbar werden, sonst behauptete die Leiste, es gebe sie nicht.
    api.buildNav(nav, views, {}, "a", () => {});
    expect(nav.querySelector('[data-group-body="X"]').hidden).toBe(false);
    expect(nav.querySelector('[data-group="X"]')
      .getAttribute("aria-expanded")).toBe("true");
  });

  // GRP10 -------------------------------------------------------------------
  it("GRP10: gruppeVerschieben bewegt den ganzen Block", () => {
    const api = _win(_prefs).AIWCockpitViewPrefs;
    const rows = [V("a", "X"), V("b", "X"), V("c", "Y")];
    const out = api.gruppeVerschieben(rows, "Y", -1);
    expect(out.map((r) => r.id)).toEqual(["c", "a", "b"]);
    // Ueber den Rand: wirkungslos, kein Fehler.
    expect(api.gruppeVerschieben(rows, "X", -1).map((r) => r.id))
      .toEqual(["a", "b", "c"]);
    expect(api.gruppeVerschieben(rows, "gibtsnicht", 1).map((r) => r.id))
      .toEqual(["a", "b", "c"]);
  });

  // GRP11 -------------------------------------------------------------------
  it("GRP11: verschiebeInGruppe endet am Gruppenrand", () => {
    const api = _win(_prefs).AIWCockpitViewPrefs;
    const rows = [V("a", "X"), V("b", "X"), V("c", "Y")];

    expect(api.verschiebeInGruppe(rows, "b", -1).map((r) => r.id))
      .toEqual(["b", "a", "c"]);
    // 'b' ist die LETZTE ihrer Gruppe: ein Zug nach unten wuerde sie in die
    // Gruppe Y tragen. Die Zugehoerigkeit legt der Katalog fest, nicht die
    // persoenliche Ordnung — also wirkungslos.
    expect(api.verschiebeInGruppe(rows, "b", 1).map((r) => r.id))
      .toEqual(["a", "b", "c"]);
    expect(api.verschiebeInGruppe(rows, "c", -1).map((r) => r.id))
      .toEqual(["a", "b", "c"]);
  });

  // GRP12 -------------------------------------------------------------------
  it("GRP12: beide Bewegungen bleiben gruppenrein und flach", () => {
    const api = _win(_prefs).AIWCockpitViewPrefs;
    let rows = [V("a", "X"), V("b", "Y"), V("c", "X"), V("d", "Y")];
    rows = api.flachAus(api.gruppenAus(rows));       // einmal ordnen
    rows = api.gruppeVerschieben(rows, "Y", -1);
    rows = api.verschiebeInGruppe(rows, "d", -1);

    const folgen = [];
    let letzte = null;
    rows.forEach((r) => {
      if (r.group !== letzte) {
        expect(folgen.includes(r.group)).toBe(false);
        folgen.push(r.group);
        letzte = r.group;
      }
    });

    // Die Nutzlast bleibt eine FLACHE Liste — keine Schemaaenderung, keine
    // Migration (mc 2026-07-29).
    const nutzlast = api.zuNutzlast(rows);
    expect(Array.isArray(nutzlast)).toBe(true);
    nutzlast.forEach((n) => {
      expect(Object.keys(n).sort()).toEqual(["key", "sichtbar"]);
    });
  });
});
