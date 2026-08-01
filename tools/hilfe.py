#!/usr/bin/env python3
# =============================================================================
# tools/hilfe.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H16)
# =============================================================================
# Zweck:
#   Das Dach ueber die Kommandozeilen-Werkzeuge der Anlage. Es beantwortet
#   die drei Fragen, die man vor dem ersten Aufruf hat:
#
#     python tools/hilfe.py liste                 Welche Werkzeuge gibt es?
#     python tools/hilfe.py zeige rbac_admin      Was macht dieses hier?
#     python tools/hilfe.py suche sicherung       Womit mache ich X?
#
# WARUM ES DIESES WERKZEUG BRAUCHT:
#   Die Anlage hat Dutzende Kommandozeilen-Werkzeuge, verteilt ueber vier
#   Verzeichnisebenen. Jedes einzelne kann '--help'. Aber '--help' setzt
#   voraus, dass man den Namen schon kennt - und genau den kennt man nicht,
#   wenn man sucht. Ohne dieses Dach ist die Suche ein Verzeichnisbaum.
#
# WAS ES NICHT TUT: Es fuehrt kein Werkzeug aus. Es liest keine Datenbank. Es
#   nimmt keine Sperre. Es gibt Text aus - sonst nichts. Damit ist es zu jeder
#   Zeit und in jedem Betriebszustand gefahrlos aufrufbar, auch mitten in
#   einer Migration.
#
# RUECKGABEWERTE:
#   0  ausgegeben
#   1  unbekanntes Werkzeug (mit Vorschlaegen) bzw. Suche ohne Treffer
#   2  Aufruffehler
#
#   WARUM DIE SUCHE OHNE TREFFER EINE 1 LIEFERT: damit ein Skript, das
#   'hilfe.py suche X' benutzt, den Leerbefund erkennen kann, ohne die
#   Ausgabe zu lesen. Ein Leerbefund ist eine Auskunft und kein Fehler - die
#   Ausgabe sagt das ausdruecklich, und der Rueckgabewert unterscheidet ihn
#   von der 0.
#
# AUSGABE: reines ASCII, 78 Zeichen, keine Escape-Sequenzen - die
#   Begruendung steht im Kopf von management/help/cli_text.py.
#
# Version: v0.8.608 - Build: 608 - 2026-07-31
# =============================================================================

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence

# Direktaufruf als Skript: das Paketverzeichnis muss im Suchpfad liegen.
# Muster aus management/search/index_cli.py.
_WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from management.help.cli_katalog import (                 # noqa: E402
    CLI_KATALOG, eintrag, fehlliste_cli_tiefe,
)
from management.help.cli_text import (                    # noqa: E402
    liste_text, suche_text, umbrechen, unbekannt_text, zeige_text,
)
from management.help.cli_modell import CliEintrag         # noqa: E402
from management.help import cli_epilog                   # noqa: E402
from management.help.cli_epilog import OHNE_EPILOG       # noqa: E402


def baue_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python tools/hilfe.py",
        description="Uebersicht ueber die Kommandozeilen-Werkzeuge der "
                    "Anlage. Gibt nur Text aus - fuehrt nichts aus.",
        epilog=cli_epilog.epilog("hilfe"),
        formatter_class=cli_epilog.HilfeFormat,
    )
    unter = p.add_subparsers(dest="befehl")

    p_liste = unter.add_parser(
        "liste", help="Alle Werkzeuge, nach Arbeitsbereich gruppiert.")
    p_liste.add_argument(
        "--nur-schreibend", action="store_true",
        help="Nur Werkzeuge, die etwas aendern koennen.")

    p_zeige = unter.add_parser(
        "zeige", help="Ein Werkzeug im Einzelnen.")
    p_zeige.add_argument("werkzeug", help="Kennung, z. B. rbac_admin")

    p_suche = unter.add_parser(
        "suche", help="Volltextsuche ueber den Katalog.")
    p_suche.add_argument("begriff", help="Suchbegriff")

    unter.add_parser(
        "stand", help="Wie vollstaendig der Katalog ausgearbeitet ist.")
    return p


