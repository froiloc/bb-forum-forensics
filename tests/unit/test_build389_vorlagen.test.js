/**
 * tests/unit/test_build389_vorlagen.test.js
 * IT-Forensisches Ermittlungswerkzeug — Regressionstests Build 389
 *
 * Prueft die Frontend-Neuerungen von Build 389 gegen die ECHTEN Funktionen
 * (Import der Produktivdateien, kein nachgebauter Ersatzcode — 'gruen aber
 * tot' waere hier besonders gefaehrlich, weil an diesen Pfaden haengt, ob
 * Chip-HTML in die Datenbank und damit in den Siegel-Hash gelangt).
 *
 * Getestet:
 *   A -- PlaceholderChips.mapBlockTexts / collectBlockTexts
 *   B -- hydrateBlockData / dehydrateBlockData (Rundreise, TABELLEN!)
 *   C -- extractFieldsFromBlockData (Felder aus Tabellenzellen)
 *   D -- ValidationRules (Katalog, Uppercase-Normalisierung, Ablehnung)
 *   E -- ModulePanel._renderTemplateList (Reiter 'Vorlagen')
 *
 * Version: v0.7.389 · Build: 389 · 2026-07-12
 * Beleg: Bauplan Build 389, Projektgespraech 2026-07-12
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import '../../userinfo/placeholder_chips.js';
import '../../userinfo/validation_rules.js';
import '../../userinfo/module_panel.js';

let Chips;
let Rules;
let Panel;

/** Der Feststellungs-Tabellenblock aus der Spurenvermerk-Vorlage (Build 388). */
const TABLE_BLOCK = {
    withHeadings: false,
    content: [
        ['Registrierungsdatum', '{{a:user.registered_datetime|unbekannt}}'],
        ['Genutztes Passwort', '{{o:passwort|unbekannt|Sofern belegbar}}'],
        ['Anzahl Beitr\u00e4ge', '{{a:user.posts_total|0}}'],
    ],
};

beforeEach(() => {
    Chips = window.PlaceholderChips;
    Rules = window.ValidationRules;
    Panel = window.ModulePanel;

    // Regel-Katalog setzen, ohne HTTP — Inhalt entspricht der ausgelieferten
    // config.yaml (validation.rules.spurennummer).
    Rules._setRulesForTest({
        spurennummer: {
            pattern: '^(AIW|R3X|FBL|AMZ|BRU)\\d+$',
            transform: 'upper',
            hint: 'Beh\u00f6rdenk\u00fcrzel gefolgt von Ziffern, z. B. AIW12345',
        },
    });
});

// ---------------------------------------------------------------------------
// A: mapBlockTexts / collectBlockTexts
// ---------------------------------------------------------------------------

describe('A: mapBlockTexts / collectBlockTexts', () => {

    it('A01: paragraph -> .text wird abgebildet', () => {
        const out = Chips.mapBlockTexts({ text: 'abc' }, t => t.toUpperCase());
        expect(out.text).toBe('ABC');
    });

    it('A02: TABLE -> jede Zelle in .content wird abgebildet', () => {
        const out = Chips.mapBlockTexts(
            { withHeadings: false, content: [['a', 'b'], ['c', 'd']] },
            t => t.toUpperCase()
        );
        expect(out.content).toEqual([['A', 'B'], ['C', 'D']]);
        // Nicht-Text-Felder bleiben unangetastet
        expect(out.withHeadings).toBe(false);
    });

    it('A03: list -> Strings UND {content}-Objekte werden abgebildet', () => {
        const out = Chips.mapBlockTexts(
            { items: ['a', { content: 'b', items: [] }] },
            t => t.toUpperCase()
        );
        expect(out.items[0]).toBe('A');
        expect(out.items[1].content).toBe('B');
    });

    it('A04: das Original wird NICHT veraendert (kein Seiteneffekt)', () => {
        const orig = { content: [['a']] };
        Chips.mapBlockTexts(orig, () => 'X');
        expect(orig.content[0][0]).toBe('a');
    });

    it('A05: collectBlockTexts sammelt Text aus allen Zellen der Tabelle', () => {
        const texts = Chips.collectBlockTexts(TABLE_BLOCK);
        expect(texts).toHaveLength(6);
        expect(texts).toContain('{{a:user.posts_total|0}}');
    });
});

