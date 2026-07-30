# =============================================================================
# tests/test_management_static.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 347: statische Auslieferung der Cockpit-Shell.
#
# S01 — StaticAssets: liefert eine vorhandene Datei mit korrektem MIME.
# S02 — StaticAssets: MIME-Whitelist je Endung (html/js/css/map/svg).
# S03 — StaticAssets: nicht vorhandene Datei -> 404.
# S04 — StaticAssets: nicht erlaubte Endung -> 404.
# S05 — StaticAssets: Traversal '..' / fuehrendes '/' / Backslash / leer -> 400.
# S06 — StaticAssets: Unterverzeichnis (vendor/...) wird ausgeliefert.
# S07 — StaticAssets: realpath-Containment faengt Ausbruch ueber Unterpfad ab.
# S08 — ManagementApp: '/' liefert die ECHTE cockpit.html (Nav-Container).
# S09 — ManagementApp: '/static/<f>' liefert echtes Asset; fehlend -> 404;
#       Traversal -> 400.
# S10 — ManagementApp: die vendorte Tabulator-Datei ist ausgeliefert (JS-MIME).
#
# Version: v0.7.347 · Build: 347 · 2026-07-10
# =============================================================================

import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.server.static_assets import StaticAssets
from management.server.management_app import ManagementApp, STATIC_DIR


