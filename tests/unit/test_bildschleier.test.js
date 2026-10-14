/**
 * =============================================================================
 * tests/unit/test_bildschleier.test.js
 * IT-Forensisches Ermittlungswerkzeug — Bildschleier-Schalter (Build 772)
 * =============================================================================
 * Testsuite fuer toolbar/bildschleier.js (Bauplan Builds 771-773, §9).
 *
 *   BS19 — gesperrt: Klick ohne Wirkung, KEIN Request, Klasse bleibt
 *   BS20 — Einschalten setzt die Klasse VOR dem Request
 *   BS21 — ein gescheitertes AUSschalten laesst die Klasse stehen
 *   BS21a — erfolgreiches Umschalten laedt neu
 *   BS21b — ohne data-Attribute an <html>: gesperrt (sichere Richtung)
 *   BS21c — seiteAnwenden: Ausnahmen gesetzt / geleert, Klasse folgt dem
 *           Server; fehlender Umschlag aendert die Klasse NICHT
 *   BS21d — Darstellung: drei Zustaende, Zeichen U+1F441, Kurzhinweis
 *
 * Build 775 (Befund 13.10.2026):
 *   BS31 — gescheitertes EINschalten (500 mit Zustand 'klar'): Zustand
 *          'lokal' — Klasse steht, Knopf verschleiert + is-local, Hinweis
 *   BS32 — Klick im Zustand 'lokal': KEIN Request, Klasse weg, klar
 *   BS33 — danach versucht der naechste Klick erneut zu speichern
 *   BS34 — Netzwerkfehler beim Einschalten: ebenfalls 'lokal'
 *   BS35 — seiteAnwenden im Zustand 'lokal': klar gemeldet -> Klasse
 *          bleibt; verschleiert gemeldet -> 'lokal' endet
 *   BS36 — seiteAnwenden im klaren Zustand setzt die Ausnahmen (D1)
 *   BS37 — gescheitertes AUSschalten, gespeichert "verschleiert": nicht 'lokal'
 *   BS38 — Blaettern, WAEHREND das Einschalten gespeichert wird: Klasse
 *          bleibt (Befund 4a der unabhaengigen Durchsicht, seit Build 772)
 *   BS39 — gescheitertes AUSschalten, Antwort meldet gespeichert "klar":
 *          'lokal', Klick hebt ohne Request auf (Befund 4b)
 *
 * MUTATIONSGEGENPROBE (Build 772): in umschalten() das Setzen der Klasse
 * hinter den Request verschoben -> BS20 rot.
 * Build 775: siehe build.json (M10-M13).
 * =============================================================================
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("toolbar/bildschleier.js", "utf-8");

/**
 * Ein Fenster mit der Shell-Auszeichnung, wie server/shell_handler.py sie
 * schreibt. fetchAntwort: {ok, status, daten} oder eine Funktion.
 */
function _fenster(htmlAttribute, fetchAntwort) {
  const dom = new JSDOM(
    `<!DOCTYPE html><html ${htmlAttribute}><head></head><body>` +
    `<button id="forensic-image-veil"></button>` +
    `<div id="forensic-viewport"></div></body></html>`,
    { runScripts: "dangerously", url: "http://localhost/forum/index.php" });
  const w = dom.window;
  const aufrufe = [];
  w.fetch = (url, opts) => {
    // Zum Zeitpunkt des Requests: steht die Klasse schon?
    aufrufe.push({
      url, opts,
      klasseBeimRequest: w.document.documentElement.classList.contains("aiw-image-veil"),
    });
    const a = typeof fetchAntwort === "function" ? fetchAntwort(opts) : fetchAntwort;
    if (a instanceof Error) return Promise.reject(a);
    return Promise.resolve({
      ok: a.ok, status: a.status,
      json: () => Promise.resolve(a.daten),
    });
  };
  w.eval(_src);
  let neuGeladen = 0;
  w.BildschleierSchalter._neuLaden = () => { neuGeladen += 1; };
  const knopf = w.document.getElementById("forensic-image-veil");
  w.BildschleierSchalter.binden(knopf);
  return { w, knopf, aufrufe, neuGeladen: () => neuGeladen };
}

const GESPERRT = 'class="aiw-image-veil" data-image-veil-veiled="1" ' +
  'data-image-veil-locked="1" data-image-veil-reason="required_by_role" ' +
  'data-image-veil-tooltip="Für Ihre Rolle ist die Bildverschleierung vorgeschrieben."';
