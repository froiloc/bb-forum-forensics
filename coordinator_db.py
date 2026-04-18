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
# Änderungen gegenüber Build 029 (Projektgespräch 2026-04-18):
#   - _get_support_status_once(): Defensive Row-Abfrage — unterstützt
#     sowohl sqlite3.Row (Normalfall) als auch Tupel-Rows (Fallback wenn
#     row_factory in Race Condition nicht gesetzt ist). Verhindert
#     'tuple index out of range'-WARNING.
#     Beleg: Projektgespräch 2026-04-18
#
# Version: v0.1.0 · Build: 030 · 2026-04-18
# Änderungen gegenüber Build 007 (Baustelle 3 — §11.5 Bauplan):
#   - SupportStatusRecord: Neues Dataclass für SSE-Support-Status.
#   - get_support_status(): Liest aktiven Support-Nutzer aus
#     investigators JOIN scrape_jobs. Gibt SupportStatusRecord zurück.
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


@dataclass(frozen=True)
class SupportStatusRecord:
    """
    Repräsentiert den aktuellen Support-Verbindungsstatus.

    Wird von get_support_status() zurückgegeben und von forensic_api/events.py
    als SSE-Nutzlast verwendet (§11.5 Bauplan Baustelle 3).

    Felder:
        active    — True wenn mindestens ein Support-Nutzer gerade aktiv ist
        username  — SAMAccountName des aktiven Support-Nutzers (oder None)
        since_ms  — Unix-Timestamp ms seit wann der Support-Nutzer aktiv ist
                    (None wenn active=False)
    """
    active:    bool
    username:  Optional[str]
    since_ms:  Optional[int]


@dataclass(frozen=True)
class InvestigatorRecord:
    """
    Repräsentiert einen Eintrag aus der investigators-Tabelle.

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
        user_id       — forum.users.id des Beschuldigten
        username      — Benutzername des Beschuldigten
        priority      — 1 (höchste) bis 5 (niedrigste)
        status        — 'pending', 'running', 'done', 'failed'
        output_path   — Pfad zur forensic_<uid>.db (gesetzt nach Stage 2)
        assigned_to   — investigators.id des zuständigen Ermittlers
        created_at    — Unix-Timestamp der Job-Anlage
    """
    id:           int
    user_id:      int
    username:     str
    priority:     int
    status:       str
    output_path:  Optional[str]
    assigned_to:  Optional[int]
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

    def get_support_status(self) -> SupportStatusRecord:
        """
        Liest den aktuellen Support-Status aus coordinator.db.

        Ein Support-Nutzer gilt als aktiv, wenn:
          1. Er in cdb.investigators mit is_support=1 eingetragen ist UND
          2. Er einen Job im Status 'running' in cdb.scrape_jobs hat.

        Gibt bei Fehler oder fehlendem Support-Nutzer einen inaktiven Status
        zurück — kein Absturz, kein stilles Versagen (Grundregel 1).

        Rückgabe:
            SupportStatusRecord mit active=False wenn kein Support-Nutzer aktiv.
        """
        try:
            return self._retry(self._get_support_status_once)
        except Exception as exc:
            logger.warning(
                "get_support_status(): Fehler beim Lesen — gebe inactive zurück: %s",
                exc,
            )
            return SupportStatusRecord(active=False, username=None, since_ms=None)

    def _get_support_status_once(self) -> SupportStatusRecord:
        """Einmaliger Versuch für get_support_status(). Wird durch _retry() wiederholt."""
        try:
            row = self._con.execute(
                """
                SELECT i.system_username, j.started_at
                FROM cdb.investigators AS i
                JOIN cdb.scrape_jobs   AS j ON j.assigned_to = i.id
                WHERE i.is_support = 1
                  AND j.status = 'running'
                ORDER BY j.started_at DESC
                LIMIT 1
                """
            ).fetchone()
        except sqlite3.OperationalError as exc:
            # Fehlende Tabelle ist ein dauerhafter Schemakonflikt — kein Retry
            # sinnvoll, sofort weiterwerfen ohne Zeit zu verlieren
            if "no such table" in str(exc):
                raise exc
            raise exc  # Andere OperationalErrors: Retry übernimmt

        if row is None:
            return SupportStatusRecord(active=False, username=None, since_ms=None)

        # Defensiver Row-Zugriff: unterstützt sqlite3.Row (Normalfall) und
        # Tupel-Rows (Fallback bei Race Condition mit row_factory).
        # sqlite3.Row: row["key"] funktioniert. Tupel: row[index] nötig.
        # Query-Reihenfolge: SELECT i.system_username [0], j.started_at [1]
        # Beleg: Projektgespräch 2026-04-18
        try:
            username_val   = row["system_username"]
            started_at_val = row["started_at"]
        except TypeError:
            # row ist ein Tupel (row_factory nicht aktiv) — Index-Zugriff
            username_val   = row[0]
            started_at_val = row[1] if len(row) > 1 else None

        # started_at ist Unix-Timestamp in Sekunden → JS erwartet ms
        started_at_s = int(started_at_val) if started_at_val is not None else 0
        return SupportStatusRecord(
            active=True,
            username=str(username_val),
            since_ms=started_at_s * 1000,
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
                "FROM cdb.investigators WHERE system_username = ?",
                (system_username,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise exc  # Retry übernimmt

        if row is None:
            logger.debug(
                "Ermittler '%s' nicht in cdb.investigators gefunden",
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

    def get_assigned_job(
        self, investigator_id: int
    ) -> Optional[JobRecord]:
        """
        Sucht den ältesten offenen Job für einen Ermittler.

        Offen = status IN ('pending', 'running').
        Sortierung: priority ASC (kleinste Zahl = höchste Priorität),
                    created_at ASC (ältester zuerst).

        Args:
            investigator_id: investigators.id des Ermittlers.

        Returns:
            JobRecord oder None wenn kein offener Job vorhanden.
        """
        return self._retry(self._get_assigned_job_once, investigator_id)

    def _get_assigned_job_once(
        self, investigator_id: int
    ) -> Optional[JobRecord]:
        try:
            row = self._con.execute(
                """
                SELECT id, user_id, username, priority, status,
                       output_path, assigned_to, created_at
                FROM cdb.scrape_jobs
                WHERE assigned_to = ?
                  AND status IN ('pending', 'running')
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """,
                (investigator_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise exc

        if row is None:
            return None

        return self._row_to_job(row)

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
                "SELECT id, user_id, username, priority, status, "
                "output_path, assigned_to, created_at "
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
            user_id=int(row["user_id"]),
            username=str(row["username"]),
            priority=int(row["priority"]),
            status=str(row["status"]),
            output_path=str(row["output_path"]) if row["output_path"] else None,
            assigned_to=int(row["assigned_to"]) if row["assigned_to"] is not None else None,
            created_at=int(row["created_at"]),
        )

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
