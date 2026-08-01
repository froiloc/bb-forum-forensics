#!/usr/bin/env python3
# =============================================================================
# tools/hilfe_lektorat.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H8a)
# =============================================================================
# Zweck:
#   Erzeugt die LEKTORATSFASSUNG der Hilfe: EIN eigenstaendiges HTML-Dokument
#   mit allen vorhandenen Kapiteln UND allen Kontexthilfe-Texten, ohne
#   Rechtefilter und ohne laufenden Server.
#
# WARUM ES DIESES WERKZEUG BRAUCHT (Anlass: mc, 2026-07-31):
#   Die redaktionelle Abnahme (Entscheidung F6) ist ein LESEvorgang, kein
#   Entwicklungsvorgang. Wer gegenlesen soll, darf dafuer nicht
#     * Python-Datenmodule mit Anfuehrungszeichen und Zeilenumbruechen lesen
#       muessen (der Text ist dort in Fragmente zerlegt),
#     * den Server starten muessen,
#     * und schon gar nicht 43 Sichten einzeln im Hilfemodus anklicken
#       muessen, um die POPUP-Texte zu sehen - die stehen in der Vollhilfe
#       naemlich gerade NICHT.
#
#   DER ZWEITE PUNKT IST DER WICHTIGE: Die Kontexthilfe-Texte sind die
#   Haelfte des Bestands, erscheinen aber nur als Popup an einem Element.
#   Ohne dieses Werkzeug waeren sie nur durch Anklicken jedes einzelnen
#   markierten Elements zu pruefen. Hier stehen sie je Sicht gesammelt neben
#   ihrem Kapitel.
#
#   OHNE RECHTEFILTER, und das ist Absicht: Die Lektoratsfassung ist kein
#   Betriebsartefakt, sondern eine Arbeitsvorlage fuer die Vier-Augen-Lesung.
#   Sie zeigt ALLES, was verfasst ist - auch Kapitel, die die lesende Person
#   im Betrieb nicht saehe. Die Sperre (E1) gilt fuer die ausgelieferte
#   Hilfe unter /help; sie gilt nicht fuer die Redaktion des Bestands.
#   DESHALB traegt das Dokument die Einstufung im Kopf UND in der Fusszeile.
#
# Aufruf:
#   python tools/hilfe_lektorat.py                      -> Hilfe_Lektorat.html
#   python tools/hilfe_lektorat.py --ziel <pfad.html>
#   python tools/hilfe_lektorat.py --nur faelle,escalation
#   python tools/hilfe_lektorat.py --nur-betrieb        (nur die Werkzeuge)
#
# Exit-Codes: 0 = geschrieben, 1 = Fehler (unbekannte Sicht o. ae.)
#
# Build 597: je Kapitel steht der relative Dateipfad dabei (mc 2026-07-31).
#
# BUILD 623 (H19 NACHTRAG): DIE BETRIEBSKAPITEL GEHOEREN HIER HINEIN.
#   Mit Build 622 sind die Werkzeugkapitel in die Vollhilfe gekommen, die dieses
#   Werkzeug nicht kannte - es liest das SICHT-Register, und die
#   Betriebskapitel stehen nicht darin. Damit waren sie ausgeliefert, aber
#   nicht gegengelesen.
#
#   DAS IST GENAU DER FEHLER, GEGEN DEN ES DIESES WERKZEUG GIBT. Der Satz
#   oben - "ein Text, der es nicht in dieses Dokument schafft, wird auch
#   nicht gegengelesen" - galt fuer sie ebenso. Ein Werkzeug fuer die
#   Vollstaendigkeitspruefung, das selbst einen Teil des Bestands nicht
#   sieht, ist schlimmer als keines: es erzeugt den Eindruck, alles sei
#   gelesen worden.
#
#   OHNE RECHTEFILTER, wie der Rest dieser Fassung: der Betriebsteil wird
#   ausdruecklich MIT 'ops.view' gebaut. Die Sperre gilt fuer die
#   ausgelieferte Hilfe unter /help, nicht fuer die Redaktion des Bestands.
#
# Version: v0.8.623 - Build: 623 - 2026-08-01
# =============================================================================

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from management.help import cli_html                        # noqa: E402
from management.help.cli_html import (                      # noqa: E402
    CLI_RECHT, Betriebsgliederung,
)
from management.help import cli_epilog                    # noqa: E402
from management.help.inhalt import (                        # noqa: E402
    SHELL_QUELLE, lade_register, quelle_je_sicht,
)
from management.help.modell import HilfeRegister, Sichthilfe  # noqa: E402
from management.help.pruefung import fehlliste_sichten      # noqa: E402
from management.help.sicht_katalog import (                 # noqa: E402
    SICHT_KATALOG, sicht as katalog_sicht,
)

