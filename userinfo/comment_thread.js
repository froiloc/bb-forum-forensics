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
 * Version: v0.6.113 · Build: 113 · 2026-05-07
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
    // Build 661 (Vorgang a84766a7): die Anmerkungen der Gegenlesenden aus den
    // Addendum-Dateien. Sie stehen in einem EIGENEN Abschnitt und werden NICHT
    // unter die Editor-Kommentare gemischt - es sind zwei Modelle mit zwei
    // Zustaendigkeiten: einen Review-Kommentar schliesst die Person ab, die
    // ihn geschrieben hat, nicht die verfassende (Konzept v0.2 \u00a74).
    const reviewBlock = _renderReviewSection(block.review_comments || []);

    if (comments.length === 0) {
        return `${reviewBlock}
                <div class="ct-empty">Noch keine Kommentare f\u00fcr diesen Block.</div>
                ${_renderComposeArea(block.block_id)}`;
    }

    const pending  = comments.filter(c => c.status === 'pending').length;
    const pendingNote = pending > 0
        ? `<div class="ct-pending-note">${pending} offene${pending === 1 ? 'r' : ''} Kommentar</div>`
        : '';

    return `${reviewBlock}${pendingNote}
            <div class="ct-list">${comments.map(cm => _renderComment(cm, block, opts)).join('')}</div>
            ${_renderComposeArea(block.block_id)}`;
}

/**
 * Rolle der kommentierenden Person in Klartext.
 * Ein unbekannter Wert wird ANGEZEIGT und nicht ersetzt (Grundregel 1) -
 * sonst verschwaende eine kuenftige Rolle hinter 'Gegenlesen'.
 */
function _reviewRole(rolle) {
    if (rolle === 'lector')     return 'Lektorat';
    if (rolle === 'supervisor') return 'Chef-Ermittlung';
    return rolle || 'Gegenlesen';
}

/**
 * Rendert den READ-ONLY-Abschnitt mit den Anmerkungen der Gegenlesenden.
 *
 * Zwei Entwurfsentscheidungen, die hier bewusst getroffen sind:
 *
 *  (1) KEINE Schaltflaeche zum Erledigen oder Verwerfen. Diese Kommentare
 *      liegen in der Datei einer ANDEREN Person; nur ihr Besitzer schreibt
 *      darin ("nie zwei Schreiber pro Datei", Konzept v0.2 \u00a74). Eine
 *      Schaltflaeche, die nichts bewirken kann, waere schlimmer als keine.
 *
 *  (2) Der Aenderungsvorschlag wird MITGEZEIGT. Er ist der eigentliche
 *      Nutzen der Gegenlese fuer die verfassende Person - ihn wegzulassen
 *      hiesse, sie muesste zum Nachlesen ins Cockpit, das sie nicht hat.
 */
function _renderReviewSection(reviewComments) {
    if (!reviewComments.length) return '';

    const offen = reviewComments.filter(c => c.status === 'pending').length;
    const kopf = offen > 0
        ? `${offen} offene Anmerkung${offen === 1 ? '' : 'en'} aus der Gegenlese`
        : 'Anmerkungen aus der Gegenlese';

    const eintraege = reviewComments.map(cm => {
        const meta = STATUS_META[cm.status] || { label: cm.status, symbol: '', cls: '' };
        const vorschlag = cm.suggested_content
            ? `<div class="ct-review-suggestion">
                 <span class="ct-review-suggestion-label">Vorschlag:</span>
                 ${_esc(cm.suggested_content)}
               </div>`
            : '';
        return `
            <div class="ct-review-comment ct-comment-${_esc(cm.status)}"
                 data-comment-id="${_esc(cm.comment_id)}">
                <div class="ct-review-head">
                    <span class="ct-review-role">${_esc(_reviewRole(cm.reviewer_role))}</span>
                    <span class="ct-status-badge ${_esc(meta.cls)}"
                          title="${_esc(meta.label)}">${meta.symbol} ${_esc(meta.label)}</span>
                    <span class="ct-review-ts">${_esc(_formatTs(cm.created_at))}</span>
                </div>
                <div class="ct-review-body">${_esc(cm.comment_text || '')}</div>
                ${vorschlag}
            </div>`;
    }).join('');

    return `<div class="ct-review-section">
                <div class="ct-review-kopf">${_esc(kopf)}</div>
                ${eintraege}
                <div class="ct-review-hinweis">Diese Anmerkungen schlie&szlig;t die
                    gegenlesende Person selbst ab.</div>
            </div>`;
}

