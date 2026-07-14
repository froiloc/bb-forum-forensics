# =============================================================================
# db/journal_policy.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2/7: Datenbankschicht
# =============================================================================
# Zweck:
#   EINZIGE Stelle im Projekt, an der der SQLite-Journalmodus gesetzt wird.
#   Ersetzt die bisher 14-fach hartkodierte Zeile 'PRAGMA journal_mode=WAL'.
#
# Warum es diesen Helfer gibt (Beleg: Diagnose 2026-07-14, Testsystem S:\):
#   Der Webserver startete von einem Netzlaufwerk (UNC \\KK31Storage15\..., von
#   Windows als DriveType=4 REMOTE gemeldet) nicht mehr:
#       sqlite3.OperationalError: disk I/O error   (extended code 8714)
#   Ursache ist keine Fehlfunktion unseres Codes, sondern eine Architekturgrenze
#   von SQLite: Der wal-index (Sperr-/Positionsindex fuer Leser) liegt in Shared
#   Memory, das SQLite als '-shm'-Datei per mmap im DB-Verzeichnis anlegt. Weil
#   Shared Memory nur maschinenlokal funktioniert, ist WAL auf Netzwerk-
#   Dateisystemen ausdruecklich nicht unterstuetzt (sqlite.org/wal.html).
#
#   Empirisch gemessen auf ebendiesem Share (nicht gerechnet, Grundregel
#   'Messen, nicht rechnen'):
#       WAL                     -> disk I/O error
#       DELETE / TRUNCATE       -> OK (schreiben + zuruecklesen bestaetigt)
#       WAL + locking_mode=EXCL -> OK (aber sperrt andere Prozesse aus -> nicht
#                                  fuer den Regelbetrieb, coordinator.db wird
#                                  auch vom Management-Server geoeffnet)
#   Lokal (C:, DriveType=3 FIXED) ist WAL unauffaellig.
#
# Strategie ('auto', Default):
#   1. WAL versuchen — das ist der PROD-Pfad. Gelingt er (lokale Platte), ist das
#      Verhalten bitidentisch zu vor Build 408.
#   2. Scheitert er, wird NICHT still weitergemacht (Grundregel 1): WARNING mit
#      Pfad, Basis- und erweitertem SQLite-Fehlercode und Klartextursache, dann
#      Rueckfall auf den Rollback-Journalmodus (Default: DELETE).
#   3. Der tatsaechlich aktive Modus wird ZURUECKGELESEN und geprueft. Ein
#      erfolgreiches PRAGMA allein ist kein Beleg ('gruen aber tot' vermeiden):
#      SQLite meldet z.B. bei read-only geoeffneten DBs den ALTEN Modus zurueck,
#      ohne einen Fehler zu werfen.
#   4. Gelingt auch der Rueckfall nicht, wird hart abgebrochen (JournalPolicyError)
#      — mit Klartext, was zu tun ist.
#
# Wichtig — was dieser Helfer NICHT kann:
#   Eine bereits WAL-GESTEMPELTE Datei (Header-Byte 18/19 == 2) laesst sich auf
#   einem Netzlaufwerk nicht einmal lesend oeffnen. Solche Bestandsdateien muessen
#   EINMALIG umgestempelt werden: tools/convert_journal_mode.py.
#
# Konfiguration (config.yaml):
#   db:
#     journal_mode:          auto | wal | delete | truncate | persist
#     journal_mode_fallback: delete | truncate | persist
#
# Abhaengigkeiten: sqlite3, logging — Stdlib + core.logger
# Version: v0.7.408 · Build: 408 · 2026-07-14
# =============================================================================

from __future__ import annotations

import ctypes
import os
import sqlite3
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)

# Zulaessige Werte fuer db.journal_mode.
# 'auto' ist kein SQLite-Modus, sondern unsere Strategie (WAL, sonst Rueckfall).
VALID_MODES = ("auto", "wal", "delete", "truncate", "persist")

# Zulaessige Rueckfallziele. MEMORY/OFF sind bewusst NICHT dabei: beide geben
# die Absturzsicherheit auf (kein Rollback-Journal auf Platte). In einem
# forensischen Werkzeug ist ein langsamer, aber transaktionssicherer Modus
# immer einem schnellen, aber verlustgefaehrdeten vorzuziehen.
VALID_FALLBACKS = ("delete", "truncate", "persist")

DEFAULT_MODE = "auto"
DEFAULT_FALLBACK = "delete"

