#!/usr/bin/env python3
# =============================================================================
# tools/anon_html.py
# IT-Forensisches Ermittlungswerkzeug - Weitergabe unverfaenglich machen
# =============================================================================
# ZWECK: In einer HTML-Datei den gesamten Textinhalt der ueber XPath
# ausgewaehlten Teilbaeume durch gleich langen Blindtext ('X') ersetzen und
# das Ergebnis als NEUE Datei schreiben.
#
# WARUM DIESE DATEI IN BUILD 687 UMGEBAUT WURDE (Vorgang ad88708d, dazu drei
# beim Nachmessen gefundene Befunde). Alles Folgende ist GEMESSEN, nicht
# hergeleitet - Container, Python 3.12.3, lxml 6.0.2, Wegwerf-HTML unter /tmp:
#
#   BEFUND 1 - NUR DER UNMITTELBARE TEXT WURDE ERSETZT. Die alte Fassung
#   arbeitete ausschliesslich auf 'elem.text'. Der Text in KINDELEMENTEN und
#   der Text HINTER einem Kindelement ('tail') blieb unangetastet:
#       <div class="postmsg">Vorname <b>Nachname</b> wohnt in Musterstadt.</div>
#     wurde zu
#       <div class="postmsg">XXXXXXX <b>Nachname</b> wohnt in Musterstadt.</div>
#   Ein Element, dessen gesamter Inhalt in einem Kindelement steckte, wurde
#   GAR NICHT angefasst. Beitraege eines FluxBB-Forums enthalten regelmaessig
#   <a>, <b>, <em> und <br>; in der Praxis ueberlebte damit ein grosser Teil
#   des Textes.
#
#   BEFUND 2 - OHNE TREFFER MELDETE DER LAUF ERFOLG. Traf der XPath kein
#   Element, endete der Lauf mit 0. Mit '-v' fiel er ausserdem NICHT in den
#   frueh gesetzten sys.exit(0) und schrieb eine UNVERAENDERTE Kopie mit der
#   Meldung "Written anonymized HTML to: ...". Eine Datei, die 'anonymized'
#   heisst und den Originaltext enthaelt, ist die gefaehrlichste Ausgabe,
#   die dieses Werkzeug haben kann.
#
#   BEFUND 3 - DIE DATEI WURDE NICHT ALS UTF-8 GELESEN. Ohne '<meta charset>'
#   raet lxml die Kodierung und landet bei Latin-1. Gemessen an derselben
#   Datei, einmal ohne und einmal mit Deklaration:
#       ohne : <p>Gruesse aus Koeln</p> stand danach DOPPELT KODIERT in der
#              Ausgabe (b'Gr\xc3\x83\xc2\xbc...'), obwohl der Absatz gar nicht
#              getroffen war; der Blindtext war 40 statt 25 Zeichen lang.
#       mit  : Bytes unveraendert, Blindtext 25 Zeichen.
#   Das Forum ist multilingual (Projektfeststellung 1 und 2). Ein von Hand
#   herausgeschnittenes Fragment hat regelmaessig keine Deklaration. Deshalb
#   wird die Kodierung jetzt ANGESAGT und nicht geraten - siehe '--encoding'.
#
#   BEFUND 4 - DER DOCTYPE GING VERLOREN. Serialisiert wurde das ELEMENT und
#   nicht der BAUM; '<!DOCTYPE html>' fehlte in der Ausgabe. Folge: der
#   Browser rendert die Weitergabe im Quirks-Modus. Damit ist gerade das
#   nicht mehr beurteilbar, wofuer der laengenerhaltende Blindtext gedacht
#   ist - die Gestalt der Seite.
#   NACHTRAG AUS DER EIGENEN AENDERUNG: Der naheliegende Weg (immer den BAUM
#   serialisieren) erzeugt die Kehrseite - lxml DICHTET einer Datei ohne
#   DOCTYPE beim Schreiben einen HTML-4.0-Transitional-DOCTYPE an (gemessen).
#   Deshalb entscheidet die Eingabe, siehe hat_doctype().
#
#   BEFUND 5 - ATTRIBUTE UND NICHT-ELEMENT-TREFFER. Innerhalb eines
#   getroffenen Elements ueberlebten 'title="Klarname im Attribut"' und
#   'href="mailto:klar@example.com"' unveraendert. Ausserdem verwarf die
#   alte Fassung Nicht-Element-Ergebnisse eines XPath ('.../text()',
#   '/@href') STILLSCHWEIGEND (Grundregel 1).
#
# WAS DIESE FASSUNG TUT UND WAS SIE AUSDRUECKLICH NICHT TUT:
#
#   Sie ersetzt den GESAMTEN Textinhalt der getroffenen Teilbaeume,
#   einschliesslich Kommentaren und dem Inhalt von <script>/<style>. Ein
#   ausgenommener Knoten waere ein Versteck - und ein Versteck in einem
#   Werkzeug, das Unverfaenglichkeit herstellen soll, ist schlimmer als
#   gar kein Werkzeug.
#
#   Sie ersetzt KEINE ATTRIBUTWERTE. Das ist eine Entscheidung und kein
#   Versehen: 'class' und 'href' blind zu ueberschreiben zerstoert genau die
#   Gestalt, um derentwillen die Datei weitergegeben wird. Stattdessen wird
#   die Zahl der verbliebenen Attribute IMMER gemeldet und mit '-v'
#   aufgelistet. Wer weitergibt, muss sie gelesen haben.
#
#   DIE GEGENPROBE (der eigentliche Beleg): Das Ergebnis wird zunaechst in
#   eine Nebendatei geschrieben, diese neu EINGELESEN und darin gemessen,
#   dass in den getroffenen Teilbaeumen kein Textknoten mehr ein anderes
#   Zeichen als 'X' und Leerraum enthaelt. Erst wenn das traegt, wird die
#   Nebendatei per os.replace() an den Zielort verschoben. Scheitert sie,
#   entsteht die Zieldatei NIE - und eine vorhandene Vorgaengerdatei bleibt
#   unangetastet.
#
#   WARUM POSITIONSPFADE UND NICHT DER XPATH: Nach dem Blenden trifft ein
#   textabhaengiger Ausdruck ('//div[contains(text(),"Klarname")]') seine
#   eigenen Treffer nicht mehr. Gemerkt wird deshalb vor dem Schreiben
#   getroottree().getpath(elem) - ein reiner Lagepfad ('/html/body/div[2]'),
#   der nur an der Struktur haengt, und die aendert sich hier nicht.
#
#   WAS DIE GEGENPROBE NICHT BELEGT: Sie sagt etwas ueber die GETROFFENE
#   AUSWAHL. Sie sagt nichts ueber den Rest der Datei und nichts ueber
#   Attributwerte. Die Schlussmeldung sagt das woertlich. Ein Werkzeug, das
#   mehr behauptet als es misst, ist der Ausgangsbefund dieses Vorgangs.
#
# SPRACHE: Die Bedienerausgaben sind ENGLISCH (Festlegung mc, Build 687) -
# das Ergebnis geht moeglicherweise an Europol, Arbeitssprache Englisch.
# Kommentare und Dokumentation bleiben deutsch wie im uebrigen Projekt.
# Die bestehenden Optionsnamen sind unveraendert; jemand kann sie in einem
# Skript stehen haben.
#
# Version: v0.8.687 - Build: 687 - 2026-08-11
# =============================================================================

