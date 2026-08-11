/**
 * test_scroll_memory.test.js
 * Unit-/Regressionstests: ScrollMemory (Scrollpositions-Wiederherstellung)
 * Baustelle 3 · Build 473 (Anker-primaer + Y-Fallback) · 2026-07-21
 *
 * Getestet wird die AUSGELIEFERTE Quelle toolbar/scroll_memory.js (kein
 * nachgebauter Klon), geladen ueber jsdom-eval — analog test_submit_dialog.
 * Schwerpunkt: die reinen Entscheidungsfunktionen (Anker-Erkennung, Ziel-
 * aufloesung Anker vs. Y, klemmen, zoom-skalieren, settle, LRU, robustes
 * Parsen) sowie der localStorage-Rundlauf.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("toolbar/scroll_memory.js", "utf-8");

function loadClass() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://127.0.0.2/forum/",
  });
  dom.window.eval(_src);
  return dom.window.ScrollMemory;
}

function fakeStorage() {
  let m = Object.create(null);
  return {
    getItem: (k) => (k in m ? m[k] : null),
    setItem: (k, v) => { m[k] = String(v); },
    removeItem: (k) => { delete m[k]; },
    _raw: () => m,
  };
}

function fakeWin(scrollY, dpr) {
  return {
    scrollY: scrollY,
    devicePixelRatio: dpr || 1,
    location: { pathname: "/forum/viewtopic.php", search: "?id=1" },
    performance: { now: () => 0 },
  };
}

describe("ScrollMemory — reine Helfer", () => {
  const SM = loadClass();

  it("SM01: Klasse und statische Helfer verfuegbar", () => {
    expect(typeof SM).toBe("function");
    ["isStableId", "clampTarget", "scaleForZoom", "anchorTarget", "shouldRestore",
     "hasRestore", "resolveTarget", "isSettled", "pruneStore", "parseStore"]
      .forEach((f) => expect(typeof SM[f]).toBe("function"));
  });

  it("SM02: clampTarget klemmt auf [0, scrollHeight-innerHeight]", () => {
    expect(SM.clampTarget(500, 3000, 1000)).toBe(500);
    expect(SM.clampTarget(9999, 3000, 1000)).toBe(2000);
    expect(SM.clampTarget(-50, 3000, 1000)).toBe(0);
    expect(SM.clampTarget(NaN, 3000, 1000)).toBe(0);
    expect(SM.clampTarget(undefined, 3000, 1000)).toBe(0);
    expect(SM.clampTarget(500, 800, 1000)).toBe(0);
  });

  it("SM03: scaleForZoom skaliert nur bei abweichender Zoomstufe", () => {
    expect(SM.scaleForZoom(1000, 1, 1)).toBe(1000);
    expect(SM.scaleForZoom(1000, 1, 2)).toBe(2000);
    expect(SM.scaleForZoom(1000, 2, 1)).toBe(500);
    expect(SM.scaleForZoom(1000, 0, 1.5)).toBe(1000);
    expect(SM.scaleForZoom(1000, 1.5, 0)).toBe(1000);
  });

  it("SM04: shouldRestore respektiert die Mindestschwelle", () => {
    expect(SM.shouldRestore(100, 8)).toBe(true);
    expect(SM.shouldRestore(8, 8)).toBe(false);
    expect(SM.shouldRestore(3, 8)).toBe(false);
    expect(SM.shouldRestore(undefined, 8)).toBe(false);
    expect(SM.shouldRestore(NaN, 8)).toBe(false);
  });

  it("SM05: isSettled — stabile Frames ODER Timeout", () => {
    const cfg = { STABLE_FRAMES: 4, MAX_WAIT_MS: 1000 };
    expect(SM.isSettled(4, 50, cfg)).toBe(true);
    expect(SM.isSettled(3, 50, cfg)).toBe(false);
    expect(SM.isSettled(0, 1000, cfg)).toBe(true);
    expect(SM.isSettled(1, 999, cfg)).toBe(false);
  });

  it("SM06: pruneStore behaelt die juengsten N und mutiert nicht", () => {
    const store = {
      "/a": { y: 1, dpr: 1, t: 10 },
      "/b": { y: 2, dpr: 1, t: 30 },
      "/c": { y: 3, dpr: 1, t: 20 },
    };
    const kept = SM.pruneStore(store, 2);
    expect(Object.keys(kept).sort()).toEqual(["/b", "/c"]);
    expect(kept["/a"]).toBeUndefined();
    expect(Object.keys(store).length).toBe(3);
    const all = SM.pruneStore(store, 10);
    expect(Object.keys(all).sort()).toEqual(["/a", "/b", "/c"]);
    expect(all).not.toBe(store);
  });

  it("SM07: parseStore faengt defekten JSON ab", () => {
    expect(SM.parseStore(null)).toEqual({});
    expect(SM.parseStore("")).toEqual({});
    expect(SM.parseStore("{kaputt")).toEqual({});
    expect(SM.parseStore('{"/a":{"y":5}}')).toEqual({ "/a": { y: 5 } });
  });

  // --- Build 473: Anker-Logik -------------------------------------------
  it("SM12: isStableId akzeptiert nur inhaltsabgeleitete IDs", () => {
    ["p335445", "p1", "forum12", "topic7", "pid42"].forEach((id) =>
      expect(SM.isStableId(id)).toBe(true));
    ["_vt_ab12", "forensic-viewport", "progressbar", "page-body", "", null, undefined, "p"]
      .forEach((id) => expect(SM.isStableId(id)).toBe(false));
  });

  it("SM13: anchorTarget = Ankerlage + Offset", () => {
    expect(SM.anchorTarget(1119, 225)).toBe(1344);
    expect(SM.anchorTarget(1000, 0)).toBe(1000);
    expect(SM.anchorTarget(1000, undefined)).toBe(1000);
    expect(SM.anchorTarget(1000, -792)).toBe(208);
  });

  it("SM14: hasRestore — Anker ODER brauchbare Y", () => {
    expect(SM.hasRestore({ anchor: "p1", offset: 10, y: 0 }, 8)).toBe(true); // Anker reicht
    expect(SM.hasRestore({ y: 500 }, 8)).toBe(true);
    expect(SM.hasRestore({ y: 3 }, 8)).toBe(false);
    expect(SM.hasRestore({ anchor: "_vt_x", y: 3 }, 8)).toBe(false); // instabiler Anker zaehlt nicht
    expect(SM.hasRestore(null, 8)).toBe(false);
  });

  it("SM15: resolveTarget — Anker hat Vorrang, Y ist Fallback", () => {
    const cfg = 8;
    // Anker vorhanden + aktuelle Ankerlage bekannt -> Anker-Pfad.
    let r = SM.resolveTarget({ anchor: "p202678", offset: 225, y: 9999, dpr: 1 },
                             1119, 1, 5000, 1000, cfg);
    expect(r.via).toBe("anchor");
    expect(r.y).toBe(1344);                       // 1119 + 225, im Bereich

    // Anker gesetzt, aber aktuelle Lage unbekannt (Element nicht gefunden) -> Y.
    r = SM.resolveTarget({ anchor: "p1", offset: 10, y: 777, dpr: 1 },
                         null, 1, 5000, 1000, cfg);
    expect(r.via).toBe("y");
    expect(r.y).toBe(777);

    // Kein Anker -> Y-Pfad mit Zoom-Skalierung + Clamp.
    r = SM.resolveTarget({ y: 1000, dpr: 1 }, null, 2, 5000, 1000, cfg);
    expect(r.via).toBe("y");
    expect(r.y).toBe(2000);                       // 1000 * (2/1)

    // Nichts Brauchbares -> none.
    r = SM.resolveTarget({ y: 2 }, null, 1, 5000, 1000, cfg);
    expect(r.via).toBe("none");

    // Anker-Ziel wird geklemmt.
    r = SM.resolveTarget({ anchor: "p9", offset: 99999, y: 0 }, 4000, 1, 5000, 1000, cfg);
    expect(r.via).toBe("anchor");
    expect(r.y).toBe(4000);                       // max = 5000-1000
  });
});

describe("ScrollMemory — Instanz + localStorage-Rundlauf", () => {
  const SM = loadClass();

  it("SM08: record/saveCurrent schreibt und lookup liest", () => {
    const storage = fakeStorage();
    const sm = new SM({ win: fakeWin(1234, 1), storage });
    sm._currentUrl = "/forum/viewtopic.php?id=42";
    sm.saveCurrent("test");                        // ohne DOM: kein Anker -> Y
    const got = sm.lookup("/forum/viewtopic.php?id=42");
    expect(got).not.toBeNull();
    expect(got.y).toBe(1234);
    expect(got.dpr).toBe(1);
    expect(got.anchor).toBeUndefined();
  });

  it("SM09: Persistenz ueberlebt Neuerzeugung (Reload-Simulation)", () => {
    const storage = fakeStorage();
    const sm1 = new SM({ win: fakeWin(777, 1), storage });
    sm1._currentUrl = "/forum/index.php";
    sm1.saveCurrent("test");
    const sm2 = new SM({ win: fakeWin(0, 1), storage });
    const got = sm2.lookup("/forum/index.php");
    expect(got && got.y).toBe(777);
  });

  it("SM10: waehrend Restore (_restoring) wird NICHT gespeichert", () => {
    const storage = fakeStorage();
    const sm = new SM({ win: fakeWin(555, 1), storage });
    sm._currentUrl = "/forum/x";
    sm._restoring = true;
    sm.saveCurrent("test");
    expect(sm.lookup("/forum/x")).toBeNull();
  });

  it("SM11: LRU-Deckel beim Persistieren greift", () => {
    const storage = fakeStorage();
    const sm = new SM({ win: fakeWin(0, 1), storage, cfg: { MAX_ENTRIES: 2 } });
    sm._mem = {
      "/a": { y: 1, dpr: 1, t: 1 },
      "/b": { y: 2, dpr: 1, t: 3 },
      "/c": { y: 3, dpr: 1, t: 2 },
    };
    sm._persist();
    const reloaded = new SM({ win: fakeWin(0, 1), storage, cfg: { MAX_ENTRIES: 2 } });
    expect(Object.keys(reloaded._mem).sort()).toEqual(["/b", "/c"]);
  });

  it("SM16: 471er-Datensatz (nur y) bleibt lesbar und restaurierbar", () => {
    const storage = fakeStorage();
    // Alt-Schema ohne anchor/offset direkt in den Storage legen.
    storage.setItem("aiw:scrollpos:v1", JSON.stringify({ "/forum/alt": { y: 640, dpr: 1, t: 5 } }));
    const sm = new SM({ win: fakeWin(0, 1), storage });
    const e = sm.lookup("/forum/alt");
    expect(e.y).toBe(640);
    expect(SM.hasRestore(e, 8)).toBe(true);
    // Ohne Anker -> Y-Pfad.
    const r = SM.resolveTarget(e, null, 1, 5000, 1000, 8);
    expect(r.via).toBe("y");
    expect(r.y).toBe(640);
  });
});

// ===========================================================================
// Build 688 — Vorrang des URI-Ankers vor der gemerkten Position
// Vorgang 74a95cba-21ba-4fc8-b882-afd44a887c17
// ---------------------------------------------------------------------------
// WARUM EIN EIGENER PRUEFSTAND UND KEIN jsdom:
//   Der Fehler liegt im ZUSAMMENSPIEL von Ankerlage, Leistenhoehe und dem
//   Settle-Warten. jsdom liefert fuer getBoundingClientRect() durchweg Nullen
//   und kennt window.scrollTo() nicht — die Rechnung waere damit nicht
//   pruefbar. Der Pruefstand unten stellt genau die vier Groessen ein, auf die
//   es ankommt (Ankerlage, Leistenhoehe, Seitenhoehe, gemerkte Y), und
//   protokolliert JEDEN scrollTo-Aufruf. Damit ist nachweisbar, WOHIN
//   gesprungen wird und WIE OFT.
// ===========================================================================

/**
 * Baut ein Fenster-Doppel mit steuerbarem DOM.
 * @param o.anker      { <id>: <clientTop> }  per getElementById auffindbar
 * @param o.namen      { <name>: <clientTop> } per getElementsByName auffindbar
 * @param o.leisten    { <id>: <hoehe> }      fixe Leisten am oberen Rand
 * @param o.ftFragment Wert von ForensicToolbar.state.get('fragment')
 * @param o.hash       window.location.hash
 */
