// =============================================================================
// management/server/static/cockpit_dashboard.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kachelflaeche im Ueberblick
// =============================================================================
// Zweck (AP-3G / Idee 37, Build 547):
//   Der Ueberblick wird zur KACHELFLAECHE. Jede Kachel ist eine gedraengte
//   Schnellauskunft aus einem BESTEHENDEN lesenden Endpunkt — dieses
//   Arbeitspaket legt keinen neuen Datenweg an. Welche Kacheln erscheinen und
//   in welcher Folge, entscheidet die Person selbst (gespeichert ueber
//   /api/viewprefs, art='widget', Build 545).
//
// ── DIE WERKSEINSTELLUNG SIEHT AUS WIE BISHER ──────────────────────────────
//
//   Ohne gespeicherte Vorliebe ist genau EINE Kachel aktiv: 'fallampel'. Und
//   diese Kachel ERSETZT die bisherige Fall-Uebersicht nicht, sie BETTET SIE
//   EIN — cockpit_overview.renderOverview() zeichnet weiterhin dieselbe
//   Tabulator-Tabelle in den Kachelrumpf (Steckplatz-Verfahren, s. unten).
//
//   DAS IST KEIN KOSMETISCHER PUNKT. Die Kommandopalette (Strg-K) springt
//   ueber focusCase() in GENAU DIESE Tabulator-Instanz (cockpit.js,
//   loadOverview seit Build 459). Haette die Kachel die Tabelle durch eine
//   eigene, gedraengte Darstellung ersetzt, waere der Fall-Sprung still
//   ausgefallen — die Palette haette weiter zur Uebersicht gewechselt und dort
//   nichts mehr hervorheben koennen.
//
// ── JEDE REDUKTION WIRD BENANNT (Bedingung aus der Abstimmung mc 2026-07-26)
//
//   Eine Kachel zeigt weniger als der Endpunkt liefert. Das ist ihr Zweck —
//   und ihre Gefahr: ein Ausschnitt, der nicht als Ausschnitt kenntlich ist,
//   sieht aus wie ein vollstaendiges Bild. In diesem Werkzeug waere das die
//   Behauptung "mehr liegt nicht an". Es gibt ZWEI Arten von Reduktion, und
//   BEIDE stehen in der Kachel:
//
//     (1) ABSCHNEIDEN — "5 von 23 angezeigt" (hinweisReduktion).
//     (2) FILTERN     — "nur fällige und überfällige" (Feld 'grundlage').
//
//   Ein Test haelt fest, dass keine Kachel abschneidet oder filtert, ohne es
//   zu sagen. Und LEER IST NICHT DASSELBE WIE AUSGEFALLEN: ein Leerbefund
//   sagt "nichts liegt an", ein Fehlschlag sagt, dass die Erhebung nicht
//   gelaufen ist (Grundregel 1).
//
// ── DIE FRISTEN-KACHEL IST DIE HEIKELSTE ───────────────────────────────────
//
//   Sie ist die einzige, an der eine RECHTSFOLGE haengt. Sie zeigt deshalb
//   KEINE Zahl, wenn der Parametersatz nicht bestaetigt ist oder der Endpunkt
//   keine Aussage zulaesst — dann steht dort der Grund. Und die Vorbehalte
//   des Endpunkts fahren IMMER mit, auch wenn eine Zahl da steht. Eine
//   Kachel, die "3 Fristen laufen ab" sagt und den Vorbehalt weglaesst, waere
//   schlimmer als keine Kachel.
//
// JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging (zur Laufzeit
//   umschaltbar, PROD aus); ausfuehrliche Kommentare; Kapselung; REINE
//   Funktionen (alle Reduzierer) fassen NIE das DOM an; UMD-artiger Ausgang ->
//   vitest prueft den ECHTEN Code.
//
// SICHERHEIT (XSS): Fall- und Personendaten (username, display_name, Betreff)
//   stammen aus Forumsdaten bzw. dem AD und sind fremdbestimmt — saemtlicher
//   variabler Text wird via textContent gesetzt, NIE via innerHTML.
//
// Build 637 (Vorgang 17200856, Welle B5 - die letzte): HILFE-MARKEN
//   fuer die eine verbliebenen Bedienelemente dieser Sicht.
// Version: v0.8.637 · Build: 637 · 2026-08-01
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
        args.unshift('[AIW-Dashboard]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '\u2014';
    // BUILD 573: von 5 auf 3. Ein Dashboard soll wenig lesen und viel
    // schauen lassen (Festlegung mc). Fuenf Zeilen je Kachel waren der Grund,
    // warum die Kacheln zu Textbloecken wurden; drei genuegen, um die
    // Groessenordnung an einem Beispiel festzumachen, und der vollstaendige
    // Bestand steht ohnehin in der zugehoerigen Sicht. Die Zahl der
    // ausgelassenen Zeilen nennt die Fusszeile ('3/9') - abgeschnitten wird
    // sichtbar, nicht still.
    var MAX_ZEILEN = 3;

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM). Genau diese testet vitest.
    // =========================================================================

    // Ampel-Rang wie in cockpit_overview.js/dashboard_repo: Schwere zuerst.
    // Unbekannt -> 99 (ans Ende), damit fehlerhafte Werte nie still
    // verschwinden (Grundregel 1).
    var AMPEL_RANG = { rot: 0, gelb: 1, gruen: 2 };
    function ampelRang(a) {
        return Object.prototype.hasOwnProperty.call(AMPEL_RANG, a)
            ? AMPEL_RANG[a] : 99;
    }

    // hinweisReduktion: der Satz, der das Abschneiden benennt.
    // Leer NUR, wenn nichts weggelassen wurde. Das ist die Zusicherung.
    function hinweisReduktion(gezeigt, gesamt) {
        if (typeof gesamt !== 'number' || gesamt <= gezeigt) { return ''; }
        return gezeigt + ' von ' + gesamt + ' angezeigt';
    }

    // leeresModell/fehlerModell: die beiden Sonderlagen, ausdruecklich
    // getrennt. Ein Fehlschlag darf NIE wie ein Leerbefund aussehen.
    function fehlerModell(text) {
        return {
            kopf: EM_DASH, unterzeile: '', zeilen: [], gesamt: null,
            gezeigt: 0, hinweis: '', grundlage: '', vorbehalt: '',
            leer: false, fehler: text || 'Abruf fehlgeschlagen'
        };
    }
    // kurzHinweis: '3 von 9 angezeigt' -> '3/9'. Die Aussage bleibt, die
    // Zeichenzahl drittelt sich. Passt das Muster nicht, wird der Text
    // UNVERAENDERT durchgelassen — Raten waere schlimmer als Laenge.
    function kurzHinweis(text) {
        var m = /(\d+)\s+von\s+(\d+)/.exec(String(text || ''));
        return m ? (m[1] + '/' + m[2]) : String(text || '');
    }

    function modell(o) {
        var m = {
            kopf: EM_DASH, unterzeile: '', zeilen: [], gesamt: null,
            gezeigt: 0, hinweis: '', grundlage: '', vorbehalt: '',
            leer: false, fehler: null, tonung: null
        };
        for (var k in (o || {})) {
            if (Object.prototype.hasOwnProperty.call(o, k)) { m[k] = o[k]; }
        }
        m.gezeigt = m.zeilen.length;
        if (!m.hinweis) { m.hinweis = hinweisReduktion(m.gezeigt, m.gesamt); }
        return m;
    }

    function zahl(n) { return (typeof n === 'number') ? n : 0; }

    // --- 1a) Fall-Uebersicht (/api/overview) ---------------------------------
    // Diese Kachel bettet die ECHTE Tabelle ein (Steckplatz). Das Modell dient
    // nur der Kopfzeile — es schneidet NICHTS ab, also auch kein Hinweis.
    function reduceFallampel(data) {
        if (!data || data.fehler) {
            return fehlerModell(data && data.fehler);
        }
        var faelle = (data.cases || []);
        var z = { rot: 0, gelb: 0, gruen: 0, sonst: 0 };
        faelle.forEach(function (c) {
            if (Object.prototype.hasOwnProperty.call(z, c.ampel)) {
                z[c.ampel] += 1;
            } else { z.sonst += 1; }
        });
        var teile = [z.rot + ' rot', z.gelb + ' gelb', z.gruen + ' grün'];
        // Unbekannte Ampelwerte werden GENANNT statt stillschweigend unter
        // 'grün' verbucht.
        if (z.sonst) { teile.push(z.sonst + ' ohne Einstufung'); }

        // BUILD 574 - AUS DER TABELLENKACHEL WIRD EINE KOMPAKTUEBERSICHT.
        //
        // Bis hierher bettete diese Kachel die VOLLSTAENDIGE Falltabelle ein
        // und schnitt daher nichts ab; 'gesamt' blieb bewusst null, damit
        // modell() keinen Reduktionshinweis erzeugt, dem keine Reduktion
        // entspricht. Diese Begruendung ist mit der Kompaktform ERLEDIGT:
        // die Kachel zeigt jetzt die drei dringendsten Faelle von allen
        // (Festlegung mc 2026-07-30), sie SCHNEIDET also ab - und dann MUSS
        // der Hinweis '3 von 248 angezeigt' erscheinen, sonst saehe ein
        // Ausschnitt wie ein vollstaendiges Bild aus (Grundregel 1).
        //
        // Die vollstaendige Tabelle steht in der Sicht 'faelle'.
        //
        // 'Dringlichkeit' ist dieselbe Ordnung wie bei den eigenen Auftraegen:
        // Ampel zuerst, bei gleicher Ampel die Prioritaet. Zwei Kacheln mit
        // demselben Wort duerfen nicht verschieden sortieren.
        var dringend = faelle.slice().sort(function (a, b) {
            var r = ampelRang(a.ampel) - ampelRang(b.ampel);
            if (r !== 0) { return r; }
            return zahl(a.priority) - zahl(b.priority);
        });
        return modell({
            kopf: String(zahl(data.count)),
            unterzeile: teile.join(' · '),
            grundlage: faelle.length > MAX_ZEILEN
                ? 'nach Ampel und Priorität' : '',
            zeilen: dringend.slice(0, MAX_ZEILEN).map(function (c) {
                return { text: (c.username || ('Fall ' + c.subject_id)),
                         stufe: c.ampel };
            }),
            gesamt: faelle.length,
            leer: faelle.length === 0
        });
    }

    // --- 1b) Eskalationen (/api/escalations) ---------------------------------
    var SEV_RANG = { hoch: 0, mittel: 1, niedrig: 2 };
    function reduceEskalationen(data, max) {
        if (!data || data.fehler) { return fehlerModell(data && data.fehler); }
        max = max || MAX_ZEILEN;
        var items = (data.items || []).slice().sort(function (a, b) {
            var ra = Object.prototype.hasOwnProperty.call(SEV_RANG, a.severity)
                ? SEV_RANG[a.severity] : 99;
            var rb = Object.prototype.hasOwnProperty.call(SEV_RANG, b.severity)
                ? SEV_RANG[b.severity] : 99;
            if (ra !== rb) { return ra - rb; }
            return zahl(b.days_inactive) - zahl(a.days_inactive);
        });
        return modell({
            kopf: String(items.length),
            unterzeile: zahl(data.count_hoch) + ' hoch · '
                + zahl(data.count_mittel) + ' mittel · '
                + zahl(data.count_niedrig) + ' niedrig',
            zeilen: items.slice(0, max).map(function (i) {
                return {
                    text: i.label + (i.subject_id !== null
                        && i.subject_id !== undefined
                        ? ' (Fall ' + i.subject_id + ')' : ''),
                    stufe: i.severity
                };
            }),
            gesamt: items.length,
            leer: items.length === 0
        });
    }

    // --- 1c) Naechstbeste Aktion (/api/next_actions) -------------------------
    function reduceNextActions(data, max) {
        if (!data || data.fehler) { return fehlerModell(data && data.fehler); }
        max = max || MAX_ZEILEN;
        var items = (data.items || []);
        return modell({
            kopf: String(zahl(data.actionable)),
            unterzeile: 'von ' + zahl(data.total_cases) + ' Fällen',
            zeilen: items.slice(0, max).map(function (i) {
                return { text: (i.username || ('Fall ' + i.subject_id))
                    + ': ' + (i.action || EM_DASH), stufe: i.ampel };
            }),
            gesamt: items.length,
            leer: items.length === 0
        });
    }

    // --- 1d) Faellige Wiedervorlagen (/api/external) -------------------------
    // HIER WIRD GEFILTERT, NICHT NUR ABGESCHNITTEN: die Kachel zeigt
    // ausschliesslich Ueberfaelliges (rot) und Faelliges (gelb). Das steht in
    // 'grundlage' und erscheint in der Kachel — sonst waere die Zahl eine
    // Aussage ueber ALLE Vorgaenge, und das waere falsch.
    function reduceWiedervorlage(data, max) {
        if (!data || data.fehler) { return fehlerModell(data && data.fehler); }
        max = max || MAX_ZEILEN;
        var alle = (data.matters || []);
        var faellig = alle.filter(function (m) {
            return m.ampel === 'rot' || m.ampel === 'gelb';
        });
        var c = data.counts || {};
        return modell({
            kopf: String(faellig.length),
            unterzeile: zahl(c.rot) + ' überfällig · ' + zahl(c.gelb)
                + ' fällig',
            grundlage: 'nur fällige und überfällige Vorgänge (von '
                + alle.length + ')',
            zeilen: faellig.slice(0, max).map(function (m) {
                return { text: (m.kind_label || m.kind || EM_DASH) + ': '
                    + (m.betreff || EM_DASH), stufe: m.ampel };
            }),
            gesamt: faellig.length,
            leer: faellig.length === 0
        });
    }

    // --- 1e) Fristen mit Vorwarnung (/api/limitation) ------------------------
    //
    // DIE EINZIGE KACHEL MIT EINER RECHTSFOLGE. Zwei Regeln, die nicht
    // verhandelbar sind:
    //   (1) KEINE ZAHL OHNE AUSSAGE. Ist der Parametersatz nicht bestaetigt
    //       oder verweigert der Endpunkt die Aussage, steht in der Kachel der
    //       GRUND und keine Zahl. Eine Zahl waere eine unbelegte
    //       Rechtsbehauptung.
    //   (2) DIE VORBEHALTE FAHREN IMMER MIT, auch wenn eine Zahl da steht.
    function reduceFristen(data, max) {
        if (!data || data.fehler) { return fehlerModell(data && data.fehler); }
        max = max || MAX_ZEILEN;
        var vorbehalt = (data.vorbehalte || []).join(' ');

        if (data.params_bestaetigt === false
                || data.aussage_moeglich === false) {
            return modell({
                kopf: EM_DASH,
                unterzeile: data.verweigerungsgrund
                    || 'Es ist keine Aussage möglich.',
                grundlage: data.params_bestaetigt === false
                    ? 'Der Parametersatz ist nicht bestätigt.' : '',
                vorbehalt: vorbehalt,
                zeilen: [], gesamt: null, leer: false
            });
        }

        var vorwarn = zahl(data.vorwarn_tage);
        var rows = (data.rows || []).filter(function (r) {
            return r.aussage_moeglich === true
                && typeof r.restlaufzeit_tage === 'number'
                && r.restlaufzeit_tage <= vorwarn;
        }).sort(function (a, b) {
            return a.restlaufzeit_tage - b.restlaufzeit_tage;
        });
        return modell({
            kopf: String(rows.length),
            unterzeile: 'Restlaufzeit ≤ ' + vorwarn + ' Tage',
            grundlage: 'nur Fälle mit belegtem Anker (von '
                + zahl(data.faelle_gesamt) + ')',
            vorbehalt: vorbehalt,
            zeilen: rows.slice(0, max).map(function (r) {
                return { text: (r.username || ('Fall ' + r.subject_id)) + ': '
                    + r.restlaufzeit_tage + ' Tage', stufe: r.ampel };
            }),
            gesamt: rows.length,
            leer: rows.length === 0
        });
    }

    // --- 1f) Lastverteilung (/api/workload) ----------------------------------
    function reduceLastverteilung(data, max) {
        if (!data || data.fehler) { return fehlerModell(data && data.fehler); }
        max = max || MAX_ZEILEN;
        var loads = (data.loads || []).filter(function (l) {
            return l.is_backlog !== true;   // Rueckstauzeile ist keine Person
        }).slice().sort(function (a, b) {
            return zahl(b.active_cases) - zahl(a.active_cases);
        });
        var o = data.overload || {};
        return modell({
            kopf: String(zahl(o.overloaded_count)),
            unterzeile: 'überlastet · ' + zahl(o.warned_count)
                + ' gewarnt · Rückstau ' + zahl(o.backlog_size),
            grundlage: 'nach aktiven Fällen absteigend',
            zeilen: loads.slice(0, max).map(function (l) {
                return { text: (l.display_name || EM_DASH) + ': '
                    + zahl(l.active_cases) + ' aktiv' };
            }),
            gesamt: loads.length,
            leer: loads.length === 0
        });
    }

    // --- 1g) Meine Auftraege (/api/mycases) ----------------------------------
    function reduceMeineAuftraege(data, max) {
        if (!data || data.fehler) { return fehlerModell(data && data.fehler); }
        max = max || MAX_ZEILEN;
        var faelle = (data.cases || []).slice().sort(function (a, b) {
            var r = ampelRang(a.ampel) - ampelRang(b.ampel);
            if (r !== 0) { return r; }
            return zahl(a.priority) - zahl(b.priority);
        });
        return modell({
            kopf: String(zahl(data.count)),
            unterzeile: 'eigene Fälle',
            grundlage: faelle.length > max ? 'nach Ampel und Priorität' : '',
            zeilen: faelle.slice(0, max).map(function (c) {
                return { text: (c.username || ('Fall ' + c.subject_id)),
                         stufe: c.ampel };
            }),
            gesamt: faelle.length,
            leer: faelle.length === 0
        });
    }

    // --- 1h) Zustand der Audit-Kette (/api/integrity) ------------------------
    // Schneidet nichts ab und filtert nichts — hier gibt es genau eine
    // Aussage, und die ist entweder ja oder nein.
    function reduceKettenzustand(data) {
        if (!data || data.fehler) { return fehlerModell(data && data.fehler); }
        if (data.ok === true) {
            return modell({
                kopf: 'unversehrt',
                unterzeile: 'Spitze bei seq ' + zahl(data.tip_seq),
                // Build 570: 'tonung' faerbt die GANZE Kachel. Diese Kachel
                // bekommt bewusst kein Diagramm (Ja/Nein-Aussage), aber sie
                // soll ohne Lesen erkennbar sein - das ist der Zweck eines
                // Ueberblicks.
                tonung: 'gruen',
                zeilen: [], gesamt: null, leer: false
            });
        }
        return modell({
            kopf: 'BRUCH', tonung: 'rot',
            unterzeile: 'erster Fehler bei seq '
                + (data.first_bad_seq === null || data.first_bad_seq === undefined
                    ? EM_DASH : data.first_bad_seq),
            zeilen: data.detail ? [{ text: String(data.detail), stufe: 'rot' }]
                : [],
            gesamt: null, leer: false
        });
    }

    //: Zuordnung Kachel -> Reduzierer. Der Schluesselsatz spiegelt
    //  viewpref_katalog.WIDGETS; ein Test haelt beide gegeneinander, damit
    //  eine kuenftige Kachel nicht ohne Reduzierer bleibt (sie waere sonst
    //  dauerhaft leer, ohne Fehlermeldung).
    var REDUZIERER = {
        fallampel: reduceFallampel,
        eskalationen: reduceEskalationen,
        naechste_aktion: reduceNextActions,
        wiedervorlage: reduceWiedervorlage,
        fristen: reduceFristen,
        lastverteilung: reduceLastverteilung,
        meine_auftraege: reduceMeineAuftraege,
        kettenzustand: reduceKettenzustand
    };

    function reduziere(key, daten, max) {
        var f = REDUZIERER[key];
        if (!f) {
            // Kein stiller Ausfall: eine Kachel ohne Reduzierer sagt das.
            return fehlerModell('Für diese Kachel gibt es keine Darstellung ('
                + key + ').');
        }
        return f(daten, max);
    }

    // aktiveKacheln: welche Kacheln erscheinen, in welcher Folge?
    //
    // DER RECHTEFILTER LAEUFT ZULETZT — dieselbe Linie wie bei den Sichten
    // (cockpit.js navViews). 'erlaubt' ist die Auskunft des SERVERS
    // (/api/viewprefs); der Browser leitet sie nicht selbst ab.
    //
    // OHNE GESPEICHERTE VORLIEBE GILT DIE WERKSEINSTELLUNG. Eine leere
    // gespeicherte Liste ist etwas anderes als keine — wer alle Kacheln
    // abwaehlt, bekommt eine leere Flaeche und nicht die Werkseinstellung
    // zurueck. Deshalb wird auf null/undefined geprueft und nicht auf Laenge.
    function aktiveKacheln(prefs, katalog) {
        var k = katalog || {};
        var alle = k.widgets || [];
        var beiKey = {};
        alle.forEach(function (w) { beiKey[w.key] = w; });

        var folge;
        if (prefs === null || prefs === undefined) {
            folge = (k.standard_widgets || []).map(function (key) {
                return { key: key, sichtbar: true };
            });
        } else {
            folge = prefs.filter(function (p) {
                return p && p.sichtbar !== false;
            });
        }
        return folge.map(function (p) { return beiKey[p.key]; })
            .filter(function (w) { return !!w && w.erlaubt === true; });
    }

    // =========================================================================
    // 2) DOM.
    // =========================================================================

    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    /**
     * renderDashboard(mainEl, data, cb)
     *
     * data = { kacheln: [WidgetSpec], modelle: {key: Modell},
     *          katalog: {...}, prefs: [...]|null }
     * cb   = { onSlot(key, bodyEl), onSpeichern(nutzlast) }
     *
     * 'onSlot' ist das STECKPLATZ-VERFAHREN: Kacheln mit 'slot' bekommen einen
     * leeren Rumpf, den die Shell selbst fuellt. So bettet 'fallampel' die
     * ECHTE Tabulator-Uebersicht ein, statt sie nachzubauen — und der
     * Fall-Sprung der Kommandopalette bleibt heil.
     */
    function renderDashboard(mainEl, data, cb) {
        if (!mainEl) { return null; }
        mainEl.textContent = '';
        data = data || {};
        cb = cb || {};
        var kacheln = data.kacheln || [];
        var modelle = data.modelle || {};

        var kopf = el('div', 'aiw-db-kopf');
        // Build 595 (Baustelle H / H7): Hilfe-Marke der Ueberschrift.
        var kopfEl = el('h2', 'aiw-pagehead', 'Überblick');
        kopfEl.setAttribute('data-hilfe-id', 'dashboard.titel');
        kopf.appendChild(kopfEl);
        var btn = el('button', 'aiw-btn', 'Kacheln wählen');
        btn.setAttribute('type', 'button');
        kopf.appendChild(btn);
        mainEl.appendChild(kopf);

        var waehler = el('div', 'aiw-db-waehler');
        waehler.style.display = 'none';
        mainEl.appendChild(waehler);
        btn.addEventListener('click', function () {
            var offen = waehler.style.display !== 'none';
            waehler.style.display = offen ? 'none' : '';
            if (!offen) { zeichneWaehler(); }
        });

        var raster = el('div', 'aiw-db-raster');
        mainEl.appendChild(raster);

        if (!kacheln.length) {
            raster.appendChild(el('p', 'aiw-pagesub',
                'Es ist keine Kachel ausgewählt. Über "Kacheln wählen" '
                + 'lässt sich der Überblick zusammenstellen.'));
        }

        // BUILD 573 - DIAGRAMME ERST EINHAENGEN, WENN ALLES IM DOM STEHT.
        //
        // Der Fehler, den das behebt: cb.onDiagramm() wurde gerufen, WAEHREND
        // die Kachel noch nicht im Dokument hing (raster.appendChild kam erst
        // danach). echarts.init() misst dann Breite und Hoehe NULL, zeichnet
        // eine leere Leinwand und richtet sich nie neu aus. Von aussen sah das
        // aus wie "Diagramme fehlen": die Leinwand war da (Sonde mc: canvas 1,
        // chartH 132), nur eben leer.
        //
        // Deshalb werden die Auftraege gesammelt und NACH der Schleife
        // ausgefuehrt. Zu diesem Zeitpunkt hat jede Kachel eine messbare
        // Groesse. Der Test DB24 prueft genau das - er verlangt, dass das
        // Zielelement beim Aufruf 'isConnected' ist.
        var diagrammAuftraege = [];

        kacheln.forEach(function (w) {
            var m = modelle[w.key] || fehlerModell('Keine Daten geladen.');
            var kachel = el('div', 'aiw-kachel'
                + (w.slot ? ' is-breit' : '')
                + (m.fehler ? ' is-fehler' : '')
                + (m.tonung ? ' ton-' + m.tonung : ''));
            kachel.setAttribute('data-widget-key', w.key);
            // Build 595 (Baustelle H / H7): JEDE Kachel traegt eine eigene
            // Hilfe-Marke. Sie wird aus dem Kachelschluessel gebildet - die
            // Kacheln sind zur Bauzeit nicht bekannt (sie stammen aus der
            // persoenlichen Ansichtseinstellung), eine literale Liste hier
            // waere also eine zweite Wahrheit neben viewpref_katalog.WIDGETS.
            // Der Paritaetstest liest sie deshalb aus dem gerenderten Baum.
            kachel.setAttribute('data-hilfe-id', 'dashboard.kachel.' + w.key);
            kachel.appendChild(el('div', 'aiw-kachel-titel', w.label));

            if (m.fehler) {
                // AUSGEFALLEN IST NICHT LEER. Der Unterschied steht im Text
                // und in der Einfaerbung.
                kachel.appendChild(el('div', 'aiw-kachel-fehler',
                    'Nicht abrufbar: ' + m.fehler));
                raster.appendChild(kachel);
                return;
            }

            if (w.slot) {
                // BUILD 572: DER STECKPLATZ-ZWEIG STIEG VOR DEM DIAGRAMMBLOCK
                // AUS. Die Fall-Uebersicht bekam deshalb NIE ihren Ampelring -
                // sie war nur die eingebettete Tabelle. Der Fehler fiel im
                // Test nicht auf, weil DB18 mit Kacheln OHNE Steckplatz
                // prueft; er fiel erst am lebenden System auf (chartH '—').
                // Jetzt kommt das Diagramm auch hier, und zwar VOR der
                // Tabelle: erst der Eindruck, dann das Detail.
                kachel.appendChild(el('div', 'aiw-kachel-unter',
                    m.kopf + ' Fälle · ' + m.unterzeile));
                var slotOption = (data.diagramme || {})[w.key];
                if (slotOption) {
                    var slotChart = el('div', 'aiw-kachel-chart');
                    slotChart.setAttribute('data-chart-key', w.key);
                    kachel.appendChild(slotChart);
                    diagrammAuftraege.push([w.key, slotChart, slotOption]);
                }
                var rumpf = el('div', 'aiw-kachel-slot');
                kachel.appendChild(rumpf);
                raster.appendChild(kachel);
                if (typeof cb.onSlot === 'function') { cb.onSlot(w.key, rumpf); }
                return;
            }

            kachel.appendChild(el('div', 'aiw-kachel-zahl', m.kopf));
            if (m.unterzeile) {
                kachel.appendChild(el('div', 'aiw-kachel-unter', m.unterzeile));
            }

            // --- DIAGRAMM (Build 570) ---------------------------------------
            // Der Steckplatz entsteht GENAU DANN, wenn es fuer diese Kachel
            // eine Option gibt. Die Entscheidung, welche Kachel eine bekommt,
            // faellt in cockpit_dashboard_charts.optionFuer() - hier wird sie
            // nicht wiederholt, sonst gaebe es zwei Wahrheiten darueber.
            //
            // Die Reihenfolge im Kachelrumpf ist Absicht: Titel, ZAHL, FORM,
            // dann Einzelzeilen. Der Blick soll von der Groessenordnung ueber
            // die Verteilung zum Detail gehen - und beim Detail darf er
            // aufhoeren, ohne etwas zu verpassen.
            var option = (data.diagramme || {})[w.key];
            if (option) {
                var chartHost = el('div', 'aiw-kachel-chart');
                chartHost.setAttribute('data-chart-key', w.key);
                kachel.appendChild(chartHost);
                diagrammAuftraege.push([w.key, chartHost, option]);
            }
            if (m.leer) {
                kachel.appendChild(el('div', 'aiw-kachel-leer',
                    'Es liegt nichts an.'));
            }
            if (m.zeilen.length) {
                var ul = el('ul', 'aiw-kachel-liste');
                m.zeilen.forEach(function (z) {
                    var li = el('li', 'aiw-kachel-zeile'
                        + (z.stufe ? ' stufe-' + z.stufe : ''), z.text);
                    ul.appendChild(li);
                });
                kachel.appendChild(ul);
            }
            // BUILD 573 - EINE FUSSZEILE STATT DREIER ABSAETZE.
            //
            // Grundlage, Reduktionshinweis und Vorbehalt sind PFLICHT: ein
            // Ausschnitt darf nicht wie ein vollstaendiges Bild aussehen, und
            // eine Zahl mit Rechtsfolge nicht ohne ihren Vorbehalt stehen.
            // Als drei Absaetze uebereinander machten sie aus der Kachel aber
            // einen Beipackzettel (Befund mc) - und eine Kachel, die man lesen
            // MUSS, ist keine Kachel.
            //
            // Der Ausweg ist nicht Weglassen, sondern VERDICHTEN: die
            // Kurzformen stehen in einer Zeile, der vollstaendige Wortlaut
            // steht im title-Attribut UND unveraendert in der zugehoerigen
            // Sicht, in der man auf die Zahl hin handelt. Verschwiegen wird
            // nichts - ein Vorbehalt bleibt als Wort sichtbar, auch wenn sein
            // Wortlaut einen Zeigerhalt entfernt liegt.
            var fussTeile = [];
            var fussVoll = [];
            if (m.hinweis) { fussTeile.push(kurzHinweis(m.hinweis)); }
            if (m.grundlage) { fussTeile.push('Auswahl'); }
            if (m.vorbehalt) { fussTeile.push('Vorbehalt'); }
            [m.hinweis, m.grundlage, m.vorbehalt].forEach(function (t) {
                if (t) { fussVoll.push(t); }
            });
            if (fussTeile.length) {
                var fuss = el('div', 'aiw-kachel-fuss'
                    + (m.vorbehalt ? ' hat-vorbehalt' : ''),
                    fussTeile.join(' · '));
                fuss.setAttribute('title', fussVoll.join('\n'));
                kachel.appendChild(fuss);
            }
            raster.appendChild(kachel);
        });

        // JETZT stehen alle Kacheln im Dokument und haben eine messbare
        // Groesse — erst hier duerfen die Diagramme entstehen.
        if (typeof cb.onDiagramm === 'function') {
            diagrammAuftraege.forEach(function (a) {
                cb.onDiagramm(a[0], a[1], a[2]);
            });
        }

        // --- Kachelwaehler ---------------------------------------------------
        // Bewusst SCHLICHT: Auswahl per Haken, Reihenfolge per Pfeil. Im
        // Dashboard ist die Person frei (Abstimmung mc 2026-07-26) — hier gibt
        // es deshalb KEINE Zaehler und KEINE Warnhinweise wie bei den
        // Navigationssichten.
        function zeichneWaehler() {
            waehler.textContent = '';
            var kat = data.katalog || {};
            var erlaubte = (kat.widgets || []).filter(function (w) {
                return w.erlaubt === true;
            });
            var aktiv = kacheln.map(function (w) { return w.key; });
            var stand = aktiv.slice();
            erlaubte.forEach(function (w) {
                if (stand.indexOf(w.key) === -1) { stand.push(w.key); }
            });

            waehler.appendChild(el('p', 'aiw-pagesub',
                'Kacheln aus- und abwählen, Reihenfolge mit den Pfeilen. '
                + 'Es erscheinen nur Kacheln, für die Sie berechtigt sind.'));
            var liste = el('div', 'aiw-db-wliste');
            waehler.appendChild(liste);

            function zeichneListe() {
                liste.textContent = '';
                stand.forEach(function (key, idx) {
                    var w = null;
                    erlaubte.forEach(function (x) { if (x.key === key) { w = x; } });
                    if (!w) { return; }
                    var zeile = el('div', 'aiw-db-wzeile');
                    var box = document.createElement('input');
                    box.type = 'checkbox';
                    box.checked = aktiv.indexOf(key) !== -1;
                    box.id = 'aiw-db-cb-' + key;
                    // Build 637 (Vorgang 17200856): Hilfe-Marke, LITERAL.
                    box.setAttribute('data-hilfe-id',
                        'dashboard.bedienung.kachelwahl');
                    box.addEventListener('change', function () {
                        var i = aktiv.indexOf(key);
                        if (box.checked && i === -1) { aktiv.push(key); }
                        if (!box.checked && i !== -1) { aktiv.splice(i, 1); }
                    });
                    zeile.appendChild(box);
                    var lab = el('label', 'aiw-db-wlabel', w.label);
                    lab.setAttribute('for', box.id);
                    zeile.appendChild(lab);
                    zeile.appendChild(el('span', 'aiw-db-wbeschr',
                                         w.beschreibung || ''));
                    var up = el('button', 'aiw-vp-pfeil', '▲');
                    up.setAttribute('type', 'button');
                    up.setAttribute('aria-label', 'Nach oben');
                    up.disabled = (idx === 0);
                    up.addEventListener('click', function () {
                        var t = stand[idx - 1];
                        stand[idx - 1] = stand[idx];
                        stand[idx] = t;
                        zeichneListe();
                    });
                    var down = el('button', 'aiw-vp-pfeil', '▼');
                    down.setAttribute('type', 'button');
                    down.setAttribute('aria-label', 'Nach unten');
                    down.disabled = (idx === stand.length - 1);
                    down.addEventListener('click', function () {
                        var t = stand[idx + 1];
                        stand[idx + 1] = stand[idx];
                        stand[idx] = t;
                        zeichneListe();
                    });
                    zeile.appendChild(up);
                    zeile.appendChild(down);
                    liste.appendChild(zeile);
                });
            }
            zeichneListe();

            var speichern = el('button', 'aiw-btn aiw-btn-primary',
                               'Anordnung speichern');
            speichern.setAttribute('type', 'button');
            speichern.addEventListener('click', function () {
                if (typeof cb.onSpeichern !== 'function') { return; }
                cb.onSpeichern(stand.map(function (key) {
                    return { key: key, sichtbar: aktiv.indexOf(key) !== -1 };
                }));
            });
            waehler.appendChild(speichern);
        }

        log('gerendert:', kacheln.length, 'Kacheln');
        return { kacheln: kacheln.map(function (w) { return w.key; }) };
    }

    // =========================================================================
    // 3) UMD-artiger Ausgang.
    // =========================================================================
    var API = {
        MAX_ZEILEN: MAX_ZEILEN,
        REDUZIERER: REDUZIERER,
        ampelRang: ampelRang,
        hinweisReduktion: hinweisReduktion,
        kurzHinweis: kurzHinweis,
        fehlerModell: fehlerModell,
        reduziere: reduziere,
        reduceFallampel: reduceFallampel,
        reduceEskalationen: reduceEskalationen,
        reduceNextActions: reduceNextActions,
        reduceWiedervorlage: reduceWiedervorlage,
        reduceFristen: reduceFristen,
        reduceLastverteilung: reduceLastverteilung,
        reduceMeineAuftraege: reduceMeineAuftraege,
        reduceKettenzustand: reduceKettenzustand,
        aktiveKacheln: aktiveKacheln,
        renderDashboard: renderDashboard
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitDashboard = API; }
})();