STANDARD_ZIEL = "Hilfe_Lektorat.html"

#: Die Quelle der Betriebskapitel - fuer die Angabe "Text steht in:" je
#: Kapitel. Sie sind kein Kapitel je Datei wie die Sichttexte, sondern
#: stammen alle aus EINEM Katalog; das ist beim Gegenlesen die wichtigere
#: Auskunft, weil eine Korrektur dort und nur dort einzutragen ist.
CLI_QUELLE = "management/help/cli_katalog.py"

_CSS = """
:root{--t:#1c1c1c;--g:#5a5a5a;--l:#d6d6d6;--f:#f7f7f5;--a:#1f4e79;--o:#8a5a00}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--t);line-height:1.55;
 font:16px/1.55 "Segoe UI",Tahoma,Geneva,Verdana,sans-serif}
header.kopf{background:var(--a);color:#fff;padding:.7em 1.4em;display:flex;
 gap:.8em;align-items:baseline;flex-wrap:wrap}
header.kopf h1{font-size:1.15rem;margin:0;font-weight:600}
.badge{border:1px solid rgba(255,255,255,.7);border-radius:3px;padding:.1em .5em;
 font-size:.75rem;letter-spacing:.05em}
.hinweis{background:#fff8e8;border-left:4px solid var(--o);color:var(--o);
 margin:0;padding:.8em 1.4em}
.inhalt{max-width:52em;margin:0 auto;padding:0 1.4em 4em}
.toc{background:var(--f);border-bottom:1px solid var(--l);padding:1em 1.4em}
.toc h2{font-size:.85rem;text-transform:uppercase;letter-spacing:.06em;
 color:var(--g);margin:0 0 .5em}
.toc ol{margin:0;padding-left:1.4em;columns:2}
.toc a{color:var(--t);text-decoration:none;border-bottom:1px solid transparent}
.toc a:hover{border-bottom-color:var(--a)}
article{border-top:2px solid var(--l);padding-top:1.4em;margin-top:2.4em}
article h2{color:var(--a);font-size:1.4rem;margin:0 0 .1em}
.kennung{color:var(--g);font-size:.8rem;margin:0 0 .3em;font-family:monospace}
.quelle{color:var(--g);font-size:.8rem;margin:0 0 .9em;font-family:monospace}
.quelle b{color:var(--a);font-weight:600}
.recht{background:var(--f);border-left:3px solid var(--a);padding:.5em .8em;
 margin:0 0 1.2em;font-size:.93rem}
section{margin:1.4em 0}
section h3{font-size:1.06rem;margin:0 0 .3em}
section h3 .anker{color:var(--g);font-family:monospace;font-size:.72rem;
 font-weight:400;margin-left:.6em}
p{margin:.5em 0}
li{margin:.3em 0}
.pop{border-top:1px dashed var(--l);margin-top:2em;padding-top:1em}
.pop h3{font-size:1rem;color:var(--a);margin:0 0 .6em}
table.k{border-collapse:collapse;width:100%;font-size:.92rem}
table.k th,table.k td{border:1px solid var(--l);padding:.45em .6em;
 vertical-align:top;text-align:left}
table.k th{background:var(--f);font-size:.8rem;letter-spacing:.03em}
table.k code{font-size:.82rem;color:var(--g);word-break:break-all}
.verweis{color:var(--a);font-size:.85rem;display:block;margin-top:.3em}
.offen{color:var(--o);font-style:italic}
footer{border-top:1px solid var(--l);color:var(--g);font-size:.82rem;
 padding:1em 1.4em 3em;max-width:52em;margin:0 auto}
@media print{
 header.kopf{background:none;color:#000;border-bottom:1pt solid #000}
 .badge{border-color:#000}
 .toc{background:none;break-after:page}
 .toc ol{columns:1}
 article{break-before:page}
 article h2,section h3{break-after:avoid}
 section,table.k tr{break-inside:avoid}
}
"""

