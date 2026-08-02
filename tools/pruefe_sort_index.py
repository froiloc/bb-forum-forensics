#!/usr/bin/env python3
# =============================================================================
# tools/pruefe_sort_index.py
# IT-Forensisches Ermittlungswerkzeug — Voruntersuchung zu Migration M004
# =============================================================================
# Zweck (Build 660, Vorgang 99bf0eb5):
#   SCHREIBFREI feststellen, was M004 auf dieser Anlage vorfinden wird, BEVOR
#   irgendjemand 'migrate-dbs.py --apply' aufruft. Es beantwortet je
#   evidence_<uid>.db drei Fragen:
#
#     (1) Welchen Typ traegt 'report_block_order.sort_index' — TEXT oder
#         INTEGER? Nur TEXT-Dateien werden von M004 angefasst.
#     (2) Sind alle Werte kanonische Ganzzahlen? Nicht kanonische werden von
#         M004 per CAST uebernommen (Festlegung mc 2026-08-02) — wer das
#         verantwortet, soll es VORHER wissen und nicht hinterher im
#         Protokoll lesen.
#     (3) AENDERT SICH DIE REIHENFOLGE UEBERHAUPT? Bei weniger als zehn
#         Bausteinen sind lexikographische und numerische Ordnung oft gleich.
#         Diese Datei ist zwar zu migrieren, aber ihre Vermerke waren nie
#         falsch. Der Unterschied entscheidet, ob eine Nachschau an bereits
#         gefertigten Vermerken noetig ist.
#
#   Beleg zur Sache: Migration M004 im Modulkopf
#   (management/migrations/evidence/m004_sort_index_integer.py).
#
# ── WARUM DIESES WERKZEUG UND NICHT DIE TROCKENUEBUNG VON migrate-dbs.py ────
#
#   migrate-dbs.py sagt, WELCHE Migrationen offen sind. Es sagt nichts
#   darueber, WAS sie vorfinden werden. Fuer eine additive Migration ist das
#   gleichgueltig; fuer eine destruktive an einem Beweismittel nicht. Der
#   Leitfaden nennt das Phase 0 — Trockenlauf mit Erwartungswert-Abgleich, vor
#   der ersten Produktivdatei.
#
# ── ES AENDERT NICHTS ───────────────────────────────────────────────────────
#
#   Jede Datei wird ausschliesslich 'mode=ro' geoeffnet. Es gibt keinen
#   Schreibpfad in diesem Werkzeug. Damit ist der Aufruf auch auf der Anlage
#   im Produktivbetrieb unbedenklich und beruehrt den Migrationsvorbehalt nicht.
#
# ── EINE DATEI, DIE NICHT LESBAR IST, WIRD GENANNT ──────────────────────────
#
#   Grundregel 1. Eine uebersprungene Datei ist von einer geprueften nicht zu
#   unterscheiden, wenn beide gleich aussehen — deshalb hat 'unlesbar' eine
#   eigene Zeile, eine eigene Zahl in der Zusammenfassung und einen eigenen
#   Rueckgabewert.
#
# ── EXIT-CODES (fuer das Betriebsskript) ────────────────────────────────────
#     0 — nichts zu tun: keine Datei traegt TEXT.
#     1 — Aufruffehler (Verzeichnis fehlt, Muster falsch).
#     2 — MIGRATION NOETIG, und sie ist unauffaellig: alle Werte kanonisch.
#     3 — MIGRATION NOETIG, ABER MIT BEFUND: mindestens ein Wert ist keine
#         kanonische Ganzzahl. EIGENER Code, weil 'zu migrieren' und 'zu
#         migrieren, aber jemand muss hinsehen' im Skript nicht gleich
#         aussehen duerfen.
#     4 — Mindestens eine Datei war nicht lesbar. Der Befund der uebrigen
#         bleibt gueltig, ist aber unvollstaendig — und das ist zu wissen.
#
# Version: v0.8.660 · Build: 660 · 2026-08-02
# =============================================================================

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog  # noqa: E402

#: Kanonische Ganzzahlform — deckungsgleich mit M004._KANONISCH. Die beiden
#  Ausdruecke MUESSEN uebereinstimmen; der Regressionsfall PS07 haelt sie
#  gegeneinander, damit die Voruntersuchung nicht etwas anderes prueft, als
#  die Migration spaeter tut.
_KANONISCH = re.compile(r"^(0|-?[1-9][0-9]*)$")

