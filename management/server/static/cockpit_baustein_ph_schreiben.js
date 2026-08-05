/**
 * management/server/static/cockpit_baustein_ph_schreiben.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Baustein-Module (W1) — PLATZHALTER ZURUECKSCHREIBEN, Build 681
 *
 * ZWECK (Vorgang 7c1f2a94, herausgeloest aus 4b032177, mc):
 *   "Ideal waere es, wenn diese Tabelle bidirektional waere und Aenderungen
 *   in den Feldern der Tabelle sich auf den Inhalt in der textarea auswirken
 *   wuerden."
 *
 *   Diese Datei ist STUFE 2 zu cockpit_baustein_platzhalter.js (Stufe 1:
 *   lesen, verifizieren, testen). Sie enthaelt AUSSCHLIESSLICH reine
 *   Funktionen - kein DOM, kein Netz. Die Bedienung liegt in der
 *   Tabellendatei, die Anbindung an den Editor in cockpit_modules.js.
 *
 * =========================================================================
 * DER BEFUND, DER DEN VORGANG VERSCHIEBT: DIE TEXTAREA SCHEIDET AUS
 * =========================================================================
 *   Der Vorgang wurde am 02.08.2026 zu Build 654 geschrieben. Damals war die
 *   textarea das Eingabefeld des Bausteins. ZWEI BUILDS SPAETER IST SIE DAS
 *   NICHT MEHR:
 *
 *     cockpit_modules.js:1262  fBody.readOnly = true — beschriftet als
 *                              "Klartextspiegel (body) — wird beim Speichern
 *                              erzeugt".
 *     cockpit_modules.js:706   gespeichert wird body: _klartext(stand), also
 *                              aus block_data ERZEUGT. Was in der textarea
 *                              steht, wird beim Speichern nicht gelesen.
 *     cockpit_modules.js:735   bei jedem _blockStandLesen() wird
 *                              f.body.value ueberschrieben.
 *
 *   Ein Zurueckschreiben in die textarea waere also WIRKUNGSLOS und beim
 *   naechsten Tastendruck im Editor verschwunden - ohne Fehlermeldung. Genau
 *   die Sorte stillen Verlusts, vor der der Kopf von
 *   cockpit_baustein_eingabe.js warnt. Entscheidung mc vom 05.08.2026:
 *   geschrieben wird nach block_data, in BEIDEN Modi.
 *
 * =========================================================================
 * WARUM ES TROTZDEM GEHT: mapBlockTexts LIEGT SCHON IM BESTAND
 * =========================================================================
 *   PlaceholderChips.mapBlockTexts (userinfo/placeholder_chips.js:401) fasst
 *   JEDE Textstelle eines Editor.js-Blocks an: .text bei Absatz/Ueberschrift/
 *   Zitat, .items[] bei Listen (flach UND verschachtelt), .content[][] bei
 *   Tabellen. Es ist dieselbe Vorschrift, gegen die auf dem Server
 *   core/placeholder_syntax.py::iter_texts() prueft. Ein eigener Durchlauf
 *   hier waere eine zweite Wahrheit ueber die Frage, WO ein Platzhalter
 *   stehen darf - und die Tabellenzelle waere der erste Ort, an dem beide
 *   auseinanderliefen.
 *
 * =========================================================================
 * DIE VIER FALLEN - DREI AUS DEM VORGANG, EINE NEU
 * =========================================================================
 *   F1 TRENNZEICHEN. '|' und '}' duerfen in keinem Feld vorkommen (_CHIP_RE
 *      benutzt [^|}\n]). Der Vorgang sagt ausdruecklich: ABZUWEISEN, nicht
 *      stillschweigend entschaerfen. feldPruefen() weist ab und BENENNT das
 *      Zeichen. Ein still entschaerfter Wert waere ein Wert, den niemand
 *      eingegeben hat und der trotzdem im Vermerk steht.
 *
 *   F2 MEHRFACHVORKOMMEN. Steht ein Name mehrfach im Text, aendert eine
 *      Tabellenzeile ALLE Vorkommen. Diese Datei zaehlt sie (Rueckgabe
 *      'ersetzt'); die Vorabanzeige und die Rueckfrage macht die
 *      Tabellendatei. Entscheidung mc: dauerhafte Anzeige PLUS Rueckfrage.
 *
 *   F3 EINFUEGEMARKE. Deshalb wird erst bei 'change' geschrieben (Feld
 *      verlassen), nicht bei 'input' - auch das eine Sache der
 *      Tabellendatei.
 *
 *   F4 NEU, UND SCHAERFER ALS F3: Im Komfortmodus haelt Editor.js das DOM.
 *      Geaenderte block_data verlangen setze() - also einen NEUAUFBAU des
 *      Editors. Der kostet nicht nur die Einfuegemarke, sondern auch den
 *      RUECKGAENGIG-VERLAUF. Das ist der Preis der Entscheidung "beide Modi"
 *      und steht so in der Hilfe.
 *
 * =========================================================================
 * DIE RUECKPROBE - WARUM HIER ZWEIMAL GEPRUEFT WIRD
 * =========================================================================
 *   tokenBauen() setzt ein Token zusammen. tokenProbe() zerlegt es SOFORT
 *   WIEDER mit derselben parse(), die der ganze Bestand benutzt, und
 *   vergleicht Feld fuer Feld mit dem, was hineingegeben wurde.
 *
 *   Das ist keine Vorsicht um ihrer selbst willen. Ein Token, das nicht
 *   zurueckgelesen werden kann, ist genau der Fall V1 aus der Tabelle: es
 *   loest keinen Fehler aus, es tut nur nichts - und erscheint woertlich im
 *   Vermerk. Diese Datei darf einen solchen Zustand nicht ERZEUGEN, waehrend
 *   die Tabelle daneben davor warnt. Schlaegt die Rueckprobe an, wird NICHT
 *   geschrieben und die Ursache benannt (Grundregel 1).
 *
 * =========================================================================
 * CHIP-HTML IM BLOCK - DER STILLE SONDERFALL
 * =========================================================================
 *   Ein Platzhalter kann in block_data in ZWEI Formen stehen: als Token
 *   '{{m:x}}' oder als gerenderter Chip '<span class="ph-chip"
 *   data-chip-raw="{{m:x}}">'. Die zweite Form entsteht ueber
 *   hydrateBlockData() (userinfo/placeholder_chips.js:457).
 *
 *   Ein Text in Chip-Form wird VOR dem Ersetzen dehydriert - und nur dann,
 *   wenn ueberhaupt ersetzt wird. Das ist dieselbe Normalisierung, die
 *   klartextAus() (cockpit_baustein_eingabe.js:297) und dehydrateBlockData()
 *   schon vornehmen; die Token-Form ist die Speicherform. Wuerde stattdessen
 *   im rohen HTML ersetzt, traefe parse() auf den Inhalt des Attributs
 *   data-chip-raw und zerschnitte das Attribut - der Block waere kaputt und
 *   der Schaden erst im Vermerk sichtbar.
 *
 * JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging; ausfuehrliche
 *   Kommentare; Kapselung; reine Funktionen einzeln exportiert (vitest);
 *   UTF-8 und multilinguale Werte bleiben unangetastet (kein Escaping, kein
 *   Umkodieren - es wird nur zusammengesetzt und verglichen).
 *
 * OEFFENTLICHE API (window.AIWBausteinPhSchreiben) — alles rein:
 *   feldPruefen(wert, feldname)            -- {ok, meldung}
 *   typPruefen(typ)                        -- {ok, meldung}
 *   namePruefen(name)                      -- {ok, meldung}
 *   tokenBauen({typ,name,vorgabe,beschreibung,regelfeld})  -- string
 *   tokenProbe(token, soll, chips)         -- {ok, meldung}
 *   ersetzeInText(text, altTyp, altName, neuToken, chips)  -- {text, ersetzt}
 *   ersetzeInBlock(daten, altTyp, altName, neuToken, chips)-- {daten, ersetzt}
 *   schreibe({daten, alt, neu, chips})     -- {ok, meldung, daten, ersetzt,
 *                                             token}
 *
 * Version: v0.8.681 · Build: 681 · 2026-08-05
 * Beleg: Vorgang 7c1f2a94; userinfo/placeholder_chips.js:73 (_CHIP_RE),
 *        :401 (mapBlockTexts), :457 (hydrateBlockData);
 *        management/server/static/cockpit_modules.js:706, :735, :1262;
 *        management/server/static/cockpit_baustein_eingabe.js:297, :691.
 */
