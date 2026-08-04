// =============================================================================
// management/server/static/cockpit.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit-Shell (Frontend)
// =============================================================================
// Zweck:
//   Baut die policy-getriebene Navigation der Verwaltungsoberflaeche im Browser
//   auf. Quelle der Wahrheit ist /api/whoami: dort liefert der Server die
//   aufgeloesten Faehigkeiten je Person als { cap: scope }-Objekt (scope =
//   'alle' | 'eigene' | null). Aus DIESEN Faehigkeiten leiten sich (a) die
//   sichtbaren Nav-Eintraege und (b) der angezeigte Scope ab — nicht aus einem
//   fest verdrahteten Rollenbild.
//   Beleg: Bauplan B7 v1.1 §11.2; Referenzlayout AIW_Verwaltung_Mockup.html.
//
// ABGRENZUNG (Split analog 314/315, Beleg: UEBERGABE_Build346 §6):
//   347 = Fundament (Nav, Rechte). 348 = Overview-Sicht (Tabulator) + SSE-Reload.
//   349 = Integritaets-/Ops-Sicht + Ketten-Banner + Live-DEBUG.
//   350 = Backend /api/workload + ECharts-Vendoring.
//   351 = Lastverteilung-Sicht (/api/workload, cockpit_workload.js) als
//   gestapeltes ECharts-Balkendiagramm + SSE-Reload; ECharts-Lifecycle
//   (dispose + Resize) in cleanupView().
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE-Wrapper mit 'use strict'.
//   2) Exzessives DEV-Debug-Logging, per Flag abschaltbar (PROD: aus).
//   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
//   4) Logik gekapselt; REINE Funktionen fassen NIE das DOM an.
//   Zusaetzlich: UMD-artiger Ausgang, damit die Vitest-Tests den ECHTEN Code
//   pruefen (kein dupliziertes Logik-Abbild -> vermeidet die 'gruen-aber-tot'-
//   Falle). Nur die render/boot-Funktionen beruehren document (Browser/jsdom).
//
// SICHERHEIT: Anzeigename (display_name) stammt aus dem AD und ist potenziell
//   fremdbestimmt -> IMMER via textContent setzen, nie via innerHTML. Nav-Label
//   und Gruppen stammen aus dem statischen VIEW_CATALOG (unkritisch), werden
//   aber ebenfalls via textContent gesetzt (Prinzip: kein innerHTML mit
//   variablem Text).
//
//   360 = Kapazitaets-Sicht (/api/capacity, cockpit_capacity.js) als ECharts-
//   Diagramm (Basis vs. netto, Auslastungs-Faerbung, Zeitraumwahl) + SSE-Reload.
//   362 = Rechte/Policy-Sicht (/api/policy, cockpit_policy.js): Tabulator-Tabellen
//   fuer Grants + Rollen-Zuweisungen + Katalog + SSE-Reload.
//   364 = Persoenliche Sichten (cockpit_mycases.js / cockpit_myhistory.js):
//   Meine Auftraege + Meine Historie (Tabulator) + SSE-Reload.
//   367 = Support-Historie (/api/support, cockpit_support.js): zwei Listen (Meine
//   Sitzungen / An meinen Faellen) + Detail-Mini-Modal + SSE-Reload.
//   369 = Ermittler-Betreuung (/api/mentoring, cockpit_mentoring.js): Live-Sicht
//   laufender Support-Sitzungen (Ampel/Laufzeit) + periodischer Refresh.
//   371 = Statistiken (/api/stats, cockpit_stats.js): Reiterstruktur, ECharts-
//   Diagramme (Verteilungen/Durchsatz), Ermittler-Tabelle, CSV/JSON-Download.
//   373 = Zuweisung (SCHREIB-Sicht): /api/assignable + POST /api/case/* mit
//   Schreib-Token (X-AIW-Token aus /api/whoami); kein optimistisches UI.
//   375 = Berichts-Abnahme (/api/reports, cockpit_reports.js) + Nav-Korrektur:
//   Sichten koennen mehrere Faehigkeiten haben (any-of, Feld 'caps').
//   378 = Berichts-Freigabe im Cockpit (POST /api/report/approve mit Schreib-
//   Token, GET /api/report/verify zur Siegelpruefung).
//   380 = Rueckgabe zur Nachbesserung (POST /api/report/return).
//   384 = Fall-Erkennung (cockpit_cases.js): GET /api/cases/detect (rein
//   lesender Abgleich Platte <-> Fallakte, vier Zustaende) + POST
//   /api/cases/import (auditierte Aufnahme der AUSGEWAEHLTEN Faelle, mit
//   Bestaetigung). Recht: assignment.edit (Backend-Vorgabe aus Build 383).
//   386 = Kalender & Wiedervorlage (cockpit_calendar.js): GET /api/calendar
//   (Monatsraster ueber ALLE Zeitquellen) + GET /api/external (Vorgangsliste)
//   + POST /api/external/create|defer|answer|close. Recht: external.view;
//   Schreiben nur mit external.edit.
//   395 = Ermittlungsergebnis (cockpit_results.js): Abdeckung JE FALL (auch
//   die NIE bewerteten — die blinden Flecken sind die Hauptaussage) +
//   Verteilung JE KRITERIUM (nie darueber hinweg). Recht: results.view.
//   406 = Betreuungs-Notizen (cockpit_notes.js): Pinboard der Ermittler-
//   Betreuung. Karten in Git-Commit-Metapher (erste Zeile = Ueberschrift, immer
//   sichtbar; Rest aufklappbar), Farbe + Tags, Status 'abarbeiten', client-
//   seitige Suche/Filter, Archiv-Umschalter, Anlegen/Bearbeiten/Duplizieren.
//   Recht: mentoring_notes.view (Lesen) / mentoring_notes.edit (Schreiben, POST
//   mit X-AIW-Token). Drag&Drop-Ordnung folgt in Block 4. Neuer Nav-Eintrag
//   'notes' (Gruppe Verwaltung) direkt neben 'mentoring'.
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Build 479: SSE-Reload-Schutz fuer Lektorat (W4) und Chef-Freigabe (W5).
//   Beide Sichten schreiben beim Oeffnen eines Berichts ueber
//   /api/report/annotations einen Chain-of-Custody-Beleg in den audit_log
//   (Grundregel 1). Die SSE meldet diesen Ausschlag ~2s spaeter als 'changed';
//   der bisher folgende Reload verwarf die offene Auswahl + iframe-Vorschau
//   (gemeldeter Fehler, belegt). Der 'changed'-Handler unterdrueckt den Reload
//   nun, solange das jeweilige Modul via hasSelection() einen offenen Bericht
//   meldet. Ohne offene Auswahl wird wie bisher nachgeladen.
// Build 500: 'Meine Auftraege' reicht onLaunch durch -> POST /api/case/launch
//   startet den Forensik-Server (main.py) fuer einen zugewiesenen Fall; Erfolg/
//   Fehler als Banner (loadMyCases mit pendingMsg neu geladen).
// Build 502 (AD-Abgleich): Nav-Eintrag 'adsync' (personnel.sync) + loadAdSync
//   (Vorschau/apply/decide). BEWUSST ohne SSE-Auto-Reload: jeder Reload ist
//   eine Live-LDAP-Anfrage (siehe Kommentar an loadAdSync).
// Build 503 (Personalverwaltung): Nav-Eintrag 'personnel' (personnel.view)
//   ERSETZT 'adsync' — der AD-Abgleich ist jetzt LAZY-Abschnitt der
//   Personal-Seite (_adsyncInto, Wiederverwendung von AIWCockpitAdSync).
//   SSE-Reload laedt nur die Personenliste, nie den AD-Abschnitt.
// Build 636 (Vorgang 17200856, Welle B4): HILFE-MARKEN fuer die
//   vier Bedienelemente der Navigation (Praefix 'shell.') dieser Sicht.
// Version: v0.8.636 · Build: 636 · 2026-08-01
// =============================================================================

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // DEV-Debug-Logging. Aktivierung im Browser JEDERZEIT (zur Laufzeit):
    //   window.AIW_COCKPIT_DEBUG = true;   // an
    //   window.AIW_COCKPIT_DEBUG = false;  // aus
    // Build 349: Das Flag wird bei JEDEM log()-Aufruf ausgelesen (nicht mehr
    // einmalig beim Laden), damit es ohne Reload umschaltbar ist. PROD: aus.
    // -------------------------------------------------------------------------
    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Cockpit]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) SICHTEN-KATALOG (statisch). Jede Sicht haengt an GENAU EINER Faehigkeit
    //    und erscheint nur, wenn die Person diese Faehigkeit besitzt. 'group'
    //    ordnet die Nav; die Reihenfolge hier bestimmt Nav- UND Gruppen-Folge.
    //    Abgeleitet aus dem Mockup (VIEWS) + Ergaenzung 'integrity' (cap
    //    'ops.view'), da das Backend /api/integrity bereitstellt (Build 346).
    // =========================================================================
    var VIEW_CATALOG = [
        { id: 'dashboard',  cap: 'dashboard.view',       group: 'Ueberblick',     label: 'Dashboard',
          stichworte: 'ueberblick kacheln startseite lage zusammenfassung' },
        // Kalender & Wiedervorlage (Build 386). Gruppe 'Ueberblick', weil die
        // Sicht BEIDE Rollen bedient: die Chefin sieht alle Faelligkeiten, der
        // Ermittler (Scope 'eigene') die seines Falls. Recht: external.view
        // (Backend-Vorgabe aus Build 385).
        { id: 'calendar',   cap: 'external.view',        group: 'Ueberblick',     label: 'Kalender & Wiedervorlage',
          stichworte: 'termine wiedervorlage frist erinnerung monat woche kalender' },
        // Build 516 (AP-2G / Idee 23): Eskalationen (Frontend zu 515). Gruppe
        // 'Ueberblick', weil die Sicht dieselbe Frage beantwortet wie das
        // Dashboard — "worauf muss ich JETZT schauen" —, nur zugespitzt auf
        // das, was ueber eine Schwelle gelaufen ist. Eigenes Recht
        // 'escalation.view' (Seed M026, default-deny) und BEWUSST NICHT
        // scope-behaftet: die wichtigste Regel (Rueckstau) gehoert zu keinem
        // Fall und damit zu keiner Person; auf 'eigene' verengt haette die
        // Sicht genau die Faelle ausgeblendet, um derentwillen es sie gibt.
        { id: 'escalation', cap: 'escalation.view',      group: 'Ueberblick',     label: 'Eskalationen',
          stichworte: 'eskalation ueberfaellig alarm rot dringend liegengeblieben' },
        // Build 519 (AP-2F / Idee 22): Naechstbeste Aktion (Frontend zu 519).
        // Gruppe 'Ueberblick' neben Dashboard und Eskalationen: alle drei
        // beantworten 'worauf muss ich JETZT schauen' — das Dashboard mit
        // Zustaenden, die Eskalationen mit Schwellenverletzungen, diese Sicht
        // mit der naechsten HANDLUNG. SCOPE-BEHAFTET: mit 'eigene' ist es die
        // eigene Arbeitsschlange, mit 'alle' die Verteilsicht der Leitung.
        { id: 'nextactions', cap: 'nextactions.view',    group: 'Ueberblick',     label: 'Nächstbeste Aktion',
          stichworte: 'vorschlag empfehlung naechster schritt todo aufgabe prioritaet' },
        { id: 'assignment', cap: 'assignment.edit',      group: 'Fallsteuerung',     label: 'Zuweisung',
          stichworte: 'zuweisen verteilen sachbearbeiter zustaendigkeit uebertragen fall' },
        // Fall-Erkennung (Build 384): haengt an DERSELBEN Faehigkeit wie die
        // Zuweisung — das Backend (Build 383) schuetzt /api/cases/detect und
        // /api/cases/import mit 'assignment.edit' (Scope 'alle'). Wir fuehren
        // dafuer bewusst KEINE zweite Faehigkeit ein (mc 2026-07-12).
        { id: 'cases',      cap: 'assignment.edit',      group: 'Fallsteuerung',     label: 'Fall-Erkennung',
          stichworte: 'fall anlegen erkennung neuaufnahme portal beschuldigter akte' },
        // Build 574: FALLUEBERSICHT. Die vollstaendige Falltabelle hatte bis
        // hierher KEINE eigene Sicht - sie war in die Kachel 'fallampel' des
        // Ueberblicks eingebettet und damit die einzige Stelle im Werkzeug, an
        // der sie ueberhaupt vorkam. Als die Kachel auf Kompaktform umgestellt
        // wurde (Ring + drei dringendste Faelle, mc 2026-07-30), waere sie
        // ohne diese Sicht STILL verschwunden - und mit ihr der Fall-Sprung
        // der Kommandopalette, der genau in diese Tabelle zielte.
        // Recht: 'dashboard.view' - dasselbe, das die Kachel und der speisende
        // Endpunkt /api/overview ohnehin pruefen. Es entsteht also KEIN neuer
        // Zugang, nur ein zweiter Weg zu demselben Bestand.
        { id: 'faelle',     cap: 'dashboard.view',       group: 'Fallsteuerung',     label: 'Fallübersicht',
          stichworte: 'fall uebersicht tabelle ampel liste alle faelle bestand prioritaet zuweisung' },
        { id: 'mentoring',  cap: 'mentoring.view',       group: 'Betreuung',     label: 'Ermittler-Betreuung',
          stichworte: 'betreuung mentor anleitung begleitung einarbeitung ermittler' },
        // Betreuungs-Notizen ("Post-its", Build 406). Eigener Nav-Eintrag DIREKT
        // neben der Ermittler-Betreuung (abgestimmt mc 2026-07-13). Recht:
        // mentoring_notes.view. Privates Board pro Autor:in; Scope 'alle' sieht
        // fremde Boards (Backend-Vorgabe Build 401/405).
        { id: 'notes',      cap: 'mentoring_notes.view',  group: 'Betreuung',     label: 'Betreuungs-Notizen',
          stichworte: 'notiz vermerk betreuungsnotiz gespraech protokoll' },
        // Berichts-Abnahme: 'reports.approve' ODER 'reports.review' genuegt
        // (wer freigeben darf, muss lesen duerfen). 'caps' = any-of; 'cap' bleibt
        // fuer den Scope-Tag/Platzhalter die Leitfaehigkeit.
        { id: 'reports',    cap: 'reports.approve',      caps: ['reports.approve', 'reports.review'], group: 'Abnahme',     label: 'Berichts-Abnahme',
          stichworte: 'bericht abnahme pruefung freigeben entwurf vermerk akte' },
        // Lektorat (W4, Build 413): Gegenlesen des Berichtstexts. 'caps' = any-of
        // (reports.review ODER reports.approve — die Chefin liest ebenfalls
        // gegen); Leitfaehigkeit fuer den Scope-Tag ist reports.review.
        { id: 'lectorate', cap: 'reports.review',       caps: ['reports.review', 'reports.approve'], group: 'Abnahme',     label: 'Lektorat',
          stichworte: 'lektorat korrektur sprache rechtschreibung durchsicht text' },
        // Chef-Freigabe (W5, Build 416): Bericht lesen + Siegel pruefen +
        // freigeben/zurueckweisen. Recht reports.approve (Freigeben erfordert
        // serverseitig Scope 'alle').
        { id: 'approval',  cap: 'reports.approve',      group: 'Abnahme',     label: 'Chef-Freigabe',
          stichworte: 'freigabe chef leitung genehmigung siegel abschluss' },
        // Platzhalter & Queries (W2, Build 423): Autoren-Maske der Redakteur:in
        // fuer Einzeldaten-Platzhalter-Queries (templates.db). Eigene Gruppe
        // 'Redaktion', in der die weiteren Autoren-Werkzeuge (W1 Bausteine, W3
        // Dokumentvorlagen) folgen. Recht: templates.edit (Build 420).
        { id: 'templates', cap: 'templates.edit',       group: 'Redaktion',      label: 'Platzhalter & Queries',
          stichworte: 'platzhalter query vorlage baustein variable feldnamen' },
        // Dokumentvorlagen (W3, Build 425): Autoren-Maske der Redakteur:in fuer
        // wiederverwendbare Berichts-Gerueste (report_templates). Gleiche Gruppe
        // 'Redaktion' und gleiches Recht templates.edit wie W2.
        { id: 'doctemplates', cap: 'templates.edit',    group: 'Redaktion',      label: 'Dokumentvorlagen',
          stichworte: 'dokumentvorlage vorlage bericht layout gliederung docx' },
        // Baustein-Module (W1, Build 427): Autoren-Maske der Redakteur:in fuer
        // wiederverwendbare Textbausteine (report_modules). Gleiche Gruppe
        // 'Redaktion' und Recht templates.edit wie W2/W3.
        { id: 'modules',   cap: 'templates.edit',       group: 'Redaktion',      label: 'Baustein-Module',
          stichworte: 'baustein modul textbaustein module_key vorschau bibliothek' },
        // Ermittlungsergebnis (Build 395). Recht: results.view. Ein Ermittler
        // mit Scope 'eigene' sieht die Sicht ebenfalls — er bekommt dann die
        // Abdeckung SEINER Faelle; die fallUEBERGREIFENDE Verteilung (/stats)
        // bleibt Scope 'alle' vorbehalten und wird in der Sicht BENANNT, statt
        // als leere Flaeche zu erscheinen.
        { id: 'results',    cap: 'results.view',         group: 'Auswertung',     label: 'Ermittlungsergebnis',
          stichworte: 'ermittlungsergebnis erkenntnis befund ergebnis bewertung' },
        { id: 'stats',      cap: 'stats.export_sta',     group: 'Kennzahlen',     label: 'Statistiken (StA/Fuehrung)',
          stichworte: 'statistik kennzahl staatsanwaltschaft fuehrung zahlen diagramm' },
        { id: 'planung',    cap: 'stats.export_sta',     group: 'Kennzahlen',     label: 'Prognose & Gantt',
          stichworte: 'prognose gantt planung szenario termin dauer hochrechnung' },
        { id: 'annostats',  cap: 'stats.export_sta',     group: 'Auswertung',     label: 'Annotations-Statistik',
          stichworte: 'annotation markierung statistik tag schlagwort verteilung' },
        // Build 525 (AP-3A / Idee 32): Verjaehrungsfristen. Gruppe
        // 'Auswertung' und NICHT 'Administration': die Sicht wertet den
        // FALLBESTAND aus (Tatzeitpunkte, Fristen), nicht den Zustand der
        // Anlage. Eigenes Recht 'limitation.view' (Seed M031).
        { id: 'limitation', cap: 'limitation.view',      group: 'Auswertung',     label: 'Fristen (Verjaehrung)',
          stichworte: 'frist verjaehrung ablauf stichtag paragraph fristenkontrolle' },
        // Build 539 (AP-3B): Dringlichkeit & Erkenntnislage. Gruppe
        // 'Auswertung' wie die Fristensicht — beide werten den FALLBESTAND
        // aus, nicht den Zustand der Anlage. EIGENES Recht 'matrix.view'
        // (Seed M033) und NICHT 'limitation.view': wer die Fristen sehen
        // darf, darf damit noch nicht sehen, wie weit die Kolleginnen mit
        // ihren Bewertungen sind. NICHT scope-behaftet — eine Rangfolge ueber
        // den eigenen Arbeitsvorrat waere keine.
        { id: 'matrix',     cap: 'matrix.view',          group: 'Auswertung',     label: 'Dringlichkeit & Erkenntnislage',
          stichworte: 'dringlichkeit erkenntnislage matrix gewichtung ampel prioritaet' },
        // Build 543 (AP-3C): QS & Metriken. Gruppe 'Auswertung' — die Sicht
        // wertet den FALLBESTAND aus (Stichprobe, Abdeckung, Liegezeiten),
        // nicht den Zustand der Anlage. EIGENES Recht 'qs.view' (Seed M034);
        // das Ziehen und Pruefen haengt zusaetzlich an 'qs.edit', der
        // Kennzahlenteil an 'metrics.view' (M035). NICHT scope-behaftet: eine
        // Stichprobe ueber den eigenen Arbeitsvorrat waere keine.
        //
        // AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT.
        { id: 'qs',         cap: 'qs.view',              group: 'Kennzahlen',     label: 'QS & Metriken',
          stichworte: 'qualitaetssicherung stichprobe metrik pruefung vieraugen kontrolle' },
        { id: 'workload',   cap: 'workload.view',        group: 'Kennzahlen',     label: 'Lastverteilung',
          stichworte: 'last auslastung verteilung arbeitsmenge pensum ermittler' },
        { id: 'capacity',   cap: 'capacity.edit',        group: 'Kennzahlen',     label: 'Kapazitaet',
          stichworte: 'kapazitaet auswertung arbeitszeit verfuegbarkeit netto diagramm' },
        { id: 'support',    cap: 'support_history.view', group: 'Kennzahlen',     label: 'Support-Historie',
          stichworte: 'support historie hilfe anfrage sitzung unterstuetzung' },
        { id: 'mycases',    cap: 'mycases.view',         group: 'Persoenlich',    label: 'Meine Auftraege',
          stichworte: 'meine auftraege eigene faelle zugewiesen persoenlich' },
        { id: 'myhistory',  cap: 'myhistory.view',       group: 'Persoenlich',    label: 'Meine Historie',
          stichworte: 'meine historie eigene taetigkeit verlauf chronik persoenlich' },
        { id: 'policy',     cap: 'policy.view',          group: 'Administration', label: 'Rechte / Policy',
          stichworte: 'recht rolle policy berechtigung faehigkeit grant rbac' },
        { id: 'integrity',  cap: 'ops.view',             group: 'Administration', label: 'Integritaet / Betrieb',
          stichworte: 'integritaet betrieb pruefsumme hashkette backup speicher system' },
        { id: 'audit',      cap: 'ops.view',             group: 'Administration', label: 'Audit-Explorer',
          stichworte: 'audit beleg protokoll kette nachweis revision ereignis' },
        // Build 520 (AP-2G / Idee 30): Uebergabe-Protokoll (Frontend zu 520).
        // Gruppe 'Administration' DIREKT neben dem Audit-Explorer, denn es ist
        // dieselbe Art Werkzeug: eine LESART der unveraenderlichen Audit-Kette.
        // Eigenes Recht 'handover.view' (Seed M029, default-deny) und BEWUSST
        // NICHT scope-behaftet — auf die eigenen Eintraege verengt entstuende
        // ein Protokoll MIT LUECKEN, das vollstaendig aussieht.
        { id: 'handover',   cap: 'handover.view',        group: 'Administration', label: 'Übergabe-Protokoll',
          stichworte: 'uebergabe protokoll schichtwechsel dienstuebergabe abgabe' },
        // Build 521 (AP-2G / Idee 29): Aufbewahrungsfristen (Frontend zu 521).
        // Gruppe 'Administration' — es ist eine Governance-/Betriebsaufgabe.
        // EIGENES Recht 'retention.view' statt 'ops.view': die uebrigen
        // ops.view-Sichten zeigen den Zustand der ANLAGE, diese eine LISTE VON
        // FAELLEN mit Beschuldigten-Kontonamen. MIT DIESEM EINTRAG IST KEIN
        // LOESCHEN VERBUNDEN - die Sicht ist rein auswertend.
        { id: 'retention',  cap: 'retention.view',       group: 'Administration', label: 'Aufbewahrungsfristen',
          stichworte: 'aufbewahrung loeschfrist retention archivierung lebensdauer' },
        { id: 'promotion',  cap: 'ops.view',             group: 'Administration', label: 'Fremdforum-Promotion',
          stichworte: 'fremdforum promotion externes forum uebernahme quelle' },
        { id: 'releases',   cap: 'release.view',         group: 'Administration', label: 'Externe Fallfreigabe',
          stichworte: 'freigabe extern fallfreigabe lka verteilung weitergabe' },
        { id: 'onboarding', cap: 'onboarding.view',      group: 'Betreuung',     label: 'Onboarding / Offboarding',
          stichworte: 'onboarding offboarding eintritt austritt checkliste zugang' },
        // Build 503: Personalverwaltung (personnel.view, Seed M021) ERSETZT
        // den separaten Eintrag 'adsync' aus Build 502 — der AD-Abgleich ist
        // jetzt ABSCHNITT der Personal-Seite (mc 2026-07-24: "Auf jener Seite
        // sollte dann auch die Einbindung sein"); sein Abschnitt erscheint
        // dort nur mit personnel.sync.
        { id: 'personnel',  cap: 'personnel.view',       group: 'Personal',     label: 'Personalverwaltung',
          stichworte: 'personal person mitarbeiter rolle konto stammdaten ad' },
        // Build 471 (AP-2A(2b)): Katalog identifizierter Personen (Konto->reale
        // Person) mit Konfidenzstufe. Auswertungs-Sicht; Recht crossref.view.
        { id: 'crossref',   cap: 'crossref.view',        group: 'Identitaeten',     label: 'Kreuzbezug',
          stichworte: 'kreuzbezug querverweis verbindung bezug verknuepfung' },
        // Build 478 (AP-2A(3)): Querfund-Meta-Uebersicht (rein lesend, Frontend
        // zu /api/crossfindings). Gleiche F5-Familie; Recht crossref.view.
        { id: 'crossfindings', cap: 'crossref.view',     group: 'Identitaeten',     label: 'Querfunde',
          stichworte: 'querfund fremder fall hinweis stpo rueckkanal meldung' },
        // Build 505 (AP-2A/A1, Idee 8): globaler Alias-Katalog (Frontend zu
        // 504). EIGENE Sicht statt Anbau an 'crossref': Aliasse existieren
        // UNABHAENGIG vom Identitaetskatalog — ein Konto kann Aliasse und
        // KEINE Identifizierung haben; ein Anbau haette diese Faelle
        // unsichtbar gemacht (Grundregel 1). Gleiche F5-Familie, Recht
        // crossref.view (Pflegen zusaetzlich crossref.edit).
        { id: 'alias',      cap: 'crossref.view',        group: 'Identitaeten',     label: 'Aliasse',
          stichworte: 'alias nickname zweitname benutzername schreibweise' },
        // Build 510 (AP-2A/A3, Idee 11): Identitaets-Gruppen (Merge/Split,
        // Frontend zu 509). EIGENE Sicht — eine Zusammenfuehrung besteht
        // UNABHAENGIG davon, ob eines der Konten identifiziert oder mit
        // Aliassen versehen ist; gerade der haeufige Fall ist "dieselbe
        // Person, aber noch unbekannt WER". Recht crossref.view
        // (Pflegen zusaetzlich crossref.edit).
        { id: 'merge',      cap: 'crossref.view',        group: 'Identitaeten',     label: 'Identitäts-Gruppen',
          stichworte: 'identitaet gruppe zusammenfuehren merge split person subjekt' },
        // Build 563 (AP-3E / Idee 38, Instanz B): fallUEBERGREIFENDE
        // Volltextsuche. Gruppe 'Auswertung' neben Aliassen und
        // Identitaets-Gruppen: alle drei beantworten dieselbe Frage —
        // "gehoert das zusammen?" —, diese hier als einzige ueber die
        // Grenze des eigenen Falls hinweg. Recht 'evidence.fulltext_search'
        // (seit M006 im Katalog, default-deny) und BEWUSST NICHT
        // scope-behaftet: auf 'eigene' verengt beantwortete die Sicht genau
        // die Frage nicht, fuer die es sie gibt.
        //
        // DIE SICHT ZEIGT IN STUFE 1 KEINEN TEXT. Wer den Inhalt eines
        // fremden Falls sehen will, braucht eine belegte Freigabe
        // (fulltext.release, M036) — die Sperre steht in der Zeile, samt
        // dem Weg zur Anfrage.
        { id: 'search',     cap: 'evidence.fulltext_search', group: 'Auswertung', label: 'Volltextsuche',
          stichworte: 'volltextsuche suchen begriff fundstelle beweismittel text' },
        // Build 546 (AP-3G / Idee 37): die Sicht, mit der man die uebrigen
        // Sichten einrichtet. Gruppe 'Persoenlich', weil sie ausschliesslich
        // die EIGENE Oberflaeche betrifft.
        //
        // 'immer: true' — SIE IST DIE EINZIGE SICHT OHNE RECHTEPRUEFUNG.
        // BESTAETIGT von mc am 2026-07-26; das ist Absicht. Es gibt an ihr
        // nichts zu schuetzen: sie zeigt keine Fall- und keine
        // Personendaten, sondern nur die eigene Einrichtung.
        // Haengte sie an einem Recht, muesste jemand dieses Recht erst
        // erteilen (default-deny) — und bis dahin kaeme niemand an seine
        // eigenen Einstellungen. Ein Recht, das man niemandem sinnvoll
        // vorenthalten kann, ist keines.
        //
        // Sie steht ausserdem in NICHT_STEUERBAR (viewpref_katalog.py): wer
        // sie ausblenden koennte, mauerte sich den Rueckweg zu.
        { id: 'viewprefs',  cap: null, immer: true, group: 'Persoenlich', label: 'Ansicht anpassen',
          stichworte: 'ansicht anpassen reihenfolge ausblenden navigation gruppen kacheln' },
        // Build 559: Kapazitaetspflege. EIGENE Sicht neben der
        // Auswertung ('capacity'), nach demselben Muster wie
        // 'policy' (nur lesend) / 'personnel' (Pflege). Recht ist
        // 'capacity.edit' — dasselbe wie bei der Auswertung; den
        // Unterschied traegt der SCOPE ('alle' = alle Personen,
        // 'eigene' = Selbstpflege, heute an niemanden vergeben).
        // Gruppe 'Verwaltung' und nicht 'Auswertung': dort sucht
        // eine personalverantwortliche Person, neben der
        // Personalverwaltung (mc 2026-07-29).
        { id: 'capacity_pflege', cap: 'capacity.edit',   group: 'Personal',     label: 'Kapazitaetspflege',
          stichworte: 'arbeitszeit urlaub krank schulung abwesenheit feiertag minuten pflege' }
    ];

    // Gueltige Scope-Werte fuer die Anzeige (weitere -> kein Tag).
    var VALID_SCOPES = { alle: true, eigene: true };

    // =========================================================================
    // 2) REINE FUNKTIONEN (kein DOM). Genau diese testet vitest.
    // =========================================================================

    // hasCap: besitzt die Person die Faehigkeit? Praesenz des Schluessels zaehlt
    // (scope darf null sein — z.B. global geltende Faehigkeiten).
    function hasCap(capabilities, cap) {
        return !!capabilities
            && Object.prototype.hasOwnProperty.call(capabilities, cap);
    }

    // visibleViews: Sichten, deren Faehigkeit vorliegt — in Katalog-Reihenfolge.
    // Gibt eine NEUE Liste zurueck (mutiert VIEW_CATALOG nicht).
    // viewCaps: Faehigkeiten, von denen EINE genuegt (any-of). Faellt auf die
    // Einzel-Faehigkeit 'cap' zurueck (Rueckwaertskompatibilitaet).
    function viewCaps(v) {
        return (v.caps && v.caps.length) ? v.caps : [v.cap];
    }

    // effectiveCap: die erste vorhandene Faehigkeit der Sicht (fuer Scope-Tag).
    function effectiveCap(v, capabilities) {
        var caps = viewCaps(v);
        for (var i = 0; i < caps.length; i++) {
            if (hasCap(capabilities, caps[i])) { return caps[i]; }
        }
        return v.cap;
    }

    // Build 546: visibleViews arbeitet jetzt auf einer UEBERGEBENEN Liste
    // (Vorgabe: der Katalog). Das ist die Voraussetzung dafuer, dass der
    // Rechtefilter ZULETZT laufen kann — er bekommt die bereits nach der
    // Vorliebe geordnete Liste und nicht umgekehrt (s. navViews).
    //
    // 'immer: true' umgeht die Rechtepruefung. Genau EIN Katalogeintrag traegt
    // das Merkmal ('viewprefs'); die Begruendung steht dort.
    function visibleViews(capabilities, views) {
        var quelle = views || VIEW_CATALOG;
        return quelle.filter(function (v) {
            if (v.immer === true) { return true; }
            return viewCaps(v).some(function (c) {
                return hasCap(capabilities, c);
            });
        });
    }

    // =========================================================================
    // Build 546 (AP-3G / Idee 37): persoenliche Ansichtseinstellung anwenden.
    //
    // REIHENFOLGE, DIE NICHT VERHANDELBAR IST (Bauplan Welle 3 §3):
    //     VIEW_CATALOG  ->  applyViewPrefs  ->  visibleViews(capabilities)
    // Der Rechtefilter steht HINTEN. applyViewPrefs kann konstruktiv nichts
    // hinzufuegen — es ordnet und markiert nur —, also kann eine Vorliebe
    // keine Sicht einblenden, fuer die das Recht fehlt. Wird ein Recht spaeter
    // entzogen, verschwindet die Sicht trotz gespeicherter Vorliebe.
    // =========================================================================

    // applyViewPrefs: ordnet 'views' nach der gespeicherten Vorliebe und
    // markiert jeden Eintrag mit 'versteckt'. Gibt eine NEUE Liste mit NEUEN
    // Objekten zurueck (der Katalog bleibt unberuehrt).
    //
    // prefs: [{key, sichtbar}] in gewuenschter Reihenfolge (aus /api/viewprefs).
    //
    // SICHTEN, DIE DIE VORLIEBE NICHT KENNT, STEHEN HINTEN UND SIND SICHTBAR.
    // Das ist die wichtigste Entscheidung dieser Funktion: eine Sicht, die es
    // bei der letzten Speicherung noch nicht gab, darf nicht dadurch
    // unsichtbar werden, dass jemand vor einem halben Jahr etwas eingerichtet
    // hat. Ein neuer Eintrag soll AUFFALLEN und nicht verschwinden
    // (Grundregel 1, sinngemaess).
    function applyViewPrefs(views, prefs) {
        var quelle = views || [];
        if (!prefs || !prefs.length) {
            return quelle.map(function (v) {
                var k = {};
                for (var f in v) {
                    if (Object.prototype.hasOwnProperty.call(v, f)) { k[f] = v[f]; }
                }
                k.versteckt = false;
                return k;
            });
        }

        var rang = {};
        var sichtbarkeit = {};
        prefs.forEach(function (p, i) {
            if (!p || typeof p.key !== 'string') { return; }
            rang[p.key] = i;
            sichtbarkeit[p.key] = (p.sichtbar !== false);
        });

        var bekannt = [];
        var unbekannt = [];   // vom Katalog, aber nicht von der Vorliebe
        quelle.forEach(function (v, i) {
            var kopie = {};
            for (var f in v) {
                if (Object.prototype.hasOwnProperty.call(v, f)) { kopie[f] = v[f]; }
            }
            if (Object.prototype.hasOwnProperty.call(rang, v.id)) {
                kopie.versteckt = !sichtbarkeit[v.id];
                kopie._rang = rang[v.id];
                bekannt.push(kopie);
            } else {
                kopie.versteckt = false;
                kopie._rang = i;
                unbekannt.push(kopie);
            }
        });
        bekannt.sort(function (a, b) { return a._rang - b._rang; });
        unbekannt.sort(function (a, b) { return a._rang - b._rang; });

        return bekannt.concat(unbekannt).map(function (v) {
            delete v._rang;
            return v;
        });
    }

    // navViews: die Sichten, die in der Navigation ERSCHEINEN — geordnet nach
    // Vorliebe, gefiltert nach Recht (in DIESER Reihenfolge), ohne die
    // versteckten.
    function navViews(capabilities, prefs) {
        var sichtbar = visibleViews(capabilities,
                                    applyViewPrefs(VIEW_CATALOG, prefs))
            .filter(function (v) { return v.versteckt !== true; });
        // Ohne gespeicherte Vorliebe gilt die Vorgabefolge; mit Vorliebe gilt
        // die eigene (erstes Auftreten in der gespeicherten Liste).
        return nachGruppenOrdnen(sichtbar,
                                 (prefs && prefs.length) ? null : GROUP_ORDER);
    }

    // hiddenCount: wie viele Sichten hat die Person ausgeblendet, die sie
    // sehen DUERFTE? Nur diese Zahl gehoert in die Navigation — Sichten ohne
    // Recht sind nicht 'ausgeblendet', sondern nicht vorhanden, und sie
    // mitzuzaehlen waere eine Auskunft ueber fremde Rechte.
    function hiddenCount(capabilities, prefs) {
        return visibleViews(capabilities, applyViewPrefs(VIEW_CATALOG, prefs))
            .filter(function (v) { return v.versteckt === true; }).length;
    }

    // scopeTag: Scope-Text fuer die Nav ('alle'/'eigene') oder '' (kein Tag,
    // z.B. bei scope null oder unbekanntem Wert).
    function scopeTag(cap, capabilities) {
        if (!hasCap(capabilities, cap)) { return ''; }
        var s = capabilities[cap];
        return VALID_SCOPES[s] ? s : '';
    }

    // firstViewId: ID der ersten sichtbaren Sicht oder null (Startauswahl /
    // Rueckfall, wenn die aktive Sicht nicht mehr sichtbar ist).
    function firstViewId(views) {
        return (views && views.length) ? views[0].id : null;
    }

    // groupSequence: geordnete, eindeutige Gruppenfolge der sichtbaren Sichten
    // (bestimmt die Reihenfolge der Nav-Gruppenkoepfe).
    // GROUP_ORDER (Build 568): die VORGABE-Reihenfolge der Gruppen. Sie steht
    // hier ausdruecklich und ergibt sich NICHT mehr aus der Katalogfolge:
    // welche Sicht zufaellig als erste ihrer Gruppe im Katalog steht, ist eine
    // Nebensache der Dateipflege und taugt nicht als Aussage darueber, in
    // welcher Ordnung jemand arbeitet.
    //
    // Die Folge liest sich als Arbeitsweg: Ueberblick -> Fall -> Betreuung ->
    // Abnahme -> Redaktion -> Auswertung -> Identitaeten -> Kennzahlen ->
    // Personal -> Administration, und ganz zuletzt das Persoenliche
    // (Einstellungen sucht man am Ende, nicht in der Mitte).
    //
    // WER SEINE EIGENE ORDNUNG GESPEICHERT HAT, dem gilt seine eigene: dann
    // bestimmt das erste Auftreten in der gespeicherten Liste die
    // Gruppenfolge, und GROUP_ORDER bleibt aussen vor.
    var GROUP_ORDER = [
        'Ueberblick', 'Fallsteuerung', 'Betreuung', 'Abnahme', 'Redaktion',
        'Auswertung', 'Identitaeten', 'Kennzahlen', 'Personal',
        'Administration', 'Persoenlich'
    ];

    // =====================================================================
    // NAVIGATIONSSUCHE (Build 569, Ticket ace2cc2a)
    // =====================================================================
    // WOGEGEN GESUCHT WIRD: Beschriftung, Gruppe und die GEPFLEGTEN
    // Stichworte am Katalogeintrag ('stichworte'). Ausdruecklich NICHT die
    // Texte der Masken selbst - die entstehen erst mit Serverdaten, und ein
    // aus den Quellen geerntetes Verzeichnis waere bei der PFLEGE
    // veraltbar: jemand aendert eine Maske, niemand fuehrt den Generator
    // aus, und die Suche findet die Sicht ab dann nicht mehr, ohne dass es
    // auffaellt. Statt dessen pflegt der Maintainer einer Sicht ihre
    // Stichworte mit (mc 2026-07-29), und die Konformitaetspruefung
    // NS10/NS11 verlangt sie fuer JEDE Sicht - Vergessen faellt sofort auf.
    //
    // UMLAUTE IN BEIDE RICHTUNGEN: der Katalog mischt Schreibweisen
    // ('Naechstbeste Aktion' neben 'Fristen (Verjaehrung)', 'Kapazitaet'
    // neben 'Identitaets-Gruppen'). Wer 'kapazität' eingibt, muss
    // 'Kapazitaet' finden, und wer 'naechstbeste' tippt, muss 'Nächstbeste'
    // finden. Deshalb wird auf BEIDEN Seiten gefaltet - Suchbegriff UND
    // Suchtext -, nicht nur auf einer.
    function suchNormal(text) {
        return String(text === null || text === undefined ? '' : text)
            .toLowerCase()
            .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue')
            .replace(/ß/g, 'ss')
            .replace(/[^a-z0-9]+/g, ' ')
            .trim();
    }

    // sichtSuchtext: der Wortschatz EINER Sicht, normalisiert.
    function sichtSuchtext(v) {
        if (!v) { return ''; }
        return suchNormal([v.label, v.group, v.stichworte, v.id].join(' '));
    }

    // suchBegriffe: Eingabe -> Liste normalisierter Begriffe.
    function suchBegriffe(query) {
        var n = suchNormal(query);
        return n ? n.split(' ').filter(function (t) { return t.length > 0; }) : [];
    }

    // sichtPasst: ALLE Begriffe muessen vorkommen (UND). Eingrenzen verhaelt
    // sich damit so, wie man es erwartet: jedes weitere Wort macht die Liste
    // kuerzer, nicht laenger. Teilwortsuche - 'kapa' findet 'kapazitaet'.
    function sichtPasst(v, begriffe) {
        if (!begriffe || !begriffe.length) { return true; }
        var text = sichtSuchtext(v);
        for (var i = 0; i < begriffe.length; i++) {
            if (text.indexOf(begriffe[i]) === -1) { return false; }
        }
        return true;
    }

    // navSuche: filtert eine SCHON rechtegefilterte und geordnete Liste.
    // Die Reihenfolge bleibt unangetastet - keine Trefferwertung (mc).
    //
    // WICHTIG: diese Funktion bekommt NIE den VIEW_CATALOG, sondern immer
    // das Ergebnis von navViewsAlle(). Sonst verriete das Suchfeld, welche
    // Sichten es gibt, fuer die einem das Recht fehlt. NS08 prueft das.
    function navSuche(views, query) {
        var begriffe = suchBegriffe(query);
        if (!begriffe.length) { return (views || []).slice(); }
        return (views || []).filter(function (v) {
            return sichtPasst(v, begriffe);
        });
    }

    // navViewsAlle: wie navViews, aber MIT den ausgeblendeten Sichten (das
    // Merkmal 'versteckt' bleibt an der Zeile stehen).
    //
    // Grundlage der Suche (mc 2026-07-29): "So sollen auch Sichten gefunden
    // werden, die sonst ausgeblendet sind. Das ermoeglicht es eine
    // aufgeraeumte Navigation zu haben und dennoch an die gewuenschte Sicht
    // zu gelangen." Das Recht bleibt die Grenze - ausgeblendet ist eine
    // Aufraeum-Entscheidung, kein Rechteentzug.
    function navViewsAlle(capabilities, prefs) {
        var angewandt = applyViewPrefs(VIEW_CATALOG, prefs);
        return nachGruppenOrdnen(
            visibleViews(capabilities, angewandt),
            (prefs && prefs.length) ? null : GROUP_ORDER);
    }

    // nachGruppenOrdnen: bringt eine flache Sichtliste in GRUPPENREINE Form —
    // jede Gruppe steht am Stueck, in der Reihenfolge 'gruppenfolge' (fehlende
    // Gruppen hinten, nach erstem Auftreten). Die Reihenfolge INNERHALB einer
    // Gruppe bleibt unangetastet.
    //
    // WARUM DAS NOETIG IST (Befund Build 568): die Vorlieben sind eine FLACHE
    // Liste, und die Bedienoberflaeche liess bis Build 567 freies Umsortieren
    // ueber Gruppengrenzen zu. buildNav setzt einen Gruppenkopf, sobald sich
    // v.group aendert - eine verschraenkte Liste erzeugte deshalb DENSELBEN
    // Gruppenkopf mehrfach. Nachweisbar mit der Folge
    // Ueberblick/dashboard -> Verwaltung/assignment -> Ueberblick/calendar:
    // drei Koepfe fuer zwei Gruppen. groupSequence zaehlte dabei zwei, buildNav
    // zeichnete drei - die beiden waren sich nicht einig.
    //
    // Diese Funktion stellt die Gruppenreinheit beim LESEN her. Damit ist der
    // Fehler auch fuer Vorlieben behoben, die bereits verschraenkt in der
    // Datenbank stehen - ohne Migration, ohne dass jemand etwas nachpflegen
    // muss. UNBEKANNTE Gruppen werden ANGEHAENGT, nie verworfen (Grundregel 1).
    function nachGruppenOrdnen(views, gruppenfolge) {
        var liste = views || [];
        var proGruppe = {};
        var erstesAuftreten = [];
        liste.forEach(function (v) {
            var g = v && v.group;
            if (!Object.prototype.hasOwnProperty.call(proGruppe, g)) {
                proGruppe[g] = [];
                erstesAuftreten.push(g);
            }
            proGruppe[g].push(v);
        });
        var folge = [];
        (gruppenfolge || []).forEach(function (g) {
            if (Object.prototype.hasOwnProperty.call(proGruppe, g)
                    && folge.indexOf(g) === -1) { folge.push(g); }
        });
        erstesAuftreten.forEach(function (g) {
            if (folge.indexOf(g) === -1) { folge.push(g); }
        });
        var out = [];
        folge.forEach(function (g) {
            out = out.concat(proGruppe[g]);
        });
        return out;
    }

    function groupSequence(views) {
        var seen = {};
        var out = [];
        (views || []).forEach(function (v) {
            if (!Object.prototype.hasOwnProperty.call(seen, v.group)) {
                seen[v.group] = true;
                out.push(v.group);
            }
        });
        return out;
    }

    // viewById: Katalogeintrag zu einer ID (oder null).
    function viewById(id) {
        for (var i = 0; i < VIEW_CATALOG.length; i++) {
            if (VIEW_CATALOG[i].id === id) { return VIEW_CATALOG[i]; }
        }
        return null;
    }

    // =========================================================================
    // 3) DOM-FUNKTIONEN (nur Browser/jsdom). Beruehren document.
    // =========================================================================

    // setWho: Anzeigename in die Kopfleiste schreiben. display_name via
    // textContent (AD-Herkunft -> XSS-sicher), system_username in Klammern.
    function setWho(whoEl, displayName, systemUsername) {
        if (!whoEl) { return; }
        whoEl.textContent = '';
        var strong = document.createElement('strong');
        strong.textContent = displayName || '?';
        whoEl.appendChild(document.createTextNode('angemeldet als '));
        whoEl.appendChild(strong);
        if (systemUsername) {
            whoEl.appendChild(
                document.createTextNode(' (' + systemUsername + ')'));
        }
    }

    // navGeruest: legt die zwei Faecher der Leiste an und gibt das Fach fuer
    // die EINTRAEGE zurueck. Idempotent - mehrfaches Aufrufen aendert nichts.
    //
    // WARUM UEBERHAUPT: buildNav leert das Element, das es bekommt
    // (navEl.textContent = ''). Laege das Suchfeld darin, wuerde es bei JEDEM
    // Tastendruck neu gebaut - Fokus und Schreibmarke waeren weg, und nach dem
    // ersten Buchstaben waere Schluss. Das Feld bekommt deshalb ein eigenes
    // Fach, das buildNav nie anfasst.
    function navGeruest(navEl) {
        if (!navEl) { return null; }
        var suchfach = navEl.querySelector(':scope > .aiw-navsuche');
        var liste = navEl.querySelector(':scope > .aiw-navliste');
        if (!suchfach) {
            suchfach = document.createElement('div');
            suchfach.className = 'aiw-navsuche';
            navEl.appendChild(suchfach);
        }
        if (!liste) {
            liste = document.createElement('div');
            liste.className = 'aiw-navliste';
            navEl.appendChild(liste);
        }
        return liste;
    }

    // buildNavSuche: das Suchfeld. Wird BEIM ERSTEN MAL gebaut und danach nur
    // noch gepflegt - das Element bleibt dasselbe, damit der Fokus beim Tippen
    // erhalten bleibt. Der Wert wird nur gesetzt, wenn er abweicht: ein
    // Zuweisen des gleichen Wertes wuerde in manchen Browsern die
    // Schreibmarke ans Ende springen lassen.
    function buildNavSuche(navEl, wert, onEingabe, trefferInfo) {
        if (!navEl) { return null; }
        navGeruest(navEl);
        var fach = navEl.querySelector(':scope > .aiw-navsuche');
        var feld = fach.querySelector('.aiw-navsuche-feld');
        if (!feld) {
            feld = document.createElement('input');
            feld.type = 'search';
            feld.className = 'aiw-navsuche-feld';
            feld.id = 'aiw-navsuche-feld';
            feld.setAttribute('placeholder', 'Sicht suchen \u2026');
            feld.setAttribute('aria-label',
                              'Sichten nach Begriff oder Stichwort filtern');
            feld.setAttribute('autocomplete', 'off');
            // Build 636 (Vorgang 17200856): Hilfe-Marke, LITERAL gesetzt.
            // Die Shell gehoert zu keiner Sicht - ihre Texte stehen in
            // management/help/inhalt/shell.py unter dem Praefix 'shell.'.
            feld.setAttribute('data-hilfe-id', 'shell.bedienung.navsuche');
            fach.appendChild(feld);
            var info = document.createElement('div');
            info.className = 'aiw-navsuche-info';
            fach.appendChild(info);
            feld.addEventListener('input', function () {
                if (typeof onEingabe === 'function') { onEingabe(feld.value); }
            });
            // Escape leert das Feld - der schnellste Weg zurueck zur
            // vollstaendigen Leiste, ohne die Maus zu benutzen.
            feld.addEventListener('keydown', function (ev) {
                if (ev.key === 'Escape' && feld.value !== '') {
                    feld.value = '';
                    if (typeof onEingabe === 'function') { onEingabe(''); }
                }
            });
        }
        var soll = (wert === undefined || wert === null) ? '' : String(wert);
        if (feld.value !== soll) { feld.value = soll; }
        var infoEl = fach.querySelector('.aiw-navsuche-info');
        if (infoEl) {
            infoEl.textContent = trefferInfo || '';
        }
        return feld;
    }

    // buildNav: Navigation in 'navEl' neu aufbauen. views = sichtbare Sichten
    // (aus visibleViews), capabilities fuer die Scope-Tags, activeId markiert
    // die aktive Sicht, onSelect(viewId) wird bei Klick aufgerufen.
    // XSS-sicher: alle variablen Texte via textContent.
    // Build 546: zusaetzlicher Parameter 'versteckt' (Anzahl ausgeblendeter
    // Sichten). Optional — fehlt er, verhaelt sich buildNav wie bisher.
    // --- Build 568: EINGEKLAPPTE GRUPPEN -----------------------------------
    // Der Zustand liegt im localStorage und NICHT auf dem Server (mc
    // 2026-07-29: "Das ist alles Kosmetik. Kosmetik kann in den
    // localStorage."). Er sagt nichts ueber die Arbeitsweise aus, nur
    // darueber, was gerade zugeklappt ist - und er darf ruhig am Arbeitsplatz
    // haengenbleiben.
    var NAV_ZU_KEY = 'aiw.cockpit.navZu.v1';

    function navZuLesen() {
        try {
            var roh = window.localStorage.getItem(NAV_ZU_KEY);
            var d = roh ? JSON.parse(roh) : null;
            return (d && typeof d === 'object') ? d : {};
        } catch (e) {
            // Kein Speicher, kein Problem: dann ist eben alles aufgeklappt.
            return {};
        }
    }

    function navZuSchreiben(zu) {
        try {
            window.localStorage.setItem(NAV_ZU_KEY, JSON.stringify(zu || {}));
        } catch (e) { log('navZu nicht speicherbar', e); }
    }

    // navGruppeUmschalten: reine Zustandsrechnung, damit sie pruefbar ist.
    function navGruppeUmschalten(zu, gruppe) {
        var k = {};
        for (var f in (zu || {})) {
            if (Object.prototype.hasOwnProperty.call(zu, f)) { k[f] = zu[f]; }
        }
        k[gruppe] = !k[gruppe];
        return k;
    }

    function buildNav(navEl, views, capabilities, activeId, onSelect,
                      versteckt, suchInfo) {
        if (!navEl) { return; }
        navEl.textContent = '';
        var sucheAktiv = !!(suchInfo && suchInfo.aktiv);
        var zu = navZuLesen();
        // SOLANGE GEFILTERT WIRD, IST ALLES OFFEN. Ein Treffer, der in einer
        // zugeklappten Gruppe steckt, waere eine stille Auslassung - die Suche
        // haette ihn gefunden und die Leiste zeigte ihn nicht. Der gemerkte
        // Klappzustand bleibt unberuehrt und gilt wieder, sobald das Feld leer
        // ist.
        if (sucheAktiv) { zu = {}; }
        // EINE EINGEKLAPPTE GRUPPE MIT DER AKTIVEN SICHT WIRD AUFGEKLAPPT.
        // Sonst waere die eigene Auswahl unsichtbar, und die Leiste behauptete
        // stillschweigend, es gebe sie nicht.
        views.forEach(function (v) {
            if (v.id === activeId) { zu[v.group] = false; }
        });
        var lastGroup = null;
        var gruppenKoerper = null;
        views.forEach(function (v) {
            if (v.group !== lastGroup) {
                var g = document.createElement('button');
                g.className = 'aiw-navgroup';
                g.setAttribute('data-hilfe-id', 'shell.bedienung.navgruppe');
                g.setAttribute('type', 'button');
                g.setAttribute('data-group', v.group);
                var zuGeklappt = zu[v.group] === true;
                g.setAttribute('aria-expanded', zuGeklappt ? 'false' : 'true');
                var pfeil = document.createElement('span');
                pfeil.className = 'aiw-navgroup-pfeil';
                pfeil.textContent = zuGeklappt ? '\u25B8' : '\u25BE';
                g.appendChild(pfeil);
                var gname = document.createElement('span');
                gname.textContent = v.group;
                g.appendChild(gname);
                navEl.appendChild(g);

                gruppenKoerper = document.createElement('div');
                gruppenKoerper.className = 'aiw-navgroup-koerper';
                gruppenKoerper.setAttribute('data-group-body', v.group);
                if (zuGeklappt) { gruppenKoerper.hidden = true; }
                navEl.appendChild(gruppenKoerper);

                (function (gruppe) {
                    g.addEventListener('click', function () {
                        var neu = navGruppeUmschalten(navZuLesen(), gruppe);
                        navZuSchreiben(neu);
                        buildNav(navEl, views, capabilities, activeId,
                                 onSelect, versteckt, suchInfo);
                    });
                })(v.group);
                lastGroup = v.group;
            }
            var b = document.createElement('button');
            b.className = 'aiw-navitem' + (v.id === activeId ? ' active' : '');
            b.setAttribute('data-hilfe-id', 'shell.bedienung.navsicht');
            b.setAttribute('type', 'button');
            b.setAttribute('data-view-id', v.id);

            var labelSpan = document.createElement('span');
            labelSpan.textContent = v.label;
            b.appendChild(labelSpan);

            // AUSGEBLENDETE SICHT, DIE TROTZDEM DASTEHT (Build 569).
            // Sie erscheint, weil die Suche sie gefunden hat oder weil sie
            // gerade aktiv ist. Ohne Kennzeichen saehe sie aus wie eine
            // normale Eintragung - und die naechste Frage waere, warum sie
            // nach dem Leeren des Suchfelds wieder verschwindet.
            if (v.versteckt === true) {
                b.classList.add('aiw-navitem-versteckt');
                var vm = document.createElement('span');
                vm.className = 'aiw-navitem-vmark';
                vm.textContent = 'ausgeblendet';
                vm.title = 'Diese Sicht ist in "Ansicht anpassen" '
                    + 'ausgeblendet und erscheint hier nur wegen der Suche '
                    + 'oder weil sie gerade geoeffnet ist.';
                b.appendChild(vm);
            }

            var scope = scopeTag(effectiveCap(v, capabilities), capabilities);
            if (scope) {
                var tag = document.createElement('span');
                tag.className = 'aiw-scopetag ' + scope;
                tag.textContent = scope;
                b.appendChild(tag);
            }

            b.addEventListener('click', function () {
                log('Nav-Klick', v.id);
                if (typeof onSelect === 'function') { onSelect(v.id); }
            });
            // In den Gruppenkoerper, damit das Einklappen genau die Eintraege
            // dieser Gruppe trifft. Der Rueckfall auf navEl greift nur, wenn
            // buildNav ohne Gruppen aufgerufen wuerde - dann bleibt es beim
            // alten Verhalten statt bei einer leeren Leiste.
            (gruppenKoerper || navEl).appendChild(b);
        });

        // KEIN TREFFER WIRD BENANNT, MIT ZAHL (Build 569). Eine leere Leiste
        // saehe wie ein Fehler aus; die Zahl sagt, wogegen gesucht wurde.
        if (sucheAktiv && views.length === 0) {
            var leer = document.createElement('div');
            leer.className = 'aiw-navsuche-leer';
            var n = (typeof suchInfo.gesamt === 'number') ? suchInfo.gesamt : 0;
            leer.textContent = 'Kein Treffer unter ' + n
                + (n === 1 ? ' erreichbaren Sicht.' : ' erreichbaren Sichten.');
            navEl.appendChild(leer);
        }

        // Build 546 (AP-3G): DER ZAEHLER DER AUSGEBLENDETEN SICHTEN.
        //
        // Er ist die Gegenleistung dafuer, dass Ausblenden ueberhaupt erlaubt
        // ist. Eine ausgeblendete Eskalationssicht koennte eine uebersehene
        // Eskalation bedeuten; deshalb darf nichts STILL verschwinden. Die
        // Zeile steht dauerhaft in der Navigation, nennt die Zahl und fuehrt
        // mit einem Klick dorthin, wo man es rueckgaengig macht.
        //
        // Gezaehlt werden NUR Sichten, die die Person sehen duerfte. Sichten
        // ohne Recht sind nicht 'ausgeblendet', sondern nicht vorhanden.
        if (typeof versteckt === 'number' && versteckt > 0) {
            var hint = document.createElement('button');
            hint.className = 'aiw-navhidden';
            hint.setAttribute('data-hilfe-id',
                'shell.bedienung.ausgeblendet');
            hint.setAttribute('type', 'button');
            hint.textContent = versteckt === 1
                ? '1 Sicht ausgeblendet'
                : (versteckt + ' Sichten ausgeblendet');
            hint.title = 'Ausgeblendete Sichten bleiben über die '
                + 'Kommandopalette (Strg-K) erreichbar. Klicken zum Anpassen.';
            hint.addEventListener('click', function () {
                if (typeof onSelect === 'function') { onSelect('viewprefs'); }
            });
            navEl.appendChild(hint);
        }
        log('Nav gebaut:', views.length, 'Sichten, aktiv:', activeId,
            'ausgeblendet:', versteckt || 0);
    }

    // renderPlaceholder: Leerzustand fuer die gewaehlte Sicht (Build 347). Die
    // echte Sicht-Verdrahtung folgt in 348.
    function renderPlaceholder(mainEl, view) {
        if (!mainEl) { return; }
        mainEl.textContent = '';
        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = view ? view.label : 'Keine Sicht verfuegbar';
        mainEl.appendChild(h);

        var p = document.createElement('p');
        p.className = 'aiw-pagesub';
        p.textContent = view
            ? ('Faehigkeit: ' + view.cap)
            : 'Fuer diese Identitaet ist keine Sicht freigegeben (default-deny).';
        mainEl.appendChild(p);

        if (view) {
            var box = document.createElement('div');
            box.className = 'aiw-placeholder';
            box.textContent = 'Diese Sicht wird in einem Folge-Build (348) '
                + 'verdrahtet. Das Fundament (Navigation, Rechte) ist aktiv.';
            mainEl.appendChild(box);
        }
    }

    // =========================================================================
    // 4) BOOT — im Browser: whoami holen, Nav bauen, erste Sicht anzeigen.
    // =========================================================================

    // Zustand lebt nur im Speicher (kein localStorage — Projekt-/Artefakt-Regel).
    // table = aktuelle Tabulator-Instanz (Build 348, Overview); sse = EventSource.
    var state = {
        capabilities: {}, activeId: null,
        // Build 569: der aktuelle Suchbegriff der Navigationsleiste. Er wird
        // NICHT gespeichert - weder auf dem Server noch im localStorage. Ein
        // Filter ist ein Moment und keine Vorliebe; wer die Anwendung neu
        // oeffnet, will die vollstaendige Leiste sehen und nicht raten
        // muessen, warum die Haelfte fehlt.
        navSuche: '',
        // Build 546 (AP-3G): die gespeicherte Ansichtseinstellung dieser
        // Person. [] heisst 'nichts gespeichert' -> Werkseinstellung; null
        // heisst 'noch nicht geladen'. Der Unterschied ist wichtig, damit ein
        // AUSGEFALLENER Abruf nicht wie 'nichts eingestellt' aussieht.
        viewPrefs: null,
        // Build 547: die Kachelauswahl des Ueberblicks. null = nichts
        // gespeichert -> Werkseinstellung; [] = alle Kacheln abgewaehlt.
        viewPrefsWidgets: null,
        viewPrefsKatalog: null,
        viewPrefsUnbekannt: [],
        viewPrefsFehler: null,
        table: null,        // aktuelle Tabulator-Instanz (Overview)
        tables: [],         // mehrere Tabulator-Instanzen (Policy-Sicht)
        charts: [],         // mehrere ECharts-Instanzen (Statistik-Sicht)
        chart: null,        // aktuelle ECharts-Instanz (Lastverteilung/Kapazitaet)
        chartResize: null,  // Resize-Handler der ECharts-Instanz
        capacityPeriod: null,  // {start, end} der Kapazitaets-Sicht (SSE-Reload)
        mentoringTimer: null,  // Intervall-Handle des Betreuungs-Live-Refresh
        sse: null,
        // Schreib-Token (Build 372/373): kommt aus /api/whoami und MUSS bei
        // jedem POST als 'X-AIW-Token' mitgeschickt werden.
        writeToken: null,
        // Build 475: Uebergabe eines aus einem Bericht erzeugten Vorlagen-
        // Entwurfs vom Lektorat an die Dokumentvorlagen-Sicht. {draft, findings,
        // warnings} oder null. Wird von loadDocTemplates EINMALIG konsumiert.
        pendingTemplateDraft: null,
        // Build 600: Ergebnis der Namensaufloesung zur aktuellen
        // Alias-Suche (GET /api/names). Lebt im State und NICHT im
        // localStorage: es ist ein Abfrageergebnis, kein Bedienzustand — es
        // waere nach einem Neustart schlicht falsch.
        aliasNamen: null
    };

    // fetchJson: kleiner Wrapper mit DEV-Logging und klarer Fehlermeldung.
    // fetchJson: LESENDER Abruf.
    //
    // BUILD 657 - DER ANTWORTKOERPER WIRD NICHT MEHR WEGGEWORFEN.
    //
    // Bis Build 656 stand hier nur 'HTTP 500 bei <url>'. Der Server schickte
    // daneben 'detail' und (seit diesem Build) 'massnahme' - also den Satz,
    // der sagt, WAS ZU TUN IST. Beides landete im Papierkorb, und am
    // Bildschirm stand eine Zahl.
    //
    // Am 2026-08-02 hat genau das eine Stunde gekostet: der Server wusste
    // 'no such column: block_type', der Browser zeigte '500'. postJson
    // daneben wertet Fehlerkoerper seit jeher aus ("Grundregel 1: kein
    // stiller Fehlschlag") - der Lesepfad war der taube von beiden.
    //
    // Der Koerper wird DEFENSIV gelesen: eine Fehlerantwort muss kein JSON
    // sein (ein Proxy, eine Zwischenschicht, ein Absturz vor dem Handler).
    // Schlaegt das Lesen fehl, bleibt es bei der Zahl - aber dann, weil
    // wirklich nichts da war, und nicht, weil niemand nachgesehen hat.
    function fetchJson(url) {
        log('fetch', url);
        return fetch(url, { headers: { 'Accept': 'application/json' } })
            .then(function (r) {
                if (r.ok) { return r.json(); }
                return r.text().then(function (roh) {
                    var zusatz = '';
                    try {
                        var d = JSON.parse(roh);
                        // Die MASSNAHME zuerst: sie sagt, was zu tun ist.
                        // 'detail' nennt die Ursache, 'error' nur die Art.
                        var teile = [d.massnahme, d.detail, d.error]
                            .filter(function (x) { return !!x; });
                        if (teile.length) { zusatz = ' — ' + teile.join(' | '); }
                    } catch (e) {
                        var kurz = String(roh || '').trim().slice(0, 200);
                        if (kurz) { zusatz = ' — ' + kurz; }
                    }
                    throw new Error('HTTP ' + r.status + ' bei ' + url
                                    + zusatz);
                }, function () {
                    // Nicht einmal der Text war lesbar. Auch das wird
                    // gesagt, statt es wie 'kein Grund' aussehen zu lassen.
                    throw new Error('HTTP ' + r.status + ' bei ' + url
                                    + ' — Antwortkoerper nicht lesbar.');
                });
            });
    }

    // postJson: AUDITIERTER SCHREIBZUGRIFF (Build 372). Sendet JSON mit dem
    // Schreib-Token. Fehlerantworten werden AUSGEWERTET und als Fehler mit der
    // Server-Begruendung weitergereicht (Grundregel 1: kein stiller Fehlschlag).
    function postJson(url, body) {
        log('post', url, body);
        if (!state.writeToken) {
            return Promise.reject(new Error(
                'Kein Schreib-Token vorhanden (Server neu gestartet? '
                + 'Seite neu laden).'));
        }
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-AIW-Token': state.writeToken
            },
            body: JSON.stringify(body)
        }).then(function (r) {
            return r.json().catch(function () { return {}; })
                .then(function (data) {
                    if (!r.ok) {
                        // Build 423: Fehlerantworten koennen eine strukturierte
                        // 'errors'-Liste tragen (z.B. Query-Validierung, W2).
                        // Diese hat Vorrang, damit ALLE konkreten Gruende sichtbar
                        // werden statt nur des Fehlercodes (Grundregel 1: kein
                        // stiller/unspezifischer Fehlschlag).
                        var detail = data.detail
                            || (data.errors && data.errors.length
                                ? data.errors.join('; ') : null)
                            || data.error || ('HTTP ' + r.status);
                        var fehler = new Error(detail);
                        // Build 534: EINZELbeanstandungen mitfuehren. Die
                        // Sammelzuweisung (/api/case/assign_batch) meldet je
                        // beanstandeten Fall eine eigene Zeile; ginge sie hier
                        // verloren, saehe der Anwender nur 'N Beanstandungen'
                        // und muesste raten, welche (Grundregel 1).
                        fehler.zeilen = (data.zeilen && data.zeilen.length)
                            ? data.zeilen : [];
                        // Build 560/561: manche Antworten nennen das
                        // SCHULDIGE FELD ('feld'). Ginge es hier verloren,
                        // koennte keine Maske es markieren und der Anwender
                        // muesste bei sieben gleichartigen Eingabefeldern
                        // raten, welches gemeint ist (Grundregel 1).
                        fehler.feld = data.feld || null;
                        throw fehler;
                    }
                    return data;
                });
        });
    }

    // destroyTable: laufende Tabulator-Instanz sauber abbauen (verhindert
    // DOM-/Listener-Leaks und doppelte Tabellen beim Sichtwechsel/Reload).
    function destroyTable() {
        if (state.table && typeof state.table.destroy === 'function') {
            try { state.table.destroy(); } catch (e) { log('destroyTable', e); }
        }
        state.table = null;
    }

    // destroyChart: laufende ECharts-Instanz entsorgen (dispose) und den daran
    // gebundenen Resize-Handler abmelden. ECharts nutzt dispose(), nicht
    // destroy() -> daher getrennt von destroyTable().
    function destroyChart() {
        if (state.chartResize && typeof window !== 'undefined') {
            window.removeEventListener('resize', state.chartResize);
            state.chartResize = null;
        }
        if (state.chart && typeof state.chart.dispose === 'function') {
            try { state.chart.dispose(); } catch (e) { log('destroyChart', e); }
        }
        state.chart = null;
    }

    // cleanupView: alle sicht-spezifischen Artefakte (Tabelle UND Diagramm)
    // abbauen. Wird beim Sichtwechsel und vor jedem Neuaufbau aufgerufen.
    function cleanupView() {
        destroyTable();
        // Mehrfach-Tabellen (Policy-Sicht) abbauen.
        (state.tables || []).forEach(function (t) {
            if (t && typeof t.destroy === 'function') {
                try { t.destroy(); } catch (e) { log('destroyTables', e); }
            }
        });
        state.tables = [];
        destroyChart();
        // Mehrfach-Charts (Statistik-Sicht) entsorgen.
        (state.charts || []).forEach(function (c) {
            if (c && typeof c.dispose === 'function') {
                try { c.dispose(); } catch (e) { log('destroyCharts', e); }
            }
        });
        state.charts = [];
        // Periodischen Betreuungs-Refresh stoppen (Live-Sicht verlassen).
        if (state.mentoringTimer) {
            clearInterval(state.mentoringTimer);
            state.mentoringTimer = null;
        }
        // Drag&Drop-Handle der Betreuungs-Notizen abbauen (Build 407), damit
        // beim Sichtwechsel keine verwaisten Listener zuruueckbleiben.
        var notesMod = (typeof window !== 'undefined')
            ? window.AIWCockpitNotes : null;
        if (notesMod && typeof notesMod.cleanup === 'function') {
            notesMod.cleanup();
        }
        // Lektorat-Sicht (Build 413) abbauen (interne Referenzen loesen).
        var lectMod = (typeof window !== 'undefined')
            ? window.AIWCockpitLectorate : null;
        if (lectMod && typeof lectMod.cleanup === 'function') {
            lectMod.cleanup();
        }
        // Chef-Freigabe-Sicht (Build 416) abbauen.
        var apprMod = (typeof window !== 'undefined')
            ? window.AIWCockpitApproval : null;
        if (apprMod && typeof apprMod.cleanup === 'function') {
            apprMod.cleanup();
        }
        // Platzhalter/Query-Autorensicht (W2, Build 423) abbauen.
        var tplMod = (typeof window !== 'undefined')
            ? window.AIWCockpitTemplates : null;
        if (tplMod && typeof tplMod.cleanup === 'function') {
            tplMod.cleanup();
        }
        // Dokumentvorlagen-Autorensicht (W3, Build 425) abbauen.
        var dtplMod = (typeof window !== 'undefined')
            ? window.AIWCockpitDocTemplates : null;
        if (dtplMod && typeof dtplMod.cleanup === 'function') {
            dtplMod.cleanup();
        }
        // Baustein-Modul-Autorensicht (W1, Build 427) abbauen.
        var modMod = (typeof window !== 'undefined')
            ? window.AIWCockpitModules : null;
        if (modMod && typeof modMod.cleanup === 'function') {
            modMod.cleanup();
        }
        // Build 546 (AP-3G): das Sortable der Einstellsicht abbauen, sonst
        // bleiben beim Sichtwechsel verwaiste Listener zurueck.
        var vpMod = (typeof window !== 'undefined')
            ? window.AIWCockpitViewPrefs : null;
        if (vpMod && typeof vpMod.cleanup === 'function') {
            vpMod.cleanup();
        }
        // Build 663 (Ticket d3f933cd): Von/Bis-Kopplung der Kapazitaetspflege
        // abmelden.
        if (_capacityPflegeView
                && typeof _capacityPflegeView.datumspaarAbmelden === 'function') {
            try { _capacityPflegeView.datumspaarAbmelden(); }
            catch (e) { log('datumspaarAbmelden', e); }
        }
        _capacityPflegeView = null;
    }

    // renderError: sichtbarer Fehlerhinweis im Hauptbereich (kein stiller Fehlpfad).
    function renderError(mainEl, msg) {
        if (!mainEl) { return; }
        mainEl.textContent = '';
        var p = document.createElement('p');
        p.className = 'aiw-pagesub';
        p.textContent = msg;
        mainEl.appendChild(p);
    }

    // loadOverview: /api/overview holen und als Tabulator-Tabelle rendern
    // (cockpit_overview.js). Wird bei Sichtwahl 'dashboard' UND bei SSE-'changed'
    // auf der aktiven Overview-Sicht aufgerufen.
    // =========================================================================
    // Build 547 (AP-3G / Idee 37): DER UEBERBLICK IST EINE KACHELFLAECHE.
    //
    // Jede Kachel speist sich aus einem BESTEHENDEN lesenden Endpunkt; dieses
    // Arbeitspaket legt keinen neuen Datenweg an. Die Abrufe laufen PARALLEL
    // und jeder faengt seinen Fehler SELBST — faellt einer aus, zeigt genau
    // diese Kachel den Ausfall, und die uebrigen stehen trotzdem. Ein
    // gemeinsamer catch haette den ganzen Ueberblick leergeraeumt, und ein
    // leerer Ueberblick saehe aus wie 'es liegt nichts an'.
    //
    // 'fallampel' ist ein STECKPLATZ: die Kachel bekommt einen leeren Rumpf,
    // in den DIESE Funktion die ECHTE Tabulator-Uebersicht zeichnet
    // (cockpit_overview.renderOverview). Damit bleibt der Fall-Sprung der
    // Kommandopalette (focusCase, Build 459) unveraendert heil — er haengt an
    // genau dieser Instanz.
    // =========================================================================
    function loadOverview(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var db = (typeof window !== 'undefined')
            ? window.AIWCockpitDashboard : null;
        var ov = (typeof window !== 'undefined') ? window.AIWCockpitOverview : null;
        if (!db || !ov) {
            renderError(mainEl, 'Ueberblick-Module nicht geladen.');
            return;
        }

        var kacheln = db.aktiveKacheln(state.viewPrefsWidgets,
                                       state.viewPrefsKatalog);
        // Build 574: KEINE Kachel traegt mehr einen Steckplatz. 'fallampel'
        // bettete bis hierher die vollstaendige Falltabelle ein - gemessene
        // 1001 Pixel fuer eine Kachel, also mehr als der halbe Bildschirm fuer
        // ein Detail. Die Tabelle hat jetzt ihre eigene Sicht ('faelle'), und
        // die Kachel ist eine Kompaktuebersicht: Ampelring plus die drei
        // dringendsten Faelle (Festlegung mc 2026-07-30).
        //
        // Die Steckplatz-Mechanik BLEIBT im Renderer - sie ist getestet und
        // kostet nichts. Wer spaeter eine Kachel mit eingebettetem Bauteil
        // braucht, setzt hier wieder ein slot-Merkmal.

        // Je Kachel EIN Abruf, parallel, mit eigenem catch.
        var abrufe = kacheln.map(function (w) {
            return fetchJson(w.api_path).then(function (d) {
                return { key: w.key, daten: d };
            }).catch(function (err) {
                return { key: w.key, daten: { fehler: err.message } };
            });
        });

        Promise.all(abrufe).then(function (ergebnisse) {
            cleanupView();  // vorherige Artefakte vor Neuaufbau abbauen
            var modelle = {};
            var rohdaten = {};
            ergebnisse.forEach(function (e) {
                rohdaten[e.key] = e.daten;
                modelle[e.key] = db.reduziere(e.key, e.daten);
            });

            // Build 570: je Kachel EINE ECharts-Option — oder keine. Die
            // Entscheidung faellt in optionFuer(); Kacheln ohne Option sind
            // Absicht und in DIAGRAMMLOS begruendet (Ja/Nein-Aussagen).
            var dc = (typeof window !== 'undefined')
                ? window.AIWCockpitDashboardCharts : null;
            var diagramme = {};
            if (dc) {
                kacheln.forEach(function (w) {
                    var opt = dc.optionFuer(w.key, rohdaten[w.key]);
                    if (opt) { diagramme[w.key] = opt; }
                });
            }

            db.renderDashboard(mainEl, {
                kacheln: kacheln, modelle: modelle, diagramme: diagramme,
                katalog: state.viewPrefsKatalog, prefs: state.viewPrefsWidgets
            }, {
                // Diagramme in die Steckplaetze haengen. JEDE Instanz wird in
                // state.charts vermerkt, weil cleanupView() sie beim
                // Sichtwechsel entsorgt - sonst bleiben Leinwaende und
                // Resize-Horcher zurueck, und das Dashboard wird bei jedem
                // Besuch etwas langsamer.
                onDiagramm: function (key, hostEl, option) {
                    if (!dc) { return; }
                    var inst = dc.zeichne(hostEl, option);
                    if (inst) {
                        state.charts = state.charts || [];
                        state.charts.push(inst);
                    }
                },
                // Build 574: der Steckplatz-Rueckruf ist entfallen - keine
                // Kachel traegt mehr ein eingebettetes Bauteil. Die
                // vollstaendige Falltabelle steht in der Sicht 'faelle'.
                // KEIN OPTIMISTISCHES UI: schreiben, dann den ECHTEN Stand neu
                // holen und daraus zeichnen.
                onSpeichern: function (nutzlast) {
                    postJson('/api/viewprefs', { widgets: nutzlast })
                        .then(function () {
                            return fetchJson('/api/viewprefs');
                        }).then(function (vp) {
                            uebernimmViewPrefs(vp);
                            loadOverview(mainEl);
                        }).catch(function (err) {
                            renderError(mainEl,
                                'Speichern fehlgeschlagen: ' + err.message);
                        });
                }
            });
            log('Ueberblick gerendert:', kacheln.length, 'Kacheln');
        }).catch(function (err) {
            // Hierher kommt nur, was NICHT aus einem Einzelabruf stammt (die
            // fangen selbst) — also ein Fehler im Aufbau der Flaeche.
            cleanupView();
            renderError(mainEl,
                'Ueberblick konnte nicht aufgebaut werden: ' + err.message);
        });
    }

    // =========================================================================
    // Build 546 (AP-3G / Idee 37): die Sicht "Ansicht anpassen".
    //
    // Die Zeilen, die die Sicht bearbeitet, entstehen HIER — nicht im Modul.
    // Grund: nur die Shell kennt beides, den Katalog und die Rechte. Sie
    // reicht die BEREITS RECHTE-GEFILTERTE, nach der Vorliebe geordnete Liste
    // hinein; das Modul kann deshalb konstruktiv nichts einblenden, was nicht
    // erlaubt ist.
    //
    // 'viewprefs' selbst wird herausgenommen: die Sicht, mit der man einstellt,
    // darf sich nicht selbst wegstellen (Server-Gegenstueck: NICHT_STEUERBAR
    // in viewpref_katalog.py).
    // =========================================================================
    function viewPrefRows() {
        return visibleViews(state.capabilities,
                            applyViewPrefs(VIEW_CATALOG, state.viewPrefs))
            .filter(function (v) { return v.id !== 'viewprefs'; })
            .map(function (v) {
                return { id: v.id, label: v.label, group: v.group,
                         versteckt: v.versteckt === true };
            });
    }

    function loadViewPrefs(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitViewPrefs : null;
        if (!mod) {
            renderError(mainEl, 'Modul "Ansicht anpassen" nicht geladen.');
            return;
        }
        cleanupView();
        mod.renderViewPrefs(mainEl, {
            rows: viewPrefRows(),
            gespeichert: state.viewPrefs || [],
            unbekannt: state.viewPrefsUnbekannt || [],
            fehler: state.viewPrefsFehler
        }, {
            // KEIN OPTIMISTISCHES UI: erst schreiben, dann den ECHTEN Stand
            // neu holen und die Navigation daraus aufbauen. Ein abgewiesener
            // Speichervorgang darf sich nicht als Erfolg anfuehlen.
            onSave: function (nutzlast) {
                postJson('/api/viewprefs', { sichten: nutzlast })
                    .then(function () {
                        // ERST nach der Bestaetigung des Servers ist der
                        // Entwurf ueberholt — nicht schon beim Klick.
                        mod.nachErfolg();
                        return neuLadenUndZeichnen(mainEl);
                    })
                    .catch(function (err) {
                        renderError(mainEl,
                            'Speichern fehlgeschlagen: ' + err.message);
                    });
            },
            onReset: function () {
                postJson('/api/viewprefs/reset', { art: 'sicht' })
                    .then(function () {
                        mod.nachErfolg();
                        return neuLadenUndZeichnen(mainEl);
                    })
                    .catch(function (err) {
                        renderError(mainEl,
                            'Zuruecksetzen fehlgeschlagen: ' + err.message);
                    });
            }
        });
    }

    // uebernimmViewPrefs: die Antwort von /api/viewprefs in den Zustand.
    //
    // AN GENAU EINER STELLE, weil sie an drei Orten gebraucht wird (boot,
    // Speichern der Sichten, Speichern der Kacheln). Drei Kopien liefen
    // irgendwann auseinander.
    //
    // 'widgets' bleibt null, wenn der Server nichts Gespeichertes meldet —
    // null heisst WERKSEINSTELLUNG, [] heisst 'alle Kacheln abgewaehlt'. Wer
    // beides gleich behandelt, gibt jemandem die Werkseinstellung zurueck, der
    // sie ausdruecklich abgewaehlt hat.
    function uebernimmViewPrefs(vp) {
        state.viewPrefs = (vp && vp.sichten) || [];
        state.viewPrefsKatalog = (vp && vp.katalog) || null;
        state.viewPrefsUnbekannt = (vp && vp.unbekannt) || [];
        state.viewPrefsWidgets = (vp && vp.widgets && vp.widgets.length)
            ? vp.widgets : null;
        state.viewPrefsFehler = null;
    }

    // neuLadenUndZeichnen: den gespeicherten Stand frisch holen, die Navigation
    // neu bauen und die Einstellsicht neu zeichnen. Eine Stelle, damit
    // Speichern und Zuruecksetzen nicht auseinanderlaufen koennen.
    function neuLadenUndZeichnen(mainEl) {
        return fetchJson('/api/viewprefs').then(function (vp) {
            uebernimmViewPrefs(vp);
            selectView('viewprefs');   // baut Nav + Sicht neu auf
        });
    }

    // loadWorkload: /api/workload holen und als ECharts-Diagramm rendern
    // (cockpit_workload.js). Bindet einen Resize-Handler an die Instanz, damit
    // das Diagramm bei Fensteraenderung mitwaechst (in cleanupView abgemeldet).
    function loadWorkload(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined') ? window.AIWCockpitWorkload : null;
        if (!mod) {
            renderError(mainEl, 'Workload-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/workload').then(function (data) {
            cleanupView();  // Tabelle/altes Diagramm vor Neuaufbau abbauen
            state.chart = mod.renderWorkload(mainEl, data, {});
            if (state.chart && typeof state.chart.resize === 'function') {
                state.chartResize = function () {
                    try { state.chart.resize(); } catch (e) { log('resize', e); }
                };
                window.addEventListener('resize', state.chartResize);
            }
            log('Workload gerendert:', data.count, 'Zeilen, scope', data.scope);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Lastverteilung konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadEscalation: /api/escalations holen und ueber cockpit_escalation.js
    // rendern (Build 516 / AP-2G, Idee 23).
    //
    // FEHLER WERDEN DURCHGEREICHT, NICHT VERSCHLUCKT: ein Fehlschlag landet als
    // {error: <text>} im Modul, das daraus einen AUSDRUECKLICHEN Fehlerzustand
    // macht. Wuerden wir hier nur renderError aufrufen und die Sicht leeren,
    // saehe der Ausfall der Erhebung genauso aus wie ein Leerbefund — und ein
    // Leerbefund waere die Behauptung "es liegt nichts an" (Grundregel 1).
    //
    // BUILD 518: zusaetzlich die auditierte QUITTIERUNG (POST). KEIN
    // optimistisches UI — nach jedem Schreibvorgang wird die Sicht NEU
    // GELADEN, damit auch eine ABGELEHNTE Aenderung den echten Stand zeigt
    // (dieselbe Linie wie beim Querfund-Rueckkanal, Build 508). Ob die
    // Bedienelemente ueberhaupt erscheinen, entscheidet AUSSCHLIESSLICH der
    // Server ueber 'acknowledgeable' — das Frontend leitet kein Recht selbst
    // ab; der Server prueft ohnehin ein zweites Mal.
    function loadEscalation(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitEscalation : null;
        if (!mod) {
            renderError(mainEl, 'Eskalations-Modul nicht geladen.');
            return;
        }

        function after(text, isError) {
            loadEscalation(mainEl, { text: text, error: isError });
        }

        var opts = {
            message: pendingMsg,
            onAck: function (body) {
                postJson('/api/escalations/ack', body)
                    .then(function (r) {
                        after('Quittiert (Vermerk #' + r.ack_id
                            + ', Beleg #' + r.audit_seq + '). Die Meldung '
                            + 'bleibt stehen, bis die Ursache behoben ist.',
                            false);
                    })
                    .catch(function (err) {
                        after('Fehler: ' + err.message + ' (es wurde nichts '
                            + 'geschrieben — die Liste zeigt den '
                            + 'unveraenderten Stand).', true);
                    });
            },
            onRevoke: function (body) {
                postJson('/api/escalations/ack/revoke', body)
                    .then(function (r) {
                        after('Vermerk #' + r.ack_id + ' widerrufen '
                            + '(Beleg #' + r.audit_seq + '). Der urspruengliche '
                            + 'Vermerk bleibt als Beleg erhalten.', false);
                    })
                    .catch(function (err) {
                        after('Fehler: ' + err.message + ' (es wurde nichts '
                            + 'geschrieben — die Liste zeigt den '
                            + 'unveraenderten Stand).', true);
                    });
            }
        };

        fetchJson('/api/escalations').then(function (data) {
            cleanupView();
            mod.renderEscalation(mainEl, data, opts);
            log('Eskalationen gerendert:', (data.items || []).length,
                'quittierbar:', data.acknowledgeable);
        }).catch(function (err) {
            cleanupView();
            mod.renderEscalation(mainEl, { error: err.message }, opts);
        });
    }

    // loadNextActions: /api/next_actions holen und ueber
    // cockpit_nextactions.js rendern (Build 519 / AP-2F, Idee 22).
    //
    // Wie bei den Eskalationen wird ein Fehlschlag als {error: ...} an das
    // Modul DURCHGEREICHT statt die Sicht zu leeren: eine leere Schlange im
    // Fehlerfall haette 'nichts zu tun' behauptet (Grundregel 1).
    function loadNextActions(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitNextActions : null;
        if (!mod) {
            renderError(mainEl, 'Modul "Naechstbeste Aktion" nicht geladen.');
            return;
        }
        fetchJson('/api/next_actions').then(function (data) {
            cleanupView();
            mod.renderNextActions(mainEl, data, {});
            log('Naechstbeste Aktion gerendert:', (data.items || []).length,
                'scope', data.scope);
        }).catch(function (err) {
            cleanupView();
            mod.renderNextActions(mainEl, { error: err.message }, {});
        });
    }

    // loadHandover: /api/handover holen und ueber cockpit_handover.js rendern
    // (Build 520 / AP-2G, Idee 30). 'subject' schraenkt auf EINEN Fall ein und
    // wird in state.hvSubject gehalten, damit ein Sichtwechsel und der
    // SSE-Reload den Ausschnitt beibehalten — und damit der Akten-Export
    // denselben Ausschnitt abbildet wie die Sicht.
    function loadHandover(mainEl, subject) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitHandover : null;
        if (!mod) {
            renderError(mainEl, 'Uebergabe-Modul nicht geladen.');
            return;
        }
        if (subject !== undefined) { state.hvSubject = subject || null; }
        var url = '/api/handover';
        if (state.hvSubject) {
            url += '?subject_id=' + encodeURIComponent(state.hvSubject);
        }
        var opts = {
            onFilter: function (next) {
                state.hvSubject = next || null;
                refreshExportButton();   // der Export folgt dem Ausschnitt
                loadHandover(mainEl);
            }
        };
        fetchJson(url).then(function (data) {
            cleanupView();
            mod.renderHandover(mainEl, data, opts);
            log('Uebergaben gerendert:', (data.entries || []).length,
                'Filter', data.filter_subject_id);
        }).catch(function (err) {
            cleanupView();
            mod.renderHandover(mainEl, { error: err.message }, opts);
        });
    }

    // loadRetention: /api/retention holen und ueber cockpit_retention.js
    // rendern (Build 521 / AP-2G, Idee 29).
    //
    // BEWUSST OHNE Schreibpfad-Verdrahtung: diese Sicht kann nichts loeschen,
    // und es soll auch nichts danach aussehen. Ein Fehlschlag wird als
    // {error: ...} durchgereicht — eine leere Kandidatenliste im Fehlerfall
    // haette 'keine Frist ueberschritten' behauptet (Grundregel 1).
    function loadRetention(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitRetention : null;
        if (!mod) {
            renderError(mainEl, 'Aufbewahrungs-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/retention').then(function (data) {
            cleanupView();
            mod.renderRetention(mainEl, data, {});
            log('Aufbewahrung gerendert:', (data.candidates || []).length,
                'Kandidaten,', data.without_reference, 'ungeprueft');
        }).catch(function (err) {
            cleanupView();
            mod.renderRetention(mainEl, { error: err.message }, {});
        });
    }

    // loadLimitation: /api/limitation holen und die Fristensicht rendern
    // (cockpit_limitation.js, Build 525).
    //
    // DIE VORWARNSCHWELLE LEBT IM STATE, nicht in der Sicht: der SSE-Reload
    // muss DIESELBE Schwelle verwenden, sonst springt die Ampelfarbe bei einem
    // fremden Fall-Abschluss unvermittelt um, und niemand koennte sich das
    // erklaeren. Muster: state.capacityPeriod (Build 360).
    //
    // KEIN SCHREIBPFAD: der einzige Rueckruf (onVorwarn) ruft diese Funktion
    // erneut auf — er aendert die ANSICHT, nie einen Beleg.
    function loadLimitation(mainEl, vorwarnTage) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitLimitation : null;
        if (!mod) {
            renderError(mainEl, 'Fristen-Modul nicht geladen.');
            return;
        }
        if (vorwarnTage !== undefined && vorwarnTage !== null) {
            state.limitationVorwarn = Number(vorwarnTage);
        }
        var url = '/api/limitation';
        if (state.limitationVorwarn) {
            url += '?vorwarn_tage='
                + encodeURIComponent(String(state.limitationVorwarn));
        }
        fetchJson(url).then(function (data) {
            cleanupView();
            mod.renderLimitation(mainEl, data, {
                onVorwarn: function (tage) { loadLimitation(mainEl, tage); }
            });
            log('Fristen gerendert:', (data.rows || []).length, 'Zeilen;',
                'Aussage moeglich:', data.aussage_moeglich);
        }).catch(function (err) {
            cleanupView();
            mod.renderLimitation(mainEl, { error: err.message }, {});
        });
    }

    // loadMatrix: /api/matrix holen und die Matrix rendern (cockpit_matrix.js,
    // Build 539).
    //
    // DAS NACHLADEN DER FRISTEN LEBT IM STATE, nicht in der Sicht — dieselbe
    // Ueberlegung wie bei state.limitationVorwarn (Build 525): der SSE-Reload
    // muss DENSELBEN Umfang laden, sonst verschwaende oder erschiene der
    // Fristanteil bei einem fremden Fall-Ereignis von selbst, und niemand
    // koennte sich das erklaeren.
    //
    // DIE VORGABE IST 'OHNE FRISTEN', und das ist eine Messentscheidung und
    // keine Geschmacksfrage: die Fristkomponente oeffnet je Fall bis zu zwei
    // Dateien. Container-Messung (Build 538): Faktor 13-14 gegenueber den
    // uebrigen fuenf Beitraegen, rund 0,7 ms je Fall. Fuer PROD (Netzlaufwerk)
    // steht die Messung aus; der Fristenmonitor lag dort um den Faktor 24
    // ueber DEV. Bis diese Zahl vorliegt, waere ein sofortiges Mitladen eine
    // Wette. Die Sicht SAGT in jedem Zustand, was fehlt — sie luegt nicht, sie
    // sagt weniger. Sobald die PROD-Zahl da ist, ist die Umstellung EINE
    // Zeile (state.matrixFristen = true).
    //
    // KEIN SCHREIBPFAD: der einzige Rueckruf (onFristen) ruft diese Funktion
    // erneut auf — er aendert die ANSICHT, nie einen Beleg.
    function loadMatrix(mainEl, mitFristen) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMatrix : null;
        if (!mod) {
            renderError(mainEl, 'Matrix-Modul nicht geladen.');
            return;
        }
        if (mitFristen !== undefined && mitFristen !== null) {
            state.matrixFristen = !!mitFristen;
        }
        var url = '/api/matrix?fristen='
            + (state.matrixFristen ? '1' : '0');
        fetchJson(url).then(function (data) {
            cleanupView();
            mod.renderMatrix(mainEl, data, {
                onFristen: function (mit) { loadMatrix(mainEl, mit); }
            });
            log('Matrix gerendert:', (data.zellen || []).length, 'Zellen;',
                'Fristen geladen:', data.fristen_geladen,
                '; Dauer', data.dauer_gesamt_ms, 'ms');
        }).catch(function (err) {
            cleanupView();
            mod.renderMatrix(mainEl, { error: err.message }, {});
        });
    }

    // loadSearch / loadSearchInhalt: die falluebergreifende Volltextsuche
    // (cockpit_search.js, Builds 560-563).
    //
    // DIE SUCHE IST EIN POST UND KEIN GET, obwohl sie fachlich nichts
    // schreibt: jede Abfrage IST ein Beleg (FULLTEXT_SEARCHED), auch der
    // Leerbefund. Deshalb laeuft sie ueber postJson (X-AIW-Token) und wird
    // NIE automatisch ausgeloest — weder beim Oeffnen der Sicht noch beim
    // SSE-Reload. Eine Sicht, die sich selbst neu sucht, erzeugte Belege
    // ohne menschliche Handlung, und genau die waeren wertlos.
    //
    // Der Zweckkatalog kommt aus der DATENBANK (GET /api/fulltext/zwecke),
    // damit die Maske genau das anbietet, was der Fremdschluessel annimmt.
    function loadSearch(mainEl, zustand) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitSearch : null;
        if (!mod) {
            renderError(mainEl, 'Volltextsuche-Modul nicht geladen.');
            return;
        }
        if (zustand) { state.searchZustand = zustand; }
        var hooks = {
            zwecke: state.searchZwecke || [],
            zustand: state.searchZustand || {},
            onSuche: function (z) { sucheAusfuehren(mainEl, z); },
            onInhalt: function (uid) { loadSearchInhalt(mainEl, uid); },
            onAnfrage: function (uid) {
                window.alert(
                    'Der Inhalt von Fall ' + uid + ' ist gesperrt.\n\n'
                    + 'Bitte die Chef-Ermittlerin um eine Inhaltsfreigabe '
                    + 'bitten; sie erteilt sie unter Angabe von Zweck und '
                    + 'Begruendung. Eine Freigabe gilt je Fall und Person, '
                    + 'nicht je Abfrage.');
            }
        };
        // Der Katalog wird EINMAL je Sitzung geholt; danach steht er im
        // State. Ohne ihn wird die Maske trotzdem gezeichnet — nur ohne
        // Auswahl, und der Server weist die Abfrage dann mit Klartext ab.
        if (state.searchZwecke) {
            cleanupView();
            mod.renderSearch(mainEl, state.searchDaten || {}, hooks);
            return;
        }
        fetchJson('/api/fulltext/zwecke').then(function (k) {
            state.searchZwecke = k.zwecke || [];
            hooks.zwecke = state.searchZwecke;
            cleanupView();
            mod.renderSearch(mainEl, state.searchDaten || {}, hooks);
            log('Zweckkatalog geladen:', state.searchZwecke.length, 'Codes');
        }).catch(function (err) {
            cleanupView();
            mod.renderSearch(mainEl, { error: err.message }, hooks);
        });
    }

    function sucheAusfuehren(mainEl, z) {
        state.searchZustand = z;
        postJson('/api/fulltext/lage', {
            begriff: z.begriff, modus: z.modus,
            zweck_code: z.zweck_code, zweck_freitext: z.zweck_freitext
        }).then(function (data) {
            state.searchDaten = data;
            loadSearch(mainEl);
            log('Trefferlage:', (data.faelle || []).length, 'Faelle');
        }).catch(function (err) {
            state.searchDaten = { error: err.message };
            loadSearch(mainEl);
        });
    }

    function loadSearchInhalt(mainEl, subjectId) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitSearch : null;
        if (!mod) {
            renderError(mainEl, 'Volltextsuche-Modul nicht geladen.');
            return;
        }
        var z = state.searchZustand || {};
        var hooks = {
            onZurueck: function () { loadSearch(mainEl); },
            onAnfrage: function () {
                window.alert('Bitte die Chef-Ermittlerin um eine '
                    + 'Inhaltsfreigabe bitten.');
            }
        };
        postJson('/api/fulltext/inhalt', {
            begriff: z.begriff, modus: z.modus, subject_id: subjectId,
            zweck_code: z.zweck_code, zweck_freitext: z.zweck_freitext
        }).then(function (data) {
            cleanupView();
            mod.renderInhalt(mainEl, data, hooks);
        }).catch(function (err) {
            cleanupView();
            mod.renderInhalt(mainEl, { error: err.message,
                                       subject_id: subjectId }, hooks);
        });
    }

    // loadQs: /api/qs UND /api/metrics holen und die Sicht rendern
    // (cockpit_qs.js, Build 543).
    //
    // ZWEI ENDPUNKTE, EINE SICHT — und zwei getrennte Rechte. Fehlt
    // 'metrics.view', antwortet /api/metrics mit 403; die Sicht zeigt dann den
    // Kennzahlenteil als AUSGEFALLEN und nicht als leer. Ein 403 auf dem einen
    // Endpunkt darf die Sicht nicht als Ganzes unbrauchbar machen — und ein
    // leerer Kennzahlenblock saehe aus wie 'nichts auffaellig'.
    //
    // DER SUBSTANZ-UMFANG LEBT IM STATE (state.qsSubstanz), damit der
    // SSE-Reload denselben Umfang laedt — Muster state.limitationVorwarn
    // (Build 525) und state.matrixFristen (Build 539). Der teure Block ist
    // ausgeschaltet, solange ihn niemand anfordert: er oeffnet EINE Datei je
    // zugewiesenem Fall.
    //
    // KEIN OPTIMISTISCHES UI: nach jedem Schreibvorgang wird NEU GELADEN. Ein
    // Pruefergebnis, das in der Oberflaeche steht, aber nicht in der Datenbank,
    // waere in einem forensischen Werkzeug die schlimmste Art von Anzeige.
    // Schlaegt ein Schreibversuch fehl, wird die Sicht MIT der Fehlermeldung
    // neu aufgebaut — insbesondere der 403 aus der Selbstpruefungssperre ist
    // genau die Meldung, die jemand lesen soll.
    function loadQs(mainEl, substanz, fehler) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitQs : null;
        if (!mod) {
            renderError(mainEl, 'QS-Modul nicht geladen.');
            return;
        }
        if (substanz !== undefined && substanz !== null) {
            state.qsSubstanz = !!substanz;
        }
        var metrikUrl = '/api/metrics?substanz='
            + (state.qsSubstanz ? '1' : '0');

        Promise.all([
            fetchJson('/api/qs'),
            fetchJson(metrikUrl).catch(function (err) {
                return { error: err.message };
            })
        ]).then(function (beides) {
            cleanupView();
            mod.renderQs(mainEl, beides[0], {
                metrik: beides[1],
                fehler: fehler || null,
                onDraw: function () {
                    postJson('/api/qs/draw', {}).then(function () {
                        loadQs(mainEl);
                    }).catch(function (err) {
                        loadQs(mainEl, undefined, err.message);
                    });
                },
                onReview: function (nutzlast) {
                    postJson('/api/qs/review', nutzlast).then(function () {
                        loadQs(mainEl);
                    }).catch(function (err) {
                        loadQs(mainEl, undefined, err.message);
                    });
                },
                onSubstanz: function (mit) { loadQs(mainEl, mit); }
            });
            log('QS gerendert:', (beides[0].ziehungen || []).length,
                'Ziehungen; Substanz:', state.qsSubstanz);
        }).catch(function (err) {
            cleanupView();
            mod.renderQs(mainEl, { error: err.message }, {});
        });
    }

    // loadCapacity: /api/capacity (Aggregat, ohne person_id) fuer einen Zeitraum
    // holen und als ECharts-Diagramm rendern (cockpit_capacity.js). Der Zeitraum
    // wird in state.capacityPeriod gehalten (Default: laufender Monat), damit der
    // SSE-Reload denselben Zeitraum verwendet. Die Zeitraum-Wahl im View ruft
    // loadCapacity mit neuem Zeitraum erneut auf.
    function loadCapacity(mainEl, period) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCapacity : null;
        if (!mod) {
            renderError(mainEl, 'Kapazitaets-Modul nicht geladen.');
            return;
        }
        if (!period) {
            period = state.capacityPeriod || mod.defaultPeriod();
        }
        state.capacityPeriod = period;
        var url = '/api/capacity?start=' + encodeURIComponent(period.start)
            + '&end=' + encodeURIComponent(period.end);
        fetchJson(url).then(function (data) {
            cleanupView();
            state.chart = mod.renderCapacity(mainEl, data, {
                onPeriodChange: function (start, end) {
                    if (start && end) {
                        loadCapacity(mainEl, { start: start, end: end });
                    }
                }
            });
            if (state.chart && typeof state.chart.resize === 'function') {
                state.chartResize = function () {
                    try { state.chart.resize(); } catch (e) { log('resize', e); }
                };
                window.addEventListener('resize', state.chartResize);
            }
            log('Kapazitaet gerendert:', data.count, 'Ermittler,',
                period.start, 'bis', period.end);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Kapazitaet konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadPolicy: /api/policy holen und als RBAC-Policy-Sicht rendern
    // (cockpit_policy.js). Liefert mehrere Tabulator-Instanzen -> state.tables
    // (in cleanupView abgebaut).
    function loadPolicy(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined') ? window.AIWCockpitPolicy : null;
        if (!mod) {
            renderError(mainEl, 'Policy-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/policy').then(function (data) {
            cleanupView();
            state.tables = mod.renderPolicy(mainEl, data, {}) || [];
            log('Policy gerendert:', (data.counts && data.counts.grants),
                'Grants, scope', data.scope);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Policy konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadMyCases: /api/mycases holen und als persoenliche Fall-Liste rendern
    // (cockpit_mycases.js). Einzelne Tabulator-Instanz -> state.table.
    //
    // Build 500 (Fallstart aus dem Portal): reicht ein onLaunch-Callback durch.
    // Ein Klick auf "Fall starten" sendet POST /api/case/launch (auditfrei, kein
    // DB-Schreibzugriff — der Server prueft nur die Eigentuemerschaft und startet
    // den Forensik-Server main.py fuer den Fall). Erfolg/Fehler werden als Banner
    // ueber der Tabelle gezeigt; dazu wird die Sicht mit pendingMsg neu geladen.
    // opts.pendingMsg wird beim Reload EINMALIG angezeigt.
    function loadMyCases(mainEl, opts) {
        opts = opts || {};
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMyCases : null;
        if (!mod) {
            renderError(mainEl, 'Modul "Meine Auftraege" nicht geladen.');
            return;
        }
        fetchJson('/api/mycases').then(function (data) {
            cleanupView();
            // Rueckmeldung eines Startversuchs in DERSELBEN Sicht neu laden.
            var reload = function (msg) {
                loadMyCases(mainEl, { pendingMsg: msg });
            };
            state.table = mod.renderMyCases(mainEl, data, {
                pendingMsg: opts.pendingMsg || null,
                onLaunch: function (subjectId) {
                    log('Fallstart angefordert fuer subject_id=', subjectId);
                    postJson('/api/case/launch', { subject_id: subjectId })
                        .then(function (r) {
                            reload({
                                text: 'Fall ' + subjectId + ' gestartet '
                                    + '(PID ' + (r && r.pid) + '). Der '
                                    + 'Forensik-Browser oeffnet sich in Kuerze.',
                                error: false
                            });
                        })
                        .catch(function (e) {
                            reload({
                                text: 'Fall ' + subjectId + ' konnte nicht '
                                    + 'gestartet werden: '
                                    + (e && e.message || e),
                                error: true
                            });
                        });
                }
            });
            log('Meine Auftraege gerendert:', data.count);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Meine Auftraege konnten nicht geladen werden: ' + err.message);
        });
    }

    // loadMyHistory: /api/myhistory holen und als kombinierte Zeitleiste
    // rendern (cockpit_myhistory.js). Einzelne Tabulator-Instanz -> state.table.
    function loadMyHistory(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMyHistory : null;
        if (!mod) {
            renderError(mainEl, 'Modul "Meine Historie" nicht geladen.');
            return;
        }
        fetchJson('/api/myhistory').then(function (data) {
            cleanupView();
            state.table = mod.renderMyHistory(mainEl, data, {});
            log('Meine Historie gerendert:', data.count, 'Eintraege');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Meine Historie konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadSupport: /api/support holen und als Support-Historie rendern
    // (cockpit_support.js). Liefert mehrere Tabulator-Instanzen -> state.tables
    // (in cleanupView abgebaut).
    function loadSupport(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitSupport : null;
        if (!mod) {
            renderError(mainEl, 'Support-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/support').then(function (data) {
            cleanupView();
            state.tables = mod.renderSupport(mainEl, data, {}) || [];
            log('Support-Historie gerendert:', data.count, 'Sitzungen');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Support-Historie konnte nicht geladen werden: ' + err.message);
        });
    }

    // Betreuung: LIVE-Sicht. Heartbeats sind nicht auditiert -> SSE genuegt
    // nicht; wir laden periodisch nach (Intervall). MENTORING_REFRESH_MS unter
    // der Stale-Schwelle (30 s), damit der Uebergang live->stale zeitnah
    // sichtbar wird.
    var MENTORING_REFRESH_MS = 15000;

    // refreshMentoring: ein Refresh-Tick — Daten neu holen und die Tabelle neu
    // aufbauen, OHNE den Timer anzufassen (sonst Timer-Churn). Nur wirksam,
    // solange die Betreuungs-Sicht aktiv ist.
    function refreshMentoring(mainEl) {
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMentoring : null;
        if (!mod) { return; }
        fetchJson('/api/mentoring').then(function (data) {
            if (state.activeId !== 'mentoring') { return; }
            if (state.table && typeof state.table.destroy === 'function') {
                try { state.table.destroy(); } catch (e) { log('refresh', e); }
            }
            state.table = mod.renderMentoring(mainEl, data, {});
            log('Betreuung aktualisiert:', data.count, 'laufend');
        }).catch(function (err) { log('Betreuung-Refresh-Fehler', err); });
    }

    // loadMentoring: Erst-Laden + periodischen Refresh scharf schalten.
    function loadMentoring(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMentoring : null;
        if (!mod) {
            renderError(mainEl, 'Betreuungs-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/mentoring').then(function (data) {
            cleanupView();  // baut alte Tabelle ab UND stoppt alten Timer
            state.table = mod.renderMentoring(mainEl, data, {});
            state.mentoringTimer = setInterval(function () {
                refreshMentoring(mainEl);
            }, MENTORING_REFRESH_MS);
            log('Betreuung gerendert:', data.count, 'laufend');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Ermittler-Betreuung konnte nicht geladen werden: '
                + err.message);
        });
    }

    // downloadBlob: erzeugt aus Text einen Download (Blob + <a download>).
    // Fehler werden geloggt, nicht verschluckt.
    function downloadBlob(filename, text, mime) {
        try {
            var blob = new Blob([text], { type: mime });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            log('downloadBlob-Fehler', e);
        }
    }

    // loadStats: /api/stats holen und als Statistik-Sicht rendern
    // (cockpit_stats.js). Mehrere ECharts -> state.charts; eine Tabelle ->
    // state.tables. Downloads: CSV via Endpunkt (?format=csv), JSON aus den
    // bereits geladenen Daten.
    function loadStats(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitStats : null;
        if (!mod) {
            renderError(mainEl, 'Statistik-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/stats').then(function (data) {
            cleanupView();
            var day = mod.isoDate();
            var res = mod.renderStats(mainEl, data, {
                onDownloadCsv: function () {
                    // CSV kommt aus dem Endpunkt (scope-korrekt serverseitig).
                    fetch('/api/stats?format=csv').then(function (r) {
                        return r.text();
                    }).then(function (text) {
                        downloadBlob('aiw_statistik_' + day + '.csv', text,
                            'text/csv;charset=utf-8');
                    }).catch(function (e) { log('CSV-Download', e); });
                },
                onDownloadJson: function (d) {
                    downloadBlob('aiw_statistik_' + day + '.json',
                        JSON.stringify(d, null, 2),
                        'application/json;charset=utf-8');
                }
            }) || { charts: [], tables: [] };
            state.charts = res.charts || [];
            state.tables = res.tables || [];
            log('Statistik gerendert:', data.totals && data.totals.cases,
                'Faelle');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Statistiken konnten nicht geladen werden: ' + err.message);
        });
    }

    // loadPlanung: Prognose & Gantt (cockpit_planung.js, Build 448). Holt BEIDE
    // read-only-Endpunkte (/api/forecast + /api/gantt) und rendert Szenario-
    // Tabelle + zwei ECharts. Die Charts wandern nach state.charts, damit
    // cleanupView sie beim Sichtwechsel entsorgt; je Chart ein Resize-Handler.
    function loadPlanung(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitPlanung : null;
        if (!mod) {
            renderError(mainEl, 'Planungs-Modul nicht geladen.');
            return;
        }
        Promise.all([fetchJson('/api/forecast'), fetchJson('/api/gantt')])
            .then(function (res) {
                cleanupView();
                var charts = mod.renderPlanung(
                    mainEl, { forecast: res[0], gantt: res[1] }, {}) || [];
                state.charts = charts;
                // Resize-Handler je Chart (in cleanupView via dispose entsorgt;
                // der Listener selbst wird ueber state.chartResize abgemeldet).
                state.chartResize = function () {
                    charts.forEach(function (c) {
                        try { c.resize(); } catch (e) { log('resize', e); }
                    });
                };
                window.addEventListener('resize', state.chartResize);
                log('Planung gerendert:', charts.length, 'Diagramm(e)');
            }).catch(function (err) {
                cleanupView();
                renderError(mainEl,
                    'Prognose/Gantt konnten nicht geladen werden: ' + err.message);
            });
    }

    // loadAnnostats: Annotations-Tortenstatistik (cockpit_annostats.js, Build
    // 450). Holt /api/annotation-stats und rendert zwei ECharts-Kreise
    // (Kategorie/Tag). Charts -> state.charts (cleanupView entsorgt); ein
    // Resize-Handler fuer beide.
    function loadAnnostats(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAnnostats : null;
        if (!mod) {
            renderError(mainEl, 'Annotations-Statistik-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/annotation-stats').then(function (data) {
            cleanupView();
            var charts = mod.renderAnnostats(mainEl, data, {}) || [];
            state.charts = charts;
            state.chartResize = function () {
                charts.forEach(function (c) {
                    try { c.resize(); } catch (e) { log('resize', e); }
                });
            };
            window.addEventListener('resize', state.chartResize);
            log('Annostats gerendert:', data.annotations_total, 'Annotationen');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Annotations-Statistik konnte nicht geladen werden: '
                + err.message);
        });
    }

    // loadNotes: Betreuungs-Notizen ("Post-its", Build 406). Laedt das Board
    // (/api/mentoring/notes, optional ?archived=1) und rendert das Pinboard
    // ueber das cockpit_notes-Modul. JEDE Schreibaktion (Anlegen/AEndern/
    // Archivieren/Wiederherstellen/Duplizieren) geht per POST an den
    // auditierten Schreibpfad; danach wird NEU GELADEN (kein optimistisches UI:
    // die Oberflaeche zeigt nur bestaetigt geschriebene Zustaende, Grundregel 1).
    // 'opts' traegt {archived, pendingMsg} durch den Reload hindurch, damit die
    // Archiv-Ansicht UND die Rueckmeldung nicht still verlorengehen.
    function loadNotes(mainEl, opts) {
        mainEl = mainEl || document.getElementById('aiw-main');
        opts = opts || {};
        var archived = opts.archived === true;
        // Aktuelle Ansicht (aktiv/Archiv) merken, damit der SSE-Reload sie
        // beibehaelt und nicht still ins aktive Board zurueckspringt.
        state.notesArchived = archived;
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitNotes : null;
        if (!mod) {
            renderError(mainEl, 'Betreuungs-Notizen-Modul nicht geladen.');
            return;
        }
        var url = '/api/mentoring/notes' + (archived ? '?archived=1' : '');
        fetchJson(url).then(function (data) {
            cleanupView();
            // Der Reload nach einem Schreibvorgang bleibt in derselben
            // Ansicht (aktiv/Archiv). Alle Callbacks fuehren ueber postJson und
            // laden dieselbe Ansicht neu; die Rueckmeldung wird mitgetragen.
            var reload = function (msg) {
                loadNotes(mainEl, { archived: archived, pendingMsg: msg });
            };
            var fail = function (err) {
                return function (e) {
                    log('Notiz-Schreibfehler', e);
                    reload({ text: 'Fehler: ' + (e && e.message || e),
                             error: true });
                };
            };
            mod.renderNotes(mainEl, data, {
                archived: archived,
                pendingMsg: opts.pendingMsg || null,
                // Ansicht wechseln (aktiv <-> Archiv) — reiner Lesewechsel.
                onToggleArchived: function (toArchived) {
                    loadNotes(mainEl, { archived: toArchived });
                },
                onCreate: function (body) {
                    postJson('/api/mentoring/note/create', body)
                        .then(function (r) {
                            reload({ text: 'Angelegt (Beleg #' + r.audit_seq
                                     + ').', error: false });
                        }).catch(fail());
                },
                onUpdate: function (body) {
                    postJson('/api/mentoring/note/update', body)
                        .then(function (r) {
                            reload({ text: 'Gespeichert (Beleg #' + r.audit_seq
                                     + ').', error: false });
                        }).catch(fail());
                },
                onArchive: function (id) {
                    postJson('/api/mentoring/note/archive', { id: id })
                        .then(function (r) {
                            reload({ text: 'Archiviert (Beleg #' + r.audit_seq
                                     + ').', error: false });
                        }).catch(fail());
                },
                onRestore: function (id) {
                    postJson('/api/mentoring/note/restore', { id: id })
                        .then(function (r) {
                            reload({ text: 'Wiederhergestellt (Beleg #'
                                     + r.audit_seq + ').', error: false });
                        }).catch(fail());
                },
                onDuplicate: function (id) {
                    postJson('/api/mentoring/note/duplicate', { id: id })
                        .then(function (r) {
                            reload({ text: 'Dupliziert (Beleg #' + r.audit_seq
                                     + ').', error: false });
                        }).catch(fail());
                },
                // Drag&Drop/Pfeil-Ordnung (Build 407): EIN gebuendelter
                // Reorder-Beleg pro Ablegen. req = {owner_id, ids}.
                onReorder: function (req) {
                    postJson('/api/mentoring/note/reorder', req)
                        .then(function (r) {
                            reload({ text: 'Reihenfolge gespeichert (Beleg #'
                                     + r.audit_seq + ').', error: false });
                        }).catch(fail());
                }
            });
            log('Betreuungs-Notizen gerendert:',
                (data.notes || []).length, 'Notizen', archived ? '(Archiv)' : '');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Betreuungs-Notizen konnten nicht geladen werden: '
                + err.message);
        });
    }

    // loadAssignment: SCHREIB-Sicht. Laedt /api/assignable und rendert die
    // Zuweisungs-Tabelle. Jede Aenderung geht per POST an den auditierten
    // Schreibpfad. 'pendingMsg' traegt die Rueckmeldung (Erfolg ODER Fehler)
    // durch einen Neuaufbau hindurch — so bleibt sie sichtbar und geht nicht
    // still verloren (Grundregel 1).
    //
    // BUILD 534 — DER ENTSCHEIDENDE UNTERSCHIED ZU VORHER:
    //   Bis einschliesslich v0.8.532 lud diese Funktion nach JEDER Einzelaenderung ALLES neu
    //   und baute die Tabelle neu auf. Damit sprangen Sortierung, Bildlauf und
    //   jede getroffene Auswahl — und der naechste rasche Klick traf eine
    //   ANDERE Zeile als die, auf die der Anwender gezielt hatte (belegter
    //   Betriebsbefund mc 2026-07-25: ueber 80 Zuweisungen am Stueck, dabei
    //   "haeufig und unbeabsichtigt das falsche Element umgestellt"). Das war
    //   eine von der Oberflaeche GEBAUTE Fehlbedienungsfalle, kein
    //   Anwenderfehler.
    //
    //   Jetzt gilt: die BESTAETIGTE Serverantwort aktualisiert NUR die
    //   betroffene Zeile (view.bestaetige). 'Kein optimistisches UI' bleibt
    //   dabei unangetastet — die Sicht zeigt weiterhin ausschliesslich
    //   Zustaende, die der Server bestaetigt hat; sie baut nur nicht mehr
    //   alles ringsherum neu auf.
    //
    //   NACH EINEM STAPEL wird weiterhin VOLLSTAENDIG neu geladen. Das ist
    //   Absicht: ein Stapel verschiebt die Last aller Ermittler (die Zahl in
    //   der Ermittler-Auswahl) und beruehrt bis zu hunderte Zeilen — dort ist
    //   der frische Serverstand die ehrlichere Darstellung, und der Anwender
    //   hat den Vorgang bewusst abgeschlossen (kein rascher Klick, der ins
    //   Leere gehen koennte).
    function loadAssignment(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAssignment : null;
        if (!mod) {
            renderError(mainEl, 'Zuweisungs-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/assignable').then(function (data) {
            cleanupView();
            var view = mod.renderAssignment(mainEl, data, {

                // --- EINZELaenderung ---------------------------------------
                onChange: function (kind, subjectId, value) {
                    var req = mod.changeRequest(kind, subjectId, value);
                    if (!req) {
                        view.setMessage('Unbekannte Aenderungsart: ' + kind,
                                        true);
                        return;
                    }
                    view.setMessage('Schreibe …', false);
                    postJson(req.path, req.body).then(function (res) {
                        // Nur die betroffene Zeile — kein Neuaufbau.
                        // Uebernommen wird der Wert, den der SERVER
                        // zurueckmeldet, nicht der, den die Zelle hatte.
                        var bestaetigt = {};
                        if (kind === 'assign') {
                            bestaetigt.assigned_to =
                                (res.person_id === undefined
                                    ? null : res.person_id);
                        } else if (kind === 'priority') {
                            bestaetigt.priority = res.priority;
                        } else if (kind === 'status') {
                            bestaetigt.status = res.status;
                        }
                        view.bestaetige(subjectId, bestaetigt,
                            'Gespeichert (Beleg #' + res.audit_seq + ').');
                    }).catch(function (err) {
                        log('Schreibfehler', err);
                        // Die Zeile bleibt auf dem bestaetigten Stand; der
                        // Fehler wird benannt, nie still verschluckt.
                        view.verwerfe(subjectId, mod.fehlerMeldung(err)
                            + ' — es wurde NICHTS geschrieben.');
                    });
                },

                // --- SAMMELZUWEISUNG ---------------------------------------
                onBatch: function (changes) {
                    postJson('/api/case/assign_batch', { changes: changes })
                        .then(function (res) {
                            // Erst die Meldung bauen, dann neu laden — so
                            // ueberlebt sie den Neuaufbau (s. o.).
                            var m = mod.batchMeldung(res);
                            loadAssignment(mainEl, { text: m.text,
                                                     error: m.error });
                        }).catch(function (err) {
                            log('Sammelzuweisung fehlgeschlagen', err);
                            // KEIN Neuaufbau: der Server hat NICHTS
                            // geschrieben (erst pruefen, dann schreiben). Die
                            // getroffene Auswahl bleibt damit gueltig, und der
                            // Anwender kann sie berichtigen, statt achtzig
                            // Kaestchen neu anzuklicken.
                            view.setMessage(mod.fehlerMeldung(err)
                                + ' — es wurde NICHTS geschrieben. Die '
                                + 'Auswahl bleibt bestehen.', true);
                            view.setSammelmodus(true);
                        });
                },

                // --- KENNZAHLEN (spaeterer, eigener Abruf) -----------------
                onStats: function () {
                    fetchJson('/api/assignable/stats')
                        .then(function (payload) {
                            view.setStats(payload);
                        }).catch(function (err) {
                            // Die Zuweisung bleibt arbeitsfaehig — aber der
                            // Ausfall wird BENANNT, damit niemand leere
                            // Spalten fuer 'keine Werte' haelt.
                            log('Kennzahlen nicht ladbar', err);
                            view.setMessage('Kennzahlen (uid_stats) konnten '
                                + 'nicht geladen werden: ' + err.message
                                + '. Die Zuweisung selbst ist davon nicht '
                                + 'betroffen.', true);
                        });
                }
            });
            if (view) { state.table = view.table; }
            if (view && pendingMsg) {
                view.setMessage(pendingMsg.text, pendingMsg.error);
            }
            log('Zuweisung gerendert:', (data.cases || []).length, 'Faelle');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Zuweisung konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadReports: Berichts-Abnahme (/api/reports). force=true umgeht den
    // serverseitigen Scan-Cache (liest alle evidence-DBs neu ein).
    function loadReports(mainEl, force, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitReports : null;
        if (!mod) {
            renderError(mainEl, 'Berichts-Modul nicht geladen.');
            return;
        }
        var url = '/api/reports' + (force ? '?force=1' : '');
        fetchJson(url).then(function (data) {
            cleanupView();
            var t = mod.renderReports(mainEl, data, {
                onForceRescan: function () { loadReports(mainEl, true); },
                // Nur wer reports.approve besitzt, bekommt die Freigabe-Knoepfe.
                // (Der Server prueft es ohnehin erneut — die Oberflaeche soll
                // nur keine Aktion anbieten, die zwingend scheitern wuerde.)
                canApprove: hasCap(state.capabilities, 'reports.approve'),
                // Rueckgabe zur Nachbesserung: Lektor (reports.review) ODER
                // Chefin (reports.approve — impliziert review).
                canReview: hasCap(state.capabilities, 'reports.review'),

                // FREIGABE (Schreibpfad, Build 377): POST mit Schreib-Token.
                // Danach NEU LADEN — die Sicht zeigt nur bestaetigt
                // geschriebene Zustaende (kein optimistisches UI).
                onApprove: function (subjectId, reportId, isFinal) {
                    postJson('/api/report/approve', {
                        subject_id: subjectId, report_id: reportId,
                        is_final: !!isFinal
                    }).then(function (res) {
                        loadReports(mainEl, false, {
                            text: (isFinal ? 'Endgueltig freigegeben'
                                           : 'Freigegeben und versiegelt')
                                + ' (Beleg #' + res.audit_seq + ', Hash '
                                + String(res.content_sha256).slice(0, 12)
                                + '\u2026).',
                            error: false
                        });
                    }).catch(function (err) {
                        log('Freigabe-Fehler', err);
                        if (t && t.aiwSetResult) {
                            t.aiwSetResult('Fehler: ' + err.message, true);
                        }
                    });
                },

                // RUECKGABE zur Nachbesserung (Build 380): submitted -> draft.
                onReturn: function (subjectId, reportId) {
                    postJson('/api/report/return', {
                        subject_id: subjectId, report_id: reportId
                    }).then(function (res) {
                        loadReports(mainEl, false, {
                            text: 'Zur Nachbesserung zurueckgegeben (Beleg #'
                                + res.audit_seq + '). Der Autor kann den '
                                + 'Bericht wieder bearbeiten.',
                            error: false
                        });
                    }).catch(function (err) {
                        log('Rueckgabe-Fehler', err);
                        if (t && t.aiwSetResult) {
                            t.aiwSetResult('Fehler: ' + err.message, true);
                        }
                    });
                },

                // SIEGELPRUEFUNG (lesend): Hash neu bilden und vergleichen.
                onVerify: function (subjectId, reportId) {
                    fetchJson('/api/report/verify?subject_id=' + subjectId
                              + '&report_id=' + reportId)
                        .then(function (v) {
                            if (t && t.aiwShowVerify) { t.aiwShowVerify(v); }
                            log('Siegelpruefung', v);
                        }).catch(function (err) {
                            if (t && t.aiwSetResult) {
                                t.aiwSetResult(
                                    'Siegelpruefung fehlgeschlagen: '
                                    + err.message, true);
                            }
                        });
                }
            });
            state.table = t;
            if (t && pendingMsg && t.aiwSetResult) {
                // Rueckmeldung der Freigabe durch den Reload tragen.
                t.aiwSelectRow(null);
                var box = mainEl.querySelector('#aiw-report-actions');
                if (box) {
                    var m = document.createElement('div');
                    m.className = pendingMsg.error ? 'error' : 'ok';
                    m.id = 'aiw-report-msg';
                    m.textContent = pendingMsg.text;
                    box.appendChild(m);
                }
            }
            log('Berichte gerendert:', data.count, '-', data.rescanned,
                'DBs neu eingelesen');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Berichte konnten nicht geladen werden: ' + err.message);
        });
    }

    // loadResultsView: ERMITTLUNGSERGEBNIS (Build 395, Frontend zu 387/393).
    //
    //   GET /api/results/coverage -> Abdeckung JE FALL (auch nie bewertete)
    //   GET /api/results/stats    -> Verteilung je Kriterium
    //
    //   Die Statistik ist Scope 'alle' vorbehalten. Ein Ermittler mit 'eigene'
    //   bekommt dort 403 — das ist KEIN Fehler, sondern die Kapselung. Die
    //   Sicht faengt das ab und BENENNT es (statt eine leere Flaeche zu
    //   zeigen); die Abdeckung seiner eigenen Faelle sieht er vollstaendig.
    //   Deshalb darf ein Statistik-Fehler den GANZEN Aufbau nicht abbrechen.
    function loadResultsView(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitResults : null;
        if (!mod) {
            renderError(mainEl, 'Ergebnis-Modul nicht geladen.');
            return;
        }

        fetchJson('/api/results/coverage').then(function (cov) {
            return fetchJson('/api/results/stats')
                .then(function (st) { return { cov: cov, stats: st }; })
                .catch(function (err) {
                    log('Statistik nicht verfuegbar:', err.message);
                    return { cov: cov, stats: null };
                });
        }).then(function (both) {
            cleanupView();
            var res = mod.renderResults(mainEl, both.cov, both.stats, {})
                || { charts: [] };
            state.table = res.table || null;
            state.charts = res.charts || [];
            log('Ergebnis-Sicht gerendert:', both.cov.faelle_gesamt, 'Faelle,',
                both.cov.nie_bewertet, 'nie bewertet');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Ergebnis-Auswertung konnte nicht geladen werden: '
                + err.message);
        });
    }

    // loadCalendar: KALENDER & WIEDERVORLAGE (Build 386, Frontend zu 385).
    //
    //   ZWEI Abrufe, EINE Sicht:
    //     GET /api/calendar?von=&bis=  -> Monatsraster (externe Vorgaenge +
    //                                     Abwesenheiten + Feiertage)
    //     GET /api/external            -> Faelligkeitsliste + Arbeitsvorrat
    //   Beide muessen DENSELBEN Stichtag verwenden, sonst koennten Raster und
    //   Liste unterschiedliche Ampeln zeigen. Der Server bestimmt den Stichtag
    //   (Europe/Berlin); wir uebernehmen ihn aus der Kalender-Antwort und
    //   geben ihn der Vorgangsliste ausdruecklich mit.
    //
    //   KEIN optimistisches UI: jeder Schreibvorgang laedt beide Abrufe neu.
    function loadCalendar(mainEl, ym, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCalendar : null;
        if (!mod) {
            renderError(mainEl, 'Kalender-Modul nicht geladen.');
            return;
        }

        // Ohne Monatsangabe: der laufende Monat (Stichtag des Servers).
        ym = ym || state.calYm || mod.ymOf(new Date().toISOString().slice(0, 10));
        state.calYm = ym;
        var r = mod.monthRange(ym);

        fetchJson('/api/calendar?von=' + r.von + '&bis=' + r.bis)
            .then(function (cal) {
                // Vorgangsliste mit DEMSELBEN Stichtag abrufen.
                return fetchJson('/api/external?stichtag=' + cal.stichtag)
                    .then(function (ext) { return { cal: cal, ext: ext }; });
            })
            .then(function (both) {
                cleanupView();
                var canEdit = hasCap(state.capabilities, 'external.edit');

                function after(text, isError) {
                    loadCalendar(mainEl, ym, { text: text, error: isError });
                }
                function fail(err) {
                    // Der Fehler wird NICHT verschluckt; danach wird der
                    // TATSAECHLICHE Stand neu geladen.
                    log('Schreibfehler', err);
                    after('Fehler: ' + err.message + ' (es wurde nichts oder '
                          + 'nur ein Teil geschrieben \u2014 die Liste zeigt '
                          + 'den tatsaechlichen Stand).', true);
                }

                var view = mod.renderCalendar(mainEl, both.cal, both.ext, {
                    ym: ym,
                    canEdit: canEdit,
                    onMonth: function (neu) { loadCalendar(mainEl, neu); },

                    onCreate: function (body) {
                        postJson('/api/external/create', body)
                            .then(function (res) {
                                after('Vorgang ' + res.matter_id
                                      + ' angelegt (Beleg #' + res.audit_seq
                                      + ').', false);
                            }).catch(fail);
                    },
                    onDefer: function (body) {
                        postJson('/api/external/defer', body)
                            .then(function (res) {
                                after('Wiedervorlage verschoben auf '
                                      + body.wiedervorlage_am + ' (Beleg #'
                                      + res.audit_seq + ').', false);
                            }).catch(fail);
                    },
                    onAnswer: function (body) {
                        postJson('/api/external/answer', body)
                            .then(function (res) {
                                after('Antwort erfasst (Beleg #'
                                      + res.audit_seq + '). Der Vorgang bleibt '
                                      + 'in der Wiedervorlage, bis er '
                                      + 'ausgewertet ist.', false);
                            }).catch(fail);
                    },
                    onClose: function (body) {
                        postJson('/api/external/close', body)
                            .then(function (res) {
                                after('Vorgang ' + body.matter_id
                                      + ' ENDGUELTIG abgeschlossen ('
                                      + body.status + ', Beleg #'
                                      + res.audit_seq + ').', false);
                            }).catch(fail);
                    }
                });

                state.table = view && view.table;
                if (view && pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Kalender', ym, 'gerendert:', both.cal.count,
                    'Eintraege,', both.ext.count, 'Vorgaenge');
            })
            .catch(function (err) {
                cleanupView();
                renderError(mainEl,
                    'Kalender konnte nicht geladen werden: ' + err.message);
            });
    }

    // loadCases: FALL-ERKENNUNG (Build 384, Frontend zu 383).
    //   GET  /api/cases/detect  — rein lesender Abgleich Platte <-> Fallakte.
    //   POST /api/cases/import  — auditierte Aufnahme der AUSGEWAEHLTEN Faelle.
    // Wie bei der Zuweisung gilt: KEIN optimistisches UI. Nach dem Schreiben
    // wird neu geladen; die Rueckmeldung (Erfolg ODER Fehler ODER uebersprungene
    // Faelle) wird ueber 'pendingMsg' durch den Reload getragen, damit sie nicht
    // still verloren geht (Grundregel 1).
    function loadCases(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCases : null;
        if (!mod) {
            renderError(mainEl, 'Fall-Erkennungs-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/cases/detect').then(function (data) {
            cleanupView();
            var view = mod.renderCases(mainEl, data, {
                onImport: function (ids) {
                    var req = mod.importRequest(ids);
                    if (!req) {
                        if (view) {
                            view.setResult('Kein Fall ausgewaehlt.', true);
                        }
                        return;
                    }
                    postJson(req.path, req.body).then(function (res) {
                        // Serverantwort NICHT selbst deuten, sondern woertlich
                        // wiedergeben (imported MIT Beleg-Nr., skipped MIT
                        // Grund) — und dann den echten Zustand neu laden.
                        var r = mod.resultText(res);
                        loadCases(mainEl, { text: r.text, error: r.error });
                    }).catch(function (err) {
                        log('Aufnahme-Fehler', err);
                        loadCases(mainEl, {
                            text: 'Fehler bei der Aufnahme: ' + err.message
                                + ' (es wurde nichts oder nur ein Teil '
                                + 'geschrieben \u2014 die Liste oben zeigt den '
                                + 'tatsaechlichen Stand).',
                            error: true
                        });
                    });
                },

                // Build 534: Kennzahlen (uid_stats) fuer die angezeigten
                // Kennungen — auch fuer die NOCH NICHT aufgenommenen. Genau
                // die sind hier der Regelfall: ueber ihre Aufnahme wird in
                // dieser Sicht entschieden, und dafuer will man wissen, ob ein
                // Fall 12 oder 40.000 Beitraege hat.
                onStats: function (ids) {
                    if (!ids || !ids.length) { return; }
                    fetchJson('/api/assignable/stats?subject_ids='
                              + ids.join(','))
                        .then(function (payload) { view.setStats(payload); })
                        .catch(function (err) {
                            // Die Fall-Erkennung bleibt arbeitsfaehig — aber
                            // der Ausfall wird BENANNT, damit niemand leere
                            // Spalten fuer 'keine Werte' haelt.
                            log('Kennzahlen nicht ladbar', err);
                            view.setResult('Kennzahlen (uid_stats) konnten '
                                + 'nicht geladen werden: ' + err.message
                                + '. Die Fall-Erkennung selbst ist davon '
                                + 'nicht betroffen.', true);
                        });
                }
            });
            state.table = view && view.table;
            if (view && pendingMsg) {
                view.setResult(pendingMsg.text, pendingMsg.error);
            }
            log('Fall-Erkennung gerendert:', data.count, 'Faelle,',
                data.counts);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Fall-Erkennung konnte nicht geladen werden: ' + err.message);
        });
    }

    // applyIntegrity: zentrale Banner-Aktualisierung aus einer Integritaets-
    // Antwort ({ok, first_bad_seq, detail, tip_seq}). Nutzt das Integritaets-
    // Modul (bannerModel + applyBanner). Wird von loadIntegrity UND refreshBanner
    // aufgerufen, damit der Banner-Zustand an genau einer Stelle entsteht.
    function applyIntegrity(data) {
        var mod = (typeof window !== 'undefined') ? window.AIWCockpitIntegrity : null;
        var bannerEl = document.getElementById('aiw-integrity');
        if (!mod || !bannerEl) { return; }
        mod.applyBanner(bannerEl, mod.bannerModel(data));
    }

    // refreshBanner: Ketten-Gesundheit GLOBAL im Banner anzeigen — unabhaengig
    // von der aktiven Sicht. Ohne 'ops.view' bleibt der Banner still/neutral
    // (kein 403-Rauschen; Entscheidung 2026-07-10). Wird bei boot() und bei
    // SSE-'changed' (wenn die aktive Sicht nicht 'integrity' ist) aufgerufen.
    function refreshBanner() {
        var bannerEl = document.getElementById('aiw-integrity');
        if (!hasCap(state.capabilities, 'ops.view')) {
            if (bannerEl) {
                bannerEl.textContent = '';
                bannerEl.className = 'aiw-integrity aiw-integrity-hidden';
            }
            return;
        }
        fetchJson('/api/integrity').then(function (data) {
            applyIntegrity(data);
            log('Banner aktualisiert: ok =', data.ok, 'tip', data.tip_seq);
        }).catch(function (err) {
            // Fehler nicht verschlucken: Banner in den Fehlerzustand setzen.
            if (bannerEl) {
                bannerEl.className = 'aiw-integrity fehler';
                bannerEl.textContent =
                    'Integritaet nicht pruefbar: ' + err.message;
            }
        });
    }

    // loadIntegrity: Integritaets-/Ops-Sicht rendern (cockpit_integrity.js) und
    // dabei den globalen Banner gleich mit aktualisieren (eine Quelle).
    function loadIntegrity(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined') ? window.AIWCockpitIntegrity : null;
        if (!mod) {
            renderError(mainEl, 'Integritaets-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/integrity').then(function (data) {
            mod.renderIntegrity(mainEl, data);
            applyIntegrity(data);
            log('Integritaet gerendert: ok =', data.ok, 'tip', data.tip_seq);
        }).catch(function (err) {
            renderError(mainEl,
                'Integritaet konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadPromotion: FREMDFORUM-PROMOTION (Build 461, Frontend zu 460).
    //   GET  /api/promotion          — Kandidaten (forensic da, evidence fehlt)
    //                                  + ihr Promotions-Zustand (read, ops.view).
    //   POST /api/promotion/decide   — auditierte Entscheidung (ops.promote).
    // Wie ueberall gilt: KEIN optimistisches UI. Nach dem Schreiben wird die
    // Sicht NEU geladen; die Rueckmeldung (Erfolg ODER Fehler) wird ueber
    // 'pendingMsg' durch den Reload getragen, damit sie nicht still verloren
    // geht (Grundregel 1). Der Kandidaten-Scan misst die PLATTE — nach einem
    // Ereignis (SSE 'changed') kann sich der Bestand aendern -> neu messen.
    function loadPromotion(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitPromotion : null;
        if (!mod) {
            renderError(mainEl, 'Promotions-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/promotion').then(function (data) {
            cleanupView();
            var canEdit = hasCap(state.capabilities, 'ops.promote');

            function after(text, isError) {
                loadPromotion(mainEl, { text: text, error: isError });
            }

            var view = mod.renderPromotion(mainEl, data, {
                canEdit: canEdit,
                onDecide: function (body) {
                    postJson('/api/promotion/decide', body)
                        .then(function (res) {
                            after('Kandidat ' + res.subject_id + ': ' + res.von
                                + ' → ' + res.auf + ' (Beleg #'
                                + res.audit_seq + ').', false);
                        })
                        .catch(function (err) {
                            // Der Fehler wird NICHT verschluckt; danach wird der
                            // TATSAECHLICHE Stand neu geladen.
                            after('Fehler: ' + err.message + ' (es wurde nichts '
                                + 'geschrieben — die Liste zeigt den '
                                + 'tatsaechlichen Stand).', true);
                        });
                }
            });

            if (view && pendingMsg) {
                view.setResult(pendingMsg.text, pendingMsg.error);
            }
            log('Promotion gerendert:', data.candidate_count, 'Kandidat(en)');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Fremdforum-Promotion konnte nicht geladen werden: '
                + err.message);
        });
    }

    // loadReleases: EXTERNE FALLFREIGABE (Build 463, Frontend zu 462).
    //   GET  /api/releases         — Freigaben + berechtigte Empfaenger (F4) +
    //                                Umfang-Katalog (read, release.view).
    //   POST /api/release/grant    — Fall freigeben (release.grant, auditiert).
    //   POST /api/release/revoke   — Freigabe widerrufen (release.grant).
    // KEIN optimistisches UI: nach dem Schreiben Reload; die Rueckmeldung
    // (Erfolg/Fehler) wird ueber 'pendingMsg' durch den Reload getragen (GR1).
    function loadReleases(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitReleases : null;
        if (!mod) {
            renderError(mainEl, 'Freigabe-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/releases').then(function (data) {
            cleanupView();
            var canEdit = hasCap(state.capabilities, 'release.grant');

            function after(text, isError) {
                loadReleases(mainEl, { text: text, error: isError });
            }
            function fail(err) {
                after('Fehler: ' + err.message + ' (es wurde nichts '
                    + 'geschrieben — die Liste zeigt den tatsaechlichen '
                    + 'Stand).', true);
            }

            var view = mod.renderReleases(mainEl, data, {
                canEdit: canEdit,
                onGrant: function (body) {
                    postJson('/api/release/grant', body)
                        .then(function (res) {
                            after('Fall ' + body.subject_id + ' an '
                                + res.recipient_display + ' freigegeben '
                                + '(Freigabe ' + res.release_id + ', Beleg #'
                                + res.audit_seq + ').', false);
                        }).catch(fail);
                },
                onRevoke: function (body) {
                    postJson('/api/release/revoke', body)
                        .then(function (res) {
                            after('Freigabe ' + body.release_id + ' widerrufen '
                                + '(Beleg #' + res.audit_seq + ').', false);
                        }).catch(fail);
                }
            });

            if (view && pendingMsg) {
                view.setResult(pendingMsg.text, pendingMsg.error);
            }
            log('Freigaben gerendert:', data.count, 'Eintraege');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Externe Fallfreigaben konnten nicht geladen werden: '
                + err.message);
        });
    }

    // loadOnboarding: ONBOARDING/OFFBOARDING (Build 465, Frontend zu 464).
    //   GET  /api/onboarding?person_id=&kind=  — Checkliste + Fall-Last (read,
    //                                            onboarding.view).
    //   POST /api/onboarding/step              — Schritt setzen (onboarding.edit).
    // Die gewaehlte Person/Art lebt NUR im State (kein localStorage — Projekt-
    // regel), damit SSE-Reloads dieselbe Sicht neu laden. KEIN optimistisches UI.
    function loadOnboarding(mainEl, personId, kind, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitOnboarding : null;
        if (!mod) {
            renderError(mainEl, 'Onboarding-Modul nicht geladen.');
            return;
        }
        var pid = (personId != null) ? personId : state.onbPerson;
        var k = kind || state.onbKind || 'onboarding';
        state.onbPerson = (pid != null) ? pid : null;
        state.onbKind = k;

        var view = null;
        function after(text, isError) {
            loadOnboarding(mainEl, pid, k, { text: text, error: isError });
        }
        var opts = {
            canEdit: hasCap(state.capabilities, 'onboarding.edit'),
            personId: pid, kind: k,
            onLoad: function (sel) {
                loadOnboarding(mainEl, sel.personId, sel.kind);
            },
            onInvalid: function (msg) { if (view) { view.setResult(msg, true); } },
            onStep: function (body) {
                postJson('/api/onboarding/step', body)
                    .then(function (res) {
                        after('Schritt „' + body.step_code + '“ → '
                            + res.status + ' (Beleg #' + res.audit_seq + ').',
                            false);
                    })
                    .catch(function (err) {
                        after('Fehler: ' + err.message + ' (es wurde nichts '
                            + 'geschrieben — die Liste zeigt den tatsaechlichen '
                            + 'Stand).', true);
                    });
            }
        };

        // Noch keine Person gewaehlt -> nur die Auswahl (kein GET).
        if (pid == null) {
            cleanupView();
            view = mod.renderOnboarding(mainEl, null, opts);
            if (pendingMsg) { view.setResult(pendingMsg.text, pendingMsg.error); }
            return;
        }

        fetchJson('/api/onboarding?person_id=' + encodeURIComponent(pid)
                + '&kind=' + encodeURIComponent(k))
            .then(function (data) {
                cleanupView();
                view = mod.renderOnboarding(mainEl, data, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Onboarding gerendert:', data.person_id, k);
            })
            .catch(function (err) {
                cleanupView();
                // Trotz Fehler die Auswahl zeigen, damit man korrigieren kann.
                view = mod.renderOnboarding(mainEl, null, opts);
                view.setResult('Konnte nicht geladen werden: ' + err.message,
                    true);
            });
    }

    // loadPersonnel: PERSONALVERWALTUNG (Build 503; ersetzt die separate
    //   AD-Abgleich-Sicht aus Build 502 — der Abgleich ist jetzt Abschnitt).
    //   GET  /api/personnel               — Liste (read, personnel.view,
    //                                       KEIN AD-Zugriff).
    //   POST /api/personnel/flags         — Rollen-Flag setzen (personnel.edit).
    //   POST /api/personnel/role/assign   — Rolle zuweisen (personnel.edit).
    //   POST /api/personnel/role/revoke   — Zuweisung widerrufen (Soft-Revoke).
    //   AD-Abschnitt (personnel.sync): LAZY via _adsyncInto — /api/adsync wird
    //   erst auf Nutzerhandlung geholt (Live-LDAP). Nach einer AD-Aktion wird
    //   die Sicht MIT offenem Abschnitt neu geladen (genau EIN frischer
    //   LDAP-Abruf nach eigener Aktion); der SSE-Reload laedt NUR die Liste.
    //   KEIN optimistisches UI: nach jedem Schreiben wird neu geladen.
    function loadPersonnel(mainEl, pendingMsg, adsyncOpen) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitPersonnel : null;
        if (!mod) {
            renderError(mainEl, 'Personalverwaltungs-Modul nicht geladen.');
            return;
        }
        var view = null;
        function after(text, isError, keepAdsync) {
            loadPersonnel(mainEl, { text: text, error: isError },
                keepAdsync === true);
        }
        // _post: gemeinsame Schreib-Huelle der Listen-Aktionen. Fehler laden
        // die Sicht ebenfalls neu — die Liste zeigt danach den tatsaechlichen
        // Stand (es wurde nichts geschrieben).
        function _post(url, body, okText) {
            postJson(url, body)
                .then(function (res) { after(okText(res), false, false); })
                .catch(function (err) {
                    after('Fehler: ' + err.message + ' (es wurde nichts '
                        + 'geschrieben — die Liste zeigt den tatsaechlichen '
                        + 'Stand).', true, false);
                });
        }
        var opts = {
            adsyncOpen: adsyncOpen === true,
            onFlags: function (body) {
                _post('/api/personnel/flags', body, function (res) {
                    return 'Flags aktualisiert (Beleg #' + res.audit_seq
                        + ').';
                });
            },
            onAssign: function (body) {
                _post('/api/personnel/role/assign', body, function (res) {
                    return 'Rolle ' + res.role_code + ' zugewiesen (Beleg #'
                        + res.audit_seq + ').';
                });
            },
            onRevoke: function (body) {
                _post('/api/personnel/role/revoke', body, function (res) {
                    return 'Zuweisung widerrufen (Soft-Revoke, Beleg #'
                        + res.audit_seq + ').';
                });
            },
            onAdsyncLoad: function (box, setResult) {
                _adsyncInto(box, setResult, after);
            }
        };
        fetchJson('/api/personnel')
            .then(function (data) {
                cleanupView();
                view = mod.renderPersonnel(mainEl, data, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Personalverwaltung gerendert:',
                    (data.persons || []).length, 'Personen');
            })
            .catch(function (err) {
                cleanupView();
                renderError(mainEl, 'Personalverwaltung konnte nicht '
                    + 'geladen werden: ' + err.message);
            });
    }

    // loadFaelle: FALLUEBERSICHT (Build 574).
    //
    // Dieselbe Tabelle, dieselbe Quelle (/api/overview) und dieselbe
    // Renderfunktion (cockpit_overview.renderOverview) wie bisher im
    // Kachel-Steckplatz - nur mit dem Platz, den eine Tabelle mit einigen
    // hundert Zeilen braucht. Das Recht prueft der Endpunkt.
    //
    // HIER LANDET AUCH DER FALL-SPRUNG der Kommandopalette (Strg-K). Vorher
    // zielte er auf 'dashboard' und wurde im Steckplatz ausgewertet; mit der
    // Kompaktkachel gaebe es dort keine Zeile mehr, auf die man springen
    // koennte.
    function loadFaelle(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var ov = (typeof window !== 'undefined')
            ? window.AIWCockpitOverview : null;
        if (!ov) {
            renderError(mainEl, 'Fall-Uebersichts-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/overview').then(function (data) {
            cleanupView();
            mainEl.textContent = '';
            // BUILD 575: KEIN EIGENER KOPF MEHR. renderOverview schreibt seit
            // Build 349 selbst eine Ueberschrift und eine Unterzeile - und
            // die ist die bessere, weil sie den Umfang nennt ('alle Faelle
            // (Gesamtsicht)') und nicht nur die Zahl. Mein zusaetzlicher Kopf
            // aus Build 574 stand darueber und ergab denselben Titel zweimal
            // (Befund mc). Ein Titel gehoert an EINE Stelle; ich nehme die
            // aeltere und reichere sie nicht doppelt an.
            state.table = ov.renderOverview(mainEl, data, {});
            // Fall-Fokus aus der Kommandopalette (Build 459, hierher verlegt in
            // Build 574): nach dem Rendern zur gewaehlten Zeile springen und
            // danach zuruecksetzen, damit ein spaeteres Neuladen nicht erneut
            // springt.
            if (state.focusCaseId !== null && state.focusCaseId !== undefined
                    && typeof ov.focusCase === 'function') {
                ov.focusCase(state.table, state.focusCaseId);
                state.focusCaseId = null;
            }
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl, 'Fallübersicht konnte nicht geladen werden: '
                + err.message);
        });
    }

    // loadCapacityPflege: KAPAZITAETSPFLEGE (Build 559).
    //   GET  /api/capacity/stammdaten        — die vier pflegbaren Bestaende
    //                                          (capacity.edit; scope-aware).
    //   POST /api/capacity/worktime          — Regel-Arbeitszeit (append-only).
    //   POST /api/capacity/availability      — Abwesenheit/Garantie.
    //   POST /api/capacity/availability/remove
    //   POST /api/capacity/holiday | /holiday/remove | /reason
    //   KEIN optimistisches UI: nach JEDEM Schreiben wird neu geladen — auch
    //   nach einem Fehler, denn dann zeigt die Liste den tatsaechlichen Stand
    //   (es wurde nichts geschrieben). Muster: loadPersonnel (Build 503).
    // _capacityPersonen: die zuletzt geladene Personenliste. Sie dient nur
    // der Rueckmeldung ("Gespeichert: Mueller, ab ..."). Eine ID in der
    // Erfolgsmeldung waere fuer den Ausfuellenden wertlos.
    var _capacityPersonen = [];
    // Build 663 (Ticket d3f933cd): die zuletzt gebaute Pflegesicht.
    // Sie wird nur festgehalten, um beim Sichtwechsel die Von/Bis-
    // Kopplung abzumelden. Die DOM-Knoten verschwinden ohnehin; die
    // ausdrueckliche Abmeldung ist die guenstigere Annahme, wenn ein
    // Feld spaeter einmal wiederverwendet statt neu gebaut wird.
    var _capacityPflegeView = null;
    function _personName(personId) {
        var treffer = null;
        _capacityPersonen.forEach(function (p) {
            if (p && p.id === personId) { treffer = p; }
        });
        return treffer ? (treffer.display_name || treffer.system_username)
                       : ('#' + personId);
    }

    function loadCapacityPflege(mainEl, uebergabe) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCapacityPflege : null;
        if (!mod) {
            renderError(mainEl, 'Kapazitaetspflege-Modul nicht geladen.');
            return;
        }
        // uebergabe = { text, error, feld, formular, entfernte } — was ueber das
        // Neuladen hinweg erhalten bleibt (Build 561). OHNE das leert jedes
        // Neuladen das Stichtagsfeld, und die naechste Eingabe scheitert am
        // Server, ohne dass jemand versteht, warum (Befund mc, Build 560).
        uebergabe = uebergabe || {};
        var view = null;

        function after(text, isError, feld, formular) {
            loadCapacityPflege(mainEl, { text: text, error: isError,
                                         feld: feld, formular: formular,
                                         entfernte: uebergabe.entfernte });
        }
        function _post(url, body, okText, formularNachher) {
            // Der Zustand wird VOR dem Absenden festgehalten: nach dem
            // Neuladen ist das alte DOM weg.
            var zustand = (view && view.formularLesen)
                ? view.formularLesen() : null;
            postJson(url, body)
                .then(function (res) {
                    after(okText(res), false, null,
                          formularNachher === undefined ? zustand
                                                        : formularNachher);
                })
                .catch(function (err) {
                    // Im Fehlerfall bleibt ALLES stehen - es wurde nichts
                    // geschrieben, und der Anwender soll nicht neu tippen.
                    after('Fehler: ' + err.message + ' — es wurde nichts '
                        + 'geschrieben, die Eingaben bleiben stehen.',
                        true, err.feld || null, zustand);
                });
        }
        var opts = {
            formular: uebergabe.formular || null,
            onWorktimeSet: function (body) {
                _post('/api/capacity/worktime', body, function (res) {
                    return mod.uebernahmeText(
                        _personName(body.person_id), res.effective_from,
                        body, res.audit_seq, false);
                });
            },
            onWorktimeReplace: function (body) {
                _post('/api/capacity/worktime/replace', body, function (res) {
                    return mod.uebernahmeText(
                        _personName(body.person_id), res.effective_from,
                        body, res.gesetzt_seq, true);
                // Nach dem Ersetzen faellt der Bearbeitungsmodus weg: die
                // Zeile, die er festhielt, gibt es nicht mehr.
                }, { worktime: { person_id: body.person_id,
                                 effective_from: body.effective_from } });
            },
            onWorktimeRemove: function (worktimeId) {
                _post('/api/capacity/worktime/remove',
                    { worktime_id: worktimeId }, function (res) {
                        return 'Arbeitszeit-Zeile #' + worktimeId
                            + ' entfernt. Sie bleibt in der Datenbank '
                            + 'stehen und faellt nur aus Rechnung und Liste '
                            + '(Beleg #' + res.audit_seq + ').';
                    });
            },
            onWorktimeEdit: function (zeile) {
                // SCHREIBT NICHTS: fuellt nur das Formular und schaltet den
                // Modus um. Erst das Speichern ersetzt.
                var vorgabe = { person_id: zeile.person_id,
                                effective_from: zeile.effective_from,
                                _ersetzt_id: zeile.id };
                ['mon_min', 'tue_min', 'wed_min', 'thu_min', 'fri_min',
                 'sat_min', 'sun_min'].forEach(function (k) {
                    vorgabe[k] = zeile[k];
                });
                loadCapacityPflege(mainEl, {
                    text: 'Zeile #' + zeile.id + ' zum Bearbeiten geladen. '
                        + 'Speichern ersetzt sie; die alte Zeile bleibt als '
                        + 'Beleg erhalten.',
                    error: false, formular: { worktime: vorgabe } });
            },
            onWorktimeEditAbort: function () {
                loadCapacityPflege(mainEl, {
                    text: 'Bearbeitung abgebrochen. Es wurde nichts geaendert.',
                    error: false, entfernte: uebergabe.entfernte });
            },
            // Build 563: die Umschaltung laedt NEU, statt im Browser zu
            // filtern. Der Server entscheidet, was sichtbar ist - ein
            // Frontend-Filter koennte Zeilen zeigen, die das Recht oder der
            // Scope gar nicht hergibt.
            onEntfernteUmschalten: function (an) {
                loadCapacityPflege(mainEl, {
                    text: an
                        ? 'Entfernte Zeilen eingeblendet. Sie sind in der '
                          + 'Spalte "Stand" gekennzeichnet und nicht mehr '
                          + 'bearbeitbar.'
                        : 'Entfernte Zeilen ausgeblendet. Ihre Zahl steht '
                          + 'weiterhin ueber jeder Liste.',
                    error: false, entfernte: an,
                    formular: (view && view.formularLesen)
                        ? view.formularLesen() : null });
            },
            onAvailabilitySet: function (body) {
                _post('/api/capacity/availability', body, function (res) {
                    return 'Abwesenheit gespeichert (Beleg #'
                        + res.audit_seq + ').';
                });
            },
            onAvailabilityRemove: function (entryId) {
                _post('/api/capacity/availability/remove',
                    { entry_id: entryId }, function (res) {
                        return 'Abwesenheit entfernt (Soft-Revoke, Beleg #'
                            + res.audit_seq + ').';
                    });
            },
            onHolidayAdd: function (body) {
                _post('/api/capacity/holiday', body, function (res) {
                    return 'Feiertag ' + res.day + ' angelegt (Beleg #'
                        + res.audit_seq + ').';
                });
            },
            onHolidayRemove: function (holidayId) {
                _post('/api/capacity/holiday/remove',
                    { holiday_id: holidayId }, function (res) {
                        return 'Feiertag entfernt (Beleg #'
                            + res.audit_seq + ').';
                    });
            },
            onReasonAdd: function (body) {
                _post('/api/capacity/reason', body, function (res) {
                    return 'Grund "' + res.code + '" angelegt (Beleg #'
                        + res.audit_seq + ').';
                });
            }
        };
        fetchJson('/api/capacity/stammdaten'
                  + (uebergabe.entfernte ? '?include_deleted=1' : ''))
            .then(function (data) {
                cleanupView();
                _capacityPersonen = data.persons || [];
                view = mod.renderCapacityPflege(mainEl, data, opts);
                _capacityPflegeView = view;
                if (uebergabe.text && view && view.setResult) {
                    view.setResult(uebergabe.text, uebergabe.error);
                }
                if (uebergabe.feld && view && view.markiereFeld) {
                    view.markiereFeld(uebergabe.feld);
                }
                log('Kapazitaetspflege gerendert:', data.counts);
            })
            .catch(function (err) {
                cleanupView();
                renderError(mainEl, 'Kapazitaetspflege konnte nicht geladen '
                    + 'werden: ' + err.message);
            });
    }

    // _adsyncInto: laedt die AD-Vorschau (/api/adsync) in den Abschnitts-
    //   Container der Personal-Seite und verdrahtet die Vollzugs-Callbacks
    //   der WIEDERVERWENDETEN Komponente AIWCockpitAdSync (Build 502).
    //   after(text, isError, keepAdsync=true) laedt die GANZE Sicht neu und
    //   oeffnet den AD-Abschnitt wieder (frische Vorschau nach eigener Aktion).
    function _adsyncInto(containerEl, setResult, after) {
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAdSync : null;
        if (!mod) {
            setResult('AD-Abgleich-Modul nicht geladen.', true);
            return;
        }
        var sub = null;
        fetchJson('/api/adsync')
            .then(function (data) {
                sub = mod.renderAdSync(containerEl, data, {
                    onApply: function () {
                        postJson('/api/adsync/apply', {})
                            .then(function (res) {
                                after(res.created.length + ' Neuaufnahmen, '
                                    + res.renamed.length
                                    + ' Namensaenderungen vollzogen '
                                    + '(Lauf-Beleg #' + res.run_seq + ').',
                                    false, true);
                            })
                            .catch(function (err) {
                                after('Fehler: ' + err.message + ' (es wurde '
                                    + 'ggf. nur ein Teil vollzogen — die '
                                    + 'Sicht zeigt den tatsaechlichen '
                                    + 'Stand).', true, true);
                            });
                    },
                    onDecide: function (body) {
                        postJson('/api/adsync/decide', body)
                            .then(function (res) {
                                var verb = { deactivate: 'deaktiviert (nur '
                                        + 'inaktiv, nicht geloescht)',
                                    abort: 'Abbruch protokolliert',
                                    reactivate: 'reaktiviert' }[res.action]
                                    || res.action;
                                after(res.system_username + ': ' + verb
                                    + ' (Beleg #' + res.audit_seq + ').',
                                    false, true);
                            })
                            .catch(function (err) {
                                // Falsches Wort/Fachfehler: NICHT neu laden
                                // (Eingaben erhalten), nur Ergebniszeile.
                                if (sub) {
                                    sub.setResult('Nicht vollzogen: '
                                        + err.message, true);
                                }
                            });
                    }
                });
                log('AD-Abschnitt gerendert:', data.counts);
            })
            .catch(function (err) {
                setResult('AD-Vorschau konnte nicht geladen werden: '
                    + err.message, true);
            });
    }

    // loadCrossref: KREUZBEZUG — Katalog identifizierter Personen (Build 471,
    //   AP-2A(2b), Frontend zu 470).
    //   GET  /api/crossref            — Katalog (read, crossref.view).
    //   POST /api/crossref/set        — Zuordnung anlegen/revidieren
    //                                   (crossref.edit). KEIN optimistisches UI:
    //                                   nach dem Schreiben Sicht NEU laden.
    function loadCrossref(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCrossref : null;
        if (!mod) {
            renderError(mainEl, 'Kreuzbezug-Modul nicht geladen.');
            return;
        }

        var view = null;
        function after(text, isError) {
            loadCrossref(mainEl, { text: text, error: isError });
        }
        var opts = {
            canEdit: hasCap(state.capabilities, 'crossref.edit'),
            onSet: function (body) {
                postJson('/api/crossref/set', body)
                    .then(function (res) {
                        var was = res.created ? 'angelegt' : 'revidiert';
                        after('Zuordnung subject_id ' + body.subject_id + ' '
                            + was + ' → ' + res.confidence_code
                            + ' (Beleg #' + res.audit_seq + ').', false);
                    })
                    .catch(function (err) {
                        after('Fehler: ' + err.message + ' (es wurde nichts '
                            + 'geschrieben — die Liste zeigt den tatsaechlichen '
                            + 'Stand).', true);
                    });
            }
        };

        fetchJson('/api/crossref')
            .then(function (data) {
                cleanupView();
                view = mod.renderCrossref(mainEl, data, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Kreuzbezug gerendert:',
                    (data && data.entries ? data.entries.length : 0));
            })
            .catch(function (err) {
                cleanupView();
                view = mod.renderCrossref(mainEl, { entries: [] }, opts);
                view.setResult('Konnte nicht geladen werden: ' + err.message,
                    true);
            });
    }

    // loadCrossfindings: QUERFUND-META-UEBERSICHT (Build 478, AP-2A(3), Frontend
    //   zu 474). REIN LESEND. GET /api/crossfindings (Recht crossref.view;
    //   optional ?only_open=1). KEIN SSE-Refresh — Querfunde entstehen ueber die
    //   automatische forensic_api-Pipeline, nicht ueber den audit_log; ein SSE-
    //   Trigger wuerde nicht feuern. Stattdessen manuelles „Aktualisieren".
    //   503 (Substrat fehlt) -> Fehlerzustand, KEINE leere Liste (Grundregel 1).
    function loadCrossfindings(mainEl, onlyOpen, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        onlyOpen = onlyOpen === true;
        var onlyUnack = state.cfOnlyUnack === true;
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCrossfindings : null;
        if (!mod) {
            renderError(mainEl, 'Querfunde-Modul nicht geladen.');
            return;
        }

        var view = null;
        function after(text, isError) {
            loadCrossfindings(mainEl, onlyOpen, { text: text, error: isError });
        }

        var opts = {
            onlyOpen: onlyOpen,
            onlyUnacknowledged: onlyUnack,
            // Build 508: Bewerten braucht crossref.edit. Ohne das Recht zeigt
            // die Sicht den Rueckkanal-Stand, bietet aber KEINE Aktion an.
            canEdit: hasCap(state.capabilities, 'crossref.edit'),
            onReload: function (nextOpen, nextUnack) {
                // State merken, damit ein View-Wechsel die Filter beibehaelt.
                state.cfOnlyOpen = (nextOpen === true);
                state.cfOnlyUnack = (nextUnack === true);
                loadCrossfindings(mainEl, state.cfOnlyOpen);
            },
            // Build 508: auditierte Rueckkanal-Entscheidung. KEIN
            // optimistisches UI — nach dem Schreiben wird neu geladen, damit
            // auch eine ABGELEHNTE Entscheidung den echten Stand zeigt.
            onDecide: function (body) {
                postJson('/api/crossfindings/decide', body)
                    .then(function (res) {
                        after('Querfund #' + body.finding_id + ' -> '
                            + res.status_code + ' (Beleg #' + res.audit_seq
                            + ').', false);
                    })
                    .catch(function (err) {
                        after('Fehler: ' + err.message + ' (es wurde nichts '
                            + 'geschrieben — die Liste zeigt den '
                            + 'tatsaechlichen Stand).', true);
                    });
            }
        };

        var params = [];
        if (onlyOpen) { params.push('only_open=1'); }
        if (onlyUnack) { params.push('only_unacknowledged=1'); }
        var url = '/api/crossfindings'
            + (params.length ? ('?' + params.join('&')) : '');

        fetchJson(url)
            .then(function (data) {
                cleanupView();
                view = mod.renderCrossfindings(mainEl, data, opts);
                if (pendingMsg) { _cfMsg(pendingMsg); }
                log('Querfunde gerendert:',
                    (data && data.findings ? data.findings.length : 0));
            })
            .catch(function (err) {
                // Auch 503 landet hier — als Fehlerzustand anzeigen, NICHT leer.
                cleanupView();
                view = mod.renderCrossfindings(mainEl, { error: err.message },
                                               opts);
                if (pendingMsg) { _cfMsg(pendingMsg); }
            });
    }

    // _cfMsg: schreibt die Rueckmeldung einer Rueckkanal-Entscheidung in die
    // Ergebniszeile der frisch gerenderten Sicht. Bewusst ueber die id statt
    // ueber einen Rueckgabewert: renderCrossfindings ist (historisch) eine
    // reine Zeichenfunktion ohne Handle, und das soll so bleiben.
    function _cfMsg(msg) {
        var el = document.getElementById('aiw-cff-result');
        if (!el || !msg) { return; }
        el.textContent = msg.text || '';
        el.classList.toggle('error', msg.error === true);
        el.classList.toggle('ok', msg.error === false);
    }

    // loadAlias: GLOBALER ALIAS-KATALOG (Build 505, AP-2A/A1, Frontend zu 504).
    //   GET  /api/alias                    — Katalog / ?q= Rueckwaertssuche /
    //                                        ?subject_id=N / ?include_retracted=1
    //   POST /api/alias/add|update|retract|reinstate  (crossref.edit)
    //   KEIN optimistisches UI: nach jedem Schreiben wird die Sicht NEU geladen,
    //   damit auch ein serverseitig ABGELEHNTER Schreibversuch (Duplikat,
    //   fehlender Grund) den tatsaechlichen Stand zeigt.
    //   SSE-Refresh ist hier RICHTIG (anders als bei 'crossfindings'): Alias-
    //   Aenderungen laufen ueber den coordinator-audit_log, der Strom feuert.
    //   Such-/Filterzustand lebt im State (kein localStorage), damit ein
    //   SSE-Reload oder ein View-Wechsel dieselbe Sicht wiederherstellt.
    function loadAlias(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAlias : null;
        if (!mod) {
            renderError(mainEl, 'Alias-Modul nicht geladen.');
            return;
        }

        var query = state.aliasQuery || '';
        var inclRetr = state.aliasInclRetracted === true;
        var view = null;
        function after(text, isError) {
            loadAlias(mainEl, { text: text, error: isError });
        }
        function fail(err) {
            after('Fehler: ' + err.message + ' (es wurde nichts geschrieben — '
                + 'die Liste zeigt den tatsaechlichen Stand).', true);
        }

        var opts = {
            canEdit: hasCap(state.capabilities, 'crossref.edit'),
            query: query,
            includeRetracted: inclRetr,
            // Build 600: Ergebnis der Namensaufloesung zur Katalogsuche.
            // Wird unten NACH /api/alias nachgeladen und die Sicht neu
            // gezeichnet — die Aliasse sollen nicht auf die zweite Quelle
            // warten muessen.
            namen: state.aliasNamen || null,
            onSearch: function (term) {
                state.aliasQuery = String(term || '').trim();
                state.aliasNamen = null;   // altes Ergebnis NIE stehen lassen
                loadAlias(mainEl);
            },
            // Build 600: ein Treffer der Namensaufloesung fuehrt in den
            // Katalog DIESES Kontos — die Bruecke Name -> Konto -> Aliasse.
            onSubject: function (sid) {
                state.aliasQuery = String(sid);
                state.aliasNamen = null;
                loadAlias(mainEl);
            },
            // Build 600: RUECKWAERTS (Kennung -> Name) fuer die
            // Kontrollanzeige unter dem subject_id-Feld. Ein Fehlschlag wird
            // BENANNT und nicht als Leerbefund ausgegeben (Grundregel 1) —
            // 'kein Name gefunden' und 'nicht abfragbar' sind verschiedene
            // Aussagen mit verschiedenen Folgen.
            onResolve: function (sid, cb) {
                fetchJson('/api/names?subject_id=' + encodeURIComponent(sid))
                    .then(function (d) { cb(d); })
                    .catch(function (err) {
                        log('Namensaufloesung fehlgeschlagen', err);
                        cb({ fehler: err.message });
                    });
            },
            // Build 600: VORWAERTS (Name -> Kennungen).
            onNameSearch: function (term, cb) {
                fetchJson('/api/names?q=' + encodeURIComponent(term))
                    .then(function (d) { cb(d); })
                    .catch(function (err) {
                        log('Namenssuche fehlgeschlagen', err);
                        cb({ fehler: err.message });
                    });
            },
            onToggleRetracted: function (next) {
                state.aliasInclRetracted = (next === true);
                loadAlias(mainEl);
            },
            onAdd: function (body) {
                postJson('/api/alias/add', body)
                    .then(function (res) {
                        after('Alias erfasst (Eintrag #' + res.alias_id
                            + ', Beleg #' + res.audit_seq + ').', false);
                    })
                    .catch(fail);
            },
            onUpdate: function (body) {
                postJson('/api/alias/update', body)
                    .then(function (res) {
                        after('Eintrag #' + res.alias_id + ' geändert '
                            + '(Beleg #' + res.audit_seq + ').', false);
                    })
                    .catch(fail);
            },
            onRetract: function (body) {
                postJson('/api/alias/retract', body)
                    .then(function (res) {
                        after('Eintrag #' + res.alias_id + ' widerrufen '
                            + '(Beleg #' + res.audit_seq + '). Die Zeile '
                            + 'bleibt als Beleg erhalten.', false);
                    })
                    .catch(fail);
            },
            onReinstate: function (body) {
                postJson('/api/alias/reinstate', body)
                    .then(function (res) {
                        after('Widerruf von Eintrag #' + res.alias_id
                            + ' zurückgenommen (Beleg #' + res.audit_seq
                            + ').', false);
                    })
                    .catch(fail);
            }
        };

        // Die Suchmaske ist bewusst EIN Feld: eine reine Zahl wird als Konto
        // gelesen, alles andere als Name. Zwei getrennte Felder haetten die
        // Ermittlerin bei jeder Suche zu einer Entscheidung gezwungen, die das
        // Werkzeug selbst treffen kann.
        var url = '/api/alias';
        var params = [];
        if (query) {
            params.push(/^\d+$/.test(query)
                ? ('subject_id=' + encodeURIComponent(query))
                : ('q=' + encodeURIComponent(query)));
        }
        if (inclRetr) { params.push('include_retracted=1'); }
        if (params.length) { url += '?' + params.join('&'); }

        // Build 600: die Namensaufloesung zur Katalogsuche wird NACH dem
        // Katalog geholt und die Sicht dann EINMAL neu gezeichnet. Grund: der
        // Aliaskatalog liegt in derselben coordinator.db und ist sofort da;
        // die globale Namensliste (default.db, rund 477.000 Zeilen) kann
        // dauern. Die Sicht soll nicht auf die zweite Quelle warten.
        // Ein Fehlschlag der ZWEITEN Quelle laesst den Katalog stehen und
        // wird BENANNT — er darf die Hauptsicht nicht mit sich reissen.
        function namenNachladen(term) {
            if (!term) { return; }
            fetchJson('/api/names?' + (/^\d+$/.test(term)
                    ? ('subject_id=' + encodeURIComponent(term))
                    : ('q=' + encodeURIComponent(term))))
                .then(function (n) {
                    state.aliasNamen = n;
                    // Nur neu zeichnen, wenn die Sicht noch dieselbe Suche
                    // zeigt — sonst ueberschriebe eine spaet eintreffende
                    // Antwort eine inzwischen andere Suche.
                    if (state.aliasQuery === term
                            && state.activeId === 'alias') {
                        loadAlias(mainEl);
                    }
                })
                .catch(function (err) {
                    log('Namensaufloesung nicht ladbar', err);
                    state.aliasNamen = { fehler: err.message, treffer: [] };
                    if (state.aliasQuery === term
                            && state.activeId === 'alias') {
                        loadAlias(mainEl);
                    }
                });
        }

        fetchJson(url)
            .then(function (data) {
                cleanupView();
                view = mod.renderAlias(mainEl, data, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                if (query && !state.aliasNamen) { namenNachladen(query); }
                log('Aliasse gerendert:',
                    (data && data.entries ? data.entries.length : 0));
            })
            .catch(function (err) {
                // Ladefehler als FEHLER anzeigen, nicht als leeren Katalog.
                cleanupView();
                view = mod.renderAlias(mainEl, { error: err.message }, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
            });
    }

    // loadMerge: IDENTITAETS-GRUPPEN (Build 510, AP-2A/A3, Frontend zu 509).
    //   GET  /api/merge  (?subject_id=N -> ganze Gruppe, ?include_split=1)
    //   POST /api/merge/set | /api/merge/split | /api/merge/remerge
    //   KEIN optimistisches UI. SSE-Refresh ist hier RICHTIG: Merge/Split
    //   laufen ueber den coordinator-audit_log, der Strom feuert.
    //   KONFLIKTMELDUNGEN DES SERVERS WERDEN WOERTLICH DURCHGEREICHT — sie
    //   nennen die beteiligten subject_ids und den konstruktiven Ausweg; eine
    //   Zusammenfassung waere hier ein Informationsverlust.
    function loadMerge(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMerge : null;
        if (!mod) {
            renderError(mainEl, 'Identitaets-Modul nicht geladen.');
            return;
        }

        var query = state.mergeQuery || '';
        var inclSplit = state.mergeInclSplit === true;
        var view = null;
        function after(text, isError) {
            loadMerge(mainEl, { text: text, error: isError });
        }
        function fail(err) {
            after('Fehler: ' + err.message + ' (es wurde nichts geschrieben — '
                + 'die Liste zeigt den tatsaechlichen Stand).', true);
        }

        var opts = {
            canEdit: hasCap(state.capabilities, 'crossref.edit'),
            query: query,
            includeSplit: inclSplit,
            onSearch: function (term) {
                state.mergeQuery = String(term || '').trim();
                loadMerge(mainEl);
            },
            onToggleSplit: function (next) {
                state.mergeInclSplit = (next === true);
                loadMerge(mainEl);
            },
            onMerge: function (body) {
                postJson('/api/merge/set', body)
                    .then(function (res) {
                        after('Konto ' + res.merged_subject_id
                            + ' dem Primärkonto ' + res.primary_subject_id
                            + ' zugeordnet (Zusammenführung #' + res.merge_id
                            + ', Beleg #' + res.audit_seq + ').', false);
                    })
                    .catch(fail);
            },
            onRevise: function (body) {
                postJson('/api/merge/set', body)
                    .then(function (res) {
                        after('Zusammenführung #' + res.merge_id
                            + ' revidiert (Beleg #' + res.audit_seq + ').',
                            false);
                    })
                    .catch(fail);
            },
            onSplit: function (body) {
                postJson('/api/merge/split', body)
                    .then(function (res) {
                        after('Zusammenführung #' + res.merge_id
                            + ' getrennt (Beleg #' + res.audit_seq + '). Die '
                            + 'Zeile bleibt als Beleg erhalten.', false);
                    })
                    .catch(fail);
            },
            onRemerge: function (body) {
                postJson('/api/merge/remerge', body)
                    .then(function (res) {
                        after('Trennung von #' + res.merge_id
                            + ' zurückgenommen (Beleg #' + res.audit_seq
                            + ').', false);
                    })
                    .catch(fail);
            }
        };

        var url = '/api/merge';
        var params = [];
        // Nur eine reine Zahl ist eine subject_id — alles andere waere eine
        // stille Fehlinterpretation.
        if (query && /^\d+$/.test(query)) {
            params.push('subject_id=' + encodeURIComponent(query));
        }
        if (inclSplit) { params.push('include_split=1'); }
        if (params.length) { url += '?' + params.join('&'); }

        fetchJson(url)
            .then(function (data) {
                cleanupView();
                view = mod.renderMerge(mainEl, data, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Identitaets-Gruppen gerendert:',
                    (data && data.entries ? data.entries.length : 0));
            })
            .catch(function (err) {
                cleanupView();
                view = mod.renderMerge(mainEl, { error: err.message }, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
            });
    }

    // loadAudit: AUDIT-/REVISIONS-EXPLORER (Build 467, AP-2E). REIN LESEND.
    //   GET /api/audit/facets  — Filter-Auswahl (Event-Typen + Akteure).
    //   GET /api/audit         — gefilterte, paginierte Seite.
    //   Der "Gerichtsfeste Export" ist ein Link auf /api/audit/export mit den
    //   ANGEWANDTEN Filtern. Filter/Offset leben im State (kein localStorage),
    //   damit ein SSE-Reload dieselbe Sicht wiederherstellt.
    function loadAudit(mainEl, filters, offset) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAudit : null;
        if (!mod) {
            renderError(mainEl, 'Audit-Modul nicht geladen.');
            return;
        }
        var f = filters || state.auditFilters || {};
        var off = (offset != null) ? offset : (state.auditOffset || 0);
        state.auditFilters = f;
        state.auditOffset = off;

        var qs = mod.buildQuery(f, { limit: 50, offset: off });
        // Facetten und Seite parallel; Facetten-Fehler darf die Sicht nicht
        // blockieren (dann eben ohne Vorauswahl-Listen).
        fetchJson('/api/audit/facets')
            .catch(function () { return { event_types: [], actors: [] }; })
            .then(function (facets) {
                return fetchJson('/api/audit?' + qs)
                    .then(function (data) { return { facets: facets, data: data }; });
            })
            .then(function (both) {
                cleanupView();
                mod.renderAudit(mainEl, both.data, both.facets, {
                    filters: f,
                    onFilter: function (nf) { loadAudit(mainEl, nf, 0); },
                    onPage: function (newOff) { loadAudit(mainEl, f, newOff); }
                });
                log('Audit gerendert:', both.data.total, 'Treffer');
            })
            .catch(function (err) {
                cleanupView();
                renderError(mainEl,
                    'Audit-Explorer konnte nicht geladen werden: '
                    + err.message);
            });
    }

    // loadLectorate: LEKTORAT (W4, Build 413, Slice 1). Laedt die Berichtsliste
    // (/api/reports, scope-korrekt serverseitig) und rendert die Gegenlese-
    // Sicht: Auswahl + read-only Berichtstext-Vorschau (<iframe> auf
    // /api/report/render, SF-1). Annotationen (SF-2) und Kommentare (SF-3)
    // folgen in den naechsten Slices (Build 414/415).
    function loadLectorate(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitLectorate : null;
        if (!mod) {
            renderError(mainEl, 'Lektorat-Modul nicht geladen.');
            return;
        }
        // reloadComments (Build 415): Kommentare (Union, SF-3) laden und
        // rendern. Nach JEDER Schreibaktion (Anlegen/Aufloesen) erneut
        // aufgerufen -> die Sicht zeigt nur bestaetigt geschriebene Zustaende
        // (kein optimistisches UI, Grundregel 1).
        // Build 659 (Vorgang 317481d3): Die Kommentare kommen jetzt ZUSAMMEN
        // mit dem Blockkatalog. Beide werden nebenlaeufig geholt und erst
        // gemeinsam gerendert — sonst zeigte die Maske einen Augenblick lang
        // ein leeres, gesperrtes Auswahlfeld, das wie ein Fehler aussieht.
        //
        // SCHLAEGT NUR DER KATALOG FEHL, werden die Kommentare trotzdem
        // angezeigt (sie sind Ermittlungsstand und duerfen nicht an einer
        // Nebenquelle haengen); das Auswahlfeld bleibt dann leer und gesperrt
        // und sagt selbst, dass es nichts anzubieten hat. Der Grund steht in
        // der Konsole - eine stumme leere Liste waere von 'Bericht hat keine
        // Bloecke' nicht zu unterscheiden (Grundregel 1).
        var reloadComments = function (uid, rid) {
            Promise.all([
                fetchJson(mod.commentsUrl(uid, rid)),
                fetchJson(mod.blocksUrl(uid, rid)).catch(function (e) {
                    log('Blockkatalog nicht ladbar:', e && e.message);
                    return null;
                })
            ]).then(function (res) {
                var cd = res[0];
                var bd = res[1];
                mod.renderComments(cd, {
                    personId: state.personId,
                    blocks: (bd && bd.blocks) ? bd.blocks : [],
                    onAdd: function (body) {
                        postJson('/api/report/comment', body)
                            .then(function () {
                                reloadComments(body.subject_id, body.report_id);
                            })
                            .catch(function (e) {
                                mod.commentsError(e && e.message);
                            });
                    },
                    onResolve: function (body) {
                        postJson('/api/report/comment/resolve', body)
                            .then(function () { reloadComments(uid, rid); })
                            .catch(function (e) {
                                mod.commentsError(e && e.message);
                            });
                    }
                });
            }).catch(function (e) { mod.commentsError(e && e.message); });
        };

        // Build 475: "Als Vorlage uebernehmen" nur anbieten, wenn das Recht
        // templates.edit vorliegt (das Speichern der Vorlage erfordert es
        // ohnehin). Ohne das Recht bleibt der Knopf aus -> das Modul rendert ihn
        // dann gar nicht (Callback fehlt).
        var canEditTemplates = hasCap(state.capabilities, 'templates.edit');
        var onTransfer = canEditTemplates
            ? function (uid, rid) {
                var url = '/api/report/as-template-draft?subject_id='
                    + encodeURIComponent(uid) + '&report_id='
                    + encodeURIComponent(rid);
                fetchJson(url).then(function (res) {
                    if (!res || !res.ok || !res.draft) {
                        throw new Error('Der Server lieferte keinen Entwurf.');
                    }
                    // Entwurf fuer die naechste Sicht hinterlegen und in die
                    // Dokumentvorlagen wechseln (dort sichten + speichern).
                    state.pendingTemplateDraft = {
                        draft: res.draft,
                        findings: res.findings || [],
                        warnings: res.warnings || []
                    };
                    selectView('doctemplates');
                }).catch(function (e) {
                    // Kein stiller Fehlpfad (Grundregel 1): Fehler im Lektorat
                    // sichtbar machen und den Knopf wieder aktivieren.
                    mod.transferError(e && e.message);
                });
            }
            : null;

        fetchJson('/api/reports').then(function (data) {
            cleanupView();
            mod.renderLectorate(mainEl, data, {
                status: 'submitted',
                // Bei Auswahl eines Berichts die zugrunde liegenden Belege
                // (SF-2) UND die Kommentare (SF-3) laden. Fehler werden im
                // jeweiligen Panel sichtbar gemacht (Grundregel 1).
                onSelect: function (uid, rid) {
                    log('Lektorat: Bericht gewaehlt', uid, rid);
                    fetchJson(mod.annotationsUrl(uid, rid))
                        .then(function (ad) { mod.renderAnnotations(ad); })
                        .catch(function (e) {
                            mod.annotationsError(e && e.message);
                        });
                    reloadComments(uid, rid);
                },
                // Build 475: Uebernahme in eine Dokumentvorlage (nur mit Recht).
                onTransferToTemplate: onTransfer
            });
            log('Lektorat gerendert:', data && data.count, 'Berichte');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Lektorat konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadApproval: CHEF-FREIGABE (W5, Build 416, Slice 1). Laedt die
    // Berichtsliste und rendert die Freigabe-Sicht: Auswahl + read-only
    // Berichtstext (SF-1) + Aktionen (Siegel pruefen / freigeben+versiegeln /
    // zurueckweisen). Schreibaktionen laufen ueber postJson (X-AIW-Token); die
    // Freigabe ist UNWIDERRUFLICH -> Rueckfrage vor dem Absenden. Nach jeder
    // Aktion wird neu geladen (kein optimistisches UI, Grundregel 1). Belege
    // (SF-2), Kommentare (SF-3) und Ergebnis-Mitpruefen folgen in den Slices.
    function loadApproval(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitApproval : null;
        if (!mod) {
            renderError(mainEl, 'Chef-Freigabe-Modul nicht geladen.');
            return;
        }
        // Freigeben erfordert reports.approve mit Scope 'alle' (Server erzwingt
        // es; das UI zeigt die Freigabe-Knoepfe nur dann).
        var canApprove = !!(state.capabilities
            && state.capabilities['reports.approve'] === 'alle');

        // reloadResults (Build 418/419): Ergebnis (read-only) rendern und -
        // bei results.edit - das append-only Bewertungs-Formular aus dem
        // Katalog aufbauen. Nach JEDER Bewertung erneut aufgerufen (kein
        // optimistisches UI: erst der bestaetigte Stand, Grundregel 1).
        var reloadResults = function (uid) {
            fetchJson(mod.resultsUrl(uid)).then(function (rd) {
                mod.renderResults(rd);
                if (rd && rd.can_edit) {
                    fetchJson('/api/results/catalog').then(function (cat) {
                        mod.renderAssessForm(cat, {
                            subjectId: uid,
                            onAssess: function (body) {
                                postJson('/api/results/assess', body)
                                    .then(function () { reloadResults(uid); })
                                    .catch(function (e) {
                                        mod.assessError(e && e.message);
                                    });
                            }
                        });
                    }).catch(function (e) {
                        log('Katalog nicht ladbar', e && e.message);
                    });
                }
            }).catch(function (e) { mod.resultsError(e && e.message); });
        };

        var render = function () {
            fetchJson('/api/reports').then(function (data) {
                cleanupView();
                mod.renderApproval(mainEl, data, {
                    status: 'submitted',
                    canApprove: canApprove,
                    // Bei Auswahl eines Berichts die Belege (SF-2) UND die
                    // Kommentare (SF-3, read-only) laden, damit die Chefin die
                    // Aussagen vor der Freigabe am Beleg verifizieren kann.
                    onSelect: function (uid, rid) {
                        fetchJson(mod.annotationsUrl(uid, rid))
                            .then(function (ad) { mod.renderAnnotations(ad); })
                            .catch(function (e) {
                                mod.annotationsError(e && e.message);
                            });
                        fetchJson(mod.commentsUrl(uid, rid))
                            .then(function (cd) { mod.renderComments(cd); })
                            .catch(function (e) {
                                mod.commentsError(e && e.message);
                            });
                        // Ermittlungsergebnis (read-only) + ggf. Bewertungs-
                        // Formular (results.edit). Fehlt results.view, meldet
                        // der Server 403 -> im Panel sichtbar (Grundregel 1).
                        reloadResults(uid);
                    },
                    onVerify: function (uid, rid) {
                        fetchJson('/api/report/verify?subject_id=' + uid
                                  + '&report_id=' + rid)
                            .then(function (v) { mod.renderVerify(v); })
                            .catch(function (e) {
                                mod.verifyError(e && e.message);
                            });
                    },
                    onApprove: function (body) {
                        if (typeof window !== 'undefined' && window.confirm
                            && !window.confirm('Bericht endgueltig freigeben '
                               + 'und versiegeln? Das ist unwiderruflich.')) {
                            return;
                        }
                        postJson('/api/report/approve', body)
                            .then(function () { render(); })
                            .catch(function (e) {
                                if (typeof window !== 'undefined'
                                    && window.alert) {
                                    window.alert('Freigabe fehlgeschlagen: '
                                        + (e && e.message));
                                }
                            });
                    },
                    onReturn: function (body) {
                        if (typeof window !== 'undefined' && window.confirm
                            && !window.confirm('Bericht zur Nachbesserung an '
                               + 'den Entwurf zurueckweisen?')) {
                            return;
                        }
                        postJson('/api/report/return', body)
                            .then(function () { render(); })
                            .catch(function (e) {
                                if (typeof window !== 'undefined'
                                    && window.alert) {
                                    window.alert('Rueckweisung fehlgeschlagen: '
                                        + (e && e.message));
                                }
                            });
                    }
                });
                log('Chef-Freigabe gerendert:', data && data.count, 'Berichte');
            }).catch(function (err) {
                cleanupView();
                renderError(mainEl,
                    'Chef-Freigabe konnte nicht geladen werden: '
                    + err.message);
            });
        };
        render();
    }

    // loadTemplates: PLATZHALTER & QUERIES (W2, Build 423). Laedt die Liste der
    // Platzhalter-Queries und rendert die Autoren-Maske. Zwei Aktionen:
    //   - Dry-Run: POST /api/templates/query/dryrun (SCHREIBFREI) -> zeigt
    //     Validierung + fdb-Beispielwert, OHNE etwas zu speichern.
    //   - Speichern: POST /api/templates/query (auditiert, TemplatesWriter) ->
    //     nach Erfolg wird die LISTE neu geladen (kein optimistisches UI:
    //     erst der bestaetigte Stand, Grundregel 1).
    function loadTemplates(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitTemplates : null;
        if (!mod) {
            renderError(mainEl, 'Platzhalter/Query-Modul nicht geladen.');
            return;
        }
        // Build 490 (Platzhalter-Neuordnung): neue Routen aus Build 489.
        fetchJson('/api/templates/placeholders').then(function (data) {
            cleanupView();
            mod.renderTemplates(mainEl, data, {
                onDryRun: function (payload) {
                    postJson('/api/templates/placeholder/dryrun', payload)
                        .then(function (res) { mod.renderDryRun(res); })
                        .catch(function (e) { mod.dryRunError(e && e.message); });
                },
                onSave: function (payload) {
                    postJson('/api/templates/placeholder', payload)
                        .then(function (res) {
                            mod.saved(res);
                            // Liste neu laden, damit ein NEUER Eintrag sofort
                            // erscheint bzw. eine Aenderung sichtbar wird.
                            loadTemplates(mainEl);
                        })
                        .catch(function (e) { mod.saveError(e && e.message); });
                }
            });
            log('Platzhalter/Queries gerendert:', data && data.count);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Platzhalter & Queries konnten nicht geladen werden: '
                + err.message);
        });
    }

    // loadDocTemplates: DOKUMENTVORLAGEN (W3, Build 425). Laedt die Vorlagen-
    // Liste und rendert die Autoren-Maske. Zwei Aktionen:
    //   - Struktur-Vorschau: POST /api/templates/document/dryrun (SCHREIBFREI).
    //   - Speichern: POST /api/templates/document (auditiert) -> nach Erfolg
    //     wird die LISTE neu geladen (kein optimistisches UI, Grundregel 1).
    function loadDocTemplates(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitDocTemplates : null;
        if (!mod) {
            renderError(mainEl, 'Dokumentvorlagen-Modul nicht geladen.');
            return;
        }
        // Build 475: einen aus dem Lektorat uebergebenen Vorlagen-Entwurf
        // EINMALIG konsumieren. Sofort aus dem State loeschen, damit ein spaeter
        // Neu-Laden (z.B. nach dem Speichern) den Entwurf NICHT erneut anwendet.
        var pending = state.pendingTemplateDraft;
        state.pendingTemplateDraft = null;

        fetchJson('/api/templates/documents').then(function (data) {
            cleanupView();
            mod.renderDocTemplates(mainEl, data, {
                onDryRun: function (payload) {
                    postJson('/api/templates/document/dryrun', payload)
                        .then(function (res) { mod.renderDryRun(res); })
                        .catch(function (e) { mod.dryRunError(e && e.message); });
                },
                onSave: function (payload) {
                    postJson('/api/templates/document', payload)
                        .then(function (res) {
                            mod.saved(res);
                            loadDocTemplates(mainEl);
                        })
                        .catch(function (e) { mod.saveError(e && e.message); });
                },
                // Build 475: Entwurf aus Bericht (oder null im Normalfall).
                initialDraft: pending ? pending.draft : null,
                initialFindings: pending ? pending.findings : null,
                initialWarnings: pending ? pending.warnings : null
            });
            log('Dokumentvorlagen gerendert:', data && data.count);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Dokumentvorlagen konnten nicht geladen werden: '
                + err.message);
        });
    }

    // loadModules: BAUSTEIN-MODULE (W1, Build 427). Laedt die Baustein-Liste und
    // rendert die Autoren-Maske. Zwei Aktionen:
    //   - Vorschau: POST /api/templates/module/dryrun (SCHREIBFREI).
    //   - Speichern: POST /api/templates/module (auditiert) -> nach Erfolg wird
    //     die LISTE neu geladen (kein optimistisches UI, Grundregel 1).
    function loadModules(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitModules : null;
        if (!mod) {
            renderError(mainEl, 'Baustein-Modul-Modul nicht geladen.');
            return;
        }
        // Build 654 (Ticket 4b032177): Die Platzhalter-Tabelle braucht zwei
        // KATALOGE - die bekannten Platzhalter und die benannten
        // Formatregeln. Beide sind schreibfrei.
        //
        // WARUM SIE DEN AUFBAU NICHT AUFHALTEN DUERFEN: die Sicht ist ohne
        // sie voll bedienbar; nur die Abgleichspruefungen (V2/V3/V5) fallen
        // dann weg, und die Tabelle SAGT das auch. Ein gescheiterter
        // Katalogabruf darf deshalb nicht die ganze Sicht kosten - deshalb
        // faengt jeder der beiden seinen Fehler selbst ab und liefert null.
        // Grundregel 1 bleibt gewahrt, weil 'null' in der Tabelle als
        // ausdruecklicher Hinweis erscheint und nicht als leere Spalte.
        function _katalog(pfad, name) {
            return fetchJson(pfad).catch(function (e) {
                log('Katalog ' + name + ' nicht ladbar:', e && e.message);
                return null;
            });
        }
        Promise.all([
            fetchJson('/api/templates/modules'),
            _katalog('/api/templates/placeholders', 'Platzhalter'),
            _katalog('/api/validation/rules', 'Formatregeln')
        ]).then(function (erg) {
            var data = erg[0];
            var phData = erg[1];
            var regelData = erg[2];
            cleanupView();
            mod.renderModules(mainEl, data, {
                placeholders: (phData && phData.placeholders)
                    ? phData.placeholders : null,
                validationRules: (regelData && regelData.rules)
                    ? regelData.rules : null,
                onDryRun: function (payload) {
                    postJson('/api/templates/module/dryrun', payload)
                        .then(function (res) { mod.renderDryRun(res); })
                        .catch(function (e) { mod.dryRunError(e && e.message); });
                },
                onSave: function (payload) {
                    postJson('/api/templates/module', payload)
                        .then(function (res) {
                            mod.saved(res);
                            loadModules(mainEl);
                        })
                        .catch(function (e) { mod.saveError(e && e.message); });
                }
            });
            log('Baustein-Module gerendert:', data && data.count);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Baustein-Module konnten nicht geladen werden: '
                + err.message);
        });
    }

    // =========================================================================
    // Build 512 (AP-2B/B1): AKTEN-EXPORT der aktiven Sicht.
    //
    // Der Knopf ist bewusst EIN Knopf in der Kopfzeile und nicht 29 Knoepfe in
    // 29 Sichten: er gehoert zur Shell, weil er fuer JEDE exportierbare Sicht
    // dasselbe tut. So kann eine kuenftige Sicht ihn auch nicht vergessen.
    //
    // Die Liste unten spiegelt management/export/view_export_catalog.py. Sie
    // ist bewusst KEINE zweite Wahrheitsquelle fuer die Rechte: der Server
    // prueft ohnehin (der Export erbt die Rechtepruefung der Sicht). Sie
    // steuert NUR, ob der Knopf ANGEBOTEN wird — ein Knopf, der verlaesslich
    // 404 liefert, waere schlechter als kein Knopf. Faellt die Liste einmal
    // auseinander, ist der schlimmste Fall eine 404-Seite, kein Datenverlust.
    var EXPORTABLE_VIEWS = {
        dashboard: 1, calendar: 1, assignment: 1, cases: 1, mentoring: 1,
        reports: 1, templates: 1, doctemplates: 1, modules: 1, results: 1,
        stats: 1, planung: 1, annostats: 1, workload: 1, capacity: 1,
        support: 1, mycases: 1, myhistory: 1, policy: 1, integrity: 1,
        audit: 1, promotion: 1, releases: 1, onboarding: 1, personnel: 1,
        crossref: 1, crossfindings: 1, alias: 1, merge: 1,
        // Build 574: der vollstaendige Fallbestand an seinem neuen Ort.
        faelle: 1,
        // Build 559: die Eingangsdaten der Kapazitaetsrechnung. Eigener
        // Export neben 'capacity' (dort steht das Ergebnis, hier die
        // Grundlage) — s. view_export_catalog.py.
        capacity_pflege: 1,
        // Build 516: die Eskalationsliste ist ein Beleg fuer die Leitung
        // ("dies lag zu diesem Zeitpunkt an") und gehoert damit in die Akte.
        // Sie kennt KEINEN Filter — es gibt entsprechend auch keinen Zweig in
        // exportParams; der Export bildet zwangslaeufig denselben Ausschnitt
        // ab wie die Sicht.
        escalation: 1,
        // Build 519: die Arbeitsschlange belegt, was zu einem Zeitpunkt
        // anstand — ein Beleg fuer die Leitung. Sie kennt keinen Filter
        // (der Umfang kommt aus dem Recht), also braucht sie auch keinen
        // exportParams-Zweig; der Export bildet zwangslaeufig denselben
        // Ausschnitt ab wie die Sicht.
        nextactions: 1,
        // Build 520: das Uebergabe-Protokoll ist ein Revisionsbeleg. Es KENNT
        // einen Filter (subject_id) — der Export bekommt ihn ueber
        // exportParams mit, sonst zeigte das Dokument den ganzen Bestand,
        // waehrend die Sicht auf einen Fall eingeschraenkt ist.
        handover: 1,
        // Build 521: die Fristenuebersicht ist ein Governance-Beleg ('zu
        // diesem Zeitpunkt standen N Faelle ueber der Frist'). Kein Filter,
        // also kein exportParams-Zweig. Der Loeschvorbehalt faehrt ueber
        // 'deletes_nothing' in das Dokument mit.
        retention: 1,
        // Build 525: die Fristenliste ist ein Governance-/Leitungsbeleg ('zu
        // diesem Zeitpunkt standen N Fristen so'). Sie KENNT einen Parameter
        // (vorwarn_tage) — er geht ueber exportParams mit, sonst zeigte das
        // Dokument eine andere Vorwarnschwelle als die Sicht, und die Schwelle
        // entscheidet ueber die Ampelfarbe.
        limitation: 1,
        // Build 539: die Matrix ist ein LEITUNGSBELEG ('zu diesem Zeitpunkt
        // standen N Faelle im Feld "dringend bei duenner Erkenntnislage"'),
        // und sie kennt einen Parameter (fristen) — er geht ueber exportParams
        // mit. Ohne ihn zeigte das Dokument womoeglich Fristbeitraege, die die
        // Sicht gar nicht geladen hatte, oder umgekehrt; die Zahlen der
        // X-Achse waeren dann andere als die auf dem Bildschirm.
        matrix: 1,
        // Build 543: die QS-Stichprobe ist ein Governance-Beleg ('zu diesem
        // Zeitpunkt war dies gezogen und dies geprueft'). Sie kennt keinen
        // Filter; der Substanz-Umfang der KENNZAHLEN ist kein Parameter von
        // /api/qs und geht deshalb nicht mit — das Dokument bildet die
        // STICHPROBE ab, nicht die Kennzahlen.
        qs: 1
    };

    // exportParams: die Sicht-Parameter, die der Export MITBEKOMMEN muss, damit
    // das Dokument genau den Ausschnitt abbildet, den die Ermittlerin vor sich
    // hat. Ein Export des GANZEN Bestands, wo die Sicht gefiltert ist, waere
    // ein irrefuehrender Beleg. REIN (kein DOM) -> vitest-pruefbar.
    function exportParams(viewId, st) {
        st = st || {};
        var p = {};
        // Build 520: der Fall-Ausschnitt des Uebergabe-Protokolls.
        if (viewId === 'handover') {
            if (st.hvSubject) { p.subject_id = st.hvSubject; }
        }
        if (viewId === 'alias') {
            if (st.aliasQuery) {
                p[/^\d+$/.test(st.aliasQuery) ? 'subject_id' : 'q'] =
                    st.aliasQuery;
            }
            if (st.aliasInclRetracted) { p.include_retracted = '1'; }
        } else if (viewId === 'merge') {
            if (st.mergeQuery && /^\d+$/.test(st.mergeQuery)) {
                p.subject_id = st.mergeQuery;
            }
            if (st.mergeInclSplit) { p.include_split = '1'; }
        } else if (viewId === 'crossfindings') {
            if (st.cfOnlyOpen) { p.only_open = '1'; }
            if (st.cfOnlyUnack) { p.only_unacknowledged = '1'; }
        } else if (viewId === 'onboarding') {
            if (st.onbPerson != null) { p.person_id = String(st.onbPerson); }
            if (st.onbKind) { p.kind = st.onbKind; }
        } else if (viewId === 'capacity') {
            if (st.capacityPeriod && st.capacityPeriod.start) {
                p.start = st.capacityPeriod.start;
            }
            if (st.capacityPeriod && st.capacityPeriod.end) {
                p.end = st.capacityPeriod.end;
            }
        } else if (viewId === 'limitation') {
            // Build 525: die Vorwarnschwelle entscheidet ueber die
            // Ampelfarbe. Fehlte sie im Export, zeigte die Aktenfassung
            // andere Farben als die Sicht, aus der sie erzeugt wurde — ein
            // irrefuehrender Beleg.
            if (st.limitationVorwarn) {
                p.vorwarn_tage = String(st.limitationVorwarn);
            }
        } else if (viewId === 'matrix') {
            // Build 539: der Fristen-Umfang. Er wird IMMER mitgegeben, auch
            // wenn er false ist — anders als bei den uebrigen Sichten, wo ein
            // fehlender Parameter 'Vorgabe' bedeutet. Grund: die Vorgabe des
            // ENDPUNKTS ist 'mit Fristen', die der SICHT ist 'ohne'. Liesse man
            // den Parameter weg, exportierte die Aktenfassung eine ANDERE
            // X-Achse als die, aus der sie erzeugt wurde.
            p.fristen = st.matrixFristen ? '1' : '0';
        }
        return p;
    }

    // exportUrl: /api/view/export mit view + Sicht-Parametern. REIN.
    function exportUrl(viewId, st) {
        var parts = ['view=' + encodeURIComponent(viewId)];
        var p = exportParams(viewId, st);
        Object.keys(p).forEach(function (k) {
            parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(p[k]));
        });
        return '/api/view/export?' + parts.join('&');
    }

    function isExportable(viewId) {
        return EXPORTABLE_VIEWS[viewId] === 1;
    }

    // refreshExportButton: blendet den Knopf je nach aktiver Sicht ein/aus und
    // haelt sein Ziel aktuell. Wird bei JEDEM Sichtwechsel gerufen.
    function refreshExportButton() {
        var btn = document.getElementById('aiw-export-btn');
        if (!btn) { return; }
        // Den href zusaetzlich BEIM KLICK neu berechnen: mehrere Sichten
        // aendern ihren Filter, ohne selectView zu rufen (z. B. der
        // 'nur offene'-Umschalter der Querfunde). Ohne das truege der Knopf
        // einen veralteten Ausschnitt — und ein Export, der einen ANDEREN
        // Ausschnitt zeigt als die Sicht, waere ein irrefuehrender Beleg.
        if (!btn.getAttribute('data-wired')) {
            btn.setAttribute('data-wired', '1');
            btn.addEventListener('click', function () {
                if (state.activeId && isExportable(state.activeId)) {
                    btn.setAttribute('href', exportUrl(state.activeId, state));
                }
            });
        }
        var vid = state.activeId;
        if (!vid || !isExportable(vid)) {
            btn.style.display = 'none';
            btn.removeAttribute('href');
            return;
        }
        btn.style.display = '';
        btn.setAttribute('href', exportUrl(vid, state));
        btn.setAttribute('title', 'Druckbare Aktenfassung dieser Sicht '
            + '(öffnet in einem neuen Tab)');
    }

    // selectView: aktive Sicht setzen, Nav neu markieren, Inhalt dispatchen.
    // Build 349: 'dashboard' -> Overview; 'integrity' -> Integritaets-Sicht;
    // sonst Platzhalter (weitere Sichten folgen).
    // sichtNachOben: die neue Sicht beginnt bei ihrer ersten Zeile.
    //
    // Build 566 (Befund mc): vorher teilten Leiste und Sicht EINE
    // Bildlaufflaeche - die des Dokuments. Wer einen Navigationseintrag
    // unterhalb des Sichtrands anklickte, schob damit auch die neue Sicht
    // nach oben aus dem Bild; sie erschien "unvollstaendig", obwohl sie
    // vollstaendig da war. Das CSS trennt die Flaechen jetzt; DIESE Zeile
    // sorgt dafuer, dass die Sicht auch beim Wechsel oben anfaengt - das
    // ergibt sich NICHT von selbst, weil der Bildlaufstand eines Elements
    // erhalten bleibt, wenn man nur seinen Inhalt austauscht.
    //
    // window.scrollTo zusaetzlich: sollte das Dokument doch einmal einen
    // Bildlauf haben (sehr schmales Fenster, oder eine aeltere cockpit.css
    // im Cache des Browsers), waere sonst nur die halbe Wirkung da.
    function sichtNachOben(mainEl) {
        if (mainEl && typeof mainEl.scrollTop === 'number') {
            mainEl.scrollTop = 0;
        }
        if (typeof window !== 'undefined'
                && typeof window.scrollTo === 'function') {
            window.scrollTo(0, 0);
        }
    }

    // navEintragZeigen: den aktiven Eintrag in der Leiste sichtbar halten.
    //
    // Die Kehrseite der eigenen Bildlaufflaeche: buildNav baut die Leiste bei
    // JEDEM Sichtwechsel neu auf, und eine neu aufgebaute Leiste steht wieder
    // ganz oben. Wer einen Eintrag weit unten waehlt, saehe danach seine
    // eigene Auswahl nicht mehr. scrollIntoView({block:'nearest'}) bewegt nur
    // dann, wenn der Eintrag tatsaechlich ausserhalb liegt - ein Eintrag im
    // sichtbaren Bereich bleibt, wo er ist, und die Leiste zappelt nicht.
    function navEintragZeigen(navEl) {
        if (!navEl || typeof navEl.querySelector !== 'function') { return; }
        var aktiv = navEl.querySelector('.aiw-navitem.active');
        if (aktiv && typeof aktiv.scrollIntoView === 'function') {
            try {
                aktiv.scrollIntoView({ block: 'nearest' });
            } catch (e) {
                // Aeltere Umgebungen kennen die Optionen nicht; ein Sprung
                // ist besser als eine Ausnahme mitten im Sichtwechsel.
                aktiv.scrollIntoView();
            }
        }
    }

    // navLeisteZeichnen: Suchfeld und Eintragsliste in EINEM Zug (Build 569).
    //
    // Reihenfolge der Schritte ist bedeutsam:
    //   1) navViewsAlle  — nach Vorliebe geordnet, nach RECHT gefiltert,
    //                      gruppenrein, MIT den ausgeblendeten.
    //   2) navSuche      — filtert nur noch innerhalb dieser Liste. Der
    //                      VIEW_CATALOG wird hier NIE angefasst; sonst
    //                      verriete das Suchfeld, welche Sichten es gibt,
    //                      fuer die einem das Recht fehlt.
    //   3) Ohne Suche fallen die ausgeblendeten heraus — bis auf die GERADE
    //      AKTIVE. Sonst zeigte die Leiste eine Sicht nicht an, die im
    //      Hauptfenster offen steht, und behauptete damit stillschweigend,
    //      es gebe sie nicht.
    function navLeisteZeichnen(navEl) {
        navEl = navEl || document.getElementById('aiw-nav');
        if (!navEl) { return; }
        var liste = navGeruest(navEl);
        var alle = navViewsAlle(state.capabilities, state.viewPrefs);
        var frage = state.navSuche || '';
        var aktiv = frage.trim() !== '';
        var gezeigt;
        if (aktiv) {
            gezeigt = navSuche(alle, frage);
        } else {
            gezeigt = alle.filter(function (v) {
                return v.versteckt !== true || v.id === state.activeId;
            });
        }
        var info = '';
        if (aktiv) {
            var vt = gezeigt.filter(function (v) {
                return v.versteckt === true;
            }).length;
            info = gezeigt.length + ' von ' + alle.length
                + (gezeigt.length === 1 ? ' Sicht' : ' Sichten')
                + (vt ? (', davon ' + vt + ' ausgeblendet') : '');
        }
        buildNavSuche(navEl, frage, function (wert) {
            state.navSuche = wert;
            navLeisteZeichnen(navEl);
        }, info);
        buildNav(liste, gezeigt, state.capabilities, state.activeId,
                 selectView, aktiv ? 0 : hiddenCount(state.capabilities,
                                                     state.viewPrefs),
                 { aktiv: aktiv, gesamt: alle.length });
    }

    function selectView(viewId) {
        // Build 546 (AP-3G, mc 2026-07-26): WARNUNG BEIM VERLASSEN MIT
        // UNGESPEICHERTEN AENDERUNGEN.
        //
        // Die Frage steht VOR cleanupView(), denn cleanupView() setzt das
        // Merkmal zurueck — danach waere nicht mehr feststellbar, dass etwas
        // offen war. Wer abbricht, bleibt auf der Sicht; ihr Zustand ist
        // unberuehrt, weil noch nichts abgebaut wurde.
        //
        // Der Zwischenstand liegt zusaetzlich im localStorage (Muster Build
        // 487/488), er ginge also selbst dann nicht verloren, wenn jemand die
        // Frage uebersieht. Die Warnung ist trotzdem da: einen Verlust
        // nachtraeglich reparieren zu koennen ersetzt nicht den Hinweis, dass
        // gerade etwas offen ist.
        if (state.activeId === 'viewprefs' && viewId !== 'viewprefs') {
            var vpm = (typeof window !== 'undefined')
                ? window.AIWCockpitViewPrefs : null;
            if (vpm && typeof vpm.hatUngespeichertes === 'function'
                    && vpm.hatUngespeichertes()
                    && typeof window.confirm === 'function') {
                var weiter = window.confirm(
                    'Die Ansichtseinstellung ist nicht gespeichert. '
                    + 'Bereich trotzdem verlassen?\n\n'
                    + 'Der Zwischenstand bleibt erhalten und wird beim '
                    + 'nächsten Aufruf wiederhergestellt.');
                if (!weiter) {
                    log('Sichtwechsel abgebrochen (ungespeicherte Ansicht)');
                    return;
                }
            }
        }
        state.activeId = viewId;
        // Build 590 (Baustelle H / H3): den Hilfemodus beim Sichtwechsel
        // verlassen und dem Modul die neue Sicht nennen. Die Hilfe-Schluessel
        // sind sichtbezogen; ein ueber den Wechsel hinweg bestehender Modus
        // zeigte auf der neuen Sicht lauter abgedunkelte Elemente ohne
        // erkennbaren Grund. Defensiv: fehlt das Modul, laeuft alles weiter.
        var hilfeModul = (typeof window !== 'undefined')
            ? window.AIWCockpitHilfe : null;
        if (hilfeModul && typeof hilfeModul.sichtGewechselt === 'function') {
            hilfeModul.sichtGewechselt(viewId);
        }
        cleanupView();  // beim Sichtwechsel offene Tabelle/Diagramm abbauen
        var navEl = document.getElementById('aiw-nav');
        var mainEl = document.getElementById('aiw-main');
        navLeisteZeichnen(navEl);
        sichtNachOben(mainEl);
        navEintragZeigen(navEl);
        refreshExportButton();
        if (viewId === 'dashboard') {
            loadOverview(mainEl);
        } else if (viewId === 'viewprefs') {
            loadViewPrefs(mainEl);
        } else if (viewId === 'integrity') {
            loadIntegrity(mainEl);
        } else if (viewId === 'audit') {
            loadAudit(mainEl, state.auditFilters, state.auditOffset);
        } else if (viewId === 'promotion') {
            loadPromotion(mainEl);
        } else if (viewId === 'releases') {
            loadReleases(mainEl);
        } else if (viewId === 'onboarding') {
            loadOnboarding(mainEl, state.onbPerson, state.onbKind);
        } else if (viewId === 'personnel') {
            loadPersonnel(mainEl);
        } else if (viewId === 'capacity_pflege') {
            loadCapacityPflege(mainEl);
        } else if (viewId === 'crossref') {
            loadCrossref(mainEl);
        } else if (viewId === 'crossfindings') {
            loadCrossfindings(mainEl, state.cfOnlyOpen === true);
        } else if (viewId === 'alias') {
            loadAlias(mainEl);
        } else if (viewId === 'merge') {
            loadMerge(mainEl);
        } else if (viewId === 'workload') {
            loadWorkload(mainEl);
        } else if (viewId === 'escalation') {
            loadEscalation(mainEl);
        } else if (viewId === 'nextactions') {
            loadNextActions(mainEl);
        } else if (viewId === 'handover') {
            loadHandover(mainEl);
        } else if (viewId === 'retention') {
            loadRetention(mainEl);
        } else if (viewId === 'search') {
            // Build 563 (AP-3E): die Volltextsuche. Sie SUCHT BEIM OEFFNEN
            // NICHT — die Maske erscheint leer. Ein automatischer Lauf
            // erzeugte einen Beleg ohne menschliche Handlung.
            loadSearch(mainEl);
        } else if (viewId === 'capacity') {
            loadCapacity(mainEl);
        } else if (viewId === 'policy') {
            loadPolicy(mainEl);
        } else if (viewId === 'mycases') {
            loadMyCases(mainEl);
        } else if (viewId === 'myhistory') {
            loadMyHistory(mainEl);
        } else if (viewId === 'support') {
            loadSupport(mainEl);
        } else if (viewId === 'mentoring') {
            loadMentoring(mainEl);
        } else if (viewId === 'notes') {
            loadNotes(mainEl);
        } else if (viewId === 'stats') {
            loadStats(mainEl);
        } else if (viewId === 'limitation') {
            // Build 525: die Fristensicht. Sie braucht keinen Vorlauf — die
            // Vorwarnschwelle kommt aus dem State (oder der Server-Vorgabe).
            loadLimitation(mainEl);
        } else if (viewId === 'qs') {
            // Build 543: QS & Metriken. Der Substanz-Umfang kommt aus dem
            // State; Vorgabe ist OHNE (Begruendung bei loadQs).
            loadQs(mainEl);
        } else if (viewId === 'matrix') {
            // Build 539: die Matrix. Der Fristen-Umfang kommt aus dem State;
            // Vorgabe ist OHNE Fristen (Begruendung bei loadMatrix).
            loadMatrix(mainEl);
        } else if (viewId === 'planung') {
            loadPlanung(mainEl);
        } else if (viewId === 'annostats') {
            loadAnnostats(mainEl);
        } else if (viewId === 'assignment') {
            loadAssignment(mainEl);
        } else if (viewId === 'faelle') {
            loadFaelle(mainEl);
        } else if (viewId === 'cases') {
            loadCases(mainEl);
        } else if (viewId === 'calendar') {
            loadCalendar(mainEl);
        } else if (viewId === 'results') {
            loadResultsView(mainEl);
        } else if (viewId === 'reports') {
            loadReports(mainEl);
        } else if (viewId === 'lectorate') {
            loadLectorate(mainEl);
        } else if (viewId === 'approval') {
            loadApproval(mainEl);
        } else if (viewId === 'templates') {
            loadTemplates(mainEl);
        } else if (viewId === 'doctemplates') {
            loadDocTemplates(mainEl);
        } else if (viewId === 'modules') {
            loadModules(mainEl);
        } else {
            renderPlaceholder(mainEl, viewById(viewId));
        }
    }

    // _moduleBusy (Build 479): Meldet ein Sicht-Modul einen aktuell geoeffneten
    // Bericht? Wird vom SSE-'changed'-Handler genutzt, um einen destruktiven
    // Reload der Lektorat-/Freigabe-Sicht zu unterdruecken, solange dort ein
    // Bericht in Sichtung ist (siehe Kopfkommentar Build 479). Defensiv: fehlt
    // das Modul oder die Methode, gilt "nicht beschaeftigt" -> bisheriges
    // Verhalten (Reload), damit ein fehlendes Skript nie einen Reload verschluckt.
    function _moduleBusy(moduleName) {
        var m = (typeof window !== 'undefined') ? window[moduleName] : null;
        return !!(m && typeof m.hasSelection === 'function' && m.hasSelection());
    }

    // startSse: Live-Aktualisierung. Server pollt die audit_log-Spitze; bei
    // 'changed' laedt der Client NUR die aktive Sicht neu (kein F5, §11.2/§11.1).
    // hello/keepalive sind reine Lebenszeichen. EventSource reconnectet selbst.
    function startSse() {
        if (typeof EventSource === 'undefined') {
            log('EventSource n/a — kein Live-Reload');
            return;
        }
        var es = new EventSource('/events');
        es.addEventListener('hello', function (e) { log('SSE hello', e.data); });
        es.addEventListener('keepalive', function () { /* Lebenszeichen */ });
        es.addEventListener('changed', function (e) {
            log('SSE changed', e.data);
            // Aktive Sicht neu laden (kein F5, §11.2/§11.1):
            if (state.activeId === 'dashboard') {
                loadOverview();
            } else if (state.activeId === 'faelle') {
                loadFaelle();
            } else if (state.activeId === 'integrity') {
                loadIntegrity();   // aktualisiert Sicht UND Banner
            } else if (state.activeId === 'audit') {
                // Neue Belege koennen dazugekommen sein -> Seite neu laden
                // (gleiche Filter/Offset aus dem State).
                loadAudit(undefined, state.auditFilters, state.auditOffset);
            } else if (state.activeId === 'promotion') {
                // Eine Entscheidung (auch durch eine andere Chefin) erzeugt einen
                // audit_log-Beleg; zudem misst die Sicht die Platte -> der
                // Kandidatenbestand kann kippen. Also neu laden.
                loadPromotion();
            } else if (state.activeId === 'releases') {
                // Eine Freigabe/ein Widerruf (auch durch eine andere Person)
                // erzeugt einen audit_log-Beleg -> Liste neu laden.
                loadReleases();
            } else if (state.activeId === 'onboarding') {
                // Nur neu laden, wenn bereits eine Person gewaehlt ist (sonst
                // steht die Auswahl und es gibt nichts zu aktualisieren).
                if (state.onbPerson != null) {
                    loadOnboarding(undefined, state.onbPerson, state.onbKind);
                }
            } else if (state.activeId === 'capacity_pflege') {
                // Kapazitaetsaenderungen (auch durch andere) erzeugen
                // audit_log-Belege -> die vier Listen neu laden. Der
                // Rechner laeuft dabei NICHT mit: die Pflegesicht holt
                // Stammdaten, nicht das Ergebnis.
                loadCapacityPflege();
            } else if (state.activeId === 'personnel') {
                // Personal-/Rollenaenderungen (auch durch andere) erzeugen
                // audit_log-Belege -> LISTE neu laden. Der AD-Abschnitt wird
                // dabei bewusst NICHT geladen (jeder Abruf waere eine
                // Live-LDAP-Anfrage; er bleibt Nutzerhandlung).
                loadPersonnel();
            } else if (state.activeId === 'crossref') {
                // Eine Anlage/Revision (auch durch eine andere Person) erzeugt
                // einen audit_log-Beleg -> Katalog neu laden.
                loadCrossref();
            } else if (state.activeId === 'merge') {
                // Build 510: Merge/Split laufen ueber den coordinator-
                // audit_log — der SSE-Strom feuert korrekt.
                loadMerge();
            } else if (state.activeId === 'alias') {
                // Build 505: Alias-Aenderungen laufen ueber den coordinator-
                // audit_log — der SSE-Strom feuert also korrekt (anders als bei
                // 'crossfindings', deren Substrat die forensic_api-Pipeline
                // schreibt). Such-/Filterzustand bleibt im State erhalten.
                loadAlias();
            } else if (state.activeId === 'workload') {
                loadWorkload();
            } else if (state.activeId === 'limitation') {
                // Ein neu aufgenommener Fall (CASE_CREATED) erzeugt einen
                // audit_log-Beleg und kann eine NEUE, moeglicherweise schon
                // knappe Frist in die Liste bringen -> neu messen. Die im
                // State gehaltene Vorwarnschwelle bleibt dabei erhalten.
                loadLimitation();
            } else if (state.activeId === 'qs') {
                // Build 543: eine neue Ziehung und jedes Pruefergebnis
                // erzeugen einen audit_log-Beleg; ausserdem aendern
                // Fallabschluesse die Grundgesamtheit und die Kennzahlen.
                // Der eingestellte Substanz-Umfang bleibt erhalten, sonst
                // laedt ein fremdes Ereignis ungefragt die teure Variante.
                loadQs();
            } else if (state.activeId === 'matrix') {
                // Build 539: fast jedes auditierte Ereignis kann die Rangfolge
                // veraendern — eine neue Bewertung hebt die Erkenntnislage,
                // eine Zuweisung nimmt den Beitrag 'unzugewiesen' weg, ein
                // neuer externer Vorgang kann ueberfaellig werden. Neu messen.
                // Der eingestellte Fristen-Umfang (state.matrixFristen) bleibt
                // erhalten, sonst laedt ein fremdes Ereignis ungefragt die
                // teure Variante nach.
                loadMatrix();
            } else if (state.activeId === 'retention') {
                // Ein Fall-Abschluss (status closed/approved) erzeugt einen
                // audit_log-Beleg und kann die Fristenlage aendern -> neu
                // messen. Kein Eingabezustand, der verloren gehen koennte.
                loadRetention();
            } else if (state.activeId === 'handover') {
                // Eine neue Zuweisung erzeugt genau den audit_log-Beleg, aus
                // dem dieses Protokoll besteht -> neu laden. Der eingestellte
                // Ausschnitt (state.hvSubject) bleibt erhalten, sonst wuerde
                // ein fremdes Ereignis die Untersuchung eines Falls abbrechen.
                loadHandover();
            } else if (state.activeId === 'nextactions') {
                // Die Arbeitsschlange leitet sich AUSSCHLIESSLICH aus dem
                // Fallzustand ab; genau dessen Aenderungen erzeugen die
                // audit_log-Belege, auf die die SSE triggert. Eine erledigte
                // Aufgabe darf nicht stehen bleiben. Die Sicht haelt keinen
                // Eingabezustand, den ein Reload verwerfen koennte.
                loadNextActions();
            } else if (state.activeId === 'escalation') {
                // Eskalationen leiten sich AUSSCHLIESSLICH aus dem Fallzustand
                // ab (Status, Zuweisung, letzte Aktivitaet). Genau diese
                // Aenderungen erzeugen coordinator-audit_log-Belege, auf die
                // die SSE triggert — ein Live-Reload ist hier also nicht nur
                // erlaubt, sondern noetig: eine Eskalation, die inzwischen
                // erledigt ist, darf nicht stehen bleiben. Die Sicht haelt
                // keinen Eingabezustand, den ein Reload verwerfen koennte.
                loadEscalation();
            } else if (state.activeId === 'capacity') {
                loadCapacity(undefined, state.capacityPeriod);
            } else if (state.activeId === 'policy') {
                loadPolicy();
            } else if (state.activeId === 'mycases') {
                loadMyCases();
            } else if (state.activeId === 'myhistory') {
                loadMyHistory();
            } else if (state.activeId === 'support') {
                loadSupport();
            } else if (state.activeId === 'mentoring') {
                loadMentoring();
            } else if (state.activeId === 'notes') {
                // Ein audit_log-Ereignis kann eine Aenderung an einer Notiz
                // durch eine Vertretung sein -> Board neu laden. Die Archiv-
                // Ansicht bleibt erhalten (state.notesArchived).
                loadNotes(undefined, { archived: state.notesArchived === true });
            } else if (state.activeId === 'stats') {
                loadStats();
            } else if (state.activeId === 'planung') {
                loadPlanung();
            } else if (state.activeId === 'annostats') {
                loadAnnostats();
            } else if (state.activeId === 'assignment') {
                loadAssignment();
            } else if (state.activeId === 'results') {
                // Eine Bewertung durch einen Ermittler (Nutzerinfo-Tab,
                // Build 390) erzeugt einen audit_log-Beleg -> die Abdeckung
                // aendert sich. Neu messen.
                loadResultsView();
            } else if (state.activeId === 'calendar') {
                // Ein audit_log-Ereignis kann ein Verschieben/Abschliessen
                // durch eine andere Person sein -> Faelligkeiten neu messen.
                loadCalendar(null, state.calYm);
            } else if (state.activeId === 'cases') {
                // Die Fall-Erkennung misst die PLATTE. Ein audit_log-Ereignis
                // (z. B. eine Aufnahme durch eine andere Chefin) veraendert die
                // Fallakte -> die Zustaende koennen kippen. Also neu messen.
                loadCases();
            } else if (state.activeId === 'reports') {
                loadReports();
            } else if (state.activeId === 'lectorate') {
                // Build 479: KEIN destruktiver Live-Reload, solange ein Bericht
                // geoeffnet ist. Belegte Ursache-Wirkung:
                //   Bericht oeffnen -> onSelect holt /api/report/annotations
                //   -> Server schreibt Chain-of-Custody-Beleg
                //      'report_annotations_viewed' in coordinator.db-audit_log
                //      (management_app.py:_audit_annotation_view; Grundregel 1)
                //   -> audit_tip_seq steigt -> SSE meldet ~2s spaeter 'changed'
                //      (management_handler.py:_handle_sse, poll=2.0s)
                //   -> loadLectorate() wuerde die Sicht neu aufbauen und die
                //      Auswahl + iframe-Vorschau verwerfen (der gemeldete Bug).
                // Ein Wieder-Auswaehlen wuerde erneut auditieren -> Endlosloop.
                // Die Berichtsliste aendert sich nur bei Einreichen/Freigeben
                // (selten). Ohne offene Auswahl laden wir wie bisher nach; bei
                // Sichtwechsel (cleanup) bzw. Rueckkehr laedt die Liste frisch.
                if (!_moduleBusy('AIWCockpitLectorate')) {
                    loadLectorate();
                } else {
                    log('SSE changed: Lektorat-Reload unterdrueckt '
                        + '(Bericht in Sichtung).');
                }
            } else if (state.activeId === 'approval') {
                // Build 479: identischer Schutz wie im Lektorat — auch die
                // Chef-Freigabe holt in onSelect /api/report/annotations und
                // wuerde sonst durch den eigenen Lesebeleg neu geladen.
                if (!_moduleBusy('AIWCockpitApproval')) {
                    loadApproval();
                } else {
                    log('SSE changed: Freigabe-Reload unterdrueckt '
                        + '(Bericht in Sichtung).');
                }
            }
            // BEWUSST KEIN Auto-Reload der Redaktions-Sichten 'templates'
            // (W2 Build 423), 'doctemplates' (W3 Build 425) und 'modules'
            // (W1 Build 427): Schreibvorgaenge auf templates.db landen in
            // templates_audit_log (eigene Tabelle), NICHT im coordinator.db-
            // audit_log, das die SSE beobachtet -> ein Upsert loest hier ohnehin
            // kein 'changed' aus. Wuerden wir dennoch neu laden, wuerde ein
            // unabhaengiges Ereignis die noch nicht gespeicherte Eingabe der
            // Autor:in verwerfen. Nach dem Speichern laden loadTemplates/
            // loadDocTemplates/loadModules die Liste selbst.
            // Banner global frisch halten, wenn die aktive Sicht nicht die
            // Integritaets-Sicht ist (dort geschieht es bereits oben).
            if (state.activeId !== 'integrity') {
                refreshBanner();
            }
        });
        es.onerror = function () {
            // Bei Reconnect/Serverneustart normal; kein harter Fehler.
            log('SSE onerror (Auto-Reconnect)');
        };
        state.sse = es;
        log('SSE gestartet');
    }

    function boot() {
        log('boot() Start');
        // Build 546 (AP-3G): erst die Identitaet, dann die Ansichtseinstellung.
        //
        // EIN FEHLSCHLAG BEIM ZWEITEN ABRUF DARF DEN START NICHT VERHINDERN,
        // aber er darf auch nicht wie 'nichts eingestellt' aussehen. Deshalb
        // faengt der catch den Fehler ab, merkt ihn in state.viewPrefsFehler
        // (die Einstellsicht zeigt ihn an) und laesst das Cockpit mit der
        // WERKSEINSTELLUNG hochkommen. Eine Oberflaeche, die wegen einer
        // Bedienvorliebe gar nicht startet, waere die schlechtere Antwort.
        fetchJson('/api/whoami').then(function (who) {
            log('whoami', who);
            state.capabilities = who.capabilities || {};
            // Eigene person_id (Build 415): erlaubt der Lektorat-Sicht, die
            // AUFLOESEN-Knoepfe nur an EIGENEN Kommentaren zu zeigen.
            state.personId = who.person_id;
            // Schreib-Token uebernehmen (nur ueber diesen authentifizierten
            // GET erhaeltlich; Voraussetzung fuer alle POSTs).
            state.writeToken = who.write_token || null;
            if (!state.writeToken) {
                log('WARNUNG: kein write_token in /api/whoami');
            }
            setWho(document.getElementById('aiw-who'),
                   who.display_name, who.system_username);

            return fetchJson('/api/viewprefs').then(function (vp) {
                uebernimmViewPrefs(vp);
                log('Ansichtseinstellung geladen:',
                    state.viewPrefs.length, 'Sichten,',
                    (state.viewPrefsWidgets || []).length, 'Kacheln');
            }).catch(function (err) {
                state.viewPrefs = [];
                state.viewPrefsFehler = err.message;
                // eslint-disable-next-line no-console
                console.warn('[AIW-Cockpit] Ansichtseinstellung nicht '
                    + 'ladbar — Werkseinstellung: ' + err.message);
            });
        }).then(function () {

            var views = navViews(state.capabilities, state.viewPrefs);
            state.activeId = firstViewId(views);
            // Erste Sicht ueber selectView anzeigen (laedt ggf. die Overview).
            if (state.activeId) {
                selectView(state.activeId);
            } else {
                navLeisteZeichnen(document.getElementById('aiw-nav'));
                renderPlaceholder(document.getElementById('aiw-main'), null);
            }

            // Ketten-Gesundheit global im Banner anzeigen (still, wenn keine
            // ops.view). Wenn 'integrity' die erste Sicht ist, hat selectView
            // den Banner bereits gesetzt -> Doppel-Fetch vermeiden.
            if (state.activeId !== 'integrity') {
                refreshBanner();
            }

            // Build 546 (AP-3G): dieselbe Warnung beim Schliessen/Neuladen
            // des Fensters. Der Browser zeigt seinen eigenen Text (der
            // Rueckgabewert wird seit langem ignoriert) — entscheidend ist,
            // DASS gefragt wird.
            window.addEventListener('beforeunload', function (e) {
                var vpm = window.AIWCockpitViewPrefs;
                if (state.activeId === 'viewprefs' && vpm
                        && typeof vpm.hatUngespeichertes === 'function'
                        && vpm.hatUngespeichertes()) {
                    e.preventDefault();
                    e.returnValue = '';
                    return '';
                }
                return undefined;
            });

            // Live-Reload aktivieren.
            startSse();

            // Kommandopalette (Strg-K, Build 457) initialisieren: sie holt die
            // Sichten stets frisch (rechte-gefiltert) und springt ueber
            // selectView. Entkoppelt -> die Palette kennt VIEW_CATALOG nicht.
            var pal = (typeof window !== 'undefined')
                ? window.AIWCockpitPalette : null;
            if (pal && typeof pal.init === 'function') {
                pal.init({
                    getViews: function () {
                        return visibleViews(state.capabilities);
                    },
                    onSelect: function (viewId) { selectView(viewId); },
                    // Fall-Suche (Build 459): read-only /api/search. Bei Fehler/
                    // 403 -> leere Liste (Palette bleibt fuer die Sicht-Suche
                    // nutzbar; kein harter Fehlpfad).
                    searchCases: function (q) {
                        return fetchJson('/api/search?q='
                                + encodeURIComponent(q) + '&limit=8')
                            .then(function (data) {
                                return (data && data.results) || [];
                            })
                            .catch(function () { return []; });
                    },
                    // Fall-Sprung: zur Uebersicht wechseln und die Zeile
                    // fokussieren (state.focusCaseId wird von loadOverview nach
                    // dem Rendern ausgewertet).
                    // Build 574: Ziel ist die Sicht 'faelle' und nicht mehr
                    // der Ueberblick. Dort steht die vollstaendige Tabelle;
                    // die Kompaktkachel des Ueberblicks zeigt nur noch drei
                    // Faelle, ein Sprung dorthin ginge meist ins Leere.
                    onSelectCase: function (subjectId) {
                        state.focusCaseId = subjectId;
                        selectView('faelle');
                    }
                });
            }

            // Build 590 (Baustelle H / H3): Hilfemodus initialisieren. Das
            // Modul bindet dabei Knopf und Tastatur (Shift+F1). Es kennt den
            // VIEW_CATALOG nicht — es bekommt die aktive Sicht ueber
            // sichtGewechselt() gesagt (Entkopplung wie bei der Palette).
            var hilfe = (typeof window !== 'undefined')
                ? window.AIWCockpitHilfe : null;
            if (hilfe && typeof hilfe.init === 'function') {
                hilfe.init({});
                if (typeof hilfe.sichtGewechselt === 'function') {
                    hilfe.sichtGewechselt(state.activeId);
                }
            }

            log('boot() fertig:', views.length, 'Sichten');
        }).catch(function (err) {
            // Kein stiller Fehlpfad: sichtbarer Hinweis + Console.
            // eslint-disable-next-line no-console
            console.error('[AIW-Cockpit] boot-Fehler:', err);
            var main = document.getElementById('aiw-main');
            if (main) {
                main.textContent = 'Fehler beim Laden der Identitaet: '
                    + err.message;
            }
        });
    }

    // Auto-Boot nur im echten Browser: window + document + fetch muessen da
    // sein. Unter Node/Vitest (JSDOM ohne fetch) wird NICHT gebootet — die
    // Unit-Tests rufen die (reinen/DOM-)Funktionen gezielt selbst auf. So
    // sprengt das fehlende fetch nicht den Modul-Eval.
    if (typeof window !== 'undefined' && typeof document !== 'undefined'
            && typeof fetch !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', boot);
        } else {
            boot();
        }
    }

    // =========================================================================
    // 5) UMD-artiger Ausgang: dieselbe API an window (Browser) UND
    //    module.exports (Node/Vitest). So testen die Unit-Tests den ECHTEN Code.
    // =========================================================================
    var API = {
        VIEW_CATALOG: VIEW_CATALOG,
        hasCap: hasCap,
        viewCaps: viewCaps,
        effectiveCap: effectiveCap,
        visibleViews: visibleViews,
        // Build 546 (AP-3G): reine Funktionen der Ansichtseinstellung.
        applyViewPrefs: applyViewPrefs,
        navViews: navViews,
        hiddenCount: hiddenCount,
        scopeTag: scopeTag,
        firstViewId: firstViewId,
        groupSequence: groupSequence,
        viewById: viewById,
        setWho: setWho,
        buildNav: buildNav,
        buildNavSuche: buildNavSuche,
        navGeruest: navGeruest,
        navGruppeUmschalten: navGruppeUmschalten,
        GROUP_ORDER: GROUP_ORDER,
        suchNormal: suchNormal,
        sichtSuchtext: sichtSuchtext,
        suchBegriffe: suchBegriffe,
        sichtPasst: sichtPasst,
        navSuche: navSuche,
        navLeisteZeichnen: navLeisteZeichnen,
        navViewsAlle: navViewsAlle,
        nachGruppenOrdnen: nachGruppenOrdnen,
        sichtNachOben: sichtNachOben,
        navEintragZeigen: navEintragZeigen,
        renderPlaceholder: renderPlaceholder,
        boot: boot,
        // Build 512 (AP-2B/B1): Akten-Export. Reine Funktionen -> vitest.
        isExportable: isExportable,
        exportParams: exportParams,
        exportUrl: exportUrl,
        EXPORTABLE_VIEWS: EXPORTABLE_VIEWS,
        // Build 657: der Lesepfad wird pruefbar. Er hat am 2026-08-02 die
        // Massnahme des Servers weggeworfen und nur die Zahl gezeigt - ein
        // Verhalten, das ohne Fall in der Suite wiederkommen kann.
        fetchJson: fetchJson
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpit = API; }
})();
