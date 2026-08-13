# =============================================================================
# core/werkzeug_konfig.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Die Anwendung der Vorrangregel auf die VERWALTUNGSWERKZEUGE — eine Stelle
#   für die rund vierzig Werkzeuge, die bisher jedes für sich aufgelöst haben.
#
#       Argument  >  config.yaml  >  fester Vorgabewert
#
#   Abgrenzung: core/setting_resolver.py ist die REGEL. maintenance/cli_config.py
#   ist ihre Anwendung auf die beiden Wartungswerkzeuge (sie haben eigene
#   Vorrangreihen, siehe dort). Dieses Modul ist ihre Anwendung auf den
#   Normalfall der Verwaltung.
#
# DER NORMALFALL, den es abdeckt — vor Build 643 in 25 Dateien einzeln gebaut:
#
#     def _resolve_db_path(args) -> str:
#         if args.coordinator_db:
#             return args.coordinator_db
#         try:
#             cfg = ConfigLoader(config_path=args.config)
#             path = cfg.get("paths.coordinator_db")
#             if path:
#                 return str(path)
#         except Exception as exc:
#             print("[werkzeug] config.yaml nicht lesbar: %s" % exc, ...)
#         raise SystemExit("[werkzeug] Kein coordinator.db-Pfad: ...")
#
#   Fünfundzwanzig Abschriften derselben zwölf Zeilen. Sie waren nicht
#   identisch: manche prüften `if args.coordinator_db`, andere
#   `getattr(args, ..., None)`; manche lasen `cfg.get("paths.coordinator_db")`,
#   andere `cfg.get("paths", {}).get("coordinator_db")` — was einen Unterschied
#   macht, sobald `paths` fehlt. Die Abbruchmeldungen wichen im Wortlaut ab.
#   Eine Regel, die fünfundzwanzigmal abgeschrieben wird, ist fünfundzwanzigmal
#   einzeln falsch zu schreiben; genau daran ist Ticket 15429c75 aufgefallen.
#
# WAS SICH FÜR DIE BEDIENUNG **NICHT** ÄNDERT — und das ist hier die
# wichtigste Zusage, weil ab dem 01.07.2026 Ermittler mit diesen Werkzeugen
# arbeiten:
#   * Dieselbe Auflösungsreihenfolge, dieselben Vorgabewerte.
#   * Derselbe Abbruch, wenn nichts gesetzt ist — nur mit einer Meldung, die
#     BEIDE Wege nennt statt nur einen.
#   * Keine neue Kommandozeilen-Option, keine geänderte Ausgabe auf `stdout`.
#     Werkzeuge mit `--json` liefern weiterhin ausschließlich JSON.
#
# DIE HERKUNFTSAUSGABE IST OPT-IN, und zwar aus genau diesem Grund. Sie ist
# das, was bei Ticket 15429c75 gefehlt hat — dort meldete ein Werkzeug einen
# Pfad, den niemand übergeben hatte, und sagte nicht, woher er kam. Sie würde
# aber die Ausgabe von vierzig Werkzeugen verändern, darunter solche, deren
# stdout ein Programm weiterverarbeitet. Deshalb:
#
#       AIW_KONFIG_HERKUNFT=1   (Umgebungsvariable)
#
#   Ist sie gesetzt, schreibt jedes umgestellte Werkzeug seine Herkunftszeilen
#   nach **stderr** — nie nach stdout. Damit ist die Auskunft im Bedarfsfall
#   da, ohne im Normalbetrieb etwas zu verändern.
#
# Forensische Relevanz:
#   Welche Datenbank ein Werkzeug öffnet, entscheidet darüber, über WELCHEN
#   Bestand es Aussagen trifft. Ein erratener Pfad ist hier schlimmer als ein
#   Abbruch — deshalb gibt es für die Fall-Datenbanken bewusst KEINEN
#   Vorgabewert (Grundregel 1).
#
# Abhängigkeiten: os, sys, typing (Stdlib) + core.setting_resolver
# Version: v0.8.718 · Build: 718 · 2026-08-13
# =============================================================================

from __future__ import annotations

import os
import sys
from typing import Any, Optional

from core.setting_resolver import SettingResolver, SettingResolverError

#: Die Umgebungsvariable, die die Herkunftszeilen einschaltet. Siehe Kopf.
HERKUNFT_UMGEBUNG = "AIW_KONFIG_HERKUNFT"