class StaticAssetsTests(unittest.TestCase):
    """Isolierte Tests der Auslieferungslogik ueber ein Temp-Verzeichnis."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        base = Path(self._tmp)
        (base / "cockpit.html").write_text(
            "<!doctype html><nav id=\"aiw-nav\"></nav>", encoding="utf-8")
        (base / "cockpit.js").write_text("// js", encoding="utf-8")
        (base / "cockpit.css").write_text("/* css */", encoding="utf-8")
        (base / "map.map").write_text("{}", encoding="utf-8")
        (base / "icon.svg").write_text("<svg/>", encoding="utf-8")
        (base / "secret.txt").write_text("geheim", encoding="utf-8")
        sub = base / "vendor" / "lib"
        sub.mkdir(parents=True)
        (sub / "lib.min.js").write_text("// vendor", encoding="utf-8")
        self.assets = StaticAssets(base)
        # Nachbardatei ausserhalb des Basisverzeichnisses (fuer Containment).
        self._outside = Path(self._tmp).parent

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    # S01 --------------------------------------------------------------------
    def test_s01_serve_existing(self):
        status, ctype, body = self.assets.serve("cockpit.html")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"aiw-nav", body)

    # S02 --------------------------------------------------------------------
    def test_s02_mime_whitelist(self):
        cases = {
            "cockpit.js": "javascript",
            "cockpit.css": "text/css",
            "map.map": "application/json",
            "icon.svg": "image/svg",
        }
        for rel, needle in cases.items():
            status, ctype, _ = self.assets.serve(rel)
            self.assertEqual(status, 200, rel)
            self.assertIn(needle, ctype, rel)

    # S03 --------------------------------------------------------------------
    def test_s03_missing(self):
        status, _, _ = self.assets.serve("fehlt.js")
        self.assertEqual(status, 404)

    # S04 --------------------------------------------------------------------
    def test_s04_disallowed_suffix(self):
        # Vorhandene Datei, aber Endung nicht in der Whitelist -> 404.
        status, _, _ = self.assets.serve("secret.txt")
        self.assertEqual(status, 404)

    # S05 --------------------------------------------------------------------
    def test_s05_traversal_rejected(self):
        for bad in ["../secret.txt", "/etc/passwd", "a\\b.js", ""]:
            status, _, _ = self.assets.serve(bad)
            self.assertEqual(status, 400, bad)

    # S06 --------------------------------------------------------------------
    def test_s06_subdir(self):
        status, ctype, body = self.assets.serve("vendor/lib/lib.min.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)
        self.assertIn(b"vendor", body)

    # S07 --------------------------------------------------------------------
    def test_s07_containment(self):
        # 'vendor/../../secret.txt' enthaelt '..' -> bereits durch die
        # String-Abwehr 400 (Containment ist das zweite Fangnetz).
        status, _, _ = self.assets.serve("vendor/../../secret.txt")
        self.assertEqual(status, 400)

    # S08 --------------------------------------------------------------------
    def test_s08_app_index_real_cockpit(self):
        # ManagementApp ohne DB-Zugriff fuer '/': static_dir zeigt auf das
        # ECHTE Asset-Verzeichnis (STATIC_DIR).
        app = ManagementApp(":memory:", static_dir=STATIC_DIR)
        r = app.dispatch(1, "/")
        self.assertEqual(r.status, 200)
        self.assertIn("text/html", r.content_type)
        self.assertIn("id=\"aiw-nav\"", r.body.decode("utf-8"))

    # S09 --------------------------------------------------------------------
    def test_s09_app_static_paths(self):
        app = ManagementApp(":memory:", static_dir=Path(self._tmp))
        r_ok = app.dispatch(1, "/static/cockpit.js")
        self.assertEqual(r_ok.status, 200)
        self.assertIn("javascript", r_ok.content_type)

        r_missing = app.dispatch(1, "/static/fehlt.js")
        self.assertEqual(r_missing.status, 404)

        r_trav = app.dispatch(1, "/static/../secret.txt")
        self.assertEqual(r_trav.status, 400)

    # S10 --------------------------------------------------------------------
    def test_s10_vendored_tabulator_served(self):
        # Die management-lokale Tabulator-Kopie muss real ausgeliefert werden.
        app = ManagementApp(":memory:", static_dir=STATIC_DIR)
        r = app.dispatch(1, "/static/vendor/tabulator/tabulator.min.js")
        self.assertEqual(r.status, 200)
        self.assertIn("javascript", r.content_type)
        self.assertGreater(len(r.body), 1000)


class GeteilteAssetsTests(unittest.TestCase):
    """
    Build 576: geteilte Dateien aus anderen Baustellen.

    Die Management-Oberflaeche braucht das Editor.js-Buendel und das
    Chip-Modul samt Stildatei, die in Baustelle 6 liegen. Ausgeliefert wird
    ueber eine EXAKTE Positivliste - kein zweites durchsuchbares Wurzel-
    verzeichnis. Diese Suite haelt genau das fest.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._basis = Path(self._tmp) / "static"
        self._basis.mkdir()
        (self._basis / "cockpit.js").write_text("// eigen\n", encoding="utf-8")
        # Eine 'fremde' Datei ausserhalb des Basisverzeichnisses.
        self._fremd = Path(self._tmp) / "fremd"
        self._fremd.mkdir()
        self._geteilt = self._fremd / "shared_modul.js"
        self._geteilt.write_text("// geteilt\n", encoding="utf-8")
        self._fehlt = self._fremd / "gibtsnicht.js"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _assets(self, mit_fehlend=False):
        geteilt = {"shared/modul.js": self._geteilt}
        if mit_fehlend:
            geteilt["shared/weg.js"] = self._fehlt
        return StaticAssets(self._basis, geteilt=geteilt)

    # GA01 ---------------------------------------------------------------
    def test_GA01_geteilte_datei_wird_ausgeliefert(self):
        st, ctype, body = self._assets().serve("shared/modul.js")
        self.assertEqual(st, 200)
        self.assertIn("javascript", ctype)
        self.assertEqual(body, b"// geteilt\n")

    # GA02 ---------------------------------------------------------------
    def test_GA02_eigene_dateien_unveraendert(self):
        """Die Positivliste darf den normalen Weg nicht stoeren."""
        st, _, body = self._assets().serve("cockpit.js")
        self.assertEqual(st, 200)
        self.assertEqual(body, b"// eigen\n")

    # GA03 ---------------------------------------------------------------
    def test_GA03_nur_wortgleiche_schluessel(self):
        """
        DER KERN DER FORM: eine URL kann nur ein WORTGLEICHER Schluessel sein.
        Kein Praefix, kein Verzeichnis, kein Muster - sonst waere aus der
        Positivliste ein zweites durchsuchbares Wurzelverzeichnis geworden.
        """
        a = self._assets()
        for pfad in ("shared/anderes.js", "shared/", "shared/sub/modul.js",
                     "SHARED/modul.js", "shared/modul.js.js"):
            st, _, _ = a.serve(pfad)
            self.assertIn(st, (400, 404),
                          "'%s' haette nicht ausgeliefert werden duerfen" % pfad)

    # GA04 ---------------------------------------------------------------
    def test_GA04_traversal_bleibt_abgewiesen(self):
        """Die bestehende Abwehr wird durch die Positivliste nicht weicher."""
        a = self._assets()
        for pfad in ("../fremd/shared_modul.js", "shared/../../fremd/x.js",
                     "/etc/passwd", "..\\fremd\\x.js"):
            st, _, _ = a.serve(pfad)
            self.assertIn(st, (400, 404), pfad)

    # GA05 ---------------------------------------------------------------
    def test_GA05_endungspruefung_gilt_auch_geteilt(self):
        """Ein geteilter Eintrag mit unerlaubter Endung wird NICHT geliefert."""
        heikel = self._fremd / "skript.exe"
        heikel.write_bytes(b"MZ")
        a = StaticAssets(self._basis, geteilt={"shared/skript.exe": heikel})
        st, _, _ = a.serve("shared/skript.exe")
        self.assertEqual(st, 404)

    # GA06 ---------------------------------------------------------------
    def test_GA06_fehlende_datei_wird_benannt(self):
        """
        Ein Eintrag ohne Datei ist ein EINRICHTUNGSFEHLER und muss auffallen -
        beim Start, nicht erst wenn im Browser ein Modul fehlt. Genau dieser
        Unterschied hat in Build 570/571 einen Abend gekostet.
        """
        a = self._assets(mit_fehlend=True)
        fehlend = a.fehlende_geteilte()
        self.assertEqual(list(fehlend), ["shared/weg.js"])
        st, _, body = a.serve("shared/weg.js")
        self.assertEqual(st, 404)
        self.assertIn(b"Geteiltes Asset", body)
        # Der vorhandene Eintrag bleibt davon unberuehrt.
        self.assertEqual(a.serve("shared/modul.js")[0], 200)

    # GA07 ---------------------------------------------------------------
    def test_GA07_ohne_positivliste_wie_bisher(self):
        """Rueckwaertskompatibel: der Aufruf ohne 'geteilt' verhaelt sich
        unveraendert."""
        a = StaticAssets(self._basis)
        self.assertEqual(a.geteilte_pfade(), {})
        self.assertEqual(a.serve("cockpit.js")[0], 200)
        self.assertEqual(a.serve("shared/modul.js")[0], 404)


