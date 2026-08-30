/**
 * tests/unit/test_vollzitat_editor.test.js
 * Unit-Tests fuer die vierte Darstellungsvariante des EvidenceBlock
 * (userinfo/report_editor.js, Build 726).
 *
 * Auftrag Chef-Ermittlerin 27.08.2026, neun Anforderungen. Die Bildschirmseite
 * holt das FERTIGE Vollzitat vom Server (GET /_forensic/vollzitat) und malt
 * es - sie rechnet es nicht selbst. Begruendung im Quelltext
 * (_fetchVollzitat) und im Kopf von forensic_api/vollzitat.py.
 *
 * VE01 - 'fullquote' steht im Einstellmenue und ist NICHT die Vorgabe
 * VE02 - der Badge nennt die Variante "Vollzitat"
 * VE03 - im Vollzitat-Modus wird /_forensic/vollzitat gerufen, mit den IDs
 * VE04 - die Antwort wird gezeichnet: Quelle, Datum, Absatz, Befund
 * VE05 - die Hinterlegung der Markierung kommt UNVERAENDERT vom Server
 * VE06 - Vorbehalte (schwacher Absatzweg, zerlegter Name) werden gezeigt
 * VE07 - Warnungen zur Beleglage stehen am Block (GR1)
 * VE08 - ein Serverfehler erzeugt eine SICHTBARE Meldung, keine leere Flaeche
 * VE09 - und loest KEINE Endlosschleife aus (hoechstens ein zweiter Ruf)
 * VE10 - Klartext wird escaped, das Absatz-Fragment NICHT
 * VE11 - GEGENPROBE: im Modus 'list' wird /_forensic/vollzitat NICHT gerufen
 *
 * Alle Inhalte sind erfunden.
 *
 * Version: v0.8.726 - Build: 726 - 2026-08-27
 */

import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

// --- Die Antwort, die der Server liefert (forensic_api/vollzitat.py) -------
const ANTWORT = {
    beschriftung: "Ortsbezuege",
    beleg_anzahl: 2,
    quellen_anzahl: 1,
    warnungen: ["Beleg #4712: Der Anker loest nicht auf."],
    abgeschnitten: 0,
    unterbloecke: [{
        bezeichnung: "Beitrag zum Thema »Wochenendtreffen & <Sueden>«",
        ist_pn: false,
        betreff: "Wochenendtreffen & <Sueden>",
        partner: null,
        posted_ts: 1710452820,
        post_id: 1891354,
        link: "/forum/viewtopic.php?id=41623#p1891354",
        absaetze: [{
            html: '<p>Ich fahre los, von <span class="vz-mark vz-cat-CAT_LOCATION" '
                + 'style="background-color: #d3e3fd;" data-beleg="1">Bad Honnef</span> aus.</p>',
            nummern: [1],
            ersatz: false,
        }],
        befunde: [
            {
                nummer: 1, annotation_id: 4711, kategorie: "CAT_LOCATION",
                kategorie_text: "LOC – Ortsangaben, geografische Hinweise",
                css_klasse: "vz-cat-CAT_LOCATION", farbe: "#d3e3fd",
                markierung: "Bad Honnef", notiz: "Ausgangsort <wichtig>",
                ermittler: "KHK Bergmann", name_quelle: "ad_felder",
                absatz_weg: "xpath", hinweis: "",
            },
            {
                nummer: 2, annotation_id: 4712, kategorie: "CAT_PERSON",
                kategorie_text: "PER – Persönliche Identifikationsmerkmale",
                css_klasse: "vz-cat-CAT_PERSON", farbe: "#fcf1d0",
                markierung: "Mein Bruder", notiz: "Begleitperson.",
                ermittler: "Okonkwo", name_quelle: "display_name",
                absatz_weg: "text", hinweis: "ueber den Wortlaut gefunden",
            },
        ],
    }],
};

