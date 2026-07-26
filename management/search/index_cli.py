# =============================================================================
# management/search/index_cli.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B560)
# =============================================================================
# Zweck:
#   Befehlszeile fuer den Suchindex — die EINZIGE Stelle, an der im Build 560
#   ein Indexlauf ausgeloest werden kann.
#
#   Aufruf (aus dem Projektverzeichnis):
#     python -m management.search.index_cli --status
#     python -m management.search.index_cli --auffrischen
#     python -m management.search.index_cli --auffrischen --voll
#     python -m management.search.index_cli --auffrischen --nur 4711,5023
#     python -m management.search.index_cli --status --json
#
# ── WARUM DAS EIN EIGENES WERKZEUG IST UND KEIN SERVER-ENDPUNKT ─────────────
#
#   Entscheidung mc 2026-07-26: "Nur ausdruecklich, inkrementell." Der Lauf ist
#   ein BETRIEBLICHER Vorgang mit messbaren Kosten auf dem Netzlaufwerk
#   (Faktor rund 24 gegenueber DEV, Messung 2026-07-25) — er gehoert in die
#   Hand derjenigen, die die Anlage betreiben. Ein Knopf in der Sicht kommt in
#   Build 563 hinzu und ruft denselben Bauer auf; bis dahin gibt es genau EINEN
#   Weg, und der laesst sich in der Betriebsakte belegen.
#
#   KEIN AUDIT-EINTRAG IN DIESEM BUILD, UND DAS IST BEGRUENDET: Der Indexlauf
#   liest ausschliesslich mit 'mode=ro' und schreibt ausschliesslich in ein
#   Hilfsmittel. Er ist keine ERMITTLUNGSHANDLUNG — die Handlung ist die
#   ABFRAGE, und die bekommt in Build 562 ihren Beleg
#   (EventType FULLTEXT_SEARCHED, auch beim Leerbefund). Einen Beleg fuer den
#   Indexlauf zu schreiben, waere nicht falsch, aber es waere ein Beleg in
#   coordinator.db fuer einen Vorgang, der dort nichts anfasst — und jeder
#   Eintrag, der nichts belegt, verwaessert die Kette.
#
# ── EXIT-CODES (fuer den Betrieb skriptbar) ─────────────────────────────────
#     0 — Lauf/Status in Ordnung, nichts unvollstaendig.
#     1 — Aufruf- oder Konfigurationsfehler (Index nicht benutzbar).
#     2 — Lauf gefahren, ABER mindestens ein Fall ist unvollstaendig
#         (nicht lesbar / nicht oeffenbar / Tabellen fehlen / Datei fehlt),
#         oder der Status weist Unvollstaendiges aus.
#   Der eigene Code 2 ist Absicht: 'gelaufen, aber nicht vollstaendig' darf im
#   Betriebsskript nicht wie 'gelaufen' aussehen (Grundregel 1).
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# Aufruf als Skript (python management/search/index_cli.py) moeglich machen —
# ohne das findet der Import 'db.search_index_db' das Projektwurzelverzeichnis
# nicht. Bei 'python -m management.search.index_cli' ist es schon gesetzt.
if __package__ in (None, ""):  # pragma: no cover — nur beim Direktaufruf
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from db.search_index_db import SearchIndexDb, SearchIndexFehler  # noqa: E402
from management.search.index_builder import SearchIndexBuilder  # noqa: E402
from management.search.index_status import SearchIndexStatus  # noqa: E402

logger = logging.getLogger("management.search.index_cli")

#: Standardablage des Index. NEBEN den Beweismitteldatenbanken, nicht darin —
#  search_index.db ist ein Hilfsmittel und darf jederzeit geloescht werden.
STANDARD_INDEX_PFAD = "./data/search_index.db"


def _evidence_dir_aus_config() -> str:
    """
    paths.evidence_db_dir aus config.yaml (Muster
    management/server/management_app.py:649-660).

    Faellt die Konfiguration aus, wird der Standard benutzt UND der Fehler
    protokolliert — kein stilles Verschlucken (Grundregel 1).
    """
    try:
        from core.config_loader import ConfigLoader
        return str(ConfigLoader().get("paths.evidence_db_dir"))
    except Exception as exc:  # pragma: no cover — Konfig-Ausfall
        logger.warning("evidence_db_dir nicht aus config.yaml lesbar (%s) — "
                       "Standard './data/evidence/'.", exc)
        return "./data/evidence/"


