#!/usr/bin/env python3
# =============================================================================
# tools/migrate-dbs.py
# IT-Forensisches Ermittlungswerkzeug — Migrationsstand aller Datenbanken
# =============================================================================
# Zweck (Build 585):
#   EIN Werkzeug fuer die Frage "ist alles auf Stand?" — ueber alle
#   Datenbanken hinweg, mit einer einheitlichen Schnittstelle.
#
# ANLASS (2026-07-30): auf der Anlage fehlten zwei Migrationen der
#   templates.db seit dem 21./22. Juli. Es gab keinen Fehler, nur Stille:
#   Bausteine, Vorlagen und Platzhalter blieben leer, weil die Datenschicht
#   gescheiterte Abfragen abfing. Die Suche kostete einen halben Tag.
#
#   Der Grund war struktureller Art. Vier Datenbanken haben ein Register
#   (schema_migrations) und einen Runner; templates.db hatte fuenf einzeln
#   aufzurufende Skripte MIT UNEINHEITLICHEN SCHALTERN (--no-backup kannten
#   nur zwei, --dry-run nur eines). Was man sich merken muss, vergisst man.
#
# ── FESTLEGUNGEN (mc 2026-07-30) ────────────────────────────────────────────
#
#   (1) VORGABE IST DIE TROCKENUEBUNG. Ohne --apply wird NICHTS geschrieben.
#       Das Werkzeug sagt, was es taete.
#   (2) SCHARFSCHALTEN IST EIN EIGENER HANDGRIFF (--apply). Das Anwenden von
#       Migrationen bleibt eine bewusste, protokollierte Handlung — dieselbe
#       Festlegung wie fuer die Server (Build 376: der Server WARNT nur).
#   (3) JEDE ANWENDUNG SICHERT VORHER, ausser bei --no-backup.
#   (4) default.db und translations.db werden GENANNT, aber nicht bewertet:
#       sie stammen aus dem Prepper. Eine noetige Migration gehoert dorthin,
#       nicht hierher (mc). Sie stillschweigend wegzulassen waere aber falsch —
#       dann fragte sich jemand, warum sie fehlen.
#
# ── WARUM forensic_<uid>.db NIE MIGRIERT WIRD ───────────────────────────────
#
#   Sie ist das versiegelte Beweismittel (read-only, Integritaet ueber
#   SHA-256 belegt). Ein Werkzeug, das dort schreibt, veraendert Beweise.
#   Deshalb wird ihr Stand GEPRUEFT und ANGEZEIGT, aber --apply laesst sie
#   auch scharfgeschaltet unberuehrt. Das ist keine Vorsichtsmassnahme,
#   sondern eine Grenze.
#
# Aufruf:
#   python3 tools/migrate-dbs.py                     # Trockenuebung, alle
#   python3 tools/migrate-dbs.py --db templates      # nur eine
#   python3 tools/migrate-dbs.py --subject-id 1488   # inkl. Fall-Datenbanken
#   python3 tools/migrate-dbs.py --apply             # scharf, mit Sicherung
#   python3 tools/migrate-dbs.py --apply --no-backup # scharf, ohne Sicherung
#
# ── WARTUNGSVORBEHALT — STUFE A (Build 612) ─────────────────────────────────
#
#   Mit --apply baut das Werkzeug Tabellen um und schreibt in templates.db
#   sowie in evidence_<uid>.db und assets_<uid>.db — Letztere stehen seit dem
#   01.07.2026 unter dem Migrationsvorbehalt. Es sichert vorher (ausser bei
#   --no-backup), aber es SPIELT NICHTS ZURUECK: nach einem Abbruch liegt die
#   Sicherung da und muss von Hand eingesetzt werden.
#
#   Vor dem scharfen Lauf wird deshalb geprueft, ob die TATSAECHLICH
#   betroffenen Dateien ruhig sind; ohne aktives Wartungsfenster geht es nur
#   nach Eingabe eines vollstaendigen Wortes weiter
#   (maintenance/wartungsvorbehalt.py). Die Trockenuebung ist davon NICHT
#   betroffen — sie schreibt nichts und braucht keinen Vorbehalt.
#   Einstufung: Vermerk_Wartungsvorbehalt_Analyse_K1_K8_v1_0.md, von mc
#   bestaetigt am 2026-07-31.
#
# Rueckgabewert: 0 = alles aktuell (auch NACH einem erfolgreichen --apply)
#                1 = es fehlt etwas · 2 = Fehler (Datei/Pfad/Zugriff)
#                3 = Wartungsvorbehalt, es wurde NICHTS geschrieben
#
# Version: v0.8.612 · Build: 612 · 2026-07-31
# =============================================================================

