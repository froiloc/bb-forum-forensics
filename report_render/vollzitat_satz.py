# =============================================================================
# report_render/vollzitat_satz.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   DAS DATENMODELL DER VIERTEN DARSTELLUNGSVARIANTE. Was hier steht, ist das
#   FERTIGE Ergebnis: der Absatz ist gefunden und eingefaerbt, der Name
#   aufgeloest, das Datum ermittelt, die Quelle benannt. Die vier Renderer
#   (HTML, PDF, DOCX, SQLite) und der Berichtseditor entscheiden nur noch,
#   WIE sie es malen - nicht mehr, WAS es ist.
#
# WARUM DIESE TRENNUNG. Genau daran ist der Zitatblock schon einmal
#   zerbrochen (Vorgang 9c41a7e6, s. Kopf von report_render/quote_typen.py):
#   zwei Stellen, die dieselbe Frage beantworten, geben irgendwann zwei
#   Antworten. Ein Vollzitat beantwortet neun Fragen auf einmal; sie in vier
#   Renderern und einer JS-Datei zu beantworten waere fuenf Gelegenheiten,
#   auseinanderzulaufen.
#
# ── DIE HIERARCHIE ───────────────────────────────────────────────────────────
#
#   VollzitatGruppe   eine Beweismittelgruppe (ein 'evidence'-Block)
#     └ Unterblock    EINE Quelle - ein Forenbeitrag oder eine PN
#         ├ Absatz    ein umschliessender Absatz, fertig eingefaerbt
#         └ Befund    ein einzelner Beleg: Kategorie, Ermittler, Notiz
#
#   Anforderung 9 der Chef-Ermittlerin: "Wenn moeglich, dann sollen
#   Annotationen, die denselben Beitrag betreffen, und die derselben
#   Belegsammlung zugeordnet werden, in einen Unterblock zusammengefasst
#   werden." Der Unterblock IST diese Zusammenfassung. Er traegt die
#   Quellenangabe, das Datum und den Link genau EINMAL - und darunter so
#   viele Befunde, wie es Belege gibt.
#
#   Warum es zwischen Unterblock und Befund noch die Ebene 'Absatz' gibt:
#   zwei Belege im selben Beitrag koennen in VERSCHIEDENEN Absaetzen stehen.
#   Dann gehoeren sie in denselben Unterblock (dieselbe Quelle, dasselbe
#   Datum, derselbe Link), aber nicht in denselben Absatz. Ohne diese Ebene
#   muesste der Absatz entweder doppelt gedruckt oder einer der beiden Belege
#   ohne Umgebung gezeigt werden.
#
# ── DIE NUMMERN ──────────────────────────────────────────────────────────────
#
#   Jeder Befund traegt eine Nummer, die im Absatz als Hochzahl an der
#   Markierung wiederkehrt. Sie laeuft JE UNTERBLOCK von 1 an und nicht
#   durch den ganzen Bericht: ein Unterblock ist die Einheit, die ein Leser
#   auf einen Blick erfasst, und dreistellige Hochzahlen in einem Zitat
#   erschweren genau das. Die Beleg-ID steht ohnehin im Befund - sie ist die
#   Kennung, die Nummer ist nur der Verweis.
#
# ── JEDER SATZ SAGT, WIE SICHER ER IST ───────────────────────────────────────
#
#   'absatz_weg' und 'name_quelle' wandern bis in den Bericht. Ein Absatz,
#   der ueber den Wortlaut gefunden wurde, und ein Nachname, der aus einer
#   Anzeigezeichenkette zerlegt wurde, sind SCHWAECHER als der jeweilige
#   Sollweg. Der Leser der Akte muss das sehen koennen, ohne den Quelltext zu
#   kennen (Grundregel: Ueberpruefbarkeit).
#
# Grundregeln: GR1, GR6, GR10.
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from report_render.quellen_kunde import Quelle


