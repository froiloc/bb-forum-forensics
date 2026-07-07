# =============================================================================
# management/workload/html_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Lastverteilung (Frontend)
# =============================================================================
# Zweck:
#   Erzeugt aus einer serialisierten Lastverteilung (Liste von dicts, aus
#   InvestigatorLoad via dataclasses.asdict) eine EINZELNE, self-contained
#   HTML-Datei: CSS, Daten und Render-JS inline. Die Chef-Ermittlerin oeffnet
#   genau eine Datei — kein Server, kein CORS. Spiegelt bewusst
#   management/support_overview/html_export.py bzw. dashboard/html_export.py.
#
#   REINE FUNKTION (keine Datei-/DB-Zugriffe, kein Netz) -> vollstaendig
#   automatisiert testbar.
#
# INTEGRITAETS-BANNER: Der Aufrufer prueft vor dem Export die audit_log-
#   Hashkette (verify_chain) und uebergibt das Ergebnis; die Datei zertifiziert
#   damit selbst, dass Fall-/Zuweisungs- und Aktivitaets-Belege auf einer
#   intakten Kette beruhen.
#
# Sicherheit: Daten-JSON wird '</' -> '<\/' entschaerft (Anzeigenamen sind
#   beliebiger Text), UTF-8 bleibt erhalten.
#
# Version: v0.7.335 · Build: 335 · 2026-07-07
# =============================================================================

import json
from typing import List, Optional

_LEGEND = (
    '<div class="aiw-legend">\n'
    '  <span><i class="dot" style="background:#c0392b"></i>rot: dringliche Last</span>\n'
    '  <span><i class="dot" style="background:#d68910"></i>gelb: mittlere Inaktivitaet</span>\n'
    '  <span><i class="dot" style="background:#1e8449"></i>gruen: aktiv/abgeschlossen</span>\n'
    '  <span><i class="dot" style="background:#7f8c8d"></i>Rueckstau: unzugewiesen</span>\n'
    '</div>\n'
)


def _safe_json(records) -> str:
    """JSON, UTF-8 erhalten, '</' entschaerft (kein vorzeitiges </script>)."""
    raw = json.dumps(records, ensure_ascii=False)
    return raw.replace("</", "<\\/")


def _integrity_banner(verify_result: Optional[dict]) -> str:
    """Kopf-Hinweis zur audit_log-Integritaet (gruen/rot/grau)."""
    if verify_result is None:
        return ('<p class="aiw-integrity aiw-integrity-unknown">'
                'Audit-Kette: nicht geprueft.</p>\n')
    if verify_result.get("ok"):
        tip_seq = verify_result.get("tip_seq")
        tip_hash = verify_result.get("tip_hash") or ""
        short = (tip_hash[:16] + "\u2026") if len(tip_hash) > 16 else tip_hash
        return ('<p class="aiw-integrity aiw-integrity-ok">'
                'Audit-Kette verifiziert bis seq ' + str(tip_seq) +
                ' (row_hash ' + short + '). Last-/Aktivitaets-Belege beruhen '
                'auf intakter Kette.</p>\n')
    detail = str(verify_result.get("detail") or "unbekannter Bruch")
    bad = verify_result.get("first_bad_seq")
    return ('<p class="aiw-integrity aiw-integrity-bad">'
            'WARNUNG: Audit-Kette GEBROCHEN (' + detail +
            (', erste fehlerhafte seq=' + str(bad) if bad is not None else '') +
            '). Zahlen sind NICHT vertrauenswuerdig.</p>\n')


def build_workload_html(records: List[dict], css_text: str, js_text: str, *,
                        debug: bool = False,
                        generated_at: Optional[str] = None,
                        verify_result: Optional[dict] = None) -> str:
    """
    Baut die self-contained Lastverteilungs-HTML.

    records:       Liste serialisierter InvestigatorLoad-dicts (kann leer sein).
    css_text/js_text: Inhalt von workload.css/.js (inline eingebettet).
    debug:         setzt window.AIW_WORKLOAD_DEBUG (PROD: False).
    generated_at:  optionaler Stand-Vermerk fuer den Kopf.
    verify_result: optionales audit_log-Pruefergebnis fuer das Banner.

    Zusammenbau per Konkatenation (NICHT format/%), da CSS/JS '{' und '%'
    enthalten.
    """
    sub = ("Getrennte Administrations-Sicht (Chef-Ermittlerin). Last je "
           "Ermittler nach Dringlichkeit/Status, plus unzugewiesener Rueckstau "
           "als Verteilungs-Pool. Umverteilung erfolgt weiterhin ueber die "
           "auditierte Einzelfall-Zuweisung (cases_admin --assign).")
    if generated_at:
        sub += " Stand: " + generated_at + "."

    return (
        "<!DOCTYPE html>\n"
        '<html lang="de">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>AIW \u2014 Ermittler-Lastverteilung</title>\n"
        "<style>\n"
        + css_text +
        "\n</style>\n</head>\n<body>\n"
        "<h1>Ermittler-Lastverteilung</h1>\n"
        '<p class="aiw-sub">' + sub + "</p>\n"
        + _integrity_banner(verify_result) +
        '<div class="aiw-filterbar">\n'
        '  <input id="aiw-filter" type="text" placeholder="Filtern '
        '(Ermittler) \u2026" autocomplete="off">\n'
        '  <span id="aiw-count" class="aiw-count"></span>\n'
        '</div>\n'
        '<div id="aiw-workload-root"></div>\n'
        + _LEGEND +
        "<script>\n"
        "window.AIW_WORKLOAD_DEBUG = " + ("true" if debug else "false") + ";\n"
        "window.__AIW_WORKLOAD__ = " + _safe_json(records) + ";\n"
        "</script>\n"
        "<script>\n"
        + js_text +
        "\n</script>\n"
        "</body>\n</html>\n"
    )