def stand_text() -> str:
    """
    Der Ausarbeitungsstand des Katalogs.

    WARUM ES DIESEN BEFEHL GIBT: Der Katalog fuehrt zu jedem Werkzeug einen
    Grundeintrag, aber die Tiefeninhalte (geprueft gefahrene Beispiele,
    Rueckgabewerte, Warnhinweise) entstehen erst nach und nach. Wer sich auf
    die Hilfe verlaesst, soll mit einem Aufruf sehen, wie weit sie ist -
    statt es an einem Eintrag zu merken, der duenner ist als erwartet
    (Grundregel 1).
    """
    offen = fehlliste_cli_tiefe()
    fertig = len(CLI_KATALOG) - len(offen)
    zeilen: List[str] = []
    zeilen.append("Stand des Werkzeugkatalogs")
    zeilen.append("=" * 78)
    zeilen.append("")
    zeilen.append("Werkzeuge insgesamt:        %d" % len(CLI_KATALOG))
    zeilen.append("davon mit Tiefeninhalt:     %d" % fertig)
    zeilen.append("davon nur Grundeintrag:     %d" % len(offen))
    zeilen.append("")
    if offen:
        zeilen.append("Noch ohne Beispiele und Rueckgabewerte:")
        zeile = "  "
        for s in offen:
            if len(zeile) + len(s) + 2 > 78:
                zeilen.append(zeile.rstrip())
                zeile = "  "
            zeile += s + ", "
        zeilen.append(zeile.rstrip().rstrip(","))
    else:
        zeilen.append("Alle Werkzeuge sind vollstaendig ausgearbeitet.")

    # Build 624 (H20): die Werkzeuge, die BEWUSST keinen Epilog in ihrer
    # eingebauten Hilfe bekommen. Sie stehen hier namentlich MIT GRUND -
    # sonst waere von aussen nicht zu unterscheiden, ob sie uebersehen
    # wurden oder ausgenommen sind (Grundregel 1).
    #
    # WARUM HIER NICHT DIE VOLLE FEHLLISTE STEHT: um zu sagen, WELCHE
    # Werkzeuge verdrahtet sind, muesste dieses Werkzeug den Quelltext des
    # Bestands durchsuchen. Es liest heute nichts ausser dem Katalog, und
    # das soll so bleiben - es ist in jedem Betriebszustand gefahrlos
    # aufrufbar, auch mitten in einer Migration. Die vollstaendige
    # Gegenprobe gegen den Bestand macht der Regressionslauf
    # (cli_epilog.verify_epilog_abgedeckt, test_help_cli_epilog.py CE10).
    if OHNE_EPILOG:
        zeilen.append("")
        zeilen.append("Ohne Beispiele in der eingebauten Hilfe (--help), "
                      "mit Grund:")
        for kennung in sorted(OHNE_EPILOG):
            zeilen.append("  " + kennung)
            zeilen.extend(umbrechen(OHNE_EPILOG[kennung], 78, "      "))
    return "\n".join(zeilen)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = baue_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    # OHNE BEFEHL WIRD NICHT GERATEN. Ein Werkzeug, das ohne Argument
    # irgendetwas tut, ist eines, dessen Verhalten man sich merken muss.
    if not args.befehl:
        parser.print_help()
        return 2

    if args.befehl == "liste":
        print(liste_text(nur_schreibend=args.nur_schreibend))
        return 0

    if args.befehl == "stand":
        print(stand_text())
        return 0

    if args.befehl == "zeige":
        e: Optional[CliEintrag] = eintrag(args.werkzeug)
        if e is None:
            # Die Meldung geht auf die FEHLERAUSGABE, die Vorschlaege
            # ebenfalls: wer die Ausgabe in eine Datei umleitet, will dort
            # keinen Fehlertext stehen haben.
            print(unbekannt_text(args.werkzeug), file=sys.stderr)
            return 1
        print(zeige_text(e))
        return 0

    if args.befehl == "suche":
        from management.help.cli_katalog import suche as _suche
        text = suche_text(args.begriff)
        print(text)
        return 0 if _suche(args.begriff) else 1

    parser.print_help()          # pragma: no cover - argparse faengt das ab
    return 2                     # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