/**
 * Rendert die Anmerkungen, die KEINEM Baustein zugeordnet werden konnten,
 * sowie die Addendum-Dateien, die nicht gelesen werden konnten.
 *
 * Warum das eine eigene Anzeige braucht (Grundregel 1): Ein Kommentar, der
 * nirgends erscheint, ist von einem nie geschriebenen nicht zu unterscheiden.
 * Und 'die Lektorin hat nichts angemerkt' sieht ohne diese Zeilen genauso aus
 * wie 'ihre Datei liess sich nicht oeffnen' - die verfassende Person gaebe
 * den Vermerk frei, ohne dass jemand die fehlende Rueckmeldung vermisst.
 */
function renderDokumentEbene(ohneBlock, fehler) {
    const posten = ohneBlock || [];
    const probleme = fehler || [];
    if (!posten.length && !probleme.length) return '';

    const zeilen = posten.map(cm => {
        const grund = cm.grund === 'block_unbekannt'
            ? 'Die Textstelle, auf die sich diese Anmerkung bezog, gibt es im '
              + 'Vermerk nicht mehr.'
            : 'Diese Anmerkung wurde ohne Textstelle geschrieben.';
        return `
            <div class="ct-review-comment ct-review-heimatlos"
                 data-comment-id="${_esc(cm.comment_id)}"
                 data-grund="${_esc(cm.grund || '')}">
                <div class="ct-review-head">
                    <span class="ct-review-role">${_esc(_reviewRole(cm.reviewer_role))}</span>
                    <span class="ct-review-grund">${_esc(grund)}</span>
                </div>
                <div class="ct-review-body">${_esc(cm.comment_text || '')}</div>
            </div>`;
    }).join('');

    const stoerung = probleme.length
        ? `<div class="ct-review-stoerung">
             ${probleme.length} Datei(en) mit Anmerkungen konnten NICHT gelesen
             werden. Es k&ouml;nnen also Anmerkungen fehlen, die hier nicht
             stehen: ${_esc(probleme.map(f => f.datei).join(', '))}
           </div>`
        : '';

    return `<div class="ct-review-section ct-review-dokument">
                <div class="ct-review-kopf">Anmerkungen zum Vermerk</div>
                ${stoerung}${zeilen}
            </div>`;
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

    // Build 661: Die Dokumentebene steht UEBER dem Block-Thread. Sie gehoert
    // nicht zum gewaehlten Baustein, muss aber sichtbar sein, solange die
    // Sidebar offen ist - sonst faende die verfassende Person eine Anmerkung
    // ohne Textstelle nie (es gibt keinen Baustein, ueber den sie dorthin
    // gelangte).
    const dok = opts && opts.reviewDokument
        ? renderDokumentEbene(opts.reviewDokument.ohneBlock,
                              opts.reviewDokument.fehler)
        : '';
    body.innerHTML = dok + renderForBlock(block, opts);
    _bindSidebarComments(body, block, opts);
    _pulseEditorBlock(blockId);
}

function _bindSidebarComments(body, block, opts) {
    body.querySelectorAll('.ct-btn-submit').forEach(btn => {
        btn.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'comment_thread', 'click:ct-btn-submit', { blockId: block?.block_id }); // B200
            _submitComment(body, btn, opts);
        });
    });

    body.querySelectorAll('[data-resolution]').forEach(btn => {
        btn.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'comment_thread', 'click:ct-resolution', { // B200
                commentId: btn.dataset.commentId, resolution: btn.dataset.resolution,
            }); // B200
            _resolveComment(parseInt(btn.dataset.commentId, 10), btn.dataset.resolution, opts);
        });
    });

    // Hover: Pulsanimation auf Editor-Block
    body.querySelectorAll('.ct-comment').forEach(el => {
        const bid = el.dataset.blockId || block.block_id;
        el.addEventListener('mouseenter', (e) => { window._uevt?.(e, 'comment_thread', 'mouseenter:ct-comment', { bid }); _pulseEditorBlock(bid); }); // B200
        el.addEventListener('focus',      (e) => { window._uevt?.(e, 'comment_thread', 'focus:ct-comment',      { bid }); _pulseEditorBlock(bid); }, true); // B200
        el.addEventListener('mouseleave', () => _clearEditorBlockPulse(bid));
        el.addEventListener('blur',       () => _clearEditorBlockPulse(bid), true);
    });
}