function makeDOM(fetchStub) {
    const dom = new JSDOM(
        `<!DOCTYPE html><html><body>
            <div id="report-editor-body"></div>
            <div id="report-selector-container"></div>
            <div id="report-editor-container"></div>
        </body></html>`,
        { runScripts: "dangerously", url: "http://localhost" }
    );
    dom.window.esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    dom.window.EditorState = { lockId: null };
    dom.window.EditorTools = {};
    dom.window.EditorJS = null;
    dom.window.crypto = { randomUUID: () => "t-" + Math.random().toString(36).slice(2) };
    dom.window.fetch = fetchStub
        || (() => Promise.resolve({ ok: false, json: () => Promise.resolve(null) }));
    dom.window.eval(readFileSync("userinfo/report_editor.js", "utf-8"));
    return dom;
}

/** Ein fetch-Ersatz, der die gerufenen Adressen mitschreibt. */
function spion(antwort, ok = true, status = 200) {
    const rufe = [];
    const fn = (url) => {
        rufe.push(String(url));
        if (String(url).indexOf("/_forensic/vollzitat") === -1) {
            return Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
        }
        return Promise.resolve({
            ok, status,
            json: () => Promise.resolve(antwort),
        });
    };
    fn.rufe = rufe;
    fn.vollzitatRufe = () => rufe.filter(u => u.indexOf("/_forensic/vollzitat") !== -1);
    return fn;
}

function block(dom, modus, ids) {
    return new dom.window.EvidenceBlock({
        data: { evidence_ids: ids, group_label: "Ortsbezuege", display_mode: modus },
        api: {},
        readOnly: true,
    });
}

/** Auf die Wirkung des asynchronen Holens warten. */
const ruhe = () => new Promise(r => setTimeout(r, 0));

