/**
 * tests/unit/test_build429_identity_profile.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
 *
 * Testsuite fuer den REINEN Identitaets-Steckbrief-Aggregator
 * (userinfo/annotation_identity_profile.js -> window.AIWIdentityProfile.build).
 * Getestet gegen echten Code; benoetigt den Filter-Kern (isHypothesis,
 * annotationTimeMs, categoryMeta).
 *
 * P01 -- Modul verfuegbar; leere Eingabe -> leeres Profil
 * P02 -- Ein Identitaetswert (selection.text) wird gesichert erfasst
 * P03 -- valueOf-Fallback: ohne selection wird die Notiz zum Wert
 * P04 -- valueOf-Fallback: ohne selection und Notiz -> Platzhalter
 * P05 -- Gleicher Wert aus zwei Annotationen -> ein Wert, zwei Belege
 * P06 -- Reine Vermutung landet in hypotheses, nicht in confirmed
 * P07 -- Gemischt (Beleg + Vermutung, gleicher Wert) -> gesichert (anyConfirmed)
 * P08 -- coveredTypes/totalValues/hypothesisValues korrekt
 * P09 -- Sektions-Reihenfolge entspricht IDENTITY_META (realname vor email)
 * P10 -- Nicht-Identitaets-Tags werden ignoriert
 * P11 -- Belege je Wert sind zeitlich aufsteigend sortiert
 *
 * Version: v0.7.429 · Build: 429 · 2026-07-15
 * Beleg: Bauplan_Baustelle4_Annotationsrecherche_v0_1.md §10/§11
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest';
import '../../userinfo/annotation_filter.js';
import '../../userinfo/annotation_identity_profile.js';

const P = window.AIWIdentityProfile;

function ann(over) {
  return Object.assign({
    id: 1, pageUrl: '/forum/viewtopic.php?id=5', category: 'CAT_PERSON',
    text: '', tags: [], elementId: 'p1', selection: null, postId: 1,
    localId: 'u1', createdAt: 1700000000000, createdBy: 'muster.mann',
    versionNr: 1, prevId: null, actualUid: null
  }, over || {});
}

describe('Build 429 — Identitäts-Steckbrief', () => {
  it('P01 leeres Profil', () => {
    expect(typeof P.build).toBe('function');
    const p = P.build([]);
    expect(p.sections).toEqual([]);
    expect(p.coveredTypes).toBe(0);
    expect(p.totalValues).toBe(0);
  });

  it('P02 gesicherter Identitaetswert', () => {
    const p = P.build([ann({ tags: ['email'], selection: { text: 'a@b.de' } })]);
    expect(p.sections.length).toBe(1);
    expect(p.sections[0].tag).toBe('email');
    expect(p.sections[0].confirmed.length).toBe(1);
    expect(p.sections[0].confirmed[0].value).toBe('a@b.de');
    expect(p.coveredTypes).toBe(1);
    expect(p.totalValues).toBe(1);
  });

  it('P03 Fallback auf Notiz', () => {
    const p = P.build([ann({ tags: ['realname'], selection: null, text: 'Max Meier' })]);
    expect(p.sections[0].confirmed[0].value).toBe('Max Meier');
  });

  it('P04 Fallback Platzhalter', () => {
    const p = P.build([ann({ tags: ['ip'], selection: null, text: '' })]);
    expect(p.sections[0].confirmed[0].value).toMatch(/kein Textwert/);
  });

  it('P05 gleicher Wert -> ein Wert, zwei Belege', () => {
    const p = P.build([
      ann({ id: 1, tags: ['email'], selection: { text: 'a@b.de' } }),
      ann({ id: 2, tags: ['email'], selection: { text: 'A@B.DE' } }) // Normalisierung
    ]);
    expect(p.sections[0].confirmed.length).toBe(1);
    expect(p.sections[0].confirmed[0].beleg.map(b => b.annId).sort()).toEqual([1, 2]);
  });

  it('P06 reine Vermutung -> hypotheses', () => {
    const p = P.build([ann({ tags: ['telefon', 'vermutung'], selection: { text: '0170-123' } })]);
    expect(p.sections[0].confirmed.length).toBe(0);
    expect(p.sections[0].hypotheses.length).toBe(1);
    expect(p.coveredTypes).toBe(0);
    expect(p.hypothesisValues).toBe(1);
  });

  it('P07 gemischt -> gesichert', () => {
    const p = P.build([
      ann({ id: 1, tags: ['email'], selection: { text: 'a@b.de' } }),
      ann({ id: 2, tags: ['email', 'vermutung'], selection: { text: 'a@b.de' } })
    ]);
    expect(p.sections[0].confirmed.length).toBe(1);
    expect(p.sections[0].hypotheses.length).toBe(0);
  });

  it('P08 Kennzahlen', () => {
    const p = P.build([
      ann({ id: 1, tags: ['email'], selection: { text: 'a@b.de' } }),
      ann({ id: 2, tags: ['realname'], selection: { text: 'Max' } }),
      ann({ id: 3, tags: ['ip', 'vermutung'], selection: { text: '1.2.3.4' } })
    ]);
    expect(p.coveredTypes).toBe(2);       // email + realname
    expect(p.totalValues).toBe(2);
    expect(p.hypothesisValues).toBe(1);
    expect(p.identityAnnotations).toBe(3);
  });

  it('P09 Sektionsreihenfolge', () => {
    const p = P.build([
      ann({ id: 1, tags: ['email'], selection: { text: 'a@b.de' } }),
      ann({ id: 2, tags: ['realname'], selection: { text: 'Max' } })
    ]);
    // IDENTITY_META: realname vor email
    expect(p.sections.map(s => s.tag)).toEqual(['realname', 'email']);
  });

  it('P10 Nicht-Identitaets-Tags ignoriert', () => {
    const p = P.build([ann({ tags: ['sprache', 'datum'], selection: { text: 'x' } })]);
    expect(p.sections.length).toBe(0);
  });

  it('P11 Belege zeitlich aufsteigend', () => {
    const p = P.build([
      ann({ id: 1, tags: ['email'], selection: { text: 'a@b.de' }, createdAt: 2000 }),
      ann({ id: 2, tags: ['email'], selection: { text: 'a@b.de' }, createdAt: 1000 })
    ]);
    expect(p.sections[0].confirmed[0].beleg.map(b => b.annId)).toEqual([2, 1]);
  });
});
