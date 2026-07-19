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
#   python tools/convert_journal_mode.py --db ./data/forensic/forensic_1488.db --apply
#   python tools/convert_journal_mode.py --data-dir ./data --skip-on-error --apply
#
# Build 433 (2026-07-19): Zwei Schalter ergaenzt, weil auf dem geteilten UNC-Share
#   mehrere Server dieselbe coordinator.db offen halten und ein Lauf ueber das
#   ganze Verzeichnis bisher an der ERSTEN gesperrten DB (alphabetisch:
#   coordinator.db vor evidence_/forensic_) hart abbrach — die eigentlich zu
#   konvertierenden Nutzer-DBs wurden nie erreicht. Beleg: PROD-Log 2026-07-19,
#   forensic_1488.db/evidence_1488.db blieben WAL-gestempelt.
#     --db PFAD        Genau EINE Datenbank konvertieren (statt --data-dir).
#     --skip-on-error  Operative Fehler (locked, I/O, unerwarteter Stempel) werden
#                      GEMELDET und uebersprungen, der Lauf faehrt mit den uebrigen
#                      DBs fort (Grundregel 1: nie still). Ein SIEGELBRUCH
#                      (Inhalts-Hash-Abweichung einer forensic_-DB) wird dabei
#                      AUSDRUECKLICH NICHT uebersprungen — er bleibt harter Abbruch.
#
# Build 434 (2026-07-19): In-Place-Pfad haerter gemacht und ein Staging-Weg fuer
#   versiegelte WAL-DBs auf Netzlaufwerken ergaenzt. Anlass: PROD-Log 2026-07-19
#   (db-error3) — forensic_1488.db ist versiegelt (read-only) UND WAL-gestempelt
#   mit stehengebliebenen -wal/-shm; der erste Schreibversuch (Checkpoint zum
#   Verlassen von WAL) scheiterte mit 'attempt to write a readonly database'.
#     * In place: auch -wal/-shm-Schreibschutz temporaer aufheben; expliziter
#       'PRAGMA wal_checkpoint(TRUNCATE)' vor dem Moduswechsel; bei READONLY ein
#       klarer Hinweis auf --staging-dir.
#     * --staging-dir LOKAL: .db(+-wal/-shm) lokal kopieren, dort umstempeln,
#       Inhalts-Hash gegen forensic_meta['sha256'] verifizieren und ATOMAR
#       (Nachbardatei + os.replace) zurueckkopieren. Original wird nie truncated;
#       haelt ein Server die DB offen, scheitert der Austausch sauber (GR1).
#
#   python tools/convert_journal_mode.py --db D:\lokal\forensic_1488.db --apply
#   python tools/convert_journal_mode.py --data-dir .\data --staging-dir C:\temp\conv --apply
#
# Exitcodes: 0 = alles gut / Trockenlauf ok
#            1 = harter Abbruch (Siegelbruch ODER Fehler ohne --skip-on-error)
#            2 = Lauf beendet, aber >=1 DB wegen Fehler uebersprungen (--skip-on-error)
# Abhaengigkeiten: sqlite3, hashlib (indirekt), pathlib, shutil — Stdlib + core.startup_checks
# Version: v0.7.434 · Build: 434 · 2026-07-19
# =============================================================================

from __future__ import annotations

import argparse
import os
import shutil
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
    """
    Operativer Abbruchgrund (z.B. Datei gesperrt, I/O-Fehler, unerwarteter
    Header-Stempel). Mit --skip-on-error DARF eine solche DB uebersprungen und
    der Lauf fortgesetzt werden — der Fehler wird dabei stets gemeldet (GR1).
    """


class SealError(ConvertError):
    """
    Siegelbruch: der INHALTS-SHA-256 einer forensic_-DB hat sich durch die
    Umstempelung geaendert. Das darf nach Lage der Dinge nie passieren (der
    Journalstempel steht im Header, nicht im Inhalt). Falls doch, ist es der
    schwerwiegendste denkbare Fehler in einem Beweismittelwerkzeug.

    Bewusst eine EIGENE Klasse (Unterklasse von ConvertError), damit --skip-on-error
    ihn NICHT ueberspringen kann: ein Siegelbruch fuehrt IMMER zum harten Abbruch,
    egal welche Schalter gesetzt sind. Ehre der Beweiskraft vor Bequemlichkeit.
    """


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


