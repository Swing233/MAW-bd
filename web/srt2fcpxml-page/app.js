/**
 * SRT → FCPXML (browser)
 * Ported from GanymedeNil/srt2fcpxml (MIT, Copyright (c) 2019 GanymedeNil)
 * FCP X 10.4.6-style FCPXML template logic.
 * https://github.com/GanymedeNil/srt2fcpxml
 */
(function () {
  'use strict';

  const SUPPORTED_FPS = ['23.98', '24', '25', '29.97', '30', '50', '59.94', '60'];
  let lastXml = '';

  function $(id) {
    return document.getElementById(id);
  }

  function round(n) {
    // Go lib.Round to 0 decimals (half away from zero-ish; JS Math.round is fine for positive times)
    return Math.round(n);
  }

  /** FrameMapString: float → 1001/{round(v)*1000}; int → 100/{v*100} */
  function frameMapString(fpsValue) {
    const isFloat = String(fpsValue).includes('.');
    if (isFloat) {
      const v = parseFloat(fpsValue);
      return '1001/' + String(round(v) * 1000);
    }
    const iv = parseInt(fpsValue, 10);
    return '100/' + String(iv * 100);
  }

  /** FrameDurationFormat → {molecular, denominator} */
  function frameDurationFormat(fpsValue) {
    const isFloat = String(fpsValue).includes('.');
    if (isFloat) {
      const v = parseFloat(fpsValue);
      return { mol: 1001, den: round(v) * 1000 };
    }
    const iv = parseInt(fpsValue, 10);
    return { mol: 100, den: iv * 100 };
  }

  /** fps numeric used in round(seconds * fps) */
  function frameDuration(fpsValue) {
    return String(fpsValue).includes('.') ? parseFloat(fpsValue) : parseInt(fpsValue, 10);
  }

  function escapeXml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function parseSrtTime(part) {
    const t = part.trim().replace(',', '.');
    const bits = t.split(':');
    let hh = 0;
    let mm = 0;
    let ss = 0;
    if (bits.length === 3) {
      hh = parseInt(bits[0], 10) || 0;
      mm = parseInt(bits[1], 10) || 0;
      ss = parseFloat(bits[2]) || 0;
    } else if (bits.length === 2) {
      hh = 0;
      mm = parseInt(bits[0], 10) || 0;
      ss = parseFloat(bits[1]) || 0;
    } else {
      ss = parseFloat(bits[0]) || 0;
    }
    return hh * 3600 + mm * 60 + ss;
  }

  function parseSrt(text) {
    const normalized = String(text || '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .trim();
    if (!normalized) return [];
    const blocks = normalized.split(/\n{2,}/);
    const items = [];
    for (const block of blocks) {
      const lines = block.split('\n').filter((ln, i, arr) => !(i === arr.length - 1 && ln === ''));
      if (!lines.length) continue;
      let idx = 0;
      if (/^\d+$/.test(lines[0].trim())) idx = 1;
      let timingIdx = -1;
      for (let i = idx; i < lines.length; i++) {
        if (lines[i].includes('-->')) {
          timingIdx = i;
          break;
        }
      }
      if (timingIdx < 0) continue;
      const [left, right] = lines[timingIdx].split('-->');
      const start = parseSrtTime(left);
      const end = parseSrtTime((right || '').trim().split(/\s+/)[0] || '0');
      const body = lines.slice(timingIdx + 1).join('\n').trim();
      if (!body) continue;
      if (!(end > start)) continue;
      items.push({ start, end, text: body });
    }
    return items;
  }

  /** Port of core.Srt2FcpXmlExport */
  const EXTRA_RES = true; // resolution validated as WxH positive ints

  function buildFcpxml(items, opts) {
    const fpsRaw = opts.fps;
    const width = opts.width;
    const height = opts.height;
    const projectName = opts.projectName || 'MAW Subtitles';
    if (!SUPPORTED_FPS.includes(String(fpsRaw))) {
      throw new Error('不支持的帧率: ' + fpsRaw);
    }
    if (!items.length) {
      throw new Error('没有可导出的字幕条目');
    }

    const fps = frameDuration(fpsRaw);
    const { mol, den } = frameDurationFormat(fpsRaw);
    const frameDurationAttr = frameMapString(fpsRaw) + 's';
    // Format name: FFVideoFormat{w}x{h}p{fps*100}
    const fmtName = 'FFVideoFormat' + width + 'x' + height + 'p' + round(fps * 100);

    const endSec = Math.max.apply(null, items.map((it) => it.end));
    const seqDuration = (round(endSec * fps) * mol) / den;
    const seqDurationAttr =
      String(round(endSec * fps) * mol) + '/' + String(den) + 's';

    // projectStart = 3.6 * den * mol  (same formula as upstream Gap/Title)
    const projectStart = 3.6 * den * mol;
    const gapDurationAttr =
      String(round(endSec * fps) * mol) + '/' + String(den) + 's';
    const gapStartAttr = String(projectStart) + '/' + String(den) + 's';

    const effectUid =
      '.../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti';

    const titleParts = items.map(function (item, index) {
      const tsId = 'ts' + (index + 1);
      const offsetNum = round(item.start * fps) * mol + projectStart;
      const offsetAttr = String(offsetNum) + '/' + String(den) + 's';
      // Upstream duration formula (kept for compatibility with FCP 10.4.6 import path)
      const durNum =
        (round((item.end - item.start) * fps) * mol * 120000.0) / den;
      const durationAttr = String(durNum) + '/120000s';
      const titleStartAttr = String(projectStart) + '/' + String(den) + 's';
      const name = item.text.split('\n')[0].slice(0, 80);
      return (
        '                    <title name="' +
        escapeXml(name) +
        '" lane="1" offset="' +
        offsetAttr +
        '" ref="r2" duration="' +
        durationAttr +
        '" start="' +
        titleStartAttr +
        '">\n' +
        '                        <param name="Position" key="9999/999166631/999166633/1/100/101" value="0 -450"/>\n' +
        '                        <param name="Alignment" key="9999/999166631/999166633/2/354/999169573/401" value="1 (Center)"/>\n' +
        '                        <param name="Flatten" key="9999/999166631/999166633/2/351" value="1"/>\n' +
        '                        <text>\n' +
        '                            <text-style ref="' +
        tsId +
        '">' +
        escapeXml(item.text) +
        '</text-style>\n' +
        '                        </text>\n' +
        '                        <text-style-def id="' +
        tsId +
        '">\n' +
        '                            <text-style font="PingFang SC" fontSize="52" fontFace="Semibold" fontColor="0.999993 1 1 1" bold="1" shadowColor="0 0 0 0.75" shadowOffset="5 315" alignment="center"/>\n' +
        '                        </text-style-def>\n' +
        '                    </title>'
      );
    });

    const xml =
      '<?xml version="1.0" encoding="UTF-8" ?>\n' +
      '<!DOCTYPE fcpxml>\n' +
      '<fcpxml version="1.7">\n' +
      '    <resources>\n' +
      '        <format id="r1" name="' +
      fmtName +
      '" frameDuration="' +
      frameDurationAttr +
      '" width="' +
      width +
      '" height="' +
      height +
      '" colorSpace="1-1-1 (Rec. 709)"/>\n' +
      '        <effect id="r2" name="Basic Title" uid="' +
      effectUid +
      '"/>\n' +
      '    </resources>\n' +
      '    <library>\n' +
      '        <event name="' +
      escapeXml(projectName) +
      '">\n' +
      '            <project name="' +
      escapeXml(projectName) +
      '" uid="' +
      escapeXml(projectName) +
      '" modDate="2020-01-01 00:00:00 +0800">\n' +
      '                <sequence format="r1" duration="' +
      seqDurationAttr +
      '" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">\n' +
      '                    <spine>\n' +
      '                        <gap name="空隙" offset="0s" duration="' +
      gapDurationAttr +
      '" start="' +
      gapStartAttr +
      '">\n' +
      titleParts.join('\n') +
      '\n' +
      '                        </gap>\n' +
      '                    </spine>\n' +
      '                </sequence>\n' +
      '            </project>\n' +
      '        </event>\n' +
      '    </library>\n' +
      '</fcpxml>\n';

    void seqDuration;
    return xml;
  }

  function setStatus(msg, isErr) {
    const el = $('status');
    el.textContent = msg;
    el.classList.toggle('err', Boolean(isErr));
  }

  function convert() {
    try {
      const items = parseSrt($('srtText').value);
      const res = ($('res').value || '1920x1080').split('x');
      const xml = buildFcpxml(items, {
        fps: $('fps').value,
        width: parseInt(res[0], 10),
        height: parseInt(res[1], 10),
        projectName: $('projectName').value.trim() || 'MAW Subtitles',
      });
      lastXml = xml;
      $('preview').textContent = xml;
      $('downloadBtn').disabled = false;
      $('copyBtn').disabled = false;
      setStatus('已生成：' + items.length + ' 条字幕 · 帧率 ' + $('fps').value + ' · ' + res[0] + '×' + res[1]);
    } catch (err) {
      lastXml = '';
      $('downloadBtn').disabled = true;
      $('copyBtn').disabled = true;
      $('preview').textContent = '// ' + (err && err.message ? err.message : String(err));
      setStatus(err && err.message ? err.message : '转换失败', true);
    }
  }

  function download() {
    if (!lastXml) return;
    let name = ($('outputName').value || 'subtitles.fcpxml').trim();
    if (!/\.fcpxml$/i.test(name)) name += '.fcpxml';
    const blob = new Blob([lastXml], { type: 'application/xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function copyXml() {
    if (!lastXml) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(lastXml).then(
        function () {
          setStatus('已复制到剪贴板');
        },
        function () {
          setStatus('复制失败，请手动全选预览内容', true);
        },
      );
    } else {
      setStatus('当前环境不支持自动复制，请手动复制预览', true);
    }
  }

  $('srtFile').addEventListener('change', function (e) {
    const file = e.target.files && e.target.files[0];
    if (!file) {
      $('fileName').textContent = '未选择文件';
      return;
    }
    $('fileName').textContent = file.name;
    const reader = new FileReader();
    reader.onload = function () {
      $('srtText').value = String(reader.result || '');
      if (!$('outputName').value || $('outputName').value === 'subtitles.fcpxml') {
        $('outputName').value = file.name.replace(/\.srt$/i, '') + '.fcpxml';
      }
      if (!$('projectName').value.trim() || $('projectName').value === 'MAW Subtitles') {
        $('projectName').value = file.name.replace(/\.srt$/i, '') || 'MAW Subtitles';
      }
      setStatus('已读取 ' + file.name);
    };
    reader.onerror = function () {
      setStatus('读取文件失败', true);
    };
    reader.readAsText(file, 'utf-8');
  });

  $('convertBtn').addEventListener('click', convert);
  $('downloadBtn').addEventListener('click', download);
  $('copyBtn').addEventListener('click', copyXml);

  // expose for tests
  window.Srt2FcpxmlPage = { parseSrt: parseSrt, buildFcpxml: buildFcpxml };
})();
