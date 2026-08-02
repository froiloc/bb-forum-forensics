# =============================================================================
# tests/test_issue_tracker_oberflaeche.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Testsuite fuer Build 645: die WEBOBERFLAECHE des Issue-Trackers.
#
# VORGESCHICHTE. Bis Build 644 lagen 'issue-tracker/templates/*.html' nicht im
# Repository - sie fielen unter die Regel '*.html' in .gitignore. Die
# Oberflaeche war damit der Pruefung nicht zugaenglich; genau das stand als
# Vorgang 44f54f0f drin. Seit Build 644 sind die Vorlagen eingecheckt, und
# beim ersten Hinsehen lagen dort zwei Fehler, die beide unmittelbar Belege
# betreffen:
#
#   (1) JEDE BEARBEITUNG UEBER DIE MASKE LOESCHTE ALLE VERWEISE DES VORGANGS.
#       issue_form.html fuehrte kein Feld 'related_to'; server.py las es
#       dennoch als Form("") und schrieb das Ergebnis unbedingt zurueck.
#       Gemessen am laufenden Tracker (Build 644a, Kopie des Bestands),
#       Vorgang f51fd838: ['906ede75','e9522fe2','c3f80e54'] -> [] nach EINEM
#       Speichern. Ohne Meldung, ohne Eintrag im Verlauf. 29 Vorgaenge fuehren
#       zusammen 35 Verweise; jeder davon war einen Klick vom Verschwinden
#       entfernt.
#
#   (2) 76 VON 126 VORGAENGEN WAREN UEBER DIE OBERFLAECHE NICHT ERREICHBAR.
#       server.py uebergibt 'pagination' seit jeher; index.html gab es nie
#       aus. Bei ITEMS_PER_PAGE=50 endete die Liste nach 50 Eintraegen, und
#       die Zeichenfolge 'page=' kam im ausgelieferten HTML nicht vor. Wer
#       '?page=2' nicht von Hand tippte, hat die anderen nie gesehen.
#
# WIE HIER GEPRUEFT WIRD - ZWEI EBENEN, MIT ABSICHT:
#
#   A) AM LAUFENDEN TRACKER (OF01-OF06). Das ist die eigentliche Aussage: es
#      wird wirklich abgeschickt und danach wirklich in der Datei nachgesehen.
#      Diese Ebene setzt 'fastapi', 'jinja2', 'python-multipart' und 'httpx'
#      voraus - alles Abhaengigkeiten des Trackers, aber KEINE des Pakets
#      (issue-tracker/requirements.txt ist eine eigene Liste, httpx steht
#      nicht einmal dort). Fehlt eines davon, wird diese Ebene UEBERSPRUNGEN
#      und sagt das auch. Ein roter Test, der nichts ueber den Pruefling
#      aussagt, ist schlimmer als keiner - dieselbe Ueberlegung wie bei
#      'jsonschema' in tests/test_issue_tracker_schema.py.
#
#   B) AN DEN VORLAGEN UND AM QUELLTEXT (OF07-OF10). Diese Ebene laeuft
#      IMMER. Sie ist schwaecher, aber sie schlaegt an, wenn jemand das
#      versteckte Feld oder die Blaetter-Bedienung wieder herausnimmt - auch
#      dort, wo Ebene A uebersprungen wird. Die Zusicherung darf nicht an
#      einer Umgebung haengen.
#
# OF01 - das Bearbeitungsformular traegt die bestehenden Verweise.
# OF02 - Speichern MIT dem Feld laesst die Verweise unveraendert.
# OF03 - Speichern OHNE das Feld (altes Formular) laesst sie ebenfalls stehen.
# OF04 - ein ausdruecklich geleertes Feld leert sie - Absicht bleibt moeglich.
# OF05 - ein unbekannter Verweis wird nicht mehr nur ins Protokoll geschrieben,
#        sondern in den Verlauf des Vorgangs.
# OF06 - die Blaetter-Bedienung ist da, die letzte Seite ist erreichbar, und
#        ein gesetzter Filter wandert mit.
# OF07 - GEGENPROBE: issue_form.html fuehrt ein Feld 'related_to'.
# OF08 - GEGENPROBE: save_issue hat fuer 'related_to' die Vorgabe None
#        (nur so ist 'nicht geschickt' von 'leer geschickt' zu unterscheiden).
# OF09 - GEGENPROBE: index.html wertet 'pagination' aus.
# OF10 - GEGENPROBE: die Blaetter-Verweise tragen die Filter weiter.
#
# Version: v0.8.645 - Build: 645 - 2026-08-01
# =============================================================================

