"""
B站媒体下载器 - 现代化 GUI 界面
"""

import os
import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QProgressBar, QTextEdit,
    QFileDialog, QMessageBox, QGroupBox, QListWidget, QListWidgetItem
)
from toolbox.core.config_manager import ConfigManager
from .api import BiliApiClient, QUALITY_MAP, VIP_QN_SET, normalize_cookie
from .downloader import MediaDownloadWorker, BatchMediaDownloadWorker, find_ffmpeg_executable


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

    def __init__(self, api: BiliApiClient, target_type: str, target_id: str):
        super().__init__()
        self.api = api
        self.target_type = target_type  # "video", "favorite", "space"
        self.target_id = target_id

    def run(self):
        try:
            if self.target_type == "favorite":
                res = self.api.get_favorite_videos(self.target_id)
                self.finished_signal.emit(res)
            elif self.target_type == "space":
                res = self.api.get_space_videos(self.target_id)
                self.finished_signal.emit(res)
            else:
                info = self.api.get_video_info(self.target_id)
                if info.get("success") and info.get("pages"):
                    pages = info.get("pages")
                    first_page = pages[0] if isinstance(pages, list) and pages and isinstance(pages[0], dict) else {}
                    first_cid = first_page.get("cid")
                    if first_cid:
                        stream_res = self.api.get_play_streams(self.target_id, first_cid)
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

        self.lbl_selected_count = QLabel("已勾选: 0/0")
        self.lbl_selected_count.setStyleSheet("color: #64748b; font-size: 12px; font-weight: bold;")
        top_list_h.addWidget(self.lbl_selected_count)

        right_card_layout.addLayout(top_list_h)

        self.list_pages = QListWidget()
        self.list_pages.itemChanged.connect(self._on_item_check_state_changed)
        self.list_pages.currentItemChanged.connect(self._on_list_item_selection_changed)
        right_card_layout.addWidget(self.list_pages, 1)

        # 画质下拉与音频格式设置
        opt_h = QHBoxLayout()
        opt_h.setSpacing(8)
        opt_h.addWidget(QLabel("目标画质:"))
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

        opt_h.addStretch()
        right_card_layout.addLayout(opt_h)

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
        self.btn_download.setMinimumWidth(130)
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._start_download)
        ctl_h.addWidget(self.btn_download)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
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

    def _parse_video(self):
        raw_text = self.le_url.text().strip()
        if not raw_text:
            QMessageBox.information(self, "提示", "请输入视频链接、BV号、收藏夹链接/FID 或 UP主主页/UID。")
            return

        mode_idx = self.combo_parse_mode.currentIndex()
        target_type = "unknown"
        target_id = None

        if mode_idx == 1:
            target_type = "video"
            target_id = self.api.extract_bvid(raw_text)
        elif mode_idx == 2:
            target_type = "favorite"
            target_id = self.api.extract_fav_id(raw_text)
        elif mode_idx == 3:
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
            QMessageBox.warning(self, "解析错误", "未能从输入中提取出合法的 ID 或链接，请核对输入格式。")
            return

        type_names = {"video": "视频", "favorite": "收藏夹", "space": "UP主主页"}
        desc = type_names.get(target_type, "资源")
        self.txt_log.append(f"正在从 B站 API 解析{desc} [{target_id}]...")
        self.btn_parse.setEnabled(False)

        self.parse_worker = MediaParseWorker(self.api, target_type, target_id)
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
                    "owner": v.get("owner", owner)
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
                    "owner": owner
                })
                self.list_pages.addItem(item)

        self.list_pages.blockSignals(False)

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
                    checked_tasks.append(data)
                else:
                    checked_tasks.append({
                        "bvid": self.current_video_info.get("bvid", ""),
                        "cid": data,
                        "title": self.current_video_info.get("title", ""),
                        "part": it.text(),
                        "page": i + 1
                    })

        if not checked_tasks:
            QMessageBox.information(self, "提示", "请至少勾选一个需要下载的视频。")
            return

        target_qn = self.combo_quality.currentData() or 80
        audio_only = self.cb_audio_only.isChecked()
        audio_fmt = self.combo_audio_format.currentText().lower()
        save_dir = self.le_save_dir.text().strip()

        # 确保最新凭据已同步
        self.api.set_cookie(self._get_normalized_cookie())

        # 会员画质预先提示
        is_target_vip = target_qn in VIP_QN_SET
        is_account_vip = bool(self.account_status and self.account_status.get("vip_status") == 1 and self.account_status.get("vip_type", 0) > 0)
        if is_target_vip and not is_account_vip and not audio_only:
            target_qname = self.combo_quality.currentText()
            reply = QMessageBox.question(
                self,
                "清晰度提示",
                f"目标清晰度 [{target_qname}] 需要大会员权限，当前账号未开通大会员，服务端将自动降级为可用的最高画质。\n\n是否继续批量下载选中的 {len(checked_tasks)} 项任务？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                self.txt_log.append("[已取消] 用户取消了批量下载任务。")
                return

        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)

        # 单个任务且已具备流地址时走快速单任务
        if len(checked_tasks) == 1 and self.current_video_info.get("type") not in ("favorite", "space") and self.current_video_info.get("stream_res") and checked_tasks[0].get("cid") == (self.current_video_info.get("pages", [{}])[0].get("cid")):
            task = checked_tasks[0]
            stream_res = self.current_video_info["stream_res"]
            if not audio_only and target_qn != stream_res.get("actual_qn"):
                try:
                    refreshed = self.api.get_play_streams(task.get("bvid", ""), task.get("cid"), qn=target_qn)
                    if refreshed.get("success"):
                        stream_res = refreshed
                        self.current_video_info["stream_res"] = refreshed
                    else:
                        self.txt_log.append(f"[警告] 重新获取画质(qn={target_qn})失败，将使用初始流: {refreshed.get('error', '未知错误')}")
                except Exception as e:
                    self.txt_log.append(f"[警告] 重新获取画质(qn={target_qn})异常: {e}，将使用初始流")

            title = str(task.get("title") or "video")
            part = str(task.get("part") or "")
            if not part or part == title or part in title:
                full_title = title
            elif title in part:
                full_title = part
            else:
                full_title = f"{title}_{part}"

            self.worker = MediaDownloadWorker(
                video_url=stream_res.get("video_url", ""),
                audio_url=stream_res.get("audio_url", ""),
                save_dir=save_dir,
                title=full_title,
                audio_only=audio_only,
                audio_format=audio_fmt,
                cookie=self.api.cookie
            )
            self.worker.progress_changed.connect(self._on_download_progress)
            self.worker.log_message.connect(self.txt_log.append)
            self.worker.finished_task.connect(self._on_download_finished)
            self.worker.start()
        else:
            # 批量执行引擎
            self.worker = BatchMediaDownloadWorker(
                api=self.api,
                tasks=checked_tasks,
                save_dir=save_dir,
                target_qn=target_qn,
                audio_only=audio_only,
                audio_format=audio_fmt,
                cookie=self.api.cookie
            )
            self.worker.progress_changed.connect(self._on_download_progress)
            self.worker.log_message.connect(self.txt_log.append)
            self.worker.batch_finished.connect(self._on_batch_download_finished)
            self.worker.start()

    def _cancel_download(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.txt_log.append("[已取消] 正在终止当前下载任务...")

    def _on_download_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"{pct}% - {msg}")

    def _on_download_finished(self, success: bool, res_msg: str):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if success:
            QMessageBox.information(self, "下载完成", f"已成功下载至:\n{res_msg}")
        else:
            QMessageBox.warning(self, "下载提示", f"任务未完成: {res_msg}")

    def _on_batch_download_finished(self, success_cnt: int, fail_cnt: int, saved_paths: list):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if fail_cnt == 0:
            QMessageBox.information(
                self,
                "下载完成",
                f"已全部下载完成！共成功下载 {success_cnt} 项。\n保存文件夹:\n{self.le_save_dir.text()}"
            )
        else:
            QMessageBox.warning(
                self,
                "批量下载提示",
                f"批量任务结束。\n成功: {success_cnt} 项\n失败: {fail_cnt} 项\n保存文件夹:\n{self.le_save_dir.text()}"
            )
