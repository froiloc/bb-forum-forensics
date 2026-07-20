# Einstiegs-Bauplan — Globale Schlüsselumstellung `user_id` → `subject_id` (coordinator.db)

**Version:** 0.1 · **Datum:** 2026-07-20 · **Modul:** `aiw_webserver`
**Autor-Entwurf:** Claude (AP-2A-Chat), zur Übernahme durch einen **frischen, fokussierten Chat**
**Klassifikation:** VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
**Status:** Entwurf/Einstieg. Der neue Chat setzt **Plan → mc → Umsetzung** fort; Code erst nach `mc`.

> **⚠ Erste Pflicht des neuen Chats: NEU MESSEN.** Dieser Bauplan beruht auf dem Stand
> **nach Build 468** (HEAD `2b419be` + m018). Parallel läuft eine Fehlerbehebung und der
> 468-Commit; der frische Chat startet daher von einem **späteren HEAD**. Vor jeder Zeile
> Code: Repo frisch klonen, HEAD bestätigen, die unten genannten Tabellen/DDLs/Trigger/
> Indizes **selbst nachgreppen** (belegte Reconciliation, Grundregel „messen, nicht rechnen").
> Diese Datei ist Startpunkt, nicht Wahrheit.

---

## 1. Auftrag & bereits getroffene Entscheidungen

Globale Umstellung des Ermittlungsschlüssels von `user_id` auf **`subject_id`** (Prepper-Schema:
Realnutzer `subject_id == users.id`; Geist `subject_id == prefix + mat_usernames.id`, Beleg:
`claude_Entscheidung_SubjectID_Schema_Geisternutzer_2026-07-20.md`). Ziel: die Geister
(552.334 Namen ohne Konto) werden im gesamten Werkzeug schlüsselfähig; die Rückwärts-
kompatibilität im Code entfällt (mc 2026-07-20).

**Fixe Entscheidungen (mc):**
- Diese Migration ist ein **eigener, fokussierter Vorgang** (dieser Chat), getrennt von AP-2A.
- **Vor** den weiteren AP-2A-Features durchführen, damit Endpunkte/Sicht/Alias/Querfunde gleich
  `subject_id`-nativ entstehen.
- **`identified_subject` (m018, Build 468) ist bereits `subject_id`-nativ** (greenfield, kein
  `cases`-FK) — es braucht in dieser Migration **keine** Änderung. Als Positiv-Beispiel prüfen.

## 2. Gemessener Blast-Radius (Stand nach 468 — im neuen Chat verifizieren)

**Anker (PK, umzubenennen):**
- `cases.user_id` **PRIMARY KEY** → `subject_id` (m002; 1:1 zum Fall, autoritativ).

**FK auf `cases(user_id)` (4 — hängen am Anker):**
- `case_events` (m004) · `external_matters` (m010) · `case_release` (m016)
- `investigation_results` (m011) — **Sonderfall:** trägt zwei **Append-only-Trigger**
  (`trg_investigation_results_no_update/_no_delete`, Rumpf referenziert `NEW/OLD.user_id`
  inkl. der Sonderausnahme „audit_seq 0→seq"), eine **View** und einen **Index** über `user_id`.

**Eigenständige `user_id`-Spalten (4 — kein cases-FK):**
- `scrape_jobs` (m002, indiziert) · `support_sessions` (m003, indiziert)
- `evidence_scan_cache` (m009, **PK**) · `forum_promotion` (m015, `UNIQUE`, bewusst **ohne**
  cases-FK).

**Nur Kommentar-Treffer (voraussichtlich keine Spalte — verifizieren):** `mentoring_notes` (m012).

**Code:** 86 Nicht-Test-`.py` referenzieren `user_id` (die meisten als lokale Variablen/Parameter;
maßgeblich sind die, die **SQL auf die umbenannten Spalten** absetzen). Dazu Datei-/CLI-Namen
(`--user-id`, JSON-Keys, `evidence_<uid>.db`-Pfadschema).

**Nicht betroffen (Entwarnung):** Die versiegelten Paket-DBs `evidence_/forensic_/assets_<uid>.db`
brauchen **keine** Migration — für Realnutzer gilt `subject_id == user_id`, Inhalt und Dateinamen
sind bereits korrekt; Geister-Pakete existieren noch nicht. Der **Migrationsvorbehalt** wird also
im Kern **nicht** ausgelöst. Betroffen ist im Wesentlichen `coordinator.db` (Schema) + der Code.

## 3. Strategie — zwei Wege, A zuerst empirisch prüfen

### Weg A (bevorzugt): `ALTER TABLE … RENAME COLUMN` — verlustfrei, ohne Zeilen-Kopie
SQLite ≥ 3.25 mit `legacy_alter_table=OFF` zieht bei `RENAME` **FK-Klauseln anderer Tabellen
sowie Trigger-/View-Rümpfe automatisch nach** (genau dieser Mechanismus trägt m005:
`investigators`→`person`). Wenn das auch für die **PK-Spalte** `cases.user_id` gilt und in die
vier FK-Referenzen propagiert, schrumpft die Migration auf ~9 `RENAME COLUMN` + Index-Umbenennung
— **keine Zeile wird kopiert**, das Risiko eines Datenverlusts ist konstruktiv null.

**Zwingende Verifikation zuerst (PoC auf einer KOPIE der Produktions-`coordinator.db`):**
1. `PRAGMA legacy_alter_table` = 0 bestätigen.
2. `ALTER TABLE cases RENAME COLUMN user_id TO subject_id;` — geht auf einer **PK-Spalte**?
3. Danach in `sqlite_master` prüfen: Wurden die `REFERENCES cases(user_id)` der vier FK-Tabellen
   automatisch zu `cases(subject_id)`? Wurden m011-**Trigger/View/Index** mitgezogen?
4. `PRAGMA foreign_key_check;` **leer**; `PRAGMA integrity_check;` = ok.
5. Zeilenzahlen je Tabelle vorher==nachher; Stichprobe: `subject_id`-Werte == alte `user_id`-Werte.

Fällt einer der Punkte 2–4 durch → **Weg B**.

### Weg B (Fallback): vollständiger Tabellen-Rebuild in Abhängigkeitsreihenfolge
`PRAGMA foreign_keys=OFF` → `cases` rebuilden (`subject_id` PK, `assigned_to REFERENCES person(id)`
— m005 hat die FK-Referenz live schon auf `person` gezogen, im Rebuild explizit so schreiben) →
die 4 FK-Tabellen rebuilden (`REFERENCES cases(subject_id)`, m011-Trigger/View/Index **mit
`subject_id` neu** anlegen, Append-only-Schutz erhalten) → je Rebuild `INSERT … SELECT`
(`user_id`→`subject_id`), `precount==postcount` verifizieren → `foreign_key_check` leer.
Die 4 eigenständigen Spalten in beiden Wegen per `RENAME COLUMN`.

## 4. Code-Sweep (der größere, sorgfältige Teil)
Nach der Spaltenumbenennung brechen alle SQL-Strings, die die umbenannten Spalten adressieren.
- Repos/Module mit SQL auf `cases`/`case_events`/`external_matters`/`investigation_results`/
  `case_release`/`scrape_jobs`/`support_sessions`/`evidence_scan_cache`/`forum_promotion`
  systematisch nachziehen (grep-getrieben, je Datei verifizieren).
- **Klärung für den neuen Chat:** externe Benennung (`--user-id`, JSON-Keys, `<uid>`-Dateinamen)
  **mitumbenennen** (voll `subject_id`-nativ) ODER als Kompatibilitäts-Label `user_id` außen
  behalten, intern `subject_id`? Empfehlung: intern konsequent `subject_id`; außen bewusst
  entscheiden (CLI-Gewohnheit der Ermittler).

## 5. Produktivbetrieb & Leitfaden (verbindlich)
- `coordinator.db` trägt **seit 01.07. Produktivdaten** (cases, audit_log, results …). Auch wenn
  kein Migrationsvorbehalt greift: **aufwändigeres Test-/Verifikationsvorgehen** einplanen.
- **`Datenmigrationsleitfaden_AIW.md`** um diesen Vorgang ergänzen: Vorher-Backup, Weg-A-PoC-
  Protokoll, Roll-forward-Schritte, Verifikations-Checkliste (Zeilenzahlen, `foreign_key_check`,
  `integrity_check`, Audit-Ketten-`verify_chain`), Rollback-Pfad.
- Migration erhält die **nächste freie Nummer** zur Bauzeit (voraussichtlich M019 — prüfen).
  Erwägen: ein **einmaliger Audit-Beleg** „Schlüsselschema user_id→subject_id angewandt
  (scheme_version)" analog `mat_subject_map_meta` des Preppers.

## 6. Verifikations-Gate (wie immer, hier verschärft)
`py_compile -W error::SyntaxWarning` über den Baum · volle Regression grün
(`python run_tests.py`; Cloud: `test_editor_renderer.py` ausklammern) · dabei **die
Migrations-/Repo-Tests, die heute `user_id` festnageln, additiv nachziehen** (die Test-Fixtures
in `tests/` bauen `coordinator.db` frisch — sie brechen bei Spaltenumbenennung und sind der beste
Frühwarnindikator). ZIP mit `aiw_webserver/`-Präfix + `MD5SUMS_BuildNNN.txt` · **MD5-Handshake
der In-Use-Dateien vorab** · Commits macht mc (PAT read-only).

## 7. Empfohlene Schritt-Reihenfolge im neuen Chat
1. Frisch klonen, HEAD bestätigen, Blast-Radius **neu messen** (§2 verifizieren).
2. **Weg-A-PoC** auf einer Kopie der Produktions-`coordinator.db` (§3) — Console-First,
   ausgabelastig, Ergebnis an mc.
3. Bauplan (A oder B) + Leitfaden-Entwurf → `mc` → Migration bauen (ein atomarer Vorgang).
4. Code-Sweep in separaten, testgedeckten Builds (Backend-Muster).
5. Volle Verifikation, Leitfaden finalisieren, ZIP/Handshake, Commit durch mc.

---
*Dokument-Ende · Einstiegs-Bauplan Schlüsselumstellung · v0.1 · 2026-07-20 · zur mc-Freigabe im neuen Chat*
