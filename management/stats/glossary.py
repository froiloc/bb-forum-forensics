# =============================================================================
# management/stats/glossary.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck (Idee 17 — Kennzahlen-Glossar):
#   EINE autoritative, belegte Definition je Kennzahl, die das Werkzeug
#   ausweist. Grundlage jeder StA-/Fuehrungs-Statistik: gleiche Zahl, gleiche
#   Bedeutung — nachvollziehbar, gerichtsfest zitierbar.
#
#   GROUNDING (Grundregel 1 — kein Beleg ausgelassen): Das Glossar definiert
#   GENAU die von StatsRepo.compute (management/stats/stats_repo.py) erzeugten
#   Kennzahlen. verify_covers_stats() erzwingt, dass keine erzeugte Kennzahl
#   ohne Definition bleibt und keine Definition ins Leere zeigt — analog zum
#   RBAC-Katalog-Startcheck. Jede Definition traegt ihren Code-Beleg
#   (Datei:Zeile bzw. Symbol).
#
#   ZWECKBINDUNG (Bauplan B7 v1.1 §11.5, verbindlich): personenbezogene
#   Kennzahlen (by_assignee, throughput) dienen der Auswertungs-Steuerung,
#   NICHT der Mitarbeiter-Bewertung. Dieser Hinweis ist Teil der Definition.
#
#   REINE DATEN + reine Funktionen (kein DB-/Netz-/Uhr-Zugriff) -> testbar.
#
# Version: v0.7.444 · Build: 444 · 2026-07-19
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Die von StatsRepo gefuehrten Vokabulare — hier NICHT neu definiert, sondern
# importiert, damit Glossar und Statistik dieselbe Wahrheit teilen (kein Drift).
from management.stats.stats_repo import _STATUSES, _PRIORITIES

# Ampel-Werte (Beleg: management/dashboard/dashboard_repo.py classify_ampel).
AMPEL_VALUES: Tuple[str, ...] = ("rot", "gelb", "gruen")

# Die Abschnitte, die StatsRepo.compute liefert (Beleg stats_repo.py:82-96).
STATS_SECTIONS: Tuple[str, ...] = (
    "totals.cases", "totals.assigned", "totals.unassigned", "totals.events",
    "by_status", "by_priority", "by_ampel", "by_assignee", "throughput_by_day",
)

_ZWECKBINDUNG = ("Zweckbindung (B7 v1.1 §11.5): Leitlinie zur Auswertungs"
                 "qualitaet, KEIN Mitarbeiter-Bewertungsinstrument.")


class GlossaryError(Exception):
    """Allgemeiner Glossar-Fehler."""


class GlossaryIncompleteError(GlossaryError):
    """Eine erzeugte Kennzahl hat keine Definition (oder umgekehrt)."""


@dataclass(frozen=True)
class KpiDefinition:
    """Eine belegte Kennzahl-Definition."""
    key: str            # eindeutiger Schluessel (Sektion oder Sektion.wert)
    label: str          # Anzeigename
    definition: str     # was die Kennzahl aussagt
    quelle: str         # Code-Beleg (Datei/Symbol)
    einheit: str        # z. B. 'Anzahl Faelle', 'Anzahl Ereignisse'
    hinweis: str = ""   # optionaler Zusatz (z. B. Zweckbindung)


