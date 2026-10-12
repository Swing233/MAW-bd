from pathlib import Path
import json
import base64
import html
import re
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    Flowable,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/tutorial"
IMAGES = OUT / "images"
meta = json.loads((IMAGES / "figures.json").read_text())
sections = []


def chapter(title, blocks, figure=None):
    sections.append(dict(title=title, blocks=blocks, figure=figure))


def p(s):
    return ("p", s)


def steps(*s):
    return ("ol", list(s))


def tip(s):
    return ("tip", s)


def table(rows):
    return ("table", rows)


chapter(
    "01｜先选对入口",
    [
        p(
            "这份教程对应 MAW-bd 1.8.0，面向 macOS Apple Silicon。你会完成：载入视频 → 识别语音 → 参考文稿校对 → 编辑与审阅 → 保存工程 → 导出 SRT / FCPXML。"
        ),
        table(
            [
                ["你已有的材料", "从哪里开始"],
                ["只有视频或音频", "选择视频 / 音频 → 开始 ASR"],
                ["视频和已有 SRT", "MP4 + SRT 直接编辑"],
                ["以前保存的 .mosp / .json", "导入工程打开"],
                ["只想先进入编辑器", "打开字幕编辑器"],
            ]
        ),
        p(
            "图中①适合已有字幕的人；②③④是没有字幕时的识别路线。已有 SRT 不必再识别一次。"
        ),
        tip(
            "截图取自本地 1.8.0 应用界面，编辑器使用独立演示工程；启动器展示未配置状态。数字序号是截图标注，不是软件按钮的一部分。"
        ),
    ],
    "01-launcher",
)
chapter(
    "02｜下载、安装与准备文件",
    [
        steps(
            "打开本项目的发布页，下载 MAW-bd-1.8.0-macOS-arm64.zip 完整包。首次安装不要下载名称带 delta 的增量包，也不要把 Source code 当作安装包。",
            "解压 ZIP，将 MAW-bd.app 拖入“应用程序”，从这里打开。完整包已带 FFmpeg / FFprobe，不需要先装原版 MAW。",
            "如果 macOS 拦截首次打开：尝试打开一次，再到“系统设置 → 隐私与安全性”查看“仍要打开”，按系统提示操作。应用尚未经过 Apple 公证。",
            "创建一个项目文件夹，例如“字幕项目 / 演示视频”。把视频、文稿和工程放在一起，之后尽量不要移动视频。",
        ),
        p("下载地址：https://github.com/Swing233/MAW-bd/releases/tag/v1.8.0"),
        p(
            "首次本地识别仍需要联网下载运行环境和模型。之后复用缓存；准备时保留足够磁盘空间。只有使用本地识别不需要百炼 Key，也不需要 DeepSeek Key。"
        ),
        table(
            [
                ["建议保存的文件", "用途"],
                ["演示.mp4", "原始视频，供试听和对齐"],
                ["演示.mosp", "编辑工程，后续继续修改"],
                ["演示.srt", "交付字幕"],
                ["演示.mp4.mopeaks", "波形缓存，可重建"],
                ["参考文稿.txt / .md / .docx", "可选的纠错参考"],
            ]
        ),
        tip(
            "工程不是视频的副本。只备份 SRT 会丢失校对信息、颜色和工程设置；请同时保留原视频与 .mosp。"
        ),
    ],
)
chapter(
    "03｜第一条路线：本地识别生成字幕",
    [
        steps(
            "点击“选择视频 / 音频”，载入需要识别的文件。确认选对版本，并试听人声是否清晰。",
            "识别方式选择“本地模型（默认）”；第一次先保持 Qwen3-ASR 1.7B。其他引擎按需要再尝试。",
            "点击“下载 / 检查本地模型”。软件会检查缓存并准备缺少的环境和模型。这个按钮准备的是识别资源，不会替你生成字幕。",
            "准备完成后点击“开始 ASR”。识别可能先提取音频、再加载模型，长音频显示分块进度。",
            "等任务状态显示完成，查看“输出 SRT”和“输出工程”路径，再打开生成的工程。要取消时点击“停止”。",
        ),
        p(
            "无法准确测量的模型下载或加载阶段，界面可能只显示“进行中”。不要把暂时没有百分比当作失败；先看最后一条关键进度或报错。"
        ),
        p(
            "云端识别是另一条可选路线：选择“云端 Qwen API”，填写阿里云百炼 Key，保存配置后选择云端模型再开始。百炼 Key 用于语音识别，DeepSeek Key 用于文字校对，两者不能互换。"
        ),
        tip(
            "识别出来的文字是初稿。先听一小段确认语言和内容正常；若整段乱码，保留工程与最后一条完整错误再排查，避免继续批量校对异常文本。"
        ),
    ],
)
chapter(
    "04｜已有 SRT：跳过识别直接编辑",
    [
        steps(
            "将“演示.mp4”和“演示.srt”放在同一目录，文件主名保持一致。",
            "在启动器点击“MP4 + SRT 直接编辑”，选择视频。后端准备波形后进入编辑器，同名 SRT 会在首次创建工程时自动载入。",
            "如果没有同名 SRT，在编辑器打开文件菜单，选择加载字幕的入口，再导入已有 SRT。",
            "如果旁边已有 .maw-edit.mosp，软件会继续打开原工程，避免覆盖你的编辑。要换一份 SRT，先另存现有工程。",
        ),
        p(
            "只有 SRT 也能改文字，但校准字幕时间需要视频或音频。视频被移动后，重新选择媒体即可；.mopeaks 不包含视频，不能替代媒体文件。"
        ),
        tip(
            "第一次直接编辑完成后先保存工程。下次从 .mosp 继续，不必再走“MP4 + SRT”或重新识别。"
        ),
    ],
)
chapter(
    "05｜获取自己的 DeepSeek API Key",
    [
        p(
            "API Key 相当于允许 MAW-bd 调用你 DeepSeek 账户的凭证。进入图中①“API 开放平台”，而不是只进入“和 DeepSeek 对话”。"
        ),
        steps(
            "打开 https://www.deepseek.com/ ，点击“API 开放平台”。也可直接访问 https://platform.deepseek.com/ 。",
            "未登录时，按官网提供的手机号验证码、密码或扫码方式登录。注册、验证码和协议确认由你在官网自行完成。",
            "登录后进入“API keys / API 密钥”管理页。直达地址：https://platform.deepseek.com/api_keys 。如果又回到登录页，先完成登录，再重新打开此地址。",
            "点击页面上的创建密钥按钮，给密钥起一个便于辨认的名称，例如“MAW-bd 字幕校对”。按钮具体文案以当前平台为准。",
            "完成创建后复制密钥，按平台提示妥善保存。不要把完整密钥放进字幕、教程截图、群聊或 GitHub；看不到原密钥时，回到平台管理或创建新密钥。",
            "查看平台的余额与费用信息。API 调用按官方规则计费；是否需要充值、充值多少以及价格，以账户页面和官方价格页为准。",
            "回到 MAW-bd，在“配置 → DeepSeek API Key”粘贴自己的密钥，点击“保存配置”。已配置状态只代表软件保存了凭证，不代表接口已经调用成功。",
        ),
        p(
            "DeepSeek 官方使用 OpenAI 兼容接口。MAW-bd 默认地址为 https://api.deepseek.com，默认模型为 deepseek-flash，通常保持默认即可。官方说明：https://api-docs.deepseek.com/zh-cn/ 。"
        ),
        table(
            [
                ["常见误区", "正确做法"],
                [
                    "把 DeepSeek 聊天网页地址当接口地址",
                    "保持默认 API 地址 api.deepseek.com",
                ],
                ["用百炼 Key 填 DeepSeek 输入框", "使用 DeepSeek 开放平台生成的 Key"],
                [
                    "免费聊天可用，所以 API 一定可用",
                    "到开放平台检查 Key、余额及 API 服务状态",
                ],
                ["截图能看到完整密钥", "发布或反馈前遮住密钥；本教程不展示真实 Key"],
            ]
        ),
        tip(
            "本节图片只截取官网公开入口。账户内创建密钥的步骤用文字说明，不展示私人账户、余额或真实密钥。"
        ),
    ],
    "11-deepseek-entry",
)
chapter(
    "06｜把 Key 填进软件，再进行文稿校对",
    [
        steps(
            "向下找到启动器的“配置”，将 DeepSeek Key 填入图中①，点击②“保存配置”。首次校对先用一小段字幕确认服务可用。",
            "在“修订字幕”选择 DeepSeek 保守校对，③保持 deepseek-flash。",
            "点击④“添加文稿”，选择 TXT、Markdown 或 DOCX。软件也可使用支持入口中的粘贴文字；不支持 PDF。没有文稿时可按现有字幕进行保守校对。",
            "确认使用的工程是刚刚识别出来的版本，点击⑤“开始修订”。",
            "完成后查看“修订结果”路径，打开对应修订工程。1.8.0 默认直接应用校对文字，同时保留原始 ASR 与修改记录。",
        ),
        p(
            "实际语音是真源。文稿只是纠错参考：同音错字、人名、地名和术语可以辅助判断，现场发挥、不同措辞和口语内容不应被原稿覆盖。"
        ),
        p(
            "校对不负责重新断句，不应改变字幕条数、顺序、起止点和字词时间。真正需要拆分长字幕时，进入编辑器处理，再试听核对。"
        ),
        p(
            "常见失败：Key 无效时重新检查复制内容；余额不足到官方平台处理；连接超时先检查网络，稍后重试。不要在报错截图中暴露 Key。"
        ),
        tip(
            "使用 DeepSeek 校对会将相关字幕文字和参考文稿发送给 DeepSeek。涉及未公开或保密内容时，先确认你允许这些内容交给外部服务。"
        ),
    ],
    "02-deepseek-config",
)
chapter(
    "07｜认识编辑器：先听，再改，再保存",
    [
        p(
            "默认工作区为“字幕列表编辑”。旧工程可能恢复以前保存的布局；顶部“工作区”可以切换。左侧查看视频、当前字幕和波形，右侧集中浏览字幕列表。"
        ),
        steps(
            "点击一条字幕，查看当前文字和对应时间。播放前后几秒，先判断是识别错误、文字问题还是时间问题。",
            "文字错了就改字；时间不对再调整边界。不要为了改一个错字重新识别整段视频。",
            "用①保存工程，养成完成一组修改后按 Cmd+S 的习惯。②导出字幕在交付时使用。",
        ),
        table(
            [
                ["区域", "主要用途"],
                ["③当前字幕编辑区", "输入文字、查看长度和阅读速度"],
                ["④波形与字幕块", "移动、修剪时间、试听、定位"],
                ["⑤字幕列表", "选择、搜索、审阅和批量处理"],
            ]
        ),
        p(
            "本教程截图的视频画面是独立演示素材，字幕末尾的数字便于区分示例条目，不代表正式字幕必须这样编号。"
        ),
        tip(
            "编辑器顶部可能显示上游 MAWE 的内部版本标记。确认应用正式版本时，以启动器版本和 Release 版本为准。"
        ),
    ],
    "03-editor",
)
chapter(
    "08｜修改、拆分与合并字幕",
    [
        steps(
            "双击波形上的字幕块，打开图中的小编辑窗。①修改文字，按 Enter 或点击③保存；点击取消放弃本次小窗修改。",
            "要按文字精确拆分：把输入光标放在两个字符之间，点击②“在光标处切割”。不要在最开头或最末尾切割。",
            "直接切割：鼠标停在字幕文字或波形字幕块上时，先看显示的分割位置，再按默认 B。鼠标不在字幕块上时，按当前音频播放位置切割。",
            "合并：选中连续字幕，按默认 C。文字光标位于字幕开头、没有选中文字时，按 macOS Delete（Backspace）可与上一条合并；第一条不执行。",
            "修改后试听前后几秒，确认两边文字完整、没有重复遗漏，时间也与说话位置一致。",
        ),
        p(
            "短小而完整的句子通常保留一条。过长内容优先在完整分句处拆开，例如“先倒入清水｜然后观察液面”，不要切开人名、英文单词、版本号或数字与量词。"
        ),
        p(
            "有真实字词时间码时，软件优先利用这些时间。只有句级时间时，文字断点与时间对应只能估计，拆分后必须试听。"
        ),
        tip(
            "小编辑窗 Enter 默认保存；主字幕编辑区可能启用 Enter 切分。要统一为保存，可在字幕面板“编辑设置 → 操作”开启“关闭回车切分”。"
        ),
    ],
    "07-edit",
)
chapter(
    "09｜逐帧调整字幕时间",
    [
        p(
            "1.8.0 导入视频时读取帧率，并在可读取时显示总帧数。编辑默认采用源视频的帧基准，拖动、起止点与键盘微调以帧为单位；工程仍保存兼容的整数毫秒。"
        ),
        table(
            [
                ["操作", "用途"],
                ["拖动字幕块中间", "整体移动这条字幕"],
                ["拖动字幕块边缘", "只调整起点或终点"],
                [
                    "选中后使用方向键等已配置微调键",
                    "逐帧调整；实际按键以快捷键设置为准",
                ],
                ["在起止点输入框输入帧时间", "按指定边界精确定位"],
            ]
        ),
        p(
            "时间码“00:00:04:15”的最后一组在帧模式下表示帧，而不是毫秒。25fps 时一帧约 40ms；29.97fps 时一帧约 33.37ms，不要把每一帧固定看成 33ms。"
        ),
        p(
            "只有音频或无法读取帧率时使用毫秒。未知帧率可在工程设置中指定；不要把默认值当成媒体的真实帧率。可变帧率视频使用读取到的平均帧率作为编辑基准，交付前应在目标剪辑工程试听和核对。"
        ),
        tip(
            "先调整起点，再调整终点，最后播放这一句。人工编辑字幕时间和 LLM 校对是两件事：校对保持时间，时间调整由你明确操作。"
        ),
    ],
)
chapter(
    "10｜用“审阅”集中检查问题",
    [
        steps(
            "点击列表工具栏的“审阅”，图中①列出校验状态与内容条件。",
            "选择“LLM 修改”集中检查自动改过的字幕，或者按需要选择数字、英文、标点和空格。",
            "可多选组合：校对状态任选其一，内容条件同时满足。例如“含阿拉伯数字 + 含英文”只保留两者兼有的字幕。",
            "修改当前筛选出来的字幕后，它们会继续留在列表里，方便你检查效果。重新选择或切换条件后才按当前内容重新筛选。",
            "点击“全部”清除状态与内容条件。超长阈值、隐藏禁用项属于独立条件，需要时另外关闭。",
        ),
        p(
            "不要把红色“待确认”直接理解为一定错误：它表示需要人工判断。黄色“现场发挥”也不应强制改成原文稿。"
        ),
        tip(
            "批量处理前，先看“已选”数量和处理范围。筛选负责决定你看到哪些字幕，多选负责决定要操作哪些字幕，两者不是一回事。"
        ),
    ],
    "04-review",
)
chapter(
    "11｜查看 LLM 改动，必要时恢复原文",
    [
        steps(
            "将鼠标悬停在字幕前面的校验徽标，例如绿色 V；校对详情在悬浮窗显示，不必点击字幕文字触发。",
            "对照图中①的原始 ASR 与校对建议，查看高亮差异、参考文稿和修改原因。",
            "拿不准时试听视频。示例“曲水 → 驱水”需要结合实际语音和术语判断，不能只因为文稿不同就采用。",
            "1.8.0 默认已应用建议。要恢复这条字幕的原始文字，使用②“保留原文”；要重新应用，使用“采用建议”。必要时 Cmd+Z 撤销。",
        ),
        p(
            "人工编辑的字幕会标记为人工修改，并受保护。校验状态说明软件处理结果，不代表所有事实与专有名词均已确认。"
        ),
        tip(
            "如果实际说话与原稿不同，保留实际说话内容。校对不是润色，也不是让字幕变得像原稿。"
        ),
    ],
    "05-proofread",
)
chapter(
    "12｜批量处理数字和英文",
    [
        steps(
            "先选中字幕：单击一条，或在列表空白处拖动框选；按住 Shift 拖动追加。波形空白处同样可以框选，字幕块上的拖动则移动字幕。",
            "点击“文本处理”，检查②处理范围。有选中项只处理选中字幕；没有选中项时可处理全部。",
            "在①选择数字转换或英文大小写，展开预览比较修改前后，确认后再点③“应用处理”。",
            "也可右键选中的字幕，在数字转换或英文处理的侧向菜单选择命令。删除空格和删除标点也是独立命令，处理后可撤销。",
        ),
        table(
            [
                ["处理", "示例"],
                ["中文数字转阿拉伯数字", "两个玻璃杯 → 2个玻璃杯"],
                ["阿拉伯数字转中文数字", "有对应校对前原文时，优先恢复原有中文表达"],
                ["每个单词首字母大写", "hello world → Hello World"],
                ["全大写 / 全小写", "DeepSeek → DEEPSEEK / deepseek"],
            ]
        ),
        p(
            "右键菜单的“233→二三三”“二三三→233”用于说明转换方向，并不表示所有数字都必须逐位读。具体转换结果以预览为准。"
        ),
        tip(
            "删除空格也会删除英文单词之间的空格；删除标点可能影响语气和句意。先选择需要处理的字幕，再检查结果，避免对全部内容误操作。"
        ),
    ],
    "06-text",
)
chapter(
    "13｜字幕空隙与列表显示",
    [
        steps(
            "列表设置可以控制跟随播放、点击后自动滚动、序号、时间码、字数列和短空隙高亮。跟随播放仅影响浏览，不修改字幕。",
            "短空隙高亮默认开启，默认基准为 200ms。在帧模式下，输入框显示相应帧数；例如 25fps 约 5帧，29.97fps 约 6帧。",
            "高亮只提示间隔，不改时间。要贴合短间隔，点击独立的“消除字幕空隙”，进入下一页的小面板。",
        ),
        tip(
            "把列表显示设置与工程内容区分开：隐藏一列、改变跟随播放或高亮阈值，不等于删除字幕。"
        ),
    ],
    "09-settings",
)
chapter(
    "14｜消除字幕之间的小间隔",
    [
        steps(
            "点击“消除字幕空隙”，在①输入最大间隔。帧模式填整数帧，毫秒模式填整数毫秒。",
            "在②选择“选中的相邻字幕”或“全部主字幕”。仅选中一条不足以形成一对相邻字幕；执行前确认范围。",
            "查看预览里的条目与总数，确认要贴合这些间隔，再点击③“应用”。",
            "执行后试听。如效果不合适，用 Cmd+Z 撤销整次操作。",
        ),
        p(
            "这个功能延长前一条字幕的结束时间到下一条的起点；不删除音频、不缩短视频、不合并字幕文字，也不改变字幕数量。它不是“删除静音”的功能。"
        ),
        tip(
            "不要消除所有自然停顿。只处理你希望字幕持续显示的短间隔，避免让字幕长时间占据画面。"
        ),
    ],
    "10-gaps",
)
chapter(
    "15｜保存工程与导出 SRT",
    [
        steps(
            "先按 Cmd+S 保存 .mosp 工程。它保留字幕、时间、颜色、校对记录和工程设置。",
            "点击顶部“导出字幕 → 完整 SRT 字幕”，保存最终字幕文件。",
            "用剪辑软件或文本编辑器检查前几条与末尾几条，确认时间、内容和文件编码正常。",
            "把视频、工程、最终 SRT 一起备份，下一次修改从工程开始。",
        ),
        table(
            [
                ["格式", "保留什么"],
                [".mosp", "继续编辑所需的完整工程信息"],
                [".srt", "字幕序号、最终文字和时间"],
                [".fcpxml", "用于 Final Cut Pro 导入的字幕时间线"],
                [".mopeaks", "可重建的波形缓存"],
            ]
        ),
        p(
            "标准 SRT 不包含校对原因、颜色或筛选条件。导出字幕与保存工程用途不同，不能只导出 SRT 就丢弃工程。"
        ),
        tip(
            "建议文件命名：“演示_字幕工程.mosp”“演示_最终字幕.srt”。修改版本较多时加日期或版本号，避免覆盖已交付版本。"
        ),
    ],
)
chapter(
    "16｜导出 FCPXML 并导入 Final Cut Pro",
    [
        steps(
            "点击“导出字幕 → 转为 .fcpxml”。",
            "先看①“当前视频”的源分辨率与帧率，再根据目标 Final Cut Pro 工程选择②帧率和③分辨率。图中的演示视频是 1280×720、29.97fps，目标工程可以是 1920×1080。",
            "填写容易辨认的工程名，点击④“导出 .fcpxml”。",
            "在 Final Cut Pro 使用“文件 → 导入 → XML”选择该文件。导入后核对开头、中间和末尾的字幕位置，并检查项目帧率、分辨率与实际剪辑工程一致。",
        ),
        table(
            [
                ["分辨率", "宽高比", "典型用途"],
                ["1920 × 1080", "16:9", "横屏高清"],
                ["3840 × 2160", "16:9", "横屏 4K"],
                ["1080 × 1920", "9:16", "竖屏视频"],
                ["2880 × 2160", "4:3", "4:3 画面"],
            ]
        ),
        p(
            "可选帧率：23.98、24、25、29.97、30、50、59.94、60fps。帧率错了可能造成位置偏移；源参数看不到时，先在视频或目标剪辑工程确认，不要盲用默认值。"
        ),
        tip(
            "FCPXML 是交接时间线的一种方式，不会把原视频打包进去。导入失败时保留 Final Cut Pro 完整错误，重新用当前版本导出再核查。"
        ),
    ],
    "08-export",
)
chapter(
    "17｜快捷键、更新与常见问题",
    [
        table(
            [
                ["常用操作", "默认键或入口"],
                ["保存工程 / 撤销", "Cmd+S / Cmd+Z"],
                ["分割 / 合并", "B / C"],
                ["小编辑窗保存", "Enter"],
                ["取消编辑或关闭面板", "Esc"],
                ["文字开头与上一条合并", "Delete（Backspace）"],
                ["自定义快捷键", "全局设置 → 通用操作 → 编辑快捷键 → 自定义"],
            ]
        ),
        p(
            "自定义时先点按钮进入采集，再按单键或组合键；实际键位以软件当前设置为准，不要把教程默认值当成你的自定义值。"
        ),
        steps(
            "更新前保存工程。启动器点击“检查更新”，选择增量或全量方式。",
            "下载时查看已下载大小、总大小与速度，线路不稳定可切换镜像或直连。",
            "按提示安装，应用会退出、替换并重启。首次安装仍需完整包；增量包只能由更新器处理。",
        ),
        table(
            [
                ["现象", "先检查什么"],
                [
                    "GitHub 403 rate limit exceeded",
                    "更新接口限流；稍后重试或直接从发布页下载完整包，不必改 DeepSeek Key",
                ],
                ["导入工程没有波形", "视频是否还在原路径，重新绑定媒体并等待生成"],
                ["本地模型下载超时", "网络、剩余磁盘空间和最后一条错误，停止后重试"],
                ["LLM 修改与实际语音不同", "试听，检查原始 ASR，必要时保留原文"],
                ["数字转换后仍在筛选列表", "这是为了保留检查结果；重新选择条件再刷新"],
                ["文字修改不满意", "Cmd+Z，或从已保存工程恢复"],
            ]
        ),
        p(
            "版本 1.8.0 的更新检查遇到限流时，可以手动打开：https://github.com/Swing233/MAW-bd/releases/latest 。本地后续修复会加入缓存、等待时间提示与发布页入口；不要把尚未发布的修复当作 1.8.0 已有功能。"
        ),
        tip(
            "反馈问题时提供版本、macOS 版本、重现步骤、完整错误与截图。发布截图前遮住密钥和私人路径，不上传 .env 或不希望公开的素材。"
        ),
    ],
)
chapter(
    "18｜完成一次字幕交付的检查表",
    [
        steps(
            "开头、中段、结尾都试听过，文字与真实语音一致。",
            "查看“审阅 → LLM 修改”和待确认字幕，核对人名、数字与术语。",
            "长字幕在自然边界拆开，没有切断英文单词或数字与量词。",
            "帧率、目标分辨率和字幕时间已核对。",
            "保存了 .mosp，导出了 SRT；需要 Final Cut Pro 时也导出了 FCPXML。",
            "保留原视频、文稿、工程与最终交付文件，准备下次继续编辑。",
        ),
        p(
            "原项目及 MAW / MAWE 核心架构由 Moyf 创建。MAW-bd 基于 Moyf/moys-asr-workflow 二次开发，保留 AGPL-3.0-only 许可证与第三方声明。"
        ),
        p(
            "来源与核查：本地 MAW-bd 1.8.0 界面及项目源码；DeepSeek 官方首页 https://www.deepseek.com/ 、API 文档 https://api-docs.deepseek.com/zh-cn/ 、密钥管理 https://platform.deepseek.com/api_keys ；GitHub 限流说明 https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api 。官网界面与规则可能变化，请以当前页面为准。"
        ),
    ],
)
(OUT / "tutorial-content.json").write_text(
    json.dumps(sections, ensure_ascii=False, indent=2)
)