def _zeit(ts: Optional[object]) -> str:
    """Unix-Sekunden als lesbare Ortszeit; None -> '—'."""
    if ts in (None, ""):
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
    except (ValueError, TypeError, OSError):
        return str(ts)


def _nur_liste(roh: Optional[str]) -> Optional[List[int]]:
    """'4711,5023' -> [4711, 5023]. Ein unsinniger Eintrag ist ein Fehler."""
    if not roh:
        return None
    aus: List[int] = []
    for teil in str(roh).split(","):
        teil = teil.strip()
        if not teil:
            continue
        if not teil.isdigit():
            raise ValueError("--nur erwartet subject_ids (Ziffern), "
                             "gefunden: %r" % teil)
        aus.append(int(teil))
    return aus or None


def _drucke_status(st: Dict[str, object]) -> None:
    """Statusbericht im Klartext."""
    print("Suchindex — Stand")
    print("  Indexdatei ............ %s" % st["index_pfad"])
    print("  evidence-Verzeichnis .. %s%s" % (
        st["verzeichnis"],
        "" if st["verzeichnis_vorhanden"]
        else "   *** NICHT VORHANDEN — es wurde NICHT nachgesehen ***"))
    print("  Index erzeugt ......... %s" % _zeit(st["index_erzeugt_at"]))
    print("  letzter Lauf .......... %s (%s)" % (
        _zeit(st["letzter_lauf_at"]), st["letzte_lauf_art"] or "—"))
    print("  Tokenizer ............. Wort='%s' / Teilstring='%s'" % (
        st["tokenizer_wort"], st["tokenizer_teil"]))
    print("  Faelle im Verzeichnis . %d" % st["faelle_im_verzeichnis"])
    print("  Faelle im Index ....... %d" % st["faelle_im_index"])
    print("  Saetze im Index ....... %d" % st["saetze_gesamt"])
    print("  neu ................... %d %s" % (len(st["neu"]), st["neu"] or ""))
    print("  veraendert ............ %d %s" % (len(st["veraendert"]),
                                               st["veraendert"] or ""))
    print("  verschwunden .......... %d %s" % (len(st["verschwunden"]),
                                               st["verschwunden"] or ""))
    print("  belegt aktuell ........ %d" % len(st["unveraendert"]))
    if st["unvollstaendig"]:
        print("  UNVOLLSTAENDIG ........ %d Fall/Faelle:"
              % len(st["unvollstaendig"]))
        for e in st["unvollstaendig"]:
            print("      Fall %-8s %s — %s" % (
                e["subject_id"], e["befund_klartext"], e["detail"] or ""))
    else:
        print("  UNVOLLSTAENDIG ........ 0")
    print("  Gesamtbefund .......... %s" % (
        "belegt aktuell und vollstaendig" if st["aktuell"]
        else "NICHT belegt aktuell — s. Zeilen oben"))