# --- Der eingefrorene Katalog -------------------------------------------------
# Reihenfolge = Anzeigeordnung. Werte-Definitionen (Status/Prioritaet/Ampel)
# folgen ihren Sektionen.
KPI_GLOSSARY: Tuple[KpiDefinition, ...] = (
    KpiDefinition(
        "totals.cases", "Fälle gesamt",
        "Anzahl der Fallakten (cases) im gewaehlten Umfang. Grundgesamtheit "
        "aller weiteren Kennzahlen.",
        "stats_repo.py: totals['cases'] = len(list_case_overview())",
        "Anzahl Fälle"),
    KpiDefinition(
        "totals.assigned", "Zugewiesen",
        "Faelle mit gesetztem assigned_to (einem Ermittler zugewiesen).",
        "stats_repo.py: totals['assigned'] (cases.assigned_to IS NOT NULL)",
        "Anzahl Fälle"),
    KpiDefinition(
        "totals.unassigned", "Unzugewiesen",
        "Faelle ohne Zuweisung (Rueckstau/Verteilungs-Pool).",
        "stats_repo.py: totals['unassigned'] (cases.assigned_to IS NULL)",
        "Anzahl Fälle"),
    KpiDefinition(
        "totals.events", "Ereignisse gesamt",
        "Summe der Fall-Ereignisse (case_events) ueber alle Faelle im Umfang.",
        "stats_repo.py: totals['events'] = sum(c.event_count)",
        "Anzahl Ereignisse"),
    KpiDefinition(
        "by_status", "Fälle je Fallstatus",
        "Verteilung der Faelle auf den Ermittlungs-Status. Vokabular: "
        + ", ".join(_STATUSES) + ".",
        "stats_repo.py: by_status ueber cases.status; _STATUSES",
        "Anzahl Fälle je Status"),
    KpiDefinition(
        "by_priority", "Fälle je Priorität",
        "Verteilung der Faelle auf Prioritaetsstufen 1 (hoechste) bis 5.",
        "stats_repo.py: by_priority ueber cases.priority; _PRIORITIES",
        "Anzahl Fälle je Stufe"),
    KpiDefinition(
        "by_ampel", "Fälle je Ampel",
        "Verteilung der Faelle auf die Dringlichkeits-Ampel (rot/gelb/gruen). "
        "Die Ampel folgt der Inaktivitaets-Schwelle (Vorgabe 7 Tage -> gelb, "
        "21 Tage -> rot; konfigurierbar via config.yaml).",
        "dashboard_repo.py: classify_ampel; DEFAULT_AMPEL_THRESHOLDS 7/21",
        "Anzahl Fälle je Ampel"),
    KpiDefinition(
        "by_assignee", "Fälle je Ermittler",
        "Anzahl zugewiesener Faelle je Ermittler (Verteilungssicht).",
        "stats_repo.py: by_assignee ueber cases.assigned_to",
        "Anzahl Fälle je Person", _ZWECKBINDUNG),
    KpiDefinition(
        "throughput_by_day", "Durchsatz je Tag",
        "Anzahl Fall-Ereignisse je Kalendertag aus dem audit_log "
        "(target_type='case'). Aktivitaets-, kein Ergebnis-Mass.",
        "stats_repo.py: _throughput (audit_log, date(ts,'unixepoch'))",
        "Ereignisse je Tag", _ZWECKBINDUNG),
    # Status-Werte
    KpiDefinition(
        "status.open", "Status: offen",
        "Fall angelegt, Bearbeitung noch nicht begonnen.",
        "cases.status CHECK ('open'); m002_cases.py", "—"),
    KpiDefinition(
        "status.in_progress", "Status: in Bearbeitung",
        "Fall wird aktiv bearbeitet.",
        "cases.status CHECK ('in_progress')", "—"),
    KpiDefinition(
        "status.approved", "Status: freigegeben",
        "Ermittlungsergebnis abgenommen (approved_at gesetzt).",
        "cases.status CHECK ('approved'); CASE_APPROVED", "—"),
    KpiDefinition(
        "status.closed", "Status: abgeschlossen",
        "Fall abgeschlossen.",
        "cases.status CHECK ('closed')", "—"),
    # Prioritaets-Werte
    KpiDefinition(
        "priority.1", "Priorität 1 (höchste)",
        "Hoechste Dringlichkeit; steht in Sortierungen zuerst.",
        "cases.priority CHECK BETWEEN 1 AND 5", "—"),
    KpiDefinition(
        "priority.5", "Priorität 5 (niedrigste)",
        "Niedrigste Dringlichkeit.",
        "cases.priority CHECK BETWEEN 1 AND 5", "—"),
    # Ampel-Werte
    KpiDefinition(
        "ampel.rot", "Ampel rot",
        "Braucht Aufmerksamkeit: Inaktivitaet >= rote Schwelle (Vorgabe 21 "
        "Tage) oder unzugewiesen/ueberfaellig.",
        "dashboard_repo.py: classify_ampel (red_idle_days=21)", "—"),
    KpiDefinition(
        "ampel.gelb", "Ampel gelb",
        "Mittlere Inaktivitaet: >= gelbe Schwelle (Vorgabe 7 Tage), < rote.",
        "dashboard_repo.py: classify_ampel (amber_idle_days=7)", "—"),
    KpiDefinition(
        "ampel.gruen", "Ampel grün",
        "Aktiv oder abgeschlossen: unterhalb der gelben Schwelle.",
        "dashboard_repo.py: classify_ampel", "—"),
)