describe("EvidenceBlock - Vollzitat (Build 726)", () => {

    it("VE01 - 'fullquote' steht im Einstellmenue und ist nicht die Vorgabe", () => {
        const dom = makeDOM();
        const b = block(dom, "list", []);
        b.render();
        const panel = b.renderSettings();
        const schluessel = Array.from(panel.querySelectorAll(".cdx-settings-button"))
            .map(el => el.dataset.key);
        expect(schluessel).toEqual(["list", "table", "quote", "fullquote"]);
        // Vorgabe bleibt 'list' - sonst aendert sich das Aussehen ALLER
        // Bestandsberichte, ohne dass jemand es gewaehlt haette.
        const ohne = new dom.window.EvidenceBlock({
            data: { evidence_ids: [] }, api: {}, readOnly: true });
        expect(ohne._data.display_mode).toBe("list");
    });

    it("VE02 - der Badge nennt die Variante 'Vollzitat'", async () => {
        const dom = makeDOM(spion(ANTWORT));
        const b = block(dom, "fullquote", [4711]);
        const el = b.render();
        await ruhe();
        expect(el.querySelector(".evidence-block-mode-badge").textContent)
            .toBe("Vollzitat");
        expect(el.className).toContain("evidence-block--mode-fullquote");
    });

    it("VE03 - /_forensic/vollzitat wird mit den IDs gerufen", async () => {
        const f = spion(ANTWORT);
        const dom = makeDOM(f);
        block(dom, "fullquote", [4711, 4712]).render();
        await ruhe();
        const rufe = f.vollzitatRufe();
        expect(rufe.length).toBeGreaterThan(0);
        expect(rufe[0]).toContain("ids=4711%2C4712");
        expect(rufe[0]).toContain("label=Ortsbezuege");
    });

    it("VE04 - die Antwort wird gezeichnet", async () => {
        const dom = makeDOM(spion(ANTWORT));
        const el = block(dom, "fullquote", [4711, 4712]).render();
        await ruhe();
        const html = el.innerHTML;
        // Art der Quelle (Anforderung 7)
        expect(html).toContain("Beitrag zum Thema");
        // Originaldatum der Quelle, nicht der Annotation (Anforderung 4)
        expect(html).toContain("14.03.2024");
        // Der Link (Anforderung 5)
        expect(html).toContain("viewtopic.php?id=41623");
        // Der Absatz (Anforderung 2)
        expect(html).toContain("Ich fahre los, von");
        // Nachname des Ermittlers (Anforderung 1)
        expect(html).toContain("KHK Bergmann");
        // Die Notiz (Anforderung 8)
        expect(html).toContain("Ausgangsort");
        // Ein Unterblock fuer beide Belege (Anforderung 9)
        expect(el.querySelectorAll(".vz-quelle").length).toBe(1);
        expect(el.querySelectorAll(".vz-befund").length).toBe(2);
    });

    it("VE05 - die Hinterlegung kommt unveraendert vom Server", async () => {
        const dom = makeDOM(spion(ANTWORT));
        const el = block(dom, "fullquote", [4711]).render();
        await ruhe();
        const mark = el.querySelector(".vz-mark");
        expect(mark).not.toBeNull();
        expect(mark.getAttribute("style")).toContain("#d3e3fd");
        expect(mark.textContent).toBe("Bad Honnef");
    });

    it("VE06 - Vorbehalte werden gezeigt", async () => {
        const dom = makeDOM(spion(ANTWORT));
        const el = block(dom, "fullquote", [4711, 4712]).render();
        await ruhe();
        const texte = Array.from(el.querySelectorAll(".vz-unsicher"))
            .map(n => n.textContent).join(" ");
        expect(texte).toContain("Wortlaut");
        expect(texte).toContain("Anzeigenamen");
        // Der Beleg mit gesichertem Weg bekommt KEINEN Vorbehalt.
        expect(el.querySelectorAll(".vz-unsicher").length).toBe(1);
    });

    it("VE07 - Warnungen zur Beleglage stehen am Block", async () => {
        const dom = makeDOM(spion(ANTWORT));
        const el = block(dom, "fullquote", [4711, 4712]).render();
        await ruhe();
        const w = el.querySelector(".vz-warnungen");
        expect(w).not.toBeNull();
        expect(w.textContent).toContain("Anker loest nicht auf");
    });

    it("VE08 - ein Serverfehler erzeugt eine sichtbare Meldung", async () => {
        const dom = makeDOM(spion(null, false, 500));
        const el = block(dom, "fullquote", [4711]).render();
        await ruhe();
        const fehler = el.querySelector(".vz-fehlt");
        expect(fehler).not.toBeNull();
        expect(fehler.textContent).toContain("500");
        // Keine leere Flaeche - GR1: ein Ausfall wird benannt.
        expect(el.textContent).not.toContain("Vollzitat wird geladen");
    });

    it("VE09 - ein Fehlschlag loest keine Endlosschleife aus", async () => {
        const f = spion(null, false, 500);
        const dom = makeDOM(f);
        const b = block(dom, "fullquote", [4711]);
        b.render();
        await ruhe();
        await ruhe();
        b._renderContent();
        await ruhe();
        // Hoechstens ein Ruf: nach dem Fehlschlag ist _vollzitatHtml nicht
        // mehr null und loest kein erneutes Holen aus.
        expect(f.vollzitatRufe().length).toBe(1);
    });

    it("VE10 - Klartext wird escaped, das Absatz-Fragment nicht", async () => {
        const dom = makeDOM(spion(ANTWORT));
        const el = block(dom, "fullquote", [4711]).render();
        await ruhe();
        const html = el.innerHTML;
        // Der Betreff traegt '<' und '&' - ein Forum ist voll davon.
        expect(html).toContain("&lt;Sueden&gt;");
        expect(html).not.toContain("<Sueden>");
        expect(html).toContain("&lt;wichtig&gt;");
        // Das Absatz-Fragment kommt fertig vom Server und bleibt Markup.
        expect(el.querySelector(".vz-absatz p")).not.toBeNull();
    });

    it("VE11 - GEGENPROBE: im Modus 'list' wird nicht gerufen", async () => {
        // Ein Test, der nicht anschlagen kann, ist kein Test: ohne diese
        // Gegenprobe belegte VE03 nur, dass irgendwann irgendetwas gerufen
        // wird.
        const f = spion(ANTWORT);
        const dom = makeDOM(f);
        const el = block(dom, "list", [4711, 4712]).render();
        await ruhe();
        expect(f.vollzitatRufe().length).toBe(0);
        expect(el.querySelector(".vz-quelle")).toBeNull();
        expect(el.innerHTML).toContain("evidence-items--list");
    });
});

