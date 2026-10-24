package com.adaptiveai.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import kotlin.math.max

class RobotOverlayService : Service() {
    private lateinit var wm: WindowManager
    private var robot: WalkingRobotView? = null
    private var robotParams: WindowManager.LayoutParams? = null
    private var panel: LinearLayout? = null
    private var panelParams: WindowManager.LayoutParams? = null
    private var speechBridge: AndroidSpeechBridge? = null
    private var responseView: TextView? = null
    private val handler = Handler(Looper.getMainLooper())
    private var x = 0
    private var y = 0
    private var direction = 1
    private var verticalDirection = 1
    private var touchRawX = 0f
    private var touchRawY = 0f
    private var touchStartX = 0
    private var touchStartY = 0
    private var dragged = false
    private var pendingListenOnOpen = false

    private val step = object : Runnable {
        override fun run() {
            val p = robotParams
            val v = robot
            if (p != null && v != null) {
                // Keep the robot roaming while the floating chat panel is open.
                if (panel == null) {
                    val dm = resources.displayMetrics
                    val screenWidth = dm.widthPixels
                    val screenHeight = dm.heightPixels
                    x += direction * 4
                    y += verticalDirection * 2
                    if (x <= 0) { x = 0; direction = 1; v.facingRight = true }
                    if (x >= max(0, screenWidth - v.width)) {
                        x = max(0, screenWidth - v.width)
                        direction = -1
                        v.facingRight = false
                    }
                    val minY = (48 * dm.density).toInt()
                    val maxY = max(minY, screenHeight - v.height - (72 * dm.density).toInt())
                    if (y <= minY) { y = minY; verticalDirection = 1 }
                    if (y >= maxY) { y = maxY; verticalDirection = -1 }
                    p.x = x
                    p.y = y
                    try { wm.updateViewLayout(v, p) } catch (_: Exception) {}
                    v.walkPhase += 0.34f
                    v.invalidate()
                } else {
                    v.walkPhase += 0.16f
                    v.invalidate()
                }
            }
            handler.postDelayed(this, 42)
        }
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(91, notification())
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE
        val v = WalkingRobotView(this)
        robot = v
        robotParams = WindowManager.LayoutParams(
            116, 190, type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 0
            y = resources.displayMetrics.heightPixels / 3
        }
        v.setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    touchRawX = event.rawX; touchRawY = event.rawY
                    touchStartX = robotParams?.x ?: 0
                    touchStartY = robotParams?.y ?: 0
                    dragged = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - touchRawX
                    val dy = event.rawY - touchRawY
                    if (kotlin.math.abs(dx) > 8 || kotlin.math.abs(dy) > 8) dragged = true
                    if (dragged) {
                        val p = robotParams
                        if (p != null) {
                            p.x = (touchStartX + dx).toInt()
                            p.y = (touchStartY + dy).toInt()
                            x = p.x
                            try { wm.updateViewLayout(view, p) } catch (_: Exception) {}
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!dragged) {
                        view.performClick()
                        if (panel == null) showChatPanel(startListening = true) else startPanelListening()
                    }
                    true
                }
                else -> true
            }
        }
        wm.addView(v, robotParams)
        handler.post(step)
    }

    private fun showChatPanel(startListening: Boolean = false) {
        pendingListenOnOpen = startListening
        if (panel != null) return
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(7, 17, 31))
            elevation = 14f
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(10, 6, 6, 6)
            setBackgroundColor(Color.rgb(18, 37, 59))
        }
        val title = TextView(this).apply {
            text = "Norah voice chat"
            textSize = 15f
            setTextColor(Color.WHITE)
        }
        val close = Button(this).apply {
            text = "Hide"
            setOnClickListener { hideChatPanel() }
        }
        header.addView(title, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        header.addView(close)
        val miniWeb = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.allowContentAccess = true
            settings.allowFileAccess = false
            CookieManager.getInstance().setAcceptCookie(true)
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    if (pendingListenOnOpen) {
                        pendingListenOnOpen = false
                        view?.evaluateJavascript("window.NorahStartListening && window.NorahStartListening()", null)
                    }
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onPermissionRequest(request: PermissionRequest) {
                    handler.post {
                        val hasMic = !request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE) ||
                            checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
                        val hasCamera = !request.resources.contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE) ||
                            checkSelfPermission(android.Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
                        if (hasMic && hasCamera) {
                            request.grant(request.resources)
                        } else {
                            request.deny()
                            Toast.makeText(this@RobotOverlayService, "Open Adaptive AI and grant microphone and camera permissions before using voice or camera in floating chat.", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            }
            loadUrl("https://adaptive-ai-huve.onrender.com/app/?native=1")
            alpha = 0f
        }
        speechBridge = AndroidSpeechBridge(this).also { bridge ->
            bridge.attachWebView(miniWeb)
            miniWeb.addJavascriptInterface(bridge, "AdaptiveNative")
        }
        val status = TextView(this).apply {
            text = "Opening secure voice session…"
            textSize = 13f
            setTextColor(Color.rgb(220, 235, 248))
            setPadding(12, 8, 12, 12)
            maxLines = 4
        }
        responseView = status
        speechBridge?.overlayTextListener = { message -> responseView?.text = message }
        speechBridge?.overlayListeningListener = { responseView?.text = "Listening… Speak now. Norah will answer aloud." }
        root.addView(header, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        root.addView(status, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        root.addView(miniWeb, LinearLayout.LayoutParams(1, 1))
        val dm = resources.displayMetrics
        val width = minOf((dm.widthPixels * 0.86f).toInt(), (320 * dm.density).toInt())
        val height = (104 * dm.density).toInt()
        val lp = WindowManager.LayoutParams(
            width, height, type,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = ((dm.widthPixels - width) / 2).coerceAtLeast(0)
            y = (dm.heightPixels * 0.12f).toInt()
            softInputMode = WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE
        }
        panel = root
        panelParams = lp
        try { wm.addView(root, lp) } catch (e: Exception) {
            panel = null; panelParams = null
            Toast.makeText(this, "Could not open floating chat. Check the display-over-other-apps permission.", Toast.LENGTH_LONG).show()
        }
    }

    private fun startPanelListening() {
        val web = panel?.getChildAt(2) as? WebView ?: return
        web.evaluateJavascript("window.NorahStartListening && window.NorahStartListening()", null)
    }

    private fun hideChatPanel() {
        pendingListenOnOpen = false
        val p = panel
        if (p != null) {
            try { (p.getChildAt(2) as? WebView)?.apply { stopLoading(); removeJavascriptInterface("AdaptiveNative"); destroy() }; wm.removeView(p) } catch (_: Exception) {}
            speechBridge?.close()
            speechBridge = null
        }
        panel = null
        panelParams = null
        responseView = null
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY
    override fun onDestroy() {
        handler.removeCallbacks(step)
        hideChatPanel()
        try { robot?.let { wm.removeView(it) } } catch (_: Exception) {}
        robot = null
        super.onDestroy()
    }
    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel("adaptive_robot", "Adaptive AI floating robot", NotificationManager.IMPORTANCE_LOW))
        }
    }
    private fun notification(): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return if (Build.VERSION.SDK_INT >= 26)
            Notification.Builder(this, "adaptive_robot")
                .setContentTitle("Adaptive AI robot is active")
                .setContentText("Tap the walking robot to talk to Norah. Use Hide to close floating chat.")
                .setSmallIcon(android.R.drawable.ic_dialog_info).setContentIntent(open).setOngoing(true).build()
        else Notification.Builder(this).setContentTitle("Adaptive AI robot is active")
            .setSmallIcon(android.R.drawable.ic_dialog_info).setContentIntent(open).build()
    }
}