#: Die Regeln fuer den Betriebsteil - EIN EIGENER BLOCK, der nur dann in das
#: Dokument kommt, wenn auch Betriebskapitel darin stehen.
#:
#: WARUM NICHT EINFACH ANHAENGEN: Ohne diese Trennung enthielte auch eine
#: Fassung ohne Betriebsteil die Klassennamen 'aiw-h-cli-...' - im
#: Stylesheet, aber sichtbar in der Datei. Eine Pruefung "steht hier
#: irgendwo etwas vom Betriebsteil?" haette dann immer angeschlagen, und
#: '--ohne-betrieb' waere nicht mehr zeichengleich mit der Fassung von
#: Build 622. Totes CSS ist ausserdem genau die Sorte Rest, die spaeter
#: niemand mehr zuzuordnen weiss.
_CSS_BETRIEB = """
/* --- Build 623: der Betriebsteil ------------------------------------------
 * Die Kapitel kommen UNVERAENDERT aus management/help/cli_html.py - dieselbe
 * Funktion, die auch /help beliefert. Nur die Gestaltung ist hier eine
 * andere, weil diese Fassung eigenstaendig ist und help.css nicht laedt.
 * Genau so gehoert es: gegengelesen wird der TEXT, und der muss derselbe
 * sein; wie er eingefaerbt ist, darf sich unterscheiden. */
.betriebsvorspann{border-top:3px double var(--a);margin-top:3em;
 padding-top:1.4em}
.betriebsvorspann h2{color:var(--a);font-size:1.5rem;margin:0 0 .4em}
article.aiw-h-betrieb{border-left:3px solid var(--l);padding-left:1em}
article.aiw-h-betrieb h2 code{font-size:.85em}
.aiw-h-betrieb-titel{color:var(--g);font-size:.75em;font-weight:400}
.aiw-h-betrieb-marke{color:var(--g);font-size:.75rem;letter-spacing:.04em;
 text-transform:uppercase;margin:0 0 .5em}
.aiw-h-recht{background:var(--f);border-left:3px solid var(--a);
 padding:.5em .8em;margin:0 0 1.2em;font-size:.93rem}
.aiw-h-abschnitt{margin:1.4em 0}
.aiw-h-abschnitt h3{font-size:1.06rem;margin:0 0 .3em}
.aiw-h-cli-aufruf code,.aiw-h-cli-beispiel pre{display:block;
 background:var(--f);border:1px solid var(--l);border-radius:3px;
 padding:.4em .6em;font-size:.86rem;white-space:pre-wrap;
 word-break:break-word;overflow-wrap:anywhere;margin:0 0 .4em}
.aiw-h-cli-beispiel{margin:1em 0}
.aiw-h-cli-nachweis{color:var(--g);font-size:.8rem;margin:0}
.aiw-h-cli-hinweis{background:var(--f);border-left:3px solid var(--o);
 padding:.4em .7em}
.aiw-h-cli-tabelle{border-collapse:collapse;width:100%;font-size:.9rem;
 margin:.6em 0}
.aiw-h-cli-tabelle th,.aiw-h-cli-tabelle td{border:1px solid var(--l);
 padding:.35em .55em;text-align:left;vertical-align:top}
.aiw-h-cli-tabelle th{background:var(--f);font-size:.8rem}
.aiw-h-cli-art-schreibend{color:var(--o);font-weight:600}
.aiw-h-cli-art-lesend{color:var(--g)}
.aiw-h-offen{color:var(--o);font-style:italic}
/* Die Blaetterleiste ist ein Bildschirmwerkzeug. In einer Lesevorlage, die
 * am Stueck durchgegangen wird, ist sie nur Stoerung. */
.aiw-h-blaettern{display:none}
@media print{
 .betriebsvorspann{break-before:page}
 .aiw-h-cli-aufruf code,.aiw-h-cli-beispiel pre{background:none;
  border:1pt solid #000}
 .aiw-h-cli-hinweis{background:none;border-left:2pt solid #000}
 .aiw-h-cli-tabelle th{background:none}
 .aiw-h-cli-art-schreibend{color:#000;text-transform:uppercase}
 .aiw-h-cli-beispiel,.aiw-h-cli-tabelle tr{break-inside:avoid}
}
"""


