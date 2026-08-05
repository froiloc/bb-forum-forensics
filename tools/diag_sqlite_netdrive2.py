#!/usr/bin/env python3
# =============================================================================
# tools/diag_sqlite_netdrive2.py
# IT-Forensisches Ermittlungswerkzeug — DIAGNOSE-Werkzeug 2 (Baustelle 2)
# =============================================================================
# Zweck:
#   Klaert, warum auf dem Share jetzt sogar 'PRAGMA journal_mode=delete' mit
#   'disk I/O error' (extended code 8714) scheitert, OBWOHL die DBs bereits
#   umgestempelt sind und obwohl DELETE in Diagnose 1 gruen war.
#
# Leitende Hypothese (zu bestaetigen ODER zu widerlegen):
#   8714 = SQLITE_IOERR (10) | (34 << 8). Subcode 34 verweist auf einen Fehler
#   beim Zugriff auf eine MEMORY-MAPPED Seite — also auf mmap der DATENBANKDATEI
#   selbst, nicht (nur) auf die '-shm'-Datei von WAL. Passt zu einem gemeldeten
#   Verhalten von SQLite 3.50.x auf UNC-Pfaden. Wenn das stimmt, muesste
#       PRAGMA mmap_size=0
#   den Fehler beseitigen — ohne locking_mode=EXCLUSIVE und ohne Verlust an
#   Parallelitaet.
#
# Warum Diagnose 1 gruen war und trotzdem nicht ausgereicht hat:
#   Dort wurde gegen frisch erzeugte, winzige Probe-DBs gemessen. Der mmap-Pfad
#   wird so offenbar gar nicht betreten. Diese Diagnose misst deshalb gegen eine
#   KOPIE DER ECHTEN evidence-DB (gleiches Verzeichnis, gleiche Groesse,
#   gleicher Inhalt).
#
# Forensische Sorgfalt:
#   * Die echten DBs werden NICHT veraendert. Alle Schreibtests laufen auf einer
#     Kopie ('_probe2_<pid>.db'), die am Ende geloescht wird.
#   * default.db (4,8 GB) wird NICHT kopiert — dort wird nur LESEND geprueft.
#
# Aufruf (in der VM, aus S:\):
#     python tools/diag_sqlite_netdrive2.py --data-dir .\data --db .\data\evidence\evidence_<uid>.db
#
# Ausgabe: Konsole + 'diag_sqlite_netdrive2.log'
# Abhaengigkeiten: nur Stdlib.
# Version: v0.7.409 · Build: 409 · 2026-07-14 (in tools/ uebernommen,
#          Build 409: --db erzwingt die BEWUSSTE Wahl der Messdatei)
# =============================================================================

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# Direktaufruf als Skript: das Paketverzeichnis muss im Suchpfad liegen,
# sonst findet der Import aus "management/" nichts (Muster aus
# tools/hilfe.py). Build 624 - noetig geworden mit dem Epilog-Import.
_WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from management.help import cli_epilog  # noqa: E402

LOGLINES: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    LOGLINES.append(msg)


def err(exc: sqlite3.Error) -> str:
    """SQLite-Fehler mit erweitertem Fehlercode (der eigentliche Erkenntnisgewinn)."""
    name = getattr(exc, "sqlite_errorname", "?")
    code = getattr(exc, "sqlite_errorcode", "?")
    return f"{type(exc).__name__}: {exc} [{name} / {code}]"


def stempel(db: Path) -> str:
    with db.open("rb") as fh:
        hdr = fh.read(100)
    if len(hdr) < 100:
        return "keine SQLite-Datei"
    return {1: "rollback-journal", 2: "WAL"}.get(hdr[18], f"unbekannt({hdr[18]})")


def neben(db: Path) -> str:
    out = [
        f"{s}={db.with_name(db.name + s).stat().st_size}B"
        for s in ("-wal", "-shm", "-journal")
        if db.with_name(db.name + s).exists()
    ]
    return ", ".join(out) if out else "keine"


# -----------------------------------------------------------------------------
# Testfaelle auf der Kopie der echten DB
# -----------------------------------------------------------------------------

