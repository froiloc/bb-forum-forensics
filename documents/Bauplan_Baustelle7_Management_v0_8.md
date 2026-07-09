# Bauplan Baustelle 7 — Verwaltungs- & Administrationsoberfläche (v0.8, finalisiert)

**Stand 2026-07-08 · finalisiert nach der Planungs-/Diskussionsphase.**
Löst inhaltlich den Stand v0.7 (Build-312-Stand) ab. Autoritative Referenz für die
pro-Build-Chats. Ergänzende Dokumente: `Ideen_Verwaltungswerkzeug_konsolidiert.md`
(Cluster + Wellen), `Auftrag_Wortzaehlung_Skripte.md` (Vorarbeit).

---

## 1. Zweck & Abgrenzung

Baustelle 7 bildet die **Metaarbeit** der Ermittlung ab — **losgelöst vom
Ermittlungsinhalt** der Baustellen 3/4/6: Zuweisung von Forennutzern zu Ermittlern,
Betreuung der Ermittler, Sichtung/Abnahme der Berichte, Statistiken zur
Ressourcenplanung, Kennzahlen für Staatsanwaltschaft und Führungsebene,
Belastungsberechnung, Vorplanung.

Die Oberfläche ist **modular**: eine **Dashboard-Ansicht** für Schnellüberblick und
Schnellzugriff auf das Häufigste, plus **eigene Fachseiten** je Bereich. Hauptfokus
zuerst: die Rolle `supervisor` (Chef-Ermittlerin). Weitere Rollen werden **mitgedacht**
(höherer Vorab-Aufwand, dafür robuster) und schrittweise bedient.

**Kapselung** bleibt strikt: fallübergreifende Sichten sind die klar benannte Ausnahme
und nur mit auditiertem Freigabemodell zulässig.

---

## 2. Grundentscheidungen (festgezurrt)

1. **Modell A2 — jeder lokal.** Jede/r startet die eigene Instanz auf der lokalen
   Offline-VM, gebunden an die aufgelöste OS-Identität. Kein zentraler Netz-Server.
2. **Rollen als Daten, nicht als Flags.** Rollensatz **{supervisor, investigator,
   support, admin, lector, searchagent}**, gepflegt in `rbac_role` + Zuordnung in
   `person_role`. **Mehrfachrollen** möglich; je Rolle steht ihre Sicht zur Verfügung.
3. **RBAC als DB-Matrix** (`coordinator.db`, Migration M005), Vergabe/Rücknahme über den
   auditierten `CoordinatorWriter` (hash-verkettet). **default-deny**, **`alle` schlägt
   `eigene`**, **append-only Soft-Revoke** (kein DELETE).
4. **Nur `supervisor` startet die Vollversion;** erster Server-Build **read-only**
   (Anzeigen live), Schreib-Aktionen als Folge-Builds.
5. **Live-Aktualisierung via SSE:** Server pollt die `audit_log`-Spitze; steigt sie,
   holt der Browser die betroffene Sicht neu (kein F5). Entkoppelt vom Schreibprozess.
6. **AD-Anzeigename** als Anzeige-Attribut; der **`system_username` bleibt die stabile
   forensische Identität**. AD-Zugriff in einer gekapselten, **nur lesenden**,
   mockbaren Schicht.
7. **`integrity_check` auf Backup-Kopien** — zertifiziert das Backup und stört keinen
   Livezugriff.
8. **Kapselung robust;** fallübergreifende Sichten (Querfunde/Alias/Identität) nutzen
   die **bereits implementierten** Freigabemodelle; offen bleibt nur das stärkste
   Modell für die 🔴-Volltextsuche (Welle 3), verankert an der Rolle `searchagent`.

---

## 3. Zielarchitektur

**Eigenständiger Management-Server**, getrennt von `aiw_webserver` (Forum-Replay, B2).
- **Entry-Point `management.py`** analog `main.py`: löst beim Start die OS-Identität
  (Windows-SAMAccountName → `person`) auf, leitet daraus Rolle(n) + Policy ab, bindet
  **ausschließlich auf localhost**, öffnet den Browser automatisch. Argumente
  `--open-browser` und `--auto-port` aus `main.py` werden übernommen.
- **Read-only im ersten Build.** Rein lesender Zugriff auf `coordinator.db`; keine
  Schemaänderung durch Betrieb → migrationssicher.
- **Nebenläufigkeit (Build-325-Lehre):** keine geteilte `sqlite3.Connection` über
  Threads. Jeder Request und jeder SSE-Poll-Tick öffnet eine **kurzlebige read-only**
  Verbindung (`file:…?mode=ro`, `uri=True`) und schließt sie sofort.
