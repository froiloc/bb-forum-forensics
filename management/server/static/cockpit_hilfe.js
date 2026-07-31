// =============================================================================
// management/server/static/cockpit_hilfe.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle H: Hilfesysteme (H3)
// =============================================================================
// Zweck (Issue 3eff6110, Teil 1 — Kontexthilfe):
//   Der HILFEMODUS der Verwaltungsoberflaeche. Ein Knopf in der Kopfzeile
//   (feste Position in JEDER Sicht) und der Tastaturweg Shift+F1 schalten die
//   Oberflaeche in einen rein lesenden Erkundungszustand: Elemente MIT Hilfe
//   bleiben klar, alles uebrige wird abgedunkelt, der Mauszeiger wird zum
//   Hilfezeiger, und kein Klick loest mehr eine Funktion aus.
//
// STAND H3 (Build 590): der MODUS, noch OHNE Popups und noch ohne ein
//   einziges data-hilfe-Attribut. Der Modus zeigt daher auf jeder Sicht
//   "alles abgedunkelt" — und genau das ist der ehrliche Zwischenstand
//   (Grundregel 1). Die Popups kommen in H4, die Inhalte ab H5.
//
// PROJEKT-GEBOTE FUER JS (eingehalten):
//   1) IIFE + 'use strict'.
//   2) DEV-Debug-Logging ueber window.AIW_COCKPIT_DEBUG — in PROD still.
//   3) Ausfuehrliche Kommentare, auch zu den Ueberlegungen.
//   4) Kapselung: der Zustandsautomat ist eine REINE Funktion ohne DOM; der
//      Rest ist duenne Verdrahtung. vitest testet damit den echten Code.
//
// ENTSCHEIDUNGEN, die hier umgesetzt sind (mc, 2026-07-30):
//   F1  Tastaturweg = Shift+F1. F1 ALLEIN ist die Browserhilfe; die duerfen
//       wir nicht kapern. preventDefault() daher NUR bei gedrueckter
//       Umschalttaste.
//   F3  Abdunkeln per Deckschicht/Grau, KEIN blur(). blur() ist auf den
//       grossen Falltabellen renderteuer und flimmert beim Scrollen.
//   F2  Das Popup oeffnet per KLICK (H4). Hover aendert hier nur den Cursor.
//
// WARUM DER KLICK IM HILFEMODUS ABGEFANGEN WIRD (wichtigste Ueberlegung
//   dieses Builds): Der Hilfemodus ist ein Erkundungszustand. Wer ihn
//   einschaltet, weiss gerade NICHT, was ein Element tut — und genau dann auf
//   eine Schaltflaeche zu klicken, die etwas freigibt, zuweist oder
//   ausschleust, waere die schlechteste aller Ueberraschungen. Der
//   Capture-Listener faengt jeden Klick VOR dem eigentlichen Ziel ab
//   (Capture-Phase, deshalb ist die Reihenfolge garantiert) und verhindert
//   ihn. Ausgenommen sind nur die Bedienelemente der Hilfe selbst.
//
// BUILD 591 (H4) ERGAENZT: das KONTEXT-POPUP samt Verweismechanik.
//   * Im Hilfemodus oeffnet ein KLICK (F2) auf ein markiertes Element ein
//     kleines Overlay: Titel, 1-4 Saetze, optionaler Verweis in die Vollhilfe.
//   * Die Inhalte kommen GEBUENDELT je Sicht von /api/help/kontext (ein Fetch
//     je Sichtaktivierung, danach zwischengespeichert) — 8-15 Popups je Sicht
//     waeren sonst 8-15 Anfragen.
//   * Der Verweis oeffnet /help#<sicht>-<anker> im BENANNTEN Fenster
//     'aiw_hilfe'. Der Name ist der ganze Trick: es gibt genau EIN
//     Hilfefenster, das bei jedem Verweis wiederverwendet wird — kein
//     Fensterstapel, der nach zehn Verweisen den Bildschirm zumauert.
//   * Unbekannter Schluessel -> Fallback-Popup "Hilfe folgt". SICHTBAR statt
//     still (Grundregel 1): ein Element, das als erklaert markiert ist, aber
//     keinen Text hat, ist ein Befund und soll auffallen.
//
// Version: v0.8.591 · Build: 591 · 2026-07-31
// =============================================================================

