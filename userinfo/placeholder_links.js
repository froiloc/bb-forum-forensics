/**
 * userinfo/placeholder_links.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   REINE, testbare Verknuepfungslogik fuer die "Stammvater/Klon"-Mechanik
 *   der m:/o:-Platzhalter (Platzhalter-Neuordnung, Slice 3, mc-Wunsch).
 *
 *   Fachlicher Hintergrund (mc-Wunsch, Projektgespraech 2026-07-20/21):
 *     Ein Vermerk (= ein Bericht) kann denselben m:/o:-Platzhalternamen in
 *     mehreren Bloecken enthalten (z.B. eine Spurennummer, die in Kopf,
 *     Feststellung und Fazit erscheint). Der Ermittler soll den Wert nur EINMAL
 *     eintragen muessen: Das erste Feld eines Namens, das explizit befuellt
 *     wird, ist der STAMMVATER. Alle noch nicht explizit befuellten Felder
 *     desselben Namens sind KLONE und spiegeln den Stammvater-Wert LIVE — bis
 *     ein Klon selbst einen eigenen (expliziten) Wert bekommt und sich damit
 *     abkoppelt (wird "eigenstaendig").
 *
 *   Sichtbare Markierung (Slice 3): Stammvater- und Klon-Felder werden im
 *   Formular optisch gekennzeichnet. classify() liefert dafuer die Rolle.
 *
 * ABGRENZUNG / SCOPE (Build 491):
 *   Dieses Modul ist BEWUSST eine reine Funktionsbibliothek OHNE DOM- und OHNE
 *   Persistenz-Zugriff. Es haengt weder an PlaceholderChips noch am DOM und ist
 *   damit unter Node/vitest vollstaendig testbar (Grundregeln 2/3: jede Version
 *   lauffaehig+getestet). Die tatsaechliche Verdrahtung in placeholder_wizard.js
 *   (Input-Events -> applyInput -> updates in den DOM schreiben, Rollen als
 *   CSS-Klassen setzen) sowie die Frage, WIE die Unterscheidung
 *   explizit/Klon persistiert wird, sind FOLGE-Builds (492+). Letzteres beruehrt
 *   die block-bezogene placeholder_values_json in evidence_<uid>.db und steht
 *   damit ab 01.07.2026 unter Migrationsvorbehalt (Datenmigrationsleitfaden) —
 *   deshalb hier zunaechst nur die reine Referenz-Algorithmik.
 *
 * Datenmodell (rein, serialisierbar):
 *   fieldRef  = { blockId: string, name: string, type: 'm'|'o' }
 *   state     = {
 *     order:    Array<fieldRef>            // Dokumentreihenfolge, nur m/o
 *     byName:   { [name]: Array<fieldRef> }// Gruppierung nach Name, Dok.-Reihenfolge
 *     explicit: { [fieldKey]: true }       // Felder mit EIGENEM expliziten Wert
 *     values:   { [fieldKey]: string }     // explizite Werte (Stammvater/eigenst.)
 *     master:   { [name]: blockId|null }   // Stammvater-blockId je Name
 *   }
 *   Ein Feld wird ueber (blockId, name) identifiziert; ein Name kann in
 *   mehreren Bloecken vorkommen, aber pro Block hoechstens einmal.
 *
 * Exports (window.PlaceholderLinks):
 *   fieldKey(blockId, name) -> string
 *   createState(fieldRefs, explicitValues) -> state
 *   applyInput(state, blockId, name, rawValue) -> { state, updates }
 *       updates: Array<{ blockId, name, value }> — Klon-Felder, deren
 *       angezeigter Wert sich AENDERT (an den DOM zu propagieren); enthaelt
 *       NICHT das gerade getippte Feld selbst.
 *   displayValue(state, blockId, name) -> string
 *   classify(state, blockId, name) -> 'stammvater'|'klon'|'eigenstaendig'|'leer'
 *
 * Version: v0.8.491 · Build: 491 · 2026-07-21
 * Beleg: mc-Wunsch Platzhalter-Neuordnung Slice 3 (Stammvater/Klon),
 *        Bauplan_Platzhalter_DB §Slice3; Grundregel 1 (kein stiller Verlust).
 */

