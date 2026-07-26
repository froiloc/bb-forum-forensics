# =============================================================================
# tests/test_uid_stats_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Zuweisung (Build 533)
# =============================================================================
# Testsuite fuer management/stats/uid_stats_repo.py und den Endpunkt
# GET /api/assignable/stats.
#
# US01 — liest uid_stats: computed/reported/discrepancy kommen VOLLSTAENDIG an.
# US02 — fehlende forensic_<uid>.db: Befund 'ohne_forensic_db', KEINE Werte.
#        Das ist der wichtigste Test der Datei: eine fehlende Datei darf nie
#        wie '0 Beitraege' aussehen (Grundregel 1).
# US03 — Datei ohne Tabelle uid_stats -> 'ohne_uid_stats'.
# US04 — Tabelle vorhanden, aber leer -> 'ohne_kennzahlen' (nicht 'gelesen').
# US05 — unlesbare Datei -> 'nicht_lesbar', mit Grund; kein Absturz.
# US06 — Katalog: sortiert, zaehlt Faelle je Kennzahl; 'vorgeschlagen' enthaelt
#        nur Schluessel, die es WIRKLICH gibt.
# US07 — Zwischenspeicher: zweiter Abruf ohne Dateizugriff, ABER geaenderte
#        Datei wird neu gelesen (Fingerabdruck).
# US08 — Endpunkt: 200 mit Recht, 403 ohne; JEDER Fall steht in 'stats'.
# US09 — leere Auswahl bedeutet KEINE Faelle (nicht 'alle').
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac.rbac_repo import RbacRepo
from management.server.management_app import ManagementApp
from management.stats.uid_stats_repo import (
    BEFUNDE,
    UidStatsRepo,
    cache_leeren,
    read_uid_stats,
    read_uid_stats_cached,
)

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""

#: Das DDL der echten Tabelle, woertlich aus forensic_uid.db.schema.sql:396-402.
#  Die Testvorrichtung baut die Tabelle NICHT nach eigenem Gutduenken — genau
#  das war der Fehler, der in Build 527/528 zu einer falsch belegten Aussage
#  ueber 'uid_posts.posted' gefuehrt hat.
_UID_STATS_DDL = """
CREATE TABLE IF NOT EXISTS "uid_stats" (
	"stat_key"	TEXT NOT NULL,
	"val_reported"	INTEGER,
	"val_computed"	INTEGER,
	"discrepancy"	INTEGER,
	PRIMARY KEY("stat_key")
)
"""


def _make_forensic(path, rows):
    """Legt eine forensic_<uid>.db mit uid_stats und den gegebenen Zeilen an."""
    con = sqlite3.connect(str(path))
    try:
        con.execute(_UID_STATS_DDL)
        con.executemany(
            "INSERT INTO uid_stats (stat_key, val_reported, val_computed, "
            "discrepancy) VALUES (?,?,?,?)", rows)
        con.commit()
    finally:
        con.close()


