/**
 * tests/unit/test_cockpit_modules.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Baustein-Module (W1), FRONTEND (Build 427)
 *
 * Testsuite fuer management/server/static/cockpit_modules.js. Testet den ECHTEN
 * Code (readFileSync + JSDOM, window.AIWCockpitModules) — reine Funktionen UND
 * das DOM-Rendering inkl. Vorschau/Save.
 *
 * MO01 — API verfuegbar (reine + DOM-Funktionen); ROLES hat 6 Eintraege.
 * MO02 — roleLabel / moduleLabel.
 * MO03 — sortModules: nach role/sort_order/key, mutiert nicht.
 * MO04 — isValidKey: Spiegel der Server-Regel.
 * MO05 — buildPayload: trimmt key/title/topic; body NICHT; sort_order Zahl.
 * MO06 — summaryText / errorsText.
 * MO07 — renderModules: Liste (sortiert) + Klick fuellt Formular.
 * MO08 — Vorschau-Button ruft onDryRun mit Payload (inkl. body).
 * MO09 — Speichern-Button ruft onSave mit Payload.
 * MO10 — renderDryRun: Fehler (rot) vs. OK mit Platzhalter-Zusammenfassung (gruen).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_modules.js",
  "utf-8"
);

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body><div id='aiw-main'></div></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api(win) { return (win || _ctx()).AIWCockpitModules; }

function _data() {
  return {
    count: 2,
    modules: [
      { id: 2, module_key: "body.aktiv", title: "Aktivitaet", description: "",
        role: "body", topic: "Aktivitaet", body: "Text {{a:x}}.", sort_order: 1,
        is_active: 1, created_by: "red01", created_at: 1, updated_at: 1 },
      { id: 1, module_key: "intro.std", title: "Standard-Einleitung",
        description: "d", role: "intro", topic: "Allgemein",
        body: "Guten Tag {{a:username}}.", sort_order: 1,
        is_active: 1, created_by: "red01", created_at: 1, updated_at: 1 },
    ],
  };
}

describe("cockpit_modules", () => {
  it("MO01 API verfuegbar", () => {
    const api = _api();
    ["roleLabel", "moduleLabel", "sortModules", "isValidKey", "buildPayload",
     "summaryText", "errorsText", "renderModules", "renderDryRun",
     "dryRunError", "saved", "saveError", "cleanup"].forEach((fn) => {
      expect(typeof api[fn]).toBe("function");
    });
    expect(api.ROLES.length).toBe(6);
  });

  it("MO02 Labels", () => {
    const api = _api();
    expect(api.roleLabel("legal")).toContain("legal");
    expect(api.roleLabel("xyz")).toBe("xyz");
    expect(api.moduleLabel({ module_key: "a.b", title: "T" })).toBe("T (a.b)");
    expect(api.moduleLabel({ module_key: "k", title: "" })).toBe("k");
  });

  it("MO03 sortModules mutiert nicht", () => {
    const api = _api();
    const input = _data().modules;
    const out = api.sortModules(input);
    // role 'body' < 'intro' -> body.aktiv zuerst.
    expect(out.map((x) => x.module_key)).toEqual(["body.aktiv", "intro.std"]);
    expect(input.map((x) => x.module_key)).toEqual(["body.aktiv", "intro.std"]);
    expect(api.sortModules(undefined)).toEqual([]);
  });

  it("MO04 isValidKey", () => {
    const api = _api();
    expect(api.isValidKey("intro.std-1_x")).toBe(true);
    expect(api.isValidKey("hat leer")).toBe(false);
    expect(api.isValidKey("")).toBe(false);
  });

  it("MO05 buildPayload", () => {
    const api = _api();
    const p = api.buildPayload({
      module_key: "  k ", title: " T ", description: "d", role: "legal",
      topic: " Thema ", body: "  Text mit Rand  ", sort_order: "3",
    });
    expect(p.module_key).toBe("k");
    expect(p.title).toBe("T");
    expect(p.topic).toBe("Thema");
    expect(p.role).toBe("legal");
    // body NICHT getrimmt (Freitext exakt erhalten).
    expect(p.body).toBe("  Text mit Rand  ");
    expect(p.sort_order).toBe(3);
  });

  it("MO06 summaryText / errorsText", () => {
    const api = _api();
    expect(api.summaryText([{ kind: "auto", count: 2 },
                           { kind: "mandatory", count: 1 }]))
      .toBe("auto×2, mandatory×1");
    expect(api.summaryText([])).toBe("");
    expect(api.errorsText(["a", "b"])).toBe("a; b");
    expect(api.errorsText([])).toBe("");
  });

  it("MO07 renderModules: Liste + Klick fuellt Formular", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    api.renderModules(main, _data(), {});
    const items = main.querySelectorAll(".aiw-mod-item");
    expect(items.length).toBe(2);
    expect(items[0].getAttribute("data-key")).toBe("body.aktiv");

    // Neu-Modus: key leer + editierbar.
    const keyField = main.querySelector(".aiw-mod-key");
    expect(keyField.value).toBe("");
    expect(keyField.disabled).toBe(false);

    // Klick laedt Baustein (key fix, role/body gesetzt).
    items[1].dispatchEvent(new win.Event("click"));
    expect(keyField.value).toBe("intro.std");
    expect(keyField.disabled).toBe(true);
    expect(main.querySelector(".aiw-mod-role").value).toBe("intro");
    expect(main.querySelector(".aiw-mod-bodytext").value).toContain(":username");
    expect(items[1].classList.contains("is-active")).toBe(true);
  });

  it("MO08 Vorschau-Button ruft onDryRun mit Payload", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    let seen = null;
    api.renderModules(main, _data(), {
      onDryRun: function (payload) { seen = payload; },
    });
    main.querySelector(".aiw-mod-key").value = "neu.key";
    main.querySelector(".aiw-mod-title").value = "Neu";
    main.querySelector(".aiw-mod-topic").value = "Thema";
    main.querySelector(".aiw-mod-bodytext").value = "Hallo {{a:x}} {{m:y}}";
    main.querySelector(".aiw-mod-drybtn").dispatchEvent(new win.Event("click"));
    expect(seen).toBeTruthy();
    expect(seen.module_key).toBe("neu.key");
    expect(seen.body).toContain("{{a:x}}");
  });

  it("MO09 Speichern-Button ruft onSave mit Payload", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    let saved = null;
    api.renderModules(main, _data(), {
      onSave: function (payload) { saved = payload; },
    });
    main.querySelector(".aiw-mod-key").value = "s.key";
    main.querySelector(".aiw-mod-title").value = "S";
    main.querySelector(".aiw-mod-topic").value = "T";
    main.querySelector(".aiw-mod-bodytext").value = "Body";
    main.querySelector(".aiw-mod-save").dispatchEvent(new win.Event("click"));
    expect(saved).toBeTruthy();
    expect(saved.module_key).toBe("s.key");
    expect(saved.body).toBe("Body");
  });

  it("MO10 renderDryRun: Fehler vs. OK mit Zusammenfassung", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    api.renderModules(main, _data(), {});
    api.renderDryRun({ ok: false, errors: ["body fehlt."] });
    let dry = main.querySelector(".aiw-mod-dry");
    expect(dry.classList.contains("is-err")).toBe(true);
    api.renderDryRun({ ok: true, errors: [],
      summary: [{ kind: "auto", count: 2 }, { kind: "mandatory", count: 1 }] });
    dry = main.querySelector(".aiw-mod-dry");
    expect(dry.classList.contains("is-ok")).toBe(true);
    expect(dry.textContent).toContain("auto×2, mandatory×1");
  });

  // --- Browser-Zwischenspeicher (Build 488) -----------------------------
  it("MO11 Eingaben werden im localStorage gesichert", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderModules(main, _data(), {});
    const key = main.querySelector(".aiw-mod-key");
    key.value = "wip.key";
    key.dispatchEvent(new win.Event("input", { bubbles: true }));
    const bodyt = main.querySelector(".aiw-mod-bodytext");
    bodyt.value = "In Arbeit {{a:x}}";
    bodyt.dispatchEvent(new win.Event("input", { bubbles: true }));
    const raw = win.localStorage.getItem(api.DRAFT_KEY);
    expect(raw).toBeTruthy();
    const d = JSON.parse(raw);
    expect(d.fields.module_key).toBe("wip.key");
    expect(d.fields.body).toBe("In Arbeit {{a:x}}");
  });

  it("MO12 Entwurf wird beim erneuten Betreten wiederhergestellt", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderModules(main, _data(), {});
    const bodyt = main.querySelector(".aiw-mod-bodytext");
    bodyt.value = "Erhaltener Text";
    bodyt.dispatchEvent(new win.Event("input", { bubbles: true }));
    api.cleanup();
    api.renderModules(main, _data(), {});
    expect(main.querySelector(".aiw-mod-bodytext").value).toBe("Erhaltener Text");
  });

  it("MO13 erfolgreiches Speichern verwirft den Zwischenspeicher", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.getElementById("aiw-main");
    win.localStorage.clear();
    api.renderModules(main, _data(), {});
    const title = main.querySelector(".aiw-mod-title");
    title.value = "X";
    title.dispatchEvent(new win.Event("input", { bubbles: true }));
    expect(win.localStorage.getItem(api.DRAFT_KEY)).toBeTruthy();
    api.saved({ created: true, target_id: "m.x" });
    expect(win.localStorage.getItem(api.DRAFT_KEY)).toBeNull();
  });
});

describe("Bausteinmodule — module_key nachtragen (Build 565)", () => {
  const _win = () => {
    const { JSDOM } = require("jsdom");
    const { readFileSync } = require("fs");
    const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
      runScripts: "dangerously", url: "http://localhost",
    });
    dom.window.eval(
      readFileSync("management/server/static/cockpit_modules.js", "utf-8"));
    return dom.window;
  };

  // MK01 --------------------------------------------------------------------
  it("MK01: schluesselVorschlag baut eine zulaessige Kennung aus dem Titel", () => {
    const api = _win().AIWCockpitModules;
    expect(api.schluesselVorschlag("Tatvorwurf", "intro"))
      .toBe("intro.tatvorwurf");
    // Umlaute werden AUSGESCHRIEBEN, nicht geloescht: sonst fielen
    // "Anhoerung" und "Anhrung" zusammen.
    expect(api.schluesselVorschlag("Anhörung des Beschuldigten", "legal"))
      .toBe("legal.anhoerung.des.beschuldigten");
    expect(api.schluesselVorschlag("Maßnahme", "body")).toBe("body.massnahme");
    // Nur unzulaessige Zeichen -> kein Vorschlag, statt eines Schluessels
    // aus lauter Punkten.
    expect(api.schluesselVorschlag("!!!", "intro")).toBe("");
    expect(api.schluesselVorschlag("", "intro")).toBe("");
  });

  // MK02 --------------------------------------------------------------------
  it("MK02: der Vorschlag haelt den erlaubten Zeichenraum ein", () => {
    const api = _win().AIWCockpitModules;
    const KEY_RE = /^[A-Za-z0-9._-]+$/;
    ["Tatvorwurf", "Anhörung des Beschuldigten", "Maßnahme 3 (Teil B)",
     "Schluss/Ausblick"].forEach((t) => {
      const v = api.schluesselVorschlag(t, "intro");
      expect(KEY_RE.test(v)).toBe(true);
      // Keine doppelten Punkte und keine Randpunkte.
      expect(v).not.toMatch(/\.\./);
      expect(v).not.toMatch(/^\.|\.$/);
    });
  });

  // MK03 --------------------------------------------------------------------
  it("MK03: buildPayload sendet die id nur im Nachtragsfall", () => {
    const api = _win().AIWCockpitModules;
    const ohne = api.buildPayload({ module_key: "a.b", title: "T",
                                    role: "intro", topic: "X", body: "Y" });
    expect(ohne.id).toBeUndefined();

    const mit = api.buildPayload({ id: 7, module_key: "a.b", title: "T",
                                   role: "intro", topic: "X", body: "Y" });
    expect(mit.id).toBe(7);
    // Leerwerte sind KEIN Nachtrag — sonst ginge eine id="" hinaus und der
    // Server muesste raten, was gemeint ist.
    expect(api.buildPayload({ id: "", module_key: "a.b" }).id).toBeUndefined();
    expect(api.buildPayload({ id: null, module_key: "a.b" }).id)
      .toBeUndefined();
  });
});

describe("Bausteinmodule — Zustand des Schlüsselfeldes (Build 575)", () => {
  const DRAFT_KEY = "aiw.modules.draft.v1";

  /** Datensatz mit einem Altbaustein OHNE Kennung. */
  function _mitAltbaustein() {
    return {
      count: 2,
      modules: [
        { id: 7, module_key: null, title: "Alter Baustein", description: "",
          role: "intro", topic: "Einleitung", body: "Text", sort_order: 0,
          is_active: 1, created_by: "alt", created_at: 1, updated_at: 1 },
        { id: 8, module_key: "intro.std", title: "Standard", description: "",
          role: "intro", topic: "Einleitung", body: "Text", sort_order: 1,
          is_active: 1, created_by: "red", created_at: 1, updated_at: 1 },
      ],
    };
  }

  function _feld(main) { return main.querySelector(".aiw-mod-key"); }
  function _hinweis(main) {
    return main.querySelector(".aiw-mod-keyhinweis");
  }

  // MK04 --------------------------------------------------------------------
  it("MK04: frisches Formular — Feld offen und leer", () => {
    const win = _ctx();
    const main = win.document.getElementById("aiw-main");
    _api(win).renderModules(main, _mitAltbaustein(), {});
    const f = _feld(main);
    expect(f).toBeTruthy();
    // Der von mc gemeldete Zustand war GESPERRT UND LEER — genau das darf es
    // nicht geben: eine Sperre, hinter der nichts steht.
    expect(f.disabled).toBe(false);
    expect(f.value).toBe("");
  });

  // MK05 --------------------------------------------------------------------
  it("MK05: Baustein MIT Kennung sperrt, Altbaustein OHNE oeffnet", () => {
    const win = _ctx();
    const main = win.document.getElementById("aiw-main");
    _api(win).renderModules(main, _mitAltbaustein(), {});
    const eintraege = main.querySelectorAll(".aiw-mod-item");
    expect(eintraege.length).toBe(2);

    // Der Altbaustein (ohne Kennung) -> Feld OFFEN, mit Vorschlag.
    eintraege[0].dispatchEvent(new win.Event("click", { bubbles: true }));
    let f = _feld(main);
    expect(f.disabled).toBe(false);
    expect(f.value).toBe("intro.alter.baustein");
    expect(_hinweis(main).textContent).toContain("ENDGUELTIG");

    // Der Baustein mit Kennung -> Feld FEST, Wert die Kennung.
    eintraege[1].dispatchEvent(new win.Event("click", { bubbles: true }));
    f = _feld(main);
    expect(f.disabled).toBe(true);
    expect(f.value).toBe("intro.std");
    expect(_hinweis(main).textContent).toContain("fest");
  });

  // MK06 --------------------------------------------------------------------
  it("MK06: ALTENTWURF erzeugt keine Sperre ohne Inhalt", () => {
    const win = _ctx();
    // Ein Entwurf aus der Zeit VOR Build 565: selKey traegt die ZEICHENKETTE
    // "null" (damals String(m.module_key)), das Schluesselfeld ist leer, und
    // es gibt weder selId noch nachtragId. Beim Wiederherstellen ergab das
    // genau das von mc gemeldete Bild: disabled und leer.
    win.localStorage.setItem(DRAFT_KEY, JSON.stringify({
      v: 1, selKey: "null",
      fields: { module_key: "", title: "Alter Baustein", description: "",
                role: "intro", topic: "Einleitung", body: "Text",
                sort_order: 0 },
    }));
    const main = win.document.getElementById("aiw-main");
    _api(win).renderModules(main, _mitAltbaustein(), {});

    const f = _feld(main);
    expect(f.value).toBe("");
    // DIE KERNAUSSAGE: kein gesperrtes Leerfeld mehr.
    expect(f.disabled).toBe(false);
  });

  // MK07 --------------------------------------------------------------------
  it("MK07: Altentwurf mit bekannter Zeile warnt vor falscher Zuordnung", () => {
    const win = _ctx();
    // Hier ist selId bekannt, nachtragId aber nicht — Speichern wuerde eine
    // ZWEITE Zeile anlegen statt die alte zu ergaenzen. Das muss dastehen.
    win.localStorage.setItem(DRAFT_KEY, JSON.stringify({
      v: 1, selKey: null, selId: 7,
      fields: { module_key: "", title: "Alter Baustein", description: "",
                role: "intro", topic: "Einleitung", body: "Text",
                sort_order: 0 },
    }));
    const main = win.document.getElementById("aiw-main");
    _api(win).renderModules(main, _mitAltbaustein(), {});

    expect(_feld(main).disabled).toBe(false);
    const h = _hinweis(main).textContent;
    expect(h).toContain("erneut anklicken");
    expect(_hinweis(main).className).toContain("aiw-mod-keyhinweis-warn");
  });
});

