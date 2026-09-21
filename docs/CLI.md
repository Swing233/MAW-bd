# CLI（精简）

```bash
# Qwen 转写
uv run --no-sync python generate_subtitle_qwen_api.py VIDEO -o out.srt --json
# 默认模型 qwen-audio-3.0-asr-flash-filetrans；副模型：
# --model qwen3-asr-flash-filetrans

# Launcher
uv run --no-sync python maw_gui.py

# 编辑器
uv run --no-sync python server-editor/serve.py --blank

# MAW 内部（冻结包）
MAW-bd.app/Contents/MacOS/MAW --serve --blank
MAW-bd.app/Contents/MacOS/MAW --transcribe -- ...   # 转发给 Qwen 生成器
```

Key：`.env` 中 `DASHSCOPE_API_KEY`。服务仅 `127.0.0.1`。
