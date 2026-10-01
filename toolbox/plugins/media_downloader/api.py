"""
B站媒体下载器 - API 交互模块
"""

import json
import re
import requests
from typing import Dict, Any, Optional, Tuple, List

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
REFERER = "https://www.bilibili.com"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": REFERER,
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

API_VIDEO_INFO = "https://api.bilibili.com/x/web-interface/view"
API_PLAY_URL = "https://api.bilibili.com/x/player/playurl"
API_NAV = "https://api.bilibili.com/x/web-interface/nav"
API_FAV_RESOURCE_LIST = "https://api.bilibili.com/x/v3/fav/resource/list"
API_MEDIALIST_RESOURCE = "https://api.bilibili.com/x/v2/medialist/resource/list"
API_USER_CARD = "https://api.bilibili.com/x/web-interface/card"

QUALITY_MAP = {
    127: "8K 超高清",
    126: "1080P 杜比视界",
    125: "HDR 真彩",
    120: "4K 超清",
    116: "1080P 60帧",
    112: "1080P 高码率",
    80: "1080P 高清",
    74: "720P 60帧",
    64: "720P 高清",
    32: "480P 清晰",
    16: "360P 流畅"
}

VIP_QN_SET = {127, 126, 125, 120, 116, 112, 74}


def normalize_cookie(raw: str) -> str:
    """
    智能自适应解析与标准化任何形式的 Cookie 输入，杜绝任何换行符与非法头部字符：
    1. 支持浏览器插件（如 Cookie-Editor / EditThisCookie）导出的 JSON 数组格式:
       [{"name": "SESSDATA", "value": "..."}, {"name": "bili_jct", ...}]
    2. 支持 JSON 键值字典: {"SESSDATA": "...", "bili_jct": "..."}
    3. 支持 Netscape 格式文件文本 (tab 分隔)
    4. 支持标准分号分隔 key=value 字符串 (自动清洗前后空格、多余换行与控制字符)
    5. 支持纯 SESSDATA 裸值 (自动补充 SESSDATA= 前缀)
    """
    if not raw:
        return ""
    if not isinstance(raw, str):
        try:
            raw = str(raw)
        except Exception:
            return ""

    raw = raw.strip()
    if not raw:
        return ""

    # 1. 剥离 Markdown 代码块与外层多余引号
    if raw.startswith("```") and raw.endswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    if (raw.startswith("`") and raw.endswith("`")) or \
       (raw.startswith('"') and raw.endswith('"')) or \
       (raw.startswith("'") and raw.endswith("'")):
        raw = raw[1:-1].strip()

    # 2. 关键清洗: 将字面量转义字符 (\\n, \\r, \\t) 反转义为真实换行与制表符
    if "\\n" in raw or "\\r" in raw or "\\t" in raw:
        raw = raw.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")

    cookie_dict = {}
    non_cookie_keys = {
        "domain", "path", "expires", "expirationdate", "httponly",
        "secure", "samesite", "hostonly", "session", "none", "sgp",
        "bmg_af_sc", "storeid", "id"
    }

    def is_dirty_key_or_val(k: str, v: str = "") -> bool:
        k_lower = k.lower().strip().strip("\"'")
        if k_lower in non_cookie_keys:
            return True
        if k_lower.startswith(("none", "sgp", "bmg_")):
            return True
        v_s = str(v)
        if "{'on':" in v_s or "'def':" in v_s or "i1.hdslb.com" in v_s or "i0-sgp.hdslb.com" in v_s:
            return True
        return False

    # 3. 策略一: 全局 JSON 解析 (数组或对象，支持自动补齐外围方括号)
    if ("[" in raw and "]" in raw) or ("{" in raw and "}" in raw):
        for candidate in [raw, "[" + raw + "]"]:
            start_bracket = candidate.find("[") if "[" in candidate else -1
            start_brace = candidate.find("{") if "{" in candidate else -1
            cand_starts = [p for p in (start_bracket, start_brace) if p >= 0]
            start_pos = min(cand_starts) if cand_starts else -1

            end_bracket = candidate.rfind("]") if "]" in candidate else -1
            end_brace = candidate.rfind("}") if "}" in candidate else -1
            cand_ends = [p for p in (end_bracket, end_brace) if p >= 0]
            end_pos = max(cand_ends) if cand_ends else -1

            if start_pos >= 0 and end_pos > start_pos:
                json_str = candidate[start_pos:end_pos + 1]
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, dict) and "name" in item and "value" in item:
                                k = str(item["name"]).strip()
                                v = str(item["value"]).strip()
                                if k and v and not is_dirty_key_or_val(k, v):
                                    cookie_dict[k] = v
                    elif isinstance(parsed, dict):
                        if "name" in parsed and "value" in parsed:
                            k = str(parsed["name"]).strip()
                            v = str(parsed["value"]).strip()
                            if k and v and not is_dirty_key_or_val(k, v):
                                cookie_dict[k] = v
                        elif any(pk in parsed for pk in ("SESSDATA", "bili_jct", "DedeUserID", "buvid3")):
                            for k, v in parsed.items():
                                k_s = str(k).strip()
                                v_s = str(v).strip()
                                if k_s and v_s and not is_dirty_key_or_val(k_s, v_s):
                                    cookie_dict[k_s] = v_s
                    if "SESSDATA" in cookie_dict:
                        break
                except Exception:
                    pass

    # 4. 策略二: 局部截断或残缺 JSON 块扫描 (匹配每一个独立的 { ... })
    if "SESSDATA" not in cookie_dict:
        for m in re.finditer(r'\{[^{}]+\}', raw):
            block = m.group(0)
            try:
                item = json.loads(block)
                if isinstance(item, dict) and "name" in item and "value" in item:
                    k = str(item["name"]).strip()
                    v = str(item["value"]).strip()
                    if k and v and not is_dirty_key_or_val(k, v):
                        cookie_dict[k] = v
            except Exception:
                pass

    # 5. 策略三: 正则跨行全文本扫描 (name / value 键值对)
    if "SESSDATA" not in cookie_dict:
        for m in re.finditer(r'"name"\s*:\s*"([^"]+)"[^{}]*?"value"\s*:\s*"([^"]+)"', raw, re.DOTALL):
            k, v = m.group(1).strip(), m.group(2).strip()
            if k and v and not is_dirty_key_or_val(k, v) and k not in cookie_dict:
                cookie_dict[k] = v
        for m in re.finditer(r'"value"\s*:\s*"([^"]+)"[^{}]*?"name"\s*:\s*"([^"]+)"', raw, re.DOTALL):
            k, v = m.group(2).strip(), m.group(1).strip()
            if k and v and not is_dirty_key_or_val(k, v) and k not in cookie_dict:
                cookie_dict[k] = v

    # 6. 策略四: 标准分号或多行 key=value 键值对 (如 "SESSDATA=xxx; buvid3=yyy")
    if not cookie_dict and "=" in raw and (";" in raw or "\n" in raw or "\r" in raw):
        norm_raw = raw.replace("\r", "\n")
        lines = [l.strip() for l in norm_raw.split("\n") if l.strip()]
        for line in lines:
            for seg in line.split(";"):
                if "=" in seg:
                    k, v = seg.split("=", 1)
                    k_c = k.strip().strip("\"'")
                    v_c = v.strip().strip("\"'")
                    if k_c and v_c and not is_dirty_key_or_val(k_c, v_c):
                        cookie_dict[k_c] = v_c

    # 7. 策略五: Netscape cookies 格式文件 (制表符分隔)
    if not cookie_dict and "\t" in raw and ("bilibili.com" in raw or "SESSDATA" in raw):
        for line in raw.replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                name = parts[5].strip()
                val = parts[6].strip()
                if name and val and not is_dirty_key_or_val(name, val):
                    cookie_dict[name] = val

    # 8. 策略六: SESSDATA 专属正则兜底拦截
    if "SESSDATA" not in cookie_dict:
        m_sess = re.search(r'(?:SESSDATA\s*[:=]\s*["\']?|["\']SESSDATA["\']\s*[:=]\s*["\']?)([a-zA-Z0-9%*_-]+)', raw, re.IGNORECASE)
        if m_sess:
            cookie_dict["SESSDATA"] = m_sess.group(1).strip()

    # 若成功提取出了有效 Cookie 字典
    if cookie_dict:
        cleaned_dict = {k: v for k, v in cookie_dict.items() if not is_dirty_key_or_val(k, v)}
        priority = ["SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "buvid3", "sid"]
        pairs = []
        for pk in priority:
            if pk in cleaned_dict:
                pairs.append(f"{pk}={cleaned_dict.pop(pk)}")
        for k, v in cleaned_dict.items():
            pairs.append(f"{k}={v}")
        return "; ".join(pairs)

    # 清除所有不可见回车换行与控制字符
    raw = re.sub(r'[\r\n\t]+', ' ', raw).strip()

    # 9. 纯 SESSDATA 裸值 (长度 > 8，且不包含 URL、结构字符或脏关键字)
    if "=" not in raw and len(raw) > 8:
        raw_l = raw.lower()
        if not any(c in raw for c in ("{", "}", "[", "]", ";", ":", "/", "?", " ", "\t")) and not any(dk in raw_l for dk in ("http", "none", "sgp", "domain", "bmg")):
            return f"SESSDATA={raw}"

    # 10. 标准分号键值对清洗
    pairs = []
    for seg in raw.split(";"):
        seg = seg.strip()
        if not seg:
            continue
        if "=" in seg:
            k, v = seg.split("=", 1)
            k = k.strip().strip("\"'")
            v = v.strip().strip("\"'")
            if k and v and not is_dirty_key_or_val(k, v):
                pairs.append(f"{k}={v}")
        elif not is_dirty_key_or_val(seg):
            pairs.append(seg)
    return "; ".join(pairs)


class BiliApiClient:
    def __init__(self, cookie: str = ""):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(HEADERS)
        self.cookie = ""
        self.set_cookie(cookie)

    def set_cookie(self, cookie: str):
        norm = normalize_cookie(cookie)
        self.cookie = norm
        if norm:
            self.session.headers.update({"Cookie": norm})
        elif "Cookie" in self.session.headers:
            del self.session.headers["Cookie"]

    def check_account_status(self) -> Dict[str, Any]:
        """
        调用 B站 nav 接口检测当前登录与大会员状态。
        返回字典:
        {
            "is_login": bool,
            "uname": str,
            "mid": int,
            "vip_type": int,
            "vip_status": int,
            "vip_label": str,
            "message": str
        }
        """
        try:
            resp = self.session.get(API_NAV, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                d = data.get("data", {})
                is_login = bool(d.get("isLogin", False))
                if is_login:
                    uname = str(d.get("uname", ""))
                    mid = int(d.get("mid", 0) or 0)
                    vip_type = int(d.get("vipType", 0) or 0)
                    vip_status = int(d.get("vipStatus", 0) or 0)

                    vip_label_raw = d.get("vip_label", {})
                    vip_label = ""
                    if isinstance(vip_label_raw, dict):
                        vip_label = vip_label_raw.get("text", "")
                    elif isinstance(vip_label_raw, str):
                        vip_label = vip_label_raw

                    # 大会员必须同时满足 vip_status == 1 且 vip_type > 0 (1: 月度/季度, 2: 年度及以上)
                    if vip_status == 1 and vip_type > 0:
                        if not vip_label:
                            vip_label = "年度大会员" if vip_type == 2 else "大会员"
                        msg = f"大会员: {uname} (全规格已解锁)"
                    else:
                        # 普通会员 / 已登录非大会员 (vip_status=0 或 vip_type=0)
                        vip_label = "普通会员"
                        msg = f"已登录: {uname} (最高1080P)"

                    return {
                        "is_login": True,
                        "uname": uname,
                        "mid": mid,
                        "vip_type": vip_type,
                        "vip_status": vip_status,
                        "vip_label": vip_label,
                        "message": msg
                    }
                else:
                    return {
                        "is_login": False,
                        "uname": "",
                        "mid": 0,
                        "vip_type": 0,
                        "vip_status": 0,
                        "vip_label": "未登录",
                        "message": "未登录 (最高480P)"
                    }
            else:
                return {
                    "is_login": False,
                    "uname": "",
                    "mid": 0,
                    "vip_type": 0,
                    "vip_status": 0,
                    "vip_label": "未登录",
                    "message": "未登录 (最高480P)"
                }
        except Exception as e:
            return {
                "is_login": False,
                "uname": "",
                "mid": 0,
                "vip_type": 0,
                "vip_status": 0,
                "vip_label": "网络异常",
                "message": f"账号状态检测失败: {e}"
            }

    @staticmethod
    def extract_bvid(input_str: str) -> Optional[str]:
        """从字符串或URL中提取BV号"""
        input_str = input_str.strip()
        pattern = r"BV[a-zA-Z0-9]{10}"
        match = re.search(pattern, input_str, re.IGNORECASE)
        if match:
            return match.group(0)

        # 检查是否是 b23.tv 短链
        if "b23.tv" in input_str:
            try:
                res = requests.head(input_str, allow_redirects=True, timeout=5)
                match = re.search(pattern, res.url, re.IGNORECASE)
                if match:
                    return match.group(0)
            except Exception:
                pass
        return None

    @staticmethod
    def extract_fav_id(input_str: str) -> Optional[str]:
        """从字符串或URL中提取收藏夹ID (fid / media_id)"""
        if not input_str:
            return None
        input_str = input_str.strip()
        # 1. 匹配 medialist/play/ml12345 或 medialist/detail/ml12345 或 /ml12345 或 ml12345
        m_ml = re.search(r"(?:medialist/(?:play|detail)/ml|(?:\b|^)ml)(\d+)", input_str, re.IGNORECASE)
        if m_ml:
            return m_ml.group(1)
        # 2. 匹配 favlist?fid=12345 或 fid=12345 或 fid:12345 或 fid 12345 或 FID12345
        m_fid = re.search(r"(?:favlist\?.*?fid=|(?:\b|^)fid[:=\s]*)(\d+)", input_str, re.IGNORECASE)
        if m_fid:
            return m_fid.group(1)
        # 3. 匹配 medialist/play/12345 或 medialist/detail/12345
        m_media = re.search(r"medialist/(?:play|detail)/(\d+)", input_str, re.IGNORECASE)
        if m_media:
            return m_media.group(1)
        # 4. 纯数字
        if input_str.isdigit():
            return input_str
        return None

    @staticmethod
    def extract_up_mid(input_str: str) -> Optional[str]:
        """从字符串或URL中提取UP主的 UID / mid"""
        if not input_str:
            return None
        input_str = input_str.strip()
        # 1. 匹配 space.bilibili.com/12345 (排除带 favlist 的情况)
        if "favlist" not in input_str:
            m_space = re.search(r"space\.bilibili\.com/(\d+)", input_str, re.IGNORECASE)
            if m_space:
                return m_space.group(1)
        # 2. 匹配 uid:12345 或 mid:12345 或 uid=12345 或 mid=12345 或 UID 12345 或 MID 12345
        m_uid = re.search(r"(?:\b|^)(?:uid|mid)[:=\s]*(\d+)", input_str, re.IGNORECASE)
        if m_uid:
            return m_uid.group(1)
        # 3. 纯数字
        if input_str.isdigit():
            return input_str
        return None

    @classmethod
    def detect_target_type_and_id(cls, input_str: str) -> Tuple[str, Optional[str]]:
        """
        智能识别输入字符串的类型及对应ID:
        返回 ("video", bvid) 或 ("favorite", fid) 或 ("space", mid) 或 ("unknown", None)
        """
        if not input_str:
            return "unknown", None
        input_str = input_str.strip()

        # 短链展开处理
        expanded_str = input_str
        if "b23.tv" in input_str:
            try:
                res = requests.head(input_str, allow_redirects=True, timeout=5)
                if res.url:
                    expanded_str = res.url
            except Exception:
                pass

        # 优先检测 BV 号 (如同时存在其他参数以 BV 为准)
        bvid = cls.extract_bvid(expanded_str)
        if bvid:
            return "video", bvid

        # 检测收藏夹
        if any(kw in expanded_str.lower() for kw in ("favlist", "medialist", "ml", "fid")):
            fid = cls.extract_fav_id(expanded_str)
            if fid:
                return "favorite", fid

        # 检测 UP 主空间
        if "space.bilibili.com" in expanded_str or any(kw in expanded_str.lower() for kw in ("uid", "mid")):
            mid = cls.extract_up_mid(expanded_str)
            if mid:
                return "space", mid

        # 纯数字输入：未显式指明
        if expanded_str.isdigit():
            return "unknown", expanded_str

        return "unknown", None

    def get_favorite_videos(self, media_id: str | int, max_count: int = 1000) -> Dict[str, Any]:
        """
        获取指定收藏夹内的所有视频列表 (支持多页合并解析)
        """
        try:
            media_id = str(media_id).strip()
            page = 1
            page_size = 20
            all_videos = []
            info = {}
            has_more = True

            while has_more and len(all_videos) < max_count:
                params = {
                    "media_id": media_id,
                    "pn": page,
                    "ps": page_size,
                    "keyword": "",
                    "order": "mtime",
                    "type": 0,
                    "tid": 0,
                    "platform": "web"
                }
                resp = self.session.get(API_FAV_RESOURCE_LIST, params=params, timeout=12)
                data = resp.json()
                if data.get("code") != 0:
                    err_msg = data.get("message") or f"错误代码: {data.get('code')}"
                    if not all_videos:
                        return {"success": False, "error": f"收藏夹解析失败: {err_msg}"}
                    break

                d = data.get("data", {}) or {}
                if not info and d.get("info"):
                    info = d["info"]

                medias = d.get("medias") or []
                if not medias:
                    break

                for m in medias:
                    if not isinstance(m, dict):
                        continue
                    bvid = m.get("bvid") or m.get("bv_id", "")
                    title = m.get("title", "")
                    if not bvid or title == "已失效视频":
                        continue
                    upper = m.get("upper", {}) or {}
                    ugc = m.get("ugc") if isinstance(m.get("ugc"), dict) else {}
                    cid = ugc.get("first_cid") or m.get("cid")
                    all_videos.append({
                        "bvid": bvid,
                        "cid": cid,
                        "title": title,
                        "owner": upper.get("name", "未知UP主"),
                        "pic": m.get("cover", ""),
                        "duration": m.get("duration", 0),
                        "page": m.get("page", 1),
                        "intro": m.get("intro", ""),
                        "fav_time": m.get("fav_time", 0)
                    })

                has_more = bool(d.get("has_more", False))
                page += 1

            if len(all_videos) > max_count:
                all_videos = all_videos[:max_count]

            if not all_videos and not info:
                return {"success": False, "error": "收藏夹为空或不存在"}

            folder_title = info.get("title", f"收藏夹_{media_id}") if isinstance(info, dict) else f"收藏夹_{media_id}"
            folder_upper = info.get("upper", {}).get("name", "") if isinstance(info, dict) and isinstance(info.get("upper"), dict) else ""
            folder_cover = info.get("cover", "") if isinstance(info, dict) else ""
            media_count = info.get("media_count", len(all_videos)) if isinstance(info, dict) else len(all_videos)

            return {
                "success": True,
                "type": "favorite",
                "media_id": media_id,
                "title": folder_title,
                "owner": folder_upper,
                "pic": folder_cover,
                "total_count": media_count,
                "videos": all_videos
            }
        except Exception as e:
            return {"success": False, "error": f"获取收藏夹视频失败: {e}"}

    def get_space_videos(self, mid: str | int, max_count: int = 1000) -> Dict[str, Any]:
        """
        获取指定UP主主页投稿全视频列表 (使用 medialist 资源接口，支持无限制分页)
        """
        try:
            mid = str(mid).strip()
            # 1. 尝试获取 UP 主基础信息
            owner_name = f"UP主_{mid}"
            face_url = ""
            try:
                card_resp = self.session.get(API_USER_CARD, params={"mid": mid}, timeout=8)
                card_data = card_resp.json()
                if card_data.get("code") == 0:
                    card_dict = card_data.get("data", {}).get("card", {})
                    if card_dict:
                        owner_name = card_dict.get("name", owner_name)
                        face_url = card_dict.get("face", "")
            except Exception:
                pass

            # 2. 分页获取 UP 主全量投稿视频
            all_videos = []
            has_more = True
            last_oid = None
            total_count = 0
            page_size = 20

            while has_more and len(all_videos) < max_count:
                params = {
                    "type": 1,
                    "biz_id": mid,
                    "ps": page_size,
                    "direction": "false"
                }
                if last_oid is not None:
                    params["oid"] = last_oid
                    params["with_current"] = "false"

                resp = self.session.get(API_MEDIALIST_RESOURCE, params=params, timeout=12)
                data = resp.json()
                if data.get("code") != 0:
                    err_msg = data.get("message") or f"错误代码: {data.get('code')}"
                    if not all_videos:
                        return {"success": False, "error": f"UP主空间解析失败: {err_msg}"}
                    break

                d = data.get("data", {}) or {}
                if not total_count:
                    total_count = d.get("total_count", 0)

                media_list = d.get("media_list") or []
                if not media_list:
                    break

                for m in media_list:
                    if not isinstance(m, dict):
                        continue
                    bvid = m.get("bv_id") or m.get("bvid", "")
                    title = m.get("title", "")
                    if not bvid:
                        continue
                    upper = m.get("upper", {}) or {}
                    if not face_url and upper.get("face"):
                        face_url = upper.get("face")
                    if owner_name.startswith("UP主_") and upper.get("name"):
                        owner_name = upper.get("name")

                    pages = m.get("pages")
                    first_page = pages[0] if isinstance(pages, list) and pages and isinstance(pages[0], dict) else {}
                    cid = first_page.get("id") or m.get("cid")

                    all_videos.append({
                        "bvid": bvid,
                        "cid": cid,
                        "title": title,
                        "owner": upper.get("name", owner_name),
                        "pic": m.get("cover", ""),
                        "duration": m.get("duration", 0),
                        "page": m.get("page", 1),
                        "intro": m.get("intro", ""),
                        "pubtime": m.get("pubtime", 0)
                    })

                has_more = bool(d.get("has_more", False))
                last_oid = media_list[-1].get("id")

            if len(all_videos) > max_count:
                all_videos = all_videos[:max_count]

            if not all_videos:
                return {"success": False, "error": "该UP主主页无投稿视频或空间受限"}

            return {
                "success": True,
                "type": "space",
                "mid": mid,
                "title": f"{owner_name} 的主页投稿",
                "owner": owner_name,
                "pic": face_url,
                "total_count": total_count or len(all_videos),
                "videos": all_videos
            }
        except Exception as e:
            return {"success": False, "error": f"获取UP主投稿失败: {e}"}

    def get_video_info(self, bvid: str) -> Dict[str, Any]:
        """获取视频基本元数据"""
        try:
            resp = self.session.get(API_VIDEO_INFO, params={"bvid": bvid}, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                d = data.get("data", {})
                pages = []
                for p in d.get("pages", []):
                    pages.append({
                        "cid": p.get("cid"),
                        "page": p.get("page"),
                        "part": p.get("part", f"P{p.get('page')}")
                    })
                return {
                    "success": True,
                    "bvid": bvid,
                    "title": d.get("title", ""),
                    "owner": d.get("owner", {}).get("name", "未知UP主"),
                    "pic": d.get("pic", ""),
                    "desc": d.get("desc", ""),
                    "duration": d.get("duration", 0),
                    "pages": pages
                }
            else:
                return {"success": False, "error": data.get("message", "接口返回异常")}
        except Exception as e:
            return {"success": False, "error": f"网络请求失败: {e}"}

    def get_play_streams(self, bvid: str, cid: int, qn: int = 80) -> Dict[str, Any]:
        """获取视频播放流 (DASH 协议)"""
        params = {
            "bvid": bvid,
            "cid": cid,
            "qn": qn,
            "fnval": 4048,  # DASH, 4K, 8K, HDR, 杜比视界, 杜比全景声, AV1 (0xFD0)
            "fnver": 0,
            "fourk": 1
        }
        try:
            resp = self.session.get(API_PLAY_URL, params=params, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                d = data.get("data", {})
                dash = d.get("dash", {})
                videos = dash.get("video", [])
                audios = dash.get("audio", [])

                support_formats = d.get("support_formats", [])
                format_desc_map = {}
                for sf in support_formats:
                    if isinstance(sf, dict) and "quality" in sf:
                        format_desc_map[sf["quality"]] = sf.get("new_description") or sf.get("display_desc", "")

                accept_qualities = d.get("accept_quality", [])
                accept_descriptions = d.get("accept_description", [])
                available_qualities = []
                seen_qns = set()

                for idx, q in enumerate(accept_qualities):
                    if q not in seen_qns:
                        seen_qns.add(q)
                        desc = format_desc_map.get(q) or (accept_descriptions[idx] if idx < len(accept_descriptions) else QUALITY_MAP.get(q, f"{q}P"))
                        available_qualities.append({
                            "qn": q,
                            "name": QUALITY_MAP.get(q, desc)
                        })

                for sf in support_formats:
                    q = sf.get("quality")
                    if q and q not in seen_qns:
                        seen_qns.add(q)
                        desc = sf.get("new_description") or sf.get("display_desc") or QUALITY_MAP.get(q, f"{q}P")
                        available_qualities.append({
                            "qn": q,
                            "name": QUALITY_MAP.get(q, desc)
                        })

                # 获取匹配或最高画质的视频流: 优先匹配 qn，其次找 <= qn 的最高流，最后取可用最高流
                best_video = None
                for v in videos:
                    if v.get("id") == qn:
                        best_video = v
                        break
                if not best_video and videos:
                    lower_or_equal = [v for v in videos if (v.get("id", 0) or 0) <= qn]
                    if lower_or_equal:
                        best_video = max(lower_or_equal, key=lambda v: v.get("id", 0) or 0)
                    else:
                        best_video = max(videos, key=lambda v: v.get("id", 0) or 0)

                video_url = ""
                actual_qn = 0
                if best_video:
                    video_url = (
                        best_video.get("baseUrl")
                        or best_video.get("base_url")
                        or (best_video.get("backupUrl", [""])[0] if best_video.get("backupUrl") else "")
                        or (best_video.get("backup_url", [""])[0] if best_video.get("backup_url") else "")
                    )
                    actual_qn = best_video.get("id", 0) or 0

                # 兼容旧版非 DASH 的 durl 返回
                if not video_url and d.get("durl"):
                    durl_list = d.get("durl", [])
                    if durl_list and isinstance(durl_list, list):
                        video_url = durl_list[0].get("url", "")
                        actual_qn = d.get("quality", 0) or 0

                actual_quality = QUALITY_MAP.get(actual_qn, f"{actual_qn}P") if actual_qn else "未知画质"
                is_downgraded = bool(qn and actual_qn < qn)

                # 音频流智能优选: flac (Hi-Res) -> dolby (杜比全景声) -> audio (按 bandwidth 降序)
                selected_audio = None
                audio_codec = ""
                audio_bandwidth = 0

                def _get_stream_url(stream_dict):
                    if not stream_dict or not isinstance(stream_dict, dict):
                        return ""
                    return (
                        stream_dict.get("baseUrl")
                        or stream_dict.get("base_url")
                        or (stream_dict.get("backupUrl", [""])[0] if stream_dict.get("backupUrl") else "")
                        or (stream_dict.get("backup_url", [""])[0] if stream_dict.get("backup_url") else "")
                    )

                # 1. 检查 Hi-Res (flac)，兼容 dict 与 list 结构
                flac_obj = dash.get("flac")
                if flac_obj and isinstance(flac_obj, dict):
                    flac_audio = flac_obj.get("audio")
                    if isinstance(flac_audio, list) and flac_audio:
                        for fa in flac_audio:
                            if isinstance(fa, dict) and _get_stream_url(fa):
                                selected_audio = fa
                                audio_codec = fa.get("codecs", "flac")
                                audio_bandwidth = fa.get("bandwidth", 0) or 0
                                break
                    elif isinstance(flac_audio, dict) and _get_stream_url(flac_audio):
                        selected_audio = flac_audio
                        audio_codec = flac_audio.get("codecs", "flac")
                        audio_bandwidth = flac_audio.get("bandwidth", 0) or 0

                # 2. 检查 杜比全景声 (dolby)
                if not selected_audio:
                    dolby_obj = dash.get("dolby")
                    if dolby_obj and isinstance(dolby_obj, dict):
                        dolby_audio = dolby_obj.get("audio")
                        if isinstance(dolby_audio, list) and dolby_audio:
                            for da in dolby_audio:
                                if isinstance(da, dict) and _get_stream_url(da):
                                    selected_audio = da
                                    audio_codec = da.get("codecs", "dolby")
                                    audio_bandwidth = da.get("bandwidth", 0) or 0
                                    break
                        elif isinstance(dolby_audio, dict) and _get_stream_url(dolby_audio):
                            selected_audio = dolby_audio
                            audio_codec = dolby_audio.get("codecs", "dolby")
                            audio_bandwidth = dolby_audio.get("bandwidth", 0) or 0

                # 3. 普通音频流 (audio)，按 bandwidth 降序排序优选
                if not selected_audio and audios:
                    valid_audios = [a for a in audios if isinstance(a, dict)]
                    sorted_audios = sorted(valid_audios, key=lambda a: a.get("bandwidth", 0) or 0, reverse=True)
                    if sorted_audios:
                        selected_audio = sorted_audios[0]
                        audio_codec = selected_audio.get("codecs", "")
                        audio_bandwidth = selected_audio.get("bandwidth", 0) or 0

                audio_url = _get_stream_url(selected_audio) if selected_audio else ""

                return {
                    "success": True,
                    "video_url": video_url,
                    "audio_url": audio_url,
                    "actual_quality": actual_quality,
                    "actual_qn": actual_qn,
                    "is_downgraded": is_downgraded,
                    "available_qualities": available_qualities,
                    "qualities": available_qualities,
                    "support_formats": support_formats,
                    "audio_codec": audio_codec,
                    "audio_bandwidth": audio_bandwidth
                }
            else:
                return {"success": False, "error": data.get("message", "获取播放流失败")}
        except Exception as e:
            return {"success": False, "error": f"获取播放流异常: {e}"}
