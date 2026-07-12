# Bauplan Build 387 — Ermittlungsergebnis-Bewertung (Backend)

**Version:** 0.1 · **Datum:** 2026-07-12
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis:** 0.7.386 · **mc:** 2026-07-12 (Punkte 1–8) · **Migration:** **M011** (`coordinator.db`, additiv).

---

## 1. Zweck

Der Ermittlungsstand eines Falls ist **kein einzelner Wert**. „Land, aber
gerichtsfest" ist ein **anderer** Stand als „Meldeanschrift, aber nur Verdacht" —
und **beide begründen andere nächste Maßnahmen**. Genau darum **zwei Achsen** und
nicht eine Zahl:

| Achse | Frage | Skala |
|---|---|---|
| **Konfidenz** | *wie sicher?* | **einheitlich** für alle Kriterien |
| **Qualität** | *wie tief?* | **kriterienspezifisch**, darf fehlen |

Dazu **zwei Extreme** je Kriterium (`mc`):
- **`schwerste`** — die **gravierendste** Erkenntnis
- **`beste`** — die am **besten belegte / präziseste** Erkenntnis

Ein Fall trägt damit höchstens `10 Kriterien × 2 = 20` aktuelle Bewertungen.
**Bewusst keine Personenliste je Fall** — das wäre ein Vielfaches an Pflegeaufwand
ohne Zusatznutzen für die Priorisierung (`mc`).

---

## 2. Die vier tragenden Entscheidungen

### 2.1 Der Katalog ist **Daten**, nicht Code

Bei `EventType`, `matter_kinds` und `EVENT_KINDS` gilt das Gegenteil: dort ist das
Vokabular im **Code eingefroren**, weil ein Belegtyp in zehn Jahren noch exakt
dasselbe bedeuten muss. **Hier ist die Lage anders** (`mc`):

> „Wir stehen noch ganz am Anfang der Ermittlungen und uns fehlt noch die
> Erfahrung, was sich langfristig als sinnvoll erweist."

Skalen und Kriterien sollen **nachträglich anpassbar** und **ergänzbar** sein.
Also: **auditierter Katalog in der Datenbank**. Ein neues Kriterium ist ein
auditierter **Schreibvorgang** (`catalog_admin`), **kein Schema-Eingriff** an
produktiven Ermittlungsdaten.

### 2.2 Die Numerik wird **eingefroren** — der wichtigste Punkt

Jede Bewertungszeile speichert den **Code** *und* den **`ordinal`-Wert zum
Zeitpunkt der Erfassung**, dazu die **Katalogversion**.

**Warum das nicht verhandelbar ist:** Wird eine Skala später umnummeriert (und
genau das ist vorgesehen), würden Bewertungen, die nur den Code speichern, ihre
Bedeutung **rückwirkend ändern**. Zeitreihen kippten dann **still** — ohne Fehler,
ohne Warnung, ohne dass es jemand merkt. **Das wäre der schwerste Fehler, den
dieses Modul machen könnte.**

