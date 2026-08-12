/**
 * management/server/static/cockpit_baustein_eingabe.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Baustein-Module (W1) — EINGABE: Editor.js + Rohmodus, Build 656
 *
 * ZWECK (Ticket 8f2b64d9, Schritt 2 der Editor.js-Reihe):
 *   "Editor.js als WYSIWYG-Haupteingabe, dazu ein Alternativmodus mit Textarea
 *   und JSON-Syntaxpruefung fuer Feinarbeit. Damit entfaellt der Bau einer
 *   eigenen Eingabemaske."
 *
 *   Setzt Build 655 voraus: report_modules fuehrt seither block_type und
 *   block_data.
 *
 * =========================================================================
 * DER KERN DIESES BAUTEILS IST NICHT DER EDITOR, SONDERN DER VERGLEICH
 * =========================================================================
 *   Ticketwortlaut: "Beim Wechsel vom Roh- in den Komfortmodus wird VERGLICHEN
 *   und werden Unterschiede GEMELDET, statt sie zu schlucken: Editor.js reicht
 *   block_data an das jeweilige Werkzeug durch, und was ein Werkzeug nicht
 *   kennt, ueberlebt ein save() moeglicherweise nicht."
 *
 *   Das ist keine Vorsichtsmassnahme, sondern eine Eigenschaft von Editor.js:
 *   ein Werkzeug baut aus den Daten sein DOM und aus dem DOM wieder Daten.
 *   Was es beim ersten Schritt nicht versteht, ist beim zweiten weg - und
 *   zwar OHNE FEHLERMELDUNG. Wer im Rohmodus ein Feld ergaenzt, das kein
 *   Werkzeug kennt, verlöre es beim naechsten Umschalten stillschweigend.
 *
 *   DESHALB: beim Wechsel Roh -> Komfort wird der Editor mit den Rohdaten
 *   aufgebaut, SOFORT wieder ausgelesen und das Ergebnis Feld fuer Feld gegen
 *   die Eingabe gehalten. Jeder Unterschied wird MIT PFAD benannt. Der
 *   Wechsel gilt erst als vollzogen, wenn die Meldung bestaetigt ist.
 *
 *   PRAEZEDENZFALL im Bestand: UnknownBlock in editor/html_renderer.py:206-226
 *   rendert einen sichtbaren Platzhalter, statt einen unbekannten Blocktyp
 *   still zu verwerfen. Dieselbe Haltung, andere Stelle.
 *
 * =========================================================================
 * WAS BEWUSST NICHT DRIN IST
 * =========================================================================
 *   SYNTAXFAERBUNG. Der Ticketwortlaut sagt es selbst: "Syntax-Highlighting
 *   braucht eine weitere Bibliothek und ist ein eigenes, spaeteres Ticket."
 *   Der Rohmodus bekommt stattdessen das, was ohne Bibliothek geht und beim
 *   Suchen eines Fehlers tatsaechlich hilft: Zeile und Spalte bei einem
 *   Syntaxfehler, eine Klammerbilanz und einen Formatieren-Knopf.
 *
 * =========================================================================
 * DER KLARTEXTSPIEGEL (body)
 * =========================================================================
 *   report_modules.body ist NOT NULL und wird an mehreren Stellen gelesen,
 *   die von Blockdaten nichts wissen: die Bausteinliste des Ermittlerservers,
 *   der Rueckfallpfad der Vorschau, die Platzhalterzaehlung des Validators.
 *
 *   Deshalb gilt ab diesem Build: block_data FUEHRT, body ist sein
 *   KLARTEXTSPIEGEL und wird bei jedem Speichern daraus erzeugt. Damit bleibt
 *   jeder Altpfad unveraendert lauffaehig, und die Platzhalter bleiben
 *   zaehlbar - auch die in einer Tabellenzelle.
 *
 * JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging; ausfuehrliche
 *   Kommentare; Kapselung; reine Funktionen einzeln exportiert (vitest);
 *   XSS-sicher ueber textContent (multilingual, UTF-8).
 *
 * =========================================================================
 * NACHTRAG BUILD 704 — DER VERGLEICH DECKTE NUR EINEN WEG AB
 * =========================================================================
 *   Der oben beschriebene Vergleich laeuft beim MODUSWECHSEL Roh -> Komfort.
 *   Der alltaegliche Weg lief ohne ihn: Datensatz oeffnen, irgendetwas
 *   aendern, speichern. Auf diesem Weg griff nichts.
 *
 *   GEMESSEN am 12.08.2026 am laufenden Bauteil mit dem echten Buendel: Ein
 *   Zitatblock { text, caption, alignment } kam nach setze() -> lies() -
 *   also nach blossem Oeffnen und Speichern, OHNE dass jemand etwas
 *   veraendert haette - zurueck als { text, type }. 'caption' und
 *   'alignment' waren weg; der body-Spiegel schrumpfte mit.
 *
 *   Beide Felder sind belegte Projektdaten: html_renderer.py:127-151 rendert
 *   'caption' als <cite> und 'alignment' als Klasse, klartextAus() in dieser
 *   Datei liest 'caption'.
 *
 *   ANTWORT: die BLINDPROBE (siehe Abschnitt 'WERKZEUGBLINDE FELDER'). Sie
 *   misst unmittelbar nach dem Aufbau - vor jeder Eingabe -, was das
 *   Werkzeug nicht halten kann, und schreibt genau das beim Lesen zurueck.
 *   Melden allein haette nicht gereicht: das Werkzeug KANN diese Felder
 *   nicht anzeigen, der Bearbeiter haette also nur die Wahl gehabt, den
 *   Verlust hinzunehmen oder nicht zu speichern.
 *
 * OEFFENTLICHE API (window.AIWBausteinEingabe)
 *   -- rein (vitest):
 *   tiefVergleich(alt, neu)         -- [{pfad, art, alt, neu}]
 *   blindeFelderAus(vorher, nachher)-- [{pfad, wert}]  (Build 704)
 *   setzeNachPfad(ziel, pfad, wert) -- {ok} | {ok:false, grund} (Build 704)
 *   jsonPruefen(text)               -- {ok, wert, zeile, spalte, meldung}
 *   klammerbilanz(text)             -- {ok, meldung, offen}
 *   formatiere(text)                -- {ok, text, fehler}
 *   klartextAus(typ, daten)         -- der body-Spiegel
 *   -- DOM:
 *   erzeuge(hostEl, opts)           -- {setze, lies, modus, aus}
 *   lies() liefert seit Build 704 zusaetzlich 'bewahrt' und 'nichtBewahrt'.
 *
 * Version: v0.8.704 · Build: 704 · 2026-08-12
 * Beleg: Ticket 8f2b64d9 (Build 656); editor/html_renderer.py:206-226
 *        (UnknownBlock) und :127-151 (Quote-Datenformat);
 *        management/server/static/cockpit_baustein_vorschau.js:118-132;
 *        deployment/build_editor_bundle.py:56 (@cychann/editorjs-quote).
 */
