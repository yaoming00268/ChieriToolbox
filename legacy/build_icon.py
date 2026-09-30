"""
生成应用程序 Windows 高清多分辨率 ICO 图标文件
"""

import os
import sys
from PySide6.QtCore import QByteArray, Qt, QRectF
from PySide6.QtGui import QPainter, QPixmap, QPainterPath, QColor, QLinearGradient
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication
from PIL import Image

def generate_icon(output_ico="app_icon.ico", output_png="app_icon.png"):
    app = QApplication.instance() or QApplication(sys.argv)
    
    svg_content = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
<polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
<line x1="12" y1="22.08" x2="12" y2="12"/>
</svg>"""

    size = 256
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    # 绘制高质感圆角渐变矩形背景 (符合现代 Fluent / macOS 设计规范)
    path = QPainterPath()
    path.addRoundedRect(QRectF(14, 14, 228, 228), 52, 52)

    gradient = QLinearGradient(0, 0, 256, 256)
    gradient.setColorAt(0.0, QColor("#3B82F6"))
    gradient.setColorAt(1.0, QColor("#1D4ED8"))

    painter.fillPath(path, gradient)

    # 渲染矢量 Logo
    renderer = QSvgRenderer(QByteArray(svg_content.encode("utf-8")))
    renderer.render(painter, QRectF(48, 48, 160, 160))
    painter.end()

    qimg = pixmap.toImage()
    buffer = qimg.bits()
    pil_img = Image.frombytes("RGBA", (size, size), bytes(buffer), "raw", "BGRA")
    
    pil_img.save(output_png)
    pil_img.save(
        output_ico,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print(f"Icon generated successfully: {output_ico} ({os.path.getsize(output_ico)} bytes)")

if __name__ == "__main__":
    generate_icon()
