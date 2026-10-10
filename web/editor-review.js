/** Human review UI using MAWE design tokens. */
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
        throw new Error('字幕已变化或已人工修改，请重新打开审查');
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
  function node(tag, text, parent) {
    const element = document.createElement(tag);
    if (text != null) element.textContent = text;
    if (parent) parent.appendChild(element);
    return element;
  }
  function open({ rows, onApply, onLocate } = {}) {
    const previous = document.getElementById('llm-review-dialog');
    if (previous?.open) return;
    previous?.remove();
    const opener = document.activeElement;
    const dialog = node('dialog'); dialog.id = 'llm-review-dialog'; dialog.className = 'mawe-dialog llm-review';
    dialog.setAttribute('aria-labelledby', 'llm-review-title');
    const header = node('header', null, dialog); node('h3', '校对审查', header).id = 'llm-review-title';
    const toolbar = node('div', null, dialog); toolbar.className = 'review-toolbar';
    const filter = node('select', null, toolbar); filter.id = 'llm-review-filter'; filter.setAttribute('aria-label', '筛选校对建议');
    [['all', '全部建议'], ['pending', '待审查'], ['digits', '含阿拉伯数字'], ['english', '含英文'], ['punctuation', '含标点符号']].forEach(([value, label]) => {
      const option = node('option', label, filter); option.value = value;
    });
    const checked = new Map(rows.map(row => [row.index, row.state === 'accepted']));
    node('p', '勾选采用建议，未勾选保留原文。应用后可撤销。', header).className = 'review-muted';
    const count = node('p', '', toolbar); count.className = 'review-muted';
    const actions = node('div', null, toolbar); actions.className = 'review-actions';
    const selectAll = node('button', '勾选当前显示', actions), deselectAll = node('button', '取消当前显示', actions);
    const list = node('div', null, dialog); list.id = 'llm-review-list'; list.className = 'llm-review-list';
    const visible = () => rows.filter(row => filter.value === 'all'
      || (filter.value === 'pending' && row.state === 'pending')
      || (filter.value === 'digits' && /[0-9]/.test(row.original + row.corrected))
      || (filter.value === 'english' && /[A-Za-z]/.test(row.original + row.corrected))
      || (filter.value === 'punctuation' && /\p{P}/u.test(row.original + row.corrected)));
    function diffLine(parent, label, parts, className) {
      const line = node('p', null, parent); line.className = 'review-text'; node('strong', label, line);
      const content = node('span', null, line);
      parts.forEach(part => { const span = node(part.changed ? 'mark' : 'span', part.text, content); if (part.changed) span.className = className; });
    }
    function render() {
      list.replaceChildren();
      const displayed = visible();
      count.textContent = `显示 ${displayed.length} / ${rows.length} 条建议 · 已勾选 ${rows.filter(row => !row.locked && checked.get(row.index)).length} 条`;
      if (!displayed.length) node('p', '没有符合条件的校对建议', list);
      displayed.forEach(row => {
        const item = node('section', null, list); item.className = 'llm-review-row'; item.dataset.index = row.index;
        const rowHeader = node('div', null, item); rowHeader.className = 'review-row-head';
        const label = node('label', null, rowHeader), checkbox = node('input', null, label);
        checkbox.type = 'checkbox'; checkbox.checked = checked.get(row.index); checkbox.disabled = row.locked;
        checkbox.setAttribute('aria-label', `采用第 ${row.index + 1} 条建议`);
        node('span', `字幕 ${row.index + 1}`, label);
        const time = ms => { const sec = Math.floor(ms / 1000); return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`; };
        node('span', `${time(row.start)} → ${time(row.end)}`, rowHeader).className = 'review-time';
        if (onLocate) node('button', '定位', rowHeader).addEventListener('click', () => onLocate(row));
        checkbox.addEventListener('change', () => { checked.set(row.index, checkbox.checked); count.textContent = `显示 ${displayed.length} / ${rows.length} 条建议 · 已勾选 ${rows.filter(r => !r.locked && checked.get(r.index)).length} 条`; });
        const diff = global.MaweProofread.diffText(row.original, row.corrected);
        const comparison = node('div', null, item); comparison.className = 'review-comparison';
        diffLine(comparison, '原文', diff.left, 'review-removed'); diffLine(comparison, '建议', diff.right, 'review-added');
        node('p', row.reason || '未提供修改原因', item).className = 'review-reason';
        if (row.locked) node('p', '已人工修改或文字已变化，已保护，不会覆盖', item).className = 'review-muted';
      });
    }
    filter.addEventListener('change', render);
    for (const [button, value] of [[selectAll, true], [deselectAll, false]]) button.addEventListener('click', () => { visible().forEach(row => { if (!row.locked) checked.set(row.index, value); }); render(); });
    const error = node('p', '', dialog); error.id = 'llm-review-error'; error.className = 'review-error'; error.setAttribute('role', 'alert');
    const footer = node('footer', null, dialog);
    const save = node('button', '应用审查结果', footer); save.id = 'llm-review-save'; save.className = 'primary';
    const cancel = node('button', '暂不处理', footer); cancel.id = 'llm-review-cancel';
    footer.append(cancel, save);
    let busy = false;
    save.addEventListener('click', async () => {
      if (busy) return;
      busy = true; error.textContent = '';
      dialog.querySelectorAll('button,input,select').forEach(el => { el.disabled = true; });
      try {
        await onApply(rows.filter(row => !row.locked).map(row => ({ index: row.index, accepted: checked.get(row.index) })));
        dialog.close();
      } catch (err) {
        error.textContent = err.message || String(err); busy = false;
        dialog.querySelectorAll('button,select').forEach(el => { el.disabled = false; }); render();
      }
    });
    cancel.addEventListener('click', () => { if (!busy) dialog.close(); });
    dialog.addEventListener('keydown', event => event.stopPropagation());
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.addEventListener('close', () => { dialog.remove(); if (opener?.isConnected) opener.focus(); });
    document.body.appendChild(dialog); render(); dialog.showModal();
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
  global.MaweReview = { rowsFromSegments, validateDecisions, applyDecisions, open, gapPlan };
})(typeof window !== 'undefined' ? window : globalThis);
