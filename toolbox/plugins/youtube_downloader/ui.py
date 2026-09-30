"""
YouTube 视频下载器 - UI 界面
提供现代化视频解析、画质自选、代理配置与下载混流面板。
"""

import os
import subprocess
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QProgressBar, QTextEdit,
    QFileDialog, QGroupBox, QApplication
)
from PySide6.QtGui import QPixmap

from toolbox.core.config_manager import ConfigManager
from toolbox.ui.icons import get_icon, get_pixmap
from .engine import VideoInfoExtractor, YoutubeDownloadWorker


class YoutubeDownloaderWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = ConfigManager()
        self.extractor: Optional[VideoInfoExtractor] = None
        self.worker: Optional[YoutubeDownloadWorker] = None
        self.video_data: Optional[dict] = None

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)

        # 1. 顶部标题栏
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("youtube", color="#ef4444", size=26))
        header_layout.addWidget(icon_lbl)

        title_lbl = QLabel("YouTube 视频解析与下载")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        badge_lbl = QLabel("yt-dlp + FFmpeg 引擎")
        badge_lbl.setFixedHeight(22)
        badge_lbl.setStyleSheet(
            "background-color: #ef4444; color: #ffffff; border-radius: 9px; "
            "padding: 2px 8px; font-size: 11px; font-weight: bold;"
        )
        header_layout.addWidget(badge_lbl, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 2. 链接输入与代理配置卡片
        input_group = QGroupBox("视频链接与网络配置")
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(10)

        url_row = QHBoxLayout()
        url_row.setSpacing(8)

        lbl_url = QLabel("视频链接:")
        lbl_url.setFixedWidth(70)
        url_row.addWidget(lbl_url)

        self.le_url = QLineEdit()
        self.le_url.setPlaceholderText("在此粘贴 YouTube 视频链接 (例如: https://www.youtube.com/watch?v=...)")
        self.le_url.returnPressed.connect(self._start_analyze)
        url_row.addWidget(self.le_url, 1)

        self.btn_paste = QPushButton("粘贴")
        self.btn_paste.setIcon(get_icon("copy", size=14))
        self.btn_paste.clicked.connect(self._paste_clipboard)
        url_row.addWidget(self.btn_paste)

        self.btn_analyze = QPushButton("解析视频")
        self.btn_analyze.setObjectName("primaryBtn")
        self.btn_analyze.setIcon(get_icon("search", size=14))
        self.btn_analyze.clicked.connect(self._start_analyze)
        url_row.addWidget(self.btn_analyze)

        input_layout.addLayout(url_row)

        # 代理设置行
        proxy_row = QHBoxLayout()
        proxy_row.setSpacing(8)

        self.cb_use_proxy = QCheckBox("启用代理")
        saved_proxy_enabled = self.config.get("youtube_use_proxy", False)
        self.cb_use_proxy.setChecked(saved_proxy_enabled)
        self.cb_use_proxy.stateChanged.connect(self._on_proxy_toggle)
        proxy_row.addWidget(self.cb_use_proxy)

        self.le_proxy = QLineEdit()
        default_proxy = self.config.get("youtube_proxy_addr", "")
        if not default_proxy:
            env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY")
            default_proxy = env_proxy or "http://127.0.0.1:7890"
        self.le_proxy.setText(default_proxy)
        self.le_proxy.setPlaceholderText("代理地址，例如 http://127.0.0.1:7890 或 socks5://127.0.0.1:10808")
        self.le_proxy.setEnabled(saved_proxy_enabled)
        self.le_proxy.editingFinished.connect(lambda: self.config.set("youtube_proxy_addr", self.le_proxy.text().strip()))
        proxy_row.addWidget(self.le_proxy, 1)

        input_layout.addLayout(proxy_row)

        # Cookie 与凭据设置行 (解除人机验证)
        cookie_row = QHBoxLayout()
        cookie_row.setSpacing(8)

        self.cb_use_cookie = QCheckBox("启用 Cookie / 凭据 (应对反爬验证)")
        self.cb_use_cookie.stateChanged.connect(self._on_cookie_toggle)
        cookie_row.addWidget(self.cb_use_cookie)

        self.combo_cookie_src = QComboBox()
        self.combo_cookie_src.addItems(["本地 cookies.txt 文件", "读取 Edge 浏览器", "读取 Chrome 浏览器", "读取 Firefox 浏览器"])
        self.combo_cookie_src.setEnabled(False)
        self.combo_cookie_src.currentIndexChanged.connect(self._on_cookie_src_changed)
        cookie_row.addWidget(self.combo_cookie_src)

        self.le_cookie_path = QLineEdit()
        self.le_cookie_path.setPlaceholderText("选择或输入 cookies.txt 路径...")
        self.le_cookie_path.setEnabled(False)
        cookie_row.addWidget(self.le_cookie_path, 1)

        self.btn_browse_cookie = QPushButton("浏览...")
        self.btn_browse_cookie.setEnabled(False)
        self.btn_browse_cookie.clicked.connect(self._browse_cookie_file)
        cookie_row.addWidget(self.btn_browse_cookie)

        input_layout.addLayout(cookie_row)
        layout.addWidget(input_group)

        # 3. 视频信息卡片 (默认隐藏，解析成功后显示)
        self.info_group = QGroupBox("视频信息与画质挑选")
        info_layout = QHBoxLayout(self.info_group)
        info_layout.setSpacing(16)

        info_details_layout = QVBoxLayout()
        info_details_layout.setSpacing(6)

        self.lbl_video_title = QLabel("标题: 等待解析...")
        self.lbl_video_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.lbl_video_title.setWordWrap(True)
        info_details_layout.addWidget(self.lbl_video_title)

        meta_row = QHBoxLayout()
        self.lbl_author = QLabel("发布者: -")
        self.lbl_author.setStyleSheet("color: #94a3b8; font-size: 12px;")
        meta_row.addWidget(self.lbl_author)

        self.lbl_duration = QLabel("时长: -")
        self.lbl_duration.setStyleSheet("color: #94a3b8; font-size: 12px;")
        meta_row.addWidget(self.lbl_duration)
        meta_row.addStretch()
        info_details_layout.addLayout(meta_row)

        # 画质选择下拉框
        opt_row = QHBoxLayout()
        opt_row.setSpacing(8)
        lbl_quality = QLabel("下载画质:")
        lbl_quality.setFixedWidth(65)
        opt_row.addWidget(lbl_quality)

        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["最佳画质 (自动混流最高)", "1080P 高清", "720P 高清", "480P 标清", "仅提取音频 (MP3 - 320k)", "仅提取音频 (M4A)"])
        opt_row.addWidget(self.combo_quality, 1)
        info_details_layout.addLayout(opt_row)

        info_layout.addLayout(info_details_layout, 1)
        layout.addWidget(self.info_group)

        # 4. 保存路径设置
        path_group = QGroupBox("保存设置")
        path_layout = QHBoxLayout(path_group)
        path_layout.setSpacing(8)

        lbl_save = QLabel("保存目录:")
        lbl_save.setFixedWidth(65)
        path_layout.addWidget(lbl_save)

        self.le_save_dir = QLineEdit()
        default_dir = self.config.get("youtube_save_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        self.le_save_dir.setText(default_dir)
        path_layout.addWidget(self.le_save_dir, 1)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setIcon(get_icon("folder", size=14))
        self.btn_browse.clicked.connect(self._browse_save_dir)
        path_layout.addWidget(self.btn_browse)

        self.btn_open_dir = QPushButton("打开目录")
        self.btn_open_dir.setIcon(get_icon("folder", size=14))
        self.btn_open_dir.clicked.connect(self._open_save_dir)
        path_layout.addWidget(self.btn_open_dir)

        layout.addWidget(path_group)

        # 5. 操作控制与进度
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_download = QPushButton("开始下载")
        self.btn_download.setObjectName("primaryBtn")
        self.btn_download.setIcon(get_icon("download", size=16))
        self.btn_download.setFixedHeight(36)
        self.btn_download.clicked.connect(self._start_download)
        action_layout.addWidget(self.btn_download, 1)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("dangerBtn")
        self.btn_cancel.setIcon(get_icon("clear", size=14))
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_download)
        action_layout.addWidget(self.btn_cancel)

        layout.addLayout(action_layout)

        # 进度与状态反馈
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        status_row = QHBoxLayout()
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        status_row.addWidget(self.lbl_status)

        self.lbl_speed = QLabel("")
        self.lbl_speed.setStyleSheet("color: #3b82f6; font-size: 12px; font-weight: 500;")
        self.lbl_speed.setAlignment(Qt.AlignRight)
        status_row.addWidget(self.lbl_speed)

        layout.addLayout(status_row)

        # 6. 日志控制台
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(110)
        self.log_console.setPlaceholderText("任务运行日志...")
        layout.addWidget(self.log_console)

    def _paste_clipboard(self):
        cb = QApplication.clipboard()
        text = cb.text().strip()
        if text:
            self.le_url.setText(text)

    def _on_proxy_toggle(self, state):
        enabled = bool(state)
        self.le_proxy.setEnabled(enabled)
        self.config.set("youtube_use_proxy", enabled)

    def _get_active_proxy(self) -> Optional[str]:
        if self.cb_use_proxy.isChecked():
            return self.le_proxy.text().strip() or None
        return None

    def _on_cookie_toggle(self, state):
        enabled = bool(state)
        self.combo_cookie_src.setEnabled(enabled)
        is_file = (self.combo_cookie_src.currentIndex() == 0)
        self.le_cookie_path.setEnabled(enabled and is_file)
        self.btn_browse_cookie.setEnabled(enabled and is_file)

    def _on_cookie_src_changed(self, idx):
        is_file = (idx == 0)
        self.le_cookie_path.setEnabled(self.cb_use_cookie.isChecked() and is_file)
        self.btn_browse_cookie.setEnabled(self.cb_use_cookie.isChecked() and is_file)

    def _browse_cookie_file(self):
        chosen, _ = QFileDialog.getOpenFileName(self, "选择 YouTube cookies.txt 文件", "", "Cookie Files (*.txt);;All Files (*)")
        if chosen:
            self.le_cookie_path.setText(chosen)

    def _get_cookie_args(self) -> tuple:
        if not self.cb_use_cookie.isChecked():
            return None, None
        idx = self.combo_cookie_src.currentIndex()
        if idx == 0:
            cfile = self.le_cookie_path.text().strip()
            return (cfile if os.path.isfile(cfile) else None), None
        elif idx == 1:
            return None, "edge"
        elif idx == 2:
            return None, "chrome"
        elif idx == 3:
            return None, "firefox"
        return None, None

    def _start_analyze(self):
        url = self.le_url.text().strip()
        if not url:
            self._log("[提示] 请先输入有效的 YouTube 视频链接。")
            return

        self.btn_analyze.setEnabled(False)
        self.lbl_status.setText("正在连接并解析视频信息...")
        self._log(f"[解析] 正在连接解析视频信息: {url}")

        cookie_file, browser_name = self._get_cookie_args()
        self.extractor = VideoInfoExtractor(
            url,
            proxy=self._get_active_proxy(),
            cookie_file=cookie_file,
            browser_cookies=browser_name
        )
        self.extractor.success.connect(self._on_analyze_success)
        self.extractor.error.connect(self._on_analyze_error)
        self.extractor.start()

    def _on_analyze_success(self, data: dict):
        self.btn_analyze.setEnabled(True)
        self.video_data = data
        self.lbl_status.setText("视频信息解析完成！")

        title = data.get("title", "")
        uploader = data.get("uploader", "未知")
        duration = data.get("duration", 0)
        mins, secs = divmod(duration, 60)
        hours, mins = divmod(mins, 60)
        dur_str = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"

        self.lbl_video_title.setText(f"标题: {title}")
        self.lbl_author.setText(f"发布者: {uploader}")
        self.lbl_duration.setText(f"时长: {dur_str}")

        # 动态刷新画质列表
        resolutions = data.get("resolutions", [])
        self.combo_quality.clear()
        self.combo_quality.addItem("最佳画质 (自动混流最高)", "best")
        for res in resolutions:
            self.combo_quality.addItem(f"{res}P 高清", res)
        self.combo_quality.addItem("仅提取音频 (MP3 - 320k)", "audio_mp3")
        self.combo_quality.addItem("仅提取音频 (M4A)", "audio_m4a")

        self._log(f"[解析成功] 标题: {title} | 时长: {dur_str} | 可选画质数: {len(resolutions)}")

    def _on_analyze_error(self, err: str):
        self.btn_analyze.setEnabled(True)
        self.lbl_status.setText("解析失败")
        self._log(f"[错误] {err}")

    def _browse_save_dir(self):
        cur = self.le_save_dir.text()
        chosen = QFileDialog.getExistingDirectory(self, "选择保存文件夹", cur)
        if chosen:
            self.le_save_dir.setText(chosen)
            self.config.set("youtube_save_dir", chosen)

    def _open_save_dir(self):
        target = self.le_save_dir.text().strip()
        if os.path.exists(target):
            subprocess.Popen(f'explorer "{os.path.normpath(target)}"')
        else:
            self._log("[提示] 保存目录不存在。")

    def _start_download(self):
        url = self.le_url.text().strip()
        if not url:
            self._log("[提示] 请先输入视频链接。")
            return

        save_dir = self.le_save_dir.text().strip()
        if not save_dir:
            self._log("[提示] 请指定保存目录。")
            return

        quality_data = self.combo_quality.currentData()
        audio_only = False
        audio_format = "mp3"
        target_res = None

        if quality_data == "audio_mp3":
            audio_only = True
            audio_format = "mp3"
        elif quality_data == "audio_m4a":
            audio_only = True
            audio_format = "m4a"
        elif isinstance(quality_data, int):
            target_res = quality_data

        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("任务启动中...")

        cookie_file, browser_name = self._get_cookie_args()
        self.worker = YoutubeDownloadWorker(
            url=url,
            save_dir=save_dir,
            quality_mode="custom" if target_res else "best",
            target_resolution=target_res,
            audio_only=audio_only,
            audio_format=audio_format,
            proxy=self._get_active_proxy(),
            cookie_file=cookie_file,
            browser_cookies=browser_name
        )
        self.worker.progress_changed.connect(self._on_progress_changed)
        self.worker.speed_changed.connect(self.lbl_speed.setText)
        self.worker.log_message.connect(self._log)
        self.worker.finished_task.connect(self._on_download_finished)
        self.worker.start()

    def _cancel_download(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_status.setText("正在取消...")
            self.btn_cancel.setEnabled(False)

    def _on_progress_changed(self, pct: int, status_text: str):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(status_text)

    def _on_download_finished(self, success: bool, msg: str):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if success:
            self.progress_bar.setValue(100)
            self.lbl_status.setText("下载完成！")
            self._log(f"[成功] 任务完成: {msg}")
        else:
            self.lbl_status.setText(f"失败: {msg}")

    def _log(self, text: str):
        self.log_console.append(text)

    def handle_initial_paths(self, paths: list):
        if paths:
            first = str(paths[0]).strip()
            self.le_url.setText(first)

    def load_settings(self):
        cfg = self.config.get_plugin_config("youtube_downloader", {})
        self.cb_use_proxy.setChecked(cfg.get("use_proxy", False))
        if "proxy_addr" in cfg and cfg["proxy_addr"]:
            self.le_proxy.setText(cfg["proxy_addr"])
        else:
            # 自动探测系统 Windows 代理
            try:
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    p_en, _ = winreg.QueryValueEx(key, "ProxyEnable")
                    if p_en == 1:
                        p_srv, _ = winreg.QueryValueEx(key, "ProxyServer")
                        if p_srv:
                            addr = p_srv.split(";")[0].replace("http=", "").replace("https=", "").strip()
                            if addr:
                                self.le_proxy.setText(f"http://{addr}" if not addr.startswith("http") else addr)
                                self.cb_use_proxy.setChecked(True)
            except Exception:
                pass

        if hasattr(self, "le_save_dir") and "save_dir" in cfg:
            self.le_save_dir.setText(cfg["save_dir"])

        if "use_cookie" in cfg:
            self.cb_use_cookie.setChecked(cfg["use_cookie"])
        if "cookie_src" in cfg:
            self.combo_cookie_src.setCurrentIndex(cfg["cookie_src"])
        if "cookie_path" in cfg:
            self.le_cookie_path.setText(cfg["cookie_path"])

    def save_settings(self):
        cfg = {
            "use_proxy": self.cb_use_proxy.isChecked(),
            "proxy_addr": self.le_proxy.text(),
            "use_cookie": self.cb_use_cookie.isChecked(),
            "cookie_src": self.combo_cookie_src.currentIndex(),
            "cookie_path": self.le_cookie_path.text(),
            "save_dir": self.le_save_dir.text() if hasattr(self, "le_save_dir") else ""
        }
        self.config.set_plugin_config("youtube_downloader", cfg)
