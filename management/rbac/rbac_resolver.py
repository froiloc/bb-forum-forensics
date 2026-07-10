# =============================================================================
# management/rbac/rbac_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   RBAC Schnitt (c): die REIN LESENDE Aufloesungs-/Durchsetzungsschicht. Loest
#   fuer eine Person ihre effektiven Faehigkeiten auf (Rollen -> aktive Grants ->
#   Faehigkeit + weitester Scope) und stellt den Start-Check bereit, der die
#   Konsistenz zwischen Code-Katalog (catalog.py) und DB (rbac_capability/
#   rbac_role) erzwingt (Grundregel 1: nichts wird still uebersprungen).
#
#   KEIN Schreibvorgang, KEINE Migration, KEIN CoordinatorWriter -> kein
#   Datenverlust-Risiko. coordinator.db ist im Produktivbetrieb ohnehin nur
#   lesend.
#
# Aufloesung (Beleg: Bauplan B7 v1.1 §11.3):
#   aktive Rollen der Person (person_role, revoked_at IS NULL)
#     -> Vereinigung der aktiven Grants dieser Rollen (rbac_grant, revoked_at
#        IS NULL)
#     -> Faehigkeit gilt bei >=1 Grant; Scope = WEITESTER (alle > eigene > kein).
#   default-deny: keine Rolle / kein Grant => keine Faehigkeit.
#
# Scope-Ordnung: 'alle' (2) > 'eigene' (1) > None (0). Bei mehreren Grants fuer
#   dieselbe Faehigkeit gewinnt der hoechste Rang (der weiteste Zugriff). None
#   bedeutet "kein Scope ausgewiesen" (fuer Faehigkeiten ohne Scope-Semantik wie
#   reports.approve); es ist der niedrigste Rang, damit ein ausgewiesenes
#   'eigene'/'alle' immer gewinnt.
#
# Start-Check (Beleg §11.3 "jede Code-Capability existiert in der DB"):
#   Richtung Code ⊆ DB — jede Rolle/Faehigkeit aus catalog.py MUSS in der DB
#   geseedet sein. Die DB DARF voraus sein (eine neue Migration hat Codes
#   ergaenzt, die der Code noch nicht kennt) — das ist zulaessig und kein Fehler.
#   Wird in management.py beim Start des Management-Servers verdrahtet (Welle 0,
#   Schritt 3); hier eigenstaendig und testbar bereitgestellt.
#
# Version: v0.7.345 · Build: 345 · 2026-07-10
# =============================================================================

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional

from management.rbac import catalog

logger = logging.getLogger(__name__)


class RbacResolverError(Exception):
    """Basisfehler der Aufloesungsschicht."""


class RbacCatalogError(RbacResolverError):
    """Start-Check: Code-Katalog ist in der DB nicht (vollstaendig) vorhanden."""


#: Scope-Rang fuer die Weitest-Auswahl. Hoeher = weiter.
_SCOPE_RANK: Dict[Optional[str], int] = {None: 0, "eigene": 1, "alle": 2}


