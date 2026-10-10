/** Subtitle suggestion decisions and gap helpers. */
(function (global) {
  'use strict';
  function rowsFromSegments(segments) {
    return (segments || []).flatMap((segment, index) => {
      const pr = segment.proofread || {};
      const original = pr.review_original ?? pr.asr_original;
      const corrected = pr.review_text ?? pr.corrected;
      if (typeof original !== 'string' || typeof corrected !== 'string' || !corrected || original === corrected
          || (pr.status === 'manual' && pr.review_text == null)) return [];
      const current = String(segment.text || '');
      return [{ index, start: segment.start, end: segment.end, original, corrected, current,
        reason: pr.reason || '', state: pr.review_state || 'pending',
        locked: pr.status === 'manual' || ![original, corrected].includes(current) }];
    });
  }
  function validateDecisions(segments, rows, choices) {
    const fresh = new Map(rowsFromSegments(segments).map(row => [row.index, row]));
    const before = new Map(rows.map(row => [row.index, row]));
    const seen = new Set();
    choices.forEach(choice => {
      const row = fresh.get(choice.index), old = before.get(choice.index);
      if (seen.has(choice.index) || typeof choice.accepted !== 'boolean' || !row || !old || row.locked
          || ['start', 'end', 'original', 'corrected', 'current'].some(key => row[key] !== old[key])) {
        throw new Error('字幕已变化或已人工修改，请重新查看校对建议');
      }
      seen.add(choice.index);
    });
  }
  function applyDecisions(segments, rows, choices) {
    validateDecisions(segments, rows, choices);
    const byIndex = new Map(rows.map(row => [row.index, row]));
    choices.forEach(choice => {
      const row = byIndex.get(choice.index), segment = segments[choice.index];
      segment.text = choice.accepted ? row.corrected : row.original;
      segment.proofread = { ...segment.proofread, review_original: row.original, review_text: row.corrected,
        review_state: choice.accepted ? 'accepted' : 'rejected' };
      segment._dirty = true;
    });
  }
  function gapPlan(segments, indices, maxGapMs) {
    if (!Number.isInteger(maxGapMs) || maxGapMs < 0) throw new Error('最大空隙须为非负整数毫秒');
    const selected = indices == null ? null : new Set(indices);
    const changes = [];
    for (let i = 0; i < segments.length - 1; i++) {
      const left = segments[i], right = segments[i + 1];
      if (selected && (!selected.has(i) || !selected.has(i + 1))) continue;
      if (left.disabled || right.disabled || ![left.start, left.end, right.start, right.end].every(Number.isInteger)
          || left.end <= left.start || right.end <= right.start) continue;
      const gap = right.start - left.end;
      if (gap > 0 && gap <= maxGapMs) changes.push({ index: i, oldEnd: left.end, end: right.start, gap });
    }
    return changes;
  }
  global.MaweReview = { rowsFromSegments, validateDecisions, applyDecisions, gapPlan };
})(typeof window !== 'undefined' ? window : globalThis);
