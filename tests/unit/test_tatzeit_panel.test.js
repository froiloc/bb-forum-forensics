/**
 * test_tatzeit_panel.test.js
 * Unit-/Regressionstests: TatzeitPanel (Aufklappbereich "Tatzeitraum")
 * Baustelle 7 · AP-3A · Build 534 · 2026-07-26
 *
 * Getestet wird die AUSGELIEFERTE Quelle toolbar/tatzeit_panel.js (kein
 * nachgebauter Klon), geladen ueber jsdom-eval — analog test_scroll_memory.
 *
 * Schwerpunkt sind die Aussagen, die man verwechseln oder stillschweigend
 * verlieren kann:
 *
 *   TP01 — Die Mahnung erscheint NUR bei §§ 176/184 und NUR solange nichts
 *          erfasst ist.
 *   TP02 — Sobald ein Wert steht, verschwinden Farbe UND Symbol GANZ, und die
 *          Zeile nennt den erfassten Zeitraum (Festlegung mc: nicht nur
 *          blasser).
 *   TP03 — Solange der Stand nicht geladen ist, wird NICHT "nicht erfasst"
 *          behauptet. Der Unterschied zwischen "nachgesehen und nichts
 *          gefunden" und "noch nicht nachgesehen" ist hier wesentlich.
 *   TP04 — In Kategorien ausserhalb §§ 176/184 ist die Zeile stumm — ein
 *          Warnzeichen ohne Handlungsbedarf entwertet das Warnzeichen ueberall
 *          sonst.
 *   TP05 — Datumsumrechnung auf UTC-Mitternacht, mit Gegenprobe gegen das
 *          stillschweigende Weiterrollen ungueltiger Daten (31. Februar).
 *   TP06 — Die Nutzlast spiegelt die Regeln des Servers: harte Angabe braucht
 *          einen Zeitwert, Ende nicht vor Beginn, weiche Angabe braucht ihren
 *          Wortlaut.
 *   TP07 — 'sonstiges' verlangt einen Freitext; jede andere Herkunft verbietet
 *          ihn.
 *   TP08 — Der Plausibilitaetsrahmen wird nur geprueft, wenn der Server ihn
 *          mitgeliefert hat. Eine GERATENE Grenze waere schlimmer als keine.
 *   TP09 — Das Ende bekommt KEINE 23:59:59 aufaddiert (erfundene Genauigkeit).
 *   TP10 — DOM-Probe: der Bereich ist beim Aufbau ZUGEKLAPPT.
 *   TP11 — DOM-Probe: setCategory() zieht die Mahnung LIVE nach.
 *   TP12 — DOM-Probe: ein Lesefehler wird GEMELDET, nicht als "nichts
 *          erfasst" ausgegeben.
 *   TP13 — DOM-Probe: fehlt 'tatzeit.edit', erscheint kein Formular, sondern
 *          eine Begruendung.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync("toolbar/tatzeit_panel.js", "utf-8");

function loadClass() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://127.0.0.2/forum/",
  });
  dom.window.eval(_src);
  return { TatzeitPanel: dom.window.TatzeitPanel, dom };
}

/** Antwort des GET-Endpunkts, wie sie forensic_api/tatzeit_endpoint.py liefert. */
function serverAntwort(over) {
  return Object.assign({
    ok: true,
    subject_id: 4711,
    annotation_id: 1,
    local_id: "abc-123",
    can_edit: true,
    readonly_grund: null,
    vokabular: {
      arten: ["hart", "weich"],
      genauigkeiten: ["jahr", "monat", "tag", "unbestimmt"],
      angabe_schluessel: ["markierung"],
      quellen: [
        { code: "beitragstext", label: "Beitragstext im Forum", freitext_pflicht: false },
        { code: "sonstiges", label: "Sonstiges (Freitext erforderlich)", freitext_pflicht: true },
      ],
    },
    plausibel_von: 1514764800,
    plausibel_bis: 1798761600,
    wird_berechnet: false,
    eintraege: [],
  }, over || {});
}

