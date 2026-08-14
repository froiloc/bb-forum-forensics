# =============================================================================
# tests/test_backup_nachzuegler.py
# IT-Forensisches Ermittlungswerkzeug - Datensicherung
# =============================================================================
# Testsuite fuer die Nachzueglererkennung (Vorgang dc63928d-9d53-4532-931e-
# 66efd7ac03e0, dritte Forderung: "In beiden Faellen ist die Erfassungsluecke
# zu schliessen: waehrend des Laufs neu entstandene Fall-Datenbanken gehoeren
# mindestens in die Liste der fehlenden").
#
# WORUM ES GEHT: Der Planer liest die Fall-Verzeichnisse EINMAL VOR dem Lauf.
# Entsteht waehrend des Laufs eine evidence_<uid>.db, wird sie nicht mehr
# gesichert. Sie muss dann wenigstens GENANNT werden - sonst fehlt sie im
# Satz, ohne dass es jemand erfaehrt (Grundregel 1).
#
# BUILD 617 HAT DAS GEBAUT, ABER FALSCH. Am 14.08.2026 an einem echten Lauf
# gemessen, drei Lagen, und in allen dreien war das Ergebnis unbrauchbar:
#
#   A) Regelfall - gemeldet wurden 'evidence_4711.db' UND
#      'approved_reports.db'. Die zweite liegt seit jeher dort und ist
#      lediglich nicht Teil des Sicherungssatzes.
#   B) mit 'include_shared_dbs: false' - zusaetzlich default.db,
#      templates.db und translations.db. VIER Falschmeldungen je Lauf.
#   C) Fall-Verzeichnis beim Planen LEER - 'evidence_4711.db' wurde GAR
#      NICHT gemeldet. Der echte Fund blieb ausgerechnet dann aus, wenn der
#      erste Fall eines Verzeichnisses entsteht.
#
# URSACHE (backup_executor._nachzuegler, Fassung Build 617): die zu
# durchsuchenden Verzeichnisse wurden aus plan.sources abgeleitet, und "neu"
# hiess "nicht gesichert". Ein leeres Verzeichnis steuert keine Quelle bei
# und wurde deshalb nie durchsucht (C); jede nicht gesicherte Datenbank neben
# der coordinator.db galt als neu (A/B).
#
# NZ01 - LAGE A: im Regelfall wird GENAU die neue Fall-Datenbank gemeldet.
# NZ02 - LAGE B: 'include_shared_dbs: false' aendert daran nichts. Die
#        geteilten Datenbanken sind nicht 'neu', sie sind ausgeschlossen.
# NZ03 - LAGE C: ein beim Planen LEERES Fall-Verzeichnis wird trotzdem
#        beobachtet. Der wichtigste Fall der Reihe.
# NZ04 - Ein ruhiger Lauf meldet NICHTS. Eine Liste, die immer etwas
#        enthaelt, wird nicht gelesen.
# NZ05 - Die Bestandsaufnahme des Planers nennt alle drei Fall-Verzeichnisse,
#        auch die leeren, und alle vorgefundenen Dateien.
# NZ06 - Ein Plan OHNE Bestandsaufnahme fuehrt zu einer leeren Liste und
#        nicht zu einer falschen (Rueckwaertsvertraeglichkeit).
# NZ07 - Der Fund steht im Manifest unter 'nicht_gesichert_weil_neu'.
# NZ08 - Eine waehrend des Laufs GELOESCHTE Fall-Datenbank erscheint NICHT
#        als Nachzuegler. Sie ist ein anderer Vorgang und stuende hier
#        falsch.
# NZ09 - Was nicht auf '.db' endet, zaehlt nicht - auch nicht ein neues
#        Unterverzeichnis.
#
# ZUR VORRICHTUNG: Gefahren wird ein ECHTER Lauf mit BackupExecutor gegen
# Wegwerf-Datenbanken unter /tmp. Die neue Datei entsteht ueber einen Haken
# an _backup_one, also WIRKLICH zwischen zwei Kopien - nicht davor und nicht
# danach. Eine Simulation haette hier nichts bewiesen: die Frage ist gerade,
# was ein Lauf sieht, der schon begonnen hat.
#
# Version: v0.8.721 - Build: 721 - 2026-08-14
# =============================================================================

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.backup.backup_config import BackupConfig
from management.backup.backup_executor import BackupExecutor
from management.backup.backup_planner import BackupPlan, BackupPlanner


def _mkdb(pfad, zeilen=3):
    con = sqlite3.connect(str(pfad))
    try:
        con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        con.executemany("INSERT INTO t(v) VALUES(?)",
                        [("x" * 20,) for _ in range(zeilen)])
        con.commit()
    finally:
        con.close()


