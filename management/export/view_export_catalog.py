# =============================================================================
# management/export/view_export_catalog.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck (Idee 5, Build 511):
#   Der KATALOG der exportierbaren Cockpit-Sichten. Er ist die einzige Stelle,
#   an der steht, welche Sicht aus welchem lesenden Endpunkt gespeist wird.
#
# WAS HIER BEWUSST NICHT STEHT: Spaltenlisten. Die Spalten leitet der Renderer
#   aus den DATEN ab (siehe view_export_spec.py). Ein 'sections'-Eintrag ist
#   damit reine KOSMETIK — er gibt einem bekannten Abschnitt eine deutsche
#   Ueberschrift und zieht wichtige Felder nach vorn. Ist 'sections' LEER,
#   rendert der Renderer AUTOMATISCH alle Top-Level-Schluessel der Antwort.
#   Dadurch ist der Export auch fuer die Sichten vollstaendig, deren Antwort
#   hier nicht im Einzelnen beschrieben ist — und er bleibt vollstaendig, wenn
#   ein Endpunkt spaeter ein Feld ergaenzt (Grundregel 1: nichts still
#   auslassen).
#
# RECHTE: Hier steht KEINE Faehigkeit. Der Export ruft 'api_path' ueber den
#   bestehenden dispatch() auf und erbt dessen Rechtepruefung, Scope und
#   Fehlerbilder. Ein zweiter Rechtepfad koennte abdriften — dieser kann es
#   konstruktiv nicht.
#
# NICHT IM KATALOG (bewusst, kein stiller Verzicht):
#   - 'notes'   — Betreuungs-Notizen sind ARBEITSNOTIZEN der Leitung und
#                 ausdruecklich KEINE Ermittlungsdaten (Beleg event_types.py
#                 Build 401). Sie gehoeren nicht in eine Akte. Auf Wunsch der
#                 Chef-Ermittlerin in einer Zeile nachruestbar.
#   - 'lectorate'/'approval' — beide arbeiten auf /api/reports, das ueber die
#                 Sicht 'reports' bereits exportierbar ist; ein zweiter,
#                 inhaltsgleicher Export haette nur Verwirrung gestiftet.
#   Alle uebrigen Sichten des VIEW_CATALOG sind erfasst (Test VE08 prueft das
#   gegen cockpit.js, damit eine kuenftige neue Sicht nicht still durchfaellt).
#
# Version: v0.8.511 · Build: 511 · 2026-07-24
# =============================================================================

from __future__ import annotations

from typing import Dict, Optional, Tuple

from management.export.view_export_spec import SectionSpec, ViewExportSpec

#: Hinweis fuer die vier Sichten, die bereits einen SPEZIALexport haben. Der
#  Akten-Export ersetzt ihn nicht — er ist die statische, druckbare Fassung.
_HAT_SPEZIALEXPORT = (
    "Für diese Sicht existiert zusätzlich ein interaktiver Spezialexport "
    "(siehe Übergabe AP-2B). Dieses Dokument ist die statische Aktenfassung."
)

