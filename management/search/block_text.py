# =============================================================================
# management/search/block_text.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B560)
# =============================================================================
# Zweck:
#   Klartext aus den JSON-Spalten der Beweismitteldatenbank gewinnen. Drei
#   Spalten aus der Indexliste sind kein Freitext, sondern JSON:
#     * report_blocks.block_data              (Editor.js-Block)
#     * report_blocks.placeholder_values_json (eingesetzte Platzhalterwerte)
#     * annotations.tags_json                 (Schlagworte)
#
#   Kein Klassenmodul (Grundregel 10 betrifft Klassen) — reine Funktionen ohne
#   Zustand. Eigene Datei, weil der Quellenleser (560), spaeter die
#   Trefferverifikation gegen die Quelle (562) und moeglicherweise die Sicht
#   (563) dieselbe Umwandlung brauchen. Zwei Implementierungen derselben
#   Umwandlung waeren zwei verschiedene Antworten auf die Frage, was im Text
#   steht.
#
# ── DIE ENTWURFSENTSCHEIDUNG: EINSAMMELN STATT AUFZAEHLEN ────────────────────
#
#   Der naheliegende Weg waere, die neun bekannten Blocktypen aufzuzaehlen
#   (report_render/report_source.py:59-62: paragraph, header, list, table,
#   quote, image, delimiter, marker, evidence) und je Typ die richtigen Felder
#   auszulesen — so macht es der Renderer, und dort ist das richtig, weil er
#   ein LAYOUT erzeugt.
#
#   Fuer den Index waere es falsch. Ein ZEHNTER Blocktyp — und die Kommentare im
#   Bestand rechnen ausdruecklich mit einem (report_source.py:57: "Ein zehnter
#   Typ wird gemeldet, nicht uebersprungen") — waere in einer Aufzaehlung
#   unsichtbar: sein Text landete nie im Index, die Suche fuende ihn nie, und
#   der Leerbefund saehe aus wie ein vollstaendiger Befund. Genau das verbietet
#   Grundregel 1.
#
#   Deshalb wird REKURSIV EINGESAMMELT: jede Zeichenkette im JSON geht in den
#   Klartext, ausser sie steht unter einem Schluessel, der bekanntermassen
#   Maschinendaten traegt (_STRUKTURSCHLUESSEL). Die Liste der Ausnahmen ist
#   kurz und konservativ — im Zweifel wird AUFGENOMMEN. Ein Wort zuviel im
#   Index kostet Plattenplatz in einem Hilfsmittel; ein Wort zuwenig kostet
#   einen Treffer, den niemand vermisst, weil niemand von ihm weiss.
#
# ── HTML IM EDITOR.JS-TEXT ───────────────────────────────────────────────────
#
#   Editor.js legt Inline-Auszeichnung als HTML im Text ab ('<b>', '<i>',
#   '<a href=...>', '<mark>'). Unbehandelt landeten die Tagnamen im Index: eine
#   Suche nach 'mark' fuende jeden hervorgehobenen Absatz, und die Wortsuche
#   nach 'href' waere der haeufigste Treffer der Anlage. Die Tags werden daher
#   entfernt und durch EIN Leerzeichen ersetzt — nicht durch nichts, sonst
#   verkleben '<b>Birnen</b>mus' zu einem Wort, das es im Text nicht gibt, und
#   'Birnen' waere in der Wortsuche verloren.
#
#   HTML-Entitaeten werden aufgeloest (html.unescape), weil '&amp;' im Index
#   sonst als 'amp' erschiene und der tatsaechliche Text '&' unauffindbar waere.
#
#   ABSICHTLICH KEIN HTML-PARSER: die Eingabe ist kein Dokument, sondern ein
#   kurzer Textschnipsel aus einer kontrollierten Quelle; ein Parser
#   (html.parser) waere je Satz ein Objekt mehr bei ueber einer Million
#   moeglicher Saetze. Der regulaere Ausdruck kann an pathologischer Eingabe
#   scheitern — er kann dabei aber nur ZUVIEL stehen lassen, nie zuwenig, und
#   zuviel ist die harmlose Richtung.
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================

import html as _html
import json
import re
from typing import Any, FrozenSet, List, Optional

# --- Schluessel, deren Werte KEIN Ermittlertext sind --------------------------
#   Bewusst kurz gehalten. Jeder Eintrag ist eine Auslassung und braucht einen
#   Grund; im Zweifel steht ein Schluessel NICHT hier.
#
#   'url'/'src'      — Bildquellen aus dem SimpleImage-Block. Es sind Pfade der
#                      Anlage, kein Ermittlertext. (Der forensisch harte
#                      Bildverweis liegt ohnehin in assets_<uid>.db,
#                      report_source.py:256-262.)
#   'block_id'/'id'  — technische Schluessel.
#   'block_type'/'type'/'style'/'alignment'/'level'/'stretched'/'withHeadings'
#                    — Darstellungssteuerung.
#   'evidence_ids'   — Verweisliste auf Annotationen (Zahlen; der Text der
#                      Annotation ist ueber annotations.text schon im Index).
#   Schluessel mit fuehrendem '_' — vom Renderer erzeugte Ableitungen
#                      ('_resolved_text' usw.), die den Originaltext DOPPELT
#                      enthielten. Sie stehen nicht in der Datenbank, aber die
#                      Funktion wird auch auf gerenderte Strukturen angewandt.
_STRUKTURSCHLUESSEL: FrozenSet[str] = frozenset({
    "url", "src", "block_id", "id", "block_type", "type", "style",
    "alignment", "level", "stretched", "withHeadings", "withBorder",
    "withBackground", "evidence_ids", "module_id", "anchor_ids",
})

