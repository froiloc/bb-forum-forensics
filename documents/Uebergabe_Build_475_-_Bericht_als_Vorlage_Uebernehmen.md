# Übergabe Build 475 — „Bericht als Vorlage übernehmen"

**Modul:** `aiw_webserver` · **Build:** 475 · **Basis:** HEAD `551dfa9` (v0.8.470) · **Datum:** 2026-07-21 **Bauplan:** `management/Bauplan_ReportAlsVorlage_v0_2.md` (v0.2, abgenommen mc)

## Was wurde gebaut

Schaltfläche im Teil **Lektorat**: „Als Vorlage uebernehmen". Sie erzeugt aus dem
aktuell gewählten Bericht (Baustelle 6) einen Vorlagen-**Entwurf** und wechselt in
den Teil **Dokumentvorlagen**, wo die `supervisor` ihn sichtet und über den
bestehenden auditierten Pfad (`POST /api/templates/document`) speichert.

## Sanitisierung (Festlegung mc 2026-07-21)

Der fallbezogene Inhalt liegt ausschließlich in den Platzhalter-**Werten** (Spalte `report_blocks.placeholder_values_json`). Der Extractor liest diese Spalte **nicht** und übernimmt je Block nur `{block_type, block_data}` → alle
Platzhalter-Werte entfernt, die neutralen Token `{{a:}}/{{m:}}/{{o:}}` bleiben.
Sonderfall `evidence`: Wrapper bleibt, `evidence_ids → []`. Jede Entfernung wird
als Befund gemeldet (Grundregel 1).

## Dateien (im ZIP, absolute Pfade)

- NEU `management/templates_admin/report_template_extractor.py`
- GEÄNDERT `management/server/management_app.py` (GET `/api/report/as-template-draft`)
- GEÄNDERT `management/server/static/cockpit_lectorate.js`, `cockpit.js`, `cockpit_doctemplates.js`, `cockpit.css`
- NEU `tests/test_report_template_extractor.py`, `tests/test_report_as_template_draft_api.py`, `tests/unit/test_build475_report_as_template.test.js`
- `build.json`, `MD5SUMS_Build475.txt`

## Kein Migrationsrisiko

`evidence_<uid>.db` nur `mode=ro` gelesen; `templates.db` nur über den bestehenden
auditierten Upsert geschrieben; kein Schema-Eingriff.

## Regression

Python 1593 passed / 0 failed (Cloud: `test_editor_renderer.py` ausgeklammert);
vitest 904 passed / 0 failed; `py_compile`/`node --check` grün.

## RBAC-Hinweis (operativ, nicht Teil des Builds)

Der Knopf braucht `reports.review|approve` **und** `templates.edit` auf derselben
Rolle (operativ `supervisor`). Grants sind default-deny und per `policy_admin` zu
vergeben.

## Offen / nächste Schritte

Abnahme in der VM (`python run_tests.py` inkl. vitest), MD5-Abgleich gegen `MD5SUMS_Build475.txt`, danach Commit/Rollout.
