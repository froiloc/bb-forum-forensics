# =============================================================================
# tests/test_view_export_renderer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Testsuite fuer Build 511: ViewExportRenderer (Akten-Export je Sicht).
# REINE Klasse — hier vollstaendig und schnell pruefbar.
#
# VR01 — Grundgeruest: Aktenkopf, Titel, Erzeugungsvermerk, Pruefsumme; die
#        Pruefsumme deckt die NUTZDATEN (unabhaengig nachrechenbar).
# VR02 — REGEL 1: Spalten kommen aus den Daten. Ein Feld, das erst in einer
#        SPAETEREN Zeile auftaucht, bekommt seine Spalte; frueheren Zeilen
#        steht ein Gedankenstrich.
# VR03 — REGEL 1 (Fortsetzung): 'order' zieht nur nach vorn und FILTERT NIE;
#        'labels' beschriftet nur.
# VR04 — REGEL 2: Top-Level-Schluessel ohne Spec erscheinen unter
#        „Weitere Daten"; ohne deklarierte Abschnitte wird alles automatisch
#        gerendert.
# VR05 — REGEL 3: ein in der Antwort FEHLENDER Abschnitt wird ausdruecklich
#        benannt (nicht weggelassen).
# VR06 — REGEL 4: Kappung ist sichtbar und nennt die Gesamtzahl.
# VR07 — Werttypen: None/bool/leerer String/verschachtelte Struktur.
# VR08 — echter Leerbefund (leere Liste / leeres dict) wird als solcher
#        benannt — und ist NICHT dasselbe wie ein fehlender Abschnitt.
# VR09 — XSS: Markup aus den Daten landet als TEXT; query_summary().
#
# Version: v0.8.511 · Build: 511 · 2026-07-24
# =============================================================================

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.export.checksum import json_payload_sha256
from management.export.export_envelope import ExportContext, ExportEnvelope
from management.export.view_export_spec import SectionSpec, ViewExportSpec
from management.export.view_renderer import ViewExportRenderer, query_summary


def _env():
    return ExportEnvelope(ExportContext(
        behoerde="Polizei NRW — EK Zarewitsch",
        aktenzeichen="Testakte",
        ersteller="h001",
        build_number=511,
        generated_at="2026-07-24 20:00 UTC",
        chain_ok=True, chain_tip_seq=42, chain_tip_hash="deadbeef",
        anzeigename="Chefin",
    ))


def _spec(sections=(), note="", label="Testsicht"):
    return ViewExportSpec(view_id="test", label=label,
                          api_path="/api/test", sections=tuple(sections),
                          note=note)


