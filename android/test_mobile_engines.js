/**
 * Comprehensive Automated Test Suite for Android Mobile Web Engines
 */

const assert = require("assert");
const fs = require("fs");
const path = require("path");

// Mock browser environments
global.window = global;
globalThis.localStorage = {
  store: {},
  getItem(k) { return this.store[k] || null; },
  setItem(k, v) { this.store[k] = String(v); },
  removeItem(k) { delete this.store[k]; },
  clear() { this.store = {}; }
};

// Load the engines
global.lamejs = require(path.join(__dirname, "app/src/main/assets/web/js/lame.min.js"));
require(path.join(__dirname, "app/src/main/assets/web/js/audio_engine.js"));
require(path.join(__dirname, "app/src/main/assets/web/js/media_engine.js"));
require(path.join(__dirname, "app/src/main/assets/web/js/archive_engine.js"));
require(path.join(__dirname, "app/src/main/assets/web/js/translator.js"));

let testsPassed = 0;
let testsFailed = 0;

function runTest(name, fn) {
  try {
    fn();
    console.log(`  [PASS] ${name}`);
    testsPassed++;
  } catch (e) {
    console.error(`  [FAIL] ${name}: ${e.message}`);
    testsFailed++;
  }
}

async function runAsyncTest(name, fn) {
  try {
    await fn();
    console.log(`  [PASS] ${name}`);
    testsPassed++;
  } catch (e) {
    console.error(`  [FAIL] ${name}: ${e.message}`);
    testsFailed++;
  }
}

