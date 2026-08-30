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
  <h2 class="topic-title" id="_vt_mfywoc">
    <span><a href="viewtopic.php?id=31351" id="_vt_x30jty">Ein Thema über Bonn</a></span>
    <span style="float:right;font-size: smaller;color:grey">#721598</span>
  </h2>

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
 * THEMENSEITE MIT MODERATIONSRECHTEN (viewtopic).
 *
 * ECHT — Auszug Alex vom 30.08.2026, gekuerzt, Schachtelung unveraendert.
 * Zwei Dinge kommen hier hinzu, die es auf den am 29.08. gemessenen Seiten
 * nicht gab:
 *
 *   1. In der Titelzeile steht ein zweiter Link in eckigen Klammern
 *      ('[ Moderate ]'). Wer den Betreff aus dem TEXT der Zeile nimmt,
 *      bekommt ihn mitgeliefert.
 *   2. Darunter steht der Moderationshinweis, und darin erscheint
 *      '<b>OP</b>' — aber NUR, wenn die Person das Thema eroeffnet hat.
 *
 * Die Kennungen '_vt_...' und die Nummer im OP-Link stehen so im Auszug.
 * Dass der OP-Link auf eine ANDERE id zeigt als das Thema, ist uebernommen
 * und nicht gedeutet — wofuer diese zweite Nummer steht, ist nicht erhoben.
 */
const SEITE_VIEWTOPIC_MOD = `
<div id="page-body" role="main">
  <h2 class="topic-title" id="_vt_mfywoc">
    <span><a href="viewtopic.php?id=31351" id="_vt_x30jty">TITLE OF THE TOPIC</a></span>
    <span> [ <a href="viewtopic.php?id=31351" style="color:red" id="_vt_ysls96">Moderate</a> ]</span>
    <span style="float:right;font-size: smaller;color:grey">#31351</span>
  </h2>
  <div style="background:lightyellow;border-left:2px solid orange;padding:0 5px">
    <small><i>You have moderation permisions in this thread.
      (<a href="viewtopic.php?id=30200" id="_vt_rwi6no"><b>OP</b></a>)</i></small>
  </div>

  <article class="post" id="p800100">
    <div class="blockpost">
      <h2><span>
        <a href="viewtopic.php?pid=800100#p800100">#800100</a>
        <i><i title="2 years ago">Tue., 03.01.2023 11:05:00</i></i>
      </span></h2>
      <div class="box" id="pp800100"><div class="inbox"><div class="postbody">
        <div class="postright">
          <h3>TITLE OF THE TOPIC</h3>
          <div class="postmsg"><p id="ziel1">Erster Beitrag im Thema.</p></div>
        </div>
      </div></div></div>
    </div>
  </article>
</div>`;

/**
 * THEMENSEITE, AUF DER DAS KONTO MODERIEREN DARF, ABER NICHT EROEFFNER IST.
 *
 * ECHT - Auszug Alex vom 30.08.2026, Thema 168221, gekuerzt, Schachtelung
 * unveraendert. Er BERICHTIGT das Modell aus Build 736 in drei Punkten:
 *
 *   1. Die Titelzeile traegt KEINEN Moderationslink, und es gibt KEINEN
 *      Hinweiskasten - obwohl das angemeldete Konto sehr wohl moderieren
 *      darf. Der Link war also nie der Anzeiger fuer Moderationsrechte.
 *   2. Die Rechte zeigen sich AM BEITRAG: ein Aufklappmenue mit Verweisen
 *      auf 'moderate.php' im Fuss.
 *   3. Das OP-Kennzeichen steht IM KOPF DES BEITRAGS und sagt etwas ueber
 *      dessen VERFASSER - hier ueber einen anderen Nutzer als das
 *      angemeldete Konto.
 *
 * Der Seitenkopf mit '#username_logged_in' ist aus Alex' erstem Auszug
 * derselben Nachricht uebernommen. Die Namen sind Platzhalter; die Nummern
 * stehen so im Auszug.
 */
