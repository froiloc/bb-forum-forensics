# =============================================================================
# tests/test_py4_lesend.py
# IT-Forensisches Ermittlungswerkzeug - Regel PY4, bestandsweit
# =============================================================================
# Testsuite fuer Build 629: JEDES Werkzeug, das der CLI-Katalog als 'lesend'
# fuehrt, oeffnet seine Datenbanken auch technisch nur lesend.
#
# DER MASSSTAB KOMMT AUS DEM KATALOG UND NICHT AUS EINER LISTE HIER. Die
#   Einstufung 'lesend' ist eine Zusage an die Betriebsseite - sie steht im
#   Katalog, in der Konsolenhilfe und seit Build 622 im Betriebskapitel der
#   Vollhilfe. Wer sie gibt, muss sie halten. Eine zweite Liste in diesem
#   Test waere binnen zweier Builds von der ersten abgewichen.
#
# DER ANLASS: Vorgang 906ede75 nannte ZWEI Werkzeuge, die 'coordinator.db'
#   schreibfaehig oeffnen, obwohl ihr Dateikopf das Gegenteil zusichert. Die
#   Erhebung fuer Build 629 fand mit demselben Verfahren ZWEI WEITERE
#   (dashboard_admin, templates_db_status) - beide seit Build 606 im Katalog
#   als 'lesend' gefuehrt, beide ohne einen einzigen Schreibvorgang im
#   Quelltext, beide mit schreibfaehiger Verbindung. Ein Vorgang, der zwei
#   Faelle nennt, hat zwei Faelle GEFUNDEN; er sagt nichts darueber, wie
#   viele es gibt. Diese Pruefung sagt es.
#
# PY01 - kein 'lesend'-Werkzeug oeffnet schreibfaehig (ausser den benannten
#        Ausnahmen)
# PY02 - jede Ausnahme gibt es wirklich, ist wirklich 'lesend' und hat
#        wirklich eine schreibfaehige Verbindung (TE6)
# PY03 - jede Ausnahme traegt eine Begruendung, die etwas sagt
# PY04 - GEGENPROBE: die Suche schlaegt bei einem echten Verstoss an
# PY05 - GEGENPROBE: die Suche haelt eine ueber eine Variable gebaute
#        mode=ro-URI NICHT faelschlich fuer schreibfaehig
#
# WAS DIESER TEST NICHT KANN (TE4): Er sieht nur die Werkzeugdatei selbst.
#   Oeffnet ein Werkzeug seine Datenbank ueber ein Repo in einem anderen
#   Modul, faellt das hier nicht auf - die Grenzen stehen im Kopf von
#   tests/_lesende_verbindungen.py. Er prueft ausserdem NICHT die Werkzeuge
#   mit art='gemischt': dort ist eine schreibfaehige Verbindung erlaubt, und
#   ob sie beim LESENDEN Unterbefehl vermieden wird, ist am Quelltext nicht
#   ohne Weiteres zu entscheiden. Das bleibt offen und ist benannt.
#
# Version: v0.8.629 - Build: 629 - 2026-08-01
# =============================================================================

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help.cli_katalog import CLI_KATALOG, eintrag
from tests._lesende_verbindungen import Fundstelle, offene_verbindungen

WURZEL = Path(__file__).resolve().parent.parent

