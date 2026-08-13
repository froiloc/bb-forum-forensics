# =============================================================================
# tests/test_backup_versatz.py
# IT-Forensisches Ermittlungswerkzeug - Datensicherung
# =============================================================================
# Testsuite fuer die Versatzauswertung (Vorgang 77757536-381e-491d-9c94-
# e1dda84fd02e): management/backup/backup_versatz.py.
#
# VZ01 - die Spanne je Lauf wird aus 'satz_von'/'satz_bis' gerechnet;
#        kleinste/Median/groesste stimmen ueber mehrere Laeufe.
# VZ02 - je Lauf werden die laengste Einzelkopie und ihr Anteil an der
#        Gesamtspanne bestimmt.
# VZ03 - eine 'dominante' Datenbank wird NUR ausgewiesen, wenn sie in ALLEN
#        messbaren Laeufen die laengste war.
# VZ04 - 'nicht_gesichert_weil_neu' wird zum Befund und hebt den
#        Rueckgabewert; die Namen stehen im Bericht.
# VZ05 - ein Manifest vor Build 617 (ohne 'satz_von') wird NICHT als Spanne 0
#        mitgezaehlt, sondern namentlich und mit Grund uebersprungen.
# VZ06 - unlesbare/kaputte Manifeste werden benannt, nicht verschluckt.
# VZ07 - ein nicht lesbares Verzeichnis ergibt Rueckgabewert 3.
# VZ08 - kein auswertbares Manifest ergibt Rueckgabewert 2 (ohne Grundlage).
# VZ09 - DIE ZEITSTEMPEL WERDEN ALS UTC GEDEUTET, nicht als Ortszeit. Dieser
#        Test setzt die Zeitzone ausdruecklich und ist der wichtigste der
#        Reihe (siehe unten).
# VZ10 - eine Kopie mit Ende vor Beginn liefert KEINE negative Dauer,
#        sondern gar keine - und einen Grund.
# VZ11 - weichen 'satz_von'/'satz_bis' von den Einzelstempeln ab, wird das
#        als Unstimmigkeit gemeldet.
# VZ12 - ohne '--schwelle-minuten' wird die Spanne gemessen, aber NICHT
#        beurteilt; mit Schwelle entsteht ein Befund.
# VZ13 - weniger auswertbare Laeufe als verlangt ist ein Befund.
# VZ14 - Arbeitszeitfenster, auch ueber Mitternacht; ohne Fenster bleibt die
#        Einordnung None ('nicht geprueft') und wird nicht zu False.
# VZ15 - arbeitszeit_zerlegen erraet nichts, sondern bricht ab.
# VZ16 - beide Berichte laufen, sind ASCII und JSON ist serialisierbar.
# VZ17 - sortiert wird nach dem Beginn des Satzes, nicht nach dem Dateinamen.
# VZ18 - GEGEN EIN ECHTES MANIFEST: ein mit BackupExecutor gefahrener Lauf
#        wird ausgewertet. Ohne diesen Test prueft die Reihe nur die eigene
#        Vorrichtung.
#
# ZUR BEDEUTUNG VON VZ09: Die Manifest-Zeitstempel tragen ein 'Z' und sind
# UTC. Wer sie mit time.mktime zerlegt, deutet sie als Ortszeit des
# auswertenden Rechners. Auf der Ermittlungs-VM (Europe/Berlin) waeren alle
# Zeitpunkte um ein bis zwei Stunden verschoben. Den DIFFERENZEN sieht man
# das nicht an - sie blieben richtig -, wohl aber der Frage, ob ein Lauf in
# der Arbeitszeit lag. Genau die soll die Auswertung beantworten. Der Fehler
# waere also unsichtbar und trotzdem ergebnisrelevant; deshalb ein eigener
# Test, der die Zeitzone von aussen verstellt.
#
# ZUR VORRICHTUNG: Die Manifeste werden hier von Hand geschrieben, weil sich
# ein Versatz von Minuten oder Stunden mit einem echten Lauf nicht herstellen
# laesst - eine Testdatenbank ist in Millisekunden kopiert. VZ18 haelt
# dagegen: es prueft, dass die von Hand nachgebildete Form mit der
# WIRKLICHEN Form uebereinstimmt. Das ist die Lehre aus BE05 (Vorgang
# c3f80e54): eine unwirkliche Vorrichtung verdeckt genau das, was die
# Pruefung finden sollte.
#
# Version: v0.8.717 - Build: 717 - 2026-08-13
# =============================================================================

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.backup.backup_versatz import (
    MINDEST_LAEUFE, RC_BEFUND, RC_OHNE_GRUNDLAGE, RC_OK, RC_UNLESBAR,
    VersatzAuswertung, arbeitszeit_zerlegen, bericht_json, bericht_text,
    ts_zu_epoche,
)


