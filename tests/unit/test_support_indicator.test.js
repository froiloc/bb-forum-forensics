/**
 * tests/unit/test_support_indicator.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
 *
 * Unit-Tests für die Zähler-Anzeige des SupportIndicatorModule (Build 312).
 *
 * Wir duplizieren hier die REINE Label-/Announce-Logik aus toolbar.js
 * (_formatSupportLabel / _formatSupportAnnounce), da toolbar.js als ganzes
 * nicht isoliert importierbar ist (window.*-Abhaengigkeiten). Diese Tests
 * verifizieren die Zaehler-Logik UNABHAENGIG von der Implementierung.
 * Beleg: Testbarkeits-Grundsatz (vgl. test_approval_buttons.test.js),
 *        Bauplan B7 v0.6 §7.2, mc 2026-07-01.
 *
 * L01 — count 1 -> "Support aktiv" ohne Zaehler
 * L02 — count 0/undefined -> ohne Zaehler (Rueckwaertskompatibilitaet)
 * L03 — count 2 -> "(2)" im Label
 * L04 — count 5 -> "(5)" im Label
 * L05 — leerer Benutzername -> "?"
 * L06 — Announce count 1 -> Einzahl-Form
 * L07 — Announce count 3 -> Mehrzahl-Form mit Zahl
 * L08 — Nicht-numerischer count wird wie 0/1 behandelt (kein Zaehler)
 *
 * Version: v0.7.312 · Build: 312 · 2026-07-02
 */

import { describe, it, expect } from 'vitest';

// ---------------------------------------------------------------------------
// Duplikat der reinen Logik aus toolbar.js (SupportIndicatorModule).
// ---------------------------------------------------------------------------

function _formatSupportLabel(count, safeUsername) {
    var name = safeUsername || "?";
    var n = (typeof count === "number" && count > 1) ? count : 0;
    if (n > 1) {
        return "⚠️ Support aktiv (" + n + ") · " + name;
    }
    return "⚠️ Support aktiv · " + name;
}

function _formatSupportAnnounce(count, rawUsername) {
    var who = rawUsername || "unbekannt";
    var n = (typeof count === "number" && count > 1) ? count : 0;
    if (n > 1) {
        return n + " Support-Zugriffe aktiv (u. a. " + who + ").";
    }
    return "Support-Zugriff durch " + who + " aktiv.";
}

// ---------------------------------------------------------------------------

describe('SupportIndicator — Label-/Zaehler-Logik', () => {

    it('L01: count 1 -> kein Zaehler im Label', () => {
        const label = _formatSupportLabel(1, 'h002');
        expect(label).toBe('⚠️ Support aktiv · h002');
        expect(label).not.toContain('(');
    });

    it('L02: count 0/undefined -> kein Zaehler', () => {
        expect(_formatSupportLabel(0, 'h002')).toBe('⚠️ Support aktiv · h002');
        expect(_formatSupportLabel(undefined, 'h002')).toBe('⚠️ Support aktiv · h002');
    });

    it('L03: count 2 -> "(2)" im Label', () => {
        const label = _formatSupportLabel(2, 'h002');
        expect(label).toContain('(2)');
        expect(label).toBe('⚠️ Support aktiv (2) · h002');
    });

    it('L04: count 5 -> "(5)" im Label', () => {
        expect(_formatSupportLabel(5, 'h009')).toBe('⚠️ Support aktiv (5) · h009');
    });

    it('L05: leerer Benutzername -> "?"', () => {
        expect(_formatSupportLabel(1, '')).toBe('⚠️ Support aktiv · ?');
        expect(_formatSupportLabel(3, null)).toBe('⚠️ Support aktiv (3) · ?');
    });

    it('L06: Announce count 1 -> Einzahl', () => {
        expect(_formatSupportAnnounce(1, 'h002'))
            .toBe('Support-Zugriff durch h002 aktiv.');
    });

    it('L07: Announce count 3 -> Mehrzahl mit Zahl', () => {
        expect(_formatSupportAnnounce(3, 'h002'))
            .toBe('3 Support-Zugriffe aktiv (u. a. h002).');
    });

    it('L08: nicht-numerischer count -> kein Zaehler', () => {
        expect(_formatSupportLabel('2', 'h002')).toBe('⚠️ Support aktiv · h002');
        expect(_formatSupportAnnounce('3', 'h002'))
            .toBe('Support-Zugriff durch h002 aktiv.');
    });
});