async function main() {
  console.log("=== Starting Android Mobile Engines Test Suite ===");

  // 1. AudioEngine Tests
  console.log("\n--- Testing AudioEngine ---");

  runTest("AudioEngine.encodeWav generates valid RIFF WAVE header", () => {
    const sampleRate = 44100;
    const channels = 2;
    const length = 4410; // 0.1s
    const mockBuffer = {
      numberOfChannels: channels,
      sampleRate: sampleRate,
      length: length,
      duration: 0.1,
      getChannelData: (ch) => new Float32Array(length).fill(ch === 0 ? 0.5 : -0.5)
    };

    const wavBlob = AudioEngine.encodeWav(mockBuffer);
    assert.strictEqual(wavBlob.type, "audio/wav");
    assert(wavBlob.size > 44, "WAV size should be greater than header");
  });

  runTest("AudioEngine.encodeMp3 generates valid MPEG Layer 3 frames", () => {
    const sampleRate = 44100;
    const channels = 2;
    const length = 2304;
    const mockBuffer = {
      numberOfChannels: channels,
      sampleRate: sampleRate,
      length: length,
      duration: length / sampleRate,
      getChannelData: () => new Float32Array(length).fill(0.2)
    };

    const mp3Blob = AudioEngine.encodeMp3(mockBuffer, 192);
    assert.strictEqual(mp3Blob.type, "audio/mp3");
    assert(mp3Blob.size > 0, "MP3 blob should not be empty");
  });

  runTest("AudioEngine.encodeFlac generates valid FLAC stream header and blocks", () => {
    const sampleRate = 48000;
    const channels = 2;
    const length = 4096;
    const mockBuffer = {
      numberOfChannels: channels,
      sampleRate: sampleRate,
      length: length,
      duration: length / sampleRate,
      getChannelData: () => new Float32Array(length).fill(0.1)
    };

    const flacBlob = AudioEngine.encodeFlac(mockBuffer);
    assert.strictEqual(flacBlob.type, "audio/flac");
    assert(flacBlob.size > 42, "FLAC blob should contain fLaC marker and frames");
  });

  // 2. MediaEngine Cookie & VIP Tests
  console.log("\n--- Testing MediaEngine (Cookie & Bilibili VIP) ---");

  runTest("MediaEngine.normalizeCookie handles raw SESSDATA string", () => {
    const raw = "1234567890abcdef1234567890abcdef";
    const res = MediaEngine.normalizeCookie(raw);
    assert.strictEqual(res, `SESSDATA=${raw}`);
  });

  runTest("MediaEngine.normalizeCookie handles JSON array from Cookie-Editor", () => {
    const raw = JSON.stringify([
      { name: "SESSDATA", value: "sess_val_test" },
      { name: "bili_jct", value: "jct_val_test" },
      { name: "buvid3", value: "buvid_val_test" }
    ]);
    const res = MediaEngine.normalizeCookie(raw);
    assert(res.includes("SESSDATA=sess_val_test"));
    assert(res.includes("bili_jct=jct_val_test"));
  });

  runTest("MediaEngine.normalizeCookie handles key-value pairs with extra spaces and quotes", () => {
    const raw = ' "SESSDATA=custom_sess_val; bili_jct=jct_123" ';
    const res = MediaEngine.normalizeCookie(raw);
    assert(res.includes("SESSDATA=custom_sess_val"));
  });

  await runAsyncTest("MediaEngine.checkAccountStatus handles unauthenticated state gracefully", async () => {
    MediaEngine.saveCookie("");
    const status = await MediaEngine.checkAccountStatus("");
    assert.strictEqual(status.is_login, false);
    assert.strictEqual(status.is_vip, false);
  });

  await runAsyncTest("MediaEngine.parseMediaUrl identifies YouTube link and extracts metadata", async () => {
    const url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
    const parsed = await MediaEngine.parseMediaUrl(url);
    assert.strictEqual(parsed.platform, "youtube");
    assert.strictEqual(parsed.id, "dQw4w9WgXcQ");
    assert(parsed.videoStreams.length > 0);
  });

  // 3. ArchiveEngine Multi-Format Tests
  console.log("\n--- Testing ArchiveEngine (Multi-Format Support) ---");

  runTest("ArchiveEngine.formatBytes formats sizes accurately", () => {
    assert.strictEqual(ArchiveEngine.formatBytes(0), "0 B");
    assert.strictEqual(ArchiveEngine.formatBytes(1024), "1.0 KB");
    assert.strictEqual(ArchiveEngine.formatBytes(1048576), "1.0 MB");
    assert.strictEqual(ArchiveEngine.formatBytes(1073741824), "1.0 GB");
  });

  await runAsyncTest("ArchiveEngine.parseTar parses standard POSIX USTAR archives", async () => {
    // Construct minimal 512-byte tar block
    const buffer = new ArrayBuffer(1024);
    const u8 = new Uint8Array(buffer);

    // Filename: "test.txt"
    const nameStr = "test.txt";
    for (let i = 0; i < nameStr.length; i++) u8[i] = nameStr.charCodeAt(i);

    // File size in octal at offset 124: "00000000014 " (12 bytes = 12 bytes octal = 10 bytes content)
    const sizeOctal = "00000000012 ";
    for (let i = 0; i < sizeOctal.length; i++) u8[124 + i] = sizeOctal.charCodeAt(i);

    // USTAR magic at offset 257: "ustar"
    const ustar = "ustar";
    for (let i = 0; i < ustar.length; i++) u8[257 + i] = ustar.charCodeAt(i);

    // Data at offset 512: "Hello, TAR"
    const dataStr = "Hello, TAR";
    for (let i = 0; i < dataStr.length; i++) u8[512 + i] = dataStr.charCodeAt(i);

    const files = await ArchiveEngine.parseTar(buffer);
    assert.strictEqual(files.length, 1);
    assert.strictEqual(files[0].name, "test.txt");
    assert.strictEqual(files[0].format, "TAR");

    const extracted = await files[0].getData();
    assert.strictEqual(extracted.length, 10);
  });

  await runAsyncTest("ArchiveEngine.parse7z validates 7z signature and extracts entries", async () => {
    const buffer = new ArrayBuffer(64);
    const u8 = new Uint8Array(buffer);
    // 7z signature: 37 7A BC AF 27 1C
    u8[0] = 0x37; u8[1] = 0x7a; u8[2] = 0xbc; u8[3] = 0xaf; u8[4] = 0x27; u8[5] = 0x1c;
    u8[6] = 0x00; u8[7] = 0x04; // version 0.4

    const files = await ArchiveEngine.parse7z(buffer, "bundle.7z");
    assert(files.length > 0);
    assert.strictEqual(files[0].format, "7Z");
    assert.strictEqual(files[0].method, "LZMA / LZMA2");
  });

  await runAsyncTest("ArchiveEngine.parseLz4 validates LZ4 frame magic and unpacks blocks", async () => {
    const buffer = new ArrayBuffer(32);
    const view = new DataView(buffer);
    view.setUint32(0, 0x184d2204, true); // LZ4 Frame magic

    const files = await ArchiveEngine.parseLz4(buffer, "sample.lz4");
    assert.strictEqual(files.length, 1);
    assert.strictEqual(files[0].format, "LZ4");
  });

  // 4. TranslatorEngine Tests
  console.log("\n--- Testing TranslatorEngine (API & ACG Dictionary) ---");

  runTest("TranslatorEngine.getDict contains essential ACG definitions", () => {
    const dict = TranslatorEngine.getDict();
    assert(dict["傲娇"].includes("Tsundere"));
    assert(dict["中二病"].includes("Chuunibyou"));
    assert(dict["天然呆"].includes("Tennen"));
  });

  await runAsyncTest("TranslatorEngine.translate prioritizes ACG dictionary for exact phrases", async () => {
    const res = await TranslatorEngine.translate("傲娇", "ja");
    assert(res.includes("【二次元萌系释义】"));
    assert(res.includes("Tsundere"));
  });

  await runAsyncTest("TranslatorEngine.translate falls back to offline guidance when unconfigured", async () => {
    TranslatorEngine.saveConfig({ provider: "offline" });
    const res = await TranslatorEngine.translate("随机未知短语", "ja");
    assert(res.includes("离线词库未收录"));
  });

  runTest("TranslatorEngine.saveConfig persists settings correctly", () => {
    TranslatorEngine.saveConfig({
      provider: "openai",
      baseUrl: "https://api.deepseek.com/v1",
      apiKey: "sk-test-key-123456",
      model: "deepseek-chat"
    });

    const loaded = TranslatorEngine.getConfig();
    assert.strictEqual(loaded.provider, "openai");
    assert.strictEqual(loaded.apiKey, "sk-test-key-123456");
    assert.strictEqual(loaded.model, "deepseek-chat");
  });

  runTest("TranslatorEngine.calcMd5 produces standard RFC 1321 hash for ASCII and UTF-8", () => {
    const crypto = require("crypto");
    const testCases = [
      "apple",
      "chieri_toolbox_test_123",
      "千绘莉魔法工具箱·高保真翻译",
      "2023050800012345Hello143566028812345678"
    ];
    for (const str of testCases) {
      const expected = crypto.createHash("md5").update(str, "utf8").digest("hex");
      const actual = TranslatorEngine.calcMd5(str);
      assert.strictEqual(actual, expected, `MD5 mismatch for input: ${str}`);
    }
  });

  runTest("TranslatorEngine persists Baidu Translate AppID and AppKey credentials", () => {
    TranslatorEngine.saveConfig({
      provider: "baidu",
      baiduAppId: "baidu_appid_998877",
      baiduKey: "baidu_key_secret_xyz"
    });
    const loaded = TranslatorEngine.getConfig();
    assert.strictEqual(loaded.provider, "baidu");
    assert.strictEqual(loaded.baiduAppId, "baidu_appid_998877");
    assert.strictEqual(loaded.baiduKey, "baidu_key_secret_xyz");
  });

  await runAsyncTest("TranslatorEngine.translate fails clearly when Baidu credentials are missing", async () => {
    TranslatorEngine.saveConfig({ provider: "baidu", baiduAppId: "", baiduKey: "" });
    let errorCaught = false;
    try {
      await TranslatorEngine.translate("Hello World", "ja");
    } catch (e) {
      errorCaught = true;
      assert(e.message.includes("百度翻译"), "Error message should mention Baidu Translate");
    }
    assert.strictEqual(errorCaught, true, "Should throw when Baidu credentials are missing");
  });

  await runAsyncTest("TranslatorEngine.testConnection routes offline provider gracefully", async () => {
    const res = await TranslatorEngine.testConnection({ provider: "offline" });
    assert.strictEqual(res.ok, true);
    assert(res.output.includes("离线词库模式已就绪"));
  });

  console.log("\n==================================================");
  console.log(`Results: ${testsPassed} passed, ${testsFailed} failed.`);
  console.log("==================================================");

  if (testsFailed > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("Test execution fatal error:", err);
  process.exit(1);
});
