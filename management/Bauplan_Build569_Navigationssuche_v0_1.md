# Bauplan Build 569 — Suchfeld der Navigationsleiste (Ticket `ace2cc2a`)

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** `d73ee49` (v0.8.568a)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29 (gepflegte Stichworte; ausgeblendete Sichten findbar; Stichwortlisten ohne Wartepflicht)

---

## 1. Wogegen gesucht wird

Beschriftung, Gruppe, Kennung und **gepflegte Stichworte** am Katalogeintrag:

```js
{ id: 'capacity_pflege', cap: 'capacity.edit', group: 'Personal',
  label: 'Kapazitaetspflege',
  stichworte: 'arbeitszeit urlaub krank schulung abwesenheit feiertag minuten pflege' }
```

**Korrektur an meiner eigenen Begründung:** Ich hatte gegen einen aus den
Quellen geernteten Index eingewandt, er sei „veraltbar". mc hat zu Recht
widersprochen — die Masken ändern sich **nicht zur Laufzeit**. Das Risiko liegt
in der **Pflege**: Maske geändert, Stichworte vergessen. Genau dagegen steht
die Konformitätsprüfung `NS10`/`NS11`: jede Sicht *muss* nicht-leere, nach der
Faltung brauchbare und untereinander verschiedene Stichworte haben. Eine neue
Sicht kostet einen Eintrag, und das Vergessen fällt sofort auf.

Festlegung mc: *„jeder Maintainer einer Sicht pflegt den Katalogeintrag mit."*

---

## 2. Umlaute in beide Richtungen

Der Katalog mischt die Schreibweisen — `Nächstbeste Aktion` neben
`Fristen (Verjaehrung)`, `Identitäts-Gruppen` neben `Kapazitaet`. Gefaltet wird
deshalb auf **beiden** Seiten: `kapazität` findet `Kapazitaet`, `naechstbeste`
findet `Nächstbeste`. `NS01`.

---

## 3. Verhalten

| | |
|---|---|
| Mehrere Begriffe | **UND** — Eingrenzen macht die Liste kürzer, wie erwartet |
| Teilwort | `kapa` findet beide Kapazitätssichten |
| Reihenfolge | unverändert aus der Voreinstellung, **keine** Trefferwertung |
| Kein Treffer | wird **benannt, mit Zahl** statt leerer Fläche |
| Speicherung | **keine** — ein Filter ist ein Moment, keine Vorliebe |
| Escape | leert das Feld |

---

## 4. Die Rechtegrenze ist die einzige harte Grenze

Der Filter arbeitet ausschließlich auf `navViewsAlle()` — nach Vorliebe
geordnet, nach **Recht** gefiltert, gruppenrein. Der `VIEW_CATALOG` wird nie
direkt gefiltert; sonst verriete das Suchfeld, welche Sichten es gibt, für die
einem das Recht fehlt. `NS08` prüft mit **einem** Recht, dass fremde Begriffe
nichts finden.

**Ausgeblendete Sichten werden gefunden** (Entscheidung mc) — und sind
gekennzeichnet. Ohne Kennzeichen sähen sie aus wie normale Einträge, und die
nächste Frage wäre, warum sie nach dem Leeren des Suchfelds verschwinden.
`NS09`.

**Daraus ergab sich ein Zusatz:** Eine ausgeblendete Sicht, die **gerade aktiv**
ist, steht auch ohne Suche in der Leiste. Sonst zeigte die Navigation eine
Sicht nicht an, die im Hauptfenster offen steht.

---

## 5. Die zentrale Falle — vor dem Bau gemessen

`buildNav` leert das Element, in das es zeichnet (`navEl.textContent = ''`).
Läge das Suchfeld darin, wäre es bei **jedem Tastendruck** neu gebaut — Fokus
und Schreibmarke weg, nach dem ersten Buchstaben Schluss.

Die Leiste hat deshalb zwei Fächer: `.aiw-navsuche` (das `buildNav` **nie**
anfasst) und `.aiw-navliste`. `buildNavSuche` baut das Feld **einmal** und
pflegt es danach nur; der Wert wird nur gesetzt, wenn er abweicht — ein
Zuweisen des gleichen Wertes kann die Schreibmarke ans Ende springen lassen.
`NS12` prüft Elementgleichheit **und** Fokus über einen Neuaufbau hinweg.

**Solange gefiltert wird, ist alles offen.** Ein Treffer in einer zugeklappten
Gruppe wäre eine stille Auslassung. Der gemerkte Klappzustand bleibt unberührt
und gilt wieder, sobald das Feld leer ist. `NS13`.

---

## 6. Ein eigener Testfehler

`NS13` setzte den Klappzustand unter dem **geratenen** Schlüssel `aiw_nav_zu`;
er heißt `aiw.cockpit.navZu.v1`. Der Zustand kam nie an, die Gruppen waren
ohnehin offen — die Prüfung war **vakuum-grün** und bestätigte sich selbst.
Behoben mit dem echten Schlüssel **und einer Gegenprobe**: ohne aktive Suche
müssen die Gruppen nachweislich zu sein. Ohne die Gegenprobe wäre derselbe
Fehler beim nächsten Umbenennen wieder möglich.

---

## 7. Ankerdelta und Regression

`VIEW_CATALOG` unverändert bei **42** Sichten und **11** Gruppen — aber jeder
Eintrag trägt nun `stichworte`. Keine Migration, keine neuen Capabilities (46),
keine neuen Ereignistypen.

| | 0.8.568a | 0.8.569 |
|---|---|---|
| vitest | 112 Dateien, 1547 passed | **113** Dateien, **1562** passed (+15: NS01–NS15) |
| Python | 2343 / 50 skipped / 45 subtests | **unverändert** — belegt: `git diff HEAD -- '*.py'` ist leer |

**Zur Durchsicht:** Die 42 Stichwortlisten sind mein Vokabular. Korrekturen sind
einzeilige Änderungen am Katalogeintrag und brauchen keinen neuen Build.

---
*Dokument-Ende · Bauplan Build 569 · v0.1 · 2026-07-29*