# Sonderfall In-Memory-Datenbank (Support-Modus, Tests): eine ':memory:'-DB
# meldet IMMER journal_mode='memory' und laesst sich weder auf WAL noch auf ein
# Rollback-Journal umstellen — das PRAGMA laeuft fehlerfrei durch, aendert aber
# nichts. Das ist KEIN Fehler (es gibt keine Datei und damit auch kein Journal
# auf Platte), sondern die korrekte Antwort von SQLite. Sie wird als solche
# erkannt, protokolliert und akzeptiert — statt sie in einen Rueckfall oder gar
# einen Abbruch laufen zu lassen. Beleg: Regression Build 408
# (tests/test_connection_manager.py::TestConnectionManagerSupport).
MEMORY_MODE = "memory"

# Klartexthinweis, der jeder Fehlermeldung beigegeben wird. Er soll dem naechsten
# Menschen die zwei Stunden Suche ersparen, die uns dieser Fehler gekostet hat.
# Build 409: Der urspruengliche Text riet dazu, db.journal_mode auf 'delete' zu
# setzen — genau das war beim Auftreten des Fehlers aber schon geschehen. Der
# Fehlschlag hatte eine ANDERE Ursache: die DATEI war noch WAL-gestempelt, und
# um WAL zu verlassen, muss SQLite die WAL-Datei auschecken — wofuer es die
# '-shm' braucht, die auf einem Netzlaufwerk nicht anzulegen ist. Der Hinweis
# nennt deshalb jetzt zuerst die Datei, nicht die Konfiguration.
# Beleg: Live-Diagnose 2026-07-14 (evidence_524888.db war als einzige DB noch
# WAL-gestempelt; alle uebrigen Pruefungen auf demselben Share waren gruen).
NETWORK_HINT = (
    "Haeufigste Ursache: die DATENBANKDATEI ist noch WAL-gestempelt "
    "(SQLite-Header-Byte 18/19 == 2). Um WAL zu verlassen, muss SQLite die "
    "WAL-Datei auschecken und braucht dafuer die '-shm'-Datei — die auf einem "
    "Netzlaufwerk (UNC/SMB) nicht angelegt werden kann, weil Shared Memory "
    "maschinenlokal ist (sqlite.org/wal.html). PRUEFEN und BEHEBEN: "
    "'python tools/convert_journal_mode.py --data-dir ./data' (Trockenlauf, "
    "zeigt den Header-Stempel jeder DB), dann mit '--apply' umstempeln. "
    "Die Einstellung db.journal_mode in der config.yaml allein behebt das NICHT "
    "— sie steuert nur, was der Server neu setzt, nicht den Stempel der "
    "vorhandenen Dateien."
)


def is_network_path(path: object) -> Optional[bool]:
    r"""
    Prueft, ob ein Pfad auf einem Netzlaufwerk liegt.

    Rueckgabe:
        True  — Netzlaufwerk (UNC-Pfad oder gemapptes Laufwerk mit DriveType=4)
        False — lokales Laufwerk
        None  — nicht entscheidbar (kein Windows, keine Laufwerksinformation)

    Zwei Wege, bewusst in dieser Reihenfolge:
      1. UNC-Praefix ('\\server\share') — plattformunabhaengig und ohne API-Aufruf.
      2. Windows GetDriveTypeW() fuer gemappte Laufwerksbuchstaben (S: -> \\...).
         DRIVE_REMOTE == 4. Belegt: Diagnose 2026-07-14 meldete fuer
         '\\KK31Storage15\Volume 1\' DriveType=4, fuer 'C:\' DriveType=3.

    Kein Raten: Wo keine Aussage moeglich ist, wird None zurueckgegeben und der
    Aufrufer entscheidet — statt eine Vermutung als Tatsache zu behandeln.
    """
    text = str(path)
    if text.startswith("\\\\") or text.startswith("//"):
        return True
    if os.name != "nt":
        return None
    try:
        laufwerk, _rest = os.path.splitdrive(os.path.abspath(text))
        if not laufwerk:
            return None
        wurzel = laufwerk + "\\"
        typ = ctypes.windll.kernel32.GetDriveTypeW(   # type: ignore[attr-defined]
            ctypes.c_wchar_p(wurzel)
        )
        DRIVE_REMOTE = 4
        return typ == DRIVE_REMOTE
    except Exception:                                  # pragma: no cover
        return None


