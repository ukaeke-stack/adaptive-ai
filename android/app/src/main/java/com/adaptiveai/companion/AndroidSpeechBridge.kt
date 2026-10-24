package com.adaptiveai.companion

import android.content.Context
import android.speech.tts.TextToSpeech
import android.webkit.JavascriptInterface
import java.util.Locale

class AndroidSpeechBridge(context: Context) : AutoCloseable {
    @Volatile private var engineReady: Boolean = false
    @Volatile private var pendingText: String? = null
    private lateinit var engine: TextToSpeech

    init {
        engine = TextToSpeech(context.applicationContext) { status: Int ->
            engineReady = status == TextToSpeech.SUCCESS
            if (engineReady) {
                engine.language = Locale("en", "NG")
                val queued: String? = pendingText
                pendingText = null
                if (queued != null) {
                    engine.speak(queued, TextToSpeech.QUEUE_FLUSH, null, "adaptive-ai-reply")
                }
            }
        }
    }

    @JavascriptInterface
    fun speak(text: String?) {
        val safe: String = text?.take(12000)?.trim().orEmpty()
        if (safe.isEmpty()) return
        if (engineReady) {
            engine.speak(safe, TextToSpeech.QUEUE_FLUSH, null, "adaptive-ai-reply")
        } else {
            pendingText = safe
        }
    }

    @JavascriptInterface
    fun stop() {
        pendingText = null
        if (engineReady) engine.stop()
    }

    override fun close() {
        pendingText = null
        if (engineReady) {
            engine.stop()
            engine.shutdown()
            engineReady = false
        }
    }
}
