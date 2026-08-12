/**
 * test_minimap_kontrast.test.js
 *
 * Unit-Tests: Farbkontrast der Marker in der Minimap (Spurenkarte).
 * Ticket 602c7557-7639-4f73-8bce-5bfbd0aca3e4 — "Kontrast verbessern in
 * Minimap im Forumfenster", gemeldet von Alex am 30.07.2026.
 *
 * ---------------------------------------------------------------------------
 * WARUM ES DIESEN TEST GIBT — die eigentliche Lehre aus dem Vorgang
 * ---------------------------------------------------------------------------
 * Der Befund war nicht, dass eine Farbe zu dunkel gewaehlt war. Der Befund
 * war, dass der Kontrast FALSCH GERECHNET wurde: In Build 649 ist
 * .forensic-minimap-trace mit "rund 3,0:1" als gerade noch regelkonform
 * eingestuft worden. Diese Zahl entstand aus der Sollfarbe im Quelltext
 * (#3a5a8a gegen #11141e). Uebersehen wurde die `opacity: 0.55` am selben
 * Element. Die Deckkraft verrechnet die Farbe gegen den Grund, BEVOR das
 * Auge sie sieht — der wirklich sichtbare Wert lag bei 1,62:1.
 *
 * Eine Pruefung, die nur die Sollfarbe betrachtet, haette diesen Fehler
 * bestaetigt statt ihn zu finden. Deshalb rechnet dieser Test die Werte
 * SELBST nach, und zwar aus den Quelldateien:
 *   - die Markerfarben aus toolbar/toolbar.js (dort setzt _makeBar sie inline),
 *   - Grundfarbe und Deckkraft aus toolbar/toolbar.css.
 * Er wiederholt KEINE Konstanten aus dem Bestand. Wer eine Farbe aendert oder
 * eine `opacity` ergaenzt, faellt hier auf — auch dann, wenn er den Test
 * gar nicht gelesen hat. Genau das war beim ersten Mal noetig gewesen.
 *
 * MASSSTAB: WCAG 2.1, Erfolgskriterium 1.4.11 "Non-text Contrast" verlangt
 * fuer grafische Objekte, die zum Verstaendnis noetig sind, mindestens 3,0:1
 * gegen den angrenzenden Grund. Die Minimap ist genau das: sie zeigt, WO auf
 * der Seite der Beschuldigte aktiv war. Ein Marker, den man nicht sieht,
 * fuehrt dazu, dass eine Spur uebersehen wird — das beruehrt Grundregel 1
 * des Projekts ("Kein Beleg darf je still uebersprungen werden") und ist
 * damit keine reine Gestaltungsfrage.
 *
 * ZIELWERT 4,5:1 fuer die Spuren (Entscheidung Alex, 12.08.2026): oberhalb
 * des Minimums, aber innerhalb der Spanne der Annotationsmarker (3,27:1 bis
 * 7,71:1). Ein hoeherer Wert haette die Spuren heller gemacht als die Haelfte
 * der Befundmarker und die Rangfolge "Spur zeigt Relevanz, Marke zeigt Befund"
 * im Helligkeitseindruck umgekehrt.
 *
 * DER ALIAS-MARKER IST IN BUILD 700 MITGEZOGEN WORDEN (Entscheidung Alex,
 * 12.08.2026), obwohl er das Minimum bereits erfuellte. Er trug dieselbe
 * Konstruktion: Sollfarbe #c8a000 (7,43:1), sichtbar mit opacity 0.65 aber
 * nur 3,78:1. Der Unterschied zu den Spuren ist die RICHTUNG der Korrektur —
 * hier war ABzusenken. Ohne Deckkraft haette #c8a000 jeden Befundmarker
 * ausser CAT_PERSON ueberstrahlt; der Alias ist aber ein Orientierungspunkt
 * und kein Befund. Neuer Wert #AB8900 -> 5,52:1, also ueber den Spuren und
 * unter dem staerksten Befundmarker.
 *
 * WAS BEWUSST NICHT ANGEFASST IST: die Annotationsmarker behalten ihre
 * `opacity: 0.8`. Dort kodiert die Helligkeit die KATEGORIE und nicht den
 * Rang; ihr Vorrang steckt in der Geometrie und im z-index. MK06 weist nach,
 * dass sie saemtlich ueber 3,0:1 liegen — mehr ist hier nicht zu entscheiden.
 *
 * ---------------------------------------------------------------------------
 * Testfaelle
 * ---------------------------------------------------------------------------
 *   MK01 — Post-Spur (.forensic-minimap-trace) erreicht mindestens 4,5:1.
 *   MK02 — Topic-Spur (.forensic-minimap-topic) erreicht mindestens 4,5:1.
 *   MK03 — An KEINEM der drei umgestellten Marker steht eine `opacity`. Das
 *          ist der eigentliche Waechter: mit Deckkraft waeren MK01, MK02 und
 *          MK05 wertlos, weil sie dann eine Farbe pruefen wuerden, die so nie
 *          auf dem Schirm erscheint.
 *   MK04 — Gegenprobe an den ALTEN Werten: die Fassung vor dieser Aenderung
 *          faellt durch. Ein Test, der auch den Fehlerzustand bestehen laesst,
 *          belegt nichts.
 *   MK05 — Alias-Marker liegt UEBER den Spuren und UNTER dem staerksten
 *          Befundmarker. Geprueft wird die Einordnung, nicht ein Zahlenwert:
 *          ein fester Sollwert waere still falsch, sobald eine Spur- oder
 *          Kategoriefarbe wechselt.
 *   MK06 — Alle Kategoriefarben der Annotationsmarker halten WIRKSAM (mit
 *          opacity 0.8) die 3,0:1. Regressionsschutz fuer den Teil, der
 *          bewusst unberuehrt blieb.
 *   MK07 — Die Spuren ueberstrahlen den staerksten Annotationsmarker nicht,
 *          die Rangfolge bleibt also lesbar. Das ist die Bedingung, unter der
 *          4,5:1 als Zielwert gewaehlt wurde.
 *   MK08 — Eigenpruefung der Rechenfunktion an den Bezugswerten aus WCAG
 *          (Weiss/Schwarz = 21:1, gleiche Farbe = 1:1). Ohne sie waere jede
 *          Zahl oben nur so gut wie eine ungepruefte Hilfsfunktion.
 *
 * Version: 0.1.0 · Build: 700 · 2026-08-12
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";

const CSS = readFileSync("toolbar/toolbar.css", "utf-8");
const JS  = readFileSync("toolbar/toolbar.js", "utf-8");

// ---------------------------------------------------------------------------
// Rechenteil: WCAG 2.1 relative Leuchtdichte und Kontrastverhaeltnis
//
// Bewusst als eigenstaendige, kleine Implementierung ohne Fremdbibliothek —
// die Formeln stehen unveraendert in WCAG 2.1 und aendern sich nicht, und
// eine Abhaengigkeit mehr im Pruefpfad waere hier ein schlechter Tausch.
// MK08 prueft diese Funktionen gegen die in der Norm genannten Eckwerte.
// ---------------------------------------------------------------------------

/** "#RRGGBB" (Gross-/Kleinschreibung egal) -> [r, g, b] als 0..255 */
function hexToRgb(hex) {
  const h = hex.replace("#", "").trim();
  if (!/^[0-9a-fA-F]{6}$/.test(h)) {
    throw new Error("Kein 6-stelliger Hex-Farbwert: " + hex);
  }
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

/** Einzelkanal von sRGB nach linearem Licht (WCAG 2.1, relative luminance) */
function channelToLinear(value255) {
  const c = value255 / 255;
  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** Relative Leuchtdichte L eines Farbwerts (WCAG 2.1) */
function luminance(rgb) {
  const [r, g, b] = rgb.map(channelToLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Kontrastverhaeltnis zweier Farben (WCAG 2.1): (Lhell+0.05)/(Ldunkel+0.05) */
function contrastRatio(rgbA, rgbB) {
  const la = luminance(rgbA);
  const lb = luminance(rgbB);
  const hell  = Math.max(la, lb);
  const dunkel = Math.min(la, lb);
  return (hell + 0.05) / (dunkel + 0.05);
}

/**
 * Deckkraft anwenden: Was sieht man wirklich?
 *
 * DAS IST DER KERN DIESES TESTS. Ein Element mit `opacity: a` ueber einem
 * Grund erscheint als lineare Mischung a*Vordergrund + (1-a)*Grund. Erst
 * DIESE Mischfarbe darf gegen den Grund gemessen werden. Wird der Schritt
 * ausgelassen, misst man eine Farbe, die nie jemand zu Gesicht bekommt —
 * exakt der Fehler, der zu Ticket 602c7557 gefuehrt hat.
 */
function composite(fgRgb, bgRgb, alpha) {
  return fgRgb.map((f, i) => alpha * f + (1 - alpha) * bgRgb[i]);
}

// ---------------------------------------------------------------------------
// Leseteil: Werte aus dem Bestand ziehen, statt sie hier zu wiederholen
// ---------------------------------------------------------------------------

/**
 * Rumpf einer CSS-Regel zu GENAU diesem Selektor liefern.
 * Der Anker `(?![\w-:])` verhindert, dass ".forensic-minimap-trace" auch
 * ".forensic-minimap-trace:hover" einfaengt — sonst wuerde MK03 die
 * Hover-Regel mitpruefen und einen falschen Befund melden.
 */
function ruleBody(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(escaped + "(?![\\w-:])\\s*\\{([^}]*)\\}");
  const m = CSS.match(re);
  if (!m) throw new Error("CSS-Regel nicht gefunden: " + selector);
  return m[1];
}

/** Wert einer Eigenschaft aus einem Regelrumpf, oder null wenn nicht gesetzt */
function declaration(body, prop) {
  const m = body.match(new RegExp("(?:^|;)\\s*" + prop + "\\s*:\\s*([^;]+)"));
  return m ? m[1].trim() : null;
}

/** Wert einer `var NAME = "#RRGGBB";`-Konstante aus toolbar.js */
function jsConst(name) {
  const m = JS.match(new RegExp("var\\s+" + name + "\\s*=\\s*\"(#[0-9a-fA-F]{6})\""));
  if (!m) throw new Error("Konstante nicht in toolbar.js gefunden: " + name);
  return m[1];
}

// --- Die tatsaechlich im Einsatz befindlichen Werte -------------------------

const GRUND_HEX = declaration(ruleBody("#forensic-minimap"), "background");
const GRUND     = hexToRgb(GRUND_HEX);

const SPUR_POST_HEX  = jsConst("TRACE_COLOR_POST");
const SPUR_TOPIC_HEX = jsConst("TRACE_COLOR_TOPIC");

// Zielwert aus der Entscheidung vom 12.08.2026; 3,0:1 ist das Minimum nach
// WCAG 1.4.11 fuer grafische Objekte und gilt fuer alle uebrigen Marker.
const ZIEL_SPUR = 4.5;
const MINIMUM   = 3.0;

// Kategoriefarben der Annotationsmarker — aus der CATEGORIES-Liste in
// toolbar.js gelesen, damit eine neue Kategorie hier automatisch mitgeprueft
// wird und nicht still am Kontrastnachweis vorbeilaeuft (Grundregel 1).
function kategorieFarben() {
  const block = JS.match(/CATEGORIES:\s*\[([\s\S]*?)\n\s*\],/);
  if (!block) throw new Error("CATEGORIES-Block nicht in toolbar.js gefunden");
  const treffer = [...block[1].matchAll(/id:\s*"([^"]+)"[\s\S]*?color:\s*"(#[0-9a-fA-F]{6})"/g)];
  if (treffer.length === 0) throw new Error("Keine Kategoriefarben gelesen");
  return treffer.map((t) => ({ id: t[1], color: t[2] }));
}

/**
 * Wirksamer Kontrast des HELLSTEN Annotationsmarkers.
 *
 * Er ist die Obergrenze, gegen die Spur und Alias geprueft werden: Marken des
 * Ermittlers sind Befunde und duerfen von nichts uebertroffen werden. Der Wert
 * wird berechnet und nicht als Konstante gefuehrt, damit eine neue oder
 * geaenderte Kategoriefarbe die Grenze automatisch mitnimmt.
 */
function staerksterBefundmarker() {
  const alpha = parseFloat(declaration(ruleBody(".forensic-minimap-bar"), "opacity"));
  return Math.max(
    ...kategorieFarben().map(({ color }) =>
      contrastRatio(composite(hexToRgb(color), GRUND, alpha), GRUND)
    )
  );
}

describe("Minimap · Kontrast der Spurmarker (Ticket 602c7557)", () => {
  it("MK01 — Post-Spur erreicht den Zielwert 4,5:1 gegen den Minimap-Grund", () => {
    const wert = contrastRatio(hexToRgb(SPUR_POST_HEX), GRUND);
    expect(
      wert,
      `Post-Spur ${SPUR_POST_HEX} gegen ${GRUND_HEX} ergibt ${wert.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(ZIEL_SPUR);
  });

  it("MK02 — Topic-Spur erreicht den Zielwert 4,5:1 gegen den Minimap-Grund", () => {
    const wert = contrastRatio(hexToRgb(SPUR_TOPIC_HEX), GRUND);
    expect(
      wert,
      `Topic-Spur ${SPUR_TOPIC_HEX} gegen ${GRUND_HEX} ergibt ${wert.toFixed(2)}:1`
    ).toBeGreaterThanOrEqual(ZIEL_SPUR);
  });

  it("MK03 — an den umgestellten Markern steht keine `opacity` (sonst waeren MK01/MK02/MK05 wertlos)", () => {
    for (const sel of [
      ".forensic-minimap-trace",
      ".forensic-minimap-topic",
      ".forensic-minimap-alias",
    ]) {
      const gesetzt = declaration(ruleBody(sel), "opacity");
      expect(
        gesetzt,
        `${sel} traegt wieder eine opacity (${gesetzt}). Damit ist die ` +
        `hinterlegte Farbe nicht mehr die sichtbare Farbe und der gepruefte ` +
        `Kontrast gilt nicht. Siehe Dateikopf toolbar.css.`
      ).toBeNull();
    }
  });

  it("MK04 — Gegenprobe: die Werte VOR der Aenderung fallen durch", () => {
    // Sollfarben und Deckkraft des Zustands, den Alex gemeldet hat.
    const altPost  = hexToRgb("#3a5a8a");
    const altTopic = hexToRgb("#3a7a4a");
    const altAlpha = 0.55;

    // Roh betrachtet — so wurde in Build 649 gerechnet.
    expect(contrastRatio(altPost, GRUND)).toBeLessThan(MINIMUM);

    // Wirksam, also mit Deckkraft — der Wert, den das Auge bekam.
    const wirksamPost  = contrastRatio(composite(altPost, GRUND, altAlpha), GRUND);
    const wirksamTopic = contrastRatio(composite(altTopic, GRUND, altAlpha), GRUND);
    expect(wirksamPost).toBeLessThan(2.0);
    expect(wirksamTopic).toBeLessThan(2.0);

    // Und die Deckkraft war der groessere Anteil des Schadens: sie hat den
    // Wert staerker gedrueckt, als die Farbwahl allein es tat.
    expect(wirksamPost).toBeLessThan(contrastRatio(altPost, GRUND));

    // Der Alias-Marker: die alte Sollfarbe lag bei 7,43:1 und haette ohne
    // Deckkraft die Rangfolge gesprengt, die wirksame Fassung lag mit 3,78:1
    // UNTER den neuen Spuren. Beide Zustaende waren falsch, in entgegen-
    // gesetzte Richtungen — das ist der Grund, warum die Farbe hier
    // abgesenkt und nicht bloss die Deckkraft entfernt wurde.
    const altAlias = hexToRgb("#c8a000");
    expect(contrastRatio(altAlias, GRUND)).toBeGreaterThan(7.0);
    expect(contrastRatio(composite(altAlias, GRUND, 0.65), GRUND))
      .toBeLessThan(contrastRatio(hexToRgb(SPUR_POST_HEX), GRUND));
  });

  it("MK05 — Alias-Marker liegt ueber den Spuren und unter dem staerksten Befundmarker", () => {
    // Geprueft wird die EINORDNUNG, nicht ein fester Zahlenwert: ein Sollwert
    // hier waere still falsch, sobald eine Spur- oder Kategoriefarbe wechselt.
    // Ein Alias ist ein Orientierungspunkt — deutlicher als eine blosse Spur,
    // aber nie so gewichtig wie die Marke eines Ermittlers.
    const alias = contrastRatio(
      hexToRgb(declaration(ruleBody(".forensic-minimap-alias"), "background")), GRUND
    );
    const spurMax = Math.max(
      contrastRatio(hexToRgb(SPUR_POST_HEX), GRUND),
      contrastRatio(hexToRgb(SPUR_TOPIC_HEX), GRUND)
    );

    expect(alias, `Alias ${alias.toFixed(2)}:1`).toBeGreaterThanOrEqual(MINIMUM);
    expect(
      alias,
      `Alias (${alias.toFixed(2)}:1) ist nicht deutlicher als die staerkste ` +
      `Spur (${spurMax.toFixed(2)}:1) — ein Orientierungspunkt, den man ` +
      `schlechter sieht als das, wozwischen er orientieren soll.`
    ).toBeGreaterThan(spurMax);
    expect(
      alias,
      `Alias (${alias.toFixed(2)}:1) ueberstrahlt den staerksten Befundmarker ` +
      `(${staerksterBefundmarker().toFixed(2)}:1) — Orientierung vor Befund.`
    ).toBeLessThan(staerksterBefundmarker());
  });

  it("MK06 — alle Kategoriefarben der Annotationsmarker halten wirksam die 3,0:1", () => {
    const alpha = parseFloat(declaration(ruleBody(".forensic-minimap-bar"), "opacity"));
    const farben = kategorieFarben();
    expect(farben.length).toBeGreaterThanOrEqual(6);
    for (const { id, color } of farben) {
      const wert = contrastRatio(composite(hexToRgb(color), GRUND, alpha), GRUND);
      expect(
        wert,
        `${id} (${color} @ opacity ${alpha}) ergibt nur ${wert.toFixed(2)}:1`
      ).toBeGreaterThanOrEqual(MINIMUM);
    }
  });

  it("MK07 — die Spuren ueberstrahlen die Befundmarker nicht (Rangfolge bleibt lesbar)", () => {
    // Bedingung, unter der 4,5:1 gewaehlt wurde: die Spur darf heller sein als
    // der SCHWAECHSTE Befundmarker — aber nicht heller als der staerkste,
    // sonst kehrt sich der Eindruck "Marke wiegt schwerer als Spur" um.
    // Geprueft wird die Obergrenze.
    const staerksterBefund = staerksterBefundmarker();

    for (const [name, hex] of [["Post-Spur", SPUR_POST_HEX], ["Topic-Spur", SPUR_TOPIC_HEX]]) {
      const spur = contrastRatio(hexToRgb(hex), GRUND);
      expect(
        spur,
        `${name} (${spur.toFixed(2)}:1) ist heller als der staerkste ` +
        `Befundmarker (${staerksterBefund.toFixed(2)}:1) — die Rangfolge kippt.`
      ).toBeLessThan(staerksterBefund);
    }
  });

  it("MK08 — Eigenpruefung der Rechenfunktion an den WCAG-Eckwerten", () => {
    // Weiss gegen Schwarz ist per Definition 21:1, gleiche Farbe ist 1:1.
    expect(contrastRatio([255, 255, 255], [0, 0, 0])).toBeCloseTo(21, 2);
    expect(contrastRatio(GRUND, GRUND)).toBeCloseTo(1, 6);
    // Reihenfolge der Argumente darf das Ergebnis nicht veraendern.
    expect(contrastRatio([255, 255, 255], GRUND)).toBeCloseTo(
      contrastRatio(GRUND, [255, 255, 255]), 9
    );
    // Deckkraft 1 aendert nichts, Deckkraft 0 ergibt den Grund selbst.
    const f = hexToRgb(SPUR_POST_HEX);
    expect(composite(f, GRUND, 1)).toEqual(f);
    expect(composite(f, GRUND, 0)).toEqual(GRUND);
  });
});
