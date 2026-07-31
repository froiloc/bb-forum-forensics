// =============================================================================
// management/server/static/cockpit_matrix.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Matrix (AP-3B)
// =============================================================================
// Zweck (Frontend zu Build 537/538):
//   Zeigt die Dringlichkeits-/Erkenntnislage-Matrix aus GET /api/matrix — die
//   Rangfolge der Faelle nach BEARBEITUNGSDRINGLICHKEIT (X) und
//   ERKENNTNISLAGE (Y), aufgeteilt in vier Quadranten plus ein fuenftes Feld
//   fuer das nicht Bestimmbare.
//
// DIE WICHTIGSTE AUSSAGE DIESER DATEI:
//   DIESE SICHT IST KEINE BEWEISWUERDIGUNG. § 261 StPO ordnet die freie
//   Beweiswuerdigung dem Gericht zu; eine Zahl, die sie vorwegnaehme, waere in
//   der Akte ein Angriffspunkt gegen die gesamte Auswertung. Die Zweckbindung
//   wird deshalb NICHT hier formuliert, sondern WORTGLEICH aus dem
//   Gewichtungssatz uebernommen (matrix_weights.json) und ganz oben gezeigt.
//   Fehlt sie in der Antwort, MELDET die Sicht das — eine zweite Formulierung
//   im Quelltext waere eine zweite Wahrheitsquelle, und eine stillschweigend
//   weiterarbeitende Sicht waere keine Kontrolle.
//
// ZWEITE AUSSAGE: DIE MATRIX SCHREIBT KEINE PRIORITAET. Sie schlaegt eine
//   Reihenfolge vor, die ein Mensch bewertet. 'cases.priority' bleibt
//   unberuehrt (Entscheidung mc). Auch diese Zusicherung faehrt in der Antwort
//   mit ('schreibt_keine_prioritaet') und wird geprueft.
//
// DAS FUENFTE FELD IST DER KERN DER SICHT:
//   Ein Fall ohne bestimmbare Dringlichkeit bekommt KEINE 0, sondern den
//   Quadranten 'nicht_bestimmbar' — und steht damit OBEN, nicht unten. Eine 0
//   saehe aus wie 'nicht eilig'; tatsaechlich heisst sie 'ungeprueft'. Seine
//   uebrigen Punkte gehen nicht verloren: sie stehen in
//   'dringlichkeit_mindestens' und werden hier als UNTERGRENZE gezeigt
//   ('mind. N'), nie als Wert.
//
// DREI ZUSTAENDE DER FRIST, DIE EINANDER NIE UEBERDECKEN DUERFEN (Build 538):
//   'nicht_geladen'  — es wurde NICHT nachgesehen (Fristen abgeschaltet oder
//                      kein Verzeichnis).
//   'keine_aussage'  — nachgesehen, aber der Verjaehrungs-Parametersatz ist
//                      nicht bestaetigt: der Monitor VERWEIGERT die
//                      Rechtsfolge.
//   ein Ampelwert    — nachgesehen und gerechnet ('ohne_tatzeit', 'ruht', ...).
//   Die Sicht gibt jedem dieser Zustaende einen EIGENEN Klartext. Sie alle als
//   'keine Frist' zu zeigen waere die folgenschwerste Vereinfachung, die hier
//   moeglich ist.
//
// DAS NACHLADEN (Build 538/539):
//   Die Fristkomponente kostet je Fall bis zu zwei Dateizugriffe; alle uebrigen
//   fuenf Beitraege zusammen kosten fuenf Abfragen auf einer Verbindung.
//   Container-Messung (Build 538): Faktor 13-14, rund 0,7 ms je Fall. Fuer PROD
//   steht die Messung aus (tools/diag_matrix_laufzeit.py). DIE SICHT LAEDT
//   DESHALB ZUNAECHST OHNE FRISTEN und bietet einen Schalter an — mit einem
//   Satz, der sagt, was fehlt. Sobald die PROD-Zahl vorliegt, ist das eine
//   Zeile in cockpit.js (state.matrixFristen) und keine Umbauaktion.
//
// Datenform GET /api/matrix (ManagementApp._matrix):
//   { stichtag, faelle_gesamt, fristen_geladen, fristen_angefordert,
//     fristen_kopf{aussage_moeglich, verweigerungsgrund, params_bestaetigt,...},
//     faelle_ohne_fristzeile, quadranten{q:n}, belastbarkeit_verteilung{b:n},
//     unbekannte_codes{code:n}, fehlende_quellen[], hinweise[],
//     dauer_gesamt_ms, dauer_fristen_ms,
//     gewichte_stand, zweckbindung, vorbehalte[], dringlichkeit_max,
//     erkenntnislage_max, schwelle_dringlichkeit, schwelle_erkenntnislage,
//     ausgeschlossene_kriterien[], konfidenz_punkte{}, identitaet_punkte{},
//     ist_keine_beweiswuerdigung: true, schreibt_keine_prioritaet: true,
//     zellen: [ { subject_id, username, dringlichkeit,
//                 dringlichkeit_mindestens, dringlichkeit_bestimmbar,
//                 dringlichkeit_belastbarkeit, dringlichkeit_grund,
//                 erkenntnislage, erkenntnislage_bestimmbar,
//                 n_kriterien_matrix, quadrant, quadrant_bedeutung,
//                 beitraege[{achse,code,punkte,grund}], vermerke[],
//                 unbekannte_codes[] }, ... ] }
//   Bei einem Fehler reicht loadMatrix {error: <text>} durch.
//
// KEIN SCHREIBPFAD. Die einzigen Bedienelemente sind der Fristen-Schalter und
//   die Aufklappflaechen je Zeile — beide aendern nur die ANSICHT.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG).
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen fassen NIE das DOM an;
//   UMD-Ausgang -> vitest testet den ECHTEN Code. Alle Texte ueber textContent
//   (Kontonamen sind beliebiger UTF-8 aus einem multilingualen Forum).
//
// Version: v0.8.539 · Build: 539 · 2026-07-26
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
        args.unshift('[AIW-Matrix]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // Zustandstabellen. Sie sind die EINZIGEN Stellen, an denen ein
    // Backend-Code eine Farbe und einen Klartext bekommt. Ein Test haelt sie
    // gegen die Listen des Backends (QUADRANTEN, BELASTBARKEITEN), damit ein
    // neuer Wert nicht farblos — und damit praktisch unsichtbar — in der Sicht
    // landet. Dasselbe Muster wie AMPEL in cockpit_limitation.js.
    // =========================================================================

    // REIHENFOLGE = DRINGLICHKEIT DER BEACHTUNG, nicht Alphabet.
    // 'nicht_bestimmbar' steht GANZ OBEN: ungeprueft ist nicht unverdaechtig
    // (dieselbe Regel wie im Fristenmonitor, und das Backend sortiert bereits
    // so — hier wird NICHT neu sortiert, sondern nur gruppiert).
    var QUADRANT = {
        nicht_bestimmbar: {
            cls: 'is-unbestimmbar', rang: 0,
            label: 'NICHT BESTIMMBAR',
            kurz: 'Mindestens eine Achse fehlt — ungeprüft, nicht '
                + 'unverdächtig.'
        },
        gefaehrlich: {
            cls: 'is-gefaehrlich', rang: 1,
            label: 'Dringend bei dünner Erkenntnislage',
            kurz: 'Hier droht der Fristablauf, bevor überhaupt ermittelt '
                + 'wurde.'
        },
        arbeitsreif: {
            cls: 'is-arbeitsreif', rang: 2,
            label: 'Arbeitsreif',
            kurz: 'Hohe Dringlichkeit bei belastbarer Erkenntnislage.'
        },
        belegt_nicht_eilig: {
            cls: 'is-belegt', rang: 3,
            label: 'Belegt, ohne Zeitdruck',
            kurz: 'Belastbare Erkenntnislage ohne Zeitdruck.'
        },
        nachrangig: {
            cls: 'is-nachrangig', rang: 4,
            label: 'Nachrangig',
            kurz: 'Weder Zeitdruck noch belastbare Erkenntnislage.'
        }
    };

    // Die Belastbarkeit der Dringlichkeitszahl (Entscheidung mc M-1). Sie ist
    // ORTHOGONAL zum Wert und bekommt deshalb eine eigene Auszeichnung statt
    // eines Farbabschlags — presste man beides in eine Skala, wuerde
    // 'vorlaeufig UND dringend' unsichtbar, und das ist die operativ
    // wichtigste Kombination.
    var BELASTBARKEIT = {
        festgestellt: { cls: 'is-festgestellt',
                        label: 'festgestellte Tatzeit' },
        vorlaeufig:   { cls: 'is-vorlaeufig',
                        label: 'VORLÄUFIG (Datum nicht festgestellt)' },
        ohne_frist:   { cls: 'is-ohne-frist',
                        label: 'ohne Fristanteil' }
    };

    // Warum eine Dringlichkeit NICHT bestimmbar ist. Die Werte stammen aus
    // urgency_matrix._dringlichkeit: entweder 'nicht_geladen' (Build 538),
    // 'restlaufzeit_fehlt' (Widerspruch im Datensatz) oder ein AMPELWERT des
    // Fristenmonitors, der keine Restlaufzeit hergibt.
    var GRUND = {
        nicht_geladen: 'Die Fristen wurden NICHT geladen — es wurde nicht '
            + 'nachgesehen. Das ist etwas anderes als "keine Frist".',
        keine_aussage: 'Der Verjährungs-Parametersatz ist nicht bestätigt; '
            + 'der Fristenmonitor VERWEIGERT jede Rechtsfolge. Es wurde '
            + 'nachgesehen — eine Aussage ist nicht möglich.',
        ohne_tatzeit: 'Kein Fristbeginn belegt.',
        ohne_anker: 'Ersatzanker für diese Tatbestände nicht zugelassen.',
        ohne_fassung: 'Keine Fassung zur Tatzeit hinterlegt.',
        ruht: 'Die Frist ruht möglicherweise (§ 78b I Nr. 1 StGB) — das hängt '
            + 'am Opferalter, das nicht in den Daten steht.',
        restlaufzeit_fehlt: 'WIDERSPRUCH: die Ampel verspricht eine '
            + 'Restlaufzeit, es kommt aber keine. Der Fall wird nicht '
            + 'gerechnet.'
    };

    // Klartext je Beitragscode. Die PUNKTE stehen daneben; dieser Text sagt,
    // WOFUER sie vergeben wurden. Ein unbekannter Code wird mit seinem
    // Rohnamen gezeigt und NICHT weggelassen.
    var BEITRAG_LABEL = {
        frist: 'Verjährungsfrist',
        wiedervorlage: 'Überfälliger externer Vorgang',
        eskalation: 'Eskalationsmeldung',
        liegezeit: 'Liegezeit',
        unzugewiesen: 'Nicht zugewiesen',
        abdeckung: 'Abdeckung der Bewertung',
        konfidenz: 'Höchste Konfidenz',
        identitaet: 'Identitätszuordnung'
    };

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM).
    // =========================================================================

    // quadrantInfo: Farbe/Klartext zu einem Quadranten. Ein UNBEKANNTER
    // Quadrant wird als solcher gekennzeichnet und NICHT auf einen bekannten
    // abgebildet — sonst bekaeme ein neuer Backend-Zustand stillschweigend
    // eine falsche Einordnung.
    function quadrantInfo(q) {
        var i = QUADRANT[q];
        if (i) { return i; }
        return { cls: 'is-unbekannt', rang: 98,
                 label: 'unbekannter Quadrant (' + String(q) + ')',
                 kurz: 'Dieser Wert ist der Sicht nicht bekannt. Bitte '
                     + 'melden — er wird NICHT eingeordnet.' };
    }

    function belastbarkeitInfo(b) {
        var i = BELASTBARKEIT[b];
        if (i) { return i; }
        return { cls: 'is-unbekannt',
                 label: 'unbekannte Belastbarkeit (' + String(b) + ')' };
    }

    function beitragLabel(code) {
        return BEITRAG_LABEL[code] || ('unbekannter Beitrag (' + String(code)
            + ')');
    }

    // zweckbindungText: die Zweckbindung WORTGLEICH aus dem Gewichtungssatz.
    // Sie wird hier NICHT formuliert. Fehlt sie, ist das ein Missstand und
    // wird als solcher benannt.
    function zweckbindungText(data) {
        var d = data || {};
        if (d.ist_keine_beweiswuerdigung === true && d.zweckbindung) {
            return String(d.zweckbindung);
        }
        return 'ACHTUNG: Die Antwort trägt die Zweckbindung NICHT mit. '
            + 'Behandeln Sie keine Zahl dieser Sicht als Bewertung eines '
            + 'Beschuldigten, bevor die Herkunft der Antwort geklärt ist '
            + '(§ 261 StPO).';
    }

    function zweckbindungOk(data) {
        return !!(data && data.ist_keine_beweiswuerdigung === true
                  && data.zweckbindung);
    }

    // prioritaetText: die zweite Zusicherung. Dieselbe Haltung wie bei
    // 'nur_festgestellte_zitierfaehig' im Fristenmonitor.
    function prioritaetText(data) {
        if (data && data.schreibt_keine_prioritaet === true) {
            return 'Diese Sicht SCHREIBT KEINE PRIORITÄT. Die Reihenfolge ist '
                + 'ein Vorschlag; cases.priority bleibt unberührt und wird '
                + 'weiterhin von Menschen gesetzt.';
        }
        return 'ACHTUNG: Die Antwort trägt die Zusicherung "schreibt keine '
            + 'Priorität" NICHT mit. Vor jeder Übernahme in die Fallsteuerung '
            + 'ist die Herkunft der Antwort zu klären.';
    }

    function prioritaetOk(data) {
        return !!(data && data.schreibt_keine_prioritaet === true);
    }

    // fristenText: der Satz zum Ladezustand der Fristkomponente. Er
    // unterscheidet die DREI Zustaende und ist der wichtigste erklaerende Satz
    // der Sicht.
    function fristenText(data) {
        var d = data || {};
        if (d.fristen_geladen !== true) {
            return 'OHNE FRISTEN: die Verjährungsfristen sind in dieser '
                + 'Ansicht NICHT geladen. Jede Dringlichkeit ist deshalb eine '
                + 'UNTERGRENZE ("mind. N") — kein Fall ist so wenig dringlich, '
                + 'wie er hier aussieht. Der Fristanteil trägt bis zu '
                + (fristAnteilMax(d)) + ' der ' + (d.dringlichkeit_max || '?')
                + ' möglichen Punkte.';
        }
        var kopf = d.fristen_kopf || {};
        if (kopf.aussage_moeglich === false) {
            return 'FRISTEN GELADEN, ABER OHNE AUSSAGE: '
                + (kopf.verweigerungsgrund
                    || 'Der Verjährungs-Parametersatz ist nicht bestätigt.')
                + ' Es wurde nachgesehen — die Rechtsfolge fehlt. Das ist '
                + 'NICHT dasselbe wie "keine Frist".';
        }
        return 'Fristen geladen und gerechnet (Parametersatz bestätigt). Der '
            + 'Fristanteil ist in den Dringlichkeitswerten enthalten.';
    }

    // fristAnteilMax: der groesste Fristbeitrag, den der Gewichtungssatz
    // vorsieht. Er wird aus 'konfidenz_punkte'/'identitaet_punkte' NICHT
    // ableitbar, deshalb kommt er aus dem Unterschied: dringlichkeit_max minus
    // der Summe der uebrigen Beitraege ist NICHT sauber bestimmbar, also wird
    // hier ausdruecklich der Wert genannt, den das Backend mitliefert — und
    // wenn es ihn nicht mitliefert, ein Fragezeichen. Geraten wird nichts.
    function fristAnteilMax(data) {
        var d = data || {};
        if (d.frist_max === undefined || d.frist_max === null) { return '?' }
        return String(d.frist_max);
    }

    // dringlichkeitText: der Zellinhalt der X-Spalte.
    //   bestimmbar  -> die Zahl.
    //   unbestimmbar-> 'mind. N' — der Wert aus dringlichkeit_mindestens.
    // NIE eine 0 fuer 'unbekannt'. Das ist der ganze Punkt des fuenften Feldes.
    function dringlichkeitText(zelle) {
        var z = zelle || {};
        if (z.dringlichkeit_bestimmbar === true
                && z.dringlichkeit !== null && z.dringlichkeit !== undefined) {
            return String(z.dringlichkeit);
        }
        var mind = (z.dringlichkeit_mindestens === null
                    || z.dringlichkeit_mindestens === undefined)
            ? 0 : Number(z.dringlichkeit_mindestens);
        return 'mind. ' + mind;
    }

    // grundText: warum die Dringlichkeit nicht bestimmbar ist — oder null.
    // Ein unbekannter Grund wird mit seinem Rohnamen gezeigt.
    function grundText(zelle) {
        var z = zelle || {};
        if (z.dringlichkeit_bestimmbar === true) { return null; }
        var g = z.dringlichkeit_grund;
        if (!g) {
            return 'Nicht bestimmbar; das Backend nennt keinen Grund. Das ist '
                + 'erklärungsbedürftig.';
        }
        return GRUND[g] || ('Nicht bestimmbar (' + String(g) + ') — dieser '
            + 'Grund ist der Sicht nicht bekannt.');
    }

    // erkenntnislageText: der Zellinhalt der Y-Spalte, mit der Bezugsgroesse.
    // 'identification' ist aus der Abdeckung heraus (Entscheidung mc M-3);
    // die Zahl der gerechneten Kriterien steht deshalb IN der Zeile — sonst
    // liesse sich der Wert nicht gegen /api/results/coverage halten, das ueber
    // ZEHN Kriterien rechnet.
    function erkenntnislageText(zelle) {
        var z = zelle || {};
        if (z.erkenntnislage_bestimmbar === false
                || z.erkenntnislage === null || z.erkenntnislage === undefined) {
            return 'nicht bestimmbar';
        }
        return String(z.erkenntnislage);
    }

    // beitraegeJeAchse: die Beitraege einer Zelle, getrennt nach Achse.
    // REIN — die Aufteilung ist Anzeigelogik und gehoert nicht ins DOM.
    function beitraegeJeAchse(zelle) {
        var out = { dringlichkeit: [], erkenntnislage: [], sonstige: [] };
        ((zelle && zelle.beitraege) || []).forEach(function (b) {
            if (b && b.achse === 'dringlichkeit') { out.dringlichkeit.push(b); }
            else if (b && b.achse === 'erkenntnislage') {
                out.erkenntnislage.push(b);
            } else { out.sonstige.push(b); }
        });
        return out;
    }

    // summeBeitraege: die Punktsumme der Beitraege einer Achse. Sie wird
    // GERECHNET und nicht uebernommen: weicht sie vom ausgewiesenen Achsenwert
    // ab, ist das ein Fehler, den die Sicht ZEIGEN soll (UM18 sichert die
    // Gleichheit im Backend ab — hier ist es die zweite, unabhaengige Probe).
    function summeBeitraege(liste) {
        var s = 0;
        (liste || []).forEach(function (b) { s += Number((b && b.punkte) || 0); });
        return s;
    }

    // beitragStimmig: stimmt die Summe der Dringlichkeitsbeitraege mit dem
    // ausgewiesenen Wert? Bei nicht bestimmbarer Dringlichkeit wird gegen
    // 'dringlichkeit_mindestens' geprueft — dort steht dann die Summe.
    function beitragStimmig(zelle) {
        var z = zelle || {};
        var teile = beitraegeJeAchse(z);
        var soll = (z.dringlichkeit_bestimmbar === true)
            ? Number(z.dringlichkeit || 0)
            : Number(z.dringlichkeit_mindestens || 0);
        return summeBeitraege(teile.dringlichkeit) === soll;
    }

    // quadrantenText: die Verteilung, in der Reihenfolge der Beachtung.
    // 'nicht_bestimmbar' und 'gefaehrlich' werden IMMER genannt, auch mit 0 —
    // die Abwesenheit eines gefaehrlichen Falls ist eine eigene, wichtige
    // Aussage, die nicht durch Weglassen entstehen darf (dieselbe Entscheidung
    // wie zaehlerText in cockpit_limitation.js).
    function quadrantenText(data) {
        var q = (data && data.quadranten) || {};
        var immer = { nicht_bestimmbar: 1, gefaehrlich: 1 };
        var reihenfolge = Object.keys(QUADRANT).sort(function (a, b) {
            return QUADRANT[a].rang - QUADRANT[b].rang;
        });
        var teile = [];
        reihenfolge.forEach(function (k) {
            var n = q[k] || 0;
            if (n > 0 || immer[k]) { teile.push(QUADRANT[k].label + ': ' + n); }
        });
        Object.keys(q).forEach(function (k) {
            if (!QUADRANT[k]) { teile.push('unbekannt (' + k + '): ' + q[k]); }
        });
        return teile.join(' · ');
    }

    // belastbarkeitText: die Verteilung ueber die Belastbarkeitsachse.
    // GENERISCH gezaehlt (alle gelieferten Schluessel), damit ein neuer Wert
    // nicht aus der Summe faellt.
    function belastbarkeitText(data) {
        var bv = (data && data.belastbarkeit_verteilung) || {};
        var schluessel = Object.keys(bv);
        if (!schluessel.length) { return null; }
        return 'Grundlage der Dringlichkeitszahlen: '
            + schluessel.sort().map(function (k) {
                return belastbarkeitInfo(k).label + ': ' + bv[k];
            }).join(' · ') + '.';
    }

    // massstabText: der angewandte Massstab. Ohne ihn ist keine Einordnung
    // nachrechenbar — dieselbe Entscheidung wie in cockpit_limitation.js.
    function massstabText(data) {
        var d = data || {};
        var t = [];
        t.push('Stichtag: ' + (d.stichtag || '—'));
        t.push('Gewichtungssatz: Stand ' + (d.gewichte_stand || '—'));
        t.push('Achsenmaxima: Dringlichkeit ' + (d.dringlichkeit_max || '?')
            + ', Erkenntnislage ' + (d.erkenntnislage_max || '?'));
        t.push('Quadrantenschwellen: ' + (d.schwelle_dringlichkeit || '?')
            + ' % / ' + (d.schwelle_erkenntnislage || '?') + ' %');
        var aus = d.ausgeschlossene_kriterien || [];
        t.push('Aus der Abdeckung ausgeschlossen: '
            + (aus.length ? aus.join(', ') : 'keine'));
        if (d.dauer_gesamt_ms !== undefined && d.dauer_gesamt_ms !== null) {
            t.push('Laufzeit: ' + d.dauer_gesamt_ms + ' ms'
                + ((d.dauer_fristen_ms === null
                    || d.dauer_fristen_ms === undefined)
                    ? ' (ohne Fristanteil)'
                    : ' (davon Fristen ' + d.dauer_fristen_ms + ' ms)'));
        }
        return t.join(' · ');
    }

    // quellenText: die ausgefallenen Quellen — oder null. Ein ausgefallener
    // Beitrag fehlt in JEDER Zeile; das macht Faelle harmloser, als sie sind,
    // und gehoert deshalb nach OBEN und nicht in die Fussnoten.
    function quellenText(data) {
        var fq = (data && data.fehlende_quellen) || [];
        if (!fq.length) { return null; }
        return 'MINDESTENS EINE QUELLE FEHLT: ' + fq.join('; ')
            + '. Die betroffenen Beiträge fehlen in JEDER Zeile — ein Fall '
            + 'kann deshalb harmloser aussehen, als er ist.';
    }

    // codesText: unbekannte Konfidenz-Codes — oder null. Sie ergeben NIE 0,
    // sondern machen den Fall unbestimmbar; der Satz sagt ausdruecklich, dass
    // eine FACHLICHE Entscheidung und keine Codeanpassung fällig ist.
    function codesText(data) {
        var uc = (data && data.unbekannte_codes) || {};
        var k = Object.keys(uc);
        if (!k.length) { return null; }
        return 'UNBEKANNTE KONFIDENZ-CODES: ' + k.sort().map(function (c) {
            return c + ' (' + uc[c] + '×)';
        }).join(' · ') + '. Die betroffenen Fälle werden NICHT mit 0 '
            + 'gerechnet, sondern als nicht bestimmbar geführt. Vermutlich '
            + 'wurde der Bewertungskatalog erweitert und der Gewichtungssatz '
            + 'nicht nachgezogen — das ist eine fachliche Entscheidung.';
    }

    // gruppen: die Zellen nach Quadrant, in der Reihenfolge der Beachtung.
    // DIE REIHENFOLGE INNERHALB EINER GRUPPE BLEIBT DIE DES BACKENDS — zwei
    // Sortierungen waeren zwei Wahrheitsquellen, und das Backend sortiert
    // bereits (nicht_bestimmbar zuerst, dann nach Dringlichkeit).
    function gruppen(data) {
        var zellen = (data && data.zellen) || [];
        var nach = {};
        zellen.forEach(function (z) {
            var q = (z && z.quadrant) || 'unbekannt';
            if (!nach[q]) { nach[q] = []; }
            nach[q].push(z);
        });
        var namen = Object.keys(nach).sort(function (a, b) {
            var ra = QUADRANT[a] ? QUADRANT[a].rang : 98;
            var rb = QUADRANT[b] ? QUADRANT[b].rang : 98;
            if (ra !== rb) { return ra - rb; }
            return a < b ? -1 : (a > b ? 1 : 0);
        });
        return namen.map(function (n) {
            return { quadrant: n, zellen: nach[n] };
        });
    }

    // quadrantIds: die vom Frontend abgedeckten Quadranten (fuer den Test
    // gegen die Backend-Liste QUADRANTEN).
    function quadrantIds() { return Object.keys(QUADRANT); }
    function belastbarkeitIds() { return Object.keys(BELASTBARKEIT); }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    function _el(doc, tag, cls, text) {
        var e = doc.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    // _beitragsliste: die Beitraege einer Achse als <ul>. Sie steht in einem
    // <details> je Zeile — mcs Vorgabe zur Matrix: 'Quadrant sichtbar, Zahlen
    // im Aufklappbereich'. Eine Tabelle mit acht Zahlenspalten waere unlesbar
    // gewesen, und die BEGRUENDUNG je Punkt haette gar keinen Platz gehabt.
    function _beitragsliste(doc, titel, liste, summe) {
        var box = _el(doc, 'div', 'aiw-mx-beitraege');
        box.appendChild(_el(doc, 'h4', null, titel + ' (Summe ' + summe + ')'));
        if (!liste.length) {
            box.appendChild(_el(doc, 'p', 'aiw-mx-leer',
                'Kein Beitrag auf dieser Achse.'));
            return box;
        }
        var ul = doc.createElement('ul');
        liste.forEach(function (b) {
            var li = _el(doc, 'li', 'aiw-mx-beitrag');
            li.appendChild(_el(doc, 'span', 'aiw-mx-punkte',
                '+' + Number(b.punkte || 0)));
            li.appendChild(_el(doc, 'span', 'aiw-mx-code',
                beitragLabel(b.code)));
            li.appendChild(_el(doc, 'span', 'aiw-mx-grund',
                String(b.grund || '')));
            ul.appendChild(li);
        });
        box.appendChild(ul);
        return box;
    }

    // renderMatrix: baut die Sicht in mainEl.
    //   opts.doc        — Dokument (injizierbar fuer Tests)
    //   opts.onFristen  — Rueckruf (bool) fuer den Fristen-Schalter. Fehlt er,
    //                     wird der Schalter NICHT gezeichnet: ein
    //                     Bedienelement ohne Wirkung waere schlimmer als
    //                     keines (dieselbe Regel wie onVorwarn in Build 525).
    function renderMatrix(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = opts.doc || mainEl.ownerDocument
            || (typeof document !== 'undefined' ? document : null);
        if (!doc) { return null; }

        mainEl.textContent = '';
        // Build 599 (Baustelle H / H10): literale Hilfe-Marken.
        var mxKopf = _el(doc, 'h2', 'aiw-pagehead',
            'Dringlichkeit & Erkenntnislage');
        mxKopf.setAttribute('data-hilfe-id', 'matrix.titel');
        mainEl.appendChild(mxKopf);

        // FEHLER: ausdruecklich als solcher — NICHT als leere Liste. Bei einer
        // Rangfolge ist das besonders wichtig: eine leere Liste liesse sich
        // als 'nichts ist dringend' lesen.
        if (data && data.error) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
                'Matrix derzeit nicht verfügbar: ' + data.error
                + ' — dies ist KEIN Leerbefund. Es ist unbekannt, welche '
                + 'Fälle dringend sind.'));
            log('Fehlerzustand:', data.error);
            return { state: 'error' };
        }

        // (1) DIE ZWECKBINDUNG — ganz oben, wortgleich aus dem
        //     Gewichtungssatz. Sie ist der Grund, aus dem diese Sicht
        //     ueberhaupt verantwortbar ist.
        var mxZweck = _el(doc, 'div',
            'aiw-mx-zweck ' + (zweckbindungOk(data) ? 'is-ok' : 'is-fehlt'),
            zweckbindungText(data));
        mxZweck.setAttribute('data-hilfe-id', 'matrix.zweckbindung');
        mainEl.appendChild(mxZweck);

        // (2) Die zweite Zusicherung: kein Schreiben von Prioritaeten.
        mainEl.appendChild(_el(doc, 'div',
            'aiw-mx-prio ' + (prioritaetOk(data) ? 'is-ok' : 'is-fehlt'),
            prioritaetText(data)));

        // (3) Der Ladezustand der Fristen. Er steht OBEN, weil er ueber bis zu
        //     40 von 90 Punkten der X-Achse entscheidet.
        var fgeladen = !!(data && data.fristen_geladen === true);
        mainEl.appendChild(_el(doc, 'div',
            'aiw-mx-fristen ' + (fgeladen ? 'is-geladen' : 'is-offen'),
            fristenText(data)));

        // (4) Der Fristen-Schalter — nur wenn er WIRKT.
        if (typeof opts.onFristen === 'function') {
            var box = _el(doc, 'div', 'aiw-mx-actions');
            box.appendChild(_el(doc, 'span', 'aiw-mx-actions-label',
                'Verjährungsfristen:'));
            [[true, 'mit Fristen (langsamer)'],
             [false, 'ohne Fristen (schnell)']].forEach(function (spec) {
                var b = _el(doc, 'button', 'aiw-mx-schalter', spec[1]);
                b.setAttribute('type', 'button');
                b.setAttribute('data-fristen', spec[0] ? '1' : '0');
                if (fgeladen === spec[0]) {
                    b.className += ' is-active';
                    b.setAttribute('aria-pressed', 'true');
                }
                b.addEventListener('click', function () {
                    log('Fristen ->', spec[0]);
                    opts.onFristen(spec[0]);
                });
                box.appendChild(b);
            });
            mainEl.appendChild(box);
        }

        // (5) Ausgefallene Quellen und unbekannte Codes — beide OBEN, weil sie
        //     darueber entscheiden, ob die Zahlen darunter belastbar sind.
        var qt = quellenText(data);
        if (qt) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-mx-quellen', qt));
        }
        var ct = codesText(data);
        if (ct) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-mx-codes', ct));
        }
        // Build 538: ein Fall OHNE Fristzeile, obwohl geladen wurde, ist ein
        // Widerspruch. Er wird gezeigt, nicht geglaettet.
        if (data && data.faelle_ohne_fristzeile) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-mx-quellen',
                'WIDERSPRUCH: zu ' + data.faelle_ohne_fristzeile
                + ' Fällen kam keine Fristzeile zurück, obwohl die Fristen '
                + 'geladen wurden. Diese Fälle stehen mit dem Grund '
                + '"nicht geladen" im fünften Feld.'));
        }

        // (6) Die Verteilungen.
        mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
            (data && data.faelle_gesamt !== undefined
                ? data.faelle_gesamt : '?') + ' Fälle · '
            + quadrantenText(data)));
        var bt = belastbarkeitText(data);
        if (bt) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-mx-belastbarkeit', bt));
        }

        // (7) Die Gruppen. Jede Gruppe traegt ihre BEDEUTUNG im Klartext —
        //     eine Farbe allein erklaert nichts, und diese Sicht muss in einer
        //     Dienstbesprechung erklaerbar sein.
        var gr = gruppen(data);
        var gesamtZeilen = 0;
        if (!gr.length) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-mx-leer',
                'Keine Fälle im Bestand. Dies ist ein Leerbefund über die '
                + 'FALLLISTE, keine Aussage über Dringlichkeit.'));
        }
        gr.forEach(function (g) {
            var info = quadrantInfo(g.quadrant);
            var sec = _el(doc, 'section', 'aiw-mx-gruppe ' + info.cls);
            sec.setAttribute('data-quadrant', String(g.quadrant));
            sec.appendChild(_el(doc, 'h3', 'aiw-mx-gruppe-titel',
                info.label + ' (' + g.zellen.length + ')'));
            sec.appendChild(_el(doc, 'p', 'aiw-mx-gruppe-sub', info.kurz));

            var tbl = _el(doc, 'table', 'aiw-mx-table');
            var thead = doc.createElement('thead');
            var trh = doc.createElement('tr');
            ['Fall', 'Dringlichkeit', 'Grundlage', 'Erkenntnislage',
             'Kriterien', 'Einzelheiten'].forEach(function (h) {
                trh.appendChild(_el(doc, 'th', null, h));
            });
            thead.appendChild(trh);
            tbl.appendChild(thead);

            var tbody = doc.createElement('tbody');
            g.zellen.forEach(function (z) {
                gesamtZeilen += 1;
                var tr = _el(doc, 'tr', 'aiw-mx-row');
                tr.setAttribute('data-subject', String(z.subject_id));
                tr.setAttribute('data-quadrant', String(z.quadrant));
                tr.appendChild(_el(doc, 'td', 'aiw-mx-case',
                    z.subject_id + ' · ' + (z.username || '?')));

                // X: die Zahl oder die UNTERGRENZE. Der Grund haengt als
                // title an der Zelle und steht zusaetzlich ausgeschrieben im
                // Aufklappbereich — wer nur ueberfliegt, soll ihn sehen; wer
                // liest, soll ihn nachlesen koennen.
                var xz = _el(doc, 'td', 'aiw-mx-x', dringlichkeitText(z));
                var gt = grundText(z);
                if (gt) {
                    xz.className += ' is-unbestimmt';
                    xz.setAttribute('title', gt);
                }
                if (!beitragStimmig(z)) {
                    // Zweite, unabhaengige Probe. Schlaegt sie an, stimmt die
                    // Zahl nicht mit ihrer Begruendung ueberein — das ist ein
                    // Fehler und wird SICHTBAR, nicht geglaettet.
                    xz.className += ' is-unstimmig';
                    xz.setAttribute('title',
                        (gt ? gt + ' — ' : '')
                        + 'WARNUNG: die Summe der Beiträge stimmt nicht mit '
                        + 'dem ausgewiesenen Wert überein.');
                }
                tr.appendChild(xz);

                // Belastbarkeit — eigene Spalte, eigene Klasse (M-1).
                var bi = belastbarkeitInfo(z.dringlichkeit_belastbarkeit);
                tr.appendChild(_el(doc, 'td', 'aiw-mx-belast ' + bi.cls,
                    bi.label));

                tr.appendChild(_el(doc, 'td', 'aiw-mx-y',
                    erkenntnislageText(z)));
                // Die Bezugsgroesse gehoert IN die Zeile: /api/results/coverage
                // rechnet ueber ZEHN Kriterien, die Matrix ueber neun.
                tr.appendChild(_el(doc, 'td', 'aiw-mx-krit',
                    (z.n_kriterien_matrix === undefined
                     || z.n_kriterien_matrix === null)
                        ? '—' : ('von ' + z.n_kriterien_matrix)));

                // Einzelheiten: der Aufklappbereich mit den Beitraegen und den
                // Vermerken. mcs Vorgabe (AP-3B): Quadrant sichtbar, Zahlen im
                // Aufklappbereich. Er ist IMMER GESCHLOSSEN — dieselbe
                // Entscheidung wie beim Tatzeit-Feld (Build 534): die
                // Oberflaeche bleibt klar, und wer die Begruendung braucht,
                // holt sie sich.
                var td = _el(doc, 'td', 'aiw-mx-detail');
                var det = doc.createElement('details');
                det.className = 'aiw-mx-details';
                var teile = beitraegeJeAchse(z);
                det.appendChild(_el(doc, 'summary', null,
                    'Begründung (' + (teile.dringlichkeit.length
                                      + teile.erkenntnislage.length) + ')'));
                det.appendChild(_beitragsliste(doc, 'Dringlichkeit',
                    teile.dringlichkeit,
                    summeBeitraege(teile.dringlichkeit)));
                det.appendChild(_beitragsliste(doc, 'Erkenntnislage',
                    teile.erkenntnislage,
                    summeBeitraege(teile.erkenntnislage)));
                if (teile.sonstige.length) {
                    det.appendChild(_beitragsliste(doc,
                        'Ohne Achsenzuordnung (unerwartet)', teile.sonstige,
                        summeBeitraege(teile.sonstige)));
                }
                // Die Vermerke des Backends WORTGLEICH. Hier steht der
                // § 78c-Vorbehalt und der Ersatzanker-Hinweis — sie werden
                // NICHT neu formuliert.
                var vm = (z.vermerke || []);
                if (vm.length) {
                    var vbox = _el(doc, 'div', 'aiw-mx-vermerke');
                    vbox.appendChild(_el(doc, 'h4', null,
                        'Vermerke (' + vm.length + ')'));
                    var vul = doc.createElement('ul');
                    vm.forEach(function (t) {
                        vul.appendChild(_el(doc, 'li', null, String(t)));
                    });
                    vbox.appendChild(vul);
                    det.appendChild(vbox);
                }
                td.appendChild(det);
                tr.appendChild(td);
                tbody.appendChild(tr);
            });
            tbl.appendChild(tbody);
            sec.appendChild(tbl);
            mainEl.appendChild(sec);
        });

        // (8) Der Massstab steht IMMER da — auch beim Leerbefund. Ohne
        //     Massstab sagt auch ein Leerbefund nichts.
        mainEl.appendChild(_el(doc, 'div', 'aiw-mx-foot', massstabText(data)));

        // (9) Vorbehalte und Hinweise des Backends WORTGLEICH.
        var vb = (data && data.vorbehalte) || [];
        var hw = (data && data.hinweise) || [];
        if (vb.length || hw.length) {
            var d2 = doc.createElement('details');
            d2.className = 'aiw-mx-vorbehalte';
            d2.appendChild(_el(doc, 'summary', null,
                'Vorbehalte und Hinweise (' + (vb.length + hw.length) + ')'));
            var ul2 = doc.createElement('ul');
            vb.concat(hw).forEach(function (t) {
                ul2.appendChild(_el(doc, 'li', null, String(t)));
            });
            d2.appendChild(ul2);
            mainEl.appendChild(d2);
        } else {
            // KEINE Vorbehalte ist ein VERDACHTSMOMENT, keine gute Nachricht:
            // das Backend liefert sie immer mit.
            mainEl.appendChild(_el(doc, 'div', 'aiw-mx-zweck is-fehlt',
                'ACHTUNG: Die Antwort enthält KEINE Vorbehalte. Das Backend '
                + 'liefert sie normalerweise immer mit — die Herkunft dieser '
                + 'Antwort ist zu klären.'));
        }

        log('gerendert:', gesamtZeilen, 'Zeilen in', gr.length, 'Gruppen;',
            'Fristen geladen:', fgeladen);
        return {
            state: gesamtZeilen ? 'befund' : 'leer',
            count: gesamtZeilen,
            gruppen: gr.length,
            fristen: fgeladen,
            zweckbindung: zweckbindungOk(data)
        };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        QUADRANT: QUADRANT,
        BELASTBARKEIT: BELASTBARKEIT,
        GRUND: GRUND,
        BEITRAG_LABEL: BEITRAG_LABEL,
        quadrantInfo: quadrantInfo,
        quadrantIds: quadrantIds,
        belastbarkeitInfo: belastbarkeitInfo,
        belastbarkeitIds: belastbarkeitIds,
        beitragLabel: beitragLabel,
        zweckbindungText: zweckbindungText,
        zweckbindungOk: zweckbindungOk,
        prioritaetText: prioritaetText,
        prioritaetOk: prioritaetOk,
        fristenText: fristenText,
        fristAnteilMax: fristAnteilMax,
        dringlichkeitText: dringlichkeitText,
        grundText: grundText,
        erkenntnislageText: erkenntnislageText,
        beitraegeJeAchse: beitraegeJeAchse,
        summeBeitraege: summeBeitraege,
        beitragStimmig: beitragStimmig,
        quadrantenText: quadrantenText,
        belastbarkeitText: belastbarkeitText,
        massstabText: massstabText,
        quellenText: quellenText,
        codesText: codesText,
        gruppen: gruppen,
        renderMatrix: renderMatrix
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitMatrix = API; }
})();
