/**
 * tests/unit/test_build431_tag_network.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
 *
 * Testsuite fuer den REINEN Tag-Netz-Aggregator
 * (userinfo/annotation_tag_network.js -> window.AIWAnnotationTagNetwork.build...)
 * sowie die Cross-Annotation-Erweiterung des Filter-Kerns (Build 431).
 *
 * N01 -- Modul verfuegbar
 * N02 -- leere Eingabe: nur Zentrums-Knoten, keine Kanten
 * N03 -- Knotenarten: Zentrum + Kategorie + Tag
 * N04 -- Ko-Okkurrenz-Kante zwischen gemeinsam getaggten Tags (Gewicht 1)
 * N05 -- Ko-Okkurrenz-Gewicht akkumuliert ueber mehrere Annotationen
 * N06 -- isolierter Tag (keine Tag-Tag-Kante) wird erkannt
 * N07 -- Kategorie-Knoten nur fuer vorkommende Kategorien
 * N08 -- tagCount/cooccurrenceEdges korrekt
 * N09 -- deriveCross: eigene vs. Fremd-UID
 * N10 -- computeFacets.cross zaehlt eigene/Fremd
 * N11 -- matchesPredicate.cross filtert
 * N12 -- emptyPredicate enthaelt cross:[]
 *
 * Version: v0.7.431 · Build: 431 · 2026-07-15
 * Beleg: Bauplan_Baustelle4_Annotationsrecherche_v0_1.md §6/§8
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';
import '../../userinfo/annotation_filter.js';
import '../../userinfo/annotation_tag_network.js';

const F = window.AIWAnnotationFilter;
const N = window.AIWAnnotationTagNetwork;

function ann(over) {
  return Object.assign({
    id: 1, pageUrl: '/forum/viewtopic.php?id=5', category: 'CAT_PERSON',
    text: '', tags: [], elementId: 'p1', selection: null, postId: 1,
    localId: 'u1', createdAt: 1700000000000, createdBy: 'm',
    versionNr: 1, prevId: null, actualUid: null
  }, over || {});
}

function tagTagLinks(built) {
  return built.links.filter(function (l) { return l._kind === 'tag-tag'; });
}

describe('Build 431 — Tag-Netz + Cross-Filter', () => {
  it('N01 Modul verfuegbar', () => {
    expect(typeof N.buildTagNetwork).toBe('function');
    expect(typeof N.TagNetworkView).toBe('function');
  });

  it('N02 leere Eingabe', () => {
    const b = N.buildTagNetwork([], { userLabel: 'X' });
    const users = b.nodes.filter(n => n._kind === 'user');
    expect(users.length).toBe(1);
    expect(b.nodes.filter(n => n._kind === 'tag').length).toBe(0);
    expect(b.cooccurrenceEdges).toBe(0);
  });

  it('N03 Knotenarten', () => {
    const b = N.buildTagNetwork([ann({ tags: ['email'] })]);
    const kinds = {};
    b.nodes.forEach(n => { kinds[n._kind] = (kinds[n._kind] || 0) + 1; });
    expect(kinds.user).toBe(1);
    expect(kinds.cat).toBe(1);      // CAT_PERSON vorhanden
    expect(kinds.tag).toBe(1);      // email
  });

  it('N04 Ko-Okkurrenz-Kante Gewicht 1', () => {
    const b = N.buildTagNetwork([ann({ tags: ['email', 'realname'] })]);
    const tt = tagTagLinks(b);
    expect(tt.length).toBe(1);
    expect(tt[0].value).toBe(1);
    expect(tt[0]._pairTags.slice().sort()).toEqual(['email', 'realname']);
    expect(b.isolatedTags).toEqual([]);
  });

  it('N05 Gewicht akkumuliert', () => {
    const b = N.buildTagNetwork([
      ann({ id: 1, tags: ['email', 'ip'] }),
      ann({ id: 2, tags: ['ip', 'email'] })   // gleiche Paarung
    ]);
    const tt = tagTagLinks(b);
    expect(tt.length).toBe(1);
    expect(tt[0].value).toBe(2);
  });

  it('N06 isolierter Tag', () => {
    const b = N.buildTagNetwork([
      ann({ id: 1, tags: ['email', 'realname'] }),
      ann({ id: 2, tags: ['ip'] })   // ip kommt nie zusammen mit anderen vor
    ]);
    expect(b.isolatedTags).toEqual(['ip']);
  });

  it('N07 Kategorie-Knoten nur fuer vorkommende', () => {
    const b = N.buildTagNetwork([ann({ category: 'CAT_184', tags: ['foto'] })]);
    const cats = b.nodes.filter(n => n._kind === 'cat');
    expect(cats.length).toBe(1);
    expect(cats[0]._catId).toBe('CAT_184');
  });

  it('N08 tagCount/edges', () => {
    const b = N.buildTagNetwork([ann({ tags: ['a', 'b', 'c'] })]);
    expect(b.tagCount).toBe(3);
    expect(b.cooccurrenceEdges).toBe(3); // a-b, a-c, b-c
  });

  it('N09 deriveCross', () => {
    expect(F.deriveCross(ann({ actualUid: null }))).toBe('eigene');
    expect(F.deriveCross(ann({ actualUid: 42 }))).toBe('42');
  });

  it('N10 computeFacets.cross', () => {
    const f = F.computeFacets([
      ann({ actualUid: null }), ann({ actualUid: null }), ann({ actualUid: 42 })
    ]);
    expect(f.cross.eigene).toBe(2);
    expect(f.cross['42']).toBe(1);
  });

  it('N11 matchesPredicate.cross', () => {
    const p = Object.assign(F.emptyPredicate(), { cross: ['42'] });
    expect(F.matchesPredicate(ann({ actualUid: 42 }), p)).toBe(true);
    expect(F.matchesPredicate(ann({ actualUid: null }), p)).toBe(false);
  });

  it('N12 emptyPredicate.cross', () => {
    expect(F.emptyPredicate().cross).toEqual([]);
  });
});