import argparse
import os
import sys

# Direktaufruf als Skript: das Paketverzeichnis muss im Suchpfad liegen
# (Muster aus tools/hilfe.py). Build 630 - noetig geworden mit dem
# Epilog-Import.
_WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from lxml import html, etree  # noqa: E402
from management.help import cli_epilog  # noqa: E402


# -----------------------------------------------------------------------------
# Rueckgabewerte
#
# WARUM MEHR ALS 0 UND 1: Der Ausgangsbefund war, dass 'anonymisiert' und
# 'nichts getroffen' denselben Rueckgabewert hatten. Wer dieses Werkzeug in
# einem Ablauf einsetzt, muss die Faelle AUSEINANDERHALTEN koennen, ohne
# Meldungstexte zu lesen. Ein Wert ungleich 0 ist hier nicht durchgehend ein
# Fehler - 2 und 3 sind BEFUNDE, und ein Befund ist die Leistung des
# Werkzeugs und nicht sein Versagen.
# -----------------------------------------------------------------------------
RC_OK = 0            # ersetzt, Gegenprobe bestanden, Datei geschrieben
RC_AUFRUF = 1        # Aufruf-, Lese- oder Schreibfehler
RC_KEIN_TREFFER = 2  # BEFUND: nichts getroffen oder nichts zu ersetzen
RC_GEGENPROBE = 3    # BEFUND: Gegenprobe gescheitert - keine Datei entstanden
RC_ZIEL_DA = 4       # Zieldatei existiert und '--overwrite' fehlt


