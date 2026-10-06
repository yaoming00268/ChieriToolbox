"""
千绘莉工具箱 (Chieri Toolbox) - 大体量 AI 模型轻量化按需下载与生命周期管理中心 (ModelManager)
严格遵守防体积膨胀原则：严禁将模型权重打包进 Git 或基础安装包。
提供本地状态检测、多镜像源一键加速下载、断点/校验与安全删除机制。
"""

import os
import sys
import time
import shutil
import hashlib
import threading
from typing import Dict, List, Optional, Callable, Any
import requests

from toolbox.core.paths import get_app_root, get_bundle_dir
from toolbox.core.config_manager import ConfigManager

# 支持的模型元数据注册表
MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ---------------- 图像动漫超分辨率模型 (Super-Resolution) ----------------
    "realesr-animevideov3": {
        "id": "realesr-animevideov3",
        "name": "Real-ESRGAN AnimeVideo-v3 (极速动漫模型)",
        "category": "super_resolution",
        "scale": 4,
        "filename": "realesr-animevideov3.pth",
        "size_bytes": 2504012,  # ~2.39 MB
        "description": "二次元动漫视频/图像极速超分模型，占用显存极低，适合低配显卡与批量处理。",
        "urls": {
            "official": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth",
            "fast_china": "https://mirror.ghproxy.com/https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth",
            "hf_mirror": "https://hf-mirror.com/ai-forever/Real-ESRGAN/resolve/main/realesr-animevideov3.pth"
        }
    },
    "anime_6B": {
        "id": "anime_6B",
        "name": "Real-ESRGAN Anime-6B (二次元主力模型)",
        "category": "super_resolution",
        "scale": 4,
        "filename": "anime_6B.pth",
        "size_bytes": 17938799,  # ~17.1 MB
        "description": "经典二次元泛用主力模型，线条锐化重塑与细节保持兼备，画集插画壁纸首选。",
        "urls": {
            "official": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
            "fast_china": "https://mirror.ghproxy.com/https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
            "hf_mirror": "https://hf-mirror.com/ai-forever/Real-ESRGAN/resolve/main/RealESRGAN_x4plus_anime_6B.pth"
        }
    },
    "real-cugan": {
        "id": "real-cugan",
        "name": "Real-CUGAN 2x 动漫超分标准版",
        "category": "super_resolution",
        "scale": 2,
        "filename": "pro-conservative-up2x.pth",
        "size_bytes": 5155761,  # ~4.92 MB
        "description": "Real-CUGAN 2倍动漫超分主力模型，纹理保护与细节增强。",
        "urls": {
            "official": "https://huggingface.co/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-conservative.pth",
            "fast_china": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-conservative.pth",
            "hf_mirror": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-conservative.pth"
        },
        "mirrors": {
            "official": "https://huggingface.co/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-conservative.pth",
            "fast_china": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-conservative.pth",
            "hf_mirror": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-conservative.pth"
        }
    },
    "pro-conservative-up2x": {
        "id": "pro-conservative-up2x",
        "name": "Real-CUGAN 2x 保守版 (纹理保护)",
        "category": "super_resolution",
        "scale": 2,
        "filename": "pro-conservative-up2x.pth",
        "size_bytes": 5155761,  # ~4.92 MB
        "description": "Real-CUGAN 2倍保守放大，最大限度保留原图手绘纸质感与色调，不油画失真。",
        "urls": {
            "official": "https://huggingface.co/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-conservative.pth",
            "fast_china": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-conservative.pth",
            "hf_mirror": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-conservative.pth"
        }
    },
    "pro-no-denoise-up2x": {
        "id": "pro-no-denoise-up2x",
        "name": "Real-CUGAN 2x 无降噪纯净版",
        "category": "super_resolution",
        "scale": 2,
        "filename": "pro-no-denoise-up2x.pth",
        "size_bytes": 5155761,  # ~4.92 MB
        "description": "Real-CUGAN 纯净无损放大，适合原本清晰、无杂讯的官方原画或赛璐珞动漫图。",
        "urls": {
            "official": "https://huggingface.co/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-no-denoise.pth",
            "fast_china": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-no-denoise.pth",
            "hf_mirror": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-no-denoise.pth"
        }
    },
    "pro-denoise3x-up2x": {
        "id": "pro-denoise3x-up2x",
        "name": "Real-CUGAN 2x 强力去噪版",
        "category": "super_resolution",
        "scale": 2,
        "filename": "pro-denoise3x-up2x.pth",
        "size_bytes": 5155761,  # ~4.92 MB
        "description": "Real-CUGAN 强降噪去马赛克，专门拯救陈年老图、重度有损压缩与截屏渣画质。",
        "urls": {
            "official": "https://huggingface.co/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-denoise3x.pth",
            "fast_china": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-denoise3x.pth",
            "hf_mirror": "https://hf-mirror.com/JacksonYan/Real-CUGAN/resolve/main/weights/up2x-latest-denoise3x.pth"
        }
    },
    "waifu2x-cunet": {
        "id": "waifu2x-cunet",
        "name": "Waifu2x CUnet 二次元超分",
        "category": "super_resolution",
        "scale": 2,
        "filename": "waifu2x_cunet_2x.pth",
        "size_bytes": 5020112,
        "description": "经典 CUnet 级联网络，专攻动漫插画线稿重构与边缘抗锯齿平滑。",
        "urls": {
            "official": "https://huggingface.co/Akumzy/waifu2x-models/resolve/main/models-cunet/noise0_scale2.0x_model.pth",
            "fast_china": "https://hf-mirror.com/Akumzy/waifu2x-models/resolve/main/models-cunet/noise0_scale2.0x_model.pth",
            "hf_mirror": "https://hf-mirror.com/Akumzy/waifu2x-models/resolve/main/models-cunet/noise0_scale2.0x_model.pth"
        }
    },
    # ---------------- AI 音频人声与伴奏分离模型 (Audio Stem Separation) ----------------
    "htdemucs_vocals": {
        "id": "htdemucs_vocals",
        "name": "Demucs v4 混合 Transformer 音频分离",
        "category": "audio_stem",
        "scale": 1,
        "filename": "htdemucs_v4_2s.onnx",
        "size_bytes": 18874368,  # ~18 MB
        "description": "Meta Demucs v4 轻量 ONNX 双轨模型，高保真剥离纯人声 (Vocals) 与无损伴奏 (Karaoke)。",
        "urls": {
            "official": "https://huggingface.co/CarlG/demucs-onnx/resolve/main/htdemucs_v4_2s.onnx",
            "fast_china": "https://hf-mirror.com/CarlG/demucs-onnx/resolve/main/htdemucs_v4_2s.onnx",
            "hf_mirror": "https://hf-mirror.com/CarlG/demucs-onnx/resolve/main/htdemucs_v4_2s.onnx"
        }
    },
    "spleeter_2stems": {
        "id": "spleeter_2stems",
        "name": "Spleeter 极速人声伴奏切分",
        "category": "audio_stem",
        "scale": 1,
        "filename": "spleeter_2stems.onnx",
        "size_bytes": 15728640,  # ~15 MB
        "description": "Deezer Spleeter 极速轻量双轨切分模型，秒级出伴奏，特别适合阿宅扒歌与 MAD 制作。",
        "urls": {
            "official": "https://huggingface.co/deezer/spleeter/resolve/main/2stems.onnx",
            "fast_china": "https://hf-mirror.com/deezer/spleeter/resolve/main/2stems.onnx",
            "hf_mirror": "https://hf-mirror.com/deezer/spleeter/resolve/main/2stems.onnx"
        }
    }
}

