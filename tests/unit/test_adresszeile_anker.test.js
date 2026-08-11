/**
 * test_adresszeile_anker.test.js
 * Unit-/Regressionstests: Der Anker der Adresszeile erreicht den Server
 * Baustelle 3 · Build 693 · 2026-08-11 · Vorgang b9b830f4-70a9-4eee-bc1c-24f22f27d9ae
 *
 * ---------------------------------------------------------------------------
 * WAS HIER GEMESSEN WIRD UND WARUM AN DIESER STELLE
 *
 * Die Behebung besteht aus zwei Zeilen. Ihre Wirkung ist aber nicht an den
 * Zeilen ablesbar, sondern erst an dem, was der Server zu sehen bekommt:
 * toolbar.js baut die Adresse zusammen, haengt sie per encodeURIComponent an
 * '/_forensic/page?url=' und schickt sie per fetch los. GENAU DIESE
 * ZEICHENKETTE ist der Nachweis - sie ist das Einzige, was den Anker vom
 * Browser zum Server traegt. Die Tests lesen deshalb die fetch-Aufrufe aus
 * und pruefen die uebergebene Adresse, nicht den Zustand des Moduls.
 *
 * Aufbau nach dem Vorbild von test_form_intercept.test.js (Build 042):
 * jsdom mit gesetzter Adresse, toolbar.js per eval, DOMContentLoaded von Hand.
 * ABWEICHUNG: Dort wird der Initialaufruf verworfen (mockClear). Hier ist er
 * der Gegenstand - AN01 bis AN04 sehen sich genau ihn an.
 *
 * FAELLE
 *   AN01  Startaufruf MIT Anker  -> Anker geht an den Server
 *   AN02  Startaufruf OHNE Anker -> unveraendert (Regression)
 *   AN03  Startaufruf mit Alias-Abfrage '?pid=' und Anker -> beides erhalten
 *   AN04  Prozentkodierter Anker bleibt unveraendert erhalten (mehrsprachig)
 *   AN05  popstate MIT History-Zustand -> Zustand hat Vorrang (Regression)
 *   AN06  popstate OHNE History-Zustand -> Anker aus der Adresszeile
 *   AN07  Klick-Weg unveraendert (Regression zu _interceptLinks)
 *   AN08  currentUrl bleibt ohne Anker, wenn der Server url_canonical liefert
 *   AN09  currentUrl bleibt ohne Anker AUCH im Rueckfall ohne url_canonical
 *   AN10  'page:loaded' traegt fragment in der Nutzlast, url bleibt ankerfrei
 *   AN11  ohne Anker steht fragment in der Nutzlast auf null (kein Rest)
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
 * Minimale, gueltige Envelope-Antwort.
 * @param o.urlCanonical  Wert des Feldes url_canonical (null = Feld fehlt)
 * @param o.fragment      Wert des Feldes fragment
 */
function envelopeResponse(o = {}) {
  const env = {
    in_scope:       true,
    fetch_failed:   false,
    html:           "<p>ok</p>",
    head: { title: "T", base_href: "/forum/", stylesheets: [], inline_styles: [] },
    scrape_context: "user",
    url_canonical:  o.urlCanonical === undefined ? "/forum/viewtopic.php?id=42" : o.urlCanonical,
    fragment:       o.fragment === undefined ? null : o.fragment,
    trace_elements: [],
  };
  return { ok: true, json: () => Promise.resolve(env) };
}

/**
 * Baut ein Fenster mit geladener toolbar.js an der angegebenen Adresse.
 * Der Initialaufruf wird NICHT verworfen - er ist hier der Gegenstand.
 */
async function fensterMitAdresse(adresse, envOpts = {}) {
  const dom = new JSDOM(
    `<!DOCTYPE html><html><head></head><body>
       <div id="forensic-toolbar"></div>
       <div id="forensic-viewport"></div>
     </body></html>`,
    { url: adresse, runScripts: "dangerously", resources: "usable" }
  );
  const { window } = dom;

  const fetchMock = vi.fn().mockResolvedValue(envelopeResponse(envOpts));
  window.fetch = fetchMock;
  window.requestAnimationFrame = (cb) => setTimeout(cb, 0);

  window.eval(TOOLBAR_SRC);

  // BELEG, WARUM HIER NICHT BLIND DISPATCHT WIRD (gemessen 2026-08-11):
  // Mit resources:"usable" steht der Zustand nach dem eval auf "loading";
  // jsdom sendet DOMContentLoaded also noch selbst. Ein zusaetzlicher Aufruf
  // von Hand - wie in test_form_intercept, das den Startaufruf ohnehin
  // verwirft - laesst die Startphase ZWEIMAL laufen und erzeugt zwei
  // Seitenanfragen. Hier wird der Startaufruf gemessen; die Zahl der Aufrufe
  // ist deshalb selbst eine Aussage und darf nicht vom Pruefstand stammen.
  if (window.document.readyState === "loading") {
    await new Promise((r) =>
      window.document.addEventListener("DOMContentLoaded", r, { once: true }));
  } else {
    window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
  }
  await new Promise((r) => setTimeout(r, 60));

  return { window, fetchMock };
}

