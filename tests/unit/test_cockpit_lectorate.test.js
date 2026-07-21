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

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
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

  // LE06 (Build 481): Tabulator-Tabelle statt Button-Liste. Der Tabulator-Ctor
  // wird als Stub injiziert (opts.Tabulator); rowClick wird direkt gerufen.
  it("LE06 renderLectorate: Tabulator-Tabelle + rowClick setzt iframe/onSelect", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);

    let made = null;
    function StubTab(container, opts) {
      made = { container, opts };
      this.replaceData = function (d) { made.replaced = d; };
      this.destroy = function () { made.destroyed = true; };
    }

    let picked = null;
    api.renderLectorate(main, _data(), {
      status: "submitted",
      onSelect: function (uid, rid) { picked = [uid, rid]; },
      Tabulator: StubTab,
    });

    // Nur submitted (2 Zeilen); erwartete Spalten vorhanden.
    expect(made.opts.data.length).toBe(2);
    const fields = made.opts.columns.map((c) => c.field);
    expect(fields).toContain("username");
    expect(fields).toContain("status_label");
    const frame = main.querySelector("iframe.aiw-lectorate-preview");
    expect(frame).not.toBeNull();

    // rowClick des ersten Berichts (uid 18, rid 1) simulieren.
    const rowData = made.opts.data[0];
    made.opts.rowClick({}, { getData: () => rowData, getElement: () => null });
    expect(frame.src).toContain("/api/report/render?subject_id=18&report_id=1");
    expect(api.hasSelection()).toBe(true);
    expect(picked).toEqual([18, 1]);
  });

  it("LE07 Statuswechsel 'alle' tauscht Tabellendaten via replaceData", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);

    let made = null;
    function StubTab(container, opts) {
      made = { container, opts };
      this.replaceData = function (d) { made.replaced = d; };
      this.destroy = function () {};
    }
    api.renderLectorate(main, _data(), {
      status: "submitted", Tabulator: StubTab,
    });
    expect(made.opts.data.length).toBe(2); // submitted

    const sel = main.querySelector("select.aiw-lectorate-status");
    sel.value = "alle";
    sel.dispatchEvent(new win.Event("change", { bubbles: true }));
    // Kein Neu-Render: dieselbe Instanz, Daten via replaceData ausgetauscht.
    expect(made.replaced.length).toBe(3); // alle
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
    api.renderComments(_comData(), {
      personId: 1,
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

    // Neuen Kommentar absenden.
    panel.querySelector(".aiw-lectorate-com-text").value = "Neuer Hinweis";
    panel.querySelector(".aiw-lectorate-com-form").dispatchEvent(
      new win.Event("submit", { bubbles: true, cancelable: true })
    );
    expect(added).toEqual({
      subject_id: 700, report_id: 1, block_id: null,
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
      { personId: 1, onAdd: function (b) { added = b; } });
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
});
