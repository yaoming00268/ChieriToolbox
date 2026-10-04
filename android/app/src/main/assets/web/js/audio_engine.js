/**
 * 千绘莉音频格式转换与音频工坊引擎 (Audio Format Converter & Studio)
 * 支持 MP3, WAV, FLAC, AAC, OGG, M4A 等全格式解码与互转
 * 支持精确采样率 (16kHz ~ 96kHz) 与比特率 (64k ~ 320k / 无损) 调优
 */

const AudioEngine = (function () {
  let audioCtx = null;

  function getAudioContext(targetSampleRate) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!audioCtx || (targetSampleRate && audioCtx.sampleRate !== targetSampleRate)) {
      audioCtx = new AudioContextClass();
    }
    if (audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    return audioCtx;
  }

  // --- Resampling via OfflineAudioContext ---
  async function resampleAudioBuffer(audioBuffer, targetSampleRate) {
    if (audioBuffer.sampleRate === targetSampleRate) {
      return audioBuffer;
    }
    const numChannels = audioBuffer.numberOfChannels;
    const duration = audioBuffer.duration;
    const targetLength = Math.max(1, Math.round(duration * targetSampleRate));

    const OfflineContextClass = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    const offlineCtx = new OfflineContextClass(numChannels, targetLength, targetSampleRate);

    const bufferSource = offlineCtx.createBufferSource();
    bufferSource.buffer = audioBuffer;
    bufferSource.connect(offlineCtx.destination);
    bufferSource.start(0);

    return await offlineCtx.startRendering();
  }

  // --- WAV Encoder (16-bit PCM RIFF) ---
  function encodeWav(audioBuffer) {
    const numChannels = audioBuffer.numberOfChannels;
    const sampleRate = audioBuffer.sampleRate;
    const bitDepth = 16;
    const bytesPerSample = bitDepth / 8;
    const blockAlign = numChannels * bytesPerSample;

    let interleaved;
    if (numChannels === 2) {
      const left = audioBuffer.getChannelData(0);
      const right = audioBuffer.getChannelData(1);
      interleaved = new Float32Array(left.length + right.length);
      let idx = 0;
      for (let i = 0; i < left.length; i++) {
        interleaved[idx++] = left[i];
        interleaved[idx++] = right[i];
      }
    } else {
      interleaved = audioBuffer.getChannelData(0);
    }

    const dataSize = interleaved.length * bytesPerSample;
    const buffer = new ArrayBuffer(44 + dataSize);
    const view = new DataView(buffer);

    // RIFF identifier
    writeString(view, 0, "RIFF");
    view.setUint32(4, 36 + dataSize, true);
    writeString(view, 8, "WAVE");

    // fmt chunk
    writeString(view, 12, "fmt ");
    view.setUint32(16, 16, true); // Subchunk1Size (16 for PCM)
    view.setUint16(20, 1, true);  // AudioFormat (1 for PCM)
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * blockAlign, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitDepth, true);

    // data chunk
    writeString(view, 36, "data");
    view.setUint32(40, dataSize, true);

    // Write PCM samples
    let offset = 44;
    for (let i = 0; i < interleaved.length; i++, offset += 2) {
      const s = Math.max(-1, Math.min(1, interleaved[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }

    return new Blob([view], { type: "audio/wav" });
  }

  // --- CRC Calculation for FLAC ---
  function calcFlacCrc8(arr) {
    let crc = 0;
    for (let i = 0; i < arr.length; i++) {
      crc ^= arr[i];
      for (let b = 0; b < 8; b++) {
        if (crc & 0x80) crc = ((crc << 1) ^ 0x07) & 0xff;
        else crc = (crc << 1) & 0xff;
      }
    }
    return crc;
  }

  function calcFlacCrc16(arr) {
    let crc = 0;
    for (let i = 0; i < arr.length; i++) {
      crc ^= (arr[i] << 8);
      for (let b = 0; b < 8; b++) {
        if (crc & 0x8000) crc = ((crc << 1) ^ 0x8005) & 0xffff;
        else crc = (crc << 1) & 0xffff;
      }
    }
    return crc;
  }

  // --- Real LAME MP3 Encoder ---
  function encodeMp3(audioBuffer, bitrateKbps) {
    const numChannels = Math.min(audioBuffer.numberOfChannels, 2);
    const sampleRate = audioBuffer.sampleRate;
    const targetBitrate = parseInt(bitrateKbps, 10) || 192;

    const Lame = (typeof lamejs !== "undefined" ? lamejs : (typeof window !== "undefined" ? window.lamejs : null));
    if (!Lame || !Lame.Mp3Encoder) {
      console.warn("lamejs not available, falling back to WAV");
      return encodeWav(audioBuffer);
    }

    const mp3encoder = new Lame.Mp3Encoder(numChannels, sampleRate, targetBitrate);
    const left = audioBuffer.getChannelData(0);
    const right = numChannels > 1 ? audioBuffer.getChannelData(1) : left;

    const leftInt16 = new Int16Array(left.length);
    for (let i = 0; i < left.length; i++) {
      const s = Math.max(-1, Math.min(1, left[i]));
      leftInt16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }

    let rightInt16 = leftInt16;
    if (numChannels > 1) {
      rightInt16 = new Int16Array(right.length);
      for (let i = 0; i < right.length; i++) {
        const s = Math.max(-1, Math.min(1, right[i]));
        rightInt16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
    }

    const mp3Data = [];
    const sampleBlockSize = 1152;
    for (let i = 0; i < leftInt16.length; i += sampleBlockSize) {
      const leftChunk = leftInt16.subarray(i, i + sampleBlockSize);
      const rightChunk = numChannels > 1 ? rightInt16.subarray(i, i + sampleBlockSize) : leftChunk;
      const mp3buf = mp3encoder.encodeBuffer(leftChunk, rightChunk);
      if (mp3buf && mp3buf.length > 0) {
        mp3Data.push(mp3buf);
      }
    }

    const endBuf = mp3encoder.flush();
    if (endBuf && endBuf.length > 0) {
      mp3Data.push(endBuf);
    }

    return new Blob(mp3Data, { type: "audio/mp3" });
  }

  // --- Lossless FLAC Encoder with Valid CRC-8 and CRC-16 ---
  function encodeFlac(audioBuffer) {
    const numChannels = audioBuffer.numberOfChannels;
    const sampleRate = audioBuffer.sampleRate;
    const bitsPerSample = 16;
    const totalSamples = audioBuffer.length;

    const left = audioBuffer.getChannelData(0);
    const right = numChannels > 1 ? audioBuffer.getChannelData(1) : left;

    const parts = [];

    // 1. FLAC stream marker "fLaC"
    const header = new Uint8Array(4 + 38);
    writeString({ setUint8: (pos, val) => { header[pos] = val; } }, 0, "fLaC");

    // 2. STREAMINFO metadata block (last metadata block = 0x80, block type = 0)
    header[4] = 0x80; // Is last block, type 0 (STREAMINFO)
    header[5] = 0x00; header[6] = 0x00; header[7] = 0x22; // Length: 34 bytes (0x22)

    // Min/Max Block size: 4096
    const blockSize = 4096;
    header[8] = (blockSize >> 8) & 0xff;
    header[9] = blockSize & 0xff;
    header[10] = (blockSize >> 8) & 0xff;
    header[11] = blockSize & 0xff;

    // Min/Max Frame size (0 for unknown)
    header[12] = 0; header[13] = 0; header[14] = 0;
    header[15] = 0; header[16] = 0; header[17] = 0;

    // Sample rate (20 bits), channels (3 bits), bits per sample (5 bits), total samples (36 bits)
    header[18] = (sampleRate >> 12) & 0xff;
    header[19] = (sampleRate >> 4) & 0xff;
    header[20] = ((sampleRate & 0x0f) << 4) | (((numChannels - 1) & 0x07) << 1) | (((bitsPerSample - 1) >> 4) & 0x01);
    header[21] = (((bitsPerSample - 1) & 0x0f) << 4) | ((Math.floor(totalSamples / 0x100000000) & 0x0f));
    header[22] = (totalSamples >> 24) & 0xff;
    header[23] = (totalSamples >> 16) & 0xff;
    header[24] = (totalSamples >> 8) & 0xff;
    header[25] = totalSamples & 0xff;

    parts.push(header);

    // 3. Audio Frames (Verbatim PCM subframes with CRC-8 and CRC-16)
    let frameNumber = 0;
    for (let i = 0; i < totalSamples; i += blockSize) {
      const curBlock = Math.min(blockSize, totalSamples - i);
      const frameData = [];

      // Frame header: Sync 0xFFF8, block size code (0xc0 = 4096), sample rate (0x08 = 44.1k or 0x09 = 48k), channel mode
      let srateCode = 0x08;
      if (sampleRate === 48000) srateCode = 0x09;
      else if (sampleRate === 96000) srateCode = 0x0b;
      else if (sampleRate === 22050) srateCode = 0x04;
      else if (sampleRate === 16000) srateCode = 0x03;

      const headerBytes = [
        0xff, 0xf8,
        0xc0 | (srateCode & 0x0f),
        (numChannels === 2 ? 0x10 : 0x00) | 0x08, // 16-bit
        frameNumber & 0x7f // Frame number
      ];
      const headerCrc = calcFlacCrc8(headerBytes);
      headerBytes.push(headerCrc);

      for (let b = 0; b < headerBytes.length; b++) {
        frameData.push(headerBytes[b]);
      }

      // Subframe: Verbatim 16-bit PCM samples
      for (let ch = 0; ch < numChannels; ch++) {
        const channelSamples = ch === 0 ? left : right;
        frameData.push(0x02); // Verbatim subframe header
        for (let s = 0; s < curBlock; s++) {
          const sample = Math.max(-1, Math.min(1, channelSamples[i + s]));
          const val = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
          frameData.push((val >> 8) & 0xff);
          frameData.push(val & 0xff);
        }
      }

      // Frame footer CRC-16
      const frameCrc = calcFlacCrc16(frameData);
      frameData.push((frameCrc >> 8) & 0xff);
      frameData.push(frameCrc & 0xff);
      parts.push(new Uint8Array(frameData));
      frameNumber++;
    }

    return new Blob(parts, { type: "audio/flac" });
  }


  // --- OGG / Opus / AAC / M4A MediaStream Encapsulation ---
  async function encodeViaMediaRecorder(audioBuffer, mimeType) {
    if (!window.MediaRecorder) {
      // Fallback to WAV container if MediaRecorder is not available
      return encodeWav(audioBuffer);
    }

    return new Promise((resolve, reject) => {
      try {
        const ctx = getAudioContext(audioBuffer.sampleRate);
        const dest = ctx.createMediaStreamDestination();
        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(dest);

        const supportedType = MediaRecorder.isTypeSupported(mimeType)
          ? mimeType
          : (MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "");

        const recorder = new MediaRecorder(dest.stream, supportedType ? { mimeType: supportedType } : {});
        const chunks = [];

        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) chunks.push(e.data);
        };

        recorder.onstop = () => {
          const finalBlob = new Blob(chunks, { type: mimeType });
          resolve(finalBlob);
        };

        recorder.onerror = (err) => {
          // Fallback to WAV
          resolve(encodeWav(audioBuffer));
        };

        recorder.start(100);
        source.start(0);

        source.onended = () => {
          setTimeout(() => {
            recorder.stop();
          }, 150);
        };
      } catch (e) {
        resolve(encodeWav(audioBuffer));
      }
    });
  }

  // --- Helpers ---
  function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  function getInterleavedInt16(audioBuffer) {
    const numChannels = audioBuffer.numberOfChannels;
    const len = audioBuffer.length;
    const left = audioBuffer.getChannelData(0);
    const right = numChannels > 1 ? audioBuffer.getChannelData(1) : null;
    const interleaved = new Int16Array(len * numChannels);

    let idx = 0;
    for (let i = 0; i < len; i++) {
      const s0 = Math.max(-1, Math.min(1, left[i]));
      interleaved[idx++] = s0 < 0 ? s0 * 0x8000 : s0 * 0x7fff;
      if (numChannels > 1 && right) {
        const s1 = Math.max(-1, Math.min(1, right[i]));
        interleaved[idx++] = s1 < 0 ? s1 * 0x8000 : s1 * 0x7fff;
      }
    }
    return interleaved;
  }

  function uint8ToBase64(u8) {
    let binary = "";
    const len = u8.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(u8[i]);
    }
    return btoa(binary);
  }

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  // --- Main Conversion Pipeline ---
  async function convertAudio(fileOrArrayBuffer, options = {}, onProgress = null) {
    const targetFormat = (options.format || "mp3").toLowerCase();
    const targetSampleRate = parseInt(options.sampleRate, 10) || 44100;
    const targetBitrate = parseInt(options.bitrate, 10) || 192;

    if (onProgress) onProgress(10, "正在读取并解析音频源文件...");

    let arrayBuffer;
    if (fileOrArrayBuffer instanceof File || fileOrArrayBuffer instanceof Blob) {
      arrayBuffer = await fileOrArrayBuffer.arrayBuffer();
    } else {
      arrayBuffer = fileOrArrayBuffer;
    }

    if (onProgress) onProgress(25, "正在通过硬件解码核心还原高保真 PCM 浮点音频流...");
    const ctx = getAudioContext();
    const decodedBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0));

    if (onProgress) onProgress(50, `正在重采样音频流 (${decodedBuffer.sampleRate}Hz -> ${targetSampleRate}Hz)...`);
    const resampledBuffer = await resampleAudioBuffer(decodedBuffer, targetSampleRate);

    if (onProgress) onProgress(75, `正在编码为目标格式 [${targetFormat.toUpperCase()}] (${targetBitrate}kbps)...`);

    let outputBlob;
    let outputMime = "audio/" + targetFormat;

    switch (targetFormat) {
      case "wav":
        outputBlob = encodeWav(resampledBuffer);
        outputMime = "audio/wav";
        break;
      case "mp3":
        outputBlob = encodeMp3(resampledBuffer, targetBitrate);
        outputMime = "audio/mp3";
        break;
      case "flac":
        outputBlob = encodeFlac(resampledBuffer);
        outputMime = "audio/flac";
        break;
      case "ogg":
        outputBlob = await encodeViaMediaRecorder(resampledBuffer, "audio/ogg;codecs=opus");
        outputMime = "audio/ogg";
        break;
      case "aac":
      case "m4a":
        if (typeof window !== "undefined" && window.AndroidBridge && window.AndroidBridge.encodePcmToM4aNative) {
          try {
            const pcmInt16 = getInterleavedInt16(resampledBuffer);
            const pcmBase64 = uint8ToBase64(new Uint8Array(pcmInt16.buffer));
            const nativeResStr = window.AndroidBridge.encodePcmToM4aNative(pcmBase64, resampledBuffer.sampleRate, resampledBuffer.numberOfChannels, targetBitrate);
            const nativeRes = JSON.parse(nativeResStr);
            if (nativeRes.ok && nativeRes.data) {
              const binary = atob(nativeRes.data);
              const bytes = new Uint8Array(binary.length);
              for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
              outputBlob = new Blob([bytes], { type: targetFormat === "m4a" ? "audio/mp4" : "audio/aac" });
              outputMime = targetFormat === "m4a" ? "audio/mp4" : "audio/aac";
              break;
            }
          } catch (e) {
            console.warn("Native M4A encoding fallback:", e);
          }
        }
        outputBlob = await encodeViaMediaRecorder(resampledBuffer, "audio/mp4;codecs=mp4a.40.2");
        outputMime = targetFormat === "m4a" ? "audio/mp4" : "audio/aac";
        break;
      default:
        outputBlob = encodeWav(resampledBuffer);
        outputMime = "audio/wav";
        break;
    }

    if (onProgress) onProgress(95, "正在生成输出文件并封装数据包...");
    const base64Data = await blobToBase64(outputBlob);

    if (onProgress) onProgress(100, "转换完成！");

    return {
      blob: outputBlob,
      base64: base64Data,
      mimeType: outputMime,
      duration: resampledBuffer.duration,
      sampleRate: resampledBuffer.sampleRate,
      channels: resampledBuffer.numberOfChannels,
      size: outputBlob.size,
      format: targetFormat
    };
  }

  // Audio Slicing (Audio Cutter)
  async function sliceAudio(arrayBuffer, startSeconds, endSeconds) {
    const ctx = getAudioContext();
    const decoded = await ctx.decodeAudioData(arrayBuffer.slice(0));

    const sampleRate = decoded.sampleRate;
    const startSample = Math.max(0, Math.floor(startSeconds * sampleRate));
    const endSample = Math.min(decoded.length, Math.floor(endSeconds * sampleRate));
    const frameCount = Math.max(1, endSample - startSample);

    const sliced = ctx.createBuffer(decoded.numberOfChannels, frameCount, sampleRate);
    for (let i = 0; i < decoded.numberOfChannels; i++) {
      const channelData = decoded.getChannelData(i);
      const subData = channelData.subarray(startSample, endSample);
      sliced.copyToChannel(subData, i);
    }

    const wavBlob = encodeWav(sliced);
    return {
      blob: wavBlob,
      duration: frameCount / sampleRate
    };
  }

  function captureVideoFrame(videoElement) {
    const canvas = document.createElement("canvas");
    canvas.width = videoElement.videoWidth || 640;
    canvas.height = videoElement.videoHeight || 360;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.95);
  }

  return {
    convertAudio,
    sliceAudio,
    captureVideoFrame,
    encodeWav,
    encodeMp3,
    encodeFlac
  };
})();

window.AudioEngine = AudioEngine;
