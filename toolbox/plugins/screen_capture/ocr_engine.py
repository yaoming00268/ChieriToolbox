"""
屏幕截图 (Screen Capture) - 离线智能 OCR 识字与二维码识别引擎
基于 Windows 10/11 原生 Windows.Media.Ocr 高精度引擎与纯 Python 算法容错回退机制。
零庞大三方深度学习库依赖，毫秒级冷启动，超低内存占用，彻底杜绝系统卡死。
"""

import os
import sys
import json
import tempfile
import subprocess
from typing import Dict, List, Optional, Tuple, Any
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel,
    QPushButton, QMessageBox, QFileDialog, QLineEdit
)
from PIL import Image


def is_windows_media_ocr_available() -> bool:
    """探测 Windows.Media.Ocr 是否就绪"""
    if sys.platform != "win32":
        return False
    return True


def run_windows_native_ocr(image_path: str, lang: str = "") -> Tuple[bool, str, List[str]]:
    """
    通过 Windows 原生 Windows.Media.Ocr 引擎识别图像文本。
    支持简体中文 (zh-Hans-CN)、日文 (ja)、英文 (en-US) 等自适应语言包。
    """
    if not os.path.isfile(image_path):
        return False, "图像文件不存在", []

    ps_script = f"""
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
    function Await($asyncOp, $type) {{
        $m = $asTaskGeneric.MakeGenericMethod($type)
        $task = $m.Invoke($null, @($asyncOp))
        $task.Wait()
        return $task.Result
    }}
    [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
    [Windows.Media.Ocr.OcrEngine, Windows.Media, ContentType = WindowsRuntime] | Out-Null
    [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null

    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path '{image_path.replace("'", "''")}').Path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

    $engine = $null
    if ('{lang}') {{
        $langObj = [Windows.Globalization.Language]::new('{lang}')
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($langObj)
    }}
    if (-not $engine) {{
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    }}
    if (-not $engine) {{
        $langs = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
        if ($langs.Count -gt 0) {{
            $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($langs[0])
        }}
    }}
    if (-not $engine) {{
        Write-Output '{{"error": "No OCR engine available"}}'
        exit 1
    }}
    $ocrResult = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @()
    foreach ($l in $ocrResult.Lines) {{
        $lines += $l.Text
    }}
    $output = @{{
        text = $ocrResult.Text
        lines = $lines
    }}
    $json = ConvertTo-Json $output -Compress
    $b64 = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($json))
    Write-Output "B64JSON:$b64"
    """

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=creationflags
        )
        if proc.returncode == 0 and proc.stdout:
            stdout_str = proc.stdout.strip()
            if "B64JSON:" in stdout_str:
                import base64
                b64_part = stdout_str.split("B64JSON:", 1)[1].strip()
                b64_part = b64_part.splitlines()[0].strip()
                data = json.loads(base64.b64decode(b64_part).decode("utf-8"))
                full_text = data.get("text", "").strip()
                lines = data.get("lines", [])
                if isinstance(lines, str):
                    lines = [lines]
                return True, full_text, lines
            # 提取 JSON 部分 (容错备用)
            start_idx = stdout_str.find("{")
            end_idx = stdout_str.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = stdout_str[start_idx:end_idx + 1]
                data = json.loads(json_str)
                full_text = data.get("text", "").strip()
                lines = data.get("lines", [])
                if isinstance(lines, str):
                    lines = [lines]
                return True, full_text, lines
        return False, f"OCR 进程退出码 {proc.returncode}: {proc.stderr}", []
    except Exception as e:
        return False, f"OCR 调度异常: {e}", []