# Preserve original screenshots; annotations are a separate vector layer.
def viewbox(name):
    m = meta[name]
    bs = m["boxes"]
    W, H = m["width"], m["height"]
    if name == "01-launcher":
        return (100, 0, 740, 620)
    if name == "02-deepseek-config":
        return (100, 600, 740, 660)
    if name == "03-editor":
        return (0, 0, W, H)
    if name == "11-deepseek-entry":
        return (0, 0, W, min(H, 770))
    x = max(0, min(b["x"] for b in bs) - 40)
    y = max(0, min(b["y"] for b in bs) - 48)
    right = min(W, max(b["x"] + b["width"] for b in bs) + 40)
    bottom = min(H, max(b["y"] + b["height"] for b in bs) + 36)
    return x, y, right - x, bottom - y


for name, m in meta.items():
    x, y, w, h = viewbox(name)
    data = base64.b64encode((IMAGES / (name + ".jpg")).read_bytes()).decode()
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="{x} {y} {w} {h}" width="{w}" height="{h}"><image x="0" y="0" width="{m["width"]}" height="{m["height"]}" xlink:href="data:image/jpeg;base64,{data}"/>'
    for b in m["boxes"]:
        bx, by, bw, bh = b["x"] - 3, b["y"] - 3, b["width"] + 6, b["height"] + 6
        svg += f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="5" fill="none" stroke="#d94738" stroke-width="3"/><circle cx="{bx + 5}" cy="{by - 7}" r="12" fill="#d94738"/><text x="{bx + 5}" y="{by - 2}" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="15" fill="white">{b["number"]}</text>'
    svg += "</svg>"
    (IMAGES / (name + ".svg")).write_text(svg)
