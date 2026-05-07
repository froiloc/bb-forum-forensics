/**
 * userinfo/comment_thread.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Kommentar-Thread fuer den Kommentar-Akkordeon-Abschnitt der Support-Sidebar.
 *   Integriert in #support-sidebar[data-accordion="comments"] (B6 Phase 3/4).
 *   Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06.
 *
 *   Verhalten (§4.4.4):
 *     - Zeigt den Kommentar-Thread des aktuell fokussierten Blocks.
 *     - Leer-Zustand: "Kein Block ausgewaehlt." / "Noch keine Kommentare."
 *     - Kommentar verfassen: Textarea + optionaler Formulierungsvorschlag.
 *     - Status-Symbole: pending (⁉), addressed (👍), dismissed (👎), revoked (↩)
 *       Hinweis zu ⮐ (U+2BB0): Kompatibilitaet mit Firefox ESR noch zu pruefen
 *       (OP-B6-7). Fallback ↩ (U+21A9) wird vorerst verwendet.
 *       Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06.
 *     - Blauer Fokus-Rahmen + Pulsanimation auf Editor-Block beim Hover.
 *     - Status-Uebergaenge sind One-Way (Grundregel 15).
 *     - Kommentieren braucht kein Lock (Grundregel: immer moeglich).
 *     - addressed/dismissed: Lock erforderlich (wird serverseitig geprueft).
 *
 * Exports:
 *   window.CommentThread.renderForBlock(block, opts)
 *   window.CommentThread.renderForCard(para, opts)   [Rueckwaerts-Kompatibilitaet]
 *   window.CommentThread.showForBlock(blockId, blocks, opts)
 *   window.CommentThread.bindForCard(card, opts)     [Rueckwaerts-Kompatibilitaet]
 *   window.CommentThread._renderComment(cm, block, opts)  [Tests]
 *   window.CommentThread._formatTs(ts)                    [Tests]
 *   window.CommentThread._pulseEditorBlock(blockId)       [Tests]
 *   window.CommentThread._clearEditorBlockPulse(blockId)  [Tests]
 *
 * Changelog:
 *   Build 095: Erstimplementierung (Karten-basiert, Phase 8-Stub).
 *   Build 102 (B6 Phase 4): Auf Support-Sidebar-Integration umgestellt.
 *     showForBlock() fuer direktes Rendern in #accordion-body-comments.
 *     Blauer Fokus-Rahmen + Pulsanimation gemaess §4.4.4.
 *     Status-Symbole gemaess Bauplan §4.4.4 (OP-B6-7 offen).
 *     Rueckwaerts-Kompatibilitaet erhalten.
 *     Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06.
 *
 * Version: v0.6.112 · Build: 112 · 2026-05-07
 */

