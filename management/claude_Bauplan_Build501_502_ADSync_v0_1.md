# Bauplan — Active-Directory-Abgleich der Ermittlerstammdaten (Builds 501–502)

- **Version:** v0.1 · **Datum:** 2026-07-24 · **Basis:** v0.8.500 (master `d572944`)
- **Bedarf/Beleg:** Projektgespräch 2026-07-24 (mc): „Die ‚lokalen' Benutzer in
  unserer coordinator.db sollen mit dem Active-Directory abgeglichen werden. …
  Neue Mitglieder mit der Rolle `investigator`. … Entfernen nur nach
  Supervisor-Bestätigung (Eingabe des Wortes ‚Entfernen'), nie löschen, nur
  inaktiv schalten." PoC: `get-members4.py` (Projektspeicher, live in der
  PROD-Umgebung verifiziert).

## 1. Grundsatzentscheidungen (mc 2026-07-24)

- **(E1) Repo-Stand:** Aufsetzen auf Build 500 (durch mc gepusht, `d572944`).
- **(E2) Bedienweg:** BEIDE Wege — gemeinsamer Sync-Kern, angebunden an
  CLI (`management/ad_sync/ad_sync_admin.py`, Betriebsweg) UND Cockpit-Sicht
  (Build 502), nach dem Muster Onboarding (Builds 464/465).
- **(E3) Inaktiv-Modell:** Migration **M020** ergänzt `person.is_active`
  (INTEGER NOT NULL DEFAULT 1), `person.deactivated_at` (INTEGER NULL),
  `person.deactivated_reason` (TEXT NULL). Rollen-Flags und `person_role`
  bleiben als historischer Beleg unangetastet. Es existiert KEIN bisheriger
  „Ruhestand"-Mechanismus (Beleg: Volltextsuche über management/, core/, db/,
  Migrationen M001–M019 am 2026-07-24 ohne Treffer; `person`-Spaltenliste in
  `setup_coordinator_dev.py` / `db/coordinator_db.py`).
- **(E4) Rollenvergabe Neue:** Doppelt — `person.is_investigator=1` (Flag,
  via `PersonRepo.create`) UND `person_role`-Zuweisung `investigator`
  (via `RbacRepo.assign_role`), beides in auditierten Schreibpfaden.
- **(E5) Abhängigkeiten:** `requirements.txt` bereits durch mc aktualisiert
  (Build 500: ldap3, ms_active_directory, winkerberos, dnspython, …).

## 2. Konfiguration (Teilauftrag „4 Variablen in config.yaml")

Die vier PoC-Variablen aus `.env` wandern nach `config.yaml` unter die
bestehende AD-Sektion (Nachbarschaft zu `ad.release_recipients`, Build 462):

```yaml
ad:
  ldap:
    domain_dns_name: ""   # PoC: DOMAIN_DNS_NAME  — DNS-Name der AD-Domäne
    base_dn: ""           # PoC: LDAP_BASE_DN     — Suchbasis Gruppenauflösung
    user_base: ""         # PoC: LDAP_USER_BASE   — Suchbasis Benutzerauflösung
    target_group: ""      # PoC: TARGET_GROUP_NAME — AD-Gruppe der Ermittler
```

Leerwerte ⇒ AD-Abgleich meldet einen klaren Konfigurationsfehler
(DEFAULT-DENY, kein stilles Überspringen — Grundregel 1). Echte Werte werden
NICHT eingecheckt (Dienst-Infrastruktur); Eintrag erfolgt durch mc in der VM.

## 3. LDAP-Schicht (Build 501)

`management/external/ldap_group_reader.py` — Klasse `LdapGroupReader`,
1:1-Übernahme der im PoC verifizierten Logik:

1. DC-Ermittlung über `ms_active_directory.ADDomain(domain).get_ldap_uris()`.
2. Bind Kerberos/SSPI (`ldap3` SASL/GSSAPI, wie PoC ohne `session_security`).
3. Gruppen-DN per `(&(objectClass=group)(cn=<target_group>))` unter `base_dn`.
4. Mitglieder rekursiv per Matching-Rule `1.2.840.113556.1.4.1941`
   (LDAP_MATCHING_RULE_IN_CHAIN) unter `user_base`;
   Attribute `sAMAccountName`, `displayName`.

Rückgabe: Liste `{sam, display_name}`. Jeder Fehlschlag ⇒ `LdapError` mit
Klartext (kein stilles Weiterlaufen). Die ldap3-/ms_active_directory-Importe
liegen IN der Methode (lazy), damit Test-/Dev-Umgebungen ohne AD-Pakete die
Module laden können. Muster F4 (`ad_directory.py`, `identity.py`): die
Mitgliederquelle ist im Sync-Kern ein injizierbarer Provider — Tests mocken,
Betrieb nutzt `LdapGroupReader`. KEIN Live-LDAP in Tests.

## 4. Migration M020 (coordinator.db)

`management/migrations/coordinator/m020_person_active_adsync.py`:

