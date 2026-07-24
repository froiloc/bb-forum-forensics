# =============================================================================
# db/coordinator_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Kapselt alle Zugriffe auf die coordinator.db (ATTACH-Alias: cdb).
#   Liest Ermittler-Stammdaten, Job-Zustände und schreibt Job-Status-Updates.
#
# Besonderheiten:
#   coordinator.db liegt auf einem SMB-Netzlaufwerk (NRW-Cloud) und wird
#   von mehreren Workstations gleichzeitig genutzt. Daher:
#   - WAL-Modus (wird von connection_manager.py beim Öffnen gesetzt)
#   - Retry-Logik: 3 Versuche, 500 ms Pause bei OperationalError
#   - Kurze Timeouts bei einzelnen Operationen
#
# Schreiboperationen:
#   Nur Job-Status-Updates (z.B. 'pending' → 'running').
#   Alle anderen Schreiboperationen (Prioritäten setzen, Zuweisung) obliegen
#   Baustelle 7 (Management-Interface).
#
# Forensische Relevanz:
#   coordinator.db ist kein Beweismittel. Sie koordiniert den Betrieb.
#   Integritätsfehler hier führen zu Betriebsunterbrechungen, nicht zu
#   verfälschten Beweisen.
#
# Abhängigkeiten: sqlite3, time — ausschließlich Stdlib
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Änderungen gegenüber Build 007 (Baustelle 3 — §11.5 Bauplan):
#   - SupportStatusRecord: Neues Dataclass für SSE-Support-Status.
#   - get_support_status(): Liest aktiven Support-Nutzer aus
#     person JOIN scrape_jobs. Gibt SupportStatusRecord zurück.
#     Fehlerbehandlung: Bei Exception → inactive-Status statt Absturz.
# =============================================================================

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)

# Retry-Konfiguration für Netzlaufwerk-Zugriffe
_RETRY_COUNT   = 3
_RETRY_DELAY_S = 0.5   # Sekunden zwischen Versuchen

# Stale-Schwelle für Live-Support-Sitzungen (Build 311): Eine Sitzung ohne
# Heartbeat innerhalb dieser Spanne gilt als inaktiv. Default = 30 s
# (mind. ~3× SSE-Tick; wird ab Build 312 aus der Konfiguration versorgt).
# Beleg: mc 2026-07-01 (Frage 1).
DEFAULT_SUPPORT_STALE_SEC = 30


@dataclass(frozen=True)
class SupportStatusRecord:
    """
    Repräsentiert den aktuellen Support-Verbindungsstatus.

    Wird von get_support_status() zurückgegeben und von forensic_api/events.py
    als SSE-Nutzlast verwendet (§11.5 Bauplan Baustelle 3).

    Felder:
        active    — True wenn mindestens ein Support-Nutzer gerade aktiv ist
        username  — SAMAccountName des am längsten aktiven Supporters (oder None)
        since_ms  — Unix-Timestamp ms seit wann dieser Supporter aktiv ist
                    (None wenn active=False)
        count     — Anzahl gleichzeitig aktiver Support-Sitzungen zum Fall
                    (0 wenn active=False). Build 311.
    """
    active:    bool
    username:  Optional[str]
    since_ms:  Optional[int]
    count:     int = 0


@dataclass(frozen=True)
class InvestigatorRecord:
    """
    Repräsentiert einen Eintrag aus der person-Tabelle (Rolle: Ermittler).

    Felder:
        id               — Primärschlüssel
        system_username  — $USER / SAMAccountName (Format PROD: h012345)
        display_name     — Anzeigename des Ermittlers
        is_investigator  — Hat Ermittler-Rolle
        is_supervisor    — Hat Supervisor-Rolle
        is_support       — Hat Support-Rolle
        created_at       — Unix-Timestamp der Anlage
    """
    id:               int
    system_username:  str
    display_name:     str
    is_investigator:  bool
    is_supervisor:    bool
    is_support:       bool
    created_at:       int


