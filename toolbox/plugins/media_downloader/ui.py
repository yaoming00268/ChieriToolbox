"""
B站媒体下载器 - 现代化 GUI 界面
"""

import os
import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QProgressBar, QTextEdit,
    QFileDialog, QMessageBox, QGroupBox, QListWidget, QListWidgetItem,
    QMenu
)
from toolbox.core.config_manager import ConfigManager
from .api import BiliApiClient, QUALITY_MAP, VIP_QN_SET, normalize_cookie
from .downloader import (
    MediaDownloadWorker,
    BatchMediaDownloadWorker,
    find_ffmpeg_executable,
    check_item_downloaded,
    get_task_target_filename
)


class ImageFetchThread(QThread):
    image_loaded = Signal(bytes)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            resp = requests.get(self.url, timeout=5)
            if resp.status_code == 200:
                self.image_loaded.emit(resp.content)
        except Exception:
            pass


class AccountCheckWorker(QThread):
    finished_signal = Signal(dict)

    def __init__(self, api: BiliApiClient):
        super().__init__()
        self.api = api

    def run(self):
        try:
            status = self.api.check_account_status()
            self.finished_signal.emit(status)
        except Exception as e:
            self.finished_signal.emit({
                "is_login": False,
                "uname": "",
                "mid": 0,
                "vip_type": 0,
                "vip_status": 0,
                "vip_label": "网络异常",
                "message": f"账号状态检测失败: {e}"
            })


class BrowserCookieWorker(QThread):
    finished_signal = Signal(bool, str, str)

    def run(self):
        try:
            from yt_dlp.cookies import extract_cookies_from_browser, YDLLogger

            class QuietLogger(YDLLogger):
                def debug(self, msg): pass
                def info(self, msg): pass
                def warning(self, msg): pass
                def error(self, msg): pass

            browsers = ["edge", "chrome", "firefox"]
            err_details = []
            for b in browsers:
                try:
                    jar = extract_cookies_from_browser(b, logger=QuietLogger())
                    cookie_dict = {}
                    for c in jar:
                        domain = getattr(c, "domain", "")
                        if "bilibili.com" in domain:
                            cookie_dict[c.name] = c.value
                    if "SESSDATA" in cookie_dict or cookie_dict:
                        cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
                        self.finished_signal.emit(True, cookie_str, b)
                        return
                    else:
                        err_details.append(f"{b}: 未找到 B站 相关 Cookie")
                except Exception as ex:
                    err_details.append(f"{b}: {ex}")

            self.finished_signal.emit(False, "，".join(err_details), "")
        except Exception as e:
            self.finished_signal.emit(False, f"读取浏览器异常: {e}", "")


class MediaParseWorker(QThread):
    finished_signal = Signal(dict)

    def __init__(
        self,
        api: BiliApiClient,
        target_type: str = "",
        target_id: str = "",
        raw_text: str = "",
        mode_idx: int = 0
    ):
        super().__init__()
        self.api = api
        self.target_type = target_type  # "video", "favorite", "space"
        self.target_id = target_id
        self.raw_text = raw_text
        self.mode_idx = mode_idx

    def run(self):
        try:
            target_type = self.target_type
            target_id = self.target_id

            if not target_id and self.raw_text:
                raw_text = self.raw_text.strip()
                if self.mode_idx == 1:
                    target_type = "video"
                    target_id = self.api.extract_bvid(raw_text)
                elif self.mode_idx == 2:
                    target_type = "favorite"
                    target_id = self.api.extract_fav_id(raw_text)
                elif self.mode_idx == 3:
                    target_type = "space"
                    target_id = self.api.extract_up_mid(raw_text)
                else:
                    target_type, target_id = self.api.detect_target_type_and_id(raw_text)
                    if target_type == "unknown":
                        if raw_text.isdigit():
                            target_type = "favorite"
                            target_id = raw_text
                        else:
                            bvid = self.api.extract_bvid(raw_text)
                            if bvid:
                                target_type = "video"
                                target_id = bvid

            if not target_id:
                self.finished_signal.emit({
                    "success": False,
                    "error": "未能从输入中提取出合法的 ID 或链接，请核对输入格式。"
                })
                return

            if target_type == "favorite":
                res = self.api.get_favorite_videos(target_id)
                self.finished_signal.emit(res)
            elif target_type == "space":
                res = self.api.get_space_videos(target_id)
                self.finished_signal.emit(res)
            else:
                info = self.api.get_video_info(target_id)
                if info.get("success") and info.get("pages"):
                    pages = info.get("pages")
                    first_page = pages[0] if isinstance(pages, list) and pages and isinstance(pages[0], dict) else {}
                    first_cid = first_page.get("cid")
                    if first_cid:
                        stream_res = self.api.get_play_streams(target_id, first_cid)
                        if stream_res.get("success"):
                            info["available_qualities"] = stream_res.get("available_qualities", [])
                            info["stream_res"] = stream_res
                self.finished_signal.emit(info)
        except Exception as e:
            self.finished_signal.emit({"success": False, "error": str(e)})


class VideoParseWorker(MediaParseWorker):
    def __init__(self, api: BiliApiClient, bvid: str):
        super().__init__(api, "video", bvid)


class MediaDownloaderWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.api = BiliApiClient()
        self.config_manager = ConfigManager()
        self.worker: MediaDownloadWorker = None
        self.img_thread: ImageFetchThread = None
        self.parse_worker: MediaParseWorker = None
        self.account_worker: AccountCheckWorker = None
        self.browser_worker: BrowserCookieWorker = None
        self.current_video_info = None
        self.account_status = None
        self.init_ui()
        self.load_config()

    def handle_initial_paths(self, paths: list):
        """处理外部传入的视频链接或BV号"""
        if paths:
            url_or_bv = paths[0].strip()
            self.le_url.setText(url_or_bv)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. 顶部解析栏 (包含解析模式选择与输入框)
        parse_box = QHBoxLayout()
        parse_box.setSpacing(10)

        self.combo_parse_mode = QComboBox()
        self.combo_parse_mode.addItems(["智能识别", "单视频 (BV/链接)", "收藏夹 (FID/链接)", "UP主主页 (UID/链接)"])
        self.combo_parse_mode.setMinimumWidth(140)
        parse_box.addWidget(self.combo_parse_mode)

        self.le_url = QLineEdit()
        self.le_url.setPlaceholderText("在此粘贴视频链接/BV号、收藏夹链接/FID 或 UP主主页链接/UID")
        parse_box.addWidget(self.le_url, 1)

        self.btn_parse = QPushButton("解析资源")
        self.btn_parse.setObjectName("primaryBtn")
        self.btn_parse.setMinimumWidth(110)
        self.btn_parse.clicked.connect(self._parse_video)
        parse_box.addWidget(self.btn_parse)

        main_layout.addLayout(parse_box)

        # 2. 账号凭据与大会员检测面板 (Cookie / SESSDATA)
        group_account = QGroupBox("账号凭据与大会员检测 (Cookie / SESSDATA)")
        layout_account = QVBoxLayout(group_account)
        layout_account.setSpacing(8)

        cookie_row = QHBoxLayout()
        cookie_row.addWidget(QLabel("Cookie / SESSDATA:"))
        self.le_cookie = QLineEdit()
        self.le_cookie.setEchoMode(QLineEdit.Password)
        self.le_cookie.setPlaceholderText("在此填入 Cookie 字符串、JSON 数组或 SESSDATA 值以解锁大会员高画质")
        self.le_cookie.textChanged.connect(self._on_cookie_text_changed)
        cookie_row.addWidget(self.le_cookie, 1)

        self.btn_toggle_cookie = QPushButton("显示")
        self.btn_toggle_cookie.setFixedWidth(60)
        self.btn_toggle_cookie.clicked.connect(self._toggle_cookie_visibility)
        cookie_row.addWidget(self.btn_toggle_cookie)

        self.btn_paste_cookie = QPushButton("从剪贴板粘贴")
        self.btn_paste_cookie.clicked.connect(self._paste_cookie_from_clipboard)
        cookie_row.addWidget(self.btn_paste_cookie)

        self.btn_read_browser = QPushButton("读取浏览器Cookie")
        self.btn_read_browser.clicked.connect(self._extract_browser_cookies)
        cookie_row.addWidget(self.btn_read_browser)

        self.btn_check_account = QPushButton("检测账号状态")
        self.btn_check_account.clicked.connect(self._check_account)
        cookie_row.addWidget(self.btn_check_account)

        layout_account.addLayout(cookie_row)

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("账号状态:"))
        self.lbl_account_badge = QLabel("[未登录 (最高480P)]")
        self.lbl_account_badge.setStyleSheet(
            "background-color: rgba(148, 163, 184, 0.15); color: #64748b; "
            "padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;"
        )
        status_row.addWidget(self.lbl_account_badge)
        status_row.addStretch()
        layout_account.addLayout(status_row)

        main_layout.addWidget(group_account)

        # 3. 中部内容区：左侧封面与基本信息，右侧分P与画质选择
        content_box = QHBoxLayout()
        content_box.setSpacing(16)

        # 左侧卡片：封面 + 标题
        left_card = QGroupBox("视频信息")
        left_card_layout = QVBoxLayout(left_card)
        left_card_layout.setSpacing(8)

        self.lbl_cover = QLabel("暂无视频封面")
        self.lbl_cover.setObjectName("mediaCoverBox")
        self.lbl_cover.setFixedSize(240, 135)
        self.lbl_cover.setAlignment(Qt.AlignCenter)
        left_card_layout.addWidget(self.lbl_cover, 0, Qt.AlignCenter)

        self.lbl_title = QLabel("标题: -")
        self.lbl_title.setObjectName("mediaTitleLabel")
        self.lbl_title.setWordWrap(True)
        left_card_layout.addWidget(self.lbl_title)

        self.lbl_up = QLabel("UP主: -")
        self.lbl_up.setObjectName("mediaUpLabel")
        left_card_layout.addWidget(self.lbl_up)

        left_card_layout.addStretch()
        content_box.addWidget(left_card, 1)

        # 右侧卡片：分P/视频列表 + 批量勾选 + 画质与音频设置
        right_card = QGroupBox("下载选项")
        right_card_layout = QVBoxLayout(right_card)
        right_card_layout.setSpacing(8)

        # 列表标题与多选工具条
        top_list_h = QHBoxLayout()
        top_list_h.setSpacing(8)
        self.lbl_list_title = QLabel("待下载列表 (0 项):")
        top_list_h.addWidget(self.lbl_list_title)
        top_list_h.addStretch()

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setFixedWidth(50)
        self.btn_select_all.clicked.connect(self._select_all_items)
        top_list_h.addWidget(self.btn_select_all)

        self.btn_select_none = QPushButton("全不选")
        self.btn_select_none.setFixedWidth(50)
        self.btn_select_none.clicked.connect(self._select_no_items)
        top_list_h.addWidget(self.btn_select_none)

        self.btn_select_invert = QPushButton("反选")
        self.btn_select_invert.setFixedWidth(50)
        self.btn_select_invert.clicked.connect(self._invert_selection)
        top_list_h.addWidget(self.btn_select_invert)

        self.btn_detect_downloaded = QPushButton("检测已下载")
        self.btn_detect_downloaded.setToolTip("扫描下载保存目录，自动识别已下载完成的文件并更新勾选状态")
        self.btn_detect_downloaded.clicked.connect(self._detect_downloaded_items_manual)
        top_list_h.addWidget(self.btn_detect_downloaded)

        self.lbl_selected_count = QLabel("已勾选: 0/0")
        self.lbl_selected_count.setStyleSheet("color: #64748b; font-size: 12px; font-weight: bold;")
        top_list_h.addWidget(self.lbl_selected_count)

        right_card_layout.addLayout(top_list_h)

        self.list_pages = QListWidget()
        self.list_pages.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_pages.customContextMenuRequested.connect(self._show_list_context_menu)
        self.list_pages.itemChanged.connect(self._on_item_check_state_changed)
        self.list_pages.currentItemChanged.connect(self._on_list_item_selection_changed)
        right_card_layout.addWidget(self.list_pages, 1)

        # 画质下拉与音频格式设置
        opt_h = QHBoxLayout()
        opt_h.setSpacing(8)
        opt_h.addWidget(QLabel("全局画质:"))
        self.combo_quality = QComboBox()
        self._populate_qualities([])
        opt_h.addWidget(self.combo_quality)

        self.cb_audio_only = QCheckBox("仅提取音频")
        self.cb_audio_only.toggled.connect(self._on_audio_only_toggled)
        opt_h.addWidget(self.cb_audio_only)

        opt_h.addWidget(QLabel("音频格式:"))
        self.combo_audio_format = QComboBox()
        self.combo_audio_format.addItems(["MP3", "M4A", "WAV", "FLAC", "AAC", "OGG"])
        self.combo_audio_format.setEnabled(False)
        self.combo_audio_format.currentIndexChanged.connect(self.save_settings)
        opt_h.addWidget(self.combo_audio_format)

        self.cb_skip_existing = QCheckBox("跳过已存在")
        self.cb_skip_existing.setChecked(True)
        self.cb_skip_existing.setToolTip("开启后，目标目录已存在的完整文件将自动跳过下载")
        opt_h.addWidget(self.cb_skip_existing)

        self.cb_download_danmaku = QCheckBox("下载弹幕(.ass)")
        self.cb_download_danmaku.setChecked(True)
        self.cb_download_danmaku.setToolTip("下载视频时同步获取 B站弹幕流，智能排版防重叠并输出同名 .ass 字幕文件")
        opt_h.addWidget(self.cb_download_danmaku)

        self.btn_open_danmaku_tool = QPushButton("弹幕转 ASS 工具...")
        self.btn_open_danmaku_tool.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_open_danmaku_tool.clicked.connect(self._open_danmaku_converter_dialog)
        opt_h.addWidget(self.btn_open_danmaku_tool)

        opt_h.addStretch()
        right_card_layout.addLayout(opt_h)

        # 单项画质微调与批量应用
        item_opt_h = QHBoxLayout()
        item_opt_h.setSpacing(8)
        item_opt_h.addWidget(QLabel("选中项画质:"))
        self.combo_item_quality = QComboBox()
        self.combo_item_quality.setMinimumWidth(160)
        self.combo_item_quality.addItem("遵循全局画质 (默认)", None)
        for qn_val in (127, 120, 116, 80, 64, 32, 16):
            q_name = QUALITY_MAP.get(qn_val, f"{qn_val}P")
            if qn_val in VIP_QN_SET:
                q_name = f"{q_name} [大会员]"
            self.combo_item_quality.addItem(q_name, qn_val)
        self.combo_item_quality.setEnabled(False)
        self.combo_item_quality.currentIndexChanged.connect(self._on_item_quality_combo_changed)
        item_opt_h.addWidget(self.combo_item_quality)

        self.btn_apply_quality_to_checked = QPushButton("应用至所有勾选项")
        self.btn_apply_quality_to_checked.setEnabled(False)
        self.btn_apply_quality_to_checked.setToolTip("将此处选择的画质批量应用给所有当前勾选的视频/分P")
        self.btn_apply_quality_to_checked.clicked.connect(self._apply_quality_to_checked)
        item_opt_h.addWidget(self.btn_apply_quality_to_checked)

        self.lbl_item_quality_tip = QLabel("(右键列表项也可快捷设置画质)")
        self.lbl_item_quality_tip.setStyleSheet("color: #64748b; font-size: 11px;")
        item_opt_h.addWidget(self.lbl_item_quality_tip)
        item_opt_h.addStretch()
        right_card_layout.addLayout(item_opt_h)

        content_box.addWidget(right_card, 2)
        main_layout.addLayout(content_box, 1)

        # 4. 底部下载设置与执行控制
        bottom_box = QVBoxLayout()
        bottom_box.setSpacing(8)

        # 下载保存路径
        path_h = QHBoxLayout()
        path_h.addWidget(QLabel("下载保存位置:"))
        self.le_save_dir = QLineEdit()
        def_dl = os.path.join(os.path.expanduser("~"), "Downloads", "bilibili")
        self.le_save_dir.setText(def_dl)
        self.le_save_dir.textChanged.connect(lambda: self._detect_downloaded_items(auto_uncheck=False))
        path_h.addWidget(self.le_save_dir, 1)
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_dir)
        path_h.addWidget(btn_browse)
        bottom_box.addLayout(path_h)

        # FFmpeg 检测状态提示
        ffmpeg_p = find_ffmpeg_executable()
        self.lbl_ffmpeg_status = QLabel(
            f"FFmpeg 引擎已就绪: {ffmpeg_p}" if ffmpeg_p else "未检测到 FFmpeg 混流程序，合并功能可能受限"
        )
        self.lbl_ffmpeg_status.setStyleSheet("color: #22c55e; font-size: 11px;" if ffmpeg_p else "color: #eab308; font-size: 11px;")
        bottom_box.addWidget(self.lbl_ffmpeg_status)

        # 进度与控制
        ctl_h = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        ctl_h.addWidget(self.progress_bar, 1)

        self.btn_download = QPushButton("开始下载")
        self.btn_download.setObjectName("primaryBtn")
        self.btn_download.setMinimumWidth(110)
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._start_download)
        ctl_h.addWidget(self.btn_download)

        self.btn_pause_resume = QPushButton("暂停")
        self.btn_pause_resume.setEnabled(False)
        self.btn_pause_resume.setMinimumWidth(75)
        self.btn_pause_resume.clicked.connect(self._toggle_pause_resume)
        ctl_h.addWidget(self.btn_pause_resume)

        self.btn_retry_failed = QPushButton("重试未下载")
        self.btn_retry_failed.setEnabled(False)
        self.btn_retry_failed.setMinimumWidth(95)
        self.btn_retry_failed.setToolTip("自动检测目标目录已下载物件，勾选未下载或失败的项目并开始下载")
        self.btn_retry_failed.clicked.connect(self._retry_failed_items)
        ctl_h.addWidget(self.btn_retry_failed)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setMinimumWidth(65)
        self.btn_cancel.clicked.connect(self._cancel_download)
        ctl_h.addWidget(self.btn_cancel)

        bottom_box.addLayout(ctl_h)

        # 实时日志输出
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setPlaceholderText("下载日志将在此展示...")
        self.txt_log.setFixedHeight(100)
        bottom_box.addWidget(self.txt_log)

        main_layout.addLayout(bottom_box)

    def _get_normalized_cookie(self) -> str:
        text = self.le_cookie.text().strip()
        return normalize_cookie(text)

    def _toggle_cookie_visibility(self):
        if self.le_cookie.echoMode() == QLineEdit.Password:
            self.le_cookie.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_cookie.setText("隐藏")
        else:
            self.le_cookie.setEchoMode(QLineEdit.Password)
            self.btn_toggle_cookie.setText("显示")

    def _paste_cookie_from_clipboard(self):
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        text = cb.text()
        if not text or not text.strip():
            self.txt_log.append("[提示] 当前剪贴板内容为空。")
            QMessageBox.information(self, "剪贴板为空", "当前系统剪贴板中没有任何文本内容。")
            return
        norm = normalize_cookie(text)
        if norm:
            if "SESSDATA=" not in norm:
                self.le_cookie.blockSignals(True)
                self.le_cookie.setText(norm)
                self.le_cookie.blockSignals(False)
                self.api.set_cookie(norm)
                self.save_settings()
                self.txt_log.append("[警告] 从剪贴板提取到了 Cookie，但缺少核心凭据 SESSDATA。")
                QMessageBox.warning(
                    self,
                    "缺少 SESSDATA 凭据",
                    "从剪贴板提取到了部分 Cookie 字段，但未包含核心凭据【SESSDATA】。\n\n"
                    "B站 识别账号和大会员状态必须依赖 SESSDATA，缺少该项会导致无法识别登录与大会员。\n\n"
                    "建议操作：\n"
                    "1. 在浏览器安装 Cookie-Editor 插件，点击「Export」->「Export as JSON」导出全量凭据；\n"
                    "2. 或在浏览器按 F12 -> Application -> Cookies 中复制名称为【SESSDATA】的值粘贴。"
                )
                self._update_account_badge({"is_login": False, "message": "凭据缺少 SESSDATA (未登录)"})
                return
            self.le_cookie.blockSignals(True)
            self.le_cookie.setText(norm)
            self.le_cookie.blockSignals(False)
            self.api.set_cookie(norm)
            self.save_settings()
            self.txt_log.append("[Cookie粘贴] 成功从剪贴板提取并识别 B站凭据，正在自动验证账号状态...")
            self._check_account()
        else:
            self.txt_log.append("[提示] 剪贴板中未识别出有效的 Cookie 或 SESSDATA。")
            QMessageBox.warning(
                self,
                "未识别到有效凭据",
                "剪贴板中的内容未识别出任何有效的 Cookie 键值或 SESSDATA。\n\n"
                "常见原因：\n"
                "1. 复制了网络调度辅助参数（如 bmg_af_sc 边缘节点参数）；\n"
                "2. 剪贴板未包含标准 key=value 键值对或 JSON 导出格式。\n\n"
                "建议操作：\n"
                "在浏览器按 F12 -> Application -> Cookies，双击复制【SESSDATA】对应的值直接粘贴即可。"
            )

    def _on_cookie_text_changed(self):
        raw = self.le_cookie.text()
        # 若用户直接粘贴了 JSON 数组、大括号对象或包含换行符的内容，自动就地清洗为标准单行格式
        if any(marker in raw for marker in ("[", "{", "\n", "\r", '"name"')):
            norm = normalize_cookie(raw)
            if norm and norm != raw:
                self.le_cookie.blockSignals(True)
                self.le_cookie.setText(norm)
                self.le_cookie.blockSignals(False)
        cookie = self._get_normalized_cookie()
        self.api.set_cookie(cookie)
        self.save_settings()

    def _extract_browser_cookies(self):
        self.btn_read_browser.setEnabled(False)
        self.txt_log.append("正在从 Edge / Chrome / Firefox 读取 B站 Cookie...")
        self.browser_worker = BrowserCookieWorker()
        self.browser_worker.finished_signal.connect(self._on_browser_cookies_extracted)
        self.browser_worker.start()

    def _on_browser_cookies_extracted(self, success: bool, res: str, browser_name: str):
        self.btn_read_browser.setEnabled(True)
        if success:
            norm = normalize_cookie(res)
            self.le_cookie.blockSignals(True)
            self.le_cookie.setText(norm)
            self.le_cookie.blockSignals(False)
            self.txt_log.append(f"[Cookie读取成功] 已从 {browser_name} 读取 B站凭据，正在自动验证账号状态...")
            self._check_account()
        else:
            from PySide6.QtWidgets import QApplication
            cb_text = QApplication.clipboard().text()
            has_clipboard_sessdata = bool(cb_text and any(k in cb_text for k in ("SESSDATA", "bili_jct", "DedeUserID")))

            if has_clipboard_sessdata:
                reply = QMessageBox.question(
                    self,
                    "读取浏览器提示",
                    "检测到现代浏览器（Chrome/Edge 127+）启用了系统级 App-Bound 应用绑定加密保护，外部程序无法直接穿透读取数据库。\n\n"
                    "但检测到您的【系统剪贴板】中已包含 B站 Cookie/SESSDATA 凭据，是否直接载入剪贴板内容？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    self._paste_cookie_from_clipboard()
                    return

            self.txt_log.append("[Cookie读取提示] 浏览器数据库受系统安全策略保护 (App-Bound Encryption/独占锁定)")
            msg = (
                "【无法直接穿透浏览器原因】\n"
                "现代 Chromium 浏览器（Chrome 127+ 与新版 Edge）引入了 Windows 原生 App-Bound 绑定加密保护，"
                "且浏览器运行中会对 Cookie 数据库进行独占锁定，禁止任何第三方外部进程静默解密。\n\n"
                "【推荐快捷获取方式】\n"
                "1. 在浏览器安装「Cookie-Editor」插件，打开 B站 页面点击 Export -> Export as JSON；\n"
                "2. 复制后回到本界面，直接点击【从剪贴板粘贴】按钮，程序将 1 秒自动提取并激活大会员！\n"
                "3. 或在浏览器按 F12 -> Application -> Cookies，复制 SESSDATA 的值粘贴进输入框。"
            )
            QMessageBox.information(self, "读取浏览器凭据说明", msg)

    def _check_account(self):
        if self.account_worker and self.account_worker.isRunning():
            return
        raw = self.le_cookie.text().strip()
        if not raw:
            self.txt_log.append("[提示] 请先填入或从剪贴板粘贴 Cookie / SESSDATA 凭据后再检测。")
            QMessageBox.information(self, "提示", "请先填入或从剪贴板粘贴 Cookie 凭据后再进行检测。")
            return

        cookie = normalize_cookie(raw)
        if cookie and cookie != raw:
            self.le_cookie.blockSignals(True)
            self.le_cookie.setText(cookie)
            self.le_cookie.blockSignals(False)

        if not cookie:
            self.txt_log.append("[提示] 输入的内容经清洗后未包含任何有效凭据（仅含网络辅助参数）。")
            QMessageBox.warning(
                self,
                "无效凭据",
                "当前输入的内容仅包含网络调度辅助参数（如 bmg_af_sc / none / sgp），未包含任何有效的 Cookie 键值或 SESSDATA。\n\n"
                "请检查是否从抓包中误复制了辅助字典。建议在浏览器 F12 中直接复制 SESSDATA 的值。"
            )
            self._update_account_badge({"is_login": False, "message": "无效凭据 (未登录)"})
            return

        if "SESSDATA=" not in cookie:
            self.txt_log.append("[警告] 当前填入的内容中未找到核心凭据 SESSDATA，B站 API 将返回未登录状态。")
            QMessageBox.warning(
                self,
                "缺少 SESSDATA 凭据",
                "当前填入的内容中未包含 B站 核心登录凭据【SESSDATA】。\n\n"
                "B站 识别账号和大会员状态必须依赖 SESSDATA，缺少该项会导致始终显示【未登录】。\n\n"
                "请检查是否只复制了单个辅助 Cookie。建议操作：\n"
                "1. 在 Cookie-Editor 插件中点击底部的「Export」->「Export as JSON」导出全量 Cookie；\n"
                "2. 或在浏览器 F12 -> Application -> Cookies 中复制名称为【SESSDATA】的那一行值。"
            )
            self._update_account_badge({"is_login": False, "message": "缺少 SESSDATA (未登录)"})
            return

        self.api.set_cookie(cookie)
        self.btn_check_account.setEnabled(False)
        self.txt_log.append("正在向 B站 API 校验账号与大会员状态...")
        self.account_worker = AccountCheckWorker(self.api)
        self.account_worker.finished_signal.connect(self._on_account_checked)
        self.account_worker.start()

    def _on_account_checked(self, status: dict):
        self.btn_check_account.setEnabled(True)
        self._update_account_badge(status)
        msg = status.get("message", "")
        self.txt_log.append(f"[账号状态] {msg}")

    def _update_account_badge(self, status: dict):
        self.account_status = status
        is_login = status.get("is_login", False)
        vip_status = status.get("vip_status", 0)
        vip_type = status.get("vip_type", 0)
        uname = status.get("uname", "")

        is_vip = bool(is_login and vip_status == 1 and vip_type > 0)

        if is_login:
            if is_vip:
                text = f"[大会员: {uname} (全规格已解锁)]"
                style = (
                    "background-color: rgba(236, 72, 153, 0.15); color: #ec4899; "
                    "padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;"
                )
            else:
                text = f"[已登录: {uname} (最高1080P)]"
                style = (
                    "background-color: rgba(59, 130, 246, 0.15); color: #3b82f6; "
                    "padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;"
                )
        else:
            text = "[未登录 (最高480P)]"
            style = (
                "background-color: rgba(245, 158, 11, 0.15); color: #f59e0b; "
                "padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;"
            )

        self.lbl_account_badge.setText(text)
        self.lbl_account_badge.setStyleSheet(style)

    def _populate_qualities(self, qualities: list):
        current_data = self.combo_quality.currentData()
        self.combo_quality.clear()

        if not qualities:
            qualities = [
                {"qn": 127, "name": "8K 超高清 [大会员]"},
                {"qn": 120, "name": "4K 超清 [大会员]"},
                {"qn": 116, "name": "1080P 60帧"},
                {"qn": 80, "name": "1080P 高清"},
                {"qn": 64, "name": "720P 高清"},
                {"qn": 32, "name": "480P 清晰"},
                {"qn": 16, "name": "360P 流畅"},
            ]

        for q_item in qualities:
            qn = q_item.get("qn")
            name = q_item.get("name", QUALITY_MAP.get(qn, f"{qn}P"))
            if qn in VIP_QN_SET and "[大会员]" not in name:
                name = f"{name} [大会员]"
            self.combo_quality.addItem(name, qn)

        idx = self.combo_quality.findData(current_data)
        if idx >= 0:
            self.combo_quality.setCurrentIndex(idx)
        else:
            idx_80 = self.combo_quality.findData(80)
            if idx_80 >= 0:
                self.combo_quality.setCurrentIndex(idx_80)
            elif self.combo_quality.count() > 0:
                self.combo_quality.setCurrentIndex(0)

        # 同步动态更新单项微调画质下拉选项
        if hasattr(self, "combo_item_quality"):
            cur_item_data = self.combo_item_quality.currentData()
            self.combo_item_quality.blockSignals(True)
            self.combo_item_quality.clear()
            self.combo_item_quality.addItem("遵循全局画质 (默认)", None)
            for q_item in qualities:
                qn = q_item.get("qn")
                name = q_item.get("name", QUALITY_MAP.get(qn, f"{qn}P"))
                if qn in VIP_QN_SET and "[大会员]" not in name:
                    name = f"{name} [大会员]"
                self.combo_item_quality.addItem(name, qn)
            idx_item = self.combo_item_quality.findData(cur_item_data)
            if idx_item >= 0:
                self.combo_item_quality.setCurrentIndex(idx_item)
            else:
                self.combo_item_quality.setCurrentIndex(0)
            self.combo_item_quality.blockSignals(False)

    def cleanup(self):
        for w in (self.account_worker, self.browser_worker, self.parse_worker, self.worker):
            if w and w.isRunning():
                if hasattr(w, "cancel"):
                    w.cancel()
                w.quit()
                w.wait(500)

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def load_config(self):
        cfg = self.config_manager.get_plugin_config("media_downloader", {})
        cookie = cfg.get("cookie", "")
        if cookie:
            self.le_cookie.setText(cookie)
            self.api.set_cookie(self._get_normalized_cookie())
            self.lbl_account_badge.setText("[凭据已载入 (未检测)]")
        else:
            self._update_account_badge({"is_login": False})

        if cfg.get("save_dir"):
            self.le_save_dir.setText(cfg["save_dir"])

        fmt = cfg.get("audio_format", "MP3")
        idx = self.combo_audio_format.findText(fmt.upper())
        if idx >= 0:
            self.combo_audio_format.setCurrentIndex(idx)

        if cfg.get("audio_only"):
            self.cb_audio_only.setChecked(True)
            self.combo_audio_format.setEnabled(True)
            self.combo_quality.setEnabled(False)

    load_settings = load_config

    def save_settings(self):
        cfg = self.config_manager.get_plugin_config("media_downloader", {})
        cfg["cookie"] = normalize_cookie(self.le_cookie.text().strip())
        cfg["save_dir"] = self.le_save_dir.text().strip()
        cfg["audio_format"] = self.combo_audio_format.currentText()
        cfg["audio_only"] = self.cb_audio_only.isChecked()
        self.config_manager.set_plugin_config("media_downloader", cfg)

    save_config = save_settings

    def _browse_dir(self):
        p = QFileDialog.getExistingDirectory(self, "选择下载保存文件夹")
        if p:
            self.le_save_dir.setText(p)
            self.save_settings()

    def _on_audio_only_toggled(self, checked: bool):
        self.combo_audio_format.setEnabled(checked)
        self.combo_quality.setEnabled(not checked)
        self.save_settings()

    def _select_all_items(self):
        self.list_pages.blockSignals(True)
        for i in range(self.list_pages.count()):
            self.list_pages.item(i).setCheckState(Qt.Checked)
        self.list_pages.blockSignals(False)
        self._update_selection_count_label()

    def _select_no_items(self):
        self.list_pages.blockSignals(True)
        for i in range(self.list_pages.count()):
            self.list_pages.item(i).setCheckState(Qt.Unchecked)
        self.list_pages.blockSignals(False)
        self._update_selection_count_label()

    def _invert_selection(self):
        self.list_pages.blockSignals(True)
        for i in range(self.list_pages.count()):
            it = self.list_pages.item(i)
            it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)
        self.list_pages.blockSignals(False)
        self._update_selection_count_label()

    def _on_item_check_state_changed(self, item):
        self._update_selection_count_label()

    def _update_selection_count_label(self):
        total = self.list_pages.count()
        checked = sum(1 for i in range(total) if self.list_pages.item(i).checkState() == Qt.Checked)
        self.lbl_selected_count.setText(f"已勾选: {checked}/{total}")

    def _on_list_item_selection_changed(self, current, previous):
        if not current:
            self.combo_item_quality.setEnabled(False)
            self.btn_apply_quality_to_checked.setEnabled(False)
            return
        data = current.data(Qt.UserRole)
        if isinstance(data, dict):
            pic = data.get("pic")
            if pic and pic != getattr(self, "_current_loaded_pic", None):
                self._current_loaded_pic = pic
                self.img_thread = ImageFetchThread(pic)
                self.img_thread.image_loaded.connect(self._on_cover_loaded)
                self.img_thread.start()
            if data.get("title"):
                self.lbl_title.setText(f"标题: {data['title']}")
            if data.get("owner"):
                self.lbl_up.setText(f"UP主: {data['owner']}")

            # 同步画质单选下拉框
            can_tune = not self.cb_audio_only.isChecked()
            self.combo_item_quality.setEnabled(can_tune)
            self.btn_apply_quality_to_checked.setEnabled(can_tune)
            custom_qn = data.get("qn")
            self.combo_item_quality.blockSignals(True)
            idx = self.combo_item_quality.findData(custom_qn)
            if idx >= 0:
                self.combo_item_quality.setCurrentIndex(idx)
            else:
                self.combo_item_quality.setCurrentIndex(0)
            self.combo_item_quality.blockSignals(False)

    def _on_item_quality_combo_changed(self, index: int):
        current = self.list_pages.currentItem()
        if not current:
            return
        data = current.data(Qt.UserRole)
        if not isinstance(data, dict):
            return
        selected_qn = self.combo_item_quality.currentData()
        data["qn"] = selected_qn
        current.setData(Qt.UserRole, data)
        self._update_list_item_display(current)
        qn_desc = QUALITY_MAP.get(selected_qn, f"{selected_qn}P") if selected_qn else "遵循全局画质"
        self.txt_log.append(f"[画质微调] 《{data.get('part') or data.get('title')}》 指定画质: {qn_desc}")

    def _apply_quality_to_checked(self):
        selected_qn = self.combo_item_quality.currentData()
        qn_desc = QUALITY_MAP.get(selected_qn, f"{selected_qn}P") if selected_qn else "遵循全局画质"
        count = 0
        for i in range(self.list_pages.count()):
            item = self.list_pages.item(i)
            if item.checkState() == Qt.Checked:
                data = item.data(Qt.UserRole)
                if isinstance(data, dict):
                    data["qn"] = selected_qn
                    item.setData(Qt.UserRole, data)
                    self._update_list_item_display(item)
                    count += 1
        self.txt_log.append(f"[画质批量设置] 已将 {count} 项已勾选视频/分P画质设为: {qn_desc}")
        QMessageBox.information(self, "设置完成", f"已成功将 {count} 项已勾选视频/分P的目标画质设为: {qn_desc}")

    def _show_list_context_menu(self, pos):
        item = self.list_pages.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            return

        menu = QMenu(self)
        quality_menu = menu.addMenu("修改此项画质")
        cur_qn = data.get("qn")

        def _make_qn_handler(qn):
            def _handler():
                data["qn"] = qn
                item.setData(Qt.UserRole, data)
                self._update_list_item_display(item)
                if self.list_pages.currentItem() == item:
                    self.combo_item_quality.blockSignals(True)
                    idx = self.combo_item_quality.findData(qn)
                    if idx >= 0:
                        self.combo_item_quality.setCurrentIndex(idx)
                    self.combo_item_quality.blockSignals(False)
                qn_desc = QUALITY_MAP.get(qn, f"{qn}P") if qn else "遵循全局画质"
                self.txt_log.append(f"[画质设置] 已将 《{data.get('part') or data.get('title')}》 目标画质设为: {qn_desc}")
            return _handler

        act_def = quality_menu.addAction("遵循全局画质 (默认)")
        act_def.setCheckable(True)
        act_def.setChecked(cur_qn is None)
        act_def.triggered.connect(_make_qn_handler(None))
        quality_menu.addSeparator()

        for qn_val in (127, 120, 116, 80, 64, 32, 16):
            q_name = QUALITY_MAP.get(qn_val, f"{qn_val}P")
            if qn_val in VIP_QN_SET:
                q_name = f"{q_name} [大会员]"
            act = quality_menu.addAction(q_name)
            act.setCheckable(True)
            act.setChecked(cur_qn == qn_val)
            act.triggered.connect(_make_qn_handler(qn_val))

        menu.addSeparator()

        act_chk = menu.addAction("勾选此项")
        act_chk.triggered.connect(lambda: item.setCheckState(Qt.Checked))
        act_unchk = menu.addAction("取消勾选此项")
        act_unchk.triggered.connect(lambda: item.setCheckState(Qt.Unchecked))

        saved_path = data.get("saved_path")
        if saved_path and os.path.isfile(saved_path):
            menu.addSeparator()
            act_loc = menu.addAction("在资源管理器中定位已下载文件")
            def _open_loc():
                import subprocess
                subprocess.run(["explorer", f"/select,{os.path.normpath(saved_path)}"])
            act_loc.triggered.connect(_open_loc)

        menu.exec(self.list_pages.mapToGlobal(pos))

    def _update_list_item_display(self, item: QListWidgetItem):
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            return
        base_text = data.get("display_title")
        if not base_text:
            raw = item.text()
            for pfx in ("[已下载] ", "[失败] ", "[下载中] "):
                if raw.startswith(pfx):
                    raw = raw[len(pfx):]
            if " [画质: " in raw and raw.endswith("]"):
                raw = raw.split(" [画质: ")[0]
            base_text = raw
            data["display_title"] = base_text
        status = data.get("status", "pending")
        custom_qn = data.get("qn")

        qn_suffix = ""
        if custom_qn:
            q_name = QUALITY_MAP.get(custom_qn, f"{custom_qn}P")
            qn_suffix = f" [画质: {q_name}]"

        if status == "downloaded":
            status_prefix = "[已下载] "
            item.setForeground(QColor("#10b981"))
        elif status == "failed":
            status_prefix = "[失败] "
            item.setForeground(QColor("#ef4444"))
        elif status == "downloading":
            status_prefix = "[下载中] "
            item.setForeground(QColor("#3b82f6"))
        else:
            status_prefix = ""
            item.setForeground(QColor("#1e293b"))

        item.setText(f"{status_prefix}{base_text}{qn_suffix}")
        if data.get("saved_path"):
            item.setToolTip(f"已下载完成: {data['saved_path']}")
        elif data.get("error"):
            item.setToolTip(f"下载失败原因: {data['error']}")
        else:
            item.setToolTip("")

    def _detect_downloaded_items(self, auto_uncheck: bool = True) -> tuple:
        save_dir = self.le_save_dir.text().strip()
        audio_only = self.cb_audio_only.isChecked()
        audio_fmt = self.combo_audio_format.currentText().lower()
        total = self.list_pages.count()
        if total == 0:
            return 0, 0
        downloaded_cnt = 0

        self.list_pages.blockSignals(True)
        for i in range(total):
            item = self.list_pages.item(i)
            data = item.data(Qt.UserRole)
            if isinstance(data, dict):
                is_done, path = check_item_downloaded(data, save_dir, audio_only, audio_fmt)
                if is_done:
                    downloaded_cnt += 1
                    data["status"] = "downloaded"
                    data["saved_path"] = path
                    if auto_uncheck:
                        item.setCheckState(Qt.Unchecked)
                else:
                    if data.get("status") != "failed":
                        data["status"] = "pending"
                item.setData(Qt.UserRole, data)
                self._update_list_item_display(item)
        self.list_pages.blockSignals(False)
        self._update_selection_count_label()
        return downloaded_cnt, total

    def _detect_downloaded_items_manual(self):
        if self.list_pages.count() == 0:
            QMessageBox.information(self, "提示", "请先解析视频或资源列表。")
            return
        dl_cnt, total = self._detect_downloaded_items(auto_uncheck=True)
        self.txt_log.append(f"[检测已下载] 目录检测完成: 共 {total} 项，其中 {dl_cnt} 项已下载，{total - dl_cnt} 项未下载。")
        QMessageBox.information(
            self,
            "检测已下载结果",
            f"目标保存目录检测完成！\n\n已下载完整文件: {dl_cnt} 项 (已自动取消勾选)\n未下载/待下载: {total - dl_cnt} 项\n保存路径: {self.le_save_dir.text()}"
        )

    def _retry_failed_items(self):
        if self.list_pages.count() == 0:
            QMessageBox.information(self, "提示", "请先解析视频或资源列表。")
            return

        self._detect_downloaded_items(auto_uncheck=True)
        checked_cnt = 0
        self.list_pages.blockSignals(True)
        for i in range(self.list_pages.count()):
            item = self.list_pages.item(i)
            data = item.data(Qt.UserRole)
            if isinstance(data, dict):
                if data.get("status") != "downloaded":
                    item.setCheckState(Qt.Checked)
                    checked_cnt += 1
                else:
                    item.setCheckState(Qt.Unchecked)
        self.list_pages.blockSignals(False)
        self._update_selection_count_label()

        if checked_cnt == 0:
            QMessageBox.information(self, "无需重试", "经检测，列表内所有视频均已成功下载，无未完成项！")
            return

        self.txt_log.append(f"[重试未下载] 已自动勾选 {checked_cnt} 项未下载或失败的项目，开始重试下载...")
        self._start_download()

    def _toggle_pause_resume(self):
        if not self.worker or not self.worker.isRunning():
            return
        if getattr(self.worker, "_is_paused", False):
            self.worker.resume()
            self.btn_pause_resume.setText("暂停")
            self.txt_log.append("[操作] 用户恢复了下载任务。")
        else:
            self.worker.pause()
            self.btn_pause_resume.setText("继续")
            self.txt_log.append("[操作] 用户暂停了下载任务。")

    def _parse_video(self):
        raw_text = self.le_url.text().strip()
        if not raw_text:
            QMessageBox.information(self, "提示", "请输入视频链接、BV号、收藏夹链接/FID 或 UP主主页/UID。")
            return

        mode_idx = self.combo_parse_mode.currentIndex()
        self.txt_log.append(f"正在后台解析资源 [{raw_text[:60]}]...")
        self.btn_parse.setEnabled(False)

        self.parse_worker = MediaParseWorker(self.api, raw_text=raw_text, mode_idx=mode_idx)
        self.parse_worker.finished_signal.connect(self._on_video_info_parsed)
        self.parse_worker.start()

    def _on_video_info_parsed(self, info: dict):
        self.btn_parse.setEnabled(True)

        if not info.get("success"):
            QMessageBox.warning(self, "获取失败", info.get("error", "未知错误"))
            self.txt_log.append(f"[解析失败] {info.get('error', '未知错误')}")
            return

        self.current_video_info = info
        title = info.get("title", "-")
        owner = info.get("owner", "-")
        self.lbl_title.setText(f"标题: {title}")
        self.lbl_up.setText(f"UP主: {owner}")

        # 异步加载封面
        if info.get("pic"):
            self._current_loaded_pic = info["pic"]
            self.img_thread = ImageFetchThread(info["pic"])
            self.img_thread.image_loaded.connect(self._on_cover_loaded)
            self.img_thread.start()

        self.list_pages.blockSignals(True)
        self.list_pages.clear()

        info_type = info.get("type", "video")
        if info_type in ("favorite", "space"):
            videos = info.get("videos", [])
            type_name = "收藏夹" if info_type == "favorite" else "UP主投稿"
            self.lbl_list_title.setText(f"{type_name}视频列表 ({len(videos)} 个视频):")
            for i, v in enumerate(videos, 1):
                dur = v.get("duration", 0)
                dur_str = f" [{dur // 60:02d}:{dur % 60:02d}]" if dur else ""
                item_text = f"[{i:02d}] {v.get('title', '')} ({v.get('bvid', '')}){dur_str}"
                item = QListWidgetItem(item_text)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, {
                    "type": "video",
                    "bvid": v.get("bvid", ""),
                    "cid": v.get("cid"),
                    "title": v.get("title", ""),
                    "part": "",
                    "page": v.get("page", 1),
                    "pic": v.get("pic", ""),
                    "owner": v.get("owner", owner),
                    "display_title": item_text,
                    "qn": None,
                    "status": "pending"
                })
                self.list_pages.addItem(item)
        else:
            pages = info.get("pages", [])
            self.lbl_list_title.setText(f"视频分P列表 ({len(pages)} 个分P):")
            for p in pages:
                item_text = f"P{p['page']}: {p.get('part', '')}"
                item = QListWidgetItem(item_text)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, {
                    "type": "video_page",
                    "bvid": info.get("bvid", ""),
                    "cid": p.get("cid"),
                    "title": info.get("title", ""),
                    "part": p.get("part", f"P{p['page']}"),
                    "page": p.get("page", 1),
                    "pic": info.get("pic", ""),
                    "owner": owner,
                    "display_title": item_text,
                    "qn": None,
                    "status": "pending"
                })
                self.list_pages.addItem(item)

        self.list_pages.blockSignals(False)

        # 自动检测本地已下载文件并更新标识
        self._detect_downloaded_items(auto_uncheck=True)

        if self.list_pages.count() > 0:
            self.list_pages.setCurrentRow(0)

        self._update_selection_count_label()

        # 填充画质下拉
        qualities = info.get("available_qualities") or info.get("qualities") or []
        self._populate_qualities(qualities)

        self.btn_download.setEnabled(self.list_pages.count() > 0)
        self.txt_log.append(f"[解析成功] 《{title}》，共解析到 {self.list_pages.count()} 项。")

    def _on_cover_loaded(self, img_bytes: bytes):
        img = QImage()
        if img.loadFromData(img_bytes):
            pix = QPixmap.fromImage(img).scaled(240, 135, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_cover.setPixmap(pix)

    def _start_download(self):
        if not self.current_video_info:
            QMessageBox.information(self, "提示", "请先解析视频或列表。")
            return

        checked_tasks = []
        for i in range(self.list_pages.count()):
            it = self.list_pages.item(i)
            if it.checkState() == Qt.Checked:
                data = it.data(Qt.UserRole)
                if isinstance(data, dict):
                    task_item = dict(data)
                    task_item["list_index"] = i
                    checked_tasks.append(task_item)
                else:
                    checked_tasks.append({
                        "bvid": self.current_video_info.get("bvid", ""),
                        "cid": data,
                        "title": self.current_video_info.get("title", ""),
                        "part": it.text(),
                        "page": i + 1,
                        "qn": None,
                        "status": "pending",
                        "list_index": i
                    })

        if not checked_tasks:
            QMessageBox.information(self, "提示", "请至少勾选一个需要下载的视频。")
            return

        target_qn = self.combo_quality.currentData() or 80
        audio_only = self.cb_audio_only.isChecked()
        audio_fmt = self.combo_audio_format.currentText().lower()
        save_dir = self.le_save_dir.text().strip()
        skip_existing = self.cb_skip_existing.isChecked()

        # 确保最新凭据已同步
        self.api.set_cookie(self._get_normalized_cookie())

        # 会员画质预先提示
        is_target_vip = target_qn in VIP_QN_SET or any(t.get("qn") in VIP_QN_SET for t in checked_tasks if t.get("qn"))
        is_account_vip = bool(self.account_status and self.account_status.get("vip_status") == 1 and self.account_status.get("vip_type", 0) > 0)
        if is_target_vip and not is_account_vip and not audio_only:
            target_qname = self.combo_quality.currentText()
            reply = QMessageBox.question(
                self,
                "清晰度提示",
                f"目标清晰度包含大会员画质，当前账号未开通大会员，服务端将自动降级为可用的最高画质。\n\n是否继续下载选中的 {len(checked_tasks)} 项任务？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                self.txt_log.append("[已取消] 用户取消了下载任务。")
                return

        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_pause_resume.setEnabled(True)
        self.btn_pause_resume.setText("暂停")
        self.btn_retry_failed.setEnabled(False)
        self.progress_bar.setValue(0)

        # 单个任务且已具备流地址时走快速单任务
        if len(checked_tasks) == 1 and self.current_video_info.get("type") not in ("favorite", "space"):
            task = checked_tasks[0]
            self._current_single_task = task
            task_qn = task.get("qn") or target_qn

            if skip_existing:
                is_done, existing_p = check_item_downloaded(task, save_dir, audio_only, audio_fmt)
                if is_done:
                    self.txt_log.append(f"[已存在] 目标文件已存在，跳过下载: {existing_p}")
                    self.progress_bar.setValue(100)
                    self._on_download_finished(True, existing_p)
                    return

            title = str(task.get("title") or "video")
            part = str(task.get("part") or "")
            if not part or part == title or part in title:
                full_title = title
            elif title in part:
                full_title = part
            else:
                full_title = f"{title}_{part}"

            stream_res = None
            if self.current_video_info.get("stream_res") and task.get("cid") == (self.current_video_info.get("pages", [{}])[0].get("cid")):
                stream_res = self.current_video_info["stream_res"]

            if not stream_res or (not audio_only and task_qn != stream_res.get("actual_qn")):
                try:
                    refreshed = self.api.get_play_streams(task.get("bvid", ""), task.get("cid"), qn=task_qn)
                    if refreshed.get("success"):
                        stream_res = refreshed
                        if self.current_video_info and (not self.current_video_info.get("pages") or task.get("cid") == (self.current_video_info.get("pages", [{}])[0].get("cid"))):
                            self.current_video_info["stream_res"] = refreshed
                    else:
                        self.txt_log.append(f"[警告] 获取指定画质(qn={task_qn})失败: {refreshed.get('error', '未知错误')}")
                except Exception as e:
                    self.txt_log.append(f"[警告] 获取指定画质(qn={task_qn})异常: {e}")

            if not stream_res or not stream_res.get("success"):
                err_msg = stream_res.get("error", "获取播放流失败") if stream_res else "获取播放流失败"
                self.txt_log.append(f"[错误] {err_msg}")
                self._on_download_finished(False, err_msg)
                return

            self.worker = MediaDownloadWorker(
                video_url=stream_res.get("video_url", ""),
                audio_url=stream_res.get("audio_url", ""),
                save_dir=save_dir,
                title=full_title,
                audio_only=audio_only,
                audio_format=task.get("audio_format") or audio_fmt,
                cookie=self.api.cookie,
                cid=task.get("cid"),
                download_danmaku=self.cb_download_danmaku.isChecked()
            )
            self.worker.progress_changed.connect(self._on_download_progress)
            self.worker.log_message.connect(self.txt_log.append)
            self.worker.paused_status.connect(self._on_worker_paused_status_changed)
            self.worker.finished_task.connect(self._on_download_finished)
            self.worker.start()
        else:
            self._current_single_task = None
            # 批量执行引擎
            self.worker = BatchMediaDownloadWorker(
                api=self.api,
                tasks=checked_tasks,
                save_dir=save_dir,
                target_qn=target_qn,
                audio_only=audio_only,
                audio_format=audio_fmt,
                cookie=self.api.cookie,
                skip_existing=skip_existing,
                download_danmaku=self.cb_download_danmaku.isChecked()
            )
            self.worker.progress_changed.connect(self._on_download_progress)
            self.worker.log_message.connect(self.txt_log.append)
            self.worker.paused_status.connect(self._on_worker_paused_status_changed)
            self.worker.item_finished.connect(self._on_item_finished)
            self.worker.batch_finished.connect(self._on_batch_download_finished)
            self.worker.start()

    def _open_danmaku_converter_dialog(self):
        from PySide6.QtWidgets import QDialog, QFileDialog, QRadioButton, QButtonGroup
        from .danmaku_to_ass import convert_danmaku_xml_file, fetch_bilibili_danmaku_xml, DanmakuToAssConverter
        dlg = QDialog(self)
        dlg.setWindowTitle("B站弹幕转高精 ASS 字幕转换器")
        dlg.resize(520, 240)
        d_layout = QVBoxLayout(dlg)
        d_layout.setSpacing(12)

        lbl = QLabel("可选择本地已下载的 B站 XML 弹幕文件转换为 ASS，或输入 CID 在线抓取生成:")
        lbl.setWordWrap(True)
        d_layout.addWidget(lbl)

        rb_file = QRadioButton("选择本地 XML 弹幕文件")
        rb_cid = QRadioButton("输入 B站视频 CID 在线转换")
        rb_file.setChecked(True)
        bg = QButtonGroup(dlg)
        bg.addButton(rb_file)
        bg.addButton(rb_cid)
        m_row = QHBoxLayout()
        m_row.addWidget(rb_file)
        m_row.addWidget(rb_cid)
        d_layout.addLayout(m_row)

        input_row = QHBoxLayout()
        le_input = QLineEdit()
        le_input.setPlaceholderText("请选择 XML 文件路径...")
        input_row.addWidget(le_input, 1)
        btn_browse = QPushButton("浏览...")
        input_row.addWidget(btn_browse)
        d_layout.addLayout(input_row)

        def _on_mode_toggled():
            if rb_file.isChecked():
                le_input.setPlaceholderText("请选择 XML 文件路径...")
                btn_browse.setVisible(True)
            else:
                le_input.setPlaceholderText("请输入纯数字 CID (如 12345678)...")
                btn_browse.setVisible(False)

        rb_file.toggled.connect(_on_mode_toggled)
        rb_cid.toggled.connect(_on_mode_toggled)

        def _browse_xml():
            p, _ = QFileDialog.getOpenFileName(dlg, "选择 XML 弹幕文件", "", "XML Files (*.xml);;All Files (*.*)")
            if p:
                le_input.setText(p)

        btn_browse.clicked.connect(_browse_xml)

        btn_convert = QPushButton("立即转换并导出 .ass")
        btn_convert.setObjectName("primaryBtn")
        d_layout.addWidget(btn_convert)

        def _do_convert():
            val = le_input.text().strip()
            if not val:
                QMessageBox.warning(dlg, "提示", "请输入有效的文件路径或 CID。")
                return
            if rb_file.isChecked():
                if not os.path.isfile(val):
                    QMessageBox.warning(dlg, "错误", f"指定的文件不存在: {val}")
                    return
                out_ass, _ = QFileDialog.getSaveFileName(dlg, "保存 ASS 字幕文件", os.path.splitext(val)[0] + ".ass", "ASS Subtitles (*.ass)")
                if not out_ass:
                    return
                ok, msg = convert_danmaku_xml_file(val, out_ass)
                if ok:
                    QMessageBox.information(dlg, "成功", f"弹幕已成功转换为高精 ASS 字幕！\n{out_ass}")
                    dlg.accept()
                else:
                    QMessageBox.critical(dlg, "失败", f"转换失败: {msg}")
            else:
                try:
                    cid_int = int(val)
                except ValueError:
                    QMessageBox.warning(dlg, "错误", "CID 必须为纯数字！")
                    return
                out_ass, _ = QFileDialog.getSaveFileName(dlg, "保存 ASS 字幕文件", f"danmaku_{cid_int}.ass", "ASS Subtitles (*.ass)")
                if not out_ass:
                    return
                xml_content = fetch_bilibili_danmaku_xml(cid_int, sessdata=self.api.cookie)
                if not xml_content:
                    QMessageBox.critical(dlg, "失败", f"未能从 B站拉取到 CID {cid_int} 的弹幕数据。")
                    return
                conv = DanmakuToAssConverter()
                ass_text = conv.convert_to_ass(xml_content, title=f"CID_{cid_int}")
                with open(out_ass, "w", encoding="utf-8-sig") as f_out:
                    f_out.write(ass_text)
                QMessageBox.information(dlg, "成功", f"弹幕已成功在线抓取并导出为 ASS！\n{out_ass}")
                dlg.accept()

        btn_convert.clicked.connect(_do_convert)
        dlg.exec()

    def _cancel_download(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.btn_pause_resume.setEnabled(False)
            self.btn_pause_resume.setText("暂停")
            self.btn_download.setEnabled(True)
            self.btn_retry_failed.setEnabled(True)
            self.txt_log.append("[已取消] 正在终止当前下载任务...")

    def _on_download_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"{pct}% - {msg}")

    def _on_download_finished(self, success: bool, res_msg: str):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_pause_resume.setEnabled(False)
        self.btn_pause_resume.setText("暂停")

        # 更新单任务对应的列表项状态
        if hasattr(self, "_current_single_task") and self._current_single_task:
            task = self._current_single_task
            target_item = None
            row_idx = task.get("list_index")
            if row_idx is not None and 0 <= row_idx < self.list_pages.count():
                target_item = self.list_pages.item(row_idx)
            if not target_item:
                for i in range(self.list_pages.count()):
                    it = self.list_pages.item(i)
                    c_data = it.data(Qt.UserRole)
                    if isinstance(c_data, dict) and task.get("cid") and c_data.get("cid") == task.get("cid"):
                        target_item = it
                        break
            if target_item:
                data = target_item.data(Qt.UserRole)
                if isinstance(data, dict):
                    if success:
                        data["status"] = "downloaded"
                        data["saved_path"] = res_msg
                        data.pop("error", None)
                        target_item.setCheckState(Qt.Unchecked)
                    else:
                        data["status"] = "failed"
                        data["error"] = res_msg
                        target_item.setCheckState(Qt.Checked)
                    target_item.setData(Qt.UserRole, data)
                    self._update_list_item_display(target_item)
                    self._update_selection_count_label()
            self._current_single_task = None

        if success:
            QMessageBox.information(self, "下载完成", f"已成功下载至:\n{res_msg}")
        else:
            self.btn_retry_failed.setEnabled(True)
            QMessageBox.warning(self, "下载提示", f"任务未完成: {res_msg}\n您可以点击【重试未下载】重新下载。")

    def _on_item_finished(self, idx: int, total: int, ok: bool, res: str):
        target_item = None
        task = None
        if self.worker and hasattr(self.worker, "tasks") and isinstance(self.worker.tasks, list):
            if 0 <= idx - 1 < len(self.worker.tasks):
                task = self.worker.tasks[idx - 1]

        if task and isinstance(task, dict):
            row_idx = task.get("list_index")
            if row_idx is not None and 0 <= row_idx < self.list_pages.count():
                candidate = self.list_pages.item(row_idx)
                c_data = candidate.data(Qt.UserRole)
                if isinstance(c_data, dict) and (c_data.get("cid") == task.get("cid") or c_data.get("part") == task.get("part")):
                    target_item = candidate

            if not target_item:
                for i in range(self.list_pages.count()):
                    candidate = self.list_pages.item(i)
                    c_data = candidate.data(Qt.UserRole)
                    if isinstance(c_data, dict):
                        if task.get("cid") and c_data.get("cid") == task.get("cid"):
                            target_item = candidate
                            break
                        if task.get("page") and c_data.get("page") == task.get("page") and c_data.get("bvid") == task.get("bvid"):
                            target_item = candidate
                            break

        if not target_item and 1 <= idx <= self.list_pages.count():
            target_item = self.list_pages.item(idx - 1)

        if target_item:
            data = target_item.data(Qt.UserRole)
            if isinstance(data, dict):
                if ok:
                    data["status"] = "downloaded"
                    data["saved_path"] = res
                    data.pop("error", None)
                    target_item.setCheckState(Qt.Unchecked)
                else:
                    data["status"] = "failed"
                    data["error"] = res
                    target_item.setCheckState(Qt.Checked)
                    self.btn_retry_failed.setEnabled(True)
                target_item.setData(Qt.UserRole, data)
                self._update_list_item_display(target_item)
                self._update_selection_count_label()

    def _on_batch_download_finished(self, success_cnt: int, fail_cnt: int, saved_paths: list):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_pause_resume.setEnabled(False)
        self.btn_pause_resume.setText("暂停")
        self._detect_downloaded_items(auto_uncheck=True)
        if fail_cnt == 0:
            QMessageBox.information(
                self,
                "下载完成",
                f"已全部下载完成！共成功下载 {success_cnt} 项。\n保存文件夹:\n{self.le_save_dir.text()}"
            )
        else:
            self.btn_retry_failed.setEnabled(True)
            self.txt_log.append(f"[提示] 检测到有 {fail_cnt} 项未完成/失败，可点击【重试未下载】按钮进行快速断点重试。")
            QMessageBox.warning(
                self,
                "批量下载提示",
                f"批量任务结束。\n成功: {success_cnt} 项\n失败: {fail_cnt} 项\n\n已自动为您勾选未完成/失败项，可直接点击【重试未下载】重新下载。"
            )

    def _on_worker_paused_status_changed(self, is_paused: bool):
        self.btn_pause_resume.setText("继续" if is_paused else "暂停")

