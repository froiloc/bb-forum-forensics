/**
 * management/server/static/cockpit_baustein_platzhalter.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Baustein-Module (W1) — PLATZHALTER-TABELLE, Build 654
 *
 * ZWECK (Ticket 4b032177, mc):
 *   "Im Baustein-Modul wurden Platzhalter verwendet. Diese koennen derzeit nur
 *   haendisch eingepflegt werden. Sie werden nicht getestet oder validiert."
 *   Gewuenscht: die Platzhalter des Bausteintexts in Echtzeit ausweisen, mit
 *   ALLEN Parametern, einer Spalte zur Verifikation und einer Spalte zum
 *   Testen einer Eingabe gegen das Pruefmuster.
 *
 *   Diese Datei ist STUFE 1: lesen, verifizieren, testen. Das bidirektionale
 *   Zurueckschreiben in den Bausteintext ist ein eigenes Ticket
 *   (7c1f2a94-..., Entscheidung mc vom 2026-08-02) - dort stehen auch die
 *   drei Fallen, die es mit sich bringt.
 *
 * WARUM EINE EIGENE DATEI: Projektregel 10 (so modular wie moeglich, jede
 *   Klasse in eine eigene Datei) und das Vorbild cockpit_baustein_vorschau.js.
 *   cockpit_modules.js traegt bereits Maske, Tabelle und Vorschau; ein
 *   vierter Bauteil darin waere der Anfang einer unlesbaren Datei.
 *
 * =========================================================================
 * DIE DREI QUELLEN, UND WARUM KEINE DAVON NEU ERFUNDEN WIRD
 * =========================================================================
 *   (1) DIE ZERLEGUNG kommt aus window.PlaceholderChips.parse
 *       (userinfo/placeholder_chips.js). Dort steht _CHIP_RE - die eine
 *       Wahrheit darueber, was ein Platzhalter IST. Ein zweiter regulaerer
 *       Ausdruck hier waere die Doppelwahrheit, vor der der Kopf jener Datei
 *       warnt: er wuerde beim naechsten Formatzusatz auseinanderlaufen, und
 *       zwar lautlos.
 *
 *   (2) DIE REGELPRUEFUNG kommt aus window.AIWCockpitTemplates.testRule /
 *       .validateRule (cockpit_templates.js, Build 490/497). Dieselben
 *       Funktionen entscheiden in der Sicht 'Platzhalter & Queries', ob eine
 *       Eingabe passt. Waere hier eine zweite Fassung, koennte dieselbe
 *       Eingabe in zwei Masken verschieden beurteilt werden - und ein
 *       Redakteur haette keine Chance zu erkennen, welche recht hat.
 *
 *   (3) DER KATALOG DER PLATZHALTER kommt aus GET /api/templates/placeholders,
 *       der KATALOG DER FORMATREGELN aus GET /api/validation/rules (neu in
 *       Build 654; derselbe Katalog, den der Ermittlerserver unter
 *       /_forensic/validation_rules ausliefert).
 *
 * =========================================================================
 * DAS FUENFTE PLATZHALTERFELD HAT ZWEI FORMEN - DAS IST DER KERN
 * =========================================================================
 *   Bis Build 388 stand dort eine BASE64-KODIERTE REGEX (OP-B6-5). Seit
 *   Build 388 steht dort in der Regel ein symbolischer Verweis 'rule:<name>'
 *   in den Katalog aus config.yaml. BEIDE Formen sind gueltig und kommen im
 *   Bestand nebeneinander vor (userinfo/validation_rules.js resolve()).
 *
 *   Eine Tabelle, die nur die Altform kennt, wuerde jeden modernen Verweis
 *   als "kein gueltiges Base64" anschlagen. Eine Tabelle, die bei der
 *   Mehrzahl der Eintraege falschen Alarm gibt, wird nicht gelesen - und
 *   dann faellt auch der ECHTE Befund nicht mehr auf. Deshalb unterscheidet
 *   musterAus() die beiden Formen ausdruecklich.
 *
 * =========================================================================
 * SECHS BEFUNDE. JEDER IM KLARTEXT, KEINER NUR ALS FARBE
 * =========================================================================
 *   V1  Verdaechtiges Token: etwas sieht aus wie ein Platzhalter, ist aber
 *       keiner ({{m:na me}}, ein Feld zu viel, ein Tippfehler im Typ). HEUTE
 *       FAELLT DAS NIEMANDEM AUF - solcher Text erscheint im fertigen Vermerk
 *       woertlich als "{{m:na me}}". Das ist der wertvollste der sechs.
 *   V2  a:-Platzhalter unbekannt, abgeschaltet oder im Katalog anderen Typs.
 *   V3  m:/o:-Platzhalter im Katalog anderen Typs: {{o:x}} auf einem
 *       Pflichtfeld bedeutet etwas anderes, als der Katalog sagt.
 *   V4  Pruefmuster unbrauchbar: 'rule:'-Verweis ins Leere, kein gueltiges
 *       Base64, oder ein Muster, das sich nicht uebersetzen laesst.
 *   V5  Pruefmuster weicht vom Katalog ab. Kein Fehler - aber meldepflichtig,
 *       denn der Server prueft am Ende gegen den Katalog.
 *   V6  Derselbe Name mehrfach mit UNTERSCHIEDLICHER Vorgabe, Beschreibung
 *       oder Regel. Beim Ausfuellen gewinnt dann eine Fassung, und welche,
 *       sieht man dem Text nicht an.
 *
 * JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging; ausfuehrliche
 *   Kommentare; Kapselung; reine Funktionen einzeln exportiert (vitest);
 *   XSS-sicher ueber textContent (multilingual, UTF-8).
 *
 * OEFFENTLICHE API (window.AIWBausteinPlatzhalter)
 *   -- rein (vitest):
 *   katalogIndex(items)            -- Liste der Platzhalter -> {id: def}
 *   musterAus(feld, regelKatalog)  -- 5. Feld -> {form, muster, quelle, fehler}
 *   verdaechtige(text)             -- Token, die keine Platzhalter sind
 *   zerlege(text, chips)           -- Eintraege je (Typ, Name), verdichtet
 *   pruefe(eintrag, kat, regeln)   -- {stufe, befunde:[{art, text}]}
 *   teste(eintrag, kat, regeln, eingabe) -- {chip, katalog}
 *   -- DOM:
 *   erzeuge(hostEl, opts)          -- {zeige(text, kat, regeln), aus()}
 *
 * Version: v0.8.654 · Build: 654 · 2026-08-02
 * Beleg: Ticket 4b032177; userinfo/placeholder_chips.js:73 (_CHIP_RE);
 *        userinfo/validation_rules.js:33-38 (beide Formen des 5. Feldes);
 *        management/server/static/cockpit_templates.js:315 (testRule).
 */