def _ts(jahr, monat, tag, stunde, minute, sekunde=0):
    """Ein Manifest-Zeitstempel aus Einzelteilen - UTC."""
    return "%04d%02d%02dT%02d%02d%02dZ" % (jahr, monat, tag, stunde, minute,
                                           sekunde)


class VersatzTestBasis(unittest.TestCase):
    """Gemeinsame Vorrichtung: ein Verzeichnis mit gebauten Manifesten."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _manifest(self, name, kopien, satz_von=None, satz_bis=None,
                  nachzuegler=(), ok=True, run_ts=None, host="vm-forensik",
                  weglassen=()):
        """
        Ein Manifest schreiben.

        'kopien' ist eine Liste (label, begonnen, beendet). 'satz_von' und
        'satz_bis' werden aus den Kopien abgeleitet, wenn nichts anderes
        gesagt ist - genau wie backup_executor._write_manifest es tut.
        """
        stempel = []
        results = []
        for label, von, bis in kopien:
            results.append({
                "label": label, "src": "/data/%s.db" % label,
                "backup_path": "/backups/%s.backup.db" % label,
                "sha512": "0" * 8, "size": 1024, "user_version": 1,
                "integrity_ok": True, "error": None,
                "begonnen_ts": von, "beendet_ts": bis,
            })
            stempel.extend([s for s in (von, bis) if s])
        daten = {
            "run_ts": run_ts or (min(stempel) if stempel
                                 else _ts(2026, 8, 1, 2, 0)),
            "host": host,
            "ok": ok,
            "punktgleich": False,
            "punktgleich_hinweis": "NICHT PUNKTGLEICH: ...",
            "satz_von": satz_von if satz_von is not None else (
                min(stempel) if stempel else ""),
            "satz_bis": satz_bis if satz_bis is not None else (
                max(stempel) if stempel else ""),
            "config": {"dest_dir": self._tmp, "retention_count": 7},
            "results": results,
            "pruned": [],
            "nicht_gesichert_weil_neu": list(nachzuegler),
            "beiseite_gelegt": [],
            "nicht_beschnitten": [],
            "aufraeum_fehler": [],
        }
        for schluessel in weglassen:
            daten.pop(schluessel, None)
        pfad = os.path.join(self._tmp, name)
        with open(pfad, "w", encoding="ascii") as fh:
            json.dump(daten, fh, ensure_ascii=True, indent=2)
        return pfad

    def _lauf(self, name, beginn_stunde, dauern, tag=1, host="vm-forensik",
              **kw):
        """
        Ein Lauf mit hintereinandergelegten Kopien.

        'dauern' ist eine Liste (label, sekunden). Die Kopien folgen
        unmittelbar aufeinander - so, wie backup_executor sie fahren wuerde.
        """
        kopien = []
        sekunde = 0
        for label, dauer in dauern:
            von_m, von_s = divmod(sekunde, 60)
            bis_m, bis_s = divmod(sekunde + dauer, 60)
            kopien.append((
                label,
                _ts(2026, 8, tag, beginn_stunde + von_m // 60, von_m % 60,
                    von_s),
                _ts(2026, 8, tag, beginn_stunde + bis_m // 60, bis_m % 60,
                    bis_s)))
            sekunde += dauer
        return self._manifest(name, kopien, host=host, **kw)

    def _auswerten(self, **kw):
        return VersatzAuswertung(self._tmp, **kw).auswerten()


class VersatzZahlenTests(VersatzTestBasis):

    # VZ01 -------------------------------------------------------------------
    def test_vz01_spanne_je_lauf_und_kennzahlen(self):
        # Drei Laeufe mit 60 s, 180 s und 600 s Gesamtspanne.
        self._lauf("manifest_A_vm.json", 2, [("coordinator", 60)])
        self._lauf("manifest_B_vm.json", 3, [("coordinator", 60),
                                             ("default", 120)])
        self._lauf("manifest_C_vm.json", 4, [("coordinator", 60),
                                             ("default", 540)])
        b = self._auswerten(mindest_laeufe=1)
        self.assertTrue(b.lesbar)
        self.assertEqual(len(b.messbare), 3)
        self.assertEqual(b.spanne_min, 60.0)
        self.assertEqual(b.spanne_median, 180.0)
        self.assertEqual(b.spanne_max, 600.0)
        self.assertIsNotNone(b.schlechtester)
        self.assertEqual(b.schlechtester.spanne_s, 600.0)

    # VZ02 -------------------------------------------------------------------
    def test_vz02_laengste_kopie_und_anteil(self):
        self._lauf("manifest_A_vm.json", 2, [("coordinator", 20),
                                             ("default", 80)])
        b = self._auswerten(mindest_laeufe=1)
        lauf = b.laeufe[0]
        self.assertEqual(lauf.spanne_s, 100.0)
        self.assertEqual(lauf.laengste_kopie.label, "default")
        self.assertAlmostEqual(lauf.anteil_laengste, 0.8)

    # VZ03 -------------------------------------------------------------------
    def test_vz03_dominant_nur_wenn_immer_die_laengste(self):
        # Erst zwei Laeufe, in denen 'default' fuehrt -> dominant.
        self._lauf("manifest_A_vm.json", 2, [("coordinator", 10),
                                             ("default", 90)])
        self._lauf("manifest_B_vm.json", 3, [("coordinator", 10),
                                             ("default", 70)])
        b = self._auswerten(mindest_laeufe=1)
        self.assertIsNotNone(b.dominante_datenbank)
        self.assertEqual(b.dominante_datenbank["label"], "default")

        # Ein dritter Lauf, in dem eine andere fuehrt -> nicht mehr dominant.
        # DAS IST DER KERN DIESES TESTS: 'meistens die laengste' traegt den
        # Vorschlag nicht, diese eine Datenbank aus dem Satz zu nehmen.
        self._lauf("manifest_C_vm.json", 4, [("coordinator", 90),
                                             ("default", 10)])
        b = self._auswerten(mindest_laeufe=1)
        self.assertIsNone(b.dominante_datenbank)

    # VZ17 -------------------------------------------------------------------
    def test_vz17_sortiert_nach_beginn_nicht_nach_dateiname(self):
        # Der Dateiname 'A' gehoert zum SPAETEREN Lauf.
        self._lauf("manifest_A_vm.json", 9, [("coordinator", 30)])
        self._lauf("manifest_B_vm.json", 3, [("coordinator", 30)])
        b = self._auswerten(mindest_laeufe=1)
        self.assertEqual([l.manifest for l in b.laeufe],
                         ["manifest_B_vm.json", "manifest_A_vm.json"])


class VersatzBefundTests(VersatzTestBasis):

    # VZ04 -------------------------------------------------------------------
    def test_vz04_nachzuegler_werden_zum_befund(self):
        self._lauf("manifest_A_vm.json", 2, [("coordinator", 30)],
                   nachzuegler=["/data/evidence/evidence_4711.db"])
        b = self._auswerten(mindest_laeufe=1)
        self.assertEqual(len(b.laeufe_mit_nachzueglern), 1)
        self.assertEqual(b.rueckgabewert(), RC_BEFUND)
        text = bericht_text(b)
        self.assertIn("evidence_4711.db", text)
        # Der Befund muss auch in der Liste stehen, die den Rueckgabewert
        # traegt - sonst koennten Bericht und Wert auseinanderlaufen.
        self.assertTrue(any("evidence_4711.db" in e for e in b.befunde()))

    # VZ05 -------------------------------------------------------------------
    def test_vz05_altes_manifest_wird_benannt_nicht_mitgezaehlt(self):
        self._lauf("manifest_neu_vm.json", 2, [("coordinator", 30)])
        # Ein Manifest aus der Zeit vor Build 617.
        self._lauf("manifest_alt_vm.json", 3, [("coordinator", 30)],
                   weglassen=("satz_von", "satz_bis"))
        b = self._auswerten(mindest_laeufe=1)
        self.assertEqual(len(b.messbare), 1)
        self.assertEqual(len(b.uebersprungen), 1)
        self.assertEqual(b.uebersprungen[0].name, "manifest_alt_vm.json")
        self.assertIn("617", b.uebersprungen[0].grund)
        # Es darf NICHT als Spanne 0 in die Zahlen eingehen.
        self.assertEqual(b.spanne_min, 30.0)
        self.assertIn("manifest_alt_vm.json", bericht_text(b))

    # VZ06 -------------------------------------------------------------------
    def test_vz06_kaputte_manifeste_werden_benannt(self):
        self._lauf("manifest_gut_vm.json", 2, [("coordinator", 30)])
        with open(os.path.join(self._tmp, "manifest_kaputt_vm.json"), "w",
                  encoding="ascii") as fh:
            fh.write("{ das ist kein JSON")
        with open(os.path.join(self._tmp, "manifest_liste_vm.json"), "w",
                  encoding="ascii") as fh:
            json.dump([1, 2, 3], fh)
        b = self._auswerten(mindest_laeufe=1)
        namen = {u.name for u in b.uebersprungen}
        self.assertEqual(namen,
                         {"manifest_kaputt_vm.json", "manifest_liste_vm.json"})
        for u in b.uebersprungen:
            self.assertTrue(u.grund, "Jeder Uebersprung braucht einen Grund")
        self.assertEqual(b.rueckgabewert(), RC_BEFUND)

    # VZ07 -------------------------------------------------------------------
    def test_vz07_unlesbares_verzeichnis(self):
        b = VersatzAuswertung(os.path.join(self._tmp, "gibtsnicht")
                              ).auswerten()
        self.assertFalse(b.lesbar)
        self.assertEqual(b.rueckgabewert(), RC_UNLESBAR)
        self.assertIn("NICHT LESBAR", bericht_text(b))

    # VZ08 -------------------------------------------------------------------
    def test_vz08_ohne_grundlage(self):
        b = self._auswerten()
        self.assertTrue(b.lesbar)
        self.assertEqual(b.rueckgabewert(), RC_OHNE_GRUNDLAGE)
        self.assertIn("Keine Grundlage", bericht_text(b))

    # VZ10 -------------------------------------------------------------------
    def test_vz10_rueckwaerts_laufende_zeit_ergibt_keine_negative_dauer(self):
        self._manifest("manifest_A_vm.json", [
            ("coordinator", _ts(2026, 8, 1, 2, 0, 0),
             _ts(2026, 8, 1, 2, 0, 30)),
            ("kaputt", _ts(2026, 8, 1, 2, 5, 0), _ts(2026, 8, 1, 2, 1, 0)),
        ], satz_von=_ts(2026, 8, 1, 2, 0, 0),
            satz_bis=_ts(2026, 8, 1, 2, 5, 0))
        b = self._auswerten(mindest_laeufe=1)
        lauf = b.laeufe[0]
        kaputt = [k for k in lauf.kopien if k.label == "kaputt"][0]
        self.assertIsNone(kaputt.dauer_s)
        self.assertIn("Ende liegt vor dem Beginn", kaputt.grund)
        # Die laengste Kopie ist die einzige messbare - keine negative Zahl.
        self.assertEqual(lauf.laengste_kopie.label, "coordinator")
        self.assertGreaterEqual(min(e["dauer_median_s"]
                                    for e in b.je_datenbank()), 0.0)

    # VZ11 -------------------------------------------------------------------
    def test_vz11_unstimmige_satzgrenzen_werden_gemeldet(self):
        # 'satz_bis' um eine Stunde weiter als der spaeteste Einzelstempel.
        self._manifest("manifest_A_vm.json", [
            ("coordinator", _ts(2026, 8, 1, 2, 0, 0),
             _ts(2026, 8, 1, 2, 0, 30)),
        ], satz_von=_ts(2026, 8, 1, 2, 0, 0),
            satz_bis=_ts(2026, 8, 1, 3, 0, 0))
        b = self._auswerten(mindest_laeufe=1)
        self.assertTrue(b.laeufe[0].stimmigkeit)
        self.assertEqual(b.rueckgabewert(), RC_BEFUND)
        # Gerechnet wird weiterhin mit den Angaben des Manifests.
        self.assertEqual(b.laeufe[0].spanne_s, 3600.0)

    # VZ12 -------------------------------------------------------------------
    def test_vz12_ohne_schwelle_keine_beurteilung(self):
        self._lauf("manifest_A_vm.json", 2, [("coordinator", 7200)])
        ohne = self._auswerten(mindest_laeufe=1)
        self.assertIsNone(ohne.schwelle_minuten)
        self.assertEqual(ohne.rueckgabewert(), RC_OK)
        self.assertIn("KEINE SCHWELLE GENANNT", bericht_text(ohne))

        mit = self._auswerten(mindest_laeufe=1, schwelle_minuten=30)
        self.assertEqual(mit.rueckgabewert(), RC_BEFUND)
        self.assertTrue(any("Schwelle" in e for e in mit.befunde()))

    # VZ13 -------------------------------------------------------------------
    def test_vz13_zu_wenige_laeufe_ist_ein_befund(self):
        self._lauf("manifest_A_vm.json", 2, [("coordinator", 30)])
        b = self._auswerten()          # Vorgabe MINDEST_LAEUFE
        self.assertEqual(b.mindest_laeufe, MINDEST_LAEUFE)
        self.assertEqual(b.rueckgabewert(), RC_BEFUND)
        self.assertTrue(any("mindestens" in e for e in b.befunde()))


class VersatzZeitTests(VersatzTestBasis):

    # VZ09 -------------------------------------------------------------------
    def test_vz09_zeitstempel_sind_utc_und_nicht_ortszeit(self):
        """
        Der Zeitstempel 20260801T120000Z ist 12:00 UTC - unabhaengig davon,
        in welcher Zeitzone der auswertende Rechner steht.
        """
        alt = os.environ.get("TZ")
        try:
            for zone in ("UTC", "Europe/Berlin", "America/New_York"):
                os.environ["TZ"] = zone
                if hasattr(time, "tzset"):
                    time.tzset()
                # Der Erwartungswert ist UNABHAENGIG von diesem Modul
                # gebildet:
                #   datetime.datetime(2026, 8, 1, 12, 0, 0,
                #       tzinfo=datetime.timezone.utc).timestamp()
                #   -> 1785585600.0
                # Ihn aus ts_zu_epoche selbst zu holen, waere ein Test, der
                # die Funktion gegen sich selbst prueft.
                self.assertEqual(ts_zu_epoche(_ts(2026, 8, 1, 12, 0, 0)),
                                 1785585600,
                                 "Zeitzone %s hat das Ergebnis veraendert"
                                 % zone)
        finally:
            if alt is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = alt
            if hasattr(time, "tzset"):
                time.tzset()

    def test_vz09b_unbrauchbarer_zeitstempel_ergibt_none(self):
        for unsinn in ("", "20260801", "2026-08-01T12:00:00Z", "abc", None):
            self.assertIsNone(ts_zu_epoche(unsinn), repr(unsinn))

    # VZ14 -------------------------------------------------------------------
    def test_vz14_arbeitszeitfenster(self):
        self._lauf("manifest_nacht_vm.json", 2, [("coordinator", 30)])
        self._lauf("manifest_tag_vm.json", 10, [("coordinator", 30)])

        # Ohne Fenster: NICHT GEPRUEFT - und das ist nicht dasselbe wie
        # 'ausserhalb'.
        ohne = self._auswerten(mindest_laeufe=1)
        for lauf in ohne.laeufe:
            self.assertIsNone(ohne.in_arbeitszeit(lauf))
        self.assertIn("Kein Arbeitszeitfenster genannt", bericht_text(ohne))

        # Mit Fenster 07:00-18:00 UTC: der 10-Uhr-Lauf liegt darin.
        mit = self._auswerten(mindest_laeufe=1,
                              arbeitszeit=arbeitszeit_zerlegen("07:00-18:00"))
        drin = {l.manifest for l in mit.laeufe_in_arbeitszeit}
        self.assertEqual(drin, {"manifest_tag_vm.json"})

        # Mit Ortszeitversatz +120 Minuten wird aus 02:00 UTC 04:00 Ortszeit
        # und aus 10:00 UTC 12:00 - der Nachtlauf bleibt draussen.
        versetzt = self._auswerten(
            mindest_laeufe=1, ortszeit_versatz=120,
            arbeitszeit=arbeitszeit_zerlegen("07:00-18:00"))
        self.assertEqual({l.manifest for l in versetzt.laeufe_in_arbeitszeit},
                         {"manifest_tag_vm.json"})

        # Fenster ueber Mitternacht: 22:00-06:00 fasst den 02-Uhr-Lauf.
        nachts = self._auswerten(
            mindest_laeufe=1, arbeitszeit=arbeitszeit_zerlegen("22:00-06:00"))
        self.assertEqual({l.manifest for l in nachts.laeufe_in_arbeitszeit},
                         {"manifest_nacht_vm.json"})

    # VZ15 -------------------------------------------------------------------
    def test_vz15_arbeitszeit_zerlegen_erraet_nichts(self):
        self.assertEqual(arbeitszeit_zerlegen("07:00-18:30"), (420, 1110))
        for unsinn in ("", "7-18", "07:00", "07:00-18:00-19:00", "25:00-26:00",
                       "07:70-18:00", "aa:bb-cc:dd", "08:00-08:00"):
            with self.assertRaises(ValueError, msg=repr(unsinn)):
                arbeitszeit_zerlegen(unsinn)


class VersatzBerichtTests(VersatzTestBasis):

    # VZ16 -------------------------------------------------------------------
    def test_vz16_berichte(self):
        self._lauf("manifest_A_vm.json", 2, [("coordinator", 30),
                                             ("default", 300)],
                   nachzuegler=["/data/evidence/evidence_9.db"])
        self._lauf("manifest_B_vm.json", 3, [("coordinator", 30),
                                             ("default", 120)])
        b = self._auswerten(mindest_laeufe=1, schwelle_minuten=1,
                            arbeitszeit=arbeitszeit_zerlegen("07:00-18:00"))

        text = bericht_text(b)
        text.encode("ascii")            # ASCII-Vorgabe des Projekts
        for erwartet in ("Versatz im Sicherungssatz", "1) WIE GROSS",
                         "2) FAELLT DIE SPANNE", "3) HAT DER BETRIEB",
                         "Rueckgabewert:"):
            self.assertIn(erwartet, text)

        daten = bericht_json(b)
        json.dumps(daten, ensure_ascii=True)   # muss serialisierbar sein
        self.assertEqual(daten["laeufe_messbar"], 2)
        self.assertEqual(daten["spanne_max_s"], 330.0)
        self.assertTrue(daten["schwelle_geprueft"])
        self.assertEqual(daten["dominante_datenbank"]["label"], "default")
        self.assertEqual(daten["laeufe"][0]["nachzuegler"],
                         ["/data/evidence/evidence_9.db"])
        # Text und JSON muessen denselben Rueckgabewert tragen.
        self.assertEqual(daten["rueckgabewert"], b.rueckgabewert())


class VersatzEchtesManifestTests(unittest.TestCase):
    """
    VZ18 - gegen ein WIRKLICH gefahrenes Manifest.

    Die uebrigen Tests bauen die Manifeste nach. Dieser hier fuehrt einen
    echten Sicherungslauf und wertet dessen Manifest aus. Damit ist belegt,
    dass die Auswertung die Form liest, die backup_executor SCHREIBT - und
    nicht nur die, die diese Testdatei nachbildet.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        base = Path(self._tmp)
        (base / "data").mkdir()
        (base / "data" / "evidence").mkdir()
        (base / "data" / "forensic").mkdir()
        (base / "data" / "assets").mkdir()
        self._dest = str(base / "backups")
        os.mkdir(self._dest)
        for pfad in (base / "data" / "coordinator.db",
                     base / "data" / "evidence" / "evidence_18.db"):
            con = sqlite3.connect(str(pfad))
            try:
                con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
                con.executemany("INSERT INTO t(v) VALUES(?)",
                                [("x" * 20,) for _ in range(3)])
                con.commit()
            finally:
                con.close()
        self._paths = {
            "coordinator_db": str(base / "data" / "coordinator.db"),
            "forensic_db_dir": str(base / "data" / "forensic"),
            "evidence_db_dir": str(base / "data" / "evidence"),
            "assets_db_dir": str(base / "data" / "assets"),
        }

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_vz18_echtes_manifest(self):
        from management.backup.backup_config import BackupConfig
        from management.backup.backup_executor import BackupExecutor
        from management.backup.backup_planner import BackupPlanner

        cfg = BackupConfig(dest_dir=self._dest, retention_count=7,
                           min_free_factor=1.3, checkpoint="passive",
                           include_shared_dbs=False)
        plan = BackupPlanner(self._paths, cfg).plan()
        lauf = BackupExecutor(cfg).run(plan)
        self.assertTrue(lauf.ok, lauf.reason)

        b = VersatzAuswertung(self._dest, mindest_laeufe=1).auswerten()
        self.assertTrue(b.lesbar)
        self.assertEqual(len(b.uebersprungen), 0,
                         "Ein echtes Manifest darf nicht uebersprungen werden")
        self.assertEqual(len(b.messbare), 1)
        ausgewertet = b.laeufe[0]
        # Alle gesicherten Datenbanken tauchen als Kopie auf.
        self.assertEqual({k.label for k in ausgewertet.kopien},
                         {r.label for r in lauf.results})
        # Die Spanne ist bestimmbar und nicht negativ. Eine ZAHL kann hier
        # nicht behauptet werden - eine Testdatenbank ist in Sekundenbruch-
        # teilen kopiert, und der Zeitstempel hat Sekundenaufloesung.
        self.assertIsNotNone(ausgewertet.spanne_s)
        self.assertGreaterEqual(ausgewertet.spanne_s, 0.0)
        self.assertFalse(ausgewertet.stimmigkeit,
                         "Die Nachrechnung muss bei einem echten Manifest "
                         "aufgehen: %s" % ausgewertet.stimmigkeit)
        self.assertEqual(len(ausgewertet.nachzuegler), 0)
        bericht_text(b).encode("ascii")
        json.dumps(bericht_json(b), ensure_ascii=True)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
