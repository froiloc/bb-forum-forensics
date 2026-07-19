# =============================================================================
# management/export/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck (Idee 1, Ideen_Verwaltungswerkzeug_konsolidiert.md §2.8):
#   Gemeinsame, wiederverwendbare Schicht fuer ALLE Management-Exporte
#   (Fallstatus-Excel, Akten-Export je Sicht, StA-Ausschleus, Audit-Explorer-
#   Export). Sie liefert den EINHEITLICHEN Aktenkopf, den Erzeugungsvermerk
#   (wer/wann/welche Buildnummer/Integritaets-Kettenspitze) und die Pruefsumme
#   des Nutzinhalts — damit jeder erzeugte Beleg gerichtsfest zuordenbar und
#   unabhaengig nachpruefbar ist.
#
#   Build 440 legt das Fundament (checksum + ExportEnvelope, rein additiv).
#   Build 441 ergaenzt das erste Format: Fallstatus -> Excel
#   (excel_case_status). Weitere Exporte (B442 Retrofit je Sicht, B443 StA-
#   Ausschleus) docken hier an.
#
# Version: v0.7.441 · Build: 441 · 2026-07-19
# =============================================================================

from management.export.checksum import (
    content_sha256_bytes,
    content_sha256_text,
    canonical_rows_sha256,
)
from management.export.export_envelope import (
    ExportContext,
    ExportEnvelope,
)
from management.export.excel_case_status import (
    build_case_status_xlsx,
    case_rows_digest,
    CASE_STATUS_COLUMNS,
    ExcelUnavailable,
)

__all__ = [
    "content_sha256_bytes",
    "content_sha256_text",
    "canonical_rows_sha256",
    "ExportContext",
    "ExportEnvelope",
    "build_case_status_xlsx",
    "case_rows_digest",
    "CASE_STATUS_COLUMNS",
    "ExcelUnavailable",
]
