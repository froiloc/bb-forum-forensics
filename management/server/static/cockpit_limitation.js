// =============================================================================
// management/server/static/cockpit_limitation.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Fristen
// =============================================================================
// Zweck (AP-3A / Idee 32, Frontend zu Build 524):
//   Zeigt den Fristen-/Verjaehrungs-Monitor aus GET /api/limitation: je Fall
//   den belegten Fristbeginn (§ 78a StGB) und die rechnerische Frist nach
//   §§ 78 ff. StGB, mit Ampel.
//
// DIE WICHTIGSTE AUSSAGE DIESER DATEI:
//   DIESE SICHT STELLT KEINE VERJAEHRUNG FEST. Sie rechnet die UNUNTERBROCHENE
//   Frist. Unterbrechungen nach § 78c StGB (Bekanntgabe der
//   Verfahrenseinleitung, Beschlagnahme-/Durchsuchungsanordnung, Anklage) sind
//   dem Werkzeug NICHT bekannt und koennen die Frist neu in Gang gesetzt haben.
//   Das Wort 'verjaehrt' kommt in dieser Sicht deshalb NICHT vor — auch nicht
//   in der rotesten Zeile. Der Vorbehalt steht OBEN und nicht als Fussnote, und
//   die Sicht MELDET es, wenn das Backend die Zusicherung
//   ('stellt_keine_verjaehrung_fest') einmal nicht mittraegt: eine
//   Fristenliste, die als Feststellung missverstanden wird, ist die
//   folgenschwerste Fehldeutung, die dieses Werkzeug zulassen koennte.
//
// ZWEITE BESONDERHEIT — DIE SICHT DARF STUMM SEIN:
//   Solange der Verjaehrungs-Parametersatz nicht juristisch BESTAETIGT ist
//   (aussage_moeglich=false), zeigt die Sicht KEINE Ampel, sondern den GRUND.
//   Die Fallliste und die Datenlage bleiben dabei vollstaendig sichtbar — man
//   sieht also sofort, fuer wie viele Faelle ueberhaupt ein Tatzeitpunkt belegt
//   ist. Das ist nuetzlich und von der Rechtsfrage unabhaengig. Eine Sicht, die
//   in diesem Zustand einfach leer waere, haette die Datenlage verborgen; eine,
//   die trotzdem Ampeln zeigte, haette eine unbestaetigte Rechtsfolge
//   behauptet. Beides waere falsch.
//
// ACHT ZUSTAENDE (Spiegel cockpit.css .aiw-lim-*):
//   ueberschritten — rot     (Frist rechnerisch abgelaufen)
//   knapp          — orange  (unter der Vorwarnschwelle)
//   ohne_tatzeit   — violett (UNGEPRUEFT: kein Fristbeginn belegt)
//   ohne_anker     — violett (UNGEPRUEFT: Ersatzanker fuer diese Tatbestaende
//                             nicht zugelassen — Build 530)
//   ohne_fassung   — violett (UNGEPRUEFT: keine Fassung zur Tatzeit hinterlegt)
//   ruht           — blau    (§ 78b Abs. 1 Nr. 1 StGB, nicht berechenbar)
//   offen          — gruen   (Restlaufzeit ueber der Schwelle)
//   keine_aussage  — grau    (Parametersatz nicht bestaetigt)
//   'ohne_tatzeit' ist AUSDRUECKLICH NICHT gruen und nicht grau: der Fall ist
//   nicht unverdaechtig, sondern unbekannt. Eine eigene, auffaellige Farbe ist
//   hier kein Zierrat, sondern der Unterschied zwischen 'geprueft' und
//   'ungeprueft'.
//
// BUILD 530 — DIE GRUNDLAGE STEHT IN DER ZEILE, NICHT IN DER AMPEL:
//   Die Ampel sagt die RECHTSFOLGE. Zwei weitere, davon unabhaengige Angaben
//   sagen, worauf sie beruht:
//     feststellung — 'festgestellt' | 'vorlaeufig' | 'ohne'
//     anker_art    — 'aktivitaet' | 'registrierung' | 'anmeldung' | 'keine'
//   Sie bekommen eine EIGENE Spalte und eine eigene Auszeichnung statt weiterer
//   Ampelfarben. Grund: 'vorlaeufig' ist keine Art von Ampel, sondern eine
//   Eigenschaft der Grundlage — presst man beides in eine Farbskala, wird
//   'vorlaeufig ueberschritten' unsichtbar, und das ist die operativ
//   wichtigste Kombination (Frist rechnerisch abgelaufen, Datum nie geprueft).
//
//   HEUTE IST JEDE ZEILE 'vorlaeufig'. Das ist kein Anzeigefehler: eine von
//   einer Ermittlerin festgestellte Tatzeit gibt es in den Daten noch nicht.
//
// Datenform GET /api/limitation (ManagementApp._limitation):
//   { stichtag, vorwarn_tage, aussage_moeglich, verweigerungsgrund,
//     params_stand, params_bestaetigt, params_bestaetigt_von,
//     params_bestaetigt_am, vorgabe_tatbestaende[], vorbehalte[], hinweise[],
//     faelle_gesamt, zaehler{ampel:n}, datenlage{befund:n},
//     stellt_keine_verjaehrung_fest: true,
//     rows: [ { subject_id, username, tatzeit_befund, tatzeit_detail,
//               frueheste_ts, spaeteste_ts, quellen[], ampel, befund,
//               tatzeit_tag, massgeblich_norm, massgeblich_ablauf_tag,
//               restlaufzeit_tage, deadlines[], ohne_fassung[] }, ... ] }
//   Bei einem Fehler reicht loadLimitation {error: <text>} durch.
//
// KEIN SCHREIBPFAD. Diese Sicht hat keine Bedienelemente ausser der
//   Vorwarnschwellen-Auswahl, und die aendert nur die ANSICHT (ein
//   Query-Parameter am Lesepfad), nie einen Beleg.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG).
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen fassen NIE das DOM an;
//   UMD-Ausgang -> vitest testet den ECHTEN Code. Alle Texte ueber textContent
//   (Kontonamen sind beliebiger UTF-8 aus einem multilingualen Forum).
//
// Build 530: Spalte 'Grundlage' (Feststellung + Ankerart), Zustand
//   'ohne_anker', Ersatzanker-Hinweis oben, zweite Zusicherung
//   'nur_festgestellte_zitierfaehig' wird geprueft und gemeldet.
// Build 527: generische Datenlage-Zaehlung (ein neuer Befund kann nicht
//   mehr aus der Summe fallen) + Ausfall-Hinweis 'quellenfehler' direkt
//   unter dem Vorbehalt + SQLite-Grund am Zellen-Titel.
// Version: v0.8.530 · Build: 530 · 2026-07-25
// =============================================================================

