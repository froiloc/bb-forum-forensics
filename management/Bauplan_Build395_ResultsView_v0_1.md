# Bauplan Build 395 — Cockpit-Sicht „Ermittlungsergebnis" (Frontend)

**Version:** 0.1 · **Datum:** 2026-07-12
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis:** 0.7.394 · **mc:** 2026-07-12 · **Migration:** keine.

---

## 1. Abgrenzung

Reiner **Frontend**-Build (Festlegung 363). Backend unverändert — 387 und 393
liefern alles:

```
GET /api/results/coverage   -> Abdeckung JE FALL (auch die NIE bewerteten)
GET /api/results/stats      -> Verteilung je Kriterium + Gesamtzahlen
```

**Recht:** `results.view`. Nav-Gruppe **„Auswertung"**.

---

## 2. Die drei Dinge, die die Sicht leistet

### 2.1 Die blinden Flecken sind die **Hauptaussage**, keine Randnotiz

Die Kopfzeile sagt es in Klartext und — sobald es sie gibt — in **Rot**:

> **„Von 31 Fällen sind 12 noch GAR NICHT bewertet."**

Das ist kein Schmuck. Ein Fall, den niemand angefasst hat, **taucht in
`/api/results/stats` überhaupt nicht auf** (er hat keine Zeile in
`v_investigation_current`). Genau deshalb gibt es `/coverage` — und genau
deshalb steht die Zahl **ganz oben**. Eine Auswertung, die nur über die bereits
bewerteten Fälle spricht, **beantwortet die falsche Frage und sieht dabei
vollständig aus** (Grundregel 1).

In der Tabelle wird die Lücke **benannt**, nicht durch einen Strich versteckt:
`nie_bewertet` → **„ALLE (nie bewertet)"**, rot. Teilbewertet → gelb,
vollständig → grün.

### 2.2 Verteilungen nur **je Kriterium** — nie darüber hinweg

**Ein ECharts-Diagramm pro Kriterium**, zwei Serien (`schwerste` / `beste`).
**Kein Gesamtdiagramm** — und das steht auch so in der Sicht.

Grund: `ordinal` misst bei `abuser_quality` **Schwere/Aktualität**, bei
`location_quality` und `victim_quality` **Präzision** (M011 §D). Ein Diagramm
darüber hinweg addierte Äpfel und Birnen. Die `quality_beschreibung` des Servers
steht **unter dem jeweiligen Diagramm**.

**Die x-Achse kommt aus dem Katalog** (`confidence_items`), **nicht** aus den
vorkommenden Werten. Sonst verschöbe sie sich je nach Datenlage und zwei
Diagramme wären nicht vergleichbar. Fehlende Stufen sind **0**, keine Lücken.

**Ab dem vierten Diagramm eingeklappt** (`mc`) — zehn offene Diagramme machen
die Seite unbedienbar.

> **Fallstrick, den ich abgefangen habe:** ECharts rendert in einem
> geschlossenen `<details>` mit **Größe 0**. Ohne `resize()` beim Aufklappen
> bliebe das Diagramm **leer** — und der Nutzer hielte das für **„keine
> Daten"**. Ein stiller Fehlschluss. Der `toggle`-Handler ruft `resize()`
> (Testbeleg **RS09**).

### 2.3 Die Zahl ohne den Vermerk gibt es nicht

Der `vermerk` steht **fest** unter der Tabelle, **nicht wegklickbar**.

Und: **der Score ist bewusst nicht die Standardsortierung** (`mc`). Sortiert wird
nach **Abdeckung aufsteigend** — die Lücken zuerst. Eine Voreinstellung nach der
provisorischen Kennzahl würde eine **Priorisierung suggerieren, die niemand
abgesegnet hat**. Sortieren *kann* man danach (Spalte ist sortierbar).

---

## 3. Scope `eigene`

Ein Ermittler mit `results.view`/`eigene` sieht die Sicht ebenfalls und bekommt
die **Abdeckung seiner Fälle vollständig**. `/api/results/stats` liefert ihm
**403** (fallübergreifend = `alle`). Das ist **kein Fehler, sondern die
Kapselung** — und die Sicht **sagt es** („Die fallübergreifende Verteilung
erfordert … Geltungsbereich ‚alle'"), statt eine leere Fläche zu zeigen.
Ein Statistik-403 bricht den Aufbau **nicht** ab (Testbeleg **RS10**).

---

## 4. Umfang (geliefert)

| | |
|---|---|
| **NEU** | `management/server/static/cockpit_results.js` (IIFE + UMD, `window.AIWCockpitResults`) |
| geändert | `cockpit.js` — Katalog `{id:'results', cap:'results.view', group:'Auswertung'}`, `loadResultsView()`, Dispatch, SSE; Charts über `state.charts` (bestehende `cleanupView()`-Entsorgung) |
| geändert | `cockpit.html` (**`git add -f`**), `cockpit.css` (scoped `.aiw-res-*`) |
| **NEU** | `tests/unit/test_cockpit_results.test.js` (RS01–RS10) |
| geändert | `tests/unit/test_cockpit_nav.test.js` — Katalog 14 → 15, neu CN03d |

---

## 5. Regression (run_tests.py)

```
pytest : 1121 passed, 59 skipped, 6 subtests   (unverändert — Frontend-only)
vitest : 677 passed (666 + 10 + 1), 56 Testdateien
```

---

## 6. Abnahme

**Management-Server neu starten.** Grants: `results.view` (aus 387).

1. Nav „Auswertung" → **Ermittlungsergebnis**.
2. **Gegenprobe blinde Flecken:** einen Fall anlegen und **nicht** bewerten →
   Kopfzeile wird **rot** und nennt ihn; in der Tabelle steht
   **„ALLE (nie bewertet)"**. Zum Vergleich: in „Statistiken" taucht er **gar
   nicht** auf.
3. Sortierung beim Öffnen: **Abdeckung aufsteigend**, nicht Score.
4. Diagramm 4+ **aufklappen** → es zeichnet sich (nicht leer). Das ist die
   `resize()`-Probe.
5. Unter `abuser`: die Semantik-Warnung („SCHWERE, NICHT Präzision").
6. Als Ermittler (`eigene`): Tabelle mit den eigenen Fällen, **statt** der
   Diagramme ein **Hinweis**, warum die Verteilung fehlt.
7. DEV-Log: `window.AIW_COCKPIT_DEBUG = true`.

---

## 7. Stand Welle 1

Damit ist die **Ergebnisbewertung durchgängig**: Erfassung (390) → Backend
(387/393) → Auswertung (395).

Offen in Welle 1: **Textbaustein-Bibliothek**, **provisorische PDF-Ausgabe**
(ungeprüft).

---

*Dokument-Ende · Bauplan Build 395 · 2026-07-12*
