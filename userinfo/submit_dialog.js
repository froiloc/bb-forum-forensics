// =============================================================================
// userinfo/submit_dialog.js
// IT-Forensisches Ermittlungswerkzeug — Berichtseditor: Zur Abnahme freigeben
// =============================================================================
// Zweck:
//   Bestaetigungsdialog fuer die Aktion "Zur Abnahme freigeben"
//   (draft -> submitted, Backend: Build 381).
//
// WARUM EIN DIALOG (mc 2026-07-10): Das Einreichen hat TRAGWEITE — der Bericht
//   wird damit FUER DEN AUTOR GESPERRT (Schreibsperre, Build 379). Er kann
//   danach keine Bloecke mehr anlegen, aendern, loeschen, umsortieren oder
//   Beweisanker setzen. Zurueckholen kann ihn NUR der Lektor oder die
//   Chef-Ermittlerin. Das darf kein versehentlicher Klick sein.
//
//   Der Dialog klaert daher ueber DREI Dinge auf:
//     (a) die TRAGWEITE      — was der Autor danach nicht mehr kann
//     (b) den PROZESS        — was als Naechstes geschieht (Abnahme,
//                              Versiegelung, Versand)
//     (c) die RUECKHOLUNG    — nur ueber Lektor/Chef-Ermittlerin
//
//   ZWEISTUFIG: Der Bestaetigen-Knopf ist erst aktiv, wenn der Autor das
//   Kontrollkaestchen "Mir ist bewusst, dass ..." gesetzt hat. Eine bewusste
//   Entscheidung, kein Reflex.
//
// Beleg: documents/Berichts_Statusmodell.md; BERICHTS-STATUSMODELL.
//
// PROJEKT-GEBOTE FUER JS: IIFE + 'use strict'; ausfuehrliche Kommentare;
//   Debug-Logging fuer DEV; Kapselung. XSS: ausschliesslich textContent.
//
// Version: v0.7.382 · Build: 382 · 2026-07-10
// =============================================================================

