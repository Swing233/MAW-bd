/**
 * MAW-bd focused Launcher: 导入 → ASR → 修订 → 编辑器
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const api = () => window.pywebview?.api;
  let llmStreamLine = null;
  let llmStreamKind = '';
  let controlsBound = false;
  let updateChecked = false;
  let updateResultShown = false;
  let updateInstalling = false;

  window.MAWLauncher = {
    onBackendEvents(batch) {
      (batch || []).forEach((item) => {
        const type = (item && item.type) || 'focusStatus';
        window.dispatchEvent(new CustomEvent(type, { detail: item }));
      });
    },
  };

  function setMsg(text, isErr, options) {
    const el = $('msg');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('err', !!isErr);
    if (options?.log !== false && text && String(text).trim()) {
      appendLog(String(text).trim(), isErr ? 'err' : '');
    }
  }

  function appendLog(text, kind) {
    const box = $('log-scroll');
    if (!box || !text) return;
    const line = document.createElement('div');
    line.className = 'log-line' + (kind ? ' ' + kind : '');
    const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    line.textContent = '[' + stamp + '] ' + text;
    box.appendChild(line);
    // cap history
    while (box.childElementCount > 2000) {
      box.removeChild(box.firstElementChild);
    }
    box.scrollTop = box.scrollHeight;
  }

  function appendLlmDelta(detail) {
    const box = $('log-scroll');
    if (!box) return;
    const kind = String(detail?.kind || 'content');
    const value = String(detail?.text || '');
    if (kind === 'reset') {
      llmStreamLine?.remove();
      llmStreamLine = null;
      llmStreamKind = '';
      if (value) appendLog(value);
      return;
    }
    if (kind === 'start' || kind === 'done' || kind === 'error') {
      llmStreamLine = null;
      llmStreamKind = '';
      if (value) appendLog(value, kind === 'error' ? 'err' : (kind === 'done' ? 'ok' : ''));
      return;
    }
    if (!value) return;
    if (!llmStreamLine || !llmStreamLine.isConnected || llmStreamKind !== kind) {
      llmStreamLine = document.createElement('div');
      llmStreamLine.className = 'log-line llm-output';
      const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
      const label = kind === 'reasoning' ? 'LLM 思考' : 'LLM 输出';
      llmStreamLine.textContent = '[' + stamp + '] [' + label + '] ';
      box.appendChild(llmStreamLine);
      llmStreamKind = kind;
    }
    llmStreamLine.textContent += value;
    while (box.childElementCount > 2000) box.removeChild(box.firstElementChild);
    box.scrollTop = box.scrollHeight;
  }

  function logFromSetMsg() {
    // companion: keep a scrolling history whenever status changes
    const el = $('msg');
    if (!el) return;
    const text = (el.textContent || '').trim();
    if (!text) return;
    appendLog(text, el.classList.contains('err') ? 'err' : '');
  }

  function setBusy(busy) {
    ['btn-asr', 'btn-revise'].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = !!busy;
    });
  }

  function setStepProgress(stepProgress) {
    const map = {
      asr: ['prog-asr', 'pct-asr'],
      revise: ['prog-revise', 'pct-revise'],
      editor: ['prog-editor', 'pct-editor'],
    };
    const sp = stepProgress || {};
    Object.keys(map).forEach((key) => {
      const value = Math.max(0, Math.min(100, Number(sp[key] || 0)));
      const [barId, pctId] = map[key];
      const bar = $(barId);
      const pct = $(pctId);
      if (bar) bar.value = value;
      if (pct) pct.textContent = value + '%';
    });
  }

  function renderState(state) {
    if (!state) return;
    const status = state.status || {};
    const result = state.result || {};
    const config = state.config || {};
    if (state.appVersion) $('app-version').textContent = 'v' + state.appVersion;
    if (state.updateResult && !updateResultShown) {
      updateResultShown = true;
      const [kind, message] = String(state.updateResult).split('|', 2);
      setMsg(message || '更新状态未知', kind !== 'ok');
    }
    $('media-path').textContent = result.mediaPath || '（未选择）';
    const ms = result.manuscriptText || '';
    const msPath = result.manuscriptPath || '';
    if (ms.trim()) {
      $('manuscript-path').textContent = '已添加文稿（' + ms.length + ' 字）';
    } else if (msPath && msPath !== '(pasted)') {
      $('manuscript-path').textContent = msPath;
    } else {
      $('manuscript-path').textContent = '（未添加文稿）';
    }
    $('srt-path').textContent = result.srtPath || '—';
    $('project-path').textContent = result.projectPath || '—';
    $('revised-path').textContent = result.revisedSrtPath || result.revisedProjectPath || '—';
    // get_state is a snapshot and may repeat an event that was already logged.
    // Keep the visible status current without duplicating the log entry.
    if (status.message) {
      setMsg(status.message + (status.error ? ' · ' + status.error : ''), !!status.error, { log: false });
    }
    setStepProgress(status.stepProgress);
    $('cfg-deepseek').checked = !!(config.deepseekApiKey || localStorage.getItem('mawbd_ds'));
    if (config.deepseekModel) $('deepseek-model').value = config.deepseekModel;
    const hint = $('local-runtime-hint');
    if (hint) {
      hint.textContent = config.localRuntimeReady
        ? '本地运行时：' + config.localRuntimePath
        : '未检测到本地运行时，本地 ASR 将不可用';
    }
  }

  async function refresh() {
    const a = api();
    if (!a || !a.get_state) return;
    try {
      const state = await a.get_state({});
      renderState(state);
    } catch (e) {
      setMsg(String(e), true);
    }
  }

  async function saveConfig() {
    const a = api();
    if (!a) return;
    const ds = $('deepseek-key').value.trim();
    const model = $('deepseek-model').value.trim() || 'deepseek-flash';
    if (ds) localStorage.setItem('mawbd_ds', '1');
    const res = await a.save_config({
      deepseekApiKey: ds,
      deepseekModel: model,
    });
    if (res && res.ok) {
      setMsg('配置已保存到 ' + res.path);
      $('deepseek-key').value = '';
      await refresh();
    } else {
      setMsg((res && res.error) || '保存失败', true);
    }
  }

  async function generateGptPrompt() {
    const a = api();
    if (!a) return;
    const res = await a.build_gpt_srt_prompt({
      customPrompt: $('custom-prompt').value || '',
      manuscriptText: $('manuscript-text').value || '',
    });
    if (!res || !res.ok) {
      setMsg((res && res.error) || '无法生成提示词', true);
      return;
    }
    $('gpt-prompt-wrap').hidden = false;
    $('gpt-prompt').value = res.prompt || '';
    // auto copy
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(res.prompt);
        setMsg('已生成 GPT 提示词并复制到剪贴板（' + (res.length || 0) + ' 字）');
      } else {
        setMsg('已生成 GPT 提示词，请手动复制');
      }
    } catch (e) {
      setMsg('已生成 GPT 提示词，请手动复制', true);
    }
  }

  async function copyGptPrompt() {
    const text = $('gpt-prompt').value || '';
    if (!text) {
      setMsg('请先生成提示词', true);
      return;
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        setMsg('已复制提示词');
      } else {
        $('gpt-prompt').select();
        setMsg('请全选并复制文本框内容');
      }
    } catch (e) {
      $('gpt-prompt').select();
      setMsg('请全选并复制文本框内容', true);
    }
  }

  async function chooseMedia() {
    const a = api();
    if (!a) return;
    const res = await a.browse_media({});
    if (res && res.ok && res.path) {
      $('media-path').textContent = res.path;
      await refresh();
    } else if (res && res.error) {
      setMsg(res.error, true);
    }
  }

  function mediaFromInput() {
    return $('media-path').textContent.trim();
  }

  function openManuscriptDialog() {
    const mask = $('manuscript-modal');
    const ta = $('manuscript-text');
    // preload existing
    const current = $('manuscript-path').textContent || '';
    if (!ta.value && current.includes('字')) {
      // keep existing textarea if any
    }
    mask.classList.add('open');
    ta.focus();
  }

  function closeManuscriptDialog() {
    $('manuscript-modal').classList.remove('open');
  }

  async function confirmManuscript() {
    const text = $('manuscript-text').value || '';
    const a = api();
    if (a && a.set_manuscript_text) {
      const res = await a.set_manuscript_text({ text });
      if (res && res.ok) {
        setMsg(text.trim() ? `已添加文稿（${text.trim().length} 字）` : '文稿已清空');
        $('manuscript-path').textContent = text.trim()
          ? `已添加文稿（${text.trim().length} 字）`
          : '（未添加文稿）';
      } else {
        setMsg((res && res.error) || '文稿保存失败', true);
      }
    } else {
      $('manuscript-path').textContent = text.trim()
        ? `已添加文稿（${text.trim().length} 字）`
        : '（未添加文稿）';
    }
    closeManuscriptDialog();
    await refresh();
  }

  async function clearManuscript() {
    const a = api();
    if (a && a.clear_manuscript) await a.clear_manuscript({});
    $('manuscript-text').value = '';
    $('manuscript-path').textContent = '（未添加文稿）';
    setMsg('已清除文稿');
    await refresh();
  }

  function toggleAsrMode() {
    const local = $('asr-mode').value === 'local';
    const le = $('local-engine-wrap');
    const cm = $('cloud-model-wrap');
    if (le) le.hidden = !local;
    if (cm) cm.hidden = local;
  }

  async function startAsr() {
    const a = api();
    if (!a) return;
    const asrMode = $('asr-mode').value;
    const localEngine = $('local-engine').value;
    const modelId = $('asr-model').value;
    const res = await a.start_asr({
      asrMode,
      localEngine,
      modelId,
      mediaPath: mediaFromInput(),
    });
    if (!res || !res.ok) {
      setMsg((res && res.error) || '无法开始 ASR', true);
      return;
    }
    setMsg('ASR 已启动…');
    setBusy(true);
  }

  async function startRevise() {
    const a = api();
    if (!a) return;
    const mode = $('revise-mode').value;
    const customPrompt = $('custom-prompt').value;
    const manuscriptText = $('manuscript-text').value || '';
    const manuscriptLabel = $('manuscript-path').textContent.trim();
    const res = await a.start_revise({
      mode,
      customPrompt,
      deepseekModel: $('deepseek-model').value,
      manuscriptText,
      manuscriptPath: manuscriptLabel.includes('已添加') ? '(pasted)' : '',
    });
    if (!res || !res.ok) {
      setMsg((res && res.error) || '无法开始修订', true);
      return;
    }
    setMsg('修订已启动…');
    setBusy(true);
  }

  async function openExistingProject() {
    const a = api();
    if (!a || !a.open_existing_project) {
      setMsg('当前环境不支持导入工程', true);
      return;
    }
    const res = await a.open_existing_project({});
    if (res && res.cancelled) {
      setMsg('已取消选择工程');
      return;
    }
    if (!res || !res.ok) {
      setMsg((res && res.error) || '无法打开工程', true);
      return;
    }
    setMsg('已导入工程并在编辑器打开：' + (res.projectPath || ''));
    await refresh();
  }

  async function openMediaEditor() {
    const a = api();
    if (!a || !a.open_media_editor) {
      setMsg('当前环境不支持直接编辑媒体', true);
      return;
    }
    const button = $('btn-media-editor');
    let mediaPath = mediaFromInput();
    if (!mediaPath || mediaPath === '（未选择）') {
      if (!a.browse_media) {
        setMsg('当前环境不支持选择媒体', true);
        return;
      }
      setMsg('请选择要直接编辑的视频或音频…');
      try {
        const picked = await a.browse_media({});
        if (!picked || !picked.path) {
          setMsg((picked && picked.error) || '已取消选择媒体', !!picked?.error);
          return;
        }
        mediaPath = picked.path;
        $('media-path').textContent = mediaPath;
      } catch (error) {
        setMsg('选择媒体失败：' + String(error), true);
        return;
      }
    }

    if (button) button.disabled = true;
    setMsg('正在创建字幕编辑工程并准备波形…');
    try {
      const res = await a.open_media_editor({ mediaPath });
      if (!res || !res.ok) {
        setMsg((res && res.error) || '无法打开媒体编辑工程', true);
        return;
      }
      setMsg(res.importedSrt
        ? `已生成波形并载入同名 SRT：${res.srtPath || ''}`
        : '已生成波形并打开编辑器，可在编辑器中加载 SRT');
      await refresh();
    } catch (error) {
      setMsg('无法打开媒体编辑工程：' + String(error), true);
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function openEditor() {
    const a = api();
    if (!a) return;
    const res = await a.open_editor({});
    if (!res || !res.ok) {
      setMsg((res && res.error) || '无法打开编辑器', true);
      return;
    }
    const url = res.url || 'http://127.0.0.1:8250';
    setMsg((res.blank ? '空白编辑器已启动：' : '编辑器已启动：') + url);
  }

  function renderUpdate(result, manual) {
    const banner = $('update-banner');
    if (!result || !result.ok) {
      if (manual) setMsg((result && result.error) || '检查更新失败', true);
      return;
    }
    $('app-version').textContent = 'v' + (result.currentVersion || '—');
    if (!result.available) {
      banner.hidden = true;
      if (manual) setMsg('当前已是最新版本 v' + result.currentVersion);
      return;
    }
    $('update-title').textContent = `发现新版本 v${result.latestVersion}`;
    $('update-notes').textContent = result.notes || '新版本已经发布。';
    $('btn-update-download').textContent = result.downloadUrl && result.assetDigest
      ? `一键安装 v${result.latestVersion}` : '查看更新';
    banner.hidden = false;
    $('btn-update').textContent = `有新版本 v${result.latestVersion}`;
    $('btn-update').classList.add('update-available');
    if (manual) setMsg(`发现新版本 v${result.latestVersion}`);
  }

  async function checkForUpdates(options) {
    const a = api();
    const manual = !!options?.manual;
    if (!a || !a.check_for_updates) return;
    const button = $('btn-update');
    button.disabled = true;
    if (manual) button.textContent = '正在检查…';
    try {
      const result = await a.check_for_updates({});
      updateChecked = true;
      renderUpdate(result, manual);
    } catch (error) {
      if (manual) setMsg('检查更新失败：' + String(error), true);
    } finally {
      button.disabled = false;
      if (!button.classList.contains('update-available')) button.textContent = '检查更新';
    }
  }

  async function openUpdatePage() {
    const a = api();
    if (!a) {
      setMsg('当前环境无法更新', true);
      return;
    }
    const button = $('btn-update-download');
    if (updateInstalling) return;
    button.disabled = true;
    try {
      if (button.textContent.startsWith('一键安装') && a.install_update) {
        const result = await a.install_update({});
        if (!result?.ok) {
          setMsg(result?.error || '无法开始更新', true);
          return;
        }
        updateInstalling = true;
        button.textContent = '正在下载…';
        setMsg('正在下载并验证新版，完成后会自动重启安装');
        return;
      }
      if (!a.open_update_page) throw new Error('当前环境无法打开更新页面');
      const result = await a.open_update_page({});
      if (!result || !result.ok) {
        setMsg((result && result.error) || '无法打开更新页面', true);
        return;
      }
      setMsg(result.directDownload ? '已在浏览器开始下载更新' : '已打开更新页面');
    } catch (error) {
      setMsg('无法打开更新页面：' + String(error), true);
    } finally {
      if (!updateInstalling) button.disabled = false;
    }
  }

  function bind() {
    if (controlsBound) return;
    controlsBound = true;
    $('btn-media').addEventListener('click', chooseMedia);
    $('btn-save-config').addEventListener('click', saveConfig);
    $('btn-asr').addEventListener('click', startAsr);
    $('btn-revise').addEventListener('click', startRevise);
    $('btn-gpt-prompt').addEventListener('click', generateGptPrompt);
    $('btn-copy-gpt-prompt').addEventListener('click', copyGptPrompt);
    $('btn-editor').addEventListener('click', openEditor);
    $('btn-open-project')?.addEventListener('click', openExistingProject);
    $('btn-media-editor')?.addEventListener('click', openMediaEditor);
    $('btn-update')?.addEventListener('click', () => checkForUpdates({ manual: true }));
    $('btn-update-download')?.addEventListener('click', openUpdatePage);
    $('btn-update-dismiss')?.addEventListener('click', () => { $('update-banner').hidden = true; });
    $('btn-manuscript').addEventListener('click', openManuscriptDialog);
    $('btn-clear-manuscript').addEventListener('click', clearManuscript);
    $('btn-manuscript-cancel').addEventListener('click', closeManuscriptDialog);
    $('btn-manuscript-ok').addEventListener('click', confirmManuscript);
    $('asr-mode').addEventListener('change', toggleAsrMode);
    $('btn-stop').addEventListener('click', async () => {
      const a = api();
      if (a && a.stop_task) {
        await a.stop_task({});
        setMsg('已请求停止');
      }
    });
    $('revise-mode').addEventListener('change', () => {
      const custom = $('revise-mode').value === 'custom';
      $('custom-prompt-wrap').hidden = !custom;
    });
    $('manuscript-modal').addEventListener('click', (e) => {
      if (e.target === $('manuscript-modal')) closeManuscriptDialog();
    });
    $('btn-clear-log')?.addEventListener('click', () => {
      const box = $('log-scroll');
      if (box) box.replaceChildren();
    });
    $('btn-toggle-log')?.addEventListener('click', () => {
      setLogCollapsed(true);
      $('btn-show-log')?.focus();
    });
    $('btn-show-log')?.addEventListener('click', () => {
      setLogCollapsed(false);
      $('btn-toggle-log')?.focus();
    });
    toggleAsrMode();
    restoreLogCollapsed();
  }

  function setLogCollapsed(collapsed) {
    const page = document.querySelector('.page');
    const rail = $('log-rail');
    const toggle = $('btn-toggle-log');
    const show = $('btn-show-log');
    if (page) page.classList.toggle('log-collapsed', !!collapsed);
    if (rail) rail.hidden = !!collapsed;
    if (toggle) toggle.setAttribute('aria-expanded', String(!collapsed));
    if (show) {
      show.hidden = !collapsed;
      show.setAttribute('aria-expanded', String(!collapsed));
    }
    try { localStorage.setItem('mawbd_log_collapsed', collapsed ? '1' : '0'); } catch (e) {}
  }

  function restoreLogCollapsed() {
    let collapsed = false;
    try { collapsed = localStorage.getItem('mawbd_log_collapsed') === '1'; } catch (e) {}
    setLogCollapsed(collapsed);
  }

  window.addEventListener('focusStatus', (event) => {
    const detail = event.detail || {};
    if (detail.message) setMsg(detail.message + (detail.error ? ' · ' + detail.error : ''), !!detail.error);
    if (detail.stepProgress) setStepProgress(detail.stepProgress);
    if (!detail.busy && (detail.step === 'asr_done' || detail.step === 'revise_done' || detail.step === 'error')) {
      setBusy(false);
      refresh();
    }
  });
  window.addEventListener('focusLlmDelta', (event) => appendLlmDelta(event.detail || {}));
  window.addEventListener('focusUpdate', (event) => {
    const detail = event.detail || {};
    const button = $('btn-update-download');
    if (detail.error) {
      updateInstalling = false;
      button.disabled = false;
      button.textContent = '重试更新';
      setMsg(detail.message || '更新失败', true);
      return;
    }
    button.textContent = `${detail.message || '正在更新'} ${detail.percent || 0}%`;
    if (detail.percent === 100 || detail.percent === 0 || detail.percent % 20 === 0) {
      setMsg(detail.message || '正在更新');
    }
  });

  window.addEventListener('pywebviewready', () => {
    bind();
    refresh();
    if (!updateChecked) checkForUpdates({ manual: false });
  });

  document.addEventListener('DOMContentLoaded', () => {
    bind();
  });
})();
