# =============================================================================
# management/help/cli_html.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H19)
# =============================================================================
# Zweck:
#   Die BETRIEBSKAPITEL der Vollhilfe: der CLI-Katalog als HTML, in derselben
#   Seite wie die Sichtkapitel und in derselben Bauart.
#
# DIE TRAGENDE FESTLEGUNG: KEIN DRITTER BESTAND.
#   Es gibt genau EINE Quelle fuer die Werkzeugbeschreibungen - den Katalog in
#   management/help/cli_katalog.py. Die Konsole liest ihn ueber cli_text.py,
#   die Vollhilfe ueber dieses Modul. Ein abgeschriebener HTML-Bestand daneben
#   waere binnen zweier Builds abgedriftet, und dann gaebe es zwei Antworten
#   auf die Frage, ob ein Aufruf schreibt.
#
# WARUM DANN NICHT EINFACH DIE ASCII-AUSGABE IN EIN <pre> STECKEN?
#   Weil cli_text.py auf eine ganz bestimmte Lage hin gebaut ist: 78 Zeichen,
#   reines ASCII, keine Escape-Sequenzen, Windows-Eingabeaufforderung. Genau
#   diese drei Festlegungen sind im HTML falsch - dort gibt es Umlaute, freien
#   Umbruch und Sprungmarken. Ein <pre>-Block waere im Handbuch nicht
#   durchsuchbar, nicht verlinkbar und im Druck an der falschen Stelle
#   umbrochen. Deshalb ein EIGENES Rendering ueber DIESELBEN Daten.
#
# ADRESSAT UND KENNZEICHNUNG (Regel H-2, documents/rules-help.md):
#   Regel H-1 (Anwendersprache) gilt hier ausdruecklich NICHT. Der Adressat
#   ist die Betriebsseite; fuer sie ist 'coordinator.db' der Name der Sache.
#   DAMIT DAS NICHT ZUR STILLEN AUSNAHME WIRD, traegt jedes Betriebskapitel
#   eine sichtbare Kennzeichnung im Kopf, und der Betriebsteil hat einen
#   eigenen Vorspann, der den Adressatenwechsel benennt. Wer im Handbuch
#   blaettert, soll an der Stelle merken, dass hier eine andere Sprache
#   gesprochen wird - und warum.
#
# SICHTBARKEIT (Entscheidung mc, 2026-08-01):
#   Die Betriebskapitel haengen an 'ops.view' - demselben Recht wie die
#   Sichten 'Integritaet / Betrieb', 'Audit-Explorer' und
#   'Fremdforum-Promotion' (Beleg: management/server/static/cockpit.js
#   Zeilen 261, 263, 281; management/server/management_app.py Zeile 442
#   CAP_OPS_VIEW). Begruendung: ein Betriebskapitel gehoert zu KEINER Sicht,
#   kann also kein Recht erben - die vorhandene Sperre (E1,
#   management/help/sichtbarkeit.py) haette hier nichts, woran sie greift.
#   Statt sie umzubauen, bekommt der Betriebsteil EIN Recht, und zwar das der
#   Sichten, die denselben Adressaten haben.
#
#   OHNE DIESES RECHT IST DER BETRIEBSTEIL LEER - nicht ausgegraut, nicht
#   angedeutet: leer. Weder im Verzeichnis noch im Suchindex noch im Druck
#   erscheint dann etwas. Das ist dieselbe strenge Lesart von E1, mit der
#   gruppen_mit_kapiteln() leere Gruppenueberschriften unterdrueckt: eine
#   Ueberschrift ohne Inhalt ist selbst schon eine Auskunft.
#
# REINE FUNKTIONEN. Kein Datei-, Netz-, Datenbank- oder Uhrzugriff. Die
#   Filterung geschieht VOR dem Rendern (baue_betriebsgliederung); die
#   Renderfunktionen bekommen die ungefilterten Daten nie zu sehen. Dieselbe
#   Arbeitsteilung wie in render_html.py, und aus demselben Grund: eine
#   Sperre, die im Renderer sitzt, laesst sich nicht gegen eine Rechte-Matrix
#   pruefen.
#
# WAS DIESES MODUL NICHT TUT (H19, Build 621): Es verdrahtet sich nicht
#   selbst. render_html.py und die Route /help bleiben in diesem Build
#   unberuehrt; die Vollhilfe sieht unveraendert aus. Der Einbau folgt in
#   Build 622. Grund: Renderer und Verdrahtung sind zwei Fehlerquellen, und
#   getrennt gebaut ist jede einzeln belegbar (Grundregel 2).
#
# Version: v0.8.621 - Build: 621 - 2026-08-01
# =============================================================================

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from management.help.cli_katalog import (
    CLI_KATALOG, GRUPPEN_REIHENFOLGE,
)
from management.help.cli_modell import CliEintrag
from management.help.cli_text import hilfe_aufruf