def blind_text(text):
    """
    Jedes Nicht-Leerraumzeichen durch 'X' ersetzen, Leerraum erhalten.

    Der erhaltene Leerraum ist gewollt: Wortlaengen und Wortgrenzen bleiben
    ablesbar, damit die Gestalt der Seite beurteilbar bleibt. Er ist zugleich
    die Grenze des Werkzeugs - fuer eine Weitergabe, bei der auch die
    Wortlaenge nicht stehen bleiben darf, taugt das Ergebnis nicht.

    'None' bleibt 'None': lxml unterscheidet "kein Textknoten" von "leerer
    Textknoten", und aus einem fehlenden Knoten einen leeren zu machen
    veraendert die Datei ohne Anlass.
    """
    if text is None:
        return None
    return "".join(ch if ch.isspace() else "X" for ch in text)


def _marke(knoten):
    """Lesbare Herkunftsangabe fuer Meldungen."""
    # Kommentare und Verarbeitungsanweisungen haben keinen str-tag, sondern
    # eine Funktion (lxml-Eigenheit).
    tag = knoten.tag
    if not isinstance(tag, str):
        return "<%s>" % getattr(tag, "__name__", "node")
    return "<%s>" % tag


def textknoten(elem):
    """
    Alle Textknoten EINES Teilbaums, als (Beschreibung, Leser, Schreiber).

    WAS DAZUGEHOERT: 'elem.text', sowie 'text' UND 'tail' jedes Nachfahren -
    einschliesslich Kommentaren und Verarbeitungsanweisungen, die
    iterdescendants() mitliefert.

    WAS NICHT DAZUGEHOERT: 'elem.tail'. Der Text hinter dem getroffenen
    Element gehoert nicht in seinen Teilbaum, sondern in den des Elternteils.
    Ihn mitzublenden hiesse, Text ausserhalb der Auswahl zu veraendern - das
    waere ein stiller Uebergriff und wuerde ausserdem die Gegenprobe
    unpruefbar machen (sie muesste Auswahl und Umgebung vermengen).

    Rueckgabe je Knoten ein Tripel:
      name   - lesbare Herkunft fuer Meldungen ("<b> text", "<span> tail")
      lesen  - Funktion ohne Argumente, liefert den aktuellen Wert
      setzen - Funktion mit einem Argument, schreibt den Wert
    """
    ergebnis = [(
        "%s text" % _marke(elem),
        lambda e=elem: e.text,
        lambda wert, e=elem: setattr(e, "text", wert),
    )]
    for kind in elem.iterdescendants():
        ergebnis.append((
            "%s text" % _marke(kind),
            lambda k=kind: k.text,
            lambda wert, k=kind: setattr(k, "text", wert),
        ))
        ergebnis.append((
            "%s tail" % _marke(kind),
            lambda k=kind: k.tail,
            lambda wert, k=kind: setattr(k, "tail", wert),
        ))
    return ergebnis


