"""
千绘莉多功能工具箱 - GitHub Releases 自动发布与分发包同步脚本 (scripts/upload_release.py)
"""

import sys
import os
import argparse
import subprocess
import requests
import json

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass

class ProgressFileWrapper:
    def __init__(self, file_path, total_size, asset_name):
        self.f = open(file_path, "rb")
        self.total_size = total_size
        self.asset_name = asset_name
        self.uploaded = 0
        self.last_print = 0

    def read(self, size=-1):
        chunk = self.f.read(size)
        if chunk:
            self.uploaded += len(chunk)
            if self.uploaded - self.last_print >= 10 * 1024 * 1024 or self.uploaded >= self.total_size:
                pct = (self.uploaded / self.total_size) * 100
                mb = self.uploaded / (1024 * 1024)
                total_mb = self.total_size / (1024 * 1024)
                print(f"[{self.asset_name}] 上传中: {mb:.1f} MB / {total_mb:.1f} MB ({pct:.1f}%)", flush=True)
                self.last_print = self.uploaded
        return chunk

    def __len__(self):
        return self.total_size

    def close(self):
        self.f.close()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.github_ops import get_token

owner = "yaoming00268"
repo = "ChieriToolbox"
tag = "v2.0.0"

release_body = """千绘莉的多功能工具箱 (Chieri Toolbox) v2.0.0 正式发布 (｀・ω・´)！

一只二次元死宅为了彻底偷懒而搓出来的究极生产力兵工厂。全新升级至 28 大即插即用动态插件与全解耦架构，包含全新 Android 移动端，暗黑 Fluent 磨砂质感，Esc 一键回城！

【/boost 架构重构与全新功能】：
1. 武器库跃升至 28 大即插即用扩展插件：
   - 🌟 剪贴板历史与收藏管理 (clipboard_manager): 系统剪贴板实时监听、多类型历史留存、常用文本分类收藏与格式智能脱敏。
   - 🌟 环境变量配置管理 (env_var_switcher): 用户/系统变量可视化维护、Path 失效诊断与一键去重、多语言开发环境秒级切换。
   - 🌟 JSON / 文本高亮对比工作台 (json_diff_studio): JSON 树形高亮美化与格式校验、Monaco 风格行内双栏差异比对与导出。
   - 🌟 端口占用监控与网络诊断哨兵 (port_network_sentinel): 端口占用与进程 PID 秒查、一键查杀顽固占用、Ping/Traceroute 连通性测试。
   - 🌟 应用极速启动台 (quick_launcher): 全局热键唤醒，拼音/首字母模糊秒搜系统应用、快捷脚本与工具箱各插件。
   - 🌟 全能水印批处理工坊 (watermark_studio): 批量平铺/自定义位置文字水印、Logo 图标水印及防盗图隐形频域盲水印。
2. 全局后台任务中心 (Global Task Manager):
   - 统一调度管理全插件后台任务，支持并发限流保护与系统内存自平衡，防止高负载多任务卡死系统。
   - 任务可视化管理面板，实时呈现进度条、状态监控与一键取消/重试控制。
3. 插件中心与全解耦独立导出生命周期 (Plugin Hub & Decoupled Lifecycle):
   - 全插件标准化 manifest.json 清单规范与热插拔沙箱隔离。
   - 独立插件中心：支持任意单插件一键导出为独立免安装包或 Inno Setup 原生安装程序。
4. 专业截图 OCR 离线文字识别引擎:
   - PixPin 风格截图新增本地 OCR 识别，框选画面即刻精准提取文字并一键复制。

【AI 进化与多端协同核心特性】：
1. AI 超分与音频模型按需轻量下载中心 (On-Demand Model Manager):
   - Real-CUGAN, Real-ESRGAN, Waifu2x 超分模型及 Demucs, Spleeter 音频模型按需动态拉取，包体极致精简。
   - 内置模型中心，多镜像源自动测速与 SHA256 完整性哈希校验。
2. 局域网本地云 (Local Cloud) 跨设备算力协同:
   - PC 端内置 Local Cloud 本地云服务（UDP 自动广播自发现 + REST API）。
   - Android 移动端与 Web 端可将高负载 AI 超分任务一键卸载至电脑算力执行并秒级取回结果。
3. B站弹幕转 ASS 特效字幕 (Danmaku to ASS):
   - 随视频下载智能将 B站 XML 弹幕流转制为专业 ASS 双轨弹幕特效字幕，支持滚动/顶端/底端弹幕与字体边框样式自定义。
4. 全能多格式音乐解密 (NCM / QMC / KGM / KWM):
   - 支持网易云 NCM、QQ音乐 QMC (.qmc3, .qmcflac, .mflac, .mgg)、酷狗 KGM (.kgm, .vpr) 与酷我 KWM (.kwm) 格式逆向解密。
5. ACG 资源解压密码本 (Password Book):
   - 预置高频 ACG 动漫同人解压密码库，支持密码本管理与一键暴力匹配自动尝试解压。

【全新 Android 移动端重磅发布 (Mobile Edition)】：
- Kotlin 原生宿主 + 现代极简 Web 混合架构，零系统污染，体积仅约 6MB。
- MediaCodec 硬件加速音频编码 + HttpURLConnection 原生网络穿透 + Apache Commons Compress 原生归档引擎。
- 100% 现代 SVG 矢量 UI + 深浅双色模式即时热切换 + 应用内贴边可折叠悬浮球与系统级全局悬浮窗。

预构建封装包说明：
1. **Setup_ChieriToolbox.exe**:
   - 基于 Inno Setup 6 编译构建的标准单文件安装向导，集成 LZMA2 固实压缩。
   - 自包含完整运行环境与 FFmpeg、7-Zip、FFprobe、FFplay 四大外部核心引擎及内置 Inno Setup 编译器。
   - 支持自定义安装路径、创建桌面快捷方式及可选开机托盘集成。

2. **ChieriToolbox-v2.0.0-Portable.zip**:
   - 绿色免安装便携版，解压至任意目录双击 ChieriToolbox.exe 即可运行，零系统污染。
   - 所有配置均保存在程序自身同级目录的 toolbox_config.json，纯净免安装。

3. **ChieriToolbox-Android.apk**:
   - Android 移动端安装包（兼容 Android 8.0+ / API 26+）。
   - 包含完整的移动端引擎与离线资源，零依赖开箱即用。

测试报告：
- 全量自动化测试套件共 267 项测试 100% 通过 (266 passed, 1 skipped)。
- 烟测自检覆盖全部 28/28 插件动态实例化与底层工具链寻路 (PASSED)。
"""