// ===========================================================================
// Build 727 — Befunde aus der Sichtpruefung vom 28.08.2026
// ===========================================================================
//
// VE12 - ein Beleg, den es nicht mehr gibt, bekommt einen EIGENEN Kasten
//        und KEINE erfundene Quellenart
// VE13 - mehrere moegliche Fundstellen werden alle gezeigt und benannt
// VE14 - eine aus dem Seitenabzug abgeleitete Beitragsnummer wird als solche
//        ausgewiesen
// VE15 - GEGENPROBE: eine Nummer aus der Annotation traegt den Zusatz NICHT

const ANTWORT_727 = {
    beschriftung: "Sammlung",
    beleg_anzahl: 3, quellen_anzahl: 3, warnungen: [], abgeschnitten: 0,
    unterbloecke: [
        {   // (a) Beleg existiert nicht mehr
            bezeichnung: "Beleg nicht mehr vorhanden", fehlt: true,
            ist_pn: false, betreff: null, partner: null, posted_ts: null,
            post_id: null, link: "", post_quelle: "keine",
            absaetze: [],
            befunde: [{ nummer: 1, annotation_id: 14, kategorie: "",
                        kategorie_text: "Unbekannte Kategorie",
                        css_klasse: "vz-cat-unbekannt", farbe: "#dfdfdf",
                        markierung: "", notiz: "", ermittler: "",
                        name_quelle: "kuerzel", absatz_weg: "fehlt",
                        hinweis: "keine aktive Annotation" }],
        },
        {   // (b) mehrdeutiger Wortlaut
            bezeichnung: "Beitrag zum Thema »Treffen«", fehlt: false,
            ist_pn: false, betreff: "Treffen", partner: null,
            posted_ts: 1710452820, post_id: null, link: "/forum/x",
            post_quelle: "keine",
            absaetze: [
                { html: "<p>Erste Stelle</p>", nummern: [1], ersatz: false,
                  moeglich: true, von_gesamt: [1, 2] },
                { html: "<p>Zweite Stelle</p>", nummern: [1], ersatz: false,
                  moeglich: true, von_gesamt: [2, 2] },
            ],
            befunde: [{ nummer: 1, annotation_id: 20, kategorie: "CAT_OTHER",
                        kategorie_text: "SON – Sonstige", css_klasse: "x",
                        farbe: "#cff1e7", markierung: "Bonn", notiz: "",
                        ermittler: "KHK Muster", name_quelle: "ad_felder",
                        absatz_weg: "text", hinweis: "kommt 2 mal vor" }],
        },
        {   // (c) Beitragsnummer aus dem Seitenabzug abgeleitet
            bezeichnung: "Beitrag zum Thema »Treffen«", fehlt: false,
            ist_pn: false, betreff: "Treffen", partner: null,
            posted_ts: 1710452820, post_id: 1891354, link: "/forum/y#p1891354",
            post_quelle: "seitenabzug",
            absaetze: [{ html: "<p>Ein Absatz</p>", nummern: [1],
                         ersatz: false, moeglich: false, von_gesamt: null }],
            befunde: [{ nummer: 1, annotation_id: 21, kategorie: "CAT_OTHER",
                        kategorie_text: "SON – Sonstige", css_klasse: "x",
                        farbe: "#cff1e7", markierung: "Bonn", notiz: "",
                        ermittler: "KHK Muster", name_quelle: "ad_felder",
                        absatz_weg: "text", hinweis: "" }],
        },
    ],
};

