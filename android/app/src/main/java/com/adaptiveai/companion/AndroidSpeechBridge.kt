package com.adaptiveai.companion

import android.content.Context
import android.speech.tts.TextToSpeech
import android.webkit.JavascriptInterface
import java.util.Locale

class AndroidSpeechBridge(context: Context) : AutoCloseable {
    @Volatile private var engineReady = false
    @Volatile private var pendingText: String? = null
    private val engine = TextToSpeech(context.applicationContext) { status ->
        engineReady = status == TextToSpeech.SUCCESS
        if (engineReady) {
            engine.language = Locale("en", "NG")
            pendingText?.let {
                engine.speak(it, TextToSpeech.QUEUE_FLUSH, null, "adaptive-ai-reply")
                pendingText = null
            }
        }
    }

    @JavascriptInterface
    fun speak(text: String?) {
        val safe = text?.take(12000)?.trim().orEmpty()
        if (safe.isEmpty()) return
        if (engineReady) engine.speak(safe, TextToSpeech.QUEUE_FLUSH, null, "adaptive-ai-reply")
        else pendingText = safe
    }

    @JavascriptInterface
    fun stop() {
        pendingText = null
        if (engineReady) engine.stop()
    }

    override fun close() {
        pendingText = null
        engine.stop()
        engine.shutdown()
        engineReady = false
    }
}
