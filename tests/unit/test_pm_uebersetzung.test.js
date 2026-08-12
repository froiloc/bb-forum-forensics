/**
 * test_pm_uebersetzung.test.js
 * Unit-/Regressionstests: Uebersetzungsflagge auch bei privaten Nachrichten
 * Baustelle 3 · Build 703 · 2026-08-12 · Vorgang da84f94f-1f99-4191-82c3-bb5eaf7e8318
 *
 * ---------------------------------------------------------------------------
 * WAS HIER GEMESSEN WIRD
 *
 * Der Vorgang verlangt: "Auch fuer PMs gibt es eine kleine deutsche Flagge,
 * die die Uebersetzung ein- und ausblendet, so denn eine Uebersetzung
 * verfuegbar ist." Bis Build 699 lief das TranslationModule ausschliesslich
 * auf viewtopic-Seiten an — auf einer PN-Dialogseite geschah NICHTS, obwohl
 * die Uebersetzungen im selben Bestand liegen (trdb.translations,
 * source='pms').
 *
 * ZWEI EBENEN, BEIDE NOETIG:
 *   PU01-PU08  die reine Logik (Adresse -> Gespraech, Schluessel, Zeitangabe).
 *              Sie laeuft gegen den ECHTEN Code ueber
 *              ForensicToolbar.config.translationHelpers.
 *   PU09-PU12  der ganze Weg an einer nachgebauten PN-Dialogseite: welche
 *              Adressen ruft die Toolbar auf, erscheint die Flagge, was steht
 *              im Uebersetzungsfeld. Eine bestandene Logikpruefung sagt noch
 *              nicht, dass die Flagge auch angezeigt wird.
 *
 * WARUM DIE QUELLE UEBERALL MITLAUFEN MUSS: Forenbeitrags- und PN-IDs stammen
 * aus eigenen, ueberlappenden ID-Raeumen — dieselbe Zahl kann beides
 * bezeichnen. PU04 und PU12 halten genau das fest.
 * ===========================================================================*/

import { describe, it, expect, beforeAll, vi } from "vitest";
import { JSDOM } from "jsdom";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TOOLBAR_SRC = readFileSync(
  join(__dirname, "../../toolbar/toolbar.js"), "utf-8"
);

// ---------------------------------------------------------------------------
// Ebene 1: reine Hilfslogik (gegen den echten Code, kein Stub)
// ---------------------------------------------------------------------------
let H;
beforeAll(() => {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => ({}) });
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.eval(TOOLBAR_SRC);
  H = dom.window.ForensicToolbar.config.translationHelpers;
});

describe("TranslationModule.gespraechAusUrl (Vorgang da84f94f)", () => {

  it("PU01: viewtopic -> Quelle 'posts' mit topic_id", () => {
    expect(H.gespraechAusUrl("/forum/viewtopic.php?id=69192"))
      .toEqual({ source: "posts", id: 69192 });
  });

  it("PU02: PN-Dialog -> Quelle 'pms' mit Dialog-ID", () => {
    expect(H.gespraechAusUrl("/forum/pmsnew.php?mdl=topic&tid=85844"))
      .toEqual({ source: "pms", id: 85844 });
  });

  it("PU03: die PN-UEBERSICHT ist kein Dialog", () => {
    // 'pmsnew.php' ohne 'mdl=topic' fuehrt Gespraechszeilen, keine
    // Nachrichten-Container. Wuerde das Modul dort anlaufen, fragte es eine
    // Dialog-ID ab, die es nicht gibt.
    expect(H.gespraechAusUrl("/forum/pmsnew.php")).toBe(null);
    expect(H.gespraechAusUrl("/forum/pmsnew.php?mdl=inbox")).toBe(null);
  });

  it("PU04: andere Seiten -> null (Modul bleibt untaetig)", () => {
    expect(H.gespraechAusUrl("/forum/viewforum.php?id=20")).toBe(null);
    expect(H.gespraechAusUrl("")).toBe(null);
    expect(H.gespraechAusUrl(null)).toBe(null);
  });

  it("PU05: pmTopicIdFromUrl liest die tid, auch mit weiteren Parametern", () => {
    expect(H.pmTopicIdFromUrl("/forum/pmsnew.php?mdl=topic&tid=85844&p=2"))
      .toBe(85844);
    expect(H.pmTopicIdFromUrl("/forum/pmsnew.php?tid=85844")).toBe(null);
  });

  it("PU06: der Zwischenspeicher-Schluessel trennt die Quellen", () => {
    // Der kritische Fall: dieselbe Zahl, zwei Bedeutungen.
    expect(H.cacheKey("posts", 44573)).not.toBe(H.cacheKey("pms", 44573));
  });

  it("PU07: Zeitangabe bevorzugt created_at", () => {
    expect(H.zeitangabe({ created_at: "2026-07-05", updated_at: "2026-07-09" }))
      .toBe(" · 2026-07-05");
  });

  it("PU08: ohne created_at wird updated_at als 'Stand' ausgewiesen", () => {
    // Genau die Lage bei PN (Datenprobe: created_at leer). Ohne diesen
    // Rueckfall traege die Pflichtkopfzeile dort kein Datum; ihn als
    // Erstellungsdatum auszugeben waere dagegen eine falsche Angabe.
    expect(H.zeitangabe({ created_at: null, updated_at: "2026-07-14 02:47:37" }))
      .toBe(" · Stand 2026-07-14 02:47:37");
    expect(H.zeitangabe({})).toBe("");
    expect(H.zeitangabe(null)).toBe("");
  });
});

