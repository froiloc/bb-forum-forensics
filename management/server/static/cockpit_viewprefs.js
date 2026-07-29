// =============================================================================
// management/server/static/cockpit_viewprefs.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit "Ansicht anpassen"
// =============================================================================
// Zweck (AP-3G / Idee 37, Build 546):
//   Die Sicht, mit der eine Person die uebrigen Sichten einrichtet:
//   REIHENFOLGE (Ziehen oder Pfeiltasten) und SICHTBARKEIT (Schalter) der
//   Navigationseintraege. Gespeichert wird SERVERSEITIG (POST /api/viewprefs),
//   weil der Browser als Ablageort projektweit ausgeschlossen ist — Beleg
//   cockpit.js: "Zustand lebt nur im Speicher (kein localStorage —
//   Projekt-/Artefakt-Regel)".
//
// ARBEITSTEILUNG mit der Shell (cockpit.js): dieses Modul RENDERT nur und
//   meldet Absichten ueber Callbacks zurueck (onSave/onReset). Die Shell fuehrt
//   den POST aus (Schreib-Token X-AIW-Token) und laedt danach NEU — kein
//   optimistisches UI: die Oberflaeche zeigt nur bestaetigt geschriebene
//   Zustaende (Muster Zuweisung/Querfund-Rueckkanal, Grundregel 1).
//
// ── WAS DIESE SICHT NICHT KANN, UND WARUM DAS WICHTIG IST ──────────────────
//
//   Sie kann keine Sicht EINBLENDEN, fuer die das Recht fehlt. Sie bekommt von
//   der Shell bereits die rechte-gefilterte Liste, und der Server prueft beim
//   Speichern ein zweites Mal gegen seinen Katalog. Der Rechtefilter laeuft in
//   cockpit.js ZULETZT (navViews) — eine Vorliebe ordnet und versteckt, sie
//   berechtigt nicht.
//
// ── AUSBLENDEN IST ERLAUBT, ABER NIE STILL ─────────────────────────────────
//
//   Eine ausgeblendete Eskalationssicht koennte eine uebersehene Eskalation
//   bedeuten. Das Verbot waere die schlechtere Antwort (dann richtet sich
//   niemand die Oberflaeche ein, und die Sicht bleibt trotzdem ungelesen — nur
//   ohne Vermerk). Stattdessen:
//     * Die Navigation traegt dauerhaft "N Sichten ausgeblendet" (cockpit.js).
//     * Ausgeblendete Sichten bleiben ueber die Kommandopalette (Strg-K)
//       erreichbar — sie bekommt die NUR rechte-gefilterte Liste.
//     * Diese Sicht zeigt Ausgeblendetes NICHT versteckt, sondern durchgestrichen
//       in der Liste, an seinem Platz.
//     * Ein Knopf setzt auf Werkseinstellung zurueck.
//     * Jede Speicherung ist ein Audit-Beleg mit dem VOLLSTAENDIGEN Zustand.
//
// ── UNGESPEICHERTES GEHT NICHT VERLOREN (mc 2026-07-26) ───────────────────
//
//   Zwei Massnahmen, die sich ergaenzen:
//
//   (1) WARNHINWEIS BEIM VERLASSEN. Wer die Sicht mit ungespeicherten
//       Aenderungen verlaesst, wird gefragt (cockpit.js selectView) — und beim
//       Schliessen/Neuladen des Fensters ebenso (beforeunload).
//
//   (2) BROWSER-ZWISCHENSPEICHER DES ENTWURFS. Der noch nicht gespeicherte
//       Stand liegt in localStorage und wird beim Wiederbetreten
//       zurueckgeholt; nach erfolgreichem Speichern wird er verworfen.
//
//   ZUR PROJEKTREGEL: localStorage ist als Ablageort fuer SICHTZUSTAND
//   projektweit ausgeschlossen (cockpit.js, "Zustand lebt nur im Speicher —
//   Projekt-/Artefakt-Regel"), und genau darauf stuetzt der Wellenplan die
//   Serverseite. Was hier liegt, ist NICHT der Zustand, sondern ein
//   ungespeicherter ENTWURF — dieselbe Abgrenzung wie bei den
//   Dokumentvorlagen (Build 487) und den Baustein-Modulen (Build 488): "nur
//   Client, migrationsneutral". DER GESPEICHERTE STAND LIEGT AUSSCHLIESSLICH
//   IN coordinator.db (person_view_pref, M037). Faellt der Zwischenspeicher
//   aus oder ist er abgeschaltet, geht nichts kaputt — es fehlt dann nur die
//   Bequemlichkeit, und die Warnung greift trotzdem.
//
// ── BARRIEREFREIHEIT ───────────────────────────────────────────────────────
//
//   Ziehen ist nicht tastaturbedienbar. Jede Zeile hat deshalb zusaetzlich
//   Pfeil-Schaltflaechen (Muster cockpit_notes.js, Build 407). Die reine
//   Funktion verschiebe() ist der EINE Ort, an dem die Verschiebelogik steht —
//   Ziehen und Pfeile fuehren beide dorthin.
//
// JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging (zur Laufzeit
//   umschaltbar, PROD aus); ausfuehrliche Kommentare; Kapselung; REINE
//   Funktionen fassen NIE das DOM an und sind per vitest gegen den ECHTEN Code
//   pruefbar (UMD-artiger Ausgang -> keine 'gruen-aber-tot'-Kopie).
//
// SICHERHEIT (XSS): Labels stammen aus dem statischen VIEW_CATALOG und sind
//   unkritisch, werden aber wie aller variable Text ausschliesslich via
//   textContent gesetzt — nie via innerHTML.
//
// Version: v0.8.546 · Build: 546 · 2026-07-26
// =============================================================================

