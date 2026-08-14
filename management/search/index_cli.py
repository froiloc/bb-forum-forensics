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
# WARTUNGSSTUFE B - betriebsvertraeglich mit benennbarer Einschraenkung
#   (Analyse Build 609, Kopfeintrag nachgetragen in Build 686). Der Lauf
#   schreibt ausschliesslich in search_index.db, die kein anderer Dienst
#   offen haelt; die evidence-Datenbanken werden nur mit 'mode=ro' gelesen.
#   ER RUFT DEN WARTUNGSVORBEHALT DESHALB NICHT und soll es nicht.
#   DIE EINSCHRAENKUNG: Eine gerade beschriebene evidence-Datei kann er
#   nicht lesen - dann bleibt dieser Fall unvollstaendig und der Lauf endet
#   mit 2. Das ist kein Sicherheits-, sondern ein Vollstaendigkeitsproblem.
#
# Version: v0.8.720 · Build: 720 · 2026-08-14
#   Build 720 (Ticket 5a7e93b1): STANDARD_INDEX_PFAD entfallen. Der Ort des
#   Suchindex kommt jetzt fuer Werkzeug UND Server aus derselben Aufloesung
#   (management/search/index_ort.py, Schluessel 'paths.search_index_db').
#   Ein moeglicher Umzug wird gemeldet; verschoben wird NICHTS.
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
from management.help import cli_epilog  # noqa: E402
# Build 646: Vorrangregel an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402
# Build 720 (Ticket 5a7e93b1): EIN Vorgabewert je Pfad.
from core.config_loader import coded_default  # noqa: E402
from management.search.index_ort import IndexOrt  # noqa: E402

logger = logging.getLogger("management.search.index_cli")

# BUILD 720 (Ticket 5a7e93b1): STANDARD_INDEX_PFAD IST ENTFALLEN.
#
# Hier stand bis Build 718 ein eigener Vorgabewert fuer den Suchindex,
# waehrend der Verwaltungsserver fuer DENSELBEN Index 'paths.search_index_db'
# las. Der Befund war seit Build 641 im Kopf dieser Datei vermerkt: "Wer den
# Index per config.yaml verlegt, verlegt ihn also nur fuer den Server."
#
# Der Ort kommt jetzt aus management/search/index_ort.py - EINE Aufloesung
# fuer Werkzeug und Server, mit dem einen Vorgabewert aus
# core/config_loader.py (paths.search_index_db).


def _evidence_dir_aus_config() -> str:
    """
    paths.evidence_db_dir aus config.yaml.

    BUILD 646: Die Aufloesung steht in core/werkzeug_konfig.py. Unveraendert
    bleiben beide Eigenheiten dieses Werkzeugs: es hat KEIN '--config'
    (gelesen wird './config.yaml' im Arbeitsverzeichnis), und ein Ausfall der
    Konfiguration fuehrt NICHT zum Abbruch, sondern zum Standard - der
    Rueckfall wird dabei protokolliert und nicht verschluckt (Grundregel 1).

    BUILD 720 - DER ZWEITE PFAD IST NICHT MEHR AUSSEN VOR (Ticket 5a7e93b1).
    Hier stand seit Build 641 der Befund: "Der Ort des Suchindex kommt aus dem
    fest verdrahteten Vorgabewert von '--index-db' (STANDARD_INDEX_PFAD),
    NICHT aus 'paths.search_index_db' - waehrend der Verwaltungsserver fuer
    denselben Index eben diesen Eintrag liest. Wer den Index per config.yaml
    verlegt, verlegt ihn also nur fuer den Server." Er war ausdruecklich
    zurueckgestellt, weil die Umstellung aendert, wohin ein bestehender Index
    geschrieben wird.

    Sie ist jetzt entschieden (Alex, 13.08.2026) und vollzogen: beide lesen
    'paths.search_index_db' ueber management/search/index_ort.py. Damit die
    Aenderung nicht stillschweigend geschieht, MELDET das Werkzeug einen
    moeglichen Umzug - siehe IndexOrt.umzugsmeldung().
    """
    r = werkzeug_konfig.resolver(_KEINE_ARGUMENTE)
    if r.config_meldung:
        logger.warning("evidence_db_dir nicht aus config.yaml lesbar (%s) - "
                       "Vorgabewert %s.", r.config_meldung,
                       coded_default("paths.evidence_db_dir"))
    return werkzeug_konfig.wert(
        "index_cli", _KEINE_ARGUMENTE,
        arg_attribut="(nicht ueber ein Argument)", arg_name="--evidence-dir",
        config_schluessel="paths.evidence_db_dir",
        # Build 720: KEIN Literal mehr - der eine Vorgabewert steht in
        # core/config_loader.py. Zwei Literale fuer denselben Pfad sind
        # solange harmlos, bis eines geaendert wird.
        default=coded_default("paths.evidence_db_dir"),
        name="evidence_db_dir", wandler=str, r=r)


