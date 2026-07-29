# Bauplan Build 559 — Kapazitätspflege, Oberfläche

**Version:** 0.1 · **Datum:** 2026-07-29 · **Baubasis:** v0.8.558
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc, 2026-07-29 (`mc`, Variante (b) und Beschriftung bestätigt)

---

## 1. Entscheidung: eigene Sicht

`capacity_pflege` ist eine **eigene Sicht** neben der Auswertung `capacity`,
nicht ein Anbau an sie. Begründung: das Projekt hat diese Trennung bereits
getroffen — `policy` zeigt die RBAC-Matrix **nur lesend**, `personnel` ist die
zugehörige Pflegefläche. Dieselbe Zweiteilung an anderer Stelle anders zu lösen
wäre genau die Uneinheitlichkeit, gegen die das Tabellen-Arbeitspaket fünfzehn
Sichten umgebaut hat. Nebeneffekt: das ECharts-Diagramm wird nicht bei jedem
Speichern neu gezeichnet.

**Gruppe „Verwaltung"**, neben der Personalverwaltung — dort sucht eine
personalverantwortliche Person, nicht unter „Auswertung" (mc).

---

## 2. Aufbau

Vier Bestände aus `GET /api/capacity/stammdaten`, jeder als Tabelle über
`tabelleAufbauen()` mit Kopffiltern, Trefferzahl, Zurücksetzen und Hilfe-Ankern:

| Kennung | Inhalt | Schreibweg |
|---|---|---|
| `capacity_worktime` | Regel-Arbeitszeiten | `POST /api/capacity/worktime` |
| `capacity_availability` | Abwesenheiten und Garantien | `…/availability`, `…/availability/remove` |
| `capacity_holiday` | Feiertage | `…/holiday`, `…/holiday/remove` |
| `capacity_reason` | Gründekatalog | `…/reason` |

Alle vier erfüllen §2.2 des UX-Bauplans (variable Zeilenzahl, Reihenfolge ohne
Aussage) — **keine Ausnahme**. Vier Registereinträge mit `index: 0…3` nach dem
Muster `policy (Grants)` / `policy (Zuweisungen)`; die Konformitätssuite wächst
dadurch von 104 auf 128 Prüfungen.

---

## 3. Was die Maske ausdrücklich sagt

**Append-only.** Eine Korrektur der Arbeitszeit legt eine **neue** datierte Zeile
an; die bisherige bleibt stehen, weil sie der Beleg für ihren Zeitraum ist. Ohne
Hinweis sieht das nach Doppelspeicherung aus — und jemand versucht, „die alte" zu
löschen, was nicht geht und nicht gehen darf.

**Rechenart ist nicht Grund.** `garantie`/`einschraenkung` ist schemagebunden
(`m008:97-98`) und trägt die Arithmetik `netto = max(basis − einschränkungen,
garantie_boden)`. „Urlaub", „Krank", „Schulung" sind der frei erweiterbare
Katalog. Getrennte Felder — und **die Rechenart-Liste kommt vom Server**
(`data.kinds`). Eine im Frontend nachgebaute Kopie wäre die zweite Wahrheit, die
eines Tages von der ersten abweicht. Geprüft in CP04.

**Scope wird sichtbar gemacht, nicht nur durchgesetzt.** Bei `scope='eigene'`
entfällt die Personenauswahl, Feiertage und Gründe erscheinen **nur lesend** —
mit Begründung im Text, statt dass Knöpfe wortlos fehlen. Ganz verstecken wäre
falsch: ohne den Gründekatalog stünde in den eigenen Abwesenheitszeilen ein
nackter Code. CP05/CP06.

---

## 4. Nachtrag zu Build 558 — eine Lücke, die ich selbst hinterlassen habe

`/api/capacity/stammdaten` lieferte `person_id` **ohne Namen**. Eine Pflegemaske,
die „#7" statt „Müller" anzeigt, ist für eine Leitung mit zwanzig Personen
unbrauchbar. Ein zweiter Abruf über `/api/personnel` wäre der falsche Weg: er
verlangt `personnel.view`, das eine Person mit `capacity.edit` nicht haben muss.
Die Auflösung gehört an diese Stelle.

Die Antwort trägt jetzt `display_name`/`system_username` je Zeile und eine
`persons`-Liste für die Auswahlfelder. **Eine Zeile ohne zugehörige Person
verschwindet nicht**, sondern steht als `unbekannt (#id)` — eine Arbeitszeit ohne
Personendatensatz ist ein Befund, kein Darstellungsproblem (Grundregel 1).
Geprüft in KP14; KP13 prüft die Personenliste unter `scope='eigene'`.

---

## 5. Befund — ein latenter Regex-Defekt an zwei Stellen

