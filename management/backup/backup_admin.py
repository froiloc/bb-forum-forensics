# =============================================================================
# management/backup/backup_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# backup_admin — CLI, das Planner + Executor + Registry zusammenfuehrt:
#
#   plan  — Trockenlauf: enumeriert alle DBs aus config.yaml und zeigt die
#           Speicherplatz-Vorabpruefung (schreibt NICHTS).
#   run   — fuehrt die Sicherung aus (verweigert bei fehlgeschlagener
#           Vorabpruefung), registriert den Lauf auditiert (BACKUP_CREATED)
#           in coordinator.db und zeigt eine Zusammenfassung.
#   list  — zeigt die registrierten Backups (Registry), optional je db_label.
#   pruefen — sieht den SICHERUNGSORDNER durch und sagt je Datenbank, wie
#           viele BRAUCHBARE Generationen uebrig sind (Build 626, rein
#           lesend). 'list' liest die Registrierung und sagt, was GESCHEHEN
#           IST; 'pruefen' sieht auf die Platte und sagt, was DA IST.
#   versatz — DIE NACHRECHNUNG (Build 717, Vorgang 77757536): rechnet aus
#           den Manifesten aus, wie weit erste und letzte Kopie eines Laufs
#           auseinanderliegen. Seit Build 617 ist der Versatz ABLESBAR; hier
#           wird er zum ersten Mal GEMESSEN. Rein lesend - es wird nicht
#           einmal eine Datenbank geoeffnet.
#   restore — DER RUECKWEG (Build 680, Vorgang 2785556a): prueft eine
#           Sicherung gegen die beim Sichern erhobene Pruefsumme, probt die
#           Zieldatenbank auf Ruhe und legt die gegengelesene Kopie NEBEN
#           das Original. UEBERSCHREIBT NIEMALS EINE DATENBANK - der Tausch
#           bleibt Handarbeit nach der ausgegebenen Anleitung
#           (Entscheidung Alex, 2026-08-05).
#
# Pfade und Rahmenbedingungen kommen aus config.yaml (paths.* / backup.*),
# override per --coordinator-db moeglich. Muster wie rbac_admin.
#
# Beleg: Bauplan B7 v1.1 §11; mc 2026-07-10.
#
# Build 625: 'run' legt Rechenschaft ueber die Aufbewahrung ab.
# Build 626: 'pruefen' kommt hinzu; 'list' liefert bei defekt vermerkten
#   Sicherungen 1 statt immer 0 (Vorgang e9522fe2).
# Build 680: 'restore' kommt hinzu (Vorgang 2785556a). Damit ist der
#   Rueckweg zum ersten Mal gefahren und nicht mehr bloss angenommen.
# Build 717: 'versatz' kommt hinzu (Vorgang 77757536). Die Ungleichzeitigkeit
#   des Sicherungssatzes ist damit nicht nur gekennzeichnet, sondern
#   ausrechenbar. DIE EINSTUFUNG DES WERKZEUGS AENDERT SICH DADURCH NICHT:
#   der neue Unterbefehl liest ausschliesslich die Manifest-Dateien im
#   Sicherungsverzeichnis - keine Datenbank, kein Schreibzugriff, auch nicht
#   auf die coordinator.db.
# WARTUNGSSTUFE B - betriebsvertraeglich mit benennbarer Einschraenkung
#   (Nachpruefung Build 616, Einstufung nachgetragen in Build 686).
#   'plan', 'list', 'pruefen' und 'versatz' sind rein lesend. 'run'
#   veraendert die Quellen nicht, konkurriert unter dem Rollback-Journal
#   aber mit den Schreibern - und der Sicherungssatz ist NICHT
#   punktgleich (Entscheidung
#   mc 2026-07-31: Kennzeichnung statt Wartungsfenster). 'restore' legt nur
#   eine Datei NEBEN das Original. Kein Wartungsvorbehalt, mit Absicht.
#
# Version: v0.8.717 · Build: 717 · 2026-08-13
# =============================================================================

import argparse
import getpass
import os
import json
import sqlite3
import sys
from typing import Dict, Optional

from management.audit.audit_log import AuditLog
from management.backup.backup_config import BackupConfig
from management.backup.backup_executor import (
    PUNKTGLEICH_VERMERK, BackupExecutor,
)
from management.backup.backup_planner import BackupPlanner
from management.backup.backup_pruefer import (
    SicherungsPruefer, bericht_json, bericht_text,
)
# VORGANG 77757536 (die Nachrechnung des Versatzes). Umbenannt importiert,
# weil dieses Werkzeug jetzt DREI Berichte kennt - der Pruefer beurteilt
# einen Ordner, der Wiederhersteller einen Rueckweg, die Versatzauswertung
# eine Reihe von Laeufen. Gleichnamige Einfuhren aus drei Bauteilen waeren
# genau die Art von Verwechslung, die man erst im Fehlerfall bemerkt.
from management.backup.backup_versatz import (
    MINDEST_LAEUFE as VZ_MINDEST_LAEUFE,
    RC_OHNE_GRUNDLAGE as VZ_RC_OHNE_GRUNDLAGE,
    RC_UNLESBAR as VZ_RC_UNLESBAR,
    VersatzAuswertung, arbeitszeit_zerlegen,
    bericht_json as vz_bericht_json, bericht_text as vz_bericht_text,
)
# Build 680 (Vorgang 2785556a): der Rueckweg. Die Namen werden umbenannt
# importiert, weil dieses Werkzeug jetzt ZWEI Berichte kennt - der Pruefer
# beurteilt einen Ordner, der Wiederhersteller einen einzelnen Rueckweg.
from management.backup.backup_wiederhersteller import (
    RC_UNBRAUCHBAR as WH_RC_UNBRAUCHBAR,
    Wiederhersteller, bericht_json as wh_bericht_json,
    bericht_text as wh_bericht_text,
)
from management.backup.backups_repo import BackupsRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from db.journal_policy import apply_journal_mode  # NEU Build 408
from management.help import cli_epilog
# Build 646: Vorrangregel an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