def attribute_im_teilbaum(elem):
    """
    Alle Attribute des Teilbaums als (Elementname, Attributname, Wert).

    SIE WERDEN NICHT VERAENDERT (Begruendung im Dateikopf). Sie werden
    gezaehlt und auf Wunsch aufgefuehrt, weil ein unbenanntes Restrisiko
    dasselbe ist wie ein verschwiegenes.
    """
    gefunden = []
    for knoten in elem.iter():
        werte = getattr(knoten, "attrib", None)
        if not werte:
            continue
        tag = knoten.tag if isinstance(knoten.tag, str) else "node"
        for name, wert in sorted(werte.items()):
            gefunden.append((tag, name, wert))
    return gefunden


def sammle_treffer(baum, xpaths, strom):
    """
    Die XPath-Ausdruecke auswerten.

    Rueckgabe: (elemente, zuordnung, nicht_elemente) - oder (None, None, None)
    bei einem ungueltigen Ausdruck.
      elemente       - getroffene Elemente, DOPPELFREI und in
                       Dokumentreihenfolge (ein Element, das zwei Ausdruecke
                       treffen, wird einmal bearbeitet).
      zuordnung      - Element -> Liste der Ausdruecke, die es getroffen haben.
      nicht_elemente - (Ausdruck, Typname, Anzahl) fuer Ergebnisse, die KEINE
                       Elemente sind.

    ZUM LETZTEN PUNKT: Die alte Fassung verwarf solche Ergebnisse
    stillschweigend. Wer '-x "//div/text()"' schrieb, bekam dieselbe Meldung
    wie jemand, dessen Ausdruck ins Leere ging - und damit keine Chance, den
    Unterschied zu bemerken. Grundregel 1.
    """
    zuordnung = {}
    nicht_elemente = []

    for ausdruck in xpaths:
        try:
            treffer = baum.xpath(ausdruck)
        except etree.XPathError as fehler:
            print("ERROR: Invalid XPath '%s': %s" % (ausdruck, fehler),
                  file=strom)
            return None, None, None

        # Ein XPath kann auch einen Einzelwert liefern (count(), string()).
        if not isinstance(treffer, list):
            treffer = [treffer]

        sonstige = {}
        for eintrag in treffer:
            if isinstance(eintrag, html.HtmlElement):
                zuordnung.setdefault(eintrag, []).append(ausdruck)
            else:
                typ = type(eintrag).__name__
                sonstige[typ] = sonstige.get(typ, 0) + 1
        for typ, anzahl in sorted(sonstige.items()):
            nicht_elemente.append((ausdruck, typ, anzahl))

    # Dokumentreihenfolge: sie macht die Ausgabe zwischen zwei Laeufen
    # vergleichbar. Ein set() waere zufaellig sortiert gewesen, und eine
    # Meldung, deren Reihenfolge sich ohne Anlass aendert, laedt zum
    # Wegsehen ein.
    reihenfolge = {}
    for nummer, knoten in enumerate(baum.iter()):
        reihenfolge[knoten] = nummer
    elemente = sorted(zuordnung, key=lambda e: reihenfolge.get(e, 0))
    return elemente, zuordnung, nicht_elemente


def anonymisiere(elem, ausdruecke, verbose, dry_run, strom):
    """
    Einen Teilbaum blenden. Rueckgabe: Zahl der tatsaechlich ersetzten Knoten.

    Gezaehlt wird nur, was auch Inhalt hatte: ein leerer oder rein aus
    Leerraum bestehender Knoten ist nichts, was anonymisiert werden koennte,
    und ihn mitzuzaehlen wuerde die Zahl aufblaehen, an der der Bediener
    seine Erwartung prueft.
    """
    ersetzt = 0
    for name, lesen, setzen in textknoten(elem):
        original = lesen()
        if not original or not original.strip():
            continue
        geblendet = blind_text(original)
        if verbose or dry_run:
            marke = "[DRY RUN]" if dry_run else "[VERBOSE]"
            print("%s %s  (matched by: %s)"
                  % (marke, name, ", ".join(ausdruecke)), file=strom)
            print("  Original: %r" % original[:80], file=strom)
            print("  Blinded:  %r" % geblendet[:80], file=strom)
        if not dry_run:
            setzen(geblendet)
        ersetzt += 1
    return ersetzt


