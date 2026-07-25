# =============================================================================
# management/stats/forecast_report.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-3F)
# =============================================================================
# Zweck (Idee 40 — Prognose-3-Szenarien-PDF):
#   Gibt die Backlog-Abbau-Prognose aus Build 446 (management/stats/forecast.py)
#   als vorlegbaren Beleg aus — als self-contained HTML UND als PDF. Der Bericht
#   traegt den einheitlichen Aktenkopf, den Erzeugungsvermerk und die Pruefsumme
#   aus dem Export-Framework (Build 440, management/export/export_envelope.py).
#
# DIE WICHTIGSTE ENTSCHEIDUNG DIESES MODULS:
#   Eine Prognose OHNE ihre Annahmen ist eine unbelegte Behauptung. Deshalb sind
#   die 'assumptions' aus der Prognose kein Anhang, sondern ein PFLICHTABSCHNITT
#   in BEIDEN Ausgaben — WORTGLEICH und VOLLSTAENDIG, in der Reihenfolge, in der
#   das Backend sie erzeugt hat (forecast.py:104-120). Nichts wird gekuerzt,
#   umformuliert oder gefiltert (Grundregel 1). Fehlt die Liste ganz, MELDET der
#   Bericht das ausdruecklich (statt einen Abschnitt einfach weglassen zu
#   koennen, was wie "es gab keine Annahmen" aussehen wuerde).
#
# EHRLICHKEIT BEI DUENNER DATENLAGE (uebernommen aus forecast.py:19-22):
#   data_sufficient=False bedeutet: es gab KEINE beobachteten Abschluesse im
#   Rueckblickfenster. Dann steht in der Restdauer 'unbestimmt' — NIE 0 und nie
#   ein Datum. Zusaetzlich traegt der Bericht in diesem Fall einen VORBEHALT
#   GANZ OBEN (nicht als Fussnote): eine Szenario-Tabelle mit drei Zeilen sieht
#   auch dann nach einer Aussage aus, wenn keine darin steht.
#
# KAPAZITAET IST NUR KONTEXT (forecast.py:24-27): die Netto-Minuten werden
#   ausgewiesen, aber ausdruecklich NICHT in Abschluesse umgerechnet — dafuer
#   fehlt ein belegter Aufwand je Fall. Der Bericht sagt das an der Zahl, nicht
#   irgendwo weiter unten. Fehlt der Kontext, steht "nicht verfuegbar" da
#   (kein leerer Abschnitt).
#
# REINE FUNKTIONEN (Muster status_report.py:15-20): kein DB-, Netz- oder
#   Uhrzugriff. forecast-dict und ExportContext werden INJIZIERT -> die Ausgabe
#   ist deterministisch und vollstaendig per pytest pruefbar. reportlab wird
#   fuer die PDF-Ausgabe LAZY importiert; fehlt sie ->
#   ForecastReportUnavailable (kein stiller Ausfall, analog
#   StatusReportUnavailable/PdfRendererUnavailable).
#
# PRUEFSUMME: SHA-256 ueber die Prognose-Nutzlast (json_payload_sha256), in HTML
#   und PDF IDENTISCH — beide Ausgaben desselben Standes tragen denselben
#   Datendigest und sind vom Empfaenger unabhaengig nachrechenbar.
#
# Version: v0.8.522 · Build: 522 · 2026-07-25
# =============================================================================

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional, Tuple

from management.export.checksum import json_payload_sha256
from management.export.export_envelope import ExportEnvelope

#: Titel beider Ausgaben (eine Wahrheit, damit HTML und PDF nicht abdriften).
TITEL = "Prognose — Backlog-Abbau in drei Szenarien"

#: Der Vorbehalt bei duenner Datenlage. Wortlaut ist Absicht: er sagt, dass
#  KEINE Prognose vorliegt — nicht, dass die Prognose "0 Tage" lautet.
VORBEHALT_DATENARM = (
    "KEINE BELASTBARE PROGNOSE: Im Rueckblickfenster wurde kein einziger "
    "Fallabschluss beobachtet. Die Szenarien unten fuehren deshalb KEINE "
    "Restdauer und KEIN Fertigstellungsdatum. Die Tabelle belegt den Zustand "
    "der Datenlage, nicht einen Zeitplan."
)

#: Steht IMMER dabei — auch bei guter Datenlage. Eine lineare Fortschreibung
#  ohne Zu-/Abgaenge ist eine Modellannahme, keine Tatsache.
VORBEHALT_MODELL = (
    "MODELLVORBEHALT: Die Restdauer ist eine lineare Fortschreibung der "
    "beobachteten Abschlussrate ohne Zu- und Abgaenge neuer Faelle. Sie ist "
    "eine Planungsgroesse und kein zugesagter Termin."
)

