/**
 * tests/unit/test_cockpit_navsuche.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 569: Suchfeld der Navigationsleiste (Ticket ace2cc2a).
 *
 * NS01 — Normalisierung faltet Umlaute in BEIDE Richtungen. Der Katalog mischt
 *        die Schreibweisen ('Nächstbeste Aktion' neben 'Fristen
 *        (Verjaehrung)'), also muss 'kapazität' auch 'Kapazitaet' finden.
 * NS02 — Teilwortsuche: 'kapa' findet die Kapazitaetssichten.
 * NS03 — mehrere Begriffe wirken als UND, nicht als ODER.
 * NS04 — leere Eingabe liefert die Liste unveraendert (kein Filter).
 * NS05 — die Reihenfolge der Treffer ist die Reihenfolge der Vorgabe; es gibt
 *        KEINE Trefferwertung (mc).
 * NS06 — gesucht wird auch in den STICHWORTEN, nicht nur in der Beschriftung:
 *        'urlaub' findet die Kapazitaetspflege, obwohl das Wort in keiner
 *        Beschriftung steht.
 * NS07 — jede der 42 Sichten ist ueber mindestens ein Stichwort erreichbar.
 * NS08 — DIE RECHTEGRENZE: die Suche arbeitet auf navViewsAlle und findet
 *        niemals eine Sicht, fuer die das Recht fehlt.
 * NS09 — ausgeblendete Sichten WERDEN gefunden (mc) und sind im DOM als
 *        ausgeblendet gekennzeichnet.
 * NS10 — jeder Katalogeintrag hat nicht-leere Stichworte (Konformitaet gegen
 *        das Verrotten: eine neue Sicht kostet einen Eintrag).
 * NS11 — die Stichworte sind normalisiert brauchbar (kein Eintrag, der nach
 *        der Faltung leer waere) und keine zwei Sichten sind wortgleich.
 * NS12 — das Suchfeld ueberlebt den Neuaufbau der Liste: dasselbe Element,
 *        Wert und Fokus bleiben. (Das war die eigentliche Falle: buildNav
 *        leert das Fach, in das es zeichnet.)
 * NS13 — solange gefiltert wird, sind alle Gruppen offen; ein Treffer kann
 *        sich nicht in einer zugeklappten Gruppe verstecken.
 * NS14 — kein Treffer wird BENANNT, mit Zahl - statt leerer Flaeche.
 * NS15 — Escape leert das Feld und meldet das.
 *
 * Version: v0.8.569 · Build: 569 · 2026-07-29
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _cockpit = readFileSync("management/server/static/cockpit.js", "utf-8");

function _ctx() {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body><nav id='nav'></nav></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(_cockpit);
  return { win: dom.window, api: dom.window.AIWCockpit,
           nav: dom.window.document.getElementById("nav") };
}

/** Rechte, die praktisch alles freischalten (fuer Filtertests). */
function _alleRechte(api) {
  const caps = {};
  api.VIEW_CATALOG.forEach((v) => { if (v.cap) { caps[v.cap] = "alle"; } });
  return caps;
}