#: Das Recht, an dem der gesamte Betriebsteil haengt (Entscheidung mc
#: 2026-08-01). EINE Konstante, damit die Sperre an genau einer Stelle steht -
#: eine ueber Route, Renderer und Test verteilte Rechtsangabe waere nicht
#: pruefbar, sondern nur ausprobierbar.
CLI_RECHT: str = "ops.view"

#: Der Praefix aller Sprungmarken des Betriebsteils. Er trennt den Namensraum
#: der Werkzeuge vom Namensraum der Sichten: eine Sicht 'audit' und ein
#: Werkzeug 'audit_export' sollen sich nicht ueber eine gleichlautende Marke
#: in die Quere kommen koennen.
KAPITEL_PRAEFIX: str = "cli"

#: Die Ueberschrift des Betriebsteils im Inhaltsverzeichnis.
BETRIEBSTEIL_TITEL: str = "Werkzeuge der Kommandozeile (Betrieb)"

#: Die Marke, die JEDES Betriebskapitel im Kopf traegt.
BETRIEBSMARKE: str = "Betriebskapitel"

#: Der Satz, der die Kennzeichnung erklaert - woertlich gleich in jedem
#: Kapitel, damit er beim Ueberfliegen wiedererkannt und nach dem zweiten Mal
#: ueberlesen werden kann.
BETRIEBSHINWEIS: str = (
    "Dieses Kapitel richtet sich an die Betriebsseite und nennt Dateinamen, "
    "Datenbanken und Aufrufe beim Namen. Es ist keine Anleitung fuer die "
    "Ermittlungsarbeit.")

#: Der Hinweis fuer ein Werkzeug ohne gefahrenen Beispielaufruf. Er steht
#: sichtbar IM Kapitel und nicht in einer Liste daneben (Grundregel 1): wer
#: das Kapitel liest, soll nicht erst anderswo nachsehen muessen, ob das
#: Fehlen eines Beispiels Absicht oder Versaeumnis ist.
OHNE_BEISPIEL_TEXT: str = (
    "Fuer dieses Werkzeug ist kein Beispielaufruf aufgenommen: es gibt "
    "keinen Lauf, der sich gefahrlos vorfuehren liesse. Ein erfundenes "
    "Beispiel steht hier bewusst nicht - es wuerde die Zeit dessen kosten, "
    "der ihm vertraut.")

#: Die Kurzmarke im Inhaltsverzeichnis fuer eben diese Werkzeuge.
OHNE_BEISPIEL_MARKE: str = "ohne Beispiellauf"

#: Der Hinweis fuer einen Eintrag ganz ohne Tiefeninhalt. Seit Build 620 hat
#: kein Eintrag des Auslieferungskatalogs diesen Zustand mehr - die Ausgabe
#: bleibt trotzdem bestehen, weil ein neu aufgenommenes Werkzeug genau hier
#: anfaengt und dann nicht wie ein fertiges aussehen darf.
OHNE_TIEFE_TEXT: str = (
    "Beispielaufrufe, Rueckgabewerte und Warnhinweise sind fuer dieses "
    "Werkzeug noch nicht erfasst.")

#: Der Hinweis fuer ein Werkzeug, bei dem noch nicht erhoben ist, welche
#: Eintraege aus config.yaml es auswertet (NEU Build 639, Ticket 60e4236e).
#: Der letzte Satz ist der wichtige: er verhindert, dass ein ungeprueftes
#: Werkzeug als "hat keine" gelesen wird.
OHNE_KONFIGURATION_TEXT: str = (
    "Fuer dieses Werkzeug ist noch nicht erhoben, welche Eintraege aus "
    "config.yaml es auswertet. Das heisst NICHT, dass es keine gibt.")

#: Klartext zur Art eines Werkzeugs - woertlich dieselben Saetze wie in
#: cli_text.zeige_text(). Zwei Formulierungen fuer dieselbe Aussage waeren
#: der Anfang genau des Drifts, den dieses Modul vermeiden soll.
ART_KLARTEXT: Dict[str, str] = {
    "lesend": "Liest nur. Keine Datenbank wird veraendert.",
    "schreibend": "Veraendert Daten.",
    "gemischt": "Je nach Unterbefehl lesend oder schreibend - siehe die "
                "Tabelle der Unterbefehle.",
}

