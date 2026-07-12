# Bauplan Build 385 — Wiedervorlage externer Vorgänge (Backend) + Kalender-Leseschicht

**Version:** 0.1 · **Datum:** 2026-07-12 · *(nachgereicht in Build 386)*
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Basis:** 0.7.384 · **mc:** 2026-07-12 · **Migration:** **M010** (coordinator.db, additiv).

---

## 1. Die Architektur-Entscheidung (`mc`)

Die Frage lautete: **ein Speicher für Personalplanung und Wiedervorlage — oder
zwei?**

Die Messung entschied sie. Die Personalplanung ist **nicht geplant, sie
existiert** (M008, Builds 355–360) und ist produktionsnah:

| | **M008 Personalplanung** | **M010 Wiedervorlage** |
|---|---|---|
| Subjekt | `person_id` (Mitarbeiter) | `user_id` (**Fall**) |
| Zeitbegriff | **Intervall** + Wochentagsmuster | **Zeitpunkt** (verschiebbar) |
| Nutzlast | **Menge** (`value_pct`/`value_minutes`) → wird **gerechnet** | **Zustand** → **Zustandsmaschine** |
| Lebensende | Soft-Delete — Planung *darf* korrigiert werden | **unwiderruflich** — forensische Historie |
| Recht | `capacity.edit` | `external.*`, Scope über die **Fall-Zuweisung** |

Ein gemeinsamer Speicher hätte eine Tabelle erzwungen, in der je nach Zeile die
Hälfte der Spalten NULL ist — **plus einen destruktiven Umbau von M008 an
bereits produktiven Daten.** Der Preis ist zu hoch.

Der gemeinsame **Verknüpfungspunkt ist die ZEIT**. Und der gehört in die
**Leseschicht**:

> **Gemeinsame Leseschicht, getrennte Schreibmodelle.**

```
        SCHREIBEN (je eigene Semantik, eigenes Recht, eigener Beleg)
   M008 availability_entry   M010 external_matters   (später: Fristen, Deadlines)
              │                       │                          │
              └────── CalendarSource ─┴──────────────────────────┘
                              │
                         CalendarEntry  (Zeitpunkt = Sonderfall von == bis)
                              │
                    GET /api/calendar?von=&bis=
                              │
              ┌───────────────┴────────────────┐
        Monats-/Listensicht (386)        Gantt (Welle 2)
```

---

## 2. Statusmodell

Verbindlich in **`documents/Wiedervorlage_Statusmodell.md`**, Quelle der Wahrheit:
`management/external/matter_status.py`.

```
                    ┌──── Wiedervorlage verschoben (neues Datum + GRUND) ────┐
                    ▼                                                        │
   [anlegen] ──► offen ──(Antwort eingegangen)──► beantwortet ──(ausgewertet)──► erledigt ✔
                    │                                  │
                    └──────(ohne Ergebnis)─────────────┴─────────────────────────► erfolglos ✔
```

**`offen → erledigt` gibt es bewusst nicht.** `erledigt` heißt „Antwort **da**
und ausgewertet". Wer ohne eingegangene Antwort schließt, schließt **ohne
Ergebnis** — das ist `erfolglos`. Das ist keine Formalie: es ist der Unterschied
zwischen einer **beantworteten** und einer **unbeantworteten** Ermittlungsfrage,
und er muss im Bericht stehen.

`erledigt`/`erfolglos` sind **unwiderruflich** — kein `reopen()`, kein
`delete()`. Ein Irrtum wird durch einen **neuen Vorgang** korrigiert.

---

## 3. Ampel

| | Bedingung (nur offene Zustände) |
|---|---|
| 🔴 | `wiedervorlage_am ≤ Stichtag` |
| 🟡 | `Stichtag < wiedervorlage_am ≤ Stichtag + vorwarnfrist_tage` |
| 🟢 | später |
| ⚪ | abgeschlossen |

`vorwarnfrist_tage` ist **je Vorgang pflegbar**, Standard **7** (`mc`).
Die Ampel wird **nie gespeichert** — sie ist eine Funktion des Stichtags und
würde sonst über Nacht veralten. Jede Ampel trägt eine **Begründung**.

**Sonderfall „verwaist" (`mc`):** Fall geschlossen (`approved`/`closed`), Vorgang
offen → **immer rot**, unabhängig vom Datum. Es wird **nichts automatisch
geschlossen** (kein stiller Eingriff in Ermittlungsdaten). Ein Mensch entscheidet.

---

## 4. Stichtag

`management/calendar/stichtag.py` — Kalendertag in **`Europe/Berlin`**, nicht UTC.
Sonst kippt eine Wiedervorlage in der Sommerzeit einen Tag **zu früh** auf rot —
und im Winter einen Tag **zu spät**, was schlimmer ist: eine fällige
Wiedervorlage bliebe grün.

