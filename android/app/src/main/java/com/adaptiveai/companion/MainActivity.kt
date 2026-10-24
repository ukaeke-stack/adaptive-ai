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
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {
    private lateinit var web: WebView
    private var pendingMediaPermission: android.webkit.PermissionRequest? = null
    private lateinit var speechBridge: AndroidSpeechBridge
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF07111F.toInt()) }
        val bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(10, 8, 10, 8) }
        val title = TextView(this).apply { text = "Adaptive AI"; textSize = 18f; setTextColor(0xFFFFFFFF.toInt()) }
        val overlay = Button(this).apply { text = "Enable roaming robot"; setOnClickListener { enableOverlay() } }
        bar.addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        bar.addView(overlay)
        speechBridge = AndroidSpeechBridge(this)
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            addJavascriptInterface(speechBridge, "AdaptiveNative")
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            webViewClient = WebViewClient()
            webChromeClient = object : WebChromeClient() {
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
        root.addView(bar)
        root.addView(web, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
    }
    private fun enableOverlay() {
        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 903)
            Toast.makeText(this, "Allow microphone access so voice chat can work in the floating panel.", Toast.LENGTH_LONG).show()
            return
        }
        if (!Settings.canDrawOverlays(this)) {
            startActivityForResult(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")), 901)
            Toast.makeText(this, "Allow Adaptive AI to display over other apps, then return here and tap Enable roaming robot again.", Toast.LENGTH_LONG).show()
            return
        }
        val intent = Intent(this, RobotOverlayService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
        Toast.makeText(this, "Robot overlay enabled. It can remain visible over other apps while Android allows the service to run.", Toast.LENGTH_LONG).show()
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 903) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) enableOverlay()
            else Toast.makeText(this, "Microphone permission is needed for floating voice chat. You can enable the robot later from this screen.", Toast.LENGTH_LONG).show()
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
