# =============================================================================
# management/search/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E)
# =============================================================================
# Zweck:
#   Paketmarke fuer AP-3E (falluebergreifende Volltextsuche). Bewusst LEER bis
#   auf diesen Kopf: ein __init__.py, das Untermodule importiert, zieht beim
#   ersten Zugriff die ganze Kette nach — und der Indexbau soll auch dann
#   laufen, wenn der Management-Server nicht gestartet ist (CLI-Betrieb).
#
# Einordnung (Entscheidungen mc 2026-07-26,
#   management/Entscheidungen_2026-07-26_AP3B_AP3C_AP3E.md §1):
#     * Modell B, zweistufig (Trefferlage frei, Inhalt gebunden).
#     * evidence.fulltext_search ist NICHT scope-faehig, default-deny.
#     * Zweckangabe bei JEDER Abfrage, als Auswahlliste codierter Zwecke.
#
# GRUNDSATZ DIESES PAKETS — HILFSMITTEL, KEIN BEWEISMITTEL:
#   Der FTS5-Index in search_index.db ist jederzeit verwerfbar und wird NIE
#   zitiert. Jeder Treffer wird vor der Anzeige gegen die Quelle
#   (evidence_<uid>.db) verifiziert. Dieselbe Einordnung wie evidence_scan_cache
#   (m009:21-25). Beleg: Klaerung_AP3E_..._v0_2.md §6 Nr. 3.
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================
