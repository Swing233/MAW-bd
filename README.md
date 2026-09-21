# MAW-bd（精简版）

> 本项目基于 [Moyf/moys-asr-workflow](https://github.com/Moyf/moys-asr-workflow) 二次开发。
> 原项目及 MAW / MAWE 核心架构由 [Moyf](https://github.com/Moyf) 创建；本仓库保留完整的上游提交历史，并在其基础上聚焦 macOS、Qwen ASR、文稿对齐、DeepSeek 保守校对与 FCPXML 导出。

语音优先的字幕工作流：

```text
视频
  → Qwen ASR（主模型；可选副模型交叉验证）
  → 原文稿对齐（本地，顺序单调）
  → DeepSeek 保守校对（默认不自动改字幕文本）
  → 校验状态 + 颜色
  → MAWE 编辑
  → SRT
  → FCPXML（本地网页转换）
```

**核心原则：实际语音是真源，文稿只作错字/专名参考。**

## 仅支持

| 能力 | 说明 |
|---|---|
| ASR | `qwen-audio-3.0-asr-flash-filetrans`（默认）+ `qwen3-asr-flash-filetrans`（副） |
| 文稿 | TXT / Markdown / DOCX / 粘贴（**不支持 PDF**） |
| 校对 | `maw/bdversion` + DeepSeek 保守协议 |
| 编辑 | MAWE（预览/波形/Seek/拆分合并/颜色/保存/SRT + proofread 过滤） |
| 工程 | `.mosp`（毫秒时间，旧工程可打开） |
| FCPXML | 打开 `web/srt2fcpxml-page/index.html`（本地，MIT：GanymedeNil/srt2fcpxml） |
| macOS | `dist/MAW-bd.app`（PyInstaller；服务仅 `127.0.0.1`） |

## 源码运行

```bash
uv sync
uv run --no-sync python maw_gui.py          # Launcher
uv run --no-sync python server-editor/serve.py --blank   # 编辑器
```

`.env` 至少配置 `DASHSCOPE_API_KEY`。DeepSeek 校对可选配置 `MAW_POSTPROCESS_DEEPSEEK_API_KEY` 等。

## 测试

```bash
uv run --no-sync python -m unittest discover -s tests -p "test_*.py"
```

详见 `docs/BDVERSION_FOCUS.md`、`docs/MACOS_PACKAGING.md`、`docs/PROOFREAD_PROTOCOL.md`。

## 上游与许可证

- 原作者：[Moyf](https://github.com/Moyf)
- 上游项目：[Moyf/moys-asr-workflow](https://github.com/Moyf/moys-asr-workflow)
- 本项目继续遵循 [AGPL-3.0-only](LICENSE)。对上游代码的修改同样按该许可证发布。
- 第三方组件及许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