/** Rueckwaerts-Kompatibilitaet fuer Karten-basierte Aufrufe. */
function bindForCard(card, opts) {
    const toggle = card.querySelector('.ct-toggle');
    const bdy    = card.querySelector('.ct-body');
    if (toggle && bdy) {
        toggle.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'comment_thread', 'click:ct-toggle'); // B200
            const isOpen = bdy.style.display !== 'none';
            bdy.style.display = isOpen ? 'none' : '';
            toggle.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
        });
    }
    card.querySelectorAll('.ct-btn-submit').forEach(btn => {
        btn.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'comment_thread', 'click:ct-btn-submit-card'); // B200
            _submitComment(card, btn, opts);
        });
    });
    card.querySelectorAll('[data-resolution]').forEach(btn => {
        btn.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'comment_thread', 'click:ct-resolution-card', { // B200
                commentId: btn.dataset.commentId, resolution: btn.dataset.resolution,
            }); // B200
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
    // Build 124: Zuerst ALLE fokussierten Bloecke bereinigen (nicht nur den letzten).
    // Verhindert, dass mehrere Bloecke gleichzeitig fokussiert erscheinen.
    // Beleg: Bugfix Build 124, Projektgespraech 2026-05-08
    document.querySelectorAll('.ce-block.block-wrapper--pulse, .ce-block.block-wrapper--focus-blue')
        .forEach(el => el.classList.remove('block-wrapper--pulse', 'block-wrapper--focus-blue'));

    const wrapper = document.querySelector(`.ce-block[data-block-id="${blockId}"]`);
    if (!wrapper) return;
    if (_pulseTimer) clearTimeout(_pulseTimer);

    // Bug 2.31 Fix Build 299: Editor-Block in den sichtbaren Bereich scrollen,
    // damit beim Wechsel von Formular-Bloecken der Fokus (Scroll) im Editor
    // mitgeht. Das Formular scrollt bereits via _scrollToFocusedBlock in
    // placeholder_wizard.js; diese Seite muss den Editor-Canvas synchronisieren.
    //
    // Strategie: Pruefen ob der Block ausserhalb der mittleren 80% des
    // Eltern-Scroll-Containers (#editorjs-holder) liegt. Falls ja: scrollen.
    // 'nearest' vermeidet unnoetiges Hin- und Herspringen.
    // Beleg: Bug 2.31, Projektgespraech 2026-06-07
    const editorHolder = document.getElementById('editorjs-holder');
    if (editorHolder) {
        const holderRect  = editorHolder.getBoundingClientRect();
        const wrapperRect = wrapper.getBoundingClientRect();
        const margin      = holderRect.height * 0.1; // 10% oben/unten = 80% Mitte
        const topBound    = holderRect.top    + margin;
        const botBound    = holderRect.bottom - margin;
        if (wrapperRect.top < topBound || wrapperRect.bottom > botBound) {
            wrapper.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    _pulseTimer = setTimeout(() => {
        wrapper.classList.add('block-wrapper--focus-blue', 'block-wrapper--pulse');
    }, 10);
}

function _clearEditorBlockPulse(blockId) {
    if (!blockId) return;
    // Build 124: Bereinigt den angegebenen Block UND vorsorglich alle anderen.
    // Beleg: Bugfix Build 124, Projektgespraech 2026-05-08
    document.querySelectorAll('.ce-block.block-wrapper--pulse, .ce-block.block-wrapper--focus-blue')
        .forEach(el => el.classList.remove('block-wrapper--pulse', 'block-wrapper--focus-blue'));
    if (_pulseTimer) { clearTimeout(_pulseTimer); _pulseTimer = null; }
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
    // Build 661 (Vorgang a84766a7): Gegenlese-Anmerkungen.
    renderDokumentEbene,
    _renderReviewSection,
    _reviewRole,
};

})();
