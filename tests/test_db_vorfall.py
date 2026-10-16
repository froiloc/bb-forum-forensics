# =============================================================================
# tests/test_db_vorfall.py
# IT-Forensisches Ermittlungswerkzeug — Register "Datenbank-Vorfaelle" (Build 777)
# =============================================================================
# Prueft Migration M041, DbVorfallMeldung, DbVorfallRepo, DbVorfallPuffer,
# DbVorfallMelder und die Endpunkte /api/db_vorfaelle(/pruefen).
#
#   DV01  M041: Tabelle, Index, schema_migrations 41; zweiter Lauf No-op
#   DV02  M041: die CHECKs greifen (am Verhalten geprueft)
#   DV03  M041: vorhandene Tabelle mit anderen Spalten -> Abbruch, nichts
#         ueberschrieben
#   DV04  erfassen: Zeile + EIN Beleg; audit_seq passt; Payload traegt die
#         SHA-256 des Befunds
#   DV05  erfassen ist idempotent; abweichender Inhalt bei gleicher Kennung
#         -> Fehler, nichts geschrieben
#   DV06  unzulaessige Meldungen werden VOR jedem Schreiben abgewiesen
#   DV07  als_geprueft: Recht, Person, Notiz Pflicht; einseitig; Beleg
#   DV08  Puffer: Ablage, Lesen, unlesbare und .tmp-Dateien werden gemeldet
#   DV09  Melder: coordinator.db fehlt -> gepuffert, KEINE Datei angelegt;
#         Nachtrag -> eingetragen (nachgetragen=1), Pufferdatei geloescht
#   DV10  Melder: weder Register noch Puffer -> nur_protokoll, Meldung
#         vollstaendig im Protokoll (CRITICAL)
#   DV11  Nachtrag eines schon eingetragenen Vorfalls: kein zweiter Beleg
#   DV12  liste/zaehler: Reihenfolge, Filter, unlesbarer Befund wird
#         mit Fehlerangabe ausgeliefert statt weggelassen
#   DV13  Melder: gesperrte coordinator.db -> gepuffert
#   DV14  GET /api/db_vorfaelle: ops.view, Zaehler, Puffer, kann_pruefen
#   DV15  POST /api/db_vorfaelle/pruefen: wartung.durchfuehren, Notiz,
#         auditiert; ops.view allein genuegt nicht
#   DV16  Nachtrag: scheitert EINE Meldung, bleibt genau ihre Datei liegen;
#         die uebrigen werden nachgetragen
#   DV17  gleichzeitiger Eintrag derselben Kennung: UNIQUE faengt ihn, es
#         gilt der vorhandene Eintrag, kein zweiter Beleg
#   DV18  die Selbstpruefung von M041 bricht bei geschwaechtem CHECK ab
#
# Version: v0.8.777 · Build: 777 · 2026-10-14
# =============================================================================

import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.audit.event_types import EventType                  # noqa: E402
from management.db_vorfall.db_vorfall_fehler import DbVorfallFehler  # noqa: E402
from management.db_vorfall.db_vorfall_melder import DbVorfallMelder  # noqa: E402
from management.db_vorfall.db_vorfall_meldung import (               # noqa: E402
    ART_STARTPRUEFUNG_EVIDENCE, ERGEBNIS_FREIGEGEBEN,
    ERGEBNIS_NICHT_FREIGEGEBEN, DbVorfallMeldung,
)
from management.db_vorfall.db_vorfall_puffer import DbVorfallPuffer  # noqa: E402
from management.db_vorfall.db_vorfall_repo import DbVorfallRepo     # noqa: E402
from management.db_vorfall.melde_ergebnis import (                  # noqa: E402
    EINGETRAGEN, GEPUFFERT, NUR_PROTOKOLL,
)
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.coordinator import m041_db_vorfall as m041  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.rbac.rbac_repo import RbacRepo                      # noqa: E402

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


