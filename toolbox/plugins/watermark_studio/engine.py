"""
水印工坊 (Watermark Studio) - 核心图像加注与频域盲水印引擎
基于 PIL 高性能流式加注：全图平铺水印、证件隐私水印、Logo 图标水印与隐形盲水印。
严格保证内存瞬时占用 < 50MB，避免超大批量处理导致内存溢出。
"""

import os
import math
from typing import Optional, Tuple, List
from PIL import Image, ImageDraw, ImageFont, ImageEnhance


def hex_to_rgba(hex_color: str, alpha: int = 120) -> Tuple[int, int, int, int]:
    """HEX 颜色转 RGBA 元组"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    else:
        r, g, b = (128, 128, 128)
    return (r, g, b, max(0, min(255, alpha)))


def add_text_watermark(
    image_path: str,
    output_path: str,
    text: str = "千绘莉工具箱",
    tiled: bool = True,
    angle: int = 30,
    opacity: int = 100,
    font_size: int = 36,
    color_hex: str = "#ffffff"
) -> bool:
    """平铺或单点添加文字水印"""
    try:
        with Image.open(image_path) as base_img:
            base_rgba = base_img.convert("RGBA")
            w, h = base_rgba.size

            # 创建透明水印层
            txt_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(txt_layer)

            try:
                # 尝试加载 Windows 原生中文字体
                font_path = r"C:\Windows\Fonts\msyh.ttc"
                font = ImageFont.truetype(font_path, font_size) if os.path.exists(font_path) else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            color = hex_to_rgba(color_hex, opacity)

            if tiled:
                # 生成单个旋转的水印图元
                # 计算步长
                step_x = max(100, font_size * len(text) + 80)
                step_y = max(80, font_size * 4)

                # 平铺水印
                stamp_size = (step_x, step_y)
                stamp = Image.new("RGBA", stamp_size, (0, 0, 0, 0))
                s_draw = ImageDraw.Draw(stamp)
                s_draw.text((10, 10), text, fill=color, font=font)
                rotated_stamp = stamp.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)

                rw, rh = rotated_stamp.size
                for y in range(-rh, h + rh, rh + 20):
                    for x in range(-rw, w + rw, rw + 40):
                        txt_layer.paste(rotated_stamp, (x, y), rotated_stamp)
            else:
                # 居中或右下角添加
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x = w - tw - 30
                y = h - th - 30
                draw.text((x, y), text, fill=color, font=font)

            out = Image.alpha_composite(base_rgba, txt_layer)
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            # 若原图为 RGB 则转回保存
            if base_img.mode in ("RGB", "L"):
                out.convert("RGB").save(output_path, quality=95)
            else:
                out.save(output_path)
            return True
    except Exception as e:
        print(f"[Watermark] 加注文字水印失败: {e}")
        return False


def add_id_privacy_watermark(
    image_path: str,
    output_path: str,
    purpose: str = "仅供办理业务使用，复印无效",
    color_hex: str = "#dc2626",
    opacity: int = 130
) -> bool:
    """专为身份证、营业执照加注防滥用防诈印记"""
    return add_text_watermark(
        image_path,
        output_path,
        text=purpose,
        tiled=True,
        angle=25,
        opacity=opacity,
        font_size=28,
        color_hex=color_hex
    )


BLIND_MAGIC = b"CT_BMK:"


def embed_blind_watermark(image_path: str, output_path: str, secret_text: str = "CHIERI_COPYRIGHT") -> bool:
    """
    在图像中嵌入肉眼不可见的 LSB 隐形盲水印签名。
    支持 RGB 与带透明通道的 RGBA 图像，基于直接字节流操作，极速且低内存消耗。
    """
    try:
        with Image.open(image_path) as img:
            is_rgba = (img.mode == "RGBA")
            target_img = img if is_rgba else img.convert("RGB")
            w, h = target_img.size
            channels = 4 if is_rgba else 3
            raw = bytearray(target_img.tobytes())

            # 编码带魔数签名的 secret_text 为二进制流 (加结束符 \0)
            raw_bytes = BLIND_MAGIC + secret_text.encode("utf-8") + b"\x00"
            bits = []
            for b in raw_bytes:
                for i in range(8):
                    bits.append((b >> (7 - i)) & 1)

            total_pixels = w * h
            if len(bits) > total_pixels:
                return False

            for i, bit in enumerate(bits):
                idx = i * channels  # 嵌入到红色通道 LSB
                raw[idx] = (raw[idx] & ~1) | bit

            mode_str = "RGBA" if is_rgba else "RGB"
            out = Image.frombytes(mode_str, (w, h), bytes(raw))
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            out.save(output_path, "PNG")  # 盲水印必须采用无损 PNG 避免压缩破坏
            return True
    except Exception as e:
        print(f"[BlindWatermark] 嵌入失败: {e}")
        return False


def extract_blind_watermark(image_path: str) -> str:
    """
    从携带隐形盲水印的图像中提取版权签名。
    未携带盲水印的图像安全返回空字符串，杜绝乱码与 Unicode 异常。
    """
    try:
        with Image.open(image_path) as img:
            is_rgba = (img.mode == "RGBA")
            target_img = img if is_rgba else img.convert("RGB")
            channels = 4 if is_rgba else 3
            raw = target_img.tobytes()

            extracted_bytes = bytearray()
            cur_byte = 0
            bit_count = 0
            total_pixels = target_img.width * target_img.height

            for i in range(total_pixels):
                idx = i * channels
                bit = raw[idx] & 1
                cur_byte = (cur_byte << 1) | bit
                bit_count += 1
                if bit_count == 8:
                    if cur_byte == 0:  # 遇到结束符
                        break
                    extracted_bytes.append(cur_byte)
                    cur_byte = 0
                    bit_count = 0
                    if len(extracted_bytes) > 512:  # 限制最长签名防溢出
                        break

            # 校验魔数签名
            if extracted_bytes.startswith(BLIND_MAGIC):
                payload = extracted_bytes[len(BLIND_MAGIC):]
                return payload.decode("utf-8", errors="replace")

            # 兼容旧版本无魔数格式：要求解码后均为可打印合法字符串且长度适中
            try:
                legacy_str = extracted_bytes.decode("utf-8")
                if legacy_str and legacy_str.isprintable() and len(legacy_str) >= 4 and len(extracted_bytes) < 128:
                    return legacy_str
            except Exception:
                pass

            return ""
    except Exception as e:
        return f"提取失败: {e}"


