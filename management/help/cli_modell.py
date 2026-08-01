# =============================================================================
# management/help/cli_modell.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H15)
# =============================================================================
# Zweck:
#   Die Datenklassen des CLI-Katalogs. Getrennt vom Katalog selbst, damit die
#   Struktur lesbar bleibt und der Katalog nur Daten enthaelt (Grundregel 10).
#
# WER IST DER ADRESSAT? - DIE WICHTIGSTE FESTLEGUNG DIESER DATEI.
#   Die Sicht-Hilfe (management/help/inhalt/) richtet sich an ERMITTELNDE. Fuer
#   sie gilt Regel H-1: keine Entwicklerbegriffe, keine Dateinamen, kein
#   "Server". Der CLI-Katalog richtet sich an die BETRIEBSSEITE - an die
#   Personen, die die Anlage aufsetzen, sichern und migrieren.
#
#   FUER SIE GILT REGEL H-1 NICHT, und zwar aus demselben Grund, aus dem sie
#   fuer die Ermittelnden gilt: Man spricht die Sprache des Adressaten. Wer
#   'coordinator.db' sichert, sucht 'coordinator.db' und nicht "die
#   Falldateien". Ein Katalog, der die Datei anders nennt als das Werkzeug,
#   waere hier unbrauchbar.
#
#   DAMIT DAS KEINE AUSREDE WIRD, ist die Trennung strukturell: der CLI-Katalog
#   ist ein EIGENER Bestand und fliesst nirgends in die Sicht-Hilfe ein. Die
#   Kapitel der Vollhilfe, die ab H19 aus diesem Katalog entstehen, sind
#   ausdruecklich als Betriebskapitel gekennzeichnet.
#
# WAS EIN GRUNDEINTRAG (H15) LEISTET UND WAS NICHT:
#   Er beantwortet: Wie rufe ich das Werkzeug auf? Wozu ist es da? Liest es
#   oder schreibt es - und WAS? Welche Datenbanken? Darf der Betrieb dabei
#   weiterlaufen? Schreibt es Belege?
#   Er beantwortet NOCH NICHT: geprueft gefahrene Beispielaufrufe, Exit-Codes,
#   Warntexte. Das ist die TIEFE, und sie folgt in H17/H18 - nachgehalten
#   ueber die Fehlliste, damit keine Luecke still bleibt (Grundregel 1).
#
# AENDERUNG BUILD 639 (Ticket 60e4236e): Neue Datenklasse CliKonfig und das
#   Feld CliEintrag.konfiguration. Der Katalog beantwortete bis dahin "wie
#   rufe ich es auf?", aber nicht "was stellt es fest ein, ohne dass ich etwas
#   uebergebe?". Fuer die Betriebsseite ist das die haeufigere Frage - und die
#   Antwort stand nirgends. Naeheres bei CliKonfig.
#
# Version: v0.8.639 - Build: 639 - 2026-08-01
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


class CliModellError(Exception):
    """Ein Katalogeintrag ist in sich unstimmig."""


#: Die zulaessigen Werte fuer 'art'. LESEND heisst: keine Datenbank wird
#: veraendert. Eine erzeugte AUSGABEDATEI (HTML, PDF, XLSX) macht ein Werkzeug
#: NICHT schreibend - das steht gesondert in 'ausgabe'. Diese Unterscheidung
#: ist keine Wortklauberei: sie entscheidet, ob ein Werkzeug unter den
#: Migrationsvorbehalt faellt.
ARTEN: Tuple[str, ...] = ("lesend", "schreibend", "gemischt")