// UTC-MITTERNACHT, nicht irgendein Zeitpunkt am Tag. Der erste Entwurf dieser
// Suite trug hier 1600000000 — das ist der 13.09.2020 um 12:26:40 UTC und
// stammte aus der Python-Suite, wo nur "irgendein Wert im Rahmen" gebraucht
// wurde. Die Maske rechnet aber ausdruecklich auf Mitternacht (kein
// aufaddierter Tagesrest), und genau das prueft TP09.
const VON = 1599955200;   // 2020-09-13T00:00:00Z
const BIS = 1600041600;   // 2020-09-14T00:00:00Z

describe("TatzeitPanel — reine Funktionen", () => {
  let TatzeitPanel;
  beforeEach(() => { ({ TatzeitPanel } = loadClass()); });

  // ===================================================================== TP01
  it("TP01: mahnt nur bei §§ 176/184 und nur ohne Eintrag", () => {
    expect(TatzeitPanel.MAHN_KATEGORIEN).toEqual(["CAT_176", "CAT_184"]);

    for (const cat of ["CAT_176", "CAT_184"]) {
      const z = TatzeitPanel.zeilenZustand(cat, []);
      expect(z.mahnung).toBe(true);
      expect(z.symbol).toBe("⚠");
      expect(z.text).toBe("nicht erfasst");
    }
    expect(TatzeitPanel.istMahnKategorie("CAT_PERSON")).toBe(false);
    expect(TatzeitPanel.istMahnKategorie("CAT_176")).toBe(true);
  });

  // ===================================================================== TP02
  it("TP02: sobald etwas steht, verschwinden Farbe und Symbol ganz", () => {
    const z = TatzeitPanel.zeilenZustand("CAT_176", [
      { art: "hart", von_ts: VON, bis_ts: BIS },
    ]);
    expect(z.mahnung).toBe(false);
    expect(z.symbol).toBe("");
    // Die Zeile sagt, WAS drinsteht — nicht nur, DASS etwas drinsteht.
    expect(z.text).toBe("13.09.2020 – 14.09.2020");

    // Gleicher Tag: kein sinnloses "13.09.2020 – 13.09.2020".
    expect(TatzeitPanel.zeilenZustand("CAT_176",
      [{ art: "hart", von_ts: VON, bis_ts: VON }]).text).toBe("13.09.2020");

    // Nur Beginn / nur Ende.
    expect(TatzeitPanel.eintragKurz({ art: "hart", von_ts: VON, bis_ts: null }))
      .toBe("ab 13.09.2020");
    expect(TatzeitPanel.eintragKurz({ art: "hart", von_ts: null, bis_ts: BIS }))
      .toBe("bis 14.09.2020");

    // Unscharfe Angabe zeigt ihren Wortlaut.
    expect(TatzeitPanel.eintragKurz(
      { art: "weich", angabe_wert: "vor zwei Jahren" }))
      .toBe("„vor zwei Jahren\"");
  });

  // ===================================================================== TP03
  it("TP03: behauptet vor dem Laden NICHT 'nicht erfasst'", () => {
    const z = TatzeitPanel.zeilenZustand("CAT_176", [], { unbekannt: true });
    expect(z.mahnung).toBe(false);
    expect(z.text).toBe("wird geladen …");
    expect(z.text).not.toContain("nicht erfasst");
  });

  // ===================================================================== TP04
  it("TP04: andere Kategorien werden nicht angemahnt", () => {
    for (const cat of ["CAT_PERSON", "CAT_LOCATION", "CAT_VICTIM", "CAT_OTHER", ""]) {
      const z = TatzeitPanel.zeilenZustand(cat, []);
      expect(z.mahnung).toBe(false);
      expect(z.symbol).toBe("");
      // Der Text bleibt sachlich — die Angabe ist dort optional.
      expect(z.text).toBe("nicht erfasst");
    }
  });

  // ===================================================================== TP05
  it("TP05: Datum -> UTC-Mitternacht, ungültige Daten ergeben null", () => {
    expect(TatzeitPanel.datumTsUTC("2020-09-13")).toBe(VON);
    expect(TatzeitPanel.tsDatumUTC(VON)).toBe("2020-09-13");
    expect(TatzeitPanel.tsAnzeige(VON)).toBe("13.09.2020");

    // Rundlauf über ein volles Jahr — keine Zeitzonen-Abweichung.
    for (const d of ["2019-01-01", "2019-06-30", "2020-02-29", "2024-12-31"]) {
      expect(TatzeitPanel.tsDatumUTC(TatzeitPanel.datumTsUTC(d))).toBe(d);
    }

    // Date.UTC rollt einen 31. Februar stillschweigend auf den 2./3. März
    // weiter. Ohne Gegenprobe würde aus einem Tippfehler ein plausibles Datum.
    expect(TatzeitPanel.datumTsUTC("2021-02-31")).toBeNull();
    expect(TatzeitPanel.datumTsUTC("2021-02-29")).toBeNull();   // kein Schaltjahr
    expect(TatzeitPanel.datumTsUTC("2021-13-01")).toBeNull();
    expect(TatzeitPanel.datumTsUTC("13.09.2020")).toBeNull();
    expect(TatzeitPanel.datumTsUTC("")).toBeNull();
    expect(TatzeitPanel.datumTsUTC(null)).toBeNull();
  });

  // ===================================================================== TP06
  it("TP06: die Nutzlast spiegelt die Regeln des Servers", () => {
    const basis = { quelle_code: "beitragstext" };

    // Harte Angabe ohne jeden Zeitwert.
    let r = TatzeitPanel.baueNutzlast({ ...basis, art: "hart" });
    expect(r.ok).toBe(false);
    expect(r.fehler).toMatch(/Beginn oder Ende/);

    // Ende vor Beginn.
    r = TatzeitPanel.baueNutzlast(
      { ...basis, art: "hart", von: "2020-09-14", bis: "2020-09-13" });
    expect(r.ok).toBe(false);
    expect(r.fehler).toMatch(/vor dem Beginn/);

    // Gültige harte Angabe.
    r = TatzeitPanel.baueNutzlast({
      ...basis, art: "hart", von: "2020-09-13", bis: "2020-09-14",
      genauigkeit: "tag",
    });
    expect(r.ok).toBe(true);
    expect(r.payload).toMatchObject({
      art: "hart", von_ts: VON, bis_ts: BIS, genauigkeit: "tag",
      quelle_code: "beitragstext", quelle_freitext: null,
    });
    // Harte Angabe führt KEINE weichen Felder mit (CHECK in m002).
    expect(r.payload.angabe_schluessel).toBeUndefined();
    expect(r.payload.angabe_wert).toBeUndefined();

    // Weiche Angabe ohne Wortlaut.
    r = TatzeitPanel.baueNutzlast({ ...basis, art: "weich" });
    expect(r.ok).toBe(false);
    expect(r.fehler).toMatch(/Wortlaut/);

    // Gültige weiche Angabe — und KEINE Zeitwerte (CHECK in m002).
    r = TatzeitPanel.baueNutzlast({
      ...basis, art: "weich", angabe_wert: "vor zwei Jahren",
      von: "2020-09-13",   // wird bewusst ignoriert
    });
    expect(r.ok).toBe(true);
    expect(r.payload).toMatchObject({
      art: "weich", angabe_schluessel: "markierung",
      angabe_wert: "vor zwei Jahren", genauigkeit: "unbestimmt",
    });
    expect(r.payload.von_ts).toBeUndefined();
    expect(r.payload.bis_ts).toBeUndefined();
  });

  // ===================================================================== TP07
  it("TP07: 'sonstiges' verlangt Freitext, alles andere verbietet ihn", () => {
    let r = TatzeitPanel.baueNutzlast(
      { art: "hart", von: "2020-09-13", quelle_code: "sonstiges" });
    expect(r.ok).toBe(false);
    expect(r.fehler).toMatch(/Freitext/);

    r = TatzeitPanel.baueNutzlast({
      art: "hart", von: "2020-09-13", quelle_code: "sonstiges",
      quelle_freitext: "Zitat aus gelöschtem Beitrag",
    });
    expect(r.ok).toBe(true);
    expect(r.payload.quelle_freitext).toBe("Zitat aus gelöschtem Beitrag");

    // Freitext bei anderer Herkunft wird VERWORFEN, nicht durchgereicht —
    // sonst läge dieselbe Angabe an zwei Orten.
    r = TatzeitPanel.baueNutzlast({
      art: "hart", von: "2020-09-13", quelle_code: "beitragstext",
      quelle_freitext: "sollte verschwinden",
    });
    expect(r.ok).toBe(true);
    expect(r.payload.quelle_freitext).toBeNull();

    // Ohne Herkunft geht gar nichts — eine Tatzeit ohne Herkunft ist kein Beleg.
    r = TatzeitPanel.baueNutzlast({ art: "hart", von: "2020-09-13" });
    expect(r.ok).toBe(false);
    expect(r.fehler).toMatch(/Herkunft/);

    // Freitext-Obergrenze.
    r = TatzeitPanel.baueNutzlast({
      art: "hart", von: "2020-09-13", quelle_code: "sonstiges",
      quelle_freitext: "x".repeat(TatzeitPanel.FREITEXT_MAX + 1),
    });
    expect(r.ok).toBe(false);
    expect(r.fehler).toMatch(/begrenzt/);
  });

  // ===================================================================== TP08
  it("TP08: Plausibilitätsrahmen nur prüfen, wenn der Server ihn liefert", () => {
    const werte = { art: "hart", von: "2010-01-01", quelle_code: "beitragstext" };

    // MIT Grenzen: abgelehnt.
    let r = TatzeitPanel.baueNutzlast(werte,
      { von: 1514764800, bis: 1798761600 });
    expect(r.ok).toBe(false);
    expect(r.fehler).toMatch(/außerhalb/);

    // OHNE Grenzen: durchgelassen — der Server prüft ohnehin, und eine
    // geratene Grenze wäre schlimmer als keine (sie könnte Gültiges ablehnen).
    r = TatzeitPanel.baueNutzlast(werte, {});
    expect(r.ok).toBe(true);
    expect(r.payload.von_ts).toBe(TatzeitPanel.datumTsUTC("2010-01-01"));
  });

  // ===================================================================== TP09
  it("TP09: das Ende bekommt keine 23:59:59 aufaddiert", () => {
    const r = TatzeitPanel.baueNutzlast({
      art: "hart", von: "2020-09-13", bis: "2020-09-13",
      quelle_code: "beitragstext",
    });
    expect(r.ok).toBe(true);
    // Gleiches Datum -> gleicher Zeitwert. Ein aufaddierter Tagesrest wäre
    // erfundene Genauigkeit; wie fein die Angabe ist, sagt 'genauigkeit'.
    expect(r.payload.bis_ts).toBe(r.payload.von_ts);
    expect(r.payload.bis_ts % 86400).toBe(0);
  });
});

