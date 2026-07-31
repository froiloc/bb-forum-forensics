/**
 * tests/unit/test_cockpit_hilfe.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle H: Hilfesysteme (H3)
 *
 * Testsuite fuer management/server/static/cockpit_hilfe.js (Build 590).
 * Testet den ECHTEN Code (readFileSync + JSDOM), nicht eine Nachbildung.
 *
 * HM01 — API verfuegbar (window.AIWCockpitHilfe), Anfangszustand aus.
 * HM02 — naechsterZustand: die fuenf Ereignisse, vollstaendig durchgespielt.
 * HM03 — 'escape' schaltet NIE ein (Abbruchtaste ist keine Einschalttaste).
 * HM04 — 'sichtwechsel' verlaesst den Modus IMMER und merkt sich die Sicht.
 * HM05 — istHilfeTaste: NUR Shift+F1; F1 allein bleibt dem Browser.
 * HM06 — koerperKlassen: setzt/entfernt nur die eigene Klasse, fremde
 *        Klassen bleiben unangetastet.
 * HM07 — Knopfklick schaltet den Modus; der Knopf zeigt den Zustand
 *        (Klasse + aria-pressed).
 * HM08 — Shift+F1 schaltet um und ruft preventDefault; F1 OHNE Shift nicht.
 * HM09 — Escape verlaesst den Modus.
 * HM10 — im Hilfemodus loest ein Klick auf eine Schaltflaeche deren
 *        Funktion NICHT aus (der Kern des Erkundungsmodus).
 * HM11 — der Hilfe-Knopf selbst bleibt im Modus klickbar (sonst kaeme man
 *        nur noch per Escape heraus).
 * HM12 — hilfeSchluessel findet das Attribut auch an einem Vorfahren.
 * HM13 — beimKlick bekommt den Schluessel gemeldet (Haken fuer H4).
 * HM14 — sichtGewechselt schaltet den laufenden Modus aus und meldet
 *        beimVerlassen.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_hilfe.js",
  "utf-8"
);

const HTML = `<!DOCTYPE html><html><body class="etwas-fremdes">
  <header class="aiw-top">
    <button type="button" id="aiw-hilfe-btn" aria-pressed="false">Hilfe</button>
  </header>
  <main class="aiw-main" id="aiw-main">
    <button type="button" id="gefaehrlich" data-hilfe-id="faelle.freigabe">
      <span id="innen">Freigeben</span>
    </button>
    <div id="ohnehilfe">Etwas ohne Hilfe</div>
  </main>
</body></html>`;

function _ctx(optionen) {
  const dom = new JSDOM(HTML, { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(_src);
  const api = dom.window.AIWCockpitHilfe;
  api.init(optionen || {});
  return { win: dom.window, doc: dom.window.document, api };
}

function _key(win, key, opts) {
  const ev = new win.KeyboardEvent(
    "keydown",
    Object.assign({ key, bubbles: true, cancelable: true }, opts || {})
  );
  win.document.dispatchEvent(ev);
  return ev;
}

describe("Hilfemodus — reine Funktionen", () => {
  let api;
  beforeEach(() => {
    api = _ctx().api;
    api.ausschalten();
  });

  it("HM01 — API vorhanden, Anfangszustand aus", () => {
    expect(typeof api.naechsterZustand).toBe("function");
    expect(api.anfangszustand()).toEqual({ an: false, sicht: null });
    expect(api.istAn()).toBe(false);
  });

  it("HM02 — Zustandsautomat vollstaendig", () => {
    const aus = { an: false, sicht: "faelle" };
    const an = { an: true, sicht: "faelle" };
    expect(api.naechsterZustand(aus, "einschalten").an).toBe(true);
    expect(api.naechsterZustand(an, "ausschalten").an).toBe(false);
    expect(api.naechsterZustand(aus, "umschalten").an).toBe(true);
    expect(api.naechsterZustand(an, "umschalten").an).toBe(false);
    // unbekanntes Ereignis laesst alles, wie es ist
    expect(api.naechsterZustand(an, "quatsch")).toEqual(an);
    // die Sicht bleibt ueber alle Schaltvorgaenge erhalten
    expect(api.naechsterZustand(an, "ausschalten").sicht).toBe("faelle");
  });

  it("HM03 — escape schaltet nie ein", () => {
    expect(api.naechsterZustand({ an: false, sicht: null }, "escape").an).toBe(false);
    expect(api.naechsterZustand({ an: true, sicht: null }, "escape").an).toBe(false);
  });

  it("HM04 — sichtwechsel verlaesst den Modus und merkt die Sicht", () => {
    const z = api.naechsterZustand({ an: true, sicht: "faelle" },
                                   "sichtwechsel", "dashboard");
    expect(z).toEqual({ an: false, sicht: "dashboard" });
  });

  it("HM05 — nur Shift+F1 ist die Hilfetaste", () => {
    expect(api.istHilfeTaste({ key: "F1", shiftKey: true })).toBe(true);
    expect(api.istHilfeTaste({ key: "F1", shiftKey: false })).toBe(false);
    expect(api.istHilfeTaste({ key: "F1", shiftKey: true, ctrlKey: true })).toBe(false);
    expect(api.istHilfeTaste({ key: "h", shiftKey: true })).toBe(false);
    expect(api.istHilfeTaste(null)).toBe(false);
    expect(api.istAbbruchtaste({ key: "Escape" })).toBe(true);
    expect(api.istAbbruchtaste({ key: "a" })).toBe(false);
  });

  it("HM06 — koerperKlassen tastet fremde Klassen nicht an", () => {
    const an = api.koerperKlassen(["fremd", "noch-eine"], { an: true });
    expect(an).toContain("fremd");
    expect(an).toContain("noch-eine");
    expect(an).toContain("aiw-hilfe-modus");
    const aus = api.koerperKlassen(an, { an: false });
    expect(aus).toEqual(["fremd", "noch-eine"]);
    // idempotent: zweimal einschalten setzt die Klasse nicht doppelt
    const zweimal = api.koerperKlassen(an, { an: true });
    expect(zweimal.filter((k) => k === "aiw-hilfe-modus").length).toBe(1);
  });
});

describe("Hilfemodus — Oberflaeche", () => {
  it("HM07 — Knopfklick schaltet und zeigt den Zustand", () => {
    const { doc, api } = _ctx();
    const knopf = doc.getElementById("aiw-hilfe-btn");
    expect(doc.body.classList.contains("aiw-hilfe-modus")).toBe(false);

    knopf.click();
    expect(api.istAn()).toBe(true);
    expect(doc.body.classList.contains("aiw-hilfe-modus")).toBe(true);
    expect(knopf.getAttribute("aria-pressed")).toBe("true");
    expect(knopf.classList.contains("aiw-hilfe-an")).toBe(true);
    // die fremde Klasse des <body> ist noch da
    expect(doc.body.classList.contains("etwas-fremdes")).toBe(true);

    knopf.click();
    expect(api.istAn()).toBe(false);
    expect(doc.body.classList.contains("aiw-hilfe-modus")).toBe(false);
    expect(knopf.getAttribute("aria-pressed")).toBe("false");
  });

  it("HM08 — Shift+F1 schaltet um, F1 allein nicht", () => {
    const { win, api } = _ctx();
    const ev = _key(win, "F1", { shiftKey: true });
    expect(api.istAn()).toBe(true);
    expect(ev.defaultPrevented).toBe(true);

    const ev2 = _key(win, "F1", { shiftKey: false });
    expect(api.istAn()).toBe(true);          // unveraendert
    expect(ev2.defaultPrevented).toBe(false); // der Browser behaelt F1

    _key(win, "F1", { shiftKey: true });
    expect(api.istAn()).toBe(false);
  });

  it("HM09 — Escape verlaesst den Modus", () => {
    const { win, api } = _ctx();
    api.einschalten();
    expect(api.istAn()).toBe(true);
    _key(win, "Escape");
    expect(api.istAn()).toBe(false);
    // im ausgeschalteten Zustand tut Escape nichts Boeses
    _key(win, "Escape");
    expect(api.istAn()).toBe(false);
  });

  it("HM10 — im Hilfemodus loest kein Klick eine Funktion aus", () => {
    const { doc, api } = _ctx();
    const geklickt = vi.fn();
    doc.getElementById("gefaehrlich").addEventListener("click", geklickt);

    // ausgeschaltet: der Klick kommt an
    doc.getElementById("gefaehrlich").click();
    expect(geklickt).toHaveBeenCalledTimes(1);

    // eingeschaltet: der Klick wird abgefangen
    api.einschalten();
    doc.getElementById("gefaehrlich").click();
    expect(geklickt).toHaveBeenCalledTimes(1);

    // auch ein Klick auf ein Kind-Element loest nichts aus
    doc.getElementById("innen").click();
    expect(geklickt).toHaveBeenCalledTimes(1);

    // wieder aus: der Klick kommt wieder an
    api.ausschalten();
    doc.getElementById("gefaehrlich").click();
    expect(geklickt).toHaveBeenCalledTimes(2);
  });

  it("HM11 — der Hilfe-Knopf bleibt im Modus bedienbar", () => {
    const { doc, api } = _ctx();
    api.einschalten();
    doc.getElementById("aiw-hilfe-btn").click();
    expect(api.istAn()).toBe(false);
  });

  it("HM12 — hilfeSchluessel sucht am Vorfahren", () => {
    const { doc, api } = _ctx();
    expect(api.hilfeSchluessel(doc.getElementById("innen")))
      .toBe("faelle.freigabe");
    expect(api.hilfeSchluessel(doc.getElementById("ohnehilfe"))).toBe(null);
    expect(api.hilfeSchluessel(null)).toBe(null);
    expect(api.istHilfeBedienelement(doc.getElementById("aiw-hilfe-btn")))
      .toBe(true);
    expect(api.istHilfeBedienelement(doc.getElementById("ohnehilfe")))
      .toBe(false);
  });

  it("HM13 — beimKlick meldet den Schluessel (Haken fuer H4)", () => {
    const beimKlick = vi.fn();
    const { doc, api } = _ctx({ beimKlick });
    api.einschalten();
    doc.getElementById("innen").click();
    expect(beimKlick).toHaveBeenCalledTimes(1);
    expect(beimKlick.mock.calls[0][0]).toBe("faelle.freigabe");

    // Element OHNE Hilfe: gemeldet wird null — sichtbar statt still
    doc.getElementById("ohnehilfe").click();
    expect(beimKlick).toHaveBeenCalledTimes(2);
    expect(beimKlick.mock.calls[1][0]).toBe(null);
  });

  it("HM14 — Sichtwechsel raeumt auf", () => {
    const beimVerlassen = vi.fn();
    const { doc, api } = _ctx({ beimVerlassen });
    api.einschalten();
    expect(doc.body.classList.contains("aiw-hilfe-modus")).toBe(true);

    api.sichtGewechselt("dashboard");
    expect(api.istAn()).toBe(false);
    expect(api.aktiveSicht()).toBe("dashboard");
    expect(doc.body.classList.contains("aiw-hilfe-modus")).toBe(false);
    expect(beimVerlassen).toHaveBeenCalledTimes(1);
  });
});

/**
 * ---------------------------------------------------------------------------
 * Build 591 (H4) — Kontext-Popup und Verweismechanik.
 *
 * HP01 — popupLage: erste Wahl ist unterhalb des Elements.
 * HP02 — popupLage: kein Platz unten, mehr Platz oben -> nach oben.
 * HP03 — popupLage: an allen vier Raendern bleibt das Popup im Sichtfeld.
 * HP04 — popupLage: der Bildlauf wird beruecksichtigt (Dokumentkoordinaten).
 * HP05 — vollhilfeUrl: '<sicht>#<anker>' -> '/help#<sicht>-<anker>';
 *        unbrauchbare Eingaben -> null (kein halbfertiger Verweis).
 * HP06 — popupInhalt: Treffer / kein Treffer (ehrlicher Platzhalter MIT
 *        Schluessel).
 * HP07 — Klick auf ein markiertes Element oeffnet das Popup mit Titel und
 *        Text aus dem Bestand.
 * HP08 — der Verweis wird als Link ins BENANNTE Fenster 'aiw_hilfe' gesetzt.
 * HP09 — unbekannter Schluessel -> Fallback-Popup, sichtbar markiert.
 * HP10 — Kontexttexte werden je Sicht nur EINMAL geholt (Zwischenspeicher).
 * HP11 — Verlassen des Modus schliesst das Popup; Sichtwechsel ebenso.
 * HP12 — Klick auf ein Element OHNE Hilfe schliesst ein offenes Popup.
 * HP13 — Texte landen ueber textContent im DOM (kein HTML aus dem Bestand).
 * ---------------------------------------------------------------------------
 */

