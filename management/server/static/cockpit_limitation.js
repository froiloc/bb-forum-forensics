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
// SIEBEN ZUSTAENDE, SIEBEN FARBEN (Spiegel cockpit.css .aiw-lim-*):
//   ueberschritten — rot     (Frist rechnerisch abgelaufen)
//   knapp          — orange  (unter der Vorwarnschwelle)
//   ohne_tatzeit   — violett (UNGEPRUEFT: kein Fristbeginn belegt)
//   ohne_fassung   — violett (UNGEPRUEFT: keine Fassung zur Tatzeit hinterlegt)
//   ruht           — blau    (§ 78b Abs. 1 Nr. 1 StGB, nicht berechenbar)
//   offen          — gruen   (Restlaufzeit ueber der Schwelle)
//   keine_aussage  — grau    (Parametersatz nicht bestaetigt)
//   'ohne_tatzeit' ist AUSDRUECKLICH NICHT gruen und nicht grau: der Fall ist
//   nicht unverdaechtig, sondern unbekannt. Eine eigene, auffaellige Farbe ist
//   hier kein Zierrat, sondern der Unterschied zwischen 'geprueft' und
//   'ungeprueft'.
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
// Version: v0.8.525 · Build: 525 · 2026-07-25
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
        ohne_fassung:   { cls: 'is-ungeprueft',
                          label: 'UNGEPRÜFT — keine Fassung zur Tatzeit',
                          rang: 3 },
        ruht:           { cls: 'is-ruht',
                          label: 'ruht möglicherweise (§ 78b I Nr. 1 StGB)',
                          rang: 4 },
        offen:          { cls: 'is-offen', label: 'Frist läuft', rang: 5 },
        keine_aussage:  { cls: 'is-stumm',
                          label: 'keine Aussage (Parametersatz unbestätigt)',
                          rang: 6 }
    };

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

    // datenlageText: die Datenlage in Zahlen. Die UNGEPRUEFTEN stehen VORNE —
    // ohne sie saehe eine kurze Befundliste wie eine vollstaendige Pruefung
    // aus (dieselbe Entscheidung wie 'without_reference' in Build 521).
    function datenlageText(data) {
        var d = data || {};
        var dl = d.datenlage || {};
        var ungeprueft = (dl.ohne_forensic_db || 0) + (dl.ohne_zeittabelle || 0)
            + (dl.nicht_lesbar || 0) + (dl.ohne_tatzeit || 0);
        return (d.faelle_gesamt || 0) + ' Fälle; ' + ungeprueft
            + ' davon OHNE belegten Tatzeitpunkt (' + (dl.belegt || 0)
            + ' mit). Aufschlüsselung: '
            + 'keine forensic-Datei ' + (dl.ohne_forensic_db || 0) + ', '
            + 'keine Zeittabelle ' + (dl.ohne_zeittabelle || 0) + ', '
            + 'nicht lesbar ' + (dl.nicht_lesbar || 0) + ', '
            + 'Tabelle ohne Zeitstempel ' + (dl.ohne_tatzeit || 0) + '.';
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

        // (3) Datenlage und Ampelverteilung.
        mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub', datenlageText(data)));
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
            ['Fall', 'Zustand', 'Fristbeginn (späteste Tat)', 'Quelle',
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
                tr.appendChild(_el(doc, 'td', 'aiw-lim-datenlage',
                    r.tatzeit_befund || '—'));
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
        zaehlerText: zaehlerText,
        restText: restText,
        quellenText: quellenText,
        rows: rows,
        renderLimitation: renderLimitation
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitLimitation = API; }
})();
