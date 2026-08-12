/**
 * tests/unit/test_cockpit_inaktive_leiste.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ruhestand von Hand
 *
 * Testsuite fuer die Leiste "Ausgeschiedene" in den beiden
 * Grundmengen-Sichten (Build 701, Ticket 95139d2a):
 *   management/server/static/cockpit_workload.js
 *   management/server/static/cockpit_capacity.js
 *
 * EINE DATEI FUER BEIDE SICHTEN, und das ist Absicht: die Leiste ist in
 * beiden fast gleich, weil sie dieselbe Sache meldet. Die Doppelung im
 * Quelltext ist begruendet (gerechnete Hilfe-Kennungen sieht keine Pruefung —
 * siehe Modulkoepfe); dass die beiden Fassungen sich AUSEINANDERENTWICKELN,
 * ist damit aber das nahe Risiko. Genau dagegen laeuft IL07: dieselben Daten
 * muessen in beiden Sichten denselben Satz ergeben.
 *
 * IL01 — die reinen Funktionen sind in beiden Sichten exportiert.
 * IL02 — inaktivBlock: fehlt der Block, ist das Ergebnis null — NICHT ein
 *        Block mit lauter Nullen (das waere eine Behauptung ueber einen
 *        Server, der die Frage nie beantwortet hat).
 * IL03 — zeigtLeiste: nur, wenn es etwas zu sagen gibt.
 * IL04 — inaktivText: Zahl UND Kennungen; Einzahl/Mehrzahl stimmen.
 * IL05 — inaktivText nennt die trotz Ruhestand Aufgefuehrten gesondert —
 *        das ist die wichtigste Zeile der Leiste.
 * IL06 — der Umschalter meldet den neuen Zustand an opts.onInaktiveToggle;
 *        der Haken steht auf dem Zustand aus der Antwort, nicht auf einem im
 *        Browser gemerkten.
 * IL07 — beide Sichten sagen zu denselben Daten dasselbe (Drift-Probe).
 * IL08 — ein Hinweis auf nicht feststellbare Fallzahlen erscheint.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const SICHTEN = [
  {
    name: "workload",
    datei: "management/server/static/cockpit_workload.js",
    global: "AIWCockpitWorkload",
    anker: "workload.bedienung.inaktive",
  },
  {
    name: "capacity",
    datei: "management/server/static/cockpit_capacity.js",
    global: "AIWCockpitCapacity",
    anker: "capacity.bedienung.inaktive",
  },
];

function _api(sicht) {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(readFileSync(sicht.datei, "utf-8"));
  return { win: dom.window, api: dom.window[sicht.global] };
}

/** Antwortform des Servers (Sichtbarkeitsbefund.to_dict). */
function _block(over) {
  return Object.assign(
    {
      ausgeblendet: 0,
      ausgeblendete_kennungen: [],
      behalten_mit_arbeit: [],
      behalten_referenziert: [],
      gezeigt: false,
      hinweis: null,
    },
    over || {}
  );
}