(function () {
    'use strict';

    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[baustein-eingabe]');
            console.log.apply(console, a);
        }
    }

    function _s(v) { return (v === undefined || v === null) ? '' : String(v); }

    // =====================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — vitest.
    // =====================================================================

    // tiefVergleich: was hat sich zwischen zwei Datensaetzen geaendert?
    // ------------------------------------------------------------------
    // Rueckgabe: [{pfad, art, alt, neu}] mit art aus
    //   'entfallen'  — im Nachher gar nicht mehr da (DER GEFAEHRLICHE FALL)
    //   'geaendert'  — anderer Wert
    //   'neu'        — im Nachher hinzugekommen (Editor.js ergaenzt Vorgaben)
    //
    // DER PFAD IST DER PUNKT. Eine Meldung "die Daten haben sich geaendert"
    // hilft niemandem; "content.1.2 ist entfallen" schon. Deshalb wird
    // rekursiv gegangen und nicht nur JSON.stringify verglichen.
    //
    // Reihenfolge in Arrays IST bedeutungstragend (Tabellenzeilen!), deshalb
    // wird ueber den Index verglichen und nicht ueber Mengen.
    function tiefVergleich(alt, neu, pfad) {
        pfad = pfad || '';
        var raus = [];

        function _typ(v) {
            if (v === null) { return 'null'; }
            if (Array.isArray(v)) { return 'array'; }
            return typeof v;
        }
        var ta = _typ(alt), tn = _typ(neu);

        if (ta !== tn) {
            raus.push({ pfad: pfad || '(Wurzel)', art: 'geaendert',
                        alt: alt, neu: neu });
            return raus;
        }
        if (ta === 'object') {
            var schluessel = {};
            Object.keys(alt).forEach(function (k) { schluessel[k] = true; });
            Object.keys(neu).forEach(function (k) { schluessel[k] = true; });
            Object.keys(schluessel).sort().forEach(function (k) {
                var p = pfad ? (pfad + '.' + k) : k;
                var inAlt = Object.prototype.hasOwnProperty.call(alt, k);
                var inNeu = Object.prototype.hasOwnProperty.call(neu, k);
                if (inAlt && !inNeu) {
                    raus.push({ pfad: p, art: 'entfallen', alt: alt[k],
                                neu: undefined });
                } else if (!inAlt && inNeu) {
                    raus.push({ pfad: p, art: 'neu', alt: undefined,
                                neu: neu[k] });
                } else {
                    raus = raus.concat(tiefVergleich(alt[k], neu[k], p));
                }
            });
            return raus;
        }
        if (ta === 'array') {
            var n = Math.max(alt.length, neu.length);
            for (var i = 0; i < n; i++) {
                var pi = pfad ? (pfad + '.' + i) : String(i);
                if (i >= neu.length) {
                    raus.push({ pfad: pi, art: 'entfallen', alt: alt[i],
                                neu: undefined });
                } else if (i >= alt.length) {
                    raus.push({ pfad: pi, art: 'neu', alt: undefined,
                                neu: neu[i] });
                } else {
                    raus = raus.concat(tiefVergleich(alt[i], neu[i], pi));
                }
            }
            return raus;
        }
        if (alt !== neu) {
            raus.push({ pfad: pfad || '(Wurzel)', art: 'geaendert',
                        alt: alt, neu: neu });
        }
        return raus;
    }

    // =====================================================================
    // BUILD 704 — WERKZEUGBLINDE FELDER
    //
    // DER BEFUND, DER DAZU GEFUEHRT HAT (gemessen am laufenden Bauteil mit
    // dem echten Buendel, 12.08.2026):
    //
    //   Ein Zitatblock aus der Datenbank
    //     { "text": "...", "caption": "Vernehmung vom 03.04.2026",
    //       "alignment": "left" }
    //   kommt nach setze() -> lies() - also nach blossem OEFFNEN UND
    //   SPEICHERN, ohne dass jemand etwas veraendert haette - zurueck als
    //     { "text": "...", "type": "quotationMark" }
    //
    //   'caption' und 'alignment' sind WEG. Beide sind keine erfundenen
    //   Felder: editor/html_renderer.py:127-151 rendert 'caption' als
    //   <cite class="cdx-quote__caption"> und 'alignment' als Klasse. Und
    //   klartextAus() in dieser Datei liest 'caption' ebenfalls - der
    //   body-Spiegel schrumpfte im selben Zug mit.
    //
    // URSACHE: Das gebuendelte Zitatwerkzeug ist '@cychann/editorjs-quote'
    // (deployment/build_editor_bundle.py:56, seit 0.6.044b). Dessen
    // Datenmodell ist {text, type}. Der Renderer dagegen ist auf das
    // Datenmodell von '@editorjs/quote' geschrieben, {text, caption,
    // alignment}. Zwei Datenmodelle fuer denselben Block, und keine Seite
    // weiss von der anderen. DAS ZUSAMMENFUEHREN DER BEIDEN MODELLE IST
    // EIN EIGENER VORGANG - hier wird der VERLUST behoben, nicht die
    // Modellfrage entschieden.
    //
    // WARUM MELDEN ALLEIN NICHT REICHT: Der Moduswechsel Roh -> Komfort
    // vergleicht seit Build 656 und fragt nach. Der alltaegliche Weg
    // - Datensatz oeffnen, etwas ganz anderes aendern, speichern - lief
    // ohne jeden Vergleich. Eine blosse Meldung an dieser Stelle haette
    // den Bearbeiter vor die Wahl gestellt "speichern und Inhalt
    // verlieren" oder "nicht speichern"; beides ist keine Loesung, wenn
    // das Werkzeug das Feld ueberhaupt nicht anzeigen kann.
    //
    // DAS VERFAHREN: Unmittelbar nachdem der Editor aus den geladenen
    // Daten aufgebaut ist - BEVOR ein Mensch etwas anfassen konnte - wird
    // er sofort wieder ausgelesen und mit den geladenen Daten verglichen.
    // Was in dieser Sekunde bereits fehlt, kann das Werkzeug nicht halten;
    // es ist WERKZEUGBLIND. Nur genau diese Felder werden beim spaeteren
    // Lesen zurueckgeschrieben.
    //
    // WARUM DER ZEITPUNKT ENTSCHEIDET - und warum nicht einfach jedes
    // spaeter fehlende Feld zurueckgeschrieben wird: Loescht der Bearbeiter
    // spaeter den zweiten Punkt einer Aufzaehlung, fehlt 'items.1' EBENSO.
    // Ein pauschales Zurueckschreiben wuerde diesen Punkt wieder
    // auferstehen lassen - aus einem Datenverlust wuerde eine
    // Datenfaelschung. Die Messung vor der ersten Eingabe trennt beides
    // sauber: sie sieht nur, was das WERKZEUG nicht kann, nie das, was
    // der MENSCH wollte.
    // =====================================================================

    // blindeFelderAus: was ist zwischen 'vorher' und 'nachher' ERSATZLOS
    // verschwunden? Ergaenzungen des Werkzeugs (art 'neu', etwa
    // table.stretched oder delimiter.style) und geaenderte Werte bleiben
    // ausdruecklich aussen vor - ergaenzt wird nichts weggenommen, und ein
    // geaenderter Wert ist keine Blindheit, sondern eine Umformung.
    function blindeFelderAus(vorher, nachher) {
        return tiefVergleich(vorher, nachher)
            .filter(function (u) { return u.art === 'entfallen'; })
            .map(function (u) { return { pfad: u.pfad, wert: u.alt }; });
    }

    // setzeNachPfad: einen Wert an einem Pfad aus tiefVergleich ablegen.
    //
    // Gibt {ok:true} oder {ok:false, grund:'...'} zurueck - NIE still
    // fehlschlagen (Grundregel 1). Der Aufrufer meldet, was nicht
    // zurueckgeschrieben werden konnte, statt es zu verschweigen.
    //
    // ABSICHTLICH ZURUECKHALTEND: Fehlt ein Zwischenglied des Pfades, wird
    // es NICHT angelegt. Ein Werkzeug, das ein ganzes Unterobjekt fallen
    // laesst, hat den Block umgebaut; dort einen Wert einzuhaengen hiesse
    // raten. Bei Feldern gilt: nur setzen, wenn nicht schon da - was der
    // Editor liefert, hat Vorrang vor dem Bewahrten.
    function setzeNachPfad(ziel, pfad, wert) {
        var teile = _s(pfad).split('.');
        if (!_s(pfad) || pfad === '(Wurzel)') {
            return { ok: false, grund: 'kein verwertbarer Pfad' };
        }
        var knoten = ziel;
        for (var i = 0; i < teile.length - 1; i++) {
            if (knoten === null || typeof knoten !== 'object') {
                return { ok: false, grund: 'Zwischenglied "' + teile[i]
                                            + '" ist kein Objekt' };
            }
            if (!Object.prototype.hasOwnProperty.call(knoten, teile[i])) {
                return { ok: false, grund: 'Zwischenglied "' + teile[i]
                                            + '" fehlt' };
            }
            knoten = knoten[teile[i]];
        }
        var letzt = teile[teile.length - 1];
        if (knoten === null || typeof knoten !== 'object') {
            return { ok: false, grund: 'Ziel ist kein Objekt' };
        }
        if (Array.isArray(knoten)) {
            // In einer Liste ist der Pfad ein Index. Zurueckgeschrieben wird
            // nur AM ENDE - an einer anderen Stelle einzufuegen wuerde die
            // Reihenfolge der uebrigen Eintraege verschieben, und in einer
            // Tabellenzeile ist die Reihenfolge bedeutungstragend.
            var idx = parseInt(letzt, 10);
            if (String(idx) !== letzt || idx < 0) {
                return { ok: false, grund: 'kein Listenindex: "' + letzt + '"' };
            }
            if (idx !== knoten.length) {
                return { ok: false, grund: 'Listenplatz ' + idx
                                            + ' ist nicht das Ende' };
            }
            knoten.push(wert);
            return { ok: true };
        }
        if (Object.prototype.hasOwnProperty.call(knoten, letzt)) {
            return { ok: false, grund: 'Feld ist bereits belegt' };
        }
        knoten[letzt] = wert;
        return { ok: true };
    }

    // jsonPruefen: Syntaxpruefung MIT ZEILE UND SPALTE.
    // ------------------------------------------------------------------
    // JSON.parse meldet je nach Browser eine Zeichenposition ("at position
    // 47") oder gar nichts Verwertbares. Eine Position in einem 400 Zeichen
    // langen Text hilft beim Suchen nicht - Zeile und Spalte schon. Sie
    // werden deshalb aus der Position ausgerechnet.
    function jsonPruefen(text) {
        var t = _s(text);
        if (t.trim() === '') {
            return { ok: false, wert: null, zeile: 1, spalte: 1,
                     meldung: 'Der Rohtext ist leer. Erwartet wird ein '
                         + 'JSON-Objekt, z. B. {"text": "..."}.' };
        }
        try {
            var wert = JSON.parse(t);
            if (wert === null || typeof wert !== 'object'
                    || Array.isArray(wert)) {
                return { ok: false, wert: null, zeile: 1, spalte: 1,
                         meldung: 'Gültiges JSON, aber kein OBJEKT. '
                             + 'Editor.js reicht je Block ein Objekt an sein '
                             + 'Werkzeug durch.' };
            }
            return { ok: true, wert: wert, zeile: 0, spalte: 0, meldung: '' };
        } catch (e) {
            var pos = _positionAus(e && e.message);
            var zs = _zeileSpalte(t, pos);
            return { ok: false, wert: null, zeile: zs.zeile, spalte: zs.spalte,
                     meldung: (e && e.message) ? String(e.message)
                                               : 'Kein gültiges JSON.' };
        }
    }

    // _positionAus: die Zeichenposition aus der Fehlermeldung fischen.
    // Verschiedene Laufzeiten formulieren verschieden ("at position 12",
    // "at line 2 column 5"); es wird genommen, was da ist, und sonst 0.
    function _positionAus(meldung) {
        var m = /position\s+(\d+)/i.exec(_s(meldung));
        return m ? parseInt(m[1], 10) : 0;
    }

    function _zeileSpalte(text, pos) {
        var bis = _s(text).slice(0, Math.max(0, pos));
        var zeilen = bis.split('\n');
        return { zeile: zeilen.length,
                 spalte: zeilen[zeilen.length - 1].length + 1 };
    }

    // klammerbilanz: zaehlt {} und [] AUSSERHALB von Zeichenketten.
    // ------------------------------------------------------------------
    // Sie ersetzt die Syntaxpruefung nicht - sie beantwortet die Frage, die
    // man beim Suchen zuerst stellt: fehlt hinten eine Klammer, oder steht
    // eine zu viel? JSON.parse sagt nur, wo es aufgehoert hat zu verstehen.
    //
    // Zeichenketten werden uebersprungen, sonst zaehlte eine geschweifte
    // Klammer im Text mit - und die Bilanz waere Laerm statt Auskunft.
    function klammerbilanz(text) {
        var t = _s(text);
        var stapel = [];
        var inStr = false, esc = false;
        for (var i = 0; i < t.length; i++) {
            var c = t[i];
            if (inStr) {
                if (esc) { esc = false; }
                else if (c === '\\') { esc = true; }
                else if (c === '"') { inStr = false; }
                continue;
            }
            if (c === '"') { inStr = true; continue; }
            if (c === '{' || c === '[') { stapel.push({ z: c, i: i }); }
            else if (c === '}' || c === ']') {
                var erwartet = (c === '}') ? '{' : '[';
                if (!stapel.length) {
                    var zs = _zeileSpalte(t, i);
                    return { ok: false, offen: 0,
                             meldung: 'Eine schließende Klammer "' + c
                                 + '" ohne öffnende (Zeile ' + zs.zeile
                                 + ', Spalte ' + zs.spalte + ').' };
                }
                var oben = stapel.pop();
                if (oben.z !== erwartet) {
                    var zs2 = _zeileSpalte(t, i);
                    return { ok: false, offen: stapel.length + 1,
                             meldung: 'Klammern überkreuzen sich: "' + oben.z
                                 + '" wird mit "' + c + '" geschlossen '
                                 + '(Zeile ' + zs2.zeile + ', Spalte '
                                 + zs2.spalte + ').' };
                }
            }
        }
        if (inStr) {
            return { ok: false, offen: stapel.length,
                     meldung: 'Eine Zeichenkette ist nicht geschlossen - es '
                         + 'fehlt ein Anführungszeichen.' };
        }
        if (stapel.length) {
            var erste = stapel[0];
            var zs3 = _zeileSpalte(t, erste.i);
            return { ok: false, offen: stapel.length,
                     meldung: stapel.length + ' Klammer(n) sind nicht '
                         + 'geschlossen; die erste ist "' + erste.z
                         + '" in Zeile ' + zs3.zeile + ', Spalte '
                         + zs3.spalte + '.' };
        }
        return { ok: true, offen: 0, meldung: 'Klammern gehen auf.' };
    }

    // formatiere: einrücken, ohne den Inhalt anzutasten.
    function formatiere(text) {
        var p = jsonPruefen(text);
        if (!p.ok) { return { ok: false, text: _s(text), fehler: p.meldung }; }
        return { ok: true, text: JSON.stringify(p.wert, null, 2), fehler: null };
    }

    // klartextAus: der body-Spiegel eines Blocks.
    // ------------------------------------------------------------------
    // WOZU: report_modules.body ist NOT NULL und wird an Stellen gelesen, die
    // von Blockdaten nichts wissen - die Bausteinliste des Ermittlerservers,
    // der Rueckfallpfad der Vorschau, die Platzhalterzaehlung des Validators.
    // Der Spiegel haelt sie alle lauffaehig.
    //
    // HTML WIRD ENTFERNT, PLATZHALTER BLEIBEN. Editor.js legt Auszeichnungen
    // als HTML in den Text ('<b>', '<mark>'); im body haetten sie nichts zu
    // suchen. Die Platzhalter dagegen MUESSEN stehenbleiben, sonst zaehlt sie
    // der Validator nicht mehr.
    function klartextAus(typ, daten, chips) {
        var d = daten || {};
        var pc = chips || (typeof window !== 'undefined'
            ? window.PlaceholderChips : null);

        function _text(v) {
            var s = _s(v);
            if (pc && typeof pc.dehydrateChips === 'function' && s.indexOf('<') >= 0) {
                s = pc.dehydrateChips(s);
            }
            // Was danach noch an Auszeichnung uebrig ist, faellt weg.
            return s.replace(/<[^>]*>/g, '');
        }

        switch (_s(typ) || 'paragraph') {
            case 'header':
            case 'paragraph':
                return _text(d.text);
            case 'quote':
                return [_text(d.text), _text(d.caption)]
                    .filter(function (x) { return x !== ''; }).join('\n');
            case 'list':
                return _listeText(d.items, _text).join('\n');
            case 'table':
                return (Array.isArray(d.content) ? d.content : [])
                    .map(function (zeile) {
                        return (Array.isArray(zeile) ? zeile : [])
                            .map(_text).join('\t');
                    }).join('\n');
            case 'delimiter':
                // Ein Trenner hat keinen Text. body ist aber NOT NULL, und
                // ein leerer body faellt beim Validator durch ('body fehlt').
                // Deshalb ein sprechendes Zeichen statt einer leeren Zeile.
                return '---';
            default:
                // Ein Typ, den dieser Spiegel nicht kennt. NICHT still leer
                // lassen (Grundregel 1): was an Text da ist, kommt mit.
                return _text(d.text || d.caption || '');
        }
    }

    // _listeText: NestedList kann verschachtelt sein (items[].content +
    // items[].items). Beide Formen kommen vor - die flache aus aelteren
    // Daten, die verschachtelte aus dem aktuellen Werkzeug.
    function _listeText(items, _text, tiefe) {
        tiefe = tiefe || 0;
        var raus = [];
        (Array.isArray(items) ? items : []).forEach(function (it) {
            if (it === null || it === undefined) { return; }
            var praefix = new Array(tiefe + 1).join('  ');
            if (typeof it === 'string') {
                raus.push(praefix + _text(it));
                return;
            }
            raus.push(praefix + _text(it.content));
            if (Array.isArray(it.items) && it.items.length) {
                raus = raus.concat(_listeText(it.items, _text, tiefe + 1));
            }
        });
        return raus;
    }

    // =====================================================================
    // 2) DOM.
    // =====================================================================

    function _leeren(el) {
        while (el && el.firstChild) { el.removeChild(el.firstChild); }
    }

    // _btn: die Schaltflaechenfabrik dieser Datei.
    //
    // SIE SETZT DIE HILFE-MARKE NICHT. Das ist die Fabrikregel aus Build 633:
    // eine Fabrik erzeugt mehrere verschiedene Bedienelemente, und eine ueber
    // eine Variable gesetzte Marke ist im Quelltext nicht auffindbar - die
    // Vollstaendigkeitspruefung (BD09/BD10) sieht dann eine Schaltflaeche
    // ohne Hilfe und vier Hilfetexte ohne Schaltflaeche. Die Marken stehen
    // deshalb LITERAL an den ABNAHMESTELLEN, jede einzeln.
    function _btn(doc, text, klasse, onClick) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'aiw-btn aiw-btn-klein ' + (klasse || '');
        b.textContent = text;
        if (onClick) { b.addEventListener('click', onClick); }
        return b;
    }

    /**
     * erzeuge(hostEl, opts) -> Steuerobjekt
     *   opts.EditorCtor / opts.tools / opts.chips — injizierbar (Tests)
     *   opts.onChange()  — wird nach jeder Aenderung gerufen (Entwurf!)
     * Rueckgabe: { setze(typ, daten), lies(), modus(), aus() }
     */
    function erzeuge(hostEl, opts) {
        opts = opts || {};
        var doc = (hostEl && hostEl.ownerDocument) || document;
        // blindeFelder / blindTyp / blindProbe (Build 704): Ergebnis und
        // Laufzustand der Blindprobe. blindTyp haelt fest, FUER WELCHE
        // Blockart gemessen wurde - nach einem Artwechsel gilt die Messung
        // nicht mehr.
        var zustand = { modus: 'komfort', typ: 'paragraph', daten: {},
                        instanz: null,
                        blindeFelder: [], blindTyp: null, blindProbe: null };

        // --- Aufbau der Flaeche -----------------------------------------
        var kopf = doc.createElement('div');
        kopf.className = 'aiw-mod-eing-kopf';
        hostEl.appendChild(kopf);

        var typWahl = doc.createElement('select');
        typWahl.className = 'aiw-mod-eing-typ';
        typWahl.setAttribute('data-hilfe-id', 'modules.bedienung.blockart');
        [['paragraph', 'Absatz'], ['header', 'Überschrift'],
         ['list', 'Liste'], ['table', 'Tabelle'], ['quote', 'Zitat'],
         ['delimiter', 'Trenner']].forEach(function (p) {
            var o = doc.createElement('option');
            o.value = p[0];
            o.textContent = p[1] + ' (' + p[0] + ')';
            typWahl.appendChild(o);
        });
        kopf.appendChild(typWahl);

        var modusBtn = _btn(doc, 'Rohmodus', 'aiw-mod-eing-modus', null);
        modusBtn.setAttribute('data-hilfe-id', 'modules.bedienung.rohmodus');
        kopf.appendChild(modusBtn);
        var formatBtn = _btn(doc, 'Formatieren', 'aiw-mod-eing-format', null);
        formatBtn.setAttribute('data-hilfe-id',
                               'modules.bedienung.formatieren');
        formatBtn.hidden = true;
        kopf.appendChild(formatBtn);

        var komfortHost = doc.createElement('div');
        komfortHost.className = 'aiw-mod-eing-komfort';
        hostEl.appendChild(komfortHost);

        var rohFeld = doc.createElement('textarea');
        rohFeld.className = 'aiw-mod-eing-roh';
        rohFeld.rows = 10;
        rohFeld.hidden = true;
        rohFeld.setAttribute('data-hilfe-id', 'modules.bedienung.rohtext');
        hostEl.appendChild(rohFeld);

        var meldung = doc.createElement('p');
        meldung.className = 'aiw-mod-eing-meldung';
        hostEl.appendChild(meldung);

        var vergleichKasten = doc.createElement('div');
        vergleichKasten.className = 'aiw-mod-eing-vergleich';
        vergleichKasten.hidden = true;
        hostEl.appendChild(vergleichKasten);

        function _melde(text, art) {
            meldung.textContent = _s(text);
            meldung.className = 'aiw-mod-eing-meldung'
                + (art ? (' ist-' + art) : '');
        }
        function _geaendert() {
            if (typeof opts.onChange === 'function') { opts.onChange(); }
        }

        // --- Komfortmodus (Editor.js) -----------------------------------
        function _ctor() {
            return opts.EditorCtor
                || (typeof window !== 'undefined' ? window.EditorJS : null);
        }
        function _tools() {
            if (opts.tools) { return opts.tools; }
            var vs = (typeof window !== 'undefined')
                ? window.AIWBausteinVorschau : null;
            // Dieselbe Werkzeugliste wie die Vorschau - eine zweite Liste
            // waere eine zweite Wahrheit, und dann koennte die Vorschau
            // etwas anzeigen, was die Eingabe nicht bauen kann.
            return (vs && typeof vs.werkzeuge === 'function')
                ? vs.werkzeuge(window) : {};
        }

        function _komfortAbbauen() {
            if (zustand.instanz && typeof zustand.instanz.destroy === 'function') {
                try { zustand.instanz.destroy(); }
                catch (e) { log('Abbau', e); }
            }
            zustand.instanz = null;
            _leeren(komfortHost);
        }

        function _komfortAufbauen() {
            _komfortAbbauen();
            var Ctor = _ctor();
            if (typeof Ctor !== 'function') {
                // KEIN STILLER AUSFALL: die Flaeche sagt, was fehlt, und der
                // Rohmodus bleibt der Weg, auf dem gearbeitet werden kann.
                komfortHost.textContent = 'Editor.js nicht geladen '
                    + '(editor.bundle.js). Der Rohmodus steht zur Verfügung.';
                komfortHost.classList.add('ist-warnung');
                return null;
            }
            komfortHost.classList.remove('ist-warnung');
            zustand.instanz = new Ctor({
                holder: komfortHost,
                minHeight: 0,
                tools: _tools(),
                data: { blocks: [{ type: zustand.typ, data: zustand.daten }] },
                // BUILD 656: DER ENTWURFSSPEICHER HAENGT HIER DRAN.
                // cockpit_modules.js sichert bei 'input'/'change' auf dem
                // Formular - Editor.js erzeugt beides NICHT. Ohne diese
                // Bruecke setzte der Entwurfsspeicher stillschweigend aus,
                // und ein Neuladen kostete die Arbeit.
                onChange: function () { _geaendert(); }
            });
            _blindprobeStarten(zustand.daten, zustand.typ);
            return zustand.instanz;
        }

        // _blindSatz: der Hinweis auf werkzeugblinde Felder, an EINER Stelle
        // formuliert.
        //
        // Er wird an zwei Stellen gebraucht - nach dem blossen Aufbau und
        // nach einem Moduswechsel - und beide schreiben in dasselbe
        // Meldungsfeld. Bis das hier zusammengefasst war, ueberschrieb die
        // Erfolgsmeldung des Wechsels ('Der Wechsel ist verlustfrei.')
        // ausgerechnet den Hinweis, dass Felder nicht angezeigt werden
        // koennen. Der Bearbeiter sah dann nur noch die Entwarnung.
        function _blindSatz(felder) {
            return 'Das Werkzeug dieser Blockart kann ' + felder.length
                + ' Angabe(n) nicht anzeigen: '
                + felder.map(function (f) { return f.pfad; }).join(', ')
                + '. Sie bleiben beim Speichern erhalten; ändern lassen sie '
                + 'sich im Rohmodus.';
        }

        // _blindprobeStarten: die Messung aus dem Kopf dieser Datei.
        //
        // Sie laeuft EINMAL je Aufbau und VOR jeder Eingabe: Editor fertig
        // aufgebaut -> sofort wieder auslesen -> gegen die geladenen Daten
        // halten. Was jetzt schon fehlt, kann das Werkzeug nicht halten.
        //
        // Das Ergebnis wird als Versprechen gemerkt, nicht nur als Liste:
        // _komfortLesen() kann waehrend der laufenden Messung aufgerufen
        // werden (schnelles Speichern nach dem Oeffnen), und dann muss es
        // warten - sonst waere ausgerechnet der eilige Fall der ungesicherte.
        function _blindprobeStarten(alsGebaut, typBeimBau) {
            zustand.blindeFelder = [];
            zustand.blindTyp = typBeimBau;
            zustand.blindProbe = null;

            var inst = zustand.instanz;
            var hatIsReady = inst && inst.isReady
                && typeof inst.isReady.then === 'function';
            if (!hatIsReady) {
                // Kein echter Editor (fehlendes Buendel, gestellter Ctor im
                // Test). Dann gibt es auch nichts zu bewahren - und vor
                // allem nichts zu verschweigen: ohne Editor laeuft der
                // Rohmodus, und der haelt ohnehin alle Felder.
                return;
            }
            // save() WIRD ERST NACH isReady ANGEHAENGT - gemessen an
            // Editor.js 2.31.6: unmittelbar nach 'new EditorJS(...)' ist
            // 'typeof instanz.save' noch 'undefined'. Eine Pruefung auf save
            // VOR dem Warten haette die Messung genau dann uebersprungen,
            // wenn sie gebraucht wird, und zwar lautlos. Deshalb steht die
            // Pruefung hinter isReady und nicht davor.
            zustand.blindProbe = inst.isReady.then(function () {
                if (typeof inst.save !== 'function') {
                    throw new Error('save() fehlt nach isReady');
                }
                return inst.save();
            }).then(function (erg) {
                if (zustand.instanz !== inst) { return; }   // zwischenzeitlich neu aufgebaut
                var b = (erg && erg.blocks && erg.blocks[0]) || null;
                zustand.blindeFelder = b
                    ? blindeFelderAus(alsGebaut || {}, b.data || {}) : [];
                if (zustand.blindeFelder.length) {
                    _melde(_blindSatz(zustand.blindeFelder), 'warnung');
                }
            })['catch'](function (e) {
                // GEMELDET, NICHT VERSCHLUCKT: schlaegt die Messung fehl,
                // wird NICHTS bewahrt - und das muss man wissen, sonst
                // haelt man sich faelschlich fuer geschuetzt.
                log('Blindprobe', e);
                zustand.blindeFelder = [];
                _melde('Die Prüfung auf nicht darstellbare Angaben ist '
                    + 'fehlgeschlagen. Vor dem Speichern bitte im Rohmodus '
                    + 'nachsehen.', 'fehler');
            });
        }

        // _komfortLesen: was steht gerade im Editor? Gibt ein Versprechen,
        // weil save() eines ist.
        //
        // BUILD 704: Vor dem Auslesen wird die Blindprobe abgewartet und
        // danach werden die werkzeugblinden Felder zurueckgeschrieben. Das
        // Ergebnis traegt 'bewahrt' und 'nichtBewahrt' - der Aufrufer soll
        // beides sehen koennen, ohne in dieser Datei nachlesen zu muessen.
        function _komfortLesen() {
            var inst = zustand.instanz;
            if (!inst) {
                return Promise.resolve({ type: zustand.typ,
                                         data: zustand.daten,
                                         bewahrt: [], nichtBewahrt: [] });
            }
            // ERST WARTEN, DANN AUF save() PRUEFEN - aus demselben Grund wie
            // in _blindprobeStarten: vor isReady gibt es save() noch nicht.
            // Die Pruefung stand hier bis Build 704 VOR dem Warten; ein
            // Speichern unmittelbar nach dem Oeffnen lieferte deshalb den
            // GELADENEN Stand zurueck statt des im Editor stehenden. Das fiel
            // nicht auf, weil beide meist gleich sind - aber eben nur meist.
            var warten = zustand.blindProbe
                || (inst.isReady && typeof inst.isReady.then === 'function'
                    ? inst.isReady : Promise.resolve());
            return warten.then(function () {
                if (typeof inst.save !== 'function') {
                    return null;
                }
                return inst.save();
            }).then(function (erg) {
                if (erg === null) {
                    return { type: zustand.typ, data: zustand.daten,
                             bewahrt: [], nichtBewahrt: [] };
                }
                var b = (erg && erg.blocks && erg.blocks[0]) || null;
                if (!b) {
                    return { type: zustand.typ, data: {},
                             bewahrt: [], nichtBewahrt: [] };
                }
                var daten = b.data || {};
                var bewahrt = [], nichtBewahrt = [];

                // NUR bei unveraenderter Blockart. Hat der Bearbeiter die Art
                // gewechselt, gehoerten die gemessenen Felder zu einem anderen
                // Werkzeug - sie in den neuen Block zu heben, ergaebe einen
                // Block, den so nie jemand geschrieben hat.
                if (b.type === zustand.blindTyp) {
                    (zustand.blindeFelder || []).forEach(function (f) {
                        var e = setzeNachPfad(daten, f.pfad, f.wert);
                        if (e.ok) { bewahrt.push(f); }
                        else { nichtBewahrt.push({ pfad: f.pfad, wert: f.wert,
                                                   grund: e.grund }); }
                    });
                }
                return { type: b.type, data: daten,
                         bewahrt: bewahrt, nichtBewahrt: nichtBewahrt };
            });
        }

        // --- Der Vergleich beim Moduswechsel ----------------------------
        function _vergleichZeigen(unterschiede, aufUebernehmen, aufZurueck) {
            _leeren(vergleichKasten);
            vergleichKasten.hidden = false;

            var titel = doc.createElement('p');
            titel.className = 'aiw-mod-eing-vergleich-titel';
            titel.textContent = 'Der Komfortmodus würde ' + unterschiede.length
                + ' Angabe(n) verändern oder verlieren. Editor.js gibt die '
                + 'Blockdaten an sein Werkzeug weiter; was das Werkzeug nicht '
                + 'kennt, überlebt den Wechsel nicht.';
            vergleichKasten.appendChild(titel);

            var ul = doc.createElement('ul');
            unterschiede.forEach(function (u) {
                var li = doc.createElement('li');
                li.className = 'ist-' + u.art;
                var was = (u.art === 'entfallen') ? 'entfällt'
                        : (u.art === 'neu') ? 'kommt hinzu' : 'ändert sich';
                var text = u.pfad + ': ' + was;
                if (u.art === 'geaendert') {
                    text += ' — vorher ' + JSON.stringify(u.alt)
                        + ', nachher ' + JSON.stringify(u.neu);
                } else if (u.art === 'entfallen') {
                    text += ' — Wert war ' + JSON.stringify(u.alt);
                } else {
                    text += ' — Wert ' + JSON.stringify(u.neu);
                }
                li.textContent = text;
                ul.appendChild(li);
            });
            vergleichKasten.appendChild(ul);

            var leiste = doc.createElement('div');
            leiste.className = 'aiw-mod-eing-vergleich-leiste';
            var uebBtn = _btn(doc, 'Wechseln und Änderungen übernehmen',
                'aiw-mod-eing-uebernehmen', function () {
                    vergleichKasten.hidden = true;
                    aufUebernehmen();
                });
            uebBtn.setAttribute('data-hilfe-id',
                                'modules.bedienung.uebernehmen');
            leiste.appendChild(uebBtn);
            var zurBtn = _btn(doc, 'Im Rohmodus bleiben',
                'aiw-mod-eing-zurueck', function () {
                    vergleichKasten.hidden = true;
                    aufZurueck();
                });
            zurBtn.setAttribute('data-hilfe-id', 'modules.bedienung.zurueck');
            leiste.appendChild(zurBtn);
            vergleichKasten.appendChild(leiste);
        }

        // --- Moduswechsel ------------------------------------------------
        function _zeigeModus() {
            var roh = (zustand.modus === 'roh');
            rohFeld.hidden = !roh;
            komfortHost.hidden = roh;
            formatBtn.hidden = !roh;
            modusBtn.textContent = roh ? 'Komfortmodus' : 'Rohmodus';
            typWahl.disabled = roh;   // im Rohmodus steht der Typ im JSON
        }

        function _nachRoh() {
            return _komfortLesen().then(function (b) {
                zustand.typ = b.type;
                zustand.daten = b.data;
                _komfortAbbauen();
                rohFeld.value = JSON.stringify(b.data, null, 2);
                zustand.modus = 'roh';
                _zeigeModus();
                _melde('Rohmodus. Die Blockart steht links; hier stehen nur '
                    + 'die Daten des Blocks.', null);
            });
        }

        // _nachKomfort: DER KERN. Rohdaten pruefen, Editor damit aufbauen,
        // SOFORT wieder auslesen und vergleichen.
        function _nachKomfort() {
            var p = jsonPruefen(rohFeld.value);
            if (!p.ok) {
                var kb = klammerbilanz(rohFeld.value);
                _melde('Zeile ' + p.zeile + ', Spalte ' + p.spalte + ': '
                    + p.meldung + (kb.ok ? '' : ' — ' + kb.meldung), 'fehler');
                return Promise.resolve(false);
            }

            var eingabe = p.wert;
            zustand.daten = eingabe;
            zustand.modus = 'komfort';
            _zeigeModus();
            _komfortAufbauen();

            if (!zustand.instanz) {
                // Ohne Editor gibt es nichts zu vergleichen - und nichts zu
                // verlieren, weil die Daten unveraendert stehenbleiben.
                _melde('Komfortmodus ohne Editor.js — die Daten sind '
                    + 'unverändert übernommen.', 'warnung');
                return Promise.resolve(true);
            }

            var bereit = (zustand.instanz.isReady
                && typeof zustand.instanz.isReady.then === 'function')
                ? zustand.instanz.isReady : Promise.resolve();

            return bereit.then(_komfortLesen).then(function (b) {
                var unterschiede = tiefVergleich(eingabe, b.data);
                if (!unterschiede.length) {
                    // Build 704: Der Hinweis auf werkzeugblinde Felder gehoert
                    // AN diese Erfolgsmeldung und nicht daneben - sonst
                    // ueberschreibt die Entwarnung genau die Auskunft, die der
                    // Bearbeiter braucht, um das Feld spaeter wiederzufinden.
                    var blind = (b.bewahrt && b.bewahrt.length)
                        ? ' ' + _blindSatz(b.bewahrt) : '';
                    _melde('Komfortmodus. Der Wechsel ist verlustfrei.' + blind,
                        blind ? 'warnung' : 'ok');
                    return true;
                }
                // NICHT SCHLUCKEN, SONDERN MELDEN - und den Wechsel erst
                // vollziehen, wenn er bestaetigt ist.
                _melde('Der Wechsel ist NICHT verlustfrei — bitte die Liste '
                    + 'unten ansehen.', 'fehler');
                _vergleichZeigen(unterschiede,
                    function () {
                        zustand.daten = b.data;
                        _melde('Komfortmodus. Die gemeldeten Änderungen sind '
                            + 'übernommen.', 'warnung');
                        _geaendert();
                    },
                    function () {
                        zustand.daten = eingabe;
                        zustand.modus = 'roh';
                        _komfortAbbauen();
                        rohFeld.value = JSON.stringify(eingabe, null, 2);
                        _zeigeModus();
                        _melde('Zurück im Rohmodus. Nichts ist verändert '
                            + 'worden.', null);
                    });
                return false;
            });
        }

        modusBtn.addEventListener('click', function () {
            vergleichKasten.hidden = true;
            if (zustand.modus === 'komfort') { _nachRoh(); }
            else { _nachKomfort(); }
        });

        formatBtn.addEventListener('click', function () {
            var f = formatiere(rohFeld.value);
            if (!f.ok) {
                var kb = klammerbilanz(rohFeld.value);
                _melde('Nicht formatierbar: ' + f.fehler
                    + (kb.ok ? '' : ' — ' + kb.meldung), 'fehler');
                return;
            }
            rohFeld.value = f.text;
            _melde('Formatiert.', 'ok');
            _geaendert();
        });

        rohFeld.addEventListener('input', function () {
            var kb = klammerbilanz(rohFeld.value);
            var p = jsonPruefen(rohFeld.value);
            if (p.ok) { _melde('JSON ist gültig. ' + kb.meldung, 'ok'); }
            else {
                _melde('Zeile ' + p.zeile + ', Spalte ' + p.spalte + ': '
                    + p.meldung + (kb.ok ? '' : ' — ' + kb.meldung), 'fehler');
            }
            _geaendert();
        });

        typWahl.addEventListener('change', function () {
            zustand.typ = typWahl.value;
            if (zustand.modus === 'komfort') {
                _komfortLesen().then(function (b) {
                    zustand.daten = b.data;
                    _komfortAufbauen();
                });
            }
            _geaendert();
        });

        _zeigeModus();

        return {
            // setze: Blockart und Blockdaten von aussen (Auswahl, Entwurf).
            setze: function (typ, daten) {
                zustand.typ = _s(typ) || 'paragraph';
                zustand.daten = (daten && typeof daten === 'object')
                    ? daten : {};
                typWahl.value = zustand.typ;
                vergleichKasten.hidden = true;
                if (zustand.modus === 'roh') {
                    // Im Rohmodus haelt das Textfeld alle Felder ohnehin -
                    // eine Blindprobe waere gegenstandslos. Der Stand aus
                    // einem frueheren Komfort-Aufbau darf aber nicht
                    // stehenbleiben: er gehoerte zu anderen Daten.
                    zustand.blindeFelder = [];
                    zustand.blindTyp = null;
                    zustand.blindProbe = null;
                    rohFeld.value = JSON.stringify(zustand.daten, null, 2);
                } else {
                    _komfortAufbauen();   // startet die Blindprobe
                }
                _melde('');
            },
            // lies: der aktuelle Stand als Versprechen.
            //
            // BUILD 704: Das Ergebnis traegt zusaetzlich 'bewahrt' und
            // 'nichtBewahrt'. Beide sind IMMER da (im Rohmodus leer), damit
            // der Aufrufer nicht auf Anwesenheit pruefen muss - ein Feld,
            // das mal fehlt und mal nicht, wird irgendwann vergessen.
            lies: function () {
                if (zustand.modus === 'roh') {
                    var p = jsonPruefen(rohFeld.value);
                    return Promise.resolve({
                        type: zustand.typ,
                        data: p.ok ? p.wert : zustand.daten,
                        rohFehler: p.ok ? null : p.meldung,
                        bewahrt: [], nichtBewahrt: []
                    });
                }
                return _komfortLesen().then(function (b) {
                    if (b.nichtBewahrt && b.nichtBewahrt.length) {
                        // GRUNDREGEL 1: Was nicht zurueckgeschrieben werden
                        // konnte, geht beim Speichern verloren - und genau
                        // das muss vor dem Speichern auf der Flaeche stehen.
                        _melde('ACHTUNG: ' + b.nichtBewahrt.length
                            + ' Angabe(n) lassen sich nicht bewahren und gehen '
                            + 'beim Speichern verloren: '
                            + b.nichtBewahrt.map(function (f) {
                                return f.pfad + ' (' + f.grund + ')';
                            }).join('; ') + '. Im Rohmodus nachsehen.',
                            'fehler');
                    }
                    return { type: b.type, data: b.data, rohFehler: null,
                             bewahrt: b.bewahrt || [],
                             nichtBewahrt: b.nichtBewahrt || [] };
                });
            },
            modus: function () { return zustand.modus; },
            aus: function () {
                _komfortAbbauen();
                _leeren(vergleichKasten);
                vergleichKasten.hidden = true;
                _melde('');
            }
        };
    }

    // =====================================================================
    // 3) UMD-Ausgang.
    // =====================================================================
    var API = {
        tiefVergleich: tiefVergleich,
        // Build 704: einzeln nach aussen gegeben, damit die Regression sie
        // ohne Editor.js pruefen kann - eine Pruefung, die erst am gebauten
        // Editor greift, prueft zwei Dinge auf einmal und benennt bei einem
        // Fehlschlag keines davon.
        blindeFelderAus: blindeFelderAus,
        setzeNachPfad: setzeNachPfad,
        jsonPruefen: jsonPruefen,
        klammerbilanz: klammerbilanz,
        formatiere: formatiere,
        klartextAus: klartextAus,
        erzeuge: erzeuge
    };
    if (typeof window !== 'undefined') { window.AIWBausteinEingabe = API; }
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    log('geladen');
})();