def baue_coordinator(pfad: str) -> None:
    """coordinator.db ueber die VOLLE Migrationskette. Personen:
    1 Leitung (ops.view + wartung.durchfuehren), 2 nur ops.view, 3 nichts."""
    con = sqlite3.connect(pfad)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.executescript(_PERSON)
    con.executescript(_OLD_SCRAPE_JOBS)
    now = int(time.time())
    for uname, dname in (("h001", "Leitung, Alpha"), ("h002", "Beta"),
                         ("h003", "Gamma")):
        con.execute(
            "INSERT INTO person (system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?,?,1,0,0,?)", (uname, dname, now))
    audit = AuditLog(con)
    MigrationRunner(con, discover(coordinator_migrations), audit=audit,
                    deployed_by="tester").run()
    rbac = RbacRepo(con, CoordinatorWriter(con, audit))
    rbac.grant("supervisor", "ops.view", scope="alle", actor_id=1)
    rbac.grant("supervisor", "wartung.durchfuehren", scope="alle", actor_id=1)
    rbac.assign_role(1, "supervisor", actor_id=1)
    rbac.grant("investigator", "ops.view", scope="alle", actor_id=1)
    rbac.assign_role(2, "investigator", actor_id=1)
    con.close()


def meldung(**kw) -> DbVorfallMeldung:
    werte = dict(art=ART_STARTPRUEFUNG_EVIDENCE, ergebnis=ERGEBNIS_FREIGEGEBEN,
                 datei="D:\\data\\evidence\\evidence_4711.db",
                 befund={"integrity_check": ["Tree 7 page 9: ...", "ä ✓"],
                         "verloren": {"page_visits": 0}},
                 subject_id=4711, person_id=2, host="VM-TEST", jetzt=1760000000)
    werte.update(kw)
    return DbVorfallMeldung.neu(**werte)


class _Welt(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        baue_coordinator(self.db_path)
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.audit = AuditLog(self.con)
        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = DbVorfallRepo(self.con, self.writer)
        self.puffer_dir = os.path.join(self._tmp, "defekt",
                                       "ausstehende_vorfaelle")

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    def spitze(self, con=None):
        return (con or self.con).execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0]

    def zeilen(self):
        return self.con.execute("SELECT COUNT(*) FROM db_vorfall").fetchone()[0]


