# AGENTS.md（MAW-bd 精简分支）

## 产品边界

仅实现：

```text
视频 → 双 Qwen ASR → 文稿对齐 → DeepSeek 保守校对 → MAWE → SRT → 本地 FCPXML 网页
```

**语音是真源**；文稿不自动改写字幕。`.mosp` 毫秒契约不变。

## 不要再引入

- 其它 ASR 供应商、本地模型下载器
- 旧「文稿改写为字幕」匹配
- OCR 去重、翻译重分句、口播对齐 Server
- 在线 FCPXML 服务、自研 Python FCPXML 主路径
- 非 `127.0.0.1` 的本地服务

## 必读

```text
README.md
docs/BDVERSION_FOCUS.md
docs/PROOFREAD_PROTOCOL.md
docs/MACOS_PACKAGING.md
JSON_SCHEMA.md
maw/bdversion/
web/editor-proofread.js
web/srt2fcpxml-page/
```

`web/` 是前端真源。**不要手改** `blank-editor.html`；发布前再 `uv run --no-sync python edit.py --blank`。

## 开发与验证

```bash
uv sync
uv run --no-sync python -m unittest discover -s tests -p "test_*.py"
node --check web/editor.js
node --check web/editor-proofread.js
# 编辑器改动手动起：
uv run --no-sync python server-editor/serve.py --blank
```

## 安全

- 本地服务只绑定 `127.0.0.1`
- `.env` 不提交；日志不打印 Key
- segments 时间整数毫秒；`segments` 是字幕真源，波形可重建

## Schema

改工程字段必须同步：`JSON_SCHEMA.md`、相关测试、`CHANGELOG.md`。旧 `.mosp` 必须可打开。

## 提交

不附加 AI 署名。不删除用户 WIP；共享工作区只改本任务文件。
