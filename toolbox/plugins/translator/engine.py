"""
全能翻译引擎 - 支持公开免配置接口、OpenAI 兼容 API 与本地 Ollama 大模型
"""

import json
import urllib.parse
from typing import Dict, Optional, Tuple
from PySide6.QtCore import QThread, Signal
import requests

LANGUAGE_CODES = {
    "自动检测": "auto",
    "中文 (简体)": "zh-CN",
    "英语": "en",
    "日语": "ja",
    "韩语": "ko",
    "法语": "fr",
    "德语": "de",
    "俄语": "ru",
    "西班牙语": "es",
    "意大利语": "it",
    "繁体中文": "zh-TW"
}


def translate_via_public(
    text: str,
    source_lang: str,
    target_lang: str,
    timeout: int = 8,
    proxy: Optional[str] = None
) -> Tuple[bool, str]:
    """通过免配置公开端点进行高精度翻译 (支持长文本与代理配置)"""
    src_code = LANGUAGE_CODES.get(source_lang, "auto")
    tgt_code = LANGUAGE_CODES.get(target_lang, "zh-CN")

    proxies = {"http": proxy, "https": proxy} if proxy else None

    # 首选 Google Translate GTX 接口 (使用 POST 杜绝长文本 414 溢出)
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        data = {
            "client": "gtx",
            "sl": src_code,
            "tl": tgt_code,
            "dt": "t",
            "q": text
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.post(url, data=data, headers=headers, proxies=proxies, timeout=timeout)
        if resp.status_code == 200:
            res_json = resp.json()
            if res_json and isinstance(res_json, list) and len(res_json) > 0 and isinstance(res_json[0], list):
                translated_parts = [part[0] for part in res_json[0] if part and part[0]]
                return True, "".join(translated_parts)
    except Exception:
        pass

    # 备选 MyMemory 公开接口
    try:
        sl = src_code if src_code != "auto" else "zh-CN"
        langpair = f"{sl}|{tgt_code}"
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text[:500])}&langpair={langpair}"
        resp = requests.get(url, proxies=proxies, timeout=timeout)
        if resp.status_code == 200:
            res_data = resp.json()
            trans = res_data.get("responseData", {}).get("translatedText", "")
            if trans:
                return True, trans
    except Exception as e:
        return False, f"公开接口请求失败: {str(e)}"

    return False, "公开翻译引擎暂时无法连接，请检查网络或切换至自定义大模型接口。"


def translate_via_openai(
    text: str,
    source_lang: str,
    target_lang: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout: int = 25
) -> Tuple[bool, str]:
    """通过 OpenAI 兼容 API (如 DeepSeek, OpenAI, Moonshot, Qwen 等) 进行翻译"""
    if not base_url:
        return False, "请先在配置中指定 API Base URL。"
    if not model:
        return False, "请先指定模型名称 (例如 deepseek-chat 或 gpt-4o-mini)。"

    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"

    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    system_prompt = (
        f"You are a professional and accurate translator. "
        f"Translate the following text from {source_lang} to {target_lang}. "
        f"Preserve the original meaning, tone, and formatting. "
        f"Output ONLY the translated result without any explanation, markdown backticks, or extra greeting."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "temperature": 0.2
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            return True, content
        else:
            return False, f"API 响应错误 [{resp.status_code}]: {resp.text[:200]}"
    except Exception as e:
        return False, f"API 请求异常: {str(e)}"


def translate_via_ollama(
    text: str,
    source_lang: str,
    target_lang: str,
    host: str,
    model: str,
    timeout: int = 30
) -> Tuple[bool, str]:
    """通过本地 Ollama 大模型端点进行翻译"""
    endpoint = host.rstrip("/")
    if not endpoint.endswith("/api/generate"):
        endpoint = f"{endpoint}/api/generate"

    prompt = (
        f"Translate the following text into {target_lang}. Output only the translation without any introduction or notes:\n\n{text}"
    )

    payload = {
        "model": model or "qwen2.5:7b",
        "prompt": prompt,
        "stream": False
    }

    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return True, data.get("response", "").strip()
        else:
            return False, f"Ollama 响应错误 [{resp.status_code}]: {resp.text[:200]}"
    except Exception as e:
        return False, f"无法连接到 Ollama: {str(e)}"


class TranslationWorker(QThread):
    """异步翻译工作线程"""
    finished = Signal(bool, str)  # (成功, 结果文本或错误原因)

    def __init__(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        engine_type: str,
        config: Dict
    ):
        super().__init__()
        self.text = text
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.engine_type = engine_type
        self.config = config

    def run(self):
        if not self.text.strip():
            self.finished.emit(True, "")
            return

        proxy = self.config.get("proxy_addr") or None

        if self.engine_type == "public":
            ok, res = translate_via_public(self.text, self.source_lang, self.target_lang, proxy=proxy)
        elif self.engine_type == "openai":
            ok, res = translate_via_openai(
                text=self.text,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                base_url=self.config.get("openai_base_url", ""),
                api_key=self.config.get("openai_api_key", ""),
                model=self.config.get("openai_model", "")
            )
        elif self.engine_type == "ollama":
            ok, res = translate_via_ollama(
                text=self.text,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                host=self.config.get("ollama_host", "http://localhost:11434"),
                model=self.config.get("ollama_model", "qwen2.5:7b")
            )
        else:
            ok, res = translate_via_public(self.text, self.source_lang, self.target_lang, proxy=proxy)

        self.finished.emit(ok, res)