# Self-contained web edition: inline image vectors work without a server.
css = """body{margin:0;background:#f4f6fa;color:#202b3b;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;line-height:1.85}header{padding:68px 6vw;background:#142b46;color:white}header small{color:#91bddc;letter-spacing:.15em}h1{font-size:42px;line-height:1.3;margin:14px 0}header p{color:#c5d5e5;max-width:720px}main{max-width:1020px;margin:auto;padding:28px 24px 70px}nav,section{background:white;border:1px solid #e1e7ef;border-radius:16px;padding:26px 34px;margin-bottom:22px}nav a{display:inline-block;margin:4px 18px 4px 0;color:#2468aa}h2{font-size:25px;margin:5px 0 22px;color:#183653}p{margin:12px 0}li{margin:10px 0}table{border-collapse:collapse;width:100%;font-size:15px;margin:20px 0}th,td{border:1px solid #dce4ec;padding:10px 13px;text-align:left}th{background:#edf4fa}aside{padding:14px 18px;background:#edf6ff;border-left:4px solid #3584c6;margin:22px 0;border-radius:6px}figure{margin:25px 0}figure svg{display:block;width:100%;height:auto;border:1px solid #dce4ec;border-radius:10px}figcaption{font-size:14px;color:#53677d;margin-top:8px}.legend{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:14px}.legend b{background:#d94738;color:#fff;border-radius:50%;padding:2px 7px;margin-right:5px}.muted{color:#6c8096}a{color:#2468aa;overflow-wrap:anywhere}section:target{border-color:#4489c0}@media(max-width:650px){header{padding:40px 24px}h1{font-size:32px}main{padding:16px}nav,section{padding:20px}h2{font-size:23px}table{font-size:13px}td,th{padding:7px}}@media print{body{background:white}nav{display:none}section{break-inside:avoid-page;border:0}header{background:white;color:#142b46;padding:20px}header p{color:#53677d}}"""


