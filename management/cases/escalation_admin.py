# =============================================================================
# management/cases/escalation_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (AP-2F)
# =============================================================================
# Zweck:
#   NUR-LESENDE CLI fuer die Eskalationsregel-Auswertung.
#
#   python -m management.cases.escalation_admin
#          [--coordinator-db PATH] [--config ./config.yaml] [--json]
#
# Version: v0.8.718 · Build: 718 · 2026-08-13
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time

from management.cases.escalation import (
    escalation_thresholds_from_config, escalation_to_dict,
)
from management.cases.escalation_repo import EscalationRepo
from management.help import cli_epilog  # noqa: E402
# Build 644: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit Build 643 an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402


def _load_config(args):
    """
    Laedt die config.yaml und MELDET ihren Ausfall auf stderr.

    TICKET cf791ef0 (Build 718): Bis hierher stand an dieser Stelle eine
    Abschrift mit 'except Exception: return None' - OHNE Ausgabe. Faellt
    die Konfiguration aus, gelten die Vorgabeschwellen, und nichts weist
    darauf hin. Das war ein still uebersprungener Beleg (Grundregel 1) -
    und zwar an einer Angabe, die das ERGEBNIS veraendert und nicht nur
    seinen Vermerk: dieselbe Datenbank ergibt mit den Vorgabeschwellen ein
    anderes Bild.

    Die Meldung steht jetzt in core/werkzeug_konfig.konfig_laden(); die
    ausfuehrliche Begruendung fuer die Zusammenfuehrung steht dort. Der
    Rueckgabewert ist unveraendert: der ConfigLoader oder None.
    """
    return werkzeug_konfig.konfig_laden(
        "escalation_admin", args, folge="Vorgabe-Schwellen werden verwendet")


def _resolve_db_path(args, cfg) -> str:
    """
    coordinator.db-Pfad: Argument --coordinator-db > paths.coordinator_db
    > Abbruch.

    BUILD 644 - DIE AUFLOESUNG IST UMGEZOGEN, das Verhalten NICHT.
    Sie steht jetzt in core/werkzeug_konfig.py; die Begruendung fuer den
    Umzug steht im Kopf jener Datei.

    'cfg' BLEIBT PARAMETER, und das ist der Kern dieser Umstellung: Dieses
    Werkzeug laedt die config.yaml EINMAL (_load_config) und reicht sie
    weiter - fuer den Pfad UND fuer seine uebrigen Werte. Wuerde die
    Aufloesung sich hier ihre eigene Kopie holen, koennten beide im
    Grenzfall aus VERSCHIEDENEN Staenden derselben Datei stammen. Der
    Aufloeser wird deshalb UM den vorhandenen Loader gebaut, nicht neben ihn.

    UNVERAENDERT bleiben: die Reihenfolge, das Fehlen eines Vorgabewerts,
    der Abbruch mit dem Praefix '[escalation_admin]' - nur nennt die Meldung jetzt
    BEIDE Wege statt nur einen. Die Meldung ueber eine unlesbare config.yaml
    gibt weiterhin _load_config aus; cfg ist dann None.
    """
    return werkzeug_konfig.db_pfad(
        "escalation_admin", args, arg_attribut="coordinator_db",
        arg_name="--coordinator-db", config_schluessel="paths.coordinator_db",
        name="coordinator_db", r=werkzeug_konfig.resolver_aus_loader(cfg))


#: Die drei Schwellen in der Reihenfolge, in der sie ausgewiesen werden.
#: Die Reihenfolge ist FEST und entspricht der Reihenfolge der Regeln R1, R2,
#: R3 in escalation.py - damit zwei Ausgaben Zeile fuer Zeile vergleichbar
#: bleiben und nicht erst sortiert werden muessen.
_SCHWELLEN_FELDER = ("red_overdue_days", "stale_open_days", "backlog_high")


def _schwellen_dict(thresholds) -> dict:
    """
    Die geltenden Schwellen als einfaches dict.

    GLEICHER SCHLUESSELSATZ WIE DER HTTP-ENDPUNKT: management_app._escalations
    haengt seit Build 515 genau diese drei Schluessel unter 'thresholds' an
    die Antwort, mit der dort ausformulierten Begruendung ("eine
    Eskalationsmeldung ohne ihren Massstab waere nicht nachpruefbar; '30 Tage
    inaktiv' ist erst mit '>= 30' eine Aussage"). Was fuer die Weboberflaeche
    gilt, gilt fuer die Kommandozeile genauso - und es waere schlimmer als
    nutzlos, wenn dieselbe Auskunft an beiden Stellen anders hiesse.
    """
    return {feld: getattr(thresholds, feld) for feld in _SCHWELLEN_FELDER}


