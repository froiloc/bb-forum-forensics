# =============================================================================
# tests/test_konfig_pfadhoheit.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Konfiguration
# =============================================================================
# DIE SPERRE zu Ticket 5a7e93b1 (Punkt d des Vorgangs).
#
# DIE REGEL, DIE HIER GEHALTEN WIRD, lautet: der Pfad einer Datenbank kommt
# aus config.yaml, und es gibt je Pfad GENAU EINEN Vorgabewert - in
# core/config_loader.py.
#
# WARUM ES DIESE DATEI GIBT UND NICHT NUR EINEN AUFGERAEUMTEN BESTAND:
#   Der Zustand, den dieser Vorgang behebt, ist nicht durch eine falsche
#   Entscheidung entstanden, sondern durch WACHSTUM: ein neues Werkzeug bringt
#   seinen Vorgabewert mit, weil das im Augenblick das Naheliegende ist.
#   Solange beide Werte uebereinstimmen, faellt nichts auf - erst wenn einer
#   geaendert wird, schreibt dieselbe Datenbank an zwei Orte. Genau so ist der
#   Suchindex auseinandergelaufen (Befund seit Build 641, behoben in 720).
#   Ein einmaliges Aufraeumen haelt das nicht; eine Sperre haelt es.
#
# PH01 - jeder Katalogschluessel ist in der AUSGELIEFERTEN config.yaml
#        gesetzt - ausser den ausdruecklich benannten Ausnahmen.
# PH02 - die Ausnahmeliste ist nicht veraltet: jede genannte Ausnahme gibt es
#        im Katalog auch, und sie ist wirklich nicht gesetzt.
# PH03 - jeder in config.yaml gesetzte Pfad hat einen Vorgabewert in
#        core/config_loader.py (und umgekehrt kein Vorgabewert ins Leere).
# PH04 - KEINE wirksamen Pfadliterale ausserhalb von core/config_loader.py.
#        Gemeint sind argparse-Vorgabewerte und Modulkonstanten - nicht
#        Hilfetexte; die duerfen und sollen Beispielpfade nennen.
#        Nicht parsbare Dateien werden GEMELDET, nicht uebergangen.
# PH05 - Gegenprobe zu PH04: ein eingeschmuggeltes Literal wird gefunden.
#        Ohne sie waere PH04 eine Zusicherung ohne Deckung.
# PH06 - coded_default() liefert den Wert aus _DEFAULTS und None fuer einen
#        Schluessel, der bewusst keinen Vorgabewert hat.
#
# Version: v0.8.720 · Build: 720 · 2026-08-14
# =============================================================================

import ast
import re
import sys
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import yaml                                                    # noqa: E402

from core.config_loader import _DEFAULTS, coded_default        # noqa: E402
from management.db_katalog import DB_KATALOG                   # noqa: E402

# =============================================================================
# DIE AUSNAHMEN — AUSDRUECKLICH, MIT GRUND.
#
# Punkt (c) des Vorgangs verlangt genau das: "Ausnahmen bleiben moeglich, aber
# sie werden BENANNT ... Das ist eine Entscheidung und gehoert als solche
# vermerkt, nicht als fehlender Eintrag."
#
# Eine Ausnahme hier einzutragen ist bewusst unbequem: sie braucht einen Satz,
# der sie traegt. Ein leerer Eintrag faellt beim Lesen auf.
# =============================================================================
AUSNAHMEN = {
    "paths.migration_db": (
        "Steuerdatenbank der Flotten-Migration. KEIN Vorgabewert, und das ist "
        "der Zweck: eine Migration soll nicht gegen eine erfundene "
        "Steuerdatei laufen. Ein gesetzter Wert in der ausgelieferten "
        "config.yaml waere genau der Schaden, den das Fehlen verhindert. "
        "Beleg: migration_fleet_admin._resolve_migration_db_path."),
    "paths.backup_dir": (
        "Sicherungsziel VOR einer Flotten-Migration. Ohne Eintrag verweigert "
        "der Companion ueber das Tor 'KEIN_BACKUP_DIR' - eine Migration ohne "
        "Sicherung findet nicht statt. Ein vorbelegtes Ziel naehme dem Tor "
        "seine Wirkung. NICHT zu verwechseln mit 'backup.dest_dir' (laufende "
        "Datensicherung), das gesetzt ist."),
}

