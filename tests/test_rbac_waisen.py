# =============================================================================
# tests/test_rbac_waisen.py
# IT-Forensisches Ermittlungswerkzeug — Regression zu Vorgang 1b7d55ae
# =============================================================================
# DER ANLASS: Vorgang 9c4e17b2 (13.08.2026). Ein Grant auf 'caseoverview.view'
# entstand, bevor die Migration diese Faehigkeit in der Datenbank anlegte -
# moeglich, weil RbacRepo gegen den Katalog im CODE prueft und die
# Fremdschluessel bei foreign_keys=OFF nicht greifen. Der Zustand war von
# aussen nicht zu sehen; der Befund musste aus drei Tabellen von Hand
# zusammengesucht werden.
#
# tools/pruefe_rbac_waisen.py sucht ihn in einem Lauf. Diese Datei prueft das
# Werkzeug - und zwar an ECHTEN Datenbanken, die ueber die regulaere
# Migrationskette und das regulaere Schreibgateway entstehen. Ein Test, der
# die Tabellen von Hand zusammenstellte, wuerde bestenfalls seine eigene
# Vorstellung vom Schema pruefen.
#
# Testfaelle:
#   RW01 - Ein vollstaendig migrierter, sauberer Bestand liefert keinen Befund
#          und Rueckgabewert 0.
#   RW02 - Der Fall aus 9c4e17b2 wird gefunden: Grant, Rolle, Umfang - und der
#          BELEG wird aus audit_log aufgeloest.
#   RW03 - Das Werkzeug SCHREIBT NICHT. Gemessen an der Pruefsumme der Datei.
#   RW04 - Ein Katalogversatz ohne Waise bekommt einen EIGENEN Rueckgabewert
#          (3), damit ein Betriebsskript ihn nicht wie einen Schaden behandelt.
#   RW05 - Eine gebrochene Beleg-Kopplung wird gefunden - der schwerste der
#          hier gesuchten Befunde.
#   RW06 - Fehlt eine Tabelle, wird die entfallene Pruefung BENANNT
#          (Grundregel 1). Ein leerer Befund darf nicht wie eine
#          Unbedenklichkeitsbescheinigung aussehen.
#   RW07 - Eine Datenbank ohne Rechte-Matrix bricht mit 1 ab, nicht mit 0.
#   RW08 - Die Unterscheidung 'steht wenigstens im Code' wird gemacht - sie
#          trennt den Reihenfolgefall vom unerklaerlichen Fall.
#
# NACHTRAG BUILD 716 (Vorgang 1b7d55ae) - WARUM ZWEI FAELLE JETZT EINEN
# NOTAUSGANG BRAUCHEN:
#   Seit Build 716 weist RbacRepo.grant einen Grant auf eine Faehigkeit ab,
#   die die DATENBANK nicht kennt. Damit laesst sich die Waise ueber den
#   auditierten Weg nicht mehr erzeugen - was der Zweck jener Aenderung ist.
#   RW02 und RW02b brauchen sie aber als AUSGANGSLAGE und setzen deshalb
#   'db_katalog_pruefen=False'. Rohes SQL schied aus: RW02 loest die Beleg-seq
#   des Grants auf, der Grant muss also ein ordentlich belegter sein.
#
#   DAS WERKZEUG WIRD DADURCH NICHT UEBERFLUESSIG, und das ist der Grund,
#   warum hier nichts weiter geaendert wurde: die Vorbeugung wirkt ab jetzt,
#   BESTEHENDE Waisen findet weiterhin nur dieser Lauf. Und fuer role_code
#   besteht der Spalt unveraendert fort (Vorgang 9783552e) - 'rollen_ohne_...'
#   bleibt also auch fuer kuenftige Faelle zustaendig.
#
# Version: v0.8.713 - Build: 713 - 2026-08-13
#   ergaenzt v0.8.716 - Build: 716 - 2026-08-13 (Notausgang in RW02/RW02b)
# =============================================================================

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover   # noqa: E402
from management.rbac.rbac_repo import RbacRepo                       # noqa: E402
from tools import pruefe_rbac_waisen                                 # noqa: E402

