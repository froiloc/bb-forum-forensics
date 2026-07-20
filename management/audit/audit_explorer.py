# =============================================================================
# management/audit/audit_explorer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Audit-/Revisions-Explorer
# =============================================================================
# Zweck (Idee 24, AP-2E):
#   REIN LESENDER, durchblaetterbarer und filterbarer Zugriff auf den
#   hash-verketteten audit_log. Waehrend die Integritaets-Sicht nur den ZUSTAND
#   der Kette zeigt (gruen/Bruch), erlaubt dieser Explorer die Durchsicht der
#   EINTRAEGE selbst (wer/wann/was) — die Grundlage fuer Revision und den
#   gerichtsfesten Export (audit_export.py).
#
#   Der audit_log ist per Trigger APPEND-ONLY (audit_log_no_update/-_delete):
#   dieses Modul schreibt NICHTS und arbeitet auf einer mode=ro-Verbindung.
#   Die Filter sind AUSSCHLIESSLICH parametrisiert (keine SQL-Injektion); die
#   Freitext-Payload (content) wird nur DURCHGEREICHT, nicht interpretiert.
#
# Version: v0.7.467 · Build: 467 · 2026-07-20
# =============================================================================

import sqlite3
from typing import Any, Dict, List, Optional, Sequence

#: Grenzen der Seitengroesse (Schutz vor versehentlichen Riesen-Abfragen).
DEFAULT_LIMIT = 50
MAX_LIMIT = 500

#: Auswaehlbare Spalten (JOIN person fuer den Akteurs-Anzeigenamen).
_SELECT = (
    "SELECT a.seq, a.ts, a.actor_id, a.event_type, a.target_type, "
    "a.target_id, a.content, a.row_hash, "
    "p.display_name AS actor_name, p.system_username AS actor_username "
    "FROM audit_log a LEFT JOIN person p ON p.id = a.actor_id"
)


class AuditExplorerError(Exception):
    """Ungueltige Filter-/Seiteneingabe."""


class AuditExplorer:
    """Read-only Filter-/Paginierungs-Zugriff auf audit_log."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------ Hilfen
    @staticmethod
    def _clamp_limit(limit: Optional[int]) -> int:
        if limit is None:
            return DEFAULT_LIMIT
        try:
            v = int(limit)
        except (TypeError, ValueError) as exc:
            raise AuditExplorerError("limit muss eine Zahl sein.") from exc
        return max(1, min(MAX_LIMIT, v))

    @staticmethod
    def _offset(offset: Optional[int]) -> int:
        if offset is None:
            return 0
        try:
            v = int(offset)
        except (TypeError, ValueError) as exc:
            raise AuditExplorerError("offset muss eine Zahl sein.") from exc
        return max(0, v)

    @staticmethod
    def _int_or_none(value, feld: str) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise AuditExplorerError("%s muss eine Zahl sein." % feld) from exc

    def _where(
        self, *, event_types, actor_id, target_type, target_id,
        seq_from, seq_to, ts_from, ts_to,
    ):
        clauses: List[str] = []
        params: List[Any] = []

        if event_types:
            marks = ",".join("?" for _ in event_types)
            clauses.append("a.event_type IN (%s)" % marks)
            params.extend(str(e) for e in event_types)
        aid = self._int_or_none(actor_id, "actor_id")
        if aid is not None:
            clauses.append("a.actor_id = ?")
            params.append(aid)
        if target_type:
            clauses.append("a.target_type = ?")
            params.append(str(target_type))
        if target_id not in (None, ""):
            clauses.append("a.target_id = ?")
            params.append(str(target_id))
        sf = self._int_or_none(seq_from, "seq_from")
        if sf is not None:
            clauses.append("a.seq >= ?")
            params.append(sf)
        st = self._int_or_none(seq_to, "seq_to")
        if st is not None:
            clauses.append("a.seq <= ?")
            params.append(st)
        tf = self._int_or_none(ts_from, "ts_from")
        if tf is not None:
            clauses.append("a.ts >= ?")
            params.append(tf)
        tt = self._int_or_none(ts_to, "ts_to")
        if tt is not None:
            clauses.append("a.ts <= ?")
            params.append(tt)

        sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return sql, params

    # ------------------------------------------------------------------- Lesen
    def query(
        self, *,
        event_types: Optional[Sequence[str]] = None,
        actor_id: Optional[int] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        seq_from: Optional[int] = None,
        seq_to: Optional[int] = None,
        ts_from: Optional[int] = None,
        ts_to: Optional[int] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Gefilterte, absteigend nach seq sortierte Seite. -> {total, rows, limit,
        offset, has_more}. Die Sortierung (neueste zuerst) ist bewusst; der
        gerichtsfeste Export nutzt DENSELBEN Filter (audit_export).
        """
        lim = self._clamp_limit(limit)
        off = self._offset(offset)
        where, params = self._where(
            event_types=event_types, actor_id=actor_id, target_type=target_type,
            target_id=target_id, seq_from=seq_from, seq_to=seq_to,
            ts_from=ts_from, ts_to=ts_to)

        total = int(self._con.execute(
            "SELECT COUNT(*) FROM audit_log a" + where, params).fetchone()[0])
        rows = [dict(r) for r in self._con.execute(
            _SELECT + where + " ORDER BY a.seq DESC LIMIT ? OFFSET ?",
            (*params, lim, off)).fetchall()]

        return {
            "total": total, "rows": rows, "limit": lim, "offset": off,
            "has_more": (off + len(rows)) < total,
        }

    def facets(self) -> Dict[str, Any]:
        """
        Fuer die Filter-Auswahl: die im Log VORHANDENEN Event-Typen und Akteure.
        (Nur was wirklich vorkommt — kein leeres Angebot, kein Rauschen.)
        """
        events = [r[0] for r in self._con.execute(
            "SELECT DISTINCT event_type FROM audit_log ORDER BY event_type")]
        actors = [
            {"actor_id": r["actor_id"], "actor_name": r["actor_name"],
             "actor_username": r["actor_username"]}
            for r in self._con.execute(
                "SELECT DISTINCT a.actor_id, p.display_name AS actor_name, "
                "p.system_username AS actor_username "
                "FROM audit_log a LEFT JOIN person p ON p.id = a.actor_id "
                "WHERE a.actor_id IS NOT NULL "
                "ORDER BY p.display_name")
        ]
        return {"event_types": events, "actors": actors}

    def get(self, seq: int) -> Optional[Dict[str, Any]]:
        """Ein Einzeleintrag inkl. content/row_hash (oder None)."""
        row = self._con.execute(
            _SELECT + " WHERE a.seq = ?",
            (self._int_or_none(seq, "seq"),)).fetchone()
        return dict(row) if row is not None else None
