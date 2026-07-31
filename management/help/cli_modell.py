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
# Version: v0.8.606 - Build: 606 - 2026-07-31
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
class CliTiefe:
    """
    Die Tiefeninhalte eines Eintrags (H17/H18). In H15 durchgehend None.

    beispiele  - Aufrufe, die VOR der Aufnahme tatsaechlich gefahren wurden
                 (Grundregel 9, sinngemaess auf die Dokumentation angewandt).
    exit_codes - (Code, Bedeutung). Ein Exit-Code, der nicht 0 ist, ist nicht
                 zwingend ein Fehler; mehrere Werkzeuge melden damit einen
                 BEFUND.
    warnungen  - was schiefgehen kann und was dann gilt.
    """
    beispiele: Tuple[str, ...] = ()
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

    def schreibt(self) -> bool:
        return self.art in ("schreibend", "gemischt")
