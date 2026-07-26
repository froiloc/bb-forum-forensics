# =============================================================================
# tests/test_tatzeit_panel_routing.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Testsuite fuer Build 534: die Auslieferung von toolbar/tatzeit_panel.js.
#
# ── WARUM DIESE SUITE EXISTIERT ──────────────────────────────────────────────
#
#   Eine neue Frontend-Datei muss an DREI Stellen bekannt sein, damit sie im
#   Browser ankommt:
#     1. forensic_api/static.py   -> _RESOURCES (Datei und MIME-Typ)
#     2. forensic_api/__init__.py -> Allowlist im Dispatcher
#     3. server/shell_handler.py  -> <script>-Tag in der Shell-HTML
#
#   FEHLT EINE DAVON, IST DER AUSFALL STILL. Das ist in diesem Projekt schon
#   zweimal passiert und in build.json des Builds 493 wortwoertlich
#   festgehalten: validation_rules.js und placeholder_links.js waren "BIS BUILD
#   492 UNGEROUTET (in report.py eingebunden, aber in KEINER Allowlist -> HTTP
#   404, window.ValidationRules blieb undefined; die Live-Formatpruefung im
#   Browser lief nie)".
#
#   Bei der Tatzeit waere derselbe Fehler besonders unangenehm: eine fehlende
#   Maske sieht nicht aus wie ein Fehler, sondern wie "hier ist nichts zu
#   erfassen".
#
#   TR-P01 — Der Endpunkt ANTWORTET (200 + JavaScript-MIME-Typ). Keine
#            Registry-Pruefung, sondern ein echter Abruf durch den Dispatcher.
#   TR-P02 — Die Datei liegt auf der Platte und ist nicht leer.
#   TR-P03 — Die Shell-HTML bindet sie ein, UND ZWAR NACH toolbar.js
#            (toolbar.js prueft beim Oeffnen des Popups auf window.TatzeitPanel).
#   TR-P04 — DIE ALLGEMEINE FASSUNG DES FEHLERS: jede Ressource, die die Shell
#            per <script>/<link> einbindet, wird vom Dispatcher auch
#            ausgeliefert. Dieser Test findet den naechsten ungerouteten
#            Eintrag, ohne dass jemand daran denken muss.
#   TR-P05 — Der Ankerpunkt im Popup existiert in toolbar.js, und toolbar.js
#            meldet es, wenn die Datei fehlt (kein stiller Ausfall).
#
# Version: v0.8.534 · Build: 534 · 2026-07-26
# =============================================================================

import io
import os
import re
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config_loader import ConfigLoader                     # noqa: E402
from core.logger import reset_for_testing, setup_logging        # noqa: E402
from forensic_api import ForensicApi                            # noqa: E402

_WURZEL = Path(__file__).resolve().parent.parent
_PANEL = _WURZEL / "toolbar" / "tatzeit_panel.js"


def _config() -> ConfigLoader:
    reset_for_testing()
    tmp = tempfile.mkdtemp()
    pfad = os.path.join(tmp, "config.yaml")
    logfile = os.path.join(tmp, "logs", "test.log")
    with open(pfad, "w") as fh:
        fh.write(textwrap.dedent(f"""
            logging:
              level: "debug"
              logfile: "{logfile}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "./c.db"
              forensic_db_dir: "./f/"
              default_db: "./d.db"
              evidence_db_dir: "./e/"
            url_patterns:
              asset_prefixes:
                - "/forum/style/"
              alias_patterns:
                post_id_param: "pid"
                notify_param: "notify"
                fragment_post: "p"
        """))
    cfg = ConfigLoader(config_path=pfad)
    setup_logging(cfg)
    return cfg


def _handler() -> MagicMock:
    h = MagicMock()
    h.command = "GET"
    h.rfile = io.BytesIO(b"")
    h.headers = {"Content-Length": "0"}
    erfasst = {}

    def capture(status, body, content_type=None, extra_headers=None):
        erfasst["status"] = status
        erfasst["body"] = body
        erfasst["content_type"] = content_type

    h.send_response_body.side_effect = capture
    h._captured = erfasst
    return h


def _abruf(api, pfad: str) -> dict:
    h = _handler()
    api.dispatch(h, "GET", pfad, "", is_ajax=False)
    return h._captured


