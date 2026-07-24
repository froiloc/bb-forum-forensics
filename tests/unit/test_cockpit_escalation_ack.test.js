/**
 * tests/unit/test_cockpit_escalation_ack.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Eskalationen
 *
 * Testsuite fuer Build 518 (AP-2G / Idee 23): die QUITTIERUNG in der
 * Eskalations-Sicht (Frontend zu Build 517). Getestet wird der ECHTE Code
 * (readFileSync + JSDOM, window.AIWCockpitEscalation).
 *
 * Die bestehenden ES01-ES12 aus test_cockpit_escalation.test.js bleiben
 * unveraendert gueltig; hier kommen ausschliesslich die Faelle des
 * Schreibpfads dazu.
 *
 * QA01 — API um die Quittierungs-Funktionen erweitert
 * QA02 — canAck folgt AUSSCHLIESSLICH dem Server ('acknowledgeable')
 * QA03 — ackState: keiner / gueltig / ueberholt
 * QA04 — ackLine nennt WER, WANN und WARUM — und bei einem ueberholten
 *        Vermerk AUSDRUECKLICH, dass sich die Lage verschlechtert hat
 * QA05 — ackText unterscheidet 'gibt es nicht' (Struktur fehlt) von
 *        'darfst du nicht' (Recht fehlt) — zwei verschiedene Aussagen
 * QA06 — ohne Recht erscheinen KEINE Bedienelemente, der Vermerk-TEXT aber
 *        sehr wohl (lesen darf man ihn)
 * QA07 — mit Recht erscheint je Zeile genau ein Feld und ein Knopf; ohne
 *        Vermerk 'Quittieren', mit Vermerk 'Vermerk widerrufen'
 * QA08 — QUITTIEREN IST KEIN ERLEDIGEN: eine quittierte Meldung bleibt in
 *        der Liste UND behaelt ihre Schwere-Klasse (kein Abstufen)
 * QA09 — Pflichttext: leerer Grund loest KEINEN Netzaufruf aus und wird
 *        BENANNT (der Knopf bleibt nicht wirkungslos)
 * QA10 — onAck bekommt rule_code, subject_id und den BEOBACHTETEN Stand;
 *        subject_id null bleibt null (systemische Regel ist quittierbar)
 * QA11 — onRevoke bekommt die ack_id und den Grund
 * QA12 — Freitext eines Vermerks bleibt Text (kein Markup), UTF-8 erhalten
 *
 * Version: v0.8.518 · Build: 518 · 2026-07-24
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_escalation.js",
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
  return _makeContext().AIWCockpitEscalation;
}

function ACK(over) {
  return Object.assign(
    {
      ack_id: 5,
      reason: "StA informiert, Fall priorisiert",
      acknowledged_by: 1,
      acknowledged_by_name: "Chefin, Alpha",
      acknowledged_at: 1750000000,
      days_inactive_at_ack: 34,
      audit_seq: 412,
      outdated: false,
    },
    over
  );
}

function I(over) {
  return Object.assign(
    {
      rule_code: "fall_ueberfaellig",
      label: "Fall ueberfaellig",
      severity: "hoch",
      subject_id: 7001,
      message: "Fall 7001 (kekz): rote Ampel, 34 Tage inaktiv (>= 30).",
      days_inactive: 34,
      ack: null,
    },
    over
  );
}

function D(over) {
  return Object.assign(
    {
      generated_at: 1750000000,
      total_cases: 47,
      count_hoch: 1,
      count_mittel: 0,
      count_niedrig: 0,
      items: [I()],
      thresholds: {
        red_overdue_days: 30,
        stale_open_days: 14,
        backlog_high: 10,
      },
      acknowledgeable: true,
      ack_migrated: true,
    },
    over
  );
}

describe("cockpit_escalation.js — Quittierung (Build 518)", () => {
  // QA01 --------------------------------------------------------------------
  it("QA01: API erweitert", () => {
    const api = _api();
    ["canAck", "ackOf", "ackState", "ackLine", "fmtTs"].forEach((n) => {
      expect(typeof api[n], n).toBe("function");
    });
  });

  // QA02 --------------------------------------------------------------------
  it("QA02: canAck folgt nur dem Server", () => {
    const api = _api();
    expect(api.canAck(D({ acknowledgeable: true }))).toBe(true);
    expect(api.canAck(D({ acknowledgeable: false }))).toBe(false);
    // Fehlt die Angabe, wird NICHT geraten -> kein Schreibangebot.
    expect(api.canAck({ items: [] })).toBe(false);
    expect(api.canAck(null)).toBe(false);
  });

  // QA03 --------------------------------------------------------------------
  it("QA03: ackState", () => {
    const api = _api();
    expect(api.ackState(I({ ack: null }))).toBe("keiner");
    expect(api.ackState(I({ ack: ACK() }))).toBe("gueltig");
    expect(api.ackState(I({ ack: ACK({ outdated: true }) }))).toBe("ueberholt");
  });

  // QA04 --------------------------------------------------------------------
  it("QA04: ackLine nennt wer, wann, warum — und die Verschlechterung", () => {
    const api = _api();
    expect(api.ackLine(I({ ack: null }))).toBe("nicht quittiert");

    const t = api.ackLine(I({ ack: ACK() }));
    expect(t).toContain("Chefin, Alpha");
    expect(t).toContain("StA informiert");
    expect(t).toContain("Beleg #412");

    const u = api.ackLine(
      I({ days_inactive: 51, ack: ACK({ outdated: true, days_inactive_at_ack: 34 }) })
    );
    expect(u).toContain("ÜBERHOLT");
    expect(u).toContain("34");
    expect(u).toContain("51");

    // Fehlender Name -> ID, nicht 'undefined'.
    expect(
      api.ackLine(I({ ack: ACK({ acknowledged_by_name: null }) }))
    ).toContain("#1");
    // Fehlender Zeitstempel -> '—', nicht 1970.
    expect(api.fmtTs(null)).toBe("—");
  });

  // QA05 --------------------------------------------------------------------
  it("QA05: 'gibt es nicht' ist nicht 'darfst du nicht'", () => {
    const api = _api();
    const darf = api.ackText(D({ acknowledgeable: true }));
    expect(darf).toContain("KEIN Erledigen");
    expect(darf).toContain("Pflicht");

    const ohneStruktur = api.ackText(
      D({ acknowledgeable: false, ack_migrated: false })
    );
    expect(ohneStruktur).toContain("M027");
    expect(ohneStruktur).toContain("NICHT dasselbe wie ein fehlendes Recht");

    const ohneRecht = api.ackText(
      D({ acknowledgeable: false, ack_migrated: true })
    );
    expect(ohneRecht).toContain("escalation.ack");
    expect(ohneRecht).toContain("Struktur ist vorhanden");

    // Die beiden Aussagen sind wirklich verschieden.
    expect(ohneStruktur).not.toBe(ohneRecht);
  });

  // QA06 --------------------------------------------------------------------
  it("QA06: ohne Recht keine Bedienelemente, aber der Vermerktext bleibt", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    win.AIWCockpitEscalation.renderEscalation(
      main,
      D({
        acknowledgeable: false,
        ack_migrated: true,
        items: [I({ ack: ACK() })],
      }),
      {}
    );
    expect(main.querySelectorAll(".aiw-esk-btn").length).toBe(0);
    expect(main.querySelectorAll(".aiw-esk-reason").length).toBe(0);
    // Lesen darf man den Vermerk sehr wohl.
    expect(main.querySelector(".aiw-esk-ackline").textContent).toContain(
      "Chefin, Alpha"
    );
  });

  // QA07 --------------------------------------------------------------------
  it("QA07: mit Recht ein Feld + ein Knopf je Zeile, Beschriftung passend", () => {
    const win = _makeContext();
    const api = win.AIWCockpitEscalation;

    const ohne = win.document.createElement("main");
    api.renderEscalation(ohne, D({ items: [I({ ack: null })] }), {});
    expect(ohne.querySelectorAll(".aiw-esk-reason").length).toBe(1);
    expect(ohne.querySelector(".aiw-esk-btn").textContent).toBe("Quittieren");

    const mit = win.document.createElement("main");
    api.renderEscalation(mit, D({ items: [I({ ack: ACK() })] }), {});
    expect(mit.querySelector(".aiw-esk-btn").textContent).toBe(
      "Vermerk widerrufen"
    );
  });

  // QA08 --------------------------------------------------------------------
  it("QA08: quittieren ist kein Erledigen — Zeile bleibt und wird nicht abgestuft", () => {
    const win = _makeContext();
    const api = win.AIWCockpitEscalation;
    const daten = D({
      items: [
        I({ subject_id: 1, ack: ACK() }),
        I({ subject_id: 2, ack: null }),
      ],
    });
    const main = win.document.createElement("main");
    const r = api.renderEscalation(main, daten, {});
    // BEIDE Meldungen stehen da — die quittierte wurde nicht gefiltert.
    expect(r.count).toBe(2);
    const zeilen = main.querySelectorAll(".aiw-esk-row");
    expect(zeilen.length).toBe(2);
    // Und die quittierte behaelt ihre Schwere-Klasse (kein Abstufen).
    expect(zeilen[0].className).toContain("is-hoch");
    expect(zeilen[0].getAttribute("data-ack")).toBe("gueltig");
    expect(zeilen[1].getAttribute("data-ack")).toBe("keiner");
    // Die Reihenfolge des Backends bleibt.
    const ziele = Array.from(main.querySelectorAll(".aiw-esk-target")).map(
      (e) => e.textContent
    );
    expect(ziele).toEqual(["Fall 1", "Fall 2"]);
  });

  // QA09 --------------------------------------------------------------------
  it("QA09: leerer Pflichttext loest keinen Netzaufruf aus und wird benannt", () => {
    const win = _makeContext();
    const api = win.AIWCockpitEscalation;
    const main = win.document.createElement("main");
    let gerufen = 0;
    api.renderEscalation(main, D({ items: [I({ ack: null })] }), {
      onAck: () => {
        gerufen += 1;
      },
    });
    // Leer lassen und klicken.
    main.querySelector(".aiw-esk-btn").click();
    expect(gerufen).toBe(0);
    const res = main.querySelector(".aiw-esk-result");
    expect(res.className).toContain("is-err");
    expect(res.textContent).toContain("Begründung");

    // Nur Leerraum zaehlt ebenfalls nicht.
    main.querySelector(".aiw-esk-reason").value = "   ";
    main.querySelector(".aiw-esk-btn").click();
    expect(gerufen).toBe(0);
  });

  // QA10 --------------------------------------------------------------------
  it("QA10: onAck bekommt Schluessel und beobachteten Stand", () => {
    const win = _makeContext();
    const api = win.AIWCockpitEscalation;

    // Fallbezogene Meldung.
    let body = null;
    const m1 = win.document.createElement("main");
    api.renderEscalation(m1, D({ items: [I({ ack: null })] }), {
      onAck: (b) => {
        body = b;
      },
    });
    m1.querySelector(".aiw-esk-reason").value = "  StA informiert  ";
    m1.querySelector(".aiw-esk-btn").click();
    expect(body).toEqual({
      rule_code: "fall_ueberfaellig",
      subject_id: 7001,
      reason: "StA informiert",
      days_inactive: 34,
    });

    // SYSTEMISCHE Meldung: subject_id null bleibt null.
    let sysBody = null;
    const m2 = win.document.createElement("main");
    api.renderEscalation(
      m2,
      D({
        items: [
          I({
            rule_code: "rueckstau_hoch",
            subject_id: null,
            days_inactive: null,
            ack: null,
          }),
        ],
      }),
      {
        onAck: (b) => {
          sysBody = b;
        },
      }
    );
    m2.querySelector(".aiw-esk-reason").value = "Verteilrunde angesetzt";
    m2.querySelector(".aiw-esk-btn").click();
    expect(sysBody.rule_code).toBe("rueckstau_hoch");
    expect(sysBody.subject_id).toBe(null);
    expect(sysBody.days_inactive).toBe(null);
  });

  // QA11 --------------------------------------------------------------------
  it("QA11: onRevoke bekommt ack_id und Grund", () => {
    const win = _makeContext();
    const api = win.AIWCockpitEscalation;
    const main = win.document.createElement("main");
    let body = null;
    let ackGerufen = 0;
    api.renderEscalation(main, D({ items: [I({ ack: ACK({ ack_id: 42 }) })] }), {
      onAck: () => {
        ackGerufen += 1;
      },
      onRevoke: (b) => {
        body = b;
      },
    });
    main.querySelector(".aiw-esk-reason").value = "Verwechslung";
    main.querySelector(".aiw-esk-btn").click();
    expect(body).toEqual({ ack_id: 42, reason: "Verwechslung" });
    // Es wurde NICHT versehentlich erneut quittiert.
    expect(ackGerufen).toBe(0);
  });

  // QA12 --------------------------------------------------------------------
  it("QA12: Vermerk-Freitext bleibt Text, UTF-8 erhalten", () => {
    const win = _makeContext();
    const main = win.document.createElement("main");
    const boese = '<img src=x onerror="1">Rücksprache mit Пётр';
    win.AIWCockpitEscalation.renderEscalation(
      main,
      D({ items: [I({ ack: ACK({ reason: boese }) })] }),
      {}
    );
    expect(main.querySelector("img")).toBe(null);
    expect(main.querySelector(".aiw-esk-ackline").textContent).toContain(boese);
    expect(main.textContent).toContain("Пётр");
  });
});
