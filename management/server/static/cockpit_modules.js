/**
 * management/server/static/cockpit_modules.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Vermaehlung B6xB7 — W1 (Baustein-Module), FRONTEND (Build 427)
 *
 * Zweck:
 *   Autoren-Sicht der Redakteur:in (Recht templates.edit): BAUSTEIN-MODULE
 *   (templates.db.report_modules) LISTEN, ANLEGEN und AENDERN. Ein Baustein ist
 *   ein wiederverwendbarer FREITEXT-Baustein (body), den der Berichtseditor
 *   ueber seine STABILE Kennung module_key einfuegt. Der body darf Platzhalter
 *   {{a:}}/{{m:}}/{{o:}} enthalten, die erst beim Rendern des konkreten Berichts
 *   aufgeloest werden — hier NICHT.
 *
 *   Vor dem Speichern kann mit "Vorschau" SCHREIBFREI geprueft werden
 *   (POST /api/templates/module/dryrun -> {ok,errors,summary} mit Platzhalter-
 *   Zaehlung). Das Speichern laeuft ueber den auditierten Pfad
 *   (POST /api/templates/module -> TemplatesWriter, Build 426).
 *
 *   Backend-Endpunkte (Build 426):
 *     GET  /api/templates/modules        — Liste
 *     POST /api/templates/module         — anlegen/aendern (auditiert)
 *     POST /api/templates/module/dryrun  — schreibfreie Vorschau
 *
 *   ABGRENZUNG: W2 pflegt Einzeldaten-Queries, W3 ganze Dokumentvorlagen (Block-
 *   Geruest), DIESE Sicht einzelne Textbausteine. Alle drei schreiben nur ueber
 *   den auditierten templates.db-Pfad.
 *
 * JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging (DEV=false fuer
 *   PROD); ausfuehrliche Kommentare; Kapselung; REINE Funktionen separat
 *   exportiert (vitest). XSS-sicher via textContent/value (multilingual, UTF-8).
 *
 * Build 488: Browser-Zwischenspeicher (localStorage) des NICHT gespeicherten
 *   Editor-Entwurfs (analog Dokumentvorlagen Build 487): jede Nutzer-Eingabe
 *   wird gesichert, beim Betreten/Neuladen wiederhergestellt, nach erfolgreichem
 *   Speichern verworfen. Eigener Schluessel DRAFT_KEY, nur Client, migrationsneutral.
* Build 635 (Vorgang 17200856, Welle B3): HILFE-MARKEN fuer die acht
*   Bedienelemente dieser Sicht - damit tragen alle eine. Die Texte
*   stehen in management/help/inhalt/redaktion.py.
*   Darunter der Umschalter 'Rohansicht / Vorschau', den mc im Vorgang
*   woertlich benannt hat.
 *
 * Build 652 (Ticket 3508ad71): DIE VORSCHAU BEKOMMT EINE EIGENE SPALTE.
 *   Sie klebte bisher UNTEN an der Eingabemaske (_vorschauAufbauen haengte
 *   Kopf und Behaelter an das Formular). Jetzt steht sie als dritte
 *   Rasterspalte RECHTS neben der Maske und ist dauerhaft sichtbar.
 *
 *   WARUM DAS RASTER UND NICHT JAVASCRIPT: der Ticketwortlaut verlangt, dass
 *   die Spalte nur nach rechts geht, "falls dort auch Platz ist, sonst kommt
 *   er nach wie vor unter die Eingabemaske". Das ist eine Breitenfrage, und
 *   Breitenfragen beantwortet CSS (grid-template-areas + @media) besser als
 *   gemessene Pixel: Editor.js misst seinen Behaelter beim Aufbau, und eine
 *   zweite Messquelle in JavaScript waere genau die Art von Doppelwahrheit,
 *   die uns in Build 575 das Schluesselfeld gekostet hat. Beim Spaltenwechsel
 *   wird die Editor-Instanz NICHT neu gebaut - nur ihre Spalte wandert.
 *
 *   DER UMSCHALTER BLEIBT, ABER ALS ZUKLAPP-SCHALTER. Das Ticket sagt, die
 *   Schaltflaeche "Rohansicht/Vorschau" werde unnoetig. Sie tat bisher genau
 *   eines: die Vorschau ein- und ausblenden (host.hidden). Auf schmalen
 *   Anzeigen ist das weiterhin noetig, sonst schiebt die Vorschau die Maske
 *   aus dem Bild. Er heisst deshalb jetzt, was er tut, und merkt sich seinen
 *   Stand (VORSCHAU_KEY) - anders als bisher, wo er ausdruecklich "ein
 *   Moment, keine Vorliebe" war. ANNAHME, VON mc ZU BESTAETIGEN ODER ZU
 *   VERWERFEN.
 *
 * Build 653 (Ticket d60e893a): DIE LISTE WIRD EINE TABELLE.
 *   Die linke Spalte war eine Kette von Schaltflaechen ohne Sortierung, ohne
 *   Filter und ohne Begrenzung der Hoehe. Bei genug Bausteinen ist das keine
 *   Liste mehr, sondern eine Halde. Sie wird durch AIWTableKit ersetzt
 *   (cockpit_tablekit.js) und wandert nach OBEN ueber die Maske - in einer
 *   300px-Spalte waeren Kopffilter und Seitenblaetterung nicht bedienbar.
 *
 *   RUECKFALL IST PFLICHT: fehlt Tabulator oder das Werkzeug, baut diese
 *   Datei die alte Schaltflaechenliste. tabelleAufbauen wuerde stattdessen
 *   einen Hinweis mit Zeilenzahl zeigen - richtig fuer eine reine Anzeige,
 *   hier aber falsch: ueber die Liste wird AUSGEWAEHLT. Ohne Rueckfall waere
 *   die Sicht nicht nur haesslich, sondern unbedienbar.
 *
 * Build 654 (Ticket 4b032177): PLATZHALTER-TABELLE unter dem Bausteintext.
 *   Sie weist die Platzhalter des Textes in Echtzeit aus, prueft sie gegen
 *   den Platzhalter- und den Formatregelkatalog und laesst eine Eingabe
 *   gegen die Regeln testen. Der Bauteil selbst liegt in
 *   cockpit_baustein_platzhalter.js (Projektregel 10); diese Datei haengt
 *   ihn ein und speist ihn - genau wie die Vorschau, mit derselben
 *   Entprellung und aus demselben Formularzustand.
 *
 * Version: v0.8.654 · Build: 654 · 2026-08-02
 */