import argparse
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from maintenance.wartungsvorbehalt import wartungsvorbehalt   # noqa: E402

# Datenbanken MIT Register (schema_migrations + m###-Module).
REGISTER_DBS = ("coordinator", "evidence", "forensic", "assets")

# Datenbanken, die der Prepper erzeugt — genannt, nicht bewertet (mc).
FREMDE_DBS = ("default", "translations")

# ── BUILD 586 — SPUREN STATT REGISTER-SCHLUSS ──────────────────────────────
#
# Befund mc (2026-07-30): die Ausgabe "evidence_1488.db  0 von 3  OFFEN: 1,2,3"
# war ZWEIDEUTIG. Sie kam allein daraus, dass die Tabelle schema_migrations
# fehlte. Das kann zweierlei heissen:
#
#   (a) die Migrationen sind wirklich nicht gelaufen, oder
#   (b) ihre WIRKUNGEN sind laengst da, nur wurde nie ein Register angelegt.
#
# (b) ist bei den Fall-Datenbanken der plausible Normalfall: m001 ist
# ausdruecklich DATENNEUTRAL - sie legt nur das Register an, die fachlichen
# Tabellen stammen aus dem Prepper. Aus einem fehlenden Register auf eine
# fehlende Wirkung zu schliessen, ist derselbe Fehler wie 'leere Liste heisst
# es gibt nichts'.
#
# Deshalb wird jetzt BEIDES erhoben: der Registerstand UND die Spur jeder
# Migration. Erst der Vergleich erlaubt eine eindeutige Aussage.
#
# (Fuer coordinator.db bleibt das Register massgeblich: es existiert dort seit
# jeher, und 37 Spuren zu pflegen waere Redundanz ohne Gewinn.)
SPUREN = {
    "evidence": {
        1: ("tabelle", "schema_migrations"),
        2: ("tabelle", "annotation_tatzeit"),
        3: ("tabelle", "evidence_audit_log"),
    },
    "assets": {
        1: ("tabelle", "schema_migrations"),
    },
    "forensic": {
        1: ("tabelle", "schema_migrations"),
    },
}

# Der ZUSTAENDIGE Befehl je Datenbankart. In Build 585 stand hier fuer ALLE
# 'python -m management.migrate' - das behandelt aber ausschliesslich
# coordinator.db. mc hat den Befehl ausgefuehrt, 'bereits aktuell' gelesen und
# nichts veraendert vorgefunden. Ein Werkzeug, das den falschen Weg weist, ist
# schlimmer als eines, das schweigt.
# Build 587: evidence und assets wendet dieses Werkzeug jetzt SELBST an
# (ueber den MigrationRunner, der das massgebliche Register in der Datenbank
# schreibt). Der Verweis auf die Flotten-Schicht ist entfallen - sie ist auf
# dieser Anlage nicht in Betrieb, und migration.db existiert nicht.
# Fuer coordinator.db bleibt der eigene Einstiegspunkt zustaendig: er baut
# zusaetzlich das Audit-Log an (deployed_by) und ist der eingefuehrte Weg.
BEFEHL = {
    "coordinator":
        "python3 -m management.migrate --deployed-by <KENNUNG>",
}

