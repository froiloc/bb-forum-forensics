# =============================================================================
# management/rbac/policy_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# PolicyRepo — REIN LESENDER Snapshot der RBAC-Policy aus coordinator.db, so wie
# ihn die Cockpit-Sicht "Rechte / Policy" (policy.view, Build 361/362) anzeigt:
#
#   roles        — Rollen-Katalog (rbac_role: code, label)
#   capabilities — Faehigkeits-Katalog (rbac_capability: code, label, description)
#   grants       — AKTIVE Grants (rbac_grant, revoked_at IS NULL): welche Rolle
#                  welche Faehigkeit mit welchem Scope hat, inkl. audit_seq
#   assignments  — AKTIVE Personen-Rollen (person_role, revoked_at IS NULL),
#                  angereichert um system_username/display_name der Person
#
# Scope-Semantik (im Endpunkt genutzt):
#   snapshot()                 -> volle Matrix (scope 'alle')
#   snapshot(person_id=<id>)   -> auf die Person gefiltert ("meine Rechte"):
#       nur deren aktive Zuweisungen und nur die Grants ihrer aktiven Rollen.
#       roles/capabilities bleiben der volle Katalog (nicht schuetzenswert).
#
# Kein Schreibpfad. Beleg: Bauplan B7 v1.1 §11.3; RbacRepo-Lesepfade.
# Version: v0.7.361 · Build: 361 · 2026-07-10
# =============================================================================

import sqlite3
from typing import Any, Dict, List, Optional


def _rows(cur) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


class PolicyRepo:
    """Liest einen konsolidierten RBAC-Policy-Snapshot (read-only)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def snapshot(self, person_id: Optional[int] = None) -> Dict[str, Any]:
        roles = _rows(self._con.execute(
            "SELECT code, label FROM rbac_role ORDER BY code"))
        capabilities = _rows(self._con.execute(
            "SELECT code, label, description FROM rbac_capability "
            "ORDER BY code"))

        if person_id is None:
            grants = self._grants()
            assignments = self._assignments()
        else:
            assignments = self._assignments(person_id=person_id)
            own_roles = sorted({a["role_code"] for a in assignments})
            grants = [g for g in self._grants()
                      if g["role_code"] in own_roles]

        return {
            "scope": "alle" if person_id is None else "eigene",
            "roles": roles,
            "capabilities": capabilities,
            "grants": grants,
            "assignments": assignments,
            "counts": {
                "roles": len(roles),
                "capabilities": len(capabilities),
                "grants": len(grants),
                "assignments": len(assignments),
            },
        }

    # ------------------------------------------------------------- internals
    def _grants(self) -> List[Dict[str, Any]]:
        # Nur AKTIVE Grants; die relevanten Felder fuer die Sicht.
        return _rows(self._con.execute(
            "SELECT id, role_code, capability_code, scope, audit_seq, "
            "       granted_by, granted_at, note "
            "FROM rbac_grant WHERE revoked_at IS NULL "
            "ORDER BY role_code, capability_code, id"))

    def _assignments(self, person_id: Optional[int] = None
                     ) -> List[Dict[str, Any]]:
        # AKTIVE Personen-Rollen, angereichert um den Anzeigenamen.
        sql = ("SELECT pr.id, pr.person_id, p.system_username, p.display_name, "
               "       pr.role_code, pr.assigned_by, pr.assigned_at, "
               "       pr.audit_seq "
               "FROM person_role pr JOIN person p ON p.id = pr.person_id "
               "WHERE pr.revoked_at IS NULL")
        params: list = []
        if person_id is not None:
            sql += " AND pr.person_id = ?"
            params.append(person_id)
        sql += " ORDER BY pr.person_id, pr.role_code, pr.id"
        return _rows(self._con.execute(sql, params))
