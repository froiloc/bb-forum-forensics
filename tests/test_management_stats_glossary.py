# =============================================================================
# tests/test_management_stats_glossary.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Testsuite fuer Build 444: Kennzahlen-Glossar (KpiGlossary).
#
# GL01 — verify_covers_stats OK auf dem Auslieferungs-Katalog
# GL02 — jede StatsRepo-Sektion + Status/Ampel-Wert hat eine Definition
# GL03 — fehlende Definition -> GlossaryIncompleteError (Luecke benannt)
# GL04 — Waisen-Schluessel (ohne Bezug) -> GlossaryIncompleteError
# GL05 — get/keys/all konsistent; doppelter Schluessel -> GlossaryError
# GL06 — Zweckbindungs-Hinweis an by_assignee und throughput_by_day
# GL07 — to_html: Aktenkopf-Band + Definitionen + Pruefsumme, HTML-escaped/UTF-8
# GL08 — Glossar-Vokabular deckt sich mit stats_repo (_STATUSES/_PRIORITIES)
#
# Version: v0.7.444 · Build: 444 · 2026-07-19
# =============================================================================

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.stats.glossary import (           # noqa: E402
    KpiGlossary, KpiDefinition, GlossaryError, GlossaryIncompleteError,
    STATS_SECTIONS, AMPEL_VALUES,
)
from management.stats.stats_repo import _STATUSES, _PRIORITIES  # noqa: E402
from management.export.export_envelope import ExportContext  # noqa: E402
from management.export.checksum import json_payload_sha256    # noqa: E402


def _ctx():
    return ExportContext(
        behoerde="Polizei NRW", aktenzeichen="Kennzahlen-Glossar",
        ersteller="h012345", build_number=444, generated_at="2026-07-19 12:00 UTC",
        chain_ok=True, chain_tip_seq=1, chain_tip_hash="ab" * 32)


def test_gl01_covers_stats_ok():
    KpiGlossary().verify_covers_stats()  # darf nicht werfen


def test_gl02_every_section_and_value_defined():
    g = KpiGlossary()
    keys = set(g.keys())
    for s in STATS_SECTIONS:
        assert s in keys
    for s in _STATUSES:
        assert "status.%s" % s in keys
    for a in AMPEL_VALUES:
        assert "ampel.%s" % a in keys


def test_gl03_missing_definition_raises():
    # Katalog ohne 'by_ampel' -> Luecke
    reduced = tuple(e for e in KpiGlossary().all() if e.key != "by_ampel")
    g = KpiGlossary(reduced)
    with pytest.raises(GlossaryIncompleteError) as ei:
        g.verify_covers_stats()
    assert "by_ampel" in str(ei.value)


def test_gl04_orphan_key_raises():
    extra = KpiGlossary().all() + [
        KpiDefinition("erfundene.kennzahl", "X", "d", "q", "e")]
    g = KpiGlossary(tuple(extra))
    with pytest.raises(GlossaryIncompleteError) as ei:
        g.verify_covers_stats()
    assert "erfundene.kennzahl" in str(ei.value)


def test_gl05_lookup_and_duplicate():
    g = KpiGlossary()
    assert g.get("totals.cases").label == "Fälle gesamt"
    assert g.get("nichtvorhanden") is None
    assert len(g.all()) == len(g.keys())
    dup = KpiGlossary().all()[:1] * 2
    with pytest.raises(GlossaryError):
        KpiGlossary(tuple(dup))


def test_gl06_zweckbindung_on_personal_metrics():
    g = KpiGlossary()
    assert "Bewertungsinstrument" in g.get("by_assignee").hinweis
    assert "Bewertungsinstrument" in g.get("throughput_by_day").hinweis


def test_gl07_to_html_frame_and_checksum():
    g = KpiGlossary()
    html = g.to_html(_ctx())
    assert 'class="aiw-export-band"' in html
    assert "Kennzahlen-Glossar" in html
    assert "Fälle gesamt" in html                    # UTF-8 erhalten
    # Pruefsumme deckt die Definitionsliste, unabhaengig nachrechenbar
    payload = [{"key": e.key, "label": e.label, "definition": e.definition,
                "quelle": e.quelle, "einheit": e.einheit, "hinweis": e.hinweis}
               for e in g.all()]
    assert json_payload_sha256(payload) in html


def test_gl08_vocab_matches_stats():
    # Alle Status-Werte aus stats_repo sind definiert; Prioritaets-Skala 1..5.
    g = KpiGlossary()
    for s in _STATUSES:
        assert g.get("status.%s" % s) is not None
    assert set(_PRIORITIES) == {"1", "2", "3", "4", "5"}
    assert g.get("priority.1") is not None and g.get("priority.5") is not None
