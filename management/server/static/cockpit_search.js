// =============================================================================
// management/server/static/cockpit_search.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Volltextsuche
// =============================================================================
// Zweck (AP-3E / Idee 38, Frontend zu den Builds 560-562, Instanz B):
//   Die falluebergreifende Volltextsuche nach Modell B. Sie beantwortet EINE
//   Frage: "Ist dieser Begriff — meist ein Nickname — schon irgendwo in der
//   Dienststelle aufgefallen?"
//
// DIE WICHTIGSTE AUSSAGE DIESER DATEI:
//   STUFE 1 ZEIGT KEINEN TEXT. Fall, Trefferzahl, Art, Zeitraum und
//   Urheber:innen — mehr nicht. Das ist kein Sparen an der Anzeige, sondern
//   der Kern des Freigabemodells: der Arbeitsstand eines FREMDEN Verfahrens
//   (Klarnamen, Opferangaben, Bewertungen von Kolleginnen) wird erst nach
//   einer belegten Entscheidung sichtbar. Wer hier Text einbaut, hebt das
//   Modell auf.
//
// Datenform POST /api/fulltext/lage (FulltextSearchService.lage):
//   { stufe, begriff, modus, modus_klartext, zweck_code, zweck_klartext,
//     befund, befund_klartext, gekappt, grenze, treffer_gesamt,
//     faelle: [ {subject_id, treffer_gesamt, nach_fassung:{aktuell,
//                ueberholt, zurueckgenommen}, arten:[{code,label,count}],
//                urheber:[{kuerzel,count}], von_ts, bis_ts, ohne_ts,
//                sichtbarkeit:{erlaubt, grund, klartext, ...}} ],
//     indexstand: {...}, audit_seq }
//   Bei einem Fehler reicht loadSearch {error: <text>} durch.
//
// VIER ENTSCHEIDUNGEN, DIE MAN DER SICHT ANSEHEN MUSS:
//
//   (1) DER INDEXSTAND STEHT OBEN, NICHT ALS FUSSNOTE. Ein Index, der drei
//       Tage alt ist, liefert eine Trefferlage von vor drei Tagen. Steht das
//       unten klein, liest es niemand — und ein Leerbefund saehe aus wie
//       'es gibt nichts'. Ist der Stand NICHT belastbar, wird der Kopf
//       hervorgehoben (aiw-search-stand--warn).
//
//   (2) DIE DREI FASSUNGEN WERDEN GETRENNT ANGEZEIGT und NIE addiert.
//       'aktuell' ist Arbeitsstand, 'ueberholt'/'zurueckgenommen' sind
//       Historie. Eine Summe behauptete eine Trefferlage, die es nicht gibt.
//       Gerade der ZURUECKGENOMMENE Befund ist fuer den Kreuzbezug wertvoll
//       ("die Kollegin hat das schon geprueft und verworfen").
//
//   (3) DIE ZWECKANGABE IST EIN PFLICHTFELD UND EINE AUSWAHLLISTE. Ohne sie
//       wird nicht gesucht (Entscheidung mc 2026-07-26, E-3). Der ANTEIL von
//       'sonstiges' wird als Kennzahl angezeigt: steigt er, FEHLT EIN CODE —
//       dann wird die Liste ergaenzt, nicht der Sammelcode ausgeweitet.
//
//   (4) EINE SPERRE IST KEIN FEHLER, SONDERN EIN WEG. Bei einem fremden Fall
//       steht 'Inhalt gesperrt' MIT dem Knopf, der die begruendungspflichtige
//       Anfrage ausloest. Eine blosse Fehlermeldung liesse die Ermittlerin im
//       Ungewissen darueber, dass ihr dieser Schritt offensteht.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG).
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen fassen NIE das DOM an;
//   UMD-Ausgang -> vitest testet den ECHTEN Code. Alle Texte ueber
//   textContent (kein innerHTML) — der Bestand ist multilingual und enthaelt
//   von Beschuldigten geschriebene Zeichenfolgen.
//
// Version: v0.8.563 · Build: 563 · 2026-07-26
// =============================================================================

