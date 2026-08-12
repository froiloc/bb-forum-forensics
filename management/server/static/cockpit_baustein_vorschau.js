// =============================================================================
// management/server/static/cockpit_baustein_vorschau.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Bausteinverwaltung
// =============================================================================
// Zweck:
//   Die Vorschau eines Textbausteins (Build 577, Ticket 64edd18a). Sie zeigt
//   den Baustein so, wie ihn der Ermittler spaeter IM BERICHTSEDITOR sieht —
//   Editor.js im Nur-Lese-Modus, Platzhalter als farbige Chips.
//
// ── WARUM DIESE ANSICHT UND NICHT DIE EXPORTFASSUNG ─────────────────────────
//
//   Es gibt drei Darstellungen eines Bausteins, und sie unterscheiden sich:
//
//     Bearbeitungsansicht  Editor.js mit Schreibrechten  Chip + Werkzeugleisten
//     Nur-Lese-Ansicht     Editor.js ohne Schreibrechte  Chip            <— hier
//     Exportfassung        editor/html_renderer.py       roher Text
//
//   Ich hatte die Exportfassung empfohlen; mc hat widersprochen, und der Code
//   gibt ihm recht: html_renderer.py loest Platzhalter NICHT auf, es maskiert
//   nur Text. Dort stuende woertlich '{{a:username}}' — genau das "sehr
//   technisch", von dem das Ticket wegwill. Die Chips sind die eigentliche
//   Information: sie sagen, WELCHE Art Platzhalter (automatisch, pflichtig,
//   optional) an der Stelle steht, und das sieht man nur hier.
//
// ── WAS GETEILT WIRD UND WARUM ──────────────────────────────────────────────
//
//   Das Editor.js-Buendel und der Chip-Renderer liegen in Baustelle 6 und
//   werden seit Build 576 GETEILT ausgeliefert (/static/shared/...), nicht
//   kopiert. Eine Kopie waere eigener Code in doppelter Ausfuehrung — und die
//   naechste Chip-Aenderung wuerde nur an einer Stelle wirken.
//
// ── KEIN STILLER AUSFALL ────────────────────────────────────────────────────
//
//   Fehlt eine der geteilten Dateien, SAGT die Vorschau das und nennt die
//   Datei. Eine leere Flaeche saehe wie ein leerer Baustein aus, und das waere
//   die Sorte Auslassung, die Grundregel 1 verbietet.
//
// Version: v0.8.577 · Build: 577 · 2026-07-30
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
        args.unshift('[AIW-Bausteinvorschau]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    // blockAus: aus einem Baustein die Editor.js-Blockliste bauen.
    //
    // HEUTE ist ein Baustein IMMER ein Absatz: report_modules fuehrt kein
    // block_type, und der Berichtseditor fuegt ihn als 'paragraph' mit
    // { text } ein. Die Funktion ist aber schon auf den spaeteren Fall
    // vorbereitet (Build 578: block_type + block_data an report_modules) —
    // liegt ein Typ und ein Datensatz vor, werden sie unveraendert benutzt.
    // So muss die Vorschau spaeter nicht neu gebaut werden.
    //
    // 'chips' ist injizierbar, damit der Test ohne das geteilte Modul auskommt.
    function blockAus(modul, chips) {
        modul = modul || {};
        var typ = modul.block_type || 'paragraph';

        if (modul.block_data && typeof modul.block_data === 'object') {
            // Zukunft: der Baustein traegt seine Blockdaten selbst.
            return [{ type: typ, data: modul.block_data }];
        }

        var roh = String(modul.body === undefined || modul.body === null
                         ? '' : modul.body);
        var text = roh;
        if (chips && typeof chips.hydrateChips === 'function') {
            try {
                text = chips.hydrateChips(roh, {}, {});
            } catch (e) {
                // Der Rohtext ist besser als nichts — und der Fehler wird
                // benannt, nicht verschluckt.
                log('hydrateChips fehlgeschlagen', e);
                text = roh;
            }
        }
        return [{ type: typ === 'paragraph' ? 'paragraph' : typ,
                  data: { text: text } }];
    }

    // fehlendeTeile: was fuer die Vorschau fehlt. Rueckgabe [] heisst 'alles da'.
    // Genannt wird die DATEI, nicht nur "geht nicht" — sonst muss jemand raten.
    function fehlendeTeile(w) {
        w = w || (typeof window !== 'undefined' ? window : {});
        var fehlt = [];
        if (typeof w.EditorJS !== 'function') {
            fehlt.push('editor.bundle.js (EditorJS)');
        }
        if (!w.EditorTools) {
            fehlt.push('editor.bundle.js (EditorTools)');
        }
        if (!w.PlaceholderChips
                || typeof w.PlaceholderChips.hydrateChips !== 'function') {
            fehlt.push('placeholder_chips.js');
        }
        return fehlt;
    }

    // werkzeuge: die Werkzeugliste des Buendels, in ZWEI Umfaengen.
    // -------------------------------------------------------------------------
    // Build 705: Der zweite Umfang ist noetig, weil Bausteine und
    // Dokumentvorlagen NICHT dieselben Blockarten fuehren duerfen:
    //
    //   'baustein' (Vorgabe)  sechs Arten. Das ist keine Gestaltungsfrage,
    //                         sondern ein SQL-CHECK: templates.db.schema.sql
    //                         zwingt report_modules.block_type auf
    //                         paragraph|header|list|table|quote|delimiter.
    //                         Wuerde die Eingabe eine siebte Art anbieten,
    //                         liesse sich der Baustein anlegen und NICHT
    //                         speichern - der Fehler kaeme aus der Datenbank,
    //                         lange nach der Eingabe. Der Schema-Kommentar
    //                         (Zeile 16-21) sagt dazu ausdruecklich, dass
    //                         SQLite diesen CHECK nicht aendern kann.
    //
    //   'vorlage'             neun Arten (report_render/report_source.py:59-62,
    //                         KNOWN_BLOCK_TYPES). report_templates.blocks_json
    //                         hat keinen CHECK; geprueft wird anwendungsseitig.
    //
    // EINE FUNKTION, ZWEI UMFAENGE - und nicht zwei Funktionen: Build 656 hat
    // die Werkzeugliste bewusst an EINER Stelle zusammengefuehrt ("eine zweite
    // Liste waere eine zweite Wahrheit"). Diese Begruendung gilt weiter; was
    // dazukommt, ist nur der Umfang.
    //
    // ── ZUM NAMEN 'marker': EIN SCHLUESSEL, ZWEI BEDEUTUNGEN ──────────────
    //
    // 'marker' ist im Buendel ein INLINE-Werkzeug (Textstelle hervorheben) und
    // steht zugleich in KNOWN_BLOCK_TYPES als Blockart. Editor.js kennt je
    // Namen nur EIN Werkzeug - beides zugleich geht nicht.
    //
    // GEMESSEN am 12.08.2026 (Editor.js 2.31.6), beide Wege:
    //   MIT Inline-Marker   <mark> im Absatztext ueberlebt save().
    //                       Ein BLOCK vom Typ 'marker' behaelt seine Daten,
    //                       wird aber mit dem eingebauten Ersatz angezeigt.
    //   OHNE Inline-Marker  <mark> wird beim save() ENTFERNT - aus
    //                       "Ein Absatz mit <mark>Hervorhebung</mark> darin."
    //                       wird "Ein Absatz mit Hervorhebung darin."
    //
    // Der Name bleibt deshalb beim Inline-Werkzeug: die Hervorhebung im
    // Fliesstext ist der haeufige Fall und ihr Verlust waere ein echter, ein
    // marker-BLOCK ist der seltene und verliert nichts. Der Renderer sieht das
    // genauso - editor/html_renderer.py:189-203 nennt ihn "Inline-Tool" und
    // behandelt den eigenstaendigen Block als "falls doch".
    //
    // ACHTUNG BEI KUENFTIGEN AENDERUNGEN: 'marker' aus dieser Liste zu
    // nehmen, kostet lautlos jede Hervorhebung im Bestand. VW07 schlaegt
    // darauf an.
    // -------------------------------------------------------------------------
    function werkzeuge(w, umfang) {
        var win = w || window;
        var T = win.EditorTools || {};
        var alle = {
            header: T.Header, paragraph: T.Paragraph, list: T.NestedList,
            table: T.Table, quote: T.Quote, delimiter: T.Delimiter,
            marker: T.Marker
        };

        if (umfang === 'vorlage') {
            // 'image' liegt als SimpleImage im Buendel und war bisher nur
            // nicht eingetragen (build_editor_bundle.py:81-86).
            alle.image = T.SimpleImage;

            // 'evidence' hat im Buendel gar kein Werkzeug - der EvidenceBlock
            // ist ermittlerseitig (userinfo/report_editor.js:1314) und haengt
            // an Falldaten, die es hier nicht gibt. Statt des englischen
            // Ersatzes von Editor.js kommt der benannte deutsche Platzhalter.
            var UB = win.AIWUnbekannterBlock;
            if (UB && UB.UnbekannterBlock) {
                alle.evidence = UB.UnbekannterBlock;
            }
        }

        var raus = {};
        Object.keys(alle).forEach(function (k) {
            // Nur eintragen, was das Buendel wirklich mitbringt — ein
            // undefiniertes Werkzeug laesst Editor.js beim Start scheitern.
            if (alle[k]) { raus[k] = { class: alle[k] }; }
        });
        return raus;
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
     * erzeuge(hostEl, opts) -> Steuerobjekt
     *   opts.EditorCtor / opts.chips / opts.win  — injizierbar (Tests)
     * Rueckgabe: { zeige(modul), aus(), istOffen() }
     */
    function erzeuge(hostEl, opts) {
        opts = opts || {};
        var w = opts.win || (typeof window !== 'undefined' ? window : {});
        var Ctor = opts.EditorCtor || w.EditorJS;
        var chips = opts.chips || w.PlaceholderChips;

        var rumpf = _el('div', 'aiw-mod-vorschau-rumpf');
        var meldung = _el('p', 'aiw-mod-vorschau-meldung', '');
        hostEl.textContent = '';
        hostEl.appendChild(meldung);
        hostEl.appendChild(rumpf);

        var instanz = null;
        var letzterStand = null;

        function melde(text, warnung) {
            meldung.textContent = text || '';
            meldung.className = 'aiw-mod-vorschau-meldung'
                + (warnung ? ' ist-warnung' : '');
        }

        function abbauen() {
            // Editor.js haengt Horcher an das Dokument. Ohne destroy() bleiben
            // bei jedem Tastendruck Instanzen zurueck, und die Maske wird
            // langsamer, bis sie steht.
            if (instanz && typeof instanz.destroy === 'function') {
                try { instanz.destroy(); } catch (e) { log('destroy', e); }
            }
            instanz = null;
            rumpf.textContent = '';
        }

        function zeige(modul) {
            var fehlt = fehlendeTeile(w);
            if (fehlt.length) {
                abbauen();
                // KEIN STILLER AUSFALL: die fehlende Datei wird GENANNT.
                melde('Vorschau nicht moeglich — es fehlt: '
                      + fehlt.join(', ') + '.', true);
                return null;
            }
            var blocks = blockAus(modul, chips);
            var stand = JSON.stringify(blocks);
            if (stand === letzterStand && instanz) {
                // Unveraendert: nicht neu aufbauen. Sonst flackert die
                // Vorschau bei jedem Tastendruck, auch wenn sich nichts
                // geaendert hat.
                return instanz;
            }
            letzterStand = stand;
            abbauen();
            melde('');
            try {
                instanz = new Ctor({
                    holder: rumpf,
                    readOnly: true,
                    minHeight: 0,
                    tools: werkzeuge(w),
                    data: { blocks: blocks }
                });
            } catch (e) {
                instanz = null;
                melde('Vorschau fehlgeschlagen: ' + (e && e.message), true);
                log('Editor.js Aufbau fehlgeschlagen', e);
                return null;
            }
            log('Vorschau aufgebaut, Bloecke:', blocks.length);
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
        blockAus: blockAus,
        fehlendeTeile: fehlendeTeile,
        werkzeuge: werkzeuge,
        erzeuge: erzeuge
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') {
        window.AIWBausteinVorschau = API;
    }
})();