#: Die Abschnitte eines Betriebskapitels, in Ausgabereihenfolge, mit ihren
#: Ueberschriften. Die Reihenfolge ist DIESELBE wie in cli_text.zeige_text():
#: Zweck, Aufruf, Wirkung, Daten, Betrieb, dann die Tiefeninhalte. Wer beide
#: Ausgaben nebeneinanderlegt, soll dieselbe Gliederung sehen.
ABSCHNITTE: Tuple[Tuple[str, str], ...] = (
    ("zweck", "Zweck"),
    ("aufruf", "Aufruf"),
    ("wirkung", "Was es tut"),
    ("daten", "Datenbanken und Belege"),
    ("betrieb", "Betriebsvoraussetzung"),
    # NEU Build 639 (Ticket 60e4236e). Der Abschnitt steht VOR den
    # Beispielen und nach der Betriebsvoraussetzung: Wer ein Werkzeug zum
    # ersten Mal fahren will, klaert erst, was die Anlage ihm dabei fest
    # vorgibt, und sieht sich dann die Aufrufe an.
    ("einstellungen", "Einstellungen in config.yaml"),
    ("beispiele", "Beispiele"),
    ("rueckgabewerte", "Rueckgabewerte"),
    ("zu_beachten", "Zu beachten"),
)

#: Die Abschnitte, die IMMER erscheinen - auch dann, wenn der Katalog dazu
#: nichts fuehrt. Fuer sie gibt es an der Stelle einen ehrlichen Satz statt
#: einer Leerstelle. 'beispiele' steht bewusst hier: das Fehlen eines
#: Beispiels ist die Auskunft, auf die es bei sechs Werkzeugen ankommt.
PFLICHTABSCHNITTE: Tuple[str, ...] = (
    "zweck", "aufruf", "wirkung", "daten", "betrieb", "beispiele",
    # 'einstellungen' ist Pflicht (Build 639) - aus demselben Grund wie
    # 'beispiele': Die Auskunft "dieses Werkzeug wertet KEINEN Eintrag aus"
    # und die Auskunft "das ist noch nicht erhoben" sind beide etwas wert,
    # und ohne den Abschnitt waeren sie voneinander nicht zu unterscheiden.
    "einstellungen",
)


class CliHtmlError(Exception):
    """Der Betriebsteil ist in sich unstimmig."""


# -----------------------------------------------------------------------------
# Sprungmarken
# -----------------------------------------------------------------------------

def kapitel_id(schluessel: str) -> str:
    """
    Die Sprungmarke eines Betriebskapitels: 'cli-<kennung>'.

    EINE Stelle, an der die Form festliegt - genau wie anker_id() in
    render_html.py. Verzeichnis, Kapitel, Blaetterleiste und Suchindex bilden
    sie alle hierueber; damit koennen sie nicht auseinanderlaufen.
    """
    return "%s-%s" % (KAPITEL_PRAEFIX, schluessel)


def abschnitt_id(schluessel: str, anker: str) -> str:
    """Die Sprungmarke eines Abschnitts: 'cli-<kennung>-<anker>'."""
    return "%s-%s" % (kapitel_id(schluessel), anker)


# -----------------------------------------------------------------------------
# Das gefilterte Seitenmodell
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Betriebsgliederung:
    """
    Der gefilterte Betriebsteil: Arbeitsbereiche in Katalogfolge mit ihren
    Werkzeugen.

    LEER heisst: diese Person hat 'ops.view' nicht. Es gibt keinen zweiten
    Grund, aus dem der Teil leer waere - der Katalog selbst ist seit Build 606
    vollzaehlig und wird gegen den Bestand abgeglichen
    (cli_katalog.verify_cli_abgedeckt).
    """
    gruppen: Tuple[Tuple[str, Tuple[CliEintrag, ...]], ...] = ()

    def eintraege(self) -> Tuple[CliEintrag, ...]:
        """Alle Werkzeuge in Ausgabereihenfolge."""
        raus: List[CliEintrag] = []
        for _, e in self.gruppen:
            raus.extend(e)
        return tuple(raus)

    def leer(self) -> bool:
        return not self.gruppen

    def ohne_beispiele(self) -> Tuple[str, ...]:
        """
        Die Kennungen, zu denen kein gefahrener Beispielaufruf vorliegt.

        Sie wird GERECHNET und nicht gefuehrt - dieselbe Entscheidung wie bei
        cli_katalog.fehlliste_cli_beispiele(), und aus demselben Grund: eine
        gepflegte Liste kann luegen, eine gerechnete nicht.
        """
        return tuple(e.schluessel for e in self.eintraege()
                     if not e.hat_beispiele())


