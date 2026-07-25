# =============================================================================
# tests/test_management_limitation_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7
# =============================================================================
# Testsuite fuer Build 524 (AP-3A / Idee 32): Fristbeginn je Fall aus den
# forensic_<uid>.db, Read-Model und Endpunkt GET /api/limitation.
#
# LESESCHICHT (read_tatzeit — eine forensic_<uid>.db, rein lesend):
#   LM01 — beide Zeitquellen vorhanden: frueheste/spaeteste ueber BEIDE Tabellen
#          gebildet, 'quellen' nennt beide.
#   LM02 — nur uid_posts vorhanden -> belegt, nur diese Quelle genannt.
#   LM03 — Datei fehlt -> befund 'ohne_forensic_db' (Fall bleibt in der Liste).
#   LM04 — Datei da, aber keine der Zeittabellen -> 'ohne_zeittabelle'.
#   LM05 — Tabellen da, aber alle Zeitstempel NULL -> 'ohne_tatzeit'
#          (unterscheidet sich ausdruecklich von 'ohne_zeittabelle').
#   LM06 — Datei unlesbar (kein SQLite) -> 'nicht_lesbar' MIT Grund.
#   LM07 — ZEITQUELLEN nennt genau die zwei belegten Spalten und NICHT
#          pages.fetched_at (Sicherungszeitpunkt, nie Tatzeit).
#
# READ-MODEL (LimitationRepo):
#   LM08 — jeder Fall aus 'cases' erzeugt GENAU EINE Zeile, auch ohne Datei;
#          'datenlage' zaehlt die Befunde, 'zaehler' die Ampelzustaende.
#   LM09 — Sortierung: 'ueberschritten' vor 'knapp' vor 'ohne_tatzeit' vor
#          'offen' (Ungeprueftes rutscht NICHT unter Unverdaechtiges).
#   LM10 — leere Auswahl (subject_ids=[]) bedeutet KEINE Faelle, nicht 'alle'.
#   LM11 — die Hinweise (share_id-Luecke, fetched_at) fahren in JEDER Antwort
#          mit.
#
# ENDPUNKT:
#   LM12 — ohne Recht -> 403 und nennt 'limitation.view'.
#   LM13 — mit Recht (unbestaetigter Satz) -> 200, aussage_moeglich false,
#          verweigerungsgrund gesetzt, ABER Fallliste und Datenlage vollstaendig.
#   LM14 — die Antwort traegt 'stellt_keine_verjaehrung_fest': true.
#   LM15 — vorwarn_tage unbrauchbar (nicht-Zahl, negativ) -> je 400.
#   LM16 — Scope 'eigene' genuegt: die Sicht ist NICHT scope-behaftet (sie
#          zeigt bewusst auch unzugewiesene Faelle).
#   LM17 — Der Endpunkt schreibt NICHTS: audit_log-Spitze unveraendert.
#   LM18 — M031 hat 'limitation.view' geseedet (Migrationskette angewandt).
#
# BUILD 527 — die Befunde aus der PROD-Messung (uid_posts OHNE Spalte 'posted'):
#   LM19 — Tabelle da, aber die Zeitspalte fehlt, und es gibt KEINE zweite
#          Quelle -> befund 'zeitspalte_unlesbar'. Der Detailtext sagt
#          UNBEKANNT und behauptet NICHT 'kein Zeitstempel gesetzt' (das war der
#          Fehler aus Build 524). Der SQLite-Grund faehrt mit.
#   LM20 — Spalte fehlt in EINER Quelle, die andere liefert einen Wert ->
#          befund 'belegt_unvollstaendig' und NICHT 'belegt'. Der Fristbeginn
#          ist gesetzt, aber die Zeile traegt den Ausfall MIT — das war der
#          gefaehrlichere der beiden Fehler, weil die Zahl vollwertig aussah.
#   LM21 — 'ohne_tatzeit' bleibt dem Fall vorbehalten, in dem Tabelle UND
#          Spalte lesbar sind und trotzdem nichts drinsteht. Die drei Lagen sind
#          damit unterscheidbar.
#   LM22 — Das Aggregat: 'quellenfehler' zaehlt je Fehlertext die Faelle,
#          'faelle_mit_quellenfehler' die betroffenen Faelle. Ein bei ALLEN
#          Faellen gleicher Fehler ist ein Schema-Befund, und die Zahl sagt das.
#   LM23 — Der Ausfall steht in den HINWEISEN der Antwort (nicht nur im
#          Serverprotokoll) und dort GANZ VORNE.
#   LM24 — Sortierung: bei gleicher Ampel steht das eingeschraenkt Belegte VOR
#          dem vollstaendig Belegten.
#   LM25 — DATENLAGE_BEFUNDE nennt alle tatsaechlich erzeugten Befunde (und
#          keinen, der nicht erzeugt wird) — dieselbe Zusicherung wie LC13 fuer
#          die Ampelzustaende.
# =============================================================================

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.cases.cases_repo import CasesRepo                   # noqa: E402
from management.deadlines.limitation_params import load_params      # noqa: E402
from management.deadlines.limitation_repo import (                  # noqa: E402
    BEFUNDE_MIT_TATZEIT,
    DATENLAGE_BEFUNDE,
    HINWEIS_FETCHED_AT,
    HINWEIS_QUELLEN,
    ZEITQUELLEN,
    LimitationRepo,
    read_tatzeit,
)
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover   # noqa: E402
from management.rbac.rbac_repo import RbacRepo                       # noqa: E402
from management.server.management_app import ManagementApp           # noqa: E402

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0,
    is_support INTEGER NOT NULL DEFAULT 0,
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