(function () {
    'use strict';

    // =========================================================================
    // 0) Debug-Logging (DEV) — in PROD ueber das fehlende Flag still.
    // =========================================================================
    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Hilfe]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) KONSTANTEN — an genau einer Stelle, damit CSS, JS und Tests dieselbe
    //    Schreibweise benutzen. Ein Tippfehler in einer Klasse waere sonst
    //    ein stiller Ausfall (der Modus schaltet, sieht aber nicht anders aus).
    // =========================================================================
    var KLASSE_MODUS = 'aiw-hilfe-modus';   // an <body>
    var KLASSE_KNOPF_AN = 'aiw-hilfe-an';   // am Knopf, solange der Modus laeuft
    // BUILD 592 (H5) - VEREINHEITLICHUNG AUF DAS BESTEHENDE ATTRIBUT.
    // In H3/H4 hiess das Attribut hier 'data-hilfe'. Beim Bau der Pilotsicht
    // stellte sich heraus, dass die Oberflaeche seit Build 548 bereits
    // 'data-hilfe-id' traegt - vom gemeinsamen Tabellen-Werkzeug ueber
    // fuenfzehn Sichten hinweg gesetzt. Zwei Attribute fuer dieselbe Sache
    // waeren genau die Drift, vor der das Konzept (§4.2) warnt. Es gilt
    // deshalb NUR NOCH das aeltere und weiter verbreitete.
    var ATTR_HILFE = 'data-hilfe-id';
    var ID_KNOPF = 'aiw-hilfe-btn';
    var ID_POPUP = 'aiw-hilfe-popup';
    var KLASSE_POPUP = 'aiw-hilfe-popup';
    var FENSTER_HILFE = 'aiw_hilfe';        // EIN benanntes Hilfefenster
    var ABSTAND = 10;                       // px zwischen Element und Popup
    var POPUP_BREITE = 320;                 // px, deckungsgleich mit dem CSS

    // Der ehrliche Platzhalter. Wortgleich mit render_html.PLATZHALTER_TEXT —
    // beide Seiten sollen dasselbe sagen; test_help_render.py haelt den
    // Wortlaut serverseitig fest.
    var TEXT_OFFEN = 'Hilfe folgt (Baustelle H).';

    // =========================================================================
    // 2) REINER ZUSTANDSAUTOMAT (kein DOM, keine Seiteneffekte).
    //
    //    Bewusst als reine Funktion: der Modus hat nur zwei Zustaende, aber
    //    fuenf Ereignisse, die ihn verlassen. Genau solche Kombinationen
    //    verrutschen erfahrungsgemaess — als reine Funktion sind sie
    //    vollstaendig und billig pruefbar.
    // =========================================================================

    // ZUSTAND: { an: boolean, sicht: string|null }
    function anfangszustand() {
        return { an: false, sicht: null };
    }

    /**
     * naechsterZustand(zustand, ereignis)
     *
     * ereignis ist eines von:
     *   'einschalten' | 'ausschalten' | 'umschalten' | 'escape' | 'sichtwechsel'
     * Bei 'sichtwechsel' traegt nutzlast die neue Sicht-ID.
     *
     * REGELN:
     *   - 'escape' schaltet NUR aus (nie ein) — Escape ist ueberall im
     *     Werkzeug die Abbruchtaste; als Einschalter waere sie eine Falle.
     *   - 'sichtwechsel' verlaesst den Modus IMMER. Begruendung: die
     *     Hilfe-Schluessel sind sichtbezogen, und ein Modus, der ueber den
     *     Sichtwechsel hinweg bestehen bliebe, zeigte auf der neuen Sicht
     *     lauter abgedunkelte Elemente ohne erkennbaren Grund.
     *   - unbekanntes Ereignis laesst den Zustand unveraendert (kein stiller
     *     Sprung in einen dritten Zustand).
     */
    function naechsterZustand(zustand, ereignis, nutzlast) {
        var z = zustand || anfangszustand();
        switch (ereignis) {
        case 'einschalten':
            return { an: true, sicht: z.sicht };
        case 'ausschalten':
        case 'escape':
            return { an: false, sicht: z.sicht };
        case 'umschalten':
            return { an: !z.an, sicht: z.sicht };
        case 'sichtwechsel':
            return { an: false, sicht: (nutzlast === undefined) ? z.sicht : nutzlast };
        default:
            return { an: z.an, sicht: z.sicht };
        }
    }

    /**
     * istHilfeTaste(ereignis) — REIN.
     *
     * Nur Shift+F1. F1 allein gehoert dem Browser (Hilfe); wir fassen es
     * nicht an, damit die gewohnte Taste gewohnt bleibt.
     */
    function istHilfeTaste(ev) {
        if (!ev) { return false; }
        return ev.key === 'F1' && ev.shiftKey === true
            && ev.ctrlKey !== true && ev.altKey !== true;
    }

    /** istAbbruchtaste(ereignis) — REIN. */
    function istAbbruchtaste(ev) {
        return !!ev && (ev.key === 'Escape' || ev.key === 'Esc');
    }

    /**
     * koerperKlassen(vorhandene, zustand) — REIN.
     *
     * Liefert die Klassenliste des <body> fuer einen Zustand. Als reine
     * Funktion, damit die Klassenlogik ohne DOM pruefbar ist (und damit sie
     * fremde Klassen NICHT antastet — der body traegt auch anderes).
     */
    function koerperKlassen(vorhandene, zustand) {
        var liste = (vorhandene || []).filter(function (k) {
            return k && k !== KLASSE_MODUS;
        });
        if (zustand && zustand.an) { liste.push(KLASSE_MODUS); }
        return liste;
    }

    /**
     * istHilfeBedienelement(element, wurzelPruefer) — REIN genug (nur DOM-Lesen).
     *
     * Die Bedienelemente der Hilfe selbst duerfen im Hilfemodus geklickt
     * werden — sonst kaeme man aus dem Modus nur noch per Escape heraus.
     */
    function istHilfeBedienelement(el) {
        var n = el;
        while (n && n.nodeType === 1) {
            if (n.id === ID_KNOPF) { return true; }
            if (n.classList && n.classList.contains('aiw-hilfe-popup')) {
                return true;
            }
            n = n.parentNode;
        }
        return false;
    }

    /**
     * hilfeSchluessel(element) — sucht am Element oder seinen Vorfahren das
     * literale data-hilfe-Attribut und liefert seinen Wert (oder null).
     *
     * Warum aufwaerts gesucht wird: Ein Klick landet oft auf einem <span> in
     * einer Schaltflaeche. Das Attribut soll am sinntragenden Element haengen
     * duerfen, nicht am innersten Textknoten.
     */
    function hilfeSchluessel(el) {
        var n = el;
        while (n && n.nodeType === 1) {
            if (n.hasAttribute && n.hasAttribute(ATTR_HILFE)) {
                return n.getAttribute(ATTR_HILFE);
            }
            n = n.parentNode;
        }
        return null;
    }

    // =========================================================================
    // 2b) REINE FUNKTIONEN DES POPUPS (Build 591 / H4) — kein DOM.
    // =========================================================================

    /**
     * popupLage(ziel, popup, sichtfeld, abstand) — REIN.
     *
     * ziel      = { links, oben, breite, hoehe }  (Rechteck des Elements,
     *             bereits in Dokumentkoordinaten — der Aufrufer addiert den
     *             Bildlauf, damit diese Funktion nichts ueber Scrollen wissen
     *             muss)
     * popup     = { breite, hoehe }
     * sichtfeld = { breite, hoehe, scrollX, scrollY }
     *
     * REGELN, und warum sie so sind:
     *   1) Erste Wahl ist UNTERHALB des Elements. Der Blick wandert beim Lesen
     *      nach unten; ein Popup ueber dem Element verdeckt ausserdem genau
     *      das, was man gerade erklaert haben will.
     *   2) Passt es unten nicht mehr ins Sichtfeld, wandert es NACH OBEN —
     *      aber nur, wenn dort tatsaechlich mehr Platz ist. Sonst bleibt es
     *      unten und wird an den Rand geschoben; ein Popup, das halb aus dem
     *      Bild ragt, ist schlimmer als eines, das dicht am Rand klebt.
     *   3) Waagerecht linksbuendig zum Element, dann in das Sichtfeld
     *      hineingeklemmt.
     * Rueckgabe: { links, oben, seite: 'unten'|'oben' }
     */
    function popupLage(ziel, popup, sichtfeld, abstand) {
        var a = (abstand === undefined) ? ABSTAND : abstand;
        var sx = sichtfeld.scrollX || 0;
        var sy = sichtfeld.scrollY || 0;

        // Platz oberhalb/unterhalb, gemessen im SICHTFELD (nicht im Dokument).
        var zielObenImBild = ziel.oben - sy;
        var platzUnten = sichtfeld.hoehe - (zielObenImBild + ziel.hoehe) - a;
        var platzOben = zielObenImBild - a;

        var seite = 'unten';
        if (popup.hoehe > platzUnten && platzOben > platzUnten) {
            seite = 'oben';
        }

        var oben = (seite === 'unten')
            ? (ziel.oben + ziel.hoehe + a)
            : (ziel.oben - popup.hoehe - a);

        // Nach oben nicht aus dem Dokument herauslaufen.
        if (oben < sy + a) { oben = sy + a; }

        var links = ziel.links;
        var maxLinks = sx + sichtfeld.breite - popup.breite - a;
        if (links > maxLinks) { links = maxLinks; }
        if (links < sx + a) { links = sx + a; }

        return { links: Math.round(links), oben: Math.round(oben), seite: seite };
    }

    /**
     * vollhilfeUrl(verweis) — REIN.
     *
     * '<sicht>#<anker>'  ->  '/help#<sicht>-<anker>'
     *
     * Die Sprungmarke wird serverseitig in render_html.anker_id() nach
     * derselben Regel gebildet. Sie steht bewusst an ZWEI Stellen im Code und
     * an EINER Stelle im Test (der Verweistest prueft beide gegeneinander) —
     * eine gemeinsame Datei fuer eine Zeichenkette waere hier mehr Apparat
     * als Nutzen.
     */
    function vollhilfeUrl(verweis) {
        if (!verweis) { return null; }
        var teile = String(verweis).split('#');
        if (teile.length !== 2 || !teile[0] || !teile[1]) { return null; }
        return '/help#' + teile[0] + '-' + teile[1];
    }

    /**
     * popupInhalt(schluessel, eintraege) — REIN.
     *
     * Waehlt den anzuzeigenden Inhalt. Kein Treffer -> ehrlicher Platzhalter
     * MIT dem Schluessel, damit man im Betrieb sofort weiss, welcher Text
     * fehlt. Das ist der Unterschied zwischen "da ist nichts" und "da fehlt
     * genau dieser Eintrag".
     */
    function popupInhalt(schluessel, eintraege) {
        var e = (eintraege || {})[schluessel];
        if (e) {
            return {
                titel: e.titel || schluessel,
                text: e.text || '',
                verweis: e.verweis || null,
                offen: false
            };
        }
        return {
            titel: schluessel || 'Hilfe',
            text: TEXT_OFFEN,
            verweis: null,
            offen: true
        };
    }

    // =========================================================================
    // 3) CONTROLLER (DOM).
    // =========================================================================

    var zustand = anfangszustand();
    var gebunden = false;

    function koerper() {
        return (typeof document !== 'undefined') ? document.body : null;
    }

    function knopf() {
        return (typeof document !== 'undefined')
            ? document.getElementById(ID_KNOPF) : null;
    }

    /** Zustand -> DOM. EINE Stelle, an der sich Sichtbares aendert. */
    function anwenden() {
        var b = koerper();
        if (b) {
            var neu = koerperKlassen(
                Array.prototype.slice.call(b.classList), zustand);
            b.className = neu.join(' ');
        }
        var k = knopf();
        if (k) {
            if (zustand.an) {
                k.classList.add(KLASSE_KNOPF_AN);
                k.setAttribute('aria-pressed', 'true');
            } else {
                k.classList.remove(KLASSE_KNOPF_AN);
                k.setAttribute('aria-pressed', 'false');
            }
        }
        log('Zustand angewandt:', JSON.stringify(zustand));
    }

    function schalte(ereignis, nutzlast) {
        var vorher = zustand.an;
        zustand = naechsterZustand(zustand, ereignis, nutzlast);
        if (vorher !== zustand.an || ereignis === 'sichtwechsel') {
            anwenden();
            if (vorher && !zustand.an) { beimVerlassen(); }
        }
    }

    // Aufraeumhaken. Seit H4 schliesst er das offene Popup. Er stand schon in
    // H3 hier, damit der Ausschaltweg von Anfang an EINER ist und nicht an
    // fuenf Stellen ergaenzt werden muss.
    var _beimVerlassen = function () {};
    function beimVerlassen() {
        popupSchliessen();
        _beimVerlassen();
    }

    // =========================================================================
    // 3b) KONTEXTTEXTE (Build 591 / H4).
    //
    // Ein Fetch je Sicht, danach zwischengespeichert. Der Speicher wird beim
    // SICHTWECHSEL NICHT geleert: die Texte einer Sicht aendern sich waehrend
    // einer Sitzung nicht (sie sind Auslieferungsbestand), und wer zwischen
    // zwei Sichten hin- und herspringt, soll nicht jedes Mal warten.
    // =========================================================================

    var _kontextSpeicher = {};      // sichtId -> { schluessel: {titel,text,verweis} }
    var _kontextLaeuft = {};        // sichtId -> Promise (kein Doppel-Fetch)

    /** Standard-Bezug ueber fetch(). In Tests ersetzbar (init.holeKontext). */
    function holeKontextStandard(sichtId) {
        if (typeof fetch !== 'function') {
            return Promise.resolve({});
        }
        return fetch('/api/help/kontext?sicht=' + encodeURIComponent(sichtId),
                     { credentials: 'same-origin' })
            .then(function (r) {
                // 403/404 sind KEINE Ausnahmen, sondern Auskuenfte: die Person
                // darf die Sicht nicht sehen bzw. es gibt sie nicht. Beides
                // fuehrt zu einem leeren Bestand und damit zu ehrlichen
                // Platzhalter-Popups — nicht zu einem stummen Modus.
                if (!r.ok) {
                    log('Kontext-Abruf fuer', sichtId, 'liefert', r.status);
                    return { eintraege: {} };
                }
                return r.json();
            })
            .then(function (d) { return (d && d.eintraege) || {}; })
            .catch(function (err) {
                // eslint-disable-next-line no-console
                console.error('[AIW-Hilfe] Kontext-Abruf fehlgeschlagen:', err);
                return {};
            });
    }

    var _holeKontext = holeKontextStandard;

    function kontextFuer(sichtId) {
        if (!sichtId) { return Promise.resolve({}); }
        if (_kontextSpeicher[sichtId]) {
            return Promise.resolve(_kontextSpeicher[sichtId]);
        }
        if (_kontextLaeuft[sichtId]) { return _kontextLaeuft[sichtId]; }
        var p = Promise.resolve(_holeKontext(sichtId))
            .then(function (eintraege) {
                _kontextSpeicher[sichtId] = eintraege || {};
                delete _kontextLaeuft[sichtId];
                log('Kontext geladen fuer', sichtId, '-',
                    Object.keys(_kontextSpeicher[sichtId]).length, 'Eintraege');
                return _kontextSpeicher[sichtId];
            });
        _kontextLaeuft[sichtId] = p;
        return p;
    }

    // =========================================================================
    // 3c) DAS POPUP (Build 591 / H4).
    // =========================================================================

    var _popupEl = null;

    function popupSchliessen() {
        if (_popupEl && _popupEl.parentNode) {
            _popupEl.parentNode.removeChild(_popupEl);
        }
        _popupEl = null;
    }

    /**
     * Baut das Popup. XSS-Disziplin wie in allen Sichten: JEDER Text ueber
     * textContent, nie ueber innerHTML. Die Hilfetexte sind zwar
     * hausgeschrieben — die Disziplin bleibt trotzdem, weil sie sonst genau
     * einmal vergessen wird.
     */
    function popupBauen(inhalt) {
        var d = document;
        var box = d.createElement('div');
        box.id = ID_POPUP;
        box.className = KLASSE_POPUP + (inhalt.offen ? ' aiw-hilfe-popup-offen' : '');
        box.setAttribute('role', 'dialog');
        box.setAttribute('aria-live', 'polite');

        var kopf = d.createElement('div');
        kopf.className = 'aiw-hilfe-popup-kopf';
        var titel = d.createElement('strong');
        titel.textContent = inhalt.titel;
        kopf.appendChild(titel);

        var zu = d.createElement('button');
        zu.type = 'button';
        zu.className = 'aiw-hilfe-popup-zu';
        zu.setAttribute('aria-label', 'Hilfe schließen');
        zu.textContent = '×';
        zu.addEventListener('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            popupSchliessen();
        });
        kopf.appendChild(zu);
        box.appendChild(kopf);

        var text = d.createElement('p');
        text.className = 'aiw-hilfe-popup-text';
        text.textContent = inhalt.text;
        box.appendChild(text);

        var url = vollhilfeUrl(inhalt.verweis);
        if (url) {
            var a = d.createElement('a');
            a.className = 'aiw-hilfe-popup-mehr';
            a.href = url;
            // Das BENANNTE Fenster: genau ein Hilfefenster, das bei jedem
            // Verweis wiederverwendet wird (Konzept §3.3).
            a.target = FENSTER_HILFE;
            a.rel = 'noopener';
            a.textContent = 'Mehr dazu in der Vollhilfe →';
            box.appendChild(a);
        }
        return box;
    }

    function popupZeigen(schluessel, element) {
        popupSchliessen();
        if (typeof document === 'undefined' || !element) { return; }

        var sichtId = zustand.sicht;
        kontextFuer(sichtId).then(function (eintraege) {
            // Zwischenzeitlich ausgeschaltet oder Sicht gewechselt? Dann kein
            // verspaetetes Popup mehr aufblenden.
            if (!zustand.an || zustand.sicht !== sichtId) { return; }

            var inhalt = popupInhalt(schluessel, eintraege);
            var box = popupBauen(inhalt);
            document.body.appendChild(box);
            _popupEl = box;

            // Erst nach dem Einhaengen messen — vorher hat das Element keine
            // Groesse. Die Lage selbst rechnet die reine Funktion.
            var r = (typeof element.getBoundingClientRect === 'function')
                ? element.getBoundingClientRect()
                : { left: 0, top: 0, width: 0, height: 0 };
            var sx = (typeof window !== 'undefined' && window.scrollX) || 0;
            var sy = (typeof window !== 'undefined' && window.scrollY) || 0;
            var lage = popupLage(
                { links: r.left + sx, oben: r.top + sy,
                  breite: r.width, hoehe: r.height },
                { breite: box.offsetWidth || POPUP_BREITE,
                  hoehe: box.offsetHeight || 120 },
                { breite: (window && window.innerWidth) || 1280,
                  hoehe: (window && window.innerHeight) || 800,
                  scrollX: sx, scrollY: sy });

            box.style.left = lage.links + 'px';
            box.style.top = lage.oben + 'px';
            box.setAttribute('data-seite', lage.seite);
            log('Popup zu', schluessel, 'bei', JSON.stringify(lage));
        });
    }

    function einschalten() { schalte('einschalten'); }
    function ausschalten() { schalte('ausschalten'); }
    function umschalten() { schalte('umschalten'); }

    /** Wird von cockpit.js bei jedem Sichtwechsel gerufen. */
    function sichtGewechselt(sichtId) {
        schalte('sichtwechsel', sichtId || null);
        log('Sichtwechsel ->', sichtId);
    }

    function aktiveSicht() { return zustand.sicht; }
    function istAn() { return zustand.an === true; }

    // --- Ereignisse ----------------------------------------------------------

    function aufTaste(ev) {
        if (istHilfeTaste(ev)) {
            // preventDefault NUR hier: bei Shift+F1. F1 ohne Shift laeuft
            // unangetastet an den Browser weiter.
            if (typeof ev.preventDefault === 'function') { ev.preventDefault(); }
            umschalten();
            return;
        }
        if (zustand.an && istAbbruchtaste(ev)) {
            ausschalten();
        }
    }

    /**
     * Klicksperre in der CAPTURE-Phase.
     *
     * Capture ist hier nicht Geschmackssache: In der Bubble-Phase haette das
     * Ziel den Klick laengst verarbeitet. Nur in der Capture-Phase kommen wir
     * VOR dem Ziel an die Reihe und koennen die Ausfuehrung verhindern.
     */
    function aufKlick(ev) {
        if (!zustand.an) { return; }
        var ziel = ev.target;
        if (istHilfeBedienelement(ziel)) { return; }

        if (typeof ev.preventDefault === 'function') { ev.preventDefault(); }
        if (typeof ev.stopPropagation === 'function') { ev.stopPropagation(); }
        if (typeof ev.stopImmediatePropagation === 'function') {
            ev.stopImmediatePropagation();
        }

        var schluessel = hilfeSchluessel(ziel);
        log('Klick im Hilfemodus abgefangen; Schluessel =', schluessel);
        if (schluessel) {
            popupZeigen(schluessel, elementMitSchluessel(ziel));
        } else {
            // Klick ins Leere schliesst ein offenes Popup — dasselbe
            // Verhalten wie ueberall sonst in der Oberflaeche.
            popupSchliessen();
        }
        _beimKlick(schluessel, ziel, ev);
    }

    /** Das Element, an dem das Attribut wirklich haengt (fuer die Messung). */
    function elementMitSchluessel(el) {
        var n = el;
        while (n && n.nodeType === 1) {
            if (n.hasAttribute && n.hasAttribute(ATTR_HILFE)) { return n; }
            n = n.parentNode;
        }
        return el;
    }

    var _beimKlick = function () {};

    /**
     * init(optionen)
     *   optionen.beimKlick     — (schluessel, element, ereignis) => void  (H4)
     *   optionen.beimVerlassen — () => void                               (H4)
     *
     * Bindet Knopf und Tastatur EINMAL. Mehrfachaufruf ist unschaedlich
     * (idempotent) — cockpit.js ruft init() beim Hochfahren, Tests rufen es
     * je Testfall.
     */
    function init(optionen) {
        var o = optionen || {};
        if (typeof o.beimKlick === 'function') { _beimKlick = o.beimKlick; }
        if (typeof o.beimVerlassen === 'function') {
            _beimVerlassen = o.beimVerlassen;
        }
        // Build 591: der Bezugsweg der Kontexttexte ist austauschbar. Im
        // Betrieb ist es fetch(); im Test ein Stub. Dadurch braucht der Test
        // keinen Server und prueft trotzdem den echten Code.
        if (typeof o.holeKontext === 'function') {
            _holeKontext = o.holeKontext;
        }

        if (!gebunden && typeof document !== 'undefined') {
            document.addEventListener('keydown', aufTaste);
            document.addEventListener('click', aufKlick, true);  // capture!
            var k = knopf();
            if (k) {
                k.addEventListener('click', function (ev) {
                    if (typeof ev.preventDefault === 'function') {
                        ev.preventDefault();
                    }
                    umschalten();
                });
            }
            gebunden = true;
        }
        anwenden();
        log('init (Knopf %s)', knopf() ? 'gefunden' : 'NICHT gefunden');
    }

    // =========================================================================
    // 4) UMD-Ausgang.
    // =========================================================================
    var API = {
        // reine Funktionen (vitest prueft sie ohne DOM)
        naechsterZustand: naechsterZustand,
        anfangszustand: anfangszustand,
        istHilfeTaste: istHilfeTaste,
        istAbbruchtaste: istAbbruchtaste,
        koerperKlassen: koerperKlassen,
        hilfeSchluessel: hilfeSchluessel,
        istHilfeBedienelement: istHilfeBedienelement,
        popupLage: popupLage,
        vollhilfeUrl: vollhilfeUrl,
        popupInhalt: popupInhalt,
        // Controller
        init: init,
        popupSchliessen: popupSchliessen,
        kontextFuer: kontextFuer,
        einschalten: einschalten,
        ausschalten: ausschalten,
        umschalten: umschalten,
        sichtGewechselt: sichtGewechselt,
        istAn: istAn,
        aktiveSicht: aktiveSicht,
        // Konstanten (damit Tests und spaetere Module nicht raten muessen)
        KLASSE_MODUS: KLASSE_MODUS,
        ATTR_HILFE: ATTR_HILFE,
        ID_KNOPF: ID_KNOPF,
        ID_POPUP: ID_POPUP,
        FENSTER_HILFE: FENSTER_HILFE,
        TEXT_OFFEN: TEXT_OFFEN,
        _debugState: function () { return zustand; }   // nur fuer Tests
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitHilfe = API; }
})();