import ast
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
TRACKER = WURZEL / "issue-tracker"
VORLAGEN = TRACKER / "templates"

# ---------------------------------------------------------------------------
# Ebene A - Aufbau. Alles, was der Tracker beim Import aus der Umgebung liest,
# wird VORHER gesetzt: server.py wertet die Umgebung zur Importzeit aus
# (Klasse Config), nicht bei jedem Aufruf. Wer das nachher setzt, setzt es
# umsonst.
# ---------------------------------------------------------------------------

_client = None
_arbeitsverzeichnis = None
_grund = ""
_umgebung_vorher = {}

#: Die Umgebungsvariablen, die diese Suite setzen MUSS, damit der Tracker beim
#: Import auf die Kopie zeigt.
#:
#: WARUM SIE HINTERHER ZURUECKGESETZT WERDEN - das ist ein Befund aus dem
#: ersten gemeinsamen Lauf und kein vorsorglicher Zierat: 'BACKUP_DIR' wird
#: auch von issue-tracker/merge.py ausgewertet (sicherungsverzeichnis()).
#: Blieb der Wert stehen, legte merge.py seine Sicherung in das laengst
#: geloeschte Arbeitsverzeichnis dieser Suite - und MG09 in
#: tests/test_issue_tracker_merge.py fiel um. Nicht, weil merge.py kaputt
#: waere, sondern weil DIESE Datei die Umgebung des ganzen Laufs verstellt
#: hatte. Ein Test, der andere Tests umwirft, ist selbst der Fehler.
_UMGEBUNGSSCHLUESSEL = (
    "DATA_DIR", "ISSUES_FILE", "TEMPLATES_DIR",
    "STATIC_DIR", "LOGS_DIR", "BACKUP_DIR",
)


def _tracker_server_laden():
    """
    Laedt issue-tracker/server.py unter EIGENEM Modulnamen.

    WARUM NICHT EINFACH 'import server' - Befund aus dem ersten gemeinsamen
    Lauf, und er ist mehr als eine Testfrage: DAS PAKET HAT EIN EIGENES
    'server'-VERZEICHNIS (server/shell_handler.py und andere). Sobald das
    Wurzelverzeichnis im Suchpfad steht - und im Regressionslauf steht es
    immer dort, weil andere Faelle 'server.*' importieren -, gewinnt das
    Paket. 'import server' liefert dann nicht issue-tracker/server.py,
    sondern das Paket des Webservers, und der Fehler lautet
    "module 'server' has no attribute 'app'". Allein aufgerufen ging die
    Suite durch, im Verbund wurde sie stillschweigend uebersprungen - die
    unangenehmste Sorte Test.

    Der Weg ueber importlib umgeht die Namensfrage vollstaendig: die Datei
    wird an ihrem Pfad geladen und heisst hier 'issue_tracker_server'. Die
    Namensgleichheit selbst bleibt ein Befund und steht als Vorgang im
    Tracker.
    """
    import importlib.util

    pfad = TRACKER / "tracker_server.py"
    spezifikation = importlib.util.spec_from_file_location(
        "issue_tracker_server", pfad)
    modul = importlib.util.module_from_spec(spezifikation)
    # Vor dem Ausfuehren in sys.modules eintragen: das Modul kann sich beim
    # Laden selbst benoetigen (Dataclasses, Logging-Namen).
    sys.modules["issue_tracker_server"] = modul
    spezifikation.loader.exec_module(modul)
    return modul


