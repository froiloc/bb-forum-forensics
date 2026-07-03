# =============================================================================
# management/dashboard/dashboard_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   NUR-LESENDES Read-Model fuer das Ampel-Dashboard (Tag 3). Aggregiert je
#   Fall die Rohsignale aus coordinator.db:
#     - cases            : Status, Prioritaet, Zuweisung, Freigabe, Seitenzahl
#     - case_events      : Ereignis-Anzahl, letzte Ereignisart + -zeit
#                          (Build 313; NUR Art/Zeit/Anzahl — KEIN Payload/Text)
#     - support_sessions : Live-Support-Praesenz (aktiv, Anzahl) (Build 311)
#   und leitet daraus eine Ampel (rot/gelb/gruen) ab.
#
#   Zugriffs-Stil: DIREKTE Verbindung auf coordinator.db mit UNQUALIFIZIERTEN
#   Tabellennamen — konsistent mit CasesRepo/CaseEventsRepo (Management-Seite),
#   NICHT der 'cdb.'-attached-Stil aus db/coordinator_db.py (Server-Runtime).
#   (Beleg: management/cases/cases_repo.py, management/case_events/
#    case_events_repo.py.)
#
#   KEIN Schreibpfad, KEIN CoordinatorWriter, KEINE Migration, KEIN Anfassen
#   von evidence_/forensic_/assets_-DB. coordinator.db ist ohnehin nur-lesend
#   (Produktivbetrieb-Regel ab 2026-07-01). Damit traegt dieser Build KEIN
#   Datenverlust-Risiko.
#
#   Der Eintragstext manueller Zeitstrahl-Ereignisse (case_events.payload)
#   wird BEWUSST NICHT gelesen — das Dashboard braucht nur Art/Zeit/Anzahl.
#   (Sensibilitaetsregel analog cases.note; Beleg B7 v0.8 Paragraph 8.5.)
#
# ---------------------------------------------------------------------------
# AMPEL-SEMANTIK (mc 2026-07-03 BESTAETIGT):
#   Schwellen amber=7 / red=21 Tage als VORGABE, ab Build 315 aus der
#   Konfiguration (config.yaml: dashboard.ampel.amber_idle_days /
#   red_idle_days) ueberschreibbar — NICHT mehr hartkodiert. Fehlt der
#   Abschnitt, greifen die Vorgabewerte (nicht-stiller Log-Hinweis).
#   Support-Praesenz fliesst BEWUSST NICHT in die Farbe (eigenes Abzeichen).
#   Sortierung ab Build 315: Ampel-Schwere zuerst (rot>gelb>gruen), dann
#   Prioritaet, dann letzte Aktivitaet, dann user_id.
# ---------------------------------------------------------------------------
#
# Beleg: Bauplan B7 v1.0 Paragraph 10, Projektgespraech/mc 2026-07-02 (Semantik)
#        und mc 2026-07-03 (Schwellen aus Config, Sortierung Ampel-zuerst).
# Version: v0.7.315 · Build: 315 · 2026-07-03
# =============================================================================

import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

# Autoritative Stale-Schwelle der Support-Praesenz (kein Magic-Number-Duplikat).
from db.coordinator_db import DEFAULT_SUPPORT_STALE_SEC

logger = logging.getLogger(__name__)

_SECONDS_PER_DAY = 86400

# Ampel-Werte (stabiles Vokabular; deutsch, konsistent mit UI-Sprache).
AMPEL_ROT = "rot"
AMPEL_GELB = "gelb"
AMPEL_GRUEN = "gruen"

# Schwere-Rang fuer die Sortierung (rot am dringlichsten). Build 315:
# 'Ampel-Schwere zuerst' ist die vom Auftraggeber bestaetigte Reihenfolge.
_AMPEL_RANK = {AMPEL_ROT: 0, AMPEL_GELB: 1, AMPEL_GRUEN: 2}

# Tabellen, die das Read-Model zwingend braucht. Fehlen sie, wird NICHT still
# degradiert, sondern mit handlungsleitender Meldung abgebrochen (Grundregel 1).
REQUIRED_TABLES = ("cases", "case_events", "support_sessions", "investigators")


class DashboardSchemaError(Exception):
    """
    Erforderliche coordinator.db-Tabelle fehlt (z. B. case_events ohne M004).
    Traegt eine handlungsleitende Meldung (welche Tabelle, was zu tun ist).
    """


