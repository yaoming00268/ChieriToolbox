"""
ACG 密码本与自动试探匹配引擎 (ACG Password Memory Book)
内置二次元动漫/Galgame/同人社区常用解压密码，支持密码记忆、自定义管理与归档秒级匹配试探。
"""

import json
import os
import subprocess
import zipfile
from typing import Callable, List, Optional, Tuple

from toolbox.core.config_manager import ConfigManager
from .engine import find_7z_executable, find_winrar_executable

# 二次元与 ACG 社区经典预设解压密码
DEFAULT_ACG_PASSWORDS: List[str] = [
    # 知名 ACG / Galgame 资源站与论坛
    "终点",
    "忧郁的loli",
    "初音",
    "hpoi",
    "acg",
    "2dfan",
    "kdays",
    "绯月",
    "sstm",
    "gmgard",
    "绅士仓库",
    "acg18",
    "琉璃神社",
    "acg狗狗",
    "91acg",
    "acg.tf",
    "acg和谐阵线",
    "touchgal",
    "御所",
    "傲娇零次元",
    "天使动漫",
    "星空",
    "zodgame",
    "gggal",
    "galgame",
    "cngal",
    # 常用站点网址密码
    "www.2dfan.com",
    "2dfan.com",
    "acgng.com",
    "www.say-huahuo.com",
    "忧郁的loli.com",
    "sstm.moe",
    "gmgard.com",
    "hpoi.net.cn",
    "liuli.cat",
    "liuli.pw",
    "hacg.cat",
    "cngal.org",
    "kfmax",
    # 社区高频提取码 / 默认通用密码
    "1234",
    "123456",
    "password",
    "acg123",
    "acgzone",
    "acgfun",
    "bilibili",
    "acfun"
]

CONFIG_KEY = "archive_password_book"


class AcgPasswordBook:
    """ACG 密码本管理器"""

    def __init__(self):
        self.config = ConfigManager()

    def get_custom_passwords(self) -> List[str]:
        """获取用户自定义保存的历史密码列表"""
        cfg = self.config.get_plugin_config(CONFIG_KEY, {})
        return cfg.get("custom_passwords", [])

    def get_all_passwords(self) -> List[str]:
        """获取所有可用密码（用户自定义优先，去重保序）"""
        custom = self.get_custom_passwords()
        seen = set()
        result = []
        for pwd in custom + DEFAULT_ACG_PASSWORDS:
            p = pwd.strip()
            if p and p not in seen:
                seen.add(p)
                result.append(p)
        return result

    def add_password(self, password: str) -> bool:
        """添加或更新自定义密码至头部"""
        p = password.strip()
        if not p:
            return False
        custom = self.get_custom_passwords()
        if p in custom:
            custom.remove(p)
        custom.insert(0, p)
        cfg = self.config.get_plugin_config(CONFIG_KEY, {})
        cfg["custom_passwords"] = custom[:500]  # 最多缓存 500 个自定义密码
        self.config.set_plugin_config(CONFIG_KEY, cfg)
        return True

    def remove_password(self, password: str) -> bool:
        """删除用户自定义密码"""
        p = password.strip()
        custom = self.get_custom_passwords()
        if p in custom:
            custom.remove(p)
            cfg = self.config.get_plugin_config(CONFIG_KEY, {})
            cfg["custom_passwords"] = custom
            self.config.set_plugin_config(CONFIG_KEY, cfg)
            return True
        return False

    def reset_custom_passwords(self):
        """清空用户自定义密码"""
        cfg = self.config.get_plugin_config(CONFIG_KEY, {})
        cfg["custom_passwords"] = []
        self.config.set_plugin_config(CONFIG_KEY, cfg)

    def export_passwords(self, target_file: str) -> bool:
        """导出全部密码到文本文件"""
        try:
            pwds = self.get_all_passwords()
            with open(target_file, "w", encoding="utf-8") as f:
                for p in pwds:
                    f.write(p + "\n")
            return True
        except Exception:
            return False

    def import_passwords(self, source_file: str) -> int:
        """从文本文件导入密码（每行一个）"""
        if not os.path.isfile(source_file):
            return 0
        added = 0
        try:
            with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        if self.add_password(line):
                            added += 1
        except Exception:
            pass
        return added


