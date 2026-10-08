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

### 波形快捷切割

鼠标停在波形字幕块上会显示剪刀与切割线，按默认 B 键直接在该线的整数毫秒位置切割，不打开文字断点窗口。主字幕列表悬停显示文字断点，同样可直接切割；鼠标不在字幕块上时使用当前播放头切割主字幕；距两端不足 100ms 时提示移动切点。拆分后可撤销。

「设置 → 通用操作 → 编辑快捷键」可配置分割、合并、新建、起点和终点键，选择冲突键时互换，支持恢复默认。可用 B/C/N/Z/X 与 F2–F8；其它键保留给原有操作。配置保存在当前编辑器的本地设置中。

文字分配优先使用完整对齐、顺序有效的字词时间码；旧工程缺少可靠时间码时仅估计文字位置并寻找附近词边界，不将估算位置写成字级时间。英文单词、版本号、URL 和数字量词组合不在内部直接切开。

### 校验详情与播放头文字预览

选中字幕不再自动展开校验详情。悬停或键盘聚焦字幕前的 V/I/U/M 徽标，可查看文稿、原始 ASR、副 ASR、校对建议与原因；原识别差异以红色标出，校对后差异以绿色标出。鼠标可移入浮窗阅读，离开、按 Esc 或滚动字幕列表后关闭。

主字幕编辑区下方显示播放头所在字幕的文字切点，随时间轴拖动刷新；它与实际时间切分使用相同的断点计算，分隔符不写入字幕。输入字幕时暂时隐藏预览，避免影响文字输入。
