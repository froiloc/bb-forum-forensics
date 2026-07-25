# =============================================================================
# management/deadlines/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Zweck (Idee 32 — Fristen-/Verjährungs-Monitor je Fall):
#   Dieses Paket beantwortet EINE Frage: wieviel Zeit bleibt in einem Fall,
#   bevor die Verfolgungsverjaehrung (§§ 78 ff. StGB) rechnerisch eintritt.
#
# WARUM DAS PAKET IN DREI SCHICHTEN GETEILT IST (Grundregel 10):
#   limitation_params.json — die PARAMETER. Daten, kein Code. Je Eintrag eine
#                            Fundstelle und eine Gueltigkeitsspanne. Nur diese
#                            Datei aendert sich, wenn sich das Recht aendert.
#   limitation_params.py   — die LADESCHICHT. Sie prueft die Parameter gegen
#                            § 78 Abs. 3 StGB nach (die Frist wird aus der
#                            Hoechststrafe NACHGERECHNET) und verweigert einen
#                            in sich widerspruechlichen Satz.
#   limitation.py          — die BERECHNUNG. Reine Funktionen, keine Datei,
#                            keine Datenbank, keine Uhr.
#   limitation_repo.py     — (Build 524) die Tatzeit je Fall aus den
#                            forensic_<uid>.db, rein lesend.
#
# DIE WICHTIGSTE GRENZE DIESES PAKETS:
#   Es stellt KEINE Verjaehrung fest. Es rechnet eine Frist und benennt jede
#   Annahme, die dabei eingeht. Ist der Parametersatz nicht als BESTAETIGT
#   gekennzeichnet, verweigert es die Aussage und nennt den Grund — statt eine
#   unbestaetigte Rechtsfolge zu behaupten.
#
# Version: v0.8.523 · Build: 523 · 2026-07-25
# =============================================================================
