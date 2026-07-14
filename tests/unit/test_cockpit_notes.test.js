/**
 * tests/unit/test_cockpit_notes.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Betreuungs-Notizen
 *
 * Testsuite fuer management/server/static/cockpit_notes.js (Build 406).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitNotes) —
 * keine duplizierte Logik-Kopie ('gruen-aber-tot'-Falle vermeiden).
 *
 * NT01 — API verfuegbar (reine Funktionen + render + openEditor).
 * NT02 — parseCommit: erste Zeile = Ueberschrift, Rest = Rumpf (Commit-Metapher).
 * NT03 — matchesSearch: Treffer in Ueberschrift/Rumpf/Tag; leer = alles.
 * NT04 — matchesFilter + filterNotes: Farbe/Status/Tag als UND-Verknuepfung.
 * NT05 — allTags: dedupliziert + sortiert.
 * NT06 — colorBg/colorEdge: Fallback 'grau' bei unbekannter Farbe.
 * NT07 — renderNotes: Kopf + Filterleiste + Karten + count; Aufklappen des
 *        Rumpfs (Chevron); Commit-Metapher sichtbar.
 * NT08 — renderNotes (Archiv): Titel 'Archiv', KEIN '+ Neue Notiz',
 *        'Wiederherstellen' statt 'Archivieren'.
 * NT09 — Callbacks: Status-Haken -> onUpdate; 'Archivieren' -> onArchive.
 * NT10 — openEditor: leere Ueberschrift -> Fehler (kein onSubmit); gueltig ->
 *        onSubmit mit geparster Nutzlast; Abbrechen entfernt das Overlay.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_notes.js",
  "utf-8"
);

let win;
function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

beforeEach(() => {
  win = _ctx();
  win.AIWCockpitNotes._resetUi();
});

function _api() { return win.AIWCockpitNotes; }

function _note(over) {
  return Object.assign(
    {
      id: 1, owner_id: 1, owner_display_name: "Chefin",
      subject_person_id: 2, subject_display_name: "Mueller",
      title: "Rueckruf klaeren", body: "Details zur Minimap.",
      color: "gelb", tags: ["schulung", "minimap"],
      status: "offen", pinned: false, sort_index: 1000,
      is_archived: false,
    },
    over || {}
  );
}

function _data(notes, over) {
  return Object.assign(
    {
      scope: "alle", owner_id: null, archived: false,
      colors: [
        { code: "gelb", label: "Gelb" },
        { code: "blau", label: "Blau" },
      ],
      persons: [
        { id: 2, display_name: "Mueller" },
        { id: 3, display_name: "Schmitz" },
      ],
      count: notes.length, notes: notes,
    },
    over || {}
  );
}

describe("cockpit_notes.js — Betreuungs-Notizen (Build 406)", () => {
  it("NT01: API verfuegbar", () => {
    const api = _api();
    ["parseCommit", "matchesSearch", "matchesFilter", "filterNotes",
     "allTags", "colorBg", "colorEdge", "renderNotes", "openEditor"]
      .forEach((fn) => expect(typeof api[fn]).toBe("function"));
  });

  it("NT02: parseCommit trennt Ueberschrift und Rumpf", () => {
    const api = _api();
    expect(api.parseCommit("Titel\nZeile 2\nZeile 3"))
      .toEqual({ title: "Titel", body: "Zeile 2\nZeile 3" });
    expect(api.parseCommit("  Nur Titel  ")).toEqual({ title: "Nur Titel", body: "" });
    expect(api.parseCommit("Titel\r\nWin")).toEqual({ title: "Titel", body: "Win" });
    expect(api.parseCommit("Titel\n\n\nRumpf")).toEqual({ title: "Titel", body: "Rumpf" });
    expect(api.parseCommit("")).toEqual({ title: "", body: "" });
  });

  it("NT03: matchesSearch trifft Titel/Rumpf/Tag", () => {
    const api = _api();
    const n = _note();
    expect(api.matchesSearch(n, "")).toBe(true);
    expect(api.matchesSearch(n, "rueckruf")).toBe(true);   // Titel
    expect(api.matchesSearch(n, "minimap")).toBe(true);    // Rumpf + Tag
    expect(api.matchesSearch(n, "SCHULUNG")).toBe(true);   // Tag, case-insensitiv
    expect(api.matchesSearch(n, "xyz")).toBe(false);
  });

  it("NT04: matchesFilter/filterNotes als UND", () => {
    const api = _api();
    const a = _note({ id: 1, color: "gelb", status: "offen", tags: ["a"] });
    const b = _note({ id: 2, color: "blau", status: "erledigt", tags: ["b"] });
    expect(api.matchesFilter(a, { color: "gelb" })).toBe(true);
    expect(api.matchesFilter(a, { color: "blau" })).toBe(false);
    expect(api.matchesFilter(b, { status: "erledigt", tag: "b" })).toBe(true);
    expect(api.matchesFilter(b, { status: "erledigt", tag: "a" })).toBe(false);

    const filtered = api.filterNotes([a, b], { status: "offen" });
    expect(filtered.map((n) => n.id)).toEqual([1]);
  });

  it("NT05: allTags dedupliziert + sortiert", () => {
    const api = _api();
    const notes = [_note({ tags: ["b", "a"] }), _note({ tags: ["a", "c"] })];
    expect(api.allTags(notes)).toEqual(["a", "b", "c"]);
  });

  it("NT06: colorBg/colorEdge Fallback grau", () => {
    const api = _api();
    expect(api.colorBg("gelb")).not.toBe(api.colorBg("grau"));
    expect(api.colorBg("gibtsnicht")).toBe(api.colorBg("grau"));
    expect(api.colorEdge("gibtsnicht")).toBe(api.colorEdge("grau"));
  });

  it("NT07: renderNotes baut Kopf/Filter/Karten + Aufklappen", () => {
    const api = _api();
    const main = win.document.createElement("div");
    api.renderNotes(main, _data([_note()]), { archived: false });

    // Kopf + Neu-Button + Filterleiste vorhanden.
    expect(main.querySelector(".aiw-notes-title").textContent)
      .toContain("Betreuungs-Notizen");
    expect(main.textContent).toContain("+ Neue Notiz");
    expect(main.querySelector(".aiw-notes-search")).toBeTruthy();

    // Genau eine Karte; Ueberschrift sichtbar, Rumpf zunaechst versteckt.
    const cards = main.querySelectorAll(".aiw-note");
    expect(cards.length).toBe(1);
    expect(main.querySelector(".aiw-note-title").textContent)
      .toBe("Rueckruf klaeren");
    const body = main.querySelector(".aiw-note-body");
    expect(body.style.display).toBe("none");

    // Chevron klappt auf.
    main.querySelector(".aiw-note-chevron").dispatchEvent(
      new win.Event("click"));
    expect(body.style.display).toBe("block");

    // Tags als Chips + Betroffener.
    expect(main.querySelectorAll(".aiw-note-tag").length).toBe(2);
    expect(main.querySelector(".aiw-note-subject").textContent)
      .toContain("Mueller");

    // count-Zeile.
    expect(main.querySelector(".aiw-notes-count").textContent)
      .toContain("1 von 1");
  });

  it("NT08: renderNotes Archiv-Ansicht", () => {
    const api = _api();
    const main = win.document.createElement("div");
    api.renderNotes(main, _data([_note({ is_archived: true })]),
                    { archived: true });
    expect(main.querySelector(".aiw-notes-title").textContent)
      .toContain("Archiv");
    expect(main.textContent).not.toContain("+ Neue Notiz");
    expect(main.textContent).toContain("Wiederherstellen");
    expect(main.textContent).not.toContain("Archivieren");
  });

  it("NT09: Callbacks Status-Haken/Archivieren", () => {
    const api = _api();
    const main = win.document.createElement("div");
    let updated = null; let archivedId = null;
    api.renderNotes(main, _data([_note({ id: 42 })]), {
      archived: false,
      onUpdate: (p) => { updated = p; },
      onArchive: (id) => { archivedId = id; },
    });

    const chk = main.querySelector(".aiw-note-check");
    chk.checked = true;
    chk.dispatchEvent(new win.Event("change"));
    expect(updated).toEqual({ id: 42, status: "erledigt" });

    // 'Archivieren' ist der Aktionsknopf mit is-danger.
    main.querySelector(".aiw-note-act.is-danger")
      .dispatchEvent(new win.Event("click"));
    expect(archivedId).toBe(42);
  });

  it("NT10: openEditor Validierung + onSubmit + Abbrechen", () => {
    const api = _api();
    let submitted = null;
    const ed = api.openEditor({
      colors: [{ code: "gelb", label: "Gelb" }],
      persons: [{ id: 2, display_name: "Mueller" }],
      note: null,
      onSubmit: (p) => { submitted = p; },
    });
    const overlay = win.document.querySelector(".aiw-modal-overlay");
    expect(overlay).toBeTruthy();

    // Leerer Text -> Fehler, kein onSubmit.
    const save = overlay.querySelector(".aiw-btn-primary");
    save.click();
    expect(submitted).toBe(null);
    expect(overlay.querySelector(".aiw-modal-err").textContent.length)
      .toBeGreaterThan(0);

    // Gueltiger Text -> onSubmit mit geparster Nutzlast, Overlay weg.
    const ta = overlay.querySelector(".aiw-modal-text");
    ta.value = "Neue Ueberschrift\nDetailzeile";
    overlay.querySelector(".aiw-modal-inp").value = "eins, zwei ,  ";
    save.click();
    expect(submitted.title).toBe("Neue Ueberschrift");
    expect(submitted.body).toBe("Detailzeile");
    expect(submitted.color).toBe("gelb");
    // Client trimmt + verwirft Leere; Dedup uebernimmt der Server (_norm_tags).
    expect(submitted.tags).toEqual(["eins", "zwei"]);
    expect(win.document.querySelector(".aiw-modal-overlay")).toBe(null);

    // Zweites Modal: Abbrechen entfernt Overlay ohne onSubmit.
    submitted = null;
    api.openEditor({ colors: [], persons: [], note: null,
                     onSubmit: (p) => { submitted = p; } });
    win.document.querySelector(".aiw-btn-ghost").click();
    expect(win.document.querySelector(".aiw-modal-overlay")).toBe(null);
    expect(submitted).toBe(null);
  });
});
