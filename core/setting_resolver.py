# =============================================================================
# core/setting_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   EINE Stelle, an der die projektweite Vorrangregel aufgeloest wird:
#
#       CLI-Argument  >  (aus einem Argument abgeleitet)
#                     >  config.yaml  >  fester Vorgabewert des Werkzeugs
#
#   Jede Aufloesung wird PROTOKOLLIERT (SettingOrigin) und ist damit belegbar.
#
# WARUM ES DIESES MODUL GIBT (Ticket 15429c75, gemeldet 2026-07-30):
#   'tools/maintenance.py enter --coordinator-db data\coordinator_2.db' brach
#   mit '[RBAC] coordinator.db fehlt (data\coordinator.db)' ab. Der uebergebene
#   DATEINAME ging unterwegs verloren; das Werkzeug fragte config.yaml
#   ueberhaupt nicht und meldete nicht, woher sein Pfad stammte.
#
#   Die Regel selbst war seit Build 001 im Kopf von core/config_loader.py
#   niedergeschrieben ("Eskalationskette ... CLI > config.yaml > Coded
#   Default"), aber NIRGENDS als Bauteil vorhanden. Rund fuenfzehn Werkzeuge
#   haben sie deshalb je fuer sich nachgebaut, teils vollstaendig
#   (management/cases/cases_admin.py), teils gar nicht (die beiden
#   Wartungswerkzeuge). Eine Regel, die fuenfzehnmal einzeln gebaut wird, ist
#   fuenfzehnmal einzeln falsch zu bauen. Ab hier gibt es sie EINMAL.
#
# WAS DIESES MODUL AUSDRUECKLICH NICHT TUT:
#   Es schreibt keinen Wert in die Konfiguration zurueck, es legt keine Datei
#   an und es kennt kein einziges Werkzeug. Welche Schluessel es gibt und
#   welcher Vorgabewert gilt, sagt der Aufrufer — hier steht nur, in welcher
#   Reihenfolge gefragt wird.
#
# Forensische Relevanz:
#   Aus diesen Werten ergibt sich, WELCHE Datenbank ein Werkzeug oeffnet. Ein
#   Werkzeug, das die Herkunft seiner Pfade nicht benennen kann, liefert keinen
#   ueberpruefbaren Befund (Grundregel 1). Deshalb ist das Protokoll kein
#   Beiwerk, sondern der Zweck.
#
# Abhaengigkeiten: pathlib, typing (Stdlib) + core.config_loader, core.setting_origin
# Version: v0.8.638 · Build: 638 · 2026-08-01
# =============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from core.setting_origin import SettingOrigin


class SettingResolverError(Exception):
    """
    Die Aufloesung ist gescheitert und darf NICHT stillschweigend mit einem
    Vorgabewert weiterlaufen (Grundregel 1).

    Zwei Faelle:
      * eine ausdruecklich per --config verlangte Datei ist nicht lesbar,
      * ein Wert aus config.yaml laesst sich nicht in den erwarteten Typ
        wandeln (etwa 'stale_seconds: viel').
    """


