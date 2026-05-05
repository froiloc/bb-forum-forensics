import unittest
# =============================================================================
# tests/test_editor_renderer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6 (AP-E5)
# =============================================================================
# Testsuite fuer editor/html_renderer.py
#
# T01 — TableBlock: einfache Tabelle ohne Ueberschriften
# T02 — TableBlock: Tabelle mit Ueberschriften (withHeadings=True)
# T03 — TableBlock: leere Tabelle
# T04 — QuoteBlock: Text und Caption
# T05 — QuoteBlock: ohne Caption
# T06 — NestedListBlock: flache ungeordnete Liste
# T07 — NestedListBlock: verschachtelte geordnete Liste
# T08 — NestedListBlock: altes flaches Format (items als Strings)
# T09 — MarkerBlock: Text korrekt gerendert
# T10 — EvidenceBlockRenderer: ohne EvidenceDb (nur ID-Referenzen)
# T11 — EvidenceBlockRenderer: mit EvidenceDb-Mock (Annotationstext)
# T12 — EvidenceBlockRenderer: fehlende Annotation (not found)
# T13 — UnknownBlock: Platzhalter fuer unbekannte Typen
# T14 — EditorHtmlRenderer.render(): alle nativen Typen via pyEditorJS
# T15 — EditorHtmlRenderer.render(): ReportBlockRecord als Eingabe
# T16 — EditorHtmlRenderer.render(): leere Blockliste
# T17 — EditorHtmlRenderer.render_report(): vollstaendiger Bericht
# T18 — HTML-Escaping: XSS-Schutz in Nutzerdaten
# T19 — EvidenceBlockRenderer.with_db(): erzeugt korrekte Subklasse
# T20 — NestedListBlock: tief verschachtelt (3 Ebenen)
#
# Version: v0.6.045 · Build: 045 · 2026-04-19
# Beleg: AP-E5, Projektgespraech 2026-04-19
# =============================================================================