(function () {
    'use strict';

    function debugOn() {
        return (typeof window !== 'undefined')
            && window.FORENSIC_DEBUG !== false;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-SubmitDialog]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (Texte) — in vitest pruefbar.
    // =========================================================================

    // dialogTexts: die drei Aufklaerungs-Abschnitte. Als Daten gehalten, damit
    // sie testbar sind und nicht im DOM-Code versickern.
    function dialogTexts(reportTitle) {
        return {
            title: 'Bericht zur Abnahme freigeben?',
            subject: reportTitle || '(ohne Titel)',
            sections: [
                {
                    key: 'tragweite',
                    heading: 'Was das bedeutet',
                    lines: [
                        'Der Bericht wird damit FUER SIE GESPERRT.',
                        'Sie koennen danach keine Absaetze mehr anlegen, '
                            + 'aendern, loeschen oder umsortieren und keine '
                            + 'Beweisanker mehr setzen.',
                        'Kommentare bleiben weiterhin moeglich.'
                    ]
                },
                {
                    key: 'prozess',
                    heading: 'Wie es weitergeht',
                    lines: [
                        'Der Bericht erscheint bei der Chef-Ermittlerin zur '
                            + 'Abnahme.',
                        'Mit der Abnahme wird er versiegelt (Inhaltshash) und '
                            + 'ist dann unwiderruflich.',
                        'Anschliessend kann er an die Staatsanwaltschaft '
                            + 'versandt werden.'
                    ]
                },
                {
                    key: 'rueckholung',
                    heading: 'Falls Sie doch noch etwas aendern muessen',
                    lines: [
                        'Sie selbst koennen den Bericht NICHT zurueckholen.',
                        'Nur der Lektor oder die Chef-Ermittlerin koennen ihn '
                            + 'zur Nachbesserung zurueckgeben.'
                    ]
                }
            ],
            ackLabel: 'Mir ist bewusst, dass ich den Bericht danach nicht mehr '
                + 'selbst bearbeiten kann.',
            confirmLabel: 'Zur Abnahme freigeben',
            cancelLabel: 'Abbrechen'
        };
    }

    // canSubmit: der Knopf erscheint NUR beim eigenen Bericht im Status
    // 'draft'. (Der Server prueft das erneut — die Oberflaeche ist keine
    // Sicherheitsgrenze, sie soll nur keine Aktion anbieten, die zwingend
    // scheitern wuerde.)
    function canSubmit(report, investigator) {
        if (!report) { return false; }
        if (String(report.status) !== 'draft') { return false; }
        if (!investigator) { return false; }
        return String(report.created_by) === String(investigator);
    }

    // =========================================================================
    // 2) DOM.
    // =========================================================================

    function _section(doc, sec) {
        var box = doc.createElement('div');
        box.className = 'aiw-submit-section';
        box.setAttribute('data-section', sec.key);

        var h = doc.createElement('h4');
        h.textContent = sec.heading;
        box.appendChild(h);

        var ul = doc.createElement('ul');
        sec.lines.forEach(function (line) {
            var li = doc.createElement('li');
            li.textContent = line;      // XSS: nur textContent
            ul.appendChild(li);
        });
        box.appendChild(ul);
        return box;
    }

    // open: zeigt den Dialog. onConfirm() wird NUR gerufen, wenn der Autor
    // bestaetigt hat. Rueckgabe: das Overlay-Element (fuer Tests/Abbau).
    function open(doc, reportTitle, onConfirm) {
        doc = doc || document;
        var t = dialogTexts(reportTitle);

        var overlay = doc.createElement('div');
        overlay.className = 'aiw-submit-overlay';
        overlay.id = 'aiw-submit-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;display:flex;'
            + 'align-items:center;justify-content:center;'
            + 'background:rgba(0,0,0,0.5);z-index:2000;';

        var box = doc.createElement('div');
        box.className = 'aiw-submit-box';
        box.style.cssText = 'background:#fff;color:#1b2733;max-width:640px;'
            + 'width:92%;max-height:85vh;overflow:auto;border-radius:8px;'
            + 'padding:20px 24px;box-shadow:0 12px 48px rgba(0,0,0,0.4);';

        var h = doc.createElement('h3');
        h.className = 'aiw-submit-title';
        h.textContent = t.title;
        h.style.marginTop = '0';
        box.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-submit-subject';
        sub.textContent = t.subject;
        box.appendChild(sub);

        t.sections.forEach(function (sec) {
            box.appendChild(_section(doc, sec));
        });

        // Zweistufig: erst bewusst bestaetigen, dann handeln.
        var ackWrap = doc.createElement('label');
        ackWrap.className = 'aiw-submit-ack';
        ackWrap.style.cssText = 'display:block;margin:14px 0;font-weight:600;';
        var ack = doc.createElement('input');
        ack.type = 'checkbox';
        ack.id = 'aiw-submit-ack';
        var ackText = doc.createElement('span');
        ackText.textContent = ' ' + t.ackLabel;
        ackWrap.appendChild(ack);
        ackWrap.appendChild(ackText);
        box.appendChild(ackWrap);

        var btns = doc.createElement('div');
        btns.style.cssText = 'display:flex;gap:10px;justify-content:flex-end;';

        var cancel = doc.createElement('button');
        cancel.type = 'button';
        cancel.id = 'aiw-submit-cancel';
        cancel.className = 'report-btn';
        cancel.textContent = t.cancelLabel;

        var confirm = doc.createElement('button');
        confirm.type = 'button';
        confirm.id = 'aiw-submit-confirm';
        confirm.className = 'report-btn report-btn-primary';
        confirm.textContent = t.confirmLabel;
        confirm.disabled = true;          // erst nach bewusster Bestaetigung

        ack.addEventListener('change', function () {
            confirm.disabled = !ack.checked;
            log('Bestaetigung', ack.checked);
        });

        function close() {
            if (overlay.parentNode) {
                overlay.parentNode.removeChild(overlay);
            }
        }
        cancel.addEventListener('click', close);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) { close(); }   // nur Overlay
        });
        confirm.addEventListener('click', function () {
            if (confirm.disabled) { return; }        // doppelte Sicherung
            close();
            log('bestaetigt — reiche ein');
            if (typeof onConfirm === 'function') { onConfirm(); }
        });

        btns.appendChild(cancel);
        btns.appendChild(confirm);
        box.appendChild(btns);
        overlay.appendChild(box);
        (doc.body || doc.documentElement).appendChild(overlay);

        log('Dialog geoeffnet fuer', reportTitle);
        return overlay;
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        dialogTexts: dialogTexts,
        canSubmit: canSubmit,
        open: open
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.SubmitDialog = API; }
})();
