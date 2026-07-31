# =============================================================================
# management/help/render_html.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H2)
# =============================================================================
# Zweck:
#   Die Vollhilfe als eigenstaendige HTML-Seite (GET /help) - gerendert aus
#   dem Register, nicht aus einem zweiten Autorenbestand (Konzept §3.3).
#
#   REINE FUNKTIONEN. Die Renderfunktion bekommt ein bereits GEFILTERTES
#   Gliederungsmodell und weiss nichts von Rechten, Datenbanken oder Requests.
#   Damit ist sie ohne Server pruefbar - und die Sperre (E1) kann nicht
#   versehentlich im Renderer umgangen werden, weil der Renderer die
#   ungefilterten Daten nie zu sehen bekommt.
#
#   ESCAPING: Jeder redaktionelle Text laeuft durch html.escape(). Die Hilfe
#   ist zwar hausgeschriebener Text, aber sie wird druckbar ausgeliefert und
#   soll auch dann korrekt sein, wenn jemand '<' oder '&' schreibt. Die
#   Disziplin ist dieselbe wie die textContent-Disziplin der Sichten.
#
#   PLATZHALTER STATT LEERSTELLE (Grundregel 1): Eine sichtbare Sicht ohne
#   Kapitel erscheint im Verzeichnis MIT dem ehrlichen Hinweis "Hilfe folgt"
#   - sie verschwindet nicht. Wer die Hilfe aufschlaegt, soll sehen, was noch
#   fehlt, statt zu glauben, es gaebe nichts.
#
# BUILD 593 (H6) ERGAENZT: Suchindex, Kapitelnavigation und Druckfassung.
#   Aus dem Kapitelstapel wird ein benutzbares Handbuch. Der Suchindex wird
#   SERVERSEITIG gebaut und ist damit bereits nach Rechten gefiltert (E1):
#   was die Person nicht sehen darf, ist auch nicht durchsuchbar. Ein
#   clientseitig gefilterter Index haette den vollen Bestand ausgeliefert.
#
# Version: v0.8.593 - Build: 593 - 2026-07-31
# =============================================================================

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from management.help.modell import Abschnitt, HilfeRegister, Sichthilfe
from management.help.sichtbarkeit import sichtbare_sicht_ids
from management.help.sicht_katalog import SICHT_KATALOG, SichtEintrag, sicht as katalog_sicht

PLATZHALTER_TEXT = "Hilfe folgt (Baustelle H)."


@dataclass(frozen=True)
class Kapiteleintrag:
    """Ein Eintrag der Gliederung: Sicht + (evtl. noch fehlendes) Kapitel."""
    sicht_id: str
    label: str
    gruppe: str
    kapitel: Optional[Sichthilfe]

    @property
    def vorhanden(self) -> bool:
        return self.kapitel is not None


@dataclass(frozen=True)
class Gliederung:
    """Das gefilterte Seitenmodell: Gruppen in Katalogfolge mit ihren Sichten."""
    gruppen: Tuple[Tuple[str, Tuple[Kapiteleintrag, ...]], ...] = ()

    def eintraege(self) -> Tuple[Kapiteleintrag, ...]:
        out: List[Kapiteleintrag] = []
        for _, e in self.gruppen:
            out.extend(e)
        return tuple(out)

    def offene(self) -> Tuple[str, ...]:
        return tuple(e.sicht_id for e in self.eintraege() if not e.vorhanden)


def baue_gliederung(register: HilfeRegister,
                    capabilities: Iterable[str],
                    katalog: Sequence[SichtEintrag] = SICHT_KATALOG
                    ) -> Gliederung:
    """
    Baut das gefilterte Seitenmodell: nur die Sichten, die diese Person sehen
    darf; je Sicht das Kapitel oder None (dann Platzhalter).

    Die Filterung passiert HIER, VOR dem Rendern - genau wie E1 es verlangt.
    """
    erlaubt = set(sichtbare_sicht_ids(capabilities, katalog))
    gruppenfolge: List[str] = []
    for e in katalog:
        if e.gruppe not in gruppenfolge:
            gruppenfolge.append(e.gruppe)

    je_gruppe = {g: [] for g in gruppenfolge}
    for e in katalog:
        if e.id not in erlaubt:
            continue
        je_gruppe[e.gruppe].append(Kapiteleintrag(
            sicht_id=e.id, label=e.label, gruppe=e.gruppe,
            kapitel=register.get(e.id)))

    return Gliederung(tuple(
        (g, tuple(je_gruppe[g])) for g in gruppenfolge if je_gruppe[g]))


