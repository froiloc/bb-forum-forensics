/**
 * tests/unit/test_cockpit_export_button.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Akten-Export (AP-2B/B1)
 *
 * Testsuite fuer den Akten-Export-Knopf in cockpit.js (Build 512).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpit).
 *
 * EX01 — isExportable/EXPORTABLE_VIEWS: die Liste deckt den VIEW_CATALOG bis
 *        auf die drei bewusst ausgenommenen Sichten ab — dieselbe Zusicherung
 *        wie serverseitig VE08, damit ein Knopf weder fehlt noch ins Leere
 *        zeigt.
 * EX02 — exportUrl ohne Sicht-Parameter.
 * EX03 — exportParams je Sicht: Alias (Zahl -> subject_id, Text -> q,
 *        Widerrufene), Merge (Gruppe, getrennte), Querfunde (BEIDE Filter),
 *        Onboarding (person_id/kind), Kapazitaet (start/end).
 * EX04 — eine Sicht ohne eigene Parameter liefert ein leeres Objekt (und der
 *        Export damit den vollen Bestand — das ist dort richtig).
 * EX05 — Kodierung: Sonderzeichen im Suchbegriff werden URL-kodiert
 *        (ein '&' im Alias darf keinen zusaetzlichen Parameter erzeugen).
 * EX06 — der erzeugte Ausschnitt ENTSPRICHT der Sicht: derselbe State
 *        erzeugt dieselben Parameter, die die Sicht selbst anfragen wuerde.
 *
 * Version: v0.8.512 · Build: 512 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/cockpit.js", "utf-8");

function _api() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window.AIWCockpit;
}

// Deckungsgleich mit _BEWUSST_OHNE_EXPORT in tests/test_view_export_api.py
// und mit dem Kommentar in view_export_catalog.py.
const OHNE_EXPORT = ["notes", "lectorate", "approval"];

describe("cockpit.js — Akten-Export-Knopf (Build 512, AP-2B/B1)", () => {
  // EX01 ---------------------------------------------------------------------
  it("EX01: Exportliste deckt den VIEW_CATALOG bis auf die Ausnahmen", () => {
    const api = _api();
    const alle = api.VIEW_CATALOG.map((v) => v.id);

    const fehlend = alle.filter(
      (id) => !api.isExportable(id) && OHNE_EXPORT.indexOf(id) === -1
    );
    expect(fehlend).toEqual([]);

    // Die Ausnahmen bieten ausdruecklich KEINEN Knopf an.
    OHNE_EXPORT.forEach((id) => {
      expect(api.isExportable(id)).toBe(false);
    });

    // Und die Liste erfindet keine Sichten, die es nicht gibt.
    const verwaist = Object.keys(api.EXPORTABLE_VIEWS).filter(
      (id) => alle.indexOf(id) === -1
    );
    expect(verwaist).toEqual([]);

    expect(api.isExportable("gibtsnicht")).toBe(false);
    expect(api.isExportable(undefined)).toBe(false);
  });

  // EX02 ---------------------------------------------------------------------
  it("EX02: exportUrl ohne Parameter", () => {
    const api = _api();
    expect(api.exportUrl("policy", {})).toBe(
      "/api/view/export?view=policy"
    );
  });

  // EX03 ---------------------------------------------------------------------
  it("EX03: exportParams bilden den Ausschnitt der jeweiligen Sicht ab", () => {
    const api = _api();

    // Alias: reine Zahl -> Konto, sonst Namenssuche.
    expect(api.exportParams("alias", { aliasQuery: "4711" })).toEqual({
      subject_id: "4711",
    });
    expect(api.exportParams("alias", { aliasQuery: "Panther" })).toEqual({
      q: "Panther",
    });
    expect(
      api.exportParams("alias", {
        aliasQuery: "Panther",
        aliasInclRetracted: true,
      })
    ).toEqual({ q: "Panther", include_retracted: "1" });

    // Merge: nur eine reine Zahl ist eine Gruppenabfrage.
    expect(api.exportParams("merge", { mergeQuery: "4711" })).toEqual({
      subject_id: "4711",
    });
    expect(api.exportParams("merge", { mergeQuery: "kein-konto" })).toEqual({});
    expect(api.exportParams("merge", { mergeInclSplit: true })).toEqual({
      include_split: "1",
    });

    // Querfunde: BEIDE Filter, unabhaengig voneinander.
    expect(
      api.exportParams("crossfindings", { cfOnlyOpen: true })
    ).toEqual({ only_open: "1" });
    expect(
      api.exportParams("crossfindings", { cfOnlyOpen: true, cfOnlyUnack: true })
    ).toEqual({ only_open: "1", only_unacknowledged: "1" });

    // Onboarding: person_id ist dort Pflicht des Endpunkts.
    expect(
      api.exportParams("onboarding", { onbPerson: 7, onbKind: "onboarding" })
    ).toEqual({ person_id: "7", kind: "onboarding" });

    // Kapazitaet: Zeitraum.
    expect(
      api.exportParams("capacity", {
        capacityPeriod: { start: "2026-01-01", end: "2026-03-31" },
      })
    ).toEqual({ start: "2026-01-01", end: "2026-03-31" });
  });

  // EX04 ---------------------------------------------------------------------
  it("EX04: Sichten ohne eigene Parameter liefern ein leeres Objekt", () => {
    const api = _api();
    ["policy", "workload", "stats", "integrity", "crossref"].forEach((v) => {
      expect(api.exportParams(v, { aliasQuery: "stoert-nicht" })).toEqual({});
    });
    // Robust gegen fehlenden State.
    expect(api.exportParams("alias", null)).toEqual({});
    expect(api.exportParams("alias", undefined)).toEqual({});
  });

  // EX05 ---------------------------------------------------------------------
  it("EX05: Parameter werden URL-kodiert", () => {
    const api = _api();
    // Ein '&' oder '=' im Suchbegriff darf KEINEN zusaetzlichen Parameter
    // erzeugen — sonst exportierte man einen anderen Ausschnitt als gesucht.
    const url = api.exportUrl("alias", { aliasQuery: "a&b=c d" });
    expect(url).toBe("/api/view/export?view=alias&q=a%26b%3Dc%20d");
    expect(url.split("&").length).toBe(2); // view + q, nicht mehr

    // Nicht-ASCII bleibt eindeutig kodiert (multilinguales Forum).
    expect(api.exportUrl("alias", { aliasQuery: "Ярослав" })).toContain(
      encodeURIComponent("Ярослав")
    );
  });

  // EX06 ---------------------------------------------------------------------
  it("EX06: voller State erzeugt genau die erwartete URL", () => {
    const api = _api();
    const state = {
      aliasQuery: "Panther",
      aliasInclRetracted: true,
      cfOnlyOpen: true,
      cfOnlyUnack: true,
    };
    // Nur die Parameter der AKTIVEN Sicht landen in der URL — der State
    // anderer Sichten darf nicht durchschlagen.
    expect(api.exportUrl("alias", state)).toBe(
      "/api/view/export?view=alias&q=Panther&include_retracted=1"
    );
    expect(api.exportUrl("crossfindings", state)).toBe(
      "/api/view/export?view=crossfindings&only_open=1&only_unacknowledged=1"
    );
  });
});