/* ===========================================================================
 * BUILD 652 (Ticket 3508ad71) — VORSCHAU IN EIGENER SPALTE, DAUERHAFT.
 *
 * Gegenstand: die Vorschau klebte bis Build 651 unten an der Eingabemaske
 * (_vorschauAufbauen(form) haengte Kopf und Behaelter an das Formular). Sie
 * steht jetzt in einer dritten Rasterspalte rechts daneben.
 *
 * WAS DIESE FAELLE PRUEFEN KOENNEN UND WAS NICHT: JSDOM wertet KEIN CSS aus
 * und kennt keine Medienabfragen. Ob die Spalte auf einem 1000px breiten
 * Fenster tatsaechlich umbricht, laesst sich hier NICHT messen - das ist in
 * der VM am Bildschirm zu pruefen. Belegbar ist zweierlei, und das wird auch
 * belegt: (a) der DOM-Aufbau, den die Rasterregel voraussetzt, und (b) dass
 * die Umbruchregel im Stylesheet ueberhaupt steht. (b) ist eine schwache,
 * aber ehrliche Sperre: sie faengt das Loeschen der Regel, nicht ihren
 * Wirkungsgrad. Das wird hier gesagt und nicht als Vollpruefung ausgegeben.
 *
 * LY01 — Vorschau haengt in einer EIGENEN Spalte, nicht mehr im Formular.
 * LY02 — sie ist ohne Zutun sichtbar (Ticket: "dauerhaft eingeblendet").
 * LY03 — der Schalter klappt zu und wieder auf und MERKT SICH DEN STAND.
 * LY04 — die Umbruchregel steht im Stylesheet (Rasterbereiche + @media).
 * =========================================================================== */
