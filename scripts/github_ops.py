"""
GitHub 认证与凭据获取模块 (scripts/github_ops.py)
优先读取环境变量 GITHUB_TOKEN / GH_TOKEN，
若无则自动从 Windows 凭据管理器探测 Git 凭据。
"""

import os
import sys
import ctypes
from ctypes import wintypes
from typing import Optional


class CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD),
        ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR),
        ('Comment', wintypes.LPWSTR),
        ('LastWritten', wintypes.FILETIME),
        ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(ctypes.c_char)),
        ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD),
        ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR),
        ('UserName', wintypes.LPWSTR),
    ]


def get_token() -> Optional[str]:
    """获取当前可用的 GitHub 访问令牌"""
    # 1. 优先读取环境变量
    env_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env_token and env_token.strip():
        return env_token.strip()

    # 2. Windows 平台从凭据管理器中读取 Git 凭据
    if sys.platform == "win32":
        try:
            advapi32 = ctypes.windll.advapi32
            CredReadW = advapi32.CredReadW
            CredReadW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                ctypes.POINTER(ctypes.POINTER(CREDENTIAL))
            ]
            CredReadW.restype = wintypes.BOOL

            candidate_targets = [
                'git:https://yaoming00268@github.com',
                'git:https://github.com',
                'LegacyGeneric:target=git:https://github.com',
            ]
            for target in candidate_targets:
                pcred = ctypes.POINTER(CREDENTIAL)()
                if CredReadW(target, 1, 0, ctypes.byref(pcred)):
                    cred = pcred.contents
                    raw_bytes = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
                    token = raw_bytes.decode('utf-16-le') if b'\x00' in raw_bytes else raw_bytes.decode('utf-8')
                    advapi32.CredFree(pcred)
                    if token and token.strip():
                        return token.strip()
        except Exception as e:
            print(f"[-] 从 Windows 凭据管理器读取 Token 异常: {e}")

    return None
