# Bauplan Baustein-Module — Builds 652 ff.

**Fassung:** v0.1 · **Datum:** 2026-08-02 · **Verfasser:** Claude
**Baubasis:** Build 651 / v0.8.651, Commit `85ec890` (`git -C aiw_webserver log --oneline -1`)
**Auftrag:** Alex, Sitzung 2026-08-02 — „Issue-Tracker-Tickets mit Bezug auf Bausteinmodule …
Funktional ist es schon gut, aber das UX gefällt mir noch nicht so richtig."

> **Status: ENTWURF.** §9 enthält drei Entscheidungen, die vor Baubeginn zu treffen sind.
> Ohne diese Entscheidungen ist §5 (Migration) und §6 (Eingabe) nicht baubar.

---

## 0. Zweck dieses Dokuments

Dieser Bauplan zerlegt die offenen Baustein-Modul-Tickets in Bauabschnitte, ordnet jedem
Abschnitt eine Buildnummer, Prüfkennungen und die Pflicht-Nacharbeiten (Hilfe, Tests,
Datenmigrationsleitfaden) zu. Er trennt ausdrücklich **Abschnitte ohne Datenrisiko** von dem
**einen Abschnitt mit Datenrisiko**, damit der Einsatz am 2026-08-03 nicht davon abhängt, dass
die Migration heute noch durchläuft.

---

## 1. Ticketlage — Befund

Gelesen aus `issue-tracker/data/issues.json` (146 Einträge, davon 39 `open`).

### 1.1 Tickets mit Tag `Bausteinmodule`

| Kennung | Status | Prio | Titel |
|---|---|---|---|
| `5d81a0c7` | open | **high** | Schritt 1: `block_type` + `block_data` an `report_modules` (Migration) |
| `8f2b64d9` | open | **high** | Schritt 2: Editor.js als Eingabe im Management + Rohmodus |
| `3d9016fe` | open | medium | Baustein mit anderem Blocktyp als `paragraph` verliert seinen Inhalt |
| `ac36e10b` | open | low | Acht Altbausteine ohne `module_key` nachtragen — **zugewiesen an Alex, nicht an Claude** |
| `a1480978` | resolved | — | bestehende Bausteine nicht vorschaufähig oder änderbar (Build 564/565) |
| `219838e4` | resolved | — | `module_key`-Feld weiterhin gesperrt und leer (Build 575) |

### 1.2 Drei weitere Tickets, die dieselbe Sicht betreffen — BEFUND ZUR TAG-LAGE

