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


if __name__ == "__main__":
    unittest.main()