@dataclass
class Befund:
    """
    Ein einzelner Beleg innerhalb eines Unterblocks.

    Felder:
        nummer         - Verweisnummer im Absatz (1, 2, 3 ... je Unterblock)
        annotation_id  - annotations.id - die Kennung, unter der der Beleg
                         in der Beweismitteldatenbank steht
        kategorie      - Rohwert aus annotations.category (kann unbekannt sein)
        kategorie_text - ausgeschriebene Bezeichnung (core/kategorie_farben)
        css_klasse     - 'vz-cat-...' fuer den HTML-Bericht
        farbe          - Hinterlegungsfarbe '#rrggbb'
        markierung     - der markierte Wortlaut
        notiz          - annotations.text, die Notiz des Ermittlers
        ermittler      - Anzeigename ("KHK Muster") oder das Kuerzel
        name_quelle    - ad_felder | display_name | kuerzel
        absatz_weg     - xpath | text | keiner | uebersetzung
        hinweis        - Klartext, wenn absatz_weg != 'xpath'; sonst ""
    """
    nummer: int
    annotation_id: int
    kategorie: str
    kategorie_text: str
    css_klasse: str
    farbe: str
    markierung: str
    notiz: str
    ermittler: str
    name_quelle: str
    absatz_weg: str
    hinweis: str = ""


@dataclass
class Absatz:
    """
    Ein umschliessender Absatz, fertig fuer die Ausgabe.

    Felder:
        html      - der Absatz als HTML-Fragment, Markierungen bereits
                    hinterlegt. BEREITS SICHER: er stammt aus dem
                    zerlegten Seitenabzug und ist von lxml neu serialisiert;
                    die Renderer geben ihn UNVERAENDERT aus (dieselbe
                    Invariante wie bei resolved_text, s. Kopf von
                    report_render/html_renderer.py).
        text      - derselbe Absatz als Klartext - fuer DOCX, PDF und die
                    SQLite-Spiegelung, die kein HTML koennen
        nummern   - die Verweisnummern der Befunde, die in diesem Absatz
                    markiert sind (in Reihenfolge des Auftretens)
        ersatz    - True, wenn KEIN Absatz gefunden wurde und statt dessen
                    nur die markierte Stelle wiedergegeben wird
        moeglich  - True, wenn der Wortlaut auf der Seite MEHRFACH vorkommt
                    und dieser Absatz nur EINE der moeglichen Fundstellen ist
                    (Build 727, Weisung Alex 28.08.2026: alle zeigen statt
                    stillschweigend eine zu waehlen)
        von_gesamt- (Nummer, Anzahl) der moeglichen Fundstellen, sonst None
    """
    html: str
    text: str
    nummern: List[int] = field(default_factory=list)
    ersatz: bool = False
    moeglich: bool = False
    von_gesamt: Optional[tuple] = None


@dataclass
class Unterblock:
    """
    Eine Quelle mit allen Belegen, die sie betreffen.

    Felder:
        quelle    - Art, Betreff/Partner, Datum, Link (report_render.quellen_kunde)
        absaetze  - die Absaetze dieser Quelle, in Fundreihenfolge
        befunde   - die Belege dieser Quelle, nach Verweisnummer
    """
    quelle: Quelle
    absaetze: List[Absatz] = field(default_factory=list)
    befunde: List[Befund] = field(default_factory=list)

    @property
    def fehlt(self) -> bool:
        """True, wenn es zu diesem Beleg keine Annotation (mehr) gibt."""
        return self.quelle.ist_unbekannt


@dataclass
class VollzitatGruppe:
    """
    Eine Beweismittelgruppe in der Darstellung 'Vollzitat'.

    Felder:
        beschriftung  - block_data.group_label, die Beschriftung der Sammlung
        unterbloecke  - die Quellen, in der Reihenfolge ihres ersten Belegs
        warnungen     - alles, was fuer den Abschnitt "Hinweise zur Erzeugung"
                        gesammelt wurde (R2). Sie werden NICHT hier gedruckt,
                        sondern vom Renderer in den Hinweisabschnitt gehoben -
                        so steht die Vollstaendigkeitsaussage des Berichts an
                        einer Stelle und nicht verstreut.
        beleg_anzahl  - Zahl der Belege insgesamt (auch der nicht auffindbaren)
    """
    beschriftung: str = ""
    unterbloecke: List[Unterblock] = field(default_factory=list)
    warnungen: List[str] = field(default_factory=list)
    beleg_anzahl: int = 0

    @property
    def quellen_anzahl(self) -> int:
        return len(self.unterbloecke)
