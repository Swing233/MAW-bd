# DeepSeek 保守校对协议（maw/bdversion）

## 原则

1. **语音是真源**，文稿只是纠错参考。
2. 不允许把现场发挥改成文稿。
3. 不允许润色 / 改写句式。
4. 不确定时保持 ASR。
5. 仅高概率识别错误可改。
6. 不允许补入 ASR 中不存在的文稿内容。
7. **不得**输出或修改时间；不得改变字幕顺序。
8. **默认**不把 `corrected_text` 写回 `segments[*].text`（人工确认后应用）。

## 路由

| 条件 | status | 是否调用 DeepSeek |
|---|---|---|
| 规范化后 ASR=文稿 | `verified` | 否 |
| 明显不同（现场发挥等） | `improvised` | 否 |
| 高分但有差异 / 难以判断 | `uncertain`（score≥0.72） | 是 |
| 低分 uncertain | `uncertain` | 否（保持 ASR） |
| 人工改过 | `manual` | 否 |

默认：`base_url=https://api.deepseek.com`，`model=deepseek-flash`，`temperature=0.1`。

## 请求

用户消息 JSON 数组（仅 LLM 路由段）：

```json
[{
  "cue_id": "main-001",
  "primary_asr": "今天介绍自工作流",
  "secondary_asr": null,
  "matched_script": "今天介绍字幕工作流",
  "match_score": 0.9
}]
```

## 响应

```json
{
  "results": [{
    "id": "main-001",
    "corrected_text": "今天介绍字幕工作流",
    "status": "uncertain",
    "changed": true,
    "reason": "同音错字：自→字"
  }]
}
```

本地强制：

- 忽略模型返回的时间字段
- 不改 segment 顺序 / start / end / items 时间
- `corrected` 写入 `proofread.corrected`
- `changed=false` 且高匹配分时，可将 status 提升为 `verified`
- 缺失 id 时保持 ASR

实现：`maw/bdversion/deepseek.py`