describe("TatzeitPanel — Verhalten im DOM", () => {
  let TatzeitPanel, dom, container, gesendet;

  function panel(over) {
    const o = over || {};
    return new TatzeitPanel(Object.assign({
      container,
      ann: { id: 1, localId: "abc-123", category: "CAT_176" },
      ajaxGet: () => Promise.resolve(serverAntwort()),
      ajaxPost: (url, body) => {
        gesendet.push({ url, body });
        return Promise.resolve({ ok: true, tatzeit_id: 1, audit_seq: 2 });
      },
      announce: () => {},
    }, o));
  }

  beforeEach(() => {
    ({ TatzeitPanel, dom } = loadClass());
    container = dom.window.document.createElement("div");
    dom.window.document.body.appendChild(container);
    gesendet = [];
  });

  // ===================================================================== TP10
  it("TP10: der Bereich ist beim Aufbau zugeklappt", async () => {
    const p = panel().mount();
    await new Promise((r) => setTimeout(r, 0));

    const det = container.querySelector("#forensic-tatzeit");
    expect(det).not.toBeNull();
    expect(det.tagName.toLowerCase()).toBe("details");
    expect(det.open).toBe(false);   // mc 2026-07-26: die Oberfläche klar halten
    expect(p.count()).toBe(0);
  });

  // ===================================================================== TP11
  it("TP11: setCategory zieht die Mahnung live nach", async () => {
    const p = panel({ ann: { id: 1, localId: "abc-123", category: "CAT_PERSON" } });
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    const sum = container.querySelector("#forensic-tatzeit-summary");
    const st = container.querySelector("#forensic-tatzeit-status");
    expect(sum.classList.contains("forensic-tatzeit-summary--mahnung")).toBe(false);
    expect(st.textContent).not.toContain("⚠");

    p.setCategory("CAT_176");
    expect(sum.classList.contains("forensic-tatzeit-summary--mahnung")).toBe(true);
    expect(st.textContent).toContain("⚠");
    expect(sum.getAttribute("title")).toMatch(/176/);

    // Und wieder zurück — die Mahnung verschwindet vollständig.
    p.setCategory("CAT_OTHER");
    expect(sum.classList.contains("forensic-tatzeit-summary--mahnung")).toBe(false);
    expect(sum.getAttribute("title")).toBeNull();
  });

  // ===================================================================== TP12
  it("TP12: ein Lesefehler wird gemeldet, nicht als 'nichts erfasst' ausgegeben", async () => {
    const p = panel({
      ajaxGet: () => Promise.resolve({
        error: "tatzeit_table_missing", detail: "m002 nicht angewandt",
      }),
    });
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    const body = container.querySelector("#forensic-tatzeit-body");
    expect(body.textContent).toContain("m002 nicht angewandt");
    // Der entscheidende Satz: eine leere Liste sähe aus wie "nichts erfasst".
    expect(body.textContent).toContain("NICHT gesagt");
    // Und es wird KEIN Eingabeformular angeboten, solange der Stand unklar ist.
    expect(container.querySelector("#forensic-tatzeit-btn-set")).toBeNull();
  });

  // ===================================================================== TP13
  it("TP13: ohne 'tatzeit.edit' erscheint eine Begründung statt eines Formulars", async () => {
    const p = panel({
      ajaxGet: () => Promise.resolve(serverAntwort({ can_edit: false })),
    });
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    const body = container.querySelector("#forensic-tatzeit-body");
    expect(container.querySelector("#forensic-tatzeit-btn-set")).toBeNull();
    expect(body.textContent).toContain("tatzeit.edit");
    expect(body.textContent).toContain("Chef-Ermittlerin");
  });

  // ===================================================================== TP14
  it("TP14: im Live-Beistand wird der Grund genannt, nicht nur gesperrt", async () => {
    const p = panel({
      ajaxGet: () => Promise.resolve(
        serverAntwort({ can_edit: false, readonly_grund: "support" })),
    });
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    const body = container.querySelector("#forensic-tatzeit-body");
    expect(body.textContent).toContain("Live-Beistand");
    expect(container.querySelector("#forensic-tatzeit-btn-set")).toBeNull();
  });

  // ===================================================================== TP15
  it("TP15: vorhandene Einträge stehen in der Liste und in der Zeile", async () => {
    const p = panel({
      ajaxGet: () => Promise.resolve(serverAntwort({
        eintraege: [{
          id: 5, art: "hart", von_ts: VON, bis_ts: BIS, genauigkeit: "tag",
          quelle: "beitragstext", quelle_code: "beitragstext",
          quelle_freitext: null, version_nr: 2, deleted_at: null,
        }],
      })),
    });
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    expect(p.count()).toBe(1);
    const st = container.querySelector("#forensic-tatzeit-status");
    expect(st.textContent).toContain("13.09.2020 – 14.09.2020");
    expect(st.textContent).not.toContain("⚠");

    const li = container.querySelector(".forensic-tatzeit-eintrag");
    expect(li).not.toBeNull();
    expect(li.textContent).toContain("Beitragstext im Forum");
    expect(li.textContent).toContain("Fassung 2");
    // Zurücknehmen ist möglich, weil can_edit gilt.
    expect(container.querySelector(".forensic-tatzeit-btn-clear")).not.toBeNull();
  });

  // ===================================================================== TP16
  it("TP16: eine ungespeicherte Annotation wird zuerst gespeichert", async () => {
    const ann = { localId: "neu-1", category: "CAT_176" };
    let gespeichert = false;
    const p = panel({
      ann,
      ajaxGet: () => Promise.resolve(serverAntwort({ eintraege: [] })),
      saveAnnotation: () => {
        gespeichert = true;
        ann.id = 99;                       // wie syncAnnotation es tut
        return Promise.resolve();
      },
    });
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    // Der Knopf sagt, was er tut — kein verstecktes Zweitverhalten.
    const btn = container.querySelector("#forensic-tatzeit-btn-set");
    expect(btn.textContent).toBe("Annotation speichern und Tatzeit eintragen");

    container.querySelector("#forensic-tatzeit-von").value = "2020-09-13";
    container.querySelector("#forensic-tatzeit-quelle").value = "beitragstext";
    btn.click();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    expect(gespeichert).toBe(true);
    expect(gesendet.length).toBe(1);
    expect(gesendet[0].url).toBe("/_forensic/tatzeit");
    expect(gesendet[0].body.annotation_id).toBe(99);
    expect(gesendet[0].body.local_id).toBe("neu-1");
    expect(gesendet[0].body.von_ts).toBe(VON);
  });

  // ===================================================================== TP17
  it("TP17: scheitert das Speichern der Annotation, wird NICHTS eingetragen", async () => {
    const ann = { localId: "neu-2", category: "CAT_176" };
    const p = panel({
      ann,
      ajaxGet: () => Promise.resolve(serverAntwort({ eintraege: [] })),
      // syncAnnotation lehnt NICHT ab, es setzt nur syncState='error' und
      // vergibt keine ID. Genau dieser Fall wird hier nachgestellt.
      saveAnnotation: () => Promise.resolve(),
    });
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    container.querySelector("#forensic-tatzeit-von").value = "2020-09-13";
    container.querySelector("#forensic-tatzeit-quelle").value = "beitragstext";
    container.querySelector("#forensic-tatzeit-btn-set").click();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));

    expect(gesendet.length).toBe(0);       // kein POST ohne annotation_id
    const meldung = container.querySelector("#forensic-tatzeit-meldung");
    expect(meldung.textContent).toContain("NICHT eingetragen");
    // Die eingegebenen Werte bleiben stehen — nichts geht verloren.
    expect(container.querySelector("#forensic-tatzeit-von").value)
      .toBe("2020-09-13");
  });

  // ===================================================================== TP18
  it("TP18: eine ungültige Eingabe erzeugt keinen POST", async () => {
    const p = panel();
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    // Weder Beginn noch Ende, keine Herkunft.
    container.querySelector("#forensic-tatzeit-btn-set").click();
    await new Promise((r) => setTimeout(r, 0));

    expect(gesendet.length).toBe(0);
    expect(container.querySelector("#forensic-tatzeit-meldung").textContent)
      .toMatch(/Herkunft/);
  });

  // ===================================================================== TP19
  it("TP19: der Hinweis 'wird nicht berechnet' steht in fremden Kategorien", async () => {
    const p = panel({ ann: { id: 1, localId: "a", category: "CAT_PERSON" } });
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    const body = container.querySelector("#forensic-tatzeit-body");
    expect(body.textContent).toContain("nicht");
    expect(body.querySelector("#forensic-tatzeit-hinweis-kat")).not.toBeNull();
    expect(body.querySelector("#forensic-tatzeit-hinweis-kat").textContent)
      .toMatch(/Fristberechnung/);
  });

  // ===================================================================== TP20
  it("TP20: Zurücknehmen sendet an den eigenen Endpunkt", async () => {
    const p = panel({
      ajaxGet: () => Promise.resolve(serverAntwort({
        eintraege: [{
          id: 7, art: "hart", von_ts: VON, bis_ts: null, genauigkeit: "tag",
          quelle: "beitragstext", quelle_code: "beitragstext",
          quelle_freitext: null, version_nr: 1, deleted_at: null,
        }],
      })),
    });
    p.mount();
    await new Promise((r) => setTimeout(r, 0));

    container.querySelector(".forensic-tatzeit-btn-clear").click();
    await new Promise((r) => setTimeout(r, 0));

    expect(gesendet.length).toBe(1);
    // Eigener Pfad, weil eine Rücknahme fachlich etwas anderes ist als eine
    // Korrektur (eigener Ereignistyp TATZEIT_CLEARED, Build 533).
    expect(gesendet[0].url).toBe("/_forensic/tatzeit/clear");
    expect(gesendet[0].body).toEqual({ tatzeit_id: 7 });
  });
});
