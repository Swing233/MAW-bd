# MAW-bd Windows 测试版

目标：Windows 10/11 x64，便携 ZIP。解压完整目录后运行 `MAW-bd.exe`，不要只复制 EXE。无需安装 Python 或原版 MAW；完整包带 FFmpeg、FFprobe 和运行环境安装器。

## 首次使用

1. 将便携包解压到可写目录，例如自己的“文档”文件夹。
2. 运行 MAW-bd.exe。启动器使用 Microsoft Edge WebView2；缺少时先从 [Microsoft 官方页面](https://developer.microsoft.com/microsoft-edge/webview2/) 安装 Evergreen Runtime。
3. 选择视频，本地模式先点击“下载 / 检查本地模型”。第一次需要联网准备 Python、依赖与模型，后续使用缓存。CPU 可以运行，但速度取决于硬件；GPU 加速须另外核对显卡和驱动。
4. 有视频和 SRT 时，直接点击“MP4 + SRT 直接编辑”。
5. 需要校对时填入自己的 DeepSeek Key，添加文稿后修订。语音优先、时间不变。
6. 在编辑器完成审阅、逐帧编辑并保存 .mosp，导出 SRT 或 FCPXML。Windows 可生成 FCPXML，最终导入仍需要 Mac 上的 Final Cut Pro。

操作与 macOS 版一致，保存和撤销分别使用 Ctrl+S、Ctrl+Z。跨系统迁移 .mosp 后，需要重新绑定媒体的新路径。

## 数据位置

- 本地识别环境：`%LOCALAPPDATA%\MAW-bd\local-runtime\Scripts\python.exe`
- 下载和 Python 缓存：`%LOCALAPPDATA%\MAW-bd`
- 配置、日志、模型缓存与更新检查缓存：`%LOCALAPPDATA%\MAW`

Windows 初版支持检查更新和打开对应 Windows 安装包下载地址，暂不提供 macOS 的自动替换和增量安装。不需要 GitHub Token。软件只监听 127.0.0.1。

## 从源码构建

需要 Windows x64、uv、网络，以及含 ffmpeg.exe / ffprobe.exe 与许可证的 Windows FFmpeg ZIP。构建使用 PyInstaller 6.16.0；运行环境依赖使用独立 Windows 哈希清单。

```powershell
./scripts/build_windows.ps1 -FFmpegZip C:\Downloads\ffmpeg-release-essentials.zip
```

输出：`dist/releases/MAW-bd-<版本>-Windows-x64.zip`。

也可手动运行 GitHub Actions 的 `Windows portable build`，下载构建产物。该流程只上传测试产物，不创建 Release、不推送源码。FFmpeg 下载来源为 FFmpeg 官方下载页列出的 Gyan，保留其许可证文件。

## 实机验收

- 解压在含中文和空格的路径，不安装 Python，启动正常。
- MP4 + SRT 直接编辑：视频、波形、字幕均正常。
- 本地模型首次准备与再次使用；取消任务后没有残留识别进程。
- 云端 ASR 与 DeepSeek 使用自己的 Key；日志不暴露密钥。
- 切割、合并、框选、撤销、审阅与帧移动正常。
- 保存后重新打开 .mosp，SRT 时间和文字正确。
- FCPXML 输出在 Mac / Final Cut Pro 中核对。

目前未进行真实 Windows 桌面和模型推理验收；需要先在 Windows 构建并按上述清单测试，不能将 macOS 的测试通过当作 Windows 已可用。
