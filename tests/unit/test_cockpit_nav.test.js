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
    expect(ids).toEqual(["dashboard", "workload", "integrity"]);
  });

  // CN03 -------------------------------------------------------------------
  it("CN03: leere capabilities -> leer; Katalog unveraendert", () => {
    const api = _api();
    expect(api.visibleViews({})).toEqual([]);
    expect(api.visibleViews(null)).toEqual([]);
    expect(api.visibleViews(undefined)).toEqual([]);
    // Kataloglaenge bleibt (keine Mutation).
    expect(api.VIEW_CATALOG.length).toBe(12);
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
});
