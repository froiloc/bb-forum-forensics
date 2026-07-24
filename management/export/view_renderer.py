# =============================================================================
# management/export/view_renderer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck (Idee 5 — Druck-/Akten-Export je Sicht, Build 511):
#   Rendert die JSON-Antwort einer Cockpit-Sicht als SELF-CONTAINED, DRUCKBARE
#   HTML-Seite OHNE JavaScript, umschlossen vom AP-2B-ExportEnvelope
#   (Aktenkopf + Klassifikation + Erzeugungsvermerk + SHA-256 des Nutzinhalts).
#
#   REINE KLASSE (Muster audit_export.py / support_overview/html_export.py):
#   keine DB, keine Uhr, kein Netz — Daten und Rahmen kommen vom Aufrufer.
#   Damit vollstaendig deterministisch und automatisiert pruefbar.
#
# DIE VIER REGELN — jede gegen einen konkreten, benannten Fehler:
#
#   (1) SPALTEN KOMMEN AUS DEN DATEN, nicht aus einer gepflegten Liste.
#       Vereinigung aller Schluessel ueber ALLE Zeilen, Reihenfolge des ersten
#       Auftretens. Grund: eine handgepflegte Spaltenliste haette bei jedem
#       Tippfehler und bei jeder spaeteren Feldergaenzung eine Spalte STILL
#       verschluckt — ein ausgelassener Beleg (Grundregel 1). 'order' zieht
#       bekannte Felder nur nach vorn, 'labels' beschriftet sie nur; BEIDE
#       FILTERN NIE. Ein Feld, das erst in Zeile 500 auftaucht, bekommt seine
#       Spalte (und die Zeilen davor ein '—').
#
#   (2) NICHT BESCHRIEBENE TOP-LEVEL-SCHLUESSEL werden trotzdem gerendert
#       (Abschnitt „Weitere Daten"). Was der Endpunkt liefert, steht im Export.
#
#   (3) EIN FEHLENDER ABSCHNITT WIRD BENANNT ("im Datensatz nicht enthalten"),
#       nicht weggelassen. Sonst saehe ein unvollstaendiger Export vollstaendig
#       aus — der gefaehrlichste aller Faelle.
#
#   (4) KAPPUNG IST SICHTBAR. Ueber MAX_ROWS hinaus wird abgeschnitten, aber
#       mit einem hervorgehobenen Vermerk IM Dokument, der die Gesamtzahl
#       nennt. Ein stilles Abschneiden waere ein stiller Beweisverlust.
#
# SICHERHEIT (XSS): ALLE variablen Werte werden mit html.escape() entschaerft —
#   die Daten stammen aus einem multilingualen Forum und aus Ermittler-Freitext.
#   UTF-8 bleibt erhalten (escape kodiert nur < > & " ').
#
# DRUCK: eingebettetes @media print (Farben/Bandbreiten reduziert, Tabellen
#   brechen zeilenweise um) — die Seite soll ohne Nacharbeit in die Akte.
#
# Version: v0.8.511 · Build: 511 · 2026-07-24
# =============================================================================

from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from management.export.checksum import json_payload_sha256
from management.export.view_export_spec import SectionSpec, ViewExportSpec

_EM_DASH = "—"

_STYLE = (
    "  body { font-family: system-ui, sans-serif; color: #1c1e21; margin: 24px; }\n"
    "  .aiw-klass { font-weight: 700; color: #922b21; letter-spacing: .04em; }\n"
    "  .aiw-export-head h1 { margin: 6px 0; font-size: 20px; }\n"
    "  .aiw-akte { color: #606770; font-size: 13px; }\n"
    "  h2 { font-size: 15px; margin: 18px 0 4px; border-bottom: 1px solid #ccc;\n"
    "       padding-bottom: 3px; }\n"
    "  table { border-collapse: collapse; width: 100%; margin-top: 6px;\n"
    "          font-size: 12px; }\n"
    "  th, td { border: 1px solid #ddd; padding: 4px 6px; text-align: left;\n"
    "           vertical-align: top; word-break: break-word; }\n"
    "  th { background: #f0f2f4; }\n"
    "  .aiw-note { color: #606770; font-size: 12px; margin: 6px 0; }\n"
    "  .aiw-missing { color: #922b21; font-size: 12px; margin: 6px 0;\n"
    "                 font-style: italic; }\n"
    "  .aiw-truncated { color: #922b21; font-weight: 700; font-size: 12px;\n"
    "                   margin: 6px 0; border: 1px solid #922b21;\n"
    "                   padding: 4px 6px; }\n"
    "  .aiw-export-foot { margin-top: 18px; border-top: 2px solid #333;\n"
    "                     padding-top: 8px; font-size: 12px; color: #333; }\n"
    "  .aiw-erzeugungsvermerk { list-style: none; padding-left: 0; }\n"
    "  @media print {\n"
    "    body { margin: 8mm; }\n"
    "    th { background: #eee !important; -webkit-print-color-adjust: exact; }\n"
    "    tr { page-break-inside: avoid; }\n"
    "    h2 { page-break-after: avoid; }\n"
    "    .aiw-export-foot { page-break-inside: avoid; }\n"
    "  }\n"
)