def check_archive_encryption_status(archive_path: str) -> Tuple[bool, bool, Optional[str]]:
    """
    检查归档文件是否加密。
    返回 (is_encrypted, is_header_encrypted, first_member_name)
    """
    if not os.path.isfile(archive_path):
        return False, False, None

    ext = os.path.splitext(archive_path)[1].lower()

    # 1. 尝试 Python zipfile
    if ext == ".zip":
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                has_enc = False
                first_enc_member = None
                for info in zf.infolist():
                    if info.flag_bits & 0x1:
                        has_enc = True
                        if not first_enc_member and not info.is_dir():
                            first_enc_member = info.filename
                if has_enc:
                    return True, False, first_enc_member
                return False, False, None
        except Exception:
            pass

    # 2. 尝试 7-Zip CLI 探测
    p7z = find_7z_executable()
    if p7z:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        cmd = [p7z, "l", "-slt", "-p", archive_path]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=15
            )
            # 如果退出码为 2 且提示 Wrong password / Enter password，表示文件头加密 (Header Encrypted)
            output = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode != 0 and any(k in output for k in ("Wrong password", "Enter password", "Can not open the file as archive")):
                return True, True, None

            first_member = None
            has_encrypted_entry = False
            cur_path = None

            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("Path = "):
                    p = line[7:].strip()
                    if p != archive_path:
                        cur_path = p
                elif line.startswith("Encrypted = "):
                    enc = line[12:].strip()
                    if enc == "+":
                        has_encrypted_entry = True
                        if not first_member and cur_path:
                            first_member = cur_path

            if has_encrypted_entry:
                return True, False, first_member

            # 如果没有标记 Encrypted = + 且 proc.returncode == 0，则未加密
            if proc.returncode == 0:
                return False, False, None
        except Exception:
            pass

    return False, False, None


def test_single_password(
    archive_path: str,
    password: str,
    target_member: Optional[str] = None,
    header_encrypted: bool = False
) -> bool:
    """
    极速测试单个密码是否正确（毫秒级试探，不完整解压大文件）
    """
    if not os.path.isfile(archive_path):
        return False

    ext = os.path.splitext(archive_path)[1].lower()

    # 1. Zipfile 内置验证
    if ext == ".zip" and not header_encrypted:
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                member_to_test = None
                if target_member:
                    member_to_test = target_member
                else:
                    for info in zf.infolist():
                        if (info.flag_bits & 0x1) and not info.is_dir():
                            member_to_test = info.filename
                            break

                if member_to_test:
                    pwd_bytes = password.encode("utf-8")
                    with zf.open(member_to_test, "r", pwd=pwd_bytes) as fp:
                        fp.read(128)  # 尝试读取前 128 字节校验 CRC
                    return True
        except (RuntimeError, zipfile.BadZipFile):
            return False
        except Exception:
            pass

    # 2. 7-Zip CLI 验证
    p7z = find_7z_executable()
    if p7z:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if header_encrypted:
            # 文件头加密直接通过 list 检验
            cmd = [p7z, "l", f"-p{password}", archive_path]
        else:
            # 内容加密通过 test 检验首个成员（或全量极速测试）
            cmd = [p7z, "t", archive_path, f"-p{password}", "-y"]
            if target_member:
                cmd.append(target_member)

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=5
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode == 0:
                if "Wrong password" not in output and "CRC Failed" not in output:
                    return True
            return False
        except Exception:
            return False

    # 3. WinRAR 验证
    p_rar = find_winrar_executable()
    if p_rar:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        cmd = [p_rar, "t", f"-p{password}", "-y", archive_path]
        if target_member:
            cmd.append(target_member)
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=5
            )
            if proc.returncode == 0:
                return True
        except Exception:
            pass

    return False


test_single_password.__test__ = False
verify_single_password = test_single_password


def auto_match_archive_password(
    archive_path: str,
    candidates: Optional[List[str]] = None,
    on_progress: Optional[Callable[[str, int, int], None]] = None
) -> Optional[str]:
    """
    自动试探匹配归档包密码。
    如果匹配成功，返回匹配到的密码字符串；未加密返回空字符串 ""；失败返回 None。
    """
    is_enc, is_hdr, target_member = check_archive_encryption_status(archive_path)
    if not is_enc:
        return ""

    if candidates is None:
        book = AcgPasswordBook()
        candidates = book.get_all_passwords()

    total = len(candidates)
    for idx, pwd in enumerate(candidates):
        if on_progress:
            on_progress(pwd, idx + 1, total)

        if test_single_password(archive_path, pwd, target_member=target_member, header_encrypted=is_hdr):
            # 记录成功密码到自定义本首位
            try:
                AcgPasswordBook().add_password(pwd)
            except Exception:
                pass
            return pwd

    return None