_NEUES_RECHT = "caseoverview.view"
_ALTES_RECHT = "dashboard.view"


class _MitBestand(unittest.TestCase):
    """Eine echte coordinator.db je Testfall, ueber die regulaere Kette."""

    #: None = ganze Kette. Eine Zahl haelt sie an - so entsteht die Lage vor
    #  einer Migration, ohne sie nachzubauen.
    _BIS_VERSION = None

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

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.executescript(self._PERSON)
        self.con.executescript(self._OLD_SCRAPE_JOBS)
        jetzt = int(time.time())
        for uname, dname, sup in (("h001", "Chefin", 1), ("h002", "Ermittler", 0)):
            self.con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,1,?,0,?)", (uname, dname, sup, jetzt))
        migrationen = discover(coordinator_migrations)
        if self._BIS_VERSION is not None:
            migrationen = [m for m in migrationen
                           if m.VERSION <= self._BIS_VERSION]
        MigrationRunner(self.con, migrationen, audit=AuditLog(self.con),
                        deployed_by="tester").run()
        self.repo = RbacRepo(self.con, CoordinatorWriter(
            self.con, AuditLog(self.con)))

    def tearDown(self):
        self.con.close()

    def _pruefe(self):
        """Das Werkzeug oeffnet die Datei selbst - schreibgeschuetzt."""
        return pruefe_rbac_waisen.pruefe(self.db_path)

    def _md5(self):
        with open(self.db_path, "rb") as fh:
            return hashlib.md5(fh.read()).hexdigest()


class SauberTests(_MitBestand):
    """Ein vollstaendig migrierter Bestand."""

    # -- RW01 -----------------------------------------------------------------
    def test_rw01_sauberer_bestand_ohne_befund(self):
        self.repo.assign_role(1, "supervisor", actor_id=1)
        self.repo.grant("supervisor", _NEUES_RECHT, scope="alle", actor_id=1)

        ergebnis, rueckgabe = self._pruefe()
        self.assertEqual(0, rueckgabe, ergebnis)
        self.assertEqual(0, ergebnis["anzahl_waisen"])
        self.assertEqual([], ergebnis["grants_ohne_faehigkeit"])
        self.assertEqual(
            [], ergebnis["uebersprungene_pruefungen_wegen_fehlender_tabelle"])
        # Und der Katalogversatz ist leer - sonst waere Rueckgabe 3 gekommen
        # und RW04 wuerde nichts mehr unterscheiden.
        self.assertFalse(any(ergebnis["katalogversatz"].values()),
                         ergebnis["katalogversatz"])

    # -- RW03 -----------------------------------------------------------------
    def test_rw03_das_werkzeug_schreibt_nicht(self):
        """
        Die Zusage, auf der die Unbedenklichkeit im Betrieb beruht.

        Gemessen an der Pruefsumme der Datei, nicht an der Absicht des
        Aufrufs: 'mode=ro' im Quelltext zu lesen belegt nicht, dass die Datei
        unveraendert bleibt - ein Journal oder ein Kontrollpunkt wuerde sie
        auch ohne fachlichen Schreibvorgang anfassen.
        """
        self.repo.assign_role(1, "supervisor", actor_id=1)
        self.con.close()
        vorher = self._md5()
        pruefe_rbac_waisen.pruefe(self.db_path)
        self.assertEqual(vorher, self._md5(),
                         "Die Datenbank wurde durch die Pruefung veraendert.")
        self.con = sqlite3.connect(self.db_path)


