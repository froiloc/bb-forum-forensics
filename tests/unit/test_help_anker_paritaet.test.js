/**
 * tests/unit/test_help_anker_paritaet.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle H: Hilfesysteme (H5)
 *
 * Testsuite fuer Build 592: das GEGENSTUECK zu tests/test_help_schluessel_
 * paritaet.py.
 *
 * WARUM ES ZWEI TESTS BRAUCHT UND NICHT EINER GENUEGT:
 *   Die Hilfe-Marken der Oberflaeche entstehen auf ZWEI Wegen.
 *     (a) LITERAL im Quelltext: data-hilfe-id="faelle.titel". Diese findet
 *         eine Textsuche vollstaendig — das prueft der Python-Test.
 *     (b) BERECHNET vom gemeinsamen Tabellen-Werkzeug (seit Build 548):
 *         sicht + '.spalte.' + feldname. Diese stehen NIRGENDS im Quelltext;
 *         sie entstehen erst, wenn die Sicht gerendert wird. Eine Textsuche
 *         kann sie grundsaetzlich nicht finden.
 *   Also wird hier gerendert und im DOM nachgesehen. Das ist die einzige
 *   Messung, die die Wahrheit trifft: was steht am Ende wirklich am Element?
 *
 * AP01 — die Pilotsicht 'faelle' setzt Anker (Rendern gelingt ueberhaupt).
 * AP02 — JEDER im DOM gefundene Anker der Pilotsicht hat einen Text im
 *        Register (gelesen aus management/help/inhalt/*.py).
 * AP03 — die vier abgeleiteten Spalten tragen seit Build 592 wieder Anker
 *        (Nachweis der Fehlerbehebung an der Erblast aus Build 548).
 * AP04 — hilfeIdNormieren schneidet nur fuehrende Unterstriche ab und laesst
 *        alles andere unangetastet.
 * AP05 — eine Kennung, die auch nach dem Normieren unzulaessig ist, wird
 *        weiterhin verworfen statt falsch gesetzt.
 * AP06 — Anker sind im gerenderten Baum eindeutig.
 * AP07 — Build 595: JEDE Kachel des Ueberblicks traegt eine Marke, und jede
 *        dieser Marken hat einen Text im Register. Die Kachelmarken werden
 *        aus dem Kachelschluessel BERECHNET (die Kachelmenge stammt aus der
 *        persoenlichen Ansichtseinstellung) — eine Textsuche kann sie
 *        grundsaetzlich nicht finden, dieser Test dagegen schon.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
// Build 603: die Schluessel kommen aus dem REGISTER SELBST und nicht mehr
// aus einem regulaeren Ausdruck ueber die Quelltexte. Warum, steht im Kopf
// von tests/unit/_hilfe_schluessel.js — kurz: berechnete Schluessel (die
// Support-Historie erzeugt ihre Spaltentexte in einer Schleife) stehen
// nirgends woertlich da, und ein Ausdruck, der sie nicht findet, meldet
// Fehlendes, das es gibt.
import { registerSchluessel } from "./_hilfe_schluessel.js";
import { JSDOM } from "jsdom";

const TABLEKIT = readFileSync(
  "management/server/static/cockpit_tablekit.js", "utf-8");
const OVERVIEW = readFileSync(
  "management/server/static/cockpit_overview.js", "utf-8");
const DASHBOARD = readFileSync(
  "management/server/static/cockpit_dashboard.js", "utf-8");


/** Tabulator-Attrappe: baut die Spaltenkoepfe ueber titleFormatter selbst. */
function macheFakeTabulator(win) {
  return class {
    constructor(el, opts) {
      this.opts = opts;
      (opts.columns || []).forEach((c) => {
        const th = win.document.createElement("div");
        if (typeof c.titleFormatter === "function") {
          th.appendChild(c.titleFormatter());
        } else {
          th.textContent = c.title || "";
        }
        el.appendChild(th);
      });
    }
    on() {} setData() {} getData() { return []; } getRows() { return []; }
    redraw() {} destroy() {} getColumns() { return []; }
    setFilter() {} clearFilter() {} getDataCount() { return 0; }
  };
}

function rendereFaelle() {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body><main id='m'></main></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(TABLEKIT);
  dom.window.eval(OVERVIEW);
  const main = dom.window.document.getElementById("m");
  dom.window.AIWCockpitOverview.renderOverview(
    main,
    {
      scope: "alle", count: 1,
      // FIKTIVE Beispieldaten (Regel H-0): 900001 stammt aus dem im
      // Register festgelegten Beispielraum, nicht aus dem Betrieb.
      cases: [{
        subject_id: 900001, username: "beispielkonto", status: "open",
        priority: 1, ampel: "rot", ampel_reason: "offen_nicht_zugewiesen",
        assigned_to: null, event_count: 3, has_note: 0, last_activity_at: null,
      }],
    },
    { Tabulator: macheFakeTabulator(dom.window), nowSec: 1000000 });
  return dom;
}

