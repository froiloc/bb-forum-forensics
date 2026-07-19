# =============================================================================
# management/export/context_builder.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck:
#   Baut aus einer offenen coordinator.db-Verbindung + Pfad einen ExportContext
#   fuer die Sichten-Exporte (B442-Retrofit). Zentralisiert die drei bislang je
#   Admin dupliziert vorbereiteten Angaben:
#     * Buildnummer  — aus build.json (GR4).
#     * Integritaets-Kettenspitze — verify_chain + tip aus dem audit_log.
#     * ausfuehrende Identitaet    — IdentityResolver (SAMAccountName = stabile
#                                    forensische Identitaet; --actor uebersteuert).
#     * Zeitstempel  — jetzt (UTC), formatiert.
#
#   VOLL ABGESICHERT: KEINE Ausnahme darf aus dem Builder dringen — ein
#   Export darf nicht am Rahmen scheitern. Fehlt/bricht eine Quelle, wird der
#   jeweilige Wert EHRLICH als 'nicht geprueft'/'unbekannt' gefuehrt (GR1),
#   nicht stillschweigend geschoent.
#
#   NICHT rein (liest DB/Uhr/Datei) — bewusst getrennt von den reinen Renderern.
#
# Version: v0.7.442 · Build: 442 · 2026-07-19
# =============================================================================

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from management.export.export_envelope import ExportContext, DEFAULT_KLASSIFIKATION

_DEFAULT_BEHOERDE = "Polizei NRW"


def _build_number() -> int:
    """Buildnummer aus der repo-eigenen build.json (GR4); Fallback 0."""
    try:
        p = Path(__file__).resolve().parents[2] / "build.json"
        return int(json.loads(p.read_text(encoding="utf-8"))["build"])
    except Exception:
        return 0


def _verify_tip(con) -> Tuple[Optional[bool], Optional[int], Optional[str], str]:
    """
    (chain_ok, tip_seq, tip_hash, detail). chain_ok: True/False/None(nicht
    pruefbar). Wirft nie — fehlt audit_log o. Ae., wird 'nicht pruefbar'
    zurueckgegeben (GR1).
    """
    try:
        from management.audit.audit_log import AuditLog
        audit = AuditLog(con)
        vr = audit.verify_chain()
        tip_hash, tip_seq = audit.tip()
        return bool(vr.ok), tip_seq, tip_hash, vr.detail
    except Exception as exc:  # sqlite/Attribute/Import — nie eskalieren
        return None, None, None, "audit_log nicht pruefbar: %s" % exc


def _resolve_actor(db_path: str, actor: Optional[str]) -> Tuple[str, Optional[str]]:
    """(system_username, display_name); --actor uebersteuert. Wirft nie."""
    try:
        from management.server.identity import IdentityResolver
        person = IdentityResolver(db_path).resolve(system_username=actor)
        return (person.get("system_username") or (actor or "unbekannt"),
                person.get("display_name"))
    except Exception:
        return (actor or "unbekannt"), None


def build_export_context(
    *,
    con: sqlite3.Connection,
    db_path: str,
    behoerde: Optional[str] = None,
    aktenzeichen: Optional[str] = None,
    actor: Optional[str] = None,
    klassifikation: Optional[str] = None,
    now_utc: Optional[str] = None,
) -> ExportContext:
    """
    Setzt den ExportContext zusammen. 'now_utc' ist injizierbar (Tests);
    Default = aktueller UTC-Zeitstempel. Alle Fehlerquellen sind abgesichert.
    """
    chain_ok, tip_seq, tip_hash, _detail = _verify_tip(con)
    ersteller, anzeigename = _resolve_actor(db_path, actor)
    generated = now_utc or datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC")
    return ExportContext(
        behoerde=behoerde or _DEFAULT_BEHOERDE,
        aktenzeichen=aktenzeichen or "Gesamtuebersicht",
        ersteller=ersteller,
        build_number=_build_number(),
        generated_at=generated,
        chain_ok=chain_ok,
        chain_tip_seq=tip_seq,
        chain_tip_hash=tip_hash,
        klassifikation=klassifikation or DEFAULT_KLASSIFIKATION,
        anzeigename=anzeigename,
    )
