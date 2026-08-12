// =============================================================================
// management/server/static/cockpit_vorlage_vorschau.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Dokumentvorlagen
// =============================================================================
// Zweck:
//   Die schreibgeschuetzte Vorschau einer ganzen DOKUMENTVORLAGE
//   (report_templates). Sie zeigt die Blockliste so, wie der Ermittler den
//   daraus erzeugten Vermerk spaeter im Berichtseditor sieht.
//
//   Ticket b47ce019 ("Schritt 3"), Teil 1 von 2. Die EINGABE folgt in einem
//   eigenen Build; diese Datei ruehrt keinen Speicherweg an.
//
// ── WARUM EINE EIGENE DATEI UND NICHT DIE BAUSTEINVORSCHAU ──────────────────
//
//   Die beiden sehen gleich aus und sind es nicht:
//
//     Baustein          GENAU EIN Block  (report_modules: block_type +
//                       block_data, dazu ein SQL-CHECK auf sechs Arten)
//     Dokumentvorlage   eine LISTE       (report_templates.blocks_json,
//                       neun Arten, kein CHECK)
//
//   Eine Vorschau, die beides koennte, muesste an jeder Stelle fragen, was
//   sie gerade ist. Getrennt sind es zwei kurze Bauteile, die je eine Sache
//   tun (Projektregel 10).
//
//   GETEILT WIRD, WAS WIRKLICH GEMEINSAM IST: die Werkzeugliste und die
//   Pruefung auf fehlende Dateien kommen aus cockpit_baustein_vorschau.js
//   (werkzeuge / fehlendeTeile). Eine zweite Werkzeugliste waere eine zweite
//   Wahrheit - dieselbe Begruendung wie in Build 656.
//
// ── WAS DIE VORLAGE OHNE UMFORMUNG ANZEIGBAR MACHT ──────────────────────────
//
//   blocks_json fuehrt bereits [{block_type, block_data}, ...] - genau die
//   Gestalt, die Editor.js erwartet, nur mit anderen Feldnamen. Es ist also
//   nichts zu RATEN und nichts aus einem Klartext zurueckzugewinnen; das
//   Ticket sagt das selbst ("die Vorschau kann sie ohne Umformung anzeigen").
//   Die Umbenennung block_type -> type ist die einzige Beruehrung, und sie
//   ist verlustfrei: block_data wird UNVERAENDERT durchgereicht.
//
// ── NICHT DARSTELLBARE BLOCKARTEN ───────────────────────────────────────────
//
//   Von den neun erlaubten Arten hat 'evidence' im Buendel kein Werkzeug und
//   bekommt den benannten deutschen Platzhalter (cockpit_unbekannter_block.js).
//   'marker' als eigenstaendiger BLOCK faellt auf den eingebauten - englischen -
//   Ersatz von Editor.js, weil der Name 'marker' fuer das Inline-Werkzeug
//   gebraucht wird; ohne dieses wuerde <mark> aus jedem Absatztext entfernt
//   (gemessen 12.08.2026). Damit der Redakteur nicht raten muss, NENNT diese
//   Vorschau solche Bloecke ueber der Flaeche - mit Nummer und Art.
//
//   IN KEINEM FALL GEHEN DATEN VERLOREN: gemessen am 12.08.2026 kommen die
//   Daten nicht darstellbarer Bloecke aus Editor.js byteweise identisch
//   zurueck. Diese Vorschau liest ohnehin nichts zurueck - sie ist
//   schreibgeschuetzt.
//
// Version: v0.8.705 · Build: 705 · 2026-08-12
// Beleg: Ticket b47ce019; templates.db.schema.sql:64-78 (report_templates);
//        report_render/report_source.py:59-62 (KNOWN_BLOCK_TYPES);
//        management/server/static/cockpit_baustein_vorschau.js (geteilte
//        Werkzeugliste); Messungen Editor.js 2.31.6 vom 12.08.2026.
// =============================================================================

