# Bauplan Builds 533–534 — Zuweisung & Fall-Erkennung: gemeinsames Tabellen-Werkzeug

**Baustelle 7 (Management-Cockpit) · Zweig `feature/b7-zuweisung-tabulator` · Basis `ba03943` (v0.8.532)**
Stand: 2026-07-26 · Version v0.1

---

## 1. Anlass — zwei belegte Betriebsbefunde

Beide stammen aus dem Auftrag mc vom 2026-07-26, der einen Vorgang vom
2026-07-25 beschreibt:

**(a) Keine Sortierung, keine Filter.** Die Zuweisungs-Sicht war eine einfache
HTML-Tabelle. Bei 163 Fällen bedeutet das: suchen durch Scrollen.

**(b) Über 80 Einzelzuweisungen — mit Fehlbedienungen.** Wörtlich:

> „Ich habe einen Ermittler, dem ich gestern über 80 Fälle zuweisen musste. Das
> musste ich einzeln machen, und immer wieder baute die Seite neu und anders
> sortiert auf, sodass ich bei einem raschen Klicken häufig und unbeabsichtigt
> das falsche Element umstellte."

Der zweite Befund hat **zwei** Ursachen, und beide liegen im Werkzeug, nicht
beim Anwender:

1. Es gab keinen Sammelweg — nur `POST /api/case/assign` für je einen Fall.
2. `loadAssignment()` lud nach **jeder** Einzeländerung **alles** neu und baute
   die Tabelle neu auf, mit der serverseitigen Sortierung (Ampel → Priorität →
   letzte Aktivität). Eine gerade geänderte Zeile wandert dabei. Der nächste
   rasche Klick traf eine andere Zeile.

Das war eine **von der Oberfläche gebaute Fehlbedienungsfalle**. Sie kann
falsche Zuweisungen erzeugt haben, die niemandem aufgefallen sind — jede davon
trägt einen `audit_log`-Beleg, der sie als gewollte Handlung ausweist.

**Nachtrag mc, gleicher Tag:** Das Erscheinungsbild soll dem der
*Fall-Erkennung* folgen, und die Fall-Erkennung soll ihrerseits alle Spalten
filterbar und die Kennzahl-Spalten wählbar bekommen:

> „Es geht darum, die Masken einheitlicher zu gestalten […] Einmal Erlerntes
> soll immer wieder verwendet werden."

---

## 2. Entwurfsentscheidung: ein gemeinsames Werkzeug statt zweier Nachbauten

Die naheliegende Umsetzung wäre gewesen, die Zuweisung umzubauen und die
Fall-Erkennung nachzuziehen. Das ergäbe zwei Fassungen derselben Regeln
(Filterart je Spalte, Spaltenwahl, Zustandssicherung), die auseinanderlaufen,
sobald eine davon einmal nachgebessert wird — und der Anwender müsste den
Unterschied auswendig lernen.

Stattdessen: **`management/server/static/cockpit_tablekit.js`** — das
gemeinsame Tabellen-Werkzeug. Beide Sichten setzen darauf auf; jede künftige
Listensicht erbt dasselbe Verhalten, ohne es nachzubauen.

| Aufgabe | Wo sie **einmal** steht |
|---|---|
| Filterart je Spalte (Auswahl ↔ Freitext) | `filterFuer`, `spaltenMitFilter` |
| Mehrfachauswahl-Vergleich | `mehrfachFilter` |
| Kennzahl-Spalten aus `uid_stats` | `statZelle`, `statSpalten`, `statFelder` |
| Spaltenwahl (Klappfeld) | `spaltenwahl` |
| „Filter zurücksetzen", Trefferanzeige | `werkzeugleiste`, `filterLoeschen` |
| Sortierung/Filter/Spalten im `localStorage` | `zustandLesen/Schreiben/Anwenden` |
| Gestaltung | `cockpit.css`, Abschnitt „Build 534" |

---

## 3. Die Schwelle 10 wird **aus den Daten** angewandt