# Die fuenf Skripte der templates.db, in Anwendungsreihenfolge.
# Idempotenz ist BELEGT (Messung 2026-07-30: zweiter Lauf auf vollstaendigem
# Stand laesst Schema und Daten unveraendert und schreibt keine Audit-Zeile).
TEMPLATES_SCHRITTE = (
    (341, "module_key an report_modules", "migrate_templates_module_key"),
    (388, "Vollstaendige Berichtsvorlagen", "migrate_templates_full_templates"),
    (421, "Audit-CHECK erweitert", "migrate_templates_audit_check"),
    (489, "Platzhalter-Neuordnung", "migrate_templates_placeholders"),
    (497, "Gross-/Kleinschreibung", "migrate_templates_ci"),
)


# ---------------------------------------------------------------- Hilfsmittel
def sicherung(pfad: Path) -> Path:
    """Dateikopie neben dem Original. Der Zeitstempel macht sie eindeutig."""
    ziel = pfad.with_suffix(pfad.suffix + ".vor-migration-%d.bak"
                            % int(time.time()))
    shutil.copy2(str(pfad), str(ziel))
    return ziel


def _register_stand(pfad: Path) -> Tuple[List[int], Optional[str]]:
    """Angewandte Versionen aus schema_migrations. -> (versionen, fehler)"""
    try:
        con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
    except sqlite3.Error as exc:
        return ([], str(exc))
    try:
        rows = con.execute("SELECT version FROM schema_migrations").fetchall()
        return (sorted(int(r[0]) for r in rows), None)
    except sqlite3.OperationalError:
        # Kein Register -> noch nie migriert (Version 0), kein Fehler.
        return ([], None)
    finally:
        con.close()


def _spur_da(pfad: Path, spur) -> bool:
    """Ist die Wirkung einer Migration in der Datei nachweisbar?"""
    art, wert = spur
    try:
        con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
    except sqlite3.Error:
        return False
    try:
        if art == "tabelle":
            row = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (wert,)).fetchone()
            return row is not None
        return False
    finally:
        con.close()


def fall_befund(pfad: Path, art: str) -> dict:
    """
    Erhebt Register UND Spuren und zieht daraus eine EINDEUTIGE Aussage.

    -> {"eingetragen": [...], "wirkung_da": [...], "wirkung_fehlt": [...],
        "lage": "aktuell" | "nur_eintrag_fehlt" | "wirkung_fehlt"}
    """
    eingetragen, _ = _register_stand(pfad)
    spuren = SPUREN.get(art, {})
    wirkung_da, wirkung_fehlt = [], []
    for version in sorted(spuren):
        (wirkung_da if _spur_da(pfad, spuren[version])
         else wirkung_fehlt).append(version)

    # BUILD 586, Feinschliff: das REGISTER ist eine Sonderspur. Seine Wirkung
    # IST der Eintrag - sein Fehlen bedeutet 'nicht eingetragen', nicht
    # 'fachlich nicht geschehen'. Wuerde man es wie eine gewoehnliche Spur
    # behandeln, meldete eine Datenbank, an der sachlich nichts fehlt, einen
    # Notstand. Genau diese Zweideutigkeit war der Anlass des Umbaus.
    fachlich_fehlt = [v for v in wirkung_fehlt
                      if spuren[v] != ("tabelle", "schema_migrations")]
    if fachlich_fehlt:
        lage = "wirkung_fehlt"
    elif wirkung_fehlt or len(eingetragen) < len(spuren):
        lage = "nur_eintrag_fehlt"
    else:
        lage = "aktuell"
    return {"eingetragen": eingetragen, "wirkung_da": wirkung_da,
            "wirkung_fehlt": wirkung_fehlt,
            "fachlich_fehlt": fachlich_fehlt, "lage": lage}


