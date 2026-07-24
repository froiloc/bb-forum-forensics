# =============================================================================
# management/ad_sync/sync_plan.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Abgleich (Build 501)
# =============================================================================
# Zweck:
#   REINE Planungslogik des AD-Abgleichs (Bauplan Build501_502 §5) — kein I/O,
#   keine DB, keine Uhr; vollstaendig in pytest pruefbar. Aus der AD-Antwort
#   (Mitglieder der Ermittler-Gruppe) und dem person-Bestand wird ein
#   SyncPlan mit vier disjunkten Mengen gebildet:
#
#     create                 — im AD, nicht in person: Neuaufnahme als
#                              investigator (mc 2026-07-24, E4).
#     rename                 — AKTIVER person-Satz, displayName im AD weicht ab:
#                              protokollierte Namensaenderung.
#     deactivate_candidates  — AKTIVER person-Satz, sam nicht (mehr) im AD:
#                              KANDIDAT — vollzogen wird NUR nach woertlicher
#                              Supervisor-Bestaetigung "Entfernen" (§6).
#     reactivate_candidates  — INAKTIVER person-Satz, sam wieder im AD:
#                              KANDIDAT — Bestaetigung "Reaktivieren" (§6),
#                              da historische Rollen wieder wirksam wuerden.
#
# Bewusste Entwurfsentscheidungen:
#   - SAMAccountName ist AD-seitig NICHT case-sensitiv (Beleg: ad_directory.py,
#     Build 462). Der Abgleich vergleicht daher case-insensitiv; die KANONISCHE
#     Schreibweise ist fuer Bestandskonten die der DB (system_username ist die
#     forensische Identitaet und wird NIE umgeschrieben), fuer Neue die des AD.
#   - Leerer displayName im AD faellt auf den sam zurueck (person.display_name
#     darf nicht leer sein — Guard in person_repo.create).
#   - GLITCH-SCHUTZ (Bauplan §6): eine LEERE AD-Antwort bricht die Planung mit
#     AdSyncPlanError ab — sie wuerde sonst JEDEN Ermittler zum Entfernungs-
#     Kandidaten machen. Ebenso brechen doppelte sams (case-insensitiv
#     kollidierend) in der AD-Antwort die Planung ab: der Abgleich waere
#     mehrdeutig. NIE stilles Weiterlaufen (Grundregel 1).
#   - Inaktive person-Saetze, deren sam NICHT im AD ist, sind KEIN Kandidat —
#     sie sind der bereits vollzogene Soll-Zustand (unchanged_inactive).
#
# Version: v0.8.501 · Build: 501 · 2026-07-24
# =============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List


class AdSyncPlanError(Exception):
    """Planung nicht moeglich (leere/mehrdeutige AD-Antwort o. ae.)."""


@dataclass
class SyncPlan:
    """Ergebnis der Planung — vier disjunkte Aenderungsmengen + Zaehler."""

    #: [{sam, display_name}] — Neuaufnahme als investigator.
    create: List[Dict[str, Any]] = field(default_factory=list)
    #: [{person_id, system_username, display_name_alt, display_name_neu}]
    rename: List[Dict[str, Any]] = field(default_factory=list)
    #: [{person_id, system_username, display_name}] — nur nach "Entfernen".
    deactivate_candidates: List[Dict[str, Any]] = field(default_factory=list)
    #: [{person_id, system_username, display_name, display_name_ad}]
    #  display_name_ad: aktueller AD-Anzeigename (kann von der DB abweichen;
    #  der Executor zieht ihn nach der Reaktivierung protokolliert nach).
    reactivate_candidates: List[Dict[str, Any]] = field(default_factory=list)
    #: Aktive Bestandskonten ohne Abweichung.
    unchanged: int = 0
    #: Inaktive Bestandskonten, die (weiterhin) nicht im AD sind — Soll-Zustand.
    unchanged_inactive: int = 0

    def counts(self) -> Dict[str, int]:
        """Zaehler fuer Belege/Anzeige (AD_SYNC_RUN-Payload)."""
        return {
            "create": len(self.create),
            "rename": len(self.rename),
            "deactivate_candidates": len(self.deactivate_candidates),
            "reactivate_candidates": len(self.reactivate_candidates),
            "unchanged": self.unchanged,
            "unchanged_inactive": self.unchanged_inactive,
        }

    def as_dict(self) -> Dict[str, Any]:
        """JSON-faehige Form (CLI --json, spaeter /api/adsync in Build 502)."""
        return {
            "create": self.create,
            "rename": self.rename,
            "deactivate_candidates": self.deactivate_candidates,
            "reactivate_candidates": self.reactivate_candidates,
            "counts": self.counts(),
        }


