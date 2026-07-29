# Bauplan Build 567 — Getrennte Bildlaufflächen (Ticket `fbfc418c`)

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** v0.8.566
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH

---

## 1. Ursache

```css
.aiw-frame { display: flex; min-height: calc(100vh - 84px); }
main.aiw-main { flex: 1; padding: 22px 26px; overflow: auto; }
```

`main` trug **schon immer** ein `overflow: auto` — es lief nur ins Leere. Der
Rahmen hatte nur eine **Mindest**höhe, wuchs also mit dem Inhalt, und gescrollt
hat das **Dokument**. Ein Element ohne begrenzte Höhe kann nicht überlaufen.

Daher beides, was mc gemeldet hat: die gemeinsame Fläche, und die Sicht, die
beim Wechsel „unvollständig" erscheint.

---

## 2. Lösung: Spaltenlayout statt Rechenwert

`body` ist jetzt eine Flex-Spalte über `100vh`; Kopfleiste und
Integritäts-Banner sind feste Glieder, der Rahmen nimmt den Rest.

**Ausdrücklich nicht `height: calc(100vh - 84px)`:** Der Integritäts-Banner
wird ohne `ops.view` ausgeblendet (`.aiw-integrity-hidden`). Die 84 px wären
dann falsch und ließen unten einen leeren Streifen stehen. Die Spaltenaufteilung
rechnet selbst nach.

**`min-height: 0` am Rahmen ist der Kern des Ganzen.** Ohne diese eine Zeile
weigert sich ein Flex-Kind, unter seine Inhaltshöhe zu schrumpfen — die inneren
`overflow`-Regeln griffen nie, und alles bliebe beim alten Verhalten. `SC05`.

---

## 3. Die Sicht beginnt oben

`selectView` ruft `sichtNachOben(mainEl)`. Das ergibt sich **nicht** von selbst:
der Bildlaufstand eines Elements bleibt erhalten, wenn man nur seinen Inhalt
austauscht. Zusätzlich `window.scrollTo(0,0)` für den Fall, dass das Dokument
doch einen Bildlauf hat — sehr schmales Fenster, oder eine ältere `cockpit.css`
im Browser-Cache. `SC01`.

---

## 4. Der Nebenbefund, den die Lösung selbst erzeugt hätte

`buildNav` baut die Leiste bei **jedem** Sichtwechsel neu auf — und eine neu
aufgebaute Leiste steht wieder ganz oben. Wer einen Eintrag weit unten wählt,
sähe seine eigene Auswahl danach nicht mehr: ein neues Ärgernis anstelle des
alten.

`navEintragZeigen` mit `scrollIntoView({ block: 'nearest' })`. **`nearest` ist
der Punkt:** ein bereits sichtbarer Eintrag bleibt stehen, die Leiste zappelt
nicht bei jedem Wechsel. Kennt eine Umgebung die Optionen nicht, wird ohne sie
gesprungen, statt eine Ausnahme mitten im Sichtwechsel zu werfen. `SC02`,
`SC04`.

---

## 5. Der Druck nimmt die feste Höhe zurück

Ohne diese Rücknahme bräche ein Ausdruck des Cockpits nach **einer** Seite ab,
weil der Rest im nicht gedruckten Bildlauf steckt. `html`, `body`,
`.aiw-frame` und `.aiw-main` werden im `@media print`-Block auf `auto` bzw.
`visible` zurückgesetzt. `SC06`.

---

## 6. Abweichung von der CSS-Konvention

Die Builds 561/563/565 haben ihr CSS **ans Dateiende angehängt**, ohne
bestehende Regeln anzufassen. Hier geht es um das **Rahmenlayout der Shell
selbst** (`body`, `.aiw-frame`, `nav.aiw-side`, `@media print`). Zwei einander
widersprechende Regelsätze am Datei-Anfang und -Ende wären schlechter zu
pflegen als eine geänderte Regel mit Begründung im Kommentar. Die Anhänge der
Builds 561/563/565 bleiben unberührt.

---

## 7. Regression

| | 0.8.566 | 0.8.567 |
|---|---|---|
| vitest | 110 Dateien, 1529 passed | **111** Dateien, **1535** passed (+6: SC01–SC06) |
| Python | 2343 / 50 skipped / 45 subtests | **unverändert** (kein Python berührt) |

**Nicht automatisch prüfbar:** ob es sich am Bildschirm richtig anfühlt — JSDOM
rechnet kein Layout. Am lebenden System gegenprüfen: Leiste für sich bewegbar;
Eintrag weit unten wählen → Sicht beginnt oben **und** der gewählte Eintrag
bleibt sichtbar; Probedruck (Strg+P) zeigt weiterhin den Hinweis auf den
Akten-Export statt einer abgeschnittenen Seite.

---
*Dokument-Ende · Bauplan Build 567 · v0.1 · 2026-07-29*