- **SSE-Mechanik (entkoppelt):** `GET /events` pollt `AuditLog.tip()`; steigt die seq,
  wird `changed {tip_seq}` gesendet, dazwischen Keepalive. Der `audit_log` ist die
  einzige Wahrheitsquelle für „es gab eine Änderung" — keine Kopplung an den
  Schreibprozess. (Die B3/4-SSE-Maschinerie in `events.py` wird bewusst **nicht**
  wiederverwendet; nur ihr RFC-8895-Format wird gespiegelt.)
- **Endpunkte:** `/` (Cockpit-Shell) · `/static/<f>` (cockpit.* + wiederverwendete
  Frontends `dashboard.js`/`support_overview.js`/`workload.js`) · `/api/<sicht>` (JSON
  aus den Read-Models) · `/api/integrity` (`verify_chain`) · `/events` (SSE).
- **Cockpit-Shell:** policy-getriebene Navigation (Sichten erscheinen nur bei
  vorhandener Fähigkeit), Tabs, Datenumfang `alle`/`eigene` je Scope. Referenz-Layout:
  `AIW_Verwaltung_Mockup.html`.

**Rechtemodell — Auflösung (im Code, rein lesend):**
Rollen der Person aus `person_role` (aktiv) → Vereinigung der aktiven Grants
(`revoked_at IS NULL`) dieser Rollen → Fähigkeit gilt bei ≥1 Grant; **Scope = weitester**
(`alle` schlägt `eigene`). Fähigkeits-/Rollen-**Katalog ist im Code die Wahrheitsquelle**,
in der DB geseedet (FK-Integrität); ein Start-Check erzwingt „jede Code-Capability
existiert in der DB" (Grundregel 1: kein stiller Tippfehler-Grant).

---

## 4. Datenmodell (Migration M005, additiv — `coordinator.db` ohne Migrationslock)

> `coordinator.db` unterliegt **keinem** Migrationsvorbehalt (der gilt nur für
> `evidence_/forensic_/assets_<uid>.db`). M005 ist additiv; `migrate.py`-Lauf beim
> Deploy dennoch zwingend. Kataloge/Codes werden **im Code** validiert (additiv), FK
> sichert Integrität — Muster wie `case_events` (M004).

### 4.1 RBAC

```sql
rbac_role(code PK, label, created_at)
  -- seed: supervisor, investigator, support, admin, lector, searchagent
rbac_capability(code PK, label, description, created_at)
  -- seed: Fähigkeits-Katalog (aus Mockup abgeleitet), z. B.:
  --   dashboard.view, assignment.edit, mentoring.view, reports.review,
  --   reports.approve, stats.export_sta, workload.view, support_history.view,
  --   mycases.view, myhistory.view, policy.view, evidence.fulltext_search,
  --   feedback.moderate, capacity.edit, ops.view …
rbac_grant(
  id PK, role_code -> rbac_role, capability_code -> rbac_capability,
  scope TEXT,                 -- 'alle' | 'eigene' | NULL
  audit_seq INTEGER NOT NULL, -- Beleg im audit_log (Kopplung in derselben Transaktion)
  granted_by -> person, granted_at,
  revoked_at, revoked_by -> person, revoke_audit_seq, note)
person_role(
  id PK, person_id -> person, role_code -> rbac_role,
  assigned_by, assigned_at, revoked_at, revoked_by, audit_seq)  -- maßgeblich für RBAC
INDEX ix_rbac_grant_active(role_code, capability_code) WHERE revoked_at IS NULL
```

**Rollen-Zuschnitt (Auszug, im Seed als auditierte Grants):**
- `supervisor`: Vollzugriff, Scope `alle`; finale **StA-Freigabe** von Berichten.
- `investigator`: `mycases.view`/`myhistory.view`/`dashboard.view` mit Scope `eigene`.
- `support`: `support_history.view`/`mentoring.view` (Betreuung), Scope wie passend.
- `admin`: Plattform-Administration inkl. `feedback.moderate` (kein operativer Inhalt).
- `lector`: `reports.review` (Gegenlesen/Kommentieren vor StA-Übergabe); **finale
  Freigabe bleibt `supervisor`**, sofern nicht explizit delegiert.
- `searchagent`: `evidence.fulltext_search` (fallübergreifend, 🔴 — Recht jetzt
  modelliert, Implementierung Welle 3).

### 4.2 Kapazität (Datenbasis für Prognose/Gantt/Überlast, Welle 2)

