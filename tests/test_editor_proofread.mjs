import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const src = readFileSync(join(root, 'web', 'editor-proofread.js'), 'utf8');

function loadProofread() {
  const sandbox = { window: {}, globalThis: {} };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return sandbox.MaweProofread;
}

test('markManual sets status and clears auto color', () => {
  const P = loadProofread();
  const seg = {
    text: '改过',
    proofread: { status: 'verified', asr_original: '原ASR' },
    color: { name: 'green', value: '#66bb6a' },
  };
  P.markManual(seg);
  assert.equal(seg.proofread.status, 'manual');
  assert.equal(seg.proofread.asr_original, '原ASR');
  assert.equal(seg.proofread.corrected, '改过');
  assert.equal(seg.color, null);
});

test('filterPass by status and llm_edited', () => {
  const P = loadProofread();
  const verified = { proofread: { status: 'verified' } };
  const corrected = { proofread: { status: 'uncertain', corrected: '新的' } };
  assert.equal(P.filterPass(verified, 'verified'), true);
  assert.equal(P.filterPass(verified, 'uncertain'), false);
  assert.equal(P.filterPass(corrected, 'llm_edited'), true);
  assert.equal(P.filterPass(verified, 'llm_edited'), false);
  assert.equal(P.filterPass(verified, 'all'), true);
});

test('renderDetail exposes script/asr/corrected/reason', () => {
  const P = loadProofread();
  const d = P.renderDetail({
    proofread: {
      status: 'improvised',
      match_score: 0.4,
      script_text: '文稿',
      asr_original: 'ASR',
      corrected: null,
      reason: '现场发挥',
    },
  });
  assert.equal(d.status, 'improvised');
  assert.equal(d.scriptText, '文稿');
  assert.equal(d.asrOriginal, 'ASR');
  assert.equal(d.reason, '现场发挥');
});

test('proofread diff isolates edits and preserves Unicode, inserts and deletes', () => {
  const P = loadProofread();
  for (const [before, after] of [['辣椒曲水', '辣椒驱水'], ['abc', 'abXc'], ['abXc', 'abc'], ['🙂原字', '🙂新字'], ['', '新增'], ['相同', '相同'], ['a'.repeat(600), 'a'.repeat(599) + 'b']]) {
    const diff = P.diffText(before, after);
    assert.equal(diff.left.map(p => p.text).join(''), before);
    assert.equal(diff.right.map(p => p.text).join(''), after);
    if (before === after) assert.equal(diff.left.some(p => p.changed), false);
  }
  const diff = P.diffText('辣椒曲水', '辣椒驱水');
  assert.equal(diff.left.filter(p => p.changed).map(p => p.text).join(''), '曲');
  assert.equal(diff.right.filter(p => p.changed).map(p => p.text).join(''), '驱');
});