def _verfuegbare_versionen(art: str) -> List[int]:
    from management.migrations.runner import discover
    paket = __import__("management.migrations.%s" % art, fromlist=["x"])
    return sorted(m.VERSION for m in discover(paket))


def templates_stand(pfad: Path) -> List[Tuple[int, str, bool]]:
    """-> [(build, bezeichnung, angewandt?)] anhand von Spuren."""
    from management.templates_db_status import MIGRATIONEN, spur_gefunden
    con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
    try:
        return [(build, name, spur_gefunden(con, spur))
                for name, build, spur, _ in MIGRATIONEN]
    finally:
        con.close()


def templates_anwenden(pfad: Path, changed_by: str) -> List[str]:
    """Alle fuenf Schritte anwenden (idempotent). -> Meldungen."""
    import importlib
    meldungen = []
    con = sqlite3.connect(str(pfad))
    con.row_factory = sqlite3.Row
    try:
        for build, name, modulname in TEMPLATES_SCHRITTE:
            mod = importlib.import_module("management.%s" % modulname)
            try:
                # Alle fuenf nehmen 'con' zuerst; 'changed_by' kennen nicht
                # alle — deshalb erst mit, bei TypeError ohne.
                try:
                    res = mod.apply_migration(con, changed_by=changed_by)
                except TypeError:
                    res = mod.apply_migration(con)
                con.commit()
                meldungen.append("  Build %-4s %-32s %s"
                                 % (build, name, _kurz(res)))
            except Exception as exc:                        # noqa: BLE001
                con.rollback()
                meldungen.append("  Build %-4s %-32s FEHLER: %s"
                                 % (build, name, exc))
                raise
    finally:
        con.close()
    return meldungen


def fall_anwenden(pfad: Path, art: str) -> List[str]:
    """
    Wendet die Migrationen einer Fall-Datenbank an — ueber den vorhandenen
    MigrationRunner (Build 587).

    WARUM DIREKT UND NICHT UEBER DIE FLOTTEN-SCHICHT: die Flotte
    (migration_fleet_admin) fuehrt zusaetzlich Katalog, Inventar und ein
    Protokoll in einer eigenen Datei migration.db. Die ist auf dieser Anlage
    NIE in Betrieb genommen worden - weder existiert sie, noch steht
    paths.migration_db in der config.yaml. Ich habe in Build 586 trotzdem
    dorthin verwiesen; der Befehl brach ab, und mc stand vor einer Datei, von
    der er noch nie gehoert hatte. Das war mein Fehler.

    Massgeblich ist ohnehin nicht die Flotte, sondern das Register IN der
    jeweiligen Datenbank (schema_migrations) — so steht es im
    Datenmigrationsleitfaden: 'migration.db ist abgeleitet und
    rekonstruierbar (kein Single Point of Failure)'. Genau dieses Register
    schreibt der MigrationRunner. Wer spaeter die Flotte in Betrieb nimmt,
    kann ihren Stand daraus wiederherstellen.
    """
    from management.migrations.runner import MigrationRunner, discover
    paket = __import__("management.migrations.%s" % art, fromlist=["x"])
    module = discover(paket)

    con = sqlite3.connect(str(pfad))
    try:
        angewandt = MigrationRunner(con, module).run()
    finally:
        con.close()
    if not angewandt:
        return ["  %-22s nichts anzuwenden" % pfad.name]
    return ["  %-22s angewandt: %s"
            % (pfad.name, ", ".join("v%03d" % v for v in angewandt))]


def _kurz(res) -> str:
    if isinstance(res, dict):
        for schluessel in ("status", "result", "action"):
            if schluessel in res:
                return str(res[schluessel])
        return "ok" if res else "no-op"
    return "ok"


# -------------------------------------------------------------------- Bericht
def _zeile(name: str, angewandt, verfuegbar) -> str:
    offen = [v for v in verfuegbar if v not in set(angewandt)]
    stand = "aktuell" if not offen else ("OFFEN: " + ", ".join(map(str, offen)))
    return "  %-22s %3d von %3d   %s" % (name, len(angewandt),
                                         len(verfuegbar), stand)


