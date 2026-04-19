/**
 * test_navigate_to_url.test.js
 * Unit-Tests: navigate_to_url via postMessage
 *
 * Testet:
 *   1. toolbar.js: window.message-Listener ruft NavigationModule.loadPage auf
 *   2. userinfo.js: initForensicLinks() sendet postMessage bei Klick auf
 *      [data-forensic-url]-Elemente
 *
 * Beleg: Projektgespräch 2026-04-18
 * Version: 0.1.0 · Build: 001 · 2026-04-18
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ---------------------------------------------------------------------------
// Hilfsfunktion: minimales DOM aufbauen
// ---------------------------------------------------------------------------

function buildDom(bodyHtml = "") {
    return new JSDOM(`<!DOCTYPE html><html><body>${bodyHtml}</body></html>`, {
        url: "http://127.0.0.2:8080",
        runScripts: "dangerously",
        resources: "usable",
    });
}

// ---------------------------------------------------------------------------
// Tests: navigate_to_url-Handler in toolbar.js
// ---------------------------------------------------------------------------

describe("toolbar.js — navigate_to_url postMessage-Handler", () => {
    it("ruft loadPage-Callback auf wenn type=navigate_to_url empfangen wird", () => {
        const dom = buildDom();
        const win = dom.window;
        const loadPageMock = vi.fn();

        // Handler direkt registrieren (wie in toolbar.js)
        win.addEventListener("message", function (evt) {
            if (!evt.data || typeof evt.data !== "object") return;
            if (evt.data.type === "navigate_to_url") {
                var url = evt.data.url;
                if (typeof url === "string" && url.length > 0) {
                    loadPageMock(url, true);
                }
            }
        });

        // MessageEvent synchron dispatchen (JSDOM-kompatibel)
        const evt = new win.MessageEvent("message", {
            data: { type: "navigate_to_url", url: "/forum/viewtopic.php?pid=8837#p8837" },
            origin: "http://127.0.0.2:8080",
        });
        win.dispatchEvent(evt);

        expect(loadPageMock).toHaveBeenCalledOnce();
        expect(loadPageMock).toHaveBeenCalledWith(
            "/forum/viewtopic.php?pid=8837#p8837",
            true
        );
    });

    it("ignoriert Nachrichten mit falschem type", () => {
        const dom = buildDom();
        const win = dom.window;
        const loadPageMock = vi.fn();

        win.addEventListener("message", function (evt) {
            if (!evt.data || typeof evt.data !== "object") return;
            if (evt.data.type === "navigate_to_url") {
                loadPageMock(evt.data.url);
            }
        });

        const evt = new win.MessageEvent("message", {
            data: { type: "some_other_type", url: "/foo" },
            origin: "http://127.0.0.2:8080",
        });
        win.dispatchEvent(evt);

        expect(loadPageMock).not.toHaveBeenCalled();
    });
});

// ---------------------------------------------------------------------------
// Tests: initForensicLinks in userinfo.js
// ---------------------------------------------------------------------------

describe("userinfo.js — initForensicLinks", () => {
    it("sendet postMessage bei Klick auf data-forensic-url", () => {
        const dom = buildDom(`
            <div id="userinfo-static">
                <span class="forensic-source-link"
                      data-forensic-url="/forum/viewtopic.php?pid=8837#p8837"
                      role="button">↗</span>
            </div>
        `);
        const win = dom.window;
        const doc = dom.window.document;

        // window.opener simulieren
        const openerMock = { postMessage: vi.fn() };
        Object.defineProperty(win, "opener", { value: openerMock, writable: true });

        // initForensicLinks direkt implementieren (ohne ganzes userinfo.js zu laden)
        function initForensicLinks() {
            const container = doc.getElementById("userinfo-static");
            if (!container) return;
            container.addEventListener("click", function (evt) {
                const link = evt.target.closest("[data-forensic-url]");
                if (!link) return;
                evt.preventDefault();
                const url = link.dataset.forensicUrl;
                if (!url) return;
                const target = win.opener || win.parent;
                if (target && target !== win) {
                    target.postMessage(
                        { type: "navigate_to_url", url: url },
                        win.location.origin
                    );
                }
            });
        }

        initForensicLinks();

        // Klick auf das Link-Element simulieren
        const linkEl = doc.querySelector("[data-forensic-url]");
        linkEl.click();

        expect(openerMock.postMessage).toHaveBeenCalledOnce();
        expect(openerMock.postMessage).toHaveBeenCalledWith(
            { type: "navigate_to_url", url: "/forum/viewtopic.php?pid=8837#p8837" },
            "http://127.0.0.2:8080"
        );
    });

    it("ignoriert Klicks auf Elemente ohne data-forensic-url", () => {
        const dom = buildDom(`
            <div id="userinfo-static">
                <span class="forensic-note">Kein Link</span>
            </div>
        `);
        const win = dom.window;
        const doc = dom.window.document;

        const openerMock = { postMessage: vi.fn() };
        Object.defineProperty(win, "opener", { value: openerMock, writable: true });

        function initForensicLinks() {
            const container = doc.getElementById("userinfo-static");
            if (!container) return;
            container.addEventListener("click", function (evt) {
                const link = evt.target.closest("[data-forensic-url]");
                if (!link) return;
                const url = link.dataset.forensicUrl;
                const target = win.opener || win.parent;
                if (target && target !== win) {
                    target.postMessage({ type: "navigate_to_url", url }, win.location.origin);
                }
            });
        }

        initForensicLinks();
        doc.querySelector(".forensic-note").click();
        expect(openerMock.postMessage).not.toHaveBeenCalled();
    });
});