(function() {
'use strict';

// ---------------------------------------------------------------------------
// DEV-Logging (Projektvorgabe JS-Gebot 2: exzessives Debug-Logging, fuer PROD
// ueber window.FORENSIC_DEBUG = false abschaltbar).
// ---------------------------------------------------------------------------
/** @param {...*} args */
function _dbg(...args) {
    if (typeof window !== 'undefined' && window.FORENSIC_DEBUG !== false) {
        // console.debug ist unter vitest/jsdom vorhanden; im Zweifel No-op.
        try { console.debug('[forensic:links]', ...args); } catch (_) {}
    }
}

// ---------------------------------------------------------------------------
// Interne Hilfsfunktionen (gekapselt, nicht exportiert)
// ---------------------------------------------------------------------------

// Unit-Separator (U+001F) als Trenner im Feldschluessel. Bewusst ein Zeichen,
// das in blockId/name nicht vorkommen kann — so ist die Zerlegung eindeutig
// und es gibt keine Kollision zwischen z.B. ("a", "b:c") und ("a:b", "c").
const _SEP = '';

/**
 * Bildet den eindeutigen Feldschluessel aus (blockId, name).
 * @param {string} blockId
 * @param {string} name
 * @returns {string}
 */
function fieldKey(blockId, name) {
    return String(blockId) + _SEP + String(name);
}

/**
 * Prueft, ob ein Rohwert als "explizit befuellt" gilt.
 * Leerzeichen-only zaehlt als leer (der Ermittler hat nichts Belegbares
 * eingetragen). Ein Klon kann daher NICHT durch Loeschen "leer eigenstaendig"
 * werden — er faellt zurueck auf den Stammvater (siehe applyInput).
 * @param {*} raw
 * @returns {boolean}
 */
function _isFilled(raw) {
    return String(raw ?? '').trim() !== '';
}

/**
 * Waehlt den Stammvater eines Namens: das ERSTE Feld in Dokumentreihenfolge,
 * das aktuell einen eigenen expliziten Wert hat. Wird nur zur NEU-Wahl nach
 * dem Loeschen des bisherigen Stammvaters benutzt. Die ERST-Wahl geschieht
 * chronologisch in applyInput (das zuerst befuellte Feld), da der mc-Wunsch
 * explizit vom "ersten explizit befuellten Feld" spricht.
 * @param {object} state
 * @param {string} name
 * @returns {string|null} blockId des neuen Stammvaters oder null
 */
function _electMaster(state, name) {
    const group = state.byName[name] || [];
    for (const ref of group) {
        if (state.explicit[fieldKey(ref.blockId, name)]) {
            return ref.blockId;
        }
    }
    return null;
}

/**
 * Interne Kopie des Zustands (flach, aber mit frischen Sub-Objekten), damit
 * applyInput den uebergebenen Zustand nicht mutiert (reine Funktion, gut
 * testbar). order/byName/fieldRefs sind unveraenderlich und werden geteilt.
 */
function _cloneState(state) {
    return {
        order:    state.order,
        byName:   state.byName,
        explicit: { ...state.explicit },
        values:   { ...state.values },
        master:   { ...state.master },
    };
}

// ---------------------------------------------------------------------------
// Oeffentliche API
// ---------------------------------------------------------------------------

/**
 * Baut den Anfangszustand aus der Feldliste (Dokumentreihenfolge) und den
 * bereits explizit gesetzten Werten.
 *
 * Nur m/o-Felder nehmen an der Verknuepfung teil (a-Platzhalter werden nie im
 * Formular angezeigt). Andere Typen werden ignoriert.
 *
 * Die Erst-Wahl des Stammvaters erfolgt hier deterministisch in
 * Dokumentreihenfolge (erstes explizites Feld je Name) — beim frischen Laden
 * einer Akte ist keine Tipp-Chronologie bekannt, also ist die Dokumentordnung
 * die einzige belegbare Reihenfolge.
 *
 * @param {Array<{blockId:string,name:string,type:string}>} fieldRefs
 * @param {Object<string,string>} [explicitValues]  fieldKey -> Wert
 * @returns {object} state
 */
function createState(fieldRefs, explicitValues) {
    const order  = [];
    const byName = Object.create(null);

    for (const ref of (fieldRefs || [])) {
        if (ref.type !== 'm' && ref.type !== 'o') continue;
        const clean = { blockId: String(ref.blockId), name: String(ref.name), type: ref.type };
        order.push(clean);
        (byName[clean.name] = byName[clean.name] || []).push(clean);
    }

    const explicit = Object.create(null);
    const values   = Object.create(null);
    const src      = explicitValues || {};

    for (const ref of order) {
        const k = fieldKey(ref.blockId, ref.name);
        if (Object.prototype.hasOwnProperty.call(src, k) && _isFilled(src[k])) {
            explicit[k]  = true;
            values[k]    = String(src[k]);
        }
    }

    const master = Object.create(null);
    for (const name of Object.keys(byName)) {
        // Erst-Stammvater = erstes explizites Feld in Dokumentreihenfolge.
        master[name] = null;
        for (const ref of byName[name]) {
            if (explicit[fieldKey(ref.blockId, name)]) {
                master[name] = ref.blockId;
                break;
            }
        }
    }

    _dbg('createState:', order.length, 'Felder,',
         Object.keys(byName).length, 'Namen');
    return { order, byName, explicit, values, master };
}

/**
 * Effektiv angezeigter Wert eines Feldes:
 *   - eigener expliziter Wert, falls vorhanden;
 *   - sonst der Stammvater-Wert (Klon spiegelt live), falls ein Stammvater
 *     existiert;
 *   - sonst leer.
 * @returns {string}
 */
function displayValue(state, blockId, name) {
    const k = fieldKey(blockId, name);
    if (state.explicit[k]) return state.values[k];
    const m = state.master[name];
    if (m != null) return state.values[fieldKey(m, name)] ?? '';
    return '';
}

/**
 * Rolle eines Feldes fuer die optische Markierung:
 *   'stammvater'    -- explizit UND aktueller Stammvater des Namens
 *   'eigenstaendig' -- explizit, aber NICHT Stammvater (eigener Wert, folgt nicht)
 *   'klon'          -- nicht explizit, aber es existiert ein Stammvater (spiegelt)
 *   'leer'          -- nicht explizit und (noch) kein Stammvater
 * @returns {string}
 */
function classify(state, blockId, name) {
    const k = fieldKey(blockId, name);
    if (state.explicit[k]) {
        return state.master[name] === blockId ? 'stammvater' : 'eigenstaendig';
    }
    return state.master[name] != null ? 'klon' : 'leer';
}

/**
 * Verarbeitet eine Eingabe (Input-Event) auf einem Feld und liefert den neuen
 * Zustand plus die Liste der KLON-Felder, deren angezeigter Wert sich dadurch
 * aendert (vom DOM-Layer nachzuziehen). Das getippte Feld selbst ist NIE in
 * updates enthalten (der DOM haelt es bereits).
 *
 * Faelle:
 *  A) Nicht-leerer Wert:
 *     - Feld wird explizit; Wert gespeichert.
 *     - Falls fuer den Namen noch KEIN Stammvater existiert -> dieses Feld wird
 *       Stammvater (mc: "erstes explizit befuelltes Feld").
 *     - Ist dieses Feld der Stammvater -> Wert an alle Klone propagieren.
 *     - Ist es ein eigenstaendiges (explizites Nicht-Stammvater-)Feld -> nur der
 *       eigene Wert aendert sich, keine Propagation.
 *  B) Leerer Wert (Loeschen):
 *     - War das Feld der Stammvater -> Neuwahl (erstes verbleibendes explizites
 *       Feld in Dok.-Reihenfolge); Klone spiegeln den neuen Stammvater (oder
 *       werden leer). So bleibt kein verwaister Klon-Wert stehen (Grundregel 1:
 *       kein stiller Beleg).
 *     - War das Feld eigenstaendig -> es wird wieder Klon und spiegelt den
 *       Stammvater (sein alter eigener Wert wird verworfen).
 *     - War das Feld bereits ein Klon -> es bleibt Klon; der Stammvater-Wert
 *       wird zurueckgespiegelt (ein Klon laesst sich nicht "leeren", er folgt
 *       dem Stammvater — mc: folgt, bis er einen EIGENEN Wert bekommt).
 *
 * @returns {{state: object, updates: Array<{blockId:string,name:string,value:string}>}}
 */
function applyInput(state, blockId, name, rawValue) {
    const s   = _cloneState(state);
    const k   = fieldKey(blockId, name);
    const grp = s.byName[name] || [];
    const wasMaster = s.master[name] === blockId;
    const updates = [];

    if (_isFilled(rawValue)) {
        // --- Fall A: expliziter Wert -------------------------------------
        const value = String(rawValue);
        s.explicit[k] = true;
        s.values[k]   = value;

        if (s.master[name] == null) {
            // Erst-Befuellung: dieses Feld wird Stammvater.
            s.master[name] = blockId;
            _dbg('applyInput: neuer Stammvater', name, '=', blockId);
        }

        if (s.master[name] === blockId) {
            // Stammvater aktualisiert -> alle Klone nachziehen.
            for (const ref of grp) {
                if (ref.blockId === blockId) continue;
                const rk = fieldKey(ref.blockId, name);
                if (!s.explicit[rk]) {
                    updates.push({ blockId: ref.blockId, name, value });
                }
            }
        }
        // Eigenstaendiges Feld (explizit, nicht Stammvater): keine Propagation.
    } else {
        // --- Fall B: geleert ---------------------------------------------
        const wasExplicit = !!s.explicit[k];
        delete s.explicit[k];
        delete s.values[k];

        if (wasMaster) {
            // Stammvater geloescht -> Neuwahl unter den verbleibenden expliziten.
            const newMaster = _electMaster(s, name);
            s.master[name]  = newMaster;
            const newVal = newMaster != null
                ? (s.values[fieldKey(newMaster, name)] ?? '')
                : '';
            _dbg('applyInput: Stammvater geloescht', name,
                 '-> Neuwahl', newMaster);
            for (const ref of grp) {
                if (ref.blockId === newMaster) continue;
                const rk = fieldKey(ref.blockId, name);
                if (!s.explicit[rk]) {
                    // Klon (inkl. des gerade geleerten Feldes) auf neuen Wert.
                    updates.push({ blockId: ref.blockId, name, value: newVal });
                }
            }
        } else {
            // Nicht-Stammvater geleert. Falls es eigenstaendig war, wird es
            // jetzt Klon; in beiden Faellen spiegelt es den Stammvater zurueck.
            const m = s.master[name];
            const mirror = m != null ? (s.values[fieldKey(m, name)] ?? '') : '';
            // Das geleerte Feld selbst NICHT in updates (DOM haelt es); der
            // DOM-Layer setzt den Klon-Wert beim Re-Render bzw. ueber
            // displayValue(). War es ein echter Klon, aendert sich nichts.
            if (wasExplicit) {
                _dbg('applyInput: eigenstaendig -> Klon', name, blockId,
                     'spiegelt', JSON.stringify(mirror));
            }
            // Kein Push fuer andere Felder: das Loeschen eines Nicht-Stammvaters
            // beeinflusst keine ANDEREN Klone.
        }
    }

    return { state: s, updates };
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------
_dbg('placeholder_links.js: window.PlaceholderLinks exportiert');
window.PlaceholderLinks = {
    fieldKey,
    createState,
    applyInput,
    displayValue,
    classify,
};

})();