def _e(text: Optional[str]) -> str:
    return html.escape(text or "", quote=True)


def _abschnitt_html(k: Sichthilfe) -> List[str]:
    teile: List[str] = []
    for a in k.abschnitte:
        teile.append('<section id="%s-%s">' % (_e(k.sicht), _e(a.anker)))
        teile.append('<h3>%s<span class="anker">#%s</span></h3>'
                     % (_e(a.titel), _e(a.anker)))
        for p in a.absaetze:
            teile.append("<p>%s</p>" % _e(p))
        if a.liste:
            tag = "ol" if a.geordnet else "ul"
            teile.append("<%s>" % tag)
            for p in a.liste:
                teile.append("<li>%s</li>" % _e(p))
            teile.append("</%s>" % tag)
        teile.append("</section>")
    return teile


def _kontext_html(eintraege, ueberschrift: str) -> List[str]:
    """
    Die Popup-Texte als Tabelle. SIE SIND DER TEIL, DEN MAN SONST NICHT ZU
    SEHEN BEKOMMT, ohne jedes markierte Element einzeln anzuklicken.
    """
    if not eintraege:
        return []
    teile = ['<div class="pop">', "<h3>%s</h3>" % _e(ueberschrift),
             '<table class="k"><thead><tr>'
             "<th>Schlüssel (steht so am Element)</th><th>Titel</th>"
             "<th>Text im Popup</th></tr></thead><tbody>"]
    for k in eintraege:
        verweis = ('<span class="verweis">&rarr; Vollhilfe: %s</span>'
                   % _e(k.verweis)) if k.verweis else ""
        teile.append("<tr><td><code>%s</code></td><td>%s</td><td>%s%s</td></tr>"
                     % (_e(k.schluessel), _e(k.titel), _e(k.text), verweis))
    teile.append("</tbody></table></div>")
    return teile


def betriebsteil_fuer_lektorat(einbeziehen: bool = True) -> Betriebsgliederung:
    """
    Der Betriebsteil fuer die Lesevorlage - AUSDRUECKLICH MIT DEM RECHT.

    Die Lektoratsfassung kennt keinen Rechtefilter (Kopf dieser Datei). Sie
    hier zu filtern hiesse, den Teil des Bestands ungelesen zu lassen, der am
    ehesten Schaden anrichtet, wenn er falsch beschrieben ist - die Aufrufe,
    die etwas veraendern.

    Der Aufruf steht in einer EIGENEN Funktion und nicht mitten im Bau, damit
    diese Absicht eine Stelle hat, an der man sie sieht und pruefen kann.
    """
    if not einbeziehen:
        return Betriebsgliederung()
    return cli_html.baue_betriebsgliederung((CLI_RECHT,))


