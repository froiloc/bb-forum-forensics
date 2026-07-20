# Bauplan Build 468 — AP-2A(1): Katalog identifizierter Personen (Backend)

**Version:** 0.1 · **Datum:** 2026-07-20 · **Modul:** `aiw_webserver`
**Basis-Commit:** `2b419be` (Version 0.7.467) · **Buildnummer:** 468 (reserviert durch mc)
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Freigabe:** mc 2026-07-20 (Klärungen #1–#3 aufgelöst, MD5-Handshake bestätigt)

---

## 1. Einordnung

Erster Baustein des **Kreuzbezugs-/Identitäts-Blocks** (AP-2A, Ideen 6–11), des
letzten verbliebenen Welle-2-Pakets. Er legt die Datenhaltung + das auditierte
Repo für den **globalen Katalog identifizierter Personen** an (Ideen 9/10) — den
Kern des Projektziels „Forenkonten realen Personen zuordnen".

**Belegte Reconciliation vorab (Grundregel 1, „messen, nicht rechnen"):** Die
Ideen-Doc-Aussage, F5-Systeme seien „bereits implementiert", hält der
Code-Prüfung **nicht** stand. Auf Management-Ebene existierte kein
Identitäts-/Alias-/Querfund-Register (`querfund`/`kreuzbezug`/`cross_ref` = 0
Treffer; höchste Migration M017). Auf `forensic_api`-Ebene bestehen pro Fall
`aliases.py` (Ermittler-Suchbegriffe) und `cross_annotation_integrator.py`
(Transport von Fremd-Annotationen) — **andere Konzepte**; die späteren AP-2A-
Builds (Alias-Katalog, Querfunde) setzen darauf auf statt zu duplizieren.

## 2. Schnitt (Backend-only)

Kleinster eigenständig testbarer Baustein: **Migration + Repo + Tests**.
Endpunkte und Cockpit-Sicht folgen in Folge-Builds (bewährtes Muster
Backend/Frontend getrennt, Vorlage Onboarding 464→465).

## 3. Gelieferte Artefakte

**Neu**
- `management/migrations/coordinator/m018_identified_subject.py` — Migration
  **M018** (additiv, `coordinator.db`): Tabelle `identified_subject`, Index
  `ix_identified_subject_confidence`, RBAC-Seed `crossref.view`/`crossref.edit`
  (literal, m005-Prinzip). Idempotent; Inline-Verifikation → `raise` → ROLLBACK.
- `management/crossref/__init__.py` — Paket-Init.
- `management/crossref/identified_subject_repo.py` — `IdentifiedSubjectRepo`
  (`list`/`get`/`upsert`), Schreiben ausschließlich über
  `CoordinatorWriter.audited_write`.
- `tests/test_migration_m018_identified_subject.py` — IM01–IM05.
- `tests/test_identified_subject_repo.py` — IR01–IR07.

**Geändert**
- `management/audit/event_types.py` — neuer Ereignistyp `SUBJECT_IDENTITY_SET`
  (Konstante + `ALL`-Frozenset).
- `management/rbac/catalog.py` — `crossref.view`/`crossref.edit` (28 → 30).
- `tests/test_management_rbac_schema.py` — R02: 28 → 30 + `assertIn`.
- `tests/test_management_dashboard.py` — D01: Migrationsliste …17 → …17,18.
- `tests/test_demo_seed.py` — DS01: Fähigkeitszahl 28 → 30 (durch Regression
  aufgedeckt; nicht in der Übergabe-Liste, aber additiv nachgezogen).
- `build.json` — Bump auf 468 (ASCII-only verifiziert).

## 4. Forensische Festlegungen (mc 2026-07-20)

- **Schlüssel `subject_id`** nach Prepper-Schema (Realnutzer `== users.id`;
  Geist `== prefix + mat_usernames.id`, Beleg: Entscheidung SubjectID/
  Geisternutzer 2026-07-20). **Kein FK auf `cases`** — sonst fielen die
  552.334 Geister still heraus (Grundregel-1-Verstoß). Für Realnutzer joint
  `subject_id` heute schon auf `cases.user_id`.
- **Greenfield, keine Datenmigration.** Die globale `user_id`→`subject_id`-
  Umstellung (Blast-Radius: 9 coordinator-Migrationen, 4 FK-Tabellen auf
  `cases(user_id)`-PK, 86 Nicht-Test-`.py`) ist ein **eigener Folge-Build** mit
  Eintrag im `Datenmigrationsleitfaden_AIW.md`. Die versiegelten Paket-DBs
  bleiben unberührt (für Realnutzer `subject_id == user_id`).
- **Konfidenz — Achse 1** (erkenntnisbezogen), CHECK-geschlossen:
  `verdacht`(10) < `wahrscheinlich`(20) < `gesichert`(30). `gesichert` statt
  `gerichtsfest`, um Sicherheit nicht mit Verwertbarkeit zu vermischen (mc).
  `confidence_ordinal` im Repo eingefroren (Muster m011).
- **Aktualisierbar, jede Änderung auditiert** (Konfidenz reift belegt); No-Op
  wirft. **Ein Ereignistyp** `subject_identity_set`, `created`-Flag atomar im
  Payload (race-frei; Muster Onboarding).
- **Sensibilitätsregel (streng):** `real_identity`/`basis`/`note` (PII) stehen
  **nie** im audit_log-Payload — nur Fakten + Textlängen. Härtester Test (IR01):
  kein sensibler Klartext im rohen Beleg.

## 5. Zurückgestellt (juristische Rückkopplung)

**Achse 2 — Verwertbarkeit** (`verwertbar`/`teilverwertbar`/`Verwertungsverbot`/
`Quellenschutz`, Zufalls-/Querfunde §108 StPO) ist eine rechtliche Wertung und
wird erst nach StA-Abstimmung **additiv** nachgerüstet (append-fähige Tabelle +
audit_log erlauben das verlustfrei). Fragenkatalog für die StA liegt separat vor
(`claude_Fragenkatalog_StAin_Verwertbarkeit_Konfidenz_v0_1.md`). Eintrag in
`claude_Wiedervorlage_offene_Punkte.md` folgt.

## 6. Verifikation

- `py_compile` (`-W error::SyntaxWarning`) über `management/ tests/ core/ server/
  forensic_api/` — RC 0.
- **Python (pytest, `test_editor_renderer.py` ausgeklammert):** 1568 passed /
  49 skipped / 6 subtests passed (Baseline 1556 + 12 neue Tests).
- **JavaScript (vitest):** 897 passed / 1 skip / 1 todo (unverändert; kein JS
  geändert).

## 7. Offene Grants (default-deny, operativ durch mc)

`crossref.view`/`crossref.edit` sind **nicht** im Build gegrantet. Vergabe an die
ermittelnden Rollen ist operative Entscheidung der Chef-Ermittlerin.

## 8. Nächster Schritt (Vorschlag)

Fokus laut mc: die globale **`user_id`→`subject_id`-Umstellung** als eigener
Build mit Leitfaden-Eintrag (vor weiteren AP-2A-Features). Danach AP-2A(2):
Endpunkte + Cockpit-Sicht „Kreuzbezug" für `identified_subject`.

---
*Dokument-Ende · Bauplan Build 468 · v0.1 · 2026-07-20*
