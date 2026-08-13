# =============================================================================
# tests/test_rbac_grant_db_katalog.py
# IT-Forensisches Ermittlungswerkzeug — Regression zu Vorgang 1b7d55ae
# =============================================================================
# DER ANLASS: RbacRepo._validate_capability prueft capability_code gegen
# catalog.CAPABILITY_CODES — also gegen den Katalog im CODE. Ob die Faehigkeit
# in rbac_capability der DATENBANK steht, prueft dort niemand, und die
# Fremdschluessel der coordinator.db greifen bei foreign_keys=OFF nicht. Ein
# Grant auf ein der Datenbank unbekanntes Recht entstand deshalb klaglos.
#
# WAS DARAUS WURDE: Vorgang 9c4e17b2 (Grant #62 vom 12.08.2026) — der Bestand
# war danach verriegelt, weil die Migration, die das Recht anlegen sollte, an
# der Waise abbrach. Die Vorbeugung sass seit Build 711 allein in
# 'rbac_admin migrate-grants', also an dem einen Weg, auf dem es damals
# geschah. Seit Build 716 sitzt sie im REPOSITORY, durch das alle Schreibwege
# laufen ('rbac_admin grant', demo_seed, jede kuenftige Stelle).
#
# DIE BESTANDSAUFNAHME VOR DER AENDERUNG (gemessen, nicht geschaetzt): eine
# Sonde an genau dieser Stelle hat die volle Suite mitgeschrieben — 1958
# Grant-Aufrufe, davon 2 mit einer der Datenbank unbekannten Faehigkeit
# (SperrriegelTests RB11/RB11b in tests/test_rechtetrennung_falluebersicht.py,
# die die Lage vom 12.08.2026 nachstellen und die Waise deshalb BRAUCHEN), 0
# ohne die Tabelle rbac_capability.
#
# Testfaelle:
#   DK01 — Der Regelfall bleibt unveraendert: kennt die Datenbank das Recht,
#          entsteht der Grant wie bisher, und die audit_log-Nutzlast traegt
#          KEINEN Zusatzschluessel.
#   DK02 — Kennt die Datenbank das Recht nicht, wird der Grant abgewiesen.
#   DK03 — Und es bleibt NICHTS zurueck: keine rbac_grant-Zeile, kein
#          audit_log-Eintrag (die Transaktion rollt vollstaendig zurueck).
#   DK04 — Der Notausgang 'db_katalog_pruefen=False' schreibt den Grant, aber
#          nicht still: Vermerk in der audit_log-Nutzlast + Protokollzeile.
#   DK05 — Fehlt die Tabelle rbac_capability ganz, ist die Lage NICHT PRUEFBAR
#          und nicht 'nachweislich falsch': der Grant entsteht, mit eigenem
#          Vermerk und eigener Protokollzeile.
#   DK06 — Die Belegkette haelt in allen drei Faellen.
#   DK07 — Der CLI-Weg 'rbac_admin grant' erbt den Waechter, meldet den
#          fehlenden Schritt im Klartext und endet mit Exit 1.
#
# Beleg: Vorgang 1b7d55ae (Issue-Tracker); Herleitung im Kopf von
# management/rbac/rbac_repo.py und management/migrations/coordinator/
# m038_caseoverview_rbac.py.
#
# Version: v0.8.716 - Build: 716 - 2026-08-13
# =============================================================================

from __future__ import annotations

import io
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.audit.event_types import EventType                  # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover   # noqa: E402
from management.rbac import catalog, rbac_admin                      # noqa: E402
from management.rbac.rbac_repo import RbacError, RbacRepo            # noqa: E402

#: Das Recht aus dem Vorgang. Es steht seit Build 698 im Katalog des CODES und
#  wird erst von M038 in den Katalog der DATENBANK geschrieben — genau der
#  Spalt, um den es geht.
_NEUES_RECHT = "caseoverview.view"

#: Ein Recht, das M006 anlegt; es steht in BEIDEN Katalogen und dient als
#  Gegenprobe fuer den Regelfall.
_ALTES_RECHT = "dashboard.view"

#: Die letzte Migration VOR M038. Wer die Kette hier anhaelt, hat die
#  Ausgangslage vom 12.08.2026.
_VOR_M038 = 37

