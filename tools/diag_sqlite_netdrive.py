#!/usr/bin/env python3
# =============================================================================
# tools/diag_sqlite_netdrive.py
# IT-Forensisches Ermittlungswerkzeug — DIAGNOSE-Werkzeug (Baustelle 2)
# =============================================================================
# Zweck:
#   Klaert empirisch, warum 'PRAGMA journal_mode=WAL' auf dem Netzlaufwerk
#   mit 'disk I/O error' scheitert, und welche Journal-/Locking-Modi auf
#   diesem Share tatsaechlich tragfaehig sind.
#
# Forensische Sorgfalt (Grundregel 1 — keine stillen Aenderungen):
#   * Die ECHTEN Datenbanken werden AUSSCHLIESSLICH LESEND angefasst:
#       - Header-Bytes 16..19 werden direkt aus der Datei gelesen (kein SQLite).
#       - SQLite-Zugriff nur ueber URI 'mode=ro' + 'immutable=0'.
#     Es wird KEIN PRAGMA gesetzt, das den Header veraendern koennte.
#   * Alle Schreib-/Modus-Experimente laufen auf einer TEMPORAEREN Probe-DB
#     ('_probe_<pid>.db') im SELBEN Verzeichnis. Diese wird am Ende geloescht.
#   * Zusaetzlich wird dieselbe Testmatrix auf einem LOKALEN Verzeichnis
#     gefahren (Vergleichsgruppe) — nur so ist belegbar, dass die Ursache das
#     Netzlaufwerk ist und nicht der Code.
#
# Aufruf (in der VM, aus dem Verzeichnis des Webservers, also z.B. S:\):
#     python tools/diag_sqlite_netdrive.py --data-dir .\data
#
# Ausgabe: Konsole + Datei 'diag_sqlite_netdrive.log' im aktuellen Verzeichnis.
# Abhaengigkeiten: nur Stdlib (Python 3.11+ wegen exc.sqlite_errorname).
# Version: v0.7.409 · Build: 409 · 2026-07-14 (in tools/ uebernommen)
# =============================================================================

from __future__ import annotations

import argparse
import ctypes
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

LOGLINES: list[str] = []


def log(msg: str = "") -> None:
    """Gibt eine Zeile aus und merkt sie fuer die Logdatei vor."""
    print(msg)
    LOGLINES.append(msg)


# -----------------------------------------------------------------------------
# 1) Datei-/Volume-Ebene — ohne SQLite
# -----------------------------------------------------------------------------

def volume_info(path: Path) -> str:
    """
    Ermittelt (best effort, nur Windows) Laufwerkstyp und Dateisystemnamen.
    Beleg fuer die Behauptung 'das ist ein Netzlaufwerk' — nicht geraten.
    """
    try:
        p = path.resolve()
        drive, _rest = os.path.splitdrive(str(p))
        if drive.startswith("\\\\"):
            # UNC: Wurzel ist \\server\share\
            parts = str(p).split("\\")
            root = "\\\\" + parts[2] + "\\" + parts[3] + "\\"
        else:
            root = drive + "\\"

        if os.name != "nt":
            return f"root={root} (Nicht-Windows — GetDriveType nicht verfuegbar)"

        k32 = ctypes.windll.kernel32                      # type: ignore[attr-defined]
        dtype = k32.GetDriveTypeW(ctypes.c_wchar_p(root))
        names = {0: "UNKNOWN", 1: "NO_ROOT_DIR", 2: "REMOVABLE",
                 3: "FIXED (lokal)", 4: "REMOTE (Netzlaufwerk)",
                 5: "CDROM", 6: "RAMDISK"}
        fsname = ctypes.create_unicode_buffer(64)
        volname = ctypes.create_unicode_buffer(261)
        k32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), volname, 261,
            None, None, None, fsname, 64,
        )
        return (f"root={root} DriveType={dtype} ({names.get(dtype, '?')}) "
                f"FS='{fsname.value}' Volume='{volname.value}'")
    except Exception as exc:                              # pragma: no cover
        return f"Volume-Info nicht ermittelbar: {exc!r}"


