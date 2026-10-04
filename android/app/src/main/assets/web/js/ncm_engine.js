/**
 * 网易云音乐 NCM 格式解密核心引擎 (纯 JS 原生实现)
 * 包含纯前端 AES-128-ECB 解密、RC4 S-Box 变换、元数据及专辑封面提取
 */

const NCMEngine = (function () {
  // AES S-Box & Inverted S-Box tables
  const S_BOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16
  ];

  const INV_S_BOX = new Uint8Array(256);
  for (let i = 0; i < 256; i++) {
    INV_S_BOX[S_BOX[i]] = i;
  }

  const RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36];

  function keyExpansion(key) {
    const w = new Uint32Array(44);
    for (let i = 0; i < 4; i++) {
      w[i] = (key[4 * i] << 24) | (key[4 * i + 1] << 16) | (key[4 * i + 2] << 8) | key[4 * i + 3];
    }
    for (let i = 4; i < 44; i++) {
      let temp = w[i - 1];
      if (i % 4 === 0) {
        temp = ((temp << 8) | (temp >>> 24));
        temp = (S_BOX[(temp >>> 24) & 0xff] << 24) |
               (S_BOX[(temp >>> 16) & 0xff] << 16) |
               (S_BOX[(temp >>> 8) & 0xff] << 8) |
               S_BOX[temp & 0xff];
        temp ^= (RCON[(i / 4) - 1] << 24);
      }
      w[i] = w[i - 4] ^ temp;
    }
    return w;
  }

  function mul(a, b) {
    let p = 0;
    for (let i = 0; i < 8; i++) {
      if (b & 1) p ^= a;
      const hi = a & 0x80;
      a = (a << 1) & 0xff;
      if (hi) a ^= 0x1b;
      b >>>= 1;
    }
    return p;
  }

  function invMixColumns(s) {
    for (let c = 0; c < 4; c++) {
      const idx = c * 4;
      const a0 = s[idx], a1 = s[idx + 1], a2 = s[idx + 2], a3 = s[idx + 3];
      s[idx]     = mul(a0, 0x0e) ^ mul(a1, 0x0b) ^ mul(a2, 0x0d) ^ mul(a3, 0x09);
      s[idx + 1] = mul(a0, 0x09) ^ mul(a1, 0x0e) ^ mul(a2, 0x0b) ^ mul(a3, 0x0d);
      s[idx + 2] = mul(a0, 0x0d) ^ mul(a1, 0x09) ^ mul(a2, 0x0e) ^ mul(a3, 0x0b);
      s[idx + 3] = mul(a0, 0x0b) ^ mul(a1, 0x0d) ^ mul(a2, 0x09) ^ mul(a3, 0x0e);
    }
  }

  function decryptAesBlock(input, offset, w) {
    let s = new Uint8Array(16);
    for (let i = 0; i < 16; i++) s[i] = input[offset + i];

    // Round 10
    for (let i = 0; i < 4; i++) {
      const kw = w[40 + i];
      s[i * 4]     ^= (kw >>> 24) & 0xff;
      s[i * 4 + 1] ^= (kw >>> 16) & 0xff;
      s[i * 4 + 2] ^= (kw >>> 8)  & 0xff;
      s[i * 4 + 3] ^= kw & 0xff;
    }

    for (let round = 9; round >= 1; round--) {
      // InvShiftRows
      let t1 = s[13]; s[13] = s[9]; s[9] = s[5]; s[5] = s[1]; s[1] = t1;
      let t2 = s[2]; s[2] = s[10]; s[10] = t2;
      let t6 = s[6]; s[6] = s[14]; s[14] = t6;
      let t3 = s[3]; s[3] = s[7]; s[7] = s[11]; s[11] = s[15]; s[15] = t3;

      // InvSubBytes
      for (let i = 0; i < 16; i++) s[i] = INV_S_BOX[s[i]];

      // AddRoundKey
      for (let i = 0; i < 4; i++) {
        const kw = w[round * 4 + i];
        s[i * 4]     ^= (kw >>> 24) & 0xff;
        s[i * 4 + 1] ^= (kw >>> 16) & 0xff;
        s[i * 4 + 2] ^= (kw >>> 8)  & 0xff;
        s[i * 4 + 3] ^= kw & 0xff;
      }

      // InvMixColumns
      invMixColumns(s);
    }

    // InvShiftRows round 0
    let t1 = s[13]; s[13] = s[9]; s[9] = s[5]; s[5] = s[1]; s[1] = t1;
    let t2 = s[2]; s[2] = s[10]; s[10] = t2;
    let t6 = s[6]; s[6] = s[14]; s[14] = t6;
    let t3 = s[3]; s[3] = s[7]; s[7] = s[11]; s[11] = s[15]; s[15] = t3;

    for (let i = 0; i < 16; i++) s[i] = INV_S_BOX[s[i]];

    for (let i = 0; i < 4; i++) {
      const kw = w[i];
      s[i * 4]     ^= (kw >>> 24) & 0xff;
      s[i * 4 + 1] ^= (kw >>> 16) & 0xff;
      s[i * 4 + 2] ^= (kw >>> 8)  & 0xff;
      s[i * 4 + 3] ^= kw & 0xff;
    }

    return s;
  }

  function aesEcbDecrypt(data, key) {
    const w = keyExpansion(key);
    const decrypted = new Uint8Array(data.length);
    for (let i = 0; i < data.length; i += 16) {
      const block = decryptAesBlock(data, i, w);
      decrypted.set(block, i);
    }
    // PKCS7 unpad
    if (decrypted.length > 0) {
      const pad = decrypted[decrypted.length - 1];
      if (pad >= 1 && pad <= 16) {
        return decrypted.slice(0, decrypted.length - pad);
      }
    }
    return decrypted;
  }

  // Hex to byte helpers
  function hexToBytes(hex) {
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < bytes.length; i++) {
      bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    return bytes;
  }

  const CORE_KEY = hexToBytes("687a4852416d736f356b496e62617857");
  const META_KEY = hexToBytes("2331346c6a6b5f215c5d2630553c2728");

  function decryptNcmBuffer(arrayBuffer) {
    const view = new DataView(arrayBuffer);
    const u8 = new Uint8Array(arrayBuffer);

    // 1. Check Magic Header: CTENFDAM
    const magic = [0x43, 0x54, 0x45, 0x4e, 0x46, 0x44, 0x41, 0x4d];
    for (let i = 0; i < 8; i++) {
      if (u8[i] !== magic[i]) {
        throw new Error("非合法 NCM 文件格式（文件头校验失败）");
      }
    }

    let pos = 10; // Skip 8 header + 2 gap bytes

    // 2. RC4 Key
    const keyLen = view.getUint32(pos, true);
    pos += 4;
    const rawKey = new Uint8Array(keyLen);
    for (let i = 0; i < keyLen; i++) rawKey[i] = u8[pos + i] ^ 0x64;
    pos += keyLen;

    const decryptedKey = aesEcbDecrypt(rawKey, CORE_KEY);
    const keyPrefix = "neteasecloudmusic";
    const prefixBytes = new TextEncoder().encode(keyPrefix);
    let matchPrefix = true;
    for (let i = 0; i < prefixBytes.length; i++) {
      if (decryptedKey[i] !== prefixBytes[i]) {
        matchPrefix = false;
        break;
      }
    }
    if (!matchPrefix) throw new Error("NCM 密钥解密验证头异常");
    const rc4Key = decryptedKey.slice(17);

    // 3. Metadata
    const metaLen = view.getUint32(pos, true);
    pos += 4;
    let meta = { musicName: "未知曲目", artist: [["未知歌手"]], format: "mp3" };
    if (metaLen > 0) {
      const rawMeta = new Uint8Array(metaLen);
      for (let i = 0; i < metaLen; i++) rawMeta[i] = u8[pos + i] ^ 0x63;
      pos += metaLen;

      try {
        const metaStr = new TextDecoder().decode(rawMeta);
        const metaB64 = metaStr.replace("163 key(Don't modify):", "");
        const metaEncrypted = Uint8Array.from(atob(metaB64), c => c.charCodeAt(0));
        const metaDecrypted = aesEcbDecrypt(metaEncrypted, META_KEY);
        const jsonStr = new TextDecoder().decode(metaDecrypted).replace("music:", "");
        meta = JSON.parse(jsonStr);
      } catch (e) {
        console.warn("解析元数据略过", e);
      }
    }

    // 4. Gap & Cover image
    pos += 5; // 5 bytes CRC/gap
    let coverBlob = null;
    let imageLen = 0;
    if (pos + 4 <= u8.length) {
      imageLen = view.getUint32(pos, true);
      pos += 4;
      if (imageLen > 0 && pos + imageLen <= u8.length) {
        const coverBytes = u8.slice(pos, pos + imageLen);
        coverBlob = new Blob([coverBytes], { type: "image/jpeg" });
        pos += imageLen;
      }
    }

    // 5. RC4 S-Box setup
    const box = new Uint8Array(256);
    for (let i = 0; i < 256; i++) box[i] = i;
    let c = 0;
    const kLen = rc4Key.length;
    for (let i = 0; i < 256; i++) {
      c = (box[i] + c + rc4Key[i % kLen]) & 0xff;
      const tmp = box[i];
      box[i] = box[c];
      box[c] = tmp;
    }

    const sbox = new Uint8Array(256);
    for (let i = 0; i < 256; i++) {
      sbox[i] = box[(box[i] + box[(box[i] + i) & 0xff]) & 0xff];
    }

    // 6. Decrypt Audio Payload
    const audioData = u8.slice(pos);
    const audioLen = audioData.length;
    for (let i = 0; i < audioLen; i++) {
      const maskIdx = (i + 1) & 0xff;
      audioData[i] ^= sbox[maskIdx];
    }

    // Determine format from magic bytes
    let ext = (meta && meta.format) ? meta.format.toLowerCase() : "mp3";
    let mimeType = "audio/mpeg";
    if (audioData.length >= 4) {
      if (audioData[0] === 0x66 && audioData[1] === 0x4c && audioData[2] === 0x61 && audioData[3] === 0x43) {
        ext = "flac";
        mimeType = "audio/flac";
      } else if (audioData[0] === 0x49 && audioData[1] === 0x44 && audioData[2] === 0x33) {
        ext = "mp3";
        mimeType = "audio/mpeg";
      }
    }

    const artistName = (meta.artist && meta.artist.length > 0)
      ? meta.artist.map(a => Array.isArray(a) ? a[0] : a.name || a).join(", ")
      : "网易云音乐";

    return {
      title: meta.musicName || "已解密音乐",
      artist: artistName,
      album: meta.album || "网易云音乐",
      format: ext,
      mimeType: mimeType,
      coverBlob: coverBlob,
      audioBlob: new Blob([audioData], { type: mimeType })
    };
  }

  return {
    decrypt: decryptNcmBuffer
  };
})();

window.NCMEngine = NCMEngine;
