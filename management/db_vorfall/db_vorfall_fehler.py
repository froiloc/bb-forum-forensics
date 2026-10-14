# =============================================================================
# management/db_vorfall/db_vorfall_fehler.py
# IT-Forensisches Ermittlungswerkzeug — Register "Datenbank-Vorfaelle" (Build 777)
# =============================================================================
# Zweck:
#   Fehlerklasse des Registers: ein Schreibwunsch ist unzulaessig (unbekannte
#   Art oder unbekanntes Ergebnis, fehlende handelnde Person, fehlendes Recht,
#   Vorfall unbekannt oder schon geprueft, Widerspruch beim Nachtrag). Die
#   Meldung ist fuer Protokoll und Antwort des Endpunkts bestimmt.
#
# Version: v0.8.777 · Build: 777 · 2026-10-14
# =============================================================================


class DbVorfallFehler(Exception):
    """Ein Schreibwunsch an das Register ist unzulaessig."""