def _ts(tag: str) -> int:
    return int(datetime.combine(date.fromisoformat(tag), dtime(0, 0),
                                tzinfo=timezone.utc).timestamp())


def _forensic_db(pfad: Path, *, posts=None, pms=None, shares=None,
                 downloads=None, mit_posts_tabelle=True,
                 mit_pms_tabelle=False, posts_spalte="posted_ts",
                 pms_spalte="posted_ts") -> None:
    """
    Baut eine minimale forensic_<uid>.db mit dem ECHTEN Schema.

    BELEG (Build 528): forensic_uid.db.schema.sql — das vollstaendige DDL,
    uebergeben am 2026-07-25, bestaetigt durch Sondenlaeufe in DEV und PROD.

    BIS BUILD 527 STAND HIER 'uid_posts(id, posted)' — eine Vorrichtung, die
    die Welt baute, die der Code erwartete. Dieser Test war deshalb gruen,
    waehrend das Feature in PROD nie lief. Die Spaltennamen dieser Vorrichtung
    stammen jetzt aus dem DDL und nicht mehr aus dem Code, den sie pruefen
    soll.

    posts_spalte ist einstellbar, um den Zustand VOR der Korrektur
    nachzustellen (Tabelle da, Spalte anders benannt).
    """
    con = sqlite3.connect(str(pfad))
    try:
        if mit_posts_tabelle:
            con.execute(
                "CREATE TABLE uid_posts (post_id INTEGER PRIMARY KEY, "
                "topic_id INTEGER, forum_id INTEGER, %s INTEGER, "
                "active INTEGER DEFAULT 1, is_topic_starter INTEGER DEFAULT 0)"
                % posts_spalte)
            for i, t in enumerate(posts or []):
                con.execute(
                    "INSERT INTO uid_posts (post_id, topic_id, forum_id, %s) "
                    "VALUES (?,?,?,?)" % posts_spalte, (i + 1, 10, 20, t))
        if mit_pms_tabelle:
            con.execute(
                "CREATE TABLE uid_pms_posts (pm_post_id INTEGER PRIMARY KEY, "
                "pm_topic_id INTEGER, topic_subject TEXT, %s INTEGER, "
                "active INTEGER DEFAULT 1, is_topic_starter INTEGER DEFAULT 0)"
                % pms_spalte)
            for i, t in enumerate(pms or []):
                con.execute(
                    "INSERT INTO uid_pms_posts (pm_post_id, pm_topic_id, %s) "
                    "VALUES (?,?,?)" % pms_spalte, (500 + i, 7, t))
        if shares is not None:
            # Build 528: Teilungsakte sind eine Tathandlungs-Quelle
            # (Verbreiten, § 184b Abs. 1 S. 1 Nr. 1).
            con.execute(
                "CREATE TABLE uid_shares (id INTEGER PRIMARY KEY, "
                "source_table TEXT, source_id INTEGER, post_id INTEGER, "
                "topic_id INTEGER, posted_ts INTEGER, filename TEXT)")
            for i, t in enumerate(shares):
                con.execute(
                    "INSERT INTO uid_shares (id, source_table, source_id, "
                    "post_id, posted_ts) VALUES (?,?,?,?,?)",
                    (i + 1, "t", 1, 900 + i, t))
        if downloads is not None:
            # Build 528: Abrufe/Downloads (Sich-Verschaffen, § 184b Abs. 3).
            con.execute(
                "CREATE TABLE uid_downloads (id INTEGER PRIMARY KEY, "
                "post_id INTEGER, cat_id INTEGER, group_id INTEGER, "
                "time_ts INTEGER, post_subject TEXT)")
            for i, t in enumerate(downloads):
                con.execute(
                    "INSERT INTO uid_downloads (id, post_id, cat_id, "
                    "group_id, time_ts) VALUES (?,?,?,?,?)",
                    (i + 1, 800 + i, 1, 1, t))
        con.commit()
    finally:
        con.close()


