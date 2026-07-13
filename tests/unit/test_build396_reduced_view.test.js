/**
 * test_build396_reduced_view.test.js
 * Unit-Tests: Verankerung der reduzierten Nicht-Vollmitglieder-Ansicht (Build 396)
 * Baustelle 3 · Beleg: Projektgespraech 2026-07-13
 *
 * Hintergrund:
 *   Forennutzern ohne Vollmitgliedschaft liefert das Forum eine reduzierte
 *   Ansicht. Der einzelne Post ist dann <div class="box type0" id="p<id>"> mit
 *   einem ANONYMEN inneren <article> (weder Klasse noch id). Dadurch griffen
 *   zwei Client-Features nicht:
 *     A) PostMarkerModule: POST_SELECTOR "article.post[id^='p']" traf den
 *        reduzierten Post nicht -> nicht markierbar -> kein Minimap-Marker.
 *     B) TranslationModule: der Flaggen-Anker ".postfootright ul" existiert im
 *        reduzierten Post nicht -> keine Uebersetzungs-Flagge.
 *
 * Getestet wird gegen den ECHTEN Code: toolbar.js wird im JSDOM ausgewertet,
 * die pure Logik ist ueber ForensicToolbar.config.postMarkerHelpers bzw.
 * .translationHelpers freigelegt (Muster wie test_translation_module.test.js).
 * Kein Stub -> kein "green but dead".
 *
 * GEGENPROBE (siehe unten): dieselben reduzierten Fixtures werden zusaetzlich
 * gegen die ALTEN (engen) Selektoren geprueft. Diese Assertions belegen, dass
 * die reduzierte Struktur unter Build <=394 tatsaechlich durchgefallen waere —
 * die Tests sind also an den neuen Code gebunden.
 *
 * Version: 0.7.396 · Build: 396 · 2026-07-13
 */

import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

let PM;   // PostMarkerModule-Helfer
let TR;   // TranslationModule-Helfer

beforeAll(() => {
  const src = readFileSync("toolbar/toolbar.js", "utf-8");
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => ({}) });
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.eval(src);
  PM = dom.window.ForensicToolbar.config.postMarkerHelpers;
  TR = dom.window.ForensicToolbar.config.translationHelpers;
});

// ---------------------------------------------------------------------------
// Fixtures — reduzierte und volle Struktur (aus dem gelieferten Original-HTML).
// ---------------------------------------------------------------------------
function frag(html) {
  return new JSDOM("<!DOCTYPE html><body>" + html + "</body>").window.document;
}

// Reduzierter Post: id am aeusseren <div class="box">, anonymes <article>.
const REDUCED_POST = `
<div class="box type0 " id="p1882874">
  <article>
    <a href=""></a>
    <div class="row">
      <div class="topic-body clearfix">
        <div class="topic-meta-data">
          <div class="names trigger-user-card ">
            <span class="first username"><a href="/forum/user.php?id=780592">forum_username</a></span>
            <span class="user-title">Senior Member</span>
          </div>
          <div class="post-infos ">
            <div class="rate-buttons"><span><ul class="post-buttons">
              <li><a href="/forum/beginner/clap.php?tid=189275&amp;pid=1882874" class="button icon-button clap"><span>Clap</span></a></li>
            </ul></span></div>
          </div>
        </div>
        <div class="regular contents"><div class="cooked"><p>The text of the post is here.</p></div>
        <section class="post-actions"><ul><li class="postquote"><span><a href="/forum/post.php?tid=189275&amp;qid=1882874">Antworten</a></span></li></ul></section>
      </div>
    </div>
  </article>
</div>`;

// Vollansicht-Post: id am <article class="post">, mit .postfoot/.postfootright.
const FULL_POST = `
<article class="post" id="p9001">
  <div class="postmsg"><p>Voller Beitrag</p></div>
  <div class="postfoot"><div class="postfootright"><ul>
    <li class="postreport"><span><a href="misc.php?report=9001">Melden</a></span></li>
  </ul></div></div>
</article>`;

