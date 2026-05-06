/**
 * userinfo/comment_thread.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Kommentar-System fuer Paragraph-Karten in Fenster 3 (Phase 8).
 *   Beleg: Bauplan B6 v0.3 §4.3, Ausdefinitionsgespraech 2026-05-05.
 *
 *   Verhalten (§4.3):
 *     - Kommentare erscheinen als aufklappbarer Thread unter jeder Karte
 *     - Jeder Ermittler kann kommentieren (auch fremde Paragraphen)
 *     - Eigentuemer des Paragraphen kann "addressed" oder "dismissed" setzen
 *     - Kommentator selbst kann "revoked" setzen
 *     - Chef-Ermittlerin kann alle Status-Uebergaenge
 *     - Status-Uebergaenge sind One-Way (Grundregel 15)
 *     - Optionaler Formulierungsvorschlag (suggested_content)
 *
 *   Status-Badge-Darstellung:
 *     pending   -> blau  "Offen"
 *     addressed -> gruen "Bearbeitet"
 *     dismissed -> grau  "Abgelehnt"
 *     revoked   -> grau  "Zurueckgezogen"
 *
 * Exports:
 *   window.CommentThread.renderForCard(para, opts)
 *     Gibt HTML-String fuer den Kommentar-Bereich einer Karte zurueck.
 *   window.CommentThread.bindForCard(card, opts)
 *     Verdrahtet alle Event-Listener fuer die Kommentare einer Karte.
 *
 *   opts: {
 *     myUsername:  string,          -- SAMAccountName des aktuellen Nutzers
 *     isChef:      boolean,         -- Chef-Ermittlerin?
 *     postFn:      async function,  -- _postWithLock aus report.js
 *     onReload:    function,        -- nach Speichern: loadReport() aufrufen
 *   }
 *
 * Version: v0.1.0 · Build: 095 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §4.3, Ausdefinitionsgespraech 2026-05-05
 */

'use strict';

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

