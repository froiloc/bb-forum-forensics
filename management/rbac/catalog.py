# =============================================================================
# management/rbac/catalog.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   WAHRHEITSQUELLE IM CODE fuer den RBAC-Katalog — die Menge der gueltigen
#   Rollen und Faehigkeiten. Die Datenbank (coordinator.db, Tabellen rbac_role /
#   rbac_capability) wird aus DIESEM Katalog geseedet, damit die FK-Integritaet
#   von rbac_grant/person_role gesichert ist (Beleg: Bauplan B7 v1.1 §11.3:
#   "Katalog ... ist im Code die Wahrheitsquelle, in der DB geseedet").
#
# Verhaeltnis zur Migration (WICHTIG, m005-Prinzip):
#   Die Seed-Migration m006_rbac_schema.py haelt eine EIGENE, EINGEFRORENE Kopie
#   dieser Werte. Sie importiert catalog.py NICHT — eine bereits angewandte
#   Migration darf ihr Laufzeitverhalten nie aendern (sonst Nichtdeterminismus
#   trotz gleicher Checksumme). Die Bruecke zwischen beiden ist der Test R02
#   (tests/test_management_rbac_schema.py): er verankert "m006-Seed == catalog.py"
#   ZUR BAUZEIT. Waechst der Katalog spaeter, seedet eine NEUE Migration die
#   Differenz; die Laufzeit-Invariante "jede Code-Capability existiert in der DB"
#   (Grundregel 1) setzt die Durchsetzungsschicht (Schnitt c) beim Start durch.
#
# Erweiterungsregel:
#   Codes sind stabile Bezeichner (wie audit event_type) — sie werden ERGAENZT,
#   niemals umbenannt oder wiederverwendet. Ein Umbenennen wuerde bestehende
#   Grants/Rollenzuweisungen forensisch entwerten.
#
# Version: v0.7.343 · Build: 343 · 2026-07-10
# =============================================================================

from typing import FrozenSet, NamedTuple, Tuple


class Role(NamedTuple):
    """Eine RBAC-Rolle: stabiler Code + Anzeigelabel."""

    code: str
    label: str


class Capability(NamedTuple):
    """Eine RBAC-Faehigkeit: stabiler Code + Label + Kurzbeschreibung."""

    code: str
    label: str
    description: str


# --- Rollensatz (Beleg: Bauplan B7 v1.1 §11.1.2) -----------------------------
#   supervisor, investigator, support, admin, lector, searchagent.
#   Mehrfachrollen sind moeglich (person_role ist eine n:m-Zuordnung).
ROLES: Tuple[Role, ...] = (
    Role("supervisor", "Chef-Ermittlerin / Aufsicht"),
    Role("investigator", "Ermittler:in"),
    Role("support", "Support / Mentoring (Live-Beistand)"),
    Role("admin", "Plattform-Administration"),
    Role("lector", "Gegenleser:in (Bericht vor StA-Uebergabe)"),
    Role("searchagent", "Recherche mit Volltextsuche"),
)


# --- Faehigkeitskatalog (Beleg: Bauplan B7 v1.1 §11.3, VOLLE Aufzaehlung) -----
#   15 Faehigkeiten. Der Katalog ist erweiterbar; hier die zur Bauzeit von 343
#   festgelegte Grundmenge. Die role->capability-ZUWEISUNGEN (Grants mit Scope)
#   sind NICHT Teil dieses Katalogs und NICHT Teil von Schnitt (a) — sie werden
#   in Schnitt (b) ueber die auditierte policy_admin-CLI vergeben (default-deny;
#   rbac_grant.audit_seq koppelt je Grant an audit_log, wie case_events).
CAPABILITIES: Tuple[Capability, ...] = (
    Capability("dashboard.view", "Ampel-Dashboard sehen",
               "Falluebersicht mit Ampel und Kennzahlen lesen."),
    Capability("assignment.edit", "Zuweisungen bearbeiten",
               "Faelle Ermittler:innen zuweisen/entziehen."),
    Capability("mentoring.view", "Mentoring-/Support-Sicht",
               "Laufende Support-Sitzungen und Beistands-Uebersicht sehen."),
    Capability("reports.review", "Berichte gegenlesen",
               "Ermittlungsberichte vor StA-Uebergabe pruefen (Vier-Augen)."),
    Capability("reports.approve", "Berichte freigeben",
               "Finale Freigabe eines Berichts (StA-Uebergabe)."),
    Capability("stats.export_sta", "StA-Statistik exportieren",
               "Gerichtsfeste Statistik-/Kennzahl-Exporte fuer die StA."),
    Capability("workload.view", "Lastverteilung sehen",
               "Ermittler-Auslastung und Verteilungsuebersicht lesen."),
    Capability("support_history.view", "Support-Historie sehen",
               "Abgeschlossene Support-Sitzungen und Verlauf lesen."),
    Capability("mycases.view", "Eigene Faelle sehen",
               "Die dem eigenen Konto zugewiesenen Faelle lesen."),
    Capability("myhistory.view", "Eigene Historie sehen",
               "Den eigenen Ereignis-/Taetigkeitsverlauf lesen."),
    Capability("policy.view", "RBAC-Richtlinie einsehen",
               "Rollen, Faehigkeiten und Grants (die RBAC-Matrix) lesen."),
    Capability("evidence.fulltext_search", "Volltextsuche (Beweismittel)",
               "Falluebergreifende Volltextsuche (staerkstes Kapselungsmodell, "
               "Welle 3)."),
    Capability("feedback.moderate", "Plattform-Feedback moderieren",
               "Bug-/Feedback-Tickets moderieren und freigeben."),
    Capability("capacity.edit", "Kapazitaet pflegen",
               "Arbeitszeit-/Verfuegbarkeitsdaten fuer Prognose/Gantt pflegen."),
    Capability("ops.view", "Betriebs-/Systemzustand sehen",
               "Backup-/Speicher-/Integritaets-Status der Anlage lesen."),
)


#: Nur die Codes — fuer schnelle Konsistenz-Checks (Seed == Katalog, Start-Check).
ROLE_CODES: FrozenSet[str] = frozenset(r.code for r in ROLES)
CAPABILITY_CODES: FrozenSet[str] = frozenset(c.code for c in CAPABILITIES)


def role_codes() -> FrozenSet[str]:
    """Menge aller gueltigen Rollen-Codes (Wahrheitsquelle im Code)."""
    return ROLE_CODES


def capability_codes() -> FrozenSet[str]:
    """Menge aller gueltigen Faehigkeits-Codes (Wahrheitsquelle im Code)."""
    return CAPABILITY_CODES