@dataclass(frozen=True)
class CliBefehl:
    """
    Ein Unterbefehl eines Werkzeugs.

    name  - der Unterbefehl, wie er auf der Kommandozeile steht.
            Leer ("") bei Werkzeugen ohne Unterbefehle.
    art   - 'lesend' oder 'schreibend'. JE UNTERBEFEHL, nicht je Werkzeug:
            die meisten Werkzeuge sind gemischt, und die Frage "aendert
            dieser Aufruf etwas?" ist genau die, die vor dem Druecken der
            Eingabetaste zaehlt.
    zweck - ein Satz.
    """
    name: str
    art: str
    zweck: str

    def __post_init__(self) -> None:
        if self.art not in ("lesend", "schreibend"):
            raise CliModellError(
                "Unterbefehl '%s': art muss 'lesend' oder 'schreibend' sein, "
                "nicht '%s'." % (self.name, self.art))
        if not self.zweck.strip():
            raise CliModellError("Unterbefehl '%s' ohne Zweck" % self.name)


@dataclass(frozen=True)
class CliBeispiel:
    """
    Ein Beispielaufruf - und der Nachweis, dass er gelaufen ist.

    WARUM DAS FELD 'geprueft' PFLICHT IST (Grundregel 9, sinngemaess auf die
    Dokumentation angewandt): Ein Beispiel, das nie gelaufen ist, kostet die
    Zeit dessen, der ihm vertraut. Der Nachweis steht deshalb AM BEISPIEL und
    nicht in einem Vermerk daneben - dort waere er beim naechsten Umbau
    verloren.

    aufruf   - die Zeile, so wie sie einzugeben ist.
    wirkung  - was dabei herauskommt. Ein Beispiel ohne die erwartete Wirkung
               laesst offen, ob es funktioniert hat.
    geprueft - WO und WANN es gelaufen ist. Leer ist unzulaessig.
    """
    aufruf: str
    wirkung: str
    geprueft: str

    def __post_init__(self) -> None:
        for pflicht in ("aufruf", "wirkung", "geprueft"):
            if not str(getattr(self, pflicht)).strip():
                raise CliModellError(
                    "Beispiel '%s': Pflichtfeld '%s' ist leer. Ein "
                    "ungepruefter Beispielaufruf gehoert nicht in den "
                    "Katalog." % (self.aufruf or "?", pflicht))


@dataclass(frozen=True)
class CliKonfig:
    """
    EIN Eintrag aus config.yaml, den dieses Werkzeug tatsaechlich auswertet
    (NEU Build 639, Ticket 60e4236e).

    WARUM ES DIESES FELD GIBT: Der Katalog beantwortete bis Build 638 die
    Frage "wie rufe ich es auf?" - aber nicht die Frage "was stellt es fest
    ein, ohne dass ich etwas uebergebe?". Wer 'backup_admin' bedient, muss
    wissen, dass Zielverzeichnis und Aufbewahrung aus config.yaml kommen;
    aus der Optionsliste geht das nicht hervor, denn dort steht kein Wort
    davon. Ein Werkzeug, dessen wichtigste Stellgroessen unsichtbar sind,
    wird blind bedient.

    schluessel - der Punkt-separierte Schluessel, so wie er in config.yaml
                 steht ('backup.retention_count'). NICHT der Abschnittsname
                 allein: wer sucht, sucht die Zeile.
    bedeutung  - was dieser Eintrag FUER DIESES WERKZEUG bewirkt. Bewusst je
                 Werkzeug und nicht einmal zentral: derselbe Eintrag wirkt an
                 zwei Stellen verschieden, und die Erklaerung gehoert dorthin,
                 wo sie gebraucht wird.
    vorgabe    - was gilt, wenn der Eintrag FEHLT. Ohne diese Angabe bleibt
                 die wichtigste Frage offen ("muss ich das setzen?").
    argument   - das Kommandozeilen-Argument, das diesen Eintrag ueberstimmt,
                 oder "" wenn es keines gibt. Der Vorrang ist projektweit
                 Argument > config.yaml > Vorgabewert (Build 638).
    beleg      - WO im Quelltext der Eintrag gelesen wird (Datei und, wo
                 sinnvoll, Zeile). Pflichtfeld. Eine Behauptung ueber das
                 Verhalten eines Werkzeugs ohne Fundstelle ist im Rahmen
                 dieses Projekts keine Angabe, sondern eine Vermutung.
    """
    schluessel: str
    bedeutung: str
    vorgabe: str
    beleg: str
    argument: str = ""

    def __post_init__(self) -> None:
        for pflicht in ("schluessel", "bedeutung", "vorgabe", "beleg"):
            if not str(getattr(self, pflicht)).strip():
                raise CliModellError(
                    "Konfigurationseintrag '%s': Pflichtfeld '%s' ist leer. "
                    "Ohne Fundstelle und ohne Vorgabewert ist der Eintrag "
                    "nicht nachpruefbar."
                    % (self.schluessel or "?", pflicht))