```sql
person_worktime(
  id PK, person_id -> person,
  mon_min, tue_min, wed_min, thu_min, fri_min, sat_min, sun_min,  -- Regel-Arbeitszeit je Wochentag
  effective_from, effective_to,
  audit_seq, created_by, created_at, deleted_at)                  -- Soft-Delete, kein DELETE
holiday(
  id PK, day, label, region,                                      -- gilt für ALLE
  audit_seq, created_by, created_at, deleted_at)
availability_reason(
  code PK, label, sort, created_by, audit_seq, created_at, deleted_at)  -- Supervisor-erweiterbar
availability_entry(
  id PK, person_id -> person, period_start, period_end,
  kind TEXT,                    -- 'garantie' | 'einschraenkung'
  value_pct INTEGER, value_minutes INTEGER,  -- CHECK: genau eines != NULL
  reason_code -> availability_reason, note,
  audit_seq, created_by, created_at, updated_at, deleted_at)
```
Kapazität(Zeitraum) = Σ Arbeitstag-Minuten (Wochentag-Wert, sofern kein Feiertag)
− Einschränkungen im Rahmen der Garantien, aus der Überlappung berechnet.

---

## 5. Sichten & Module (policy-getrieben)

**Dashboard** (Landeseite): Schnellüberblick-Kacheln + Schnellzugriff; Scope-abhängig
(`alle` vs. `eigene`). **Fachseiten** (jeweils an eine Fähigkeit gebunden):
Zuweisung · Ermittler-Betreuung · Berichts-Abnahme (inkl. `lector`-Gegenlesen) ·
Statistiken (StA/Führung, ECharts) · Lastverteilung · Support-Historie · Meine
Aufträge/Historie/Berichte · Betriebs-/Systemzustand · Rechte/Policy · (später)
Kreuzbezüge, Kapazität/Planung, Feedback/Bugtracker.

**Bereits gebaut, im Cockpit nur einzubinden:** Ampel-Dashboard (Builds 316–323),
Support-Historie (330), Lastverteilung (335). **Als CLI vorhanden → werden Seiten:**
Mitarbeiter/Rollen (`investigators_admin`), Einzelfall-Zuweisung (`cases_admin`).

Tabellen durchgängig mit **Tabulator.js**, Diagramme mit **ECharts** (Rendering-
Grundlagen, früh bereitzustellen).

---

## 6. Abdeckungs-/Blinde-Flecken-Modell (Welle 2)

**Quelle** (per-Fall, read-only aggregiert): `evidence_<uid>.db.page_visits` und
`viewport_events`. **Vier Qualitätsstufen je Post:**

| Stufe | Kriterium | Wertung |
|---|---|---|
| nie gesehen | kein Sicht-Ereignis | blinder Fleck |
| flüchtig | < 2 s Verweildauer | blinder Fleck |
| gesichtet | ≥ 2 s Verweildauer | ok |
| bewertet | > 10 s **oder** Annotation gesetzt | ok (Qualität) |

**Verweildauer je Post = gekappte kumulierte Summe** der `viewport_events.visible_ms`
(Idle-/Ausreißer-Obergrenze, damit „Fenster offen" ≠ „gelesen"; Raucherpausen etc.).
**Sonderregel:** intensive Verweildauer (> 5 min) **ohne** Annotation zählt nur als
*gesichtet*, nicht *bewertet* (Anti-Pausen-Heuristik). Schwellen **konfigurierbar**.

**Nenner** (relevanz-gescopt, konfigurierbar): PN-Konversationen voll · Topics
< 20 Posts voll · große Topics = Nutzerposts + Kontextfenster (±k). Die vollständige
Post-Liste je Topic (Quell-`posts`) ist noch zu **materialisieren** (separater
Baustein). **Längen-Normierung** über Wortzahl ist optional/später; die
`word_count`-Vorarbeit läuft parallel (deutscher Zählwert aus `translations.word_count`).

**Zweckbindung (verbindlich):** Leitlinie zur Sicherung der Auswertungsqualität und
Rechtsstaatlichkeit — **kein Instrument zur Bewertung von Mitarbeitern.**

---

## 7. Plattform-Feedback / Bugtracker (Welle 3, fallinhaltsfrei)

Sichtbarkeits-**Zustandsmaschine** je Ticket:
`privat` (Inhalt nur für Ersteller + `admin`; öffentlich nur Stub „neues Thema von X,
nicht freigegeben") → `freigegeben` (nach **protokollierter** Prüfung öffentlich
einsehbar). Moderation = Rolle **`admin`**. Strikt fallinhaltsfrei (Nebenkanal-Leck
vermeiden).

---

## 8. Bau-Sequenz

**Vorarbeit (läuft parallel):** Wortzähl-Skript(e) — siehe `Auftrag_Wortzaehlung_Skripte.md`.

**Welle 0 — Fundamente (Reihenfolge zwingend, da ineinandergreifend):**