class KpiGlossary:
    """Zugriff + Vollstaendigkeitspruefung + HTML-Ausgabe des KPI-Glossars."""

    def __init__(self, entries: Tuple[KpiDefinition, ...] = KPI_GLOSSARY) -> None:
        self._entries = entries
        self._by_key: Dict[str, KpiDefinition] = {e.key: e for e in entries}
        if len(self._by_key) != len(entries):
            raise GlossaryError("Doppelte KPI-Schluessel im Glossar.")

    def all(self) -> List[KpiDefinition]:
        return list(self._entries)

    def get(self, key: str) -> Optional[KpiDefinition]:
        return self._by_key.get(key)

    def keys(self) -> List[str]:
        return list(self._by_key.keys())

    def verify_covers_stats(self) -> None:
        """
        Erzwingt Deckung zwischen Glossar und den real erzeugten Kennzahlen:
          * jede STATS_SECTION hat eine Definition,
          * jeder Status-, Prioritaets- (1 und 5 als Grenzwerte) und Ampel-Wert
            hat eine Definition.
        Fehlt etwas -> GlossaryIncompleteError mit Auflistung (GR1). Umgekehrt:
        jeder Glossar-Schluessel ist entweder eine bekannte Sektion oder ein
        bekannter Wert (kein Definitions-Waisenkind).
        """
        required = set(STATS_SECTIONS)
        for s in _STATUSES:
            required.add("status.%s" % s)
        for a in AMPEL_VALUES:
            required.add("ampel.%s" % a)
        # Prioritaet: Grenzwerte 1 und 5 sind definiert (Skala erklaert).
        required.add("priority.1")
        required.add("priority.5")

        have = set(self._by_key.keys())
        missing = sorted(required - have)
        if missing:
            raise GlossaryIncompleteError(
                "Kennzahlen ohne Definition: %s" % ", ".join(missing))

        # Kein Waisen-Schluessel: alles ist Sektion oder anerkannter Wert.
        allowed = set(required)
        for p in _PRIORITIES:
            allowed.add("priority.%s" % p)
        orphans = sorted(have - allowed)
        if orphans:
            raise GlossaryIncompleteError(
                "Glossar-Schluessel ohne Bezug: %s" % ", ".join(orphans))

    def to_html(self, context) -> str:
        """
        Self-contained Glossar-HTML mit einheitlichem Aktenkopf/Erzeugungs-
        vermerk/Pruefsumme (ExportEnvelope). Werte html-escaped, UTF-8 erhalten.
        Pruefsumme deckt die Definitionsliste (unabhaengig nachrechenbar).
        """
        import html
        from management.export.export_envelope import ExportEnvelope
        from management.export.checksum import json_payload_sha256

        env = ExportEnvelope(context)
        payload = [{"key": e.key, "label": e.label, "definition": e.definition,
                    "quelle": e.quelle, "einheit": e.einheit, "hinweis": e.hinweis}
                   for e in self._entries]
        digest = json_payload_sha256(payload)

        rows = []
        for e in self._entries:
            hinweis = ("<div class=\"aiw-hinweis\">%s</div>" % html.escape(e.hinweis)
                       if e.hinweis else "")
            rows.append(
                "<tr><td><code>%s</code></td><td>%s</td>"
                "<td>%s%s</td><td>%s</td><td><code>%s</code></td></tr>"
                % (html.escape(e.key), html.escape(e.label),
                   html.escape(e.definition), hinweis,
                   html.escape(e.einheit), html.escape(e.quelle)))

        return (
            "<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n"
            "<meta charset=\"utf-8\">\n"
            "<title>AIW — Kennzahlen-Glossar</title>\n"
            "<style>table{border-collapse:collapse}td,th{border:1px solid "
            "#ccc;padding:6px;vertical-align:top;text-align:left}"
            ".aiw-hinweis{color:#8a5a00;font-size:.9em;margin-top:4px}"
            ".aiw-export-band{background:#1F4E79;color:#fff;padding:8px}"
            "</style>\n</head>\n<body>\n"
            + env.classification_band_html()
            + "<h1>Kennzahlen-Glossar</h1>\n"
            "<table>\n<thead><tr><th>Schlüssel</th><th>Kennzahl</th>"
            "<th>Definition</th><th>Einheit</th><th>Beleg</th></tr></thead>\n"
            "<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>\n"
            + env.footer_html(digest)
            + "</body>\n</html>\n"
        )
