# 转写后处理（精简）

Launcher 自动后处理 **默认关闭**。

本产品流水线由 `maw/bdversion` 承担（对齐 / DeepSeek / dual ASR），
不依赖旧「文稿改写匹配 / OCR / 翻译」管线。

固定替换（`maw/postprocess_pipeline.py` 仅保留 replace 步骤）可在需要时手动使用。
DeepSeek 协议见 `PROOFREAD_PROTOCOL.md`。
