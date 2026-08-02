# =============================================================================
# tests/test_issue_tracker_start.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Testsuite fuer Build 651: DER TRACKER MUSS STARTEN - auch mit Reload.
#
# DER ANLASS, und er geht auf mein Konto. Build 650 hat die Serverdatei von
# 'server.py' in 'tracker_server.py' umbenannt (Vorgang 7c7a738f). Ich habe
# run.py, die readme und vier Testdateien nachgezogen - und die Stelle IM
# INNEREN DER DATEI SELBST uebersehen:
#
#     uvicorn.run("server:app", ..., reload=True)
#
# Ein Name, der als Zeichenkette dasteht, wandert bei keiner Umbenennung mit.
# In der VM sah das so aus (mc, 2026-08-02):
#
#     ERROR:    Error loading ASGI app. Could not import module "server".
#
# WARUM MEINE STARTPROBE ES NICHT GEFANGEN HAT - das ist der eigentliche
# Befund: Der Zweig mit dem Modulnamen wird NUR bei RELOAD=true durchlaufen.
# Ohne Reload bekommt uvicorn das App-OBJEKT und braucht den Namen gar nicht.
# Ich habe in Build 650 den Start geprueft - aber ohne .env, also ohne
# Reload. Ich habe damit genau den Weg geprueft, den der Fehler nicht
# beruehrt, und das Ergebnis als 'Start nachgeprueft' vermerkt. Eine Probe,
# die den halben Fall abdeckt, ist keine halbe Sicherheit; sie ist eine
# falsche.
#
# ST01 - der Modulname wird aus dem DATEINAMEN gebildet, steht also nicht
#        mehr als Zeichenkette da. Laeuft immer, kostet nichts.
# ST02 - DIE ECHTE GEGENPROBE: der Tracker wird mit RELOAD=true gestartet und
#        muss 'Application startup complete' melden, ohne 'Error loading ASGI
#        app'. Braucht uvicorn und einige Sekunden; fehlt uvicorn, wird der
#        Fall mit Grund uebersprungen.
#
# Version: v0.8.651 - Build: 651 - 2026-08-02
# =============================================================================

import ast
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
TRACKER = WURZEL / "issue-tracker"
SERVERDATEI = TRACKER / "tracker_server.py"


class TestStartform(unittest.TestCase):
    """ST01 - laeuft immer."""

    def setUp(self):
        if not SERVERDATEI.is_file():
            self.skipTest(f"{SERVERDATEI.name} fehlt im Bestand.")
        self.quelle = SERVERDATEI.read_text(encoding="utf-8")
        self.baum = ast.parse(self.quelle)

    def _funktion(self, name):
        for knoten in ast.walk(self.baum):
            if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
                return knoten
        raise AssertionError(f"{name}() nicht gefunden")

    def test_st01a_kein_modulname_als_zeichenkette(self):
        """
        In start() darf kein Zeichenketten-Literal stehen, das wie ein
        Modulname aussieht. Genau so ist der Fehler entstanden.
        """
        # Gesucht ist ein VOLLSTAENDIGER Modulname als Literal ('server:app'),
        # nicht jedes Vorkommen von ':app'. BEFUND AUS DEM ERSTEN LAUF DIESER
        # DATEI: die richtige Fassung baut den Namen als f-Zeichenkette
        # zusammen, und deren fester Teil IST ':app'. Eine Pruefung auf
        # 'enthaelt :app' schlug damit gegen die Loesung an, die sie schuetzen
        # soll - schon wieder eine Pruefung, die zu grob greift.
        muster = re.compile(r"^[A-Za-z_][\w.]*:app$")
        start = self._funktion("start")
        literale = [k.value for k in ast.walk(start)
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    and muster.match(k.value)]
        self.assertEqual(
            literale, [],
            f"Der Modulname steht wieder als Zeichenkette in start(): "
            f"{literale}. Er wandert dann bei einer Umbenennung nicht mit - "
            f"und faellt erst im Betrieb auf, und auch nur mit RELOAD=true."
        )

    def test_st01b_modulname_kommt_aus_dem_dateinamen(self):
        self.assertIn("Path(__file__).stem", self.quelle,
                      "Der Modulname wird nicht aus dem Dateinamen gebildet")

        # Und er muss auch stimmen: der Wert ist der Name dieser Datei.
        self.assertEqual(SERVERDATEI.stem, "tracker_server")


