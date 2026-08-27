# =============================================================================
# report_render/beleg_darstellung.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   DIE DARSTELLUNGSVARIANTEN EINER BEWEISMITTELGRUPPE AN EINER STELLE. Der
#   Berichtseditor laesst den Bearbeiter zwischen mehreren Darstellungen
#   waehlen und legt die Wahl in block_data.display_mode ab. Seit Build 725
#   sind es VIER; die vierte heisst 'Vollzitat'.
#
#   Aufgebaut wie report_render/quote_typen.py und aus demselben Grund: HTML,
#   PDF, DOCX und SQLite sollen sich nur noch darin unterscheiden, WIE sie
#   eine Variante malen - nicht darin, WELCHE sie erkennen.
#
# ── DER BEFUND, DER DIESER DATEI VORAUSGING ──────────────────────────────────
#
#   Die drei bisherigen Varianten hatten im ausgelieferten Bericht KEINE
#   WIRKUNG. Gemessen am Stand Build 724 (Commit 9e40c38):
#     userinfo/report_editor.js Z. 3678-3682  waehlt list | table | quote
#     report_render/html_renderer.py Z. 294-301   druckt "Beweis-IDs: 42, 43"
#     report_render/docx_renderer.py Z. 285-290  dasselbe
#     report_render/pdf_renderer.py  Z. 280-285  dasselbe
#     report_render/sqlite_renderer.py Z. 133-139 dasselbe
#     report_render/report_source.py Z. 265-268  liest display_mode nicht
#   'display_mode' kam im gesamten Ausgabepfad nicht vor. Der zweite
#   Renderer, der die drei Varianten kennt (editor/html_renderer.py
#   Z. 276-281), hat ausser den Tests keinen Aufrufer (Vorgang
#   3b9d5c11-84f7-4a26-b0e3-9d5a17c2f480, offen).
#
#   Das ist dieselbe Lage, die Vorgang 9c41a7e6 beim Zitatblock beschrieben
#   hat, und die Begruendung von damals gilt hier woertlich: eine
#   Bedienmoeglichkeit ohne Wirkung ist schlimmer als gar keine, weil sie eine
#   Zusage macht, die niemand einloest. Ab Build 725 lesen die Renderer die
#   Wahl - alle vier Varianten.
#
# ── DIE VORGABE BLEIBT 'list' ────────────────────────────────────────────────
#
#   Das Werkzeug setzt sie an drei Stellen hart (report_editor.js Z. 3335,
#   3844, 3900-3904). Ein Block ohne 'display_mode' - also jeder vor Build 161
#   angelegte - wird deshalb als Liste gezeigt, so wie auf dem Bildschirm.
#   'Vollzitat' wird NIE zur Vorgabe: es waere eine stille Aenderung des
#   Aussehens aller Bestandsberichte, und der Bearbeiter hat die Variante
#   nicht gewaehlt.
#
# ── ES WIRD NICHTS GESCHRIEBEN ───────────────────────────────────────────────
#
#   'display_mode' wird gelesen, nie geschrieben; ein fehlendes Feld bleibt
#   fehlend. Kein Migrationsschritt, kein Schreibzugriff, Migrationsvorbehalt
#   ab 01.07.2026 nicht beruehrt. Die Berichts-Siegel bleiben gueltig:
#   ReportSealer hasht die Zeilen aus report_blocks, nicht die gerenderte
#   Ausgabe (report_sealer.py, Kopf "UMFANG DES SIEGELS").
#
# Grundregeln: GR6, GR10.
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, Tuple

#: Die vier Werte, die das Werkzeug schreiben kann.
MODUS_LISTE = "list"
MODUS_TABELLE = "table"
MODUS_ZITAT = "quote"
MODUS_VOLLZITAT = "fullquote"

#: Alle gueltigen Werte - in der Reihenfolge, in der das Werkzeug sie
#: anbietet. Als Tupel, damit die Liste nicht versehentlich veraendert wird.
MODI: Tuple[str, ...] = (
    MODUS_LISTE, MODUS_TABELLE, MODUS_ZITAT, MODUS_VOLLZITAT,
)

#: Die Vorgabe des Werkzeugs - s. Kopf, "DIE VORGABE BLEIBT 'list'".
MODUS_VORGABE = MODUS_LISTE

