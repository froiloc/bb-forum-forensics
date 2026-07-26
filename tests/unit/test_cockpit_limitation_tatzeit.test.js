/**
 * =============================================================================
 * tests/unit/test_cockpit_limitation_tatzeit.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7 · AP-3A · Build 535
 * =============================================================================
 * Testsuite fuer die Anzeige der FESTGESTELLTEN Tatzeit in der Sicht
 * "Fristen (Verjaehrung)".
 *
 * EIGENE DATEI, NICHT ANHANG AN test_cockpit_limitation.test.js: mc entwickelt
 * parallel Oberflaechenverbesserungen im Management als eigenen Branch
 * (Uebergabe §2.4 Nr. 22). Eine neue Datei laesst sich zusammenfuehren, ein
 * Einschub mitten in eine 700-Zeilen-Suite erzeugt Konflikte.
 *
 *   LT01 — Die neue Ankerart 'tatzeit' hat ein Label. Ohne es zeigte die Sicht
 *          'unbekannter Anker (tatzeit)' — kein stiller Fehler, aber die
 *          schlechteste denkbare Auskunft an der wichtigsten Stelle.
 *   LT02 — Das Label sagt FESTGESTELLT und ist damit von den Ersatzankern
 *          unterscheidbar; 'tatzeit' ist ausdruecklich KEIN Ersatzanker.
 *   LT03 — Eine festgestellte Zeile bekommt NICHT die Auszeichnung
 *          'is-vorlaeufig' — sie ist der einzige zitierfaehige Fall.
 *   LT04 — MEHRDEUTIGE Zeilen werden als solche gekennzeichnet (Klasse und
 *          Text), damit die uebergangene spaeteste Beendigung nicht unsichtbar
 *          bleibt.
 *   LT05 — Der uebergangene Zeitpunkt steht im title — WORTGLEICH aus dem
 *          Backend uebernommen, nicht neu formuliert.
 *   LT06 — Eine NICHT mehrdeutige Zeile bekommt weder Klasse noch Zusatztext
 *          (ein Hinweis ohne Anlass entwertet den Hinweis).
 * =============================================================================
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_limitation.js",
  "utf-8"
);

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

/** Eine Antwort des Backends mit EINER Zeile. */
function _daten(zeile) {
  return {
    stichtag: "2026-07-26",
    vorwarn_tage: 180,
    aussage_moeglich: true,
    verweigerungsgrund: null,
    params_stand: "2026-07-26",
    params_bestaetigt: true,
    vorgabe_tatbestaende: ["176", "184b"],
    vorbehalte: ["stellt keine Verjaehrung fest"],
    stellt_keine_verjaehrung_fest: true,
    nur_festgestellte_zitierfaehig: true,
    hinweise: [],
    faelle_gesamt: 1,
    zaehler: { offen: 1 },
    datenlage: { belegt: 1 },
    anker_verteilung: { tatzeit: 1 },
    feststellung_verteilung: { festgestellt: 1 },
    rows: [
      Object.assign(
        {
          subject_id: 101,
          username: "beschuldigter",
          ampel: "offen",
          feststellung: "festgestellt",
          anker_art: "tatzeit",
          anker_vermerke: [],
          tatzeit_tag: "2019-06-30",
          tatzeit_befund: "belegt",
          massgeblich_norm: "§ 184b StGB",
          massgeblich_ablauf_tag: "2029-06-30",
          restlaufzeit_tage: 1070,
          quellen: ["uid_posts.posted_ts"],
        },
        zeile || {}
      ),
    ],
  };
}

function _zelle(win, daten) {
  const doc = win.document;
  const wurzel = doc.createElement("div");
  doc.body.appendChild(wurzel);
  win.AIWCockpitLimitation.renderLimitation(wurzel, daten, {});
  return wurzel.querySelector(".aiw-lim-grundlage");
}

describe("Fristen-Sicht — festgestellte Tatzeit (Build 535)", () => {
  // ===================================================================== LT01
  it("LT01: die Ankerart 'tatzeit' hat ein Label", () => {
    const api = _win().AIWCockpitLimitation;
    const label = api.ankerLabel("tatzeit");
    expect(label).toBeTruthy();
    expect(label).not.toMatch(/unbekannter Anker/);
  });

  // ===================================================================== LT02
  it("LT02: das Label sagt FESTGESTELLT und ist kein Ersatzanker", () => {
    const api = _win().AIWCockpitLimitation;
    expect(api.ankerLabel("tatzeit")).toMatch(/FESTGESTELLTE/);
    // Die Abgrenzung ist die eigentliche Aussage: ein Ersatzanker ist ein
    // Hilfswert, eine Feststellung das Gegenteil davon.
    expect(api.ankerLabel("registrierung")).toMatch(/ERSATZANKER/);
    expect(api.istErsatzanker("tatzeit")).toBe(false);
  });

  // ===================================================================== LT03
  it("LT03: eine festgestellte Zeile ist nicht 'vorlaeufig' ausgezeichnet", () => {
    const win = _win();
    const gz = _zelle(win, _daten());
    expect(gz).not.toBeNull();
    expect(gz.className).not.toMatch(/is-vorlaeufig/);
    expect(gz.className).not.toMatch(/is-ersatzanker/);
    expect(gz.textContent).toMatch(/FESTGESTELLTE Tatzeit/);
  });

  // ===================================================================== LT04
  it("LT04: mehrdeutige Zeilen werden gekennzeichnet", () => {
    const win = _win();
    const gz = _zelle(
      win,
      _daten({
        tatzeit_mehrdeutig: true,
        tatzeit_frueheste_beendigung: 1561852800,
        tatzeit_spaeteste_beendigung: 1672444800,
        tatzeit_feststellung_detail:
          "2 festgestellte(r) Tatzeitraum/-raeume; verankert wird die " +
          "FRUEHESTE Beendigung (2019-06-30); NICHT verankert wurde die " +
          "spaeteste Beendigung 2022-12-31",
      })
    );
    expect(gz.className).toMatch(/is-mehrdeutig/);
    expect(gz.textContent).toMatch(/mehrdeutig/);
  });

  // ===================================================================== LT05
  it("LT05: der übergangene Zeitpunkt steht wortgleich im title", () => {
    const win = _win();
    const detail =
      "2 festgestellte(r) Tatzeitraum/-raeume; verankert wird die FRUEHESTE " +
      "Beendigung (2019-06-30); NICHT verankert wurde die spaeteste " +
      "Beendigung 2022-12-31";
    const gz = _zelle(
      win,
      _daten({ tatzeit_mehrdeutig: true, tatzeit_feststellung_detail: detail })
    );
    const title = gz.getAttribute("title") || "";
    // WORTGLEICH — keine zweite Formulierung derselben Tatsache.
    expect(title).toContain(detail);
    expect(title).toContain("2022-12-31");
  });

  // ===================================================================== LT06
  it("LT06: ohne Mehrdeutigkeit gibt es weder Klasse noch Zusatztext", () => {
    const win = _win();
    const gz = _zelle(
      win,
      _daten({
        tatzeit_mehrdeutig: false,
        tatzeit_feststellung_detail:
          "1 festgestellte(r) Tatzeitraum/-raeume; verankert wird die " +
          "FRUEHESTE Beendigung (2019-06-30)",
      })
    );
    expect(gz.className).not.toMatch(/is-mehrdeutig/);
    expect(gz.textContent).not.toMatch(/mehrdeutig/);
    // Und der Detailtext drängt sich nicht in den title, wo er nichts erklärt.
    expect(gz.getAttribute("title") || "").not.toMatch(/Tatzeitraum/);
  });
});
