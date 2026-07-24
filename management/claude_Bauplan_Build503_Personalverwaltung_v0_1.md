# Bauplan Build 503 — Personalverwaltung (Cockpit-Sicht) + Cache-Fix

- **Version:** v0.1 · **Datum:** 2026-07-24 · **Basis:** v0.8.502 (master `bf2443e`)
- **Bedarf/Beleg:** Projektgespräch 2026-07-24 (mc): „Mir fehlt also eine Seite
  zum Verwalten der Anwender. Auf jener Seite sollte dann auch die Einbindung
  [des AD-Abgleichs] sein." + Zustimmung zu den optionalen Vorschlägen
  (auditiertes Setzen von Rollenzuweisungen aus der Oberfläche; die Grants der
  Rollen-Matrix bleiben der CLI vorbehalten).
- **Vorfall (Cache):** 2026-07-24 — „AD-Abgleich-Modul nicht geladen" trotz
  korrektem Deploy. Ursache: der Management-Server sendet für `/` und
  `/static/*` KEINE Cache-Control-Header (nur SSE hat `no-cache`,
  `management_handler.py` Z. 179); der Browser hielt die alte `cockpit.html`
  im Cache, die `cockpit_adsync.js` nie referenziert — daher auch kein
  404 im Serverlog. Sofortmaßnahme war Strg+F5; dieser Build behebt die
  Ursache.

## 1. Cache-Fix (management_handler.py)

`_send_bytes` (der EINE Sendepfad aller Nicht-SSE-Antworten) sendet künftig
`Cache-Control: no-cache`. Wirkung: der Browser revalidiert jede Ressource
bei jedem Zugriff; da der Server lokal (127.0.0.2) läuft, ist der Overhead
bedeutungslos, und Deploys greifen sofort. Kein ETag/Last-Modified-Ausbau
(bewusst einfach; Revalidierung ohne Validatoren = frischer Abruf).

## 2. Migration M021 — RBAC-Seed Personalverwaltung

`m021_personnel_rbac.py` (Muster M014: reiner Capability-Seed, eingefrorene
Kopie, m005-Prinzip; `catalog.py` ergänzt):

- `personnel.view` — „Personalliste sehen": Personen mit Aktiv-Status,
  Flags und Rollenzuweisungen lesen.
- `personnel.edit` — „Personal pflegen": Rollen-Flags setzen und
  Rollenzuweisungen erteilen/widerrufen (auditiert).

Default-deny; Grants an `supervisor` operativ via `policy_admin`
(Empfehlung: `personnel.view` + `personnel.edit` + `personnel.sync`).
Bestehende Anker-Tests wachsen 31 → 33 Capabilities, Migrationsliste +21.

## 3. Backend

- **NEU `management/person/person_overview_repo.py`** — `PersonOverviewRepo`,
  REIN LESEND: alle Personen (inkl. `is_active`, `deactivated_at/-reason`,
  Flags) + je Person die AKTIVEN Rollenzuweisungen (`person_role.id`,
  `role_code`, Label aus `rbac_role`, `assigned_at`) + Rollenkatalog.
- **`management_app.py`** (alle Routen Tor wie angegeben):
  - `GET  /api/personnel` (personnel.view) → `{persons, roles_catalog,
    can_edit, can_sync}` (die beiden Flags steuern nur die Anzeige; jede
    Schreibroute prüft ihr Recht selbst).
  - `POST /api/personnel/flags` (personnel.edit) → `{person_id,
    is_investigator?, is_supervisor?, is_support?}` via `PersonRepo.update`
    (Beleg INVESTIGATOR_UPDATED, Diff alt→neu).
  - `POST /api/personnel/role/assign` (personnel.edit) → `{person_id,
    role_code}` via `RbacRepo.assign_role` (Beleg ROLE_ASSIGNED).
  - `POST /api/personnel/role/revoke` (personnel.edit) → `{person_role_id}`
    via `RbacRepo.revoke_role` (Soft-Revoke, Beleg ROLE_REVOKED).
  - **SELBSTSCHUTZ (Entwurfsentscheidung, zur Abnahme):** die eigene Person
    ist über die Oberfläche unantastbar — eigene Flags ändern und eigene
    Rollenzuweisungen widerrufen → 400 mit Klartext. Grund: Lockout-/
    Selbst-Degradierungs-Schutz im Browser (ein Versehen ist ein Klick);
    der auditierte CLI-Weg (`rbac_admin`/`person_admin`) bleibt dafür offen.
