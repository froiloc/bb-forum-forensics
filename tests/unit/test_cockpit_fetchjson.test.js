/**
 * tests/unit/test_cockpit_fetchjson.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * fetchJson — der LESENDE Abruf, Build 657
 *
 * ANLASS: Vorfall 2026-08-02. Die Sicht "Baustein-Module" antwortete mit
 * HTTP 500. Der Server schickte im Koerper 'detail' ("no such column:
 * block_type") und haette mit Build 657 auch 'massnahme' geschickt — den
 * Satz, der sagt, WAS ZU TUN IST. fetchJson warf beides weg und meldete
 * 'HTTP 500 bei /api/templates/modules'. Am Bildschirm stand eine Zahl.
 *
 * Die Asymmetrie war das Aergerliche: postJson daneben wertet Fehlerkoerper
 * seit jeher aus ("Grundregel 1: kein stiller Fehlschlag"). Nur der
 * Lesepfad war taub.
 *
 * FJ01 — Erfolg: der Koerper kommt als Objekt zurueck (unveraendert).
 * FJ02 — DER KERNFALL: 'massnahme' und 'detail' stehen in der Fehlermeldung.
 * FJ03 — kein JSON im Koerper: der Rohtext kommt mit, gekuerzt.
 * FJ04 — leerer oder unlesbarer Koerper: es bleibt bei der Zahl, aber es
 *        wird GESAGT, dass nichts da war.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/cockpit.js", "utf-8");

function _ctx(fetchStub) {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body><div id='aiw-main'></div>" +
    "<nav id='aiw-nav'></nav></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.fetch = fetchStub;
  dom.window.eval(_src);
  return dom.window;
}

/** Eine Antwort, wie fetch sie liefert. */
function _antwort(status, koerper, opts) {
  opts = opts || {};
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status: status,
    json: () => (opts.jsonWirft
      ? Promise.reject(new Error("kein JSON"))
      : Promise.resolve(JSON.parse(koerper))),
    text: () => (opts.textWirft
      ? Promise.reject(new Error("Koerper nicht lesbar"))
      : Promise.resolve(koerper)),
  });
}

describe("fetchJson — der Lesepfad (Build 657)", () => {
  it("FJ01 — Erfolg bleibt Erfolg", async () => {
    const win = _ctx(() => _antwort(200, '{"count":2,"modules":[]}'));
    const d = await win.AIWCockpit.fetchJson("/api/templates/modules");
    expect(d).toEqual({ count: 2, modules: [] });
  });

  it("FJ02 — die Massnahme des Servers kommt an", async () => {
    // Genau der Koerper, den der Server am 2026-08-02 geschickt haette.
    const koerper = JSON.stringify({
      error: "templates_read_failed",
      detail: "no such column: block_type",
      massnahme: "templates.db ist angebunden, aber unvollstaendig migriert. "
        + "Es fehlen die Spalten: report_modules.block_type. Abhilfe: "
        + "management/migrate_templates_blocktyp.py (Build 655) ausfuehren.",
    });
    const win = _ctx(() => _antwort(500, koerper));

    await expect(
      win.AIWCockpit.fetchJson("/api/templates/modules")
    ).rejects.toThrow(/HTTP 500 bei \/api\/templates\/modules/);

    let meldung = "";
    try { await win.AIWCockpit.fetchJson("/api/templates/modules"); }
    catch (e) { meldung = e.message; }

    // DIE MASSNAHME ZUERST — sie sagt, was zu tun ist.
    expect(meldung).toContain("Abhilfe");
    expect(meldung).toContain("migrate_templates_blocktyp.py");
    // Und die Ursache steht daneben.
    expect(meldung).toContain("no such column: block_type");
    // Mit der Fassung aus Build 656 stand hier NUR die Zahl.
    expect(meldung.length).toBeGreaterThan(60);
  });

  it("FJ03 — kein JSON: der Rohtext kommt mit", async () => {
    const win = _ctx(() => _antwort(502, "<html>Bad Gateway</html>"));
    let meldung = "";
    try { await win.AIWCockpit.fetchJson("/api/x"); }
    catch (e) { meldung = e.message; }
    expect(meldung).toContain("HTTP 502");
    expect(meldung).toContain("Bad Gateway");

    // Sehr lange Koerper werden gekuerzt — eine Fehlermeldung, die eine
    // ganze HTML-Seite enthaelt, liest niemand.
    const lang = "x".repeat(5000);
    const win2 = _ctx(() => _antwort(500, lang));
    let m2 = "";
    try { await win2.AIWCockpit.fetchJson("/api/x"); } catch (e) { m2 = e.message; }
    expect(m2.length).toBeLessThan(400);
  });

  it("FJ04 — nichts lesbar: dann wird auch DAS gesagt", async () => {
    // Leerer Koerper -> es bleibt bei der Zahl, ohne angehaengtes Nichts.
    const win = _ctx(() => _antwort(403, ""));
    let m = "";
    try { await win.AIWCockpit.fetchJson("/api/x"); } catch (e) { m = e.message; }
    expect(m).toBe("HTTP 403 bei /api/x");

    // Koerper gar nicht lesbar -> das ist ein eigener Befund und wird
    // benannt, statt wie 'kein Grund' auszusehen.
    const win2 = _ctx(() => _antwort(500, "", { textWirft: true }));
    let m2 = "";
    try { await win2.AIWCockpit.fetchJson("/api/x"); } catch (e) { m2 = e.message; }
    expect(m2).toContain("nicht lesbar");
  });
});
