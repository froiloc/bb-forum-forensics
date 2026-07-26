// =============================================================================
// management/server/static/cockpit_tablekit.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit (Build 534)
// =============================================================================
// Zweck:
//   DAS GEMEINSAME TABELLEN-WERKZEUG des Cockpits. Es haelt an EINER Stelle,
//   was jede Listensicht braucht:
//     * Kopffilter je Spalte (Auswahlliste mit Mehrfachauswahl, wo es wenige
//       verschiedene Werte gibt; Freitext sonst),
//     * eine Spaltenwahl fuer die Kennzahlen aus uid_stats,
//     * eine Schaltflaeche, die ALLE Filter entfernt,
//     * die Sicherung von Sortierung, Filtern und Spaltenwahl im Browser.
//
// WARUM GEMEINSAM UND NICHT JE SICHT (mc 2026-07-26):
//   "UX bedeutet intuitive Bedienung. Einmal Erlerntes soll immer wieder
//   verwendet werden." Zwei Sichten, die dasselbe TUN, sollen es nicht nur
//   AEHNLICH tun. Zwei Nachbauten desselben Filterkopfes waeren zwei
//   Verhaltensweisen, die auseinanderlaufen, sobald eine davon einmal
//   nachgebessert wird — und der Anwender muesste den Unterschied auswendig
//   lernen. Hier gibt es nur ein Verhalten; jede kuenftige Sicht erbt es.
//
// DIE SCHWELLE 10 IST EINE ENTSCHEIDUNG, KEINE NATURKONSTANTE (mc 2026-07-26:
//   "Fuer Spalten, in denen weniger als 10 einzigartige Eintraege existieren
//   [...] soll es einen Drop-Down-Filter geben"). Sie steht als Konstante
//   SCHWELLE_AUSWAHL und wird AUS DEN DATEN heraus angewandt, nicht je Spalte
//   von Hand gesetzt: eine Spalte 'Ermittler' hat heute 6 verschiedene Werte
//   und naechstes Jahr 14. Eine handverdrahtete Entscheidung waere dann still
//   falsch; diese passt sich an und ist nachrechenbar.
//
// MEHRFACHAUSWAHL MIT EIGENER FILTERFUNKTION (bewusst):
//   Tabulator kann Mehrfachauswahl, aber welche Vergleichsregel dabei gilt,
//   haengt an Bibliotheks-Voreinstellungen. In einem forensischen Werkzeug
//   soll die Regel IM CODE stehen und pruefbar sein: 'mehrfachFilter' ist
//   sieben Zeilen lang, hat einen eigenen Test und sagt ausdruecklich, dass
//   eine LEERE Auswahl NICHT filtert (sonst verschwaende die ganze Liste,
//   sobald jemand das letzte Haekchen entfernt).
//   Dasselbe Muster wie die Auswahlspalte in cockpit_cases.js (Build 384).
//
// KEINE WERTE ERFINDEN — '—' STATT '0':
//   Die Kennzahlen stammen aus den forensic_<uid>.db. Fehlt eine Datei oder
//   ist sie unlesbar, liefert der Server KEINE Werte und einen benannten
//   Befund (management/stats/uid_stats_repo.py). 'statZelle' macht daraus ein
//   '—' mit dem Grund als Tooltip — NIE eine 0. Eine 0 saehe aus wie eine
//   Feststellung und waere das Gegenteil davon (Grundregel 1).
//
// localStorage: NUR Bedienzustand (Sortierung, Filter, sichtbare Spalten),
//   NIE Ermittlungsdaten. Der Schluessel traegt eine Formatnummer, damit ein
//   spaeteres Format alte Staende gezielt verwerfen kann statt an ihnen zu
//   scheitern (Muster cockpit_doctemplates.js, Build 487). Der Zugriff ist
//   gekapselt: faellt localStorage aus (Privat-Modus, Quota), arbeitet die
//   Sicht ohne Sicherung weiter, statt abzustuerzen.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG).
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen getrennt vom DOM, damit
//   vitest den ECHTEN Code prueft.
//
// XSS: ausschliesslich textContent / Option.text (kein innerHTML).
//
// BUILD 548 — ANKER FUER DIE SPAETERE SCHNELLHILFE (mc 2026-07-26):
//   Jedes Bedienelement, das dieses Werkzeug erzeugt, bekommt ein stabiles
//   'data-hilfe-id'. Die Schnellhilfe (Overlay-Modus, in dem umrandete
//   Elemente anklickbar werden) gibt es noch NICHT — die Anker entstehen
//   trotzdem jetzt, weil sie beim Umbau der Tabellen fast nichts kosten und
//   spaeter 22 Sichten ein ZWEITES Mal anzufassen waeren.
//
//   DIE ANKER SIND EIN VERSPRECHEN, KEINE DEKORATION. Eine Kennung, die sich
//   spaeter aendert, macht einen Hilfetext stumm — deshalb: Muster erzwungen
//   (HILFE_MUSTER), Eindeutigkeit im Test geprueft, und wer die Werkzeugleiste
//   dieses Moduls benutzt, bekommt die Anker automatisch. Genau das ist der
//   Gewinn des gemeinsamen Werkzeugs: EINE Stelle vergibt sie fuer alle.
//
//   MUSTER: '<sicht>.<bereich>.<name>', Kleinbuchstaben, Punkte als Trenner.
//   Beispiele: 'personnel.werkzeug.filter_entfernen', 'personnel.spalte.rollen'.
//
// Version: v0.8.548 · Build: 548 · 2026-07-26 (Hilfe-Anker)
//   Build 534: Erstfassung (Kopffilter, Spaltenwahl, Zustandssicherung).
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
        args.unshift('[AIW-Tabelle]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // Ab so vielen VERSCHIEDENEN Werten wird aus der Auswahlliste ein
    // Freitextfeld (siehe Kopfkommentar). '<10' heisst: 9 Werte -> Liste.
    var SCHWELLE_AUSWAHL = 10;

    // Anzeigetext fuer 'kein Wert' — an EINER Stelle, damit Filterliste und
    // Zelle nie auseinanderlaufen.
    var LEER_TEXT = '(leer)';

    // Anzeigetext fuer 'nicht gelesen'. Bewusst NICHT '0' (siehe Kopf).
    var UNBEKANNT_TEXT = '—';       // Geviertstrich

    // Formatnummer des gesicherten Bedienzustands.
    var ZUSTAND_FORMAT = 1;

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM, kein Netz) — vitest prueft sie einzeln.
    // =========================================================================

    // _text: einheitliche Textfassung eines Zellwerts. null/undefined/'' sind
    // DASSELBE (leer) — sonst hiesse ein Filtereintrag '(leer)' und ein
    // anderer '' und der Anwender saehe zwei Zeilen fuer denselben Zustand.
    function _text(v) {
        if (v === null || v === undefined) { return ''; }
        return String(v);
    }

    // eindeutigeWerte: die verschiedenen Werte einer Spalte, sortiert.
    // Zahlen werden numerisch sortiert, alles andere nach Sprachregeln
    // (localeCompare) — sonst stuende '10' vor '2', und ein Filter, dessen
    // Reihenfolge niemand versteht, wird nicht benutzt.
    function eindeutigeWerte(rows, field) {
        var gesehen = {};
        var werte = [];
        (rows || []).forEach(function (r) {
            var t = _text(r ? r[field] : '');
            if (!Object.prototype.hasOwnProperty.call(gesehen, t)) {
                gesehen[t] = true;
                werte.push(t);
            }
        });
        var nurZahlen = werte.every(function (t) {
            return t !== '' && !isNaN(Number(t));
        });
        if (nurZahlen) {
            werte.sort(function (a, b) { return Number(a) - Number(b); });
        } else {
            werte.sort(function (a, b) { return a.localeCompare(b, 'de'); });
        }
        return werte;
    }

    // filterArt: 'auswahl' (Mehrfachauswahl) oder 'text' (Freitext).
    // Entscheidet AUS DEN DATEN (siehe Kopfkommentar zur Schwelle).
    function filterArt(rows, field) {
        return eindeutigeWerte(rows, field).length < SCHWELLE_AUSWAHL
            ? 'auswahl' : 'text';
    }

    // mehrfachFilter: die Vergleichsregel der Mehrfachauswahl.
    //   LEERE Auswahl -> KEIN Filter (alles bleibt sichtbar). Das ist die
    //   wichtigste Zeile: die andere Auslegung ("nichts ausgewaehlt = nichts
    //   anzeigen") wuerde die Liste leeren, sobald jemand das letzte Haekchen
    //   entfernt, und wie ein Datenverlust aussehen.
    function mehrfachFilter(headerValue, rowValue) {
        if (headerValue === null || headerValue === undefined) { return true; }
        if (!Array.isArray(headerValue)) {
            // Einzelwert (die Liste kann auch ohne Mehrfachauswahl laufen).
            return headerValue === '' || _text(rowValue) === _text(headerValue);
        }
        if (headerValue.length === 0) { return true; }
        return headerValue.indexOf(_text(rowValue)) !== -1;
    }

    // filterFuer: der Filter-Teil einer Spaltendefinition. Wird ueber die
    // fertige Spalte gelegt (Object.assign-artig), damit der Aufrufer Titel,
    // Breite und Formatter behaelt.
    //   opts.erzwingeText — Spalte immer als Freitext (z. B. Benutzername:
    //     dort ist die Auswahlliste auch bei wenigen Zeilen sinnlos, weil man
    //     nach Namensteilen sucht).
    function filterFuer(rows, field, opts) {
        opts = opts || {};
        if (opts.erzwingeText || filterArt(rows, field) === 'text') {
            return {
                headerFilter: 'input',
                headerFilterPlaceholder: 'suchen …',
                headerFilterLiveFilter: true
            };
        }
        var werte = eindeutigeWerte(rows, field).map(function (w) {
            return { value: w, label: (w === '' ? LEER_TEXT : w) };
        });
        return {
            headerFilter: 'list',
            headerFilterParams: {
                values: werte,
                multiselect: true,
                clearable: true,
                autocomplete: false,
                sort: 'none'          // die Reihenfolge steht schon fest
            },
            headerFilterFunc: mehrfachFilter,
            headerFilterLiveFilter: true
        };
    }

    // spaltenMitFilter: legt ueber JEDE Spalte einer Definition den passenden
    // Filter. Spalten mit 'kein_filter: true' bleiben ausgenommen (die
    // Auswahlspalte der Fall-Erkennung z. B. — ein Filter auf Kaestchen waere
    // sinnlos). Die Eingabe wird NICHT veraendert (neue Objekte).
    function spaltenMitFilter(rows, columns) {
        return (columns || []).map(function (c) {
            var neu = {};
            Object.keys(c).forEach(function (k) { neu[k] = c[k]; });
            if (c.kein_filter || !c.field) {
                delete neu.kein_filter;
                return neu;
            }
            var f = filterFuer(rows, c.field,
                               { erzwingeText: !!c.filter_text });
            Object.keys(f).forEach(function (k) {
                // Eine ausdrueckliche Angabe der Sicht schlaegt die Automatik.
                if (neu[k] === undefined) { neu[k] = f[k]; }
            });
            delete neu.kein_filter;
            delete neu.filter_text;
            return neu;
        });
    }

    // ------------------------------------------------------- uid_stats-Teil

    // statZelle: was in einer Kennzahl-Zelle steht.
    //   -> { wert, text, titel }
    //   'wert' ist die ZAHL (oder null) und dient dem Sortieren; 'text' ist,
    //   was man sieht. Beides getrennt, weil '—' sich nicht sortieren laesst
    //   und eine 0 an seiner Stelle falsch waere.
    //   Eine Abweichung zwischen der vom Forum gemeldeten und der aus den
    //   gesicherten Daten gezaehlten Zahl wird MARKIERT (Stern) und im Titel
    //   erklaert — sie ist selbst ein Befund (geloeschte Beitraege,
    //   unvollstaendige Sicherung) und darf nicht unter den Tisch fallen.
    function statZelle(stats, subjectId, key) {
        var eintrag = (stats || {})[String(subjectId)];
        if (!eintrag) {
            return { wert: null, text: UNBEKANNT_TEXT,
                     titel: 'Keine Kennzahlen abgerufen.' };
        }
        var w = (eintrag.werte || {})[key];
        if (!w) {
            return {
                wert: null, text: UNBEKANNT_TEXT,
                titel: 'Nicht gelesen (' + (eintrag.befund || 'unbekannt')
                       + '). Das ist NICHT dasselbe wie 0.'
            };
        }
        var c = (w.c === undefined) ? null : w.c;
        var r = (w.r === undefined) ? null : w.r;
        if (c === null && r === null) {
            return { wert: null, text: UNBEKANNT_TEXT,
                     titel: 'Kennzahl vorhanden, aber ohne Wert.' };
        }
        if (c === null) {
            return {
                wert: r, text: String(r) + '°',
                titel: 'Nur die vom Forum GEMELDETE Zahl liegt vor (' + r
                       + '); aus den gesicherten Daten wurde nichts gezaehlt.'
            };
        }
        var titel = 'Aus den gesicherten Daten gezaehlt: ' + c;
        var text = String(c);
        if (r !== null && r !== c) {
            titel += '. Vom Forum gemeldet: ' + r
                   + ' (Abweichung ' + (w.d === null || w.d === undefined
                        ? (r - c) : w.d) + ').';
            text += '*';
        } else if (r !== null) {
            titel += '. Vom Forum gemeldet: ' + r + ' (keine Abweichung).';
        }
        return { wert: c, text: text, titel: titel };
    }

    // statSpalten: Spaltendefinitionen fuer die GEWAEHLTEN Kennzahlen.
    //   'katalog' ist die Antwort des Servers ([{key, faelle}]) und bestimmt,
    //   WAS waehlbar ist; 'gewaehlt' bestimmt, was davon sichtbar ist.
    //   Unbekannte Schluessel in 'gewaehlt' werden UEBERGANGEN — aber der
    //   Aufrufer bekommt sie zurueck (zweiter Rueckgabewert), damit er es
    //   melden kann statt still zu schlucken (ein alter localStorage-Stand
    //   kann Schluessel enthalten, die es nicht mehr gibt).
    function statSpalten(katalog, gewaehlt, stats) {
        var bekannt = {};
        (katalog || []).forEach(function (e) { bekannt[e.key] = true; });
        var spalten = [];
        var unbekannt = [];
        (gewaehlt || []).forEach(function (key) {
            if (!bekannt[key]) { unbekannt.push(key); return; }
            spalten.push({
                title: key,                  // technische Bezeichnung (mc)
                field: 'stat_' + key,
                width: 110,
                hozAlign: 'right',
                sorter: 'number',
                // Die Zelle baut sich aus statZelle — inkl. Tooltip. Eigener
                // Formatter statt Standardausgabe, damit '—' und '*' ihre
                // Erklaerung mitbringen.
                formatter: function (cell) {
                    var d = cell.getData();
                    var z = statZelle(stats, d.subject_id, key);
                    var el = cell.getElement();
                    if (el) { el.title = z.titel; }
                    return z.text;
                }
            });
        });
        return { spalten: spalten, unbekannt: unbekannt };
    }

    // statFelder: haengt die Kennzahlen als 'stat_<key>' AN DIE ZEILEN.
    //   Warum ueberhaupt: Tabulator sortiert und filtert ueber Felder der
    //   Zeile, nicht ueber den Formatter. Ohne diesen Schritt waere die
    //   Spalte sichtbar, aber nicht sortierbar — und das faellt erst auf,
    //   wenn jemand darauf klickt und nichts passiert.
    //   Der Wert ist die ZAHL (oder null), nicht der Anzeigetext.
    function statFelder(rows, stats, keys) {
        return (rows || []).map(function (r) {
            var neu = {};
            Object.keys(r).forEach(function (k) { neu[k] = r[k]; });
            (keys || []).forEach(function (key) {
                neu['stat_' + key] = statZelle(stats, r.subject_id, key).wert;
            });
            return neu;
        });
    }

    // ------------------------------------------------- Bedienzustand sichern

    function schluessel(sichtId) {
        return 'aiw.tabelle.' + sichtId + '.v' + ZUSTAND_FORMAT;
    }

    // _ls: sicherer Zugriff auf localStorage. In Privat-Modus/Sandbox/bei
    // Quota kann der Zugriff werfen -> dann null (Sicherung still aus, aber
    // die Sicht laeuft; Muster cockpit_doctemplates.js Build 487).
    function _ls() {
        try {
            return (typeof localStorage !== 'undefined') ? localStorage : null;
        } catch (e) { return null; }
    }

    // zustandLesen: gesicherter Bedienzustand oder null.
    //   Ein unlesbarer oder fremdformatiger Stand wird VERWORFEN, nicht
    //   repariert: ein halb verstandener Zustand waere schlimmer als keiner.
    function zustandLesen(sichtId) {
        var ls = _ls();
        if (!ls) { return null; }
        var roh;
        try { roh = ls.getItem(schluessel(sichtId)); } catch (e) { return null; }
        if (!roh) { return null; }
        try {
            var z = JSON.parse(roh);
            if (!z || z.v !== ZUSTAND_FORMAT) { return null; }
            return z;
        } catch (e) {
            log('Gesicherter Zustand unlesbar, wird verworfen:', sichtId);
            return null;
        }
    }

    function zustandSchreiben(sichtId, zustand) {
        var ls = _ls();
        if (!ls) { return false; }
        var z = {
            v: ZUSTAND_FORMAT,
            sort: (zustand && zustand.sort) || [],
            filter: (zustand && zustand.filter) || [],
            spalten: (zustand && zustand.spalten) || []
        };
        try {
            ls.setItem(schluessel(sichtId), JSON.stringify(z));
            return true;
        } catch (e) {
            log('Zustand konnte nicht gesichert werden:', e);
            return false;
        }
    }

    function zustandLoeschen(sichtId) {
        var ls = _ls();
        if (!ls) { return false; }
        try { ls.removeItem(schluessel(sichtId)); return true; }
        catch (e) { return false; }
    }

    // zustandAusTabelle: liest Sortierung und Filter AUS der Tabelle.
    // Defensiv: eine Tabelle ohne diese Methoden (Test-Attrappe) liefert
    // leere Listen statt eines Absturzes.
    function zustandAusTabelle(table, spalten) {
        var sort = [];
        var filter = [];
        try {
            (table.getSorters ? table.getSorters() : []).forEach(function (s) {
                var feld = s.field || (s.column && s.column.getField
                    ? s.column.getField() : null);
                if (feld) { sort.push({ column: feld, dir: s.dir || 'asc' }); }
            });
        } catch (e) { log('getSorters fehlgeschlagen:', e); }
        try {
            (table.getHeaderFilters ? table.getHeaderFilters() : [])
                .forEach(function (f) {
                    filter.push({ field: f.field, value: f.value });
                });
        } catch (e) { log('getHeaderFilters fehlgeschlagen:', e); }
        return { sort: sort, filter: filter, spalten: (spalten || []).slice() };
    }

    // zustandAnwenden: legt einen gesicherten Zustand auf die Tabelle.
    //   Felder, die es nicht (mehr) gibt, werden UEBERGANGEN und
    //   zurueckgemeldet — nicht still geschluckt. Rueckgabe: die Liste der
    //   uebergangenen Felder.
    function zustandAnwenden(table, zustand, vorhandeneFelder) {
        var uebergangen = [];
        if (!table || !zustand) { return uebergangen; }
        var kennt = {};
        (vorhandeneFelder || []).forEach(function (f) { kennt[f] = true; });

        (zustand.filter || []).forEach(function (f) {
            if (!kennt[f.field]) { uebergangen.push(f.field); return; }
            try { table.setHeaderFilterValue(f.field, f.value); }
            catch (e) { log('Filter nicht setzbar:', f.field, e); }
        });
        var sort = (zustand.sort || []).filter(function (s) {
            if (kennt[s.column]) { return true; }
            uebergangen.push(s.column);
            return false;
        });
        if (sort.length) {
            try { table.setSort(sort); }
            catch (e) { log('Sortierung nicht setzbar:', e); }
        }
        return uebergangen;
    }

    // =========================================================================
    // 2) DOM — Bedienleiste, Spaltenwahl.
    // =========================================================================

    function _btn(doc, id, text, onClick, titel) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.id = id;
        b.className = 'aiw-btn aiw-tk-btn';
        b.textContent = text;
        if (titel) { b.title = titel; }
        b.addEventListener('click', onClick);
        return b;
    }

    // spaltenwahl: das Klappfeld mit den waehlbaren Kennzahlen.
    //   Die Beschriftung ist die TECHNISCHE Bezeichnung aus uid_stats — so
    //   ausdruecklich gewuenscht (mc 2026-07-26). Die Zahl dahinter sagt, in
    //   wie vielen Faellen die Kennzahl ueberhaupt vorliegt: eine Spalte, die
    //   nur bei 2 von 163 Faellen gefuellt ist, soll man vorher erkennen.
    //   Rueckgabe: { el, setKatalog }
    function spaltenwahl(doc, opts) {
        opts = opts || {};
        var gewaehlt = (opts.gewaehlt || []).slice();
        var katalog = opts.katalog || [];

        var huelle = doc.createElement('div');
        huelle.className = 'aiw-tk-spaltenwahl';

        var knopf = _btn(doc, opts.id || 'aiw-tk-spalten', 'Spalten ▾',
            function () {
                var offen = feld.classList.toggle('offen');
                knopf.setAttribute('aria-expanded', offen ? 'true' : 'false');
            }, 'Zusaetzliche Kennzahl-Spalten aus uid_stats ein- und ausblenden');
        knopf.setAttribute('aria-expanded', 'false');
        huelle.appendChild(knopf);

        var feld = doc.createElement('div');
        feld.className = 'aiw-tk-spaltenfeld';
        huelle.appendChild(feld);

        function melde() {
            knopf.textContent = 'Spalten ▾'
                + (gewaehlt.length ? ' (' + gewaehlt.length + ')' : '');
            if (typeof opts.onChange === 'function') {
                opts.onChange(gewaehlt.slice());
            }
        }

        function bauen() {
            feld.textContent = '';
            if (!katalog.length) {
                var leer = doc.createElement('div');
                leer.className = 'aiw-tk-hinweis';
                leer.textContent = 'Keine Kennzahlen verfuegbar. '
                    + '(Die forensic-Datenbanken wurden noch nicht gelesen '
                    + 'oder enthalten keine uid_stats.)';
                feld.appendChild(leer);
                return;
            }
            katalog.forEach(function (e) {
                var zeile = doc.createElement('label');
                zeile.className = 'aiw-tk-spaltenzeile';

                var box = doc.createElement('input');
                box.type = 'checkbox';
                box.checked = gewaehlt.indexOf(e.key) !== -1;
                box.setAttribute('data-stat-key', e.key);
                box.addEventListener('change', function () {
                    var i = gewaehlt.indexOf(e.key);
                    if (box.checked && i === -1) { gewaehlt.push(e.key); }
                    if (!box.checked && i !== -1) { gewaehlt.splice(i, 1); }
                    melde();
                });
                zeile.appendChild(box);

                var name = doc.createElement('span');
                name.className = 'aiw-tk-spaltenname';
                name.textContent = e.key;
                zeile.appendChild(name);

                var zahl = doc.createElement('span');
                zahl.className = 'aiw-tk-spaltenzahl';
                zahl.textContent = '(' + e.faelle + ')';
                zahl.title = 'In so vielen Faellen liegt diese Kennzahl vor.';
                zeile.appendChild(zahl);

                feld.appendChild(zeile);
            });
        }

        bauen();
        melde();

        return {
            el: huelle,
            setKatalog: function (neu) {
                katalog = neu || [];
                // Ein gewaehlter Schluessel, den es nicht mehr gibt, wird
                // entfernt — aber im Protokoll benannt.
                var bekannt = {};
                katalog.forEach(function (e) { bekannt[e.key] = true; });
                var weg = gewaehlt.filter(function (k) { return !bekannt[k]; });
                if (weg.length) {
                    log('Gewaehlte Kennzahlen nicht mehr vorhanden:', weg);
                    gewaehlt = gewaehlt.filter(function (k) {
                        return bekannt[k];
                    });
                }
                bauen();
                melde();
            },
            getGewaehlt: function () { return gewaehlt.slice(); }
        };
    }

    // =========================================================================
    // Build 548: ANKER FUER DIE SCHNELLHILFE.
    // =========================================================================

    //: Zulaessige Form einer Hilfe-Kennung: '<sicht>.<bereich>.<name>', also
    //  mindestens zwei Punkte-Abschnitte, Kleinbuchstaben/Ziffern/Unterstrich.
    var HILFE_MUSTER = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/;

    // hilfeGueltig: reine Pruefung (vitest).
    function hilfeGueltig(id) {
        return typeof id === 'string' && HILFE_MUSTER.test(id);
    }

    // hilfeAnker: haengt die Kennung an ein Element und gibt es zurueck.
    //
    // EINE UNGUELTIGE KENNUNG WIRD NICHT GESETZT, sondern gemeldet. Ein
    // stillschweigend falsch geschriebener Anker waere schlimmer als gar
    // keiner: die Schnellhilfe umrandete das Element spaeter, faende aber
    // keinen Text — und der Anwender klickte ins Leere. Lieber gar kein
    // Rahmen als ein Rahmen ohne Inhalt.
    function hilfeAnker(el, id) {
        if (!el) { return el; }
        if (!hilfeGueltig(id)) {
            // eslint-disable-next-line no-console
            if (typeof console !== 'undefined' && console.warn) {
                console.warn('[AIW-Tabelle] Hilfe-Kennung verworfen (Muster '
                    + '<sicht>.<bereich>.<name>): ' + id);
            }
            return el;
        }
        el.setAttribute('data-hilfe-id', id);
        return el;
    }

    // hilfeIds: alle Anker unterhalb eines Knotens, in Dokumentreihenfolge.
    // Dient der spaeteren Schnellhilfe UND den Tests (Eindeutigkeit).
    function hilfeIds(root) {
        if (!root || typeof root.querySelectorAll !== 'function') { return []; }
        var raus = [];
        var knoten = root.querySelectorAll('[data-hilfe-id]');
        for (var i = 0; i < knoten.length; i++) {
            raus.push(knoten[i].getAttribute('data-hilfe-id'));
        }
        return raus;
    }

    // titelMitHilfe: ein Spaltenkopf, der einen Hilfe-Anker traegt.
    //
    // Rueckgabe ist eine Funktion fuer Tabulators 'titleFormatter' — die
    // einzige Stelle, an der sich an einen von der Bibliothek gebauten
    // Spaltenkopf ein eigenes Attribut haengen laesst. Spaltenkoepfe sind das
    // ERSTE, was eine Schnellhilfe erklaeren muss ("was steht in dieser
    // Spalte?"), deshalb bekommen sie Anker und nicht nur die Knoepfe.
    //
    // 'titel' wird via textContent gesetzt (XSS), 'erklaerung' landet als
    // title-Attribut — das ist die SOFORT wirksame Kurzhilfe, auch ohne
    // Schnellhilfe-Modus.
    function titelMitHilfe(doc, titel, hilfeId, erklaerung) {
        return function () {
            var sp = doc.createElement('span');
            sp.className = 'aiw-tk-titel';
            sp.textContent = titel;
            if (erklaerung) { sp.title = erklaerung; }
            return hilfeAnker(sp, hilfeId);
        };
    }

    // werkzeugleiste: die gemeinsame Leiste ueber jeder Listentabelle.
    //   Aufbau (von links): eigene Bedienelemente der Sicht — Spaltenwahl —
    //   'Filter zurueckesetzen' — Trefferanzeige.
    //   Rueckgabe: { el, setTreffer, spaltenwahl }
    function werkzeugleiste(doc, opts) {
        opts = opts || {};
        var leiste = doc.createElement('div');
        leiste.className = 'aiw-tk-leiste';
        if (opts.id) { leiste.id = opts.id; }

        (opts.eigene || []).forEach(function (el) {
            if (el) { leiste.appendChild(el); }
        });

        // Build 548: 'sicht' ist die Kennung der Sicht fuer die Hilfe-Anker
        // (z. B. 'personnel'). Fehlt sie, bleiben die Anker WEG statt falsch
        // zu heissen — ein Anker 'undefined.werkzeug.…' waere ein toter Link.
        var sicht = opts.sicht || null;
        function anker(el, teil) {
            return sicht ? hilfeAnker(el, sicht + '.werkzeug.' + teil) : el;
        }

        var wahl = null;
        if (opts.spaltenwahl) {
            wahl = spaltenwahl(doc, opts.spaltenwahl);
            anker(wahl.el, 'spaltenwahl');
            leiste.appendChild(wahl.el);
        }

        leiste.appendChild(anker(_btn(doc, (opts.id || 'aiw-tk') + '-clear',
            'Filter zurücksetzen',
            function () {
                if (typeof opts.onFilterLoeschen === 'function') {
                    opts.onFilterLoeschen();
                }
            },
            'Entfernt ALLE Spaltenfilter dieser Sicht.'), 'filter_entfernen'));

        var treffer = doc.createElement('span');
        treffer.className = 'aiw-tk-treffer';
        treffer.id = (opts.id || 'aiw-tk') + '-treffer';
        anker(treffer, 'trefferzahl');
        leiste.appendChild(treffer);

        return {
            el: leiste,
            spaltenwahl: wahl,
            // setTreffer: 'sichtbar von gesamt'. Die Zahl steht bewusst
            // NEBEN der Leiste und nicht nur ueber der Tabelle: nach einem
            // Filterwechsel ist 'wie viele sehe ich gerade' die erste Frage.
            setTreffer: function (sichtbar, gesamt) {
                if (sichtbar === gesamt) {
                    treffer.textContent = gesamt + ' Zeilen';
                    treffer.classList.remove('gefiltert');
                } else {
                    treffer.textContent = sichtbar + ' von ' + gesamt
                        + ' Zeilen (gefiltert)';
                    treffer.classList.add('gefiltert');
                }
            }
        };
    }

    // =========================================================================
    // Build 549: tabelleAufbauen — DIE GANZE VERDRAHTUNG AN EINER STELLE.
    // =========================================================================
    //
    // WARUM DAS HIERHER GEHOERT: die Schritte 'Werkzeugleiste bauen, Filter an
    // die Spalten haengen, Tabelle erzeugen, Trefferzahl fuehren,
    // Bedienzustand sichern und wiederherstellen' sind in JEDER Listensicht
    // dieselben. Beim Ausrollen auf 21 Sichten waeren daraus 21 Beinahe-Kopien
    // geworden — und die erste, die nachgebessert wird, laesst die uebrigen
    // zwanzig zurueck. Genau davor warnt der Kopf dieses Moduls ("zwei
    // Sichten, die dasselbe TUN, sollen es nicht nur AEHNLICH tun").
    //
    // Die Sicht liefert nur noch, was sie WIRKLICH unterscheidet: ihre
    // Kennung, ihre Zeilen, ihre Spalten und ihre eigenen Tabulator-Optionen.
    //
    // opts:
    //   sicht        — Kennung ('mycases'). Praefix der Hilfe-Anker UND
    //                  Schluessel der Zustandssicherung. PFLICHT.
    //   id           — Praefix der DOM-Kennungen (Vorgabe: 'aiw-' + sicht).
    //   rows         — die Zeilen (Array).
    //   columns      — Spalten OHNE Filter; die haengt diese Funktion an.
    //   Ctor         — Tabulator-Konstruktor (injizierbar fuer Tests).
    //   tabulator    — weitere Tabulator-Optionen (index, height,
    //                  rowFormatter, placeholder ...). Sie werden
    //                  DURCHGEREICHT und haben Vorrang, damit eine Sicht ihre
    //                  Besonderheiten behaelt (z. B. index:'subject_id' fuer
    //                  den Fallsprung der Kommandopalette).
    //   eigene       — eigene Bedienelemente fuer die Leiste (Array von DOM).
    //   spaltenwahl  — optional, s. spaltenwahl().
    //   ohneZustand  — true: nicht sichern/wiederherstellen (z. B. wenn die
    //                  Sicht ihre Zeilen bei jedem Aufruf neu zusammenstellt).
    //   einheit      — Substantiv der Zeilen ('Anwender', 'Fälle', ...) fuer
    //                  die Ersatzmeldung. Rueckfall: 'Datensätze'.
    //   onRowClick   — Handler(e, row) fuer den Zeilenklick. NICHT ueber
    //                  'tabulator.rowClick' setzen: das ist in Tabulator v6
    //                  keine Konstruktoroption und wird IGNORIERT (s. u.).
    //
    // Rueckgabe: { table, leiste, host, felder }. table ist NULL, wenn kein
    // Konstruktor da ist — und dann steht ein AUSDRUECKLICHER Hinweis MIT
    // Zeilenzahl im Baum. Eine leere Flaeche saehe aus wie 'keine Daten
    // vorhanden' (Grundregel 1).
    function tabelleAufbauen(doc, mainEl, opts) {
        opts = opts || {};
        var sicht = opts.sicht;
        var id = opts.id || ('aiw-' + (sicht || 'tk'));
        var rows = opts.rows || [];
        var cols = opts.columns || [];

        if (!doc || !mainEl) { return { table: null, leiste: null,
                                        host: null, felder: [] }; }
        if (!sicht) {
            // Ohne Kennung gaebe es weder brauchbare Hilfe-Anker noch einen
            // Schluessel fuer die Zustandssicherung. Das ist ein Bauversehen
            // und wird gemeldet, nicht stillschweigend umgangen.
            // eslint-disable-next-line no-console
            if (typeof console !== 'undefined' && console.warn) {
                console.warn('[AIW-Tabelle] tabelleAufbauen ohne "sicht" — '
                    + 'Hilfe-Anker und Zustandssicherung entfallen.');
            }
        }

        var host = doc.createElement('div');
        host.className = 'aiw-tk-host';
        host.id = id + '-table';

        if (typeof opts.Ctor !== 'function') {
            // DIE ZAHL STEHT IMMER DA, und sie steht mit dem Substantiv der
            // Sicht ('3 Anwender', nicht '3 Datensätze'). Vereinheitlichung
            // darf nicht damit bezahlt werden, dass die Meldung nichts mehr
            // sagt — 'Datensätze' ist nur der Rueckfall, wenn eine Sicht
            // nichts angibt.
            var note = doc.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Tabellenbibliothek nicht verfügbar — die '
                + 'Tabelle kann nicht angezeigt werden. Es liegen '
                + rows.length + ' ' + (opts.einheit || 'Datensätze')
                + ' vor.';
            mainEl.appendChild(note);
            return { table: null, leiste: null, host: null, felder: [] };
        }

        var table = null;
        var felder = cols.map(function (c) { return c.field; })
            .filter(function (f) { return !!f; });

        function sichern() {
            if (opts.ohneZustand || !sicht || !table) { return; }
            zustandSchreiben(sicht, zustandAusTabelle(table));
        }

        var leiste = werkzeugleiste(doc, {
            id: id + '-tk',
            sicht: sicht,
            eigene: opts.eigene || [],
            spaltenwahl: opts.spaltenwahl,
            onFilterLoeschen: function () {
                filterLoeschen(table);
                sichern();
            }
        });
        mainEl.appendChild(leiste.el);
        mainEl.appendChild(host);

        function treffer() {
            if (!table) { return; }
            var sichtbar = rows.length;
            try {
                if (typeof table.getDataCount === 'function') {
                    sichtbar = table.getDataCount('active');
                }
            } catch (e) { log('Trefferzahl nicht lesbar', e); }
            leiste.setTreffer(sichtbar, rows.length);
        }

        // Grundoptionen; die Sicht kann jede davon ueberschreiben.
        var tabOpts = {
            data: rows,
            layout: 'fitColumns',
            columns: spaltenMitFilter(rows, cols)
        };
        var eigen = opts.tabulator || {};
        Object.keys(eigen).forEach(function (k) { tabOpts[k] = eigen[k]; });

        // Die beiden Rueckrufe werden UMHUELLT statt ersetzt: eine Sicht darf
        // eigene Handler haben, ohne dass Trefferzahl oder Sicherung
        // ausfallen. Zwei Verhaltensweisen an einer Stelle sind eine zu viel.
        var eigFiltered = tabOpts.dataFiltered;
        tabOpts.dataFiltered = function () {
            treffer();
            sichern();
            if (typeof eigFiltered === 'function') {
                eigFiltered.apply(this, arguments);
            }
        };
        var eigSorted = tabOpts.dataSorted;
        tabOpts.dataSorted = function () {
            sichern();
            if (typeof eigSorted === 'function') {
                eigSorted.apply(this, arguments);
            }
        };

        // ROWCLICK IST IN TABULATOR v6.4.0 KEINE KONSTRUKTOR-OPTION.
        //
        // Wer ihn dort hineinschreibt, bekommt KEINEN Fehler — der Handler
        // wird schlicht ignoriert, und der Zeilenklick tut nichts. Genau das
        // ist zweimal passiert: cockpit_support.js (seit Build 367; die Sicht
        // versprach in ihrer eigenen Unterzeile "Zeile anklicken fuer
        // Details") und cockpit_reports.js (seit Build 378). Build 486 hat es
        // in Lektorat und Chef-Freigabe repariert, die beiden anderen aber
        // nie erreicht.
        //
        // Deshalb steht der Weg jetzt HIER: 'onRowClick' wird nach dem
        // Erzeugen ueber table.on() angehaengt. Eine Sicht kann es nicht mehr
        // falsch machen, und UX08 der Konformitaetssuite weist einen
        // rowClick in den Konstruktoroptionen zurueck.
        if (tabOpts.rowClick) {
            // eslint-disable-next-line no-console
            if (typeof console !== 'undefined' && console.warn) {
                console.warn('[AIW-Tabelle] "rowClick" in den '
                    + 'Konstruktoroptionen wird von Tabulator v6 IGNORIERT — '
                    + 'bitte opts.onRowClick verwenden. Sicht: ' + sicht);
            }
            if (!opts.onRowClick) { opts.onRowClick = tabOpts.rowClick; }
            delete tabOpts.rowClick;
        }

        table = new opts.Ctor(host, tabOpts);

        if (typeof opts.onRowClick === 'function'
                && table && typeof table.on === 'function') {
            try { table.on('rowClick', opts.onRowClick); }
            catch (e) { log('rowClick nicht anhaengbar', e); }
        }

        if (!opts.ohneZustand && sicht) {
            var uebergangen = zustandAnwenden(table, zustandLesen(sicht),
                                              felder);
            if (uebergangen.length) {
                // Kein stiller Verlust: ein Filter, der lautlos wegfaellt,
                // wirkt wie ein veraendertes Ergebnis.
                log('gesicherter Zustand teilweise übergangen:', uebergangen);
            }
        }
        treffer();

        log('Tabelle aufgebaut:', sicht, rows.length, 'Zeilen,',
            felder.length, 'Felder');
        return { table: table, leiste: leiste, host: host, felder: felder };
    }

    // filterLoeschen: entfernt ALLE Kopffilter einer Tabelle.
    // Gekapselt, weil zwei Sichten dieselbe Schaltflaeche haben und beide
    // dieselbe Wirkung zeigen muessen.
    function filterLoeschen(table) {
        if (!table) { return false; }
        try {
            if (typeof table.clearHeaderFilter === 'function') {
                table.clearHeaderFilter();
            }
            if (typeof table.clearFilter === 'function') {
                table.clearFilter(true);
            }
            return true;
        } catch (e) {
            log('Filter konnten nicht geloescht werden:', e);
            return false;
        }
    }

    // =========================================================================
    // 3) UMD-Ausgang: dieselbe API an window (Browser) UND module.exports
    //    (Node/Vitest) — die Tests pruefen den ECHTEN Code.
    // =========================================================================
    var API = {
        SCHWELLE_AUSWAHL: SCHWELLE_AUSWAHL,
        LEER_TEXT: LEER_TEXT,
        UNBEKANNT_TEXT: UNBEKANNT_TEXT,
        ZUSTAND_FORMAT: ZUSTAND_FORMAT,
        eindeutigeWerte: eindeutigeWerte,
        filterArt: filterArt,
        mehrfachFilter: mehrfachFilter,
        filterFuer: filterFuer,
        spaltenMitFilter: spaltenMitFilter,
        statZelle: statZelle,
        statSpalten: statSpalten,
        statFelder: statFelder,
        schluessel: schluessel,
        zustandLesen: zustandLesen,
        zustandSchreiben: zustandSchreiben,
        zustandLoeschen: zustandLoeschen,
        zustandAusTabelle: zustandAusTabelle,
        zustandAnwenden: zustandAnwenden,
        spaltenwahl: spaltenwahl,
        werkzeugleiste: werkzeugleiste,
        filterLoeschen: filterLoeschen,
        // Build 548: Anker fuer die spaetere Schnellhilfe.
        HILFE_MUSTER: HILFE_MUSTER,
        hilfeGueltig: hilfeGueltig,
        hilfeAnker: hilfeAnker,
        hilfeIds: hilfeIds,
        titelMitHilfe: titelMitHilfe,
        // Build 549: die gesamte Verdrahtung einer Listentabelle.
        tabelleAufbauen: tabelleAufbauen
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWTableKit = API; }
})();
