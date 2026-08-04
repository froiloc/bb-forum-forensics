/**
 * management/server/static/cockpit_datumspaar.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * DATUMSPAAR — koppelt ein "Von"-Feld an ein "Bis"-Feld.
 *
 * ANLASS: Ticket d3f933cd-40fd-44c0-938f-e8f84053d382 (Alex, 2026-08-03).
 * Wer einen Zeitraum eintraegt, muss sich im Bis-Kalender vom HEUTIGEN Tag bis
 * zum Zieldatum durchklicken — Monat fuer Monat —, obwohl das Von-Datum daneben
 * schon steht. Fuer einen eintaegigen Zeitraum sind das zwei volle Eingaben fuer
 * ein und dasselbe Datum.
 *
 * -----------------------------------------------------------------------------
 * ZWEI WIRKUNGEN, GETRENNT SCHALTBAR — UND WARUM
 *
 * Es gibt im Bestand zwei ARTEN von Datumspaaren, und was fuer die eine richtig
 * ist, waere fuer die andere ein Schaden:
 *
 *   (1) EINGABEMASKEN (z. B. Abwesenheit von/bis in der Kapazitaetspflege).
 *       Hier IST das Paar der Gegenstand. Ein leeres Bis-Feld heisst "habe ich
 *       noch nicht gesagt", und die Uebernahme des Von-Datums ist genau die
 *       gewuenschte Abkuerzung.
 *
 *   (2) FILTER- UND ZEITRAUMWAHLEN (z. B. der Auswertungszeitraum der
 *       Kapazitaetsansicht, die Von/Bis-Schiene der Annotationsrecherche).
 *       Hier ist ein leeres Bis-Feld ein OFFENES ENDE — "bis heute", "ohne
 *       Begrenzung". Wuerde man es auf das Von-Datum setzen, schruempfte die
 *       Auswertung stillschweigend auf einen einzigen Tag, und die Bedienerin
 *       saehe eine leere Liste ohne zu wissen, warum. Das waere eine still
 *       herbeigefuehrte Auslassung (Grundregel 1) — verursacht ausgerechnet
 *       von einer Bequemlichkeitsfunktion.
 *
 * Deshalb: 'uebernehmen' ist AUS per Vorgabe und wird nur dort eingeschaltet,
 * wo ein Paar wirklich eine Eingabe ist. Die untere Schranke ('min') dagegen
 * ist ueberall richtig — ein Ende vor dem Anfang ist in BEIDEN Faellen unsinnig.
 *
 * -----------------------------------------------------------------------------
 * WAS DIESER BAUSTEIN AUSDRUECKLICH NICHT TUT
 *
 * Er ueberschreibt NIE ein bereits gefuelltes Bis-Feld. Eine eingegebene Angabe
 * unter der Hand zu ersetzen, waere schlimmer als die Unbequemlichkeit, die hier
 * behoben wird: die Bedienerin muesste jede Eingabe erneut pruefen, weil sie
 * ihr nicht mehr trauen koennte.
 *
 * Steht im Bis-Feld ein Datum VOR dem neuen Von-Datum, wird es deshalb ebenfalls
 * nicht angetastet — aber auch nicht verschwiegen: das Feld erhaelt die Marke
 * 'aiw-feldfehler', und ein optionaler Rueckruf 'onWarnung' meldet den Widerspruch
 * an die Sicht. Der Server prueft ohnehin; hier geht es darum, dass die Person
 * es SIEHT, bevor sie speichert.
 *
 * -----------------------------------------------------------------------------
 * WARUM 'change' UND NICHT 'input'
 *
 * Ein <input type="date"> feuert 'input' auch bei halbfertigen Eingaben — im
 * Tastaturweg entsteht so kurzzeitig etwa der 01.01.0002, weil das Jahr erst
 * ziffernweise entsteht. Auf 'input' zu reagieren hiesse, das Bis-Feld mit
 * Zwischenstaenden zu fuellen. 'change' feuert erst, wenn der Wert vollstaendig
 * ist (Kalenderklick oder Verlassen des Feldes) — das ist der richtige Moment.
 *
 * Version: v0.8.663 · Build: 663 · 2026-08-04
 * =============================================================================
 */
