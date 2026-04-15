# =============================================================================
# db/connection_manager.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Öffnet alle Datenbankverbindungen und baut die ATTACH-Struktur auf.
#   Ist der einzige Ort im gesamten Projekt, der sqlite3.connect() aufruft.
#   Gibt fertig initialisierte Instanzen von ForensicDb, DefaultDb,
#   EvidenceDb und CoordinatorDb zurück.
#
# ATTACH-Konfiguration — Normalmodus (job/cli):
#   Haupt-DB:  evidence_<uid>.db  (READ-WRITE)
#   ATTACH AS fdb: forensic_<uid>.db  (READ-ONLY, URI mode=ro)
#   ATTACH AS ddb: default.db         (READ-ONLY, URI mode=ro)
#   ATTACH AS cdb: coordinator.db     (READ-WRITE)
#
# ATTACH-Konfiguration — Support-Modus:
#   Haupt-DB:  :memory: oder /tmp/forensic_support_<session_id>.db
#   ATTACH AS edb: evidence_<uid>.db  (READ-ONLY, URI mode=ro)
#   ATTACH AS fdb: forensic_<uid>.db  (READ-ONLY, URI mode=ro)
#   ATTACH AS ddb: default.db         (READ-ONLY, URI mode=ro)
#   ATTACH AS cdb: coordinator.db     (READ-WRITE)
#
# Verbindliche Alias-Namen (unveränderlich):
#   fdb → forensic_<uid>.db
#   ddb → default.db
#   cdb → coordinator.db
#   edb → evidence_<uid>.db (nur Support-Modus)
#
# Session-ID für Support-TEMP-DB:
#   Wird aus Unix-Timestamp + user_id gebildet.
#   Ermöglicht mehrere gleichzeitige Support-Sessions auf demselben System.
#
# Forensische Relevanz:
#   forensic_<uid>.db wird immer mit URI mode=ro geöffnet — kein Code
#   im Webserver kann jemals in die Beweismittel-DB schreiben.
#   Jede Verbindungsöffnung wird im Log protokolliert (mit Pfaden).
#
# Abhängigkeiten: sqlite3, time, os — Stdlib + interne DB-Module
# Version: v0.1.0 · Build: 018 · 2026-04-15
# =============================================================================

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.logger import get_logger
from core.mode_resolver import ResolvedContext
from core.config_loader import ConfigLoader
from db.forensic_db import ForensicDb
from db.default_db import DefaultDb
from db.evidence_db import EvidenceDb
from db.coordinator_db import CoordinatorDb
from db.assets_db import AssetsDb          # NEU Build 017

logger = get_logger(__name__)


@dataclass
class DatabaseBundle:
    """
    Bündelt alle initialisierten DB-Instanzen für den Serverbetrieb.

    Felder:
        connection   — Die Haupt-sqlite3.Connection (Träger aller ATTACHs)
        forensic     — ForensicDb (READ-ONLY, BLOB-Lookup + Aliasse)
        default      — DefaultDb  (READ-ONLY, statische Assets)
        evidence     — EvidenceDb (READ-WRITE oder Support-TEMP)
        coordinator  — CoordinatorDb (READ-WRITE außer in Sonderfällen)
        assets       — AssetsDb  (READ-ONLY, nutzerspezifische Bilder/Avatare)
                       Kann intern None-Verbindung haben wenn assets_<uid>.db
                       noch nicht existiert (vor erstem asset_importer-Lauf).
        temp_db_path — Pfad zur Support-TEMP-DB-Datei, oder None
                       (None = In-Memory oder Normalmodus)
    """
    connection:   sqlite3.Connection
    forensic:     ForensicDb
    default:      DefaultDb
    evidence:     EvidenceDb
    coordinator:  CoordinatorDb
    assets:       AssetsDb            # NEU Build 017
    temp_db_path: Optional[str] = None

    def close(self) -> None:
        """Schließt die Haupt-Verbindung (und damit alle ATTACHs)."""
        try:
            self.connection.close()
            logger.info("Datenbankverbindungen geschlossen.")
            if self.temp_db_path and os.path.exists(self.temp_db_path):
                os.unlink(self.temp_db_path)
                logger.debug("Support-TEMP-DB gelöscht: '%s'", self.temp_db_path)
        except Exception as exc:
            logger.warning("Fehler beim Schließen der DB-Verbindung: %s", exc)