/** Alle an /_forensic/page gerichteten Aufrufe. */
function seitenAufrufe(fetchMock) {
  return fetchMock.mock.calls
    .map((c) => c[0])
    .filter((u) => typeof u === "string" && u.includes("/_forensic/page"));
}

/** Die im Aufruf uebergebene Seitenadresse (dekodiert). */
function uebergebeneAdresse(aufruf) {
  const m = /[?&]url=([^&]*)/.exec(aufruf);
  return m ? decodeURIComponent(m[1]) : null;
}

// ---------------------------------------------------------------------------
// Startaufruf (Two-Phase-Load, Phase 3)
// ---------------------------------------------------------------------------
describe("toolbar.js — Anker beim Startaufruf (Vorgang b9b830f4)", () => {

  it("AN01: Anker der Adresszeile geht an den Server", async () => {
    const { fetchMock } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/viewtopic.php?id=42#p335445"
    );
    const aufrufe = seitenAufrufe(fetchMock);
    expect(aufrufe.length).toBe(1);
    expect(uebergebeneAdresse(aufrufe[0]))
      .toBe("/forum/viewtopic.php?id=42#p335445");
    // Doppelt gesichert: das '#' MUSS kodiert in der Abfrage stehen, sonst
    // schneidet es der Browser als eigenes Fragment der API-Adresse ab und
    // der Server sieht es nie.
    expect(aufrufe[0]).toContain("%23p335445");
  });

  it("AN02: ohne Anker bleibt der Startaufruf unveraendert (Regression)", async () => {
    const { fetchMock } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/viewtopic.php?id=42"
    );
    const aufrufe = seitenAufrufe(fetchMock);
    expect(aufrufe.length).toBe(1);
    expect(uebergebeneAdresse(aufrufe[0])).toBe("/forum/viewtopic.php?id=42");
    expect(aufrufe[0]).not.toContain("%23");
  });

  it("AN03: Abfrageteil und Anker stehen nebeneinander", async () => {
    // '?pid=' ist der Weg, auf dem der Server den Anker selbst ableitet
    // (blob_handler.py: '?pid=12345' -> 'p12345'). Beides muss ankommen -
    // welche der beiden Angaben gilt, entscheidet der Server, nicht wir.
    const { fetchMock } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/viewtopic.php?pid=12345#p12345"
    );
    expect(uebergebeneAdresse(seitenAufrufe(fetchMock)[0]))
      .toBe("/forum/viewtopic.php?pid=12345#p12345");
  });

  it("AN04: prozentkodierter Anker bleibt Zeichen fuer Zeichen erhalten", async () => {
    // Fallerkenntnis 2: mehrsprachiges Forum. Ein Anker kann Nicht-ASCII
    // tragen und steht in der Adresszeile kodiert. Er darf hier weder
    // dekodiert noch doppelt kodiert werden.
    const { fetchMock } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/viewtopic.php?id=7#Gr%C3%BCsse"
    );
    expect(uebergebeneAdresse(seitenAufrufe(fetchMock)[0]))
      .toBe("/forum/viewtopic.php?id=7#Gr%C3%BCsse");
  });
});

// ---------------------------------------------------------------------------
// popstate
// ---------------------------------------------------------------------------
describe("toolbar.js — Anker im popstate-Zweig (Vorgang b9b830f4)", () => {

  it("AN05: History-Zustand hat Vorrang vor der Adresszeile (Regression)", async () => {
    const { window, fetchMock } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/viewtopic.php?id=42#p1"
    );
    fetchMock.mockClear();

    window.dispatchEvent(new window.PopStateEvent("popstate", {
      state: { forensicUrl: "/forum/viewtopic.php?id=99#p999" },
    }));
    await new Promise((r) => setTimeout(r, 60));

    expect(uebergebeneAdresse(seitenAufrufe(fetchMock)[0]))
      .toBe("/forum/viewtopic.php?id=99#p999");
  });

  it("AN06: ohne History-Zustand traegt die Adresszeile den Anker", async () => {
    // Das ist der Eintrag, den nicht wir erzeugt haben - allen voran der
    // ERSTE Eintrag des Fensters, also die vom Ermittler aufgerufene Adresse.
    const { window, fetchMock } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/viewtopic.php?id=42#p335445"
    );
    fetchMock.mockClear();

    window.dispatchEvent(new window.PopStateEvent("popstate", { state: null }));
    await new Promise((r) => setTimeout(r, 60));

    const aufrufe = seitenAufrufe(fetchMock);
    expect(aufrufe.length).toBe(1);
    expect(uebergebeneAdresse(aufrufe[0]))
      .toBe("/forum/viewtopic.php?id=42#p335445");
  });
});

