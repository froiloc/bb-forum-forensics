# =============================================================================
# management/support_overview/html_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Support-Historie (Frontend)
# =============================================================================
# Zweck:
#   Erzeugt aus einer serialisierten Sitzungs-Historie (Liste von dicts, aus
#   SupportSessionRecord via dataclasses.asdict) eine EINZELNE, self-contained
#   HTML-Datei: CSS, Daten und Render-JS werden inline eingebettet. Die Chef-
#   Ermittlerin oeffnet genau eine Datei — kein Server, kein CORS, kein externer
#   Dateiverweis (saubere Trennung von der Ermittlungsoberflaeche). Spiegelt
#   bewusst das Muster von management/dashboard/html_export.py.
#
#   REINE FUNKTION (keine Datei-/DB-Zugriffe, kein Netz) -> vollstaendig
#   automatisiert testbar. Das Einlesen von support_overview.css/.js und der
#   echten Daten erfolgt im CLI-Aufrufer (support_overview_admin export-html).
#
# FORENSISCHER ZUSATZ — Integritaets-Banner: Der Aufrufer prueft VOR dem Export
#   die audit_log-Hashkette (verify_chain) und uebergibt das Ergebnis. Die
#   Export-Datei zertifiziert damit SELBST, dass die Belegkette zum Lesezeitpunkt
#   intakt (oder eben gebrochen) war — die Historie ist nur so vertrauenswuerdig
#   wie die Kette, aus der sie stammt.
#
# Sicherheit beim Inlinen: Die Daten (JSON) werden vor dem Einbetten so
#   entschaerft, dass ein '</script>' o. Ae. aus Forumsdaten (beliebiger UTF-8-
#   Text — multilinguale Benutzernamen!) die Seite NICHT vorzeitig schliessen
#   kann ('</' -> '<\/'). UTF-8 bleibt erhalten.
#
# Version: v0.7.330 · Build: 330 · 2026-07-07
# =============================================================================

import json
from typing import List, Optional, TYPE_CHECKING

from management.export.checksum import json_payload_sha256

if TYPE_CHECKING:
    from management.export.export_envelope import ExportEnvelope

_LEGEND = (
    '<div class="aiw-legend">\n'
    '  <span><i class="dot" style="background:#1e8449"></i>beendet: sauberes Ende</span>\n'
    '  <span><i class="dot" style="background:#d68910"></i>orphan_timeout: Zeitueberschreitung (System)</span>\n'
    '  <span><i class="dot" style="background:#2471a3"></i>offen: kein ENDED-Beleg</span>\n'
    '  <span><i class="dot" style="background:#c0392b"></i>herrenlos: ENDED ohne STARTED</span>\n'
    '</div>\n'
)


def _safe_json(records) -> str:
    """
    JSON der Historie, UTF-8 erhalten, aber '</' entschaerft, damit kein
    '</script>' aus den Daten den Inline-<script>-Block bricht.
    """
    raw = json.dumps(records, ensure_ascii=False)
    return raw.replace("</", "<\\/")


def _integrity_banner(verify_result: Optional[dict]) -> str:
    """
    Baut den Kopf-Hinweis zur audit_log-Integritaet. verify_result ist ein dict
    {ok: bool, tip_seq: int, tip_hash: str, detail: str} oder None (kein Check).
    Die Klasse steuert die Farbe (gruen=intakt, rot=Bruch, grau=ungeprueft).
    """
    if verify_result is None:
        return ('<p class="aiw-integrity aiw-integrity-unknown">'
                'Audit-Kette: nicht geprueft.</p>\n')
    if verify_result.get("ok"):
        tip_seq = verify_result.get("tip_seq")
        tip_hash = verify_result.get("tip_hash") or ""
        short = (tip_hash[:16] + "\u2026") if len(tip_hash) > 16 else tip_hash
        return ('<p class="aiw-integrity aiw-integrity-ok">'
                'Audit-Kette verifiziert bis seq ' + str(tip_seq) +
                ' (row_hash ' + short + '). Historie beruht auf intakter '
                'Belegkette.</p>\n')
    detail = str(verify_result.get("detail") or "unbekannter Bruch")
    bad = verify_result.get("first_bad_seq")
    return ('<p class="aiw-integrity aiw-integrity-bad">'
            'WARNUNG: Audit-Kette GEBROCHEN (' + detail +
            (', erste fehlerhafte seq=' + str(bad) if bad is not None else '') +
            '). Historie ist NICHT vertrauenswuerdig.</p>\n')


def build_support_overview_html(records: List[dict], css_text: str, js_text: str,
                                *, debug: bool = False,
                                generated_at: Optional[str] = None,
                                verify_result: Optional[dict] = None,
                                envelope: "Optional[ExportEnvelope]" = None) -> str:
    """
    Baut die self-contained Support-Historie-HTML.

    records:       Liste serialisierter SupportSessionRecord-dicts (kann leer sein).
    css_text:      Inhalt von support_overview.css (wird inline eingebettet).
    js_text:       Inhalt von support_overview.js (wird inline eingebettet).
    debug:         setzt window.AIW_SUPPORT_OVERVIEW_DEBUG (PROD: False).
    generated_at:  optionaler Stand-Vermerk fuer den Kopf.
    verify_result: optionales audit_log-Pruefergebnis fuer das Integritaets-Banner.
    envelope:      optionaler ExportEnvelope (B442): einheitlicher Aktenkopf-Band
                   + Erzeugungsvermerk/Pruefsumme. None -> unveraendert.

    Zusammenbau per Konkatenation (NICHT str.format/%), da CSS/JS geschweifte
    Klammern und '%' enthalten, die Format-Platzhalter stoeren wuerden.
    """
    sub = ("Getrennte Administrations-Sicht (Chef-Ermittlerin). Permanente "
           "'wer sah wann welchen Fall'-Historie aus dem audit_log — nicht aus "
           "der fluechtigen Praesenztabelle. Chronologisch, sortier- und "
           "filterbar.")
    if generated_at:
        sub += " Stand: " + generated_at + "."

    band = envelope.classification_band_html() if envelope else ""
    foot = (envelope.footer_html(json_payload_sha256(records))
            if envelope else "")

    return (
        "<!DOCTYPE html>\n"
        '<html lang="de">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>AIW \u2014 Support-Sitzungs-Historie</title>\n"
        "<style>\n"
        + css_text +
        "\n</style>\n</head>\n<body>\n"
        + band +
        "<h1>Support-Sitzungs-Historie</h1>\n"
        '<p class="aiw-sub">' + sub + "</p>\n"
        + _integrity_banner(verify_result) +
        '<div class="aiw-filterbar">\n'
        '  <input id="aiw-filter" type="text" placeholder="Filtern '
        '(Supporter, Benutzer, Fall, Status) \u2026" autocomplete="off">\n'
        '  <span id="aiw-count" class="aiw-count"></span>\n'
        '</div>\n'
        '<div id="aiw-support-overview-root"></div>\n'
        + _LEGEND +
        "<script>\n"
        "window.AIW_SUPPORT_OVERVIEW_DEBUG = "
        + ("true" if debug else "false") + ";\n"
        "window.__AIW_SUPPORT_OVERVIEW__ = " + _safe_json(records) + ";\n"
        "</script>\n"
        "<script>\n"
        + js_text +
        "\n</script>\n"
        + foot +
        "</body>\n</html>\n"
    )