function _esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function _formatTs(ts) {
    if (!ts) return '';
    return new Date(ts * 1000).toLocaleString('de-DE', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
}

// Statustext und CSS-Klasse je Kommentar-Status
const STATUS_META = {
    pending:   { label: 'Offen',              cls: 'ct-status-pending'   },
    addressed: { label: 'Bearbeitet',          cls: 'ct-status-addressed' },
    dismissed: { label: 'Abgelehnt',           cls: 'ct-status-dismissed' },
    revoked:   { label: 'Zur\u00fcckgezogen', cls: 'ct-status-revoked'   },
};

// ---------------------------------------------------------------------------
// HTML rendern
// ---------------------------------------------------------------------------

/**
 * Rendert den kompletten Kommentar-Bereich fuer eine Paragraph-Karte.
 *
 * @param {Object} para -- Paragraph-Daten inkl. para.comments[]
 * @param {Object} opts
 * @returns {string} HTML
 */
function renderForCard(para, opts) {
    const comments = para.comments || [];
    const pending  = comments.filter(c => c.status === 'pending').length;
    const total    = comments.length;

    const summaryLabel = total === 0
        ? 'Kommentare (0)'
        : pending > 0
            ? `Kommentare (${total}, ${pending} offen)`
            : `Kommentare (${total})`;

    const hasPending = pending > 0;

    return `
        <div class="ct-thread" data-block-id="${_esc(para.block_id)}">
            <button class="ct-toggle ${hasPending ? 'ct-toggle-pending' : ''}"
                    aria-expanded="false"
                    data-block-id="${_esc(para.block_id)}">
                \ud83d\udcac ${_esc(summaryLabel)}
            </button>
            <div class="ct-body" style="display:none">
                <div class="ct-list">
                    ${comments.length
                        ? comments.map(cm => _renderComment(cm, para, opts)).join('')
                        : '<div class="ct-empty">Noch keine Kommentare.</div>'}
                </div>
                <div class="ct-compose">
                    <textarea class="ct-textarea"
                              placeholder="Kommentar zum Absatz verfassen\u2026"
                              rows="2"></textarea>
                    <details class="ct-suggestion-wrap">
                        <summary class="ct-suggestion-toggle">
                            Formulierungsvorschlag hinzuf\u00fcgen (optional)
                        </summary>
                        <textarea class="ct-suggestion-textarea"
                                  placeholder="Alternativer Volltext\u2026"
                                  rows="3"></textarea>
                    </details>
                    <div class="ct-compose-footer">
                        <button class="ct-btn ct-btn-primary ct-btn-submit"
                                data-block-id="${_esc(para.block_id)}">
                            Kommentar senden
                        </button>
                    </div>
                </div>
            </div>
        </div>`;
}

function _renderComment(cm, para, opts) {
    const meta    = STATUS_META[cm.status] || { label: cm.status, cls: '' };
    const isOwner = cm.author === opts.myUsername;
    const isParaOwner = para.author === opts.myUsername;
    const isPending   = cm.status === 'pending';

    // Welche Aufloesebuttons zeigen?
    const showAddressed = isPending && (isParaOwner || opts.isChef);
    const showDismissed = isPending && (isParaOwner || opts.isChef);
    const showRevoked   = isPending && isOwner;

    return `
        <div class="ct-comment ct-comment-${_esc(cm.status)}" data-comment-id="${cm.id}">
            <div class="ct-comment-header">
                <span class="ct-comment-author">${_esc(cm.author)}</span>
                <span class="ct-comment-ts">${_esc(_formatTs(cm.created_at))}</span>
                <span class="ct-status-badge ${_esc(meta.cls)}">${_esc(meta.label)}</span>
            </div>
            <div class="ct-comment-text">${_esc(cm.comment_text)}</div>
            ${cm.suggested_content ? `
                <div class="ct-suggestion">
                    <span class="ct-suggestion-label">Vorschlag:</span>
                    <div class="ct-suggestion-text">${_esc(cm.suggested_content)}</div>
                </div>` : ''}
            ${isPending ? `
                <div class="ct-comment-actions">
                    ${showAddressed ? `<button class="ct-btn ct-btn-resolve"
                        data-comment-id="${cm.id}" data-resolution="addressed">
                        \u2713 Bearbeitet</button>` : ''}
                    ${showDismissed ? `<button class="ct-btn ct-btn-dismiss"
                        data-comment-id="${cm.id}" data-resolution="dismissed">
                        \u2715 Ablehnen</button>` : ''}
                    ${showRevoked ? `<button class="ct-btn ct-btn-revoke"
                        data-comment-id="${cm.id}" data-resolution="revoked">
                        \u21a9 Zur\u00fcckziehen</button>` : ''}
                </div>` : ''}
            ${cm.resolved_by ? `
                <div class="ct-resolved-by">
                    ${_esc(meta.label)} von ${_esc(cm.resolved_by)}
                    ${cm.resolved_at ? ' am ' + _esc(_formatTs(cm.resolved_at)) : ''}
                </div>` : ''}
        </div>`;
}

// ---------------------------------------------------------------------------
// Event-Binding
// ---------------------------------------------------------------------------

/**
 * Verdrahtet alle Event-Listener fuer den Kommentar-Bereich einer Karte.
 * Muss nach jedem _render() / _renderParagraphList() aufgerufen werden.
 *
 * @param {HTMLElement} card  -- .report-paragraph-card
 * @param {Object}      opts
 */
function bindForCard(card, opts) {
    // Aufklapp-Button
    const toggle = card.querySelector('.ct-toggle');
    const body   = card.querySelector('.ct-body');
    if (toggle && body) {
        toggle.addEventListener('click', () => {
            const isOpen = body.style.display !== 'none';
            body.style.display = isOpen ? 'none' : '';
            toggle.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
        });
    }

    // Kommentar senden
    card.querySelectorAll('.ct-btn-submit').forEach(btn => {
        btn.addEventListener('click', () => _submitComment(card, btn, opts));
    });

    // Aufloesebuttons (addressed / dismissed / revoked)
    card.querySelectorAll('[data-resolution]').forEach(btn => {
        btn.addEventListener('click', () => {
            _resolveComment(
                parseInt(btn.dataset.commentId, 10),
                btn.dataset.resolution,
                opts
            );
        });
    });
}

// ---------------------------------------------------------------------------
// Serveraktionen
// ---------------------------------------------------------------------------

async function _submitComment(card, btn, opts) {
    const blockId   = btn.dataset.blockId;
    const textarea  = card.querySelector('.ct-textarea');
    const suggested = card.querySelector('.ct-suggestion-textarea');
    const text      = textarea?.value?.trim() ?? '';

    if (!text) {
        textarea?.classList.add('ct-input-error');
        setTimeout(() => textarea?.classList.remove('ct-input-error'), 2000);
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Wird gesendet\u2026';

    try {
        // Kommentare brauchen KEINEN Lock (§4.3: "Kommentar immer moeglich")
        const resp = await fetch('/_forensic/report', {
            method:  'POST',
            headers: {
                'Content-Type':       'application/json',
                'X-Forensic-Request': 'ajax',
            },
            body: JSON.stringify({
                action:            'add_comment',
                block_id:          blockId,
                comment_text:      text,
                suggested_content: suggested?.value?.trim() || null,
            }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error ?? resp.status);

        // Felder leeren
        if (textarea)  textarea.value  = '';
        if (suggested) suggested.value = '';

        opts.onReload();

    } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Kommentar senden';
        // Fehlermeldung im Thread anzeigen
        const errEl = document.createElement('div');
        errEl.className = 'ct-send-error';
        errEl.textContent = 'Fehler: ' + String(err);
        card.querySelector('.ct-compose-footer')?.prepend(errEl);
        setTimeout(() => errEl.remove(), 4000);
    }
}

async function _resolveComment(commentId, resolution, opts) {
    try {
        const lockId = window.EditorState?.lockId ?? null;
        const resp   = await fetch('/_forensic/report', {
            method:  'POST',
            headers: {
                'Content-Type':       'application/json',
                'X-Forensic-Request': 'ajax',
                ...(lockId ? { 'X-Forensic-Lock-Id': lockId } : {}),
            },
            body: JSON.stringify({
                action:     'resolve_comment',
                comment_id: commentId,
                resolution,
                lock_id:    lockId,
                is_chef:    opts.isChef,
            }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error ?? resp.status);
        opts.onReload();
    } catch (err) {
        // Kurze Fehlermeldung in die Konsole — kein modaler Dialog
        console.error('resolve_comment fehlgeschlagen:', err);
    }
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

window.CommentThread = {
    renderForCard,
    bindForCard,
    // Interna fuer Tests
    _renderComment,
    _formatTs,
};