def pruefe_teilbaum(elem):
    """
    Die eigentliche Messung: enthaelt dieser Teilbaum noch Klartext?

    Rueckgabe: Liste der beanstandeten (Knotenname, Wert). Leer heisst
    bestanden. Zulaessig ist ausschliesslich 'X' und Leerraum - kein
    Zeichenvorrat, keine Ausnahmeliste, keine Naeherung.
    """
    beanstandet = []
    for name, lesen, _setzen in textknoten(elem):
        wert = lesen()
        if not wert:
            continue
        if [ch for ch in wert if not ch.isspace() and ch != "X"]:
            beanstandet.append((name, wert[:120]))
    return beanstandet


def lies_und_pruefe_kodierung(pfad, kodierung, strom):
    """
    Datei als Bytes lesen und die Kodierung NACHWEISEN statt sie zu raten.

    Die strenge Dekodierung vorab ist der Kern von Befund 3: lxml wuerde
    ungueltige Bytes stillschweigend ersetzen und mit einem beschaedigten
    Baum weiterarbeiten. Hier bricht der Lauf stattdessen ab und nennt die
    Byteposition - dort steht in aller Regel das erste Zeichen einer
    anderen Kodierung.
    """
    try:
        with open(pfad, "rb") as datei:
            roh = datei.read()
    except OSError as fehler:
        print("ERROR: Cannot read HTML file: %s" % fehler, file=strom)
        return None

    try:
        roh.decode(kodierung)
    except (UnicodeDecodeError, LookupError) as fehler:
        print("ERROR: File is not valid %s: %s" % (kodierung, fehler),
              file=strom)
        print("       The file was NOT processed. Re-run with the correct "
              "--encoding.", file=strom)
        return None
    return roh


def baue_baum(roh, kodierung, strom):
    """
    HTML mit ANGESAGTER Kodierung auswerten.

    Der Parser bekommt die Kodierung ausdruecklich mit. Damit spielt es keine
    Rolle mehr, ob die Datei ein '<meta charset>' traegt - und genau das war
    Befund 3.
    """
    try:
        leser = html.HTMLParser(encoding=kodierung)
        return html.fromstring(roh, parser=leser)
    except Exception as fehler:                     # noqa: BLE001
        print("ERROR: Failed to parse HTML: %s" % fehler, file=strom)
        return None


def hat_doctype(roh, kodierung):
    """
    Trug die EINGABE einen DOCTYPE?

    WARUM DAS AN DEN ROHBYTES HAENGT UND NICHT AN lxml: 'docinfo.doctype'
    beantwortet die Frage NICHT. Gemessen (Build 687): fuer eine Datei OHNE
    DOCTYPE liefert es '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0
    Transitional//EN" ...' - einen erfundenen. Wer sich darauf verliesse,
    haette Befund 4 nur umgedreht: statt einen DOCTYPE zu verlieren, wuerde
    das Werkzeug einen hinzudichten und damit den Darstellungsmodus des
    Browsers aendern. Beides ist eine stille Veraenderung an einer Datei,
    die weitergegeben wird.

    Gesucht wird nur im VORSPANN - alles vor dem Wurzelelement. Weiter
    hinten kann ein DOCTYPE nicht stehen; ein '<!doctype' im Fliesstext
    einer Forenseite waere maskiert ('&lt;!DOCTYPE').
    """
    text = roh.decode(kodierung, errors="replace")
    stelle = text.lower().find("<html")
    vorspann = text[:stelle] if stelle >= 0 else text[:4096]
    return "<!doctype" in vorspann.lower()