(function () {
    'use strict';

    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[ph-schreiben]');
            console.log.apply(console, a);
        }
    }

    function _s(v) { return (v === undefined || v === null) ? '' : String(v); }

    // Die drei erlaubten Typkuerzel in KURZFORM. Geschrieben wird immer die
    // Kurzform, auch wenn im Text die Langform stand ('mandatory' ->  'm'):
    // parse() normalisiert ohnehin auf die Kurzform (_normalizeType), und ein
    // Token, das sich beim Zurueckschreiben nicht aendert, waere sonst nicht
    // wiederzuerkennen.
    var TYPEN = ['a', 'm', 'o'];

    // Die Zeichen, die _CHIP_RE in einem Feld AUSSCHLIESST: [^|}\n]. '\r'
    // steht nicht im Ausschluss, kommt aber nur zusammen mit '\n' vor und
    // wuerde in einer einzeiligen Eingabe nichts Gutes bewirken - es wird
    // deshalb mit abgewiesen. Der Name der Falle: F1.
    var VERBOTEN = [
        { zeichen: '|', wort: 'ein senkrechter Strich "|"' },
        { zeichen: '}', wort: 'eine geschweifte Klammer "}"' },
        { zeichen: '\n', wort: 'ein Zeilenumbruch' },
        { zeichen: '\r', wort: 'ein Zeilenumbruch' }
    ];

    // Der Name eines Platzhalters, wie _CHIP_RE ihn zulaesst. Der Name ist in
    // der Tabelle NICHT beschreibbar (Entscheidung mc); geprueft wird er
    // trotzdem, weil diese Datei auch von aussen aufrufbar ist und ein
    // ungueltiger Name ein unlesbares Token ergaebe.
    var _NAME_RE = /^[A-Za-z0-9._-]+$/;

    // =====================================================================
    // 1) PRUEFUNGEN
    // =====================================================================

    /**
     * feldPruefen: darf dieser Wert in ein Platzhalterfeld?
     * F1 - abweisen statt entschaerfen. Die Meldung BENENNT das Zeichen,
     * damit der Redakteur nicht raten muss, was an seiner Eingabe stoert.
     */
    function feldPruefen(wert, feldname) {
        var w = _s(wert);
        var name = _s(feldname) || 'Das Feld';
        for (var i = 0; i < VERBOTEN.length; i += 1) {
            if (w.indexOf(VERBOTEN[i].zeichen) >= 0) {
                return {
                    ok: false,
                    meldung: name + ' enthält ' + VERBOTEN[i].wort
                        + '. Dieses Zeichen trennt die Felder eines '
                        + 'Platzhalters und kann in keinem Feld stehen. Die '
                        + 'Eingabe wird NICHT übernommen — sie stillschweigend '
                        + 'zu entschärfen hieße, einen Wert in den Vermerk zu '
                        + 'schreiben, den niemand eingegeben hat.'
                };
            }
        }
        return { ok: true, meldung: '' };
    }

    /** typPruefen: a, m oder o - nichts sonst. */
    function typPruefen(typ) {
        var t = _s(typ);
        if (TYPEN.indexOf(t) < 0) {
            return {
                ok: false,
                meldung: 'Unbekannte Art "' + t + '". Erlaubt sind nur '
                    + 'a (automatisch), m (verpflichtend) und o (optional).'
            };
        }
        return { ok: true, meldung: '' };
    }

    /** namePruefen: A-Z a-z 0-9 . _ - und nicht leer. */
    function namePruefen(name) {
        var n = _s(name);
        if (n === '') {
            return { ok: false, meldung: 'Der Name des Platzhalters fehlt.' };
        }
        if (!_NAME_RE.test(n)) {
            return {
                ok: false,
                meldung: 'Der Name "' + n + '" enthält unzulässige Zeichen. '
                    + 'Erlaubt sind A-Z, a-z, 0-9, Punkt, Unterstrich und '
                    + 'Bindestrich.'
            };
        }
        return { ok: true, meldung: '' };
    }

    // =====================================================================
    // 2) TOKEN BAUEN UND ZURUECKLESEN
    // =====================================================================

    /**
     * tokenBauen: aus den fuenf Angaben ein Platzhalter-Token.
     *
     * LEERE FELDER AM ENDE FALLEN WEG, leere Felder DAZWISCHEN nicht: das
     * fuenfte Feld laesst sich ohne das dritte und vierte nicht erreichen,
     * '{{m:x|||rule:a}}' ist deshalb richtig und nicht etwa umstaendlich.
     * Ein Token, das mehr Felder fuehrt als noetig, waere kein Fehler - aber
     * es waere im Text laenger als das, was der Redakteur eingegeben hat,
     * und der Unterschied faellt beim Lesen des Textes auf.
     */
    function tokenBauen(a) {
        var q = a || {};
        var felder = [_s(q.vorgabe), _s(q.beschreibung), _s(q.regelfeld)];
        var letzter = -1;
        felder.forEach(function (f, i) { if (f !== '') { letzter = i; } });
        var schwanz = (letzter < 0)
            ? ''
            : ('|' + felder.slice(0, letzter + 1).join('|'));
        return '{{' + _s(q.typ) + ':' + _s(q.name) + schwanz + '}}';
    }

    /**
     * tokenProbe: das gebaute Token SOFORT wieder zerlegen und vergleichen.
     *
     * Geprueft wird mit derselben parse(), die im ganzen Bestand entscheidet,
     * was ein Platzhalter ist. Verlangt wird:
     *   - GENAU EIN Segment, und zwar ein Chip (nicht ein Chip mit Resttext:
     *     ein Rest bedeutet, dass ein Teil der Eingabe ausserhalb des Tokens
     *     gelandet ist)
     *   - seg.raw ist das ganze Token
     *   - alle fuenf Angaben kommen unveraendert zurueck
     *
     * Die Rueckgabe nennt bei Abweichung das FELD, nicht nur die Tatsache.
     */
    function tokenProbe(token, soll, chips) {
        var pc = chips || (typeof window !== 'undefined'
            ? window.PlaceholderChips : null);
        if (!pc || typeof pc.parse !== 'function') {
            return {
                ok: false,
                meldung: 'Die Platzhalter-Zerlegung (placeholder_chips.js) '
                    + 'ist nicht geladen. Ohne sie lässt sich nicht prüfen, '
                    + 'ob das neue Token lesbar ist — es wird deshalb nicht '
                    + 'geschrieben.'
            };
        }
        var t = _s(token);
        var segmente = pc.parse(t) || [];
        var chip = (segmente.length === 1 && segmente[0]
                    && segmente[0].type === 'chip') ? segmente[0] : null;
        if (!chip || chip.raw !== t) {
            return {
                ok: false,
                meldung: 'Aus den Angaben entsteht kein lesbarer Platzhalter '
                    + '("' + t + '"). Er würde wörtlich im Vermerk stehen, '
                    + 'ohne einen Fehler auszulösen — genau der Fall, vor dem '
                    + 'die Spalte Verifikation als V1 warnt. Es wird nichts '
                    + 'geschrieben.'
            };
        }
        var s = soll || {};
        var paare = [
            ['die Art', chip.chipType, _s(s.typ)],
            ['der Name', chip.name, _s(s.name)],
            ['die Vorgabe', _s(chip.defaultVal), _s(s.vorgabe)],
            ['die Beschreibung', _s(chip.description), _s(s.beschreibung)],
            ['das Prüfmuster',
             chip.b64regex === null ? '' : _s(chip.b64regex),
             _s(s.regelfeld)]
        ];
        for (var i = 0; i < paare.length; i += 1) {
            if (paare[i][1] !== paare[i][2]) {
                return {
                    ok: false,
                    meldung: 'Die Rückprobe schlägt fehl: ' + paare[i][0]
                        + ' kommt als "' + paare[i][1] + '" zurück, '
                        + 'eingegeben war "' + paare[i][2] + '". Es wird '
                        + 'nichts geschrieben.'
                };
            }
        }
        return { ok: true, meldung: '' };
    }

    // =====================================================================
    // 3) ERSETZEN
    // =====================================================================

    /**
     * ersetzeInText: alle Vorkommen EINES (Typ, Name) durch ein neues Token.
     *
     * ZEICHENGENAU UEBER parse(), NICHT UEBER SUCHEN-UND-ERSETZEN. parse()
     * liefert den Text lueckenlos als Folge von Text- und Chip-Segmenten;
     * wieder zusammengesetzt ergibt sie zeichengleich den Ausgangstext. Damit
     * ist ausgeschlossen, was ein textuelles Ersetzen mit sich braechte:
     *   - eine Ersetzung, die ihrerseits wieder gefunden wird,
     *   - ein Treffer mitten in gewoehnlichem Text,
     *   - Sonderzeichen im alten Token, die als Regex gelesen wuerden.
     *
     * Zurueck kommt der neue Text UND die Zahl der Ersetzungen. Die Zahl ist
     * der Beleg: ist sie 0, ist nichts geschehen, und der Aufrufer sagt das
     * (Grundregel 1) statt Erfolg zu melden.
     */
    function ersetzeInText(text, altTyp, altName, neuToken, chips) {
        var pc = chips || (typeof window !== 'undefined'
            ? window.PlaceholderChips : null);
        var roh = _s(text);
        if (!pc || typeof pc.parse !== 'function') {
            return { text: roh, ersetzt: 0 };
        }

        // Chip-HTML zuerst in die Token-Form zuruecknehmen - siehe Kopf,
        // "Chip-HTML im Block". Nur wenn ueberhaupt ein Chip drinsteht, und
        // NUR auf einer Arbeitskopie: bleibt es am Ende bei 0 Ersetzungen,
        // wird der Ausgangstext unveraendert zurueckgegeben.
        var t = roh;
        if (t.indexOf('ph-chip') >= 0
                && typeof pc.dehydrateChips === 'function') {
            try { t = _s(pc.dehydrateChips(t)); }
            catch (e) { log('dehydrate', e); t = roh; }
        }

        var segmente = pc.parse(t) || [];
        var n = 0;
        var neu = segmente.map(function (seg) {
            if (!seg) { return ''; }
            if (seg.type !== 'chip') { return _s(seg.text); }
            if (seg.chipType === altTyp && seg.name === altName) {
                n += 1;
                return _s(neuToken);
            }
            return _s(seg.raw);
        }).join('');

        return (n === 0) ? { text: roh, ersetzt: 0 }
                         : { text: neu, ersetzt: n };
    }

    /**
     * ersetzeInBlock: dasselbe ueber ALLE Textstellen eines Blocks.
     *
     * Der Durchlauf ist mapBlockTexts aus placeholder_chips.js - dieselbe
     * Vorschrift, gegen die der Server prueft. Sie liefert eine NEUE
     * block_data; das Original bleibt unangetastet, damit der Aufrufer bei
     * einem Fehlschlag noch den alten Stand in der Hand haelt.
     */
    function ersetzeInBlock(daten, altTyp, altName, neuToken, chips) {
        var pc = chips || (typeof window !== 'undefined'
            ? window.PlaceholderChips : null);
        if (!pc || typeof pc.mapBlockTexts !== 'function') {
            return { daten: daten, ersetzt: 0 };
        }
        var n = 0;
        var raus = pc.mapBlockTexts(daten, function (t) {
            var e = ersetzeInText(t, altTyp, altName, neuToken, pc);
            n += e.ersetzt;
            return e.text;
        });
        return { daten: raus, ersetzt: n };
    }

    // =====================================================================
    // 4) DER GANZE VORGANG
    // =====================================================================

    /**
     * schreibe: pruefen, bauen, zurueckprobieren, ersetzen — in dieser
     * Reihenfolge, und beim ersten Fehlschlag ohne jede Wirkung.
     *
     * auftrag = {
     *   daten : block_data (Objekt),
     *   alt   : {typ, name}       -- welcher Platzhalter wird ersetzt,
     *   neu   : {typ, name, vorgabe, beschreibung, regelfeld},
     *   chips : window.PlaceholderChips (injizierbar)
     * }
     *
     * Rueckgabe {ok, meldung, daten, ersetzt, token}. 'daten' ist bei einem
     * Fehlschlag der UNVERAENDERTE Eingabestand - der Aufrufer kann sie also
     * bedenkenlos weiterreichen, ohne den Erfolg abzufragen. Er soll es
     * trotzdem tun; 'meldung' ist dann der Grund im Klartext.
     */
    function schreibe(auftrag) {
        var a = auftrag || {};
        var alt = a.alt || {};
        var neu = a.neu || {};
        var pc = a.chips || (typeof window !== 'undefined'
            ? window.PlaceholderChips : null);
        var zurueck = { ok: false, meldung: '', daten: a.daten, ersetzt: 0,
                        token: '' };

        if (!a.daten || typeof a.daten !== 'object') {
            zurueck.meldung = 'Es liegen keine Blockdaten vor, in die '
                + 'geschrieben werden könnte.';
            return zurueck;
        }
        if (!pc || typeof pc.parse !== 'function'
                || typeof pc.mapBlockTexts !== 'function') {
            zurueck.meldung = 'Die Platzhalter-Werkzeuge '
                + '(placeholder_chips.js) sind nicht geladen. Es wird nichts '
                + 'geschrieben.';
            return zurueck;
        }

        // --- (a) die Eingaben pruefen. F1. ------------------------------
        var p = typPruefen(neu.typ);
        if (!p.ok) { zurueck.meldung = p.meldung; return zurueck; }
        p = namePruefen(neu.name);
        if (!p.ok) { zurueck.meldung = p.meldung; return zurueck; }
        var felder = [
            [neu.vorgabe, 'Die Vorgabe'],
            [neu.beschreibung, 'Die Beschreibung'],
            [neu.regelfeld, 'Das Prüfmuster']
        ];
        for (var i = 0; i < felder.length; i += 1) {
            p = feldPruefen(felder[i][0], felder[i][1]);
            if (!p.ok) { zurueck.meldung = p.meldung; return zurueck; }
        }

        // --- (b) bauen und SOFORT zurueckprobieren. --------------------
        var soll = {
            typ: _s(neu.typ), name: _s(neu.name),
            vorgabe: _s(neu.vorgabe), beschreibung: _s(neu.beschreibung),
            regelfeld: _s(neu.regelfeld)
        };
        var token = tokenBauen(soll);
        zurueck.token = token;
        p = tokenProbe(token, soll, pc);
        if (!p.ok) { zurueck.meldung = p.meldung; return zurueck; }

        // --- (c) ersetzen. --------------------------------------------
        var e = ersetzeInBlock(a.daten, _s(alt.typ), _s(alt.name), token, pc);
        if (e.ersetzt === 0) {
            // GRUNDREGEL 1: kein stiller Fehlschlag. Ein "gespeichert", nach
            // dem nichts anders ist, waere die schaedlichste aller Antworten.
            zurueck.meldung = 'Der Platzhalter "' + _s(alt.typ) + ':'
                + _s(alt.name) + '" ist im Bausteininhalt nicht mehr zu '
                + 'finden. Es ist NICHTS geändert worden. Wahrscheinlich ist '
                + 'der Text inzwischen an anderer Stelle bearbeitet worden — '
                + 'die Tabelle baut sich beim nächsten Tastendruck neu auf.';
            return zurueck;
        }

        zurueck.ok = true;
        zurueck.daten = e.daten;
        zurueck.ersetzt = e.ersetzt;
        zurueck.meldung = (e.ersetzt === 1)
            ? 'Ein Vorkommen geändert.'
            : (e.ersetzt + ' Vorkommen geändert.');
        log('geschrieben', token, e.ersetzt);
        return zurueck;
    }

    // =====================================================================
    // 5) UMD-Ausgang (Browser + vitest).
    // =====================================================================
    var API = {
        TYPEN: TYPEN,
        feldPruefen: feldPruefen,
        typPruefen: typPruefen,
        namePruefen: namePruefen,
        tokenBauen: tokenBauen,
        tokenProbe: tokenProbe,
        ersetzeInText: ersetzeInText,
        ersetzeInBlock: ersetzeInBlock,
        schreibe: schreibe
    };
    if (typeof window !== 'undefined') {
        window.AIWBausteinPhSchreiben = API;
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = API;
    }
    log('geladen');
})();
