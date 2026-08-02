# =============================================================================
# tests/test_issue_tracker_formular.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Testsuite fuer Build 649: die Maske weist ab, statt zu verwerfen - und die
# Filter nehmen mehrere Werte.
#
# ACHT VORGAENGE, DIE HIER FESTGENAGELT WERDEN:
#
#   237503ce  Titel wurde bei 80 Zeichen stillschweigend gekuerzt
#   fd0d5d52  die Maske konnte den Bestand schemawidrig machen
#   ed9205cc  unlesbare Aufwandsangabe wurde still verworfen
#   04a0a4bc  unbekannte Verweise wurden still verworfen
#   b2175ac7  der Aenderungsvermerk blieb immer leer (tote Bedingung)
#   044ca2ee  Schnellaktion liess die Fassung leer
#   08e62af3  die Rueckrichtung der Verweise wurde nie angezeigt
#   3aaf1315  confirmDelete() ohne Loeschweg
#   f42afcd9  Filter mit Mehrfachauswahl (mc)
#   01fedc41  Tag-Wolke soll den Hauptfiltern folgen (mc)
#
# DIE ERSTEN VIER HABEN EINE URSACHE: es gab keinen Weg zurueck. save_issue
# konnte nur speichern oder mit einem HTTP-Fehler abbrechen - und ein Abbruch
# haette die Eingabe genauso verloren. Also wurde stillschweigend
# zurechtgebogen. Ab Build 649 kommt das Formular MIT DEN EINGABEN zurueck.
#
# ZWEI EBENEN wie in den uebrigen Tracker-Suiten: Ebene A am laufenden Server
# (braucht fastapi/jinja2/python-multipart/httpx, wird sonst mit Grund
# uebersprungen), Ebene B an den Vorlagen und laeuft immer.
#
# FM01 - JEDER VORGANG DES BESTANDS uebersteht die Pruefung unveraendert.
# FM02 - zu langer Titel: 400, Meldung, Eingabe bleibt stehen, nichts gespeichert.
# FM03 - krumme Versionsangabe: 400.
# FM04 - Aufwand: 'viel' wird abgewiesen, '2,5' wird angenommen.
# FM05 - unbekannter Verweis: 400; ein SCHON GESPEICHERTER Verweis bleibt erlaubt.
# FM06 - der Aenderungsvermerk nennt die geaenderten Felder.
# FM07 - 'leer' und 'nicht vorhanden' gelten als dasselbe (keine erfundene Aenderung).
# FM08 - die Detailansicht zeigt beide Richtungen der Verweise.
# FM09 - die Schnellaktion traegt die laufende Fassung ein.
# MF01 - ODER innerhalb einer Filterart, UND zwischen den Filterarten.
# MF02 - leere Filterwerte filtern nichts weg.
# MF03 - die Tag-Wolke folgt den Hauptfiltern.
# MF04 - sie folgt NICHT dem Tag-Filter (sonst Sackgasse).
# MF05 - ein gesetztes Tag bleibt sichtbar und laesst sich abwaehlen.
# MF06 - das Blaettern traegt alle Filterwerte weiter.
# FV01 - GEGENPROBE AN DEN VORLAGEN: Feld fuer den Aufwand, Mehrfachauswahl,
#        Rueckrichtung, kein totes JavaScript.
#
# Version: v0.8.649 - Build: 649 - 2026-08-01
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

_client = None
_modul = None
_grund = ""
_arbeit = None
_umgebung_vorher = {}

#: Siehe test_issue_tracker_oberflaeche.py: 'BACKUP_DIR' wird auch von merge.py
#: ausgewertet. Bleibt der Wert stehen, faellt MG09 in einer ANDEREN Datei um.
_UMGEBUNGSSCHLUESSEL = ("DATA_DIR", "ISSUES_FILE", "TEMPLATES_DIR",
                        "STATIC_DIR", "LOGS_DIR", "BACKUP_DIR")