_PATH_KEYS = ("coordinator_db", "forensic_db_dir", "evidence_db_dir",
              "assets_db_dir", "default_db", "templates_db", "translations_db")


def _load_cfg(config_path: str):
    """
    Die Konfiguration dieses Laufs.

    UNVERAENDERT: Ein Fehlschlag ist hier ein ABBRUCH und kein Rueckfall -
    die ConfigLoader-Ausnahme wird bewusst nicht gefangen. Ohne lesbare
    Konfiguration weiss ein Sicherungswerkzeug weder, WAS es sichern soll,
    noch WOHIN; ein Lauf auf Vorgabewerten waere hier die gefaehrlichste
    aller Antworten.
    """
    from core.config_loader import ConfigLoader
    return ConfigLoader(config_path=config_path)


def _paths_from_cfg(cfg) -> Dict[str, str]:
    return {k: cfg.get("paths." + k) for k in _PATH_KEYS}


def _coordinator_db(args, cfg) -> str:
    """
    coordinator.db-Pfad: Argument --coordinator-db > paths.coordinator_db
    > Abbruch.

    BUILD 646: Aufloesung in core/werkzeug_konfig.py. Der Aufloeser wird UM
    die bereits geladene Konfiguration gebaut - dieses Werkzeug liest die
    Datei einmal und braucht sie an mehreren Stellen (Quellpfade,
    Sicherungsziel, Aufbewahrung). Zwei Lesungen koennten im Grenzfall
    verschiedene Staende erwischen; bei einer Sicherung waere das ein Satz
    aus zwei Konfigurationen.

    KEIN VORGABEWERT: Die coordinator.db ist hier zugleich Ziel der
    Registrierung UND eine der gesicherten Quellen. Ein erratener Pfad
    hiesse, den Lauf gegen einen anderen Bestand zu belegen als den
    gesicherten.
    """
    return werkzeug_konfig.db_pfad(
        "backup_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


def _open_con(db_path: str) -> sqlite3.Connection:
    """
    Die SCHREIBENDE Verbindung. Nur 'run' braucht sie - dort wird der Lauf
    registriert und ein Beleg geschrieben.
    """
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    # Build 408: Journalmodus zentral ueber db/journal_policy.py.
    # 'auto' = WAL bevorzugen, bei Fehlschlag (z.B. Netzlaufwerk: WAL braucht
    # maschinenlokales Shared Memory) protokollierter Rueckfall auf DELETE.
    apply_journal_mode(con, db_path)
    return con


def _open_con_ro(db_path: str) -> sqlite3.Connection:
    """
    Die NUR LESENDE Verbindung - fuer 'list' und 'pruefen'.

    BUILD 627 (Vorgang e9522fe2, zweiter Teil). Bis Build 626 benutzten auch
    die lesenden Unterbefehle _open_con: die coordinator.db wurde
    SCHREIBFAEHIG geoeffnet, und apply_journal_mode setzte dabei ein
    Journalmodus-PRAGMA. Nutzdaten wurden keine geschrieben - aber die
    Einstufung 'lesend' im Katalog war damit eine Zusage, die nichts
    durchsetzte. Genau derselbe Befundtyp steht im Eingang noch einmal
    (906ede75).

    KEIN apply_journal_mode HIER. Der Journalmodus ist eine Eigenschaft der
    DATEI, nicht der Verbindung; ihn zu setzen ist ein Schreibvorgang, und
    eine lesende Verbindung hat daran nichts zu aendern. Auf einer Datei, die
    bereits im WAL-Modus liegt, kann auch nur-lesend gelesen werden.
    """
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    return con


def _resolve_actor(con: sqlite3.Connection, actor: Optional[str]):
    if actor:
        row = con.execute(
            "SELECT id FROM person WHERE system_username = ?",
            (actor,)).fetchone()
        if row is None:
            raise SystemExit("[backup_admin] Unbekannte Person (--actor %r)."
                             % actor)
        return int(row[0]), None
    return None, {"performed_by": getpass.getuser()}


# ------------------------------------------------------------------ commands
def cmd_plan(args) -> int:
    cfg = _load_cfg(args.config)
    bcfg = BackupConfig.from_loader(cfg)
    plan = BackupPlanner(_paths_from_cfg(cfg), bcfg).plan()

    print("[backup_admin] Backup-Plan (Trockenlauf)")
    print("  Ziel:            %s" % plan.dest_dir)
    print("  Quellen:         %d DB(s)" % len(plan.sources))
    for s in plan.sources:
        print("    - %-16s %12d Bytes  %s" % (s.label, s.size, s.path))
    if plan.missing:
        print("  Fehlend/uebersprungen:")
        for m in plan.missing:
            print("    ! %s" % m)
    print("  Gesamtgroesse:   %d Bytes" % plan.total_size)
    print("  Benoetigt frei:  %d Bytes" % plan.required_free)
    print("  Frei am Ziel:    %d Bytes" % plan.free_at_dest)
    print("  Vorabpruefung:   %s%s" % (
        "OK" if plan.ok else "FEHLGESCHLAGEN",
        "" if plan.ok else " — " + plan.reason))
    return 0 if plan.ok else 2


def _umbruch(text: str, breite: int):
    """
    Bricht einen Fliesstext um. Bewusst hier von Hand und ohne Rueckgriff auf
    das Hilfesystem: dieses Werkzeug soll ohne den CLI-Katalog auskommen.
    """
    zeilen, aktuell = [], ""
    for wort in (text or "").split():
        if aktuell and len(aktuell) + 1 + len(wort) > breite:
            zeilen.append(aktuell)
            aktuell = wort
        else:
            aktuell = (aktuell + " " + wort) if aktuell else wort
    if aktuell:
        zeilen.append(aktuell)
    return zeilen


def cmd_run(args) -> int:
    cfg = _load_cfg(args.config)
    bcfg = BackupConfig.from_loader(cfg)
    plan = BackupPlanner(_paths_from_cfg(cfg), bcfg).plan()

    if not plan.ok:
        print("[backup_admin] Lauf verweigert (Vorabpruefung): %s"
              % plan.reason, file=sys.stderr)
        return 2

    # Erst sichern (kein offener coordinator-Writer waehrend VACUUM INTO), ...
    run = BackupExecutor(bcfg).run(plan)

    # ... dann den Lauf auditiert registrieren.
    db_path = _coordinator_db(args, cfg)
    con = _open_con(db_path)
    try:
        actor_id, _meta = _resolve_actor(con, args.actor)
        writer = CoordinatorWriter(con, AuditLog(con))
        seq = BackupsRepo(con, writer).record_run(run, actor_id)
    finally:
        con.close()

    ok_cnt = sum(1 for r in run.results if r.error is None and r.integrity_ok)
    print("[backup_admin] Lauf %s (Beleg audit_seq=%d)"
          % ("OK" if run.ok else "MIT FEHLERN", seq))
    print("  gesichert: %d/%d DB(s), geloescht (Retention): %d"
          % (ok_cnt, len(run.results), len(run.pruned)))
    for r in run.results:
        status = "ok" if (r.error is None and r.integrity_ok) else \
            ("FEHLER: " + (r.error or "integrity"))
        # Der Zeitpunkt JE DATENBANK steht mit in der Zeile - erst damit ist
        # der Versatz zwischen den Kopien ohne Blick ins Manifest zu sehen.
        print("    - %-16s %s%s"
              % (r.label, status,
                 ("   [%s .. %s]" % (r.begonnen_ts, r.beendet_ts))
                 if r.begonnen_ts else ""))
    print("  Manifest: %s" % run.manifest_path)

    # --- WAS DIE AUFBEWAHRUNG GETAN UND WAS SIE GELASSEN HAT (Build 625) ---
    # Alle drei Angaben stehen auch im Manifest. Sie gehoeren aber auf die
    # Konsole: der Anlass fuer diesen Umbau war ein Befund, den man nur
    # bemerkt hat, weil jemand den Quelltext gelesen hat - im Betrieb waere
    # er unsichtbar geblieben, bis die Sicherungen gebraucht worden waeren.
    if run.beiseite_gelegt:
        print("")
        print("  BEISEITEGELEGT - nicht als Sicherung belegt (%d):"
              % len(run.beiseite_gelegt))
        for eintrag in run.beiseite_gelegt:
            print("    %s" % eintrag)
        print("  Sie zaehlen nicht mehr als Generation und verdraengen "
              "nichts. Geloescht wurden sie nicht: an ihnen ist zu sehen, "
              "woran es gescheitert ist.")

    if run.nicht_beschnitten:
        print("")
        print("  NICHT BESCHNITTEN - kein belegter Lauf in diesem Durchgang "
              "(%d):" % len(run.nicht_beschnitten))
        for eintrag in run.nicht_beschnitten:
            print("    %s" % eintrag)

    if run.aufraeum_fehler:
        # AUF DIE FEHLERAUSGABE. Bleibt eine nicht belegte Datei unter dem
        # zaehlenden Namen liegen, kann sie eine gute Generation verdraengen -
        # das ist genau der Zustand, den dieser Build verhindern soll, und er
        # darf in keiner Protokollauswertung untergehen.
        print("")
        print("  AUFRAEUMEN UNVOLLSTAENDIG (%d):" % len(run.aufraeum_fehler),
              file=sys.stderr)
        for eintrag in run.aufraeum_fehler:
            print("    %s" % eintrag, file=sys.stderr)

    # WAEHREND DES LAUFS ENTSTANDEN und deshalb NICHT gesichert. Leer ist der
    # Regelfall; steht hier etwas, fehlt es im Satz - und das gehoert gesagt
    # und nicht nur ins Manifest geschrieben (Grundregel 1).
    if run.nachzuegler:
        print("")
        print("  NICHT GESICHERT - waehrend des Laufs entstanden (%d):"
              % len(run.nachzuegler))
        for pfad in run.nachzuegler:
            print("    %s" % pfad)
        print("  Sie fehlen in diesem Satz und sind beim naechsten Lauf "
              "dabei.")

    # --- DER VERMERK ZUR PUNKTGLEICHHEIT (Build 617) ---------------------
    # Er steht auf der KONSOLE und nicht nur im Manifest. Ein Hinweis, den
    # man erst findet, wenn man ihn sucht, erreicht denjenigen nicht, der
    # sich im Ernstfall auf den Satz verlaesst. Entscheidung mc 2026-07-31:
    # Kennzeichnung statt Wartungsfenster - damit gehoert die Einschraenkung
    # in jede Ausgabe.
    print("")
    for zeile in _umbruch(PUNKTGLEICH_VERMERK, 76):
        print("  " + zeile)
    return 0 if run.ok else 1


def cmd_list(args) -> int:
    cfg = _load_cfg(args.config)
    db_path = _coordinator_db(args, cfg)
    con = _open_con_ro(db_path)          # Build 627: 'list' liest nur
    try:
        rows = BackupsRepo(con, None).list_backups(
            db_label=args.db_label, limit=args.limit)
    finally:
        con.close()

    if not rows:
        print("[backup_admin] Keine registrierten Backups.")
        return 0
    print("[backup_admin] %d registrierte(s) Backup(s):" % len(rows))
    defekt = 0
    for r in rows:
        if not r["integrity_ok"]:
            defekt += 1
        print("  #%d  %s  %-16s  integrity=%s  seq=%s  %s"
              % (r["id"], r["run_ts"], r["db_label"],
                 "ok" if r["integrity_ok"] else "FEHLER",
                 r["audit_seq"], r["backup_path"] or "(kein)"))

    # BUILD 626 (Vorgang e9522fe2): 'list' lieferte IMMER 0 - auch dann, wenn
    # jede aufgefuehrte Sicherung 'integrity=FEHLER' trug. Eine Ueberwachung,
    # die nur den Rueckgabewert auswertet, sah dauerhaft gruen. Jetzt ist der
    # Leerbefund von einem Befund unterscheidbar, ohne die Ausgabe zu lesen.
    #
    # DIE 1 IST EINE AUSKUNFT UND KEIN PROGRAMMFEHLER - dieselbe Auffassung
    # wie bei 'hilfe.py suche' ohne Treffer. Sie wird deshalb auch
    # ausgesprochen und nicht nur zurueckgegeben.
    if defekt:
        print("")
        print("  BEFUND: %d von %d registrierten Sicherungen sind als NICHT "
              "integer" % (defekt, len(rows)))
        print("  vermerkt. Was hier steht, ist die Lage BEIM SICHERN - was "
              "heute im")
        print("  Ordner liegt, sagt 'backup_admin pruefen'.")
        return 1
    return 0


def cmd_pruefen(args) -> int:
    """
    Den Sicherungsordner ansehen: was liegt da, und wie viel davon ist
    brauchbar?

    REIN LESEND - kein Umbenennen, kein Loeschen, keine Registrierung. Ein
    Werkzeug, das eine Lage beurteilen soll, darf sie nicht veraendern.

    DIE REGISTRIERUNG WIRD NUR GELESEN, und auch das nur, um die
    Pruefsummen und die Gegenrichtung ('registriert, aber nicht da')
    beisteuern zu koennen. Ist die coordinator.db nicht erreichbar, laeuft
    die Pruefung trotzdem - sie ist dann nur um diese eine Angabe aermer,
    und das steht in der Ausgabe.
    """
    cfg = _load_cfg(args.config)
    bcfg = BackupConfig.from_loader(cfg)

    registrierte: Dict[str, Optional[str]] = {}
    hinweis = ""
    try:
        con = _open_con_ro(_coordinator_db(args, cfg))
        try:
            for r in BackupsRepo(con, None).list_backups(limit=100000):
                if r["backup_path"]:
                    registrierte[r["backup_path"]] = r["sha512"]
        finally:
            con.close()
    except Exception as exc:                       # pragma: no cover
        hinweis = ("Die Registrierung war nicht lesbar (%s). Geprueft wurde "
                   "allein, was im Ordner liegt; Pruefsummen und der Abgleich "
                   "'registriert, aber nicht da' fehlen." % exc)

    befund = SicherungsPruefer(bcfg.dest_dir).pruefen(
        registrierte=registrierte, mit_pruefsummen=args.pruefsummen)

    if args.json:
        daten = bericht_json(befund)
        if hinweis:
            daten["hinweis"] = hinweis
        print(json.dumps(daten, ensure_ascii=True, indent=2))
    else:
        print(bericht_text(befund))
        if hinweis:
            print("")
            for zeile in _umbruch("HINWEIS: " + hinweis, 78):
                print(zeile)

    # Der Ernstfall geht zusaetzlich auf die FEHLERAUSGABE. Wer die Ausgabe in
    # eine Datei umleitet und nur bei Fehlern hinsieht, muss ihn trotzdem
    # bemerken.
    if befund.ohne_sicherung:
        print("[backup_admin] OHNE BRAUCHBARE SICHERUNG: %s"
              % ", ".join(befund.ohne_sicherung), file=sys.stderr)
    return befund.rueckgabewert()


# =============================================================================
# restore - DER RUECKWEG (Build 680, Vorgang 2785556a)
# =============================================================================
# ZWEI ENTSCHEIDUNGEN STEHEN HINTER DIESER ROUTE, und beide gehoeren
# ausgesprochen:
#
# (1) ES WIRD NICHTS UEBERSCHRIEBEN. Die gepruefte Kopie wird NEBEN das
#     Original gelegt; der Tausch bleibt Handarbeit nach der ausgegebenen
#     Anleitung (Entscheidung Alex, 2026-08-05). Das Bauteil setzt das durch,
#     nicht dieses Werkzeug - siehe backup_wiederhersteller._schreiben.
#
# (2) DIESE ROUTE SCHREIBT NICHT IN DIE coordinator.db - auch keinen
#     Auditbeleg. Das ist bewusst und nicht vergessen: Im Ernstfall kann
#     ausgerechnet die coordinator.db die Datenbank sein, die ersetzt werden
#     soll. Ein Rueckweg, der einen Schreibzugriff auf sie voraussetzt, waere
#     dann nicht zu fahren. EventType.RESTORE_PERFORMED ist im Bestand
#     ausdruecklich als 'reserviert, noch nicht aktiv' gefuehrt
#     (management/audit/event_types.py Z. 383-384); er gehoert zum TAUSCH,
#     den ein Mensch verantwortet, nicht zu dieser Vorbereitung.
#
#     DAMIT DER LAUF TROTZDEM BELEGT IST, wird der vollstaendige Befund als
#     JSON neben die Kopie gelegt ('<ziel>.wiederhergestellt.befund.json').
#     Ein Rueckweg ohne Beleg waere genau die Vermutung, gegen die dieser
#     Vorgang geschrieben ist (Grundregel 1).
# =============================================================================

#: Die Endung der Protokolldatei neben der Kopie.
ENDUNG_BEFUND = ".befund.json"


def _registrierung_lesen(args, cfg):
    """
    Die registrierten Sicherungen - oder eine leere Liste und ein Hinweis.

    KEIN ABBRUCH bei unlesbarer Registrierung. Die Registrierung ist hier
    die BESSERE, aber nicht die einzige Quelle: im Ernstfall kann sie selbst
    beschaedigt sein. Was dann fehlt, ist die erhobene Pruefsumme - und das
    wird gesagt, nicht verschwiegen.
    """
    try:
        con = _open_con_ro(_coordinator_db(args, cfg))
        try:
            return list(BackupsRepo(con, None).list_backups(limit=100000)), ""
        finally:
            con.close()
    except Exception as exc:                       # pragma: no cover
        return [], ("Die Registrierung war nicht lesbar (%s). Damit steht "
                    "KEINE erhobene Pruefsumme zur Verfuegung; ohne sie ist "
                    "nicht feststellbar, ob die Sicherungsdatei noch die "
                    "ist, die beim Sichern zertifiziert wurde." % exc)


def _summe_zu_pfad(rows, pfad: str) -> Optional[str]:
    """Die erhobene Pruefsumme zu einer Sicherungsdatei - oder None."""
    ziel = os.path.abspath(pfad)
    for r in rows:
        if r["backup_path"] and os.path.abspath(r["backup_path"]) == ziel:
            return r["sha512"]
    return None


def _quelle_zu_pfad(rows, pfad: str) -> Optional[str]:
    """Woher die Sicherung stammte (src_path) - oder None."""
    ziel = os.path.abspath(pfad)
    for r in rows:
        if r["backup_path"] and os.path.abspath(r["backup_path"]) == ziel:
            return r["src_path"]
    return None


def _aus_registrierung(rows, db_label: str, stand: Optional[str]):
    """
    Die juengste brauchbare registrierte Sicherung eines db_label.

    'brauchbar' heisst hier: beim Sichern als integer vermerkt UND die Datei
    liegt noch da. Eine Zeile, deren Datei fehlt, ist eine Buchhaltung ohne
    Gegenstand - sie wird uebergangen, aber gezaehlt, damit der Grund im
    Hinweis stehen kann.

    Die Liste kommt aus list_backups() bereits nach run_ts absteigend
    sortiert (backups_repo.py, ORDER BY run_ts DESC) - die erste passende
    Zeile ist deshalb die juengste.
    """
    verworfen_defekt = 0
    verworfen_weg = 0
    for r in rows:
        if r["db_label"] != db_label:
            continue
        if stand and not str(r["run_ts"] or "").startswith(stand):
            continue
        if not r["integrity_ok"]:
            verworfen_defekt += 1
            continue
        if not r["backup_path"] or not os.path.isfile(r["backup_path"]):
            verworfen_weg += 1
            continue
        return r, verworfen_defekt, verworfen_weg
    return None, verworfen_defekt, verworfen_weg


def _aus_ordner(bcfg, db_label: str, stand: Optional[str]):
    """
    DER RUECKFALL: die juengste brauchbare Generation im Sicherungsordner,
    ohne Registrierung.

    Es wird derselbe Pruefer benutzt wie bei 'pruefen' - eine zweite
    Beurteilung derselben Frage waere eine zweite Wahrheit. Die
    Pruefsummenpruefung entfaellt hier notwendigerweise: sie stammt aus der
    Registrierung, die gerade nicht zur Verfuegung steht.
    """
    befund = SicherungsPruefer(bcfg.dest_dir).pruefen(
        registrierte={}, mit_pruefsummen=False)
    for label in befund.labels:
        if label.label != db_label:
            continue
        for datei in label.brauchbar:
            if stand and not datei.ts.startswith(stand):
                continue
            return datei
    return None


def cmd_restore(args) -> int:
    """
    Eine Sicherung pruefen und neben ihr Original legen.

    DER WEG IN VIER SCHRITTEN, und der dritte ist der, um den es geht:
      1. Die Sicherung waehlen - aus der Registrierung, hilfsweise aus dem
         Ordner.
      2. Die erhobene Pruefsumme dazuholen.
      3. Der Wiederhersteller faehrt die Prueffolge und legt die Kopie ab.
      4. Der Befund wird ausgegeben und neben die Kopie protokolliert.
    """
    cfg = _load_cfg(args.config)
    bcfg = BackupConfig.from_loader(cfg)
    rows, reg_hinweis = _registrierung_lesen(args, cfg)
    hinweise = [reg_hinweis] if reg_hinweis else []

    sicherung: Optional[str] = None
    ziel: Optional[str] = args.ziel

    if args.sicherung:
        # AUSDRUECKLICH BENANNT. Dann wird sie genommen - auch wenn sie nicht
        # registriert ist. Das ist der Ernstfall-Weg: eine von Hand vom
        # Sicherungsmedium geholte Datei. Ob eine Pruefsumme dazu vorliegt,
        # entscheidet sich gleich, und ihr Fehlen ist ein BEFUND.
        sicherung = args.sicherung
        if not ziel:
            ziel = _quelle_zu_pfad(rows, sicherung)
            if ziel:
                hinweise.append(
                    "Das Ziel wurde der Registrierung entnommen (src_path "
                    "der Sicherung): %s. Wenn diese Anlage inzwischen an "
                    "einem anderen Ort laeuft, ist '--ziel' ausdruecklich "
                    "anzugeben." % ziel)
    else:
        if not args.db_label:
            print("[backup_admin] restore braucht entweder --sicherung "
                  "oder --db-label.", file=sys.stderr)
            return WH_RC_UNBRAUCHBAR
        zeile, defekt, weg = _aus_registrierung(rows, args.db_label,
                                                args.stand)
        if zeile is not None:
            sicherung = zeile["backup_path"]
            if not ziel:
                ziel = zeile["src_path"]
            if defekt or weg:
                hinweise.append(
                    "Uebergangen wurden %d als nicht integer vermerkte und "
                    "%d registrierte, aber nicht mehr vorhandene "
                    "Sicherung(en) desselben db_label. Das ist kein Fehler - "
                    "es steht hier, damit die getroffene Auswahl "
                    "nachvollziehbar ist." % (defekt, weg))
        else:
            datei = _aus_ordner(bcfg, args.db_label, args.stand)
            if datei is None:
                print("[backup_admin] KEINE brauchbare Sicherung fuer "
                      "db_label '%s'%s - weder registriert noch im Ordner "
                      "'%s'."
                      % (args.db_label,
                         (" mit Stand '%s'" % args.stand) if args.stand
                         else "", bcfg.dest_dir),
                      file=sys.stderr)
                return WH_RC_UNBRAUCHBAR
            sicherung = datei.pfad
            hinweise.append(
                "DIE SICHERUNG STAMMT AUS DEM ORDNER, nicht aus der "
                "Registrierung: zu '%s' ist dort keine brauchbare Zeile "
                "vorhanden. Damit gibt es keine erhobene Pruefsumme, gegen "
                "die sich gegenrechnen liesse." % args.db_label)

    if not ziel:
        print("[backup_admin] Kein Ziel bestimmbar. '--ziel <pfad>' angeben "
              "- die Registrierung kennt zu dieser Sicherung keinen "
              "src_path.", file=sys.stderr)
        return WH_RC_UNBRAUCHBAR

    summe = _summe_zu_pfad(rows, sicherung)

    werkzeug = Wiederhersteller(sicherung, ziel)
    befund = werkzeug.fahren(erwartete_summe=summe,
                             schreiben=not args.trocken)

    if args.json:
        daten = wh_bericht_json(befund)
        if hinweise:
            daten["hinweise"] = hinweise
        print(json.dumps(daten, ensure_ascii=True, indent=2))
    else:
        print(wh_bericht_text(befund))
        for h in hinweise:
            print("")
            for zeile in _umbruch("HINWEIS: " + h, 78):
                print(zeile)

    # --- DER BELEG NEBEN DER KOPIE ---------------------------------------
    # Nur wenn wirklich geschrieben wurde. Ein Protokoll ohne Kopie waere
    # ein Beleg ueber nichts.
    if befund.geschrieben:
        protokoll = befund.geschrieben + ENDUNG_BEFUND
        daten = wh_bericht_json(befund)
        daten["hinweise"] = hinweise
        try:
            with open(protokoll, "w", encoding="utf-8") as fh:
                json.dump(daten, fh, ensure_ascii=True, indent=2)
            print("")
            print("  Beleg: %s" % protokoll)
        except OSError as exc:
            # AUF DIE FEHLERAUSGABE, und der Rueckgabewert bleibt davon
            # unberuehrt: die Kopie liegt und ist gegengelesen. Ein
            # fehlendes Protokoll ist ein Mangel am Beleg, nicht an der
            # Wiederherstellung - aber er darf nicht untergehen.
            print("  BELEG NICHT GESCHRIEBEN (%s): %s" % (protokoll, exc),
                  file=sys.stderr)

    # Der Ernstfall zusaetzlich auf die Fehlerausgabe - wie bei 'pruefen'.
    if not befund.ok:
        print("[backup_admin] RUECKWEG MIT BEFUND (%d): %s"
              % (len(befund.offene_befunde),
                 ", ".join(s.name for s in befund.offene_befunde)),
              file=sys.stderr)
    return befund.rueckgabewert()


# =============================================================================
# versatz - DIE NACHRECHNUNG (Vorgang 77757536)
# =============================================================================
# WARUM ES DIESEN UNTERBEFEHL GIBT: Build 617 hat den Versatz im
# Sicherungssatz ABLESBAR gemacht - 'begonnen_ts'/'beendet_ts' je Datenbank,
# 'satz_von'/'satz_bis' je Lauf. Ablesbar ist nicht gemessen. Die
# Entscheidung von mc gegen ein Wartungsfenster (31.07.2026) steht seither
# auf der Annahme, der Versatz sei klein; ob er es ist, entscheidet eine
# Zahl, die aus den Manifesten zu bilden ist.
#
# ER STEHT BEI DEN LESENDEN UNTERBEFEHLEN, weil er es ist: kein Schreiben,
# keine Datenbankverbindung, nicht einmal die coordinator.db wird geoeffnet.
# Gelesen werden ausschliesslich die Manifest-Dateien im
# Sicherungsverzeichnis. Damit ist er zu jeder Betriebszeit unbedenklich -
# anders als der Lauf, den er auswertet.
# =============================================================================

def cmd_versatz(args) -> int:
    """
    Den Versatz im Sicherungssatz aus den Manifesten ausrechnen. REIN LESEND.

    DAS VERZEICHNIS KOMMT AUS DER KONFIGURATION (backup.dest_dir) und wird
    nur durch '--verzeichnis' ersetzt. Der Ausnahmefall dahinter ist echt:
    Manifeste, die von einem Sicherungsmedium in einen Ordner zurueckgeholt
    wurden, liegen nicht dort, wo heute gesichert wird.

    KEINE STILLE ANNAHME BEI DER UHRZEIT: '--arbeitszeit' verlangt zwingend
    auch '--ortszeit-versatz'. Die Zeitstempel sind UTC, die Arbeitszeit der
    Ermittelnden ist Ortszeit. Wer beides ohne Umrechnung vergleicht, ordnet
    im Sommer jeden Lauf um zwei Stunden falsch ein - und das Ergebnis saehe
    aus wie eine Auskunft. Ein Abbruch ist hier das kleinere Uebel; es ist
    dieselbe Regel, die der CLI-Katalog bei den Datenbankpfaden anlegt.
    """
    if args.verzeichnis:
        verzeichnis = args.verzeichnis
    else:
        cfg = _load_cfg(args.config)
        verzeichnis = BackupConfig.from_loader(cfg).dest_dir

    arbeitszeit = None
    if args.arbeitszeit:
        if args.ortszeit_versatz is None:
            print("[backup_admin] '--arbeitszeit' verlangt zusaetzlich "
                  "'--ortszeit-versatz'.", file=sys.stderr)
            for zeile in _umbruch(
                    "Die Zeitstempel der Manifeste sind UTC, ein "
                    "Arbeitszeitfenster ist Ortszeit. Ohne den Versatz waere "
                    "der Vergleich im Sommer um 120 Minuten daneben, ohne "
                    "dass man es der Ausgabe ansieht. Fuer Europe/Berlin: "
                    "'--ortszeit-versatz 120' (Sommerzeit) bzw. '60' "
                    "(Winterzeit). Wer in UTC vergleichen will, gibt "
                    "ausdruecklich '--ortszeit-versatz 0' an.", 76):
                print("  " + zeile, file=sys.stderr)
            return VZ_RC_UNLESBAR
        try:
            arbeitszeit = arbeitszeit_zerlegen(args.arbeitszeit)
        except ValueError as exc:
            print("[backup_admin] '--arbeitszeit' ist nicht verstaendlich: %s"
                  % exc, file=sys.stderr)
            return VZ_RC_UNLESBAR

    befund = VersatzAuswertung(
        verzeichnis,
        mindest_laeufe=args.mindest_laeufe,
        schwelle_minuten=args.schwelle_minuten,
        ortszeit_versatz=args.ortszeit_versatz or 0,
        arbeitszeit=arbeitszeit).auswerten()

    if args.json:
        print(json.dumps(vz_bericht_json(befund), ensure_ascii=True,
                         indent=2))
    else:
        print(vz_bericht_text(befund))

    # Wie bei 'pruefen': der Ernstfall geht zusaetzlich auf die
    # FEHLERAUSGABE. Wer die Auswertung in eine Datei umleitet und nur bei
    # Fehlern hinsieht, muss ihn trotzdem bemerken.
    if befund.rueckgabewert() >= VZ_RC_OHNE_GRUNDLAGE:
        print("[backup_admin] VERSATZ NICHT AUSGEWERTET: %s"
              % ("das Verzeichnis '%s' ist nicht lesbar" % verzeichnis
                 if not befund.lesbar
                 else "kein Manifest aus Build 617 oder neuer in '%s'"
                      % verzeichnis),
              file=sys.stderr)
    return befund.rueckgabewert()


# ---------------------------------------------------------------- arg parser
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auditierte Datensicherung "
                    "(plan/run/list/pruefen/restore/versatz).",
        epilog=cli_epilog.epilog("backup_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    sub = parser.add_subparsers(dest="action", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--coordinator-db", default=None)
    common.add_argument("--config", default="./config.yaml")

    sub.add_parser("plan", parents=[common],
                   help="Trockenlauf: Quellen + Speicherplatz-Vorabpruefung.")

    # BUILD 626: die Nachschau im Sicherungsordner. Sie steht bei 'plan' und
    # nicht bei 'run', weil sie zu den LESENDEN Unterbefehlen gehoert - und
    # weil man sie vor einem Lauf ansieht, nicht danach.
    p_pruefen = sub.add_parser(
        "pruefen", parents=[common],
        help="Sicherungsordner ansehen: was liegt da, und wie viel davon "
             "ist brauchbar? Rein lesend.")
    p_pruefen.add_argument(
        "--pruefsummen", action="store_true",
        help="Die beim Sichern erhobenen Pruefsummen gegenrechnen. LIEST "
             "JEDE DATEI GANZ - bei grossen Bestaenden dauert das.")
    p_pruefen.add_argument("--json", action="store_true",
                           help="Befund als JSON statt als Text.")

    # VORGANG 77757536: die Nachrechnung. Sie steht bei den lesenden
    # Unterbefehlen, weil sie nichts anfasst ausser den Manifesten.
    p_versatz = sub.add_parser(
        "versatz", parents=[common],
        help="Den VERSATZ im Sicherungssatz aus den Manifesten ausrechnen: "
             "wie weit liegen erste und letzte Kopie eines Laufs "
             "auseinander? Rein lesend.")
    p_versatz.add_argument(
        "--verzeichnis", default=None,
        help="Wo die Manifeste liegen. Ohne Angabe backup.dest_dir aus der "
             "Konfiguration. Fuer Manifeste, die von einem "
             "Sicherungsmedium zurueckgeholt wurden.")
    p_versatz.add_argument(
        "--mindest-laeufe", type=int, default=VZ_MINDEST_LAEUFE,
        dest="mindest_laeufe",
        help="Wie viele auswertbare Laeufe als Grundlage verlangt werden "
             "(Vorgabe %d, aus Vorgang 77757536). Darunter ergeht ein "
             "Befund - die Zahlen sind dann richtig, tragen aber noch "
             "keine Entscheidung." % VZ_MINDEST_LAEUFE)
    p_versatz.add_argument(
        "--schwelle-minuten", type=float, default=None,
        dest="schwelle_minuten",
        help="Ab welcher Spanne ein Lauf beanstandet wird. OHNE ANGABE WIRD "
             "NICHT BEURTEILT, nur gemessen: eine Grenze ist nicht "
             "entschieden, und eine fest verdrahtete waere eine Entscheidung "
             "im Gewand einer Messung.")
    p_versatz.add_argument(
        "--ortszeit-versatz", type=int, default=None,
        dest="ortszeit_versatz",
        help="Versatz der Ortszeit gegen UTC in MINUTEN (Europe/Berlin: 120 "
             "im Sommer, 60 im Winter). Betrifft nur die Anzeige und die "
             "Arbeitszeitfrage, nicht die gemessenen Spannen. Zwingend, "
             "wenn '--arbeitszeit' angegeben wird.")
    p_versatz.add_argument(
        "--arbeitszeit", default=None,
        help="Arbeitszeitfenster in ORTSZEIT als 'HH:MM-HH:MM' (z. B. "
             "'07:00-18:00'). Ein Fenster ueber Mitternacht ist erlaubt. "
             "Ohne Angabe wird nicht beurteilt, ob ein Lauf in die "
             "Arbeitszeit fiel.")
    p_versatz.add_argument("--json", action="store_true",
                           help="Befund als JSON statt als Text.")

    p_run = sub.add_parser("run", parents=[common],
                           help="Sicherung ausfuehren + auditiert registrieren.")
    p_run.add_argument("--actor", default=None,
                       help="system_username des Ausfuehrenden (Audit-Akteur).")

    p_list = sub.add_parser("list", parents=[common],
                            help="Registrierte Backups zeigen.")
    p_list.add_argument("--db-label", default=None, dest="db_label")
    p_list.add_argument("--limit", type=int, default=100)

    # BUILD 680 (Vorgang 2785556a): DER RUECKWEG. Er steht hier ans Ende und
    # nicht zwischen die lesenden Unterbefehle, weil er als einziger eine
    # Datei ANLEGT - wenn auch niemals die Zieldatenbank selbst.
    p_restore = sub.add_parser(
        "restore", parents=[common],
        help="Eine Sicherung pruefen und NEBEN ihr Original legen. "
             "Ueberschreibt nichts - der Tausch bleibt Handarbeit nach der "
             "ausgegebenen Anleitung.")
    p_restore.add_argument(
        "--db-label", default=None, dest="db_label",
        help="Welche Datenbank (z. B. 'coordinator', 'evidence_18'). Es "
             "wird die juengste brauchbare Generation genommen. Entweder "
             "dies oder --sicherung.")
    p_restore.add_argument(
        "--sicherung", default=None,
        help="Eine bestimmte Sicherungsdatei - der Ernstfall-Weg fuer eine "
             "von Hand vom Sicherungsmedium geholte Datei.")
    p_restore.add_argument(
        "--ziel", default=None,
        help="Die Datenbank, die ersetzt werden soll. Ohne Angabe wird der "
             "src_path aus der Registrierung genommen.")
    p_restore.add_argument(
        "--stand", default=None,
        help="Eine bestimmte Generation ueber den Anfang ihres "
             "Zeitstempels waehlen (z. B. '20260805').")
    p_restore.add_argument(
        "--trocken", action="store_true",
        help="Nur pruefen und sagen, was geschehen WUERDE. Schreibt nichts.")
    p_restore.add_argument("--json", action="store_true",
                           help="Befund als JSON statt als Text.")

    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "list": cmd_list,
            "pruefen": cmd_pruefen, "versatz": cmd_versatz,
            "restore": cmd_restore}[args.action](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