def herkunft_gewuenscht() -> bool:
    """Ob die Herkunftszeilen ausgegeben werden sollen."""
    return os.environ.get(HERKUNFT_UMGEBUNG, "").strip() not in ("", "0",
                                                                 "nein", "no")


def resolver(args) -> SettingResolver:
    """
    Baut den Aufloeser aus '--config' des Werkzeugs.

    'pflicht' ist hier IMMER False, und das ist eine bewusste Abweichung von
    den Wartungswerkzeugen: Dort kann man '--config' weglassen, hier tragen
    alle Werkzeuge den Vorgabewert './config.yaml' im argparse-Aufbau. Ein
    ausdruecklich genannter Pfad ist damit von einem nicht genannten nicht zu
    unterscheiden — ein harter Abbruch bei fehlender Datei wuerde also auch
    den treffen, der '--config' gar nicht angegeben hat. Das waere eine
    Verhaltensaenderung; die fehlende Datei fuehrt stattdessen wie bisher zur
    Meldung und danach zum Pflicht-Abbruch, falls kein Argument gesetzt ist.
    """
    return SettingResolver(config_path=getattr(args, "config", None))


def resolver_aus_loader(loader) -> SettingResolver:
    """
    Ein Aufloeser um eine BEREITS geladene config.yaml (NEU Build 644).

    Fuer die Werkzeuge der zweiten Form: sie laden die Datei einmal in
    '_load_config(args)' und reichen sie weiter — fuer den Datenbankpfad UND
    fuer ihre Schwellenwerte. Diese Aufteilung bleibt bestehen; nur die
    AUFLOESUNG des Pfades wandert hierher. Naeheres bei
    SettingResolver.aus_loader.

    'loader' darf None sein: dann gibt es keine auswertbare Konfiguration,
    der Aufrufer hat das bereits gemeldet, und es bleiben Argument und
    Vorgabewert.
    """
    return SettingResolver.aus_loader(loader)


#: Der Rueckfall-Halbsatz fuer 'konfig_laden'. Er steht als Vorgabewert hier
#: und nicht im Aufruf, weil er fuer die Mehrzahl der Werkzeuge zutrifft:
#: faellt die config.yaml aus, arbeiten sie mit ihren festen Vorgabewerten
#: weiter. Die Werkzeuge, bei denen etwas anderes gilt (Schwellenwerte;
#: Werkzeuge ohne jeden Vorgabewert, die danach abbrechen), nennen ihren
#: eigenen Halbsatz beim Aufruf — siehe die Erlaeuterung in 'konfig_laden'.
FOLGE_VORGABEN = "Vorgaben werden verwendet"


