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

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help.cli_katalog import CLI_KATALOG, eintrag
from tests._lesende_verbindungen import (Fundstelle, hat_lesenden_oeffner,
                                         offene_verbindungen)

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


# =============================================================================
# Vorgang 88dc129b - die beiden Luecken, die Build 629 ausdruecklich offen
# gelassen hat. Bis Build 648 stand im Kopf dieser Datei, dass es sie GIBT;
# WIE GROSS sie sind, war unbekannt. Build 649 hat es erhoben.
# =============================================================================

#: Verzeichnisse, die bei der Modul-Erhebung nicht mitzaehlen - je mit Grund.
#: Sie stehen hier NAMENTLICH und nicht als Bequemlichkeitsfilter, weil jede
#: Auslassung die Zahl kleiner macht, als sie ist.
#:
#: NACHGEMESSEN IN BUILD 649, und das Ergebnis gehoert dazu: Von diesen
#: Auslassungen wirkt HEUTE genau EINE - 'tests' nimmt 162 Dateien mit
#: schreibfaehiger Verbindung heraus. Die uebrigen enthalten im gegenwaertigen
#: Bestand ueberhaupt keine .py-Datei mit einer solchen Verbindung
#: ('issue-tracker' hat drei .py-Dateien, keine davon oeffnet SQLite; die
#: anderen haben gar keine). Sie stehen trotzdem hier, weil sie
#: Fremd- oder Erzeugniscode aufnehmen, SOBALD er entsteht - ein im Bestand
#: angelegtes 'venv' wuerde die Liste sonst um Hunderte Fremddateien
#: aufblaehen und damit unbrauchbar machen. Wer die Liste liest, soll aber
#: nicht den Eindruck bekommen, hier waeren acht Fundgruben abgeraeumt
#: worden: es ist eine, und die sieben anderen sind Vorsorge.
MODUL_AUSGENOMMEN = {
    "tests": "Pruefcode. Er legt sich seine Datenbanken selbst an; das ist "
             "sein Gegenstand und kein Zugriff auf einen Bestand. Einzige "
             "Auslassung, die im Bestand von Build 649 wirklich etwas "
             "herausnimmt (162 Dateien).",
    "setup": "Auslieferungsmaterial (Raeder, Handreichungen), kein "
             "Laufzeitcode des Werkzeugs. Vorsorglich; enthaelt derzeit "
             "keine .py-Datei.",
    "venv": "Fremdcode aus der Laufzeitumgebung. Vorsorglich - ein im "
            "Bestand angelegtes venv wuerde die Erhebung mit Hunderten "
            "fremder Dateien fluten und wertlos machen.",
    "node_modules": "Fremdcode der Browserseite. Vorsorglich, aus demselben "
                    "Grund wie venv.",
    "issue-tracker": "Vorgangsverwaltung neben dem Werkzeug; ihre drei "
                     "Python-Dateien oeffnen keine SQLite-Datenbank. "
                     "Vorsorglich fuer den Fall, dass sich das aendert.",
    "documents": "Regel- und Betriebstexte. Vorsorglich; enthaelt derzeit "
                 "keine .py-Datei und soll auch keine enthalten.",
    "static": "Was an den Browser ausgeliefert wird. Vorsorglich; enthaelt "
              "derzeit keine .py-Datei.",
    "__pycache__": "Erzeugnis des Uebersetzers, kein Quelltext - eine "
                   "Meldung darueber waere nie behebbar. Vorsorglich; im "
                   "ausgelieferten Bestand nicht vorhanden.",
}