def _raeume_auf(probe_verz: Path, kopie: Path) -> None:
    """
    Raeumt Kopie, Nebendateien und Probeverzeichnis weg - und SAGT, was
    liegenbleibt (Build 682, Vorgang 33b859f9).

    An EINER Stelle, weil das Aufraeumen ab jetzt an mehreren Ausgaengen
    gebraucht wird: nach dem regulaeren Lauf und beim Abbruch, wenn die Kopie
    nicht anlegbar war. Zwei Fassungen waeren binnen weniger Builds
    auseinandergelaufen, und dann bliebe an einem der Ausgaenge eine
    vollstaendige Kopie eines Beweismittels liegen.

    WAS ES NICHT TUT: Reste FRUEHERER Laeufe entfernen. Die werden beim Start
    benannt und bleiben liegen - eine vollstaendige Kopie eines Beweismittels
    loescht man nicht nebenbei, ohne dass jemand davon weiss.
    """
    for anhang in ("", "-wal", "-shm", "-journal"):
        q = kopie.with_name(kopie.name + anhang)
        if q.exists():
            try:
                q.unlink()
            except OSError as exc:
                log(f"   HINWEIS: Rest nicht loeschbar: {q} ({exc!r})")
    if probe_verz.is_dir():
        try:
            probe_verz.rmdir()
        except OSError as exc:
            # rmdir scheitert, wenn noch etwas drinliegt. Genau dann muss es
            # gesagt werden - ein stilles Weitergehen liesse eine Kopie
            # zurueck, von der niemand weiss.
            uebrig = sorted(q.name for q in probe_verz.iterdir()) \
                if probe_verz.is_dir() else []
            log(f"   HINWEIS: Probeverzeichnis bleibt liegen: {probe_verz}")
            log(f"            Grund: {exc!r}")
            if uebrig:
                log(f"            Enthaelt noch: {', '.join(uebrig)}")
            log("            BITTE PRUEFEN - es kann eine vollstaendige Kopie "
                "eines Beweismittels sein.")