def setUpModule():
    global _client, _modul, _grund, _arbeit

    for schluessel in _UMGEBUNGSSCHLUESSEL:
        _umgebung_vorher[schluessel] = os.environ.get(schluessel)

    if not VORLAGEN.is_dir():
        _grund = "issue-tracker/templates fehlt im Bestand."
        return

    _arbeit = Path(tempfile.mkdtemp(prefix="tracker_fm_"))
    (_arbeit / "data").mkdir()
    quelle = TRACKER / "data" / "issues.json"
    if quelle.exists():
        shutil.copy2(quelle, _arbeit / "data" / "issues.json")
    else:
        (_arbeit / "data" / "issues.json").write_text('{"issues": []}', encoding="utf-8")

    os.environ.update({
        "DATA_DIR": str(_arbeit / "data"),
        "ISSUES_FILE": str(_arbeit / "data" / "issues.json"),
        "TEMPLATES_DIR": str(VORLAGEN),
        "STATIC_DIR": str(_arbeit / "static"),
        "LOGS_DIR": str(_arbeit / "logs"),
        "BACKUP_DIR": str(_arbeit / "backups"),
    })

    try:
        from fastapi.testclient import TestClient
        import multipart  # noqa: F401
        import importlib.util

        # EIGENER MODULNAME: das Paket fuehrt selbst ein Verzeichnis 'server/',
        # und 'import server' liefert im Verbund dieses statt der Datei des
        # Trackers (Vorgang 7c7a738f).
        spez = importlib.util.spec_from_file_location(
            "issue_tracker_server_formular", TRACKER / "server.py")
        _modul = importlib.util.module_from_spec(spez)
        sys.modules["issue_tracker_server_formular"] = _modul
        spez.loader.exec_module(_modul)
        _client = TestClient(_modul.app)
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
    if _arbeit:
        shutil.rmtree(_arbeit, ignore_errors=True)


def _bestand():
    return json.loads(Path(os.environ["ISSUES_FILE"]).read_text(encoding="utf-8"))["issues"]


def _felder(v, **abweichungen):
    """Genau das, was issue_form.html abschickt."""
    felder = {
        "issue_id": v["id"], "type": v["type"], "title": v["title"],
        "affected_version": v["affected_version"], "reporter": v["reporter"],
        "priority": v.get("priority", "medium"), "severity": v.get("severity", "minor"),
        "prerequisites": v.get("prerequisites", ""), "description": v.get("description", ""),
        "expected_behavior": v.get("expected_behavior", ""),
        "actual_behavior": v.get("actual_behavior", ""),
        "assigned_to": v.get("assigned_to", ""),
        "target_version": v.get("target_version") or "",
        "tags": ", ".join(v.get("tags") or []),
        "related_to": ", ".join(v.get("related_to") or []),
        "estimated_hours": "", "os": "", "browser": "", "python_version": "", "database": "",
    }
    felder.update(abweichungen)
    return felder


#: Die Zahl steht einmal als Text der Blaetterzeile und - bis Build 649 -
#: auch in den 'title'-Attributen der Tag-Wolke. Das Muster verlangt deshalb
#: das Zeichen davor: '>' (Textanfang im Element) oder '&mdash;'. BEFUND AUS
#: DEM ERSTEN LAUF DIESER SUITE: ohne diese Verankerung traf die Suche den
#: ersten Tag-Titel und lieferte '1' fuer jede Abfrage.
_AUSWAHLMUSTER = re.compile(r"(?:>|&mdash;)\s*(\d+) Vorgänge in der Auswahl")


def _auswahl(antwort) -> int:
    """Die Zahl der Vorgaenge in der Auswahl, aus der Blaetterzeile."""
    treffer = _AUSWAHLMUSTER.search(antwort.text)
    return int(treffer.group(1)) if treffer else antwort.text.count('class="issue-item"')


def _tags(antwort) -> int:
    return antwort.text.count('class="tag tag-stufe-')


class Grundgeruest(unittest.TestCase):
    def setUp(self):
        if _client is None:
            self.skipTest(_grund)
        # Frische Kopie vor jedem Fall: diese Suite schreibt, und ein Test,
        # dessen Ausgang von der Reihenfolge abhaengt, belegt nichts.
        quelle = TRACKER / "data" / "issues.json"
        if quelle.exists():
            shutil.copy2(quelle, os.environ["ISSUES_FILE"])


