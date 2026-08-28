# =============================================================================
# report_render/html_renderer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   Rendert ein ReportDocument in ein selbstenthaltendes HTML-Dokument (UTF-8).
#   Der Renderer sieht NUR das ReportDocument, NIE eine Datenbank (Bauplan §2).
#
#   Nicht verhandelbare Regeln (Bauplan Build 397 §3):
#     R1 — Berichtsstatus sichtbar im Kopf (Entwurf != freigegebene Akte).
#     R2 — Kein Platzhalter/kein Datenfehler verschwindet still: Abschnitt
#          "Hinweise zur Erzeugung" listet alle Warnungen.
#     R3 — Unbekannter Blocktyp wird sichtbar gemeldet, nicht uebersprungen.
#
#   Wichtige Escaping-Invariante:
#     Die vom ReportSource/PlaceholderResolver gelieferten Felder
#     (resolved_text, _resolved_items, _resolved_rows, _resolved_caption) sind
#     BEREITS HTML-sichere Fragmente (Editor.js-HTML + escapte Chip-Werte) und
#     werden UNVERAENDERT ausgegeben. Nur "Chrome" und Metadaten (Titel, Name,
#     Ankertexte, Warnungs-Details) werden hier via _esc() escaped.
#     Doppeltes Escaping wuerde die Ansicht vom Bildschirm des Ermittlers
#     abweichen lassen (Parität, §6).
#
# Version: v0.7.402 · Build: 402 · 2026-07-14 (Bild-Anker url_hash/asset_id/size ergaenzt)
# =============================================================================

from __future__ import annotations

from datetime import datetime

from report_render.report_document import ReportDocument, RenderedBlock
# Vorgang 9c41a7e6: die im Werkzeug gewaehlte Zitatvariante. Normalisiert
# wird sie in report_source; hier wird nur noch die Klasse dazu geholt.
from report_render.quote_typen import QUOTE_TYP_FELD, css_klasse
# Build 725 (Vollzitat): die Darstellungsvariante der Beweismittelgruppe.
# Normalisiert wird sie in report_source; hier wird nur noch gemalt.
from report_render import beleg_darstellung
from report_render.beleg_darstellung import (
    GRUPPE_FELD, MODUS_FELD, MODUS_VOLLZITAT,
)

CLASSIFICATION = "VERTRAULICH — IT-FORENSISCHES ERMITTLUNGSWERKZEUG NRW"

#: Anzeigenamen der Berichtstypen. Build 473 (Refactoring "Bericht" -> "Vermerk",
#: mc 2026-07-21): Labels umbenannt; DB-Schluessel unveraendert (migrationsneutral).
#: Beleg: Auftrag 2026-07-21.
REPORT_TYPE_LABELS = {
    "interim":  "Vermerk",
    "final":    "Abschlussbericht",
    "addendum": "Ergänzungsvermerk",
}

#: Menschenlesbare Beschreibung der Warn-Arten fuer den Hinweis-Abschnitt (R2).
WARNING_LABELS = {
    "unresolved_placeholder": "Nicht auflösbarer Platzhalter (Default eingesetzt)",
    "unknown_placeholder":    "Unbekannter Platzhalter (unveraendert belassen)",
    "unordered_block":        "Block ohne Sortierungseintrag (ans Ende gestellt)",
    "unknown_block_type":     "Unbekannter Blocktyp (Inhalt nicht regulaer dargestellt)",
    "missing_image":          "Bild-Verweis nicht auffindbar",
    # Build 725 (Vollzitat): die Beleglage selbst war unvollstaendig.
    "evidence_gap":           "Beleglage unvollstaendig (Beweismittelgruppe)",
}


def _esc(s) -> str:
    """HTML-Escaping fuer Chrome/Metadaten (& < > ")."""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


