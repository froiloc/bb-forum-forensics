# =============================================================================
# tests/test_issue_tracker_merge.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Testsuite fuer Build 642: das Merge-Werkzeug des Issue-Trackers.
#
# WARUM DIESE SUITE UEBERHAUPT ENTSTEHT. 'python merge.py' ist seit Build 628
# DER massgebliche Weg, auf dem neue Vorgaenge in den Bestand kommen (siehe
# tests/test_issue_eingang_schema.py). Fuer das Schema gab es ab da eine
# Pruefung - fuer das WERKZEUG, das dieses Schema anwendet und die einzige
# Bestandsdatei ueberschreibt, gab es keine einzige. Dabei lagen dort drei
# Fehler, von denen zwei unmittelbar den Bestand betrafen.
#
# DIE DREI BEFUNDE AUS BUILD 641, die hier festgenagelt werden:
#
#   (1) '--output' SCHRIEB TROTZDEM INS ZIEL (main(), Z. 822-832). Der alte
#       Weg mergte in die Zieldatei und kopierte das Ergebnis danach zur
#       Ausgabedatei. Wer 'data/issues.json' schonen wollte und deshalb
#       '--output' waehlte, veraenderte sie genau damit.
#
#   (2) '--output' MIT '--dry-run' STUERZTE AB (main(), Z. 828 gegen Z. 843).
#       Der Zweig, der 'result' belegt, lief nur ausserhalb des Trockenlaufs;
#       die Auswertung des Exit-Codes las danach eine unbelegte Variable:
#       'NameError: name 'result' is not defined'. Ausgerechnet der
#       vorsichtigste Aufruf - anschauen, nichts anfassen - war der einzige,
#       der krachte.
#
#   (3) UNGUELTIGE VORGAENGE WURDEN UEBERSPRUNGEN UND DER REST GESPEICHERT
#       (merge(), Z. 505-515). Am Ende stand '✅ MERGE ABGESCHLOSSEN' und ein
#       Bestand, in dem ein Teil der Eingangsdatei fehlte. Das ist der Fall,
#       den Grundregel 1 ausdruecklich verbietet.
#
# MG01 - '--output' laesst die Zieldatei unveraendert und schreibt die Ausgabe.
# MG02 - '--dry-run' zusammen mit '--output' laeuft durch, ohne Absturz, und
#        veraendert weder Ziel noch Ausgabe.
# MG03 - der Validator lehnt eine Kurzform in 'related_to' ab.
# MG04 - der Validator prueft die Versionsmuster (null bleibt erlaubt).
# MG05 - eine ungueltige Quelldatei bricht den Lauf ab, BEVOR geschrieben wird.
# MG06 - '--force' pflegt den Rest ein und vermerkt die Auslassung.
# MG07 - ein gueltiger Lauf fuegt hinzu und vermerkt die Herkunft.
# MG08 - zeitzonenlose Zeitstempel bringen die Konfliktbewertung nicht zu Fall.
# MG09 - die Sicherung entsteht neben dem Datenverzeichnis, nicht im
#        Arbeitsverzeichnis des Aufrufers.
#
# Version: v0.8.642 - Build: 642 - 2026-08-01
# =============================================================================

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
TRACKER = WURZEL / "issue-tracker"
MERGE_PY = TRACKER / "merge.py"

if str(TRACKER) not in sys.path:
    sys.path.insert(0, str(TRACKER))

from merge import IssueMergeEngine, IssueValidator  # noqa: E402


def _vorgang(kennung: str, **abweichungen) -> dict:
    """
    Ein gueltiger Mindestvorgang.

    Die Kennung wird aus einer festen Vorlage gebildet, damit die IDs echte
    UUIDs sind (der Validator prueft das) und trotzdem lesbar bleiben.
    """
    grund = {
        "id": f"{kennung}-0000-4000-8000-000000000000",
        "type": "bug",
        "title": f"Prüfvorgang {kennung}",
        "affected_version": "0.8.642",
        "reporter": "Testlauf",
        "reported_at": "2026-08-01T12:00:00+00:00",
        "status": "open",
        "priority": "medium",
        "severity": "minor",
        "related_to": [],
        "updates": [],
    }
    grund.update(abweichungen)
    return grund