#: Werkzeuge, die als 'lesend' gefuehrt sind und trotzdem eine schreibfaehige
#: Verbindung oeffnen DUERFEN - je mit dem Grund.
#:
#: ALLE DREI SIND DIAGNOSEWERKZEUGE, und bei allen dreien IST DAS SCHREIBEN
#: DER GEGENSTAND DER MESSUNG. Sie sind im Katalog als 'lesend' gefuehrt,
#: weil sie keine Datenbank DES BESTANDES veraendern - sie legen sich ihre
#: eigenen Wegwerf-Dateien an. Die Einstufung ist also richtig, und die
#: Ausnahme ist es auch.
AUSNAHMEN = {
    "diag_migrationsluecke": (
        "Oeffnet ':memory:'. Eine Datenbank im Arbeitsspeicher hat keine "
        "Datei, die man schuetzen koennte, und sie ist mit dem Prozess "
        "wieder weg."),
    "diag_sqlite_netdrive": (
        "Legt auf dem zu pruefenden Laufwerk eine eigene Probe-Datenbank an "
        "und SCHREIBT hinein ('CREATE TABLE'). Genau das ist die Messung: "
        "ob ein Netzlaufwerk einen echten Schreibpfad traegt. Ein PRAGMA "
        "allein waere kein Beleg. Beweismittel werden dabei nicht "
        "angefasst."),
    "diag_sqlite_netdrive2": (
        "Wie diag_sqlite_netdrive: schreibt in eine Wegwerf-Kopie und liest "
        "zurueck, weil ein PRAGMA allein nichts belegt. Zusaetzlich eine "
        "Probe-Datei unter tempfile.mkdtemp(), weil 'PRAGMA mmap_size' auf "
        "':memory:' keine Zeile liefert - der Vorgabewert der Bibliothek ist "
        "nur an einer DATEI-Datenbank abzufragen."),
    # NEU Build 643. Diese Ausnahme ist NICHT beim Schreiben des Werkzeugs
    # eingetragen worden, sondern weil PY01 im Regressionslauf angeschlagen
    # hat - die Pruefung hat getan, wofuer es sie gibt.
    "diag_backup_verdraengung": (
        "Baut sich seinen Wegwerf-Bestand SELBST: eine Quelldatenbank mit "
        "Schema und Inhalt, in einem Verzeichnis, das das Werkzeug anlegt "
        "und das leer sein muss. Ohne diesen Schreibvorgang gaebe es nichts "
        "zu sichern und damit nichts zu pruefen - und eine leere Attrappe "
        "wuerde die Beurteilung der Kopie (user_version, Schemaobjekte, "
        "nicht leer) gar nicht erst erreichen; die Probe liefe ins Nichts "
        "und saehe aus wie ein Erfolg. Ein Bestand wird dabei nicht "
        "angefasst: das Werkzeug oeffnet keine Datenbank, die es nicht "
        "selbst angelegt hat, und lehnt ein nicht leeres Zielverzeichnis "
        "ab."),
}


def _lesende_werkzeuge():
    """Die Katalogeintraege mit art='lesend', deren Datei es gibt."""
    return [e for e in CLI_KATALOG
            if e.art == "lesend" and (WURZEL / e.pfad).is_file()]


