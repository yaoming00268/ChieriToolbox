package com.chieri.toolbox

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.chieri.toolbox.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    lateinit var binding: ActivityMainBinding
    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    private var pendingAction: String? = null
    private var isPageLoaded = false
    private var backPressedTime = 0L

    fun evaluateJavascript(script: String) {
        runOnUiThread {
            binding.webView.evaluateJavascript(script, null)
        }
    }

    private val filePickerLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (filePathCallback != null) {
            val results: Array<Uri>? = if (result.resultCode == RESULT_OK) {
                result.data?.let { intent ->
                    intent.data?.let { arrayOf(it) } ?: intent.clipData?.let { clipData ->
                        Array(clipData.itemCount) { i -> clipData.getItemAt(i).uri }
                    }
                }
            } else {
                null
            }
            filePathCallback?.onReceiveValue(results)
            filePathCallback = null
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupWindowInsets()
        setupWebView()
        setupBackPressHandler()

        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIntent(it) }
    }

    private fun handleIntent(intent: Intent) {
        val action = intent.getStringExtra("EXTRA_ACTION") ?: return
        if (isPageLoaded) {
            executeAction(action)
        } else {
            pendingAction = action
        }
    }

    private fun executeAction(action: String) {
        if (action == "TOGGLE_SIDEBAR") {
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("window.toggleSidebar && window.toggleSidebar();", null)
            }, 100)
        } else if (action == "WAKE_AND_OPEN_SIDEBAR") {
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("window.openSidebar && window.openSidebar();", null)
            }, 100)
        } else if (action.startsWith("NAVIGATE:")) {
            val toolId = action.substringAfter("NAVIGATE:")
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("window.navigateToTool && window.navigateToTool('$toolId');", null)
            }, 100)
        } else if (action == "TEST_AUDIO_CONVERT") {
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("window.__loadTestAudioAndConvert && window.__loadTestAudioAndConvert('mp3');", null)
            }, 100)
        } else if (action == "TEST_AUDIO_CONVERT_M4A") {
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("window.__loadTestAudioAndConvert && window.__loadTestAudioAndConvert('m4a');", null)
            }, 100)
        } else if (action == "TEST_ARCHIVE_UNPACK") {
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("window.__loadTestArchive && window.__loadTestArchive();", null)
            }, 100)
        } else if (action == "TEST_TRANSLATOR") {
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("const chip = document.querySelector('.acg-chip'); if(chip) chip.click();", null)
            }, 100)
        } else if (action == "TEST_BILIBILI_VIP") {
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("const inp = document.getElementById('bili-sessdata-input'); if(inp) { inp.value = 'dummy_sessdata_test_key_12345'; } const b = document.getElementById('btn-verify-bili-vip'); if(b) b.click();", null)
            }, 100)
        } else if (action == "TOGGLE_THEME") {
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("const b = document.getElementById('btn-toggle-theme'); if (b) b.click();", null)
            }, 100)
        } else if (action == "TEST_TRANSLATOR_BAIDU") {
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript("const s = document.getElementById('trans-provider-select'); if(s) { s.value = 'baidu'; s.dispatchEvent(new Event('change')); } const inp = document.getElementById('trans-input'); if(inp) { inp.value = '你好世界'; } const b = document.getElementById('btn-do-trans'); if(b) b.click();", null)
            }, 100)
        } else if (action.startsWith("B64EVAL:")) {
            val b64 = action.substringAfter("B64EVAL:")
            try {
                val script = String(android.util.Base64.decode(b64, android.util.Base64.DEFAULT), java.nio.charset.StandardCharsets.UTF_8)
                binding.webView.postDelayed({
                    binding.webView.evaluateJavascript(script, null)
                }, 100)
            } catch (_: Exception) {}
        } else if (action.startsWith("EVAL:")) {
            val script = action.substringAfter("EVAL:")
            binding.webView.postDelayed({
                binding.webView.evaluateJavascript(script, null)
            }, 100)
        }
    }

    private fun setupWindowInsets() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val insetsController = WindowCompat.getInsetsController(window, window.decorView)
        insetsController.isAppearanceLightStatusBars = false
        insetsController.isAppearanceLightNavigationBars = false
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val webView = binding.webView
        val settings = webView.settings

        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.useWideViewPort = true
        settings.loadWithOverviewMode = true
        settings.databaseEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.cacheMode = WebSettings.LOAD_DEFAULT

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            WebView.setWebContentsDebuggingEnabled(true)
        }

        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null)
        webView.isVerticalScrollBarEnabled = false
        webView.isHorizontalScrollBarEnabled = false

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                isPageLoaded = true
                pendingAction?.let { act ->
                    executeAction(act)
                    pendingAction = null
                }
            }

            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                url ?: return false
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    try {
                        val browserIntent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                        startActivity(browserIntent)
                        return true
                    } catch (_: Exception) {}
                }
                return false
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(consoleMessage: android.webkit.ConsoleMessage?): Boolean {
                android.util.Log.d("WebConsole", "[${consoleMessage?.messageLevel()}] ${consoleMessage?.message()} (${consoleMessage?.sourceId()}:${consoleMessage?.lineNumber()})")
                return true
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                this@MainActivity.filePathCallback?.onReceiveValue(null)
                this@MainActivity.filePathCallback = filePathCallback

                val intent = fileChooserParams?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                    type = "*/*"
                    addCategory(Intent.CATEGORY_OPENABLE)
                }

                try {
                    filePickerLauncher.launch(intent)
                } catch (e: Exception) {
                    this@MainActivity.filePathCallback = null
                    return false
                }
                return true
            }
        }

        webView.addJavascriptInterface(WebAppInterface(this), "AndroidBridge")
        webView.loadUrl("file:///android_asset/web/index.html")
    }

    private fun setupBackPressHandler() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                binding.webView.evaluateJavascript("window.handleAndroidBackPressed && window.handleAndroidBackPressed();") { result ->
                    val handled = result?.replace("\"", "")?.toBoolean() ?: false
                    if (!handled) {
                        if (System.currentTimeMillis() - backPressedTime < 2000) {
                            finish()
                        } else {
                            backPressedTime = System.currentTimeMillis()
                            Toast.makeText(this@MainActivity, "再按一次返回键退出工具箱", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            }
        })
    }

    override fun onDestroy() {
        binding.webView.destroy()
        super.onDestroy()
    }
}
