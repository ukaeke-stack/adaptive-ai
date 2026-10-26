package com.adaptiveai.companion

import android.app.Activity
import android.content.pm.PackageManager
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.ValueCallback
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {
    private lateinit var web: WebView
    private var pendingMediaPermission: android.webkit.PermissionRequest? = null
    private var pendingFileChooser: ValueCallback<Array<Uri>>? = null
    private lateinit var speechBridge: AndroidSpeechBridge
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF07111F.toInt()) }
        val bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(10, 8, 10, 8) }
        val title = TextView(this).apply { text = "Norah"; textSize = 18f; setTextColor(0xFFFFFFFF.toInt()) }
        val overlay = Button(this).apply { text = "Enable roaming robot"; setOnClickListener { enableOverlay() } }
        bar.addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        bar.addView(overlay)
        speechBridge = AndroidSpeechBridge(this)
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            addJavascriptInterface(speechBridge, "AdaptiveNative")
            addJavascriptInterface(AndroidDeviceActions(this@MainActivity), "AdaptiveDevice")
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            webViewClient = WebViewClient()
            webChromeClient = object : WebChromeClient() {
                override fun onShowFileChooser(
                    webView: WebView?,
                    filePathCallback: ValueCallback<Array<Uri>>?,
                    fileChooserParams: FileChooserParams?
                ): Boolean {
                    pendingFileChooser?.onReceiveValue(null)
                    pendingFileChooser = filePathCallback
                    val acceptedType = fileChooserParams?.acceptTypes?.firstOrNull { it.isNotBlank() && it != "*/*" }
                        ?: "application/pdf"
                    val pick = Intent(Intent.ACTION_GET_CONTENT).apply {
                        type = acceptedType
                        addCategory(Intent.CATEGORY_OPENABLE)
                    }
                    return try {
                        startActivityForResult(Intent.createChooser(pick, "Choose a document"), 905)
                        true
                    } catch (_: android.content.ActivityNotFoundException) {
                        pendingFileChooser?.onReceiveValue(null)
                        pendingFileChooser = null
                        Toast.makeText(this@MainActivity, "No file picker is available.", Toast.LENGTH_LONG).show()
                        false
                    }
                }
                override fun onPermissionRequest(request: android.webkit.PermissionRequest) {
                    runOnUiThread {
                        val needed = mutableListOf<String>()
                        if (request.resources.contains(android.webkit.PermissionRequest.RESOURCE_AUDIO_CAPTURE) &&
                            checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                            needed.add(android.Manifest.permission.RECORD_AUDIO)
                        }
                        if (request.resources.contains(android.webkit.PermissionRequest.RESOURCE_VIDEO_CAPTURE) &&
                            checkSelfPermission(android.Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                            needed.add(android.Manifest.permission.CAMERA)
                        }
                        if (needed.isEmpty()) request.grant(request.resources)
                        else { pendingMediaPermission = request; requestPermissions(needed.toTypedArray(), 902) }
                    }
                }
            }
            loadUrl("https://adaptive-ai-huve.onrender.com/app/")
        }
        speechBridge.attachWebView(web)
        root.addView(bar)
        root.addView(web, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 903)
        } else {
            requestNotificationPermissionIfNeeded()
            if (Settings.canDrawOverlays(this)) startRobotService()
        }
    }
    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 904)
        }
    }
    private fun startRobotService() {
        val intent = Intent(this, RobotOverlayService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
    }
    private fun enableOverlay() {
        if (!Settings.canDrawOverlays(this)) {
            startActivityForResult(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")), 901)
            Toast.makeText(this, "Allow Adaptive AI to display over other apps. The floating robot will start when you return.", Toast.LENGTH_LONG).show()
            return
        }
        startRobotService()
        Toast.makeText(this, "Floating robot enabled. It should remain available over other apps while Android allows the foreground service to run.", Toast.LENGTH_LONG).show()
    }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 905) {
            val callback = pendingFileChooser
            pendingFileChooser = null
            val uri = if (resultCode == RESULT_OK) data?.data else null
            callback?.onReceiveValue(if (uri != null) arrayOf(uri) else null)
            return
        }
        if (requestCode == 901 && Settings.canDrawOverlays(this)) startRobotService()
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 903) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                requestNotificationPermissionIfNeeded()
                enableOverlay()
            } else Toast.makeText(this, "Microphone permission is needed for floating voice chat. You can enable the robot later from this screen.", Toast.LENGTH_LONG).show()
        }
        if (requestCode == 904 && grantResults.firstOrNull() != PackageManager.PERMISSION_GRANTED) {
            Toast.makeText(this, "Reminders can be saved, but notifications are disabled. Enable them in Android app settings.", Toast.LENGTH_LONG).show()
        }
        if (requestCode == 902) {
            val request = pendingMediaPermission; pendingMediaPermission = null
            val allowed = request != null && request.resources.all { resource ->
                when (resource) {
                    android.webkit.PermissionRequest.RESOURCE_AUDIO_CAPTURE -> checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
                    android.webkit.PermissionRequest.RESOURCE_VIDEO_CAPTURE -> checkSelfPermission(android.Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
                    else -> false
                }
            }
            if (allowed) request?.grant(request.resources) else request?.deny()
        }
    }
    override fun onDestroy() {
        if (::speechBridge.isInitialized) speechBridge.close()
        if (::web.isInitialized) { web.stopLoading(); web.destroy() }
        super.onDestroy()
    }
    override fun onBackPressed() {
        if (::web.isInitialized && web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}
