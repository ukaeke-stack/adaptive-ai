package com.adaptiveai.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import kotlin.math.max

class RobotOverlayService : Service() {
    private lateinit var wm: WindowManager
    private lateinit var robot: WebView
    private lateinit var robotParams: WindowManager.LayoutParams
    private var panel: LinearLayout? = null
    private var panelParams: WindowManager.LayoutParams? = null
    private var responseText: TextView? = null
    private var responseScroll: ScrollView? = null
    private lateinit var speechBridge: AndroidSpeechBridge
    private val handler = Handler(Looper.getMainLooper())
    private var x = 0
    private var y = 0
    private var direction = 1
    private var verticalDirection = 1

    private val step = object : Runnable {
        override fun run() {
            if (::robot.isInitialized && ::robotParams.isInitialized) {
                val dm = resources.displayMetrics
                val screenWidth = dm.widthPixels
                val screenHeight = dm.heightPixels
                x += direction * 4
                y += verticalDirection * 2
                if (x <= 0) { x = 0; direction = 1 }
                if (x >= max(0, screenWidth - robotParams.width)) {
                    x = max(0, screenWidth - robotParams.width)
                    direction = -1
                }
                val minY = dp(48)
                val maxY = max(minY, screenHeight - robotParams.height - dp(72))
                if (y <= minY) { y = minY; verticalDirection = 1 }
                if (y >= maxY) { y = maxY; verticalDirection = -1 }
                robotParams.x = x
                robotParams.y = y
                try { wm.updateViewLayout(robot, robotParams) } catch (_: Exception) {}
            }
            handler.postDelayed(this, 42)
        }
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(91, notification())
        wm = getSystemService(WINDOW_SERVICE) as WindowManager

        speechBridge = AndroidSpeechBridge(this)
        speechBridge.overlayTextListener = { showResponse(it) }
        speechBridge.overlayTextProgressListener = { progress ->
            responseScroll?.post {
                val scroll = responseScroll ?: return@post
                if (scroll.childCount > 0) {
                    val range = (scroll.getChildAt(0).height - scroll.height).coerceAtLeast(0)
                    scroll.scrollTo(0, (range * progress).toInt())
                }
            }
        }
        speechBridge.overlayListeningListener = {
            panel?.visibility = View.GONE
        }

        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE
        robot = WebView(this).apply {
            setBackgroundColor(Color.TRANSPARENT)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.allowContentAccess = true
            settings.allowFileAccess = false
            CookieManager.getInstance().setAcceptCookie(true)
            addJavascriptInterface(speechBridge, "AdaptiveNative")
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    view?.evaluateJavascript(
                        "((window.NorahReady || Promise.resolve()).then(function(){document.body.classList.add('overlay-mode');}))",
                        null
                    )
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onPermissionRequest(request: PermissionRequest) {
                    handler.post {
                        val hasMic = !request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE) ||
                            checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
                        val hasCamera = !request.resources.contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE) ||
                            checkSelfPermission(android.Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
                        if (hasMic && hasCamera) request.grant(request.resources) else request.deny()
                    }
                }
            }
        }
        val robotWidth = dp(116)
        val robotHeight = dp(190)
        robotParams = WindowManager.LayoutParams(
            robotWidth, robotHeight, type,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 0
            y = resources.displayMetrics.heightPixels / 3
        }
        x = robotParams.x
        y = robotParams.y
        try {
            wm.addView(robot, robotParams)
            robot.loadUrl("https://adaptive-ai-huve.onrender.com/app/?overlay=1")
        } catch (e: Exception) {
            Toast.makeText(this, "Could not start Norah's floating robot. Check display-over-other-apps permission.", Toast.LENGTH_LONG).show()
        }
        handler.post(step)
    }

    private fun showResponse(text: String) {
        if (text.isBlank()) return
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE
        if (panel == null) {
            val scroll = ScrollView(this).apply {
                isFillViewport = true
                setBackgroundColor(Color.rgb(7, 17, 31))
            }
            val reply = TextView(this).apply {
                textSize = 14f
                setTextColor(Color.rgb(237, 245, 255))
                setPadding(dp(12), dp(8), dp(12), dp(8))
                setLineSpacing(1f, 1.08f)
            }
            scroll.addView(reply, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT
            ))
            val root = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundColor(Color.rgb(7, 17, 31))
                addView(scroll, LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, dp(88)
                ))
            }
            responseText = reply
            responseScroll = scroll
            panel = root
            val dm = resources.displayMetrics
            val width = minOf((dm.widthPixels * 0.86f).toInt(), dp(320))
            panelParams = WindowManager.LayoutParams(
                width, dp(88), type,
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.TRANSLUCENT
            ).apply {
                gravity = Gravity.TOP or Gravity.START
                x = robotParams.x.coerceIn(0, (dm.widthPixels - width).coerceAtLeast(0))
                y = (robotParams.y + robotParams.height + dp(4))
                    .coerceIn(dp(12), (dm.heightPixels - dp(88)).coerceAtLeast(dp(12)))
            }
            try { wm.addView(root, panelParams) } catch (_: Exception) {
                panel = null
                panelParams = null
                responseText = null
                responseScroll = null
                return
            }
        }
        responseText?.text = text
        panel?.visibility = View.VISIBLE
        val p = panelParams
        if (p != null) {
            val dm = resources.displayMetrics
            val width = p.width
            p.x = robotParams.x.coerceIn(0, (dm.widthPixels - width).coerceAtLeast(0))
            val below = robotParams.y + robotParams.height + dp(4)
            p.y = (if (below + dp(88) < dm.heightPixels) below else robotParams.y - dp(88))
                .coerceIn(dp(12), (dm.heightPixels - dp(88)).coerceAtLeast(dp(12)))
            try { panel?.let { wm.updateViewLayout(it, p) } } catch (_: Exception) {}
        }
        responseScroll?.post { responseScroll?.smoothScrollTo(0, responseText?.bottom ?: 0) }
    }

    private fun hidePanel() {
        panel?.let { try { wm.removeView(it) } catch (_: Exception) {} }
        panel = null
        panelParams = null
        responseText = null
        responseScroll = null
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        handler.removeCallbacks(step)
        hidePanel()
        if (::robot.isInitialized) {
            try { robot.stopLoading(); robot.removeJavascriptInterface("AdaptiveNative"); robot.destroy(); wm.removeView(robot) } catch (_: Exception) {}
        }
        if (::speechBridge.isInitialized) speechBridge.close()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(
                "adaptive_robot", "Adaptive AI floating robot", NotificationManager.IMPORTANCE_LOW
            ))
        }
    }

    private fun notification(): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return if (Build.VERSION.SDK_INT >= 26)
            Notification.Builder(this, "adaptive_robot")
                .setContentTitle("Norah's floating robot is active")
                .setContentText("Tap the Norah robot to speak. The reply appears beside it.")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentIntent(open).setOngoing(true).build()
        else Notification.Builder(this)
            .setContentTitle("Norah's floating robot is active")
            .setSmallIcon(android.R.drawable.ic_dialog_info).setContentIntent(open).build()
    }
}
