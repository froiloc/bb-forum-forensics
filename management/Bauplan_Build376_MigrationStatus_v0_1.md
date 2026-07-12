# Bauplan Build 376 — Migrationsstand-Prüfung beim Serverstart

**Version:** 0.1 · **Datum:** 2026-07-10
**Klassifikation:** VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
**Baustelle:** 7 (Management-Interface) · **Basis:** 0.7.375 · **mc:** 2026-07-10
**Migration:** keine.

---

## 1. Anlass (echter Betriebsvorfall)

Migration **m009** (`evidence_scan_cache`, Build 374) war ausgeliefert, aber in
der produktiven `coordinator.db` **nie angewandt** — Migrationen laufen **nicht**
beim Serverstart, sondern über das eigene CLI `python -m management.migrate`.
**Der Abnahmehinweis in Build 374 war falsch.**

**Folge im Betrieb:** Der Berichts-Scan-Cache fiel aus und protokollierte je Fall
eine beiläufige Warnung (`no such table: evidence_scan_cache`).

**Wichtig:** Es ging **nichts verloren**. Der Cache ist bewusst nur ein
Beschleuniger; die Berichtsliste war vollständig. Aber der Zustand war leicht zu
übersehen.

---

## 2. Entscheidung (mc)

Der Server **migriert nicht selbst**. Das Anwenden bleibt eine **kontrollierte,
im Audit-Log belegte Handlung** (`deployed_by`). Der Server **warnt** nur — dafür
aber **deutlich**, an der sichtbarsten Stelle (Start), **unter Nennung des exakten
Befehls**.

---

## 3. Umfang (geliefert)

- **NEU `management/server/migration_status.py`** (Grundregel 10): `MigrationStatus`
  (applied/available/pending/ok/missing_registry), `MigrationStatusCheck`
  (vergleicht `schema_migrations` mit den per `discover()` gefundenen Modulen),
  `warning_lines()` — umrahmte **ACHTUNG**-Warnung mit ausstehenden Migrationen,
  Folge, **exaktem Befehl** und dem Hinweis, dass der Server bewusst nicht selbst
  migriert. `MIGRATE_COMMAND` zentral definiert.
- **`management_app.py`**: `migration_status()` (rein lesend).
- **`management.py`**: Schritt 3b — Warnung auf stderr bzw. „Migrationsstand
  aktuell (N Migrationen)". Die Prüfung verhindert nie den Start, schweigt aber
  auch nicht.
- **`reports_repo.py`**: Cache-Schreibfehler wird **einmalig** gemerkt und als
  **`cache_error`** zurückgegeben — sichtbar statt im Log verschwindend; die
  Berichtsliste bleibt vollständig.
- **`cockpit_reports.js`**: Betriebshinweis in der Sicht (nennt den Befehl,
  stellt klar, dass die Liste dennoch vollständig ist).
- **Tests**: `test_migration_status.py` (MS01–MS05, inkl. exaktem
  Produktionsfall) · `test_cockpit_reports.test.js` BR07.

---

## 4. Regression (run_tests.py)

```
pytest : 987 passed, 59 skipped, 3 subtests   (982 + 5)
vitest : 565 passed, 1 skipped, 1 todo (567), 49 Testdateien   (564 + 1)
```

---

## 5. SOFORTMASSNAHME in der VM (behebt den gemeldeten Vorfall)

```
python -m management.migrate --deployed-by h0a2898
```
Danach den Management-Server neu starten. Die Scan-Info zeigt beim zweiten Laden
**„0 neu eingelesen"** (Cache greift).

---

## 6. Abnahme dieses Builds

Server starten → bei vollständigem Stand: `[management] Migrationsstand aktuell
(N Migrationen).` Bei Rückstand die umrahmte **ACHTUNG**-Warnung mit dem Befehl.

---

## 7. Nächste Schritte

**377 — Versiegelung** (`approved_reports.db`, Inhaltshash nach der Konvention
aus `core/startup_checks.py`, **ohne** `report_comments`, `POST
/api/report/approve`, `verify`-Pfad) · **378 — Schreibsperre** im
Ermittler-Webserver bei `approved`/`final`.

---

*Dokument-Ende · Bauplan Build 376 · 2026-07-10*