def konfig_laden(werkzeug: str, args, *, folge: str = FOLGE_VORGABEN):
    """
    Laedt die config.yaml fuer ein Verwaltungswerkzeug und MELDET ihren
    Ausfall. Rueckgabe: der ConfigLoader oder None (NEU Build 718).

    WARUM ES DIESE FUNKTION GIBT — Ticket cf791ef0. Vierzehn Werkzeuge
    trugen dieselbe Funktion '_load_config(args)' als Abschrift; SECHS von
    ihnen gaben im 'except'-Zweig eine Zeile auf stderr aus, ACHT gaben gar
    nichts aus und lieferten wortlos None. Das ist dasselbe Muster, das
    Ticket 15429c75 bei der Pfadaufloesung aufgedeckt hat: eine Regel, die
    vierzehnmal abgeschrieben wird, ist vierzehnmal einzeln falsch zu
    schreiben. Die Regel steht deshalb ab jetzt an EINER Stelle.

    WAS DER STILLE AUSFALL GEKOSTET HAT: Die Konfiguration liefert nicht nur
    den Datenbankpfad, sondern bei mehreren Werkzeugen die SCHWELLEN, nach
    denen ausgewertet wird. Faellt sie unbemerkt aus, gelten die
    Vorgabeschwellen — dieselbe Datenbank ergibt dann ein anderes Bild, und
    wer zwei Ausgaben nebeneinanderlegt, kann nicht erkennen, dass die eine
    ohne Konfiguration entstanden ist. Ein still uebersprungener Beleg an
    einer Angabe, die das ERGEBNIS veraendert (Grundregel 1).

    ES WAR AUCH SCHON SO DOKUMENTIERT: Der Kopf von 'resolver_aus_loader'
    sagt zu 'loader is None' woertlich "der Aufrufer hat das bereits
    gemeldet", und die Docstrings der acht stummen Werkzeuge sagten
    "Die Meldung ueber eine unlesbare config.yaml gibt weiterhin
    _load_config aus". Der Quelltext hat diese Zusage nicht eingeloest.
    Diese Funktion loest sie ein; die Docstrings bleiben deshalb richtig.

    NACH STDERR, NIE NACH STDOUT — aus demselben Grund wie bei
    'herkunft_ausgeben': mehrere dieser Werkzeuge geben mit '--json' etwas
    aus, das ein Programm weiterliest. Eine Zeile auf stdout waere dort kein
    Hinweis, sondern ein Fehler.

    NICHT OPT-IN, anders als die Herkunftszeilen. Die Herkunft eines Wertes
    ist eine Auskunft ueber den Normalbetrieb; der AUSFALL der Konfiguration
    ist eine Stoerung. Eine Stoerung, die man erst einschalten muss, um sie
    zu sehen, ist keine Meldung.

    'folge' benennt, WAS statt der Konfiguration gilt. Der Halbsatz gehoert
    zur Meldung, weil er die Frage beantwortet, die der Empfaenger als
    naechstes hat: "und was heisst das jetzt fuer meine Ausgabe?" Drei
    Auspraegungen sind im Bestand:
      * "Vorgabe-Schwellen werden verwendet" — das Werkzeug wertet nach
        Schwellen aus, die auch aus der config.yaml stammen koennen.
      * "Vorgaben werden verwendet" (Vorgabewert) — es gelten feste
        Vorgabewerte fuer Verzeichnisse, Bezeichnungen und Aehnliches.
      * "es gelten nur die Angaben von der Befehlszeile" — das Werkzeug
        holt aus der Konfiguration NUR den Datenbankpfad, fuer den es
        bewusst keinen Vorgabewert gibt; ohne '--coordinator-db' folgt
        gleich danach der Abbruch. 'Vorgaben' waere hier schlicht falsch.

    'args.config' wird ueber getattr geholt, damit die Funktion auch fuer
    ein Werkzeug ohne '--config' benutzbar bleibt; ConfigLoader sucht dann
    an seinem eigenen Vorgabeort.
    """
    try:
        from core.config_loader import ConfigLoader
        return ConfigLoader(config_path=getattr(args, "config", None))
    except Exception as exc:
        # BREITES 'except' MIT ABSICHT: Der Rueckfall auf die Vorgabewerte
        # soll fuer JEDEN Ausfall der Datei greifen — fehlend, unlesbar,
        # kaputtes YAML, ungueltiger Wert. Verengt auf ConfigLoaderError
        # wuerde z.B. ein PermissionError das Werkzeug abbrechen lassen,
        # was gegenueber dem bisherigen Verhalten eine Verschaerfung waere.
        # Weil die Meldung jetzt IMMER erfolgt, bleibt der Ausfall
        # trotzdem sichtbar.
        print("[%s] config.yaml nicht lesbar (%s): %s" % (werkzeug, folge, exc),
              file=sys.stderr)
        return None


def herkunft_ausgeben(werkzeug: str, r: SettingResolver) -> None:
    """
    Schreibt die Herkunftszeilen nach stderr — nur wenn angefordert.

    NACH STDERR UND NIE NACH STDOUT: Mehrere dieser Werkzeuge geben JSON aus,
    das ein Programm weiterliest. Eine zusaetzliche Zeile auf stdout waere
    dort kein Hinweis, sondern ein Fehler.

    NUR DAS NEUE WIRD GEDRUCKT. Ein Werkzeug, das nacheinander drei Werte
    aufloest, ruft diese Funktion dreimal auf; ohne den Zaehler stuende die
    erste Zeile dann dreimal da. Wer eine Zeile mehrfach sieht, sucht nach
    mehreren Vorgaengen.
    """
    if not herkunft_gewuenscht():
        return
    zeilen = r.protokoll_zeilen()
    ab = getattr(r, "_gedruckt", 0)
    for zeile in zeilen[ab:]:
        print("[%s][Konfig] %s" % (werkzeug, zeile), file=sys.stderr)
    try:
        setattr(r, "_gedruckt", len(zeilen))
    except AttributeError:                        # pragma: no cover
        pass