def erhebung_gemischt_ohne_lesenden_oeffner():
    """
    Werkzeuge mit art='gemischt', die einen LESENDEN Unterbefehl haben, in
    ihrer eigenen Datei schreibfaehig oeffnen und dabei GAR KEINEN
    nur-lesenden Oeffner besitzen.

    WARUM DIESE DREI BEDINGUNGEN ZUSAMMEN: 'gemischt' allein ist kein
    Mangel - ein Werkzeug, das auch schreibt, DARF schreibfaehig oeffnen.
    Zum Befund wird es erst, wenn es einen Unterbefehl gibt, der als lesend
    ausgewiesen ist, und die dafuer noetige zweite Verbindung nirgends
    vorkommt. Dann laeuft die zugesagte Leseoperation mit Schreibrecht auf
    ein Beweismittel.

    WAS SIE NICHT LEISTET (TE4): Sie sagt nichts ueber Werkzeuge, die BEIDE
    Oeffner haben und im lesenden Unterbefehl trotzdem den falschen nehmen.
    Diese Liste ist die untere Schranke, nicht die Wahrheit.
    """
    raus = []
    for e in CLI_KATALOG:
        if e.art != "gemischt":
            continue
        p = WURZEL / e.pfad
        if not p.is_file():
            continue
        if not any(b.art == "lesend" for b in (e.befehle or [])):
            continue
        if not offene_verbindungen(str(p)):
            continue
        if hat_lesenden_oeffner(str(p)):
            continue
        raus.append(e.schluessel)
    return sorted(raus)


def erhebung_module_schreibfaehig():
    """
    Die 'Repo-Luecke': Dateien, die KEIN Werkzeug des Katalogs sind und
    selbst schreibfaehig oeffnen.

    NICHT JEDER EINTRAG IST EIN BEFUND, und das ist der Grund, warum daraus
    keine Regel wird, sondern eine gefuehrte Liste: db/evidence_db.py etwa
    SOLL schreiben. Der Wert der Liste liegt darin, dass ein NEUER Eintrag
    auffaellt - denn genau ueber solche Module umgeht ein 'lesend'
    gefuehrtes Werkzeug die Pruefung PY01, die nur seine eigene Datei
    ansieht.
    """
    werkzeugpfade = {e.pfad for e in CLI_KATALOG}
    raus = []
    for p in sorted(WURZEL.rglob("*.py")):
        rel = p.relative_to(WURZEL).as_posix()
        if rel.split("/")[0] in MODUL_AUSGENOMMEN:
            continue
        if rel in werkzeugpfade:
            continue
        if offene_verbindungen(str(p)):
            raus.append(rel)
    return sorted(raus)