def journal_stamp(path: object) -> Optional[int]:
    """
    Liest den Journal-Stempel aus dem SQLite-Header (Byte 18, write_version).

    Rueckgabe: 1 = Rollback-Journal, 2 = WAL, None = keine lesbare SQLite-Datei.

    Bewusst OHNE SQLite: Eine WAL-gestempelte Datei laesst sich auf einem
    Netzlaufwerk gar nicht erst oeffnen — die Pruefung muss deshalb VOR jedem
    SQLite-Zugriff moeglich sein. 100 Bytes lesen genuegt.
    """
    try:
        with open(str(path), "rb") as fh:
            hdr = fh.read(100)
    except OSError:
        return None
    if len(hdr) < 100 or not hdr.startswith(b"SQLite format 3\x00"):
        return None
    return hdr[18]


class JournalPolicyError(RuntimeError):
    """Wird geworfen, wenn WEDER der gewuenschte NOCH der Rueckfallmodus greift."""


def describe_sqlite_error(exc: sqlite3.Error) -> str:
    """
    Formatiert einen SQLite-Fehler inklusive erweitertem Fehlercode.

    Der erweiterte Code ist hier der eigentliche Erkenntnisgewinn — er
    unterscheidet ein Shared-Memory-/mmap-Problem (WAL auf Netzlaufwerk) von
    einem echten Sperr- oder Rechteproblem. Python 3.11+ liefert ihn ueber
    exc.sqlite_errorcode / exc.sqlite_errorname; unbekannte (neuere) Subcodes
    meldet Python als 'unknown', der Zahlenwert bleibt aber aussagekraeftig.
    """
    name = getattr(exc, "sqlite_errorname", "?")
    code = getattr(exc, "sqlite_errorcode", "?")
    return f"{type(exc).__name__}: {exc} [{name} / {code}]"


def resolve_mode(config, key: str = "db.journal_mode") -> str:
    """
    Liest den gewuenschten Journalmodus aus der Konfiguration.

    Unbekannte Werte werden NICHT still auf den Default gebogen — sie sind ein
    Konfigurationsfehler und werden als solcher gemeldet (Grundregel 1).
    """
    raw = config.get(key, DEFAULT_MODE) if config is not None else DEFAULT_MODE
    mode = str(raw or DEFAULT_MODE).strip().lower()
    if mode not in VALID_MODES:
        raise JournalPolicyError(
            f"Unzulaessiger Wert fuer {key}: '{raw}'. "
            f"Erlaubt: {', '.join(VALID_MODES)}."
        )
    return mode


def resolve_fallback(config, key: str = "db.journal_mode_fallback") -> str:
    """Liest das Rueckfallziel fuer den 'auto'-Modus aus der Konfiguration."""
    raw = config.get(key, DEFAULT_FALLBACK) if config is not None else DEFAULT_FALLBACK
    fb = str(raw or DEFAULT_FALLBACK).strip().lower()
    if fb not in VALID_FALLBACKS:
        raise JournalPolicyError(
            f"Unzulaessiger Wert fuer {key}: '{raw}'. "
            f"Erlaubt: {', '.join(VALID_FALLBACKS)}."
        )
    return fb


def _set_and_read_back(
    con: sqlite3.Connection,
    prefix: str,
    mode: str,
) -> str:
    """
    Setzt den Journalmodus und liest ihn ZURUECK.

    Rueckgabe: der tatsaechlich aktive Modus (lowercase).
    Das PRAGMA gibt den aktiven Modus selbst zurueck; wir lesen zusaetzlich
    separat nach, damit auch ein leeres Ergebnis (theoretisch moeglich) auffliegt.
    """
    row = con.execute(f"PRAGMA {prefix}journal_mode={mode}").fetchone()
    _ = row  # Rueckgabe des Setz-PRAGMA wird bewusst nicht als Beleg verwendet.
    check = con.execute(f"PRAGMA {prefix}journal_mode").fetchone()
    if not check:
        raise JournalPolicyError(
            f"PRAGMA {prefix}journal_mode lieferte kein Ergebnis — "
            f"Journalmodus nicht verifizierbar."
        )
    value = check[0]
    return str(value).strip().lower()


