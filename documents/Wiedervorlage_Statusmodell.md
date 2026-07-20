# Wiedervorlage externer Vorgänge — Statusmodell

**Verbindlich** · `mc` 2026-07-12 · eingeführt mit Build 385
**Code-Suchbegriff:** `WIEDERVORLAGE-STATUSMODELL` · **Quelle der Wahrheit:**
`management/external/matter_status.py`

---

## 1. Was ist ein externer Vorgang?

Ein Ermittlungsschritt, den die Ermittlung **nicht selbst abschließen kann** und
auf dessen Antwort sie **wartet**: Bestandsdatenauskunft beim Provider, Beschluss
bei StA/Ermittlungsrichter, Rechtshilfeersuchen, Bankauskunft, Amtshilfe,
Gutachten, OSINT-Auftrag, technische Auswertung.

Er blockiert den Fall faktisch — und **er geht verloren, wenn ihn niemand
wiedervorlegt.** Genau das ist der Zweck dieses Systems.

Vorgangsarten (eingefroren, additiv erweiterbar): `management/external/matter_kinds.py`.

---

## 2. Zustände

```
                    ┌──── Wiedervorlage verschoben (neues Datum + GRUND) ────┐
                    ▼                                                        │
   [anlegen] ──► offen ──(Antwort eingegangen)──► beantwortet ──(ausgewertet)──► erledigt  ✔
                    │                                  │
                    └──────(ohne Ergebnis)─────────────┴─────────────────────────► erfolglos ✔
```

| Zustand | Bedeutung |
|---|---|
| `offen` | Antwort steht aus. |
| `beantwortet` | Antwort da, **Auswertung** steht aus. Der Vorgang bleibt in der Wiedervorlage. |
| `erledigt` ✔ | Antwort da **und** ausgewertet. **Endgültig.** |
| `erfolglos` ✔ | Ohne Ergebnis abgeschlossen (keine Antwort, gegenstandslos). **Endgültig.** |

### Warum es `offen → erledigt` **nicht** gibt

`erledigt` heißt „Antwort da **und** ausgewertet". Wer einen Vorgang schließt,
ohne dass eine Antwort einging, schließt ihn **ohne Ergebnis** — das ist
`erfolglos`. Diese Unterscheidung ist keine Formalie: sie ist der Unterschied
zwischen einer **beantworteten** und einer **unbeantworteten** Ermittlungsfrage,
und sie muss im Bericht stehen.

### Endgültigkeit

`erledigt` und `erfolglos` sind **unwiderruflich**. Es gibt kein `reopen()` und
kein `delete()`. Ein Irrtum wird durch einen **neuen Vorgang** korrigiert, nicht
durch Zurückdrehen — die Historie eines Ermittlungsvorgangs wird nicht
umgeschrieben. (Gleiche Linie wie das Berichts-Statusmodell, Build 377.)

---

## 3. Verschieben verlangt einen Grund

Jedes Verschieben der Wiedervorlage (`defer`) ist **pflichtig begründet** und
bekommt einen **eigenen Belegtyp** (`external_matter_deferred`) — kein stilles
`UPDATE`. Das Verschieben *ist* der Vorgang, um den es hier geht: **wer wie oft
verschoben hat, muss im Bericht stehen können.**

Verschieben ist nur in den offenen Zuständen möglich.

---

## 4. Wiedervorlage-Ampel

Berechnet gegen den **Stichtag** (Kalendertag in `Europe/Berlin`, siehe §6).
Nur für **offene** Zustände; abgeschlossene Vorgänge sind `neutral`.

| | Bedingung |
|---|---|
| 🔴 | `wiedervorlage_am ≤ Stichtag` (heute fällig oder überfällig) |
| 🟡 | `Stichtag < wiedervorlage_am ≤ Stichtag + vorwarnfrist_tage` |
| 🟢 | später |

`vorwarnfrist_tage` ist **je Vorgang pflegbar**, Standard **7 Kalendertage**
(eine Bestandsdatenauskunft braucht eine andere Vorwarnzeit als ein
Rechtshilfeersuchen).

