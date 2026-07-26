/**
 * tests/unit/test_cockpit_nav.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit-Shell (Frontend)
 *
 * Testsuite fuer management/server/static/cockpit.js (Build 347).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpit) — KEIN
 * dupliziertes Logik-Abbild (vermeidet die 'gruen-aber-tot'-Falle).
 *
 * CN01 — API nach dem Laden verfuegbar (window.AIWCockpit).
 * CN02 — visibleViews(): filtert nach vorhandener Faehigkeit, Katalog-Reihenfolge.
 * CN03 — visibleViews(): leere/fehlende capabilities -> leer; mutiert Katalog nicht.
 * CN04 — scopeTag(): 'alle'/'eigene' bei gueltigem Scope, sonst '' (null/unbekannt/fehlend).
 * CN05 — firstViewId(): erste sichtbare ID bzw. null.
 * CN06 — groupSequence(): geordnete, eindeutige Gruppenfolge.
 * CN07 — buildNav(): Gruppenkoepfe + Nav-Buttons, Scope-Tags, aktive Klasse.
 * CN08 — buildNav(): Klick ruft onSelect(viewId).
 * CN09 — setWho(): Anzeigename via textContent (XSS-sicher).
 * CN10 — renderPlaceholder(): Leerzustand mit Sicht-Label bzw. default-deny-Hinweis.
 *
 * Version: v0.7.347 · Build: 347 · 2026-07-10
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

// cockpit.js einmalig lesen (Pfad relativ zum Repo-Wurzelverzeichnis).
const _src = readFileSync(
  "management/server/static/cockpit.js",
  "utf-8"
);

// Frischer JSDOM-Kontext pro Test (keine Interferenzen). Bewusst OHNE fetch,
// damit der Auto-Boot in cockpit.js nicht anlaeuft (siehe Guard dort).
function _makeContext() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

function _api() {
  return _makeContext().AIWCockpit;
}

describe("cockpit.js — policy-getriebene Navigation (Build 347)", () => {
  // CN01 -------------------------------------------------------------------
  it("CN01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.visibleViews).toBe("function");
    expect(Array.isArray(api.VIEW_CATALOG)).toBe(true);
  });

  // CN02 -------------------------------------------------------------------
  it("CN02: visibleViews filtert nach Faehigkeit, Katalog-Reihenfolge", () => {
    const api = _api();
    // Supervisor-artig: dashboard.view + workload.view + ops.view.
    const caps = {
      "dashboard.view": "alle",
      "workload.view": "alle",
      "ops.view": "alle",
    };
    const ids = api.visibleViews(caps).map((v) => v.id);
    // Build 461: 'promotion' haengt ebenfalls an ops.view (Fremdforum-Promotion).
    // Build 467: 'audit' (Audit-Explorer) haengt ebenfalls an ops.view und steht
    // in der Katalog-Reihenfolge direkt nach 'integrity'.
    expect(ids).toEqual(
      ["dashboard", "workload", "integrity", "audit", "promotion"]);
  });

  // CN03 -------------------------------------------------------------------
  it("CN03: leere capabilities -> leer; Katalog unveraendert", () => {
    const api = _api();
    expect(api.visibleViews({})).toEqual([]);
    expect(api.visibleViews(null)).toEqual([]);
    expect(api.visibleViews(undefined)).toEqual([]);
    // Kataloglaenge bleibt (keine Mutation).
    // Build 384: 13 statt 12 Sichten (neu: 'cases' - Fall-Erkennung).
    // Build 386: 14 (neu: 'calendar' - Kalender & Wiedervorlage).
    // Build 395: 15 (neu: 'results' - Ermittlungsergebnis).
    // Build 406: 16 (neu: 'notes' - Betreuungs-Notizen).
    // Build 413: 17 (neu: 'lectorate' - Lektorat, W4 Gegenlesen).
    // Build 416: 18 (neu: 'approval' - Chef-Freigabe, W5).
    // Build 423: 19 (neu: 'templates' - Platzhalter & Queries, W2).
    // Build 425: 20 (neu: 'doctemplates' - Dokumentvorlagen, W3).
    // Build 427: 21 (neu: 'modules' - Baustein-Module, W1).
    // Build 448: 22 (neu: 'planung' - Prognose & Gantt, AP-2C).
    // Build 450: 23 (neu: 'annostats' - Annotations-Statistik, AP-2D).
    // Build 461: 24 (neu: 'promotion' - Fremdforum-Promotion, AP-2G).
    // Build 463: 25 (neu: 'releases' - Externe Fallfreigabe, AP-2G).
    // Build 465: 26 (neu: 'onboarding' - Onboarding/Offboarding, AP-2G).
    // Build 467: 27 (neu: 'audit' - Audit-/Revisions-Explorer, AP-2E).
    // Build 471: 28 (neu: 'crossref' - Kreuzbezug/identifizierte Personen, AP-2A).
    // Build 478: 29 (neu: 'crossfindings' - Querfund-Meta-Uebersicht, AP-2A).
    // Build 502: 30 (neu: 'adsync' - AD-Abgleich, personnel.sync).
    // Build 503: 30 ('adsync' ERSETZT durch 'personnel' -
    //             Personalverwaltung mit eingebundenem AD-Abgleich).
    // Build 505: 31 (neu: 'alias' - globaler Alias-Katalog, AP-2A/A1).
    // Build 510: 32 (neu: 'merge' - Identitaets-Gruppen, AP-2A/A3).
    // Build 516: 33 (neu: 'escalation' - Eskalationen, AP-2G/Idee 23).
    // Build 519: 34 (neu: 'nextactions' - Naechstbeste Aktion, AP-2F/Idee 22).
    // Build 520: 35 (neu: 'handover' - Uebergabe-Protokoll, AP-2G/Idee 30).
    // Build 521: 36 (neu: 'retention' - Aufbewahrungsfristen, AP-2G/Idee 29).
    // Build 525: 37 (neu: 'limitation' - Fristen/Verjaehrung,
    //           AP-3A/Idee 32; Gruppe 'Auswertung', Recht
    //           limitation.view).
    // Build 539: 38 (neu: 'matrix' - Dringlichkeit & Erkenntnislage,
    //           AP-3B; Gruppe 'Auswertung', EIGENES Recht matrix.view
    //           aus M033 - ausdruecklich NICHT limitation.view).
    expect(api.VIEW_CATALOG.length).toBe(38);
  });

  // CN-QUERFUND (Build 478) --------------------------------------------------
  it("CN-QUERFUND: Querfunde haengt an crossref.view, Gruppe Auswertung", () => {
    const api = _api();
    const v = api.viewById("crossfindings");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("crossref.view");
    expect(v.group).toBe("Auswertung");
    expect(api.visibleViews({}).map((x) => x.id)).not.toContain("crossfindings");
    expect(
      api.visibleViews({ "crossref.view": "alle" }).map((x) => x.id)
    ).toContain("crossfindings");
  });

  // CN-MERGE (Build 510) -----------------------------------------------------
  it("CN-MERGE: Identitaets-Gruppen haengen an crossref.view, Gruppe Auswertung",
     () => {
    const api = _api();
    const v = api.viewById("merge");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("crossref.view");
    expect(v.group).toBe("Auswertung");
    // default-deny: ohne Recht unsichtbar.
    expect(api.visibleViews({}).map((x) => x.id)).not.toContain("merge");
    expect(
      api.visibleViews({ "crossref.view": "alle" }).map((x) => x.id)
    ).toContain("merge");
  });

  // CN-ALIAS (Build 505) -----------------------------------------------------
  it("CN-ALIAS: Aliasse haengt an crossref.view, Gruppe Auswertung", () => {
    const api = _api();
    const v = api.viewById("alias");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("crossref.view");
    expect(v.group).toBe("Auswertung");
    expect(v.label).toBe("Aliasse");
    // default-deny: ohne Recht unsichtbar.
    expect(api.visibleViews({}).map((x) => x.id)).not.toContain("alias");
    expect(
      api.visibleViews({ "crossref.view": "alle" }).map((x) => x.id)
    ).toContain("alias");
  });

  // CN-XREF (Build 471) ------------------------------------------------------
  it("CN-XREF: Kreuzbezug haengt an crossref.view, Gruppe Auswertung", () => {
    const api = _api();
    const v = api.viewById("crossref");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("crossref.view");
    expect(v.group).toBe("Auswertung");
    // Ohne Recht unsichtbar; mit Recht sichtbar.
    expect(api.visibleViews({}).map((x) => x.id)).not.toContain("crossref");
    expect(
      api.visibleViews({ "crossref.view": "alle" }).map((x) => x.id)
    ).toContain("crossref");
  });

  // CN03b (Build 384) --------------------------------------------------------
  it("CN03b: Fall-Erkennung haengt an assignment.edit (Backend-Vorgabe 383)", () => {
    const api = _api();
    const v = api.viewById("cases");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("assignment.edit");
    expect(v.group).toBe("Verwaltung");

    // Wer zuweisen darf, sieht auch die Fall-Erkennung - und nur der.
    expect(api.visibleViews({ "assignment.edit": "alle" }).map((x) => x.id))
      .toEqual(["assignment", "cases"]);
    expect(api.visibleViews({ "dashboard.view": "eigene" }).map((x) => x.id))
      .toEqual(["dashboard"]);
  });

  // CN03c (Build 386) --------------------------------------------------------
  it("CN03c: Kalender & Wiedervorlage haengt an external.view", () => {
    const api = _api();
    const v = api.viewById("calendar");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("external.view");
    expect(v.group).toBe("Ueberblick");

    // Der Ermittler mit Scope 'eigene' sieht die Sicht ebenso wie die Chefin —
    // die Kapselung passiert im Backend (Scope), nicht in der Navigation.
    expect(api.visibleViews({ "external.view": "eigene" }).map((x) => x.id))
      .toEqual(["calendar"]);
  });

  // CN03d (Build 395) --------------------------------------------------------
  it("CN03d: Ermittlungsergebnis haengt an results.view", () => {
    const api = _api();
    const v = api.viewById("results");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("results.view");
    expect(v.group).toBe("Auswertung");

    // Auch der Ermittler mit Scope 'eigene' sieht die Sicht — er bekommt die
    // Abdeckung SEINER Faelle. Die fallUEBERGREIFENDE Verteilung (/stats)
    // bleibt Scope 'alle' vorbehalten; das prueft das Backend, nicht die Nav.
    expect(api.visibleViews({ "results.view": "eigene" }).map((x) => x.id))
      .toEqual(["results"]);
  });

  // CN03e (Build 423) --------------------------------------------------------
  it("CN03e: Platzhalter & Queries (W2) haengt an templates.edit", () => {
    const api = _api();
    const v = api.viewById("templates");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("templates.edit");
    expect(v.group).toBe("Redaktion");

    // Nur wer templates.edit hat (Redakteur:in/Chef), sieht die Autoren-Masken.
    // Build 425: templates.edit macht W2 UND W3 sichtbar (beide Gruppe Redaktion).
    // Build 427: zusaetzlich W1 ('modules') — alle drei Autoren-Werkzeuge.
    expect(api.visibleViews({ "templates.edit": "alle" }).map((x) => x.id))
      .toEqual(["templates", "doctemplates", "modules"]);
    // Ohne das Recht ist die Sicht unsichtbar (kein Leak in die Navigation).
    expect(api.visibleViews({ "dashboard.view": "alle" }).map((x) => x.id))
      .toEqual(["dashboard"]);
  });

  // CN03f (Build 425) --------------------------------------------------------
  it("CN03f: Dokumentvorlagen (W3) haengt an templates.edit, Gruppe Redaktion", () => {
    const api = _api();
    const v = api.viewById("doctemplates");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("templates.edit");
    expect(v.group).toBe("Redaktion");

    // templates.edit macht ALLE Redaktions-Sichten sichtbar (W2 + W3 + W1).
    expect(api.visibleViews({ "templates.edit": "alle" }).map((x) => x.id))
      .toEqual(["templates", "doctemplates", "modules"]);
  });

  // CN03g (Build 427) --------------------------------------------------------
  it("CN03g: Baustein-Module (W1) haengt an templates.edit, Gruppe Redaktion", () => {
    const api = _api();
    const v = api.viewById("modules");
    expect(v).toBeTruthy();
    expect(v.cap).toBe("templates.edit");
    expect(v.group).toBe("Redaktion");
  });

  // CN04 -------------------------------------------------------------------
  it("CN04: scopeTag liefert gueltigen Scope oder ''", () => {
    const api = _api();
    const caps = {
      "dashboard.view": "alle",
      "mycases.view": "eigene",
      "ops.view": null, // scope-los -> kein Tag
      "policy.view": "quatsch", // unbekannt -> kein Tag
    };
    expect(api.scopeTag("dashboard.view", caps)).toBe("alle");
    expect(api.scopeTag("mycases.view", caps)).toBe("eigene");
    expect(api.scopeTag("ops.view", caps)).toBe("");
    expect(api.scopeTag("policy.view", caps)).toBe("");
    expect(api.scopeTag("workload.view", caps)).toBe(""); // nicht vorhanden
  });

  // CN05 -------------------------------------------------------------------
  it("CN05: firstViewId erste sichtbare bzw. null", () => {
    const api = _api();
    const views = api.visibleViews({ "workload.view": "alle" });
    expect(api.firstViewId(views)).toBe("workload");
    expect(api.firstViewId([])).toBe(null);
  });

  // CN06 -------------------------------------------------------------------
  it("CN06: groupSequence geordnet und eindeutig", () => {
    const api = _api();
    const caps = {
      "dashboard.view": "alle", // Ueberblick
      "assignment.edit": "alle", // Verwaltung
      "reports.approve": "alle", // Verwaltung (Duplikat der Gruppe)
      "workload.view": "alle", // Auswertung
    };
    const views = api.visibleViews(caps);
    expect(api.groupSequence(views)).toEqual([
      "Ueberblick",
      "Verwaltung",
      "Auswertung",
    ]);
  });

  // CN07 -------------------------------------------------------------------
  it("CN07: buildNav baut Gruppenkoepfe, Buttons, Scope-Tags, aktive Klasse", () => {
    const win = _makeContext();
    const api = win.AIWCockpit;
    const nav = win.document.getElementById("aiw-nav")
      || win.document.createElement("nav");
    // Falls kein #aiw-nav vorhanden (leeres body): temporaeres Element nutzen.
    win.document.body.appendChild(nav);

    const caps = { "dashboard.view": "alle", "mycases.view": "eigene" };
    const views = api.visibleViews(caps);
    api.buildNav(nav, views, caps, "mycases", () => {});

    const groups = nav.querySelectorAll(".aiw-navgroup");
    const items = nav.querySelectorAll(".aiw-navitem");
    expect(groups.length).toBe(2); // Ueberblick, Persoenlich
    expect(items.length).toBe(2);

    // Aktive Sicht markiert.
    const active = nav.querySelector(".aiw-navitem.active");
    expect(active.getAttribute("data-view-id")).toBe("mycases");

    // Scope-Tags vorhanden (alle + eigene).
    const tags = Array.from(nav.querySelectorAll(".aiw-scopetag")).map(
      (t) => t.textContent
    );
    expect(tags.sort()).toEqual(["alle", "eigene"]);
  });

  // CN08 -------------------------------------------------------------------
  it("CN08: buildNav-Klick ruft onSelect(viewId)", () => {
    const win = _makeContext();
    const api = win.AIWCockpit;
    const nav = win.document.createElement("nav");
    win.document.body.appendChild(nav);

    let picked = null;
    const caps = { "dashboard.view": "alle", "workload.view": "alle" };
    const views = api.visibleViews(caps);
    api.buildNav(nav, views, caps, "dashboard", (id) => {
      picked = id;
    });

    const workloadBtn = nav.querySelector('[data-view-id="workload"]');
    workloadBtn.dispatchEvent(new win.Event("click"));
    expect(picked).toBe("workload");
  });

  // CN09 -------------------------------------------------------------------
  it("CN09: setWho setzt Anzeigename via textContent (XSS-sicher)", () => {
    const win = _makeContext();
    const api = win.AIWCockpit;
    const who = win.document.createElement("span");
    api.setWho(who, "<img src=x onerror=alert(1)>", "h001");
    // Kein injiziertes <img>-Element: der String steht als Text im <strong>.
    expect(who.querySelector("img")).toBe(null);
    expect(who.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(who.textContent).toContain("(h001)");
  });

  // CN10 -------------------------------------------------------------------
  it("CN10: renderPlaceholder mit Sicht bzw. default-deny", () => {
    const win = _makeContext();
    const api = win.AIWCockpit;
    const main = win.document.createElement("main");

    api.renderPlaceholder(main, api.viewById("dashboard"));
    expect(main.querySelector(".aiw-pagehead").textContent).toBe("Dashboard");
    expect(main.querySelector(".aiw-placeholder")).toBeTruthy();

    // Ohne Sicht (null): default-deny-Hinweis, kein Platzhalter-Kasten.
    api.renderPlaceholder(main, null);
    expect(main.querySelector(".aiw-placeholder")).toBe(null);
    expect(main.querySelector(".aiw-pagesub").textContent).toContain(
      "default-deny"
    );
  });

  // CN11 (Build 375): Sichten mit MEHREREN Faehigkeiten (any-of).
  // 'Berichts-Abnahme' ist sichtbar mit reports.approve ODER reports.review.
  it("CN11: any-of Faehigkeiten (reports)", () => {
    const api = _api();
    const view = api.VIEW_CATALOG.filter((v) => v.id === "reports")[0];
    expect(view.caps).toEqual(["reports.approve", "reports.review"]);

    // Nur reports.approve (Supervisor) -> sichtbar.
    let vis = api.visibleViews({ "reports.approve": "alle" });
    expect(vis.map((v) => v.id)).toContain("reports");

    // Nur reports.review (Lektor) -> ebenfalls sichtbar.
    vis = api.visibleViews({ "reports.review": "alle" });
    expect(vis.map((v) => v.id)).toContain("reports");

    // Keine von beiden -> nicht sichtbar.
    vis = api.visibleViews({ "dashboard.view": "alle" });
    expect(vis.map((v) => v.id)).not.toContain("reports");

    // effectiveCap: die tatsaechlich vorhandene Faehigkeit (fuer den Scope-Tag).
    expect(api.effectiveCap(view, { "reports.review": "alle" }))
      .toBe("reports.review");
  });
});
