# Bauplan Build 563 — Entfernte Zeilen in der Pflegesicht (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** v0.8.562
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29

Gegenstück zu Build 562. Getrennt gehalten nach Festlegung 363.

---

## 1. Die Zahl steht auch da, wenn der Schalter aus ist

Im Kopf als Gesamtzahl **und je Abschnitt einzeln**. Eine Gesamtzahl allein
sagt nicht, **wo** etwas fehlt.

Ist nichts entfernt, steht auch **kein** Hinweis — ein Satz über null
ausgeblendete Zeilen wäre Lärm. **CP18**, **CP19**.

**Ein Schalter für alle vier Bestände.** Vier einzelne Schalter wären vier
Orte, an denen man den Überblick verlieren kann.

---

## 2. Eingeblendete entfernte Zeilen werden dreifach gekennzeichnet

| Kennzeichen | Begründung |
|---|---|
| Spalte **„Stand"** | erscheint **nur** im eingeblendeten Zustand — eine Spalte, in der ausnahmslos „aktiv" steht, wäre Ballast |
| gedämpfte, durchgestrichene Zeile | Durchstreichen allein ist bei Zahlenkolonnen schlecht lesbar |
| **keine** Aktionsknöpfe | auch fachlich richtig: ein zweites Entfernen wiese der Server ab, und „Bearbeiten" wollte eine Zeile ersetzen, die nicht mehr gilt |

Der Grund für den Aufwand: **eine stillgelegte Regel, die aussieht wie eine
gültige, ist schlimmer als eine, die gar nicht da ist** — jemand könnte danach
planen. **CP20**.

---

## 3. Die Umschaltung lädt neu, statt im Browser zu filtern

Der Server entscheidet, was sichtbar ist; ein Frontend-Filter könnte Zeilen
zeigen, die Recht oder Scope nicht hergeben.

Der Zustand des Hakens kommt aus der **Antwort** (`data.include_deleted`),
nicht aus dem Frontend — sonst könnte der Haken gesetzt sein, während die Liste
noch die alte Antwort zeigt. **CP21**; serverseitig prüft **KP25**, dass der
Schalter weder Recht noch Scope aushebelt.

---

## 4. Der Formularzustand überlebt auch das Umschalten

Build 561 sinngemäß fortgeführt: wer mitten in einer Eingabe einblendet,
verliert sie nicht.

---

## 5. Ankerdelta und Regression

Keine Migration, keine neuen Capabilities (46), keine neuen Ereignistypen,
`VIEW_CATALOG` unverändert (42).

| | 0.8.562 | 0.8.563 |
|---|---|---|
| vitest | 110 Dateien, 1520 passed | **1524** (+4: CP18–CP21) |
| Python | 2331 / 50 skipped / 45 subtests | **unverändert** — belegt: `git diff HEAD -- '*.py'` zeigt nur die beiden Dateien aus Build 562 |

`cockpit.css`: erneut **Anhang ans Dateiende**, keine bestehende Regel angefasst.

---
*Dokument-Ende · Bauplan Build 563 · v0.1 · 2026-07-29*
