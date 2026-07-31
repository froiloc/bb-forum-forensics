// =============================================================================
// management/server/static/help.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle H: Hilfesysteme (H6)
// =============================================================================
// Zweck:
//   Die Kapitelsuche im Hilfefenster (/help). Sie filtert das
//   Inhaltsverzeichnis waehrend des Tippens auf die passenden Kapitel.
//
// WARUM DER INDEX VOM SERVER KOMMT (und nicht hier gebaut wird):
//   Die Vollhilfe ist nach Rechten gefiltert (Entscheidung E1). Ein Index,
//   den dieses Skript aus dem Dokument zusammensuchte, koennte nur enthalten,
//   was ohnehin schon dasteht — das waere zwar richtig, aber der Index traegt
//   ausserdem die STICHWORTE aus dem VIEW_CATALOG ('ampel', 'rueckstau',
//   'frist' …), die im Kapiteltext gar nicht vorkommen muessen. Die kommen
//   serverseitig dazu, aus demselben gepflegten Bestand, der auch die
//   Kommandopalette speist. Ein zweiter Stichwortbestand waere Drift.
//
// WARUM NUR UEBERSCHRIFTEN UND STICHWORTE DURCHSUCHT WERDEN:
//   Eine Volltextsuche ueber alle Absaetze faende bei einem Wort wie 'Fall'
//   fast jedes Kapitel — und eine Trefferliste, die fast alles enthaelt, ist
//   keine Hilfe. Gesucht wird nach dem, wonach man in einem Handbuch sucht:
//   Namen von Sichten, Elementen und Abschnitten.
//
// KEIN JAVASCRIPT? Dann bleibt das Suchfeld verborgen (es ist im Markup
//   'hidden' vorbelegt und wird erst hier eingeblendet). Ein Eingabefeld,
//   das nichts tut, waere schlimmer als keines. Das Handbuch selbst ist
//   vollstaendig ohne dieses Skript lesbar und druckbar.
//
// PROJEKT-GEBOTE FUER JS: IIFE + 'use strict', Debug-Logging, ausfuehrliche
//   Kommentare, reine Filterfunktion getrennt vom DOM (vitest prueft den
//   echten Code). XSS: ausschliesslich textContent.
//
// Version: v0.8.593 · Build: 593 · 2026-07-31
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
        args.unshift('[AIW-Hilfe/Suche]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTION (kein DOM) — nach dem Muster filterViews in
    //    cockpit_palette.js. Dieselbe Ordnungsregel, damit sich Suche und
    //    Kommandopalette gleich anfuehlen: frueherer Treffer zuerst.
    // =========================================================================

    /**
     * filtereKapitel(index, begriff)
     *
     * index   = [{ id, label, gruppe, offen, worte }]
     * begriff = Eingabe der Person
     *
     * REGELN:
     *   - leerer Begriff -> ALLES (eine Kopie, nicht die Vorlage selbst).
     *   - mehrere Woerter sind ein UND: 'ampel frist' findet nur Kapitel, in
     *     denen beides vorkommt. Das ist die Erwartung, die man von jeder
     *     Suche mitbringt.
     *   - Ordnung: Treffer im LABEL zuerst (und dort der fruehere), danach
     *     Treffer nur in den Stichworten, jeweils alphabetisch.
     * REIN und deterministisch.
     */
    function filtereKapitel(index, begriff) {
        var liste = index || [];
        var roh = String(begriff || '').toLowerCase().trim();
        if (!roh) { return liste.slice(); }

        var worte = roh.split(/\s+/).filter(function (w) { return !!w; });
        var bewertet = [];
        liste.forEach(function (e) {
            var heu = String(e.worte || '');
            var label = String(e.label || '').toLowerCase();
            var alleDrin = worte.every(function (w) {
                return heu.indexOf(w) >= 0;
            });
            if (!alleDrin) { return; }
            // Rang 0: das erste Wort steht im Label -> die Person meint
            // wahrscheinlich genau diese Sicht.
            var imLabel = label.indexOf(worte[0]);
            bewertet.push({
                e: e,
                rang: (imLabel >= 0) ? 0 : 1,
                pos: (imLabel >= 0) ? imLabel : 0
            });
        });
        bewertet.sort(function (a, b) {
            if (a.rang !== b.rang) { return a.rang - b.rang; }
            if (a.pos !== b.pos) { return a.pos - b.pos; }
            return String(a.e.label).localeCompare(String(b.e.label));
        });
        return bewertet.map(function (b) { return b.e; });
    }

    /** Trefferzahl als Text. Rein, damit die Formulierung pruefbar ist. */
    function trefferText(anzahl, gesamt) {
        if (anzahl === gesamt) { return gesamt + ' Kapitel'; }
        if (anzahl === 0) { return 'kein Kapitel gefunden'; }
        return anzahl + ' von ' + gesamt + ' Kapiteln';
    }

    // =========================================================================
    // 2) DOM-Verkabelung.
    // =========================================================================

    function leseIndex(doc) {
        var el = doc.getElementById('aiw-h-index');
        if (!el) { return []; }
        try {
            return JSON.parse(el.textContent || '[]');
        } catch (err) {
            // Kein stiller Fehlpfad: ohne Index gibt es keine Suche, und das
            // soll man in der Konsole sehen.
            // eslint-disable-next-line no-console
            console.error('[AIW-Hilfe] Suchindex unlesbar:', err);
            return [];
        }
    }

    function anwenden(doc, treffer, gesamt) {
        var erlaubt = {};
        treffer.forEach(function (e) { erlaubt[e.id] = true; });

        // Kapitel-Eintraege ein-/ausblenden ...
        var punkte = doc.querySelectorAll('.aiw-h-verzeichnis li[data-sicht]');
        for (var i = 0; i < punkte.length; i++) {
            var li = punkte[i];
            li.hidden = !erlaubt[li.getAttribute('data-sicht')];
        }
        // ... und Gruppenueberschriften, die dadurch leer werden. Eine
        // Ueberschrift ohne Eintraege sieht aus wie ein Fehler.
        var listen = doc.querySelectorAll('.aiw-h-verzeichnis ul[data-gruppe]');
        for (var j = 0; j < listen.length; j++) {
            var ul = listen[j];
            var sichtbar = ul.querySelectorAll('li:not([hidden])').length;
            ul.hidden = (sichtbar === 0);
            var gruppe = ul.getAttribute('data-gruppe');
            var h3 = doc.querySelector(
                '.aiw-h-verzeichnis h3[data-gruppe="' + gruppe + '"]');
            if (h3) { h3.hidden = (sichtbar === 0); }
        }

        var zahl = doc.getElementById('aiw-h-suchzahl');
        if (zahl) { zahl.textContent = trefferText(treffer.length, gesamt); }
    }

    function init(doc) {
        doc = doc || (typeof document !== 'undefined' ? document : null);
        if (!doc) { return null; }

        var index = leseIndex(doc);
        var feld = doc.getElementById('aiw-h-suche');
        var kasten = doc.getElementById('aiw-h-suchfeld');
        if (!feld || !kasten) {
            log('kein Suchfeld im Dokument');
            return null;
        }
        // Erst jetzt sichtbar: ab hier tut es auch etwas.
        kasten.hidden = false;

        function lauf() {
            var treffer = filtereKapitel(index, feld.value);
            anwenden(doc, treffer, index.length);
            log(treffer.length, 'von', index.length);
        }

        feld.addEventListener('input', lauf);
        feld.addEventListener('keydown', function (ev) {
            // Escape leert das Feld — dieselbe Abbruchtaste wie ueberall
            // sonst im Werkzeug.
            if (ev.key === 'Escape') {
                feld.value = '';
                lauf();
            }
        });
        lauf();
        log('init mit', index.length, 'Kapiteln');
        return { lauf: lauf, index: index };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        filtereKapitel: filtereKapitel,
        trefferText: trefferText,
        init: init
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') {
        window.AIWHilfeSuche = API;
        if (typeof document !== 'undefined') {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', function () {
                    init(document);
                });
            } else {
                init(document);
            }
        }
    }
})();
