# =============================================================================
# management/person/person_overview_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Personalverwaltung (Build 503)
# =============================================================================
# Zweck:
#   REIN LESENDES Aggregat fuer die Personalverwaltungs-Sicht (Bauplan
#   Build503 §3): alle Personen (inkl. Aktiv-Status aus M020 und Rollen-Flags)
#   plus je Person die AKTIVEN Rollenzuweisungen (person_role.revoked_at IS
#   NULL) mit ihrem Label aus rbac_role, plus der Rollenkatalog fuer das
#   Zuweisen-Dropdown der Oberflaeche.
#
# Bewusste Entwurfsentscheidungen:
#   - KEIN Schreibpfad hier: geschrieben wird ausschliesslich ueber die
#     bestehenden auditierten Wege (PersonRepo fuer Flags, RbacRepo fuer
#     Rollenzuweisungen) — dieses Repo ist das Lesemodell der Sicht.
#   - person_role_id wird MITGELIEFERT, damit der Widerruf in der Oberflaeche
#     exakt die Zeile trifft, die angezeigt wurde (RbacRepo.revoke_role
#     arbeitet auf der id; kein Raten ueber person+rolle).
#   - Defensiv wie PersonRepo: fehlen die M020-Spalten (Altbestand), gilt
#     is_active=1 — die Sicht bricht nicht (Schreibpfade verlangen M020 ohnehin
#     ausdruecklich).
#
# Version: v0.8.503 · Build: 503 · 2026-07-24
# =============================================================================

import sqlite3
from typing import Any, Dict, List

from management.person.person_repo import PersonRepo


class PersonOverviewRepo:
    """Nur-lesendes Aggregat: Personen + aktive Rollen + Rollenkatalog."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    def overview(self) -> Dict[str, Any]:
        """
        Liefert {persons: [...], roles_catalog: [...]}.
        persons aufsteigend nach system_username (wie PersonRepo.list_persons),
        je Person 'roles': aktive Zuweisungen aufsteigend nach role_code.
        """
        # Personen ueber PersonRepo lesen (eine Wahrheitsquelle fuer das
        # defensive M020-Verhalten; writer wird fuer Lesen nicht benoetigt).
        persons = PersonRepo(self._con, writer=None).list_persons()

        # Aktive Rollenzuweisungen ALLER Personen in einem Rutsch (die Sicht
        # zeigt immer die volle Liste; N Einzelabfragen waeren nur Overhead).
        rows = self._con.execute(
            "SELECT pr.id AS person_role_id, pr.person_id, pr.role_code, "
            "       pr.assigned_at, r.label "
            "FROM person_role pr JOIN rbac_role r ON r.code = pr.role_code "
            "WHERE pr.revoked_at IS NULL "
            "ORDER BY pr.person_id, pr.role_code"
        ).fetchall()
        by_person: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            by_person.setdefault(int(r["person_id"]), []).append({
                "person_role_id": int(r["person_role_id"]),
                "role_code": r["role_code"],
                "label": r["label"],
                "assigned_at": (int(r["assigned_at"])
                                if r["assigned_at"] is not None else None),
            })
        for p in persons:
            p["roles"] = by_person.get(int(p["id"]), [])

        catalog = [
            {"code": r["code"], "label": r["label"]}
            for r in self._con.execute(
                "SELECT code, label FROM rbac_role ORDER BY code ASC"
            ).fetchall()
        ]
        return {"persons": persons, "roles_catalog": catalog}