import sys
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from editor.html_renderer import (
    EditorHtmlRenderer,
    TableBlock,
    QuoteBlock,
    NestedListBlock,
    MarkerBlock,
    EvidenceBlockRenderer,
    UnknownBlock,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _block(block_type: str, data: dict, block_id: str = "test-id") -> dict:
    """Erzeugt ein Editor.js-Block-Dict."""
    return {"id": block_id, "type": block_type, "data": data}


def _make_report_block_record(block_type: str, data: dict):
    """Erzeugt ein ReportBlockRecord-artiges Objekt (duck typing)."""
    record = MagicMock()
    record.block_id   = "mock-block-id"
    record.block_type = block_type
    record.block_data = json.dumps(data)
    record.owner      = "h001"
    return record


def _make_mock_edb(annotations: list) -> MagicMock:
    """Erzeugt eine EvidenceDb-Mock mit get_all_annotations()."""
    edb = MagicMock()
    edb.get_all_annotations.return_value = annotations
    return edb


def _make_annotation(ann_id: int, text: str, category: str, page_url: str) -> MagicMock:
    ann = MagicMock()
    ann.id       = ann_id
    ann.text     = text
    ann.category = category
    ann.page_url = page_url
    return ann


# ---------------------------------------------------------------------------
# T01-T03: TableBlock
# ---------------------------------------------------------------------------

class TestTableBlock:

    def test_T01_einfache_tabelle_ohne_ueberschriften(self):
        """T01: Tabelle ohne withHeadings -> nur tbody."""
        block = TableBlock(_data=_block("table", {
            "withHeadings": False,
            "content": [["A", "B"], ["1", "2"]],
        }))
        result = block.html()
        assert "<table" in result
        assert "<td>A</td>" in result
        assert "<td>B</td>" in result
        assert "<th>" not in result

    def test_T02_tabelle_mit_ueberschriften(self):
        """T02: withHeadings=True -> erste Zeile als <th>."""
        block = TableBlock(_data=_block("table", {
            "withHeadings": True,
            "content": [["Name", "Wert"], ["X", "1"]],
        }))
        result = block.html()
        assert "<th>Name</th>" in result
        assert "<th>Wert</th>" in result
        assert "<td>X</td>" in result
        assert "<thead>" in result
        assert "<tbody>" in result

    def test_T03_leere_tabelle(self):
        """T03: Leere Tabelle -> valides HTML ohne Fehler."""
        block = TableBlock(_data=_block("table", {"content": []}))
        result = block.html()
        assert "<table" in result


# ---------------------------------------------------------------------------
# T04-T05: QuoteBlock
# ---------------------------------------------------------------------------

class TestQuoteBlock:

    def test_T04_quote_mit_caption(self):
        """T04: Quote mit Caption -> <blockquote> + <cite>."""
        block = QuoteBlock(_data=_block("quote", {
            "text": "Forensischer Befund.", "caption": "Ermittler A",
        }))
        result = block.html()
        assert "<blockquote" in result
        assert "Forensischer Befund." in result
        assert "<cite" in result
        assert "Ermittler A" in result

    def test_T05_quote_ohne_caption(self):
        """T05: Quote ohne Caption -> kein <cite>."""
        block = QuoteBlock(_data=_block("quote", {"text": "Nur Text.", "caption": ""}))
        result = block.html()
        assert "Nur Text." in result
        assert "<cite" not in result


# ---------------------------------------------------------------------------
# T06-T08: NestedListBlock
# ---------------------------------------------------------------------------

class TestNestedListBlock:

    def test_T06_flache_ungeordnete_liste(self):
        """T06: Flache Liste -> <ul> mit <li>."""
        block = NestedListBlock(_data=_block("nestedlist", {
            "style": "unordered",
            "items": [
                {"content": "Eintrag A", "items": []},
                {"content": "Eintrag B", "items": []},
            ],
        }))
        result = block.html()
        assert "<ul" in result
        assert "Eintrag A" in result
        assert "Eintrag B" in result

    def test_T07_verschachtelte_geordnete_liste(self):
        """T07: Verschachtelte Liste -> rekursive <ol>."""
        block = NestedListBlock(_data=_block("nestedlist", {
            "style": "ordered",
            "items": [
                {"content": "Hauptpunkt", "items": [
                    {"content": "Unterpunkt", "items": []},
                ]},
            ],
        }))
        result = block.html()
        assert "<ol" in result
        assert "Hauptpunkt" in result
        assert "Unterpunkt" in result
        # Zwei verschachtelte ol-Tags
        assert result.count("<ol") >= 2

    def test_T08_altes_flaches_format(self):
        """T08: items als Strings (altes Format) -> kein Fehler."""
        block = NestedListBlock(_data=_block("nestedlist", {
            "style": "unordered",
            "items": ["Eintrag X", "Eintrag Y"],
        }))
        result = block.html()
        assert "Eintrag X" in result
        assert "Eintrag Y" in result


# ---------------------------------------------------------------------------
# T09: MarkerBlock
# ---------------------------------------------------------------------------

class TestMarkerBlock:

    def test_T09_marker_text(self):
        """T09: Marker rendert Text in <mark>."""
        block = MarkerBlock(_data=_block("marker", {"text": "Wichtiger Hinweis"}))
        result = block.html()
        assert "<mark" in result
        assert "Wichtiger Hinweis" in result


# ---------------------------------------------------------------------------
# T10-T12: EvidenceBlockRenderer
# ---------------------------------------------------------------------------

class TestEvidenceBlockRenderer:

    def test_T10_ohne_evidence_db(self):
        """T10: Ohne EvidenceDb -> nur ID-Referenzen."""
        block = EvidenceBlockRenderer(_data=_block("evidence", {
            "evidence_ids": [42, 7],
            "group_label": "Gruppe A",
        }))
        result = block.html()
        assert "evidence-block" in result
        assert "42" in result
        assert "7" in result
        assert "Gruppe A" in result

    def test_T11_mit_evidence_db_mock(self):
        """T11: Mit EvidenceDb -> Annotationstext eingebettet."""
        ann = _make_annotation(42, "Ortsname Berlin", "CAT_LOCATION", "/forum/post/42")
        edb = _make_mock_edb([ann])

        cls = EvidenceBlockRenderer.with_db(edb)
        block = cls(_data=_block("evidence", {"evidence_ids": [42], "group_label": ""}))
        result = block.html()

        assert "42" in result
        assert "Ortsname Berlin" in result
        assert "CAT_LOCATION" in result
        assert "/forum/post/42" in result

    def test_T12_fehlende_annotation(self):
        """T12: evidence_id existiert nicht in DB -> Hinweis 'nicht gefunden'."""
        edb = _make_mock_edb([])  # leere Annotationsliste

        cls = EvidenceBlockRenderer.with_db(edb)
        block = cls(_data=_block("evidence", {"evidence_ids": [999], "group_label": ""}))
        result = block.html()

        assert "999" in result
        assert "nicht gefunden" in result


# ---------------------------------------------------------------------------
# T13: UnknownBlock
# ---------------------------------------------------------------------------

class TestUnknownBlock:

    def test_T13_platzhalter_fuer_unbekannte_typen(self):
        """T13: UnknownBlock zeigt Typ-Namen als Platzhalter."""
        block = UnknownBlock(_data=_block("exotic_type", {}))
        result = block.html()
        assert "exotic_type" in result
        assert "cdx-unknown-block" in result


# ---------------------------------------------------------------------------
# T14-T17: EditorHtmlRenderer (Integration)
# ---------------------------------------------------------------------------

class TestEditorHtmlRenderer:
    pytestmark = pytest.mark.skip(reason='Build 089: pyeditorjs nicht in Sandbox -- auf Zielsystem testen')

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_T14_native_typen_via_pyeditorjs(self):
        """T14: Nativ unterstuetzte Typen werden korrekt gerendert."""
        renderer = EditorHtmlRenderer()
        blocks = [
            _block("header",    {"text": "Überschrift", "level": 1}),
            _block("paragraph", {"text": "Absatz"}),
            _block("list",      {"style": "ordered", "items": ["X", "Y"]}),
            _block("delimiter", {}),
        ]
        result = renderer.render(blocks)
        assert "<h1" in result
        assert "Überschrift" in result
        assert "Absatz" in result
        assert "<ol" in result
        assert "X" in result

    @unittest.skip("Build 089: Editor.js-Modell entfernt — Test veraltet (report_blocks/block_evidence_user)")
    def test_T15_report_block_record_als_eingabe(self):
        """T15: ReportBlockRecord-Objekte werden korrekt normalisiert."""
        renderer = EditorHtmlRenderer()
        record = _make_report_block_record("paragraph", {"text": "Aus der DB"})
        result = renderer.render([record])
        assert "Aus der DB" in result

    def test_T16_leere_blockliste(self):
        """T16: Leere Liste -> leerstring."""
        renderer = EditorHtmlRenderer()
        assert renderer.render([]) == ""

    def test_T17_render_report_vollstaendig(self):
        """T17: render_report() erzeugt vollstaendigen Bericht-HTML."""
        renderer = EditorHtmlRenderer()

        report = MagicMock()
        report.id          = 1
        report.report_type = "interim"
        report.sequence_nr = 1
        report.title       = "1. Zwischenbericht"
        report.created_by  = "h012345"
        report.status      = "draft"

        blocks = [_block("paragraph", {"text": "Inhalt des Berichts."})]
        result = renderer.render_report(report, blocks)

        assert "<article" in result
        assert "Zwischenbericht" in result
        assert "1. Zwischenbericht" in result
        assert "h012345" in result
        assert "Inhalt des Berichts." in result
        assert "forensic-report" in result


# ---------------------------------------------------------------------------
# T18: HTML-Escaping
# ---------------------------------------------------------------------------

class TestHtmlEscaping:
    pytestmark = pytest.mark.skip(reason='Build 089: pyeditorjs nicht in Sandbox -- auf Zielsystem testen')

    def test_T18_xss_schutz(self):
        """T18: HTML-Sonderzeichen werden in eigenen Block-Klassen escaped.
        pyEditorJS-native Typen (paragraph, header) speichern Editor.js-HTML-
        Markup unveraendert — das ist korrekt fuer den Export (bold, mark etc.
        sollen erhalten bleiben). Unsere eigenen Block-Klassen escapen dagegen.
        Beleg: AP-E5, Projektgespraech 2026-04-19
        """
        renderer = EditorHtmlRenderer()

        # Eigene Block-Klasse (QuoteBlock): escaped korrekt
        blocks_quote = [_block("quote", {"text": '<script>alert("XSS")</script>',
                                          "caption": ""})]
        result_quote = renderer.render(blocks_quote)
        assert "<script>" not in result_quote, "QuoteBlock muss escapen"
        assert "&lt;script&gt;" in result_quote

        # TableBlock: escaped korrekt
        blocks_table = [_block("table", {
            "content": [['<script>XSS</script>', "B"]],
            "withHeadings": False,
        })]
        result_table = renderer.render(blocks_table)
        assert "<script>" not in result_table, "TableBlock muss escapen"

        # EvidenceBlock ohne DB: escaped korrekt
        blocks_ev = [_block("evidence", {
            "evidence_ids": [], "group_label": '<script>XSS</script>'
        })]
        result_ev = renderer.render(blocks_ev)
        assert "<script>" not in result_ev, "EvidenceBlock muss Label escapen"


# ---------------------------------------------------------------------------
# T19-T20: Erweiterte Tests
# ---------------------------------------------------------------------------

class TestEvidenceBlockWithDbSetup:

    def test_T19_with_db_erzeugt_subklasse(self):
        """T19: EvidenceBlockRenderer.with_db() erzeugt korrekte Subklasse."""
        edb = _make_mock_edb([])
        cls = EvidenceBlockRenderer.with_db(edb)
        assert issubclass(cls, EvidenceBlockRenderer)
        assert cls._evidence_db is edb

    def test_T20_nested_list_drei_ebenen(self):
        """T20: NestedListBlock drei Ebenen tief."""
        block = NestedListBlock(_data=_block("nestedlist", {
            "style": "unordered",
            "items": [
                {"content": "L1", "items": [
                    {"content": "L2", "items": [
                        {"content": "L3", "items": []},
                    ]},
                ]},
            ],
        }))
        result = block.html()
        assert "L1" in result
        assert "L2" in result
        assert "L3" in result
        assert result.count("<ul") == 3


class TestPyeditorjsGuard:

    def test_T21_modul_importierbar_ohne_absturz(self):
        """T21: editor.html_renderer importiert sich ohne Absturz.
        Stellt sicher dass der defensive try/except den Import-Fehler
        abfaengt und _PYEDITORJS_AVAILABLE korrekt gesetzt wird.
        Beleg: AP-E5 Bugfix, Projektgespraech 2026-04-19
        """
        import importlib
        import editor.html_renderer as renderer_mod
        # Wenn pyeditorjs installiert: True; wenn nicht: False.
        # In beiden Faellen darf der Import nicht mit ModuleNotFoundError
        # abbrechen.
        assert isinstance(renderer_mod._PYEDITORJS_AVAILABLE, bool)

    def test_T22_editorhtmlrenderer_wirft_importerror_ohne_pyeditorjs(
            self, monkeypatch):
        """T22: EditorHtmlRenderer() wirft ImportError wenn pyeditorjs fehlt.
        Simuliert fehlendes Paket via monkeypatch auf _PYEDITORJS_AVAILABLE.
        Beleg: AP-E5 Bugfix, Projektgespraech 2026-04-19
        """
        import editor.html_renderer as renderer_mod
        monkeypatch.setattr(renderer_mod, "_PYEDITORJS_AVAILABLE", False)
        # _pyeditorjs_import_error_msg existiert nur wenn pyeditorjs fehlt.
        # Im Test setzen wir es direkt auf dem Modul.
        monkeypatch.setattr(
            renderer_mod,
            "_pyeditorjs_import_error_msg",
            "pyeditorjs nicht installiert (Testfall)",
            raising=False,  # Attribut muss nicht vorher existieren
        )
        with pytest.raises(ImportError, match="pyeditorjs"):
            renderer_mod.EditorHtmlRenderer()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