def baue_lektoratsfassung(register: HilfeRegister,
                          nur: Sequence[str] = (),
                          build: int = 0,
                          datum: str = "",
                          betrieb: Optional[Betriebsgliederung] = None) -> str:
    """
    Reine Funktion: Register (+ Betriebsteil) -> eigenstaendiges HTML. Kein
    Datei- und kein Netzzugriff, damit sie testbar bleibt.

    'betrieb' ist wie in render_html.render_hilfe_seite ein bereits
    zusammengestellter Teil und standardmaessig None - dann entsteht
    zeichengleich die Fassung von Build 622.
    """
    # Kapitel in KATALOGREIHENFOLGE - dieselbe Ordnung wie Navigation und
    # Handbuch. Wer nach dem Lesen etwas wiederfinden will, sucht es dort,
    # wo es auch im Werkzeug steht.
    auswahl = set(nur) if nur else None
    quellen = quelle_je_sicht()
    kapitel = [register.get(e.id) for e in SICHT_KATALOG
               if register.get(e.id) is not None
               and (auswahl is None or e.id in auswahl)]

    betriebs_eintraege = (betrieb.eintraege()
                          if betrieb is not None and not betrieb.leer()
                          else ())

    offen = fehlliste_sichten(register)
    teile: List[str] = [
        "<!DOCTYPE html>", '<html lang="de">', "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>AIW &ndash; Hilfe, Lektoratsfassung</title>",
        "<style>%s%s</style>" % (
            _CSS, _CSS_BETRIEB if betriebs_eintraege else ""),
        "</head>", "<body>",
        '<header class="kopf"><h1>AIW &ndash; Hilfe: Lektoratsfassung</h1>',
        '<span class="badge">VS-NfD</span>',
        "<span>Build %s%s</span></header>"
        % (_e(str(build) if build else "?"),
           " &middot; " + _e(datum) if datum else ""),
        '<p class="hinweis">Arbeitsvorlage für die Vier-Augen-Lesung '
        "(Entscheidung F6). Sie zeigt <strong>alle</strong> verfassten Texte "
        "ohne Rechtefilter &ndash; auch Kapitel, die eine lesende Person im "
        "Betrieb nicht sähe. Die Kapitel erscheinen so, wie sie unter "
        "<code>/help</code> stehen; die Tabellen darunter enthalten die "
        "<strong>Popup-Texte</strong>, die im Werkzeug nur im Hilfemodus am "
        "jeweiligen Element sichtbar sind. "
        "Stand: %d von %d Sichten verfasst, %d noch offen.%s</p>"
        % (len(register.ids()), len(SICHT_KATALOG), len(offen),
           # Build 623: der Betriebsteil wird IM KOPF genannt und nicht erst
           # dort, wo er anfaengt. Wer die Vorlage aufschlaegt, muss wissen,
           # dass hier zwei Bestaende mit zwei Adressaten zu lesen sind -
           # und dass fuer den zweiten eine andere Sprachregel gilt.
           (" Dazu %d <strong>Betriebskapitel</strong> zu den Werkzeugen der "
            "Kommandozeile: für sie gilt Regel H-2 (Betriebssprache), nicht "
            "Regel H-1. Sie stehen alle in <code>%s</code>."
            % (len(betriebs_eintraege), _e(CLI_QUELLE)))
           if betriebs_eintraege else ""),
    ]

    # Inhaltsverzeichnis
    teile.append('<nav class="toc"><h2>Kapitel in dieser Fassung</h2><ol>')
    for k in kapitel:
        e = katalog_sicht(k.sicht)
        gruppe = e.gruppe if e is not None else "?"
        teile.append('<li><a href="#%s">%s</a> <small>(%s)</small></li>'
                     % (_e(k.sicht), _e(k.titel), _e(gruppe)))
    for e2 in betriebs_eintraege:
        teile.append('<li><a href="#%s"><code>%s</code></a> '
                     "<small>(Betrieb / %s)</small></li>"
                     % (_e(cli_html.kapitel_id(e2.schluessel)),
                        _e(e2.schluessel), _e(e2.gruppe)))
    teile.append("</ol></nav>")

    teile.append('<main class="inhalt">')

    # Die Shell-Texte zuerst: sie gehoeren zu keiner Sicht, gelten aber
    # ueberall - und sind damit die Texte, die am haeufigsten gelesen werden.
    if register.shell and auswahl is None:
        teile.append('<article id="shell">')
        teile.append("<h2>Bedienelemente der Oberfläche (Shell)</h2>")
        teile.append('<p class="kennung">kein Kapitel &ndash; nur '
                     "Kontexthilfe; gilt in jeder Sicht</p>")
        teile.append('<p class="quelle">Text steht in: <b>%s</b></p>'
                     % _e(SHELL_QUELLE))
        teile.extend(_kontext_html(
            register.shell,
            "Popup-Texte der Shell (erscheinen in JEDER Sicht)"))
        teile.append("</article>")

    for k in kapitel:
        e = katalog_sicht(k.sicht)
        teile.append('<article id="%s">' % _e(k.sicht))
        teile.append("<h2>%s</h2>" % _e(k.titel))
        teile.append('<p class="kennung">Sicht <code>%s</code> &middot; '
                     "Gruppe %s &middot; Ankerpräfixe: %s &middot; "
                     "Stand: Fassung %s</p>"
                     % (_e(k.sicht),
                        _e(e.gruppe if e is not None else "?"),
                        _e(", ".join(k.praefixe())),
                        _e(str(k.stand))))
        # Der Dateipfad je Kapitel (mc 2026-07-31): wer beim Gegenlesen eine
        # Formulierung aendern will, soll nicht suchen muessen, in welcher
        # der Inhaltsdateien sie steht.
        teile.append('<p class="quelle">Text steht in: <b>%s</b></p>'
                     % _e(quellen.get(k.sicht, "(unbekannt)")))
        teile.append('<p class="recht"><strong>Rechtelage:</strong> %s</p>'
                     % _e(k.recht_klartext))
        teile.extend(_abschnitt_html(k))
        teile.extend(_kontext_html(
            k.kontext,
            "Popup-Texte dieser Sicht (%d)" % len(k.kontext)))
        teile.append("</article>")

    # --- Der Betriebsteil ---------------------------------------------------
    # Die Kapitel kommen UNVERAENDERT aus cli_html - derselbe Aufruf, der
    # auch /help beliefert. Waere hier eine zweite Erzeugung, koennte die
    # Lesevorlage etwas anderes zeigen als die ausgelieferte Seite, und die
    # Abnahme haette dann den falschen Text abgenommen.
    if betriebs_eintraege:
        teile.append('<div class="betriebsvorspann">')
        teile.append("<h2>Betriebskapitel &ndash; die Werkzeuge der "
                     "Kommandozeile (%d)</h2>" % len(betriebs_eintraege))
        teile.append(
            '<p class="quelle">Text steht in: <b>%s</b> &ndash; '
            "alle %d Kapitel, ein Eintrag je Werkzeug. Eine Korrektur ist "
            "dort einzutragen und nirgends sonst.</p>"
            % (_e(CLI_QUELLE), len(betriebs_eintraege)))
        teile.append(
            "<p><strong>Beim Gegenlesen zu beachten:</strong> Für diese "
            "Kapitel gilt Regel H-1 <em>nicht</em>. Dateinamen, "
            "Datenbanknamen und Aufrufe sind hier richtig und sollen so "
            "stehen bleiben (Regel H-2). Zu prüfen ist etwas anderes: ob die "
            "Angabe <em>lesend</em> oder <em>schreibend</em> stimmt, ob die "
            "genannten Datenbanken vollständig sind, ob die "
            "Betriebsvoraussetzung zutrifft &ndash; und ob jeder "
            "Beispielaufruf einen Prüfnachweis trägt.</p>")
        teile.append("</div>")
        teile.append(cli_html.kapitel_alle_html(betrieb))

    teile.append("</main>")

    if offen:
        teile.append('<footer><strong>Noch ohne Kapitel (%d):</strong> %s'
                     % (len(offen), _e(", ".join(offen))))
    else:
        teile.append("<footer>Alle Sichten haben ein Kapitel.")
    if betrieb is not None and not betrieb.leer():
        # Der Leerbefund wird AUSGESPROCHEN, nicht weggelassen: 'keine
        # Aufzaehlung' und 'es gibt nichts aufzuzaehlen' sehen sonst gleich
        # aus (Grundregel 1).
        ohne = betrieb.ohne_beispiele()
        teile.append(
            "<br><strong>Betriebskapitel ohne gefahrenen Beispielaufruf "
            "(%d):</strong> %s"
            % (len(ohne), _e(", ".join(ohne)) if ohne else "keine"))
    teile.append("<br>VS-NUR FÜR DEN DIENSTGEBRAUCH &middot; Regel H-0: die "
                 "Hilfe beschreibt das Werkzeug, niemals Falldaten.</footer>")
    teile.append("</body></html>")
    return "\n".join(t for t in teile if t)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Erzeugt die Lektoratsfassung der Hilfe (ein HTML).",
        epilog=cli_epilog.epilog("hilfe_lektorat"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--ziel", default=STANDARD_ZIEL,
                   help="Zieldatei (Vorgabe: %s)" % STANDARD_ZIEL)
    p.add_argument("--nur", default="",
                   help="nur diese Sichten, kommagetrennt "
                        "(Vorgabe: alle verfassten). Der Betriebsteil "
                        "entfaellt dabei.")
    p.add_argument("--nur-betrieb", action="store_true",
                   help="NUR die Betriebskapitel (die Werkzeuge der "
                        "Kommandozeile), ohne die Sichtkapitel.")
    p.add_argument("--ohne-betrieb", action="store_true",
                   help="Die Betriebskapitel weglassen (Fassung wie vor "
                        "Build 623).")
    args = p.parse_args(argv)

    # ZWEI GEGENSAETZLICHE SCHALTER WERDEN NICHT AUSGELEGT, sondern
    # zurueckgewiesen. Eine Vorrangregel muesste man sich merken - und wer
    # sich vertut, bekaeme wortlos eine Fassung, die er nicht wollte.
    if args.nur_betrieb and args.ohne_betrieb:
        print("--nur-betrieb und --ohne-betrieb schliessen einander aus.",
              file=sys.stderr)
        return 2
    if args.nur_betrieb and args.nur:
        print("--nur-betrieb und --nur schliessen einander aus.",
              file=sys.stderr)
        return 2

    register = lade_register()
    nur = [s.strip() for s in args.nur.split(",") if s.strip()]

    # Ein Tippfehler in --nur darf nicht zu einer stillschweigend leeren
    # Fassung fuehren (Grundregel 1).
    unbekannt = sorted(set(nur) - set(register.ids()))
    if unbekannt:
        print("Keine verfassten Kapitel zu: %s" % ", ".join(unbekannt),
              file=sys.stderr)
        print("Verfasst sind: %s" % ", ".join(register.ids()), file=sys.stderr)
        return 1

    build, datum = 0, ""
    try:
        from core.build_info import BuildInfo
        info = BuildInfo(Path(__file__).resolve().parents[1])
        build, datum = info.build, info.date
    except Exception as exc:                      # pragma: no cover
        print("Hinweis: build.json nicht lesbar (%s)" % exc, file=sys.stderr)

    # Der Betriebsteil entfaellt bei --nur: wer auf einzelne Sichten
    # eingrenzt, meint die Sichten - genau wie die Shell-Texte heute schon
    # entfallen. Mit --nur-betrieb entfaellt umgekehrt alles andere.
    if args.nur_betrieb:
        register_fuer_ausgabe = HilfeRegister(())
        nur = []
    else:
        register_fuer_ausgabe = register
    betrieb = betriebsteil_fuer_lektorat(
        einbeziehen=not args.ohne_betrieb and not nur)

    text = baue_lektoratsfassung(register_fuer_ausgabe, nur, build, datum,
                                 betrieb=betrieb)
    ziel = Path(args.ziel)
    ziel.write_text(text, encoding="utf-8")

    # BEFUND Build 602: die Meldung nannte bisher IMMER den Umfang des ganzen
    # Registers - auch bei --nur. Wer eine Teilfassung erzeugte, las dann
    # "27 Kapitel" und hatte sechs in der Hand. Eine Zahl, die etwas anderes
    # zaehlt als das erzeugte Dokument, ist eine Falschauskunft; gezaehlt wird
    # jetzt, was WIRKLICH in der Datei steht. Build 623 zieht das fuer den
    # Betriebsteil nach - aus demselben Grund.
    gewaehlt = [s for s in register_fuer_ausgabe.sichten
                if not nur or s.sicht in set(nur)]
    popups = sum(len(s.kontext) for s in gewaehlt)
    if not nur and not args.nur_betrieb:
        popups = len(register.kontext_schluessel())      # samt Shell-Texten
    print("Geschrieben: %s (%d Kapitel, %d Popup-Texte, %d Betriebskapitel)"
          % (ziel, len(gewaehlt), popups, len(betrieb.eintraege())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