describe("Bausteinmodule — Vorschau-Spalte (Build 652)", () => {
  const _main = (win) => win.document.getElementById("aiw-main");
  const _spalte = (main) => main.querySelector(".aiw-mod-vorschaucol");
  const _schalter = (main) => main.querySelector("#aiw-mod-vorschau-schalter");
  const _host = (main) => main.querySelector("#aiw-mod-vorschau");

  // LY01 --------------------------------------------------------------------
  it("LY01: die Vorschau steht in einer eigenen Spalte, nicht im Formular", () => {
    const win = _ctx();
    const main = _main(win);
    _api(win).renderModules(main, _data(), {});

    const spalte = _spalte(main);
    const host = _host(main);
    const form = main.querySelector(".aiw-mod-form");

    expect(spalte).toBeTruthy();
    expect(host).toBeTruthy();
    // DIE KERNAUSSAGE: der Behaelter haengt an der Spalte, NICHT am Formular.
    // Mit der Fassung aus Build 651 faellt genau diese Zeile um.
    expect(spalte.contains(host)).toBe(true);
    expect(form.contains(host)).toBe(false);

    // Alle drei Spalten sind Kinder desselben Rasters, in der Reihenfolge
    // Liste - Maske - Vorschau. Die Rasterbereiche ordnen sie zwar selbst,
    // aber die Vorlese-Reihenfolge folgt dem DOM, und die soll stimmen.
    const raster = main.querySelector(".aiw-mod-body");
    const kinder = Array.prototype.map.call(raster.children,
      (el) => el.className.split(" ")[0]);
    expect(kinder).toEqual([
      "aiw-mod-listcol", "aiw-mod-form", "aiw-mod-vorschaucol",
    ]);
  });

  // LY02 --------------------------------------------------------------------
  it("LY02: die Vorschau ist ohne Zutun sichtbar", () => {
    const win = _ctx();
    const main = _main(win);
    _api(win).renderModules(main, _data(), {});

    expect(_host(main).hidden).toBe(false);
    expect(_spalte(main).className).not.toContain("ist-zu");
    // Der Schalter sagt, was er tut - nicht, was gerade zu sehen ist.
    expect(_schalter(main).textContent).toBe("Vorschau ausblenden");
    expect(_schalter(main).getAttribute("aria-expanded")).toBe("true");
  });

  // LY03 --------------------------------------------------------------------
  it("LY03: der Schalter klappt zu, wieder auf und merkt sich den Stand", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _main(win);
    api.renderModules(main, _data(), {});

    _schalter(main).click();
    expect(_host(main).hidden).toBe(true);
    expect(_spalte(main).className).toContain("ist-zu");
    expect(_schalter(main).textContent).toBe("Vorschau einblenden");
    expect(_schalter(main).getAttribute("aria-expanded")).toBe("false");
    expect(win.localStorage.getItem(api.VORSCHAU_KEY)).toBe("0");

    _schalter(main).click();
    expect(_host(main).hidden).toBe(false);
    expect(win.localStorage.getItem(api.VORSCHAU_KEY)).toBe("1");

    // DER EIGENTLICHE PUNKT: neu aufgebaut kommt der gemerkte Stand zurueck.
    // Bis Build 651 war das ausdruecklich NICHT so ("ein Moment, keine
    // Vorliebe") - deshalb steht es hier als Fall und nicht als Zusicherung
    // im Kommentar.
    _schalter(main).click();               // -> zu, gemerkt
    api.renderModules(main, _data(), {});
    expect(_host(main).hidden).toBe(true);
    expect(_schalter(main).textContent).toBe("Vorschau einblenden");
  });

  // LY04 --------------------------------------------------------------------
  it("LY04: die Umbruchregel steht im Stylesheet", () => {
    const css = readFileSync(
      "management/server/static/cockpit.css", "utf-8");

    // Das Raster selbst.
    expect(css).toMatch(/\.aiw-mod-body\s*\{[^}]*display:\s*grid/);
    expect(css).toMatch(/grid-template-areas: "liste liste"/);
    expect(css).toMatch(/\.aiw-mod-vorschaucol\s*\{[^}]*grid-area:\s*vorschau/);

    // Und die beiden Umbruchstufen. Ohne sie ginge die Spalte auf schmalen
    // Anzeigen nicht unter die Maske, sondern quetschte sie zusammen - genau
    // der Zustand, den das Ticket ausschliesst.
    expect(css).toContain("@media (max-width: 1280px)");
    expect(css).toContain("@media (max-width: 900px)");
    // Build 653 hat die Anordnung geaendert: die Liste liegt jetzt OBEN,
    // darunter Maske und Vorschau. Der Umbruch stapelt alle drei.
    expect(css).toMatch(/"liste"\s*\n\s*"maske"\s*\n\s*"vorschau"/);
  });
});

