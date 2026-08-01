#!/usr/bin/env python3
# =============================================================================
# tools/diag_backup_verdraengung.py
# IT-Forensisches Ermittlungswerkzeug - Diagnose (Build 642)
# =============================================================================
# Zweck:
#   Beantwortet EINE Frage nachpruefbar: Kann eine DEFEKTE Sicherungskopie
#   eine GUTE Generation aus der Aufbewahrung verdraengen?
#
#   Das ist der Vorgang 651e6d84 ("Sicherungs-Aufbewahrung verdraengt gute
#   Generationen durch defekte", kritisch). Die Builds 625-627 sollen ihn
#   behoben haben. Dieses Werkzeug prueft das nach - es behauptet nichts,
#   es misst.
#
# WARUM ES DIESES WERKZEUG GIBT - DIE FRAGE, DIE ES BEANTWORTBAR MACHT:
#   Um die Behebung zu pruefen, braucht man eine defekte Kopie. Die entsteht
#   im Betrieb durch einen Abbruch mitten im Schreiben, und darauf kann man
#   nicht warten. Dieses Werkzeug erzeugt sie auf DREI Wegen, vom billigsten
#   zum echtesten:
#
#     Probe A  UNTERGESCHOBEN. Eine 0-Byte-Datei mit einem zaehlenden Namen
#              und dem juengsten Zeitstempel wird in den Ordner gelegt. Das
#              ist keine Nachstellung des Symptoms, das IST das Symptom: Der
#              Vorgang beschreibt genau diesen Zustand ("die Datei bleibt
#              liegen und traegt den aktuellen Zeitstempel im Namen").
#              Deterministisch, in Sekunden, auf jedem System.
#
#     Probe S  DIE SELBSTPROBE. Derselbe Ordner, aber gegen den Stand VOR
#              Build 625 gefahren (die eine hinzugefuegte Pruefung wird
#              wieder weggenommen). Hier MUSS sich der Vorgang zeigen.
#              Tut er es nicht, ist Probe A blind, und ihr 'BESTANDEN'
#              belegt nichts. Diese Probe laeuft IMMER und steht VORNE.
#
#     Probe B  DIE GEGENPROBE (Grundregel: eine Pruefung, die nie anschlaegt,
#              belegt nichts). Derselbe Ordner, aber mit einer GUTEN vierten
#              Generation statt der defekten. Hier MUSS die aelteste geloescht
#              werden. Ohne diese Probe wuerde Probe A auch dann bestehen,
#              wenn die Aufbewahrung ueberhaupt nichts mehr loescht - und das
#              waere ein anderer Fehler, nicht die Behebung.
#
#     Probe C  ECHTER ABBRUCHREST. Ein 'VACUUM INTO' wird mitten im Lauf
#              abgeschossen. Das ist der Weg, auf dem der Vorgang im Betrieb
#              entsteht; er braucht eine ausreichend grosse Quelle, damit der
#              Abbruch ueberhaupt einen Zeitpunkt hat. Nur diese Probe deckt
#              die Kette 'Kopie beurteilen -> beiseitelegen -> nicht zaehlen'
#              vollstaendig ab.
#
# SICHERHEIT - BITTE LESEN:
#   Das Werkzeug arbeitet AUSSCHLIESSLICH in einem Wegwerf-Verzeichnis, das
#   es selbst anlegt. Es oeffnet keine Datenbank des Bestandes, es liest die
#   config.yaml des Bestandes nicht, und es schreibt nirgendwo sonst hin.
#   Ein bereits vorhandenes, nicht leeres Zielverzeichnis wird abgelehnt.
#
# Aufruf:
#   python tools/diag_backup_verdraengung.py --arbeitsverzeichnis ./tmp_651e6d84
#   python tools/diag_backup_verdraengung.py --arbeitsverzeichnis ./tmp --mit-abbruch
#   python tools/diag_backup_verdraengung.py --arbeitsverzeichnis ./tmp --behalten
#
# Rueckgabewerte:
#   0  Alle gefahrenen Proben bestanden - der Vorgang ist behoben.
#   1  MINDESTENS EINE PROBE HAT DEN VORGANG NACHGEWIESEN. Das ist der
#      Ernstfall: eine defekte Kopie verdraengt eine gute Generation.
#   2  Aufruffehler oder die Vorbereitung ist gescheitert (dann ist NICHTS
#      geprueft - ein nicht gefahrener Test ist kein bestandener Test).
#
# Version: v0.8.642 - Build: 642 - 2026-08-01
# =============================================================================

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from management.backup.backup_config import BackupConfig       # noqa: E402
from management.backup.backup_executor import (                # noqa: E402
    DEFEKT_ENDUNG, BackupExecutor,
)
from management.help import cli_epilog                          # noqa: E402