Diese drei tragen den Tag `Bausteinmodule` **nicht**, gehören aber sachlich in dieselbe
Sicht „Baustein-Module" bzw. sind ihr unmittelbar nachgelagert. Sie sind, dem Wortlaut des
Auftrags nach zu urteilen („das UX gefällt mir noch nicht"), sehr wahrscheinlich mitgemeint —
zwei von ihnen sind die **einzigen reinen UX-Tickets** dieser Sicht:

| Kennung | Status | Prio | Tags | Titel |
|---|---|---|---|---|
| `3508ad71` | open | **high** | *(keine)* | Editor.js-Vorschau rechts neben Eingabemaske verschieben |
| `d60e893a` | open | **high** | *(keine)* | Listen in Redaktion auf tabulator.js umstellen |
| `4b032177` | open | medium | `Baustein-Modul`, `Platzhalter`, … | Management Baustein-Module Platzhalter analysieren und testen |

`4b032177` trägt `Baustein-Modul` (Bindestrich, Singular) statt `Bausteinmodule`. Eine reine
Tag-Abfrage nach `Bausteinmodule` hätte es übersehen.

**Vorschlag zur Tag-Pflege (Teil des ersten Builds):** `3508ad71`, `d60e893a` und `4b032177`
erhalten zusätzlich den Tag `Bausteinmodule`. Sonst fällt derselbe Fehler beim nächsten Mal
wieder an.

### 1.3 Nachgelagert, nicht in diesem Plan

`b47ce019` (Schritt 3: Editor.js für Dokumentvorlagen) — setzt Schritt 1 und 2 voraus,
ausdrücklich „Nach Schritt 1 und 2" (Claude-Kommentar im Ticket). Bleibt offen.

---

## 2. Risikoklassen

Grundlage: `documents/Datenmigrationsleitfaden_AIW.md:185` führt `templates.db` in der Zeile
*„default / templates"* als **nur-lesend** mit **reduzierter Zeremonie**, ohne
Migrationsvorbehalt; bestätigt in `:338` und `:375` („Nicht betroffen: … `templates.db`").

Das heißt **nicht** „risikofrei". `templates.db` trägt die redaktionelle Arbeit (Bausteine,
Vorlagen, Platzhalter). Verloren gingen dort keine Ermittlerergebnisse, wohl aber
Redaktionsarbeit. Deshalb:

| Klasse | Abschnitte | Datenrisiko | Einsatzfähig am 03.08. auch bei Abbruch? |
|---|---|---|---|
| **A — reines Frontend** | A1, A2, A3 | keines (kein Schreibpfad berührt) | ja, jeder Abschnitt einzeln |
| **B — Schema + Schreibpfad** | B1, B2 | additive Migration auf `templates.db` | nur als Ganzes |

**Baureihenfolge daraus:** A vor B. Klasse A ist bis zum letzten Build einzeln
auslieferbar und rücknehmbar; Klasse B nicht.

---

## 3. Bauabschnitt A1 — Vorschau dauerhaft rechts (Build 652)

**Ticket:** `3508ad71` · **Risiko:** keines · **Berührt keine Datenbank.**

### 3.1 Ist-Zustand (Beleg)

* `management/server/static/cockpit.html:272` — die gesamte Sicht wird zur Laufzeit in
  `<main id="aiw-main">` gerendert; es gibt **keinen** HTML-Abschnitt für Baustein-Module.
* `management/server/static/cockpit_modules.js:558` — `.aiw-mod-body`, zweispaltig
  (`cockpit.css:845`, `display:flex; gap:18px`).
* `cockpit_modules.js:308-352` — `_vorschauAufbauen()` hängt Kopfzeile, Umschalter
  `#aiw-mod-vorschau-schalter` und Host `#aiw-mod-vorschau` **unter** das Formular.
* `cockpit_modules.js:702-706` — Einspeisung entprellt mit 350 ms.
* `cockpit_baustein_vorschau.js:150-225` — `erzeuge(hostEl, opts)` → `{zeige, aus, istOffen}`.

### 3.2 Soll

Dreispaltiges Grundgerüst in `.aiw-mod-body`: Liste | Formular | **Vorschau (dauerhaft)**.
Umbruch nach unten, wenn kein Platz ist — Ticketwortlaut: *„nur an die rechte Seite …, falls
dort auch Platz ist, sonst kommt er nach wie vor unter die Eingabemaske."*

**Umsetzung:** CSS Grid mit `grid-template-columns` und `@media`-Umbruchpunkt, **kein**
JavaScript-Messcode. Begründung: Editor.js misst seinen Behälter beim Aufbau
(`cockpit_modules.js:693-698` ruft `erzeuge()` ausdrücklich erst **nach**
`mainEl.appendChild`); eine JS-gesteuerte Breitenlogik brächte eine zweite Messquelle und
damit eine Fehlerquelle. Bei Spaltenwechsel wird die Instanz **nicht** neu gebaut — der
Editor bleibt stehen, nur seine Spalte wandert.

### 3.3 Der Umschalter

Der Umschalter `#aiw-mod-vorschau-schalter` entfällt laut Ticket. Er bleibt jedoch als
**Zuklapp-Schalter der Spalte** erhalten (nicht als Erzeuger/Zerstörer der Instanz), damit
auf schmalen Anzeigen die Vorschau weggeräumt werden kann. Zustand in `localStorage` unter
dem bestehenden Muster.

> Das ist eine Abweichung vom Ticketwortlaut („Damit entfällt die Notwendigkeit für die
> Schaltfläche"). Sie ist zu bestätigen oder zu verwerfen — siehe §9, Restfragen.

### 3.4 Pflicht-Nacharbeiten

* Hilfe: `management/help/inhalt/redaktion.py:510-520` (Abschnitt `vorschau`) und die Marke
  `modules.bedienung.ansicht` (`:570-577`) umschreiben — die Marke beschreibt heute einen
  Umschalter, den es so nicht mehr gibt.
* Tests: `tests/unit/test_cockpit_modules.test.js` — Fälle **LY01–LY04** (Spaltengerüst
  vorhanden; Vorschau ohne Klick da; Zuklappen behält Instanz; Umbruchpunkt in CSS belegt).

---

## 4. Bauabschnitt A2 — Liste auf Tabulator (Build 653)

**Ticket:** `d60e893a` · **Risiko:** keines.

### 4.1 Ist-Zustand (Beleg)

`cockpit_modules.js:575-602` — `.aiw-mod-list`, je Eintrag ein `<button class="aiw-mod-item">`
mit `data-key` = `module_key` **oder** `#id:<id>` für Zeilen ohne Kennung (`:593-594`).
Auswahl per Klick → `_fillForm` (`:218`), inkl. Nachtragsmodus (`:229-235`).

### 4.2 Soll

Ersetzen durch `window.AIWTableKit.tabelleAufbauen(doc, mainEl, opts)`
(`cockpit_tablekit.js:780`), `sicht: 'modules'`. Damit kommen ohne Eigenbau: Spaltenwahl,
Kopffilter, Zustandssicherung je Sicht (`zustandLesen`/`zustandSchreiben`, `:372`/`:388`),
Hilfe-Anker und die Rückfallmeldung bei fehlender Bibliothek (`:803-817`).

Spalten: Kennung (`module_key`, leer → sichtbare Markierung „ohne Kennung"), Titel, Rolle,
Thema, Sortierung, aktiv. Maximalhöhe + Pagination nach dem Muster der übrigen Sichten
(Vorbild: `cockpit_lectorate.js:356`, `cockpit_cases.js:253`).

### 4.3 Zu beachten

* Der Auswahlweg muss **beide** Adressierungen weiter bedienen: `module_key` und Zeilen-`id`.
  Der Nachtragsmodus (`_state.nachtragId`) hängt daran — er ist die Lehre aus `a1480978`
  („ein neu getippter Schlüssel hätte nichts gefunden und eine ZWEITE Zeile angelegt").
* Die acht Altzeilen ohne `module_key` (Ticket `ac36e10b`) müssen in der Tabelle **auffindbar
  und filterbar** sein — sonst wird die Datenpflege schwerer statt leichter. Vorschlag: eine
  Filterschaltfläche „nur ohne Kennung".
* `einheit: 'Bausteine'` setzen (Vorgabe aus `cockpit_tablekit.js:806-810`: die Zahl steht
  immer mit dem Substantiv der Sicht).

### 4.4 Pflicht-Nacharbeiten

* Hilfe: `redaktion.py` — Marke `modules.bedienung.waehlen` (`:582-585`) neu fassen, Abschnitt
  `aufbau` (`:491-500`) nachziehen, Marken für Filter/Spaltenwahl ergänzen.
* Tests: **TB01–TB05** in `test_cockpit_modules.test.js` (Auswahl über `module_key`; Auswahl
  über Zeilen-`id` ohne Kennung; Nachtragsmodus bleibt erreichbar; Rückfall ohne Tabulator;
  Filter „ohne Kennung" liefert genau die kennungslosen Zeilen).

---

## 5. Bauabschnitt A3 — Platzhalter-Tabelle (Build 654)

**Ticket:** `4b032177` · **Risiko:** keines, solange nur gelesen wird (Stufe 1).

### 5.1 Datenquellen (Beleg)

* Zerlegung des Bausteintexts: `userinfo/placeholder_chips.js:73` `_CHIP_RE`, `parse()` `:117`,
  `extractFields(text, type)` `:266`. Geliefert wird je Chip:
  `{chipType, name, defaultVal, description, b64regex, raw}`.
  Drei Typen: `a`/`auto`, `m`/`mandatory`, `o`/`optional` (`_normalizeType` `:78-86`).
* Katalog der bekannten Platzhalter: `GET /api/templates/placeholders`
  (`management/server/management_app.py:982`, Handler `:3880-3896`, Recht `templates.edit`).
  Spalten aus `management/templates_admin/placeholder_repo.py:36-38`, darunter
  `type, validation, validation_type` (`regex`|`list`|`like`), `validation_ci`,
  `default_value`, `return_type`, `is_active`.
* Die Datei ist im Cockpit bereits geladen: `cockpit.html:200`
  (`/static/shared/placeholder_chips.js`, Positivliste `management_app.py:395-405`).

### 5.2 Soll — Stufe 1 (lesend + prüfend + testend)

Tabelle unter dem Bausteintext, live aus dem Textfeld gespeist (dieselbe 350-ms-Entprellung
wie die Vorschau). Spalten:

| Spalte | Inhalt | Quelle |
|---|---|---|
| Typ | `a` / `m` / `o` | `seg.chipType` |
| Name | Feldname bzw. `query_id` | `seg.name` |
| Vorgabe | `defaultVal` | `seg.defaultVal` |
| Beschreibung | `description` | `seg.description` |
| Prüfmuster | `b64regex`, **dekodiert angezeigt** | `seg.b64regex` |
| Vorkommen | Anzahl im Text | `parse()` |
| **Verifikation** | Ampel + Klartextbefund | siehe §5.3 |
| **Testeingabe** | Eingabefeld, nur bei `m:`/`o:` | siehe §5.4 |

### 5.3 Was „Verifikation" konkret prüft

Jede Prüfung liefert einen **Klartextbefund**, keine bloße Farbe. Kein Befund wird still
übersprungen (Grundregel 1).

1. **Namensform** gegen `[A-Za-z0-9._-]+` (aus `_CHIP_RE`).
2. **Bei `a:`** — existiert `name` als `query_id` im Katalog? Ist er `is_active`? Ist sein
   `type` im Katalog tatsächlich `a`? Ein `a:`-Chip auf einen `m:`-Eintrag ist ein Fehler,
   der heute erst zur Laufzeit auffällt.
3. **Prüfmuster** — ist `b64regex` gültiges Base64? Ergibt es einen kompilierbaren regulären
   Ausdruck? (`new RegExp` in `try`.)
4. **Widerspruch zum Katalog** — trägt derselbe Name im Katalog ein anderes `validation` als
   der Chip im Text? Das ist kein Fehler, aber ein meldepflichtiger Unterschied.
5. **Doppelvergabe** — derselbe Name zweimal mit **unterschiedlicher** Vorgabe/Beschreibung.
6. **Feldüberzahl** — mehr als fünf `|`-Felder im Token, d. h. abgeschnittener Chip.

### 5.4 Was „Testeingabe" konkret tut

Nur für `m:` und `o:`. Eingabe wird sofort geprüft gegen:
* das Prüfmuster aus dem Chip (`b64regex`, dekodiert), **und**
* falls der Name im Katalog steht, zusätzlich gegen `validation`/`validation_type` von dort,
  unter Beachtung von `validation_ci`.

Weichen die beiden Urteile voneinander ab, wird **beides** ausgewiesen. Das ist der Punkt,
an dem die heute unbemerkte Abweichung zwischen Baustein und Katalog sichtbar wird.

### 5.5 Stufe 2 — bidirektional (Build 655, **nur auf Zusage**)

Ticketwunsch: *„Ideal wäre es, wenn diese Tabelle bidirektional wäre."*

Technisch tragfähig, weil `parse()` je Chip das Originaltoken in `seg.raw` mitführt
(`placeholder_chips.js`, Segmentaufbau ab `:117`): Ein geänderter Wert wird zu einem neuen
Token zusammengesetzt und **positionsgenau** gegen `raw` ersetzt.

Drei Fallen, die vorab zu entscheiden sind:
* **Trennzeichen.** `|` und `}` dürfen in keinem Feld vorkommen (`[^|}\n]` im `_CHIP_RE`).
  Eingaben mit diesen Zeichen sind **abzuweisen**, nicht stillschweigend zu entschärfen.
* **Mehrfachvorkommen.** Steht ein Name mehrfach im Text, ändert die Tabellenzeile **alle**
  Vorkommen. Das ist anzuzeigen, bevor es geschieht.
* **Schreibrichtung zur Cursorposition.** Das Zurückschreiben setzt die Einfügemarke im
  Textfeld zurück. Das ist beim Tippen unangenehm — deshalb schreibt Stufe 2 erst bei
  `change` (Feld verlassen), nicht bei `input`.

### 5.6 Pflicht-Nacharbeiten

* Hilfe: neuer Abschnitt in `redaktion.py` `abschnitte` (Anker `platzhaltertabelle`), plus
  Marken je Spalte im Tupel `kontext` (`:555-632`). Abschnitt `arten` (`:501-509`) verweisen.
* Tests: **PT01–PT10** (Zerlegung; alle sechs Verifikationsbefunde je einzeln; Testeingabe
  gegen Chip-Muster; Testeingabe gegen Katalog; Abweichungsmeldung; leerer Text → leere
  Tabelle ohne Fehler). Bei Stufe 2 zusätzlich **PT11–PT14** (Roundtrip zeichengenau;
  abgewiesenes `|`; Mehrfachvorkommen; kein Roundtrip-Verlust bei Sonderzeichen/UTF-8).

---

## 6. Bauabschnitt B1 — Migration `block_type` + `block_data` (Build 656)

**Tickets:** `5d81a0c7` (Hauptaufgabe), `3d9016fe` (mit zu beheben) · **Risiko: Klasse B.**

### 6.1 Ist-Zustand (Beleg)

`templates.db.schema.sql:3-17` — `report_modules(id, title, description, role, topic, body,
sort_order, is_active, created_by, created_at, updated_at, module_key)`. Kein `block_type`,
kein `block_data`.

`templates.db` hat **keinen** Migrations-Runner und keine Versionstabelle; der Stand wird an
Spuren abgelesen — `management/templates_db_status.py:19-27` sagt das ausdrücklich, und
`tools/migrate-dbs.py:87-88` schließt `templates` aus dem Register aus.

Die Vorschau ist vorbereitet: `cockpit_baustein_vorschau.js:72-77` —
`var typ = modul.block_type || 'paragraph';` und `if (modul.block_data && typeof
modul.block_data === 'object') return [{type: typ, data: modul.block_data}];`
**Sie erwartet ein Objekt, keinen JSON-Text.** (Prüfkennung BV03.)

Der Defekt aus `3d9016fe` steht in `userinfo/report_editor.js:4087-4090`:
```js
const blockData = modData.block_type === 'paragraph'
    ? { text: insertText }
    : {};
```

### 6.2 Vorgeschlagenes Schema

```sql
ALTER TABLE report_modules ADD COLUMN block_type TEXT NOT NULL DEFAULT 'paragraph';
ALTER TABLE report_modules ADD COLUMN block_data TEXT;   -- JSON, NULL erlaubt
```

Begründung für zwei ADD COLUMN statt Rebuild: wörtlich das Argument aus
`management/migrate_templates_ci.py:12-17` — *„SQLite führt ALTER TABLE … ADD COLUMN …
DEFAULT nicht-destruktiv aus, ohne die vorhandenen CHECK-Constraints anzutasten. Ein Rebuild
wäre unnötiges Risiko."*

`block_data IS NULL` bedeutet: **Bestandszeile, Inhalt steht in `body`.** Kein Backfill nötig,
keine Zeile wird angefasst, `is_active`/`updated_at` bleiben unberührt. Die Vorschau fällt für
diese Zeilen automatisch auf den `body`-Pfad zurück (`cockpit_baustein_vorschau.js:79-93`) —
das ist genau die geforderte Verlustfreiheit, ohne Datenschreibvorgang.

**Offen:** `CHECK`-Constraint auf `block_type` ja/nein. Siehe §9, Frage 2.

### 6.3 Berührungspunkte — vollständige Liste

Zwingend (jeweils belegt):

1. `templates.db.schema.sql:3-17`
2. `tests/fixtures_templates_schema.sql:1-7`
3. **neu** `management/migrate_templates_blocktyp.py` nach dem Muster
   `migrate_templates_ci.py` — Signatur `apply_migration(con, changed_by=…)` (Pflicht wegen
   `tools/migrate-dbs.py:259-262`), Backup `<db>.pre656.bak`, Audit-Zeile `action='migrate'`,
   `PRAGMA integrity_check`, `--no-backup`, CLI-Epilog `management.help.cli_epilog`
4. `management/templates_db_status.py:62-80` — Eintrag mit Spur
   `("spalte", "report_modules.block_type")`
5. `tools/migrate-dbs.py:146-152` — `TEMPLATES_SCHRITTE`
6. `db/templates_db.py:188-191` (`ERWARTETE_SPALTEN`), `:201-208` (`SPALTEN_MIGRATION`),
   `ModuleRecord` `:50-62`, SELECTs `:376-382`, `:400-406`, `:437-457`, `_row_to_module`
   `:660-671`
7. `management/templates_admin/module_repo.py` — SELECTs `:48-54`, `:56-61`, `:63-73`,
   Feldübernahme `:134-140`, INSERT `:165-171`, beide UPDATEs `:174-186`
8. `management/templates_admin/module_validator.py:68-95` — `block_type` gegen Wertevorrat,
   `block_data` als JSON prüfen
9. `management/server/management_app.py:4180-4189` — `_tpl_module_from_payload`
10. `management/server/static/cockpit_modules.js:155-173` — `buildPayload`
11. `forensic_api/templates_ep.py:189-201` und `:234-242` — Ausgabefelder
12. `userinfo/module_panel.js:440-446`, `:1173`, `:1198-1202` — die fest verdrahteten
    `'paragraph'`
13. `userinfo/report_editor.js:4087-4090` — Ticket `3d9016fe`
14. `documents/Datenmigrationsleitfaden_AIW.md` — neuer Abschnitt am Ende, Versionszeile und
    Änderungshistorie nachziehen
15. Hilfe: `management/help/inhalt/redaktion.py`, `management/help/cli_katalog.py`
    (Eintrag für das neue Migrationswerkzeug, Muster `:2790-2829`)
16. `build.json`, `MD5SUMS_Build656.txt`

**Nicht anzufassen:** `management/gateway/templates_writer.py` — feldagnostisch
(`:76-118`), kennt `report_modules` nicht.

### 6.4 BEFUND: drei Fallen im Bestand

**(a) Fünf parallele DDL-Wahrheiten.** Das `report_modules`-DDL steht an fünf Stellen:
`templates.db.schema.sql:3-17`, `tests/fixtures_templates_schema.sql:1-7`,
`tests/test_templates_module_admin.py:47-53`, `tests/test_templates_writer.py:35-41`,
`tests/test_templates_quelle_zustand.py:266-269`. Einen zentralen Fixture-Lader gibt es
nicht. **Alle fünf sind einzeln nachzuziehen**, sonst prüfen die Tests gegen ein Schema, das
es nicht gibt.

**(b) Zwei Tests brechen planmäßig.** `tests/test_templates_quelle_zustand.py` GS03
(`:293-296`, `fehlende_spalten() == {}`) und GS05 (`:309-325`, `assertEqual(anzahl, 2)`)
kippen, sobald `ERWARTETE_SPALTEN` und `MIGRATIONEN` wachsen. Das ist kein Defekt, sondern
die Sperre, die funktioniert — sie ist mit dem Build nachzuziehen. `tests/test_migrate_dbs_tool.py`
MD05/MD01 ebenso.

**(c) Offener Mangel im Sammelwerkzeug.** Ticket `1bfb124e` (open, major): auf einem Bestand
vor Build 489 bricht `migrate-dbs --apply` ab, weil Schritt 388 die Tabelle `placeholders`
verlangt, die erst 489 anlegt; zusätzlich fängt `templates_anwenden` mit `except Exception`,
während die Migration `SystemExit` (erbt von `BaseException`) wirft. Die Arbeit daran wurde
ausdrücklich abgebrochen, bis Alex die Reihenfolge selbst geprüft hat. **Eine sechste
Migration wird ans Ende dieser Kette gehängt und ist von der Reihenfolgefrage betroffen.**
Auf einem Bestand, der bereits auf 497 steht — der Regelfall in der VM —, ist der Mangel
folgenlos; das ist vor der Ausführung zu belegen, nicht anzunehmen.

### 6.5 Prüfkennungen

**BT01** Migration auf leerer DB legt beide Spalten an, `PRAGMA integrity_check` = `ok`.
**BT02** Migration auf Bestand mit Zeilen: **kein** `body` verändert, **kein** `updated_at`
verändert (Fingerabdruck vorher/nachher, Muster `test_migrate_dbs_tool.py:96-112`).
**BT03** Idempotenz: zweiter Lauf ändert nichts und schreibt keine Audit-Zeile.
**BT04** Backup wird angelegt, `--no-backup` unterdrückt es.
**BT05** Audit-Zeile mit `action='migrate'` vorhanden.
**BT06** `templates_db_status` meldet die Migration vorher als offen, nachher als erledigt.
**BT07** Bestandszeile ohne `block_data` wird von der Vorschau unverändert als
`paragraph` gezeigt (Rückfallpfad, gegen BV03 gemessen).
**BT08** `report_editor.js`: Baustein mit `block_type='table'` behält seinen Inhalt —
**gegen den heutigen Stand gemessen**, d. h. der Fall muss mit der Fassung aus Build 651
umfallen. Ohne diese Gegenprobe ist er keine Sperre, sondern eine Behauptung.

---

## 7. Bauabschnitt B2 — Editor.js als Eingabe + Rohmodus (Build 657)

**Ticket:** `8f2b64d9` · setzt B1 voraus.

### 7.1 Vorhandenes

Editor.js **2.31.6** ist gebündelt: `static/editor/editor.bundle.js` (367 358 Bytes),
Werkzeuge laut `static/editor/bundle_manifest.json`: `header, paragraph, nested-list, table,
quote, simple-image, marker, annotation, undo, delimiter`. Im Cockpit bereits geladen
(`cockpit.html:199`). Die Vorschau nutzt davon eine bewusst reduzierte Auswahl
(`cockpit_baustein_vorschau.js:118-132`, ohne `evidence`/`annotation`/`placeholder`).

### 7.2 Soll

Zwei Eingabearten, umschaltbar:
* **Komfort** — Editor.js, `readOnly:false`, Werkzeugsatz identisch zur Vorschau plus das
  Platzhalter-Inlinewerkzeug.
* **Roh** — Textfeld mit JSON. Gefordert (Ticketwortlaut): Zeile/Spalte bei Fehlern,
  Klammerbilanz, Formatieren-Knopf. **Syntaxfärbung ausdrücklich nicht** — eigenes Ticket.

**Der Kern des Tickets ist nicht der Editor, sondern der Vergleich beim Moduswechsel:**
*„Beim Wechsel vom Roh- in den Komfortmodus wird VERGLICHEN und werden Unterschiede
GEMELDET, statt sie zu schlucken."* Editor.js reicht `block_data` an das jeweilige Werkzeug
durch; was ein Werkzeug nicht kennt, überlebt ein `save()` möglicherweise nicht.
Präzedenzfall im Bestand: `UnknownBlock` in `editor/html_renderer.py` rendert einen
sichtbaren Platzhalter, statt still zu verwerfen.

**Umsetzung:** vor dem Wechsel `block_data` festhalten, nach `editor.save()` tief vergleichen,
jede weggefallene oder geänderte Eigenschaft **mit Pfad** melden. Der Wechsel wird erst
vollzogen, wenn die Meldung bestätigt ist.

### 7.3 Zwei bekannte Stolpersteine

* **Der Entwurfsspeicher greift nicht.** `cockpit_modules.js:690-691` hängt an
  `form.addEventListener('input'|'change', _persistDraft)`. Editor.js erzeugt **kein**
  `input`-Ereignis auf dem Formular — der Draft-Mechanismus (`DRAFT_KEY` `:64`,
  `_restoreDraft` `:501-529`) müsste sonst stillschweigend aussetzen. Er ist an
  `editor.onChange` zu hängen. **Ohne diesen Punkt verliert die Maske Entwürfe.**
* **`_schluesselFeldStand()` bleibt die einzige Regel** (`:289-296`). Das ist die Lehre aus
  `219838e4` („es gab DREI unabhängige Ausdrücke für den Feldzustand"). Der Umbau darf keinen
  vierten hinzufügen.

### 7.4 Prüfkennungen

**ED01–ED03** Umschalten in beide Richtungen ohne Inhaltsverlust; **ED04** unbekannte
Eigenschaft in `block_data` wird beim Wechsel **gemeldet**, nicht geschluckt; **ED05**
Rohmodus meldet Zeile/Spalte bei defektem JSON; **ED06** Klammerbilanz; **ED07** Entwurf
wird auch bei Editor-Eingabe gesichert und wiederhergestellt; **ED08** Schlüsselfeldregel
unverändert (MK01–MK07 laufen weiter durch).

---

## 8. Zeit- und Auslieferungsplan

| Build | Abschnitt | Klasse | Einzeln auslieferbar |
|---|---|---|---|
| 652 | A1 Vorschau rechts, dauerhaft | A | ja |
| 653 | A2 Liste auf Tabulator | A | ja |
| 654 | A3 Platzhalter-Tabelle, Stufe 1 | A | ja |
| 655 | A3 Platzhalter-Tabelle, Stufe 2 (bidirektional) | A | ja |
| 656 | B1 Migration + `3d9016fe` | **B** | nein |
| 657 | B2 Editor.js-Eingabe + Rohmodus | **B** | nein |

**Ehrliche Einschätzung zum Umfang:** 652–654 sind an einem Tag machbar. 656 ist wegen der
fünf DDL-Wahrheiten (§6.4 a) und der Testnachzüge (§6.4 b) der aufwendigste Einzelbuild der
Reihe, obwohl das eigentliche `ALTER TABLE` zwei Zeilen hat. 657 setzt 656 voraus und ist
danach nicht mehr an einem Tag mit der nötigen Sorgfalt zu prüfen. Alles sechs heute
zuzusagen wäre eine Zusage, die ich nicht belegen kann.

Je Build: `python run_tests.py` in der VM vor Übergabe, `build.json` fortgeschrieben,
`MD5SUMS_Build<NNN>.txt`, Archiv `aiw_webserver_<NNN>.zip` mit erhaltener
Verzeichnisstruktur, Tracker-Eintrag als `eintraege_claude_Build<NNN>.json`.

---

## 9. Offene Entscheidungen — vor Baubeginn zu treffen

**Frage 1 — Umfang und Reihenfolge für heute.** Welche Builds sollen heute entstehen? Meine
Empfehlung: 652–654 (Klasse A, jederzeit lieferbar, trifft „das UX gefällt mir nicht"
unmittelbar), danach 656 nur, wenn dafür noch ein sauberes Prüffenster in der VM bleibt.

**Frage 2 — Datenmodell `block_type`/`block_data`.** Drei Teilentscheidungen:
(a) `CHECK`-Constraint auf `block_type` gegen den Wertevorrat aus `userinfo/module_panel.js:117-122`
(`paragraph, header, list, table, quote, delimiter`) — oder offen lassen? Ein `CHECK` ist über
`ADD COLUMN` **nicht** nachrüstbar ohne Tabellen-Rebuild; er müsste also jetzt oder gar nicht
kommen. Meine Empfehlung: **kein `CHECK` in der Datenbank**, stattdessen Prüfung im
`module_validator` — neue Editor.js-Werkzeuge sollen später nicht an einer Migration hängen.
(b) `block_data` als JSON-**Text** in der Datenbank, an der API als **Objekt** — die Vorschau
erwartet ausdrücklich ein Objekt (`cockpit_baustein_vorschau.js:74`). Bestätigen?
(c) Führendes Feld: bleibt `body` die Wahrheit und `block_data` die Struktur daneben, oder
wird `block_data` führend und `body` nur noch der Klartextspiegel für die Altpfade
(`forensic_api/templates_ep.py`, `module_panel.js`)? Meine Empfehlung: **`block_data` führend,
sobald gesetzt; `body` wird beim Speichern aus `block_data` als Klartext mitgeschrieben und
bleibt `NOT NULL`** — so bleibt jeder Altpfad und die Volltextsuche unverändert lauffähig.

**Frage 3 — Platzhalter-Tabelle: Ausbaustufe.** Stufe 1 (lesen, verifizieren, testen) heute
sicher machbar. Stufe 2 (bidirektional) ist der Wunsch aus dem Ticket, bringt aber das
Zurückschreiben in den Bausteintext mit den drei Fallen aus §5.5. Heute mitnehmen oder als
eigenen Build nachziehen?

**Weitere Fragen bestehen** (Beschränkung auf drei je Wortwechsel, § Projektregeln) — offen
sind mindestens: der Zuklapp-Schalter aus §3.3, wer die Migration in der VM fährt und ob dafür
ein Wartungsfenster gesetzt wird, sowie die Bestätigung des VM-Standes per MD5 gegen
`MD5SUMS_Build651.txt`.

---

## 10. Belegverzeichnis

Alle Zeilenangaben gegen Commit `85ec890` (Build 651). Geprüft am 2026-08-02 durch Lesen der
genannten Dateien; nicht durch Ausführung — die Prüfung in der VM steht noch aus.

**Ausdrücklich unbelegt und daher nicht behauptet:** ob eine Startprüfung des
Migrationsstandes existiert (kein Aufrufer von `templates_db_status` in `main.py`,
`management.py`, `start.sh`, `start.bat` gefunden — Abwesenheitsbeweis durch Suche, nicht
durch Ausführung); der Wertevorrat für `block_type` (nirgends festgelegt, die Liste in
`module_panel.js:117-122` ist ein Indiz, keine Festlegung); ob der Bestand in der VM auf
Migrationsstand 497 steht.
