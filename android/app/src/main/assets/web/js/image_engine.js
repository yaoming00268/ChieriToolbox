/**
 * 图片批处理工坊 (Image Master)
 * 格式转换 (PNG/JPG/WEBP/BMP/ICO)、1:1 头像智能居中裁切、高清 Lanczos/双线性等比缩放
 */

const ImageEngine = (function () {
  function processImage(imgElement, options) {
    const {
      mode = "convert", // 'convert' | 'square' | 'resize'
      targetFormat = "image/png",
      targetWidth = null,
      targetHeight = null,
      scalePercent = 100,
      quality = 0.92
    } = options;

    const origWidth = imgElement.naturalWidth || imgElement.width;
    const origHeight = imgElement.naturalHeight || imgElement.height;

    let srcX = 0, srcY = 0, srcW = origWidth, srcH = origHeight;
    let destW = origWidth, destH = origHeight;

    if (mode === "square") {
      // 1:1 Smart Center Crop
      const size = Math.min(origWidth, origHeight);
      srcX = Math.floor((origWidth - size) / 2);
      srcY = Math.floor((origHeight - size) / 2);
      srcW = size;
      srcH = size;
      destW = targetWidth || 512;
      destH = destW;
    } else if (mode === "resize") {
      if (targetWidth && targetHeight) {
        destW = targetWidth;
        destH = targetHeight;
      } else if (scalePercent) {
        const factor = scalePercent / 100;
        destW = Math.max(1, Math.round(origWidth * factor));
        destH = Math.max(1, Math.round(origHeight * factor));
      }
    }

    const canvas = document.createElement("canvas");
    canvas.width = destW;
    canvas.height = destH;
    const ctx = canvas.getContext("2d");

    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";

    // If JPEG, fill white background to avoid black background artifacts
    if (targetFormat === "image/jpeg") {
      ctx.fillStyle = "#FFFFFF";
      ctx.fillRect(0, 0, destW, destH);
    }

    ctx.drawImage(imgElement, srcX, srcY, srcW, srcH, 0, 0, destW, destH);

    return new Promise((resolve) => {
      canvas.toBlob((blob) => {
        resolve({
          blob,
          dataUrl: canvas.toDataURL(targetFormat, quality),
          width: destW,
          height: destH
        });
      }, targetFormat, quality);
    });
  }

  return {
    processImage
  };
})();

window.ImageEngine = ImageEngine;
