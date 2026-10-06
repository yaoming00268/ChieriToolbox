/**
 * 千绘莉工具箱 (Chieri Toolbox Mobile) - 主路由、现代化 UI 自定义与工具集成中枢
 */

(function () {
  // Navigation & Drawer Elements
  const drawerBackdrop = document.getElementById("drawer-backdrop");
  const drawerSidebar = document.getElementById("drawer-sidebar");
  const btnOpenDrawer = document.getElementById("btn-open-drawer");
  const btnCloseDrawer = document.getElementById("btn-close-drawer");
  const drawerFloatingBallSwitch = document.getElementById("drawer-floating-ball-switch");
  const settingsFloatingBallSwitch = document.getElementById("settings-floating-ball-switch");
  const settingsSystemOverlaySwitch = document.getElementById("settings-system-overlay-switch");
  const btnToggleTheme = document.getElementById("btn-toggle-theme");
  const iconThemeSun = document.getElementById("icon-theme-sun");
  const iconThemeMoon = document.getElementById("icon-theme-moon");

  let currentTool = "dashboard";

  // --- UI Customization & Appearance System ---
  const STORAGE_KEY_UI = "chieri_ui_custom_prefs";
  const defaultUiPrefs = {
    theme: "dark",
    cardSize: "standard",
    opacity: 92,
    blur: 16
  };

  function getUiPrefs() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_UI);
      if (saved) return { ...defaultUiPrefs, ...JSON.parse(saved) };
    } catch (_) {}
    return { ...defaultUiPrefs };
  }

  function saveUiPrefs(prefs) {
    localStorage.setItem(STORAGE_KEY_UI, JSON.stringify(prefs));
  }

  function applyUiPrefs(prefs) {
    const root = document.documentElement;

    // 1. Theme
    root.setAttribute("data-theme", prefs.theme);
    if (prefs.theme === "dark") {
      if (iconThemeSun) iconThemeSun.style.display = "none";
      if (iconThemeMoon) iconThemeMoon.style.display = "block";
    } else {
      if (iconThemeSun) iconThemeSun.style.display = "block";
      if (iconThemeMoon) iconThemeMoon.style.display = "none";
    }

    // Inform Android native status bar
    if (window.AndroidBridge && window.AndroidBridge.setStatusBarTheme) {
      window.AndroidBridge.setStatusBarTheme(prefs.theme === "dark");
    }

    // 2. Card Size
    root.setAttribute("data-card-size", prefs.cardSize);

    // 3. Surface Opacity
    const opacityVal = Math.min(1, Math.max(0.5, prefs.opacity / 100));
    root.style.setProperty("--surface-opacity", opacityVal.toString());

    // 4. Backdrop Blur
    root.style.setProperty("--backdrop-blur", `${prefs.blur}px`);

    // Synchronize UI Controls in Settings
    syncUiControls(prefs);
  }

  function syncUiControls(prefs) {
    // Theme chips
    document.querySelectorAll(".radio-chip[data-theme]").forEach((chip) => {
      chip.classList.toggle("active", chip.getAttribute("data-theme") === prefs.theme);
    });

    // Card size chips
    document.querySelectorAll(".radio-chip[data-size]").forEach((chip) => {
      chip.classList.toggle("active", chip.getAttribute("data-size") === prefs.cardSize);
    });

    // Opacity slider
    const sliderOpacity = document.getElementById("slider-surface-opacity");
    const labelOpacity = document.getElementById("label-surface-opacity");
    if (sliderOpacity) sliderOpacity.value = prefs.opacity;
    if (labelOpacity) labelOpacity.innerText = `${prefs.opacity}%`;

    // Blur chips
    document.querySelectorAll(".radio-chip[data-blur]").forEach((chip) => {
      chip.classList.toggle("active", parseInt(chip.getAttribute("data-blur"), 10) === prefs.blur);
    });
  }

  function initUiCustomization() {
    const prefs = getUiPrefs();
    applyUiPrefs(prefs);

    // Header Quick Theme Toggle Button
    if (btnToggleTheme) {
      btnToggleTheme.addEventListener("click", () => {
        const cur = getUiPrefs();
        cur.theme = cur.theme === "dark" ? "light" : "dark";
        saveUiPrefs(cur);
        applyUiPrefs(cur);
        showAppToast(`已切换为${cur.theme === "dark" ? "深色" : "浅色"}模式`);
      });
    }

    // Settings Theme Chips
    document.querySelectorAll(".radio-chip[data-theme]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const theme = chip.getAttribute("data-theme");
        const cur = getUiPrefs();
        cur.theme = theme;
        saveUiPrefs(cur);
        applyUiPrefs(cur);
        showAppToast(`已设为${theme === "dark" ? "深色" : "浅色"}模式`);
      });
    });

    // Settings Card Size Chips
    document.querySelectorAll(".radio-chip[data-size]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const size = chip.getAttribute("data-size");
        const cur = getUiPrefs();
        cur.cardSize = size;
        saveUiPrefs(cur);
        applyUiPrefs(cur);
        showAppToast(`卡片尺寸已设为: ${chip.innerText}`);
      });
    });

    // Settings Opacity Slider
    const sliderOpacity = document.getElementById("slider-surface-opacity");
    const labelOpacity = document.getElementById("label-surface-opacity");
    if (sliderOpacity) {
      sliderOpacity.addEventListener("input", (e) => {
        const val = parseInt(e.target.value, 10);
        if (labelOpacity) labelOpacity.innerText = `${val}%`;
        const cur = getUiPrefs();
        cur.opacity = val;
        saveUiPrefs(cur);
        applyUiPrefs(cur);
      });
    }

    // Settings Blur Chips
    document.querySelectorAll(".radio-chip[data-blur]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const blur = parseInt(chip.getAttribute("data-blur"), 10);
        const cur = getUiPrefs();
        cur.blur = blur;
        saveUiPrefs(cur);
        applyUiPrefs(cur);
        showAppToast(`磨砂效果已设为: ${chip.innerText}`);
      });
    });

    // Reset UI Prefs Button
    const btnResetUi = document.getElementById("btn-reset-ui-prefs");
    if (btnResetUi) {
      btnResetUi.addEventListener("click", () => {
        saveUiPrefs(defaultUiPrefs);
        applyUiPrefs(defaultUiPrefs);
        showAppToast("已恢复默认外观设置");
      });
    }
  }

  // --- Drawer & Navigation ---
  function openSidebar() {
    if (window.closeFloatingMenu) window.closeFloatingMenu();
    drawerBackdrop.classList.add("active");
    drawerSidebar.classList.add("active");
  }

  function closeSidebar() {
    drawerBackdrop.classList.remove("active");
    drawerSidebar.classList.remove("active");
  }

  function toggleSidebar() {
    if (drawerSidebar.classList.contains("active")) closeSidebar();
    else openSidebar();
  }

  function isSidebarOpen() {
    return drawerSidebar.classList.contains("active");
  }

  function showAppToast(message) {
    if (window.AndroidBridge && window.AndroidBridge.showToast) {
      window.AndroidBridge.showToast(message);
    } else {
      let container = document.getElementById("toast-container");
      if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        document.body.appendChild(container);
      }
      const toast = document.createElement("div");
      toast.className = "toast";
      toast.innerText = message;
      container.appendChild(toast);
      setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transition = "opacity 0.25s";
        setTimeout(() => toast.remove(), 250);
      }, 2000);
    }
  }

  function syncSettingsSwitches() {
    if (settingsFloatingBallSwitch && window.isFloatingBallVisible) {
      settingsFloatingBallSwitch.checked = window.isFloatingBallVisible();
    }
    if (drawerFloatingBallSwitch && window.isFloatingBallVisible) {
      drawerFloatingBallSwitch.checked = window.isFloatingBallVisible();
    }
    if (settingsSystemOverlaySwitch && window.AndroidBridge && window.AndroidBridge.isSystemFloatingBallRunning) {
      settingsSystemOverlaySwitch.checked = window.AndroidBridge.isSystemFloatingBallRunning();
    }
  }

  function navigateToTool(toolId) {
    currentTool = toolId;
    closeSidebar();

    document.querySelectorAll(".tool-view-panel").forEach((p) => p.classList.remove("active"));
    const target = document.getElementById(`panel-${toolId}`);
    if (target) {
      target.classList.add("active");
      window.scrollTo(0, 0);
    }

    if (toolId === "settings") {
      syncSettingsSwitches();
      syncUiControls(getUiPrefs());
    }

    document.querySelectorAll(".menu-item").forEach((item) => {
      item.classList.toggle("active", item.getAttribute("data-tool") === toolId);
    });

    // Special Inits
    if (toolId === "osu_skin_studio" && window.OsuEngine) {
      const c = document.getElementById("maniaCanvas");
      if (c) window.OsuEngine.init(c);
    } else if (toolId === "whiteboard" && window.WhiteboardEngine) {
      const c = document.getElementById("whiteboardCanvas");
      if (c) window.WhiteboardEngine.init(c);
    } else if (toolId === "media_downloader") {
      loadBiliVipStatus();
    } else if (toolId === "translator") {
      loadTranslatorConfigUi();
    }
  }

  function handleAndroidBackPressed() {
    if (window.isFloatingMenuOpen && window.isFloatingMenuOpen()) {
      window.closeFloatingMenu();
      return true;
    }
    if (isSidebarOpen()) {
      closeSidebar();
      return true;
    }
    if (currentTool !== "dashboard") {
      navigateToTool("dashboard");
      return true;
    }
    return false;
  }

  window.openSidebar = openSidebar;
  window.closeSidebar = closeSidebar;
  window.toggleSidebar = toggleSidebar;
  window.navigateToTool = navigateToTool;
  window.showAppToast = showAppToast;
  window.handleAndroidBackPressed = handleAndroidBackPressed;

  // Drawer event listeners
  if (btnOpenDrawer) btnOpenDrawer.addEventListener("click", openSidebar);
  if (btnCloseDrawer) btnCloseDrawer.addEventListener("click", closeSidebar);
  if (drawerBackdrop) drawerBackdrop.addEventListener("click", closeSidebar);

  document.querySelectorAll(".esc-escape-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      navigateToTool("dashboard");
      showAppToast("已瞬间返回仪表盘");
    });
  });

  // Floating Ball Switch Listeners
  if (drawerFloatingBallSwitch) {
    drawerFloatingBallSwitch.addEventListener("change", (e) => {
      window.setFloatingBallVisible && window.setFloatingBallVisible(e.target.checked);
      if (settingsFloatingBallSwitch) settingsFloatingBallSwitch.checked = e.target.checked;
      showAppToast(e.target.checked ? "悬浮球已开启" : "悬浮球已关闭");
    });
  }

  if (settingsFloatingBallSwitch) {
    settingsFloatingBallSwitch.addEventListener("change", (e) => {
      window.setFloatingBallVisible && window.setFloatingBallVisible(e.target.checked);
      if (drawerFloatingBallSwitch) drawerFloatingBallSwitch.checked = e.target.checked;
      showAppToast(e.target.checked ? "悬浮球已开启" : "悬浮球已关闭");
    });
  }

  if (settingsSystemOverlaySwitch) {
    settingsSystemOverlaySwitch.addEventListener("change", (e) => {
      if (window.AndroidBridge && window.AndroidBridge.toggleSystemFloatingBall) {
        const ok = window.AndroidBridge.toggleSystemFloatingBall(e.target.checked);
        if (!ok) e.target.checked = false;
      } else {
        showAppToast("当前环境不支持系统全局悬浮窗");
      }
    });
  }

  // Drawer Menu Items
  document.querySelectorAll(".menu-item").forEach((item) => {
    item.addEventListener("click", () => {
      const tool = item.getAttribute("data-tool");
      if (tool) navigateToTool(tool);
    });
  });

  // Dashboard Card Clicks
  document.querySelectorAll(".tool-card").forEach((card) => {
    card.addEventListener("click", () => {
      const tool = card.getAttribute("data-tool");
      if (tool) navigateToTool(tool);
    });
  });

  // Back to Dashboard buttons in panels
  document.querySelectorAll(".panel-back-btn").forEach((btn) => {
    btn.addEventListener("click", () => navigateToTool("dashboard"));
  });

  // Dashboard Search & Filters
  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      const val = e.target.value.toLowerCase().trim();
      document.querySelectorAll(".tool-card").forEach((card) => {
        const tags = (card.getAttribute("data-tags") || "").toLowerCase();
        const title = card.querySelector(".tool-card-title").innerText.toLowerCase();
        const match = tags.includes(val) || title.includes(val);
        card.style.display = match ? "flex" : "none";
      });
    });
  }

  document.querySelectorAll(".filter-chip[data-category]").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".filter-chip[data-category]").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      const cat = chip.getAttribute("data-category");
      document.querySelectorAll(".tool-card").forEach((card) => {
        const c = card.getAttribute("data-category");
        if (cat === "all" || c === cat) card.style.display = "flex";
        else card.style.display = "none";
      });
    });
  });

  // --- Tool 1: Audio Converter Logic ---
  let selectedAudioFile = null;
  let convertedAudioResult = null;

  const audioDropzone = document.getElementById("audio-conv-dropzone");
  const audioFileInput = document.getElementById("audio-conv-file-input");
  const audioFilenameDisplay = document.getElementById("audio-conv-filename-display");
  const audioSourcePreviewBox = document.getElementById("audio-source-preview-box");
  const audioSourcePlayer = document.getElementById("audio-source-player");
  const audioSourceMetaTag = document.getElementById("audio-source-meta-tag");
  const btnStartAudioConvert = document.getElementById("btn-start-audio-convert");
  const audioConvProgressBox = document.getElementById("audio-conv-progress-box");
  const audioConvProgressFill = document.getElementById("audio-conv-progress-fill");
  const audioConvStatusText = document.getElementById("audio-conv-status-text");
  const audioConvResultBox = document.getElementById("audio-conv-result-box");
  const audioResultPlayer = document.getElementById("audio-result-player");
  const audioResultFilename = document.getElementById("audio-result-filename");
  const audioResultSizeBadge = document.getElementById("audio-result-size-badge");
  const audioResultMetaLine = document.getElementById("audio-result-meta-line");
  const btnSaveAudioToDownloads = document.getElementById("btn-save-audio-to-downloads");
  const btnWebDownloadAudio = document.getElementById("btn-web-download-audio");

  if (audioDropzone && audioFileInput) {
    audioDropzone.addEventListener("click", () => audioFileInput.click());
    audioFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        loadAudioFile(e.target.files[0]);
      }
    });

    audioDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      audioDropzone.classList.add("dragover");
    });
    audioDropzone.addEventListener("dragleave", () => audioDropzone.classList.remove("dragover"));
    audioDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      audioDropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        loadAudioFile(e.dataTransfer.files[0]);
      }
    });
  }

  function loadAudioFile(file) {
    selectedAudioFile = file;
    audioFilenameDisplay.innerText = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    audioConvResultBox.style.display = "none";

    // Preview
    const url = URL.createObjectURL(file);
    audioSourcePlayer.src = url;
    audioSourcePreviewBox.style.display = "block";
    audioSourceMetaTag.innerText = file.type || "音频格式";
  }

  if (btnStartAudioConvert) {
    btnStartAudioConvert.addEventListener("click", async () => {
      if (!selectedAudioFile) {
        showAppToast("请先选择待转换的音频源文件！");
        return;
      }

      const format = document.getElementById("audio-target-format").value;
      const sampleRate = document.getElementById("audio-target-samplerate").value;
      const bitrate = document.getElementById("audio-target-bitrate").value;

      audioConvProgressBox.style.display = "block";
      btnStartAudioConvert.disabled = true;

      try {
        const result = await AudioEngine.convertAudio(
          selectedAudioFile,
          { format, sampleRate, bitrate },
          (percent, text) => {
            audioConvProgressFill.style.width = `${percent}%`;
            audioConvStatusText.innerText = `[${percent}%] ${text}`;
          }
        );

        convertedAudioResult = result;
        const outName = selectedAudioFile.name.replace(/\.[^/.]+$/, "") + `_converted.${format}`;
        convertedAudioResult.filename = outName;

        // Render result box
        const resultBlobUrl = URL.createObjectURL(result.blob);
        audioResultPlayer.src = resultBlobUrl;
        audioResultFilename.innerText = outName;
        audioResultSizeBadge.innerText = `${(result.size / 1024 / 1024).toFixed(2)} MB`;
        audioResultMetaLine.innerHTML = `
          <span>时长: ${result.duration.toFixed(1)}s</span>
          <span>格式: ${format.toUpperCase()}</span>
          <span>采样率: ${(result.sampleRate / 1000).toFixed(1)}kHz</span>
          <span>声道: ${result.channels === 2 ? "立体声" : "单声道"}</span>
        `;

        audioConvResultBox.style.display = "block";
        showAppToast("音频转换成功！");
      } catch (err) {
        audioConvStatusText.innerText = `转换失败: ${err.message}`;
        showAppToast(`转换异常: ${err.message}`);
      } finally {
        btnStartAudioConvert.disabled = false;
      }
    });
  }

  if (btnSaveAudioToDownloads) {
    btnSaveAudioToDownloads.addEventListener("click", () => {
      if (!convertedAudioResult) return;
      if (window.AndroidBridge && window.AndroidBridge.saveBase64File) {
        window.AndroidBridge.saveBase64File(
          convertedAudioResult.filename,
          convertedAudioResult.base64,
          convertedAudioResult.mimeType
        );
      } else {
        triggerWebDownload(convertedAudioResult.blob, convertedAudioResult.filename);
        showAppToast("已下载音频文件");
      }
    });
  }

  if (btnWebDownloadAudio) {
    btnWebDownloadAudio.addEventListener("click", () => {
      if (!convertedAudioResult) return;
      triggerWebDownload(convertedAudioResult.blob, convertedAudioResult.filename);
    });
  }

  function triggerWebDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      a.remove();
      URL.revokeObjectURL(url);
    }, 1000);
  }

  // --- Tool 2: Bilibili VIP & Media Downloader Logic ---
  const biliSessdataInput = document.getElementById("bili-sessdata-input");
  const btnVerifyBiliVip = document.getElementById("btn-verify-bili-vip");
  const btnClearBiliVip = document.getElementById("btn-clear-bili-vip");
  const biliVipStatusBadge = document.getElementById("bili-vip-status-badge");
  const mediaUrlInput = document.getElementById("media-url-input");
  const btnParseMediaUrl = document.getElementById("btn-parse-media-url");
  const mediaParsedDetailBox = document.getElementById("media-parsed-detail-box");
  const mediaDetailCover = document.getElementById("media-detail-cover");
  const mediaDetailTitle = document.getElementById("media-detail-title");
  const mediaDetailAuthor = document.getElementById("media-detail-author");
  const mediaVideoTrackSelect = document.getElementById("media-video-track-select");
  const mediaAudioTrackSelect = document.getElementById("media-audio-track-select");
  const btnCopyMediaStreamUrl = document.getElementById("btn-copy-media-stream-url");
  const btnAddDownloadQueue = document.getElementById("btn-add-download-queue");
  const mediaQueueContainer = document.getElementById("media-queue-container");

  let currentParsedMedia = null;

  async function loadBiliVipStatus() {
    const saved = MediaEngine.getSavedCookie();
    if (biliSessdataInput && saved) {
      biliSessdataInput.value = saved;
    }
    if (saved) {
      const status = await MediaEngine.checkAccountStatus(saved);
      updateVipBadge(status);
    } else {
      updateVipBadge({ is_login: false, is_vip: false, vip_label: "未配置凭证", message: "未登录" });
    }
  }

  function updateVipBadge(status) {
    if (!biliVipStatusBadge) return;
    if (status.is_vip) {
      biliVipStatusBadge.className = "badge badge-vip";
      biliVipStatusBadge.innerText = `👑 ${status.vip_label || "大会员"}: ${status.uname}`;
    } else if (status.is_login) {
      biliVipStatusBadge.className = "badge badge-success";
      biliVipStatusBadge.innerText = `已登录: ${status.uname}`;
    } else {
      biliVipStatusBadge.className = "badge";
      biliVipStatusBadge.innerText = status.vip_label || "未登录";
    }
  }

  if (btnVerifyBiliVip) {
    btnVerifyBiliVip.addEventListener("click", async () => {
      const raw = biliSessdataInput.value.trim();
      const norm = MediaEngine.saveCookie(raw);
      showAppToast("正在验证 B站 账号状态...");
      const status = await MediaEngine.checkAccountStatus(norm);
      updateVipBadge(status);
      showAppToast(status.message);
    });
  }

  if (btnClearBiliVip) {
    btnClearBiliVip.addEventListener("click", () => {
      MediaEngine.saveCookie("");
      if (biliSessdataInput) biliSessdataInput.value = "";
      updateVipBadge({ is_login: false, is_vip: false, vip_label: "未配置凭据" });
      showAppToast("已清空 B站 账号凭据");
    });
  }

  if (btnParseMediaUrl) {
    btnParseMediaUrl.addEventListener("click", async () => {
      const url = mediaUrlInput.value.trim();
      if (!url) {
        showAppToast("请先填入 B站 或 YouTube 视频链接！");
        return;
      }

      btnParseMediaUrl.disabled = true;
      btnParseMediaUrl.innerText = "正在深度解析音画流...";

      try {
        const res = await MediaEngine.parseMediaUrl(url);
        currentParsedMedia = res;

        // Render video details
        mediaDetailTitle.innerText = res.title;
        mediaDetailAuthor.innerText = `UP主: ${res.owner} · 时长: ${Math.round(res.duration / 60)}分钟`;
        if (res.cover) mediaDetailCover.src = res.cover;

        // Populate video tracks
        mediaVideoTrackSelect.innerHTML = "";
        for (const vt of res.videoStreams) {
          const opt = document.createElement("option");
          opt.value = vt.url;
          opt.innerText = (vt.isVip ? "👑 [大会员] " : "") + `${vt.label} (${vt.codecs})`;
          mediaVideoTrackSelect.appendChild(opt);
        }

        // Populate audio tracks
        mediaAudioTrackSelect.innerHTML = "";
        for (const at of res.audioStreams) {
          const opt = document.createElement("option");
          opt.value = at.url;
          opt.innerText = (at.isVip ? "👑 [大会员专享] " : "") + `${at.label} (${at.codecs})`;
          mediaAudioTrackSelect.appendChild(opt);
        }

        mediaParsedDetailBox.style.display = "block";
        showAppToast(res.hasVipStreams ? "已成功解析！包含大会员专享画质流" : "已成功解析视频轨道");
      } catch (e) {
        showAppToast(`解析失败: ${e.message}`);
      } finally {
        btnParseMediaUrl.disabled = false;
        btnParseMediaUrl.innerText = "立即解析全量音画轨道";
      }
    });
  }

  if (btnCopyMediaStreamUrl) {
    btnCopyMediaStreamUrl.addEventListener("click", () => {
      const streamUrl = mediaVideoTrackSelect.value || mediaAudioTrackSelect.value;
      if (!streamUrl) {
        showAppToast("未选定有效轨道地址");
        return;
      }
      navigator.clipboard.writeText(streamUrl).then(() => {
        showAppToast("音画直链地址已复制至剪贴板");
      }).catch(() => {
        showAppToast("直链: " + streamUrl.slice(0, 50) + "...");
      });
    });
  }

  // Native Android Media Download Progress Callback
  window.onMediaDownloadProgress = function (filename, progress, speed, status) {
    const queue = MediaEngine.getQueue();
    const task = queue.find((t) => t.title.includes(filename) || filename.includes(t.title) || t.id === filename);
    if (task) {
      task.progress = progress;
      task.speed = speed;
      task.status = status;
      renderMediaQueue();
    }
  };

  if (btnAddDownloadQueue) {
    btnAddDownloadQueue.addEventListener("click", () => {
      if (!currentParsedMedia) return;
      const selectedStreamUrl = mediaVideoTrackSelect.value || mediaAudioTrackSelect.value;
      const selectedLabel = mediaVideoTrackSelect.options[mediaVideoTrackSelect.selectedIndex]?.text || "MP4";

      const task = MediaEngine.addTask(currentParsedMedia, "mp4", {
        label: selectedLabel,
        url: selectedStreamUrl
      });

      renderMediaQueue();
      showAppToast("已加入下载队列");

      if (window.AndroidBridge && window.AndroidBridge.downloadMediaStream && selectedStreamUrl && selectedStreamUrl.startsWith("http")) {
        const cleanName = `${(currentParsedMedia.title || "video").replace(/[\\\\/:*?\"<>|]/g, "_")}_${selectedLabel.replace(/[^a-zA-Z0-9_\-\u4e00-\u9fa5]/g, "_")}.mp4`;
        const headers = {
          "Referer": currentParsedMedia.platform === "bilibili" ? "https://www.bilibili.com" : "https://www.youtube.com",
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        };
        const savedCookie = MediaEngine.getSavedCookie();
        if (savedCookie) headers["Cookie"] = savedCookie;
        window.AndroidBridge.downloadMediaStream(selectedStreamUrl, cleanName, JSON.stringify(headers));
      } else {
        MediaEngine.simulateDownload(
          task,
          () => renderMediaQueue(),
          () => {
            renderMediaQueue();
            showAppToast(`下载完成: ${task.title}`);
          }
        );
      }
    });
  }

  function renderMediaQueue() {
    const queue = MediaEngine.getQueue();
    if (!mediaQueueContainer) return;
    if (queue.length === 0) {
      mediaQueueContainer.innerHTML = `<div style="text-align: center; font-size: 12px; color: var(--text-muted); padding: 14px;">暂无下载任务</div>`;
      return;
    }

    mediaQueueContainer.innerHTML = "";
    for (const t of queue) {
      const item = document.createElement("div");
      item.style.padding = "8px 10px";
      item.style.background = "var(--bg-input)";
      item.style.borderRadius = "var(--radius-md)";
      item.style.marginBottom = "6px";
      item.style.border = "1px solid var(--border-subtle)";
      item.innerHTML = `
        <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 550; color: var(--text-main); margin-bottom: 4px;">
          <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 70%;">${t.title}</span>
          <span style="color: var(--accent-primary);">${t.status === "completed" ? "已完成" : t.speed}</span>
        </div>
        <div class="progress-bar-wrap" style="margin: 4px 0;">
          <div class="progress-bar-fill" style="width: ${t.progress}%;"></div>
        </div>
        <div style="font-size: 10px; color: var(--text-muted); display: flex; justify-content: space-between;">
          <span>${t.streamLabel}</span>
          <span>${t.progress}%</span>
        </div>
      `;
      mediaQueueContainer.appendChild(item);
    }
  }

  // --- Tool 3: Multi-Format Archive Manager Logic ---
  const archiveDropzone = document.getElementById("archive-dropzone");
  const archiveFileInput = document.getElementById("archive-file-input");
  const archiveFilenameDisplay = document.getElementById("archive-filename-display");
  const archiveContentsBox = document.getElementById("archive-contents-box");
  const archiveFormatBadge = document.getElementById("archive-format-badge");
  const archiveCountBadge = document.getElementById("archive-count-badge");
  const archiveFileList = document.getElementById("archive-file-list");
  const archiveSearchFilter = document.getElementById("archive-search-filter");
  const btnExtractAllArchive = document.getElementById("btn-extract-all-archive");

  let currentArchiveFiles = [];

  if (archiveDropzone && archiveFileInput) {
    archiveDropzone.addEventListener("click", () => archiveFileInput.click());
    archiveFileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        loadArchiveFile(e.target.files[0]);
      }
    });

    archiveDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      archiveDropzone.classList.add("dragover");
    });
    archiveDropzone.addEventListener("dragleave", () => archiveDropzone.classList.remove("dragover"));
    archiveDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      archiveDropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        loadArchiveFile(e.dataTransfer.files[0]);
      }
    });
  }

  let currentArchiveFile = null;
  let currentArchiveBase64 = null;

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function loadArchiveFile(file) {
    currentArchiveFile = file;
    archiveFilenameDisplay.innerText = `${file.name} (${ArchiveEngine.formatBytes(file.size)})`;
    showAppToast("正在解析归档目录结构...");

    try {
      currentArchiveBase64 = await fileToBase64(file);
      let files = null;
      let usedNative = false;

      // Prefer native Commons Compress bridge if on Android
      if (window.AndroidBridge && window.AndroidBridge.listArchiveEntriesNative) {
        try {
          const nativeResStr = window.AndroidBridge.listArchiveEntriesNative(currentArchiveBase64, file.name);
          const nativeRes = JSON.parse(nativeResStr);
          if (nativeRes.ok && Array.isArray(nativeRes.entries) && nativeRes.entries.length > 0) {
            files = nativeRes.entries.map((e) => ({
              name: e.name,
              format: file.name.split(".").pop().toUpperCase(),
              compressedSize: e.compressedSize || e.size || 0,
              uncompressedSize: e.size || 0,
              method: e.method || "Native Commons Compress",
              isDir: Boolean(e.isDir),
              getData: async () => {
                const extResStr = window.AndroidBridge.extractArchiveEntryNative(currentArchiveBase64, file.name, e.name);
                const extRes = JSON.parse(extResStr);
                if (extRes.ok && extRes.data) {
                  const bin = atob(extRes.data);
                  const bytes = new Uint8Array(bin.length);
                  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                  return bytes;
                }
                throw new Error(extRes.error || "原生提取失败");
              },
              getNativeBase64: () => {
                const extResStr = window.AndroidBridge.extractArchiveEntryNative(currentArchiveBase64, file.name, e.name);
                const extRes = JSON.parse(extResStr);
                if (extRes.ok && extRes.data) return extRes.data;
                throw new Error(extRes.error || "原生提取失败");
              }
            }));
            usedNative = true;
          }
        } catch (errNative) {
          console.warn("Android native archive inspection error:", errNative);
        }
      }

      if (!files || files.length === 0) {
        files = await ArchiveEngine.parseArchive(file);
      }

      currentArchiveFiles = files;
      archiveContentsBox.style.display = "block";
      const format = files[0]?.format || file.name.split(".").pop().toUpperCase();
      archiveFormatBadge.innerText = `${format} 引擎${usedNative ? " (原生)" : ""}`;
      archiveCountBadge.innerText = `${files.length} 个文件`;

      renderArchiveFiles(files);
      showAppToast(`解析完成: 包含 ${files.length} 个条目`);
    } catch (e) {
      showAppToast(`解析归档失败: ${e.message}`);
    }
  }

  function renderArchiveFiles(files) {
    if (!archiveFileList) return;
    archiveFileList.innerHTML = "";

    const query = (archiveSearchFilter?.value || "").toLowerCase().trim();
    const filtered = query ? files.filter((f) => f.name.toLowerCase().includes(query)) : files;

    if (filtered.length === 0) {
      archiveFileList.innerHTML = `<div style="text-align: center; font-size: 12px; color: var(--text-muted); padding: 14px;">未匹配到文件</div>`;
      return;
    }

    for (const f of filtered) {
      const row = document.createElement("div");
      row.style.display = "flex";
      row.style.alignItems = "center";
      row.style.justifyContent = "space-between";
      row.style.padding = "8px 10px";
      row.style.background = "var(--bg-input)";
      row.style.borderRadius = "var(--radius-sm)";
      row.style.marginBottom = "4px";
      row.style.fontSize = "12px";

      row.innerHTML = `
        <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 65%;">
          <span style="color: ${f.isDir ? "var(--accent-warning)" : "var(--text-main)"}; font-weight: 500;">
            ${f.isDir ? "📁" : "📄"} ${f.name}
          </span>
          <div style="font-size: 10px; color: var(--text-muted); margin-top: 2px;">
            大小: ${ArchiveEngine.formatBytes(f.uncompressedSize)} · 算法: ${f.method}
          </div>
        </div>
        <button class="btn-secondary btn-sm btn-extract-single" style="width: auto; padding: 4px 10px;">提取</button>
      `;

      row.querySelector(".btn-extract-single").addEventListener("click", async () => {
        showAppToast(`正在解压: ${f.name}`);
        const fname = f.name.split("/").pop() || "extracted_file";
        try {
          if (window.AndroidBridge && window.AndroidBridge.saveBase64File) {
            let b64 = "";
            if (f.getNativeBase64) {
              b64 = f.getNativeBase64();
            } else {
              const data = await f.getData();
              const u8 = new Uint8Array(data);
              let bin = "";
              for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
              b64 = btoa(bin);
            }
            window.AndroidBridge.saveBase64File(fname, b64, "");
            showAppToast(`已提取并保存至下载目录: ${fname}`);
          } else {
            const data = await f.getData();
            const blob = new Blob([data]);
            triggerWebDownload(blob, fname);
            showAppToast("提取完成！");
          }
        } catch (err) {
          showAppToast(`提取失败: ${err.message}`);
        }
      });

      archiveFileList.appendChild(row);
    }
  }

  if (archiveSearchFilter) {
    archiveSearchFilter.addEventListener("input", () => {
      renderArchiveFiles(currentArchiveFiles);
    });
  }

  if (btnExtractAllArchive) {
    btnExtractAllArchive.addEventListener("click", async () => {
      if (!currentArchiveFiles || currentArchiveFiles.length === 0) return;
      showAppToast(`正在批量解压 ${currentArchiveFiles.length} 个条目...`);

      if (window.AndroidBridge && window.AndroidBridge.extractAllArchiveNative && currentArchiveBase64 && currentArchiveFile) {
        try {
          const resStr = window.AndroidBridge.extractAllArchiveNative(currentArchiveBase64, currentArchiveFile.name);
          const res = JSON.parse(resStr);
          if (res.ok) {
            showAppToast(`全部完成！已成功解压 ${res.count} 个文件至系统下载目录`);
            return;
          }
        } catch (e) {
          console.warn("Native extract all error:", e);
        }
      }

      for (const f of currentArchiveFiles) {
        if (f.isDir) continue;
        try {
          const fname = f.name.split("/").pop() || "file";
          if (window.AndroidBridge && window.AndroidBridge.saveBase64File) {
            let b64 = f.getNativeBase64 ? f.getNativeBase64() : null;
            if (!b64) {
              const data = await f.getData();
              const u8 = new Uint8Array(data);
              let bin = "";
              for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
              b64 = btoa(bin);
            }
            window.AndroidBridge.saveBase64File(fname, b64, "");
          } else {
            const data = await f.getData();
            const blob = new Blob([data]);
            triggerWebDownload(blob, fname);
          }
        } catch (_) {}
      }
      showAppToast("全部文件已成功批量提取导出！");
    });
  }

  // --- Tool 4: Smart AI & ACG Translator Logic ---
  const btnToggleTransConfig = document.getElementById("btn-toggle-trans-config");
  const transConfigPanelBody = document.getElementById("trans-config-panel-body");
  const transConfigStatusBadge = document.getElementById("trans-config-status-badge");
  const transProviderSelect = document.getElementById("trans-provider-select");
  const transBaseUrl = document.getElementById("trans-base-url");
  const transApiKey = document.getElementById("trans-api-key");
  const transModelName = document.getElementById("trans-model-name");
  const transBaiduBox = document.getElementById("trans-baidu-box");
  const transBaiduAppId = document.getElementById("trans-baidu-appid");
  const transBaiduAppKey = document.getElementById("trans-baidu-appkey");
  const transOpenAiBox = document.getElementById("trans-openai-box");
  const btnSaveTransConfig = document.getElementById("btn-save-trans-config");
  const btnTestTransApi = document.getElementById("btn-test-trans-api");
  const transInput = document.getElementById("trans-input");
  const transOutput = document.getElementById("trans-output");
  const transTargetLang = document.getElementById("trans-target-lang");
  const btnDoTrans = document.getElementById("btn-do-trans");
  const btnCopyTransResult = document.getElementById("btn-copy-trans-result");

  function updateTransProviderUi(provider) {
    const presetsBox = document.getElementById("preset-deepseek")?.parentElement;
    if (transBaiduBox) transBaiduBox.style.display = provider === "baidu" ? "block" : "none";
    if (transOpenAiBox) transOpenAiBox.style.display = (provider === "openai" || provider === "deepl") ? "block" : "none";
    if (presetsBox) presetsBox.style.display = provider === "openai" ? "flex" : "none";
    if (transConfigStatusBadge) {
      const map = {
        openai: "OpenAI 兼容模式",
        deepl: "DeepL 官方接口",
        google: "Google 免费通道",
        baidu: "百度翻译开放平台",
        offline: "离线二次元词库"
      };
      transConfigStatusBadge.innerText = map[provider] || provider;
    }
  }

  function loadTranslatorConfigUi() {
    const cfg = TranslatorEngine.getConfig();
    if (transProviderSelect) transProviderSelect.value = cfg.provider;
    if (transBaseUrl) transBaseUrl.value = cfg.baseUrl || "";
    if (transApiKey) transApiKey.value = cfg.apiKey || "";
    if (transModelName) transModelName.value = cfg.model || "";
    if (transBaiduAppId) transBaiduAppId.value = cfg.baiduAppId || "";
    if (transBaiduAppKey) transBaiduAppKey.value = cfg.baiduKey || "";
    updateTransProviderUi(cfg.provider);
  }

  if (transProviderSelect) {
    transProviderSelect.addEventListener("change", (e) => {
      updateTransProviderUi(e.target.value);
    });
  }

  if (btnToggleTransConfig && transConfigPanelBody) {
    btnToggleTransConfig.addEventListener("click", () => {
      const isHidden = transConfigPanelBody.style.display === "none";
      transConfigPanelBody.style.display = isHidden ? "block" : "none";
    });
  }

  // Presets
  const presetDeepSeek = document.getElementById("preset-deepseek");
  const presetOpenAI = document.getElementById("preset-openai");
  const presetQwen = document.getElementById("preset-qwen");
  const presetLocal = document.getElementById("preset-local");

  if (presetDeepSeek) {
    presetDeepSeek.addEventListener("click", () => {
      transProviderSelect.value = "openai";
      updateTransProviderUi("openai");
      transBaseUrl.value = "https://api.deepseek.com/v1";
      transModelName.value = "deepseek-chat";
      showAppToast("已载入 DeepSeek 官方配置模板");
    });
  }
  if (presetOpenAI) {
    presetOpenAI.addEventListener("click", () => {
      transProviderSelect.value = "openai";
      updateTransProviderUi("openai");
      transBaseUrl.value = "https://api.openai.com/v1";
      transModelName.value = "gpt-4o-mini";
      showAppToast("已载入 OpenAI 官方配置模板");
    });
  }
  if (presetQwen) {
    presetQwen.addEventListener("click", () => {
      transProviderSelect.value = "openai";
      updateTransProviderUi("openai");
      transBaseUrl.value = "https://dashscope.aliyuncs.com/compatible-mode/v1";
      transModelName.value = "qwen-turbo";
      showAppToast("已载入通义千问配置模板");
    });
  }
  if (presetLocal) {
    presetLocal.addEventListener("click", () => {
      transProviderSelect.value = "openai";
      updateTransProviderUi("openai");
      transBaseUrl.value = "http://10.0.2.2:11434/v1";
      transModelName.value = "qwen2.5:7b";
      showAppToast("已载入本地 Ollama 模拟器回环地址");
    });
  }

  if (btnSaveTransConfig) {
    btnSaveTransConfig.addEventListener("click", () => {
      const updated = TranslatorEngine.saveConfig({
        provider: transProviderSelect.value,
        baseUrl: transBaseUrl ? transBaseUrl.value.trim() : "",
        apiKey: transApiKey ? transApiKey.value.trim() : "",
        model: transModelName ? transModelName.value.trim() : "",
        baiduAppId: transBaiduAppId ? transBaiduAppId.value.trim() : "",
        baiduKey: transBaiduAppKey ? transBaiduAppKey.value.trim() : ""
      });
      loadTranslatorConfigUi();
      showAppToast("翻译接口配置已保存");
    });
  }

  if (btnTestTransApi) {
    btnTestTransApi.addEventListener("click", async () => {
      const cfg = {
        provider: transProviderSelect.value,
        baseUrl: transBaseUrl ? transBaseUrl.value.trim() : "",
        apiKey: transApiKey ? transApiKey.value.trim() : "",
        model: transModelName ? transModelName.value.trim() : "",
        baiduAppId: transBaiduAppId ? transBaiduAppId.value.trim() : "",
        baiduKey: transBaiduAppKey ? transBaiduAppKey.value.trim() : ""
      };
      showAppToast("正在测试 API 连通性...");
      const res = await TranslatorEngine.testConnection(cfg);
      if (res.ok) {
        showAppToast(`接口测试成功！延时: ${res.latencyMs}ms (${res.output})`);
      } else {
        showAppToast(`连接失败: ${res.error}`);
      }
    });
  }

  if (btnDoTrans) {
    btnDoTrans.addEventListener("click", async () => {
      const text = transInput.value.trim();
      if (!text) {
        showAppToast("请输入待翻译的文本内容！");
        return;
      }
      const targetLang = transTargetLang.value;
      btnDoTrans.disabled = true;
      btnDoTrans.innerText = "翻译中...";

      try {
        const out = await TranslatorEngine.translate(text, targetLang, (statusMsg) => {
          transOutput.value = `[${statusMsg}]`;
        });
        transOutput.value = out;
        showAppToast("翻译成功！");
      } catch (err) {
        transOutput.value = `[翻译异常] ${err.message}`;
        showAppToast(err.message);
      } finally {
        btnDoTrans.disabled = false;
        btnDoTrans.innerText = "立即执行高保真翻译";
      }
    });
  }

  // ACG Quick chips
  document.querySelectorAll(".acg-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const word = chip.innerText.trim();
      transInput.value = word;
      btnDoTrans.click();
    });
  });

  if (btnCopyTransResult) {
    btnCopyTransResult.addEventListener("click", () => {
      const text = transOutput.value.trim();
      if (!text) return;
      navigator.clipboard.writeText(text).then(() => {
        showAppToast("译文已复制至剪贴板");
      }).catch(() => {
        showAppToast("已复制");
      });
    });
  }

  // --- Clear Cache in Settings ---
  const btnClearCache = document.getElementById("btn-clear-cache");
  if (btnClearCache) {
    btnClearCache.addEventListener("click", () => {
      localStorage.clear();
      showAppToast("本地缓存与配置已彻底清空，即将重启");
      setTimeout(() => location.reload(), 600);
    });
  }

  // --- Cross Device Upscale & Local Cloud Handlers ---
  const cloudPcHostInput = document.getElementById("cloud-pc-host");
  const btnDiscoverPc = document.getElementById("btn-discover-pc");
  const btnTestPcConn = document.getElementById("btn-test-pc-conn");
  const cloudConnStatus = document.getElementById("cloud-conn-status");
  const cloudUpscaleDropzone = document.getElementById("cloud-upscale-dropzone");
  const cloudUpscaleInput = document.getElementById("cloud-upscale-input");
  const cloudUpscaleFilename = document.getElementById("cloud-upscale-filename");
  const cloudUpscaleFileinfo = document.getElementById("cloud-upscale-fileinfo");
  const cloudUpscaleModel = document.getElementById("cloud-upscale-model");
  const cloudUpscaleScale = document.getElementById("cloud-upscale-scale");
  const btnStartCloudUpscale = document.getElementById("btn-start-cloud-upscale");
  const cloudUpscaleResultBox = document.getElementById("cloud-upscale-result-box");
  const cloudUpscaleResultImg = document.getElementById("cloud-upscale-result-img");
  const cloudUpscaleResultInfo = document.getElementById("cloud-upscale-result-info");
  const btnSaveCloudUpscaleImg = document.getElementById("btn-save-cloud-upscale-img");
  const btnSelectDropFile = document.getElementById("btn-select-drop-file");
  const chieriDropFileInput = document.getElementById("chieri-drop-file-input");
  const btnSyncClipboard = document.getElementById("btn-sync-clipboard");

  let currentUpscaleImageBase64 = null;
  let currentUpscaleResultBase64 = null;

  // Initialize saved PC host
  if (cloudPcHostInput && window.CrossDeviceEngine) {
    if (window.CrossDeviceEngine.connectedServerUrl) {
      cloudPcHostInput.value = window.CrossDeviceEngine.connectedServerUrl;
      if (cloudConnStatus) {
        cloudConnStatus.innerText = `已配置服务器: ${window.CrossDeviceEngine.connectedServerUrl} (${window.CrossDeviceEngine.connectedHostName || "PC"})`;
        cloudConnStatus.style.color = "var(--accent-success)";
      }
    }
  }

  if (btnDiscoverPc) {
    btnDiscoverPc.addEventListener("click", async () => {
      showAppToast("正在通过 UDP 广播与局域网扫描寻找 PC 端...");
      if (cloudConnStatus) cloudConnStatus.innerText = "状态: 正在探测局域网 PC...";
      try {
        const found = await CrossDeviceEngine.discoverPC();
        if (found && found.length > 0) {
          const pc = found[0];
          cloudPcHostInput.value = pc.url;
          CrossDeviceEngine.setConnectedServer(pc.url, pc.hostname);
          if (cloudConnStatus) {
            cloudConnStatus.innerText = `已成功连线 PC: ${pc.hostname} (${pc.url})`;
            cloudConnStatus.style.color = "var(--accent-success)";
          }
          showAppToast(`发现 PC 端: ${pc.hostname}`);
        } else {
          if (cloudConnStatus) {
            cloudConnStatus.innerText = "未搜寻到局域网 PC，请在上方输入框手动指定 IP:端口";
            cloudConnStatus.style.color = "var(--accent-warning)";
          }
          showAppToast("未探测到 PC，请手动输入 IP");
        }
      } catch (e) {
        showAppToast(`发现失败: ${e.message}`);
      }
    });
  }

  if (btnTestPcConn) {
    btnTestPcConn.addEventListener("click", async () => {
      const url = cloudPcHostInput ? cloudPcHostInput.value.trim() : "";
      if (!url) {
        showAppToast("请输入 PC 端 IP 与端口");
        return;
      }
      showAppToast("正在连接 PC 服务...");
      const fullUrl = url.startsWith("http") ? url : `http://${url}`;
      const res = await CrossDeviceEngine.pingServer(fullUrl);
      if (res.ok) {
        CrossDeviceEngine.setConnectedServer(fullUrl, res.hostname);
        if (cloudConnStatus) {
          cloudConnStatus.innerText = `连线正常: ${res.hostname || "PC"} (Chieri Local Cloud v${res.version || "1.0"})`;
          cloudConnStatus.style.color = "var(--accent-success)";
        }
        showAppToast(`连接成功: ${res.hostname || "PC"}`);
      } else {
        if (cloudConnStatus) {
          cloudConnStatus.innerText = `连接失败: ${res.error}`;
          cloudConnStatus.style.color = "var(--accent-danger)";
        }
        showAppToast(`连接失败: ${res.error}`);
      }
    });
  }

  if (cloudUpscaleDropzone && cloudUpscaleInput) {
    cloudUpscaleDropzone.addEventListener("click", () => cloudUpscaleInput.click());
    cloudUpscaleInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      cloudUpscaleFilename.innerText = file.name;
      cloudUpscaleFileinfo.innerText = `${(file.size / 1024).toFixed(1)} KB · ${file.type || "图像"}`;

      const reader = new FileReader();
      reader.onload = (evt) => {
        currentUpscaleImageBase64 = evt.target.result;
      };
      reader.readAsDataURL(file);
    });
  }

  if (btnStartCloudUpscale) {
    btnStartCloudUpscale.addEventListener("click", async () => {
      if (!currentUpscaleImageBase64) {
        showAppToast("请先选择待超分的图像文件！");
        return;
      }
      const model = cloudUpscaleModel ? cloudUpscaleModel.value : "real-cugan";
      const scale = cloudUpscaleScale ? parseInt(cloudUpscaleScale.value, 10) : 4;

      btnStartCloudUpscale.disabled = true;
      btnStartCloudUpscale.innerText = "正在投送至电脑端并执行超分...";
      showAppToast("已提交任务至 PC 端，请稍候...");

      try {
        const res = await CrossDeviceEngine.upscaleImageOnPC(currentUpscaleImageBase64, {
          model: model,
          scale: scale
        });

        currentUpscaleResultBase64 = res.previewBase64;
        if (cloudUpscaleResultBox && cloudUpscaleResultImg) {
          cloudUpscaleResultImg.src = res.previewBase64;
          cloudUpscaleResultBox.style.display = "block";
          if (cloudUpscaleResultInfo) {
            cloudUpscaleResultInfo.innerText = `超分成功！倍率: ${scale}x · 模型: ${model} · 耗时: ${res.costTime || "完成"}`;
          }
        }
        showAppToast("电脑端 AI 超分已顺利完成！");
      } catch (err) {
        showAppToast(`超分失败: ${err.message}`);
      } finally {
        btnStartCloudUpscale.disabled = false;
        btnStartCloudUpscale.innerText = "发送至 PC 端执行 AI 超分";
      }
    });
  }

  if (btnSaveCloudUpscaleImg) {
    btnSaveCloudUpscaleImg.addEventListener("click", () => {
      if (!currentUpscaleResultBase64) return;
      if (window.AndroidBridge && window.AndroidBridge.saveImageToGallery) {
        const ok = window.AndroidBridge.saveImageToGallery(currentUpscaleResultBase64, `chieri_upscale_${Date.now()}.png`);
        if (ok) showAppToast("高清超分图像已保存至手机相册");
        else showAppToast("保存失败，请检查存储权限");
      } else {
        const a = document.createElement("a");
        a.href = currentUpscaleResultBase64;
        a.download = `chieri_upscale_${Date.now()}.png`;
        a.click();
        showAppToast("超分图像下载已启动");
      }
    });
  }

  if (btnSelectDropFile && chieriDropFileInput) {
    btnSelectDropFile.addEventListener("click", () => chieriDropFileInput.click());
    chieriDropFileInput.addEventListener("change", async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      showAppToast(`正在投送 ${file.name} 到电脑...`);
      const reader = new FileReader();
      reader.onload = async (evt) => {
        try {
          const res = await CrossDeviceEngine.sendFileToPC(evt.target.result, file.name);
          if (res.ok) showAppToast(`文件 ${file.name} 已成功接收至 PC 端！`);
          else showAppToast(`投送失败: ${res.error}`);
        } catch (err) {
          showAppToast(`投送异常: ${err.message}`);
        }
      };
      reader.readAsDataURL(file);
    });
  }

  if (btnSyncClipboard) {
    btnSyncClipboard.addEventListener("click", async () => {
      try {
        let text = "";
        if (navigator.clipboard && navigator.clipboard.readText) {
          text = await navigator.clipboard.readText();
        }
        if (!text) {
          showAppToast("剪贴板中没有可同步的纯文本内容");
          return;
        }
        showAppToast("正在向 PC 同步剪贴板...");
        const res = await CrossDeviceEngine.syncClipboard(text, "send");
        if (res.ok) showAppToast("手机剪贴板已秒级同步至 PC 端！");
        else showAppToast(`剪贴板同步失败: ${res.error}`);
      } catch (err) {
        showAppToast(`同步异常: ${err.message}`);
      }
    });
  }

  // --- Verification Helpers for Automated UI Testing ---
  window.__loadTestAudioAndConvert = async function(targetFormat = "mp3") {
    try {
      const sampleRate = 44100;
      const channels = 2;
      const length = 44100; // 1s
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const buffer = ctx.createBuffer(channels, length, sampleRate);
      const d0 = buffer.getChannelData(0);
      const d1 = buffer.getChannelData(1);
      for (let i = 0; i < length; i++) {
        d0[i] = Math.sin(2 * Math.PI * 440 * i / sampleRate);
        d1[i] = Math.sin(2 * Math.PI * 880 * i / sampleRate);
      }
      const wavBlob = AudioEngine.encodeWav(buffer);
      const testFile = new File([wavBlob], "chieri_test_audio.wav", { type: "audio/wav" });
      loadAudioFile(testFile);
      if (document.getElementById("audio-target-format")) {
        document.getElementById("audio-target-format").value = targetFormat;
      }
      setTimeout(() => {
        if (btnStartAudioConvert) btnStartAudioConvert.click();
      }, 300);
    } catch (e) {
      showAppToast("测试音频生成失败: " + e.message);
    }
  };

  window.__loadTestArchive = async function() {
    try {
      const header = new Uint8Array(512);
      const nameStr = "chieri_sample.txt";
      for (let i = 0; i < nameStr.length; i++) header[i] = nameStr.charCodeAt(i);
      const mode = "0000644\0";
      for (let i = 0; i < mode.length; i++) header[100 + i] = mode.charCodeAt(i);
      const content = new TextEncoder().encode("Chieri Toolbox Mobile Test Archive OK!\nComprehensive Multi-Format Verified.");
      const sizeStr = content.length.toString(8).padStart(11, '0') + " ";
      for (let i = 0; i < sizeStr.length; i++) header[124 + i] = sizeStr.charCodeAt(i);
      const magic = "ustar\0";
      for (let i = 0; i < magic.length; i++) header[257 + i] = magic.charCodeAt(i);
      for (let i = 0; i < 8; i++) header[148 + i] = 32;
      let sum = 0;
      for (let i = 0; i < 512; i++) sum += header[i];
      const chkStr = sum.toString(8).padStart(6, '0') + "\0 ";
      for (let i = 0; i < chkStr.length; i++) header[148 + i] = chkStr.charCodeAt(i);
      const padLen = 512 - (content.length % 512);
      const padded = new Uint8Array(content.length + (padLen === 512 ? 0 : padLen));
      padded.set(content);
      const eof = new Uint8Array(1024);
      const tarBlob = new Blob([header, padded, eof], { type: "application/x-tar" });
      const file = new File([tarBlob], "chieri_pack.tar", { type: "application/x-tar" });
      loadArchiveFile(file);
    } catch (e) {
      showAppToast("测试归档生成失败: " + e.message);
    }
  };

  // Initialize UI customization on startup
  initUiCustomization();

})();
