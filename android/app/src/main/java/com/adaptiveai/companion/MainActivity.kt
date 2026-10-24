package com.adaptiveai.companion

import android.app.Activity
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.Toast

class MainActivity : Activity() {
    private lateinit var web: WebView
    private var pendingMediaPermission: android.webkit.PermissionRequest? = null
    private lateinit var speechBridge: AndroidSpeechBridge

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        speechBridge = AndroidSpeechBridge(this)
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            addJavascriptInterface(speechBridge, "AdaptiveNative")
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
                        else {
                            pendingMediaPermission = request
                            requestPermissions(needed.toTypedArray(), 902)
                        }
                    }
                }
            }
            loadUrl("https://adaptive-ai-huve.onrender.com/app/?native=1")
        }
        speechBridge.attachWebView(web)
        setContentView(web)
        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(android.Manifest.permission.RECORD_AUDIO), 903)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 902) {
            val request = pendingMediaPermission
            pendingMediaPermission = null
            val allowed = request != null && request.resources.all { resource ->
                when (resource) {
                    android.webkit.PermissionRequest.RESOURCE_AUDIO_CAPTURE ->
                        checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
                    android.webkit.PermissionRequest.RESOURCE_VIDEO_CAPTURE ->
                        checkSelfPermission(android.Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
                    else -> false
                }
            }
            if (allowed) request?.grant(request.resources) else request?.deny()
        } else if (requestCode == 903 &&
            (grantResults.isEmpty() || grantResults[0] != PackageManager.PERMISSION_GRANTED)) {
            Toast.makeText(this, "Microphone permission is needed for voice chat. You can still type messages.", Toast.LENGTH_LONG).show()
        }
    }

    override fun onDestroy() {
        if (::speechBridge.isInitialized) speechBridge.close()
        if (::web.isInitialized) {
            web.stopLoading()
            web.removeJavascriptInterface("AdaptiveNative")
            web.destroy()
        }
        super.onDestroy()
    }

    override fun onBackPressed() {
        if (::web.isInitialized && web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}
