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
# Build 625 — DIE AUFBEWAHRUNG ZAEHLT NUR BRAUCHBARE GENERATIONEN
# (Vorgang 651e6d84, kritisch; dazu der beim Messen gefundene zweite Befund):
#
# BE10 — eine nicht belegte Kopie verdraengt KEINE gute Generation
# BE11 — sie wird beiseitegelegt statt geloescht, und das Namensmuster
#        erfasst sie danach nicht mehr
# BE12 — GEMESSENER BEFUND: eine 0-Byte-Datei unter dem zaehlenden Namen
#        besteht 'integrity_check', zaehlt aber trotzdem nicht als Generation
# BE13 — ein Label ohne belegte Kopie in diesem Lauf wird nicht beschnitten
#        und steht namentlich im Manifest
# BE14 — ein misslungenes Aufraeumen wird gemeldet, nicht verschluckt
# BE15 — auch die beiseitegelegten Dateien bleiben begrenzt
# BE16 — das Manifest legt ueber das Aufraeumen Rechenschaft ab
#
# ZUR TESTVORRICHTUNG VON BE05: sie schrieb bis Build 624 den Text 'alt' in
# die Dateien, die alte Generationen darstellen sollten. Das sind keine
# SQLite-Dateien - eine Sicherung ist eine. Mit der Nachschau aus Build 625
# faellt das auf, und der Test schlug fehl. Die Vorrichtung legt jetzt
# richtige Sicherungen an. Das ist keine Anpassung an den Code, sondern die
# Beseitigung genau des Musters, das Vorgang c3f80e54 beschreibt: eine
# schwache Pruefung erlaubt eine unwirkliche Vorrichtung, und die verdeckt
# dann, was die Pruefung haette finden sollen.
#
# Version: v0.8.625 · Build: 625 · 2026-08-01
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
from management.backup.backup_executor import (
    DEFEKT_ENDUNG, BackupExecutor, Quellmerkmale,
)
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
            # ECHTE Sicherungsdateien: eine Generation ist eine SQLite-Datei.
            # Mit einem Textschnipsel liesse sich seit Build 625 nichts mehr
            # belegen - und mit ihm liesse sich auch nichts mehr WIDERLEGEN.
            _mkdb(Path(self._dest) / name, user_version=5)
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


# =============================================================================
# BUILD 625 - DIE AUFBEWAHRUNG ZAEHLT NUR BRAUCHBARE GENERATIONEN
#
# Vorgang 651e6d84 (kritisch): _prune sortierte allein nach dem Zeitstempel im
# Dateinamen. Eine defekte Kopie zaehlte als juengste Generation und
# verdraengte die aelteste gute - nach retention_count solchen Laeufen war von
# der betroffenen Datenbank keine brauchbare Sicherung mehr da.
#
# Beim Messen dazugekommen: 'PRAGMA integrity_check' allein zertifiziert
# nichts. Eine abgebrochene 'VACUUM INTO' hinterlaesst eine Teildatei, die
# beim ersten Oeffnen auf 0 Byte zurueckgerollt wird - und darauf meldet
# integrity_check 'ok'.
# =============================================================================

class _ExecutorMitFalschenMerkmalen(BackupExecutor):
    """
    Ein Executor, der die QUELLE falsch vermisst.

    So entsteht der Fall 'Kopie erzeugt, aber nicht belegbar' OHNE die
    Beurteilung selbst zu faelschen: _kopie_beurteilen laeuft unveraendert
    und stellt die Abweichung wirklich fest. Ein gefaelschtes Urteil haette
    nur die Verdrahtung geprueft, nicht die Pruefung.
    """

    def _quellmerkmale(self, src_path):
        echt = super()._quellmerkmale(src_path)
        return Quellmerkmale(user_version=echt.user_version + 1000,
                             seiten=echt.seiten,
                             schema_objekte=echt.schema_objekte)