class ViewExportRendererTests(unittest.TestCase):

    # VR01 -------------------------------------------------------------------
    def test_vr01_grundgeruest(self):
        data = {"entries": [{"a": 1}]}
        out = ViewExportRenderer(_spec([SectionSpec("entries", "Einträge")])) \
            .render(data, _env())

        self.assertIn("<!DOCTYPE html>", out)
        self.assertIn("Testsicht", out)
        self.assertIn("VERTRAULICH", out)
        self.assertIn("Polizei NRW", out)
        self.assertIn("Erstellt von: Chefin (h001)", out)
        self.assertIn("Werkzeug-Build: 511", out)
        self.assertIn("Audit-Kette: INTAKT", out)
        # Die Pruefsumme deckt die NUTZDATEN — unabhaengig nachrechenbar.
        self.assertIn(json_payload_sha256(data), out)
        # ... und ausdruecklich NICHT das gerenderte HTML.
        self.assertNotEqual(json_payload_sha256(data),
                            json_payload_sha256({"html": out}))
        # Kein JavaScript im Akten-Export.
        self.assertNotIn("<script", out.lower())

    # VR02 -------------------------------------------------------------------
    def test_vr02_spalten_kommen_aus_den_daten(self):
        """
        Der Kernfall von Regel 1: ein Feld taucht erst in Zeile 3 auf. Eine
        handgepflegte Spaltenliste haette es still verschluckt.
        """
        data = {"rows": [
            {"id": 1, "name": "A"},
            {"id": 2, "name": "B"},
            {"id": 3, "name": "C", "spaetes_feld": "WICHTIG"},
        ]}
        out = ViewExportRenderer(_spec([SectionSpec("rows", "Zeilen")])) \
            .render(data, _env())

        self.assertIn("<th>spaetes_feld</th>", out)
        self.assertIn("WICHTIG", out)
        # Die frueheren Zeilen bekommen eine leere Zelle, keine Verschiebung.
        self.assertEqual(out.count("<tr>"), 4)          # Kopf + 3 Datenzeilen
        self.assertGreaterEqual(out.count("—"), 2)

    # VR03 -------------------------------------------------------------------
    def test_vr03_order_filtert_nie_labels_beschriften_nur(self):
        sec = SectionSpec("rows", "Zeilen",
                          labels={"id": "Kennung"},
                          order=("name", "id"))
        data = {"rows": [{"id": 1, "name": "A", "extra": "bleibt drin"}]}
        out = ViewExportRenderer(_spec([sec])).render(data, _env())

        # Beschriftung greift ...
        self.assertIn("<th>Kennung</th>", out)
        # ... 'order' zieht nach vorn ...
        self.assertLess(out.index("<th>name</th>"), out.index("<th>Kennung</th>"))
        # ... und das NICHT genannte Feld bleibt trotzdem im Dokument.
        self.assertIn("<th>extra</th>", out)
        self.assertIn("bleibt drin", out)

    # VR04 -------------------------------------------------------------------
    def test_vr04_undeklarierte_schluessel_und_automodus(self):
        data = {"rows": [{"id": 1}], "counts": {"total": 1},
                "mode": "all"}
        out = ViewExportRenderer(_spec([SectionSpec("rows", "Zeilen")])) \
            .render(data, _env())
        self.assertIn("Weitere Daten", out)
        self.assertIn("counts", out)
        self.assertIn("mode", out)
        self.assertIn("all", out)

        # OHNE deklarierte Abschnitte wird alles automatisch gerendert.
        out2 = ViewExportRenderer(_spec()).render(data, _env())
        self.assertNotIn("Weitere Daten", out2)   # keine kuenstliche Trennung
        self.assertIn("<h2>rows</h2>", out2)
        self.assertIn("<h2>counts</h2>", out2)
        self.assertIn("<h2>mode</h2>", out2)

    # VR05 -------------------------------------------------------------------
    def test_vr05_fehlender_abschnitt_wird_benannt(self):
        sec = SectionSpec("gibtsnicht", "Fehlender Abschnitt")
        out = ViewExportRenderer(_spec([sec])).render({"rows": []}, _env())
        self.assertIn("Fehlender Abschnitt", out)
        self.assertIn("nicht enthalten", out)
        self.assertIn("aiw-missing", out)

    # VR06 -------------------------------------------------------------------
    def test_vr06_kappung_ist_sichtbar(self):
        data = {"rows": [{"i": n} for n in range(25)]}
        r = ViewExportRenderer(_spec([SectionSpec("rows", "Zeilen")]),
                               max_rows=10)
        out = r.render(data, _env())

        # Auf den VERMERK pruefen, nicht auf den Klassennamen: 'aiw-truncated'
        # steht als CSS-Regel immer im Stylesheet.
        self.assertIn('<p class="aiw-truncated">', out)
        self.assertIn("ACHTUNG", out)
        self.assertIn("ersten 10 von 25", out)
        self.assertIn("15 Einträge fehlen", out)
        # Kopf + 10 Datenzeilen — mehr nicht.
        self.assertEqual(out.count("<tr>"), 11)

        # Unterhalb der Grenze KEIN Vermerk (sonst waere er Rauschen).
        out2 = ViewExportRenderer(_spec([SectionSpec("rows", "Zeilen")]),
                                  max_rows=100).render(data, _env())
        self.assertNotIn('<p class="aiw-truncated">', out2)
        self.assertNotIn("ACHTUNG", out2)
        self.assertEqual(out2.count("<tr>"), 26)     # Kopf + alle 25 Zeilen

    # VR07 -------------------------------------------------------------------
    def test_vr07_werttypen(self):
        c = ViewExportRenderer._cell
        self.assertEqual(c(None), "—")
        self.assertEqual(c(""), "—")
        self.assertEqual(c(True), "ja")
        self.assertEqual(c(False), "nein")
        self.assertEqual(c(0), "0")           # 0 ist ein WERT, kein Leerwert
        self.assertEqual(c(1.5), "1.5")
        self.assertEqual(c("Text"), "Text")
        # Verschachteltes bleibt LESBAR im Dokument, statt zu verschwinden.
        self.assertIn("alt", c({"alt": 1, "neu": 2}))
        self.assertIn("b", c(["a", "b"]))
        # UTF-8 bleibt erhalten (multilinguales Forum).
        self.assertEqual(c("Ярослав"), "Ярослав")
        self.assertIn("Ярослав", c({"n": "Ярослав"}))

    # VR08 -------------------------------------------------------------------
    def test_vr08_leerbefund_ist_nicht_fehlend(self):
        out = ViewExportRenderer(_spec([SectionSpec("rows", "Zeilen"),
                                        SectionSpec("obj", "Objekt")])) \
            .render({"rows": [], "obj": {}}, _env())
        self.assertIn("echter Leerbefund", out)
        self.assertNotIn("nicht enthalten", out)
        # Skalare Werte werden ebenfalls dargestellt.
        out2 = ViewExportRenderer(_spec([SectionSpec("ok", "Status")])) \
            .render({"ok": False}, _env())
        self.assertIn("nein", out2)

    # VR09 -------------------------------------------------------------------
    def test_vr09_xss_und_query_summary(self):
        boese = '<script>alert(1)</script>'
        data = {"rows": [{"alias": boese, "basis": '"><img src=x>'}]}
        out = ViewExportRenderer(_spec([SectionSpec("rows", "Zeilen")])) \
            .render(data, _env(), query_summary=query_summary(
                {"q": [boese], "view": ["alias"]}))

        # Kein rohes Markup im Dokument ...
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertNotIn("<img src=x>", out)
        # ... aber der Inhalt ist als TEXT sichtbar (nichts verschluckt).
        self.assertIn("&lt;script&gt;", out)

        # query_summary: 'view' wird entfernt (es ist Steuerung, kein Filter).
        self.assertEqual(query_summary({"q": ["x"], "view": ["alias"]}),
                         "q=x")
        self.assertEqual(query_summary({}), "keine")
        self.assertEqual(query_summary(None), "keine")
        self.assertEqual(query_summary({"view": ["alias"]}), "keine")
        self.assertEqual(query_summary({"a": ["1", "2"], "b": "3"}),
                         "a=1, 2; b=3")

    # VR10 -------------------------------------------------------------------
    def test_vr10_note_und_parameterzeile_erscheinen(self):
        out = ViewExportRenderer(_spec(note="Sonderhinweis XY")) \
            .render({"a": 1}, _env(), query_summary="start=2026-01-01")
        self.assertIn("Sonderhinweis XY", out)
        self.assertIn("Angewandte Parameter: start=2026-01-01", out)


if __name__ == "__main__":
    unittest.main()
