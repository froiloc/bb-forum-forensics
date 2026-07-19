# =============================================================================
# management/dashboard/html_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ampel-Dashboard (Frontend)
# =============================================================================
# Zweck:
#   Erzeugt aus einer serialisierten Fall-Uebersicht (Liste von dicts, aus
#   CaseOverview via dataclasses.asdict) eine EINZELNE, self-contained HTML-
#   Datei: CSS, Daten und Render-JS werden inline eingebettet. Der Admin oeffnet
#   genau eine Datei — kein Server, kein CORS, kein externer Dateiverweis
#   (saubere Trennung von der Ermittlungsoberflaeche).
#
#   REINE FUNKTION (keine Datei-/DB-Zugriffe, kein Netz) -> vollstaendig
#   automatisiert testbar. Das Einlesen von dashboard.css/dashboard.js und der
#   echten Daten erfolgt im CLI-Aufrufer (dashboard_admin export-html).
#
# Sicherheit beim Inlinen: Die Daten (JSON) werden vor dem Einbetten so
#   entschaerft, dass ein '</script>' o. Ae. aus Forumsdaten (beliebiger UTF-8-
#   Text!) die Seite NICHT vorzeitig schliessen kann ('</' -> '<\/'). UTF-8
#   bleibt erhalten (multilinguale Benutzernamen).
#
# Beleg: management/dashboard/frontend/dashboard.js (Render-Schicht, Build 322),
#        management/dashboard/dashboard_repo.py (CaseOverview), Build 314/315.
# Version: v0.7.323 · Build: 323 · 2026-07-04
# =============================================================================

import json
from typing import List, Optional, TYPE_CHECKING

from management.export.checksum import json_payload_sha256

if TYPE_CHECKING:
    from management.export.export_envelope import ExportEnvelope

_LEGEND = (
    '<div class="aiw-legend">\n'
    '  <span><i class="dot" style="background:#c0392b"></i>rot: braucht Aufmerksamkeit</span>\n'
    '  <span><i class="dot" style="background:#d68910"></i>gelb: mittlere Inaktivitaet</span>\n'
    '  <span><i class="dot" style="background:#1e8449"></i>gruen: aktiv / abgeschlossen</span>\n'
    '</div>\n'
)


def _safe_json(overview) -> str:
    """
    JSON der Uebersicht, UTF-8 erhalten, aber '</' entschaerft, damit kein
    '</script>' aus den Daten den Inline-<script>-Block bricht.
    """
    raw = json.dumps(overview, ensure_ascii=False)
    return raw.replace("</", "<\\/")


def build_dashboard_html(overview: List[dict], css_text: str, js_text: str, *,
                         debug: bool = False,
                         generated_at: Optional[str] = None,
                         envelope: "Optional[ExportEnvelope]" = None) -> str:
    """
    Baut die self-contained Dashboard-HTML.

    overview:      Liste serialisierter CaseOverview-dicts (kann leer sein).
    css_text:      Inhalt von dashboard.css (wird inline eingebettet).
    js_text:       Inhalt von dashboard.js (wird inline eingebettet).
    debug:         setzt window.AIW_DASHBOARD_DEBUG (PROD: False).
    generated_at:  optionaler Stand-Vermerk fuer den Kopf.
    envelope:      optionaler ExportEnvelope (B442). Ist er gesetzt, traegt die
                   Datei den EINHEITLICHEN Aktenkopf-Band (Klassifikation/
                   Behoerde/Aktenzeichen) oben und den Erzeugungsvermerk +
                   Pruefsumme (SHA-256 ueber die eingebettete Datenliste) unten.
                   None -> unveraendertes Verhalten (Rueckwaertskompatibilitaet).

    Zusammenbau per Konkatenation (NICHT str.format/%), da CSS/JS geschweifte
    Klammern und '%' enthalten, die Format-Platzhalter stoeren wuerden.
    """
    sub = ("Getrennte Administrations-Sicht (Chef-Ermittlerin). Sortierung: "
           "Dringlichkeit zuerst (rot &gt; gelb &gt; gruen), dann Prioritaet, "
           "dann letzte Aktivitaet.")
    if generated_at:
        sub += " Stand: " + generated_at + "."

    # Einheitlicher Rahmen (nur wenn envelope gesetzt). Die Pruefsumme deckt die
    # eingebettete Datenliste \u2014 vom Empfaenger unabhaengig nachrechenbar.
    band = envelope.classification_band_html() if envelope else ""
    foot = (envelope.footer_html(json_payload_sha256(overview))
            if envelope else "")

    return (
        "<!DOCTYPE html>\n"
        '<html lang="de">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>AIW \u2014 Ampel-Dashboard (Fall-Uebersicht)</title>\n"
        "<style>\n"
        + css_text +
        "\n</style>\n</head>\n<body>\n"
        + band +
        "<h1>Ampel-Dashboard \u2014 Fall-Uebersicht</h1>\n"
        '<p class="aiw-sub">' + sub + "</p>\n"
        '<div id="aiw-dashboard-root"></div>\n'
        + _LEGEND +
        "<script>\n"
        "window.AIW_DASHBOARD_DEBUG = " + ("true" if debug else "false") + ";\n"
        "window.__AIW_DASHBOARD__ = " + _safe_json(overview) + ";\n"
        "</script>\n"
        "<script>\n"
        + js_text +
        "\n</script>\n"
        + foot +
        "</body>\n</html>\n"
    )
