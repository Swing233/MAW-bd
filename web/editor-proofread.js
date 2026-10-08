/**
 * MAWE proofread UI helpers (maw-bdversion).
 * Speech-first status: verified / improvised / uncertain / manual.
 * Manual is never auto-colored.
 */
(function (global) {
  'use strict';

  const STATUS_META = {
    verified: { label: '已校验', colorName: 'green', short: 'V' },
    improvised: { label: '现场发挥', colorName: 'yellow', short: 'I' },
    uncertain: { label: '待确认', colorName: 'red', short: 'U' },
    manual: { label: '人工修改', colorName: null, short: 'M' },
  };

  const FILTERS = [
    { id: 'all', label: '全部' },
    { id: 'verified', label: '已校验' },
    { id: 'improvised', label: '现场发挥' },
    { id: 'uncertain', label: '待确认' },
    { id: 'manual', label: '人工修改' },
    { id: 'llm_edited', label: '含校对建议' },
  ];

  function getProofread(segment) {
    const pr = segment && segment.proofread;
    return pr && typeof pr === 'object' ? pr : null;
  }

  function getStatus(segment) {
    const pr = getProofread(segment);
    const status = pr && typeof pr.status === 'string' ? pr.status : '';
    return STATUS_META[status] ? status : '';
  }

  function statusMeta(status) {
    return STATUS_META[status] || null;
  }

  function statusLabel(segment) {
    const status = getStatus(segment);
    return status ? STATUS_META[status].label : '';
  }

  function filterPass(segment, filterId) {
    if (!filterId || filterId === 'all') return true;
    const pr = getProofread(segment);
    if (filterId === 'llm_edited') {
      return Boolean(pr && pr.corrected && String(pr.corrected).length);
    }
    return getStatus(segment) === filterId;
  }

  /**
   * User edited subtitle text → status=manual.
   * Does not change start/end. Clears auto proofread color (manual has none).
   */
  function markManual(segment) {
    if (!segment || typeof segment !== 'object') return segment;
    const prev = getProofread(segment) || {};
    if (prev.asr_original == null) {
      // keep first known original when possible
      prev.asr_original = prev.asr_original != null ? prev.asr_original : segment.text;
    }
    const next = Object.assign({}, prev, {
      status: 'manual',
      asr_original: prev.asr_original != null ? prev.asr_original : segment.text,
      corrected: segment.text,
      reason: prev.reason || 'manual edit',
    });
    segment.proofread = next;
    // manual 不自动上色；若存在校对自动色则清除
    const color = segment.color;
    if (color && typeof color === 'object') {
      const autoNames = ['green', 'yellow', 'red'];
      if (autoNames.indexOf(color.name) >= 0) {
        segment.color = null;
        segment.color_ref = null;
      }
    }
    return segment;
  }

  function renderDetail(segment) {
    const pr = getProofread(segment);
    const status = getStatus(segment);
    const meta = statusMeta(status);
    return {
      status,
      statusLabel: meta ? meta.label : '—',
      matchScore: pr && typeof pr.match_score === 'number' ? pr.match_score : null,
      scriptText: pr && pr.script_text != null ? String(pr.script_text) : '',
      asrOriginal: pr && pr.asr_original != null ? String(pr.asr_original) : '',
      secondaryAsr: pr && pr.secondary_asr != null ? String(pr.secondary_asr) : '',
      corrected: pr && pr.corrected != null ? String(pr.corrected) : '',
      reason: pr && pr.reason != null ? String(pr.reason) : '',
      disagreement: pr && pr.disagreement && typeof pr.disagreement === 'object'
        ? pr.disagreement
        : null,
    };
  }

  // Unicode-aware LCS; bound work for unexpectedly large imported metadata.
  function diffText(before, after) {
    const a = Array.from(String(before || '')), b = Array.from(String(after || ''));
    const left = [], right = [];
    function add(list, text, changed) {
      if (!text) return;
      const last = list[list.length - 1];
      if (last && last.changed === changed) last.text += text;
      else list.push({ text, changed });
    }
    if (a.length * b.length > 250000) {
      let head = 0, tail = 0;
      while (head < Math.min(a.length, b.length) && a[head] === b[head]) head++;
      while (tail < Math.min(a.length, b.length) - head && a[a.length - tail - 1] === b[b.length - tail - 1]) tail++;
      for (const [chars, list] of [[a, left], [b, right]]) {
        add(list, chars.slice(0, head).join(''), false);
        add(list, chars.slice(head, chars.length - tail).join(''), true);
        add(list, chars.slice(chars.length - tail).join(''), false);
      }
      return { left, right };
    }
    const dp = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
    for (let i = a.length - 1; i >= 0; i--) {
      for (let j = b.length - 1; j >= 0; j--) {
        dp[i][j] = a[i] === b[j] ? 1 + dp[i + 1][j + 1] : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    let i = 0, j = 0;
    while (i < a.length || j < b.length) {
      if (i < a.length && j < b.length && a[i] === b[j]) {
        add(left, a[i++], false); add(right, b[j++], false);
      } else if (i < a.length && (j === b.length || dp[i + 1][j] >= dp[i][j + 1])) {
        add(left, a[i++], true);
      } else add(right, b[j++], true);
    }
    return { left, right };
  }

  function applyCueClass(el, segment) {
    if (!el || !el.classList) return;
    const status = getStatus(segment);
    el.classList.remove('proofread-verified', 'proofread-improvised', 'proofread-uncertain', 'proofread-manual');
    if (status) el.classList.add('proofread-' + status);
    el.dataset.proofreadStatus = status || '';
  }

  function createBadge(segment) {
    const status = getStatus(segment);
    if (!status) return null;
    const meta = STATUS_META[status];
    const span = document.createElement('span');
    span.className = 'proofread-badge proofread-badge-' + status;
    span.textContent = meta.short;
    span.tabIndex = 0;
    span.setAttribute('aria-label', meta.label + '，查看校验详情');
    return span;
  }

  global.MaweProofread = {
    STATUS_META,
    FILTERS,
    getProofread,
    getStatus,
    statusMeta,
    statusLabel,
    filterPass,
    markManual,
    renderDetail,
    applyCueClass,
    createBadge,
    diffText,
  };
})(typeof window !== 'undefined' ? window : globalThis);
