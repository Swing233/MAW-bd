# macOS 打包说明（MAW bdversion）

## 目标形态

- 交付物：`MAW-bd.app`（PyInstaller onedir + `BUNDLE`）
- 运行时：Python + pywebview Launcher + `server-editor`（本机）+ `web/` 前端
- 识别：仅阿里云百炼 **双 Qwen**
  - 主：`qwen-audio-3.0-asr-flash-filetrans`
  - 副（可选交叉验证）：`qwen3-asr-flash-filetrans`
- 校对域：`maw/bdversion`（文稿对齐 / DeepSeek 保守校对 / dual ASR / proofread）
- FCPXML：打开本地网页 `web/srt2fcpxml-page/index.html`（MIT：GanymedeNil/srt2fcpxml），**不**走 Python 导出为主路径

## 构建步骤（macOS）

```bash
cd /path/to/moys-asr-workflow-bdversion
uv sync

# 1) PyInstaller（使用仓库 MAW.spec）
uv run --no-sync pyinstaller MAW.spec --noconfirm

# 2) 内置 FFmpeg（完整版）
# CI/发布脚本下载 arm64 静态 ffmpeg/ffprobe，安装到：
#   dist/MAW-bd.app/Contents/MacOS/ffmpeg/bin/ffmpeg
#   dist/MAW-bd.app/Contents/MacOS/ffmpeg/bin/ffprobe
# 解析顺序见 maw/ffmpeg.py：显式配置 → bundled → Homebrew → PATH

# 3) ad-hoc 签名（本地分发）
codesign --force --deep --sign - dist/MAW-bd.app
```

`MAW-lite`：同一 spec 产物但不捆绑 ffmpeg；用户需自备 `ffmpeg`/`ffprobe`。

## 打包内容（focused）

| 纳入 | 路径 |
|---|---|
| Launcher / GUI | `maw_gui.py` + `maw/gui_*.py` |
| 编辑器服务器 | `server-editor/serve.py` |
| 前端真源 | `web/`（含 `editor-proofread.js`、`srt2fcpxml-page/`、launcher） |
| Qwen 转写 | `generate_subtitle_qwen_api.py` + `local-runtime/maw/*` |
| 校对域 | `maw/bdversion/*`（hiddenimports） |
| 许可 | `LICENSE`、`THIRD_PARTY_NOTICES.md` |

| 明确排除 | 原因 |
|---|---|
| Soniox / 腾讯 / 豆包 / 必剪 / OpenAI ASR / 本地模型 | 产品已收窄为双 Qwen |
| `server-align`、旧文稿匹配、OCR runtime | 与新流程无关 |
| `exporters.fcpxml` | 改用本地转换网页 |

## 安全约束

1. **编辑器服务只监听 `127.0.0.1`**（`server-editor/serve.py`），禁止 `0.0.0.0`。
2. API Key：开发期读 `.env`（应用旁或 `~/Library/Application Support/MAW/.env`）。
3. **正式版 Key 迁移 macOS Keychain** — 尚未实现；发布前需：
   - 读取：Keychain → 回退 `.env`
   - 写入：仅 GUI「保存 Key」写入 Keychain，不写回工程/日志
   - 日志与前端响应继续脱敏
4. 工程真源 `.mosp`；波形为可重建缓存；SRT/FCPXML 不含 proofread 元数据。

## 用户数据路径（macOS）

| 用途 | 位置 |
|---|---|
| `.env` | App 同级优先，否则 `~/Library/Application Support/MAW/.env` |
| Server 设置 | `~/Library/Application Support/MAW/server-editor-settings.json` |
| 日志 | `~/Library/Application Support/MAW/logs` |

见 `maw/app_paths.py`。

## 发布前检查清单

- [ ] `uv run --no-sync python -m unittest discover -s tests -p 'test_*.py'`
- [ ] 重点：`tests/test_packaging_focus.py`、`tests/test_bdversion_*.py`、`tests/test_editor_proofread_ui.py`
- [ ] `MAW.spec` 无已删除模块的 active hiddenimports
- [ ] `web/srt2fcpxml-page/index.html` 存在且随 `web/` datas 打包
- [ ] App 内 `ffmpeg`/`ffprobe` 可解析（完整版）
- [ ] `serve.py` 仍为 `127.0.0.1`
- [ ] `THIRD_PARTY_NOTICES.md` 含 srt2fcpxml MIT 条目
- [ ] `.env` / 媒体 / 个人路径未进入仓库与安装包
- [ ] CHANGELOG 记录精简范围（仅双 Qwen、删旧匹配/OCR/多 ASR）

## 与 `/Applications/MAW.app`（官方完整版）对照

| 封装槽位 | 官方 App | 精简版 `dist/MAW-bd.app` |
|---|---|---|
| `Contents/MacOS/MAW` | 有 | 有 |
| `MacOS/ffmpeg/bin/{ffmpeg,ffprobe}` | 有（系统 framework 链接，~50MB/个） | **已对齐**：同结构 + 许可证文件 |
| `Resources/web/launcher/` | 有 | 有 |
| `Resources/server-editor/` | 有 | 有 |
| `Resources/local-runtime/generate_subtitle_qwen_api.py` | 有 | 有 |
| `Resources/base_library.zip` | 有 | 有 |
| `Resources/ocr-runtime` / `moss-runtime` / `server-align` | 有 | **无**（产品收窄，预期） |
| `Resources/web/srt2fcpxml-page/` | 无 | **有**（本地 SRT→FCPXML 页） |
| `Info.plist` BundleId / Executable / Icon | `com.moy.maw.bdversion` / `MAW` / `maw.icns` | Bundle 名/Id 已区分官方 MAW.app |
| `CFBundleShortVersionString` | `0.0.0` | `1.6.0-beta.4`（跟 `pyproject.toml`） |
| Python 运行时 | `Frameworks/Python.framework` | `Frameworks/libpython3.11.dylib`（PyInstaller 6） |

结论：封装格式与官方 **同为 PyInstaller macOS BUNDLE**；差异主要来自精简范围与 PyInstaller 版本，而非另一套打包体系。


`desktop/`（Tauri MOSE）**不是**本精简版的发布载体。macOS 正式路径仍是 **PyInstaller `MAW-bd.app`**（精简版）。

## 与 MOSE 的关系

`desktop/`（Tauri MOSE）**不是**本精简版的发布载体。macOS 正式路径仍是 **PyInstaller `MAW-bd.app`**（精简版）。

## 尚未完成（Roadmap）

1. Keychain 读写与迁移工具
2. CI：`macos-14` 构建 + ffmpeg 下载 + `codesign` + zip
3. Launcher 打开 `srt2fcpxml-page` 的菜单入口
4. 将 `dual_transcribe` / 对齐 / DeepSeek 接到 GUI 一键流水线（默认关闭）