#: Wie viele Generationen die Probe aufbewahrt. Bewusst klein: die Probe soll
#: die Grenze erreichen, ohne dass jemand zwanzig Laeufe abwarten muss.
RETENTION = 3

#: Groesse der Wegwerf-Quelle fuer Probe C, in Megabyte. 'VACUUM INTO' muss
#: lange genug laufen, dass ein Abbruch ueberhaupt einen Zeitpunkt hat - bei
#: einer 1-MB-Datei ist die Kopie fertig, bevor man abschiessen kann.
ABBRUCH_QUELLE_MB = 120


# -----------------------------------------------------------------------------
# Ausgabe
# -----------------------------------------------------------------------------

class Bericht:
    """Sammelt die Befunde und haelt fest, ob eine Probe wirklich lief."""

    def __init__(self) -> None:
        self.zeilen: List[str] = []
        self.gefahren: List[str] = []
        self.durchgefallen: List[str] = []
        self.nicht_gefahren: List[Tuple[str, str]] = []

    def sagen(self, text: str = "") -> None:
        print(text)
        self.zeilen.append(text)

    def probe(self, name: str, bestanden: bool, befund: str) -> None:
        self.gefahren.append(name)
        marke = "BESTANDEN" if bestanden else "DURCHGEFALLEN"
        self.sagen("  [%s] %s" % (marke, name))
        for z in befund.splitlines():
            self.sagen("      " + z)
        if not bestanden:
            self.durchgefallen.append(name)

    def uebersprungen(self, name: str, grund: str) -> None:
        # KEIN STILLES UEBERSPRINGEN (Grundregel 1). Eine Probe, die nicht
        # lief, steht namentlich im Schlussbericht - sonst saehe ein
        # halber Lauf aus wie ein ganzer.
        self.nicht_gefahren.append((name, grund))
        self.sagen("  [NICHT GEFAHREN] %s" % name)
        self.sagen("      " + grund)


# -----------------------------------------------------------------------------
# Wegwerf-Bestand
# -----------------------------------------------------------------------------

def _db_bauen(pfad: Path, zeilen: int, user_version: int = 42) -> None:
    """
    Legt eine Wegwerf-Datenbank an - mit Schema und Inhalt.

    BEIDES IST NOETIG, und das ist kein Beiwerk: Die Beurteilung einer Kopie
    (Build 625) vergleicht 'user_version' und die Zahl der Schemaobjekte mit
    der Quelle und verlangt, dass die Kopie nicht leer ist, wenn die Quelle
    es nicht war. Eine leere Attrappe wuerde diese Pruefungen gar nicht erst
    erreichen - die Probe liefe ins Nichts und saehe aus wie ein Erfolg.
    """
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(pfad))
    try:
        con.execute("PRAGMA journal_mode=DELETE")   # WAL ist projektweit verboten
        con.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY, fuellung TEXT)")
        con.execute("CREATE INDEX probe_fuellung ON probe(fuellung)")
        con.execute("PRAGMA user_version=%d" % user_version)
        block = "x" * 512
        con.executemany("INSERT INTO probe (fuellung) VALUES (?)",
                        ((block,) for _ in range(zeilen)))
        con.commit()
    finally:
        con.close()


