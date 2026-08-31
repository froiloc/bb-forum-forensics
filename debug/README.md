# `debug/` — Messvorrichtungen und Wegwerfwerkzeuge

## Was hier hineingehört

Alles, was **einmal oder wenige Male** gefahren wird, um eine Frage zu
beantworten: Konsolenskripte für das Ermittlungsfenster, Sonden, Mitschnitte,
Auszüge, kleine Auswertungen.

Kennzeichen einer Datei in diesem Verzeichnis:

* Sie ist **nicht Bestandteil des laufenden Systems**. Der Webserver
  importiert von hier nichts.
* Sie ist **rein lesend**, wo immer das geht — eine Messung, die etwas
  verändert, misst nicht mehr denselben Gegenstand.
* Sie trägt im Kopf: **wozu**, **wann**, **wo**, **wie** ausführen und
  **was zu beobachten** ist. Ohne diese vier Angaben ist ein Messskript für
  jeden außer dem Verfasser wertlos.

## Namensschema der laufenden Messreihe (ab Build 753)

| Datei | misst |
|---|---|
| `messung_xpath_blink_M1.js` | Lösen die gespeicherten XPath-Ausdrücke in Blink auf, und auf welchen Beitrag zeigen sie? |
| `messung_wiederherstellung_M1b.js` | Was liefert die Wiederherstellung wirklich — und wie viele Markierungen werden überhaupt gezeichnet? |
| `messung_seitenumfang_M1c.js` | Wie viele Beiträge trägt die Seite, und welchen Index verlangen die Ausdrücke? |

## Was hier **nicht** hineingehört

* Werkzeuge, die im Betrieb gebraucht werden — die gehören nach `tools/`,
  mit Katalogeintrag, Hilfe und Regressionstest.
* Fallbezogene Daten, Auszüge aus Beweismitteln, Seitenabzüge.

## Für JavaScript-Messskripte gilt zusätzlich

IIFE-Wrapper mit `'use strict'`, ausführliche Kommentare zur Absicht, und die
Ausgabe muss **kopierbar** sein (`copy()` plus `console.log`) — ein Messwert,
den man nicht aus dem Fenster bekommt, ist keiner.
