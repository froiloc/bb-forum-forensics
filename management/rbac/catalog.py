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
    # --- Build 420 (SF-4, Vermaehlung B6xB7): Authoring-Werkzeuge W1/W2/W3 ---
    #   Redakteur:in pflegt die Berichtsvorlagen/Bausteine/Platzhalter in
    #   templates.db (auditiert ueber den TemplatesWriter, Build 421). Die
    #   Chef-Ermittlerin erhaelt das Recht ueblicherweise ebenfalls (Grant).
    Role("template_editor", "Redakteur:in (Berichtsvorlagen/Bausteine)"),
    # --- Wartungsmodus (Sequenz A-D, Builds 435-438): Betriebsstillstand ------
    #   Wer die Wartungs-Werkzeuge (enter/exit/kill) bedienen darf. Die
    #   Chef-Ermittlerin (supervisor) erhaelt das Recht ueblicherweise ebenfalls
    #   (Grant ueber policy_admin; mc 2026-07-19).
    Role("maintenance", "Wartung / kontrollierter Betriebsstillstand"),
)


# --- Faehigkeitskatalog (Beleg: Bauplan B7 v1.1 §11.3, VOLLE Aufzaehlung) -----
#   21 Faehigkeiten (15 ab Build 343, +2 ab 385, +2 ab 387, +2 ab 401). Der Katalog ist
#   erweiterbar; hier die zur Bauzeit von 343
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
    # --- Build 460: Fremdforum-Promotion (Seed in M015) ---------------------
    #   Schreibrecht auf die Promotions-Entscheidung ueber Fremdforum-Kandidaten
    #   (forensic_<uid>.db vorhanden, evidence fehlt). Der Schreibpfad ist
    #   auditiert (PromotionRepo ueber CoordinatorWriter). NICHT scope-behaftet:
    #   die Entscheidung, ob ein Kandidat in die Ermittlung uebernommen wird, ist
    #   eine Leitungshandlung, kein fallgebundener Vorgang. Das LESEN der Sicht
    #   haengt an 'ops.view' (wie die data/-Uebersicht, Build 454). Der Grant an
    #   'supervisor' ist eine operative Entscheidung der Chef-Ermittlerin
    #   (policy_admin), NICHT Teil dieses Builds (default-deny; mc 2026-07-20).
    Capability("ops.promote", "Fremdforum-Kandidaten entscheiden",
               "Fremdforum-Kandidaten uebernehmen, zurueckstellen oder als "
               "fremdzustaendig einstufen (auditiert)."),
    # --- Build 462: Externe Fallfreigabe (Seed in M016) ---------------------
    #   Weitergabe eines Falls an einen bestaetigten NRW-Ermittler (AD-ACL, F4)
    #   nach Unbedenklichkeitspruefung (Fallregel 3), auditiert. NICHT scope-
    #   behaftet: die externe Weitergabe ist eine Leitungshandlung. Lesen und
    #   Erteilen/Widerrufen sind getrennt (Vier-Augen bleibt moeglich). Grants an
    #   'supervisor' per policy_admin (default-deny; mc 2026-07-20).
    Capability("release.view", "Externe Fallfreigaben sehen",
               "Externe Fallfreigaben an NRW-Ermittler (Empfaenger, Umfang, "
               "Zustand) lesen."),
    Capability("release.grant", "Externe Fallfreigabe erteilen/widerrufen",
               "Einen Fall an einen bestaetigten NRW-Ermittler freigeben oder "
               "eine Freigabe widerrufen (auditiert, Unbedenklichkeit Pflicht)."),
    # --- Build 385: Wiedervorlage externer Vorgaenge (Seed in M010) ---------
    #   BEIDE sind scope-faehig ('alle' = alle Faelle, 'eigene' = nur die mir
    #   zugewiesenen). Der Ermittler bekommt 'eigene' und pflegt die Vorgaenge
    #   seines eigenen Falls selbst — sonst waere die Chef-Ermittlerin das
    #   Nadeloehr fuer jede Providerauskunft (mc 2026-07-12).
    Capability("external.view", "Externe Vorgaenge sehen",
               "Wiedervorlage externer Vorgaenge (Beschluesse, Auskuenfte) "
               "lesen."),
    Capability("external.edit", "Externe Vorgaenge pflegen",
               "Externe Vorgaenge anlegen, wiedervorlegen und abschliessen."),
    # --- Build 387: Ermittlungsergebnis-Bewertung (Seed in M011) ------------
    #   Eigene Faehigkeiten (mc 2026-07-12): das Erfassen und Ansehen der
    #   EIGENEN Bewertung ('eigene') hat eine andere Qualitaet als die
    #   fallübergreifende statistische Auswertung ('alle').
    Capability("results.view", "Ermittlungsergebnis sehen",
               "Bewertung des Ermittlungsergebnisses (Konfidenz/Qualitaet) "
               "lesen."),
    Capability("results.edit", "Ermittlungsergebnis bewerten",
               "Bewertungen des Ermittlungsergebnisses erfassen (append-only)."),
    # --- Build 401: Betreuungs-Notizen ("Post-its", Seed in M012) -----------
    #   Arbeitsnotizen der Leitung zu den Belangen einzelner Mitarbeiter (KEINE
    #   Ermittlungsdaten). Sichtbarkeit: privates Board pro Autor:in; eine
    #   Vertretung/Aufsicht mit Scope 'alle' sieht fremde Boards. Die Grants
    #   sind eine operative Entscheidung der Chef-Ermittlerin (mc 2026-07-13).
    Capability("mentoring_notes.view", "Betreuungs-Notizen sehen",
               "Betreuungs-Notizen (Post-its) der Ermittler-Betreuung lesen."),
    Capability("mentoring_notes.edit", "Betreuungs-Notizen pflegen",
               "Betreuungs-Notizen anlegen, aendern, archivieren, "
               "wiederherstellen und ordnen."),
    # --- Build 420 (SF-4): Authoring der Berichtsvorlagen (Seed in M013) -----
    #   Schreibrecht auf templates.db (Baustein-Module, Platzhalter/Queries,
    #   Dokumentvorlagen). Der Schreibpfad selbst ist auditiert (TemplatesWriter,
    #   Build 421). Nicht scope-behaftet: der Katalog ist fallunabhaengig.
    Capability("templates.edit", "Berichtsvorlagen/Bausteine pflegen",
               "Baustein-Module, Platzhalter/Queries und Dokumentvorlagen in "
               "templates.db anlegen und pflegen (auditiert)."),
    # --- Wartungsmodus (Sequenz A-D): kontrollierter Betriebsstillstand -------
    #   Wer ein Wartungsfenster setzen/aufheben und laufende Wartungs-Test-Server
    #   beenden darf. NICHT scope-behaftet (globale Betriebshandlung, nicht
    #   fallbezogen). Grant an 'maintenance' UND 'supervisor' ueber policy_admin
    #   (mc 2026-07-19).
    Capability("wartung.durchfuehren", "Wartung durchfuehren",
               "Wartungsfenster setzen/aufheben (enter/exit) und laufende "
               "Wartungs-Test-Server beenden (kill). Nicht fallbezogen."),
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