def _stand():
    with open(WURZEL / "tests" / "hilfe_fehlliste_stand.json",
              encoding="utf-8") as fh:
        return json.load(fh)


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

    # --- PY07 (NEU Build 649, Vorgang 88dc129b) -----------------------------
    def test_py07_gemischte_ohne_lesenden_oeffner_darf_nur_schrumpfen(self):
        """
        PY07: Die Liste der 'gemischten' Werkzeuge ohne nur-lesenden Oeffner
        wird GERECHNET und gegen den eingecheckten Stand gehalten. Sie darf
        schrumpfen (ein Werkzeug hat seinen zweiten Oeffner bekommen), aber
        nicht wachsen.

        WARUM NICHT SOFORT DIE ABSOLUTE FORDERUNG: Weil die Behebung 13
        Werkzeuge betrifft und jedes einzeln nachzuweisen ist. Eine Regel,
        die man am Tag ihrer Einfuehrung nicht einhalten kann, wird
        abgeschaltet - und dann haelt sie gar nichts mehr. Der Weg ist der
        von CK07 (Build 620) und KF08 (Build 641): erst die Schranke, dann
        die Regel, sobald die Liste leer ist. Der Umschaltpunkt steht unten
        und schlaegt von selbst zu.

        EIN NEUER EINTRAG IST EIN BEFUND, kein Pflegevorgang: Entweder ist
        ein Werkzeug mit lesendem Unterbefehl ohne zweiten Oeffner
        hinzugekommen, oder einem bestehenden ist seiner abhanden gekommen.
        """
        stand = _stand()
        eingecheckt = set(stand.get("py4_gemischt_ohne_lesenden_oeffner", []))
        aktuell = set(erhebung_gemischt_ohne_lesenden_oeffner())

        self.assertGreaterEqual(
            stand.get("stand_build", 0), 649,
            "Diese Liste wird erst seit Build 649 gefuehrt; ein aelterer "
            "Stand kann sie nicht belegen.")

        neu = sorted(aktuell - eingecheckt)
        self.assertEqual(
            [], neu,
            "Die Liste der 'gemischten' Werkzeuge ohne nur-lesenden Oeffner "
            "ist GEWACHSEN um: %s. Ein Werkzeug mit lesendem Unterbefehl "
            "braucht einen zweiten, nur-lesenden Oeffner - das Hausmuster "
            "ist backup_admin (Build 627)." % ", ".join(neu))

        if not eingecheckt:
            # Ab hier gilt der Satz selbst und nicht mehr nur die Schranke.
            self.assertEqual(
                set(), aktuell,
                "Der eingecheckte Stand ist leer - damit gilt: KEIN "
                "'gemischtes' Werkzeug mit lesendem Unterbefehl ohne "
                "nur-lesenden Oeffner. Wieder aufgetreten bei: %s"
                % ", ".join(sorted(aktuell)))

    # --- PY08 ---------------------------------------------------------------
    def test_py08_schreibfaehige_module_duerfen_nur_schrumpfen(self):
        """
        PY08: Die Repo-Luecke. Module, die kein Werkzeug sind und selbst
        schreibfaehig oeffnen, werden gezaehlt und namentlich gefuehrt.

        DIESE LISTE IST AUSDRUECKLICH KEINE MAENGELLISTE. Viele dieser
        Module SCHREIBEN zu Recht - db/evidence_db.py ist die Ablage der
        Beweismittel und waere ohne Schreibrecht sinnlos. Die Liste
        beantwortet eine andere Frage: WELCHE Wege gibt es ueberhaupt, auf
        denen ein als 'lesend' gefuehrtes Werkzeug an eine schreibfaehige
        Verbindung kommt, ohne dass PY01 es sieht? PY01 sieht nur die Datei
        des Werkzeugs.

        DER NUTZEN LIEGT IM WACHSTUM, nicht im Bestand: Ein NEUES Modul in
        dieser Liste ist ein neuer solcher Weg, und dann ist zu pruefen, wer
        ihn benutzt. Deshalb ist die Schranke einseitig und wird nie zur
        absoluten Forderung - anders als bei PY07 waere 'die Liste ist leer'
        hier gar kein erstrebenswerter Zustand.
        """
        stand = _stand()
        eingecheckt = set(stand.get("py4_module_schreibfaehig", []))
        aktuell = set(erhebung_module_schreibfaehig())

        self.assertTrue(
            eingecheckt,
            "Die eingecheckte Liste 'py4_module_schreibfaehig' ist leer. Das "
            "hiesse, KEIN Modul ausserhalb der Werkzeuge oeffnet "
            "schreibfaehig - der Bestand schreibt aber (db/evidence_db.py). "
            "Eine leere Liste ist hier ein Zeichen dafuer, dass die Erhebung "
            "nicht gelaufen ist, und keine gute Nachricht.")

        neu = sorted(aktuell - eingecheckt)
        self.assertEqual(
            [], neu,
            "Neue Module mit schreibfaehiger Verbindung: %s. Das ist nicht "
            "zwingend ein Mangel - aber es ist ein neuer Weg, auf dem ein "
            "'lesend' gefuehrtes Werkzeug an Schreibrecht kommt, ohne dass "
            "PY01 es sieht. Bitte nachsehen, wer das Modul benutzt, und den "
            "Eintrag mit Begruendung in tests/hilfe_fehlliste_stand.json "
            "nachtragen." % ", ".join(neu))

    # --- PY09: GEGENPROBE zu PY07 -------------------------------------------
    def test_py09_der_zweite_oeffner_wird_wirklich_erkannt(self):
        """
        Eine Erhebung, die niemanden AUSNIMMT, waere nur eine Liste aller
        gemischten Werkzeuge (TE5). Gegengeprobt am Hausmuster: backup_admin
        hat seit Build 627 beide Oeffner und darf deshalb NICHT in der Liste
        stehen - obwohl es 'gemischt' ist, lesende Unterbefehle hat und
        schreibfaehig oeffnet. Es erfuellt also drei der vier Bedingungen;
        genau die vierte ist der Gegenstand der Pruefung.
        """
        e = eintrag("backup_admin")
        self.assertIsNotNone(e)
        self.assertEqual("gemischt", e.art)
        p = str(WURZEL / e.pfad)
        self.assertTrue(offene_verbindungen(p),
                        "Vorbedingung: backup_admin oeffnet auch schreibfaehig")
        self.assertTrue(hat_lesenden_oeffner(p),
                        "Vorbedingung: backup_admin hat einen mode=ro-Oeffner")
        self.assertNotIn("backup_admin",
                         erhebung_gemischt_ohne_lesenden_oeffner())

    def test_py09b_ein_werkzeug_ohne_zweiten_oeffner_faellt_auf(self):
        """
        Die Gegenrichtung an einer erfundenen Datei: ohne mode=ro schlaegt
        'hat_lesenden_oeffner' NICHT an, mit mode=ro schon.
        """
        ohne = ("import sqlite3\n"
                "def zeige(p):\n"
                "    return sqlite3.connect(p)\n")
        mit = ohne + ("def zeige2(p):\n"
                      "    return sqlite3.connect('file:%s?mode=ro' % p,\n"
                      "                           uri=True)\n")
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.py")
            b = os.path.join(d, "b.py")
            with open(a, "w", encoding="utf-8") as fh:
                fh.write(ohne)
            with open(b, "w", encoding="utf-8") as fh:
                fh.write(mit)
            self.assertFalse(hat_lesenden_oeffner(a))
            self.assertTrue(hat_lesenden_oeffner(b))
            # ...und die schreibfaehige Fundstelle bleibt in BEIDEN sichtbar.
            self.assertEqual(1, len(offene_verbindungen(a)))
            self.assertEqual(1, len(offene_verbindungen(b)))

    # --- PY10: GEGENPROBE zu PY08 -------------------------------------------
    def test_py10_die_modulsuche_findet_ueberhaupt_etwas(self):
        """
        TE5 fuer die Repo-Erhebung: Sie muss die Ablage der Beweismittel
        finden. Faende sie die nicht, waere ihr leeres Ergebnis anderswo
        wertlos - und PY08 haette den falschen Grund fuer sein Gruen.
        """
        module = erhebung_module_schreibfaehig()
        self.assertIn("db/evidence_db.py", module,
                      "Die Erhebung findet nicht einmal die Ablage der "
                      "Beweismittel - dann findet sie gar nichts.")
        # Und sie darf kein Werkzeug des Katalogs enthalten; dafuer ist PY01
        # zustaendig, und eine doppelte Meldung verwischt die Zustaendigkeit.
        werkzeugpfade = {e.pfad for e in CLI_KATALOG}
        doppelt = sorted(set(module) & werkzeugpfade)
        self.assertEqual([], doppelt,
                         "Diese Pfade sind Werkzeuge und gehoeren zu PY01, "
                         "nicht in die Modulliste: %s" % ", ".join(doppelt))

    def test_py10b_jedes_ausgenommene_verzeichnis_ist_begruendet(self):
        """
        Jede Ausnahme der Modul-Erhebung macht die Zahl kleiner, als sie
        ist. Also braucht jede einen Grund, der etwas sagt (wie PY03 fuer
        die Werkzeug-Ausnahmen).
        """
        for name, grund in sorted(MODUL_AUSGENOMMEN.items()):
            self.assertGreater(
                len((grund or "").strip()), 20,
                "%s: eine Auslassung braucht einen Grund." % name)

    def test_py10c_die_auslassung_tests_wirkt_wirklich(self):
        """
        TE5 fuer die Auslassungsliste selbst: Wuerde KEINE der Auslassungen
        etwas herausnehmen, waere die Liste Zierat - und niemand merkte es,
        weil das Ergebnis dasselbe waere. Geprueft wird die einzige, die im
        Bestand von Build 649 wirklich wirkt: 'tests'. Die uebrigen sieben
        sind ausdruecklich Vorsorge und im Kopf der Liste als solche
        benannt; sie hier zu fordern, hiesse ein Verzeichnis anzulegen, nur
        damit ein Test gruen wird.
        """
        treffer = [p for p in (WURZEL / "tests").rglob("*.py")
                   if offene_verbindungen(str(p))]
        self.assertGreater(
            len(treffer), 50,
            "Die Auslassung 'tests' nimmt nichts mehr heraus - dann ist "
            "entweder der Pruefcode verschwunden oder die Suche kaputt.")


if __name__ == "__main__":
    unittest.main()