/* ===========================================================================
 * BUILD 653 (Ticket d60e893a) — DIE LISTE ALS TABELLE.
 *
 * Gegenstand: die linke Spalte war eine Kette von Schaltflaechen ohne
 * Sortierung, Filter oder Hoehenbegrenzung. Sie ist jetzt eine Tabelle
 * (AIWTableKit + Tabulator) im oberen Bereich.
 *
 * WARUM EIN STUB UND KEIN ECHTER TABULATOR: die Bibliothek liegt als
 * vendor-Bundle vor und braucht ein Layout, das JSDOM nicht liefert. Geprueft
 * wird deshalb DIE VERDRAHTUNG - welche Zeilen, welche Spalten, welche
 * Optionen und welcher Zeilenklick ankommen. Dass Tabulator daraus eine
 * Tabelle malt, ist seine Sache und in der VM zu sehen.
 *
 * TB01 — moduleRows: abgeleitete Felder, Altzeilen als _ohneKennung.
 * TB02 — zeilenKennung: module_key, sonst '#id:<n>'. DER ZWEITE ADRESSWEG.
 * TB03 — die Tabelle bekommt Zeilen, Blaetterung und Hoechstzahl.
 * TB04 — Zeilenklick fuellt die Maske; Nachtragsmodus bleibt erreichbar.
 * TB05 — ohne Tabulator: Rueckfall auf die Schaltflaechenliste, MIT Hinweis.
 * TB06 — "Nur ohne Kennung" setzt und entfernt genau einen Filter.
 * =========================================================================== */