(function() {
'use strict';

// ---------------------------------------------------------------------------
// DEV-Logging (Build 110: systematisches Debug-Logging eingefuehrt)
// Ueber window.FORENSIC_DEBUG = false in der Browser-Console abschaltbar.
// Beleg: Projektgespraech 2026-05-07
// ---------------------------------------------------------------------------
/** @param {...*} args */
function _dbg(...args) {
    if (window.FORENSIC_DEBUG !== false) {
        console.debug('[forensic]', ...args);
    }
}


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

// ---------------------------------------------------------------------------
// Konstanten
// ---------------------------------------------------------------------------

// Status-Metadaten gemaess Bauplan B6 v0.5 §4.4.4.
// Symbole: ⁉ (U+2049, pending), 👍 (addressed), 👎 (dismissed), ↩ (revoked).
// OP-B6-7: ⮐ (U+2BB0) noch nicht gegen Firefox ESR geprueft — Fallback ↩.
// Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
const STATUS_META = {
    pending:   { label: 'Offen',              symbol: '\u2049',         cls: 'ct-status-pending'   },
    addressed: { label: 'Bearbeitet',          symbol: '\uD83D\uDC4D',   cls: 'ct-status-addressed' },
    dismissed: { label: 'Abgelehnt',           symbol: '\uD83D\uDC4E',   cls: 'ct-status-dismissed' },
    revoked:   { label: 'Zur\u00fcckgezogen',  symbol: '\u21a9',         cls: 'ct-status-revoked'   },
};

// ---------------------------------------------------------------------------
// Rendern — Sidebar-Version
// ---------------------------------------------------------------------------

/**
 * Rendert den Kommentar-Thread fuer einen Block.
 * Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
 */
function renderForBlock(block, opts) {
    const comments = block.comments || [];

    if (comments.length === 0) {
        return `<div class="ct-empty">Noch keine Kommentare f\u00fcr diesen Block.</div>
                ${_renderComposeArea(block.block_id)}`;
    }

    const pending  = comments.filter(c => c.status === 'pending').length;
    const pendingNote = pending > 0
        ? `<div class="ct-pending-note">${pending} offene${pending === 1 ? 'r' : ''} Kommentar</div>`
        : '';

    return `${pendingNote}
            <div class="ct-list">${comments.map(cm => _renderComment(cm, block, opts)).join('')}</div>
            ${_renderComposeArea(block.block_id)}`;
}

/** Rueckwaerts-Kompatibilitaet. */
function renderForCard(para, opts) { return renderForBlock(para, opts); }

/**
 * Rendert einen einzelnen Kommentar.
 * Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
 */
function _renderComment(cm, block, opts) {
    const meta         = STATUS_META[cm.status] || { label: cm.status, symbol: '', cls: '' };
    const isAuthor     = cm.author === opts.myUsername;
    const isBlockOwner = block.author === opts.myUsername;
    const isPending    = cm.status === 'pending';

    const showAddressed = isPending && (isBlockOwner || opts.isChef);
    const showDismissed = isPending && (isBlockOwner || opts.isChef);
    const showRevoked   = isPending && isAuthor;

    const resolvedInfo = cm.resolved_by
        ? `<div class="ct-resolved-by">
               ${_esc(meta.label)} von ${_esc(cm.resolved_by)}
               ${cm.resolved_at ? ' \u00b7 ' + _esc(_formatTs(cm.resolved_at)) : ''}
           </div>`
        : '';

    const suggestion = cm.suggested_content
        ? `<div class="ct-suggestion">
               <span class="ct-suggestion-label">Vorschlag:</span>
               <div class="ct-suggestion-text">${_esc(cm.suggested_content)}</div>
           </div>`
        : '';

    const actions = isPending && (showAddressed || showDismissed || showRevoked)
        ? `<div class="ct-comment-actions">
               ${showAddressed ? `<button class="ct-btn ct-btn-resolve" type="button"
                   data-comment-id="${cm.id}" data-resolution="addressed"
                   aria-label="Als bearbeitet markieren">\u2713 Bearbeitet</button>` : ''}
               ${showDismissed ? `<button class="ct-btn ct-btn-dismiss" type="button"
                   data-comment-id="${cm.id}" data-resolution="dismissed"
                   aria-label="Kommentar ablehnen">\u2715 Ablehnen</button>` : ''}
               ${showRevoked ? `<button class="ct-btn ct-btn-revoke" type="button"
                   data-comment-id="${cm.id}" data-resolution="revoked"
                   aria-label="Kommentar zur\u00fcckziehen">\u21a9 Zur\u00fcckziehen</button>` : ''}
           </div>`
        : '';

    return `
        <div class="ct-comment ct-comment-${_esc(cm.status)}"
             data-comment-id="${cm.id}"
             data-block-id="${_esc(block.block_id ?? '')}"
             tabindex="0"
             aria-label="Kommentar von ${_esc(cm.author)}">
            <div class="ct-comment-header">
                <span class="ct-status-badge ${_esc(meta.cls)}"
                      title="${_esc(meta.label)}">${_esc(meta.symbol)}</span>
                <span class="ct-comment-author">${_esc(cm.author)}</span>
                <span class="ct-comment-ts">${_esc(_formatTs(cm.created_at))}</span>
            </div>
            <div class="ct-comment-text">${_esc(cm.comment_text)}</div>
            ${suggestion}
            ${actions}
            ${resolvedInfo}
        </div>`;
}

function _renderComposeArea(blockId) {
    return `
        <div class="ct-compose" data-block-id="${_esc(blockId)}">
            <textarea class="ct-textarea comment-input-textarea"
                      placeholder="Kommentar verfassen\u2026"
                      rows="3"
                      aria-label="Neuen Kommentar verfassen"></textarea>
            <details class="ct-suggestion-wrap">
                <summary class="ct-suggestion-toggle">
                    Formulierungsvorschlag hinzuf\u00fcgen (optional)
                </summary>
                <textarea class="ct-suggestion-textarea"
                          placeholder="Alternativer Volltext\u2026"
                          rows="3"
                          aria-label="Formulierungsvorschlag"></textarea>
            </details>
            <div class="ct-compose-footer">
                <button class="ct-btn ct-btn-primary ct-btn-submit"
                        type="button"
                        data-block-id="${_esc(blockId)}"
                        aria-label="Kommentar senden">
                    Kommentar senden
                </button>
            </div>
        </div>`;
}

// ---------------------------------------------------------------------------
// Support-Sidebar-Integration (Phase 4)
// ---------------------------------------------------------------------------

/**
 * Rendert den Kommentar-Thread fuer blockId direkt in #accordion-body-comments.
 * Haupteinstiegspunkt fuer report_editor.js._openCommentAccordion().
 * Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
 */
function showForBlock(blockId, blocks, opts) {
    const body = document.getElementById('accordion-body-comments');
    if (!body) return;

    const block = (blocks || []).find(b => b.block_id === blockId);

    if (!block) {
        body.innerHTML = '<p class="ct-empty" id="comments-empty-state">Kein Block ausgew\u00e4hlt.</p>';
        return;
    }

    body.innerHTML = renderForBlock(block, opts);
    _bindSidebarComments(body, block, opts);
    _pulseEditorBlock(blockId);
}

function _bindSidebarComments(body, block, opts) {
    body.querySelectorAll('.ct-btn-submit').forEach(btn => {
        btn.addEventListener('click', () => _submitComment(body, btn, opts));
    });

    body.querySelectorAll('[data-resolution]').forEach(btn => {
        btn.addEventListener('click', () => {
            _resolveComment(parseInt(btn.dataset.commentId, 10), btn.dataset.resolution, opts);
        });
    });

    // Hover: Pulsanimation auf Editor-Block
    body.querySelectorAll('.ct-comment').forEach(el => {
        const bid = el.dataset.blockId || block.block_id;
        el.addEventListener('mouseenter', () => _pulseEditorBlock(bid));
        el.addEventListener('focus',      () => _pulseEditorBlock(bid), true);
        el.addEventListener('mouseleave', () => _clearEditorBlockPulse(bid));
        el.addEventListener('blur',       () => _clearEditorBlockPulse(bid), true);
    });
}

/** Rueckwaerts-Kompatibilitaet fuer Karten-basierte Aufrufe. */
function bindForCard(card, opts) {
    const toggle = card.querySelector('.ct-toggle');
    const bdy    = card.querySelector('.ct-body');
    if (toggle && bdy) {
        toggle.addEventListener('click', () => {
            const isOpen = bdy.style.display !== 'none';
            bdy.style.display = isOpen ? 'none' : '';
            toggle.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
        });
    }
    card.querySelectorAll('.ct-btn-submit').forEach(btn => {
        btn.addEventListener('click', () => _submitComment(card, btn, opts));
    });
    card.querySelectorAll('[data-resolution]').forEach(btn => {
        btn.addEventListener('click', () => {
            _resolveComment(parseInt(btn.dataset.commentId, 10), btn.dataset.resolution, opts);
        });
    });
}

// ---------------------------------------------------------------------------
// Pulsanimation (§4.4.4)
// ---------------------------------------------------------------------------

let _pulseTimer = null;

/**
 * Setzt blauen box-shadow auf Block-Wrapper und pulsiert 2-3x.
 * Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
 */
function _pulseEditorBlock(blockId) {
    if (!blockId) return;
    const wrapper = document.querySelector(`.block-wrapper[data-block-id="${blockId}"]`);
    if (!wrapper) return;
    wrapper.classList.remove('block-wrapper--pulse', 'block-wrapper--focus-blue');
    if (_pulseTimer) clearTimeout(_pulseTimer);
    _pulseTimer = setTimeout(() => {
        wrapper.classList.add('block-wrapper--focus-blue', 'block-wrapper--pulse');
    }, 10);
}

function _clearEditorBlockPulse(blockId) {
    if (!blockId) return;
    const wrapper = document.querySelector(`.block-wrapper[data-block-id="${blockId}"]`);
    if (!wrapper) return;
    wrapper.classList.remove('block-wrapper--pulse', 'block-wrapper--focus-blue');
}

// ---------------------------------------------------------------------------
// Serveraktionen
// ---------------------------------------------------------------------------

async function _submitComment(container, btn, opts) {
    const blockId   = btn.dataset.blockId;
    const textarea  = container.querySelector('.ct-textarea');
    const suggested = container.querySelector('.ct-suggestion-textarea');
    const text      = textarea?.value?.trim() ?? '';

    if (!text) {
        textarea?.classList.add('ct-input-error');
        setTimeout(() => textarea?.classList.remove('ct-input-error'), 2000);
        return;
    }

    const origText  = btn.textContent;
    btn.disabled    = true;
    btn.textContent = 'Wird gesendet\u2026';

    try {
        const resp = await fetch('/_forensic/report', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-Forensic-Request': 'ajax' },
            body: JSON.stringify({
                action:            'add_comment',
                block_id:          blockId,
                comment_text:      text,
                suggested_content: suggested?.value?.trim() || null,
            }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error ?? String(resp.status));
        if (textarea)  textarea.value  = '';
        if (suggested) suggested.value = '';
        opts.onReload();
    } catch (err) {
        btn.disabled    = false;
        btn.textContent = origText;
        const errEl     = document.createElement('div');
        errEl.className = 'ct-send-error';
        errEl.textContent = 'Fehler: ' + String(err);
        container.querySelector('.ct-compose-footer')?.prepend(errEl);
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
            body: JSON.stringify({ action: 'resolve_comment', comment_id: commentId, resolution }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error ?? String(resp.status));
        opts.onReload();
    } catch (err) {
        console.error('resolve_comment fehlgeschlagen:', err);
    }
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

window.CommentThread = {
    renderForBlock,
    renderForCard,
    showForBlock,
    bindForCard,
    _renderComment,
    _formatTs,
    _pulseEditorBlock,
    _clearEditorBlockPulse,
};

})();
