# MAW-bd Codex 交接包（2026-09-18 更新）

工作树：仓库根目录
分支：`feature/bdversion-focused`
应用：`dist/MAW-bd.app`

## 产品流程

```text
1 导入媒体
2 ASR — 仅识别（默认本地 Qwen3-ASR 1.7B），不自动断句
3 修订 — DeepSeek / 自定义提示词 / 可粘贴文稿参考
   最终只输出 1 个 .mosp + 1 个 .srt（无 *.断句* 文件）
4 打开字幕编辑器（MAW/MAWE）
   — 导入工程打开 / SRT / 转为 .fcpxml
```

## 断句规则（修订后或需要时）

- **只在正常句末标点**（。！？；）断开
- **不确定就不断**：无句末标点的长句保持完整，不硬切
- ASR 步骤 **不** 自动断句
- 修订完成时按句读写回 **同一套** 工程/SRT

## 界面

- 白色四步 GUI；日志在 **右侧**，可 **一键收起**
- 分步进度条：ASR / 修订 / 编辑器
- 文稿：对话框粘贴（非选文件）
- 「生成提示词并复制」：给 GPT 的 SRT 修订提示词
- 配置：仅 DeepSeek Key（ASR 用本地模型）
- 本地运行时路径：`~/Library/Application Support/MAW/local-runtime/bin/python`

## 关键路径

| 路径 | 职责 |
|---|---|
| `maw/focus_launcher.py` | GUI API |
| `maw/bdversion/segment.py` + `maw/local_segment.py` | 保守断句 |
| `maw/bdversion/revise.py` | 修订 / 就地断句（suffix 空） |
| `maw/local_asr.py` / `generate_subtitle_local.py` | 本地 ASR 1.7B |
| `server-editor/serve.py` | MAWE，仅 127.0.0.1 |
| `web/launcher/` | 四步 GUI + 侧栏日志 |
| `web/editor*` + `web/srt2fcpxml-page/` | 编辑器 + FCPXML |

## 运行 / 打包

```bash
cd <worktree>
uv sync
uv run --no-sync python maw_gui.py
# 或
open dist/MAW-bd.app

# 测试
uv run --no-sync python -m unittest discover -s tests -p "test_*.py"

# 打包
uv run --with pyinstaller pyinstaller MAW.spec --noconfirm --clean
cp -a /Applications/MAW.app/Contents/MacOS/ffmpeg/* dist/MAW-bd.app/Contents/MacOS/ffmpeg/
codesign --force --deep --sign - dist/MAW-bd.app
```

**打包注意**：`local-runtime/maw` 的 PyInstaller dest 必须是目录；`local_asr` 使用 `maw/local_segment.py`，勿改回依赖 `maw.bdversion`。

## 输出文件

- ASR：媒体旁 `*.mosp` + `*.srt`
- 修订：同目录 `*.修订.mosp` + `*.修订.srt`；只校对每条内部文字，保持 ASR 的条数、分段边界、顺序与时间码。
- 读工程：`encoding=utf-8` + 手动去 BOM（不用 `utf-8-sig`）

## 已知

1. 1.7B 首次需下载模型（缓存目前可能只有 0.6B）
2. 波形：有关联媒体时打开编辑器会尝试生成；无媒体则跳过，不影响改字幕
3. 服务禁止 `0.0.0.0`；不要手改 `blank-editor.html`
4. Keychain 未做；DeepSeek Key 在 `.env`

## Codex 建议下一步

- 端到端：ASR → 修订 → 编辑器 → 导出 SRT / fcpxml
- 检查 Final Cut 实机导入 fcpxml（分辨率含 2880×2160）
- 优化断句仅在用户反馈后改 `maw/bdversion/segment.py`（与 local_segment 保持同步）
