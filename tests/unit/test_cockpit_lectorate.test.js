/**
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 * tests/unit/test_cockpit_lectorate.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Lektorat (W4)
 *
 * Testsuite fuer management/server/static/cockpit_lectorate.js (Build 413,
 * Slice 1). Testet den ECHTEN Code (readFileSync + JSDOM,
 * window.AIWCockpitLectorate).
 *
 * LE01 — API verfuegbar.
 * LE02 — statusLabel: deutsche Bezeichnungen (R1).
 * LE03 — filterReports: 'submitted' (Vorgabe), 'alle', leer; mutiert nicht.
 * LE04 — renderUrl: korrekte SF-1-URL (subject_id/report_id).
 * LE05 — reportLabel: Zeilentext.
 * LE06 — renderLectorate: Auswahl-Liste (nur submitted) + <iframe>; Klick setzt
 *        iframe.src auf die Render-URL, markiert aktiv, ruft onSelect.
 * LE07 — Statuswechsel 'alle' rendert mehr Zeilen (reiner Lesewechsel).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_lectorate.js",
  "utf-8"
);

// Build 553: das gemeinsame Tabellen-Werkzeug MUSS im Kontext liegen — genau
// wie im Browser. Ohne es faellt die Sicht in ihren Ersatzpfad, und der Test
// wuerde die Tabelle gar nicht mehr beruehren.
const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_tkSrc);
  dom.window.eval(_src);
  return dom.window;
}
function _api(win) { return (win || _ctx()).AIWCockpitLectorate; }

function _data() {
  return {
    scope: "alle",
    count: 3,
    reports: [
      { subject_id: 18, username: "b18", id: 1, report_type: "interim",
        sequence_nr: 1, title: "Zwischenbericht", status: "submitted" },
      { subject_id: 19, username: "b19", id: 2, report_type: "final",
        sequence_nr: 3, title: "Abschlussbericht", status: "approved" },
      { subject_id: 20, username: "b20", id: 1, report_type: "addendum",
        sequence_nr: 2, title: "Nachtrag", status: "submitted" },
    ],
  };
}

describe("cockpit_lectorate", () => {
  it("LE01 API verfuegbar", () => {
    const api = _api();
    expect(typeof api.renderLectorate).toBe("function");
    expect(typeof api.filterReports).toBe("function");
    expect(typeof api.renderUrl).toBe("function");
    expect(typeof api.cleanup).toBe("function");
  });

  it("LE02 statusLabel deutsch", () => {
    const api = _api();
    expect(api.statusLabel("submitted")).toBe("Zur Abnahme vorgelegt");
    expect(api.statusLabel("approved")).toBe("Freigegeben");
    expect(api.statusLabel("draft")).toBe("Entwurf");
    expect(api.statusLabel("xyz")).toBe("xyz");
  });

  it("LE03 filterReports", () => {
    const api = _api();
    const data = _data();
    expect(api.filterReports(data, "submitted").length).toBe(2);
    expect(api.filterReports(data, "alle").length).toBe(3);
    expect(api.filterReports(data, "approved").length).toBe(1);
    expect(api.filterReports({ reports: [] }, "submitted").length).toBe(0);
    // mutiert die Eingabe nicht:
    expect(data.reports.length).toBe(3);
  });

  it("LE04 renderUrl", () => {
    const api = _api();
    expect(api.renderUrl(18, 1)).toBe(
      "/api/report/render?subject_id=18&report_id=1"
    );
  });

  it("LE05 reportLabel", () => {
    const api = _api();
    const r = _data().reports[0];
    const s = api.reportLabel(r);
    expect(s).toContain("b18");
    expect(s).toContain("Zwischenbericht");
    expect(s).toContain("Zur Abnahme vorgelegt");
  });

  it("LE05b toRows: Felder + Fallbacks (Grundregel 1)", () => {
    const api = _api();
    const rows = api.toRows(_data(), "submitted");
    expect(rows.length).toBe(2); // nur submitted
    expect(rows[0]).toMatchObject({
      subject_id: 18, id: 1, username: "b18", title: "Zwischenbericht",
      status: "submitted", status_label: "Zur Abnahme vorgelegt",
    });
    expect(rows[0].typ).toBe("Vermerk"); // interim -> Vermerk
    // Fehlende Felder werden sichtbar ersetzt, nicht verschluckt.
    const rows2 = api.toRows(
      { reports: [{ subject_id: 77, id: 5, status: "submitted" }] },
      "submitted"
    );
    expect(rows2[0].username).toBe("uid 77");
    expect(rows2[0].title).toBe("(ohne Titel)");
  });

  // LE06 (Build 481/484): Tabulator-Tabelle statt Button-Liste. Der Ctor wird
  // als Stub injiziert; rowClick wird direkt gerufen. Build 484: die Tabelle
  // laedt ALLE Zeilen; Typ/Status sind Dropdown-Filter; Default via
  // initialHeaderFilter.
  it("LE06 renderLectorate: Tabulator-Tabelle + rowClick setzt iframe/onSelect", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);

    let made = null;
    function StubTab(container, opts) {
      made = { container, opts, handlers: {} };
      // Build 486: rowClick wird ueber die Event-API angehaengt (table.on).
      this.on = function (ev, fn) { made.handlers[ev] = fn; };
      this.replaceData = function (d) { made.replaced = d; };
      this.destroy = function () { made.destroyed = true; };
    }

    let picked = null;
    api.renderLectorate(main, _data(), {
      status: "submitted",
      onSelect: function (uid, rid) { picked = [uid, rid]; },
      Tabulator: StubTab,
    });

    // Build 484: ALLE Zeilen geladen (Statusfilter uebernimmt der Header).
    expect(made.opts.data.length).toBe(3);
    const cols = made.opts.columns;
    const uCol = cols.find((c) => c.field === "username");
    expect(uCol.headerFilter).toBe("input");
    // Typ + Status als Dropdown (list) mit festen Werten + 'alle'.
    const tCol = cols.find((c) => c.field === "typ");
    expect(tCol.headerFilter).toBe("list");
    expect(tCol.headerFilterParams.values).toMatchObject({
      "": "alle", Vermerk: "Vermerk", Abschlussbericht: "Abschlussbericht",
    });
    // Build 486: Typ-Dropdown exakter Full-Match ('=').
    expect(tCol.headerFilterFunc).toBe("=");
    const sCol = cols.find((c) => c.field === "status_label");
    expect(sCol.headerFilter).toBe("list");
    expect(sCol.headerFilterParams.values).toMatchObject({
      "": "alle", submitted: "Zur Abnahme vorgelegt", final: "Versandt",
    });
    // Default-Statusfilter 'submitted' via initialHeaderFilter.
    expect(made.opts.initialHeaderFilter).toEqual([
      { field: "status_label", value: "submitted" },
    ]);
    // Paginierung bleibt.
    expect(made.opts.pagination).toBe("local");
    expect(made.opts.paginationSize).toBe(20);
    const frame = main.querySelector("iframe.aiw-lectorate-preview");
    expect(frame).not.toBeNull();

    // Build 486: rowClick via table.on registriert -> ueber handlers aufrufen.
    expect(typeof made.handlers.rowClick).toBe("function");
    const rowData = made.opts.data[0];
    made.handlers.rowClick({}, { getData: () => rowData, getElement: () => null });
    expect(frame.src).toContain("/api/report/render?subject_id=18&report_id=1");
    expect(api.hasSelection()).toBe(true);
    expect(picked).toEqual([18, 1]);
  });

  // Build 484: das Status-<select> ueber der Tabelle ist ENTFERNT.
  it("LE07 Status-Header-Filter filtert Roh-Status; 'alle' zeigt alles", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    function StubTab(container, opts) { this.opts = opts;
      this.on = function () {}; this.replaceData = function () {};
      this.destroy = function () {}; }
    api.renderLectorate(main, _data(), { status: "submitted", Tabulator: StubTab });
    // Kein Status-<select> mehr.
    expect(main.querySelector("select.aiw-lectorate-status")).toBeNull();
    // Filterlogik: Roh-Status, leerer Wert => alle.
    expect(api.statusFilter("submitted", "x", { status: "submitted" })).toBe(true);
    expect(api.statusFilter("approved", "x", { status: "submitted" })).toBe(false);
    expect(api.statusFilter("", "x", { status: "draft" })).toBe(true);
    expect(api.statusFilter(null, "x", { status: "final" })).toBe(true);
  });

  it("LE07d Uebernahme-Knopf steht UNTER der Tabelle (DOM-Reihenfolge)", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    function StubTab(container, opts) { this.opts = opts;
      this.on = function () {}; this.replaceData = function () {};
      this.destroy = function () {}; }
    api.renderLectorate(main, _data(), {
      status: "submitted",
      onTransferToTemplate: function () {},
      Tabulator: StubTab,
    });
    const table = main.querySelector(".aiw-lectorate-table");
    const xbar = main.querySelector(".aiw-lectorate-xferbar");
    expect(table).not.toBeNull();
    expect(xbar).not.toBeNull();
    // compareDocumentPosition: FOLLOWING (4) => xbar kommt NACH der Tabelle.
    const rel = table.compareDocumentPosition(xbar);
    expect(rel & win.Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  // LE08 (Build 414) -------------------------------------------------------
  it("LE08 annotationsUrl + forumContext + categoryLabel", () => {
    const api = _api();
    expect(api.annotationsUrl(18, 1)).toBe(
      "/api/report/annotations?subject_id=18&report_id=1"
    );
    expect(api.categoryLabel("CAT_PERSON")).toBe("Person");
    expect(api.categoryLabel("CAT_UNBEKANNT")).toBe("CAT_UNBEKANNT");
    expect(api.forumContext({ topic_id: 7, forum_id: 3 }))
      .toBe("Thema 7 · Unterforum 3");
    expect(api.forumContext({ topic_id: null, forum_id: null })).toBe("—");
  });

  // LE09 -------------------------------------------------------------------
  it("LE09 renderAnnotations baut Belege mit Forenkontext", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    // renderLectorate setzt das Belege-Panel (annPanel) auf.
    api.renderLectorate(main, _data(), { status: "submitted" });

    api.renderAnnotations({
      report_id: 1, anchor_count: 2,
      items: [
        { annotation_id: 10, block_id: "b1", block_type: "evidence",
          anchor_text: "x", category: "CAT_PERSON", text: "Beleg A",
          post_id: 42, topic_id: 7, forum_id: 3, missing: false,
          deleted: false },
        { annotation_id: 11, block_id: "b2", block_type: "paragraph",
          anchor_text: "y", category: null, text: null, post_id: null,
          topic_id: null, forum_id: null, missing: true, deleted: false },
      ],
    });

    const panel = main.querySelector(".aiw-lectorate-annotations");
    const items = panel.querySelectorAll(".aiw-lectorate-ann-item");
    expect(items.length).toBe(2);
    expect(panel.querySelector(".aiw-lectorate-ann-head").textContent)
      .toContain("Belege (2)");
    // Erster Beleg: Kategorie/Text/Forenkontext.
    expect(items[0].querySelector(".aiw-lectorate-ann-cat").textContent)
      .toBe("Person");
    expect(items[0].querySelector(".aiw-lectorate-ann-text").textContent)
      .toBe("Beleg A");
    const meta0 = items[0].querySelector(".aiw-lectorate-ann-meta").textContent;
    expect(meta0).toContain("Beitrag #42");
    expect(meta0).toContain("Thema 7 · Unterforum 3");
    // Zweiter Beleg: fehlende Annotation sichtbar gemacht.
    expect(items[1].classList.contains("is-missing")).toBe(true);
    expect(items[1].querySelector(".aiw-lectorate-ann-text").textContent)
      .toContain("nicht (mehr) vorhanden");
  });

  // LE10 -------------------------------------------------------------------
  it("LE10 renderAnnotations: keine Belege -> Hinweis", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    api.renderLectorate(main, _data(), { status: "submitted" });
    api.renderAnnotations({ report_id: 1, anchor_count: 0, items: [] });
    const panel = main.querySelector(".aiw-lectorate-annotations");
    expect(panel.querySelectorAll(".aiw-lectorate-ann-item").length).toBe(0);
    expect(panel.textContent).toContain("keine Belege");
  });

  // LE11 -------------------------------------------------------------------
  it("LE11 annotationsError zeigt Fehlermeldung im Panel", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    api.renderLectorate(main, _data(), { status: "submitted" });
    api.annotationsError("HTTP 500");
    const panel = main.querySelector(".aiw-lectorate-annotations");
    expect(panel.textContent).toContain("HTTP 500");
  });

  // --- Kommentar-Panel (SF-3, Build 415) ---------------------------------
  function _comData() {
    return {
      subject_id: 700, report_id: 1, count: 2,
      comments: [
        { comment_id: "c1", report_id: 1, block_id: "b1", reviewer_pid: 1,
          reviewer_role: "lector", comment_text: "Bitte praezisieren",
          suggested_content: null, status: "pending", created_at: 1500 },
        { comment_id: "c2", report_id: 1, block_id: null, reviewer_pid: 4,
          reviewer_role: "supervisor", comment_text: "Chef-Anmerkung",
          suggested_content: "Text Y", status: "addressed", created_at: 1600 },
      ],
    };
  }

  // Build 659 (Vorgang 317481d3): Antwort von /api/report/blocks.
  // b2 traegt die Ordnungszahl 1 — die Ausgabereihenfolge ist NICHT die
  // alphabetische; die Tests haengen deshalb nirgends an der Sortierung.
  function _blocks() {
    return [
      { ordinal: 1, block_id: "b2", block_type: "header",
        type_label: "Überschrift", excerpt: "Die Auswertung ergab Folgendes.",
        truncated: false, comment_count: 0, is_known_type: true },
      { ordinal: 2, block_id: "b1", block_type: "paragraph",
        type_label: "Absatz", excerpt: "Der Beschuldigte meldete sich an. …",
        truncated: true, comment_count: 2, is_known_type: true },
    ];
  }

  it("LE12 reine Kommentar-Helfer", () => {
    const api = _api();
    expect(api.commentsUrl(700, 1)).toBe(
      "/api/report/comments?subject_id=700&report_id=1"
    );
    expect(api.commentStatusLabel("pending")).toBe("offen");
    expect(api.commentStatusLabel("addressed")).toBe("erledigt");
    expect(api.reviewerRoleLabel("supervisor")).toBe("Chef-Ermittlerin");
    expect(api.reviewerRoleLabel("lector")).toBe("Lektorat");
    expect(api.isOwnComment({ reviewer_pid: 1 }, 1)).toBe(true);
    expect(api.isOwnComment({ reviewer_pid: 4 }, 1)).toBe(false);
  });

  it("LE13 renderComments: Formular, Liste, eigene Aufloesung", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    api.renderLectorate(main, _data(), { status: "submitted" });

    let added = null, resolved = null;
    // Build 659: Die Blockliste gehoert jetzt zum Aufruf. Ohne sie kann kein
    // Kommentar mehr abgesendet werden (der Anker ist Pflicht) — LE16 haelt
    // genau diesen Fall fest.
    api.renderComments(_comData(), {
      personId: 1,
      blocks: _blocks(),
      onAdd: function (b) { added = b; },
      onResolve: function (b) { resolved = b; },
    });

    const panel = main.querySelector(".aiw-lectorate-comments");
    expect(panel.querySelector(".aiw-lectorate-com-head").textContent)
      .toContain("Kommentare (2)");
    const items = panel.querySelectorAll(".aiw-lectorate-com-item");
    expect(items.length).toBe(2);
    // c1 = eigen + offen -> Aufloesen-Knoepfe; c2 = fremd -> keine.
    expect(items[0].querySelectorAll(".aiw-lectorate-com-resolve").length)
      .toBe(2);
    expect(items[1].querySelectorAll(".aiw-lectorate-com-resolve").length)
      .toBe(0);
    expect(items[1].classList.contains("is-resolved")).toBe(true);
    expect(items[1].querySelector(".aiw-lectorate-com-suggestion").textContent)
      .toContain("Text Y");

    // Neuen Kommentar absenden — mit GEWAEHLTER Textstelle (Build 659).
    panel.querySelector(".aiw-lectorate-com-text").value = "Neuer Hinweis";
    panel.querySelector(".aiw-lectorate-com-block").value = "b2";
    panel.querySelector(".aiw-lectorate-com-form").dispatchEvent(
      new win.Event("submit", { bubbles: true, cancelable: true })
    );
    expect(added).toEqual({
      subject_id: 700, report_id: 1, block_id: "b2",
      comment_text: "Neuer Hinweis", suggested_content: null,
    });

    // Eigenen Kommentar aufloesen (erledigt).
    items[0].querySelector('.aiw-lectorate-com-resolve[data-status="addressed"]')
      .dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(resolved).toEqual({
      subject_id: 700, comment_id: "c1", status: "addressed",
    });
  });

  it("LE14 renderComments: leerer Text -> Fehler, keine Kommentare -> Hinweis", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    api.renderLectorate(main, _data(), { status: "submitted" });

    // keine Kommentare -> Hinweis.
    let added = null;
    api.renderComments({ subject_id: 700, report_id: 1, count: 0, comments: [] },
      { personId: 1, blocks: _blocks(), onAdd: function (b) { added = b; } });
    const panel = main.querySelector(".aiw-lectorate-comments");
    expect(panel.textContent).toContain("Noch keine Kommentare");

    // leerer Text -> Fehlermeldung, onAdd NICHT gerufen.
    panel.querySelector(".aiw-lectorate-com-form").dispatchEvent(
      new win.Event("submit", { bubbles: true, cancelable: true })
    );
    expect(added).toBeNull();
    expect(panel.querySelector(".aiw-lectorate-com-formerr").textContent)
      .toContain("Kommentartext");
  });

  // =========================================================================
  // Build 659 — Vorgang 317481d3: Anker als AUSWAHL statt Freitext.
  // =========================================================================

  it("LE15 blocksUrl + blockOptionLabel (reine Funktionen)", () => {
    const api = _api();
    expect(api.blocksUrl(700, 1)).toBe(
      "/api/report/blocks?subject_id=700&report_id=1"
    );
    const [b2, b1] = _blocks();
    // Nr. · Typ · Auszug — ohne Kommentare KEIN '(0 Kommentare)'-Anhang.
    expect(api.blockOptionLabel(b2)).toBe(
      "1 · Überschrift · Die Auswertung ergab Folgendes."
    );
    // Mit Kommentaren: Zahl am Ende, korrekter Numerus.
    expect(api.blockOptionLabel(b1)).toBe(
      "2 · Absatz · Der Beschuldigte meldete sich an. … (2 Kommentare)"
    );
    expect(api.blockOptionLabel({ ordinal: 5, type_label: "Absatz",
      excerpt: "X", comment_count: 1 })).toContain("(1 Kommentar)");
    expect(api.blockOptionLabel(null)).toBe("");
  });

  it("LE16 Anker ist ein Auswahlfeld, ist Pflicht und hat keine Vorauswahl", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    api.renderLectorate(main, _data(), { status: "submitted" });

    let added = null;
    api.renderComments({ subject_id: 700, report_id: 1, count: 0, comments: [] },
      { personId: 1, blocks: _blocks(), onAdd: function (b) { added = b; } });
    const panel = main.querySelector(".aiw-lectorate-comments");
    const sel = panel.querySelector(".aiw-lectorate-com-block");

    // DER KERN DES VORGANGS: kein Freitextfeld mehr.
    expect(sel.tagName).toBe("SELECT");
    expect(sel.required).toBe(true);
    expect(sel.disabled).toBe(false);

    // Ein Platzhalter + zwei Bloecke, in der Reihenfolge der Vorschau.
    const opts = sel.querySelectorAll("option");
    expect(opts.length).toBe(3);
    expect(opts[0].disabled).toBe(true);
    expect(opts[0].textContent).toContain("Textstelle wählen");
    expect([opts[1].value, opts[2].value]).toEqual(["b2", "b1"]);

    // KEINE Vorauswahl: sonst entstuende beim schnellen Absenden ein
    // Kommentar an Block 1, den niemand gewaehlt hat.
    expect(sel.value).toBe("");

    // Text da, Stelle fehlt -> abgewiesen, onAdd NICHT gerufen.
    panel.querySelector(".aiw-lectorate-com-text").value = "Passt so nicht.";
    panel.querySelector(".aiw-lectorate-com-form").dispatchEvent(
      new win.Event("submit", { bubbles: true, cancelable: true })
    );
    expect(added).toBeNull();
    expect(panel.querySelector(".aiw-lectorate-com-formerr").textContent)
      .toContain("Textstelle");
  });

  it("LE17 ohne Blockliste: gesperrt und benannt, KEIN Rueckfall auf Freitext", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    api.renderLectorate(main, _data(), { status: "submitted" });

    let added = null;
    // blocks fehlt ganz — z.B. weil /api/report/blocks nicht antwortete.
    api.renderComments({ subject_id: 700, report_id: 1, count: 0, comments: [] },
      { personId: 1, onAdd: function (b) { added = b; } });
    const panel = main.querySelector(".aiw-lectorate-comments");
    const sel = panel.querySelector(".aiw-lectorate-com-block");

    expect(sel.tagName).toBe("SELECT");
    expect(sel.disabled).toBe(true);
    expect(sel.querySelectorAll("option").length).toBe(1);
    // Die Maske SAGT, was los ist, statt ein leeres Feld zu zeigen.
    expect(sel.textContent).toContain("keine Blöcke verfügbar");

    panel.querySelector(".aiw-lectorate-com-text").value = "Hinweis";
    panel.querySelector(".aiw-lectorate-com-form").dispatchEvent(
      new win.Event("submit", { bubbles: true, cancelable: true })
    );
    expect(added).toBeNull();
    expect(panel.querySelector(".aiw-lectorate-com-formerr").textContent)
      .toContain("nicht geladen");
  });

  it("LE18 Kommentarliste weist die Stelle lesbar aus", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    api.renderLectorate(main, _data(), { status: "submitted" });

    const daten = _comData();
    // Dritter Kommentar: Anker zeigt auf einen Block, den es nicht (mehr) gibt.
    daten.comments.push({
      comment_id: "c3", report_id: 1, block_id: "b-weg", reviewer_pid: 1,
      reviewer_role: "lector", comment_text: "Verwaist", suggested_content: null,
      status: "pending", created_at: 1700,
    });
    daten.count = 3;
    api.renderComments(daten, { personId: 1, blocks: _blocks() });

    const panel = main.querySelector(".aiw-lectorate-comments");
    const metas = panel.querySelectorAll(".aiw-lectorate-com-meta");

    // c1 haengt an b1 -> dieselbe Beschriftung wie im Auswahlfeld, KEINE UUID.
    expect(metas[0].textContent).toContain("Textstelle 2 · Absatz");
    // c2 ist ankerlos -> ausdruecklich benannt statt einfach weggelassen.
    expect(metas[1].textContent).toContain("ohne Textstelle");
    // c3 zeigt ins Leere -> Befund, nicht Rohkennung.
    expect(metas[2].textContent).toContain("nicht (mehr) im");
    expect(metas[2].textContent).toContain("b-weg");
  });
});