# =============================================================================
# Migration
# =============================================================================
class MigrationTests(_Welt):

    def test_dv01_tabelle_index_idempotent(self):
        self.assertEqual(m041.VERSION, 41)
        self.assertEqual(m041.KIND, "additive")
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM schema_migrations WHERE version = 41").fetchone())
        spalten = {r[1] for r in self.con.execute(
            "PRAGMA table_info(db_vorfall)")}
        self.assertEqual(spalten, m041._SPALTEN)
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' "
            "AND name='ix_db_vorfall_status'").fetchone())
        schema_vorher = self.con.execute(
            "SELECT sql FROM sqlite_master WHERE name='db_vorfall'").fetchone()
        self.con.execute("BEGIN")
        m041.up(self.con)
        self.con.execute("COMMIT")
        self.assertEqual(schema_vorher, self.con.execute(
            "SELECT sql FROM sqlite_master WHERE name='db_vorfall'").fetchone())
        self.assertEqual(self.zeilen(), 0)

    def _insert(self, **werte):
        zeile = {"vorfall_uid": "a" * 32, "erkannt_at": 1, "erfasst_at": 1,
                 "nachgetragen": 0, "art": "x", "ergebnis": "y", "datei": "d",
                 "befund_json": "{}", "status": "offen", "audit_seq": 1}
        zeile.update(werte)
        k = sorted(zeile)
        self.con.execute("INSERT INTO db_vorfall (%s) VALUES (%s)" % (
            ",".join(k), ",".join("?" * len(k))), [zeile[x] for x in k])

    def test_dv02_checks_greifen(self):
        vermerk = {"geprueft_von": 1, "geprueft_at": 1, "pruef_audit_seq": 1}
        abzulehnen = [{"status": "erledigt"}, {"nachgetragen": 2},
                      {"status": "geprueft"}, dict(vermerk)]
        # JEDES Feld des Pruefvermerks einzeln (Gegenprobe N8: ein einzelnes
        # vergessenes Feld im CHECK blieb sonst unbemerkt).
        for feld in sorted(vermerk):
            abzulehnen.append(dict({k: v for k, v in vermerk.items()
                                    if k != feld}, status="geprueft"))
            abzulehnen.append({feld: vermerk[feld]})
        for werte in abzulehnen:
            with self.assertRaises(sqlite3.IntegrityError, msg=str(werte)):
                self._insert(**werte)
        # Gegenprobe: gueltig offen und gueltig geprueft werden angenommen.
        self._insert()
        self._insert(vorfall_uid="b" * 32, status="geprueft", geprueft_von=1,
                     geprueft_at=1, pruef_audit_seq=1)
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert()       # UNIQUE vorfall_uid
        self.assertEqual(self.zeilen(), 2)

    def test_dv03_abweichende_tabelle_bricht_ab(self):
        con = sqlite3.connect(":memory:")
        con.isolation_level = None
        con.execute("CREATE TABLE person (id INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE audit_log (seq INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE db_vorfall (id INTEGER PRIMARY KEY, x TEXT)")
        con.execute("INSERT INTO db_vorfall (x) VALUES ('bleibt')")
        con.execute("BEGIN")
        with self.assertRaises(RuntimeError) as ctx:
            m041.up(con)
        con.execute("ROLLBACK")
        self.assertIn("ABWEICHENDEN", str(ctx.exception))
        self.assertEqual(con.execute("SELECT x FROM db_vorfall").fetchall(),
                         [("bleibt",)])

    def test_dv18_selbstpruefung_der_migration_greift(self):
        """Ein geschwaechter CHECK im DDL laesst M041 abbrechen — die
        Selbstpruefung ist keine Kulisse (Gegenprobe N8c)."""
        from unittest import mock
        schwach = m041._DDL.replace(
            "AND geprueft_at IS NULL AND pruef_audit_seq IS NULL)",
            "AND geprueft_at IS NULL)")
        self.assertNotEqual(schwach, m041._DDL)
        con = sqlite3.connect(":memory:")
        con.isolation_level = None
        con.execute("CREATE TABLE person (id INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE audit_log (seq INTEGER PRIMARY KEY)")
        con.execute("BEGIN")
        with mock.patch.object(m041, "_DDL", schwach):
            with self.assertRaises(RuntimeError) as ctx:
                m041.up(con)
        con.execute("ROLLBACK")
        self.assertIn("offen mit pruef_audit_seq", str(ctx.exception))