# -----------------------------------------------------------------------------
# Rendern
# -----------------------------------------------------------------------------

def _e(text: Optional[str]) -> str:
    return html.escape(text or "", quote=True)


def anker_id(sicht_id: str, anker: str) -> str:
    """
    Die Sprungmarke eines Abschnitts. EINE Stelle, an der die Form festliegt -
    die Kontexthilfe im Browser bildet dieselbe Marke (H4), und der
    Verweistest haelt beide zusammen.
    """
    return "%s-%s" % (sicht_id, anker)


def _abschnitt_html(sicht_id: str, a: Abschnitt) -> str:
    teile = ['<section class="aiw-h-abschnitt" id="%s">'
             % _e(anker_id(sicht_id, a.anker)),
             "<h3>%s</h3>" % _e(a.titel)]
    for p in a.absaetze:
        teile.append("<p>%s</p>" % _e(p))
    if a.liste:
        tag = "ol" if a.geordnet else "ul"
        teile.append("<%s>" % tag)
        for p in a.liste:
            teile.append("<li>%s</li>" % _e(p))
        teile.append("</%s>" % tag)
    teile.append("</section>")
    return "\n".join(teile)


def _blaetterleiste(vorher: Optional[Kapiteleintrag],
                    nachher: Optional[Kapiteleintrag]) -> str:
    """
    Voriges / naechstes Kapitel. Ein Handbuch, in dem man nur ueber das
    Inhaltsverzeichnis weiterkommt, liest sich niemand durch - und die
    Nachbarschaft der Kapitel folgt der Nav-Ordnung, ist also selbst eine
    Aussage ueber Zusammengehoerigkeit.
    """
    links = []
    if vorher is not None:
        links.append('<a class="aiw-h-vor" href="#%s">&larr; %s</a>'
                     % (_e(vorher.sicht_id), _e(vorher.label)))
    if nachher is not None:
        links.append('<a class="aiw-h-zurueck" href="#%s">%s &rarr;</a>'
                     % (_e(nachher.sicht_id), _e(nachher.label)))
    if not links:
        return ""
    return ('<nav class="aiw-h-blaettern" aria-label="Kapitel">%s</nav>'
            % "".join(links))


def _kapitel_html(eintrag: Kapiteleintrag,
                  vorher: Optional[Kapiteleintrag] = None,
                  nachher: Optional[Kapiteleintrag] = None) -> str:
    kopf = ['<article class="aiw-h-kapitel" id="%s">' % _e(eintrag.sicht_id),
            "<h2>%s</h2>" % _e(eintrag.label)]
    if eintrag.kapitel is None:
        kopf.append('<p class="aiw-h-offen">%s</p>' % _e(PLATZHALTER_TEXT))
        kopf.append(_blaetterleiste(vorher, nachher))
        kopf.append("</article>")
        return "\n".join(kopf)

    k = eintrag.kapitel
    # Die Rechtelage steht PROMINENT im Kapitelkopf (E1).
    kopf.append('<p class="aiw-h-recht"><strong>Rechtelage:</strong> %s</p>'
                % _e(k.recht_klartext))
    for a in k.abschnitte:
        kopf.append(_abschnitt_html(k.sicht, a))
    if k.stand:
        # Build 597: KEIN Wort "Build" auf der Anwenderseite (Regel H-1).
        # Die Nachvollziehbarkeit bleibt - die Zahl ist dieselbe -, aber sie
        # heisst jetzt so, wie eine anwendende Person sie lesen kann.
        kopf.append('<p class="aiw-h-stand">Stand dieser Hilfe: Fassung %d</p>'
                    % k.stand)
    kopf.append(_blaetterleiste(vorher, nachher))
    kopf.append("</article>")
    return "\n".join(kopf)