class GeteilteAssetsProjektTests(unittest.TestCase):
    """
    Build 576: die Positivliste des ECHTEN Projekts. Diese Suite haelt die
    Pfade gegen den Baum - ein verschobenes Modul faellt hier auf und nicht
    im Browser.
    """

    def test_GA08_projektpfade_existieren(self):
        from management.server.management_app import GETEILTE_ASSETS
        fehlend = {rel: str(p) for rel, p in GETEILTE_ASSETS.items()
                   if not p.is_file()}
        self.assertEqual(fehlend, {},
                         "Geteilte Datei(en) nicht am erwarteten Ort.")

    def test_GA09_chip_stile_sind_herausgeloest(self):
        """
        Build 576 hat die Chip-Regeln aus report.css in eine eigene Datei
        gezogen. Diese Pruefung haelt beides fest: die Regeln stehen in der
        neuen Datei UND nicht mehr in report.css. Ohne sie koennte eine
        spaetere Aenderung stillschweigend eine zweite Kopie anlegen.
        """
        import re
        from management.server.management_app import _REPO_WURZEL
        chips = (_REPO_WURZEL / "userinfo" / "placeholder_chips.css")
        report = (_REPO_WURZEL / "userinfo" / "report.css")
        self.assertTrue(chips.is_file(), "placeholder_chips.css fehlt.")
        c = chips.read_text(encoding="utf-8")
        r = report.read_text(encoding="utf-8")
        sel_chips = set(re.findall(r"\.ph-chip[\w-]*", c))
        sel_report = set(re.findall(r"\.ph-chip[\w-]*", r))
        # Alle sieben Chip-Selektoren aus Build 576.
        self.assertGreaterEqual(len(sel_chips), 7, sorted(sel_chips))
        self.assertEqual(sel_report, set(),
                         "Chip-Regeln stehen wieder in report.css: %s"
                         % sorted(sel_report))
        # Die Druckregel ist mit ihrem @media-Rahmen mitgekommen - ohne ihn
        # waere sie wirkungslos.
        self.assertIn("@media print", c)


if __name__ == "__main__":
    unittest.main()