# =============================================================================
# Repo
# =============================================================================
class RepoTests(_Welt):

    def test_dv04_erfassen_mit_beleg(self):
        m = meldung()
        vorher = self.spitze()
        seq = self.repo.erfassen(m, jetzt=1760000100)
        self.assertEqual(seq, vorher + 1)
        z = self.con.execute(
            "SELECT vorfall_uid, erkannt_at, erfasst_at, nachgetragen, status, "
            "audit_seq, befund_json, subject_id, person_id, host FROM db_vorfall"
        ).fetchone()
        self.assertEqual(z[0], m.vorfall_uid)
        self.assertEqual((z[1], z[2], z[3], z[4], z[5]),
                         (1760000000, 1760000100, 0, "offen", seq))
        self.assertEqual(json.loads(z[6]), m.befund)
        self.assertIn("ä ✓", z[6])          # UTF-8 im Klartext
        self.assertEqual((z[7], z[8], z[9]), (4711, 2, "VM-TEST"))
        b = self.con.execute(
            "SELECT event_type, actor_id, target_type, target_id, content "
            "FROM audit_log WHERE seq = ?", (seq,)).fetchone()
        self.assertEqual(b[0], EventType.DB_VORFALL_ERFASST)
        self.assertEqual((b[1], b[2], b[3]), (2, "db_vorfall", m.vorfall_uid))
        payload = json.loads(b[4])
        import hashlib
        self.assertEqual(payload["befund_sha256"], hashlib.sha256(
            m.befund_json().encode("utf-8")).hexdigest())
        self.assertEqual(payload["ergebnis"], ERGEBNIS_FREIGEGEBEN)
        self.assertFalse(payload["nachgetragen"])
        self.assertTrue(self.audit.verify_chain().ok)

    def test_dv05_idempotent_und_widerspruch(self):
        m = meldung()
        seq = self.repo.erfassen(m)
        spitze = self.spitze()
        self.assertEqual(self.repo.erfassen(m), seq)
        self.assertEqual(self.repo.erfassen(m, nachgetragen=True), seq)
        self.assertEqual(self.spitze(), spitze)
        self.assertEqual(self.zeilen(), 1)
        anders = DbVorfallMeldung.aus_dict(dict(m.als_dict(),
                                                ergebnis=ERGEBNIS_NICHT_FREIGEGEBEN))
        with self.assertRaises(DbVorfallFehler):
            self.repo.erfassen(anders)
        self.assertEqual(self.spitze(), spitze)
        self.assertEqual(self.con.execute(
            "SELECT ergebnis FROM db_vorfall").fetchone()[0], ERGEBNIS_FREIGEGEBEN)

    def test_dv06_unzulaessige_meldungen(self):
        spitze = self.spitze()
        schlecht = [
            meldung(art="unbekannt"),
            meldung(ergebnis="geraten"),
            meldung(datei="  "),
            meldung(befund={"objekt": object()}),
            DbVorfallMeldung.aus_dict(dict(meldung().als_dict(),
                                           vorfall_uid="nicht-hex")),
            DbVorfallMeldung.aus_dict(dict(meldung().als_dict(),
                                           erkannt_at="gestern")),
        ]
        for m in schlecht:
            with self.assertRaises(DbVorfallFehler, msg=repr(m)):
                self.repo.erfassen(m)
        with self.assertRaises(DbVorfallFehler):
            DbVorfallRepo(self.con).erfassen(meldung())   # ohne Schreiber
        self.assertEqual(self.spitze(), spitze)
        self.assertEqual(self.zeilen(), 0)

    def test_dv07_als_geprueft(self):
        self.repo.erfassen(meldung())
        vid = self.con.execute("SELECT id FROM db_vorfall").fetchone()[0]
        spitze = self.spitze()
        for kw in ({"actor_id": 2, "notiz": "gesehen"},     # nur ops.view
                   {"actor_id": 3, "notiz": "gesehen"},     # gar nichts
                   {"actor_id": None, "notiz": "gesehen"},
                   {"actor_id": 1, "notiz": "   "},
                   {"actor_id": 1, "notiz": "x" * 4001}):
            with self.assertRaises(DbVorfallFehler, msg=str(kw)):
                self.repo.als_geprueft(vid, **kw)
        with self.assertRaises(DbVorfallFehler):
            self.repo.als_geprueft(vid + 99, actor_id=1, notiz="gesehen")
        self.assertEqual(self.spitze(), spitze)
        seq = self.repo.als_geprueft(vid, actor_id=1,
                                     notiz=" Protokoll gelesen, Daten ok ",
                                     jetzt=1760001000)
        self.assertEqual(seq, spitze + 1)
        z = self.repo.holen(vid)
        self.assertEqual((z["status"], z["geprueft_von"], z["geprueft_at"],
                          z["pruef_notiz"], z["pruef_audit_seq"]),
                         ("geprueft", 1, 1760001000,
                          "Protokoll gelesen, Daten ok", seq))
        b = self.con.execute("SELECT event_type, actor_id, content FROM "
                             "audit_log WHERE seq = ?", (seq,)).fetchone()
        self.assertEqual((b[0], b[1]), (EventType.DB_VORFALL_GEPRUEFT, 1))
        self.assertEqual(json.loads(b[2])["notiz"], "Protokoll gelesen, Daten ok")
        with self.assertRaises(DbVorfallFehler):
            self.repo.als_geprueft(vid, actor_id=1, notiz="nochmal")
        self.assertEqual(self.spitze(), seq)

    def test_dv12_liste_zaehler_unlesbarer_befund(self):
        self.repo.erfassen(meldung(jetzt=100))
        self.repo.erfassen(meldung(jetzt=300, ergebnis=ERGEBNIS_NICHT_FREIGEGEBEN))
        self.repo.erfassen(meldung(jetzt=200))
        ids = [v["erkannt_at"] for v in self.repo.liste()]
        self.assertEqual(ids, [300, 200, 100])
        vid = self.repo.liste()[2]["id"]
        self.repo.als_geprueft(vid, actor_id=1, notiz="ok")
        self.assertEqual(self.repo.zaehler(), {"offen": 2, "geprueft": 1})
        self.assertEqual([v["erkannt_at"] for v in self.repo.liste("geprueft")],
                         [100])
        self.assertEqual(len(self.repo.liste("offen")), 2)
        with self.assertRaises(DbVorfallFehler):
            self.repo.liste("erledigt")
        # Ein (von Hand) beschaedigter Befund verschwindet nicht.
        self.con.execute("UPDATE db_vorfall SET befund_json = '{kaputt' "
                         "WHERE erkannt_at = 200")
        z = [v for v in self.repo.liste() if v["erkannt_at"] == 200][0]
        self.assertIsNone(z["befund"])
        self.assertEqual(z["befund_roh"], "{kaputt")
        self.assertIn("kein gueltiges JSON", z["befund_fehler"])
        self.assertEqual(len(self.repo.liste()), 3)
        self.assertIn("NICHT freigegeben",
                      self.repo.liste()[0]["ergebnis_klartext"])