- `ALTER TABLE person ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1`
- `ALTER TABLE person ADD COLUMN deactivated_at INTEGER` (NULL = aktiv)
- `ALTER TABLE person ADD COLUMN deactivated_reason TEXT`
- Seed RBAC-Capability `personnel.sync` („AD-Abgleich durchführen") —
  Muster M017 (Schema + Capability-Seed in einer Migration); Aufnahme
  ebenfalls in `management/rbac/catalog.py` (Wahrheitsquelle im Code;
  eingefrorene Kopie in der Migration, m005-Prinzip).
- Idempotenz-Guards (PRAGMA table_info / INSERT OR IGNORE);
  `verify`: Zeilenzahl `person` unverändert, alle Bestandszeilen
  `is_active=1`, `deactivated_at/reason` NULL.
- Grant `personnel.sync` an Rollen ist bewusst NICHT Teil des Seeds
  (default-deny; Vergabe operativ via `policy_admin`, wie M014/M015).

## 5. Sync-Kern (Build 501) — `management/ad_sync/`

Eine Klasse je Datei (Grundregel 10):

- **`sync_plan.py`** — REINE Logik, ohne I/O: `SyncPlanner.build(ad_members,
  persons)` → `SyncPlan` mit vier Mengen:
  - `create`: im AD, nicht in person ⇒ Neuaufnahme als investigator (E4).
  - `rename`: sam vorhanden, `displayName` ≠ `display_name` ⇒ Namensänderung.
  - `deactivate_candidates`: aktiver person-Satz, sam nicht im AD ⇒ Kandidat —
    NUR nach Bestätigung (§6).
  - `reactivate_candidates`: inaktiver person-Satz, sam wieder im AD ⇒
    Kandidat für Reaktivierung — ebenfalls NUR nach Bestätigung (§6),
    da dabei die historischen Rollen (ggf. supervisor) wieder scharf würden.
  - Abgleich case-insensitiv (SAMAccountName ist AD-seitig nicht
    case-sensitiv, Beleg `ad_directory.py`); kanonische Schreibweise:
    Bestand aus DB, Neue aus AD. Leerer `displayName` im AD fällt auf den
    sam zurück (kein leerer Anzeigename, Beleg `person_repo.create`-Guard).
- **`sync_executor.py`** — `SyncExecutor`, ALLE Schreibpfade über
  `CoordinatorWriter` (Write+Audit in einer Transaktion):
  - `run_preview()` → AD lesen, Plan bauen (rein lesend, kein Beleg).
  - `apply_automatic(plan, actor_id)` → creates (PersonRepo.create +
    RbacRepo.assign_role `investigator`) und renames (PersonRepo.update);
    Abschluss-Beleg `AD_SYNC_RUN` mit Zählern (Klammer über den Lauf).
  - `deactivate(person, reason, confirmation, actor_id)` — verlangt
    EXAKT das Wort „Entfernen" (Schreibweise identisch); sonst
    `AdSyncError`. Setzt `is_active=0`, `deactivated_at=now`,
    `deactivated_reason`; Beleg `PERSON_DEACTIVATED` (Payload: sam,
    Anzeigename, Grund, Bestätigungswort). NIEMALS DELETE.
  - `abort_deactivation(person, actor_id, note)` — protokollierter
    Abbruch: Beleg `PERSON_DEACTIVATION_ABORTED`, KEINE Datenänderung.
  - `reactivate(person, confirmation, actor_id)` — Wort „Reaktivieren";
    setzt `is_active=1`, löscht `deactivated_at/reason` (Werte stehen im
    Audit-Payload alt→neu); Beleg `PERSON_REACTIVATED`.
- **`ad_sync_admin.py`** — CLI (Muster `onboarding_admin`):
  - `preview [--json]` — Plan anzeigen, rein lesend.
  - `apply --actor KENNUNG` — creates/renames automatisch; danach je
    Deaktivierungs-/Reaktivierungskandidat interaktive Abfrage
    („Entfernen"/„Reaktivieren" oder Abbruch), jeweils auditiert.
  - `--db/--config` wie bestehende Admin-CLIs; Exit-Codes 0/1.

Neue EventTypes (`management/audit/event_types.py` + Aufnahme in `ALL`):
`AD_SYNC_RUN`, `PERSON_DEACTIVATED`, `PERSON_DEACTIVATION_ABORTED`,
`PERSON_REACTIVATED`. Anlegen/Umbenennen nutzen die BESTEHENDEN Belege
`INVESTIGATOR_CREATED`/`INVESTIGATOR_UPDATED` (historische Semantik,
target_type='investigator'; m005-Prinzip).

`PersonRepo` wird additiv erweitert: Lesepfade liefern `is_active`,
`deactivated_at`, `deactivated_reason` mit (defensiv: fehlt die Spalte —
DB vor M020 — wird `is_active=1` angenommen, damit Lesewerkzeuge auf
Altbestand nicht brechen); neue Methoden `deactivate`/`reactivate`
(auditiert, wie oben). `IdentityResolver` weist inaktive Konten ab
(`IdentityError` mit Klartext) — ein entfernter Ermittler darf sich nicht
mehr am Management-Portal anmelden.

## 6. Bestätigungs-Semantik (Vorgabe mc)

- Deaktivierung NUR nach wörtlicher Eingabe **„Entfernen"** (Schutz vor
  Glitch-Entfernungen, z. B. AD-Ausfall/halbleere Gruppenantwort).
