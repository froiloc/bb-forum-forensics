# =============================================================================
# management/templates_admin/placeholder_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Platzhalter-Neuordnung (Build 489, Slice 1): Lese-/Schreib-Repo der Platzhalter
# =============================================================================
# Zweck:
#   Liest templates.db.placeholders (fuer die Liste in der Autoren-Maske) und
#   schreibt AUSSCHLIESSLICH ueber den auditierten TemplatesWriter (Build 421,
#   target_type 'placeholder' — CHECK-Erweiterung durch
#   migrate_templates_placeholders.py). Ein Upsert (create ODER update) laeuft
#   mit seinem Audit-Eintrag in EINER Transaktion.
#
#   Nachfolger des query_repo (Build 422). Die Validierung
#   (placeholder_validator) erfolgt VOR dem Aufruf von upsert() im Endpunkt —
#   das Repo schreibt nur bereits gepruefte Platzhalter.
#
#   Normalisierung: leere Strings der optionalen Felder (sql_query,
#   default_value, validation, validation_type, tags) werden als NULL
#   gespeichert — so greifen die CHECK-Regeln der Tabelle eindeutig
#   (z.B. "(validation IS NULL) = (validation_type IS NULL)").
#
# Beleg: Bauplan management/Bauplan_Platzhalter_DB_v0_1.md §4 (mc-Freigabe
# 2026-07-21).
# Version: v0.8.489 · Build: 489 · 2026-07-21
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.gateway.templates_writer import TemplatesWriter

_COLS = ("id, title, description, type, sql_query, default_value, "
         "validation, validation_type, tags, return_type, is_active, "
         "created_by, created_at, updated_at")


def _nullable(v: Any) -> Optional[str]:
    """Leere/fehlende optionale Felder -> NULL (s. Kopfkommentar)."""
    if v is None:
        return None
    s = str(v)
    return s if s.strip() != "" else None


class PlaceholderAuthorRepo:
    """Lese-/Schreibzugriff auf templates.db.placeholders."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        rows = self._con.execute(
            "SELECT %s FROM placeholders ORDER BY type, id" % _COLS).fetchall()
        return [dict(r) for r in rows]

    def get(self, pid: str) -> Optional[Dict[str, Any]]:
        row = self._con.execute(
            "SELECT %s FROM placeholders WHERE id = ?" % _COLS,
            (pid,)).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------
    def upsert(self, p: Dict[str, Any], changed_by: str,
               *, ts: Optional[int] = None) -> Dict[str, Any]:
        """
        Legt einen Platzhalter an ODER aktualisiert ihn (nach id). Auditiert
        ueber den TemplatesWriter (target_type 'placeholder'). Gibt
        {target_id, created(bool)} zurueck.
        """
        pid = str(p["id"]).strip()
        existing = self.get(pid)
        created = existing is None
        now = int(ts if ts is not None else time.time())

        title = str(p["title"]).strip()
        desc = str(p.get("description") or "")
        ptype = str(p["type"]).strip()
        sql = _nullable(p.get("sql_query"))
        default_value = _nullable(p.get("default_value"))
        validation = _nullable(p.get("validation"))
        vtype = _nullable(p.get("validation_type"))
        tags = _nullable(p.get("tags"))
        rt = p.get("return_type") or "scalar"

        # Kanonische Vorher/Nachher-Werte fuer den Audit-Eintrag (nur Fakten;
        # inkl. Typ und Validierung — genau das ist die neue Beweisgrundlage).
        def _canon(src: Dict[str, Any]) -> str:
            return json.dumps(
                {"title": src.get("title"), "type": src.get("type"),
                 "sql_query": src.get("sql_query"),
                 "default_value": src.get("default_value"),
                 "validation": src.get("validation"),
                 "validation_type": src.get("validation_type"),
                 "return_type": src.get("return_type")},
                ensure_ascii=False)

        new_value = _canon({"title": title, "type": ptype, "sql_query": sql,
                            "default_value": default_value,
                            "validation": validation,
                            "validation_type": vtype, "return_type": rt})
        old_value = _canon(existing) if existing is not None else None

        def _do_write(con: sqlite3.Connection) -> Dict[str, Any]:
            if created:
                con.execute(
                    "INSERT INTO placeholders "
                    "(id, title, description, type, sql_query, default_value, "
                    " validation, validation_type, tags, return_type, "
                    " is_active, created_by, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                    (pid, title, desc, ptype, sql, default_value, validation,
                     vtype, tags, rt, changed_by, now, now))
            else:
                con.execute(
                    "UPDATE placeholders SET title=?, description=?, type=?, "
                    "sql_query=?, default_value=?, validation=?, "
                    "validation_type=?, tags=?, return_type=?, updated_at=? "
                    "WHERE id=?",
                    (title, desc, ptype, sql, default_value, validation,
                     vtype, tags, rt, now, pid))
            return {"target_id": pid, "old_value": old_value,
                    "new_value": new_value}

        writer = TemplatesWriter(self._con)
        writer.audited_write(
            do_write=_do_write,
            action=("create" if created else "update"),
            target_type="placeholder", changed_by=changed_by, ts=now)
        return {"target_id": pid, "created": created}
