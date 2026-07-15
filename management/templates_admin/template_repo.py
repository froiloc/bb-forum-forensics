# =============================================================================
# management/templates_admin/template_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W3 (Build 424): Lese-/Schreib-Repo der Dokumentvorlagen
# =============================================================================
# Zweck:
#   Liest report_templates (fuer die Liste in der Autoren-Maske) und schreibt sie
#   AUSSCHLIESSLICH ueber den auditierten TemplatesWriter (Build 421). Ein Upsert
#   (create ODER update, nach dem stabilen template_key) laeuft mit seinem
#   Audit-Eintrag (target_type='template') in EINER Transaktion.
#
#   Die Validierung (template_validator) erfolgt VOR dem Aufruf von upsert() im
#   Endpunkt — das Repo schreibt nur bereits gepruefte Vorlagen.
#
#   Serialisierung: die Bloecke werden als KOMPAKTES, deterministisches JSON in
#   report_templates.blocks_json abgelegt (ensure_ascii=False -> multilinguales
#   Forum, UTF-8). Der forensische Webserver liest daraus (insert_template) und
#   vergibt je Block eine frische UUID.
#
# Version: v0.7.424 · Build: 424 · 2026-07-15
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.gateway.templates_writer import TemplatesWriter
from management.templates_admin.template_validator import coerce_blocks


class TemplateAuthorRepo:
    """Lese-/Schreibzugriff auf templates.db.report_templates."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        rows = self._con.execute(
            "SELECT id, template_key, title, description, report_type, "
            "blocks_json, sort_order, is_active, created_by, created_at, "
            "updated_at FROM report_templates ORDER BY sort_order, template_key"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        row = self._con.execute(
            "SELECT id, template_key, title, description, report_type, "
            "blocks_json, sort_order, is_active, created_by, created_at, "
            "updated_at FROM report_templates WHERE template_key = ?",
            (key,)).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------
    def upsert(self, t: Dict[str, Any], changed_by: str,
               *, ts: Optional[int] = None) -> Dict[str, Any]:
        """
        Legt eine Vorlage an ODER aktualisiert sie (nach template_key). Auditiert
        ueber den TemplatesWriter (target_type='template'). Gibt
        {target_id, created(bool)} zurueck.
        """
        key = str(t["template_key"]).strip()
        existing = self.get_by_key(key)
        created = existing is None
        now = int(ts if ts is not None else time.time())

        title = str(t["title"]).strip()
        desc = t.get("description")
        desc = None if desc is None else str(desc)
        report_type = t["report_type"]
        sort_order = int(t.get("sort_order") or 0)

        # Bloecke kanonisch serialisieren (kompakt, UTF-8-treu).
        blocks, berr = coerce_blocks(t)
        if berr:
            # Sollte durch die vorgelagerte Validierung nie eintreten; als
            # Sicherung dennoch hart scheitern (kein stiller Fehlschrieb).
            raise ValueError("blocks nicht serialisierbar: %s" % berr)
        blocks_json = json.dumps(blocks, ensure_ascii=False,
                                 separators=(",", ":"))

        # Kanonische Vorher/Nachher-Werte fuer den Audit (nur Fakten, kompakt).
        new_value = json.dumps(
            {"title": title, "report_type": report_type,
             "n_blocks": len(blocks)}, ensure_ascii=False)
        old_value = None
        if existing is not None:
            try:
                old_blocks = json.loads(existing.get("blocks_json") or "[]")
                old_n = len(old_blocks) if isinstance(old_blocks, list) else 0
            except (json.JSONDecodeError, ValueError):
                old_n = -1  # unlesbarer Altstand -> als -1 dokumentieren
            old_value = json.dumps(
                {"title": existing.get("title"),
                 "report_type": existing.get("report_type"),
                 "n_blocks": old_n}, ensure_ascii=False)

        def _do_write(con: sqlite3.Connection) -> Dict[str, Any]:
            if created:
                con.execute(
                    "INSERT INTO report_templates "
                    "(template_key, title, description, report_type, "
                    " blocks_json, sort_order, is_active, created_by, "
                    " created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                    (key, title, desc, report_type, blocks_json, sort_order,
                     changed_by, now, now))
            else:
                con.execute(
                    "UPDATE report_templates SET title=?, description=?, "
                    "report_type=?, blocks_json=?, sort_order=?, updated_at=? "
                    "WHERE template_key=?",
                    (title, desc, report_type, blocks_json, sort_order, now,
                     key))
            return {"target_id": key, "old_value": old_value,
                    "new_value": new_value}

        writer = TemplatesWriter(self._con)
        writer.audited_write(
            do_write=_do_write,
            action=("create" if created else "update"),
            target_type="template", changed_by=changed_by, ts=now)
        return {"target_id": key, "created": created}
