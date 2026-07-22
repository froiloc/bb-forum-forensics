/**
 * userinfo/placeholder_defs.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * ZWECK (Build 494)
 *   Client-seitiger Zugriff auf die m/o-PLATZHALTERDEFINITIONEN aus der
 *   Datenbank (templates.placeholders, Build 489), ausgeliefert ueber
 *       GET /_forensic/placeholders/library
 *       -> [ { id, title, description, tags, return_type, type,
 *              default_value, validation, validation_type }, ... ]
 *
 * WARUM ES DIESE DATEI GIBT
 *   Seit der Platzhalter-Neuordnung (Build 489) ist die DATENBANK die
 *   Autoritaet fuer bekannte Platzhalter-IDs — auch fuer deren Validierung
 *   (validation/validation_type). Ein m/o-Token {{m:<id>|...}} verweist mit
 *   <id> auf placeholders.id (gleiche Kennung wie {{a:<id>}}). Trifft der
 *   Token-Name eine bekannte m/o-Definition, gilt DEREN Validierung — nicht
 *   nur die inline im 5. Token-Feld hinterlegte Regel. Damit lassen sich
 *   Formatregeln (regex/list/like) zentral pflegen, statt sie in jedem
 *   Modultext zu wiederholen (Bauplan Platzhalter_DB §2.3, DB-Autoritaet).
 *
 * ABGRENZUNG
 *   Nur die Definitionen (Validierung/Default) werden hier vorgehalten. Die
 *   fallweise Wiederverwendung von m/o-WERTEN ueber den placeholder_cache
 *   (mc-Wunsch) ist ein eigener Folge-Build (Prefill/Writeback).
 *
 * OEFFENTLICHE API (window.PlaceholderDefs)
 *   await window.PlaceholderDefs.load()   -- Bibliothek einmalig laden (m/o)
 *   window.PlaceholderDefs.get(id)        -- Definition | null (nur m/o)
 *   window.PlaceholderDefs.isLoaded()
 *   window.PlaceholderDefs.all()          -- flache Kopie aller m/o-Defs
 *
 * Version: v0.8.494 · Build: 494 · 2026-07-21
 * Beleg: Bauplan Platzhalter_DB §2.3; mc-Wunsch 2026-07-20/21.
 */

(function() {
'use strict';

// ---------------------------------------------------------------------------
// DEV-Logging (fuer PROD ueber window.FORENSIC_DEBUG = false abschaltbar).
// ---------------------------------------------------------------------------
function _dbg(...args) {
    if (typeof window !== 'undefined' && window.FORENSIC_DEBUG !== false) {
        try { console.debug('[PlaceholderDefs]', ...args); } catch (_) {}
    }
}

const LIBRARY_API = '/_forensic/placeholders/library';

// Der geladene Index (id -> def). null = noch nie geladen (Unterschied zu {} =
// geladen, aber keine m/o-Definitionen vorhanden — kein Ladezustand).
let _defs    = null;
let _loading = null;   // laufendes Versprechen (verhindert Mehrfachabruf)

/**
 * Baut aus der Bibliotheksantwort einen Index der m/o-Definitionen.
 * a-Platzhalter werden ausgelassen (sie nehmen an der Feldpruefung nicht teil).
 * @param {Array} items
 * @returns {Object<string, object>}
 */
function _index(items) {
    const idx = Object.create(null);
    for (const it of (Array.isArray(items) ? items : [])) {
        if (!it || (it.type !== 'm' && it.type !== 'o')) continue;
        if (it.id == null) continue;
        idx[String(it.id)] = {
            id:              String(it.id),
            type:            it.type,
            title:           it.title ?? '',
            description:     it.description ?? '',
            default_value:   it.default_value ?? null,
            validation:      it.validation ?? null,
            validation_type: it.validation_type ?? null,
            // Build 497: case-insensitive-Flag (0/1) fuer die Feldpruefung.
            validation_ci:   it.validation_ci ? 1 : 0,
        };
    }
    return idx;
}

/**
 * Laedt die Bibliothek. Mehrfachaufrufe teilen sich EIN Versprechen.
 * Im Fehlerfall wird {} gesetzt (geladen, aber leer) und geloggt
 * (Grundregel 1: kein stilles Zurueckfallen auf 'keine Regeln').
 * @returns {Promise<Object>} der Index (im Fehlerfall {})
 */
async function load() {
    if (_defs !== null) return _defs;
    if (_loading)       return _loading;

    _loading = (async () => {
        try {
            const resp = await fetch(LIBRARY_API, {
                headers: { 'X-Forensic-Request': 'ajax' },
            });
            if (!resp.ok) {
                console.error(
                    '[PlaceholderDefs] Bibliothek konnte nicht geladen werden ' +
                    '(HTTP ' + resp.status + '). m/o-Felder werden im Browser ' +
                    'NICHT gegen die DB-Definition geprueft; der Server prueft ' +
                    'beim Einreichen.'
                );
                _defs = {};
                return _defs;
            }
            const data = await resp.json();
            _defs = _index(data);
            _dbg('geladen:', Object.keys(_defs).length, 'm/o-Definitionen');
            return _defs;
        } catch (err) {
            console.error('[PlaceholderDefs] Laden fehlgeschlagen:', err);
            _defs = {};
            return _defs;
        } finally {
            _loading = null;
        }
    })();

    return _loading;
}

function isLoaded() {
    return _defs !== null;
}

/**
 * @param {string} id  Platzhalter-ID (= m/o-Token-Name)
 * @returns {object|null} Definition oder null (unbekannt / noch nicht geladen)
 */
function get(id) {
    if (!_defs || id == null) return null;
    return _defs[String(id)] || null;
}

/**
 * Flache Kopie aller m/o-Definitionen (id -> def). Leeres Objekt wenn nicht
 * geladen.
 * @returns {Object<string, object>}
 */
function all() {
    return _defs ? { ..._defs } : {};
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------
window.PlaceholderDefs = {
    load,
    isLoaded,
    get,
    all,
    // Nur fuer Tests: Index direkt setzen, ohne HTTP.
    _setForTest(items) { _defs = _index(items); },
    // Nur fuer Tests: Ladezustand zuruecksetzen (erzwingt beim naechsten load()
    // den echten fetch-Pfad).
    _resetForTest() { _defs = null; _loading = null; },
};

_dbg('placeholder_defs.js geladen — window.PlaceholderDefs exportiert');

})();