#: Die kanonische Form des Dateinamens — GENAU EINE Zahl. Uebernommen aus
#  management/db_katalog.py (Build 658): 'evidence_<uid>_<...>.db' sind
#  Transportdateien des Cross-Annotation-Integrators bzw. Addendum-Dateien der
#  Kommentar-Bruecke und KEINE Falldatenbanken.
_DATEI_MUSTER = re.compile(r"^evidence_\d+\.db$")


def _befund_einer_datei(pfad: Path) -> dict:
    """
    Erhebt den Zustand EINER Falldatenbank. Rein lesend.

    -> {"datei", "lage", "typ", "zeilen", "zweifel":[...], "ordnung_aendert_sich"}
       lage: 'ok' | 'zu_migrieren' | 'ohne_tabelle' | 'unlesbar'
    """
    ergebnis = {"datei": pfad.name, "lage": "unlesbar", "typ": None,
                "zeilen": 0, "zweifel": [], "ordnung_aendert_sich": None,
                "detail": ""}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % pfad.resolve(), uri=True)
    except sqlite3.Error as exc:
        ergebnis["detail"] = str(exc)
        return ergebnis
    try:
        vorhanden = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND "
            "name='report_block_order'").fetchone()
        if vorhanden is None:
            ergebnis["lage"] = "ohne_tabelle"
            ergebnis["detail"] = ("report_block_order fehlt - beide "
                                  "Schema-Quellen legen sie an.")
            return ergebnis

        typ = None
        for r in con.execute('PRAGMA table_info("report_block_order")'):
            if r[1] == "sort_index":
                typ = (r[2] or "").upper()
        ergebnis["typ"] = typ

        zeilen = con.execute(
            "SELECT block_id, sort_index, CAST(sort_index AS INTEGER) "
            "FROM report_block_order").fetchall()
        ergebnis["zeilen"] = len(zeilen)

        if typ != "TEXT":
            # Bereits INTEGER (oder ein unerwarteter Typ, den M004 zurueckweist).
            ergebnis["lage"] = "ok"
            return ergebnis

        ergebnis["lage"] = "zu_migrieren"
        for block_id, roh, ziel in zeilen:
            if not _KANONISCH.match(str(roh if roh is not None else "")):
                ergebnis["zweifel"].append({
                    "block_id": str(block_id),
                    "roh": (None if roh is None else str(roh)),
                    "wuerde_werden": int(ziel)})

        # AENDERT SICH DIE REIHENFOLGE? Verglichen wird die heutige
        # (lexikographische) mit der kuenftigen (numerischen) Ausgabefolge —
        # und zwar ueber DENSELBEN Ausdruck, den get_blocks_for_report
        # benutzt (db/evidence_db.py:1819), damit hier nicht etwas anderes
        # gemessen wird als der Server spaeter tut.
        heute = [r[0] for r in con.execute(
            "SELECT rb.block_id FROM report_blocks rb "
            "LEFT JOIN report_block_order rbo ON rbo.block_id = rb.block_id "
            "ORDER BY COALESCE(rbo.sort_index, 999999) ASC, rb.created_at ASC")]
        kuenftig = [r[0] for r in con.execute(
            "SELECT rb.block_id FROM report_blocks rb "
            "LEFT JOIN report_block_order rbo ON rbo.block_id = rb.block_id "
            "ORDER BY COALESCE(CAST(rbo.sort_index AS INTEGER), 999999) ASC, "
            "         rb.created_at ASC")]
        ergebnis["ordnung_aendert_sich"] = (heute != kuenftig)
        return ergebnis
    except sqlite3.Error as exc:
        ergebnis["lage"] = "unlesbar"
        ergebnis["detail"] = str(exc)
        return ergebnis
    finally:
        con.close()


def erhebe(verzeichnis: Path) -> dict:
    """Erhebt alle Falldatenbanken eines Verzeichnisses (nicht rekursiv)."""
    dateien, uebergangen = [], []
    for p in sorted(verzeichnis.glob("*.db")):
        (dateien if _DATEI_MUSTER.match(p.name) else uebergangen).append(p)
    befunde = [_befund_einer_datei(p) for p in dateien]
    return {"verzeichnis": str(verzeichnis), "befunde": befunde,
            # GR1: was nicht betrachtet wurde, wird GENANNT und nicht
            # weggelassen (Lehre aus Build 657/658).
            "uebergangen": [p.name for p in uebergangen]}


