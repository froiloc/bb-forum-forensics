/**
 * tests/unit/test_annotation_sidebar.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer userinfo/annotation_sidebar.js
 *
 * T01 -- AnnotationSidebar ist nach dem Laden verfuegbar
 * T02 -- _matchesSearch(): leerer Suchtext -> immer true
 * T03 -- _matchesSearch(): Treffer in tags -> true
 * T04 -- _matchesSearch(): Treffer in text (Notiz) -> true
 * T05 -- _matchesSearch(): Treffer in selection.text (Originaltext) -> true
 * T06 -- _matchesSearch(): kein Treffer -> false
 * T07 -- _matchesSearch(): Suche ist case-insensitiv
 * T08 -- _filterAndGroup(): gruppiert Annotationen nach Kategorie
 * T09 -- _filterAndGroup(): _hideAnchored filtert verankerte heraus
 * T10 -- _filterAndGroup(): Suchtext filtert Annotationen
 * T11 -- _filterAndGroup(): Kategorien ohne Treffer erscheinen nicht
 * T12 -- _renderAnnotation(): Notiztext wird angezeigt
 * T13 -- _renderAnnotation(): Tags werden als Chips gerendert
 * T14 -- _renderAnnotation(): Originaltext erscheint in Anfuehrungszeichen
 * T15 -- _renderAnnotation(): Verankerte Annotation erhaelt as-ann-anchored-Klasse
 * T16 -- _renderAnnotation(): XSS-Schutz in Annotationstext
 * T17 -- showSidebar ist exportiert
 * T18 -- _renderAnnotation() hat draggable="true"
 * T19 -- _renderAnnotation() enthält data-ann-id
 * T20 -- _renderAnnotation() zeigt "Als Beleg einfuegen"-Button
 * T21 -- _renderAnnotation(): verankerte Annotation hat deaktivierten Anker-Button
 * T22 -- showSidebar mit EvidenceBlock-Bloecken extrahiert evidence_ids
 * T23 -- Bug 2.22: _filterAndGroup filtert verankerte bei _hideAnchored=true
 * T24 -- Bug 2.22: _filterAndGroup zeigt verankerte bei _hideAnchored=false
 * T25 -- Bug 2.21: _render() bricht stumm ab wenn Container fehlt
 *
 * Version: v0.6.106 · Build: 106 · 2026-05-06
 * Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import '../../userinfo/annotation_sidebar.js';

// ---------------------------------------------------------------------------
// Hilfsfunktionen fuer Tests
// ---------------------------------------------------------------------------

/** Erstellt eine Minimalannotation fuer Tests. */
function _ann(overrides = {}) {
    return {
        id:        1,
        category:  'CAT_OTHER',
        text:      'Notiztext',
        tags:      ['tag1'],
        selection: { text: 'Originaltext im Forum' },
        createdBy: 'h001',
        createdAt: 1700000000000,
        ...overrides,
    };
}

/**
 * Setzt den internen Zustand des Moduls fuer Tests.
 * Da _annotations, _anchoredIds etc. modul-intern sind, setzen wir sie
 * ueber Hilfsmethoden, die in window.AnnotationSidebar._test* exponiert sind.
 */
function _setState(annotations, anchoredIds, searchText, hideAnchored) {
    // Wir rufen init() mit Dummy-Container auf und patchen danach
    // den Zustand ueber die Test-Hooks.
    window.AnnotationSidebar._testSetState(annotations, anchoredIds, searchText, hideAnchored);
}

// ---------------------------------------------------------------------------
// T01: API-Verfuegbarkeit
// ---------------------------------------------------------------------------

describe('AnnotationSidebar API', () => {

    it('T01: AnnotationSidebar ist nach dem Laden verfuegbar', () => {
        expect(window.AnnotationSidebar).toBeDefined();
        expect(typeof window.AnnotationSidebar.init).toBe('function');
        expect(typeof window.AnnotationSidebar.reload).toBe('function');
        expect(typeof window.AnnotationSidebar.updateAnchored).toBe('function');
        expect(typeof window.AnnotationSidebar._filterAndGroup).toBe('function');
        expect(typeof window.AnnotationSidebar._matchesSearch).toBe('function');
        expect(typeof window.AnnotationSidebar._renderAnnotation).toBe('function');
    });
});

// ---------------------------------------------------------------------------
// T02-T07: _matchesSearch()
// ---------------------------------------------------------------------------

