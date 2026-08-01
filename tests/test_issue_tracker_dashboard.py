# =============================================================================
# tests/test_issue_tracker_dashboard.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Testsuite fuer Build 647: die drei Vorgaenge von mc am Dashboard.
#
#   d2ade5dc (critical) - Zeilenumbrueche sollen sichtbar sein.
#   7571d4de (high)     - alle moeglichen Status als Filter.
#   2d692c67 (major)    - Tag-Wolke, die zugleich filtert.
#
# ZWEI EBENEN, wie in tests/test_issue_tracker_oberflaeche.py und aus
# demselben Grund:
#
#   A) AM LAUFENDEN TRACKER (DB..). Setzt fastapi, jinja2, python-multipart
#      und httpx voraus - Abhaengigkeiten des Trackers, keine des Pakets.
#      Fehlt eines, wird die Ebene mit Grund uebersprungen.
#
#   B) AN DEN BAUSTEINEN (TF.., TW..). Laeuft IMMER. Build 647 hat die beiden
#      neuen Bausteine ausdruecklich aus server.py herausgeloest
#      (issue-tracker/textformat.py und issue-tracker/tag_cloud.py), damit
#      genau das moeglich ist: die Maskierung ist die einzige Stelle, an der
#      aus Daten HTML wird, und die Stufung der Wolke ist die einzige, die
#      aus Daten eine Aussage macht. Beides muss ohne fastapi pruefbar sein.
#
# TF01 - der Textfilter MASKIERT: eingebettetes Markup kommt maskiert heraus.
# TF02 - jede der drei Umbruchschreibweisen ergibt genau einen Umbruch.
# TF03 - None und '' ergeben nichts (kein leerer Kasten).
# TF04 - eine Leerzeile bleibt als Zeile erhalten (Gliederung geht nicht
#        verloren), aber sie erzeugt keinen zusaetzlichen Kasten mit Inhalt.
# TW01 - jedes Tag des Bestands steht in der Wolke, mit richtiger Anzahl.
# TW02 - GLEICHE ANZAHL ERGIBT IMMER DIESELBE STUFE (der Befund, der zur
#        logarithmischen Stufung gefuehrt hat).
# TW03 - Schreibweisen werden zusammengefasst; angezeigt wird die haeufigste.
# TW04 - ein Tag zaehlt je Vorgang einmal, auch wenn es dort doppelt steht.
# TW05 - haeufiger heisst nie kleiner (die Stufung ist monoton).
# TW06 - leerer Bestand ergibt eine leere Wolke, kein Absturz.
# DB01 - das Dashboard bietet ALLE Status, Typen und Prioritaeten an.
# DB02 - jeder im Bestand vorkommende Wert ist auch waehlbar (Gegenprobe an
#        den Daten, nicht an der Aufzaehlung).
# DB03 - ein zuvor nicht waehlbarer Status liefert jetzt Treffer.
# DB04 - die Tag-Wolke steht im Dashboard und bleibt beim Filtern vollstaendig.
# DB05 - ein Klick auf ein Tag filtert; Gross-/Kleinschreibung ist gleich.
# DB06 - die Suche findet ueber Tags (Vorgang 18204843).
# DB07 - die Kennzahlen beschreiben den BESTAND, nicht die Auswahl (05f65255).
# DB08 - die Detailansicht gibt Zeilen als Bloecke aus.
#
# Version: v0.8.647 - Build: 647 - 2026-08-01
# =============================================================================

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

if str(TRACKER) not in sys.path:
    sys.path.insert(0, str(TRACKER))

from tag_cloud import tag_wolke  # noqa: E402
from textformat import zeilen_html  # noqa: E402


# ---------------------------------------------------------------------------
# Ebene B - die Bausteine. Braucht nichts ausser der Standardbibliothek.
# ---------------------------------------------------------------------------