def apply_journal_mode(
    con: sqlite3.Connection,
    db_path: object = "<unbekannt>",
    *,
    schema: str = "main",
    mode: str = DEFAULT_MODE,
    fallback: str = DEFAULT_FALLBACK,
    log: Optional[object] = None,
) -> str:
    """
    Setzt den Journalmodus fuer 'schema' auf der Verbindung 'con'.

    Args:
        con:      Offene sqlite3-Verbindung.
        db_path:  Nur fuer Protokoll/Fehlermeldung (Pfad der Datei).
        schema:   'main' oder ein ATTACH-Alias (z.B. 'cdb').
        mode:     'auto' | 'wal' | 'delete' | 'truncate' | 'persist'
        fallback: Ziel des Rueckfalls im 'auto'-Modus.
        log:      Logger (Default: Modul-Logger).

    Returns:
        Der tatsaechlich aktive Journalmodus (lowercase), z.B. 'wal' oder 'delete'.

    Raises:
        JournalPolicyError: Wenn kein tragfaehiger Modus gesetzt werden konnte
                            oder die Konfiguration unzulaessig ist.
    """
    lg = log or logger

    if mode not in VALID_MODES:
        raise JournalPolicyError(
            f"Unzulaessiger Journalmodus: '{mode}'. Erlaubt: {', '.join(VALID_MODES)}."
        )
    if fallback not in VALID_FALLBACKS:
        raise JournalPolicyError(
            f"Unzulaessiges Rueckfallziel: '{fallback}'. "
            f"Erlaubt: {', '.join(VALID_FALLBACKS)}."
        )

    prefix = "" if schema in ("", "main") else f"{schema}."

    # --- Fall 1: expliziter Modus (kein Rueckfall, kein Ratespiel) ------------
    if mode != "auto":
        try:
            aktiv = _set_and_read_back(con, prefix, mode)
        except sqlite3.Error as exc:
            raise JournalPolicyError(
                f"Journalmodus '{mode}' konnte fuer '{db_path}' (schema='{schema}') "
                f"nicht gesetzt werden. {describe_sqlite_error(exc)}. {NETWORK_HINT}"
            ) from exc
        if aktiv == MEMORY_MODE and mode != MEMORY_MODE:
            lg.debug(
                "In-Memory-Datenbank (db='%s', schema='%s'): journal_mode bleibt "
                "'memory' — kein Journal auf Platte noetig.", db_path, schema,
            )
            return aktiv
        if aktiv != mode:
            raise JournalPolicyError(
                f"Journalmodus '{mode}' wurde fuer '{db_path}' (schema='{schema}') "
                f"NICHT uebernommen — aktiv ist '{aktiv}'. "
                f"(Kein stiller Weiterbetrieb: Grundregel 1.) {NETWORK_HINT}"
            )
        lg.debug(
            "Journalmodus '%s' gesetzt (schema='%s', db='%s').",
            aktiv, schema, db_path,
        )
        return aktiv

    # --- Fall 2: 'auto' — erst WAL, sonst Rueckfall ---------------------------
    try:
        aktiv = _set_and_read_back(con, prefix, "wal")
        if aktiv == "wal":
            lg.debug(
                "Journalmodus 'wal' gesetzt (schema='%s', db='%s').", schema, db_path
            )
            return aktiv
        if aktiv == MEMORY_MODE:
            lg.debug(
                "In-Memory-Datenbank (db='%s', schema='%s'): journal_mode bleibt "
                "'memory' — kein Journal auf Platte noetig.", db_path, schema,
            )
            return aktiv
        # Kein Fehler, aber auch kein WAL: SQLite meldet in diesem Fall den alten
        # Modus zurueck (z.B. bei read-only geoeffneter Datei). Das ist genau der
        # Fall, den ein reines try/except NICHT faengt.
        grund = f"PRAGMA lief fehlerfrei durch, aktiv blieb aber '{aktiv}'"
    except sqlite3.Error as exc:
        grund = describe_sqlite_error(exc)

    lg.warning(
        "WAL-Modus nicht verfuegbar fuer '%s' (schema='%s'): %s. "
        "Rueckfall auf '%s'. %s",
        db_path, schema, grund, fallback, NETWORK_HINT,
    )

    try:
        aktiv = _set_and_read_back(con, prefix, fallback)
    except sqlite3.Error as exc:
        raise JournalPolicyError(
            f"Weder 'wal' noch Rueckfall '{fallback}' konnten fuer '{db_path}' "
            f"(schema='{schema}') gesetzt werden. {describe_sqlite_error(exc)}. "
            f"{NETWORK_HINT}"
        ) from exc

    if aktiv != fallback:
        raise JournalPolicyError(
            f"Rueckfall-Journalmodus '{fallback}' wurde fuer '{db_path}' "
            f"(schema='{schema}') NICHT uebernommen — aktiv ist '{aktiv}'. "
            f"{NETWORK_HINT}"
        )

    lg.info(
        "Journalmodus-Rueckfall aktiv: '%s' (schema='%s', db='%s'). "
        "Parallelitaet ist damit geringer als mit WAL — das ist gewollt und "
        "protokolliert.",
        aktiv, schema, db_path,
    )
    return aktiv
