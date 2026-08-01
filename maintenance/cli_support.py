# =============================================================================
# maintenance/cli_support.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 438, Werkzeuge)
# =============================================================================
# Zweck:
#   Gemeinsame, reine Helfer fuer die Wartungs-Werkzeuge (tools/maintenance.py,
#   tools/maintenance_kill.py). Bewusst OHNE Config-/Server-Kopplung, damit sie
#   vollstaendig testbar bleiben.
#
# Enthaelt:
#   * ziel_zu_pfad / ziel_pfade — bildet Fenster-Ziele ('coordinator',
#     'evidence:1488', 'all') auf konkrete DB-Dateien ab.
#   * exklusiv_pruefen — DER Beweis der Ruhigstellung: Versuch, einen
#     EXCLUSIVE-Lock auf die Ziel-DB zu erhalten (Messen, nicht rechnen). Gelingt
#     das, haelt niemand mehr eine Sperre.
#   * quiesce_status — klassifiziert die lebenden Server anhand Praesenz + ACK.
#   * pruefe_wartungsberechtigung — RBAC-Vorpruefung ueber coordinator.db.
#
# Aenderung Build 638 (Ticket 15429c75):
#   pruefe_wartungsberechtigung nimmt jetzt zusaetzlich 'coordinator_db' als
#   VOLLSTAENDIGEN Pfad entgegen. Bis Build 637 kannte der Helfer nur das
#   Datenverzeichnis und haengte den festen Namen 'coordinator.db' an — ein
#   per --coordinator-db uebergebener abweichender DATEINAME ging damit
#   verloren. Die Config-Kopplung selbst bleibt draussen (siehe oben); sie
#   wohnt in maintenance/cli_config.py.
#
# Version: v0.8.638 · Build: 638 · 2026-08-01
# =============================================================================

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from maintenance.ack_file import AckFile
from maintenance.atomic_io import jetzt_epoch
from maintenance.paths import MaintenancePaths
from maintenance.exklusiv_befund import (BELEGT, NICHT_MESSBAR,
                                         RUHIG, ExklusivBefund)
from maintenance.presence_beacon import PresenceBeacon

# Nutzerspezifische DBs liegen in Unterverzeichnissen; geteilte DBs top-level.
_UNTERVERZEICHNIS = {"evidence": "evidence", "forensic": "forensic",
                     "assets": "assets"}


def ziel_zu_pfad(data_dir, token: str) -> Optional[Path]:
    """
    Bildet ein Fenster-Ziel auf eine DB-Datei ab.
      'coordinator'   -> data_dir/coordinator.db
      'evidence:1488' -> data_dir/evidence/evidence_1488.db
      'templates'     -> data_dir/templates.db
    'all' wird hier NICHT aufgeloest (siehe ziel_pfade).
    """
    data_dir = Path(data_dir)
    token = str(token)
    if token == "all":
        return None
    if ":" in token:
        name, uid = token.split(":", 1)
        sub = _UNTERVERZEICHNIS.get(name)
        fname = f"{name}_{uid}.db"
        return (data_dir / sub / fname) if sub else (data_dir / fname)
    return data_dir / f"{token}.db"


def ziel_pfade(data_dir, ziel) -> list:
    """
    Liefert die konkreten DB-Pfade fuer eine Ziel-Liste. 'all' wird auf die
    geteilten Top-Level-DBs (data_dir/*.db) abgebildet — die per-Nutzer-DBs in
    Unterverzeichnissen werden bei 'all' bewusst NICHT einzeln gesperrt.
    """
    data_dir = Path(data_dir)
    if "all" in ziel:
        return sorted(data_dir.glob("*.db"))
    pfade = []
    for token in ziel:
        p = ziel_zu_pfad(data_dir, token)
        if p is not None:
            pfade.append(p)
    return pfade


