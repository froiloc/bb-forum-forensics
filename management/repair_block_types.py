# =============================================================================
# management/repair_block_types.py
# IT-Forensisches Ermittlungswerkzeug — Datenreparatur (Build 392)
# =============================================================================
# ZWECK
#   Stellt block_type-Werte wieder her, die durch den Fehler aus Build 388/389
#   (behoben in Build 392) still auf 'paragraph' zurueckgesetzt wurden.
#
# DER FEHLER
#   forensic_api/report.py::_action_save_block setzte block_type auf
#   'paragraph', wenn der Aufrufer keinen Typ mitsendete — AUCH bei einem
#   bereits bestehenden Block. Zwei Aufrufer senden bewusst keinen Typ, weil
#   sie nur Werte nachtragen:
#     report_editor.js:753   _resolveAutoPlaceholders()  ({{a:}}-Werte)
#     report_editor.js:2058  _onPlaceholderFieldSave()   (Formularwert)
#   Ein TABLE-Block wurde dadurch in report_blocks auf 'paragraph' umgeschrieben.
#   Beim naechsten Laden verschwand die Tabelle aus der Darstellung.
#
# WICHTIG — WAS NICHT VERLOREN IST
#   Der INHALT blieb erhalten: block_data enthaelt weiterhin die Tabelle
#   ({"withHeadings": ..., "content": [[...]]}). Nur die TYPANGABE ging
#   verloren. Deshalb ist die Reparatur verlustfrei und eindeutig: ein echter
#   paragraph-Block hat NIE ein 'content'-Feld mit einem Zeilen-Array.
#
# VORGEHEN (GRUNDREGEL 1 — nichts still tun)
#   - Standard ist DRY-RUN. Geschrieben wird nur mit --apply.
#   - Jeder Fund wird einzeln benannt (Datenbank, report_id, block_id, Grund).
#   - Zweifelsfaelle werden NICHT angefasst, sondern als UNKLAR gemeldet.
#   - Vor --apply MUSS ein verifiziertes Backup der evidence_*.db bestehen
#     (Datenmigrationsleitfaden). Das Skript weist darauf hin und verlangt
#     eine ausdrueckliche Bestaetigung.
#
# AUFRUF
#   python -m management.repair_block_types --config ./config.yaml
#   python -m management.repair_block_types --config ./config.yaml --apply
#   python -m management.repair_block_types --evidence-dir ./data/evidence/
#
# Beleg: Bugbefund Projektgespraech 2026-07-12, Bauplan Build 392
# Version: v0.7.392 · Build: 392 · 2026-07-12
# =============================================================================

from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
import time
from management.help import cli_epilog  # noqa: E402
# Build 646: Vorrangregel an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


# =============================================================================
# Erkennung
# =============================================================================

def classify(block_type: str, block_data_raw: str) -> tuple[str, str]:
    """
    Entscheidet, ob ein Block vom Fehler betroffen ist.

    Returns:
        (befund, begruendung)
        befund ist einer von:
          'ok'      -- unauffaellig, nichts zu tun
          'table'   -- war eine Tabelle, muss auf 'table' zurueck
          'list'    -- war eine Liste, muss auf 'list' zurueck
          'unklar'  -- verdaechtig, aber NICHT eindeutig -> nicht anfassen

    Die Regeln sind bewusst ENG. Lieber ein Block bleibt unrepariert und wird
    gemeldet, als dass ein unbeteiligter Block umgeschrieben wird.
    """
    if block_type != "paragraph":
        # Nur 'paragraph' kann das Ergebnis des Fehlers sein.
        return ("ok", "")

    try:
        data = json.loads(block_data_raw or "{}")
    except json.JSONDecodeError:
        return ("unklar", "block_data ist kein gueltiges JSON")

    if not isinstance(data, dict):
        return ("unklar", "block_data ist kein Objekt")

    has_text    = isinstance(data.get("text"), str) and data["text"].strip() != ""
    content     = data.get("content")
    items       = data.get("items")
    has_heading = "withHeadings" in data

    # --- Tabelle -------------------------------------------------------
    # Editor.js-Table: {"withHeadings": bool, "content": [[zelle, ...], ...]}
    is_table_shape = (
        isinstance(content, list)
        and len(content) > 0
        and all(isinstance(row, list) for row in content)
    )
    if is_table_shape:
        if has_text:
            # Ein Block mit BEIDEM waere ein Widerspruch — nicht raten.
            return ("unklar",
                    "hat sowohl 'text' als auch ein Tabellen-'content'")
        return ("table",
                "content ist ein Zeilen-Array (%d Zeilen)%s"
                % (len(content), ", withHeadings vorhanden" if has_heading else ""))

    # --- Liste ---------------------------------------------------------
    # Editor.js-List: {"style": "unordered", "items": [...]}
    if isinstance(items, list) and len(items) > 0:
        if has_text:
            return ("unklar", "hat sowohl 'text' als auch 'items'")
        return ("list", "items-Array vorhanden (%d Eintraege)" % len(items))

    # --- Unauffaellig ---------------------------------------------------
    return ("ok", "")


