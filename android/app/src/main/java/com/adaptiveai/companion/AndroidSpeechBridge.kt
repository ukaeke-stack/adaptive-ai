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
            engineReady = status == TextToSpeech.SUCCESS && configureLanguage()
            val queued: String? = pendingText
            pendingText = null
            if (engineReady && queued != null) {
                engine.speak(queued, TextToSpeech.QUEUE_FLUSH, null, "adaptive-ai-reply")
            }
        }
    }

    private fun configureLanguage(): Boolean {
        val nigerianEnglish = Locale("en", "NG")
        val usEnglish = Locale.US
        val preferredAvailable = engine.isLanguageAvailable(nigerianEnglish) >= TextToSpeech.LANG_AVAILABLE
        val selected = if (preferredAvailable) nigerianEnglish else usEnglish
        if (engine.isLanguageAvailable(selected) < TextToSpeech.LANG_AVAILABLE) return false
        return engine.setLanguage(selected) >= TextToSpeech.LANG_AVAILABLE
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
