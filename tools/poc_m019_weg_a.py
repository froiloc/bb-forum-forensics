#!/usr/bin/env python3
# =============================================================================
# tools/poc_m019_weg_a.py — PoC Weg A (M019): user_id -> subject_id per RENAME COLUMN
# =============================================================================
# Zweck (Beleg: claude_Einstieg_Bauplan_Migration_user_id_zu_subject_id_v0_1.md §3):
#   Empirischer Nachweis auf einer KOPIE der coordinator.db, dass
#   1) PRAGMA legacy_alter_table = 0 ist,
#   2) RENAME COLUMN auf der PK-Spalte cases.user_id funktioniert,
#   3) SQLite die REFERENCES-Klauseln der 4 FK-Tabellen sowie Trigger-/View-/
#      Index-Ruempfe automatisch nachzieht,
#   4) foreign_key_check leer und integrity_check ok sind,
#   5) Zeilenzahlen und Werte vorher == nachher (verlustfrei, keine Zeilen-Kopie).
#
# Aufruf:  python3 poc_weg_a.py <pfad-zur-kopie.db> [--seed]
#   --seed: fuellt DEV-Testzeilen in alle 9 betroffenen Tabellen (NICHT auf
#           einer Produktions-Kopie verwenden; dort sind echte Daten vorhanden).
#
# Console-First, ausgabelastig (Projektregel). Arbeitet NUR auf der uebergebenen
# Datei — niemals auf der Produktions-DB selbst.
#
# EINSATZ (Datenmigrationsleitfaden §13): VOR dem scharfen M019-Lauf in der VM
# auf einer VACUUM-INTO-Kopie der Produktions-coordinator.db ausfuehren und das
# Konsolenprotokoll zu den Phase-2-Artefakten nehmen. Erwartung: "WEG A GANGBAR".
#
# Aufruf VM (Produktionskopie, OHNE --seed!):  python tools\poc_m019_weg_a.py kopie.db
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================
import sqlite3
import sys

TABLES = ("cases", "case_events", "external_matters", "investigation_results",
          "case_release", "scrape_jobs", "support_sessions",
          "evidence_scan_cache", "forum_promotion")

# Tabellen, deren eigene Spalte user_id -> subject_id umbenannt wird
# (cases zuerst: der Anker; danach FK-Kinder und eigenstaendige Spalten).
RENAME_ORDER = ("cases", "case_events", "external_matters",
                "investigation_results", "case_release",
                "scrape_jobs", "support_sessions",
                "evidence_scan_cache", "forum_promotion")

FK_CHILDREN = ("case_events", "external_matters",
               "investigation_results", "case_release")


def log(msg=""):
    print(msg, flush=True)


def seed(con):
    """DEV-Testdaten in alle 9 Tabellen (inkl. Geister-ID im Prepper-Schema)."""
    now = 1753000000
    aseq = int(con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0])
    crit = con.execute("SELECT code FROM assessment_criterion LIMIT 1").fetchone()[0]
    con.executescript("BEGIN;")
    con.execute("INSERT OR IGNORE INTO cases (user_id, username, created_at, updated_at) VALUES (18,'DEV-uid18',?,?)", (now, now))
    con.execute("INSERT OR IGNORE INTO cases (user_id, username, created_at, updated_at) VALUES (42,'DEV-uid42',?,?)", (now, now))
    con.execute("INSERT INTO case_events (user_id, event_kind, payload, created_by, created_at, audit_seq) VALUES (18,'poc','{}',1,?,?)", (now, aseq))
    con.execute("INSERT INTO case_events (user_id, event_kind, payload, created_by, created_at, audit_seq) VALUES (42,'poc','{}',1,?,?)", (now, aseq))
    con.execute("INSERT INTO external_matters (user_id, kind, betreff, angefordert_am, wiedervorlage_am, created_by, created_at, audit_seq, created_audit_seq) VALUES (18,'auskunft','PoC','2026-07-20','2026-08-01',1,?,?,?)", (now, aseq, aseq))
    con.execute("INSERT INTO investigation_results (user_id, criterion_code, extrem, confidence_code, confidence_ordinal, catalog_version, note, created_by, created_at, audit_seq) VALUES (18,?,'schwerste','verdacht',10,1,'PoC',1,?,?)", (crit, now, aseq))
    con.execute("INSERT INTO investigation_results (user_id, criterion_code, extrem, confidence_code, confidence_ordinal, catalog_version, note, created_by, created_at, audit_seq) VALUES (18,?,'schwerste','gesichert',30,1,'PoC neuer',1,?,?)", (crit, now + 10, aseq))
    con.execute("INSERT INTO case_release (user_id, recipient_kennung, recipient_display, umfang, unbedenklichkeit_grundlage, created_by, created_at, audit_seq, created_audit_seq) VALUES (18,'lka.mm','M. Mustermann','bericht','PoC-Vermerk',1,?,?,?)", (now, aseq, aseq))
    con.execute("INSERT INTO scrape_jobs (user_id, username, created_at) VALUES (42,'DEV-uid42',?)", (now,))
    con.execute("INSERT INTO support_sessions (user_id, supporter_id, started_at, last_heartbeat) VALUES (18,1,?,?)", (now, now))
    con.execute("INSERT INTO evidence_scan_cache (user_id, fingerprint, scanned_at) VALUES (18,'poc-fp',?)", (now,))
    # Geister-Kandidat im Prepper-Schema (subject_id = prefix + mat_usernames.id):
    con.execute("INSERT INTO forum_promotion (user_id, status, created_by, created_at, audit_seq, created_audit_seq) VALUES (2000000123,'gesichtet',1,?,?,?)", (now, aseq, aseq))
    con.execute("COMMIT")
    log("[seed] DEV-Testzeilen eingefuegt (inkl. Geister-ID 2000000123 in forum_promotion).")