describe("Leiste 'Ausgeschiedene' (Build 701)", () => {
  SICHTEN.forEach((s) => {
    describe(s.name, () => {
      // IL01 -----------------------------------------------------------------
      it("IL01: reine Funktionen exportiert", () => {
        const { api } = _api(s);
        for (const fn of ["inaktivBlock", "inaktivText", "zeigtLeiste",
                          "renderInaktiveLeiste"]) {
          expect(typeof api[fn], s.name + "." + fn).toBe("function");
        }
      });

      // IL02 -----------------------------------------------------------------
      it("IL02: ohne Block wird nichts behauptet", () => {
        const { api } = _api(s);
        expect(api.inaktivBlock({})).toBe(null);
        expect(api.inaktivBlock(null)).toBe(null);
        expect(api.inaktivText({})).toBe("");
        expect(api.zeigtLeiste({})).toBe(false);
      });

      // IL03 -----------------------------------------------------------------
      it("IL03: die Leiste erscheint nur mit Anlass", () => {
        const { api } = _api(s);
        // Nichts ausgeblendet, nichts stehengeblieben -> kein Bedienrauschen.
        expect(api.zeigtLeiste({ inaktive: _block() })).toBe(false);
        expect(api.zeigtLeiste({ inaktive: _block({ ausgeblendet: 1 }) }))
          .toBe(true);
        expect(api.zeigtLeiste({ inaktive: _block({ gezeigt: true }) }))
          .toBe(true);
        expect(api.zeigtLeiste({
          inaktive: _block({ behalten_mit_arbeit: ["h0last"] }),
        })).toBe(true);
        expect(api.zeigtLeiste({ inaktive: _block({ hinweis: "x" }) }))
          .toBe(true);
      });

      // IL04 -----------------------------------------------------------------
      it("IL04: Zahl und Kennungen, richtige Zahlform", () => {
        const { api } = _api(s);
        const eins = api.inaktivText({
          inaktive: _block({ ausgeblendet: 1,
                             ausgeblendete_kennungen: ["h0leer"] }),
        });
        expect(eins).toContain("1 ausgeschiedene Person");
        // EINE ZAHL ALLEIN LAESST OFFEN, WEN ES BETRIFFT.
        expect(eins).toContain("h0leer");

        const zwei = api.inaktivText({
          inaktive: _block({ ausgeblendet: 2,
                             ausgeblendete_kennungen: ["h0a", "h0b"] }),
        });
        expect(zwei).toContain("2 ausgeschiedene Personen");
        expect(zwei).toContain("h0a, h0b");

        // Eingeblendet ist ein ANDERER Satz — nicht dieselbe Meldung mit
        // anderer Zahl.
        const alle = api.inaktivText({ inaktive: _block({ gezeigt: true }) });
        expect(alle).toContain("eingeblendet");
        expect(alle).not.toContain("ausgeblendet");
      });

      // IL05 -----------------------------------------------------------------
      it("IL05: trotz Ruhestand Aufgefuehrte werden benannt", () => {
        const { api } = _api(s);
        const t = api.inaktivText({
          inaktive: _block({ ausgeblendet: 1,
                             ausgeblendete_kennungen: ["h0leer"],
                             behalten_mit_arbeit: ["h0last"] }),
        });
        expect(t).toContain("offene Fälle");
        expect(t).toContain("h0last");
        // Beide Aussagen stehen nebeneinander — die eine ersetzt die andere
        // nicht.
        expect(t).toContain("h0leer");
      });

      // IL06 -----------------------------------------------------------------
      it("IL06: der Umschalter meldet den neuen Zustand", () => {
        const { win, api } = _api(s);
        const main = win.document.createElement("div");
        win.document.body.appendChild(main);
        const gemeldet = [];
        api.renderInaktiveLeiste(main, {
          inaktive: _block({ ausgeblendet: 1,
                             ausgeblendete_kennungen: ["h0leer"] }),
        }, { doc: win.document,
             onInaktiveToggle: (v) => gemeldet.push(v) });

        const cb = main.querySelector(".aiw-inaktive-leiste input");
        expect(cb, "kein Kaestchen").toBeTruthy();
        expect(cb.getAttribute("data-hilfe-id")).toBe(s.anker);
        // Der Haken folgt der ANTWORT, nicht einem Browser-Gedaechtnis.
        expect(cb.checked).toBe(false);
        cb.checked = true;
        cb.dispatchEvent(new win.Event("change"));
        expect(gemeldet).toEqual([true]);

        // Und umgekehrt: kommt die Antwort mit 'gezeigt', steht der Haken.
        const main2 = win.document.createElement("div");
        win.document.body.appendChild(main2);
        api.renderInaktiveLeiste(main2, {
          inaktive: _block({ gezeigt: true }),
        }, { doc: win.document });
        expect(main2.querySelector(".aiw-inaktive-leiste input").checked)
          .toBe(true);

        // Ohne Anlass entsteht gar nichts.
        const main3 = win.document.createElement("div");
        expect(api.renderInaktiveLeiste(main3, { inaktive: _block() },
                                        { doc: win.document })).toBe(null);
        expect(main3.querySelector(".aiw-inaktive-leiste")).toBe(null);
      });

      // IL08 -----------------------------------------------------------------
      it("IL08: ein Hinweis auf fehlende Angaben wird gezeigt", () => {
        const { win, api } = _api(s);
        const main = win.document.createElement("div");
        win.document.body.appendChild(main);
        api.renderInaktiveLeiste(main, {
          inaktive: _block({ hinweis: "Offene Faelle nicht feststellbar (x)" }),
        }, { doc: win.document });
        expect(main.querySelector(".aiw-inaktive-text").textContent)
          .toContain("nicht feststellbar");
      });
    });
  });

  // IL07 ---------------------------------------------------------------------
  it("IL07: beide Sichten sagen zu denselben Daten dasselbe", () => {
    // DRIFT-PROBE. Die Doppelung im Quelltext ist begruendet, das
    // Auseinanderlaufen waere es nicht. Faellt dieser Fall, wurde eine der
    // beiden Fassungen geaendert und die andere vergessen.
    const daten = [
      { inaktive: _block() },
      { inaktive: _block({ gezeigt: true }) },
      { inaktive: _block({ ausgeblendet: 1,
                           ausgeblendete_kennungen: ["h0leer"] }) },
      { inaktive: _block({ ausgeblendet: 2,
                           ausgeblendete_kennungen: ["h0a", "h0b"],
                           behalten_mit_arbeit: ["h0last"] }) },
      { inaktive: _block({ hinweis: "nicht feststellbar" }) },
      {},
    ];
    const [a, b] = SICHTEN.map((s) => _api(s).api);
    daten.forEach((d, i) => {
      expect(b.inaktivText(d), "Datensatz " + i).toBe(a.inaktivText(d));
      expect(b.zeigtLeiste(d), "Datensatz " + i).toBe(a.zeigtLeiste(d));
    });
  });
});
