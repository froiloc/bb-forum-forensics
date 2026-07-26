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
# Build 524: +limitation.view (AP-3A, Seed in M031). Auszaehlung am Code-Stand
#   524: 39 Faehigkeiten, 8 Rollen (vorher 38 Faehigkeiten). Die Zahl steht hier
#   BEWUSST als nachgezaehlter Wert und nicht als Fortschreibung fruehrerer
#   Notizen — die Angabe "32 -> 36" in build.json 521 zaehlte etwas anderes
#   (Anker in test_management_rbac_schema.py), nicht die Katalogtupel.
# Version: v0.8.524 · Build: 524 · 2026-07-25
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
    # --- Build 464: Onboarding/Offboarding-Checkliste (Seed in M017) --------
    #   Personal-/Leitungsfunktion (koppelt AD-Schicht F4). NICHT scope-behaftet.
    #   Lesen und Pflegen getrennt. Grants an 'supervisor' (ggf. 'admin') per
    #   policy_admin (default-deny; mc 2026-07-20).
    Capability("onboarding.view", "Onboarding-/Offboarding-Checkliste sehen",
               "Den Stand der Onboarding-/Offboarding-Checklisten der "
               "Mitarbeiter lesen."),
    Capability("onboarding.edit", "Onboarding-/Offboarding-Checkliste pflegen",
               "Checklisten-Schritte als erledigt/nicht zutreffend setzen oder "
               "zuruecksetzen (auditiert)."),
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
    # --- Build 468 (AP-2A): Kreuzbezug/Identitaets-Katalog ------------------
    #   Globaler Katalog identifizierter Personen (Konto->reale Person) mit
    #   Konfidenzstufe. Seed in M018. Grant an ermittelnde Rollen ist operative
    #   Entscheidung (default-deny), nicht Teil des Builds (mc 2026-07-20).
    Capability("crossref.view", "Kreuzbezug/Identitaetskatalog sehen",
               "Den Katalog identifizierter Personen (Konto->reale Person) "
               "lesen."),
    Capability("crossref.edit", "Kreuzbezug/Identitaetskatalog pflegen",
               "Zuordnungen anlegen/revidieren und die Konfidenzstufe setzen "
               "(auditiert)."),
    # --- Build 501: AD-Abgleich der Ermittlerstammdaten (Seed in M020) ------
    #   Abgleich person <-> Active-Directory-Gruppe (Neuaufnahme als
    #   investigator, protokollierte Namensaenderung, Deaktivierung NUR nach
    #   woertlicher Bestaetigung "Entfernen" — nie Loeschen). NICHT scope-
    #   behaftet: Personalstammdaten sind eine Leitungsangelegenheit. Grant an
    #   'supervisor' (ggf. 'admin') per policy_admin (default-deny; Bauplan
    #   Build501_502 §4; mc 2026-07-24).
    Capability("personnel.sync", "AD-Abgleich durchfuehren",
               "Ermittlerstammdaten mit der Active-Directory-Gruppe abgleichen "
               "(Vorschau, Neuaufnahme, Namensaenderung, bestaetigte "
               "Deaktivierung/Reaktivierung — auditiert, nie Loeschen)."),
    # --- Build 503: Personalverwaltung (Seed in M021) -----------------------
    #   Die Personal-Seite des Cockpits (mc 2026-07-24: "Seite zum Verwalten
    #   der Anwender", mit eingebundenem AD-Abgleich). Lesen und Pflegen
    #   getrennt; die Grants der Rollen-MATRIX (rbac_grant) bleiben bewusst
    #   der auditierten CLI (policy_admin) vorbehalten. Grants an 'supervisor'
    #   per policy_admin (default-deny).
    Capability("personnel.view", "Personalliste sehen",
               "Personen mit Aktiv-Status, Rollen-Flags und Rollenzuweisungen "
               "lesen."),
    Capability("personnel.edit", "Personal pflegen",
               "Rollen-Flags setzen und Rollenzuweisungen erteilen/widerrufen "
               "(auditiert; Grants der Rollen-Matrix bleiben der CLI "
               "vorbehalten)."),
    # --- Build 515 (AP-2G / Idee 23): Eskalationen (Seed in M026) -----------
    #   Das Read-Model aus Build 453 wird als Cockpit-Sicht erreichbar. BEWUSST
    #   NICHT scope-behaftet: eine Eskalationsliste ist ein Aufsichtsinstrument
    #   der Fallverteilung — sie beantwortet die Frage "wo bleibt etwas liegen,
    #   das NIEMAND anfasst". Auf 'eigene' verengt haette sie genau die Faelle
    #   nicht gezeigt, um derentwillen es sie gibt (die unzugewiesenen), und
    #   waere damit ein irrefuehrender Beleg. Wer sie nicht haben soll, bekommt
    #   den Grant nicht (default-deny) — Analogie: personnel.sync.
    #   Grant an 'supervisor' per policy_admin.
    Capability("escalation.view", "Eskalationen sehen",
               "Belegte Eskalationen aus dem Fallzustand lesen (ueberfaellige "
               "rote Faelle, unbearbeitete offene Faelle, systemischer "
               "Rueckstau) — auswertend, nicht fallbezogen scope-behaftet."),
    # --- Build 517 (AP-2G / Idee 23): Quittierung (Seed in M027) ------------
    #   EIGENE Faehigkeit neben 'escalation.view': wer Eskalationen SEHEN darf,
    #   darf damit noch lange nicht fuer die Behoerde festhalten, dass etwas
    #   gesehen und veranlasst wurde. Ein Lese-Grant darf nie ein Schreibrecht
    #   mitbringen. Quittieren ist KEIN Erledigen — die Eskalation bleibt
    #   sichtbar und traegt ihren Vermerk (Befund Uebergabe 440-453 §3.3).
    Capability("escalation.ack", "Eskalationen quittieren",
               "Eine Eskalation mit Pflichtbegruendung als gesehen vermerken "
               "und einen Vermerk mit Pflichtgrund widerrufen (auditiert; die "
               "Eskalation bleibt sichtbar — quittieren ist kein Erledigen)."),
    # --- Build 519 (AP-2F / Idee 22): Naechstbeste Aktion (Seed in M028) -----
    #   Die priorisierte, BELEGTE Arbeitsschlange. Anders als 'escalation.view'
    #   ist diese Sicht SCHEIN-scope-behaftet gemeint: mit Scope 'eigene' sieht
    #   eine Ermittlerin ihre eigene Schlange, mit 'alle' die der ganzen
    #   Dienststelle. Beides ist sinnvoll und beides ist etwas anderes — der
    #   Scope entscheidet nicht ueber Sichtbarkeit einer Randzeile, sondern
    #   ueber den ZWECK der Sicht (Selbstorganisation vs. Verteilung).
    #   Grant an 'investigator' (eigene) und 'supervisor' (alle) per
    #   policy_admin; default-deny.
    Capability("nextactions.view", "Naechstbeste Aktion sehen",
               "Die priorisierte Arbeitsschlange lesen (naechste sinnvolle "
               "Handlung je offenem Fall, mit belegter Begruendung). Scope "
               "'eigene' = eigene Faelle, 'alle' = alle Faelle."),
    # --- Build 520 (AP-2G / Idee 30): Uebergabe-Protokoll (Seed in M029) -----
    #   "Wer hat wann welchen Fall an wen uebergeben" — rekonstruiert aus der
    #   unveraenderlichen audit_log-Kette (CASE_ASSIGNED). BEWUSST NICHT
    #   scope-behaftet, gleiche Begruendung wie 'escalation.view': ein
    #   Uebergabe-Protokoll handelt von der BEZIEHUNG zwischen Personen. Auf
    #   die eigenen Eintraege verengt entstuende ein Protokoll MIT LUECKEN,
    #   das vollstaendig AUSSIEHT — und dessen Zaehler (Uebergaben, betroffene
    #   Faelle) dann etwas anderes bedeuteten als sie sagen. Wer es nicht
    #   sehen soll, bekommt den Grant nicht (default-deny).
    Capability("handover.view", "Uebergabe-Protokoll sehen",
               "Nachvollziehen, wer wann welchen Fall an wen uebergeben hat "
               "(rekonstruiert aus der Audit-Kette; rein lesend)."),
    # --- Build 521 (AP-2G / Idee 29): Aufbewahrungsfristen (Seed in M030) ----
    #   EIGENES Recht statt Wiederverwendung von 'ops.view'. Begruendung: die
    #   uebrigen ops.view-Sichten zeigen den Zustand der ANLAGE (Backup,
    #   Speicher, Integritaet). Diese Sicht zeigt eine LISTE VON FAELLEN mit
    #   Beschuldigten-Kontonamen. Wer die Anlage betreut, braucht diese Namen
    #   nicht — eine Wiederverwendung waere ein Zweckbindungsverstoss, keine
    #   Sparsamkeit. Nicht scope-behaftet: Fristenkontrolle ist eine
    #   Leitungsaufgabe. Grant an 'supervisor' per policy_admin (default-deny).
    Capability("retention.view", "Aufbewahrungsfristen sehen",
               "Faelle lesen, deren Aufbewahrungsfrist ueberschritten ist "
               "(Pruefvorschlag). Loeschen ist damit AUSDRUECKLICH NICHT "
               "verbunden — es gibt dafuer keinen Weg im Werkzeug."),
    # --- Build 524 (AP-3A / Idee 32): Verjaehrungsfristen (Seed in M031) -----
    #   EIGENES Recht, nicht 'ops.view' und nicht 'dashboard.view'. Die Sicht
    #   zeigt zwei Dinge ZUSAMMEN, die keine bestehende Sicht zusammen zeigt:
    #   eine Liste von Faellen mit Beschuldigten-Kontonamen UND eine
    #   rechtliche Einschaetzung mit unumkehrbarer Folge (eine verjaehrte Tat
    #   ist nicht heilbar). Wer die Anlage betreut, braucht beides nicht; wer
    #   das Ampel-Dashboard liest, bekommt damit noch keine Fristbewertung.
    #   NICHT scope-behaftet (wie escalation.view): auf 'eigene' verengt haette
    #   die Sicht genau die Faelle nicht gezeigt, um derentwillen es sie gibt —
    #   die unzugewiesenen, bei denen die Frist trotzdem laeuft.
    #   Grant an 'supervisor' per policy_admin (default-deny).
    Capability("limitation.view", "Verjaehrungsfristen sehen",
               "Faelle mit der rechnerischen Verjaehrungsfrist (§§ 78 ff. "
               "StGB) lesen. Die Sicht stellt KEINE Verjaehrung fest und ist "
               "ohne bestaetigten Parametersatz stumm."),
    # --- Build 533 (AP-3A): Tatzeitraum erfassen (Seed in M032) -------------
    #   EIN Recht, kein Paar aus view/edit. Begruendung: Die Tatzeit ist Teil
    #   der Annotation, und wer die Annotation sehen darf, sieht sie ohnehin —
    #   ein eigenes Leserecht wuerde eine Trennung behaupten, die es in der
    #   Oberflaeche nicht gibt und die niemand durchhalten koennte. Das
    #   SCHREIBEN dagegen ist eine eigenstaendige Handlung mit rechtlicher
    #   Tragweite und bekommt deshalb sein eigenes Recht.
    #
    #   WARUM NICHT 'results.edit' MITBENUTZEN: Dort wird eine Ermittlungs-
    #   BEWERTUNG erfasst (Konfidenz, Qualitaet je Kriterium). Hier wird eine
    #   TATSACHENANGABE festgestellt, aus der eine Frist gerechnet wird, deren
    #   Ablauf unumkehrbar ist. Das sind verschiedene Erkenntnisarten; eine
    #   Wiederverwendung waere ein Zweckbindungsverstoss, keine Sparsamkeit
    #   (dieselbe Abgrenzung wie retention.view/M030 und limitation.view/M031).
    #
    #   NICHT scope-behaftet — und hier aus einem anderen Grund als sonst: Der
    #   forensische Server hat immer nur GENAU EINEN Fall geoeffnet, und die
    #   subject_id kommt aus dem ResolvedContext, nie aus dem Rumpf
    #   (forensic_api/results_endpoint.py:20-27). Ein Scope 'eigene' waere
    #   wirkungslose Doppelung einer Schranke, die schon strukturell steht.
    #
    #   MIT DIESEM RECHT IST KEINE FRISTAUSSAGE VERBUNDEN. Es erlaubt, eine
    #   Tatzeit zu ERFASSEN. Ob daraus eine Frist gerechnet wird, entscheidet
    #   allein der bestaetigte Parametersatz (limitation_params.json).
    #   Grant an 'investigator' und 'supervisor' per policy_admin (default-deny).
    Capability("tatzeit.edit", "Tatzeitraum erfassen",
               "Zu einer Annotation den festgestellten Tatzeitraum (Beginn "
               "und/oder Ende) erfassen, korrigieren oder zuruecknehmen. "
               "Append-only mit Beleg in der Beweismitteldatenbank."),
    # --- Build 536 (AP-3B): Dringlichkeitsmatrix (Seed in M033) -------------
    #   EIGENES Recht, nicht 'dashboard.view' und nicht 'limitation.view'.
    #   Das Ampel-Dashboard zeigt den BEARBEITUNGSSTAND je Fall; die Matrix
    #   zeigt eine RANGFOLGE und stuetzt sich dabei auf die Verjaehrungsfrist,
    #   deren Ablauf unumkehrbar ist. Und sie zeigt neben der Frist den
    #   ARBEITSSTAND fremder Faelle (Abdeckung der Bewertung, hoechste
    #   Konfidenz, Identitaetszuordnung) — wer die Fristen sehen darf, darf
    #   damit noch nicht sehen, wie weit die Kolleginnen sind.
    #
    #   NICHT scope-behaftet: eine Rangfolge ueber den eigenen Arbeitsvorrat
    #   waere keine. Auf 'eigene' verengt zeigte sie genau die Faelle nicht,
    #   um derentwillen es sie gibt — die unzugewiesenen.
    #
    #   MIT DIESEM RECHT IST KEINE PRIORISIERUNG VERBUNDEN. Die Matrix
    #   schreibt NICHT in cases.priority; sie ist ein Vorschlag, den ein
    #   Mensch sieht, und ausdruecklich KEINE Beweiswuerdigung (§ 261 StPO).
    #   Grant an 'supervisor' per policy_admin (default-deny).
    Capability("matrix.view", "Dringlichkeitsmatrix sehen",
               "Die Rangfolge der Faelle nach Bearbeitungsdringlichkeit und "
               "Erkenntnislage lesen. Die Matrix ist ein VORSCHLAG und keine "
               "Beweiswuerdigung (§ 261 StPO); sie schreibt keine Prioritaet."),

    # --- AP-3C (Build 540, Seed in M034): QS-Stichprobe ---------------------
    #   ZWEI Rechte, ausdruecklich GETRENNT (Muster release.view /
    #   release.grant): wer die Stichprobe sehen darf, darf damit noch nicht
    #   pruefen. Nur so bleibt Vier-Augen moeglich.
    #
    #   ZWECKBINDUNG: AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGS-
    #   INSTRUMENT. Sie steht in jeder Antwort, jeder Sicht und jedem Export
    #   (management/qs/qs_vokabular.py: ZWECKBINDUNG).
    #
    #   NICHT scope-behaftet: eine Stichprobe ueber den eigenen Arbeitsvorrat
    #   waere keine. Grant an 'supervisor' UND 'lector' (Entscheidung mc
    #   C-1) per policy_admin; default-deny.
    Capability("qs.view", "QS-Stichproben sehen",
               "Ziehungen und Pruefergebnisse der Qualitaetssicherung lesen. "
               "AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT."),
    Capability("qs.edit", "QS-Stichproben ziehen und pruefen",
               "Eine Stichprobe ziehen und Pruefergebnisse mit "
               "Pflichtbegruendung erfassen. Die SELBSTPRUEFUNG ist "
               "serverseitig gesperrt: wer einen Fall bearbeitet hat, kann ihn "
               "nicht pruefen."),
    # --- Build 561 (AP-3E, Instanz B): Inhaltsfreigabe der Volltextsuche ----
    #   Seed in M040. ANKERDELTA: 43 -> 44 Faehigkeiten (Basis 43 ist der beim
    #   Rebase auf v0.8.540 VORGEFUNDENE Stand, nicht der der Bauzeit;
    #   Parallelbetrieb §6 Nr. 2).
    #
    #   WARUM EIN EIGENES RECHT UND NICHT 'release.grant' (M016): dort geht es
    #   um die EXTERNE Fallfreigabe an eine andere Dienststelle — anderer
    #   Empfaengerkreis, andere Zweckbindung, andere Rechtsgrundlage. Hier
    #   geht es um die Sichtbarkeit des Arbeitsstands INNERHALB des Hauses.
    #   Eine Wiederverwendung waere ein Zweckbindungsverstoss, keine
    #   Sparsamkeit (dieselbe Abgrenzung wie tatzeit.edit gegenueber
    #   results.edit).
    #
    #   NICHT scope-behaftet: der Sinn der Freigabe ist gerade der Zugriff auf
    #   einen FREMDEN Fall. Ein Scope 'eigene' waere die Aufhebung der
    #   Funktion, nicht ihre Absicherung.
    #
    #   ABGRENZUNG ZU 'evidence.fulltext_search' (seit M006 im Katalog): das
    #   ist das Recht, ueberhaupt zu SUCHEN (Stufe 1). Dieses hier ist das
    #   Recht, anderen den INHALT fremder Faelle zu OEFFNEN (Stufe 2). Wer
    #   sucht, gibt damit nichts frei; wer freigibt, sucht damit nicht.
    #   Grant an 'supervisor' per policy_admin (default-deny).
    Capability("fulltext.release", "Inhaltsfreigabe der Volltextsuche erteilen",
               "Einer Person den Zugriff auf den Trefferinhalt (Stufe 2) "
               "eines ihr NICHT zugewiesenen Falls erteilen oder widerrufen. "
               "Auditiert, mit Pflichtbegruendung; eine Freigabe je Fall und "
               "Person."),
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
