# MAWE 使用（精简）

**保留**：预览、波形、Seek、拆分/合并、颜色、保存/自动保存、SRT、proofread 过滤。

**已移除界面能力**：贴纸、Lottie/OGraf、ASS 样式库与 ASS 导出、OTIO/OTIOZ、多重字幕/叠加轨。

- 双击改字；改字后 `proofread.status = manual`
- 工具栏「校对」过滤：全部 / 已校验 / 现场发挥 / 待确认 / 人工修改 / 含校对建议
- 当前字幕面板显示：文稿 / 原始 ASR / 副 ASR / 校对建议 / 原因
- 状态色：绿 verified / 黄 improvised / 红 uncertain；manual 无自动色
- 保存 `Ctrl/Cmd+S` → `.mosp`
- 导出 SRT：仅最终文本与时间
- FCPXML：用 `web/srt2fcpxml-page/` 转换 SRT
