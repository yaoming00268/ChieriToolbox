# 千绘莉的多功能工具箱 (Chieri Toolbox)

[![Release](https://img.shields.io/github/v/release/yaoming00268/ChieriToolbox?color=blue&label=Release)](https://github.com/yaoming00268/ChieriToolbox/releases/tag/v2.0.0)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Android-green)](https://github.com/yaoming00268/ChieriToolbox/releases/tag/v2.0.0)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![Kotlin](https://img.shields.io/badge/Kotlin-1.9%2B-purple?logo=kotlin)](https://kotlinlang.org/)
[![License](https://img.shields.io/badge/License-MIT-brightgreen)](https://github.com/yaoming00268/ChieriToolbox)

> 一只二次元死宅为了彻底偷懒而搓出来的 (｀・ω・´)

诸君，我喜欢偷懒，我十分喜欢偷懒，我非常喜欢把一万个散落在各个角落的 Python 脚本、命令行小工具和杂七杂八功能统统塞进同一个现代化暗黑窗口里口牙！

明明最初只是想随手扒几首二次元新番 ED、顺手截几张老婆的 1080P/4K 高清壁纸、给 osu!mania 搓几个手感舒服的打歌皮肤...结果写着写着就把整个 Windows 桌面生态全给卷进来了。才、才不是特意为了你们这些现充写的呢！这可是本死宅自用的终极效率利器 (*/ω＼*)！

本工具箱集成了整整 22 个即插即用动态扩展插件，同时带来了全新重磅构建的 **Android 移动端版本**！桌面端采用 Fluent 暗黑磨砂质感视觉设计，右上角常驻 `Esc` 键一键瞬间逃跑回城；移动端采用 100% SVG 极简现代矢量视觉、深浅双色切换与双轨悬浮交互体系。无论在 PC 桌面还是手机平板上，都能随时从容应对各种生产力与二次元娱乐场景！

---

## 核心特性与阿宅友好设计

1. **PC & Android 双端互通与跨设备算力协同 (Local Cloud)**
   桌面端提供 22 大即插即用动态插件与四大内置核心引擎；PC 端内置轻量 Local Cloud 本地云服务（支持局域网 UDP 自动广播自发现与 REST API），移动端可将高负载 AI 超分任务一键卸载至电脑算力执行！

2. **AI 模型按需动态下载 (On-Demand Model Manager)**
   针对 Real-CUGAN、Real-ESRGAN、Waifu2x 超分模型及 Demucs、Spleeter 人声分离模型，采用轻量解耦按需动态拉取架构，彻底杜绝安装包体积膨胀。内置模型中心支持 SHA256 哈希校验与多镜像源切换。

3. **统一暗黑仪表盘 (Dashboard)**
   所有武器库卡片在首页网格平铺，支持拼音与关键字实时过滤、分类标签筛选。想用哪个点哪个，不用在一堆快捷方式里翻箱倒柜。

4. **随时随地 Esc / 返回键瞬间回城**
   桌面端任何插件界面的右上角均设有显著的返回按钮，猛敲 `Esc` 键或按下 `Alt + Left` 立即无条件切回主页；移动端深度对接系统物理/手势返回键，智能层级返回，极其省电环保。

5. **四大核心引擎全自包含 (免配系统环境变量)**
   PC 工具箱内置了预编译的 `ffmpeg`、`7z`、`ffprobe`、`ffplay` 二进制组件。无论是解压便携版还是安装版，双击直接起飞，彻底告别“请配置 PATH 环境变量”的远古折磨。

6. **安全沙箱与插件热插拔机制**
   各功能遵循标准规范，按需懒加载实例化。单个插件内部哪怕发生不可抗力异常崩溃，也会被沙箱优雅拦截并记录日志，整个工具箱基座纹丝不动。

---

## 重点武器库指南 (22大插件一览)

### 1. B站媒体收割与解构一条龙 (`media_downloader`)
专为收录二次元动画原声、MMD 与高质量同人视频打造的下载引擎：
- **全模式智能识别**: 自动解析单视频（BV号/链接/短链）、多分 P 选集、个人收藏夹全量爬取、UP 主空间投稿全扫荡。
- **大会员原画解锁**: 智能识别并清洗 Cookie / SESSDATA 凭据，4K 超清、8K、HDR、1080P 60帧全规格画质直通。
- **音画分离 DASH 流秒级合成**: 智能捕获最高画质流与 Hi-Res / 杜比全景声音频轨，调用内置 FFmpeg 秒速合并，无损且杜绝音画不同步。
- **批量勾选与音频导出**: 支持全选、全不选、反选与多选批量排队下载；勾选“仅提取音频”时，支持自由导出为 MP3、WAV、FLAC、M4A、AAC、OGG 等多种无损与高码率格式。
- **B站弹幕转 ASS 特效字幕 (`danmaku_to_ass`)**: 支持随视频自动下载 XML 弹幕并无损转制为专业 ASS 格式，智能排布滚动弹幕、顶端固定与底端防挡字幕，支持自定义字体、边框阴影与不透明度。

### 2. 图像格式转换与 AI 超分辨率工坊 (`image_master`)
二次元画师与壁纸党必备的图像处理枢纽：
- **全格式多线程互转**: 完美支持 PNG、JPG、WEBP、ICO、BMP、TIFF、GIF 批量互转，内置透明通道纯白打底算法，转换 JPEG 时彻底杜绝黑色底色暴毙惨剧。
- **二次元 AI 超分辨率重采样**: 集成 Real-CUGAN、Real-ESRGAN、Waifu2x 等二次元图像超分算法（2x / 4x 放大，智能消除伪影与降噪），支持 CPU / GPU 渲染与轻量模型按需动态下载。
- **智能居中裁切填充**: 独创二次元正方形头像生成模式，自动保持原图比例缩放并智能居中裁剪为 1:1 头像（如 400x400、512x512）。
- **坐标区域显式剪裁**: 支持指定 `(left, top, right, bottom)` 像素矩形剪裁，截取本子或插画局部细节快准狠。
- **高保真缩放**: 百分比缩放与固定分辨率等比缩放均采用高质量 Lanczos 滤波器，保持线条边缘锐利清晰。

### 3. 音频精准剪裁与音轨提取 (`audio_cutter` & `video_to_audio` & `audio_converter`)
- **毫秒级时间轴剪裁**: 视音频波形时间轴精准切割，支持流拷贝（0 损耗秒级切片）与重编码双模式，用来切二次元歌曲铃声或者剪 MAD 音效简直爽到飞起。
- **批量视频转音频**: 批量丢入本地动漫番剧或 MV 视频，一键抽离背景音乐并转换为高品质 MP3 / FLAC。
- **音频批量格式转换**: 音频码率、采样率、声道数随心调整。

### 4. 视频逐帧解压提取 (`frame_extractor`)
- **逐帧与定时抽帧**: 自由设置每秒帧数（FPS）或时间间隔采样，捕捉动画每一帧神仙作画。
- **I 关键帧模式**: 自动适配 FFmpeg 新版 `passthrough` / `vfr` 语法，只提取不模糊的 I 关键帧，生成高质量壁纸原画素材。

### 5. 音游狗专属: osu!mania 皮肤调校工作台 (`osu_skin_studio`)
- **结构化读写 `skin.ini`**: 可视化调节判定线位置（HitPosition）、列宽（ColumnWidth）、舞台偏移（ScorePosition/ComboPosition）等。
- **实时视口画布预览**: 4K 到 9K 键位实时渲染，支持 16:9 与 4:3 视口切换，调皮肤再也不用繁琐地反复重启游戏测试了 (￣▽￣)ノ。

### 6. 更多阿宅日常护肝利器
- **全平台音乐格式解密工坊 (`ncm_decryptor`)**:
  - **网易云音乐**: `.ncm` 格式一键无损还原为标准 MP3/FLAC，保留元数据与封面。
  - **QQ音乐 QMC**: 智能识别 QMCv1 与 QMCv2 算法，支持 `.qmc3`, `.qmc0`, `.qmcflac`, `.mflac`, `.mgg` 解密。
  - **酷狗音乐 KGM**: 支持 `.kgm`, `.vpr` 解密与单字节/双重异或回退。
  - **酷我音乐 KWM**: 支持 `.kwm` 动态报头解析与掩码逆向探测解密。
- **压缩解压与 ACG 密码本 (`archive_manager`)**: 基于 7-Zip LZMA2 引擎，支持 7z/zip/rar 高压缩比打包与解压；内置 **ACG 资源解压密码本**，收集各大二次元资源站/论坛高频密码，解密包自动轮询暴力匹配一键解开。
- **文件批量整理大师 (`file_suite`)**: 正则批量改名、前后缀替换、数字序号对齐补零、文件夹扁平化整理，整顿几万张杂乱同人图的救星。
- **专业截图工具 (`screen_capture`)**: PixPin 风格截图标注、贴图置顶、放大镜像素吸色。
- **高清屏幕录像机 (`screen_recorder`)**: 虚拟桌面全屏或区域录像，音画同步捕获游戏精彩操作。
- **顽固应用与文件强力粉碎 (`force_killer`)**: 遇到被 Windows 进程死锁占用的文件，一键查杀占用句柄并强力抹除。
- **交互式白板 (`whiteboard`)**: 希沃白板风格，摸鱼随手涂鸦、画草图、笔划撤销与整幅导出。
- **模拟键入与极速粘贴 (`auto_input`)**: 底层真实字符延时模拟击键，绕过网页端或远程桌面的防粘贴限制。
- **应用代理配置工具 (`proxy_configurator`)**: 一键查看与开关应用代理环境。
- **全能文本翻译 (`translator`)**: 快速多语言文本对照。
- **系统增强与右键助手 (`system_integrator`)**: 一键为 Windows 右键菜单注入快捷通道，无需管理员权限。

---

## 移动端 (Android) 极简架构与核心功能

千绘莉工具箱移动端专为二次元阿宅打造，采用轻量化 Kotlin 原生宿主 + 现代纯净 Web 前端混合架构（WebView + WebAppInterface 原生桥接），不依赖重量级外部运行环境，零系统污染，体积仅约 6MB。

### 1. 移动端架构设计与原生硬件能力穿透
- **原生与 Web 双向桥接 (`WebAppInterface`)**：
  - **MediaCodec 硬件加速音频编码**：结合 Web Audio API 获取 PCM 数据，通过 Android 原生 `MediaCodec` 硬件编码器配合 `MediaMuxer` 封装为高保真 AAC/M4A 格式，极速且省电。
  - **底层网络穿透与防盗链突破**：针对移动端 WebView 的 CORS（跨域资源共享）与防盗链限制，使用原生 `HttpURLConnection` 发起网络请求，完美持久化传递 Cookie 与 `SESSDATA`，支持带 Referer 请求头的高清媒体流直拉。
  - **Apache Commons Compress 原生归档引擎**：内置 Apache 官方成熟解压组件，脱离系统命令依赖，原生支持 7Z, TAR, GZ, BZ2, LZ4, XZ, ZIP 格式预览与提取，落盘公共 Downloads 目录。
  - **系统媒体库联动 (`MediaScannerConnection`)**：下载或导出的多媒体文件（图片、音频、解压包）写入公共目录后，自动触发 MediaScanner 索引广播，立即可在手机系统相册与音乐播放器中找到。
  - **RFC 1321 MD5 签名加速**：原生 Java 消息摘要引擎，毫秒级计算百度翻译等第三方 API 所需的 MD5 签名。

### 2. 移动端重点功能武器库
- **音频多格式转换工坊 (`audio_engine`)**：
  - 支持 **MP3** (内置 LAME.js 压制)、**WAV** (16-bit PCM 容器生成)、**FLAC** (无损帧格式打包)、**AAC/M4A** (MediaCodec 硬件加速)、**OGG** 格式互转。
  - 支持音频波形毫秒级切片截取、采样率重采样 (16kHz ~ 48kHz) 与码率调节 (128kbps ~ 320kbps)。
- **B站/YT 媒体流解析与大会员高画质提取 (`media_engine`)**：
  - 支持持久化配置与管理 Cookie / SESSDATA 大会员凭据，自动解锁 1080P60 / 4K 超清 / 杜比全景声 DASH 独立音画流。
  - 原生支持单视频与多 P 视频解析，提供音画分轨直接下载，后台流式下载并实时推送百分比与下载速度。
- **全能解压缩与归档中心 (`archive_engine`)**：
  - 支持 **7Z** (7-Zip LZMA/LZMA2), **TAR**, **GZ / TGZ**, **BZ2 / TBZ2**, **LZ4** (Frame 格式), **XZ**, **ZIP** 全格式。
  - 支持压缩包内文件树结构极速预览、单文件精准提取以及全量一键解压至系统公共 `Download/` 目录。
- **智能多引擎 AI 翻译 (`translator`)**：
  - 支持 **OpenAI 兼容接口** (可自由接入 DeepSeek, ChatGPT, Qwen, 通义千问等大模型)。
  - 支持 **DeepL API**、**百度翻译开放平台**（内置 RFC 1321 MD5 签名计算）、**Google 翻译**。
  - 独家内置 **二次元/ACG 专属高频离线词库**，常见黑话与角色名离线秒级智能翻译。
- **网易云 NCM 本地格式解密 (`ncm_engine`)**：
  - 纯前端逆向 AES-128-ECB 与 RC4 密钥流，本地一键无损还原为标准 MP3/FLAC，保留内嵌封面与 ID3 元数据。
- **触控优化摸鱼白板 (`whiteboard`)**：
  - 针对手机与平板多点触控与手写笔优化的轻量画布，支持自由笔刷、粗细调节、颜色拾取、多步撤销重做与图片导出。
- **osu!mania 移动端谱面与皮肤视口 (`osu_engine`)**：
  - 结构化读写 `skin.ini`，移动端 4K-9K 键位实时视口模拟，支持舞台偏移与打击线精细标定。
- **跨设备局域网算力协同 (`cross_device_engine`)**：
  - 自动扫描局域网 PC 端 Local Cloud 服务或手动配置直连，将移动端低清壁纸/插图一键分发至 PC 端 GPU 进行 Real-CUGAN / Real-ESRGAN 超分放大，异步进度轮询并秒级回传超清成果。

### 3. 现代化极简移动 UI 与外观定制中心
- **100% SVG 扁平化矢量图标体系**：全界面彻底告别 emoji 字符图标，采用工业级现代矢量线条设计，在各类高刷新率手机屏幕上保持绝对的清晰锐利与视觉统一。
- **深浅色双模式即时热切换 (Dark / Light)**：
  - 沉浸式状态栏与导航栏着色：通过 `WindowCompat.getInsetsController` 动态同步 Android 状态栏图标与导航栏底色，深浅模式切换丝滑无闪烁。
- **高度自由的外观调节中心**：
  - **卡片尺寸三档密度**：紧凑 (Compact)、标准 (Standard)、宽松 (Comfortable)，自由适配大屏手机与小折叠屏。
  - **界面与卡片透明度**：50% ~ 100% 线性无极滑动调节，即时生效。
  - **毛玻璃 / 亚克力磨砂质感**：提供无模糊 (0px)、轻微磨砂 (8px)、深度磨砂 (16px) 三种 Backdrop Filter 级别。
  - **外观状态本地持久化**：所有个性化外观配置自动持久化至 LocalStorage，并支持一键恢复默认。
- **双轨悬浮交互系统 (In-App & System-Wide Floating Ball)**：
  - **应用内悬浮球 (In-App)**：手指自由拖拽，松手平滑物理吸附屏幕边缘，靠边自动半透明折叠；轻点展开气泡快捷菜单，快速跳转各核心功能。
  - **全局系统悬浮窗 (System Overlay)**：基于 `FloatingBallService` 与 `TYPE_APPLICATION_OVERLAY` 机制，退至手机桌面或其他 App 时依旧常驻贴边，轻触即刻拉起千绘莉工具箱并滑出侧边抽屉。
  - **侧边栏抽屉导航 (Drawer Navigation)**：自适应滑出，分类整理 10 大移动端工具库与设置入口。

### 4. Android Linux 沙盒机制差异与边界矩阵
由于 Android 操作系统基于 Linux 内核，且严格遵循 Linux UID 隔离、SELinux 强制访问控制策略与移动端生命周期规范，部分 PC 桌面独占的功能在移动端受到沙盒客观限制。千绘莉工具箱在设计之初秉承严谨的工程态度，对 PC 独占功能的技术根因进行了梳理，并提供对应的高可用移动平替方案：

| 武器库功能项 | 移动端状态 | 技术根因与沙盒隔离说明 | 移动端平替 / 建议操作 |
|:---|:---:|:---|:---|
| **音频多格式转换** | ✅ 深度移植 | 支持 MediaCodec 硬件加速与 Web Audio API，MP3/WAV/FLAC/AAC/OGG 全支持 | 原生硬件加速 + 纯前端编码 |
| **B站大会员音视频收割** | ✅ 深度移植 | 突破 WebView CORS 限制，持久化 Cookie/SESSDATA，直取 1080P60/4K 流 | 原生 HttpURLConnection 桥接下载 |
| **多格式归档压缩解压** | ✅ 深度移植 | 集成 Apache Commons Compress，支持 7Z/ZIP/TAR/GZ/BZ2/LZ4/XZ | 原生落盘公共 Downloads 目录 |
| **AI 智能与二次元翻译** | ✅ 深度移植 | 支持 OpenAI 兼容、DeepL、百度（RFC 1321 MD5）、Google 与离线词库 | 本地与云端双引擎 |
| **网易云 NCM 格式解密** | ✅ 深度移植 | 纯前端逆向 AES+RC4 解密，保留元数据与封面 | 纯前端解密 |
| **系统托盘常驻菜单** | 🔄 移动端平替 | Android 无系统托盘概念 | 采用 `FloatingBallService` 全局贴边悬浮球平替 |
| **视音频波形切片与截取** | 🔄 移动端平替 | 移动端无本地重量级 FFmpeg 二进制环境 | 采用 Web Audio API 毫秒级重采样与 WAV 导出平替 |
| **Win32 进程强力查杀 (Force Killer)** | ❌ 沙盒限制无法实现 | **技术根因**：Android 严格执行 Linux UID 进程沙盒与 SELinux 强制访问控制。第三方非 Root 应用仅能杀戮自身进程，系统内核直接拒绝跨 UID 强杀其他应用进程。 | 请使用系统自带“设置 -> 应用管理 -> 强行停止” |
| **Windows 注册表 PAC 代理注入** | ❌ 沙盒限制无法实现 | **技术根因**：Android 无 Windows 注册表子系统。系统网络代理必须由用户手动在 Wi-Fi 设置中配置，或通过系统 `VpnService` 启动虚拟网卡并经系统授权弹窗，无法静默注入 PAC 脚本。 | 请在 Wi-Fi 高级设置中手动配置代理或使用 VPN 应用 |
| **物理键盘钩子与模拟键入 (Auto Input)** | ❌ 沙盒限制无法实现 | **技术根因**：Win32 `SetWindowsHookEx` / `SendInput` 可全局拦截物理键盘事件。Android 为防御敲击记录器恶意木马，严禁后台全局物理键盘监听，需依赖无障碍辅助服务且受严格权限限制。 | 使用一键复制到剪贴板，通过系统输入法粘贴 |
| **DirectShow 底层原生录屏** | ❌ 沙盒限制无法实现 | **技术根因**：DirectShow 与 Desktop Duplication 为 Windows 独占多媒体子系统。Android 移动端录屏必须申请 `MediaProjection` 用户交互授权凭据且后台服务功耗限制大。 | 推荐使用 Android 控制中心下拉自带的“屏幕录制” |

---

## 预构建封装包 (Releases 下载)

懒得配环境的诸君请直接前往 [GitHub Releases v2.0.0 官方发布页面](https://github.com/yaoming00268/ChieriToolbox/releases/tag/v2.0.0) 下载预打包二进制产物：

| 分发包文件 | 平台架构 | 文件大小 | 特性说明与直链高速下载 |
|:---|:---:|:---:|:---|
| **[📦 Setup_ChieriToolbox.exe](https://github.com/yaoming00268/ChieriToolbox/releases/download/v2.0.0/Setup_ChieriToolbox.exe)** | Windows x64 | ~170 MB | 基于 Inno Setup 6 编译构建的标准单文件安装向导，内置 LZMA2 固实压缩、四大引擎 (FFmpeg, 7-Zip, FFprobe, FFplay) 与桌面/开始菜单快捷方式 |
| **[📦 ChieriToolbox-v2.0.0-Portable.zip](https://github.com/yaoming00268/ChieriToolbox/releases/download/v2.0.0/ChieriToolbox-v2.0.0-Portable.zip)** | Windows x64 | ~228 MB | 绿色免安装便携版，解压至任意目录双击 `ChieriToolbox.exe` 即开即用，配置持久化于当前目录，纯净不污染系统 |
| **[📱 ChieriToolbox-Android.apk](https://github.com/yaoming00268/ChieriToolbox/releases/download/v2.0.0/ChieriToolbox-Android.apk)** | Android 8.0+ (ARM64/x86) | ~6.14 MB | Android 极简轻量移动端，内置 Kotlin 原生硬件加速 + 100% SVG 矢量 UI + 双轨悬浮窗，体积超轻，离线全自包含 |

### 移动端 Android 安装包使用指引

1. **安装步骤**：
   - 手机浏览器或 PC 下载 `ChieriToolbox-Android.apk`，在手机文件管理器中点击安装。
   - 若系统弹出“允许来自此来源的应用”或未知应用来源安装确认，点击“允许”或“继续安装”即可。
2. **权限授权与隐私安全**：
   - **网络权限 (`INTERNET`)**：用于 B站/YouTube 媒体流解析下载与 OpenAI/DeepL/百度在线翻译，网络请求均由本地发起，绝不上传任何隐私。
   - **文件存储**：自动适配 Android 10+ 分区存储规范，下载的音视频与解压文件默认落盘于公共 `Download/` 目录，无需授予危险的 `MANAGE_EXTERNAL_STORAGE` 权限。
   - **系统级悬浮窗 (`SYSTEM_ALERT_WINDOW`)**：若需使用退至后台/桌面也能随时拉起的“全局贴边悬浮球”，首次在应用设置中开启时，系统会自动引导跳转授权“显示在其他应用上层”，授权后即刻生效。
3. **国产定制 ROM (MIUI/澎湃OS/鸿蒙/ColorOS/OriginOS) 保活建议**：
   - 若开启“全局系统悬浮窗”后，应用切至后台被系统电池管理强杀，建议前往系统“设置 -> 应用管理 -> 千绘莉工具箱”：
     - 允许“自启动 / 关联启动”；
     - 将电池策略设为“无限制 / 不受省电策略限制”。

---

## 极客专属: 源码运行与本地构建

如果你也是喜欢折腾源码的同道中人，可以通过如下步骤本地调试运行：

### 1. 准备环境 (桌面端)
推荐使用 Python 3.10 及以上版本：
```powershell
git clone https://github.com/yaoming00268/ChieriToolbox.git
cd ChieriToolbox
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt  # 或安装 PySide6, requests, Pillow, yt-dlp
```

### 2. 本地启动桌面端
```powershell
.\.venv\Scripts\python.exe main.py
```
或者直接双击根目录下的 `启动工具箱.bat`。

### 3. 执行自动化测试套件
本项目具备完备的测试验证体系（涵盖 222 项全量自动化测试、B站音视频流水线、图片裁剪缩放、音频剪裁与 22 插件完整生命周期）：
```powershell
# 运行全量 222 项自动化集成测试
.\.venv\Scripts\pytest

# 运行桌面端动态寻路与核心引擎冒烟测试
.\.venv\Scripts\python.exe main.py --smoke-test
```

### 4. 本地独立打包桌面版 EXE
本项目提供了完整的 PyInstaller 规格配置文件与 Inno Setup 编译脚本：
```powershell
pyinstaller --clean toolbox.spec
```

### 5. 编译 Android 移动端 APK
移动端工程采用标准 Gradle 构建体系：
```powershell
cd android
# 编译 Debug 版 APK
.\gradlew.bat assembleDebug
# 编译产物位于: android/app/build/outputs/apk/debug/app-debug.apk
```
同时可运行移动端纯前端与硬件引擎自动化验证脚本：
```powershell
node android/test_mobile_engines.js
```

---

## 测试跑分与稳定性验证记录

本工具箱代码经过严格的闭环集成验证与高强度自动化回归测试：
- **全量单元与真实集成测试**: `pytest tests/` 共 **231 项自动化测试 100% 全部通过** (包括 22 个插件动态发现、B站流水线、模型按需下载管理器、局域网本地云协同、多平台音乐解密及 ACG 密码本自动化测试)。
- **进化特性专项回归测试**: `tests/test_evolution_features.py` 覆盖 Local Cloud HTTP/UDP 广播发现、超分接口、多源模型下载、QMC/KGM/KWM 音频解密、弹幕 ASS 转换及 ACG 密码匹配，**9/9 全项通过**。
- **多 DPI 与多分辨率视觉自适应测试**: `tests/test_ui_adaptive_visual.py` 覆盖 100% (1.0x)、125% (1.25x)、150% (1.5x) 多档系统 DPI 缩放及从 1024x700 紧凑到 1920x1080 全高清多档窗口尺寸，产出 33 份全界面截图（保存在 `tests/ui_screenshots/dpi_adaptive/`），均无控件重叠或文本截断。
- **冻结可执行文件冒烟测试**: 打包版独立程序执行 `ChieriToolbox.exe --smoke-test`，22 个插件动态发现、5 大底层可执行工具寻路（ffmpeg, 7z, ffprobe, ffplay, inno_setup_iscc）与持久化配置读写 **全部通过 (PASSED)**。
- **Android 移动端核心引擎自动化测试**: `node android/test_mobile_engines.js` 覆盖 AudioEngine (WAV/MP3/FLAC 结构校验)、MediaEngine (Cookie / SESSDATA 清洗解析)、ArchiveEngine (POSIX TAR / 7Z / LZ4 流式解压)、TranslatorEngine (RFC 1321 MD5 签名生成、ACG 离线词库) 以及 CrossDeviceEngine 跨设备端点解析与超分载荷装配，**24 项测试 100% 全部通过 (PASS)**。
- **Android 真机与模拟器 UI 自动化与外观测试**: 覆盖冷启动加载、抽屉侧边栏平滑交互、系统返回键栈导航、应用内悬浮球物理吸附/半贴边折叠、全局系统悬浮窗 (`FloatingBallService`) 跨应用常驻与唤醒、深浅色模式与卡片外观调节，全流程验证通过。

---

## 免责声明

1. 本项目仅供 Python 与移动端开发者交流学习以及个人效率提升使用，请勿用于任何非法商业用途。
2. B站媒体下载器与视频解析功能仅供个人学习离线备份合法视听内容，视频所有权与版权均归属 Bilibili 弹幕视频网及对应的原视频创作者所有。
3. 请合理控制网络请求并发频率，自觉遵守相关平台的服务条款与网络法律法规。

---

> 咕咕咕？不，本死宅的代码绝对不会鸽！喜欢的话就顺手点个 Star 鼓励一下这只屑开发者吧 _(:з」∠)_！