def setUpModule():
    global _client, _arbeitsverzeichnis, _grund

    for schluessel in _UMGEBUNGSSCHLUESSEL:
        _umgebung_vorher[schluessel] = os.environ.get(schluessel)

    if not VORLAGEN.is_dir():
        _grund = ("issue-tracker/templates fehlt - die Vorlagen liegen nicht "
                  "im Bestand (vgl. Vorgang 44f54f0f).")
        return

    _arbeitsverzeichnis = tempfile.mkdtemp(prefix="tracker_of_")
    arbeit = Path(_arbeitsverzeichnis)
    (arbeit / "data").mkdir()

    # NIE gegen den echten Bestand arbeiten. Diese Suite schreibt, und sie
    # schreibt ausschliesslich in eine Kopie.
    quelle = TRACKER / "data" / "issues.json"
    if quelle.exists():
        shutil.copy2(quelle, arbeit / "data" / "issues.json")
    else:
        (arbeit / "data" / "issues.json").write_text(
            '{"issues": []}', encoding="utf-8")

    os.environ["DATA_DIR"] = str(arbeit / "data")
    os.environ["ISSUES_FILE"] = str(arbeit / "data" / "issues.json")
    os.environ["TEMPLATES_DIR"] = str(VORLAGEN)
    os.environ["STATIC_DIR"] = str(arbeit / "static")
    os.environ["LOGS_DIR"] = str(arbeit / "logs")
    os.environ["BACKUP_DIR"] = str(arbeit / "backups")

    if str(TRACKER) not in sys.path:
        sys.path.insert(0, str(TRACKER))

    try:
        from fastapi.testclient import TestClient  # noqa: F401
        import multipart  # noqa: F401  (python-multipart, fuer Form-Felder)
        tracker_server = _tracker_server_laden()
        _client = TestClient(tracker_server.app)
    except Exception as fehler:  # ImportError und alles, was daraus folgt
        _grund = (f"Der Tracker laesst sich hier nicht starten ({fehler}). "
                  f"Benoetigt: fastapi, jinja2, python-multipart, httpx.")
        _client = None


def tearDownModule():
    # ZUERST die Umgebung zuruecksetzen - siehe die Begruendung oben. Sie
    # steht vor dem Aufraeumen des Verzeichnisses, weil sie die wichtigere der
    # beiden Aufraeumarbeiten ist: ein liegengebliebenes Temp-Verzeichnis
    # kostet Platz, eine liegengebliebene Umgebungsvariable kostet einen
    # fremden Testfall.
    for schluessel, wert in _umgebung_vorher.items():
        if wert is None:
            os.environ.pop(schluessel, None)
        else:
            os.environ[schluessel] = wert

    if _arbeitsverzeichnis:
        shutil.rmtree(_arbeitsverzeichnis, ignore_errors=True)


def _bestand():
    pfad = Path(os.environ["ISSUES_FILE"])
    return {i["id"]: i for i in json.loads(pfad.read_text(encoding="utf-8"))["issues"]}


def _formularfelder(vorgang, **abweichungen):
    """Genau die Felder, die issue_form.html abschickt."""
    felder = {
        "issue_id": vorgang["id"],
        "type": vorgang["type"],
        "title": vorgang["title"],
        "affected_version": vorgang["affected_version"],
        "reporter": vorgang["reporter"],
        "priority": vorgang.get("priority", "medium"),
        "severity": vorgang.get("severity", "minor"),
        "prerequisites": vorgang.get("prerequisites", ""),
        "description": vorgang.get("description", ""),
        "expected_behavior": vorgang.get("expected_behavior", ""),
        "actual_behavior": vorgang.get("actual_behavior", ""),
        "assigned_to": vorgang.get("assigned_to", ""),
        "target_version": vorgang.get("target_version") or "",
        "tags": ", ".join(vorgang.get("tags") or []),
        "related_to": ", ".join(vorgang.get("related_to") or []),
        "os": "", "browser": "", "python_version": "", "database": "",
    }
    felder.update(abweichungen)
    return felder


