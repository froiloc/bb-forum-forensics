# Bauplan Build 558 — Kapazitätspflege, Backend

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** `7e4aab1` (v0.8.557)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29 (`mc`)

---

## 1. Anlass

Die Kapazitätsrechnung ist seit Build 355–360 vollständig: Schema (`m008`),
vier auditierte Schreibpfade, Rechner, Sicht. Erreichbar waren die Schreibpfade
aber **ausschließlich über die Kommandozeile** (`management/capacity/capacity_admin.py`).
Die Sicht zeigte Personen ohne Regel-Arbeitszeit folglich als graue Balken
(„keine Basis") — der Mangel war sichtbar, aber im Werkzeug nicht behebbar.

**Gemessener Ausgangsstand (`7e4aab1`):**

| Baustein | Zustand | Fundstelle |
|---|---|---|
| Schema | 4 Tabellen | `m008_capacity.py` |
| Schreibpfade | 6 Methoden über `CoordinatorWriter` | `worktime_repo`, `availability_repo`, `holiday_repo`, `reason_repo` |
| Lesemethoden | 4 | ebenda |
| Ereignistypen | 6, bereits in `ALL` | `event_types.py:82-87, 413-418` |
| HTTP | 1 Route, nur lesend | `management_app.py:874` |

Es fehlten also **Endpunkt und Oberfläche**, nicht die Fachlogik.

---

## 2. Entwurfsentscheidung 1 — kein neues Recht, keine Migration

Zunächst war eine Aufspaltung in `capacity.view` (lesen) und `capacity.edit`
(schreiben) angeboten worden. Nach Messung ist sie **verworfen**:

**Keine Migration im Bestand schreibt jemals einen Grant.** `rbac_grant` kommt
nur in `m006` vor, und zwar als DDL. Sie *könnte* es auch nicht:
`rbac_grant.audit_seq` ist `NOT NULL` mit Fremdschlüssel auf `audit_log` — eine
Migration kann ein Recht nicht **belegt** vergeben. Ein neues Leserecht hätte
also im Katalog gestanden, ohne dass es jemand hat, und die Kapazitätssicht wäre
für alle dunkel gewesen, bis jemand von Hand nachvergibt. Genau die stille
Funktionslücke, die Grundregel 1 verbietet.

**Die Unterscheidung trägt der Scope**, den der Lesepfad seit Build 359 bereits
auswertet (`management_app.py:1995`) und den das Schema kennt (`m006:105`,
`CHECK(scope IN ('alle','eigene'))`):

| Scope | Bedeutung |
|---|---|
| `alle` | Kapazität **beliebiger** Personen setzen — Personalverantwortliche / Leitung |
| `eigene` | ausschließlich die **eigene** Kapazität — Selbstpflege |

Damit ist die Selbstpflege **gebaut, aber nicht vergeben**. Sie bleibt bis zu
einer ausdrücklichen Grant-Entscheidung unerreichbar.

**Der Preis, einmal genannt:** Lesen und Schreiben bleiben dasselbe Recht. Wer
die Kapazitätsauswertung sehen soll, ohne pflegen zu dürfen, braucht später doch
die Trennung. Heute fragt das niemand nach.

---

## 3. Entwurfsentscheidung 2 — anlagenweite Daten sind nicht selbstpflegbar

Feiertage und Abwesenheitsgründe gehören keiner Person, sondern der Anlage. Wer
sie ändert, verschiebt die Rechnung **aller** Personen. Beide verlangen deshalb
hart `scope='alle'`; die Ablehnung nennt den Grund. Geprüft in **KP10**.

---

## 4. Entwurfsentscheidung 3 — kein Selbstschutz-Verbot

Bei `/api/personnel/*` ist die eigene Person über die Oberfläche unantastbar
(`management_app.py:116-118`) — dort schützt das vor dem Aussperren aus dem
eigenen Konto. Eine Arbeitszeit sperrt niemanden aus; ein Verbot hätte nur
verhindert, dass die Leitung ihre eigene Kapazität einträgt. Belegt wird jede
Änderung ohnehin (mc 2026-07-29: „Alles wird dokumentiert und das reicht als
Kontrolle aus").

---

## 5. Klarstellung — `kind` ist keine Gründeliste

Im Gespräch war `kind` als Liste der Abwesenheitsarten („Urlaub", „Krank",
„Schulung", „anderer Dienstauftrag") verstanden worden. Das trifft ein anderes
Feld:

| Feld | Wesen | Erweiterbar? |
|---|---|---|
| `kind` | **Rechenart**, schemagebunden auf `('garantie','einschraenkung')` (`m008:97-98`); trägt die Arithmetik `netto = max(basis − einschränkungen, garantie_boden)` (`capacity_calculator.py:110`) | **nein** — eine Erweiterung änderte die Rechnung |
| `reason_code` → `availability_reason` | **Grundkatalog**, Soft-Delete, Beleg `AVAILABILITY_REASON_ADDED` | **ja, frei** |

Der Wunsch der Leitung, die Liste nach Belieben zu erweitern, ist damit
`POST /api/capacity/reason`. **KP05** prüft, dass ein neu angelegter Grund
sofort in `set_availability` verwendbar ist.

Die Rechenarten gehen als **feste Liste** aus `/api/capacity/stammdaten` an die
Oberfläche, damit dort keine zweite, driftende Kopie entsteht.

---

## 6. Endpunkte

| Methode | Pfad | Nutzlast | Repo-Methode | Beleg | Scope |
|---|---|---|---|---|---|
| GET | `/api/capacity/stammdaten` | `person_id?` | vier `list_*` | — | alle / eigene |
| POST | `/api/capacity/worktime` | `person_id, effective_from, mon_min…sun_min, effective_to?` | `set_worktime` | `WORKTIME_SET` | alle / eigene |
| POST | `/api/capacity/availability` | `person_id, period_start, period_end, kind, value_pct?｜value_minutes?, reason_code?, note?` | `set_availability` | `AVAILABILITY_SET` | alle / eigene |
| POST | `/api/capacity/availability/remove` | `entry_id` | `remove_availability` | `AVAILABILITY_REMOVED` | alle / eigene¹ |
| POST | `/api/capacity/holiday` | `day, label, region?` | `add_holiday` | `HOLIDAY_ADDED` | **nur alle** |
| POST | `/api/capacity/holiday/remove` | `holiday_id` | `remove_holiday` | `HOLIDAY_REMOVED` | **nur alle** |
| POST | `/api/capacity/reason` | `code, label, sort?` | `add_reason` | `AVAILABILITY_REASON_ADDED` | **nur alle** |

¹ **Die Falle:** Die Zielperson steht nicht in der Nutzlast, sondern an der
Zeile. Die `person_id` des Eintrags wird deshalb **vor** der Scope-Prüfung
gelesen — sonst könnte eine selbstpflegende Person fremde Einträge über deren ID
entfernen, obwohl sie sie nie sehen konnte. **KP11** geht genau diesen Weg.

**Sechs Schreibrouten statt einer Sammelroute**, weil es sechs fachlich
verschiedene Handlungen mit sechs verschiedenen Belegarten sind. Eine
Sammelroute müsste die Belegart aus der Nutzlast **raten** — ein falsch
geratener Beleg ist schlimmer als gar keiner. Muster: die vier Alias-Routen
(Build 504) und `/api/qs/draw|review` (Build 541).

**`/api/capacity/stammdaten` ist getrennt von `/api/capacity`**, weil es etwas
anderes ist: dort steht das **Ergebnis** der Rechnung, hier stehen die
**Eingangsdaten**. Eine Sammelroute hätte die Pflegemaske gezwungen, bei jedem
Tastendruck den Rechner laufen zu lassen.

---

## 7. Keine Fachregel im Endpunkt

Minutenschranken, „genau **eines** von `value_pct`/`value_minutes`", aktiver
`reason_code` und Zeitraumfolge bleiben in den Repos. Der Endpunkt prüft Recht,
Scope und Nutzlastform und reicht `CapacityError` als **400 mit Begründung**
durch. So können Oberfläche und Kommandozeile nicht auseinanderlaufen.
Geprüft in **KP07**.

---

## 8. Tests — `tests/test_management_capacity_api.py`

Wirkungsprüfungen, keine Existenzprüfungen: kein Test prüft, *dass* ein Endpunkt
antwortet; jeder prüft, dass die Datenzeile **entsteht** und ein **Beleg mit
gekoppelter `audit_seq`** daneben steht.

| Nr. | Prüfgegenstand |
|---|---|
| KP01 | Arbeitszeit: Zeile + `WORKTIME_SET`, `audit_seq` der Zeile == `seq` des Belegs |
| KP02 | Abwesenheit: Zeile + `AVAILABILITY_SET` |
| KP03 | Entfernen ist **Soft-Delete** — die Zeile bleibt, `deleted_at` gesetzt, `AVAILABILITY_REMOVED` |
| KP04 | Feiertag anlegen/entfernen, beide Belege |
| KP05 | Grund anlegen → Beleg **und** sofortige Verwendbarkeit |
| KP06 | Stammdaten-GET: alle vier Bestände, Zähler, feste Rechenart-Liste |
| KP07 | Fachfehler aus dem Repo → **400 mit Begründung**, nicht 500, nicht stumm |
| KP08 | ohne `capacity.edit` → 403, Antwort **nennt** das fehlende Recht |
| KP09 | `scope='eigene'`: fremde `person_id` → 403; eigene → 200 |
| KP10 | `scope='eigene'` auf Feiertag/Grund → 403 |
| KP11 | `scope='eigene'` entfernt fremden Eintrag über dessen ID → 403, Zeile unberührt |
| KP12 | Arbeitszeit zweimal → **zwei** Zeilen (append-only); Rechner nimmt die jüngere |

**Ein Fehler im Testaufbau, benannt statt stillschweigend behoben:** `_reload()`
ersetzte die Verbindung, nicht aber den `CoordinatorWriter`, der sie als Feld
hält. KP11 brach mit `Cannot operate on a closed database` ab und sah wie ein
Fehler im Prüfling aus. Der Writer wird jetzt mitgezogen; der Grund steht im
Docstring.

---

## 9. Ankerdelta und Regression

**Ankerdelta: keines.** 46 Capabilities, 41 `VIEW_CATALOG`, coordinator-Kette
m001–m037, evidence `[1,2,3]`, keine neuen Ereignistypen, keine Migration.

| | 0.8.557 | 0.8.558 |
|---|---|---|
| Python | 2306 passed / 50 skipped / 45 subtests | **2318** passed / 50 skipped / 45 subtests |
| vitest | 108 Dateien, 1469 / 1 skipped / 1 todo | **unverändert** (kein JS berührt) |

`tests/test_editor_renderer.py` bleibt im Container ausgeklammert (PEP-701,
Python 3.11) — **in der VM muss sie mitlaufen.**

---

## 10. Offen

Die Oberfläche. **Build 559** setzt die Pflegemaske auf diese Endpunkte auf.
Zwei Dinge muss sie benennen, sonst wirkt das Verhalten wie ein Fehler:

1. **Append-only bei der Arbeitszeit.** Eine Korrektur legt eine neue datierte
   Zeile an; die alte bleibt stehen, weil sie der Beleg für den Zeitraum ist, in
   dem sie galt. Ohne Hinweis sieht das aus, als sei die Änderung doppelt
   gespeichert worden.
2. **Der Unterschied zwischen Rechenart und Grund** (§5). „Urlaub" ist ein
   Grund, keine Rechenart — die Maske muss beides getrennt anbieten.

---
*Dokument-Ende · Bauplan Build 558 · v0.1 · 2026-07-29*
