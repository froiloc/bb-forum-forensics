# =============================================================================
# report_render/vollzitat_klartext.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   DIE VOLLZITAT-GRUPPE ALS ZEILEN. Was der HTML-Bericht mit Rahmen, Farben
#   und Hochzahlen zeigt, brauchen DOCX, PDF und die SQLite-Spiegelung als
#   Folge von Textzeilen. Diese Datei erzeugt sie - EINMAL, fuer alle drei.
#
# WARUM NICHT DREIMAL IN DEN DREI RENDERERN: Weil die Zeilen den Inhalt der
#   Akte tragen und nicht ihre Gestaltung. Ob ein Befund seine Kategorie
#   nennt, ob das Datum als "nicht ermittelbar" erscheint, ob der Vorbehalt
#   zum Absatzfund mitgedruckt wird - das sind AUSSAGEN, und drei Fassungen
#   davon waeren drei Gelegenheiten, in einer davon eine Aussage zu
#   verlieren. Die Renderer entscheiden nur noch ueber Schriftgroesse,
#   Fettung und Einzug.
#
# DIE FARBE FEHLT HIER, UND ZWAR ABSICHTLICH. Anforderung 3 ("markierte
#   Stelle in derselben Farbe hinterlegt") laesst sich in einer reinen
#   Zeilenfolge nicht erfuellen. Statt die Anforderung stillschweigend
#   fallen zu lassen, wird die Markierung im Klartext durch die
#   Verweisnummer und durch >>...<< kenntlich gemacht, und der Befund nennt
#   die Kategorie ausgeschrieben. Das ist dieselbe Ueberlegung wie im Kopf
#   von core/kategorie_farben.py: die Farbe ordnet zu, das Wort benennt.
#   FUER DOCX UND PDF ist die farbige Hinterlegung technisch moeglich; sie
#   ist als eigener Vorgang aufgenommen und NICHT hier verschwiegen.
#
# Grundregeln: GR1, GR6, GR10.
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

#: Die Zeilenarten. Der Renderer entscheidet daran ueber die Form:
#:   'kopf'      - Kopfzeile der Gruppe            (fett, gross)
#:   'label'     - Beschriftung der Belegsammlung  (fett)
#:   'quelle'    - Art und Betreff/Partner         (fett)
#:   'meta'      - Datum, Beitragsnummer           (klein)
#:   'link'      - die Fundstelle                  (klein, nicht umbrechen)
#:   'absatz'    - der zitierte Absatz             (eingerueckt)
#:   'befund'    - Kategorie, Beleg-Nr., Ermittler (klein, fett)
#:   'notiz'     - die Notiz des Ermittlers
#:   'vorbehalt' - Einschraenkung zu diesem Beleg  (klein, hervorgehoben)
ARTEN = ("kopf", "label", "quelle", "meta", "link", "absatz",
         "befund", "notiz", "vorbehalt")


def _zeit(ts) -> str:
    """
    Die Inhaltszeit als deutsches Datum MIT Zonenangabe.

    Wortgleich zu HtmlRenderer._fmt_inhaltszeit - und aus demselben Grund
    mit Zone: eine Tatzeitangabe in einer Akte ohne Zone ist um eine oder
    zwei Stunden unbestimmt.
    """
    if not ts:
        return "nicht ermittelbar"
    try:
        return datetime.fromtimestamp(int(ts)).astimezone().strftime(
            "%d.%m.%Y, %H:%M Uhr (%Z)")
    except (ValueError, OSError, OverflowError):
        return "nicht ermittelbar"