class WaisenTests(_MitBestand):
    """Die Ausgangslage aus Vorgang 9c4e17b2: die Kette haelt vor M038 an."""

    _BIS_VERSION = 37

    # -- RW02 / RW08 ----------------------------------------------------------
    def test_rw02_findet_den_grant_und_loest_den_beleg_auf(self):
        self.repo.assign_role(1, "supervisor", actor_id=1)
        # db_katalog_pruefen=False (Build 716, Vorgang 1b7d55ae): seit dem
        # zweiten Waechter in RbacRepo.grant weist der auditierte Weg genau
        # diesen Grant ab - das ist der Zweck des Waechters, und er ergaenzt
        # dieses Werkzeug, statt es zu ersetzen (Bestandsfaelle bleiben zu
        # finden). Dieser Test BRAUCHT die Waise aber als Ausgangslage.
        # Rohes SQL scheidet aus: unten wird die Beleg-seq aufgeloest, der
        # Grant muss also ein ordentlich belegter sein.
        seq = self.repo.grant("supervisor", _NEUES_RECHT, scope="alle",
                              actor_id=1, db_katalog_pruefen=False)

        ergebnis, rueckgabe = self._pruefe()
        self.assertEqual(2, rueckgabe)
        self.assertEqual(1, len(ergebnis["grants_ohne_faehigkeit"]))

        fund = ergebnis["grants_ohne_faehigkeit"][0]
        self.assertEqual("supervisor", fund["rolle"])
        self.assertEqual(_NEUES_RECHT, fund["faehigkeit"])
        self.assertEqual("alle", fund["umfang"])
        self.assertTrue(fund["aktiv"])

        # DER KERN: der Beleg wird aufgeloest. Ohne ihn saehe man, DASS eine
        # Waise da ist, aber nicht, wer sie erzeugt hat - und genau das war
        # die Frage, die am 13.08.2026 offenblieb.
        self.assertIsNotNone(fund["beleg"])
        self.assertTrue(fund["beleg"]["vorhanden"])
        self.assertEqual(seq, fund["beleg"]["seq"])
        self.assertEqual(1, fund["beleg"]["actor_id"])
        self.assertEqual("h001", fund["beleg"]["actor"])

        # RW08: die Deutung. 'steht wenigstens im Code' trennt den
        # Reihenfolgefall vom unerklaerlichen Fall - beide gleich zu melden
        # hiesse, dem Leser die Einordnung zu ueberlassen, die das Werkzeug
        # treffen kann.
        self.assertTrue(fund["im_code_katalog"])

    # -- RW04 -----------------------------------------------------------------
    def test_rw04_katalogversatz_ohne_waise_bekommt_eigenen_rueckgabewert(self):
        """
        Zwischen dem Einspielen einer Lieferung und dem Migrationslauf ist
        genau dieser Zustand der Normalfall. Ein Betriebsskript, das ihn wie
        einen Schaden behandelt, wuerde bei jeder Lieferung Alarm schlagen.
        """
        ergebnis, rueckgabe = self._pruefe()
        self.assertEqual(0, ergebnis["anzahl_waisen"])
        self.assertEqual(3, rueckgabe)
        self.assertIn(_NEUES_RECHT,
                      ergebnis["katalogversatz"]["faehigkeiten_nur_im_code"])
        # Die Gegenrichtung ist leer - der Code hinkt hier nicht nach.
        self.assertEqual(
            [], ergebnis["katalogversatz"]["faehigkeiten_nur_in_der_db"])

    # -- RW02b ----------------------------------------------------------------
    def test_rw02b_waise_hat_vorrang_vor_versatz(self):
        """Beides zugleich: der schwerere Befund entscheidet."""
        self.repo.assign_role(1, "supervisor", actor_id=1)
        # Notausgang wie in RW02 - dieselbe Ausgangslage, dieselbe Begruendung.
        self.repo.grant("supervisor", _NEUES_RECHT, scope="alle", actor_id=1,
                        db_katalog_pruefen=False)
        ergebnis, rueckgabe = self._pruefe()
        self.assertTrue(any(ergebnis["katalogversatz"].values()))
        self.assertEqual(2, rueckgabe, "Der Versatz hat die Waise verdeckt.")


