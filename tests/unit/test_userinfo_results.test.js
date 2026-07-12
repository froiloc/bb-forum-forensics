/**
 * tests/unit/test_userinfo_results.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Ergebnisbewertung
 *
 * Testsuite fuer userinfo/userinfo_results.js (Build 390).
 * Prueft den ECHTEN Code (readFileSync + JSDOM, window.AIWUserinfoResults).
 *
 * UR01 — API verfuegbar.
 * UR02 — indexCurrent/cellText: 'nicht bewertet' ist ein BEFUND, kein Nichts.
 * UR03 — historyFor/historyLine: Verlauf mit Katalogversion und Beleg-Nr.
 * UR04 — hasQuality: Kriterien OHNE Qualitaetsskala bekommen KEIN Feld.
 * UR05 — assessRequest: Pflichtfelder; KEINE user_id im Rumpf (der Server
 *        nimmt sie aus dem Kontext — fremde Faelle sind strukturell
 *        unmoeglich); Qualitaet ohne Skala wird abgefangen.
 * UR06 — render: Tabelle mit EINER ZEILE JE KRITERIUM, zwei Extrem-Spalten.
 * UR07 — render: Historie ist sichtbar (details/summary), sobald es mehr als
 *        einen Stand gibt.
 * UR08 — render: Bearbeitung oeffnet EIN Feld unter der Zeile; es ist immer
 *        nur EINES offen.
 * UR09 — render: Kriterium ohne Qualitaetsskala zeigt KEIN Qualitaetsfeld;
 *        mit Skala erscheint die SEMANTIK-WARNUNG (Praezision vs. Schwere).
 * UR10 — render: zweistufig — "Erfassen (neuer Stand)" -> Bestaetigung ->
 *        POST; Abbrechen schreibt nichts.
 * UR11 — render: Kennzahl mit VERMERK; die Luecken werden genannt.
 * UR12 — render: ohne results.edit gibt es keine Knoepfe (nur Lesen).
 */

import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("userinfo/userinfo_results.js", "utf-8");

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api() { return _ctx().AIWUserinfoResults; }

function _catalog() {
  return {
    catalog_version: 1,
    extreme: ["schwerste", "beste"],
    confidence_items: [
      { code: "unbestimmt", label: "unbestimmt", ordinal: 0 },
      { code: "verdacht", label: "Verdacht", ordinal: 3 },
      { code: "gerichtsfest", label: "gerichtsfest", ordinal: 5 },
    ],
    criteria: [
      { code: "identification", label: "Identifizierung des Kontoinhabers",
        quality_scale: null, quality_label: null,
        quality_beschreibung: null, quality_items: [], sort: 10 },
      { code: "abuser", label: "Missbrauchshandlung (Taeterschaft)",
        quality_scale: "abuser_quality",
        quality_label: "Missbrauchsbeziehung",
        quality_beschreibung:
          "ACHTUNG — ANDERE SEMANTIK: ordinal misst hier SCHWERE/AKTUALITAET, "
          + "NICHT Praezision.",
        quality_items: [
          { code: "kontaktlos", label: "kontaktlos", ordinal: 1 },
          { code: "fortlaufend", label: "fortlaufend", ordinal: 3 },
        ], sort: 40 },
    ],
  };
}

function _data(canEdit = true) {
  return {
    user_id: 18,
    can_edit: canEdit,
    catalog: _catalog(),
    current: [
      { criterion_code: "abuser", extrem: "schwerste",
        confidence_code: "verdacht", confidence_ordinal: 3,
        confidence_label: "Verdacht", quality_code: "fortlaufend",
        quality_ordinal: 3, quality_label: "fortlaufend",
        catalog_version: 1, note: "Chat 2024", audit_seq: 42,
        created_at: 1783000000, id: 2 },
    ],
    history: [
      { id: 2, criterion_code: "abuser", extrem: "schwerste",
        confidence_code: "verdacht", confidence_ordinal: 3,
        confidence_label: "Verdacht", quality_code: "fortlaufend",
        quality_ordinal: 3, quality_label: "fortlaufend",
        catalog_version: 1, note: "Chat 2024", audit_seq: 42,
        created_at: 1783000000 },
      { id: 1, criterion_code: "abuser", extrem: "schwerste",
        confidence_code: "unbestimmt", confidence_ordinal: 0,
        confidence_label: "unbestimmt", quality_code: null,
        quality_ordinal: null, quality_label: null,
        catalog_version: 1, note: "", audit_seq: 40,
        created_at: 1782900000 },
    ],
    score: {
      score: 3.0, basis: 1, abdeckung: 0.5,
      unbewertet: ["identification"],
      beitraege: [],
      vermerk: "PROVISORISCH — Gewichtung und Struktur dieser Formel sind mit "
        + "Chef-Ermittlerin und Staatsanwaltschaft NICHT abgestimmt.",
    },
  };
}

