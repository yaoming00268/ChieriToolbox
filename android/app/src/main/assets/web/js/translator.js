/**
 * 智能二次元与多模型 AI 翻译器 (Smart ACG & Multi-Model AI Translator)
 * 支持 OpenAI 兼容大模型 (DeepSeek / GPT-4o / Qwen)、DeepL、Google 翻译开放接口
 * 支持离线二次元专属词典与零延时本地速查
 */

const TranslatorEngine = (function () {
  const STORAGE_KEY_CONFIG = "chieri_trans_config";

  const defaultConfig = {
    provider: "openai", // 'openai' | 'deepl' | 'google' | 'baidu' | 'offline'
    baseUrl: "https://api.deepseek.com/v1",
    apiKey: "",
    model: "deepseek-chat",
    baiduAppId: "",
    baiduKey: "",
    systemPrompt: "你是一位精通中日英二次元、同人文化与多语言本地化的专业翻译专家。请准确、流畅地将用户给出的文本翻译为目标语言，保留专有名词与二次元语气风格，直接输出译文，不要多余闲聊。",
    useDictFirst: true
  };

  const animeDict = {
    "傲娇": "ツンデレ (Tsundere) - 表面带刺、内心娇羞",
    "病娇": "ヤンデレ (Yandere) - 执着狂热的畸形深情",
    "中二病": "中二病 (Chuunibyou) - 沉浸于自我设定的幻想",
    "天然呆": "天然ボケ (Tennen) - 纯真无邪、自带迷糊属性",
    "萌": "萌え (Moe) - 直击心底的纯真可爱",
    "正义": "正義 (Seigi) - 魔法与勇者的崇高誓约",
    "现充": "リア充 (Riajuu) - 现实生活充实之人",
    "死宅": "オタク (Otaku) - 专注二次元亚文化的御宅族",
    "番剧": "アニメ (Anime) - 日本动画剧集连载",
    "老婆": "嫁 (Yome) - 钟爱至深的纸片人伴侣",
    "千绘莉": "ちえり (Chieri) - 灵动优雅的魔法看板娘",
    "魔法少女": "魔法少女 (Mahou Shoujo) - 拯救世界的契约少女",
    "同人志": "同人誌 (Doujinshi) - 创作者热忱创作的非商业刊物",
    "黑化": "闇堕ち (Yami-ochi) - 信念崩塌步入幽暗极端",
    "幼驯染": "幼馴染 (Osananajimi) - 青梅竹马的一生羁绊",
    "绝对领域": "絶対領域 (Zettai Ryouiki) - 裙摆与过膝袜间的神圣空间",
    "声优": "声優 (Seiyuu) - 为角色赋予灵魂的声音艺术家",
    "神作": "神作 (Kamisaku) - 惊世骇俗、无可挑剔的殿堂经典",
    "废萌": "日常系 (Nichijou-kei) - 无主线轻快卖萌治愈日常",
    "腹黑": "腹黒 (Haraguro) - 外表纯良、内心深藏算计",
    "打call": "コール (Call) - 演唱会热血应援应和",
    "剧透": "ネタバレ (Netabare) - 提前揭露剧情关键伏笔",
    "生肉": "Raw (未熟) - 未经中文字幕压制的源生熟肉视频",
    "熟肉": "Subbed (既熟) - 经民间字幕组精心翻译润色的完整番剧"
  };

  function getConfig() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_CONFIG);
      if (saved) {
        return { ...defaultConfig, ...JSON.parse(saved) };
      }
    } catch (_) {}
    return { ...defaultConfig };
  }

  function saveConfig(cfg) {
    const merged = { ...getConfig(), ...cfg };
    localStorage.setItem(STORAGE_KEY_CONFIG, JSON.stringify(merged));
    return merged;
  }

  // --- Network Request via AndroidBridge or Fetch ---
  async function performNetworkRequest(url, method, headers, body) {
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

    const resp = await fetch(url, {
      method: method,
      headers: headers,
      body: body ? body : undefined
    });
    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`网络响应错误 ${resp.status}: ${errText.slice(0, 100)}`);
    }
    return await resp.json();
  }

  // --- OpenAI Compatible Translation ---
  async function translateViaOpenAI(text, targetLang, cfg) {
    let base = (cfg.baseUrl || "https://api.deepseek.com/v1").trim().replace(/\/+$/, "");
    if (!base.endsWith("/chat/completions")) {
      base += "/chat/completions";
    }

    const langMap = {
      ja: "日文 (Japanese)",
      zh: "简体中文 (Simplified Chinese)",
      en: "英文 (English)",
      ko: "韩文 (Korean)",
      ru: "俄文 (Russian)",
      fr: "法文 (French)"
    };
    const targetLangName = langMap[targetLang] || targetLang;

    const payload = {
      model: cfg.model || "deepseek-chat",
      messages: [
        {
          role: "system",
          content: cfg.systemPrompt || defaultConfig.systemPrompt
        },
        {
          role: "user",
          content: `请将以下文本翻译为【${targetLangName}】。只返回翻译后的纯文本译文，不要包含任何前缀、解释或标记：\n\n${text}`
        }
      ],
      temperature: 0.2
    };

    const headers = {
      "Content-Type": "application/json"
    };
    if (cfg.apiKey) {
      headers["Authorization"] = `Bearer ${cfg.apiKey.trim()}`;
    }

    const json = await performNetworkRequest(base, "POST", headers, JSON.stringify(payload));
    if (json && json.choices && json.choices.length > 0 && json.choices[0].message) {
      return json.choices[0].message.content.trim();
    }
    throw new Error("模型接口返回数据格式异常");
  }

  // --- DeepL Translation ---
  async function translateViaDeepL(text, targetLang, cfg) {
    const isFree = cfg.apiKey.endsWith(":fx");
    const endpoint = isFree ? "https://api-free.deepl.com/v2/translate" : "https://api.deepl.com/v2/translate";

    const payload = {
      text: [text],
      target_lang: targetLang.toUpperCase()
    };

    const headers = {
      "Content-Type": "application/json",
      "Authorization": `DeepL-Auth-Key ${cfg.apiKey.trim()}`
    };

    const json = await performNetworkRequest(endpoint, "POST", headers, JSON.stringify(payload));
    if (json && json.translations && json.translations.length > 0) {
      return json.translations[0].text;
    }
    throw new Error("DeepL 翻译返回数据格式异常");
  }

  // --- Google Translate Free Endpoint ---
  async function translateViaGoogle(text, targetLang) {
    const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=${targetLang}&dt=t&q=${encodeURIComponent(text)}`;
    const json = await performNetworkRequest(url, "GET", { "User-Agent": "Mozilla/5.0" }, null);
    if (Array.isArray(json) && Array.isArray(json[0])) {
      let result = "";
      for (const seg of json[0]) {
        if (seg && seg[0]) result += seg[0];
      }
      return result;
    }
    throw new Error("谷歌翻译返回异常");
  }

  // --- MD5 Hashing Utility ---
  function calcMd5(string) {
    if (typeof window !== "undefined" && window.AndroidBridge && window.AndroidBridge.md5) {
      try {
        const nativeHash = window.AndroidBridge.md5(string);
        if (nativeHash) return nativeHash;
      } catch (_) {}
    }
    function md5cycle(x, k) {
      let a = x[0], b = x[1], c = x[2], d = x[3];
      a = ff(a, b, c, d, k[0], 7, -680876936);
      d = ff(d, a, b, c, k[1], 12, -389564586);
      c = ff(c, d, a, b, k[2], 17, 606105819);
      b = ff(b, c, d, a, k[3], 22, -1044525330);
      a = ff(a, b, c, d, k[4], 7, -176418897);
      d = ff(d, a, b, c, k[5], 12, 1200080426);
      c = ff(c, d, a, b, k[6], 17, -1473231341);
      b = ff(b, c, d, a, k[7], 22, -45705983);
      a = ff(a, b, c, d, k[8], 7, 1770035416);
      d = ff(d, a, b, c, k[9], 12, -1958414417);
      c = ff(c, d, a, b, k[10], 17, -42063);
      b = ff(b, c, d, a, k[11], 22, -1990404162);
      a = ff(a, b, c, d, k[12], 7, 1804603682);
      d = ff(d, a, b, c, k[13], 12, -40341101);
      c = ff(c, d, a, b, k[14], 17, -1502002290);
      b = ff(b, c, d, a, k[15], 22, 1236535329);
      a = gg(a, b, c, d, k[1], 5, -165796510);
      d = gg(d, a, b, c, k[6], 9, -1069501632);
      c = gg(c, d, a, b, k[11], 14, 643717713);
      b = gg(b, c, d, a, k[0], 20, -373897302);
      a = gg(a, b, c, d, k[5], 5, -701558691);
      d = gg(d, a, b, c, k[10], 9, 38016083);
      c = gg(c, d, a, b, k[15], 14, -660478335);
      b = gg(b, c, d, a, k[4], 20, -405537848);
      a = gg(a, b, c, d, k[9], 5, 568446438);
      d = gg(d, a, b, c, k[14], 9, -1019803690);
      c = gg(c, d, a, b, k[3], 14, -187363961);
      b = gg(b, c, d, a, k[8], 20, 1163531501);
      a = gg(a, b, c, d, k[13], 5, -1444681467);
      d = gg(d, a, b, c, k[2], 9, -51403784);
      c = gg(c, d, a, b, k[7], 14, 1735328473);
      b = gg(b, c, d, a, k[12], 20, -1926607734);
      a = hh(a, b, c, d, k[5], 4, -378558);
      d = hh(d, a, b, c, k[8], 11, -2022574463);
      c = hh(c, d, a, b, k[11], 16, 1839030562);
      b = hh(b, c, d, a, k[14], 23, -35309556);
      a = hh(a, b, c, d, k[1], 4, -1530992060);
      d = hh(d, a, b, c, k[4], 11, 1272893353);
      c = hh(c, d, a, b, k[7], 16, -155497632);
      b = hh(b, c, d, a, k[10], 23, -1094730640);
      a = hh(a, b, c, d, k[13], 4, 681279174);
      d = hh(d, a, b, c, k[0], 11, -358537222);
      c = hh(c, d, a, b, k[3], 16, -722521979);
      b = hh(b, c, d, a, k[6], 23, 76029189);
      a = hh(a, b, c, d, k[9], 4, -640364487);
      d = hh(d, a, b, c, k[12], 11, -421815835);
      c = hh(c, d, a, b, k[15], 16, 530742520);
      b = hh(b, c, d, a, k[2], 23, -995338651);
      a = ii(a, b, c, d, k[0], 6, -198630844);
      d = ii(d, a, b, c, k[7], 10, 1126891415);
      c = ii(c, d, a, b, k[14], 15, -1416354905);
      b = ii(b, c, d, a, k[5], 21, -57434055);
      a = ii(a, b, c, d, k[12], 6, 1700485571);
      d = ii(d, a, b, c, k[3], 10, -1894986606);
      c = ii(c, d, a, b, k[10], 15, -1051523);
      b = ii(b, c, d, a, k[1], 21, -2054922799);
      a = ii(a, b, c, d, k[8], 6, 1873313359);
      d = ii(d, a, b, c, k[15], 10, -30611744);
      c = ii(c, d, a, b, k[6], 15, -1560198380);
      b = ii(b, c, d, a, k[13], 21, 1309151649);
      a = ii(a, b, c, d, k[4], 6, -145523070);
      d = ii(d, a, b, c, k[11], 10, -1120210379);
      c = ii(c, d, a, b, k[2], 15, 718787259);
      b = ii(b, c, d, a, k[9], 21, -343485551);
      x[0] = add32(a, x[0]);
      x[1] = add32(b, x[1]);
      x[2] = add32(c, x[2]);
      x[3] = add32(d, x[3]);
    }
    function cmn(q, a, b, x, s, t) {
      a = add32(add32(a, q), add32(x, t));
      return add32((a << s) | (a >>> (32 - s)), b);
    }
    function ff(a, b, c, d, x, s, t) { return cmn((b & c) | ((~b) & d), a, b, x, s, t); }
    function gg(a, b, c, d, x, s, t) { return cmn((b & d) | (c & (~d)), a, b, x, s, t); }
    function hh(a, b, c, d, x, s, t) { return cmn(b ^ c ^ d, a, b, x, s, t); }
    function ii(a, b, c, d, x, s, t) { return cmn(c ^ (b | (~d)), a, b, x, s, t); }
    function md51(s) {
      const n = s.length;
      const state = [1732584193, -271733879, -1732584194, 271733878];
      let i;
      for (i = 64; i <= s.length; i += 64) {
        md5cycle(state, md5blk(s.substring(i - 64, i)));
      }
      s = s.substring(i - 64);
      const tail = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
      for (i = 0; i < s.length; i++) tail[i >> 2] |= s.charCodeAt(i) << ((i % 4) << 3);
      tail[i >> 2] |= 0x80 << ((i % 4) << 3);
      if (i > 55) {
        md5cycle(state, tail);
        for (i = 0; i < 16; i++) tail[i] = 0;
      }
      tail[14] = n * 8;
      md5cycle(state, tail);
      return state;
    }
    function md5blk(s) {
      const md5blks = [];
      for (let i = 0; i < 64; i += 4) {
        md5blks[i >> 2] = s.charCodeAt(i) + (s.charCodeAt(i + 1) << 8) + (s.charCodeAt(i + 2) << 16) + (s.charCodeAt(i + 3) << 24);
      }
      return md5blks;
    }
    function rhex(n) {
      let s = '', j = 0;
      for (; j < 4; j++) s += ((n >> (j * 8 + 4)) & 0x0f).toString(16) + ((n >> (j * 8)) & 0x0f).toString(16);
      return s;
    }
    function hex(x) {
      for (let i = 0; i < x.length; i++) x[i] = rhex(x[i]);
      return x.join('');
    }
    function add32(a, b) { return (a + b) & 0xffffffff; }

    let utf8Str = "";
    if (typeof TextEncoder !== "undefined") {
      const bytes = new TextEncoder().encode(string);
      for (let i = 0; i < bytes.length; i++) utf8Str += String.fromCharCode(bytes[i]);
    } else if (typeof Buffer !== "undefined") {
      utf8Str = Buffer.from(string, "utf8").toString("binary");
    } else {
      utf8Str = unescape(encodeURIComponent(string));
    }
    return hex(md51(utf8Str));
  }

  // --- Baidu Translate Open Platform ---
  async function translateViaBaidu(text, targetLang, cfg) {
    const appid = (cfg.baiduAppId || "").trim();
    const appkey = (cfg.baiduKey || "").trim();
    if (!appid || !appkey) {
      throw new Error("请先在配置中填入百度翻译 AppID 与密钥 (App Key)");
    }
    const baiduLangMap = {
      ja: "jp",
      zh: "zh",
      en: "en",
      ko: "kor",
      fr: "fra",
      ru: "ru",
      de: "de",
      es: "spa"
    };
    const to = baiduLangMap[targetLang] || targetLang;
    const salt = Date.now().toString();
    const signStr = appid + text + salt + appkey;
    const sign = calcMd5(signStr);

    const bodyParams = new URLSearchParams();
    bodyParams.append("q", text);
    bodyParams.append("from", "auto");
    bodyParams.append("to", to);
    bodyParams.append("appid", appid);
    bodyParams.append("salt", salt);
    bodyParams.append("sign", sign);

    const endpoint = "https://fanyi-api.baidu.com/api/trans/vip/translate";
    const headers = {
      "Content-Type": "application/x-www-form-urlencoded"
    };

    const res = await performNetworkRequest(endpoint, "POST", headers, bodyParams.toString());
    const json = typeof res === "string" ? JSON.parse(res) : res;
    if (json.trans_result && json.trans_result.length > 0) {
      return json.trans_result.map((item) => item.dst).join("\n");
    }
    if (json.error_code) {
      throw new Error(`百度翻译接口错误 [${json.error_code}]: ${json.error_msg || ""}`);
    }
    throw new Error("百度翻译返回格式异常");
  }

  // --- Test API Connectivity ---
  async function testConnection(cfg) {
    const start = performance.now();
    try {
      let res = "";
      if (cfg.provider === "baidu") {
        res = await translateViaBaidu("Hello", "zh", cfg);
      } else if (cfg.provider === "google") {
        res = await translateViaGoogle("Hello", "zh");
      } else if (cfg.provider === "deepl") {
        res = await translateViaDeepL("Hello", "zh", cfg);
      } else if (cfg.provider === "offline") {
        res = "离线词库模式已就绪";
      } else {
        res = await translateViaOpenAI("Hello", "zh", cfg);
      }
      const elapsed = Math.round(performance.now() - start);
      return {
        ok: true,
        latencyMs: elapsed,
        output: res
      };
    } catch (e) {
      return {
        ok: false,
        error: e.message || String(e)
      };
    }
  }

  // --- Main Translation Router ---
  async function translate(text, targetLang = "ja", onStatus = null) {
    if (!text || !text.trim()) return "";
    const trimmed = text.trim();
    const cfg = getConfig();

    // 1. Check Offline Anime Dictionary
    if (cfg.useDictFirst && animeDict[trimmed]) {
      return `【二次元萌系释义】\n${animeDict[trimmed]}`;
    }

    // 2. Offline Mode Only
    if (cfg.provider === "offline") {
      return animeDict[trimmed]
        ? `【萌系词库】${animeDict[trimmed]}`
        : `[离线词库未收录: ${trimmed}] 请在上方配置大模型 API 体验高保真 AI 在线翻译。`;
    }

    // 3. API Translation
    if (cfg.provider === "openai") {
      if (!cfg.apiKey && !cfg.baseUrl.includes("localhost") && !cfg.baseUrl.includes("127.0.0.1") && !cfg.baseUrl.includes("10.0.2.2")) {
        throw new Error("未配置 API Key！请点击右上角【API 配置】填入您的 Key 或选择 Google 免费翻译通道。");
      }
      if (onStatus) onStatus("正在请求 AI 模型翻译接口...");
      return await translateViaOpenAI(trimmed, targetLang, cfg);
    }

    if (cfg.provider === "deepl") {
      if (!cfg.apiKey) {
        throw new Error("请先在配置中填入 DeepL Auth Key");
      }
      if (onStatus) onStatus("正在调用 DeepL 引擎...");
      return await translateViaDeepL(trimmed, targetLang, cfg);
    }

    if (cfg.provider === "baidu") {
      if (!cfg.baiduAppId || !cfg.baiduKey) {
        throw new Error("请先在配置中填入百度翻译 AppID 与密钥");
      }
      if (onStatus) onStatus("正在调用百度翻译开放平台接口...");
      return await translateViaBaidu(trimmed, targetLang, cfg);
    }

    if (cfg.provider === "google") {
      if (onStatus) onStatus("正在连接谷歌翻译接口...");
      return await translateViaGoogle(trimmed, targetLang);
    }

    // Fallback
    return `[${targetLang.toUpperCase()}] ${text}`;
  }

  return {
    getConfig,
    saveConfig,
    translate,
    testConnection,
    getDict: () => animeDict,
    calcMd5,
    translateViaBaidu
  };
})();

window.TranslatorEngine = TranslatorEngine;
