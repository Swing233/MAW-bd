# MAW-bd 变更记录

## 1.1.1

- 修复编辑器端口探测误判已绑定但未监听的端口；编辑器异常退出时显示脱敏后的子进程错误详情

## 1.1.0

- 增加应用内更新检查：启动时静默查询官方 GitHub Release，发现新版后显示版本、更新说明和下载入口
- 更新链接固定到 `Swing233/MAW-bd`，并校验版本标签、下载域名和响应大小；检查失败不影响主流程

## 1.0.1

- 修正“MP4 + SRT 直接编辑”按钮无响应：先通过稳定的媒体选择接口取得路径，并显示创建进度与调用错误

## 1.0.0（macOS 首个正式版）

- 产品收窄为：双 Qwen ASR → 文稿对齐 → DeepSeek 保守校对 → MAWE → SRT / 本地 FCPXML 网页
- 新增 `maw/bdversion`（manuscript / alignment / status / deepseek / dual_asr / project_meta）
- 编辑器 proofread 状态过滤与人工改字 `manual`
- macOS 包名 `MAW-bd.app`；服务仅 `127.0.0.1`
- **移除** 其它 ASR、旧文稿改写匹配、OCR、翻译/口播对齐、Tauri MOSE、官网站等
- FCPXML 主路径改为本地网页 `web/srt2fcpxml-page/`（MIT srt2fcpxml）
- LLM 修订阶段将流式输出实时显示在右侧日志，并让 GPT 提示词优先生成可下载的 UTF-8 `.srt` 文件
- 云端、本地和手动重新断句统一复用 Qwen 自然断句核心：目标约 14 字、普通上限 20 字、25 字仅作绝对兜底，强停顿默认 750ms
- ASR 完成后不再自动二次重切；文稿匹配与 LLM 校对保持字幕条数、顺序、毫秒时间和 items 不变
- 只有句级时间时按语义边界拆分并写入 `timing_estimated: true`，不生成伪字级时间戳；新字幕与 SRT 均保持单行
- 波形空白处改为直接拖拽框选，Shift+拖拽追加选择；字幕块本身仍按原逻辑拖动
- 双击波形上的主字幕、副字幕或叠加字幕块，可弹出字幕文字修改框
- 修正编辑器 FCPXML 的非法全局 `text-style-def` 资源，恢复 Final Cut Pro DTD 兼容
- 修正从空白编辑器直接导入 `.mosp` 时未启用后端波形生成的问题；大媒体会读取或生成本地波形缓存，不再交给浏览器整段解码
- 修正 macOS 包内本地 ASR 误加载 GUI LLM 模块导致的 `ModuleNotFoundError`
- 修正 Launcher 启动时误报“请通过 MAW-bd 应用启动本界面”，以及选择一次媒体重复记录三条日志的问题
- 修正首版 GitHub Actions 中 Ruff 导入顺序、重复定义和未使用导入错误

历史完整变更见上游仓库 CHANGELOG（本分支不再维护多供应商版本史）。
