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
#   (excel_case_status). Build 442 ruestet die bestehenden Sichten-Exporte
#   (dashboard/workload/support_overview) auf den einheitlichen Rahmen um
#   (classification_band + Erzeugungsvermerk/Pruefsumme) via context_builder.
#   Build 443 ergaenzt das StA-Ausschleus-Verzeichnis (staging.StagingArea):
#   gepruefte Uebergabe mit Unbedenklichkeitsvermerk (Fallregel 3), Manifest,
#   Pruefsummen je Artefakt und Selbstverifikation.
#
# Version: v0.7.443 · Build: 443 · 2026-07-19
# =============================================================================

from management.export.checksum import (
    content_sha256_bytes,
    content_sha256_text,
    canonical_rows_sha256,
    json_payload_sha256,
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
from management.export.context_builder import build_export_context
from management.export.staging import (
    StagingArea,
    StagingError,
    UnbedenklichkeitError,
)

__all__ = [
    "content_sha256_bytes",
    "content_sha256_text",
    "canonical_rows_sha256",
    "json_payload_sha256",
    "ExportContext",
    "ExportEnvelope",
    "build_case_status_xlsx",
    "case_rows_digest",
    "CASE_STATUS_COLUMNS",
    "ExcelUnavailable",
    "build_export_context",
    "StagingArea",
    "StagingError",
    "UnbedenklichkeitError",
]
