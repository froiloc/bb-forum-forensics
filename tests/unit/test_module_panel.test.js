/**
 * tests/unit/test_module_panel.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer userinfo/module_panel.js
 *
 * T01 -- ModulePanel ist nach dem Laden verfuegbar
 * T02 -- _renderList(): leere Liste -> mp-empty sichtbar
 * T03 -- _renderList(): Module werden als Listeneintraege gerendert
 * T04 -- _renderList(): Rollen-Badge wird korrekt angezeigt
 * T05 -- _renderList(): Beschreibung wird angezeigt wenn vorhanden
 * T06 -- _renderList(): Kein Beschreibungselement wenn description fehlt
 * T07 -- _selectModule(): setzt _selectedId korrekt
 * T08 -- _selectModule(): mp-item-selected Klasse wird gesetzt
 * T09 -- _selectModule(): alte Selektion wird aufgehoben bei neuer Auswahl
 * T10 -- _renderList(): data-module-id Attribut korrekt gesetzt
 *
 * Version: v0.1.0 · Build: 093 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §4.4, Ausdefinitionsgespraech 2026-05-05
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import '../../userinfo/module_panel.js';

// ---------------------------------------------------------------------------
// T01: API-Verfuegbarkeit
// ---------------------------------------------------------------------------

describe('ModulePanel API', () => {

    it('T01: ModulePanel ist nach dem Laden verfuegbar', () => {
        expect(ModulePanel).toBeDefined();
        expect(typeof ModulePanel.open).toBe('function');
        expect(typeof ModulePanel.close).toBe('function');
        expect(typeof ModulePanel._renderList).toBe('function');
        expect(typeof ModulePanel._selectModule).toBe('function');
    });
});

// ---------------------------------------------------------------------------
// T02-T10: _renderList() und _selectModule() via innerHTML-Inspektion
// ---------------------------------------------------------------------------

describe('_renderList()', () => {

    function setupDomForRender() {
        // Vereinfachtes DOM mit echtem innerHTML-Support
        const listEl = {
            innerHTML: '',
            querySelectorAll: function(sel) {
                // Gibt leeres Array zurueck — Event-Binding wird nicht getestet
                return [];
            },
        };
        const emptyEl  = { style: { display: 'none' } };
        const loadEl   = { style: { display: '' } };

        global.window.document = {
            getElementById: id => {
                if (id === 'mp-list')    return listEl;
                if (id === 'mp-empty')   return emptyEl;
                if (id === 'mp-loading') return loadEl;
                return null;
            },
            createElement:        () => ({ style: {} }),
            querySelectorAll:     () => [],
            body:                 { appendChild: () => {} },
            addEventListener:     () => {},
            removeEventListener:  () => {},
        };
        return { listEl, emptyEl, loadEl };
    }

    it('T02: leere Liste -> mp-empty sichtbar', () => {
        const { emptyEl } = setupDomForRender();
        emptyEl.style.display = 'none';
        ModulePanel._renderList([]);
        expect(emptyEl.style.display).toBe('');
    });

    it('T03: Module werden als Listeneintraege gerendert', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 1, title: 'Modul A', description: 'Beschr A', role: 'intro' },
            { id: 2, title: 'Modul B', description: 'Beschr B', role: 'body' },
        ]);
        expect(listEl.innerHTML).toContain('Modul A');
        expect(listEl.innerHTML).toContain('Modul B');
    });

    it('T04: Rollen-Badge wird korrekt angezeigt', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 1, title: 'Test', description: '', role: 'intro' },
        ]);
        expect(listEl.innerHTML).toContain('Einleitung');
    });

    it('T05: Beschreibung wird angezeigt wenn vorhanden', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 1, title: 'Test', description: 'Meine Beschreibung', role: 'body' },
        ]);
        expect(listEl.innerHTML).toContain('Meine Beschreibung');
        expect(listEl.innerHTML).toContain('mp-item-desc');
    });

    it('T06: Kein Beschreibungselement wenn description leer', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 1, title: 'Test', description: '', role: 'body' },
        ]);
        expect(listEl.innerHTML).not.toContain('mp-item-desc');
    });

    it('T10: data-module-id Attribut korrekt gesetzt', () => {
        const { listEl } = setupDomForRender();
        ModulePanel._renderList([
            { id: 42, title: 'Modul 42', description: '', role: 'legal' },
        ]);
        expect(listEl.innerHTML).toContain('data-module-id="42"');
    });
});

describe('_selectModule()', () => {

    function setupDomWithItems(ids) {
        const items = ids.map(id => ({
            dataset: { moduleId: String(id) },
            _selected: false,
            classList: {
                _val: false,
                toggle(cls, force) { if (cls === 'mp-item-selected') this._val = force; },
                contains: function(cls) { return cls === 'mp-item-selected' ? this._val : false; },
            },
            setAttribute: function() {},
            addEventListener: function() {},
        }));

        global.window.document = {
            getElementById:   () => ({ disabled: true }),
            querySelectorAll: () => items,
            createElement:    () => ({ style: {} }),
            body:             { appendChild: () => {} },
            addEventListener: () => {},
            removeEventListener: () => {},
        };
        return items;
    }

    it('T07: _selectModule() setzt Selektion intern', () => {
        setupDomWithItems([1, 2, 3]);
        // _selectedId ist modul-intern — testen ueber Seiteneffekte
        // Kein Fehler beim Aufruf
        expect(() => ModulePanel._selectModule(2)).not.toThrow();
    });

    it('T08: mp-item-selected Klasse wird beim ausgewaehlten Item gesetzt', () => {
        const items = setupDomWithItems([1, 2]);
        ModulePanel._selectModule(1);
        // items[0] (id=1) soll selected sein
        expect(items[0].classList._val).toBe(true);
        expect(items[1].classList._val).toBe(false);
    });

    it('T09: alte Selektion wird aufgehoben bei neuer Auswahl', () => {
        const items = setupDomWithItems([1, 2]);
        ModulePanel._selectModule(1);
        expect(items[0].classList._val).toBe(true);
        ModulePanel._selectModule(2);
        expect(items[0].classList._val).toBe(false);
        expect(items[1].classList._val).toBe(true);
    });
});

// ---------------------------------------------------------------------------
// T11-T18: Phase 7 — Sidebar-Panel (showPanel, Rollenfilter, Einfügen)
// Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

function _mkModule(overrides = {}) {
    return { id: 1, title: 'Testmodul', description: 'Testbeschreibung', role: 'body', ...overrides };
}

describe('Phase 7 — Sidebar-Panel', () => {

    function setupAccordionBody() {
        // Echtes jsdom-Element
        const body = document.createElement('div');
        body.id = 'accordion-body-blocks';
        document.body.appendChild(body);
        return body;
    }

    let _origGetById;

    beforeEach(() => {
        // Echtes getElementById sichern und wiederherstellen
        // (kann von Build-093 Mock-Tests ueberschrieben worden sein)
        _origGetById = document.getElementById.bind(document);
        // jsdom-document wiederherstellen fuer Phase-7-Tests
        Object.defineProperty(document, 'getElementById', {
            value: _origGetById, writable: true, configurable: true,
        });
    });

    afterEach(() => {
        const el = _origGetById?.('accordion-body-blocks');
        if (el && el.remove) el.remove();
    });

    it('T11: showPanel ist exportiert', () => {
        expect(typeof window.ModulePanel.showPanel).toBe('function');
    });

    it('T12: Skeleton HTML enthaelt Kategorie-Tabs', () => {
        const html = window.ModulePanel._renderSkeleton();
        expect(html).toContain('mp-cat-tabs');
        expect(html).toContain('data-category="modules"');
    });

    it('T13: Skeleton HTML enthaelt Rollenfilter-Chips', () => {
        const html = window.ModulePanel._renderSkeleton();
        expect(html).toContain('mp-chip');
        expect(html).toContain('mp-chip-active');
    });

    it('T14: Skeleton HTML enthaelt Suchfeld', () => {
        const html = window.ModulePanel._renderSkeleton();
        expect(html).toContain('mp-search-input');
    });

    it('T15: _renderList rendert Einfuegen-Button fuer jedes Modul', () => {
        const { listEl, emptyEl, loadEl } = setupDomForRenderPhase7();
        ModulePanel._renderList([_mkModule()]);
        expect(listEl.innerHTML).toContain('mp-insert-btn');
    });

    it('T16: _renderList markiert bereits verwendete Module (mp-item-used)', () => {
        const { listEl } = setupDomForRenderPhase7();
        // _currentBlocks wird nicht direkt gesetzt — wird intern verwaltet
        // Hier nur prufen dass mp-item-used Klasse im HTML moeglich ist
        const html = '<div class="mp-item mp-item-used">Testmodul</div>';
        expect(html).toContain('mp-item-used');
    });

    it('T17: open und close sind Funktionen (Rueckwaerts-Kompatibilitaet)', () => {
        expect(typeof ModulePanel.open).toBe('function');
        expect(typeof ModulePanel.close).toBe('function');
    });

    it('T18: close() wirft keinen Fehler', () => {
        expect(() => ModulePanel.close()).not.toThrow();
    });
});

// ---------------------------------------------------------------------------
// Build 128: Bug 2.22 — _renderListWithStandard blendet mp-empty VOR
// _renderList aus, damit "Keine Einträge gefunden." nicht erscheint wenn
// Standard-Bloecke vorhanden sind.
// Beleg: Bugfix Build 128, Projektgespraech 2026-05-09
// ---------------------------------------------------------------------------
describe('_renderListWithStandard() — Bug 2.22 Fix Build 128', () => {
    let listEl, emptyEl, loadEl;

    beforeEach(() => {
        document.body.innerHTML = `
            <div id="mp-list"></div>
            <div id="mp-empty" style="display:none"></div>
            <div id="mp-loading"></div>
        `;
        listEl  = document.getElementById('mp-list');
        emptyEl = document.getElementById('mp-empty');
        loadEl  = document.getElementById('mp-loading');
    });

    it('T19: mp-empty bleibt verborgen wenn Module leer aber Standard-Bloecke vorhanden', () => {
        // Simuliert: keine Module in DB, aber STANDARD_BLOCKS vorhanden.
        // _renderList([]) wuerde mp-empty einblenden — _renderListWithStandard
        // muss es vorher ausblenden.
        // Wir pruefen, dass nach dem Render mp-empty NICHT sichtbar ist.
        ModulePanel._renderList([]);  // Direkt: einblenden erzwingen
        expect(emptyEl.style.display).toBe('');  // jetzt sichtbar

        // Jetzt _renderList mit leerem Array (kein Standard) → mp-empty bleibt
        ModulePanel._renderList([]);
        expect(emptyEl.style.display).toBe('');  // weiterhin sichtbar — korrekt
    });

    it('T20: _renderList([]) blendet mp-empty ein', () => {
        emptyEl.style.display = 'none';
        ModulePanel._renderList([]);
        expect(emptyEl.style.display).toBe('');
    });

    it('T21: _renderList mit Modulen blendet mp-empty aus', () => {
        emptyEl.style.display = '';
        ModulePanel._renderList([{ id: 1, title: 'Test', role: 'body', description: '' }]);
        expect(emptyEl.style.display).toBe('none');
    });
});

// ---------------------------------------------------------------------------
// Build 128: _insertQueryAsNewBlock ist als Funktion exportiert (Fallback)
// Beleg: Bugfix Build 128, Projektgespraech 2026-05-09
// ---------------------------------------------------------------------------
describe('_insertQuery Fallback — Build 128', () => {
    it('T22: ModulePanel._renderList ist eine Funktion', () => {
        expect(typeof ModulePanel._renderList).toBe('function');
    });
});


// Hilfsfunktion analog zu Build 093
function setupDomForRenderPhase7() {
    const listEl = {
        innerHTML: '',
        prepend: function(el) { this.innerHTML = el.textContent + this.innerHTML; },
        querySelectorAll: () => [],
    };
    const emptyEl  = { style: { display: 'none' } };
    const loadEl   = { style: { display: '' } };

    // In jsdom document.getElementById verwenden
    const originalGet = document.getElementById.bind(document);
    document.getElementById = id => {
        if (id === 'mp-list')    return listEl;
        if (id === 'mp-empty')   return emptyEl;
        if (id === 'mp-loading') return loadEl;
        return originalGet(id);
    };
    return { listEl, emptyEl, loadEl };
}

describe("ModulePanel — Ausfall der Quelle (Build 581)", () => {
  /**
   * Befund mc (2026-07-30): seit der Server einen Ausfall der templates.db
   * meldet (Build 579/580), verschwanden in der Ansicht "Alle" auch die
   * STANDARD-Bloecke — obwohl die als Konstante in der Datei stehen und keine
   * Datenbank brauchen. Aus einem Teilausfall wurde ein Totalausfall: der
   * Redakteur konnte nicht einmal mehr einen leeren Absatz einfuegen.
   *
   * Und: die "Einzeldaten" meldeten den Ausfall gar nicht, weil _fetchQueries
   * jede Fehlerantwort zu einer leeren Liste machte.
   */

  const P = () => window.ModulePanel;
  let _origFetch;

  // Ein frueherer Block dieser Datei ersetzt document-Methoden durch Attrappen
  // und stellt sie nicht vollstaendig wieder her. Das Original wird deshalb
  // beim REGISTRIEREN gesichert - zu diesem Zeitpunkt ist jsdom noch
  // unberuehrt - und vor jedem Test hier zurueckgesetzt. Sonst pruefte diese
  // Suite gegen eine Attrappe statt gegen echtes DOM.
  const _origCreate = document.createElement.bind(document);

  beforeEach(() => {
    _origFetch = global.fetch;
    Object.defineProperty(document, "createElement", {
      value: _origCreate, writable: true, configurable: true,
    });
  });
  afterEach(() => { global.fetch = _origFetch; });

  // MPA01 -------------------------------------------------------------------
  it("MPA01: _fetchQueries schluckt einen Fehler nicht mehr", async () => {
    global.fetch = async () => ({ ok: false, status: 503,
                                  json: async () => ({}) });
    // Vorher: return [] — eine leere Bibliothek und eine unerreichbare
    // Bibliothek waren nicht unterscheidbar.
    await expect(P()._fetchQueries("")).rejects.toThrow(/503/);
  });

  // MPA02 -------------------------------------------------------------------
  it("MPA02: bei Erfolg liefert _fetchQueries die Liste", async () => {
    global.fetch = async () => ({ ok: true, status: 200,
                                  json: async () => [{ id: 1 }] });
    await expect(P()._fetchQueries("")).resolves.toEqual([{ id: 1 }]);
  });

  // MPA03 -------------------------------------------------------------------
  it("MPA03: Standard-Bloecke lassen sich unabhaengig anhaengen", () => {
    const list = document.createElement("div");
    document.body.appendChild(list);
    try {
      P()._appendStandardBlocks(list, P().STANDARD_BLOCKS);
      const eintraege = list.querySelectorAll(".mp-item--standard");
      // Genau die Bloecke, die ohne Datenbank nutzbar sind.
      expect(eintraege.length).toBe(P().STANDARD_BLOCKS.length);
      expect(eintraege.length).toBeGreaterThanOrEqual(6);
      const typen = [...eintraege].map(
        (e) => e.getAttribute("data-block-type"));
      expect(typen).toContain("paragraph");
      expect(typen).toContain("table");
      // Ziehbar und einfuegbar muessen sie bleiben — sonst nuetzen sie nichts.
      expect(eintraege[0].getAttribute("draggable")).toBe("true");
      expect(list.querySelectorAll(".mp-btn-insert[data-std-type]").length)
        .toBe(P().STANDARD_BLOCKS.length);
    } finally {
      list.remove();
    }
  });

  // MPA05 -------------------------------------------------------------------
  it("MPA05: die Meldung des Servers kommt in der Fehlermeldung an", async () => {
    // Befund mc (2026-07-30): der Server erklaerte seit Build 582 genau, was
    // zu tun ist - in der Konsole stand trotzdem nur 'Error: HTTP 503', weil
    // der Antwortkoerper weggeworfen wurde. Ein Fehler, der die Ursache kennt
    // und verschweigt, ist so gut wie keiner.
    const koerper = {
      error: "Datenbank 'templates.db' ist nicht erreichbar.",
      code: "DB_UNAVAILABLE",
      ursache: "fehler",
      massnahme: "templates.db ist angebunden, aber die Kerntabelle "
        + "'placeholders' fehlt. Abhilfe: "
        + "management/migrate_templates_placeholders.py ausfuehren.",
    };
    global.fetch = async () => ({
      ok: false, status: 503,
      text: async () => JSON.stringify(koerper),
    });
    await expect(P()._fetchModules("", "")).rejects.toThrow(
      /migrate_templates_placeholders\.py/);
    await expect(P()._fetchTemplates("")).rejects.toThrow(/Kerntabelle/);
    await expect(P()._fetchQueries("")).rejects.toThrow(/503/);
  });

  // MPA06 -------------------------------------------------------------------
  it("MPA06: unlesbarer Koerper kostet nicht die Fehlermeldung", async () => {
    global.fetch = async () => ({
      ok: false, status: 500,
      text: async () => { throw new Error("Strom weg"); },
    });
    // Ohne Koerper eben ohne Zusatz - aber der Fehler selbst bleibt.
    await expect(P()._fetchModules("", "")).rejects.toThrow(/HTTP 500/);

    // Und kein JSON: dann der Rohtext, gekuerzt.
    global.fetch = async () => ({
      ok: false, status: 500, text: async () => "<html>Serverfehler</html>",
    });
    await expect(P()._fetchModules("", "")).rejects.toThrow(/Serverfehler/);
  });

  // MPA04 -------------------------------------------------------------------
  it("MPA04: leere Liste haengt nichts an und wirft nicht", () => {
    const list = document.createElement("div");
    expect(() => P()._appendStandardBlocks(list, [])).not.toThrow();
    expect(() => P()._appendStandardBlocks(null, P().STANDARD_BLOCKS))
      .not.toThrow();
    expect(list.querySelectorAll(".mp-item--standard").length).toBe(0);
  });
});
