# =============================================================================
# core/logger.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Konfiguriert das projektweite Logging-System und stellt eine einheitliche
#   get_logger()-Fabrikfunktion bereit. Alle Module des Projekts beziehen
#   ihren Logger ausschließlich über diese Funktion.
#
# Zwei Log-Handler (immer beide aktiv):
#   (1) Konsolenausgabe (StreamHandler → stderr)
#   (2) Rotierende Logdatei (RotatingFileHandler)
#       Rotation bei max_bytes, backup_count Sicherungsdateien.
#
# Log-Level:
#   info  — Normalbetrieb: Serverstart, Requests, Fehler, Warnungen
#   debug — Entwicklung: zusätzlich SQL-Queries, Request-Timing, BLOB-Lookup-Pfade
#
# Initialisierung:
#   Einmalig beim Serverstart durch main.py via setup_logging(config).
#   Danach holt sich jedes Modul seinen Logger per get_logger(__name__).
#
# Forensische Relevanz:
#   Das Logfile ist ein Betriebsprotokoll, kein Beweismittel. Es dokumentiert
#   den technischen Ablauf des Werkzeugs, nicht die Ermittlungsergebnisse.
#   Ermittlungsrelevante Daten landen ausschließlich in evidence_db.
#
# Abhängigkeiten: logging, logging.handlers — ausschließlich Stdlib
# Version: v0.1.0 · Build: 002 · 2026-04-10
# =============================================================================

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional

from core.config_loader import ConfigLoader


# ---------------------------------------------------------------------------
# Interner Zustand: Initialisierungsflag
# Verhindert doppelte Handler-Registrierung bei mehrfachem setup_logging()-Aufruf
# (kann in Tests auftreten).
# ---------------------------------------------------------------------------
_is_initialized: bool = False

# Name des Root-Loggers für dieses Projekt.
# Alle Modul-Logger sind Kinder dieses Loggers (z.B. "forensic.core.config_loader").
_ROOT_LOGGER_NAME: str = "forensic"

# Datumsformat für alle Log-Einträge (ISO 8601, Sekunden-Präzision)
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# Format für Konsolenausgabe: kompakt, gut lesbar im Terminal
_CONSOLE_FORMAT: str = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"

# Format für Logdatei: vollständiger Pfad für Nachverfolgbarkeit
_FILE_FORMAT: str = (
    "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
)


def setup_logging(config: ConfigLoader) -> None:
    """
    Initialisiert das Logging-System anhand der geladenen Konfiguration.
    Muss einmalig beim Serverstart aufgerufen werden, bevor get_logger()
    verwendet wird.

    Idempotent: Mehrfachaufrufe haben keine doppelten Handler zur Folge.

    Args:
        config: Geladene ConfigLoader-Instanz. Relevante Schlüssel:
                logging.level        — "info" oder "debug"
                logging.logfile      — Pfad zur Logdatei
                logging.max_bytes    — Maximale Dateigröße vor Rotation
                logging.backup_count — Anzahl der Rotationsdateien
    """
    global _is_initialized

    if _is_initialized:
        # Bereits initialisiert — kein doppeltes Setup.
        # Tritt in Tests auf, wenn setup_logging() mehrfach aufgerufen wird.
        return

    # Log-Level aus Konfiguration auflösen
    level_str: str = config.get("logging.level", "info").upper()
    level: int = getattr(logging, level_str, logging.INFO)

    # Root-Logger des Projekts konfigurieren
    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    root_logger.setLevel(level)

    # Handler 1: Konsolenausgabe (stderr)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(
        logging.Formatter(fmt=_CONSOLE_FORMAT, datefmt=_DATE_FORMAT)
    )
    root_logger.addHandler(console_handler)

    # Handler 2: Rotierende Logdatei
    logfile_path = config.get("logging.logfile", "./logs/forensic_server.log")
    max_bytes = config.get("logging.max_bytes", 10 * 1024 * 1024)
    backup_count = config.get("logging.backup_count", 5)

    # Verzeichnis anlegen, falls es nicht existiert
    logfile_dir = Path(logfile_path).parent
    logfile_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=logfile_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(fmt=_FILE_FORMAT, datefmt=_DATE_FORMAT)
    )
    root_logger.addHandler(file_handler)

    # Propagation zum Python-Root-Logger deaktivieren —
    # verhindert doppelte Ausgaben durch den Standard-Root-Logger.
    root_logger.propagate = False

    _is_initialized = True

    # Erster Logeintrag: Bestätigung der Initialisierung
    root_logger.info(
        "Logging initialisiert — Level: %s, Logdatei: %s",
        level_str,
        Path(logfile_path).resolve(),
    )


def get_logger(name: str) -> logging.Logger:
    """
    Gibt einen benannten Logger zurück, der dem Projekt-Root-Logger untergeordnet ist.

    Verwendung in jedem Modul:
        from core.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Server gestartet auf %s:%d", host, port)
        logger.debug("SQL: %s | Params: %s", query, params)

    Der Logger-Name wird als "<modul>.<submodul>"-Pfad aufgebaut, z.B.:
        core.config_loader → forensic.core.config_loader
        server.router      → forensic.server.router

    Falls setup_logging() noch nicht aufgerufen wurde, gibt die Funktion einen
    Logger zurück, der nur auf dem Python-Root-Logger basiert (Fallback).
    In der Produktion ist setup_logging() immer vor get_logger() aufzurufen.

    Args:
        name: Typischerweise __name__ des aufrufenden Moduls.

    Returns:
        logging.Logger-Instanz, dem Projekt-Root-Logger untergeordnet.
    """
    # Modulpfad unter den Projekt-Root-Logger hängen,
    # damit alle Projekt-Logger hierarchisch gebündelt sind.
    if name.startswith(_ROOT_LOGGER_NAME + "."):
        # Bereits korrekt prefixiert (kann bei direktem Aufruf vorkommen)
        logger_name = name
    elif name == "__main__":
        logger_name = _ROOT_LOGGER_NAME
    else:
        logger_name = f"{_ROOT_LOGGER_NAME}.{name}"

    return logging.getLogger(logger_name)


def reset_for_testing() -> None:
    """
    Setzt den Initialisierungszustand zurück und entfernt alle Handler
    vom Projekt-Root-Logger.

    NUR für Unit-Tests verwenden. Im Produktionsbetrieb niemals aufrufen.
    Ermöglicht mehrfaches setup_logging() in derselben Test-Session.
    """
    global _is_initialized
    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)
    _is_initialized = False