#: Dateien, die von PH04 ausgenommen sind — mit Grund.
DATEI_AUSNAHMEN = {
    "core/config_loader.py": "Die Heimat der Vorgabewerte.",
    "management/db_katalog.py": (
        "Der Katalog fuehrt je Eintrag den Vorgabewert MIT, damit die "
        "Uebersicht ohne einen zweiten Abruf lesbar ist. Er ist eine "
        "Beschreibung des Bestands, kein wirksamer Vorgabewert - gelesen "
        "wird er von der Uebersichtsanzeige, nicht von einem Werkzeug. "
        "PH03 haelt ihn mit _DEFAULTS in Uebereinstimmung."),
}

#: Ausnahmen, die NICHT im DB-Katalog stehen - mit Grund. 'backup_dir' ist
#: kein Datenbankpfad, sondern ein Sicherungsverzeichnis; der Katalog fuehrt
#: Datenbanken. PH02 darf ihn deshalb dort nicht suchen.
AUSSERHALB_DES_KATALOGS = {
    "paths.backup_dir": "Sicherungsverzeichnis, keine Datenbank.",
}

#: Ein Pfadliteral: './data/...', './backups/...', './logs/...'
_LITERAL = re.compile(r'\A\./(?:data|backups|logs)/')

#: Verzeichnisse, die nicht zum ausgelieferten Quelltext gehoeren.
_UEBERSPRINGEN = {"node_modules", ".git", "__pycache__", "backups", "logs",
                  "data", "deployment", "tests", ".pytest_cache", "venv"}


def _quelldateien():
    """Alle .py des ausgelieferten Bestands."""
    for pfad in WURZEL.rglob("*.py"):
        if any(teil in _UEBERSPRINGEN for teil in pfad.parts):
            continue
        yield pfad.relative_to(WURZEL).as_posix()


def _wirksame_literale(text: str):
    """
    (Zeilennummer, Fundstelle) je WIRKSAMEM Pfadliteral.

    GEMESSEN WIRD AM SYNTAXBAUM, nicht an der Zeile - und das ist eine
    Korrektur an dieser Pruefung selbst: die erste Fassung suchte
    zeilenweise und meldete prompt einen DOCSTRING als Fehler
    (core/setting_resolver.py, das Verwendungsbeispiel der Klasse). Ein Test,
    der Falschbefunde erzeugt, wird abgeschaltet oder mit Ausnahmen
    zugeschuettet - beides schlimmer als gar keiner.

    Gezaehlt wird deshalb genau zweierlei:
      * ein Schluesselwort-Argument 'default=' mit Pfadliteral (argparse),
      * eine Zuweisung an eine GROSSGESCHRIEBENE Modulkonstante.
    Alles andere - Hilfetexte, Meldungen, Docstrings, der Hilfekatalog - ist
    Text und bleibt aussen vor. Die Hilfe MUSS Beispielpfade nennen duerfen.
    """
    def _ist_pfad(knoten) -> bool:
        return (isinstance(knoten, ast.Constant)
                and isinstance(knoten.value, str)
                and _LITERAL.match(knoten.value))

    baum = ast.parse(text)          # SyntaxError geht an den Aufrufer

    raus = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Call):
            for kw in knoten.keywords:
                if kw.arg == "default" and _ist_pfad(kw.value):
                    raus.append((kw.value.lineno,
                                 "default=%r" % kw.value.value))
        elif isinstance(knoten, ast.Assign):
            if not _ist_pfad(knoten.value):
                continue
            for ziel in knoten.targets:
                if isinstance(ziel, ast.Name) and ziel.id.isupper():
                    raus.append((knoten.lineno, "%s = %r"
                                 % (ziel.id, knoten.value.value)))
    return sorted(raus)


