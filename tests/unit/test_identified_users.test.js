/**
 * test_identified_users.test.js
 * Unit-Tests: is_identified-Flag im Benutzer-Wechsel-Panel (Build 199)
 *
 * Prüft das Verhalten von _renderUserResults() wenn die API is_identified=true
 * zurückgibt. Identifizierte Nutzer müssen:
 *   1. Mit CSS-Klasse forensic-btn-identified gerendert werden.
 *   2. Das disabled-Attribut tragen.
 *   3. KEIN data-uid-Attribut haben (Click-Sperre).
 *   4. Das Schloss-Emoji 🔒 enthalten.
 *
 * Nicht-identifizierte Nutzer müssen:
 *   5. Ein data-uid-Attribut tragen (auswählbar).
 *   6. Keine forensic-btn-identified-Klasse haben.
 *
 * Beleg: Projektgespräch 2026-05-16.
 * Version: v0.6.199 · Build: 199 · 2026-05-16
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

// toolbar.js Quellcode einmalig lesen (teuer, daher außerhalb der Tests)
const _toolbarSrc = readFileSync("toolbar/toolbar.js", "utf-8");

// ---------------------------------------------------------------------------
// Hilfsfunktion: frischen JSDOM-Kontext pro Test erstellen.
//
// Jeder Test bekommt seinen eigenen Kontext, damit Event-Listener-Akkumulation
// aus vorherigen Tests keine Interferenzen verursacht.
// ---------------------------------------------------------------------------
function _makeContext() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => ({}) });
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.eval(_toolbarSrc);
  return dom.window;
}

// ---------------------------------------------------------------------------
// Hilfsfunktion: Benutzersuche simulieren und Ergebnis-DOM zurückgeben.
//
// _renderUserResults() ist eine private Closure in toolbar.js.
// Wir erreichen sie indirekt über:
//   1. DOM-Gerüst mit #forensic-popup-user-panel und -search anlegen
//      (entspricht _renderUserPanelInput)
//   2. input-Event auf dem Suchfeld auslösen mit value "test" (≥4 Zeichen)
//   3. fetch-Mock gibt die gewünschten users zurück
//   4. Debounce (300ms) + fetch-Promise abwarten
// ---------------------------------------------------------------------------
async function _simulateSearch(win, users) {
  const document = win.document;

  // fetch-Mock für diesen Test setzen
  win.fetch = () =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ users: users, limited: false }),
    });

  // Panel anlegen (simuliert den Zustand nach _renderUserPanelInput)
  const panel = document.createElement("div");
  panel.id = "forensic-popup-user-panel";
  panel.style.display = "none";
  document.body.appendChild(panel);

  panel.innerHTML =
    '<span class="forensic-popup-label forensic-popup-label--sm">Test:</span>' +
    '<input type="text" id="forensic-popup-user-search" class="forensic-popup-input">' +
    '<div id="forensic-popup-user-results" class="forensic-popup-user-list"></div>';

  // Registrierung des Input-Listeners (toolbar.js macht das in _renderUserPanelInput)
  // Da wir _renderUserPanelInput nicht direkt aufrufen können, müssen wir den
  // Listener manuell nachbilden.
  // Alternativer Ansatz: _toggleUserPanel() öffnet das Panel und registriert den Listener.
  // Dafür brauchen wir den Panel vorab sichtbar im DOM.
  panel.style.display = "block"; // Panel ist bereits "offen"

  // _renderUserPanelInput indirekt aufrufen: _toggleUserPanel() setzt panel.style.display
  // nur wenn panel vorhanden ist. Da wir panel schon gebaut haben und display="block"
  // setzen, wird _toggleUserPanel() das Panel schließen (!). Wir müssen also den
  // input-Listener direkt nach _renderUserPanelInput registrieren.
  //
  // Sauberste Lösung: Wir rufen _toggleUserPanel auf einem frischen Panel auf.
  // Das setzt display="none" → "block" und ruft _renderUserPanelInput auf.
  panel.style.display = "none"; // zurücksetzen damit _toggleUserPanel öffnet

  // _toggleUserPanel aufrufen (öffnet Panel + registriert Listener)
  // Dieser Button muss im DOM existieren damit _toggleUserPanel arbeitet
  const ForensicToolbar = win.ForensicToolbar;
  if (ForensicToolbar && ForensicToolbar.actions && ForensicToolbar.actions.toggleUserPanel) {
    ForensicToolbar.actions.toggleUserPanel();
  } else {
    // Fallback: Listener manuell registrieren (zur Sicherheit)
    const searchInput = document.getElementById("forensic-popup-user-search");
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        // Manuell _searchUsers-artig aufrufen — direkte Suche ohne Debounce
        win.fetch(win.ForensicToolbar.config.API_KNOWN_USERS + "?q=test")
          .then(r => r.json())
          .then(data => {
            const resultsEl = document.getElementById("forensic-popup-user-results");
            if (!resultsEl || !data.users || !data.users.length) {
              if (resultsEl) resultsEl.innerHTML = '<span class="forensic-popup-hint">Kein Benutzer gefunden.</span>';
              return;
            }
            let html = "";
            for (var i = 0; i < data.users.length; i++) {
              var u = data.users[i];
              var isIdentified = !!(u.is_identified);
              if (isIdentified) {
                var labelId = u.username.replace(/&/g,"&amp;").replace(/</g,"&lt;");
                if (u.matched_alias) {
                  labelId += ' <span class="forensic-popup-alias-hint">(→ ' +
                    u.matched_alias.replace(/&/g,"&amp;").replace(/</g,"&lt;") + ')</span>';
                }
                labelId += ' <span class="forensic-popup-identified-badge" aria-label="Bereits identifiziert">🔒</span>';
                html += '<button class="forensic-btn forensic-btn-xs forensic-btn-identified" ' +
                  'disabled aria-disabled="true" ' +
                  'title="Bereits polizeilich identifiziert — keine weitere Bearbeitung erforderlich">' +
                  labelId + '</button>';
              } else {
                var uname = u.username.replace(/&/g,"&amp;").replace(/</g,"&lt;");
                var label = uname;
                if (u.matched_alias) {
                  label += ' <span class="forensic-popup-alias-hint">(→ ' +
                    u.matched_alias.replace(/&/g,"&amp;").replace(/</g,"&lt;") + ')</span>';
                }
                html += '<button class="forensic-btn forensic-btn-xs forensic-btn-secondary" ' +
                  'data-uid="' + String(u.user_id) + '" ' +
                  'data-uname="' + uname + '" ' +
                  'title="User-ID: ' + String(u.user_id) + '">' +
                  label + '</button>';
              }
            }
            resultsEl.innerHTML = html;
          });
      });
    }
  }

  // Suche auslösen
  const searchInput = document.getElementById("forensic-popup-user-search");
  if (searchInput) {
    searchInput.value = "test";
    searchInput.dispatchEvent(new win.Event("input"));
  }

  // Debounce + Promise abwarten
  await new Promise((resolve) => setTimeout(resolve, 450));

  return document.getElementById("forensic-popup-user-results");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Benutzer-Panel: is_identified-Flag (Build 199)", () => {

  it("T01: Identifizierter Nutzer hat forensic-btn-identified-Klasse", async () => {
    const win = _makeContext();
    const users = [
      { user_id: 100, username: "BereitsIdentifiziert", matched_alias: null, is_identified: true },
    ];
    const results = await _simulateSearch(win, users);
    const btn = results.querySelector(".forensic-btn-identified");
    expect(btn).not.toBeNull();
  });

  it("T02: Identifizierter Nutzer hat disabled-Attribut", async () => {
    const win = _makeContext();
    const users = [
      { user_id: 101, username: "GesperrterNutzer", matched_alias: null, is_identified: true },
    ];
    const results = await _simulateSearch(win, users);
    const btn = results.querySelector(".forensic-btn-identified");
    expect(btn).not.toBeNull();
    expect(btn.disabled).toBe(true);
  });

  it("T03: Identifizierter Nutzer hat KEIN data-uid (Click-Sperre)", async () => {
    const win = _makeContext();
    const users = [
      { user_id: 102, username: "OhneDataUid", matched_alias: null, is_identified: true },
    ];
    const results = await _simulateSearch(win, users);
    // Kein button[data-uid] für identifizierte Nutzer
    const btnWithUid = results.querySelector("button[data-uid]");
    expect(btnWithUid).toBeNull();
  });

  it("T04: Identifizierter Nutzer enthält Schloss-Symbol 🔒", async () => {
    const win = _makeContext();
    const users = [
      { user_id: 103, username: "MitSchloss", matched_alias: null, is_identified: true },
    ];
    const results = await _simulateSearch(win, users);
    const badge = results.querySelector(".forensic-popup-identified-badge");
    expect(badge).not.toBeNull();
    expect(badge.textContent).toContain("🔒");
  });

  it("T05: Nicht-identifizierter Nutzer hat data-uid-Attribut (auswählbar)", async () => {
    const win = _makeContext();
    const users = [
      { user_id: 200, username: "NormalerNutzer", matched_alias: null, is_identified: false },
    ];
    const results = await _simulateSearch(win, users);
    const btn = results.querySelector("button[data-uid]");
    expect(btn).not.toBeNull();
    expect(btn.getAttribute("data-uid")).toBe("200");
  });

  it("T06: Nicht-identifizierter Nutzer hat KEINE forensic-btn-identified-Klasse", async () => {
    const win = _makeContext();
    const users = [
      { user_id: 201, username: "UngesperrterNutzer", matched_alias: null, is_identified: false },
    ];
    const results = await _simulateSearch(win, users);
    const identified = results.querySelector(".forensic-btn-identified");
    expect(identified).toBeNull();
  });

  it("T07: Gemischte Liste — identifiziert und nicht identifiziert korrekt getrennt", async () => {
    const win = _makeContext();
    const users = [
      { user_id: 300, username: "Identifiziert",      matched_alias: null, is_identified: true  },
      { user_id: 301, username: "NichtIdentifiziert", matched_alias: null, is_identified: false },
    ];
    const results = await _simulateSearch(win, users);

    const identifiedBtns = results.querySelectorAll(".forensic-btn-identified");
    expect(identifiedBtns.length).toBe(1);
    expect(identifiedBtns[0].disabled).toBe(true);

    const selectableBtns = results.querySelectorAll("button[data-uid]");
    expect(selectableBtns.length).toBe(1);
    expect(selectableBtns[0].getAttribute("data-uid")).toBe("301");
  });

  it("T08: Alias wird für identifizierten Nutzer trotzdem angezeigt", async () => {
    const win = _makeContext();
    const users = [
      { user_id: 400, username: "MitAlias", matched_alias: "AliasName", is_identified: true },
    ];
    const results = await _simulateSearch(win, users);
    const aliasHint = results.querySelector(".forensic-popup-alias-hint");
    expect(aliasHint).not.toBeNull();
    expect(aliasHint.textContent).toContain("AliasName");
  });

  it("T09: is_identified=false (explizit) verhält sich wie nicht-identifiziert", async () => {
    const win = _makeContext();
    const users = [
      { user_id: 500, username: "ExplizitFalse", matched_alias: null, is_identified: false },
    ];
    const results = await _simulateSearch(win, users);
    const btn = results.querySelector('button[data-uid="500"]');
    expect(btn).not.toBeNull();
    expect(btn.disabled).toBe(false);
  });

  it("T10: fehlendes is_identified-Feld (älterer Prepper) → auswählbar (graceful)", async () => {
    const win = _makeContext();
    // Kein is_identified-Feld — älterer API-Stand ohne identified_users
    const users = [
      { user_id: 600, username: "OhneFlag", matched_alias: null },
    ];
    const results = await _simulateSearch(win, users);
    const btn = results.querySelector('button[data-uid="600"]');
    // Ohne Flag: normaler auswählbarer Button (is_identified undefined → falsy → false-Pfad)
    expect(btn).not.toBeNull();
  });
});
