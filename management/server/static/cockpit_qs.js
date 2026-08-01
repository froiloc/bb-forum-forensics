// =============================================================================
// management/server/static/cockpit_qs.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit QS & Metriken
// =============================================================================
// Zweck (AP-3C, Frontend zu den Builds 540-542):
//   EINE Sicht, ZWEI Abschnitte — oben die QS-Stichproben (ziehen, Ergebnis
//   erfassen), unten die Ermittler-Metriken.
//
// DIE WICHTIGSTE AUSSAGE DIESER DATEI:
//   AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT. Die
//   Zweckbindung wird hier NICHT formuliert, sondern WORTGLEICH aus den
//   Antworten uebernommen (qs_vokabular.ZWECKBINDUNG bzw.
//   metrics_vokabular.ZWECKBINDUNG). Fehlt sie, MELDET die Sicht das — eine
//   zweite Formulierung im Frontend waere eine zweite Wahrheitsquelle, und
//   eine stillschweigend weiterarbeitende Sicht waere keine Kontrolle.
//   Muster: der Verjaehrungsvorbehalt (Build 525) und die Zweckbindung der
//   Matrix (Build 539).
//
//   ES SIND ZWEI ZWECKBINDUNGEN UND NICHT EINE. Die QS-Antwort spricht ueber
//   ein Pruefergebnis zu EINEM Fall, die Metrik-Antwort ueber Aggregate ueber
//   viele. Die Sicht zeigt beide dort, wo sie gelten, und legt sie NICHT
//   zusammen.
//
// DREI ENTWURFSENTSCHEIDUNGEN, DIE DEN BELEG TRAGEN:
//
//   (1) DIE BEGRUENDUNG IST EIN PFLICHTFELD, UND DIE SICHT SETZT DAS DURCH,
//       BEVOR SIE SENDET. Nicht, weil der Server es nicht koennte — er kann
//       es und tut es (qs_repo, CHECK in M034) —, sondern weil ein
//       abgewiesener Klick mit leerem Feld eine vermeidbare Zumutung ist. DIE
//       SERVERSEITIGE PRUEFUNG BLEIBT DIE MASSGEBLICHE; diese hier ist
//       Bedienkomfort und ausdruecklich keine Kontrolle.
//
//   (2) DIE SELBSTPRUEFUNGSSPERRE WIRD ANGEZEIGT, NICHT DURCHGESETZT. Der
//       Server liefert je Prueflings-Zeile 'darf_pruefen' und 'sperrgruende'
//       (Build 541). Die Sicht zeigt den GRUND und blendet das Formular aus.
//       Wer die Oberflaeche umgeht, laeuft trotzdem in den 403 — die Sperre
//       gehoert in den Server (Entscheidung mc C-1), und diese Anzeige
//       ersetzt sie nicht.
//
//   (3) KEIN OPTIMISTISCHES UI. Nach einem POST wird neu geladen. Ein
//       Pruefergebnis, das in der Oberflaeche steht, aber nicht in der
//       Datenbank, waere in einem forensischen Werkzeug die schlimmste Art
//       von Anzeige.
//
// WAS DIESE SICHT NICHT ZEIGT — und das ist Absicht:
//   KEINE Rangfolge zwischen Personen, keine Leistungszahl, keinen Vergleich
//   zweier Ermittlerinnen. Die Metrik-Antwort enthaelt so etwas gar nicht
//   (metrics_repo, gegen VERBOTENE_KENNZAHLEN getestet); die Sicht rechnet
//   auch nichts nach, woraus sich so etwas ergaebe. Ein Ausreisser wird mit
//   seinem GRUND gezeigt und ohne Schwere, ohne Punktzahl, ohne Sortierung
//   nach Auffaelligkeit.
//
// Datenform GET /api/qs (ManagementApp._qs):
//   { ziehungen: [ { id, gezogen_at, gezogen_von_name, verfahren, seed,
//                    grundgesamtheit_n, stichprobe_n, filter, bemerkung,
//                    geprueft_n, offen_n, zaehler{code:n},
//                    faelle: [ { subject_id, username, position, schicht,
//                                ergebnis, ergebnis_label, begruendung,
//                                geprueft_von_name, geprueft_at,
//                                darf_pruefen, sperrgruende[] } ],
//                    ausserhalb_der_ziehung: [...] } ],
//     ziehungen_gesamt, ergebnis_codes[], zweckbindung,
//     ist_kein_bewertungsinstrument, prueflinge_sind_vorschlag,
//     darf_pruefen_recht }
//
// Datenform GET /api/metrics (ManagementApp._metrics):
//   { stichtag, kennzahlen[], bestand{}, abdeckung{}, anlaufzeit{},
//     substanz{}, ausreisser[{subject_id, art, grund}], fehlende_quellen[],
//     hinweise[], dauer_gesamt_ms, dauer_substanz_ms, zweckbindung,
//     ist_kein_bewertungsinstrument, keine_personenrangfolge }
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG).
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen fassen NIE das DOM an;
//   UMD-Ausgang -> vitest testet den ECHTEN Code. Alle Texte ueber
//   textContent (Kontonamen sind beliebiger UTF-8 aus einem multilingualen
//   Forum, Begruendungen sind Freitext von Menschen).
//
// Build 637 (Vorgang 17200856, Welle B5 - die letzte): HILFE-MARKEN
//   fuer die zwei verbliebenen Bedienelemente dieser Sicht.
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
        args.unshift('[AIW-QS]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // Zustandstabellen. EINZIGE Stelle, an der ein Backend-Code Farbe und
    // Klartext bekommt; ein Test haelt sie gegen ERGEBNIS_CODES des Backends.
    //
    // ES GIBT KEINE RANGFOLGE VON GUT NACH SCHLECHT und keine Farbe, die
    // 'schlecht' bedeutet: 'nachzuarbeiten' und 'ruecklauf_erforderlich' sind
    // Befunde zur SACHE. Rot ist deshalb dem einen Fall vorbehalten, in dem
    // die Auswertung so nicht in die Akte kann — und auch dort heisst rot
    // 'hier ist etwas zu tun' und nicht 'hier hat jemand versagt'.
    // =========================================================================
    var ERGEBNIS = {
        in_ordnung: { cls: 'is-ok', label: 'in Ordnung' },
        nachzuarbeiten: { cls: 'is-nacharbeit', label: 'nachzuarbeiten' },
        ruecklauf_erforderlich: { cls: 'is-ruecklauf',
                                  label: 'Rücklauf erforderlich' },
        nicht_beurteilbar: { cls: 'is-unklar', label: 'nicht beurteilbar' }
    };

    var SCHICHT_LABEL = {
        nie_bewertet: 'nie bewertet',
        abdeckung_niedrig: 'Abdeckung unter der Schwelle',
        rest: 'übrige Fälle'
    };

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM).
    // =========================================================================

    // ergebnisInfo: Farbe/Label. Ein UNBEKANNTER Code wird als solcher
    // gekennzeichnet und NICHT auf einen bekannten abgebildet — sonst bekaeme
    // ein neuer Backend-Code stillschweigend eine falsche Bedeutung.
    function ergebnisInfo(code) {
        if (!code) {
            return { cls: 'is-offen', label: 'OFFEN' };
        }
        var e = ERGEBNIS[code];
        if (e) { return e; }
        return { cls: 'is-unbekannt',
                 label: 'unbekanntes Ergebnis (' + String(code) + ')' };
    }

    function schichtLabel(code) {
        if (!code) { return '—'; }
        return SCHICHT_LABEL[code]
            || ('unbekannte Schicht (' + String(code) + ')');
    }

    function ergebnisCodes() { return Object.keys(ERGEBNIS); }

    // zweckText: die Zweckbindung WORTGLEICH aus der Antwort. Sie wird hier
    // NICHT formuliert. Fehlt sie, ist das ein Missstand und wird benannt.
    function zweckText(data, was) {
        var d = data || {};
        if (d.ist_kein_bewertungsinstrument === true && d.zweckbindung) {
            return String(d.zweckbindung);
        }
        return 'ACHTUNG: Die Antwort (' + was + ') trägt die Zweckbindung '
            + 'NICHT mit. Behandeln Sie keine Angabe dieser Sicht als Aussage '
            + 'über eine Person, bevor die Herkunft der Antwort geklärt ist.';
    }

    function zweckOk(data) {
        return !!(data && data.ist_kein_bewertungsinstrument === true
                  && data.zweckbindung);
    }

    // vorschlagText: die Prueflinge sind ein VORSCHLAG (Entscheidung mc).
    // Ohne diesen Satz liest sich eine Ziehung wie eine Anweisung.
    function vorschlagText(data) {
        if (data && data.prueflinge_sind_vorschlag === true) {
            return 'Die gezogenen Fälle sind ein VORSCHLAG. Eine Abweichung '
                + 'ist zulässig und wird protokolliert — ein Ergebnis zu einem '
                + 'nicht gezogenen Fall erscheint eigens ausgewiesen.';
        }
        return 'ACHTUNG: Die Antwort trägt den Hinweis auf den Vorschlags-'
            + 'charakter der Ziehung NICHT mit.';
    }

    // fortschrittText: geprueft von wie vielen. Die OFFENEN stehen mit dabei —
    // eine Ziehung, an der niemand gearbeitet hat, sieht sonst aus wie eine
    // ohne Beanstandung.
    function fortschrittText(ziehung) {
        var z = ziehung || {};
        var n = (z.faelle || []).length;
        return (z.geprueft_n || 0) + ' von ' + n + ' geprüft'
            + (z.offen_n ? (' · ' + z.offen_n + ' offen') : '');
    }

    // nachweisText: was diese Ziehung NACHRECHENBAR macht. Der Keim gehoert in
    // die Sicht und nicht nur in die Datenbank: wer ihn sieht, weiss, dass er
    // ihn pruefen lassen kann (python -m management.qs.qs_admin nachziehen).
    function nachweisText(ziehung) {
        var z = ziehung || {};
        return 'Verfahren: ' + (z.verfahren || '—')
            + ' · Zufallskeim: ' + (z.seed === undefined || z.seed === null
                                    ? '—' : z.seed)
            + ' · Umfang: ' + (z.stichprobe_n || 0) + ' von '
            + (z.grundgesamtheit_n || 0)
            + ' · Diese Ziehung ist mit dem Keim exakt nachrechenbar.';
    }

    // zaehlerText: die Ergebnisverteilung EINER Ziehung. Codes mit 0 werden
    // weggelassen, ABER 'ruecklauf_erforderlich' immer genannt — die
    // Abwesenheit eines Rücklaufs ist eine eigene, wichtige Aussage.
    function zaehlerText(ziehung) {
        var z = (ziehung && ziehung.zaehler) || {};
        var immer = { ruecklauf_erforderlich: 1 };
        var teile = [];
        Object.keys(ERGEBNIS).forEach(function (k) {
            var n = z[k] || 0;
            if (n > 0 || immer[k]) {
                teile.push(ERGEBNIS[k].label + ': ' + n);
            }
        });
        Object.keys(z).forEach(function (k) {
            if (!ERGEBNIS[k]) { teile.push('unbekannt (' + k + '): ' + z[k]); }
        });
        return teile.join(' · ');
    }

    // begruendungFehlt: die Vorab-Pruefung des Pflichtfeldes (s. Kopf, (1)).
    // REIN — sie fasst kein DOM an und ist deshalb einzeln pruefbar.
    function begruendungFehlt(text) {
        return !String(text || '').trim();
    }

    // sperrText: warum ein Fall nicht geprueft werden darf — oder null.
    function sperrText(fall) {
        var f = fall || {};
        if (f.darf_pruefen !== false) { return null; }
        var gruende = f.sperrgruende || [];
        return 'SELBSTPRÜFUNG GESPERRT: ' + (gruende.length
            ? gruende.join(' ')
            : 'Diese Person hat den Fall bearbeitet.')
            + ' Die Prüfung ist an eine andere Person zu geben.';
    }

    // --- Metriken ---------------------------------------------------------

    // substanzText: der Ladezustand des teuren Blocks. Er unterscheidet
    // 'nicht nachgesehen' von 'nachgesehen, nichts gefunden' — dieselbe
    // Unterscheidung wie bei den Fristen der Matrix (Build 539).
    function substanzText(metrik) {
        var s = (metrik && metrik.substanz) || {};
        if (s.geprueft === true) {
            return s.ohne_annotation + ' von ' + s.faelle_zugewiesen
                + ' zugewiesenen Fällen enthalten KEINE Annotation. '
                + s.ohne_evidence_datei + ' Fälle haben (noch) keine '
                + 'evidence-Datei — das ist etwas anderes und wird nicht '
                + 'mitgezählt.';
        }
        if (s.fehler) {
            return 'Der Substanz-Block war NICHT LESBAR: ' + s.fehler
                + ' — das ist kein Leerbefund.';
        }
        return String(s.hinweis || 'NICHT NACHGESEHEN.');
    }

    function substanzGeprueft(metrik) {
        return !!(metrik && metrik.substanz
                  && metrik.substanz.geprueft === true);
    }

    // anlaufText: die Liegezeiten. Der Satz nennt AUSDRUECKLICH die Faelle
    // OHNE inhaltliches Ereignis — sie fallen aus jeder Median-Rechnung
    // heraus und sind doch die eigentliche Aussage.
    function anlaufText(metrik) {
        var a = (metrik && metrik.anlaufzeit) || {};
        if (a.fehler) {
            return 'Nicht lesbar: ' + a.fehler;
        }
        var teile = [];
        if (a.median_tage === null || a.median_tage === undefined) {
            teile.push('Keine messbare Anlaufzeit — es gibt keine Spanne '
                + '(das ist NICHT dasselbe wie 0 Tage).');
        } else {
            teile.push('Median ' + a.median_tage + ' Tage (Q1 ' + a.q1_tage
                + ', Q3 ' + a.q3_tage + ', längste ' + a.max_tage + ')');
        }
        teile.push((a.faelle_ohne_inhaltliches_ereignis || 0)
            + ' von ' + (a.faelle_mit_zuweisung || 0)
            + ' zugewiesenen Fällen haben ÜBERHAUPT KEIN inhaltliches '
            + 'Ereignis.');
        return teile.join(' · ');
    }

    // ausreisserText: die Deutung, wortgleich zur Absicht des Backends.
    function ausreisserText(metrik) {
        var n = ((metrik && metrik.ausreisser) || []).length;
        if (!n) {
            return 'Keine Auffälligkeit benannt. Das ist ein Leerbefund über '
                + 'die geprüften Merkmale und keine Bescheinigung.';
        }
        return n + ' Auffälligkeit(en). EIN AUSREISSER IST EIN HINWEIS AUF '
            + 'PRÜFBEDARF AN DER AUSWERTUNG und kein Befund über eine Person. '
            + 'Er ist nicht bewertet, nicht gewichtet und nicht nach Schwere '
            + 'geordnet.';
    }

    // abdeckungZeilen: das Histogramm als Liste. REIN.
    function abdeckungZeilen(metrik) {
        var a = (metrik && metrik.abdeckung) || {};
        var k = a.klassen || {};
        return Object.keys(k).map(function (code) {
            return { code: code, n: k[code] };
        });
    }

    function ziehungen(data) {
        return (data && data.ziehungen) || [];
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    function _el(doc, tag, cls, text) {
        var e = doc.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    function _pruefformular(doc, ziehung, fall, opts) {
        /*
         * Das Erfassungsformular EINER Zeile. Es erscheint nur, wenn
         * (a) das Recht 'qs.edit' vorliegt, (b) der Fall nicht gesperrt ist
         * und (c) ein wirkender Rueckruf uebergeben wurde. Ein Bedienelement
         * ohne Wirkung waere schlimmer als keines (Regel seit Build 525).
         */
        var box = _el(doc, 'div', 'aiw-qs-form');
        var sel = doc.createElement('select');
        // EIGENE Klasse und NICHT 'aiw-qs-ergebnis': die traegt bereits
        // die ERGEBNISSPALTE der Tabelle. Zwei Elemente mit derselben
        // Klasse, die Verschiedenes bedeuten, sind ein Fehler in der
        // Benennung — er ist in der Testvorrichtung zu Build 543
        // aufgefallen (querySelector traf die Zelle statt der Auswahl).
        sel.className = 'aiw-qs-ergebnis-wahl';
        // Build 637 (Vorgang 17200856): Hilfe-Marken, LITERAL gesetzt.
        sel.setAttribute('data-hilfe-id', 'qs.bedienung.ergebnis');
        Object.keys(ERGEBNIS).forEach(function (code) {
            var o = doc.createElement('option');
            o.value = code;
            o.textContent = ERGEBNIS[code].label;
            sel.appendChild(o);
        });
        var ta = doc.createElement('textarea');
        ta.className = 'aiw-qs-begruendung';
        ta.setAttribute('rows', '2');
        ta.setAttribute('placeholder',
            'Begründung (Pflicht) — was trägt, was fehlt?');
        ta.setAttribute('data-hilfe-id', 'qs.bedienung.begruendung');
        var knopf = _el(doc, 'button', 'aiw-qs-speichern', 'Ergebnis erfassen');
        knopf.setAttribute('type', 'button');
        var fehler = _el(doc, 'div', 'aiw-qs-formfehler', '');

        knopf.addEventListener('click', function () {
            // VORAB-PRUEFUNG, kein Ersatz fuer den Server (s. Kopf, (1)).
            if (begruendungFehlt(ta.value)) {
                fehler.textContent =
                    'Die Begründung ist Pflicht. Ein Prüfergebnis ohne '
                    + 'Begründung ist ein Daumen und kein Befund.';
                return;
            }
            fehler.textContent = '';
            log('review', ziehung.id, fall.subject_id, sel.value);
            opts.onReview({
                sample_id: ziehung.id,
                subject_id: fall.subject_id,
                ergebnis: sel.value,
                begruendung: ta.value
            });
        });

        box.appendChild(sel);
        box.appendChild(ta);
        box.appendChild(knopf);
        box.appendChild(fehler);
        return box;
    }

    function _ziehungsblock(doc, z, data, opts) {
        var sec = _el(doc, 'section', 'aiw-qs-ziehung');
        sec.setAttribute('data-sample', String(z.id));
        sec.appendChild(_el(doc, 'h3', 'aiw-qs-ziehung-titel',
            'Ziehung ' + z.id + ' — ' + fortschrittText(z)));
        // DER NACHWEIS STEHT OBEN, nicht in einer Fussnote: er ist der Grund,
        // aus dem diese Stichprobe ueberhaupt ein Beleg ist.
        sec.appendChild(_el(doc, 'p', 'aiw-qs-nachweis', nachweisText(z)));
        var zt = zaehlerText(z);
        if (zt) {
            sec.appendChild(_el(doc, 'p', 'aiw-qs-zaehler', zt));
        }
        if (z.bemerkung) {
            sec.appendChild(_el(doc, 'p', 'aiw-qs-bemerkung',
                'Bemerkung: ' + z.bemerkung));
        }

        var tbl = _el(doc, 'table', 'aiw-qs-table');
        var thead = doc.createElement('thead');
        var trh = doc.createElement('tr');
        ['Pos', 'Fall', 'Schicht', 'Ergebnis', 'Begründung', 'geprüft von']
            .forEach(function (h) {
                trh.appendChild(_el(doc, 'th', null, h));
            });
        thead.appendChild(trh);
        tbl.appendChild(thead);

        var tbody = doc.createElement('tbody');
        (z.faelle || []).forEach(function (f) {
            var info = ergebnisInfo(f.ergebnis);
            var tr = _el(doc, 'tr', 'aiw-qs-row ' + info.cls);
            tr.setAttribute('data-subject', String(f.subject_id));
            tr.appendChild(_el(doc, 'td', 'aiw-qs-pos', String(f.position)));
            tr.appendChild(_el(doc, 'td', 'aiw-qs-case',
                f.subject_id + ' · ' + (f.username || '?')));
            tr.appendChild(_el(doc, 'td', 'aiw-qs-schicht',
                schichtLabel(f.schicht)));
            tr.appendChild(_el(doc, 'td', 'aiw-qs-ergebnis', info.label));

            var bz = _el(doc, 'td', 'aiw-qs-begr');
            if (f.begruendung) {
                bz.textContent = f.begruendung;
            } else {
                var sp = sperrText(f);
                if (sp) {
                    bz.className += ' is-gesperrt';
                    bz.textContent = sp;
                } else if (typeof opts.onReview === 'function'
                        && data.darf_pruefen_recht === true) {
                    bz.appendChild(_pruefformular(doc, z, f, opts));
                } else {
                    bz.textContent = '—';
                }
            }
            tr.appendChild(bz);
            tr.appendChild(_el(doc, 'td', 'aiw-qs-wer',
                f.geprueft_von_name || '—'));
            tbody.appendChild(tr);
        });
        tbl.appendChild(tbody);
        sec.appendChild(tbl);

        // AUSSERHALB DER ZIEHUNG: die zulaessige Abweichung. Sie wird EIGENS
        // ausgewiesen — stillschweigend mitgezaehlt waere sie die gezielte
        // Auswahl durch die Hintertuer.
        var aus = z.ausserhalb_der_ziehung || [];
        if (aus.length) {
            var box = _el(doc, 'div', 'aiw-qs-ausserhalb');
            box.appendChild(_el(doc, 'h4', null,
                'Außerhalb der Ziehung geprüft (' + aus.length + ')'));
            var ul = doc.createElement('ul');
            aus.forEach(function (r) {
                ul.appendChild(_el(doc, 'li', null,
                    'Fall ' + r.subject_id + ' — '
                    + ergebnisInfo(r.ergebnis).label
                    + ' (' + (r.geprueft_von_name || '?') + ')'));
            });
            box.appendChild(ul);
            sec.appendChild(box);
        }
        return sec;
    }

    function _metrikblock(doc, metrik) {
        var sec = _el(doc, 'section', 'aiw-qs-metriken');
        sec.appendChild(_el(doc, 'h3', 'aiw-qs-metrik-titel',
            'Kennzahlen zur Auswertung'));

        if (metrik && metrik.error) {
            sec.appendChild(_el(doc, 'p', 'aiw-qs-fehler',
                'Kennzahlen derzeit nicht verfügbar: ' + metrik.error
                + ' — dies ist KEIN Leerbefund.'));
            return sec;
        }

        // Die ZWEITE Zweckbindung — die der Metriken. Sie steht hier und nicht
        // oben: sie gilt fuer diesen Abschnitt.
        sec.appendChild(_el(doc, 'div',
            'aiw-qs-zweck ' + (zweckOk(metrik) ? 'is-ok' : 'is-fehlt'),
            zweckText(metrik, 'Kennzahlen')));

        var b = (metrik && metrik.bestand) || {};
        sec.appendChild(_el(doc, 'p', 'aiw-qs-kennzahl',
            'Bestand: ' + (b.faelle_gesamt || 0) + ' Fälle, davon '
            + (b.unzugewiesen || 0) + ' unzugewiesen.'));

        // Abdeckung als Klassenliste — kein Diagramm: eine Verteilung ueber
        // fuenf Klassen ist als Liste vollstaendig lesbar, und eine Grafik
        // haette eine Genauigkeit vorgetaeuscht, die die Klassen nicht haben.
        var ab = (metrik && metrik.abdeckung) || {};
        var ul = doc.createElement('ul');
        ul.className = 'aiw-qs-abdeckung';
        abdeckungZeilen(metrik).forEach(function (z) {
            ul.appendChild(_el(doc, 'li', null, z.code + ': ' + z.n));
        });
        sec.appendChild(_el(doc, 'p', 'aiw-qs-kennzahl',
            'Abdeckung der Bewertungskriterien (' + (ab.n_kriterien || '?')
            + ' Kriterien), Fälle je Klasse:'));
        sec.appendChild(ul);

        sec.appendChild(_el(doc, 'p', 'aiw-qs-kennzahl',
            'Anlaufzeit: ' + anlaufText(metrik)));
        sec.appendChild(_el(doc, 'p', 'aiw-qs-kennzahl',
            'Substanz: ' + substanzText(metrik)));

        // AUSREISSER — benannt, nicht bewertet.
        sec.appendChild(_el(doc, 'p',
            'aiw-qs-ausreisser-kopf', ausreisserText(metrik)));
        var arr = (metrik && metrik.ausreisser) || [];
        if (arr.length) {
            var ul2 = doc.createElement('ul');
            ul2.className = 'aiw-qs-ausreisser';
            arr.forEach(function (a) {
                ul2.appendChild(_el(doc, 'li', null,
                    'Fall ' + a.subject_id + ': ' + a.grund));
            });
            sec.appendChild(ul2);
        }

        (metrik && metrik.hinweise || []).forEach(function (h) {
            sec.appendChild(_el(doc, 'p', 'aiw-qs-hinweis', h));
        });
        return sec;
    }

    // renderQs: baut die Sicht in mainEl.
    //   data          — Antwort von GET /api/qs (oder {error})
    //   opts.metrik   — Antwort von GET /api/metrics (oder {error}/null)
    //   opts.doc      — Dokument (injizierbar fuer Tests)
    //   opts.onDraw   — Rueckruf () fuer 'Neue Stichprobe ziehen'
    //   opts.onReview — Rueckruf ({sample_id, subject_id, ergebnis,
    //                   begruendung}) fuer ein Pruefergebnis
    //   opts.onSubstanz — Rueckruf (bool) fuer den teuren Metrik-Block
    //   opts.fehler   — optionale Fehlermeldung des letzten Schreibversuchs
    function renderQs(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = opts.doc || mainEl.ownerDocument
            || (typeof document !== 'undefined' ? document : null);
        if (!doc) { return null; }

        mainEl.textContent = '';
        // Build 602 (Baustelle H / H11): literale Hilfe-Marken.
        var qsKopf = _el(doc, 'h2', 'aiw-pagehead', 'QS & Metriken');
        qsKopf.setAttribute('data-hilfe-id', 'qs.titel');
        mainEl.appendChild(qsKopf);

        if (data && data.error) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
                'QS-Sicht derzeit nicht verfügbar: ' + data.error
                + ' — dies ist KEIN Leerbefund. Es ist unbekannt, ob geprüft '
                + 'wurde.'));
            log('Fehlerzustand:', data.error);
            return { state: 'error' };
        }

        // (1) DIE ZWECKBINDUNG DER QS — ganz oben.
        var qsZweck = _el(doc, 'div',
            'aiw-qs-zweck ' + (zweckOk(data) ? 'is-ok' : 'is-fehlt'),
            zweckText(data, 'QS-Stichprobe'));
        qsZweck.setAttribute('data-hilfe-id', 'qs.zweckbindung');
        mainEl.appendChild(qsZweck);

        // (2) Der Vorschlagscharakter der Ziehung.
        var qsVorschlag = _el(doc, 'div', 'aiw-qs-vorschlag',
            vorschlagText(data));
        qsVorschlag.setAttribute('data-hilfe-id', 'qs.vorschlag');
        mainEl.appendChild(qsVorschlag);

        // (3) Ein fehlgeschlagener Schreibversuch steht OBEN und bleibt
        //     stehen, bis der naechste Versuch laeuft. Ein 403 aus der
        //     Selbstpruefungssperre ist genau die Meldung, die jemand lesen
        //     soll.
        if (opts.fehler) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-qs-fehler',
                'Der letzte Schreibversuch ist fehlgeschlagen: '
                + opts.fehler));
        }

        // (4) Ziehen — nur mit Recht UND wirkendem Rueckruf.
        if (typeof opts.onDraw === 'function'
                && data.darf_pruefen_recht === true) {
            var box = _el(doc, 'div', 'aiw-qs-actions');
            var b = _el(doc, 'button', 'aiw-qs-draw',
                'Neue Stichprobe ziehen');
            b.setAttribute('type', 'button');
            b.addEventListener('click', function () {
                log('draw');
                opts.onDraw();
            });
            box.appendChild(b);
            box.appendChild(_el(doc, 'span', 'aiw-qs-actions-hinweis',
                'Der Zufallskeim wird mitgeschrieben; die Ziehung bleibt '
                + 'nachrechenbar.'));
            mainEl.appendChild(box);
        }

        // (5) Die Ziehungen.
        var liste = ziehungen(data);
        if (!liste.length) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-qs-leer',
                'Keine Ziehung vorhanden. Das ist ein Leerbefund über die '
                + 'STICHPROBEN und keine Aussage über die '
                + 'Auswertungsqualität.'));
        } else {
            liste.forEach(function (z) {
                mainEl.appendChild(_ziehungsblock(doc, z, data, opts));
            });
        }

        // (6) Die Metriken.
        if (opts.metrik) {
            mainEl.appendChild(_metrikblock(doc, opts.metrik));
            if (typeof opts.onSubstanz === 'function') {
                var sbox = _el(doc, 'div', 'aiw-qs-actions');
                sbox.appendChild(_el(doc, 'span', 'aiw-qs-actions-label',
                    'Substanz-Prüfung (ein Dateizugriff je Fall):'));
                [[true, 'nachsehen'], [false, 'auslassen']]
                    .forEach(function (spec) {
                        var sb = _el(doc, 'button', 'aiw-qs-substanz',
                            spec[1]);
                        sb.setAttribute('type', 'button');
                        sb.setAttribute('data-substanz', spec[0] ? '1' : '0');
                        if (substanzGeprueft(opts.metrik) === spec[0]) {
                            sb.className += ' is-active';
                            sb.setAttribute('aria-pressed', 'true');
                        }
                        sb.addEventListener('click', function () {
                            log('substanz ->', spec[0]);
                            opts.onSubstanz(spec[0]);
                        });
                        sbox.appendChild(sb);
                    });
                mainEl.appendChild(sbox);
            }
        }

        log('gerendert:', liste.length, 'Ziehungen; Metriken:',
            !!opts.metrik);
        return {
            state: liste.length ? 'befund' : 'leer',
            ziehungen: liste.length,
            metriken: !!opts.metrik,
            zweckbindung: zweckOk(data)
        };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        ERGEBNIS: ERGEBNIS,
        SCHICHT_LABEL: SCHICHT_LABEL,
        ergebnisInfo: ergebnisInfo,
        ergebnisCodes: ergebnisCodes,
        schichtLabel: schichtLabel,
        zweckText: zweckText,
        zweckOk: zweckOk,
        vorschlagText: vorschlagText,
        fortschrittText: fortschrittText,
        nachweisText: nachweisText,
        zaehlerText: zaehlerText,
        begruendungFehlt: begruendungFehlt,
        sperrText: sperrText,
        substanzText: substanzText,
        substanzGeprueft: substanzGeprueft,
        anlaufText: anlaufText,
        ausreisserText: ausreisserText,
        abdeckungZeilen: abdeckungZeilen,
        ziehungen: ziehungen,
        renderQs: renderQs
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitQs = API; }
})();