def baue_betriebsgliederung(capabilities: Iterable[str],
                            katalog: Sequence[CliEintrag] = CLI_KATALOG
                            ) -> Betriebsgliederung:
    """
    Baut den Betriebsteil - oder eben nicht.

    Die Rechtepruefung ist bewusst ALLES ODER NICHTS und nicht je Werkzeug:
    der Katalog fuehrt kein Recht je Eintrag, und eines zu erfinden hiesse,
    65 Einzelentscheidungen zu treffen, die niemand belegt hat. Ein Recht,
    eine Aussage (Entscheidung mc 2026-08-01).
    """
    if CLI_RECHT not in set(capabilities):
        return Betriebsgliederung()

    je_gruppe: Dict[str, List[CliEintrag]] = {}
    for e in katalog:
        je_gruppe.setdefault(e.gruppe, []).append(e)

    # Reihenfolge: GRUPPEN_REIHENFOLGE zuerst - dieselbe Ordnung wie in der
    # Konsole. Eine Gruppe, die dort nicht steht, wird NICHT verschluckt,
    # sondern hinten angehaengt; verify_katalog_konsistent() faengt sie
    # ohnehin ab, aber ein Renderer, der still etwas weglaesst, waere die
    # falsche zweite Verteidigungslinie (Grundregel 1).
    folge: List[str] = [g for g in GRUPPEN_REIHENFOLGE if g in je_gruppe]
    folge.extend(sorted(g for g in je_gruppe if g not in GRUPPEN_REIHENFOLGE))

    return Betriebsgliederung(tuple(
        (g, tuple(je_gruppe[g])) for g in folge))


def verify_betriebsteil_vollzaehlig(
        gliederung: Betriebsgliederung,
        katalog: Sequence[CliEintrag] = CLI_KATALOG) -> None:
    """
    Mit Recht muss der Betriebsteil JEDEN Katalogeintrag fuehren.

    Warum eine eigene Pruefung und nicht nur ein Test: Ein Werkzeug, das im
    Handbuch fehlt, faellt niemandem auf - im Gegensatz zu einem, das zuviel
    dasteht. Diese Richtung braucht ein Netz (Grundregel 1).
    """
    if gliederung.leer():
        return
    gezeigt = {e.schluessel for e in gliederung.eintraege()}
    erwartet = {e.schluessel for e in katalog}
    fehlend = sorted(erwartet - gezeigt)
    if fehlend:
        raise CliHtmlError(
            "Betriebsteil unvollstaendig - diese Werkzeuge haben kein "
            "Kapitel: %s" % ", ".join(fehlend))
    fremd = sorted(gezeigt - erwartet)
    if fremd:
        raise CliHtmlError(
            "Betriebsteil fuehrt Kapitel ohne Katalogeintrag: %s"
            % ", ".join(fremd))


# -----------------------------------------------------------------------------
# Rendern
# -----------------------------------------------------------------------------

def _e(text: Optional[str]) -> str:
    return html.escape(text or "", quote=True)


def _abschnitt(schluessel: str, anker: str, titel: str,
               inhalt: Sequence[str]) -> List[str]:
    """
    Ein Abschnitt mit Sprungmarke. 'inhalt' sind FERTIGE HTML-Bruchstuecke -
    das Maskieren ist Sache des Aufrufers, weil nur er weiss, was Text und was
    Auszeichnung ist.
    """
    return (['<section class="aiw-h-abschnitt" id="%s">'
             % _e(abschnitt_id(schluessel, anker)),
             "<h3>%s</h3>" % _e(titel)]
            + list(inhalt) + ["</section>"])


def _zweck_inhalt(e: CliEintrag) -> List[str]:
    return ["<p>%s</p>" % _e(e.zweck)]


def _aufruf_inhalt(e: CliEintrag) -> List[str]:
    """
    Aufrufform, Datei und der Verweis auf die eingebaute Hilfe.

    DER VERWEIS AUF '--help' STEHT HIER UND NICHT AM ENDE (anders als in der
    Konsole): Im Handbuch liest man nicht zwangslaeufig bis zum Schluss, und
    die Auskunft "die vollstaendige Optionsliste sagt das Werkzeug selbst"
    gehoert neben die Aufrufform, auf die sie sich bezieht.
    """
    return [
        '<p class="aiw-h-cli-aufruf"><code>%s</code></p>' % _e(e.aufruf),
        "<p>Datei im Bestand: <code>%s</code></p>" % _e(e.pfad),
        "<p>Die vollstaendige Liste der Optionen nennt das Werkzeug selbst: "
        "<code>%s</code>. Sie steht bewusst nicht hier - eine abgeschriebene "
        "Optionsliste veraltet, die eingebaute nicht.</p>"
        % _e(hilfe_aufruf(e.aufruf)),
    ]


