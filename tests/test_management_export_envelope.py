# =============================================================================
# tests/test_management_export_envelope.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Testsuite fuer Build 440: checksum + ExportEnvelope (Fundament, rein additiv).
#
# EX01 — content_sha256_bytes deterministisch + gleich hashlib-Referenz
# EX02 — content_sha256_text == content_sha256_bytes(text.encode utf-8)
# EX03 — content_sha256_bytes weist str zurueck (TypeError)
# EX04 — canonical_rows_sha256 deckungsgleich zur Sealer-Kanonik (report_sealer._hash)
# EX05 — canonical_rows_sha256: Zeilenreihenfolge ist signifikant
# EX06 — Erzeugungsvermerk enthaelt Ersteller/Zeit/Build/Ketten-Status
# EX07 — integrity_line: chain_ok None -> "nicht geprueft" (keine stille Luecke, GR1)
# EX08 — integrity_line: chain_ok False -> "GEBROCHEN" mit seq/hash
# EX09 — header_html/footer_html escapen HTML (Injektionsschutz), UTF-8 bleibt
# EX10 — Pruefsumme im Footer deckt den Nutzinhalt, unabhaengig nachrechenbar
# EX11 — anzeigename erscheint neben dem SAMAccountName im Erzeugungsvermerk
#
# Version: v0.7.440 · Build: 440 · 2026-07-19
# =============================================================================

import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.export.checksum import (           # noqa: E402
    content_sha256_bytes,
    content_sha256_text,
    canonical_rows_sha256,
)
from management.export.export_envelope import (     # noqa: E402
    ExportContext,
    ExportEnvelope,
    DEFAULT_KLASSIFIKATION,
)


def _ctx(**over):
    base = dict(
        behoerde="Polizei NRW — EK Zarewitsch",
        aktenzeichen="UID 4711",
        ersteller="h012345",
        build_number=440,
        generated_at="2026-07-19 12:00:00",
        chain_ok=True,
        chain_tip_seq=99,
        chain_tip_hash="ab" * 32,
    )
    base.update(over)
    return ExportContext(**base)


# -- checksum -----------------------------------------------------------------

def test_ex01_bytes_deterministic():
    data = "Grüße aus München — 日本語".encode("utf-8")
    assert content_sha256_bytes(data) == hashlib.sha256(data).hexdigest()
    assert content_sha256_bytes(data) == content_sha256_bytes(data)


def test_ex02_text_equals_bytes():
    text = "Grüße — 中文 — علي"
    assert content_sha256_text(text) == content_sha256_bytes(text.encode("utf-8"))


def test_ex03_bytes_rejects_str():
    with pytest.raises(TypeError):
        content_sha256_bytes("kein bytes")  # type: ignore[arg-type]


def test_ex04_canonical_matches_sealer_recipe():
    # Nachbau der Sealer-Kanonik: table + ":" + "|".join(repr(v)) + "\n"
    tables = [
        ("reports", [1, "Titel", None]),
        ("report_blocks", [10, "text", "Inhalt äöü"]),
    ]
    sha = hashlib.sha256()
    for tbl, vals in tables:
        sha.update((tbl + ":" + "|".join(repr(v) for v in vals) + "\n").encode("utf-8"))
    assert canonical_rows_sha256(tables) == sha.hexdigest()


def test_ex05_canonical_order_significant():
    a = [("t", [1]), ("t", [2])]
    b = [("t", [2]), ("t", [1])]
    assert canonical_rows_sha256(a) != canonical_rows_sha256(b)


# -- ExportEnvelope -----------------------------------------------------------

def test_ex06_erzeugungsvermerk_fields():
    env = ExportEnvelope(_ctx())
    lines = env.erzeugungsvermerk_lines()
    joined = "\n".join(lines)
    assert "h012345" in joined
    assert "2026-07-19 12:00:00" in joined
    assert "440" in joined
    assert "INTAKT" in joined and "seq=99" in joined


def test_ex07_integrity_none_marks_unchecked():
    env = ExportEnvelope(_ctx(chain_ok=None, chain_tip_seq=None, chain_tip_hash=None))
    assert env.integrity_line() == "Audit-Kette: nicht geprueft"


def test_ex08_integrity_broken():
    env = ExportEnvelope(_ctx(chain_ok=False, chain_tip_seq=7, chain_tip_hash="cd" * 32))
    line = env.integrity_line()
    assert "GEBROCHEN" in line and "seq=7" in line and "cd" * 32 in line


def test_ex09_html_escaping_keeps_utf8():
    # Aktenzeichen mit HTML-Injektionsversuch + Nicht-ASCII.
    env = ExportEnvelope(_ctx(aktenzeichen="<script>x</script> — Größe"))
    head = env.header_html("Bericht")
    assert "<script>x" not in head          # roher Tag darf nicht durch
    assert "&lt;script&gt;" in head          # escaped
    assert "Größe" in head                   # UTF-8 erhalten
    foot = env.footer_html("deadbeef")
    assert "deadbeef" in foot


def test_ex10_footer_checksum_covers_payload():
    env = ExportEnvelope(_ctx())
    payload = "<p>Nutzinhalt äöü</p>"
    digest = env.checksum_text(payload)
    # unabhaengig nachrechenbar
    assert digest == hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert digest in env.footer_html(digest)


def test_ex11_display_name_beside_samaccount():
    env = ExportEnvelope(_ctx(anzeigename="Mustermann, Erika"))
    joined = "\n".join(env.erzeugungsvermerk_lines())
    assert "Mustermann, Erika" in joined and "h012345" in joined


def test_ex12_default_klassifikation_present():
    env = ExportEnvelope(_ctx())
    assert DEFAULT_KLASSIFIKATION in env.header_text("Titel")
