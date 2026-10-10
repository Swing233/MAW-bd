# MAW-bd（精简版）

> 本项目基于 [Moyf/moys-asr-workflow](https://github.com/Moyf/moys-asr-workflow) 二次开发。
> 原项目及 MAW / MAWE 核心架构由 [Moyf](https://github.com/Moyf) 创建；本仓库保留完整的上游提交历史，并在其基础上聚焦 macOS、Qwen ASR、文稿对齐、DeepSeek 保守校对与 FCPXML 导出。

MAW-bd 面向 macOS 字幕制作：识别视频语音，参考文稿校对，再编辑字幕并导出 SRT 或 FCPXML。

**实际语音是真源，文稿只用于纠错。** 保留现场发挥、口语和重复，不把字幕改写成文稿。

## 下载与安装

从 [Releases](https://github.com/Swing233/MAW-bd/releases) 下载 macOS Apple Silicon 完整 ZIP，解压后将 `MAW-bd.app` 放入「应用程序」。首次使用本地识别需要联网准备运行环境和模型，无需另装原版 MAW。

已有软件可在启动器点击「检查更新」。增量包仅供更新器使用，首次安装下载完整包。

## 如何使用

1. 选择视频或音频，使用本地模型或云端 Qwen 识别。
2. 按需添加文稿，使用 DeepSeek 校对文字。
3. 打开编辑器，检查文字、拆分字幕和调整时间。
4. 保存 `.mosp` 工程，再导出 SRT 或 FCPXML。

已有视频和 SRT 时，点击「MP4 + SRT 直接编辑」；已有工程时点击「导入工程打开」。编辑器可随时打开，不必先运行识别。

## 使用文档

| 想了解什么 | 文档 |
| --- | --- |
| 第一次制作字幕 | [完整使用教程](docs/WORKFLOW.md) |
| 识别、模型、API 配置与更新 | [启动器指南](docs/GUI_GUIDE.md) |
| 编辑、快捷键、审阅与导出 | [字幕编辑器指南](docs/EDITOR_GUIDE.md) |
| 安装、下载、波形和导出问题 | [常见问题](docs/FAQ.md) |
| 每个版本的变化 | [CHANGELOG](CHANGELOG.md) |

文档对应 1.8.0。LLM 校对结果默认直接应用，保留修改前文字可供恢复；1.7.0 使用先保存建议、在编辑器采用的流程。

## 主要功能

- 本地 Qwen3-ASR 1.7B、FunASR、faster-whisper；云端 Qwen Audio 3.0 与 Qwen3 ASR。
- 文稿支持 TXT、Markdown、DOCX 或粘贴文字，不支持 PDF。
- 字幕列表、视频预览、波形、切割合并、颜色、保存与自动保存。
- 审阅筛选、数字转换、英文大小写和自定义快捷键。
- SRT 与本地 FCPXML 转换，支持横屏、竖屏和常见帧率。
- 兼容旧 `.mosp` / `.json` 工程，沿用整数毫秒时间。

## 源码运行

```bash
uv sync
uv run --no-sync python maw_gui.py          # Launcher
uv run --no-sync python server-editor/serve.py --blank   # 编辑器
```

云端 ASR 配置 `DASHSCOPE_API_KEY`；DeepSeek 校对配置 `MAW_POSTPROCESS_DEEPSEEK_API_KEY`。本地 ASR 不需要百炼 Key。不要提交 `.env`。

开发与打包见 [开发文档](docs/DEVELOPMENT.md) 和 [macOS 打包说明](docs/MACOS_PACKAGING.md)。本机编辑服务仅监听 `127.0.0.1`。

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