class TestTatzeitPanelAuslieferung(unittest.TestCase):

    def setUp(self):
        self.cfg = _config()
        self.ctx = MagicMock()
        self.ctx.mode = "cli"
        self.ctx.subject_id = 42
        self.ctx.investigator_id = 1
        self.api = ForensicApi(MagicMock(), self.ctx, self.cfg)

    def tearDown(self):
        reset_for_testing()

    # =================================================================== TR-P01
    def test_TRP01_endpunkt_antwortet(self):
        """
        Wirkungspruefung: nicht "steht in _RESOURCES", sondern "der Dispatcher
        liefert sie aus". Genau der Unterschied, an dem Build 492 gescheitert
        ist.
        """
        r = _abruf(self.api, "/_forensic/tatzeit_panel.js")
        self.assertEqual(r.get("status"), 200,
                         "tatzeit_panel.js wird nicht ausgeliefert — der "
                         "Aufklappbereich waere im Browser nicht vorhanden.")
        self.assertIn("javascript", (r.get("content_type") or "").lower())
        self.assertTrue(r.get("body"), "Leere Antwort.")
        self.assertIn(b"TatzeitPanel", r["body"])

    # =================================================================== TR-P02
    def test_TRP02_datei_liegt_vor_und_ist_nicht_leer(self):
        self.assertTrue(_PANEL.is_file(), "toolbar/tatzeit_panel.js fehlt.")
        quelle = _PANEL.read_text(encoding="utf-8")
        self.assertGreater(len(quelle), 1000)
        # IIFE-Wrapper mit 'use strict' ist Projektvorgabe fuer JavaScript.
        self.assertIn("(function ()", quelle)
        self.assertIn("'use strict'", quelle)
        self.assertIn("window.TatzeitPanel", quelle)

    # =================================================================== TR-P03
    def test_TRP03_shell_bindet_ein_und_zwar_nach_toolbar(self):
        from server import shell_handler

        # Die Shell wird aus Konstanten zusammengesetzt; geprueft wird der
        # tatsaechlich erzeugte Tag-Text, nicht der Variablenname.
        self.assertIn("/_forensic/tatzeit_panel.js",
                      shell_handler._TATZEIT_PANEL_JS_TAG)
        self.assertIn("<script", shell_handler._TATZEIT_PANEL_JS_TAG)

        quelle = (_WURZEL / "server" / "shell_handler.py").read_text(
            encoding="utf-8")
        # Die Reihenfolge im f-String der Shell entscheidet, was der Browser
        # zuerst laedt. toolbar.js MUSS vorher stehen — es prueft beim Oeffnen
        # des Popups auf window.TatzeitPanel.
        pos_toolbar = quelle.find("{_TOOLBAR_JS_TAG}")
        pos_panel = quelle.find("{_TATZEIT_PANEL_JS_TAG}")
        self.assertGreater(pos_toolbar, -1)
        self.assertGreater(pos_panel, -1)
        self.assertLess(pos_toolbar, pos_panel,
                        "tatzeit_panel.js wird VOR toolbar.js geladen — dann "
                        "ist window.ForensicToolbar beim Auswerten noch nicht "
                        "da.")

    # =================================================================== TR-P04
    def test_TRP04_jede_ressource_der_shell_wird_ausgeliefert(self):
        """
        DIE ALLGEMEINE FASSUNG DES FEHLERS aus Build 492/493.

        Statt nur die neue Datei zu pruefen, werden ALLE /_forensic/-Pfade
        eingesammelt, die die Shell-HTML einbindet, und einzeln abgerufen.
        Wer kuenftig eine Datei in die Shell haengt und die Allowlist vergisst,
        faellt hier auf — ohne dass jemand daran denken muss.
        """
        quelle = (_WURZEL / "server" / "shell_handler.py").read_text(
            encoding="utf-8")
        pfade = sorted(set(re.findall(r'["\'](/_forensic/[A-Za-z0-9_./-]+)', quelle)))
        self.assertGreaterEqual(len(pfade), 3,
                                "Es wurden kaum Shell-Ressourcen gefunden — "
                                "das Suchmuster passt vermutlich nicht mehr.")
        self.assertIn("/_forensic/tatzeit_panel.js", pfade)

        fehlend = []
        for p in pfade:
            r = _abruf(self.api, p)
            if r.get("status") != 200:
                fehlend.append("%s -> %s" % (p, r.get("status")))
        self.assertEqual(fehlend, [],
                         "Diese von der Shell eingebundenen Ressourcen werden "
                         "NICHT ausgeliefert (HTTP != 200): %s" % fehlend)

    # =================================================================== TR-P05
    def test_TRP05_toolbar_haengt_den_bereich_ein_und_meldet_sein_fehlen(self):
        quelle = (_WURZEL / "toolbar" / "toolbar.js").read_text(encoding="utf-8")
        self.assertIn('id="forensic-popup-tatzeit-mount"', quelle,
                      "Der Ankerpunkt im Popup fehlt.")
        self.assertIn("window.TatzeitPanel", quelle)
        # Kein stiller Ausfall: fehlt die Datei, wird das protokolliert.
        self.assertIn("tatzeit_panel.js nicht geladen", quelle,
                      "toolbar.js meldet ein fehlendes Panel nicht — der "
                      "Ausfall waere still, und eine fehlende Tatzeitmaske "
                      "sieht aus wie 'hier ist nichts zu erfassen'.")
        # Der Kategoriewechsel muss die Mahnung nachziehen.
        self.assertIn("_tatzeitPanel.setCategory", quelle)
        # Und beim Schliessen wird abgeraeumt.
        self.assertIn("_tatzeitPanel.destroy", quelle)


if __name__ == "__main__":
    unittest.main()