// ---------------------------------------------------------------------------
// Klick-Weg — der Weg, der schon vorher richtig war
// ---------------------------------------------------------------------------
describe("toolbar.js — Klick-Weg unveraendert", () => {

  it("AN07: ein Verweis mit Anker wird unveraendert weitergereicht", async () => {
    const { window, fetchMock } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/index.php"
    );
    fetchMock.mockClear();

    const vp = window.document.getElementById("forensic-viewport");
    vp.innerHTML = '<a id="ziel" href="/forum/viewtopic.php?id=42#p777">Beitrag</a>';
    // _interceptLinks laeuft ueber die Navigation; hier wird es ueber den
    // oeffentlichen Weg ausgeloest, damit der Test nicht an Interna haengt.
    window.ForensicToolbar.navigation.loadPage("/forum/viewtopic.php?id=42#p777", false);
    await new Promise((r) => setTimeout(r, 60));

    expect(uebergebeneAdresse(seitenAufrufe(fetchMock)[0]))
      .toBe("/forum/viewtopic.php?id=42#p777");
  });
});

// ---------------------------------------------------------------------------
// Der Schluessel bleibt ankerfrei
// ---------------------------------------------------------------------------
describe("toolbar.js — currentUrl traegt nie einen Anker", () => {

  it("AN08: mit url_canonical vom Server", async () => {
    const { window } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/viewtopic.php?id=42#p335445",
      { urlCanonical: "/forum/viewtopic.php?id=42", fragment: "p335445" }
    );
    expect(window.ForensicToolbar.state.get("currentUrl"))
      .toBe("/forum/viewtopic.php?id=42");
    // Das Fragment selbst geht NICHT verloren - es steht im Zustand, von wo
    // scroll_memory.js es liest (Build 688, Anker-Quelle 2).
    expect(window.ForensicToolbar.state.get("fragment")).toBe("p335445");
  });

  it("AN09: auch im Rueckfall, wenn der Server keine kanonische Adresse schickt", async () => {
    // DER EIGENTLICHE GRUND FUER _stripFragment(). Ohne das Abtrennen wuerde
    // 'currentUrl' hier den Anker tragen - und Annotationen, Markierungen und
    // die gemerkte Leseposition zerfielen fuer dieselbe Seite in mehrere
    // Datensaetze, je nach angesprungenem Beitrag.
    const { window } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/viewtopic.php?id=42#p335445",
      { urlCanonical: null, fragment: "p335445" }
    );
    expect(window.ForensicToolbar.state.get("currentUrl"))
      .toBe("/forum/viewtopic.php?id=42");
  });
});

// ---------------------------------------------------------------------------
// Nutzlast von 'page:loaded' (Build 693)
// ---------------------------------------------------------------------------
describe("toolbar.js — 'page:loaded' traegt den Anker", () => {

  it("AN10: 'page:loaded' traegt das Fragment in der Nutzlast, 'url' nicht", async () => {
    // Build 693: Der Anker haengt jetzt am Ereignis statt am Zeitpunkt, zu
    // dem ein Abonnent den Zustand liest. Gemessen wird beides zugleich -
    // dass das Fragment ankommt UND dass 'url' der ankerfreie Schluessel
    // bleibt. Beides in EINEM Fall, weil genau ihre Verwechslung der Fehler
    // waere, den dieser Waechter verhindern soll.
    const dom = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/index.php"
    );
    const { window, fetchMock } = dom;

    const nutzlasten = [];
    window.ForensicToolbar.events.on("page:loaded", (d) => nutzlasten.push(d));
    fetchMock.mockClear();
    fetchMock.mockResolvedValue(envelopeResponse({
      urlCanonical: "/forum/viewtopic.php?id=42",
      fragment:     "p335445",
    }));

    window.ForensicToolbar.navigation.loadPage("/forum/viewtopic.php?id=42#p335445", false);
    await new Promise((r) => setTimeout(r, 60));

    expect(nutzlasten.length).toBe(1);
    expect(nutzlasten[0].fragment).toBe("p335445");
    expect(nutzlasten[0].url).toBe("/forum/viewtopic.php?id=42");
  });

  it("AN11: ohne Anker steht 'fragment' in der Nutzlast auf null", async () => {
    // Ein fehlendes Feld und ein Feld mit dem Wert null sind fuer einen
    // Abonnenten dasselbe - ein STEHENGEBLIEBENER Wert der Vorseite waere es
    // nicht. Deshalb wird der Nachfolgeaufruf gemessen, nicht der erste.
    const { window, fetchMock } = await fensterMitAdresse(
      "http://127.0.0.2:8080/forum/viewtopic.php?id=42#p335445",
      { urlCanonical: "/forum/viewtopic.php?id=42", fragment: "p335445" }
    );
    const nutzlasten = [];
    window.ForensicToolbar.events.on("page:loaded", (d) => nutzlasten.push(d));
    fetchMock.mockClear();
    fetchMock.mockResolvedValue(envelopeResponse({
      urlCanonical: "/forum/index.php",
      fragment:     null,
    }));

    window.ForensicToolbar.navigation.loadPage("/forum/index.php", false);
    await new Promise((r) => setTimeout(r, 60));

    expect(nutzlasten.length).toBe(1);
    expect(nutzlasten[0].fragment).toBeNull();
  });
});
