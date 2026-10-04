/**
 * B站 / YouTube 媒体收割与大会员高阶解析引擎 (Media Engine)
 * 支持 SESSDATA 凭据持久化与多策略清洗
 * 支持 4K 超清、1080P 60帧、1080P高码率、杜比全景声、Hi-Res 无损 DASH 音画流深度解析
 */

const MediaEngine = (function () {
  const STORAGE_KEY_COOKIE = "chieri_bili_sessdata";
  const queue = [];

  // --- Cookie Parsing & Normalization ---
  function normalizeCookie(raw) {
    if (!raw || typeof raw !== "string") return "";
    let str = raw.trim();
    if (!str) return "";

    // Strip codeblock or outer quotes
    if (str.startsWith("```") && str.endsWith("```")) {
      str = str.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
    }
    if ((str.startsWith('"') && str.endsWith('"')) || (str.startsWith("'") && str.endsWith("'"))) {
      str = str.slice(1, -1).trim();
    }

    // Try parsing as JSON array (Cookie-Editor format)
    try {
      const parsed = JSON.parse(str);
      if (Array.isArray(parsed)) {
        const parts = [];
        for (const item of parsed) {
          if (item && item.name && item.value !== undefined) {
            parts.push(`${item.name}=${item.value}`);
          }
        }
        if (parts.length > 0) return parts.join("; ");
      } else if (typeof parsed === "object" && parsed !== null) {
        const parts = [];
        for (const [k, v] of Object.entries(parsed)) {
          if (v !== undefined) parts.push(`${k}=${v}`);
        }
        if (parts.length > 0) return parts.join("; ");
      }
    } catch (_) {}

    // Regex fallback for SESSDATA
    if (!str.includes("SESSDATA=")) {
      const match = str.match(/(?:SESSDATA\s*[:=]\s*["']?|["']SESSDATA["']\s*[:=]\s*["']?)([a-zA-Z0-9%*_-]{16,})/i);
      if (match) {
        return `SESSDATA=${match[1]}`;
      }
      if (str.length >= 24 && !str.includes(" ") && !str.includes(";") && !str.includes("/")) {
        return `SESSDATA=${str}`;
      }
    }

    return str;
  }

  function getSavedCookie() {
    return localStorage.getItem(STORAGE_KEY_COOKIE) || "";
  }

  function saveCookie(cookieStr) {
    const norm = normalizeCookie(cookieStr);
    localStorage.setItem(STORAGE_KEY_COOKIE, norm);
    return norm;
  }

  // --- Native or Fetch HTTP Client ---
  async function performRequest(url, options = {}) {
    const method = options.method || "GET";
    const headers = options.headers || {};
    const body = options.body || "";

    // Prefer AndroidBridge if available to avoid CORS and header restrictions
    if (window.AndroidBridge && window.AndroidBridge.httpRequest) {
      try {
        const resStr = window.AndroidBridge.httpRequest(method, url, JSON.stringify(headers), body);
        const resObj = JSON.parse(resStr);
        if (resObj.ok) {
          try {
            return JSON.parse(resObj.data);
          } catch (_) {
            return resObj.data;
          }
        } else {
          throw new Error(resObj.error || `HTTP 错误: ${resObj.status}`);
        }
      } catch (e) {
        console.warn("AndroidBridge httpRequest failed, falling back to fetch:", e);
      }
    }

    // Web fetch fallback
    const resp = await fetch(url, {
      method: method,
      headers: headers
    });
    if (!resp.ok) {
      throw new Error(`网络响应错误: ${resp.status}`);
    }
    return await resp.json();
  }

  // --- Account & VIP Verification ---
  async function checkAccountStatus(customCookie = null) {
    const cookie = customCookie !== null ? normalizeCookie(customCookie) : getSavedCookie();
    const headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Referer": "https://www.bilibili.com"
    };
    if (cookie) {
      headers["Cookie"] = cookie;
    }

    try {
      const data = await performRequest("https://api.bilibili.com/x/web-interface/nav", { headers });
      if (data && data.code === 0 && data.data) {
        const d = data.data;
        const isLogin = Boolean(d.isLogin);
        if (isLogin) {
          const uname = String(d.uname || "");
          const mid = Number(d.mid || 0);
          const vipType = Number(d.vipType || 0);
          const vipStatus = Number(d.vipStatus || 0);
          let vipLabel = "";
          if (d.vip_label && typeof d.vip_label === "object") {
            vipLabel = d.vip_label.text || "";
          }

          const isVip = vipStatus === 1 && vipType > 0;
          if (isVip) {
            if (!vipLabel) vipLabel = vipType === 2 ? "年度大会员" : "大会员";
            return {
              is_login: true,
              is_vip: true,
              uname: uname,
              mid: mid,
              vip_type: vipType,
              vip_label: vipLabel,
              face: d.face || "",
              message: `大会员: ${uname} (4K/1080P60/杜比全景声已全部解锁)`
            };
          } else {
            return {
              is_login: true,
              is_vip: false,
              uname: uname,
              mid: mid,
              vip_type: 0,
              vip_label: "普通会员",
              face: d.face || "",
              message: `已登录: ${uname} (最高支持 1080P 高清)`
            };
          }
        }
      }
      return {
        is_login: false,
        is_vip: false,
        uname: "",
        mid: 0,
        vip_type: 0,
        vip_label: "未登录",
        message: "未登录 (最高支持 480P，建议配置 SESSDATA 解锁全规格)"
      };
    } catch (e) {
      return {
        is_login: false,
        is_vip: false,
        uname: "",
        mid: 0,
        vip_type: 0,
        vip_label: "离线/未认证",
        message: `检测状态: ${e.message || "未能连接 B站 服务器"}`
      };
    }
  }

  // --- Extract BV Number ---
  function extractBvid(input) {
    if (!input) return null;
    const trimmed = input.trim();
    const bvMatch = trimmed.match(/(BV[a-zA-Z0-9]{10})/i);
    if (bvMatch) return bvMatch[1];

    const avMatch = trimmed.match(/av(\d+)/i);
    if (avMatch) return `av${avMatch[1]}`;

    return null;
  }

  // Quality Map
  const QUALITY_NAMES = {
    127: "8K 超高清 (VIP)",
    126: "1080P 杜比视界 (VIP)",
    125: "HDR 真彩 (VIP)",
    120: "4K 超清 (VIP)",
    116: "1080P 60帧 (VIP)",
    112: "1080P 高码率 (VIP)",
    80: "1080P 高清",
    74: "720P 60帧 (VIP)",
    64: "720P 高清",
    32: "480P 清晰",
    16: "360P 流畅"
  };

  const VIP_QN_SET = new Set([127, 126, 125, 120, 116, 112, 74]);

  // --- Parse Bilibili Video ---
  async function parseBilibiliVideo(bvid) {
    const cookie = getSavedCookie();
    const headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Referer": "https://www.bilibili.com"
    };
    if (cookie) headers["Cookie"] = cookie;

    // 1. Fetch Video Info
    const infoUrl = `https://api.bilibili.com/x/web-interface/view?bvid=${bvid}`;
    const infoData = await performRequest(infoUrl, { headers });
    if (!infoData || infoData.code !== 0 || !infoData.data) {
      throw new Error((infoData && infoData.message) || "无法获取视频元数据，请检查 BV 号是否正确");
    }

    const d = infoData.data;
    const title = d.title || "未知视频";
    const cover = d.pic || "";
    const owner = (d.owner && d.owner.name) || "未知UP主";
    const duration = d.duration || 0;
    const pages = (d.pages || []).map((p) => ({
      cid: p.cid,
      page: p.page,
      part: p.part || `P${p.page}`,
      duration: p.duration
    }));

    const defaultCid = pages.length > 0 ? pages[0].cid : d.cid;

    // 2. Fetch Play Streams (fnval=4048 for DASH 4K/Dolby/HDR)
    const playUrl = `https://api.bilibili.com/x/player/playurl?bvid=${bvid}&cid=${defaultCid}&qn=120&fnval=4048&fnver=0&fourk=1`;
    let streamData = null;
    try {
      streamData = await performRequest(playUrl, { headers });
    } catch (e) {
      console.warn("PlayUrl request failed:", e);
    }

    const videoStreams = [];
    const audioStreams = [];
    let hasVipStreams = false;

    if (streamData && streamData.code === 0 && streamData.data && streamData.data.dash) {
      const dash = streamData.data.dash;

      // Video tracks
      const vTracks = dash.video || [];
      const seenQn = new Set();
      for (const v of vTracks) {
        const qn = v.id;
        const qnKey = `${qn}_${v.codecs}`;
        if (seenQn.has(qnKey)) continue;
        seenQn.add(qnKey);

        const isVip = VIP_QN_SET.has(qn);
        if (isVip) hasVipStreams = true;

        videoStreams.push({
          id: qn,
          label: QUALITY_NAMES[qn] || `${qn}P 画质`,
          codecs: v.codecs || "AVC",
          width: v.width,
          height: v.height,
          frameRate: v.frameRate || "30",
          bandwidth: v.bandwidth,
          url: v.baseUrl || (v.backupUrl && v.backupUrl[0]) || "",
          isVip: isVip
        });
      }

      // Audio tracks
      const aTracks = dash.audio || [];
      for (const a of aTracks) {
        let label = "标准音频";
        if (a.id === 30280) label = "320kbps 超高音质";
        else if (a.id === 30232) label = "132kbps 高清音质";
        else if (a.id === 30216) label = "64kbps 流畅音质";

        audioStreams.push({
          id: a.id,
          label: label,
          codecs: a.codecs || "mp4a",
          bandwidth: a.bandwidth,
          url: a.baseUrl || (a.backupUrl && a.backupUrl[0]) || "",
          isVip: false
        });
      }

      // Dolby Atmos Audio
      if (dash.dolby && dash.dolby.audio) {
        for (const da of dash.dolby.audio) {
          hasVipStreams = true;
          audioStreams.unshift({
            id: da.id || 30250,
            label: "👑 杜比全景声 (Dolby Atmos)",
            codecs: da.codecs || "ec-3",
            bandwidth: da.bandwidth,
            url: da.baseUrl || (da.backupUrl && da.backupUrl[0]) || "",
            isVip: true
          });
        }
      }

      // Hi-Res Lossless Audio
      if (dash.flac && dash.flac.audio) {
        hasVipStreams = true;
        audioStreams.unshift({
          id: dash.flac.audio.id || 30251,
          label: "👑 Hi-Res 无损原声 (FLAC)",
          codecs: "flac",
          bandwidth: dash.flac.audio.bandwidth,
          url: dash.flac.audio.baseUrl || (dash.flac.audio.backupUrl && dash.flac.audio.backupUrl[0]) || "",
          isVip: true
        });
      }
    }

    return {
      platform: "bilibili",
      bvid: bvid,
      title: title,
      owner: owner,
      cover: cover,
      duration: duration,
      pages: pages,
      videoStreams: videoStreams,
      audioStreams: audioStreams,
      hasVipStreams: hasVipStreams
    };
  }

  // --- Universal Parser Router ---
  async function parseMediaUrl(inputUrl) {
    const raw = inputUrl.trim();
    const bvid = extractBvid(raw);

    if (bvid) {
      return await parseBilibiliVideo(bvid);
    }

    // YouTube Detection
    const ytMatch = raw.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/))([a-zA-Z0-9_-]{11})/i);
    if (ytMatch) {
      const ytId = ytMatch[1];
      return {
        platform: "youtube",
        id: ytId,
        title: `YouTube 视频 [${ytId}]`,
        owner: "YouTube 创作者",
        cover: `https://img.youtube.com/vi/${ytId}/hqdefault.jpg`,
        duration: 0,
        pages: [],
        videoStreams: [
          { id: 1080, label: "1080P 超高清 60FPS", codecs: "VP9/Opus", isVip: false, url: `https://www.youtube.com/watch?v=${ytId}` },
          { id: 720, label: "720P 高清", codecs: "H.264", isVip: false, url: `https://www.youtube.com/watch?v=${ytId}` }
        ],
        audioStreams: [
          { id: 128, label: "Opus 160kbps 高保真音频", isVip: false, url: `https://www.youtube.com/watch?v=${ytId}` }
        ],
        hasVipStreams: false
      };
    }

    throw new Error("未能识别链接类型，请粘贴 B站 视频 (BV/av号) 或 YouTube 链接！");
  }

  // --- Task Queue Manager ---
  function addTask(parsedResult, selectedFormat, selectedStream) {
    const task = {
      id: "task_" + Date.now().toString(36) + "_" + Math.random().toString(36).substr(2, 5),
      title: parsedResult.title,
      platform: parsedResult.platform,
      format: selectedFormat,
      streamLabel: selectedStream ? selectedStream.label : selectedFormat.toUpperCase(),
      streamUrl: selectedStream ? selectedStream.url : "",
      status: "ready", // ready, downloading, completed, failed
      progress: 0,
      speed: "待处理"
    };
    queue.unshift(task);
    return task;
  }

  function simulateDownload(task, onProgress, onComplete) {
    task.status = "downloading";
    task.progress = 0;

    const interval = setInterval(() => {
      task.progress += Math.floor(Math.random() * 20) + 12;
      task.speed = (Math.random() * 4 + 3).toFixed(1) + " MB/s";

      if (task.progress >= 100) {
        task.progress = 100;
        task.status = "completed";
        task.speed = "已完成";
        clearInterval(interval);
        if (onComplete) onComplete(task);
      } else {
        if (onProgress) onProgress(task);
      }
    }, 250);
  }

  return {
    normalizeCookie,
    getSavedCookie,
    saveCookie,
    checkAccountStatus,
    parseMediaUrl,
    addTask,
    getQueue: () => queue,
    simulateDownload
  };
})();

window.MediaEngine = MediaEngine;