Auftrag: „Für Spalten, in denen weniger als 10 einzigartige Einträge
existieren, wie `Priorität`, `Status` möglicherweise auch `Ermittler`, soll es
einen Drop-Down-Filter geben."

Umgesetzt als Konstante `SCHWELLE_AUSWAHL = 10`, angewandt **auf die geladenen
Daten**, nicht je Spalte von Hand gesetzt. Begründung: die Spalte *Ermittler*
hat heute sechs verschiedene Werte und nächstes Jahr vierzehn. Eine
handverdrahtete Entscheidung wäre dann still falsch; diese passt sich an und
ist nachrechenbar (Test TK03 prüft 9 → Auswahl, 10 → Freitext).

**Ausnahme `filter_text`:** Benutzername, Fall-Nummer und Hinweis bleiben
Freitext, auch wenn die Schwelle eine Auswahlliste zuließe — dort sucht man
nach *Teilen*, nicht aus einer Liste.

**Die wichtigste Zeile des Filters** ist `mehrfachFilter`: eine **leere**
Auswahl filtert **nicht**. Die andere Auslegung („nichts ausgewählt = nichts
anzeigen") würde die Liste leeren, sobald jemand das letzte Häkchen entfernt —
das sähe aus wie ein Datenverlust (Test TK04).

---

## 4. Kennzahl-Spalten aus `uid_stats` (Build 533, Backend)

### 4.1 Eigener Endpunkt — Begründung

`uid_stats` liegt **je Fall** in einer eigenen `forensic_<uid>.db`. Bei 163
Fällen sind das 163 Dateiöffnungen. Hinge das an `/api/assignable`, erschiene
die **Kernsicht** (wer bearbeitet was) erst, wenn eine **Nebenquelle**
vollständig gelesen ist.

`GET /api/assignable/stats` ist deshalb getrennt und wird vom Frontend **nach**
der Tabelle geholt. Rechte: dieselben wie `/api/assignable`
(`assignment.edit`, Scope `alle`) — dieselbe Fähigkeit gatet auch die
Fall-Erkennung (`cockpit.js:153`), beide Sichten sind damit abgedeckt.

Parameter:

* `force=1` — Fingerabdruck-Speicher umgehen, alle Dateien neu lesen.
* `subject_ids=18,19,20` — **genau diese** Kennungen, auch solche außerhalb der
  Fallakte (s. 4.3).

### 4.2 Zwei Zahlen, nicht eine

`uid_stats` führt `val_reported` (was das Forum selbst auswies) und
`val_computed` (was der Prepper aus den gesicherten Daten zählte; Beleg
`aiw_sqlite_prepper/stage1/phase_b_exporter.py:3405-3432`, „doppelte
Buchführung"). Angezeigt wird `val_computed` — die Zahl, die aus dem
Beweismittel folgt. Die andere wird **nicht** weggeworfen: eine Abweichung ist
selbst ein Befund (gelöschte Beiträge, unvollständige Sicherung). Sie erscheint
als `*` hinter dem Wert, mit Erklärung im Tooltip.

### 4.3 Zwei eigene Fehler, gefunden und behoben

**(a) Angefragte Kennungen wurden gegen die Fallakte gefiltert.** Der erste
Entwurf setzte `WHERE subject_id IN (…)` gegen `cases`. Wer eine Kennung
anfragte, die (noch) nicht aufgenommen ist, bekam sie **still** nicht zurück —
und das ist der **Regelfall der Fall-Erkennung**: dort stehen die auf der
Platte gefundenen `forensic_<uid>.db`, über deren Aufnahme gerade entschieden
wird. Die Kennzahlen wären ausgerechnet für die Fälle verschwunden, für die man
sie am dringendsten braucht, und zwar lautlos. Eine angefragte Kennung ist eine
**Angabe des Aufrufers**, kein Suchbegriff. Test **US10**.

**(b) `sqlite3.connect()` öffnet die Datei nicht.** Der Fehler
`file is not a database` fällt erst bei der **ersten Abfrage** an. Der erste
Entwurf rief `_table_exists` ungeschützt auf; eine einzige beschädigte
`forensic_<uid>.db` hätte die Kennzahlen **aller** Fälle mit einem HTTP 500
beendet. Gefunden hat es Test **US05**.

### 4.4 Nichts wird still übersprungen

Sechs benannte Befundarten (`BEFUNDE`): `gelesen`, `ohne_kennzahlen`,
`ohne_uid_stats`, `tabelle_unlesbar`, `ohne_forensic_db`, `nicht_lesbar`.
Jeder angefragte Fall bekommt genau eine Zeile — auch der, dessen Datei fehlt.

**Der gefährlichste denkbare Fehler dieses Moduls wäre, eine unlesbare Datei
als „0 Beiträge" darzustellen.** Eine 0 sieht aus wie eine Feststellung und ist
hier das Gegenteil davon. Deshalb liefert ein nicht gelesener Fall ein **leeres**
Wertefeld (keine Nullen), und die Zelle zeigt **`—`** mit dem Befund im
Tooltip. Tests US02, TK06, FE14.

---

## 5. Sammelzuweisung (Build 533, Backend)

`POST /api/case/assign_batch`, Rumpf
`{"changes": [{"subject_id": 18, "person_id": 4, "priority": 2}, …]}`.

| Entscheidung | Begründung |
|---|---|
| **Erst prüfen, dann schreiben** | Alle Angaben werden vollständig geprüft, bevor die Transaktion aufgeht. Ein Rollback nach 79 von 80 Schreibvorgängen ist teuer und verschleiert die Ursache. Alle Beanstandungen kommen **auf einmal** (AB09). |
| **Alles oder nichts** | Eine Transaktion (`audited_write_many`). Ein halb ausgeführter Stapel wäre der schlechteste Zustand: niemand kann danach sagen, welche Zuweisung gewollt und welche ein Rest war (AB04). |
| **Ein Beleg je Fall** | 80 Zuweisungen ⇒ 80 `audit_log`-Einträge. Ein Sammelbeleg wäre kürzer und forensisch wertlos — man könnte einer einzelnen Fallzuweisung keinen Beleg mehr zuordnen (AB01). |
| **Unveränderte Werte: übergangen, aber gemeldet** | Ein Audit-Eintrag für „ist schon so" wäre kein Beleg, sondern Rauschen — und Rauschen in einer Beweiskette ist teuer, weil jede Zeile später erklärt werden muss. Solche Fälle stehen einzeln in der Antwort (AB02). |
| **Obergrenze 1000, Ablehnung statt Kürzung** | Schutz gegen einen entgleisten Rumpf. Eine stille Kürzung wäre genau die Auslassung, die Grundregel 1 verbietet (AB05). |
| **Kein Status im Stapel** | Ein Statuswechsel ist eine Aussage über den Bearbeitungsstand **eines** Falls. Ihn versehentlich über 80 Fälle zu ziehen wäre schwer zurückzunehmen. Nachrüstbar. |

**Keine zweite Fassung der Schreiblogik:** `CasesRepo.assign`/`set_priority`
sind in eine *bauende* (`assign_unit`, `priority_unit` → `WriteUnit`) und eine
*ausführende* Hälfte geteilt. Beide Wege benutzen dieselben `UPDATE`-
Anweisungen und denselben `case_events`-Spiegel. Verhalten der öffentlichen
Methoden unverändert (Regressionsanker **AB08**).

---

## 6. Frontend (Build 534)

### 6.1 Kein optimistisches UI — auch mit Zelleneditor

Ein Zelleneditor zeigt den neuen Wert sofort. Das darf diese Sicht nicht.
Deshalb: nach **jeder** Bearbeitung zuerst `cell.restoreOldValue()`, dann POST;
erst die **bestätigte** Serverantwort setzt den neuen Stand. Wer während des
Schreibens hinsieht, sieht den alten Stand und „Schreibe …" — nie eine
unbelegte Zahl (Test **AZ11**).

### 6.2 Nur die betroffene Zeile wird aktualisiert

Der Kern von Befund (b): `view.bestaetige(subjectId, …)` → `table.updateData`.
Sortierung, Filter, Bildlauf und Auswahl bleiben stehen (Test **AZ12**).

**Nach einem Stapel** wird weiterhin vollständig neu geladen — ein Stapel
verschiebt die Last aller Ermittler und berührt bis zu hunderte Zeilen; dort
ist der frische Serverstand die ehrlichere Darstellung, und der Anwender hat
den Vorgang bewusst abgeschlossen.

**Bei einem abgelehnten Stapel** wird **nicht** neu geladen: der Server hat
nichts geschrieben, die getroffene Auswahl bleibt gültig, und der Anwender kann
sie berichtigen, statt achtzig Häkchen neu zu setzen.

### 6.3 Der Sammelmodus

Umschalter → führende Häkchen-Spalte, im Spaltenkopf **⇄ Auswahl umkehren**,
darüber der **fixierte** Steuerkopf (Ermittler, Priorität, Absenden,
Abbrechen, Zähler). Die Tabelle scrollt in sich (`height: 62vh`).

Vier Entscheidungen, die im Auftrag nicht ausdrücklich standen:

1. **Steuerkopf fixiert** (`position: sticky`) — bei 80 Zeilen soll man zum
   Absenden nicht erst nach oben scrollen. (War ausdrücklicher Wunsch.)
2. **„Auswahl umkehren" wirkt auf die *sichtbaren* Zeilen.** Wer nach
   „Ermittler = leer" filtert und umkehrt, meint die 40 Zeilen vor sich, nicht
   die 163 dahinter. Steht auch im Titel der Schaltfläche (Test AZ10).
3. **Wer eine Zelle bearbeitet, wählt die Zeile damit aus.** Eine Vormerkung an
   einer nicht ausgewählten Zeile fiele beim Absenden lautlos unter den Tisch.
4. **Vormerkungen sind sichtbar anders** (Pfeil, gelber Grund, gestrichelter
   Rahmen, Titel „noch nicht geschrieben"). Sie sind kein optimistisches UI,
   sondern eine Absichtserklärung — und müssen als solche erkennbar sein.

**Ausgewählte Fälle ohne Änderungswunsch** (Kopf auf „nicht ändern", keine
Vormerkung) werden **nicht** mitgeschickt, aber **benannt** — im Zähler und in
der Meldung vor dem Absenden. Wer 80 Fälle auswählt und von dem 3 lautlos
herausfallen, hat einen Beleg verloren, ohne es zu merken (Test AZ07).

### 6.4 Gesicherter Bedienzustand

Schlüssel `aiw.tabelle.<sicht>.v1` im `localStorage`, Inhalt: Sortierung,
Kopffilter, gewählte Kennzahl-Spalten. **Nur Bedienzustand, nie
Ermittlungsdaten.** Ein unlesbarer oder fremdformatiger Stand wird **verworfen**,
nicht repariert. Felder, die es nicht mehr gibt, werden übergangen **und
gemeldet** (Tests TK09, TK10).

Der Zugriff ist gekapselt (`_ls()`): fällt `localStorage` aus (Privat-Modus,
Quota), arbeitet die Sicht ohne Sicherung weiter, statt abzustürzen.

### 6.5 Fall-Erkennung

* **Jede** Spalte filterbar (vorher: nur *Benutzername*). Die eine Spalte mit
  Filter und sieben ohne war die eigentliche Unstimmigkeit.
* Dieselbe Werkzeugleiste, dieselbe Spaltenwahl, dieselbe Zustandssicherung.
* Der Zustands-Schnellfilter **bleibt** — er trägt die Zählung je Zustand und
  ist mit einem Griff bedient. „Filter zurücksetzen" räumt ihn **mit** weg;
  eine Schaltfläche, die einen Filter stehen ließe, wäre eine halbe
  Zusicherung (Test FE15).
* Kennzahlen werden für **alle angezeigten** Kennungen geholt, auch für die
  noch nicht aufgenommenen (Test FE13).

---

## 7. Prüfstand

| Suite | Basis 532 (Container) | Builds 533–534 | Δ |
|---|---|---|---|
| pytest | 1995 / 65 skip / 25 subtests | **2014** / 65 / 25 | +19 |
| vitest | 1191, 99 Dateien | **1216**, 100 Dateien | +25 |

Neue Anker: `US01–US10` (Kennzahlen), `AB01–AB09` (Sammelzuweisung),
`TK01–TK13` (Tabellen-Werkzeug), `AZ01–AZ14` (Zuweisung, davon AZ05/AZ06
angepasst), `FE12–FE15` (Fall-Erkennung).

> **Zur Ankeranpassung AZ05/AZ06:** Die alten Fassungen prüften eine
> HTML-Tabelle mit drei `<select>` je Zeile. Dass sie fehlgeschlagen sind, ist
> die gewollte Wirkung eines Ankers — die Sicht wurde bewusst umgebaut. Die
> Anker der reinen Funktionen (AZ01–AZ04) sind **unverändert** geblieben und
> haben den Umbau überstanden.

**Umgebungsvorbehalt:** Diese Zahlen stammen aus dem Entwicklungscontainer
(Python 3.13). Die VM meldete für Basis 532 `1997 passed / 50 skipped` — die
Abweichung liegt in umgebungsabhängigen Skips, nicht im Ergebnis. Maßgeblich
ist der Lauf in der VM (`python run_tests.py`).

---

## 8. Bewusst **nicht** gebaut (kein stiller Verzicht)

1. **Der Aktenexport der Zuweisung enthält die Kennzahl-Spalten nicht.**
   `view_export_catalog.py` bildet je Sicht **einen** lesenden Endpunkt ab;
   `/api/assignable/stats` ist ein zweiter. Die Sicht zeigt damit mehr, als ihr
   Export enthält. **Das ist zu entscheiden** — die saubere Lösung wäre ein
   `ViewExportSpec` mit mehreren Quellen. Bis dahin gilt der Export als
   unverändert gültig für das, was er abbildet.
2. **Kein Statuswechsel im Stapel** (s. 5).
3. **Kein serverseitiges Sortieren/Filtern.** Bei 163 Fällen ist die
   vollständige Liste im Browser die einfachere und schnellere Lösung. Ab
   einigen Tausend Fällen wäre das neu zu bewerten.
4. **Die Spaltenwahl zeigt technische Bezeichnungen** (`posts_total`) — so
   ausdrücklich gewünscht („Vorerst ist es okay"). Eine Übersetzungstabelle
   wäre nachrüstbar; sie gehörte dann ins gemeinsame Werkzeug.

---

## 9. Geänderte und neue Dateien

**Neu**

* `management/stats/uid_stats_repo.py`
* `management/cases/cases_batch_repo.py`
* `management/server/static/cockpit_tablekit.js`
* `tests/test_uid_stats_repo.py`, `tests/test_assignment_batch.py`
* `tests/unit/test_cockpit_tablekit.test.js`
* `management/Bauplan_Builds533-534_ZuweisungTabulator_v0_1.md` (dieses Dokument)

**Geändert**

* `management/gateway/coordinator_writer.py` (+`WriteUnit`, +`audited_write_many`)
* `management/cases/cases_repo.py` (Aufteilung in `*_unit` + Ausführung)
* `management/server/management_app.py` (zwei Endpunkte)
* `management/server/static/cockpit.js` (`loadAssignment`, `loadCases`, `postJson`)
* `management/server/static/cockpit_assignment.js` (neu aufgebaut)
* `management/server/static/cockpit_cases.js` (Filter, Spaltenwahl, Kennzahlen)
* `management/server/static/cockpit.html` (`cockpit_tablekit.js` **vor** den Sichten)
* `management/server/static/cockpit.css` (Abschnitt „Build 534")
* `tests/unit/test_cockpit_assignment.test.js`, `tests/unit/test_cockpit_cases.test.js`
* `build.json`

**Migrationsvorbehalt ab 01.07.2026: nicht berührt.** Keine Schemaänderung, kein
neuer `EventType`, keine neue Tabelle. Die `forensic_<uid>.db` werden
ausschließlich mit `mode=ro` geöffnet.
