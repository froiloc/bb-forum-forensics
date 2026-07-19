# =============================================================================
# tests/test_management_export_staging.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Testsuite fuer Build 443: StA-Ausschleus-Verzeichnis (StagingArea).
#
# ST01 — add ohne unbedenklich -> UnbedenklichkeitError; Datei NICHT aufgenommen
# ST02 — add mit unbedenklich kopiert Datei + Manifest-Eintrag (sha256=Dateihash, size)
# ST03 — manifest_sha256 = json_payload_sha256(artifacts), aenderungssensitiv
# ST04 — Zustand ueberlebt neue StagingArea-Instanz (inkrementell, mehrere adds)
# ST05 — finalize stempelt Kopfdaten + Erzeugungsvermerk + schreibt UEBERGABE.txt
# ST06 — verify OK auf intaktem Paket; erkennt veraenderte Datei (mismatched)
# ST07 — verify erkennt fehlende Datei (missing) und Zusatzdatei (extra)
# ST08 — cleared_by leer -> UnbedenklichkeitError (kein Pruefer)
# ST09 — UTF-8 in note/source_ref bleibt erhalten
# ST10 — Namenskollision -> StagingError (kein stilles Ueberschreiben, GR1)
#
# Version: v0.7.443 · Build: 443 · 2026-07-19
# =============================================================================

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.export.staging import (           # noqa: E402
    StagingArea, StagingError, UnbedenklichkeitError, MANIFEST_NAME, OVERVIEW_NAME,
)
from management.export.export_envelope import ExportContext  # noqa: E402
from management.export.checksum import (           # noqa: E402
    json_payload_sha256, content_sha256_bytes,
)


def _mkfile(d, name, content=b"PDF-BYTES-\xc3\xa4\xc3\xb6"):
    p = os.path.join(str(d), name)
    with open(p, "wb") as fh:
        fh.write(content)
    return p


def _ctx(**over):
    base = dict(
        behoerde="Polizei NRW — EK Zarewitsch", aktenzeichen="StA 123 Js 456",
        ersteller="h012345", build_number=443, generated_at="2026-07-19 12:00 UTC",
        chain_ok=True, chain_tip_seq=9, chain_tip_hash="ab" * 32,
    )
    base.update(over)
    return ExportContext(**base)


def test_st01_refuse_without_unbedenklich(tmp_path):
    area = StagingArea(str(tmp_path / "out"))
    src = _mkfile(tmp_path, "bericht.pdf")
    with pytest.raises(UnbedenklichkeitError):
        area.add_artifact(src, kind="report_pdf", source_ref="uid=4711",
                          unbedenklich=False, cleared_by="h012345",
                          added_at="2026-07-19 12:00 UTC")
    # Datei NICHT aufgenommen
    assert not (tmp_path / "out" / "bericht.pdf").exists()
    assert area.load()["artifacts"] == []


def test_st02_add_copies_and_records(tmp_path):
    area = StagingArea(str(tmp_path / "out"))
    content = b"REPORT-\xc3\xa4"
    src = _mkfile(tmp_path, "bericht.pdf", content)
    entry = area.add_artifact(src, kind="report_pdf", source_ref="uid=4711",
                              unbedenklich=True, cleared_by="h012345",
                              added_at="2026-07-19 12:00 UTC", note="ok")
    assert (tmp_path / "out" / "bericht.pdf").exists()
    assert entry["sha256"] == content_sha256_bytes(content)
    assert entry["size"] == len(content)
    assert entry["unbedenklich"] is True and entry["cleared_by"] == "h012345"


def test_st03_manifest_digest(tmp_path):
    area = StagingArea(str(tmp_path / "out"))
    src = _mkfile(tmp_path, "a.pdf")
    area.add_artifact(src, kind="k", source_ref="s", unbedenklich=True,
                      cleared_by="h1", added_at="t")
    m = area.load()
    assert m["manifest_sha256"] == json_payload_sha256(m["artifacts"])
    d1 = m["manifest_sha256"]
    area.add_artifact(_mkfile(tmp_path, "b.pdf"), kind="k", source_ref="s",
                      unbedenklich=True, cleared_by="h1", added_at="t")
    assert area.load()["manifest_sha256"] != d1


