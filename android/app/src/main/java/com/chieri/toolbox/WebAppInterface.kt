package com.chieri.toolbox

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.provider.Settings
import android.util.Base64
import android.webkit.JavascriptInterface
import android.widget.Toast
import android.media.MediaScannerConnection
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.MediaMuxer
import androidx.core.view.WindowCompat
import org.apache.commons.compress.archivers.sevenz.SevenZFile
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.archivers.zip.ZipArchiveInputStream
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream
import org.apache.commons.compress.compressors.gzip.GzipCompressorInputStream
import org.apache.commons.compress.compressors.lz4.FramedLZ4CompressorInputStream
import org.apache.commons.compress.compressors.xz.XZCompressorInputStream
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.zip.GZIPInputStream

class WebAppInterface(private val activity: MainActivity) {

    @JavascriptInterface
    fun showToast(message: String) {
        activity.runOnUiThread {
            Toast.makeText(activity, message, Toast.LENGTH_SHORT).show()
        }
    }

    @JavascriptInterface
    fun vibrate(durationMs: Long) {
        val ms = if (durationMs in 1..2000) durationMs else 50L
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vibratorManager = activity.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                vibratorManager?.defaultVibrator?.vibrate(
                    VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE)
                )
            } else {
                @Suppress("DEPRECATION")
                val vibrator = activity.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    vibrator?.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
                } else {
                    @Suppress("DEPRECATION")
                    vibrator?.vibrate(ms)
                }
            }
        } catch (_: Exception) {}
    }

    @JavascriptInterface
    fun canDrawOverlays(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(activity)
        } else {
            true
        }
    }

    @JavascriptInterface
    fun requestOverlayPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(activity)) {
            val intent = Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:${activity.packageName}")
            )
            activity.startActivity(intent)
        }
    }

    @JavascriptInterface
    fun toggleSystemFloatingBall(enable: Boolean): Boolean {
        if (enable) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(activity)) {
                requestOverlayPermission()
                showToast("请在系统设置中允许显示在其他应用上层")
                return false
            }
            val intent = Intent(activity, FloatingBallService::class.java)
            activity.startService(intent)
            showToast("全局悬浮窗已开启")
            return true
        } else {
            val intent = Intent(activity, FloatingBallService::class.java).apply {
                action = FloatingBallService.ACTION_STOP
            }
            activity.startService(intent)
            showToast("全局悬浮窗已关闭")
            return true
        }
    }

    @JavascriptInterface
    fun isSystemFloatingBallRunning(): Boolean {
        return FloatingBallService.isRunning
    }

    @JavascriptInterface
    fun setStatusBarTheme(isDark: Boolean) {
        activity.runOnUiThread {
            try {
                val insetsController = WindowCompat.getInsetsController(activity.window, activity.window.decorView)
                insetsController.isAppearanceLightStatusBars = !isDark
                insetsController.isAppearanceLightNavigationBars = !isDark
            } catch (_: Exception) {}
        }
    }

    @JavascriptInterface
    fun md5(input: String): String {
        return try {
            val md = MessageDigest.getInstance("MD5")
            val digest = md.digest(input.toByteArray(StandardCharsets.UTF_8))
            digest.joinToString("") { "%02x".format(it) }
        } catch (e: Exception) {
            ""
        }
    }

    @JavascriptInterface
    fun httpRequest(method: String, urlString: String, headersJson: String?, bodyStr: String?): String {
        val result = JSONObject()
        try {
            val url = URL(urlString)
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = method.uppercase()
            conn.connectTimeout = 15000
            conn.readTimeout = 25000
            conn.instanceFollowRedirects = true

            // Set default headers
            conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            conn.setRequestProperty("Accept-Encoding", "gzip, deflate")

            if (!headersJson.isNullOrBlank()) {
                val hObj = JSONObject(headersJson)
                val keys = hObj.keys()
                while (keys.hasNext()) {
                    val key = keys.next()
                    conn.setRequestProperty(key, hObj.optString(key))
                }
            }

            if (method.equals("POST", ignoreCase = true) || method.equals("PUT", ignoreCase = true)) {
                conn.doOutput = true
                if (!bodyStr.isNullOrEmpty()) {
                    conn.outputStream.use { os ->
                        os.write(bodyStr.toByteArray(StandardCharsets.UTF_8))
                        os.flush()
                    }
                }
            }

            val status = conn.responseCode
            result.put("status", status)
            result.put("ok", status in 200..299)

            val encoding = conn.contentEncoding
            val rawInputStream = try {
                if (status in 200..299) conn.inputStream else (conn.errorStream ?: conn.inputStream)
            } catch (_: Exception) {
                conn.errorStream ?: ByteArrayInputStream(ByteArray(0))
            }

            val inputStream = if ("gzip".equals(encoding, ignoreCase = true)) {
                try { GZIPInputStream(rawInputStream) } catch (_: Exception) { rawInputStream }
            } else {
                rawInputStream
            }

            val reader = BufferedReader(InputStreamReader(inputStream, StandardCharsets.UTF_8))
            val sb = StringBuilder()
            var line: String?
            while (reader.readLine().also { line = it } != null) {
                sb.append(line).append("\n")
            }
            reader.close()

            result.put("data", sb.toString())

            val headersObj = JSONObject()
            for ((key, value) in conn.headerFields) {
                if (key != null && value.isNotEmpty()) {
                    headersObj.put(key, value.joinToString(", "))
                }
            }
            result.put("headers", headersObj)

        } catch (e: Exception) {
            result.put("ok", false)
            result.put("status", -1)
            result.put("error", e.message ?: e.toString())
        }
        return result.toString()
    }

    @JavascriptInterface
    fun downloadMediaStream(urlString: String, filename: String, headersJson: String?): String {
        val downloadDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        if (!downloadDir.exists()) downloadDir.mkdirs()

        val sanitized = filename.replace(Regex("[\\\\/:*?\"<>|]"), "_")
        val targetFile = File(downloadDir, sanitized)

        Thread {
            try {
                val url = URL(urlString)
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "GET"
                conn.connectTimeout = 15000
                conn.readTimeout = 30000
                conn.instanceFollowRedirects = true
                conn.setRequestProperty("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                conn.setRequestProperty("Referer", "https://www.bilibili.com")

                if (!headersJson.isNullOrBlank()) {
                    val hObj = JSONObject(headersJson)
                    val keys = hObj.keys()
                    while (keys.hasNext()) {
                        val key = keys.next()
                        conn.setRequestProperty(key, hObj.optString(key))
                    }
                }

                val totalLength = conn.contentLength.toLong()
                var downloaded = 0L

                conn.inputStream.use { input ->
                    FileOutputStream(targetFile).use { output ->
                        val buffer = ByteArray(64 * 1024)
                        var read: Int
                        var lastReportTime = System.currentTimeMillis()
                        while (input.read(buffer).also { read = it } != -1) {
                            output.write(buffer, 0, read)
                            downloaded += read
                            val now = System.currentTimeMillis()
                            if (now - lastReportTime >= 400) {
                                lastReportTime = now
                                val progress = if (totalLength > 0) ((downloaded * 100) / totalLength).toInt() else 50
                                val speedStr = String.format("%.1f MB", downloaded / 1048576.0)
                                activity.evaluateJavascript("window.onMediaDownloadProgress && window.onMediaDownloadProgress('${sanitized}', ${progress}, '${speedStr}', 'downloading');")
                            }
                        }
                    }
                }

                MediaScannerConnection.scanFile(activity, arrayOf(targetFile.absolutePath), null, null)
                showToast("已成功下载至: Download/$sanitized")
                activity.evaluateJavascript("window.onMediaDownloadProgress && window.onMediaDownloadProgress('${sanitized}', 100, '已完成', 'completed');")
            } catch (e: Exception) {
                showToast("下载失败: ${e.message}")
                activity.evaluateJavascript("window.onMediaDownloadProgress && window.onMediaDownloadProgress('${sanitized}', 0, '下载失败', 'failed');")
            }
        }.start()

        return JSONObject().apply {
            put("ok", true)
            put("targetPath", targetFile.absolutePath)
        }.toString()
    }

    @JavascriptInterface
    fun listArchiveEntriesNative(base64Data: String, filename: String): String {
        return try {
            val clean = if (base64Data.contains(",")) base64Data.substringAfter(",") else base64Data
            val bytes = Base64.decode(clean, Base64.DEFAULT)
            val lowerName = filename.lowercase()
            val entriesArray = JSONArray()

            if (lowerName.endsWith(".7z")) {
                val tempFile = File(activity.cacheDir, "temp_${System.currentTimeMillis()}.7z")
                try {
                    FileOutputStream(tempFile).use { it.write(bytes) }
                    val sevenZ = SevenZFile(tempFile)
                    var entry = sevenZ.nextEntry
                    while (entry != null) {
                        val obj = JSONObject().apply {
                            put("name", entry.name)
                            put("size", entry.size)
                            put("compressedSize", entry.size)
                            put("isDir", entry.isDirectory)
                            put("method", "7-Zip LZMA")
                        }
                        entriesArray.put(obj)
                        entry = sevenZ.nextEntry
                    }
                    sevenZ.close()
                } finally {
                    tempFile.delete()
                }
            } else {
                var inStream: InputStream = ByteArrayInputStream(bytes)
                var isTar = false
                var method = "Store"

                if (lowerName.endsWith(".tar.gz") || lowerName.endsWith(".tgz")) {
                    inStream = GzipCompressorInputStream(inStream)
                    isTar = true
                    method = "GZ Deflate"
                } else if (lowerName.endsWith(".gz")) {
                    inStream = GzipCompressorInputStream(inStream)
                    method = "GZ Deflate"
                } else if (lowerName.endsWith(".tar.bz2") || lowerName.endsWith(".tbz2") || lowerName.endsWith(".tbz")) {
                    inStream = BZip2CompressorInputStream(inStream)
                    isTar = true
                    method = "BZip2"
                } else if (lowerName.endsWith(".bz2")) {
                    inStream = BZip2CompressorInputStream(inStream)
                    method = "BZip2"
                } else if (lowerName.endsWith(".tar.lz4")) {
                    inStream = FramedLZ4CompressorInputStream(inStream)
                    isTar = true
                    method = "LZ4 Frame"
                } else if (lowerName.endsWith(".lz4")) {
                    inStream = FramedLZ4CompressorInputStream(inStream)
                    method = "LZ4 Frame"
                } else if (lowerName.endsWith(".tar.xz") || lowerName.endsWith(".txz")) {
                    inStream = XZCompressorInputStream(inStream)
                    isTar = true
                    method = "XZ LZMA2"
                } else if (lowerName.endsWith(".tar")) {
                    isTar = true
                    method = "POSIX TAR"
                } else if (lowerName.endsWith(".zip")) {
                    method = "ZIP Deflate"
                }

                if (lowerName.endsWith(".zip")) {
                    val zip = ZipArchiveInputStream(inStream)
                    var ze = zip.nextZipEntry
                    while (ze != null) {
                        val obj = JSONObject().apply {
                            put("name", ze.name)
                            put("size", ze.size)
                            put("compressedSize", ze.compressedSize)
                            put("isDir", ze.isDirectory)
                            put("method", method)
                        }
                        entriesArray.put(obj)
                        ze = zip.nextZipEntry
                    }
                    zip.close()
                } else if (isTar) {
                    val tar = TarArchiveInputStream(inStream)
                    var te = tar.nextTarEntry
                    while (te != null) {
                        val obj = JSONObject().apply {
                            put("name", te.name)
                            put("size", te.size)
                            put("compressedSize", te.size)
                            put("isDir", te.isDirectory)
                            put("method", method)
                        }
                        entriesArray.put(obj)
                        te = tar.nextTarEntry
                    }
                    tar.close()
                } else {
                    val baseName = filename.replace(Regex("\\.(gz|bz2|lz4|xz)$", RegexOption.IGNORE_CASE), "")
                    val innerBytes = ByteArrayOutputStream()
                    inStream.copyTo(innerBytes)
                    val decompressed = innerBytes.toByteArray()
                    val obj = JSONObject().apply {
                        put("name", if (baseName == filename) "$filename.extracted" else baseName)
                        put("size", decompressed.size.toLong())
                        put("compressedSize", bytes.size.toLong())
                        put("isDir", false)
                        put("method", method)
                    }
                    entriesArray.put(obj)
                }
            }
            JSONObject().apply {
                put("ok", true)
                put("entries", entriesArray)
            }.toString()
        } catch (e: Exception) {
            JSONObject().apply {
                put("ok", false)
                put("error", e.message ?: e.toString())
            }.toString()
        }
    }

    @JavascriptInterface
    fun extractArchiveEntryNative(base64Data: String, filename: String, entryName: String): String {
        return try {
            val clean = if (base64Data.contains(",")) base64Data.substringAfter(",") else base64Data
            val bytes = Base64.decode(clean, Base64.DEFAULT)
            val lowerName = filename.lowercase()
            val out = ByteArrayOutputStream()

            if (lowerName.endsWith(".7z")) {
                val tempFile = File(activity.cacheDir, "temp_${System.currentTimeMillis()}.7z")
                try {
                    FileOutputStream(tempFile).use { it.write(bytes) }
                    val sevenZ = SevenZFile(tempFile)
                    var entry = sevenZ.nextEntry
                    var found = false
                    while (entry != null) {
                        if (entry.name == entryName && !entry.isDirectory) {
                            val buffer = ByteArray(8192)
                            var bytesRead: Int
                            while (sevenZ.read(buffer, 0, buffer.size).also { bytesRead = it } != -1) {
                                out.write(buffer, 0, bytesRead)
                            }
                            found = true
                            break
                        }
                        entry = sevenZ.nextEntry
                    }
                    sevenZ.close()
                    if (!found) throw IllegalArgumentException("文件未找到: $entryName")
                } finally {
                    tempFile.delete()
                }
            } else {
                var inStream: InputStream = ByteArrayInputStream(bytes)
                var isTar = false

                if (lowerName.endsWith(".tar.gz") || lowerName.endsWith(".tgz")) {
                    inStream = GzipCompressorInputStream(inStream)
                    isTar = true
                } else if (lowerName.endsWith(".gz")) {
                    inStream = GzipCompressorInputStream(inStream)
                } else if (lowerName.endsWith(".tar.bz2") || lowerName.endsWith(".tbz2") || lowerName.endsWith(".tbz")) {
                    inStream = BZip2CompressorInputStream(inStream)
                    isTar = true
                } else if (lowerName.endsWith(".bz2")) {
                    inStream = BZip2CompressorInputStream(inStream)
                } else if (lowerName.endsWith(".tar.lz4")) {
                    inStream = FramedLZ4CompressorInputStream(inStream)
                    isTar = true
                } else if (lowerName.endsWith(".lz4")) {
                    inStream = FramedLZ4CompressorInputStream(inStream)
                } else if (lowerName.endsWith(".tar.xz") || lowerName.endsWith(".txz")) {
                    inStream = XZCompressorInputStream(inStream)
                    isTar = true
                } else if (lowerName.endsWith(".tar")) {
                    isTar = true
                }

                if (lowerName.endsWith(".zip")) {
                    val zip = ZipArchiveInputStream(inStream)
                    var ze = zip.nextZipEntry
                    var found = false
                    while (ze != null) {
                        if (ze.name == entryName && !ze.isDirectory) {
                            zip.copyTo(out)
                            found = true
                            break
                        }
                        ze = zip.nextZipEntry
                    }
                    zip.close()
                    if (!found) throw IllegalArgumentException("文件未找到: $entryName")
                } else if (isTar) {
                    val tar = TarArchiveInputStream(inStream)
                    var te = tar.nextTarEntry
                    var found = false
                    while (te != null) {
                        if (te.name == entryName && !te.isDirectory) {
                            tar.copyTo(out)
                            found = true
                            break
                        }
                        te = tar.nextTarEntry
                    }
                    tar.close()
                    if (!found) throw IllegalArgumentException("文件未找到: $entryName")
                } else {
                    inStream.copyTo(out)
                }
            }

            val b64 = Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
            JSONObject().apply {
                put("ok", true)
                put("data", b64)
            }.toString()
        } catch (e: Exception) {
            JSONObject().apply {
                put("ok", false)
                put("error", e.message ?: e.toString())
            }.toString()
        }
    }

    @JavascriptInterface
    fun extractAllArchiveNative(base64Data: String, filename: String): String {
        return try {
            val clean = if (base64Data.contains(",")) base64Data.substringAfter(",") else base64Data
            val bytes = Base64.decode(clean, Base64.DEFAULT)
            val lowerName = filename.lowercase()
            val downloadDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            val safeBase = File(filename).name.replace(Regex("[\\\\/:*?\"<>|]"), "_")
            val folderName = safeBase.replace(Regex("\\.(tar\\.(gz|bz2|lz4|xz)|tgz|tbz2|txz|zip|tar|gz|bz2|lz4|7z)$", RegexOption.IGNORE_CASE), "") + "_extracted"
            val targetDir = File(downloadDir, folderName)
            if (!targetDir.exists()) targetDir.mkdirs()
            val targetCanonical = targetDir.canonicalPath

            var extractedCount = 0
            val scannedPaths = mutableListOf<String>()

            if (lowerName.endsWith(".7z")) {
                val tempFile = File(activity.cacheDir, "temp_${System.currentTimeMillis()}.7z")
                try {
                    FileOutputStream(tempFile).use { it.write(bytes) }
                    val sevenZ = SevenZFile(tempFile)
                    var entry = sevenZ.nextEntry
                    while (entry != null) {
                        val entryPath = entry.name.replace("\\", "/")
                        val outFile = File(targetDir, entryPath)
                        val outCanonical = outFile.canonicalPath
                        if (!outCanonical.startsWith(targetCanonical + File.separator) && outCanonical != targetCanonical) {
                            entry = sevenZ.nextEntry
                            continue
                        }
                        if (entry.isDirectory) {
                            outFile.mkdirs()
                        } else {
                            outFile.parentFile?.mkdirs()
                            FileOutputStream(outFile).use { fos ->
                                val buffer = ByteArray(8192)
                                var r: Int
                                while (sevenZ.read(buffer, 0, buffer.size).also { r = it } != -1) {
                                    fos.write(buffer, 0, r)
                                }
                            }
                            extractedCount++
                            scannedPaths.add(outFile.absolutePath)
                        }
                        entry = sevenZ.nextEntry
                    }
                    sevenZ.close()
                } finally {
                    tempFile.delete()
                }
            } else {
                var inStream: InputStream = ByteArrayInputStream(bytes)
                var isTar = false

                if (lowerName.endsWith(".tar.gz") || lowerName.endsWith(".tgz")) {
                    inStream = GzipCompressorInputStream(inStream)
                    isTar = true
                } else if (lowerName.endsWith(".gz")) {
                    inStream = GzipCompressorInputStream(inStream)
                } else if (lowerName.endsWith(".tar.bz2") || lowerName.endsWith(".tbz2") || lowerName.endsWith(".tbz")) {
                    inStream = BZip2CompressorInputStream(inStream)
                    isTar = true
                } else if (lowerName.endsWith(".bz2")) {
                    inStream = BZip2CompressorInputStream(inStream)
                } else if (lowerName.endsWith(".tar.lz4")) {
                    inStream = FramedLZ4CompressorInputStream(inStream)
                    isTar = true
                } else if (lowerName.endsWith(".lz4")) {
                    inStream = FramedLZ4CompressorInputStream(inStream)
                } else if (lowerName.endsWith(".tar.xz") || lowerName.endsWith(".txz")) {
                    inStream = XZCompressorInputStream(inStream)
                    isTar = true
                } else if (lowerName.endsWith(".tar")) {
                    isTar = true
                }

                if (lowerName.endsWith(".zip")) {
                    val zip = ZipArchiveInputStream(inStream)
                    var ze = zip.nextZipEntry
                    while (ze != null) {
                        val zePath = ze.name.replace("\\", "/")
                        val outFile = File(targetDir, zePath)
                        val outCanonical = outFile.canonicalPath
                        if (!outCanonical.startsWith(targetCanonical + File.separator) && outCanonical != targetCanonical) {
                            ze = zip.nextZipEntry
                            continue
                        }
                        if (ze.isDirectory) {
                            outFile.mkdirs()
                        } else {
                            outFile.parentFile?.mkdirs()
                            FileOutputStream(outFile).use { zip.copyTo(it) }
                            extractedCount++
                            scannedPaths.add(outFile.absolutePath)
                        }
                        ze = zip.nextZipEntry
                    }
                    zip.close()
                } else if (isTar) {
                    val tar = TarArchiveInputStream(inStream)
                    var te = tar.nextTarEntry
                    while (te != null) {
                        val tePath = te.name.replace("\\", "/")
                        val outFile = File(targetDir, tePath)
                        val outCanonical = outFile.canonicalPath
                        if (!outCanonical.startsWith(targetCanonical + File.separator) && outCanonical != targetCanonical) {
                            te = tar.nextTarEntry
                            continue
                        }
                        if (te.isDirectory) {
                            outFile.mkdirs()
                        } else {
                            outFile.parentFile?.mkdirs()
                            FileOutputStream(outFile).use { tar.copyTo(it) }
                            extractedCount++
                            scannedPaths.add(outFile.absolutePath)
                        }
                        te = tar.nextTarEntry
                    }
                    tar.close()
                } else {
                    val singleBase = File(folderName.removeSuffix("_extracted")).name.replace(Regex("[\\\\/:*?\"<>|]"), "_")
                    val singleOut = File(targetDir, singleBase)
                    val outCanonical = singleOut.canonicalPath
                    if (outCanonical.startsWith(targetCanonical + File.separator) || outCanonical == targetCanonical) {
                        FileOutputStream(singleOut).use { inStream.copyTo(it) }
                        extractedCount++
                        scannedPaths.add(singleOut.absolutePath)
                    }
                }
            }

            if (scannedPaths.isNotEmpty()) {
                MediaScannerConnection.scanFile(activity, scannedPaths.toTypedArray(), null, null)
            }
            showToast("成功解压 $extractedCount 个文件至 Download/$folderName")

            JSONObject().apply {
                put("ok", true)
                put("count", extractedCount)
                put("outputDir", targetDir.absolutePath)
            }.toString()
        } catch (e: Exception) {
            showToast("解压失败: ${e.message}")
            JSONObject().apply {
                put("ok", false)
                put("error", e.message ?: e.toString())
            }.toString()
        }
    }

    @JavascriptInterface
    fun encodePcmToM4aNative(pcmBase64: String, sampleRate: Int, channels: Int, bitrateKbps: Int): String {
        return try {
            val clean = if (pcmBase64.contains(",")) pcmBase64.substringAfter(",") else pcmBase64
            val pcmBytes = Base64.decode(clean, Base64.DEFAULT)

            val outputFile = File(activity.cacheDir, "temp_encoded_${System.currentTimeMillis()}.m4a")
            val muxer = MediaMuxer(outputFile.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)

            val aacFormat = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC, sampleRate, channels).apply {
                setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
                setInteger(MediaFormat.KEY_BIT_RATE, bitrateKbps * 1000)
                setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16384)
            }

            val encoder = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC)
            encoder.configure(aacFormat, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            encoder.start()

            val bufferInfo = MediaCodec.BufferInfo()
            var audioTrackIndex = -1
            var muxerStarted = false

            var pcmOffset = 0
            val pcmLength = pcmBytes.size
            var inputEos = false
            var outputEos = false
            val timeoutUs = 10000L
            var totalSamplesSent = 0L
            val bytesPerFrame = Math.max(1, channels * 2)

            try {
                while (!outputEos) {
                    if (!inputEos) {
                        val inputBufIdx = encoder.dequeueInputBuffer(timeoutUs)
                        if (inputBufIdx >= 0) {
                            val inputBuf = encoder.getInputBuffer(inputBufIdx)
                            if (inputBuf != null) {
                                inputBuf.clear()
                                val bytesToRead = Math.min(inputBuf.remaining(), pcmLength - pcmOffset)
                                if (bytesToRead > 0) {
                                    val ptsUs = (totalSamplesSent * 1_000_000L) / sampleRate
                                    inputBuf.put(pcmBytes, pcmOffset, bytesToRead)
                                    pcmOffset += bytesToRead
                                    totalSamplesSent += (bytesToRead / bytesPerFrame)
                                    encoder.queueInputBuffer(inputBufIdx, 0, bytesToRead, ptsUs, 0)
                                } else {
                                    inputEos = true
                                    val ptsUs = (totalSamplesSent * 1_000_000L) / sampleRate
                                    encoder.queueInputBuffer(inputBufIdx, 0, 0, ptsUs, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                }
                            }
                        }
                    }

                    val outputBufIdx = encoder.dequeueOutputBuffer(bufferInfo, timeoutUs)
                    if (outputBufIdx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                        if (!muxerStarted) {
                            audioTrackIndex = muxer.addTrack(encoder.outputFormat)
                            muxer.start()
                            muxerStarted = true
                        }
                    } else if (outputBufIdx >= 0) {
                        val outBuf = encoder.getOutputBuffer(outputBufIdx)
                        if (outBuf != null) {
                            if ((bufferInfo.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) {
                                bufferInfo.size = 0
                            }
                            if (bufferInfo.size > 0 && muxerStarted) {
                                outBuf.position(bufferInfo.offset)
                                outBuf.limit(bufferInfo.offset + bufferInfo.size)
                                muxer.writeSampleData(audioTrackIndex, outBuf, bufferInfo)
                            }
                        }
                        encoder.releaseOutputBuffer(outputBufIdx, false)
                        if ((bufferInfo.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) {
                            outputEos = true
                        }
                    }
                }
            } finally {
                try { encoder.stop() } catch (_: Exception) {}
                try { encoder.release() } catch (_: Exception) {}
                if (muxerStarted) {
                    try { muxer.stop() } catch (_: Exception) {}
                    try { muxer.release() } catch (_: Exception) {}
                }
            }

            val encodedBytes = outputFile.readBytes()
            outputFile.delete()
            val b64 = Base64.encodeToString(encodedBytes, Base64.NO_WRAP)
            JSONObject().apply {
                put("ok", true)
                put("data", b64)
            }.toString()
        } catch (e: Exception) {
            JSONObject().apply {
                put("ok", false)
                put("error", e.message ?: e.toString())
            }.toString()
        }
    }

    @JavascriptInterface
    fun saveBase64File(filename: String, base64Data: String, mimeType: String): String {
        return try {
            val cleanBase64 = if (base64Data.contains(",")) {
                base64Data.substringAfter(",")
            } else {
                base64Data
            }
            val bytes = Base64.decode(cleanBase64, Base64.DEFAULT)
            val downloadDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            if (!downloadDir.exists()) downloadDir.mkdirs()

            val sanitized = filename.replace(Regex("[\\\\/:*?\"<>|]"), "_")
            val targetFile = File(downloadDir, sanitized)
            FileOutputStream(targetFile).use { it.write(bytes) }

            // Notify MediaScanner
            try {
                MediaScannerConnection.scanFile(
                    activity,
                    arrayOf(targetFile.absolutePath),
                    if (mimeType.isNotBlank()) arrayOf(mimeType) else null,
                    null
                )
            } catch (_: Exception) {}

            showToast("已成功保存至下载目录: $sanitized")
            targetFile.absolutePath
        } catch (e: Exception) {
            e.printStackTrace()
            showToast("保存文件失败: ${e.message}")
            ""
        }
    }

    @JavascriptInterface
    fun shareText(text: String) {
        val sendIntent = Intent().apply {
            action = Intent.ACTION_SEND
            putExtra(Intent.EXTRA_TEXT, text)
            type = "text/plain"
        }
        val shareIntent = Intent.createChooser(sendIntent, "千绘莉工具箱 分享")
        activity.startActivity(shareIntent)
    }

    @JavascriptInterface
    fun discoverLocalCloudPC(): String {
        val results = JSONArray()
        try {
            val socket = java.net.DatagramSocket()
            socket.broadcast = true
            socket.soTimeout = 1200
            val reqData = "CHIERI_DISCOVER_REQ".toByteArray(StandardCharsets.UTF_8)
            val packet = java.net.DatagramPacket(
                reqData, reqData.size,
                java.net.InetAddress.getByName("255.255.255.255"), 23333
            )
            socket.send(packet)

            val buf = ByteArray(1024)
            val respPacket = java.net.DatagramPacket(buf, buf.size)
            val startTime = System.currentTimeMillis()
            while (System.currentTimeMillis() - startTime < 1200) {
                try {
                    socket.receive(respPacket)
                    val respStr = String(respPacket.data, 0, respPacket.length, StandardCharsets.UTF_8).trim()
                    if (respStr.startsWith("CHIERI_DISCOVER_RESP:")) {
                        val parts = respStr.split(":")
                        val port = if (parts.size >= 2) parts[1].toIntOrNull() ?: 8765 else 8765
                        val host = if (parts.size >= 3) parts[2] else "Desktop"
                        val ip = respPacket.address.hostAddress ?: ""
                        val item = JSONObject()
                        item.put("ip", ip)
                        item.put("port", port)
                        item.put("hostname", host)
                        item.put("url", "http://$ip:$port")
                        results.put(item)
                    }
                } catch (_: java.net.SocketTimeoutException) {
                    break
                }
            }
            socket.close()
        } catch (e: Exception) {
            e.printStackTrace()
        }
        return results.toString()
    }

    @JavascriptInterface
    fun uploadImageForCloudUpscale(
        serverUrl: String,
        imageBase64: String,
        model: String,
        scale: Int,
        denoise: String
    ): String {
        val result = JSONObject()
        try {
            val cleanBase64 = if (imageBase64.contains(",")) imageBase64.substringAfter(",") else imageBase64
            val imageBytes = Base64.decode(cleanBase64, Base64.DEFAULT)

            val url = URL("${serverUrl.trimEnd('/')}/api/upscale")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.connectTimeout = 15000
            conn.readTimeout = 180000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "image/png")
            conn.setRequestProperty("X-Model", model)
            conn.setRequestProperty("X-Scale", scale.toString())
            conn.setRequestProperty("X-Denoise", denoise)
            conn.setFixedLengthStreamingMode(imageBytes.size)

            conn.outputStream.use { os ->
                os.write(imageBytes)
                os.flush()
            }

            val statusCode = conn.responseCode
            if (statusCode == 200) {
                val outBytes = conn.inputStream.use { it.readBytes() }
                val picturesDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES)
                val targetDir = File(picturesDir, "ChieriToolbox")
                if (!targetDir.exists()) targetDir.mkdirs()

                val filename = "upscale_${scale}x_${System.currentTimeMillis()}.png"
                val outFile = File(targetDir, filename)
                outFile.outputStream().use { it.write(outBytes) }

                try {
                    MediaScannerConnection.scanFile(
                        activity,
                        arrayOf(outFile.absolutePath),
                        arrayOf("image/png"),
                        null
                    )
                } catch (_: Exception) {}

                val base64Preview = Base64.encodeToString(outBytes, Base64.NO_WRAP)
                result.put("ok", true)
                result.put("path", outFile.absolutePath)
                result.put("filename", filename)
                result.put("previewBase64", "data:image/png;base64,$base64Preview")
                result.put("costTime", conn.getHeaderField("X-Process-Time") ?: "")
                showToast("云端超分成功！已保存至相册: $filename")
            } else {
                val errStr = conn.errorStream?.bufferedReader()?.use { it.readText() } ?: "HTTP $statusCode"
                result.put("ok", false)
                result.put("error", "电脑端处理失败: $errStr")
                showToast("电脑端超分失败: $statusCode")
            }
        } catch (e: Exception) {
            e.printStackTrace()
            result.put("ok", false)
            result.put("error", e.message ?: e.toString())
            showToast("连接电脑宿主异常: ${e.message}")
        }
        return result.toString()
    }

    @JavascriptInterface
    fun sendDropFileToPC(serverUrl: String, base64Data: String, filename: String): String {
        val result = JSONObject()
        try {
            val cleanBase64 = if (base64Data.contains(",")) base64Data.substringAfter(",") else base64Data
            val dataBytes = Base64.decode(cleanBase64, Base64.DEFAULT)

            val encName = java.net.URLEncoder.encode(filename, "UTF-8")
            val url = URL("${serverUrl.trimEnd('/')}/api/drop/send")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.connectTimeout = 10000
            conn.readTimeout = 60000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/octet-stream")
            conn.setRequestProperty("X-Filename", encName)
            conn.setFixedLengthStreamingMode(dataBytes.size)

            conn.outputStream.use { os ->
                os.write(dataBytes)
                os.flush()
            }

            val statusCode = conn.responseCode
            val respBody = (if (statusCode in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader()?.use { it.readText() } ?: ""

            if (statusCode == 200) {
                result.put("ok", true)
                result.put("message", "已成功通过 Chieri Drop 投送至电脑！")
                showToast("文件已投送至电脑！")
            } else {
                result.put("ok", false)
                result.put("error", respBody)
                showToast("投送失败: HTTP $statusCode")
            }
        } catch (e: Exception) {
            result.put("ok", false)
            result.put("error", e.message ?: e.toString())
            showToast("投送异常: ${e.message}")
        }
        return result.toString()
    }

    @JavascriptInterface
    fun syncClipboardWithPC(serverUrl: String, text: String, mode: String): String {
        val result = JSONObject()
        try {
            val url = URL("${serverUrl.trimEnd('/')}/api/clipboard")
            val conn = url.openConnection() as HttpURLConnection
            if (mode == "send") {
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                val postJson = JSONObject()
                postJson.put("text", text)
                val body = postJson.toString().toByteArray(StandardCharsets.UTF_8)
                conn.outputStream.use { it.write(body) }
                val code = conn.responseCode
                result.put("ok", code == 200)
                if (code == 200) showToast("已投送手机剪贴板至电脑！")
            } else {
                conn.requestMethod = "GET"
                val code = conn.responseCode
                if (code == 200) {
                    val resp = conn.inputStream.bufferedReader().use { it.readText() }
                    val j = JSONObject(resp)
                    val pcText = j.optString("text", "")
                    result.put("ok", true)
                    result.put("text", pcText)
                    showToast("已获取电脑剪贴板内容！")
                } else {
                    result.put("ok", false)
                }
            }
        } catch (e: Exception) {
            result.put("ok", false)
            result.put("error", e.message ?: e.toString())
        }
        return result.toString()
    }

    @JavascriptInterface
    fun getAppVersion(): String {
        return "2.6.0-Mobile"
    }
}