@dataclass(frozen=True)
class JobRecord:
    """
    Repräsentiert einen Eintrag aus der scrape_jobs-Tabelle.

    Felder:
        id            — Primärschlüssel
        subject_id    — Subjekt-ID (numerisch = forum.users.id) des Beschuldigten
        username      — Benutzername des Beschuldigten
        priority      — 1 (höchste) bis 5 (niedrigste)
        status        — 'pending', 'running', 'done', 'failed'
        output_path   — Pfad zur forensic_<uid>.db (gesetzt nach Stage 2)
        created_at    — Unix-Timestamp der Job-Anlage
    """
    id:           int
    subject_id:   int
    username:     str
    priority:     int
    status:       str
    output_path:  Optional[str]
    created_at:   int


class CoordinatorDb:
    """
    Kapselt alle Zugriffe auf cdb (coordinator.db).

    Verwendung:
        cdb = CoordinatorDb(con)
        investigator = cdb.get_investigator("h012345")
        job = cdb.get_assigned_job(investigator.id)
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        """
        Initialisiert CoordinatorDb.

        Args:
            con: Geöffnete sqlite3.Connection mit angebundener cdb.
                 WAL-Modus muss bereits durch connection_manager.py
                 gesetzt worden sein.
        """
        self._con = con
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    # Support-Status (§11.5 Bauplan Baustelle 3)
    # ------------------------------------------------------------------

    def get_support_status(
        self, subject_id: Optional[int] = None,
        stale_sec: int = DEFAULT_SUPPORT_STALE_SEC,
    ) -> SupportStatusRecord:
        """
        Liest den Live-Support-Status zu EINEM Fall (subject_id) aus
        cdb.support_sessions (Build 311). Aktiv = mindestens eine Sitzung ohne
        ended_at mit Heartbeat innerhalb stale_sec. username/since_ms beziehen
        sich auf den am längsten aktiven Supporter; count zählt alle aktiven.

        Ohne subject_id (kein Fallkontext) wird inaktiv zurückgegeben — der
        Aufrufer (events.py) liefert den Fall ab Build 312.

        Bei Fehler oder fehlender Sitzung: inaktiver Status — kein Absturz,
        kein stilles Versagen (Grundregel 1).
        """
        if subject_id is None:
            return SupportStatusRecord(active=False, username=None,
                                       since_ms=None, count=0)
        try:
            return self._retry(self._get_support_status_once, subject_id, stale_sec)
        except Exception as exc:
            logger.warning(
                "get_support_status(): Fehler beim Lesen — gebe inactive zurück: %s",
                exc,
            )
            return SupportStatusRecord(active=False, username=None,
                                       since_ms=None, count=0)

    def _get_support_status_once(
        self, subject_id: int, stale_sec: int
    ) -> SupportStatusRecord:
        """
        Einmaliger Versuch für get_support_status(). Liest aktive Support-
        Sitzungen des Falls aus cdb.support_sessions (verknüpft mit
        cdb.person für den system_username des Supporters).

        Build 311: löst den ehrlichen 'inactive'-Stub aus Build 308 ab — jetzt
        existiert mit support_sessions (M003) eine echte Präsenz-Erfassung.
        Beleg: Bauplan B7 v0.5 §6, mc 2026-07-01.
        """
        threshold = int(time.time()) - stale_sec
        rows = self._con.execute(
            "SELECT s.started_at, i.system_username "
            "FROM cdb.support_sessions s "
            "LEFT JOIN cdb.person i ON i.id = s.supporter_id "
            "WHERE s.subject_id = ? AND s.ended_at IS NULL AND s.last_heartbeat >= ? "
            "ORDER BY s.started_at ASC",
            (subject_id, threshold),
        ).fetchall()
        if not rows:
            return SupportStatusRecord(active=False, username=None,
                                       since_ms=None, count=0)
        first = rows[0]
        # started_at ist Unix-Sekunden -> JS erwartet ms.
        return SupportStatusRecord(
            active=True,
            username=first["system_username"],
            since_ms=int(first["started_at"]) * 1000,
            count=len(rows),
        )

    # ------------------------------------------------------------------
    # Ermittler-Abfragen
    # ------------------------------------------------------------------

    def get_investigator(
        self, system_username: str
    ) -> Optional[InvestigatorRecord]:
        """
        Sucht einen Ermittler anhand seines Systembenutzernamen.

        Args:
            system_username: $USER (Linux) oder SAMAccountName (Windows).

        Returns:
            InvestigatorRecord oder None wenn nicht gefunden.
        """
        return self._retry(self._get_investigator_once, system_username)

    def _get_investigator_once(
        self, system_username: str
    ) -> Optional[InvestigatorRecord]:
        try:
            row = self._con.execute(
                "SELECT id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at "
                "FROM cdb.person WHERE system_username = ?",
                (system_username,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise exc  # Retry übernimmt

        if row is None:
            logger.debug(
                "Ermittler '%s' nicht in cdb.person gefunden",
                system_username,
            )
            return None

        return InvestigatorRecord(
            id=int(row["id"]),
            system_username=str(row["system_username"]),
            display_name=str(row["display_name"]),
            is_investigator=bool(row["is_investigator"]),
            is_supervisor=bool(row["is_supervisor"]),
            is_support=bool(row["is_support"]),
            created_at=int(row["created_at"]),
        )

    # ------------------------------------------------------------------
    # Job-Abfragen
    # ------------------------------------------------------------------

    # get_assigned_job() / _get_assigned_job_once() ENTFERNT (Build 308):
    # Die Zuweisung 'Ermittler -> Fall' ist mit M002 von scrape_jobs.assigned_to
    # auf die Fallakte cases übergegangen. Die Job-Modus-Auflösung erfolgt jetzt
    # in core/mode_resolver._query_job direkt gegen cdb.cases. Diese Methode hatte
    # keine produktiven Aufrufer mehr. Beleg: Problem-1-Analyse 2026-07-01, mc.

    def get_job_by_id(self, job_id: int) -> Optional[JobRecord]:
        """
        Gibt einen Job anhand seiner ID zurück.

        Args:
            job_id: Primärschlüssel in scrape_jobs.

        Returns:
            JobRecord oder None.
        """
        return self._retry(self._get_job_by_id_once, job_id)

    def _get_job_by_id_once(self, job_id: int) -> Optional[JobRecord]:
        try:
            row = self._con.execute(
                "SELECT id, subject_id, username, priority, status, "
                "output_path, created_at "
                "FROM cdb.scrape_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise exc

        return self._row_to_job(row) if row else None

    # ------------------------------------------------------------------
    # Job-Status-Updates
    # ------------------------------------------------------------------

    def update_job_status(
        self,
        job_id: int,
        status: str,
        worker_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Aktualisiert den Status eines Jobs.

        Zulässige Übergänge:
          pending  → running (Server nimmt Job auf)
          running  → done    (nicht hier, sondern Stage 2)
          running  → failed  (bei Fehlern)

        Args:
            job_id:        Primärschlüssel des Jobs.
            status:        Neuer Status: 'pending', 'running', 'done', 'failed'.
            worker_id:     Hostname des Workers (optional).
            error_message: Fehlermeldung bei status='failed' (optional).

        Returns:
            True wenn ein Eintrag aktualisiert wurde, False wenn job_id
            nicht gefunden.
        """
        valid_statuses = {"pending", "running", "done", "failed"}
        if status not in valid_statuses:
            logger.error(
                "Ungültiger Job-Status: '%s'. Zulässig: %s",
                status, sorted(valid_statuses),
            )
            return False

        def _update() -> bool:
            ts_col = ""
            ts_val: list = []
            if status == "running":
                ts_col = ", started_at = ?"
                ts_val = [int(time.time())]
            elif status in ("done", "failed"):
                ts_col = ", finished_at = ?"
                ts_val = [int(time.time())]

            params = [status]
            extra_cols = ""
            extra_vals: list = []
            if worker_id is not None:
                extra_cols += ", worker_id = ?"
                extra_vals.append(worker_id)
            if error_message is not None:
                extra_cols += ", error_message = ?"
                extra_vals.append(error_message)

            all_params = params + extra_vals + ts_val + [job_id]
            cursor = self._con.execute(
                f"UPDATE cdb.scrape_jobs "
                f"SET status = ? {extra_cols} {ts_col} "
                f"WHERE id = ?",
                all_params,
            )
            self._con.commit()
            return cursor.rowcount > 0

        result = self._retry(_update)
        logger.debug(
            "Job %d Status → '%s' (worker=%s): %s",
            job_id, status, worker_id, "OK" if result else "nicht gefunden",
        )
        return result

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobRecord:
        """Konvertiert eine DB-Zeile in ein JobRecord."""
        return JobRecord(
            id=int(row["id"]),
            subject_id=int(row["subject_id"]),
            username=str(row["username"]),
            priority=int(row["priority"]),
            status=str(row["status"]),
            output_path=str(row["output_path"]) if row["output_path"] else None,
            created_at=int(row["created_at"]),
        )

    # ==========================================================================
    # pending_cross_annotations (Build 182 - Bug 2.78)
    # Transportmechanismus fuer Fremd-Annotationen.
    # Beleg: Projektgespraech 2026-05-12.
    # ==========================================================================

    def add_pending_cross_annotation(
        self,
        source_iid: int,
        target_uid: int,
        db_path: str,
        annotation_local_id: str,
    ) -> int:
        """Traegt neue Transportnotiz in pending_cross_annotations ein. Idempotent."""
        def _insert() -> int:
            # Build 185: Tabelle anlegen falls noch nicht vorhanden.
            # setup_coordinator_dev.py macht das beim Setup, aber fuer den Fall
            # dass es uebersprungen wurde, legen wir sie hier nach.
            # Beleg: Webserver-Log 2026-05-12 — coordinator.db verfuegbar aber
            # pending_cross_annotations-Eintrag fehlte lautlos.
            #
            # ACHTUNG (Build 506, Governance A4): Die KANONISCHE DDL dieser
            # Tabelle liegt seit Migration M023
            # (management/migrations/coordinator/m023_pca_into_chain.py) in der
            # MIGRATIONSKETTE. Das folgende executescript bleibt bewusst als
            # Absicherung gegen den urspruenglichen Bug 2.78 bestehen (eine
            # coordinator.db ohne gelaufene Migration soll den Querfund-
            # Transport nicht lautlos verschlucken) — es ist aber nicht mehr
            # die Wahrheitsquelle. WER HIER ETWAS AENDERT, MUSS M023
            # MITAENDERN; sonst laufen die beiden Stellen auseinander.
            # M023 ergaenzt zusaetzlich die VIRTUELL GENERIERTE Spalte
            # 'subject_id AS (target_uid)' (Schluesselangleichung ans
            # Prepper-Schema). Sie wird hier NICHT geschrieben und darf es auch
            # nicht: generierte Spalten sind nicht beschreibbar — der INSERT
            # unten fuellt weiterhin nur 'target_uid', und SQLite leitet
            # 'subject_id' daraus ab. Genau deshalb koennen die beiden nie
            # divergieren.
            self._con.executescript("""
                CREATE TABLE IF NOT EXISTS pending_cross_annotations (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_iid           INTEGER NOT NULL,
                    target_uid           INTEGER NOT NULL,
                    db_path              TEXT    NOT NULL,
                    annotation_local_id  TEXT    NOT NULL,
                    created_at           INTEGER NOT NULL,
                    integrated_at        INTEGER DEFAULT NULL
                );
                CREATE INDEX IF NOT EXISTS pca_target_uid_idx
                    ON pending_cross_annotations (target_uid)
                    WHERE integrated_at IS NULL;
            """)
            ts = int(time.time())
            existing = self._con.execute(
                "SELECT id FROM cdb.pending_cross_annotations "
                "WHERE target_uid = ? AND annotation_local_id = ? "
                "AND integrated_at IS NULL",
                (target_uid, annotation_local_id),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = self._con.execute(
                "INSERT INTO cdb.pending_cross_annotations "
                "(source_iid, target_uid, db_path, annotation_local_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_iid, target_uid, db_path, annotation_local_id, ts),
            )
            self._con.commit()
            return cursor.lastrowid or 0
        return self._retry(_insert)

    def get_pending_for_uid(self, target_uid: int) -> list:
        """Gibt ausstehende Transportnotizen fuer einen Ziel-uid zurueck."""
        def _get() -> list:
            # Tabelle anlegen falls noch nicht vorhanden (Build 185)
            try:
                rows = self._con.execute(
                    "SELECT id, source_iid, target_uid, db_path, "
                    "       annotation_local_id, created_at "
                    "FROM cdb.pending_cross_annotations "
                    "WHERE target_uid = ? AND integrated_at IS NULL "
                    "ORDER BY created_at ASC",
                    (target_uid,),
                ).fetchall()
            except Exception:
                # Tabelle existiert noch nicht — kein Fehler
                return []
            return [
                {
                    "id":                  int(r["id"]),
                    "source_iid":          int(r["source_iid"]),
                    "target_uid":          int(r["target_uid"]),
                    "db_path":             str(r["db_path"]),
                    "annotation_local_id": str(r["annotation_local_id"]),
                    "created_at":          int(r["created_at"]),
                }
                for r in rows
            ]
        return self._retry(_get)

    def mark_integrated(self, pending_id: int) -> bool:
        """Markiert Transporteintrag als integriert (integrated_at = now)."""
        def _mark() -> bool:
            ts = int(time.time())
            cursor = self._con.execute(
                "UPDATE cdb.pending_cross_annotations "
                "SET integrated_at = ? WHERE id = ?",
                (ts, pending_id),
            )
            self._con.commit()
            return cursor.rowcount > 0
        return self._retry(_mark)

    def _retry(self, func, *args):
        """
        Führt func(*args) aus und wiederholt bei sqlite3.OperationalError.

        Retry-Logik für Netzlaufwerk-Zugriffe:
          _RETRY_COUNT Versuche, _RETRY_DELAY_S Sekunden zwischen Versuchen.

        Raises:
            sqlite3.OperationalError: Wenn alle Versuche fehlschlagen.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, _RETRY_COUNT + 1):
            try:
                return func(*args)
            except sqlite3.OperationalError as exc:
                # Strukturelle Fehler (fehlende Tabellen/Spalten) sind dauerhaft —
                # Retries mit Wartezeit helfen nicht, sofort abbrechen.
                if "no such table" in str(exc) or "no such column" in str(exc):
                    logger.error(
                        "coordinator.db: Strukturfehler (kein Retry): %s", exc
                    )
                    raise exc
                last_exc = exc
                if attempt < _RETRY_COUNT:
                    logger.warning(
                        "coordinator.db OperationalError (Versuch %d/%d): %s — "
                        "Wiederhole in %.1f s",
                        attempt, _RETRY_COUNT, exc, _RETRY_DELAY_S,
                    )
                    time.sleep(_RETRY_DELAY_S)
        logger.error(
            "coordinator.db: Alle %d Versuche fehlgeschlagen. Letzter Fehler: %s",
            _RETRY_COUNT, last_exc,
        )
        raise last_exc
