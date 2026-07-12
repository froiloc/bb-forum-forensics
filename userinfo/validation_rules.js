/**
 * userinfo/validation_rules.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * ZWECK
 *   Client-seitiger Zugriff auf den ZENTRALEN Katalog der Formatregeln, den
 *   der Server aus config.yaml (validation.rules) ausliefert:
 *       GET /_forensic/validation_rules
 *       -> { "rules": { "spurennummer": { pattern, transform, hint } } }
 *
 * WARUM ES DIESE DATEI GIBT
 *   Bis Build 388 stand die Formatpruefung als BASE64-KODIERTE REGEX im
 *   5. Feld des Platzhalters, also im Modultext in templates.db. Ein neues
 *   Spurennummern-Format haette bedeutet: Modultext aendern, Base64 neu
 *   kodieren, Seed nachziehen. Ab Build 388 verweist der Baustein nur noch
 *   symbolisch:
 *       {{m:spurennummer||Spurennummer der Vorgangsverwaltung|rule:spurennummer}}
 *   Ein weiteres Behoerdenkuerzel erfordert dann NUR eine Aenderung an
 *   config.yaml + Serverneustart — kein Code, keine Datenbankaenderung.
 *
 * ZWEI PRUEFUNGEN, ZWEI ZWECKE (bewusst redundant):
 *   Hier (Browser)  = Bedienkomfort. Der Ermittler sieht sofort, dass
 *                     'AIW 123' nicht passt, statt es erst beim Einreichen
 *                     zu erfahren.
 *   Server (report.py::_validate_report_fields, Build 388) = die ZUSICHERUNG.
 *                     Ein direkter POST wuerde diese Datei umgehen; fuer ein
 *                     gerichtsverwertbares Dokument darf die Pruefung nicht
 *                     im Browser des Ermittlers enden.
 *   Beide pruefen DASSELBE Muster aus DERSELBEN Quelle — deshalb duerfen die
 *   Muster keine Konstrukte nutzen, die in Python und JavaScript
 *   Unterschiedliches bedeuten (keine Lookbehinds, keine benannten Gruppen).
 *
 * ABWAERTSKOMPATIBILITAET
 *   Das 5. Platzhalterfeld darf weiterhin eine Base64-Regex enthalten
 *   (Alt-Form, OP-B6-5). resolve() erkennt beide Formen: alles, was mit
 *   'rule:' beginnt, ist ein Katalogverweis; alles andere wird als Base64
 *   behandelt. Bestehende Bausteine funktionieren unveraendert weiter.
 *
 * OEFFENTLICHE API (window.ValidationRules)
 *   await window.ValidationRules.load()      -- Katalog einmalig laden
 *   window.ValidationRules.get(name)         -- { pattern, transform, hint } | null
 *   window.ValidationRules.resolve(rawField) -- aus dem 5. Platzhalterfeld
 *   window.ValidationRules.normalize(rule, wert)  -- transform anwenden
 *   window.ValidationRules.check(rule, wert)      -- { ok, value, message }
 *   window.ValidationRules.isLoaded()
 *
 * Version: v0.7.389 · Build: 389 · 2026-07-12
 * Beleg: Bauplan Build 389 §3, Projektgespraech 2026-07-12
 */