def _ausgabe_text(erhebung: dict) -> str:
    zeilen = ["Voruntersuchung zu M004 - report_block_order.sort_index",
              "Verzeichnis: %s" % erhebung["verzeichnis"], ""]
    zu_migrieren = mit_befund = unlesbar = ohne_tabelle = ordnung_falsch = 0
    for b in erhebung["befunde"]:
        marke = {"ok": "  ", "zu_migrieren": "->", "ohne_tabelle": "!!",
                 "unlesbar": "!!"}[b["lage"]]
        text = "%s %-24s Typ=%-8s Zeilen=%-5d" % (
            marke, b["datei"], b["typ"] or "?", b["zeilen"])
        if b["lage"] == "zu_migrieren":
            zu_migrieren += 1
            text += " zu migrieren"
            if b["ordnung_aendert_sich"]:
                ordnung_falsch += 1
                text += "; REIHENFOLGE AENDERT SICH"
            else:
                text += "; Reihenfolge unveraendert"
            if b["zweifel"]:
                mit_befund += 1
                text += "; %d ZWEIFELSFALL/-FAELLE" % len(b["zweifel"])
        elif b["lage"] == "ok":
            text += " nichts zu tun"
        else:
            if b["lage"] == "unlesbar":
                unlesbar += 1
            else:
                ohne_tabelle += 1
            text += " %s: %s" % (b["lage"].upper(), b["detail"])
        zeilen.append(text)
        for z in b["zweifel"]:
            zeilen.append("       block_id=%s Wert=%r -> wuerde %d"
                          % (z["block_id"], z["roh"], z["wuerde_werden"]))

    zeilen += ["", "Zusammenfassung:",
               "  %d Falldatenbank(en) betrachtet" % len(erhebung["befunde"]),
               "  %d zu migrieren" % zu_migrieren,
               "  %d davon mit geaenderter Reihenfolge (bereits gefertigte "
               "Vermerke pruefen!)" % ordnung_falsch,
               "  %d davon mit Zweifelsfaellen" % mit_befund,
               "  %d ohne report_block_order" % ohne_tabelle,
               "  %d nicht lesbar" % unlesbar]
    if erhebung["uebergangen"]:
        zeilen.append("  %d weitere Datei(en) tragen nicht die Form "
                      "evidence_<uid>.db und sind uebergangen worden: %s"
                      % (len(erhebung["uebergangen"]),
                         ", ".join(erhebung["uebergangen"][:8])
                         + (" ..." if len(erhebung["uebergangen"]) > 8 else "")))
    return "\n".join(zeilen)


def _exit_code(erhebung: dict) -> int:
    unlesbar = any(b["lage"] == "unlesbar" for b in erhebung["befunde"])
    zweifel = any(b["zweifel"] for b in erhebung["befunde"])
    zu_migrieren = any(b["lage"] == "zu_migrieren" for b in erhebung["befunde"])
    # Reihenfolge der Prueflinge = Reihenfolge der Dringlichkeit. Ein
    # unvollstaendiger Befund schlaegt jeden vollstaendigen.
    if unlesbar:
        return 4
    if zweifel:
        return 3
    if zu_migrieren:
        return 2
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Schreibfreie Voruntersuchung zu Migration M004 "
                    "(report_block_order.sort_index TEXT -> INTEGER).",
        epilog=cli_epilog.epilog("pruefe_sort_index"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--dir", default="data/evidence",
                   help="Verzeichnis der Falldatenbanken "
                        "(Vorgabe: data/evidence)")
    p.add_argument("--json", action="store_true",
                   help="Ausgabe als JSON statt als Text")
    args = p.parse_args(argv)

    verzeichnis = Path(args.dir)
    if not verzeichnis.is_dir():
        print("FEHLER: Verzeichnis nicht gefunden: %s" % verzeichnis,
              file=sys.stderr)
        return 1

    erhebung = erhebe(verzeichnis)
    if args.json:
        print(json.dumps(erhebung, indent=2, ensure_ascii=False))
    else:
        print(_ausgabe_text(erhebung))
    return _exit_code(erhebung)


if __name__ == "__main__":
    sys.exit(main())
