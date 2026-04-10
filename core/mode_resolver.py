# =============================================================================
# core/mode_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Löst den Startmodus des Servers auf und ermittelt daraus alle
#   betriebsnotwendigen Pfade und die User-ID des zu untersuchenden
#   Beschuldigten.
#
# Die drei Startmodi (Eskalationskette: CLI > config.yaml > Coded Default):
#
#   job     — Normalbetrieb. Der Systembenutzer wird gegen die
#             investigators-Tabelle in coordinator.db geprüft. Der zugewiesene
#             Job aus scrape_jobs bestimmt user_id und forensic_db-Pfad.
#             Kein Job vorhanden → ModeResolverError.
#
#   cli     — Manueller Betrieb. user_id oder username werden per CLI-Argument
#             übergeben. Die Datenbankpfade werden aus den konfigurierten
#             Verzeichnissen und der user_id zusammengesetzt.
#             Weder user_id noch username angegeben → ModeResolverError.
#
#   support — Nur-Lese-Betrieb. Wie cli, aber evidence_db wird als read-only
#             angebunden; alle Schreiboperationen gehen in eine lokale TEMP-DB.
#             Dieselbe Pfadzusammensetzung wie cli.
#
# Dateinamensschema (unveränderlich, nicht konfigurierbar):
#   forensic_<uid>.db  →  <forensic_db_dir>/forensic_<uid>.db
#   evidence_<uid>.db  →  <evidence_db_dir>/evidence_<uid>.db
#
# Wichtig: Dieser Modul baut KEINE Datenbankverbindung auf. Er ermittelt nur
# Pfade und Modus. Die eigentliche Verbindung öffnet connection_manager.py.
# Die coordinator.db wird hier nur als Datenquelle für die Job-Abfrage
# im 'job'-Modus benötigt — über eine minimale Direktabfrage, da
# coordinator_db.py noch nicht initialisiert ist.
#
# Forensische Relevanz:
#   Die hier ermittelte user_id ist der Schlüssel zu allen Beweismitteln.
#   Eine falsche user_id würde Beweise eines Beschuldigten einem anderen
#   zuordnen. Daher: harter Abbruch bei jeder Unklarheit.
#
# Abhängigkeiten: sqlite3, os, pathlib — Stdlib + core-Module
# Version: v0.1.0 · Build: 004 · 2026-04-10
# =============================================================================

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.config_loader import ConfigLoader
from core.logger import get_logger
from core.user_resolver import UserResolver

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Zulässige Startmodi
# ---------------------------------------------------------------------------
VALID_MODES = frozenset({"job", "cli", "support"})


class ModeResolverError(Exception):
    """
    Wird geworfen, wenn der Startmodus nicht aufgelöst werden kann.
    Führt im Produktionsbetrieb zu einem harten Serverabbruch.

    Typische Ursachen:
    - Modus 'job': Kein offener Job für den aktuellen Systembenutzer
    - Modus 'cli'/'support': Weder --user-id noch --username angegeben
    - coordinator.db nicht erreichbar im 'job'-Modus
    - Unbekannte user_id oder username
    """


@dataclass(frozen=True)
class ResolvedContext:
    """
    Unveränderliches Ergebnisobjekt des ModeResolver.
    Enthält alle für den Serverbetrieb notwendigen Pfade und Kennzeichen.

    Felder:
        mode            — Aufgelöster Startmodus: "job", "cli" oder "support"
        user_id         — User-ID des zu untersuchenden Beschuldigten
        username        — Benutzername des Beschuldigten (aus DB oder CLI)
        forensic_db     — Absoluter Pfad zur forensic_<uid>.db (READ-ONLY)
        evidence_db     — Absoluter Pfad zur evidence_<uid>.db
                          (READ-WRITE in 'job'/'cli', READ-ONLY in 'support')
        default_db      — Absoluter Pfad zur default.db (READ-ONLY)
        coordinator_db  — Absoluter Pfad zur coordinator.db (READ-WRITE)
        investigator_id — investigators.id des aktuellen Systembenutzer,
                          oder None wenn nicht in coordinator.db gefunden
                          (im support-Modus akzeptabel)
    """
    mode:            str
    user_id:         int
    username:        str
    forensic_db:     Path
    evidence_db:     Path
    default_db:      Path
    coordinator_db:  Path
    investigator_id: Optional[int]