- Der Abbruch der Frage ist ebenso ein Beleg (`PERSON_DEACTIVATION_ABORTED`).
- Entfernte Benutzer werden NIE gelöscht — nur `is_active=0`.
- Symmetrisch (Entscheidung Claude, zur Abnahme durch mc): Reaktivierung
  verlangt **„Reaktivieren"**, weil dabei historische Rollen wieder wirksam
  werden.
- Zusätzliche Sicherung: meldet das AD **null Mitglieder**, wird der Lauf mit
  Fehler abgebrochen (leere Gruppe ist mit überwältigender Wahrscheinlichkeit
  ein Glitch/Fehlkonfiguration, kein realer Personalstand).

## 7. Build 502 — Cockpit-Sicht + API

- `management/server/management_app.py`:
  - Konstruktor-Parameter `ad_members_provider` (injizierbar, Muster
    `case_launcher`), Default: `LdapGroupReader.from_config`.
  - `GET /api/adsync` (Cap `personnel.sync`) → Plan als JSON (Preview).
  - `POST /api/adsync/apply` (Cap `personnel.sync`) → creates/renames.
  - `POST /api/adsync/decide` (Cap `personnel.sync`) → Body
    `{sam, action: deactivate|abort|reactivate, confirmation, reason}`;
    Bestätigungswort wird SERVERSEITIG geprüft (nie nur im Browser).
- `management/server/static/cockpit_adsync.js` — Sicht „AD-Abgleich"
  (Gruppe ‚Verwaltung'): Vorschau-Tabellen (Neu / Umbenennung / Entfernungs-
  kandidaten / Reaktivierungskandidaten), je Kandidat Texteingabe des
  Bestätigungsworts + Grund, Buttons „Bestätigen"/„Abbrechen (protokolliert)";
  IIFE, Debug-Logging, gekapselt, ausführlich kommentiert (JS-Gebote 1–4).
- Nav-Eintrag in `cockpit.js`, Stil in `cockpit.css` (scoped `.aiw-adsync-*`).
- JS-Tests (vitest) für reine Renderer-/Zustandsfunktionen.

## 8. Nicht in diesem Schnitt (kein stilles Übergehen)

- Filter `is_active=1` in Auslastungs-/Zuweisungs-Sichten (`/api/assignable`,
  Workload/Kapazität): inaktive Ermittler erscheinen dort weiter, bis das in
  einem Folgebuild je Sicht entschieden ist (betrifft Anzeige, nicht Rechte —
  die Portal-Anmeldung ist ab 501 gesperrt).
- Automatischer/geplanter Sync (Scheduler) — Abgleich bleibt manuell
  angestoßen.
- Offboarding-Checkliste (M017) wird beim Deaktivieren nicht automatisch
  eröffnet (Verzahnung möglich, separat zu entscheiden).

## 9. Migration / Produktivbetrieb (seit 2026-07-01)

M020 betrifft NUR `coordinator.db` (laut Projektregeln: wird von Ermittlern
nur gelesen, kein Erkenntnisverlust möglich). Die Migration ist additiv
(3 neue Spalten mit Default, 1 Capability-Zeile), verlustfrei und idempotent;
`evidence_/forensic_/assets_<uid>.db` bleiben unberührt. Aufnahme in den
Datenmigrationsleitfaden nach Abnahme.

## 10. Tests (Regressionspflicht)

- `tests/test_ad_sync_plan.py` — Planner: Mengenbildung, case-insensitiv,
  leerer displayName, leere AD-Antwort ⇒ Fehler, Reaktivierungs-Kandidaten.
- `tests/test_ad_sync_executor.py` — Executor gegen In-Memory-DB mit M020:
  create (Flag+Rolle+Belege), rename (Diff alt→neu), deactivate nur mit
  exakt „Entfernen", Abbruch-Beleg, reactivate, AD_SYNC_RUN-Klammer,
  Audit-Kette intakt.
- `tests/test_m020_migration.py` — Migration: Spalten, Defaults, Idempotenz,
  verify, Capability-Seed, Bestandszeilen unverändert.
- `tests/test_ad_sync_admin.py` — CLI: preview/apply mit gemocktem Provider
  und simulierten Eingaben.
- Build 502: Endpoint-Tests (Cap-Pflicht, 403 ohne Recht, serverseitige
  Bestätigungsprüfung) + vitest für cockpit_adsync.
- Volle Python- und JS-Suite müssen grün bleiben (Baseline Build 500:
  1688 passed/54 skipped [Py 3.13.13 VM] · vitest 1032 passed/86 Dateien).