def _widest(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Gibt den weiteren der beiden Scopes zurueck (alle > eigene > None)."""
    return a if _SCOPE_RANK.get(a, 0) >= _SCOPE_RANK.get(b, 0) else b


@dataclass(frozen=True)
class PersonPolicy:
    """
    Aufgeloeste, effektive Rechte einer Person. Rein lesendes DTO.

    roles         — aktive Rollen-Codes der Person.
    capabilities  — Abbildung Faehigkeits-Code -> weitester Scope
                    ('alle' | 'eigene' | None). Enthaelt genau die Faehigkeiten,
                    fuer die >=1 aktiver Grant existiert.
    """

    person_id: int
    roles: FrozenSet[str] = field(default_factory=frozenset)
    capabilities: Dict[str, Optional[str]] = field(default_factory=dict)

    def can(self, capability_code: str) -> bool:
        """True, wenn die Person die Faehigkeit besitzt (>=1 aktiver Grant)."""
        return capability_code in self.capabilities

    def scope(self, capability_code: str) -> Optional[str]:
        """
        Weitester Scope der Faehigkeit ('alle'/'eigene'/None). ACHTUNG: None
        bedeutet sowohl 'nicht vorhanden' ALS AUCH 'vorhanden ohne Scope' —
        zur Unterscheidung can() verwenden.
        """
        return self.capabilities.get(capability_code)


class RbacResolver:
    """Rein lesende Rechte-Aufloesung ueber person_role + rbac_grant."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    def resolve(self, person_id: int) -> PersonPolicy:
        """
        Loest die effektiven Rechte der Person auf. Unbekannte Person / keine
        aktive Rolle => leere Policy (default-deny), KEIN Fehler.
        """
        role_rows = self._con.execute(
            "SELECT role_code FROM person_role "
            "WHERE person_id = ? AND revoked_at IS NULL",
            (person_id,),
        ).fetchall()
        roles = frozenset(r["role_code"] for r in role_rows)
        if not roles:
            return PersonPolicy(person_id=person_id)

        placeholders = ",".join("?" for _ in roles)
        grant_rows = self._con.execute(
            "SELECT capability_code, scope FROM rbac_grant "
            "WHERE revoked_at IS NULL AND role_code IN (%s)" % placeholders,
            tuple(roles),
        ).fetchall()

        caps: Dict[str, Optional[str]] = {}
        for g in grant_rows:
            code = g["capability_code"]
            if code in caps:
                caps[code] = _widest(caps[code], g["scope"])
            else:
                caps[code] = g["scope"]

        return PersonPolicy(
            person_id=person_id, roles=roles, capabilities=caps)

    def can(self, person_id: int, capability_code: str) -> bool:
        """Bequemlichkeit: resolve(person).can(capability)."""
        return self.resolve(person_id).can(capability_code)

    def scope_for(self, person_id: int, capability_code: str) -> Optional[str]:
        """Bequemlichkeit: resolve(person).scope(capability)."""
        return self.resolve(person_id).scope(capability_code)


def verify_catalog_present(con: sqlite3.Connection) -> None:
    """
    Start-Check (Grundregel 1): jede Rolle/Faehigkeit aus dem Code-Katalog
    (catalog.py) MUSS in der DB geseedet sein. Richtung Code ⊆ DB; die DB darf
    voraus sein (das ist zulaessig). Fehlt etwas -> harter, handlungsleitender
    RbacCatalogError (Hinweis auf 'python -m management.migrate'), niemals ein
    stiller Durchgang.
    """
    try:
        db_roles = {
            r[0] for r in con.execute("SELECT code FROM rbac_role").fetchall()
        }
        db_caps = {
            r[0]
            for r in con.execute("SELECT code FROM rbac_capability").fetchall()
        }
    except sqlite3.OperationalError as exc:
        raise RbacCatalogError(
            "RBAC-Tabellen fehlen (%s). Migration ausstehend? "
            "'python -m management.migrate' ausfuehren." % exc
        )

    missing_roles = sorted(catalog.ROLE_CODES - db_roles)
    missing_caps = sorted(catalog.CAPABILITY_CODES - db_caps)
    if missing_roles or missing_caps:
        parts: List[str] = []
        if missing_roles:
            parts.append("Rollen fehlen: %s" % ", ".join(missing_roles))
        if missing_caps:
            parts.append("Faehigkeiten fehlen: %s" % ", ".join(missing_caps))
        raise RbacCatalogError(
            "Code-Katalog nicht vollstaendig in der DB — %s. Es fehlt eine "
            "Seed-Migration: 'python -m management.migrate' ausfuehren."
            % "; ".join(parts)
        )

    logger.debug(
        "RBAC-Katalog-Check ok: %d Rollen, %d Faehigkeiten aus dem Code in der "
        "DB vorhanden (DB fuehrt %d/%d).",
        len(catalog.ROLE_CODES), len(catalog.CAPABILITY_CODES),
        len(db_roles), len(db_caps),
    )