class HtmlRenderer:
    """ReportDocument -> bytes (UTF-8, selbstenthaltendes HTML)."""

    def render(self, doc: ReportDocument) -> bytes:
        """Erzeugt das vollstaendige HTML-Dokument als UTF-8-Bytes."""
        parts: list[str] = []
        parts.append(self._doc_head(doc))
        parts.append(self._status_banner(doc))
        parts.append(self._meta_header(doc))

        if doc.blocks:
            for blk in doc.blocks:
                parts.append(self._render_block(blk))
        else:
            parts.append('<p><em>Keine Bloecke im Bericht vorhanden.</em></p>')

        parts.append(self._hints_section(doc))     # R2
        parts.append(self._doc_foot())
        return "".join(parts).encode("utf-8")

    # ------------------------------------------------------------------
    def _fmt_ts(self, ts: int) -> str:
        """Formatiert einen Unix-Zeitstempel (deterministisch aus dem Wert)."""
        try:
            return datetime.fromtimestamp(int(ts)).strftime("%d.%m.%Y %H:%M")
        except (ValueError, OSError, OverflowError):
            return str(ts)

    def _doc_head(self, doc: ReportDocument) -> str:
        title = f"{REPORT_TYPE_LABELS.get(doc.report_type, doc.report_type)} — {doc.username} (ID: {doc.uid})"
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>{_esc(title)}</title>
  <style>
    body {{ font-family: "Times New Roman", Times, serif; font-size: 11pt;
           max-width: 800px; margin: 40px auto; color: #000; }}
    .status-banner {{ font-family: Arial, sans-serif; font-weight: bold;
           padding: 8pt 12pt; margin-bottom: 18pt; border: 2pt solid; }}
    .status-draft     {{ color: #7a0000; border-color: #7a0000; background: #fff3f3; }}
    .status-submitted {{ color: #7a5200; border-color: #7a5200; background: #fff9ec; }}
    .status-approved  {{ color: #14532d; border-color: #14532d; background: #f0fff4; }}
    .header {{ font-size: 9pt; color: #555; border-bottom: 1pt solid #ccc;
               padding-bottom: 6pt; margin-bottom: 24pt; font-family: Arial, sans-serif; }}
    .block {{ margin-bottom: 14pt; page-break-inside: avoid; }}
    .para-content {{ line-height: 1.6; word-break: break-word; }}
    h1,h2,h3,h4,h5,h6 {{ font-family: Arial, sans-serif; }}
    blockquote {{ margin: 8pt 0; padding: 2pt 12pt; color: #333; }}
    blockquote cite {{ display: block; font-size: 9pt; color: #666; margin-top: 4pt; }}
    /* Die drei Zitatvarianten des Werkzeugs (Vorgang 9c41a7e6).
       Sie bilden nach, was der Bearbeiter auf dem Bildschirm gewaehlt hat;
       die Zuordnung zu den Werten von 'type' steht in
       report_render/quote_typen.py. Bis Build 718 gab es hier nur EINE
       Regel - die des senkrechten Strichs -, und zwar unabhaengig davon,
       was gewaehlt war.
       NACHBILDUNG, NICHT KOPIE: die Stile des Buendels sind fuer den
       Bildschirm gemacht (Pixel, Bildschirmfarben, ein SVG-Symbol von
       '/icons/'). Hier gilt Druckmass (pt), und ein Verweis auf eine
       externe Datei verboete sich - dieses HTML muss selbstenthaltend
       bleiben. Das Anfuehrungszeichen ist deshalb ein Schriftzeichen und
       kein Bild. Die drei Varianten sind unterscheidbar; pixelgleich sind
       sie nicht, und das sollen sie auch nicht sein. */
    blockquote.zitat--anfuehrung {{ text-align: center; padding: 2pt 24pt;
           border: none; }}
    blockquote.zitat--anfuehrung::before {{ content: "\\201E"; display: block;
           font-size: 20pt; line-height: 1; color: #999; margin-bottom: 2pt; }}
    blockquote.zitat--linie {{ border-left: 3pt solid #ccc; text-align: left; }}
    blockquote.zitat--kasten {{ border: 1pt solid #d7d7d7; padding: 8pt 12pt;
           text-align: left; }}
    table.report-table {{ border-collapse: collapse; width: 100%; }}
    table.report-table td, table.report-table th {{ border: 1pt solid #999; padding: 3pt 6pt; }}
    .image-ref {{ border: 1pt dashed #999; background: #fafafa; padding: 8pt 12pt;
                  font-family: Arial, sans-serif; font-size: 9.5pt; }}
    .image-ref .lbl {{ font-weight: bold; }}
    .image-missing {{ color: #7a0000; }}
    .evidence-ref {{ border-left: 3pt solid #14532d; padding: 2pt 12pt; }}
    /* --- Vollzitat, die vierte Darstellung einer Beweismittelgruppe
       (Auftrag Chef-Ermittlerin 27.08.2026). Anforderung 6 verlangt, dass
       die Gruppe "gerahmt oder anderweitig als gruppiert deutlich
       erkennbar" ist - daher der durchgehende Rahmen um die Gruppe und ein
       zweiter, leichterer um jede Quelle.
       DRUCKMASS (pt), KEIN BILDSCHIRMMASS: dieselbe Ueberlegung wie bei den
       Zitatvarianten oben. 'page-break-inside: avoid' haelt einen Unterblock
       zusammen - ein Absatz auf Seite 4 und sein Befund auf Seite 5 waeren
       in einer Akte schwer zu lesen. */
    .vz-gruppe {{ border: 1.5pt solid #14532d; margin: 6pt 0 12pt;
                  page-break-inside: avoid; }}
    .vz-gruppe-kopf {{ font-family: Arial, sans-serif; font-size: 8.5pt;
                  font-weight: bold; color: #fff; background: #14532d;
                  padding: 3pt 8pt; }}
    .vz-gruppe-kopf .vz-zaehler {{ float: right; font-weight: normal; }}
    .vz-gruppe-label {{ font-family: Arial, sans-serif; font-size: 10pt;
                  font-weight: bold; padding: 6pt 10pt 0; }}
    .vz-quelle {{ border: 1pt solid #b9c7bd; margin: 6pt 10pt 0;
                  padding-bottom: 6pt; page-break-inside: avoid; }}
    .vz-quelle-kopf {{ font-family: Arial, sans-serif; font-size: 9.5pt;
                  background: #eef3ef; border-bottom: 1pt solid #dbe4dd;
                  padding: 4pt 8pt; }}
    .vz-art {{ font-weight: bold; }}
    .vz-meta {{ font-family: Arial, sans-serif; font-size: 8.5pt; color: #444;
                  padding: 3pt 8pt 0; }}
    .vz-meta .vz-k {{ color: #777; }}
    .vz-link {{ font-family: "Courier New", monospace; font-size: 8pt;
                  word-break: break-all; color: #14532d; }}
    .vz-absatz {{ margin: 6pt 8pt 0; padding: 5pt 8pt; border-left: 3pt solid #ccc;
                  line-height: 1.6; }}
    .vz-absatz.vz-ersatz {{ border-left-style: dotted; }}
    /* Build 727: eine von mehreren moeglichen Fundstellen. Gestrichelt und
       mit Vorspann - der Leser muss sehen, dass die Zuordnung offen ist. */
    .vz-absatz.vz-moeglich {{ border-left-style: dashed; }}
    .vz-moeglich-kopf {{ font-family: Arial, sans-serif; font-size: 8pt;
                  font-weight: bold; color: #7a5200; margin-bottom: 3pt; }}
    .vz-quelle--fehlt {{ border-style: dashed; }}
    /* box-decoration-break: die Hinterlegung soll auch dann sauber aussehen,
       wenn die Markierung ueber einen Zeilenumbruch laeuft. */
    .vz-mark {{ padding: 0 1pt; box-decoration-break: clone;
                  -webkit-box-decoration-break: clone; }}
    .vz-nr {{ display: inline-block; min-width: 12pt; text-align: center;
                  font-family: Arial, sans-serif; font-size: 7.5pt;
                  font-weight: bold; border: 1pt solid #666; margin-right: 3pt; }}
    .vz-befund {{ margin: 6pt 8pt 0; padding-left: 6pt;
                  border-left: 2.5pt solid #ccc; font-size: 10pt; }}
    .vz-befund-kopf {{ font-family: Arial, sans-serif; font-size: 8.5pt;
                  color: #333; }}
    .vz-kat {{ font-weight: bold; }}
    .vz-notiz .vz-k {{ font-family: Arial, sans-serif; font-size: 8.5pt;
                  color: #777; }}
    .vz-unsicher {{ font-family: Arial, sans-serif; font-size: 8pt;
                  color: #7a5200; }}
    .vz-fehlt {{ font-family: Arial, sans-serif; font-size: 8.5pt;
                  color: #7a0000; font-weight: bold; padding: 4pt 8pt; }}
    .unknown-block {{ color: #7a0000; font-family: Arial, sans-serif; font-weight: bold;
                      border: 1pt solid #7a0000; padding: 4pt 8pt; }}
    .anchors {{ font-size: 8.5pt; color: #555; margin-top: 4pt; }}
    .hints {{ font-family: Arial, sans-serif; font-size: 8.5pt; color: #444;
              border-top: 1pt solid #ccc; margin-top: 36pt; padding-top: 8pt; }}
    .hints h3 {{ font-size: 10pt; margin-bottom: 6pt; }}
    .hints .warn {{ color: #7a0000; }}
    .footer {{ font-size: 8pt; color: #888; border-top: 1pt solid #ddd;
               padding-top: 4pt; margin-top: 24pt; text-align: center;
               font-family: Arial, sans-serif; font-weight: bold; }}
  </style>
</head>
<body>
"""

    def _status_banner(self, doc: ReportDocument) -> str:
        """R1 — Berichtsstatus sichtbar im Kopf."""
        st = doc.status
        if st == "draft":
            return ('<div class="status-banner status-draft">'
                    'ENTWURF — nicht freigegeben. Nicht zur Vorlage bestimmt.</div>')
        if st == "submitted":
            return ('<div class="status-banner status-submitted">'
                    'ZUR ABNAHME VORGELEGT — noch nicht freigegeben.</div>')
        if st in ("approved", "final"):
            label = "FREIGEGEBEN" if st == "approved" else "ABGESCHLOSSEN / AN STA VERSANDT"
            return (f'<div class="status-banner status-approved">'
                    f'{label} — Stand: {_esc(self._fmt_ts(doc.generated_at))}.</div>')
        # Unbekannter Status: nicht still — als Entwurf-aehnliche Warnung behandeln.
        return (f'<div class="status-banner status-draft">'
                f'UNBEKANNTER STATUS: {_esc(st)} — Behandlung wie Entwurf.</div>')

    def _meta_header(self, doc: ReportDocument) -> str:
        type_label = REPORT_TYPE_LABELS.get(doc.report_type, doc.report_type)
        return (
            '<div class="header">'
            f'Beschuldigter: {_esc(doc.username)} &middot; ID: {doc.uid}<br>'
            f'{_esc(type_label)} Nr. {doc.sequence_nr} &middot; Titel: {_esc(doc.title)}<br>'
            f'Erstellt am: {_esc(self._fmt_ts(doc.generated_at))} &middot; '
            f'{len(doc.blocks)} Bl&ouml;cke &middot; {doc.anchor_count} Beweisanker'
            '</div>'
        )

    # ------------------------------------------------------------------
    def _render_block(self, blk: RenderedBlock) -> str:
        """Dispatch auf den passenden Blockrenderer. Unbekannter Typ -> R3."""
        if not blk.is_known_type:
            return self._render_unknown(blk)
        fn = {
            "paragraph": self._render_paragraph,
            "header":    self._render_header,
            "list":      self._render_list,
            "table":     self._render_table,
            "quote":     self._render_quote,
            "image":     self._render_image,
            "delimiter": self._render_delimiter,
            "marker":    self._render_marker,
            "evidence":  self._render_evidence,
        }.get(blk.block_type, self._render_unknown)
        return f'<div class="block">{fn(blk)}{self._anchors(blk)}</div>'

    # -- einzelne Blockrenderer (resolved_* = bereits HTML-sicher!) --

    def _render_paragraph(self, blk: RenderedBlock) -> str:
        return f'<p class="para-content">{blk.resolved_text}</p>'

    def _render_header(self, blk: RenderedBlock) -> str:
        try:
            level = int(blk.data.get("level", 2))
        except (ValueError, TypeError):
            level = 2
        level = min(max(level, 1), 6)
        return f'<h{level}>{blk.resolved_text}</h{level}>'

    def _render_list(self, blk: RenderedBlock) -> str:
        items = blk.data.get("_resolved_items", [])
        tag = "ol" if blk.data.get("style") == "ordered" else "ul"
        lis = "".join(f"<li>{it}</li>" for it in items)
        return f'<{tag}>{lis}</{tag}>'

    def _render_table(self, blk: RenderedBlock) -> str:
        rows = blk.data.get("_resolved_rows", [])
        with_headings = bool(blk.data.get("withHeadings"))
        out = ['<table class="report-table">']
        for i, row in enumerate(rows):
            cell_tag = "th" if (with_headings and i == 0) else "td"
            cells = "".join(f"<{cell_tag}>{c}</{cell_tag}>" for c in row)
            out.append(f"<tr>{cells}</tr>")
        out.append("</table>")
        return "".join(out)

    def _render_quote(self, blk: RenderedBlock) -> str:
        """
        Zitat mit Quellenangabe UND der gewaehlten Variante (Vorgang
        9c41a7e6).

        css_klasse() bekommt den bereits normalisierten Wert aus
        report_source und normalisiert ihn sicherheitshalber noch einmal -
        der Renderer soll auch dann eine gueltige Klasse liefern, wenn ihm
        jemand ein von Hand gebautes ReportDocument vorsetzt (die Tests tun
        genau das). Ein 'KeyError' mitten im Bericht waere die schlechteste
        aller Antworten.
        """
        caption = blk.data.get("_resolved_caption", "")
        cite = f"<cite>{caption}</cite>" if caption else ""
        klasse = css_klasse(blk.data.get(QUOTE_TYP_FELD))
        return (f'<blockquote class="{klasse}">'
                f'{blk.resolved_text}{cite}</blockquote>')

    def _render_image(self, blk: RenderedBlock) -> str:
        """§4.2: forensisch harter VERWEIS, KEINE Bild-Bytes."""
        url = blk.data.get("_image_url", "")
        caption = blk.data.get("_resolved_caption", "")
        available = blk.data.get("_image_available", False)
        avail_txt = ("in assets_&lt;uid&gt;.db vorhanden" if available
                     else '<span class="image-missing">NICHT in assets_&lt;uid&gt;.db auffindbar</span>')
        cap = f'<br><span class="lbl">Bildunterschrift:</span> {caption}' if caption else ""
        # BLOB-freier Wiederauffind-Anker (Build 402), nur wenn vorhanden.
        anchor = ""
        if available:
            uh = blk.data.get("_image_url_hash")
            aid = blk.data.get("_image_asset_id")
            size = blk.data.get("_image_size")
            bits = []
            if uh:
                bits.append(f"url_hash={_esc(uh)}")
            if aid is not None:
                bits.append(f"asset_id={_esc(aid)}")
            if size is not None:
                bits.append(f"file_size={_esc(size)} B")
            if bits:
                anchor = f'<br><span class="lbl">Anker:</span> {" &middot; ".join(bits)}'
        return (
            '<div class="image-ref">'
            '<span class="lbl">Bildverweis (nicht eingebettet — §§184b/184c):</span><br>'
            f'Quelle: {_esc(url) or "(keine URL)"}<br>'
            f'Status: {avail_txt}'
            f'{anchor}'
            f'{cap}'
            '</div>'
        )

    def _render_delimiter(self, blk: RenderedBlock) -> str:
        return "<hr>"

    def _render_marker(self, blk: RenderedBlock) -> str:
        # 'marker' als Blocktyp: wie ein hervorgehobener Absatz behandeln.
        return f'<p class="para-content"><mark>{blk.resolved_text}</mark></p>'

    def _render_evidence(self, blk: RenderedBlock) -> str:
        """
        Eine Beweismittelgruppe.

        BUILD 725: die im Werkzeug gewaehlte Darstellung wird gelesen. Fuer
        'Vollzitat' wird die fertige Gruppe gezeichnet, die report_source
        aufgebaut hat; fuer die drei uebrigen Varianten bleibt es bei der
        bisherigen Ausgabe (Beleg-IDs). Dass jene drei im Bericht weiterhin
        gleich aussehen, ist BENANNT und nicht vergessen - s. Kopf von
        report_render/beleg_darstellung.py und der Vorgang dazu im
        Aufgabenverzeichnis.
        """
        if blk.data.get(MODUS_FELD) == MODUS_VOLLZITAT:
            gruppe = blk.data.get(GRUPPE_FELD)
            if gruppe is not None:
                return self._render_vollzitat(gruppe)

        ev_ids = blk.data.get("evidence_ids", [])
        ids_txt = ""
        if isinstance(ev_ids, list) and ev_ids:
            ids_txt = "Beweis-IDs: " + ", ".join(_esc(str(e)) for e in ev_ids)
        body = blk.resolved_text or ""
        inner = body + (f'<div class="anchors">{ids_txt}</div>' if ids_txt else "")
        return f'<div class="evidence-ref">{inner}</div>'

    # ------------------------------------------------------------------
    def _render_vollzitat(self, gruppe) -> str:
        """
        Die vierte Darstellungsvariante zeichnen.

        ESCAPING: Die Absatz-Fragmente (absatz.html) kommen aus dem zerlegten
        Seitenabzug und sind von lxml neu serialisiert - sie sind BEREITS
        HTML-sicher und werden UNVERAENDERT ausgegeben. Das ist dieselbe
        Invariante wie bei resolved_text (s. Dateikopf). Alles uebrige -
        Betreff, Partner, Notiz, Ermittlername, Adresse - ist Klartext aus der
        Datenbank und geht durch _esc(). Ein Themenbetreff kann '<' enthalten;
        ein Forum ist voll davon.
        """
        from core import kategorie_farben

        teile = [
            '<div class="vz-gruppe">',
            '<div class="vz-gruppe-kopf">&#9878;&#65039; BEWEISMITTELGRUPPE '
            '&mdash; VOLLZITAT'
            f'<span class="vz-zaehler">{gruppe.beleg_anzahl} '
            f'{"Beleg" if gruppe.beleg_anzahl == 1 else "Belege"} &middot; '
            f'{gruppe.quellen_anzahl} '
            f'{"Quelle" if gruppe.quellen_anzahl == 1 else "Quellen"}</span>'
            '</div>',
        ]
        if gruppe.beschriftung:
            teile.append('<div class="vz-gruppe-label">Belegsammlung: '
                         f'&bdquo;{_esc(gruppe.beschriftung)}&ldquo;</div>')

        for ub in gruppe.unterbloecke:
            teile.append(self._render_vz_quelle(ub, kategorie_farben))

        teile.append('</div>')
        return "".join(teile)

    # ------------------------------------------------------------------
    def _render_vz_quelle(self, ub, kategorie_farben) -> str:
        q = ub.quelle
        # Build 727: ein Beleg, den es nicht (mehr) gibt, bekommt eine EIGENE
        # Darstellung - keine Quellenzeile, kein Datum, keine Fundstelle. Bis
        # Build 726 stand dort "Beitrag zum Thema »(Betreff nicht
        # ermittelbar)«", also eine erfundene Quellenart.
        if q.ist_unbekannt:
            return self._render_vz_fehlbeleg(ub)

        teile = ['<div class="vz-quelle">']

        # -- Kopf: Art der Quelle (Anforderung 7) --------------------------
        if q.ist_pn:
            art, wer = "Private Nachricht mit", q.partner
            fehlt = "(Gespr&auml;chspartner nicht ermittelbar)"
        else:
            art, wer = "Beitrag zum Thema", q.betreff
            fehlt = "(Betreff nicht ermittelbar)"
        bezeichner = (f'&raquo;{_esc(wer)}&laquo;' if wer else fehlt)
        teile.append(f'<div class="vz-quelle-kopf">'
                     f'<span class="vz-art">{art}</span> {bezeichner}</div>')

        # -- Metazeile: Originaldatum (Anf. 4), Link (Anf. 5) --------------
        meta = []
        datum = self._fmt_inhaltszeit(q.posted_ts)
        wort = "Datum der Nachricht" if q.ist_pn else "Datum des Beitrags"
        meta.append(f'<span class="vz-k">{wort}:</span> {_esc(datum)}')
        if q.ist_pn and q.betreff:
            meta.append(f'<span class="vz-k">Betreff:</span> '
                        f'&bdquo;{_esc(q.betreff)}&ldquo;')
        if q.verfasser:
            meta.append(f'<span class="vz-k">Verfasser:</span> '
                        f'{_esc(q.verfasser)}')
        if q.post_id is not None:
            kennwort = "Nachricht" if q.ist_pn else "Beitrag"
            # Build 727: stammt die Nummer nicht aus der Annotation, sondern
            # ist sie aus dem Seitenabzug abgeleitet, steht das dabei. Der
            # Leser der Akte soll sehen, worauf Betreff, Datum und
            # Zusammenfassung beruhen.
            herkunft = ("" if q.post_quelle != "seitenabzug"
                        else ' <span class="vz-k">(aus dem Seitenabzug '
                             'bestimmt)</span>')
            meta.append(f'<span class="vz-k">{kennwort}:</span> '
                        f'#{q.post_id}{herkunft}')
        zeile = " &middot; ".join(meta)
        link = q.link
        teile.append(
            f'<div class="vz-meta">{zeile}<br>'
            f'<span class="vz-k">Fundstelle:</span> '
            f'<span class="vz-link">{_esc(link) or "(keine Adresse)"}</span>'
            f'</div>')

        # -- Die Absaetze (Anforderung 2 und 3) ----------------------------
        for absatz in ub.absaetze:
            klasse = "vz-absatz"
            if absatz.ersatz:
                klasse += " vz-ersatz"
            if absatz.moeglich:
                klasse += " vz-moeglich"
            vorspann = ""
            if absatz.von_gesamt:
                lauf, gesamt = absatz.von_gesamt
                vorspann = (
                    f'<div class="vz-moeglich-kopf">M&ouml;gliche Fundstelle '
                    f'{lauf} von {gesamt}</div>')
            teile.append(f'<div class="{klasse}">{vorspann}{absatz.html}</div>')

        # -- Die Befunde (Anforderungen 1 und 8) ---------------------------
        for bf in ub.befunde:
            teile.append(self._render_vz_befund(bf, kategorie_farben))

        teile.append('</div>')
        return "".join(teile)

    # ------------------------------------------------------------------
    def _render_vz_fehlbeleg(self, ub) -> str:
        """
        Ein Beleg, zu dem es keine Annotation (mehr) gibt.

        Er wird GEZEIGT (GR1: kein Beleg verschwindet still), aber ohne jede
        Quellenangabe - denn es gibt keine. Die Begruendung steht im Kasten
        selbst und nicht nur im Hinweisabschnitt: wer die Gruppe liest, soll
        an Ort und Stelle sehen, dass hier nichts steht, statt einen leeren
        Beitrag zu vermuten.
        """
        nummern = ", ".join("#%d" % b.annotation_id for b in ub.befunde)
        return (
            '<div class="vz-quelle vz-quelle--fehlt">'
            '<div class="vz-quelle-kopf">Beleg nicht mehr vorhanden</div>'
            f'<div class="vz-fehlt">&#9888; Zu {_esc(nummern)} gibt es in '
            'der Beweismitteldatenbank keine aktive Annotation. Sie wurde '
            'gel&ouml;scht oder stammt aus einer anderen '
            'Beweismitteldatenbank. Quelle, Datum und Wortlaut sind damit '
            'nicht bestimmbar &mdash; der Beleg wird hier ausgewiesen und '
            'nicht &uuml;bersprungen.</div>'
            '</div>')

    # ------------------------------------------------------------------
    def _render_vz_befund(self, bf, kategorie_farben) -> str:
        # Der farbige Balken links am Befund traegt die VOLLE Kategoriefarbe,
        # die Markierung im Absatz die aufgehellte. Beide gehoeren zusammen
        # und sollen es auch aussehen; der Balken ist schmal genug, dass die
        # Vollfarbe dort nicht stoert (Begruendung: Kopf von
        # core/kategorie_farben.py).
        rand = kategorie_farben.farbe(bf.kategorie)
        kopf = [
            f'<span class="vz-nr">{bf.nummer}</span>',
            f'<span class="vz-kat">{_esc(bf.kategorie_text)}</span>',
            f'Beleg&nbsp;#{bf.annotation_id}',
        ]
        if bf.ermittler:
            kopf.append(f'Ermittler: <strong>{_esc(bf.ermittler)}</strong>')
        else:
            kopf.append('Ermittler: <em>nicht vermerkt</em>')

        teile = [f'<div class="vz-befund" style="border-left-color: {rand};">',
                 f'<div class="vz-befund-kopf">'
                 f'{" &middot; ".join(kopf)}</div>']

        if bf.notiz:
            teile.append(f'<div class="vz-notiz"><span class="vz-k">Notiz:'
                         f'</span> {_esc(bf.notiz)}</div>')

        # Jeder Beleg sagt, wie sicher seine Angaben sind. Ein Absatz ueber
        # den Wortlaut gefunden und ein aus dem Anzeigenamen zerlegter
        # Nachname sind schwaecher als der jeweilige Sollweg - der Leser der
        # Akte muss das sehen, ohne den Quelltext zu kennen.
        vorbehalte = []
        if bf.absatz_weg == "fehlt":
            # Build 727: kein Vorbehalt zum Absatz - es gibt gar keinen Beleg.
            # (Erreichbar nur, wenn ein Fehlbeleg je in einem Unterblock mit
            #  Quelle landete; der Fehlbeleg-Kasten geht diesen Weg nicht.)
            vorbehalte = []
        elif bf.absatz_weg == "text":
            vorbehalte.append(
                "Absatz &uuml;ber den Wortlaut gefunden, nicht &uuml;ber den "
                "Anker der Markierung")
        elif bf.absatz_weg == "uebersetzung":
            vorbehalte.append(
                "Markierung in der maschinellen &Uuml;bersetzung; der Absatz "
                "des Originals ist nicht ihre Umgebung")
        elif bf.absatz_weg == "keiner":
            vorbehalte.append("umschlie&szlig;ender Absatz nicht auffindbar")
        if bf.name_quelle == "display_name":
            vorbehalte.append(
                "Nachname aus dem Anzeigenamen abgeleitet")
        elif bf.name_quelle == "kuerzel" and bf.ermittler:
            vorbehalte.append("nur das Benutzerk&uuml;rzel bekannt")
        if vorbehalte:
            teile.append('<div class="vz-unsicher">&#9888; '
                         + "; ".join(vorbehalte) + '.</div>')
        if bf.hinweis and bf.absatz_weg == "keiner":
            teile.append(f'<div class="vz-fehlt">{_esc(bf.hinweis)}</div>')

        teile.append('</div>')
        return "".join(teile)

    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_inhaltszeit(ts) -> str:
        """
        Die Inhaltszeit als deutsches Datum.

        NICHT _fmt_ts(): jene Methode formatiert den Erzeugungszeitpunkt des
        Berichts. Hier geht es um das Datum DES BEITRAGS - der Unterschied ist
        die ganze Anforderung 4, und ein gemeinsamer Formatierer haette die
        beiden Bedeutungen im Quelltext ununterscheidbar gemacht.
        Fehlt die Zeit, wird das GESAGT und kein Platzhalterdatum gedruckt.

        DIE ZEITZONE WIRD MITGEDRUCKT, und zwar nur hier. In fdb.uid_posts
        steht ein Unix-Zeitstempel, also ein Zeitpunkt in UTC; angezeigt wird
        er in der Zeitzone der auswertenden Maschine. Eine Tatzeitangabe in
        einer Akte ohne Zone ist um eine oder zwei Stunden unbestimmt - bei
        einem Alibi ist das der ganze Unterschied. '%Z' nennt die tatsaechlich
        angewandte Zone; laeuft die VM auf UTC, steht dort UTC, und auch das
        ist eine Aussage.

        Der uebrige Bericht (Erzeugungszeitpunkt, _fmt_ts oben) druckt
        weiterhin ohne Zone. Das ist NICHT vergessen: es ist getesteter
        Ausgabetext an mehreren Stellen und in drei Renderern, und es geht
        dort um einen Verwaltungszeitpunkt, nicht um eine Tatzeit. Als
        eigener Vorgang aufgenommen.
        """
        if not ts:
            return "nicht ermittelbar"
        try:
            zeit = datetime.fromtimestamp(int(ts)).astimezone()
            return zeit.strftime("%d.%m.%Y, %H:%M Uhr (%Z)")
        except (ValueError, OSError, OverflowError):
            return "nicht ermittelbar"

    def _render_unknown(self, blk: RenderedBlock) -> str:
        """R3 — unbekannter Blocktyp sichtbar gemeldet, nicht uebersprungen."""
        return (f'<div class="block"><div class="unknown-block">'
                f'&#9888; Unbekannter Blocktyp \'{_esc(blk.block_type)}\' — '
                f'Inhalt nicht regulaer dargestellt (siehe Hinweise).'
                f'</div>{self._anchors(blk)}</div>')

    def _anchors(self, blk: RenderedBlock) -> str:
        """Beweisanker als Fussnotenliste (Ankertext ist Klartext -> escapen)."""
        if not blk.anchors:
            return ""
        lis = []
        for a in blk.anchors:
            aid = getattr(a, "id", "")
            atext = getattr(a, "anchor_text", "")
            lis.append(f"<li>[{_esc(str(aid))}] {_esc(atext)}</li>")
        return f'<ol class="anchors">{"".join(lis)}</ol>'

    # ------------------------------------------------------------------
    def _hints_section(self, doc: ReportDocument) -> str:
        """R2 — "Hinweise zur Erzeugung": Zeitpunkt, Status, Zahlen, Warnliste."""
        out = ['<div class="hints">']
        out.append("<h3>Hinweise zur Erzeugung</h3>")
        out.append(
            f'<div>Erzeugt: {_esc(self._fmt_ts(doc.generated_at))} &middot; '
            f'Berichtsstatus: {_esc(doc.status)} &middot; '
            f'Bl&ouml;cke: {len(doc.blocks)} &middot; '
            f'Beweisanker: {doc.anchor_count}</div>'
        )
        if doc.warnings:
            out.append(f'<div class="warn">Warnungen ({len(doc.warnings)}):</div><ul class="warn">')
            for w in doc.warnings:
                label = WARNING_LABELS.get(w.kind, w.kind)
                loc = f" (Block {_esc(w.block_id)})" if w.block_id else ""
                out.append(f"<li>{_esc(label)}: {_esc(w.detail)}{loc}</li>")
            out.append("</ul>")
        else:
            out.append("<div>Keine Warnungen — alle Platzhalter aufgeloest, "
                       "alle Bl&ouml;cke sortiert und bekannt.</div>")
        out.append("</div>")
        return "".join(out)

    def _doc_foot(self) -> str:
        return (f'<div class="footer">{_esc(CLASSIFICATION)}</div>\n</body>\n</html>')