# -----------------------------------------------------------------------------
# Suchindex (Build 593 / H6)
# -----------------------------------------------------------------------------

def suchindex(gliederung: Gliederung) -> List[dict]:
    """
    Der Suchindex - EIN Eintrag je sichtbarem Kapitel.

    Er wird SERVERSEITIG aus der bereits gefilterten Gliederung gebaut. Das
    ist keine Bequemlichkeit: Ein clientseitig zusammengesetzter Index
    muesste den vollen Bestand ausliefern, um darin suchen zu koennen - und
    haette damit genau die Sperre ausgehebelt, die E1 verlangt.

    Der Suchtext eines Kapitels besteht aus (in dieser Reihenfolge):
      * dem Sicht-Label,
      * den Stichworten aus dem VIEW_CATALOG (dem gepflegten Grundstock,
        der schon die Kommandopalette speist - kein zweiter Bestand),
      * den Abschnittsueberschriften,
      * den Titeln der Kontexthilfen.
    Der Fliesstext bleibt ABSICHTLICH draussen: eine Volltextsuche ueber alle
    Absaetze faende bei einem Wort wie 'Fall' fast jedes Kapitel und waere
    damit wertlos. Gesucht wird nach dem, wonach man in einem Handbuch sucht:
    Namen von Sichten, Elementen und Abschnitten.
    """
    raus: List[dict] = []
    for e in gliederung.eintraege():
        katalog = katalog_sicht(e.sicht_id)
        worte: List[str] = [e.label]
        if katalog is not None and katalog.stichworte:
            worte.append(katalog.stichworte)
        if e.kapitel is not None:
            worte.extend(a.titel for a in e.kapitel.abschnitte)
            worte.extend(k.titel for k in e.kapitel.kontext)
        raus.append({
            "id": e.sicht_id,
            "label": e.label,
            "gruppe": e.gruppe,
            "offen": not e.vorhanden,
            "worte": " ".join(worte).lower(),
        })
    return raus


def _verzeichnis_html(gliederung: Gliederung) -> str:
    teile = ['<nav class="aiw-h-verzeichnis" aria-label="Inhalt">',
             "<h2>Inhalt</h2>",
             # Build 593: das Suchfeld sitzt IM Verzeichnis und nicht in der
             # Kopfzeile - man sucht hier nach einem Kapitel, also gehoert
             # das Feld dorthin, wo die Kapitel stehen. Ohne JavaScript
             # bleibt es wirkungslos, deshalb ist es 'hidden' vorbelegt und
             # wird von help.js sichtbar geschaltet: ein totes Eingabefeld
             # waere schlimmer als keines.
             '<div class="aiw-h-suchfeld" id="aiw-h-suchfeld" hidden>'
             '<label for="aiw-h-suche">Kapitel suchen</label>'
             '<input type="search" id="aiw-h-suche" autocomplete="off"'
             ' placeholder="z. B. ampel, frist, rechte">'
             '<span class="aiw-h-suchzahl" id="aiw-h-suchzahl"></span>'
             "</div>"]
    for gruppe, eintraege in gliederung.gruppen:
        teile.append('<h3 data-gruppe="%s">%s</h3>' % (_e(gruppe), _e(gruppe)))
        teile.append('<ul data-gruppe="%s">' % _e(gruppe))
        for e in eintraege:
            marke = "" if e.vorhanden else ' <span class="aiw-h-offen">(%s)</span>' \
                % _e("Hilfe folgt")
            teile.append('<li data-sicht="%s"><a href="#%s">%s</a>%s</li>'
                         % (_e(e.sicht_id), _e(e.sicht_id), _e(e.label), marke))
        teile.append("</ul>")
    teile.append("</nav>")
    return "\n".join(teile)


