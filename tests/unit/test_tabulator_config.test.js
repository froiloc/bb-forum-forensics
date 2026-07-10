/**
 * test_tabulator_config.test.js
 * Unit-Tests: buildTabulatorConfig() aus userinfo.js (Pager-Fix, Variante A).
 *
 * Beleg: Bauplan Userinfo-Verschoenerung Pkt.7, Entscheidung 2026-07-10.
 * Ursache (Console-Diagnose): maxHeight:'600px' + .tabulator{overflow:hidden}
 * kappte den darunter liegenden Pager. Fix: kein maxHeight, height:false.
 *
 * Anti-"gruen aber tot": die ECHTE Funktion wird per Klammer-Matching aus der
 * Datei extrahiert und evaluiert (reine Funktion, kein DOM/Tabulator noetig).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

function extractFn(src, name) {
    const start = src.indexOf("function " + name);
    if (start < 0) throw new Error("Funktion nicht gefunden: " + name);
    const braceStart = src.indexOf("{", start);
    let depth = 0, i = braceStart;
    for (; i < src.length; i++) {
        const c = src[i];
        if (c === "{") depth++;
        else if (c === "}") { depth--; if (depth === 0) { i++; break; } }
    }
    return src.slice(start, i);
}

const SRC = readFileSync(join(__dirname, "../../userinfo/userinfo.js"), "utf-8");
// eslint-disable-next-line no-new-func
const buildTabulatorConfig = new Function(
    `${extractFn(SRC, "buildTabulatorConfig")}\nreturn buildTabulatorConfig;`
)();

const mkRows = (n) => Array.from({ length: n }, (_, i) => ({ id: i }));

describe("userinfo.js — buildTabulatorConfig()", () => {
    it("Variante A: height=false, KEIN maxHeight (kein Pager-Clipping)", () => {
        const cfg = buildTabulatorConfig(mkRows(10), []);
        expect(cfg.height).toBe(false);
        expect("maxHeight" in cfg).toBe(false);
    });

    it("Paginierung erst ab >50 Zeilen aktiv", () => {
        expect(buildTabulatorConfig(mkRows(50), []).pagination).toBe(false);
        expect(buildTabulatorConfig(mkRows(51), []).pagination).toBe("local");
    });

    it("paginationSize=50 und de-de-Labels vorhanden", () => {
        const cfg = buildTabulatorConfig(mkRows(60), []);
        expect(cfg.paginationSize).toBe(50);
        expect(cfg.locale).toBe("de-de");
        expect(cfg.langs["de-de"].pagination.next).toBe("Weiter");
    });

    it("data und columns werden durchgereicht", () => {
        const rows = mkRows(3), cols = [{ title: "X" }];
        const cfg = buildTabulatorConfig(rows, cols);
        expect(cfg.data).toBe(rows);
        expect(cfg.columns).toBe(cols);
    });
});
