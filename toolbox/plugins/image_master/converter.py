"""
图像格式转换与缩放工坊 - 格式转换核心引擎
"""

import os
from typing import Tuple, List, Optional
from PIL import Image


SUPPORTED_FORMATS = ["PNG", "JPG", "JPEG", "WEBP", "ICO", "BMP", "TIFF", "GIF"]


def convert_image(
    src_path: str,
    output_dir: str,
    target_format: str,
    quality: int = 90,
    fill_color: Tuple[int, int, int] = (255, 255, 255),
    ico_sizes: Optional[List[Tuple[int, int]]] = None
) -> Tuple[bool, str, str]:
    """
    单个图像格式转换核心函数
    返回: (成功布尔值, 输出路径/错误信息, 详细说明)
    """
    try:
        norm_fmt = target_format.upper()
        if norm_fmt == "JPG":
            norm_fmt = "JPEG"

        base_name = os.path.splitext(os.path.basename(src_path))[0]
        ext = target_format.lower()
        if ext == "jpeg":
            ext = "jpg"
        os.makedirs(output_dir, exist_ok=True)
        out_filename = f"{base_name}.{ext}"
        out_path = os.path.join(output_dir, out_filename)

        is_same_file = (os.path.normcase(os.path.abspath(out_path)) == os.path.normcase(os.path.abspath(src_path)))
        save_target = out_path
        tmp_target = None
        if is_same_file:
            tmp_target = os.path.join(output_dir, f"._tmp_{os.getpid()}_{out_filename}")
            save_target = tmp_target

        with Image.open(src_path) as img:
            img.load()
            # 透明通道处理
            has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)

            # 转换为不支持透明度的格式 (如 JPEG, BMP) 时用填充色平铺
            if norm_fmt in ("JPEG", "BMP") and has_alpha:
                rgba = img.convert("RGBA")
                background = Image.new("RGBA", rgba.size, fill_color + (255,))
                composite = Image.alpha_composite(background, rgba)
                img_to_save = composite.convert("RGB")
            elif norm_fmt in ("JPEG", "BMP") and img.mode != "RGB":
                img_to_save = img.convert("RGB")
            elif norm_fmt == "ICO":
                img_to_save = img.convert("RGBA")
            else:
                img_to_save = img.copy()

        save_kwargs = {}
        if norm_fmt in ("JPEG", "WEBP"):
            save_kwargs["quality"] = quality
        if norm_fmt == "ICO":
            sizes = ico_sizes or [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            save_kwargs["sizes"] = sizes

        img_to_save.save(save_target, format=norm_fmt, **save_kwargs)

        if tmp_target and os.path.exists(tmp_target):
            os.replace(tmp_target, out_path)

        return True, out_path, f"成功转换为 {norm_fmt}"
    except Exception as e:
        return False, "", str(e)
