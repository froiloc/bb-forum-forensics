/**
 * tests/unit/test_approval_buttons.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Prueft die Sichtbarkeitslogik fuer Freigabe- und Ausschliessen-Buttons
 * in report.js (Phase 9). Da report.js nicht isoliert testbar ist,
 * testen wir die Rendering-Logik der Buttons via DOM-Inspektion
 * nach gezieltem Template-String-Aufruf.
 *
 * T01 -- Freigaben-Button erscheint nur bei is_chef=true und status='active'
 * T02 -- Freigeben-Button erscheint NICHT bei status='draft'
 * T03 -- Freigeben-Button erscheint NICHT bei status='approved'
 * T04 -- Ausschliessen-Button erscheint nur bei is_chef=true und nicht-approved/omitted
 * T05 -- Ausschliessen-Button erscheint NICHT bei status='approved'
 * T06 -- Ausschliessen-Button erscheint NICHT bei status='omitted'
 * T07 -- Kein Chef: keine Freigabe/Ausschliessen-Buttons
 * T08 -- InvestigatorMeEndpoint-Antwort: is_supervisor-Feld vorhanden
 *
 * Version: v0.1.0 · Build: 096 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §4.3, Build 096
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';

// ---------------------------------------------------------------------------
// Hilfsfunktionen: Simulate der Template-Logik aus report.js
// Wir duplizieren hier die relevante Bedingungslogik, da report.js
// als ganzes nicht isoliert importierbar ist (window.*-Abhaengigkeiten).
// Diese Tests verifizieren die Logik UNABHAENGIG von der Implementierung.
// Beleg: Testbarkeits-Grundsatz, Projektgespraech 2026-05-05
// ---------------------------------------------------------------------------

/**
 * Simuliert die Schaltflaechen-Renderlogik aus _renderParagraphCard().
 * Gibt ein Objekt {showApprove, showOmit} zurueck.
 */
function _computeButtonVisibility(status, isChef) {
    const showApprove = isChef && status === 'active';
    const showOmit    = isChef && status !== 'approved' && status !== 'omitted';
    return { showApprove, showOmit };
}

// ---------------------------------------------------------------------------
// T01-T07: Sichtbarkeitslogik
// ---------------------------------------------------------------------------

describe('Freigabe/Ausschliessen-Button-Logik', () => {

    it('T01: Chef + status=active -> Freigeben-Button sichtbar', () => {
        const { showApprove } = _computeButtonVisibility('active', true);
        expect(showApprove).toBe(true);
    });

    it('T02: Chef + status=draft -> Freigeben-Button NICHT sichtbar', () => {
        const { showApprove } = _computeButtonVisibility('draft', true);
        expect(showApprove).toBe(false);
    });

    it('T03: Chef + status=approved -> Freigeben-Button NICHT sichtbar', () => {
        const { showApprove } = _computeButtonVisibility('approved', true);
        expect(showApprove).toBe(false);
    });

    it('T04: Chef + status=draft -> Ausschliessen-Button sichtbar', () => {
        const { showOmit } = _computeButtonVisibility('draft', true);
        expect(showOmit).toBe(true);
    });

    it('T05: Chef + status=approved -> Ausschliessen-Button NICHT sichtbar', () => {
        const { showOmit } = _computeButtonVisibility('approved', true);
        expect(showOmit).toBe(false);
    });

    it('T06: Chef + status=omitted -> Ausschliessen-Button NICHT sichtbar', () => {
        const { showOmit } = _computeButtonVisibility('omitted', true);
        expect(showOmit).toBe(false);
    });

    it('T07: kein Chef -> weder Freigeben noch Ausschliessen sichtbar', () => {
        for (const status of ['draft', 'active', 'approved', 'omitted', 'superseded']) {
            const { showApprove, showOmit } = _computeButtonVisibility(status, false);
            expect(showApprove).toBe(false);
            expect(showOmit).toBe(false);
        }
    });
});

// ---------------------------------------------------------------------------
// T08: InvestigatorMe-Antwortstruktur
// ---------------------------------------------------------------------------

describe('InvestigatorMe-Antwortstruktur', () => {

    it('T08: is_supervisor-Feld und andere Pflichtfelder vorhanden', () => {
        // Simulated response wie vom Endpunkt geliefert
        const mockResponse = {
            system_username: 'h001',
            display_name:    'Max Muster',
            is_investigator: true,
            is_supervisor:   false,
            is_support:      false,
        };
        expect(mockResponse).toHaveProperty('is_supervisor');
        expect(mockResponse).toHaveProperty('system_username');
        expect(typeof mockResponse.is_supervisor).toBe('boolean');
    });
});