def schreibe(baum, ziel, kodierung, doctype, strom):
    """
    Baum serialisieren und schreiben.

    'baum.getroottree()' statt 'baum' ist der Unterschied zwischen "DOCTYPE
    erhalten" und "DOCTYPE verloren" (Befund 4). Gemessen: tostring(elem)
    liefert '<html>...', tostring(roottree) liefert '<!DOCTYPE html>' und
    dann '<html>...'. Welcher der beiden Wege richtig ist, entscheidet
    ausschliesslich die EINGABE - siehe hat_doctype().
    """
    try:
        was = baum.getroottree() if doctype else baum
        daten = html.tostring(was, encoding=kodierung, method="html")
        with open(ziel, "wb") as datei:
            datei.write(daten)
        return True
    except (OSError, ValueError, LookupError) as fehler:
        print("ERROR: Failed to write output: %s" % fehler, file=strom)
        return False


def gegenprobe(pfad, kodierung, lagepfade, strom):
    """
    Die geschriebene Datei neu einlesen und messen. Rueckgabe: Beanstandungen.

    WARUM GEGEN DIE DATEI UND NICHT GEGEN DEN BAUM IM SPEICHER: Zwischen dem
    Baum und der Datei liegen Serialisierung und Kodierung - also genau die
    beiden Schritte, an denen Befund 3 und 4 haengen. Eine Probe am Baum
    haette beide nicht gesehen. Geprueft wird das, was weitergegeben wird.
    """
    beanstandet = []

    roh = lies_und_pruefe_kodierung(pfad, kodierung, strom)
    if roh is None:
        return ["the written file could not be read back or is not valid %s"
                % kodierung]

    baum = baue_baum(roh, kodierung, strom)
    if baum is None:
        return ["the written file could not be parsed back"]

    wurzelbaum = baum.getroottree()
    for lagepfad in lagepfade:
        wieder = wurzelbaum.xpath(lagepfad)
        if len(wieder) != 1:
            beanstandet.append(
                "position path %s resolved to %d element(s) after writing - "
                "the structure changed and the result cannot be verified"
                % (lagepfad, len(wieder)))
            continue
        for name, wert in pruefe_teilbaum(wieder[0]):
            beanstandet.append("%s %s still contains plain text: %r"
                               % (lagepfad, name, wert))
    return beanstandet


def _entferne(pfad):
    """Nebendatei beseitigen - ein Rest davon waere eine unklare Ausgabe."""
    try:
        os.remove(pfad)
    except OSError:
        # Bewusst still: das Scheitern des Aufraeumens darf den Befund, der
        # gerade gemeldet wird, nicht ueberdecken. Die Datei traegt
        # '.anon-tmp-<pid>' im Namen und ist damit als Rest erkennbar.
        pass


def _baue_parser():
    """
    Der Argumentparser - ausgelagert, damit die Tests ihn ohne Lauf pruefen
    koennen.

    'add_help=False' bleibt, weil dieses Werkzeug '-h' selbst anmeldet
    (Build 630). Epilog und Formatierer kommen aus dem Werkzeugkatalog.
    """
    parser = argparse.ArgumentParser(
        add_help=False,
        prog="anon_html.py",
        description="Replaces the ENTIRE text content of the subtrees "
                    "selected by XPath with blind text of the same length "
                    "and writes the result as a NEW file. The result is "
                    "verified afterwards; a file that fails the check is "
                    "never produced.",
        epilog=cli_epilog.epilog("anon_html"),
        formatter_class=cli_epilog.HilfeFormat)
    parser.add_argument("html_file", help="Path of the HTML file")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show what is replaced")
    parser.add_argument("-d", "--dry-run", action="store_true",
                        help="Show what would be executed")
    parser.add_argument("-o", "--output",
                        help="Output file path (default: "
                             "<original>.new.<extension>)")
    parser.add_argument("-f", "--xpath-file",
                        help="Text file with one XPath per line")
    parser.add_argument("-x", "--xpath", help="Single XPath expression")
    parser.add_argument("--overwrite", action="store_true",
                        help="Allow an existing output file to be replaced "
                             "(default: refuse)")
    parser.add_argument("--encoding", default="utf-8",
                        help="Character encoding of the input file "
                             "(default: utf-8). It is enforced, not guessed.")
    parser.add_argument("-h", "--help", action="help",
                        help="Show this help message")
    return parser