def gespeicherter_siegelhash(con: sqlite3.Connection) -> Optional[str]:
    """
    Liest den in der DB hinterlegten Siegel-Hash (forensic_meta['sha256']).

    Dient beim Staging-Rueckweg (Build 434) als ZUSAETZLICHE Absicherung: bevor
    die konvertierte Kopie ueber das versiegelte Original kopiert wird, muss ihr
    berechneter Inhalts-Hash mit dem gespeicherten Siegel uebereinstimmen — sonst
    wuerde eine fremde/beschaedigte Datei zurueckgeschrieben. Fehlt der Eintrag,
    wird None geliefert und der Aufrufer meldet das ausdruecklich (GR1).
    """
    try:
        row = con.execute(
            "SELECT value FROM forensic_meta WHERE key = 'sha256'"
        ).fetchone()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    return str(row[0]).strip()


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

    # Build 434: auch die Nebendateien entsperren. Um WAL zu verlassen, muss
    # SQLite die -wal einchecken und -wal/-shm danach loeschen. Sind die Sidecars
    # schreibgeschuetzt (typisch bei einer versiegelten forensic-DB, deren -wal
    # beim seal() stehen blieb), scheitert genau dieser Aufraeumschritt.
    sidecar_modi: list[tuple[Path, int]] = []
    for sc in nebendateien(db):
        if ist_schreibgeschuetzt(sc):
            sidecar_modi.append((sc, schreibschutz_aufheben(sc)))
    if sidecar_modi:
        print("    Nebendateien temporaer entsperrt: "
              + ", ".join(p.name for p, _ in sidecar_modi))

    try:
        con = oeffne_exklusiv(db, readonly=False)
        try:
            hash_vorher = inhalts_hash(con) if ist_forensic else None
            if hash_vorher:
                print(f"    Inhalts-SHA256 vorher : {hash_vorher}")

            # Build 434: WAL-Frames explizit einchecken, BEVOR der Modus wechselt.
            # So scheitert ein nicht schreibbarer Datentraeger hier mit klarer
            # Aussage, statt spaeter opak im Moduswechsel.
            if stempel == 2:
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

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
                    raise SealError(
                        "INHALTS-HASH HAT SICH GEAENDERT — Abbruch, keine weitere "
                        f"Datei wird angefasst (auch mit --skip-on-error NICHT). "
                        f"Datei: {db}\n"
                        f"  vorher : {hash_vorher}\n"
                        f"  nachher: {hash_nachher}\n"
                        f"  Rueckabwicklung: {rueck}"
                    )
        finally:
            con.close()
    except sqlite3.Error as exc:
        hinweis = ""
        if "readonly" in str(exc).lower() or "read-only" in str(exc).lower():
            # Build 434: der klassische Netzlaufwerk-Fall. SQLite oeffnet eine
            # WAL-gestempelte DB dort read-only, weil es die -shm nicht etablieren
            # kann; der erste Schreibversuch (Checkpoint) meldet dann READONLY.
            hinweis = ("\n    HINWEIS: Auf einem Netzlaufwerk laesst sich eine "
                       "WAL-gestempelte, versiegelte DB nicht in place umstempeln. "
                       "Nutze --staging-dir <lokaler_pfad> — dann kopiert das "
                       "Werkzeug die DB lokal, stempelt sie dort um, verifiziert "
                       "den Inhalts-Hash und kopiert sie atomar zurueck.")
        raise ConvertError(f"SQLite-Fehler bei '{db}': {exc}{hinweis}") from exc
    finally:
        # Sidecar-Schreibschutz wiederherstellen, soweit die Datei noch existiert
        # (nach erfolgreicher Umstempelung sind -wal/-shm ohnehin geloescht).
        for sc, modus in sidecar_modi:
            if sc.exists():
                schreibschutz_wiederherstellen(sc, modus)
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
# Verarbeitung ueber ein lokales Staging (Build 434)
# -----------------------------------------------------------------------------