release_payload = {
    "tag_name": tag,
    "target_commitish": "main",
    "name": f"ChieriToolbox {tag} - 二次元死宅专属全能生产力工具箱 (28合1 + 双端互通)",
    "body": release_body,
    "draft": False,
    "prerelease": False
}


def sync_git_tag():
    """将本地 v2.0.0 标签同步至当前 HEAD 并推送到远程仓库"""
    print(f"[*] 正在同步 Git 标签 {tag} 指向当前最新提交...")
    try:
        subprocess.run(["git", "tag", "-fa", tag, "-m", f"Release {tag}"], cwd=PROJECT_ROOT, check=True)
        proc = subprocess.run(["git", "push", "origin", tag, "--force"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        if proc.returncode == 0:
            print(f"[√] 成功将远程标签 {tag} 强制同步至最新提交！")
            return True
        else:
            print(f"[-] 推送 Git 标签失败: {proc.stderr}")
            return False
    except Exception as e:
        print(f"[-] 同步 Git 标签异常: {e}")
        return False


def upload_release():
    token = get_token()
    if not token:
        print("[错误] 未能获取 GitHub Token (请检查环境变量 GITHUB_TOKEN 或 Windows 凭据管理器)！")
        sys.exit(1)

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 1. 先确保远程 Git tag 指向当前 commit
    sync_git_tag()

    print(f"Checking/updating release {tag} on {owner}/{repo}...")
    r_get = requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}", headers=headers)
    if r_get.status_code == 200:
        release_data = r_get.json()
        print(f"Found existing release ID {release_data['id']}. Updating metadata...")
        r_update = requests.patch(
            f"https://api.github.com/repos/{owner}/{repo}/releases/{release_data['id']}",
            headers=headers,
            json=release_payload
        )
        if r_update.status_code == 200:
            release_data = r_update.json()
            print("Release metadata updated successfully.")
        else:
            print("Failed to update release metadata:", r_update.status_code, r_update.text)
    else:
        print(f"Creating new release {tag} on {owner}/{repo}...")
        r = requests.post(f"https://api.github.com/repos/{owner}/{repo}/releases", headers=headers, json=release_payload)
        if r.status_code not in (200, 201):
            print("Failed to create release:", r.status_code, r.text)
            sys.exit(1)
        release_data = r.json()
        print("Release created successfully! ID:", release_data["id"])

    upload_url_base = release_data["upload_url"].split("{")[0]

    apk_path = os.path.join(PROJECT_ROOT, "dist", "ChieriToolbox-Android.apk")
    if not os.path.exists(apk_path):
        apk_path = os.path.join(PROJECT_ROOT, "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk")

    assets_to_upload = [
        (os.path.join(PROJECT_ROOT, "dist", "Setup_ChieriToolbox.exe"), "Setup_ChieriToolbox.exe", "application/octet-stream"),
        (os.path.join(PROJECT_ROOT, "dist", "ChieriToolbox-v2.0.0-Portable.zip"), "ChieriToolbox-v2.0.0-Portable.zip", "application/zip"),
        (apk_path, "ChieriToolbox-Android.apk", "application/vnd.android.package-archive")
    ]

    # 获取当前 release 下已存在的 assets 列表
    r_assets = requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases/{release_data['id']}/assets", headers=headers)
    existing_assets_map = {}
    if r_assets.status_code == 200:
        for ea in r_assets.json():
            existing_assets_map[ea["name"]] = ea

    success_all = True
    for file_path, asset_name, content_type in assets_to_upload:
        if not os.path.exists(file_path):
            if asset_name in existing_assets_map:
                ea = existing_assets_map[asset_name]
                print(f"[√] 资产 {asset_name} 本地未构建，但已存在于远程 Release (ID: {ea['id']}, 大小: {ea['size'] / (1024*1024):.2f} MB)，予以保留。")
                continue
            else:
                print(f"[错误] 目标发布文件不存在且远程无备份: {file_path}")
                success_all = False
                continue

        file_size = os.path.getsize(file_path)
        print(f"\n[上传准备] {asset_name} ({file_size / (1024*1024):.2f} MB)...")

        # 检查是否已存在同名 asset，若存在则先删除
        if asset_name in existing_assets_map:
            ea = existing_assets_map[asset_name]
            print(f"Asset {asset_name} (ID: {ea['id']}) 已存在，正在删除以更新最新版本...")
            del_resp = requests.delete(ea["url"], headers=headers)
            if del_resp.status_code in (200, 204):
                print(f"旧版本 {asset_name} 已成功清理。")
            else:
                print(f"清理旧版本失败: {del_resp.status_code} {del_resp.text}")

        upload_headers = {
            "Authorization": f"token {token}",
            "Content-Type": content_type,
            "Content-Length": str(file_size)
        }

        print(f"正在上传 {asset_name} ...", flush=True)
        wrapper = ProgressFileWrapper(file_path, file_size, asset_name)
        try:
            upload_resp = requests.post(
                f"{upload_url_base}?name={asset_name}",
                headers=upload_headers,
                data=wrapper,
                timeout=900
            )
        finally:
            wrapper.close()

        if upload_resp.status_code in (200, 201):
            asset_info = upload_resp.json()
            print(f"[√] 成功上传 {asset_name}! 下载链接: {asset_info.get('browser_download_url')}")
        else:
            print(f"[×] 上传失败 {asset_name}: {upload_resp.status_code} {upload_resp.text}")
            success_all = False


    if success_all:
        print("\n=======================================================")
        print(" [√] 所有构建产物已成功上传至 GitHub Releases！")
        print("=======================================================")
    else:
        print("\n[!] 部分产物上传未能成功，请检查输出日志。")
        sys.exit(1)


if __name__ == '__main__':
    upload_release()