class TestEchterStart(unittest.TestCase):
    """
    ST02 - die Gegenprobe am laufenden Prozess.

    Sie startet den Tracker wirklich, mit RELOAD=true, in einem eigenen
    Arbeitsverzeichnis und auf einem Port, der nichts stoert. Das kostet ein
    paar Sekunden; es ist der einzige Weg, der den Fehler aus Build 650
    gefunden haette.
    """

    def setUp(self):
        if not SERVERDATEI.is_file():
            self.skipTest(f"{SERVERDATEI.name} fehlt im Bestand.")
        try:
            import uvicorn  # noqa: F401
            import fastapi  # noqa: F401
        except Exception as fehler:
            self.skipTest(f"uvicorn/fastapi nicht vorhanden ({fehler}).")

    def test_st02_start_mit_reload(self):
        with tempfile.TemporaryDirectory(prefix="tracker_start_") as ordner:
            arbeit = Path(ordner) / "issue-tracker"
            shutil.copytree(TRACKER, arbeit,
                            ignore=shutil.ignore_patterns("backups", "logs", "__pycache__"))
            # DER PORT WIRD VOM BETRIEBSSYSTEM GEHOLT, nicht geraten.
            # BEFUND AUS DEM ERSTEN LAUF: mit einer festen Nummer scheiterte
            # der Fall an '[Errno 98] Address already in use' - der Reloader
            # des vorherigen Laufs hielt den Port noch. Ein Test, der an einer
            # fremden Belegung scheitert, sagt nichts ueber den Pruefling.
            with socket.socket() as dose:
                dose.bind(("127.0.0.1", 0))
                port = dose.getsockname()[1]
            (arbeit / ".env").write_text(
                f"HOST=127.0.0.1\nPORT={port}\nRELOAD=true\nDEBUG=false\n",
                encoding="utf-8")

            # Kein subprocess.run: das wartet, bis der Prozess endet - und ein
            # Server endet nicht. Also starten, mitlesen, beenden.
            # EIGENE PROZESSGRUPPE: uvicorn startet im Reload-Betrieb einen
            # KINDPROZESS. Ein terminate() auf den Elternprozess laesst das
            # Kind laufen - und mit ihm den belegten Port. Also die ganze
            # Gruppe beenden.
            prozess = subprocess.Popen(
                [sys.executable, "run.py"],
                cwd=str(arbeit), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"},
                start_new_session=True)
            try:
                import time
                zeilen = []
                ende = time.monotonic() + 25
                erfolg = False
                while time.monotonic() < ende:
                    zeile = prozess.stdout.readline()
                    if not zeile:
                        if prozess.poll() is not None:
                            break
                        continue
                    zeilen.append(zeile)
                    if "Error loading ASGI app" in zeile:
                        break
                    if "Application startup complete" in zeile:
                        erfolg = True
                        break
            finally:
                try:
                    os.killpg(os.getpgid(prozess.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError, AttributeError):
                    prozess.terminate()
                try:
                    prozess.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    try:
                        os.killpg(os.getpgid(prozess.pid), signal.SIGKILL)
                    except Exception:
                        prozess.kill()

            ausgabe = "".join(zeilen)
            self.assertNotIn(
                "Error loading ASGI app", ausgabe,
                "Der Tracker startet mit RELOAD=true nicht - genau der Fehler "
                "aus Build 650:\n" + ausgabe[-1200:])
            self.assertTrue(
                erfolg,
                "Kein 'Application startup complete' innerhalb von 25 "
                "Sekunden:\n" + ausgabe[-1200:])


if __name__ == "__main__":
    unittest.main()
