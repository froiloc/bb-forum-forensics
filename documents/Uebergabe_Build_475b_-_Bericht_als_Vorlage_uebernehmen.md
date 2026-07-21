# Übergabe Build 475b — „Bericht als Vorlage übernehmen"

**Modul:** `aiw_webserver` · **Build:** 475b · **Basis:** HEAD `ee55528` (v0.8.474) · **Datum:** 2026-07-21 **Bauplan:** `management/Bauplan_ReportAlsVorlage_v0_2.md` (abgenommen mc)

## Korrektur 475 → 475b (Ursache dokumentiert)

Der erste 475er-Stand war auf Basis **v0.8.470** gebaut. Zwischen 470 und dem
tatsächlichen VM-Stand liegen aber die Builds **471–474**. Da Änderungen als
vollständige Datei übergeben werden, hat meine 470-basierte `management_app.py` (und `cockpit.js`/`cockpit.css`) beim Einspielen die 471–474-Ergänzungen
zurückgesetzt — u. a. den `/api/crossfindings`-Endpunkt aus Build 474 → die vier
Fehlschläge in `tests/test_crossfindings_api.py` (404 statt 403/200/503). **475b** setzt dieselben Änderungen sauber auf **474** neu auf; `crossfindings` bleibt erhalten. `cockpit_lectorate.js`/`cockpit_doctemplates.js` waren 470→474
unverändert (identische MD5 zur 475-Lieferung).

## Was gebaut wurde

Schaltfläche im Teil **Lektorat** („Als Vorlage uebernehmen") → erzeugt aus dem
gewählten Bericht einen Vorlagen-**Entwurf** und wechselt in **Dokumentvorlagen**,
wo die `supervisor` ihn sichtet und über den bestehenden auditierten Pfad
(`POST /api/templates/document`) speichert.

## Sanitisierung

`placeholder_values_json` wird nicht gelesen → alle Platzhalter-Werte entfernt,
Token `{{a:}}/{{m:}}/{{o:}}` bleiben. `evidence`-Wrapper bleibt, `evidence_ids → []`.
Jede Entfernung als Befund (GR1).

## Dateien (aiw_webserver_475b.zip, absolute Pfade)

NEU `management/templates_admin/report_template_extractor.py`; GEÄNDERT `management/server/management_app.py` (GET `/api/report/as-template-draft`), `cockpit_lectorate.js`, `cockpit.js`, `cockpit_doctemplates.js`, `cockpit.css`;
NEU `tests/test_report_template_extractor.py`, `tests/test_report_as_template_draft_api.py`, `tests/unit/test_build475_report_as_template.test.js`; `build.json`, `MD5SUMS_Build475b.txt`.

## Regression (auf 474)

Python 1609 passed / 0 failed inkl. `test_crossfindings_api.py` (Cloud: `test_editor_renderer.py` ausgeklammert); vitest 928 passed / 0 failed; `py_compile`/`node --check` grün.

## RBAC (operativ)

Knopf braucht `reports.review|approve` **und** `templates.edit` (operativ `supervisor`); Grants default-deny, per `policy_admin`.

## Lehre für künftige Builds

Vor dem Bauen `git fetch` und auf den **aktuellen** `origin/master` aufsetzen —
nicht auf den zu Sessionbeginn geklonten Stand, wenn zwischenzeitlich Builds
hinzukamen.