#: Der Feldname, unter dem der normalisierte Wert im RenderedBlock landet.
#: Der Unterstrich folgt der Konvention der uebrigen abgeleiteten Felder
#: ('_resolved_caption', '_quote_typ'): was hier steht, ist NICHT aus der
#: Datenbank, sondern von report_source errechnet.
MODUS_FELD = "_beleg_modus"

#: Der Feldname, unter dem die fertige Vollzitat-Gruppe abgelegt wird.
#: Nur bei MODUS_VOLLZITAT gesetzt - die uebrigen Varianten brauchen den
#: Seitenabzug nicht, und ihn dennoch zu zerlegen waere die teuerste
#: Rechenarbeit des Berichtsaufbaus fuer nichts.
GRUPPE_FELD = "_vollzitat"

#: Klartextbezeichnung je Variante - fuer Ausgabeformate ohne Stile, fuer
#: Fehlermeldungen und fuer die Kopfzeile der Gruppe im Bericht.
_BEZEICHNUNGEN: Dict[str, str] = {
    MODUS_LISTE: "Liste",
    MODUS_TABELLE: "Tabelle",
    MODUS_ZITAT: "Zitat",
    MODUS_VOLLZITAT: "Vollzitat",
}

#: Die CSS-Klasse je Variante fuer den HTML-Bericht.
#:
#: SPRECHENDE NAMEN. Der Bericht ist ein Dokument, das Menschen ausserhalb
#: der Entwicklung lesen und im Zweifel im Quelltext nachsehen - eine Akte
#: geht an die Staatsanwaltschaft.
_CSS_KLASSEN: Dict[str, str] = {
    MODUS_LISTE: "beleg--liste",
    MODUS_TABELLE: "beleg--tabelle",
    MODUS_ZITAT: "beleg--zitat",
    MODUS_VOLLZITAT: "beleg--vollzitat",
}


def normalisiere(wert: Any) -> str:
    """
    Einen rohen 'display_mode' auf einen der vier gueltigen abbilden.

    Ein fehlender, leerer, falsch geschriebener oder nicht-textlicher Wert
    ergibt die Vorgabe - genau wie im Werkzeug, das im Konstruktor
    "data.display_mode || 'list'" schreibt (report_editor.js Z. 3335).

    KEINE WARNUNG BEI EINEM UNBEKANNTEN WERT, und das ist dieselbe bewusste
    Abweichung von der sonstigen Strenge wie in quote_typen.normalisiere():
    ein solcher Wert kann den Bearbeiter nicht erreichen - das Einstellmenue
    bietet nur die vier an -, er entstuende nur durch Handarbeit an der
    Datenbank. Eine Warnung wuerde etwas melden, das auf dem Bildschirm
    unsichtbar ist, und die Hinweisliste verwaessern, auf die es bei den
    Platzhaltern und den fehlenden Belegen ankommt.
    """
    if isinstance(wert, str) and wert in MODI:
        return wert
    return MODUS_VORGABE


def aus_daten(daten: Any) -> str:
    """
    Den Modus aus dem Datenteil eines 'evidence'-Blocks holen.

    Nimmt ausdruecklich ein beliebiges Objekt entgegen und nicht nur ein
    Woerterbuch: report_source legt bei unlesbarem JSON ein Ersatzobjekt an
    ({'_raw': ...}), und ein Renderer soll daran nicht scheitern.
    """
    if isinstance(daten, dict):
        return normalisiere(daten.get("display_mode"))
    return MODUS_VORGABE


def braucht_absatz(modus: Any) -> bool:
    """
    True, wenn diese Variante den umschliessenden Absatz benoetigt.

    Nur 'Vollzitat' tut das. Die Unterscheidung ist keine Feinoptimierung:
    fuer den Absatz muss der gesamte Seitenabzug zerlegt werden - eine
    Themenseite traegt bis zu 500 Beitraege. In den drei anderen Varianten
    waere das Rechenarbeit fuer ein Ergebnis, das niemand sieht.
    """
    return normalisiere(modus) == MODUS_VOLLZITAT


def bezeichnung(modus: Any) -> str:
    """Die deutsche Bezeichnung der Variante."""
    return _BEZEICHNUNGEN[normalisiere(modus)]


def css_klasse(modus: Any) -> str:
    """Die CSS-Klasse fuer den HTML-Bericht."""
    return _CSS_KLASSEN[normalisiere(modus)]