def linked(text):
    t = html.escape(text)
    return re.sub(
        r"https://[A-Za-z0-9_./?=&-]+", lambda m: f'<a href="{m[0]}">{m[0]}</a>', t
    )


htmls = [
    '<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MAW-bd 1.8.0 图文使用教程</title><style>'
    + css
    + "</style></head><body><header><small>MAW-bd · macOS · 1.8.0</small><h1>从视频到成品字幕</h1><p>一步一步完成识别、DeepSeek 配置、文稿校对、精准编辑与导出。</p><p>图文使用教程 · 2026-10-12 · 本地界面实拍</p></header><main><nav><strong>快速跳转</strong><br>"
]
for i, s in enumerate(sections):
    htmls.append(f'<a href="#s{i}">{s["title"]}</a>')
htmls.append("</nav>")
md = [
    "# MAW-bd 1.8.0 图文使用教程\n\n从视频到成品字幕｜2026-10-12\n\n本地 1.8.0 界面与独立演示工程，框选编号对应正文。\n"
]
for i, s in enumerate(sections):
    htmls.append(f'<section id="s{i}"><h2>{s["title"]}</h2>')
    md.append("\n## " + s["title"] + "\n")
    for kind, value in s["blocks"]:
        if kind == "p":
            htmls.append("<p>" + linked(value) + "</p>")
            md.append(value + "\n")
        elif kind == "tip":
            htmls.append("<aside>" + linked(value) + "</aside>")
            md.append("> " + value + "\n")
        elif kind == "ol":
            htmls.append(
                "<ol>" + "".join("<li>" + linked(v) + "</li>" for v in value) + "</ol>"
            )
            md.extend([str(n + 1) + ". " + v for n, v in enumerate(value)])
            md.append("")
        else:
            htmls.append(
                "<table>"
                + "".join(
                    "<tr>"
                    + "".join(
                        ("<th>" if j == 0 else "<td>")
                        + linked(v)
                        + ("</th>" if j == 0 else "</td>")
                        for v in row
                    )
                    + "</tr>"
                    for j, row in enumerate(value)
                )
                + "</table>"
            )
            md.extend(
                [
                    "| " + " | ".join(value[0]) + " |",
                    "| " + " | ".join(["---"] * len(value[0])) + " |",
                ]
                + ["| " + " | ".join(row) + " |" for row in value[1:]]
            )
            md.append("")
    if s["figure"]:
        name = s["figure"]
        svg = (IMAGES / (name + ".svg")).read_text()
        htmls.append(
            "<figure>"
            + svg
            + '<figcaption>本地截图 / 官网公开页面 · 红框编号对照操作步骤</figcaption><div class="legend">'
            + "".join(
                f"<span><b>{b['number']}</b>{html.escape(b['label'])}</span>"
                for b in meta[name]["boxes"]
            )
            + "</div></figure>"
        )
        md.append(f"![{s['title']}](images/{name}.svg)\n")
        md.append(
            "；".join(f"{b['number']}：{b['label']}" for b in meta[name]["boxes"])
            + "\n"
        )
    htmls.append("</section>")