def _wirkung_inhalt(e: CliEintrag) -> List[str]:
    """Art, erzeugte Dateien und die Unterbefehle als Tabelle."""
    teile: List[str] = ["<p>%s</p>" % _e(ART_KLARTEXT.get(
        e.art, "Art nicht angegeben."))]
    if e.ausgabe:
        teile.append("<p>Erzeugt: %s</p>" % _e(e.ausgabe))
    if e.befehle:
        # TABELLE STATT LISTE: die Frage vor dem Druecken der Eingabetaste
        # lautet "schreibt DIESER Unterbefehl?". In einer Tabelle steht die
        # Antwort in einer eigenen Spalte und laesst sich ueberfliegen; in
        # einem Fliesstext muss man sie suchen.
        teile.append('<table class="aiw-h-cli-tabelle">')
        teile.append("<thead><tr><th>Unterbefehl</th><th>Art</th>"
                     "<th>Wozu</th></tr></thead><tbody>")
        for b in e.befehle:
            art = "schreibend" if b.art == "schreibend" else "lesend"
            teile.append(
                '<tr><td><code>%s</code></td>'
                '<td class="aiw-h-cli-art-%s">%s</td><td>%s</td></tr>'
                % (_e(b.name or "(ohne Unterbefehl)"), _e(art), _e(art),
                   _e(b.zweck)))
        teile.append("</tbody></table>")
    return teile


def _daten_inhalt(e: CliEintrag) -> List[str]:
    """Beruehrte Datenbanken und die Belegfrage."""
    teile: List[str] = []
    if e.datenbanken:
        teile.append("<ul>")
        for d in e.datenbanken:
            teile.append("<li><code>%s</code></li>" % _e(d))
        teile.append("</ul>")
    else:
        teile.append("<p>Keine Datenbank wird geoeffnet.</p>")
    teile.append("<p>%s</p>" % _e(
        "Schreibt Belege ins Protokollbuch (audit_log)." if e.beleg
        else "Schreibt keine Belege ins Protokollbuch."))
    return teile


def _betrieb_inhalt(e: CliEintrag) -> List[str]:
    teile = ["<p>%s</p>" % _e(e.betrieb)]
    if e.hinweis:
        # Der Hinweis ist die Einordnung, die man VOR dem Aufruf gelesen
        # haben muss (cli_modell.CliEintrag). Deshalb abgesetzt und nicht als
        # weiterer Absatz - sonst liest man ihn als Nachtrag.
        teile.append('<p class="aiw-h-cli-hinweis"><strong>Hinweis:</strong> '
                     "%s</p>" % _e(e.hinweis))
    return teile


def _einstellungen_inhalt(e: CliEintrag) -> List[str]:
    """
    Die ausgewerteten Eintraege aus config.yaml (NEU Build 639).

    DREI ZUSTAENDE, DREI AUSGABEN - und der Unterschied zwischen den letzten
    beiden ist der Grund fuer den ganzen Abschnitt:
      * Eintraege vorhanden -> Tabelle mit Bedeutung, Vorgabe, Vorrang, Beleg.
      * geprueft, keine     -> ein Satz, der das ausdruecklich sagt.
      * nicht erhoben       -> ein Satz, der das ebenso ausdruecklich sagt.
    Wer nur den ersten Fall ausgaebe, liesse den Leser bei jedem uebrigen
    Werkzeug raten, ob es nichts gibt oder ob niemand nachgesehen hat.
    """
    if e.hat_konfiguration():
        teile: List[str] = [
            "<p>%s</p>" % _e(
                "Diese Eintraege wertet das Werkzeug aus. Der Vorrang ist "
                "Argument vor config.yaml vor Vorgabewert."),
            '<table class="aiw-h-cli-tabelle">',
            "<thead><tr><th>Eintrag</th><th>Bedeutung</th>"
            "<th>ohne Eintrag</th><th>ueberstimmt durch</th>"
            "<th>Fundstelle</th></tr></thead><tbody>",
        ]
        for k in e.konfiguration:
            teile.append(
                "<tr><td><code>%s</code></td><td>%s</td><td>%s</td>"
                "<td>%s</td><td>%s</td></tr>"
                % (_e(k.schluessel), _e(k.bedeutung), _e(k.vorgabe),
                   ("<code>%s</code>" % _e(k.argument)) if k.argument
                   else "&ndash;",
                   _e(k.beleg)))
        teile.append("</tbody></table>")
        return teile
    if e.konfiguration_geprueft():
        return ["<p>%s</p>" % _e(
            "Geprueft: Dieses Werkzeug wertet keinen Eintrag aus config.yaml "
            "aus.")]
    return ['<p class="aiw-h-offen">%s</p>' % _e(OHNE_KONFIGURATION_TEXT)]