// ---------------------------------------------------------------------------
// Ebene 2: der ganze Weg an einer nachgebauten PN-Dialogseite
// ---------------------------------------------------------------------------

/**
 * Rumpf einer PN-Dialogseite.
 *
 * DIE FUSSLEISTE IST WOERTLICH DER AUSZUG, den Alex am 12.08.2026 geliefert
 * hat — einschliesslich der &amp;-Kodierung, der Klassen 'postreport'/
 * 'postquote' und des inneren <span> je Eintrag. Ein selbst ausgedachter
 * Nachbau haette hier nichts bewiesen: gemessen werden soll, dass die Flagge
 * in DIESEM Geruest landet, und zwar als ERSTER Eintrag.
 */
function pnFussleiste(tid, qid) {
  return `
    <div class="postfoot clearb">
      <div class="postfootleft"><p></p></div>
      <div class="postfootright">
        <ul>
          <li class="postreport"><span><a href="pmsnew.php?mdl=blocking&amp;uid=3834489&amp;csrf_token=4b54f63f">Block</a></span></li>
          <li class="postquote"><span><a href="pmsnew.php?mdl=post&amp;tid=${tid}&amp;qid=${qid}">Antworten</a></span></li>
        </ul>
      </div>
    </div>`;
}

const PN_HTML = `
  <div class="blockpost" id="p44573">
    <div class="postbody"><div class="postmsg">Original der Nachricht</div></div>
    ${pnFussleiste(86328, 350328)}
  </div>
  <div class="blockpost" id="p44580">
    <div class="postbody"><div class="postmsg">Nachricht ohne Uebersetzung</div></div>
    ${pnFussleiste(86328, 350329)}
  </div>`;

/**
 * Fenster mit geladener toolbar.js auf einer PN-Dialogseite.
 * Der fetch-Doppelgaenger antwortet je nach Adresse; alle Aufrufe werden
 * mitgeschrieben, denn die uebergebene Adresse IST der Nachweis, dass die
 * Quelle beim Server ankommt.
 */
async function fensterAufPnDialog(opts = {}) {
  const uebersetzt = opts.uebersetzt || [44573];
  const seiteninhalt = opts.html || PN_HTML;
  const dom = new JSDOM(
    `<!DOCTYPE html><html><head></head><body>
       <div id="forensic-toolbar"></div>
       <div id="forensic-viewport"></div>
     </body></html>`,
    { url: "http://127.0.0.2:8080/forum/pmsnew.php?mdl=topic&tid=85844",
      runScripts: "dangerously", resources: "usable" }
  );
  const { window } = dom;
  window.Element.prototype.scrollIntoView = vi.fn();

  const aufrufe = [];
  window.fetch = vi.fn(function (url) {
    aufrufe.push(String(url));
    const u = String(url);
    let daten;
    if (u.indexOf("/_forensic/translations") !== -1) {
      daten = { topic_id: 85844, source: "pms", post_ids: uebersetzt,
                count: uebersetzt.length, status: "ok",
                resolved_via: "pm_aliases" };
    } else if (u.indexOf("/_forensic/translate") !== -1) {
      daten = { post_id: 44573, found: true, source: "pms",
                translated_text: "Hallo mein Freund, moegen all deine "
                                 + "Wuensche wahr werden.",
                model_used: "llama3:8b-instruct-q4_K_M",
                created_at: null, updated_at: "2026-07-14 02:47:37" };
    } else if (u.indexOf("/_forensic/page") !== -1) {
      daten = {
        in_scope: true, fetch_failed: false, html: seiteninhalt,
        head: { title: "PN", base_href: "/forum/", stylesheets: [],
                inline_styles: [] },
        scrape_context: "user", http_status: 200,
        url_canonical: "/forum/pmsnew.php?mdl=topic&tid=85844",
        fragment: null, fragment_source: null, trace_elements: [],
      };
    } else {
      daten = {};   // Annotationen, Sitzungsdaten usw. — hier ohne Belang
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(daten) });
  });
  window.requestAnimationFrame = (cb) => setTimeout(cb, 0);

  window.eval(TOOLBAR_SRC);
  if (window.document.readyState === "loading") {
    await new Promise((r) =>
      window.document.addEventListener("DOMContentLoaded", r, { once: true }));
  } else {
    window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
  }
  await new Promise((r) => setTimeout(r, 120));

  return { window, aufrufe };
}

