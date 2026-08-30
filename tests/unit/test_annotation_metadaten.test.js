// ===========================================================================
// Build 735 — die Metadaten einer Annotation: post_id, Zeitstempel, Betreff
// ===========================================================================
//
// WAS HIER GEPRUEFT WIRD UND WARUM ES ZWEI GRUPPEN SIND
//
// Build 727 hatte gruene Tests und wirkte im Betrieb NIE. Die Ursache war
// nicht der Code der geprueften Funktion, sondern ihr Aufrufweg: '_onMouseUp'
// loeschte die Auswahl, BEVOR die Funktion sie las. TB01-TB09 riefen die
// Funktion direkt mit gesetzter Auswahl auf — sie pruefen das STUECK. Ein
// gruener Test ueber eine Funktion, die im Betrieb nie unter diesen
// Bedingungen laeuft, ist kein Nachweis.
//
// Deshalb hier ZWEI Gruppen:
//
//   MD01-MD14  die Verfahren EINZELN. Sie sollen einen Fehlschlag EINEM
//              Verfahren zuordnen koennen statt der ganzen Kette.
//   TB10-TB14  DER WEG. Ein echter 'mouseup' auf dem Viewport, durch den
//              ausgelieferten Listener, und geprueft wird, was am Ende in
//              der Annotation steht. Diese Gruppe haette Build 727 gefangen.
//
// DIE AUFBAUTEN SIND ECHT. Sie stammen aus den Auszuegen, die Alex am
// 28.08.2026 uebergeben hat, und aus den Sondenlaeufen vom 29.08.2026
// (claude/Analyse_Sondenmessung_29082026.md). Gekuerzt und ohne Inhalte, in
// der Schachtelung unveraendert. Wo etwas NACHGESTELLT ist, steht es dabei.
//
// Beleg: claude/Analyse_Sondenmessung_29082026.md; toolbar/toolbar.js
//        (PostMetaModule, MarkerToolModule).

import { describe, it, expect } from "vitest";
import { JSDOM } from "jsdom";
import { readFileSync as _lese } from "fs";

// ---------------------------------------------------------------------------
// Aufbauten
// ---------------------------------------------------------------------------

/**
 * THEMENSEITE (viewtopic) — zwei Beitraege.
 *
 * Merkmale, auf die es ankommt:
 *   - der Beitragskopf traegt BEIDE Kennungen (p<n> aussen, pp<n> innen)
 *   - der Dauerlink im Kopf hat als Text die Nummer ('#721598') — genau
 *     daran ist in der Sonde v1 ein Betreffs-Verfahren gescheitert
 *   - der Zeitstempel steht im INNEREN <i> (Verfahren T1)
 *   - der Seitenkopf-<h2> traegt den Themenbetreff MIT angehaengter Nummer;
 *     die Messung ergab dort 'Titel #99999' (Verfahren S4 gegen S6)
 *   - der <h3> des EROEFFNUNGSbeitrags trug in der Messung denselben
 *     Fingerabdruck wie der Seitenkopf ohne Nummer (S2 == S6)
 */
const SEITE_VIEWTOPIC = `
<div id="brd-main">
  <div class="linkst"><h2><span>Ein Thema über Bonn #721598</span></h2></div>

  <article class="post" id="p721598">
    <div class="blockpost">
      <h2><span>
        <a href="viewtopic.php?pid=721598#p721598">#721598</a>
        <i><i title="3 years ago">Fri., 16.12.2022 19:08:03</i></i>
      </span></h2>
      <div class="box" id="pp721598"><div class="inbox"><div class="postbody">
        <div class="postleft"><dl><dd><span>Posts: 114</span></dd></dl></div>
        <div class="postright">
          <h3>Ein Thema über Bonn</h3>
          <div class="postmsg"><p id="ziel1">Der Zug fährt ab Hauptbahnhof.</p></div>
        </div>
      </div></div></div>
    </div>
  </article>

  <article class="post" id="p721603">
    <div class="blockpost">
      <h2><span>
        <a href="viewtopic.php?pid=721603#p721603">#721603</a>
        <i><i title="3 years ago">Sat., 17.12.2022 08:14:00</i></i>
      </span></h2>
      <div class="box" id="pp721603"><div class="inbox"><div class="postbody">
        <div class="postright">
          <h3>Re: Ein Thema über Bonn</h3>
          <div class="postmsg"><p id="ziel2">Ich komme mit dem Rad.</p></div>
        </div>
      </div></div></div>
    </div>
  </article>
</div>`;

