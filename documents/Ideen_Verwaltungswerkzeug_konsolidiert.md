# Verwaltungswerkzeug (Baustelle 7) — Konsolidierte Ideen, Cluster & Priorisierung

**Planungsdokument · Stand 2026-07-07 · kein Build, keine Versionsnummer.**
Baut auf `Ideen_zum_Verwaltungswerkzeug.md` (Ideen §1–§15) auf und führt das
Ergebnis von vier Brainstorming-Runden zusammen. Zweck: Grundlage für das
Gespräch mit der Chef-Ermittlerin und eine der StA vorlegbare Priorisierung.

Leitsatz: Das Verwaltungswerkzeug bildet die **Metaarbeit** ab (Verwaltung,
Zuteilung, Betreuung, Abnahme, Statistik, Planung) — **losgelöst vom
Ermittlungsinhalt** der Baustellen 3/4/6. Die per-Fall-Kapselung bleibt strikt;
sie wird nur an klar benannten, eigens freigegebenen Stellen bewusst durchbrochen.

**Kapselungs-Ampel je Idee:**
🟢 plattformbezogen, kein Fallinhalt · 🟡 fallübergreifend, braucht eigenes
auditiertes Freigabe-/Sichtbarkeitsmodell · 🔴 greift auf Ermittlungs-*inhalt*
mehrerer Fälle zu (höchste Hürde).

**Status-Kürzel:** ✅ gebaut · 🔧 als CLI vorhanden (wird zur Seite) · 🆕 neu.

---

## 0. Bereits getroffene Entscheidungen (Fundament des Entwurfs)

Diese Punkte sind im Verlauf der Diskussion festgezurrt und rahmen alles Weitere:

1. **Ein Werkzeug, jeder lokal (Modell A2):** Jede/r startet ihre/seine eigene
   Instanz auf der lokalen Offline-VM, beschränkt auf die aufgelöste OS-Identität.
   Kein zentraler Netz-Server.
2. **Rollen = AIW-Flags** (`is_supervisor`/`is_investigator`/`is_support`);
   **Mehrfachrollen möglich** — je Rolle steht die jeweilige Sicht zur Verfügung.
3. **RBAC als DB-Matrix** in `coordinator.db`, Änderungen über den auditierten
   `CoordinatorWriter` (hash-verkettet). Trennung: (a) Sicht-/Aktions-Sichtbarkeit
   je Rolle, (b) Datensicht-Umfang `alle`/`eigene` als Query-Prädikat im Lese-Repo.
4. **Nur `is_supervisor` startet die Vollversion;** erster Server-Build read-only
   (Anzeigen live), Schreib-Aktionen als Folge-Build.
5. **Live-Aktualisierung via SSE:** der Management-Server pollt die `audit_log`-
   Spitze; steigt sie, wird die betroffene Sicht im Browser neu geholt (kein F5).
6. **AD-Anzeigename** als Anzeige-Attribut; der **`system_username` bleibt die
   stabile forensische Identität** (Belege hängen daran, nicht am Rufnamen).
7. **`integrity_check` läuft auf den Backup-Kopien** — zertifiziert das Backup
   und stört keinen Livezugriff.
8. **Kapselung bleibt robust;** fallübergreifende Sichten (🟡/🔴) nur mit
   explizitem, auditiertem Freigabemodell.

---

## 1. Die vier (bzw. fünf) Fundamente

Querschnitts-Bausteine, auf denen die meisten Sichten aufbauen — daher **zuerst**.

| # | Fundament | Was es trägt | Aufwand | Kaps. |
|---|---|---|---|---|
| F1 | **RBAC-Matrix (DB, auditiert)** | jede rollen-/scope-abhängige Sicht (§15 teilw.) | mittel–hoch | 🟢 |
| F2 | **Dedizierter Management-Server + SSE-Auto-Refresh** | das gesamte Live-Cockpit | hoch | 🟢 |
| F3 | **Zustandsmaschinen** (Fallstatus-Workflow · Wiedervorlage externer Vorgänge · Fremdforum-Promotion) | Workflow, Kalender/Gantt, Eskalation, data/-Übersicht | mittel | 🟢 |
| F4 | **AD-Integrationsschicht** (gekapselt, mockbar): Gruppenabgleich · Anzeigename · externe Kennung | Ermittler-Anlage, Namen, externe Freigabe | mittel | 🟢 |
| F5 | **Kreuzbezugs-Register** (eigenes Freigabemodell) | Querfunde, Alias, Identitäts-Katalog | hoch | 🟡 |
| T1 | **Rendering-Grundlagen**: ECharts (Diagramme) + Tabulator.js (Tabellen) | alle Statistik-/Tabellen-Sichten | gering | 🟢 |

