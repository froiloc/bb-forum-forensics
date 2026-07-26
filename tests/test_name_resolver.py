# =============================================================================
# tests/test_name_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Namensaufloesung
# =============================================================================
# Testsuite fuer management/crossref/name_resolver.py und GET /api/names.
#
# NR01 — RUECKWAERTS aus der Fallakte: subject_id -> Name, mit Quelle.
# NR02 — RUECKWAERTS aus known_users, wenn die Fallakte den Fall nicht kennt.
#        Der Schluesseltest der Datei: known_users.user_id IST die subject_id
#        (Entscheidung Geisternutzer-Schema 2026-07-20 §3) — es wird NICHT
#        umgerechnet.
# NR03 — Nichts gefunden -> name=None, KEIN erfundener Platzhalter; eine
#        Kennung im Geisterband bekommt die Erklaerung dazu.
# NR04 — Fehlende/kaputte default.db: die Fallakte antwortet weiter, und der
#        Ausfall wird BENANNT (Grundregel 1).
# NR05 — VORWAERTS, Kaskade: Treffer in der Fallakte -> known_users wird NICHT
#        gelistet, aber GEZAEHLT (die Kaskade schweigt nicht).
# NR06 — VORWAERTS, zweite Stufe: ohne Fallakten-Treffer wird known_users
#        gelistet.
# NR07 — Mindestlaenge 4: darunter wird known_users NICHT abgefragt, und die
#        Antwort sagt das, statt einen Leerbefund zu behaupten.
# NR08 — Sortierung: genau vor beginnt-mit vor enthaelt.
# NR09 — LIKE-Sonderzeichen ('%') sind entschaerft — sonst lieferte die
#        Eingabe '%' die ganze Tabelle als "Treffer".
# NR10 — Endpunkt: 200 mit crossref.view, 403 ohne, 400 ohne Parameter.
# NR11 — Aliasse fahren bei der Aufloesung MIT, ersetzen den Kontonamen aber
#        nicht.
#
# Version: v0.8.600 · 2026-07-26
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
from management.crossref.name_resolver import (
    MIN_SUCHLAENGE,
    NameResolver,
    QUELLEN_HINWEIS,
)
from management.crossref.subject_alias_repo import SubjectAliasRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac.rbac_repo import RbacRepo
from management.server.management_app import ManagementApp

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

#: DDL der echten Tabelle, woertlich aus dem Prepper
#  (aiw_sqlite_prepper/stage1/phase_b_exporter.py:216-220) bzw. aus
#  management/maintenance/default_db_merger.py:98-100. Die Testvorrichtung baut
#  sie NICHT nach eigenem Gutduenken — genau das war der Fehler, der in
#  Build 527/528 zu einer falsch belegten Aussage gefuehrt hat.
_DDL_KNOWN_USERS = """
CREATE TABLE IF NOT EXISTS known_users (
    user_id   INTEGER PRIMARY KEY,
    username  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS known_users_username_idx ON known_users (username);
"""


class NameResolverTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        self._ddb = os.path.join(self._tmp, "default.db")

        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        for pid, user, name, inv, sup in ((1, "h0a2898", "Chefin", 1, 1),
                                          (3, "h003", "Ohnerecht", 0, 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,?,0,?)",
                (pid, user, name, inv, sup, int(time.time())))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.writer = CoordinatorWriter(con, AuditLog(con))
        self.rbac = RbacRepo(con, self.writer)
        self.rbac.grant("supervisor", "crossref.view", scope="alle",
                        actor_id=1)
        self.rbac.grant("supervisor", "crossref.edit", scope="alle",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)

        cases = CasesRepo(con, self.writer)
        # 18 = 'Apfelbaum' (auch in known_users), 19 = 'Birnenmus'
        cases.create_case(18, "Apfelbaum", actor_id=1)
        cases.create_case(19, "Birnenmus", actor_id=1)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        # default.db: 18 kommt in BEIDEN vor, 4711/4712 NUR hier.
        d = sqlite3.connect(self._ddb)
        d.executescript(_DDL_KNOWN_USERS)
        d.executemany("INSERT INTO known_users (user_id, username) "
                      "VALUES (?,?)", [
                          (18, "Apfelbaum"),
                          (4711, "apfel"),            # genau (case-insensitiv)
                          (4712, "Apfelkuchen"),      # beginnt mit
                          (4713, "Bratapfel"),        # enthaelt
                          (4714, "Zwetschge"),
                      ])
        d.commit()
        d.close()

    def tearDown(self):
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

    def _r(self, ddb=None):
        return NameResolver(self.con,
                            self._ddb if ddb is None else ddb)

    # NR01 -------------------------------------------------------------------
    def test_nr01_rueckwaerts_aus_fallakte(self):
        a = self._r().aufloesen(19)
        self.assertEqual(a.name, "Birnenmus")
        self.assertEqual(a.quelle, "fallakte")
        self.assertTrue(a.to_dict()["gefunden"])
        self.assertIn("Fallakte", a.to_dict()["quelle_label"])

    # NR02 -------------------------------------------------------------------
    def test_nr02_rueckwaerts_aus_known_users_ohne_umrechnung(self):
        """
        known_users.user_id IST die subject_id (Entscheidung 2026-07-20 §3:
        'Realnutzer: subject_id = users.id'). Wuerde hier irgendwo ein Offset
        addiert, faende dieser Test nichts.
        """
        a = self._r().aufloesen(4712)
        self.assertEqual(a.name, "Apfelkuchen")
        self.assertEqual(a.quelle, "forenkonto")

    # NR03 -------------------------------------------------------------------
    def test_nr03_nicht_gefunden_ohne_platzhalter(self):
        a = self._r().aufloesen(99999)
        self.assertIsNone(a.name)                 # KEIN erfundener Name
        self.assertEqual(a.quelle, "nicht_gefunden")
        self.assertFalse(a.to_dict()["gefunden"])

        # Geisterband: die Kennung erklaert sich selbst, statt nur 'unbekannt'
        # zu sagen (Entscheidung 2026-07-20 §3, Band oberhalb 1e9).
        g = self._r().aufloesen(1000000123)
        self.assertIsNone(g.name)
        self.assertTrue(any("Geisternutzer" in h for h in g.hinweise), g.hinweise)

        # Der Quellen-Hinweis steht in JEDER Antwort.
        self.assertIn("nicht 'gibt es nicht'", a.to_dict()["quellen_hinweis"])

    # NR04 -------------------------------------------------------------------
    def test_nr04_default_db_ausfall_wird_benannt(self):
        # (a) Datei fehlt -> Fallakte antwortet weiter.
        r = self._r(ddb=os.path.join(self._tmp, "gibtsnicht.db"))
        a = r.aufloesen(18)
        self.assertEqual(a.name, "Apfelbaum")      # aus der Fallakte
        b = r.aufloesen(4712)
        self.assertIsNone(b.name)
        self.assertTrue(any("nicht gefunden" in h for h in b.hinweise),
                        b.hinweise)

        # (b) Datei da, aber keine SQLite-Datei. Muss BENANNT werden und darf
        #     NICHT werfen — dieselbe Lehre wie Build 534/US05.
        kaputt = os.path.join(self._tmp, "kaputt.db")
        Path(kaputt).write_bytes(b"das ist ganz sicher keine SQLite-Datei")
        c = self._r(ddb=kaputt).aufloesen(4712)
        self.assertIsNone(c.name)
        self.assertTrue(c.hinweise)

        # (c) Datei da, aber ohne die Tabelle.
        leer = os.path.join(self._tmp, "leer.db")
        con = sqlite3.connect(leer)
        con.execute("CREATE TABLE irgendwas (a INTEGER)")
        con.commit()
        con.close()
        d = self._r(ddb=leer).aufloesen(4712)
        self.assertIsNone(d.name)
        self.assertTrue(any("known_users" in h for h in d.hinweise),
                        d.hinweise)

    # NR05 -------------------------------------------------------------------
    def test_nr05_kaskade_zaehlt_die_zweite_stufe(self):
        """
        'Apfel' trifft in der Fallakte (18 Apfelbaum) UND in known_users
        (4711 apfel, 4712 Apfelkuchen, 4713 Bratapfel, 18 Apfelbaum).
        Die Kaskade listet nur die Fallakte — nennt aber die ZAHL der anderen.
        Ohne diese Zahl saehe das Ergebnis vollstaendig aus und waere es nicht.
        """
        e = self._r().suchen("Apfel")
        self.assertEqual(e.quelle, "fallakte")
        self.assertEqual([t.subject_id for t in e.treffer], [18])
        self.assertEqual(e.weitere_treffer.get("forenkonto"), 4)
        d = e.to_dict()
        self.assertEqual(d["weitere_treffer"]["forenkonto"], 4)

    # NR06 -------------------------------------------------------------------
    def test_nr06_zweite_stufe_wenn_fallakte_leer(self):
        e = self._r().suchen("Zwetschge")
        self.assertEqual(e.quelle, "forenkonto")
        self.assertEqual([t.subject_id for t in e.treffer], [4714])
        self.assertEqual(e.treffer[0].quelle, "forenkonto")

    # NR07 -------------------------------------------------------------------
    def test_nr07_mindestlaenge(self):
        """
        Unter der Schwelle wird known_users NICHT abgefragt — und die Antwort
        sagt das. Ein stiller Leerbefund waere hier die Unwahrheit: nicht
        gesucht ist nicht dasselbe wie nicht gefunden.
        """
        self.assertEqual(MIN_SUCHLAENGE, 4)
        e = self._r().suchen("Zwe")               # 3 Zeichen, kein Fall-Treffer
        self.assertEqual(e.treffer, ())
        self.assertTrue(any("mindestens 4 Zeichen" in h for h in e.hinweise),
                        e.hinweise)

        # Ein Fall-Treffer unter der Schwelle funktioniert weiterhin (die
        # Fallakte hat 163 Zeilen, keine Schwelle noetig) ...
        f = self._r().suchen("Bir")
        self.assertEqual([t.subject_id for t in f.treffer], [19])
        # ... und die zweite Stufe wird dann NICHT gezaehlt: 'None' heisst
        # 'nicht abgefragt' und ist etwas anderes als '0'.
        self.assertNotIn("forenkonto", f.weitere_treffer)

    # NR08 -------------------------------------------------------------------
    def test_nr08_sortierung_genau_vor_praefix_vor_enthaelt(self):
        e = self._r().suchen("apfel")
        self.assertEqual(e.quelle, "fallakte")     # Kaskade greift
        # Fuer die zweite Stufe direkt pruefen:
        treffer, gesamt, fehler = self._r()._suche_forenkonten("apfel", 50)
        self.assertEqual(fehler, "")
        self.assertEqual([t.name for t in treffer],
                         ["apfel", "Apfelbaum", "Apfelkuchen", "Bratapfel"])
        self.assertEqual(gesamt, 4)

    # NR09 -------------------------------------------------------------------
    def test_nr09_like_sonderzeichen_entschaerft(self):
        """
        Ohne Entschaerfung wuerde '%' als Platzhalter wirken und ALLE Zeilen
        als 'Treffer' liefern — ein Ergebnis, das wie ein Fund aussieht und
        keiner ist.
        """
        e = self._r().suchen("%")
        self.assertEqual(e.treffer, ())
        treffer, gesamt, _ = self._r()._suche_forenkonten("%%%%", 50)
        self.assertEqual(treffer, [])
        self.assertEqual(gesamt, 0)

    # NR10 -------------------------------------------------------------------
    def test_nr10_endpunkt(self):
        app = ManagementApp(self._db, default_db=self._ddb)

        r = app.dispatch(1, "/api/names", {"subject_id": ["4712"]})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["modus"], "aufloesung")
        self.assertEqual(d["name"], "Apfelkuchen")
        self.assertEqual(d["quelle"], "forenkonto")

        r2 = app.dispatch(1, "/api/names", {"q": ["Zwetschge"]})
        self.assertEqual(r2.status, 200)
        d2 = json.loads(r2.body.decode("utf-8"))
        self.assertEqual(d2["modus"], "suche")
        self.assertEqual(d2["treffer"][0]["subject_id"], 4714)
        self.assertIn("quellen_hinweis", d2)

        # Ohne Parameter -> 400 (kein stiller Gesamtabzug).
        self.assertEqual(app.dispatch(1, "/api/names", {}).status, 400)
        # Ungueltige Kennung -> 400.
        self.assertEqual(app.dispatch(
            1, "/api/names", {"subject_id": ["pfui"]}).status, 400)
        # Ohne crossref.view -> 403 (dieselbe Huerde wie /api/alias).
        self.assertEqual(app.dispatch(
            3, "/api/names", {"q": ["Zwetschge"]}).status, 403)

    # NR11 -------------------------------------------------------------------
    def test_nr11_aliasse_fahren_mit_ersetzen_aber_nicht(self):
        SubjectAliasRepo(self.con, self.writer).add(
            subject_id=19, alias="Birne2000", kind_code="forenname",
            basis="Signatur in Beitrag #4711", actor_id=1)
        a = self._r().aufloesen(19)
        # Der KONTONAME bleibt der Kontoname ...
        self.assertEqual(a.name, "Birnenmus")
        self.assertEqual(a.quelle, "fallakte")
        # ... und der Alias steht DANEBEN.
        self.assertEqual(a.aliasse, ("Birne2000",))
        self.assertIn("Birne2000", a.to_dict()["aliasse"])

    # NR12 -------------------------------------------------------------------
    def test_nr12_leerer_begriff_liefert_nichts(self):
        """Wer nichts sucht, soll nicht versehentlich alles bekommen."""
        for begriff in ("", "   ", None):
            e = self._r().suchen(begriff)
            self.assertEqual(e.treffer, ())
            self.assertEqual(e.gesamt, 0)
        self.assertTrue(QUELLEN_HINWEIS)


if __name__ == "__main__":
    unittest.main()