describe("EvidenceBlock — Vollzitat, Befunde der Sichtpruefung (Build 727)", () => {

    async function gezeichnet() {
        const dom = makeDOM(spion(ANTWORT_727));
        const el = block(dom, "fullquote", [14, 20, 21]).render();
        await ruhe();
        return el;
    }

    it("VE12 - ein fehlender Beleg bekommt einen eigenen Kasten", async () => {
        const el = await gezeichnet();
        const kasten = el.querySelector(".vz-quelle--fehlt");
        expect(kasten).not.toBeNull();
        expect(kasten.textContent).toContain("Beleg nicht mehr vorhanden");
        expect(kasten.textContent).toContain("#14");
        expect(kasten.textContent).toContain("keine aktive Annotation");
        // KEINE erfundene Quellenart und KEIN irrefuehrender Vorbehalt.
        expect(kasten.textContent).not.toContain("Beitrag zum Thema");
        expect(kasten.textContent).not.toContain("Absatz nicht auffindbar");
        expect(kasten.querySelector(".vz-meta")).toBeNull();
    });

    it("VE13 - alle moeglichen Fundstellen werden gezeigt und benannt", async () => {
        const el = await gezeichnet();
        const moegliche = el.querySelectorAll(".vz-absatz.vz-moeglich");
        expect(moegliche.length).toBe(2);
        const texte = Array.from(el.querySelectorAll(".vz-moeglich-kopf"))
            .map(n => n.textContent.trim());
        expect(texte).toEqual(["Mögliche Fundstelle 1 von 2",
                               "Mögliche Fundstelle 2 von 2"]);
    });

    it("VE14 - abgeleitete Beitragsnummer wird ausgewiesen", async () => {
        const el = await gezeichnet();
        const metas = Array.from(el.querySelectorAll(".vz-meta"))
            .map(n => n.textContent.replace(/\s+/g, " "));
        const mit = metas.filter(t => t.includes("#1891354"));
        expect(mit.length).toBe(1);
        expect(mit[0]).toContain("aus dem Seitenabzug bestimmt");
    });

    it("VE15 - GEGENPROBE: eine Nummer aus der Annotation ohne Zusatz", async () => {
        // Ein Test, der nicht anschlagen kann, ist kein Test: mit
        // post_quelle='annotation' darf der Zusatz NICHT erscheinen.
        const daten = JSON.parse(JSON.stringify(ANTWORT_727));
        daten.unterbloecke[2].post_quelle = "annotation";
        const dom = makeDOM(spion(daten));
        const el = block(dom, "fullquote", [14, 20, 21]).render();
        await ruhe();
        expect(el.innerHTML).toContain("#1891354");
        expect(el.innerHTML).not.toContain("aus dem Seitenabzug bestimmt");
    });
});

// ===========================================================================
// Build 727 — die Beitragsnummer an der Quelle (toolbar/toolbar.js)
// ===========================================================================
//
// TB01 - eine Markierung in einem <article id="pNNN"> liefert NNN
// TB02 - dasselbe fuer die PN-Ansicht (<div id="pNNN" class="blockpost">)
// TB03 - ausserhalb eines Beitrags (Uebersichtsseite) bleibt es bei null
// TB04 - GEGENPROBE: ohne Auswahl gibt es keine Nummer

import { readFileSync as _lese } from "fs";

function toolbarDOM(innenHtml) {
    const dom = new JSDOM(
        `<!DOCTYPE html><html><body>
            <div id="forensic-toolbar"></div>
            <div id="forensic-viewport">${innenHtml}</div>
        </body></html>`,
        { runScripts: "dangerously", url: "http://localhost" });
    dom.window.fetch = () => Promise.resolve({ ok: false, json: () => ({}) });
    dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
    dom.window.eval(_lese("toolbar/toolbar.js", "utf-8"));
    return dom;
}

/** Setzt die Auswahl auf den ersten Textknoten von 'sel'. */
function waehle(dom, selektor) {
    const el = dom.window.document.querySelector(selektor);
    const range = dom.window.document.createRange();
    range.selectNodeContents(el);
    const s = dom.window.getSelection();
    s.removeAllRanges();
    s.addRange(range);
}