class TestReadTatzeit(unittest.TestCase):
    """LM01-LM07 — die Leseschicht, eine Datei je Fall."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_LM01_beide_quellen(self):
        p = self.dir / "forensic_11.db"
        _forensic_db(p, posts=[_ts("2022-03-14"), _ts("2023-01-05")],
                     pms=[_ts("2021-08-01"), _ts("2024-02-02")],
                     mit_pms_tabelle=True)
        t = read_tatzeit(p, 11, "nutzer11")
        self.assertEqual(t.befund, "belegt")
        self.assertEqual(t.frueheste_ts, _ts("2021-08-01"))
        self.assertEqual(t.spaeteste_ts, _ts("2024-02-02"))
        self.assertEqual(set(t.quellen),
                         {"uid_posts.posted_ts", "uid_pms_posts.posted_ts"})

    def test_LM02_nur_posts(self):
        p = self.dir / "forensic_12.db"
        _forensic_db(p, posts=[_ts("2022-03-14")])
        t = read_tatzeit(p, 12, "nutzer12")
        self.assertEqual(t.befund, "belegt")
        self.assertEqual(t.spaeteste_ts, _ts("2022-03-14"))
        self.assertEqual(t.quellen, ("uid_posts.posted_ts",))

    def test_LM03_datei_fehlt(self):
        t = read_tatzeit(self.dir / "forensic_13.db", 13, "nutzer13")
        self.assertEqual(t.befund, "ohne_forensic_db")
        self.assertIsNone(t.spaeteste_ts)
        self.assertIn("forensic_13.db", t.detail)

    def test_LM04_ohne_zeittabelle(self):
        p = self.dir / "forensic_14.db"
        _forensic_db(p, mit_posts_tabelle=False)
        # Eine Datei ohne jede Tabelle: SQLite legt sie beim CREATE erst an, wir
        # erzeugen also bewusst eine leere Datenbank mit einer FREMDEN Tabelle.
        con = sqlite3.connect(str(p))
        con.execute("CREATE TABLE pages (page_id INTEGER, fetched_at INTEGER)")
        con.commit()
        con.close()
        t = read_tatzeit(p, 14, "nutzer14")
        self.assertEqual(t.befund, "ohne_zeittabelle")
        self.assertIn("uid_posts", t.detail)

    def test_LM05_ohne_tatzeit_ist_nicht_ohne_tabelle(self):
        p = self.dir / "forensic_15.db"
        _forensic_db(p, posts=[None, None])
        t = read_tatzeit(p, 15, "nutzer15")
        self.assertEqual(t.befund, "ohne_tatzeit")
        self.assertIn("kein einziger", t.detail)
        # Der Unterschied zu 'ohne_zeittabelle' ist der ganze Punkt: hier war
        # die Tabelle da und leer, dort fehlte sie.
        self.assertNotEqual(t.befund, "ohne_zeittabelle")

    def test_LM06_nicht_lesbar_mit_grund(self):
        p = self.dir / "forensic_16.db"
        p.write_bytes(b"das ist keine SQLite-Datei")
        t = read_tatzeit(p, 16, "nutzer16")
        self.assertEqual(t.befund, "nicht_lesbar")
        self.assertTrue(t.detail.strip())
        self.assertIsNone(t.spaeteste_ts)

    def test_LM07_zeitquellen_sind_belegt_und_abgeschlossen(self):
        spalten = {"%s.%s" % (t, s) for t, s, _b in ZEITQUELLEN}
        self.assertEqual(spalten, {"uid_posts.posted_ts",
                                   "uid_pms_posts.posted_ts",
                                   "uid_shares.posted_ts",
                                   "uid_downloads.time_ts"})
        # pages.fetched_at ist der SICHERUNGSZEITPUNKT und darf nie als Tatzeit
        # dienen — eine Verwechslung wuerde jede Frist um Jahre verschieben.
        self.assertNotIn("pages.fetched_at", spalten)
        # Und die Belege verweisen auf das DDL, NICHT auf eine Testvorrichtung.
        for _t, _sp, beleg in ZEITQUELLEN:
            self.assertIn("forensic_uid.db.schema.sql", beleg)
            self.assertNotIn("test_build", beleg)
        for _t, _s, beleg in ZEITQUELLEN:
            self.assertTrue(beleg.strip())


class TestBuild528Quellen(unittest.TestCase):
    """
    LM26-LM28 — die Korrekturen aus dem Schema-Beleg (Build 528).

    Anlass: mc hat am 2026-07-25 das vollstaendige DDL uebergeben
    (forensic_uid.db.schema.sql). Es belegt die echten Spaltennamen UND zwei
    Tathandlungs-Quellen, die Build 524 nicht kannte.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_LM26_teilung_und_download_sind_tathandlungen(self):
        """
        Ein Teilungsakt bzw. ein Download NACH dem letzten Beitrag verschiebt
        den Fristbeginn nach hinten. Vor Build 528 fielen beide unter den
        Tisch, und der Fristbeginn lag damit ZU FRUEH.
        """
        p = self.dir / "forensic_41.db"
        _forensic_db(p, posts=[_ts("2021-03-01")],
                     shares=[_ts("2023-06-15")],
                     downloads=[_ts("2024-02-10")])
        t = read_tatzeit(p, 41, "nutzer41")
        self.assertEqual(t.befund, "belegt")
        # Der Download ist die spaeteste Handlung -> er bestimmt den Beginn.
        self.assertEqual(t.spaeteste_ts, _ts("2024-02-10"))
        self.assertEqual(t.frueheste_ts, _ts("2021-03-01"))
        self.assertEqual(set(t.quellen),
                         {"uid_posts.posted_ts", "uid_shares.posted_ts",
                          "uid_downloads.time_ts"})

    def test_LM27_unplausible_werte_werden_verworfen_und_gezaehlt(self):
        """
        Epoch 0 ('unbekannt') und ein Wert weit in der Zukunft duerfen keine
        Frist erzeugen — sie werden aber GEZAEHLT, nicht verschwiegen.
        """
        p = self.dir / "forensic_42.db"
        _forensic_db(p, posts=[0, _ts("2022-05-05"), 4102444800])  # 0 und 2100
        t = read_tatzeit(p, 42, "nutzer42")
        self.assertEqual(t.befund, "belegt")
        # Nur der plausible Wert bildet die Spanne.
        self.assertEqual(t.frueheste_ts, _ts("2022-05-05"))
        self.assertEqual(t.spaeteste_ts, _ts("2022-05-05"))
        # Und die beiden anderen sind nicht verschwunden.
        self.assertEqual(t.unplausible_werte, 2)

    def test_LM28_nur_unplausible_werte_sind_kein_tatzeitpunkt(self):
        """Ein Konto, dessen einzige Zeitwerte Epoch 0 sind, hat keine Tatzeit."""
        p = self.dir / "forensic_43.db"
        _forensic_db(p, posts=[0, 0])
        t = read_tatzeit(p, 43, "nutzer43")
        self.assertEqual(t.befund, "ohne_tatzeit")
        self.assertIsNone(t.spaeteste_ts)
        self.assertEqual(t.unplausible_werte, 2)
        # Der Text nennt die Zahl — sonst saehe es wie ein leeres Konto aus.
        self.assertIn("ausserhalb", t.detail)