def header_info(db: Path) -> str:
    """
    Liest die SQLite-Header-Bytes direkt aus der Datei (KEIN SQLite-Zugriff).
    Byte 18 = write_version, Byte 19 = read_version:
        1 = Rollback-Journal (legacy)   2 = WAL
    Das ist die einzige verlaessliche Aussage darueber, ob eine DB bereits
    als WAL-DB gestempelt ist — eine WAL-gestempelte DB laesst sich auf einem
    Netzlaufwerk NICHT oeffnen, auch nicht lesend.
    """
    try:
        with db.open("rb") as fh:
            hdr = fh.read(100)
    except OSError as exc:
        return f"Header nicht lesbar: {exc!r}"

    if len(hdr) < 100 or not hdr.startswith(b"SQLite format 3\x00"):
        return f"KEINE SQLite-Datei (magic fehlt), {len(hdr)} Bytes gelesen"

    wv, rv = hdr[18], hdr[19]
    mode = {1: "rollback-journal", 2: "WAL"}
    page_size = int.from_bytes(hdr[16:18], "big")
    if page_size == 1:
        page_size = 65536
    return (f"write_version={wv} ({mode.get(wv, '?')}), "
            f"read_version={rv} ({mode.get(rv, '?')}), page_size={page_size}")


def sidecars(db: Path) -> str:
    """Meldet vorhandene -wal / -shm / -journal Begleitdateien mit Groesse."""
    out = []
    for suffix in ("-wal", "-shm", "-journal"):
        s = db.with_name(db.name + suffix)
        if s.exists():
            out.append(f"{suffix}={s.stat().st_size}B")
    return ", ".join(out) if out else "keine (-wal/-shm/-journal)"


# -----------------------------------------------------------------------------
# 2) SQLite-Ebene — echte DBs NUR lesend
# -----------------------------------------------------------------------------

def err(exc: sqlite3.Error) -> str:
    """Formatiert einen SQLite-Fehler MIT erweitertem Fehlercode.

    Der erweiterte Code ist hier der eigentliche Erkenntnisgewinn:
    SQLITE_IOERR_SHMOPEN/SHMMAP/SHMSIZE  -> Shared Memory (-shm) scheitert = WAL-Problem
    SQLITE_IOERR_LOCK / SQLITE_BUSY      -> Locking auf dem Share scheitert  = groesseres Problem
    """
    name = getattr(exc, "sqlite_errorname", "?")
    code = getattr(exc, "sqlite_errorcode", "?")
    return f"{type(exc).__name__}: {exc} [{name} / {code}]"


def read_only_check(db: Path) -> None:
    """Oeffnet die DB streng read-only und liest den aktiven journal_mode."""
    uri = "file:" + str(db).replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5.0)
        try:
            jm = con.execute("PRAGMA journal_mode").fetchone()[0]
            n = con.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
            log(f"      Lesetest (mode=ro): OK — journal_mode='{jm}', "
                f"{n} Objekte in sqlite_master")
        finally:
            con.close()
    except sqlite3.Error as exc:
        log(f"      Lesetest (mode=ro): FEHLGESCHLAGEN — {err(exc)}")


# -----------------------------------------------------------------------------
# 3) Probe-DB — hier und NUR hier wird geschrieben
# -----------------------------------------------------------------------------

