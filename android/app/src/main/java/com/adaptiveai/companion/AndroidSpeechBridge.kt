package com.adaptiveai.companion

import android.content.Context
import android.media.AudioAttributes
import android.speech.tts.TextToSpeech
import android.webkit.JavascriptInterface
import java.util.Locale

class AndroidSpeechBridge(context: Context) : AutoCloseable {
    @Volatile private var initializationComplete: Boolean = false
    @Volatile private var engineReady: Boolean = false
    @Volatile private var pendingText: String? = null
    private lateinit var engine: TextToSpeech

    init {
        engine = TextToSpeech(context.applicationContext) { status: Int ->
            engineReady = status == TextToSpeech.SUCCESS && configureLanguage()
            initializationComplete = true
            val queued: String? = pendingText
            pendingText = null
            if (engineReady && queued != null) {
                speakNow(queued)
            }
        }
    }

    private fun configureLanguage(): Boolean {
        // Use the normal media stream so speech follows the phone's media volume.
        engine.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
        )
        val candidates = listOf(
            Locale("en", "NG"),
            Locale.US,
            Locale.UK,
            Locale.ENGLISH,
            Locale.getDefault()
        )
        val selected = candidates.firstOrNull {
            engine.isLanguageAvailable(it) >= TextToSpeech.LANG_AVAILABLE
        } ?: return false
        return engine.setLanguage(selected) >= TextToSpeech.LANG_AVAILABLE
    }

    private fun speakNow(text: String): Boolean {
        return engine.speak(
            text,
            TextToSpeech.QUEUE_FLUSH,
            null,
            "adaptive-ai-reply"
        ) == TextToSpeech.SUCCESS
    }

    @JavascriptInterface
    fun speak(text: String?): Boolean {
        val safe: String = text?.take(12000)?.trim().orEmpty()
        if (safe.isEmpty()) return false
        if (engineReady) return speakNow(safe)
        if (initializationComplete) return false
        pendingText = safe
        return true
    }

    @JavascriptInterface
    fun stop() {
        pendingText = null
        if (engineReady) engine.stop()
    }

    override fun close() {
        pendingText = null
        if (::engine.isInitialized) {
            engine.stop()
            engine.shutdown()
            engineReady = false
            initializationComplete = true
        }
    }
}