(function () {
    'use strict';

    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[baustein-platzhalter]');
            console.log.apply(console, a);
        }
    }

    var REGEL_PRAEFIX = 'rule:';

    // Ein Token, das AUSSIEHT wie ein Platzhalter. Bewusst weiter gefasst als
    // _CHIP_RE: alles zwischen '{{' und '}}' ohne '}' dazwischen. Was hier
    // haengenbleibt und von parse() NICHT als Chip erkannt wurde, ist ein
    // Befund - siehe V1.
    var _VERDACHT_RE = /\{\{([^}]*)\}\}/g;

    // Die drei Typkuerzel in Lang- und Kurzform (Spiegel von
    // placeholder_chips.js _normalizeType). Sie stehen hier NUR fuer die
    // Verdachtspruefung; die Zerlegung selbst macht weiterhin parse().
    var _TYPEN = ['a', 'auto', 'm', 'mandatory', 'o', 'optional'];

    // =====================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — vitest.
    // =====================================================================

    function _s(v) { return (v === undefined || v === null) ? '' : String(v); }

    function typLabel(typ) {
        switch (typ) {
            case 'a': return 'automatisch (a)';
            case 'm': return 'verpflichtend (m)';
            case 'o': return 'optional (o)';
            default:  return _s(typ);
        }
    }

    // katalogIndex: aus der Antwort von /api/templates/placeholders einen
    // Index id -> Definition. ALLE Typen, nicht nur m/o - der a-Typ ist es,
    // dessen Existenz hier geprueft werden soll.
    function katalogIndex(items) {
        var idx = {};
        var liste = Array.isArray(items)
            ? items
            : (items && Array.isArray(items.placeholders) ? items.placeholders : []);
        liste.forEach(function (it) {
            if (!it || it.id === undefined || it.id === null) { return; }
            idx[String(it.id)] = it;
        });
        return idx;
    }

    // _b64: Base64 -> Unicode. ZEICHENGLEICH zu validation_rules.js:88-98
    // und placeholder_wizard.js:141 - dieselbe Umleitung ueber
    // decodeURIComponent, damit UTF-8-Muster (das Forum ist multilingual!)
    // nicht an atob() zerbrechen.
    function _b64(s) {
        try {
            var roh = (typeof atob === 'function')
                ? atob(s)
                : Buffer.from(s, 'base64').toString('binary');
            return decodeURIComponent(roh.split('').map(function (c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
        } catch (e) { return null; }
    }

    // musterAus: das fuenfte Platzhalterfeld auswerten.
    // Rueckgabe:
    //   { form: ''|'regel'|'base64', muster: string|null, quelle: string,
    //     hinweis: string, fehler: string|null }
    // form '' heisst: kein fuenftes Feld, also keine Regel am Token. Das ist
    // kein Fehler - viele Platzhalter brauchen keine.
    function musterAus(feld, regelKatalog) {
        var f = _s(feld);
        if (f === '') {
            return { form: '', muster: null, quelle: '', hinweis: '',
                     fehler: null };
        }
        if (f.indexOf(REGEL_PRAEFIX) === 0) {
            var name = f.slice(REGEL_PRAEFIX.length);
            var kat = regelKatalog || {};
            var spec = kat[name];
            if (!spec) {
                return {
                    form: 'regel', muster: null, quelle: name, hinweis: '',
                    // GRUNDREGEL 1: nicht still durchwinken. Der Wortlaut ist
                    // an core/validation_rules.py:validate angelehnt, damit
                    // Maske und Server dasselbe sagen.
                    fehler: 'Der Baustein verweist auf die Formatregel "'
                        + name + '", die es in der Serverkonfiguration '
                        + '(validation.rules) nicht gibt. Der Wert kann nicht '
                        + 'geprueft werden.'
                };
            }
            return { form: 'regel', muster: _s(spec.pattern), quelle: name,
                     hinweis: _s(spec.hint), fehler: null };
        }
        var dek = _b64(f);
        if (dek === null) {
            return { form: 'base64', muster: null, quelle: f, hinweis: '',
                     fehler: 'Das fuenfte Feld ist weder ein Verweis '
                         + '("rule:name") noch gueltiges Base64.' };
        }
        return { form: 'base64', muster: dek, quelle: f, hinweis: '',
                 fehler: null };
    }

    // _regexPruefen: laesst sich das Muster als JavaScript-RegExp bauen?
    function _regexPruefen(muster) {
        if (muster === null || muster === undefined) { return null; }
        try { new RegExp(String(muster)); return null; }
        catch (e) {
            return 'Das Pruefmuster laesst sich nicht uebersetzen: '
                + (e && e.message ? e.message : String(e));
        }
    }

    // verdaechtige: Token, die wie Platzhalter aussehen, aber keine sind.
    // ------------------------------------------------------------------
    // DER WERTVOLLSTE BEFUND DIESER TABELLE. Ein vertipptes Token wird von
    // _CHIP_RE schlicht nicht erkannt - es bleibt woertlicher Text und
    // erscheint SO im fertigen Vermerk. Es faellt heute niemandem auf, weil
    // es keinen Fehler ausloest, sondern nur nichts tut.
    //
    // 'gueltige' ist die Menge der Rohtoken, die parse() als Chip erkannt
    // hat; alles andere zwischen '{{' und '}}' ist verdaechtig.
    function verdaechtige(text, gueltige) {
        var t = _s(text);
        var bekannt = {};
        (gueltige || []).forEach(function (r) { bekannt[r] = true; });
        var raus = [];
        var re = new RegExp(_VERDACHT_RE.source, 'g');
        var m;
        while ((m = re.exec(t)) !== null) {
            if (bekannt[m[0]]) { continue; }
            var inhalt = m[1];
            var grund;
            var dp = inhalt.indexOf(':');
            var typ = dp >= 0 ? inhalt.slice(0, dp) : '';
            if (dp < 0) {
                grund = 'Kein Typkuerzel vor dem Doppelpunkt.';
            } else if (_TYPEN.indexOf(typ) < 0) {
                grund = 'Unbekanntes Typkuerzel "' + typ + '" (erlaubt: a, m, '
                    + 'o bzw. auto, mandatory, optional).';
            } else if ((inhalt.match(/\|/g) || []).length > 3) {
                grund = 'Zu viele durch "|" getrennte Felder (hoechstens '
                    + 'Vorgabe, Beschreibung und Pruefmuster).';
            } else {
                grund = 'Der Name enthaelt unzulaessige Zeichen (erlaubt: '
                    + 'A-Z a-z 0-9 . _ -).';
            }
            raus.push({ roh: m[0], grund: grund });
        }
        return raus;
    }

    // zerlege: den Bausteintext in Tabelleneintraege.
    // ------------------------------------------------------------------
    // Verdichtet auf (Typ, Name): derselbe Platzhalter kann mehrfach im Text
    // stehen. 'vorkommen' zaehlt sie, 'varianten' sammelt die VERSCHIEDENEN
    // Auspraegungen - daraus entsteht V6.
    //
    // chips ist window.PlaceholderChips (injizierbar fuer die Pruefung).
    function zerlege(text, chips) {
        var pc = chips || (typeof window !== 'undefined'
            ? window.PlaceholderChips : null);
        if (!pc || typeof pc.parse !== 'function') { return null; }

        var segmente = pc.parse(_s(text)) || [];
        var reihenfolge = [];
        var nach = {};
        var rohtoken = [];

        segmente.forEach(function (seg) {
            if (!seg || seg.type !== 'chip') { return; }
            rohtoken.push(seg.raw);
            var schluessel = seg.chipType + '\u0000' + seg.name;
            var e = nach[schluessel];
            if (!e) {
                e = {
                    typ: seg.chipType,
                    name: seg.name,
                    vorgabe: _s(seg.defaultVal),
                    beschreibung: _s(seg.description),
                    regelfeld: seg.b64regex === null ? '' : _s(seg.b64regex),
                    vorkommen: 0,
                    varianten: [],
                    rohtoken: []
                };
                nach[schluessel] = e;
                reihenfolge.push(e);
            }
            e.vorkommen += 1;
            e.rohtoken.push(seg.raw);
            var v = _s(seg.defaultVal) + '\u0001' + _s(seg.description)
                + '\u0001' + (seg.b64regex === null ? '' : _s(seg.b64regex));
            if (e.varianten.indexOf(v) < 0) { e.varianten.push(v); }
        });

        return { eintraege: reihenfolge, rohtoken: rohtoken,
                 verdaechtige: verdaechtige(text, rohtoken) };
    }

    // pruefe: die Befunde zu EINEM Eintrag.
    // stufe: 'ok' | 'hinweis' | 'fehler'. Ein Fehler bedeutet: so wie es
    // dasteht, kann es beim Ausfuellen nicht funktionieren. Ein Hinweis
    // bedeutet: es funktioniert, aber jemand sollte hinsehen.
    function pruefe(eintrag, katalog, regelKatalog) {
        var befunde = [];
        if (!eintrag) { return { stufe: 'ok', befunde: befunde }; }
        var kat = katalog || {};
        var def = kat[eintrag.name] || null;

        // --- V2 / V3: Abgleich mit dem Platzhalter-Katalog ---------------
        if (eintrag.typ === 'a') {
            if (!def) {
                befunde.push({ art: 'fehler', kennung: 'V2', text:
                    'Kein Platzhalter mit der Kennung "' + eintrag.name
                    + '" im Katalog. Ein automatischer Platzhalter ohne '
                    + 'Abfrage bleibt im Vermerk leer.' });
            } else {
                if (String(def.type) !== 'a') {
                    befunde.push({ art: 'fehler', kennung: 'V2', text:
                        'Im Katalog ist "' + eintrag.name + '" vom Typ '
                        + typLabel(def.type) + ', hier steht er als '
                        + 'automatischer Platzhalter.' });
                }
                if (def.is_active === 0) {
                    befunde.push({ art: 'fehler', kennung: 'V2', text:
                        'Der Platzhalter "' + eintrag.name + '" ist im '
                        + 'Katalog abgeschaltet und wird nicht aufgeloest.' });
                }
            }
        } else if (def && String(def.type) === 'a') {
            befunde.push({ art: 'fehler', kennung: 'V3', text:
                'Im Katalog ist "' + eintrag.name + '" ein automatischer '
                + 'Platzhalter; hier wird er als Eingabefeld gefuehrt.' });
        } else if (def && String(def.type) !== eintrag.typ) {
            befunde.push({ art: 'hinweis', kennung: 'V3', text:
                'Im Katalog ist "' + eintrag.name + '" ' + typLabel(def.type)
                + ', hier ' + typLabel(eintrag.typ) + '. Beim Ausfuellen '
                + 'entscheidet der Katalog darueber, ob eine Eingabe '
                + 'erzwungen wird.' });
        }

        // --- V4: das Pruefmuster am Token --------------------------------
        var m = musterAus(eintrag.regelfeld, regelKatalog);
        if (m.fehler) {
            befunde.push({ art: 'fehler', kennung: 'V4', text: m.fehler });
        } else {
            var re = _regexPruefen(m.muster);
            if (re) {
                befunde.push({ art: 'fehler', kennung: 'V4', text: re });
            }
        }

        // --- V5: Widerspruch zwischen Token und Katalog ------------------
        // Nur wenn BEIDE eine Regel tragen und beide brauchbar sind. Der
        // Server prueft am Ende gegen den Katalog; ein Redakteur, der die
        // Regel am Token pflegt, arbeitet dann ins Leere.
        if (def && m.form !== '' && !m.fehler
                && _s(def.validation) !== ''
                && String(def.validation_type || '') === 'regex'
                && _s(def.validation) !== _s(m.muster)) {
            befunde.push({ art: 'hinweis', kennung: 'V5', text:
                'Das Pruefmuster am Platzhalter weicht vom Katalog ab. '
                + 'Am Token: ' + _s(m.muster) + ' — im Katalog: '
                + _s(def.validation) + '. Beim Ausfuellen gilt der Katalog.' });
        }

        // --- V6: derselbe Name mit verschiedenen Angaben ------------------
        if (eintrag.varianten && eintrag.varianten.length > 1) {
            befunde.push({ art: 'fehler', kennung: 'V6', text:
                'Der Platzhalter "' + eintrag.name + '" steht '
                + eintrag.vorkommen + '-mal im Text, aber mit '
                + eintrag.varianten.length + ' verschiedenen Angaben '
                + '(Vorgabe, Beschreibung oder Pruefmuster). Beim Ausfuellen '
                + 'gewinnt eine Fassung, und welche, sieht man dem Text '
                + 'nicht an.' });
        }

        var stufe = 'ok';
        befunde.forEach(function (b) {
            if (b.art === 'fehler') { stufe = 'fehler'; }
            else if (stufe !== 'fehler') { stufe = 'hinweis'; }
        });
        return { stufe: stufe, befunde: befunde };
    }

    // teste: eine Beispieleingabe gegen BEIDE Regeln.
    // ------------------------------------------------------------------
    // Rueckgabe { chip, katalog } - je { geprueft, passt, fehler, quelle }
    // oder null, wenn es dort nichts zu pruefen gibt.
    //
    // WARUM BEIDE: Weichen sie voneinander ab, ist genau das der Befund, den
    // ein Redakteur heute nicht sehen kann. Eine gemittelte Antwort waere
    // eine Antwort, die keine der beiden Wahrheiten wiedergibt.
    function teste(eintrag, katalog, regelKatalog, eingabe, tpl) {
        var raus = { chip: null, katalog: null };
        if (!eintrag || eintrag.typ === 'a') { return raus; }
        var werkzeug = tpl || (typeof window !== 'undefined'
            ? window.AIWCockpitTemplates : null);
        var wert = _s(eingabe);

        // (a) die Regel am Token selbst.
        var m = musterAus(eintrag.regelfeld, regelKatalog);
        if (m.form !== '') {
            if (m.fehler) {
                raus.chip = { geprueft: false, passt: null, fehler: m.fehler,
                              quelle: 'Platzhalter im Text' };
            } else {
                var re = _regexPruefen(m.muster);
                if (re) {
                    raus.chip = { geprueft: false, passt: null, fehler: re,
                                  quelle: 'Platzhalter im Text' };
                } else {
                    raus.chip = {
                        geprueft: true,
                        passt: new RegExp(String(m.muster)).test(wert),
                        fehler: null,
                        quelle: (m.form === 'regel')
                            ? ('Formatregel "' + m.quelle + '"')
                            : 'Platzhalter im Text'
                    };
                }
            }
        }

        // (b) die Regel aus dem Platzhalter-Katalog. Sie laeuft ueber
        // AIWCockpitTemplates.testRule - dieselbe Funktion, die in der Sicht
        // 'Platzhalter & Queries' urteilt, samt validation_ci (Build 497).
        var def = (katalog || {})[eintrag.name] || null;
        if (def && _s(def.validation) !== '' && _s(def.validation_type) !== '') {
            if (!werkzeug || typeof werkzeug.testRule !== 'function') {
                raus.katalog = { geprueft: false, passt: null,
                    fehler: 'Das Pruefwerkzeug (cockpit_templates.js) ist '
                        + 'nicht geladen; gegen den Katalog wird nicht '
                        + 'geprueft.',
                    quelle: 'Katalog' };
            } else {
                var erg = werkzeug.testRule(def.validation_type,
                                            def.validation, wert,
                                            def.validation_ci ? 1 : 0);
                raus.katalog = {
                    geprueft: !!erg.ok,
                    passt: erg.ok ? erg.match : null,
                    fehler: erg.ok ? null : erg.error,
                    quelle: 'Katalog (' + _s(def.validation_type) + ')'
                };
            }
        }
        return raus;
    }

    // =====================================================================
    // 2) DOM.
    // =====================================================================

    function _leeren(el) {
        while (el && el.firstChild) { el.removeChild(el.firstChild); }
    }

    function _zelle(doc, text, klasse) {
        var td = doc.createElement('td');
        if (klasse) { td.className = klasse; }
        td.textContent = _s(text);
        return td;
    }

    // Die Spalten der Tabelle. Bewusst KEINE Tabulator-Tabelle: sie traegt
    // Eingabefelder je Zeile, wird bei jedem Tastendruck (entprellt) neu
    // aufgebaut und hat hoechstens eine Handvoll Zeilen. Tabulator waere hier
    // Aufwand ohne Gewinn - und der Bedienzustand einer Tabelle, die sich
    // beim Tippen aendert, laesst sich ohnehin nicht sinnvoll sichern.
    var _KOPF = ['Typ', 'Name', 'Vorgabe', 'Beschreibung', 'Prüfmuster',
                 'Vorkommen', 'Verifikation', 'Testeingabe'];

    function erzeuge(hostEl, opts) {
        opts = opts || {};
        var doc = (hostEl && hostEl.ownerDocument) || document;
        var zustand = { text: null, kat: null, regeln: null,
                        eingaben: {} };   // Testeingaben ueberleben Neuaufbau

        var meldung = doc.createElement('p');
        meldung.className = 'aiw-mod-ph-meldung';
        hostEl.appendChild(meldung);

        var rumpf = doc.createElement('div');
        rumpf.className = 'aiw-mod-ph-rumpf';
        hostEl.appendChild(rumpf);

        function _melde(text, warnung) {
            meldung.textContent = _s(text);
            meldung.classList.toggle('ist-warnung', !!warnung);
        }

        function _befundZelle(erg) {
            var td = doc.createElement('td');
            td.className = 'aiw-mod-ph-befund ist-' + erg.stufe;
            if (!erg.befunde.length) {
                td.textContent = 'geprüft, ohne Beanstandung';
                return td;
            }
            var ul = doc.createElement('ul');
            erg.befunde.forEach(function (b) {
                var li = doc.createElement('li');
                li.className = 'ist-' + b.art;
                // Die Kennung steht MIT DABEI: so laesst sich ein Befund im
                // Kopfkommentar dieser Datei nachschlagen und im Gespraech
                // benennen, ohne den ganzen Satz zu zitieren.
                li.textContent = b.kennung + ': ' + b.text;
                ul.appendChild(li);
            });
            td.appendChild(ul);
            return td;
        }

        function _urteilText(erg) {
            if (!erg) { return ''; }
            if (!erg.geprueft) { return erg.fehler || 'nicht prüfbar'; }
            return (erg.passt ? 'passt' : 'passt NICHT') + ' — ' + erg.quelle;
        }

        function _testZelle(eintrag) {
            var td = doc.createElement('td');
            td.className = 'aiw-mod-ph-test';
            if (eintrag.typ === 'a') {
                // Ein automatischer Platzhalter wird nicht eingegeben,
                // sondern abgefragt. Ein Testfeld waere hier eine Einladung
                // zu einem Missverstaendnis.
                td.textContent = '— wird abgefragt, nicht eingegeben —';
                td.classList.add('ist-leer');
                return td;
            }
            var feld = doc.createElement('input');
            feld.type = 'text';
            feld.className = 'aiw-mod-ph-eingabe';
            feld.setAttribute('data-name', eintrag.typ + ':' + eintrag.name);
            feld.setAttribute('aria-label',
                'Testeingabe für ' + eintrag.name);
            feld.setAttribute('data-hilfe-id', 'modules.bedienung.phtest');
            feld.value = _s(zustand.eingaben[eintrag.typ + ':' + eintrag.name]);
            var urteil = doc.createElement('div');
            urteil.className = 'aiw-mod-ph-urteil';

            function _bewerte() {
                zustand.eingaben[eintrag.typ + ':' + eintrag.name] = feld.value;
                _leeren(urteil);
                if (feld.value === '') {
                    urteil.textContent = '';
                    urteil.className = 'aiw-mod-ph-urteil';
                    return;
                }
                var t = teste(eintrag, zustand.kat, zustand.regeln,
                              feld.value, opts.tpl);
                if (!t.chip && !t.katalog) {
                    urteil.textContent = 'keine Prüfregel hinterlegt';
                    urteil.className = 'aiw-mod-ph-urteil ist-leer';
                    return;
                }
                var alleGut = true;
                [t.chip, t.katalog].forEach(function (erg) {
                    if (!erg) { return; }
                    if (!erg.geprueft || erg.passt !== true) { alleGut = false; }
                    var z = doc.createElement('div');
                    z.className = 'ist-'
                        + (!erg.geprueft ? 'fehler'
                                         : (erg.passt ? 'ok' : 'nein'));
                    z.textContent = _urteilText(erg);
                    urteil.appendChild(z);
                });
                // Weichen die beiden Urteile voneinander ab, wird das
                // AUSDRUECKLICH gesagt. Genau dieser Fall ist heute
                // unsichtbar.
                if (t.chip && t.katalog && t.chip.geprueft
                        && t.katalog.geprueft
                        && t.chip.passt !== t.katalog.passt) {
                    var w = doc.createElement('div');
                    w.className = 'ist-fehler';
                    w.textContent = 'ACHTUNG: Platzhalter im Text und Katalog '
                        + 'urteilen VERSCHIEDEN. Beim Ausfüllen gilt der '
                        + 'Katalog.';
                    urteil.appendChild(w);
                }
                urteil.classList.toggle('ist-gut', alleGut);
            }

            feld.addEventListener('input', _bewerte);
            td.appendChild(feld);
            td.appendChild(urteil);
            if (feld.value !== '') { _bewerte(); }
            return td;
        }

        function _zeichne() {
            _leeren(rumpf);
            var pc = opts.chips || (typeof window !== 'undefined'
                ? window.PlaceholderChips : null);
            if (!pc || typeof pc.parse !== 'function') {
                _melde('Platzhalter-Zerlegung nicht geladen '
                    + '(placeholder_chips.js) — die Tabelle bleibt leer.',
                    true);
                return;
            }
            var z = zerlege(zustand.text, pc);
            if (!z) { return; }

            // Die verdaechtigen Token ZUERST: sie sind der Befund, den heute
            // niemand sieht, und sie stehen nicht in der Tabelle, weil sie
            // gerade KEINE Platzhalter sind.
            if (z.verdaechtige.length) {
                var warn = doc.createElement('ul');
                warn.className = 'aiw-mod-ph-verdacht';
                z.verdaechtige.forEach(function (v) {
                    var li = doc.createElement('li');
                    li.textContent = 'V1: "' + v.roh + '" sieht aus wie ein '
                        + 'Platzhalter, ist aber keiner und erscheint '
                        + 'wörtlich im Vermerk. ' + v.grund;
                    warn.appendChild(li);
                });
                rumpf.appendChild(warn);
            }

            if (!z.eintraege.length) {
                _melde(z.verdaechtige.length
                    ? 'Kein gültiger Platzhalter im Bausteintext.'
                    : 'Keine Platzhalter im Bausteintext.',
                    z.verdaechtige.length > 0);
                return;
            }

            var fehler = 0, hinweise = 0;
            var tab = doc.createElement('table');
            tab.className = 'aiw-mod-ph-tabelle';
            var thead = doc.createElement('thead');
            var trk = doc.createElement('tr');
            _KOPF.forEach(function (t) {
                var th = doc.createElement('th');
                th.textContent = t;
                trk.appendChild(th);
            });
            thead.appendChild(trk);
            tab.appendChild(thead);

            var tbody = doc.createElement('tbody');
            z.eintraege.forEach(function (e) {
                var erg = pruefe(e, zustand.kat, zustand.regeln);
                if (erg.stufe === 'fehler') { fehler += 1; }
                else if (erg.stufe === 'hinweis') { hinweise += 1; }

                var tr = doc.createElement('tr');
                tr.className = 'ist-' + erg.stufe;
                tr.setAttribute('data-name', e.typ + ':' + e.name);
                tr.appendChild(_zelle(doc, typLabel(e.typ), 'aiw-mod-ph-typ'));
                tr.appendChild(_zelle(doc, e.name, 'aiw-mod-ph-name'));
                tr.appendChild(_zelle(doc, e.vorgabe || '—'));
                tr.appendChild(_zelle(doc, e.beschreibung || '—'));

                // Das Pruefmuster wird DEKODIERT angezeigt. Base64 im
                // Klartext hilft niemandem beim Nachsehen, ob das Muster
                // stimmt - und genau darum geht es hier.
                var m = musterAus(e.regelfeld, zustand.regeln);
                var mtext;
                if (m.form === '') { mtext = '—'; }
                else if (m.fehler) { mtext = m.quelle + ' (unbrauchbar)'; }
                else if (m.form === 'regel') {
                    mtext = 'rule:' + m.quelle + ' → ' + m.muster;
                } else { mtext = m.muster; }
                tr.appendChild(_zelle(doc, mtext, 'aiw-mod-ph-muster'));

                tr.appendChild(_zelle(doc, String(e.vorkommen),
                                      'aiw-mod-ph-zahl'));
                tr.appendChild(_befundZelle(erg));
                tr.appendChild(_testZelle(e));
                tbody.appendChild(tr);
            });
            tab.appendChild(tbody);
            rumpf.appendChild(tab);

            // DIE ZAHL STEHT IMMER DA, mit dem Substantiv dieser Sicht.
            var satz = z.eintraege.length + ' Platzhalter';
            if (fehler) { satz += ', ' + fehler + ' mit Fehler'; }
            if (hinweise) { satz += ', ' + hinweise + ' mit Hinweis'; }
            if (!zustand.kat) {
                satz += '. Der Platzhalter-Katalog ist NICHT geladen — '
                    + 'gegen ihn wird nicht geprüft.';
            }
            _melde(satz, fehler > 0 || !zustand.kat);
        }

        return {
            // zeige: neuer Text und/oder neue Kataloge.
            zeige: function (text, kat, regeln) {
                zustand.text = _s(text);
                if (kat !== undefined) { zustand.kat = kat; }
                if (regeln !== undefined) { zustand.regeln = regeln; }
                _zeichne();
            },
            // kataloge: nur die Kataloge nachreichen (sie kommen ueber das
            // Netz und treffen spaeter ein als der erste Text).
            kataloge: function (kat, regeln) {
                if (kat !== undefined) { zustand.kat = kat; }
                if (regeln !== undefined) { zustand.regeln = regeln; }
                if (zustand.text !== null) { _zeichne(); }
            },
            aus: function () {
                _leeren(rumpf);
                _melde('');
            }
        };
    }

    // =====================================================================
    // 3) UMD-Ausgang (Browser + vitest).
    // =====================================================================
    var API = {
        typLabel: typLabel,
        katalogIndex: katalogIndex,
        musterAus: musterAus,
        verdaechtige: verdaechtige,
        zerlege: zerlege,
        pruefe: pruefe,
        teste: teste,
        erzeuge: erzeuge
    };
    if (typeof window !== 'undefined') { window.AIWBausteinPlatzhalter = API; }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = API;
    }
    log('geladen');
})();