def probe_matrix(directory: Path, label: str) -> None:
    """
    Legt eine frische Probe-DB im Zielverzeichnis an und testet die Kandidaten-
    Modi. Jeder Test: Modus setzen -> Tabelle anlegen -> schreiben -> committen
    -> zurueckelesen. Erst dann gilt ein Modus als tragfaehig ('gruen aber tot'
    vermeiden: ein erfolgreiches PRAGMA allein beweist noch keinen Schreibpfad).
    """
    log()
    log(f"  --- Schreibtest-Matrix in {label}: {directory}")
    if not directory.is_dir():
        log(f"      Verzeichnis existiert nicht — uebersprungen.")
        return

    # Kandidaten: (Beschreibung, Liste von PRAGMAs in Reihenfolge)
    kandidaten = [
        ("WAL (aktueller Code, Zeile 203)", ["journal_mode=WAL"]),
        ("WAL + locking_mode=EXCLUSIVE (kein -shm noetig)",
         ["locking_mode=EXCLUSIVE", "journal_mode=WAL"]),
        ("DELETE (Rollback-Journal, Default)", ["journal_mode=DELETE"]),
        ("TRUNCATE (Rollback, weniger Verzeichnis-I/O)", ["journal_mode=TRUNCATE"]),
        ("PERSIST", ["journal_mode=PERSIST"]),
    ]

    for i, (beschreibung, pragmas) in enumerate(kandidaten):
        probe = directory / f"_probe_{os.getpid()}_{i}.db"
        # Reste vorheriger Laeufe entfernen (Probe-DB ist ausschliesslich unsere)
        for suffix in ("", "-wal", "-shm", "-journal"):
            p = probe.with_name(probe.name + suffix)
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

        con = None
        try:
            con = sqlite3.connect(str(probe), timeout=5.0)
            gesetzt = []
            for pr in pragmas:
                row = con.execute(f"PRAGMA {pr}").fetchone()
                gesetzt.append(f"{pr} -> {row[0] if row else 'ok'}")
            # Echter Schreibpfad, nicht nur das PRAGMA:
            con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
            con.execute("INSERT INTO t (v) VALUES (?)", ("beleg",))
            con.commit()
            zurueck = con.execute("SELECT v FROM t").fetchone()[0]
            aktiv = con.execute("PRAGMA journal_mode").fetchone()[0]
            ok = (zurueck == "beleg")
            log(f"      [{'OK ' if ok else 'FEHL'}] {beschreibung}")
            log(f"             {' | '.join(gesetzt)}; aktiv='{aktiv}'; "
                f"Rueckgelesen='{zurueck}'")
        except sqlite3.Error as exc:
            log(f"      [FEHL] {beschreibung}")
            log(f"             {err(exc)}")
        finally:
            if con is not None:
                try:
                    con.close()
                except sqlite3.Error:
                    pass
            for suffix in ("", "-wal", "-shm", "-journal"):
                p = probe.with_name(probe.name + suffix)
                if p.exists():
                    try:
                        p.unlink()
                    except OSError as exc:
                        log(f"             HINWEIS: Probe-Rest nicht loeschbar: "
                            f"{p.name} ({exc!r})")


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Diagnose: SQLite-Journalmodi auf Netzlaufwerk (nicht-destruktiv)"
    )
    ap.add_argument("--data-dir", default="./data",
                    help="Datenverzeichnis des Webservers (Default: ./data)")
    ap.add_argument("--skip-local", action="store_true",
                    help="Vergleichstest auf lokalem TEMP-Verzeichnis auslassen")
    args = ap.parse_args()

    data = Path(args.data_dir)

    log("=" * 78)
    log("DIAGNOSE: SQLite auf Netzlaufwerk — journal_mode / Shared Memory / Locking")
    log("=" * 78)
    log(f"Python      : {sys.version.split()[0]}")
    # Hinweis: sqlite3.version wurde in Python 3.14 ENTFERNT — daher bewusst
    # nur sqlite_version (die Version der SQLite-Bibliothek selbst).
    log(f"sqlite3-Lib : {sqlite3.sqlite_version}")
    log(f"CWD         : {Path.cwd()}")
    log(f"Datenverz.  : {data.resolve() if data.exists() else str(data) + '  (EXISTIERT NICHT)'}")
    log(f"Volume      : {volume_info(data if data.exists() else Path.cwd())}")
    log()

    # --- Teil A: echte DBs, ausschliesslich lesend --------------------------
    log("A) BESTANDSAUFNAHME der vorhandenen Datenbanken (nur lesend)")
    if not data.is_dir():
        log("   Datenverzeichnis nicht gefunden — Teil A uebersprungen.")
    else:
        dbs = sorted(p for p in data.rglob("*.db") if not p.name.startswith("_probe_"))
        if not dbs:
            log("   Keine *.db gefunden.")
        for db in dbs:
            log(f"   {db}")
            log(f"      Groesse: {db.stat().st_size} B")
            log(f"      Header : {header_info(db)}")
            log(f"      Neben  : {sidecars(db)}")
            read_only_check(db)
            log()

    # --- Teil B: Schreibtest-Matrix -----------------------------------------
    log("B) SCHREIBTEST-MATRIX (nur auf temporaerer Probe-DB, echte DBs unberuehrt)")
    if data.is_dir():
        probe_matrix(data, "NETZLAUFWERK/Zielverzeichnis")
    if not args.skip_local:
        lokal = Path(tempfile.gettempdir())
        log()
        log(f"  Vergleichsgruppe (lokal): {lokal}  |  {volume_info(lokal)}")
        probe_matrix(lokal, "LOKAL (Vergleich)")

    log()
    log("=" * 78)
    log("ENDE. Bitte die gesamte Ausgabe bzw. diag_sqlite_netdrive.log zurueckgeben.")
    log("=" * 78)

    try:
        Path("diag_sqlite_netdrive.log").write_text(
            "\n".join(LOGLINES) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"[WARN] Logdatei nicht schreibbar: {exc!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