def bericht(data_dir: Path, subject_id: Optional[int],
            nur: Optional[str]) -> Tuple[int, List[str], List[str]]:
    """
    -> (anzahl_offen, zeilen, offene_datenbanken)
    Reine Auskunft; schreibt nichts.
    """
    zeilen = ["Migrationsstand — %s" % data_dir, "=" * 66]
    offen_gesamt = 0
    offene_dbs: List[str] = []

    def betrifft(name: str) -> bool:
        return nur is None or nur == name

    # --- coordinator.db ---------------------------------------------------
    if betrifft("coordinator"):
        pfad = data_dir / "coordinator.db"
        if pfad.is_file():
            angewandt, fehler = _register_stand(pfad)
            verf = _verfuegbare_versionen("coordinator")
            zeilen.append(_zeile("coordinator.db", angewandt, verf))
            if fehler:
                zeilen.append("      Zugriff: %s" % fehler)
            elif [v for v in verf if v not in set(angewandt)]:
                offen_gesamt += 1
                offene_dbs.append("coordinator")
        else:
            zeilen.append("  %-22s nicht gefunden" % "coordinator.db")

    # --- templates.db -----------------------------------------------------
    if betrifft("templates"):
        pfad = data_dir / "templates.db"
        if pfad.is_file():
            stand = templates_stand(pfad)
            fehlend = [b for b, _, da in stand if not da]
            zeilen.append(_zeile("templates.db",
                                 [b for b, _, da in stand if da],
                                 [b for b, _, _ in stand]))
            for build, name, da in stand:
                zeilen.append("      [%s] Build %-4s %s"
                              % ("x" if da else " ", build, name))
            if fehlend:
                offen_gesamt += 1
                offene_dbs.append("templates")
        else:
            zeilen.append("  %-22s nicht gefunden" % "templates.db")

    # --- Fall-Datenbanken -------------------------------------------------
    if subject_id is not None:
        zeilen.append("-" * 66)
        zeilen.append("  Fall %s:" % subject_id)
        for art, unterordner, muster in (
            ("evidence", "evidence", "evidence_%s.db"),
            ("assets", "assets", "assets_%s.db"),
            ("forensic", "forensic", "forensic_%s.db"),
        ):
            if not betrifft(art):
                continue
            pfad = data_dir / unterordner / (muster % subject_id)
            if not pfad.is_file():
                zeilen.append("  %-22s nicht gefunden" % pfad.name)
                continue

            befund = fall_befund(pfad, art)

            # BUILD 586: die Lage wird BENANNT, nicht aus dem Register
            # erschlossen. 'Kein Eintrag' und 'keine Wirkung' sind zweierlei
            # und verlangen Verschiedenes.
            if art == "forensic":
                # Versiegelt: das Register laesst sich hier NIE anlegen, also
                # ist die fehlende Eintragung auch keine Luecke. Sonst meldete
                # das Werkzeug bis in alle Ewigkeit einen Notstand, den
                # niemand beheben darf.
                zeilen.append(
                    "  %-22s versiegelt — Register nicht moeglich, "
                    "keine Luecke" % pfad.name)
                continue

            if befund["lage"] == "aktuell":
                zeilen.append("  %-22s aktuell (%d eingetragen, alle "
                              "Wirkungen vorhanden)"
                              % (pfad.name, len(befund["eingetragen"])))
            elif befund["lage"] == "nur_eintrag_fehlt":
                zeilen.append(
                    "  %-22s WIRKUNGEN VORHANDEN, nur der Registereintrag "
                    "fehlt" % pfad.name)
                zeilen.append("      Kein Notstand — ein Nachtrag. "
                              "Die Migrationen sind sachlich erledigt.")
                offen_gesamt += 1
                offene_dbs.append(art)
            else:
                zeilen.append("  %-22s WIRKUNG FEHLT fuer Version(en): %s"
                              % (pfad.name,
                                 ", ".join(map(str, befund["fachlich_fehlt"]))))
                for v in befund["fachlich_fehlt"]:
                    zeilen.append("      fehlt: %s '%s'"
                                  % SPUREN[art][v])
                offen_gesamt += 1
                offene_dbs.append(art)

    # --- Prepper-Erzeugnisse: genannt, nicht bewertet ---------------------
    zeilen.append("-" * 66)
    for name in FREMDE_DBS:
        pfad = data_dir / ("%s.db" % name)
        zeilen.append("  %-22s %s (Prepper-Erzeugnis — hier nicht bewertet)"
                      % (pfad.name, "vorhanden" if pfad.is_file() else "fehlt"))

    zeilen.append("=" * 66)
    zeilen.append("Alles aktuell." if not offen_gesamt
                  else "OFFEN in %d Datenbank(en): %s"
                       % (offen_gesamt, ", ".join(offene_dbs)))
    return (offen_gesamt, zeilen, offene_dbs)