class NachzueglerTests(unittest.TestCase):
    """Gemeinsame Vorrichtung: ein Bestand, wie ihn die Anlage wirklich hat."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        basis = Path(self._tmp)
        (basis / "data").mkdir()
        for name in ("evidence", "forensic", "assets"):
            (basis / "data" / name).mkdir()
        self._dest = str(basis / "backups")
        os.mkdir(self._dest)
        self._basis = basis

        # Die Einzeldatenbanken neben der coordinator.db - einschliesslich
        # der beiden, die NICHT gesichert werden. Genau sie haben die alte
        # Fassung in die Irre gefuehrt.
        for name in ("coordinator.db", "default.db", "templates.db",
                     "translations.db", "approved_reports.db"):
            _mkdb(basis / "data" / name)
        _mkdb(basis / "data" / "forensic" / "forensic_18.db")

        self._paths = {
            "coordinator_db": str(basis / "data" / "coordinator.db"),
            "forensic_db_dir": str(basis / "data" / "forensic"),
            "evidence_db_dir": str(basis / "data" / "evidence"),
            "assets_db_dir": str(basis / "data" / "assets"),
            "default_db": str(basis / "data" / "default.db"),
            "templates_db": str(basis / "data" / "templates.db"),
            "translations_db": str(basis / "data" / "translations.db"),
        }

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------- Helfer
    def _evidence_18(self):
        """Das evidence-Verzeichnis fuellen (Lagen A und B)."""
        _mkdb(self._basis / "data" / "evidence" / "evidence_18.db")

    def _cfg(self, shared=True):
        return BackupConfig(dest_dir=self._dest, retention_count=7,
                            min_free_factor=1.3, checkpoint="passive",
                            include_shared_dbs=shared)

    def _lauf(self, shared=True, waehrenddessen=None):
        """
        Einen echten Lauf fahren und dabei etwas dazwischenwerfen.

        'waehrenddessen' wird NACH der ersten Kopie ausgefuehrt - also
        mitten im Lauf. Genau darum geht es: was zwischen zwei Kopien
        geschieht, ist der Kern dieses Vorgangs.
        """
        cfg = self._cfg(shared)
        plan = BackupPlanner(self._paths, cfg).plan()
        self.assertTrue(plan.ok, plan.reason)
        ex = BackupExecutor(cfg)
        urspruenglich = ex._backup_one
        zaehler = {"n": 0}

        def haken(src, *args, **kwargs):
            ergebnis = urspruenglich(src, *args, **kwargs)
            zaehler["n"] += 1
            if zaehler["n"] == 1 and waehrenddessen is not None:
                waehrenddessen()
            return ergebnis

        ex._backup_one = haken
        return plan, ex.run(plan)

    @staticmethod
    def _namen(pfade):
        return sorted(os.path.basename(p) for p in pfade)

    # NZ01 -------------------------------------------------------------------
    def test_nz01_lage_a_genau_die_neue_datenbank(self):
        self._evidence_18()
        neu = self._basis / "data" / "evidence" / "evidence_4711.db"
        _plan, lauf = self._lauf(shared=True,
                                 waehrenddessen=lambda: _mkdb(neu))
        self.assertEqual(self._namen(lauf.nachzuegler), ["evidence_4711.db"])
        # Die alte Fassung meldete hier zusaetzlich 'approved_reports.db' -
        # eine Datenbank, die seit jeher dort liegt.
        self.assertNotIn("approved_reports.db",
                         self._namen(lauf.nachzuegler))

    # NZ02 -------------------------------------------------------------------
    def test_nz02_lage_b_geteilte_datenbanken_sind_nicht_neu(self):
        """
        'include_shared_dbs: false' schliesst default/templates/translations
        AUS. Ausgeschlossen ist nicht dasselbe wie neu entstanden - die alte
        Fassung machte daraus vier Falschmeldungen je Lauf.
        """
        self._evidence_18()
        neu = self._basis / "data" / "evidence" / "evidence_4711.db"
        _plan, lauf = self._lauf(shared=False,
                                 waehrenddessen=lambda: _mkdb(neu))
        self.assertEqual(self._namen(lauf.nachzuegler), ["evidence_4711.db"])
        for falsch in ("default.db", "templates.db", "translations.db",
                       "approved_reports.db"):
            self.assertNotIn(falsch, self._namen(lauf.nachzuegler))

    # NZ03 -------------------------------------------------------------------
    def test_nz03_lage_c_leeres_verzeichnis_wird_trotzdem_beobachtet(self):
        """
        DER WICHTIGSTE FALL DER REIHE. Das evidence-Verzeichnis ist beim
        Planen leer und steuert keine Quelle bei. Die alte Fassung leitete
        die zu durchsuchenden Verzeichnisse aus plan.sources ab und sah
        deshalb gar nicht hinein: der erste Fall eines Verzeichnisses konnte
        nie als Nachzuegler auffallen.
        """
        neu = self._basis / "data" / "evidence" / "evidence_4711.db"
        plan, lauf = self._lauf(shared=True,
                                waehrenddessen=lambda: _mkdb(neu))
        # Beim Planen war dort nichts - und trotzdem wird es beobachtet.
        self.assertEqual([p for p in plan.vorgefunden if "evidence" in p], [])
        self.assertTrue(any(p.endswith("evidence")
                            for p in plan.fall_verzeichnisse))
        self.assertEqual(self._namen(lauf.nachzuegler), ["evidence_4711.db"])

    # NZ04 -------------------------------------------------------------------
    def test_nz04_ruhiger_lauf_meldet_nichts(self):
        self._evidence_18()
        _plan, lauf = self._lauf(shared=True, waehrenddessen=None)
        self.assertEqual(list(lauf.nachzuegler), [])

    # NZ05 -------------------------------------------------------------------
    def test_nz05_bestandsaufnahme_des_planers(self):
        self._evidence_18()
        plan = BackupPlanner(self._paths, self._cfg()).plan()
        verzeichnisse = sorted(os.path.basename(d)
                               for d in plan.fall_verzeichnisse)
        # ALLE DREI, auch das leere 'assets'.
        self.assertEqual(verzeichnisse, ["assets", "evidence", "forensic"])
        self.assertEqual(self._namen(plan.vorgefunden),
                         ["evidence_18.db", "forensic_18.db"])
        # Die Einzeldatenbanken gehoeren NICHT in die Bestandsaufnahme: sie
        # liegen nicht in den Fall-Verzeichnissen.
        self.assertNotIn("coordinator.db", self._namen(plan.vorgefunden))

    # NZ06 -------------------------------------------------------------------
    def test_nz06_plan_ohne_bestandsaufnahme_meldet_nichts(self):
        """
        Ein von Hand gebauter Plan traegt keine Bestandsaufnahme. Dann ist
        keine Aussage ueber 'neu' moeglich, und die Liste bleibt leer - eine
        LEERE Liste ist hier richtig, eine falsche waere schlimmer als keine.
        Zugleich der Nachweis, dass die neuen Felder Vorgabewerte haben und
        bestehende Aufrufe gueltig bleiben.
        """
        self._evidence_18()
        cfg = self._cfg()
        voll = BackupPlanner(self._paths, cfg).plan()
        knapp = BackupPlan(
            sources=voll.sources, missing=[], total_size=voll.total_size,
            required_free=voll.required_free, free_at_dest=voll.free_at_dest,
            dest_dir=voll.dest_dir, ok=True, reason="")
        self.assertEqual(knapp.fall_verzeichnisse, ())
        self.assertEqual(knapp.vorgefunden, ())
        _mkdb(self._basis / "data" / "evidence" / "evidence_4711.db")
        self.assertEqual(BackupExecutor(cfg)._nachzuegler(knapp), [])

    # NZ07 -------------------------------------------------------------------
    def test_nz07_der_fund_steht_im_manifest(self):
        self._evidence_18()
        neu = self._basis / "data" / "evidence" / "evidence_4711.db"
        _plan, lauf = self._lauf(shared=True,
                                 waehrenddessen=lambda: _mkdb(neu))
        self.assertTrue(lauf.manifest_path)
        with open(lauf.manifest_path, encoding="ascii") as fh:
            manifest = json.load(fh)
        self.assertEqual(
            self._namen(manifest["nicht_gesichert_weil_neu"]),
            ["evidence_4711.db"])

    # NZ08 -------------------------------------------------------------------
    def test_nz08_geloeschte_datenbank_ist_kein_nachzuegler(self):
        """
        Verschwindet eine Fall-Datenbank waehrend des Laufs, ist das ein
        Befund - aber ein anderer. Er steht als 'error' im Ergebnis der
        betroffenen Quelle und hat unter 'nicht_gesichert_weil_neu' nichts
        verloren. Der Vergleich VORHER GEGEN NACHHER haelt beides
        auseinander; die alte Regel 'nicht gesichert = neu' haette die
        geloeschte Datei nicht gefunden, dafuer aber andere erfunden.
        """
        self._evidence_18()
        alt = self._basis / "data" / "evidence" / "evidence_18.db"
        _plan, lauf = self._lauf(shared=True,
                                 waehrenddessen=lambda: os.remove(alt))
        self.assertEqual(list(lauf.nachzuegler), [])

    # NZ09 -------------------------------------------------------------------
    def test_nz09_nur_db_dateien_zaehlen(self):
        self._evidence_18()
        verzeichnis = self._basis / "data" / "evidence"

        def dazwischen():
            (verzeichnis / "notiz.txt").write_text("kein Beleg",
                                                   encoding="utf-8")
            (verzeichnis / "evidence_4711.db-journal").write_text(
                "auch nicht", encoding="utf-8")
            (verzeichnis / "unterordner.db").mkdir()

        _plan, lauf = self._lauf(shared=True, waehrenddessen=dazwischen)
        # 'unterordner.db' endet zwar auf '.db', ist aber keine Datei -
        # os.path.isfile faengt das ab.
        self.assertEqual(list(lauf.nachzuegler), [])


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