class ConnectionManagerError(Exception):
    """Wird geworfen wenn Datenbankverbindungen nicht aufgebaut werden können."""


class ConnectionManager:
    """
    Baut alle Datenbankverbindungen auf und gibt ein DatabaseBundle zurück.

    Verwendung:
        manager = ConnectionManager(config, context)
        bundle = manager.open()
        # ... Serverbetrieb ...
        bundle.close()

    Die Klasse ist nicht wiederverwendbar — nach open() ist sie verbraucht.
    Für einen Neustart muss eine neue Instanz erstellt werden.
    """

    def __init__(
        self,
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        # Reihenfolge (context, config) entspricht dem Aufruf in main.py.
        self._config = config
        self._ctx = context

    def open(self) -> DatabaseBundle:
        """
        Öffnet alle Verbindungen und gibt ein fertiges DatabaseBundle zurück.

        Raises:
            ConnectionManagerError: Wenn Verbindungen nicht aufgebaut werden können.
        """
        mode = self._ctx.mode
        logger.info(
            "Öffne Datenbankverbindungen (Modus: '%s', user_id: %d)",
            mode, self._ctx.user_id,
        )

        if mode in ("job", "cli"):
            return self._open_normal()
        elif mode == "support":
            return self._open_support()
        else:
            raise ConnectionManagerError(
                f"Unbekannter Modus: '{mode}'"
            )

    # ------------------------------------------------------------------
    # Normalmodus (job / cli)
    # ------------------------------------------------------------------

    def _open_normal(self) -> DatabaseBundle:
        """
        Öffnet Verbindungen im Normalmodus.

        Haupt-DB: evidence_<uid>.db (READ-WRITE)
        ATTACHs:  fdb (READ-ONLY), ddb (READ-ONLY), cdb (READ-WRITE)
        """
        evidence_path   = self._ctx.evidence_db
        forensic_path   = self._ctx.forensic_db
        default_path    = self._ctx.default_db
        coordinator_path = self._ctx.coordinator_db

        self._assert_exists(forensic_path, "forensic_db")
        self._assert_exists(default_path,  "default_db")

        try:
            # Haupt-DB: evidence_db (READ-WRITE)
            # Wird angelegt wenn nicht vorhanden (erster Start für diesen Nutzer)
            con = sqlite3.connect(
                str(evidence_path),
                timeout=10.0,
                check_same_thread=False,
            )
            con.row_factory = sqlite3.Row
            logger.debug("Haupt-DB geöffnet: '%s'", evidence_path)

            # WAL-Modus für bessere Parallelität
            con.execute("PRAGMA journal_mode=WAL")

            # fdb: forensic_db READ-ONLY
            self._attach_readonly(con, forensic_path, "fdb")

            # ddb: default_db READ-ONLY
            self._attach_readonly(con, default_path, "ddb")

            # cdb: coordinator_db READ-WRITE (nur wenn vorhanden)
            if coordinator_path.exists():
                self._attach_readwrite(con, coordinator_path, "cdb")
                con.execute("PRAGMA cdb.journal_mode=WAL")
                logger.debug("cdb angebunden: '%s'", coordinator_path)
            else:
                logger.warning(
                    "coordinator.db nicht gefunden — cdb nicht angebunden: '%s'",
                    coordinator_path,
                )

            # adb: assets_db READ-ONLY (optional — existiert erst nach asset_importer)
            # NEU Build 017
            assets_path = self._ctx.assets_db
            assets_con: Optional[sqlite3.Connection] = None
            if assets_path.exists():
                self._attach_readonly(con, assets_path, "adb")
                assets_con = con
                logger.debug("adb angebunden (READ-ONLY): '%s'", assets_path)
            else:
                logger.info(
                    "assets_<uid>.db nicht gefunden — adb nicht angebunden: '%s'. "
                    "Asset-Lookup fällt vollständig auf default.db zurück.",
                    assets_path,
                )

            # DB-Instanzen initialisieren
            forensic    = ForensicDb(con)
            # forum_base_url aus forensic_meta lesen — wird für Asset-URL-Lookup
            # benötigt, da asset_urls vollständige Onion-URLs als Schlüssel speichert
            forum_base_url = forensic.get_forum_base_url()
            default     = DefaultDb(con, forum_base_url=forum_base_url)
            evidence    = EvidenceDb(con)
            coordinator = CoordinatorDb(con)
            assets      = AssetsDb(assets_con, forum_base_url=forum_base_url)   # NEU Build 017

            logger.info(
                "Alle Verbindungen aufgebaut (Normalmodus). "
                "forensic_db: %d Seiten, evidence_db: %d Annotationen",
                forensic.page_count(),
                evidence.annotation_count(),
            )

            return DatabaseBundle(
                connection=con,
                forensic=forensic,
                default=default,
                evidence=evidence,
                coordinator=coordinator,
                assets=assets,    # NEU Build 017
            )

        except sqlite3.OperationalError as exc:
            raise ConnectionManagerError(
                f"Datenbankverbindung konnte nicht aufgebaut werden: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Support-Modus
    # ------------------------------------------------------------------

    def _open_support(self) -> DatabaseBundle:
        """
        Öffnet Verbindungen im Support-Modus.

        Haupt-DB: TEMP-DB (In-Memory oder /tmp-Datei)
        ATTACHs:  edb (READ-ONLY), fdb (READ-ONLY),
                  ddb (READ-ONLY), cdb (READ-WRITE)
        """
        evidence_path    = self._ctx.evidence_db
        forensic_path    = self._ctx.forensic_db
        default_path     = self._ctx.default_db
        coordinator_path = self._ctx.coordinator_db

        self._assert_exists(forensic_path, "forensic_db")
        self._assert_exists(default_path,  "default_db")

        temp_db_mode = self._config.get("support.temp_db", "memory")
        temp_db_path: Optional[str] = None

        try:
            # Haupt-DB: TEMP-DB
            if temp_db_mode == "memory":
                con = sqlite3.connect(
                    ":memory:",
                    check_same_thread=False,
                )
                logger.debug("Support-Modus: In-Memory TEMP-DB")
            else:
                session_id = f"{int(time.time())}_{self._ctx.user_id}"
                temp_db_path = os.path.join(
                    tempfile.gettempdir(),
                    f"forensic_support_{session_id}.db",
                )
                con = sqlite3.connect(
                    temp_db_path,
                    timeout=10.0,
                    check_same_thread=False,
                )
                logger.debug("Support-Modus: TEMP-DB-Datei '%s'", temp_db_path)

            con.row_factory = sqlite3.Row
            con.execute("PRAGMA journal_mode=WAL")

            # edb: evidence_db READ-ONLY (lesender Zugriff für Support)
            if evidence_path.exists():
                self._attach_readonly(con, evidence_path, "edb")
                logger.debug("edb angebunden (READ-ONLY): '%s'", evidence_path)
            else:
                logger.warning(
                    "evidence_db nicht gefunden — edb nicht angebunden: '%s'",
                    evidence_path,
                )

            # fdb: forensic_db READ-ONLY
            self._attach_readonly(con, forensic_path, "fdb")

            # ddb: default_db READ-ONLY
            self._attach_readonly(con, default_path, "ddb")

            # cdb: coordinator_db READ-WRITE
            if coordinator_path.exists():
                self._attach_readwrite(con, coordinator_path, "cdb")
                con.execute("PRAGMA cdb.journal_mode=WAL")
                logger.debug("cdb angebunden (READ-WRITE): '%s'", coordinator_path)
            else:
                logger.warning(
                    "coordinator.db nicht gefunden — cdb nicht angebunden: '%s'",
                    coordinator_path,
                )

            # adb: assets_db READ-ONLY (optional — existiert erst nach asset_importer)
            # NEU Build 017
            assets_path = self._ctx.assets_db
            assets_con: Optional[sqlite3.Connection] = None
            if assets_path.exists():
                self._attach_readonly(con, assets_path, "adb")
                assets_con = con
                logger.debug("adb angebunden (READ-ONLY, Support): '%s'", assets_path)
            else:
                logger.info(
                    "assets_<uid>.db nicht gefunden — adb nicht angebunden: '%s'. "
                    "Asset-Lookup fällt vollständig auf default.db zurück.",
                    assets_path,
                )

            # DB-Instanzen initialisieren
            # ForensicDb und DefaultDb wie im Normalmodus
            forensic    = ForensicDb(con)
            # forum_base_url aus forensic_meta lesen — wird für Asset-URL-Lookup
            # benötigt, da asset_urls vollständige Onion-URLs als Schlüssel speichert
            forum_base_url = forensic.get_forum_base_url()
            default     = DefaultDb(con, forum_base_url=forum_base_url)
            # EvidenceDb schreibt in die TEMP-Haupt-DB
            evidence    = EvidenceDb(con)
            coordinator = CoordinatorDb(con)
            assets      = AssetsDb(assets_con, forum_base_url=forum_base_url)   # NEU Build 017

            logger.info(
                "Alle Verbindungen aufgebaut (Support-Modus). "
                "TEMP-DB: %s",
                "In-Memory" if temp_db_mode == "memory" else temp_db_path,
            )

            return DatabaseBundle(
                connection=con,
                forensic=forensic,
                default=default,
                evidence=evidence,
                coordinator=coordinator,
                assets=assets,        # NEU Build 017
                temp_db_path=temp_db_path,
            )

        except sqlite3.OperationalError as exc:
            raise ConnectionManagerError(
                f"Support-Modus: Datenbankverbindung konnte nicht aufgebaut "
                f"werden: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _attach_readonly(
        self, con: sqlite3.Connection, path: Path, alias: str
    ) -> None:
        """
        Bindet eine DB im READ-ONLY-Modus per ATTACH an.
        Verwendet SQLite URI-Syntax mit mode=ro.

        Args:
            con:   Geöffnete Hauptverbindung.
            path:  Absoluter Pfad zur anzubindenden DB.
            alias: ATTACH-Alias-Name (fdb, ddb, edb).

        Raises:
            sqlite3.OperationalError: Wenn ATTACH fehlschlägt.
        """
        uri = path.as_uri() + "?mode=ro"
        con.execute(f"ATTACH DATABASE '{uri}' AS {alias}")
        logger.debug("ATTACH %s (READ-ONLY): '%s'", alias, path)

    def _attach_readwrite(
        self, con: sqlite3.Connection, path: Path, alias: str
    ) -> None:
        """
        Bindet eine DB im READ-WRITE-Modus per ATTACH an.

        Args:
            con:   Geöffnete Hauptverbindung.
            path:  Absoluter Pfad zur anzubindenden DB.
            alias: ATTACH-Alias-Name (cdb).
        """
        con.execute(f"ATTACH DATABASE '{str(path)}' AS {alias}")
        logger.debug("ATTACH %s (READ-WRITE): '%s'", alias, path)

    @staticmethod
    def _assert_exists(path: Path, label: str) -> None:
        """
        Prüft ob eine Datei existiert.

        Raises:
            ConnectionManagerError: Wenn die Datei nicht gefunden wird.
        """
        if not path.exists():
            raise ConnectionManagerError(
                f"{label} nicht gefunden: '{path}'\n"
                f"Bitte startup_checks.py vor connection_manager.py aufrufen."
            )