class TestFormular(Grundgeruest):

    def test_fm01_jeder_vorgang_uebersteht_die_pruefung(self):
        """
        DER WICHTIGSTE FALL DIESER SUITE - und ein Befund aus dem ersten Lauf.

        Die erste Fassung der Pruefung verlangte eine Beschreibung. Damit
        liess sich ein Vorgang des Bestands nicht mehr speichern, der keine
        hat. EINE MASKE DARF NICHT STRENGER SEIN ALS DAS SCHEMA - sonst
        sperrt sie Vorgaenge aus, die regelgerecht im Bestand stehen, und der
        Fehler faellt erst auf, wenn jemand genau diesen Vorgang bearbeiten
        will.
        """
        vorgaenge = _bestand()
        kennungen = {v["id"] for v in vorgaenge}
        abgewiesen = []
        for v in vorgaenge:
            werte = {
                "title": v.get("title"),
                "affected_version": v.get("affected_version"),
                "target_version": v.get("target_version") or "",
                "reporter": v.get("reporter"),
                "estimated_hours": v.get("estimated_hours", ""),
                "related_to_liste": list(v.get("related_to") or []),
            }
            meldungen = _modul.pruefe_formular(werte, kennungen,
                                               list(v.get("related_to") or []))
            if meldungen:
                abgewiesen.append((v["id"][:8], meldungen))
        self.assertEqual(abgewiesen, [], f"Die Maske weist eigenen Bestand ab: {abgewiesen}")

    def test_fm02_zu_langer_titel_wird_abgewiesen(self):
        v = _bestand()[0]
        vorher = json.dumps(_bestand(), sort_keys=True)

        antwort = _client.post("/issue/save",
                               data=_felder(v, title="X" * 120),
                               follow_redirects=False)

        self.assertEqual(antwort.status_code, 400)
        self.assertIn("erlaubt sind 80", antwort.text)
        self.assertIn("X" * 120, antwort.text, "Die Eingabe steht nicht mehr im Formular")
        self.assertEqual(json.dumps(_bestand(), sort_keys=True), vorher,
                         "Trotz Abweisung wurde geschrieben")

    def test_fm03_krumme_versionsangabe_wird_abgewiesen(self):
        v = _bestand()[0]
        for feld, wert in (("affected_version", "0.8"), ("target_version", "spaeter")):
            with self.subTest(feld=feld):
                antwort = _client.post("/issue/save", data=_felder(v, **{feld: wert}),
                                       follow_redirects=False)
                self.assertEqual(antwort.status_code, 400)
                self.assertIn("Versionsmuster", antwort.text)

    def test_fm04_aufwand(self):
        v = _bestand()[0]

        schlecht = _client.post("/issue/save", data=_felder(v, estimated_hours="viel"),
                                follow_redirects=False)
        self.assertEqual(schlecht.status_code, 400)
        self.assertIn("keine Zahl", schlecht.text)

        negativ = _client.post("/issue/save", data=_felder(v, estimated_hours="-2"),
                               follow_redirects=False)
        self.assertEqual(negativ.status_code, 400)

        # Das deutsche Komma muss durchgehen - alles andere waere eine Falle.
        gut = _client.post("/issue/save", data=_felder(v, estimated_hours="2,5"),
                           follow_redirects=False)
        self.assertEqual(gut.status_code, 303)
        gespeichert = {i["id"]: i for i in _bestand()}[v["id"]]
        self.assertEqual(gespeichert.get("estimated_hours"), 2.5)

    def test_fm05_verweise(self):
        vorgaenge = _bestand()
        mit_verweisen = [v for v in vorgaenge if v.get("related_to")]
        if not mit_verweisen:
            self.skipTest("Kein Vorgang mit Verweisen.")
        v = mit_verweisen[0]

        # Unbekannter Verweis -> abgewiesen, Eingabe bleibt stehen.
        antwort = _client.post(
            "/issue/save",
            data=_felder(v, related_to="99999999-0000-4000-8000-000000000000"),
            follow_redirects=False)
        self.assertEqual(antwort.status_code, 400)
        self.assertIn("keinen Vorgang", antwort.text)
        self.assertIn("99999999", antwort.text)

        # Die BESTEHENDEN Verweise muessen weiterhin durchgehen - auch wenn
        # einer davon unbekannt waere. Sonst entfernte die Maske Altlasten
        # stillschweigend, und genau das war der Fehler aus Build 645.
        weiter = _client.post("/issue/save", data=_felder(v), follow_redirects=False)
        self.assertEqual(weiter.status_code, 303)
        self.assertEqual({i["id"]: i for i in _bestand()}[v["id"]]["related_to"],
                         v["related_to"])

    def test_fm06_aenderungsvermerk_nennt_die_felder(self):
        v = next(x for x in _bestand() if x.get("description"))
        anzahl_vorher = len(v.get("updates") or [])

        antwort = _client.post("/issue/save",
                               data=_felder(v, priority="low", assigned_to="Prüfer"),
                               follow_redirects=False)

        self.assertEqual(antwort.status_code, 303)
        vermerk = {i["id"]: i for i in _bestand()}[v["id"]]["updates"][anzahl_vorher]["comment"]
        self.assertIn("Zuständig", vermerk,
                      f"Der Vermerk nennt die Aenderung nicht: {vermerk!r}")
        self.assertIn("Prüfer", vermerk)

    def test_fm07_leer_und_nicht_vorhanden_sind_dasselbe(self):
        """
        Befund aus dem ersten Lauf: Nicht jeder Vorgang fuehrt jedes Feld.
        Kommt aus dem Formular eine leere Zeichenkette, meldete der Vergleich
        'Beschreibung geaendert' - eine erfundene Aenderung. Ein Vermerk, der
        Aenderungen erfindet, ist so wenig wert wie einer, der keine nennt.
        """
        ohne_feld = [x for x in _bestand()
                     if not x.get("prerequisites") and not x.get("actual_behavior")]
        if not ohne_feld:
            self.skipTest("Kein Vorgang ohne diese Felder.")
        v = ohne_feld[0]
        anzahl_vorher = len(v.get("updates") or [])

        _client.post("/issue/save", data=_felder(v), follow_redirects=False)

        vermerk = {i["id"]: i for i in _bestand()}[v["id"]]["updates"][anzahl_vorher]["comment"]
        for erfunden in ("Voraussetzungen geändert", "Tatsächliches Verhalten geändert"):
            self.assertNotIn(erfunden, vermerk, f"Erfundene Aenderung: {vermerk!r}")

    def test_fm08_detailansicht_zeigt_beide_richtungen(self):
        vorgaenge = _bestand()
        verwiesen = {r for v in vorgaenge for r in (v.get("related_to") or [])}
        ziel = next((v for v in vorgaenge if v["id"] in verwiesen), None)
        if ziel is None:
            self.skipTest("Auf keinen Vorgang wird verwiesen.")

        html = _client.get(f"/issue/{ziel['id']}").text
        self.assertIn("Wird verwiesen von", html,
                      "Die Rueckrichtung wird berechnet und nicht angezeigt - "
                      "genau der Zustand aus Vorgang 08e62af3")

    def test_fm09_schnellaktion_traegt_die_fassung(self):
        offen = next((v for v in _bestand() if v["status"] in ("open", "in_progress")), None)
        if offen is None:
            self.skipTest("Kein offener Vorgang.")

        html = _client.get(f"/issue/{offen['id']}").text
        treffer = re.search(r'name="resolved_version" value="([^"]*)"', html)
        self.assertIsNotNone(treffer, "Die Schnellaktion schickt keine Fassung mit")
        self.assertRegex(treffer.group(1), r"^\d+\.\d+\.\d+[a-z]?$",
                         "Die mitgeschickte Fassung ist keine Versionsangabe")