describe("Navigationssuche (Build 569)", () => {
  // NS01 --------------------------------------------------------------------
  it("NS01: Umlaute werden in beide Richtungen gefaltet", () => {
    const { api } = _ctx();
    expect(api.suchNormal("Kapazität")).toBe("kapazitaet");
    expect(api.suchNormal("Kapazitaet")).toBe("kapazitaet");
    expect(api.suchNormal("Nächstbeste Aktion")).toBe("naechstbeste aktion");
    expect(api.suchNormal("Übergabe")).toBe("uebergabe");
    expect(api.suchNormal("Maßnahme")).toBe("massnahme");
    // Der Kern: beide Schreibweisen treffen denselben Katalogeintrag.
    const kap = api.VIEW_CATALOG.filter((v) => v.id === "capacity");
    expect(api.navSuche(kap, "kapazität").length).toBe(1);
    expect(api.navSuche(kap, "kapazitaet").length).toBe(1);
    const naechst = api.VIEW_CATALOG.filter((v) => v.id === "nextactions");
    expect(api.navSuche(naechst, "naechstbeste").length).toBe(1);
    expect(api.navSuche(naechst, "nächstbeste").length).toBe(1);
  });

  // NS02 --------------------------------------------------------------------
  it("NS02: Teilwortsuche", () => {
    const { api } = _ctx();
    const ids = api.navSuche(api.VIEW_CATALOG, "kapa").map((v) => v.id);
    expect(ids).toContain("capacity");
    expect(ids).toContain("capacity_pflege");
    expect(api.navSuche(api.VIEW_CATALOG, "verjaehr").map((v) => v.id))
      .toContain("limitation");
  });

  // NS03 --------------------------------------------------------------------
  it("NS03: mehrere Begriffe sind UND, nicht ODER", () => {
    const { api } = _ctx();
    const nurArbeitszeit = api.navSuche(api.VIEW_CATALOG, "arbeitszeit");
    const mitUrlaub = api.navSuche(api.VIEW_CATALOG, "arbeitszeit urlaub");
    expect(mitUrlaub.length).toBeGreaterThan(0);
    // Eingrenzen macht die Liste KUERZER. Bei ODER waere sie laenger.
    expect(mitUrlaub.length).toBeLessThanOrEqual(nurArbeitszeit.length);
    mitUrlaub.forEach((v) => {
      const t = api.sichtSuchtext(v);
      expect(t).toContain("arbeitszeit");
      expect(t).toContain("urlaub");
    });
  });

  // NS04 --------------------------------------------------------------------
  it("NS04: leere Eingabe filtert nicht", () => {
    const { api } = _ctx();
    expect(api.navSuche(api.VIEW_CATALOG, "").length)
      .toBe(api.VIEW_CATALOG.length);
    expect(api.navSuche(api.VIEW_CATALOG, "   ").length)
      .toBe(api.VIEW_CATALOG.length);
    expect(api.navSuche(api.VIEW_CATALOG, null).length)
      .toBe(api.VIEW_CATALOG.length);
  });

  // NS05 --------------------------------------------------------------------
  it("NS05: keine Trefferwertung, Reihenfolge bleibt", () => {
    const { api } = _ctx();
    const quelle = api.VIEW_CATALOG.slice();
    const treffer = api.navSuche(quelle, "e");   // trifft fast alles
    const erwartet = quelle
      .filter((v) => treffer.some((t) => t.id === v.id))
      .map((v) => v.id);
    expect(treffer.map((v) => v.id)).toEqual(erwartet);
  });

  // NS06 --------------------------------------------------------------------
  it("NS06: gesucht wird auch in den Stichworten", () => {
    const { api } = _ctx();
    // 'urlaub' steht in KEINER Beschriftung.
    const inBeschriftung = api.VIEW_CATALOG.filter(
      (v) => api.suchNormal(v.label).indexOf("urlaub") !== -1);
    expect(inBeschriftung.length).toBe(0);
    expect(api.navSuche(api.VIEW_CATALOG, "urlaub").map((v) => v.id))
      .toContain("capacity_pflege");
    // Weitere Fachwoerter, die niemand in der Beschriftung finden wuerde.
    expect(api.navSuche(api.VIEW_CATALOG, "rbac").map((v) => v.id))
      .toContain("policy");
    expect(api.navSuche(api.VIEW_CATALOG, "hashkette").map((v) => v.id))
      .toContain("integrity");
  });

  // NS07 --------------------------------------------------------------------
  it("NS07: jede Sicht ist ueber ein Stichwort erreichbar", () => {
    const { api } = _ctx();
    api.VIEW_CATALOG.forEach((v) => {
      const woerter = api.suchNormal(v.stichworte).split(" ")
        .filter((w) => w.length > 2);
      expect(woerter.length).toBeGreaterThan(0);
      const treffer = api.navSuche(api.VIEW_CATALOG, woerter[0])
        .map((t) => t.id);
      expect(treffer).toContain(v.id);
    });
  });

  // NS08 --------------------------------------------------------------------
  it("NS08: die Suche ueberschreitet die Rechtegrenze nicht", () => {
    const { api } = _ctx();
    // Nur EIN Recht: das der Personalverwaltung.
    const eine = api.VIEW_CATALOG.filter((v) => v.id === "personnel")[0];
    const caps = {};
    caps[eine.cap] = "alle";
    const erreichbar = api.navViewsAlle(caps, []);
    const ids = erreichbar.map((v) => v.id);
    expect(ids).toContain("personnel");
    expect(ids).not.toContain("policy");

    // Ein Begriff, der ausserhalb der Rechte laege, findet NICHTS.
    expect(api.navSuche(erreichbar, "hashkette").length).toBe(0);
    expect(api.navSuche(erreichbar, "rbac").length).toBe(0);
    // Und innerhalb sehr wohl.
    expect(api.navSuche(erreichbar, "mitarbeiter").map((v) => v.id))
      .toContain("personnel");
  });

  // NS09 --------------------------------------------------------------------
  it("NS09: ausgeblendete Sichten werden gefunden und gekennzeichnet", () => {
    const { win, api, nav } = _ctx();
    const caps = _alleRechte(api);
    // 'capacity_pflege' ausdruecklich ausblenden.
    const prefs = api.VIEW_CATALOG.map((v) => ({
      key: v.id, sichtbar: v.id !== "capacity_pflege",
    }));
    const alle = api.navViewsAlle(caps, prefs);
    const treffer = api.navSuche(alle, "urlaub");
    const gefunden = treffer.filter((v) => v.id === "capacity_pflege")[0];
    expect(gefunden).toBeTruthy();
    expect(gefunden.versteckt).toBe(true);

    // navViews (ohne Ausgeblendete) enthaelt sie dagegen NICHT — die Suche
    // ist der Mehrwert, nicht ein Aufweichen der Einstellung.
    expect(api.navViews(caps, prefs).map((v) => v.id))
      .not.toContain("capacity_pflege");

    api.buildNav(nav, treffer, caps, null, () => {},
                 0, { aktiv: true, gesamt: alle.length });
    const eintrag = nav.querySelector('[data-view-id="capacity_pflege"]');
    expect(eintrag).toBeTruthy();
    expect(eintrag.classList.contains("aiw-navitem-versteckt")).toBe(true);
    expect(eintrag.querySelector(".aiw-navitem-vmark").textContent)
      .toBe("ausgeblendet");
  });

  // NS10 --------------------------------------------------------------------
  it("NS10: jeder Katalogeintrag hat Stichworte", () => {
    const { api } = _ctx();
    const ohne = api.VIEW_CATALOG
      .filter((v) => !v.stichworte || String(v.stichworte).trim() === "")
      .map((v) => v.id);
    expect(ohne).toEqual([]);
    // Build 574: 43 (neu: 'faelle' — Fallübersicht).
    expect(api.VIEW_CATALOG.length).toBe(43);
  });

  // NS11 --------------------------------------------------------------------
  it("NS11: Stichworte sind brauchbar und je Sicht verschieden", () => {
    const { api } = _ctx();
    const gesehen = {};
    api.VIEW_CATALOG.forEach((v) => {
      const n = api.suchNormal(v.stichworte);
      // Ein Eintrag, der nach der Faltung leer waere, waere eine leere Zusage.
      expect(n.length).toBeGreaterThan(3);
      expect(gesehen[n]).toBeUndefined();
      gesehen[n] = v.id;
    });
  });

  // NS12 --------------------------------------------------------------------
  it("NS12: das Suchfeld ueberlebt den Neuaufbau der Liste", () => {
    const { win, api, nav } = _ctx();
    const caps = _alleRechte(api);
    const liste = api.navGeruest(nav);
    let letzte = null;
    const feld1 = api.buildNavSuche(nav, "kapa", (w) => { letzte = w; }, "");
    feld1.focus();
    expect(win.document.activeElement).toBe(feld1);

    // Die Liste wird neu gezeichnet — das Feld liegt in einem anderen Fach.
    api.buildNav(liste, api.navSuche(api.navViewsAlle(caps, []), "kapa"),
                 caps, null, () => {}, 0, { aktiv: true, gesamt: 42 });

    const feld2 = api.buildNavSuche(nav, "kapa", (w) => { letzte = w; }, "");
    expect(feld2).toBe(feld1);              // dasselbe Element
    expect(feld2.value).toBe("kapa");
    expect(win.document.activeElement).toBe(feld2);   // Fokus erhalten
  });

  // NS13 --------------------------------------------------------------------
  it("NS13: waehrend der Suche sind alle Gruppen offen", () => {
    const { win, api, nav } = _ctx();
    const caps = _alleRechte(api);
    // Alle Gruppen als eingeklappt merken. DER SCHLUESSEL MUSS STIMMEN —
    // mit einem falschen Namen waere der Zustand nie gesetzt, alle Gruppen
    // waeren ohnehin offen, und die Pruefung unten waere gruen ohne etwas
    // zu pruefen ("gruen aber tot").
    const zu = {};
    api.GROUP_ORDER.forEach((g) => { zu[g] = true; });
    win.localStorage.setItem("aiw.cockpit.navZu.v1", JSON.stringify(zu));

    const treffer = api.navSuche(api.navViewsAlle(caps, []), "kapa");

    // GEGENPROBE: ohne aktive Suche greift der gemerkte Zustand wirklich.
    api.buildNav(nav, treffer, caps, null, () => {},
                 0, { aktiv: false, gesamt: 42 });
    const zuKoepfe = [...nav.querySelectorAll(".aiw-navgroup")];
    expect(zuKoepfe.length).toBeGreaterThan(0);
    zuKoepfe.forEach((k) => {
      expect(k.getAttribute("aria-expanded")).toBe("false");
    });

    // Und MIT Suche ist alles offen: ein Treffer in einer zugeklappten
    // Gruppe waere eine stille Auslassung — gefunden, aber nicht gezeigt.
    api.buildNav(nav, treffer, caps, null, () => {},
                 0, { aktiv: true, gesamt: 42 });
    const koepfe = [...nav.querySelectorAll(".aiw-navgroup")];
    expect(koepfe.length).toBeGreaterThan(0);
    koepfe.forEach((k) => {
      expect(k.getAttribute("aria-expanded")).toBe("true");
    });
    expect(nav.querySelectorAll(".aiw-navitem").length)
      .toBe(treffer.length);
    // Der gemerkte Zustand bleibt unberuehrt und gilt danach wieder.
    expect(JSON.parse(win.localStorage.getItem("aiw.cockpit.navZu.v1"))
      [api.GROUP_ORDER[0]]).toBe(true);
  });

  // NS14 --------------------------------------------------------------------
  it("NS14: kein Treffer wird benannt, mit Zahl", () => {
    const { api, nav } = _ctx();
    const caps = _alleRechte(api);
    api.buildNav(nav, [], caps, null, () => {},
                 0, { aktiv: true, gesamt: 42 });
    const leer = nav.querySelector(".aiw-navsuche-leer");
    expect(leer).toBeTruthy();
    expect(leer.textContent).toBe("Kein Treffer unter 42 erreichbaren Sichten.");

    // Ohne aktive Suche steht die Zeile NICHT da — eine leere Leiste ohne
    // Suche hat einen anderen Grund und braucht eine andere Auskunft.
    api.buildNav(nav, [], caps, null, () => {}, 0, { aktiv: false, gesamt: 42 });
    expect(nav.querySelector(".aiw-navsuche-leer")).toBeNull();
  });

  // NS15 --------------------------------------------------------------------
  it("NS15: Escape leert das Feld und meldet das", () => {
    const { win, api, nav } = _ctx();
    let letzte = "unberuehrt";
    const feld = api.buildNavSuche(nav, "kapa", (w) => { letzte = w; }, "");
    feld.dispatchEvent(new win.KeyboardEvent("keydown", { key: "Escape",
                                                          bubbles: true }));
    expect(feld.value).toBe("");
    expect(letzte).toBe("");
  });
});
