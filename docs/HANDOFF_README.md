# MAW-bd 交接包

先读 **CODEX_HANDOFF.md**。

| 文件 | 说明 |
|---|---|
| `CODEX_HANDOFF.md` | 架构、API、运行、打包、测试、已知问题 |
| `maw-bd-source.zip` | 源码工作树（不含 .venv/dist/build/.git） |
| `MAW-bd.app.zip` | 已构建 macOS 应用（含 ffmpeg） |
| `GUI_GUIDE.md` 等 | 使用与打包说明 |

## 快速

```bash
unzip maw-bd-source.zip -d maw-bd
cd maw-bd && uv sync
uv run --no-sync python maw_gui.py

# 或直接
unzip MAW-bd.app.zip && open MAW-bd.app
```

本地 ASR 运行时（本机）：
`~/Library/Application Support/MAW/local-runtime/bin/python`
