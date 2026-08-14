# =============================================================================
# management/backup/backup_executor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# BackupExecutor — Phase des SCHREIBENS (Build 353). Fuehrt fuer jeden Eintrag
# eines geprueften BackupPlan die eigentliche Sicherung durch:
#
#   1) optional 'wal_checkpoint(PASSIVE)' auf der Quelle (nicht blockierend;
#      nie TRUNCATE) — je config.backup.checkpoint,
#   2) transaktionaler Snapshot per 'VACUUM INTO' (via BackupTool, Build 317;
#      Quelle wird NICHT veraendert),
#   3) 'PRAGMA integrity_check' auf der KOPIE (zertifiziert das Backup, stoert
#      keinen Livezugriff; Beleg: Bauplan B7 v1.1 §11 Punkt 7),
#   4) SHA512 (aus BackupTool) als Integritaets-/Provenienzsiegel.
#
# Robustheit (Grundregel 1 — kein stiller Fehlpfad): ein Fehler bei EINER DB
# bricht den Gesamtlauf NICHT ab. Jede DB wird einzeln bilanziert; der Lauf ist
# nur dann ok, wenn ALLE Sicherungen erfolgreich UND integer sind. Alle
# Ergebnisse landen in einem JSON-Manifest je Lauf.
#
# Der Executor VERWEIGERT den Lauf, wenn die Speicherplatz-Vorabpruefung
# (BackupPlan.ok) fehlgeschlagen ist — halbe/unbrauchbare Kopien bei voller
# Platte werden so verhindert (vorfall-getrieben, 2026-07-01).
#
# Registrierung in der 'backups'-Registry + 'BACKUP_CREATED'-Audit folgt in
# Build 354 (bewusst getrennt).
#
# Beleg: Bauplan B7 v1.1 §11; Datenmigrationsleitfaden v0.2 §4; mc 2026-07-10.
# Build 354: BackupRun um run_ts/host erweitert (fuer die backups-Registrierung).
#
# =============================================================================
# BUILD 625 - DIE AUFBEWAHRUNG DARF NUR BRAUCHBARE GENERATIONEN ZAEHLEN.
# =============================================================================
# Behoben werden zwei Befunde. Der zweite ist beim Messen des ersten
# aufgetaucht und ist der schwerere.
#
# BEFUND 1 (Vorgang 651e6d84, kritisch): _prune gruppierte allein nach dem
#   Namensmuster und sortierte nach dem Zeitstempel. Ob eine Kopie die
#   Integritaetspruefung bestanden hatte, ging NICHT ein. Eine defekte Kopie
#   blieb mit dem aktuellen Zeitstempel liegen, zaehlte als juengste
#   Generation und verdraengte die aelteste gute. Nach retention_count
#   solchen Laeufen war von der betroffenen Datenbank keine brauchbare
#   Sicherung mehr da - bei einem Sicherungsordner, der voll aussieht.
#
# BEFUND 2 (gemessen am 2026-08-01, Vorgang im Eingang): 'PRAGMA
#   integrity_check' ALLEIN ZERTIFIZIERT EINE SICHERUNG NICHT.
#   Der Versuch: eine 87-MB-Quelle, 'VACUUM INTO' mitten im Lauf mit SIGKILL
#   abgebrochen. Ergebnis:
#     * Am Ziel liegt eine Teildatei (42 MB) - MIT dem zaehlenden Namen,
#       daneben ein '-journal'.
#     * Beim ERSTEN Oeffnen rollt SQLite das Journal zurueck; die Datei ist
#       danach 0 Byte gross.
#     * 'PRAGMA integrity_check' auf dieser 0-Byte-Datei liefert 'ok'.
#   Eine leere SQLite-Datei ist formal fehlerfrei. Die bisherige Pruefung
#   haette die Teildatei also als integer BESTAETIGT, und sie waere als
#   vollwertige Generation in die Aufbewahrung eingegangen. Das ist schlimmer
#   als Befund 1: dort stand wenigstens integrity_ok=False im Manifest.
#
#   UNTERSCHEIDBAR ist der Fall an drei Angaben, die alle im Dateikopf oder
#   im Schema stehen und nichts kosten:
#     Quelle              Groesse 91258880  user_version 37  Tabellen 1  page_count 22280
#     Teildatei (0 Byte)  Groesse 0         user_version 0   Tabellen 0  page_count 0
#     vollstaendige Kopie Groesse 91258880  user_version 37  Tabellen 1  page_count 22280
#
# DIE DREI FESTLEGUNGEN, DIE DARAUS FOLGEN:
#
#   1) EINE KOPIE IST ERST BELEGT, WENN SIE DER QUELLE ENTSPRICHT. Geprueft
#      wird jetzt integrity_check UND user_version UND die Zahl der
#      Schemaobjekte UND dass die Kopie nicht leer ist, wenn die Quelle es
#      nicht war. 'VACUUM INTO' erhaelt alle drei Merkmale; eine Abweichung
#      ist deshalb ein Befund und keine Eigenheit.
#
#   2) WAS NICHT BELEGT IST, TRAEGT DEN ZAEHLENDEN NAMEN NICHT MEHR. Die
#      Datei wird nicht geloescht, sondern auf '.defekt' umbenannt - das
#      Namensmuster erfasst sie dann nicht, und sie bleibt als Beleg liegen.
#      Loeschen waere in einem forensischen Verfahren die falsche Antwort:
#      an der Teildatei sieht man, WORAN der Lauf gescheitert ist.
#
#   3) _prune LOESCHT NUR DORT, WO ES ETWAS DAZUGEWONNEN HAT. Ein Label,
#      fuer das dieser Lauf keine belegte Kopie erzeugt hat, wird nicht
#      beschnitten. Aufbewahrung heisst 'die N neuesten behalten' - wer
#      keine hinzufuegt, muss auch keine wegnehmen. Was aus diesem Grund
#      stehen bleibt, steht namentlich im Manifest.
#
#   ZUSAETZLICH prueft _prune jede Datei, die es als Generation ZAEHLEN will,
#   noch einmal billig nach (page_count aus dem Dateikopf, kein Vollscan).
#   Damit faellt auch eine Altlast auf, die vor diesem Build in den Ordner
#   geraten ist - etwa aus einem abgebrochenen Lauf.
#
#   UND: kein stiller Fehlpfad mehr. Ein misslungenes Loeschen oder
#   Umbenennen wurde bisher verschluckt ('pass'); es steht jetzt im Manifest
#   und auf der Konsole.
#
# Version: v0.8.625 - Build: 625 - 2026-08-01
# =============================================================================