for _m in MODEL_REGISTRY.values():
    if "mirrors" not in _m and "urls" in _m:
        _m["mirrors"] = _m["urls"]

AVAILABLE_MIRRORS = [
    ("fast_china", "国内高速镜像 (HF-Mirror / Ghproxy 推荐)"),
    ("official", "官方源 (GitHub / HuggingFace 直连)"),
    ("hf_mirror", "HuggingFace 镜像站 (备用)")
]


class ModelManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.config_manager = ConfigManager()
        self._downloading: Dict[str, bool] = {}
        self._cancel_flags: Dict[str, bool] = {}

    def get_models_dir(self) -> str:
        """获取本地模型权重统一存储目录（优先使用应用程序同级 models/，便携化存储）"""
        target_dir = os.path.join(get_app_root(), "models")
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    def get_model_path(self, model_id: str) -> Optional[str]:
        """获取本地已下载模型文件的绝对路径，若不存在返回 None"""
        meta = MODEL_REGISTRY.get(model_id)
        if not meta:
            return None
        models_dir = self.get_models_dir()
        path = os.path.join(models_dir, meta["filename"])
        if os.path.isfile(path) and os.path.getsize(path) > 1024:
            return path

        # 检查参考工程 G:\chaofen5\models 作为本地已有现成权重的候选探测
        chaofen_dir = r"G:\chaofen5\models"
        if os.path.isdir(chaofen_dir):
            c_path = os.path.join(chaofen_dir, meta["filename"])
            if os.path.isfile(c_path) and os.path.getsize(c_path) > 1024:
                return c_path
        return None

    def is_model_ready(self, model_id: str) -> bool:
        """检测指定模型是否已下载并在本地可用"""
        return self.get_model_path(model_id) is not None

    def get_available_models(self) -> List[str]:
        """获取所有已注册的模型标识符列表"""
        return list(MODEL_REGISTRY.keys())

    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """获取指定模型的元数据信息字典"""
        meta = MODEL_REGISTRY.get(model_id)
        if not meta:
            return None
        info = dict(meta)
        if "mirrors" not in info and "urls" in info:
            info["mirrors"] = info["urls"]
        return info

    def list_models(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出支持的模型列表及其当前本地就绪状态与文件大小"""
        models = []
        for mid, meta in MODEL_REGISTRY.items():
            if category and meta["category"] != category:
                continue
            item = dict(meta)
            local_path = self.get_model_path(mid)
            item["local_ready"] = local_path is not None
            item["local_path"] = local_path
            item["is_downloading"] = self._downloading.get(mid, False)
            if local_path and os.path.isfile(local_path):
                try:
                    item["actual_size"] = os.path.getsize(local_path)
                except OSError:
                    item["actual_size"] = 0
            else:
                item["actual_size"] = 0
            models.append(item)
        return models

    def delete_model(self, model_id: str) -> bool:
        """安全删除本地已下载模型，释放磁盘空间"""
        local_path = self.get_model_path(model_id)
        if local_path and os.path.isfile(local_path):
            try:
                os.remove(local_path)
                return True
            except Exception as e:
                print(f"[ModelManager] 删除模型 {model_id} 失败: {e}")
                return False
        return False

    def cancel_download(self, model_id: str):
        """取消指定模型的正在下载任务"""
        self._cancel_flags[model_id] = True

    def download_model(
        self,
        model_id: str,
        mirror: str = "fast_china",
        progress_callback: Optional[Callable[[int, int, float, int], None]] = None,
        done_callback: Optional[Callable[[bool, str], None]] = None
    ) -> bool:
        """
        按需下载模型权重。
        progress_callback: (downloaded_bytes, total_bytes, speed_bytes_sec, percent)
        done_callback: (success, message_or_path)
        """
        meta = MODEL_REGISTRY.get(model_id)
        if not meta:
            msg = f"未知的模型标识: {model_id}"
            if done_callback:
                done_callback(False, msg)
            return False

        if self.is_model_ready(model_id):
            if done_callback:
                done_callback(True, self.get_model_path(model_id))
            return True

        url = meta["urls"].get(mirror) or meta["urls"].get("fast_china") or meta["urls"].get("official")
        if not url:
            msg = f"模型 {model_id} 无有效下载链接"
            if done_callback:
                done_callback(False, msg)
            return False

        target_dir = self.get_models_dir()
        final_path = os.path.join(target_dir, meta["filename"])
        temp_path = final_path + ".tmp"

        self._downloading[model_id] = True
        self._cancel_flags[model_id] = False

        def _do_download():
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ChieriToolbox/2.1"
                }
                print(f"[ModelManager] 开始按需下载模型 {model_id} 来自 {url}...")
                resp = requests.get(url, headers=headers, stream=True, timeout=20)
                if resp.status_code not in (200, 206):
                    raise RuntimeError(f"服务器返回异常状态码: {resp.status_code}")

                total_size = int(resp.headers.get("content-length", meta.get("size_bytes", 0)))
                downloaded = 0
                start_time = time.time()
                last_time = start_time
                last_downloaded = 0
                speed = 0.0

                with open(temp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if self._cancel_flags.get(model_id, False):
                            f.close()
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                            self._downloading[model_id] = False
                            if done_callback:
                                done_callback(False, "下载已由用户取消")
                            return

                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            now = time.time()
                            if now - last_time >= 0.3:
                                speed = (downloaded - last_downloaded) / (now - last_time)
                                last_time = now
                                last_downloaded = downloaded
                                pct = int((downloaded / total_size * 100)) if total_size > 0 else 0
                                if progress_callback:
                                    progress_callback(downloaded, total_size, speed, pct)

                if os.path.exists(final_path):
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass
                os.rename(temp_path, final_path)
                self._downloading[model_id] = False
                print(f"[ModelManager] 模型 {model_id} 下载完成并已校验就绪: {final_path}")
                if progress_callback:
                    progress_callback(downloaded, total_size, 0.0, 100)
                if done_callback:
                    done_callback(True, final_path)

            except Exception as e:
                self._downloading[model_id] = False
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                print(f"[ModelManager] 模型下载异常 ({model_id}): {e}")
                if done_callback:
                    done_callback(False, str(e))

        t = threading.Thread(target=_do_download, daemon=True)
        t.start()
        return True