describe("Bausteinmodule — Tabelle statt Liste (Build 653)", () => {
  const _tkSrc = readFileSync(
    "management/server/static/cockpit_tablekit.js", "utf-8");

  // Ein Tabulator, der sich merkt, was man ihm sagt. Er tut nichts, aber er
  // luegt auch nicht: jede Methode, die der Code aufruft, ist da.
  function _stub() {
    const gemacht = { filter: [], sort: [], headerFilter: [], events: {} };
    function Stub(container, opts) {
      this.container = container;
      this.opts = opts;
      gemacht.instanz = this;
      gemacht.opts = opts;
    }
    Stub.prototype.on = function (ev, fn) { gemacht.events[ev] = fn; };
    Stub.prototype.getRows = function () { return []; };
    Stub.prototype.getDataCount = function () {
      return (gemacht.opts && gemacht.opts.data) ? gemacht.opts.data.length : 0;
    };
    Stub.prototype.getSorters = function () { return []; };
    Stub.prototype.getHeaderFilters = function () { return []; };
    Stub.prototype.setHeaderFilterValue = function () {};
    Stub.prototype.setSort = function () {};
    Stub.prototype.getFilters = function () { return gemacht.filter.slice(); };
    Stub.prototype.setFilter = function (field, type, value) {
      gemacht.filter.push({ field, type, value });
    };
    Stub.prototype.removeFilter = function (field, type, value) {
      gemacht.filter = gemacht.filter.filter(
        (f) => !(f.field === field && f.type === type && f.value === value));
    };
    Stub.prototype.clearHeaderFilter = function () {};
    Stub.prototype.clearFilter = function () { gemacht.filter = []; };
    Stub.prototype.destroy = function () { gemacht.zerstoert = true; };
    return { Stub, gemacht };
  }

  // Kontext MIT dem Tabellenwerkzeug — wie im Browser, wo cockpit.html
  // cockpit_tablekit.js vor den Sichten laedt.
  function _ctxTk() {
    const dom = new JSDOM(
      "<!DOCTYPE html><html><body><div id='aiw-main'></div></body></html>",
      { runScripts: "dangerously", url: "http://localhost" });
    dom.window.eval(_tkSrc);
    dom.window.eval(_src);
    return dom.window;
  }

  const _mitAlt = () => ({
    count: 3,
    modules: _data().modules.concat([
      { id: 9, module_key: null, title: "Altbaustein ohne Kennung",
        description: "", role: "legal", topic: "Recht", body: "Alt.",
        sort_order: 0, is_active: 1, created_by: "red01",
        created_at: 1, updated_at: 1 },
    ]),
  });

  // TB01 --------------------------------------------------------------------
  it("TB01: moduleRows leitet die Anzeigefelder ab", () => {
    const api = _api();
    const rows = api.moduleRows(_mitAlt().modules);

    expect(rows.length).toBe(3);
    // Sortierung von sortModules bleibt gueltig: body < intro < legal.
    expect(rows.map((r) => r.role)).toEqual(["body", "intro", "legal"]);

    const alt = rows.find((r) => r.id === 9);
    expect(alt._ohneKennung).toBe(true);
    // KEINE LEERE ZELLE: eine leere Zelle sieht aus wie ein Anzeigefehler.
    expect(alt._kennungText).toBe("— ohne Kennung —");
    expect(alt._rolleText).toBe("Rechtliches (legal)");
    expect(alt._aktivText).toBe("ja");
    // Der ganze Datensatz bleibt in der Zeile — der Klick fuellt daraus.
    expect(alt.body).toBe("Alt.");

    const mit = rows.find((r) => r.id === 1);
    expect(mit._ohneKennung).toBe(false);
    expect(mit._kennungText).toBe("intro.std");

    // is_active === 0 ergibt 'nein', alles andere 'ja'.
    expect(api.moduleRows([{ id: 1, is_active: 0 }])[0]._aktivText).toBe("nein");
  });

  // TB02 --------------------------------------------------------------------
  it("TB02: zeilenKennung haelt BEIDE Adresswege offen", () => {
    const api = _api();
    // Der Regelfall.
    expect(api.zeilenKennung({ id: 3, module_key: "intro.a" })).toBe("intro.a");
    // Der Fall, der Ticket a1480978 ausgeloest hat: ohne Kennung MUSS die
    // Zeilen-id adressieren, sonst legt ein Speichern eine ZWEITE Zeile an.
    expect(api.zeilenKennung({ id: 3, module_key: null })).toBe("#id:3");
    expect(api.zeilenKennung({ id: 3, module_key: "" })).toBe("#id:3");
    // Ohne beides gibt es keine Adresse — und das wird gesagt, nicht geraten.
    expect(api.zeilenKennung({ module_key: null })).toBe(null);
    expect(api.zeilenKennung(null)).toBe(null);
  });

  // TB03 --------------------------------------------------------------------
  it("TB03: die Tabelle bekommt Zeilen, Spalten und Blaetterung", () => {
    const win = _ctxTk();
    const { Stub, gemacht } = _stub();
    win.AIWCockpitModules.renderModules(
      win.document.getElementById("aiw-main"), _mitAlt(), { Tabulator: Stub });

    expect(gemacht.instanz).toBeTruthy();
    expect(gemacht.opts.data.length).toBe(3);
    // Kennung zuerst: sie ist das Feld, ueber das Berichtsvorlagen
    // verweisen — und das Feld, das den Altzeilen fehlt.
    expect(gemacht.opts.columns[0].field).toBe("_kennungText");
    expect(gemacht.opts.columns.map((c) => c.field)).toContain("title");
    // Die Antwort des Tickets auf "unuebersichtlich": Blaetterung + index.
    expect(gemacht.opts.pagination).toBe("local");
    expect(gemacht.opts.paginationSize).toBe(15);
    expect(gemacht.opts.index).toBe("id");
    // height:false ist das dokumentierte Muster gegen abgeschnittene
    // Blaetterleisten — nicht Zufall, sondern Beleg aus cockpit_lectorate.js.
    expect(gemacht.opts.height).toBe(false);
    // Kein stiller Leerzustand.
    expect(String(gemacht.opts.placeholder)).toContain("Kein Baustein");
    // rowClick gehoert NICHT in die Konstruktoroptionen (Tabulator v6
    // ignoriert ihn dort lautlos) — das TableKit haengt ihn ueber .on() an.
    expect(gemacht.opts.rowClick).toBeUndefined();
    expect(typeof gemacht.events.rowClick).toBe("function");
  });

  // TB04 --------------------------------------------------------------------
  it("TB04: der Zeilenklick fuellt die Maske, auch bei Altzeilen", () => {
    const win = _ctxTk();
    const { Stub, gemacht } = _stub();
    const main = win.document.getElementById("aiw-main");
    win.AIWCockpitModules.renderModules(main, _mitAlt(), { Tabulator: Stub });

    const zeile = (d) => ({ getData: () => d, getElement: () => null });
    const alt = gemacht.opts.data.find((r) => r.id === 9);

    gemacht.events.rowClick({}, zeile(alt));
    expect(main.querySelector(".aiw-mod-title").value)
      .toBe("Altbaustein ohne Kennung");
    // DER PUNKT: der Nachtragsmodus muss ueber die Tabelle genauso
    // erreichbar bleiben wie ueber die alte Liste. Ohne Kennung ist das
    // Feld OFFEN und traegt einen Vorschlag — nie gesperrt und leer.
    const key = main.querySelector(".aiw-mod-key");
    expect(key.disabled).toBe(false);
    expect(key.value).toBe("legal.altbaustein.ohne.kennung");
    expect(main.querySelector(".aiw-mod-keyhinweis").textContent)
      .toContain("ENDGUELTIG");

    // Und der Regelfall: mit Kennung ist das Feld fest.
    gemacht.events.rowClick({},
      zeile(gemacht.opts.data.find((r) => r.id === 1)));
    expect(main.querySelector(".aiw-mod-key").value).toBe("intro.std");
    expect(main.querySelector(".aiw-mod-key").disabled).toBe(true);
  });

  // TB05 --------------------------------------------------------------------
  it("TB05: ohne Tabulator bleibt die Sicht BEDIENBAR", () => {
    const win = _ctxTk();
    const main = win.document.getElementById("aiw-main");
    // Kein Konstruktor — weder ueber opts noch am Fenster.
    win.AIWCockpitModules.renderModules(main, _mitAlt(), {});

    // Die alte Schaltflaechenliste tritt an ihre Stelle. Das ist KEIN
    // Schoenheitsfehler, den man hinnimmt: ueber die Liste wird AUSGEWAEHLT.
    // Ein blosser Hinweis mit Zeilenzahl (so macht es tabelleAufbauen fuer
    // reine Anzeigen) machte die Sicht unbedienbar.
    const items = main.querySelectorAll(".aiw-mod-item");
    expect(items.length).toBe(3);
    // KEIN STILLER AUSFALL: der Rueckfall sagt, dass er einer ist.
    const warn = main.querySelector(".aiw-mod-empty.ist-warnung");
    expect(warn).toBeTruthy();
    expect(warn.textContent).toContain("nicht verfügbar");
    expect(warn.textContent).toContain("3 Bausteine");

    // Und er funktioniert auch.
    items[0].click();
    expect(main.querySelector(".aiw-mod-title").value).toBeTruthy();
  });

  // TB06 --------------------------------------------------------------------
  it("TB06: 'Nur ohne Kennung' setzt und entfernt genau einen Filter", () => {
    const win = _ctxTk();
    const { Stub, gemacht } = _stub();
    const main = win.document.getElementById("aiw-main");
    win.AIWCockpitModules.renderModules(main, _mitAlt(), { Tabulator: Stub });

    const btn = main.querySelector(".aiw-mod-nurohne");
    expect(btn).toBeTruthy();
    expect(btn.getAttribute("aria-pressed")).toBe("false");

    btn.click();
    expect(gemacht.filter).toEqual([
      { field: "_ohneKennung", type: "=", value: true },
    ]);
    expect(btn.getAttribute("aria-pressed")).toBe("true");
    expect(btn.className).toContain("ist-an");

    btn.click();
    // removeFilter und NICHT clearFilter: die Kopffilter des Redakteurs
    // bleiben stehen. Deshalb wird hier auf LEER geprueft und nicht darauf,
    // dass irgendetwas geraeumt wurde.
    expect(gemacht.filter).toEqual([]);
    expect(btn.getAttribute("aria-pressed")).toBe("false");
  });
});