F5 ist bewusst als Fundament markiert, weil Querfunde/Alias/Identität mehrere
fallübergreifende Sichten speisen und alle **dasselbe** Freigabemodell brauchen —
das einmal sauber, nicht dreimal halb.

---

## 2. Cluster mit Einzel-Ideen

### 2.1 Ermittlungssteuerung (Supervisor)

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Ampel-Dashboard je Fall (§1) | hoch | — | F2 | 🟢 | ✅ |
| Zuweisung von Fällen (§, Runde 2.5) | hoch | gering | F1 | 🟢 | 🔧 |
| Lastverteilung + Überlastwarnung (§6) | hoch | mittel | Kapazitätsdaten | 🟢 | ✅ (Basis) |
| Risiko-/Dringlichkeits-Matrix (§3) | mittel | mittel | Fristen, Relevanz | 🟢 | 🆕 |
| Fristen-/Verjährungs-Monitor je Fall | hoch | mittel | F3 | 🟢 | 🆕 |
| Eskalations-/Benachrichtigungsregeln | hoch | mittel | F3 | 🟢 | 🆕 |
| „Nächstbeste Aktion"-Warteschlange (Ermittler) | mittel | mittel | F3 | 🟢 | 🆕 |
| Fall-Ereigniszeitstrahl (§11) | mittel | gering | audit_log | 🟢 | 🆕 |

### 2.2 Ermittler-Sicht (Scope „eigene")

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Meine Aufträge (offene, zugewiesene Fälle) | hoch | gering | F1 (Scope) | 🟢 | 🆕 |
| Meine Historie (eigene auditierte Aktivität) | hoch | gering | audit_log | 🟢 | 🆕 |
| Meine Berichte (Berichte zu meinen Fällen, auch fremdverfasst) | hoch | mittel | B6-Meta | 🟡 | 🆕 |

### 2.3 Berichte & Abnahme (Meta zu Baustelle 6)

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Berichts-Abnahme (ansehen/abnehmen/zurückweisen/Status) (§4) | hoch | mittel | B6, Export | 🟡 | 🆕 |
| Berichts-Vorlagen / Textbaustein-Bibliothek (StA-Boilerplate) | mittel | gering | — | 🟢 | 🆕 |
| Vier-Augen-/QS-Stichprobe abgeschlossener Arbeit | mittel | mittel | F1 | 🟡 | 🆕 |

### 2.4 Auswertung & Statistik (StA / Führung)

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| StA-Statistik-Export (§2) | hoch | mittel | T1, Export | 🟢 | 🆕 |
| StA-Berichtsgenerator (periodischer Statusbericht, PDF) | hoch | mittel | Export | 🟢 | 🆕 |
| Kennzahlen-Glossar (einheitliche Definitionen) | mittel | gering | — | 🟢 | 🆕 |
| Prognose-Modul, 3 Szenarien (§7) | mittel | hoch | Kapazität, Historie | 🟢 | 🆕 |
| Gantt-Chart + Ressourcenplanung (§5) | hoch | hoch | F3, T1, Kapazität | 🟢 | 🆕 |
| ECharts-Diagramme für Statistiken | Basis | gering | T1 | 🟢 | 🆕 |
| Annotations-Tortenstatistik (Kategorien/Notizen/Tags) (§12) | mittel | mittel | evidence-Aggregat | 🟡 | 🆕 |

### 2.5 Qualität & Schulung (aus Metadaten)

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Abdeckungs-/Vollständigkeitsscore je Fall (gesichtet vs. gescrapt) | hoch | mittel | Scrape-/Sicht-Daten | 🟡 | 🆕 |
| „Blinde Flecken": gescrapt, aber nie gesichtet (§Runde) | hoch | mittel | s. o. | 🟡 | 🆕 |
| Auswertungsstrategien-Analyse (Reihenfolge der Bearbeitung) | mittel | mittel | audit/evidence | 🟡 | 🆕 |
| Anonymisierte Schulungs-Fallbeispiele | mittel | mittel | Anonymisierung | 🟡 | 🆕 |
| Ermittler-Metriken & Ausreißer-Detektion (§8) | mittel | hoch | evidence, QS-Governance | 🟡 | 🆕 |

### 2.6 Personal, Rollen & Kapazität

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Mitarbeiter/Rollen pflegen (§Runde) | hoch | gering | F1 | 🟢 | 🔧 |
| Ermittler automatisch aus AD-Gruppe `SEC_16_03_EK-Zarewitsch` anlegen | hoch | mittel | F4 | 🟢 | 🆕 |
| AD-Anzeigename statt SAMAccountName anzeigen | mittel | gering | F4 | 🟢 | 🆕 |
| Abwesenheits-/Kapazitätsplanung (Urlaub/Schulung/Krankheit) | hoch | mittel | — | 🟢 | 🆕 |
| Übergabe-Protokoll bei Fall-Umverteilung | mittel | gering | audit_log | 🟡 | 🆕 |
| Onboarding/Offboarding-Checkliste (koppelt AD) | mittel | mittel | F4 | 🟢 | 🆕 |