(function() {
'use strict';

// ---------------------------------------------------------------------------
// Debug-Logging (DEV) — fuer PROD auf false setzen.
// ---------------------------------------------------------------------------
const DEBUG = true;
function _dbg(...args) {
    if (DEBUG) console.log('[ValidationRules]', ...args);
}

const RULES_API   = '/_forensic/validation_rules';
const RULE_PREFIX = 'rule:';

// Der geladene Katalog. null = noch nie geladen (Unterschied zu {} = geladen,
// aber leer! Diese Unterscheidung ist wichtig: bei {} wissen wir, dass der
// Server nichts hat — das ist ein Missstand, kein Ladezustand).
let _rules   = null;
let _loading = null;   // laufendes Versprechen (verhindert Mehrfachabruf)

/**
 * Base64 -> Unicode-String (Alt-Form des 5. Platzhalterfeldes).
 * Identisch zur Implementierung in placeholder_wizard.js.
 * @returns {string|null} null wenn nicht dekodierbar
 */
function _b64Decode(b64) {
    try {
        return decodeURIComponent(
            atob(b64).split('').map(
                c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
            ).join('')
        );
    } catch (_) {
        return null;
    }
}

/**
 * Laedt den Katalog. Mehrfachaufrufe teilen sich EIN Versprechen.
 * @returns {Promise<Object>} der Katalog (im Fehlerfall {})
 */
async function load() {
    if (_rules !== null) return _rules;
    if (_loading)        return _loading;

    _loading = (async () => {
        try {
            const resp = await fetch(RULES_API, {
                headers: { 'X-Forensic-Request': 'ajax' },
            });
            if (!resp.ok) {
                // GRUNDREGEL 1: nicht still auf 'keine Regeln' zurueckfallen.
                console.error(
                    '[ValidationRules] Katalog konnte nicht geladen werden ' +
                    '(HTTP ' + resp.status + '). Felder mit Formatregel werden ' +
                    'im Browser NICHT geprueft; der Server lehnt sie beim ' +
                    'Einreichen ab.'
                );
                _rules = {};
                return _rules;
            }
            const data = await resp.json();
            _rules = (data && data.rules) ? data.rules : {};
            _dbg('Katalog geladen:', Object.keys(_rules));
            if (!Object.keys(_rules).length) {
                console.warn(
                    '[ValidationRules] Der Katalog ist LEER. Bausteine mit ' +
                    'einem rule:-Verweis koennen nicht geprueft werden. ' +
                    'validation.rules in config.yaml pruefen.'
                );
            }
            return _rules;
        } catch (err) {
            console.error('[ValidationRules] Laden fehlgeschlagen:', err);
            _rules = {};
            return _rules;
        } finally {
            _loading = null;
        }
    })();

    return _loading;
}

function isLoaded() {
    return _rules !== null;
}

/**
 * @param {string} name  Regelname, z.B. 'spurennummer'
 * @returns {{pattern: string, transform: string, hint: string}|null}
 */
function get(name) {
    if (!_rules || !name) return null;
    return _rules[name] || null;
}

/**
 * Loest das 5. Platzhalterfeld auf — egal in welcher Form.
 *
 * @param {string} rawField  z.B. 'rule:spurennummer' ODER eine Base64-Regex
 * @returns {{pattern: string, transform: string, hint: string,
 *            ruleName: string|null, missing: boolean}|null}
 *          missing=true bedeutet: es WURDE eine Regel verlangt, sie steht aber
 *          nicht im Katalog. Das ist ein Missstand, kein 'keine Pruefung'.
 */
function resolve(rawField) {
    if (!rawField) return null;

    // Neue Form: Katalogverweis
    if (rawField.startsWith(RULE_PREFIX)) {
        const name = rawField.slice(RULE_PREFIX.length).trim();
        const spec = get(name);
        if (!spec) {
            console.warn(
                '[ValidationRules] Der Baustein verweist auf die Formatregel "' +
                name + '", die im Katalog fehlt.'
            );
            return {
                pattern: '', transform: 'none', hint: '',
                ruleName: name, missing: true,
            };
        }
        return {
            pattern:   spec.pattern,
            transform: spec.transform || 'none',
            hint:      spec.hint || '',
            ruleName:  name,
            missing:   false,
        };
    }

    // Alt-Form: Base64-Regex direkt im Baustein (OP-B6-5, bis Build 388).
    const pattern = _b64Decode(rawField);
    if (pattern === null) return null;
    return {
        pattern:   pattern,
        transform: 'none',
        hint:      '',
        ruleName:  null,
        missing:   false,
    };
}

/**
 * Wendet NUR die Normalisierung an (ohne Pruefung).
 * Muss identisch zu core/validation_rules.py::_apply_transform sein.
 */
function applyTransform(value, transform) {
    const v = String(value == null ? '' : value);
    switch (transform) {
        case 'upper': return v.trim().toUpperCase();
        case 'lower': return v.trim().toLowerCase();
        case 'strip': return v.trim();
        default:      return v;
    }
}

/**
 * Normalisiert einen Wert gemaess dem 5. Platzhalterfeld.
 * @param {string} rawField  z.B. 'rule:spurennummer'
 * @param {string} value
 * @returns {string} normalisierter Wert (unveraendert wenn keine Regel greift)
 */
function normalize(rawField, value) {
    const spec = resolve(rawField);
    if (!spec || spec.missing) return String(value == null ? '' : value);
    return applyTransform(value, spec.transform);
}

/**
 * Prueft einen Wert. Reihenfolge wie auf dem Server: ERST normalisieren
 * (z.B. Uppercase), DANN gegen das Muster pruefen. Der zurueckgegebene Wert
 * ist der normalisierte — genau dieser wird gespeichert.
 *
 * @param {string} rawField
 * @param {string} value
 * @returns {{ok: boolean, value: string, message: string}}
 */
function check(rawField, value) {
    const raw  = String(value == null ? '' : value);
    const spec = resolve(rawField);

    // Kein Regelverweis -> hier ist nichts zu pruefen.
    if (!spec) return { ok: true, value: raw, message: '' };

    if (spec.missing) {
        // GRUNDREGEL 1: nicht als 'gueltig' durchwinken. Der Server wuerde
        // diesen Wert beim Einreichen ohnehin ablehnen — der Ermittler soll
        // das JETZT erfahren, nicht erst am Ende.
        return {
            ok: false,
            value: raw,
            message: 'Die Formatregel "' + spec.ruleName +
                     '" ist auf dem Server nicht hinterlegt. Bitte an die ' +
                     'Systembetreuung wenden.',
        };
    }

    const normalized = applyTransform(raw, spec.transform);

    let re;
    try {
        re = new RegExp(spec.pattern);
    } catch (err) {
        console.error('[ValidationRules] Ungueltiges Muster:', spec.pattern, err);
        return {
            ok: false,
            value: normalized,
            message: 'Die hinterlegte Formatregel ist fehlerhaft.',
        };
    }

    if (!re.test(normalized)) {
        return {
            ok: false,
            value: normalized,
            message: spec.hint
                ? ('Eingabe entspricht nicht dem geforderten Format (' + spec.hint + ').')
                : 'Eingabe entspricht nicht dem geforderten Format.',
        };
    }

    return { ok: true, value: normalized, message: '' };
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

window.ValidationRules = {
    load,
    isLoaded,
    get,
    resolve,
    normalize,
    check,
    applyTransform,
    // Nur fuer Tests: Katalog direkt setzen, ohne HTTP.
    _setRulesForTest(rules) { _rules = rules || {}; },
};

_dbg('validation_rules.js geladen — window.ValidationRules exportiert');

})();