| # | Build(s) | Inhalt | Kaps./Migration |
|---|---|---|---|
| 0.1 | Refactor | `investigators → person`, `investigator_id → person_id`, Repos/FKs/Tests; alte `is_*`-Flags bleiben als kosmetische Leser | rein mechanisch, kein Migrationslock |
| 0.2 | RBAC (a) | M005-Schema + Seed (Rollen/Fähigkeiten/Initial-Grants, auditiert) | additiv |
| 0.3 | RBAC (b) | Auditierter Schreibpfad + `policy_admin`-CLI (grant/revoke, Katalog-Validierung) | — |
| 0.4 | RBAC (c) | Lese-/Durchsetzungsschicht (Auflösung, default-deny, `alle`>`eigene`) | — |
| 0.5 | Server | Management-Server-Grundgerüst (`management.py`), read-only, SSE, Cockpit-Shell mit policy-getriebener Nav | read-only |
| 0.6 | AD | AD-Integrationsschicht (nur lesend, gekapselt, mockbar): Gruppenabgleich, Anzeigename | — |
| 0.7 | Zustandsm. | Fallstatus-Workflow (erste Zustandsmaschine) | additiv |
| — | Grundlagen | ECharts + Tabulator.js bereitstellen (sobald erste Sicht sie braucht) | — |

**Welle 1–3:** gemäß `Ideen_Verwaltungswerkzeug_konsolidiert.md` (Wellen-Vorschlag),
just-in-time pro Build geplant. Kernpunkte: Welle 1 = Cockpit-Sichten der bereits
gebauten Module + Zuweisung + Meine-* + Betriebs-/Systemzustand + Wiedervorlage +
Berichts-Abnahme (provisorischer Print-to-PDF) + Textbaustein-Bibliothek. Welle 2 =
Export-Subsystem (gerichtsfester PDF), Kreuzbezüge, Abdeckung, Statistik/Prognose/Gantt
+ Kapazität, u. a. Welle 3 = Fristen-Monitor, QS/Metriken, Volltextsuche (`searchagent`),
Plattform-Feedback.

---

## 9. Arbeitsweise (verbindlich)

- **Granularität:** ein Bauplan **pro baubarer Einheit** (kleine Ideen bündeln, große
  aufteilen), **ein Chat pro Build**, überbrückt durch `UEBERGABE_*.md`-Handover
  (MD5-Fingerprints, Test-Baseline, geparkte Punkte, Start-Checkliste).
- **Zyklus je Build:** Bauplan → explizites `mc` → Implementierung → `py_compile` +
  `node --check` → Vollregression `python3 run_tests.py` → ZIP mit MD5 je Datei
  (repo-relativ) → `present_files` → Alex committet selbst.
- **Belege zuerst:** frischer Klon je Session, HEAD bestätigen (Webserver zuletzt
  **v0.7.341**), Baseline-Regression vor jeder Änderung; Build-Nummern wegen
  Parallelarbeit jeweils bestätigen.
- **Grundregeln 1–10** gelten unverändert; `build.json`-Notiz ASCII-only.
- **Read-only-Disziplin** des Servers; Schreib-Aktionen erst nach bestätigter
  Browser-Verifikation von Shell + SSE.

---

## 10. Offene Punkte & Risiken

- **Nenner-Materialisierung** (vollständige Post-Liste je gescraptem Topic) für die
  Abdeckungsanalyse — Design in Welle 2, Quelle Quell-`posts`.
- **Volltextsuche (🔴)**: rechen-/darstellungsintensiv; nur an `searchagent`; stärkstes
  Freigabemodell vor Implementierung (Welle 3).
- **Bestehende versiegelte Fälle**: `word_count` fließt erst bei regulärem Prepper-
  Neubau ins Siegel — dokumentierte Vereinfachung, blockiert Welle 0 nicht.
- **AD-Anbindung** offline testbar halten (Mock), damit CI/Dev nicht an AD hängt.
- **Refactor-Oberfläche** (`person`) ist breit; als eigener, getrennt verifizierter
  Build zuerst — nicht mit RBAC bündeln.

---

## 11. Referenzen

- `Ideen_Verwaltungswerkzeug_konsolidiert.md` — Ideen, Cluster, Wellen, Kapselungs-Ampel.
- `Auftrag_Wortzaehlung_Skripte.md` — Vorarbeit Wortzahl (parallel).
- `AIW_Verwaltung_Mockup.html` — Referenz-Layout Cockpit/Rollen-Sicht/Policy-Panel.
- `Datenmigrationsleitfaden_AIW.md` — für alle Eingriffe an versiegelten Evidence-DBs.

*Ende Bauplan v0.8. Nächster Schritt: eigener Chat für Build 0.1 (Refactor `person`),
Bauplan → `mc` → Umsetzung.*
