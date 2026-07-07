/**
 * tests/unit/test_support_preflight.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
 *
 * Regressions-Guard fuer den SSE-Preflight-Header des SupportIndicatorModule
 * (toolbar.js, role=main). Build 324.
 *
 * HINTERGRUND (Beleg: PoC 2026-07-06, P3=PASS):
 *   Der Server (forensic_api/events.py:333-335) unterscheidet einen reinen
 *   Slot-Check von einem echten SSE-Stream AUSSCHLIESSLICH am Request-Header
 *   'X-Forensic-Preflight: 1'. Fehlt der Header, wird der Preflight-GET als
 *   echter Stream behandelt, beansprucht via claim_sse_role() die Rolle 'main'
 *   und haelt sie offen — die danach geoeffnete echte EventSource kollidiert
 *   dann mit dem eigenen Preflight-Stream (HTTP 409). Folge: kein support_status,
 *   kein Support-Indikator (Selbst-Kollision). Genau dieser Header hatte in
 *   Build 312 gefehlt.
 *
 * WARUM QUELLCODE-BASIERT (readFileSync statt Verhaltenstest):
 *   toolbar.js ist als Ganzes nicht isoliert importierbar (window.*-Abhaengig-
 *   keiten) — dieselbe Begruendung wie in test_support_indicator.test.js, das
 *   deshalb reine Logik dupliziert. Ein Verhaltenstest von init() wuerde einen
 *   vollstaendigen toolbar.js-Bootstrap in JSDOM erfordern. Der Guard prueft
 *   daher den TATSAECHLICHEN Quelltext des Preflight-fetch — nicht einen
 *   Kommentar (der Anker liegt AUF dem fetch(-Aufruf, Kommentare davor sind
 *   ausgeschlossen), sodass Entfernen des Headers den Test rot faerbt.
 *
 * P01 — toolbar.js role=main-Preflight-fetch enthaelt 'X-Forensic-Preflight'
 * P02 — der Header-Wert ist '1'
 * P03 — Positiv-Kontrolle: sse_layer.js (Referenzmuster) sendet den Header weiter
 * P04 — userinfo.js role=userinfo-Preflight-fetch enthaelt 'X-Forensic-Preflight' (Build 327)
 * P05 — der userinfo-Preflight-Header-Wert ist '1' (Build 327)
 *
 * Build 327 (2026-07-07): P04/P05 ergaenzt. userinfo.js Fenster 2 nutzt einen
 * EIGENEN Preflight-Pfad (initSSEWindow2, OHNE SSELayer) und hatte denselben
 * fehlenden Header wie role=main in Build 312 -> role=userinfo Selbst-Kollision.
 *
 * Version: v0.7.327 · Build: 327 · 2026-07-07
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..', '..');

const TOOLBAR   = readFileSync(join(REPO_ROOT, 'toolbar', 'toolbar.js'), 'utf8');
const SSE_LAYER = readFileSync(join(REPO_ROOT, 'userinfo', 'sse_layer.js'), 'utf8');
const USERINFO  = readFileSync(join(REPO_ROOT, 'userinfo', 'userinfo.js'), 'utf8');

// Hilfsfunktion: Fenster ab dem ERSTEN fetch(-Aufruf nach dem role=main-Anker.
// Damit werden vorangestellte Kommentare (die den Header erwaehnen) bewusst
// ausgeschlossen — der Guard prueft nur den echten Code des fetch-Aufrufs.
function mainPreflightFetchRegion(source) {
    const anchor = source.indexOf("'?role=main'");
    if (anchor < 0) return null;
    const fetchStart = source.indexOf('fetch(', anchor);
    if (fetchStart < 0) return null;
    // Der fetch-Aufruf inkl. Options-Objekt ist kurz (~100 Zeichen). 200 Zeichen
    // decken ihn sicher ab, ohne in unbeteiligten Folgecode zu laufen.
    return source.slice(fetchStart, fetchStart + 200);
}

// Analog fuer userinfo.js (Fenster 2, role=userinfo): Anker AUF dem fetch(-Aufruf
// nach dem '?role=userinfo'-Literal, sodass vorangestellte Kommentare (die den
// Header erwaehnen) ausgeschlossen sind und Entfernen des Headers den Test rot faerbt.
function userinfoPreflightFetchRegion(source) {
    const anchor = source.indexOf("'?role=userinfo'");
    if (anchor < 0) return null;
    const fetchStart = source.indexOf('fetch(', anchor);
    if (fetchStart < 0) return null;
    return source.slice(fetchStart, fetchStart + 200);
}

describe('SSE-Preflight-Header (Build 324, role=main Selbst-Kollision)', () => {
    it('P01 — toolbar.js role=main-Preflight-fetch enthaelt X-Forensic-Preflight', () => {
        const region = mainPreflightFetchRegion(TOOLBAR);
        expect(region, "role=main-Preflight-fetch nicht gefunden").not.toBeNull();
        expect(region).toContain('X-Forensic-Preflight');
    });

    it('P02 — der Preflight-Header-Wert ist "1"', () => {
        const region = mainPreflightFetchRegion(TOOLBAR);
        expect(region).not.toBeNull();
        // Akzeptiert einfache oder doppelte Anfuehrungszeichen und flexible
        // Leerzeichen: 'X-Forensic-Preflight': '1'  /  "X-Forensic-Preflight":"1"
        expect(region).toMatch(/['"]X-Forensic-Preflight['"]\s*:\s*['"]1['"]/);
    });

    it('P03 — Positiv-Kontrolle: sse_layer.js sendet den Header weiterhin', () => {
        // Referenzmuster, an dem der Fix gespiegelt wurde. Faellt dieser Test,
        // hat sich die Referenz veraendert und der Guard ist neu zu bewerten.
        expect(SSE_LAYER).toContain('X-Forensic-Preflight');
    });
});

describe('SSE-Preflight-Header (Build 327, role=userinfo Selbst-Kollision)', () => {
    it('P04 — userinfo.js role=userinfo-Preflight-fetch enthaelt X-Forensic-Preflight', () => {
        const region = userinfoPreflightFetchRegion(USERINFO);
        expect(region, "role=userinfo-Preflight-fetch nicht gefunden").not.toBeNull();
        expect(region).toContain('X-Forensic-Preflight');
    });

    it('P05 — der userinfo-Preflight-Header-Wert ist "1"', () => {
        const region = userinfoPreflightFetchRegion(USERINFO);
        expect(region).not.toBeNull();
        expect(region).toMatch(/['"]X-Forensic-Preflight['"]\s*:\s*['"]1['"]/);
    });
});
