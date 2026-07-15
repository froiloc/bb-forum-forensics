# =============================================================================
# management/templates_admin/query_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W2 (Build 422): Lese-/Schreib-Repo der Platzhalter-Queries
# =============================================================================
# Zweck:
#   Liest die placeholder_queries (fuer die Liste in der Autoren-Maske) und
#   schreibt sie AUSSCHLIESSLICH ueber den auditierten TemplatesWriter (Build
#   421). Ein Upsert (create ODER update) laeuft mit seinem Audit-Eintrag in
#   EINER Transaktion.
#
#   Die Validierung (query_validator) erfolgt VOR dem Aufruf von upsert() im
#   Endpunkt — das Repo schreibt nur bereits gepruefte Queries.
#
# Version: v0.7.422 · Build: 422 · 2026-07-14
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.gateway.templates_writer import TemplatesWriter


class QueryAuthorRepo:
    """Lese-/Schreibzugriff auf templates.db.placeholder_queries."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        rows = self._con.execute(
            "SELECT id, title, description, sql_query, tags, return_type, "
            "is_active, created_by, created_at, updated_at "
            "FROM placeholder_queries ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def get(self, qid: str) -> Optional[Dict[str, Any]]:
        row = self._con.execute(
            "SELECT id, title, description, sql_query, tags, return_type, "
            "is_active, created_by, created_at, updated_at "
            "FROM placeholder_queries WHERE id = ?", (qid,)).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------
    def upsert(self, q: Dict[str, Any], changed_by: str,
               *, ts: Optional[int] = None) -> Dict[str, Any]:
        """
        Legt eine Query an ODER aktualisiert sie (nach id). Auditiert ueber den
        TemplatesWriter. Gibt {target_id, created(bool)} zurueck.
        """
        qid = str(q["id"]).strip()
        existing = self.get(qid)
        created = existing is None
        now = int(ts if ts is not None else time.time())
        title = str(q["title"]).strip()
        desc = str(q.get("description") or "")
        sql = str(q["sql_query"]).strip()
        tags = q.get("tags")
        rt = q.get("return_type") or "scalar"

        # Kanonische Vorher/Nachher-Werte fuer den Audit-Eintrag (nur Fakten).
        new_value = json.dumps({"title": title, "sql_query": sql,
                                "return_type": rt}, ensure_ascii=False)
        old_value = None
        if existing is not None:
            old_value = json.dumps(
                {"title": existing.get("title"),
                 "sql_query": existing.get("sql_query"),
                 "return_type": existing.get("return_type")},
                ensure_ascii=False)

        def _do_write(con: sqlite3.Connection) -> Dict[str, Any]:
            if created:
                con.execute(
                    "INSERT INTO placeholder_queries "
                    "(id, title, description, sql_query, tags, return_type, "
                    " is_active, created_by, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                    (qid, title, desc, sql, tags, rt, changed_by, now, now))
            else:
                con.execute(
                    "UPDATE placeholder_queries SET title=?, description=?, "
                    "sql_query=?, tags=?, return_type=?, updated_at=? "
                    "WHERE id=?",
                    (title, desc, sql, tags, rt, now, qid))
            return {"target_id": qid, "old_value": old_value,
                    "new_value": new_value}

        writer = TemplatesWriter(self._con)
        writer.audited_write(
            do_write=_do_write,
            action=("create" if created else "update"),
            target_type="query", changed_by=changed_by, ts=now)
        return {"target_id": qid, "created": created}