_PERSON = """
CREATE TABLE person (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT    NOT NULL UNIQUE,
    display_name    TEXT    NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor   INTEGER NOT NULL DEFAULT 0,
    is_support      INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL
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


class _MitDatenbank(unittest.TestCase):
    """
    Eine frisch migrierte coordinator.db je Testfall.

    _BIS_VERSION haelt die Kette nach dieser Version an; None faehrt sie ganz.
    Aufbau uebernommen aus tests/test_rechtetrennung_falluebersicht.py, damit
    beide Nachstellungen desselben Vorgangs von derselben Ausgangslage
    ausgehen.
    """

    _BIS_VERSION = None

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.executescript(_PERSON)
        self.con.executescript(_OLD_SCRAPE_JOBS)
        jetzt = int(time.time())
        for uname, dname, inv, sup in (("h001", "Chefin", 0, 1),
                                       ("h002", "Ermittler", 1, 0)):
            self.con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,?)", (uname, dname, inv, sup, jetzt))
        self.audit = AuditLog(self.con)
        migrationen = discover(coordinator_migrations)
        if self._BIS_VERSION is not None:
            migrationen = [m for m in migrationen
                           if m.VERSION <= self._BIS_VERSION]
        MigrationRunner(self.con, migrationen,
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)

    def tearDown(self):
        try:
            self.con.close()
        finally:
            for fn in os.listdir(self._tmp):
                try:
                    os.remove(os.path.join(self._tmp, fn))
                except OSError:
                    pass
            try:
                os.rmdir(self._tmp)
            except OSError:
                pass

    # -- Helfer ---------------------------------------------------------------
    def _nutzlast(self, seq):
        """
        Die audit_log-Nutzlast eines Belegs als Text (roh, ungedeutet).

        Die Spalte heisst 'content' und traegt die KANONISCHE Fassung der
        Nutzlast - genau die Zeichenfolge, die auch gehasht wird
        (audit_log.py Z. 203/221). Sie wird hier absichtlich als Text geprueft
        und nicht zurueckgedeutet: geprueft werden soll, was im Beleg STEHT.
        """
        row = self.con.execute(
            "SELECT content FROM audit_log WHERE seq=?", (seq,)).fetchone()
        return row["content"] if row is not None else None

    def _grants(self, code):
        return self.con.execute(
            "SELECT * FROM rbac_grant WHERE capability_code=?",
            (code,)).fetchall()

    def _max_seq(self):
        return self.con.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM audit_log").fetchone()[0]


class KatalogDerDatenbankTests(_MitDatenbank):
    """Die Kette laeuft ganz durch — die Datenbank kennt beide Rechte."""

    # -- DK01 -----------------------------------------------------------------
    def test_dk01_regelfall_unveraendert_und_ohne_zusatzschluessel(self):
        # Die Ausgangslage muss echt sein, sonst prueft der Test nichts.
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM rbac_capability WHERE code=?",
            (_ALTES_RECHT,)).fetchone())

        seq = self.repo.grant("supervisor", _ALTES_RECHT, scope="alle",
                              actor_id=1)
        self.assertEqual(1, len(self._grants(_ALTES_RECHT)))

        # WICHTIG fuer den Migrationsvorbehalt: im Regelfall bleibt die
        # Nutzlast die von vorher. Der Vermerk entsteht NUR in der Ausnahme;
        # bestehende Belege bleiben damit Zeichen fuer Zeichen vergleichbar.
        self.assertNotIn("db_katalog", self._nutzlast(seq))
        self.assertTrue(AuditLog(self.con).verify_chain().ok)

    # -- DK05 -----------------------------------------------------------------
    def test_dk05_fehlende_tabelle_ist_nicht_pruefbar_und_laesst_durch(self):
        """
        'rbac_capability existiert nicht' ist eine ANDERE Lage als 'die
        Migration steht aus': die erste heisst 'nicht pruefbar', die zweite
        'nachweislich falsch'. Ein Abbruch auf 'nicht pruefbar' traefe
        Altbestaende vor M006, ueber die wir keinen Befund haben - und der
        Vorgang 9c4e17b2 entstand nicht so (Weisung Alex, 13.08.2026).

        Die Lage wird hier hergestellt, indem die Katalogtabelle nach dem
        Migrationslauf entfernt wird. Das ist eine NACHSTELLUNG und kein
        Bestand: in der Suite kommt der Fall 0-mal vor (Sondenmessung), der
        Waechter muss ihn trotzdem beantworten koennen.
        """
        self.con.execute("DROP TABLE rbac_capability")

        with self.assertLogs("management.rbac.rbac_repo",
                             level="WARNING") as log:
            seq = self.repo.grant("supervisor", _ALTES_RECHT, scope="alle",
                                  actor_id=1)

        self.assertEqual(1, len(self._grants(_ALTES_RECHT)))
        self.assertIn("nicht_pruefbar_tabelle_fehlt", self._nutzlast(seq))
        text = "\n".join(log.output)
        self.assertIn("rbac_capability", text)
        self.assertIn("M006", text)
        # DK06 fuer diesen Zweig.
        self.assertTrue(AuditLog(self.con).verify_chain().ok)


class SpaltVorM038Tests(_MitDatenbank):
    """
    Die Kette haelt vor M038 an: das Recht steht im Katalog des CODES (sonst
    wiese schon _validate_capability es ab), aber noch nicht in dem der
    DATENBANK. Das ist der Spalt aus Vorgang 1b7d55ae.
    """

    _BIS_VERSION = _VOR_M038

    def setUp(self):
        super().setUp()
        # Beide Halbsaetze der Ausgangslage werden belegt, nicht behauptet.
        self.assertIn(_NEUES_RECHT, catalog.CAPABILITY_CODES,
                      "Das Recht fehlt im Katalog des Codes - dann prueft "
                      "dieser Test den falschen Waechter.")
        self.assertIsNone(self.con.execute(
            "SELECT 1 FROM rbac_capability WHERE code=?",
            (_NEUES_RECHT,)).fetchone(),
            "Die Kette haelt nicht vor M038 an.")

    # -- DK02 -----------------------------------------------------------------
    def test_dk02_unbekannt_in_der_datenbank_wird_abgewiesen(self):
        with self.assertRaises(RbacError) as ctx:
            self.repo.grant("supervisor", _NEUES_RECHT, scope="alle",
                            actor_id=1)
        # Die Meldung muss den naechsten Schritt nennen, nicht nur das Nein.
        text = str(ctx.exception)
        self.assertIn(_NEUES_RECHT, text)
        self.assertIn("rbac_capability", text)
        self.assertIn("management.migrate", text)

    # -- DK03 -----------------------------------------------------------------
    def test_dk03_nach_dem_abweisen_bleibt_nichts_zurueck(self):
        """
        Ein halb geschriebener Vorgang waere schlimmer als der, den der
        Waechter verhindert: eine Grant-Zeile ohne Beleg oder ein Beleg ohne
        Zeile. Gemessen wird deshalb BEIDES, vorher und nachher.
        """
        seq_vorher = self._max_seq()
        anzahl_vorher = self.con.execute(
            "SELECT COUNT(*) FROM rbac_grant").fetchone()[0]

        with self.assertRaises(RbacError):
            self.repo.grant("supervisor", _NEUES_RECHT, scope="alle",
                            actor_id=1)

        self.assertEqual(0, len(self._grants(_NEUES_RECHT)))
        self.assertEqual(anzahl_vorher, self.con.execute(
            "SELECT COUNT(*) FROM rbac_grant").fetchone()[0])
        self.assertEqual(seq_vorher, self._max_seq(),
                         "Es ist ein audit_log-Eintrag zurueckgeblieben - die "
                         "Transaktion hat nicht vollstaendig zurueckgerollt.")
        self.assertEqual(0, self.con.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event_type=? AND "
            "target_id=?", (EventType.RBAC_GRANTED,
                            "supervisor/%s" % _NEUES_RECHT)).fetchone()[0])
        self.assertTrue(AuditLog(self.con).verify_chain().ok)

    # -- DK04 -----------------------------------------------------------------
    def test_dk04_notausgang_schreibt_aber_nicht_still(self):
        """
        Der Notausgang ist fuer die Nachstellung des Vorgangs da (RB11/RB11b).
        Er darf den Waechter oeffnen - aber nicht lautlos: sonst waere die
        Waise spaeter von einem regulaeren Grant nicht zu unterscheiden, und
        genau diese Unterscheidbarkeit fehlte am 12.08.2026.
        """
        with self.assertLogs("management.rbac.rbac_repo",
                             level="WARNING") as log:
            seq = self.repo.grant("supervisor", _NEUES_RECHT, scope="alle",
                                  actor_id=1, db_katalog_pruefen=False)

        zeilen = self._grants(_NEUES_RECHT)
        self.assertEqual(1, len(zeilen))
        # Die Kopplung Grant <-> Beleg haelt auch im Notausgang; RB11 prueft
        # spaeter genau diese seq.
        self.assertEqual(seq, zeilen[0]["audit_seq"])
        self.assertIn("unbekannt_uebergangen", self._nutzlast(seq))
        self.assertIn("db_katalog_pruefen=False", "\n".join(log.output))
        # DK06 fuer diesen Zweig.
        self.assertTrue(AuditLog(self.con).verify_chain().ok)

    # -- DK07 -----------------------------------------------------------------
    def test_dk07_cli_grant_erbt_den_waechter(self):
        """
        'rbac_admin grant' war neben demo_seed der zweite produktive Weg ohne
        eigene Pruefung (Bestandsaufnahme zum Vorgang). Er bekommt sie jetzt
        vom Repository - ohne eine Zeile in rbac_admin.py, weil die zentrale
        Fehlerbehandlung dort RbacError bereits ausgibt und mit 1 endet.
        """
        self.con.close()
        try:
            aus, fehler = io.StringIO(), io.StringIO()
            with redirect_stdout(aus), redirect_stderr(fehler):
                rc = rbac_admin.main([
                    "grant", "--role", "supervisor",
                    "--capability", _NEUES_RECHT, "--scope", "alle",
                    "--coordinator-db", self.db_path])
            self.assertEqual(1, rc, "Der zu fruehe Lauf haette abbrechen "
                                    "muessen.")
            meldung = fehler.getvalue()
            self.assertIn(_NEUES_RECHT, meldung)
            self.assertIn("management.migrate", meldung)
        finally:
            self.con = sqlite3.connect(self.db_path)
            self.con.isolation_level = None
            self.con.row_factory = sqlite3.Row

        # Und es wurde nichts geschrieben.
        self.assertEqual(0, len(self._grants(_NEUES_RECHT)))


if __name__ == "__main__":
    unittest.main()
