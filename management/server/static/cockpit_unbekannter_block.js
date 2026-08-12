// =============================================================================
// management/server/static/cockpit_unbekannter_block.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Bausteinverwaltung
// =============================================================================
// Zweck:
//   Ein Editor.js-Werkzeug fuer Blocktypen, fuer die es KEIN echtes Werkzeug
//   gibt. Es zeigt einen benannten Platzhalter und gibt die Blockdaten beim
//   Auslesen UNVERAENDERT zurueck.
//
// ── WARUM ES DIESES WERKZEUG GIBT ───────────────────────────────────────────
//
//   Dokumentvorlagen duerfen neun Blocktypen fuehren (report_render/
//   report_source.py:59-62: paragraph, header, list, table, quote, image,
//   delimiter, marker, evidence). Das ausgelieferte Editor.js-Buendel bringt
//   Block-Werkzeuge fuer sieben davon mit (deployment/build_editor_bundle.py:
//   81-86); 'marker' liegt nur als INLINE-Werkzeug bei, 'evidence' gar nicht -
//   der EvidenceBlock ist ermittlerseitig (userinfo/report_editor.js:1314) und
//   haengt an Falldaten, die es in der Verwaltungsoberflaeche nicht gibt.
//
//   Diese Bloecke sind nicht theoretisch: management/templates_admin/
//   report_template_extractor.py:192 erzeugt evidence-Bloecke, wenn aus einem
//   Vermerk eine Vorlage gewonnen wird.
//
// ── WAS EDITOR.JS VON SICH AUS TUT, UND WARUM DAS NICHT REICHT ──────────────
//
//   GEMESSEN am 12.08.2026 (Editor.js 2.31.6, jsdom + editor.bundle.js):
//   Fehlt zu einem Blocktyp das Werkzeug, setzt Editor.js einen eigenen
//   Ersatzblock. Die DATEN ueberleben - alle neun Typen kamen aus einem
//   Durchlauf byteweise identisch zurueck. Ein stiller Verlust droht also
//   NICHT, und das ist die gute Nachricht.
//
//   Angezeigt wird aber der Satz "The block can not be displayed correctly."
//   Er ist englisch in einer durchgehend deutschen Oberflaeche, er NENNT DEN
//   TYP NICHT, und er laesst offen, ob hier etwas kaputt ist oder ob es so
//   gemeint war. Ein Redakteur, der das sieht, hat drei Fragen und keine
//   Antwort - und die naheliegende Vermutung ist die falsche: dass sein
//   Inhalt weg sei.
//
//   PRAEZEDENZFALL im Bestand: UnknownBlock in editor/html_renderer.py:206-226
//   rendert '[Block-Typ: <typ>]' statt still zu verwerfen, mit derselben
//   Begruendung ("Forensische Grundregel: kein stiller Fehlschlag"). Dieses
//   Werkzeug ist dasselbe Verhalten an der anderen Stelle - dort beim
//   Rendern, hier beim Anzeigen.
//
// ── WAS ES AUSDRUECKLICH NICHT TUT ──────────────────────────────────────────
//
//   Es BEARBEITET nichts. Ein Werkzeug, das den Inhalt eines Blocks anzeigt,
//   den es nicht versteht, koennte ihn nur raten; ein Eingabefeld daneben
//   wuerde eine Bearbeitbarkeit vortaeuschen, die es nicht gibt. Der Weg,
//   einen solchen Block zu aendern, ist die Rohansicht - und genau das sagt
//   der angezeigte Text.
//
// Version: v0.8.705 · Build: 705 · 2026-08-12
// Beleg: report_render/report_source.py:59-62 (KNOWN_BLOCK_TYPES);
//        deployment/build_editor_bundle.py:81-86 (Inhalt des Buendels);
//        editor/html_renderer.py:206-226 (UnknownBlock, Praezedenzfall);
//        Messung Editor.js 2.31.6 vom 12.08.2026.
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
        args.unshift('[AIW-UnbekannterBlock]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTION — der angezeigte Text.
    //
    // Herausgezogen, damit die Regression den Wortlaut pruefen kann, ohne
    // Editor.js zu bauen. Der Wortlaut ist hier die eigentliche Leistung:
    // er hat drei Fragen zu beantworten, und zwar in dieser Reihenfolge -
    // WAS ist das, IST MEIN INHALT WEG, und WIE aendere ich es.
    // =========================================================================
    function platzhalterText(typ) {
        var t = (typ === undefined || typ === null || typ === '')
            ? 'unbekannt' : String(typ);
        return 'Blockart «' + t + '» — hier nicht darstellbar. '
            + 'Der Inhalt bleibt unverändert erhalten und wird mitgespeichert. '
            + 'Ändern lässt er sich in der Rohansicht.';
    }

    // =========================================================================
    // 2) DAS WERKZEUG.
    //
    // Editor.js verlangt eine Klasse mit render() und save(). Geschrieben als
    // Funktion mit Prototyp statt als 'class', weil diese Datei - wie der
    // uebrige Cockpit-Code - ohne Uebersetzungsschritt ausgeliefert wird und
    // im selben Sprachstand bleiben soll wie ihre Nachbarn.
    // =========================================================================
    function UnbekannterBlock(cfg) {
        var c = cfg || {};
        // DIE DATEN WERDEN UNBERUEHRT FESTGEHALTEN. Kein Kopieren, kein
        // Normalisieren, kein Auffuellen von Vorgaben - jeder Eingriff waere
        // eine Aenderung an einem Block, den dieses Werkzeug nicht versteht.
        this._daten = (c.data && typeof c.data === 'object') ? c.data : {};
        // Editor.js reicht den Namen des Werkzeugs durch, unter dem es
        // aufgerufen wurde. Genau der ist der gesuchte Blocktyp.
        this._typ = c.block && typeof c.block.name === 'string'
            ? c.block.name
            : (c.api && c.api.blocks && c.block ? '' : '');
        if (!this._typ && c.toolName) { this._typ = String(c.toolName); }
        log('erzeugt fuer', this._typ, this._daten);
    }

    // Editor.js fragt das ab, bevor es das Werkzeug einsetzt. 'true' hiesse
    // Inline-Werkzeug (wie Marker) - das hier ist ein Blockwerkzeug.
    UnbekannterBlock.isInline = false;

    // Ohne Schreibrechte ist nichts zu tun; MIT Schreibrechten ebenfalls
    // nicht, weil dieses Werkzeug bewusst nicht bearbeitet. Editor.js darf
    // die Nur-Lese-Ansicht deshalb ohne Umbau benutzen.
    UnbekannterBlock.isReadOnlySupported = true;

    UnbekannterBlock.prototype.render = function () {
        var doc = (typeof document !== 'undefined') ? document : null;
        if (!doc) { return null; }
        var el = doc.createElement('div');
        el.className = 'cdx-block aiw-unbekannter-block';
        el.setAttribute('data-blockart', String(this._typ || 'unbekannt'));
        // textContent, nicht innerHTML: der Typ stammt aus den Daten, und das
        // Forum ist multilingual (UTF-8, beliebige Zeichensaetze).
        el.textContent = platzhalterText(this._typ);
        return el;
    };

    // DIE EIGENTLICHE ZUSICHERUNG DIESES WERKZEUGS: was hereinkam, kommt
    // heraus. Nicht die Anzeige wird gespeichert, sondern der urspruengliche
    // Datensatz - unveraendert und ohne Kopie, damit auch kein Feld auf dem
    // Weg normalisiert werden kann.
    UnbekannterBlock.prototype.save = function () {
        return this._daten;
    };

    // Editor.js fragt vor dem Speichern, ob der Block leer ist, und WIRFT
    // LEERE BLOECKE WEG. Ein Ersatzblock sieht fuer diese Pruefung leer aus
    // (er hat kein Textfeld) - ohne diese Zusage koennte also ausgerechnet
    // das Werkzeug gegen den Verlust den Verlust ausloesen.
    UnbekannterBlock.prototype.validate = function () {
        return true;
    };

    // =========================================================================
    // 3) UMD-AUSGANG.
    // =========================================================================
    var API = {
        UnbekannterBlock: UnbekannterBlock,
        platzhalterText: platzhalterText
    };
    if (typeof window !== 'undefined') {
        window.AIWUnbekannterBlock = API;
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = API;
    }
    log('geladen');
})();
