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
    span.title = meta.label;
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
  };
})(typeof window !== 'undefined' ? window : globalThis);