def snapshot(con, col):
    """Zeilenzahlen + sortierte ID-Wertelisten je Tabelle."""
    snap = {}
    for t in TABLES:
        cols = [r[1] for r in con.execute("PRAGMA table_info(%s)" % t)]
        use = col if col in cols else ("subject_id" if "subject_id" in cols else col)
        n = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
        vals = [r[0] for r in con.execute("SELECT %s FROM %s ORDER BY %s" % (use, t, use))]
        snap[t] = (n, vals)
    return snap


def main():
    if len(sys.argv) < 2:
        log("Aufruf: python3 poc_weg_a.py <kopie.db> [--seed]")
        return 2
    path = sys.argv[1]
    do_seed = "--seed" in sys.argv
    con = sqlite3.connect(path)
    con.isolation_level = None

    log("=" * 78)
    log("PoC Weg A — user_id -> subject_id (RENAME COLUMN)  ·  DB: %s" % path)
    log("=" * 78)
    log("[0] sqlite_version = %s (python %s)" % (sqlite3.sqlite_version, sys.version.split()[0]))

    # --- Schritt 1: legacy_alter_table ---------------------------------------
    legacy = con.execute("PRAGMA legacy_alter_table").fetchone()[0]
    log("[1] PRAGMA legacy_alter_table = %s  -> %s" % (legacy, "OK (0 erwartet)" if legacy == 0 else "FEHLER"))
    if legacy != 0:
        return 1

    if do_seed:
        seed(con)

    # --- Vorher-Snapshot ------------------------------------------------------
    before = snapshot(con, "user_id")
    log("\n[VORHER] Zeilenzahlen:")
    for t in TABLES:
        log("    %-24s n=%-4d ids=%s" % (t, before[t][0], before[t][1]))

    # --- Schritt 2+3: RENAME COLUMN in Reihenfolge, alles in EINER Transaktion
    log("\n[2] RENAME COLUMN (eine Transaktion, foreign_keys wie Produktions-"
        "Default OFF auf dieser Verbindung):")
    con.execute("BEGIN IMMEDIATE")
    try:
        for t in RENAME_ORDER:
            con.execute("ALTER TABLE %s RENAME COLUMN user_id TO subject_id" % t)
            log("    ALTER TABLE %-22s RENAME COLUMN user_id TO subject_id  OK" % t)
        con.execute("COMMIT")
    except Exception as exc:
        con.execute("ROLLBACK")
        log("    FEHLER: %r -> ROLLBACK. Weg A NICHT gangbar." % (exc,))
        return 1

    # --- Schritt 3: Propagation pruefen (strukturell, nicht textuell) ---------
    log("\n[3] Propagation in sqlite_master (strukturell geprueft):")
    ok = True

    # 3a: Spaltennamen je Tabelle
    for t in TABLES:
        cols = [r[1] for r in con.execute("PRAGMA table_info(%s)" % t)]
        has_new = "subject_id" in cols
        has_old = "user_id" in cols
        state = "OK" if (has_new and not has_old) else "FEHLER"
        ok &= (state == "OK")
        log("    3a %-24s subject_id=%s user_id=%s  %s" % (t, has_new, has_old, state))

    # 3b: FK-Klauseln der 4 Kinder zeigen auf cases(subject_id)
    for t in FK_CHILDREN:
        fks = con.execute("PRAGMA foreign_key_list(%s)" % t).fetchall()
        hit = [(fk[2], fk[3], fk[4]) for fk in fks if fk[2] == "cases"]
        good = all(frm == "subject_id" and to == "subject_id" for (_tbl, frm, to) in hit) and hit
        ok &= bool(good)
        log("    3b %-24s FK->cases: %s  %s" % (t, hit, "OK" if good else "FEHLER"))

    # 3c: Trigger-/View-/Index-Ruempfe
    for name, typ in (("trg_investigation_results_no_update", "trigger"),
                      ("v_investigation_current", "view")):
        sql = con.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0]
        good = "subject_id" in sql and ".user_id" not in sql and "OLD.user_id" not in sql
        ok &= good
        log("    3c %-38s subject_id im Rumpf: %s  %s" % (name, "subject_id" in sql, "OK" if good else "FEHLER"))
    idx_rows = con.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall()
    for name, sql in idx_rows:
        if "subject_id" in sql or "user_id" in sql:
            good = "subject_id" in sql
            ok &= good
            log("    3c index %-32s %s" % (name, "OK (subject_id)" if good else "FEHLER (noch user_id)"))

    # 3d: KEIN Strukturbezug auf user_id mehr (Kommentare in DDL ausgenommen)
    resid = []
    for t in TABLES:
        if "user_id" in [r[1] for r in con.execute("PRAGMA table_info(%s)" % t)]:
            resid.append(t)
    log("    3d Rest-Spalten 'user_id': %s  %s" % (resid or "keine", "OK" if not resid else "FEHLER"))
    ok &= not resid

    # --- Schritt 4: Integritaet ----------------------------------------------
    con.execute("PRAGMA foreign_keys=ON")
    fkc = con.execute("PRAGMA foreign_key_check").fetchall()
    log("\n[4] PRAGMA foreign_key_check: %s  %s" % (fkc or "leer", "OK" if not fkc else "FEHLER"))
    ok &= not fkc
    ic = con.execute("PRAGMA integrity_check").fetchone()[0]
    log("[4] PRAGMA integrity_check: %s  %s" % (ic, "OK" if ic == "ok" else "FEHLER"))
    ok &= (ic == "ok")

    # --- Schritt 5: Zeilenzahlen + Werte vorher == nachher --------------------
    after = snapshot(con, "subject_id")
    log("\n[5] Zeilenzahlen/Werte vorher == nachher:")
    for t in TABLES:
        same = before[t] == after[t]
        ok &= same
        log("    %-24s n: %d -> %d  werte gleich: %s  %s"
            % (t, before[t][0], after[t][0], same, "OK" if same else "FEHLER"))

    # --- Zusatz A: Append-only-Trigger funktioniert noch ----------------------
    # WICHTIG: Produktionsverbindungen laufen mit foreign_keys=OFF (SQLite-
    # Default; Beleg: m002_cases.py Kopfkommentar, kein Code setzt ON). Die
    # Beleg-Kopplung audit_seq=0 -> seq SETZT DAS VORAUS (seq 0 existiert nicht
    # in audit_log). Der Funktionstest spiegelt daher den Produktionszustand.
    con.execute("PRAGMA foreign_keys=OFF")
    log("\n[A] Funktionstest Append-only-Trigger (investigation_results, foreign_keys=OFF wie Produktion):")
    n_res = con.execute("SELECT COUNT(*) FROM investigation_results").fetchone()[0]
    if n_res:
        rid = con.execute("SELECT MIN(id) FROM investigation_results").fetchone()[0]
        try:
            con.execute("UPDATE investigation_results SET note='hack' WHERE id=?", (rid,))
            log("    illegaler UPDATE ging DURCH -> FEHLER"); ok = False
        except sqlite3.IntegrityError as exc:
            log("    illegaler UPDATE abgewiesen: OK (%s...)" % str(exc)[:60])
        try:
            con.execute("DELETE FROM investigation_results WHERE id=?", (rid,))
            log("    DELETE ging DURCH -> FEHLER"); ok = False
        except sqlite3.IntegrityError:
            log("    DELETE abgewiesen: OK")
        # Legaler Pfad audit_seq 0 -> seq (Sonderausnahme) in einer Transaktion:
        con.execute("BEGIN")
        try:
            crit = con.execute("SELECT criterion_code FROM investigation_results LIMIT 1").fetchone()[0]
            aseq = int(con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0])
            cur = con.execute(
                "INSERT INTO investigation_results (subject_id, criterion_code, extrem,"
                " confidence_code, confidence_ordinal, catalog_version, note, created_at, audit_seq)"
                " VALUES (18, ?, 'beste', 'verdacht', 10, 1, 'trigger-poc', 1753000001, 0)", (crit,))
            con.execute("UPDATE investigation_results SET audit_seq=? WHERE id=?", (aseq, cur.lastrowid))
            log("    legale Beleg-Kopplung 0 -> %d: OK" % aseq)
            con.execute("ROLLBACK")  # PoC hinterlaesst nichts
        except Exception as exc:
            con.execute("ROLLBACK")
            log("    legale Beleg-Kopplung FEHLGESCHLAGEN: %r -> FEHLER" % (exc,)); ok = False
    else:
        log("    (keine Zeilen vorhanden — Funktionstest uebersprungen)")

    # --- Zusatz B: View liefert ----------------------------------------------
    v = con.execute("SELECT COUNT(*) FROM v_investigation_current").fetchall()
    log("[B] v_investigation_current SELECT: OK (%s Zeile(n))" % v[0][0])

    log("\n" + "=" * 78)
    log("ERGEBNIS: %s" % ("WEG A GANGBAR — alle Pruefungen bestanden." if ok else "WEG A DURCHGEFALLEN — Weg B (Rebuild) erforderlich."))
    log("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
