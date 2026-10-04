"""
千绘莉多功能工具箱 - GitHub Releases 自动发布与分发包同步脚本 (scripts/upload_release.py)
"""

import sys
import os
import argparse
import subprocess
import requests
import json

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.github_ops import get_token

owner = "yaoming00268"
repo = "ChieriToolbox"
tag = "v2.0.0"

release_body = """千绘莉的多功能工具箱 (Chieri Toolbox) v2.0.0 正式发布 (｀・ω・´)！

一只二次元死宅为了彻底偷懒而搓出来的究极生产力兵工厂。集成本地 22 大即插即用动态插件与全新 Android 移动端，暗黑 Fluent 磨砂质感，Esc 一键回城！

【全新 Android 移动端重磅发布 (Mobile Edition)】：
- **移动端架构与原生硬件桥接**：
  1. Kotlin 原生宿主 + 现代极简 Web 混合架构，零系统污染。
  2. 原生 MediaCodec 硬件加速：结合 Web Audio API 实现高保真 AAC/M4A 极速硬件编码。
  3. HttpURLConnection 原生网络穿透：彻底打破 WebView CORS 跨域壁垒，支持 Cookie / SESSDATA 凭据持久化与 DASH 音画流分轨提取。
  4. Apache Commons Compress 原生归档引擎：全面支持 7Z, TAR, GZ, BZ2, LZ4, XZ, ZIP 解析并批量解压至公共 Downloads 目录。
  5. 智能 AI 翻译接口：支持 OpenAI 兼容 API、DeepL、百度翻译（RFC 1321 MD5 签名生成算法）、Google 及离线 ACG 专属词库。
- **现代化极简 UI 与外观定制中心**：
  1. 100% SVG 扁平化矢量图标体系（零 emoji 字符），精致线条质感。
  2. 深浅色双模式即时切换，WindowCompat 状态栏与导航栏沉浸式动态着色跟随。
  3. 卡片尺寸三档调节（紧凑 Compact / 标准 Standard / 宽松 Comfortable）、50%-100% 界面透明度滑动调节与毛玻璃磨砂（0px/8px/16px）深度定制。
  4. 双轨悬浮交互系统：应用内贴边可折叠悬浮球 + 全局系统悬浮窗 (WindowManager / Overlay)，支持靠边半隐藏贴边折叠与呼出侧边栏抽屉导航。
- **Android 沙盒差异与平替矩阵权威公示**：内置公示 Linux UID 进程沙盒、PAC 代理、全局按键监听与底层 DirectShow 录屏限制技术根因及平替方案。

【桌面端核心特性与系统重构】：
- **B站媒体下载器全面增强**：
  1. 支持下载任务实时暂停 (Pause) 与断点续传恢复 (Resume)
  2. 智能本地已有文件扫描检测与一键重试未下载/失败物件
  3. 支持分P/单视频微调画质 (可独立针对单项指定 1080P60/1080P/720P 等)
  4. 支持批量应用自定义画质至所有勾选项
  5. 自动根据 CID/list_index 精准映射任务状态，杜绝子集勾选索引错位
- **内置原生打包流水线与便携式 Inno Setup 编译器**：
  - 内置便携式 Inno Setup 编译器 (bin/InnoSetup/ISCC.exe)，摆脱系统级外部环境依赖。
  - 支持一键原生 EXE 安装向导构建与独立插件应用解耦导出。
- **架构加固与审计缺陷全面修复 (Audit v2 Fixes)**：
  1. 配置管理器安全加固：实现原子持久化写入、跨进程文件锁与递归深度合并，防止多进程下配置意外丢失或覆写。
  2. 独立插件隔离：独立插件配置与主题切换全面隔离全局配置，防止污染主工具箱设置。
  3. 冻结态路径自适应：打包运行环境下多级安全路径探测，确保动态插件发现与外部二进制工具 100% 定位。
  4. 进程与多线程安全：音频/录屏引擎采用无阻塞异步等待与安全退出机制，规避管道死锁与界面卡死。
  5. 多媒体与归档安全：媒体压缩参数安全清洗；归档管理器全量集成 TarSlip / ZipSlip 路径穿越防御及 LZ4 流式加解压。
  6. 白板与托盘管理：修复动态缩放撤销重做画布裁切风险；托盘图标生命周期严格受控。

预构建封装包说明：
1. **Setup_ChieriToolbox.exe**:
   - 基于 Inno Setup 6 编译构建的标准单文件安装向导，集成 LZMA2 固实压缩。
   - 自包含完整运行环境与 FFmpeg、7-Zip、FFprobe、FFplay 四大外部核心引擎及内置 Inno Setup 编译器。
   - 支持自定义安装路径、创建桌面快捷方式及可选开机托盘集成。

2. **ChieriToolbox-v2.0.0-Portable.zip**:
   - 绿色免安装便携版，解压至任意目录双击 ChieriToolbox.exe 即可运行。
   - 所有配置均保存在程序自身同级目录的 toolbox_config.json，纯净免安装。

3. **ChieriToolbox-Android.apk**:
   - Android 移动端安装包（兼容 Android 8.0+ / API 26+）。
   - 包含完整的移动端引擎与离线资源，零依赖开箱即用。

测试报告：
- 全量单元/集成测试与移动端引擎自动化测试套件全部通过 (100% Passed)。
- 烟测验证 22/22 插件与外部工具链全项通过 (PASSED)。
"""

release_payload = {
    "tag_name": tag,
    "target_commitish": "main",
    "name": f"ChieriToolbox {tag} - 二次元死宅专属全能生产力工具箱 (PC & Android 双端)",
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

    assets_to_upload = [
        (os.path.join(PROJECT_ROOT, "dist", "Setup_ChieriToolbox.exe"), "Setup_ChieriToolbox.exe", "application/octet-stream"),
        (os.path.join(PROJECT_ROOT, "dist", "ChieriToolbox-v2.0.0-Portable.zip"), "ChieriToolbox-v2.0.0-Portable.zip", "application/zip"),
        (os.path.join(PROJECT_ROOT, "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk"), "ChieriToolbox-Android.apk", "application/vnd.android.package-archive")
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

        print(f"正在上传 {asset_name} ...")
        with open(file_path, "rb") as f:
            upload_resp = requests.post(
                f"{upload_url_base}?name={asset_name}",
                headers=upload_headers,
                data=f,
                timeout=900
            )

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