def _cfg(dest_dir: Path) -> BackupConfig:
    return BackupConfig(
        dest_dir=str(dest_dir), retention_count=RETENTION,
        min_free_factor=1.3, checkpoint="none", include_shared_dbs=True)


def _generation_anlegen(dest_dir: Path, label: str, ts: str,
                        quelle: Optional[Path]) -> Path:
    """
    Legt eine Datei mit ZAEHLENDEM Namen an.

    quelle=None -> 0 Byte, also die DEFEKTE Kopie. Genau so sieht der
    Abbruchrest aus, nachdem SQLite sein Journal zurueckgerollt hat (gemessen
    Build 626, siehe Kopf von backup_executor.py).
    """
    name = "%s_v42_%s_pruefhost.backup.db" % (label, ts)
    ziel = dest_dir / name
    if quelle is None:
        ziel.write_bytes(b"")
    else:
        shutil.copyfile(quelle, ziel)
    return ziel


def _zaehlende(dest_dir: Path, label: str) -> List[str]:
    """Die Dateien, die die Aufbewahrung als Generation ZAEHLEN wuerde."""
    return sorted(n for n in os.listdir(dest_dir)
                  if n.startswith(label + "_v") and n.endswith(".backup.db"))


# -----------------------------------------------------------------------------
# Probe A - die untergeschobene defekte Kopie
# -----------------------------------------------------------------------------

def probe_a(arbeit: Path, ber: Bericht) -> bool:
    """
    DER KERN DES VORGANGS. Drei gute Generationen, dazu eine 0-Byte-Datei mit
    dem JUENGSTEN Zeitstempel. Aufbewahrung: 3.

    Vor der Behebung: Die defekte Datei zaehlt als juengste Generation, die
    drei juengsten werden behalten - also die defekte und zwei gute -, und
    die aelteste GUTE wird geloescht. Ergebnis: 2 gute statt 3.

    Nach der Behebung: Die defekte Datei wird beiseitegelegt ('.defekt') und
    zaehlt nicht. Es bleiben 3 gute; geloescht wird nichts.
    """
    dest = arbeit / "probe_a"
    dest.mkdir(parents=True)
    quelle = arbeit / "quelle_klein.db"

    gute = [_generation_anlegen(dest, "coordinator", ts, quelle)
            for ts in ("20260801T100000Z", "20260801T110000Z",
                       "20260801T120000Z")]
    defekt = _generation_anlegen(dest, "coordinator", "20260801T130000Z", None)

    exe = BackupExecutor(_cfg(dest))
    erg = exe._prune(str(dest))            # gute_labels=None -> alle Labels

    verbleibend = _zaehlende(dest, "coordinator")
    beiseite = [n for n in os.listdir(dest) if n.endswith(DEFEKT_ENDUNG)]
    ueberlebende_gute = [p.name for p in gute if p.name in verbleibend]

    bestanden = (len(ueberlebende_gute) == 3
                 and defekt.name not in verbleibend
                 and len(beiseite) == 1)
    befund = (
        "Ausgangslage : 3 gute Generationen + 1 defekte (0 Byte, juengster "
        "Zeitstempel), Aufbewahrung %d\n"
        "Gute ueberlebt: %d von 3   %s\n"
        "Defekte zaehlt: %s\n"
        "Beiseitegelegt: %d Datei(en) %s\n"
        "Geloescht     : %s"
        % (RETENTION, len(ueberlebende_gute),
           "" if len(ueberlebende_gute) == 3
           else "<-- VERDRAENGT: " + ", ".join(
               p.name for p in gute if p.name not in verbleibend),
           "NEIN" if defekt.name not in verbleibend
           else "JA <-- der Vorgang ist NICHT behoben",
           len(beiseite), beiseite or "",
           [os.path.basename(p) for p in erg.geloescht] or "nichts"))
    ber.probe("A - defekte Kopie verdraengt eine gute Generation", bestanden,
              befund)
    return bestanden


