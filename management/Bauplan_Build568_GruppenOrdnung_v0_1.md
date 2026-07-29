# Bauplan Build 568 — Zweistufige Ordnung und Gruppen (Ticket `ffbfb7f5`)

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** `e15060f` (v0.8.567)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29 (`mc`; Zuschnitt übernommen, `localStorage`, flach bleiben)

---

## 1. Befund, der den Auftrag fast erzwang

Eine Gruppe konnte **zweimal** in der Leiste stehen. Die Vorlieben sind eine
**flache** Liste, `cockpit_viewprefs.js` ließ freies Umsortieren über
Gruppengrenzen zu, und `buildNav` setzt einen Gruppenkopf, sobald sich
`v.group` ändert. Am laufenden Code belegt:

```
Reihenfolge nach Vorliebe: Ueberblick/dashboard -> Verwaltung/assignment -> Ueberblick/calendar
groupSequence           : Ueberblick, Verwaltung          (2 Gruppen)
Gruppenkoepfe in der Nav: Ueberblick | Verwaltung | Ueberblick   (3 Koepfe)
```

`groupSequence` und `buildNav` hatten also **verschiedene Vorstellungen** davon,
was eine Gruppe ist. `GRP01` und `GRP04` halten das jetzt fest.

---

## 2. Keine Schemaänderung

Die zweistufige Ordnung braucht keine Spalte. Es genügt **eine Zusage: jede
Gruppe steht am Stück.** Dann ist die Gruppenfolge die Reihenfolge des ersten
Auftretens und die Sichtfolge die flache Reihenfolge.

`nachGruppenOrdnen` stellt das beim **Lesen** her — damit ist der Doppelkopf
auch für bereits verschränkt gespeicherte Vorlieben behoben, **ohne die Daten
anzufassen**.

Ein `art='gruppe'` in `person_view_pref` hätte den `CHECK` erweitern müssen, in
SQLite also Tabellen-Neuaufbau — auf einer Tabelle, in der seit dem 01.07.
echte Vorlieben liegen. Das steht in keinem Verhältnis zu einer Anzeigefrage.

**Fehlende Gruppen werden angehängt, nicht verworfen** (`GRP03`): eine neue
Sicht mit neuer Gruppe fällt nicht stillschweigend aus der Navigation.
`GRP05` prüft, dass `GROUP_ORDER` heute alle Katalog-Gruppen abdeckt,
`GRP06`, dass kein Eintrag ohne Gruppe existiert.

---

## 3. Neuer Zuschnitt

| Gruppe | Sichten |
|---|---|
| Überblick | 4 |
| Fallsteuerung | 2 |
| Betreuung | 3 |
| Abnahme | 3 |
| Redaktion | 3 |
| Auswertung | 5 |
| Identitäten | 4 |
| Kennzahlen | 6 |
| Personal | 2 |
| Administration | 7 |
| Persönlich | 3 |

„Verwaltung" (vorher 10) entfällt, „Auswertung" schrumpft von 15 auf 5.

Es wurden **nur `group`-Zeichenketten** geändert — keine Sicht-Kennung, keine
Fähigkeit, kein Recht. **Gespeicherte Vorlieben bleiben gültig**, weil sie auf
der Sicht-Kennung stehen und nicht auf der Gruppe.

---

## 4. Zwei Ebenen in „Ansicht anpassen"

- `gruppeVerschieben` bewegt den **ganzen Block**.
- `verschiebeInGruppe` endet am **Gruppenrand**, nicht am Listenrand.

Gespeichert wird weiterhin eine flache Liste — sie entsteht aus beiden Ebenen
und ist dadurch von Haus aus gruppenrein. `GRP10`, `GRP11`, `GRP12`.

---

## 5. Einklappen

Zustand im `localStorage` (mc: „Kosmetik kann in den localStorage"). Er sagt
nichts über die Arbeitsweise aus, nur darüber, was gerade nicht im Weg sein
soll — er gehört nicht in `coordinator.db` und schon gar nicht in den Beleg.
`navGruppeUmschalten` ist als **reine Zustandsrechnung** gebaut und deshalb
prüfbar (`GRP08`).

**Eine eingeklappte Gruppe mit der aktiven Sicht wird aufgeklappt** (`GRP09`).
Sonst wäre die eigene Auswahl unsichtbar, und die Leiste behauptete
stillschweigend, es gebe sie nicht.

---

## 6. Ankerdelta und Regression

`VIEW_CATALOG` unverändert bei **42** Sichten, aber **6 → 11 Gruppen**. Keine
Migration, keine neuen Capabilities (46), keine neuen Ereignistypen.

| | 0.8.567 | 0.8.568 |
|---|---|---|
| vitest | 111 Dateien, 1535 passed | **112** Dateien, **1547** passed (+12: GRP01–GRP12) |
| Python | 2343 / 50 skipped / 45 subtests | **unverändert** — belegt: `git diff HEAD -- '*.py'` ist leer |

**Nicht automatisch prüfbar:** ob die Leiste aufgeräumt **wirkt**. JSDOM rechnet
kein Layout und hat keinen Geschmack. Am lebenden System ansehen: elf Gruppen
statt sechs, Gruppenköpfe klickbar, Zustand übersteht das Neuladen der Seite,
und in „Ansicht anpassen" lassen sich Gruppen als Block und Sichten innerhalb
ihrer Gruppe bewegen.

---
*Dokument-Ende · Bauplan Build 568 · v0.1 · 2026-07-29*
