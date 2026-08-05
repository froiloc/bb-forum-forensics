# =============================================================================
# tests/test_diag_netdrive_probekopie.py
# IT-Forensisches Ermittlungswerkzeug — Regression zu Vorgang 33b859f9
# =============================================================================
# DER BEFUND (Build 614, behoben in Build 682):
#   tools/diag_sqlite_netdrive2.py legte zur Vermessung der Journalmodi eine
#   VOLLKOPIE der gewaehlten evidence_<uid>.db NEBEN das Original - siebenmal
#   nacheinander, je Testfall einmal - und setzte auf jede Kopie chmod 0o666,
#   also Lese- UND Schreibrecht fuer ALLE. Auf einem geteilten Netzlaufwerk,
#   und genau dafuer ist das Werkzeug gebaut, lag damit waehrend des Laufs
#   eine fuer jeden les- und beschreibbare Ausfertigung eines Beweismittels im
#   Verzeichnis.
#
#   Erschwerend: das Schwesterwerkzeug diag_sqlite_netdrive.py schloss beim
#   Bestandsdurchgang nur Namen mit dem Praefix '_probe_' aus. '_probe2_...'
#   beginnt damit NICHT (Unterstrich!) - eine liegengebliebene Kopie wurde
#   also wie eine regulaere Datenbank mitvermessen.
#
# Testfaelle:
#   PK01 - Im Quelltext steht kein chmod(0o666) mehr.
#   PK02 - Die Kopie wird mit 0o600 angelegt: schreibbar, aber nur fuer die
#          aufrufende Person. NICHT ersatzlos gestrichen - Begruendung im
#          Fall selbst.
#   PK03 - Die Kopie liegt in einem eigenen Unterverzeichnis '_probe2_<pid>',
#          nicht neben dem Original.
#   PK04 - Das Aufraeumen entfernt Kopie, Nebendateien und Verzeichnis.
#   PK05 - Bleibt etwas liegen, wird es BENANNT statt verschwiegen.
#   PK06 - Das Schwesterwerkzeug uebergeht '_probe2_'-Reste - auch in
#          Unterverzeichnissen - und sagt, dass es sie uebergeht.
#
# Version: v0.8.682 - Build: 682 - 2026-08-05
# =============================================================================

from __future__ import annotations

import ast
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

_WURZEL = Path(__file__).resolve().parent.parent
_WZ2 = _WURZEL / "tools" / "diag_sqlite_netdrive2.py"
_WZ1 = _WURZEL / "tools" / "diag_sqlite_netdrive.py"


def _lade(name: str, pfad: Path):
    spec = importlib.util.spec_from_file_location(name, pfad)
    modul = importlib.util.module_from_spec(spec)
    sys.modules[name] = modul
    spec.loader.exec_module(modul)
    return modul


class ProbekopieTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.wz2 = _lade("diag_sqlite_netdrive2", _WZ2)
        cls.quelle2 = _WZ2.read_text(encoding="utf-8")
        cls.quelle1 = _WZ1.read_text(encoding="utf-8")

    def setUp(self):
        self.wz2.LOGLINES.clear()

    @staticmethod
    def _chmod_argumente(quelle: str) -> list[int]:
        """Alle Zahlwerte, die im Quelltext an chmod() uebergeben werden."""
        werte: list[int] = []
        for knoten in ast.walk(ast.parse(quelle)):
            if not isinstance(knoten, ast.Call):
                continue
            name = getattr(knoten.func, "attr", None) or \
                getattr(knoten.func, "id", None)
            if name != "chmod":
                continue
            for arg in knoten.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                    werte.append(arg.value)
        return werte

    # -- PK01 -----------------------------------------------------------------
    def test_pk01_kein_chmod_0666_mehr(self):
        """
        Geprueft wird der CODE, nicht der Text.

        Erste Fassung dieses Falls suchte die Zeichenkette 'chmod(0o666)' -
        und schlug an, weil sie im KOMMENTAR steht ('HIER STAND ...'). Ein
        Waechter, der Kommentare mitliest, zwingt dazu, die Begruendung aus
        dem Code zu entfernen, um ihn gruen zu bekommen. Das waere genau der
        falsche Anreiz: die Begruendung ist das Wertvollste an der Aenderung.
        Der Syntaxbaum sieht nur, was ausgefuehrt wird.
        """
        rechte = self._chmod_argumente(self.quelle2)
        self.assertNotIn(
            0o666, rechte,
            "Die Kopie wird wieder fuer ALLE beschreibbar angelegt - das war "
            "der Befund aus Vorgang 33b859f9. Gefundene chmod-Werte: %s"
            % [oct(r) for r in rechte])

    # -- PK02 -----------------------------------------------------------------
    def test_pk02_kopie_traegt_0600(self):
        """
        NICHT ersatzlos gestrichen, obwohl der Vorgang das vorschlug.

        Begruendung: das Werkzeug misst ausdruecklich mit, ob das Original
        schreibgeschuetzt ist, und die Testmatrix muss auf die Kopie
        SCHREIBEN. Uebernaehme man ueber shutil.copy2 die Rechte eines
        schreibgeschuetzten Originals, fiele die halbe Messung aus - mit einem
        Fehlerbild, das wie ein Befund des Netzlaufwerks aussieht. 0o600 loest
        beides.
        """
        self.assertIn(0o600, self._chmod_argumente(self.quelle2),
                      "Es wird kein chmod(0o600) mehr gesetzt.")

        # Und die Wirkung nachgestellt: eine Kopie mit 0o600 ist fuer die
        # aufrufende Person schreibbar und traegt keine Rechte fuer andere.
        if os.name == "nt":                       # pragma: no cover
            self.skipTest("POSIX-Rechtebits wirken unter Windows nicht")
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "probe.db"
            datei.write_bytes(b"x")
            datei.chmod(0o600)
            modus = stat.S_IMODE(datei.stat().st_mode)
            self.assertTrue(modus & stat.S_IWUSR, "nicht schreibbar")
            self.assertFalse(modus & (stat.S_IRGRP | stat.S_IWGRP
                                      | stat.S_IROTH | stat.S_IWOTH),
                             "Rechte fuer andere sind gesetzt")

    # -- PK03 -----------------------------------------------------------------
    def test_pk03_kopie_liegt_im_eigenen_verzeichnis(self):
        self.assertIn('probe_verz = original.parent / f"_probe2_{os.getpid()}"',
                      self.quelle2)
        self.assertIn('kopie = probe_verz / "probe.db"', self.quelle2)
        self.assertNotIn('kopie = original.with_name(f"_probe2_', self.quelle2,
                         "Die Kopie liegt wieder neben dem Original.")

    # -- PK04 -----------------------------------------------------------------
    def test_pk04_aufraeumen_entfernt_alles(self):
        with tempfile.TemporaryDirectory() as tmp:
            verz = Path(tmp) / "_probe2_4711"
            verz.mkdir()
            kopie = verz / "probe.db"
            kopie.write_bytes(b"beweismittelkopie")
            for anhang in ("-wal", "-shm", "-journal"):
                (verz / ("probe.db" + anhang)).write_bytes(b"neben")

            self.wz2._raeume_auf(verz, kopie)

            self.assertFalse(kopie.exists(), "Kopie liegt noch da")
            self.assertFalse(verz.exists(), "Probeverzeichnis liegt noch da")

    # -- PK05 -----------------------------------------------------------------
    def test_pk05_ein_rest_wird_benannt(self):
        """
        Ein stilles Weitergehen liesse eine vollstaendige Kopie eines
        Beweismittels zurueck, von der niemand weiss.
        """
        with tempfile.TemporaryDirectory() as tmp:
            verz = Path(tmp) / "_probe2_4711"
            verz.mkdir()
            kopie = verz / "probe.db"
            kopie.write_bytes(b"beweismittelkopie")
            # Etwas Fremdes im Verzeichnis: rmdir muss scheitern.
            (verz / "unerwartet.txt").write_text("liegt im Weg")

            self.wz2._raeume_auf(verz, kopie)

            ausgabe = "\n".join(self.wz2.LOGLINES)
            self.assertIn("Probeverzeichnis bleibt liegen", ausgabe)
            self.assertIn("unerwartet.txt", ausgabe)
            self.assertIn("Kopie eines Beweismittels", ausgabe)
            self.assertTrue(verz.exists())

    # -- PK06 -----------------------------------------------------------------
    def test_pk06_schwesterwerkzeug_uebergeht_probe_reste(self):
        """
        Der Ausschluss muss den GANZEN PFAD ansehen: seit Build 682 liegt die
        Kopie in einem Unterverzeichnis, und rglob() steigt hinein.
        """
        self.assertIn("def _ist_probe(pfad)", self.quelle1)
        self.assertIn('teil.startswith("_probe")', self.quelle1)
        self.assertIn("UEBERGANGEN, weil Probe-Reste", self.quelle1,
                      "Ein Ausschluss, der nicht gesagt wird, laesst die "
                      "Bestandsaufnahme vollstaendig aussehen.")

        # Die Auswahlregel nachgestellt - genau wie im Werkzeug.
        def ist_probe(pfad: Path) -> bool:
            return any(teil.startswith("_probe") for teil in pfad.parts)

        faelle = {
            Path("data/evidence/evidence_1488.db"):           False,
            Path("data/evidence/_probe_9.db"):                True,
            Path("data/evidence/_probe2_9.db"):               True,
            Path("data/evidence/_probe2_9/probe.db"):         True,
            Path("data/evidence/_probe2_9/probe.db-wal"):     True,
            Path("data/coordinator.db"):                      False,
        }
        for pfad, erwartet in faelle.items():
            with self.subTest(pfad=str(pfad)):
                self.assertEqual(erwartet, ist_probe(pfad))


if __name__ == "__main__":
    unittest.main()
