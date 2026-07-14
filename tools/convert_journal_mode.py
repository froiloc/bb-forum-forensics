#!/usr/bin/env python3
# =============================================================================
# tools/convert_journal_mode.py
# IT-Forensisches Ermittlungswerkzeug — Werkzeug (kein Serverpfad)
# =============================================================================
# Zweck:
#   Stempelt bestehende SQLite-Datenbanken zwischen WAL und Rollback-Journal um.
#
# Warum das noetig ist (Beleg: Diagnose 2026-07-14, Testsystem auf UNC-Share):
#   Der Journalmodus WAL ist eine PERSISTENTE Eigenschaft der Datei (Header-Byte
#   18 = write_version, Byte 19 = read_version; 1 = Rollback-Journal, 2 = WAL).
#   Eine WAL-gestempelte Datei laesst sich auf einem Netzlaufwerk NICHT EINMAL
#   LESEND oeffnen — SQLite braucht dafuer die '-shm'-Datei im Shared Memory,
#   und Shared Memory ist maschinenlokal (sqlite.org/wal.html). Gemessen auf dem
#   betroffenen Share: 'mode=ro'-Lesetest scheitert fuer alle WAL-gestempelten
#   DBs mit 'disk I/O error' (extended code 8714).
#   Es reicht daher NICHT, im Servercode kein WAL mehr zu setzen (Build 408,
#   db/journal_policy.py) — die Bestandsdateien muessen einmalig umgestempelt
#   werden.
#
# Verfahren (in-place, ohne Kopieren):
#   Mit 'PRAGMA locking_mode=EXCLUSIVE' kommt SQLite OHNE '-shm' aus. Genau das
#   ist auf dem Share empirisch gruen (Diagnose-Matrix, Zeile 2). In diesem Modus
#   laesst sich die WAL-DB oeffnen, auschecken und per 'PRAGMA journal_mode=DELETE'
#   umstempeln. Die 4,8 GB grosse default.db muss dafuer NICHT ueber das Netz
#   kopiert werden.
#
# Forensische Sicherungen:
#   * TROCKENLAUF IST DEFAULT. Es wird erst geschrieben, wenn --apply gesetzt ist.
#   * Fuer forensic_<uid>.db wird der INHALTS-SHA-256 vor und nach der Umstempelung
#     berechnet und verglichen. Er MUSS identisch bleiben — das Siegel ist
#     ausdruecklich inhaltsbasiert und nicht dateibasiert (core/startup_checks.py,
#     '_compute_content_sha256', Begruendung dort im Docstring). Weicht er ab,
#     bricht das Werkzeug SOFORT ab und faehrt keine weitere Datei an.
#   * Es wird EXAKT die Hash-Funktion des Servers verwendet (StartupChecker.
#     _compute_content_sha256) — kein Nachbau, damit die beiden nicht auseinander-
#     laufen koennen.
#   * Jede uebersprungene Datei wird gemeldet, nie still weggelassen (Grundregel 1).
#   * Der NTFS-/POSIX-Schreibschutz wird nur temporaer aufgehoben und danach
#     exakt wiederhergestellt.
#
# Aufruf:
#   python tools/convert_journal_mode.py --data-dir ./data              # Trockenlauf
#   python tools/convert_journal_mode.py --data-dir ./data --apply      # scharf
#   python tools/convert_journal_mode.py --data-dir ./data --to wal --apply
#
# Exitcodes: 0 = alles gut / Trockenlauf ok, 1 = Fehler (inkl. Hash-Abweichung)
# Abhaengigkeiten: sqlite3, hashlib (indirekt), pathlib — Stdlib + core.startup_checks
# Version: v0.7.408 · Build: 408 · 2026-07-14
# =============================================================================

from __future__ import annotations

import argparse
import os
import sqlite3
import stat
import sys
from pathlib import Path
from typing import Optional

# Repo-Wurzel in den Suchpfad, damit das Werkzeug auch aus tools/ heraus laeuft.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.startup_checks import StartupChecker  # noqa: E402

