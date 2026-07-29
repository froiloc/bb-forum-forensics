# Bauplan Build 562 — Entfernte Zeilen sichtbar machen (Backend)

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** `f91d23d` (v0.8.561)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29

---

## 1. Das eigentliche Problem war nicht der fehlende Schalter

„Entfernen" ist in der Kapazität ein **Soft-Delete**: die Zeile bleibt in der
Datenbank und trägt `deleted_at`. Sichtbar war sie danach **nirgends** mehr —
und die Oberfläche hatte keine Möglichkeit zu wissen, dass überhaupt etwas
ausgeblendet ist. Das ist eine stille Auslassung, und genau die verbietet
Grundregel 1.

---

## 2. Zwei Dinge, die zusammengehören

| | Wirkung |
|---|---|
| `?include_deleted=1` | liefert entfernte Zeilen **mit** aus |
| `entfernt: {worktimes, availability, holidays, reasons}` | steht **immer** in der Antwort, auch ohne den Schalter |

Nur der Schalter allein wäre ein Schalter, den niemand betätigt — weil niemand
ahnt, dass es etwas einzublenden gibt. **KP22** prüft genau diese Kombination:
ohne Schalter fehlt die Zeile in der Liste, ihre **Zahl** steht aber trotzdem
da.

---

## 3. Einmal lesen, dann teilen

Es wird stets mit `include_deleted=True` gelesen und danach gezählt bzw.
gefiltert. Eine zweite Abfrage nur zum Zählen könnte ein anderes Ergebnis
liefern als die erste — und wäre teurer.

---

## 4. Der Schalter ist eine Anzeigefrage, keine Rechtefrage

Er ersetzt kein Recht und weicht den Scope nicht auf: ohne `capacity.edit`
bleibt es bei 403, und mit `scope='eigene'` zählt und zeigt er ausschließlich
eigene Zeilen. **KP25** prüft beides — auch, dass eine **fremde** entfernte
Zeile nicht in die Zählung gerät.

---

## 5. Alle vier Bestände

Nicht nur die Arbeitszeiten: Abwesenheiten, Feiertage und Gründe kennen
denselben Soft-Delete und dieselbe Auslassung. Alle vier Repos konnten
`include_deleted` bereits (seit Build 356/357) — es fehlte nur der Durchgriff.
**KP24**.

Entfernte Zeilen sind **als solche erkennbar**: `deleted_at` wird
mitgeliefert, sonst sähen sie in der Liste aus wie gültige Regeln. Die
Namensauflösung aus Build 559 greift auch für sie. **KP23**.

---

## 6. Ankerdelta und Regression

Keine Migration, keine neuen Capabilities (46), keine neuen Ereignistypen,
`VIEW_CATALOG` unverändert (42).

| | 0.8.561 | 0.8.562 |
|---|---|---|
| Python | 2327 / 50 skipped / 45 subtests | **2331** (+4: KP22–KP25) |
| vitest | 110 Dateien, 1520 passed | **unverändert** (kein JS berührt) |

---

## 7. Offen

**Build 563** (Frontend) bringt die Umschaltung und die Anzeige der
ausgeblendeten Zahl in die Pflegesicht. Getrennt gehalten nach Festlegung 363.

---
*Dokument-Ende · Bauplan Build 562 · v0.1 · 2026-07-29*