def _beispiele_inhalt(e: CliEintrag) -> List[str]:
    """
    Die gefahrenen Beispielaufrufe - oder der ehrliche Grund, warum keiner
    dasteht.

    DER PRUEFNACHWEIS STEHT AM BEISPIEL, nicht in einer Fussnote. Die
    Begruendung dafuer steht im Kopf von cli_modell.CliBeispiel und gilt hier
    unveraendert: ein Beispiel, das nie gelaufen ist, kostet die Zeit dessen,
    der ihm vertraut.
    """
    t = e.tiefe
    if t is None or not t.beispiele:
        return ['<p class="aiw-h-offen">%s</p>' % _e(OHNE_BEISPIEL_TEXT)]
    teile: List[str] = []
    for bsp in t.beispiele:
        teile.append('<div class="aiw-h-cli-beispiel">')
        # <pre> um den Aufruf: eine ueber zwei Zeilen umbrochene Befehlszeile
        # laesst sich nicht kopieren, und genau dafuer steht sie da. Der
        # Umbruch wird per CSS erlaubt, aber nicht erzwungen.
        teile.append("<pre><code>%s</code></pre>" % _e(bsp.aufruf))
        teile.append("<p>%s</p>" % _e(bsp.wirkung))
        teile.append('<p class="aiw-h-cli-nachweis">Gefahren: %s</p>'
                     % _e(bsp.geprueft))
        teile.append("</div>")
    return teile


def _rueckgabe_inhalt(e: CliEintrag) -> List[str]:
    t = e.tiefe
    if t is None or not t.exit_codes:
        return []
    teile = ['<table class="aiw-h-cli-tabelle">',
             "<thead><tr><th>Wert</th><th>Bedeutung</th></tr></thead><tbody>"]
    for code, bedeutung in t.exit_codes:
        teile.append("<tr><td><code>%d</code></td><td>%s</td></tr>"
                     % (code, _e(bedeutung)))
    teile.append("</tbody></table>")
    return teile


def _beachten_inhalt(e: CliEintrag) -> List[str]:
    t = e.tiefe
    if t is None or not t.warnungen:
        return []
    teile = ['<ul class="aiw-h-cli-warnungen">']
    for w in t.warnungen:
        teile.append("<li>%s</li>" % _e(w))
    teile.append("</ul>")
    return teile


#: Anker -> Inhaltsfunktion. Als Tabelle und nicht als if-Kette, damit
#: ABSCHNITTE und die Erzeugung nicht getrennt voneinander gepflegt werden
#: koennen; verify_abschnitte_vollstaendig() haelt beide zusammen.
_INHALT = {
    "zweck": _zweck_inhalt,
    "aufruf": _aufruf_inhalt,
    "wirkung": _wirkung_inhalt,
    "daten": _daten_inhalt,
    "betrieb": _betrieb_inhalt,
    "einstellungen": _einstellungen_inhalt,
    "beispiele": _beispiele_inhalt,
    "rueckgabewerte": _rueckgabe_inhalt,
    "zu_beachten": _beachten_inhalt,
}


def verify_abschnitte_vollstaendig() -> None:
    """
    Zu jedem Abschnitt der Gliederung gibt es eine Inhaltsfunktion und
    umgekehrt. Eine Ueberschrift ohne Inhalt waere eine leere Zusage, eine
    Inhaltsfunktion ohne Ueberschrift toter Code.
    """
    benannt = {a for a, _ in ABSCHNITTE}
    gebaut = set(_INHALT)
    if benannt != gebaut:
        raise CliHtmlError(
            "Abschnitte und Inhaltsfunktionen decken sich nicht: nur benannt "
            "%s, nur gebaut %s"
            % (sorted(benannt - gebaut) or "-", sorted(gebaut - benannt) or "-"))
    fremd = sorted(set(PFLICHTABSCHNITTE) - benannt)
    if fremd:
        raise CliHtmlError(
            "Pflichtabschnitte ohne Gliederungseintrag: %s" % ", ".join(fremd))


def _blaetterleiste(vorher: Optional[CliEintrag],
                    nachher: Optional[CliEintrag]) -> str:
    """
    Voriges / naechstes Werkzeug.

    DIE KETTE BLEIBT INNERHALB DES BETRIEBSTEILS und laeuft nicht in die
    Sichtkapitel hinein. Das ist Absicht: die beiden Teile haben verschiedene
    Adressaten, und ein Weiter-Verweis vom letzten Sichtkapitel in die
    Betriebskapitel wuerde die Grenze verwischen, die BETRIEBSHINWEIS gerade
    zieht.
    """
    links: List[str] = []
    if vorher is not None:
        links.append('<a class="aiw-h-vor" href="#%s">&larr; %s</a>'
                     % (_e(kapitel_id(vorher.schluessel)), _e(vorher.schluessel)))
    if nachher is not None:
        links.append('<a class="aiw-h-zurueck" href="#%s">%s &rarr;</a>'
                     % (_e(kapitel_id(nachher.schluessel)),
                        _e(nachher.schluessel)))
    if not links:
        return ""
    return ('<nav class="aiw-h-blaettern" aria-label="Werkzeuge">%s</nav>'
            % "".join(links))


