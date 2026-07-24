# =============================================================================
# management/ad_sync/sync_executor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Abgleich (Build 501)
# =============================================================================
# Zweck:
#   Vollzugsschicht des AD-Abgleichs (Bauplan Build501_502 §5/§6). Nimmt den
#   SyncPlan (sync_plan.py) und vollzieht ihn AUSSCHLIESSLICH ueber die
#   bestehenden auditierten Schreibpfade (CoordinatorWriter: Write+Audit in
#   EINER Transaktion — Grundregel 1, kein Write ohne Beleg):
#
#     Neuaufnahme      — PersonRepo.create (INVESTIGATOR_CREATED, Flag
#                        is_investigator=1) + RbacRepo.assign_role
#                        'investigator' (ROLE_ASSIGNED) — mc 2026-07-24, E4.
#     Namensaenderung  — PersonRepo.update (INVESTIGATOR_UPDATED, Diff
#                        alt->neu im Beleg).
#     Deaktivierung    — NUR nach WOERTLICHER Bestaetigung "Entfernen"
#                        (Glitch-Schutz, mc 2026-07-24); PersonRepo.deactivate
#                        (PERSON_DEACTIVATED). NIE ein DELETE.
#     Abbruch          — der protokollierte Abbruch der Entfernen-Frage:
#                        eigener Beleg PERSON_DEACTIVATION_ABORTED, KEINE
#                        Datenaenderung.
#     Reaktivierung    — Bestaetigung "Reaktivieren" (historische Rollen
#                        werden wieder wirksam); PersonRepo.reactivate
#                        (PERSON_REACTIVATED); ein abweichender AD-Anzeigename
#                        wird anschliessend protokolliert nachgezogen.
#     Lauf-Klammer     — EIN Beleg AD_SYNC_RUN je Abgleich-Lauf mit Zaehlern
#                        und Quellgruppe; auch "keine Abweichungen" ist eine
#                        Erkenntnis und wird belegt.
#
# Bewusste Entwurfsentscheidungen:
#   - Die Mitgliederquelle (provider) ist INJIZIERBAR (Muster F4/identity.py):
#     Betrieb = LdapGroupReader (live), Tests = Mock. Verlangt werden nur
#     .fetch_members() und .target_group.
#   - Die Bestaetigungsworte werden HIER geprueft (exakter Stringvergleich,
#     KEINE Normalisierung: "entfernen" != "Entfernen") — nie nur in einer
#     Oberflaeche. Das getippte Wort wandert in den Beleg (meta).
#   - Vollzug je Person einzeln (kein Sammel-Commit ueber alle): faellt ein
#     Schritt, sind die vorherigen Schritte einzeln belegt und der Fehler
#     bricht den Lauf sichtbar ab (kein stilles Ueberspringen).
#
# Version: v0.8.501 · Build: 501 · 2026-07-24
# =============================================================================

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.person.person_repo import PersonRepo
from management.rbac.rbac_repo import RbacRepo
from management.ad_sync.sync_plan import SyncPlan, SyncPlanner

logger = logging.getLogger(__name__)

#: Rolle fuer Neuaufnahmen (mc 2026-07-24, E4).
NEW_MEMBER_ROLE = "investigator"

#: Woertliche Bestaetigungen (mc 2026-07-24: "Eingabe des Wortes 'Entfernen'").
CONFIRM_DEACTIVATE = "Entfernen"
CONFIRM_REACTIVATE = "Reaktivieren"

#: Standard-Begruendung der Deaktivierung durch den AD-Abgleich.
DEFAULT_DEACTIVATE_REASON = (
    "Nicht mehr im Active-Directory gefuehrt (AD-Abgleich)")


class AdSyncError(Exception):
    """Vollzugsfehler (falsches Bestaetigungswort, unbekannte Person, ...)."""