// ---------------------------------------------------------------------------
// B: hydrateBlockData / dehydrateBlockData
// ---------------------------------------------------------------------------

describe('B: Hydration/Dehydration von Tabellenbloecken', () => {

    it('B01: Tabellenzellen werden zu Chips hydriert', () => {
        const out = Chips.hydrateBlockData(
            TABLE_BLOCK,
            { passwort: 'hunter2' },
            { 'user.posts_total': '17' }
        );
        // Bezeichnerspalte bleibt reiner Text
        expect(out.content[0][0]).toBe('Registrierungsdatum');
        // Wertspalte enthaelt jetzt Chip-HTML
        expect(out.content[1][1]).toContain('ph-chip');
        expect(out.content[1][1]).toContain('hunter2');
        expect(out.content[2][1]).toContain('17');
    });

    it('B02: RUNDREISE — hydrieren, dann dehydrieren ergibt das Original', () => {
        const hyd = Chips.hydrateBlockData(TABLE_BLOCK, { passwort: 'x' }, {});
        const deh = Chips.dehydrateBlockData(hyd);
        expect(deh.content).toEqual(TABLE_BLOCK.content);
    });

    it('B03: KERNTEST — nach dem Dehydrieren steht KEIN Chip-HTML mehr drin', () => {
        // Genau das entscheidet, ob Darstellungs-HTML in report_blocks.block_data
        // und damit in den Siegel-Hash des Berichts gelangt.
        const hyd = Chips.hydrateBlockData(TABLE_BLOCK, {}, {});
        const deh = Chips.dehydrateBlockData(hyd);
        const alsText = JSON.stringify(deh);
        expect(alsText).not.toContain('ph-chip');
        expect(alsText).not.toContain('<span');
        expect(alsText).toContain('{{a:user.posts_total|0}}');
    });

    it('B04: dehydrateBlockData ist idempotent auf reiner Template-Syntax', () => {
        const einmal  = Chips.dehydrateBlockData(TABLE_BLOCK);
        const zweimal = Chips.dehydrateBlockData(einmal);
        expect(zweimal.content).toEqual(TABLE_BLOCK.content);
    });

    it('B05: Zellen ohne Platzhalter bleiben unveraendert', () => {
        const out = Chips.hydrateBlockData(
            { content: [['Nur Text', 'Auch nur Text']] }, {}, {}
        );
        expect(out.content[0][0]).toBe('Nur Text');
        expect(out.content[0][1]).toBe('Auch nur Text');
    });

    it('B06: paragraph-Bloecke funktionieren weiter wie bisher', () => {
        const hyd = Chips.hydrateBlockData({ text: 'Nutzer {{a:user.username}}' },
                                           {}, { 'user.username': 'rindexxx' });
        expect(hyd.text).toContain('rindexxx');
        expect(Chips.dehydrateBlockData(hyd).text).toBe('Nutzer {{a:user.username}}');
    });
});

// ---------------------------------------------------------------------------
// C: extractFieldsFromBlockData
// ---------------------------------------------------------------------------

describe('C: Feld-Extraktion aus Tabellenzellen', () => {

    it('C01: o:-Feld in einer Tabellenzelle wird gefunden', () => {
        const fields = Chips.extractFieldsFromBlockData(TABLE_BLOCK, 'o');
        expect(fields).toHaveLength(1);
        expect(fields[0].name).toBe('passwort');
        expect(fields[0].defaultVal).toBe('unbekannt');
    });

    it('C02: a:-Felder in Tabellenzellen werden gefunden', () => {
        const names = Chips.extractFieldsFromBlockData(TABLE_BLOCK, 'a')
            .map(f => f.name);
        expect(names).toEqual(['user.registered_datetime', 'user.posts_total']);
    });

    it('C03: Pflichtfeld in einer HEADER-Zeile wird gefunden', () => {
        // So sieht der erste Block des Spurenvermerks aus.
        const header = {
            text: 'Spurenvermerk zur Spurennummer ' +
                  '{{m:spurennummer||Spurennummer|rule:spurennummer}}',
            level: 2,
        };
        const fields = Chips.extractFieldsFromBlockData(header, 'm');
        expect(fields).toHaveLength(1);
        expect(fields[0].name).toBe('spurennummer');
        expect(fields[0].b64regex).toBe('rule:spurennummer');
    });

    it('C04: derselbe Feldname in mehreren Zellen wird EINMAL zurueckgegeben', () => {
        // Ein Feldname = ein Wert je Block (so ist placeholder_values_json gebaut).
        const block = { content: [['a', '{{o:x}}'], ['b', '{{o:x}}']] };
        expect(Chips.extractFieldsFromBlockData(block, 'o')).toHaveLength(1);
    });
});