const BESTAND = {
  faelle: {
    "faelle.ampel": {
      titel: "Dringlichkeits-Ampel",
      text: "Zeigt die Dringlichkeitsstufe des Falls.",
      verweis: "faelle#ampel",
    },
    "faelle.export": {
      titel: "Export",
      text: "Erzeugt die Aktenfassung.",
      verweis: null,
    },
  },
  dashboard: {},
};

function _ctxPopup(zaehler) {
  const dom = new JSDOM(HTML, { runScripts: "dangerously", url: "http://localhost" });
  dom.window.eval(_src);
  const api = dom.window.AIWCockpitHilfe;
  api.init({
    holeKontext: (sicht) => {
      if (zaehler) { zaehler[sicht] = (zaehler[sicht] || 0) + 1; }
      return Promise.resolve(BESTAND[sicht] || {});
    },
  });
  api.sichtGewechselt("faelle");
  return { win: dom.window, doc: dom.window.document, api };
}

const _warten = () => new Promise((r) => setTimeout(r, 0));

describe("Kontext-Popup — reine Funktionen", () => {
  let api;
  beforeEach(() => { api = _ctxPopup().api; });

  const SICHTFELD = { breite: 1000, hoehe: 800, scrollX: 0, scrollY: 0 };
  const POPUP = { breite: 320, hoehe: 120 };

  it("HP01 — erste Wahl ist unterhalb", () => {
    const l = api.popupLage({ links: 100, oben: 200, breite: 80, hoehe: 24 },
                            POPUP, SICHTFELD, 10);
    expect(l.seite).toBe("unten");
    expect(l.oben).toBe(234);
    expect(l.links).toBe(100);
  });

  it("HP02 — kein Platz unten, mehr Platz oben -> nach oben", () => {
    const l = api.popupLage({ links: 100, oben: 700, breite: 80, hoehe: 24 },
                            POPUP, SICHTFELD, 10);
    expect(l.seite).toBe("oben");
    expect(l.oben).toBe(570);
  });

  it("HP03 — an allen vier Raendern im Sichtfeld", () => {
    // rechter Rand: das Popup wird hineingeschoben
    const rechts = api.popupLage({ links: 980, oben: 100, breite: 20, hoehe: 20 },
                                 POPUP, SICHTFELD, 10);
    expect(rechts.links).toBe(1000 - 320 - 10);

    // linker Rand: mindestens der Abstand
    const links = api.popupLage({ links: -50, oben: 100, breite: 20, hoehe: 20 },
                                POPUP, SICHTFELD, 10);
    expect(links.links).toBe(10);

    // oberer Rand: auch bei 'oben' nicht aus dem Dokument
    const oben = api.popupLage({ links: 10, oben: 5, breite: 20, hoehe: 20 },
                               { breite: 320, hoehe: 400 }, SICHTFELD, 10);
    expect(oben.oben).toBeGreaterThanOrEqual(10);

    // unterer Rand bei winzigem Sichtfeld: bleibt berechenbar
    const eng = api.popupLage({ links: 10, oben: 10, breite: 20, hoehe: 20 },
                              POPUP, { breite: 200, hoehe: 100 }, 10);
    expect(eng.links).toBeGreaterThanOrEqual(-320);
    expect(Number.isFinite(eng.oben)).toBe(true);
  });

  it("HP04 — der Bildlauf zaehlt mit", () => {
    const gescrollt = { breite: 1000, hoehe: 800, scrollX: 0, scrollY: 500 };
    // Element steht im Dokument bei 600, also im Bild bei 100 -> Platz unten.
    const l = api.popupLage({ links: 100, oben: 600, breite: 80, hoehe: 24 },
                            POPUP, gescrollt, 10);
    expect(l.seite).toBe("unten");
    expect(l.oben).toBe(634);
  });

  it("HP05 — vollhilfeUrl", () => {
    expect(api.vollhilfeUrl("faelle#ampel")).toBe("/help#faelle-ampel");
    expect(api.vollhilfeUrl(null)).toBe(null);
    expect(api.vollhilfeUrl("faelle")).toBe(null);
    expect(api.vollhilfeUrl("#ampel")).toBe(null);
    expect(api.vollhilfeUrl("faelle#")).toBe(null);
  });

  it("HP06 — popupInhalt mit und ohne Treffer", () => {
    const treffer = api.popupInhalt("faelle.ampel", BESTAND.faelle);
    expect(treffer.titel).toBe("Dringlichkeits-Ampel");
    expect(treffer.offen).toBe(false);

    const fehlt = api.popupInhalt("faelle.gibtsnicht", BESTAND.faelle);
    expect(fehlt.offen).toBe(true);
    expect(fehlt.text).toBe(api.TEXT_OFFEN);
    // der Schluessel steht im Titel - damit weiss man im Betrieb sofort,
    // WELCHER Text fehlt
    expect(fehlt.titel).toBe("faelle.gibtsnicht");
  });
});