class TestTextformat(unittest.TestCase):
    """TF01-TF04: aus Text wird HTML - und zwar sicher."""

    def test_tf01_markup_aus_den_daten_wird_maskiert(self):
        boesartig = '<script>alert("x")</script>\nzweite Zeile'
        ergebnis = zeilen_html(boesartig)

        self.assertNotIn("<script>", ergebnis,
                         "Markup aus den Daten kommt unmaskiert durch - in "
                         "einem Werkzeug, dessen Inhalte aus einem "
                         "beschlagnahmten Forum stammen, ist das keine "
                         "theoretische Sorge")
        self.assertIn("&lt;script&gt;", ergebnis)
        # Das EINZIGE Markup im Ergebnis stammt aus dem Baustein selbst.
        self.assertEqual(ergebnis.count("<span"), 2)
        self.assertEqual(ergebnis.count("<"), ergebnis.count("<span") + ergebnis.count("</span"))

    def test_tf02_alle_drei_umbruchschreibweisen(self):
        for name, text in (("unix", "a\nb"), ("windows", "a\r\nb"), ("mac", "a\rb")):
            with self.subTest(schreibweise=name):
                ergebnis = zeilen_html(text)
                self.assertEqual(ergebnis.count('<span class="zeile">'), 2,
                                 f"{name}: nicht genau zwei Zeilen")
                self.assertNotIn("\r", ergebnis)

    def test_tf03_leere_eingabe_ergibt_nichts(self):
        self.assertEqual(zeilen_html(None), "")
        self.assertEqual(zeilen_html(""), "")

    def test_tf04_leerzeile_bleibt_eine_zeile(self):
        # Zwei Umbrueche hintereinander = eine leere Zeile dazwischen. Sie
        # gehoert zur Gliederung und darf nicht verschluckt werden; dass sie
        # optisch nicht doppelt aufreisst, regelt das CSS (.zeile:empty).
        ergebnis = zeilen_html("a\n\nb")
        self.assertEqual(ergebnis.count('<span class="zeile">'), 3)
        self.assertIn('<span class="zeile"></span>', ergebnis)


class TestTagWolke(unittest.TestCase):
    """TW01-TW06: aus Tags wird eine Aussage."""

    @staticmethod
    def _vorgang(*tags):
        return {"id": "x", "tags": list(tags)}

    def test_tw01_jedes_tag_mit_richtiger_anzahl(self):
        wolke = tag_wolke([
            self._vorgang("Alpha", "Beta"),
            self._vorgang("Alpha"),
            self._vorgang("Gamma"),
        ])
        gezaehlt = {e["tag"]: e["anzahl"] for e in wolke}
        self.assertEqual(gezaehlt, {"Alpha": 2, "Beta": 1, "Gamma": 1})
        # Alphabetisch, weil eine Wolke zum Suchen da ist.
        self.assertEqual([e["tag"] for e in wolke], ["Alpha", "Beta", "Gamma"])

    def test_tw02_gleiche_anzahl_ergibt_gleiche_stufe(self):
        """
        DER BEFUND AUS DEM ERSTEN LAUF, festgenagelt.

        Die erste Fassung stufte nach dem RANG. Am echten Bestand ergab das
        Tags mit DERSELBEN Anzahl in VERSCHIEDENEN Stufen - je nachdem, wo
        die Grenze zwischen zwei Fuenfteln zufaellig fiel. Eine Anzeige, die
        gleiche Daten verschieden darstellt, ist eine Falschaussage.
        """
        vorgaenge = []
        # 30 Tags mit je 1 Vorkommen, eines mit 12, eines mit 5.
        for n in range(30):
            vorgaenge.append(self._vorgang(f"einzeln{n}"))
        for _ in range(12):
            vorgaenge.append(self._vorgang("haeufig"))
        for _ in range(5):
            vorgaenge.append(self._vorgang("mittel"))

        wolke = tag_wolke(vorgaenge)
        stufen_je_anzahl = {}
        for e in wolke:
            stufen_je_anzahl.setdefault(e["anzahl"], set()).add(e["stufe"])

        fehler = {a: s for a, s in stufen_je_anzahl.items() if len(s) > 1}
        self.assertEqual(
            fehler, {},
            f"Dieselbe Anzahl erscheint in verschiedenen Stufen: {fehler}"
        )

    def test_tw03_schreibweisen_werden_zusammengefasst(self):
        wolke = tag_wolke([
            self._vorgang("Migration"),
            self._vorgang("migration"),
            self._vorgang("Migration"),
        ])
        self.assertEqual(len(wolke), 1, "Schreibweisen wurden nicht zusammengefasst")
        self.assertEqual(wolke[0]["anzahl"], 3)
        self.assertEqual(wolke[0]["tag"], "Migration",
                         "Angezeigt wird nicht die haeufigste Schreibweise")

    def test_tw04_ein_tag_zaehlt_je_vorgang_einmal(self):
        wolke = tag_wolke([self._vorgang("Alpha", "alpha", "ALPHA")])
        self.assertEqual(wolke[0]["anzahl"], 1,
                         "Ein Pflegefehler im selben Vorgang wurde zu einer "
                         "Aussage ueber die Haeufigkeit")

    def test_tw05_haeufiger_ist_nie_kleiner(self):
        vorgaenge = []
        for anzahl, name in ((1, "a"), (2, "b"), (7, "c"), (30, "d")):
            vorgaenge.extend(self._vorgang(name) for _ in range(anzahl))
        wolke = {e["tag"]: e for e in tag_wolke(vorgaenge)}

        paare = sorted(wolke.values(), key=lambda e: e["anzahl"])
        for links, rechts in zip(paare, paare[1:]):
            self.assertLessEqual(
                links["stufe"], rechts["stufe"],
                f"{links['tag']} ({links['anzahl']}x) ist groesser dargestellt "
                f"als {rechts['tag']} ({rechts['anzahl']}x)"
            )

    def test_tw06_leerer_bestand(self):
        self.assertEqual(tag_wolke([]), [])
        self.assertEqual(tag_wolke([{"id": "x"}, {"id": "y", "tags": []}]), [])

    def test_tw07_live_bestand_ist_vollstaendig_abgebildet(self):
        """GEGENPROBE AN DEN ECHTEN DATEN, nicht nur an erfundenen."""
        datei = TRACKER / "data" / "issues.json"
        if not datei.exists():
            self.skipTest("issue-tracker/data/issues.json nicht vorhanden.")

        vorgaenge = json.loads(datei.read_text(encoding="utf-8"))["issues"]
        wolke = tag_wolke(vorgaenge)

        aus_den_daten = set()
        for v in vorgaenge:
            for t in v.get("tags") or []:
                if str(t).strip():
                    aus_den_daten.add(str(t).strip().lower())
        in_der_wolke = {e["tag"].lower() for e in wolke}

        self.assertEqual(
            aus_den_daten - in_der_wolke, set(),
            "Tags aus dem Bestand fehlen in der Wolke"
        )
        self.assertEqual(sum(1 for _ in wolke), len(aus_den_daten))


