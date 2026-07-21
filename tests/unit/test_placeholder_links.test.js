/**
 * tests/unit/test_placeholder_links.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer userinfo/placeholder_links.js
 * (Stammvater/Klon-Verknuepfungslogik, Platzhalter-Neuordnung Slice 3,
 *  mc-Wunsch; reine Funktionen ohne DOM/Persistenz.)
 *
 * T01 -- fieldKey(): eindeutig, keine Kollision zwischen (a,b:c) und (a:b,c)
 * T02 -- createState(): filtert Nicht-m/o-Felder heraus
 * T03 -- createState(): waehlt Erst-Stammvater in Dokumentreihenfolge
 * T04 -- createState(): leere Werte zaehlen nicht als explizit
 * T05 -- classify(): leer, wenn kein Wert und kein Stammvater
 * T06 -- applyInput(): erste Befuellung -> Feld wird Stammvater
 * T07 -- applyInput(): Stammvater propagiert an alle Klone (auch frueher im Dok.)
 * T08 -- applyInput(): Klon bekommt eigenen Wert -> koppelt sich ab (eigenstaendig)
 * T09 -- applyInput(): weiterer Klon spiegelt weiterhin den URSPRUENGLICHEN Stammvater
 * T10 -- applyInput(): Stammvater-Wert-Aenderung zieht Klone live nach
 * T11 -- applyInput(): eigenstaendiges Feld geleert -> wird wieder Klon (spiegelt)
 * T12 -- applyInput(): Stammvater geleert -> Neuwahl, Klone folgen neuem Stammvater
 * T13 -- applyInput(): Stammvater geleert, kein weiterer expliziter -> Klone leer
 * T14 -- applyInput(): reine Funktion — Eingangs-state bleibt unveraendert
 * T15 -- displayValue(): Klon spiegelt Stammvater, eigenes Feld hat Vorrang
 * T16 -- applyInput(): Whitespace-only zaehlt als leer (kein Stammvater)
 *
 * Version: v0.8.491 · Build: 491 · 2026-07-21
 * Beleg: mc-Wunsch Platzhalter-Neuordnung Slice 3 (Stammvater/Klon)
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import '../../userinfo/placeholder_links.js';

let L;

beforeEach(() => {
    L = window.PlaceholderLinks;
});

// Hilfs-Feldliste: derselbe Name 'spur' in drei Bloecken (Dok.-Reihenfolge
// b1, b2, b3) plus ein unabhaengiger Name 'ort' und ein a-Feld (muss raus).
function threeSpurFields() {
    return [
        { blockId: 'b1', name: 'spur', type: 'm' },
        { blockId: 'b2', name: 'spur', type: 'm' },
        { blockId: 'b3', name: 'spur', type: 'o' },
        { blockId: 'b1', name: 'ort',  type: 'o' },
        { blockId: 'b9', name: 'auto', type: 'a' }, // wird gefiltert
    ];
}

describe('fieldKey()', () => {
    it('T01: keine Kollision zwischen (a,b:c) und (a:b,c)', () => {
        expect(L.fieldKey('a', 'b:c')).not.toBe(L.fieldKey('a:b', 'c'));
    });
});

describe('createState()', () => {
    it('T02: filtert Nicht-m/o-Felder heraus', () => {
        const st = L.createState(threeSpurFields(), {});
        // 'auto' (Typ a) darf nicht in der Ordnung auftauchen
        expect(st.order.some(r => r.name === 'auto')).toBe(false);
        expect(st.byName['auto']).toBeUndefined();
        expect(st.order).toHaveLength(4);
    });

    it('T03: waehlt Erst-Stammvater in Dokumentreihenfolge', () => {
        // b2 und b3 explizit befuellt -> Stammvater ist b2 (frueher im Dok.)
        const ev = {};
        ev[L.fieldKey('b2', 'spur')] = '5';
        ev[L.fieldKey('b3', 'spur')] = '7';
        const st = L.createState(threeSpurFields(), ev);
        expect(st.master['spur']).toBe('b2');
    });

    it('T04: leere Werte zaehlen nicht als explizit', () => {
        const ev = {};
        ev[L.fieldKey('b1', 'spur')] = '   ';
        const st = L.createState(threeSpurFields(), ev);
        expect(st.master['spur']).toBeNull();
        expect(st.explicit[L.fieldKey('b1', 'spur')]).toBeUndefined();
    });
});

describe('classify() Grundzustand', () => {
    it('T05: leer, wenn kein Wert und kein Stammvater', () => {
        const st = L.createState(threeSpurFields(), {});
        expect(L.classify(st, 'b1', 'spur')).toBe('leer');
        expect(L.classify(st, 'b2', 'spur')).toBe('leer');
    });
});

describe('applyInput() Stammvater/Klon', () => {
    it('T06: erste Befuellung -> Feld wird Stammvater', () => {
        let st = L.createState(threeSpurFields(), {});
        const r = L.applyInput(st, 'b2', 'spur', '42');
        expect(r.state.master['spur']).toBe('b2');
        expect(L.classify(r.state, 'b2', 'spur')).toBe('stammvater');
    });

    it('T07: Stammvater propagiert an alle Klone (auch frueher im Dok.)', () => {
        let st = L.createState(threeSpurFields(), {});
        const r = L.applyInput(st, 'b2', 'spur', '42');
        // Klone b1 (frueher!) und b3 sollen aktualisiert werden
        const ids = r.updates.map(u => u.blockId).sort();
        expect(ids).toEqual(['b1', 'b3']);
        expect(r.updates.every(u => u.value === '42')).toBe(true);
        // Angezeigter Wert der Klone == Stammvater-Wert
        expect(L.displayValue(r.state, 'b1', 'spur')).toBe('42');
        expect(L.displayValue(r.state, 'b3', 'spur')).toBe('42');
        expect(L.classify(r.state, 'b1', 'spur')).toBe('klon');
    });

    it('T08: Klon bekommt eigenen Wert -> koppelt sich ab (eigenstaendig)', () => {
        let st = L.createState(threeSpurFields(), {});
        st = L.applyInput(st, 'b2', 'spur', '42').state;      // b2 Stammvater
        const r = L.applyInput(st, 'b1', 'spur', '99');       // b1 eigener Wert
        expect(L.classify(r.state, 'b1', 'spur')).toBe('eigenstaendig');
        expect(L.displayValue(r.state, 'b1', 'spur')).toBe('99');
        // b1 ist kein Klon mehr -> keine Propagation an andere
        expect(r.updates).toHaveLength(0);
    });

    it('T09: weiterer Klon spiegelt weiterhin den urspruenglichen Stammvater', () => {
        let st = L.createState(threeSpurFields(), {});
        st = L.applyInput(st, 'b2', 'spur', '42').state;  // b2 Stammvater
        st = L.applyInput(st, 'b1', 'spur', '99').state;  // b1 eigenstaendig
        // b3 ist weiterhin Klon und muss den Stammvater b2 ('42') spiegeln
        expect(L.classify(st, 'b3', 'spur')).toBe('klon');
        expect(L.displayValue(st, 'b3', 'spur')).toBe('42');
    });

    it('T10: Stammvater-Wert-Aenderung zieht Klone live nach', () => {
        let st = L.createState(threeSpurFields(), {});
        st = L.applyInput(st, 'b2', 'spur', '42').state;
        const r = L.applyInput(st, 'b2', 'spur', '4242');  // Stammvater aendert Wert
        expect(r.updates.map(u => u.value)).toEqual(['4242', '4242']);
        expect(L.displayValue(r.state, 'b3', 'spur')).toBe('4242');
    });

    it('T11: eigenstaendiges Feld geleert -> wird wieder Klon (spiegelt)', () => {
        let st = L.createState(threeSpurFields(), {});
        st = L.applyInput(st, 'b2', 'spur', '42').state;  // b2 Stammvater
        st = L.applyInput(st, 'b1', 'spur', '99').state;  // b1 eigenstaendig
        st = L.applyInput(st, 'b1', 'spur', '').state;    // b1 geleert
        expect(L.classify(st, 'b1', 'spur')).toBe('klon');
        expect(L.displayValue(st, 'b1', 'spur')).toBe('42');
    });

    it('T12: Stammvater geleert -> Neuwahl, Klone folgen neuem Stammvater', () => {
        let st = L.createState(threeSpurFields(), {});
        st = L.applyInput(st, 'b2', 'spur', '42').state;  // b2 Stammvater
        st = L.applyInput(st, 'b3', 'spur', '77').state;  // b3 eigenstaendig
        const r = L.applyInput(st, 'b2', 'spur', '');     // Stammvater b2 geleert
        // Neuwahl: erstes verbleibendes explizites Feld in Dok.-Reihenfolge = b3
        expect(r.state.master['spur']).toBe('b3');
        // b1 (Klon) spiegelt jetzt b3 ('77')
        expect(L.displayValue(r.state, 'b1', 'spur')).toBe('77');
        expect(r.updates.some(u => u.blockId === 'b1' && u.value === '77')).toBe(true);
    });

    it('T13: Stammvater geleert, kein weiterer expliziter -> Klone leer', () => {
        let st = L.createState(threeSpurFields(), {});
        st = L.applyInput(st, 'b2', 'spur', '42').state;  // b2 einziger Stammvater
        const r = L.applyInput(st, 'b2', 'spur', '');     // geleert
        expect(r.state.master['spur']).toBeNull();
        expect(L.displayValue(r.state, 'b1', 'spur')).toBe('');
        expect(L.classify(r.state, 'b1', 'spur')).toBe('leer');
    });

    it('T14: reine Funktion — Eingangs-state bleibt unveraendert', () => {
        const st = L.createState(threeSpurFields(), {});
        const snapshotMaster = st.master['spur'];
        L.applyInput(st, 'b2', 'spur', '42');
        // Original darf nicht mutiert sein
        expect(st.master['spur']).toBe(snapshotMaster);
        expect(st.explicit[L.fieldKey('b2', 'spur')]).toBeUndefined();
    });

    it('T15: displayValue — eigenes Feld hat Vorrang vor Stammvater', () => {
        let st = L.createState(threeSpurFields(), {});
        st = L.applyInput(st, 'b2', 'spur', '42').state;
        st = L.applyInput(st, 'b3', 'spur', '77').state;
        expect(L.displayValue(st, 'b2', 'spur')).toBe('42'); // Stammvater
        expect(L.displayValue(st, 'b3', 'spur')).toBe('77'); // eigenstaendig
    });

    it('T16: Whitespace-only zaehlt als leer (kein Stammvater)', () => {
        let st = L.createState(threeSpurFields(), {});
        const r = L.applyInput(st, 'b2', 'spur', '   ');
        expect(r.state.master['spur']).toBeNull();
        expect(r.updates).toHaveLength(0);
    });
});