describe("Kontext-Popup — Oberflaeche", () => {
  it("HP07 — Klick oeffnet das Popup mit echtem Inhalt", async () => {
    const { doc, api } = _ctxPopup();
    doc.getElementById("gefaehrlich").setAttribute("data-hilfe-id", "faelle.ampel");
    api.einschalten();
    doc.getElementById("innen").click();
    await _warten();

    const box = doc.getElementById("aiw-hilfe-popup");
    expect(box).not.toBe(null);
    expect(box.textContent).toContain("Dringlichkeits-Ampel");
    expect(box.textContent).toContain("Zeigt die Dringlichkeitsstufe");
  });

  it("HP08 — Verweis geht ins benannte Hilfefenster", async () => {
    const { doc, api } = _ctxPopup();
    doc.getElementById("gefaehrlich").setAttribute("data-hilfe-id", "faelle.ampel");
    api.einschalten();
    doc.getElementById("gefaehrlich").click();
    await _warten();

    const link = doc.querySelector(".aiw-hilfe-popup-mehr");
    expect(link).not.toBe(null);
    expect(link.getAttribute("href")).toBe("/help#faelle-ampel");
    expect(link.getAttribute("target")).toBe(api.FENSTER_HILFE);
    expect(link.getAttribute("target")).toBe("aiw_hilfe");
  });

  it("HP09 — unbekannter Schluessel -> sichtbarer Platzhalter", async () => {
    const { doc, api } = _ctxPopup();
    doc.getElementById("gefaehrlich").setAttribute("data-hilfe-id", "faelle.neu");
    api.einschalten();
    doc.getElementById("gefaehrlich").click();
    await _warten();

    const box = doc.getElementById("aiw-hilfe-popup");
    expect(box.className).toContain("aiw-hilfe-popup-offen");
    expect(box.textContent).toContain("Hilfe folgt");
    // ohne Text gibt es auch keinen Verweis ins Leere
    expect(doc.querySelector(".aiw-hilfe-popup-mehr")).toBe(null);
  });

  it("HP10 — Kontexttexte werden je Sicht nur einmal geholt", async () => {
    const zaehler = {};
    const { doc, api } = _ctxPopup(zaehler);
    doc.getElementById("gefaehrlich").setAttribute("data-hilfe-id", "faelle.ampel");
    api.einschalten();

    doc.getElementById("gefaehrlich").click();
    await _warten();
    doc.getElementById("gefaehrlich").click();
    await _warten();
    doc.getElementById("gefaehrlich").click();
    await _warten();

    expect(zaehler.faelle).toBe(1);
  });

  it("HP11 — Verlassen und Sichtwechsel schliessen das Popup", async () => {
    const { doc, api } = _ctxPopup();
    doc.getElementById("gefaehrlich").setAttribute("data-hilfe-id", "faelle.ampel");

    api.einschalten();
    doc.getElementById("gefaehrlich").click();
    await _warten();
    expect(doc.getElementById("aiw-hilfe-popup")).not.toBe(null);

    api.ausschalten();
    expect(doc.getElementById("aiw-hilfe-popup")).toBe(null);

    api.einschalten();
    doc.getElementById("gefaehrlich").click();
    await _warten();
    expect(doc.getElementById("aiw-hilfe-popup")).not.toBe(null);

    api.sichtGewechselt("dashboard");
    expect(doc.getElementById("aiw-hilfe-popup")).toBe(null);
  });

  it("HP12 — Klick ins Leere schliesst das Popup", async () => {
    const { doc, api } = _ctxPopup();
    doc.getElementById("gefaehrlich").setAttribute("data-hilfe-id", "faelle.ampel");
    api.einschalten();
    doc.getElementById("gefaehrlich").click();
    await _warten();
    expect(doc.getElementById("aiw-hilfe-popup")).not.toBe(null);

    doc.getElementById("ohnehilfe").click();
    await _warten();
    expect(doc.getElementById("aiw-hilfe-popup")).toBe(null);
  });

  it("HP13 — Texte kommen als Text an, nicht als HTML", async () => {
    const boeser = "<img src=x onerror=alert(1)>";
    const dom = new JSDOM(HTML, { runScripts: "dangerously", url: "http://localhost" });
    dom.window.eval(_src);
    const api = dom.window.AIWCockpitHilfe;
    api.init({
      holeKontext: () => Promise.resolve({
        "faelle.x": { titel: boeser, text: boeser, verweis: null },
      }),
    });
    api.sichtGewechselt("faelle");
    const doc = dom.window.document;
    doc.getElementById("gefaehrlich").setAttribute("data-hilfe-id", "faelle.x");
    api.einschalten();
    doc.getElementById("gefaehrlich").click();
    await _warten();

    const box = doc.getElementById("aiw-hilfe-popup");
    expect(box.querySelector("img")).toBe(null);
    expect(box.textContent).toContain("onerror");
  });
});