(function () {
    'use strict';

    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var a = Array.prototype.slice.call(arguments);
        a.unshift('[cockpit_search]');
        // eslint-disable-next-line no-console
        console.log.apply(console, a);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM). Genau diese testet vitest.
    // =========================================================================

    // fmtTs: Unix-Sekunden -> 'YYYY-MM-DD'. null/0 -> '—'.
    // KEINE Uhrzeit: die Trefferlage nennt einen ZEITRAUM, und eine
    // Minutenangabe suggerierte eine Genauigkeit, die die Quelldaten nicht
    // durchgaengig haben (nicht jede Spalte fuehrt ueberhaupt einen Stempel).
    function fmtTs(ts) {
        if (ts === null || ts === undefined || ts === '') { return '—'; }
        var n = Number(ts);
        if (!isFinite(n) || n <= 0) { return '—'; }
        var d = new Date(n * 1000);
        function p2(x) { return (x < 10 ? '0' : '') + x; }
        return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-'
            + p2(d.getDate());
    }

    // zeitraumText: der Zeitraum EINES Falls — samt der Zahl der Saetze OHNE
    // Zeitstempel. Die wegzulassen liesse den Zeitraum vollstaendiger
    // aussehen, als er ist (Grundregel 1).
    function zeitraumText(fall) {
        if (!fall) { return '—'; }
        var von = fall.von_ts, bis = fall.bis_ts;
        var ohne = Number(fall.ohne_ts || 0);
        var txt;
        if (von === null || von === undefined) {
            txt = (ohne > 0) ? 'kein Zeitpunkt erfasst' : '—';
        } else if (von === bis) {
            txt = fmtTs(von);
        } else {
            txt = fmtTs(von) + ' bis ' + fmtTs(bis);
        }
        if (ohne > 0 && von !== null && von !== undefined) {
            txt += ' (' + ohne + ' ohne Zeitpunkt)';
        }
        return txt;
    }

    // fassungText: die drei Zustaende NEBENEINANDER, nie summiert.
    // Nullwerte werden weggelassen, damit die Zeile lesbar bleibt — aber
    // 'aktuell' steht IMMER, auch bei 0: 'ueberholt: 2' allein liesse offen,
    // ob es daneben noch gueltige Treffer gibt.
    function fassungText(nachFassung) {
        var f = nachFassung || {};
        var teile = ['aktuell: ' + Number(f.aktuell || 0)];
        if (Number(f.ueberholt || 0) > 0) {
            teile.push('überholt: ' + Number(f.ueberholt));
        }
        if (Number(f.zurueckgenommen || 0) > 0) {
            teile.push('zurückgenommen: ' + Number(f.zurueckgenommen));
        }
        return teile.join(' · ');
    }

    // artenText: die Trefferarten eines Falls, haeufigste zuerst.
    function artenText(arten) {
        if (!arten || !arten.length) { return '—'; }
        return arten.map(function (a) {
            return (a.label || a.code) + ' (' + Number(a.count || 0) + ')';
        }).join(', ');
    }

    // urheberText: MIT WEM man darueber redet — der praktische Kern von
    // Stufe 1. In den meisten Faellen braucht die Suchende nicht den Text der
    // Kollegin, sondern die Kollegin.
    function urheberText(urheber) {
        if (!urheber || !urheber.length) { return '—'; }
        return urheber.map(function (u) {
            return u.kuerzel + ' (' + Number(u.count || 0) + ')';
        }).join(', ');
    }

    // indexstandText: der Stand in EINEM Satz, fuer den Kopf der Sicht.
    // Der Server liefert bereits einen 'hinweis'; hier kommt nur der
    // Zeitpunkt davor, damit beides in einer Zeile steht.
    function indexstandText(stand) {
        if (!stand) { return 'Indexstand unbekannt.'; }
        var wann = (stand.indexzeitpunkt)
            ? ('Index vom ' + fmtTs(stand.indexzeitpunkt))
            : 'Index noch nie aufgebaut';
        return wann + ' — ' + (stand.hinweis || '');
    }

    // standIstWarnung: soll der Kopf hervorgehoben werden?
    // Eigene Funktion, damit die Regel an EINER Stelle steht und der Test sie
    // fassen kann: gewarnt wird, sobald der Stand nicht belastbar ist.
    function standIstWarnung(stand) {
        return !!stand && stand.belastbar !== true;
    }

    // sichtbarkeitsKnopf: welcher Knopf gehoert in die Zeile?
    // 'inhalt'   — der Inhalt ist zugaenglich (eigener Fall oder Freigabe).
    // 'anfragen' — gesperrt; die begruendungspflichtige Anfrage steht offen.
    // 'keiner'   — ohne Handelnden gibt es nichts anzubieten.
    function sichtbarkeitsKnopf(sicht) {
        if (!sicht) { return 'keiner'; }
        if (sicht.erlaubt === true) { return 'inhalt'; }
        if (sicht.grund === 'gesperrt') { return 'anfragen'; }
        return 'keiner';
    }

    // sonstigesAnteil: die Kennzahl aus E-3. Anteil der Abfragen/Freigaben mit
    // dem Sammelcode, gerundet auf ganze Prozent.
    // STEIGT ER, FEHLT EIN CODE — die Liste wird dann ERGAENZT, nicht der
    // Sammelcode ausgeweitet. Ohne Grundgesamtheit gibt es keinen Anteil und
    // ausdruecklich NICHT '0 %': das waere eine Aussage, wo keine Daten sind.
    function sonstigesAnteil(eintraege) {
        var liste = eintraege || [];
        if (!liste.length) { return null; }
        var n = 0;
        for (var i = 0; i < liste.length; i++) {
            if (liste[i] && liste[i].zweck_code === 'sonstiges') { n++; }
        }
        return Math.round((n / liste.length) * 100);
    }

    // verifikationText: warum steht bei diesem Treffer kein Text?
    // Der Server liefert den Klartext mit; hier ist nur der Rueckfall, damit
    // ein unbekannter Befund NICHT als leere Zelle erscheint.
    function verifikationText(treffer) {
        if (!treffer) { return '—'; }
        if (treffer.verifikation_klartext) {
            return treffer.verifikation_klartext;
        }
        return 'Verifikationsbefund unbekannt (' +
            (treffer.verifikation || 'ohne Angabe') + ')';
    }

    // gekapptHinweis: wurde die Trefferliste an der Grenze abgeschnitten?
    // KEINE STILLE KAPPUNG (Grundregel 1) — eine Trefferlage, die unbemerkt
    // bei N aufhoert, ist eine falsche Trefferlage.
    function gekapptHinweis(data) {
        if (!data || !data.gekappt) { return null; }
        return 'Die Trefferliste wurde bei ' + Number(data.grenze || 0)
            + ' Treffern abgeschnitten. Die angezeigte Lage ist damit '
            + 'UNVOLLSTAENDIG — bitte den Suchbegriff verengen.';
    }

    // zweckBrauchtFreitext: bei welchem Code ist der Freitext Pflicht?
    // Der Katalog kommt aus der DATENBANK (GET /api/fulltext/zwecke), damit
    // die Maske genau das anbietet, was der Fremdschluessel auch annimmt.
    function zweckBrauchtFreitext(zwecke, code) {
        var liste = zwecke || [];
        for (var i = 0; i < liste.length; i++) {
            if (liste[i] && liste[i].code === code) {
                return liste[i].freitext_pflicht === true;
            }
        }
        return false;
    }

    // eingabeFehler: liefert den Grund, warum NICHT gesucht werden kann —
    // oder null. Die Pruefung sitzt AUCH im Server (dort hart); hier steht
    // sie nur, damit die Ermittlerin den Grund SOFORT sieht und nicht erst
    // nach einer Antwort. Sie ersetzt die serverseitige NICHT.
    function eingabeFehler(zustand, zwecke) {
        var z = zustand || {};
        if (!z.begriff || !String(z.begriff).trim()) {
            return 'Bitte einen Suchbegriff eingeben.';
        }
        if (!z.zweck_code) {
            return 'Die Zweckangabe ist bei jeder Abfrage Pflicht.';
        }
        if (zweckBrauchtFreitext(zwecke, z.zweck_code)
                && !String(z.zweck_freitext || '').trim()) {
            return 'Bei "Sonstiges" ist eine Begründung Pflicht.';
        }
        if (z.modus === 'teilstring'
                && String(z.begriff).trim().length < 3) {
            return 'Die Teilstringsuche braucht mindestens 3 Zeichen.';
        }
        return null;
    }

    // =========================================================================
    // 2) DOM-AUFBAU.
    // =========================================================================

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) { n.className = cls; }
        if (text !== undefined && text !== null) { n.textContent = text; }
        return n;
    }

    function renderKopf(wrap, data) {
        var kopf = el('div', 'aiw-search-stand');
        if (standIstWarnung(data.indexstand)) {
            kopf.className += ' aiw-search-stand--warn';
        }
        kopf.appendChild(el('span', null, indexstandText(data.indexstand)));
        wrap.appendChild(kopf);

        var warn = gekapptHinweis(data);
        if (warn) {
            wrap.appendChild(el('p', 'aiw-search-warn', warn));
        }
        if (data.befund && data.befund !== 'ok') {
            wrap.appendChild(el('p', 'aiw-search-warn',
                data.befund_klartext || data.befund));
        }
    }

    function renderMaske(wrap, zustand, zwecke, hooks) {
        var form = el('div', 'aiw-search-maske');

        var feld = document.createElement('input');
        feld.type = 'text';
        feld.className = 'aiw-search-begriff';
        feld.value = zustand.begriff || '';
        feld.setAttribute('aria-label', 'Suchbegriff');
        feld.placeholder = 'Nickname oder Begriff';
        form.appendChild(feld);

        var modus = document.createElement('select');
        modus.className = 'aiw-search-modus';
        modus.setAttribute('aria-label', 'Suchart');
        [['wort', 'Wortsuche'],
         ['teilstring', 'Teilstring (findet auch Verklebtes)']]
            .forEach(function (p) {
                var o = document.createElement('option');
                o.value = p[0];
                o.textContent = p[1];
                if ((zustand.modus || 'wort') === p[0]) { o.selected = true; }
                modus.appendChild(o);
            });
        form.appendChild(modus);

        var zweck = document.createElement('select');
        zweck.className = 'aiw-search-zweck';
        zweck.setAttribute('aria-label', 'Zweck der Abfrage (Pflicht)');
        var leer = document.createElement('option');
        leer.value = '';
        leer.textContent = '— Zweck wählen (Pflicht) —';
        zweck.appendChild(leer);
        (zwecke || []).forEach(function (z) {
            var o = document.createElement('option');
            o.value = z.code;
            o.textContent = z.label;
            o.title = z.beschreibung || '';
            if (zustand.zweck_code === z.code) { o.selected = true; }
            zweck.appendChild(o);
        });
        form.appendChild(zweck);

        var frei = document.createElement('input');
        frei.type = 'text';
        frei.className = 'aiw-search-freitext';
        frei.placeholder = 'Begründung (bei "Sonstiges" Pflicht)';
        frei.setAttribute('aria-label', 'Begründung');
        frei.value = zustand.zweck_freitext || '';
        frei.disabled = !zweckBrauchtFreitext(zwecke, zustand.zweck_code);
        form.appendChild(frei);

        var knopf = el('button', 'aiw-btn', 'Suchen');
        knopf.type = 'button';
        form.appendChild(knopf);

        var fehler = el('p', 'aiw-search-warn', '');
        fehler.style.display = 'none';

        function lesen() {
            return {
                begriff: feld.value,
                modus: modus.value,
                zweck_code: zweck.value,
                zweck_freitext: frei.value
            };
        }
        zweck.addEventListener('change', function () {
            frei.disabled = !zweckBrauchtFreitext(zwecke, zweck.value);
            if (frei.disabled) { frei.value = ''; }
        });
        function ausloesen() {
            var z = lesen();
            var grund = eingabeFehler(z, zwecke);
            if (grund) {
                fehler.textContent = grund;
                fehler.style.display = '';
                log('Eingabe abgewiesen:', grund);
                return;
            }
            fehler.style.display = 'none';
            if (hooks && typeof hooks.onSuche === 'function') {
                hooks.onSuche(z);
            }
        }
        knopf.addEventListener('click', ausloesen);
        feld.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter') { ausloesen(); }
        });

        wrap.appendChild(form);
        wrap.appendChild(fehler);
    }

    function renderFall(fall, data, hooks) {
        var box = el('div', 'aiw-search-fall');
        var kopf = el('div', 'aiw-search-fall-kopf');
        kopf.appendChild(el('strong', null, 'Fall ' + fall.subject_id));
        kopf.appendChild(el('span', 'aiw-search-fassung',
                            fassungText(fall.nach_fassung)));
        box.appendChild(kopf);

        var dl = el('dl', 'aiw-search-meta');
        [['Art', artenText(fall.arten)],
         ['Zeitraum', zeitraumText(fall)],
         ['Bearbeitet von', urheberText(fall.urheber)]]
            .forEach(function (p) {
                dl.appendChild(el('dt', null, p[0]));
                dl.appendChild(el('dd', null, p[1]));
            });
        box.appendChild(dl);

        var sicht = fall.sichtbarkeit || {};
        var zeile = el('div', 'aiw-search-sicht');
        zeile.appendChild(el('span', null, sicht.klartext || ''));
        var art = sichtbarkeitsKnopf(sicht);
        if (art === 'inhalt') {
            var b1 = el('button', 'aiw-btn', 'Inhalt anzeigen');
            b1.type = 'button';
            b1.addEventListener('click', function () {
                if (hooks && typeof hooks.onInhalt === 'function') {
                    hooks.onInhalt(fall.subject_id);
                }
            });
            zeile.appendChild(b1);
        } else if (art === 'anfragen') {
            // EINE SPERRE IST KEIN FEHLER, SONDERN EIN WEG (Entscheidung 4 im
            // Dateikopf): der Knopf steht neben der Sperre, nicht anstelle
            // einer Erklaerung.
            var b2 = el('button', 'aiw-btn', 'Freigabe anfragen');
            b2.type = 'button';
            b2.addEventListener('click', function () {
                if (hooks && typeof hooks.onAnfrage === 'function') {
                    hooks.onAnfrage(fall.subject_id, data);
                }
            });
            zeile.appendChild(b2);
        }
        box.appendChild(zeile);
        return box;
    }

    // renderSearch: Stufe 1 in den Container zeichnen.
    // Rueckgabe (fuer den Aufrufer und den Test): {state, count}.
    function renderSearch(mainEl, data, hooks) {
        if (!mainEl) { return { state: 'kein_ziel', count: 0 }; }
        mainEl.textContent = '';
        var wrap = el('section', 'aiw-search');
        wrap.appendChild(el('h2', null, 'Fallübergreifende Volltextsuche'));

        if (data && data.error) {
            wrap.appendChild(el('p', 'aiw-search-warn',
                'Die Suche ist fehlgeschlagen: ' + data.error));
            mainEl.appendChild(wrap);
            return { state: 'fehler', count: 0 };
        }

        var d = data || {};
        var zwecke = (hooks && hooks.zwecke) || [];
        renderMaske(wrap, hooks && hooks.zustand ? hooks.zustand : {}, zwecke,
                    hooks);

        if (!d.stufe) {
            // Noch nicht gesucht — die Maske steht, sonst nichts. KEIN
            // 'keine Treffer': es wurde nichts gesucht, und das ist etwas
            // anderes als ein Leerbefund.
            wrap.appendChild(el('p', 'aiw-search-leer',
                'Noch keine Abfrage. Jede Abfrage wird protokolliert — '
                + 'auch dann, wenn sie nichts findet.'));
            mainEl.appendChild(wrap);
            return { state: 'bereit', count: 0 };
        }

        renderKopf(wrap, d);
        var faelle = d.faelle || [];
        wrap.appendChild(el('p', 'aiw-search-summe',
            faelle.length + ' Fall/Fälle mit Treffern, '
            + Number(d.treffer_gesamt || 0) + ' Treffer insgesamt. '
            + 'Zweck: ' + (d.zweck_klartext || '—') + '.'));

        if (!faelle.length) {
            wrap.appendChild(el('p', 'aiw-search-leer',
                'Kein Treffer. Dieser Leerbefund ist protokolliert.'));
            mainEl.appendChild(wrap);
            log('Leerbefund fuer', d.begriff);
            return { state: 'leer', count: 0 };
        }

        var liste = el('div', 'aiw-search-liste');
        faelle.forEach(function (f) {
            liste.appendChild(renderFall(f, d, hooks));
        });
        wrap.appendChild(liste);
        mainEl.appendChild(wrap);
        log('gerendert:', faelle.length, 'Faelle,', d.treffer_gesamt,
            'Treffer');
        return { state: 'befund', count: faelle.length };
    }

    // renderInhalt: Stufe 2 — die Treffer EINES Falls.
    // JEDER Ausschnitt stammt aus der QUELLE und ist gegen sie verifiziert;
    // Treffer ohne Bestaetigung erscheinen MIT BEFUND und OHNE Text. Sie
    // wegzulassen waere eine stille Auslassung (Grundregel 1).
    function renderInhalt(mainEl, data, hooks) {
        if (!mainEl) { return { state: 'kein_ziel', count: 0 }; }
        mainEl.textContent = '';
        var wrap = el('section', 'aiw-search');
        var d = data || {};
        wrap.appendChild(el('h2', null,
            'Trefferinhalt — Fall ' + (d.subject_id || '?')));

        var zurueck = el('button', 'aiw-btn', 'Zurück zur Trefferlage');
        zurueck.type = 'button';
        zurueck.addEventListener('click', function () {
            if (hooks && typeof hooks.onZurueck === 'function') {
                hooks.onZurueck();
            }
        });
        wrap.appendChild(zurueck);

        if (d.error) {
            wrap.appendChild(el('p', 'aiw-search-warn',
                'Abruf fehlgeschlagen: ' + d.error));
            mainEl.appendChild(wrap);
            return { state: 'fehler', count: 0 };
        }

        renderKopf(wrap, d);

        if (d.erlaubt !== true) {
            var sperre = el('div', 'aiw-search-gesperrt');
            sperre.appendChild(el('p', null,
                (d.sichtbarkeit && d.sichtbarkeit.klartext) || 'Gesperrt.'));
            var b = el('button', 'aiw-btn', 'Freigabe anfragen');
            b.type = 'button';
            b.addEventListener('click', function () {
                if (hooks && typeof hooks.onAnfrage === 'function') {
                    hooks.onAnfrage(d.subject_id, d);
                }
            });
            sperre.appendChild(b);
            wrap.appendChild(sperre);
            mainEl.appendChild(wrap);
            log('Stufe 2 gesperrt fuer Fall', d.subject_id);
            return { state: 'gesperrt', count: 0 };
        }

        wrap.appendChild(el('p', 'aiw-search-summe',
            d.verifikationshinweis || ''));

        var treffer = d.treffer || [];
        var liste = el('div', 'aiw-search-liste');
        treffer.forEach(function (t) {
            var box = el('div', 'aiw-search-treffer');
            var kopf = el('div', 'aiw-search-fall-kopf');
            kopf.appendChild(el('strong', null,
                t.satz_art_label || t.satz_art));
            kopf.appendChild(el('span', 'aiw-search-fassung',
                'Fassung: ' + (t.fassung || '—')));
            box.appendChild(kopf);
            box.appendChild(el('div', 'aiw-search-herkunft',
                (t.quell_tabelle || '?') + '.' + (t.quell_spalte || '?')
                + ' #' + (t.quell_schluessel || '?')
                + ' · ' + fmtTs(t.ts)
                + ' · ' + (t.urheber || 'ohne Urheber')));
            if (t.ausschnitt) {
                box.appendChild(el('p', 'aiw-search-text', t.ausschnitt
                    + (t.ausschnitt_gekuerzt ? ' […]' : '')));
            } else {
                box.appendChild(el('p', 'aiw-search-warn',
                    verifikationText(t)));
            }
            liste.appendChild(box);
        });
        wrap.appendChild(liste);
        mainEl.appendChild(wrap);
        log('Stufe 2 gerendert:', treffer.length, 'Treffer,',
            d.gegen_quelle_bestaetigt, 'bestaetigt');
        return { state: treffer.length ? 'befund' : 'leer',
                 count: treffer.length };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        fmtTs: fmtTs,
        zeitraumText: zeitraumText,
        fassungText: fassungText,
        artenText: artenText,
        urheberText: urheberText,
        indexstandText: indexstandText,
        standIstWarnung: standIstWarnung,
        sichtbarkeitsKnopf: sichtbarkeitsKnopf,
        sonstigesAnteil: sonstigesAnteil,
        verifikationText: verifikationText,
        gekapptHinweis: gekapptHinweis,
        zweckBrauchtFreitext: zweckBrauchtFreitext,
        eingabeFehler: eingabeFehler,
        renderSearch: renderSearch,
        renderInhalt: renderInhalt
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitSearch = API; }
})();