class BelegkopplungTests(_MitBestand):

    # -- RW05 -----------------------------------------------------------------
    def test_rw05_gebrochene_belegkopplung(self):
        """
        Eine audit_seq, zu der es keinen Eintrag gibt. Das ist der schwerste
        der hier gesuchten Befunde: die Kopplung ist die Zusage, dass kein
        Grant ohne nachvollziehbare Vergabe existiert.

        Von Hand eingesetzt - ueber das Gateway laesst sich dieser Zustand
        gerade NICHT herstellen, und das ist die gute Nachricht.
        """
        self.con.execute(
            "INSERT INTO rbac_grant (role_code, capability_code, scope, "
            "audit_seq, granted_at) VALUES ('supervisor', ?, 'alle', "
            "999999, 0)", (_ALTES_RECHT,))

        ergebnis, rueckgabe = self._pruefe()
        self.assertEqual(2, rueckgabe)
        self.assertEqual(1, len(ergebnis["gebrochene_belege"]))
        fund = ergebnis["gebrochene_belege"][0]
        self.assertEqual("rbac_grant", fund["tabelle"])
        self.assertEqual("audit_seq", fund["spalte"])
        self.assertEqual(999999, fund["seq"])
        # Der Grant selbst ist KEINE Waise - Rolle und Recht gibt es.
        self.assertEqual([], ergebnis["grants_ohne_faehigkeit"])
        self.assertEqual([], ergebnis["grants_ohne_rolle"])


class UnvollstaendigTests(unittest.TestCase):
    """Was passiert, wenn die Datenbank nicht das ist, was sie sein sollte."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "fremd.db")

    # -- RW07 -----------------------------------------------------------------
    def test_rw07_ohne_rechte_matrix_bricht_es_ab(self):
        con = sqlite3.connect(self.db_path)
        con.execute("CREATE TABLE irgendwas (id INTEGER PRIMARY KEY)")
        con.commit()
        con.close()

        ergebnis, rueckgabe = pruefe_rbac_waisen.pruefe(self.db_path)
        # NICHT 0. Eine Datenbank ohne Rechte-Matrix ist keine gepruefte
        # Datenbank, und 'kein Befund' waere hier die gefaehrlichste Auskunft.
        self.assertEqual(1, rueckgabe)
        self.assertIn("rbac_capability", ergebnis["fehlende_pflichttabellen"])

    # -- RW06 -----------------------------------------------------------------
    def test_rw06_entfallene_pruefung_wird_benannt(self):
        """
        Grundregel 1: was nicht geprueft wurde, wird gesagt. Sonst liest sich
        ein leerer Befund wie eine Unbedenklichkeitsbescheinigung.
        """
        con = sqlite3.connect(self.db_path)
        con.executescript(
            "CREATE TABLE rbac_capability (code TEXT PRIMARY KEY, "
            "  label TEXT, description TEXT, created_at INTEGER);"
            "CREATE TABLE rbac_role (code TEXT PRIMARY KEY, label TEXT);"
            "CREATE TABLE rbac_grant (id INTEGER PRIMARY KEY, "
            "  role_code TEXT, capability_code TEXT, scope TEXT, "
            "  audit_seq INTEGER, granted_at INTEGER, revoked_at INTEGER, "
            "  revoke_audit_seq INTEGER, note TEXT);")
        con.commit()
        con.close()

        ergebnis, _rueckgabe = pruefe_rbac_waisen.pruefe(self.db_path)
        entfallen = ergebnis["uebersprungene_pruefungen_wegen_fehlender_tabelle"]
        for tabelle in ("person_role", "person", "audit_log"):
            self.assertIn(tabelle, entfallen)

    # -- RW07b ----------------------------------------------------------------
    def test_rw07b_der_aufruf_ueber_die_befehlszeile_meldet_dasselbe(self):
        """
        Die Rueckgabewerte des CLI-Aufrufs sind Teil der Zusage an das
        Betriebsskript und werden deshalb ueber main() gemessen, nicht nur
        ueber pruefe().
        """
        self.assertEqual(
            1, pruefe_rbac_waisen.main(
                ["--db", os.path.join(self._tmp, "gibt-es-nicht.db")]))


if __name__ == "__main__":
    unittest.main()