# -----------------------------------------------------------------------------
# Probe B - die Gegenprobe
# -----------------------------------------------------------------------------

def probe_b(arbeit: Path, ber: Bericht) -> bool:
    """
    DIE GEGENPROBE, und sie ist nicht weniger wichtig als Probe A.

    Dieselbe Lage, aber die vierte Datei ist GUT. Jetzt MUSS die aelteste
    geloescht werden - denn genau das ist die Aufgabe der Aufbewahrung.

    Ohne diese Probe wuerde Probe A auch dann bestehen, wenn die Aufbewahrung
    ueberhaupt nichts mehr loescht. Das waere kein behobener Vorgang, sondern
    ein neuer: ein Sicherungsordner, der unbegrenzt waechst, bis die
    Platzvorabpruefung jeden weiteren Lauf verweigert.
    """
    dest = arbeit / "probe_b"
    dest.mkdir(parents=True)
    quelle = arbeit / "quelle_klein.db"

    alle = [_generation_anlegen(dest, "coordinator", ts, quelle)
            for ts in ("20260801T100000Z", "20260801T110000Z",
                       "20260801T120000Z", "20260801T130000Z")]
    aeltester = alle[0]

    exe = BackupExecutor(_cfg(dest))
    erg = exe._prune(str(dest))
    verbleibend = _zaehlende(dest, "coordinator")

    bestanden = (aeltester.name not in verbleibend
                 and len(verbleibend) == RETENTION)
    befund = (
        "Ausgangslage : 4 GUTE Generationen, Aufbewahrung %d\n"
        "Verbleibend  : %d (erwartet %d)\n"
        "Geloescht    : %s\n"
        "%s"
        % (RETENTION, len(verbleibend), RETENTION,
           [os.path.basename(p) for p in erg.geloescht] or "nichts",
           "" if bestanden else
           "<-- Die Aufbewahrung loescht NICHT. Dann belegt Probe A nichts:\n"
           "    sie wuerde auch bei voellig untaetiger Aufbewahrung bestehen."))
    ber.probe("B - Gegenprobe: die Aufbewahrung loescht ueberhaupt",
              bestanden, befund)
    return bestanden


# -----------------------------------------------------------------------------
# Probe C - der echte Abbruchrest
# -----------------------------------------------------------------------------

def _abbruchrest_erzeugen(arbeit: Path, ber: Bericht) -> Optional[Path]:
    """
    Erzeugt eine ECHTE Teildatei, indem ein laufendes 'VACUUM INTO'
    abgeschossen wird.

    WIE DER ABBRUCH ZUVERLAESSIG GETROFFEN WIRD: Nicht nach fester Zeit -
    das trifft auf einer schnellen Platte nichts. Es wird gewartet, bis die
    Zieldatei eine Mindestgroesse erreicht hat, und ERST DANN abgeschossen.
    Damit ist sichergestellt, dass ueberhaupt schon geschrieben wurde.

    Laeuft auf Windows und Linux gleichermassen: Popen.kill() beendet den
    Prozess abrupt (Windows: TerminateProcess, Linux: SIGKILL). Beides laesst
    die Teildatei mitsamt Journal liegen - genau der gesuchte Zustand.
    """
    quelle = arbeit / "quelle_gross.db"
    ziel = arbeit / "abbruch" / "coordinator_v42_20260801T140000Z_pruefhost.backup.db"
    ziel.parent.mkdir(parents=True, exist_ok=True)

    skript = (
        "import sqlite3,sys\n"
        "con=sqlite3.connect(sys.argv[1])\n"
        "con.execute(\"VACUUM INTO ?\",(sys.argv[2],))\n"
        "con.close()\n")
    proc = subprocess.Popen([sys.executable, "-c", skript,
                             str(quelle), str(ziel)])
    frist = time.monotonic() + 30.0
    getroffen = False
    while time.monotonic() < frist:
        if proc.poll() is not None:
            break                                  # zu schnell fertig
        if ziel.exists() and ziel.stat().st_size > 4 * 1024 * 1024:
            proc.kill()
            getroffen = True
            break
        time.sleep(0.02)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:              # pragma: no cover
        proc.kill()

    if not getroffen:
        ber.uebersprungen(
            "C - echter Abbruchrest",
            "Das 'VACUUM INTO' war fertig, bevor der Abbruch greifen konnte "
            "(Quelle %d MB, sehr schnelle Platte). Mit einer groesseren "
            "Quelle erneut versuchen: ABBRUCH_QUELLE_MB im Kopf dieses "
            "Werkzeugs erhoehen. NICHT GEPRUEFT heisst NICHT BESTANDEN."
            % ABBRUCH_QUELLE_MB)
        return None
    if not ziel.exists():                          # pragma: no cover
        ber.uebersprungen(
            "C - echter Abbruchrest",
            "Nach dem Abbruch lag keine Teildatei am Ziel. Ohne sie ist "
            "nichts zu pruefen.")
        return None
    return ziel