(function () {
    'use strict';

    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Fristen]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // Die Zustandstabelle. Sie ist die EINZIGE Stelle, an der ein Ampelwert
    // eine Farbe und ein Label bekommt — ein Test haelt sie gegen die Liste
    // AMPEL_ZUSTAENDE des Backends, damit ein neuer Zustand nicht farblos
    // (und damit praktisch unsichtbar) in der Sicht landet.
    var AMPEL = {
        ueberschritten: { cls: 'is-ueberschritten',
                          label: 'Frist rechnerisch abgelaufen', rang: 0 },
        knapp:          { cls: 'is-knapp',
                          label: 'unter der Vorwarnschwelle', rang: 1 },
        ohne_tatzeit:   { cls: 'is-ungeprueft',
                          label: 'UNGEPRÜFT — kein Fristbeginn belegt',
                          rang: 2 },
        ohne_anker:     { cls: 'is-ungeprueft',
                          label: 'UNGEPRÜFT — Ersatzanker für diese '
                               + 'Tatbestände nicht zugelassen',
                          rang: 3 },
        ohne_fassung:   { cls: 'is-ungeprueft',
                          label: 'UNGEPRÜFT — keine Fassung zur Tatzeit',
                          rang: 4 },
        ruht:           { cls: 'is-ruht',
                          label: 'ruht möglicherweise (§ 78b I Nr. 1 StGB)',
                          rang: 5 },
        offen:          { cls: 'is-offen', label: 'Frist läuft', rang: 6 },
        keine_aussage:  { cls: 'is-stumm',
                          label: 'keine Aussage (Parametersatz unbestätigt)',
                          rang: 7 }
    };

    // Build 530: Klartext der beiden ZUR AMPEL ORTHOGONALEN Achsen. Wie bei
    // DATENLAGE_LABEL gilt: ein hier unbekannter Wert wird mit seinem Rohnamen
    // gezeigt und NICHT auf einen bekannten abgebildet.
    var FESTSTELLUNG_LABEL = {
        festgestellt: 'festgestellt',
        vorlaeufig: 'VORLÄUFIG',
        ohne: 'ohne Datum'
    };
    var ANKER_LABEL = {
        aktivitaet: 'belegte Tathandlung',
        registrierung: 'ERSATZANKER: Registrierung',
        anmeldung: 'ERSATZANKER: erste protokollierte Anmeldung',
        keine: 'kein Anker'
    };
    // Welche Ankerarten sind ERSATZ (und damit erklärungsbedürftig)? Spiegel
    // von ERSATZANKER_ARTEN in limitation.py.
    var ERSATZANKER_ARTEN = ['registrierung', 'anmeldung'];

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM).
    // =========================================================================

    // ampelInfo: Farbe/Label zu einem Zustand. Ein UNBEKANNTER Zustand wird
    // ausdruecklich als solcher gekennzeichnet und NICHT auf einen bekannten
    // abgebildet — sonst bekaeme ein neuer Backend-Zustand stillschweigend eine
    // falsche Farbe, und das waere eine Falschaussage in der auffaelligsten
    // moeglichen Form.
    function ampelInfo(ampel) {
        var a = AMPEL[ampel];
        if (a) { return a; }
        return { cls: 'is-unbekannt',
                 label: 'unbekannter Zustand (' + String(ampel) + ')',
                 rang: 99 };
    }

    // vorbehaltText: der VERJAEHRUNGSVORBEHALT. Kern dieser Sicht.
    function vorbehaltText(data) {
        if (data && data.stellt_keine_verjaehrung_fest === true) {
            return 'DIESE SICHT STELLT KEINE VERJÄHRUNG FEST. Sie rechnet die '
                + 'ununterbrochene Frist. Unterbrechungen nach § 78c StGB '
                + '(z. B. Bekanntgabe der Verfahrenseinleitung, Beschlagnahme- '
                + 'oder Durchsuchungsanordnung, Anklageerhebung) sind diesem '
                + 'Werkzeug nicht bekannt und können die Frist neu in Gang '
                + 'gesetzt haben. Jede Angabe ist die FRÜHESTMÖGLICHE Frist '
                + 'und ersetzt keine juristische Prüfung im Einzelfall.';
        }
        return 'ACHTUNG: Die Antwort trägt den Vorbehalt NICHT mit. Behandeln '
            + 'Sie keine Zeile dieser Liste als Feststellung einer Verjährung, '
            + 'bevor die Herkunft der Antwort geklärt ist.';
    }

    function vorbehaltOk(data) {
        return !!(data && data.stellt_keine_verjaehrung_fest === true);
    }

    // stummText: der Grund, warum keine Ampel gezeigt wird — oder null, wenn
    // eine Aussage moeglich ist.
    function stummText(data) {
        var d = data || {};
        if (d.aussage_moeglich === true) { return null; }
        var grund = d.verweigerungsgrund
            || 'Der Verjährungs-Parametersatz ist nicht bestätigt.';
        return 'KEINE FRISTAUSSAGE MÖGLICH: ' + grund
            + ' Die Fallliste und die Datenlage unten sind trotzdem '
            + 'vollständig — nur die rechtliche Einstufung fehlt.';
    }

    // massstabText: der angewandte Massstab. Ohne ihn ist keine Einstufung
    // nachrechenbar (dieselbe Entscheidung wie fristText in Build 521).
    function massstabText(data) {
        var d = data || {};
        var teile = [];
        teile.push('Stichtag: ' + (d.stichtag || '—'));
        teile.push('Vorwarnschwelle: '
            + ((d.vorwarn_tage === null || d.vorwarn_tage === undefined)
                ? 'nicht mitgeliefert' : (d.vorwarn_tage + ' Tage')));
        teile.push('Parametersatz: Stand ' + (d.params_stand || '—') + ', '
            + (d.params_bestaetigt
                ? ('bestätigt von ' + (d.params_bestaetigt_von || '?')
                   + ' am ' + (d.params_bestaetigt_am || '?'))
                : 'NICHT bestätigt'));
        var tb = d.vorgabe_tatbestaende || [];
        teile.push('Geprüfte Tatbestände: '
            + (tb.length ? tb.join(', ') : 'keine angegeben'));
        return teile.join(' · ');
    }

    // Klartext je Datenlage-Befund. Ein hier UNBEKANNTER Befund wird mit seinem
    // Rohnamen gezeigt statt weggelassen (Build 527).
    var DATENLAGE_LABEL = {
        belegt: 'Tatzeitpunkt belegt',
        belegt_unvollstaendig: 'belegt, aber EINGESCHRÄNKT (eine Zeitquelle '
            + 'war nicht lesbar)',
        ohne_tatzeit: 'kein Zeitstempel gesetzt',
        zeitspalte_unlesbar: 'Zeitspalte NICHT LESBAR (unbekannt, ob '
            + 'Zeitstempel vorliegen)',
        ohne_zeittabelle: 'keine Zeittabelle',
        ohne_forensic_db: 'keine forensic-Datei',
        nicht_lesbar: 'Datei nicht lesbar'
    };

    // Welche Befunde bedeuten 'ein Fristbeginn liegt vor'? Spiegel von
    // BEFUNDE_MIT_TATZEIT in limitation_repo.py.
    var BEFUNDE_MIT_TATZEIT = ['belegt', 'belegt_unvollstaendig'];

    function datenlageLabel(befund) {
        return DATENLAGE_LABEL[befund] || ('unbekannter Befund ('
            + String(befund) + ')');
    }

    // datenlageText: die Datenlage in Zahlen. Die UNGEPRUEFTEN stehen VORNE —
    // ohne sie saehe eine kurze Befundliste wie eine vollstaendige Pruefung
    // aus (dieselbe Entscheidung wie 'without_reference' in Build 521).
    //
    // BUILD 527 — DIE ZAEHLUNG IST JETZT GENERISCH. Vorher waren die vier
    // damals bekannten Befunde einzeln addiert. Als das Backend zwei neue
    // Befunde bekam ('zeitspalte_unlesbar', 'belegt_unvollstaendig'), waeren
    // sie aus der Summe GEFALLEN — die Sicht haette dann weniger ungepruefte
    // Faelle gemeldet, als es gab. Genau diese Art stiller Untererfassung soll
    // hier nicht moeglich sein: 'ohne Tatzeitpunkt' wird als Rest gerechnet
    // (Gesamt minus die Befunde MIT Tatzeit), und die Aufschluesselung listet
    // ALLE gelieferten Schluessel, auch unbekannte.
    function datenlageText(data) {
        var d = data || {};
        var dl = d.datenlage || {};
        var gesamt = d.faelle_gesamt || 0;
        var mit = 0;
        BEFUNDE_MIT_TATZEIT.forEach(function (k) { mit += (dl[k] || 0); });
        var ohne = Math.max(0, gesamt - mit);
        var teile = Object.keys(dl).sort().map(function (k) {
            return datenlageLabel(k) + ': ' + dl[k];
        });
        return gesamt + ' Fälle; ' + ohne + ' davon OHNE belegten '
            + 'Tatzeitpunkt (' + mit + ' mit). Aufschlüsselung: '
            + (teile.length ? teile.join(' · ') : 'keine Angaben') + '.';
    }

    // quellenfehlerText: das Aggregat der Lesefehler — oder null.
    // Es ersetzt einen Schwall von Protokollzeilen durch eine nachpruefbare
    // Zahl. Ein bei ALLEN Faellen gleicher Fehler ist ein Schema-Befund, und
    // der Satz sagt das ausdruecklich.
    function quellenfehlerText(data) {
        var d = data || {};
        var qf = d.quellenfehler || {};
        var schluessel = Object.keys(qf);
        if (!schluessel.length) { return null; }
        var betroffen = d.faelle_mit_quellenfehler || 0;
        var gesamt = d.faelle_gesamt || 0;
        var alle = (gesamt > 0 && betroffen === gesamt);
        return 'DATENLAGE EINGESCHRÄNKT: bei ' + betroffen + ' von ' + gesamt
            + ' Fällen war eine Zeitquelle nicht lesbar'
            + (alle ? ' — bei ALLEN, das deutet auf das Datenbankschema und '
                    + 'nicht auf einzelne Dateien'
                    : '')
            + '. ' + schluessel.sort().map(function (k) {
                return k + ' (' + qf[k] + '×)';
            }).join(' · ')
            + '. Vor einer Fristentscheidung ist die Ursache zu klären.';
    }

    // -------------------------------------------------------------------------
    // Build 530: Grundlage der Zahl (Feststellung + Ankerart).
    // -------------------------------------------------------------------------

    function feststellungLabel(wert) {
        return FESTSTELLUNG_LABEL[wert]
            || ('unbekannte Feststellung (' + String(wert) + ')');
    }

    function ankerLabel(wert) {
        return ANKER_LABEL[wert] || ('unbekannter Anker (' + String(wert) + ')');
    }

    function istErsatzanker(wert) {
        return ERSATZANKER_ARTEN.indexOf(wert) >= 0;
    }

    // grundlageText: der Zellinhalt der Spalte 'Grundlage'. Kurz genug fuer
    // eine Tabellenzelle; der ausfuehrliche Wortlaut steht als title (die
    // Vermerke des Backends, wortgleich).
    function grundlageText(row) {
        var r = row || {};
        return feststellungLabel(r.feststellung) + ' · ' + ankerLabel(r.anker_art);
    }

    // grundlageTitle: die Vermerke des Backends WORTGLEICH. Sie werden hier
    // nicht neu formuliert — eine zweite Formulierung waere eine zweite
    // Wahrheitsquelle.
    function grundlageTitle(row) {
        var v = (row && row.anker_vermerke) || [];
        return v.length ? v.join(' | ') : '';
    }

    // zitierhinweisText: die zweite Zusicherung des Backends. Fehlt sie, wird
    // das GEMELDET — genau wie beim Verjaehrungsvorbehalt. Eine Sicht, die
    // stillschweigend weiterarbeitet, wenn eine Zusicherung wegfaellt, ist
    // keine Kontrolle.
    function zitierhinweisText(data) {
        var d = data || {};
        if (d.nur_festgestellte_zitierfaehig === true) {
            return 'Der Bericht darf nur FESTGESTELLTE Daten zitieren. '
                + 'Vorläufige Zeilen sind Arbeitswerte für die Priorisierung '
                + 'und keine Fristfeststellungen.';
        }
        return 'ACHTUNG: Die Antwort trägt die Zusicherung zur '
            + 'Zitierfähigkeit NICHT mit. Übernehmen Sie keine Zeile in einen '
            + 'Bericht, bevor die Herkunft der Antwort geklärt ist.';
    }

    function zitierhinweisOk(data) {
        return !!(data && data.nur_festgestellte_zitierfaehig === true);
    }

    // ersatzankerText: wie viele Zeilen auf einem Ersatzanker beruhen — oder
    // null. Der Satz nennt AUSDRUECKLICH die Fehlerrichtung: der Anker liegt am
    // Anfang der Zugehoerigkeit, § 78a StGB knuepft an die Beendigung an, die
    // Faelle erscheinen also dringender als sie sind. Wer das nicht weiss,
    // liest die Liste falsch.
    function ersatzankerText(data) {
        var d = data || {};
        var av = d.anker_verteilung || {};
        var n = 0;
        ERSATZANKER_ARTEN.forEach(function (k) { n += (av[k] || 0); });
        if (!n) { return null; }
        return n + ' von ' + (d.faelle_gesamt || 0) + ' Fällen beruhen auf '
            + 'einem ERSATZANKER (Registrierung: ' + (av.registrierung || 0)
            + ', erste protokollierte Anmeldung: ' + (av.anmeldung || 0)
            + ') statt auf einer belegten Tathandlung. Diese Zeitpunkte liegen '
            + 'am ANFANG der Zugehörigkeit, während § 78a StGB an die '
            + 'BEENDIGUNG anknüpft — die Fristabläufe sind dort ZU FRÜH und '
            + 'die Fälle erscheinen DRINGENDER, als sie nach den bekannten '
            + 'Tatsachen sind.';
    }

    // feststellungText: die Verteilung ueber 'festgestellt'/'vorlaeufig'. Sie
    // wird GENERISCH gezaehlt (alle gelieferten Schluessel), damit ein neuer
    // Wert nicht aus der Summe faellt — dieselbe Entscheidung wie bei der
    // Datenlage in Build 527.
    function feststellungText(data) {
        var fv = (data && data.feststellung_verteilung) || {};
        var schluessel = Object.keys(fv);
        if (!schluessel.length) { return null; }
        return 'Grundlage der Zahlen: ' + schluessel.sort().map(function (k) {
            return feststellungLabel(k) + ': ' + fv[k];
        }).join(' · ') + '.';
    }

    // zaehlerText: die Ampelverteilung, in der Reihenfolge der Dringlichkeit.
    // Zustaende mit 0 werden WEGGELASSEN — aber 'ueberschritten' und 'knapp'
    // werden IMMER genannt, auch mit 0: die Abwesenheit einer Fristgefahr ist
    // eine eigene, wichtige Aussage, die nicht durch Weglassen entstehen darf.
    function zaehlerText(data) {
        var z = (data && data.zaehler) || {};
        var reihenfolge = Object.keys(AMPEL).sort(function (a, b) {
            return AMPEL[a].rang - AMPEL[b].rang;
        });
        var immer = { ueberschritten: 1, knapp: 1 };
        var teile = [];
        reihenfolge.forEach(function (k) {
            var n = z[k] || 0;
            if (n > 0 || immer[k]) {
                teile.push(AMPEL[k].label + ': ' + n);
            }
        });
        // Unbekannte Zustaende (die AMPEL nicht kennt) werden ANGEHAENGT und
        // nicht verschwiegen.
        Object.keys(z).forEach(function (k) {
            if (!AMPEL[k]) { teile.push('unbekannt (' + k + '): ' + z[k]); }
        });
        return teile.join(' · ');
    }

    // restText: die Restlaufzeit. null = nicht berechenbar -> '—', NIE '0'.
    function restText(row) {
        if (!row || row.restlaufzeit_tage === null
                || row.restlaufzeit_tage === undefined) {
            return '—';
        }
        var n = Number(row.restlaufzeit_tage);
        if (n < 0) { return n + ' T (überschritten)'; }
        if (n === 0) { return '0 T (heute)'; }
        return n + ' T';
    }

    // quellenText: aus welchen Spalten der Fristbeginn stammt. Das ist eine
    // nachpruefbare Tatsache und gehoert in die Zeile — genau wie das
    // Bezugsfeld bei den Aufbewahrungsfristen (Build 521).
    function quellenText(row) {
        var q = (row && row.quellen) || [];
        return q.length ? q.join(', ') : '—';
    }

    // rows: Reihenfolge des Backends. KEINE Neusortierung — zwei Sortierungen
    // waeren zwei Wahrheitsquellen, und das Backend sortiert bereits nach
    // Dringlichkeit (ueberschritten zuerst, Ungeprueftes vor Unverdaechtigem).
    function rows(data) {
        return (data && data.rows) || [];
    }

    // ampelZustaende: die vom Frontend abgedeckten Zustaende (fuer den Test
    // gegen die Backend-Liste AMPEL_ZUSTAENDE).
    function ampelZustaende() {
        return Object.keys(AMPEL);
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    function _el(doc, tag, cls, text) {
        var e = doc.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    // renderLimitation: baut die Sicht in mainEl.
    //   opts.doc          — Dokument (injizierbar fuer Tests)
    //   opts.onVorwarn    — Rueckruf (tage) fuer die Schwellen-Auswahl. Fehlt
    //                       er, wird die Auswahl NICHT gezeichnet: ein
    //                       Bedienelement ohne Wirkung waere schlimmer als
    //                       keines.
    function renderLimitation(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = opts.doc || mainEl.ownerDocument
            || (typeof document !== 'undefined' ? document : null);
        if (!doc) { return null; }

        mainEl.textContent = '';
        mainEl.appendChild(_el(doc, 'h2', 'aiw-pagehead',
            'Fristen (Verjährung §§ 78 ff. StGB)'));

        // FEHLER: ausdruecklich als solcher — NICHT als leere Liste. Bei einer
        // Fristsicht ist das besonders wichtig: eine leere Liste liesse sich
        // als 'keine Frist in Gefahr' lesen.
        if (data && data.error) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
                'Fristenmonitor derzeit nicht verfügbar: ' + data.error
                + ' — dies ist KEIN Leerbefund. Es ist unbekannt, ob Fristen '
                + 'ablaufen.'));
            log('Fehlerzustand:', data.error);
            return { state: 'error' };
        }

        // (1) DER VERJAEHRUNGSVORBEHALT — ganz oben, eigene Auszeichnung.
        mainEl.appendChild(_el(doc, 'div',
            'aiw-lim-vorbehalt ' + (vorbehaltOk(data) ? 'is-ok' : 'is-fehlt'),
            vorbehaltText(data)));

        // (2) Der Grund, wenn die Sicht stumm ist.
        var stumm = stummText(data);
        if (stumm) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-lim-stumm', stumm));
        }

        // (2b) Build 527: der Lesefehler-Ausfall. Er steht DIREKT unter dem
        // Vorbehalt und NICHT unten bei den Hinweisen — er entscheidet
        // darueber, ob die Zahlen in der Tabelle ueberhaupt belastbar sind,
        // und ist damit keine Fussnote. Rot, weil es hier tatsaechlich ein
        // Missstand ist (anders als der blaue Verjaehrungsvorbehalt: dort
        // haelt sich das Werkzeug an seine Grenze, hier fehlt ihm etwas).
        var qfehler = quellenfehlerText(data);
        if (qfehler) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-lim-quellenfehler',
                qfehler));
        }

        // (2c) Build 530: die zweite Zusicherung (Zitierfaehigkeit) und der
        // Ersatzanker-Hinweis. Beide stehen OBEN, weil sie darueber
        // entscheiden, was mit den Zahlen geschehen darf — nicht unten bei den
        // Fussnoten.
        mainEl.appendChild(_el(doc, 'div',
            'aiw-lim-zitierhinweis '
            + (zitierhinweisOk(data) ? 'is-ok' : 'is-fehlt'),
            zitierhinweisText(data)));
        var eatext = ersatzankerText(data);
        if (eatext) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-lim-ersatzanker', eatext));
        }

        // (3) Datenlage und Ampelverteilung.
        mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub', datenlageText(data)));
        var ftext = feststellungText(data);
        if (ftext) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-lim-feststellung', ftext));
        }
        if (!stumm) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-lim-zaehler',
                zaehlerText(data)));
        }

        // (4) Vorwarnschwellen-Auswahl — nur wenn sie WIRKT (opts.onVorwarn)
        //     und nur wenn eine Aussage moeglich ist (ohne Ampel hat eine
        //     Schwelle keinen Sinn).
        if (typeof opts.onVorwarn === 'function' && !stumm) {
            var box = _el(doc, 'div', 'aiw-lim-actions');
            box.appendChild(_el(doc, 'span', 'aiw-lim-actions-label',
                'Vorwarnschwelle:'));
            [[180, '6 Monate'], [365, '12 Monate'], [548, '18 Monate']]
                .forEach(function (spec) {
                    var b = _el(doc, 'button', 'aiw-lim-schwelle', spec[1]);
                    b.setAttribute('type', 'button');
                    b.setAttribute('data-tage', String(spec[0]));
                    if (Number(data && data.vorwarn_tage) === spec[0]) {
                        b.className += ' is-active';
                        b.setAttribute('aria-pressed', 'true');
                    }
                    b.addEventListener('click', function () {
                        log('Vorwarnschwelle ->', spec[0]);
                        opts.onVorwarn(spec[0]);
                    });
                    box.appendChild(b);
                });
            mainEl.appendChild(box);
        }

        // (5) Die Tabelle. Sie wird AUCH im stummen Zustand gezeichnet — dann
        //     ohne Ampelfarbe, aber mit der Datenlage je Fall.
        var liste = rows(data);
        if (!liste.length) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-lim-leer',
                'Keine Fälle im Bestand. Dies ist ein Leerbefund über die '
                + 'FALLLISTE, keine Aussage über Fristen.'));
        } else {
            var tbl = _el(doc, 'table', 'aiw-lim-table');
            var thead = doc.createElement('thead');
            var trh = doc.createElement('tr');
            ['Fall', 'Zustand', 'Grundlage', 'Fristbeginn', 'Quelle',
             'Maßgebliche Norm', 'Fristablauf', 'Restlaufzeit', 'Datenlage']
                .forEach(function (h) {
                    trh.appendChild(_el(doc, 'th', null, h));
                });
            thead.appendChild(trh);
            tbl.appendChild(thead);

            var tbody = doc.createElement('tbody');
            liste.forEach(function (r) {
                var info = ampelInfo(r.ampel);
                var tr = _el(doc, 'tr', 'aiw-lim-row ' + info.cls);
                tr.setAttribute('data-subject', String(r.subject_id));
                tr.setAttribute('data-ampel', String(r.ampel));
                tr.appendChild(_el(doc, 'td', 'aiw-lim-case',
                    r.subject_id + ' · ' + (r.username || '?')));
                tr.appendChild(_el(doc, 'td', 'aiw-lim-zustand', info.label));
                // Build 530: die Grundlage. Sie bekommt eigene Klassen statt
                // einer Ampelfarbe — die Zeile soll BEIDES gleichzeitig zeigen
                // koennen ('rot' UND 'vorlaeufig').
                var gz = _el(doc, 'td', 'aiw-lim-grundlage', grundlageText(r));
                if (r.feststellung === 'vorlaeufig') {
                    gz.className += ' is-vorlaeufig';
                }
                if (istErsatzanker(r.anker_art)) {
                    gz.className += ' is-ersatzanker';
                }
                var gt = grundlageTitle(r);
                if (gt) { gz.setAttribute('title', gt); }
                tr.appendChild(gz);
                tr.appendChild(_el(doc, 'td', 'aiw-lim-tat',
                    r.tatzeit_tag || '—'));
                tr.appendChild(_el(doc, 'td', 'aiw-lim-quelle',
                    quellenText(r)));
                tr.appendChild(_el(doc, 'td', 'aiw-lim-norm',
                    r.massgeblich_norm || '—'));
                tr.appendChild(_el(doc, 'td', 'aiw-lim-ablauf',
                    r.massgeblich_ablauf_tag || '—'));
                tr.appendChild(_el(doc, 'td', 'aiw-lim-rest', restText(r)));
                // Die Datenlage steht IN der Zeile: 'keine forensic-Datei' ist
                // eine andere Lage als 'Tabelle ohne Zeitstempel', und beide
                // erklaeren, warum die Frist leer bleibt.
                var dz = _el(doc, 'td', 'aiw-lim-datenlage',
                    datenlageLabel(r.tatzeit_befund));
                // Der SQLite-Grund gehoert an die Zelle, nicht in ein
                // Protokoll: wer die Zeile sieht, soll die Ursache erfahren.
                if (r.quellen_fehler && r.quellen_fehler.length) {
                    dz.className += ' is-eingeschraenkt';
                    dz.setAttribute('title', r.quellen_fehler.join(' | '));
                }
                tr.appendChild(dz);
                tbody.appendChild(tr);
            });
            tbl.appendChild(tbody);
            mainEl.appendChild(tbl);
        }

        // (6) Der Massstab steht IMMER da — auch im stummen Zustand und auch
        //     beim Leerbefund. Ohne Massstab sagt auch ein Leerbefund nichts.
        mainEl.appendChild(_el(doc, 'div', 'aiw-lim-foot',
            massstabText(data)));

        // (7) Die Vorbehalte und Hinweise des Backends WORTGLEICH. Sie sind
        //     kein Anhang: die share_id-Luecke und der Ruhens-Vorbehalt
        //     entscheiden darueber, wie belastbar jede Zeile oben ist.
        var vb = (data && data.vorbehalte) || [];
        var hw = (data && data.hinweise) || [];
        if (vb.length || hw.length) {
            var det = doc.createElement('details');
            det.className = 'aiw-lim-vorbehalte';
            var sum = _el(doc, 'summary', null,
                'Vorbehalte und Datenlücken (' + (vb.length + hw.length) + ')');
            det.appendChild(sum);
            var ul = doc.createElement('ul');
            vb.concat(hw).forEach(function (t) {
                ul.appendChild(_el(doc, 'li', null, t));
            });
            det.appendChild(ul);
            mainEl.appendChild(det);
        } else {
            // KEINE Vorbehalte ist ein VERDACHTSMOMENT, nicht eine gute
            // Nachricht: das Backend liefert sie immer mit.
            mainEl.appendChild(_el(doc, 'div', 'aiw-lim-vorbehalt is-fehlt',
                'ACHTUNG: Die Antwort enthält KEINE Vorbehalte. Das Backend '
                + 'liefert sie normalerweise immer mit — die Herkunft dieser '
                + 'Antwort ist zu klären.'));
        }

        log('gerendert:', liste.length, 'Zeilen; stumm:', !!stumm);
        return {
            state: stumm ? 'stumm' : (liste.length ? 'befund' : 'leer'),
            count: liste.length,
            vorbehalt: vorbehaltOk(data)
        };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        AMPEL: AMPEL,
        ampelInfo: ampelInfo,
        ampelZustaende: ampelZustaende,
        vorbehaltText: vorbehaltText,
        vorbehaltOk: vorbehaltOk,
        stummText: stummText,
        massstabText: massstabText,
        datenlageText: datenlageText,
        datenlageLabel: datenlageLabel,
        quellenfehlerText: quellenfehlerText,
        DATENLAGE_LABEL: DATENLAGE_LABEL,
        BEFUNDE_MIT_TATZEIT: BEFUNDE_MIT_TATZEIT,
        FESTSTELLUNG_LABEL: FESTSTELLUNG_LABEL,
        ANKER_LABEL: ANKER_LABEL,
        ERSATZANKER_ARTEN: ERSATZANKER_ARTEN,
        feststellungLabel: feststellungLabel,
        ankerLabel: ankerLabel,
        istErsatzanker: istErsatzanker,
        grundlageText: grundlageText,
        grundlageTitle: grundlageTitle,
        zitierhinweisText: zitierhinweisText,
        zitierhinweisOk: zitierhinweisOk,
        ersatzankerText: ersatzankerText,
        feststellungText: feststellungText,
        zaehlerText: zaehlerText,
        restText: restText,
        quellenText: quellenText,
        rows: rows,
        renderLimitation: renderLimitation
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitLimitation = API; }
})();