# =============================================================================
# Durchlauf je Datenbank
# =============================================================================

def scan_db(db_path: str) -> list[dict]:
    """Untersucht EINE evidence_<uid>.db. Schreibt nichts."""
    funde: list[dict] = []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        try:
            rows = con.execute(
                "SELECT block_id, report_id, block_type, block_data "
                "FROM report_blocks"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            print("  ! Tabelle report_blocks nicht lesbar: %s" % exc)
            return funde

        for row in rows:
            befund, grund = classify(row["block_type"], row["block_data"])
            if befund == "ok":
                continue
            funde.append({
                "db":         db_path,
                "block_id":   row["block_id"],
                "report_id":  row["report_id"],
                "ist":        row["block_type"],
                "soll":       befund if befund != "unklar" else None,
                "befund":     befund,
                "grund":      grund,
            })
    finally:
        con.close()
    return funde


def repair_db(db_path: str, funde: list[dict]) -> int:
    """Schreibt die eindeutigen Korrekturen EINER Datenbank (Transaktion)."""
    reparabel = [f for f in funde if f["befund"] in ("table", "list")]
    if not reparabel:
        return 0

    con = sqlite3.connect(db_path)
    try:
        now = int(time.time())
        for f in reparabel:
            con.execute(
                "UPDATE report_blocks SET block_type = ?, updated_at = ? "
                "WHERE block_id = ?",
                (f["soll"], now, f["block_id"]),
            )
        con.commit()
    except Exception:
        con.rollback()
        print("  ! FEHLER — Aenderungen an %s wurden ZURUECKGEROLLT." % db_path)
        raise
    finally:
        con.close()
    return len(reparabel)


# =============================================================================
# CLI
# =============================================================================

def _resolve_evidence_dir(args) -> str:
    """
    Verzeichnis der evidence_<uid>.db: Argument --evidence-dir > paths.evidence_db_dir > Abbruch.

    BUILD 646 - UMGESTELLT, UND DIE BEGRUENDUNG DAFUER GEHOERT HIERHER.
    Bis Build 645 las diese Funktion die config.yaml UNMITTELBAR mit
    'yaml.safe_load', am ConfigLoader vorbei. Der Kommentar nannte als Grund,
    das Skript ohne den Paket-Import lauffaehig zu halten.

    DIESER GRUND TRAEGT NICHT MEHR: Seit dem Rollout des Epilogs (Build 624)
    importiert diese Datei ohnehin 'management.help.cli_epilog' - sie laeuft
    also schon lange nicht mehr ohne das Paket. Die Sonderbehandlung war
    damit eine Abweichung ohne Nutzen, aber mit Preis: zwei Wege, dieselbe
    Frage zu beantworten.

    WAS SICH NICHT AENDERT - und das war die Sorge bei dieser Umstellung:
    Der Abbruch bei fehlendem Eintrag BLEIBT. Die Coded Defaults des
    ConfigLoaders greifen hier NICHT durch, weil die Aufloesung ueber
    'stammt_aus_datei' geht und nicht ueber 'get': Es zaehlt nur, was in der
    DATEI steht. Ein Werkzeug, das den Bestand veraendert, darf nicht
    stillschweigend auf './data/...' ausweichen.

    WAS BESSER WIRD: Eine fehlende config.yaml fuehrte bisher zu einem
    FileNotFoundError mitsamt Rueckverfolgung; jetzt ist es ein Abbruch mit
    Klartext, der beide Wege nennt.
    """
    return werkzeug_konfig.db_pfad(
        "repair_block_types", args, arg_attribut="evidence_dir", arg_name="--evidence-dir",
        config_schluessel="paths.evidence_db_dir", name="evidence_dir")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build 392: verlorene block_type-Werte wiederherstellen.",
        epilog=cli_epilog.epilog("repair_block_types"),
        formatter_class=cli_epilog.HilfeFormat,
    )
    parser.add_argument("--evidence-dir", default=None,
                        help="Verzeichnis mit den evidence_<uid>.db")
    parser.add_argument("--config", default="./config.yaml",
                        help="config.yaml (wenn --evidence-dir fehlt)")
    parser.add_argument("--apply", action="store_true",
                        help="Aenderungen tatsaechlich schreiben "
                             "(ohne dies: reiner Trockenlauf)")
    parser.add_argument("--ja-backup-vorhanden", action="store_true",
                        help="Bestaetigt, dass ein verifiziertes Backup der "
                             "evidence-Datenbanken vorliegt. Fuer --apply Pflicht.")
    args = parser.parse_args(argv)

    ev_dir = _resolve_evidence_dir(args)
    if not os.path.isdir(ev_dir):
        print("FEHLER: Verzeichnis nicht gefunden: %s" % ev_dir, file=sys.stderr)
        return 2

    if args.apply and not args.ja_backup_vorhanden:
        print(
            "ABBRUCH: --apply veraendert Ermittlerdaten in den evidence-Daten"
            "banken.\n"
            "         Legen Sie zuerst ein verifiziertes Backup an und wieder"
            "holen Sie\n"
            "         den Aufruf mit --ja-backup-vorhanden.",
            file=sys.stderr,
        )
        return 3

    dbs = sorted(glob.glob(os.path.join(ev_dir, "evidence_*.db")))
    if not dbs:
        print("Keine evidence_*.db in %s gefunden." % ev_dir)
        return 0

    print("Modus: %s" % ("SCHREIBEN (--apply)" if args.apply else "TROCKENLAUF"))
    print("Untersuche %d Datenbank(en) in %s\n" % (len(dbs), ev_dir))

    gesamt_funde: list[dict] = []
    gesamt_repariert = 0

    for db in dbs:
        print("- %s" % os.path.basename(db))
        funde = scan_db(db)
        gesamt_funde.extend(funde)

        if not funde:
            print("    unauffaellig.")
            continue

        for f in funde:
            if f["befund"] == "unklar":
                # GRUNDREGEL 1: melden, nicht anfassen.
                print("    ? UNKLAR  report_id=%s block_id=%s — %s"
                      % (f["report_id"], f["block_id"], f["grund"]))
            else:
                print("    ! DEFEKT  report_id=%s block_id=%s: '%s' -> '%s' (%s)"
                      % (f["report_id"], f["block_id"], f["ist"], f["soll"],
                         f["grund"]))

        if args.apply:
            n = repair_db(db, funde)
            gesamt_repariert += n
            print("    -> %d Block/Bloecke wiederhergestellt." % n)

    # --- Zusammenfassung ---------------------------------------------------
    defekt = [f for f in gesamt_funde if f["befund"] in ("table", "list")]
    unklar = [f for f in gesamt_funde if f["befund"] == "unklar"]

    print("\n" + "=" * 60)
    print("  Zusammenfassung")
    print("=" * 60)
    print("  Eindeutig defekt : %d" % len(defekt))
    print("  Unklar (nicht angefasst) : %d" % len(unklar))
    if args.apply:
        print("  Wiederhergestellt : %d" % gesamt_repariert)
    else:
        print("\n  TROCKENLAUF — es wurde NICHTS geaendert.")
        if defekt:
            print("  Zum Schreiben: --apply --ja-backup-vorhanden")
    if unklar:
        print("\n  ACHTUNG: %d Block/Bloecke sind verdaechtig, aber nicht "
              "eindeutig\n  zuzuordnen. Sie wurden NICHT veraendert und "
              "muessen von Hand\n  geprueft werden (siehe Liste oben)." % len(unklar))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