def _index_html(gliederung: Gliederung) -> str:
    """
    Der Suchindex als eingebettetes JSON.

    <script type="application/json"> wird vom Browser NICHT ausgefuehrt - der
    Inhalt ist reine Nutzlast. Trotzdem wird '<' maskiert: ein '</script>' im
    Text wuerde den Block sonst vorzeitig beenden. Das ist der einzige
    Ausbruch, den ein JSON-Block in HTML hat, und er wird hier geschlossen.
    """
    import json
    roh = json.dumps(suchindex(gliederung), ensure_ascii=False)
    roh = roh.replace("<", "\\u003c").replace(">", "\\u003e")
    return ('<script type="application/json" id="aiw-h-index">%s</script>'
            % roh)


def render_hilfe_seite(gliederung: Gliederung,
                       version: str = "",
                       build: int = 0,
                       stand_datum: str = "") -> str:
    """
    Die vollstaendige, eigenstaendige Hilfeseite.

    Die Fusszeile nennt Version und Buildnummer (Bauplan H2). Das ist kein
    Schmuck: Wer einen Hilfeausdruck in der Hand haelt, muss sagen koennen,
    zu welchem Stand des Werkzeugs er gehoert.
    """
    eintraege = gliederung.eintraege()
    stuecke = []
    for i, e in enumerate(eintraege):
        stuecke.append(_kapitel_html(
            e,
            vorher=eintraege[i - 1] if i > 0 else None,
            nachher=eintraege[i + 1] if i + 1 < len(eintraege) else None))
    kapitel = "\n".join(stuecke)

    offen = gliederung.offene()
    hinweis = ""
    if offen:
        # Ehrlich statt still: die Seite sagt selbst, was noch fehlt.
        hinweis = ('<p class="aiw-h-hinweis">Diese Hilfe ist im Aufbau. Noch '
                   'ohne Kapitel: %d von %d hier sichtbaren Sichten.</p>'
                   % (len(offen), len(eintraege)))

    return (
        "<!DOCTYPE html>\n"
        '<html lang="de">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>AIW - Hilfe</title>\n"
        '<link rel="stylesheet" href="/static/help.css">\n'
        "</head>\n<body class=\"aiw-h\">\n"
        '<header class="aiw-h-kopf">\n'
        "<h1>AIW - Hilfe</h1>\n"
        '<span class="aiw-h-badge">VS-NfD</span>\n'
        "</header>\n"
        + hinweis
        + '<div class="aiw-h-rahmen">\n'
        + _verzeichnis_html(gliederung)
        + '\n<main class="aiw-h-inhalt">\n'
        + kapitel
        + "\n</main>\n</div>\n"
        + '<footer class="aiw-h-fuss">%s</footer>\n'
          % _e("AIW-Verwaltung, Fassung %s (%s)%s - Hilfe ist fallinhaltsfrei "
               "(Regel H-0): sie beschreibt das Werkzeug, niemals Falldaten."
               % (version or "?", build or "?",
                  " - Stand %s" % stand_datum if stand_datum else ""))
        + _index_html(gliederung) + "\n"
        + '<script src="/static/help.js"></script>\n'
        + "</body>\n</html>\n"
    )


def kontext_nutzlast(register: HilfeRegister, sicht_id: str) -> dict:
    """
    Die Kontexthilfe einer Sicht als JSON-faehiges Woerterbuch:
    Schluessel -> {titel, text, verweis}. Ein Fetch je Sichtaktivierung
    (Konzept §3.2) - deshalb gebuendelt und nicht je Element.

    DIE SHELL-TEXTE LIEGEN IMMER BEI (Build 591 / H4). Kopfzeile, Navigation
    und Banner stehen in JEDER Sicht; ihre Erklaerungen an eine einzelne Sicht
    zu haengen hiesse, sie auf allen anderen unerreichbar zu machen. Sie
    unterliegen KEINER Rechtesperre - wer das Werkzeug oeffnen kann, sieht
    diese Bedienelemente ohnehin vor sich.
    """
    eintraege = {}
    for k in register.shell:
        eintraege[k.schluessel] = {
            "titel": k.titel, "text": k.text, "verweis": k.verweis}
    kapitel = register.get(sicht_id)
    if kapitel is not None:
        for k in kapitel.kontext:
            eintraege[k.schluessel] = {
                "titel": k.titel, "text": k.text, "verweis": k.verweis}
    return {"sicht": sicht_id, "anzahl": len(eintraege), "eintraege": eintraege}
