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
#   ATTACH AS adb: assets_<uid>.db    (READ-ONLY, optional)
#   ATTACH AS tdb: templates.db       (READ-ONLY, optional) — NEU Build 117
#
# ATTACH-Konfiguration — Support-Modus:
#   Haupt-DB:  :memory: oder /tmp/forensic_support_<session_id>.db
#   ATTACH AS edb: evidence_<uid>.db  (READ-ONLY, URI mode=ro)
#   ATTACH AS fdb: forensic_<uid>.db  (READ-ONLY, URI mode=ro)
#   ATTACH AS ddb: default.db         (READ-ONLY, URI mode=ro)
#   ATTACH AS cdb: coordinator.db     (READ-WRITE)
#   ATTACH AS adb: assets_<uid>.db    (READ-ONLY, optional)
#   ATTACH AS tdb: templates.db       (READ-ONLY, optional) — NEU Build 117
#
# Verbindliche Alias-Namen (unveränderlich):
#   fdb → forensic_<uid>.db
#   ddb → default.db
#   cdb → coordinator.db
#   edb → evidence_<uid>.db (nur Support-Modus)
#   adb → assets_<uid>.db   (optional)
#   tdb → templates.db      (optional)
#
# Session-ID für Support-TEMP-DB:
#   Wird aus Unix-Timestamp + subject_id gebildet.
#   Ermöglicht mehrere gleichzeitige Support-Sessions auf demselben System.
#
# Forensische Relevanz:
#   forensic_<uid>.db wird immer mit URI mode=ro geöffnet — kein Code
#   im Webserver kann jemals in die Beweismittel-DB schreiben.
#   Jede Verbindungsöffnung wird im Log protokolliert (mit Pfaden).
#
# Abhängigkeiten: sqlite3, time, os — Stdlib + interne DB-Module
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
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
from db.assets_db import AssetsDb
from db.templates_db import TemplatesDb          # NEU Build 089
from db.translations_db import TranslationsDb    # NEU Build 329
from db.locking_connection import LockingConnection  # Build 325: Nebenlaeufigkeits-Serialisierung
from db.journal_policy import (          # NEU Build 408: Journalmodus zentral
    apply_journal_mode,
    resolve_mode,
    resolve_fallback,
    JournalPolicyError,
    NETWORK_HINT as JOURNAL_NETWORK_HINT,
)

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
        templates    — TemplatesDb (READ-ONLY, Berichtsvorlagen aus templates.db)
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
    templates:    TemplatesDb         # NEU Build 089
    translations: TranslationsDb      # NEU Build 329 — READ-ONLY, KI-Uebersetzungen
    temp_db_path: Optional[str] = None
    # Menge aktiver SSE-Client-IDs — von EventsEndpoint verwaltet.
    # Wird von _action_release_lock fuer Queue-Kaskade (SLA Punkt 4) benoetigt.
    # Beleg: Architektur-Revision 2026-05-23
    _active_sse_clients: set = None

    def get_active_sse_clients(self) -> set:
        """Gibt Menge aktiver SSE-Client-IDs zurueck."""
        return self._active_sse_clients or set()

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
            "Öffne Datenbankverbindungen (Modus: '%s', subject_id: %d)",
            mode, self._ctx.subject_id,
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
        ATTACHs:  fdb (READ-ONLY), ddb (READ-ONLY), cdb (READ-WRITE),
                  adb (READ-ONLY, optional), tdb (READ-ONLY, optional)
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

            # Journalmodus zentral (Build 408). 'auto' = WAL versuchen, bei
            # Fehlschlag protokollierter Rueckfall auf ein Rollback-Journal.
            # Beleg fuer die Notwendigkeit: Diagnose 2026-07-14 — WAL scheitert
            # auf Netzlaufwerken mit 'disk I/O error' (Shared Memory/'-shm' ist
            # maschinenlokal, sqlite.org/wal.html). Auf lokaler Platte greift
            # weiterhin WAL — PROD-Verhalten unveraendert.
            journal_mode     = resolve_mode(self._config)
            journal_fallback = resolve_fallback(self._config)
            apply_journal_mode(
                con, evidence_path,
                schema="main", mode=journal_mode, fallback=journal_fallback,
                log=logger,
            )

            # fdb: forensic_db READ-ONLY
            self._attach_readonly(con, forensic_path, "fdb")

            # ddb: default_db READ-ONLY
            self._attach_readonly(con, default_path, "ddb")

            # cdb: coordinator_db READ-WRITE (nur wenn vorhanden)
            if coordinator_path.exists():
                self._attach_readwrite(con, coordinator_path, "cdb")
                apply_journal_mode(
                    con, coordinator_path,
                    schema="cdb", mode=journal_mode, fallback=journal_fallback,
                    log=logger,
                )
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

            # tdb: templates_db READ-ONLY (optional — existiert erst nach setup_templates.py)
            # NEU Build 117 — Bug 3.3: templates.db wurde bisher nicht per ATTACH
            # eingebunden, TemplatesDb._check_available() fing das still ab.
            # Beleg: Projektgespraech 2026-05-07
            templates_path = Path(
                self._config.get("paths.templates_db", "./data/templates.db")
            ).resolve()
            if templates_path.exists():
                self._attach_readonly(con, templates_path, "tdb")
                logger.debug("tdb angebunden (READ-ONLY): '%s'", templates_path)
            else:
                logger.info(
                    "templates.db nicht gefunden — tdb nicht angebunden: '%s'. "
                    "Bausteine-Bibliothek bleibt leer. "
                    "setup_templates.py ausfuehren um templates.db anzulegen.",
                    templates_path,
                )

            # trdb: translations_db READ-ONLY (optional — existiert erst nach
            # externem ollama-Prepper-Lauf, ~2 Wochen nach Build 329). Muster
            # analog tdb (Build 117). Anbindung VOR set_authorizer(None) unten.
            # Beleg: Bauplan Build 329 §2.3
            translations_path = Path(
                self._config.get("paths.translations_db", "./data/translations.db")
            ).resolve()
            if translations_path.exists():
                self._attach_readonly(con, translations_path, "trdb")
                logger.debug("trdb angebunden (READ-ONLY): '%s'", translations_path)
            else:
                logger.info(
                    "translations.db nicht gefunden — trdb nicht angebunden: '%s'. "
                    "Uebersetzungs-Buttons bleiben aus, bis der ollama-Prepper "
                    "die DB erzeugt.",
                    translations_path,
                )

            # DB-Instanzen initialisieren
            # Build 325: Ab hier laufen ALLE Fach-DB-Zugriffe (mehrthreadig zur Laufzeit:
            # SSE-Thread + Request-Threads, Beleg connection_manager.py:262-273 / Build 021)
            # ueber den LockingConnection-Wrapper, der jeden execute+fetch-Abschnitt
            # serialisiert. ATTACH/PRAGMA/Authorizer oben liefen bewusst auf der rohen
            # (einthreadigen) con. Beleg: Live-Diagnose 2026-07-06 (get_page InterfaceError
            # 'bad parameter or other API misuse' bei Nebenlaeufigkeit).
            db_con = LockingConnection(con)
            if assets_con is not None:
                assets_con = db_con          # assets nutzt dieselbe geteilte con (adb-ATTACH)

            forensic    = ForensicDb(db_con)
            # forum_base_url aus forensic_meta lesen — wird für Asset-URL-Lookup
            # benötigt, da asset_urls vollständige Onion-URLs als Schlüssel speichert
            forum_base_url = forensic.get_forum_base_url()
            default     = DefaultDb(db_con, forum_base_url=forum_base_url)
            evidence    = EvidenceDb(db_con, db_path=str(evidence_path))  # Build 098: Thread-Safety
            coordinator = CoordinatorDb(db_con)
            assets      = AssetsDb(assets_con, forum_base_url=forum_base_url)   # NEU Build 017
            templates   = TemplatesDb(db_con)          # NEU Build 089
            translations = TranslationsDb(db_con)      # NEU Build 329

            # Authorizer nach vollständigem ATTACH-Aufbau deaktivieren.
            # Hintergrund (Build 021): set_authorizer() ist nicht thread-safe
            # wenn check_same_thread=False — auf Windows führt das zu Deadlocks
            # wenn SSE-Thread und Request-Threads gleichzeitig die Connection
            # nutzen. Der Schreibschutz auf fdb/ddb/adb ist durch
            # startup_checks._check_forensic_db_readonly() und das
            # Dateisystem (Stage-2 setzt chmod/NTFS-readonly) gewährleistet.
            # Beleg: webserver_freeze.txt, Projektgespräch 2026-04-22.
            con.set_authorizer(None)
            logger.debug("Authorizer deaktiviert — Schreibschutz via Dateisystem/startup_checks.")

            logger.info(
                "Alle Verbindungen aufgebaut (Normalmodus). "
                "forensic_db: %d Seiten, evidence_db: %d Annotationen",
                forensic.page_count(),
                evidence.annotation_count(),
            )

            return DatabaseBundle(
                connection=db_con,   # Build 325: gewrappte (serialisierte) Verbindung
                forensic=forensic,
                default=default,
                evidence=evidence,
                coordinator=coordinator,
                assets=assets,    # NEU Build 017
                templates=templates,  # NEU Build 089
                translations=translations,  # NEU Build 329
            )

        except JournalPolicyError as exc:
            # Build 408: Journalmodus-Probleme sind auf Netzlaufwerken der haeufigste
            # Startfehler. Sie werden als ConnectionManagerError weitergereicht,
            # damit main.py sie ohne Roh-Traceback im Klartext melden kann.
            raise ConnectionManagerError(str(exc)) from exc

        except sqlite3.OperationalError as exc:
            zusatz = " — " + JOURNAL_NETWORK_HINT if "disk i/o error" in str(exc).lower() else ""
            raise ConnectionManagerError(
                f"Datenbankverbindung konnte nicht aufgebaut werden: {exc}{zusatz}"
            ) from exc

    # ------------------------------------------------------------------
    # Support-Modus
    # ------------------------------------------------------------------

    def _open_support(self) -> DatabaseBundle:
        """
        Öffnet Verbindungen im Support-Modus.

        Haupt-DB: TEMP-DB (In-Memory oder /tmp-Datei)
        ATTACHs:  edb (READ-ONLY), fdb (READ-ONLY),
                  ddb (READ-ONLY), cdb (READ-WRITE),
                  adb (READ-ONLY, optional), tdb (READ-ONLY, optional)
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
                session_id = f"{int(time.time())}_{self._ctx.subject_id}"
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
            # Build 408: siehe _open_normal(). Die Support-TEMP-DB liegt zwar
            # in der Regel lokal (tempfile), die coordinator.db darunter aber
            # nicht zwingend — daher dieselbe Strategie fuer beide.
            journal_mode     = resolve_mode(self._config)
            journal_fallback = resolve_fallback(self._config)
            apply_journal_mode(
                con, temp_db_path or ":memory:",
                schema="main", mode=journal_mode, fallback=journal_fallback,
                log=logger,
            )

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
                apply_journal_mode(
                    con, coordinator_path,
                    schema="cdb", mode=journal_mode, fallback=journal_fallback,
                    log=logger,
                )
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

            # tdb: templates_db READ-ONLY (optional — existiert erst nach setup_templates.py)
            # NEU Build 117 — Bug 3.3: analog zum Normalmodus.
            # Beleg: Projektgespraech 2026-05-07
            templates_path = Path(
                self._config.get("paths.templates_db", "./data/templates.db")
            ).resolve()
            if templates_path.exists():
                self._attach_readonly(con, templates_path, "tdb")
                logger.debug("tdb angebunden (READ-ONLY, Support): '%s'", templates_path)
            else:
                logger.info(
                    "templates.db nicht gefunden — tdb nicht angebunden (Support): '%s'. "
                    "Bausteine-Bibliothek bleibt leer.",
                    templates_path,
                )

            # trdb: translations_db READ-ONLY (optional — analog Normalmodus).
            # Beleg: Bauplan Build 329 §2.3
            translations_path = Path(
                self._config.get("paths.translations_db", "./data/translations.db")
            ).resolve()
            if translations_path.exists():
                self._attach_readonly(con, translations_path, "trdb")
                logger.debug("trdb angebunden (READ-ONLY, Support): '%s'", translations_path)
            else:
                logger.info(
                    "translations.db nicht gefunden — trdb nicht angebunden (Support): '%s'. "
                    "Uebersetzungs-Buttons bleiben aus.",
                    translations_path,
                )

            # DB-Instanzen initialisieren
            # ForensicDb und DefaultDb wie im Normalmodus
            # Build 325: Fach-DB-Zugriffe ueber LockingConnection-Wrapper serialisieren
            # (SSE-Thread + Request-Threads). Beleg: Live-Diagnose 2026-07-06.
            db_con = LockingConnection(con)
            if assets_con is not None:
                assets_con = db_con          # assets nutzt dieselbe geteilte con (adb-ATTACH)

            forensic    = ForensicDb(db_con)
            # forum_base_url aus forensic_meta lesen — wird für Asset-URL-Lookup
            # benötigt, da asset_urls vollständige Onion-URLs als Schlüssel speichert
            forum_base_url = forensic.get_forum_base_url()
            default     = DefaultDb(db_con, forum_base_url=forum_base_url)
            # EvidenceDb schreibt in die TEMP-Haupt-DB
            evidence    = EvidenceDb(db_con, db_path=str(evidence_path))  # Build 098: Thread-Safety
            coordinator = CoordinatorDb(db_con)
            assets      = AssetsDb(assets_con, forum_base_url=forum_base_url)   # NEU Build 017
            templates   = TemplatesDb(db_con)          # NEU Build 089
            translations = TranslationsDb(db_con)      # NEU Build 329

            # Authorizer nach vollständigem ATTACH-Aufbau deaktivieren.
            # Hintergrund (Build 021): set_authorizer() ist nicht thread-safe
            # wenn check_same_thread=False — auf Windows führt das zu Deadlocks
            # wenn SSE-Thread und Request-Threads gleichzeitig die Connection
            # nutzen. Der Schreibschutz auf fdb/ddb/adb ist durch
            # startup_checks._check_forensic_db_readonly() und das
            # Dateisystem (Stage-2 setzt chmod/NTFS-readonly) gewährleistet.
            # Beleg: webserver_freeze.txt, Projektgespräch 2026-04-22.
            con.set_authorizer(None)
            logger.debug("Authorizer deaktiviert — Schreibschutz via Dateisystem/startup_checks.")

            logger.info(
                "Alle Verbindungen aufgebaut (Support-Modus). "
                "TEMP-DB: %s",
                "In-Memory" if temp_db_mode == "memory" else temp_db_path,
            )

            return DatabaseBundle(
                connection=db_con,   # Build 325: gewrappte (serialisierte) Verbindung
                forensic=forensic,
                default=default,
                evidence=evidence,
                coordinator=coordinator,
                assets=assets,        # NEU Build 017
                templates=templates,  # NEU Build 089
                translations=translations,  # NEU Build 329
                temp_db_path=temp_db_path,
            )

        except JournalPolicyError as exc:
            raise ConnectionManagerError(f"Support-Modus: {exc}") from exc

        except sqlite3.OperationalError as exc:
            zusatz = " — " + JOURNAL_NETWORK_HINT if "disk i/o error" in str(exc).lower() else ""
            raise ConnectionManagerError(
                f"Support-Modus: Datenbankverbindung konnte nicht aufgebaut "
                f"werden: {exc}{zusatz}"
            ) from exc

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------


    # Aliases die niemals beschreibbar sein dürfen.
    # Wird vom Authorizer ausgewertet. Beleg: Projektgespräch 2026-04-22 PROD.
    _READONLY_ALIASES: frozenset = frozenset({"fdb", "ddb", "adb", "edb"})

    # SQLite action codes für Schreiboperationen.
    # Beleg: https://www.sqlite.org/c3ref/c_alter_table.html
    _WRITE_ACTION_CODES: frozenset = frozenset({
        1,   # SQLITE_CREATE_TABLE
        3,   # SQLITE_CREATE_INDEX
        7,   # SQLITE_CREATE_VIEW
        9,   # SQLITE_DELETE
        11,  # SQLITE_DROP_TABLE
        13,  # SQLITE_DROP_INDEX
        17,  # SQLITE_DROP_VIEW
        18,  # SQLITE_INSERT
        23,  # SQLITE_UPDATE
        26,  # SQLITE_ALTER_TABLE
    })

    @classmethod
    def _make_authorizer(cls):
        """
        Erzeugt einen SQLite-Authorizer der Schreibzugriffe auf READ-ONLY-
        Aliases (fdb, ddb, adb, edb) blockiert.

        Hintergrund (Build 020): SQLite URI-Syntax mit mode=ro funktioniert
        auf Windows nicht für UNC-Pfade (\\\\server\\share\\...) — weder mit
        file:////server/... (RFC 8089, Build 019) noch in anderer Form.
        Fehler in PROD: "unable to open database: file:////prod01/..."
        Beleg: webserver_error.txt, Projektgespräch 2026-04-22.

        Lösung: ATTACH mit normalem Pfad-String (kein URI), Schreibschutz
        über Python-seitigen sqlite3.set_authorizer().

        TEMP-Operationen (blob_lookup TEMP VIEW, db_name='temp') sind nie
        in _READONLY_ALIASES — werden immer erlaubt. Das ist der entscheidende
        Unterschied zu PRAGMA query_only = ON (wirkt global, blockiert TEMP VIEW).
        Beleg: set_authorizer()-Doku, empirisch verifiziert Build 020.
        """
        readonly  = cls._READONLY_ALIASES
        write_ops = cls._WRITE_ACTION_CODES

        def authorizer(action_code, arg1, arg2, db_name, trigger_name):
            if action_code in write_ops and db_name in readonly:
                return 1   # SQLITE_DENY
            return 0       # SQLITE_OK

        return authorizer

    def _attach_readonly(
        self, con: sqlite3.Connection, path: Path, alias: str
    ) -> None:
        """
        Bindet eine DB im READ-ONLY-Modus per ATTACH an.

        Schreibschutz (Build 020): URI mode=ro ist auf Windows für UNC-Pfade
        nicht verwendbar. ATTACH verwendet normalen Pfad-String, Schreibschutz
        wird über set_authorizer() sichergestellt.
        Beleg: Projektgespräch 2026-04-22 — UNC-Pfad-Problem PROD.

        set_authorizer() wird nach jedem ATTACH neu gesetzt, da SQLite pro
        Connection nur einen Authorizer kennt.

        Args:
            con:   Geöffnete Hauptverbindung.
            path:  Absoluter Pfad zur anzubindenden DB.
            alias: ATTACH-Alias-Name (fdb, ddb, adb, edb).

        Raises:
            sqlite3.OperationalError: Wenn ATTACH fehlschlägt.
        """
        con.execute("ATTACH DATABASE ? AS " + alias, (str(path),))
        con.set_authorizer(self._make_authorizer())
        logger.debug("ATTACH %s (READ-ONLY via Authorizer): '%s'", alias, path)
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