# ----------------------------------------------------------------------- main
def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Migrationsstand aller Datenbanken pruefen und anwenden.")
    p.add_argument("--data-dir", default="./data")
    p.add_argument("--db", choices=("coordinator", "templates", "evidence",
                                    "assets", "forensic"),
                   help="Nur diese Datenbank betrachten.")
    p.add_argument("--subject-id", type=int,
                   help="Fall-Datenbanken dieses Falls mitpruefen.")
    p.add_argument("--apply", action="store_true",
                   help="SCHARFSCHALTEN: Migrationen wirklich anwenden.")
    p.add_argument("--no-backup", action="store_true",
                   help="Keine Sicherung anlegen (nur mit --apply sinnvoll).")
    p.add_argument("--changed-by", default=os.environ.get("USER", "system"))
    args = p.parse_args(argv)

    data_dir = Path(args.data_dir).resolve()
    if not data_dir.is_dir():
        print("Datenverzeichnis nicht gefunden: %s" % data_dir,
              file=sys.stderr)
        return 2

    offen, zeilen, offene_dbs = bericht(data_dir, args.subject_id, args.db)
    print("\n".join(zeilen))

    if not args.apply:
        print()
        if offen:
            print("TROCKENUEBUNG — es wurde nichts geschrieben.")
            print("Zum Anwenden: %s --apply%s"
                  % (" ".join(sys.argv), ""))
        return 1 if offen else 0

    if not offen:
        print()
        print("Nichts anzuwenden.")
        return 0

    # --- WARTUNGSVORBEHALT (Stufe A, Build 612) --------------------------
    # Das Werkzeug baut Tabellen um (Rebuild) und schreibt dabei in
    # templates.db sowie in die Fall-Datenbanken evidence_<uid>.db und
    # assets_<uid>.db — Letztere stehen seit dem 01.07.2026 unter dem
    # Migrationsvorbehalt. Es sichert zwar vorher (ausser bei --no-backup),
    # aber es SPIELT NICHTS ZURUECK: nach einem Abbruch liegt die Sicherung
    # da und muss von Hand eingesetzt werden.
    #
    # GEPRUEFT WIRD NUR, WAS DIESER LAUF WIRKLICH ANFASST. Der Bericht oben
    # hat bereits ermittelt, welche Datenbanken offen sind; coordinator und
    # forensic wendet dieses Werkzeug ausdruecklich NICHT selbst an, also
    # gehoeren sie hier auch nicht in die Pruefung. Eine Pruefung, die mehr
    # meldet, als der Lauf anfasst, erzeugt Fehlalarme — und Fehlalarme
    # bringen genau die Gewoehnung hervor, gegen die der Vorbehalt gebaut ist.
    betroffen = []
    if "templates" in offene_dbs:
        betroffen.append(data_dir / "templates.db")
    for art in ("evidence", "assets"):
        if art in offene_dbs:
            pfad = data_dir / art / ("%s_%s.db" % (art, args.subject_id))
            if pfad.is_file():
                betroffen.append(pfad)
    if betroffen:
        befund = wartungsvorbehalt(
            data_dir, betroffen, werkzeug="migrate-dbs",
            was_geschieht="wendet ausstehende Migrationen an und baut dabei "
                          "Tabellen um. Eine Sicherung wird angelegt%s, aber "
                          "nach einem Abbruch NICHT von selbst "
                          "zurueckgespielt."
                          % (" NICHT (--no-backup)" if args.no_backup else ""))
        print(befund.text)
        if not befund.erlaubt:
            return befund.rueckgabewert

    # ------------------------------------------------------------- anwenden
    print()
    print("SCHARFGESCHALTET — wende an:")
    fehler = 0
    if "templates" in offene_dbs:
        pfad = data_dir / "templates.db"
        if not args.no_backup:
            print("  Sicherung: %s" % sicherung(pfad).name)
        try:
            for zeile in templates_anwenden(pfad, args.changed_by):
                print(zeile)
        except Exception as exc:                            # noqa: BLE001
            print("  ABGEBROCHEN: %s" % exc, file=sys.stderr)
            fehler += 1

    # --- Fall-Datenbanken: direkt ueber den MigrationRunner ---------------
    for art in ("evidence", "assets"):
        if art not in offene_dbs:
            continue
        pfad = data_dir / art / ("%s_%s.db" % (art, args.subject_id))
        if not pfad.is_file():
            continue
        if not args.no_backup:
            print("  Sicherung: %s" % sicherung(pfad).name)
        try:
            for zeile in fall_anwenden(pfad, art):
                print(zeile)
        except Exception as exc:                            # noqa: BLE001
            print("  ABGEBROCHEN (%s): %s" % (pfad.name, exc),
                  file=sys.stderr)
            fehler += 1

    andere = [d for d in offene_dbs if d not in ("templates", "evidence",
                                                 "assets")]
    if andere:
        print()
        print("  Fuer %s ist ein eigener Weg zustaendig (er fuehrt das "
              "Register und den Beleg). Dieses Werkzeug wendet dort NICHT "
              "selbst an — zwei Wege, die dasselbe schreiben, waeren zwei "
              "Wahrheiten ueber den Beleg." % ", ".join(andere))
        for art in andere:
            vorlage = BEFEHL.get(art)
            if not vorlage:
                continue
            if art == "coordinator":
                befehl = vorlage.replace("<KENNUNG>", args.changed_by)
            else:
                unterordner = art
                pfad = (data_dir / unterordner
                        / ("%s_%s.db" % (art, args.subject_id)))
                befehl = vorlage.format(pfad=pfad, uid=args.subject_id)
            print()
            print("  # %s" % art)
            print("    %s" % befehl)
            if art != "coordinator":
                print("    (ohne --confirm ist es eine Vorpruefung mit Plan; "
                      "zum Ausfuehren --confirm --backup-dir <PFAD> "
                      "--operator %s)" % args.changed_by)

    if fehler:
        return 2

    # NACHPRUEFEN statt behaupten: nach dem Anwenden wird der Stand erneut
    # erhoben. Nur wenn er wirklich vollstaendig ist, meldet das Werkzeug
    # Erfolg (0). Ein 'ich habe etwas getan' ist keine Zusicherung, dass es
    # gewirkt hat.
    print()
    rest, zeilen2, _ = bericht(data_dir, args.subject_id, args.db)
    print("Stand danach:")
    print("\n".join(zeilen2[-1:]))
    if rest:
        print()
        print("ES BLEIBT ETWAS OFFEN — bitte die Meldungen oben lesen.")
    return 1 if rest else 0


if __name__ == "__main__":
    raise SystemExit(main())