VIEW_EXPORTS: Tuple[ViewExportSpec, ...] = (
    ViewExportSpec(
        view_id="dashboard", label="Ampel-Dashboard — Fall-Übersicht",
        api_path="/api/overview", note=_HAT_SPEZIALEXPORT,
        sections=(SectionSpec("cases", "Fälle",
                              order=("subject_id", "status", "ampel",
                                     "ampel_reason", "prioritaet",
                                     "zugewiesen_an")),),
    ),
    ViewExportSpec(
        view_id="calendar", label="Kalender & Wiedervorlage",
        api_path="/api/external",
        sections=(SectionSpec("matters", "Externe Vorgänge"),),
    ),
    ViewExportSpec(
        view_id="assignment", label="Zuweisung — zuweisbare Fälle",
        api_path="/api/assignable",
        sections=(SectionSpec("cases", "Fälle"),
                  SectionSpec("investigators", "Ermittler:innen")),
    ),
    ViewExportSpec(
        view_id="cases", label="Fall-Erkennung",
        api_path="/api/cases/detect", sections=(),
    ),
    ViewExportSpec(
        view_id="mentoring", label="Ermittler-Betreuung",
        api_path="/api/mentoring",
        sections=(SectionSpec("sessions", "Sitzungen"),),
    ),
    ViewExportSpec(
        view_id="reports", label="Berichts-Abnahme",
        api_path="/api/reports", sections=(),
    ),
    ViewExportSpec(
        view_id="templates", label="Platzhalter & Queries",
        api_path="/api/templates/placeholders",
        sections=(SectionSpec("placeholders", "Platzhalter"),),
    ),
    ViewExportSpec(
        view_id="doctemplates", label="Dokumentvorlagen",
        api_path="/api/templates/documents",
        sections=(SectionSpec("documents", "Vorlagen"),),
    ),
    ViewExportSpec(
        view_id="modules", label="Baustein-Module",
        api_path="/api/templates/modules",
        sections=(SectionSpec("modules", "Module"),),
    ),
    ViewExportSpec(
        view_id="results", label="Ermittlungsergebnis — Abdeckung",
        api_path="/api/results/coverage", sections=(),
    ),
    ViewExportSpec(
        view_id="stats", label="Statistiken (StA/Führung)",
        api_path="/api/stats", sections=(),
    ),
    ViewExportSpec(
        view_id="planung", label="Prognose (3 Szenarien)",
        api_path="/api/forecast", sections=(),
    ),
    ViewExportSpec(
        view_id="annostats", label="Annotations-Statistik",
        api_path="/api/annotation-stats", sections=(),
    ),
    ViewExportSpec(
        view_id="workload", label="Lastverteilung",
        api_path="/api/workload", note=_HAT_SPEZIALEXPORT,
        # Build 513 (AP-2F/Idee 21): die Ueberlastwarnung gehoert MIT in die
        # Akte. Sie waere ueber den Auto-Modus (Regel 2) ohnehin unter
        # 'Weitere Daten' erschienen; hier bekommt sie einen benannten Platz in
        # der Reihenfolge, in der man sie liest: erst der Alarm, dann die Last.
        sections=(
            SectionSpec("overload", "Überlastwarnung (Schwellen und Zähler)"),
            SectionSpec("overload_assessments", "Überlast je Ermittler:in"),
            SectionSpec("loads", "Last je Ermittler:in"),
        ),
    ),
    # Build 516 (AP-2G / Idee 23): die Eskalationsliste ist ein Beleg fuer die
    # Leitung ("dies lag zu diesem Zeitpunkt an") und gehoert damit in die
    # Akte. Die Schwellen bekommen einen EIGENEN, benannten Abschnitt VOR den
    # Meldungen: ohne den Massstab ist keine der Meldungen nachrechenbar.
    ViewExportSpec(
        view_id="escalation", label="Eskalationen",
        api_path="/api/escalations",
        sections=(
            SectionSpec("thresholds", "Angewandter Maßstab"),
            SectionSpec("items", "Gemeldete Eskalationen"),
        ),
    ),
    # Build 519 (AP-2F / Idee 22): die Arbeitsschlange belegt, was zu einem
    # bestimmten Zeitpunkt anstand. Sie hat KEINEN eigenen Abschnitt fuer den
    # Umfang - 'scope'/'granted_scope' erscheinen ueber den Auto-Modus
    # (Regel 2) unter 'Weitere Daten' und stehen zusaetzlich im Dokumentkopf.
    ViewExportSpec(
        view_id="nextactions", label="Nächstbeste Aktion",
        api_path="/api/next_actions",
        sections=(SectionSpec("items", "Arbeitsschlange"),),
    ),
    ViewExportSpec(
        view_id="capacity", label="Kapazität",
        api_path="/api/capacity", requires=("start",),
        sections=(SectionSpec("capacities", "Kapazitäten"),),
    ),
    ViewExportSpec(
        view_id="support", label="Support-Historie",
        api_path="/api/support", note=_HAT_SPEZIALEXPORT,
        sections=(SectionSpec("sessions", "Support-Sitzungen"),),
    ),
    ViewExportSpec(
        view_id="mycases", label="Meine Aufträge",
        api_path="/api/mycases",
        sections=(SectionSpec("cases", "Fälle"),),
    ),
    ViewExportSpec(
        view_id="myhistory", label="Meine Historie",
        api_path="/api/myhistory", sections=(),
    ),
    ViewExportSpec(
        view_id="policy", label="Rechte / Policy",
        api_path="/api/policy", sections=(),
    ),
    ViewExportSpec(
        view_id="integrity", label="Integrität / Betrieb",
        api_path="/api/integrity", sections=(),
    ),
    ViewExportSpec(
        view_id="audit", label="Audit-/Revisions-Explorer",
        api_path="/api/audit",
        note=("Für den Audit-Explorer existiert der gerichtsfeste Spezialexport "
              "GET /api/audit/export mit eigener Filterbeschreibung "
              "(Build 467). Dieses Dokument ist die Aktenfassung der aktuell "
              "angezeigten Seite."),
        sections=(SectionSpec("rows", "Belege"),),
    ),
    ViewExportSpec(
        view_id="promotion", label="Fremdforum-Promotion",
        api_path="/api/promotion",
        sections=(SectionSpec("candidates", "Kandidaten"),
                  SectionSpec("decisions", "Entscheidungen")),
    ),
    ViewExportSpec(
        view_id="releases", label="Externe Fallfreigabe",
        api_path="/api/releases",
        sections=(SectionSpec("releases", "Freigaben"),
                  SectionSpec("recipients", "Empfänger (AD)")),
    ),
    ViewExportSpec(
        view_id="onboarding", label="Onboarding / Offboarding",
        api_path="/api/onboarding", requires=("person_id",),
        sections=(SectionSpec("steps", "Checklisten-Schritte"),),
    ),
    ViewExportSpec(
        view_id="personnel", label="Personalverwaltung",
        api_path="/api/personnel", sections=(),
    ),
    ViewExportSpec(
        view_id="crossref", label="Kreuzbezug — identifizierte Personen",
        api_path="/api/crossref",
        sections=(SectionSpec("entries", "Katalog",
                              order=("subject_id", "real_identity",
                                     "confidence_code", "basis")),),
    ),
    ViewExportSpec(
        view_id="crossfindings", label="Querfunde",
        api_path="/api/crossfindings",
        sections=(SectionSpec("findings", "Querfunde",
                              order=("id", "subject_id", "source_name",
                                     "status", "feedback_status",
                                     "feedback_reason")),),
    ),
    ViewExportSpec(
        view_id="alias", label="Aliasse — globaler Namenskatalog",
        api_path="/api/alias",
        sections=(SectionSpec("entries", "Aliasse",
                              order=("subject_id", "alias", "kind_code",
                                     "basis", "is_active",
                                     "retracted_reason")),),
    ),
    ViewExportSpec(
        view_id="merge", label="Identitäts-Gruppen",
        api_path="/api/merge",
        sections=(SectionSpec("entries", "Zusammenführungen",
                              order=("primary_subject_id",
                                     "merged_subject_id", "confidence_code",
                                     "basis", "is_active", "split_reason")),),
    ),
)

#: Schneller Zugriff nach view_id.
_BY_ID: Dict[str, ViewExportSpec] = {s.view_id: s for s in VIEW_EXPORTS}


def spec_for(view_id: str) -> Optional[ViewExportSpec]:
    """Die Spec einer Sicht oder None (unbekannte/nicht exportierbare Sicht)."""
    return _BY_ID.get(str(view_id or ""))


def known_view_ids() -> Tuple[str, ...]:
    """Alle exportierbaren view_ids in Katalogreihenfolge (fuer 404-Meldung)."""
    return tuple(s.view_id for s in VIEW_EXPORTS)