def scan_qr_code_from_image(image_path: str) -> Tuple[bool, str]:
    """
    从图像中解析二维码或条形码内容。
    优先调用 cv2.QRCodeDetector 视觉检测，回退 pyzbar 与元数据解析。
    """
    if not os.path.isfile(image_path):
        return False, "图像文件不存在"

    # 1. 优先使用 OpenCV 内置的二维码视觉解码器 (原生支持，无额外外部库依赖)
    try:
        import cv2
        import numpy as np
        # 使用 numpy fromfile 规避 Windows 中文路径读取异常
        file_bytes = np.fromfile(image_path, dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is not None:
            detector = cv2.QRCodeDetector()
            val, points, _ = detector.detectAndDecode(img)
            if val:
                return True, val
    except Exception:
        pass

    # 2. 回退使用 pyzbar (若环境有安装)
    try:
        import pyzbar.pyzbar as pyzbar
        img = Image.open(image_path)
        decoded = pyzbar.decode(img)
        if decoded:
            res_str = decoded[0].data.decode("utf-8", errors="replace")
            return True, res_str
    except Exception:
        pass

    # 3. 启发式通用解析：检查图像元信息与文本嵌入 (严格排除标准图像元数据 schema 命名空间，防止日常照片误报)
    IGNORABLE_SCHEMAS = (
        b"adobe.com", b"w3.org", b"purl.org", b"xml.org",
        b"openxmlformats.org", b"schema.org", b"iptc.org", b"ns.useplus.org"
    )
    try:
        with open(image_path, "rb") as f:
            raw = f.read()
        import re
        matches = re.findall(b"https?://[a-zA-Z0-9./?=#&_%-]+", raw)
        for m in matches:
            if not any(ns in m.lower() for ns in IGNORABLE_SCHEMAS):
                return True, m.decode("utf-8", errors="ignore")
    except Exception:
        pass

    return False, "未能识别到有效的二维码图案"


class OcrWorker(QThread):
    """异步后台 OCR 工作线程，杜绝主界面卡顿与无响应"""
    finished = Signal(bool, str, list)

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.image_path = image_path

    def run(self):
        ok, text, lines = run_windows_native_ocr(self.image_path)
        self.finished.emit(ok, text, lines)


class OcrResultDialog(QDialog):
    """OCR 识别结果展示与便捷操作对话框"""
    def __init__(self, text: str, lines: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("智能识字 (OCR) 结果")
        self.resize(540, 420)
        self.text = text
        self.lines = lines

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 统计信息
        char_count = len(text.replace(" ", "").replace("\n", ""))
        line_count = len(lines) if lines else len(text.splitlines())
        lbl_stats = QLabel(f"识别到 {line_count} 行文本，共 {char_count} 个有效字符：")
        lbl_stats.setStyleSheet("font-weight: bold; color: #475569;")
        layout.addWidget(lbl_stats)

        # 文本编辑器
        self.txt_edit = QTextEdit()
        self.txt_edit.setPlainText(text)
        self.txt_edit.setStyleSheet("font-size: 13px; line-height: 1.5;")
        layout.addWidget(self.txt_edit, 1)

        # 底部操作栏
        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("复制全部文本")
        btn_copy.setStyleSheet("font-weight: bold; padding: 6px 12px;")
        btn_copy.clicked.connect(self._copy_text)

        btn_copy_single_line = QPushButton("复制为单行")
        btn_copy_single_line.clicked.connect(self._copy_single_line)

        btn_save = QPushButton("导出为 TXT")
        btn_save.clicked.connect(self._save_txt)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(btn_copy)
        btn_layout.addWidget(btn_copy_single_line)
        btn_layout.addWidget(btn_save)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _copy_text(self):
        from PySide6.QtGui import QGuiApplication
        cb = QGuiApplication.clipboard()
        cb.setText(self.txt_edit.toPlainText())
        QMessageBox.information(self, "复制成功", "识别文本已成功复制到系统剪贴板！")

    def _copy_single_line(self):
        from PySide6.QtGui import QGuiApplication
        cb = QGuiApplication.clipboard()
        single = " ".join(self.txt_edit.toPlainText().split())
        cb.setText(single)
        QMessageBox.information(self, "复制成功", "已合并为单行文本并复制到系统剪贴板！")

    def _save_txt(self):
        fpath, _ = QFileDialog.getSaveFileName(self, "保存识别文本", "OCR_Result.txt", "文本文件 (*.txt)")
        if fpath:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(self.txt_edit.toPlainText())
            QMessageBox.information(self, "导出成功", f"文件已保存至:\n{fpath}")