class MergeGrundgeruest(unittest.TestCase):
    """Legt fuer jeden Test einen eigenen kleinen Bestand an."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.arbeit = Path(self._tmp.name)
        self.daten = self.arbeit / "data"
        self.daten.mkdir()
        self.ziel = self.daten / "issues.json"
        self._schreiben(self.ziel, [_vorgang("aaaaaaaa")])
        self.quelle = self.arbeit / "eingang.json"
        self._schreiben(self.quelle, [_vorgang("bbbbbbbb")])

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def _schreiben(pfad: Path, vorgaenge):
        pfad.write_text(
            json.dumps({"issues": vorgaenge}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _lesen(pfad: Path):
        return json.loads(pfad.read_text(encoding="utf-8"))["issues"]

    def _aufruf(self, *argumente):
        """Ruft merge.py als eigenen Prozess auf - so, wie ein Mensch es tut."""
        return subprocess.run(
            [sys.executable, str(MERGE_PY), *argumente],
            cwd=str(self.arbeit),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            # Kein stdin: bliebe das Werkzeug an einer Rueckfrage haengen,
            # soll es scheitern und nicht warten.
            stdin=subprocess.DEVNULL,
        )


class TestAusgabeUndTrockenlauf(MergeGrundgeruest):
    """MG01, MG02 - die beiden Fehler in main()."""

    def test_mg01_output_laesst_das_ziel_unveraendert(self):
        vorher = self.ziel.read_bytes()
        ausgabe = self.arbeit / "ergebnis.json"

        lauf = self._aufruf(str(self.quelle), "--target", str(self.ziel),
                            "--output", str(ausgabe), "--force")

        self.assertEqual(lauf.returncode, 0, lauf.stdout + lauf.stderr)
        self.assertEqual(
            self.ziel.read_bytes(), vorher,
            "Die Zieldatei wurde trotz --output veraendert - genau der Fehler "
            "aus Build 641"
        )
        self.assertTrue(ausgabe.exists(), "Die Ausgabedatei wurde nicht geschrieben")
        kennungen = {v["id"] for v in self._lesen(ausgabe)}
        self.assertEqual(len(kennungen), 2, "Die Ausgabe enthaelt nicht beide Vorgaenge")

    def test_mg02_trockenlauf_mit_output_stuerzt_nicht_ab(self):
        vorher = self.ziel.read_bytes()
        ausgabe = self.arbeit / "ergebnis.json"

        lauf = self._aufruf(str(self.quelle), "--target", str(self.ziel),
                            "--output", str(ausgabe), "--dry-run")

        self.assertNotIn("NameError", lauf.stderr,
                         "Der Trockenlauf mit --output stuerzt weiterhin ab")
        self.assertEqual(lauf.returncode, 0, lauf.stdout + lauf.stderr)
        self.assertEqual(self.ziel.read_bytes(), vorher,
                         "Der Trockenlauf hat die Zieldatei veraendert")
        self.assertFalse(ausgabe.exists(),
                         "Der Trockenlauf hat eine Ausgabedatei geschrieben")


class TestValidator(unittest.TestCase):
    """MG03, MG04 - was der massgebliche Pruefweg abweist."""

    def test_mg03_kurzform_in_related_to_wird_abgewiesen(self):
        vorgang = _vorgang("cccccccc", related_to=["651e6d84"])
        fehler = IssueValidator.validate(vorgang)
        self.assertTrue(
            any("related_to" in f for f in fehler),
            f"Die Kurzform wurde durchgelassen. Gemeldet wurde: {fehler}"
        )

    def test_mg03b_volle_uuid_bleibt_zulaessig(self):
        vorgang = _vorgang("cccccccc",
                           related_to=["651e6d84-7ebc-4905-ab21-9f324021ec1d"])
        self.assertEqual(IssueValidator.validate(vorgang), [])

    def test_mg04_versionsmuster_wird_geprueft(self):
        self.assertEqual(IssueValidator.validate(_vorgang("dddddddd")), [])

        krumm = _vorgang("dddddddd", affected_version="0.8")
        self.assertTrue(any("affected_version" in f for f in IssueValidator.validate(krumm)))

        zwischenstand = _vorgang("dddddddd", affected_version="0.8.642a")
        self.assertEqual(IssueValidator.validate(zwischenstand), [],
                         "Zwischenstaende (Vorgang b67f7424) muessen zulaessig bleiben")

        # null ist ausdruecklich erlaubt - das Schema fuehrt fuer die beiden
        # optionalen Felder type ["string","null"] (Vorgang d76b5ab4).
        offen = _vorgang("dddddddd", resolved_in_version=None, target_version=None)
        self.assertEqual(IssueValidator.validate(offen), [])

        leer = _vorgang("dddddddd", target_version="")
        self.assertTrue(any("target_version" in f for f in IssueValidator.validate(leer)),
                        "Eine leere Zeichenkette ist keine Version")


class TestAbbruchStattTeilimport(MergeGrundgeruest):
    """MG05, MG06 - Grundregel 1 im Merge."""

    def _quelle_mit_fehler(self):
        gut = _vorgang("bbbbbbbb")
        schlecht = _vorgang("cccccccc", affected_version="völlig krumm")
        self._schreiben(self.quelle, [gut, schlecht])

    def test_mg05_abbruch_ohne_jede_schreibung(self):
        self._quelle_mit_fehler()
        vorher = self.ziel.read_bytes()

        lauf = self._aufruf(str(self.quelle), "--target", str(self.ziel))

        self.assertEqual(lauf.returncode, 1, lauf.stdout + lauf.stderr)
        self.assertIn("ABBRUCH", lauf.stdout)
        self.assertEqual(
            self.ziel.read_bytes(), vorher,
            "Trotz ungueltiger Quelle wurde geschrieben - der Bestand haette "
            "einen Teilstand bekommen"
        )
        # Auch der gueltige Vorgang darf NICHT eingepflegt sein: entweder
        # ganz oder gar nicht.
        self.assertEqual(len(self._lesen(self.ziel)), 1)

    def test_mg06_force_pflegt_den_rest_ein_und_vermerkt_es(self):
        self._quelle_mit_fehler()

        lauf = self._aufruf(str(self.quelle), "--target", str(self.ziel), "--force")

        kennungen = {v["id"][:8] for v in self._lesen(self.ziel)}
        self.assertIn("bbbbbbbb", kennungen, "Der gueltige Vorgang fehlt")
        self.assertNotIn("cccccccc", kennungen, "Der ungueltige Vorgang wurde eingepflegt")
        self.assertIn("NICHT eingepflegt", lauf.stdout,
                      "Die Auslassung wurde nicht vermerkt")


class TestNormalfall(MergeGrundgeruest):
    """MG07, MG09 - der Lauf, der gutgehen soll."""

    def test_mg07_neuer_vorgang_wird_mit_herkunft_eingepflegt(self):
        lauf = self._aufruf(str(self.quelle), "--target", str(self.ziel), "--force")
        self.assertEqual(lauf.returncode, 0, lauf.stdout + lauf.stderr)

        bestand = {v["id"][:8]: v for v in self._lesen(self.ziel)}
        self.assertEqual(set(bestand), {"aaaaaaaa", "bbbbbbbb"})
        vermerke = [u.get("comment", "") for u in bestand["bbbbbbbb"]["updates"]]
        self.assertTrue(any("eingang.json" in v for v in vermerke),
                        f"Kein Herkunftsvermerk gefunden: {vermerke}")

    def test_mg09_sicherung_liegt_neben_dem_datenverzeichnis(self):
        self._aufruf(str(self.quelle), "--target", str(self.ziel), "--force")

        erwartet = self.arbeit / "backups"
        self.assertTrue(erwartet.is_dir(),
                        "Kein Sicherungsverzeichnis neben data/ angelegt")
        sicherungen = list(erwartet.glob("issues_backup_before_merge_*.json"))
        self.assertEqual(len(sicherungen), 1, f"Sicherungen: {sicherungen}")

        # Die Sicherung muss den Stand VOR dem Merge enthalten - sonst ist sie
        # wertlos.
        vorher = json.loads(sicherungen[0].read_text(encoding="utf-8"))["issues"]
        self.assertEqual(len(vorher), 1)


class TestZeitstempel(unittest.TestCase):
    """MG08 - der Absturz, der nie gemeldet wurde, weil er selten auftrat."""

    def setUp(self):
        self.engine = IssueMergeEngine(target_file=Path("data/issues.json"))

    def test_mg08_zeitzonenloser_stempel_bricht_den_vergleich_nicht(self):
        # So schreibt der Tracker selbst: mit Zeitzone.
        mit_zone = _vorgang("aaaaaaaa", updates=[{
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "author": "Tracker", "action": "comment", "comment": "",
        }])
        # So kann eine von Hand gepflegte Eingangsdatei aussehen: ohne.
        ohne_zone = _vorgang("aaaaaaaa", updates=[{
            "timestamp": (datetime.now() - timedelta(days=1)).isoformat(),
            "author": "Handarbeit", "action": "comment", "comment": "",
        }])

        links = self.engine._get_last_update_time(mit_zone)
        rechts = self.engine._get_last_update_time(ohne_zone)

        # Der eigentliche Punkt: dieser Vergleich darf keinen TypeError werfen
        # ('can't compare offset-naive and offset-aware datetimes').
        self.assertTrue(links > rechts)

    def test_mg08b_fehlender_stempel_ergibt_den_frueheste_zeitpunkt(self):
        ohne = {"id": "x"}
        self.assertEqual(
            self.engine._get_last_update_time(ohne),
            datetime.min.replace(tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