/**
 * PRIVATE NACHRICHT (pmsnew) — ein Beitrag.
 *
 * ECHT (Auszug Alex 28.08.2026): der aeussere <div id="p120862"
 * class="blockpost">, der Kopf mit '#2' und dem Datum IM LINK (T2), und die
 * '.box' OHNE Kennung. Der Titel der Unterhaltung steht AUSSERHALB des
 * Beitrags unter 'div.block2col > div.block > h2' (Verfahren S3).
 *
 * NACHGESTELLT sind die beiden <h2> davor. Die Messung vom 29.08.2026 ergab
 * auf der echten PN-Seite: S4 (erster <h2> ausserhalb eines Beitrags) war
 * LEER, S6 lieferte 7 Zeichen, S3 lieferte 4 — drei Verfahren, drei Werte.
 * WELCHES Element S6 dort getroffen hat, ist NICHT erhoben; die Sonde gibt
 * nur Laenge und Fingerabdruck aus. Dieser Aufbau bildet deshalb nicht die
 * Seite nach, sondern die EIGENSCHAFT, auf die es ankommt: dass S6 auf einer
 * PN-Seite einen anderen Wert liefert als S3 und deshalb kein Rueckfall
 * sein darf.
 */
const SEITE_PMSNEW = `
<div id="brd-main">
  <div class="linkst"><h2></h2></div>
  <div class="inbox"><h2>Postfach</h2></div>

  <div class="block2col"><div class="block">
    <h2 style="color:#115098;">Bonn</h2>
  </div></div>

  <div id="p120862" class="blockpost roweven contains_traces">
    <h2><span><span class="conr">#2</span>
      <a href="pmsnew.php?mdl=topic&amp;pid=120862#p120862">Mon., 26.04.2021 20:36:03</a>
    </span></h2>
    <div class="box"><div class="inbox"><div class="postbody">
      <div class="postleft"><dl><dt><strong>INHABER</strong></dt></dl></div>
      <div class="postright"><div class="postmsg">
        <p id="ziel1">Ich bin ab Freitag in Köln.</p>
      </div></div>
    </div></div></div>
  </div>
</div>`;

// ---------------------------------------------------------------------------
// Messrahmen
// ---------------------------------------------------------------------------

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

/** Setzt die Auswahl auf den Inhalt von 'selektor' und gibt den Startknoten. */
function markiere(dom, selektor) {
    const el = dom.window.document.querySelector(selektor);
    const range = dom.window.document.createRange();
    range.selectNodeContents(el);
    const s = dom.window.getSelection();
    s.removeAllRanges();
    s.addRange(range);
    return range.startContainer;
}

function meta(dom) {
    return dom.window.ForensicToolbar.config.postMetaHelpers;
}

