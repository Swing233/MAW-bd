# MAW-bd 使用说明（GUI 四步）

启动 `dist/MAW-bd.app`：

1. **导入文件** — 选择视频/音频
2. **ASR 语音识别** — **默认本地模型**
   - Qwen3-ASR 0.6B（推荐，本机已有模型缓存）
   - FunASR paraformer-zh / faster-whisper
   - 可选切换「云端 Qwen API」
3. **修订字幕**
   - **添加文稿**（TXT/MD/DOCX）→ 仅作 DeepSeek **参考**（人名/术语/错别字），不整段覆盖语音
   - DeepSeek 保守校对 **或** 自定义提示词
   - 输出 `*.修订.mosp` + `*.修订.srt`（时间轴不变）
**字幕编辑器随时可打开**：窗口顶部点击「打开字幕编辑器」会启动空白编辑器，可在其中选择工程；「导入工程打开」可直接选择现有 `.mosp` / `.json`。无需先完成 ASR 或修订。服务只监听 `127.0.0.1`。

## 本地 ASR 运行时

路径：

```text
~/Library/Application Support/MAW/local-runtime/bin/python
~/Library/Application Support/MAW/model-cache   # Qwen3-ASR / ForcedAligner 等
```

界面会显示「本地运行时」是否就绪。未安装时请改用云端，或重新安装 MAW 本地 Runtime。

## 配置（.env）

| 字段 | 键 |
|---|---|
| DashScope（云端 ASR） | `DASHSCOPE_API_KEY` |
| DeepSeek（修订） | `MAW_POSTPROCESS_DEEPSEEK_API_KEY` / `DEEPSEEK_API_KEY` |
| DeepSeek 模型 | 默认 `deepseek-flash` |

## 编辑器

- 沿用 **MAW / MAWE** 全套编辑能力（预览、波形、拆分合并、颜色、SRT、proofread）。
- **导出字幕 → 转为 .fcpxml**：弹窗选择
  - 帧率：23.98 / 24 / 25 / 29.97 / 30 / 50 / 59.94 / 60
  - 分辨率：1920×1080 / **3840×2160** / **2880×2160**
  - 算法沿用本地 `srt2fcpxml`（MIT）转换逻辑，仅导出最终字幕文字与时间。

## ASR 断句

- 本地默认 **Qwen3-ASR 1.7B**（`Qwen/Qwen3-ASR-1.7B`）。
- ASR 完成后会将断句写回同一套 `.mosp` / `.srt`；文稿校对只修正每条字幕内的文字，不再拆分、合并或重排字幕。
- 云端与本地识别共用自然断句：目标约 14 字，通常优先落在 10–16 字，普通上限 20 字，25 字只作为找不到自然边界时的绝对兜底；短句阈值 5 字，软停顿 450ms，强停顿 750ms。ASR 完成后不会再次自动重切，手动重新断句也只在原字幕范围内拆分。
- 直接导入 `.mosp` / `.json` 时，编辑器会读取工程里的 `media` 路径并自动加载或生成波形缓存；空白编辑器才跳过波形预计算。

## 修订提示词

- DeepSeek / 自定义 LLM 调用期间，模型的流式思考与输出会实时追加到右侧日志栏。
- 界面按钮 **生成提示词并复制**：生成可直接粘贴到 GPT 的 SRT 修订提示词；要求 GPT 直接提供一个 UTF-8 `.srt` 文件供下载，并保持序号、条数、分段边界和时间码，只校对每条内部文字。

## 波形框选

- 在字幕块上按住左键拖动：移动该字幕块，行为保持不变。
- 双击字幕块：弹出字幕修改框；支持取消、保存，以及 Cmd/Ctrl+Enter 保存。
- 在波形空白处直接按住左键拖动：框选字幕；按住 Shift 拖动时追加到已有选择。
- 在空白处单击但不拖动：仍按原逻辑跳转播放位置。