def kapitel_html(e: CliEintrag,
                 vorher: Optional[CliEintrag] = None,
                 nachher: Optional[CliEintrag] = None) -> str:
    """Ein Werkzeug als Kapitel."""
    teile: List[str] = [
        '<article class="aiw-h-kapitel aiw-h-betrieb" id="%s">'
        % _e(kapitel_id(e.schluessel)),
        # DIE UEBERSCHRIFT IST DIE KENNUNG, nicht der Titel: gesucht wird ein
        # Werkzeug immer unter dem Namen, den man auf der Kommandozeile
        # eintippt. Der Titel steht daneben.
        "<h2><code>%s</code> <span class=\"aiw-h-betrieb-titel\">%s</span></h2>"
        % (_e(e.schluessel), _e(e.titel)),
        '<p class="aiw-h-betrieb-marke"><strong>%s</strong> &middot; '
        "Arbeitsbereich %s</p>" % (_e(BETRIEBSMARKE), _e(e.gruppe)),
        '<p class="aiw-h-recht"><strong>Rechtelage:</strong> Sichtbar mit '
        "dem Recht <code>%s</code>. %s</p>" % (_e(CLI_RECHT),
                                               _e(BETRIEBSHINWEIS)),
    ]

    hat_tiefe = e.hat_tiefe()
    for anker, titel in ABSCHNITTE:
        inhalt = _INHALT[anker](e)
        if not inhalt and anker not in PFLICHTABSCHNITTE:
            # Ein Abschnitt ohne Inhalt entfaellt - ABER nur, wenn er kein
            # Pflichtabschnitt ist. Fuer 'beispiele' gilt das gerade nicht.
            continue
        teile.extend(_abschnitt(e.schluessel, anker, titel, inhalt))

    if not hat_tiefe:
        # Kein stilles Weglassen: dass Rueckgabewerte und Warnhinweise fehlen,
        # bekommt eine eigene Ueberschrift. Ohne sie saehe ein Grundeintrag
        # aus wie ein fertiger. (Seit Build 620 trifft das keinen Eintrag des
        # Auslieferungskatalogs mehr - ein NEU aufgenommenes Werkzeug faengt
        # aber genau hier an.)
        teile.extend(_abschnitt(
            e.schluessel, "ausarbeitung", "Ausarbeitung",
            ['<p class="aiw-h-offen">%s</p>' % _e(OHNE_TIEFE_TEXT)]))

    teile.append(_blaetterleiste(vorher, nachher))
    teile.append("</article>")
    return "\n".join(t for t in teile if t)


def vorspann_html(gliederung: Betriebsgliederung) -> str:
    """
    Der Vorspann des Betriebsteils: der Adressatenwechsel, benannt.

    ER IST KEIN KAPITEL und bekommt deshalb auch keinen Verzeichniseintrag -
    er ist die Erklaerung der Ueberschrift, unter der die Kapitel stehen.
    Auch die Zahl der Werkzeuge ohne Beispiellauf steht hier: sie gehoert an
    den Anfang des Teils und nicht in eine Fussnote, sonst liest sie niemand,
    der sich auf ein einzelnes Kapitel verlaesst.
    """
    if gliederung.leer():
        return ""
    anzahl = len(gliederung.eintraege())
    ohne = gliederung.ohne_beispiele()
    teile = [
        '<section class="aiw-h-betrieb-vorspann" id="%s-vorspann">'
        % _e(KAPITEL_PRAEFIX),
        "<h2>%s</h2>" % _e(BETRIEBSTEIL_TITEL),
        "<p>Die folgenden %d Kapitel beschreiben die Werkzeuge, mit denen die "
        "Anlage aufgesetzt, gesichert, migriert und geprueft wird. Sie "
        "richten sich an die Betriebsseite und nennen Dateien und Datenbanken "
        "bei ihrem Namen - anders als die vorangehenden Kapitel, die fuer die "
        "Ermittlungsarbeit geschrieben sind.</p>" % anzahl,
        "<p>Jedes Kapitel sagt an derselben Stelle, ob ein Aufruf nur liest "
        "oder etwas veraendert, welche Datenbanken er beruehrt, ob der "
        "Betrieb dabei weiterlaufen darf und ob er Belege ins Protokollbuch "
        "schreibt. Beispielaufrufe sind gefahren worden; wo und wann, steht "
        "am Beispiel.</p>",
    ]
    if ohne:
        teile.append(
            '<p class="aiw-h-offen">Zu %d der %d Werkzeuge steht kein '
            "Beispielaufruf: %s. Fuer sie gibt es keinen Lauf, der sich "
            "gefahrlos vorfuehren liesse. Das ist im jeweiligen Kapitel "
            "wiederholt.</p>"
            % (len(ohne), anzahl, _e(", ".join(ohne))))
    else:
        teile.append("<p>Zu jedem Werkzeug steht mindestens ein gefahrener "
                     "Beispielaufruf.</p>")
    teile.append("</section>")
    return "\n".join(teile)


