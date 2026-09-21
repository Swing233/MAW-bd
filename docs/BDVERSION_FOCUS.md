# MAW-bd 产品范围（唯一需求基线）

## 目标流水线

```text
视频
  → Qwen ASR（主：qwen-audio-3.0-asr-flash-filetrans；副：qwen3-asr-flash-filetrans）
  → 原文稿对齐（本地顺序单调；TXT/MD/DOCX/粘贴）
  → DeepSeek 保守校对（语音优先；corrected 默认不自动覆盖 text）
  → 校验状态 + 既有五色
  → MAWE 编辑（核心能力 + proofread 过滤/manual）
  → SRT（仅最终字幕）
  → FCPXML（本地网页 web/srt2fcpxml-page，MIT GanymedeNil/srt2fcpxml）
```

## 约束

- 语音是真源；文稿只作错字/专名参考
- `.mosp` 毫秒契约；旧工程可打开
- 服务仅 `127.0.0.1`
- macOS 交付：`dist/MAW-bd.app`（PyInstaller）
- 不手改 `blank-editor.html`

## 决策（已确认）

1. DeepSeek 不自动覆盖 `segments[*].text`
2. `manual` 不自动上色
3. 包名模块：`maw/bdversion`
4. FCPXML：本地转换网页（非 Python 主路径）
5. 新流水线 Launcher 默认关闭

## 已删除（本分支）

- 其它 ASR、本地模型、OCR、旧文稿改写匹配、口播对齐、翻译重分句
- Tauri MOSE、官网 website、Python exporters、多平台发布脚本
- 测试反馈长文 / 历史开发笔记 / 调研文档
- **编辑器重功能**：贴纸/表情包、Lottie/OGraf、ASS 样式库与 ASS 导出、OTIO/OTIOZ、多重字幕/叠加轨、FCP7 模板
  - UI 隐藏 + `server-editor` 相关 API 返回 501
  - `maw/ass_styles.py` / `lottie_glyphs.py` 改为最小桩（兼容 burn/ffmpeg 调用）

## 相关文档

- `README.md`
- `docs/PROOFREAD_PROTOCOL.md`
- `docs/MACOS_PACKAGING.md`
- `docs/WORKFLOW.md` / `CLI.md` / `EDITOR_GUIDE.md` / `DEVELOPMENT.md`
- `JSON_SCHEMA.md`（含 `proofread`）