def probe_c(arbeit: Path, ber: Bericht) -> bool:
    """
    Die ganze Kette an einem ECHTEN Abbruchrest: Wird er als nicht belegt
    erkannt, verliert er den zaehlenden Namen - und zaehlt danach nicht als
    Generation?

    DIESE PROBE IST DIE EINZIGE, DIE BEFUND 2 AUS BUILD 625 MIT ABDECKT:
    'PRAGMA integrity_check' meldet auf der zurueckgerollten 0-Byte-Datei
    'ok'. Wer nur den integrity_check prueft, bekommt hier ein 'bestanden'
    fuer ein Nichts.
    """
    rest = _abbruchrest_erzeugen(arbeit, ber)
    if rest is None:
        return True            # nicht gefahren - steht im Schlussbericht

    groesse = rest.stat().st_size
    journal = [p.name for p in rest.parent.iterdir()
               if p.name.startswith(rest.name) and p.name != rest.name]

    dest = rest.parent
    quelle = arbeit / "quelle_klein.db"
    for ts in ("20260801T100000Z", "20260801T110000Z", "20260801T120000Z"):
        _generation_anlegen(dest, "coordinator", ts, quelle)

    exe = BackupExecutor(_cfg(dest))
    erg = exe._prune(str(dest))
    verbleibend = _zaehlende(dest, "coordinator")

    bestanden = (rest.name not in verbleibend and len(verbleibend) == 3)
    befund = (
        "Teildatei    : %d Byte, Begleitdateien %s\n"
        "Zaehlt noch  : %s\n"
        "Gute ueberlebt: %d von 3\n"
        "Geloescht    : %s"
        % (groesse, journal or "keine",
           "NEIN" if rest.name not in verbleibend
           else "JA <-- der echte Abbruchrest verdraengt eine gute Generation",
           len(verbleibend),
           [os.path.basename(p) for p in erg.geloescht] or "nichts"))
    ber.probe("C - echter Abbruchrest zaehlt nicht als Generation",
              bestanden, befund)
    return bestanden


# -----------------------------------------------------------------------------
# Probe S - die Selbstprobe
# -----------------------------------------------------------------------------

