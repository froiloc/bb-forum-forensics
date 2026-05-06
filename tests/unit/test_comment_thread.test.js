/**
 * tests/unit/test_comment_thread.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer userinfo/comment_thread.js
 *
 * T01 -- CommentThread ist nach dem Laden verfuegbar
 * T02 -- renderForCard(): leere Kommentarliste -> "(0)" im Toggle
 * T03 -- renderForCard(): offene Kommentare -> Anzahl und "offen" im Toggle
 * T04 -- renderForCard(): alle erledigten -> nur Anzahl, kein "offen"
 * T05 -- renderForCard(): Toggle hat ct-toggle-pending bei offenen Kommentaren
 * T06 -- _renderComment(): Kommentartext wird angezeigt
 * T07 -- _renderComment(): Status-Badge "Offen" bei pending
 * T08 -- _renderComment(): Status-Badge "Bearbeitet" bei addressed
 * T09 -- _renderComment(): Formulierungsvorschlag wird angezeigt wenn vorhanden
 * T10 -- _renderComment(): XSS-Schutz im Kommentartext
 * T11 -- _renderComment(): Aufloesebuttons nur fuer pending sichtbar
 * T12 -- _renderComment(): Eigentuemer sieht "Zurueckziehen"-Button
 * T13 -- _renderComment(): Para-Eigentuemer sieht "Bearbeitet"-Button
 * T14 -- _renderComment(): Fremder Ermittler sieht keine Aktionsbuttons
 * T15 -- _renderComment(): Chef sieht alle Aktionsbuttons
 * T16 -- _formatTs(): null -> leerer String
 * T17 -- renderForBlock(): renderForCard als Alias vorhanden
 * T18 -- renderForBlock(): gibt HTML fuer leere Kommentarliste
 * T19 -- _renderComment(): Status-Symbol fuer pending ist ⁉
 * T20 -- _renderComment(): Status-Symbol fuer addressed
 * T21 -- showForBlock: Leer-Zustand bei unbekanntem blockId
 * T22 -- _pulseEditorBlock/clearEditorBlockPulse exportiert
 *
 * Version: v0.6.102 · Build: 102 · 2026-05-06
 * Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import '../../userinfo/comment_thread.js';

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

function _mkComment(overrides = {}) {
    return {
        id:               1,
        author:           'h002',
        created_at:       1700000000,
        comment_text:     'Bitte ueberarbeiten.',
        suggested_content: null,
        status:           'pending',
        resolved_by:      null,
        resolved_at:      null,
        ...overrides,
    };
}

function _mkPara(comments = [], overrides = {}) {
    return {
        block_id:  'blk-001',
        author:    'h001',
        comments,
        ...overrides,
    };
}

const _baseOpts = {
    myUsername: 'h001',
    isChef:     false,
    postFn:     async () => ({}),
    onReload:   () => {},
};

// ---------------------------------------------------------------------------
// T01: API-Verfuegbarkeit
// ---------------------------------------------------------------------------

describe('CommentThread API', () => {
    it('T01: CommentThread ist nach dem Laden verfuegbar', () => {
        expect(window.CommentThread).toBeDefined();
        expect(typeof window.CommentThread.renderForCard).toBe('function');
        expect(typeof window.CommentThread.bindForCard).toBe('function');
        expect(typeof window.CommentThread._renderComment).toBe('function');
        expect(typeof window.CommentThread._formatTs).toBe('function');
    });
});

// ---------------------------------------------------------------------------
// T02-T05: renderForCard()
// ---------------------------------------------------------------------------

describe('renderForCard()', () => {

    it('T02: leere Kommentarliste -> Leer-Zustand und Eingabefeld', () => {
        // Neues Sidebar-Modell: kein Toggle-Button, stattdessen ct-empty + ct-compose
        // Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
        const html = window.CommentThread.renderForCard(_mkPara([]), _baseOpts);
        expect(html).toContain('ct-empty');
        expect(html).toContain('ct-compose');
    });

    it('T03: offene Kommentare -> ct-pending-note und ct-list', () => {
        // Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
        const html = window.CommentThread.renderForCard(
            _mkPara([_mkComment(), _mkComment({ id: 2 })]),
            _baseOpts
        );
        expect(html).toContain('ct-pending-note');
        expect(html).toContain('ct-list');
        expect(html).toContain('offene');
    });

    it('T04: nur erledigte Kommentare -> kein ct-pending-note', () => {
        // Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
        const html = window.CommentThread.renderForCard(
            _mkPara([_mkComment({ status: 'addressed' })]),
            _baseOpts
        );
        expect(html).not.toContain('ct-pending-note');
        expect(html).toContain('ct-list');
    });

    it('T05: offene Kommentare -> ct-pending-note vorhanden', () => {
        // Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
        const html = window.CommentThread.renderForCard(
            _mkPara([_mkComment()]),
            _baseOpts
        );
        expect(html).toContain('ct-pending-note');
    });
});

// ---------------------------------------------------------------------------
// T06-T16: _renderComment()
// ---------------------------------------------------------------------------

describe('_renderComment()', () => {

    it('T06: Kommentartext wird angezeigt', () => {
        const html = window.CommentThread._renderComment(
            _mkComment({ comment_text: 'Formulierung ueberdenken' }),
            _mkPara(),
            _baseOpts
        );
        expect(html).toContain('Formulierung ueberdenken');
        expect(html).toContain('ct-comment-text');
    });

    it('T07: Status-Badge "Offen" bei pending', () => {
        const html = window.CommentThread._renderComment(
            _mkComment({ status: 'pending' }),
            _mkPara(),
            _baseOpts
        );
        expect(html).toContain('Offen');
        expect(html).toContain('ct-status-pending');
    });

    it('T08: Status-Badge "Bearbeitet" bei addressed', () => {
        const html = window.CommentThread._renderComment(
            _mkComment({ status: 'addressed' }),
            _mkPara(),
            _baseOpts
        );
        expect(html).toContain('Bearbeitet');
        expect(html).toContain('ct-status-addressed');
    });

    it('T09: Formulierungsvorschlag wird angezeigt wenn vorhanden', () => {
        const html = window.CommentThread._renderComment(
            _mkComment({ suggested_content: 'Alternativtext hier' }),
            _mkPara(),
            _baseOpts
        );
        expect(html).toContain('Alternativtext hier');
        expect(html).toContain('ct-suggestion');
    });

    it('T10: XSS-Schutz im Kommentartext', () => {
        const html = window.CommentThread._renderComment(
            _mkComment({ comment_text: '<script>alert(1)</script>' }),
            _mkPara(),
            _baseOpts
        );
        expect(html).not.toContain('<script>');
        expect(html).toContain('&lt;script&gt;');
    });

    it('T11: Aktionsbuttons nur fuer pending-Kommentare sichtbar', () => {
        const htmlPending = window.CommentThread._renderComment(
            _mkComment({ status: 'pending' }),
            _mkPara(),
            { ..._baseOpts, myUsername: 'h002' }  // Kommentator
        );
        const htmlDone = window.CommentThread._renderComment(
            _mkComment({ status: 'addressed' }),
            _mkPara(),
            _baseOpts
        );
        expect(htmlPending).toContain('ct-comment-actions');
        expect(htmlDone).not.toContain('ct-comment-actions');
    });

    it('T12: Kommentator sieht "Zurueckziehen"-Button (revoked)', () => {
        // h002 ist Kommentator
        const html = window.CommentThread._renderComment(
            _mkComment({ author: 'h002', status: 'pending' }),
            _mkPara(),
            { ..._baseOpts, myUsername: 'h002' }
        );
        expect(html).toContain('data-resolution="revoked"');
    });

    it('T13: Para-Eigentuemer sieht "Bearbeitet"-Button (addressed)', () => {
        // Para.author = h001, opts.myUsername = h001
        const html = window.CommentThread._renderComment(
            _mkComment({ author: 'h002', status: 'pending' }),
            _mkPara([], { author: 'h001' }),
            { ..._baseOpts, myUsername: 'h001' }
        );
        expect(html).toContain('data-resolution="addressed"');
    });

    it('T14: Fremder Ermittler sieht keine Aktionsbuttons', () => {
        // h003 ist weder Kommentator noch Para-Eigentuemer noch Chef
        const html = window.CommentThread._renderComment(
            _mkComment({ author: 'h002', status: 'pending' }),
            _mkPara([], { author: 'h001' }),
            { ..._baseOpts, myUsername: 'h003', isChef: false }
        );
        expect(html).not.toContain('data-resolution');
    });

    it('T15: Chef sieht addressed- und dismissed-Buttons', () => {
        const html = window.CommentThread._renderComment(
            _mkComment({ author: 'h002', status: 'pending' }),
            _mkPara([], { author: 'h001' }),
            { ..._baseOpts, myUsername: 'h099', isChef: true }
        );
        expect(html).toContain('data-resolution="addressed"');
        expect(html).toContain('data-resolution="dismissed"');
    });
});

// ---------------------------------------------------------------------------
// T16: _formatTs()
// ---------------------------------------------------------------------------

describe('_formatTs()', () => {
    it('T16: null oder 0 -> leerer String', () => {
        expect(window.CommentThread._formatTs(null)).toBe('');
        expect(window.CommentThread._formatTs(0)).toBe('');
    });
});

// ---------------------------------------------------------------------------
// T17-T22: Neue API und Phase-4-Erweiterungen (Build 102)
// Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

describe('Phase 4 — renderForBlock / Sidebar-API', () => {

    it('T17: renderForCard ist Alias fuer renderForBlock', () => {
        // Beide muessen dasselbe Ergebnis fuer denselben Input liefern
        const block = _mkPara([], { block_id: 'blk-x' });
        const html1 = window.CommentThread.renderForBlock(block, _baseOpts);
        const html2 = window.CommentThread.renderForCard(block, _baseOpts);
        expect(html1).toBe(html2);
    });

    it('T18: renderForBlock() mit leerer Liste liefert Leer-Zustand und Eingabefeld', () => {
        const block = _mkPara([], { block_id: 'blk-empty' });
        const html = window.CommentThread.renderForBlock(block, _baseOpts);
        expect(html).toContain('ct-empty');
        expect(html).toContain('ct-compose');
        expect(html).toContain('blk-empty');
    });

    it('T19: Status-Symbol fuer pending ist ⁉ (U+2049)', () => {
        const html = window.CommentThread._renderComment(
            _mkComment({ status: 'pending' }),
            _mkPara(),
            _baseOpts
        );
        expect(html).toContain('\u2049');
        expect(html).toContain('ct-status-pending');
    });

    it('T20: Status-Symbol fuer addressed ist 👍', () => {
        const html = window.CommentThread._renderComment(
            _mkComment({ status: 'addressed' }),
            _mkPara(),
            _baseOpts
        );
        expect(html).toContain('ct-status-addressed');
        expect(html).toContain('Bearbeitet');
    });

    it('T21: showForBlock rendert Leer-Zustand fuer unbekannte block_id', () => {
        // DOM fuer #accordion-body-comments erzeugen
        const body = document.createElement('div');
        body.id = 'accordion-body-comments';
        document.body.appendChild(body);

        window.CommentThread.showForBlock('nonexistent-id', [], _baseOpts);

        expect(body.innerHTML).toContain('ct-empty');
        expect(body.innerHTML).not.toContain('ct-compose');
        document.body.removeChild(body);
    });

    it('T22: _pulseEditorBlock und _clearEditorBlockPulse sind exportiert', () => {
        expect(typeof window.CommentThread._pulseEditorBlock).toBe('function');
        expect(typeof window.CommentThread._clearEditorBlockPulse).toBe('function');
    });
});