`tests/test_management_viewprefs.py:208` und `tests/test_view_export_api.py:307`
lasen den `VIEW_CATALOG` mit `r"\{\s*id:\s*'([a-z]+)'"`. Eine Sicht-Kennung
**mit Unterstrich** wird davon **gar nicht gefunden**. Bis Build 558 trug keine
Kennung einen Unterstrich — der Fehler war latent; `capacity_pflege` ist die
erste.

Die Wirkung wäre an beiden Stellen **gegensätzlich** gewesen:

| Stelle | Wirkung |
|---|---|
| `test_management_viewprefs.py` (VP01) | Prüfung bleibt **grün**, während die neue Sicht weder steuerbar noch ausdrücklich ausgenommen ist — eine **stille Lücke** |
| `test_view_export_api.py` (VE08) | **Fehlalarm**: „Export-Katalog nennt Sichten, die es nicht gibt" |

Das Muster war offenbar kopiert. Beide Stellen sind auf `[a-z_]+` korrigiert und
tragen den Grund im Kommentar. **Nicht behoben, sondern gemeldet:** ob weitere
Stellen im Baum dasselbe Muster tragen, wurde geprüft — es sind genau diese zwei.

---

## 6. Export: eigener Eintrag statt Ausnahme

EX01 und VE08 verlangen für jede neue Sicht eine Entscheidung: exportierbar oder
ausdrücklich ausgenommen. `capacity_pflege` bekommt einen eigenen
`ViewExportSpec` mit vier Abschnitten — **keine Ausnahme**, weil ihr Bestand ein
anderer ist als der von `capacity`: dort steht das **Ergebnis** der Rechnung,
hier stehen die **Eingangsdaten**. Wer später belegen muss, *warum* eine
Kapazität so ausgewiesen war, braucht Regel-Arbeitszeit und Abwesenheit, nicht
nur die Summe.

---

## 7. Abweichung von Festlegung 363, begründet

Festlegung 363 verlangt Backend und Frontend in getrennten Builds. Dieser Build
fasst beides an. Der Grund: der Eintrag in `STEUERBARE_SICHTEN`
(`viewpref_katalog.py`) und der `ViewExportSpec` sind **keine Fachlogik**,
sondern die Gegenstücke des `VIEW_CATALOG`-Eintrags. Ohne sie schlagen VP01 und
VE08 fehl. Ein reiner Frontend-Build wäre ein **wissentlich roter** Build und
verstieße gegen Grundregel 2 („jede Versionsnummer ein lauffähiges, getestetes
System"). **Grundregel 2 geht hier vor.**

Der Namens-Nachtrag aus §4 fällt ebenfalls darunter: eine Maske ohne Namen wäre
zwar lauffähig, aber nicht benutzbar.

---

## 8. Tests

`tests/unit/test_cockpit_capacity_pflege.test.js` — CP01 bis CP10:
Wochensumme mit Lücken, Wert-Darstellung (Prozent **oder** Minuten, `0` ist eine
Angabe), unbekannter Grund wird ausgewiesen, Rechenart aus `data.kinds`,
`scope='eigene'` ohne Formulare **mit** Begründung, Append-only-Hinweis,
Ersatzpfad mit Zeilenzahl je Abschnitt, Nutzlast der Rückrufe (leere Zahlenfelder
werden `null` und **nicht** `0`), XSS an Freitext.

Ergänzt: KP13, KP14 in `tests/test_management_capacity_api.py`.

---

## 9. Ein eigener Fehler beim Bau

Die Sicht griff zunächst auf `window.AIWCockpitTablekit` zu; der Globalname
lautet `AIWTableKit`. Der Fehler fiel **nicht still** aus — der Ersatzpfad
meldete die Zeilenzahl je Abschnitt, genau wie vorgesehen —, aber die
Konformitätssuite schlug mit 20 Fehlschlägen an. Korrigiert; CP08 prüft den
Ersatzpfad seither ausdrücklich.

---

## 10. Ankerdelta und Regression

`VIEW_CATALOG` **41 → 42**. Keine Migration, keine neuen Capabilities (46),
keine neuen Ereignistypen, coordinator-Kette m001–m037, evidence `[1,2,3]`.

| | 0.8.558 | 0.8.559 |
|---|---|---|
| Python | 2318 / 50 skipped / 45 subtests | **2320** (+2: KP13, KP14) |
| vitest | 108 Dateien, 1469 passed | **109** Dateien, **1503** passed (+10 CP, +24 Register) |

---

## 11. Offen

`cockpit.css` kennt die neuen Klassen noch nicht (`aiw-capp-form`,
`aiw-capp-section`, `aiw-btn-klein`, `aiw-label`, `aiw-select`, `aiw-input`). Die
Sicht ist **voll bedienbar, aber ungestaltet**. Das Nachziehen gehört in den
Oberflächen-Zweig, weil `cockpit.css` dort gepflegt wird (mc).

---
*Dokument-Ende · Bauplan Build 559 · v0.1 · 2026-07-29*
