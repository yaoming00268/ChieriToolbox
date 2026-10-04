/**
 * 二次元便签与触控白板 (Whiteboard)
 * 支持移动端多点触控平滑绘制、调色盘、橡皮擦及保存为图片
 */

const WhiteboardEngine = (function () {
  let canvas = null;
  let ctx = null;
  let isDrawing = false;
  let lastX = 0, lastY = 0;
  let color = "#FF6B8B";
  let lineWidth = 4;
  let isEraser = false;

  function init(canvasEl) {
    canvas = canvasEl;
    ctx = canvas.getContext("2d");
    resize();

    // Event listeners
    canvas.addEventListener("touchstart", onTouchStart, { passive: false });
    canvas.addEventListener("touchmove", onTouchMove, { passive: false });
    window.addEventListener("touchend", onTouchEnd);

    canvas.addEventListener("mousedown", onMouseDown);
    canvas.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  function resize() {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      canvas.width = rect.width;
      canvas.height = rect.height;
      clear();
    }
  }

  function clear() {
    if (!ctx || !canvas) return;
    ctx.fillStyle = "#14141E";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  function getPos(e) {
    const rect = canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    return {
      x: clientX - rect.left,
      y: clientY - rect.top
    };
  }

  function startDraw(pos) {
    isDrawing = true;
    lastX = pos.x;
    lastY = pos.y;
  }

  function moveDraw(pos) {
    if (!isDrawing || !ctx) return;
    ctx.beginPath();
    ctx.moveTo(lastX, lastY);
    ctx.lineTo(pos.x, pos.y);
    ctx.strokeStyle = isEraser ? "#14141E" : color;
    ctx.lineWidth = isEraser ? lineWidth * 3 : lineWidth;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.stroke();

    lastX = pos.x;
    lastY = pos.y;
  }

  function stopDraw() {
    isDrawing = false;
  }

  function onTouchStart(e) {
    e.preventDefault();
    startDraw(getPos(e));
  }

  function onTouchMove(e) {
    e.preventDefault();
    moveDraw(getPos(e));
  }

  function onTouchEnd() {
    stopDraw();
  }

  function onMouseDown(e) {
    startDraw(getPos(e));
  }

  function onMouseMove(e) {
    moveDraw(getPos(e));
  }

  function onMouseUp() {
    stopDraw();
  }

  function setColor(newColor) {
    color = newColor;
    isEraser = false;
  }

  function setEraser(eraserMode) {
    isEraser = eraserMode;
  }

  function setLineWidth(w) {
    lineWidth = w;
  }

  function exportImage() {
    return canvas ? canvas.toDataURL("image/png") : null;
  }

  return {
    init,
    clear,
    resize,
    setColor,
    setEraser,
    setLineWidth,
    exportImage
  };
})();

window.WhiteboardEngine = WhiteboardEngine;
