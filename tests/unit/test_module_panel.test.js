/**
 * tests/unit/test_module_panel.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer userinfo/module_panel.js
 *
 * T01 -- ModulePanel ist nach dem Laden verfuegbar
 * T02 -- _renderList(): leere Liste -> mp-empty sichtbar
 * T03 -- _renderList(): Module werden als Listeneintraege gerendert
 * T04 -- _renderList(): Rollen-Badge wird korrekt angezeigt
 * T05 -- _renderList(): Beschreibung wird angezeigt wenn vorhanden
 * T06 -- _renderList(): Kein Beschreibungselement wenn description fehlt
 * T07 -- _selectModule(): setzt _selectedId korrekt
 * T08 -- _selectModule(): mp-item-selected Klasse wird gesetzt
 * T09 -- _selectModule(): alte Selektion wird aufgehoben bei neuer Auswahl
 * T10 -- _renderList(): data-module-id Attribut korrekt gesetzt
 *
 * Version: v0.1.0 · Build: 093 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §4.4, Ausdefinitionsgespraech 2026-05-05
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import '../../userinfo/module_panel.js';

// ---------------------------------------------------------------------------
// T01: API-Verfuegbarkeit
// ---------------------------------------------------------------------------

describe('ModulePanel API', () => {

    it('T01: ModulePanel ist nach dem Laden verfuegbar', () => {
        expect(ModulePanel).toBeDefined();
        expect(typeof ModulePanel.open).toBe('function');
        expect(typeof ModulePanel.close).toBe('function');
        expect(typeof ModulePanel._renderList).toBe('function');
        expect(typeof ModulePanel._selectModule).toBe('function');
    });
});

// ---------------------------------------------------------------------------
// T02-T10: _renderList() und _selectModule() via innerHTML-Inspektion
// ---------------------------------------------------------------------------

describe('_renderList()', () => {

    function setupDomForRender() {
        // Vereinfachtes DOM mit echtem innerHTML-Support
        const listEl = {
            innerHTML: '',
            querySelectorAll: function(sel) {
                // Gibt leeres Array zurueck — Event-Binding wird nicht getestet
                return [];
            },
        };
        const emptyEl  = { style: { display: 'none' } };
        const loadEl   = { style: { display: '' } };

        global.window.document = {
            getElementById: id => {
                if (id === 'mp-list')    return listEl;
                if (id === 'mp-empty')   return emptyEl;
                if (id === 'mp-loading') return loadEl;
                return null;
            },
            createElement:        () => ({ style: {} }),
            querySelectorAll:     () => [],
            body:                 { appendChild: () => {} },
            addEventListener:     () => {},
            removeEventListener:  () => {},
        };
        return { listEl, emptyEl, loadEl };
    }

    it('T02: leere Liste -> mp-empty sichtbar', () => {
        const { emptyEl } = setupDomForRender();
        emptyEl.style.display = 'none';
        ModulePanel._renderList([]);
        expect(emptyEl.style.display).toBe('');
    });

    it('T03: Module werden als Listeneintraege gerendert', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 1, title: 'Modul A', description: 'Beschr A', role: 'intro' },
            { id: 2, title: 'Modul B', description: 'Beschr B', role: 'body' },
        ]);
        expect(listEl.innerHTML).toContain('Modul A');
        expect(listEl.innerHTML).toContain('Modul B');
    });

    it('T04: Rollen-Badge wird korrekt angezeigt', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 1, title: 'Test', description: '', role: 'intro' },
        ]);
        expect(listEl.innerHTML).toContain('Einleitung');
    });

    it('T05: Beschreibung wird angezeigt wenn vorhanden', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 1, title: 'Test', description: 'Meine Beschreibung', role: 'body' },
        ]);
        expect(listEl.innerHTML).toContain('Meine Beschreibung');
        expect(listEl.innerHTML).toContain('mp-item-desc');
    });

    it('T06: Kein Beschreibungselement wenn description leer', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 1, title: 'Test', description: '', role: 'body' },
        ]);
        expect(listEl.innerHTML).not.toContain('mp-item-desc');
    });

    it('T10: data-module-id Attribut korrekt gesetzt', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 42, title: 'Modul 42', description: '', role: 'legal' },
        ]);
        expect(listEl.innerHTML).toContain('data-module-id="42"');
    });
});

describe('_selectModule()', () => {

    function setupDomWithItems(ids) {
        const items = ids.map(id => ({
            dataset: { moduleId: String(id) },
            _selected: false,
            classList: {
                _val: false,
                toggle(cls, force) { if (cls === 'mp-item-selected') this._val = force; },
                contains: function(cls) { return cls === 'mp-item-selected' ? this._val : false; },
            },
            setAttribute: function() {},
            addEventListener: function() {},
        }));

        global.window.document = {
            getElementById:   () => ({ disabled: true }),
            querySelectorAll: () => items,
            createElement:    () => ({ style: {} }),
            body:             { appendChild: () => {} },
            addEventListener: () => {},
            removeEventListener: () => {},
        };
        return items;
    }

    it('T07: _selectModule() setzt Selektion intern', () => {
        setupDomWithItems([1, 2, 3]);
        // _selectedId ist modul-intern — testen ueber Seiteneffekte
        // Kein Fehler beim Aufruf
        expect(() => ModulePanel._selectModule(2)).not.toThrow();
    });

    it('T08: mp-item-selected Klasse wird beim ausgewaehlten Item gesetzt', () => {
        const items = setupDomWithItems([1, 2]);
        ModulePanel._selectModule(1);
        // items[0] (id=1) soll selected sein
        expect(items[0].classList._val).toBe(true);
        expect(items[1].classList._val).toBe(false);
    });

    it('T09: alte Selektion wird aufgehoben bei neuer Auswahl', () => {
        const items = setupDomWithItems([1, 2]);
        ModulePanel._selectModule(1);
        expect(items[0].classList._val).toBe(true);
        ModulePanel._selectModule(2);
        expect(items[0].classList._val).toBe(false);
        expect(items[1].classList._val).toBe(true);
    });
});