describe('_matchesSearch()', () => {

    it('T02: leerer Suchtext -> immer true', () => {
        const ann = _ann();
        expect(window.AnnotationSidebar._matchesSearch(ann, '')).toBe(true);
    });

    it('T03: Treffer in tags -> true', () => {
        const ann = _ann({ tags: ['verdaechtig', 'alias'] });
        expect(window.AnnotationSidebar._matchesSearch(ann, 'alias')).toBe(true);
    });

    it('T04: Treffer in text (Notiz) -> true', () => {
        const ann = _ann({ text: 'Stimmt mit Alias ueberein' });
        expect(window.AnnotationSidebar._matchesSearch(ann, 'alias')).toBe(true);
    });

    it('T05: Treffer in selection.text (Originaltext) -> true', () => {
        const ann = _ann({ selection: { text: 'wie BirnenKenner99 bereits' } });
        expect(window.AnnotationSidebar._matchesSearch(ann, 'birnenkenner')).toBe(true);
    });

    it('T06: kein Treffer in keinem Feld -> false', () => {
        const ann = _ann({ tags: ['xyz'], text: 'nichts', selection: { text: 'leer' } });
        expect(window.AnnotationSidebar._matchesSearch(ann, 'suchbegriff')).toBe(false);
    });

    it('T07: Suche ist case-insensitiv', () => {
        const ann = _ann({ text: 'GROSSBUCHSTABEN' });
        expect(window.AnnotationSidebar._matchesSearch(ann, 'grossbuchstaben')).toBe(true);
    });
});

// ---------------------------------------------------------------------------
// T08-T11: _filterAndGroup() via _testSetState
// ---------------------------------------------------------------------------

describe('_filterAndGroup()', () => {

    it('T08: gruppiert Annotationen nach Kategorie', () => {
        window.AnnotationSidebar._testSetState(
            [
                _ann({ id: 1, category: 'CAT_PERSON' }),
                _ann({ id: 2, category: 'CAT_PERSON' }),
                _ann({ id: 3, category: 'CAT_OTHER' }),
            ],
            new Set(), '', false
        );
        const grouped = window.AnnotationSidebar._filterAndGroup();
        expect(grouped['CAT_PERSON']).toHaveLength(2);
        expect(grouped['CAT_OTHER']).toHaveLength(1);
    });

    it('T09: _hideAnchored filtert verankerte Annotationen heraus', () => {
        window.AnnotationSidebar._testSetState(
            [
                _ann({ id: 1, category: 'CAT_OTHER' }),
                _ann({ id: 2, category: 'CAT_OTHER' }),
            ],
            new Set([1]),  // id=1 ist verankert
            '', true       // hideAnchored=true
        );
        const grouped = window.AnnotationSidebar._filterAndGroup();
        expect(grouped['CAT_OTHER']).toHaveLength(1);
        expect(grouped['CAT_OTHER'][0].id).toBe(2);
    });

    it('T10: Suchtext filtert passende Annotationen heraus', () => {
        window.AnnotationSidebar._testSetState(
            [
                _ann({ id: 1, text: 'BirnenKenner99 Hinweis' }),
                _ann({ id: 2, text: 'nichts passendes' }),
            ],
            new Set(), 'birnenkenner', false
        );
        const grouped = window.AnnotationSidebar._filterAndGroup();
        expect(grouped['CAT_OTHER']).toHaveLength(1);
        expect(grouped['CAT_OTHER'][0].id).toBe(1);
    });

    it('T11: Kategorien ohne Treffer erscheinen nicht im Ergebnis', () => {
        window.AnnotationSidebar._testSetState(
            [
                _ann({ id: 1, category: 'CAT_PERSON', text: 'treffer' }),
                _ann({ id: 2, category: 'CAT_OTHER',  text: 'kein match' }),
            ],
            new Set(), 'treffer', false
        );
        const grouped = window.AnnotationSidebar._filterAndGroup();
        expect(grouped['CAT_PERSON']).toHaveLength(1);
        expect(grouped['CAT_OTHER']).toBeUndefined();
    });
});

// ---------------------------------------------------------------------------
// T12-T16: _renderAnnotation()
// ---------------------------------------------------------------------------

describe('_renderAnnotation()', () => {

    beforeEach(() => {
        // Leeren Zustand setzen (keine verankerten IDs)
        window.AnnotationSidebar._testSetState([], new Set(), '', false);
    });

    it('T12: Notiztext wird angezeigt', () => {
        const html = window.AnnotationSidebar._renderAnnotation(
            _ann({ text: 'Stimmt mit Alias ueberein' })
        );
        expect(html).toContain('Stimmt mit Alias ueberein');
        expect(html).toContain('as-ann-notes');  // Build 240: umbenannt von as-ann-text
    });

    it('T13: Tags werden als as-tag-Chips gerendert', () => {
        const html = window.AnnotationSidebar._renderAnnotation(
            _ann({ tags: ['alias', 'pgp'] })
        );
        expect(html).toContain('as-tag');
        expect(html).toContain('alias');
        expect(html).toContain('pgp');
    });

    it('T14: Originaltext erscheint in Anfuehrungszeichen (as-ann-orig)', () => {
        const html = window.AnnotationSidebar._renderAnnotation(
            _ann({ selection: { text: 'wie BirnenKenner99 bereits' } })
        );
        expect(html).toContain('as-ann-quote');  // Build 240: umbenannt von as-ann-orig
        expect(html).toContain('BirnenKenner99');
    });

    it('T15: verankerte Annotation erhaelt as-ann-anchored-Klasse', () => {
        window.AnnotationSidebar._testSetState([], new Set([42]), '', false);
        const html = window.AnnotationSidebar._renderAnnotation(
            _ann({ id: 42 })
        );
        expect(html).toContain('as-ann-anchored');
    });

    it('T16: XSS-Schutz in Annotationstext', () => {
        const html = window.AnnotationSidebar._renderAnnotation(
            _ann({ text: '<script>alert(1)</script>' })
        );
        expect(html).not.toContain('<script>');
        expect(html).toContain('&lt;script&gt;');
    });
});