// ===========================================================================
// Fix A — PostMarkerModule.postElFromTarget
// ===========================================================================
describe("Build 396 · PostMarkerModule.postElFromTarget", () => {
  it("reduzierter Post: Klick in .cooked -> aeusserer div.box#p<id>", () => {
    const d = frag(REDUCED_POST);
    const target = d.querySelector(".cooked p");
    const postEl = PM.postElFromTarget(target);
    expect(postEl).not.toBe(null);
    expect(postEl.id).toBe("p1882874");
    // Die id haengt am aeusseren div.box (nicht am anonymen <article>).
    expect(postEl.classList.contains("box")).toBe(true);
    expect(postEl.tagName.toLowerCase()).toBe("div");
  });

  it("Vollansicht-Post: Klick in .postmsg -> article.post#p<id> (unveraendert)", () => {
    const d = frag(FULL_POST);
    const target = d.querySelector(".postmsg p");
    const postEl = PM.postElFromTarget(target);
    expect(postEl).not.toBe(null);
    expect(postEl.id).toBe("p9001");
    expect(postEl.tagName.toLowerCase()).toBe("article");
  });

  it("Numerik-Guard: div.box mit nicht-numerischer id wird NICHT als Post erkannt", () => {
    const d = frag(`<div class="box" id="preview"><span class="cooked">x</span></div>`);
    const target = d.querySelector(".cooked");
    expect(PM.postElFromTarget(target)).toBe(null);
  });

  it("Klick ausserhalb jeglichen Post-Containers -> null", () => {
    const d = frag(`<div class="sidebar"><span>irrelevant</span></div>`);
    expect(PM.postElFromTarget(d.querySelector("span"))).toBe(null);
  });

  it("null/kein closest -> null (defensiv)", () => {
    expect(PM.postElFromTarget(null)).toBe(null);
    expect(PM.postElFromTarget({})).toBe(null);
  });

  // GEGENPROBE: der reduzierte Post scheitert am ALTEN engen Selektor.
  it("Gegenprobe: reduzierter Post matcht NICHT den alten article.post-Selektor", () => {
    const d = frag(REDUCED_POST);
    const target = d.querySelector(".cooked p");
    expect(target.closest("article.post[id^='p']")).toBe(null);
  });
});

// ===========================================================================
// Fix B — TranslationModule.resolveFlagAnchor
// ===========================================================================
describe("Build 396 · TranslationModule.resolveFlagAnchor", () => {
  it("Vollansicht: .postfootright ul hat Prioritaet (unveraendert)", () => {
    const d = frag(FULL_POST);
    const container = d.getElementById("p9001");
    const anchor = TR.resolveFlagAnchor(container);
    expect(anchor).not.toBe(null);
    expect(anchor.closest(".postfootright")).not.toBe(null);
  });

  it("reduzierter Post: faellt auf .post-actions ul zurueck", () => {
    const d = frag(REDUCED_POST);
    const container = d.getElementById("p1882874");
    const anchor = TR.resolveFlagAnchor(container);
    expect(anchor).not.toBe(null);
    expect(anchor.closest(".post-actions")).not.toBe(null);
  });

  it("reduzierter Post ohne .post-actions: nutzt .rate-buttons ul.post-buttons", () => {
    // .post-actions entfernt -> naechster Anker in der Prioritaet.
    const d = frag(REDUCED_POST);
    const container = d.getElementById("p1882874");
    container.querySelector(".post-actions").remove();
    const anchor = TR.resolveFlagAnchor(container);
    expect(anchor).not.toBe(null);
    expect(anchor.classList.contains("post-buttons")).toBe(true);
  });

  it("Prioritaet: bei vorhandenem .postfootright wird NICHT .post-actions gewaehlt", () => {
    // Mischcontainer mit beidem -> .postfootright ul muss gewinnen.
    const d = frag(`<div id="pX">
      <section class="post-actions"><ul id="pa"></ul></section>
      <div class="postfoot"><div class="postfootright"><ul id="pf"></ul></div></div>
    </div>`);
    const anchor = TR.resolveFlagAnchor(d.getElementById("pX"));
    expect(anchor.id).toBe("pf");
  });

  it("kein Anker vorhanden -> null (Button wird nicht injiziert)", () => {
    const d = frag(`<div id="pE"><div class="cooked">nur Text</div></div>`);
    expect(TR.resolveFlagAnchor(d.getElementById("pE"))).toBe(null);
  });

  // GEGENPROBE: der reduzierte Post besitzt keinen ".postfootright ul".
  it("Gegenprobe: reduzierter Post hat keinen alten .postfootright-ul-Anker", () => {
    const d = frag(REDUCED_POST);
    const container = d.getElementById("p1882874");
    expect(container.querySelector(".postfootright ul")).toBe(null);
    // ...aber sehr wohl die neuen Anker:
    expect(container.querySelector(".post-actions ul")).not.toBe(null);
  });
});