import json
import os
import re
import socket
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple

from management.backup.backup_config import BackupConfig
from management.backup.backup_planner import BackupPlan
from management.migration_fleet.harness.backup import BackupTool

#: DER VERMERK ZUR PUNKTGLEICHHEIT (Build 617, Entscheidung mc 2026-07-31).
#:
#: Er steht an EINER Stelle, damit Manifest und Konsole nicht auseinander-
#: laufen. Anlass ist die Nachpruefung aus Build 616: Die Datenbanken werden
#: NACHEINANDER gesichert, jede fuer sich transaktional stimmig - der SATZ
#: als Ganzes ist es nicht. Zwischen zwei Kopien kann der Betrieb einen Fall
#: anlegen oder eine Zuweisung aendern; aus einem solchen Satz
#: wiederhergestellt entstuende ein Zustand, den es nie gegeben hat.
#:
#: mc hat sich am 2026-07-31 fuer die KENNZEICHNUNG entschieden und gegen ein
#: Wartungsfenster: eine taegliche Sicherung soll nebenher laufen koennen.
#: Der Preis ist, dass jeder, der den Satz benutzt, von der Einschraenkung
#: WISSEN muss - und dafuer genuegt es nicht, sie im Vermerk abzulegen. Sie
#: steht deshalb im Manifest UND auf der Konsole, bei jedem Lauf.
PUNKTGLEICH_VERMERK = (
    "NICHT PUNKTGLEICH: Die Datenbanken wurden nacheinander gesichert. Jede "
    "Kopie ist fuer sich transaktional stimmig; der Satz als Ganzes bildet "
    "KEINEN gemeinsamen Zeitpunkt ab. Zwischen zwei Kopien kann der Betrieb "
    "geschrieben haben. Fuer eine Wiederherstellung des GESAMTEN Bestandes "
    "ist ein ruhiger Zustand noetig (keine offenen Schreiber) - sonst kann "
    "ein Zustand entstehen, den es nie gegeben hat. Die Felder "
    "'begonnen_ts' und 'beendet_ts' je Datenbank machen den Versatz "
    "ablesbar."
)

#: Erkennt Backup-Dateinamen der Leitfaden-Konvention
#: '<label>_v<version>_<ts>_<host>.backup.db' fuer die Retention-Gruppierung.
#:
#: DAS MUSTER ENDET AUF '.backup.db' UND IST DAMIT ZUGLEICH DIE SPERRE: eine
#: Datei mit der Endung '.defekt' faellt heraus und zaehlt nicht als
#: Generation. Genau darauf beruht Festlegung 2 (Build 625).
_BACKUP_NAME_RE = re.compile(
    r"^(?P<label>.+)_v\d+_(?P<ts>\d{8}T\d{6}Z)_.+\.backup\.db$")

#: Die Endung, die eine nicht belegte Kopie bekommt. Sie liegt HINTER
#: '.backup.db', damit der urspruengliche Name lesbar bleibt - man soll der
#: Datei ansehen, aus welchem Lauf sie stammt.
DEFEKT_ENDUNG = ".defekt"

#: Erkennt die beiseitegelegten Dateien - fuer ihre eigene Aufbewahrung.
_DEFEKT_NAME_RE = re.compile(
    r"^(?P<label>.+)_v\d+_(?P<ts>\d{8}T\d{6}Z)_.+\.backup\.db"
    + re.escape(DEFEKT_ENDUNG) + r"$")


@dataclass(frozen=True)
class Quellmerkmale:
    """
    Die Merkmale der QUELLE, an denen sich eine Kopie messen lassen muss.

    'VACUUM INTO' erzeugt eine logisch gleiche Datenbank: dieselbe
    user_version, dasselbe Schema. Die Groesse darf abweichen (VACUUM
    verdichtet), die Seitenzahl ebenso - deshalb wird von der Kopie nur
    verlangt, dass sie NICHT LEER ist, wenn die Quelle es nicht war.
    """
    user_version: int
    seiten: int
    schema_objekte: int