class AufbewahrungTests(unittest.TestCase):
    """Dieselbe Vorrichtung wie oben, aber auf die Aufbewahrung gerichtet."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        base = Path(self._tmp)
        (base / "data").mkdir()
        for d in ("evidence", "forensic", "assets"):
            (base / "data" / d).mkdir()
        self._dest = str(base / "backups")
        os.mkdir(self._dest)
        _mkdb(base / "data" / "coordinator.db", user_version=5)
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
        base = dict(dest_dir=self._dest, retention_count=2,
                    min_free_factor=1.3, checkpoint="passive",
                    include_shared_dbs=False)
        base.update(over)
        return BackupConfig(**base)

    def _plan(self, cfg):
        return BackupPlanner(self._paths, cfg).plan()

    def _alte_generationen(self, *ts_liste, label="coordinator", version=5):
        for ts in ts_liste:
            _mkdb(Path(self._dest) / ("%s_v%d_%s_host.backup.db"
                                      % (label, version, ts)),
                  user_version=version)

    def _zaehlende(self, label="coordinator"):
        return sorted(n for n in os.listdir(self._dest)
                      if n.startswith(label + "_v")
                      and n.endswith(".backup.db"))

    # --- BE10 ---------------------------------------------------------------
    def test_be10_nicht_belegte_kopie_verdraengt_keine_gute_generation(self):
        """
        DER KERN DES VORGANGS 651e6d84. Zwei gute Generationen liegen da,
        retention_count ist 2. Der Lauf erzeugt eine Kopie, die sich nicht
        belegen laesst. Vorher waere die aeltere gute Generation dafuer
        geloescht worden.
        """
        self._alte_generationen("20260101T000000Z", "20260102T000000Z")
        cfg = self._cfg(retention_count=2)
        run = _ExecutorMitFalschenMerkmalen(cfg).run(self._plan(cfg))

        self.assertFalse(run.ok)
        behalten = self._zaehlende()
        self.assertEqual(len(behalten), 2, behalten)
        self.assertTrue(any("20260101" in n for n in behalten),
                        "die aelteste GUTE Generation wurde verdraengt")
        self.assertTrue(any("20260102" in n for n in behalten))
        self.assertEqual([], run.pruned, "es wurde etwas geloescht")

    # --- BE11 ---------------------------------------------------------------
    def test_be11_nicht_belegte_kopie_wird_beiseitegelegt_nicht_geloescht(self):
        """
        Sie bleibt als Beleg liegen - an einer Teildatei sieht man, woran der
        Lauf gescheitert ist -, traegt aber den zaehlenden Namen nicht mehr.
        """
        cfg = self._cfg()
        run = _ExecutorMitFalschenMerkmalen(cfg).run(self._plan(cfg))
        ergebnis = [r for r in run.results if r.label == "coordinator"][0]

        self.assertFalse(ergebnis.integrity_ok)
        self.assertIn("user_version", ergebnis.error or "")
        self.assertTrue(ergebnis.backup_path.endswith(DEFEKT_ENDUNG),
                        ergebnis.backup_path)
        self.assertTrue(os.path.isfile(ergebnis.backup_path),
                        "der Beleg wurde geloescht statt beiseitegelegt")
        self.assertEqual([], self._zaehlende(),
                         "sie traegt weiter den zaehlenden Namen")

    # --- BE12 ---------------------------------------------------------------
    def test_be12_leere_datei_besteht_integrity_check_zaehlt_aber_nicht(self):
        """
        DER GEMESSENE BEFUND (2026-08-01). Erst wird belegt, dass eine leere
        SQLite-Datei 'integrity_check' BESTEHT - sonst waere die Pruefung
        dahinter nur eine Behauptung. Dann, dass sie trotzdem nicht als
        Generation zaehlt.
        """
        leer = Path(self._dest) / "coordinator_v5_20260103T000000Z_host.backup.db"
        leer.write_bytes(b"")

        con = sqlite3.connect(str(leer))
        try:
            befund = con.execute("PRAGMA integrity_check").fetchall()
        finally:
            con.close()
        self.assertEqual([("ok",)], befund,
                         "Vorbedingung: integrity_check meldet auf einer "
                         "leeren Datei 'ok'")

        self._alte_generationen("20260101T000000Z", "20260102T000000Z")
        cfg = self._cfg(retention_count=2)
        run = BackupExecutor(cfg).run(self._plan(cfg))

        self.assertTrue(run.ok, run.reason)
        self.assertTrue(any(str(leer) in e for e in run.beiseite_gelegt),
                        run.beiseite_gelegt)
        self.assertFalse(leer.exists())
        self.assertTrue((Path(str(leer) + DEFEKT_ENDUNG)).exists())
        # Und die beiden guten Altgenerationen? Eine davon darf weichen - der
        # Lauf hat eine belegte Kopie erzeugt, also ist Beschneiden richtig.
        behalten = self._zaehlende()
        self.assertEqual(len(behalten), 2, behalten)
        self.assertTrue(any("20260102" in n for n in behalten),
                        "die juengere gute Generation fehlt")

    # --- BE13 ---------------------------------------------------------------
    def test_be13_label_ohne_neue_kopie_wird_nicht_beschnitten(self):
        """
        Aufbewahrung heisst 'die N neuesten behalten'. Wer keine hinzufuegt,
        muss auch keine wegnehmen - sonst schrumpft der Bestand eines Falls,
        dessen Datenbank es nicht mehr gibt, bis auf null.
        """
        self._alte_generationen("20260101T000000Z", "20260102T000000Z",
                                "20260103T000000Z", label="evidence_99",
                                version=3)
        cfg = self._cfg(retention_count=1)
        run = BackupExecutor(cfg).run(self._plan(cfg))

        self.assertTrue(run.ok, run.reason)
        self.assertEqual(3, len(self._zaehlende("evidence_99")))
        self.assertTrue(any("evidence_99" in e for e in run.nicht_beschnitten),
                        run.nicht_beschnitten)
        # Das eigene Label wurde sehr wohl beschnitten.
        self.assertEqual(1, len(self._zaehlende("coordinator")))

    # --- BE14 ---------------------------------------------------------------
    def test_be14_misslungenes_aufraeumen_wird_gemeldet(self):
        """
        Bis Build 624 stand hier 'pass'. Ein Loeschen, das nicht klappt, ist
        eine Auskunft - vor allem, wenn eine nicht belegte Datei deshalb
        unter dem zaehlenden Namen liegen bleibt.
        """
        cfg = self._cfg(retention_count=1)
        ex = BackupExecutor(cfg)
        gestoert = []

        def _kaputt(pfad, erg):
            gestoert.append(pfad)
            erg.fehler.append("'%s' konnte nicht geloescht werden: Probe"
                              % os.path.basename(pfad))

        ex._loeschen = _kaputt
        self._alte_generationen("20260101T000000Z", "20260102T000000Z")
        run = ex.run(self._plan(cfg))

        self.assertTrue(gestoert, "die Vorrichtung hat nicht gegriffen")
        self.assertTrue(run.aufraeum_fehler)
        self.assertIn("Aufraeumen unvollstaendig", run.reason)

    # --- BE15 ---------------------------------------------------------------
    def test_be15_auch_die_beiseitegelegten_bleiben_begrenzt(self):
        """
        Ein unbegrenzt wachsender Sicherungsordner laesst die
        Platzvorabpruefung irgendwann JEDEN Lauf verweigern - aus dem Verlust
        einzelner Generationen wuerde der Verlust der Sicherung ueberhaupt.
        """
        for ts in ("20260101T000000Z", "20260102T000000Z",
                   "20260103T000000Z", "20260104T000000Z"):
            (Path(self._dest) / ("coordinator_v5_%s_host.backup.db%s"
                                 % (ts, DEFEKT_ENDUNG))).write_bytes(b"rest")
        cfg = self._cfg(retention_count=2)
        run = BackupExecutor(cfg).run(self._plan(cfg))

        uebrig = sorted(n for n in os.listdir(self._dest)
                        if n.endswith(DEFEKT_ENDUNG))
        self.assertEqual(2, len(uebrig), uebrig)
        self.assertTrue(all("20260101" not in n and "20260102" not in n
                            for n in uebrig), uebrig)
        self.assertGreaterEqual(len(run.pruned), 2)

    # --- BE16 ---------------------------------------------------------------
    def test_be16_manifest_legt_rechenschaft_ab(self):
        self._alte_generationen("20260101T000000Z", "20260102T000000Z",
                                label="evidence_99", version=3)
        (Path(self._dest)
         / "coordinator_v5_20260103T000000Z_host.backup.db").write_bytes(b"")
        cfg = self._cfg(retention_count=1)
        run = BackupExecutor(cfg).run(self._plan(cfg))

        with open(run.manifest_path, encoding="ascii") as fh:
            m = json.load(fh)
        for feld in ("beiseite_gelegt", "nicht_beschnitten",
                     "aufraeum_fehler", "aufbewahrung_hinweis"):
            self.assertIn(feld, m)
        self.assertTrue(m["beiseite_gelegt"], m)
        self.assertTrue(any("evidence_99" in e for e in m["nicht_beschnitten"]))
        self.assertIn(DEFEKT_ENDUNG, m["aufbewahrung_hinweis"])

    # --- BE17 ---------------------------------------------------------------
    def test_be17_der_gute_fall_bleibt_unveraendert(self):
        """
        Gegenprobe: ohne Befund tut die Aufbewahrung genau das, was sie
        vorher tat - sonst waere die Verschaerfung eine Verhaltensaenderung
        und keine Absicherung.
        """
        self._alte_generationen("20260101T000000Z", "20260102T000000Z",
                                "20260103T000000Z")
        cfg = self._cfg(retention_count=2)
        run = BackupExecutor(cfg).run(self._plan(cfg))

        self.assertTrue(run.ok, run.reason)
        self.assertEqual([], run.beiseite_gelegt)
        self.assertEqual([], run.nicht_beschnitten)
        self.assertEqual([], run.aufraeum_fehler)
        self.assertEqual(2, len(self._zaehlende()))
        self.assertEqual(2, len(run.pruned), run.pruned)
