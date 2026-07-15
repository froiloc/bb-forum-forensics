/**
 * tests/unit/test_build430_timeline.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
 *
 * Testsuite fuer den REINEN Zeitstrahl-Option-Builder
 * (userinfo/annotation_timeline.js -> window.AIWAnnotationTimeline).
 * Kein ECharts noetig (buildTimelineOption ist reine Datenlogik).
 *
 * Z01 -- Modul verfuegbar
 * Z02 -- timeForBasis content: contentTs (s) -> ms
 * Z03 -- timeForBasis content: ohne contentTs -> null
 * Z04 -- timeForBasis annotation: createdAt (ms)
 * Z05 -- buildTimelineOption: Punkte + withoutTime (content-Basis)
 * Z06 -- buildTimelineOption: y-Kategorien = 6 kanonische Labels
 * Z07 -- buildTimelineOption: Punktfarbe = Kategoriefarbe, annId gesetzt
 * Z08 -- buildTimelineOption: annotation-Basis nutzt createdAt (nichts "ohne Zeit")
 * Z09 -- buildTimelineOption: leere Eingabe -> 0 Punkte
 * Z10 -- Option enthaelt Zeit-x-Achse, Kategorie-y-Achse und Brush
 *
 * Version: v0.7.430 · Build: 430 · 2026-07-15
 * Beleg: Bauplan_Baustelle4_Annotationsrecherche_v0_1.md §9/§13
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';
import '../../userinfo/annotation_filter.js';
import '../../userinfo/annotation_timeline.js';

const T = window.AIWAnnotationTimeline;

function ann(over) {
  return Object.assign({
    id: 1, pageUrl: '/forum/viewtopic.php?id=5', category: 'CAT_PERSON',
    text: 'Notiz', tags: [], elementId: 'p10', selection: null, postId: 10,
    localId: 'u1', createdAt: 1700000000000, createdBy: 'muster.mann',
    versionNr: 1, prevId: null, actualUid: null, contentTs: null
  }, over || {});
}

describe('Build 430 — Zeitstrahl', () => {
  it('Z01 Modul verfuegbar', () => {
    expect(T).toBeTruthy();
    expect(typeof T.buildTimelineOption).toBe('function');
    expect(typeof T.timeForBasis).toBe('function');
  });

  it('Z02 timeForBasis content s->ms', () => {
    expect(T.timeForBasis(ann({ contentTs: 1600000000 }), 'content')).toBe(1600000000000);
  });

  it('Z03 timeForBasis content ohne contentTs -> null', () => {
    expect(T.timeForBasis(ann({ contentTs: null }), 'content')).toBeNull();
  });

  it('Z04 timeForBasis annotation', () => {
    expect(T.timeForBasis(ann({ createdAt: 123 }), 'annotation')).toBe(123);
    expect(T.timeForBasis(ann({ createdAt: null }), 'annotation')).toBeNull();
  });

  it('Z05 Punkte + withoutTime (content)', () => {
    const data = [
      ann({ id: 1, contentTs: 1600000000 }),
      ann({ id: 2, contentTs: null }),          // ohne Inhaltszeit
      ann({ id: 3, contentTs: 1600000500 })
    ];
    const built = T.buildTimelineOption(data, { basis: 'content' });
    expect(built.plotted).toBe(2);
    expect(built.withoutTime).toBe(1);
    expect(built.option.series[0].data.length).toBe(2);
  });

  it('Z06 y-Kategorien', () => {
    const built = T.buildTimelineOption([], { basis: 'content' });
    expect(built.categories.length).toBe(6);
    expect(built.option.yAxis.data.length).toBe(6);
    // Labels enthalten die Kurzcodes
    expect(built.categories.join(' ')).toMatch(/PER/);
    expect(built.categories.join(' ')).toMatch(/184/);
  });

  it('Z07 Punktfarbe + annId', () => {
    const built = T.buildTimelineOption([ann({ id: 7, category: 'CAT_176', contentTs: 1600000000 })], { basis: 'content' });
    const p = built.option.series[0].data[0];
    expect(p.annId).toBe(7);
    expect(p.itemStyle.color).toBe('#e84040'); // CAT_176
    expect(Array.isArray(p.value)).toBe(true);
    expect(p.value[0]).toBe(1600000000000);
  });

  it('Z08 annotation-Basis', () => {
    const data = [ann({ id: 1, contentTs: null, createdAt: 1000 }), ann({ id: 2, contentTs: null, createdAt: 2000 })];
    const built = T.buildTimelineOption(data, { basis: 'annotation' });
    expect(built.plotted).toBe(2);
    expect(built.withoutTime).toBe(0);
  });

  it('Z09 leer', () => {
    const built = T.buildTimelineOption([], { basis: 'content' });
    expect(built.plotted).toBe(0);
    expect(built.option.series[0].data.length).toBe(0);
  });

  it('Z10 Achsen + Brush', () => {
    const built = T.buildTimelineOption([], {});
    expect(built.option.xAxis.type).toBe('time');
    expect(built.option.yAxis.type).toBe('category');
    expect(built.option.brush).toBeTruthy();
    expect(built.option.brush.brushType).toBe('lineX');
  });
});