(function () {
    'use strict';

    // Gemeinsames Flag der ganzen Oberflaeche, zur Laufzeit umschaltbar.
    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-ViewPrefs]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM). Genau diese testet vitest.
    // =========================================================================

    // verschiebe: Eintrag mit 'key' um 'delta' Plaetze bewegen.
    //
    // Gibt eine NEUE Liste zurueck; die Eingabe bleibt unberuehrt. Ein Zug
    // ueber den Rand hinaus ist KEIN Fehler und KEIN Sonderfall — er ist
    // schlicht wirkungslos (die Liste kommt unveraendert zurueck). Eine
    // Fehlermeldung fuer "die oberste Zeile kann nicht hoeher" waere Laerm.
    function verschiebe(rows, key, delta) {
        var liste = (rows || []).slice();
        var i = -1;
        for (var n = 0; n < liste.length; n++) {
            if (liste[n] && liste[n].id === key) { i = n; break; }
        }
        if (i < 0) { return liste; }
        var ziel = i + delta;
        if (ziel < 0 || ziel >= liste.length) { return liste; }
        var tmp = liste[i];
        liste[i] = liste[ziel];
        liste[ziel] = tmp;
        return liste;
    }

    // ======================================================================
    // Build 568 — ZWEI EBENEN: Gruppen und Sichten darin.
    // ======================================================================
    // Gespeichert wird weiterhin EINE FLACHE LISTE (person_view_pref, eine
    // Position je Sicht) - mc 2026-07-29: "Schoen flach halten. Das ist nur
    // Kosmetik. Keine Rechtfertigung fuer hohen Aufwand."
    //
    // Die zweite Ebene braucht dafuer kein eigenes Feld, sondern nur eine
    // ZUSAGE an die flache Liste: jede Gruppe steht am Stueck. Dann ist die
    // Gruppenfolge das erste Auftreten, und die Folge innerhalb der Gruppe ist
    // die flache Folge. Beide Bewegungen unten halten diese Zusage ein - und
    // damit kann die Bedienoberflaeche gar nicht mehr erzeugen, was bis
    // Build 567 moeglich war: eine verschraenkte Liste, die in der Navigation
    // denselben Gruppenkopf zweimal erscheinen liess.

    // gruppenAus: flache Liste -> [{ gruppe, zeilen: [...] }], gruppenrein und
    // in der Reihenfolge des ersten Auftretens.
    function gruppenAus(rows) {
        var proGruppe = {};
        var folge = [];
        (rows || []).forEach(function (r) {
            var g = r && r.group;
            if (!Object.prototype.hasOwnProperty.call(proGruppe, g)) {
                proGruppe[g] = [];
                folge.push(g);
            }
            proGruppe[g].push(r);
        });
        return folge.map(function (g) {
            return { gruppe: g, zeilen: proGruppe[g] };
        });
    }

    // flachAus: [{gruppe, zeilen}] -> flache Liste. Gegenstueck zu gruppenAus.
    function flachAus(bloecke) {
        var out = [];
        (bloecke || []).forEach(function (b) {
            out = out.concat(b.zeilen || []);
        });
        return out;
    }

    // gruppeVerschieben: eine GANZE Gruppe um 'delta' Plaetze bewegen. Ein Zug
    // ueber den Rand ist wirkungslos, kein Fehler (wie bei 'verschiebe').
    function gruppeVerschieben(rows, gruppe, delta) {
        var bloecke = gruppenAus(rows);
        var i = -1;
        for (var n = 0; n < bloecke.length; n++) {
            if (bloecke[n].gruppe === gruppe) { i = n; break; }
        }
        if (i < 0) { return (rows || []).slice(); }
        var ziel = i + delta;
        if (ziel < 0 || ziel >= bloecke.length) {
            return (rows || []).slice();
        }
        var tmp = bloecke[i];
        bloecke[i] = bloecke[ziel];
        bloecke[ziel] = tmp;
        return flachAus(bloecke);
    }

    // verschiebeInGruppe: eine Sicht NUR innerhalb ihrer Gruppe bewegen. Am
    // Rand der Gruppe ist Schluss - ein Zug darueber hinaus wuerde die Sicht
    // in eine fremde Gruppe tragen, und die Zugehoerigkeit einer Sicht ist
    // eine Festlegung des Katalogs, keine Frage der persoenlichen Ordnung.
    function verschiebeInGruppe(rows, key, delta) {
        var bloecke = gruppenAus(rows);
        for (var b = 0; b < bloecke.length; b++) {
            var z = bloecke[b].zeilen;
            for (var i = 0; i < z.length; i++) {
                if (z[i] && z[i].id === key) {
                    var ziel = i + delta;
                    if (ziel < 0 || ziel >= z.length) {
                        return (rows || []).slice();
                    }
                    var neu = z.slice();
                    var tmp = neu[i];
                    neu[i] = neu[ziel];
                    neu[ziel] = tmp;
                    bloecke[b] = { gruppe: bloecke[b].gruppe, zeilen: neu };
                    return flachAus(bloecke);
                }
            }
        }
        return (rows || []).slice();
    }

    // umschalten: Sichtbarkeit eines Eintrags kippen. NEUE Liste, NEUE Objekte
    // (die Eingabe bleibt unberuehrt — sonst haette die Shell einen veraenderten
    // Katalog in der Hand).
    function umschalten(rows, key) {
        return (rows || []).map(function (r) {
            if (!r || r.id !== key) { return r; }
            var k = {};
            for (var f in r) {
                if (Object.prototype.hasOwnProperty.call(r, f)) { k[f] = r[f]; }
            }
            k.versteckt = !r.versteckt;
            return k;
        });
    }

    // zuNutzlast: die Liste in das Format des Endpunkts uebersetzen.
    // Die REIHENFOLGE des Arrays ist die Reihenfolge — eine mitgeschickte
    // Position gaebe es zweimal (Server: viewpref_repo, Kopf).
    function zuNutzlast(rows) {
        return (rows || []).map(function (r) {
            return { key: r.id, sichtbar: r.versteckt !== true };
        });
    }

    // zusammenfassung: Zahlen fuer die Kopfzeile. Sie stehen dort, damit die
    // Wirkung des Ausblendens auch OHNE Scrollen ablesbar ist.
    function zusammenfassung(rows) {
        var liste = rows || [];
        var versteckt = 0;
        liste.forEach(function (r) { if (r && r.versteckt) { versteckt++; } });
        return {
            gesamt: liste.length,
            versteckt: versteckt,
            sichtbar: liste.length - versteckt
        };
    }

    // istGeaendert: unterscheidet sich der Bearbeitungsstand vom geladenen?
    // Steuert, ob "Speichern" ueberhaupt etwas zu tun haette.
    function istGeaendert(rows, geladen) {
        var a = zuNutzlast(rows);
        var b = (geladen || []).map(function (p) {
            return { key: p.key, sichtbar: p.sichtbar !== false };
        });
        if (a.length !== b.length) { return true; }
        for (var i = 0; i < a.length; i++) {
            if (a[i].key !== b[i].key) { return true; }
            if (a[i].sichtbar !== b[i].sichtbar) { return true; }
        }
        return false;
    }

    // entwurfAnwenden: einen zwischengespeicherten Entwurf auf die Zeilenliste
    // legen. REIN und darum pruefbar.
    //
    // DER ENTWURF DARF NICHTS HINZUFUEGEN. Er nennt nur Reihenfolge und
    // Sichtbarkeit; welche Zeilen es GIBT, entscheidet allein die
    // rechte-gefilterte Liste der Shell. Ein Entwurf, der aus der Zeit vor
    // einem Rechteentzug stammt, kann so keine Sicht zurueckholen — dieselbe
    // Linie wie applyViewPrefs in cockpit.js.
    function entwurfAnwenden(rows, entwurf) {
        if (!entwurf || !entwurf.length) { return (rows || []).slice(); }
        var rang = {}, sicht = {};
        entwurf.forEach(function (e, i) {
            if (!e || typeof e.key !== 'string') { return; }
            rang[e.key] = i;
            sicht[e.key] = (e.sichtbar !== false);
        });
        var bekannt = [], neu = [];
        (rows || []).forEach(function (r, i) {
            var k = {};
            for (var f in r) {
                if (Object.prototype.hasOwnProperty.call(r, f)) { k[f] = r[f]; }
            }
            if (Object.prototype.hasOwnProperty.call(rang, r.id)) {
                k.versteckt = !sicht[r.id];
                k._r = rang[r.id];
                bekannt.push(k);
            } else {
                // Seit dem Entwurf hinzugekommen -> hinten und SICHTBAR.
                k._r = i;
                neu.push(k);
            }
        });
        bekannt.sort(function (a, b) { return a._r - b._r; });
        neu.sort(function (a, b) { return a._r - b._r; });
        return bekannt.concat(neu).map(function (v) { delete v._r; return v; });
    }

    // =========================================================================
    // 2) DOM (nur Browser/jsdom).
    // =========================================================================

    // Build 546: Browser-Zwischenspeicher des NOCH NICHT gespeicherten
    // Entwurfs (Muster Build 487/488). Eigener versionierter Schluessel.
    var DRAFT_KEY = 'aiw.viewprefs.draft.v1';
    function _ls() {
        try {
            return (typeof localStorage !== 'undefined') ? localStorage : null;
        } catch (e) { return null; }   // abgeschaltet/geblockt -> kein Fehler
    }
    function entwurfSchreiben(nutzlast) {
        var ls = _ls();
        if (!ls) { return false; }
        try {
            ls.setItem(DRAFT_KEY, JSON.stringify(nutzlast));
            return true;
        } catch (e) { return false; }  // z.B. Speicher voll
    }
    function entwurfLesen() {
        var ls = _ls();
        if (!ls) { return null; }
        try {
            var roh = ls.getItem(DRAFT_KEY);
            if (!roh) { return null; }
            var d = JSON.parse(roh);
            return (d && d.length !== undefined) ? d : null;
        } catch (e) { return null; }   // unlesbar -> behandeln wie 'keiner'
    }
    function entwurfVerwerfen() {
        var ls = _ls();
        if (!ls) { return; }
        try { ls.removeItem(DRAFT_KEY); } catch (e) { /* egal */ }
    }

    // Ungespeicherter Stand? Die Shell fragt das, bevor sie die Sicht
    // verlaesst. Ausserhalb der Sicht ist die Antwort immer 'nein'.
    var _dirty = false;
    function hatUngespeichertes() { return _dirty === true; }

    var _sortable = null;
    function destroySortable() {
        if (_sortable) {
            try { _sortable.destroy(); } catch (e) { /* schon abgebaut */ }
            _sortable = null;
        }
    }

    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    /**
     * renderViewPrefs(mainEl, data, cb)
     *
     * data = {
     *   rows:      [ {id, label, group, versteckt} ]  — bereits RECHTE-GEFILTERT
     *   gespeichert: [ {key, sichtbar} ]              — der geladene Stand
     *   unbekannt: [ {art, key} ]                     — verwaiste Eintraege
     *   fehler:    string|null                        — Abruf fehlgeschlagen
     * }
     * cb = { onSave(nutzlast), onReset() }
     */
    function renderViewPrefs(mainEl, data, cb) {
        if (!mainEl) { return null; }
        destroySortable();
        mainEl.textContent = '';
        data = data || {};
        cb = cb || {};

        var rows = (data.rows || []).slice();
        var gespeichert = data.gespeichert || [];

        // Zwischengespeicherten Entwurf zurueckholen — aber nur, wenn er sich
        // vom gespeicherten Stand UNTERSCHEIDET. Ein Entwurf, der dasselbe
        // sagt wie die Datenbank, ist keiner und wuerde nur einen falschen
        // "ungespeichert"-Zustand erzeugen.
        var entwurf = entwurfLesen();
        var entwurfAktiv = false;
        if (entwurf) {
            var probe = entwurfAnwenden(rows, entwurf);
            if (istGeaendert(probe, gespeichert)) {
                rows = probe;
                entwurfAktiv = true;
            } else {
                entwurfVerwerfen();
            }
        }

        mainEl.appendChild(el('h2', 'aiw-pagehead', 'Ansicht anpassen'));
        mainEl.appendChild(el('p', 'aiw-pagesub',
            'Reihenfolge und Sichtbarkeit der Bereiche in der linken '
            + 'Navigation — Gruppen untereinander, Bereiche innerhalb ihrer '
            + 'Gruppe. Die Einstellung gilt nur für Sie.'));

        // Kein stiller Fehlpfad: ein fehlgeschlagener Abruf sieht NICHT aus
        // wie "nichts eingestellt".
        if (data.fehler) {
            var f = el('div', 'aiw-vp-fehler',
                'Die gespeicherte Einstellung konnte nicht geladen werden ('
                + data.fehler + '). Angezeigt wird die Werkseinstellung. '
                + 'Ein Speichern würde die bisherige Einstellung ersetzen.');
            mainEl.appendChild(f);
        }

        // Verwaiste Eintraege werden BENANNT (Grundregel 1) — sie zeigen auf
        // Sichten, die es nicht mehr gibt. Aufgeraeumt wird nicht automatisch:
        // darueber soll jemand entscheiden.
        if (data.unbekannt && data.unbekannt.length) {
            var u = el('div', 'aiw-vp-hinweis');
            u.appendChild(el('strong', null,
                data.unbekannt.length + ' gespeicherte Einträge zeigen auf '
                + 'Bereiche, die es nicht mehr gibt: '));
            u.appendChild(document.createTextNode(
                data.unbekannt.map(function (x) { return x.key; }).join(', ')
                + '. Sie wirken sich nicht aus. Ein Zurücksetzen entfernt sie.'));
            mainEl.appendChild(u);
        }

        // Ein zurueckgeholter Entwurf wird BENANNT. Sonst saehe die Sicht beim
        // Wiederbetreten anders aus als beim Verlassen, ohne dass jemand
        // wuesste warum — und ein spaeteres "Speichern" schriebe einen Stand
        // fest, den die Person nicht mehr auf dem Schirm hatte.
        if (entwurfAktiv) {
            mainEl.appendChild(el('div', 'aiw-vp-hinweis',
                'Ein nicht gespeicherter Zwischenstand aus dieser Sitzung '
                + 'wurde wiederhergestellt. "Speichern" schreibt ihn fest, '
                + '"Zurücksetzen" verwirft ihn zusammen mit der gespeicherten '
                + 'Einstellung.'));
        }

        var kopf = el('p', 'aiw-vp-zahlen');
        mainEl.appendChild(kopf);

        var liste = el('div', 'aiw-vp-liste');
        liste.setAttribute('role', 'list');
        mainEl.appendChild(liste);

        var leiste = el('div', 'aiw-vp-leiste');
        var btnSave = el('button', 'aiw-btn aiw-btn-primary', 'Speichern');
        btnSave.setAttribute('type', 'button');
        var btnReset = el('button', 'aiw-btn', 'Auf Werkseinstellung zurücksetzen');
        btnReset.setAttribute('type', 'button');
        var meldung = el('span', 'aiw-vp-meldung');
        leiste.appendChild(btnSave);
        leiste.appendChild(btnReset);
        leiste.appendChild(meldung);
        mainEl.appendChild(leiste);

        function zeichne() {
            var z = zusammenfassung(rows);
            kopf.textContent = z.gesamt + ' Bereiche · ' + z.sichtbar
                + ' sichtbar · ' + z.versteckt + ' ausgeblendet';

            liste.textContent = '';
            // Build 568: ZWEI EBENEN. Die Gruppen bilden die aeussere Ordnung,
            // die Sichten die innere. Beide werden mit denselben Pfeilen
            // bedient - eine Ebene mit Pfeilen und eine mit Ziehen waere zwei
            // Bedienarten fuer dieselbe Sache.
            var bloecke = gruppenAus(rows);
            bloecke.forEach(function (block, gidx) {
                var gkopf = el('div', 'aiw-vp-gruppenkopf');
                gkopf.setAttribute('data-group', block.gruppe);

                var gname = el('span', 'aiw-vp-gruppenname', block.gruppe);
                gkopf.appendChild(gname);
                var gzahl = el('span', 'aiw-vp-gruppenzahl',
                    block.zeilen.length + (block.zeilen.length === 1
                        ? ' Bereich' : ' Bereiche'));
                gkopf.appendChild(gzahl);

                var gup = el('button', 'aiw-vp-pfeil', '▲');
                gup.setAttribute('type', 'button');
                gup.setAttribute('aria-label',
                    'Gruppe "' + block.gruppe + '" nach oben');
                gup.disabled = (gidx === 0);
                gup.addEventListener('click', function () {
                    rows = gruppeVerschieben(rows, block.gruppe, -1);
                    zeichne();
                });
                var gdown = el('button', 'aiw-vp-pfeil', '▼');
                gdown.setAttribute('type', 'button');
                gdown.setAttribute('aria-label',
                    'Gruppe "' + block.gruppe + '" nach unten');
                gdown.disabled = (gidx === bloecke.length - 1);
                gdown.addEventListener('click', function () {
                    rows = gruppeVerschieben(rows, block.gruppe, 1);
                    zeichne();
                });
                gkopf.appendChild(gup);
                gkopf.appendChild(gdown);
                liste.appendChild(gkopf);

                block.zeilen.forEach(function (r, idx) {
                    _zeileZeichnen(r, idx, block.zeilen.length);
                });
            });

            function _zeileZeichnen(r, idx, anzahlInGruppe) {
                var zeile = el('div', 'aiw-vp-zeile'
                    + (r.versteckt ? ' is-versteckt' : ''));
                zeile.setAttribute('role', 'listitem');
                zeile.setAttribute('data-view-id', r.id);

                var griff = el('span', 'aiw-vp-griff', '⠿');
                griff.setAttribute('aria-hidden', 'true');
                zeile.appendChild(griff);

                var cb2 = document.createElement('input');
                cb2.type = 'checkbox';
                cb2.className = 'aiw-vp-schalter';
                cb2.checked = !r.versteckt;
                cb2.id = 'aiw-vp-cb-' + r.id;
                cb2.setAttribute('aria-label',
                    'Bereich "' + r.label + '" anzeigen');
                cb2.addEventListener('change', function () {
                    rows = umschalten(rows, r.id);
                    zeichne();
                });
                zeile.appendChild(cb2);

                var lab = el('label', 'aiw-vp-label', r.label);
                lab.setAttribute('for', cb2.id);
                zeile.appendChild(lab);
                // Die Gruppe steht jetzt im Kopf darueber - sie ein zweites
                // Mal je Zeile zu wiederholen waere Laerm.

                // Pfeile: Ziehen ist nicht tastaturbedienbar (a11y, Muster
                // cockpit_notes.js Build 407).
                var up = el('button', 'aiw-vp-pfeil', '▲');
                up.setAttribute('type', 'button');
                up.setAttribute('aria-label', 'Nach oben');
                up.disabled = (idx === 0);
                up.addEventListener('click', function () {
                    rows = verschiebeInGruppe(rows, r.id, -1);
                    zeichne();
                });
                var down = el('button', 'aiw-vp-pfeil', '▼');
                down.setAttribute('type', 'button');
                down.setAttribute('aria-label', 'Nach unten');
                // Am Rand der GRUPPE ist Schluss, nicht am Rand der Liste:
                // die Zugehoerigkeit einer Sicht legt der Katalog fest.
                down.disabled = (idx === anzahlInGruppe - 1);
                down.addEventListener('click', function () {
                    rows = verschiebeInGruppe(rows, r.id, 1);
                    zeichne();
                });
                zeile.appendChild(up);
                zeile.appendChild(down);

                liste.appendChild(zeile);
            }

            // Der ungespeicherte Zustand wird an EINER Stelle bestimmt und
            // von dort aus sowohl gemerkt (Warnung beim Verlassen) als auch
            // zwischengespeichert. Zwei Stellen koennten auseinanderlaufen.
            _dirty = istGeaendert(rows, gespeichert);
            btnSave.disabled = !_dirty;
            if (_dirty) {
                entwurfSchreiben(zuNutzlast(rows));
                meldung.textContent = 'Nicht gespeichert.';
            } else {
                entwurfVerwerfen();
                meldung.textContent = 'Keine ungespeicherten Änderungen.';
            }

            destroySortable();
            if (typeof window !== 'undefined' && window.Sortable) {
                _sortable = window.Sortable.create(liste, {
                    handle: '.aiw-vp-griff',
                    draggable: '.aiw-vp-zeile',
                    animation: 150,
                    onEnd: function () {
                        // Die DOM-Folge ist nach dem Ablegen die Wahrheit;
                        // rows wird daraus NEU aufgebaut, damit es genau EINE
                        // Reihenfolge gibt.
                        var neu = [];
                        var knoten = liste.querySelectorAll('.aiw-vp-zeile');
                        for (var i = 0; i < knoten.length; i++) {
                            var id = knoten[i].getAttribute('data-view-id');
                            for (var j = 0; j < rows.length; j++) {
                                if (rows[j].id === id) {
                                    neu.push(rows[j]);
                                    break;
                                }
                            }
                        }
                        rows = neu;
                        zeichne();
                    }
                });
            }
        }

        btnSave.addEventListener('click', function () {
            if (typeof cb.onSave === 'function') {
                log('Speichern', rows.length, 'Zeilen');
                cb.onSave(zuNutzlast(rows));
            }
        });
        btnReset.addEventListener('click', function () {
            if (typeof cb.onReset === 'function') { cb.onReset(); }
        });

        zeichne();
        log('gerendert:', rows.length, 'Bereiche');
        return { zeilen: function () { return rows.slice(); } };
    }

    // =========================================================================
    // 3) UMD-artiger Ausgang: window (Browser) UND module.exports (vitest).
    // =========================================================================
    // nachErfolg: von der Shell NACH einem bestaetigten Schreibvorgang
    // aufzurufen. Erst dann ist der Entwurf ueberholt — nicht schon beim
    // Klick (kein optimistisches UI).
    function nachErfolg() {
        entwurfVerwerfen();
        _dirty = false;
    }

    // cleanup: beim Sichtwechsel. Setzt AUCH das dirty-Flag zurueck — die
    // Warnung ist Sache der Shell und wird VOR cleanupView() gestellt.
    // Der Entwurf im localStorage bleibt bewusst LIEGEN: er ist genau fuer
    // den Fall da, dass jemand die Sicht verlaesst und wiederkommt.
    function cleanup() {
        destroySortable();
        _dirty = false;
    }

    var API = {
        verschiebe: verschiebe,
        gruppenAus: gruppenAus,
        flachAus: flachAus,
        gruppeVerschieben: gruppeVerschieben,
        verschiebeInGruppe: verschiebeInGruppe,
        umschalten: umschalten,
        zuNutzlast: zuNutzlast,
        zusammenfassung: zusammenfassung,
        istGeaendert: istGeaendert,
        entwurfAnwenden: entwurfAnwenden,
        entwurfLesen: entwurfLesen,
        entwurfSchreiben: entwurfSchreiben,
        entwurfVerwerfen: entwurfVerwerfen,
        hatUngespeichertes: hatUngespeichertes,
        nachErfolg: nachErfolg,
        renderViewPrefs: renderViewPrefs,
        cleanup: cleanup
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitViewPrefs = API; }
})();