(function () {
    'use strict';

    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Vorlagenvorschau]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN — vitest, ohne DOM und ohne Editor.js.
    // =========================================================================

    /**
     * bloeckeAus: aus der gespeicherten Blockliste die Editor.js-Blockliste.
     *
     * EINGANG  [{block_type, block_data}, ...]  (so steht es in blocks_json)
     * AUSGANG  [{type, data}, ...]              (so will es Editor.js)
     *
     * ES WIRD NUR UMBENANNT. block_data geht unveraendert weiter - kein
     * Kopieren, kein Auffuellen, kein Normalisieren. Jede dieser
     * Bequemlichkeiten waere eine Aenderung an Daten, die diese Vorschau nur
     * ANZEIGEN soll.
     *
     * EIN BLOCK OHNE ART WIRD NICHT UEBERSPRUNGEN (Grundregel 1): er bekommt
     * die Art '' und faellt damit auf den Ersatzblock - sichtbar, zaehlbar
     * und in der Meldung ueber der Flaeche benannt. Stillschweigend
     * auszulassen hiesse, eine luecke im Aufbau der Vorlage zu verstecken.
     */
    function bloeckeAus(bloecke) {
        return (Array.isArray(bloecke) ? bloecke : []).map(function (b) {
            var q = b || {};
            var daten = (q.block_data && typeof q.block_data === 'object')
                ? q.block_data : {};
            return { type: (q.block_type === undefined
                            || q.block_type === null)
                        ? '' : String(q.block_type),
                     data: daten };
        });
    }

    /**
     * nichtDarstellbare: welche Bloecke der Liste hat kein echtes Werkzeug?
     *
     * Rueckgabe [{nummer, art}] mit NUMMER AB 1 - der Redakteur zaehlt seine
     * Bloecke von oben, nicht ab null.
     *
     * 'werkzeugNamen' ist die Liste der wirklich registrierten Werkzeuge;
     * sie wird hereingereicht statt hier ermittelt, damit diese Funktion
     * ohne Editor.js prueffbar bleibt und nicht ein zweites Mal entscheidet,
     * was registriert ist.
     *
     * 'ersatzNamen' sind Namen, die zwar in der Werkzeugliste STEHEN, einen
     * BLOCK dieser Art aber nicht darstellen. Heute sind das zwei, aus
     * verschiedenen Gruenden:
     *   'evidence'  wird vom Ersatzwerkzeug bedient (kein echtes Werkzeug
     *               im Buendel).
     *   'marker'    ist unter diesem Namen ein INLINE-Werkzeug. Ein Block
     *               dieser Art faellt auf den eingebauten Ersatz von
     *               Editor.js - der Name ist belegt und kann nicht doppelt
     *               vergeben werden (siehe cockpit_baustein_vorschau.js).
     * Ohne diese Liste meldete die Vorschau Entwarnung fuer genau die
     * Bloecke, wegen derer es sie gibt: 'marker' STEHT in der Werkzeugliste
     * und saehe damit darstellbar aus.
     */
    function nichtDarstellbare(bloecke, werkzeugNamen, ersatzNamen) {
        var kennt = {};
        (werkzeugNamen || []).forEach(function (n) { kennt[n] = true; });
        var ersatz = {};
        (ersatzNamen || []).forEach(function (n) { ersatz[n] = true; });

        var raus = [];
        (Array.isArray(bloecke) ? bloecke : []).forEach(function (b, i) {
            var art = (b && b.type) ? String(b.type) : '';
            if (!art || !kennt[art] || ersatz[art]) {
                raus.push({ nummer: i + 1, art: art || '(ohne Art)' });
            }
        });
        return raus;
    }

    /**
     * meldungText: der Satz ueber der Vorschau. Rein, damit der Wortlaut
     * pruefbar ist, ohne einen Editor zu bauen.
     *
     * Der Satz hat EINEN Zweck: verhindern, dass der graue Ersatzblock als
     * Datenverlust gelesen wird. Deshalb steht die Entwarnung im selben Satz
     * wie der Befund und nicht darunter.
     */
    function meldungText(fehlende) {
        if (!fehlende || !fehlende.length) { return ''; }
        var teile = fehlende.map(function (f) {
            return 'Block ' + f.nummer + ' («' + f.art + '»)';
        });
        var eins = (teile.length === 1);
        return (eins ? 'Ein Block lässt sich' : teile.length
                        + ' Blöcke lassen sich')
            + ' hier nicht darstellen: ' + teile.join(', ')
            + '. Der Inhalt ist vollständig vorhanden und wird gespeichert — '
            + 'nur die Anzeige fehlt.';
    }

    // =========================================================================
    // 2) VORSCHAU (DOM).
    // =========================================================================

    function _el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    /**
     * erzeuge(hostEl, opts) -> { zeige(bloecke), aus(), istOffen() }
     *   opts.EditorCtor / opts.win / opts.vorschau — injizierbar (Tests)
     *
     * 'zeige' nimmt die Liste in der GESPEICHERTEN Gestalt
     * ([{block_type, block_data}]), nicht in der von Editor.js. So muss die
     * aufrufende Sicht nichts umbauen, und die Umbenennung liegt an genau
     * einer Stelle.
     */
    function erzeuge(hostEl, opts) {
        opts = opts || {};
        var w = opts.win || (typeof window !== 'undefined' ? window : {});
        var Ctor = opts.EditorCtor || w.EditorJS;
        // Die Bausteinvorschau ist die gemeinsame Quelle fuer Werkzeugliste
        // und Vollstaendigkeitspruefung.
        var vs = opts.vorschau || w.AIWBausteinVorschau;

        var meldung = _el('p', 'aiw-dtpl-vorschau-meldung', '');
        var rumpf = _el('div', 'aiw-dtpl-vorschau-rumpf');
        hostEl.textContent = '';
        hostEl.appendChild(meldung);
        hostEl.appendChild(rumpf);

        var instanz = null;
        var letzterStand = null;

        function melde(text, art) {
            meldung.textContent = text || '';
            meldung.className = 'aiw-dtpl-vorschau-meldung'
                + (art ? (' ist-' + art) : '');
        }

        function abbauen() {
            // Editor.js haengt Horcher an das Dokument. Ohne destroy() bleiben
            // bei jeder Aktualisierung Instanzen zurueck, und die Maske wird
            // langsamer, bis sie steht. (Dasselbe Vorgehen wie in der
            // Bausteinvorschau, aus demselben gemessenen Grund.)
            if (instanz && typeof instanz.destroy === 'function') {
                try { instanz.destroy(); } catch (e) { log('destroy', e); }
            }
            instanz = null;
            rumpf.textContent = '';
        }

        function zeige(bloecke) {
            if (!vs || typeof vs.werkzeuge !== 'function'
                    || typeof vs.fehlendeTeile !== 'function') {
                abbauen();
                melde('Vorschau nicht möglich — cockpit_baustein_vorschau.js '
                      + 'ist nicht geladen.', 'warnung');
                return null;
            }
            var fehlt = vs.fehlendeTeile(w);
            if (fehlt.length) {
                abbauen();
                // KEIN STILLER AUSFALL: die fehlende Datei wird GENANNT.
                // Eine leere Flaeche saehe wie eine leere Vorlage aus.
                melde('Vorschau nicht möglich — es fehlt: '
                      + fehlt.join(', ') + '.', 'warnung');
                return null;
            }

            var liste = bloeckeAus(bloecke);
            var stand = JSON.stringify(liste);
            if (stand === letzterStand && instanz) {
                // Unveraendert: nicht neu aufbauen, sonst flackert die
                // Vorschau bei jedem Tastendruck.
                return instanz;
            }
            letzterStand = stand;
            abbauen();

            var wz = vs.werkzeuge(w, 'vorlage');
            // 'evidence' und 'marker' STEHEN in der Werkzeugliste, stellen
            // einen BLOCK dieser Art aber nicht dar (Ersatzwerkzeug bzw.
            // Inline-Werkzeug). Die Liste steht hier und nicht in der reinen
            // Funktion, weil sie davon abhaengt, was werkzeuge() gerade
            // zusammenstellt - eine zweite Aufzaehlung dort liefe der ersten
            // irgendwann davon.
            var fehlende = nichtDarstellbare(liste, Object.keys(wz),
                                             ['evidence', 'marker']);
            melde(meldungText(fehlende), fehlende.length ? 'hinweis' : null);

            if (!liste.length) {
                melde('Diese Vorlage enthält noch keinen Block.', 'hinweis');
                return null;
            }

            try {
                instanz = new Ctor({
                    holder: rumpf,
                    readOnly: true,
                    minHeight: 0,
                    tools: wz,
                    data: { blocks: liste }
                });
            } catch (e) {
                instanz = null;
                melde('Vorschau fehlgeschlagen: ' + (e && e.message),
                      'warnung');
                log('Editor.js Aufbau fehlgeschlagen', e);
                return null;
            }
            log('Vorschau aufgebaut, Bloecke:', liste.length);
            return instanz;
        }

        return {
            zeige: zeige,
            aus: function () { abbauen(); letzterStand = null; melde(''); },
            istOffen: function () { return instanz !== null; }
        };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        bloeckeAus: bloeckeAus,
        nichtDarstellbare: nichtDarstellbare,
        meldungText: meldungText,
        erzeuge: erzeuge
    };
    if (typeof window !== 'undefined') { window.AIWVorlagenVorschau = API; }
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    log('geladen');
})();
