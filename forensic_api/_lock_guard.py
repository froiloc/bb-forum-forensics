# =============================================================================
# forensic_api/_lock_guard.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Gemeinsame Lock-Pruefungsfunktion fuer alle schreibenden Editor-Endpunkte.
#   Extrahiert aus report.py um Codeduplizierung zu vermeiden.
#
#   Schreibende Aktionen in folgenden Endpunkten verwenden diese Funktion:
#     - editor_block.py  (save, delete)
#     - editor_order.py  (update)
#     - editor_evidence.py (add, remove)
#
#   Dreischichtiger Lock-Mechanismus (§8.6 Bauplan B4):
#     Schicht 1: BroadcastChannel (client-seitig)
#     Schicht 2: SSE-Verbindungsabriss gibt Lock automatisch frei
#     Schicht 3: Server-Lock in editor_locks (diese Funktion prüft Schicht 3)
#
# Beleg: AP-E3, Projektgespraech 2026-04-19
# Version: v0.6.044 · Build: 044 · 2026-04-19
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.evidence_db import EvidenceDb

# Vorgefertigte Fehlerbody-Bytes — werden bei jedem Lock-Fehler wiederverwendet.
_LOCK_REQUIRED_BODY = json.dumps(
    {"error": "Lock erforderlich", "code": "LOCK_REQUIRED"},
    ensure_ascii=False,
).encode("utf-8")

_CONTENT_TYPE_JSON = "application/json; charset=utf-8"


def require_lock(
    handler: "ForensicRequestHandler",
    data: dict,
    evidence_db: "EvidenceDb",
) -> "str | None":
    """
    Prueft ob ein gueltiger Editor-Lock gehalten wird.

    Liest die Lock-ID aus:
      1. X-Forensic-Lock-Id-Header (bevorzugt)
      2. data["lock_id"] (Fallback fuer JSON-Body-Uebermittlung)

    Args:
        handler:     ForensicRequestHandler-Instanz.
        data:        Geparstes JSON-Request-Body als Dict.
        evidence_db: EvidenceDb-Instanz fuer validate_lock().

    Returns:
        lock_id (str) wenn Lock gueltig.
        None wenn Lock fehlt oder ungueltig — sendet dabei HTTP 423 an den Client.

    Beleg: AP-E3, Projektgespraech 2026-04-19
    """
    lock_id = (
        handler.headers.get("X-Forensic-Lock-Id", "")
        or str(data.get("lock_id", ""))
    )

    if not lock_id:
        handler.send_response_body(
            423, _LOCK_REQUIRED_BODY, content_type=_CONTENT_TYPE_JSON
        )
        return None

    # Bug 2.120 Fix Build 226: report_id aus Request-Body lesen und
    # an validate_lock weitergeben fuer bericht-spezifischen Lock.
    # Beleg: Bugfix Build 226, Projektgespraech 2026-05-18
    rid_raw = data.get("report_id") if data else None
    try:
        report_id_guard = int(rid_raw) if rid_raw is not None else None
    except (TypeError, ValueError):
        report_id_guard = None
    _rid = report_id_guard or 0
    if not evidence_db.validate_lock(_rid, lock_id):
        handler.send_response_body(
            423, _LOCK_REQUIRED_BODY, content_type=_CONTENT_TYPE_JSON
        )
        return None

    return lock_id
