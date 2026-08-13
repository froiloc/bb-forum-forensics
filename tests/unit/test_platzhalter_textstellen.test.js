/**
 * tests/unit/test_platzhalter_textstellen.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 * ALLE TEXTSTELLEN EINES BLOCKS, Build 710
 *
 * Gegenstand: userinfo/placeholder_chips.js — mapBlockTexts und die drei
 * Funktionen, die darauf aufsetzen (hydrateBlockData, dehydrateBlockData,
 * collectBlockTexts / extractFieldsFromBlockData).
 *
 * ---------------------------------------------------------------------------
 * DER BEFUND
 * ---------------------------------------------------------------------------
 * Gemessen am 12.08.2026. mapBlockTexts liess ZWEI Textstellen aus:
 *
 *   Liste, VERSCHACHTELTER Eintrag (items[].items[]) .... nicht gesehen
 *   Zitat, QUELLENANGABE (caption) ..................... nicht gesehen
 *
 * Beides sind belegte Textstellen. klartextAus() in
 * cockpit_baustein_eingabe.js geht rekursiv in Unterlisten und liest
 * 'caption'; editor/html_renderer.py:127-151 rendert 'caption' als
 * <cite class="cdx-quote__caption"> in den Vermerk.
 *
 * WAS DAS GEKOSTET HAT - und warum es mehr ist als ein Anzeigefehler:
 *   userinfo/placeholder_wizard.js:241,636 bestimmt ueber
 *   extractFieldsFromBlockData, welche Pflicht- und Optionalplatzhalter dem
 *   Ermittler beim Schreiben eines Vermerks zum Ausfuellen ANGEBOTEN werden.
 *   Ein {{m:...}} an einer der beiden Stellen wurde nie angeboten - und stand
 *   danach als roher Vorlagentext im unterschriebenen Vermerk.
 *
 *   Die Platzhalter-Tabelle der Bausteinsicht (Build 683) liest dieselbe
 *   Quelle. Sie war bis Build 682 auf den body-Spiegel gestuetzt, der BEIDE
 *   Stellen enthaelt - fuer diese zwei Faelle hat Build 683 die Abdeckung
 *   also VERENGT, mit der Begruendung, sie zu erweitern.
 *
 * ---------------------------------------------------------------------------
 * Testfaelle
 * ---------------------------------------------------------------------------
 *   PT01 — collectBlockTexts sieht verschachtelte Listeneintraege, bis in
 *          die dritte Ebene.
 *   PT02 — collectBlockTexts sieht die Quellenangabe eines Zitats.
 *   PT03 — extractFieldsFromBlockData bietet die Pflichtfelder aus beiden
 *          Stellen an. DAS IST DER FALL MIT DEN FOLGEN: was hier fehlt,
 *          fragt der Ausfuell-Assistent nie ab.
 *   PT04 — hydrateBlockData erzeugt an beiden Stellen Chips.
 *   PT05 — SYMMETRIE: hydrate -> dehydrate ergibt wieder den Ausgangsstand.
 *          Griffe nur eine Seite auf die neuen Stellen zu, bliebe Chip-HTML
 *          in der Datenbank stehen.
 *   PT06 — DAS ORIGINAL BLEIBT UNBERUEHRT, auch verschachtelt. Die Vorschau
 *          bekommt denselben Datensatz, der gleich gespeichert wird.
 *   PT07 — GEGENPROBE gegen Uebereifer: Felder, die keine Textstellen sind
 *          (level, style, withHeadings), werden nicht angefasst.
 *   PT08 — eine im Kreis zeigende Struktur beendet den Lauf. block_data
 *          kommt aus einer Datenbank und ist nicht vertrauenswuerdig.
 *
 * Die Entsprechung auf dem Server prueft
 * tests/test_placeholder_textstellen.py (PY-Reihe PS01-PS05).
 *
 * Version: 0.1.0 · Build: 710 · 2026-08-13
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("userinfo/placeholder_chips.js", "utf-8");

function _pc() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>",
    { runScripts: "dangerously", url: "http://localhost" });
  dom.window.FORENSIC_DEBUG = false;
  dom.window.eval(_src);
  return dom.window.PlaceholderChips;
}

/** Eine Liste mit drei Verschachtelungsebenen. */
const LISTE = () => ({
  style: "unordered",
  items: [
    { content: "Ebene 1 {{a:user.username}}", items: [
      { content: "Ebene 2 {{m:spurennummer}}", items: [
        { content: "Ebene 3 {{o:bemerkung}}", items: [] },
      ] },
    ] },
  ],
});

/** Ein Zitat mit Quellenangabe. */
const ZITAT = () => ({
  text: "Der Zeuge sagte aus {{a:user.id}}",
  caption: "Vernehmung {{m:aktenzeichen}}",
});

const istChip = (s) => typeof s === "string" && s.indexOf("ph-chip") >= 0;