const KLAR = 'data-image-veil-veiled="0" data-image-veil-locked="0" ' +
  'data-image-veil-reason="default" data-image-veil-tooltip="klar"';
const VERSCHLEIERT = 'class="aiw-image-veil" data-image-veil-veiled="1" ' +
  'data-image-veil-locked="0" data-image-veil-reason="chosen" ' +
  'data-image-veil-tooltip="verschleiert"';

const _warte = () => new Promise((r) => setTimeout(r, 0));

describe("Bildschleier-Schalter", () => {

  it("BS19 gesperrt: Klick ohne Wirkung, kein Request", async () => {
    const f = _fenster(GESPERRT, { ok: true, status: 200, daten: {} });
    f.knopf.click();
    await _warte();
    expect(f.aufrufe.length).toBe(0);
    expect(f.neuGeladen()).toBe(0);
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    expect(f.knopf.classList.contains("is-locked")).toBe(true);
    expect(f.knopf.getAttribute("aria-disabled")).toBe("true");
    expect(f.knopf.title).toContain("Rolle");
  });

  it("BS20 Einschalten setzt die Klasse VOR dem Request", async () => {
    const f = _fenster(KLAR, { ok: true, status: 200,
      daten: { veiled: true, locked: false, reason: "chosen", tooltip: "v" } });
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(false);
    await f.w.BildschleierSchalter.umschalten();
    expect(f.aufrufe.length).toBe(1);
    expect(f.aufrufe[0].klasseBeimRequest).toBe(true);
    expect(JSON.parse(f.aufrufe[0].opts.body)).toEqual({ veiled: true });
    expect(f.aufrufe[0].url).toBe("/_forensic/image-veil");
  });

  it("BS21 gescheitertes Ausschalten laesst die Klasse stehen", async () => {
    const f = _fenster(VERSCHLEIERT, { ok: false, status: 500,
      daten: { error: "store_failed", detail: "gesperrt" } });
    const ok = await f.w.BildschleierSchalter.umschalten();
    expect(ok).toBe(false);
    expect(JSON.parse(f.aufrufe[0].opts.body)).toEqual({ veiled: false });
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    expect(f.neuGeladen()).toBe(0);
    expect(f.knopf.classList.contains("is-error")).toBe(true);
    expect(f.knopf.title).toContain("fehlgeschlagen");
  });

  it("BS21 auch ein Netzwerkfehler entschleiert nicht", async () => {
    const f = _fenster(VERSCHLEIERT, new Error("offline"));
    await f.w.BildschleierSchalter.umschalten();
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
  });

  it("BS21a erfolgreiches Umschalten laedt neu", async () => {
    const f = _fenster(VERSCHLEIERT, { ok: true, status: 200,
      daten: { veiled: false, locked: false, reason: "chosen", tooltip: "k" } });
    const ok = await f.w.BildschleierSchalter.umschalten();
    expect(ok).toBe(true);
    expect(f.neuGeladen()).toBe(1);
    // Die Klasse entfernt erst die neu geladene Shell, nicht dieses Modul.
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
  });

  it("BS21a ein 403 uebernimmt den gemeldeten Zustand (gesperrt)", async () => {
    const f = _fenster(KLAR, { ok: false, status: 403,
      daten: { veiled: true, locked: true, reason: "no_capability",
               tooltip: "Recht fehlt", error: "forbidden" } });
    await f.w.BildschleierSchalter.umschalten();
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    expect(f.w.BildschleierSchalter.zustand().locked).toBe(true);
    expect(f.knopf.classList.contains("is-locked")).toBe(true);
  });

  it("BS21b ohne data-Attribute: gesperrt und verschleiert", async () => {
    const f = _fenster("", { ok: true, status: 200, daten: {} });
    const z = f.w.BildschleierSchalter.zustand();
    expect(z.veiled).toBe(true);
    expect(z.locked).toBe(true);
    f.knopf.click();
    await _warte();
    expect(f.aufrufe.length).toBe(0);
  });

  it("BS21c seiteAnwenden setzt und leert die Ausnahmen", () => {
    const f = _fenster(VERSCHLEIERT, { ok: true, status: 200, daten: {} });
    const S = f.w.BildschleierSchalter;
    S.seiteAnwenden({ veiled: true, locked: false, reason: "chosen",
                      tooltip: "v", exempt_css: "x { filter: none }" });
    const stil = f.w.document.getElementById("aiw-image-veil-page");
    expect(stil).not.toBeNull();
    expect(stil.textContent).toBe("x { filter: none }");
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    S.seiteAnwenden({ veiled: false, locked: false, reason: "chosen",
                      tooltip: "k", exempt_css: "" });
    expect(stil.textContent).toBe("");
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(false);
  });

  it("BS21c fehlender Umschlag aendert die Klasse nicht", () => {
    const f = _fenster(VERSCHLEIERT, { ok: true, status: 200, daten: {} });
    f.w.BildschleierSchalter.seiteAnwenden(undefined);
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    f.w.BildschleierSchalter.seiteAnwenden({ veiled: "ja" });
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
  });

  it("BS21d drei Zustaende, Zeichen U+1F441", () => {
    const g = _fenster(GESPERRT, { ok: true, status: 200, daten: {} });
    const v = _fenster(VERSCHLEIERT, { ok: true, status: 200, daten: {} });
    const k = _fenster(KLAR, { ok: true, status: 200, daten: {} });
    expect(g.knopf.textContent).toBe("\u{1F441}");
    expect(g.knopf.className).toContain("is-locked");
    expect(v.knopf.className).toContain("is-veiled");
    expect(v.knopf.className).not.toContain("is-locked");
    expect(k.knopf.className).toContain("is-clear");
    expect(v.knopf.getAttribute("aria-pressed")).toBe("true");
    expect(k.knopf.getAttribute("aria-pressed")).toBe("false");
    expect(k.knopf.title).toBe("klar");
  });

  // ===========================================================================
  // Build 775 — Befund 13.10.2026 (D1, D2)
  // ===========================================================================

  const FEHLER_KLAR = { ok: false, status: 500,
    daten: { veiled: false, locked: false, reason: "default", tooltip: "klar",
             error: "store_failed", detail: "database is locked" } };

  it("BS31 gescheitertes Einschalten -> lokal verschleiert", async () => {
    const f = _fenster(KLAR, FEHLER_KLAR);
    const ok = await f.w.BildschleierSchalter.umschalten();
    expect(ok).toBe(false);
    expect(f.neuGeladen()).toBe(0);
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    const z = f.w.BildschleierSchalter.zustand();
    expect(z.veiled).toBe(false);          // gespeichert: klar
    expect(z.lokal).toBe(true);
    expect(f.knopf.classList.contains("is-veiled")).toBe(true);
    expect(f.knopf.classList.contains("is-local")).toBe(true);
    expect(f.knopf.classList.contains("is-clear")).toBe(false);
    expect(f.knopf.getAttribute("aria-pressed")).toBe("true");
    expect(f.knopf.title).toContain("Nur lokal verschleiert");
    expect(f.knopf.title).toContain("database is locked");
  });

  it("BS32 Klick im Zustand lokal: kein Request, Klasse weg", async () => {
    const f = _fenster(KLAR, FEHLER_KLAR);
    await f.w.BildschleierSchalter.umschalten();
    expect(f.aufrufe.length).toBe(1);
    await f.w.BildschleierSchalter.umschalten();
    expect(f.aufrufe.length).toBe(1);      // KEIN zweiter Request
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(false);
    expect(f.w.BildschleierSchalter.zustand().lokal).toBe(false);
    expect(f.knopf.classList.contains("is-clear")).toBe(true);
    expect(f.knopf.classList.contains("is-local")).toBe(false);
    expect(f.knopf.classList.contains("is-error")).toBe(false);
    expect(f.knopf.title).toBe("klar");
  });

  it("BS33 danach speichert der naechste Klick erneut", async () => {
    let n = 0;
    const f = _fenster(KLAR, () => (++n === 1 ? FEHLER_KLAR
      : { ok: true, status: 200,
          daten: { veiled: true, locked: false, reason: "chosen", tooltip: "v" } }));
    await f.w.BildschleierSchalter.umschalten();   // scheitert -> lokal
    await f.w.BildschleierSchalter.umschalten();   // lokal aufheben
    const ok = await f.w.BildschleierSchalter.umschalten();
    expect(ok).toBe(true);
    expect(f.aufrufe.length).toBe(2);
    expect(JSON.parse(f.aufrufe[1].opts.body)).toEqual({ veiled: true });
    expect(f.aufrufe[1].klasseBeimRequest).toBe(true);
    expect(f.neuGeladen()).toBe(1);
  });

  it("BS34 Netzwerkfehler beim Einschalten -> lokal", async () => {
    const f = _fenster(KLAR, new Error("offline"));
    await f.w.BildschleierSchalter.umschalten();
    expect(f.w.BildschleierSchalter.zustand().lokal).toBe(true);
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    expect(f.knopf.classList.contains("is-local")).toBe(true);
  });

  it("BS35 Blaettern im Zustand lokal", async () => {
    const f = _fenster(KLAR, FEHLER_KLAR);
    const S = f.w.BildschleierSchalter;
    await S.umschalten();
    S.seiteAnwenden({ veiled: false, locked: false, reason: "default",
                      tooltip: "klar", exempt_css: "a { }" });
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    expect(S.zustand().lokal).toBe(true);
    S.seiteAnwenden({ veiled: true, locked: false, reason: "chosen",
                      tooltip: "v", exempt_css: "" });
    expect(S.zustand().lokal).toBe(false);
    expect(f.knopf.classList.contains("is-local")).toBe(false);
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
  });

  it("BS36 klarer Zustand: Ausnahmen stehen bereit (D1)", () => {
    const f = _fenster(KLAR, { ok: true, status: 200, daten: {} });
    const S = f.w.BildschleierSchalter;
    S.seiteAnwenden({ veiled: false, locked: false, reason: "default",
                      tooltip: "klar", exempt_css: "html.aiw-image-veil x { }" });
    const stil = f.w.document.getElementById("aiw-image-veil-page");
    expect(stil).not.toBeNull();
    expect(stil.textContent).toBe("html.aiw-image-veil x { }");
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(false);
  });

  it("BS37 gescheitertes Ausschalten (gespeichert verschleiert) ist nicht lokal", async () => {
    const f = _fenster(VERSCHLEIERT, { ok: false, status: 500,
      daten: { veiled: true, locked: false, reason: "chosen", tooltip: "v",
               error: "store_failed", detail: "database is locked" } });
    await f.w.BildschleierSchalter.umschalten();
    expect(f.w.BildschleierSchalter.zustand().lokal).toBe(false);
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    expect(f.knopf.classList.contains("is-local")).toBe(false);
    // Ein weiterer Klick versucht erneut AUSzuschalten (mit Request).
    await f.w.BildschleierSchalter.umschalten();
    expect(f.aufrufe.length).toBe(2);
    expect(JSON.parse(f.aufrufe[1].opts.body)).toEqual({ veiled: false });
  });

  it("BS38 Blaettern waehrend das Einschalten gespeichert wird", async () => {
    let freigeben;
    const f = _fenster(KLAR, { ok: true, status: 200, daten: {} });
    // Eigene fetch-Attrappe, deren Antwort erst auf freigeben() kommt —
    // so laesst sich zwischen Anfrage und Antwort blaettern.
    f.w.fetch = () => new Promise((r) => { freigeben = () => r({
      ok: true, status: 200,
      json: () => Promise.resolve({ veiled: true, locked: false,
                                    reason: "chosen", tooltip: "v" }) }); });
    const S = f.w.BildschleierSchalter;
    const laeuft = S.umschalten();
    // Antwort steht aus — jetzt wird geblaettert, der Umschlag meldet "klar".
    S.seiteAnwenden({ veiled: false, locked: false, reason: "default",
                      tooltip: "klar", exempt_css: "" });
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    freigeben();
    expect(await laeuft).toBe(true);
    expect(f.neuGeladen()).toBe(1);
  });

  it("BS39 gescheitertes Ausschalten, gespeichert klar -> lokal", async () => {
    const f = _fenster(VERSCHLEIERT, FEHLER_KLAR);
    await f.w.BildschleierSchalter.umschalten();
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(true);
    expect(f.w.BildschleierSchalter.zustand().lokal).toBe(true);
    expect(f.knopf.classList.contains("is-local")).toBe(true);
    await f.w.BildschleierSchalter.umschalten();
    expect(f.aufrufe.length).toBe(1);      // Aufheben ohne Request
    expect(f.w.document.documentElement.classList.contains("aiw-image-veil")).toBe(false);
    expect(f.knopf.classList.contains("is-clear")).toBe(true);
  });
});
