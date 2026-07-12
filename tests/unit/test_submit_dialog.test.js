/**
 * tests/unit/test_submit_dialog.test.js
 * IT-Forensisches Ermittlungswerkzeug — Berichtseditor: Zur Abnahme freigeben
 *
 * Testsuite fuer userinfo/submit_dialog.js (Build 382).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.SubmitDialog).
 *
 * SD01 — API verfuegbar.
 * SD02 — canSubmit: NUR eigener Bericht im Status 'draft'.
 * SD03 — dialogTexts: klaert ueber TRAGWEITE, PROZESS und RUECKHOLUNG auf.
 * SD04 — Dialog: Bestaetigen ist ANFANGS GESPERRT (zweistufig).
 * SD05 — Erst nach dem Kontrollkaestchen ist Bestaetigen moeglich -> onConfirm.
 * SD06 — Abbrechen schliesst den Dialog OHNE onConfirm.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("userinfo/submit_dialog.js", "utf-8");

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api() { return _ctx().SubmitDialog; }

describe("submit_dialog.js — Zur Abnahme freigeben (Build 382)", () => {
  it("SD01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.canSubmit).toBe("function");
    expect(typeof api.dialogTexts).toBe("function");
    expect(typeof api.open).toBe("function");
  });

  it("SD02: canSubmit — nur eigener Bericht im Entwurf", () => {
    const api = _api();
    const mine = { id: 1, status: "draft", created_by: "h002", title: "T" };

    // Eigener Entwurf -> ja.
    expect(api.canSubmit(mine, "h002")).toBe(true);

    // Fremder Entwurf -> nein.
    expect(api.canSubmit(mine, "h003")).toBe(false);

    // Eigener Bericht, aber schon eingereicht/abgenommen/versandt -> nein.
    ["submitted", "approved", "final"].forEach((st) => {
      expect(api.canSubmit({ ...mine, status: st }, "h002")).toBe(false);
    });

    // Kein Bericht / keine Kennung -> nein.
    expect(api.canSubmit(null, "h002")).toBe(false);
    expect(api.canSubmit(mine, null)).toBe(false);
  });

  it("SD03: dialogTexts klaert ueber Tragweite/Prozess/Rueckholung auf", () => {
    const api = _api();
    const t = api.dialogTexts("Zwischenbericht");
    expect(t.subject).toBe("Zwischenbericht");

    const keys = t.sections.map((s) => s.key);
    expect(keys).toEqual(["tragweite", "prozess", "rueckholung"]);

    const all = t.sections
      .map((s) => s.lines.join(" "))
      .join(" ");
    // (a) Tragweite: Sperre + was nicht mehr geht + Kommentare bleiben.
    expect(all).toContain("GESPERRT");
    expect(all).toContain("Kommentare");
    // (b) Prozess: Abnahme + Versiegelung.
    expect(all).toContain("Abnahme");
    expect(all).toContain("versiegelt");
    // (c) Rueckholung: NUR ueber Lektor/Chef-Ermittlerin.
    expect(all).toContain("NICHT zurueckholen");
    expect(all).toContain("Chef-Ermittlerin");
    // Bewusste Bestaetigung.
    expect(t.ackLabel).toContain("nicht mehr");
  });

  it("SD04: Bestaetigen ist anfangs gesperrt (zweistufig)", () => {
    const win = _ctx();
    const api = win.SubmitDialog;
    api.open(win.document, "Zwischenbericht", () => {});
    const confirm = win.document.getElementById("aiw-submit-confirm");
    expect(confirm).toBeTruthy();
    expect(confirm.disabled).toBe(true);   // kein Reflex-Klick moeglich
    // Alle drei Aufklaerungs-Abschnitte sind im DOM.
    expect(win.document.querySelectorAll(".aiw-submit-section").length).toBe(3);
  });

  it("SD05: nach bewusster Bestaetigung -> onConfirm", () => {
    const win = _ctx();
    const api = win.SubmitDialog;
    let confirmed = 0;
    api.open(win.document, "Zwischenbericht", () => { confirmed++; });

    const ack = win.document.getElementById("aiw-submit-ack");
    const confirm = win.document.getElementById("aiw-submit-confirm");

    // Klick ohne Bestaetigung bleibt wirkungslos.
    confirm.click();
    expect(confirmed).toBe(0);

    ack.checked = true;
    ack.dispatchEvent(new win.Event("change"));
    expect(confirm.disabled).toBe(false);

    confirm.click();
    expect(confirmed).toBe(1);
    // Dialog ist geschlossen.
    expect(win.document.getElementById("aiw-submit-overlay")).toBeNull();
  });

  it("SD06: Abbrechen schliesst ohne Einreichen", () => {
    const win = _ctx();
    const api = win.SubmitDialog;
    let confirmed = 0;
    api.open(win.document, "T", () => { confirmed++; });
    win.document.getElementById("aiw-submit-cancel").click();
    expect(confirmed).toBe(0);
    expect(win.document.getElementById("aiw-submit-overlay")).toBeNull();
  });
});