def test_st04_state_survives_new_instance(tmp_path):
    d = str(tmp_path / "out")
    StagingArea(d).add_artifact(_mkfile(tmp_path, "a.pdf"), kind="k",
                                source_ref="s", unbedenklich=True,
                                cleared_by="h1", added_at="t")
    # neue Instanz liest den Bestand
    area2 = StagingArea(d)
    area2.add_artifact(_mkfile(tmp_path, "b.pdf"), kind="k", source_ref="s",
                       unbedenklich=True, cleared_by="h1", added_at="t")
    assert {a["filename"] for a in area2.load()["artifacts"]} == {"a.pdf", "b.pdf"}


def test_st05_finalize_stamps_and_overview(tmp_path):
    d = tmp_path / "out"
    area = StagingArea(str(d))
    area.add_artifact(_mkfile(tmp_path, "a.pdf"), kind="report_pdf",
                      source_ref="uid=4711", unbedenklich=True,
                      cleared_by="h012345", added_at="t")
    area.finalize(_ctx())
    m = area.load()
    assert m["behoerde"] == "Polizei NRW — EK Zarewitsch"
    assert m["aktenzeichen"] == "StA 123 Js 456"
    assert any("Werkzeug-Build: 443" in line for line in m["erzeugungsvermerk"])
    text = (d / OVERVIEW_NAME).read_text(encoding="utf-8")
    assert "StA-Ausschleus" in text and "a.pdf" in text
    assert m["manifest_sha256"] in text            # Manifest-Digest im Fuss


def test_st06_verify_ok_and_tamper(tmp_path):
    d = tmp_path / "out"
    area = StagingArea(str(d))
    area.add_artifact(_mkfile(tmp_path, "a.pdf", b"ORIG"), kind="k",
                      source_ref="s", unbedenklich=True, cleared_by="h1",
                      added_at="t")
    assert area.verify()["ok"] is True
    # Manipulation der ausgeschleusten Datei
    (d / "a.pdf").write_bytes(b"TAMPERED")
    res = area.verify()
    assert res["ok"] is False and res["mismatched"] == ["a.pdf"]


def test_st07_verify_missing_and_extra(tmp_path):
    d = tmp_path / "out"
    area = StagingArea(str(d))
    area.add_artifact(_mkfile(tmp_path, "a.pdf"), kind="k", source_ref="s",
                      unbedenklich=True, cleared_by="h1", added_at="t")
    os.remove(str(d / "a.pdf"))                    # fehlend
    (d / "fremd.txt").write_text("x", encoding="utf-8")  # zusaetzlich
    res = area.verify()
    assert res["missing"] == ["a.pdf"] and res["extra"] == ["fremd.txt"]
    assert res["ok"] is False


def test_st08_cleared_by_required(tmp_path):
    area = StagingArea(str(tmp_path / "out"))
    with pytest.raises(UnbedenklichkeitError):
        area.add_artifact(_mkfile(tmp_path, "a.pdf"), kind="k", source_ref="s",
                          unbedenklich=True, cleared_by="   ", added_at="t")


def test_st09_utf8_preserved(tmp_path):
    area = StagingArea(str(tmp_path / "out"))
    area.add_artifact(_mkfile(tmp_path, "a.pdf"), kind="k",
                      source_ref="Fall Größe/中文", unbedenklich=True,
                      cleared_by="h1", added_at="t", note="geprüft ✓")
    raw = area.manifest_path.read_text(encoding="utf-8")
    assert "中文" in raw and "geprüft" in raw


def test_st10_duplicate_name_refused(tmp_path):
    area = StagingArea(str(tmp_path / "out"))
    area.add_artifact(_mkfile(tmp_path, "a.pdf"), kind="k", source_ref="s",
                      unbedenklich=True, cleared_by="h1", added_at="t")
    with pytest.raises(StagingError):
        area.add_artifact(_mkfile(tmp_path, "a.pdf"), kind="k", source_ref="s",
                          unbedenklich=True, cleared_by="h1", added_at="t")