@dataclass(frozen=True)
class Aufraeumen:
    """
    Was die Aufbewahrung getan hat - und was sie NICHT getan hat.

    Das zweite Feld ist der eigentliche Gewinn: bis Build 624 gab es nur die
    Liste der geloeschten Dateien. Ob dabei etwas uebersprungen wurde und
    warum, stand nirgends.
    """
    geloescht: List[str] = field(default_factory=list)
    beiseite: List[str] = field(default_factory=list)
    nicht_beschnitten: List[str] = field(default_factory=list)
    fehler: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class BackupItemResult:
    """Ergebnis der Sicherung EINER Datenbank."""
    label: str
    src: str
    backup_path: Optional[str]
    sha512: Optional[str]
    size: int
    user_version: int
    integrity_ok: bool
    error: Optional[str]   # None wenn erfolgreich, sonst Klartext-Grund
    # BUILD 617 — DER ZEITPUNKT JE DATENBANK.
    # Bis Build 616 trug das Manifest nur EINEN Zeitstempel fuer den ganzen
    # Lauf. Damit sah der Sicherungssatz punktgleich aus, ohne es zu sein:
    # die Datenbanken werden nacheinander gesichert, und dazwischen arbeitet
    # der Betrieb weiter. Diese beiden Felder machen den Versatz ABLESBAR.
    # Sie stehen im Manifest, NICHT in der Registry - eine Schemaaenderung an
    # der coordinator.db fiele unter den Migrationsvorbehalt und waere fuer
    # eine Angabe, die ins Manifest gehoert, der falsche Preis.
    begonnen_ts: str = ""
    beendet_ts: str = ""


@dataclass(frozen=True)
class BackupRun:
    """Gesamtergebnis eines Backup-Laufs."""
    ok: bool
    run_ts: str
    host: str
    results: List[BackupItemResult]
    pruned: List[str]
    manifest_path: Optional[str]
    reason: str
    #: Fall-Datenbanken, die WAEHREND des Laufs entstanden sind und deshalb
    #: NICHT gesichert wurden (Build 617). Leer ist der Regelfall.
    nachzuegler: List[str] = field(default_factory=list)
    #: BUILD 625 - Dateien, die den zaehlenden Namen verloren haben, weil
    #: ihre Brauchbarkeit nicht belegt ist. Sie liegen weiter im Ordner,
    #: verdraengen aber keine gute Generation mehr.
    beiseite_gelegt: List[str] = field(default_factory=list)
    #: BUILD 625 - Labels, die nicht beschnitten wurden, weil dieser Lauf
    #: fuer sie keine belegte Kopie erzeugt hat.
    nicht_beschnitten: List[str] = field(default_factory=list)
    #: BUILD 625 - misslungene Loesch- und Umbenennvorgaenge. Bis Build 624
    #: wurden sie verschluckt.
    aufraeum_fehler: List[str] = field(default_factory=list)