describe("Textstellen eines Blocks (Build 710)", () => {
  // PT01 -------------------------------------------------------------------
  it("PT01: collectBlockTexts sieht verschachtelte Listeneintraege", () => {
    const texte = _pc().collectBlockTexts(LISTE());
    expect(texte).toEqual([
      "Ebene 1 {{a:user.username}}",
      "Ebene 2 {{m:spurennummer}}",
      "Ebene 3 {{o:bemerkung}}",
    ]);
  });

  // PT02 -------------------------------------------------------------------
  it("PT02: collectBlockTexts sieht die Quellenangabe eines Zitats", () => {
    const texte = _pc().collectBlockTexts(ZITAT());
    expect(texte).toContain("Vernehmung {{m:aktenzeichen}}");
    expect(texte).toContain("Der Zeuge sagte aus {{a:user.id}}");
  });

  // PT03 -------------------------------------------------------------------
  it("PT03: der Ausfuell-Assistent bekommt die Pflichtfelder beider Stellen",
    () => {
      const pc = _pc();
      // DAS IST DER FALL MIT DEN FOLGEN. Was diese Funktion nicht liefert,
      // wird dem Ermittler nie zum Ausfuellen angeboten - und steht danach
      // als roher Vorlagentext im unterschriebenen Vermerk.
      const ausListe = pc.extractFieldsFromBlockData(LISTE(), "m")
        .map((f) => f.name);
      expect(ausListe).toContain("spurennummer");

      const ausZitat = pc.extractFieldsFromBlockData(ZITAT(), "m")
        .map((f) => f.name);
      expect(ausZitat).toContain("aktenzeichen");

      // Und die optionalen ebenso - auch die aus der dritten Ebene.
      expect(pc.extractFieldsFromBlockData(LISTE(), "o").map((f) => f.name))
        .toContain("bemerkung");
    });

  // PT04 -------------------------------------------------------------------
  it("PT04: hydrateBlockData erzeugt an beiden Stellen Chips", () => {
    const pc = _pc();
    const l = pc.hydrateBlockData(LISTE());
    expect(istChip(l.items[0].content)).toBe(true);
    expect(istChip(l.items[0].items[0].content)).toBe(true);
    expect(istChip(l.items[0].items[0].items[0].content)).toBe(true);

    const z = pc.hydrateBlockData(ZITAT());
    expect(istChip(z.text)).toBe(true);
    expect(istChip(z.caption)).toBe(true);
  });

  // PT05 -------------------------------------------------------------------
  it("PT05: hydrate und dehydrate erfassen DIESELBEN Stellen", () => {
    const pc = _pc();
    for (const bau of [LISTE, ZITAT]) {
      const vorher = bau();
      const zurueck = pc.dehydrateBlockData(pc.hydrateBlockData(vorher));
      // Griffe nur eine der beiden Seiten auf die neuen Stellen zu, bliebe
      // dort Chip-HTML stehen und ginge so in die Datenbank.
      expect(zurueck).toEqual(vorher);
    }
  });

  // PT06 -------------------------------------------------------------------
  it("PT06: das Original bleibt unberuehrt, auch verschachtelt", () => {
    const pc = _pc();
    const original = LISTE();
    const kopie = JSON.parse(JSON.stringify(original));
    pc.hydrateBlockData(original);
    // Die Vorschau bekommt denselben Datensatz, der gleich gespeichert wird.
    // Wuerde hier in place hydriert, stuende Chip-HTML in der Datenbank.
    expect(original).toEqual(kopie);
  });

  // PT07 -------------------------------------------------------------------
  it("PT07: Felder, die keine Textstellen sind, bleiben unangetastet", () => {
    const pc = _pc();
    const daten = { text: "{{m:x}}", level: 2, style: "ordered",
                    withHeadings: true, url: "bild.png" };
    const raus = pc.mapBlockTexts
      ? pc.mapBlockTexts(daten, () => "ERSETZT")
      : pc.hydrateBlockData(daten);
    expect(raus.level).toBe(2);
    expect(raus.style).toBe("ordered");
    expect(raus.withHeadings).toBe(true);
    // 'url' ist KEINE Platzhalter-Textstelle. Sie mitzunehmen waere
    // Uebereifer - und ein Chip in einer Bild-URL waere ein kaputtes Bild.
    expect(raus.url).toBe("bild.png");
  });

  // PT08 -------------------------------------------------------------------
  it("PT08: eine im Kreis zeigende Struktur beendet den Lauf", () => {
    const pc = _pc();
    // block_data kommt aus einer Datenbank und ist nicht vertrauenswuerdig.
    // Ohne Tiefengrenze liefe das hier nicht zu Ende - in einem Pfad, der
    // beim Rendern des Editors laeuft.
    const eintrag = { content: "{{m:x}}", items: [] };
    eintrag.items.push(eintrag);
    expect(() => pc.hydrateBlockData({ items: [eintrag] })).not.toThrow();
    expect(() => pc.collectBlockTexts({ items: [eintrag] })).not.toThrow();
  });
});