// ===========================================================================
// Gruppe 1 — die Verfahren einzeln
// ===========================================================================
describe("PostMetaModule — die Verfahren einzeln (Build 735)", () => {

    // -- Ansicht -------------------------------------------------------------

    it("MD01 - die Ansicht wird an der Adresse erkannt", () => {
        const m = meta(toolbarDOM(SEITE_VIEWTOPIC));
        // Weisung Alex 28.08.2026: "Die URL bei privaten Nachrichten beginnt
        // immer mit '/forum/pmsnew.php'."
        expect(m.ansichtAus("/forum/pmsnew.php?mdl=topic&tid=91")).toBe("pmsnew");
        expect(m.ansichtAus("/forum/viewtopic.php?pid=721598")).toBe("viewtopic");
        // GEGENPROBE: ohne Adresse wird NICHT 'pmsnew' geraten. Ein falsches
        // 'pmsnew' haette zur Folge, dass der Beitragsbetreff gar nicht erst
        // gesucht wird.
        expect(m.ansichtAus("")).toBe("viewtopic");
        expect(m.ansichtAus(null)).toBe("viewtopic");
    });

    // -- Zeit zerlegen -------------------------------------------------------

    it("MD02 - Zeittexte werden zerlegt, mit und ohne Sekunden", () => {
        const m = meta(toolbarDOM(SEITE_VIEWTOPIC));
        const a = m.zerlegeZeit("Fri., 16.12.2022 19:08:03");
        expect(a.isoOhneZone).toBe("2022-12-16T19:08:03");
        expect(a.jahr).toBe(2022);
        expect(a.sekunde).toBe(3);
        // Nicht jede Forenvorlage rendert Sekunden.
        const b = m.zerlegeZeit("Mon., 26.04.2021 20:36");
        expect(b.isoOhneZone).toBe("2021-04-26T20:36:00");
    });

    it("MD03 - GEGENPROBE: ohne Datum kommt null, nicht ein leeres Geruest", () => {
        // Ein Verfahren, das immer ein Objekt zurueckgibt, kann nicht
        // scheitern — und dann ist die Trefferquote wertlos. Genau dieser
        // Fehler steckte in der Sonde v1 (T4 zaehlte als Treffer).
        const m = meta(toolbarDOM(SEITE_VIEWTOPIC));
        expect(m.zerlegeZeit("3 years ago")).toBeNull();
        expect(m.zerlegeZeit("Original Poster")).toBeNull();
        expect(m.zerlegeZeit("")).toBeNull();
        expect(m.zerlegeZeit(null)).toBeNull();
    });

    it("MD04 - 'roh' traegt NUR das Datum, nicht seine Quelle", () => {
        // BEFUND ALEX 29.08.2026: die Sonde v2 gab in 'roh' die ganze
        // Zeichenkette zurueck, aus der das Datum stammt. Bei einem Verfahren
        // ueber den Kopftext ist das der KOMPLETTE Kopf — mit dem
        // Benutzernamen des Verfassers. In Alex' Ausgabe stand deshalb ein
        // Klarname. Dieser Testfall haelt fest, dass es hier nicht noch
        // einmal passiert.
        const m = meta(toolbarDOM(SEITE_VIEWTOPIC));
        const z = m.zerlegeZeit("FluchOfTheCoffee schrieb am 16.12.2022 19:08:03 Uhr");
        expect(z.roh).toBe("16.12.2022 19:08:03");
        expect(z.roh).not.toContain("FluchOfTheCoffee");
        expect(JSON.stringify(z)).not.toContain("FluchOfTheCoffee");
    });

    // -- Behaelter -----------------------------------------------------------

    it("MD05 - beitragBehaelter nimmt den AEUSSERSTEN, nicht die '.box'", () => {
        // DER FEHLER, DEN DIE SONDE IN SICH SELBST GEFUNDEN HAT: ein
        // 'closest(...)' trifft in der viewtopic-Ansicht zuerst auf
        // '<div class="box" id="pp721598">'. Der <h2> mit Datum und Betreff
        // steht dort NICHT darin — er ist dessen GESCHWISTER. Zeit und
        // Betreff kamen als null zurueck, obwohl beide auf der Seite standen.
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const knoten = markiere(dom, "#ziel1");
        const b = meta(dom).beitragBehaelter(knoten);
        expect(b.id).toBe("p721598");
        expect(b.tagName.toLowerCase()).toBe("article");
        // Und der Kopf ist von dort aus erreichbar — das ist der Sinn.
        expect(b.querySelector("h2")).not.toBeNull();
    });

    // -- Zeitkette -----------------------------------------------------------

    it("MD06 - viewtopic: der Zeitstempel kommt ueber T1", () => {
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const b = meta(dom).beitragBehaelter(markiere(dom, "#ziel1"));
        const z = meta(dom).zeitVon(b);
        expect(z.weg).toBe("T1");
        expect(z.zeit.isoOhneZone).toBe("2022-12-16T19:08:03");
    });

    it("MD07 - pmsnew: derselbe Aufruf kommt ueber T2", () => {
        // T1 und T2 schliessen einander aus (Messung: 4/4 zu 0/6 und
        // umgekehrt). Genau deshalb genuegt die Kette und braucht KEINE
        // Ansichtserkennung — sie kann sich nicht vergreifen.
        const dom = toolbarDOM(SEITE_PMSNEW);
        const b = meta(dom).beitragBehaelter(markiere(dom, "#ziel1"));
        const z = meta(dom).zeitVon(b);
        expect(z.weg).toBe("T2");
        expect(z.zeit.isoOhneZone).toBe("2021-04-26T20:36:03");
    });

    it("MD08 - T3 faengt auf, wenn weder <i> noch Link ein Datum tragen", () => {
        const dom = toolbarDOM(
            '<div id="p9001" class="blockpost">' +
            '<h2>NUTZER — Wed., 01.03.2023 07:00:00</h2>' +
            '<div class="postmsg"><p id="ziel1">Text</p></div></div>');
        const b = meta(dom).beitragBehaelter(markiere(dom, "#ziel1"));
        const z = meta(dom).zeitVon(b);
        expect(z.weg).toBe("T3");
        expect(z.zeit.isoOhneZone).toBe("2023-03-01T07:00:00");
    });

    it("MD09 - GEGENPROBE: das title-Attribut liefert keinen Zeitstempel", () => {
        // Es ist RELATIV ("3 years ago") und aendert sich mit dem
        // Lesezeitpunkt. Eine Tatzeit daraus waere wertlos. Die Messung
        // bestaetigte 0/4 und 0/6.
        const dom = toolbarDOM(
            '<div id="p9002" class="blockpost">' +
            '<h2><i title="4 years ago">vor langer Zeit</i></h2>' +
            '<div class="postmsg"><p id="ziel1">Text</p></div></div>');
        const b = meta(dom).beitragBehaelter(markiere(dom, "#ziel1"));
        expect(meta(dom).zeitVon(b).zeit).toBeNull();
    });

    // -- Betreff -------------------------------------------------------------

    it("MD10 - viewtopic: S6 ohne angehaengte Nummer, S2 mit 'Re:'", () => {
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const m = meta(dom);
        // S6 schneidet die angehaengte Nummer ab. Die Messung ergab fuer das
        // unbereinigte Verfahren 'Titel? #99999'.
        expect(m.betreffS6()).toBe("Ein Thema über Bonn");
        const b1 = m.beitragBehaelter(markiere(dom, "#ziel1"));
        const b2 = m.beitragBehaelter(markiere(dom, "#ziel2"));
        // S2 des EROEFFNUNGSbeitrags == S6. Zwei unabhaengige Wege, ein Wert
        // — in der Messung an zwei verschiedenen Themen bestaetigt
        // (Fingerabdruecke 33fb820c und 076ee3a1).
        expect(m.betreffS2(b1)).toBe(m.betreffS6());
        expect(m.betreffS2(b2)).toBe("Re: Ein Thema über Bonn");
    });

    it("MD11 - GEGENPROBE: auf PN liefert S6 einen ANDEREN Wert als S3", () => {
        // DAS IST DER GRUND, WARUM DER BETREFF AN DER ANSICHT HAENGT UND
        // NICHT AN EINER KETTE. Eine Kette 'S6, sonst S3' haette auf jeder
        // PN-Seite still den falschen Betreff eingetragen — falsch,
        // zuversichtlich und unauffaellig. Ohne diese Probe waere MD12 auch
        // mit einer Kette gruen.
        const dom = toolbarDOM(SEITE_PMSNEW);
        const m = meta(dom);
        expect(m.betreffS3()).toBe("Bonn");
        expect(m.betreffS6()).not.toBe(m.betreffS3());
    });

    // -- post_id -------------------------------------------------------------

    it("MD12 - P1 und P3 bestaetigen einander", () => {
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const m = meta(dom);
        const knoten = markiere(dom, "#ziel2");
        expect(m.postIdP1(knoten)).toBe(721603);
        expect(m.postIdP3(m.beitragBehaelter(knoten))).toBe(721603);
        const md = m.metadatenVon(knoten, "/forum/viewtopic.php?pid=721598");
        expect(md.postId).toBe(721603);
        expect(md.postIdWeg).toBe("P1+P3");
    });

    it("MD13 - GEGENPROBE: widersprechen sich P1 und P3, wird nichts geschrieben", () => {
        // Eine geratene Beitragsnummer ist schlimmer als keine: an ihr
        // haengen im Vollzitat fuenf weitere Angaben (Themenbetreff,
        // Originaldatum, Sprungmarke, PN-Partner, Zusammenfassung). Sie
        // waere plausibel und falsch.
        const dom = toolbarDOM(
            '<article class="post" id="p111"><div class="blockpost"><h2>' +
            '<a href="viewtopic.php?pid=222#p222">#222</a></h2>' +
            '<div class="postmsg"><p id="ziel1">Text</p></div>' +
            '</div></article>');
        const md = meta(dom).metadatenVon(markiere(dom, "#ziel1"),
                                          "/forum/viewtopic.php?id=1");
        expect(md.postId).toBeNull();
        expect(md.postIdGegenprobe).toBe(222);
        expect(md.hinweise.join(" ")).toContain("weichen ab");
    });

    it("MD14 - ohne Beitrag bleibt alles null, und es steht ein Grund dabei", () => {
        // Uebersichts-, Such- und Profilseiten haben keine Beitraege. Ein
        // stilles Ausbleiben waere ein uebersprungener Beleg (Grundregel 1).
        const dom = toolbarDOM('<table><tbody><tr>' +
            '<td id="ziel1">Ein Themenlink</td></tr></tbody></table>');
        const md = meta(dom).metadatenVon(markiere(dom, "#ziel1"),
                                          "/forum/viewforum.php?id=7");
        expect(md.postId).toBeNull();
        expect(md.zeitRoh).toBeNull();
        expect(md.hinweise.length).toBeGreaterThan(0);
        expect(md.hinweise.join(" ")).toContain("keine Beitraege");
    });
});

