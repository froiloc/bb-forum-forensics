// =============================================================================
// management/server/static/cockpit_integrity.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Integritaet/Ops
// =============================================================================
// Zweck:
//   Rendert die Integritaets-/Ops-Sicht (/api/integrity) und liefert das Modell
//   fuer den globalen Ketten-Banner. Der auditierte, hash-verkettete audit_log
//   ist das forensische Rueckgrat; seine Unversehrtheit muss fuer die
//   Ermittelnden JEDERZEIT sichtbar sein (Beleg: Bauplan B7 v1.1 §11.1/§11.2;
//   Grundprinzip "append-only, hash-chained audit_log").
//
// Datenform /api/integrity (Backend ManagementApp._integrity, Build 346):
//   { ok: bool, first_bad_seq: int|null, detail: str, tip_seq: int }
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE-Wrapper mit 'use strict'.
//   2) DEV-Debug-Logging, zur Laufzeit umschaltbar (Build 349).
//   3) Ausfuehrliche Kommentare.
//   4) Reine Funktionen fassen NIE das DOM an; UMD-Ausgang -> vitest testet
//      den ECHTEN Code.
//
// SICHERHEIT (XSS): 'detail' ist server-generiert; dennoch grundsaetzlich via
//   textContent gesetzt (nie innerHTML mit variablem Text).
//
// Version: v0.7.349 · Build: 349 · 2026-07-10
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
        args.unshift('[AIW-Integrity]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '\u2014';

    // =========================================================================
    // 1) REINE FUNKTION: Banner-Modell aus der Integritaets-Antwort.
    //    ok    -> gruen: "Kette intakt bis Sequenz N."
    //    !ok   -> rot:   "KETTENBRUCH ab Sequenz M." (first_bad_seq; fehlt er,
    //             wird das nicht still verschluckt, sondern als '?' markiert).
    // =========================================================================
    function bannerModel(data) {
        data = data || {};
        if (data.ok) {
            return {
                klass: 'ok',
                text: 'Integritaet: Kette intakt bis Sequenz '
                    + (data.tip_seq != null ? data.tip_seq : '?') + '.'
            };
        }
        var bad = (data.first_bad_seq != null) ? data.first_bad_seq : '?';
        return {
            klass: 'fehler',
            text: 'Integritaet: KETTENBRUCH ab Sequenz ' + bad + '!'
        };
    }

    // =========================================================================
    // 2) DOM: Banner setzen + Sicht rendern.
    // =========================================================================

    // applyBanner: Banner-Element gemaess Modell setzen. Setzt die Klasse
    // vollstaendig (entfernt damit auch 'aiw-integrity-hidden') und den Text
    // via textContent.
    function applyBanner(bannerEl, model) {
        if (!bannerEl || !model) { return; }
        bannerEl.className = 'aiw-integrity ' + model.klass;
        bannerEl.textContent = model.text;
    }

    // renderIntegrity: Detailsicht (Karte) mit Status, Ketten-Spitze, erstem
    // Bruch und Detailtext.
    function renderIntegrity(mainEl, data) {
        if (!mainEl) { return; }
        data = data || {};
        mainEl.textContent = '';

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Integritaet / Betrieb';
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Unversehrtheit der auditierten, hash-verketteten '
            + 'Ereigniskette (audit_log).';
        mainEl.appendChild(sub);

        var card = document.createElement('div');
        card.className = 'aiw-card';

        // Status-Zeile mit Ampelpunkt.
        var statusRow = document.createElement('h3');
        var dot = document.createElement('span');
        dot.className = 'dot ' + (data.ok ? 'gruen' : 'rot');
        statusRow.appendChild(dot);
        var statusTxt = document.createElement('span');
        statusTxt.textContent = data.ok
            ? ' Status: Kette intakt' : ' Status: KETTENBRUCH';
        statusRow.appendChild(statusTxt);
        card.appendChild(statusRow);

        card.appendChild(_kv('Ketten-Spitze (tip_seq)',
            data.tip_seq != null ? String(data.tip_seq) : EM_DASH));
        card.appendChild(_kv('Erster fehlerhafter Sequenz-Punkt',
            data.first_bad_seq != null ? String(data.first_bad_seq) : EM_DASH));
        card.appendChild(_kv('Detail', data.detail || EM_DASH));

        mainEl.appendChild(card);
        log('renderIntegrity: ok =', !!data.ok, 'tip', data.tip_seq);
    }

    // _kv: kleine "Label: Wert"-Zeile (Wert via textContent, XSS-sicher).
    function _kv(label, value) {
        var p = document.createElement('p');
        var b = document.createElement('strong');
        b.textContent = label + ': ';
        p.appendChild(b);
        var span = document.createElement('span');
        span.textContent = value;
        p.appendChild(span);
        return p;
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        bannerModel: bannerModel,
        applyBanner: applyBanner,
        renderIntegrity: renderIntegrity
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitIntegrity = API; }
})();