# =============================================================================
# Puffer und Melder
# =============================================================================
class PufferMelderTests(_Welt):

    def test_dv08_puffer(self):
        p = DbVorfallPuffer(self.puffer_dir)
        self.assertEqual(p.eintraege(), [])          # Ordner fehlt: leer
        m = meldung()
        pfad = p.ablegen(m)
        self.assertEqual(os.path.basename(pfad),
                         "db_vorfall_%s.json" % m.vorfall_uid)
        self.assertFalse(os.path.exists(pfad + ".tmp"))
        (gelesen_pfad, gelesen, fehler), = p.eintraege()
        self.assertEqual((gelesen_pfad, fehler), (pfad, None))
        self.assertEqual(gelesen.als_dict(), m.als_dict())
        # unlesbar, .tmp und falscher Name werden gemeldet, nicht uebergangen
        with open(os.path.join(self.puffer_dir, "db_vorfall_kaputt.json"),
                  "w", encoding="utf-8") as fh:
            fh.write("{")
        with open(os.path.join(self.puffer_dir, "db_vorfall_x.json.tmp"),
                  "w", encoding="utf-8") as fh:
            fh.write("{}")
        m2 = meldung()
        with open(os.path.join(self.puffer_dir, "db_vorfall_%s.json" % ("f" * 32)),
                  "w", encoding="utf-8") as fh:
            json.dump(m2.als_dict(), fh)
        with open(os.path.join(self.puffer_dir, "fremd.txt"), "w") as fh:
            fh.write("gehoert nicht dazu")
        e = p.eintraege()
        self.assertEqual(len(e), 4)
        self.assertEqual(p.anzahl(), 4)
        fehler = sorted(f for _p, mm, f in e if mm is None)
        self.assertEqual(len(fehler), 3)
        self.assertTrue(any(".tmp" in f for f in fehler))
        self.assertTrue(any("passt nicht zur Kennung" in f for f in fehler))
        with self.assertRaises(DbVorfallFehler):
            p.entfernen(os.path.join(self._tmp, "coordinator.db"))
        self.assertTrue(os.path.exists(self.db_path))

    def test_dv09_puffern_ohne_anlegen_dann_nachtragen(self):
        # Der Ordner EXISTIERT, nur die Datei fehlt: ein Oeffnen mit
        # Anlegerecht wuerde hier eine leere coordinator.db erzeugen (die
        # Gegenprobe N5 hat gezeigt, dass ein fehlender Ordner das verdeckt).
        fehlt = os.path.join(self._tmp, "coordinator_fehlt.db")
        melder = DbVorfallMelder(fehlt, DbVorfallPuffer(self.puffer_dir),
                                 timeout=0.2)
        m = meldung()
        with self.assertLogs("management.db_vorfall.db_vorfall_melder",
                             level="WARNING"):
            erg = melder.melden(m)
        self.assertEqual(erg.ausgang, GEPUFFERT)
        self.assertIsNone(erg.audit_seq)
        self.assertTrue(os.path.isfile(erg.puffer_pfad))
        self.assertTrue(erg.fehler and erg.fehler[0].startswith("Register:"))
        self.assertFalse(os.path.exists(fehlt), "coordinator.db wurde angelegt")
        self.assertIn("Puffer", erg.klartext())
        # Nachtrag scheitert, solange die Datei fehlt -> Datei bleibt.
        with self.assertLogs("management.db_vorfall.db_vorfall_melder",
                             level="ERROR"):
            n = melder.nachtragen()
        self.assertEqual(len(n["fehlgeschlagen"]), 1)
        self.assertTrue(os.path.isfile(erg.puffer_pfad))
        # Mit erreichbarer coordinator.db: eingetragen, Datei weg.
        melder2 = DbVorfallMelder(self.db_path, DbVorfallPuffer(self.puffer_dir))
        n = melder2.nachtragen()
        self.assertEqual(n["nachgetragen"], [m.vorfall_uid])
        self.assertEqual((n["fehlgeschlagen"], n["unlesbar"]), ([], []))
        self.assertFalse(os.path.exists(erg.puffer_pfad))
        z = self.repo.liste()[0]
        self.assertTrue(z["nachgetragen"])
        self.assertEqual(z["erkannt_at"], 1760000000)
        payload = json.loads(self.con.execute(
            "SELECT content FROM audit_log WHERE seq = ?",
            (z["audit_seq"],)).fetchone()[0])
        self.assertTrue(payload["nachgetragen"])

    def test_dv10_nur_protokoll(self):
        # Pufferordner ist eine DATEI -> nicht anlegbar.
        sperre = os.path.join(self._tmp, "keinordner")
        with open(sperre, "w") as fh:
            fh.write("x")
        melder = DbVorfallMelder(os.path.join(self._tmp, "fehlt.db"),
                                 DbVorfallPuffer(os.path.join(sperre, "p")),
                                 timeout=0.2)
        m = meldung()
        with self.assertLogs("management.db_vorfall.db_vorfall_melder",
                             level="CRITICAL") as log:
            erg = melder.melden(m)
        self.assertEqual(erg.ausgang, NUR_PROTOKOLL)
        self.assertEqual(len(erg.fehler), 2)
        kritisch = [r.getMessage() for r in log.records
                    if r.levelno == logging.CRITICAL]
        self.assertEqual(len(kritisch), 1)
        self.assertIn(m.vorfall_uid, kritisch[0])
        self.assertIn(json.dumps(m.als_dict(), ensure_ascii=False,
                                 sort_keys=True), kritisch[0])
        # Ohne Puffer ebenso.
        erg = DbVorfallMelder(None, None).melden(meldung())
        self.assertEqual(erg.ausgang, NUR_PROTOKOLL)
        # Eine UNZULAESSIGE Meldung wird geworfen, nicht gepuffert.
        with self.assertRaises(DbVorfallFehler):
            DbVorfallMelder(self.db_path, None).melden(meldung(art="x"))

    def test_dv11_nachtrag_idempotent(self):
        m = meldung()
        seq = self.repo.erfassen(m)
        spitze = self.spitze()
        p = DbVorfallPuffer(self.puffer_dir)
        pfad = p.ablegen(m)      # Datei blieb nach einem Eintrag liegen
        n = DbVorfallMelder(self.db_path, p).nachtragen()
        self.assertEqual(n["nachgetragen"], [m.vorfall_uid])
        self.assertFalse(os.path.exists(pfad))
        self.assertEqual(self.spitze(), spitze)
        self.assertEqual(self.zeilen(), 1)
        self.assertEqual(self.repo.liste()[0]["audit_seq"], seq)
        self.assertFalse(self.repo.liste()[0]["nachgetragen"])

    def test_dv16_nachtrag_einzelfehler_haelt_die_datei(self):
        """Scheitert der Nachtrag EINER Meldung (Widerspruch zum Register),
        bleibt genau ihre Datei liegen; die uebrigen werden nachgetragen."""
        m = meldung()
        self.repo.erfassen(m)
        p = DbVorfallPuffer(self.puffer_dir)
        widerspruch = DbVorfallMeldung.aus_dict(dict(
            m.als_dict(), ergebnis=ERGEBNIS_NICHT_FREIGEGEBEN))
        pfad_w = p.ablegen(widerspruch)
        gut = meldung(subject_id=815)
        pfad_g = p.ablegen(gut)
        with self.assertLogs("management.db_vorfall.db_vorfall_melder",
                             level="ERROR"):
            n = DbVorfallMelder(self.db_path, p).nachtragen()
        self.assertEqual(n["nachgetragen"], [gut.vorfall_uid])
        self.assertEqual([f["datei"] for f in n["fehlgeschlagen"]], [pfad_w])
        self.assertIn("ANDEREM Inhalt", n["fehlgeschlagen"][0]["fehler"])
        self.assertTrue(os.path.exists(pfad_w))
        self.assertFalse(os.path.exists(pfad_g))
        self.assertEqual(self.zeilen(), 2)

    def test_dv17_gleichzeitiger_eintrag_derselben_kennung(self):
        """Zwischen Nachsehen und Schreiben traegt ein anderer Prozess
        DENSELBEN Vorfall ein: die UNIQUE-Verletzung rollt zurueck, es gilt
        der vorhandene Eintrag, kein zweiter Beleg."""
        m = meldung()
        seq = self.repo.erfassen(m)
        spitze = self.spitze()
        original = self.repo._vorhanden
        aufrufe = []

        def erst_blind(meldung_, befund_json):
            aufrufe.append(1)
            if len(aufrufe) == 1:
                return None          # das Nachsehen "verpasst" den Eintrag
            return original(meldung_, befund_json)
        self.repo._vorhanden = erst_blind
        self.assertEqual(self.repo.erfassen(m), seq)
        self.assertEqual(len(aufrufe), 2)
        self.assertEqual(self.spitze(), spitze)
        self.assertEqual(self.zeilen(), 1)
        # Mit ANDEREM Inhalt bleibt es ein Widerspruch.
        aufrufe.clear()
        anders = DbVorfallMeldung.aus_dict(dict(
            m.als_dict(), ergebnis=ERGEBNIS_NICHT_FREIGEGEBEN))
        with self.assertRaises(DbVorfallFehler):
            self.repo.erfassen(anders)
        self.assertEqual(self.spitze(), spitze)

    def test_dv13_gesperrte_coordinator_db(self):
        sperr = sqlite3.connect(self.db_path, isolation_level=None)
        sperr.execute("BEGIN EXCLUSIVE")
        try:
            erg = DbVorfallMelder(self.db_path, DbVorfallPuffer(self.puffer_dir),
                                  timeout=0.2).melden(meldung())
        finally:
            sperr.execute("ROLLBACK")
            sperr.close()
        self.assertEqual(erg.ausgang, GEPUFFERT)
        self.assertEqual(self.zeilen(), 0)
        erg2 = DbVorfallMelder(self.db_path, None).melden(meldung())
        self.assertEqual(erg2.ausgang, EINGETRAGEN)
        self.assertTrue(erg2.eingetragen)
        self.assertEqual(self.zeilen(), 1)


