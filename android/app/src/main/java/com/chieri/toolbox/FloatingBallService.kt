package com.chieri.toolbox

import android.animation.ValueAnimator
import android.app.Service
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.view.animation.DecelerateInterpolator
import android.widget.Toast
import kotlin.math.abs

class FloatingBallService : Service() {

    private var windowManager: WindowManager? = null
    private var floatingView: View? = null
    private var params: WindowManager.LayoutParams? = null
    private var snapAnimator: ValueAnimator? = null

    companion object {
        var isRunning = false
        const val ACTION_STOP = "com.chieri.toolbox.ACTION_STOP"
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        showFloatingWindow()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    private fun showFloatingWindow() {
        try {
            windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
            val inflater = LayoutInflater.from(this)
            floatingView = inflater.inflate(R.layout.layout_floating_ball, null)

            val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            }

            val displayMetrics = resources.displayMetrics
            val margin = (16 * displayMetrics.density).toInt()
            val ballSize = (56 * displayMetrics.density).toInt()
            val defaultX = displayMetrics.widthPixels - ballSize - margin
            val defaultY = (displayMetrics.heightPixels * 0.35f).toInt()

            params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                layoutType,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                        WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT
            ).apply {
                gravity = Gravity.TOP or Gravity.START
                x = defaultX
                y = defaultY
            }

            val touchSlop = ViewConfiguration.get(this).scaledTouchSlop

            floatingView?.setOnTouchListener(object : View.OnTouchListener {
                private var startParamX = 0
                private var startParamY = 0
                private var initialTouchX = 0f
                private var initialTouchY = 0f
                private var touchStartTime = 0L

                override fun onTouch(v: View?, event: MotionEvent?): Boolean {
                    event ?: return false
                    when (event.action) {
                        MotionEvent.ACTION_DOWN -> {
                            snapAnimator?.cancel()
                            startParamX = params?.x ?: 0
                            startParamY = params?.y ?: 0
                            initialTouchX = event.rawX
                            initialTouchY = event.rawY
                            touchStartTime = System.currentTimeMillis()
                            return true
                        }
                        MotionEvent.ACTION_MOVE -> {
                            val metrics = resources.displayMetrics
                            val screenWidth = metrics.widthPixels
                            val screenHeight = metrics.heightPixels
                            val size = (56 * metrics.density).toInt()
                            val topMargin = (48 * metrics.density).toInt()
                            val bottomMargin = (48 * metrics.density).toInt()

                            val dx = (event.rawX - initialTouchX).toInt()
                            val dy = (event.rawY - initialTouchY).toInt()
                            params?.x = (startParamX + dx).coerceIn(0, screenWidth - size)
                            val maxY = (screenHeight - size - bottomMargin).coerceAtLeast(topMargin)
                            params?.y = (startParamY + dy).coerceIn(topMargin, maxY)
                            try {
                                windowManager?.updateViewLayout(floatingView, params)
                            } catch (_: Exception) {}
                            return true
                        }
                        MotionEvent.ACTION_UP -> {
                            val clickDuration = System.currentTimeMillis() - touchStartTime
                            val dx = abs(event.rawX - initialTouchX)
                            val dy = abs(event.rawY - initialTouchY)
                            if (clickDuration < 300 && dx < touchSlop && dy < touchSlop) {
                                onBallClicked()
                            } else {
                                snapToEdge()
                            }
                            return true
                        }
                    }
                    return false
                }
            })

            windowManager?.addView(floatingView, params)
        } catch (e: Exception) {
            e.printStackTrace()
            stopSelf()
        }
    }

    private fun snapToEdge() {
        val displayMetrics = resources.displayMetrics
        val screenWidth = displayMetrics.widthPixels
        val screenHeight = displayMetrics.heightPixels
        val ballSize = (56 * displayMetrics.density).toInt()
        val margin = (16 * displayMetrics.density).toInt()
        val topMargin = (48 * displayMetrics.density).toInt()
        val bottomMargin = (48 * displayMetrics.density).toInt()

        val startX = params?.x ?: margin
        val startY = params?.y ?: (screenHeight * 0.35f).toInt()

        val isCloserToLeft = startX + (ballSize / 2) < screenWidth / 2
        val targetX = if (isCloserToLeft) margin else (screenWidth - ballSize - margin)
        val maxTargetY = (screenHeight - ballSize - bottomMargin).coerceAtLeast(topMargin)
        val targetY = startY.coerceIn(topMargin, maxTargetY)

        snapAnimator?.cancel()
        snapAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 260
            interpolator = DecelerateInterpolator(1.5f)
            addUpdateListener { animator ->
                val fraction = animator.animatedFraction
                params?.x = (startX + (targetX - startX) * fraction).toInt()
                params?.y = (startY + (targetY - startY) * fraction).toInt()
                try {
                    windowManager?.updateViewLayout(floatingView, params)
                } catch (_: Exception) {}
            }
            start()
        }
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        floatingView?.post {
            snapToEdge()
        }
    }

    private fun onBallClicked() {
        Toast.makeText(this, "千绘莉工具箱 快捷唤醒", Toast.LENGTH_SHORT).show()
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("EXTRA_ACTION", "WAKE_AND_OPEN_SIDEBAR")
        }
        startActivity(intent)
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        snapAnimator?.cancel()
        floatingView?.let {
            try {
                windowManager?.removeView(it)
            } catch (_: Exception) {}
        }
    }
}