// ===========================================================================
// Gruppe 2 — DER WEG
// ===========================================================================
//
// HIER LIEGT DER EIGENTLICHE MANGEL VON BUILD 727. Diese Gruppe fuehrt einen
// echten Markierungsvorgang durch den ausgelieferten 'mouseup'-Listener und
// prueft, was am Ende in der Annotation steht — nicht, was eine Hilfsfunktion
// unter Laborbedingungen zurueckgibt.

describe("MarkerToolModule — der WEG durch _onMouseUp (Build 735)", () => {

    /**
     * Ruestet die Toolbar so, wie sie im Betrieb steht, und markiert.
     * Gibt die entstandene Annotation zurueck (oder null).
     */
    function markiereUeberDenWeg(dom, selektor, url) {
        const FT = dom.window.ForensicToolbar;
        // Eine aktive Kategorie ist die Bedingung dafuer, dass eine
        // Markierung ueberhaupt eine Annotation anlegt (Z. 'if (!activeCat)').
        FT._setState({ activeCategory: 1, viewMode: "enhanced", currentUrl: url });
        // Den ausgelieferten Listener anhaengen — genau so, wie es nach dem
        // Laden einer Seite geschieht. NICHT die Funktion direkt aufrufen:
        // das waere wieder eine Pruefung des Stuecks statt des Weges.
        FT.events.emit("page:loaded");

        const el = dom.window.document.querySelector(selektor);
        markiere(dom, selektor);
        el.dispatchEvent(new dom.window.MouseEvent("mouseup", { bubbles: true }));

        const map = FT.state.get("annotations");
        const alle = Array.from(map.values());
        return alle.length ? alle[alle.length - 1] : null;
    }

    it("TB10 - viewtopic: die Markierung traegt die Beitragsnummer", () => {
        // GENAU DAS HAT BUILD 727 NICHT GELIEFERT. Alex' Lauf zeigte: auch
        // die nach dem Einspielen neu entstandene Annotation #31 war ohne
        // post_id — weil '_postElementVon' die Auswahl erneut las, nachdem
        // '_onMouseUp' sie geloescht hatte.
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const ann = markiereUeberDenWeg(dom, "#ziel2",
                                        "/forum/viewtopic.php?pid=721598");
        expect(ann).not.toBeNull();
        expect(ann.postId).toBe(721603);
    });

    it("TB11 - GEGENPROBE: die Markierung ist danach WEG, die Nummer trotzdem da", () => {
        // DAS IST DER NACHWEIS DER REIHENFOLGE, nicht nur des Ergebnisses:
        // Ist die Textmarkierung nach dem Lauf aufgehoben UND die Nummer
        // gesetzt, dann MUSS sie VOR der Aufhebung geholt worden sein. Mit
        // der Reihenfolge aus Build 734 kann dieser Testfall nicht gruen
        // werden.
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const ann = markiereUeberDenWeg(dom, "#ziel1",
                                        "/forum/viewtopic.php?pid=721598");
        const s = dom.window.getSelection();

        // GEMESSEN, NICHT ANGENOMMEN: 'rangeCount' ist danach NICHT 0. Der
        // Lauf loescht die Auswahl zwar ('removeAllRanges'), aber das danach
        // geoeffnete Annotationsfenster setzt den Schreibcursor in sein
        // Textfeld — und das ist eine neue, LEERE Auswahl im <textarea>.
        // Auf 'rangeCount === 0' zu pruefen waere deshalb falsch gewesen und
        // haette diesen Testfall an einem Nebenumstand scheitern lassen
        // statt an der Sache.
        expect(s.toString()).toBe("");
        expect(s.isCollapsed).toBe(true);
        expect(ann.postId).toBe(721598);

        // Und der Weg von Build 734 unmittelbar nachgestellt: wer die
        // Nummer AN DIESER STELLE aus der Auswahl holen will — so wie es
        // '_postElementVon' bis Build 734 tat — bekommt null. Der Cursor
        // steht im Textfeld des Fensters, nicht mehr im Beitrag.
        const fn = dom.window.ForensicToolbar.config.markerHelpers.postElementVon;
        expect(fn(s.rangeCount ? s.getRangeAt(0).startContainer : null)).toBeNull();
        expect(fn(null)).toBeNull();
    });

    it("TB12 - viewtopic: Zeitstempel und beide Betreffe stehen im JSON", () => {
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const ann = markiereUeberDenWeg(dom, "#ziel2",
                                        "/forum/viewtopic.php?pid=721598");
        const m = ann.selection.meta;
        expect(m.ansicht).toBe("viewtopic");
        expect(m.zeitIsoOhneZone).toBe("2022-12-17T08:14:00");
        expect(m.zeitWeg).toBe("T1");
        expect(m.zeitTeile.jahr).toBe(2022);
        // Beide Betreffe: der Bericht schreibt 'Beitrag zum Thema »…«' und
        // braucht dafuer den THEMENbetreff; die Fundstelle selbst traegt
        // 'Re: …'. Beide zu erheben kostet nichts und laesst die Wahl der
        // Darstellung offen.
        expect(m.themenbetreff).toBe("Ein Thema über Bonn");
        expect(m.themenbetreffWeg).toBe("S6");
        expect(m.betreff).toBe("Re: Ein Thema über Bonn");
        expect(m.betreffWeg).toBe("S2");
        // KEINE Zonenangabe im Namen und keine im Wert — die Zone des Forums
        // ist nicht erhoben, und eine Tatzeit mit falscher Zone ist um
        // Stunden falsch.
        expect(m.zeitIsoOhneZone).not.toMatch(/Z$|[+-]\d\d:\d\d$/);
    });

    it("TB13 - pmsnew: S3 traegt den Titel, ein Beitragsbetreff entsteht NICHT", () => {
        // Der wichtigste Befund der Messung, hier als Testfall: auf einer
        // PN-Seite darf S6 nicht greifen. Waere hier eine Kette am Werk,
        // stuende in 'themenbetreff' der Wert von S6 — und der ist falsch.
        const dom = toolbarDOM(SEITE_PMSNEW);
        const ann = markiereUeberDenWeg(dom, "#ziel1",
                                        "/forum/pmsnew.php?mdl=topic&tid=91");
        const m = ann.selection.meta;
        expect(ann.postId).toBe(120862);
        expect(m.ansicht).toBe("pmsnew");
        expect(m.themenbetreff).toBe("Bonn");
        expect(m.themenbetreffWeg).toBe("S3");
        expect(m.betreff).toBeNull();
        expect(m.zeitWeg).toBe("T2");
    });

    it("TB15 - reduzierte Ansicht: NUR 'pp<n>' - der breitere Weg faengt es auf", () => {
        // ZWEI WEGE, UND SIE SIND NICHT DECKUNGSGLEICH. PostMetaModule
        // (P1+P3) ist der belegstaerkere, nimmt aber nur die AEUSSERE
        // Kennung. In der reduzierten Ansicht fuer Nicht-Vollmitglieder
        // (Build 396) und in gallery.php gibt es nur die INNERE — dort
        // liefert P1 nichts.
        //
        // Ohne diesen Testfall waere ein Bruch in '_postElementVon' nicht
        // mehr zu bemerken: TB10 bekaeme seine Nummer weiterhin ueber P1.
        // Er ist die einzige Stelle, an der der Rueckfall allein traegt.
        const dom = toolbarDOM(
            '<div class="box" id="pp5150"><div class="postmsg">' +
            '<p id="ziel1">Kein article darum herum.</p></div></div>');
        const ann = markiereUeberDenWeg(dom, "#ziel1",
                                        "/forum/viewtopic.php?id=1");
        expect(ann.postId).toBe(5150);
        expect(ann.selection.meta.postId).toBeNull();          // P1 hat nichts
        expect(ann.selection.meta.postIdSpalte)
            .toContain("Build728");                            // und wer half
    });

    it("TB16 - GEGENPROBE: bei Widerspruch kommt AUCH ueber den Rueckfall nichts", () => {
        // Widersprechen sich P1 und P3, ist die Nummer strittig. Dann darf
        // sie auch nicht ueber den breiteren Weg doch noch in die Akte
        // gelangen — sonst waere die Sperre aus MD13 im Betrieb wirkungslos,
        // und genau solche Luecken zwischen Stueck und Weg sind der Grund
        // fuer diese Testgruppe.
        const dom = toolbarDOM(
            '<article class="post" id="p111"><div class="blockpost"><h2>' +
            '<a href="viewtopic.php?pid=222#p222">#222</a></h2>' +
            '<div class="box" id="pp111"><div class="postmsg">' +
            '<p id="ziel1">Text</p></div></div>' +
            '</div></article>');
        const ann = markiereUeberDenWeg(dom, "#ziel1",
                                        "/forum/viewtopic.php?id=1");
        expect(ann.postId).toBeNull();
        expect(ann.selection.meta.postIdSpalte).toContain("strittig");
    });

    it("TB14 - GEGENPROBE: ohne aktive Kategorie entsteht keine Annotation", () => {
        // Ein Test, der nicht anschlagen kann, ist kein Test: waere der
        // Listener unabhaengig von der Kategorie, legte jedes Markieren im
        // Ermittlungsfenster ungewollt Belege an.
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const FT = dom.window.ForensicToolbar;
        FT._setState({ activeCategory: null, viewMode: "enhanced",
                       currentUrl: "/forum/viewtopic.php?pid=721598" });
        FT.events.emit("page:loaded");
        const el = dom.window.document.querySelector("#ziel1");
        markiere(dom, "#ziel1");
        el.dispatchEvent(new dom.window.MouseEvent("mouseup", { bubbles: true }));
        expect(FT.state.get("annotations").size).toBe(0);
        // Und die Auswahl bleibt stehen — es wurde nichts angefasst.
        expect(dom.window.getSelection().rangeCount).toBe(1);
    });
});