class TestFilter(Grundgeruest):

    def test_mf01_oder_innerhalb_und_zwischen_den_arten(self):
        einzeln = {}
        for wert in ("critical", "high"):
            einzeln[wert] = _auswahl(_client.get(f"/?priority_filter={wert}"))
        beide = _auswahl(_client.get("/?priority_filter=critical&priority_filter=high"))

        self.assertEqual(beide, einzeln["critical"] + einzeln["high"],
                         "Mehrere Werte einer Filterart sind nicht mit ODER verknüpft")

        # UND zwischen den Arten: die Schnittmenge kann nur kleiner sein.
        offen = _auswahl(_client.get("/?status_filter=open"))
        kombiniert = _auswahl(_client.get("/?status_filter=open&priority_filter=high"))
        self.assertLessEqual(kombiniert, min(offen, einzeln["high"]))

    def test_mf02_leere_werte_filtern_nichts_weg(self):
        # Ein <select> ohne Auswahl schickt seinen leeren Eintrag mit. Ohne
        # Reinigung wuerde der Filter alles wegwerfen, und die Seite zeigte
        # einfach nichts an - ein Fehler, den man lange sucht.
        self.assertEqual(_auswahl(_client.get("/?status_filter=&type_filter=&assigned_to=")),
                         _auswahl(_client.get("/")))

    def test_mf03_wolke_folgt_den_hauptfiltern(self):
        ohne = _tags(_client.get("/"))
        mit = _tags(_client.get("/?status_filter=closed"))
        self.assertGreater(ohne, 0)
        self.assertLess(mit, ohne,
                        "Die Wolke reagiert nicht auf die Hauptfilter - "
                        "Vorgang 01fedc41")

    def test_mf04_wolke_folgt_nicht_dem_tagfilter(self):
        """
        Die Ausnahme, und sie ist der Grund, warum die Wolke ueberhaupt
        bedienbar ist: Wuerde sie auch dem Tag-Filter folgen, bliebe nach dem
        ersten Klick nur noch das angeklickte Tag stehen - jeder weitere Weg
        waere verschwunden. mc hat in 01fedc41 ausdruecklich die HAUPTFILTER
        genannt.
        """
        wolke = _modul.issue_manager.get_tag_cloud(_bestand())
        if not wolke:
            self.skipTest("Keine Tags im Bestand.")
        groesstes = max(wolke, key=lambda e: e["anzahl"])["tag"]

        self.assertEqual(_tags(_client.get(f"/?tag_filter={groesstes}")),
                         _tags(_client.get("/")))

    def test_mf05_gesetztes_tag_bleibt_abwaehlbar(self):
        wolke = _modul.issue_manager.get_tag_cloud(_bestand())
        if not wolke:
            self.skipTest("Keine Tags im Bestand.")
        tag = max(wolke, key=lambda e: e["anzahl"])["tag"]

        antwort = _client.get(f"/?tag_filter={tag}")
        self.assertIn("tag-aktiv", antwort.text, "Das gesetzte Tag ist nicht markiert")

        # Es muss einen Verweis geben, der OHNE dieses Tag weiterfuehrt.
        self.assertIn("Tag-Auswahl aufheben", antwort.text)

        # Und zwei Tags gleichzeitig sind moeglich (ODER).
        weitere = [e["tag"] for e in wolke if e["tag"] != tag][:1]
        if weitere:
            zwei = _auswahl(_client.get(f"/?tag_filter={tag}&tag_filter={weitere[0]}"))
            eins = _auswahl(_client.get(f"/?tag_filter={tag}"))
            self.assertGreaterEqual(zwei, eins)

    def test_mf06_blaettern_traegt_alle_filterwerte(self):
        antwort = _client.get("/?status_filter=open&status_filter=resolved&priority_filter=high")
        if 'class="pagination"' not in antwort.text:
            self.skipTest("Die Auswahl passt auf eine Seite.")
        for erwartet in ("status_filter=open", "status_filter=resolved",
                         "priority_filter=high"):
            self.assertIn(erwartet, antwort.text,
                          f"Beim Blaettern geht '{erwartet}' verloren")