def verzeichnis_html(gliederung: Betriebsgliederung) -> str:
    """
    Der Betriebsteil des Inhaltsverzeichnisses.

    Die Markup-Form ist ZEICHENGLEICH mit der der Sichtkapitel
    (render_html._verzeichnis_html): 'h3[data-gruppe]' und
    'ul[data-gruppe] > li[data-sicht]'. Damit filtert die vorhandene
    Kapitelsuche (static/help.js) den Betriebsteil mit, ohne dass eine Zeile
    JavaScript geaendert werden muesste.

    ZUM ATTRIBUTNAMEN 'data-sicht': Er ist der Schluessel, ueber den help.js
    einen Verzeichniseintrag wiederfindet - keine Aussage darueber, dass der
    Eintrag eine Sicht WAERE. Ihn hier umzubenennen haette eine Aenderung an
    help.js und an dessen Tests erzwungen, ohne dass irgendetwas dadurch
    richtiger wuerde.
    """
    if gliederung.leer():
        return ""
    teile = ['<div class="aiw-h-verzeichnis-betrieb">',
             "<h2>%s</h2>" % _e(BETRIEBSTEIL_TITEL)]
    for gruppe, eintraege in gliederung.gruppen:
        marke = "%s / %s" % (BETRIEBSMARKE, gruppe)
        teile.append('<h3 data-gruppe="%s">%s</h3>' % (_e(marke), _e(gruppe)))
        teile.append('<ul data-gruppe="%s">' % _e(marke))
        for e in eintraege:
            zusatz = ""
            if not e.hat_beispiele():
                zusatz = (' <span class="aiw-h-offen">(%s)</span>'
                          % _e(OHNE_BEISPIEL_MARKE))
            teile.append('<li data-sicht="%s"><a href="#%s"><code>%s</code>'
                         "</a>%s</li>"
                         % (_e(kapitel_id(e.schluessel)),
                            _e(kapitel_id(e.schluessel)),
                            _e(e.schluessel), zusatz))
        teile.append("</ul>")
    teile.append("</div>")
    return "\n".join(teile)


def kapitel_alle_html(gliederung: Betriebsgliederung) -> str:
    """Vorspann und alle Kapitel des Betriebsteils, in Ausgabereihenfolge."""
    if gliederung.leer():
        return ""
    eintraege = gliederung.eintraege()
    stuecke = [vorspann_html(gliederung)]
    for i, e in enumerate(eintraege):
        stuecke.append(kapitel_html(
            e,
            vorher=eintraege[i - 1] if i > 0 else None,
            nachher=eintraege[i + 1] if i + 1 < len(eintraege) else None))
    return "\n".join(stuecke)


def suchindex(gliederung: Betriebsgliederung) -> List[dict]:
    """
    Der Suchindex des Betriebsteils - ein Eintrag je Werkzeug, in derselben
    Form wie render_html.suchindex() (id, label, gruppe, offen, worte).

    WAS DURCHSUCHT WIRD - und warum hier anders als bei den Sichtkapiteln:
    Dort bleibt der Fliesstext absichtlich draussen, weil eine Volltextsuche
    ueber alle Absaetze bei einem Wort wie 'Fall' fast jedes Kapitel faende.
    Der Katalog hat keinen Stichwortbestand, dafuer aber je Werkzeug EINEN
    Satz Zweck und EINE Aufrufform. Beides ist kurz, unterscheidend und genau
    das, wonach man sucht ('sicherung', 'pruefsumme', 'migrate'). Der
    Fliesstext der Tiefeninhalte bleibt auch hier draussen.

    'offen' bedeutet hier wie dort "noch nicht ausgearbeitet" - beim
    Sichtkapitel: kein Kapitel, beim Werkzeug: kein Tiefeninhalt.
    """
    raus: List[dict] = []
    for gruppe, eintraege in gliederung.gruppen:
        for e in eintraege:
            worte = [e.schluessel, e.titel, e.zweck, e.aufruf, e.gruppe,
                     e.pfad]
            worte.extend(b.name for b in e.befehle if b.name)
            worte.extend(b.zweck for b in e.befehle)
            raus.append({
                "id": kapitel_id(e.schluessel),
                "label": e.schluessel,
                "gruppe": "%s / %s" % (BETRIEBSMARKE, gruppe),
                "offen": not e.hat_tiefe(),
                "worte": " ".join(worte).lower(),
            })
    return raus