describe("Uebersetzungsflagge auf der PN-Dialogseite (Vorgang da84f94f)", () => {

  it("PU09: die Abfrage nennt die Dialog-ID UND die Quelle 'pms'", async () => {
    const { aufrufe } = await fensterAufPnDialog();
    const abfrage = aufrufe.find((u) => u.indexOf("/_forensic/translations") !== -1);
    expect(abfrage).toBeDefined();
    expect(abfrage).toContain("topic_id=85844");
    expect(abfrage).toContain("source=pms");
  });

  it("PU10: die Flagge erscheint NUR an der uebersetzten Nachricht", async () => {
    const { window } = await fensterAufPnDialog({ uebersetzt: [44573] });
    const mit = window.document.querySelector("#p44573 .aiw-translate-flag");
    const ohne = window.document.querySelector("#p44580 .aiw-translate-flag");
    expect(mit).not.toBeNull();
    expect(ohne).toBeNull();
  });

  it("PU11: der Klick oeffnet das Feld mit Text, Modell und Stand", async () => {
    const { window, aufrufe } = await fensterAufPnDialog();
    const flagge = window.document.querySelector("#p44573 .aiw-translate-flag");
    flagge.dispatchEvent(new window.Event("click"));
    await new Promise((r) => setTimeout(r, 60));

    // Die Einzelabfrage muss die Quelle mitfuehren — sonst antwortete der
    // Server mit der Uebersetzung des GLEICHNAMIGEN Forenbeitrags.
    const einzel = aufrufe.find((u) => u.indexOf("/_forensic/translate?") !== -1);
    expect(einzel).toContain("post_id=44573");
    expect(einzel).toContain("source=pms");

    const panel = window.document.querySelector(
      '#p44573 .aiw-translation-panel[data-post-id="44573"]');
    expect(panel).not.toBeNull();
    expect(panel.querySelector(".aiw-translation-body").textContent)
      .toContain("moegen all deine Wuensche wahr werden");
    const kopf = panel.querySelector(".aiw-translation-head").textContent;
    expect(kopf).toContain("Maschinell übersetzt");
    expect(kopf).toContain("llama3:8b-instruct-q4_K_M");
    expect(kopf).toContain("Stand 2026-07-14 02:47:37");
    expect(kopf).toContain("nicht gerichtsverwertbar");
  });

  it("PU12: das Feld traegt die Quelle 'pms' (Anker der Erfassung)", async () => {
    // Build 333 liest data-source am Panel und legt es in den Markierungs-
    // Anker. Stuende dort 'posts', wiese eine Markierung in einer PRIVATEN
    // Nachricht auf den gleichnamigen FORENBEITRAG — eine falsche
    // Zuschreibung, nicht bloss ein Anzeigefehler.
    const { window } = await fensterAufPnDialog();
    const flagge = window.document.querySelector("#p44573 .aiw-translate-flag");
    flagge.dispatchEvent(new window.Event("click"));
    await new Promise((r) => setTimeout(r, 60));

    const panel = window.document.querySelector(".aiw-translation-panel");
    expect(panel.getAttribute("data-source")).toBe("pms");
  });

  it("PU17: die Flagge steht als ERSTER Eintrag in '.postfootright ul'", async () => {
    // Weisung Alex, 12.08.2026 — samt Beleg (Auszug der Fussleiste). Die
    // Reihenfolge ist keine Geschmacksfrage: die Flagge soll vor 'Block' und
    // 'Antworten' stehen, also am Anfang der Leiste.
    const { window } = await fensterAufPnDialog();
    const liste = window.document.querySelector("#p44573 .postfootright ul");
    expect(liste).not.toBeNull();

    const erstes = liste.firstElementChild;
    expect(erstes.querySelector(".aiw-translate-flag")).not.toBeNull();
    // Die bestehenden Eintraege bleiben unangetastet und stehen dahinter.
    const texte = Array.from(liste.children).map((li) => li.textContent.trim());
    expect(texte.slice(1)).toEqual(["Block", "Antworten"]);
  });

  it("PU18: der Eintrag ist ein <li> — ein <span> im <ul> waere ungueltig", async () => {
    // In ein <ul> gehoert ein <li>. Nur so greift auch die Formatierung, die
    // das Forum den uebrigen Eintraegen dieser Leiste gibt.
    const { window } = await fensterAufPnDialog();
    const eintrag = window.document.querySelector(
      "#p44573 .postfootright ul > .aiw-translate-item");
    expect(eintrag.tagName).toBe("LI");
    expect(eintrag.classList.contains("aux-part")).toBe(true);
    // Innerer <span> wie bei 'Block'/'Antworten'.
    expect(eintrag.querySelector("span > .aiw-translate-flag")).not.toBeNull();
  });

  it("PU13: ein zweiter Klick blendet die Uebersetzung wieder aus", async () => {
    // Der Vorgang verlangt ausdruecklich ein EIN- UND AUSBLENDEN.
    const { window } = await fensterAufPnDialog();
    const flagge = window.document.querySelector("#p44573 .aiw-translate-flag");
    flagge.dispatchEvent(new window.Event("click"));
    await new Promise((r) => setTimeout(r, 60));
    expect(window.document.querySelector(".aiw-translation-panel")).not.toBeNull();

    flagge.dispatchEvent(new window.Event("click"));
    await new Promise((r) => setTimeout(r, 20));
    expect(window.document.querySelector(".aiw-translation-panel")).toBeNull();
  });
});

