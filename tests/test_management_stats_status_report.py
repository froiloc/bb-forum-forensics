# =============================================================================
# tests/test_management_stats_status_report.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Testsuite fuer Build 445: StA-Berichtsgenerator (status_report).
#
# SR01 — HTML: Aktenkopf-Band + Titel + alle Abschnitte + Werte
# SR02 — HTML: Pruefsumme = stats_digest(stats), im Fuss, UTF-8 erhalten
# SR03 — HTML: leere Teilmengen zeigen 'keine Daten' (kein stiller Ausfall, GR1)
# SR04 — _sections deckt genau die StatsRepo-Abschnitte (Deckung)
# SR05 — stats_digest deterministisch + aenderungssensitiv
# SR06 — PDF: liefert %PDF-Bytes (reportlab vorhanden) ODER wird uebersprungen
# SR07 — PDF: StatusReportUnavailable, wenn reportlab fehlt (Import-Guard)
# SR08 — HTML: person-Umfang 'eigene' wird ausgewiesen; period_label erscheint
#
# Version: v0.7.445 · Build: 445 · 2026-07-19
# =============================================================================

import builtins
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.stats.status_report import (       # noqa: E402
    build_status_report_html, build_status_report_pdf, stats_digest,
    _sections, StatusReportUnavailable,
)
from management.export.export_envelope import ExportContext  # noqa: E402
from management.export.checksum import json_payload_sha256   # noqa: E402


def _ctx(**over):
    base = dict(
        behoerde="Polizei NRW — EK Zarewitsch", aktenzeichen="StA 123 Js 456",
        ersteller="h012345", build_number=445, generated_at="2026-07-19 12:00 UTC",
        chain_ok=True, chain_tip_seq=7, chain_tip_hash="ab" * 32)
    base.update(over)
    return ExportContext(**base)


def _stats(**over):
    base = {
        "scope": "alle", "generated_at": 1_700_000_000,
        "totals": {"cases": 3, "assigned": 2, "unassigned": 1, "events": 9},
        "by_status": {"open": 1, "in_progress": 1, "approved": 1, "closed": 0},
        "by_priority": {"1": 1, "2": 0, "3": 2, "4": 0, "5": 0},
        "by_ampel": {"rot": 1, "gelb": 1, "gruen": 1},
        "by_assignee": [{"person_id": 1, "display_name": "Müller, A", "count": 2}],
        "throughput_by_day": [{"day": "2026-07-18", "count": 4}],
    }
    base.update(over)
    return base


def test_sr01_html_sections_and_values():
    html = build_status_report_html(_stats(), _ctx())
    assert 'class="aiw-export-band"' in html
    assert "StA-Statusbericht" in html
    for title in ("Gesamtzahlen", "Fälle je Fallstatus", "Fälle je Priorität",
                  "Fälle je Ampel", "Fälle je Ermittler", "Durchsatz je Tag"):
        assert title in html
    assert "Müller, A" in html and "2026-07-18" in html


def test_sr02_html_checksum_and_utf8():
    stats = _stats()
    html = build_status_report_html(stats, _ctx())
    assert stats_digest(stats) in html
    assert stats_digest(stats) == json_payload_sha256(stats)
    assert "Fälle gesamt" in html


def test_sr03_empty_subsets_marked():
    stats = _stats(by_assignee=[], throughput_by_day=[])
    html = build_status_report_html(stats, _ctx())
    assert html.count("keine Daten") >= 2


def test_sr04_sections_cover_stats():
    titles = [t for t, _rows in _sections(_stats())]
    assert titles == ["Gesamtzahlen", "Fälle je Fallstatus", "Fälle je Priorität",
                      "Fälle je Ampel", "Fälle je Ermittler",
                      "Durchsatz je Tag (Fall-Ereignisse)"]


def test_sr05_digest_deterministic_and_sensitive():
    d = stats_digest(_stats())
    assert d == stats_digest(_stats())
    changed = _stats()
    changed["totals"]["cases"] = 99
    assert stats_digest(changed) != d


def test_sr06_pdf_bytes_or_skip():
    reportlab = pytest.importorskip("reportlab")
    data = build_status_report_pdf(_stats(), _ctx(), period_label="KW 29/2026")
    assert isinstance(data, bytes) and data[:5] == b"%PDF-"
    assert len(data) > 800


def test_sr07_pdf_unavailable(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("reportlab"):
            raise ImportError("simuliert fehlend")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(StatusReportUnavailable):
        build_status_report_pdf(_stats(), _ctx())


def test_sr08_scope_and_period():
    html = build_status_report_html(
        _stats(scope="eigene"), _ctx(), period_label="KW 29/2026")
    assert "Eigene Fälle" in html and "KW 29/2026" in html