Die Ampel wird **nie gespeichert** — sie ist eine Funktion des Stichtags und
würde sonst über Nacht veralten. Jede Ampel trägt eine **Begründung**; eine Ampel
ohne Grund ist im forensischen Kontext wertlos.

### Sonderfall: verwaister Vorgang 🔴

Ist der **Fall** geschlossen (`approved`/`closed`), der Vorgang aber noch offen,
ist das **immer rot** — unabhängig vom Datum. Es wird **nichts automatisch
geschlossen** (kein stiller Eingriff in Ermittlungsdaten). Ein Mensch entscheidet.

---

## 5. Belege

| Ereignis | `audit_log.event_type` | Spiegel in `case_events` |
|---|---|---|
| Anlage | `external_matter_created` | `external_matter` / `action=created` |
| Verschieben | `external_matter_deferred` | `action=deferred` (mit Grund) |
| Antwort | `external_matter_answered` | `action=answered` |
| Abschluss | `external_matter_closed` | `action=closed` |

**Sensibilitätsregel** (wie `cases.note`): Freitexte (`betreff`, `ergebnis`,
`grund`) stehen **nicht** im `audit_log` — dort nur **Fakten + Textlängen**. Der
Text lebt in `external_matters` bzw. im `case_events`-Payload, wo die
RBAC-Kapselung greift. Das Audit-Log ist ein **Beleg**, kein Aktenordner.

---

## 6. Stichtag

Alle Fälligkeiten werden gegen den Kalendertag in **`Europe/Berlin`** gerechnet
(`management/calendar/stichtag.py`), nicht gegen UTC. Jede Antwort trägt einen
sichtbaren **Herkunftsvermerk** („Fälligkeiten berechnet zum 12.07.2026, Zeitzone
Europe/Berlin"), damit eine falsche VM-Uhr einem Menschen auffällt, statt still zu
wirken. Fehlt die Zeitzonendatenbank (Windows ohne `tzdata`), wird auf die lokale
Systemzeit zurückgefallen — **mit sichtbarer Warnung**, nie stillschweigend.

---

## 7. Rechte

| Fähigkeit | Scope `alle` | Scope `eigene` |
|---|---|---|
| `external.view` | alle Fälle | nur zugewiesene Fälle |
| `external.edit` | alle Fälle | nur zugewiesene Fälle |

Der **Ermittler** bekommt `eigene` und pflegt die Vorgänge seines Falls **selbst** —
sonst wäre die Chef-Ermittlerin das Nadelöhr für jede Providerauskunft.
Grants sind eine **operative Entscheidung** (`rbac_admin`-CLI), nicht Teil eines
Builds (default-deny).

---

## 8. Verhältnis zur Personalplanung

Die Kapazitäts-/Abwesenheitsplanung (M008) bleibt ein **eigenes Schreibmodell**:

| | M008 Personalplanung | M010 Wiedervorlage |
|---|---|---|
| Subjekt | `person_id` | `user_id` (Fall) |
| Zeit | **Intervall** | **Zeitpunkt** (verschiebbar) |
| Nutzlast | **Menge** (Minuten/Prozent, wird gerechnet) | **Zustand** (Zustandsmaschine) |
| Ende | Soft-Delete (korrigierbar) | **unwiderruflich** |

Der gemeinsame **Verknüpfungspunkt ist die Zeit** — und der lebt in der
**Leseschicht** `management/calendar/`: `CalendarSource` → `CalendarEntry` →
`CalendarRepo` → `GET /api/calendar`. Neue Zeitquellen (Fristen,
Berichts-Deadlines, Gantt in Welle 2) hängen sich dort an, **ohne** dass ein
bestehendes Schema angefasst wird.

> **Gemeinsame Leseschicht, getrennte Schreibmodelle.**

Jede Quelle prüft ihre Rechte **selbst** und **meldet, wenn sie schweigt**
(Feld `hinweise`). Ein Kalender, der unvollständig ist, ohne es zu sagen, ist
gefährlicher als gar keiner: der Ermittler schlösse aus der Leere, es stünde
nichts an.