# ---------------------------------------------------------------------------
# Ebene A - am laufenden Tracker.
# ---------------------------------------------------------------------------

_client = None
_grund = ""
_arbeitsverzeichnis = None
_umgebung_vorher = {}

#: Siehe tests/test_issue_tracker_oberflaeche.py: 'BACKUP_DIR' wird auch von
#: merge.py ausgewertet. Bleibt der Wert stehen, faellt MG09 in einer ANDEREN
#: Datei um. Ein Test, der andere Tests umwirft, ist selbst der Fehler.
_UMGEBUNGSSCHLUESSEL = (
    "DATA_DIR", "ISSUES_FILE", "TEMPLATES_DIR",
    "STATIC_DIR", "LOGS_DIR", "BACKUP_DIR",
)


def setUpModule():
    global _client, _grund, _arbeitsverzeichnis

    for schluessel in _UMGEBUNGSSCHLUESSEL:
        _umgebung_vorher[schluessel] = os.environ.get(schluessel)

    if not VORLAGEN.is_dir():
        _grund = "issue-tracker/templates fehlt im Bestand."
        return

    _arbeitsverzeichnis = tempfile.mkdtemp(prefix="tracker_db_")
    arbeit = Path(_arbeitsverzeichnis)
    (arbeit / "data").mkdir()

    quelle = TRACKER / "data" / "issues.json"
    if quelle.exists():
        shutil.copy2(quelle, arbeit / "data" / "issues.json")
    else:
        (arbeit / "data" / "issues.json").write_text('{"issues": []}', encoding="utf-8")

    os.environ["DATA_DIR"] = str(arbeit / "data")
    os.environ["ISSUES_FILE"] = str(arbeit / "data" / "issues.json")
    os.environ["TEMPLATES_DIR"] = str(VORLAGEN)
    os.environ["STATIC_DIR"] = str(arbeit / "static")
    os.environ["LOGS_DIR"] = str(arbeit / "logs")
    os.environ["BACKUP_DIR"] = str(arbeit / "backups")

    try:
        from fastapi.testclient import TestClient
        import multipart  # noqa: F401
        import importlib.util

        # EIGENER MODULNAME, siehe test_issue_tracker_oberflaeche.py: das
        # Paket fuehrt selbst ein Verzeichnis 'server/', und 'import server'
        # liefert im Verbund dieses statt der Datei des Trackers.
        spezifikation = importlib.util.spec_from_file_location(
            "issue_tracker_server_dashboard", TRACKER / "server.py")
        modul = importlib.util.module_from_spec(spezifikation)
        sys.modules["issue_tracker_server_dashboard"] = modul
        spezifikation.loader.exec_module(modul)
        _client = TestClient(modul.app)
    except Exception as fehler:
        _grund = (f"Der Tracker laesst sich hier nicht starten ({fehler}). "
                  f"Benoetigt: fastapi, jinja2, python-multipart, httpx.")
        _client = None