// ---------------------------------------------------------------------------
// D: ValidationRules
// ---------------------------------------------------------------------------

describe('D: Zentraler Regel-Katalog', () => {

    it('D01: rule:-Verweis wird aufgeloest', () => {
        const spec = Rules.resolve('rule:spurennummer');
        expect(spec.ruleName).toBe('spurennummer');
        expect(spec.transform).toBe('upper');
        expect(spec.missing).toBe(false);
    });

    it('D02: Uppercase-Normalisierung VOR der Pruefung', () => {
        const res = Rules.check('rule:spurennummer', 'aiw12345');
        expect(res.ok).toBe(true);
        // Der zurueckgegebene Wert ist der GESPEICHERTE.
        expect(res.value).toBe('AIW12345');
    });

    it('D03: normalize() liefert den Wert, der gespeichert wird', () => {
        expect(Rules.normalize('rule:spurennummer', '  bru7 ')).toBe('BRU7');
    });

    it.each(['XYZ123', 'AIW', '12345', 'AIW 123', 'AIW123X'])(
        'D04: ungueltige Spurennummer wird abgelehnt: %s',
        (eingabe) => {
            const res = Rules.check('rule:spurennummer', eingabe);
            expect(res.ok).toBe(false);
            expect(res.message).toBeTruthy();  // Begruendung ist Pflicht
        }
    );

    it('D05: Der Hinweistext der Regel wird durchgereicht', () => {
        const res = Rules.check('rule:spurennummer', 'XYZ1');
        expect(res.message).toContain('AIW12345');
    });

    it('D06: FEHLENDE Regel wird NICHT still durchgewunken (Grundregel 1)', () => {
        const res = Rules.check('rule:gibt_es_nicht', 'irgendwas');
        expect(res.ok).toBe(false);
        expect(res.message).toContain('gibt_es_nicht');
    });

    it('D07: Alt-Form (Base64-Regex) funktioniert unveraendert weiter', () => {
        // btoa('^\\d+$')
        const b64 = btoa('^\\d+$');
        expect(Rules.check(b64, '12345').ok).toBe(true);
        expect(Rules.check(b64, 'abc').ok).toBe(false);
        // Alt-Form kennt keine Normalisierung
        expect(Rules.resolve(b64).transform).toBe('none');
    });

    it('D08: kein 5. Feld -> nichts zu pruefen, Wert gilt', () => {
        const res = Rules.check('', 'beliebig');
        expect(res.ok).toBe(true);
        expect(res.value).toBe('beliebig');
    });

    it('D09: applyTransform deckt sich mit der Serverseite', () => {
        expect(Rules.applyTransform(' ab ', 'upper')).toBe('AB');
        expect(Rules.applyTransform(' AB ', 'lower')).toBe('ab');
        expect(Rules.applyTransform(' ab ', 'strip')).toBe('ab');
        expect(Rules.applyTransform(' ab ', 'none')).toBe(' ab ');
    });
});

// ---------------------------------------------------------------------------
// E: Reiter 'Vorlagen'
// ---------------------------------------------------------------------------

