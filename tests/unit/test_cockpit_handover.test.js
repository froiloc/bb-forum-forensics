/**
 * tests/unit/test_cockpit_handover.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Uebergaben
 *
 * Testsuite fuer Build 520 (AP-2G / Idee 30): management/server/static/
 * cockpit_handover.js, Frontend zu /api/handover. Getestet wird der ECHTE
 * Code (readFileSync + JSDOM, window.AIWCockpitHandover).
 *
 * HV01 — API vollstaendig verfuegbar
 * HV02 — Entscheidung (1): die BELEGNUMMER steht in jeder Zeile
 * HV03 — Entscheidung (2): ein fehlender Vorgaenger bei der Erstzuweisung
 *        wird als "(aus dem Rückstau)" ausgewiesen, nicht als leere Zelle
 * HV04 — eine Rueckgabe hat keinen Empfaenger — auch das wird BENANNT
 * HV05 — ein wirklich unbekannter Bezug heisst "(nicht erfasst)" und wird
 *        nicht mit "(aus dem Rückstau)" verwechselt
 * HV06 — Entscheidung (3): ein Ausschnitt wird benannt, und die Zaehler
 *        werden ausdruecklich auf ihn bezogen
 * HV07 — Entscheidung (4): die Reihenfolge des Backends (neueste zuerst)
 *        bleibt unangetastet
 * HV08 — drei unterscheidbare Zustaende: Fehler / Leerbefund / Befund
 * HV09 — der Leerbefund MIT Filter sagt ausdruecklich, dass er nichts ueber
 *        die Existenz des Falls aussagt
 * HV10 — die Filterleiste ruft onFilter mit Wert bzw. null
 * HV11 — unbekannte Art faellt auf; personText liefert nie 'undefined'
 * HV12 — Markup in Namen bleibt Text, UTF-8 erhalten; der Herkunftsvermerk
 *        steht unter jeder Fassung
 *
 * Version: v0.8.520 · Build: 520 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_handover.js",
  "utf-8"
);

function _makeContext() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

function _api() {
  return _makeContext().AIWCockpitHandover;
}

function E(over) {
  return Object.assign(
    {
      subject_id: 5001,
      seq: 412,
      ts: 1750000000,
      kind: "reassignment",
      from_person_id: 2,
      from_name: "Beta",
      to_person_id: 4,
      to_name: "Delta",
      by_person_id: 1,
      by_name: "Chefin, Alpha",
    },
    over
  );
}

function D(over) {
  return Object.assign(
    {
      generated_at: 1750000000,
      reassignment_count: 1,
      cases_with_handover: 1,
      filter_subject_id: null,
      entries: [E()],
    },
    over
  );
}

describe("cockpit_handover.js (Build 520)", () => {
  // HV01 --------------------------------------------------------------------
  it("HV01: API vollstaendig", () => {
    const api = _api();
    [
      "kindLabel",
      "kindClass",
      "personText",
      "fromText",
      "toText",
      "byText",
      "fmtTs",
      "filterText",
      "countsText",
      "entries",
      "renderHandover",
    ].forEach((n) => {
      expect(typeof api[n], n).toBe("function");
    });
  });

  // HV02 --------------------------------------------------------------------
  it("HV02: die Belegnummer steht in der Zeile", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitHandover.renderHandover(main, D({ entries: [E({ seq: 991 })] }), {});
    expect(main.querySelector(".aiw-hv-seq").textContent).toBe("#991");
    expect(main.querySelector(".aiw-hv-row").getAttribute("data-seq")).toBe(
      "991"
    );
  });

  // HV03 --------------------------------------------------------------------
  it("HV03: kein Vorgaenger bei der Erstzuweisung ist eine Aussage", () => {
    const api = _api();
    const e = E({ kind: "initial", from_person_id: null, from_name: null });
    expect(api.fromText(e)).toBe("(aus dem Rückstau)");

    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitHandover.renderHandover(main, D({ entries: [e] }), {});
    const zelle = main.querySelector(".aiw-hv-from");
    expect(zelle.textContent).toContain("Rückstau");
    expect(zelle.textContent).not.toBe("");
  });

  // HV04 --------------------------------------------------------------------
  it("HV04: eine Rueckgabe hat keinen Empfaenger — benannt", () => {
    const api = _api();
    const e = E({ kind: "unassignment", to_person_id: null, to_name: null });
    expect(api.toText(e)).toBe("(zurück in den Rückstau)");
    expect(api.kindLabel("unassignment")).toBe("Rückgabe in den Rückstau");
  });

  // HV05 --------------------------------------------------------------------
  it("HV05: 'nicht erfasst' wird nicht mit 'Rückstau' verwechselt", () => {
    const api = _api();
    // reassignment OHNE Vorgaenger waere ein echter Datenmangel.
    expect(
      api.fromText(E({ kind: "reassignment", from_person_id: null, from_name: null }))
    ).toBe("(nicht erfasst)");
    expect(
      api.toText(E({ kind: "reassignment", to_person_id: null, to_name: null }))
    ).toBe("(nicht erfasst)");
    expect(api.byText(E({ by_person_id: null, by_name: null }))).toBe(
      "(nicht erfasst)"
    );
  });

  // HV06 --------------------------------------------------------------------
  it("HV06: der Ausschnitt wird benannt und die Zaehler bezogen", () => {
    const api = _api();
    expect(api.filterText(D({ filter_subject_id: null }))).toContain(
      "alle Fälle"
    );
    const mit = api.filterText(D({ filter_subject_id: 5001 }));
    expect(mit).toContain("NUR Fall 5001");
    expect(mit).toContain("allein auf diesen Fall");
    expect(
      api.countsText(D({ reassignment_count: 3, cases_with_handover: 2 }))
    ).toContain("im gezeigten Ausschnitt");
  });

  // HV07 --------------------------------------------------------------------
  it("HV07: Reihenfolge des Backends (neueste zuerst) bleibt", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitHandover.renderHandover(
      main,
      D({
        entries: [E({ seq: 900 }), E({ seq: 500 }), E({ seq: 100 })],
      }),
      {}
    );
    const seqs = Array.from(main.querySelectorAll(".aiw-hv-row")).map((r) =>
      r.getAttribute("data-seq")
    );
    expect(seqs).toEqual(["900", "500", "100"]);
  });

  // HV08 --------------------------------------------------------------------
  it("HV08: drei unterscheidbare Zustaende", () => {
    const win = _makeContext();
    const api = win.AIWCockpitHandover;

    const mErr = win.document.createElement("main");
    expect(api.renderHandover(mErr, { error: "HTTP 503" }, {}).state).toBe(
      "error"
    );
    expect(mErr.textContent).toContain("KEIN Leerbefund");
    expect(mErr.querySelector(".aiw-hv-leer")).toBe(null);

    const mLeer = win.document.createElement("main");
    expect(
      api.renderHandover(mLeer, D({ entries: [], reassignment_count: 0 }), {})
        .state
    ).toBe("leer");
    expect(mLeer.querySelector(".aiw-hv-leer")).toBeTruthy();

    const mBefund = win.document.createElement("main");
    expect(api.renderHandover(mBefund, D(), {}).count).toBe(1);
  });

  // HV09 --------------------------------------------------------------------
  it("HV09: Leerbefund mit Filter sagt nichts ueber die Existenz des Falls", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitHandover.renderHandover(
      main,
      D({ entries: [], reassignment_count: 0, filter_subject_id: 5020 }),
      {}
    );
    const t = main.querySelector(".aiw-hv-leer").textContent;
    expect(t).toContain("5020");
    expect(t).toContain("NICHT");
    expect(t).toContain("Zuweisungsbeleg");
  });

  // HV10 --------------------------------------------------------------------
  it("HV10: die Filterleiste ruft onFilter", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    const gerufen = [];
    win.AIWCockpitHandover.renderHandover(main, D(), {
      onFilter: (v) => gerufen.push(v),
    });
    const feld = main.querySelector(".aiw-hv-filter");
    const knoepfe = main.querySelectorAll(".aiw-hv-btn");
    feld.value = " 5001 ";
    knoepfe[0].click();               // Einschraenken
    expect(gerufen[0]).toBe("5001");  // getrimmt
    feld.value = "";
    knoepfe[0].click();               // leeres Feld -> kein Filter
    expect(gerufen[1]).toBe(null);
    knoepfe[1].click();               // 'Alle Fälle'
    expect(gerufen[2]).toBe(null);

    // Der bestehende Filter steht im Feld — der Ausschnitt ist ablesbar.
    const m2 = win.document.createElement("main");
    win.AIWCockpitHandover.renderHandover(
      m2,
      D({ filter_subject_id: 777 }),
      {}
    );
    expect(m2.querySelector(".aiw-hv-filter").value).toBe("777");
  });

  // HV11 --------------------------------------------------------------------
  it("HV11: unbekannte Art faellt auf; personText nie 'undefined'", () => {
    const api = _api();
    expect(api.kindClass("uebertragung")).toBe("is-unbekannt");
    expect(api.kindLabel("uebertragung")).toContain("unbekannt");
    expect(api.kindLabel("uebertragung")).toContain("uebertragung");
    expect(api.kindClass("initial")).toBe("is-initial");
    // personText: Name > ID > null (nie 'undefined').
    expect(api.personText(7, "Beta")).toBe("Beta");
    expect(api.personText(7, null)).toBe("#7");
    expect(api.personText(null, null)).toBe(null);
    expect(api.fmtTs(null)).toBe("—");
  });

  // HV12 --------------------------------------------------------------------
  it("HV12: Markup bleibt Text; der Herkunftsvermerk steht immer da", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    const name = '<img src=x onerror="1">Пётр';
    win.AIWCockpitHandover.renderHandover(
      main,
      D({ entries: [E({ to_name: name })] }),
      {}
    );
    expect(main.querySelector("img")).toBe(null);
    expect(main.querySelector(".aiw-hv-to").textContent).toBe(name);
    expect(main.textContent).toContain("Пётр");
    // Herkunftsvermerk — auch beim Leerbefund.
    expect(main.querySelector(".aiw-hv-foot").textContent).toContain(
      "Audit-Kette"
    );
    const m2 = win.document.createElement("main");
    win.AIWCockpitHandover.renderHandover(m2, D({ entries: [] }), {});
    expect(m2.querySelector(".aiw-hv-foot")).toBeTruthy();
  });
});
