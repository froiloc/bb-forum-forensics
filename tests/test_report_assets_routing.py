# =============================================================================
# tests/test_report_assets_routing.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck (Build 493):
#   REGRESSIONS-WAECHTER gegen "eingebunden, aber nicht ausgeliefert".
#
#   Die Berichts-Editor-Seite (forensic_api/report.py) bindet ihre Frontend-
#   Module ueber <script src="/_forensic/<name>.js"> bzw. <link href=...css>
#   ein. Ausgeliefert werden diese Dateien aber nur, wenn ihr Pfad in ZWEI
#   Allowlisten steht: der Dispatch-Tupel in forensic_api/__init__.py UND der
#   Registry _RESOURCES in forensic_api/static.py. Fehlt der Pfad in einer der
#   beiden, liefert der Server 404 — das Modul laedt nie, window.<Modul> bleibt
#   undefined, und das Feature ist im Produktivbetrieb still tot.
#
#   Genau das war bei Build 492 der Fall: placeholder_links.js wurde vom Wizard
#   benutzt (window.PlaceholderLinks), aber weder eingebunden noch geroutet —
#   die Stammvater/Klon-Mechanik war im Browser wirkungslos. Ebenso lag
#   validation_rules.js seit Build 389 uneingebunden/ungeroutet.
#
#   Dieser Test startet den echten Server, liest die von report.py
#   eingebundenen Flach-Asset-Pfade (/_forensic/<name>.js|css, OHNE die per
#   Praefix ausgelieferten /_forensic/static/*-Pfade) und fordert JEDEN an.
#   Jeder MUSS HTTP 200 liefern. So kann diese Fehlerklasse nicht mehr
#   unbemerkt zurueckkehren (Grundregel 3: Regressionstests Pflicht;
#   Grundregel 1: kein Beleg/Modul darf still uebersprungen werden).
#
# Version: v0.8.493 · Build: 493 · 2026-07-21
# Beleg: Routing-Defekt placeholder_links.js (Build 492), validation_rules.js
#        (Build 389); Projektgespraech 2026-07-21.
# =============================================================================

import re
import urllib.request
from pathlib import Path

# Wiederverwendung der vollstaendigen Server-Fixture aus den Integrationstests.
from tests.test_integration import _ServerFixture

_REPORT_PY = Path(__file__).resolve().parent.parent / "forensic_api" / "report.py"


def _included_flat_assets() -> list[str]:
    """
    Liest die von report.py eingebundenen Flach-Asset-Pfade.

    Beruecksichtigt <script src="..."> und <link href="...css">. Praefix-
    ausgelieferte Pfade (/_forensic/static/*, z.B. das Editor.js-Bundle)
    werden ausgeklammert — deren Auslieferung haengt vom Build-Zustand der
    VM ab (AP-E2) und wird ueber eigene Praefix-Handler getestet.
    """
    src = _REPORT_PY.read_text(encoding="utf-8")
    paths = set(re.findall(r'src="(/_forensic/[^"?]+\.js)"', src))
    paths |= set(re.findall(r'href="(/_forensic/[^"?]+\.css)"', src))
    return sorted(p for p in paths if "/_forensic/static/" not in p)


class TestReportAssetsRouting(_ServerFixture):
    """Jedes von report.py eingebundene Flach-Asset muss HTTP 200 liefern."""

    def test_report_page_assets_are_served(self):
        assets = _included_flat_assets()
        # Sicherstellen, dass ueberhaupt Assets gefunden wurden (sonst waere der
        # Test wertlos gruen).
        self.assertGreater(len(assets), 5,
                           "Keine Asset-Pfade in report.py gefunden — Regex pruefen.")

        failures = []
        for path in assets:
            url = f"{self.base_url}{path}"
            try:
                with urllib.request.urlopen(url, timeout=2.0) as resp:
                    status = resp.status
                    body_len = len(resp.read())
            except urllib.error.HTTPError as exc:
                status = exc.code
                body_len = 0
            except Exception as exc:  # noqa: BLE001 — im Test alles als Fehler werten
                failures.append(f"{path}: Ausnahme {exc!r}")
                continue
            if status != 200:
                failures.append(f"{path}: HTTP {status}")
            elif body_len == 0:
                failures.append(f"{path}: HTTP 200 aber leerer Body")

        self.assertEqual(
            failures, [],
            "Eingebundene, aber nicht (korrekt) ausgelieferte Assets:\n  "
            + "\n  ".join(failures),
        )