def _warum_unmessbar(p: Path) -> str:
    """
    Warum ein GELUNGENES 'BEGIN EXCLUSIVE' hier nichts beweist - oder "".

    Gefragt wird das Betriebssystem (os.access) und nicht der Dateimodus:
    Eigentuemerschaft, Gruppen und ACLs entscheiden mit, und root darf
    ohnehin. Das Verzeichnis zaehlt mit, weil SQLite fuer das
    Rollback-Journal dort eine Datei anlegen muss.
    """
    if not os.access(str(p), os.W_OK):
        return ("kein Schreibrecht an der Datei — SQLite oeffnet sie dann nur "
                "lesend, und eine nur lesende Verbindung nimmt beim "
                "'BEGIN EXCLUSIVE' gar keine Sperre. Der Befehl gelingt hier "
                "folgenlos und beweist NICHTS. Abhilfe: die Probe unter dem "
                "Konto fahren, dem die Datei gehoert, oder die Versiegelung "
                "fuer die Dauer der Wartung aufheben.")
    if not os.access(str(p.parent), os.W_OK):
        return ("kein Schreibrecht am Verzeichnis '%s' — SQLite kann dort das "
                "Rollback-Journal nicht anlegen. Auch hier ist ein gelungenes "
                "'BEGIN EXCLUSIVE' kein Nachweis." % p.parent)
    return ""


def exklusiv_beurteilen(db_path, timeout_s: float = 2.0) -> ExklusivBefund:
    """
    DIE SPERRPROBE - mit drei Ergebnissen statt zwei (NEU Build 648).

    Sie ist der Nachweis der Ruhigstellung: "Die Bestaetigung allein ist nicht
    der Beweis - der Exklusiv-Lock-Erwerb ist es."

    ============================================================================
    VORGANG 96f2b18f - WARUM DIESE FUNKTION UMGEBAUT WERDEN MUSSTE
    ============================================================================
    Bis Build 647 kannte sie zwei Ausgaenge: erhalten oder gesperrt. Ein
    dritter Fall wurde dabei dem ERSTEN zugeschlagen, obwohl er das Gegenteil
    bedeutet - der Fall, in dem gar nicht gemessen werden konnte.

    Kann der ausfuehrende Prozess die Datei nicht BESCHREIBEN, oeffnet SQLite
    sie still nur lesend. Eine nur lesende Verbindung nimmt beim
    'BEGIN EXCLUSIVE' UEBERHAUPT KEINE SPERRE; der Befehl gelingt folgenlos,
    und die Funktion meldete 'exklusiv erhalten'.

    GEMESSEN AM 2026-08-01 (Container, SQLite 3.45.1, Journalmodus 'delete',
    als Fremdbenutzer 'nobody', KEIN Halter auf der Datei):
        Datei 0444 (versiegelt)          -> (True, 'exklusiv erhalten')
        Datei 0644 (voellig gewoehnlich) -> (True, 'exklusiv erhalten')
    Beide Male hat niemand die Datei gehalten, und beide Male war die Meldung
    unverdient.

    DAMIT IST DER MANGEL BREITER ALS GEMELDET. Der Vorgang nannte die
    versiegelten forensic_<uid>.db. Entscheidend ist aber nicht die
    Versiegelung, sondern das SCHREIBRECHT DES MESSENDEN PROZESSES. Auf einem
    geteilten Laufwerk, auf dem der Dienst unter einem anderen Konto laeuft
    als die Wartung, ist das der Normalfall.

    ZWEI GEGENPROBEN, ebenfalls gemessen, weil sie den Mangel eingrenzen:
      * Haelt ein SCHREIBER eine EXCLUSIVE-Sperre, meldet die Probe auch ohne
        Schreibrecht 'belegt' - eine EXCLUSIVE-Sperre blockiert schon das
        Lesen. Dieser Fall war nie blind.
      * Haelt ein LESER eine SHARED-Sperre, bleibt er unbemerkt: eine nur
        lesende Verbindung stoert ihn nicht. Ausgerechnet der HAEUFIGSTE Fall
        - jemand liest noch - war der uebersehene.

    WIE 'nicht messbar' FESTGESTELLT WIRD: ERST wird gemessen, DANN wird nur
    dem ERFOLG misstraut. 'Gesperrt' ist eine Messung und bleibt eine - auch
    ohne Schreibrecht. Nur ein gelungenes 'BEGIN EXCLUSIVE' wird gegen das
    Schreibrecht an Datei und Verzeichnis gehalten (siehe _warum_unmessbar).

    Die erste Fassung hat das Recht VOR der Messung geprueft und dabei die
    echte Auskunft 'jemand haelt sie' weggeworfen. Aufgefallen ist das an der
    eigenen Gegenprobe SP05, nicht im Betrieb.

    Returns:
        ExklusivBefund mit zustand RUHIG | BELEGT | NICHT_MESSBAR.
    """
    p = Path(db_path)
    if not p.exists():
        return ExklusivBefund(str(p), RUHIG,
                              "Datei nicht vorhanden — nichts zu sperren")

    # =====================================================================
    # ERST MESSEN, DANN DEM ERGEBNIS MISSTRAUEN - und zwar NUR dem Erfolg.
    #
    # Die erste Fassung dieser Behebung hat das Schreibrecht VOR der Messung
    # geprueft und bei fehlendem Recht sofort 'nicht messbar' gemeldet. Das
    # war zu grob, und die eigene Gegenprobe SP05 hat es gezeigt: Haelt ein
    # SCHREIBER eine EXCLUSIVE-Sperre, dann erfaehrt man das AUCH ohne
    # Schreibrecht - eine EXCLUSIVE-Sperre blockiert schon das Lesen. Die
    # Vorabpruefung hat diese echte Auskunft weggeworfen und durch ein
    # 'weiss nicht' ersetzt.
    #
    # MISSTRAUEN GEHOERT NUR DEM ERFOLGSFALL: 'gesperrt' ist eine Messung
    # und bleibt eine. Nur ein GELUNGENES 'BEGIN EXCLUSIVE' ist zu
    # hinterfragen - denn genau das gelingt auf einer nur lesend geoeffneten
    # Datei folgenlos.
    # =====================================================================
    con = None
    try:
        con = sqlite3.connect(str(p), timeout=timeout_s)
        con.execute("BEGIN EXCLUSIVE")
        con.execute("ROLLBACK")
        unmessbar = _warum_unmessbar(p)
        if unmessbar:
            return ExklusivBefund(str(p), NICHT_MESSBAR, unmessbar)
        return ExklusivBefund(str(p), RUHIG, "exklusiv erhalten")
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "locked" in msg or "busy" in msg:
            return ExklusivBefund(str(p), BELEGT,
                                  "database is locked — noch von jemandem gehalten")
        if "readonly" in msg or "read-only" in msg:
            # Wir haben oben Schreibrecht festgestellt und bekommen trotzdem
            # 'readonly' - dann liegt es an etwas anderem (Dateisystem nur
            # lesend eingehaengt, Netzlaufwerk). Das ist KEINE Ruhe.
            return ExklusivBefund(
                str(p), NICHT_MESSBAR,
                "SQLite meldet 'readonly', obwohl das Betriebssystem "
                "Schreibrecht ausweist (%s). Moeglich bei nur lesend "
                "eingehaengten Dateisystemen oder Netzlaufwerken. Nicht "
                "gemessen — und damit kein Nachweis." % exc)
        return ExklusivBefund(str(p), NICHT_MESSBAR,
                              "nicht pruefbar: %s" % exc)
    except sqlite3.Error as exc:
        return ExklusivBefund(str(p), NICHT_MESSBAR,
                              "nicht pruefbar: %s" % exc)
    finally:
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass


def exklusiv_pruefen(db_path, timeout_s: float = 2.0) -> tuple:
    """
    Die alte, zweiwertige Form '(ok, grund)' — sie bleibt fuer Aufrufer, die
    die Dreiwertigkeit nicht auswerten.

    ACHTUNG, DAS VERHALTEN HAT SICH GEAENDERT (Build 648): 'nicht messbar'
    liefert hier jetzt False. Das ist die sichere Seite und der Kern der
    Behebung von 96f2b18f - lieber ein 'nicht frei' zu viel als eine Ruhe,
    die nie gemessen wurde. Wer die drei Zustaende unterscheiden will, ruft
    exklusiv_beurteilen().
    """
    return exklusiv_beurteilen(db_path, timeout_s).als_tupel()


def quiesce_status(paths: MaintenancePaths, window_id: str, stale_s: int,
                   jetzt: Optional[int] = None) -> dict:
    """
    Klassifiziert alle lebenden Server anhand Praesenz + ACK des Fensters:
      gequiesct : hat eine ACK zu diesem Fenster geschrieben
      offen     : lebt (frisches Beacon), aber noch KEINE ACK
      tot       : Beacon veraltet -> vermutlich tot, unbestaetigt (GR1)
    'fehler' sammelt kaputte Steuerdateien (werden gemeldet, nicht still).
    """
    fehler: list = []
    beacons = PresenceBeacon.alle_laden(paths, fehler=fehler)
    ack_keys = {(a.host, a.pid, a.role)
                for a in AckFile.fuer_fenster(paths, window_id, fehler=fehler)}
    now = jetzt if jetzt is not None else jetzt_epoch()

    gequiesct, offen, tot = [], [], []
    for b in beacons:
        key = (b.host, b.pid, b.role)
        if key in ack_keys:
            gequiesct.append(b)
        elif b.ist_veraltet(stale_s, now):
            tot.append(b)
        else:
            offen.append(b)
    return {"gequiesct": gequiesct, "offen": offen, "tot": tot, "fehler": fehler}