def _coordinator_db_aus_config() -> str:
    """
    paths.coordinator_db - AUSSCHLIESSLICH fuer die Umzugserkennung des
    Suchindex (Build 720).

    Das Werkzeug braucht die coordinator.db selbst nicht. Es braucht ihren
    Ort nur, um zu wissen, wo der Index nach der ALTEN Regel des Servers
    gelegen haette ('neben der coordinator.db'). Ohne diese Angabe koennte
    die Meldung den haeufigsten Umzugsfall nicht erkennen - genau den, der
    auf einer Anlage mit verlegten Datenbanken eintritt.
    """
    r = werkzeug_konfig.resolver(_KEINE_ARGUMENTE)
    return werkzeug_konfig.wert(
        "index_cli", _KEINE_ARGUMENTE,
        arg_attribut="(nicht ueber ein Argument)", arg_name="--coordinator-db",
        config_schluessel="paths.coordinator_db",
        default=coded_default("paths.coordinator_db"),
        name="coordinator_db", wandler=str, r=r)


class _KeineArgumente:
    """Platzhalter: dieses Werkzeug hat kein '--config'."""


_KEINE_ARGUMENTE = _KeineArgumente()

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
                    "(Hilfsmittel, kein Beweismittel).",
        epilog=cli_epilog.epilog("index_cli"),
        formatter_class=cli_epilog.HilfeFormat)
    # default=None ist PFLICHT, damit die Vorrangregel greift: ein
    # argparse-Vorgabewert waere von einer Nutzereingabe nicht zu
    # unterscheiden (siehe SettingResolver, Festlegung 1).
    p.add_argument("--index-db", default=None,
                   help="Pfad der Indexdatei. Ohne Angabe: "
                        "paths.search_index_db aus config.yaml, sonst %s"
                        % coded_default("paths.search_index_db"))
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
        # Build 720: EINE Aufloesung fuer Werkzeug und Server. Die
        # Umzugsmeldung steht VOR dem Zugriff - danach haette der Aufbau
        # die neue Datei schon angelegt, und die Bedingung waere nicht mehr
        # erfuellt.
        ort = IndexOrt.bestimmen(arg_wert=args.index_db,
                                 coordinator_db=_coordinator_db_aus_config())
        # '--json' BLEIBT MASCHINENLESBAR. Die Herkunftszeile und eine
        # etwaige Umzugsmeldung ENTFALLEN dabei nicht (Grundregel 1) - sie
        # wechseln den Kanal auf die Fehlerausgabe. Die Alternative waere
        # gewesen, sie im JSON-Betrieb wegzulassen; dann saehe ein Skript
        # einen umgezogenen Index wie einen leeren. SI23b liest stdout mit
        # json.loads() und haette den Fehler ohnehin gemeldet.
        kanal = sys.stderr if args.json else sys.stdout
        print(ort.protokollzeile(), file=kanal)
        meldung = ort.umzugsmeldung()
        if meldung:
            print(meldung, file=kanal)
        index = SearchIndexDb(ort.pfad)
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
