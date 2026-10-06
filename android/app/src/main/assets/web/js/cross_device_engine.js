/**
 * 千绘莉工具箱 (Chieri Toolbox Mobile) - 双端互联与电脑云超分引擎 (CrossDeviceEngine)
 * 纯局域网轻量通信：
 * 1. UDP/HTTP 自动探测同一 Wi-Fi 下的 PC 宿主
 * 2. 移动端将大图无缝投送给 PC 执行 Real-CUGAN / Real-ESRGAN 超分并自动保存至手机相册
 * 3. Chieri Drop 局域网文件闪传与跨端剪贴板实时流转
 */

(function (global) {
  "use strict";

  const CrossDeviceEngine = {
    connectedServerUrl: localStorage.getItem("chieri_cloud_server_url") || "",
    connectedHostName: localStorage.getItem("chieri_cloud_hostname") || "",

    /**
     * 发现局域网内的 PC 宿主
     */
    async discoverPC() {
      if (global.Android && typeof global.Android.discoverLocalCloudPC === "function") {
        try {
          const raw = global.Android.discoverLocalCloudPC();
          const list = JSON.parse(raw);
          if (Array.isArray(list) && list.length > 0) {
            return list;
          }
        } catch (e) {
          console.error("discoverPC native error:", e);
        }
      }

      // 如果原生 UDP 没搜到，尝试本地通用 IP 段常用端口探测
      const candidates = [
        this.connectedServerUrl,
        "http://192.168.1.100:8765",
        "http://192.168.0.100:8765",
        "http://127.0.0.1:8765"
      ].filter(Boolean);

      const found = [];
      for (const url of candidates) {
        try {
          const res = await this.pingServer(url);
          if (res.ok) {
            found.push({
              url: url,
              hostname: res.hostname || "PC-Desktop",
              port: res.port || 8765
            });
            break;
          }
        } catch (_) {}
      }
      return found;
    },

    /**
     * 测试指定服务器连接
     */
    async pingServer(serverUrl) {
      const cleanUrl = serverUrl.replace(/\/+$/, "");
      if (global.Android && typeof global.Android.httpRequest === "function") {
        try {
          const respStr = global.Android.httpRequest("GET", cleanUrl + "/api/ping", null, null);
          const r = JSON.parse(respStr);
          if (r.ok && r.data) {
            const data = JSON.parse(r.data);
            return { ok: true, hostname: data.hostname, version: data.version, port: data.port };
          }
        } catch (e) {
          return { ok: false, error: e.message };
        }
      }

      try {
        const resp = await fetch(cleanUrl + "/api/ping", { method: "GET", mode: "cors" });
        if (resp.ok) {
          const data = await resp.json();
          return { ok: true, hostname: data.hostname, version: data.version, port: data.port };
        }
      } catch (e) {
        return { ok: false, error: e.message };
      }
      return { ok: false, error: "无法连接到该地址" };
    },

    /**
     * 保存当前连接的服务器信息
     */
    setConnectedServer(url, hostname) {
      this.connectedServerUrl = url;
      this.connectedHostName = hostname || "PC 宿主";
      localStorage.setItem("chieri_cloud_server_url", url);
      localStorage.setItem("chieri_cloud_hostname", this.connectedHostName);
    },

    /**
     * 提交图片至电脑进行云超分
     */
    async upscaleImageOnPC(imageBase64, options = {}) {
      if (!this.connectedServerUrl) {
        throw new Error("请先连接到同一 Wi-Fi 下的电脑宿主！");
      }

      const scale = options.scale || 2;
      const model = options.model || "realesr-animevideov3";
      const denoise = options.denoise || "conservative";

      if (global.Android && typeof global.Android.uploadImageForCloudUpscale === "function") {
        const respStr = global.Android.uploadImageForCloudUpscale(
          this.connectedServerUrl,
          imageBase64,
          model,
          scale,
          denoise
        );
        const res = JSON.parse(respStr);
        if (!res.ok) {
          throw new Error(res.error || "云端超分处理失败");
        }
        return res;
      }

      // Web/Dev Fallback
      const blob = await (await fetch(imageBase64)).blob();
      const resp = await fetch(this.connectedServerUrl.replace(/\/+$/, "") + "/api/upscale", {
        method: "POST",
        headers: {
          "Content-Type": "image/png",
          "X-Scale": String(scale),
          "X-Model": model,
          "X-Denoise": denoise
        },
        body: blob
      });

      if (!resp.ok) {
        throw new Error(`电脑端超分错误 HTTP ${resp.status}`);
      }

      const outBlob = await resp.blob();
      const previewUrl = URL.createObjectURL(outBlob);
      return {
        ok: true,
        previewBase64: previewUrl,
        costTime: resp.headers.get("X-Process-Time") || "1.2s",
        filename: `upscale_${scale}x_${Date.now()}.png`
      };
    },

    /**
     * Chieri Drop 投送文件至电脑
     */
    async sendFileToPC(base64Data, filename) {
      if (!this.connectedServerUrl) {
        throw new Error("请先连接到电脑宿主！");
      }
      if (global.Android && typeof global.Android.sendDropFileToPC === "function") {
        const respStr = global.Android.sendDropFileToPC(this.connectedServerUrl, base64Data, filename);
        return JSON.parse(respStr);
      }
      throw new Error("当前环境不支持原生文件投送");
    },

    /**
     * 跨端剪贴板同步
     */
    async syncClipboard(text = "", mode = "send") {
      if (!this.connectedServerUrl) {
        throw new Error("请先连接到电脑宿主！");
      }
      if (global.Android && typeof global.Android.syncClipboardWithPC === "function") {
        const respStr = global.Android.syncClipboardWithPC(this.connectedServerUrl, text, mode);
        return JSON.parse(respStr);
      }
      return { ok: false, error: "环境不支持" };
    }
  };

  global.CrossDeviceEngine = CrossDeviceEngine;
})(typeof window !== "undefined" ? window : global);