private class WalkingRobotView(context: android.content.Context) : View(context) {
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    var walkPhase = 0f
    var facingRight = true
    private fun paint(color: Int, style: Paint.Style = Paint.Style.FILL, width: Float = 1f) {
        p.color = color; p.style = style; p.strokeWidth = width; p.strokeCap = Paint.Cap.ROUND; p.strokeJoin = Paint.Join.ROUND
    }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val c = canvas
        val cx = width / 2f
        val swing = kotlin.math.sin(walkPhase.toDouble()).toFloat() * 13f
        val wave = if (walkPhase % 9f > 6f) 22f else 0f
        c.save()
        if (!facingRight) c.scale(-1f, 1f, cx, height / 2f)
        paint(Color.argb(25, 97, 230, 239)); c.drawOval(RectF(8f, 12f, width - 8f, height - 5f), p)
        c.save()
        c.rotate(kotlin.math.sin((walkPhase * .35f).toDouble()).toFloat() * 4f, cx, 44f)
        paint(Color.rgb(97, 230, 239), Paint.Style.STROKE, 3f); c.drawLine(cx, 13f, cx, 23f, p)
        paint(Color.rgb(97, 230, 239)); c.drawCircle(cx, 10f, 5f, p)
        paint(Color.rgb(255, 132, 42)); c.drawRoundRect(RectF(cx - 49f, 31f, cx - 28f, 59f), 9f, 9f, p); c.drawRoundRect(RectF(cx + 28f, 31f, cx + 49f, 59f), 9f, 9f, p)
        paint(Color.rgb(174, 185, 194)); c.drawOval(RectF(cx - 25f, 21f, cx + 25f, 65f), p)
        paint(Color.rgb(228, 246, 255)); c.drawOval(RectF(cx - 21f, 23f, cx + 21f, 62f), p)
        paint(Color.rgb(16, 34, 56)); c.drawRoundRect(RectF(cx - 20, 33f, cx + 20, 58f), 10f, 10f, p)
        paint(Color.rgb(40, 170, 255), Paint.Style.STROKE, 3f); c.drawCircle(cx - 10, 44f, 10f, p); c.drawCircle(cx + 10, 44f, 10f, p)
        paint(Color.rgb(15, 70, 130)); c.drawCircle(cx - 10, 44f, 5f, p); c.drawCircle(cx + 10, 44f, 5f, p)
        c.drawRoundRect(RectF(cx - 7, 52f, cx + 7, 55f), 2f, 2f, p)
        c.restore()
        paint(Color.rgb(255, 132, 42)); c.drawRoundRect(RectF(cx - 26f, 68f, cx + 26f, 108f), 12f, 12f, p)
        paint(Color.rgb(185, 199, 208)); c.drawRoundRect(RectF(cx - 22f, 68f, cx + 22f, 106f), 10f, 10f, p)
        paint(Color.rgb(248, 252, 255)); c.drawRoundRect(RectF(cx - 18f, 72f, cx + 18f, 109f), 8f, 8f, p)
        paint(Color.rgb(97, 230, 239)); c.drawRoundRect(RectF(cx - 7f, 80f, cx + 7f, 92f), 3f, 3f, p)
        paint(Color.rgb(174, 213, 231)); c.drawRoundRect(RectF(cx - 13f, 104f, cx + 13f, 118f), 6f, 6f, p)
        paint(Color.rgb(174, 213, 231), Paint.Style.STROKE, 7f)
        c.drawLine(cx - 21f, 75f, cx - 29f, 88f + swing * .3f, p); c.drawLine(cx - 29f, 88f + swing * .3f, cx - 26f + swing, 105f, p)
        c.drawLine(cx + 21f, 75f, cx + 29f, 88f - swing * .3f - wave, p); c.drawLine(cx + 29f, 88f - swing * .3f - wave, cx + 26f - swing, 105f - wave, p)
        paint(Color.rgb(97, 230, 239)); c.drawCircle(cx - 29f, 89f + swing * .3f, 4f, p); c.drawCircle(cx + 29f, 89f - swing * .3f - wave, 4f, p)
        paint(Color.rgb(228, 246, 255)); c.drawCircle(cx - 26f + swing, 107f, 5f, p); c.drawCircle(cx + 26f - swing, 107f - wave, 5f, p)
        paint(Color.rgb(176, 188, 198), Paint.Style.STROKE, 9f)
        c.drawLine(cx - 9, 111f, cx - 12 - swing * .35f, 143f, p); c.drawLine(cx + 9, 111f, cx + 12 + swing * .35f, 143f, p)
        paint(Color.rgb(255, 132, 42))
        c.drawRoundRect(RectF(cx - 25f, 140f, cx - 5f, 154f), 5f, 5f, p); c.drawRoundRect(RectF(cx + 5f, 140f, cx + 25f, 154f), 5f, 5f, p)
        paint(Color.rgb(235, 243, 248))
        c.drawRoundRect(RectF(cx - 23 - swing * .35f, 140f, cx - 6 - swing * .35f, 151f), 5f, 5f, p)
        c.drawRoundRect(RectF(cx + 6 + swing * .35f, 140f, cx + 23 + swing * .35f, 151f), 5f, 5f, p)
        c.restore()
    }
    override fun performClick(): Boolean { super.performClick(); return true }
}