function pruefstand(o) {
  o = o || {};
  const gescrollt = [];
  const rafQueue = [];
  const leisten = o.leisten === undefined ? { "forensic-toolbar": 62, "forensic-hintbar": 28 } : o.leisten;

  function machElement(clientTop) {
    return {
      getBoundingClientRect: () => ({ top: clientTop, bottom: clientTop, height: 10 }),
    };
  }
  function machLeiste(id) {
    // Leisten liegen gestapelt ab y=0: Unterkante = Summe der Hoehen bis dahin.
    const ids = Object.keys(leisten);
    let unten = 0;
    for (const k of ids) { unten += leisten[k]; if (k === id) break; }
    return { getBoundingClientRect: () => ({ top: unten - leisten[id], bottom: unten, height: leisten[id] }) };
  }

  const win = {
    scrollY: o.scrollY || 0,
    devicePixelRatio: 1,
    innerHeight: o.innerHeight || 1000,
    innerWidth: 1200,
    performance: { now: () => 0 },
    location: { pathname: "/forum/viewtopic.php", search: "?id=42", hash: o.hash || "" },
    history: {},
    requestAnimationFrame: (fn) => { rafQueue.push(fn); return rafQueue.length; },
    scrollTo: (x, y) => { gescrollt.push(y); win.scrollY = y; },
    addEventListener: () => {},
    removeEventListener: () => {},
    document: {
      readyState: "complete",                       // schaltet die load-Nachkorrektur ab
      documentElement: { scrollHeight: o.scrollHeight || 20000 },
      getElementById: (id) => {
        if (leisten && Object.prototype.hasOwnProperty.call(leisten, id)) return machLeiste(id);
        if (o.anker && Object.prototype.hasOwnProperty.call(o.anker, id)) return machElement(o.anker[id]);
        return null;
      },
      getElementsByName: (n) => {
        if (o.namen && Object.prototype.hasOwnProperty.call(o.namen, n)) return [machElement(o.namen[n])];
        return [];
      },
    },
  };
  if (o.ftFragment !== undefined) {
    win.ForensicToolbar = { state: { get: (k) => (k === "fragment" ? o.ftFragment : null) } };
  }

  // Laeuft die rAF-Warteschlange leer (Deckel gegen Endlosschleifen).
  function abarbeiten(maxRunden = 50) {
    let runden = 0;
    while (rafQueue.length && runden < maxRunden) {
      const fn = rafQueue.shift();
      fn(0);
      runden++;
    }
  }

  return { win, gescrollt, abarbeiten };
}

