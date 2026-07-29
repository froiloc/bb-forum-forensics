// =============================================================================
// management/server/static/cockpit_minutenrechner.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Hilfswerkzeug
// =============================================================================
// Zweck:
//   Ein kleiner Umrechner Stunden/Minuten/Prozent -> MINUTEN, als bewegliches
//   Fenster. Arbeitszeiten werden in diesem Werkzeug in Minuten gefuehrt
//   (person_worktime.*_min), gedacht und gesprochen wird aber in Stunden:
//   "sieben Komma fuenf" muss jemand sonst im Kopf mal sechzig nehmen. Genau
//   dort entstehen die Zahlendreher, die spaeter in einer Kapazitaetsrechnung
//   stehen.
//
// EIGENE DATEI (Grundregel 10): der Rechner haengt an keiner Sicht. Er wird
//   hier von der Kapazitaetspflege gerufen, ist aber ueberall verwendbar, wo
//   Minuten einzugeben sind - deshalb kennt er das Kapazitaetsmodul nicht und
//   bekommt sein Ziel von aussen gesagt.
//
// KEIN MODALES SPERREN: das Fenster blockiert die Seite NICHT. Genau das ist
//   der Zweck (mc 2026-07-29) - man soll bei offenem Rechner ein Eingabefeld
//   im Formular anklicken koennen, um das Ergebnis dorthin zu uebernehmen.
//   Deshalb: kein Ueberlagerungsschirm, kein Schliessen bei Klick daneben,
//   kein Schliessen mit Escape. Zu geht es NUR ueber das X.
//
// RUNDUNG WIRD BENANNT, NICHT VERSCHLUCKT: die Datenbank kennt nur ganze
//   Minuten (INTEGER). 7,3 h sind 438 Minuten - der Rechner sagt dann
//   ausdruecklich "gerundet von 438,0", damit niemand spaeter eine
//   Abweichung von einer Minute sucht, die er selbst erzeugt hat.
//
// DEUTSCHE EINGABE: '7,5' wird zu '7.5'. Wer auf einer deutschen Tastatur im
//   Zahlenblock tippt, bekommt ein Komma; parseFloat('7,5') waere 7 - also
//   still ein halber Arbeitstag weniger. Das ist kein Schoenheitsfehler,
//   sondern ein Datenfehler, und deshalb wird umgesetzt statt gewarnt.
//
// BUILD 565: die Zielanzeige folgt dem Fokus. Bis dahin wurde sie nur bei
//   Eingaben IM Rechner aufgefrischt - wer draussen ein anderes Feld anklickte,
//   sah weiter das alte Ziel und erfuhr erst beim Uebernehmen, wohin der Wert
//   ging (Befund mc).
//
// Version: v0.8.565 · Build: 565 · 2026-07-29
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
        args.unshift('[AIW-Minutenrechner]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    // zahlLesen: deutsche wie englische Schreibweise -> Zahl oder null.
    // Leerer Text ist KEINE 0, sondern "keine Angabe" - der Aufrufer
    // entscheidet, was das bedeutet (Stunden leer = 0 h, Prozent leer = 100 %).
    function zahlLesen(text) {
        if (text === null || text === undefined) { return null; }
        var s = String(text).trim().replace(',', '.');
        if (s === '') { return null; }
        if (!/^-?\d*\.?\d+$/.test(s)) { return null; }
        var z = parseFloat(s);
        return isFinite(z) ? z : null;
    }

    // rechnen: (Stunden, Minuten, Prozent) -> Ergebnis.
    // Rueckgabe:
    //   { ok:true, minuten:int, roh:number, gerundet:bool, text:string }
    //   { ok:false, fehler:string, feld:string }
    //
    // Die Reihenfolge ist (h*60 + min) * pct/100 und nicht h*60 + min*pct/100:
    // der Prozentsatz bezieht sich auf die GESAMTE eingegebene Dauer. Alles
    // andere waere an dieser Stelle eine Ueberraschung.
    function rechnen(stundenText, minutenText, prozentText) {
        var h = zahlLesen(stundenText);
        var m = zahlLesen(minutenText);
        var p = zahlLesen(prozentText);

        if (stundenText !== '' && stundenText !== null
                && stundenText !== undefined && h === null) {
            return { ok: false, feld: 'stunden',
                     fehler: 'Stunden: keine gueltige Zahl.' };
        }
        if (minutenText !== '' && minutenText !== null
                && minutenText !== undefined && m === null) {
            return { ok: false, feld: 'minuten',
                     fehler: 'Minuten: keine gueltige Zahl.' };
        }
        if (prozentText !== '' && prozentText !== null
                && prozentText !== undefined && p === null) {
            return { ok: false, feld: 'prozent',
                     fehler: 'Prozent: keine gueltige Zahl.' };
        }
        h = (h === null) ? 0 : h;
        m = (m === null) ? 0 : m;
        p = (p === null) ? 100 : p;      // Vorgabe 100 % (mc)

        if (h < 0 || m < 0) {
            return { ok: false, feld: h < 0 ? 'stunden' : 'minuten',
                     fehler: 'Negative Dauer ergibt keine Arbeitszeit.' };
        }
        if (p < 0) {
            return { ok: false, feld: 'prozent',
                     fehler: 'Negativer Anteil ergibt keine Arbeitszeit.' };
        }

        var roh = (h * 60 + m) * p / 100;
        var gerundet = Math.round(roh);
        var wurdeGerundet = Math.abs(roh - gerundet) > 1e-9;
        var text = gerundet + ' Minuten';
        if (wurdeGerundet) {
            // Die Rundung wird BENANNT. Wer 438 statt 438,6 in der Datenbank
            // findet, soll wissen, woher der Unterschied kommt.
            text += ' (gerundet von ' + roh.toFixed(2).replace('.', ',') + ')';
        }
        return { ok: true, minuten: gerundet, roh: roh,
                 gerundet: wurdeGerundet, text: text };
    }

    // zielName: technisches Feld -> lesbarer Name fuer die Zielanzeige.
    // Das Uebernehmen schreibt in ein Feld, das der Rechner nicht sieht -
    // deshalb muss er SAGEN, wohin er schreibt, statt es blind zu tun.
    var _TAGNAMEN = {
        mon_min: 'Montag', tue_min: 'Dienstag', wed_min: 'Mittwoch',
        thu_min: 'Donnerstag', fri_min: 'Freitag', sat_min: 'Samstag',
        sun_min: 'Sonntag'
    };
    function zielName(feldId) {
        if (!feldId) { return null; }
        var key = String(feldId).replace(/^.*-/, '');
        if (_TAGNAMEN[key]) { return _TAGNAMEN[key]; }
        if (/av-min$/.test(feldId)) { return 'Abwesenheit: Minuten'; }
        if (/av-pct$/.test(feldId)) { return 'Abwesenheit: Prozent'; }
        return feldId;
    }

    // =========================================================================
    // 2) FENSTER.
    // =========================================================================

    function _el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    function _feld(id, platzhalter, wert) {
        var i = document.createElement('input');
        i.type = 'text';               // TEXT, nicht number: sonst verwirft der
        i.id = id;                     // Browser das Komma still (Firefox) oder
        i.className = 'aiw-input';     // liefert '' (Chrome) - beides waere ein
        i.placeholder = platzhalter || '';   // stiller Verlust der Eingabe.
        if (wert !== undefined) { i.value = wert; }
        return i;
    }

    /**
     * oeffnen(opts) -> Steuerobjekt
     *   opts.host           — Elternknoten (Vorgabe: document.body)
     *   opts.zielGeben()    — liefert { id, label } des zuletzt gewaehlten
     *                         Eingabefelds oder null
     *   opts.uebernehmen(minuten) — schreibt das Ergebnis dorthin
     *   opts.position       — { links, oben } in Pixeln
     * Rueckgabe: { wurzel, schliessen, aktualisieren, istOffen }
     */
    function oeffnen(opts) {
        opts = opts || {};
        var host = opts.host
            || (typeof document !== 'undefined' ? document.body : null);
        if (!host) { return null; }

        var wurzel = _el('div', 'aiw-rechner');
        wurzel.id = 'aiw-rechner';
        wurzel.setAttribute('role', 'dialog');
        wurzel.setAttribute('aria-label', 'Minutenrechner');
        // Positionierung inline: sie wird beim Ziehen ohnehin berechnet und
        // gehoert damit nicht ins Stylesheet.
        wurzel.style.position = 'fixed';
        wurzel.style.left = ((opts.position && opts.position.links) || 40) + 'px';
        wurzel.style.top = ((opts.position && opts.position.oben) || 80) + 'px';
        wurzel.style.zIndex = '9000';

        // --- Titelzeile (Griff zum Ziehen + X) ---
        var kopf = _el('div', 'aiw-rechner-kopf');
        kopf.appendChild(_el('span', 'aiw-rechner-titel', 'Minutenrechner'));
        var zu = _el('button', 'aiw-rechner-zu', '\u00D7');
        zu.type = 'button';
        zu.id = 'aiw-rechner-zu';
        zu.setAttribute('aria-label', 'Rechner schliessen');
        kopf.appendChild(zu);
        wurzel.appendChild(kopf);

        // --- Eingaben ---
        var koerper = _el('div', 'aiw-rechner-koerper');
        var fStunden = _feld('aiw-rechner-h', 'z. B. 7,5');
        var fMinuten = _feld('aiw-rechner-m', 'z. B. 30');
        var fProzent = _feld('aiw-rechner-p', '100', '100');
        [['Stunden', fStunden], ['Minuten', fMinuten],
         ['Prozent', fProzent]].forEach(function (paar) {
            koerper.appendChild(_el('label', 'aiw-label', paar[0]));
            koerper.appendChild(paar[1]);
        });
        wurzel.appendChild(koerper);

        var ergebnis = _el('p', 'aiw-rechner-ergebnis', '0 Minuten');
        ergebnis.id = 'aiw-rechner-ergebnis';
        wurzel.appendChild(ergebnis);

        var zielzeile = _el('p', 'aiw-rechner-ziel', 'Ziel: kein Feld gewaehlt');
        zielzeile.id = 'aiw-rechner-ziel';
        wurzel.appendChild(zielzeile);

        var uebernehmen = _el('button', 'aiw-btn', 'Uebernehmen');
        uebernehmen.type = 'button';
        uebernehmen.id = 'aiw-rechner-uebernehmen';
        wurzel.appendChild(uebernehmen);

        var letztes = null;            // letztes gueltiges Ergebnis
        var doc = host.ownerDocument || document;

        function aktualisieren() {
            var r = rechnen(fStunden.value, fMinuten.value, fProzent.value);
            if (r.ok) {
                letztes = r;
                ergebnis.textContent = r.text;
                ergebnis.classList.remove('aiw-error');
            } else {
                letztes = null;
                ergebnis.textContent = r.fehler;
                ergebnis.classList.add('aiw-error');
            }
            var ziel = (typeof opts.zielGeben === 'function')
                ? opts.zielGeben() : null;
            zielzeile.textContent = ziel
                ? ('Ziel: ' + (ziel.label || zielName(ziel.id)))
                : 'Ziel: kein Feld gewaehlt';
            return r;
        }

        [fStunden, fMinuten, fProzent].forEach(function (f) {
            f.addEventListener('input', aktualisieren);
        });

        // BEFUND mc (Build 561): die Zielzeile wurde NUR bei Eingaben IM
        // Rechner neu geschrieben. Wer das Fenster offen liess und draussen
        // ein anderes Feld anklickte, sah weiter das alte Ziel - und erfuhr
        // erst beim Uebernehmen, wohin der Wert wirklich ging. Das ist genau
        // die Sorte Ueberraschung, die man bei sieben gleichartigen Feldern
        // nicht haben will.
        //
        // Der Rechner horcht deshalb auf FOCUSIN am Dokument. Bewusst nicht
        // auf 'click': mit der Tabulatortaste wechselt man ebenso das Feld,
        // und ein Klick, der keinen Fokus setzt, ist kein Zielwechsel.
        // Ereignisse aus dem Rechner selbst werden uebergangen, sonst
        // ueberschriebe ein Klick in 'Stunden' die Zielanzeige.
        function zielBeobachten(ev) {
            if (wurzel.contains(ev.target)) { return; }
            aktualisieren();
        }
        doc.addEventListener('focusin', zielBeobachten);

        uebernehmen.addEventListener('click', function () {
            var r = aktualisieren();
            if (!r.ok) { return; }
            var ziel = (typeof opts.zielGeben === 'function')
                ? opts.zielGeben() : null;
            if (!ziel) {
                // KEIN STILLES NICHTS: wer auf Uebernehmen drueckt und nichts
                // passiert, haelt das Werkzeug fuer kaputt.
                ergebnis.textContent = r.text
                    + ' — kein Zielfeld gewaehlt. Erst ein Minutenfeld im '
                    + 'Formular anklicken.';
                ergebnis.classList.add('aiw-error');
                return;
            }
            if (typeof opts.uebernehmen === 'function') {
                opts.uebernehmen(r.minuten, ziel);
            }
            ergebnis.textContent = r.text + ' \u2192 '
                + (ziel.label || zielName(ziel.id));
        });

        // --- Ziehen ---
        // Nur ueber die Titelzeile, damit ein Klick in ein Eingabefeld nicht
        // versehentlich das Fenster verschiebt.
        var zieht = false, dx = 0, dy = 0;
        kopf.addEventListener('mousedown', function (ev) {
            if (ev.target === zu) { return; }
            zieht = true;
            dx = ev.clientX - wurzel.offsetLeft;
            dy = ev.clientY - wurzel.offsetTop;
            ev.preventDefault();
        });
        function bewegen(ev) {
            if (!zieht) { return; }
            wurzel.style.left = Math.max(0, ev.clientX - dx) + 'px';
            wurzel.style.top = Math.max(0, ev.clientY - dy) + 'px';
        }
        function loslassen() { zieht = false; }
        doc.addEventListener('mousemove', bewegen);
        doc.addEventListener('mouseup', loslassen);

        function schliessen() {
            doc.removeEventListener('mousemove', bewegen);
            doc.removeEventListener('mouseup', loslassen);
            doc.removeEventListener('focusin', zielBeobachten);
            if (wurzel.parentNode) { wurzel.parentNode.removeChild(wurzel); }
            log('geschlossen');
        }
        zu.addEventListener('click', schliessen);

        host.appendChild(wurzel);
        aktualisieren();
        log('geoeffnet');

        return {
            wurzel: wurzel, schliessen: schliessen,
            aktualisieren: aktualisieren,
            istOffen: function () { return !!wurzel.parentNode; },
            letztesErgebnis: function () { return letztes; }
        };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        zahlLesen: zahlLesen,
        rechnen: rechnen,
        zielName: zielName,
        oeffnen: oeffnen
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWMinutenrechner = API; }
})();