### 2.7 Betrieb, Integrität & Datensicherheit (Systemzustand)

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Backup & Point-in-Time-Recovery-Maske (§10) | hoch | mittel | — | 🟢 | 🆕 |
| Integritäts-/Restore-Übung + `integrity_check` **auf Backup-Kopien** | hoch | mittel | Backup | 🟢 | 🆕 |
| DB-Gesundheitsprüfung (Ergebnis-Historie, geplant) | hoch | gering | Backup | 🟢 | 🆕 |
| Log-Auswertung nach Fehlern (`logs/forensic_server.log*`) | mittel | gering | — | 🟢 | 🆕 |
| Speicher-/Wachstumsübersicht von `data/` | mittel | gering | — | 🟢 | 🆕 |
| Übersicht Fälle in `data/` inkl. Fremdforum-Evidence ohne `evidence_<uid>.db` | hoch | mittel | F3 | 🟡 | 🆕 |
| Audit-/Revisions-Explorer (verifizierbar, gerichtsfester Export) | hoch | mittel | audit_log | 🟢 | 🆕 |
| Audit-Log Nichtmanipulierbarkeit (§13) | Basis | — | — | 🟢 | ✅ |

### 2.8 Export & Ausschleusung

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Export-Subsystem (einheitl. Kopf/Fuß, Prüfsumme, Erzeugungsvermerk) | hoch | mittel | — | 🟢 | 🆕 |
| Fallstatus → Excel-Export | hoch | gering | Export | 🟢 | 🆕 |
| Bericht → PDF für Akte/StA | hoch | mittel | B6-Meta, Export | 🟡 | 🆕 |
| StA-Export-Modul mit Ausschleus-Verzeichnis (§12) | hoch | mittel | Export | 🟡 | 🆕 |
| Druck-/Akten-Export je Sicht | mittel | gering | Export | 🟢 | 🆕 |
| Externe Fallfreigabe an NRW-Ermittler (AD-ACL, Unbedenklichkeit, auditiert) | hoch | mittel | F4, Prüfung | 🟡 | 🆕 |
| LKÄ-Distribution (Demo-/Mockup-Paket) | mittel | mittel | Freigabe | 🟡 | 🆕 |

### 2.9 Kreuzbezüge & Identität (fallübergreifend — F5)

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Querfunde (Fund über B im Fall A) | hoch | mittel | F5 | 🟡 | 🆕 |
| Querfund-Rückkanal (erreicht den B-Ermittler aktiv) | hoch | mittel | F5, F3 | 🟡 | 🆕 |
| Globaler Alias-Editor / -Katalog | hoch | mittel | F5 | 🟡 | 🆕 |
| Katalog identifizierter Nutzer/Personen (Chef pflegt, Ermittler lesen) | hoch | mittel | F5 | 🟡 | 🆕 |
| Flag „Person identifiziert" + Konfidenzstufe (Verdacht/wahrsch./gerichtsfest) | hoch | gering | F5 | 🟡 | 🆕 |
| Identitäts-Zusammenführung (Merge/Split, umkehrbar, auditiert) | mittel | mittel | F5 | 🟡 | 🆕 |
| Volltextsuche über alle `evidence_*.db` (§14) | hoch | hoch | starkes Freigabemodell | 🔴 | 🆕 |

### 2.10 Plattform-Feedback & Hilfe (streng fallinhaltsfrei!)

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Hilfsdokumente-Bibliothek | mittel | gering | — | 🟢 | 🆕 |
| Feedback-Board (Rückmeldungen zur Software) | mittel | gering | — | 🟢 | 🆕 |
| Bugtracker light (zentral, nachschlagbar) | mittel | mittel | — | 🟢 | 🆕 |
| Internes Nachrichtensystem, nur Templates (§9) | gering | gering | — | 🟢 | 🆕 |

### 2.11 UX / Plattform-Querschnitt

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Kommandopalette (Strg-K): Funktions-/Seiten-Suche **und** Sprung zu Fall/Nutzer/Alias | hoch | mittel | F1, F5 | 🟢/🟡 | 🆕 |
| Tabulator.js für alle Tabellen | Basis | gering | T1 | 🟢 | 🆕 |
| Konfigurations-Editor mit Validierung (Ampel-Schwellen, Fristen, Defaults; auditiert) | mittel | mittel | F1 | 🟢 | 🆕 |
| Modul-Steuerung / Rollen-Widgets, konfigurierbares Dashboard (§15) | mittel | hoch | F1, F2 | 🟢 | 🆕 |