# Rollback-Modi (Header-Stempel 1) gegenueber WAL (Header-Stempel 2).
ROLLBACK_MODES = ("delete", "truncate", "persist")
ALL_TARGETS = ROLLBACK_MODES + ("wal",)

# Erwarteter Header-Stempel je Zielmodus.
ERWARTETER_STEMPEL = {"delete": 1, "truncate": 1, "persist": 1, "wal": 2}


class ConvertError(RuntimeError):
    """Abbruchgrund, der eine weitere Verarbeitung verbietet."""


# -----------------------------------------------------------------------------
# Datei-Ebene (ohne SQLite)
# -----------------------------------------------------------------------------

def header_stempel(db: Path) -> Optional[int]:
    """
    Liest write_version (Header-Byte 18) direkt aus der Datei.
    Rueckgabe: 1 = Rollback-Journal, 2 = WAL, None = keine SQLite-Datei.
    """
    with db.open("rb") as fh:
        hdr = fh.read(100)
    if len(hdr) < 100 or not hdr.startswith(b"SQLite format 3\x00"):
        return None
    return hdr[18]


def ist_schreibgeschuetzt(db: Path) -> bool:
    """Prueft den Schreibschutz (NTFS-Readonly bzw. POSIX-Schreibbit)."""
    return not os.access(str(db), os.W_OK)


def schreibschutz_aufheben(db: Path) -> int:
    """Hebt den Schreibschutz auf und gibt den urspruenglichen Modus zurueck."""
    alt = db.stat().st_mode
    db.chmod(alt | stat.S_IWRITE | stat.S_IWUSR)
    return alt


def schreibschutz_wiederherstellen(db: Path, alt: int) -> None:
    """Stellt den urspruenglichen Dateimodus wieder her."""
    db.chmod(alt)


def nebendateien(db: Path) -> list[Path]:
    """Liefert vorhandene -wal/-shm/-journal-Begleitdateien."""
    return [
        db.with_name(db.name + suffix)
        for suffix in ("-wal", "-shm", "-journal")
        if db.with_name(db.name + suffix).exists()
    ]


# -----------------------------------------------------------------------------
# SQLite-Ebene
# -----------------------------------------------------------------------------

def oeffne_exklusiv(db: Path, readonly: bool) -> sqlite3.Connection:
    """
    Oeffnet die DB mit 'locking_mode=EXCLUSIVE'.

    EXCLUSIVE ist hier kein Performance-Trick, sondern die Voraussetzung dafuer,
    dass eine WAL-gestempelte DB auf einem Netzlaufwerk ueberhaupt geoeffnet
    werden kann: In diesem Modus haelt SQLite den wal-index im Heap statt in
    einer gemappten '-shm'-Datei.
    """
    if readonly:
        uri = "file:" + str(db).replace("?", "%3f").replace("#", "%23") + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=10.0)
    else:
        con = sqlite3.connect(str(db), timeout=10.0)
    # Muss VOR dem ersten WAL-Zugriff gesetzt werden.
    con.execute("PRAGMA locking_mode=EXCLUSIVE")
    return con


def inhalts_hash(con: sqlite3.Connection) -> str:
    """
    Berechnet den kanonischen Inhalts-SHA-256 mit der Funktion des Servers.

    Es wird bewusst StartupChecker verwendet und die Logik NICHT nachgebaut:
    ein Nachbau koennte vom Serverpfad abweichen und damit genau die Aussage
    entwerten, die wir hier belegen wollen. Der Konstruktor speichert lediglich
    context/config, beide werden fuer die Hashberechnung nicht benoetigt.
    """
    checker = StartupChecker(None, None)          # type: ignore[arg-type]
    return checker._compute_content_sha256(con)   # noqa: SLF001 — bewusst, s.o.


def aktiver_modus(con: sqlite3.Connection) -> str:
    return str(con.execute("PRAGMA journal_mode").fetchone()[0]).strip().lower()


# -----------------------------------------------------------------------------
# Verarbeitung einer Datei
# -----------------------------------------------------------------------------