def probe_s(arbeit: Path, ber: Bericht) -> bool:
    """
    SIEHT DIESES WERKZEUG DEN FEHLER UEBERHAUPT?

    Das ist die unbequemste Frage an jede Nachpruefung, und sie wird zu
    selten gestellt: Probe A besteht auch dann, wenn sie blind ist. Ein
    'BESTANDEN' von einer Probe, die gar nichts messen kann, ist schlimmer
    als kein Ergebnis - es beendet die Suche.

    Deshalb wird hier derselbe Ordner GEGEN DEN STAND VOR BUILD 625 gefahren.
    Nachgestellt wird er an genau einer Stelle: '_traegt_inhalt' liefert
    immer True. Das ist praezise die Pruefung, die Build 625 hinzugefuegt hat
    - vorher zaehlte jede Datei mit passendem Namen als Generation, ohne dass
    jemand hineingesehen haette.

    ERWARTET WIRD HIER EIN FEHLSCHLAG. Bleibt er aus, misst Probe A nichts,
    und der ganze Lauf ist wertlos - dann meldet dieses Werkzeug das, statt
    Entwarnung zu geben.
    """
    dest = arbeit / "probe_s"
    dest.mkdir(parents=True)
    quelle = arbeit / "quelle_klein.db"

    gute = [_generation_anlegen(dest, "coordinator", ts, quelle)
            for ts in ("20260801T100000Z", "20260801T110000Z",
                       "20260801T120000Z")]
    defekt = _generation_anlegen(dest, "coordinator", "20260801T130000Z", None)

    exe = BackupExecutor(_cfg(dest))
    # Die EINE Zeile, die Build 625 gebracht hat, wieder wegnehmen:
    exe._traegt_inhalt = lambda pfad: (True, "ok")
    erg = exe._prune(str(dest))

    verbleibend = _zaehlende(dest, "coordinator")
    ueberlebende_gute = [p.name for p in gute if p.name in verbleibend]

    # Der Vorgang MUSS sich hier zeigen - sonst ist die Probe blind.
    zeigt_sich = (len(ueberlebende_gute) < 3 and defekt.name in verbleibend)
    befund = (
        "Nachgestellt : Stand vor Build 625 ('_traegt_inhalt' liefert immer "
        "True)\n"
        "Gute ueberlebt: %d von 3\n"
        "Defekte zaehlt: %s\n"
        "Geloescht     : %s\n"
        "%s"
        % (len(ueberlebende_gute),
           "JA" if defekt.name in verbleibend else "nein",
           [os.path.basename(p) for p in erg.geloescht] or "nichts",
           "Erwartet war genau das: Der alte Stand verdraengt eine gute "
           "Generation.\nDie Probe kann den Fehler also sehen."
           if zeigt_sich else
           "<-- HIER HAETTE SICH DER VORGANG ZEIGEN MUESSEN. Er tut es nicht.\n"
           "    Damit misst Probe A nichts, und ihr 'BESTANDEN' belegt nichts."))
    ber.probe("S - Selbstprobe: die Probe kann den Fehler sehen",
              zeigt_sich, befund)
    return zeigt_sich


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="diag_backup_verdraengung",
        description="Prueft nach, ob eine defekte Sicherungskopie eine gute "
                    "Generation verdraengen kann (Vorgang 651e6d84). "
                    "Arbeitet ausschliesslich in einem Wegwerf-Verzeichnis.",
        epilog=cli_epilog.epilog("diag_backup_verdraengung"),
        formatter_class=cli_epilog.HilfeFormat)
    ap.add_argument("--arbeitsverzeichnis", required=True,
                    help="Wegwerf-Verzeichnis. MUSS leer sein oder nicht "
                         "existieren - ein vorhandener Inhalt wird nicht "
                         "angetastet, der Aufruf bricht dann ab.")
    ap.add_argument("--mit-abbruch", action="store_true", dest="mit_abbruch",
                    help="Zusaetzlich Probe C fahren: einen ECHTEN "
                         "Abbruchrest erzeugen, indem ein laufendes 'VACUUM "
                         "INTO' abgeschossen wird. Braucht rund %d MB "
                         "Plattenplatz und einige Sekunden."
                         % (ABBRUCH_QUELLE_MB * 2))
    ap.add_argument("--behalten", action="store_true",
                    help="Das Wegwerf-Verzeichnis nach dem Lauf stehen "
                         "lassen, um hineinzusehen.")
    args = ap.parse_args(argv)

    arbeit = Path(args.arbeitsverzeichnis).resolve()
    if arbeit.exists() and any(arbeit.iterdir()):
        print("[FEHLER] '%s' ist nicht leer. Dieses Werkzeug legt nur in "
              "einem eigenen, leeren Verzeichnis an - ein vorhandener "
              "Bestand wird nicht angetastet." % arbeit, file=sys.stderr)
        return 2

    ber = Bericht()
    ber.sagen("=" * 78)
    ber.sagen("NACHPRUEFUNG VORGANG 651e6d84")
    ber.sagen("Kann eine defekte Sicherungskopie eine gute Generation "
              "verdraengen?")
    ber.sagen("=" * 78)
    ber.sagen("Arbeitsverzeichnis: %s" % arbeit)
    ber.sagen("Aufbewahrung (retention_count): %d" % RETENTION)
    ber.sagen()

    try:
        arbeit.mkdir(parents=True, exist_ok=True)
        _db_bauen(arbeit / "quelle_klein.db", zeilen=200)
        if args.mit_abbruch:
            ber.sagen("Baue die grosse Wegwerf-Quelle (%d MB) fuer Probe C ..."
                      % ABBRUCH_QUELLE_MB)
            _db_bauen(arbeit / "quelle_gross.db",
                      zeilen=ABBRUCH_QUELLE_MB * 1800)
            ber.sagen("  %d Byte"
                      % (arbeit / "quelle_gross.db").stat().st_size)
            ber.sagen()
    except Exception as exc:
        print("[FEHLER] Vorbereitung gescheitert: %s\nEs ist NICHTS geprueft "
              "worden." % exc, file=sys.stderr)
        return 2

    alles_gut = True
    # DIE SELBSTPROBE STEHT VORNE. Wer sie hinten anhaengt, liest sie
    # womoeglich nicht mehr - und sie entscheidet darueber, ob alles
    # Folgende ueberhaupt etwas wert ist.
    alles_gut &= probe_s(arbeit, ber)
    ber.sagen()
    alles_gut &= probe_a(arbeit, ber)
    ber.sagen()
    alles_gut &= probe_b(arbeit, ber)
    ber.sagen()
    if args.mit_abbruch:
        alles_gut &= probe_c(arbeit, ber)
    else:
        ber.uebersprungen(
            "C - echter Abbruchrest",
            "Nicht angefordert. Mit '--mit-abbruch' fahren - erst diese Probe "
            "deckt die Kette 'Kopie beurteilen -> beiseitelegen -> nicht "
            "zaehlen' an einem ECHTEN Abbruch ab.")
    ber.sagen()

    ber.sagen("=" * 78)
    if ber.durchgefallen:
        ber.sagen("BEFUND: DER VORGANG 651e6d84 IST NICHT BEHOBEN.")
        for n in ber.durchgefallen:
            ber.sagen("  durchgefallen: %s" % n)
        rc = 1
    else:
        ber.sagen("BEFUND: Alle GEFAHRENEN Proben bestanden - eine defekte "
                  "Kopie verdraengt keine gute Generation.")
        rc = 0
    if ber.nicht_gefahren:
        # Grundregel 1: Was nicht geprueft wurde, steht im Schlussbericht.
        ber.sagen()
        ber.sagen("NICHT GEPRUEFT (%d) - das ist kein Bestanden:"
                  % len(ber.nicht_gefahren))
        for n, grund in ber.nicht_gefahren:
            ber.sagen("  %s" % n)
    ber.sagen("=" * 78)

    if not args.behalten:
        shutil.rmtree(arbeit, ignore_errors=True)
    else:
        ber.sagen("Wegwerf-Verzeichnis bleibt stehen: %s" % arbeit)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
