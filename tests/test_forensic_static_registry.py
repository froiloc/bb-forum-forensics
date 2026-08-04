# =============================================================================
# tests/test_forensic_static_registry.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2
# =============================================================================
# Prueft die Ressourcen-Registry in forensic_api/static.py auf VORHANDENSEIN.
#
# ANLASS (Build 663, Ticket d3f933cd): mit cockpit_datumspaar.js liefert der
# Ermittler-Webserver erstmals eine Datei aus dem MANAGEMENT-Baum aus. Das ist
# richtig — zwei Abschriften desselben Verhaltens laufen auseinander —, schafft
# aber eine Abhaengigkeit ueber Verzeichnisgrenzen hinweg.
#
# WARUM DAS EINEN TEST BRAUCHT: static.py antwortet auf eine FEHLENDE .js-Datei
# mit einem LEEREN PLATZHALTER und HTTP 200, damit der Browser nicht blockiert.
# Das ist fuer den Betrieb richtig und fuer die Auslieferung gefaehrlich: ein
# Umbenennen oder Verschieben faellt niemandem auf, denn es gibt keinen Fehler
# zu sehen — nur eine Funktion, die stillschweigend nicht mehr da ist. Genau
# das verbietet Grundregel 1.
#
# FS01 — jeder Registry-Eintrag zeigt auf eine vorhandene Datei.
# FS02 — der gemeinsame Datumspaar-Baustein ist ueber die Route erreichbar UND
#        ist dieselbe Datei, die das Cockpit einbindet (eine Quelle, nicht zwei).
#
# Version: v0.8.663 · Build: 663 · 2026-08-04
# =============================================================================

import unittest
from pathlib import Path

from forensic_api.static import _RESOURCES, _MGMT_STATIC_DIR


class ForensicStaticRegistryTests(unittest.TestCase):

    # FS01 -------------------------------------------------------------------
    def test_fs01_alle_registrierten_dateien_existieren(self):
        fehlend = []
        for route, (dateiname, _mime, verzeichnis) in _RESOURCES.items():
            pfad = Path(verzeichnis) / dateiname
            if not pfad.is_file():
                fehlend.append("%s -> %s" % (route, pfad))
        self.assertEqual(
            [], fehlend,
            "Registrierte Ressourcen ohne Datei (der Server antwortet darauf "
            "mit einem leeren Platzhalter und HTTP 200 — der Ausfall waere "
            "also unsichtbar): %s" % "; ".join(fehlend))

    # FS02 -------------------------------------------------------------------
    def test_fs02_datumspaar_ist_eine_einzige_quelle(self):
        route = "/_forensic/cockpit_datumspaar.js"
        self.assertIn(route, _RESOURCES,
                      "Die Route fuer den gemeinsamen Datumspaar-Baustein "
                      "fehlt; die Annotationsrecherche laedt sie.")
        dateiname, mime, verzeichnis = _RESOURCES[route]
        self.assertEqual("cockpit_datumspaar.js", dateiname)
        self.assertIn("javascript", mime)

        aus_registry = (Path(verzeichnis) / dateiname).resolve()
        # Derselbe Pfad, den cockpit.html ueber /static/ einbindet. Waeren es
        # zwei Dateien, verhielte sich dieselbe Bedienung an zwei Stellen
        # verschieden — und nur eine der beiden wuerde je gepflegt.
        im_cockpit = (Path(__file__).resolve().parent.parent
                      / "management" / "server" / "static"
                      / "cockpit_datumspaar.js").resolve()
        self.assertEqual(im_cockpit, aus_registry)
        self.assertTrue(aus_registry.is_file())
        self.assertEqual(Path(_MGMT_STATIC_DIR).resolve(),
                         aus_registry.parent)


if __name__ == "__main__":
    unittest.main()