# =============================================================================
# Endpunkte
# =============================================================================
class ApiTests(_Welt):

    def setUp(self):
        super().setUp()
        from management.server.management_app import ManagementApp
        self.app = ManagementApp(self.db_path,
                                 vorfall_puffer_dir=self.puffer_dir)

    def _json(self, r):
        return json.loads(r.body.decode("utf-8"))

    def test_dv14_lesen(self):
        r = self.app.dispatch(3, "/api/db_vorfaelle")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "ops.view")
        self.repo.erfassen(meldung())
        DbVorfallPuffer(self.puffer_dir).ablegen(meldung(subject_id=815))
        r = self.app.dispatch(2, "/api/db_vorfaelle")
        self.assertEqual(r.status, 200)
        d = self._json(r)
        self.assertEqual(d["zaehler"], {"offen": 1, "geprueft": 0})
        self.assertEqual(len(d["vorfaelle"]), 1)
        self.assertEqual(d["vorfaelle"][0]["person_name"], "Beta")
        self.assertIsNone(d["vorfaelle"][0]["geprueft_von_name"])
        self.assertFalse(d["kann_pruefen"])
        self.assertEqual(d["puffer"]["anzahl"], 1)
        self.assertEqual(d["puffer"]["eintraege"][0]["subject_id"], 815)
        self.assertIn(ERGEBNIS_FREIGEGEBEN, d["ergebnisse"])
        self.assertTrue(self._json(self.app.dispatch(1, "/api/db_vorfaelle"))
                        ["kann_pruefen"])
        r = self.app.dispatch(1, "/api/db_vorfaelle", {"status": ["geprueft"]})
        self.assertEqual(self._json(r)["vorfaelle"], [])
        r = self.app.dispatch(1, "/api/db_vorfaelle", {"status": ["kaputt"]})
        self.assertEqual(r.status, 400)

    def test_dv15_pruefen(self):
        self.repo.erfassen(meldung())
        vid = self.repo.liste()[0]["id"]
        spitze = self.spitze()
        r = self.app.dispatch_write(2, "/api/db_vorfaelle/pruefen",
                                    {"id": vid, "notiz": "gesehen"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "wartung.durchfuehren")
        r = self.app.dispatch_write(1, "/api/db_vorfaelle/pruefen",
                                    {"id": vid, "notiz": ""})
        self.assertEqual(r.status, 400)
        r = self.app.dispatch_write(1, "/api/db_vorfaelle/pruefen",
                                    {"id": "x", "notiz": "a"})
        self.assertEqual(r.status, 400)
        self.assertEqual(self.spitze(), spitze)
        r = self.app.dispatch_write(1, "/api/db_vorfaelle/pruefen",
                                    {"id": vid, "notiz": "Protokoll gelesen"})
        self.assertEqual(r.status, 200, r.body)
        self.assertEqual(self._json(r)["audit_seq"], spitze + 1)
        d = self._json(self.app.dispatch(1, "/api/db_vorfaelle"))
        self.assertEqual(d["zaehler"], {"offen": 0, "geprueft": 1})
        self.assertEqual(d["vorfaelle"][0]["geprueft_von_name"], "Leitung, Alpha")
        r = self.app.dispatch_write(1, "/api/db_vorfaelle/pruefen",
                                    {"id": vid, "notiz": "nochmal"})
        self.assertEqual(r.status, 400)


if __name__ == "__main__":
    unittest.main()