const SEITE_VIEWTOPIC_OP_FREMD = `
<div id="brd-main">
  <div id="page-header">
    <ul><li id="username_logged_in" class="rightside" data-skip-responsive="true">
      <div class="header-profile dropdown-container">
        <a href="/forum/profile.php" class="header-avatar dropdown-trigger"><span class="username">Ermittler</span></a>
        <div class="dropdown hidden"><ul class="dropdown-contents" role="menu">
          <li><a href="/forum/profile.php" title="Profile" role="menuitem">Profile</a></li>
          <li><a href="/forum/login/logout.php?action=out&amp;id=155955&amp;csrf_hash=74894d72" title="Logout" role="menuitem">Exit</a></li>
        </ul></div>
      </div>
    </li></ul>
  </div>

  <div id="page-body" role="main">
    <h2 class="topic-title" id="_vt_b5ekop">
      <span><a href="viewtopic.php?id=168221" id="_vt_asw7n3">I paid didn't get in?</a></span>
      <span style="float:right;font-size: smaller;color:grey">#168221</span>
    </h2>

    <article class="post" style="" id="p1690431">
      <div class="blockpost firstpost blockpost1">
        <h2 id="_vt_jwhurd">
          <strong style="margin-left:15px"><a class="op" href="?id=30200" title="Original Poster">OP</a><a href="user.php?id=3837243">Username_Of_The_Thread_Starter</a></strong>
          <span><ul class="post-buttons"><li><a href="/forum/misc.php?report=1690431" title="Report a problem" class="button icon-button report-icon"><span>Report a problem</span></a></li></ul></span>
          <span>
            <a href="/forum/viewtopic.php?pid=1690431#p1690431" id="_vt_g80tf4">I paid didn't get in?</a>
            <i><i title="2 years ago">Tue., 05.12.2023 13:04:34</i></i><i style="float:right;color:#bbb;">#1690431</i>
          </span>
        </h2>
        <div class="box" id="pp1690431"><div class="inbox"><div class="postbody">
          <div class="postleft"><dl><dd><span>Beiträge: 10</span></dd></dl></div>
          <div class="postright">
            <h3>I paid didn't get in?</h3>
            <div class="postmsg"><p id="ziel1">TEXT OF THE POST</p></div>
          </div>
        </div></div>
        <div class="inbox"><div class="postfoot"><div class="postfootright"><ul>
          <span><div class="dropup"><button class="dropbtn1" style="color:red">Moderate</button>
            <div class="dropup-content"><ul>
              <li><a href="moderate.php?action=punish&amp;fid=368&amp;id=168221&amp;pid=1690431&amp;hash=3b150ec0">Punish</a></li>
              <li><a href="moderate.php?pid=1690431&amp;fid=368&amp;action=blockThumb">BlockThumb</a></li>
            </ul></div>
          </div></span>
        </ul></div></div></div>
        </div>
      </div>
    </article>
  </div>
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

    it("MD10 - viewtopic: S6 nimmt den Titellink, S2 den Beitragsbetreff", () => {
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const m = meta(dom);
        // Build 736: S6 holt den Titel STRUKTURELL — der erste taugliche
        // Link der Zeile. Die Nummernanzeige '#721598' ist ein eigener
        // <span> und kommt gar nicht erst in Betracht.
        expect(m.betreffS6().text).toBe("Ein Thema über Bonn");
        expect(m.betreffS6().weg).toBe("S6a");
        const b1 = m.beitragBehaelter(markiere(dom, "#ziel1"));
        const b2 = m.beitragBehaelter(markiere(dom, "#ziel2"));
        // S2 des EROEFFNUNGSbeitrags == S6. Zwei unabhaengige Wege, ein Wert
        // — in der Messung an zwei verschiedenen Themen bestaetigt
        // (Fingerabdruecke 33fb820c und 076ee3a1).
        expect(m.betreffS2(b1)).toBe(m.betreffS6().text);
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
        // Auf den TEXT vergleichen, nicht auf das Objekt: ein Objekt ist nie
        // gleich einer Zeichenkette, und die Probe waere immer gruen — also
        // wertlos.
        expect(m.betreffS6().text).not.toBe(m.betreffS3());
    });

    // -- Build 736: Moderationslink und Eroeffnerkennzeichen -----------------

    it("MD15 - der Moderationslink wird sprachunabhaengig erkannt", () => {
        // KEIN VERFAHREN UEBER DAS WORT 'Moderate'. Das Forum ist
        // mehrsprachig; der Linktext kann uebersetzt sein. Erkannt wird an
        // der eckigen Klammer der umgebenden <span> ODER an 'color:red'.
        const dom = toolbarDOM(SEITE_VIEWTOPIC_MOD);
        const m = meta(dom);
        const d = dom.window.document;
        const titel = d.querySelector("#_vt_x30jty");
        const mod = d.querySelector("#_vt_ysls96");
        expect(m.istModerationsLink(mod)).toBe(true);
        // GEGENPROBE: der TITELLINK darf nicht als Moderationslink gelten —
        // sonst faellt genau die Angabe weg, um die es geht.
        expect(m.istModerationsLink(titel)).toBe(false);
        // Und jedes der beiden Merkmale traegt fuer sich: ein uebersetzter
        // Linktext ohne Farbangabe wird an der Klammer erkannt.
        const dom2 = toolbarDOM(
            '<h2><span><a href="viewtopic.php?id=9">Der Titel</a></span>' +
            '<span> [ <a href="viewtopic.php?id=9" id="mod2">Moderieren</a> ]</span></h2>');
        expect(meta(dom2).istModerationsLink(
            dom2.window.document.querySelector("#mod2"))).toBe(true);
    });

    it("MD16 - der Betreff traegt den Moderationszusatz NICHT", () => {
        // DAS IST DER FEHLER, DEN ALEX AM 30.08.2026 GEFUNDEN HAT. Bis
        // Build 735 wurde der TEXT der Titelzeile genommen; daraus waere
        // 'TITLE OF THE TOPIC [ Moderate ]' geworden — ein Betreff, der so
        // nirgends steht und in einem Vermerk als Themenbezeichnung
        // erschienen waere.
        const dom = toolbarDOM(SEITE_VIEWTOPIC_MOD);
        const s6 = meta(dom).betreffS6();
        expect(s6.text).toBe("TITLE OF THE TOPIC");
        expect(s6.weg).toBe("S6a");
        expect(s6.text).not.toContain("Moderate");
        expect(s6.text).not.toContain("[");
        expect(s6.text).not.toContain("#31351");
    });

    it("MD17 - ohne Titellink wird der Zeilentext bereinigt (S6b)", () => {
        // Der schwaechere Weg, und er wird als solcher ausgewiesen: er setzt
        // voraus, dass die Zusaetze am ENDE stehen. Beide Reihenfolgen
        // werden abgeschnitten, weil an einem einzigen Auszug nicht zu
        // belegen ist, welche das Forum waehlt.
        const m1 = meta(toolbarDOM(
            '<h2 class="topic-title">Ein Titel ohne Link [ Moderate ] #4711</h2>'));
        expect(m1.betreffS6()).toEqual(
            { text: "Ein Titel ohne Link", weg: "S6b" });
        const m2 = meta(toolbarDOM(
            '<h2 class="topic-title">Ein Titel ohne Link #4711 [ Moderate ]</h2>'));
        expect(m2.betreffS6().text).toBe("Ein Titel ohne Link");
    });

    it("MD18 - das OP-Kennzeichen steht AM BEITRAG, nicht am Konto", () => {
        // BERICHTIGUNG ZU BUILD 736. Dort hatte ich aus EINEM Auszug
        // geschlossen, das Kennzeichen sage etwas ueber den angemeldeten
        // Benutzer. Alex' zweiter Auszug zeigt es an einem FREMDEN Beitrag:
        // es sagt etwas ueber dessen VERFASSER.
        const dom = toolbarDOM(SEITE_VIEWTOPIC_OP_FREMD);
        const m = meta(dom);
        const b = m.beitragBehaelter(markiere(dom, "#ziel1"));
        expect(m.eroeffnerkennzeichenIn(b)).not.toBeNull();
        expect(m.verfasserVon(b)).toEqual(
            { uid: 3837243, name: "Username_Of_The_Thread_Starter" });
        // GEGENPROBE: ein Beitrag OHNE Kennzeichen darf keines bekommen.
        const dom2 = toolbarDOM(SEITE_VIEWTOPIC);
        const m2 = meta(dom2);
        const b2 = m2.beitragBehaelter(markiere(dom2, "#ziel1"));
        expect(m2.eroeffnerkennzeichenIn(b2)).toBeNull();
    });

    it("MD19 - GEGENPROBE: ein 'OP' im Beitragstext zaehlt nicht", () => {
        // Ohne diese Probe waere MD18 auch mit einer Suche gruen, die
        // irgendein 'OP' auf der Seite als Kennzeichen nimmt - und dann
        // machte ein Beitrag, der ueber 'den OP' schreibt, seinen Verfasser
        // zum Themeneroeffner. In einem Vermerk waere das eine erfundene
        // Zuschreibung.
        const dom = toolbarDOM(SEITE_VIEWTOPIC_OP_FREMD.replace(
            '<a class="op" href="?id=30200" title="Original Poster">OP</a>', '')
            .replace('<p id="ziel1">TEXT OF THE POST</p>',
                     '<p id="ziel1">Frag doch mal den <b>OP</b> danach.</p>'));
        const m = meta(dom);
        const b = m.beitragBehaelter(markiere(dom, "#ziel1"));
        expect(m.eroeffnerkennzeichenIn(b)).toBeNull();
        expect(m.themeneroeffner().gefunden).toBe(false);
    });

    it("MD20 - das Scraping-Konto steht im Seitenkopf", () => {
        // WESSEN RECHTE, WESSEN 'DU'? Alles, was die Seite in der zweiten
        // Person sagt, bezieht sich auf DIESES Konto. Ohne die Angabe waere
        // jede solche Zeile im Vermerk zweideutig - und die naheliegende
        // Fehldeutung ist die schlimmste: sie schriebe dem Beschuldigten
        // Rechte zu, die das Ermittlungskonto hatte.
        //
        // Die Benutzernummer steht im Abmeldelink (Weisung Alex 30.08.2026).
        const m = meta(toolbarDOM(SEITE_VIEWTOPIC_OP_FREMD));
        expect(m.angemeldetesKonto()).toEqual(
            { name: "Ermittler", uid: 155955 });
        // GEGENPROBE: ohne den Seitenkopf wird nichts geraten.
        const m2 = meta(toolbarDOM(SEITE_VIEWTOPIC));
        expect(m2.angemeldetesKonto()).toEqual({ name: null, uid: null });
    });

    it("MD21 - Moderationsrechte werden am LINKZIEL erkannt, nicht am Wort", () => {
        // Das Forum ist mehrsprachig (Erkenntnis zum Fall Nr. 2). Ein
        // Verfahren ueber das Wort 'Moderate' verloere die Angabe auf jeder
        // uebersetzten Seite - still, und deshalb unbemerkt.
        const dom = toolbarDOM(SEITE_VIEWTOPIC_OP_FREMD);
        const m = meta(dom);
        const b = m.beitragBehaelter(markiere(dom, "#ziel1"));
        expect(m.moderationAmBeitrag(b)).toBe(true);
        // Und mit uebersetztem Menuetext genauso:
        const dom2 = toolbarDOM(
            SEITE_VIEWTOPIC_OP_FREMD.replace(/>Moderate</g, ">Moderieren<"));
        const m2 = meta(dom2);
        expect(m2.moderationAmBeitrag(
            m2.beitragBehaelter(markiere(dom2, "#ziel1")))).toBe(true);
        // GEGENPROBE: ein Beitrag ohne Moderationsmenue.
        const dom3 = toolbarDOM(SEITE_VIEWTOPIC);
        const m3 = meta(dom3);
        expect(m3.moderationAmBeitrag(
            m3.beitragBehaelter(markiere(dom3, "#ziel1")))).toBe(false);
    });

    it("MD22 - der Themeneroeffner wird seitenweit gefunden", () => {
        const m = meta(toolbarDOM(SEITE_VIEWTOPIC_OP_FREMD));
        expect(m.themeneroeffner()).toEqual(
            { uid: 3837243, name: "Username_Of_The_Thread_Starter",
              gefunden: true });
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
        expect(m.themenbetreffWeg).toBe("S6a");
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

    it("TB17 - Weg: Verfasser, Eroeffnerschaft und Konto landen im JSON", () => {
        // Der Weg durch _onMouseUp auf Alex' Auszug vom 30.08.2026
        // (Thema 168221). Geprueft wird, was in der Annotation LANDET.
        const dom = toolbarDOM(SEITE_VIEWTOPIC_OP_FREMD);
        const ann = markiereUeberDenWeg(dom, "#ziel1",
                                        "/forum/viewtopic.php?id=168221");
        const m = ann.selection.meta;
        expect(m.themenbetreff).toBe("I paid didn't get in?");
        expect(m.themenbetreffWeg).toBe("S6a");
        // DER VERFASSER - die Angabe, um die es in diesem Projekt geht.
        expect(m.autorUid).toBe(3837243);
        expect(m.autorName).toBe("Username_Of_The_Thread_Starter");
        expect(m.autorIstEroeffner).toBe(true);
        expect(m.eroeffnerUid).toBe(3837243);
        // DAS KONTO - und es ist NICHT der Verfasser. Genau diese
        // Unterscheidung hat mir in Build 736 gefehlt.
        expect(m.kontoName).toBe("Ermittler");
        expect(m.kontoUid).toBe(155955);
        expect(m.kontoUid).not.toBe(m.autorUid);
        expect(m.kontoDarfModerieren).toBe(true);
        // Kein Hinweiskasten auf dieser Seite -> UNBEKANNT, nicht 'nein'.
        expect(m.kontoIstEroeffner).toBeNull();
    });

    it("TB18 - GEGENPROBE: ohne OP-Kennzeichen wird nichts zugeschrieben", () => {
        // null heisst UNBEKANNT. Stuende hier 'false', truege jeder Beleg
        // einer gewoehnlichen Seite eine Verneinung, fuer die es keinen
        // Beleg gibt - und ein Vermerk gaebe sie wieder.
        const dom = toolbarDOM(SEITE_VIEWTOPIC);
        const ann = markiereUeberDenWeg(dom, "#ziel1",
                                        "/forum/viewtopic.php?pid=721598");
        const m = ann.selection.meta;
        expect(m.autorIstEroeffner).toBeNull();
        expect(m.eroeffnerUid).toBeNull();
        expect(m.kontoName).toBeNull();
        expect(m.kontoDarfModerieren).toBe(false);
        expect(m.hinweise.join(" ")).toContain("UNBEKANNT");
    });

    it("TB19 - GEGENPROBE: ein zweiter Beitrag ist NICHT der Eroeffner", () => {
        // Ohne diese Probe waere TB17 auch mit einer Fassung gruen, die
        // 'autorIstEroeffner' pauschal auf true setzt, sobald es auf der
        // Seite IRGENDWO ein OP-Kennzeichen gibt. Dann waere jeder
        // Mitschreiber eines Themas dessen Eroeffner.
        const zweiter = SEITE_VIEWTOPIC_OP_FREMD.replace(
            "</article>",
            '</article>'
            + '<article class="post" id="p1690999"><div class="blockpost">'
            + '<h2><strong><a href="user.php?id=9911">Ein_Anderer</a></strong>'
            + '<span><i><i title="2 years ago">Wed., 06.12.2023 09:00:00</i></i>'
            + '</span></h2>'
            + '<div class="box" id="pp1690999"><div class="postright">'
            + '<h3>Re: I paid didn\'t get in?</h3>'
            + '<div class="postmsg"><p id="ziel2">Mir ging es genauso.</p>'
            + '</div></div></div></div></article>');
        const dom = toolbarDOM(zweiter);
        const ann = markiereUeberDenWeg(dom, "#ziel2",
                                        "/forum/viewtopic.php?id=168221");
        const m = ann.selection.meta;
        expect(m.autorUid).toBe(9911);
        expect(m.autorIstEroeffner).toBe(false);
        // Der Eroeffner der SEITE bleibt der erste Beitrag - beides steht
        // nebeneinander und wird nicht verwechselt.
        expect(m.eroeffnerUid).toBe(3837243);
        // Und dieser Beitrag traegt kein Moderationsmenue.
        expect(m.kontoDarfModerieren).toBe(false);
    });

    it("TB20 - der Hinweiskasten sagt etwas ueber das KONTO", () => {
        // Alex' erster Auszug (Thema 31351): Hinweiskasten mit '(OP)'. Er
        // sagt, dass das ANGEMELDETE KONTO das Thema eroeffnet hat - nicht,
        // dass der Verfasser des markierten Beitrags es tat. Die beiden
        // Angaben stehen getrennt nebeneinander.
        const dom = toolbarDOM(SEITE_VIEWTOPIC_MOD);
        const ann = markiereUeberDenWeg(dom, "#ziel1",
                                        "/forum/viewtopic.php?id=31351");
        const m = ann.selection.meta;
        expect(m.kontoIstEroeffner).toBe(true);
        // Der Beitrag dieser Seite traegt KEIN OP-Kennzeichen im Kopf -
        // also bleibt die Aussage ueber den VERFASSER unbekannt.
        expect(m.autorIstEroeffner).toBeNull();
        expect(m.themenbetreff).toBe("TITLE OF THE TOPIC");
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