describe("ScrollMemory — URI-Anker (Build 688, Vorgang 74a95cba)", () => {
  const SM = loadClass();

  it("SM17: normalizeFragment entfernt '#' und weist Leeres ab", () => {
    expect(SM.normalizeFragment("#p12345")).toBe("p12345");
    expect(SM.normalizeFragment("p12345")).toBe("p12345");
    expect(SM.normalizeFragment("#")).toBeNull();
    expect(SM.normalizeFragment("")).toBeNull();
    expect(SM.normalizeFragment(null)).toBeNull();
    expect(SM.normalizeFragment(undefined)).toBeNull();
    expect(SM.normalizeFragment(42)).toBeNull();
  });

  it("SM18: fragmentEntry baut den Ersatzdatensatz (offset erst beim Anwenden)", () => {
    expect(SM.fragmentEntry("#p7")).toEqual({ anchor: "p7", offset: 0, fromFragment: true });
    expect(SM.fragmentEntry("beitrag-oben")).toEqual({ anchor: "beitrag-oben", offset: 0, fromFragment: true });
    expect(SM.fragmentEntry("#")).toBeNull();
  });

  it("SM19: anchorUsable — Positivliste gilt fuer gemerkte, NICHT fuer URI-Anker", () => {
    // Gemerkter Datensatz: enge Positivliste bleibt in Kraft (Beleg Build 473).
    expect(SM.anchorUsable({ anchor: "p12345" })).toBe(true);
    expect(SM.anchorUsable({ anchor: "_vt_ab12" })).toBe(false);
    // URI-Anker: ausdruecklich benannt, deshalb ohne Positivliste.
    expect(SM.anchorUsable({ anchor: "_vt_ab12", fromFragment: true })).toBe(true);
    expect(SM.anchorUsable({ anchor: "kapitel-3", fromFragment: true })).toBe(true);
    // Ohne Anker bleibt es bei false.
    expect(SM.anchorUsable({ fromFragment: true })).toBe(false);
    expect(SM.anchorUsable(null)).toBe(false);
  });

  it("SM20: resolveTarget meldet via='fragment' und faellt NICHT auf y zurueck", () => {
    const e = { anchor: "p999", offset: -90, fromFragment: true };
    const r = SM.resolveTarget(e, 4000, 1, 20000, 1000, 8);
    expect(r.via).toBe("fragment");
    expect(r.y).toBe(3910);                       // 4000 - 90 (Leistenhoehe)
    // Anker im DOM nicht auffindbar -> 'none'. Der Ersatzdatensatz traegt
    // bewusst kein y; die Entscheidung gegen die gemerkte Position ist
    // bereits in _onPageLoaded gefallen und wird hier nicht zurueckgedreht.
    const r2 = SM.resolveTarget(e, null, 1, 20000, 1000, 8);
    expect(r2.via).toBe("none");
  });

  it("SM21: hasRestore/resolveTarget fuer gemerkte Datensaetze unveraendert (Regression 473)", () => {
    expect(SM.hasRestore({ anchor: "p1", offset: 10, y: 0 }, 8)).toBe(true);
    expect(SM.hasRestore({ anchor: "_vt_x", y: 3 }, 8)).toBe(false);
    const r = SM.resolveTarget({ anchor: "p202678", offset: 225, y: 9999, dpr: 1 },
                               1119, 1, 5000, 1000, 8);
    expect(r.via).toBe("anchor");
    expect(r.y).toBe(1344);
  });

  it("SM22: URI-Anker schlaegt die gemerkte Position (der gemeldete Fehler)", () => {
    const { win, gescrollt, abarbeiten } = pruefstand({
      ftFragment: "p335445",
      anker: { p335445: 4000 },                    // clientTop bei scrollY=0 -> absTop 4000
    });
    const sm = new SM({ win, storage: fakeStorage() });
    sm._mem["/forum/viewtopic.php?id=42"] = { y: 12345, dpr: 1, t: 1 };   // alter Besuch

    sm._onPageLoaded({ url: "/forum/viewtopic.php?id=42" });
    abarbeiten();

    // Genau EINE Bewegung, und zwar zum URI-Anker abzueglich der Leisten
    // (62 + 28 = 90). Die gemerkten 12345 werden NICHT angefahren.
    expect(gescrollt).toEqual([3910]);
    expect(gescrollt).not.toContain(12345);
  });

  it("SM23: tote Sprungmarke -> gemerkte Position gilt weiter", () => {
    const { win, gescrollt, abarbeiten } = pruefstand({
      ftFragment: "p999999",                       // im DOM nicht vorhanden
      anker: {},
    });
    const sm = new SM({ win, storage: fakeStorage() });
    sm._mem["/forum/viewtopic.php?id=42"] = { y: 12345, dpr: 1, t: 1 };

    sm._onPageLoaded({ url: "/forum/viewtopic.php?id=42" });
    abarbeiten();

    expect(gescrollt).toEqual([12345]);
  });

  it("SM24: ohne URI-Anker bleibt der Weg von Build 473 unveraendert", () => {
    const { win, gescrollt, abarbeiten } = pruefstand({
      ftFragment: null,
      anker: { p202678: 1119 },
    });
    const sm = new SM({ win, storage: fakeStorage() });
    sm._mem["/forum/viewtopic.php?id=42"] = { y: 9999, dpr: 1, t: 1, anchor: "p202678", offset: 225 };

    sm._onPageLoaded({ url: "/forum/viewtopic.php?id=42" });
    abarbeiten();

    expect(gescrollt).toEqual([1344]);              // 1119 + 225, Anker-Pfad ohne Leistenabzug
  });

  it("SM25: Reload-Fall — Anker kommt aus location.hash, wenn der Zustand leer ist", () => {
    // Beleg: toolbar.js Z. 8393 laedt die Startseite ohne Hash; der Server
    // sieht das Fragment also nie. Das Adressfeld traegt es weiterhin.
    const { win, gescrollt, abarbeiten } = pruefstand({
      ftFragment: null,
      hash: "#p777",
      anker: { p777: 2000 },
    });
    const sm = new SM({ win, storage: fakeStorage() });
    sm._mem["/forum/viewtopic.php?id=42"] = { y: 500, dpr: 1, t: 1 };

    sm._onPageLoaded({ url: "/forum/viewtopic.php?id=42" });
    abarbeiten();

    expect(gescrollt).toEqual([1910]);              // 2000 - 90
  });

  it("SM26: der gemerkte Datensatz wird durch den Vorrang NICHT veraendert", () => {
    const { win, abarbeiten } = pruefstand({
      ftFragment: "p42",
      anker: { p42: 3000 },
    });
    const storage = fakeStorage();
    const sm = new SM({ win, storage });
    const vorher = { y: 777, dpr: 1, t: 5, anchor: "p1", offset: 12 };
    sm._mem["/forum/viewtopic.php?id=42"] = vorher;

    sm._onPageLoaded({ url: "/forum/viewtopic.php?id=42" });
    abarbeiten();

    expect(sm.lookup("/forum/viewtopic.php?id=42")).toEqual(vorher);
  });

  it("SM27: Sprungmarken als <a name> und in prozentkodierter Form werden gefunden", () => {
    // Mehrsprachiges Forum (Fallerkenntnis 2): Sprungmarken koennen
    // Nicht-ASCII-Zeichen tragen und erscheinen im Adressfeld kodiert.
    const { win, gescrollt, abarbeiten } = pruefstand({
      hash: "#Gr%C3%BCsse",
      namen: { "Grüsse": 1500 },
      ftFragment: null,
    });
    const sm = new SM({ win, storage: fakeStorage() });
    sm._mem["/forum/viewtopic.php?id=42"] = { y: 8000, dpr: 1, t: 1 };

    sm._onPageLoaded({ url: "/forum/viewtopic.php?id=42" });
    abarbeiten();

    expect(gescrollt).toEqual([1410]);              // 1500 - 90
  });

  it("SM28: Nutzlast des Ereignisses hat Vorrang vor Zustand und Adressfeld", () => {
    const { win, gescrollt, abarbeiten } = pruefstand({
      ftFragment: "p111",
      hash: "#p222",
      anker: { p111: 1000, p222: 2000, p333: 3000 },
    });
    const sm = new SM({ win, storage: fakeStorage() });
    sm._onPageLoaded({ url: "/forum/viewtopic.php?id=42", fragment: "p333" });
    abarbeiten();
    expect(gescrollt).toEqual([2910]);              // 3000 - 90
  });
});
