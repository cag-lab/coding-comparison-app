// SPDX-License-Identifier: GPL-3.0-or-later
// Unit tests for the statistics core, run against the built single-file app.
// Usage: node --test tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const html = readFileSync(join(root, 'coder-agreement-viewer.html'), 'utf8');
const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
// The UI only initialises when `document` exists, so this loads just the pure core.
const Core = new Function(js + '; return Core;')();

const load = f => JSON.parse(readFileSync(join(root, 'examples', f), 'utf8'));
const A = load('synthetic-icu-progress-note__cag__coding.json');
const B = load('synthetic-icu-progress-note__cag2__coding.json');
const close = (got, want, msg) => assert.ok(Math.abs(got - want) < 1e-6, `${msg}: got ${got}, want ${want}`);

test('example files validate cleanly', () => {
  for (const [d, n] of [[A, 'A'], [B, 'B']]) {
    const checks = Core.validateFile(d, n);
    assert.ok(checks.every(c => c.level === 'ok'), JSON.stringify(checks));
  }
  const cross = Core.crossValidate(A, B);
  assert.ok(!cross.some(c => c.level === 'error'));
  assert.ok(cross.some(c => c.level === 'info' && /copy/.test(c.msg)), 'flags copied ids');
});

test('note hash verifies', async () => {
  assert.equal(await Core.sha256Hex(A.note.text), A.note.sha256);
});

test('different note text is a blocking error', () => {
  const B2 = structuredClone(B);
  B2.note.text = B2.note.text.replace('Day 5', 'Day 6');
  assert.ok(Core.crossValidate(A, B2).some(c => c.level === 'error'));
});

test('bad offsets are reported and ignored', () => {
  const A2 = structuredClone(A);
  A2.annotations.push({ id: 'X', code: 'c', start: 10, end: 99999 });
  A2.annotations[0].text = 'wrong';
  const checks = Core.validateFile(A2, 'A');
  assert.ok(checks.some(c => /invalid offsets/.test(c.msg)));
  assert.ok(checks.some(c => /does not match/.test(c.msg)));
  assert.equal(Core.normalize(A2, 'A').anns.length, 5);
});

test('character IoU and span matching (hand-calculated)', () => {
  const r = Core.compute(Core.normalize(A, 'A'), Core.normalize(B, 'B'), { unit: 'token', thr: 0.5 });
  const by = Object.fromEntries(r.perCode.map(p => [p.code, p]));
  close(by.physiological_success.iou, 48 / 48, 'success IoU');
  close(by.physiological_failure.iou, 96 / 343, 'failure IoU');
  close(by.patient_family_engagement.iou, 0, 'engagement IoU');
  close(r.overall.microIoU, 144 / 441, 'micro IoU');
  assert.equal(r.overall.matched, 2);
  close(r.overall.spanF1, 4 / 9, 'span F1');
});

test('kappa, alpha and ICC match reference implementation (tests/reference_check.py)', () => {
  const r = Core.compute(Core.normalize(A, 'A'), Core.normalize(B, 'B'), { unit: 'token', thr: 0.5 });
  const f = r.perCode.find(p => p.code === 'physiological_failure');
  close(f.kappa, 0.381337, 'kappa');
  close(f.alpha, 0.380018, 'alpha');
  close(f.icc2, 0.381654, 'ICC(2,1)');
  close(f.icc3, 0.383483, 'ICC(3,1)');
  const e = r.perCode.find(p => p.code === 'patient_family_engagement');
  close(e.alpha, -0.004046, 'engagement alpha');
  assert.equal(e.icc2, 0);
  close(r.note.countAlpha, 0.561404, 'count alpha (interval)');
  close(r.note.countIcc2, 0.583333, 'count ICC(2,1)');
  close(r.note.countIcc3, 0.5, 'count ICC(3,1)');
});

test('textbook statistics', () => {
  const { cohenKappa, alphaNominal, icc } = Core.stats;
  // perfect agreement
  assert.equal(cohenKappa([1, 0, 1, 0], [1, 0, 1, 0]), 1);
  assert.equal(alphaNominal([1, 0, 1, 0], [1, 0, 1, 0]), 1);
  // no variation -> undefined
  assert.equal(alphaNominal([0, 0, 0], [0, 0, 0]), null);
  assert.equal(icc([1, 1, 1], [1, 1, 1]).icc2, null);
  // kappa: 2x2 table [[20,5],[10,15]] -> po=.70, pe=.50, kappa=.40
  const x = [], y = [];
  const add = (a, b, n) => { for (let i = 0; i < n; i++) { x.push(a); y.push(b); } };
  add(1, 1, 20); add(1, 0, 5); add(0, 1, 10); add(0, 0, 15);
  close(cohenKappa(x, y), 0.4, 'kappa 2x2');
});

test('UTF-16 offsets: non-BMP characters do not shift spans', () => {
  const text = 'pain 😖 severe. calm.';
  const start = text.indexOf('severe');
  const mk = (code) => ({
    schema: 'note-coder/v1', coder_id: code, note: { text, char_count: text.length },
    annotations: [{ id: 'T1', code: 'x', start, end: start + 6, text: 'severe' }]
  });
  assert.ok(Core.validateFile(mk('a'), 'A').every(c => c.level === 'ok'));
  const r = Core.compute(Core.normalize(mk('a'), 'A'), Core.normalize(mk('b'), 'B'), { unit: 'token', thr: 0.5 });
  assert.equal(r.overall.microIoU, 1);
});

test('all text units compute without error', () => {
  for (const unit of ['token', 'sentence', 'char']) {
    const r = Core.compute(Core.normalize(A, 'A'), Core.normalize(B, 'B'), { unit, thr: 0.5 });
    assert.ok(r.units.length > 0);
    assert.ok(r.overall.pooledAlpha > 0 && r.overall.pooledAlpha < 1);
  }
});