class UidStatsRepoTests(unittest.TestCase):

    def setUp(self):
        cache_leeren()          # Testfolgen duerfen sich nicht beeinflussen
        self._tmp = tempfile.mkdtemp()
        self._forensic = Path(self._tmp) / "forensic"
        self._forensic.mkdir()
        self._db = os.path.join(self._tmp, "coordinator.db")

        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1,'h0a2898','Chefin',1,1,0,?)", (int(time.time()),))
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (3,'h003','Support',0,0,1,?)", (int(time.time()),))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.writer = CoordinatorWriter(con, AuditLog(con))
        self.rbac = RbacRepo(con, self.writer)
        self.rbac.grant("supervisor", "assignment.edit", scope="alle",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        cases = CasesRepo(con, self.writer)
        for uid in (18, 19, 20):
            cases.create_case(uid, "b%d" % uid, actor_id=1)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        # Fall 18: vollstaendig. Fall 19: Datei fehlt (bewusst).
        # Fall 20: Datei da, aber ohne uid_stats.
        _make_forensic(self._forensic / "forensic_18.db", [
            ("posts_total", 130, 123, 7),
            ("downloads_total", None, 4, None),
            ("shares_total", 2, 2, 0),
        ])
        con2 = sqlite3.connect(str(self._forensic / "forensic_20.db"))
        con2.execute("CREATE TABLE irgendwas (a INTEGER)")
        con2.commit()
        con2.close()

    def tearDown(self):
        cache_leeren()
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _repo(self):
        return UidStatsRepo(self.con, self._forensic)

    # US01 -------------------------------------------------------------------
    def test_us01_liest_kennzahlen_vollstaendig(self):
        s = read_uid_stats(self._forensic / "forensic_18.db", 18)
        self.assertEqual(s.befund, "gelesen")
        self.assertEqual(s.werte["posts_total"],
                         {"c": 123, "r": 130, "d": 7})
        # NULL bleibt None und wird NICHT zu 0 — der Unterschied zwischen
        # 'nicht ausgewiesen' und 'null' ist selbst eine Information.
        self.assertEqual(s.werte["downloads_total"],
                         {"c": 4, "r": None, "d": None})
        self.assertEqual(len(s.werte), 3)

    # US02 -------------------------------------------------------------------
    def test_us02_fehlende_datei_liefert_keine_nullen(self):
        s = read_uid_stats(self._forensic / "forensic_19.db", 19)
        self.assertEqual(s.befund, "ohne_forensic_db")
        # Der Kern: KEINE Werte. Eine 0 saehe aus wie eine Feststellung.
        self.assertEqual(s.werte, {})
        self.assertIn("forensic_19.db", s.detail)
        self.assertIn(s.befund, BEFUNDE)

    # US03 -------------------------------------------------------------------
    def test_us03_datei_ohne_uid_stats(self):
        s = read_uid_stats(self._forensic / "forensic_20.db", 20)
        self.assertEqual(s.befund, "ohne_uid_stats")
        self.assertEqual(s.werte, {})

    # US04 -------------------------------------------------------------------
    def test_us04_leere_tabelle_ist_nicht_gelesen(self):
        pfad = self._forensic / "forensic_77.db"
        _make_forensic(pfad, [])
        s = read_uid_stats(pfad, 77)
        self.assertEqual(s.befund, "ohne_kennzahlen")
        self.assertEqual(s.werte, {})

    # US05 -------------------------------------------------------------------
    def test_us05_unlesbare_datei(self):
        pfad = self._forensic / "forensic_78.db"
        pfad.write_bytes(b"das ist ganz sicher keine SQLite-Datei")
        s = read_uid_stats(pfad, 78)
        # DIESER TEST HAT EINEN ECHTEN FEHLER GEFUNDEN (2026-07-26):
        # sqlite3.connect() oeffnet die Datei nicht, es merkt sich nur den
        # Pfad — 'file is not a database' faellt erst bei der ERSTEN ABFRAGE
        # an. Der erste Entwurf liess die Ausnahme durch und haette die
        # Kennzahlen ALLER Faelle mit einem 500 beendet. Die Zusicherung ist
        # deshalb: BENANNTER Befund, kein Wurf.
        self.assertIn(s.befund, ("nicht_lesbar", "ohne_uid_stats",
                                 "tabelle_unlesbar"))
        self.assertEqual(s.werte, {})
        self.assertTrue(s.detail)

    # US06 -------------------------------------------------------------------
    def test_us06_katalog_und_vorschlag(self):
        _make_forensic(self._forensic / "forensic_19.db", [
            ("posts_total", None, 9, None),
            ("pm_posts_total", None, 5, None),
        ])
        cache_leeren()
        report = self._repo().collect()
        d = report.to_dict()

        katalog = {e["key"]: e["faelle"] for e in d["katalog"]}
        self.assertEqual(katalog["posts_total"], 2)      # Fall 18 und 19
        self.assertEqual(katalog["pm_posts_total"], 1)   # nur Fall 19
        # Sortiert — eine Spaltenauswahl, die bei jedem Abruf anders sortiert
        # ist, waere genau die Unruhe, die diese Ueberarbeitung beseitigt.
        self.assertEqual([e["key"] for e in d["katalog"]],
                         sorted(katalog.keys()))
        # 'vorgeschlagen' nennt nur, was es gibt: downloads_total und
        # shares_total sind da, pm_posts_total auch — warnings_total nicht.
        self.assertIn("posts_total", d["vorgeschlagen"])
        self.assertIn("pm_posts_total", d["vorgeschlagen"])
        self.assertNotIn("warnings_total", d["vorgeschlagen"])
        # Befundzaehlung: Fall 20 hat keine uid_stats.
        self.assertEqual(d["befund_zaehler"]["gelesen"], 2)
        self.assertEqual(d["befund_zaehler"]["ohne_uid_stats"], 1)
        # Und der Fall steht EINZELN in 'probleme' (nicht nur als Zahl).
        self.assertEqual([p["subject_id"] for p in d["probleme"]], [20])

    # US07 -------------------------------------------------------------------
    def test_us07_zwischenspeicher_und_fingerabdruck(self):
        pfad = self._forensic / "forensic_18.db"
        erst = read_uid_stats_cached(pfad, 18)
        self.assertEqual(erst.werte["posts_total"]["c"], 123)

        # Datei aendern -> der Fingerabdruck aendert sich -> neu lesen.
        con = sqlite3.connect(str(pfad))
        con.execute("UPDATE uid_stats SET val_computed=999 "
                    "WHERE stat_key='posts_total'")
        con.commit()
        con.close()
        # mtime sicher verschieben (manche Dateisysteme haben grobe Aufloesung)
        st = pfad.stat()
        os.utime(pfad, (st.st_atime + 5, st.st_mtime + 5))

        neu = read_uid_stats_cached(pfad, 18)
        self.assertEqual(neu.werte["posts_total"]["c"], 999)

        # Ohne Aenderung liefert der Speicher DASSELBE Objekt (kein Neulesen).
        nochmal = read_uid_stats_cached(pfad, 18)
        self.assertIs(nochmal, neu)

    # US08 -------------------------------------------------------------------
    def test_us08_endpunkt(self):
        app = ManagementApp(self._db, forensic_dir=str(self._forensic))
        r = app.dispatch(1, "/api/assignable/stats")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))

        # JEDER Fall steht in 'stats' — auch die ohne Werte (Grundregel 1).
        self.assertEqual(sorted(d["stats"].keys()), ["18", "19", "20"])
        self.assertEqual(d["stats"]["18"]["werte"]["posts_total"]["c"], 123)
        self.assertEqual(d["stats"]["19"]["befund"], "ohne_forensic_db")
        self.assertEqual(d["stats"]["19"]["werte"], {})
        self.assertEqual(d["forensic_dir"], str(self._forensic))
        self.assertEqual(set(d["befunde"]), set(BEFUNDE))

        # force=1 liest neu und liefert dasselbe Bild.
        r2 = app.dispatch(1, "/api/assignable/stats", {"force": ["1"]})
        self.assertEqual(r2.status, 200)
        d2 = json.loads(r2.body.decode("utf-8"))
        self.assertEqual(d2["stats"]["18"]["werte"],
                         d["stats"]["18"]["werte"])

        # Ohne assignment.edit -> 403 (dieselbe Huerde wie /api/assignable).
        self.assertEqual(app.dispatch(3, "/api/assignable/stats").status, 403)

    # US09 -------------------------------------------------------------------
    def test_us09_leere_auswahl_ist_keine_auswahl(self):
        report = self._repo().collect(subject_ids=[])
        self.assertEqual(report.faelle, ())
        report_alle = self._repo().collect(subject_ids=None)
        self.assertEqual(len(report_alle.faelle), 3)

    # US10 -------------------------------------------------------------------
    def test_us10_angefragte_kennung_ausserhalb_der_fallakte(self):
        """
        Die Sicht 'Fall-Erkennung' zeigt forensic_<uid>.db, die NOCH NICHT in
        der Fallakte stehen. Genau fuer die braucht man die Kennzahlen, um
        ueber die Aufnahme zu entscheiden. Der erste Entwurf hat solche
        Kennungen still weggefiltert — dieser Test haelt die Korrektur fest.
        """
        # 4711 ist in KEINER Fallakte; die Datei liegt aber auf der Platte.
        _make_forensic(self._forensic / "forensic_4711.db",
                       [("posts_total", None, 42, None)])
        report = self._repo().collect(subject_ids=[4711, 18])
        d = report.to_dict()
        self.assertEqual(sorted(d["stats"].keys()), ["18", "4711"])
        self.assertEqual(d["stats"]["4711"]["werte"]["posts_total"]["c"], 42)

        # ... und ueber den Endpunkt, so wie die Sicht es aufruft.
        app = ManagementApp(self._db, forensic_dir=str(self._forensic))
        r = app.dispatch(1, "/api/assignable/stats",
                         {"subject_ids": ["4711,18"]})
        self.assertEqual(r.status, 200)
        self.assertEqual(
            json.loads(r.body.decode("utf-8"))["stats"]["4711"]["befund"],
            "gelesen")

        # Eine unlesbare Kennung fuehrt zu 400 — NICHT zu einer stillen
        # Teil-Liste, die vollstaendig aussieht.
        self.assertEqual(app.dispatch(
            1, "/api/assignable/stats",
            {"subject_ids": ["18,pfui"]}).status, 400)


if __name__ == "__main__":
    unittest.main()