def verarbeite(db: Path, ziel: str, apply: bool) -> bool:
    """
    Verarbeitet eine einzelne Datenbank.

    Returns:
        True  = umgestempelt (bzw. im Trockenlauf: waere umzustempeln)
        False = keine Aenderung noetig
    Raises:
        ConvertError bei Hash-Abweichung oder unmoeglicher Umstempelung.
    """
    print(f"\n  {db}")
    stempel = header_stempel(db)
    if stempel is None:
        print("    KEINE SQLite-Datei — uebersprungen (gemeldet, nicht still).")
        return False

    ist_forensic = db.name.startswith("forensic_")
    neben = nebendateien(db)
    print(f"    Header vorher : write_version={stempel} "
          f"({'WAL' if stempel == 2 else 'rollback-journal'})")
    print(f"    Groesse       : {db.stat().st_size} B")
    print(f"    Nebendateien  : "
          f"{', '.join(p.name.rsplit('.db', 1)[-1] for p in neben) if neben else 'keine'}")
    print(f"    Schreibschutz : {'ja' if ist_schreibgeschuetzt(db) else 'nein'}")

    if stempel == ERWARTETER_STEMPEL[ziel]:
        print(f"    Bereits im Zielzustand fuer '{ziel}' — keine Aenderung noetig.")
        return False

    # --- Trockenlauf ---------------------------------------------------------
    if not apply:
        if ist_forensic:
            # Zweistufig, weil eine WAL-gestempelte DB NICHT read-only geoeffnet
            # werden kann: eine 'mode=ro'-Verbindung darf die fehlende '-shm' nicht
            # anlegen und scheitert mit 'disk I/O error' (auch lokal reproduziert).
            # Stufe 2 oeffnet daher read-write mit locking_mode=EXCLUSIVE, FUEHRT
            # ABER KEINEN SCHREIBZUGRIFF AUS. Belegt: die Datei bleibt danach
            # byteidentisch (MD5 vorher == MD5 nachher), es entstehen keine
            # Nebendateien. Messung 2026-07-14 in der Entwicklungsumgebung.
            hash_vorher = "(nicht ermittelbar)"
            for readonly, hinweis in ((True, "mode=ro"), (False, "rw, ohne Schreibzugriff")):
                try:
                    con = oeffne_exklusiv(db, readonly=readonly)
                    try:
                        hash_vorher = f"{inhalts_hash(con)}  [{hinweis}]"
                    finally:
                        con.close()
                    break
                except sqlite3.Error as exc:
                    hash_vorher = f"(nicht lesbar: {exc})"
            print(f"    Inhalts-SHA256: {hash_vorher}")
        print(f"    WUERDE umgestempelt auf '{ziel}' (Trockenlauf — nichts geschrieben).")
        return True

    # --- Scharfer Lauf -------------------------------------------------------
    alt_modus: Optional[int] = None
    if ist_schreibgeschuetzt(db):
        alt_modus = schreibschutz_aufheben(db)
        print("    Schreibschutz temporaer aufgehoben.")

    try:
        con = oeffne_exklusiv(db, readonly=False)
        try:
            hash_vorher = inhalts_hash(con) if ist_forensic else None
            if hash_vorher:
                print(f"    Inhalts-SHA256 vorher : {hash_vorher}")

            con.execute(f"PRAGMA journal_mode={ziel}")
            jetzt = aktiver_modus(con)
            if jetzt != ziel:
                raise ConvertError(
                    f"Umstempelung auf '{ziel}' NICHT uebernommen — aktiv ist "
                    f"'{jetzt}'. Datei: {db}"
                )

            hash_nachher = inhalts_hash(con) if ist_forensic else None
            if hash_nachher:
                print(f"    Inhalts-SHA256 nachher: {hash_nachher}")
                if hash_nachher != hash_vorher:
                    # Darf nach Lage der Dinge nicht passieren (der Stempel steht im
                    # Header, nicht im Inhalt). Falls doch: sofort zurueckdrehen und
                    # abbrechen — lieber ein nicht startender Server als eine
                    # Beweismitteldatenbank mit gebrochenem Siegel.
                    rueck = "nicht versucht"
                    try:
                        con.execute("PRAGMA journal_mode=wal")
                        rueck = f"zurueckgestempelt auf '{aktiver_modus(con)}'"
                    except sqlite3.Error as exc2:      # pragma: no cover
                        rueck = f"RUECKSTEMPELUNG FEHLGESCHLAGEN: {exc2}"
                    raise ConvertError(
                        "INHALTS-HASH HAT SICH GEAENDERT — Abbruch, keine weitere "
                        f"Datei wird angefasst. Datei: {db}\n"
                        f"  vorher : {hash_vorher}\n"
                        f"  nachher: {hash_nachher}\n"
                        f"  Rueckabwicklung: {rueck}"
                    )
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise ConvertError(f"SQLite-Fehler bei '{db}': {exc}") from exc
    finally:
        if alt_modus is not None:
            schreibschutz_wiederherstellen(db, alt_modus)
            print("    Schreibschutz wiederhergestellt.")

    # Reste aufraeumen: nach dem Verlassen von WAL raeumt SQLite -wal/-shm selbst
    # auf. Bleibt doch etwas liegen (z.B. eine verwaiste -shm aus einem frueheren
    # Lauf), wird das gemeldet und entfernt — sonst haelt sich der alte Zustand.
    for rest in nebendateien(db):
        try:
            rest.unlink()
            print(f"    Rest entfernt: {rest.name}")
        except OSError as exc:
            print(f"    HINWEIS: Rest nicht entfernbar: {rest.name} ({exc!r})")

    stempel_nachher = header_stempel(db)
    print(f"    Header nachher: write_version={stempel_nachher} "
          f"({'WAL' if stempel_nachher == 2 else 'rollback-journal'})")
    if stempel_nachher != ERWARTETER_STEMPEL[ziel]:
        raise ConvertError(
            f"Header-Stempel nach der Umstempelung unerwartet: "
            f"{stempel_nachher} (erwartet {ERWARTETER_STEMPEL[ziel]}). Datei: {db}"
        )
    print(f"    UMGESTEMPELT auf '{ziel}'. ✓")
    return True


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stempelt SQLite-DBs zwischen WAL und Rollback-Journal um "
                    "(Trockenlauf ist Default)."
    )
    ap.add_argument("--data-dir", default="./data",
                    help="Verzeichnis mit den *.db-Dateien (Default: ./data)")
    ap.add_argument("--to", default="delete", choices=list(ALL_TARGETS),
                    help="Zielmodus (Default: delete — Empfehlung fuer Netzlaufwerke)")
    ap.add_argument("--apply", action="store_true",
                    help="SCHARF schalten. Ohne diesen Schalter wird nichts geschrieben.")
    args = ap.parse_args(argv)

    data = Path(args.data_dir)
    if not data.is_dir():
        print(f"[FEHLER] Datenverzeichnis nicht gefunden: {data}", file=sys.stderr)
        return 1

    print("=" * 78)
    print(f"JOURNALMODUS-UMSTEMPELUNG — Ziel: '{args.to}' | "
          f"{'SCHARF (--apply)' if args.apply else 'TROCKENLAUF (nichts wird geschrieben)'}")
    print(f"Verzeichnis: {data.resolve()}")
    print(f"SQLite     : {sqlite3.sqlite_version}")
    print("=" * 78)

    dbs = sorted(data.rglob("*.db"))
    if not dbs:
        print("Keine *.db gefunden — nichts zu tun.")
        return 0

    geaendert = 0
    try:
        for db in dbs:
            if verarbeite(db, args.to, args.apply):
                geaendert += 1
    except ConvertError as exc:
        print(f"\n[ABBRUCH] {exc}", file=sys.stderr)
        print("Es wurden KEINE weiteren Dateien angefasst.", file=sys.stderr)
        return 1

    print("\n" + "=" * 78)
    if args.apply:
        print(f"FERTIG: {geaendert} von {len(dbs)} Datenbanken umgestempelt.")
    else:
        print(f"TROCKENLAUF: {geaendert} von {len(dbs)} Datenbanken WUERDEN "
              f"umgestempelt. Mit --apply scharf schalten.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
