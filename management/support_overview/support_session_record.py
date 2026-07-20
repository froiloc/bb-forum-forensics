# =============================================================================
# management/support_overview/support_session_record.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Reines Lese-DTO (frozen dataclass) EINER rekonstruierten Support-Sitzung
#   fuer die Support-Sitzungs-Uebersicht/-Historie (Build 330). Eigene Datei
#   gemaess Grundregel 10 (jede Klasse in eine eigene Datei; mc 2026-07-07).
#
#   Eine Sitzung wird aus BIS ZU ZWEI audit_log-Belegen zusammengesetzt:
#     - SUPPORT_SESSION_STARTED  -> supporter_id, started_at   (Anlage)
#     - SUPPORT_SESSION_ENDED    -> ended_at, duration_sec[, reason] (Ende)
#   Verknuepfungsschluessel ist content.session_id (Beleg: die drei Schreibpfade
#   in support_sessions_repo.start()/end()/close_orphans() legen session_id in
#   JEDEN Payload). target_id taugt NICHT als Schluessel, da er bei STARTED die
#   subject_id, bei ENDED die session_id traegt (belegte Asymmetrie).
#
# GRUNDREGEL 1 (kein Beleg still uebersprungen): Auch UNVOLLSTAENDIGE Sitzungen
#   werden als Datensatz gefuehrt und sichtbar gemacht, nie verworfen:
#     - STARTED ohne ENDED  -> status 'offen'
#     - ENDED ohne STARTED  -> status 'herrenlos' (dangling; supporter unbekannt)
#   Zusaetzliche Auffaelligkeiten (z. B. doppeltes ENDED) landen in 'anomaly'.
#
# 'MESSEN, NICHT RECHNEN': duration_sec wird AUSSCHLIESSLICH aus dem ENDED-
#   Payload uebernommen (der ehrliche, geschriebene Beleg). Bei 'offen'/
#   'herrenlos' bleibt duration_sec None — es wird KEIN now-started errechnet.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

from dataclasses import dataclass
from typing import FrozenSet, Optional

# -----------------------------------------------------------------------------
# Status-Vokabular (stabil, maschinenlesbar; die Frontend-Schicht lokalisiert).
# Bewusst deutsch/knapp und konsistent zum uebrigen Management-Vokabular.
# -----------------------------------------------------------------------------
#: Sauber beendete Sitzung (ENDED ohne 'reason').
STATUS_ENDED_CLEAN: str = "beendet"
#: Verwaist per Zeitueberschreitung beendet (ENDED mit reason='orphan_timeout';
#: ended_at == last_heartbeat, System-Aktion). Beleg: close_orphans(), Build 328.
STATUS_ENDED_ORPHAN: str = "orphan_timeout"
#: STARTED vorhanden, ENDED (noch) nicht — Sitzung offen (live ODER Waise, die
#: noch nicht auditiert beendet wurde). Rein audit-basiert (mc 2026-07-07:
#: KEIN Abgleich mit der fluechtigen support_sessions fuer 'live jetzt').
STATUS_OPEN: str = "offen"
#: ENDED ohne zugehoeriges STARTED (im gelesenen Fenster) — muss SICHTBAR sein.
STATUS_DANGLING: str = "herrenlos"

#: Alle gueltigen Status-Werte (fuer Tests/Validierung).
ALL_STATUSES: FrozenSet[str] = frozenset(
    {STATUS_ENDED_CLEAN, STATUS_ENDED_ORPHAN, STATUS_OPEN, STATUS_DANGLING}
)

# -----------------------------------------------------------------------------
# Anomalie-Codes (maschinenlesbar). None = unauffaellig. Sitzungen mit Anomalie
# werden NICHT verworfen (Grundregel 1), sondern markiert angezeigt.
# -----------------------------------------------------------------------------
ANOMALY_DOUBLE_STARTED: str = "doppeltes_started"
ANOMALY_DOUBLE_ENDED: str = "doppeltes_ended"
ANOMALY_MISSING_SESSION_ID: str = "fehlende_session_id_im_payload"


@dataclass(frozen=True)
class SupportSessionRecord:
    """
    Eine aus dem audit_log rekonstruierte Support-Sitzung (reines Lese-DTO).

    Identitaet / Fall:
        session_id   — support_sessions.id aus content.session_id (Schluessel).
                       0 nur im Ausnahmefall fehlender session_id (mit anomaly).
        subject_id      — betroffener Forum-Benutzer (aus dem Payload).
        username     — Forum-Benutzername aus cases.username (None, falls kein
                       cases-Eintrag existiert — Zeile bleibt trotzdem sichtbar).

    Supporter (nur aus STARTED bekannt; bei 'herrenlos' None):
        supporter_id, supporter_system_username, supporter_display_name.

    Zeit/Dauer (jeweils der GESCHRIEBENE Beleg, kein errechneter Wert):
        started_at   — Unix-Sekunden aus STARTED-Payload (None bei 'herrenlos').
        ended_at     — Unix-Sekunden aus ENDED-Payload  (None bei 'offen').
        duration_sec — aus ENDED-Payload (None, wenn kein ENDED vorliegt).
        reason       — ENDED-Grund; None = sauberes Ende, 'orphan_timeout' =
                       System-Zeitueberschreitung.

    Status (abgeleitet, siehe STATUS_*): beendet / orphan_timeout / offen /
        herrenlos.

    Audit-Belegverweise (fuer Nachpruefbarkeit — 'welche Zeile im audit_log'):
        started_seq, ended_seq  — audit_log.seq der jeweiligen Belegzeile.
        started_ts,  ended_ts   — audit_log.ts (Schreibzeitpunkt der Belegzeile;
                                   bei orphan_timeout weicht ended_ts bewusst von
                                   ended_at ab: ts = spaetere Schreibung, ended_at
                                   = ehrlicher letzter Heartbeat).
        started_actor_id, ended_actor_id — audit_log.actor_id (None = System).

    Auffaelligkeit:
        anomaly      — None oder ein ANOMALY_*-Code (z. B. doppeltes ENDED).
    """
    session_id: int
    subject_id: int
    username: Optional[str]

    supporter_id: Optional[int]
    supporter_system_username: Optional[str]
    supporter_display_name: Optional[str]

    started_at: Optional[int]
    ended_at: Optional[int]
    duration_sec: Optional[int]
    reason: Optional[str]

    status: str

    started_seq: Optional[int]
    ended_seq: Optional[int]
    started_ts: Optional[int]
    ended_ts: Optional[int]
    started_actor_id: Optional[int]
    ended_actor_id: Optional[int]

    anomaly: Optional[str] = None