htmls.append("</main></body></html>")
(OUT / "MAW-bd-1.8.0-图文教程.html").write_text("".join(htmls))
(OUT / "README.md").write_text("\n".join(md))
# PDF: draw the same image and vector annotations directly; no bitmap edits.
pdfmetrics.registerFont(
    TTFont("TutorialCJK", "/System/Library/Fonts/STHeiti Light.ttc", subfontIndex=0)
)
styles = {
    n: ParagraphStyle(
        n,
        fontName="TutorialCJK",
        fontSize=size,
        leading=leading,
        textColor=colors.HexColor("#24364a"),
        spaceAfter=8,
        wordWrap="CJK",
    )
    for n, size, leading in [
        ("body", 10.5, 17),
        ("title", 24, 34),
        ("h", 17, 25),
        ("small", 9, 14),
        ("tip", 10, 16),
    ]
}
styles["tip"].backColor = colors.HexColor("#edf6ff")
styles["tip"].borderPadding = 9


class Screenshot(Flowable):
    def __init__(self, name, width=480):
        Flowable.__init__(self)
        self.name = name
        self.crop = viewbox(name)
        self.width = min(width, 650 * self.crop[2] / self.crop[3])
        self.height = self.width * self.crop[3] / self.crop[2]

    def draw(self):
        c = self.canv
        x, y, w, h = self.crop
        m = meta[self.name]
        scale = self.width / w
        c.saveState()
        path = c.beginPath()
        path.rect(0, 0, self.width, self.height)
        c.clipPath(path, stroke=0)
        c.drawImage(
            ImageReader(str(IMAGES / (self.name + ".jpg"))),
            -x * scale,
            -(m["height"] - y - h) * scale,
            width=m["width"] * scale,
            height=m["height"] * scale,
        )
        c.setStrokeColor(colors.HexColor("#d94738"))
        c.setFillColor(colors.HexColor("#d94738"))
        c.setLineWidth(1.1)
        for b in m["boxes"]:
            bx = (b["x"] - x - 3) * scale
            by = (y + h - b["y"] - b["height"] - 3) * scale
            c.roundRect(
                bx,
                by,
                (b["width"] + 6) * scale,
                (b["height"] + 6) * scale,
                3,
                stroke=1,
                fill=0,
            )
            cx = (b["x"] - x + 2) * scale
            cy = (y + h - b["y"] + 10) * scale
            c.circle(cx, cy, 7, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(cx, cy - 3, str(b["number"]))
            c.setFillColor(colors.HexColor("#d94738"))
        c.restoreState()


story = [
    Paragraph("MAW-bd 1.8.0", styles["title"]),
    Spacer(1, 12),
    Paragraph("从视频到成品字幕", styles["title"]),
    Spacer(1, 10),
    Paragraph("图文使用教程 · 2026-10-12", styles["body"]),
    Paragraph(
        "安装 · 本地识别 · DeepSeek API · 文稿校对 · 字幕编辑 · 审阅 · SRT / FCPXML",
        styles["body"],
    ),
    Spacer(1, 20),
    Paragraph(
        "截图取自本地 1.8.0 程序界面，使用独立演示工程。账户信息、私人素材和真实密钥不纳入教程。",
        styles["tip"],
    ),
    Spacer(1, 18),
    Paragraph("目录", styles["h"]),
]
for s in sections:
    story.append(Paragraph(s["title"], styles["small"]))
for s in sections:
    story.extend([PageBreak(), Paragraph(s["title"], styles["h"])])
    for kind, value in s["blocks"]:
        if kind in ["p", "tip"]:
            story.append(
                Paragraph(
                    html.escape(value), styles["tip" if kind == "tip" else "body"]
                )
            )
        elif kind == "ol":
            for j, v in enumerate(value):
                story.append(Paragraph(f"{j + 1}. " + html.escape(v), styles["body"]))
        else:
            n = len(value[0])
            t = Table(
                [
                    [Paragraph(html.escape(v), styles["small"]) for v in row]
                    for row in value
                ],
                colWidths=[490 / n] * n,
                hAlign="LEFT",
            )
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf4fa")),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dce4ec")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.extend([t, Spacer(1, 10)])
    if s["figure"]:
        name = s["figure"]
        image = Screenshot(name)
        legend = " / ".join(
            str(b["number"]) + " " + b["label"] for b in meta[name]["boxes"]
        )
        # Give each annotated figure its own page so controls remain readable.
        story.extend(
            [
                PageBreak(),
                Paragraph(s["title"] + " · 操作图", styles["h"]),
                image,
                Spacer(1, 12),
                Paragraph(html.escape(legend), styles["small"]),
            ]
        )


def footer(c, doc):
    c.saveState()
    c.setFont("TutorialCJK", 8)
    c.setFillColor(colors.HexColor("#6d7f92"))
    c.drawString(42, 24, "MAW-bd 1.8.0 · 图文教程")
    c.drawRightString(552, 24, str(doc.page))
    c.restoreState()


pdfpath = ROOT / "output/pdf/MAW-bd-1.8.0-图文教程.pdf"
SimpleDocTemplate(
    str(pdfpath),
    pagesize=(595.28, 841.89),
    leftMargin=48,
    rightMargin=48,
    topMargin=40,
    bottomMargin=42,
    title="MAW-bd 1.8.0 图文教程",
    author="MAW-bd",
).build(story, onFirstPage=footer, onLaterPages=footer)
print(
    json.dumps(
        {"sections": len(sections), "figures": len(meta), "pdf": str(pdfpath)},
        ensure_ascii=False,
    )
)
