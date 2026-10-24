package com.adaptiveai.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
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
import kotlin.math.max
import kotlin.math.min

class RobotOverlayService : Service() {
    private lateinit var wm: WindowManager
    private var robot: WalkingRobotView? = null
    private var params: WindowManager.LayoutParams? = null
    private val handler = Handler(Looper.getMainLooper())
    private var x = 0; private var direction = 1
    private val step = object : Runnable {
        override fun run() {
            val p = params; val v = robot
            if (p != null && v != null) {
                val width = resources.displayMetrics.widthPixels
                x += direction * 5
                if (x <= 0) { x = 0; direction = 1; v.facingRight = true }
                if (x >= max(0, width - v.width)) { x = max(0, width - v.width); direction = -1; v.facingRight = false }
                p.x = x
                try { wm.updateViewLayout(v, p) } catch (_: Exception) {}
                v.walkPhase += 0.38f; v.invalidate()
            }
            handler.postDelayed(this, 42)
        }
    }
    override fun onCreate() {
        super.onCreate(); createNotificationChannel(); startForeground(91, notification())
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY else WindowManager.LayoutParams.TYPE_PHONE
        val v = WalkingRobotView(this)
        robot = v
        params = WindowManager.LayoutParams(116, 190, type, WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN, PixelFormat.TRANSLUCENT).apply { gravity = Gravity.TOP or Gravity.START; x = 0; y = resources.displayMetrics.heightPixels / 3 }
        v.setOnClickListener { val i = Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP); startActivity(i) }
        v.setOnTouchListener { view, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> { view.tag = floatArrayOf(event.rawX - (params?.x ?: 0), event.rawY - (params?.y ?: 0)); true }
                MotionEvent.ACTION_MOVE -> { val d = view.tag as? FloatArray; val p = params; if (d != null && p != null) { p.x = (event.rawX - d[0]).toInt(); p.y = (event.rawY - d[1]).toInt(); x = p.x; try { wm.updateViewLayout(view, p) } catch (_: Exception) {} }; true }
                MotionEvent.ACTION_UP -> { if (kotlin.math.abs(event.rawX - event.downTime.toFloat()) < -1f) performClick(); true }
                else -> true
            }
        }
        wm.addView(v, params); handler.post(step)
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY
    override fun onDestroy() { handler.removeCallbacks(step); try { robot?.let { wm.removeView(it) } } catch (_: Exception) {}; robot = null; super.onDestroy() }
    override fun onBind(intent: Intent?): IBinder? = null
    private fun createNotificationChannel() { if (Build.VERSION.SDK_INT >= 26) { val manager = getSystemService(NotificationManager::class.java); manager.createNotificationChannel(NotificationChannel("adaptive_robot", "Adaptive AI floating robot", NotificationManager.IMPORTANCE_LOW)) } }
    private fun notification(): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, "adaptive_robot").setContentTitle("Adaptive AI robot is active").setContentText("Tap the notification to open voice chat. Stop the service from Android settings to hide the robot.").setSmallIcon(android.R.drawable.ic_dialog_info).setContentIntent(open).setOngoing(true).build() else Notification.Builder(this).setContentTitle("Adaptive AI robot is active").setSmallIcon(android.R.drawable.ic_dialog_info).setContentIntent(open).build()
    }
}

private class WalkingRobotView(context: android.content.Context) : View(context) {
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    var walkPhase = 0f; var facingRight = true
    private fun paint(color: Int, style: Paint.Style = Paint.Style.FILL, width: Float = 1f) { p.color = color; p.style = style; p.strokeWidth = width; p.strokeCap = Paint.Cap.ROUND; p.strokeJoin = Paint.Join.ROUND }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas); val c = canvas; val cx = width / 2f; val swing = kotlin.math.sin(walkPhase.toDouble()).toFloat() * 13f
        c.save(); if (!facingRight) { c.scale(-1f, 1f, cx, height / 2f) }
        paint(Color.argb(25, 97, 230, 239)); c.drawOval(RectF(8f, 12f, width-8f, height-5f), p)
        paint(Color.rgb(97,230,239), Paint.Style.STROKE, 3f); c.drawLine(cx, 13f, cx, 23f, p); paint(Color.rgb(97,230,239)); c.drawCircle(cx, 10f, 5f, p)
        paint(Color.rgb(214,250,255)); c.drawRoundRect(RectF(cx-27,24f,cx+27,67f),16f,16f,p); paint(Color.rgb(16,34,56)); c.drawRoundRect(RectF(cx-20,33f,cx+20,58f),10f,10f,p)
        paint(Color.rgb(97,230,239)); c.drawCircle(cx-9,44f,4f,p); c.drawCircle(cx+9,44f,4f,p); c.drawRoundRect(RectF(cx-7,52f,cx+7,55f),2f,2f,p)
        paint(Color.rgb(157,140,255)); c.drawRoundRect(RectF(cx-18,69f,cx+18,111f),9f,9f,p); paint(Color.rgb(128,234,240)); c.drawCircle(cx,86f,7f,p)
        paint(Color.rgb(119,184,215),Paint.Style.STROKE,7f); c.drawLine(cx-16,76f,cx-26,94f+swing,p); c.drawLine(cx+16,76f,cx+26,94f-swing,p); paint(Color.rgb(214,250,255)); c.drawCircle(cx-26,96f+swing,5f,p); c.drawCircle(cx+26,96f-swing,5f,p)
        paint(Color.rgb(119,184,215),Paint.Style.STROKE,9f); c.drawLine(cx-9,111f,cx-12-swing*.35f,143f,p); c.drawLine(cx+9,111f,cx+12+swing*.35f,143f,p); paint(Color.rgb(214,250,255)); c.drawRoundRect(RectF(cx-23-swing*.35f,140f,cx-6-swing*.35f,151f),5f,5f,p); c.drawRoundRect(RectF(cx+6+swing*.35f,140f,cx+23+swing*.35f,151f),5f,5f,p)
        c.restore()
    }
    override fun performClick(): Boolean { super.performClick(); return true }
}