### 2.12 Support-Rolle

| Idee | Nutzen | Aufwand | Abhängig | Kaps. | St. |
|---|---|---|---|---|---|
| Support-Historie (wer/wann/wie lange/wie beendet) (§) | hoch | — | F2 | 🟢/🟡 | ✅ |
| Ermittler-Betreuung (laufende Support-Sitzungen begleiten) | mittel | mittel | F2 | 🟡 | 🆕 |
| Support-Schicht-/Bereitschaftsübersicht | gering | gering | Kapazität | 🟢 | 🆕 |

---

## 3. Wellen-Vorschlag (Leitachse: Produktivstart-Nutzen, Fundamente als Nebenbedingung)

Dies ist der Vorschlag, den die Chef-Ermittlerin ordnen/anpassen und der StA als
**ihre** Priorisierung vorlegen kann.

**Welle 0 — Fundament (muss zuerst).**
F1 RBAC-Matrix · F2 Management-Server + SSE · F3 Fallstatus-Workflow · F4 AD-Schicht
· T1 ECharts + Tabulator.js. (F5 Kreuzbezugs-Register unmittelbar danach.)

**Welle 1 — Produktivstart-Muss (höchster Betriebsnutzen).**
Cockpit-Shell (Supervisor- + Ermittler-Sicht, policy-getrieben) · Dashboard ✅
einbinden · Zuweisung (🔧→Seite) · Meine Aufträge/Historie/Berichte ·
Lastverteilung ✅ · Support-Historie ✅ · Mitarbeiter/Rollen-Seite (🔧) ·
Betriebs-/Systemzustand-Sicht (Backup-Restore-Verify + `integrity_check` auf
Backup-Kopien + DB-Health + Log-Fehler) · Wiedervorlage externer Vorgänge +
Fristen-/Verjährungs-Monitor · Berichts-Abnahme + Export-Subsystem (Excel-Fallstatus,
Bericht-PDF, StA-Ausschleus).

**Welle 2 — Wertstiftend.**
Kreuzbezugs-Register (Querfunde/Alias/Identität/Konfidenz/Merge-Split/Rückkanal) ·
Abdeckungs-Score + blinde Flecken · StA-Statistik/Prognose/Berichtsgenerator +
Kennzahlen-Glossar · Gantt + Kapazitäts-/Abwesenheitsplanung + Überlast ·
Nächstbeste-Aktion · Eskalationsregeln · Audit-/Revisions-Explorer ·
Fremdforum-Promotion + `data/`-Übersicht · externe Fallfreigabe + LKÄ-Distribution ·
Kommandopalette/globale Suche · Datenschutz-/Löschkonzept · Übergabe-Protokoll ·
Onboarding/Offboarding.

**Welle 3 — Später / Ausbau (heikler oder abhängig von sauberer Datenbasis).**
Ermittler-Metriken/Ausreißer · Auswertungsstrategien-Analyse + anonymisierte
Schulungsfälle · Annotations-Tortenstatistik · QS-Stichprobe ·
Modul-Steuerung/Drag&Drop-Widgets · Textbaustein-Bibliothek · **Volltextsuche über
alle `evidence_*.db` (🔴 — stärkstes Freigabemodell zwingend)** · Risiko-/
Dringlichkeitsmatrix · Prognose-3-Szenarien-PDF · Plattform-Feedback
(Hilfe-Bibliothek/Feedback-Board/Bugtracker/Nachrichten-Templates).

---

## 4. Offene, noch zu klärende Punkte

- **Datenbasis für Kapazität/Prognose/Gantt/Überlast:** Abwesenheits-/
  Kapazitätsplanung ist Voraussetzung — ohne sie bleibt „freie Kapazität" geraten.
- **Freigabemodell für 🟡/🔴-Sichten:** wer darf Querfund/Alias/Identität/Volltext
  sehen und eintragen — muss vor Welle 2 stehen.
- **Datenquelle „gesichtet vs. gescrapt"** für Abdeckungsscore/blinde Flecken:
  woher kommt „gesichtet" belegbar (evidence_<uid>.db / audit)?
- **DDL-Entwurf der RBAC-Matrix-Tabellen** (Migration, additiv) — noch auszuarbeiten.
- **Auslieferungsweg der Ermittler-Instanz** (A2: jeder lokal) — Start-/Rechte-Detail.
- **Kapselungs-Disziplin** bei Feedback-Board/Bugtracker/Hilfe: müssen fallinhaltsfrei
  bleiben (Nebenkanal-Leck vermeiden).

---

*Ende der Konsolidierung. Grundlage für Ordnen/Bewerten/Priorisieren mit der
Chef-Ermittlerin.*