class SyncPlanner:
    """Bildet aus AD-Mitgliedern und person-Bestand den SyncPlan (rein)."""

    @staticmethod
    def build(ad_members: List[Dict[str, Any]],
              persons: List[Dict[str, Any]]) -> SyncPlan:
        """
        ad_members — [{sam, display_name}] (LdapGroupReader.fetch_members
                     oder Mock; display_name darf leer sein).
        persons    — person-Saetze wie aus PersonRepo.list_persons (muessen
                     id, system_username, display_name, is_active enthalten;
                     fehlendes is_active gilt als aktiv — Altbestand).
        """
        if not ad_members:
            raise AdSyncPlanError(
                "AD-Antwort enthaelt KEINE Mitglieder — Abgleich abgebrochen. "
                "Eine leere Ermittler-Gruppe ist mit ueberwaeltigender "
                "Wahrscheinlichkeit ein Glitch oder eine Fehlkonfiguration "
                "(Gruppe/Suchbasis pruefen); ein Vollzug wuerde ALLE "
                "Ermittler zu Entfernungs-Kandidaten machen.")

        # AD-Antwort case-insensitiv indizieren; Kollisionen sind ein Abbruch.
        ad_index: Dict[str, Dict[str, Any]] = {}
        for m in ad_members:
            sam = str(m.get("sam", "")).strip()
            if not sam:
                raise AdSyncPlanError(
                    "AD-Mitglied ohne sAMAccountName in der Antwort — "
                    "Abgleich abgebrochen (Eintrag: %r)." % (m,))
            key = sam.lower()
            if key in ad_index:
                raise AdSyncPlanError(
                    "Mehrdeutige AD-Antwort: sAMAccountName %r kommt "
                    "mehrfach vor (%r / %r) — Abgleich abgebrochen."
                    % (sam, ad_index[key]["sam"], sam))
            display = str(m.get("display_name") or "").strip()
            # Leerer Anzeigename faellt auf den sam zurueck (Kopfkommentar).
            ad_index[key] = {"sam": sam, "display_name": display or sam}

        plan = SyncPlan()
        seen_ad_keys = set()

        for p in persons:
            key = str(p["system_username"]).strip().lower()
            active = bool(p.get("is_active", True))
            ad = ad_index.get(key)
            if ad is not None:
                seen_ad_keys.add(key)
                if active:
                    if ad["display_name"] != p["display_name"]:
                        plan.rename.append({
                            "person_id": int(p["id"]),
                            "system_username": p["system_username"],
                            "display_name_alt": p["display_name"],
                            "display_name_neu": ad["display_name"],
                        })
                    else:
                        plan.unchanged += 1
                else:
                    plan.reactivate_candidates.append({
                        "person_id": int(p["id"]),
                        "system_username": p["system_username"],
                        "display_name": p["display_name"],
                        "display_name_ad": ad["display_name"],
                    })
            else:
                if active:
                    plan.deactivate_candidates.append({
                        "person_id": int(p["id"]),
                        "system_username": p["system_username"],
                        "display_name": p["display_name"],
                    })
                else:
                    plan.unchanged_inactive += 1

        # Neuaufnahmen: AD-Mitglieder ohne person-Satz, in AD-Reihenfolge
        # (deterministisch nach sam sortiert fuer stabile Belege/Tests).
        for key in sorted(k for k in ad_index if k not in seen_ad_keys):
            ad = ad_index[key]
            plan.create.append({"sam": ad["sam"],
                                "display_name": ad["display_name"]})
        return plan