describe("Notanker fuer unbekannte Nachrichten-Layouts (Build 703)", () => {

  // Nachricht OHNE .postfoot/.post-actions/.rate-buttons — der Aufbau der
  // PN-Dialogseite ist nicht belegt (es liegt kein anonymisierter Auszug vor).
  const PN_HTML_OHNE_ANKER = `
    <div class="blockpost" id="p44573">
      <div class="postbody"><div class="postmsg">Original der Nachricht</div></div>
    </div>`;

  it("PU14: kein bekannter Anker im Aufbau — resolveFlagAnchor sagt das auch", async () => {
    const { window } = await fensterAufPnDialog({ html: PN_HTML_OHNE_ANKER });
    const helfer = window.ForensicToolbar.config.translationHelpers;
    const behaelter = window.document.getElementById("p44573");
    expect(helfer.resolveFlagAnchor(behaelter)).toBe(null);
  });

  it("PU15: trotzdem erscheint die Flagge — im Notanker", async () => {
    // Bis Build 699 unterblieb die Flagge in dieser Lage STILLSCHWEIGEND
    // (nur eine Debug-Zeile). Eine vorhandene Uebersetzung waere damit
    // unsichtbar geblieben — genau die stille Auslassung, die GR1 verbietet.
    const { window } = await fensterAufPnDialog({ html: PN_HTML_OHNE_ANKER });
    const flagge = window.document.querySelector("#p44573 .aiw-translate-flag");
    expect(flagge).not.toBeNull();
    expect(flagge.closest(".aiw-flag-fallback")).not.toBeNull();
    // Der Notanker ist ein AIW-Element und verschwindet in der
    // Originalansicht wie jedes andere (.aux-part).
    expect(flagge.closest(".aiw-flag-fallback").classList.contains("aux-part"))
      .toBe(true);
  });

  it("PU16: der Notanker traegt die Flagge nur EINMAL", async () => {
    // _apply laeuft je Seite mehrfach (z. B. nach dem Nachladen von
    // Annotationen). Ein zweiter Durchgang darf weder eine zweite Leiste noch
    // eine zweite Flagge erzeugen.
    const { window } = await fensterAufPnDialog({ html: PN_HTML_OHNE_ANKER });
    expect(window.document.querySelectorAll("#p44573 .aiw-flag-fallback").length)
      .toBe(1);
    expect(window.document.querySelectorAll("#p44573 .aiw-translate-flag").length)
      .toBe(1);
  });
});