class PfadhoheitTests(unittest.TestCase):

    def setUp(self):
        self.config = yaml.safe_load(
            (WURZEL / "config.yaml").read_text(encoding="utf-8"))
        self.gesetzt = set(self.config.get("paths") or {})

    # PH01 -------------------------------------------------------------------
    def test_ph01_jeder_katalogpfad_steht_gesetzt_in_config_yaml(self):
        fehlend = []
        for e in DB_KATALOG:
            if not e.config_schluessel:
                continue
            if e.config_schluessel in AUSNAHMEN:
                continue
            name = e.config_schluessel.split(".", 1)[1]
            if name not in self.gesetzt:
                fehlend.append("%s (%s)" % (e.config_schluessel, e.name))
        self.assertEqual(
            sorted(fehlend), [],
            "Diese Pfade werden vom Code gelesen, stehen in der "
            "AUSGELIEFERTEN config.yaml aber nicht gesetzt. Wer dort "
            "nachsieht, findet sie nicht - und der Vorgabewert lebt "
            "unsichtbar im Quelltext. Entweder eintragen oder als "
            "AUSNAHME mit Grund in AUSNAHMEN aufnehmen.")

    # PH02 -------------------------------------------------------------------
    def test_ph02_die_ausnahmeliste_ist_nicht_veraltet(self):
        """
        Eine Ausnahme, deren Pfad es nicht mehr gibt, bleibt sonst stehen und
        deckt spaeter einen anderen Fall zu. Und eine Ausnahme fuer einen
        Pfad, der inzwischen GESETZT ist, ist keine mehr.
        """
        bekannt = {e.config_schluessel for e in DB_KATALOG
                   if e.config_schluessel}
        for schluessel, grund in AUSNAHMEN.items():
            if schluessel not in AUSSERHALB_DES_KATALOGS:
                self.assertIn(schluessel, bekannt,
                              "Ausnahme %r steht im Test, aber nicht im "
                              "Katalog." % schluessel)
            self.assertNotIn(
                schluessel.split(".", 1)[1], self.gesetzt,
                "Ausnahme %r ist inzwischen in config.yaml GESETZT - dann "
                "ist sie keine Ausnahme mehr und gehoert aus der Liste."
                % schluessel)
            self.assertGreater(
                len(grund), 60,
                "Die Ausnahme %r traegt keinen tragfaehigen Grund. Eine "
                "Ausnahme ohne Begruendung ist ein vergessener Eintrag."
                % schluessel)

    # PH03 -------------------------------------------------------------------
    def test_ph03_config_yaml_und_vorgabewerte_stimmen_ueberein(self):
        vorgaben = set(_DEFAULTS.get("paths") or {})
        ohne_vorgabe = self.gesetzt - vorgaben
        self.assertEqual(
            sorted(ohne_vorgabe), [],
            "In config.yaml gesetzt, aber ohne Vorgabewert in "
            "core/config_loader.py. Faellt der Eintrag einmal weg, gibt es "
            "keinen benannten Rueckfall.")
        ins_leere = vorgaben - self.gesetzt
        self.assertEqual(
            sorted(ins_leere), [],
            "Vorgabewert vorhanden, in der ausgelieferten config.yaml aber "
            "nicht gesetzt - genau der Zustand, den Ticket 5a7e93b1 behebt.")
        # Und der Katalog beschreibt denselben Bestand.
        for e in DB_KATALOG:
            if not e.config_schluessel or e.vorgabe is None:
                continue
            self.assertEqual(
                e.vorgabe, coded_default(e.config_schluessel),
                "db_katalog fuehrt fuer %s einen anderen Vorgabewert als "
                "core/config_loader.py. Zwei Angaben zu derselben Sache, "
                "und die Uebersicht zeigt die falsche." % e.config_schluessel)

    # PH04 -------------------------------------------------------------------
    def test_ph04_keine_wirksamen_pfadliterale_ausserhalb_config_loader(self):
        """
        NICHT PARSBARE DATEIEN WERDEN GEMELDET, NICHT UEBERGANGEN.

        Diese Pruefung liest den Syntaxbaum. Eine Datei, die der LAUFENDE
        Interpreter nicht parsen kann, ist damit ungeprueft - im Baucontainer
        trifft das editor/html_renderer.py, weil Python 3.11 die PEP-701-
        f-string dort nicht kennt (derselbe Grund wie bei PY08/PY10; in der
        VM mit Python 3.14 gibt es den Fall nicht).

        Der Test SCHEITERT daran nicht - er koennte es auf keinem aelteren
        Interpreter je bestehen. Er sagt statt dessen, WIEVIELE und WELCHE
        Dateien er nicht lesen konnte. Eine Pruefung, die stillschweigend
        einen Teil des Bestands auslaesst, behauptet mehr, als sie geprueft
        hat (Grundregel 1).
        """
        treffer = []
        ungeprueft = []
        gelesen = 0
        for rel in _quelldateien():
            if rel in DATEI_AUSNAHMEN:
                continue
            text = (WURZEL / rel).read_text(encoding="utf-8")
            try:
                fundstellen = _wirksame_literale(text)
            except SyntaxError as exc:
                ungeprueft.append("%s (%s)" % (rel, exc.msg))
                continue
            gelesen += 1
            for nr, stelle in fundstellen:
                treffer.append("%s:%d  %s" % (rel, nr, stelle))

        # Die Rechenschaft steht im Testprotokoll, auch im gruenen Fall.
        print("PH04: %d Dateien geprueft, %d nicht parsbar%s"
              % (gelesen, len(ungeprueft),
                 (": " + ", ".join(ungeprueft)) if ungeprueft else ""))

        self.assertEqual(
            sorted(treffer), [],
            "WIRKSAME Pfadliterale ausserhalb von core/config_loader.py. "
            "Jedes davon ist ein zweiter Vorgabewert fuer dieselbe Datei - "
            "solange harmlos, bis einer geaendert wird. Statt dessen "
            "'coded_default(\"paths....\")' verwenden.")
        # Und die Pruefung muss ueberhaupt etwas gesehen haben: eine leere
        # Dateiliste waere gruen und wertlos.
        self.assertGreater(gelesen, 100,
                           "Es wurden nur %d Dateien gelesen - die Erhebung "
                           "greift nicht mehr." % gelesen)

    # PH05 -------------------------------------------------------------------
    def test_ph05_gegenprobe_die_suche_findet_wirklich_etwas(self):
        """
        OHNE DIESEN FALL WAERE PH04 EINE ZUSICHERUNG OHNE DECKUNG: ein
        kaputter regulaerer Ausdruck faende nie etwas, und der Test bliebe
        fuer immer gruen.
        """
        gefunden = _wirksame_literale(
            'p.add_argument("--x", default="./data/x.db")')
        self.assertEqual(len(gefunden), 1, "argparse-Vorgabewert nicht erkannt")

        gefunden = _wirksame_literale('STANDARD_PFAD = "./data/x.db"')
        self.assertEqual(len(gefunden), 1, "Modulkonstante nicht erkannt")

        # UND DIE ANDERE RICHTUNG: Hilfetexte und Kommentare bleiben aussen
        # vor, sonst waere die Hilfe nicht mehr zu schreiben.
        for harmlos in ('p.add_argument("--x", help="Standard: ./data/x.db")',
                        '# default="./data/x.db"',
                        'text = "Beispiel: ./data/x.db"',
                        # DER FALL, AN DEM DIE ERSTE FASSUNG GESCHEITERT IST:
                        # ein Docstring mit Verwendungsbeispiel.
                        'def f():\n    """Beispiel:\n'
                        '        default="./data/x.db"\n    """\n    pass'):
            self.assertEqual(_wirksame_literale(harmlos), [],
                             "Text faelschlich als Vorgabewert gewertet: %s"
                             % harmlos)

    # PH06 -------------------------------------------------------------------
    def test_ph06_coded_default(self):
        self.assertEqual(coded_default("paths.evidence_db_dir"),
                         _DEFAULTS["paths"]["evidence_db_dir"])
        self.assertEqual(coded_default("paths.search_index_db"),
                         "./data/search_index.db")
        # Ein Schluessel OHNE Vorgabewert liefert None - 'nicht gesetzt',
        # nicht 'leer'.
        self.assertIsNone(coded_default("paths.migration_db"))
        self.assertEqual(coded_default("paths.gibtsnicht", "X"), "X")
        # Und ein Zwischenknoten, der kein dict ist, bricht nicht.
        self.assertIsNone(coded_default("paths.evidence_db_dir.tiefer"))


if __name__ == "__main__":                                # pragma: no cover
    unittest.main()