#: HTML-Tag oder -Kommentar. Nicht-gierig, damit '<b>x</b>' nicht als EIN Tag
#  gilt. Ein '<' ohne schliessendes '>' bleibt stehen — die harmlose Richtung.
_TAG_RE = re.compile(r"<[^<>]{0,4000}?>")

#: Mehrfach-Weissraum (inkl. Zeilenumbruch) zu einem Leerzeichen.
_WS_RE = re.compile(r"\s+")

#: Obergrenze je Satz. Ein einzelner Berichtsbaustein kann sehr lang werden;
#  FTS5 kommt damit zurecht, der trigram-Index waechst aber linear mit der
#  Textlaenge. 64 KiB je Satz ist weit oberhalb jedes realen Bausteins und
#  verhindert zugleich, dass eine defekte Zeile den Indexlauf sprengt.
#  WIRD DIE GRENZE GEZOGEN, IST DAS EIN BEFUND UND KEIN DETAIL: der Aufrufer
#  erfaehrt es ueber gekuerzt(), damit es in der Auslieferung benannt werden
#  kann statt still zu geschehen.
MAX_SATZ_LAENGE = 65536


def html_zu_klartext(roh: Optional[str]) -> str:
    """
    HTML-Auszeichnung entfernen, Entitaeten aufloesen, Weissraum normalisieren.

    Tags werden durch EIN LEERZEICHEN ersetzt (nicht durch nichts), damit
    '<b>Birnen</b>mus' nicht zu 'Birnenmus' verklebt — ein Wort, das im
    Originaltext nicht steht. Fuer die Teilstringsuche waere der Unterschied
    egal, fuer die Wortsuche ist er entscheidend.
    """
    if not roh:
        return ""
    ohne_tags = _TAG_RE.sub(" ", str(roh))
    entschluesselt = _html.unescape(ohne_tags)
    return _WS_RE.sub(" ", entschluesselt).strip()


def _sammle(knoten: Any, aus: List[str], tiefe: int = 0) -> None:
    """
    Rekursiv alle Zeichenketten einsammeln (Hilfsfunktion von json_klartext).

    Die Tiefenbegrenzung schuetzt vor pathologisch verschachteltem JSON. Sie
    ist bewusst grosszuegig (32): Editor.js-Bloecke sind flach (Tabelle =
    Liste von Listen = Tiefe 3), und eine zu enge Grenze waere eine stille
    Auslassung genau der Art, die dieses Modul vermeiden soll.
    """
    if tiefe > 32:
        return
    if isinstance(knoten, str):
        t = html_zu_klartext(knoten)
        if t:
            aus.append(t)
        return
    if isinstance(knoten, dict):
        for schluessel, wert in knoten.items():
            if not isinstance(schluessel, str):
                continue
            if schluessel in _STRUKTURSCHLUESSEL or schluessel.startswith("_"):
                continue
            _sammle(wert, aus, tiefe + 1)
        return
    if isinstance(knoten, (list, tuple)):
        for wert in knoten:
            _sammle(wert, aus, tiefe + 1)
        return
    # Zahlen, Wahrheitswerte, None: kein Text. Bewusst NICHT als Text
    # aufgenommen — eine '1' im Index waere ein Treffer ohne Aussage.


def json_klartext(roh: Optional[str]) -> str:
    """
    Klartext aus einer JSON-Spalte gewinnen.

    Kein gueltiges JSON? Dann wird der ROHWERT als Text behandelt und nicht
    verworfen. Begruendung: die Spalte koennte historisch Klartext enthalten
    haben, und ein Verwerfen waere eine stille Auslassung (Grundregel 1). Die
    Kosten des Gegenteils sind null — im schlimmsten Fall steht etwas JSON-
    Syntax im Index eines Hilfsmittels.
    """
    if roh is None:
        return ""
    text = str(roh).strip()
    if not text:
        return ""
    try:
        daten = json.loads(text)
    except (ValueError, TypeError):
        return html_zu_klartext(text)
    teile: List[str] = []
    _sammle(daten, teile)
    return " ".join(teile).strip()


def gekuerzt(text: str) -> bool:
    """True, wenn text die Satzgrenze ueberschreitet und gekuerzt WERDEN MUSS."""
    return len(text) > MAX_SATZ_LAENGE


def kuerze(text: str) -> str:
    """
    Auf MAX_SATZ_LAENGE kuerzen. Der Aufrufer prueft vorher mit gekuerzt() und
    ZAEHLT den Fall, damit die Kuerzung in der Auslieferung benannt werden kann.
    """
    return text if len(text) <= MAX_SATZ_LAENGE else text[:MAX_SATZ_LAENGE]
