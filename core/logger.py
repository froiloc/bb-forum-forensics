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
#   Einmalig beim Serverstart durch main.py.
#   Zwei Aufrufvarianten (beide unterstützt — rückwärtskompatibel):
#
#   Variante A (Tests, legacy): setup_logging(config)
#     config ist eine ConfigLoader-Instanz.
#
#   Variante B (main.py): setup_logging(level=..., logfile=..., ...)
#     Einzelparameter direkt.
#
# Änderungen gegenüber Build 002 (Build 013):
#   - setup_logging() akzeptiert nun beide Aufrufvarianten (A und B).
#     Variante B entspricht dem Aufruf in main.py:
#       setup_logging(level="info", logfile="...", max_bytes=N, backup_count=N)
#     Variante A (config-Objekt) bleibt erhalten für Rückwärtskompatibilität.
#
# Abhängigkeiten: logging, logging.handlers — ausschließlich Stdlib
# Version: v0.1.0 · Build: 013 · 2026-04-14
# =============================================================================

import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from core.config_loader import ConfigLoader


# ---------------------------------------------------------------------------
# Interner Zustand: Initialisierungsflag
# ---------------------------------------------------------------------------
_is_initialized: bool = False

_ROOT_LOGGER_NAME: str = "forensic"
_DATE_FORMAT:      str = "%Y-%m-%d %H:%M:%S"
_CONSOLE_FORMAT:   str = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_FILE_FORMAT:      str = (
    "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
)


def setup_logging(
    config_or_level: "Union[ConfigLoader, str, None]" = None,
    *,
    level:        Optional[str] = None,
    logfile:      Optional[str] = None,
    max_bytes:    Optional[int] = None,
    backup_count: Optional[int] = None,
) -> None:
    """
    Initialisiert das Logging-System. Idempotent.

    Variante A — config-Objekt (Tests / Legacy):
        setup_logging(config)          # config ist ConfigLoader-Instanz

    Variante B — Einzelparameter (main.py):
        setup_logging(
            level="info",
            logfile="./logs/forensic_server.log",
            max_bytes=10*1024*1024,
            backup_count=5,
        )

    Beide Varianten sind äquivalent. Variante B hat Vorrang vor Variante A
    wenn Einzelparameter explizit angegeben werden.

    Args:
        config_or_level: ConfigLoader-Instanz (Variante A) oder None.
        level:           Log-Level-String: "info" oder "debug".
        logfile:         Pfad zur rotierenden Logdatei.
        max_bytes:       Maximale Dateigröße vor Rotation.
        backup_count:    Anzahl der Rotationsdateien.
    """
    global _is_initialized

    if _is_initialized:
        return

    # ---- Werte auflösen ------------------------------------------------
    # Einzelparameter (Variante B) haben Vorrang über config-Objekt (Variante A).

    _level_str      = "INFO"
    _logfile        = "./logs/forensic_server.log"
    _max_bytes      = 10 * 1024 * 1024
    _backup_count   = 5

    # Variante A: config-Objekt
    if config_or_level is not None and not isinstance(config_or_level, str):
        cfg = config_or_level
        _level_str    = str(cfg.get("logging.level",        "info")).upper()
        _logfile      = str(cfg.get("logging.logfile",      _logfile))
        _max_bytes    = int(cfg.get("logging.max_bytes",    _max_bytes))
        _backup_count = int(cfg.get("logging.backup_count", _backup_count))

    # Variante B: Einzelparameter überschreiben
    if level is not None:
        _level_str = level.upper()
    if logfile is not None:
        _logfile = logfile
    if max_bytes is not None:
        _max_bytes = int(max_bytes)
    if backup_count is not None:
        _backup_count = int(backup_count)

    # ---- Logging aufbauen -----------------------------------------------

    numeric_level: int = getattr(logging, _level_str, logging.INFO)

    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    root_logger.setLevel(numeric_level)

    # Handler 1: Konsolenausgabe (stderr)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(
        logging.Formatter(fmt=_CONSOLE_FORMAT, datefmt=_DATE_FORMAT)
    )
    root_logger.addHandler(console_handler)

    # Handler 2: Rotierende Logdatei
    logfile_dir = Path(_logfile).parent
    logfile_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=_logfile,
        maxBytes=_max_bytes,
        backupCount=_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(
        logging.Formatter(fmt=_FILE_FORMAT, datefmt=_DATE_FORMAT)
    )
    root_logger.addHandler(file_handler)

    root_logger.propagate = False
    _is_initialized = True

    root_logger.info(
        "Logging initialisiert — Level: %s, Logdatei: %s",
        _level_str,
        Path(_logfile).resolve(),
    )


def get_logger(name: str) -> logging.Logger:
    """
    Gibt einen benannten Logger zurück, der dem Projekt-Root-Logger untergeordnet ist.

    Verwendung in jedem Modul:
        from core.logger import get_logger
        logger = get_logger(__name__)
    """
    if name.startswith(_ROOT_LOGGER_NAME + "."):
        logger_name = name
    elif name == "__main__":
        logger_name = _ROOT_LOGGER_NAME
    else:
        logger_name = f"{_ROOT_LOGGER_NAME}.{name}"

    return logging.getLogger(logger_name)


def reset_for_testing() -> None:
    """
    Setzt den Initialisierungszustand zurück und entfernt alle Handler.
    NUR für Unit-Tests verwenden. Im Produktionsbetrieb niemals aufrufen.
    """
    global _is_initialized
    root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)
    _is_initialized = False
