/**
 * 手机特有悬浮窗 / 悬浮球 (Floating Ball & Quick Menu)
 * 支持平滑拖拽、边缘自动吸附、快速弹出菜单、随时开启/关闭
 */

(function () {
  const container = document.getElementById("floating-ball-container");
  const ball = document.getElementById("floating-ball");
  const menu = document.getElementById("floating-ball-menu");

  if (!container || !ball || !menu) return;

  let isDragging = false;
  let startX = 0, startY = 0;
  let initialLeft = 0, initialTop = 0;
  let hasMoved = false;
  let isMenuOpen = false;

  // Retrieve saved preference
  let ballEnabled = localStorage.getItem("chieri_floating_ball_enabled") !== "false";

  function applyVisibility(enabled) {
    ballEnabled = enabled;
    localStorage.setItem("chieri_floating_ball_enabled", enabled ? "true" : "false");
    container.style.display = enabled ? "block" : "none";
    if (!enabled) {
      closeMenu();
    }

    // Sync switches in UI
    const drawerSwitch = document.getElementById("drawer-floating-ball-switch");
    if (drawerSwitch) drawerSwitch.checked = enabled;
    const settingsSwitch = document.getElementById("settings-floating-ball-switch");
    if (settingsSwitch) settingsSwitch.checked = enabled;
  }

  function initPosition() {
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;
    const defaultX = Math.max(16, screenWidth - 70);
    const defaultY = Math.max(120, Math.floor(screenHeight * 0.4));
    container.style.left = defaultX + "px";
    container.style.top = defaultY + "px";
    ball.classList.add("docked-right");
  }

  function snapToEdge() {
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;
    const currentLeft = container.offsetLeft;
    const isCloserToLeft = currentLeft + 27 < screenWidth / 2;

    container.style.transition = "left 0.25s cubic-bezier(0.18, 0.89, 0.32, 1.28), top 0.25s cubic-bezier(0.18, 0.89, 0.32, 1.28)";
    if (isCloserToLeft) {
      container.style.left = "16px";
      ball.classList.remove("docked-right");
      ball.classList.add("docked-left");
    } else {
      container.style.left = Math.max(16, screenWidth - 70) + "px";
      ball.classList.remove("docked-left");
      ball.classList.add("docked-right");
    }

    // Clamp vertical position safely within viewport
    const maxTop = Math.max(60, screenHeight - 70);
    const clampedTop = Math.max(60, Math.min(maxTop, container.offsetTop));
    container.style.top = clampedTop + "px";

    setTimeout(() => {
      container.style.transition = "";
    }, 260);
  }

  function positionMenu() {
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;
    const currentLeft = container.offsetLeft;
    const currentTop = container.offsetTop;

    // Horizontal placement
    if (currentLeft + 27 < screenWidth / 2) {
      menu.style.left = "60px";
      menu.style.right = "auto";
    } else {
      menu.style.left = "-175px";
      menu.style.right = "auto";
    }

    // Vertical placement - ensure it stays inside screen
    const menuHeight = menu.offsetHeight || 240;
    if (currentTop + menuHeight > screenHeight - 16) {
      if (currentTop + 54 - menuHeight >= 16) {
        menu.style.top = "auto";
        menu.style.bottom = "0px";
      } else {
        menu.style.top = Math.max(0, 16 - currentTop) + "px";
        menu.style.bottom = "auto";
      }
    } else {
      menu.style.top = "0px";
      menu.style.bottom = "auto";
    }
  }

  function toggleMenu() {
    isMenuOpen = !isMenuOpen;
    console.log("toggleMenu invoked! isMenuOpen now:", isMenuOpen);
    if (isMenuOpen) {
      positionMenu();
      menu.classList.add("active");
      console.log("Menu styled left:", menu.style.left, "top:", menu.style.top);
    } else {
      menu.classList.remove("active");
    }
  }

  function closeMenu() {
    isMenuOpen = false;
    menu.classList.remove("active");
  }

  // Pointer Handlers
  function onStart(clientX, clientY) {
    isDragging = true;
    hasMoved = false;
    startX = clientX;
    startY = clientY;
    initialLeft = container.offsetLeft;
    initialTop = container.offsetTop;
    container.style.transition = "";
  }

  function onMove(clientX, clientY) {
    if (!isDragging) return;
    const dx = clientX - startX;
    const dy = clientY - startY;

    if (Math.abs(dx) > 8 || Math.abs(dy) > 8) {
      hasMoved = true;
      if (isMenuOpen) closeMenu();
    }

    let nextLeft = initialLeft + dx;
    let nextTop = initialTop + dy;

    // Boundaries
    const maxLeft = window.innerWidth - 64;
    const maxTop = window.innerHeight - 70;
    nextLeft = Math.max(8, Math.min(maxLeft, nextLeft));
    nextTop = Math.max(60, Math.min(maxTop, nextTop));

    container.style.left = nextLeft + "px";
    container.style.top = nextTop + "px";
  }

  function onEnd() {
    console.log("onEnd called! isDragging:", isDragging, "hasMoved:", hasMoved);
    if (!isDragging) return;
    isDragging = false;

    if (!hasMoved) {
      toggleMenu();
    } else {
      snapToEdge();
    }
  }

  // Unified Pointer Events
  ball.addEventListener("pointerdown", (e) => {
    e.stopPropagation();
    try { ball.setPointerCapture(e.pointerId); } catch (_) {}
    onStart(e.clientX, e.clientY);
  });

  ball.addEventListener("pointermove", (e) => {
    e.stopPropagation();
    if (isDragging) {
      onMove(e.clientX, e.clientY);
    }
  });

  ball.addEventListener("pointerup", (e) => {
    e.stopPropagation();
    try { ball.releasePointerCapture(e.pointerId); } catch (_) {}
    onEnd();
  });

  ball.addEventListener("pointercancel", (e) => {
    e.stopPropagation();
    try { ball.releasePointerCapture(e.pointerId); } catch (_) {}
    if (isDragging) {
      isDragging = false;
      snapToEdge();
    }
  });

  ball.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
  });

  // Close menu when tapping outside
  document.addEventListener("pointerdown", (e) => {
    if (isMenuOpen && !container.contains(e.target)) {
      closeMenu();
    }
  });

  // Explicit close button on bubble menu header
  const btnCloseMenu = menu.querySelector(".btn-close-floating-menu");
  if (btnCloseMenu) {
    btnCloseMenu.addEventListener("click", (e) => {
      e.stopPropagation();
      closeMenu();
    });
  }

  // Menu action items delegation
  menu.addEventListener("click", (e) => {
    const item = e.target.closest(".float-menu-item");
    if (!item) return;

    const action = item.getAttribute("data-action");
    closeMenu();

    if (action === "home") {
      window.navigateToTool && window.navigateToTool("dashboard");
    } else if (action === "sidebar") {
      window.openSidebar && window.openSidebar();
    } else if (action === "ncm") {
      window.navigateToTool && window.navigateToTool("ncm_decryptor");
    } else if (action === "downloader") {
      window.navigateToTool && window.navigateToTool("media_downloader");
    } else if (action === "settings") {
      window.navigateToTool && window.navigateToTool("settings");
    } else if (action === "close_ball") {
      applyVisibility(false);
      window.showAppToast && window.showAppToast("已关闭悬浮窗，可在侧边栏或设置中重新开启");
    }
  });

  // Screen rotation & resize adaptation
  function handleResize() {
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;

    // Reposition horizontally based on dock side
    const isDockedLeft = ball.classList.contains("docked-left");
    if (isDockedLeft) {
      container.style.left = "16px";
    } else {
      container.style.left = Math.max(16, screenWidth - 70) + "px";
    }

    // Reposition vertically within safe viewport bounds
    const maxTop = Math.max(60, screenHeight - 70);
    let currentTop = container.offsetTop;
    if (currentTop < 60) {
      currentTop = 60;
    } else if (currentTop > maxTop) {
      currentTop = maxTop;
    }
    container.style.top = currentTop + "px";

    if (isMenuOpen) {
      positionMenu();
    }
  }

  window.addEventListener("resize", handleResize);
  window.addEventListener("orientationchange", () => {
    setTimeout(handleResize, 150);
  });

  // Export public API
  window.setFloatingBallVisible = applyVisibility;
  window.toggleFloatingBall = function () {
    applyVisibility(!ballEnabled);
  };
  window.isFloatingBallVisible = function () {
    return ballEnabled;
  };
  window.closeFloatingMenu = closeMenu;
  window.isFloatingMenuOpen = function () {
    return isMenuOpen;
  };

  // Init
  initPosition();
  applyVisibility(ballEnabled);
})();