class ViewExportRenderer:
    """Rendert eine Sicht-JSON-Antwort als gerichtsfeste, druckbare HTML-Seite."""

    #: Sichtbare Kappungsgrenze je Abschnitt (Regel 4). Bewusst grosszuegig:
    #  sie schuetzt vor einer unbedienbaren Datei, nicht vor Vollstaendigkeit.
    MAX_ROWS = 5000

    def __init__(self, spec: ViewExportSpec, *,
                 max_rows: Optional[int] = None) -> None:
        self._spec = spec
        self._max_rows = int(max_rows) if max_rows else self.MAX_ROWS

    # ------------------------------------------------------------ oeffentlich
    def render(self, data: Dict[str, Any], envelope,
               *, query_summary: str = "") -> str:
        """
        data     — die JSON-Antwort des Sicht-Endpunkts (dict).
        envelope — ExportEnvelope (Aktenkopf/Fuss/Pruefsumme).
        query_summary — Klartext der angewandten Parameter (erscheint im Kopf;
                        ohne ihn waere unklar, welcher Ausschnitt vorliegt).
        """
        data = data if isinstance(data, dict) else {}
        body: List[str] = []

        if self._spec.note:
            body.append('<p class="aiw-note">%s</p>\n'
                        % html.escape(self._spec.note))
        if query_summary:
            body.append('<p class="aiw-note">Angewandte Parameter: %s</p>\n'
                        % html.escape(query_summary))

        gesehen = set()
        if self._spec.sections:
            for sec in self._spec.sections:
                gesehen.add(sec.key)
                body.append(self._section_html(
                    sec.title, data.get(sec.key, _MISSING), sec))
        # Regel 2 + Auto-Modus: alles, was keine Spec beschreibt, kommt trotzdem
        # ins Dokument. Ohne deklarierte Abschnitte ist das der Normalfall.
        rest = [k for k in data.keys() if k not in gesehen]
        if rest:
            if self._spec.sections:
                body.append("<h2>Weitere Daten</h2>\n")
            for key in rest:
                body.append(self._section_html(
                    self._auto_title(key), data.get(key), None))

        body_html = "".join(body)
        # Pruefsumme ueber die NUTZDATEN (nicht ueber das gerenderte HTML) —
        # der Empfaenger kann sie aus derselben Endpunkt-Antwort nachrechnen.
        digest = json_payload_sha256(data)

        return (
            '<!DOCTYPE html>\n<html lang="de">\n<head>\n'
            '<meta charset="utf-8">\n'
            "<title>%s</title>\n<style>\n%s</style>\n</head>\n<body>\n"
            % (html.escape(self._spec.label), _STYLE)
            + envelope.header_html(self._spec.label)
            + body_html
            + envelope.footer_html(digest)
            + "</body>\n</html>\n"
        )

    # ------------------------------------------------------------------ intern
    @staticmethod
    def _auto_title(key: str) -> str:
        """Ueberschrift fuer einen nicht beschriebenen Schluessel."""
        return str(key).replace("_", " ")

    def _section_html(self, title: str, value: Any,
                      sec: Optional[SectionSpec]) -> str:
        """Ein Abschnitt. Der Wert bestimmt die Darstellungsform."""
        out = ["<h2>%s</h2>\n" % html.escape(str(title))]

        # Regel 3: fehlender Abschnitt wird BENANNT.
        if value is _MISSING:
            out.append('<p class="aiw-missing">Dieser Abschnitt ist in der '
                       'Antwort des Endpunkts nicht enthalten.</p>\n')
            return "".join(out)

        if isinstance(value, list):
            if not value:
                out.append('<p class="aiw-note">Keine Einträge '
                           '(echter Leerbefund).</p>\n')
                return "".join(out)
            if all(isinstance(r, dict) for r in value):
                out.append(self._rows_table(value, sec))
            else:
                out.append(self._scalar_list(value))
            return "".join(out)

        if isinstance(value, dict):
            if not value:
                out.append('<p class="aiw-note">Keine Angaben '
                           '(echter Leerbefund).</p>\n')
                return "".join(out)
            out.append(self._kv_table(value, sec))
            return "".join(out)

        out.append("<p>%s</p>\n" % html.escape(self._cell(value)))
        return "".join(out)

    def _rows_table(self, rows: Sequence[dict],
                    sec: Optional[SectionSpec]) -> str:
        cols = self._columns(rows, sec)
        labels = (sec.labels if sec else {}) or {}

        shown, truncated = list(rows), 0
        if len(shown) > self._max_rows:
            truncated = len(shown) - self._max_rows
            shown = shown[:self._max_rows]

        head = "".join("<th>%s</th>" % html.escape(str(labels.get(c, c)))
                       for c in cols)
        body = []
        for r in shown:
            cells = "".join(
                "<td>%s</td>" % html.escape(self._cell(r.get(c, None)))
                for c in cols)
            body.append("<tr>%s</tr>\n" % cells)

        out = ('<table>\n<thead><tr>%s</tr></thead>\n<tbody>\n%s</tbody>\n'
               "</table>\n" % (head, "".join(body)))
        # Regel 4: Kappung ist SICHTBAR und nennt die Gesamtzahl.
        if truncated:
            out += ('<p class="aiw-truncated">ACHTUNG: Aus Gründen der '
                    'Dateigröße sind hier nur die ersten %d von %d Einträgen '
                    'abgebildet — %d Einträge fehlen in DIESEM Dokument. '
                    'Der vollständige Bestand ist über die Sicht bzw. den '
                    'Endpunkt abrufbar.</p>\n'
                    % (self._max_rows, len(rows), truncated))
        return out

    def _kv_table(self, obj: Dict[str, Any],
                  sec: Optional[SectionSpec]) -> str:
        labels = (sec.labels if sec else {}) or {}
        keys = self._ordered(list(obj.keys()), sec)
        rows = "".join(
            "<tr><th>%s</th><td>%s</td></tr>\n"
            % (html.escape(str(labels.get(k, k))),
               html.escape(self._cell(obj.get(k))))
            for k in keys)
        return "<table>\n<tbody>\n%s</tbody>\n</table>\n" % rows

    @staticmethod
    def _scalar_list(values: Sequence[Any]) -> str:
        items = "".join("<li>%s</li>\n" % html.escape(ViewExportRenderer._cell(v))
                        for v in values)
        return "<ul>\n%s</ul>\n" % items

    def _columns(self, rows: Sequence[dict],
                 sec: Optional[SectionSpec]) -> List[str]:
        """
        Regel 1: Vereinigung ALLER Schluessel ueber ALLE Zeilen, Reihenfolge des
        ersten Auftretens. Ein Feld, das erst spaet auftaucht, bekommt seine
        Spalte — sonst waere es still verschwunden.
        """
        seen: List[str] = []
        known = set()
        for r in rows:
            for k in r.keys():
                if k not in known:
                    known.add(k)
                    seen.append(k)
        return self._ordered(seen, sec)

    @staticmethod
    def _ordered(keys: List[str], sec: Optional[SectionSpec]) -> List[str]:
        """
        'order' zieht bekannte Felder nach vorn — und HAENGT alle uebrigen
        hinten an. Es filtert NIE (das ist der Kern von Regel 1).
        """
        if not sec or not sec.order:
            return keys
        rest = [k for k in keys if k not in sec.order]
        front = [k for k in sec.order if k in keys]
        return front + rest

    @staticmethod
    def _cell(value: Any) -> str:
        """
        Zellwert als Klartext (das Escaping macht der Aufrufer).
        None -> Gedankenstrich; bool -> ja/nein; verschachteltes -> kompaktes
        JSON (UTF-8 erhalten), damit auch strukturierte Werte LESBAR im
        Dokument stehen statt zu verschwinden.
        """
        if value is None:
            return _EM_DASH
        if isinstance(value, bool):
            return "ja" if value else "nein"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return value if value != "" else _EM_DASH
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True,
                              separators=(",", ": "))
        except (TypeError, ValueError):
            return str(value)


class _Missing:
    """Sentinel: 'Schluessel war nicht in der Antwort' (!= None-Wert)."""

    __slots__ = ()

    def __repr__(self) -> str:            # pragma: no cover - Diagnose
        return "<fehlend>"


_MISSING = _Missing()


def query_summary(query: Any, *, drop: Tuple[str, ...] = ("view",)) -> str:
    """
    Klartext der angewandten Query-Parameter fuer den Dokumentkopf. Ohne diese
    Zeile waere im Nachhinein unklar, WELCHER Ausschnitt exportiert wurde —
    ein Export ohne seinen Filter ist als Beleg wertlos.
    'query' ist die parse_qs-Form (Dict[str, List[str]]); Skalare werden
    ebenfalls akzeptiert (Muster ManagementApp._q1).
    """
    if not isinstance(query, dict) or not query:
        return "keine"
    teile = []
    for k in sorted(query.keys()):
        if k in drop:
            continue
        v = query[k]
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v)
        teile.append("%s=%s" % (k, v))
    return "; ".join(teile) if teile else "keine"
