/**
 * tests/unit/test_build428_annotation_recherche.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
 *
 * Testsuite fuer den reinen Filter-Kern (userinfo/annotation_filter.js) und die
 * reinen Store-Helfer (userinfo/annotation_store.js) sowie die Tag-Parselogik
 * der Bearbeiten-Maske (userinfo/annotation_edit_dialog.js). Getestet wird gegen
 * echten Code (kein Stub), nur bei addTags wird saveEdit gekapselt, um den
 * Netzzugriff aus dem reinen Merge-Test herauszuhalten.
 *
 * T01 -- Module verfuegbar nach Laden
 * T02 -- categoryMeta liefert bekannte und Fallback-Kategorie
 * T03 -- deriveSource: post/pm/profile/file/other
 * T04 -- annotationTimeMs bevorzugt contentTs (Sekunden->ms), sonst createdAt
 * T05 -- annotationTimeMs: ohne Zeitfelder -> null
 * T06 -- matchesSearch: leer -> true
 * T07 -- matchesSearch: Treffer in text/tag/selection
 * T08 -- matchesSearch: case-insensitiv, kein Treffer -> false
 * T09 -- emptyPredicate ist neutral (alles passt)
 * T10 -- matchesTags ODER
 * T11 -- matchesTags UND
 * T12 -- matchesPredicate: Kategorie schraenkt ein
 * T13 -- matchesPredicate: Autor schraenkt ein
 * T14 -- matchesPredicate: Quelle schraenkt ein
 * T15 -- matchesPredicate: Zeitraum (from/to), ohne Zeit -> raus
 * T16 -- matchesPredicate: hypothesisOnly
 * T17 -- applyFilter: kombiniertes Praedikat zaehlt korrekt
 * T18 -- sortAnnotations: Zeit absteigend/aufsteigend
 * T19 -- sortAnnotations: ohne Zeit immer hinten
 * T20 -- sortAnnotations: identity nach Zahl der Identitaets-Tags
 * T21 -- computeFacets: Zaehlwerte je Facette
 * T22 -- isHypothesis erkennt Vermutungs-Tags
 * T23 -- identityScore zaehlt Identitaets-Tags
 * T24 -- Store.canEdit: nur mit localId
 * T25 -- Store._toApiBody: camelCase->snake_case, Felder erhalten
 * T26 -- Store._toApiBody: overrides ueberschreiben gezielt
 * T27 -- Store.addTags: Union, Duplikate (case-insensitiv) unterdrueckt
 * T28 -- Store.saveEdit: ohne localId -> Reject (Duplikatschutz)
 * T29 -- EditDialog._parseTags: trennt, trimmt, verwirft Leeres
 *
 * Version: v0.7.428 · Build: 428 · 2026-07-14
 * Beleg: Bauplan_Baustelle4_Annotationsrecherche_v0_1.md §4/§6/§7/§11/§12
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';
import '../../userinfo/annotation_filter.js';
import '../../userinfo/annotation_store.js';
import '../../userinfo/annotation_edit_dialog.js';

const F = window.AIWAnnotationFilter;

// Testdaten-Fabrik (minimale, realistische Annotationen gemaess Datenvertrag)
function ann(over) {
  return Object.assign({
    id: 1, pageUrl: '/forum/viewtopic.php?id=5', category: 'CAT_PERSON',
    text: '', tags: [], elementId: 'p10', selection: null, postId: 10,
    localId: 'uuid-1', createdAt: 1700000000000, createdBy: 'muster.mann',
    syncState: 'synced', versionNr: 1, prevId: null, actualUid: null
  }, over || {});
}

describe('Build 428 — Annotationsrecherche', () => {
  it('T01 Module verfuegbar', () => {
    expect(window.AIWAnnotationFilter).toBeTruthy();
    expect(typeof window.AIWAnnotationStore).toBe('function');
    expect(typeof window.AIWAnnotationEditDialog).toBe('function');
  });

  it('T02 categoryMeta', () => {
    expect(F.categoryMeta('CAT_176').label).toBe('176');
    expect(F.categoryMeta('CAT_176').color).toBe('#e84040');
    expect(F.categoryMeta('UNBEKANNT').label).toBe('UNBEKANNT');
  });

  it('T03 deriveSource', () => {
    expect(F.deriveSource(ann({ pageUrl: '/forum/viewtopic.php?id=1', postId: 3 }))).toBe('post');
    expect(F.deriveSource(ann({ pageUrl: '/forum/misc.php?email=pms', postId: null }))).toBe('pm');
    expect(F.deriveSource(ann({ pageUrl: '/forum/profile.php?id=7', postId: null }))).toBe('profile');
    expect(F.deriveSource(ann({ pageUrl: '/forum/gallery.php?id=9', postId: null }))).toBe('file');
    expect(F.deriveSource(ann({ pageUrl: '/forum/index.php', postId: null }))).toBe('other');
  });

  it('T04 annotationTimeMs bevorzugt contentTs', () => {
    // contentTs in Sekunden -> *1000
    expect(F.annotationTimeMs(ann({ contentTs: 1600000000, createdAt: 1700000000000 }))).toBe(1600000000000);
    expect(F.annotationTimeMs(ann({ createdAt: 1700000000000 }))).toBe(1700000000000);
  });

  it('T05 annotationTimeMs ohne Zeit -> null', () => {
    expect(F.annotationTimeMs(ann({ contentTs: null, createdAt: null }))).toBeNull();
  });

  it('T06 matchesSearch leer', () => {
    expect(F.matchesSearch(ann(), '')).toBe(true);
  });

  it('T07 matchesSearch Treffer', () => {
    expect(F.matchesSearch(ann({ text: 'Klarname Meier' }), 'meier')).toBe(true);
    expect(F.matchesSearch(ann({ tags: ['email'] }), 'mail')).toBe(true);
    expect(F.matchesSearch(ann({ selection: { text: 'Wohnort Köln' } }), 'köln')).toBe(true);
  });

  it('T08 matchesSearch kein Treffer', () => {
    expect(F.matchesSearch(ann({ text: 'abc' }), 'xyz')).toBe(false);
  });

  it('T09 emptyPredicate neutral', () => {
    const p = F.emptyPredicate();
    expect(F.matchesPredicate(ann(), p)).toBe(true);
    expect(p.tagMode).toBe('or');
  });

  it('T10 matchesTags ODER', () => {
    expect(F.matchesTags(ann({ tags: ['email', 'ip'] }), ['email', 'foto'], 'or')).toBe(true);
    expect(F.matchesTags(ann({ tags: ['ip'] }), ['email', 'foto'], 'or')).toBe(false);
  });

  it('T11 matchesTags UND', () => {
    expect(F.matchesTags(ann({ tags: ['email', 'ip'] }), ['email', 'ip'], 'and')).toBe(true);
    expect(F.matchesTags(ann({ tags: ['email'] }), ['email', 'ip'], 'and')).toBe(false);
  });

  it('T12 matchesPredicate Kategorie', () => {
    const p = Object.assign(F.emptyPredicate(), { categories: ['CAT_184'] });
    expect(F.matchesPredicate(ann({ category: 'CAT_184' }), p)).toBe(true);
    expect(F.matchesPredicate(ann({ category: 'CAT_PERSON' }), p)).toBe(false);
  });

  it('T13 matchesPredicate Autor', () => {
    const p = Object.assign(F.emptyPredicate(), { authors: ['a.b'] });
    expect(F.matchesPredicate(ann({ createdBy: 'a.b' }), p)).toBe(true);
    expect(F.matchesPredicate(ann({ createdBy: 'c.d' }), p)).toBe(false);
  });

  it('T14 matchesPredicate Quelle', () => {
    const p = Object.assign(F.emptyPredicate(), { sources: ['pm'] });
    expect(F.matchesPredicate(ann({ pageUrl: '/forum/pms.php', postId: null }), p)).toBe(true);
    expect(F.matchesPredicate(ann({ pageUrl: '/forum/viewtopic.php', postId: 1 }), p)).toBe(false);
  });

  it('T15 matchesPredicate Zeitraum', () => {
    const p = Object.assign(F.emptyPredicate(), { from: 1000, to: 2000 });
    expect(F.matchesPredicate(ann({ contentTs: 1, createdAt: 1500 }), p)).toBe(true); // contentTs 1s=1000ms
    expect(F.matchesPredicate(ann({ contentTs: null, createdAt: 3000 }), p)).toBe(false);
    expect(F.matchesPredicate(ann({ contentTs: null, createdAt: null }), p)).toBe(false); // ohne Zeit raus
  });

  it('T16 matchesPredicate hypothesisOnly', () => {
    const p = Object.assign(F.emptyPredicate(), { hypothesisOnly: true });
    expect(F.matchesPredicate(ann({ tags: ['vermutung'] }), p)).toBe(true);
    expect(F.matchesPredicate(ann({ tags: ['email'] }), p)).toBe(false);
  });

  it('T17 applyFilter kombiniert', () => {
    const data = [
      ann({ id: 1, category: 'CAT_PERSON', tags: ['email'] }),
      ann({ id: 2, category: 'CAT_PERSON', tags: ['ip'] }),
      ann({ id: 3, category: 'CAT_184', tags: ['email'] })
    ];
    const p = Object.assign(F.emptyPredicate(), { categories: ['CAT_PERSON'], tags: ['email'] });
    const out = F.applyFilter(data, p);
    expect(out.map(a => a.id)).toEqual([1]);
  });

  it('T18 sortAnnotations Zeit', () => {
    const data = [ann({ id: 1, createdAt: 100 }), ann({ id: 2, createdAt: 300 }), ann({ id: 3, createdAt: 200 })];
    expect(F.sortAnnotations(data, 'time', 'desc').map(a => a.id)).toEqual([2, 3, 1]);
    expect(F.sortAnnotations(data, 'time', 'asc').map(a => a.id)).toEqual([1, 3, 2]);
  });

  it('T19 sortAnnotations ohne Zeit hinten', () => {
    const data = [ann({ id: 1, contentTs: null, createdAt: null }), ann({ id: 2, createdAt: 200 })];
    expect(F.sortAnnotations(data, 'time', 'desc').map(a => a.id)).toEqual([2, 1]);
    expect(F.sortAnnotations(data, 'time', 'asc').map(a => a.id)).toEqual([2, 1]);
  });

  it('T20 sortAnnotations identity', () => {
    const data = [
      ann({ id: 1, tags: ['email'] }),
      ann({ id: 2, tags: ['email', 'realname', 'ip'] }),
      ann({ id: 3, tags: [] })
    ];
    expect(F.sortAnnotations(data, 'identity', 'desc').map(a => a.id)).toEqual([2, 1, 3]);
  });

  it('T21 computeFacets', () => {
    const data = [
      ann({ category: 'CAT_PERSON', tags: ['email'], createdBy: 'a', pageUrl: '/forum/viewtopic.php', postId: 1 }),
      ann({ category: 'CAT_PERSON', tags: ['email', 'ip'], createdBy: 'b', pageUrl: '/forum/pms.php', postId: null }),
      ann({ category: 'CAT_184', tags: ['vermutung'], createdBy: 'a', pageUrl: '/forum/viewtopic.php', postId: 2 })
    ];
    const f = F.computeFacets(data);
    expect(f.total).toBe(3);
    expect(f.categories.CAT_PERSON).toBe(2);
    expect(f.tags.email).toBe(2);
    expect(f.authors.a).toBe(2);
    expect(f.sources.pm).toBe(1);
    expect(f.hypotheses).toBe(1);
  });

  it('T22 isHypothesis', () => {
    expect(F.isHypothesis(ann({ tags: ['Vermutung'] }))).toBe(true);
    expect(F.isHypothesis(ann({ tags: ['hypothese'] }))).toBe(true);
    expect(F.isHypothesis(ann({ tags: ['email'] }))).toBe(false);
  });

  it('T23 identityScore', () => {
    expect(F.identityScore(ann({ tags: ['email', 'realname', 'sprache'] }))).toBe(2);
  });

  it('T24 Store.canEdit', () => {
    const s = new window.AIWAnnotationStore();
    expect(s.canEdit(ann({ localId: 'x' }))).toBe(true);
    expect(s.canEdit(ann({ localId: null }))).toBe(false);
  });

  it('T25 Store._toApiBody Mapping', () => {
    const s = new window.AIWAnnotationStore();
    const body = s._toApiBody(ann({ pageUrl: '/u', category: 'CAT_LOCATION', text: 'hi', elementId: 'p9', localId: 'L1', postId: 9, tags: ['ort'], actualUid: 42 }), {});
    expect(body.page_url).toBe('/u');
    expect(body.category).toBe('CAT_LOCATION');
    expect(body.text).toBe('hi');
    expect(body.element_id).toBe('p9');
    expect(body.local_id).toBe('L1');
    expect(body.post_id).toBe(9);
    expect(body.tags).toEqual(['ort']);
    expect(body.target_user_id).toBe(42);
  });

  it('T26 Store._toApiBody overrides', () => {
    const s = new window.AIWAnnotationStore();
    const body = s._toApiBody(ann({ tags: ['a'] }), { tags: ['a', 'b'], category: 'CAT_OTHER' });
    expect(body.tags).toEqual(['a', 'b']);
    expect(body.category).toBe('CAT_OTHER');
  });

  it('T27 Store.addTags Union ohne Duplikate', () => {
    const s = new window.AIWAnnotationStore();
    let captured = null;
    s.saveEdit = (a, ov) => { captured = ov; return Promise.resolve(); };
    return s.addTags(ann({ tags: ['email'] }), ['IP', 'email', 'ip', 'foto']).then(() => {
      // 'email' bereits vorhanden; 'IP' neu; 'ip' Duplikat zu 'IP' (case-insensitiv); 'foto' neu
      expect(captured.tags).toEqual(['email', 'IP', 'foto']);
    });
  });

  it('T28 Store.saveEdit ohne localId rejected', () => {
    const s = new window.AIWAnnotationStore();
    return s.saveEdit(ann({ localId: null }), { text: 'x' }).then(
      () => { throw new Error('sollte rejecten'); },
      (err) => { expect(String(err.message)).toMatch(/local_id/); }
    );
  });

  it('T29 EditDialog._parseTags', () => {
    const d = new window.AIWAnnotationEditDialog(null);
    expect(d._parseTags('a, b ,, c ')).toEqual(['a', 'b', 'c']);
    expect(d._parseTags('')).toEqual([]);
  });
});
