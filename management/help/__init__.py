# =============================================================================
# management/help/__init__.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H1)
# =============================================================================
# Zweck:
#   Das HILFE-REGISTER: die eine Quelle, aus der sich alle drei Hilfesysteme
#   speisen (Konzept_Hilfesysteme §2.1):
#     * Kontexthilfe  - "Was ist dieses Element hier?"   (Popup im Cockpit)
#     * Vollhilfe     - "Wie und warum arbeite ich mit dieser Sicht?" (/help)
#     * CLI-Hilfe     - "Welches Werkzeug nehme ich, und wie gefahrlos?"
#
#   WARUM EINE QUELLE (gesicherte Erkenntnis, Konzept §2.1): Nur gegen genau
#   EINEN Bestand laesst sich Vollstaendigkeit maschinell pruefen, nur so
#   koennen Verweise nicht ins Leere zeigen, und nur so gibt es keinen Drift
#   zwischen dem, was das Popup sagt, und dem, was das Handbuch sagt.
#
#   ARCHITEKTURVORBILD ist das Kennzahlen-Glossar (management/stats/
#   glossary.py mit verify_covers_stats()): reine Daten + reine Funktionen,
#   kein DB-, Netz- oder Uhrzugriff, dafuer eine harte Vollstaendigkeits-
#   pruefung, die eine Luecke BENENNT statt sie still zu uebergehen
#   (Grundregel 1).
#
# Bestandteile:
#   sicht_katalog.py - Python-Spiegel des VIEW_CATALOG (43 Sichten)
#   modell.py        - die Datenklassen der Hilfetexte
#   pruefung.py      - die Vollstaendigkeits- und Verweispruefungen
#   inhalt/          - die Hilfetexte selbst, je Nav-Gruppe eine Datei
#
# REGEL H-0 (hart, Konzept §4.1): Kein Hilfetext enthaelt Falldaten, echte
#   UIDs, echte Kontonamen oder echte Personennamen. Beispiele sind erkennbar
#   fiktiv. Begruendung: die Vollhilfe ist druckbar, und Ausdrucke wandern.
#   pruefung.verify_fallinhaltsfrei() ist das maschinelle Netz dagegen; die
#   eigentliche Sicherung bleibt redaktionell (Vier-Augen).
#
# Version: v0.8.588 - Build: 588 - 2026-07-31
# =============================================================================

from __future__ import annotations

# Bewusst KEINE Re-Exporte der Inhalte hier: das Register wird ueber
# management.help.inhalt.lade_register() geholt, damit die Ladereihenfolge
# an genau einer Stelle steht und Testfaelle ein eigenes Register bauen
# koennen, ohne das Auslieferungsregister zu beruehren.

__all__ = ["sicht_katalog", "modell", "pruefung", "inhalt"]