#: Kapazitaet ist Kontext, nicht Rechengroesse (forecast.py:24-27).
VORBEHALT_KAPAZITAET = (
    "Der Kapazitaets-Kontext ist NICHT in Abschluesse umgerechnet — dafuer "
    "fehlt ein belegter Aufwand je Fall. Er steht als Groessenordnung dabei."
)


class ForecastReportUnavailable(RuntimeError):
    """reportlab ist nicht installiert — PDF-Prognosebericht nicht moeglich."""


def forecast_digest(forecast: Dict[str, Any]) -> str:
    """Datendigest ueber die Prognose-Nutzlast (kanonisch, nachrechenbar)."""
    return json_payload_sha256(forecast)


# -- Aufbereitung: EINE Wahrheit fuer HTML und PDF ----------------------------

def _txt(value: Any, fallback: str = "-") -> str:
    """Anzeigewert; None/'' -> fallback (nie ein leeres Feld ohne Aussage)."""
    if value is None:
        return fallback
    s = str(value)
    return s if s != "" else fallback


def vorbehalt_lines(forecast: Dict[str, Any]) -> List[str]:
    """
    Die Vorbehalte in Lesereihenfolge. Der DATENARM-Vorbehalt steht VORNE,
    wenn er greift — er entscheidet, wie die ganze Tabelle zu lesen ist.

    data_sufficient wird BEWUSST streng geprueft: nur ein echtes True gilt als
    ausreichende Datenlage. Fehlt der Schluessel (aeltere Antwort, fremder
    Aufrufer), gilt die Lage als duenn — im Zweifel der Vorbehalt, nicht die
    Aussage.
    """
    lines: List[str] = []
    if forecast.get("data_sufficient") is not True:
        lines.append(VORBEHALT_DATENARM)
    lines.append(VORBEHALT_MODELL)
    lines.append(VORBEHALT_KAPAZITAET)
    return lines


