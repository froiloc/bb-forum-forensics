// =============================================================================
// management/server/static/cockpit_escalation.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Eskalationen
// =============================================================================
// Zweck (AP-2G / Idee 23, Frontend zu Build 515):
//   Zeigt die belegten Eskalationen aus GET /api/escalations. Das Read-Model
//   selbst gibt es seit Build 453 — es war bis Build 514 nur ueber die CLI
//   erreichbar und in KEINER Cockpit-Sicht sichtbar (Befund Uebergabe 440-453).
//
// ERWEITERT IN BUILD 518 (Frontend zu 517): die QUITTIERUNG. Eine Leitung kann
//   jetzt in der Sicht festhalten, dass sie eine Eskalation gesehen und was sie
//   veranlasst hat — auditiert, mit Pflichtbegruendung, widerrufbar.
//
// Datenform GET /api/escalations (ManagementApp._escalations):
//   { generated_at, total_cases,
//     count_hoch, count_mittel, count_niedrig,
//     items: [ {rule_code, label, severity, subject_id, message,
//               days_inactive,
//               // ab Build 517 additiv:
//               ack: null | {ack_id, reason, acknowledged_by,
//                            acknowledged_by_name, acknowledged_at,
//                            days_inactive_at_ack, audit_seq, outdated}
//              }, ... ],
//     thresholds: {red_overdue_days, stale_open_days, backlog_high},
//     acknowledgeable: bool,   // Struktur UND Recht
//     ack_migrated: bool }     // nur Struktur
//   Bei einem Fehler reicht loadEscalation {error: <text>} durch.
//
// SCHREIBEN (nur mit escalation.ack):
//   opts.onAck({rule_code, subject_id, reason, days_inactive})
//        -> POST /api/escalations/ack
//   opts.onRevoke({ack_id, reason})
//        -> POST /api/escalations/ack/revoke
//   KEIN optimistisches UI: nach dem Schreiben laedt cockpit.js die Sicht neu.
//   Der Pflichttext wird HIER geprueft, BEVOR der Server behelligt wird — der
//   Server prueft ihn ohnehin ein zweites Mal (er ist die Wahrheitsquelle).
//
// FUENF ENTSCHEIDUNGEN, DIE DEN BELEG TRAGEN:
//
//   (1) subject_id === null IST EINE AUSSAGE, KEINE LUECKE. Die systemische
//       Regel 'rueckstau_hoch' gehoert GAR KEINEM Fall — sie meldet, dass
//       Faelle unverteilt liegen bleiben. Sie wird deshalb ausdruecklich als
//       "systemisch (kein Einzelfall)" ausgewiesen und NICHT als leere Zelle
//       oder als Fall 0. Eine leere Zelle haette wie ein Datenfehler gelesen.
//       Sie ist AUCH quittierbar — sie ist die wichtigste Meldung der Sicht.
//
//   (2) DER MASSSTAB STEHT DABEI. Die angewandten Schwellen erscheinen unter
//       der Liste. "30 Tage inaktiv" ist erst zusammen mit ">= 30" eine
//       nachpruefbare Aussage; ohne den Massstab waere jede Zeile eine
//       unbelegte Behauptung.
//
//   (3) QUITTIEREN IST KEIN ERLEDIGEN. Eine quittierte Meldung BLEIBT in der
//       Liste und behaelt ihre Schwere und Farbe. Sie bekommt lediglich einen
//       Vermerk dazu. Wuerde die Sicht sie ausblenden oder abstufen, liesse
//       sich ein liegengebliebener Fall per Klick unauffaellig machen, ohne
//       dass sich an ihm etwas aendert (Grundregel 1). Das Frontend filtert
//       daher NICHTS und sortiert NICHTS um.
//
//   (4) 'gibt es nicht' UND 'darfst du nicht' SIND ZWEI AUSSAGEN. Der Server
//       liefert beide getrennt (ack_migrated / acknowledgeable). Die Sicht
//       sagt entsprechend entweder "die Struktur fehlt (Migration M027)" oder
//       "Sie haben dieses Recht nicht" — statt in beiden Faellen wortlos
//       keinen Knopf zu zeigen.
//
//   (5) EIN UEBERHOLTER VERMERK WIRD ALS SOLCHER GEZEIGT. 'ack.outdated' sagt
//       ohne jede zusaetzliche Schwelle: der Fall ist heute laenger inaktiv
//       als bei der Quittierung. Die Lage hat sich seit dem Vermerk
//       VERSCHLECHTERT — das darf nicht aussehen wie ein frischer Vermerk.
//
// GRUNDREGEL 1 (kein stiller Leerbefund): drei UNTERSCHEIDBARE Zustaende —
//   Fehler ("derzeit nicht verfuegbar"), echter Leerbefund ("keine Eskalation,
//   bewertet wurden N Faelle") und Befund (Liste). Eine leere Liste im
//   Fehlerfall haette faelschlich "alles in Ordnung" behauptet.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging, umschaltbar ueber
//   window.AIW_COCKPIT_DEBUG. 3) Ausfuehrliche Kommentare. 4) Reine Funktionen
//   fassen NIE das DOM an; UMD-Ausgang -> vitest testet den ECHTEN Code.
//   Alle Texte ueber textContent (kein innerHTML): die Meldungen und die
//   Vermerke enthalten Namen und Freitexte aus ungepruefter Quelle.
//
// Version: v0.8.518 · Build: 518 · 2026-07-24
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
        args.unshift('[AIW-Eskalation]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM).
    // =========================================================================

    // severityClass: CSS-Modifikator je Schwere. Unbekannte Werte bekommen
    // KEINEN Modifikator (statt still auf 'niedrig' zu fallen) — eine neue
    // Schwere aus dem Backend soll auffallen, nicht verschwinden.
    function severityClass(sev) {
        if (sev === 'hoch') { return 'is-hoch'; }
        if (sev === 'mittel') { return 'is-mittel'; }
        if (sev === 'niedrig') { return 'is-niedrig'; }
        return 'is-unbekannt';
    }

    // severityLabel: Anzeigetext je Schwere. Ein unbekannter Wert wird
    // WOERTLICH durchgereicht und als solcher markiert.
    function severityLabel(sev) {
        if (sev === 'hoch') { return 'hoch'; }
        if (sev === 'mittel') { return 'mittel'; }
        if (sev === 'niedrig') { return 'niedrig'; }
        return 'unbekannt (' + String(sev) + ')';
    }

    // itemTarget: Bezugsobjekt einer Meldung als Klartext. Siehe Entscheidung
    // (1) im Dateikopf — null ist hier eine Aussage, keine Luecke.
    function itemTarget(item) {
        if (!item || item.subject_id === null || item.subject_id === undefined) {
            return 'systemisch (kein Einzelfall)';
        }
        return 'Fall ' + item.subject_id;
    }

    // inactiveText: Inaktivitaet als Klartext. null bedeutet "nie eine
    // Aktivitaet erfasst" — das ist etwas anderes als "0 Tage inaktiv".
    function inactiveText(item) {
        if (!item || item.days_inactive === null
            || item.days_inactive === undefined) {
            return '—';
        }
        return item.days_inactive + ' T';
    }

    // countsText: Zusammenfassung ueber der Liste. Nennt IMMER alle drei
    // Schweren, auch wenn sie 0 sind (eine weggelassene 0 waere ein stiller
    // Verzicht), und die Zahl der bewerteten Faelle — sie belegt, dass die
    // Erhebung stattgefunden hat.
    function countsText(data) {
        var d = data || {};
        return (d.count_hoch || 0) + ' hoch · ' + (d.count_mittel || 0)
            + ' mittel · ' + (d.count_niedrig || 0) + ' niedrig — bewertet '
            + 'wurden ' + (d.total_cases || 0) + ' Fälle.';
    }

    // thresholdText: der angewandte Massstab (Entscheidung (2)). Fehlt der
    // Block, wird das BENANNT statt einfach nichts anzuzeigen.
    function thresholdText(data) {
        var t = data && data.thresholds;
        if (!t) {
            return 'Angewandter Maßstab: nicht mitgeliefert — die Einstufungen '
                + 'sind hier NICHT nachrechenbar.';
        }
        return 'Angewandter Maßstab: rote Fälle ab ' + t.red_overdue_days
            + ' Tagen Inaktivität, offene zugewiesene Fälle ab '
            + t.stale_open_days + ' Tagen, Rückstau-Alarm ab '
            + t.backlog_high + ' unzugewiesenen Fällen.';
    }

    // ackText: Ansage zum Quittierungsweg (Entscheidungen (3) und (4)).
    // Sie unterscheidet AUSDRUECKLICH, warum nicht quittiert werden kann.
    function ackText(data) {
        var d = data || {};
        if (d.acknowledgeable === true) {
            return 'Quittieren hält fest, dass die Eskalation gesehen und was '
                + 'veranlasst wurde. Es ist KEIN Erledigen: die Meldung bleibt '
                + 'stehen, bis die Ursache behoben ist. Die Begründung ist '
                + 'Pflicht und wird auditiert.';
        }
        if (d.ack_migrated === false) {
            return 'Quittieren ist nicht möglich: die dafür nötige Struktur '
                + 'fehlt in dieser Datenbank (Migration M027 nicht angewandt). '
                + 'Das ist NICHT dasselbe wie ein fehlendes Recht.';
        }
        if (d.ack_migrated === true) {
            return 'Quittieren ist Ihnen hier nicht möglich: das Recht '
                + '„escalation.ack“ ist Ihnen nicht erteilt. Die Struktur ist '
                + 'vorhanden — es fehlt allein die Berechtigung.';
        }
        // Aeltere Antwort ohne die beiden Angaben: NICHT raten.
        return 'Quittieren ist in dieser Fassung nicht möglich: die Sicht ist '
            + 'rein auswertend. Eine Eskalation verschwindet erst, wenn die '
            + 'zugrunde liegende Ursache behoben ist (Fall bearbeiten, '
            + 'zuweisen oder abschließen).';
    }

    // canAck: darf dieser Aufrufer quittieren? Nur wenn der SERVER es sagt.
    // Das Frontend leitet das NICHT aus Rechten ab, die es selbst kennt — der
    // Server ist die Wahrheitsquelle und prueft ohnehin ein zweites Mal.
    function canAck(data) {
        return !!(data && data.acknowledgeable === true);
    }

    // ackOf: der Vermerk einer Meldung (oder null).
    function ackOf(item) {
        return (item && item.ack) ? item.ack : null;
    }

    // ackState: 'keiner' | 'gueltig' | 'ueberholt'. Entscheidung (5).
    function ackState(item) {
        var a = ackOf(item);
        if (!a) { return 'keiner'; }
        return a.outdated === true ? 'ueberholt' : 'gueltig';
    }

    // fmtTs: Unix-Sekunden als lesbares Datum (lokale Zeit des Arbeitsplatzes).
    // Ein fehlender Zeitstempel wird als '—' gezeigt, nicht als 1970.
    function fmtTs(ts) {
        if (ts === null || ts === undefined || ts === '') { return '—'; }
        var d = new Date(Number(ts) * 1000);
        if (isNaN(d.getTime())) { return String(ts); }
        function p(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-'
            + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
    }

    // ackLine: der Vermerk einer Meldung als Klartext. Rein.
    // Nennt WER, WANN, WARUM und — bei einem ueberholten Vermerk — dass sich
    // die Lage seither verschlechtert hat.
    function ackLine(item) {
        var a = ackOf(item);
        if (!a) { return 'nicht quittiert'; }
        var wer = a.acknowledged_by_name || ('#' + a.acknowledged_by);
        var txt = 'Quittiert ' + fmtTs(a.acknowledged_at) + ' von ' + wer
            + ': ' + (a.reason || '');
        if (a.audit_seq) { txt += ' (Beleg #' + a.audit_seq + ')'; }
        if (a.outdated === true) {
            txt += ' — ÜBERHOLT: bei der Quittierung ' + a.days_inactive_at_ack
                + ' Tage inaktiv, jetzt ' + item.days_inactive + '.';
        }
        return txt;
    }

    // items: die Meldungen in der Reihenfolge des Backends. BEWUSST keine
    // Neusortierung und KEINE Filterung im Frontend — das Backend ordnet
    // bereits nach Schwere, dann Inaktivitaet, dann subject_id. Zwei
    // Sortierungen fuer dieselbe Liste waeren zwei Wahrheitsquellen; ein
    // Filter waere ein stiller Verzicht (Entscheidung (3)).
    function items(data) {
        return (data && data.items) || [];
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

    // _ackControls: die Bedienelemente einer Zeile. Gibt es einen gueltigen
    // Vermerk, wird WIDERRUFEN angeboten (nie Loeschen); sonst QUITTIEREN.
    // Beide verlangen einen Pflichttext, der HIER geprueft wird, bevor der
    // Server behelligt wird.
    function _ackControls(doc, item, opts, setResult) {
        var host = _el(doc, 'div', 'aiw-esk-actions');
        var a = ackOf(item);
        var istWiderruf = !!a;

        var feld = doc.createElement('input');
        feld.type = 'text';
        feld.className = 'aiw-esk-reason';
        feld.placeholder = istWiderruf
            ? 'Grund des Widerrufs (Pflicht)'
            : 'Was wurde veranlasst? (Pflicht)';
        feld.setAttribute('aria-label', feld.placeholder);

        var knopf = _el(doc, 'button', 'aiw-esk-btn',
            istWiderruf ? 'Vermerk widerrufen' : 'Quittieren');
        knopf.type = 'button';
        knopf.addEventListener('click', function () {
            var text = (feld.value || '').trim();
            if (!text) {
                // Pflichttext VOR dem Netzaufruf pruefen — und die Ablehnung
                // BENENNEN statt den Knopf wirkungslos zu lassen.
                setResult(istWiderruf
                    ? 'Der Widerruf braucht einen Grund.'
                    : 'Die Quittierung braucht eine Begründung — ein Vermerk '
                      + 'ohne Begründung belegt nur einen Klick.', true);
                feld.focus();
                return;
            }
            if (istWiderruf) {
                if (typeof opts.onRevoke === 'function') {
                    opts.onRevoke({ ack_id: a.ack_id, reason: text });
                } else {
                    setResult('Kein Schreibpfad verdrahtet.', true);
                }
                return;
            }
            if (typeof opts.onAck === 'function') {
                opts.onAck({
                    rule_code: item.rule_code,
                    // null bleibt null: die systemische Regel gehoert zu
                    // keinem Fall (Entscheidung (1)).
                    subject_id: (item.subject_id === undefined
                        ? null : item.subject_id),
                    reason: text,
                    // Der BEOBACHTETE Stand faehrt mit, damit spaeter
                    // erkennbar bleibt, ob sich die Lage verschlechtert hat.
                    days_inactive: (item.days_inactive === undefined
                        ? null : item.days_inactive)
                });
            } else {
                setResult('Kein Schreibpfad verdrahtet.', true);
            }
        });

        host.appendChild(feld);
        host.appendChild(knopf);
        return host;
    }

    // renderEscalation: baut die Sicht in mainEl. opts.doc ist injizierbar
    // (JSDOM-Tests); Default ist das Dokument von mainEl.
    // opts.onAck / opts.onRevoke — Schreibpfade (siehe Dateikopf).
    // opts.message — {text, error} Rueckmeldung des vorigen Schreibvorgangs.
    // Rueckgabe: kleines Sichtobjekt mit setResult(text, isError).
    function renderEscalation(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = opts.doc || mainEl.ownerDocument
            || (typeof document !== 'undefined' ? document : null);
        if (!doc) { return null; }

        mainEl.textContent = '';
        // Build 595 (Baustelle H / H7): literale Hilfe-Marken (handgebaute
        // Tabelle, daher keine Anker vom gemeinsamen Tabellen-Werkzeug).
        var kopfEl = _el(doc, 'h2', 'aiw-pagehead', 'Eskalationen');
        kopfEl.setAttribute('data-hilfe-id', 'escalation.titel');
        mainEl.appendChild(kopfEl);

        // Rueckmeldeleiste: sie existiert IMMER, damit eine Meldung nicht
        // durch einen Neuaufbau der Sicht verlorengeht.
        var res = _el(doc, 'div', 'aiw-esk-result');
        function setResult(text, isError) {
            res.textContent = text || '';
            res.className = 'aiw-esk-result'
                + (text ? (isError ? ' is-err' : ' is-ok') : '');
        }

        // FEHLER: ausdruecklich als solcher — NICHT als leere Liste.
        if (data && data.error) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
                'Eskalationen derzeit nicht verfügbar: ' + data.error
                + ' — dies ist KEIN Leerbefund. Es ist unbekannt, ob '
                + 'Eskalationen vorliegen.'));
            log('Fehlerzustand:', data.error);
            return { state: 'error', setResult: setResult };
        }

        var zahlenEl = _el(doc, 'p', 'aiw-pagesub', countsText(data));
        zahlenEl.setAttribute('data-hilfe-id', 'escalation.zahlen');
        mainEl.appendChild(zahlenEl);
        mainEl.appendChild(res);
        if (opts.message && opts.message.text) {
            setResult(opts.message.text, opts.message.error === true);
        }

        var darfQuittieren = canAck(data);
        var liste = items(data);

        if (!liste.length) {
            // ECHTER Leerbefund — und er sagt dazu, worauf er sich stuetzt.
            mainEl.appendChild(_el(doc, 'div', 'aiw-esk-leer',
                'Keine Eskalation. Geprüft wurden '
                + ((data && data.total_cases) || 0)
                + ' Fälle gegen den unten genannten Maßstab.'));
        } else {
            var tbl = _el(doc, 'table', 'aiw-esk-table');
            var thead = doc.createElement('thead');
            var trh = doc.createElement('tr');
            [['Schwere', 'schwere'], ['Regel', 'regel'], ['Bezug', 'bezug'],
             ['Inaktiv', 'inaktiv'], ['Begründung', 'begruendung'],
             ['Vermerk', 'vermerk']]
                .forEach(function (h) {
                    var th = _el(doc, 'th', null, h[0]);
                    th.setAttribute('data-hilfe-id',
                        'escalation.spalte.' + h[1]);
                    trh.appendChild(th);
                });
            thead.appendChild(trh);
            tbl.appendChild(thead);

            var tbody = doc.createElement('tbody');
            liste.forEach(function (it) {
                // ENTSCHEIDUNG (3): die Schwere-Klasse bleibt, was sie ist.
                // Ein Vermerk stuft NICHT ab.
                var tr = _el(doc, 'tr', 'aiw-esk-row '
                    + severityClass(it.severity));
                tr.setAttribute('data-rule', String(it.rule_code || ''));
                tr.setAttribute('data-severity', String(it.severity || ''));
                tr.setAttribute('data-ack', ackState(it));
                tr.appendChild(_el(doc, 'td', 'aiw-esk-sev',
                    severityLabel(it.severity)));
                tr.appendChild(_el(doc, 'td', null, it.label || it.rule_code));
                tr.appendChild(_el(doc, 'td', 'aiw-esk-target',
                    itemTarget(it)));
                tr.appendChild(_el(doc, 'td', 'aiw-esk-days',
                    inactiveText(it)));
                // Die Begruendung kommt WOERTLICH aus dem Backend — das
                // Frontend formuliert keine zweite Fassung derselben Aussage.
                tr.appendChild(_el(doc, 'td', 'aiw-esk-msg', it.message || ''));

                // Vermerk-Spalte: Text IMMER, Bedienelemente nur mit Recht.
                var tdAck = _el(doc, 'td', 'aiw-esk-ackcell');
                var zeile = _el(doc, 'div',
                    'aiw-esk-ackline is-' + ackState(it), ackLine(it));
                tdAck.appendChild(zeile);
                if (darfQuittieren) {
                    tdAck.appendChild(_ackControls(doc, it, opts, setResult));
                }
                tr.appendChild(tdAck);
                tbody.appendChild(tr);
            });
            tbl.appendChild(tbody);
            mainEl.appendChild(tbl);
        }

        // Massstab (2) und Quittierungs-Ansage (3)/(4) stehen IMMER da — auch
        // beim Leerbefund, denn ohne Massstab sagt auch ein Leerbefund nichts.
        mainEl.appendChild(_el(doc, 'div', 'aiw-esk-foot', thresholdText(data)));
        var ack = ackText(data);
        if (ack) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-esk-ack', ack));
        }

        log('gerendert:', liste.length, 'Meldungen, quittierbar:',
            darfQuittieren);
        return {
            state: liste.length ? 'befund' : 'leer',
            count: liste.length,
            canAck: darfQuittieren,
            setResult: setResult
        };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        severityClass: severityClass,
        severityLabel: severityLabel,
        itemTarget: itemTarget,
        inactiveText: inactiveText,
        countsText: countsText,
        thresholdText: thresholdText,
        ackText: ackText,
        items: items,
        renderEscalation: renderEscalation,
        // Build 518 (Quittierung) — rein und damit unter vitest pruefbar.
        canAck: canAck,
        ackOf: ackOf,
        ackState: ackState,
        ackLine: ackLine,
        fmtTs: fmtTs
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitEscalation = API; }
})();
