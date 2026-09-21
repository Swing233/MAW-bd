# 工作流（精简）

1. 配置 `DASHSCOPE_API_KEY`（`.env` 或 Launcher 设置）
2. Launcher 选择媒体 → Qwen ASR（默认 audio-3.0；可开双模型）
3. （可选）文稿对齐：TXT/MD/DOCX/粘贴 → `maw/bdversion` 顺序匹配
4. （可选）DeepSeek 保守校对 → 写入 `proofread.corrected`，默认不改 `text`
5. MAWE：查看状态色 / 过滤 / 人工改字（→ `manual`）→ 保存 `.mosp`
6. 导出 SRT（仅最终字幕）
7. FCPXML：打开 `web/srt2fcpxml-page/index.html`，导入 SRT 后生成 `.fcpxml`

原则：语音优先；旧工程无 `proofread` 字段仍可打开。