Jede Antwort trägt einen sichtbaren **Herkunftsvermerk** („Fälligkeiten berechnet
zum …, Zeitzone …"), damit eine falsche VM-Uhr **einem Menschen auffällt**, statt
still zu wirken. Fehlt `tzdata` (Windows), wird auf die lokale Systemzeit
zurückgefallen — **mit sichtbarer Warnung**, nie stillschweigend.

---

## 5. Umfang (geliefert)

**Migration M010** (`KIND=additive`, idempotent, Inline-Verifikation):
`external_matters` + Indizes `ix_external_due` / `ix_external_case` +
**eingefrorener RBAC-Seed** `external.view` / `external.edit`
(**m005-Prinzip:** literale Werte, **kein Import von `catalog.py`** — eine
Migration muss auch in Jahren noch exakt dasselbe tun).

**Schreibmodell:**
- `external/matter_kinds.py` — eingefrorenes Vokabular, **11 Vorgangsarten**
  (inkl. `osint`, `auswertung`)
- `external/matter_status.py` — `MatterStatus`: Übergänge + Ampel (**rein**;
  der Stichtag wird **übergeben**, nie aus der Systemuhr gelesen — sonst hätten
  wir Tests, die je nach Testtag kippen)
- `external/external_matters_repo.py` — **einziger** Schreibpfad, ausschließlich
  über `CoordinatorWriter.audited_write` (Write + Beleg + Zeitstrahl-Spiegel in
  **einer** Transaktion). Ohne Writer **verweigert** das Repo jeden Schreibvorgang.
- `external/external_admin.py` — CLI. `--actor` bei jedem Schreibbefehl Pflicht
  (**ein Beleg ohne Handelnden ist kein Beleg**). **Exit 2** bei roter Ampel,
  umrahmte Warnung auf stderr.

**Leseschicht** `management/calendar/`: `CalendarEntry` · `CalendarSource` (ABC) ·
`ExternalSource` · `AvailabilitySource` · `HolidaySource` · `CalendarRepo` ·
`stichtag`.

**Endpunkte:** `GET /api/external` · `GET /api/calendar?von=&bis=` ·
`POST /api/external/create|defer|answer|close`.

**Tests:** `tests/test_external_matters.py` (EX01–EX12).

---

## 6. Die nicht verhandelbaren Eigenschaften

1. **Verschieben verlangt einen Grund** und bekommt einen **eigenen Belegtyp**
   (`external_matter_deferred`), kein stilles `UPDATE`. **Das Verschieben *ist*
   der Vorgang, um den es hier geht:** wer wie oft verschoben hat, muss im
   Bericht stehen können.
2. **Sensibilitätsregel** (wie `cases.note`): Freitexte (`betreff`, `ergebnis`,
   `grund`) stehen **nicht** im `audit_log` — dort nur **Fakten + Textlängen**.
   Das Audit-Log ist ein **Beleg**, kein Aktenordner.
3. **Jede Kalenderquelle prüft ihre Rechte selbst** — der Aggregator kann die
   Semantik der Quellen nicht beurteilen.
4. **Jede Quelle meldet, wenn sie schweigt** (`hinweise`). Ein Kalender, der
   unvollständig ist, ohne es zu sagen, ist **gefährlicher als gar keiner**: der
   Ermittler schlösse aus der Leere, es stünde nichts an.
5. **Überfälliges erscheint auch außerhalb des Zeitraums** — sonst verschwände es
   beim Blättern in den nächsten Monat. Genau dieses Versäumnis soll das System
   verhindern.
6. **Scope-Auflösung:** `alle` → `None` (alle Fälle); `eigene` → **Liste** der
   zugewiesenen Fälle (ggf. **leer**); kein Recht → 403. Ein Ermittler ohne
   Zuweisung bekommt eine **leere Liste**, **nicht** „alle" — genau diese
   Verwechslung wäre der klassische Kapselungsbruch über einen `None`-Wert.

---

## 7. Rechte

`external.view` und `external.edit`, **beide scope-fähig**. Der **Ermittler**
bekommt `eigene` und pflegt die Vorgänge **seines** Falls selbst — sonst wäre die
Chef-Ermittlerin das Nadelöhr für jede Providerauskunft (`mc`).
**Grants sind operativ** (`rbac_admin`-CLI), default-deny, **nicht** Teil des Builds.

---

## 8. Regression (run_tests.py)

```
pytest : 1030 passed (1018 + 12), 59 skipped, 6 subtests
vitest : 591 passed, 51 Testdateien   (unverändert — Backend-only)
```

---

## 9. Abnahme

1. `python -m management.migrate` → **M010**.
2. `python -m management.rbac.rbac_admin` → **Grants vergeben**
   (`supervisor` → `alle`, `investigator` → `eigene`). **Ohne Grants sieht
   niemand die Vorgänge** (default-deny).
3. `external_admin add … --actor h0a2898` → Vorgang + Beleg; `list` → Ampel +
   Stichtagsvermerk; bei überfälligem Vorgang **Exit 2**.
4. `GET /api/calendar?von=…&bis=…` → Vorgänge + Abwesenheiten + Feiertage in
   **einer** Liste.
5. **Gegenprobe Kapselung:** als Ermittler (`eigene`)
   `/api/external?user_id=<fremder Fall>` → **403**.
6. **Gegenprobe verwaist:** Fall auf `closed` setzen, während ein Vorgang offen
   ist → Ampel **rot** mit Begründung; die Fallakte bleibt unverändert.

---

*Dokument-Ende · Bauplan Build 385 · 2026-07-12*
