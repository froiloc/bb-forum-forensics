# =============================================================================
# tests/test_merge_nachtraege.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Regression zu Vorgang 7d3c1a95: eine Lieferung, die zu einem VORHANDENEN
# Vorgang nur Update-Zeilen nachtraegt, kam nicht im Bestand an. merge.py
# meldete Erfolg, merge-new-tickets.sh loeschte die Quelldatei, und der
# Nachtrag war spurlos weg.
#
# DER VERLUSTFALL WIRD HIER ZUERST NACHGESTELLT (MN00) und danach
# ausgeschlossen. Ein Regressionsfall, der nur den behobenen Zustand prueft,
# belegt nicht, dass er je kaputt war - und die naechste Umarbeitung koennte
# ihn unbemerkt wieder herstellen.
#
# MN00 - der ALTE Vergleich (nur die acht Felder) haelt einen reinen Nachtrag
#        fuer unauffaellig. Das ist der Fehler, historisch nachgestellt.
# MN01 - detect_conflicts() erkennt ihn jetzt und meldet UPDATE_TIMELINE.
# MN02 - auto_resolve_conflict() liefert dafuer IMMER MERGE_UPDATES, auch bei
#        '--auto-resolve target'. Bei diesem Typ gibt es nichts zu
#        entscheiden, nur etwas anzuhaengen.
# MN03 - Ende zu Ende: nach dem Einmischen steht die nachgetragene Zeile im
#        Bestand, und die vorhandene Historie ist unversehrt.
# MN04 - ein echter Feldkonflikt verhaelt sich unveraendert (kein Rueckschritt).
# MN05 - pruefe_einmischung.py: meldet 0 bei vollstaendiger Uebernahme und 1,
#        sobald eine Update-Zeile fehlt.
# MN06 - die Feldliste in pruefe_einmischung.py ist eine Abschrift der Liste
#        in merge.py. Weichen sie voneinander ab, prueft die Gegenprobe am
#        falschen Massstab.
#
# Version: v0.8.673 - Build: 673 - 2026-08-05
# =============================================================================

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_WURZEL = Path(__file__).resolve().parent.parent
_TRACKER = _WURZEL / "issue-tracker"


def _lade(name: str, datei: Path):
    """Laedt ein Modul aus issue-tracker/ ohne Paketkontext."""
    if str(_TRACKER) not in sys.path:
        sys.path.insert(0, str(_TRACKER))
    spec = importlib.util.spec_from_file_location(name, datei)
    modul = importlib.util.module_from_spec(spec)
    sys.modules[name] = modul
    spec.loader.exec_module(modul)
    return modul


def _vorgang(kennung: str, stempel: list[str], status: str = "open") -> dict:
    """Ein Vorgang mit den Pflichtfeldern und einer Update-Historie."""
    return {
        "id": kennung,
        "type": "bug",
        "title": "Probevorgang",
        "affected_version": "0.8.672",
        "reporter": "Probe",
        "reported_at": "2026-08-05T10:00:00+00:00",
        "description": "Nur fuer die Regression.",
        "status": status,
        "priority": "medium",
        "severity": "minor",
        "assigned_to": "",
        "target_version": None,
        "updates": [{"timestamp": t, "author": "Probe", "action": "comment",
                     "comment": "Zeile %s" % t} for t in stempel],
    }


class MergeNachtraegeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.merge = _lade("merge_modul", _TRACKER / "merge.py")
        cls.pruef = _lade("pruefe_einmischung", _TRACKER / "pruefe_einmischung.py")

    # -- MN00 -----------------------------------------------------------------
    def test_mn00_der_alte_vergleich_haette_nichts_gemerkt(self):
        """
        Der Verlustfall, historisch nachgestellt.

        Bis Build 672 entschied AUSSCHLIESSLICH der Vergleich der acht Felder,
        ob ein vorhandener Vorgang ueberhaupt angefasst wird. Dieser Fall
        rechnet genau diesen alten Vergleich noch einmal nach und zeigt: er
        haelt einen Nachtrag, der eine ganze Update-Zeile mitbringt, fuer
        unauffaellig. Genau deshalb fiel die Lieferung zwischen den Zweigen
        hindurch.
        """
        ziel   = _vorgang("11111111-1111-4111-8111-111111111111",
                          ["2026-08-05T10:00:00+00:00"])
        quelle = _vorgang("11111111-1111-4111-8111-111111111111",
                          ["2026-08-05T10:00:00+00:00",
                           "2026-08-05T12:00:00+00:00"])

        felder = ["title", "description", "status", "priority", "severity",
                  "assigned_to", "target_version", "affected_version"]
        abweichend = [f for f in felder if ziel.get(f) != quelle.get(f)]

        self.assertEqual(
            [], abweichend,
            "Der alte Vergleich meldet hier eine Abweichung - dann bildet "
            "dieser Fall den Verlustfall nicht mehr ab.")
        neue = [u for u in quelle["updates"]
                if u["timestamp"] not in {x["timestamp"] for x in ziel["updates"]}]
        self.assertEqual(1, len(neue),
                         "Die Quelle muss genau eine neue Zeile mitbringen.")

    # -- MN01 -----------------------------------------------------------------
    def test_mn01_reiner_nachtrag_wird_erkannt(self):
        motor = self.merge.IssueMergeEngine(
            target_file=Path("egal.json"), auto_resolve="source")
        ziel   = _vorgang("22222222-2222-4222-8222-222222222222",
                          ["2026-08-05T10:00:00+00:00"])
        quelle = _vorgang("22222222-2222-4222-8222-222222222222",
                          ["2026-08-05T10:00:00+00:00",
                           "2026-08-05T12:00:00+00:00"])

        konflikte = motor.detect_conflicts([ziel], [quelle])

        self.assertEqual(1, len(konflikte),
                         "Der Nachtrag muss als behandlungsbeduerftig "
                         "erkannt werden - sonst faellt er wieder durch.")
        self.assertEqual(self.merge.ConflictType.UPDATE_TIMELINE,
                         konflikte[0].type)
        self.assertEqual(["updates"], konflikte[0].conflicting_fields)

    # -- MN02 -----------------------------------------------------------------
    def test_mn02_nachtrag_wird_immer_zusammengefuehrt(self):
        """
        Auch bei '--auto-resolve target'. Bei diesem Typ ist per Konstruktion
        kein Feld abweichend - es gibt nichts zu entscheiden. 'target' waere
        hier wieder ein Verlust mit Erfolgsmeldung.
        """
        konflikt = self.merge.Conflict(
            issue_id="33333333-3333-4333-8333-333333333333",
            type=self.merge.ConflictType.UPDATE_TIMELINE,
            description="Probe", target_data={}, source_data={},
            conflicting_fields=["updates"])
        for strategie in ("source", "target", "newer", "merge"):
            with self.subTest(strategie=strategie):
                motor = self.merge.IssueMergeEngine(
                    target_file=Path("egal.json"), auto_resolve=strategie)
                self.assertEqual(
                    self.merge.ResolutionStrategy.MERGE_UPDATES,
                    motor.auto_resolve_conflict(konflikt))

    # -- MN03 -----------------------------------------------------------------
    def test_mn03_ende_zu_ende_der_nachtrag_kommt_an(self):
        kennung = "44444444-4444-4444-8444-444444444444"
        with tempfile.TemporaryDirectory() as tmp:
            verz = Path(tmp)
            bestand = verz / "issues.json"
            quelle  = verz / "eintraege.json"
            bestand.write_text(json.dumps(
                {"issues": [_vorgang(kennung, ["2026-08-05T10:00:00+00:00"])]},
                ensure_ascii=False), encoding="utf-8")
            quelle.write_text(json.dumps(
                {"issues": [_vorgang(kennung, ["2026-08-05T10:00:00+00:00",
                                               "2026-08-05T12:00:00+00:00"])]},
                ensure_ascii=False), encoding="utf-8")

            motor = self.merge.IssueMergeEngine(
                target_file=bestand, auto_resolve="source", no_backup=True)
            motor.merge(quelle)

            danach = json.loads(bestand.read_text(encoding="utf-8"))

        vorgaenge = danach["issues"]
        self.assertEqual(1, len(vorgaenge), "Es darf kein Vorgang dazukommen.")
        stempel = [u["timestamp"] for u in vorgaenge[0]["updates"]]
        self.assertIn("2026-08-05T12:00:00+00:00", stempel,
                      "Die nachgetragene Zeile ist NICHT angekommen - das ist "
                      "der Fehler aus Vorgang 7d3c1a95.")
        self.assertIn("2026-08-05T10:00:00+00:00", stempel,
                      "Die vorhandene Historie muss unversehrt bleiben.")

    # -- MN04 -----------------------------------------------------------------
    def test_mn04_echter_feldkonflikt_bleibt_wie_bisher(self):
        """Kein Rueckschritt: eine echte Feldabweichung bleibt DATA_DIVERGENCE
        bzw. STATUS_CONFLICT und wird nach der gewaehlten Strategie geloest."""
        motor = self.merge.IssueMergeEngine(
            target_file=Path("egal.json"), auto_resolve="source")
        ziel   = _vorgang("55555555-5555-4555-8555-555555555555",
                          ["2026-08-05T10:00:00+00:00"], status="open")
        quelle = _vorgang("55555555-5555-4555-8555-555555555555",
                          ["2026-08-05T10:00:00+00:00"], status="resolved")

        konflikte = motor.detect_conflicts([ziel], [quelle])

        self.assertEqual(1, len(konflikte))
        self.assertEqual(self.merge.ConflictType.STATUS_CONFLICT,
                         konflikte[0].type)
        self.assertEqual(self.merge.ResolutionStrategy.KEEP_SOURCE,
                         motor.auto_resolve_conflict(konflikte[0]))

    # -- MN05 -----------------------------------------------------------------
    def test_mn05_gegenprobe_schlaegt_bei_fehlender_zeile_an(self):
        kennung = "66666666-6666-4666-8666-666666666666"
        quelle  = {"issues": [_vorgang(kennung, ["2026-08-05T10:00:00+00:00",
                                                 "2026-08-05T12:00:00+00:00"])]}

        vollstaendig = {"issues": [copy.deepcopy(quelle["issues"][0])]}
        self.assertEqual(
            [], self.pruef.pruefe(quelle, vollstaendig),
            "Bei vollstaendiger Uebernahme darf die Gegenprobe schweigen.")

        unvollstaendig = {"issues": [_vorgang(kennung,
                                              ["2026-08-05T10:00:00+00:00"])]}
        maengel = self.pruef.pruefe(quelle, unvollstaendig)
        self.assertEqual(1, len(maengel), maengel)
        self.assertIn("12:00:00", maengel[0])

        fehlt_ganz = {"issues": []}
        self.assertTrue(self.pruef.pruefe(quelle, fehlt_ganz),
                        "Ein gar nicht angekommener Vorgang muss auffallen.")

    # -- MN05b ----------------------------------------------------------------
    def test_mn05b_gegenprobe_als_programm(self):
        """Auch ueber die Kommandozeile - so ruft merge-new-tickets.sh sie."""
        kennung = "77777777-7777-4777-8777-777777777777"
        with tempfile.TemporaryDirectory() as tmp:
            verz = Path(tmp)
            (verz / "quelle.json").write_text(json.dumps(
                {"issues": [_vorgang(kennung, ["2026-08-05T10:00:00+00:00",
                                               "2026-08-05T12:00:00+00:00"])]}),
                encoding="utf-8")
            (verz / "gut.json").write_text(json.dumps(
                {"issues": [_vorgang(kennung, ["2026-08-05T10:00:00+00:00",
                                               "2026-08-05T12:00:00+00:00"])]}),
                encoding="utf-8")
            (verz / "schlecht.json").write_text(json.dumps(
                {"issues": [_vorgang(kennung, ["2026-08-05T10:00:00+00:00"])]}),
                encoding="utf-8")

            werkzeug = str(_TRACKER / "pruefe_einmischung.py")
            gut = subprocess.run(
                [sys.executable, werkzeug, str(verz / "quelle.json"),
                 "--bestand", str(verz / "gut.json")],
                capture_output=True, text=True)
            self.assertEqual(0, gut.returncode, gut.stderr)

            schlecht = subprocess.run(
                [sys.executable, werkzeug, str(verz / "quelle.json"),
                 "--bestand", str(verz / "schlecht.json")],
                capture_output=True, text=True)
            self.assertEqual(1, schlecht.returncode)
            self.assertIn("NICHT GELOESCHT", schlecht.stderr)

    # -- MN06 -----------------------------------------------------------------
    def test_mn06_feldliste_ist_abschrift_aus_merge_py(self):
        quelle = (_TRACKER / "merge.py").read_text(encoding="utf-8")
        baum = ast.parse(quelle)
        gefunden = None
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Assign):
                namen = [z.id for z in knoten.targets if isinstance(z, ast.Name)]
                if "comparable_fields" in namen:
                    gefunden = ast.literal_eval(knoten.value)
                    break
        self.assertIsNotNone(
            gefunden,
            "'comparable_fields' in merge.py nicht auffindbar - dann ist die "
            "Abschrift in pruefe_einmischung.py ungeprueft.")
        self.assertEqual(
            list(gefunden), list(self.pruef.VERGLEICHSFELDER),
            "Die Gegenprobe prueft am falschen Massstab: ihre Feldliste weicht "
            "von der in merge.py ab.")


if __name__ == "__main__":
    unittest.main()