def pruefe_wartungsberechtigung(data_dir, recovery: bool,
                                *, os_user: Optional[str] = None,
                                coordinator_db=None) -> tuple:
    """
    Prueft, ob der ausfuehrende OS-Benutzer die Faehigkeit 'wartung.durchfuehren'
    besitzt (RBAC ueber coordinator.db). Rueckgabe (ok, meldung):

      DB lesbar + berechtigt        -> (True,  "erlaubt: <user>")
      DB lesbar + NICHT berechtigt  -> (False, "verweigert: <user> ...")
      DB nicht lesbar / Fehler:
        recovery=False (enter)      -> (False, ... abgebrochen)   [fail-safe]
        recovery=True  (exit/kill)  -> (True,  ... nicht blockiert) [Recovery]

    Der Henne-Ei-Fall (coordinator.db gerade gesperrt) blockiert also NUR das
    Setzen eines Fensters (enter), nie die Wiederherstellung (exit/kill).

    coordinator_db (NEU Build 638, Ticket 15429c75):
        Der VOLLSTAENDIGE Pfad zur coordinator.db, Dateiname eingeschlossen.
        Ist er gesetzt, wird er unveraendert verwendet.

        WARUM DAS NOETIG WAR: Zuvor kannte dieser Helfer nur das
        Datenverzeichnis und setzte darauf den festen Namen 'coordinator.db'.
        Wer die Datei anders benannte (etwa 'coordinator_2.db', beim
        Parallelbetrieb zweier Bestaende der Normalfall), bekam eine Meldung
        ueber eine Datei, die er nie genannt hatte — und keinen Hinweis
        darauf, dass sein Argument unterwegs verlorengegangen war.

        None haelt das bisherige Verhalten (data_dir/coordinator.db) und damit
        alle bestehenden Aufrufe unveraendert.
    """
    import sqlite3
    coord = (Path(coordinator_db) if coordinator_db is not None
             else Path(data_dir) / "coordinator.db")
    try:
        from management.server.identity import IdentityResolver
        from management.rbac.rbac_resolver import RbacResolver
    except Exception as exc:  # RBAC-Infrastruktur nicht importierbar
        if recovery:
            return (True, "RBAC nicht importierbar (%s) — Wiederherstellung "
                          "nicht blockiert." % exc)
        return (False, "RBAC nicht importierbar (%s) — abgebrochen." % exc)

    if not coord.exists():
        if recovery:
            return (True, "coordinator.db fehlt (%s) — Wiederherstellung nicht "
                          "blockiert." % coord)
        return (False, "coordinator.db fehlt (%s) — RBAC nicht pruefbar, "
                       "abgebrochen." % coord)

    try:
        person = IdentityResolver(str(coord)).resolve(os_user)
        con = sqlite3.connect("file:%s?mode=ro" % coord, uri=True)
        con.row_factory = sqlite3.Row
        try:
            erlaubt = RbacResolver(con).can(person["id"], "wartung.durchfuehren")
        finally:
            con.close()
    except Exception as exc:
        if recovery:
            return (True, "RBAC nicht pruefbar (%s) — Wiederherstellung nicht "
                          "blockiert." % exc)
        return (False, "RBAC nicht pruefbar (%s) — abgebrochen." % exc)

    wer = person.get("system_username", "?")
    if erlaubt:
        return (True, "erlaubt: %s" % wer)
    return (False, "verweigert: %s hat 'wartung.durchfuehren' nicht." % wer)
