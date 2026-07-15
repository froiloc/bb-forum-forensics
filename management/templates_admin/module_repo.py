# =============================================================================
# management/templates_admin/module_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W1 (Build 426): Lese-/Schreib-Repo der Baustein-Module
# =============================================================================
# Zweck:
#   Liest report_modules (fuer die Liste in der Autoren-Maske) und schreibt sie
#   AUSSCHLIESSLICH ueber den auditierten TemplatesWriter (Build 421). Ein Upsert
#   (create ODER update, nach der stabilen module_key) laeuft mit seinem
#   Audit-Eintrag (target_type='module') in EINER Transaktion.
#
#   Die Validierung (module_validator) erfolgt VOR dem Aufruf von upsert() im
#   Endpunkt — das Repo schreibt nur bereits gepruefte Module.
#
# Version: v0.7.426 · Build: 426 · 2026-07-15
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.gateway.templates_writer import TemplatesWriter


class ModuleAuthorRepo:
    """Lese-/Schreibzugriff auf templates.db.report_modules."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        rows = self._con.execute(
            "SELECT id, module_key, title, description, role, topic, body, "
            "sort_order, is_active, created_by, created_at, updated_at "
            "FROM report_modules ORDER BY role, sort_order, module_key"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        row = self._con.execute(
            "SELECT id, module_key, title, description, role, topic, body, "
            "sort_order, is_active, created_by, created_at, updated_at "
            "FROM report_modules WHERE module_key = ?", (key,)).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------
    def upsert(self, m: Dict[str, Any], changed_by: str,
               *, ts: Optional[int] = None) -> Dict[str, Any]:
        """
        Legt einen Baustein an ODER aktualisiert ihn (nach module_key). Auditiert
        ueber den TemplatesWriter (target_type='module'). Gibt {target_id,
        created(bool)} zurueck.
        """
        key = str(m["module_key"]).strip()
        existing = self.get_by_key(key)
        created = existing is None
        now = int(ts if ts is not None else time.time())

        title = str(m["title"]).strip()
        desc = m.get("description")
        desc = None if desc is None else str(desc)
        role = m["role"]
        topic = str(m["topic"]).strip()
        body = str(m["body"])
        sort_order = int(m.get("sort_order") or 0)

        # Kanonische Vorher/Nachher-Werte fuer den Audit (nur Fakten, kompakt;
        # der volle body-Text wird NICHT in den Audit kopiert — er kann sehr
        # lang sein; die Laenge genuegt als Beleg der Aenderung).
        new_value = json.dumps({"title": title, "role": role, "topic": topic,
                                "body_len": len(body)}, ensure_ascii=False)
        old_value = None
        if existing is not None:
            old_value = json.dumps(
                {"title": existing.get("title"),
                 "role": existing.get("role"),
                 "topic": existing.get("topic"),
                 "body_len": len(str(existing.get("body") or ""))},
                ensure_ascii=False)

        def _do_write(con: sqlite3.Connection) -> Dict[str, Any]:
            if created:
                con.execute(
                    "INSERT INTO report_modules "
                    "(title, description, role, topic, body, sort_order, "
                    " is_active, created_by, created_at, updated_at, module_key) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                    (title, desc, role, topic, body, sort_order,
                     changed_by, now, now, key))
            else:
                con.execute(
                    "UPDATE report_modules SET title=?, description=?, role=?, "
                    "topic=?, body=?, sort_order=?, updated_at=? "
                    "WHERE module_key=?",
                    (title, desc, role, topic, body, sort_order, now, key))
            return {"target_id": key, "old_value": old_value,
                    "new_value": new_value}

        writer = TemplatesWriter(self._con)
        writer.audited_write(
            do_write=_do_write,
            action=("create" if created else "update"),
            target_type="module", changed_by=changed_by, ts=now)
        return {"target_id": key, "created": created}
