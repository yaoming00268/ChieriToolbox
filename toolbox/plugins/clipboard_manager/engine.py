"""
剪贴板管理器 (Clipboard Manager) - 核心引擎与敏感信息脱敏检测
提供低内存占用历史队列、敏感凭证脱敏与多格式记录管理。
"""

import re
import time
from typing import List, Dict, Optional, Tuple, Any
from PySide6.QtCore import Qt

# 敏感信息检测正则
RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
RE_ID_CARD = re.compile(r"\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b")
RE_API_KEY = re.compile(r"\b(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|eyJh[a-zA-Z0-9._-]{20,})\b", re.IGNORECASE)


def detect_and_mask_sensitive_text(text: str) -> Tuple[bool, str, List[str]]:
    """
    探测并掩码文本中的敏感信息 (手机号、身份证、API Key / Token)。
    返回 (是否发现敏感信息, 脱敏后文本, 发现的敏感类型列表)
    """
    if not text:
        return False, text, []

    found_types = []
    masked = text

    # 1. 手机号脱敏 (前3后4，中间4位打码)
    phones = RE_PHONE.findall(text)
    if phones:
        found_types.append("手机号")
        for p in set(phones):
            masked = masked.replace(p, f"{p[:3]}****{p[7:]}")

    # 2. 身份证号脱敏 (前6后4)
    ids = RE_ID_CARD.findall(text)
    if ids:
        found_types.append("身份证号")
        for id_num in set(ids):
            masked = masked.replace(id_num, f"{id_num[:6]}********{id_num[-4:]}")

    # 3. 密钥与 Token 脱敏
    keys = RE_API_KEY.findall(text)
    if keys:
        found_types.append("API密钥/Token")
        for k in set(keys):
            masked = masked.replace(k, f"{k[:4]}****{k[-4:] if len(k) > 8 else ''}")

    return bool(found_types), masked, found_types


class ClipboardHistoryItem:
    """单个剪贴板条目轻量记录结构"""
    def __init__(self, content: str, item_type: str = "text", preview_pixmap=None, full_pixmap=None):
        self.content = content
        self.item_type = item_type  # "text" / "image" / "file"
        self.preview_pixmap = preview_pixmap  # 仅保存微缩图
        self.full_pixmap = full_pixmap
        self.timestamp = time.time()
        self.has_sensitive, self.masked_content, self.sensitive_types = (
            detect_and_mask_sensitive_text(content) if item_type == "text" else (False, content, [])
        )
        self.is_pinned = False

    def get_display_text(self, desensitize: bool = True) -> str:
        if self.item_type != "text":
            return f"[{self.item_type.upper()} 数据]"
        return self.masked_content if desensitize and self.has_sensitive else self.content


class ClipboardHistoryManager:
    """剪贴板历史队列单例（带严格内存上限保护）"""
    def __init__(self, max_items: int = 80):
        self.max_items = max_items
        self.items: List[ClipboardHistoryItem] = []
        self.pinned_snippets: List[Dict[str, str]] = [
            {"title": "通用打卡问候", "content": "您好！今天工作辛苦了，请查收今日报告。"},
            {"title": "邮箱标准签名", "content": "Best Regards,\nChieri Toolbox Team"},
            {"title": "Base64 测试头", "content": "data:image/png;base64,"},
        ]

    def add_text(self, text: str) -> Optional[ClipboardHistoryItem]:
        clean = text.strip()
        if not clean:
            return None
        # 去重：若与最新一条完全相同则直接跳过
        if self.items and self.items[0].content == clean:
            return self.items[0]

        item = ClipboardHistoryItem(clean, "text")
        self.items.insert(0, item)
        self._prune()
        return item

    def add_image(self, pixmap) -> Optional[ClipboardHistoryItem]:
        if not pixmap or pixmap.isNull():
            return None
        # 严格限制内存：缩放为不超过 96x96 的缩略图缓存
        thumb = pixmap.scaled(96, 96, Qt.KeepAspectRatio)
        # 若超大分辨率则约束全尺寸上限至 2560px，防止单图占用上百兆内存
        if pixmap.width() > 2560 or pixmap.height() > 2560:
            cached_full = pixmap.scaled(2560, 2560, Qt.KeepAspectRatio)
        else:
            cached_full = pixmap
        item = ClipboardHistoryItem("[图片数据]", "image", preview_pixmap=thumb, full_pixmap=cached_full)
        self.items.insert(0, item)
        self._prune()
        return item

    def clear(self):
        # 保留已置顶条目
        self.items = [it for it in self.items if it.is_pinned]

    def _prune(self):
        if len(self.items) > self.max_items:
            # 优先移除非置顶的最老项
            unpinned = [i for i, it in enumerate(self.items) if not it.is_pinned]
            if unpinned:
                oldest_idx = unpinned[-1]
                self.items.pop(oldest_idx)
            else:
                self.items = self.items[:self.max_items]

        # 内存过载防御：最多仅保留最近 10 张全尺寸高清大图，防止连续截屏导致内存溢出
        image_items = [it for it in self.items if it.item_type == "image" and it.full_pixmap is not None]
        if len(image_items) > 10:
            for it in image_items[10:]:
                it.full_pixmap = None