def main(argv=None):
    args = _baue_parser().parse_args(argv)

    # Der Bericht geht durchgehend nach stderr. Grund: die Ausgabe dieses
    # Werkzeugs ist die DATEI, nicht der Text - wer stdout weiterleitet, soll
    # dabei nicht den Pruefbericht einsammeln. (Die alte Fassung schrieb den
    # Verbose-Teil nach stdout und den Rest nach stderr.)
    strom = sys.stderr

    # ---------------------------------------------------------------- Aufruf
    if not args.xpath_file and not args.xpath:
        print("ERROR: Either --xpath-file or --xpath must be provided.",
              file=strom)
        return RC_AUFRUF

    if args.xpath_file and args.xpath:
        print("ERROR: Provide only one of --xpath-file or --xpath, not both.",
              file=strom)
        return RC_AUFRUF

    if args.xpath_file:
        try:
            with open(args.xpath_file, "r", encoding="utf-8") as datei:
                xpaths = [zeile.strip() for zeile in datei if zeile.strip()]
        except OSError as fehler:
            print("ERROR: Cannot read xpath file: %s" % fehler, file=strom)
            return RC_AUFRUF
        if not xpaths:
            # Eine leere Ausdrucksdatei ist ein Aufruffehler und kein
            # "nichts getroffen": es wurde nicht gesucht.
            print("ERROR: XPath file contains no expressions: %s"
                  % args.xpath_file, file=strom)
            return RC_AUFRUF
    else:
        xpaths = [args.xpath]

    if not os.path.isfile(args.html_file):
        print("ERROR: HTML file not found: %s" % args.html_file, file=strom)
        return RC_AUFRUF

    if args.output:
        ziel = args.output
    else:
        basis, endung = os.path.splitext(args.html_file)
        ziel = "%s.new%s" % (basis, endung)

    # ------------------------------------------------- Ueberschreibschutz
    # FRUEH und nicht erst vor dem Schreiben: wer erst nach getaner Arbeit
    # erfaehrt, dass er die Zieldatei nicht anfassen darf, hat die Zeit
    # bereits verloren - und bei einem Werkzeug, das man unter Zeitdruck
    # bedient, ist die Versuchung gross, dann '--overwrite' anzuhaengen,
    # ohne nachzusehen, was dort steht.
    if not args.dry_run and os.path.exists(ziel) and not args.overwrite:
        print("ERROR: Output file already exists: %s" % ziel, file=strom)
        print("       Refusing to overwrite it. Pass --overwrite if that is "
              "what you want.", file=strom)
        return RC_ZIEL_DA

    # ------------------------------------------------------------- Einlesen
    roh = lies_und_pruefe_kodierung(args.html_file, args.encoding, strom)
    if roh is None:
        return RC_AUFRUF

    baum = baue_baum(roh, args.encoding, strom)
    if baum is None:
        return RC_AUFRUF

    # -------------------------------------------------------------- Treffer
    elemente, zuordnung, nicht_elemente = sammle_treffer(baum, xpaths, strom)
    if elemente is None:
        return RC_AUFRUF

    for ausdruck, typ, anzahl in nicht_elemente:
        print("NOTE: XPath '%s' returned %d result(s) of type '%s', which is "
              "not an element and cannot be anonymized."
              % (ausdruck, anzahl, typ), file=strom)
        print("      Select the ELEMENT instead (e.g. '//div[@class=\"x\"]' "
              "rather than '//div[@class=\"x\"]/text()').", file=strom)

    if not elemente:
        print("FINDING: No elements matched the given XPath(s).", file=strom)
        print("         No file has been written. This is deliberate: a file "
              "called 'anonymized' that still contains the original text is "
              "the most dangerous output this tool can produce.", file=strom)
        return RC_KEIN_TREFFER

    # ---------------------------------------------------------- Lagepfade
    # VOR dem Blenden gemerkt. Begruendung im Dateikopf: ein textabhaengiger
    # XPath findet seine eigenen Treffer danach nicht mehr wieder.
    lagepfade = [baum.getroottree().getpath(elem) for elem in elemente]

    # ------------------------------------------------------------- Blenden
    ersetzt = 0
    for elem in elemente:
        ersetzt += anonymisiere(elem, zuordnung[elem], args.verbose,
                                args.dry_run, strom)

    print("Matched %d element(s), replaced %d text node(s)."
          % (len(elemente), ersetzt), file=strom)

    if ersetzt == 0:
        print("FINDING: The XPath(s) matched, but there was no text to "
              "replace.", file=strom)
        print("         No file has been written - it would have been a copy "
              "of the original under a name suggesting otherwise.",
              file=strom)
        return RC_KEIN_TREFFER

    # Attribute: nicht veraendert, aber benannt.
    attribute = []
    for elem in elemente:
        attribute.extend(attribute_im_teilbaum(elem))
    if attribute:
        print("NOTE: %d attribute value(s) inside the matched subtrees were "
              "NOT anonymized (e.g. href, title, alt). This tool does not "
              "touch attributes, because blanking 'class' or 'href' would "
              "destroy the very layout the output is meant to show. READ "
              "THEM before sharing%s."
              % (len(attribute),
                 "" if args.verbose else " (--verbose lists them)"),
              file=strom)
        if args.verbose:
            for tag, name, wert in attribute:
                print("      <%s %s=%r>" % (tag, name, wert[:80]), file=strom)

    # ---------------------------------------------------------- Trockenlauf
    if args.dry_run:
        print("[DRY RUN] No file written. Would write to: %s" % ziel,
              file=strom)
        return RC_OK

    # ------------------------------------------- Schreiben in die Nebendatei
    # Sie liegt im ZIELVERZEICHNIS, damit os.replace() ein Umbenennen im
    # selben Dateisystem ist und nicht ein Kopieren ueber eine Grenze hinweg.
    # Das ist auf den UNC-Pfaden der Anlage kein Detail.
    nebendatei = "%s.anon-tmp-%d" % (ziel, os.getpid())
    if not schreibe(baum, nebendatei, args.encoding,
                    hat_doctype(roh, args.encoding), strom):
        _entferne(nebendatei)
        return RC_AUFRUF

    # ------------------------------------------------------------ Gegenprobe
    befunde = gegenprobe(nebendatei, args.encoding, lagepfade, strom)
    if befunde:
        _entferne(nebendatei)
        print("FINDING: The verification pass FAILED. No file has been "
              "written; %s"
              % ("an existing %s was left untouched." % ziel
                 if os.path.exists(ziel) else "nothing was left behind."),
              file=strom)
        for zeile in befunde:
            print("         %s" % zeile, file=strom)
        return RC_GEGENPROBE

    try:
        os.replace(nebendatei, ziel)
    except OSError as fehler:
        _entferne(nebendatei)
        print("ERROR: Failed to move the verified result into place: %s"
              % fehler, file=strom)
        return RC_AUFRUF

    print("Written anonymized HTML to: %s" % ziel, file=strom)
    print("VERIFIED: re-read the written file; in the %d matched subtree(s) "
          "no text node contains any character other than 'X' and "
          "whitespace." % len(lagepfade), file=strom)
    print("          This says nothing about the rest of the file and "
          "nothing about attribute values.", file=strom)
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