class DashboardConfigError(Exception):
    """Ungueltige dashboard.ampel-Konfiguration (z. B. amber >= red)."""


@dataclass(frozen=True)
class AmpelThresholds:
    """
    Schwellen fuer die Ampel-Ableitung. Vorgabe amber=7 / red=21 (mc
    2026-07-02); ab Build 315 aus config.yaml (dashboard.ampel.*)
    ueberschreibbar (ampel_thresholds_from_config).

    Felder:
        amber_idle_days — ab so vielen Tagen ohne Fall-Aktivitaet wird ein
                          offener/laufender Fall mindestens GELB.
        red_idle_days   — ab so vielen Tagen ohne Aktivitaet wird er ROT.
    """
    amber_idle_days: int = 7
    red_idle_days: int = 21


#: Vorgabe-Schwellen (greifen, wenn config.yaml keinen dashboard.ampel-Block hat).
DEFAULT_AMPEL_THRESHOLDS = AmpelThresholds()


def ampel_thresholds_from_config(cfg: Any) -> AmpelThresholds:
    """
    Baut AmpelThresholds aus der Konfiguration. 'cfg' ist ein Objekt mit einer
    get(dotted_key, default)-Methode (z. B. core.config_loader.ConfigLoader).

    Gelesen werden dashboard.ampel.amber_idle_days und .red_idle_days. Fehlt
    ein Wert, wird die Vorgabe (7 bzw. 21) verwendet — und das NICHT still,
    sondern per Log-Hinweis vermerkt (Grundregel 1). Ungueltige Werte
    (nicht-ganzzahlig, amber < 1, oder red <= amber) fuehren zu einem harten,
    handlungsleitenden DashboardConfigError statt zu stiller Fehlkonfiguration.

    Beleg: mc 2026-07-03 (Schwellen konfigurierbar, Vorgabe 7/21).
    """
    default = AmpelThresholds()
    if cfg is None:
        return default

    raw_amber = cfg.get("dashboard.ampel.amber_idle_days", None)
    raw_red = cfg.get("dashboard.ampel.red_idle_days", None)

    used_defaults = []
    if raw_amber is None:
        raw_amber = default.amber_idle_days
        used_defaults.append("amber_idle_days=%d" % raw_amber)
    if raw_red is None:
        raw_red = default.red_idle_days
        used_defaults.append("red_idle_days=%d" % raw_red)

    try:
        amber = int(raw_amber)
        red = int(raw_red)
    except (TypeError, ValueError):
        raise DashboardConfigError(
            "dashboard.ampel-Schwellen muessen ganze Zahlen sein "
            "(amber_idle_days=%r, red_idle_days=%r). Bitte config.yaml "
            "korrigieren." % (raw_amber, raw_red)
        )

    if amber < 1 or red <= amber:
        raise DashboardConfigError(
            "Ungueltige Ampel-Schwellen: amber_idle_days (%d) muss >= 1 und "
            "echt kleiner als red_idle_days (%d) sein. Bitte config.yaml unter "
            "dashboard.ampel.* korrigieren." % (amber, red)
        )

    if used_defaults:
        logger.info(
            "dashboard.ampel: Vorgabewerte verwendet (%s) — anpassbar in "
            "config.yaml unter dashboard.ampel.*.", ", ".join(used_defaults)
        )
    return AmpelThresholds(amber_idle_days=amber, red_idle_days=red)


# Reason-Codes (maschinenlesbar; die UI kann sie spaeter lokalisieren).
REASON_CLOSED = "abgeschlossen"
REASON_APPROVED = "freigegeben"
REASON_OPEN_UNASSIGNED = "offen_nicht_zugewiesen"
REASON_IDLE_LONG = "inaktiv_lang"
REASON_IDLE_MEDIUM = "inaktiv_mittel"
REASON_ACTIVE = "aktiv"