class SyncExecutor:
    """Vollzieht den AD-Abgleich ueber die auditierten Schreibpfade."""

    def __init__(self, con: sqlite3.Connection, writer: CoordinatorWriter,
                 provider: Any) -> None:
        """
        con      — coordinator.db-Verbindung (M020 angewandt).
        writer   — CoordinatorWriter (Write+Audit atomar).
        provider — Mitgliederquelle: .fetch_members() -> [{sam, display_name}],
                   .target_group -> str. Betrieb: LdapGroupReader; Tests: Mock.
        """
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer
        self._provider = provider
        self._persons = PersonRepo(con, writer)
        self._rbac = RbacRepo(con, writer)

    # ---------------------------------------------------------------- Vorschau
    def preview(self) -> SyncPlan:
        """
        AD lesen und Plan bauen — REIN LESEND, kein Beleg (erst der Vollzug
        belegt; die Vorschau aendert nichts und behauptet nichts).
        Wirft LdapError (Provider) oder AdSyncPlanError (Planner) im
        Fehlerfall — nie ein stilles leeres Ergebnis.
        """
        members = self._provider.fetch_members()
        persons = self._persons.list_persons()
        return SyncPlanner.build(members, persons)

    # ----------------------------------------------------------------- Vollzug
    def apply_automatic(self, plan: SyncPlan, *,
                        actor_id: Optional[int]) -> Dict[str, Any]:
        """
        Vollzieht die NICHT bestaetigungspflichtigen Planteile (Neuaufnahmen,
        Namensaenderungen) und schreibt die AD_SYNC_RUN-Klammer. Kandidaten
        (Deaktivierung/Reaktivierung) werden hier NICHT angefasst — sie
        verlangen die woertliche Einzel-Bestaetigung (§6).
        Gibt eine Zusammenfassung {created, renamed, run_seq} zurueck.
        """
        created: List[Dict[str, Any]] = []
        for c in plan.create:
            self._persons.create(
                c["sam"], c["display_name"],
                is_investigator=True,
                actor_id=actor_id,
                meta={"quelle": "ad_sync",
                      "gruppe": self._provider.target_group},
            )
            person = self._persons.get(system_username=c["sam"])
            if person is None:  # pragma: no cover — direkt nach create
                raise AdSyncError(
                    "Neu angelegter Ermittler %r nicht auffindbar." % c["sam"])
            # Rollenzuweisung ZUSAETZLICH zum Flag (mc 2026-07-24, E4).
            self._rbac.assign_role(
                person["id"], NEW_MEMBER_ROLE,
                actor_id=actor_id,
                meta={"quelle": "ad_sync"},
            )
            created.append({"person_id": person["id"], "sam": c["sam"],
                            "display_name": c["display_name"]})
            logger.info("ad_sync: Neuaufnahme %r (person_id=%s) als %s.",
                        c["sam"], person["id"], NEW_MEMBER_ROLE)

        renamed: List[Dict[str, Any]] = []
        for r in plan.rename:
            self._persons.update(
                id=r["person_id"],
                display_name=r["display_name_neu"],
                actor_id=actor_id,
                meta={"quelle": "ad_sync",
                      "anlass": "displayName-Aenderung im AD"},
            )
            renamed.append(dict(r))
            logger.info("ad_sync: Namensaenderung %r: %r -> %r.",
                        r["system_username"], r["display_name_alt"],
                        r["display_name_neu"])

        run_seq = self._write_run_marker(plan, actor_id=actor_id)
        return {"created": created, "renamed": renamed, "run_seq": run_seq}

    def deactivate(self, system_username: str, *, confirmation: str,
                   actor_id: Optional[int],
                   reason: str = DEFAULT_DEACTIVATE_REASON) -> int:
        """
        Deaktiviert einen Entfernungs-Kandidaten — NUR bei woertlicher
        Bestaetigung "Entfernen" (exakter Vergleich). Gibt die audit_log-seq
        des PERSON_DEACTIVATED-Belegs zurueck.
        """
        if confirmation != CONFIRM_DEACTIVATE:
            raise AdSyncError(
                "Deaktivierung von %r NICHT vollzogen: Bestaetigungswort "
                "%r entspricht nicht dem geforderten Wort %r."
                % (system_username, confirmation, CONFIRM_DEACTIVATE))
        return self._persons.deactivate(
            system_username=system_username,
            reason=reason,
            actor_id=actor_id,
            meta={"quelle": "ad_sync",
                  "bestaetigungswort": confirmation},
        )

    def abort_deactivation(self, system_username: str, *,
                           actor_id: Optional[int],
                           note: str = "") -> int:
        """
        Protokollierter ABBRUCH der Entfernen-Frage (mc 2026-07-24: "Diese
        Frage kann aber auch protokolliert abgebrochen werden."): eigener
        Beleg, KEINE Datenaenderung. note haelt fest, was statt des
        Bestaetigungsworts eingegeben wurde bzw. den Abbruchgrund.
        """
        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = con.execute(
                "SELECT id, system_username, display_name, is_active "
                "FROM person WHERE system_username = ?",
                (system_username,)).fetchone()
            if row is None:
                raise AdSyncError(
                    "Abbruch nicht protokollierbar: unbekannter Ermittler %r."
                    % system_username)
            return {
                "id": int(row["id"]),
                "system_username": row["system_username"],
                "display_name": row["display_name"],
                "is_active": int(row["is_active"]),
                "entscheidung": "abgebrochen",
                "note": (note or "").strip(),
            }

        return self._writer.audited_write(
            do_write=_w,
            event_type=EventType.PERSON_DEACTIVATION_ABORTED,
            actor_id=actor_id,
            target_type="investigator",
            target_id=system_username,
            meta={"quelle": "ad_sync"},
        )

    def reactivate(self, system_username: str, *, confirmation: str,
                   actor_id: Optional[int],
                   display_name_ad: Optional[str] = None) -> int:
        """
        Reaktiviert einen Rueckkehrer — NUR bei woertlicher Bestaetigung
        "Reaktivieren" (historische Rollen werden wieder wirksam, Bauplan §6).
        Weicht der AD-Anzeigename ab, wird er ANSCHLIESSEND protokolliert
        nachgezogen (eigener INVESTIGATOR_UPDATED-Beleg). Gibt die seq des
        PERSON_REACTIVATED-Belegs zurueck.
        """
        if confirmation != CONFIRM_REACTIVATE:
            raise AdSyncError(
                "Reaktivierung von %r NICHT vollzogen: Bestaetigungswort "
                "%r entspricht nicht dem geforderten Wort %r."
                % (system_username, confirmation, CONFIRM_REACTIVATE))
        seq = self._persons.reactivate(
            system_username=system_username,
            actor_id=actor_id,
            meta={"quelle": "ad_sync",
                  "bestaetigungswort": confirmation},
        )
        if display_name_ad:
            person = self._persons.get(system_username=system_username)
            if person is not None and person["display_name"] != display_name_ad:
                self._persons.update(
                    system_username=system_username,
                    display_name=display_name_ad,
                    actor_id=actor_id,
                    meta={"quelle": "ad_sync",
                          "anlass": "displayName-Nachzug bei Reaktivierung"},
                )
        return seq

    # ------------------------------------------------------------------ intern
    def _write_run_marker(self, plan: SyncPlan, *,
                          actor_id: Optional[int]) -> int:
        """AD_SYNC_RUN-Klammer: Zaehler + Quellgruppe (kein Tabellen-Write)."""
        counts = plan.counts()

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            return {"gruppe": self._provider.target_group, "zaehler": counts}

        return self._writer.audited_write(
            do_write=_w,
            event_type=EventType.AD_SYNC_RUN,
            actor_id=actor_id,
            target_type="ad_sync",
            target_id=self._provider.target_group,
            meta=None,
        )