def testfall(kopie: Path, name: str, pragmas: list[str], schreiben: bool) -> None:
    """
    Fuehrt einen Testfall auf der Kopie aus.

    Jeder Testfall: frische Verbindung -> PRAGMAs in Reihenfolge -> (optional)
    echter Schreibpfad (CREATE/INSERT/COMMIT/SELECT). Ein erfolgreiches PRAGMA
    allein ist KEIN Beleg — deshalb wird geschrieben und zurueckgelesen.
    """
    con = None
    try:
        con = sqlite3.connect(str(kopie), timeout=5.0)
        schritte = []
        for pr in pragmas:
            row = con.execute(f"PRAGMA {pr}").fetchone()
            schritte.append(f"{pr} -> {row[0] if row else 'ok'}")

        if schreiben:
            con.execute("CREATE TABLE IF NOT EXISTS _probe2 (id INTEGER PRIMARY KEY, v TEXT)")
            con.execute("INSERT INTO _probe2 (v) VALUES (?)", ("beleg",))
            con.commit()
            zurueck = con.execute(
                "SELECT v FROM _probe2 ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            schritte.append(f"Schreiben+Ruecklesen -> '{zurueck}'")

        log(f"      [OK ] {name}")
        for s in schritte:
            log(f"             {s}")
    except sqlite3.Error as exc:
        log(f"      [FEHL] {name}")
        log(f"             {err(exc)}")
    finally:
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Diagnose 2: mmap vs. locking auf dem Netzlaufwerk (nicht-destruktiv)",
        epilog=cli_epilog.epilog("diag_sqlite_netdrive2"),
        formatter_class=cli_epilog.HilfeFormat,
    )
    ap.add_argument("--data-dir", default="./data")
    ap.add_argument(
        "--db", default=None,
        help="Zu vermessende evidence-DB. PFLICHT, wenn mehrere vorhanden sind — "
             "Build 409: die erste Fassung griff sich stillschweigend die "
             "alphabetisch erste evidence_*.db und vermass damit die FALSCHE "
             "Datei (der Server scheiterte an einer anderen). Kein Raten mehr "
             "(Grundregel 1).",
    )
    args = ap.parse_args()
    data = Path(args.data_dir)

    log("=" * 78)
    log("DIAGNOSE 2 — 'disk I/O error' trotz Rollback-Journal")
    log("=" * 78)
    log(f"Python: {sys.version.split()[0]}   SQLite: {sqlite3.sqlite_version}")
    log(f"Datenverzeichnis: {data.resolve()}")
    log()

    # Voreinstellung der Bibliothek: ist memory-mapped I/O ueberhaupt aktiv?
    # Hinweis: auf ':memory:' liefert 'PRAGMA mmap_size' KEINE Zeile — der
    # Vorgabewert muss an einer DATEI-DB abgefragt werden.
    import tempfile
    _tmpdir = tempfile.mkdtemp()
    tmp = sqlite3.connect(os.path.join(_tmpdir, "mmapprobe.db"))
    try:
        mm = tmp.execute("PRAGMA mmap_size").fetchone()
        log(f"Vorgabewert PRAGMA mmap_size dieser SQLite-Bibliothek: "
            f"{mm[0] if mm else '(keine Zeile)'}")
        log("  (0 = memory-mapped I/O aus; > 0 = aktiv — dann ist die mmap-Hypothese plausibel)")
    finally:
        tmp.close()
        shutil.rmtree(_tmpdir, ignore_errors=True)
    log()

    # --- A) evidence-DB: Kopie anlegen und die Kandidaten durchspielen --------
    ev_dir = data / "evidence"
    evidences = sorted(ev_dir.glob("evidence_*.db")) if ev_dir.is_dir() else []

    if args.db:
        original = Path(args.db)
        if not original.exists():
            log(f"[FEHLER] --db nicht gefunden: {original}")
            return 1
    elif not evidences:
        log("[FEHLER] Keine evidence_<uid>.db gefunden — Abbruch.")
        return 1
    elif len(evidences) > 1:
        # KEINE stille Auswahl. Genau hier lag der Fehler in der ersten Fassung.
        log("[FEHLER] Mehrere evidence-DBs gefunden. Bitte mit --db die zu "
            "vermessende Datei ANGEBEN — eine stille Auswahl vermisst sonst "
            "moeglicherweise die falsche Datei:")
        for e in evidences:
            log(f"   {e}   (Stempel: {stempel(e)})")
        return 1
    else:
        original = evidences[0]

    log("A) ECHTE evidence-DB (nur gelesen, nicht veraendert)")
    log(f"   {original}")
    log(f"   Groesse: {original.stat().st_size} B | Stempel: {stempel(original)} "
        f"| Nebendateien: {neben(original)}")
    log(f"   Schreibgeschuetzt: {'ja' if not os.access(str(original), os.W_OK) else 'nein'}")
    log()

    # -------------------------------------------------------------------------
    # BUILD 682 (Vorgang 33b859f9): DIE KOPIE LIEGT IN EINEM EIGENEN
    # UNTERVERZEICHNIS, nicht mehr neben dem Original.
    #
    # WARUM: Die Kopie ist eine vollstaendige Ausfertigung eines BEWEISMITTELS.
    # Das Aufraeumen funktioniert und ist gemessen - aber bei einem harten
    # Abbruch (Stromausfall, Prozessabschuss, Netzabbruch) bleibt sie liegen,
    # und dann lag sie bisher zwischen den echten Datenbanken. Ein Rest in
    # einem eigens benannten Verzeichnis ist als Rest ERKENNBAR; einer neben
    # dem Original sieht aus wie Bestand.
    #
    # WAS DAS NICHT AENDERT: das Verzeichnis liegt auf DEMSELBEN Datentraeger
    # wie das Original - und darauf kommt es bei dieser Messung an, denn
    # gemessen wird das Verhalten des Netzlaufwerks. Ein Unterverzeichnis
    # wechselt weder Datentraeger noch Freigabe.
    # -------------------------------------------------------------------------
    probe_verz = original.parent / f"_probe2_{os.getpid()}"
    kopie = probe_verz / "probe.db"

    # Reste frueherer, hart abgebrochener Laeufe BENENNEN. Sie werden NICHT
    # von selbst geloescht: eine vollstaendige Kopie eines Beweismittels
    # loescht man nicht nebenbei, ohne dass jemand davon weiss.
    reste = sorted(q for q in original.parent.glob("_probe2_*")
                   if q != probe_verz)
    if reste:
        log("   ACHTUNG - Reste frueherer Laeufe gefunden:")
        for q in reste:
            log(f"      {q}")
        log("   Diese Reste sind vollstaendige Kopien eines Beweismittels.")
        log("   Sie werden NICHT selbsttaetig geloescht - bitte pruefen und")
        log("   von Hand entfernen.")
        log()

    try:
        probe_verz.mkdir(exist_ok=True)
        # Zugriff nur fuer die aufrufende Person. Zur Wirkung unter Windows
        # siehe die Anmerkung bei der Kopie weiter unten.
        try:
            probe_verz.chmod(0o700)
        except OSError:
            pass
    except OSError as exc:
        log(f"[FEHLER] Probeverzeichnis nicht anlegbar: {exc!r}")
        return 1

    log(f"B) TESTMATRIX auf einer KOPIE dieser DB im selben Verzeichnis")
    log(f"   {probe_verz.name}/{kopie.name}  (wird am Ende geloescht)")
    log()

    # Kandidaten. Reihenfolge der PRAGMAs ist bedeutsam:
    # mmap_size / locking_mode muessen VOR dem ersten Datenbankzugriff stehen.
    kandidaten = [
        ("Nur lesen: PRAGMA journal_mode (ohne Setzen)",
         ["journal_mode"], False),
        ("Setzen: journal_mode=delete  (= das, was Build 408 tut)",
         ["journal_mode=delete"], True),
        ("mmap_size=0, dann journal_mode=delete   <-- Hypothese",
         ["mmap_size=0", "journal_mode=delete"], True),
        ("locking_mode=EXCLUSIVE, dann journal_mode=delete",
         ["locking_mode=EXCLUSIVE", "journal_mode=delete"], True),
        ("mmap_size=0 + locking_mode=EXCLUSIVE + journal_mode=delete",
         ["mmap_size=0", "locking_mode=EXCLUSIVE", "journal_mode=delete"], True),
        ("Ohne jedes PRAGMA: nur schreiben",
         [], True),
        ("mmap_size=0, dann nur schreiben",
         ["mmap_size=0"], True),
    ]

    for name, pragmas, schreiben in kandidaten:
        # Fuer jeden Testfall eine FRISCHE Kopie — sonst verfaelschen Vorlaeufer
        # das Ergebnis (z.B. eine bereits angelegte _probe2-Tabelle).
        for s in ("", "-wal", "-shm", "-journal"):
            p = kopie.with_name(kopie.name + s)
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
        try:
            shutil.copy2(str(original), str(kopie))
            # -----------------------------------------------------------------
            # BUILD 682 (Vorgang 33b859f9): 0o600 STATT 0o666.
            #
            # HIER STAND chmod(0o666) - Lese- UND Schreibrecht fuer ALLE.
            # Auf einem geteilten Netzlaufwerk, und genau dafuer ist dieses
            # Werkzeug gebaut, lag damit waehrend des Laufs eine fuer jeden
            # Benutzer les- und beschreibbare Vollkopie eines Beweismittels im
            # Verzeichnis.
            #
            # DER VORGANG SCHLUG VOR, das chmod ERSATZLOS zu streichen -
            # shutil.copy2 uebernehme ja die Rechte des Originals. Nachgesehen:
            # das traegt nicht. Das Werkzeug misst ausdruecklich mit, ob das
            # Original schreibgeschuetzt ist (Zeile 'Schreibgeschuetzt: ...'),
            # und die Testmatrix muss auf die Kopie SCHREIBEN. Uebernaehme man
            # die Rechte eines schreibgeschuetzten Originals, faellt die halbe
            # Messung aus - und zwar mit einem Fehlerbild, das wie ein Befund
            # des Netzlaufwerks aussieht. 0o600 loest beides: schreibbar, aber
            # nur fuer die aufrufende Person.
            #
            # ZUR WIRKUNG UNTER WINDOWS, die im Vorgang als ungeprueft
            # vermerkt war: os.chmod setzt dort ausschliesslich das
            # Schreibschutz-Merkmal; alle uebrigen Bits werden ignoriert
            # (Python-Dokumentation zu os.chmod). Auf NTFS bewirkten 0o666 und
            # 0o600 also DASSELBE - naemlich nur, dass die Datei beschreibbar
            # ist. Die Rechte der Kopie ergeben sich dort aus der Vererbung des
            # Zielverzeichnisses. Der urspruengliche Befund wiegt auf der
            # Produktions-VM damit LEICHTER als befuerchtet; auf einem
            # POSIX-System war er real. Beides gehoert gesagt.
            # -----------------------------------------------------------------
            kopie.chmod(0o600)
        except OSError as exc:
            log(f"      [FEHL] Kopie nicht anlegbar: {exc!r} — Abbruch.")
            _raeume_auf(probe_verz, kopie)
            return 1
        testfall(kopie, name, pragmas, schreiben)
        log()

    _raeume_auf(probe_verz, kopie)

    # --- C) default.db: nur LESEND (4,8 GB werden nicht kopiert) --------------
    default_db = data / "default.db"
    if default_db.exists():
        log("C) default.db — NUR LESEND (kein Kopieren, keine Aenderung)")
        log(f"   Stempel: {stempel(default_db)} | Nebendateien: {neben(default_db)}")
        for name, pragmas in (
            ("mode=ro, Standard", []),
            ("mode=ro + mmap_size=0", ["mmap_size=0"]),
        ):
            uri = "file:" + str(default_db).replace("?", "%3f") + "?mode=ro"
            con = None
            try:
                con = sqlite3.connect(uri, uri=True, timeout=5.0)
                for pr in pragmas:
                    con.execute(f"PRAGMA {pr}")
                n = con.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
                log(f"      [OK ] {name} — {n} Objekte in sqlite_master")
            except sqlite3.Error as exc:
                log(f"      [FEHL] {name} — {err(exc)}")
            finally:
                if con is not None:
                    try:
                        con.close()
                    except sqlite3.Error:
                        pass
        log()

    log("=" * 78)
    log("ENDE. Bitte die gesamte Ausgabe bzw. diag_sqlite_netdrive2.log zurueckgeben.")
    log("=" * 78)

    try:
        Path("diag_sqlite_netdrive2.log").write_text(
            "\n".join(LOGLINES) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"[WARN] Logdatei nicht schreibbar: {exc!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