class TestBuild527Befunde(unittest.TestCase):
    """
    LM19-LM21, LM25 — die drei Lagen, die Build 524 in einen Topf geworfen hat.

    Anlass ist ein ECHTER Befund: in den forensic_<uid>.db der Dienststelle
    existiert die Spalte 'uid_posts.posted' nicht ('no such column: posted',
    162 von 162 Dateien, Messung 2026-07-25).
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_LM19_zeitspalte_unlesbar_statt_falscher_aussage(self):
        p = self.dir / "forensic_21.db"
        # Tabelle da, Spalte HEISST ANDERS -> der Zugriff scheitert.
        _forensic_db(p, posts=[1647216000], posts_spalte="posted")
        t = read_tatzeit(p, 21, "nutzer21")
        self.assertEqual(t.befund, "zeitspalte_unlesbar")
        self.assertIsNone(t.spaeteste_ts)
        # DER KERN: es wird NICHT behauptet, es sei kein Zeitstempel gesetzt.
        self.assertNotIn("kein einziger Zeitstempel", t.detail)
        self.assertIn("UNBEKANNT", t.detail)
        # Der SQLite-Grund faehrt mit — sonst sucht man im falschen Ort.
        self.assertTrue(t.quellen_fehler)
        self.assertIn("no such column", " ".join(t.quellen_fehler))
        self.assertIn("uid_posts.posted", " ".join(t.quellen_fehler))

    def test_LM20_belegt_unvollstaendig_ist_nicht_belegt(self):
        p = self.dir / "forensic_22.db"
        # uid_posts unbrauchbar, uid_pms_posts liefert einen Wert — genau die
        # Lage, die in der DEV-Messung 18 Faelle als 'belegt' ausgewiesen hat.
        _forensic_db(p, posts=[1647216000], posts_spalte="posted",
                     pms=[1700000000], mit_pms_tabelle=True)
        t = read_tatzeit(p, 22, "nutzer22")
        self.assertEqual(t.befund, "belegt_unvollstaendig")
        self.assertNotEqual(t.befund, "belegt")
        # Der Fristbeginn IST gesetzt (aus der lesbaren Quelle) ...
        self.assertEqual(t.spaeteste_ts, 1700000000)
        self.assertEqual(t.quellen, ("uid_pms_posts.posted_ts",))
        # ... aber die Zeile traegt den Ausfall UND seine Richtung mit.
        self.assertTrue(t.quellen_fehler)
        self.assertIn("zu frueh angesetzt", t.detail)
        # Und er gilt weiterhin als Fall MIT Tatzeit (die Frist wird gerechnet).
        self.assertIn(t.befund, BEFUNDE_MIT_TATZEIT)

    def test_LM21_ohne_tatzeit_bleibt_der_echte_leerbefund(self):
        p = self.dir / "forensic_23.db"
        # Tabelle UND Spalte lesbar, aber nur NULL-Werte.
        _forensic_db(p, posts=[None, None])
        t = read_tatzeit(p, 23, "nutzer23")
        self.assertEqual(t.befund, "ohne_tatzeit")
        self.assertEqual(t.quellen_fehler, ())
        self.assertIn("lesbar", t.detail)
        self.assertIn("kein einziger Zeitstempel", t.detail)

    def test_LM25_datenlage_befunde_vollstaendig(self):
        """Jeder deklarierte Befund wird erzeugt, und kein anderer."""
        erzeugt = set()
        # belegt
        p1 = self.dir / "forensic_31.db"
        _forensic_db(p1, posts=[1647216000])
        erzeugt.add(read_tatzeit(p1, 31, "a").befund)
        # belegt_unvollstaendig
        p2 = self.dir / "forensic_32.db"
        _forensic_db(p2, posts=[1], posts_spalte="posted", pms=[1700000000],
                     mit_pms_tabelle=True)
        erzeugt.add(read_tatzeit(p2, 32, "b").befund)
        # ohne_tatzeit
        p3 = self.dir / "forensic_33.db"
        _forensic_db(p3, posts=[None])
        erzeugt.add(read_tatzeit(p3, 33, "c").befund)
        # zeitspalte_unlesbar
        p4 = self.dir / "forensic_34.db"
        _forensic_db(p4, posts=[1], posts_spalte="posted")
        erzeugt.add(read_tatzeit(p4, 34, "d").befund)
        # ohne_zeittabelle
        p5 = self.dir / "forensic_35.db"
        _forensic_db(p5, mit_posts_tabelle=False)
        con = sqlite3.connect(str(p5))
        con.execute("CREATE TABLE pages (page_id INTEGER)")
        con.commit()
        con.close()
        erzeugt.add(read_tatzeit(p5, 35, "e").befund)
        # ohne_forensic_db
        erzeugt.add(read_tatzeit(self.dir / "forensic_36.db", 36, "f").befund)
        # nicht_lesbar
        p7 = self.dir / "forensic_37.db"
        p7.write_bytes(b"kein sqlite")
        erzeugt.add(read_tatzeit(p7, 37, "g").befund)

        self.assertEqual(erzeugt, set(DATENLAGE_BEFUNDE),
                         "deklariert-aber-nicht-erzeugt: %s / "
                         "erzeugt-aber-nicht-deklariert: %s"
                         % (set(DATENLAGE_BEFUNDE) - erzeugt,
                            erzeugt - set(DATENLAGE_BEFUNDE)))


class TestLimitationRepoAndApi(unittest.TestCase):
    """LM08-LM18 — Read-Model und Endpunkt."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.forensic = Path(self._tmp) / "forensic"
        self.forensic.mkdir()

        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=delete")
        self.con.executescript(_PERSON)
        self.con.executescript(_OLD_SCRAPE_JOBS)
        for uname, dname, inv, sup in (
                ("NRW\\chefin", "Chef-Ermittlerin", 0, 1),
                ("NRW\\ermittler", "Ermittler", 1, 0),
                ("NRW\\ohne", "Ohne Rechte", 0, 0)):
            self.con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,0)", (uname, dname, inv, sup))

        self.audit = AuditLog(self.con)
        self.applied = MigrationRunner(
            self.con, discover(coordinator_migrations), audit=self.audit,
            deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        rbac = RbacRepo(self.con, self.writer)
        rbac.grant("supervisor", "limitation.view", scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Person 2 bekommt dasselbe Recht mit Scope 'eigene' — die Sicht ist
        # NICHT scope-behaftet, also muss sie trotzdem antworten (LM16).
        rbac.grant("investigator", "limitation.view", scope="eigene",
                   actor_id=1)
        rbac.assign_role(2, "investigator", actor_id=1)
        # Person 3: nichts.

        cases = CasesRepo(self.con, self.writer)
        for uid, name in ((101, "alt_und_knapp"), (102, "frisch"),
                          (103, "ohne_datei"), (104, "leere_tabelle")):
            cases.create_case(uid, name, actor_id=1)

        # 101: Tat 2021-08-01 -> mit 5-Jahres-Frist am Stichtag ueberschritten.
        _forensic_db(self.forensic / "forensic_101.db",
                     posts=[_ts("2020-01-01"), _ts("2021-08-01")])
        # 102: Tat 2024-08-01 -> reichlich Zeit.
        _forensic_db(self.forensic / "forensic_102.db",
                     posts=[_ts("2024-08-01")])
        # 103: KEINE Datei.
        # 104: Tabelle da, aber leer.
        _forensic_db(self.forensic / "forensic_104.db", posts=[None])

        self.params = load_params()          # der ausgelieferte, UNBESTAETIGTE
        self.app = ManagementApp(self.db_path, forensic_dir=str(self.forensic))

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # -- Read-Model ---------------------------------------------------------

    def _repo(self):
        con = sqlite3.connect("file:%s?mode=ro" % self.db_path, uri=True)
        con.row_factory = sqlite3.Row
        return con, LimitationRepo(con, self.forensic)

    def test_LM08_jeder_fall_genau_eine_zeile(self):
        con, repo = self._repo()
        try:
            r = repo.compute(params=self.params, now_ts=_ts("2026-07-25"))
        finally:
            con.close()
        self.assertEqual(r.faelle_gesamt, 4)
        self.assertEqual(len(r.rows), 4)
        self.assertEqual(sum(r.datenlage.values()), 4)
        self.assertEqual(sum(r.zaehler.values()), 4)
        self.assertEqual(r.datenlage.get("ohne_forensic_db"), 1)
        self.assertEqual(r.datenlage.get("ohne_tatzeit"), 1)
        self.assertEqual(r.datenlage.get("belegt"), 2)
        # Kein Fall verschwindet: alle subject_ids sind vertreten.
        self.assertEqual({row.tatzeit.subject_id for row in r.rows},
                         {101, 102, 103, 104})

    def test_LM09_sortierung_dringlichstes_zuerst(self):
        """Mit BESTAETIGTEM Satz: ueberschritten vor knapp vor ungeprueft."""
        raw = json.loads(
            (Path("management/deadlines/limitation_params.json")
             ).read_text(encoding="utf-8"))
        raw["bestaetigt"] = True
        raw["bestaetigt_von"] = "StA Testfixture"
        raw["bestaetigt_am"] = "2026-07-25"
        p = Path(self._tmp) / "params_ok.json"
        p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        params_ok = load_params(p)

        con, repo = self._repo()
        try:
            r = repo.compute(params=params_ok, now_ts=_ts("2026-08-08"))
        finally:
            con.close()
        ampeln = [row.assessment.ampel for row in r.rows]
        rang = {"ueberschritten": 0, "knapp": 1, "ohne_tatzeit": 2,
                "ohne_fassung": 3, "ruht": 4, "offen": 5, "keine_aussage": 6}
        self.assertEqual(ampeln, sorted(ampeln, key=lambda a: rang[a]),
                         "Reihenfolge: %s" % ampeln)
        # 101 (Tat 2021-08-01, 5-Jahres-Frist) muss ueberschritten sein.
        erste = r.rows[0]
        self.assertEqual(erste.tatzeit.subject_id, 101)
        self.assertEqual(erste.assessment.ampel, "ueberschritten")
        self.assertNotIn("verjaehrt", erste.assessment.befund)
        # Die UNGEPRUEFTEN stehen VOR den unverdaechtigen 'offen'-Faellen.
        self.assertLess(ampeln.index("ohne_tatzeit"), ampeln.index("offen"))

    def test_LM10_leere_auswahl_ist_keine_auswahl_aller(self):
        con, repo = self._repo()
        try:
            r = repo.compute(params=self.params, now_ts=_ts("2026-07-25"),
                             subject_ids=[])
            r2 = repo.compute(params=self.params, now_ts=_ts("2026-07-25"),
                              subject_ids=[101])
        finally:
            con.close()
        self.assertEqual(r.faelle_gesamt, 0)
        self.assertEqual(r2.faelle_gesamt, 1)

    def test_LM11_hinweise_immer_dabei(self):
        con, repo = self._repo()
        try:
            r = repo.compute(params=self.params, now_ts=_ts("2026-07-25"))
        finally:
            con.close()
        self.assertIn(HINWEIS_QUELLEN, r.hinweise)
        self.assertIn(HINWEIS_FETCHED_AT, r.hinweise)
        # Build 528: der Hinweis nennt jetzt ALLE VIER Quellen — und
        # dass Teilungsakte und Downloads seit 528 dabei sind.
        self.assertTrue(any("uid_shares.posted_ts" in h
                            for h in r.hinweise))
        self.assertTrue(any("uid_downloads.time_ts" in h
                            for h in r.hinweise))
        # Und die Vorbehalte des Parametersatzes ebenso.
        self.assertGreaterEqual(len(r.vorbehalte), 4)

    # -- Endpunkt -----------------------------------------------------------

    def _get(self, person_id, query=None):
        return self.app.dispatch(person_id, "/api/limitation", query or {})

    def test_LM12_ohne_recht_403(self):
        r = self._get(3)
        self.assertEqual(r.status, 403)
        self.assertIn("limitation.view", r.body.decode("utf-8"))

    def test_LM13_unbestaetigt_aber_vollstaendig(self):
        r = self._get(1)
        self.assertEqual(r.status, 200)
        b = json.loads(r.body.decode("utf-8"))
        self.assertFalse(b["aussage_moeglich"])
        self.assertIn("NICHT JURISTISCH BESTAETIGT", b["verweigerungsgrund"])
        self.assertFalse(b["params_bestaetigt"])
        # ABER: die nuetzlichen Teile sind vollstaendig da.
        self.assertEqual(b["faelle_gesamt"], 4)
        self.assertEqual(len(b["rows"]), 4)
        self.assertEqual(sum(b["datenlage"].values()), 4)
        self.assertEqual(b["zaehler"].get("keine_aussage"), 4)
        # Jede Zeile nennt ihre Datenlage — auch wenn die Rechtsfolge fehlt.
        befunde = {row["tatzeit_befund"] for row in b["rows"]}
        self.assertEqual(befunde, {"belegt", "ohne_forensic_db",
                                   "ohne_tatzeit"})

    def test_LM14_zusicherung_faehrt_mit(self):
        b = json.loads(self._get(1).body.decode("utf-8"))
        self.assertTrue(b["stellt_keine_verjaehrung_fest"])

    def test_LM15_vorwarn_tage_unbrauchbar_400(self):
        for bad in ("abc", "-1"):
            r = self._get(1, {"vorwarn_tage": [bad]})
            self.assertEqual(r.status, 400, "Wert %r muss 400 ergeben" % bad)
        r_ok = self._get(1, {"vorwarn_tage": ["540"]})
        self.assertEqual(r_ok.status, 200)
        self.assertEqual(
            json.loads(r_ok.body.decode("utf-8"))["vorwarn_tage"], 540)

    def test_LM16_scope_eigene_genuegt(self):
        """
        Die Sicht ist NICHT scope-behaftet. Person 2 hat das Recht nur mit
        Scope 'eigene' und bekommt trotzdem die VOLLE Liste — genau so ist es
        gewollt: die gefaehrlichsten Faelle sind die unzugewiesenen.
        """
        r = self._get(2)
        self.assertEqual(r.status, 200)
        b = json.loads(r.body.decode("utf-8"))
        self.assertEqual(b["faelle_gesamt"], 4)

    def test_LM17_endpunkt_schreibt_nichts(self):
        tip = self.app.audit_tip_seq()
        self.assertEqual(self._get(1).status, 200)
        self.assertEqual(self._get(1, {"vorwarn_tage": ["30"]}).status, 200)
        self.assertEqual(self.app.audit_tip_seq(), tip)

    def test_LM22_quellenfehler_aggregat(self):
        """Ein bei ALLEN Faellen gleicher Fehler ist ein Schema-Befund."""
        # Zwei Faelle mit falscher Spalte, einer davon mit lesbarer PN-Quelle.
        _forensic_db(self.forensic / "forensic_105.db",
                     posts=[_ts("2022-01-01")], posts_spalte="posted")
        _forensic_db(self.forensic / "forensic_106.db",
                     posts=[_ts("2022-01-01")], posts_spalte="posted",
                     pms=[_ts("2023-05-05")], mit_pms_tabelle=True)
        cases = CasesRepo(self.con, self.writer)
        cases.create_case(105, "spalte_fehlt", actor_id=1)
        cases.create_case(106, "teilweise", actor_id=1)

        con, repo = self._repo()
        try:
            r = repo.compute(params=self.params, now_ts=_ts("2026-07-25"))
        finally:
            con.close()

        self.assertEqual(r.faelle_mit_quellenfehler, 2)
        self.assertEqual(sum(r.quellenfehler.values()), 2)
        schluessel = " ".join(r.quellenfehler.keys())
        self.assertIn("uid_posts.posted", schluessel)
        self.assertIn("no such column", schluessel)
        self.assertEqual(r.datenlage.get("zeitspalte_unlesbar"), 1)
        self.assertEqual(r.datenlage.get("belegt_unvollstaendig"), 1)
        # Die Summe bleibt stimmig — kein Fall verschwindet, keiner doppelt.
        self.assertEqual(sum(r.datenlage.values()), r.faelle_gesamt)

    def test_LM23_ausfall_steht_in_den_hinweisen_ganz_vorne(self):
        """
        Das Serverprotokoll sieht niemand, der die Liste liest. Der Ausfall
        gehoert deshalb in die ANTWORT — und dort an die erste Stelle.
        """
        _forensic_db(self.forensic / "forensic_107.db",
                     posts=[_ts("2022-01-01")], posts_spalte="posted")
        CasesRepo(self.con, self.writer).create_case(107, "x", actor_id=1)

        con, repo = self._repo()
        try:
            r = repo.compute(params=self.params, now_ts=_ts("2026-07-25"))
        finally:
            con.close()
        self.assertIn("DATENLAGE EINGESCHRAENKT", r.hinweise[0])
        self.assertIn("no such column", r.hinweise[0])
        # Die bestehenden Hinweise bleiben erhalten (nichts wird verdraengt).
        self.assertIn(HINWEIS_QUELLEN, r.hinweise)
        self.assertIn(HINWEIS_FETCHED_AT, r.hinweise)
        # Ohne Ausfall steht der Hinweis NICHT da (er soll etwas bedeuten).
        con2, repo2 = self._repo()
        try:
            r2 = repo2.compute(params=self.params, now_ts=_ts("2026-07-25"),
                               subject_ids=[101])
        finally:
            con2.close()
        self.assertNotIn("DATENLAGE EINGESCHRAENKT", " ".join(r2.hinweise))

    def test_LM24_eingeschraenktes_steht_vor_vollstaendigem(self):
        """Bei gleicher Ampel zuerst die Zeile, deren Zahl unter Vorbehalt steht."""
        _forensic_db(self.forensic / "forensic_108.db",
                     posts=[_ts("2024-08-01")], posts_spalte="posted",
                     pms=[_ts("2024-08-01")], mit_pms_tabelle=True)
        CasesRepo(self.con, self.writer).create_case(108, "teilweise",
                                                    actor_id=1)
        con, repo = self._repo()
        try:
            r = repo.compute(params=self.params, now_ts=_ts("2026-07-25"))
        finally:
            con.close()
        # Alle Ampeln sind 'keine_aussage' (Satz unbestaetigt) -> die
        # Reihenfolge entscheidet sich am Vorbehalt.
        befunde = [row.tatzeit.befund for row in r.rows]
        self.assertIn("belegt_unvollstaendig", befunde)
        self.assertLess(befunde.index("belegt_unvollstaendig"),
                        befunde.index("belegt"))

    def test_LM18_m031_hat_geseedet(self):
        self.assertIn(31, self.applied)
        row = self.con.execute(
            "SELECT code FROM rbac_capability WHERE code='limitation.view'"
        ).fetchone()
        self.assertIsNotNone(row)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