/**
 * Der Startknoten der stehenden Auswahl.
 *
 * BUILD 735 - WARUM DIESE HILFE JETZT NOETIG IST: '_postElementVon' bekommt
 * den Knoten seit Build 735 UEBERGEBEN und schlaegt ihn nicht mehr selbst
 * ueber 'window.getSelection()' nach. Das war die Ursache dafuer, dass
 * Build 727 im Betrieb nie einen Wert lieferte - der einzige Aufrufweg
 * loeschte die Auswahl vorher. Die Tests hier bilden den neuen Vertrag ab.
 */
function startknoten(dom) {
    const s = dom.window.getSelection();
    return s.rangeCount ? s.getRangeAt(0).startContainer : null;
}

describe("MarkerToolModule._postElementVon (Build 727)", () => {

    it("TB01 - Vollansicht: <article class='post' id='p1891354'>", () => {
        const dom = toolbarDOM(
            '<div id="brd-main"><article class="post" id="p1891354">' +
            '<div class="postmsg"><p id="ziel">Ich fahre nach Bonn.</p>' +
            '</div></article></div>');
        waehle(dom, "#ziel");
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        expect(fn(startknoten(dom))).toBe(1891354);
    });

    it("TB02 - PN-Ansicht: <div id='p44573' class='blockpost'>", () => {
        const dom = toolbarDOM(
            '<div id="p44573" class="blockpost"><div class="postmsg">' +
            '<p id="ziel">Meld dich kurz vorher.</p></div></div>');
        waehle(dom, "#ziel");
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        expect(fn(startknoten(dom))).toBe(44573);
    });

    it("TB03 - ausserhalb eines Beitrags bleibt es bei null", () => {
        // Uebersichts- und Suchseiten haben keine Beitraege. Dann faellt der
        // Bericht auf die Ableitung aus dem Seitenabzug zurueck und BENENNT
        // das - geraten wird nichts.
        const dom = toolbarDOM('<div id="vf"><table><tbody><tr>' +
            '<td id="ziel">Ein Themenlink</td></tr></tbody></table></div>');
        waehle(dom, "#ziel");
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        expect(fn(startknoten(dom))).toBeNull();
    });

    it("TB04 - GEGENPROBE: ohne Auswahl keine Nummer", () => {
        const dom = toolbarDOM(
            '<article class="post" id="p1"><p id="ziel">Text</p></article>');
        dom.window.getSelection().removeAllRanges();
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        // Ohne Auswahl gibt es keinen Startknoten - und ohne Startknoten
        // keine Nummer. Seit Build 735 ist genau das der Vertrag: die
        // Funktion RAET nicht, wenn ihr nichts uebergeben wird.
        expect(fn(startknoten(dom))).toBeNull();
        expect(fn(null)).toBeNull();
    });

    // -----------------------------------------------------------------------
    // Build 728 — die INNERE Kennung.
    //
    // viewtopic0.php vergibt an ineinanderliegenden Elementen DESSELBEN
    // Beitrags zwei Kennungen: aussen 'p<id>' am <article>, innen 'pp<id>'
    // am <div class="box">. Beim Aufstieg wird die innere ZUERST erreicht.
    // Build 727 pruefte nur /^p\d+$/ — die innere passte nicht, der Aufstieg
    // lief bis zum <article> weiter, und das Ergebnis war richtig. Es hing
    // aber daran, dass der <article> da ist. Weisung Alex 28.08.2026 nennt
    // ausdruecklich die innere Kennung; die Doppelung ist im Webserver seit
    // langem bekannt (db/forensic_db.py:307).
    // -----------------------------------------------------------------------

    it("TB05 - beide Kennungen zugleich: dieselbe Nummer, kein NaN", () => {
        const dom = toolbarDOM(
            '<article class="post" id="p1891354"><div class="blockpost">' +
            '<div class="box" id="pp1891354"><div class="postmsg">' +
            '<p id="ziel">Ich fahre nach Bonn.</p>' +
            '</div></div></div></article>');
        waehle(dom, "#ziel");
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        // Die INNERE wird zuerst erreicht. Bis Build 727 wurde sie
        // uebersprungen; jetzt trifft sie — die Nummer muss dieselbe sein.
        expect(fn(startknoten(dom))).toBe(1891354);
    });

    it("TB06 - NUR die innere Kennung: bis Build 727 blieb es bei null", () => {
        const dom = toolbarDOM(
            '<div class="box" id="pp5150"><div class="postmsg">' +
            '<p id="ziel">Kein article darum herum.</p></div></div>');
        waehle(dom, "#ziel");
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        expect(fn(startknoten(dom))).toBe(5150);
    });

    // -----------------------------------------------------------------------
    // TB08/TB09 — DIE BEIDEN ECHTEN AUFBAUTEN.
    //
    // Uebergeben von Alex am 28.08.2026, gekuerzt und ohne Inhalte, in der
    // Schachtelung unveraendert. Sie sind VERSCHIEDEN, und darauf kommt es an:
    //
    //   Forenbeitrag:      <article id="p<N>"> … <div class="box" id="pp<N>">
    //                      -> beide Kennungen, die INNERE zuerst erreicht
    //   Private Nachricht: <div id="p<N>" class="blockpost"> … <div class="box">
    //                      -> die '.box' hat dort GAR KEINE Kennung
    //
    // Haette man Alex' Weisung ("Suche nach <div class='box' id='pp<post_id>'>")
    // als EINZIGEN Weg genommen, waeren die privaten Nachrichten leer
    // geblieben — und dort haengt am post_id der Gespraechspartner.
    // -----------------------------------------------------------------------

    it("TB08 - echter Forenbeitrag (viewtopic): innere Kennung trifft", () => {
        const dom = toolbarDOM(
            '<article class="post" style="" id="p1164441">' +
            '<div class="blockpost"><h2><strong>POSTER</strong></h2>' +
            '<div class="box" id="pp1164441"><div class="inbox">' +
            '<div class="postbody"><div class="postleft"><dl>' +
            '<dd><span>Posts: 114</span></dd></dl></div>' +
            '<div class="postright"><div class="postmsg">' +
            '<p id="ziel">Der Zug faehrt ab Hauptbahnhof.</p>' +
            '</div></div></div></div></div></div></article>');
        waehle(dom, "#ziel");
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        expect(fn(startknoten(dom))).toBe(1164441);
    });

    it("TB09 - echte private Nachricht (pmsnew): '.box' OHNE Kennung", () => {
        const dom = toolbarDOM(
            '<div class="block2col"><div class="block">' +
            '<h2>TITEL DER UNTERHALTUNG</h2></div></div>' +
            '<div id="p120862" class="blockpost roweven contains_traces">' +
            '<h2><span><span class="conr">#2</span>' +
            '<a href="pmsnew.php?mdl=topic&amp;pid=120862#p120862">' +
            'Mon., 26.04.2021 20:36:03</a></span></h2>' +
            '<div class="box"><div class="inbox"><div class="postbody">' +
            '<div class="postleft"><dl><dt><strong>INHABER</strong></dt>' +
            '</dl></div><div class="postright"><div class="postmsg">' +
            '<p id="ziel">Ich bin ab Freitag in Koeln.</p>' +
            '</div></div></div></div></div>' +
            '<div class="aiw-flag-fallback aux-part"></div></div>');
        waehle(dom, "#ziel");
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        // Die kennungslose '.box' darf den Aufstieg weder abbrechen noch
        // selbst eine Nummer liefern — die Nummer steht nur aussen.
        expect(fn(startknoten(dom))).toBe(120862);
    });

    it("TB07 - GEGENPROBE: 'ppp7' und 'post12' sind KEINE Beitraege", () => {
        // Ohne diese Probe waere TB05/TB06 auch mit einem Muster gruen, das
        // jede Kennung mit 'p' und Ziffern annimmt — und dann waere jedes
        // beliebige Element im Forum ein Beitrag.
        const dom = toolbarDOM(
            '<div id="ppp7"><div id="post12">' +
            '<p id="ziel">Weder das eine noch das andere.</p></div></div>');
        waehle(dom, "#ziel");
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        expect(fn(startknoten(dom))).toBeNull();
    });
});