def _drucke_lauf(b: Dict[str, object]) -> None:
    """Laufbericht im Klartext."""
    if not b["verzeichnis_vorhanden"]:
        print("Indexlauf NICHT gefahren: das evidence-Verzeichnis existiert "
              "nicht. Es wurde nichts indiziert und nichts entfernt.")
        return
    print("Indexlauf (%s) — %s" % (b["laufart"], _zeit(b["lauf_at"])))
    print("  Dauer ................. %d ms" % b["dauer_ms"])
    print("  Faelle gelesen ........ %d" % b["faelle_gelesen"])
    print("  Saetze geschrieben .... %d" % b["saetze_geschrieben"])
    if b["saetze_gekuerzt"]:
        print("  Saetze GEKUERZT ....... %d (Laengengrenze erreicht — die "
              "betroffenen Texte sind im Index unvollstaendig)"
              % b["saetze_gekuerzt"])
    if b["faelle_entfernt"]:
        print("  Faelle entfernt ....... %s" % (b["faelle_entfernt"],))
    print("  Befunde ............... %s" % (b["nach_befund"] or "—",))
    if b["unvollstaendig"]:
        print("  UNVOLLSTAENDIG ........ %d Fall/Faelle:"
              % len(b["unvollstaendig"]))
        for e in b["unvollstaendig"]:
            print("      Fall %-8s %s — %s" % (
                e["subject_id"], e["befund_klartext"], e["detail"] or ""))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Einstiegspunkt. Rueckgabe = Exit-Code (s. Modulkopf)."""
    p = argparse.ArgumentParser(
        prog="python -m management.search.index_cli",
        description="Suchindex (AP-3E) aufbauen, auffrischen und pruefen. "
                    "Liest die evidence-Datenbanken ausschliesslich "
                    "read-only; schreibt ausschliesslich in search_index.db "
                    "(Hilfsmittel, kein Beweismittel).")
    p.add_argument("--index-db", default=STANDARD_INDEX_PFAD,
                   help="Pfad der Indexdatei (Standard: %s)"
                        % STANDARD_INDEX_PFAD)
    p.add_argument("--evidence-dir", default=None,
                   help="Verzeichnis der evidence_<uid>.db "
                        "(Standard: paths.evidence_db_dir aus config.yaml)")
    p.add_argument("--status", action="store_true",
                   help="Nur den Stand berichten, nichts aendern.")
    p.add_argument("--auffrischen", action="store_true",
                   help="Indexlauf fahren (inkrementell, sofern nicht --voll).")
    p.add_argument("--voll", action="store_true",
                   help="Alle Faelle neu lesen. Teuer — aber der einzige Weg, "
                        "einen Fingerabdruck-Fehltreffer aufzuloesen.")
    p.add_argument("--nur", default=None,
                   help="Nur diese subject_ids, kommagetrennt (Nacharbeit).")
    p.add_argument("--ohne-optimize", action="store_true",
                   help="FTS5-'optimize' nach dem Lauf auslassen (schneller, "
                        "der Index bleibt groesser).")
    p.add_argument("--json", action="store_true",
                   help="Ausgabe als JSON statt Klartext (fuer Skripte).")
    p.add_argument("--leise", action="store_true",
                   help="Kein Fortschritt je Fall.")
    args = p.parse_args(argv)

    if not args.status and not args.auffrischen:
        p.error("Bitte --status oder --auffrischen angeben.")

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s")

    evidence_dir = args.evidence_dir or _evidence_dir_aus_config()
    try:
        nur = _nur_liste(args.nur)
    except ValueError as exc:
        print("Fehler: %s" % exc, file=sys.stderr)
        return 1

    try:
        index = SearchIndexDb(args.index_db)
    except SearchIndexFehler as exc:
        print("Fehler: %s" % exc, file=sys.stderr)
        return 1

    try:
        if index.neu_aufgebaut:
            print("Hinweis: die vorgefundene Indexdatei hatte eine andere "
                  "Schemaversion und wurde verworfen. Der naechste Lauf baut "
                  "sie vollstaendig neu auf. Es ist dabei kein Beleg verloren "
                  "gegangen (Hilfsmittel, kein Beweismittel).")

        ausgabe: Dict[str, object] = {}
        unvollstaendig = False

        if args.auffrischen:
            bauer = SearchIndexBuilder(evidence_dir, index)

            def fortschritt(fertig: int, gesamt: int, uid: int) -> None:
                if not args.leise and not args.json:
                    print("  [%d/%d] Fall %d" % (fertig, gesamt, uid))

            bericht = bauer.lauf(voll=args.voll, nur=nur,
                                 optimieren=not args.ohne_optimize,
                                 fortschritt=fortschritt)
            ausgabe["lauf"] = bericht
            unvollstaendig = bool(bericht["unvollstaendig"]) or not bericht[
                "verzeichnis_vorhanden"]
            if not args.json:
                _drucke_lauf(bericht)

        if args.status or args.auffrischen:
            st = SearchIndexStatus(evidence_dir, index).status()
            ausgabe["status"] = st
            unvollstaendig = unvollstaendig or bool(st["unvollstaendig"]) \
                or not st["verzeichnis_vorhanden"]
            if not args.json:
                if args.auffrischen:
                    print("")
                _drucke_status(st)

        if args.json:
            print(json.dumps(ausgabe, ensure_ascii=False, indent=2,
                             sort_keys=True))
        return 2 if unvollstaendig else 0
    finally:
        index.close()


if __name__ == "__main__":  # pragma: no cover — Einstiegspunkt
    sys.exit(main())