def _vorbehalte(bf) -> List[str]:
    """
    Die Einschraenkungen zu einem Befund - wortgleich zum HTML-Bericht.

    Sie sind kein Beiwerk: sie sagen, auf welcher Grundlage die Angabe
    darueber steht. Ein Bericht, der sie im DOCX weglaesst und im HTML
    zeigt, waere zweierlei Akte.
    """
    aus = []
    if bf.absatz_weg == "text":
        aus.append("Absatz ueber den Wortlaut gefunden, nicht ueber den "
                   "Anker der Markierung")
    elif bf.absatz_weg == "uebersetzung":
        aus.append("Markierung in der maschinellen Uebersetzung; der Absatz "
                   "des Originals ist nicht ihre Umgebung")
    elif bf.absatz_weg == "keiner":
        aus.append("umschliessender Absatz nicht auffindbar")
    if bf.name_quelle == "display_name":
        aus.append("Nachname aus dem Anzeigenamen abgeleitet")
    elif bf.name_quelle == "kuerzel" and bf.ermittler:
        aus.append("nur das Benutzerkuerzel bekannt")
    return aus


def zeilen(gruppe) -> List[Tuple[str, str]]:
    """
    Die Vollzitat-Gruppe als Liste von (Art, Text).

    Die Reihenfolge ist die des HTML-Berichts: Gruppenkopf, Beschriftung,
    dann je Quelle Kopf, Metazeile, Fundstelle, Absaetze, Befunde.
    """
    aus: List[Tuple[str, str]] = []
    aus.append((
        "kopf",
        "BEWEISMITTELGRUPPE - VOLLZITAT (%d %s, %d %s)"
        % (gruppe.beleg_anzahl,
           "Beleg" if gruppe.beleg_anzahl == 1 else "Belege",
           gruppe.quellen_anzahl,
           "Quelle" if gruppe.quellen_anzahl == 1 else "Quellen")))
    if gruppe.beschriftung:
        aus.append(("label", "Belegsammlung: %s" % gruppe.beschriftung))

    for ub in gruppe.unterbloecke:
        q = ub.quelle
        aus.append(("quelle", q.bezeichnung()))

        meta = ["%s: %s" % ("Datum der Nachricht" if q.ist_pn
                            else "Datum des Beitrags", _zeit(q.posted_ts))]
        if q.ist_pn and q.betreff:
            meta.append("Betreff: %s" % q.betreff)
        if q.verfasser:
            meta.append("Verfasser: %s" % q.verfasser)
        if q.post_id is not None:
            meta.append("%s: #%d" % ("Nachricht" if q.ist_pn else "Beitrag",
                                     q.post_id))
        aus.append(("meta", " · ".join(meta)))
        aus.append(("link", "Fundstelle: %s"
                    % (q.link or "(keine Adresse)")))

        for absatz in ub.absaetze:
            kenn = ("[%s] " % ", ".join(str(n) for n in absatz.nummern)
                    if absatz.nummern else "")
            if absatz.ersatz:
                # Kein Absatz gefunden - nur die markierte Stelle. Das wird
                # gesagt, damit niemand den Ausschnitt fuer den ganzen
                # Beitrag haelt.
                aus.append(("absatz",
                            "%s>>%s<< (nur die markierte Stelle; "
                            "umschliessender Absatz nicht auffindbar)"
                            % (kenn, absatz.text)))
            else:
                aus.append(("absatz", "%s%s" % (kenn, absatz.text)))

        for bf in ub.befunde:
            kopf = ["[%d] %s" % (bf.nummer, bf.kategorie_text),
                    "Beleg #%d" % bf.annotation_id]
            kopf.append("Ermittler: %s" % (bf.ermittler or "nicht vermerkt"))
            aus.append(("befund", " · ".join(kopf)))
            if bf.markierung:
                aus.append(("notiz", "Markierte Stelle: >>%s<<"
                            % bf.markierung))
            if bf.notiz:
                aus.append(("notiz", "Notiz: %s" % bf.notiz))
            vb = _vorbehalte(bf)
            if vb:
                aus.append(("vorbehalt", "Hinweis: " + "; ".join(vb) + "."))
            if bf.hinweis and bf.absatz_weg == "keiner":
                aus.append(("vorbehalt", bf.hinweis))

    return aus


def klartext(gruppe) -> str:
    """Die ganze Gruppe als ein Textblock - fuer die SQLite-Spiegelung."""
    return "\n".join(text for _art, text in zeilen(gruppe))