def classify_ampel(
    *,
    status: str,
    assigned_to: Optional[int],
    last_activity_at: int,
    now: int,
    thresholds: AmpelThresholds = DEFAULT_AMPEL_THRESHOLDS,
) -> Tuple[str, str]:
    """
    Reine (seiteneffektfreie) Ableitung der Ampel aus den Fall-Rohsignalen.
    Regelreihenfolge (mc 2026-07-02 bestaetigt; erste Regel greift):

      1. status 'closed'            -> GRUEN (abgeschlossen)
      2. status 'approved'          -> GRUEN (freigegeben)
      3. status 'open' & unzugewiesen -> ROT (offen_nicht_zugewiesen)
      4. offen/laufend & Inaktivitaet:
           idle >= red_idle_days    -> ROT  (inaktiv_lang)
           idle >= amber_idle_days  -> GELB (inaktiv_mittel)
      5. sonst                      -> GRUEN (aktiv)

    Support-Praesenz fliesst BEWUSST NICHT in die Farbe ein — sie ist ein
    orthogonaler Live-Zustand und wird im Dashboard als eigenes Abzeichen
    (support_active/support_count) gefuehrt (mc 2026-07-02 bestaetigt).

    Gibt (ampel, reason_code) zurueck.
    """
    if status == "closed":
        return AMPEL_GRUEN, REASON_CLOSED
    if status == "approved":
        return AMPEL_GRUEN, REASON_APPROVED
    if status == "open" and assigned_to is None:
        return AMPEL_ROT, REASON_OPEN_UNASSIGNED

    idle_days = max(0, now - last_activity_at) / _SECONDS_PER_DAY
    if idle_days >= thresholds.red_idle_days:
        return AMPEL_ROT, REASON_IDLE_LONG
    if idle_days >= thresholds.amber_idle_days:
        return AMPEL_GELB, REASON_IDLE_MEDIUM
    return AMPEL_GRUEN, REASON_ACTIVE


@dataclass(frozen=True)
class CaseOverview:
    """
    Aggregierte Uebersicht eines Falls fuer das Dashboard. Reines Lese-DTO.

    Rohsignale (aus der DB):
        user_id, username, status, priority, assigned_to,
        assigned_system_username, assigned_display_name, has_note,
        approved_at, total_pages_scraped, created_at, updated_at,
        event_count, last_event_kind, last_event_at,
        support_active, support_count, support_since
    Abgeleitet:
        last_activity_at — max(updated_at, last_event_at)
        ampel, ampel_reason — abgeleitet (siehe classify_ampel)
    """
    user_id: int
    username: str
    status: str
    priority: int
    assigned_to: Optional[int]
    assigned_system_username: Optional[str]
    assigned_display_name: Optional[str]
    has_note: bool
    approved_at: Optional[int]
    total_pages_scraped: Optional[int]
    created_at: int
    updated_at: int
    event_count: int
    last_event_kind: Optional[str]
    last_event_at: Optional[int]
    support_active: bool
    support_count: int
    support_since: Optional[int]
    last_activity_at: int
    ampel: str
    ampel_reason: str