> Testbeleg: **IR07** („Kernprobe") — Skala wird erweitert, alte Bewertung behält
> `ordinal` **und** `catalog_version`.

### 2.3 Append-only — auf **Datenbankebene**

`investigation_results` kennt kein `UPDATE` und kein `DELETE`. Eine Korrektur ist
eine **neue Zeile**. **Der Verlauf *ist* hier die Ermittlungsleistung:** er zeigt,
wie aus `Verdacht` → `wahrscheinlich` → `gerichtsfest` wurde.

Der Schutz hängt **nicht allein an der Anwendung** — ein Repo kann man umgehen,
einen **Trigger** nicht (gleiche Linie wie `audit_log`, M001).

**Genau eine Ausnahme:** die **Beleg-Kopplung**. `audit_seq` ist `NOT NULL`, die
`seq` ist beim `INSERT` aber noch nicht bekannt. Die Zeile wird mit `audit_seq=0`
eingefügt und im `after_audit`-Hook — **in derselben Transaktion** — auf die echte
`seq` gesetzt. Der Trigger erlaubt **exakt diesen Schritt** (`0 → positiv`, **alle
Fachspalten unverändert**) und **nichts sonst**. Damit kann niemand die Ausnahme
nutzen, um eine Bewertung umzuschreiben oder sie einem fremden Beleg
unterzuschieben.

> Diesen Konflikt hat der Test **IR05** beim Bauen aufgedeckt — der erste
> Trigger-Entwurf blockierte den legitimen Nachtrag mit.

**Auch der Katalog ist append-only:** `deprecate` statt `DELETE`. Ein überholter
Skalenpunkt verschwindet aus den **Auswahllisten**, bleibt aber **lesbar** — sonst
zeigten bestehende Bewertungen ins Leere.

### 2.4 Die Semantik des `ordinal` ist **nicht überall dieselbe**

| Skala | was `ordinal` misst |
|---|---|
| `location_quality`, `victim_quality` | **Präzision** (je höher, desto genauer) |
| **`abuser_quality`** | **Schwere/Aktualität** (fortlaufend > ehemalig > kontaktlos) |

Das ist eine **andere Bedeutung derselben Zahl** (`mc`, ausdrücklich bestätigt).
Sie steht deshalb in `assessment_scale.beschreibung` und **reist mit jeder
API-Antwort mit**. Wer diese Werte über Skalen hinweg addiert, addiert Äpfel und
Birnen. Mittelwerte werden daher **je Kriterium** gebildet, **nie darüber hinweg**.

---

## 3. Seed (M011, eingefroren-literal — m005-Prinzip)

**Konfidenz:** `unbestimmt 0 · kein_anhalt 1 · anhaltspunkt 2 · verdacht 3 · wahrscheinlich 4 · gerichtsfest 5`

| Skala | Punkte (ordinal) |
|---|---|
| `location_quality` | meldeanschrift 4 · ort 3 · region 2 · land 1 · unbestimmt 0 |
| `victim_quality` | name 4 · beziehungsgrad 3 · alter 2 · geschlecht 1 · unbestimmt 0 |
| `abuser_quality` | fortlaufend 3 · ehemalig 2 · kontaktlos 1 · unbestimmt 0 |

**10 Kriterien** (ohne `_confidence`-Suffix — das Kriterium **ist** die Sache, die
Konfidenz ist nur **eine** der beiden Achsen):
`identification` · `location_identification`\* · `victim_identification`\* ·
`abuser`\* · `cp_possession` · `cp_distribution` · `cp_production` ·
`jp_possession` · `jp_distribution` · `jp_production`
\* mit Qualitätsskala; die übrigen **vorerst nur Konfidenz** — ihre Skala kommt
**per CLI nach, ohne Migration** (`catalog_admin set-quality`).

---

## 4. Provisorische Kennzahl

`PriorityScorer` — **flach und ungewichtet**, Gewichte als **Parameter**
(`weights`), nicht fest verdrahtet. Wenn die Gewichtung festgelegt wird, ist das
eine **Konfiguration**, kein Umbau.

Sie liefert **nie eine nackte Zahl**, sondern `{score, beitraege, unbewertet,
abdeckung, vermerk}` — und der **Vermerk** lautet wörtlich:

> *PROVISORISCH — Gewichtung und Struktur dieser Formel sind mit Chef-Ermittlerin
> und Staatsanwaltschaft NICHT abgestimmt. Die Zahl darf keine Maßnahme allein
> begründen.*

Eine Kennzahl ohne diesen Satz wäre eine **unbelegte Behauptung** im Bericht.

**Sie schreibt nicht in `cases.priority`.** Nur `schwerste` geht ein (die
Priorisierung richtet sich nach der **gravierendsten**, nicht der bestbelegten
Erkenntnis). Die **Qualität wird ausgewiesen, aber nicht addiert** (§2.4).
`unbewertet` nennt die **Lücke** — dort ist zu ermitteln.

---

## 5. Rechte

`results.view` / `results.edit`, **beide scope-fähig**. Das Erfassen und Ansehen
der **eigenen** Bewertung (`eigene`) hat eine **andere Qualität** als die
fallübergreifende Auswertung (`mc`): `GET /api/results/stats` verlangt
ausdrücklich Scope **`alle`**. Ein Ermittler mit `eigene` bekommt dort **403** —
**nicht** eine stillschweigend auf ihn zusammengeschrumpfte Statistik, die wie
eine Gesamtauswertung aussähe.

---

## 6. Umfang (geliefert)

| | |
|---|---|
| NEU | `migrations/coordinator/m011_investigation_results.py` |
| NEU | `results/assessment_catalog_repo.py` · `results/results_repo.py` · `results/priority_scorer.py` |
| NEU | `results/results_admin.py` (CLI) · `results/catalog_admin.py` (CLI, **ohne Migration**) |
| geändert | `audit/event_types.py` (+5) · `case_events_repo.py` (+`assessment`) · `rbac/catalog.py` (17 → 19) · `server/management_app.py` |
| NEU | `tests/test_investigation_results.py` (IR01–IR13) |

**Endpunkte:** `GET /api/results/catalog` · `GET /api/results?user_id=` (aktueller
Stand **+ volle Historie** + Kennzahl) · `GET /api/results/stats` (Scope `alle`) ·
`POST /api/results/assess` (append-only).

**Filterbar/suchbar/statistikfähig:** Filter über `code`, Statistik über `ordinal`,
Suche über `note`; Indizes `(user_id, criterion_code, extrem, id)` und
`(criterion_code, confidence_ordinal)`.

---

## 7. Regression (run_tests.py)

```
pytest : 1043 passed (1030 + 13), 59 skipped, 6 subtests
vitest : 605 passed, 52 Testdateien   (unverändert — Backend-only)
```

---

## 8. Abnahme

1. `python -m management.migrate` → **M011**.
2. `python -m management.rbac.rbac_admin` → **Grants**: `supervisor` →
   `results.view`/`results.edit` (**alle**), `investigator` → (**eigene**).
   **Ohne Grants sieht niemand die Bewertung** (default-deny).
3. `results_admin catalog` → 10 Kriterien, 4 Skalen, Katalogversion 1.
4. `results_admin assess --user-id <F> --criterion abuser --extrem schwerste
   --confidence verdacht --quality fortlaufend --actor h002` → Beleg.
5. **Gegenprobe append-only:** dieselbe Bewertung nochmals mit `--confidence
   gerichtsfest` → `current` zeigt den neuen Stand, `history` **beide**.
6. **Gegenprobe Trigger:** direktes `UPDATE investigation_results SET
   confidence_code='…'` in `sqlite3` → **ABORT**.
7. **Kernprobe (§2.2):** `catalog_admin add-item --scale location_quality --code
   hausnummer --ordinal 5 --actor h0a2898` → Katalogversion 2; alte Bewertungen
   behalten `ordinal` **und** `catalog_version=1`.
8. `results_admin score --user-id <F>` → Kennzahl **mit umrahmtem Vermerk** und
   Liste der **noch nicht bewerteten** Kriterien.
9. **Gegenprobe Kapselung:** Ermittler (`eigene`) ruft `/api/results/stats` → **403**.

---

## 9. Nächste Builds

- **388 (Frontend Cockpit):** Auswertung, Filter, Statistik für die Chefin.
- **389 (Frontend Ermittler):** Erfassungsmaske im **Nutzerinfo-Tab** (Baustelle 4).
- Danach aus Welle 1 offen: **Textbaustein-Bibliothek**, **PDF-Ausgabe** (ungeprüft).

---

*Dokument-Ende · Bauplan Build 387 · 2026-07-12*