class ModeResolver:
    """
    Löst den Startmodus auf und gibt einen ResolvedContext zurück.

    Verwendung:
        resolver = ModeResolver(config, user_resolver, cli_overrides)
        ctx = resolver.resolve()
        print(ctx.mode, ctx.user_id, ctx.forensic_db)

    cli_overrides ist ein Dict mit den CLI-Argumenten, die den Modus und
    die Benutzerauswahl betreffen:
        {
            "mode":     "cli" | "job" | "support" | None,
            "user_id":  12345 | None,
            "username": "beschuldigter_name" | None,
        }
    """

    def __init__(
        self,
        config: ConfigLoader,
        user_resolver: UserResolver,
        cli_overrides: Optional[dict] = None,
    ) -> None:
        self._config = config
        self._user_resolver = user_resolver
        self._cli = cli_overrides or {}

    def resolve(self) -> ResolvedContext:
        """
        Löst den Startmodus auf und gibt den vollständigen ResolvedContext zurück.

        Raises:
            ModeResolverError: Bei jedem Problem, das den Betrieb verhindert.
        """
        mode = self._resolve_mode()
        logger.info("Startmodus: '%s'", mode)

        if mode == "job":
            return self._resolve_job(mode)
        elif mode in ("cli", "support"):
            return self._resolve_cli_or_support(mode)
        else:
            # Sollte durch _resolve_mode() bereits abgefangen sein
            raise ModeResolverError(f"Unbekannter Modus: '{mode}'")

    # ------------------------------------------------------------------
    # Modus-Auflösung
    # ------------------------------------------------------------------

    def _resolve_mode(self) -> str:
        """
        Löst den Startmodus anhand der Eskalationskette auf.
        CLI > config.yaml > Coded Default ("job")

        Raises:
            ModeResolverError: Wenn der ermittelte Modus kein gültiger Wert ist.
        """
        # CLI hat höchste Priorität
        mode = self._cli.get("mode") or self._config.get("server.mode", "job")

        if mode not in VALID_MODES:
            raise ModeResolverError(
                f"Ungültiger Startmodus: '{mode}'. "
                f"Zulässige Werte: {sorted(VALID_MODES)}"
            )
        return mode

    # ------------------------------------------------------------------
    # Modus 'job'
    # ------------------------------------------------------------------

    def _resolve_job(self, mode: str) -> ResolvedContext:
        """
        Löst Modus 'job' auf: Systembenutzer → coordinator.db → Job → user_id.

        Raises:
            ModeResolverError: Wenn kein offener Job gefunden wird oder die
                               coordinator.db nicht erreichbar ist.
        """
        system_username = self._user_resolver.system_username
        coordinator_db = self._resolve_coordinator_db_path()

        logger.debug(
            "Modus 'job': Suche offenen Job für Systembenutzer '%s' in '%s'",
            system_username, coordinator_db,
        )

        # Minimale Direktabfrage auf coordinator.db —
        # connection_manager.py ist zu diesem Zeitpunkt noch nicht aktiv.
        try:
            con = sqlite3.connect(str(coordinator_db), timeout=5.0)
            con.row_factory = sqlite3.Row
            try:
                job_row, investigator_id = self._query_job(con, system_username)
            finally:
                con.close()
        except sqlite3.OperationalError as exc:
            raise ModeResolverError(
                f"coordinator.db nicht erreichbar oder lesbar: '{coordinator_db}'\n"
                f"SQLite-Fehler: {exc}"
            ) from exc

        if job_row is None:
            raise ModeResolverError(
                f"Kein offener Ermittlungsauftrag für Systembenutzer "
                f"'{system_username}' in coordinator.db gefunden.\n"
                f"Mögliche Ursachen:\n"
                f"  - Kein Job zugewiesen (assigned_to)\n"
                f"  - Alle Jobs bereits abgeschlossen (status != 'pending'/'running')\n"
                f"  - Benutzer nicht in investigators-Tabelle eingetragen\n"
                f"Alternativ: Server mit --mode cli --user-id <id> starten."
            )

        user_id = int(job_row["user_id"])
        username = str(job_row["username"])

        # output_path aus dem Job-Eintrag übernehmen, sofern gesetzt —
        # andernfalls Standard-Pfadzusammensetzung verwenden.
        output_path = job_row["output_path"]
        if output_path:
            forensic_db = Path(output_path).resolve()
        else:
            forensic_db = self._build_forensic_db_path(user_id)

        evidence_db = self._build_evidence_db_path(user_id)

        logger.info(
            "Job gefunden: user_id=%d, username='%s', forensic_db='%s'",
            user_id, username, forensic_db,
        )

        return ResolvedContext(
            mode=mode,
            user_id=user_id,
            username=username,
            forensic_db=forensic_db,
            evidence_db=evidence_db,
            default_db=self._resolve_default_db_path(),
            coordinator_db=coordinator_db,
            investigator_id=investigator_id,
        )

    def _query_job(
        self, con: sqlite3.Connection, system_username: str
    ) -> tuple[Optional[sqlite3.Row], Optional[int]]:
        """
        Sucht in coordinator.db nach dem ältesten offenen Job für den
        Systembenutzer. Gibt (job_row, investigator_id) zurück.

        Ein Job gilt als offen wenn:
          - status IN ('pending', 'running')
          - assigned_to verweist auf den investigators-Eintrag des Systembenutzers

        Falls die investigators-Tabelle noch nicht existiert (z.B. in DEV vor
        der ersten Einrichtung), wird ein leeres Ergebnis zurückgegeben.
        """
        investigator_id: Optional[int] = None

        # Investigator-ID ermitteln
        try:
            row = con.execute(
                "SELECT id FROM investigators WHERE system_username = ?",
                (system_username,),
            ).fetchone()
            if row:
                investigator_id = int(row["id"])
        except sqlite3.OperationalError:
            # Tabelle existiert noch nicht — kein harter Fehler in DEV
            logger.warning(
                "investigators-Tabelle nicht gefunden in coordinator.db. "
                "Modus 'job' benötigt eine eingerichtete coordinator.db."
            )
            return None, None

        if investigator_id is None:
            logger.warning(
                "Systembenutzer '%s' nicht in investigators-Tabelle eingetragen.",
                system_username,
            )
            return None, None

        # Ältesten offenen Job für diesen Investigator suchen
        try:
            job_row = con.execute(
                """
                SELECT user_id, username, output_path
                FROM scrape_jobs
                WHERE assigned_to = ?
                  AND status IN ('pending', 'running')
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """,
                (investigator_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.warning("scrape_jobs-Abfrage fehlgeschlagen: %s", exc)
            return None, investigator_id

        return job_row, investigator_id

    # ------------------------------------------------------------------
    # Modi 'cli' und 'support'
    # ------------------------------------------------------------------

    def _resolve_cli_or_support(self, mode: str) -> ResolvedContext:
        """
        Löst die Modi 'cli' und 'support' auf.
        user_id oder username müssen per CLI angegeben worden sein.

        Raises:
            ModeResolverError: Wenn weder user_id noch username angegeben wurden,
                               oder wenn ein username nicht aufgelöst werden kann.
        """
        cli_user_id: Optional[int] = self._cli.get("user_id")
        cli_username: Optional[str] = self._cli.get("username")

        if cli_user_id is None and not cli_username:
            raise ModeResolverError(
                f"Modus '{mode}' erfordert --user-id <id> oder --username <name>.\n"
                f"Bitte einen der beiden Parameter angeben."
            )

        coordinator_db = self._resolve_coordinator_db_path()

        # user_id aus CLI oder via username-Lookup aus coordinator.db auflösen
        user_id, username, investigator_id = self._resolve_user_identity(
            cli_user_id, cli_username, coordinator_db
        )

        forensic_db = self._build_forensic_db_path(user_id)
        evidence_db = self._build_evidence_db_path(user_id)

        logger.info(
            "Modus '%s': user_id=%d, username='%s', forensic_db='%s'",
            mode, user_id, username, forensic_db,
        )

        return ResolvedContext(
            mode=mode,
            user_id=user_id,
            username=username,
            forensic_db=forensic_db,
            evidence_db=evidence_db,
            default_db=self._resolve_default_db_path(),
            coordinator_db=coordinator_db,
            investigator_id=investigator_id,
        )

    def _resolve_user_identity(
        self,
        cli_user_id: Optional[int],
        cli_username: Optional[str],
        coordinator_db: Path,
    ) -> tuple[int, str, Optional[int]]:
        """
        Löst user_id und username des Beschuldigten auf.

        Wenn user_id per CLI angegeben: Diese wird verwendet. Username wird
        aus coordinator.db nachgeschlagen (forensic_db hat diesen Stand nicht
        immer aktuell — maßgeblich ist scrape_jobs.username).

        Wenn nur username per CLI angegeben: user_id wird aus coordinator.db
        über scrape_jobs gesucht.

        Gibt (user_id, username, investigator_id) zurück.

        Raises:
            ModeResolverError: Wenn die Auflösung fehlschlägt.
        """
        system_username = self._user_resolver.system_username
        investigator_id: Optional[int] = None

        try:
            con = sqlite3.connect(str(coordinator_db), timeout=5.0)
            con.row_factory = sqlite3.Row
            try:
                # Investigator-ID des aktuellen Systembenutzers ermitteln
                # (nicht des Beschuldigten — der Beschuldigte ist kein Ermittler)
                try:
                    inv_row = con.execute(
                        "SELECT id FROM investigators WHERE system_username = ?",
                        (system_username,),
                    ).fetchone()
                    if inv_row:
                        investigator_id = int(inv_row["id"])
                except sqlite3.OperationalError:
                    # investigators-Tabelle noch nicht vorhanden — in DEV toleriert
                    pass

                if cli_user_id is not None:
                    # user_id bekannt — username nachschlagen
                    user_id = int(cli_user_id)
                    username = self._lookup_username(con, user_id) or f"uid_{user_id}"
                    return user_id, username, investigator_id
                else:
                    # Nur username bekannt — user_id suchen
                    result = self._lookup_user_id_by_name(con, cli_username)
                    if result is None:
                        raise ModeResolverError(
                            f"Benutzername '{cli_username}' nicht in "
                            f"coordinator.db (scrape_jobs) gefunden.\n"
                            f"Bitte --user-id verwenden oder den Benutzernamen "
                            f"prüfen."
                        )
                    return result[0], result[1], investigator_id
            finally:
                con.close()

        except sqlite3.OperationalError as exc:
            # coordinator.db nicht erreichbar — CLI-Modus kann trotzdem
            # funktionieren, wenn user_id bekannt ist
            if cli_user_id is not None:
                logger.warning(
                    "coordinator.db nicht erreichbar ('%s'): %s. "
                    "Betrieb ohne Username-Lookup.",
                    coordinator_db, exc,
                )
                return int(cli_user_id), f"uid_{cli_user_id}", None
            raise ModeResolverError(
                f"coordinator.db nicht erreichbar: '{coordinator_db}'\n"
                f"Für Modus 'cli' mit --username ist coordinator.db erforderlich.\n"
                f"Alternativ: --user-id verwenden."
            ) from exc

    def _lookup_username(
        self, con: sqlite3.Connection, user_id: int
    ) -> Optional[str]:
        """
        Sucht den aktuellen Benutzernamen zu einer user_id in scrape_jobs.
        Gibt den neuesten Eintrag zurück (höchste id = jüngster Job).
        """
        try:
            row = con.execute(
                """
                SELECT username FROM scrape_jobs
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            return str(row["username"]) if row else None
        except sqlite3.OperationalError:
            return None

    def _lookup_user_id_by_name(
        self, con: sqlite3.Connection, username: str
    ) -> Optional[tuple[int, str]]:
        """
        Sucht user_id und username zu einem Benutzernamen in scrape_jobs.
        Gibt (user_id, username) zurück oder None.
        """
        try:
            row = con.execute(
                """
                SELECT user_id, username FROM scrape_jobs
                WHERE username = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (username,),
            ).fetchone()
            if row:
                return int(row["user_id"]), str(row["username"])
            return None
        except sqlite3.OperationalError:
            return None

    # ------------------------------------------------------------------
    # Pfadzusammensetzung
    # ------------------------------------------------------------------

    def _build_forensic_db_path(self, user_id: int) -> Path:
        """
        Setzt den Pfad zur forensic_<uid>.db aus Verzeichnis + user_id zusammen.
        Dateinamensschema: forensic_<uid>.db
        """
        directory = Path(self._config.get("paths.forensic_db_dir"))
        return (directory / f"forensic_{user_id}.db").resolve()

    def _build_evidence_db_path(self, user_id: int) -> Path:
        """
        Setzt den Pfad zur evidence_<uid>.db aus Verzeichnis + user_id zusammen.
        Dateinamensschema: evidence_<uid>.db
        """
        directory = Path(self._config.get("paths.evidence_db_dir"))
        return (directory / f"evidence_{user_id}.db").resolve()

    def _resolve_default_db_path(self) -> Path:
        """Gibt den aufgelösten Pfad zur default.db zurück."""
        return Path(self._config.get("paths.default_db")).resolve()

    def _resolve_coordinator_db_path(self) -> Path:
        """Gibt den aufgelösten Pfad zur coordinator.db zurück."""
        return Path(self._config.get("paths.coordinator_db")).resolve()