class SettingResolver:
    """
    Loest Einstellwerte nach der Vorrangregel auf und protokolliert dabei
    jede einzelne Entscheidung.

    Verwendung:
        r = SettingResolver(config_path=args.config,
                            pflicht=bool(args.config))
        coord = r.aufloesen(
            name="coordinator_db",
            arg_wert=args.coordinator_db, arg_name="--coordinator-db",
            config_schluessel="paths.coordinator_db",
            default="./data/coordinator.db")
        for zeile in r.protokoll_zeilen():
            print(zeile)

    ZWEI FESTLEGUNGEN, die man kennen muss:

    1) 'Nicht gesetzt' heisst None — nicht "leer" und nicht "falsch".
       Ein Argument mit dem Wert 0, '' oder False ist GESETZT und gewinnt.
       Folge fuer den Aufrufer: argparse-Argumente, die an der Vorrangregel
       teilnehmen, MUESSEN 'default=None' tragen. Ein argparse-Default ist von
       einer Nutzereingabe sonst nicht zu unterscheiden — genau daran ist die
       Regel in den Wartungswerkzeugen gescheitert ('--data-dir' trug dort
       'default="./data"' und sah damit immer wie eine Eingabe aus).

    2) Aus config.yaml zaehlt nur, was DORT STEHT.
       Gefragt wird ueber ConfigLoader.stammt_aus_datei() (Build 638), nicht
       ueber get(). get() liefert auch die Coded Defaults des ConfigLoaders;
       die als 'aus config.yaml' zu melden, waere eine falsche Herkunftsangabe.
    """

    def __init__(self, config_path: Optional[str] = None, *,
                 pflicht: bool = False) -> None:
        """
        Args:
            config_path: Pfad zur config.yaml. None → './config.yaml'.
            pflicht:     True  → ist die Datei nicht ladbar, wird
                                 SettingResolverError geworfen. Das ist der
                                 Fall, wenn der Aufrufer sie AUSDRUECKLICH per
                                 --config benannt hat: wer einen Pfad nennt,
                                 bekommt keinen anderen untergeschoben.
                         False → ist die Datei nicht ladbar, laeuft die
                                 Aufloesung ohne sie weiter (Vorgabewerte
                                 greifen). Der Grund wird in config_meldung
                                 festgehalten und ist vom Werkzeug AUSZUGEBEN
                                 — nicht still zu verschlucken.

                                 WARUM NICHT IMMER HART ABBRECHEN: Die
                                 Wartungswerkzeuge muessen auch dann noch
                                 laufen, wenn der Bestand halb zerlegt ist.
                                 Ein 'exit' des Wartungsfensters, das an einer
                                 fehlenden config.yaml scheitert, waere die
                                 Wiederherstellung, die genau dann versagt,
                                 wenn man sie braucht.
        """
        self._config = None
        self._config_pfad: Optional[Path] = None
        self._config_meldung: Optional[str] = None
        self._protokoll: List[SettingOrigin] = []

        try:
            from core.config_loader import ConfigLoader
            self._config = ConfigLoader(config_path=config_path)
            self._config_pfad = self._config.config_path
        except Exception as exc:
            self._config_meldung = (
                "config.yaml nicht ausgewertet (%s: %s) — es greifen die "
                "Vorgabewerte des Werkzeugs."
                % (type(exc).__name__, exc))
            if pflicht:
                raise SettingResolverError(
                    "Die ausdruecklich angegebene Konfiguration '%s' ist nicht "
                    "auswertbar: %s: %s"
                    % (config_path, type(exc).__name__, exc)) from exc

    # ------------------------------------------------------------------
    # Auskunft ueber die Konfigurationsdatei
    # ------------------------------------------------------------------

    @property
    def config_geladen(self) -> bool:
        """Ob eine config.yaml ausgewertet werden konnte."""
        return self._config is not None

    @property
    def config(self):
        """
        Der geladene ConfigLoader - oder None (NEU Build 643).

        WOFUER: Mehrere Verwaltungswerkzeuge brauchen aus derselben
        config.yaml nicht nur einen Pfad, sondern auch Schwellenwerte
        (escalation.*, workload.overload.*, dashboard.ampel.*). Ohne diese
        Auskunft muessten sie die Datei ein zweites Mal oeffnen - und mit
        zwei Ladevorgaengen koennten Pfad und Schwelle im Grenzfall aus
        VERSCHIEDENEN Staenden derselben Datei stammen.

        Bewusst der ConfigLoader selbst und keine Kopie: Die vorhandenen
        Bauteile (ampel_thresholds_from_config und die anderen) erwarten ein
        Objekt mit get().
        """
        return self._config

    @property
    def config_pfad(self) -> Optional[Path]:
        """Der tatsaechlich geladene Pfad — oder None."""
        return self._config_pfad

    @property
    def config_meldung(self) -> Optional[str]:
        """
        Der Grund, WARUM keine config.yaml ausgewertet wurde — oder None.
        Ein Werkzeug hat diese Meldung auszugeben; sonst waere das Ausbleiben
        der Konfiguration ein stiller Vorgang (Grundregel 1).
        """
        return self._config_meldung

    # ------------------------------------------------------------------
    # Die Vorrangregel
    # ------------------------------------------------------------------

    def aufloesen(self, *, name: str, arg_wert: Any, arg_name: str,
                  config_schluessel: Optional[str], default: Any,
                  abgeleitet: Any = None, abgeleitet_quelle: str = "",
                  wandler: Optional[Callable[[Any], Any]] = None,
                  pflicht: bool = False,
                  meldung_anhaengen: bool = True) -> SettingOrigin:
        """
        Loest EINEN Wert auf und legt das Ergebnis ins Protokoll.

        Reihenfolge:
          1. arg_wert    (is not None)  → 'argument'
          2. abgeleitet  (is not None)  → 'abgeleitet'   (aus einem ANDEREN Argument)
          3. config.yaml, sofern der Schluessel dort STEHT → 'config.yaml'
          4. default                                      → 'default'

        Args:
            name:              Benennung im Werkzeug ('coordinator_db').
            arg_wert:          Wert des Kommandozeilen-Arguments oder None.
            arg_name:          Wie das Argument heisst ('--coordinator-db') —
                               fuer die Herkunftszeile.
            config_schluessel: Punkt-separierter Schluessel oder None, wenn der
                               Wert in config.yaml keine Entsprechung hat.
            default:           Fester Vorgabewert des Werkzeugs.
            abgeleitet:        Aus einem anderen Argument gebildeter Wert oder
                               None. Nur setzen, wenn dieses andere Argument
                               tatsaechlich uebergeben wurde.
            abgeleitet_quelle: Woraus abgeleitet wurde. Pflicht, sobald
                               'abgeleitet' gesetzt ist.
            wandler:           Optionale Typwandlung (int, float, str, Path ...).
                               Wird auf JEDEN Rueckgabewert angewandt, damit ein
                               Wert aus config.yaml denselben Typ hat wie einer
                               von der Kommandozeile. Scheitert sie bei einem
                               Wert aus config.yaml, ist das ein harter Fehler:
                               eine unlesbare Einstellung darf nicht stillschweigend
                               durch den Vorgabewert ersetzt werden.
            pflicht:           True -> es MUSS ein Wert zustande kommen. Bleibt
                               nur der Vorgabewert uebrig und ist der None,
                               wird SettingResolverError geworfen. Die Meldung
                               nennt BEIDE Wege, den Wert zu setzen (Argument
                               und Eintrag) - wer sie liest, muss nicht erst
                               den Quelltext aufschlagen.

                               WOFUER: Rund fuenfundzwanzig Verwaltungswerkzeuge
                               haben KEINEN Vorgabewert fuer ihren
                               Datenbankpfad, und das ist Absicht - ein
                               erratener Pfad waere schlimmer als ein Abbruch.
                               Ohne diese Weiche muesste jedes von ihnen die
                               Abbruchmeldung selbst formulieren, und genau so
                               ist die Vorrangregel dort fuenfundzwanzigmal
                               einzeln entstanden.

        Returns:
            SettingOrigin (der Wert steht in '.wert').

        Raises:
            SettingResolverError: bei pflicht=True ohne Wert, bei einer
                gescheiterten Wandlung, oder wenn 'abgeleitet' ohne
                Fundstelle uebergeben wurde.
        """
        if abgeleitet is not None and not str(abgeleitet_quelle).strip():
            raise SettingResolverError(
                "%s: 'abgeleitet' ist gesetzt, aber 'abgeleitet_quelle' ist "
                "leer — die Fundstelle waere nicht benennbar." % name)

        if arg_wert is not None:
            return self._merken(name, self._wandeln(name, arg_wert, wandler,
                                                    "Argument %s" % arg_name),
                                "argument", "Argument %s" % arg_name)

        if abgeleitet is not None:
            return self._merken(
                name, self._wandeln(name, abgeleitet, wandler, abgeleitet_quelle),
                "abgeleitet", abgeleitet_quelle)

        if (config_schluessel and self._config is not None
                and self._config.stammt_aus_datei(config_schluessel)):
            roh = self._config.get(config_schluessel)
            quelle = "%s aus %s" % (config_schluessel,
                                    self._config_pfad or "config.yaml")
            # Ein EINGETRAGENER, aber leerer Wert ('' oder null) ist keine
            # Einstellung, sondern ein Platzhalter. config.yaml haelt solche
            # Platzhalter bewusst vor (etwa 'browser.path: ""'). Er faellt
            # deshalb auf den Vorgabewert durch — aber sichtbar, ueber die
            # Herkunftszeile, und nicht heimlich.
            if roh is not None and not (isinstance(roh, str) and not roh.strip()):
                return self._merken(name, self._wandeln(name, roh, wandler, quelle),
                                    "config.yaml", quelle)

        if pflicht and default is None:
            # KEIN ERRATENER WERT. Die Meldung nennt beide Wege - das Argument
            # und den Eintrag -, damit sie ohne Blick in den Quelltext
            # brauchbar ist.
            wege = ["das Argument %s angeben" % arg_name]
            if config_schluessel:
                wege.append("'%s' in der config.yaml setzen%s"
                            % (config_schluessel,
                               " (%s)" % self._config_pfad
                               if self._config_pfad else ""))
            # 'meldung_anhaengen=False' setzt, wer die Meldung ueber eine
            # unlesbare config.yaml bereits selbst ausgegeben hat. Sonst
            # stuende sie zweimal untereinander - und ein Leser, der sie
            # zweimal sieht, sucht nach zwei Fehlern.
            anhang = (" " + self._config_meldung
                      if (self._config_meldung and meldung_anhaengen) else "")
            raise SettingResolverError(
                "Kein Wert fuer '%s'. Es gibt hier bewusst keinen "
                "Vorgabewert - ein erratener Wert waere schlimmer als ein "
                "Abbruch. Abhilfe: %s.%s"
                % (name, " ODER ".join(wege), anhang))

        return self._merken(
            name, self._wandeln(name, default, wandler, "Vorgabewert"),
            "default", "Vorgabewert des Werkzeugs (%s)" % default)

    # ------------------------------------------------------------------
    # Protokoll
    # ------------------------------------------------------------------

    def protokoll(self) -> Tuple[SettingOrigin, ...]:
        """Alle Aufloesungen in der Reihenfolge ihres Zustandekommens."""
        return tuple(self._protokoll)

    def herkunft(self, name: str) -> Optional[SettingOrigin]:
        """Die Aufloesung zu einem Namen — oder None, wenn es sie nicht gibt."""
        for eintrag in self._protokoll:
            if eintrag.name == name:
                return eintrag
        return None

    def protokoll_zeilen(self) -> List[str]:
        """
        Die Herkunftszeilen fuer die Konsolenausgabe, einschliesslich einer
        Kopfzeile zur Konfigurationsdatei. Ein Werkzeug gibt sie unveraendert
        aus; damit steht im Sitzungsprotokoll, mit welchen Werten es gelaufen
        ist.
        """
        zeilen: List[str] = []
        if self._config is not None:
            zeilen.append("config.yaml: %s" % self._config_pfad)
        elif self._config_meldung:
            zeilen.append(self._config_meldung)
        zeilen.extend(eintrag.zeile() for eintrag in self._protokoll)
        return zeilen

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    def _merken(self, name: str, wert: Any, herkunft: str,
                quelle: str) -> SettingOrigin:
        eintrag = SettingOrigin(name=name, wert=wert, herkunft=herkunft,
                                quelle=quelle)
        self._protokoll.append(eintrag)
        return eintrag

    @staticmethod
    def _wandeln(name: str, wert: Any, wandler: Optional[Callable[[Any], Any]],
                 quelle: str) -> Any:
        if wandler is None or wert is None:
            return wert
        try:
            return wandler(wert)
        except (TypeError, ValueError) as exc:
            raise SettingResolverError(
                "%s: Der Wert %r (%s) ist nicht in das erwartete Format zu "
                "wandeln (%s). Bitte die Angabe berichtigen — es wird KEIN "
                "Ersatzwert eingesetzt." % (name, wert, quelle, exc)) from exc


def als_pfad(wert: Any) -> Path:
    """
    Wandler fuer Pfadangaben. Eigenstaendig, damit die Werkzeuge nicht je fuer
    sich 'Path(str(x))' schreiben — und damit ein leerer Pfad hier auffaellt
    und nicht erst beim Oeffnen der Datenbank.
    """
    text = str(wert).strip()
    if not text:
        raise ValueError("leerer Pfad")
    return Path(text)