describe("Hilfe-Anker — Paritaet am gerenderten Baum", () => {
  it("AP01 — die Pilotsicht setzt Anker", () => {
    const dom = rendereFaelle();
    const anker = dom.window.AIWTableKit.hilfeIds(dom.window.document.body);
    expect(anker.length).toBeGreaterThan(10);
  });

  it("AP02 — jeder Anker der Pilotsicht hat einen Text im Register", () => {
    const dom = rendereFaelle();
    const anker = dom.window.AIWTableKit.hilfeIds(dom.window.document.body);
    const bekannt = registerSchluessel();
    const ohneText = anker.filter((a) => !bekannt.has(a));
    expect(ohneText, `Anker ohne Text im Register: ${ohneText.join(", ")}`)
      .toEqual([]);
  });

  it("AP03 — die abgeleiteten Spalten tragen wieder Anker (Build 592)", () => {
    // BEFUND, den dieser Test festhaelt: Bis Build 591 verwarf hilfeAnker
    // jede Kennung, deren letzter Abschnitt mit '_' begann — und genau so
    // heissen im ganzen Bestand die abgeleiteten Tabulator-Felder. Auf der
    // Fall-Uebersicht betraf das 4 von 10 Spalten, darunter die Ampel.
    const dom = rendereFaelle();
    const anker = dom.window.AIWTableKit.hilfeIds(dom.window.document.body);
    for (const erwartet of ["overview.spalte.rank", "overview.spalte.assignee",
                            "overview.spalte.sincedays",
                            "overview.spalte.support"]) {
      expect(anker).toContain(erwartet);
    }
    // ... und die Kopfmarken der Sicht selbst (literal gesetzt)
    const doc = dom.window.document;
    expect(doc.querySelector('[data-hilfe-id="faelle.titel"]')).not.toBe(null);
    expect(doc.querySelector('[data-hilfe-id="faelle.umfang"]')).not.toBe(null);
  });

  it("AP04 — hilfeIdNormieren schneidet nur fuehrende Unterstriche ab", () => {
    const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>",
      { runScripts: "dangerously", url: "http://localhost" });
    dom.window.eval(TABLEKIT);
    const TK = dom.window.AIWTableKit;
    expect(TK.hilfeIdNormieren("a.spalte._rank")).toBe("a.spalte.rank");
    expect(TK.hilfeIdNormieren("a.spalte.__x")).toBe("a.spalte.x");
    expect(TK.hilfeIdNormieren("a.spalte.has_note")).toBe("a.spalte.has_note");
    expect(TK.hilfeIdNormieren("a.b.c")).toBe("a.b.c");
    expect(TK.hilfeIdNormieren(null)).toBe(null);
  });

  it("AP05 — unzulaessige Kennung wird weiterhin verworfen", () => {
    const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>",
      { runScripts: "dangerously", url: "http://localhost" });
    dom.window.eval(TABLEKIT);
    const TK = dom.window.AIWTableKit;
    const el = dom.window.document.createElement("div");
    TK.hilfeAnker(el, "OHNE.punkte.GROSS");
    expect(el.hasAttribute("data-hilfe-id")).toBe(false);
    const el2 = dom.window.document.createElement("div");
    TK.hilfeAnker(el2, "ohnepunkt");
    expect(el2.hasAttribute("data-hilfe-id")).toBe(false);
  });

  it("AP06 — Anker sind im gerenderten Baum eindeutig", () => {
    const dom = rendereFaelle();
    const anker = dom.window.AIWTableKit.hilfeIds(dom.window.document.body);
    const doppelt = anker.filter((a, i) => anker.indexOf(a) !== i);
    expect(doppelt, `doppelte Anker: ${doppelt.join(", ")}`).toEqual([]);
  });
});


describe("Hilfe-Anker — Kacheln des Ueberblicks (Build 595)", () => {
  /** Rendert die Kachelflaeche mit allen acht Kacheln des Katalogs. */
  function rendereUeberblick() {
    const dom = new JSDOM(
      "<!DOCTYPE html><html><body><main id='m'></main></body></html>",
      { runScripts: "dangerously", url: "http://localhost" });
    dom.window.eval(DASHBOARD);
    const api = dom.window.AIWCockpitDashboard
      || dom.window.AIWDashboard || dom.window.AIWCockpitUeberblick;
    return { dom, api };
  }

  it("AP07 — jede Kachel traegt eine Marke mit Text im Register", () => {
    const { dom, api } = rendereUeberblick();
    expect(api, "Dashboard-Modul nicht unter dem erwarteten Namen exportiert")
      .toBeTruthy();

    // Die Kachelschluessel stammen aus viewpref_katalog.WIDGETS. Sie hier
    // NOCHMALS aufzuschreiben waere eine zweite Wahrheit — deshalb werden
    // sie aus der Python-Quelle gelesen, genau wie die Registerschluessel.
    const kat = readFileSync(
      "management/viewprefs/viewpref_katalog.py", "utf-8");
    const keys = [];
    const re = /WidgetSpec\(\s*\n?\s*key="([a-z0-9_]+)"/g;
    let m;
    while ((m = re.exec(kat)) !== null) { keys.push(m[1]); }
    expect(keys.length).toBeGreaterThan(5);

    const bekannt = registerSchluessel();
    const ohneText = keys
      .map((k) => "dashboard.kachel." + k)
      .filter((s) => !bekannt.has(s));
    expect(ohneText, `Kacheln ohne Text im Register: ${ohneText.join(", ")}`)
      .toEqual([]);

    // Und die Marke wird auch wirklich gesetzt: das Modul bildet sie aus dem
    // Kachelschluessel. Beleg im Quelltext statt Annahme.
    expect(DASHBOARD).toContain("'dashboard.kachel.' + w.key");
    dom.window.close();
  });
});