(function () {
    'use strict';

    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[modules]');
            console.log.apply(console, a);
        }
    }

    var _state = {
        listEl: null, fields: null, msgEl: null, dryEl: null,
        selKey: null, selId: null, nachtragId: null,
        keyHinweisEl: null,
        // Build 577 / 652: Vorschau. vorschauSpalte ist die dritte
        // Rasterspalte, vorschauEl der Behaelter darin, vorschau die
        // Editor-Instanz, vorschauSpaltenStand die EINE Funktion, die den
        // Zuklapp-Zustand anzeigt.
        vorschauEl: null, vorschau: null, vorschauAn: true,
        vorschauSpalte: null, vorschauSpaltenStand: null,
        // Build 654: Platzhalter-Tabelle und ihre beiden Kataloge. Die
        // Kataloge ueberdauern einen Neuaufbau der Maske, weil sie ueber das
        // Netz kommen und sich beim Bearbeiten eines Bausteins nicht aendern.
        platzhalter: null, phKatalog: null, phRegeln: null,
        // Build 653: die Tabelle. listEl bleibt daneben bestehen und traegt
        // NUR im Rueckfall etwas - genau eines der beiden ist je gesetzt.
        table: null, nurOhneKennung: false, nurOhneBtn: null
    };

    // Build 488: Browser-Zwischenspeicher (localStorage) des NOCH NICHT
    // gespeicherten Editor-Entwurfs (analog Dokumentvorlagen Build 487). Eigener
    // versionierter Schluessel. Nur Client-seitig, migrationsneutral.
    var DRAFT_KEY = 'aiw.modules.draft.v1';

    // Build 652: Stand des Zuklapp-Schalters der Vorschau-Spalte. Eigener
    // Schluessel, damit er den Entwurf (DRAFT_KEY) nicht beruehrt - ein
    // zugeklapptes Vorschaufenster ist keine Arbeit, die verlorengehen kann.
    var VORSCHAU_KEY = 'aiw.modules.vorschau.v1';

    function _ls() {
        try {
            return (typeof localStorage !== 'undefined') ? localStorage : null;
        } catch (e) { return null; }
    }

    // _vorschauStandLesen / _vorschauStandSchreiben (Build 652)
    // --------------------------------------------------------------------
    // VORGABE IST OFFEN. Das Ticket 3508ad71 will die Vorschau als "immer
    // sichtbaren Standard"; wer sie einmal zuklappt, bekommt sie beim
    // naechsten Betreten trotzdem nicht ungefragt zurueck. Deshalb: nur ein
    // ausdrueckliches '0' schliesst - jeder andere Wert, auch ein fehlender
    // oder ein unlesbarer Speicher, ergibt OFFEN.
    function _vorschauStandLesen() {
        var ls = _ls();
        if (!ls) { return true; }
        try { return ls.getItem(VORSCHAU_KEY) !== '0'; } catch (e) { return true; }
    }
    function _vorschauStandSchreiben(offen) {
        var ls = _ls();
        if (!ls) { return; }
        try { ls.setItem(VORSCHAU_KEY, offen ? '1' : '0'); } catch (e) { /* egal */ }
    }

    // Stabiler Schluessel-Zeichenraum (Spiegel der Server-Regel _KEY_RE).
    var _KEY_RE = /^[A-Za-z0-9._-]+$/;

    // Zulaessige Rollen (deckungsgleich mit report_modules.role / module_validator.ROLES).
    var ROLES = ['intro', 'conclusion', 'body', 'legal', 'appendix', 'closing'];

    // =====================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — vitest.
    // =====================================================================

    // roleLabel: Klartext zur Rolle (Fallback: Rohwert).
    function roleLabel(role) {
        switch (role) {
            case 'intro':      return 'Einleitung (intro)';
            case 'conclusion': return 'Fazit (conclusion)';
            case 'body':       return 'Hauptteil (body)';
            case 'legal':      return 'Rechtliches (legal)';
            case 'appendix':   return 'Anhang (appendix)';
            case 'closing':    return 'Schluss (closing)';
            default:           return role || '';
        }
    }

    // moduleLabel: Anzeigetext eines Listeneintrags: "Titel (key)".
    function moduleLabel(m) {
        if (!m) { return '?'; }
        var key = (m.module_key === undefined || m.module_key === null)
            ? '' : String(m.module_key);
        var title = (m.title === undefined || m.title === null)
            ? '' : String(m.title);
        if (title && key) { return title + ' (' + key + ')'; }
        return title || key || '?';
    }

    // sortModules: neue Liste, nach role dann sort_order dann module_key.
    // Mutiert die Eingabe NICHT.
    function sortModules(list) {
        var arr = (list || []).slice();
        arr.sort(function (a, b) {
            var ar = String((a && a.role) || '');
            var br = String((b && b.role) || '');
            if (ar !== br) { return ar < br ? -1 : 1; }
            var ao = (a && a.sort_order) || 0;
            var bo = (b && b.sort_order) || 0;
            if (ao !== bo) { return ao - bo; }
            var ak = String((a && a.module_key) || '').toLowerCase();
            var bk = String((b && b.module_key) || '').toLowerCase();
            if (ak < bk) { return -1; }
            if (ak > bk) { return 1; }
            return 0;
        });
        return arr;
    }

    // isValidKey: Client-Spiegel der Server-Regel (Bequemlichkeit).
    function isValidKey(key) {
        return _KEY_RE.test(String(key || ''));
    }

    // moduleRows (Build 653): aus den Bausteinen die Zeilen der Tabelle.
    // ------------------------------------------------------------------
    // REIN und deshalb einzeln pruefbar. Die abgeleiteten Felder tragen
    // einen Unterstrich, damit man ihnen ansieht, dass sie NICHT aus der
    // Datenbank kommen und nichts zurueckgeschrieben wird.
    //
    // _ohneKennung ist das wichtigste davon: acht Altbausteine haben noch
    // keinen module_key (Ticket ac36e10b), und wer sie nachtragen soll, muss
    // sie FINDEN koennen. Als Wahrheitswert laesst er sich filtern - ein
    // leerer Text liesse sich das nicht.
    //
    // _kennungText steht bewusst als sichtbarer Klartext da und nicht als
    // Leerzelle: eine leere Zelle sieht aus wie ein Anzeigefehler, und
    // Grundregel 1 verbietet das stille Uebergehen eines Befundes.
    function moduleRows(list) {
        return sortModules(list).map(function (m) {
            var key = (m && m.module_key !== undefined && m.module_key !== null)
                ? String(m.module_key) : '';
            var zeile = {};
            // Der ganze Datensatz bleibt in der Zeile - der Zeilenklick
            // fuellt daraus die Maske, ohne noch einmal nachzuladen.
            Object.keys(m || {}).forEach(function (k) { zeile[k] = m[k]; });
            zeile._kennung = key;
            zeile._ohneKennung = (key === '');
            zeile._kennungText = key || '— ohne Kennung —';
            zeile._rolleText = roleLabel(m && m.role);
            zeile._aktivText = (m && m.is_active === 0) ? 'nein' : 'ja';
            return zeile;
        });
    }

    // zeilenKennung (Build 653): der Wert, ueber den eine Zeile adressiert
    // wird. ZWEI ADRESSWEGE, UND DAS MIT ABSICHT: ueber module_key, solange
    // es einen gibt, sonst ueber die Zeilen-id als '#id:<n>'.
    //
    // Das ist die Lehre aus Ticket a1480978: ModuleAuthorRepo.upsert fand
    // eine Altzeile ohne Kennung ueber den module_key NICHT und legte eine
    // ZWEITE Zeile an, die alte blieb unerreichbar daneben stehen. Wer diese
    // Funktion vereinfacht, holt genau diesen Fehler zurueck.
    function zeilenKennung(m) {
        if (!m) { return null; }
        var key = (m.module_key === undefined || m.module_key === null)
            ? '' : String(m.module_key);
        if (key !== '') { return key; }
        return (m.id === undefined || m.id === null) ? null : ('#id:' + m.id);
    }

    // schluesselVorschlag: aus einem Titel eine zulaessige Kennung bauen
    // (Build 565). Ein leeres Pflichtfeld ohne Anhalt ist eine Falle - wer
    // acht Altbausteine nachtragen muss, soll nicht achtmal ueberlegen
    // muessen, wie ein Schluessel auszusehen hat. Der Vorschlag ist frei
    // ueberschreibbar; er wird NIE automatisch gespeichert.
    //
    // Regeln: Umlaute ausschreiben (sonst faellt 'Beschluss' zu 'Beschluss'
    // und 'Anhörung' zu 'Anhrung' zusammen), alles klein, jede unzulaessige
    // Folge zu einem Punkt, Raender abschneiden. Der erlaubte Zeichenraum
    // ist [A-Za-z0-9._-] (module_validator).
    function schluesselVorschlag(titel, rolle) {
        var t = String(titel || '').toLowerCase();
        t = t.replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue')
             .replace(/ß/g, 'ss');
        t = t.replace(/[^a-z0-9]+/g, '.').replace(/^\.+|\.+$/g, '');
        if (!t) { return ''; }
        var r = String(rolle || '').replace(/[^a-z0-9]+/g, '');
        // Praefix aus der Rolle, wie beim Bestand ('intro.standard',
        // 'legal.ki_uebersetzung'): so bleibt die Liste sortierbar.
        return r ? (r + '.' + t) : t;
    }

    // buildPayload: Feldwerte zum POST-Body. REIN. module_key/title/topic werden
    // getrimmt; body NICHT (Freitext bleibt exakt erhalten); description wie
    // eingegeben (leer erlaubt); sort_order als Zahl.
    function buildPayload(fields) {
        var f = fields || {};
        return {
            // Build 564/565: die id wird NUR mitgesendet, wenn ein Schluessel
            // nachzutragen ist. Sonst bliebe sie ein zweiter Adressweg neben
            // dem module_key - und zwei Adresswege auf dieselbe Zeile sind
            // einer zu viel.
            id: (f.id === undefined || f.id === null || f.id === '')
                ? undefined : f.id,
            module_key: String(f.module_key || '').trim(),
            title: String(f.title || '').trim(),
            description: (f.description === undefined || f.description === null)
                ? '' : String(f.description),
            role: f.role || 'body',
            topic: String(f.topic || '').trim(),
            body: (f.body === undefined || f.body === null) ? '' : String(f.body),
            sort_order: parseInt(f.sort_order, 10) || 0
        };
    }

    // summaryText: Platzhalter-Zaehlung zu "auto×2, mandatory×1" verdichten.
    function summaryText(summary) {
        if (!summary || !summary.length) { return ''; }
        return summary.map(function (s) {
            return String(s.kind) + '×' + String(s.count);
        }).join(', ');
    }

    // errorsText: Fehlerliste zu einer Zeile ('' bei keiner).
    function errorsText(errors) {
        if (!errors || !errors.length) { return ''; }
        return errors.join('; ');
    }

    // =====================================================================
    // 2) DOM-FUNKTIONEN (nur Browser/jsdom).
    // =====================================================================

    function _clearNode(el) { if (el) { el.textContent = ''; } }

    function _labeledField(parent, labelText, kind, className) {
        var lab = document.createElement('label');
        lab.className = 'aiw-mod-field';
        var span = document.createElement('span');
        span.className = 'aiw-mod-label';
        span.textContent = labelText;
        lab.appendChild(span);
        var input;
        if (kind === 'textarea') {
            input = document.createElement('textarea');
            input.rows = 6;
        } else if (kind === 'select') {
            input = document.createElement('select');
        } else {
            input = document.createElement('input');
            input.type = (kind === 'number') ? 'number' : 'text';
        }
        input.className = className;
        lab.appendChild(input);
        parent.appendChild(lab);
        return input;
    }

    function _fillForm(m) {
        var f = _state.fields;
        if (!f) { return; }
        if (m) {
            // BUILD 565 - ALTBESTAND OHNE SCHLUESSEL.
            // Bis Build 564 war das Feld im Editier-Modus IMMER gesperrt. Das
            // ist fuer Bausteine MIT Schluessel richtig (er ist eine stabile
            // Kennung, auf die Berichtsvorlagen verweisen) - fuer Altzeilen
            // OHNE Schluessel war es eine Sackgasse: sie liessen sich weder
            // in der Vorschau ansehen noch aendern, weil die Validierung den
            // Schluessel verlangt und niemand ihn eintragen konnte.
            var hatKey = !!(m.module_key);
            f.module_key.value = m.module_key || '';
            _state.nachtragId = hatKey ? null : m.id;
            if (!hatKey) {
                // Vorschlag setzen, aber NICHT speichern - das tut erst der
                // Anwender mit dem Speichern-Knopf.
                f.module_key.value = schluesselVorschlag(m.title, m.role);
            }
            f.title.value = m.title || '';
            f.description.value = m.description || '';
            f.role.value = m.role || 'body';
            f.topic.value = m.topic || '';
            f.body.value = m.body || '';
            f.sort_order.value = (m.sort_order === undefined
                || m.sort_order === null) ? 0 : m.sort_order;
            // selKey adressiert die Zeile in der Liste. Bei einer Altzeile
            // gibt es keinen Schluessel - dann wird ueber die id adressiert,
            // sonst stuende dort der Text "null".
            _state.selKey = hatKey ? String(m.module_key) : null;
            _state.selId = m.id;
        } else {
            f.module_key.value = '';
            f.title.value = '';
            f.description.value = '';
            f.role.value = 'body';
            f.topic.value = '';
            f.body.value = '';
            f.sort_order.value = 0;
            _state.selKey = null;
            _state.selId = null;
            _state.nachtragId = null;
        }
        // Build 575: EINE Regel fuer Sperre UND Hinweis - abgeleitet aus dem
        // Wert im Feld, nicht aus einem Zustandsfeld.
        _schluesselFeldStand();
        _setMsg('');
        renderDryRun(null);
        _markActive();
        // Build 577: die Vorschau folgt dem Formular - auch wenn es
        // programmatisch gefuellt wurde (Auswahl aus der Liste, Entwurf).
        // Programmatische .value-Zuweisungen loesen kein 'input' aus.
        _vorschauAktualisieren();
    }

    // _schluesselFeldStand: DIE EINZIGE Regel fuer Sperre und Hinweis des
    // Schluesselfeldes (Build 575).
    //
    // WARUM DAS NOETIG WAR: es gab DREI unabhaengige Ausdruecke dafuer -
    // _fillForm mit Modul (disabled = hatKey), _fillForm ohne Modul
    // (disabled = false) und die Entwurfs-Wiederherstellung
    // (disabled = selKey !== null). Der dritte kannte den Nachtragsmodus
    // nicht. Ein Entwurf aus der Zeit VOR Build 565 traegt selKey als die
    // Zeichenkette "null" (damals: String(m.module_key)) und ein leeres
    // module_key-Feld - beim Wiederherstellen ergab das genau das von mc
    // gemeldete Bild: GESPERRT UND LEER, also wieder die Sackgasse.
    //
    // Die neue Regel leitet den Zustand aus dem WERT ab und nicht aus einem
    // Zustandsfeld: ein Feld mit Schluessel ist fest, ein leeres ist offen.
    // Damit kann kein Zustand aus irgendeiner Quelle mehr eine Sperre
    // erzeugen, hinter der nichts steht.
    function _schluesselFeldStand() {
        var f = _state.fields;
        if (!f || !f.module_key) { return; }
        var wert = String(f.module_key.value || '').trim();
        var nachtrag = !!_state.nachtragId;
        f.module_key.disabled = (!nachtrag && wert !== '');
        _renderKeyHinweis();
    }

    // _renderKeyHinweis: erklaert den Zustand des Schluesselfeldes.
    // ------------------------------------------------------------------
    // BUILD 577 - VORSCHAU DES BAUSTEINS.
    //
    // Zeigt den Baustein so, wie ihn der Ermittler spaeter IM BERICHTSEDITOR
    // sieht: Editor.js im Nur-Lese-Modus, Platzhalter als Chips.
    //
    // BUILD 652 (Ticket 3508ad71): die Vorschau steht nicht mehr unter der
    // Maske, sondern in einer EIGENEN Spalte rechts daneben. Der Parameter
    // heisst deshalb nicht mehr 'form', sondern 'spalte' - das ist keine
    // Kosmetik, sondern der Unterschied, an dem man beim Lesen erkennt, dass
    // hier nicht mehr ins Formular gehaengt wird.
    // ------------------------------------------------------------------
    function _vorschauAufbauen(spalte) {
        var kopf = document.createElement('div');
        kopf.className = 'aiw-mod-vorschau-kopf';
        var titel = document.createElement('span');
        titel.className = 'aiw-mod-vorschau-titel';
        titel.textContent = 'Vorschau (Ansicht im Berichtseditor)';
        kopf.appendChild(titel);
        var schalter = document.createElement('button');
        schalter.type = 'button';
        schalter.className = 'aiw-btn aiw-btn-klein aiw-mod-vorschau-schalter';
        schalter.id = 'aiw-mod-vorschau-schalter';
        // Build 635 (Vorgang 17200856): Hilfe-Marke, LITERAL gesetzt.
        // mc hat DIESEN Schalter im Vorgang ausdruecklich benannt:
        // "Insbesondere die Wechselschaltflaechen 'Rohansicht' und
        // 'Vorschau' muessen erklaert werden."
        // Build 652: er heisst jetzt nach seiner Wirkung. Die Marke bleibt,
        // ihr Text in redaktion.py ist mitgezogen.
        schalter.setAttribute('data-hilfe-id', 'modules.bedienung.ansicht');
        kopf.appendChild(schalter);
        spalte.appendChild(kopf);

        var host = document.createElement('div');
        host.className = 'aiw-mod-vorschau';
        host.id = 'aiw-mod-vorschau';
        spalte.appendChild(host);
        _state.vorschauEl = host;
        _state.vorschauSpalte = spalte;

        var vs = (typeof window !== 'undefined')
            ? window.AIWBausteinVorschau : null;
        if (vs && typeof vs.erzeuge === 'function') {
            _state.vorschau = vs.erzeuge(host, {});
        } else {
            // KEIN STILLER AUSFALL - die Flaeche sagt, was fehlt.
            host.textContent = 'Vorschau-Modul nicht geladen '
                + '(cockpit_baustein_vorschau.js).';
            host.classList.add('ist-warnung');
        }

        // _spaltenStand: bringt Schalterbeschriftung, Sichtbarkeit des
        // Behaelters und die Klasse an der Spalte auf EINEN Stand. Es gibt
        // bewusst nur diese eine Stelle, die das tut - die Lehre aus Build
        // 575 ('es gab DREI unabhaengige Ausdruecke fuer den Feldzustand').
        function _spaltenStand() {
            var offen = !!_state.vorschauAn;
            schalter.textContent = offen ? 'Vorschau ausblenden'
                                         : 'Vorschau einblenden';
            schalter.setAttribute('aria-expanded', offen ? 'true' : 'false');
            host.hidden = !offen;
            spalte.classList.toggle('ist-zu', !offen);
        }
        _state.vorschauSpaltenStand = _spaltenStand;

        // Der gemerkte Stand gilt ab jetzt; Vorgabe ist offen.
        _state.vorschauAn = _vorschauStandLesen();
        _spaltenStand();
        if (_state.vorschauAn) { _vorschauAktualisieren(); }

        schalter.addEventListener('click', function () {
            _state.vorschauAn = !_state.vorschauAn;
            _vorschauStandSchreiben(_state.vorschauAn);
            _spaltenStand();
            if (_state.vorschauAn) { _vorschauAktualisieren(); }
            else if (_state.vorschau) { _state.vorschau.aus(); }
        });
    }

    // _vorschauAktualisieren: aus dem AKTUELLEN Formularzustand, nicht aus dem
    // gespeicherten Datensatz - der Redakteur soll sehen, was er gerade tippt.
    //
    // Build 654: dieselbe Quelle speist die Platzhalter-Tabelle. Sie haengt
    // NICHT am Zuklapp-Zustand der Vorschau - sie steht unter dem Textfeld
    // und ist eine Pruefung, keine Ansicht.
    function _vorschauAktualisieren() {
        if (!_state.fields) { return; }
        var f = _state.fields;
        var text = f.body ? f.body.value : '';
        if (_state.vorschauAn && _state.vorschau) {
            _state.vorschau.zeige({ body: text });
        }
        if (_state.platzhalter) {
            _state.platzhalter.zeige(text);
        }
    }

    // _platzhalterAufbauen (Build 654, Ticket 4b032177).
    // ------------------------------------------------------------------
    // Der Bauteil liegt in cockpit_baustein_platzhalter.js. Fehlt er, sagt
    // die Flaeche das im Klartext - dieselbe Regel wie bei der Vorschau:
    // eine leere Flaeche saehe aus wie 'keine Platzhalter vorhanden', und
    // das waere eine Falschaussage (Grundregel 1).
    function _platzhalterAufbauen(host) {
        var ph = (typeof window !== 'undefined')
            ? window.AIWBausteinPlatzhalter : null;
        if (!ph || typeof ph.erzeuge !== 'function') {
            host.textContent = 'Platzhalter-Tabelle nicht geladen '
                + '(cockpit_baustein_platzhalter.js).';
            host.classList.add('ist-warnung');
            return;
        }
        _state.platzhalter = ph.erzeuge(host, {});
        // Die Kataloge kommen ueber das Netz und treffen spaeter ein als der
        // erste Text. Sie werden deshalb NACHGEREICHT, statt den Aufbau auf
        // sie warten zu lassen - eine Tabelle, die erst nach zwei
        // Netzabrufen erscheint, wirkt kaputt.
        if (_state.phKatalog || _state.phRegeln) {
            _state.platzhalter.kataloge(_state.phKatalog, _state.phRegeln);
        }
    }

    function _renderKeyHinweis() {
        var el = _state.keyHinweisEl;
        if (!el) { return; }
        el.classList.remove('aiw-mod-keyhinweis-warn');
        if (_state.nachtragId) {
            el.textContent = 'Dieser Baustein stammt aus der Zeit vor der '
                + 'Schluessel-Einfuehrung und hat noch keine Kennung. Ohne sie '
                + 'ist weder Vorschau noch Aenderung moeglich. Der Vorschlag '
                + 'ist aus dem Titel gebildet und frei aenderbar — nach dem '
                + 'Speichern ist die Kennung ENDGUELTIG, weil '
                + 'Berichtsvorlagen ueber sie auf den Baustein verweisen.';
            el.classList.add('aiw-mod-keyhinweis-warn');
        } else if (_state.selKey) {
            el.textContent = 'Die Kennung ist fest: Berichtsvorlagen verweisen '
                + 'ueber sie auf diesen Baustein.';
        } else if (_state.selId) {
            // Ein bestehendes Modul ohne Kennung, dessen Zeilen-id wir NICHT
            // kennen (alter Entwurf). Speichern wuerde hier eine ZWEITE Zeile
            // anlegen statt die alte zu ergaenzen - deshalb der ausdrueckliche
            // Hinweis, das Modul neu aus der Liste zu waehlen.
            el.textContent = 'Dieser Entwurf stammt aus einer aelteren Fassung '
                + 'und kann die Kennung nicht sicher zuordnen. Bitte den '
                + 'Baustein links erneut anklicken, dann wird sie korrekt '
                + 'nachgetragen.';
            el.classList.add('aiw-mod-keyhinweis-warn');
        } else {
            el.textContent = 'Kennung frei waehlbar; nach dem ersten Speichern '
                + 'bleibt sie unveraendert.';
        }
    }

    function _currentFields() {
        var f = _state.fields;
        return {
            id: _state.nachtragId,
            module_key: f.module_key.value,
            title: f.title.value,
            description: f.description.value,
            role: f.role.value,
            topic: f.topic.value,
            body: f.body.value,
            sort_order: f.sort_order.value
        };
    }

    // _aktuelleKennung: was gerade in der Maske steht, als Adresse.
    // Spiegel von zeilenKennung, nur aus _state statt aus einem Datensatz.
    function _aktuelleKennung() {
        if (_state.selKey !== null && _state.selKey !== undefined) {
            return String(_state.selKey);
        }
        return _state.selId ? ('#id:' + _state.selId) : null;
    }

    // _markActive: markiert die Zeile, die gerade in der Maske steht.
    // Build 653: BEIDE Darstellungen werden bedient - die Tabelle und der
    // Rueckfall auf Schaltflaechen. Es waere bequemer, nur die Tabelle zu
    // kennen; dann bliebe im Rueckfall aber unsichtbar, was gerade
    // bearbeitet wird, und der Rueckfall waere nur halb einer.
    function _markActive() {
        var kennung = _aktuelleKennung();

        // (a) Tabelle.
        var t = _state.table;
        if (t && typeof t.getRows === 'function') {
            try {
                t.getRows().forEach(function (row) {
                    var el = (typeof row.getElement === 'function')
                        ? row.getElement() : null;
                    if (!el || !el.classList) { return; }
                    var d = (typeof row.getData === 'function')
                        ? row.getData() : null;
                    var an = (kennung !== null
                        && zeilenKennung(d) === kennung);
                    el.classList.toggle('is-active', an);
                });
            } catch (e) { log('Zeilenmarkierung nicht setzbar', e); }
        }

        // (b) Rueckfall-Schaltflaechen.
        if (_state.listEl) {
            var items = _state.listEl.querySelectorAll('.aiw-mod-item');
            Array.prototype.forEach.call(items, function (it) {
                var an = (kennung !== null
                    && it.getAttribute('data-key') === kennung);
                it.classList.toggle('is-active', an);
            });
        }
    }

    // =====================================================================
    // Build 653 — DIE LISTE ALS TABELLE (Ticket d60e893a).
    // =====================================================================

    // _tk / _mitHilfe: Zugriff auf das gemeinsame Tabellenwerkzeug und die
    // Hilfe-Anker der Spaltenkoepfe. LAZY geholt, damit die Ladereihenfolge
    // diese Sicht nicht lautlos brechen kann (Muster aus cockpit_mentoring.js
    // :105-127). Die Spalten werden KOPIERT - die Modulkonstante bleibt
    // unberuehrt, sonst wuechse sie bei jedem Aufruf einen Formatter an.
    function _tk() {
        return (typeof window !== 'undefined' && window.AIWTableKit)
            ? window.AIWTableKit : null;
    }
    function _mitHilfe(cols, sicht, doc) {
        var TK = _tk();
        if (!TK || !doc || !TK.titelMitHilfe) { return cols; }
        return cols.map(function (c) {
            var neu = {};
            Object.keys(c).forEach(function (k) { neu[k] = c[k]; });
            if (c.field && !c.titleFormatter) {
                neu.titleFormatter = TK.titelMitHilfe(
                    doc, c.title || c.field,
                    sicht + '.spalte.' + String(c.field).toLowerCase());
            }
            return neu;
        });
    }

    // Die Spalten. Kennung zuerst: sie ist das, worueber Berichtsvorlagen
    // auf den Baustein verweisen, und das Feld, das acht Altzeilen fehlt.
    var _SPALTEN = [
        { title: 'Kennung', field: '_kennungText', headerFilter: 'input',
          widthGrow: 2 },
        { title: 'Titel', field: 'title', headerFilter: 'input',
          widthGrow: 3 },
        { title: 'Rolle', field: '_rolleText', headerFilter: 'list',
          widthGrow: 2 },
        { title: 'Thema', field: 'topic', headerFilter: 'input',
          widthGrow: 2 },
        { title: 'Sortierung', field: 'sort_order', hozAlign: 'right',
          width: 110 },
        { title: 'Aktiv', field: '_aktivText', headerFilter: 'list',
          width: 90 }
    ];

    // _ohneKennungSchalter: Filter auf die Altzeilen ohne module_key.
    // ------------------------------------------------------------------
    // WARUM EIGENS DAFUER EIN SCHALTER: Ticket ac36e10b verlangt, acht
    // Altbausteine einzeln nachzutragen - eine Sammelvergabe gibt es
    // bewusst nicht, weil die Kennung danach endgueltig ist. Wer diese acht
    // aus einer nach Rolle sortierten Tabelle heraussuchen muss, sucht
    // lange. Ein Kopffilter auf '— ohne Kennung —' taete es zwar auch, aber
    // nur, wenn man den genauen Wortlaut kennt.
    function _ohneKennungSchalter(doc) {
        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.className = 'aiw-btn aiw-btn-klein aiw-mod-nurohne';
        btn.textContent = 'Nur ohne Kennung';
        btn.title = 'Zeigt nur Bausteine, denen die Kennung noch fehlt '
            + '(Nachtrag nach Ticket ac36e10b).';
        btn.setAttribute('aria-pressed', 'false');
        btn.setAttribute('data-hilfe-id', 'modules.bedienung.nurohne');
        btn.addEventListener('click', function () {
            _state.nurOhneKennung = !_state.nurOhneKennung;
            _ohneKennungAnwenden();
        });
        _state.nurOhneBtn = btn;
        return btn;
    }

    // _ohneKennungAnwenden: setzt oder entfernt den Filter und bringt die
    // Beschriftung des Schalters auf denselben Stand. EINE Stelle fuer
    // beides - die Lehre aus Build 575.
    function _ohneKennungAnwenden() {
        var t = _state.table;
        var btn = _state.nurOhneBtn;
        var an = !!_state.nurOhneKennung;
        if (btn) {
            btn.setAttribute('aria-pressed', an ? 'true' : 'false');
            btn.classList.toggle('ist-an', an);
        }
        if (!t) { return; }
        try {
            if (an) { t.setFilter('_ohneKennung', '=', true); }
            // removeFilter und NICHT clearFilter: clearFilter(true) raeumt
            // auch die Kopffilter weg, die der Redakteur gerade gesetzt hat.
            else { t.removeFilter('_ohneKennung', '=', true); }
        } catch (e) { log('Filter nicht setzbar', e); }
    }

    // _ohneKennungSyncen: der Schalter folgt dem TATSAECHLICHEN Filterstand.
    // Noetig, weil 'Filter zurücksetzen' aus der Werkzeugleiste des
    // TableKit den Filter mit wegraeumt (clearFilter(true)). Ohne diesen
    // Abgleich stuende der Schalter danach auf 'an', ohne dass gefiltert
    // waere - eine Anzeige, hinter der nichts steht.
    function _ohneKennungSyncen() {
        var t = _state.table;
        if (!t || typeof t.getFilters !== 'function') { return; }
        var gesetzt = false;
        try {
            gesetzt = (t.getFilters() || []).some(function (f) {
                return f && f.field === '_ohneKennung';
            });
        } catch (e) { return; }
        if (gesetzt !== !!_state.nurOhneKennung) {
            _state.nurOhneKennung = gesetzt;
            var btn = _state.nurOhneBtn;
            if (btn) {
                btn.setAttribute('aria-pressed', gesetzt ? 'true' : 'false');
                btn.classList.toggle('ist-an', gesetzt);
            }
        }
    }

    // _listeAufbauen: Tabelle, wenn es geht - sonst die alte Liste.
    // Rueckgabe: true, wenn eine Tabelle entstanden ist.
    // Ctor wird DURCHGEREICHT (opts.Tabulator) und faellt sonst auf
    // window.Tabulator zurueck - Hausmuster der uebrigen Sichten
    // (cockpit_mentoring.js MT05), damit die Tabelle pruefbar bleibt.
    function _listeAufbauen(host, rows, doc, Ctor) {
        var TK = _tk();
        if (typeof Ctor !== 'function') {
            Ctor = (typeof window !== 'undefined') ? window.Tabulator : null;
        }
        if (!TK || typeof TK.tabelleAufbauen !== 'function'
                || typeof Ctor !== 'function') {
            return false;
        }

        var auf = TK.tabelleAufbauen(doc, host, {
            sicht: 'modules',
            rows: rows,
            columns: _mitHilfe(_SPALTEN, 'modules', doc),
            Ctor: Ctor,
            // Die Zahl steht mit dem Substantiv DIESER Sicht, nicht mit
            // 'Datensätze' (Vorgabe des TableKit).
            einheit: 'Bausteine',
            eigene: [_ohneKennungSchalter(doc)],
            onRowClick: function (e, row) {
                var d = (typeof row.getData === 'function')
                    ? row.getData() : null;
                if (!d) { return; }
                _fillForm(d);
                _persistDraft();
            },
            tabulator: {
                // Zeilenidentitaet ueber die Datenbank-id: sie ist das
                // einzige Feld, das JEDE Zeile hat - der module_key fehlt
                // acht Altzeilen.
                index: 'id',
                // height:false + Seitenblaetterung: das dokumentierte
                // Muster gegen abgeschnittene Blaetterleisten (Beleg:
                // cockpit_lectorate.js:596-599, Console-Diagnose 2026-07-10).
                height: false,
                pagination: 'local',
                paginationSize: 15,
                paginationCounter: 'rows',
                locale: 'de-de',
                langs: {
                    'de-de': {
                        pagination: {
                            first: 'Erste', first_title: 'Erste Seite',
                            last: 'Letzte', last_title: 'Letzte Seite',
                            prev: 'Zurück', prev_title: 'Vorige Seite',
                            next: 'Weiter', next_title: 'Nächste Seite',
                            counter: {
                                showing: 'Zeige', of: 'von',
                                rows: 'Zeilen', pages: 'Seiten'
                            }
                        }
                    }
                },
                placeholder: 'Kein Baustein passt zu den gesetzten Filtern.',
                // Nach jedem Filter- und Seitenwechsel: Markierung der
                // gewaehlten Zeile neu setzen (Tabulator baut die Zeilen
                // dabei neu auf) und den Schalter mit dem echten
                // Filterstand abgleichen.
                dataFiltered: function () { _ohneKennungSyncen(); _markActive(); },
                renderComplete: function () { _markActive(); }
            }
        });
        _state.table = auf.table;
        return !!auf.table;
    }

    // _listeRueckfall: die Schaltflaechenliste aus Build 427 bis 652.
    // Sie bleibt erhalten, weil ueber die Liste AUSGEWAEHLT wird - ohne sie
    // waere die Sicht ohne Tabulator nicht bedienbar, sondern nur lesbar.
    function _listeRueckfall(host, rows, doc) {
        var hinweis = doc.createElement('p');
        hinweis.className = 'aiw-mod-empty ist-warnung';
        hinweis.textContent = 'Tabellenbibliothek nicht verfügbar — es folgt '
            + 'die einfache Liste. ' + rows.length + ' Bausteine.';
        host.appendChild(hinweis);

        var list = doc.createElement('div');
        list.className = 'aiw-mod-list';
        _state.listEl = list;
        if (!rows.length) {
            var empty = doc.createElement('p');
            empty.className = 'aiw-mod-empty';
            empty.textContent = 'Noch keine Bausteine angelegt.';
            list.appendChild(empty);
        }
        rows.forEach(function (m) {
            var it = doc.createElement('button');
            it.type = 'button';
            it.className = 'aiw-mod-item';
            it.setAttribute('data-hilfe-id', 'modules.bedienung.waehlen');
            it.setAttribute('data-key', zeilenKennung(m) || '');
            it.textContent = moduleLabel(m);
            it.addEventListener('click', function () {
                _fillForm(m);
                _persistDraft();
            });
            list.appendChild(it);
        });
        host.appendChild(list);
    }

    function _setMsg(text, kind) {
        if (!_state.msgEl) { return; }
        _state.msgEl.textContent = text || '';
        _state.msgEl.className = 'aiw-mod-msg' + (kind ? (' is-' + kind) : '');
    }

    // renderDryRun: Ergebnis der schreibfreien Vorschau. res=null leert. Fehler
    // (rot) haben Vorrang vor der Platzhalter-Zusammenfassung (gruen) —
    // Grundregel 1: Fehler nie still schlucken.
    function renderDryRun(res) {
        var box = _state.dryEl;
        if (!box) { return; }
        _clearNode(box);
        if (!res) { return; }
        var errs = errorsText(res.errors);
        if (errs) {
            var pe = document.createElement('p');
            pe.className = 'aiw-mod-dry is-err';
            pe.textContent = 'Nicht gueltig: ' + errs;
            box.appendChild(pe);
            return;
        }
        var ps = document.createElement('p');
        ps.className = 'aiw-mod-dry is-ok';
        var txt = summaryText(res.summary);
        ps.textContent = 'Felder OK' + (txt
            ? (' — Platzhalter: ' + txt)
            : ' — keine Platzhalter im Text.');
        box.appendChild(ps);
    }

    function dryRunError(msg) {
        var box = _state.dryEl;
        if (!box) { return; }
        _clearNode(box);
        var p = document.createElement('p');
        p.className = 'aiw-mod-dry is-err';
        p.textContent = 'Vorschau fehlgeschlagen: ' + (msg || 'unbekannt');
        box.appendChild(p);
    }

    function saved(res) {
        var created = !!(res && res.created);
        var tid = (res && res.target_id) ? res.target_id : '?';
        _setMsg('Baustein "' + tid + '" '
            + (created ? 'angelegt.' : 'geaendert.'), 'ok');
        _clearDraft();   // Build 488: gespeichert -> Zwischenspeicher verwerfen.
    }

    function saveError(msg) {
        _setMsg('Speichern fehlgeschlagen: ' + (msg || 'unbekannt'), 'err');
    }

    // --- Browser-Zwischenspeicher des Entwurfs (Build 488) ---------------
    function _draftFromState() {
        return { v: 1, fields: _currentFields(), selKey: _state.selKey,
                 selId: _state.selId, nachtragId: _state.nachtragId };
    }
    function _persistDraft() {
        var ls = _ls();
        if (!ls || !_state.fields) { return; }
        try { ls.setItem(DRAFT_KEY, JSON.stringify(_draftFromState())); }
        catch (e) { log('persistDraft', e); }
    }
    function _loadDraft() {
        var ls = _ls();
        if (!ls) { return null; }
        try {
            var s = ls.getItem(DRAFT_KEY);
            if (!s) { return null; }
            var d = JSON.parse(s);
            return (d && typeof d === 'object') ? d : null;
        } catch (e) { log('loadDraft', e); return null; }
    }
    function _clearDraft() {
        var ls = _ls();
        if (!ls) { return; }
        try { ls.removeItem(DRAFT_KEY); } catch (e) { log('clearDraft', e); }
    }
    // _restoreDraft: Entwurf laden, OHNE erneut zu persistieren. module_key ist
    // der Schluessel: im Editier-Modus (selKey gesetzt) fix, sonst editierbar.
    function _restoreDraft(d) {
        var f = _state.fields;
        if (!f || !d) { return; }
        var fl = d.fields || {};
        f.module_key.value = fl.module_key || '';
        f.title.value = fl.title || '';
        f.description.value = fl.description || '';
        f.role.value = fl.role || 'body';
        f.topic.value = fl.topic || '';
        f.body.value = fl.body || '';
        f.sort_order.value = (fl.sort_order === undefined
            || fl.sort_order === null) ? 0 : fl.sort_order;
        _state.selKey = (d.selKey === undefined) ? null : d.selKey;
        _state.selId = (d.selId === undefined) ? null : d.selId;
        _state.nachtragId = (d.nachtragId === undefined) ? null : d.nachtragId;
        // Build 575: KEINE eigene Sperrlogik mehr. Ein Entwurf aus einer
        // aelteren Fassung kann selKey als Zeichenkette "null" tragen; das
        // wird hier abgefangen, damit daraus keine Sperre ohne Inhalt wird.
        if (_state.selKey === 'null' || _state.selKey === 'undefined'
                || _state.selKey === '') {
            _state.selKey = null;
        }
        _schluesselFeldStand();
        _vorschauAktualisieren();
        renderDryRun(null);
        _markActive();
        _setMsg('Nicht gespeicherter Entwurf aus dem Browserspeicher '
            + 'wiederhergestellt. Speichern schliesst ihn ab.', '');
    }

    // renderModules: Gesamtsicht. data = {count, modules}. opts:
    //   onDryRun(payload) — schreibfreie Vorschau (cockpit.js -> POST)
    //   onSave(payload)   — auditiertes Speichern (cockpit.js -> POST)
    function renderModules(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        _clearNode(mainEl);

        var wrap = document.createElement('div');
        wrap.className = 'aiw-mod-wrap';

        var h = document.createElement('h2');
        h.className = 'aiw-pagetitle';
        h.textContent = 'Baustein-Module';
        // Build 598 (Baustelle H / H9): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'modules.titel');
        wrap.appendChild(h);
        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'modules.hinweis');
        sub.textContent = 'Wiederverwendbare Textbausteine pflegen. Der Text '
            + '(body) ist Freitext und darf Platzhalter wie {{a:name}} / '
            + '{{m:name}} / {{o:name}} enthalten; diese werden erst beim Rendern '
            + 'des konkreten Berichts aufgeloest. Vor dem Speichern mit '
            + '"Vorschau" pruefen.';
        wrap.appendChild(sub);

        var body = document.createElement('div');
        body.className = 'aiw-mod-body';

        // --- Oberer Bereich: "Neu" + Tabelle (Build 653, Ticket d60e893a).
        // Sie spannt ueber die ganze Breite. In einer 300px-Spalte waeren
        // Kopffilter und Blaetterleiste nicht bedienbar - deshalb der
        // Umzug nach oben, den das Ticket als Moeglichkeit nennt.
        var left = document.createElement('div');
        left.className = 'aiw-mod-listcol';
        var newBtn = document.createElement('button');
        newBtn.type = 'button';
        newBtn.className = 'aiw-mod-new';
        newBtn.textContent = '+ Neuer Baustein';
        newBtn.setAttribute('data-hilfe-id', 'modules.bedienung.neu');
        newBtn.addEventListener('click', function () {
            _fillForm(null);
            _persistDraft();   // Build 488: Neu-Modus als aktuellen Entwurf sichern.
        });
        left.appendChild(newBtn);

        var rows = moduleRows(data && data.modules);
        _state.listEl = null;
        _state.table = null;
        _state.nurOhneKennung = false;
        _state.nurOhneBtn = null;
        // Der Tabellenbereich entsteht HIER, wird aber erst nach dem
        // Einhaengen gefuellt: Tabulator misst seinen Behaelter wie
        // Editor.js, und auf einem nicht eingehaengten Element sind das
        // null Pixel (Lehre aus Build 570-573).
        var tabHost = document.createElement('div');
        tabHost.className = 'aiw-mod-tabelle';
        left.appendChild(tabHost);
        body.appendChild(left);

        // --- Rechte Spalte: Editor-Maske.
        var form = document.createElement('div');
        form.className = 'aiw-mod-form';

        // Marken an den ABNAHMESTELLEN der Fabrik '_labeledField' - sieben
        // verschiedene Felder aus einer Fabrik (Fabrikregel, Build 633).
        var fKey = _labeledField(form, 'module_key (A-Z a-z 0-9 . _ -)', 'text',
            'aiw-mod-key');
        fKey.setAttribute('data-hilfe-id',
            'modules.bedienung.schluessel');
        // Build 565: Hinweiszeile DIREKT unter dem Feld. Sie sagt, warum das
        // Feld gerade gesperrt oder offen ist - ein Feld, das mal geht und mal
        // nicht, ohne dass jemand sagt warum, wirkt kaputt.
        var keyHinweis = document.createElement('p');
        keyHinweis.className = 'aiw-mod-keyhinweis';
        form.appendChild(keyHinweis);
        _state.keyHinweisEl = keyHinweis;
        _state.vorschauEl = null;
        _state.vorschau = null;
        _state.vorschauAn = true;
        var fTitle = _labeledField(form, 'Titel', 'text', 'aiw-mod-title');
        fTitle.setAttribute('data-hilfe-id',
            'modules.bedienung.titel');
        var fRole = _labeledField(form, 'Rolle', 'select', 'aiw-mod-role');
        fRole.setAttribute('data-hilfe-id',
            'modules.bedienung.rolle');
        ROLES.forEach(function (r) {
            var opt = document.createElement('option');
            opt.value = r;
            opt.textContent = roleLabel(r);
            fRole.appendChild(opt);
        });
        var fTopic = _labeledField(form, 'Thema (topic)', 'text', 'aiw-mod-topic');
        fTopic.setAttribute('data-hilfe-id',
            'modules.bedienung.thema');
        var fDesc = _labeledField(form, 'Beschreibung (optional)', 'textarea',
            'aiw-mod-desc');
        fDesc.setAttribute('data-hilfe-id',
            'modules.bedienung.beschreibung');
        fDesc.rows = 2;
        var fBody = _labeledField(form, 'Bausteintext (body)', 'textarea',
            'aiw-mod-bodytext');
        fBody.setAttribute('data-hilfe-id',
            'modules.bedienung.bausteintext');
        var fSort = _labeledField(form, 'Sortierung', 'number', 'aiw-mod-sort');
        fSort.setAttribute('data-hilfe-id',
            'modules.bedienung.sortierung');

        // Aktionen: Vorschau + Speichern + Rueckmeldung + Ausgabe.
        var actions = document.createElement('div');
        actions.className = 'aiw-mod-actions';
        var dryBtn = document.createElement('button');
        dryBtn.type = 'button';
        dryBtn.className = 'aiw-mod-drybtn';
        dryBtn.textContent = 'Vorschau (schreibfrei)';
        dryBtn.setAttribute('data-hilfe-id', 'modules.bedienung.probelauf');
        actions.appendChild(dryBtn);
        var saveBtn = document.createElement('button');
        saveBtn.type = 'button';
        saveBtn.className = 'aiw-mod-save';
        saveBtn.textContent = 'Speichern (auditiert)';
        saveBtn.setAttribute('data-hilfe-id', 'modules.bedienung.speichern');
        actions.appendChild(saveBtn);
        var msg = document.createElement('span');
        msg.className = 'aiw-mod-msg';
        _state.msgEl = msg;
        actions.appendChild(msg);
        form.appendChild(actions);

        var dry = document.createElement('div');
        dry.className = 'aiw-mod-dryout';
        _state.dryEl = dry;
        form.appendChild(dry);

        // --- Platzhalter-Tabelle (Build 654, Ticket 4b032177).
        // Sie steht UNTER der Maske und nicht in der Vorschau-Spalte: sie
        // gehoert zum Schreiben des Textes, nicht zum Ansehen des Ergebnisses.
        var phKopf = document.createElement('div');
        phKopf.className = 'aiw-mod-ph-kopf';
        phKopf.setAttribute('data-hilfe-id', 'modules.bedienung.phtabelle');
        phKopf.textContent = 'Platzhalter im Bausteintext';
        form.appendChild(phKopf);
        var phHost = document.createElement('div');
        phHost.className = 'aiw-mod-ph';
        phHost.id = 'aiw-mod-ph';
        form.appendChild(phHost);
        _state.platzhalter = null;

        body.appendChild(form);

        // --- Dritte Spalte: Vorschau (Build 652, Ticket 3508ad71).
        // Sie wird HIER erzeugt, damit sie im Raster steht; GEFUELLT wird sie
        // erst nach dem Einhaengen (siehe unten) - Editor.js misst.
        var vsCol = document.createElement('div');
        vsCol.className = 'aiw-mod-vorschaucol';
        body.appendChild(vsCol);

        wrap.appendChild(body);
        mainEl.appendChild(wrap);

        _state.fields = {
            module_key: fKey, title: fTitle, role: fRole, topic: fTopic,
            description: fDesc, body: fBody, sort_order: fSort
        };

        // Build 488: jede Nutzer-Eingabe sichert den Stand (programmatische
        // .value-Zuweisungen loesen kein input/change aus -> kein Ueberschreiben).
        form.addEventListener('input', _persistDraft);
        form.addEventListener('change', _persistDraft);

        // BUILD 577: DIE VORSCHAU ENTSTEHT ERST JETZT — nach mainEl.appendChild.
        // Editor.js misst beim Aufbau die Groesse seines Behaelters; auf einem
        // noch nicht eingehaengten Element sind das NULL Pixel, und es zeichnet
        // ins Nichts. Genau dieser Fehler hat in Build 570 bis 573 die
        // Kacheldiagramme unsichtbar gemacht; die Lehre steht hier als Zeile.
        // Build 654: die Kataloge fuer die Platzhalter-Tabelle. Sie kommen
        // aus cockpit.js (zwei schreibfreie Abrufe) und duerfen fehlen -
        // dann sagt die Tabelle, dass sie ohne Katalog urteilt.
        if (opts.placeholders !== undefined) {
            var php = (typeof window !== 'undefined')
                ? window.AIWBausteinPlatzhalter : null;
            _state.phKatalog = (php && opts.placeholders)
                ? php.katalogIndex(opts.placeholders) : null;
        }
        if (opts.validationRules !== undefined) {
            _state.phRegeln = opts.validationRules || null;
        }

        // Build 652: Ziel ist die dritte Rasterspalte, nicht mehr das Formular.
        _vorschauAufbauen(vsCol);
        _platzhalterAufbauen(phHost);

        // BUILD 653: DIE TABELLE EBENFALLS ERST JETZT - aus demselben Grund.
        // Gelingt sie nicht, tritt die alte Schaltflaechenliste an ihre
        // Stelle. KEIN STILLER AUSFALL: der Rueckfall sagt im Klartext, dass
        // er einer ist, und nennt die Zahl der Bausteine.
        if (!_listeAufbauen(tabHost, rows, document, opts.Tabulator)) {
            _listeRueckfall(tabHost, rows, document);
        }

        // Beim Tippen mitlaufen, aber entprellt: Editor.js baut je Aktualisierung
        // eine Instanz auf, und das bei jedem Tastendruck waere Verschwendung.
        var vsTimer = null;
        fBody.addEventListener('input', function () {
            if (vsTimer) { clearTimeout(vsTimer); }
            vsTimer = setTimeout(_vorschauAktualisieren, 350);
        });

        dryBtn.addEventListener('click', function () {
            _setMsg('');
            if (typeof opts.onDryRun === 'function') {
                opts.onDryRun(buildPayload(_currentFields()));
            }
        });
        saveBtn.addEventListener('click', function () {
            renderDryRun(null);
            if (typeof opts.onSave === 'function') {
                opts.onSave(buildPayload(_currentFields()));
            }
        });

        _fillForm(null);
        // Build 488: noch nicht gespeicherter Entwurf aus dem Browserspeicher
        // hat Vorrang vor dem leeren Neu-Modus (Neuladen verliert keine Arbeit).
        var _saved = _loadDraft();
        if (_saved) { _restoreDraft(_saved); }
        log('renderModules:', rows.length, 'Bausteine');
        return wrap;
    }

    function cleanup() {
        // Build 653: die Tabelle haelt Ereignisbindungen und einen eigenen
        // DOM-Baum. Sie wird ABGEBAUT, nicht nur vergessen - dieselbe Regel
        // wie fuer die Editor-Instanz der Vorschau.
        if (_state.table && typeof _state.table.destroy === 'function') {
            try { _state.table.destroy(); }
            catch (e) { /* Abbau darf nie werfen */ }
        }
        _state.table = null;
        _state.nurOhneBtn = null;
        _state.nurOhneKennung = false;
        _state.listEl = null;
        _state.fields = null;
        _state.msgEl = null;
        _state.dryEl = null;
        _state.selKey = null;
        _state.selId = null;
        _state.nachtragId = null;
        // Build 652: die Editor-Instanz der Vorschau haelt einen DOM-Baum
        // fest. Beim Verlassen der Sicht wird sie ABGEBAUT, nicht nur
        // vergessen - sonst bleibt sie samt Behaelter im Speicher stehen.
        if (_state.vorschau && typeof _state.vorschau.aus === 'function') {
            try { _state.vorschau.aus(); } catch (e) { /* Abbau darf nie werfen */ }
        }
        _state.vorschau = null;
        _state.vorschauEl = null;
        _state.vorschauSpalte = null;
        _state.vorschauSpaltenStand = null;
        // Build 654: die Platzhalter-Tabelle raeumt ihre Zeilen selbst weg.
        // Die KATALOGE bleiben stehen - sie sind Netzdaten, keine Sichtdaten,
        // und ein erneuter Abruf beim naechsten Betreten waere Verschwendung.
        if (_state.platzhalter && typeof _state.platzhalter.aus === 'function') {
            try { _state.platzhalter.aus(); } catch (e) { /* nie werfen */ }
        }
        _state.platzhalter = null;
    }

    // -------------------------------------------------------------------------
    // OEFFENTLICHE API. Reine Funktionen zuerst (vitest), dann DOM.
    // -------------------------------------------------------------------------
    window.AIWCockpitModules = {
        // reine Funktionen (vitest)
        roleLabel: roleLabel,
        moduleLabel: moduleLabel,
        sortModules: sortModules,
        moduleRows: moduleRows,           // Tabellenzeilen (Build 653)
        zeilenKennung: zeilenKennung,     // Adressweg einer Zeile (Build 653)
        isValidKey: isValidKey,
        buildPayload: buildPayload,
        schluesselVorschlag: schluesselVorschlag,
        _vorschauAktualisieren: _vorschauAktualisieren,
        _schluesselFeldStand: _schluesselFeldStand,
        summaryText: summaryText,
        errorsText: errorsText,
        ROLES: ROLES,
        DRAFT_KEY: DRAFT_KEY,             // Browser-Zwischenspeicher (Build 488)
        VORSCHAU_KEY: VORSCHAU_KEY,       // Zuklapp-Stand der Vorschau (Build 652)
        // DOM
        renderModules: renderModules,
        renderDryRun: renderDryRun,
        dryRunError: dryRunError,
        saved: saved,
        saveError: saveError,
        cleanup: cleanup
    };
})();