function _card(win) {
  const el = win.document.createElement("div");
  win.document.body.appendChild(el);
  return el;
}

describe("userinfo_results (Build 390)", () => {
  it("UR01 — API verfuegbar", () => {
    const api = _api();
    expect(typeof api.renderResults).toBe("function");
    expect(typeof api.assessRequest).toBe("function");
  });

  it("UR02 — 'nicht bewertet' ist ein BEFUND, kein Nichts", () => {
    const api = _api();
    expect(api.cellText(null)).toBe("nicht bewertet");
    expect(api.cellText({ confidence_label: "Verdacht", confidence_ordinal: 3 }))
      .toBe("Verdacht (3)");
    expect(api.cellText({
      confidence_label: "Verdacht", confidence_ordinal: 3,
      quality_code: "fortlaufend", quality_label: "fortlaufend",
      quality_ordinal: 3,
    })).toContain("fortlaufend (3)");

    const idx = api.indexCurrent(_data().current);
    expect(idx["abuser|schwerste"]).toBeTruthy();
    expect(idx["abuser|beste"]).toBeUndefined();
  });

  it("UR03 — Verlauf mit Katalogversion und Beleg-Nr.", () => {
    const api = _api();
    const h = api.historyFor(_data().history, "abuser", "schwerste");
    expect(h).toHaveLength(2);
    expect(api.historyFor(_data().history, "identification", "beste"))
      .toHaveLength(0);

    const line = api.historyLine(h[0]);
    expect(line).toContain("Katalog v1");
    expect(line).toContain("Beleg #42");
    expect(line).toContain("Chat 2024");
  });

  it("UR04 — Kriterium ohne Qualitaetsskala hat kein Qualitaetsfeld", () => {
    const api = _api();
    const cat = _catalog();
    expect(api.hasQuality(cat, "abuser")).toBe(true);
    expect(api.hasQuality(cat, "identification")).toBe(false);
    expect(api.hasQuality(cat, "gibtsnicht")).toBe(false);
  });

  it("UR05 — assessRequest: Pflichtfelder, KEINE user_id im Rumpf", () => {
    const api = _api();
    const cat = _catalog();

    expect(api.assessRequest(cat, {}).error).toContain("Kriterium");
    expect(api.assessRequest(cat, { criterion_code: "abuser" }).error)
      .toContain("Extrem");
    expect(api.assessRequest(cat, {
      criterion_code: "abuser", extrem: "schwerste" }).error)
      .toContain("Konfidenz");

    // Qualitaet, wo es keine Skala gibt -> abgefangen, kein POST.
    expect(api.assessRequest(cat, {
      criterion_code: "identification", extrem: "beste",
      confidence_code: "verdacht", quality_code: "ort" }).error)
      .toContain("keine Qualitaetsskala");

    const ok = api.assessRequest(cat, {
      criterion_code: "abuser", extrem: "schwerste",
      confidence_code: "gerichtsfest", quality_code: "fortlaufend",
      note: "Beleg S. 14" });
    expect(ok.path).toBe("/_forensic/results/assess");
    // DIE user_id FEHLT ABSICHTLICH: der Server nimmt sie aus dem Kontext.
    // Fremde Faelle sind damit strukturell unmoeglich, nicht nur verhindert.
    expect(ok.body.user_id).toBeUndefined();
    expect(ok.body).toEqual({
      criterion_code: "abuser", extrem: "schwerste",
      confidence_code: "gerichtsfest", quality_code: "fortlaufend",
      note: "Beleg S. 14" });

    // Ohne Qualitaetsangabe -> null (nicht "" — der Server unterscheidet das).
    expect(api.assessRequest(cat, {
      criterion_code: "identification", extrem: "beste",
      confidence_code: "verdacht" }).body.quality_code).toBeNull();
  });

  it("UR06 — eine Zeile je Kriterium, zwei Extrem-Spalten", () => {
    const win = _ctx();
    const api = win.AIWUserinfoResults;
    const card = _card(win);
    api.renderResults(card, _data(), {});

    const rows = card.querySelectorAll("#uir-table tbody tr");
    expect(rows).toHaveLength(2);                 // 2 Kriterien, NICHT 4
    expect(rows[0].getAttribute("data-criterion")).toBe("identification");

    const cells = rows[1].querySelectorAll(".uir-cell");
    expect(cells).toHaveLength(2);
    expect(cells[0].getAttribute("data-extrem")).toBe("schwerste");
    expect(cells[0].querySelector(".uir-val").textContent)
      .toContain("Verdacht (3)");

    // 'beste' ist nicht bewertet — das steht da, es ist nicht leer.
    expect(cells[1].querySelector(".uir-val").textContent)
      .toBe("nicht bewertet");
    expect(cells[1].classList.contains("uir-leer")).toBe(true);

    // Katalogversion sichtbar.
    expect(card.querySelector("#uir-sub").textContent)
      .toContain("Katalogversion: 1");
  });

  it("UR07 — Historie ist sichtbar", () => {
    const win = _ctx();
    const api = win.AIWUserinfoResults;
    const card = _card(win);
    api.renderResults(card, _data(), {});

    const det = card.querySelector(".uir-hist");
    expect(det).toBeTruthy();
    expect(det.querySelector("summary").textContent).toContain("Verlauf (2)");
    expect(det.querySelectorAll("li")).toHaveLength(2);
    expect(det.textContent).toContain("Beleg #40");
  });

  it("UR08 — Bearbeitung: EIN Feld unter der Zeile, immer nur eines", () => {
    const win = _ctx();
    const api = win.AIWUserinfoResults;
    const card = _card(win);
    api.renderResults(card, _data(), {});

    expect(card.querySelector("#uir-editor")).toBeNull();

    const btns = card.querySelectorAll("button.uir-edit");
    // 2 Kriterien x 2 Extreme = 4 Knoepfe.
    expect(btns).toHaveLength(4);

    btns[0].dispatchEvent(new win.Event("click"));
    let ed = card.querySelectorAll("#uir-editor");
    expect(ed).toHaveLength(1);

    // Ein zweiter Klick woanders SCHLIESST den ersten Editor.
    btns[3].dispatchEvent(new win.Event("click"));
    ed = card.querySelectorAll("tr.uir-editor");
    expect(ed).toHaveLength(1);

    // Schliessen entfernt ihn.
    card.querySelector("#uir-cancel").dispatchEvent(new win.Event("click"));
    expect(card.querySelector("tr.uir-editor")).toBeNull();
  });

  it("UR09 — Qualitaetsfeld nur mit Skala; Semantik-Warnung erscheint", () => {
    const win = _ctx();
    const api = win.AIWUserinfoResults;
    const card = _card(win);
    const view = api.renderResults(card, _data(), {});

    // 'identification' hat KEINE Qualitaetsskala -> KEIN Feld.
    // (openEditor loest die Ankerzeile SELBST auf — ein von aussen gemerktes
    //  Zeilen-Element koennte nach closeEditor() aus dem DOM sein.)
    view.openEditor(_catalog().criteria[0], "beste");
    expect(card.querySelector("#uir-conf")).toBeTruthy();
    expect(card.querySelector("#uir-qual")).toBeNull();

    // 'abuser' hat eine -> Feld + SEMANTIK-WARNUNG.
    view.openEditor(_catalog().criteria[1], "schwerste");
    expect(card.querySelector("#uir-qual")).toBeTruthy();
    const hint = card.querySelector(".uir-hint");
    expect(hint).toBeTruthy();
    expect(hint.textContent).toContain("SCHWERE");
    expect(hint.textContent).toContain("NICHT Praezision");

    // Der bestehende Stand ist vorbelegt (Verdacht + fortlaufend).
    expect(card.querySelector("#uir-conf").value).toBe("verdacht");
    expect(card.querySelector("#uir-qual").value).toBe("fortlaufend");
  });

  it("UR10 — zweistufig: Erfassen -> Bestaetigung -> POST", () => {
    const win = _ctx();
    const api = win.AIWUserinfoResults;
    const card = _card(win);
    const onAssess = vi.fn();

    const view = api.renderResults(card, _data(), { onAssess });
    view.openEditor(_catalog().criteria[1], "schwerste");

    // Der Knopf heisst "Erfassen (neuer Stand)", NICHT "Speichern" — wer
    // glaubt, er korrigiere einen Wert, versteht das System falsch.
    const save = card.querySelector("#uir-save");
    expect(save.textContent).toContain("neuer Stand");

    // Stufe 1: Bestaetigung, KEIN Schreibvorgang.
    save.dispatchEvent(new win.Event("click"));
    expect(onAssess).not.toHaveBeenCalled();
    const ct = card.querySelector(".uir-confirm-title").textContent;
    expect(ct).toContain("NEUER");
    expect(ct).toContain("audit_log");
    expect(ct).toContain("nichts ueberschrieben");

    // Abbrechen -> nichts.
    card.querySelector("#uir-confirm-no").dispatchEvent(new win.Event("click"));
    expect(onAssess).not.toHaveBeenCalled();
    expect(card.querySelector("#uir-result").textContent)
      .toContain("Es wurde nichts geschrieben");

    // Erneut, diesmal ausfuehren.
    save.dispatchEvent(new win.Event("click"));
    card.querySelector("#uir-conf").value = "gerichtsfest";
    card.querySelector("#uir-qual").value = "kontaktlos";
    card.querySelector("#uir-note").value = "Asservat 3";
    card.querySelector("#uir-confirm-yes")
      .dispatchEvent(new win.Event("click"));

    expect(onAssess).toHaveBeenCalledTimes(1);
    expect(onAssess).toHaveBeenCalledWith({
      criterion_code: "abuser", extrem: "schwerste",
      confidence_code: "gerichtsfest", quality_code: "kontaktlos",
      note: "Asservat 3" });

    // Ohne Konfidenz -> kein POST, sondern eine Meldung.
    save.dispatchEvent(new win.Event("click"));
    card.querySelector("#uir-conf").value = "";
    card.querySelector("#uir-confirm-yes")
      .dispatchEvent(new win.Event("click"));
    expect(onAssess).toHaveBeenCalledTimes(1);        // unveraendert
    expect(card.querySelector("#uir-result").textContent)
      .toContain("Konfidenz ist Pflicht");
  });

  it("UR11 — Kennzahl mit VERMERK und genannten Luecken", () => {
    const win = _ctx();
    const api = win.AIWUserinfoResults;
    const card = _card(win);
    api.renderResults(card, _data(), {});

    const sc = card.querySelector("#uir-score");
    expect(sc.querySelector(".uir-score-val").textContent)
      .toContain("Provisorische Kennzahl: 3");
    expect(sc.querySelector(".uir-gaps").textContent)
      .toContain("identification");
    // Der VERMERK ist Teil der Zahl, nicht ihr Beiwerk.
    expect(sc.querySelector(".uir-vermerk").textContent)
      .toContain("NICHT abgestimmt");
  });

  it("UR12 — ohne results.edit: nur Lesen", () => {
    const win = _ctx();
    const api = win.AIWUserinfoResults;
    const card = _card(win);
    api.renderResults(card, _data(false), {});

    expect(card.querySelectorAll("button.uir-edit")).toHaveLength(0);
    expect(card.querySelector(".uir-readonly").textContent)
      .toContain("results.edit");
    // Tabelle, Historie und Kennzahl stehen trotzdem.
    expect(card.querySelector("#uir-table")).toBeTruthy();
    expect(card.querySelector(".uir-hist")).toBeTruthy();
    expect(card.querySelector("#uir-score")).toBeTruthy();
  });
});