class LaufenderTracker(unittest.TestCase):
    """Ebene A - die Aussagen, auf die es ankommt."""

    def setUp(self):
        if _client is None:
            self.skipTest(_grund)

        # DIE KOPIE WIRD VOR JEDEM FALL FRISCH GEZOGEN. Diese Suite schreibt;
        # ohne das Zuruecksetzen haengt jeder Fall am Ausgang des vorherigen
        # (OF04 leert die Verweise - OF05 saehe danach einen anderen Vorgang).
        # Ein Test, dessen Ausgang von der Reihenfolge abhaengt, belegt nichts.
        quelle = TRACKER / "data" / "issues.json"
        if quelle.exists():
            shutil.copy2(quelle, os.environ["ISSUES_FILE"])

        # Einen Vorgang MIT Verweisen suchen - sonst prueft der Test nichts.
        self.bestand = _bestand()
        mit_verweisen = [v for v in self.bestand.values() if v.get("related_to")]
        if not mit_verweisen:
            self.skipTest("Kein Vorgang mit Verweisen im Bestand.")
        self.vorgang = mit_verweisen[0]
        self.kennung = self.vorgang["id"]
        self.verweise_vorher = list(self.vorgang["related_to"])

    def test_of01_formular_traegt_die_bestehenden_verweise(self):
        html = _client.get(f"/issue/{self.kennung}/edit").text
        treffer = re.search(r'name="related_to"[^>]*value="([^"]*)"', html)
        self.assertIsNotNone(
            treffer,
            "Das Bearbeitungsformular fuehrt kein Feld 'related_to' - genau "
            "der Zustand, in dem jedes Speichern die Verweise loescht"
        )
        im_feld = [t.strip() for t in treffer.group(1).split(",") if t.strip()]
        self.assertEqual(im_feld, self.verweise_vorher)

    def test_of02_speichern_mit_feld_erhaelt_die_verweise(self):
        antwort = _client.post("/issue/save",
                               data=_formularfelder(self.vorgang),
                               follow_redirects=False)
        self.assertEqual(antwort.status_code, 303)
        self.assertEqual(
            _bestand()[self.kennung].get("related_to"), self.verweise_vorher,
            "Die Verweise haben das Speichern nicht ueberstanden"
        )

    def test_of03_speichern_ohne_feld_erhaelt_die_verweise(self):
        # Der Fall 'altes Formular im Browser-Cache' - und zugleich die Sperre
        # dagegen, dass die Zusicherung nur an der Vorlage haengt.
        felder = _formularfelder(self.vorgang)
        felder.pop("related_to")

        antwort = _client.post("/issue/save", data=felder, follow_redirects=False)

        self.assertEqual(antwort.status_code, 303)
        self.assertEqual(
            _bestand()[self.kennung].get("related_to"), self.verweise_vorher,
            "Ohne das Feld wurden die Verweise geloescht - der Rueckfall auf "
            "den Bestand greift nicht"
        )

    def test_of04_ausdruecklich_geleert_wird_geleert(self):
        # Die Gegenprobe zum Rueckfall: er darf das Loeschen nicht unmoeglich
        # machen, sonst waere aus einem Fehler eine neue Sperre geworden.
        antwort = _client.post("/issue/save",
                               data=_formularfelder(self.vorgang, related_to=""),
                               follow_redirects=False)
        self.assertEqual(antwort.status_code, 303)
        self.assertEqual(_bestand()[self.kennung].get("related_to"), [])

    def test_of05_unbekannter_verweis_wird_abgewiesen(self):
        """
        GEAENDERT IN BUILD 649 - die Zusage ist STAERKER geworden, nicht
        schwaecher.

        In Build 645 stand hier: ein verworfener Verweis muss wenigstens im
        VERLAUF des Vorgangs stehen und nicht nur im Serverprotokoll. Das war
        der bestmoegliche Behelf, solange die Maske keinen Weg zurueck hatte -
        sie konnte nur speichern oder mit einem HTTP-Fehler abbrechen, und ein
        Abbruch haette die Eingabe genauso verloren.

        Build 649 hat diesen Weg gebaut (Vorgang 04a0a4bc): Es wird GAR NICHTS
        MEHR VERWORFEN. Der Speichervorgang wird abgewiesen, die Meldung steht
        am Formular, und die Eingabe bleibt stehen. Damit gibt es keinen
        'verworfenen Verweis' mehr, den man vermerken koennte - der Fall
        prueft jetzt die staerkere Zusage.
        """
        vorher = _bestand()[self.kennung]

        antwort = _client.post(
            "/issue/save",
            data=_formularfelder(self.vorgang,
                                 related_to="99999999-0000-4000-8000-000000000000"),
            follow_redirects=False)

        self.assertEqual(antwort.status_code, 400,
                         "Der unbekannte Verweis wurde angenommen")
        self.assertIn("99999999", antwort.text,
                      "Die Eingabe steht nicht mehr im Formular")
        self.assertEqual(_bestand()[self.kennung], vorher,
                         "Trotz Abweisung wurde am Vorgang etwas geaendert")

    def test_of06_blaettern_erreicht_die_letzte_seite(self):
        gesamt = len(_bestand())
        je_seite = int(os.getenv("ITEMS_PER_PAGE", "50"))
        seiten = max(1, (gesamt + je_seite - 1) // je_seite)
        if seiten < 2:
            self.skipTest(f"Nur {gesamt} Vorgaenge - eine Seite.")

        erste = _client.get("/")
        self.assertIn('class="pagination"', erste.text,
                      "Keine Blaetter-Bedienung im ausgelieferten HTML")

        letzte = _client.get(f"/?page={seiten}")
        self.assertEqual(letzte.status_code, 200)
        sichtbar = letzte.text.count('class="issue-item"')
        rest = gesamt - (seiten - 1) * je_seite
        self.assertEqual(sichtbar, rest,
                         f"Die letzte Seite zeigt {sichtbar} statt {rest}")

        # Und die Summe muss aufgehen - sonst faellt irgendwo etwas heraus.
        summe = sum(_client.get(f"/?page={n}").text.count('class="issue-item"')
                    for n in range(1, seiten + 1))
        self.assertEqual(summe, gesamt,
                         "Ueber alle Seiten zusammen sind nicht alle Vorgaenge "
                         "erreichbar")

    def test_of06b_filter_wandert_beim_blaettern_mit(self):
        antwort = _client.get("/?status_filter=open&page=2")
        if 'class="pagination"' not in antwort.text:
            self.skipTest("Die gefilterte Auswahl passt auf eine Seite.")
        self.assertIn("status_filter=open", antwort.text,
                      "Beim Blaettern geht der gesetzte Filter verloren - man "
                      "landet unbemerkt wieder im gesamten Bestand")


class VorlagenUndQuelltext(unittest.TestCase):
    """
    Ebene B - laeuft immer, auch ohne fastapi.

    Schwaecher als Ebene A, aber unabhaengig von der Umgebung. Sie haelt fest,
    dass die beiden Haelften der Zusicherung ueberhaupt vorhanden sind.
    """

    def setUp(self):
        if not VORLAGEN.is_dir():
            self.skipTest("issue-tracker/templates fehlt im Bestand.")

    def test_of07_formular_fuehrt_das_feld_related_to(self):
        html = (VORLAGEN / "issue_form.html").read_text(encoding="utf-8")
        self.assertRegex(
            html, r'name="related_to"',
            "issue_form.html fuehrt kein Feld 'related_to'. Solange server.py "
            "das Feld liest und zurueckschreibt, loescht jedes Speichern die "
            "Verweise des Vorgangs."
        )

    def test_of08_save_issue_unterscheidet_fehlend_von_leer(self):
        quelle = (TRACKER / "tracker_server.py").read_text(encoding="utf-8")
        baum = ast.parse(quelle)
        funktion = next(
            (k for k in ast.walk(baum)
             if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))
             and k.name == "save_issue"),
            None,
        )
        self.assertIsNotNone(funktion, "save_issue nicht gefunden")

        # Den Vorgabewert des Parameters 'related_to' aus dem Syntaxbaum holen.
        argumente = funktion.args.args + funktion.args.kwonlyargs
        vorgaben = funktion.args.defaults + [
            d for d in funktion.args.kw_defaults if d is not None
        ]
        zuordnung = dict(zip([a.arg for a in argumente[-len(vorgaben):]], vorgaben))
        self.assertIn("related_to", zuordnung, "related_to hat keine Vorgabe")

        vorgabe = zuordnung["related_to"]
        # Erwartet: Form(None). Ein Form("") koennte 'nicht geschickt' nicht
        # von 'leer geschickt' unterscheiden - und genau daran hing der Fehler.
        self.assertIsInstance(vorgabe, ast.Call)
        self.assertTrue(vorgabe.args, "Form() ohne Argument")
        erstes = vorgabe.args[0]
        self.assertTrue(
            isinstance(erstes, ast.Constant) and erstes.value is None,
            "Die Vorgabe fuer 'related_to' ist nicht None. Damit ist 'Feld "
            "fehlt' nicht von 'Feld leer' zu unterscheiden, und ein Formular "
            "ohne dieses Feld loescht wieder alle Verweise."
        )

    def test_of09_index_wertet_die_seitenangaben_aus(self):
        html = (VORLAGEN / "index.html").read_text(encoding="utf-8")
        self.assertIn("pagination.total_pages", html,
                      "index.html wertet 'pagination' nicht aus - Vorgaenge "
                      "jenseits der ersten Seite sind nicht erreichbar")
        self.assertIn("pagination.current_page", html)

    def test_of10_blaetterverweise_tragen_die_filter(self):
        html = (VORLAGEN / "index.html").read_text(encoding="utf-8")
        for feld in ("status_filter", "type_filter", "priority_filter", "search"):
            self.assertIn(
                feld, html,
                f"Der Filter '{feld}' wird beim Blaettern nicht mitgegeben"
            )


if __name__ == "__main__":
    unittest.main()
