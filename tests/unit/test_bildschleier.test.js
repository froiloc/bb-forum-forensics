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
 * MUTATIONSGEGENPROBE (Build 772): in umschalten() das Setzen der Klasse
 * hinter den Request verschoben -> BS20 rot.
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
});
