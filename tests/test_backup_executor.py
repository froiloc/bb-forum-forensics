# =============================================================================
# tests/test_backup_executor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# Testsuite fuer Build 353: BackupExecutor (VACUUM INTO + integrity_check +
# SHA512 + Manifest + Retention).
#
# BE01 — run(): erzeugt je Quelle eine integere Backup-Kopie; Manifest; ok.
# BE02 — user_version der Quelle landet im Dateinamen ('_v5_').
# BE03 — verweigert bei fehlgeschlagener Vorabpruefung (plan.ok=False).
# BE04 — Pro-DB-Fehlerisolation: kaputte DB -> error, andere ok, Gesamt=nicht ok.
# BE05 — Retention: je Label bleiben retention_count neueste; aeltere geloescht.
#
# Version: v0.7.353 · Build: 353 · 2026-07-10
# =============================================================================

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.backup.backup_config import BackupConfig
from management.backup.backup_planner import BackupPlanner
from management.backup.backup_executor import BackupExecutor
from management.migration_fleet.harness.backup import BackupTool


def _mkdb(path, user_version=0, rows=3):
    con = sqlite3.connect(str(path))
    try:
        con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        con.executemany("INSERT INTO t(v) VALUES(?)",
                        [("x" * 20,) for _ in range(rows)])
        if user_version:
            con.execute("PRAGMA user_version=%d" % user_version)
        con.commit()
    finally:
        con.close()


class BackupExecutorTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        base = Path(self._tmp)
        (base / "data").mkdir()
        (base / "data" / "evidence").mkdir()
        (base / "data" / "forensic").mkdir()
        (base / "data" / "assets").mkdir()
        self._dest = str(base / "backups")
        os.mkdir(self._dest)

        _mkdb(base / "data" / "coordinator.db", user_version=5)
        _mkdb(base / "data" / "evidence" / "evidence_18.db")

        self._base = base
        self._paths = {
            "coordinator_db": str(base / "data" / "coordinator.db"),
            "forensic_db_dir": str(base / "data" / "forensic"),
            "evidence_db_dir": str(base / "data" / "evidence"),
            "assets_db_dir": str(base / "data" / "assets"),
        }

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _cfg(self, **over):
        base = dict(dest_dir=self._dest, retention_count=7,
                    min_free_factor=1.3, checkpoint="passive",
                    include_shared_dbs=False)
        base.update(over)
        return BackupConfig(**base)

    def _plan(self, cfg):
        return BackupPlanner(self._paths, cfg).plan()

    # BE01 -------------------------------------------------------------------
    def test_be01_run_creates_verified_backups(self):
        cfg = self._cfg()
        run = BackupExecutor(cfg).run(self._plan(cfg))
        self.assertTrue(run.ok, run.reason)
        self.assertEqual(len(run.results), 2)  # coordinator + evidence_18
        for r in run.results:
            self.assertIsNone(r.error)
            self.assertTrue(r.integrity_ok)
            self.assertTrue(os.path.isfile(r.backup_path))
            self.assertTrue(r.backup_path.endswith(".backup.db"))
            # SHA512 stimmt mit der Datei ueberein.
            self.assertTrue(BackupTool.verify_backup(r.backup_path, r.sha512))
        # Manifest geschrieben und parsebar.
        self.assertTrue(os.path.isfile(run.manifest_path))
        with open(run.manifest_path, encoding="ascii") as fh:
            man = json.load(fh)
        self.assertTrue(man["ok"])
        self.assertEqual(len(man["results"]), 2)

    # BE02 -------------------------------------------------------------------
    def test_be02_user_version_in_filename(self):
        cfg = self._cfg()
        run = BackupExecutor(cfg).run(self._plan(cfg))
        coord = [r for r in run.results if r.label == "coordinator"][0]
        self.assertEqual(coord.user_version, 5)
        self.assertIn("_v5_", os.path.basename(coord.backup_path))

    # BE03 -------------------------------------------------------------------
    def test_be03_refuses_on_failed_precheck(self):
        cfg = self._cfg(min_free_factor=1e15)  # unmoeglich viel Platz
        plan = self._plan(cfg)
        self.assertFalse(plan.ok)
        run = BackupExecutor(cfg).run(plan)
        self.assertFalse(run.ok)
        self.assertEqual(run.results, [])
        self.assertIn("Vorabpruefung", run.reason)
        # Es darf NICHTS geschrieben worden sein.
        self.assertEqual(
            [n for n in os.listdir(self._dest) if n.endswith(".backup.db")], [])

    # BE04 -------------------------------------------------------------------
    def test_be04_per_db_failure_isolation(self):
        # Kaputte "DB" ins evidence-Verzeichnis legen (kein gueltiges SQLite).
        with open(self._base / "data" / "evidence" / "evidence_bad.db",
                  "wb") as fh:
            fh.write(b"das ist keine datenbank")
        cfg = self._cfg()
        run = BackupExecutor(cfg).run(self._plan(cfg))
        self.assertFalse(run.ok)  # eine DB kaputt -> Gesamt nicht ok
        bad = [r for r in run.results if r.label == "evidence_bad"][0]
        good = [r for r in run.results if r.label == "evidence_18"][0]
        self.assertIsNotNone(bad.error)          # Fehler erfasst
        self.assertIsNone(good.error)            # andere DB dennoch gesichert
        self.assertTrue(good.integrity_ok)
        self.assertTrue(os.path.isfile(good.backup_path))

    # BE05 -------------------------------------------------------------------
    def test_be05_retention_prunes_old(self):
        # Vorab 4 alte coordinator-Generationen mit sortierbaren ts anlegen.
        old_ts = ["20260101T000000Z", "20260102T000000Z",
                  "20260103T000000Z", "20260104T000000Z"]
        for ts in old_ts:
            name = "coordinator_v5_%s_host.backup.db" % ts
            with open(os.path.join(self._dest, name), "wb") as fh:
                fh.write(b"alt")
        cfg = self._cfg(retention_count=2, include_shared_dbs=False)
        run = BackupExecutor(cfg).run(self._plan(cfg))
        self.assertTrue(run.ok, run.reason)
        # Nach dem Lauf: nur 2 neueste coordinator-Backups behalten.
        coord_files = sorted(
            n for n in os.listdir(self._dest)
            if n.startswith("coordinator_v") and n.endswith(".backup.db"))
        self.assertEqual(len(coord_files), 2)
        # Die aeltesten (2026-01-01/02) muessen weg sein.
        self.assertTrue(all("20260101" not in n and "20260102" not in n
                            for n in coord_files))
        # Pruned-Liste enthaelt geloeschte Dateien.
        self.assertGreaterEqual(len(run.pruned), 1)


    # =========================================================================
    # BUILD 617 - DIE KENNZEICHNUNG DES SATZES
    #
    # Entscheidung mc, 2026-07-31: Der Sicherungssatz bleibt NICHT punktgleich
    # (eine taegliche Sicherung soll nebenher laufen koennen), wird aber als
    # solcher gekennzeichnet. Der Preis dieser Entscheidung ist, dass jeder,
    # der den Satz benutzt, von der Einschraenkung WISSEN muss - und deshalb
    # pruefen die folgenden Tests, dass die Kennzeichnung wirklich ankommt und
    # nicht nur irgendwo abgelegt ist.
    # =========================================================================

    def test_be05_manifest_kennzeichnet_den_satz_als_nicht_punktgleich(self):
        """
        BE05 - Das Manifest sagt ausdruecklich, dass der Satz keinen
        gemeinsamen Zeitpunkt abbildet, und begruendet es.

        Ein Feld 'punktgleich: false' allein waere zu wenig: wer das Manifest
        im Ernstfall liest, hat keine Zeit, sich die Folge selbst
        herzuleiten. Der Klartext gehoert dazu.
        """
        cfg = self._cfg(include_shared_dbs=True)
        run = BackupExecutor(cfg).run(self._plan(cfg))
        self.assertTrue(run.ok, run.reason)

        with open(run.manifest_path, encoding="ascii") as fh:
            manifest = json.load(fh)

        self.assertIs(manifest["punktgleich"], False)
        self.assertIn("NICHT PUNKTGLEICH", manifest["punktgleich_hinweis"])
        self.assertIn("ruhiger Zustand",
                      manifest["punktgleich_hinweis"])
        # Die Spanne des Satzes ist ablesbar.
        self.assertIn("satz_von", manifest)
        self.assertIn("satz_bis", manifest)
        self.assertLessEqual(manifest["satz_von"], manifest["satz_bis"])

    def test_be06_jede_datenbank_traegt_einen_eigenen_zeitpunkt(self):
        """
        BE06 - Der Versatz zwischen den Kopien ist ABLESBAR.

        Bis Build 616 trug das Manifest nur EINEN Zeitstempel fuer den ganzen
        Lauf. Damit sah der Satz punktgleich aus, ohne es zu sein - das ist
        die schlechteste aller Lagen: eine falsche Auskunft, die wie eine
        richtige aussieht.
        """
        cfg = self._cfg(include_shared_dbs=True)
        run = BackupExecutor(cfg).run(self._plan(cfg))
        self.assertTrue(run.ok, run.reason)
        self.assertGreater(len(run.results), 1,
                           "Der Test braucht mehr als eine Quelle.")

        for r in run.results:
            self.assertTrue(r.begonnen_ts, "%s ohne Beginn" % r.label)
            self.assertTrue(r.beendet_ts, "%s ohne Ende" % r.label)
            self.assertLessEqual(r.begonnen_ts, r.beendet_ts)

        # Und die Zeitpunkte stehen auch im Manifest, nicht nur im Ergebnis.
        with open(run.manifest_path, encoding="ascii") as fh:
            manifest = json.load(fh)
        for eintrag in manifest["results"]:
            self.assertTrue(eintrag["begonnen_ts"])
            self.assertTrue(eintrag["beendet_ts"])

    def test_be07_waehrend_des_laufs_entstandene_db_wird_benannt(self):
        """
        BE07 - Eine Fall-Datenbank, die es beim Planen noch nicht gab, wird
        NICHT gesichert - aber sie wird GENANNT.

        Bis Build 616 verschwand sie still: der Planer liest die Verzeichnisse
        einmal vorher, und in die Liste der fehlenden Dateien kam sie nicht.
        Gesichert wird sie auch jetzt nicht - das machte den Satz noch
        ungleichzeitiger und der Lauf haette kein definiertes Ende. Aber
        Grundregel 1 verlangt, dass sie nicht unbemerkt fehlt.
        """
        cfg = self._cfg(include_shared_dbs=False)
        plan = self._plan(cfg)
        # Sie entsteht NACH dem Planen - genau der Fall aus der Nachpruefung.
        spaet = Path(self._tmp) / "data" / "evidence" / "evidence_99.db"
        _mkdb(spaet)

        run = BackupExecutor(cfg).run(plan)

        self.assertEqual([os.path.abspath(str(spaet))], run.nachzuegler)
        gesichert = {r.label for r in run.results}
        self.assertNotIn("evidence_99", gesichert,
                         "Der Nachzuegler darf NICHT gesichert werden.")
        with open(run.manifest_path, encoding="ascii") as fh:
            manifest = json.load(fh)
        self.assertEqual([os.path.abspath(str(spaet))],
                         manifest["nicht_gesichert_weil_neu"])

    def test_be09_die_kennzeichnung_erreicht_auch_die_konsole(self):
        """
        BE09 - Der Vermerk steht in der AUSGABE von 'run', nicht nur im
        Manifest.

        Geprueft am Quelltext und nicht am Verhalten: ein vollstaendiger
        cmd_run-Lauf braucht eine eingerichtete coordinator.db samt
        Belegkette und Personendatensatz - mehr Gestell als Aussage. Was hier
        zu sichern ist, ist eine einzige Frage: geht der Vermerk auf die
        Konsole? Dasselbe Verfahren wie CT11 beim Dachwerkzeug.

        WARUM DAS NICHT NEBENSAECHLICH IST: mc hat sich fuer die
        Kennzeichnung und gegen ein Wartungsfenster entschieden. Der Preis
        dieser Entscheidung ist, dass die Einschraenkung jeden erreicht, der
        den Satz benutzt. Ein Hinweis, den man erst findet, wenn man ihn
        sucht, erreicht im Ernstfall niemanden.
        """
        quelle = (Path(__file__).resolve().parent.parent
                  / "management" / "backup" / "backup_admin.py"
                  ).read_text(encoding="utf-8")
        self.assertIn("PUNKTGLEICH_VERMERK", quelle,
                      "backup_admin gibt den Vermerk nicht aus.")
        self.assertIn("run.nachzuegler", quelle,
                      "backup_admin nennt die Nachzuegler nicht.")
        # Und der Vermerk kommt aus EINER Quelle - sonst laufen Manifest und
        # Konsole auseinander.
        self.assertNotIn("NICHT PUNKTGLEICH:", quelle,
                         "Der Vermerktext ist in backup_admin abgeschrieben "
                         "statt eingebunden.")

    def test_be08_ohne_nachzuegler_bleibt_die_liste_leer(self):
        """
        BE08 - Die Gegenprobe. Eine Meldung, die immer kommt, wird nicht
        gelesen; der Regelfall muss still sein.
        """
        cfg = self._cfg(include_shared_dbs=True)
        run = BackupExecutor(cfg).run(self._plan(cfg))
        self.assertEqual([], run.nachzuegler)


if __name__ == "__main__":
    unittest.main()