#: Der ausdrueckliche Vermerk "geprueft, dieses Werkzeug liest KEINEN Eintrag
#: aus config.yaml". Er ist NICHT dasselbe wie 'konfiguration=None' (= noch
#: nicht geprueft), und diese Unterscheidung ist der ganze Zweck: sonst waere
#: ein ungeprueftes Werkzeug von einem geprueften ohne Eintraege nicht zu
#: unterscheiden, und die Fehlliste wuerde die Luecke verschweigen
#: (Grundregel 1).
KONFIG_KEINE: Tuple["CliKonfig", ...] = ()


@dataclass(frozen=True)
class CliTiefe:
    """
    Die Tiefeninhalte eines Eintrags (H17/H18). In H15 durchgehend None.

    beispiele  - Aufrufe, die VOR der Aufnahme tatsaechlich gefahren wurden.
    exit_codes - (Code, Bedeutung). Ein Exit-Code, der nicht 0 ist, ist nicht
                 zwingend ein Fehler; mehrere Werkzeuge melden damit einen
                 BEFUND.
    warnungen  - was schiefgehen kann und was dann gilt.

    DIE DREI SIND EINZELN NACHGEHALTEN: Exit-Codes und Warnungen lassen sich
    am Quelltext belegen, ein Beispiel muss GEFAHREN werden. Deshalb fuehrt
    der Katalog zwei Fehllisten - eine fuer "gar keine Tiefe" und eine fuer
    "Tiefe, aber ohne gepruefte Beispiele". Sonst saehe ein Eintrag mit
    Exit-Codes fertig aus, obwohl der teuerste Teil noch fehlt.
    """
    beispiele: Tuple[CliBeispiel, ...] = ()
    exit_codes: Tuple[Tuple[int, str], ...] = ()
    warnungen: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CliEintrag:
    """
    Ein Werkzeug im Katalog.

    schluessel   - eindeutige Kurzkennung (Dateiname ohne Endung).
    pfad         - der relative Pfad im Bestand. ER ist der Schluessel der
                   Scan-Pruefung: der Katalog wird gegen das Dateisystem
                   abgeglichen, nicht gegen eine gepflegte Liste.
    aufruf       - die Aufrufform, so wie sie in der Konsole einzugeben ist.
    titel        - kurze Benennung.
    gruppe       - Arbeitsbereich (fuer die gruppierte Ausgabe).
    zweck        - ein Satz.
    art          - 'lesend' | 'schreibend' | 'gemischt' (Gesamtcharakter).
    datenbanken  - welche Datenbanken beruehrt werden, je mit lesend/schreibend.
                   Leer heisst: gar keine.
    betrieb      - Betriebsvoraussetzung im Klartext: darf die Anlage
                   weiterlaufen, braucht es ein Wartungsfenster, ist es nur
                   ausserhalb des Betriebs sinnvoll?
    beleg        - schreibt das Werkzeug Belege ins Protokollbuch?
    befehle      - die Unterbefehle.
    ausgabe      - erzeugte Dateien (HTML, PDF, XLSX ...), soweit vorhanden.
    hinweis      - eine Einordnung, die man vor dem Aufruf gelesen haben muss
                   (nur ausserhalb des Betriebs, abgekuendigt, einmalige
                   Altmigration ...). Leer, wenn es nichts zu sagen gibt.
    tiefe        - H17/H18.
    konfiguration - die ausgewerteten Eintraege aus config.yaml (Build 639).
                   DREI ZUSTAENDE, und der mittlere ist der Grund fuer das
                   Ganze:
                     None         - NOCH NICHT GEPRUEFT. Der Eintrag steht
                                    in fehlliste_cli_konfiguration().
                     KONFIG_KEINE - geprueft: dieses Werkzeug liest keinen
                                    Eintrag aus config.yaml.
                     (CliKonfig,) - geprueft: diese Eintraege, mit Fundstelle.
                   Ohne die Unterscheidung von None und KONFIG_KEINE waere
                   "wir haben nichts gefunden" von "wir haben nicht gesucht"
                   nicht zu unterscheiden - und die Fehlliste wuerde eine
                   Luecke als erledigt ausweisen (Grundregel 1).
    """
    schluessel: str
    pfad: str
    aufruf: str
    titel: str
    gruppe: str
    zweck: str
    art: str
    datenbanken: Tuple[str, ...] = ()
    betrieb: str = ""
    beleg: bool = False
    befehle: Tuple[CliBefehl, ...] = ()
    ausgabe: str = ""
    hinweis: str = ""
    tiefe: Optional[CliTiefe] = None
    konfiguration: Optional[Tuple[CliKonfig, ...]] = None

    def __post_init__(self) -> None:
        if self.art not in ARTEN:
            raise CliModellError(
                "%s: art '%s' ist keine der zulaessigen (%s)."
                % (self.schluessel, self.art, ", ".join(ARTEN)))
        for pflicht in ("schluessel", "pfad", "aufruf", "titel", "gruppe",
                        "zweck", "betrieb"):
            if not str(getattr(self, pflicht)).strip():
                raise CliModellError(
                    "%s: Pflichtfeld '%s' ist leer."
                    % (self.schluessel or self.pfad, pflicht))
        # EIN GEMISCHTES WERKZEUG MUSS SEINE UNTERBEFEHLE NENNEN. Sonst
        # bliebe offen, WELCHER Aufruf schreibt - und genau das ist die
        # Frage, wegen der jemand den Katalog aufschlaegt.
        if self.art == "gemischt" and not self.befehle:
            raise CliModellError(
                "%s ist als 'gemischt' gefuehrt, nennt aber keine "
                "Unterbefehle. Dann ist nicht erkennbar, welcher Aufruf "
                "schreibt." % self.schluessel)

    def hat_tiefe(self) -> bool:
        """Ob der Eintrag ueber den Grundeintrag hinaus ausgearbeitet ist."""
        t = self.tiefe
        return bool(t and (t.beispiele or t.exit_codes or t.warnungen))

    def hat_beispiele(self) -> bool:
        """Ob GEPRUEFTE Beispielaufrufe vorliegen."""
        return bool(self.tiefe and self.tiefe.beispiele)

    def konfiguration_geprueft(self) -> bool:
        """
        Ob die Frage "welche Eintraege aus config.yaml wertet dieses Werkzeug
        aus?" ueberhaupt untersucht wurde (Build 639).

        ACHTUNG, DER UNTERSCHIED IST DER PUNKT: True auch dann, wenn das
        Ergebnis KONFIG_KEINE lautet - "geprueft, liest keinen Eintrag" ist
        eine Antwort. Nur None heisst "nicht gesucht", und nur das gehoert in
        die Fehlliste.
        """
        return self.konfiguration is not None

    def hat_konfiguration(self) -> bool:
        """Ob dieses Werkzeug mindestens einen Eintrag aus config.yaml liest."""
        return bool(self.konfiguration)

    def schreibt(self) -> bool:
        return self.art in ("schreibend", "gemischt")