class DashboardRepo:
    """NUR-LESENDES Aggregat ueber coordinator.db fuer das Ampel-Dashboard."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    def _check_required_tables(self) -> None:
        """
        Prueft VOR der Aggregatabfrage, ob alle Pflichttabellen existieren.
        Fehlt eine (typisch: case_events ohne M004), wird statt eines rohen
        sqlite3.OperationalError ein handlungsleitender DashboardSchemaError
        geworfen, der die fehlende Tabelle nennt und auf den Migrationslauf
        verweist (mc 2026-07-03: 'handlungsleitende Fehlermeldungen').
        """
        have = {
            row[0] for row in self._con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = [t for t in REQUIRED_TABLES if t not in have]
        if missing:
            raise DashboardSchemaError(
                "Erforderliche Tabelle(n) fehlen in coordinator.db: %s. "
                "Bitte ausstehende Migrationen anwenden: "
                "python -m management.migrate" % ", ".join(missing)
            )

    def list_case_overview(
        self,
        *,
        thresholds: AmpelThresholds = DEFAULT_AMPEL_THRESHOLDS,
        support_stale_sec: int = DEFAULT_SUPPORT_STALE_SEC,
        now: Optional[int] = None,
    ) -> List[CaseOverview]:
        """
        Liefert je Fall eine CaseOverview. 'now' ist injizierbar (Tests,
        deterministische Inaktivitaets-/Praesenz-Berechnung); Standard ist die
        Systemzeit.

        Sortierung (mc 2026-07-03): Ampel-Schwere zuerst (rot > gelb >
        gruen), dann Prioritaet aufsteigend (1 zuerst), dann letzte Aktivitaet
        absteigend, dann user_id — 'was am dringlichsten ist, steht oben'.
        'thresholds' stammt in der CLI aus config.yaml
        (ampel_thresholds_from_config); Vorgabe 7/21.

        Eine einzige Aggregatabfrage (kein N+1): case_events- und
        support_sessions-Kennzahlen kommen aus abgeleiteten Teilmengen bzw.
        einer korrelierten Unterabfrage fuer die letzte Ereignisart.
        """
        self._check_required_tables()

        now = int(time.time()) if now is None else int(now)
        sup_threshold = now - support_stale_sec

        sql = """
        SELECT
            c.user_id                                   AS user_id,
            c.username                                  AS username,
            c.status                                    AS status,
            c.priority                                  AS priority,
            c.assigned_to                               AS assigned_to,
            i.system_username                           AS assigned_system_username,
            i.display_name                              AS assigned_display_name,
            CASE WHEN c.note IS NOT NULL AND c.note <> ''
                 THEN 1 ELSE 0 END                      AS has_note,
            c.approved_at                               AS approved_at,
            c.total_pages_scraped                       AS total_pages_scraped,
            c.created_at                                AS created_at,
            c.updated_at                                AS updated_at,
            COALESCE(ev.event_count, 0)                 AS event_count,
            ev.last_event_at                            AS last_event_at,
            (SELECT e2.event_kind FROM case_events e2
              WHERE e2.user_id = c.user_id
              ORDER BY e2.created_at DESC, e2.id DESC
              LIMIT 1)                                  AS last_event_kind,
            COALESCE(sp.support_count, 0)               AS support_count,
            sp.support_since                            AS support_since
        FROM cases c
        LEFT JOIN investigators i
               ON i.id = c.assigned_to
        LEFT JOIN (
            SELECT user_id,
                   COUNT(*)        AS event_count,
                   MAX(created_at) AS last_event_at
            FROM case_events
            GROUP BY user_id
        ) ev ON ev.user_id = c.user_id
        LEFT JOIN (
            SELECT user_id,
                   COUNT(*)        AS support_count,
                   MIN(started_at) AS support_since
            FROM support_sessions
            WHERE ended_at IS NULL AND last_heartbeat >= ?
            GROUP BY user_id
        ) sp ON sp.user_id = c.user_id
        """
        rows = self._con.execute(sql, (sup_threshold,)).fetchall()

        out: List[CaseOverview] = []
        for r in rows:
            updated_at = int(r["updated_at"])
            last_event_at = r["last_event_at"]
            last_event_at = int(last_event_at) if last_event_at is not None else None
            last_activity_at = max(updated_at, last_event_at or 0)

            support_count = int(r["support_count"])
            support_active = support_count > 0

            ampel, reason = classify_ampel(
                status=r["status"],
                assigned_to=r["assigned_to"],
                last_activity_at=last_activity_at,
                now=now,
                thresholds=thresholds,
            )

            out.append(CaseOverview(
                user_id=int(r["user_id"]),
                username=r["username"],
                status=r["status"],
                priority=int(r["priority"]),
                assigned_to=r["assigned_to"],
                assigned_system_username=r["assigned_system_username"],
                assigned_display_name=r["assigned_display_name"],
                has_note=bool(r["has_note"]),
                approved_at=r["approved_at"],
                total_pages_scraped=r["total_pages_scraped"],
                created_at=int(r["created_at"]),
                updated_at=updated_at,
                event_count=int(r["event_count"]),
                last_event_kind=r["last_event_kind"],
                last_event_at=last_event_at,
                support_active=support_active,
                support_count=support_count,
                support_since=(int(r["support_since"])
                               if r["support_since"] is not None else None),
                last_activity_at=last_activity_at,
                ampel=ampel,
                ampel_reason=reason,
            ))

        # Sortierung (mc 2026-07-03): Ampel-Schwere zuerst (rot vor gelb vor
        # gruen), dann Prioritaet aufsteigend, dann letzte Aktivitaet
        # absteigend, dann user_id — 'was am dringlichsten ist, steht oben'.
        out.sort(key=lambda o: (_AMPEL_RANK.get(o.ampel, 99), o.priority,
                                -o.last_activity_at, o.user_id))
        return out
