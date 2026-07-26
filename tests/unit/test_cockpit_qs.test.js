/**
 * =============================================================================
 * tests/unit/test_cockpit_qs.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 543 (AP-3C): die Cockpit-Sicht "QS & Metriken"
 * (cockpit_qs.js).
 *
 * DIE WICHTIGSTEN TESTS PRUEFEN, WAS DIE SICHT NICHT BEHAUPTET.
 *
 *   QV01 — API-Oberflaeche vollstaendig.
 *   QV02 — DIE ZWECKBINDUNG WIRD NICHT IM FRONTEND FORMULIERT: der angezeigte
 *          Text ist der der Antwort, ZEICHENGLEICH, und der Wortlaut kommt im
 *          JS-Quelltext nicht vor.
 *   QV03 — Fehlt die Zweckbindung, MELDET die Sicht das in eigener
 *          Auszeichnung — sie behauptet sie nicht stillschweigend.
 *   QV04 — ZWEI Zweckbindungen: die der QS steht oben, die der Kennzahlen im
 *          Kennzahlenblock. Sie werden NICHT zusammengelegt.
 *   QV05 — KEIN ELEMENT, DAS EINE PERSON MIT EINER ANDEREN VERGLEICHT: im
 *          gerenderten Text kommt kein Rangbegriff vor.
 *   QV06 — Die Begruendung ist Pflicht: ein leeres Feld loest KEINEN Aufruf
 *          aus und zeigt den Grund.
 *   QV07 — Ein gefuelltes Feld ruft mit genau der Nutzlast auf, die der
 *          Endpunkt erwartet.
 *   QV08 — Die SELBSTPRUEFUNGSSPERRE wird angezeigt: Grund sichtbar, KEIN
 *          Formular. (Durchgesetzt wird sie im Server.)
 *   QV09 — Ohne 'qs.edit' erscheint weder das Formular noch der Ziehknopf.
 *   QV10 — Der ZUFALLSKEIM steht in der Sicht — er ist der Grund, aus dem die
 *          Ziehung ein Beleg ist.
 *   QV11 — Ein UNBEKANNTER Ergebniscode wird als solcher gekennzeichnet und
 *          NICHT auf einen bekannten abgebildet.
 *   QV12 — Die Frontend-Codes decken genau ERGEBNIS_CODES des Backends ab
 *          (aus qs_vokabular.py GELESEN, nicht abgeschrieben).
 *   QV13 — 'ruecklauf_erforderlich' wird AUCH MIT 0 genannt.
 *   QV14 — 'ausserhalb der Ziehung' wird eigens ausgewiesen; ohne solche
 *          Ergebnisse erscheint der Bereich NICHT.
 *   QV15 — Substanz: 'nicht nachgesehen' und 'nachgesehen' ergeben
 *          VERSCHIEDENE Texte.
 *   QV16 — Anlaufzeit: ohne Spanne KEIN Median und ausdruecklich keine 0;
 *          die Faelle ohne inhaltliches Ereignis werden genannt.
 *   QV17 — Ausreisser werden mit GRUND gezeigt, ohne Schwere und ohne
 *          Punktzahl.
 *   QV18 — Faellt /api/metrics aus, bleibt der Stichprobenteil stehen und der
 *          Kennzahlenteil sagt, dass er NICHT verfuegbar ist.
 *   QV19 — Fehlerzustand der QS: ausdruecklich KEIN Leerbefund.
 *   QV20 — Leerbefund: als solcher benannt, mit dem Satz, dass er nichts
 *          ueber die Qualitaet aussagt.
 *   QV21 — Begruendungen und Kontonamen bleiben Text (textContent).
 *   QV22 — Ein fehlgeschlagener Schreibversuch steht OBEN und bleibt lesbar.
 * =============================================================================
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("management/server/static/cockpit_qs.js", "utf-8");

// Die Codeliste des BACKENDS — aus dem Python-Quelltext GELESEN, nicht
// abgeschrieben (Muster LV08/MV08).
const _py = readFileSync("management/qs/qs_vokabular.py", "utf-8");
function backendErgebnisCodes() {
  const m = _py.match(/ERGEBNIS_CODES[^=]*=\s*\(([\s\S]*?)\)/);
  if (!m) throw new Error("ERGEBNIS_CODES nicht in qs_vokabular.py gefunden");
  return (m[1].match(/"([a-z_]+)"/g) || []).map((s) => s.replace(/"/g, ""));
}

function _both() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return { win: dom.window, api: dom.window.AIWCockpitQs };
}

function _api() {
  return _both().api;
}

const QS_ZWECK =
  "AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT. Die " +
  "QS-Stichprobe prueft die AUSWERTUNG eines Falls.";
const MT_ZWECK =
  "AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT. Diese " +
  "Kennzahlen beschreiben den Zustand der AUSWERTUNG.";

function F(over) {
  return Object.assign(
    {
      subject_id: 101,
      username: "nutzer101",
      position: 0,
      schicht: "nie_bewertet",
      ergebnis: null,
      ergebnis_label: null,
      begruendung: null,
      geprueft_von_name: null,
      geprueft_at: null,
      darf_pruefen: true,
      sperrgruende: [],
    },
    over || {}
  );
}

function Z(over) {
  return Object.assign(
    {
      id: 1,
      gezogen_at: 1785000000,
      gezogen_von_name: "NRW\\chefin",
      verfahren: "geschichtet",
      seed: 4711,
      grundgesamtheit_n: 16,
      stichprobe_n: 2,
      bemerkung: "",
      geprueft_n: 0,
      offen_n: 2,
      zaehler: {},
      filter: {},
      faelle: [F(), F({ subject_id: 102, position: 1 })],
      ausserhalb_der_ziehung: [],
    },
    over || {}
  );
}

function D(over) {
  return Object.assign(
    {
      ziehungen: [Z()],
      ziehungen_gesamt: 1,
      ergebnis_codes: backendErgebnisCodes(),
      zweckbindung: QS_ZWECK,
      ist_kein_bewertungsinstrument: true,
      prueflinge_sind_vorschlag: true,
      darf_pruefen_recht: true,
    },
    over || {}
  );
}

function M(over) {
  return Object.assign(
    {
      stichtag: "2026-07-26",
      kennzahlen: ["bestand", "abdeckung", "anlaufzeit", "substanz"],
      bestand: { faelle_gesamt: 16, je_status: { closed: 16 }, unzugewiesen: 3 },
      abdeckung: {
        faelle_gesamt: 16,
        n_kriterien: 10,
        nie_bewertet: 16,
        klassen: { nie_bewertet: 16, bis_25: 0, bis_50: 0, bis_75: 0, ueber_75: 0 },
      },
      anlaufzeit: {
        faelle_mit_zuweisung: 4,
        faelle_mit_anlaufzeit: 2,
        faelle_ohne_inhaltliches_ereignis: 2,
        median_tage: 10,
        q1_tage: 5,
        q3_tage: 20,
        max_tage: 40,
      },
      substanz: { geprueft: false, hinweis: "NICHT NACHGESEHEN. ..." },
      ausreisser: [],
      fehlende_quellen: [],
      hinweise: [],
      dauer_gesamt_ms: 12,
      dauer_substanz_ms: null,
      zweckbindung: MT_ZWECK,
      ist_kein_bewertungsinstrument: true,
      keine_personenrangfolge: true,
    },
    over || {}
  );
}

function _render(data, opts) {
  const b = _both();
  const el = b.win.document.createElement("div");
  b.win.document.body.appendChild(el);
  const res = b.api.renderQs(
    el,
    data,
    Object.assign({ doc: b.win.document }, opts || {})
  );
  return { win: b.win, api: b.api, el, res };
}

describe("cockpit_qs (Build 543)", () => {
  // QV01 ---------------------------------------------------------------------
  it("QV01: API-Oberflaeche vollstaendig", () => {
    const api = _api();
    [
      "ERGEBNIS", "SCHICHT_LABEL", "ergebnisInfo", "ergebnisCodes",
      "schichtLabel", "zweckText", "zweckOk", "vorschlagText",
      "fortschrittText", "nachweisText", "zaehlerText", "begruendungFehlt",
      "sperrText", "substanzText", "substanzGeprueft", "anlaufText",
      "ausreisserText", "abdeckungZeilen", "ziehungen", "renderQs",
    ].forEach((k) => expect(api[k], "fehlt: " + k).toBeDefined());
  });

  // QV02 ---------------------------------------------------------------------
  it("QV02: Zweckbindung ZEICHENGLEICH, nicht neu formuliert", () => {
    const api = _api();
    expect(api.zweckText(D(), "QS")).toBe(QS_ZWECK);
    // Der Wortlaut darf im CODE nicht vorkommen. Im KOPFKOMMENTAR steht er,
    // weil dort begruendet wird, warum er nicht im Code steht — deshalb wird
    // nur gegen die Nicht-Kommentarzeilen geprueft (dasselbe Vorgehen wie
    // QM07 in tests/test_qs_sampler.py).
    const _code = _src
      .split("\n")
      .filter((z) => !z.trim().startsWith("//"))
      .join("\n");
    expect(_code.indexOf("KEIN MITARBEITER-BEWERTUNGSINSTRUMENT")).toBe(-1);
  });

  // QV03 ---------------------------------------------------------------------
  it("QV03: fehlende Zweckbindung wird GEMELDET", () => {
    const api = _api();
    expect(api.zweckOk(D())).toBe(true);
    expect(api.zweckOk(D({ ist_kein_bewertungsinstrument: false }))).toBe(false);
    expect(api.zweckText(D({ zweckbindung: "" }), "QS")).toMatch(/ACHTUNG/);
    const r = _render(D({ ist_kein_bewertungsinstrument: false }));
    expect(r.el.querySelector(".aiw-qs-zweck").className).toMatch(/is-fehlt/);
  });

  // QV04 ---------------------------------------------------------------------
  it("QV04: ZWEI Zweckbindungen, nicht zusammengelegt", () => {
    const r = _render(D(), { metrik: M() });
    const zwecke = r.el.querySelectorAll(".aiw-qs-zweck");
    expect(zwecke.length).toBe(2);
    expect(zwecke[0].textContent).toBe(QS_ZWECK);
    expect(zwecke[1].textContent).toBe(MT_ZWECK);
    expect(zwecke[0].textContent).not.toBe(zwecke[1].textContent);
  });

  // QV05 ---------------------------------------------------------------------
  it("QV05: kein Element, das eine Person mit einer anderen vergleicht", () => {
    const r = _render(D(), { metrik: M() });
    const text = r.el.textContent.toLowerCase();
    ["rangliste", "ranking", "bestenliste", "produktivit", "leistung je",
     "pro stunde", "je stunde"].forEach((verboten) => {
      expect(text).not.toContain(verboten);
    });
  });

  // QV06 ---------------------------------------------------------------------
  it("QV06: leere Begruendung loest KEINEN Aufruf aus", () => {
    const api = _api();
    expect(api.begruendungFehlt("")).toBe(true);
    expect(api.begruendungFehlt("   ")).toBe(true);
    expect(api.begruendungFehlt("traegt")).toBe(false);

    const gesehen = [];
    const r = _render(D(), { onReview: (n) => gesehen.push(n) });
    const knopf = r.el.querySelector(".aiw-qs-speichern");
    expect(knopf).toBeTruthy();
    knopf.dispatchEvent(new r.win.Event("click"));
    expect(gesehen).toEqual([]);
    expect(r.el.querySelector(".aiw-qs-formfehler").textContent).toMatch(
      /Begründung ist Pflicht/
    );
  });

  // QV07 ---------------------------------------------------------------------
  it("QV07: gefuelltes Feld ruft mit der erwarteten Nutzlast auf", () => {
    const gesehen = [];
    const r = _render(D(), { onReview: (n) => gesehen.push(n) });
    const ta = r.el.querySelector(".aiw-qs-begruendung");
    const sel = r.el.querySelector(".aiw-qs-ergebnis-wahl");
    ta.value = "Zu 'sharing' fehlt jede Bewertung.";
    // ueber selectedIndex und nicht ueber .value: in jsdom greift das
    // zuverlaessig, und der Test soll die Auswahl pruefen, nicht die
    // Eigenheiten der DOM-Nachbildung.
    const opts = Array.prototype.slice.call(
      sel.querySelectorAll("option"));
    const treffer = opts.filter((o) => o.value === "nachzuarbeiten");
    expect(treffer.length).toBe(1);
    treffer[0].selected = true;
    r.el.querySelector(".aiw-qs-speichern").dispatchEvent(
      new r.win.Event("click")
    );
    expect(gesehen.length).toBe(1);
    expect(gesehen[0]).toEqual({
      sample_id: 1,
      subject_id: 101,
      ergebnis: "nachzuarbeiten",
      begruendung: "Zu 'sharing' fehlt jede Bewertung.",
    });
  });

  // QV08 ---------------------------------------------------------------------
  it("QV08: die Selbstpruefungssperre wird angezeigt, Formular entfaellt", () => {
    const api = _api();
    expect(api.sperrText(F())).toBe(null);
    const gesperrt = F({
      darf_pruefen: false,
      sperrgruende: ["Der Fall ist dieser Person aktuell zugewiesen."],
    });
    expect(api.sperrText(gesperrt)).toMatch(/SELBSTPRÜFUNG GESPERRT/);

    const r = _render(D({ ziehungen: [Z({ faelle: [gesperrt] })] }), {
      onReview: () => {},
    });
    const zelle = r.el.querySelector(".aiw-qs-begr");
    expect(zelle.className).toMatch(/is-gesperrt/);
    expect(zelle.textContent).toMatch(/aktuell zugewiesen/);
    expect(r.el.querySelector(".aiw-qs-speichern")).toBe(null);
  });

  // QV09 ---------------------------------------------------------------------
  it("QV09: ohne qs.edit weder Formular noch Ziehknopf", () => {
    const r = _render(D({ darf_pruefen_recht: false }), {
      onReview: () => {},
      onDraw: () => {},
    });
    expect(r.el.querySelector(".aiw-qs-speichern")).toBe(null);
    expect(r.el.querySelector(".aiw-qs-draw")).toBe(null);
    // Und ohne wirkenden Rueckruf ebenfalls nicht.
    const r2 = _render(D());
    expect(r2.el.querySelector(".aiw-qs-draw")).toBe(null);
  });

  // QV10 ---------------------------------------------------------------------
  it("QV10: der Zufallskeim steht in der Sicht", () => {
    const api = _api();
    const t = api.nachweisText(Z());
    expect(t).toMatch(/Zufallskeim: 4711/);
    expect(t).toMatch(/nachrechenbar/);
    const r = _render(D());
    expect(r.el.querySelector(".aiw-qs-nachweis").textContent).toMatch(/4711/);
  });

  // QV11 ---------------------------------------------------------------------
  it("QV11: unbekannter Ergebniscode wird gekennzeichnet", () => {
    const api = _api();
    const i = api.ergebnisInfo("voellig_neu");
    expect(i.cls).toBe("is-unbekannt");
    expect(i.label).toMatch(/voellig_neu/);
    // Und 'kein Ergebnis' ist OFFEN, nicht 'in Ordnung'.
    expect(api.ergebnisInfo(null).label).toBe("OFFEN");
  });

  // QV12 ---------------------------------------------------------------------
  it("QV12: Frontend-Codes decken genau ERGEBNIS_CODES des Backends", () => {
    const api = _api();
    const backend = backendErgebnisCodes();
    expect(backend.length).toBe(4);
    expect(api.ergebnisCodes().slice().sort()).toEqual(backend.slice().sort());
  });

  // QV13 ---------------------------------------------------------------------
  it("QV13: 'Rücklauf erforderlich' wird auch mit 0 genannt", () => {
    const api = _api();
    const t = api.zaehlerText(Z({ zaehler: { in_ordnung: 3 } }));
    expect(t).toMatch(/Rücklauf erforderlich: 0/);
    expect(t).toMatch(/in Ordnung: 3/);
    expect(t).not.toMatch(/nicht beurteilbar/);
    // Ein unbekannter Code wird angehaengt statt verschwiegen.
    expect(api.zaehlerText(Z({ zaehler: { neu: 2 } }))).toMatch(/neu\): 2/);
  });

  // QV14 ---------------------------------------------------------------------
  it("QV14: 'außerhalb der Ziehung' wird eigens ausgewiesen", () => {
    expect(_render(D()).el.querySelector(".aiw-qs-ausserhalb")).toBe(null);
    const r = _render(
      D({
        ziehungen: [
          Z({
            ausserhalb_der_ziehung: [
              { subject_id: 909, ergebnis: "in_ordnung",
                geprueft_von_name: "NRW\\lektor" },
            ],
          }),
        ],
      })
    );
    const box = r.el.querySelector(".aiw-qs-ausserhalb");
    expect(box).toBeTruthy();
    expect(box.textContent).toMatch(/909/);
  });

  // QV15 ---------------------------------------------------------------------
  it("QV15: Substanz — nachgesehen und nicht nachgesehen sind verschieden", () => {
    const api = _api();
    const aus = api.substanzText(M());
    const an = api.substanzText(
      M({
        substanz: {
          geprueft: true,
          faelle_zugewiesen: 5,
          ohne_annotation: 2,
          ohne_evidence_datei: 1,
        },
      })
    );
    expect(aus).toMatch(/NICHT NACHGESEHEN/);
    expect(an).toMatch(/2 von 5/);
    expect(an).toMatch(/etwas anderes/);
    expect(aus).not.toBe(an);
    expect(api.substanzGeprueft(M())).toBe(false);
  });

  // QV16 ---------------------------------------------------------------------
  it("QV16: Anlaufzeit ohne Spanne — kein Median, keine 0", () => {
    const api = _api();
    const ohne = api.anlaufText(
      M({
        anlaufzeit: {
          faelle_mit_zuweisung: 3,
          faelle_mit_anlaufzeit: 0,
          faelle_ohne_inhaltliches_ereignis: 3,
          median_tage: null,
        },
      })
    );
    expect(ohne).toMatch(/Keine messbare Anlaufzeit/);
    expect(ohne).toMatch(/NICHT dasselbe wie 0 Tage/);
    expect(ohne).toMatch(/3 von 3/);
    expect(api.anlaufText(M())).toMatch(/Median 10 Tage/);
  });

  // QV17 ---------------------------------------------------------------------
  it("QV17: Ausreisser mit GRUND, ohne Schwere", () => {
    const api = _api();
    expect(api.ausreisserText(M())).toMatch(/Leerbefund/);
    expect(api.ausreisserText(M())).toMatch(/keine Bescheinigung/);
    const mit = M({
      ausreisser: [
        { subject_id: 101, art: "abgeschlossen_ohne_bewertung",
          grund: "Der Fall ist abgeschlossen, aber kein Kriterium gesetzt." },
      ],
    });
    expect(api.ausreisserText(mit)).toMatch(/PRÜFBEDARF AN DER AUSWERTUNG/);
    expect(api.ausreisserText(mit)).toMatch(/nicht nach Schwere geordnet/);
    const r = _render(D(), { metrik: mit });
    const li = r.el.querySelectorAll(".aiw-qs-ausreisser li");
    expect(li.length).toBe(1);
    expect(li[0].textContent).toMatch(/kein Kriterium gesetzt/);
  });

  // QV18 ---------------------------------------------------------------------
  it("QV18: faellt /api/metrics aus, bleibt die Stichprobe stehen", () => {
    const r = _render(D(), { metrik: { error: "403 forbidden" } });
    expect(r.el.querySelector(".aiw-qs-table")).toBeTruthy();
    expect(r.el.querySelector(".aiw-qs-metriken").textContent).toMatch(
      /nicht verfügbar/
    );
    expect(r.el.querySelector(".aiw-qs-metriken").textContent).toMatch(
      /KEIN Leerbefund/
    );
    expect(r.res.state).toBe("befund");
  });

  // QV19 ---------------------------------------------------------------------
  it("QV19: Fehlerzustand ist ausdruecklich KEIN Leerbefund", () => {
    const r = _render({ error: "500 qs_failed" });
    expect(r.res.state).toBe("error");
    expect(r.el.textContent).toMatch(/KEIN Leerbefund/);
    expect(r.el.querySelector(".aiw-qs-table")).toBe(null);
  });

  // QV20 ---------------------------------------------------------------------
  it("QV20: Leerbefund wird als solcher benannt", () => {
    const r = _render(D({ ziehungen: [], ziehungen_gesamt: 0 }));
    expect(r.res.state).toBe("leer");
    expect(r.el.querySelector(".aiw-qs-leer").textContent).toMatch(
      /keine Aussage über die Auswertungsqualität/
    );
  });

  // QV21 ---------------------------------------------------------------------
  it("QV21: Begruendungen und Kontonamen bleiben Text", () => {
    const name = "<img src=x onerror=alert(1)> Ünïcødé ✓ 日本語";
    const grund = "<script>alert(2)</script> Ünïcødé";
    const r = _render(
      D({
        ziehungen: [
          Z({ faelle: [F({ username: name, ergebnis: "in_ordnung",
                           begruendung: grund })] }),
        ],
      })
    );
    expect(r.el.querySelector(".aiw-qs-case").textContent).toContain(name);
    expect(r.el.querySelector(".aiw-qs-begr").textContent).toContain(grund);
    expect(r.el.innerHTML).not.toContain("<img");
    expect(r.el.innerHTML).not.toContain("<script>alert");
    expect(r.el.innerHTML).toContain("&lt;img");
  });

  // QV22 ---------------------------------------------------------------------
  it("QV22: ein fehlgeschlagener Schreibversuch steht OBEN", () => {
    const r = _render(D(), {
      fehler: "SELBSTPRÜFUNG IST GESPERRT. Fall 101 wurde von dieser Person "
        + "bearbeitet.",
    });
    const box = r.el.querySelector(".aiw-qs-fehler");
    expect(box).toBeTruthy();
    expect(box.textContent).toMatch(/SELBSTPRÜFUNG IST GESPERRT/);
    // VOR der ersten Ziehung.
    const kinder = Array.prototype.slice.call(r.el.children);
    const iFehler = kinder.indexOf(box);
    const iZiehung = kinder.findIndex(
      (k) => k.className && k.className.indexOf("aiw-qs-ziehung") >= 0
    );
    expect(iFehler).toBeLessThan(iZiehung);
    // Ohne Fehler erscheint der Bereich NICHT.
    expect(_render(D()).el.querySelector(".aiw-qs-fehler")).toBe(null);
  });
});
