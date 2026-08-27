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