def grundlage_rows(forecast: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Kennzahl/Wert-Zeilen des Abschnitts 'Grundlage der Prognose'."""
    suff = forecast.get("data_sufficient")
    return [
        ("Stichtag (UTC)", _txt(forecast.get("now_day"))),
        ("Offener Fallbestand (Backlog)", _txt(forecast.get("backlog"), "0")),
        ("Rueckblickfenster (Tage)", _txt(forecast.get("lookback_days"))),
        ("Beobachtete Abschluesse im Fenster",
         _txt(forecast.get("completions_observed"), "0")),
        ("Beobachtete Rate (Faelle/Tag)",
         _txt(forecast.get("observed_rate_per_day"), "0")),
        ("Datenlage ausreichend",
         "ja" if suff is True else "NEIN — keine belastbare Prognose"),
    ]


def scenario_rows(forecast: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Eine Zeile je Szenario, bereits als ANZEIGETEXT.

    days_to_clear None -> 'unbestimmt' (NIE '0'): der Unterschied zwischen
    "nichts mehr zu tun" und "nicht berechenbar" ist der ganze Punkt.
    days_to_clear 0 wird als '0 Tage (Backlog leer)' benannt statt als
    Leerwert gezeigt — auch die Null ist eine Aussage.
    """
    out: List[Dict[str, str]] = []
    for s in (forecast.get("scenarios") or []):
        days = s.get("days_to_clear")
        if days is None:
            days_text = "unbestimmt"
        elif int(days) == 0:
            days_text = "0 Tage (Backlog leer)"
        else:
            days_text = "%d Tage" % int(days)
        out.append({
            "name": _txt(s.get("name")),
            "factor": "x%s" % _txt(s.get("factor")),
            "rate": _txt(s.get("rate_per_day"), "0"),
            "days": days_text,
            "finish": _txt(s.get("finish_day"), "unbestimmt"),
        })
    return out


def kapazitaet_rows(forecast: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Kennzahl/Wert-Zeilen des Kapazitaets-Kontexts.

    Fehlt der Kontext (None), gibt es KEINEN leeren Abschnitt, sondern eine
    ausdrueckliche Zeile 'nicht verfuegbar'. Ein leerer Abschnitt liesse offen,
    ob nicht gerechnet oder nichts gefunden wurde.
    """
    ctx = forecast.get("capacity_context")
    if not isinstance(ctx, dict):
        return [("Kapazitaets-Kontext", "nicht verfuegbar (keine "
                                        "Arbeitszeitdaten oder nicht erhoben)")]
    return [
        ("Personen mit Arbeitszeitdaten", _txt(ctx.get("persons"), "0")),
        ("Verfuegbare Netto-Minuten", _txt(ctx.get("netto_minutes"), "0")),
        ("Fenster (Tage)", _txt(ctx.get("window_days"))),
        ("Fenster von", _txt(ctx.get("window_start"))),
        ("Fenster bis", _txt(ctx.get("window_end"))),
    ]


def assumption_lines(forecast: Dict[str, Any]) -> List[str]:
    """
    Die Annahmen WORTGLEICH und in Backend-Reihenfolge.

    Ist die Liste leer oder fehlt sie, liefert diese Funktion eine
    AUSDRUECKLICHE Meldung statt einer leeren Liste. Ein leerer
    Annahmen-Abschnitt wuerde behaupten, die Prognose beruhe auf keinen
    Annahmen — das waere die unwahrste moegliche Aussage dieses Berichts.
    """
    items = forecast.get("assumptions")
    if not items:
        return ["KEINE ANNAHMEN UEBERMITTELT — die Prognose ist ohne die "
                "Annahmen des erzeugenden Moduls nicht nachvollziehbar. "
                "Bitte den Erzeugungsstand pruefen."]
    return [str(a) for a in items]


# -- HTML ---------------------------------------------------------------------

def build_forecast_report_html(forecast: Dict[str, Any], context,
                               *, period_label: Optional[str] = None) -> str:
    """
    Self-contained Prognosebericht (HTML) im einheitlichen Rahmen.

    Alle eingebetteten Werte werden html-escaped (multilinguale Quellen, UTF-8
    bleibt erhalten — escape kodiert nur < > & " ').
    """
    env = ExportEnvelope(context)
    digest = forecast_digest(forecast)

    parts: List[str] = [
        "<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<title>AIW — Prognosebericht</title>\n"
        "<style>body{font-family:sans-serif;margin:2em}"
        "table{border-collapse:collapse;margin:.4em 0}"
        "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}"
        "th{background:#1F4E79;color:#fff}"
        ".aiw-export-band{background:#1F4E79;color:#fff;padding:8px}"
        ".aiw-vorbehalt{border-left:6px solid #b7950b;background:#fcf3cf;"
        "padding:8px 12px;margin:.8em 0}"
        ".aiw-vorbehalt--datenarm{border-left-color:#c0392b;background:#fdecea}"
        "h2{margin-top:1.2em}</style>\n</head>\n<body>\n",
        env.classification_band_html(),
        "<h1>%s</h1>\n" % html.escape(TITEL),
    ]
    if period_label:
        parts.append("<p>Zeitraum: %s</p>\n" % html.escape(period_label))

    # Die Vorbehalte stehen GANZ OBEN, vor jeder Zahl. Der datenarme Vorbehalt
    # bekommt eine eigene Auszeichnung — er aendert die Lesart der Tabelle.
    for i, line in enumerate(vorbehalt_lines(forecast)):
        cls = "aiw-vorbehalt"
        if i == 0 and line == VORBEHALT_DATENARM:
            cls += " aiw-vorbehalt--datenarm"
        parts.append('<div class="%s">%s</div>\n' % (cls, html.escape(line)))

    parts.append("<h2>Grundlage der Prognose</h2>\n<table>\n"
                 "<tr><th>Kennzahl</th><th>Wert</th></tr>\n")
    for k, v in grundlage_rows(forecast):
        parts.append("<tr><td>%s</td><td>%s</td></tr>\n"
                     % (html.escape(k), html.escape(v)))
    parts.append("</table>\n")

    parts.append("<h2>Die drei Szenarien</h2>\n<table>\n"
                 "<tr><th>Szenario</th><th>Faktor</th><th>Rate/Tag</th>"
                 "<th>Restdauer</th><th>Voraussichtliche Fertigstellung</th>"
                 "</tr>\n")
    rows = scenario_rows(forecast)
    if not rows:
        # Kein stiller Leerbefund: eine Prognose ohne Szenarien ist ein Befund.
        parts.append("<tr><td colspan=\"5\"><em>KEINE SZENARIEN "
                     "UEBERMITTELT</em></td></tr>\n")
    for r in rows:
        parts.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                     "<td>%s</td></tr>\n"
                     % (html.escape(r["name"]), html.escape(r["factor"]),
                        html.escape(r["rate"]), html.escape(r["days"]),
                        html.escape(r["finish"])))
    parts.append("</table>\n")

    parts.append("<h2>Kapazitaets-Kontext (nicht in Abschluesse "
                 "umgerechnet)</h2>\n<table>\n")
    for k, v in kapazitaet_rows(forecast):
        parts.append("<tr><td>%s</td><td>%s</td></tr>\n"
                     % (html.escape(k), html.escape(v)))
    parts.append("</table>\n")

    parts.append("<h2>Annahmen der Prognose (unveraendert aus dem "
                 "Erzeugungsmodul)</h2>\n<ul>\n")
    for line in assumption_lines(forecast):
        parts.append("<li>%s</li>\n" % html.escape(line))
    parts.append("</ul>\n")

    parts.append(env.footer_html(digest))
    parts.append("</body>\n</html>\n")
    return "".join(parts)


# -- PDF (reportlab, lazy) ----------------------------------------------------

def build_forecast_report_pdf(forecast: Dict[str, Any], context,
                              *, period_label: Optional[str] = None) -> bytes:
    """
    Prognosebericht als PDF (reportlab/platypus).

    Der Aufbau spiegelt die HTML-Fassung ABSCHNITT FUER ABSCHNITT — beide
    speisen sich aus denselben reinen Funktionen (grundlage_rows,
    scenario_rows, kapazitaet_rows, assumption_lines, vorbehalt_lines). Damit
    kann keine der beiden Ausgaben etwas enthalten, was die andere nicht hat;
    zwei Belege desselben Standes duerfen sich nicht widersprechen.

    Fehlt reportlab -> ForecastReportUnavailable (kein stiller Ausfall).
    """
    try:
        import io
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
    except ImportError as exc:  # pragma: no cover - Umgebungsrandfall
        raise ForecastReportUnavailable(str(exc)) from exc

    env = ExportEnvelope(context)
    digest = forecast_digest(forecast)
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    small = ParagraphStyle("aiw_small", parent=body, fontSize=8,
                           textColor=colors.HexColor("#555555"))
    warn = ParagraphStyle("aiw_warn", parent=body, fontSize=9,
                          textColor=colors.HexColor("#7d6608"))
    alarm = ParagraphStyle("aiw_alarm", parent=body, fontSize=9,
                           textColor=colors.HexColor("#c0392b"))

    def esc(s: Any) -> str:
        """XML-Escaping fuer das Paragraph-Mini-Markup von reportlab."""
        return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    story: List[Any] = []
    story.append(Paragraph(esc(context.klassifikation), small))
    story.append(Paragraph(esc(TITEL), styles["Title"]))
    meta = "Behoerde: %s · Aktenzeichen: %s" % (
        esc(context.behoerde), esc(context.aktenzeichen))
    if period_label:
        meta += " · Zeitraum: " + esc(period_label)
    story.append(Paragraph(meta, small))
    story.append(Spacer(1, 0.4 * cm))

    # Vorbehalte ZUERST (siehe Modulkopf).
    for line in vorbehalt_lines(forecast):
        story.append(Paragraph(esc(line),
                               alarm if line == VORBEHALT_DATENARM else warn))
        story.append(Spacer(1, 0.15 * cm))
    story.append(Spacer(1, 0.25 * cm))

    tstyle = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])

    def kv_block(title: str, rows: List[Tuple[str, str]]) -> None:
        story.append(Paragraph(esc(title), styles["Heading2"]))
        data = [["Kennzahl", "Wert"]] + [[esc(k), esc(v)] for k, v in rows]
        tbl = Table(data, colWidths=[8.5 * cm, 7.5 * cm])
        tbl.setStyle(tstyle)
        story.append(tbl)
        story.append(Spacer(1, 0.3 * cm))

    kv_block("Grundlage der Prognose", grundlage_rows(forecast))

    story.append(Paragraph("Die drei Szenarien", styles["Heading2"]))
    sdata = [["Szenario", "Faktor", "Rate/Tag", "Restdauer",
              "Fertigstellung"]]
    srows = scenario_rows(forecast)
    if srows:
        for r in srows:
            sdata.append([esc(r["name"]), esc(r["factor"]), esc(r["rate"]),
                          esc(r["days"]), esc(r["finish"])])
    else:
        sdata.append(["KEINE SZENARIEN UEBERMITTELT", "", "", "", ""])
    stbl = Table(sdata, colWidths=[3.6 * cm, 1.8 * cm, 2.4 * cm, 4.2 * cm,
                                   4.0 * cm])
    stbl.setStyle(tstyle)
    story.append(stbl)
    story.append(Spacer(1, 0.3 * cm))

    kv_block("Kapazitaets-Kontext (nicht in Abschluesse umgerechnet)",
             kapazitaet_rows(forecast))

    story.append(Paragraph("Annahmen der Prognose (unveraendert aus dem "
                           "Erzeugungsmodul)", styles["Heading2"]))
    for line in assumption_lines(forecast):
        story.append(Paragraph("• " + esc(line), body))
    story.append(Spacer(1, 0.4 * cm))

    for line in env.erzeugungsvermerk_lines():
        story.append(Paragraph(esc(line), small))
    story.append(Paragraph("Pruefsumme Prognose (SHA-256): %s" % esc(digest),
                           small))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title="AIW-Prognosebericht",
                      author="AIW", subject=TITEL).build(story)
    return buf.getvalue()