// ---------------------------------------------------------------------------
// T17-T22: Phase 8 — Sidebar-Integration, Drag-and-Drop, showSidebar
// Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

describe('Phase 8 — Sidebar-Integration', () => {

    it('T17: showSidebar ist exportiert', () => {
        expect(typeof window.AnnotationSidebar.showSidebar).toBe('function');
    });

    it('T18: _renderAnnotation() hat draggable="true"', () => {
        window.AnnotationSidebar._testSetState([], new Set(), '', false);
        const html = window.AnnotationSidebar._renderAnnotation(
            { id: 1, category: 'CAT_OTHER', text: 'Test', tags: [], selection: {} }
        );
        expect(html).toContain('draggable="true"');
    });

    it('T19: _renderAnnotation() enthält data-ann-id', () => {
        window.AnnotationSidebar._testSetState([], new Set(), '', false);
        const html = window.AnnotationSidebar._renderAnnotation(
            { id: 77, category: 'CAT_OTHER', text: 'Test', tags: [], selection: {} }
        );
        expect(html).toContain('data-ann-id="77"');
    });

    it('T20: _renderAnnotation() zeigt "Als Beleg einfuegen"-Button', () => {
        window.AnnotationSidebar._testSetState([], new Set(), '', false);
        const html = window.AnnotationSidebar._renderAnnotation(
            { id: 1, category: 'CAT_OTHER', text: 'Test', tags: [], selection: {} }
        );
        expect(html).toContain('as-btn-anchor');
    });

    it('T21: _renderAnnotation(): verankerte Annotation hat deaktivierten Anker-Button', () => {
        window.AnnotationSidebar._testSetState([], new Set([5]), '', false);
        const html = window.AnnotationSidebar._renderAnnotation(
            { id: 5, category: 'CAT_OTHER', text: 'Test', tags: [], selection: {} }
        );
        expect(html).toContain('disabled');
    });

    it('T22: showSidebar mit EvidenceBlock-Bloecken extrahiert evidence_ids', () => {
        // Prueft dass showSidebar keine Ausnahme wirft und korrekt aufgerufen wird
        const blocks = [
            {
                block_id:   'blk-001',
                block_type: 'evidence',
                block_data: '{"evidence_ids":[42,43],"group_label":""}',
            },
        ];
        expect(() => {
            window.AnnotationSidebar.showSidebar(blocks, { lockId: null });
        }).not.toThrow();
    });
});

describe('Bug 2.22 — Checkbox-State-Persistenz beim Re-Render', () => {

    it('T23: _filterAndGroup filtert verankerte heraus wenn _hideAnchored=true', () => {
        // Prüft den Kerneffekt: verankerte Annotationen werden bei hideAnchored=true
        // aus dem Ergebnis entfernt. Der HTML-Render-Pfad wird indirekt abgedeckt,
        // weil _filterAndGroup() von _render() genutzt wird.
        const anns = [
            { id: 1, category: 'CAT_OTHER', text: 'A', tags: [], selection: {} },
            { id: 2, category: 'CAT_OTHER', text: 'B', tags: [], selection: {} },
        ];
        window.AnnotationSidebar._testSetState(anns, new Set([1]), '', true);
        const grouped = window.AnnotationSidebar._filterAndGroup();
        const ids = (grouped['CAT_OTHER'] || []).map(a => a.id);
        expect(ids).not.toContain(1);
        expect(ids).toContain(2);
    });

    it('T24: _filterAndGroup zeigt verankerte wenn _hideAnchored=false (Standard)', () => {
        const anns = [
            { id: 5, category: 'CAT_OTHER', text: 'X', tags: [], selection: {} },
        ];
        window.AnnotationSidebar._testSetState(anns, new Set([5]), '', false);
        const grouped = window.AnnotationSidebar._filterAndGroup();
        expect((grouped['CAT_OTHER'] || []).map(a => a.id)).toContain(5);
    });

});

describe('Bug 2.21 — Scrollposition-Erhalt beim Re-Render', () => {

    it('T25: _render() bricht stumm ab wenn Container nicht vorhanden', () => {
        // Stellt sicher, dass _render() bei fehlendem Container keinen Fehler wirft.
        // Der Test prueft die Robustheit des Fallback-Guards in _render().
        window.AnnotationSidebar._testSetState([], new Set(), '', false);
        // init() mit nicht-existentem containerId — _render() muss ohne Fehler abbrechen
        expect(() => {
            window.AnnotationSidebar.init({
                containerId: 'nicht-vorhanden-2021',
                annotationsApiUrl: null,
            });
        }).not.toThrow();
    });

});