class Py4LesendTests(unittest.TestCase):

    # --- PY01 ---------------------------------------------------------------
    def test_py01_kein_lesendes_werkzeug_oeffnet_schreibfaehig(self):
        befunde = []
        for e in _lesende_werkzeuge():
            if e.schluessel in AUSNAHMEN:
                continue
            offen = offene_verbindungen(str(WURZEL / e.pfad))
            for f in offen:
                befunde.append("%s (%s): %s" % (e.schluessel, e.pfad, f))
        self.assertEqual(
            [], befunde,
            "Regel PY4 verletzt - als 'lesend' gefuehrt, aber schreibfaehig "
            "geoeffnet:\n" + "\n".join(befunde))

    # --- PY02 ---------------------------------------------------------------
    def test_py02_jede_ausnahme_gibt_es_wirklich(self):
        """
        TE6: Eine Ausnahmeliste wird gegen die Wirklichkeit geprueft. Sonst
        bleibt eine Ausnahme stehen, deren Gegenstand laengst behoben ist -
        und die naechste Luecke faellt durch sie hindurch.
        """
        maengel = []
        for kennung, _grund in sorted(AUSNAHMEN.items()):
            e = eintrag(kennung)
            if e is None:
                maengel.append("%s: kein Katalogeintrag" % kennung)
                continue
            if e.art != "lesend":
                maengel.append("%s: ist '%s', nicht 'lesend' - die Ausnahme "
                               "gehoert hier nicht hin" % (kennung, e.art))
                continue
            if not (WURZEL / e.pfad).is_file():
                maengel.append("%s: Datei fehlt (%s)" % (kennung, e.pfad))
                continue
            if not offene_verbindungen(str(WURZEL / e.pfad)):
                maengel.append(
                    "%s: hat KEINE schreibfaehige Verbindung mehr - die "
                    "Ausnahme ist ueberholt und gehoert weg" % kennung)
        self.assertEqual([], maengel, "\n".join(maengel))

    # --- PY03 ---------------------------------------------------------------
    def test_py03_jede_ausnahme_ist_begruendet(self):
        for kennung, grund in sorted(AUSNAHMEN.items()):
            self.assertGreater(
                len((grund or "").strip()), 60,
                "%s: eine Ausnahme braucht einen Grund, der traegt - "
                "'historisch so gewachsen' ist keiner." % kennung)

    # --- PY04 ---------------------------------------------------------------
    def test_py04_die_suche_schlaegt_bei_einem_verstoss_an(self):
        """Eine Pruefung, die nie anschlaegt, belegt nichts (TE5)."""
        quelle = (
            "import sqlite3\n"
            "def lies(pfad):\n"
            "    con = sqlite3.connect(pfad)\n"
            "    return con.execute('SELECT 1').fetchone()\n")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "probe.py")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(quelle)
            offen = offene_verbindungen(p)
        self.assertEqual(1, len(offen), offen)
        self.assertEqual(3, offen[0].zeile)
        self.assertEqual("lies", offen[0].funktion)

    def test_py04b_ein_direktes_mode_ro_wird_erkannt(self):
        quelle = (
            "import sqlite3\n"
            "def lies(pfad):\n"
            "    return sqlite3.connect('file:%s?mode=ro' % pfad, uri=True)\n")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "probe.py")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(quelle)
            self.assertEqual([], offene_verbindungen(p))

    # --- PY05 ---------------------------------------------------------------
    def test_py05_ueber_eine_variable_gebaute_uri_wird_erkannt(self):
        """
        DAS HAUSMUSTER. tools/diag_sqlite_netdrive.py baut die URI eine Zeile
        vor dem Aufruf zusammen. Eine Suche, die nur das Argument ansieht,
        haelt das faelschlich fuer schreibfaehig - bei der Erhebung fuer
        Build 629 waren zwei von zehn Fundstellen genau dieser Fall. Sie
        haetten die Ausnahmeliste um zwei unwahre Eintraege verlaengert.
        """
        quelle = (
            "import sqlite3\n"
            "def lies(db):\n"
            "    uri = 'file:' + str(db) + '?mode=ro'\n"
            "    con = sqlite3.connect(uri, uri=True, timeout=5.0)\n"
            "    return con\n")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "probe.py")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(quelle)
            self.assertEqual([], offene_verbindungen(p))

    def test_py05b_am_lebenden_beispiel(self):
        """
        Gegenprobe an der Datei, an der es aufgefallen ist: in
        diag_sqlite_netdrive darf NUR die Probe-Datenbank uebrigbleiben,
        nicht der Lesetest.
        """
        offen = offene_verbindungen(
            str(WURZEL / "tools" / "diag_sqlite_netdrive.py"))
        self.assertTrue(offen, "Vorbedingung: es gibt dort eine Probe")
        self.assertNotIn("read_only_check", [f.funktion for f in offen],
                         "der mode=ro-Lesetest wurde faelschlich gemeldet")

    # --- Bestandsaufnahme ---------------------------------------------------
    def test_py06_die_vier_behobenen_bleiben_behoben(self):
        """
        Namentlich, damit ein Rueckbau auffaellt: zwei aus Vorgang 906ede75
        und zwei, die bei der Erhebung dazukamen.
        """
        for kennung in ("workload_admin", "support_overview_admin",
                        "dashboard_admin", "templates_db_status"):
            e = eintrag(kennung)
            self.assertIsNotNone(e, kennung)
            self.assertEqual("lesend", e.art, kennung)
            self.assertEqual([], offene_verbindungen(str(WURZEL / e.pfad)),
                             "%s oeffnet wieder schreibfaehig" % kennung)


if __name__ == "__main__":
    unittest.main()
