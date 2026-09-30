"""
图像格式转换与缩放工坊 - 尺寸缩放引擎与多线程任务
"""

import os
from typing import List, Tuple, Optional
from PIL import Image
from PySide6.QtCore import QThread, Signal
from .converter import convert_image


class ImageBatchWorker(QThread):
    progress = Signal(int, int)   # (当前已完成数, 总数)
    log_message = Signal(str)     # 日志行
    task_finished = Signal(int, int) # (成功数, 失败数)

    def __init__(
        self,
        task_type: str,           # "convert" 或 "resize"
        file_paths: List[str],
        output_dir: str,
        # 格式转换参数
        target_format: str = "PNG",
        quality: int = 90,
        # 缩放参数
        resize_mode: str = "percent", # "percent", "fixed", 或 "crop"
        scale_pct: float = 100.0,
        target_w: int = 1920,
        target_h: int = 1080,
        keep_ratio: bool = True,
        crop_box: Optional[Tuple[int, int, int, int]] = None
    ):
        super().__init__()
        self.task_type = task_type
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.target_format = target_format
        self.quality = quality
        self.resize_mode = resize_mode
        self.scale_pct = scale_pct
        self.target_w = target_w
        self.target_h = target_h
        self.keep_ratio = keep_ratio
        self.crop_box = crop_box
        self._is_stopped = False

    def stop(self):
        self._is_stopped = True

    def run(self):
        total = len(self.file_paths)
        if total == 0:
            self.task_finished.emit(0, 0)
            return

        os.makedirs(self.output_dir, exist_ok=True)
        success_count = 0
        fail_count = 0

        for idx, src_path in enumerate(self.file_paths, start=1):
            if self._is_stopped:
                self.log_message.emit("[已停止] 用户已停止当前批处理任务。")
                break

            filename = os.path.basename(src_path)

            try:
                if self.task_type == "convert":
                    ok, out_path, detail = convert_image(
                        src_path=src_path,
                        output_dir=self.output_dir,
                        target_format=self.target_format,
                        quality=self.quality
                    )
                    if ok:
                        success_count += 1
                        self.log_message.emit(f"[{idx}/{total}] [成功] 转换成功: {filename} -> {os.path.basename(out_path)}")
                    else:
                        fail_count += 1
                        self.log_message.emit(f"[{idx}/{total}] [失败] 转换失败: {filename} ({detail})")

                elif self.task_type == "resize":
                    out_path = os.path.join(self.output_dir, filename)
                    is_same_file = (os.path.normcase(os.path.abspath(src_path)) == os.path.normcase(os.path.abspath(out_path)))
                    tmp_target = os.path.join(self.output_dir, f"._tmp_resize_{os.getpid()}_{filename}") if is_same_file else None
                    save_target = tmp_target if is_same_file else out_path

                    try:
                        with Image.open(src_path) as raw_img:
                            raw_img.load()
                            orig_w, orig_h = raw_img.size
                            img_info = dict(raw_img.info)

                            # 1. 显式区域剪裁 (crop_box: left, top, right, bottom)
                            if self.crop_box:
                                cl, ct, cr, cb = self.crop_box
                                cl = max(0, min(orig_w - 1, cl))
                                ct = max(0, min(orig_h - 1, ct))
                                cr = max(cl + 1, min(orig_w, cr))
                                cb = max(ct + 1, min(orig_h, cb))
                                raw_img = raw_img.crop((cl, ct, cr, cb))
                                orig_w, orig_h = raw_img.size

                            # 2. 缩放与自适应模式
                            if self.resize_mode == "percent":
                                factor = self.scale_pct / 100.0
                                new_w = max(1, int(orig_w * factor))
                                new_h = max(1, int(orig_h * factor))
                                resized = raw_img.resize((new_w, new_h), Image.Resampling.LANCZOS).copy()
                            elif self.resize_mode == "crop":
                                # 保持纵横比居中缩放并裁切填充至 target_w x target_h
                                scale = max(self.target_w / orig_w, self.target_h / orig_h)
                                inter_w = max(1, int(orig_w * scale))
                                inter_h = max(1, int(orig_h * scale))
                                inter_img = raw_img.resize((inter_w, inter_h), Image.Resampling.LANCZOS)
                                left = max(0, (inter_w - self.target_w) // 2)
                                top = max(0, (inter_h - self.target_h) // 2)
                                right = left + self.target_w
                                bottom = top + self.target_h
                                resized = inter_img.crop((left, top, right, bottom)).copy()
                                new_w, new_h = self.target_w, self.target_h
                            else:
                                if self.keep_ratio:
                                    ratio = min(self.target_w / orig_w, self.target_h / orig_h)
                                    new_w = max(1, int(orig_w * ratio))
                                    new_h = max(1, int(orig_h * ratio))
                                else:
                                    new_w = self.target_w
                                    new_h = self.target_h

                                resized = raw_img.resize((new_w, new_h), Image.Resampling.LANCZOS).copy()

                        # 如果目标文件为 JPEG 或 BMP，且包含透明通道，则需用纯白底色平铺转为 RGB
                        is_target_jpeg_or_bmp = out_path.lower().endswith(('.jpg', '.jpeg', '.bmp'))
                        if is_target_jpeg_or_bmp and (resized.mode in ("RGBA", "LA") or (resized.mode == "P" and "transparency" in img_info)):
                            rgba = resized.convert("RGBA")
                            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                            composite = Image.alpha_composite(background, rgba)
                            resized = composite.convert("RGB")
                        elif is_target_jpeg_or_bmp and resized.mode != "RGB":
                            resized = resized.convert("RGB")

                        resized.save(save_target)

                        if tmp_target and os.path.exists(tmp_target):
                            os.replace(tmp_target, out_path)
                    except Exception:
                        if tmp_target and os.path.exists(tmp_target):
                            try:
                                os.remove(tmp_target)
                            except Exception:
                                pass
                        raise

                    success_count += 1
                    mode_desc = "裁剪填充" if self.resize_mode == "crop" else ("裁剪并缩放" if self.crop_box else "缩放")
                    self.log_message.emit(f"[{idx}/{total}] [成功] {mode_desc}成功: {filename} ({orig_w}x{orig_h} -> {new_w}x{new_h})")

            except Exception as e:
                fail_count += 1
                self.log_message.emit(f"[{idx}/{total}] [异常] 处理异常: {filename} ({str(e)})")

            self.progress.emit(idx, total)

        self.task_finished.emit(success_count, fail_count)
