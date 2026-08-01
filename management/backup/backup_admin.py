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
#
# Pfade und Rahmenbedingungen kommen aus config.yaml (paths.* / backup.*),
# override per --coordinator-db moeglich. Muster wie rbac_admin.
#
# Beleg: Bauplan B7 v1.1 §11; mc 2026-07-10.
#
# Build 625: 'run' legt Rechenschaft ueber die Aufbewahrung ab.
# Build 626: 'pruefen' kommt hinzu; 'list' liefert bei defekt vermerkten
#   Sicherungen 1 statt immer 0 (Vorgang e9522fe2).
# Version: v0.8.626 · Build: 626 · 2026-08-01
# =============================================================================

import argparse
import getpass
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


# ---------------------------------------------------------------- arg parser
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auditierte Datensicherung (plan/run/list).",
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

    p_run = sub.add_parser("run", parents=[common],
                           help="Sicherung ausfuehren + auditiert registrieren.")
    p_run.add_argument("--actor", default=None,
                       help="system_username des Ausfuehrenden (Audit-Akteur).")

    p_list = sub.add_parser("list", parents=[common],
                            help="Registrierte Backups zeigen.")
    p_list.add_argument("--db-label", default=None, dest="db_label")
    p_list.add_argument("--limit", type=int, default=100)

    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "list": cmd_list,
            "pruefen": cmd_pruefen}[args.action](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
