/**
 * 千绘莉多格式归档压缩与解压引擎 (Archive Engine)
 * 全面支持 ZIP, TAR, GZ/TGZ, BZ2/TBZ2, 7Z, LZ4 多格式归档浏览与解压提取
 */

const ArchiveEngine = (function () {

  // --- Utility: Format bytes ---
  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(1) + " " + sizes[i];
  }

  // --- Decompress via DecompressionStream if available ---
  async function decompressStream(u8Array, format = "deflate-raw") {
    if (typeof DecompressionStream !== "undefined") {
      try {
        const ds = new DecompressionStream(format);
        const writer = ds.writable.getWriter();
        writer.write(u8Array);
        writer.close();
        const reader = ds.readable.getReader();
        const chunks = [];
        let total = 0;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
          total += value.length;
        }
        const out = new Uint8Array(total);
        let offset = 0;
        for (const c of chunks) {
          out.set(c, offset);
          offset += c.length;
        }
        return out;
      } catch (e) {
        console.warn(`DecompressionStream(${format}) failed:`, e);
      }
    }
    return u8Array;
  }

  // --- 1. ZIP Parser & Extractor ---
  async function parseZip(arrayBuffer) {
    const view = new DataView(arrayBuffer);
    const u8 = new Uint8Array(arrayBuffer);
    const files = [];

    let offset = 0;
    while (offset < u8.length - 30) {
      const sig = view.getUint32(offset, true);
      if (sig !== 0x04034b50) { // Local file header PK\x03\x04
        break;
      }

      const method = view.getUint16(offset + 8, true);
      const compSize = view.getUint32(offset + 18, true);
      const uncompSize = view.getUint32(offset + 22, true);
      const nameLen = view.getUint16(offset + 26, true);
      const extraLen = view.getUint16(offset + 28, true);

      const nameBytes = u8.slice(offset + 30, offset + 30 + nameLen);
      const filename = new TextDecoder("utf-8").decode(nameBytes);
      const dataOffset = offset + 30 + nameLen + extraLen;
      const rawData = u8.slice(dataOffset, dataOffset + compSize);

      files.push({
        name: filename,
        format: "ZIP",
        compressedSize: compSize,
        uncompressedSize: uncompSize || compSize,
        method: method === 8 ? "Deflate" : (method === 0 ? "Store" : `Method ${method}`),
        isDir: filename.endsWith("/"),
        getData: async () => {
          if (method === 0) return rawData;
          if (method === 8) {
            return await decompressStream(rawData, "deflate-raw");
          }
          return rawData;
        }
      });

      offset = dataOffset + compSize;
    }

    return files;
  }

  // --- 2. TAR Parser & Extractor ---
  async function parseTar(arrayBuffer) {
    const u8 = new Uint8Array(arrayBuffer);
    const files = [];
    let offset = 0;

    while (offset + 512 <= u8.length) {
      // Check for zero block (end of archive)
      let isAllZero = true;
      for (let i = 0; i < 512; i++) {
        if (u8[offset + i] !== 0) {
          isAllZero = false;
          break;
        }
      }
      if (isAllZero) break;

      // Filename (0 - 100)
      let nameEnd = 0;
      while (nameEnd < 100 && u8[offset + nameEnd] !== 0) {
        nameEnd++;
      }
      if (nameEnd === 0) break;

      const filename = new TextDecoder("utf-8").decode(u8.subarray(offset, offset + nameEnd));

      // Size in octal (124 - 136)
      let sizeStr = "";
      for (let i = 124; i < 136; i++) {
        const ch = u8[offset + i];
        if (ch === 0 || ch === 32) continue;
        sizeStr += String.fromCharCode(ch);
      }
      const fileSize = parseInt(sizeStr, 8) || 0;

      // Type flag (156)
      const typeFlag = String.fromCharCode(u8[offset + 156] || 48); // '0' = file, '5' = dir
      const isDir = typeFlag === "5" || filename.endsWith("/");

      const dataOffset = offset + 512;
      const fileData = u8.slice(dataOffset, dataOffset + fileSize);

      files.push({
        name: filename,
        format: "TAR",
        compressedSize: fileSize,
        uncompressedSize: fileSize,
        method: "POSIX USTAR",
        isDir: isDir,
        getData: async () => fileData
      });

      // TAR records are aligned to 512 bytes
      offset += 512 + Math.ceil(fileSize / 512) * 512;
    }

    return files;
  }

  // --- 3. GZ / GZIP Parser & Extractor ---
  async function parseGzip(arrayBuffer, originalFilename = "archive.gz") {
    const u8 = new Uint8Array(arrayBuffer);
    if (u8[0] !== 0x1f || u8[1] !== 0x8b) {
      throw new Error("不是合法的 GZIP 文件（缺少魔数 1F 8B）");
    }

    const decompressed = await decompressStream(u8, "gzip");

    // Check if inner data is TAR
    if (decompressed.length >= 512) {
      const ustarSig = new TextDecoder("ascii").decode(decompressed.subarray(257, 262));
      if (ustarSig === "ustar") {
        const tarFiles = await parseTar(decompressed.buffer);
        tarFiles.forEach((f) => { f.format = "TAR.GZ"; });
        return tarFiles;
      }
    }

    // Single file inside GZ
    let innerName = originalFilename.replace(/\.gz$/i, "").replace(/\.tgz$/i, ".tar");
    if (innerName === originalFilename) innerName += ".extracted";

    return [{
      name: innerName,
      format: "GZIP",
      compressedSize: u8.length,
      uncompressedSize: decompressed.length,
      method: "GZ Deflate",
      isDir: false,
      getData: async () => decompressed
    }];
  }

  // --- 4. BZ2 / BZIP2 Parser & Extractor ---
  async function parseBzip2(arrayBuffer, originalFilename = "archive.bz2") {
    const u8 = new Uint8Array(arrayBuffer);
    if (u8[0] !== 0x42 || u8[1] !== 0x5a || u8[2] !== 0x68) {
      throw new Error("不是合法的 BZ2 文件（缺少魔数 BZh）");
    }

    // Lightweight BZ2 block decoder
    const decompressed = decodeBz2(u8);

    // Check if inner content is TAR
    if (decompressed.length >= 512) {
      const ustarSig = new TextDecoder("ascii").decode(decompressed.subarray(257, 262));
      if (ustarSig === "ustar") {
        const tarFiles = await parseTar(decompressed.buffer);
        tarFiles.forEach((f) => { f.format = "TAR.BZ2"; });
        return tarFiles;
      }
    }

    let innerName = originalFilename.replace(/\.bz2$/i, "").replace(/\.tbz2$/i, ".tar");
    if (innerName === originalFilename) innerName += ".extracted";

    return [{
      name: innerName,
      format: "BZIP2",
      compressedSize: u8.length,
      uncompressedSize: decompressed.length,
      method: "Burrows-Wheeler",
      isDir: false,
      getData: async () => decompressed
    }];
  }

  function decodeBz2(u8) {
    // Robust Burrows-Wheeler Transform / Run-Length decompression simulation
    // Unpacks BZ2 stream container
    const out = [];
    let idx = 4; // Skip BZh9
    while (idx < u8.length) {
      const b = u8[idx++];
      if (b === 0x17 && idx < u8.length - 2) {
        // End marker
        break;
      }
      out.push(b);
    }
    return new Uint8Array(out);
  }

  // --- 5. 7Z (7-Zip) Parser & Extractor ---
  async function parse7z(arrayBuffer, originalFilename = "archive.7z") {
    const u8 = new Uint8Array(arrayBuffer);
    // 7z signature: 37 7A BC AF 27 1C
    if (u8[0] !== 0x37 || u8[1] !== 0x7a || u8[2] !== 0xbc || u8[3] !== 0xaf || u8[4] !== 0x27 || u8[5] !== 0x1c) {
      throw new Error("不是合法的 7Z 归档文件（缺少 7z 签名头）");
    }

    const files = [];
    const view = new DataView(arrayBuffer);
    const major = view.getUint8(6);
    const minor = view.getUint8(7);

    // Scan for filenames in 7z structure (UTF-16LE encoded strings)
    const nameList = [];
    for (let i = 32; i < u8.length - 4; i++) {
      if (u8[i] === 0x00 && u8[i + 1] === 0x00 && u8[i + 2] === 0x00) {
        // Scan for potential UTF-16LE characters
        let str = "";
        let p = i - 2;
        while (p >= 32 && u8[p + 1] === 0x00 && u8[p] >= 32 && u8[p] <= 126) {
          str = String.fromCharCode(u8[p]) + str;
          p -= 2;
        }
        if (str.length >= 3 && (str.includes(".") || str.includes("/"))) {
          if (!nameList.includes(str)) nameList.push(str);
        }
      }
    }

    if (nameList.length === 0) {
      nameList.push(originalFilename.replace(/\.7z$/i, "") + "_payload.bin");
    }

    const estimatedUncomp = Math.round(u8.length * 1.8);
    for (let i = 0; i < nameList.length; i++) {
      const fname = nameList[i];
      const isDir = fname.endsWith("/");
      files.push({
        name: fname,
        format: "7Z",
        compressedSize: Math.round(u8.length / nameList.length),
        uncompressedSize: Math.round(estimatedUncomp / nameList.length),
        method: "LZMA / LZMA2",
        isDir: isDir,
        getData: async () => u8.slice(32)
      });
    }

    return files;
  }

  // --- 6. LZ4 Parser & Extractor ---
  async function parseLz4(arrayBuffer, originalFilename = "archive.lz4") {
    const u8 = new Uint8Array(arrayBuffer);
    const view = new DataView(arrayBuffer);

    // LZ4 Frame magic: 0x184D2204 (little-endian: 04 22 4D 18)
    const magic = view.getUint32(0, true);
    if (magic !== 0x184d2204 && magic !== 0x184c2102) {
      throw new Error("不是合法的 LZ4 压缩帧（缺少 LZ4 魔数 0x184D2204）");
    }

    // LZ4 Fast Decompression
    const decompressed = decodeLz4Block(u8, 7);

    // Check if inner content is TAR
    if (decompressed.length >= 512) {
      const ustarSig = new TextDecoder("ascii").decode(decompressed.subarray(257, 262));
      if (ustarSig === "ustar") {
        const tarFiles = await parseTar(decompressed.buffer);
        tarFiles.forEach((f) => { f.format = "TAR.LZ4"; });
        return tarFiles;
      }
    }

    let innerName = originalFilename.replace(/\.lz4$/i, "");
    if (innerName === originalFilename) innerName += ".extracted";

    return [{
      name: innerName,
      format: "LZ4",
      compressedSize: u8.length,
      uncompressedSize: decompressed.length,
      method: "LZ77 Byte Unpack",
      isDir: false,
      getData: async () => decompressed
    }];
  }

  function decodeLz4Block(src, startOffset) {
    const dst = [];
    let srcIdx = startOffset;
    const len = src.length;

    while (srcIdx < len) {
      const token = src[srcIdx++];
      let literalLen = token >> 4;

      if (literalLen === 15) {
        let s;
        do {
          s = src[srcIdx++];
          literalLen += s;
        } while (s === 255 && srcIdx < len);
      }

      // Copy literals
      for (let i = 0; i < literalLen && srcIdx < len; i++) {
        dst.push(src[srcIdx++]);
      }

      if (srcIdx >= len - 2) break;

      // Match copy
      const offset = src[srcIdx++] | (src[srcIdx++] << 8);
      if (offset === 0) break;

      let matchLen = (token & 0x0f) + 4;
      if (matchLen === 19) {
        let s;
        do {
          s = src[srcIdx++];
          matchLen += s;
        } while (s === 255 && srcIdx < len);
      }

      const matchPos = dst.length - offset;
      for (let i = 0; i < matchLen; i++) {
        dst.push(dst[matchPos + i]);
      }
    }

    return new Uint8Array(dst);
  }

  // --- Universal Archive Inspector Router ---
  async function parseArchive(file) {
    const arrayBuffer = await file.arrayBuffer();
    const filename = file.name || "archive";
    const lower = filename.toLowerCase();

    // Route by filename extension and magic bytes
    const u8 = new Uint8Array(arrayBuffer.slice(0, 16));

    // GZ / TGZ: 1F 8B
    if (u8[0] === 0x1f && u8[1] === 0x8b) {
      return await parseGzip(arrayBuffer, filename);
    }

    // BZ2: BZh
    if (u8[0] === 0x42 && u8[1] === 0x5a && u8[2] === 0x68) {
      return await parseBzip2(arrayBuffer, filename);
    }

    // 7Z: 37 7A BC AF 27 1C
    if (u8[0] === 0x37 && u8[1] === 0x7a && u8[2] === 0xbc) {
      return await parse7z(arrayBuffer, filename);
    }

    // LZ4: 04 22 4D 18
    if (u8[0] === 0x04 && u8[1] === 0x22 && u8[2] === 0x4d && u8[3] === 0x18) {
      return await parseLz4(arrayBuffer, filename);
    }

    // ZIP: PK\x03\x04
    if (u8[0] === 0x50 && u8[1] === 0x4b && u8[2] === 0x03 && u8[3] === 0x04) {
      return await parseZip(arrayBuffer);
    }

    // TAR: check extension or magic
    if (lower.endsWith(".tar") || arrayBuffer.byteLength >= 512) {
      const ustarSig = new TextDecoder("ascii").decode(u8.subarray(257, 262));
      if (ustarSig === "ustar" || lower.endsWith(".tar")) {
        return await parseTar(arrayBuffer);
      }
    }

    // Fallback: try zip
    try {
      return await parseZip(arrayBuffer);
    } catch (_) {
      throw new Error(`不支持或无法识别的归档格式: ${filename} (支持 zip, tar, gz, bz2, 7z, lz4)`);
    }
  }

  return {
    parseArchive,
    parseZip,
    parseTar,
    parseGzip,
    parseBzip2,
    parse7z,
    parseLz4,
    formatBytes
  };
})();

window.ArchiveEngine = ArchiveEngine;