def _schwellen_herkunft(cfg, feld: str) -> str:
    """
    Woher der Wert einer Schwelle stammt: 'config.yaml' oder 'Vorgabe'.

    BELEGT, NICHT GERATEN: Gefragt wird ConfigLoader.stammt_aus_datei(), das
    ausschliesslich in den ROHEN Dateiinhalt sieht. cfg.get() waere hier
    untauglich - es liefert auch Werte, die nur aus den Coded Defaults
    stammen, und die Herkunftsangabe waere eine unbelegte Behauptung (die
    Begruendung steht ausfuehrlich in core/config_loader.py, Build 638).

    'cfg' ist None, wenn die config.yaml nicht lesbar war; _load_config hat
    das dann bereits gemeldet, und es gilt ueberall die Vorgabe. Der
    getattr-Test faengt den Fall ab, dass ein Aufrufer ein einfaches dict
    statt eines ConfigLoader hereinreicht - dann ist die Herkunft nicht
    belegbar, und 'Vorgabe' zu behaupten waere falsch.
    """
    if cfg is None:
        return "Vorgabe"
    pruefer = getattr(cfg, "stammt_aus_datei", None)
    if pruefer is None:
        return "unbekannt"
    try:
        return "config.yaml" if pruefer("escalation.%s" % feld) else "Vorgabe"
    except Exception:  # pragma: no cover - defensiv, siehe oben
        return "unbekannt"


def _schwellen_zeile(thresholds, cfg) -> str:
    """
    Die Kopfzeile mit den geltenden Schwellen und ihrer Herkunft.

    WARUM SIE IMMER ERSCHEINT und nicht nur im Stoerungsfall (Ticket
    cf791ef0): Zwei Ausgaben sollen VERGLEICHBAR sein. Stuende der Massstab
    nur dann da, wenn die Konfiguration ausgefallen ist, muesste man aus dem
    FEHLEN der Zeile auf den Normalfall schliessen - und ein Fehlen ist kein
    Beleg. Wer zwei Laeufe nebeneinanderlegt, sieht so in Zeile 1 beider
    Ausgaben, ob sie denselben Massstab hatten.

    NUR IM TEXTBETRIEB. Mit '--json' bleibt stdout ausschliesslich JSON
    (dieselbe Zusage wie im Kopf von core/werkzeug_konfig.py); dort fahren
    die Schwellen unter dem Schluessel 'thresholds' mit.
    """
    teile = ["%s=%s [%s]" % (feld, getattr(thresholds, feld),
                             _schwellen_herkunft(cfg, feld))
             for feld in _SCHWELLEN_FELDER]
    return "Schwellen: " + "  ".join(teile)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="escalation_admin",
        description="Eskalationsregel-Auswertung (nur lesend).",
        epilog=cli_epilog.epilog("escalation_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    cfg = _load_config(args)
    db_path = _resolve_db_path(args, cfg)
    thresholds = escalation_thresholds_from_config(cfg)

    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        report = EscalationRepo(con).compute(
            thresholds=thresholds, now=int(time.time()))
    finally:
        con.close()

    if args.json:
        # Ticket cf791ef0: Die Schwellen fahren MIT - wie beim HTTP-Endpunkt
        # seit Build 515. Die uebrigen Schluessel und ihre Werte sind
        # unveraendert; ein Programm, das bisher nur 'items' und die Zaehler
        # gelesen hat, liest sie weiterhin unveraendert.
        payload = escalation_to_dict(report)
        payload["thresholds"] = _schwellen_dict(thresholds)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(_schwellen_zeile(thresholds, cfg))
    print("Eskalationen: hoch=%d mittel=%d niedrig=%d (von %d Faellen)"
          % (report.count_hoch, report.count_mittel, report.count_niedrig,
             report.total_cases))
    mark = {"hoch": "!!", "mittel": "! ", "niedrig": "  "}
    for i in report.items:
        print("  %s [%s] %s" % (mark.get(i.severity, "  "), i.rule_code, i.message))
    if not report.items:
        print("  (keine Eskalation)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
