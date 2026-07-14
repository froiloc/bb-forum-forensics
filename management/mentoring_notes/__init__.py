# =============================================================================
# management/mentoring_notes/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Paketmarker fuer die BETREUUNGS-NOTIZEN ("Post-its") der Ermittler-Betreuung
#   (Build 401, Welle 1). Arbeits-/Organisationsnotizen der Leitung zu den
#   Belangen einzelner Mitarbeiter — KEINE Ermittlungsdaten ueber Beschuldigte.
#
#   Schreibpfade laufen ausschliesslich ueber das CoordinatorWriter-Gateway
#   (fachlicher Write + audit_log-Beleg atomar). Loeschen findet nur ueber ein
#   'archived_at'-Flag statt (wiederherstellbar); es gibt KEIN physisches
#   Loeschen. Freitexte gehen nie in den audit_log-Payload (Sensibilitaetsregel).
#
# Version: v0.7.401 · Build: 401 · 2026-07-13
# =============================================================================