class TestVorlagen(unittest.TestCase):
    """FV01 - laeuft immer, auch ohne fastapi."""

    def setUp(self):
        if not VORLAGEN.is_dir():
            self.skipTest("issue-tracker/templates fehlt im Bestand.")

    def test_fv01a_formular_fuehrt_das_aufwandsfeld(self):
        html = (VORLAGEN / "issue_form.html").read_text(encoding="utf-8")
        self.assertIn('name="estimated_hours"', html,
                      "server.py liest den Aufwand, die Maske bietet ihn nicht an")
        self.assertIn('name="related_to"', html)

    def test_fv01b_filter_sind_mehrfachauswahl(self):
        html = (VORLAGEN / "index.html").read_text(encoding="utf-8")
        for feld in ("status_filter", "type_filter", "priority_filter", "assigned_to"):
            block = html.split(f'name="{feld}"', 1)[1].split(">", 1)[0]
            self.assertIn("multiple", block, f"'{feld}' ist kein Mehrfachfeld")

    def test_fv01c_detailansicht_gibt_die_rueckrichtung_aus(self):
        html = (VORLAGEN / "issue_detail.html").read_text(encoding="utf-8")
        self.assertIn("referencing_issues", html,
                      "server.py berechnet die Rueckrichtung, die Vorlage gibt "
                      "sie nicht aus (Vorgang 08e62af3)")

    def test_fv01d_kein_totes_javascript(self):
        # OHNE DIE JINJA-KOMMENTARE - derselbe Befund wie bei SW06 in Build
        # 642: die Vorlage ERKLAERT, dass confirmDelete() entfallen ist, und
        # eine Textsuche findet diese Erklaerung. Ein Test, der die
        # Dokumentation seines Gegenstands nicht von dessen Inhalt
        # unterscheidet, zwingt dazu, Erklaerungen wegzulassen.
        roh = (VORLAGEN / "base.html").read_text(encoding="utf-8")
        html = re.sub(r"\{#.*?#\}", "", roh, flags=re.S)
        self.assertNotIn("confirmDelete", html,
                         "confirmDelete() ohne Loeschweg (Vorgang 3aaf1315)")
        self.assertNotIn("<script", html,
                         "Die Oberflaeche soll ohne JavaScript auskommen - "
                         "wie das Forum selbst")


if __name__ == "__main__":
    unittest.main()
