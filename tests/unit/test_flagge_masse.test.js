/**
 * test_flagge_masse.test.js
 * Regressionstests: Die Uebersetzungsflagge behaelt ihre Masse
 * Baustelle 3 · Build 707 · 2026-08-12 · Vorgang da84f94f (Nachtrag)
 *
 * ---------------------------------------------------------------------------
 * DER BEFUND (Alex, 12.08.2026): In der PN-Ansicht war die Flagge "stark in
 * die Breite verzerrt", im Forenbeitrag dagegen richtig — bei identischem
 * Markup. Ursache ist das Zusammentreffen dreier Umstaende:
 *   1. Seit Build 703 haengt die Flagge in einem <li> (davor: <span> direkt
 *      im <ul>). Damit greifen Seitenregeln der Form 'li ... span' auf ihr.
 *   2. Das Flaggenbild IST ein <span> (.aiw-flag-de) im Knopf.
 *   3. Die Stilvorlage der Seite wird bei jeder Navigation NACH toolbar.css
 *      in den Kopf der Schale gezogen (_updateHead) und gewinnt bei gleicher
 *      Spezifitaet. '.aiw-flag-de' (eine Klasse) verlor gegen
 *      '.postfootright ul li span' (eine Klasse + drei Elemente).
 *
 * ---------------------------------------------------------------------------
 * WARUM HIER DER STILBOGEN GEPRUEFT WIRD UND NICHT DIE GERECHNETE BREITE:
 * jsdom rechnet keine Spezifitaet aus — es nimmt bei zwei Regeln fuer
 * dieselbe Eigenschaft schlicht die zuletzt gelesene. Ein
 * getComputedStyle-Test waere hier also GRUEN, ohne irgendetwas zu belegen,
 * und ROT, sobald man die Reihenfolge der Stilboegen aendert. Gemessen wurde
 * die Wirkung deshalb im echten Chromium (Ergebnis in der Uebergabe zu Build
 * 707: vorher 590 px breit, danach 20 x 13 px, gleich in beiden Ansichten).
 *
 * DIESE DATEI SICHERT DAS, WAS DIE MESSUNG TRAGFAEHIG MACHT: dass die
 * Massangaben unter einem Selektor mit ZWEI Klassen stehen und festgenagelt
 * sind — und dass die Ausblendung in der Originalansicht dabei NICHT
 * ausgehebelt wird. Faellt eines davon weg, kehrt der Fehler zurueck.
 *
 * FAELLE
 *   FM01  Die Masse des Flaggenbildes sind auf 20 x 13 px festgenagelt
 *   FM02  Der Selektor fuehrt zwei Klassen (schlaegt 'li span' der Seite)
 *   FM03  Knopf und Eintrag nageln 'display' NICHT fest
 *         (sonst bliebe die Flagge in der Originalansicht stehen)
 *   FM04  Der Eintrag stellt sich in die Reihe statt die Zeile zu fuellen
 * ===========================================================================*/

import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(join(__dirname, "../../toolbar/toolbar.css"), "utf-8");

/**
 * Liest den Regelblock zu einem Selektor aus dem Stilbogen.
 * Bewusst eine einfache Suche statt eines CSS-Zerlegers: geprueft wird eine
 * Handvoll Eigenschaften an drei Selektoren, und der Zerleger waere die
 * groessere Fehlerquelle als das, was er pruefen soll.
 */
function regelblock(selektor) {
  const i = CSS.indexOf(selektor + " {");
  if (i === -1) return null;
  const von = CSS.indexOf("{", i);
  const bis = CSS.indexOf("}", von);
  return CSS.slice(von + 1, bis);
}

/** Wert einer Eigenschaft im Block, ohne abschliessendes Semikolon. */
function wert(block, eigenschaft) {
  const m = new RegExp("(?:^|;|\\n)\\s*" + eigenschaft + "\\s*:([^;]+)")
    .exec(block);
  return m ? m[1].trim() : null;
}

describe("Uebersetzungsflagge — feste Masse (Vorgang da84f94f, Nachtrag)", () => {

  let flagge;
  beforeAll(() => {
    flagge = regelblock(".aiw-translate-flag .aiw-flag-de");
  });

  it("FM01: 20 x 13 px, festgenagelt gegen die Stilvorlage der Seite", () => {
    expect(flagge).not.toBeNull();
    for (const [eigenschaft, sollwert] of [
      ["width", "20px"], ["height", "13px"],
      ["min-width", "20px"], ["max-width", "20px"],
      ["min-height", "13px"], ["max-height", "13px"],
    ]) {
      const v = wert(flagge, eigenschaft);
      expect(v, eigenschaft + " fehlt").not.toBeNull();
      expect(v, eigenschaft + " ohne Mass").toContain(sollwert);
      // Ohne '!important' genuegt schon eine Seitenregel mit zwei Klassen,
      // um die Flagge wieder zu verformen. Die Stilvorlage der Seite ist
      // Beweismittel und wird nicht angetastet — die Abwehr liegt hier.
      expect(v, eigenschaft + " nicht festgenagelt").toContain("!important");
    }
  });

  it("FM02: der Selektor fuehrt ZWEI Klassen", () => {
    // Spezifitaet: Klassen zaehlen vor Elementen. (0,2,0) schlaegt
    // '.postfootright ul li span' = (0,1,3) — unabhaengig davon, welcher
    // Stilbogen zuletzt geladen wird. Genau daran hat es gefehlt.
    const treffer = ".aiw-translate-flag .aiw-flag-de".match(/\.[a-z0-9-]+/gi);
    expect(treffer.length).toBeGreaterThanOrEqual(2);
  });

  it("FM03: bei Knopf und Eintrag ist 'display' NICHT festgenagelt", () => {
    // 'body.aiw-view-original .aux-part { display:none !important }' blendet
    // alle AIW-Elemente in der Originalansicht aus. Stuende hier ebenfalls
    // ein '!important' auf 'display', entschiede bei gleichem Rang die
    // Reihenfolge — und die Flagge bliebe in der Originalansicht stehen.
    for (const sel of [".aiw-translate-flag.aux-part",
                       "li.aiw-translate-item.aux-part"]) {
      const block = regelblock(sel);
      expect(block, sel + " fehlt").not.toBeNull();
      const d = wert(block, "display");
      expect(d, sel + ": display fehlt").not.toBeNull();
      expect(d, sel + ": display darf nicht festgenagelt sein")
        .not.toContain("!important");
    }
  });

  it("FM04: der Eintrag stellt sich in die Reihe", () => {
    const eintrag = regelblock("li.aiw-translate-item.aux-part");
    expect(wert(eintrag, "display")).toContain("inline-block");
    expect(wert(eintrag, "width")).toContain("auto");
    expect(wert(eintrag, "list-style")).toContain("none");
    const knopf = regelblock(".aiw-translate-flag.aux-part");
    expect(wert(knopf, "width")).toContain("auto");
  });
});
