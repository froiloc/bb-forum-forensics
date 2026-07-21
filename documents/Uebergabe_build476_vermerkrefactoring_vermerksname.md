# Übergabe Build 476 — Baustelle 4: „Bericht"→„Vermerk" + editierbarer Vermerksname

Modul: `aiw_webserver` · Build 476 (v0.8.476) · 2026-07-21

## Nummerierung / Merge

Ursprünglich lokal als **473** gebaut. Parallel wurden remote bereits **473** (Crossfindings-Basis), **474** (Crossfindings-Overview) und **475/475b** („Bericht als Vorlage übernehmen") vergeben. Daher sauber auf `origin/master` HEAD `ba7faf9` (v0.8.475b) gemerged und auf **476** neu nummeriert. **Einziger Berührungspunkt:** `management/server/static/cockpit_doctemplates.js` — Build 475 ergänzte `draftToRows`/`findingsText`/`_fillDraft`/Befund-Panel (andere Regionen); meine Änderung betrifft nur `reportTypeLabel` + Options-Reihenfolge. Automatischer Merge konfliktfrei, beide Stände erhalten. Alle übrigen 15 Dateien wurden von 473–475 nicht angefasst.

## Entscheidungen (mit Alex abgestimmt 2026-07-21)

- **Voller Sweep inkl. Cockpit** für Typ-Labels; generisches „Bericht" nur im Ermittler-Editor vollständig, Cockpit-Abschnittsüberschriften belassen (Begriff nur „teilweise" abzulösen).
- **Heuristik ohne Flag** → kein Schemaeingriff, kein Migrationsvorbehalt (Stichtag 01.07.2026).
- **Erster `header`-Block (H1)** = „Editor.js-Title-Element".

## Label-Mapping (DB-Schlüssel unverändert)

`interim`→**Vermerk** · `addendum`→**Ergänzungsvermerk** · `final`=**Abschlussbericht** (Reihenfolge zuletzt). DB-Werte `interim/final/addendum` unverändert → migrationsneutral.

## Belegte Kerninvariante (Siegel-Integrität)

`report_sealer._REPORT_COLS` enthält `title`; `_hash()` serialisiert die `reports`-Zeile. Umbenennen bräche ein Siegel → `update_report_title()`/Endpunkt **strikt auf Status `draft`** begrenzt. Namenszeile nur bei `draft` + Lock editierbar.

## Auto-Sync-Modell (`report_editor.js`)

`_nameManual` (in-memory). Laden: `manuell = (title !== erste-H1)`. onChange: nicht-manuell → Name := erste H1 (debounced persist). Namenszeile absenden: leer → Auto-Sync reaktivieren (Name := H1); nicht-leer → `manuell = (Wert !== H1)`. Anlage optional: Way 1 (Name→H1, manuell), Way 2 (leer→„Neuer Vermerk", Auto). **Dokumentierte Konsequenz:** Der manuelle Lock aus Way 1 überlebt nur die Sitzung; nach Reload liest die Heuristik Name==H1 wieder als „automatisch".

## Geänderte Dateien (16) + `MD5SUMS_Build476.txt`

`db/evidence_db.py`, `forensic_api/reports.py`, `forensic_api/__init__.py`, `forensic_api/report.py`, `editor/html_renderer.py`, `report_render/{pdf,html,docx}_renderer.py`, `management/server/static/cockpit_reports.js`, `management/server/static/cockpit_doctemplates.js` (gemergt), `userinfo/report_editor.js`, `userinfo/report.css`, `tests/test_baustelle4.py` (neu `TestReportRename`), `tests/test_editor_renderer.py`, `tests/unit/test_cockpit_reports.test.js`, `build.json`. `userinfo/report.js` = Alt-Modul, nicht angefasst.

## Regression (nach Merge auf 475b-Basis)

`py_compile` (3.13) OK · `node --check` OK · **pytest 1618 passed / 61 skipped** · **vitest 928 passed / 80 Dateien** (inkl. der Remote-Suiten crossfindings, report-as-template, scroll_memory).

## Manuelles UI-Prüfprotokoll (Sync, nicht unit-getestet)

`window.forensicDebug=true`: (1) Neuer Vermerk ohne Namen → H1 tippen, Zeile folgt live. (2) Mit Namen → H1 steht + Zeile; H1 ändern → Name folgt NICHT (Sitzung). (3) Zeile manuell ändern → Sync endet. (4) Zeile leeren+Enter → Name := aktuelle H1, Sync wieder aktiv. (5) `submitted` → Zeile disabled, Rename-Endpunkt 409.