- **Bewusst NICHT in der Oberfläche** (kein stiller Verzicht):
  - Grants der Rollen-Matrix (rbac_grant) — bleiben CLI (`policy_admin`),
    Anzeige weiterhin in „Rechte / Policy" (mc 2026-07-24).
  - Person anlegen — der AD-Abgleich ist der Aufnahme-Weg (Build 501/502);
    Sonderfälle über `person_admin create`.
  - `display_name` ändern — das AD ist die Namensquelle (Abgleich zieht nach).
  - Manuelles Deaktivieren OHNE AD-Kandidatur — Deaktivierung läuft über die
    Entfernen-Bestätigung des AD-Abgleichs (mc-Vorgabe); Ausnahmen per CLI.

## 4. Frontend

- **NEU `cockpit_personnel.js`** — Sicht „Personalverwaltung" (Gruppe
  ‚Verwaltung', Cap `personnel.view`):
  - Personenliste als DOM-Tabelle: Kennung, Anzeigename, Status
    (aktiv/inaktiv + Zeitpunkt/Grund als Tooltip-Text), Flags
    (Checkboxen bei `can_edit`, sonst nur Anzeige), Rollen-Chips mit
    Widerrufs-„×" + Zuweisen-Dropdown (bei `can_edit`).
  - Abschnitt **„AD-Abgleich"** (nur bei `can_sync`): LAZY — Knopf
    „AD-Vorschau laden" holt `/api/adsync` erst auf Klick (kein
    LDAP-Zugriff beim bloßen Öffnen der Seite) und rendert die BESTEHENDE
    Komponente `AIWCockpitAdSync.renderAdSync` in einen Unter-Container
    (Wiederverwendung statt Kopie).
  - IIFE, DEV-Logging, textContent (XSS), reine Funktionen für vitest.
- **`cockpit.js`**: Nav-Eintrag `personnel` (personnel.view) ERSETZT den
  Eintrag `adsync` — die Einbindung auf der Personal-Seite ist die von mc
  gewünschte Bedienung; Kataloggröße bleibt 30. `loadPersonnel` mit
  Callbacks (flags/assign/revoke/adsync-apply/-decide); nach jedem
  Schreiben wird die Sicht NEU geladen (kein optimistisches UI); war der
  AD-Abschnitt offen und die Aktion kam aus ihm, wird er mitgeladen
  (bewusst genau EIN frischer LDAP-Abruf nach eigener Aktion). SSE-Reload
  lädt NUR die Personenliste, nie den AD-Abschnitt (kein LDAP-Spam).
  ÜBERGANG: Wer nur `personnel.sync` ohne `personnel.view` hat, sieht die
  Seite nicht → Übergabe-Hinweis, beide Grants zu vergeben.
- `cockpit.html` (Script-Tag), `cockpit.css` (scoped `.aiw-pers-*`).

## 5. Tests

- `tests/test_person_overview_repo.py` — Liste inkl. Rollen/Status; rein
  lesend (Zeilenzahlen unverändert).
- `tests/test_management_personnel_endpoint.py` — PN01: 403 ohne Recht;
  PN02: Liste mit Rollen + can_edit/can_sync; PN03: Flags setzen (Beleg,
  Diff); PN04: Rolle zuweisen/widerrufen (Belege, Soft-Revoke); PN05:
  Selbstschutz (eigene Flags/eigene Rolle → 400, keine Änderung); PN06:
  bad requests.
- `tests/unit/test_cockpit_personnel.test.js` — reine Funktionen + DOM
  (JSDOM): Zeilenbau, Flag-/Rollen-Callbacks, Lazy-AD-Abschnitt, XSS.
- `tests/test_management_handler_cache.py` — `_send_bytes` sendet
  `Cache-Control: no-cache` (Vorfalls-Regression).
- Anker-Updates: rbac_schema/demo_seed 31→33; dashboard-Migrationsliste +21;
  nav-Katalog: 'adsync' → 'personnel' (Länge bleibt 30).

## 6. Migrationsklasse

M021 ist ein reiner rbac_capability-Seed (additiv, idempotent, nur
coordinator.db). Kein Eingriff in Ermittler-Daten;
evidence_/forensic_/assets_<uid>.db unberührt.
