# management.maintenance — Wartungswerkzeuge für die Produktivumgebung.
#
# Enthält Werkzeuge, die NICHT im normalen Request-Pfad des Webservers
# laufen, sondern administrativ/einmalig aufgerufen werden (CLI). Aktuell:
#   - default_db_merger.DefaultDbMerger:
#       Konsolidiert mehrere (versehentlich pro Beschuldigtem angelegte)
#       default.db-Dateien verlustfrei in eine zentrale default.db.
#
# Beleg: Projektgespräch 2026-07-01 (mc), Analyse default.db-Konsolidierung.