def db_pfad(werkzeug: str, args, *,
            arg_attribut: str = "coordinator_db",
            arg_name: str = "--coordinator-db",
            config_schluessel: str = "paths.coordinator_db",
            default: Optional[str] = None,
            name: str = "coordinator_db",
            r: Optional[SettingResolver] = None) -> str:
    """
    DER NORMALFALL: Argument > config.yaml > (Vorgabewert oder Abbruch).

    Args:
        werkzeug:          Kennung fuer die Meldungen ('cases_admin'). Sie
                           steht in eckigen Klammern am Zeilenanfang, genau
                           wie bisher — die Meldungen bleiben wiedererkennbar.
        args:              Das argparse-Ergebnis.
        arg_attribut:      Attributname am argparse-Ergebnis ('coordinator_db',
                           'db', 'templates_db' ...).
        arg_name:          Wie das Argument auf der Kommandozeile heisst.
        config_schluessel: Punkt-separierter Schluessel.
        default:           Fester Vorgabewert — oder None fuer 'kein
                           Vorgabewert, dann Abbruch'.
        name:              Benennung in der Herkunftszeile.
        r:                 Ein bereits gebauter Aufloeser. Werkzeuge, die
                           MEHRERE Werte aufloesen, reichen denselben herein;
                           dann steht alles in EINEM Protokoll und die
                           config.yaml wird einmal gelesen statt dreimal.

    Returns:
        Der Pfad als Zeichenkette.

    Raises:
        SystemExit: wenn kein Wert zustande kommt (Rueckgabewert 1). Das
            entspricht dem bisherigen Verhalten aller umgestellten Werkzeuge.
    """
    aufl = r if r is not None else resolver(args)

    # Die Meldung ueber eine unlesbare config.yaml geht wie bisher nach
    # stderr — und zwar IMMER, nicht nur bei eingeschalteter Herkunft. Eine
    # nicht auswertbare Konfiguration ist ein Befund und kein Detail.
    if aufl.config_meldung and not getattr(aufl, "_gemeldet", False):
        print("[%s] %s" % (werkzeug, aufl.config_meldung), file=sys.stderr)
        try:
            setattr(aufl, "_gemeldet", True)   # nicht dreimal dieselbe Zeile
        except AttributeError:                 # pragma: no cover
            pass

    schon_gemeldet = bool(aufl.config_meldung)

    roh = getattr(args, arg_attribut, None)
    # LEERE ZEICHENKETTE IST KEINE ANGABE. Die alten Fassungen schrieben
    # 'if args.coordinator_db:' — ein '--coordinator-db ""' fiel dort also
    # durch auf config.yaml. Dieses Verhalten wird beibehalten; es hier
    # stillschweigend zu aendern hiesse, einen Aufruf anders zu behandeln
    # als bisher.
    if isinstance(roh, str) and not roh.strip():
        roh = None

    try:
        eintrag = aufl.aufloesen(
            name=name, arg_wert=roh, arg_name=arg_name,
            config_schluessel=config_schluessel, default=default,
            wandler=str, pflicht=True,
            meldung_anhaengen=not schon_gemeldet)
    except SettingResolverError as exc:
        raise SystemExit("[%s] %s" % (werkzeug, exc))
    herkunft_ausgeben(werkzeug, aufl)
    return eintrag.wert


def wert(werkzeug: str, args, *, arg_attribut: str, arg_name: str,
         config_schluessel: Optional[str], default: Any,
         name: Optional[str] = None, wandler=None,
         r: Optional[SettingResolver] = None) -> Any:
    """
    Wie db_pfad, aber MIT Vorgabewert und ohne Abbruch — fuer die Werte, die
    einen Rueckfall haben (Verzeichnisse, Schwellen, Grenzen).

    Getrennt von db_pfad, weil der Unterschied betrieblich zaehlt: Der eine
    Fall bricht ab, der andere laeuft weiter. Wer beide durch dieselbe
    Funktion schickt, sieht am Aufruf nicht mehr, welcher von beiden vorliegt.
    """
    aufl = r if r is not None else resolver(args)
    roh = getattr(args, arg_attribut, None)
    if isinstance(roh, str) and not roh.strip():
        roh = None
    try:
        eintrag = aufl.aufloesen(
            name=name or arg_attribut, arg_wert=roh, arg_name=arg_name,
            config_schluessel=config_schluessel, default=default,
            wandler=wandler)
    except SettingResolverError as exc:
        raise SystemExit("[%s] %s" % (werkzeug, exc))
    herkunft_ausgeben(werkzeug, aufl)
    return eintrag.wert