(function () {
    'use strict';

    // Debug-Protokoll: im Betrieb still, in der Entwicklung gespraechig.
    // Derselbe Schalter wie im Cockpit (window.AIW_COCKPIT_DEBUG = true).
    function log() {
        var an = (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
        if (!an || typeof console === 'undefined') { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[Datumspaar]');
        console.log.apply(console, args);
    }

    /**
     * istIsoDatum: taugt der Wert als ISO-Datum (YYYY-MM-DD)?
     *
     * Ein <input type="date"> liefert entweder genau diese Form oder den leeren
     * String — ein halb eingetipptes Datum gilt dem Browser als ungueltig und
     * kommt als '' heraus. Die Pruefung ist trotzdem da: dieser Baustein wird
     * auch mit Feldern aufgerufen, die (etwa in Tests oder in aelteren Masken)
     * schlichte Textfelder sind.
     */
    function istIsoDatum(wert) {
        return typeof wert === 'string'
            && /^\d{4}-\d{2}-\d{2}$/.test(wert);
    }

    /**
     * koppeln: verbindet zwei Datumsfelder.
     *
     *   vonEl, bisEl        — die beiden <input type="date">
     *   opts.uebernehmen    — bei leerem Bis-Feld das Von-Datum uebernehmen.
     *                         VORGABE false (siehe Kopfkommentar).
     *   opts.min            — untere Schranke am Bis-Feld setzen.
     *                         VORGABE true.
     *   opts.onWarnung(txt) — optionaler Rueckruf bei Widerspruch
     *                         (Bis liegt vor Von). Ohne Rueckruf bleibt nur
     *                         die Feldmarkierung.
     *   opts.onUebernahme(datum) — optionaler Rueckruf, NACHDEM uebernommen
     *                         wurde. Damit kann die Sicht es in ihrer
     *                         Ergebniszeile benennen; eine unerklaerte
     *                         Wertaenderung im Formular waere sonst ein
     *                         kleines Raetsel.
     *
     * Rueckgabe: { abmelden() } — meldet die Ereignisbehandlung wieder ab.
     * Das ist keine Zierde: die Cockpit-Sichten werden bei jedem Neuladen neu
     * gezeichnet, und liegengebliebene Zuhoerer auf entsorgten Knoten sind
     * genau die Sorte Fehler, die man spaeter nicht mehr findet.
     */
    function koppeln(vonEl, bisEl, opts) {
        opts = opts || {};
        if (!vonEl || !bisEl) {
            log('koppeln: ein Feld fehlt — nichts zu tun.',
                { von: !!vonEl, bis: !!bisEl });
            return { abmelden: function () {} };
        }

        var uebernehmen = opts.uebernehmen === true;
        var setzeMin = opts.min !== false;

        function anwenden(ausloeser) {
            var von = vonEl.value;
            if (!istIsoDatum(von)) {
                // Von wurde geleert: die Schranke muss mit weg, sonst bliebe
                // das Bis-Feld grundlos beschraenkt.
                if (setzeMin && bisEl.getAttribute('min')) {
                    bisEl.removeAttribute('min');
                    log('Von geleert -> min am Bis-Feld entfernt.');
                }
                bisEl.classList.remove('aiw-feldfehler');
                return;
            }

            if (setzeMin) {
                bisEl.setAttribute('min', von);
            }

            var bis = bisEl.value;

            if (!istIsoDatum(bis)) {
                if (uebernehmen) {
                    bisEl.value = von;
                    bisEl.classList.remove('aiw-feldfehler');
                    log('Bis war leer -> uebernommen:', von, '(', ausloeser, ')');
                    if (typeof opts.onUebernahme === 'function') {
                        opts.onUebernahme(von);
                    }
                }
                return;
            }

            // Bis ist gefuellt. NICHT anfassen — aber den Widerspruch zeigen.
            if (bis < von) {                       // ISO-Datum: Textvergleich
                bisEl.classList.add('aiw-feldfehler');
                log('Widerspruch: Bis', bis, 'liegt vor Von', von);
                if (typeof opts.onWarnung === 'function') {
                    opts.onWarnung('Das Bis-Datum (' + bis + ') liegt vor dem '
                        + 'Von-Datum (' + von + '). Der Eintrag wurde NICHT '
                        + 'veraendert — bitte von Hand berichtigen.');
                }
            } else {
                bisEl.classList.remove('aiw-feldfehler');
            }
        }

        function beiVonAenderung() { anwenden('change'); }

        vonEl.addEventListener('change', beiVonAenderung);

        // Steht beim Aufbau schon ein Von-Datum (Formularzustand nach dem
        // Neuzeichnen, Build 561), gilt die Schranke sofort — ohne dass die
        // Person das Feld erst anfassen muesste. Die UEBERNAHME unterbleibt
        // hier bewusst: sie ist eine Reaktion auf eine EINGABE, nicht auf das
        // Zeichnen einer Maske.
        (function beimAufbau() {
            var merk = uebernehmen;
            uebernehmen = false;
            anwenden('aufbau');
            uebernehmen = merk;
        })();

        log('gekoppelt:', vonEl.id || '(ohne id)', '->',
            bisEl.id || '(ohne id)',
            { uebernehmen: uebernehmen, min: setzeMin });

        return {
            abmelden: function () {
                vonEl.removeEventListener('change', beiVonAenderung);
                log('abgemeldet:', vonEl.id || '(ohne id)');
            }
        };
    }

    var API = { koppeln: koppeln, istIsoDatum: istIsoDatum };

    // UMD-artiger Ausgang: im Browser am window, unter Node fuer die Tests.
    // Die Tests sollen die ECHTE Funktion pruefen, nicht eine nachgebaute
    // (Lehre "gruen aber tot").
    if (typeof window !== 'undefined') { window.AIWDatumspaar = API; }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = API;
    }
})();