def tearDownModule():
    for schluessel, wert in _umgebung_vorher.items():
        if wert is None:
            os.environ.pop(schluessel, None)
        else:
            os.environ[schluessel] = wert
    if _arbeitsverzeichnis:
        shutil.rmtree(_arbeitsverzeichnis, ignore_errors=True)


def _bestand():
    return json.loads(Path(os.environ["ISSUES_FILE"]).read_text(encoding="utf-8"))["issues"]


def _auswahlwerte(html: str, feldname: str) -> set:
    """Die Werte eines <select> aus dem ausgelieferten HTML."""
    block = html.split(f'name="{feldname}"', 1)[1].split("</select>", 1)[0]
    return {w for w in re.findall(r'<option value="([^"]*)"', block) if w}


class LaufendesDashboard(unittest.TestCase):

    def setUp(self):
        if _client is None:
            self.skipTest(_grund)
        self.startseite = _client.get("/")
        self.assertEqual(self.startseite.status_code, 200)

    def test_db01_alle_werte_stehen_im_filter(self):
        # Vorgang 7571d4de: "Ich kann nach Tickets in jedem beliebigen Status
        # filtern." Bis Build 646 waren es 4 von 9.
        status = _auswahlwerte(self.startseite.text, "status_filter")
        self.assertEqual(len(status), 9, f"Status im Filter: {sorted(status)}")
        self.assertEqual(len(_auswahlwerte(self.startseite.text, "type_filter")), 5)
        self.assertEqual(len(_auswahlwerte(self.startseite.text, "priority_filter")), 5)

    def test_db02_jeder_wert_der_daten_ist_waehlbar(self):
        """
        GEGENPROBE AN DEN DATEN. DB01 zaehlt gegen die Aufzaehlung - dieser
        Fall zaehlt gegen das, was tatsaechlich im Bestand vorkommt. Nur so
        faellt auf, wenn jemand einen Wert einfuehrt, den keine Liste kennt.
        """
        vorgaenge = _bestand()
        for feld, filtername in (("status", "status_filter"),
                                 ("type", "type_filter"),
                                 ("priority", "priority_filter")):
            with self.subTest(feld=feld):
                vorhanden = {i[feld] for i in vorgaenge if i.get(feld)}
                waehlbar = _auswahlwerte(self.startseite.text, filtername)
                fehlend = vorhanden - waehlbar
                betroffen = sum(1 for i in vorgaenge if i.get(feld) in fehlend)
                self.assertEqual(
                    fehlend, set(),
                    f"{betroffen} Vorgaenge sind ueber den Filter nicht "
                    f"auffindbar - nicht waehlbar: {sorted(fehlend)}"
                )

    def test_db03_zuvor_nicht_waehlbarer_status_liefert_treffer(self):
        vorgaenge = _bestand()
        for status in ("review", "testing", "duplicate"):
            erwartet = sum(1 for i in vorgaenge if i.get("status") == status)
            if not erwartet:
                continue
            with self.subTest(status=status):
                antwort = _client.get(f"/?status_filter={status}")
                self.assertEqual(antwort.status_code, 200)
                self.assertEqual(antwort.text.count('class="issue-item"'), erwartet)

    def test_db04_tagwolke_steht_und_bleibt_vollstaendig(self):
        # Vorgang 2d692c67. Die Wolke wird aus dem GESAMTBESTAND gebildet -
        # sonst schrumpfte sie bei jedem Klick auf das, was uebrig ist, und
        # waere nach dem ersten Klick eine Sackgasse.
        self.assertIn('class="tag-cloud"', self.startseite.text,
                      "Keine Tag-Wolke im Dashboard")
        insgesamt = self.startseite.text.count('class="tag tag-stufe-')
        self.assertGreater(insgesamt, 0)

        gefiltert = _client.get("/?status_filter=closed")
        self.assertEqual(
            gefiltert.text.count('class="tag tag-stufe-'), insgesamt,
            "Die Wolke schrumpft mit der Auswahl - nach dem ersten Klick "
            "waere jeder andere Weg verschwunden"
        )

    def test_db05_tag_filtert_und_ist_schreibungsunabhaengig(self):
        wolke = tag_wolke(_bestand())
        if not wolke:
            self.skipTest("Keine Tags im Bestand.")
        groesstes = max(wolke, key=lambda e: e["anzahl"])

        antwort = _client.get(f"/?tag_filter={groesstes['tag']}")
        self.assertEqual(antwort.status_code, 200)
        treffer = int(re.search(r"(\d+) Vorgänge in der Auswahl", antwort.text).group(1))
        self.assertEqual(treffer, groesstes["anzahl"])

        klein = _client.get(f"/?tag_filter={groesstes['tag'].lower()}")
        self.assertEqual(
            int(re.search(r"(\d+) Vorgänge in der Auswahl", klein.text).group(1)),
            groesstes["anzahl"],
            "Gross- und Kleinschreibung ergeben verschiedene Ergebnisse"
        )

    def test_db06_suche_findet_ueber_tags(self):
        # Vorgang 18204843. Ein Tag, das in KEINEM Titel und in KEINER
        # Beschreibung vorkommt - sonst belegt der Fall nichts.
        vorgaenge = _bestand()
        for eintrag in tag_wolke(vorgaenge):
            tag = eintrag["tag"]
            anderswo = any(
                tag.lower() in (str(i.get("title", "")) + str(i.get("description", ""))).lower()
                for i in vorgaenge
            )
            if not anderswo:
                antwort = _client.get(f"/?search={tag}")
                treffer = int(re.search(r"(\d+) Vorgänge in der Auswahl", antwort.text).group(1))
                self.assertGreaterEqual(
                    treffer, 1,
                    f"Die Suche nach dem Tag '{tag}' findet nichts, obwohl "
                    f"{eintrag['anzahl']} Vorgaenge es tragen"
                )
                return
        self.skipTest("Kein Tag gefunden, das nur als Tag vorkommt.")

    def test_db07_kennzahlen_beschreiben_den_bestand(self):
        # Vorgang 05f65255: bis Build 646 wurden sie aus der GEFILTERTEN
        # Menge gebildet und sahen trotzdem aus wie Bestandszahlen.
        gesamt = len(_bestand())

        def _kachel(html):
            return int(html.split('stat-number">')[1].split("<")[0])

        self.assertEqual(_kachel(self.startseite.text), gesamt)

        gefiltert = _client.get("/?status_filter=open")
        self.assertEqual(
            _kachel(gefiltert.text), gesamt,
            "Die Kennzahlen folgen wieder dem Filter - die Zahlen sehen aus "
            "wie Bestandszahlen und sind Auswahlzahlen"
        )
        # Die Zahl der AUSWAHL steht weiterhin bei der Blaetter-Bedienung.
        auswahl = int(re.search(r"(\d+) Vorgänge in der Auswahl", gefiltert.text).group(1))
        self.assertLessEqual(auswahl, gesamt)

    def test_db08_detailansicht_gibt_zeilen_als_bloecke_aus(self):
        # Vorgang d2ade5dc.
        mit_umbruch = [i for i in _bestand() if "\n" in str(i.get("description") or "")]
        if not mit_umbruch:
            self.skipTest("Kein Vorgang mit Zeilenumbruch im Bestand.")
        vorgang = mit_umbruch[0]

        html = _client.get(f"/issue/{vorgang['id']}").text
        self.assertIn('class="textblock"', html)
        erwartet = str(vorgang["description"]).replace("\r\n", "\n").count("\n") + 1
        self.assertGreaterEqual(
            html.count('<span class="zeile">'), erwartet,
            "Die Zeilen der Beschreibung erscheinen nicht als eigene Bloecke"
        )


if __name__ == "__main__":
    unittest.main()
