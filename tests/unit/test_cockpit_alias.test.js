/**
 * tests/unit/test_cockpit_alias.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Aliasse (AP-2A/A1)
 *
 * Testsuite fuer management/server/static/cockpit_alias.js (Build 505).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitAlias) —
 * keine Logik-Duplikation (B4-S12: „gruen, aber tot" vermeiden).
 *
 * AS01 — API verfuegbar; KINDS_FALLBACK deckungsgleich mit der DDL-Menge.
 * AS02 — reine Helfer: entries/kinds/counts/countsText/kindLabel/statusClass.
 * AS03 — buildAddPayload: subject_id NUR bei vollstaendig ganzzahliger Eingabe
 *        ('47xy' -> null, NICHT 47 — sonst landete der Alias am falschen Konto).
 * AS04 — validateAdd deckt alle drei Pflichtfelder ab.
 * AS05 — leerer Katalog -> Platzhalter; Suchmodus hat einen EIGENEN Leertext;
 *        Formular nur mit canEdit.
 * AS06 — mit Eintraegen: Tabelle, Status-Klassen, Widerrufsgrund sichtbar,
 *        Aktionen statusabhaengig (aktiv: Ändern/Widerrufen; widerrufen:
 *        Zurücknehmen).
 * AS07 — Widerruf verlangt einen Grund: leeres Feld -> KEIN onRetract,
 *        stattdessen Fehlermeldung; mit Grund -> onRetract({alias_id, reason}).
 * AS08 — XSS: ein Alias mit Markup landet als TEXT, nicht als DOM.
 * AS09 — Ladefehler wird als FEHLER angezeigt, nicht als leerer Katalog
 *        (Grundregel 1).
 *
 * Version: v0.8.505 · Build: 505 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/cockpit_alias.js", "utf-8");

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api() {
  return _win().AIWCockpitAlias;
}
function _mount(win) {
  const el = win.document.createElement("div");
  win.document.body.appendChild(el);
  return el;
}
function _data(over) {
  return Object.assign(
    {
      entries: [
        {
          id: 1,
          subject_id: 4711,
          alias: "Panther",
          alias_norm: "panther",
          kind_code: "forenname",
          kind_label: "weiterer Forenname",
          basis: "Signatur in Post 12",
          note: null,
          is_active: true,
          retracted_reason: null,
          created_at: 1700000000,
          updated_at: 1700000100,
          audit_seq: 5,
          created_audit_seq: 5,
        },
        {
          id: 2,
          subject_id: 90210,
          alias: "Luchs",
          alias_norm: "luchs",
          kind_code: "handle",
          kind_label: "Handle/Nickname ausserhalb des Forums",
          basis: "",
          note: null,
          is_active: false,
          retracted_reason: "Verwechslung mit Konto 99",
          created_at: 1700000000,
          updated_at: 1700000200,
          audit_seq: 9,
          created_audit_seq: 6,
        },
      ],
      counts: { total: 2, aktiv: 1, widerrufen: 1, subjects: 1 },
      mode: "all",
      kinds: [
        { code: "forenname", label: "weiterer Forenname" },
        { code: "handle", label: "Handle/Nickname ausserhalb des Forums" },
      ],
    },
    over || {}
  );
}

describe("cockpit_alias.js (Build 505, AP-2A/A1)", () => {
  // AS01 ---------------------------------------------------------------------
  it("AS01: API verfuegbar, Fallback-Arten decken die DDL-Menge", () => {
    const api = _api();
    expect(typeof api.renderAlias).toBe("function");
    expect(typeof api.buildAddPayload).toBe("function");
    // Deckungsgleich mit ALIAS_KINDS (subject_alias_repo.py) und dem
    // CHECK in m022 — eine Auswahl, die der Server ablehnte, waere ein Bug.
    expect(api.KINDS_FALLBACK.map((k) => k.code)).toEqual([
      "forenname",
      "handle",
      "signatur",
      "kontakt",
      "sonstiges",
    ]);
  });

  // AS02 ---------------------------------------------------------------------
  it("AS02: reine Helfer sind robust gegen fehlende Felder", () => {
    const api = _api();
    expect(api.entries(null)).toEqual([]);
    expect(api.entries({ entries: "nope" })).toEqual([]);
    // Fehlt die Server-Liste, greift der Fallback (nie eine LEERE Auswahl).
    expect(api.kinds({}).length).toBe(5);
    expect(api.kinds({ kinds: [{ code: "x", label: "X" }] }).length).toBe(1);

    expect(api.counts(null)).toEqual({
      total: 0,
      aktiv: 0,
      widerrufen: 0,
      subjects: 0,
    });
    expect(api.countsText(_data())).toContain("1 aktiv");
    expect(api.countsText(_data())).toContain("1 widerrufen");

    expect(api.kindLabel("forenname")).toBe("weiterer Forenname");
    expect(api.kindLabel("gibtsnicht")).toBe("gibtsnicht");
    expect(api.statusClass(true)).toBe("aiw-alias-aktiv");
    expect(api.statusClass(false)).toBe("aiw-alias-widerrufen");
    expect(api.fmtTs(0)).toBe("—");
    expect(api.fmtTs("quatsch")).toBe("—");
  });

  // AS03 ---------------------------------------------------------------------
  it("AS03: buildAddPayload parst subject_id streng", () => {
    const api = _api();
    expect(api.buildAddPayload({ subject_id: "4711" }).subject_id).toBe(4711);
    expect(api.buildAddPayload({ subject_id: " 4711 " }).subject_id).toBe(4711);
    // Der entscheidende Fall: parseInt('47xy') waere 47 — ein FALSCHES Konto.
    expect(api.buildAddPayload({ subject_id: "47xy" }).subject_id).toBeNull();
    expect(api.buildAddPayload({ subject_id: "" }).subject_id).toBeNull();
    expect(api.buildAddPayload({}).subject_id).toBeNull();

    const b = api.buildAddPayload({
      subject_id: "1",
      alias: "  Panther  ",
      kind_code: "handle",
      basis: "  Fund  ",
      note: "   ",
    });
    expect(b.alias).toBe("Panther");
    expect(b.basis).toBe("Fund");
    // Leere Notiz wird weggelassen (der Server behandelt sie dann als null).
    expect("note" in b).toBe(false);

    const c = api.buildAddPayload({ subject_id: "1", note: " x " });
    expect(c.note).toBe("x");
  });

  // AS04 ---------------------------------------------------------------------
  it("AS04: validateAdd deckt alle Pflichtfelder ab", () => {
    const api = _api();
    expect(api.validateAdd(null)).toMatch(/subject_id/);
    expect(api.validateAdd({ subject_id: null })).toMatch(/subject_id/);
    expect(api.validateAdd({ subject_id: 1, alias: "" })).toMatch(/Alias/);
    expect(
      api.validateAdd({ subject_id: 1, alias: "P", kind_code: "" })
    ).toMatch(/Art/);
    expect(
      api.validateAdd({ subject_id: 1, alias: "P", kind_code: "handle" })
    ).toBeNull();
  });

  // AS05 ---------------------------------------------------------------------
  it("AS05: Leerbefund und Rechte-Abhaengigkeit des Formulars", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;

    const el1 = _mount(win);
    api.renderAlias(el1, { entries: [], counts: {} }, { doc: win.document });
    expect(el1.querySelector("table")).toBeNull();
    expect(el1.querySelector(".aiw-placeholder").textContent).toBe(
      "Noch kein Alias im Katalog."
    );
    // Ohne canEdit: kein Anlage-Formular, dafuer der Hinweis auf das Recht.
    expect(el1.querySelector("#aiw-alias-add")).toBeNull();
    expect(el1.querySelector(".aiw-alias-readonly")).toBeTruthy();

    // Im SUCHMODUS ist der Leerbefund eine ANDERE Aussage.
    const el2 = _mount(win);
    api.renderAlias(
      el2,
      { entries: [], counts: {} },
      { doc: win.document, query: "Panther" }
    );
    expect(el2.querySelector(".aiw-placeholder").textContent).toBe(
      "Kein Konto führt diesen Namen."
    );

    const el3 = _mount(win);
    api.renderAlias(
      el3,
      { entries: [], counts: {} },
      { doc: win.document, canEdit: true }
    );
    expect(el3.querySelector("#aiw-alias-add")).toBeTruthy();
    expect(el3.querySelector(".aiw-alias-readonly")).toBeNull();
  });

  // AS06 ---------------------------------------------------------------------
  it("AS06: Tabelle, Status-Klassen und statusabhaengige Aktionen", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    api.renderAlias(el, _data(), { doc: win.document, canEdit: true });

    const rows = el.querySelectorAll("tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0].className).toBe("aiw-alias-aktiv");
    expect(rows[1].className).toBe("aiw-alias-widerrufen");

    // Der Widerrufsgrund gehoert sichtbar in die Zeile.
    expect(rows[1].textContent).toContain("Verwechslung mit Konto 99");

    // Aktive Zeile: Ändern + Widerrufen, KEIN Zurücknehmen.
    expect(rows[0].querySelector(".aiw-alias-change")).toBeTruthy();
    expect(rows[0].querySelector(".aiw-alias-retract")).toBeTruthy();
    expect(rows[0].querySelector(".aiw-alias-reinstate")).toBeNull();
    // Widerrufene Zeile: nur Zurücknehmen.
    expect(rows[1].querySelector(".aiw-alias-reinstate")).toBeTruthy();
    expect(rows[1].querySelector(".aiw-alias-retract")).toBeNull();

    // Ohne canEdit gibt es gar keine Aktionen.
    const el2 = _mount(win);
    api.renderAlias(el2, _data(), { doc: win.document });
    expect(el2.querySelectorAll(".aiw-alias-retract").length).toBe(0);
  });

  // AS07 ---------------------------------------------------------------------
  it("AS07: Widerruf ohne Grund wird im UI abgefangen", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    const calls = [];
    api.renderAlias(el, _data(), {
      doc: win.document,
      canEdit: true,
      onRetract: (b) => calls.push(b),
    });

    const row = el.querySelectorAll("tbody tr")[0];
    row.querySelector(".aiw-alias-retract").click();
    const reasonRow = el.querySelector(".aiw-alias-reasonrow");
    expect(reasonRow).toBeTruthy();

    // Leerer Grund -> kein Aufruf, aber eine sichtbare Meldung.
    reasonRow.querySelector(".aiw-alias-retract-go").click();
    expect(calls.length).toBe(0);
    const res = el.querySelector("#aiw-alias-result");
    expect(res.textContent).toMatch(/Grund ist Pflicht/);
    expect(res.classList.contains("error")).toBe(true);

    // Mit Grund -> genau ein Aufruf mit den erwarteten Feldern.
    reasonRow.querySelector(".aiw-alias-reason").value = "  Irrtum  ";
    reasonRow.querySelector(".aiw-alias-retract-go").click();
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({ alias_id: 1, reason: "Irrtum" });
  });

  // AS08 ---------------------------------------------------------------------
  it("AS08: Fremdtext ist XSS-sicher (textContent, kein Markup)", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    const boese = '<img src=x onerror="alert(1)">Panther';
    const d = _data();
    d.entries[0].alias = boese;
    d.entries[0].basis = "<script>alert(2)</script>";
    api.renderAlias(el, d, { doc: win.document, canEdit: true });

    const cell = el.querySelector(".aiw-alias-name-cell");
    expect(cell.textContent).toBe(boese);
    // Kein eingeschleustes Element im gesamten Baum.
    expect(el.querySelector("img")).toBeNull();
    expect(el.querySelector("script")).toBeNull();
  });

  // AS09 ---------------------------------------------------------------------
  it("AS09: Ladefehler ist kein Leerbefund", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    api.renderAlias(el, { error: "HTTP 503" }, { doc: win.document });

    const err = el.querySelector(".aiw-alias-error");
    expect(err).toBeTruthy();
    expect(err.textContent).toContain("HTTP 503");
    // ... und ausdruecklich NICHT der harmlose "noch kein Alias"-Text.
    expect(el.querySelector(".aiw-placeholder")).toBeNull();
    expect(el.querySelector("table")).toBeNull();
  });

  // =========================================================================
  // BUILD 600 — NAMENSAUFLOESUNG
  //
  // AS20 — aufloesungText: die DREI Zustaende sind unterscheidbar. 'nicht
  //        gefunden' ist NICHT dasselbe wie 'nicht abfragbar', und keiner von
  //        beiden darf wie ein Erfolg aussehen (Grundregel 1).
  // AS21 — kaskadenText nennt die NICHT gelisteten Treffer der zweiten Stufe.
  //        Ohne diesen Satz saehe die Kaskade vollstaendig aus.
  // AS22 — Formular: Kennung eintippen -> onResolve wird gerufen, das Ergebnis
  //        steht unter dem Feld.
  // AS23 — Formular: Namenssuche -> Treffer anklicken -> subject_id gesetzt
  //        UND sofort rueckwaerts bestaetigt (zwei Anzeigen, eine Wahrheit).
  // AS24 — Katalogsuche: der Namensblock erscheint samt Quellen-Hinweis; ein
  //        Klick auf einen Treffer fuehrt in den Katalog dieses Kontos.
  // AS25 — Keine ganze Zahl -> es wird gar nicht erst gefragt, und die Sicht
  //        sagt warum.
  // =========================================================================

  /** Antwort von GET /api/names?subject_id=… */
  function _aufloesung(over) {
    return Object.assign({
      subject_id: 4711, name: "Panther", gefunden: true,
      quelle: "fallakte", quelle_label: "Fallakte (in Bearbeitung)",
      detail: "Fall in der Fallakte (Status: open)",
      aliasse: [], hinweise: [],
      quellen_hinweis: "… nicht 'gibt es nicht'.",
    }, over || {});
  }

  /** Antwort von GET /api/names?q=… */
  function _suche(over) {
    return Object.assign({
      begriff: "Panther", quelle: "fallakte",
      quelle_label: "Fallakte (in Bearbeitung)",
      treffer: [{ subject_id: 4711, name: "Panther", quelle: "fallakte",
                  quelle_label: "Fallakte (in Bearbeitung)",
                  detail: "Fall in der Fallakte (Status: open)" }],
      gesamt: 1, gekuerzt: false,
      weitere_treffer: { forenkonto: 3 },
      hinweise: [],
      quellen_hinweis: "Abgefragt werden die Fallakte und die globale "
        + "Namensliste … nicht 'gibt es nicht'.",
    }, over || {});
  }

  it("AS20: aufloesungText unterscheidet gefunden / leer / Fehler", () => {
    const api = _api();

    const ok = api.aufloesungText(_aufloesung());
    expect(ok.art).toBe("ok");
    expect(ok.text).toContain("Panther");
    // Die QUELLE gehoert dazu: ein Name aus der Fallakte ist ein anderer
    // Beleg als einer aus der globalen Namensliste.
    expect(ok.text).toContain("Fallakte");

    // Aliasse fahren mit, ersetzen den Kontonamen aber nicht.
    const mitAlias = api.aufloesungText(_aufloesung({ aliasse: ["Luchs"] }));
    expect(mitAlias.text).toContain("Panther");
    expect(mitAlias.text).toContain("Luchs");

    // Nicht gefunden -> gelb, und NICHT als Erfolg.
    const leer = api.aufloesungText(
      _aufloesung({ gefunden: false, name: null }));
    expect(leer.art).toBe("leer");
    expect(leer.text).toContain("Kein Name gefunden");
    expect(leer.text).toContain("abgefragten Quellen");

    // Nicht ABFRAGBAR ist etwas anderes als nicht gefunden — die Hinweise
    // machen daraus einen Fehlerzustand.
    const kaputt = api.aufloesungText(_aufloesung({
      gefunden: false, name: null,
      hinweise: ["default.db nicht gefunden — die globale Namensliste wurde "
                 + "NICHT abgefragt."],
    }));
    expect(kaputt.art).toBe("fehler");
    expect(kaputt.text).toContain("NICHT abgefragt");

    // Netzfehler.
    expect(api.aufloesungText({ fehler: "HTTP 503" }).art).toBe("fehler");
    // Nichts angefragt.
    expect(api.aufloesungText(null).art).toBe("wartet");
  });

  it("AS21: kaskadenText verschweigt die zweite Stufe nicht", () => {
    const api = _api();
    const t = api.kaskadenText(_suche());
    expect(t).toContain("1 Treffer");
    // DER KERN: die Kaskade endet bei der ersten Quelle mit Treffer — die
    // Zahl der uebrigen MUSS dastehen, sonst sieht das Ergebnis vollstaendig
    // aus und ist es nicht.
    expect(t).toContain("3 Treffer in der globalen");
    expect(t).toContain("nicht gelistet");

    // Ohne zweite Stufe kein Satz darueber.
    const ohne = api.kaskadenText(_suche({ weitere_treffer: {} }));
    expect(ohne).not.toContain("Außerdem");

    // Gekuerzte Liste wird als solche benannt.
    const viel = api.kaskadenText(_suche({ gesamt: 900, gekuerzt: true }));
    expect(viel).toContain("900");
    expect(viel).toContain("gekürzt");

    // Hinweise (z. B. Mindestlaenge) fahren mit.
    const kurz = api.kaskadenText(_suche({
      treffer: [], gesamt: 0, weitere_treffer: {},
      hinweise: ["Die globale Namensliste wurde NICHT abgefragt: sie verlangt "
                 + "mindestens 4 Zeichen."],
    }));
    expect(kurz).toContain("Kein Treffer");
    expect(kurz).toContain("mindestens 4 Zeichen");
  });

  it("AS22: subject_id eintippen loest den Namen auf", async () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    const gefragt = [];
    api.renderAlias(el, _data(), {
      doc: win.document, canEdit: true,
      onResolve: function (sid, cb) { gefragt.push(sid); cb(_aufloesung()); },
    });

    const sid = el.querySelector("#aiw-alias-sid");
    const anzeige = el.querySelector("#aiw-alias-sidname");
    expect(sid).toBeTruthy();
    expect(anzeige).toBeTruthy();

    sid.value = "4711";
    sid.dispatchEvent(new win.Event("input"));
    // Der Abruf ist entprellt — zuerst steht nur der Zwischenstand da.
    expect(anzeige.textContent).toContain("Löse auf");
    await new Promise((r) => setTimeout(r, 420));

    expect(gefragt).toEqual([4711]);
    expect(anzeige.textContent).toContain("Panther");
    expect(anzeige.classList.contains("ok")).toBe(true);
  });

  it("AS23: Namenssuche fuellt die Kennung und bestaetigt sie", async () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    const aufgeloest = [];
    api.renderAlias(el, _data(), {
      doc: win.document, canEdit: true,
      onNameSearch: function (term, cb) { cb(_suche({ begriff: term })); },
      onResolve: function (sid, cb) { aufgeloest.push(sid); cb(_aufloesung()); },
    });

    const feld = el.querySelector("#aiw-alias-namesearch");
    feld.value = "Panther";
    el.querySelector("#aiw-alias-namesearch-btn")
      .dispatchEvent(new win.Event("click"));

    const zeilen = el.querySelectorAll(
      "#aiw-alias-treffer .aiw-alias-treffer-zeile");
    expect(zeilen).toHaveLength(1);
    expect(zeilen[0].textContent).toContain("Panther");
    expect(zeilen[0].textContent).toContain("4711");
    // Auch hier steht die zweite Stufe der Kaskade da.
    expect(el.querySelector(".aiw-alias-treffer-kopf").textContent)
      .toContain("3 Treffer in der globalen");

    zeilen[0].dispatchEvent(new win.Event("click"));
    // Die Kennung ist gesetzt ...
    expect(el.querySelector("#aiw-alias-sid").value).toBe("4711");
    // ... und es wurde NICHTS geschrieben (die Meldung sagt es ausdruecklich).
    expect(el.querySelector("#aiw-alias-result").textContent)
      .toContain("nichts geschrieben");
    // ... und die Uebernahme wird rueckwaerts bestaetigt.
    await new Promise((r) => setTimeout(r, 420));
    expect(aufgeloest).toEqual([4711]);
  });

  it("AS24: Katalogsuche zeigt den Namensblock mit Quellen-Hinweis", () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    const gewaehlt = [];
    api.renderAlias(el, _data(), {
      doc: win.document, canEdit: false,
      query: "Panther",
      namen: _suche(),
      onSubject: function (sid) { gewaehlt.push(sid); },
    });

    const block = el.querySelector("#aiw-alias-namen");
    expect(block).toBeTruthy();
    expect(block.textContent).toContain("Namensauflösung");
    expect(block.textContent).toContain("3 Treffer in der globalen");
    // Der Quellen-Hinweis steht IMMER da.
    expect(el.querySelector(".aiw-alias-namen-fuss").textContent)
      .toContain("nicht 'gibt es nicht'");

    block.querySelector(".aiw-alias-treffer-zeile")
      .dispatchEvent(new win.Event("click"));
    expect(gewaehlt).toEqual([4711]);

    // Ohne Suchbegriff kein Block (er beantwortet eine Frage, die niemand
    // gestellt hat).
    const el2 = _mount(win);
    api.renderAlias(el2, _data(), { doc: win.document, namen: _suche() });
    expect(el2.querySelector("#aiw-alias-namen")).toBeNull();
  });

  it("AS25: keine ganze Zahl -> es wird gar nicht erst gefragt", async () => {
    const win = _win();
    const api = win.AIWCockpitAlias;
    const el = _mount(win);
    const gefragt = [];
    api.renderAlias(el, _data(), {
      doc: win.document, canEdit: true,
      onResolve: function (sid, cb) { gefragt.push(sid); cb(_aufloesung()); },
    });

    const sid = el.querySelector("#aiw-alias-sid");
    sid.value = "47xy";
    sid.dispatchEvent(new win.Event("input"));
    await new Promise((r) => setTimeout(r, 420));

    // Keine Anfrage — und die Sicht sagt WARUM, statt still nichts zu tun.
    expect(gefragt).toEqual([]);
    expect(el.querySelector("#aiw-alias-sidname").textContent)
      .toContain("Keine ganze Zahl");

    // Leeres Feld -> Anzeige leert sich wieder.
    sid.value = "";
    sid.dispatchEvent(new win.Event("input"));
    await new Promise((r) => setTimeout(r, 420));
    expect(el.querySelector("#aiw-alias-sidname").textContent).toBe("");
    expect(gefragt).toEqual([]);
  });
});
