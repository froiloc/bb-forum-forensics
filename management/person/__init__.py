# management.person — Ermittlerstammdaten (Tabelle 'person') + auditierte
# Verwaltungs-CLI (Baustelle 7). Anlegen/Ändern ausschließlich über das
# CoordinatorWriter-Gateway; kein Roh-SQL-Direktzugriff mehr nötig.
#
# Build 342 (Welle 0): umbenannt aus management.investigators. Die Tabelle
# 'investigators' wurde per Migration m005 verlustfrei nach 'person' umbenannt;
# Klasse InvestigatorsRepo -> PersonRepo. Rollen-Flags is_investigator/
# is_supervisor/is_support bleiben als kosmetische Leser erhalten.
