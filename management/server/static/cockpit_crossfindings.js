// =============================================================================
// management/server/static/cockpit_crossfindings.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Querfunde (AP-2A)
// =============================================================================
// Zweck (Idee 6, Frontend zu Build 474):
//   REIN LESENDE Meta-Uebersicht der Querfunde ("Fund ueber B im Fall A") aus
//   GET /api/crossfindings. Zeigt je Fund: Ziel-Subjekt (subject_id), Quell-
//   Ermittler, Status (offen/integriert), Zeiten. Erfassung + Transport laufen
//   AUTOMATISCH (forensic_api) — hier wird NICHTS geschrieben.
//
// Datenform GET /api/crossfindings (ManagementApp._crossfindings):
//   { findings: [ {id, subject_id, source_iid, source_name, has_case,
//                  annotation_local_id, db_path, created_at, integrated_at,
//                  status}, ... ],
//     counts: { total, offen, integriert } }
//   Bei fehlendem Substrat liefert der Endpunkt 503; loadCrossfindings reicht
//   das als {error: <text>} an renderCrossfindings weiter.
//
// GRUNDREGEL 1 (kein stiller Leerbefund): Ein 503/Fehler zeigt „Uebersicht
//   derzeit nicht verfuegbar" — NICHT eine leere Liste, die faelschlich „keine
//   Querfunde" suggerierte. Ein echter Leerbefund (Substrat da, 0 Funde) zeigt
//   dagegen bewusst „Keine Querfunde".
//
// KEIN SSE-REFRESH (bewusst): Querfunde entstehen ueber die automatische
//   forensic_api-Pipeline (pending_cross_annotations), NICHT ueber den
//   coordinator-audit_log. Der SSE-Strom triggert auf Audit-Ereignisse und
//   wuerde fuer neue Querfunde nicht feuern — ein SSE-Refresh waere irrefuehrend.
//   Deshalb ein expliziter „Aktualisieren"-Knopf.
//
// KAPSELUNG / GEBOTE: IIFE + 'use strict'; DEV-Logging; ausfuehrliche
//   Kommentare; reine Helfer ohne DOM (vitest); UMD-Export. XSS: textContent.
//
// Version: v0.8.478 · Build: 478 · 2026-07-21
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
        args.unshift('[AIW-Querfunde]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';

    // ------------------------------------------------------------------ Helfer
    // (rein — kein DOM, damit unter vitest direkt pruefbar)

    function statusLabel(code) {
        if (code === 'integriert') { return 'integriert'; }
        if (code === 'offen') { return 'offen'; }
        return String(code == null ? '' : code);
    }
    function statusClass(code) {
        if (code === 'integriert') { return 'aiw-cf-integriert'; }
        if (code === 'offen') { return 'aiw-cf-offen'; }
        return 'aiw-cf-unbekannt';
    }

    // findings: robuste Extraktion der Listenform.
    function findings(data) {
        return (data && Array.isArray(data.findings)) ? data.findings : [];
    }

    // fmtTs: Epoch-Sekunden -> lokal lesbar; 0/None -> Gedankenstrich.
    function fmtTs(epoch) {
        var n = parseInt(epoch, 10);
        if (!n || isNaN(n)) { return EM_DASH; }
        try {
            return new Date(n * 1000).toLocaleString();
        } catch (e) {
            return String(epoch);
        }
    }

    // =========================================================================
    // DOM: Sicht rendern. data = {findings, counts} ODER {error: <text>}.
    // =========================================================================
    function renderCrossfindings(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return; }
        data = data || {};
        var onlyOpen = opts.onlyOpen === true;

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Querfunde — fallübergreifende Funde';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Funde über ein anderes Subjekt (B), die bei der '
            + 'Ermittlung im Fall A entstanden sind. Erfassung und Transport '
            + 'laufen automatisch — diese Sicht ist rein lesend.';
        mainEl.appendChild(sub);

        // --- Steuerleiste: „nur offene" + Aktualisieren ----------------------
        mainEl.appendChild(_controls(doc, onlyOpen, opts));

        // --- Fehler-/Nichtverfuegbar-Zustand (Grundregel 1) ------------------
        if (data.error) {
            var err = doc.createElement('div');
            err.className = 'aiw-cf-result error';
            err.textContent = 'Übersicht derzeit nicht verfügbar: '
                + data.error;
            mainEl.appendChild(err);
            log('renderCrossfindings: Fehlerzustand', data.error);
            return;
        }

        // --- counts-Kopf -----------------------------------------------------
        var counts = data.counts
            || { total: 0, offen: 0, integriert: 0 };
        var head = doc.createElement('div');
        head.className = 'aiw-cf-counts';
        head.textContent = 'offen: ' + (counts.offen || 0)
            + '  ·  integriert: ' + (counts.integriert || 0)
            + '  ·  gesamt: ' + (counts.total || 0);
        mainEl.appendChild(head);

        // --- Tabelle / echter Leerbefund -------------------------------------
        var rows = findings(data);
        if (rows.length === 0) {
            var empty = doc.createElement('p');
            empty.className = 'aiw-placeholder';
            empty.textContent = onlyOpen
                ? 'Keine offenen Querfunde.'
                : 'Keine Querfunde.';
            mainEl.appendChild(empty);
            log('renderCrossfindings: 0 Funde (onlyOpen', onlyOpen, ')');
            return;
        }

        var table = doc.createElement('table');
        table.className = 'aiw-cf-table';
        var thead = doc.createElement('thead');
        var htr = doc.createElement('tr');
        ['subject_id', 'Quell-Ermittler', 'Status', 'angelegt', 'integriert']
            .forEach(function (label) {
                var th = doc.createElement('th');
                th.textContent = label;
                htr.appendChild(th);
            });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = doc.createElement('tbody');
        rows.forEach(function (f) {
            tbody.appendChild(_rowEl(doc, f));
        });
        table.appendChild(tbody);
        mainEl.appendChild(table);

        log('renderCrossfindings:', rows.length, 'Funde (onlyOpen', onlyOpen,
            ')');
    }

    // _controls: „nur offene"-Umschalter + Aktualisieren. Beide loesen
    // opts.onReload(onlyOpen) aus (cockpit.js laedt neu).
    function _controls(doc, onlyOpen, opts) {
        var bar = doc.createElement('div');
        bar.className = 'aiw-cf-controls';

        var lbl = doc.createElement('label');
        lbl.className = 'aiw-cf-lbl';
        var cb = doc.createElement('input');
        cb.type = 'checkbox';
        cb.id = 'aiw-cf-onlyopen';
        cb.checked = onlyOpen;
        cb.addEventListener('change', function () {
            if (typeof opts.onReload === 'function') {
                opts.onReload(cb.checked === true);
            }
        });
        lbl.appendChild(cb);
        lbl.appendChild(doc.createTextNode(' nur offene'));
        bar.appendChild(lbl);

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-cf-refresh';
        btn.className = 'aiw-btn aiw-cf-btn';
        btn.textContent = 'Aktualisieren';
        btn.addEventListener('click', function () {
            if (typeof opts.onReload === 'function') {
                opts.onReload(onlyOpen);
            }
        });
        bar.appendChild(btn);
        return bar;
    }

    // _rowEl: eine Querfund-Zeile.
    function _rowEl(doc, f) {
        var tr = doc.createElement('tr');
        tr.setAttribute('data-subject', String(f.subject_id));

        var tdSid = doc.createElement('td');
        tdSid.textContent = String(f.subject_id);
        tr.appendChild(tdSid);

        var tdSrc = doc.createElement('td');
        // source_name kann null sein (Ermittler nicht zuordenbar) — dann die
        // rohe iid zeigen, damit die Zeile nicht bedeutungslos wird
        // (Grundregel 1: sichtbar bleiben statt verschlucken).
        tdSrc.textContent = f.source_name
            || ('iid ' + (f.source_iid == null ? EM_DASH : f.source_iid));
        tr.appendChild(tdSrc);

        var tdStatus = doc.createElement('td');
        var badge = doc.createElement('span');
        badge.className = 'aiw-badge aiw-cf-badge ' + statusClass(f.status);
        badge.textContent = statusLabel(f.status);
        tdStatus.appendChild(badge);
        tr.appendChild(tdStatus);

        var tdCreated = doc.createElement('td');
        tdCreated.textContent = fmtTs(f.created_at);
        tr.appendChild(tdCreated);

        var tdInteg = doc.createElement('td');
        tdInteg.textContent = (f.integrated_at != null)
            ? fmtTs(f.integrated_at) : EM_DASH;
        tr.appendChild(tdInteg);

        return tr;
    }

    // =========================================================================
    // UMD-Ausgang.
    // =========================================================================
    var API = {
        statusLabel: statusLabel,
        statusClass: statusClass,
        findings: findings,
        fmtTs: fmtTs,
        renderCrossfindings: renderCrossfindings
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitCrossfindings = API; }
})();