describe('E: Vorlagen-Reiter im Bausteine-Panel', () => {

    const TEMPLATES = [{
        template_key: 'vermerk.nicht_identifiziert',
        title: 'Spurenvermerk \u2013 Nutzer nicht identifiziert',
        description: 'Kurzvermerk f\u00fcr nicht identifizierte Forennutzer.',
        report_type: 'final',
    }];

    beforeEach(() => {
        document.body.innerHTML = `
            <div id="mp-list"></div>
            <div id="mp-empty" style="display:none"></div>
            <div id="mp-loading"></div>`;
    });

    it('E01: Reiter "Vorlagen" ist im Skelett vorhanden', () => {
        Panel._setActiveCategoryForTest('templates');
        const html = Panel._renderSkeleton();
        expect(html).toContain('data-category="templates"');
        expect(html).toContain('>Vorlagen<');
    });

    it('E02: Vorlagen werden mit Einfuege-Knopf gerendert', () => {
        Panel._renderTemplateList(TEMPLATES);
        const list = document.getElementById('mp-list');
        expect(list.querySelectorAll('.mp-item--template')).toHaveLength(1);
        const btn = list.querySelector('.mp-insert-btn[data-template-key]');
        expect(btn).not.toBeNull();
        expect(btn.dataset.templateKey).toBe('vermerk.nicht_identifiziert');
    });

    it('E03: Der Einleitungstext erklaert die Wirkung VOR dem Klick', () => {
        Panel._renderTemplateList(TEMPLATES);
        const intro = document.querySelector('.mp-cat-intro');
        expect(intro).not.toBeNull();
        expect(intro.textContent).toContain('Ende des Berichts');
    });

    it('E04: KEIN Drag&Drop auf Vorlagen (sie gehen immer ans Ende)', () => {
        Panel._renderTemplateList(TEMPLATES);
        const item = document.querySelector('.mp-item--template');
        // Module sind draggable; eine Vorlage darf es nicht sein, sonst
        // suggeriert die Oberflaeche eine Einfuegeposition, die es nicht gibt.
        expect(item.getAttribute('draggable')).toBeNull();
    });

    it('E05: leere Liste -> klare Leermeldung, keine stille leere Liste', () => {
        Panel._renderTemplateList([]);
        const empty = document.getElementById('mp-empty');
        expect(empty.style.display).toBe('');
        expect(empty.textContent).toContain('Keine Vorlagen');
    });

    it('E06: Einfuegen sendet NUR den template_key (Server baut die Bloecke)', async () => {
        const sendSpy = vi.fn().mockResolvedValue({
            template_key: 'vermerk.nicht_identifiziert',
            block_ids: ['a', 'b', 'c'],
            block_count: 3,
        });
        window.lockLayer     = { lockId: 'lock-1' };
        window.documentLayer = { _sendRequest: sendSpy };
        window.confirm       = vi.fn().mockReturnValue(true);

        Panel._setTemplatesForTest(TEMPLATES);
        Panel._renderTemplateList(TEMPLATES);
        await Panel._insertTemplate('vermerk.nicht_identifiziert');

        expect(sendSpy).toHaveBeenCalledTimes(1);
        const payload = sendSpy.mock.calls[0][0];
        expect(payload.action).toBe('insert_template');
        expect(payload.template_key).toBe('vermerk.nicht_identifiziert');
        // Der Client darf KEINE Bloecke selbst schicken — sonst koennte bei
        // einem Abbruch ein halber Spurenvermerk entstehen.
        expect(payload.blocks).toBeUndefined();
    });

    it('E07: Abbruch im Bestaetigungsdialog fuegt nichts ein', async () => {
        const sendSpy = vi.fn();
        window.lockLayer     = { lockId: 'lock-1' };
        window.documentLayer = { _sendRequest: sendSpy };
        window.confirm       = vi.fn().mockReturnValue(false);

        Panel._setTemplatesForTest(TEMPLATES);
        await Panel._insertTemplate('vermerk.nicht_identifiziert');
        expect(sendSpy).not.toHaveBeenCalled();
    });

    it('E08: ohne Lock wird nicht eingefuegt', async () => {
        const sendSpy = vi.fn();
        window.lockLayer     = { lockId: null };
        window.documentLayer = { _sendRequest: sendSpy };
        window.confirm       = vi.fn().mockReturnValue(true);

        await Panel._insertTemplate('vermerk.nicht_identifiziert');
        expect(sendSpy).not.toHaveBeenCalled();
    });
});
