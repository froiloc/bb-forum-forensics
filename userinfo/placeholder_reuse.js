/**
 * userinfo/placeholder_reuse.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * ZWECK (Build 495)
 *   Case-weite Wiederverwendung von m/o-Ermittlerwerten (mc-Wunsch).
 *   Ein einmal eingetragener Wert eines bekannten m/o-Platzhalters wird im Fall
 *   (uid) im placeholder_cache vorgehalten und kann in anderen Vermerken
 *   desselben Falls als Vorschlag uebernommen werden.
 *
 *       GET  /_forensic/placeholders/cache?ids=a,b,c  -> { id: value }   (Prefill)
 *       POST /_forensic/placeholders/cache {id,value}  -> { ok, id }      (Writeback)
 *
 *   Der Server laesst beim Writeback NUR bekannte m/o-Platzhalter zu (Schutz
 *   des {{a:}}-Auto-Caches). Dieser Client haelt einen lokalen {id:value}-Cache
 *   fuer die aktuelle Formularsicht.
 *
 * ABGRENZUNG
 *   Reine Werte-Wiederverwendung. Die Validierung der Werte kommt aus
 *   PlaceholderDefs/ValidationRules (Build 494); die Stammvater/Klon-Mechanik
 *   (innerhalb EINES Vermerks) aus PlaceholderLinks (Build 491/492). Die
 *   fallweite Wiederverwendung ist VERMERK-UEBERGREIFEND und davon getrennt.
 *
 * OEFFENTLICHE API (window.PlaceholderReuse)
 *   await window.PlaceholderReuse.loadCache(ids) -- {id:value} fuer ids laden
 *   window.PlaceholderReuse.getCached(id)        -- Wert | null (aus lokalem Cache)
 *   await window.PlaceholderReuse.writeback(id, value) -- Wert case-weit sichern
 *   window.PlaceholderReuse.isLoaded()
 *
 * Version: v0.8.495 · Build: 495 · 2026-07-21
 * Beleg: mc-Wunsch 2026-07-20/21; forensic_api/placeholders.py handle_cache_*.
 */

(function() {
'use strict';

function _dbg(...args) {
    if (typeof window !== 'undefined' && window.FORENSIC_DEBUG !== false) {
        try { console.debug('[PlaceholderReuse]', ...args); } catch (_) {}
    }
}

const CACHE_API = '/_forensic/placeholders/cache';

// Lokaler {id:value}-Cache. null = noch nie geladen.
let _cache = null;

/**
 * Laedt die gecachten m/o-Werte fuer die angegebenen IDs und MERGT sie in den
 * lokalen Cache (mehrere Aufrufe mit verschiedenen ID-Mengen ergaenzen sich).
 * Fehler -> lokaler Cache bleibt/wird {} (kein stiller Ausfall: geloggt).
 * @param {Array<string>} ids
 * @returns {Promise<Object>} der lokale Cache
 */
async function loadCache(ids) {
    const list = (ids || []).map(String).filter(s => s.trim() !== '');
    if (!list.length) {
        if (_cache === null) _cache = {};
        return _cache;
    }
    try {
        const qs   = encodeURIComponent(list.join(','));
        const resp = await fetch(`${CACHE_API}?ids=${qs}`, {
            headers: { 'X-Forensic-Request': 'ajax' },
        });
        if (!resp.ok) {
            console.error('[PlaceholderReuse] Cache-Laden fehlgeschlagen (HTTP '
                + resp.status + '). Kein Prefill fuer diese Sicht.');
            if (_cache === null) _cache = {};
            return _cache;
        }
        const data = await resp.json();
        _cache = { ...(_cache || {}), ...(data && typeof data === 'object' ? data : {}) };
        _dbg('geladen:', Object.keys(_cache).length, 'Werte im lokalen Cache');
        return _cache;
    } catch (err) {
        console.error('[PlaceholderReuse] Cache-Laden fehlgeschlagen:', err);
        if (_cache === null) _cache = {};
        return _cache;
    }
}

function isLoaded() {
    return _cache !== null;
}

/**
 * @param {string} id
 * @returns {string|null} gecachter Wert oder null
 */
function getCached(id) {
    if (!_cache || id == null) return null;
    const v = _cache[String(id)];
    return (v == null || v === '') ? null : String(v);
}

/**
 * Schreibt einen m/o-Wert case-weit zurueck (Writeback). Fire-and-forget:
 * Erfolg aktualisiert den lokalen Cache; Fehler werden geloggt, aber nicht
 * geworfen (die lokale Speicherung des Wertes ist bereits ueber onSave
 * erfolgt — das Writeback ist nur die case-weite Kopie).
 * @param {string} id
 * @param {string} value
 * @returns {Promise<boolean>} true bei erfolgreichem Writeback
 */
async function writeback(id, value) {
    if (id == null || String(id).trim() === '') return false;
    try {
        const resp = await fetch(CACHE_API, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json; charset=utf-8',
                'X-Forensic-Request': 'ajax',
            },
            body: JSON.stringify({ id: String(id), value: String(value == null ? '' : value) }),
        });
        if (!resp.ok) {
            // 400 = nicht wiederverwendbar (unbekannt/kein m/o) — kein Fehlerfall
            // fuer den Ermittler, nur kein case-weiter Vorschlag.
            _dbg('Writeback nicht gespeichert fuer', id, '(HTTP ' + resp.status + ')');
            return false;
        }
        if (_cache === null) _cache = {};
        _cache[String(id)] = String(value == null ? '' : value);
        _dbg('Writeback ok:', id);
        return true;
    } catch (err) {
        console.error('[PlaceholderReuse] Writeback fehlgeschlagen:', id, err);
        return false;
    }
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------
window.PlaceholderReuse = {
    loadCache,
    getCached,
    writeback,
    isLoaded,
    // Nur fuer Tests: lokalen Cache direkt setzen / zuruecksetzen.
    _setForTest(map) { _cache = map ? { ...map } : {}; },
    _resetForTest() { _cache = null; },
};

_dbg('placeholder_reuse.js geladen — window.PlaceholderReuse exportiert');

})();
