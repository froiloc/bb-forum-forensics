# =============================================================================
# tests/test_management_export_retrofit.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Testsuite fuer Build 442: Retrofit der Sichten-Exporte auf den einheitlichen
# Rahmen (Aktenkopf-Band + Erzeugungsvermerk + Pruefsumme) via optionalem
# ExportEnvelope. Sicherstellen, dass OHNE envelope alles unveraendert bleibt
# (Rueckwaertskompatibilitaet) und MIT envelope Kopf/Fuss/Pruefsumme erscheinen.
#
# RF01 — dashboard: ohne envelope KEIN Band/Erzeugungsvermerk (unveraendert)
# RF02 — dashboard: mit envelope Band + Erzeugungsvermerk + korrekte Pruefsumme
# RF03 — workload: mit envelope Band + Pruefsumme ueber records
# RF04 — support_overview: mit envelope Band + Pruefsumme ueber records
# RF05 — Pruefsumme ist json_payload_sha256 der eingebetteten Daten (nachrechenbar)
# RF06 — build_export_context wirft nie (fehlendes audit_log -> chain None)
# RF07 — build_export_context: --actor-Fallback bei nicht aufloesbarer Identitaet
# RF08 — classification_band_html escaped HTML, UTF-8 bleibt
# RF09 — json_payload_sha256 deterministisch + aenderungssensitiv
# RF10 — dashboard mit envelope: '</script>'-Zaehlung unveraendert (2), Band kein Script
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import hashlib
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.dashboard.html_export import build_dashboard_html        # noqa: E402
from management.workload.html_export import build_workload_html          # noqa: E402
from management.support_overview.html_export import build_support_overview_html  # noqa: E402
from management.export.export_envelope import ExportContext, ExportEnvelope  # noqa: E402
from management.export.checksum import json_payload_sha256               # noqa: E402
from management.export.context_builder import build_export_context       # noqa: E402


def _env(**over):
    base = dict(
        behoerde="Polizei NRW — EK Zarewitsch", aktenzeichen="Gesamtuebersicht",
        ersteller="h012345", build_number=442, generated_at="2026-07-19 12:00 UTC",
        chain_ok=True, chain_tip_seq=5, chain_tip_hash="ab" * 32,
    )
    base.update(over)
    return ExportEnvelope(ExportContext(**base))


_ROWS = [{"subject_id": 4201, "username": "täter_süd", "ampel": "rot"}]


def test_rf01_dashboard_without_envelope_unchanged():
    html = build_dashboard_html(_ROWS, "CSS", "JS")
    assert "aiw-export-band" not in html
    assert "Erzeugungsvermerk" not in html
    assert "Prüfsumme" not in html


def test_rf02_dashboard_with_envelope():
    html = build_dashboard_html(_ROWS, "CSS", "JS", envelope=_env())
    assert 'class="aiw-export-band"' in html
    assert "EK Zarewitsch" in html
    assert "Werkzeug-Build: 442" in html
    assert json_payload_sha256(_ROWS) in html


def test_rf03_workload_with_envelope():
    recs = [{"investigator": "h1", "total": 3}]
    html = build_workload_html(recs, "CSS", "JS", envelope=_env())
    assert 'class="aiw-export-band"' in html
    assert json_payload_sha256(recs) in html


def test_rf04_support_with_envelope():
    recs = [{"session_id": 1, "subject_id": 4201}]
    html = build_support_overview_html(recs, "CSS", "JS", envelope=_env())
    assert 'class="aiw-export-band"' in html
    assert json_payload_sha256(recs) in html


def test_rf05_checksum_independently_recomputable():
    digest = json_payload_sha256(_ROWS)
    canonical = json.dumps(_ROWS, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    assert digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _mk_min_coordinator(path, with_audit=True):
    con = sqlite3.connect(path)
    con.executescript("PRAGMA journal_mode=delete;")
    if with_audit:
        con.execute("CREATE TABLE audit_log(seq INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "ts INTEGER, actor_id INTEGER, event_type TEXT, target_type TEXT,"
                    "target_id TEXT, content TEXT, meta TEXT, prev_hash TEXT, row_hash TEXT)")
    con.commit()
    return con


def test_rf06_context_builder_never_raises_missing_audit(tmp_path):
    db = str(tmp_path / "c.db")
    con = _mk_min_coordinator(db, with_audit=False)  # KEIN audit_log
    try:
        ctx = build_export_context(con=con, db_path=db, actor="h9",
                                   now_utc="2026-07-19 12:00 UTC")
    finally:
        con.close()
    assert ctx.chain_ok is None            # nicht pruefbar -> ehrlich None
    assert ctx.ersteller == "h9"           # Fallback auf --actor
    assert "nicht geprueft" in ExportEnvelope(ctx).integrity_line()


def test_rf07_context_builder_actor_fallback(tmp_path):
    db = str(tmp_path / "c.db")
    con = _mk_min_coordinator(db, with_audit=True)  # audit_log leer -> tip Genesis
    try:
        ctx = build_export_context(con=con, db_path=db, actor="hXYZ",
                                   now_utc="2026-07-19 12:00 UTC")
    finally:
        con.close()
    # Identitaet nicht aufloesbar (kein person-Schema) -> Rohwert --actor
    assert ctx.ersteller == "hXYZ"
    assert ctx.anzeigename is None


def test_rf08_band_escapes_and_keeps_utf8():
    env = _env(aktenzeichen="<b>Größe</b>")
    band = env.classification_band_html()
    assert "<b>Größe" not in band
    assert "&lt;b&gt;Größe" in band


def test_rf09_json_digest_deterministic_and_sensitive():
    a = json_payload_sha256(_ROWS)
    assert a == json_payload_sha256([dict(_ROWS[0])])
    changed = [{"subject_id": 4201, "username": "täter_süd", "ampel": "gelb"}]
    assert json_payload_sha256(changed) != a


def test_rf10_dashboard_script_count_unchanged_with_envelope():
    html = build_dashboard_html(_ROWS, "CSS", "JS", envelope=_env())
    assert html.count("</script>") == 2      # Band/Fuss bringen kein <script>