def verarbeite_via_staging(db: Path, ziel: str, apply: bool,
                           staging_dir: Path) -> bool:
    """
    Stempelt eine WAL-gestempelte, versiegelte DB um, die sich auf ihrem
    Datentraeger (Netzlaufwerk) nicht in place umstempeln laesst.

    Verfahren (belegt siegelneutral, Messung 2026-07-19):
      1. .db + -wal + -shm in ein LOKALES Verzeichnis kopieren (dort funktioniert
         die -shm, die WAL zum Verlassen braucht).
      2. Die lokale Kopie mit exakt derselben Logik umstempeln (verarbeite()).
         Dabei greift die Inhalts-Hash-Kontrolle (vorher == nachher).
      3. ZUSAETZLICH: berechneten Inhalts-Hash gegen das gespeicherte Siegel
         (forensic_meta['sha256']) pruefen — die Kopie MUSS die echte, versiegelte
         DB sein, bevor sie zurueckgeschrieben wird.
      4. Die konvertierte Kopie ATOMAR ueber das Original legen (erst als
         Nachbardatei auf den Share schreiben, dann os.replace). Das Original wird
         nie truncated; haelt ein Server es offen, scheitert der Austausch sauber,
         ohne das Original zu beschaedigen (GR1).
      5. Den urspruenglichen Schreibschutz (Siegel) wiederherstellen; lokale
         Kopien entfernen.

    Returns True, wenn umgestempelt (bzw. im Trockenlauf: waere), sonst False.
    Raises SealError bei Siegelbruch, ConvertError bei operativem Fehler.
    """
    print(f"\n  {db}   [via Staging]")
    stempel = header_stempel(db)
    if stempel is None:
        print("    KEINE SQLite-Datei — uebersprungen (gemeldet, nicht still).")
        return False
    if stempel == ERWARTETER_STEMPEL[ziel]:
        print(f"    Bereits im Zielzustand fuer '{ziel}' — keine Aenderung noetig.")
        return False

    ist_forensic = db.name.startswith("forensic_")
    print(f"    Header vorher : write_version={stempel} "
          f"({'WAL' if stempel == 2 else 'rollback-journal'})")
    print(f"    Groesse       : {db.stat().st_size} B")
    print(f"    Staging-Ziel  : {staging_dir.resolve()}")

    if not apply:
        print("    WUERDE via Staging umgestempelt (Kopie -> Konvertierung -> "
              "verifizierte Rueckkopie). Trockenlauf — nichts geschrieben.")
        return True

    if not staging_dir.is_dir():
        raise ConvertError(f"--staging-dir nicht gefunden: {staging_dir}")

    # Eigenes Unterverzeichnis je DB, um Kollisionen auszuschliessen.
    arbeit = staging_dir / f"_convert_{db.stem}"
    if arbeit.exists():
        raise ConvertError(
            f"Staging-Arbeitsverzeichnis existiert bereits (bitte aufraeumen): "
            f"{arbeit}")
    arbeit.mkdir(parents=True)
    lokale_db = arbeit / db.name

    try:
        # (1) Kopieren: .db plus vorhandene Sidecars.
        for suffix in ("", "-wal", "-shm"):
            quelle = db.with_name(db.name + suffix)
            if quelle.exists():
                ziel_pfad = arbeit / quelle.name
                shutil.copy2(str(quelle), str(ziel_pfad))
                # Kopie muss beschreibbar sein (das Original ist versiegelt).
                if ist_schreibgeschuetzt(ziel_pfad):
                    schreibschutz_aufheben(ziel_pfad)
        print("    Kopiert (inkl. vorhandener -wal/-shm).")

        # (2) Lokale Umstempelung mit der REGULAEREN Logik (inkl. Hash-Kontrolle).
        if not verarbeite(lokale_db, ziel, apply=True):
            raise ConvertError(
                f"Lokale Umstempelung meldete 'keine Aenderung' — unerwartet fuer "
                f"eine WAL-DB: {db}")

        # (3) Zusatz-Absicherung fuer forensic: gegen gespeichertes Siegel pruefen.
        if ist_forensic:
            con = sqlite3.connect(str(lokale_db), timeout=10.0)
            try:
                berechnet = inhalts_hash(con)
                gespeichert = gespeicherter_siegelhash(con)
            finally:
                con.close()
            if gespeichert is None:
                print("    HINWEIS: forensic_meta['sha256'] fehlt — kann nicht gegen "
                      "das gespeicherte Siegel pruefen (nur vorher==nachher wurde "
                      "verifiziert). Gemeldet, nicht still uebergangen (GR1).")
            elif berechnet != gespeichert:
                raise SealError(
                    "STAGING-KOPIE PASST NICHT ZUM GESPEICHERTEN SIEGEL — es wird "
                    "NICHTS zurueckgeschrieben. "
                    f"Datei: {db}\n  berechnet   : {berechnet}\n  "
                    f"forensic_meta['sha256']: {gespeichert}")
            else:
                print(f"    Siegel-Gegenprobe OK: {berechnet}")

        # (4) Atomarer Austausch: erst Nachbardatei auf dem Share, dann os.replace.
        ersatz = db.with_name(db.name + ".konvertiert")
        shutil.copy2(str(lokale_db), str(ersatz))
        if header_stempel(ersatz) != ERWARTETER_STEMPEL[ziel]:
            ersatz.unlink(missing_ok=True)
            raise ConvertError(
                f"Ersatzdatei hat unerwarteten Stempel — Abbruch, Original "
                f"unberuehrt: {db}")

        alt_modus = None
        if ist_schreibgeschuetzt(db):
            alt_modus = schreibschutz_aufheben(db)  # Siegel kurz oeffnen
        try:
            os.replace(str(ersatz), str(db))        # atomar auf demselben Share
        except OSError as exc:
            ersatz.unlink(missing_ok=True)
            raise ConvertError(
                f"Atomarer Austausch fehlgeschlagen (haelt ein Server die DB "
                f"offen?): {exc}. Original UNBERUEHRT: {db}") from exc
        finally:
            if alt_modus is not None:
                schreibschutz_wiederherstellen(db, alt_modus)  # Siegel wieder setzen

        # Verwaiste Sidecars des Originals entfernen (Header ist jetzt rollback).
        for rest in nebendateien(db):
            try:
                if ist_schreibgeschuetzt(rest):
                    schreibschutz_aufheben(rest)
                rest.unlink()
                print(f"    Rest am Original entfernt: {rest.name}")
            except OSError as exc:
                print(f"    HINWEIS: Rest nicht entfernbar: {rest.name} ({exc!r})")

        stempel_nachher = header_stempel(db)
        if stempel_nachher != ERWARTETER_STEMPEL[ziel]:
            raise ConvertError(
                f"Header-Stempel am Original nach Rueckkopie unerwartet: "
                f"{stempel_nachher} (erwartet {ERWARTETER_STEMPEL[ziel]}). {db}")
        print(f"    UMGESTEMPELT via Staging auf '{ziel}'. ✓")
        return True
    finally:
        # Lokale Kopien immer entfernen (enthalten Beweismittel-Inhalte).
        shutil.rmtree(str(arbeit), ignore_errors=True)


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stempelt SQLite-DBs zwischen WAL und Rollback-Journal um "
                    "(Trockenlauf ist Default)."
    )
    ap.add_argument("--data-dir", default="./data",
                    help="Verzeichnis mit den *.db-Dateien (Default: ./data). "
                         "Wird ignoriert, wenn --db gesetzt ist.")
    ap.add_argument("--db", default=None,
                    help="Genau EINE Datenbankdatei konvertieren (Pfad). "
                         "Nuetzlich, um gezielt eine Nutzer-DB umzustempeln, "
                         "ohne an einer gesperrten geteilten DB (coordinator.db) "
                         "zu haengen. Hat Vorrang vor --data-dir.")
    ap.add_argument("--skip-on-error", action="store_true",
                    help="Operative Fehler (locked, I/O, unerwarteter Stempel) "
                         "melden und ueberspringen, statt abzubrechen — der Lauf "
                         "faehrt mit den uebrigen DBs fort. Ein SIEGELBRUCH "
                         "(Inhalts-Hash-Abweichung) wird NIE uebersprungen.")
    ap.add_argument("--to", default="delete", choices=list(ALL_TARGETS),
                    help="Zielmodus (Default: delete — Empfehlung fuer Netzlaufwerke)")
    ap.add_argument("--staging-dir", default=None,
                    help="LOKALES Verzeichnis fuer versiegelte WAL-DBs, die sich auf "
                         "dem Netzlaufwerk nicht in place umstempeln lassen. Die DB "
                         "wird dorthin kopiert, lokal umgestempelt, der Inhalts-Hash "
                         "gegen das Siegel geprueft und atomar zurueckkopiert. Greift "
                         "nur fuer schreibgeschuetzte, WAL-gestempelte Dateien.")
    ap.add_argument("--apply", action="store_true",
                    help="SCHARF schalten. Ohne diesen Schalter wird nichts geschrieben.")
    args = ap.parse_args(argv)

    staging_dir = Path(args.staging_dir) if args.staging_dir else None

    # --- DB-Auswahl: --db (eine Datei) hat Vorrang vor --data-dir -------------
    if args.db is not None:
        einzel = Path(args.db)
        if not einzel.is_file():
            print(f"[FEHLER] --db: Datei nicht gefunden: {einzel}", file=sys.stderr)
            return 1
        dbs = [einzel]
        quelle = f"Einzeldatei: {einzel.resolve()}"
    else:
        data = Path(args.data_dir)
        if not data.is_dir():
            print(f"[FEHLER] Datenverzeichnis nicht gefunden: {data}", file=sys.stderr)
            return 1
        dbs = sorted(data.rglob("*.db"))
        quelle = f"Verzeichnis: {data.resolve()}"

    print("=" * 78)
    print(f"JOURNALMODUS-UMSTEMPELUNG — Ziel: '{args.to}' | "
          f"{'SCHARF (--apply)' if args.apply else 'TROCKENLAUF (nichts wird geschrieben)'}")
    print(quelle)
    if args.skip_on_error:
        print("Modus      : --skip-on-error (operative Fehler werden gemeldet und "
              "uebersprungen; Siegelbruch bricht dennoch hart ab)")
    print(f"SQLite     : {sqlite3.sqlite_version}")
    print("=" * 78)

    if not dbs:
        print("Keine *.db gefunden — nichts zu tun.")
        return 0

    geaendert = 0
    # Uebersprungene Dateien werden gesammelt und am Ende NAMENTLICH gemeldet
    # (Grundregel 1: kein Beleg wird still uebergangen).
    uebersprungen: list[tuple[Path, str]] = []

    for db in dbs:
        try:
            # Build 434: eine versiegelte (schreibgeschuetzte), WAL-gestempelte DB
            # kann auf dem Netzlaufwerk nicht in place umgestempelt werden — dann
            # ueber das lokale Staging gehen, sofern --staging-dir gesetzt ist.
            via_staging = (
                staging_dir is not None
                and header_stempel(db) == 2
                and ist_schreibgeschuetzt(db)
            )
            if via_staging:
                getan = verarbeite_via_staging(db, args.to, args.apply, staging_dir)
            else:
                getan = verarbeite(db, args.to, args.apply)
            if getan:
                geaendert += 1
        except SealError as exc:
            # Siegelbruch: IMMER harter Abbruch, unabhaengig von --skip-on-error.
            print(f"\n[ABBRUCH — SIEGELBRUCH] {exc}", file=sys.stderr)
            print("Es wurden KEINE weiteren Dateien angefasst.", file=sys.stderr)
            return 1
        except ConvertError as exc:
            if args.skip_on_error:
                print(f"    [UEBERSPRUNGEN wegen Fehler] {exc}", file=sys.stderr)
                uebersprungen.append((db, str(exc)))
                continue
            print(f"\n[ABBRUCH] {exc}", file=sys.stderr)
            print("Es wurden KEINE weiteren Dateien angefasst. "
                  "(Mit --skip-on-error wuerde der Lauf die uebrigen DBs "
                  "dennoch verarbeiten.)", file=sys.stderr)
            return 1

    print("\n" + "=" * 78)
    if args.apply:
        print(f"FERTIG: {geaendert} von {len(dbs)} Datenbanken umgestempelt.")
    else:
        print(f"TROCKENLAUF: {geaendert} von {len(dbs)} Datenbanken WUERDEN "
              f"umgestempelt. Mit --apply scharf schalten.")

    if uebersprungen:
        # GR1: die uebersprungenen DBs werden ausdruecklich und vollstaendig
        # aufgezaehlt, damit niemand von einem vollstaendigen Lauf ausgeht.
        print(f"\nUEBERSPRUNGEN (wegen Fehler, --skip-on-error): {len(uebersprungen)}")
        for db, grund in uebersprungen:
            print(f"  {db}\n      -> {grund}")
        print("Diese Datenbanken sind NICHT konvertiert und muessen nachgezogen "
              "werden, sobald ihre Sperre aufgehoben ist.")
    print("=" * 78)

    # Exitcode: 2, wenn der Lauf zwar durchlief, aber >=1 DB uebersprungen wurde.
    # So erkennt auch eine Automatisierung, dass NICHT alles erledigt ist.
    return 2 if uebersprungen else 0


if __name__ == "__main__":
    raise SystemExit(main())