class BackupExecutor:
    """
    Fuehrt einen geprueften BackupPlan aus.

    ZUR QUELLE, seit Build 627 genau statt pauschal: Sie wird NUR GELESEN -
    mit EINER Ausnahme, dem optionalen 'wal_checkpoint(PASSIVE)'. Der
    schreibt naturgemaess und ist deshalb die einzige schreibfaehige
    Verbindung im ganzen Sicherungspfad; die Begruendung steht bei
    _checkpoint_passive. Alle uebrigen Zugriffe - Merkmale lesen und
    'VACUUM INTO' - laufen ueber 'file:...?mode=ro'.

    Bis Build 626 stand hier die Pauschale 'Quelle read-only'. Technisch
    verhindert hat sie nichts: die Verbindungen waren schreibfaehig, und die
    Zusage stand allein im Kommentar (Vorgang e9522fe2).
    """

    def __init__(self, backup_cfg: BackupConfig) -> None:
        self._cfg = backup_cfg

    # ------------------------------------------------------------------- run
    def run(self, plan: BackupPlan) -> BackupRun:
        """
        Sichert alle Quellen des Plans. Verweigert, wenn plan.ok False ist
        (Vorabpruefung fehlgeschlagen).
        """
        if not plan.ok:
            return BackupRun(
                ok=False, run_ts="", host=socket.gethostname(),
                results=[], pruned=[], manifest_path=None,
                reason="Vorabpruefung fehlgeschlagen: " + plan.reason)

        run_ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        host = socket.gethostname()

        results = [self._backup_one(src, plan.dest_dir, run_ts, host)
                   for src in plan.sources]

        # --- NACHSCHAU: WAS IST WAEHREND DES LAUFS DAZUGEKOMMEN? (B617) ---
        # Der Planer liest die Fallverzeichnisse EINMAL VOR dem Lauf. Eine
        # Fall-Datenbank, die waehrend des Laufs entsteht, wurde bis Build 616
        # weder gesichert NOCH genannt - sie verschwand still (Grundregel 1).
        # Gesichert wird sie auch jetzt nicht: sie nachtraeglich mitzunehmen
        # machte den Satz noch ungleichzeitiger, und der Lauf haette kein
        # definiertes Ende. Aber sie wird BENANNT, und damit weiss der
        # naechste Lauf bzw. die auswertende Person davon.
        nachzuegler = self._nachzuegler(plan)

        # DIE BILANZ STEHT VOR DEM AUFRAEUMEN (Build 625). Bis Build 624 lief
        # _prune unmittelbar nach dem Sichern und noch vor der Bilanz - es
        # loeschte also, bevor feststand, ob die neue Generation ueberhaupt
        # taugt. Die Reihenfolge war die falsche, und sie hat den Befund
        # 651e6d84 erst wirksam werden lassen.
        overall_ok = all(r.error is None and r.integrity_ok for r in results)

        # NUR LABELS MIT EINER BELEGTEN NEUEN KOPIE WERDEN BESCHNITTEN.
        gute_labels = {r.label for r in results
                       if r.error is None and r.integrity_ok}
        aufraeumen = self._prune(plan.dest_dir, gute_labels)

        manifest_path = self._write_manifest(
            plan.dest_dir, run_ts, host, results, aufraeumen.geloescht,
            overall_ok, nachzuegler, aufraeumen)

        reason = "" if overall_ok else (
            "Mindestens eine DB-Sicherung schlug fehl oder ist nicht integer "
            "(siehe Manifest).")
        if aufraeumen.fehler:
            # Ein misslungenes Aufraeumen macht den Lauf nicht ungueltig - die
            # Sicherungen sind geschrieben. Es darf aber nicht still bleiben:
            # bleibt eine nicht belegte Datei unter dem zaehlenden Namen
            # liegen, ist der Befund von 651e6d84 wieder da.
            reason = (reason + " " if reason else "") + (
                "Aufraeumen unvollstaendig (%d Vorgang/Vorgaenge) - siehe "
                "Manifest." % len(aufraeumen.fehler))
        return BackupRun(ok=overall_ok, run_ts=run_ts, host=host,
                         results=results, pruned=aufraeumen.geloescht,
                         manifest_path=manifest_path, reason=reason,
                         nachzuegler=nachzuegler,
                         beiseite_gelegt=aufraeumen.beiseite,
                         nicht_beschnitten=aufraeumen.nicht_beschnitten,
                         aufraeum_fehler=aufraeumen.fehler)

    # ----------------------------------------------------------- backup_one
    def _backup_one(self, src, dest_dir: str, run_ts: str,
                    host: str) -> BackupItemResult:
        """Eine DB sichern; jeder Fehler wird gefangen und bilanziert."""
        begonnen = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        try:
            if self._cfg.checkpoint == "passive":
                # Nicht-blockierender WAL-Trim; Fehlschlag ist unkritisch, weil
                # VACUUM INTO ohnehin konsistent liest -> nur protokollieren.
                self._checkpoint_passive(src.path)

            merkmale = self._quellmerkmale(src.path)
            uv = merkmale.user_version
            res = BackupTool.create_backup(
                src.path, dest_dir, db_label=src.label, version=uv,
                host=host, ts=run_ts)

            integ_ok, detail = self._kopie_beurteilen(res.path, merkmale)
            pfad = res.path
            fehler = None if integ_ok else detail
            if not integ_ok:
                # BUILD 625: die nicht belegte Kopie verliert den zaehlenden
                # Namen SOFORT - noch bevor _prune ueberhaupt hinsieht. Sie
                # bleibt liegen; an ihr sieht man, woran es gescheitert ist.
                pfad, umbenennfehler = self._beiseite_legen(res.path)
                if umbenennfehler:
                    fehler = "%s | ACHTUNG: %s" % (detail, umbenennfehler)
            return BackupItemResult(
                label=src.label, src=src.path, backup_path=pfad,
                sha512=res.sha512, size=res.size, user_version=uv,
                integrity_ok=integ_ok, error=fehler,
                begonnen_ts=begonnen,
                beendet_ts=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
        except Exception as exc:  # bewusst breit: kein DB darf den Lauf killen
            return BackupItemResult(
                label=src.label, src=src.path, backup_path=None, sha512=None,
                size=0, user_version=0, integrity_ok=False, error=str(exc),
                begonnen_ts=begonnen,
                beendet_ts=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))

    # ------------------------------------------------------------- helpers
    def _checkpoint_passive(self, src_path: str) -> None:
        """
        DIE EINE STELLE, AN DER DIE QUELLE SCHREIBFAEHIG GEOEFFNET WIRD -
        und das ist keine Nachlaessigkeit, sondern die Natur der Sache: ein
        Checkpoint SCHREIBT, er traegt den Inhalt des WAL in die Datenbank
        zurueck. Eine nur-lesende Verbindung koennte ihn nicht ausfuehren.

        GEMESSEN am 2026-08-01: auf einer mit 'mode=ro' geoeffneten
        Verbindung wirft 'PRAGMA wal_checkpoint(PASSIVE)' NICHT, sondern
        liefert (0, 0, 0) - es tut also STILL NICHTS. Ein stiller Nichtlauf
        waere hier das schlechteste Ergebnis: die Sicherung liefe weiter, und
        niemand wuesste, dass der Checkpoint ausgefallen ist. Deshalb bleibt
        die Verbindung hier ausdruecklich schreibfaehig.

        WER DAS NICHT WILL, setzt 'backup.checkpoint' auf etwas anderes als
        'passive' - dann wird die Quelle im ganzen Lauf nur gelesen. Die
        Sicherung selbst braucht den Checkpoint nicht: 'VACUUM INTO' liest
        ohnehin konsistent ueber das WAL hinweg.
        """
        con = sqlite3.connect(src_path)
        try:
            con.isolation_level = None
            con.execute("PRAGMA wal_checkpoint(PASSIVE)")
        finally:
            con.close()

    def _user_version(self, src_path: str) -> int:
        con = sqlite3.connect("file:%s?mode=ro" % src_path, uri=True)
        try:
            row = con.execute("PRAGMA user_version").fetchone()
            return int(row[0]) if row else 0
        finally:
            con.close()

    def _quellmerkmale(self, src_path: str) -> Quellmerkmale:
        """
        Die Merkmale der Quelle, an denen die Kopie gemessen wird.

        ALLE DREI IN EINER VERBINDUNG. Waeren es drei Verbindungen, koennten
        sie drei verschiedene Zustaende sehen - bei einer Quelle, in die der
        Betrieb weiterschreibt, ist das kein Randfall.

        DER RESTLICHE ZEITVERSATZ BLEIBT: zwischen diesem Lesen und dem
        'VACUUM INTO' kann der Betrieb das Schema aendern. Das ist ein
        seltener Fall, und er faellt auf die SICHERE Seite - gemeldet wuerde
        eine Sicherung, die nicht belegt ist, obwohl sie es waere. Ein
        Fehlalarm bei einer Sicherung kostet eine Nachschau; die Gegenrichtung
        kostet die Sicherung.
        """
        con = sqlite3.connect("file:%s?mode=ro" % src_path, uri=True)
        try:
            uv = int(con.execute("PRAGMA user_version").fetchone()[0])
            seiten = int(con.execute("PRAGMA page_count").fetchone()[0])
            objekte = int(con.execute(
                "SELECT count(*) FROM sqlite_master").fetchone()[0])
        finally:
            con.close()
        return Quellmerkmale(user_version=uv, seiten=seiten,
                             schema_objekte=objekte)

    def _kopie_beurteilen(self, backup_path: str,
                          quelle: Quellmerkmale) -> Tuple[bool, str]:
        """
        Ist diese Kopie als Sicherung BELEGT?

        WARUM 'PRAGMA integrity_check' ALLEIN NICHT GENUEGT - gemessen am
        2026-08-01, die Zahlen stehen im Kopf dieser Datei: Eine
        abgebrochene 'VACUUM INTO' hinterlaesst eine Teildatei mit Journal;
        beim ersten Oeffnen rollt SQLite zurueck, die Datei ist danach 0 Byte
        gross - und 'integrity_check' meldet darauf 'ok'. Eine leere
        SQLite-Datei ist formal fehlerfrei. Die Pruefung haette das Nichts
        also bestaetigt.

        Geprueft wird deshalb gegen die QUELLE. 'VACUUM INTO' erhaelt
        user_version und Schema; die Groesse und die Seitenzahl duerfen
        abweichen, weil VACUUM verdichtet. Verlangt wird darum:
          * integrity_check meldet 'ok',
          * die Kopie ist nicht leer, wenn die Quelle es nicht war,
          * user_version stimmt ueberein,
          * die Zahl der Schemaobjekte stimmt ueberein.
        """
        try:
            # BUILD 627: auch die KOPIE wird nur-lesend angesehen. Sie ist
            # gerade erst entstanden, ein heisses Journal ist hier also nicht
            # zu erwarten - aber die Regel soll ohne Ausnahmen auskommen:
            # in diesem Modul oeffnet nichts schreibfaehig ausser dem
            # Checkpoint. Eine Regel mit zwei Ausnahmen prueft niemand nach.
            con = sqlite3.connect("file:%s?mode=ro" % backup_path, uri=True)
            try:
                rows = con.execute("PRAGMA integrity_check").fetchall()
                seiten = int(con.execute("PRAGMA page_count").fetchone()[0])
                uv = int(con.execute("PRAGMA user_version").fetchone()[0])
                objekte = int(con.execute(
                    "SELECT count(*) FROM sqlite_master").fetchone()[0])
            finally:
                con.close()
        except sqlite3.Error as exc:
            return False, "Kopie nicht lesbar: %s" % exc

        if not (len(rows) == 1 and rows[0][0] == "ok"):
            return False, "integrity_check: " + "; ".join(
                str(r[0]) for r in rows[:5])
        if quelle.seiten > 0 and seiten == 0:
            return False, (
                "Die Kopie ist LEER (0 Seiten), die Quelle hatte %d. "
                "'integrity_check' meldet auf einer leeren Datei 'ok' - das "
                "ist der Fall einer abgebrochenen Sicherung."
                % quelle.seiten)
        if uv != quelle.user_version:
            return False, (
                "user_version weicht ab: Kopie %d, Quelle %d. 'VACUUM INTO' "
                "erhaelt sie - eine Abweichung heisst, dass die Kopie nicht "
                "diese Quelle in diesem Stand abbildet."
                % (uv, quelle.user_version))
        if objekte != quelle.schema_objekte:
            return False, (
                "Schema unvollstaendig: Kopie %d Objekte, Quelle %d."
                % (objekte, quelle.schema_objekte))
        return True, "ok"

    # ------------------------------------------------------- beiseite legen
    def _beiseite_legen(self, pfad: str) -> Tuple[str, Optional[str]]:
        """
        Nimmt einer nicht belegten Datei den zaehlenden Namen.

        NICHT LOESCHEN, SONDERN UMBENENNEN. In einem forensischen Verfahren
        ist die Teildatei ein Beleg: an ihr sieht man, woran der Lauf
        gescheitert ist - Platte voll, Abbruch, defekte Quelle. Eine
        geloeschte Datei beantwortet keine Frage mehr.

        Gibt (neuer_pfad, fehler) zurueck. Schlaegt das Umbenennen fehl,
        bleibt der alte Pfad stehen UND der Fehler wird benannt: dann liegt
        eine nicht belegte Datei weiter unter dem zaehlenden Namen, und genau
        das ist der Zustand, den dieser Build verhindern soll.
        """
        ziel = pfad + DEFEKT_ENDUNG
        # Zwei Laeufe in derselben Sekunde koennten denselben Namen treffen.
        n = 1
        while os.path.exists(ziel):
            ziel = "%s%s.%d" % (pfad, DEFEKT_ENDUNG, n)
            n += 1
        try:
            os.replace(pfad, ziel)
        except OSError as exc:
            return pfad, (
                "Die nicht belegte Kopie '%s' konnte nicht beiseitegelegt "
                "werden (%s). SIE TRAEGT WEITER DEN ZAEHLENDEN NAMEN und "
                "kann eine gute Generation verdraengen - von Hand entfernen."
                % (os.path.basename(pfad), exc))
        # Das Journal einer abgebrochenen Sicherung gehoert mit zur Seite -
        # sonst wendet SQLite es auf die naechste gleichnamige Datei an.
        for anhang in ("-journal", "-wal", "-shm"):
            neben = pfad + anhang
            if os.path.exists(neben):
                try:
                    os.replace(neben, ziel + anhang)
                except OSError:
                    pass          # der Hauptbefund steht bereits fest
        return ziel, None

    def _traegt_inhalt(self, pfad: str) -> Tuple[bool, str]:
        """
        Billige Nachschau vor dem Zaehlen: hat diese Datei ueberhaupt Inhalt?

        'PRAGMA page_count' liest den Dateikopf, keinen Vollscan - das ist
        auch bei einer mehrere Gigabyte grossen Sicherung eine Sache von
        Millisekunden. Damit faellt auch eine ALTLAST auf, die vor Build 625
        in den Ordner geraten ist.

        ZWEI VORSICHTSMASSNAHMEN, beide am 2026-08-01 gemessen und beide
        noetig, weil das blosse ANSEHEN einer Datei sie sonst veraendert:

        1) EIN HEISSES JOURNAL WIRD NICHT ANGEFASST. Liegt neben der Datei
           ein '-journal' oder '-wal', dann ist der Schreibvorgang
           abgebrochen worden. Oeffnet man sie jetzt gewoehnlich, SPIELT
           SQLITE DAS JOURNAL ZURUECK - aus 34 MB Teildatei werden 0 Byte,
           und der Beleg, an dem man den Umfang des Abbruchs abgelesen
           haette, ist weg. Das Journal IST hier der Befund; die Datei muss
           dafuer gar nicht geoeffnet werden.

        2) GEOEFFNET WIRD NUR-LESEND ('mode=ro'). Damit kann diese Nachschau
           unter keinen Umstaenden etwas schreiben. Gemessen: auf einer
           Datei mit heissem Journal antwortet SQLite dann 'attempt to write
           a readonly database' und LAESST DIE DATEI IN RUHE - genau das
           gewuenschte Verhalten.
        """
        try:
            if os.path.getsize(pfad) == 0:
                return False, "0 Byte"
        except OSError as exc:
            return False, "nicht lesbar: %s" % exc

        heiss = [a for a in ("-journal", "-wal") if os.path.exists(pfad + a)]
        if heiss:
            return False, ("abgebrochene Sicherung - heisses Journal (%s) "
                           "liegt daneben; die Datei wurde NICHT geoeffnet, "
                           "damit der Beleg erhalten bleibt"
                           % ", ".join(heiss))

        try:
            con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
            try:
                seiten = int(con.execute("PRAGMA page_count").fetchone()[0])
            finally:
                con.close()
        except (OSError, sqlite3.Error) as exc:
            return False, "nicht lesbar: %s" % exc
        if seiten == 0:
            return False, "0 Seiten"
        return True, "ok"

    # -------------------------------------------------------------- prune
    def _prune(self, dest_dir: str,
               gute_labels: Optional[set] = None) -> Aufraeumen:
        """
        Behaelt je DB-Label die retention_count neuesten BRAUCHBAREN
        Generationen und loescht aeltere. Nur Dateien der Namenskonvention
        werden beruecksichtigt; alles andere bleibt unangetastet.

        DREI UNTERSCHIEDE ZU BUILD 624 - alle drei sind die Antwort auf den
        Vorgang 651e6d84:

        1) GEZAEHLT WIRD NUR, WAS INHALT HAT. Jede Datei, die als Generation
           zaehlen soll, wird billig nachgesehen (_traegt_inhalt). Eine leere
           oder unlesbare Datei wird beiseitegelegt statt gezaehlt - sonst
           verdraengt das Nichts eine brauchbare Sicherung.

        2) BESCHNITTEN WIRD NUR, WO ETWAS DAZUGEKOMMEN IST. 'gute_labels'
           sind die Labels, fuer die DIESER Lauf eine belegte Kopie erzeugt
           hat. Fuer alle anderen bleibt der Bestand, wie er ist:
           Aufbewahrung heisst 'die N neuesten behalten' - wer keine
           hinzufuegt, muss auch keine wegnehmen. Nebenwirkung, und eine
           erwuenschte: die Sicherungen eines geloeschten Falls verschwinden
           nicht mehr nach und nach von selbst. Sie stehen dafuer namentlich
           im Manifest.
           gute_labels=None heisst 'alle' - fuer den Direktaufruf in Tests.

        3) KEIN STILLER FEHLPFAD. Ein misslungenes Loeschen wurde bisher
           verschluckt ('pass'). Es steht jetzt in Aufraeumen.fehler.

        Die beiseitegelegten Dateien haben eine EIGENE Aufbewahrung, ebenfalls
        retention_count. Ohne sie wuechse der Ordner unbegrenzt, und die
        Platzvorabpruefung wuerde irgendwann jeden weiteren Lauf verweigern -
        aus dem Verlust einzelner Generationen wuerde der Verlust der
        Sicherung ueberhaupt.
        """
        erg = Aufraeumen()
        try:
            names = os.listdir(dest_dir)
        except OSError as exc:
            erg.fehler.append("Sicherungsverzeichnis nicht lesbar: %s" % exc)
            return erg

        # --- 1) Kandidaten sammeln und auf Inhalt nachsehen -----------------
        gruppen = {}
        for name in sorted(names):
            m = _BACKUP_NAME_RE.match(name)
            if not m:
                continue
            pfad = os.path.join(dest_dir, name)
            hat_inhalt, grund = self._traegt_inhalt(pfad)
            if not hat_inhalt:
                neu, fehler = self._beiseite_legen(pfad)
                if fehler:
                    erg.fehler.append(fehler)
                else:
                    erg.beiseite.append("%s (%s)" % (neu, grund))
                continue
            gruppen.setdefault(m.group("label"), []).append(
                (m.group("ts"), name))

        # --- 2) je Label beschneiden, aber nur wo dazugewonnen wurde --------
        for label, items in sorted(gruppen.items()):
            if gute_labels is not None and label not in gute_labels:
                if len(items) > self._cfg.retention_count:
                    erg.nicht_beschnitten.append(
                        "%s (%d Generationen, kein belegter Lauf in diesem "
                        "Durchgang)" % (label, len(items)))
                continue
            items.sort(reverse=True)              # neueste zuerst
            for _ts, name in items[self._cfg.retention_count:]:
                self._loeschen(os.path.join(dest_dir, name), erg)

        # --- 3) auch die beiseitegelegten Dateien bleiben begrenzt ----------
        self._defekte_begrenzen(dest_dir, erg)
        return erg

    def _loeschen(self, pfad: str, erg: Aufraeumen) -> None:
        try:
            os.remove(pfad)
            erg.geloescht.append(pfad)
        except OSError as exc:
            erg.fehler.append(
                "'%s' konnte nicht geloescht werden: %s"
                % (os.path.basename(pfad), exc))

    def _defekte_begrenzen(self, dest_dir: str, erg: Aufraeumen) -> None:
        """
        Auch von den beiseitegelegten Dateien bleiben je Label nur die
        retention_count neuesten.

        DAS IST EINE ABWAEGUNG UND KEINE SELBSTVERSTAENDLICHKEIT: eine
        Teildatei ist ein Beleg, und Belege loescht man nicht gern. Aber sie
        kann Gigabyte gross sein, und ein unbegrenzt wachsender
        Sicherungsordner laesst die Platzvorabpruefung irgendwann JEDEN Lauf
        verweigern. Dann waere aus dem Verlust einzelner Generationen der
        Verlust der Sicherung ueberhaupt geworden. Mehr als retention_count
        Fehlschlaege desselben Labels sagen zudem dasselbe wie die neuesten:
        das Problem ist dauerhaft.
        """
        try:
            names = sorted(os.listdir(dest_dir))
        except OSError:
            return                      # in _prune bereits gemeldet
        gruppen = {}
        for name in names:
            m = _DEFEKT_NAME_RE.match(name)
            if m:
                gruppen.setdefault(m.group("label"), []).append(
                    (m.group("ts"), name))
        for _label, items in sorted(gruppen.items()):
            items.sort(reverse=True)
            for _ts, name in items[self._cfg.retention_count:]:
                self._loeschen(os.path.join(dest_dir, name), erg)

    # ----------------------------------------------------------- manifest
    def _nachzuegler(self, plan: BackupPlan) -> List[str]:
        """
        Fall-Datenbanken, die WAEHREND des Laufs entstanden sind.

        VORHER GEGEN NACHHER, und nicht 'gesichert gegen nicht gesichert'.
        Verglichen wird die Bestandsaufnahme des Planers (plan.vorgefunden)
        mit dem, was jetzt in den Fall-Verzeichnissen liegt. Ein Pfad zaehlt
        genau dann, wenn er nachher da ist und vorher nicht war - also genau
        das, was der Feldname 'nicht_gesichert_weil_neu' verspricht.

        BUILD 721 - WARUM DAS UMGEBAUT WURDE (Vorgang dc63928d, dritte
        Forderung). Die erste Fassung aus Build 617 leitete die zu
        durchsuchenden Verzeichnisse aus plan.sources ab und hielt fuer 'neu',
        was nicht gesichert worden war. Beides war falsch, und beides ist am
        14.08.2026 an einem echten Lauf gemessen worden:

          LAGE C - DER ECHTE FUND BLIEB AUS. War ein Fall-Verzeichnis beim
          Planen LEER, steuerte es keine Quelle bei und kam in der
          Verzeichnismenge gar nicht vor. Eine waehrend des Laufs dort
          entstandene evidence_4711.db wurde weder gesichert noch genannt -
          also genau der stille Verlust, den dieser Vorgang schliessen
          sollte, und zwar ausgerechnet beim ERSTEN Fall eines
          Verzeichnisses.

          LAGEN A UND B - DAFUER MELDETE SIE FALSCHES. Weil auch das
          Verzeichnis der coordinator.db durchsucht wurde und 'neu' hiess
          'nicht gesichert', erschien dort jede nicht gesicherte Datenbank
          als Nachzuegler: approved_reports.db bei JEDEM Lauf, und bei
          'include_shared_dbs: false' zusaetzlich default.db, templates.db
          und translations.db. Vier Falschmeldungen je Lauf. Eine Liste, die
          immer etwas meldet, liest nach der dritten Woche niemand mehr - der
          Beleg waere dann wieder still, nur auf dem umgekehrten Weg.

        GESUCHT WIRD NUR IN DEN FALL-VERZEICHNISSEN (plan.fall_verzeichnisse,
        aus der Konfiguration). Die geteilten Datenbanken neben der
        coordinator.db entstehen nicht 'waehrend eines Laufs'; ob sie
        mitgesichert werden, entscheidet 'backup.include_shared_dbs' und
        nicht der Zufall eines Verzeichnisinhalts.

        OHNE BESTANDSAUFNAHME KEINE AUSSAGE: Traegt der Plan keine
        Fall-Verzeichnisse - etwa weil er von Hand gebaut wurde -, ist die
        Liste leer. Das ist richtig so und keine Luecke: eine Aussage ueber
        'neu' setzt einen Vorher-Stand voraus. Wo keiner erhoben wurde, ist
        nichts festzustellen, und das Manifest behauptet dann auch nichts.

        Ein Fehler bei der Nachschau darf den Lauf nicht umwerfen - die
        Sicherungen sind zu diesem Zeitpunkt bereits geschrieben.
        """
        vorher = {os.path.abspath(p) for p in (plan.vorgefunden or ())}
        neu: List[str] = []
        for d in sorted(set(plan.fall_verzeichnisse or ())):
            try:
                namen = sorted(os.listdir(d))
            except OSError:
                # Das Verzeichnis war beim Planen lesbar und ist es jetzt
                # nicht mehr. Das ist ein Befund - aber keiner ueber
                # Nachzuegler, und hier waere er am falschen Ort. Der Lauf
                # selbst hat es gemerkt: die Quellen daraus stehen mit
                # 'error' in den Ergebnissen.
                continue
            for name in namen:
                if not name.endswith(".db"):
                    continue
                voll = os.path.abspath(os.path.join(d, name))
                if voll not in vorher and os.path.isfile(voll):
                    neu.append(voll)
        return neu

    def _write_manifest(self, dest_dir: str, run_ts: str, host: str,
                        results: List[BackupItemResult], pruned: List[str],
                        overall_ok: bool,
                        nachzuegler: Optional[List[str]] = None,
                        aufraeumen: Optional[Aufraeumen] = None
                        ) -> Optional[str]:
        """Schreibt ein JSON-Manifest des Laufs (ASCII-only)."""
        # DIE SPANNE DES SATZES: vom Beginn der ersten bis zum Ende der
        # letzten Kopie. Wer den Satz spaeter beurteilt, sieht damit auf einen
        # Blick, ueber welchen Zeitraum er sich erstreckt.
        stempel = [r.begonnen_ts for r in results if r.begonnen_ts]
        stempel += [r.beendet_ts for r in results if r.beendet_ts]
        manifest = {
            "run_ts": run_ts,
            "host": host,
            "ok": overall_ok,
            "punktgleich": False,
            "punktgleich_hinweis": PUNKTGLEICH_VERMERK,
            "satz_von": min(stempel) if stempel else run_ts,
            "satz_bis": max(stempel) if stempel else run_ts,
            "config": {
                "dest_dir": self._cfg.dest_dir,
                "retention_count": self._cfg.retention_count,
                "min_free_factor": self._cfg.min_free_factor,
                "checkpoint": self._cfg.checkpoint,
                "include_shared_dbs": self._cfg.include_shared_dbs,
            },
            "results": [asdict(r) for r in results],
            "pruned": pruned,
            # Waehrend des Laufs entstanden und deshalb NICHT gesichert.
            # Leer ist der Regelfall; steht hier etwas, fehlt es im Satz.
            "nicht_gesichert_weil_neu": list(nachzuegler or []),
            # BUILD 625 - die Aufbewahrung legt Rechenschaft ab. Bis Build 624
            # stand hier nur, was geloescht wurde; was uebersprungen wurde und
            # warum, stand nirgends.
            "beiseite_gelegt": list(aufraeumen.beiseite if aufraeumen else []),
            "nicht_beschnitten": list(
                aufraeumen.nicht_beschnitten if aufraeumen else []),
            "aufraeum_fehler": list(aufraeumen.fehler if aufraeumen else []),
            "aufbewahrung_hinweis": (
                "Als Generation zaehlt nur eine Datei mit Inhalt, deren "
                "Sicherung gegen die Quelle belegt ist (integrity_check, "
                "user_version, Schemaumfang, nicht leer). Was das nicht "
                "erfuellt, traegt die Endung '%s' und verdraengt nichts. "
                "Beschnitten wird nur ein Label, fuer das dieser Lauf eine "
                "belegte Kopie erzeugt hat." % DEFEKT_ENDUNG),
        }
        path = os.path.join(
            dest_dir, "manifest_%s_%s.json" % (run_ts, host))
        try:
            with open(path, "w", encoding="ascii") as fh:
                json.dump(manifest, fh, ensure_ascii=True, indent=2)
            return path
        except OSError:
            return None
