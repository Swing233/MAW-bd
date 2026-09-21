# 开发说明（MAW-bd）

| 路径 | 职责 |
|---|---|
| `generate_subtitle_qwen_api.py` | Qwen ASR |
| `maw/bdversion/` | 文稿对齐 / DeepSeek / dual / proofread 元数据 |
| `server-editor/serve.py` | 127.0.0.1 MAWE |
| `web/` | 编辑器与 Launcher 真源 |
| `web/srt2fcpxml-page/` | SRT→FCPXML 本地页 |
| `maw/project.py` | `.mosp` 契约 |

检查：

```bash
uv run --no-sync python -m unittest discover -s tests -p "test_*.py"
"$MIMO_NODE" --check web/editor.js
"$MIMO_NODE" --check web/editor-proofread.js
```

不要手改 `blank-editor.html`。
