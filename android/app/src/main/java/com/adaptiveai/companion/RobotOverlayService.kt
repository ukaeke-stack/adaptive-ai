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
                        if (panel == null) showChatPanel() else hideChatPanel()
                    }
                    true
                }
                else -> true
            }
        }
        wm.addView(v, robotParams)
        handler.post(step)
    }

    private fun showChatPanel() {
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
            text = "Adaptive AI"
            textSize = 16f
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
            webViewClient = WebViewClient()
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
            loadUrl("https://adaptive-ai-huve.onrender.com/app/")
        }
        root.addView(header, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        root.addView(miniWeb, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        val dm = resources.displayMetrics
        val width = minOf((dm.widthPixels * 0.92f).toInt(), (380 * dm.density).toInt())
        val height = (dm.heightPixels * 0.68f).toInt()
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

    private fun hideChatPanel() {
        val p = panel
        if (p != null) {
            try { (p.getChildAt(1) as? WebView)?.apply { stopLoading(); destroy() }; wm.removeView(p) } catch (_: Exception) {}
        }
        panel = null
        panelParams = null
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
                .setContentText("Tap the walking robot to open or hide floating chat.")
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
        c.save()
        if (!facingRight) c.scale(-1f, 1f, cx, height / 2f)
        paint(Color.argb(25, 97, 230, 239)); c.drawOval(RectF(8f, 12f, width - 8f, height - 5f), p)
        paint(Color.rgb(97, 230, 239), Paint.Style.STROKE, 3f); c.drawLine(cx, 13f, cx, 23f, p)
        paint(Color.rgb(97, 230, 239)); c.drawCircle(cx, 10f, 5f, p)
        paint(Color.rgb(214, 250, 255)); c.drawRoundRect(RectF(cx - 27, 24f, cx + 27, 67f), 16f, 16f, p)
        paint(Color.rgb(16, 34, 56)); c.drawRoundRect(RectF(cx - 20, 33f, cx + 20, 58f), 10f, 10f, p)
        paint(Color.rgb(97, 230, 239)); c.drawCircle(cx - 9, 44f, 4f, p); c.drawCircle(cx + 9, 44f, 4f, p)
        c.drawRoundRect(RectF(cx - 7, 52f, cx + 7, 55f), 2f, 2f, p)
        paint(Color.rgb(157, 140, 255)); c.drawRoundRect(RectF(cx - 18, 69f, cx + 18, 111f), 9f, 9f, p)
        paint(Color.rgb(128, 234, 240)); c.drawCircle(cx, 86f, 7f, p)
        paint(Color.rgb(119, 184, 215), Paint.Style.STROKE, 7f)
        c.drawLine(cx - 16, 76f, cx - 26, 94f + swing, p); c.drawLine(cx + 16, 76f, cx + 26, 94f - swing, p)
        paint(Color.rgb(214, 250, 255)); c.drawCircle(cx - 26, 96f + swing, 5f, p); c.drawCircle(cx + 26, 96f - swing, 5f, p)
        paint(Color.rgb(119, 184, 215), Paint.Style.STROKE, 9f)
        c.drawLine(cx - 9, 111f, cx - 12 - swing * .35f, 143f, p); c.drawLine(cx + 9, 111f, cx + 12 + swing * .35f, 143f, p)
        paint(Color.rgb(214, 250, 255))
        c.drawRoundRect(RectF(cx - 23 - swing * .35f, 140f, cx - 6 - swing * .35f, 151f), 5f, 5f, p)
        c.drawRoundRect(RectF(cx + 6 + swing * .35f, 140f, cx + 23 + swing * .35f, 151f), 5f, 5f, p)
        c.restore()
    }
    override fun performClick(): Boolean { super.performClick(); return true }
}
