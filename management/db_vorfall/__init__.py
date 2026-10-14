# =============================================================================
# management/db_vorfall/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Register "Datenbank-Vorfaelle" (Build 777)
# =============================================================================
# Zweck:
#   Paket fuer das zentrale Register der Datenbankvorfaelle (Tabelle
#   db_vorfall in coordinator.db, M041):
#
#     DbVorfallMeldung  — ein Vorfall, wie ihn der Erkennende beschreibt
#     DbVorfallRepo     — Lesen und auditiertes Schreiben (CoordinatorWriter)
#     DbVorfallPuffer   — Ablage, wenn coordinator.db nicht erreichbar ist
#     DbVorfallMelder   — Eintragen ODER Puffern; Nachtragen des Puffers
#     MeldeErgebnis     — was beim Melden geschah
#     DbVorfallFehler   — unzulaessiger Schreibwunsch
#
#   Der erste Melder ist die Startpruefung der evidence_<uid>.db im Webserver
#   (Build 778). Die Sicht im Management (Recht ops.view, Pruefen mit
#   wartung.durchfuehren) liest das Register.
#
# Version: v0.8.777 · Build: 777 · 2026-10-14
# =============================================================================
