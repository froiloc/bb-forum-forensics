# Bauplan Build 408 — Journalmodus-Weiche und Umstempel-Werkzeug

**Baustelle:** 2 (Webserver) / 7 (Management) · **Version:** v0.7.408 · **Datum:** 2026-07-14
**Autoritativ:** `mc` vom 2026-07-14 · **Status:** umgesetzt, Regression grün

---

## 1. Anlass (belegt, nicht vermutet)

Der Webserver startete auf einem Testsystem nicht, dessen Datenverzeichnis auf einem Netzlaufwerk liegt:

```
File ".../db/connection_manager.py", line 203, in _open_normal
    con.execute("PRAGMA journal_mode=WAL")
sqlite3.OperationalError: disk I/O error
```

**Diagnose (`diag_sqlite_netdrive.py`, 2026-07-14, nicht-destruktiv):**

| Messpunkt | Ergebnis |
|---|---|
| Volume | `\\KK31Storage15\Volume 1\` — Windows `DriveType=4 (REMOTE)`, FS `NTFS` |
| `PRAGMA journal_mode=WAL` auf dem Share | **FEHL** — `disk I/O error`, erweiterter Code **8714** |
| `DELETE` / `TRUNCATE` / `PERSIST` auf dem Share | **OK** (Schreiben **und** Zurücklesen belegt) |
| `WAL + locking_mode=EXCLUSIVE` auf dem Share | **OK** |
| dieselbe Matrix lokal (`C:`, `DriveType=3 FIXED`) | **alles OK** |
| Header-Stempel (Byte 18/19) der Bestands-DBs | `forensic`, `evidence`, `assets`, `default`, `coordinator` = **2 (WAL)**; `templates`, `translations` = 1 |
| `mode=ro`-Lesetest der WAL-gestempelten DBs | **FEHL** (Ausnahme: `forensic_524888.db` — nur, weil zufällig eine alte `-shm` danebenlag) |

**Ursache:** kein Codefehler. SQLite hält den wal-index in Shared Memory (`-shm`, per `mmap` im DB-Verzeichnis). Shared Memory ist maschinenlokal; WAL ist auf Netzwerk-Dateisystemen daher ausdrücklich nicht unterstützt (sqlite.org/wal.html).

**Zweite, gravierendere Folge:** Der Journalmodus ist eine **persistente Eigenschaft der Datei**. WAL-gestempelte Bestands-DBs sind auf dem Share **auch lesend** nicht zu öffnen. Ein reiner Code-Fix hätte den Start nur bis zum nächsten `ATTACH` gebracht.

---

## 2. Umsetzung

### 2.1 `db/journal_policy.py` (neu)

Einzige Stelle im Projekt, die den Journalmodus setzt. Ersetzt die **14** hartkodierten `PRAGMA journal_mode=WAL`.

* `apply_journal_mode(con, db_path, schema=..., mode=..., fallback=...) -> str`
* **`auto` (Default):** WAL versuchen → bei Fehlschlag **WARNING** mit erweitertem SQLite-Fehlercode, Pfad und Klartextursache → Rückfall auf Rollback-Journal (`delete`). **Kein stiller Pfad** (Grundregel 1).
* Der tatsächlich aktive Modus wird **zurückgelesen**. Damit fällt auch der Fall auf, in dem das PRAGMA fehlerfrei durchläuft, aber nichts übernimmt (z. B. read-only geöffnete DB) — ein reines `try/except` fängt das **nicht**.
* Expliziter Modus (`wal`/`delete`/…): **kein** Rückfall, harter Abbruch mit Klartext.
* Sonderfall In-Memory-DB (`journal_mode='memory'`): erkannt, protokolliert, akzeptiert — kein Rückfall, kein Abbruch (in der Regression aufgefallen).
* `config.yaml`: `db.journal_mode: auto|wal|delete|truncate|persist`, `db.journal_mode_fallback: delete|truncate|persist`. Unzulässige Werte werden gemeldet, nicht still auf den Default gebogen.

**PROD bleibt unverändert:** Auf lokaler Platte greift WAL wie bisher, der Rückfallzweig wird nie betreten.

### 2.2 `tools/convert_journal_mode.py` (neu)

* Stempelt Bestands-DBs **in-place** um: `locking_mode=EXCLUSIVE` (kommt ohne `-shm` aus) → `journal_mode=DELETE`. Die 4,8 GB grosse `default.db` wird **nicht** über das Netz kopiert.
* **Trockenlauf ist Default**; scharf erst mit `--apply`.
* Für `forensic_<uid>.db`: **Inhalts-SHA-256 vorher/nachher** mit der Funktion des Servers (`StartupChecker._compute_content_sha256`, **kein Nachbau**). Muss identisch bleiben — das Siegel ist inhalts-, nicht dateibasiert. Bei Abweichung: Rückstempelung auf WAL, sofortiger Abbruch, keine weitere Datei.
* NTFS-Schreibschutz wird nur temporär aufgehoben und exakt wiederhergestellt. Verwaiste `-wal`/`-shm`-Reste werden entfernt und gemeldet.

### 2.3 Geänderte Dateien

`config.yaml` · `db/connection_manager.py` (4 Fundstellen, dazu Klartexthinweis bei `disk I/O error` und `JournalPolicyError → ConnectionManagerError`) · `forensic_api/support_presence.py` · `setup_coordinator_dev.py` · `management/person|rbac|cases|case_events|backup|capacity|migration_fleet/*_admin.py` · `management/migrate.py` · `management/reports/approved_reports_db.py` · `tests/test_assets_db.py` (Config-Mock verhielt sich nicht wie `ConfigLoader.get(key, default)`).

---

## 3. Tests

* `tests/test_journal_policy.py` (**+11**): WAL-Regelfall; simulierter Netzlaufwerk-Fehlschlag (`disk I/O error`) mit Rückfall **und** Protokollnachweis; nicht übernommenes PRAGMA; expliziter Modus ohne Rückfall; ATTACH-Alias `cdb`; Konfigurationsauflösung inkl. Unfug-Erkennung.
* `tests/test_convert_journal_mode.py` (**+6**): WAL-gestempelte Ausgangslage; Trockenlauf lässt Dateien **byteidentisch**; `--apply` stempelt um **und** das Siegel bleibt gültig (gegengeprüft mit `StartupChecker`); Idempotenz; Rückweg nach WAL; fehlendes Verzeichnis.
* Regression: `python run_tests.py` — pytest **1201 passed / 54 skipped**, vitest bestanden.

---

## 4. Vorgehen in der VM

```
# 1. Backup (Phase 1, VACUUM INTO) — vor jedem scharfen Lauf
# 2. Trockenlauf, Ausgabe prüfen:
python tools/convert_journal_mode.py --data-dir .\data
# 3. Scharf:
python tools/convert_journal_mode.py --data-dir .\data --apply
# 4. Start:
python main.py --mode cli --user-id 524888 --auto-port --open-browser
```

Erwartet: im Log erscheint einmalig die WARNING „WAL-Modus nicht verfügbar … Rückfall auf 'delete'". Wer das nicht bei jedem Start sehen will, setzt auf diesem System `db.journal_mode: "delete"` in der `config.yaml` — dann ist es Absicht statt Rückfall.

---

## 5. Offen (Architekturfrage, kein Bugfix)

Mehrere Rechner, die gleichzeitig **schreibend** auf **eine** `coordinator.db` auf einem SMB-Share zugreifen, sind auch im Rollback-Journalmodus **keine von SQLite unterstützte Konfiguration** (Sperren über Netzwerkspeicher). Für den Produktivbetrieb ist zu klären, ob dieser Fall auftritt; falls ja, gehört er in eine eigene Baustelle.
