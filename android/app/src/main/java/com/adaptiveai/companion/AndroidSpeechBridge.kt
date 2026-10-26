package com.adaptiveai.companion

import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.webkit.JavascriptInterface
import android.webkit.WebView
import org.json.JSONObject
import java.util.Locale

class AndroidSpeechBridge(context: Context) : AutoCloseable {
    @Volatile private var initializationComplete = false
    @Volatile private var engineReady = false
    @Volatile private var pendingText: String? = null
    private val appContext = context.applicationContext
    private val mainHandler = Handler(Looper.getMainLooper())
    @Volatile private var webView: WebView? = null
    private var recognizer: SpeechRecognizer? = null
    @Volatile private var listening = false
    @Volatile private var recognitionLanguage = "en-NG"
    @Volatile private var speechRate = 1.0f
    @Volatile private var speechPitch = 1.0f
    private lateinit var engine: TextToSpeech

    init {
        engine = TextToSpeech(appContext) { status ->
            engineReady = status == TextToSpeech.SUCCESS && configureLanguage()
            initializationComplete = true
            val queued = pendingText
            pendingText = null
            if (engineReady && queued != null) speakNow(queued)
        }
        if (SpeechRecognizer.isRecognitionAvailable(appContext)) {
            mainHandler.post {
                recognizer = SpeechRecognizer.createSpeechRecognizer(appContext).apply {
                    setRecognitionListener(object : RecognitionListener {
                        override fun onReadyForSpeech(params: Bundle?) {
                            listening = true
                            notifyPage("onListening", "")
                        }
                        override fun onBeginningOfSpeech() {}
                        override fun onRmsChanged(rmsdB: Float) {}
                        override fun onBufferReceived(buffer: ByteArray?) {}
                        override fun onEndOfSpeech() {}
                        override fun onError(error: Int) {
                            listening = false
                            notifyPage("onError", errorMessage(error))
                        }
                        override fun onResults(results: Bundle?) {
                            listening = false
                            val spoken = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                                ?.firstOrNull()?.trim().orEmpty()
                            if (spoken.isNotEmpty()) notifyPage("onResult", spoken)
                            else notifyPage("onError", "I didn't catch that. Tap the microphone and try again.")
                        }
                        override fun onPartialResults(partialResults: Bundle?) {
                            val spoken = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                                ?.firstOrNull()?.trim().orEmpty()
                            if (spoken.isNotEmpty()) notifyPage("onPartial", spoken)
                        }
                        override fun onEvent(eventType: Int, params: Bundle?) {}
                    })
                }
            }
        }
    }

    fun attachWebView(view: WebView) { webView = view }

    private fun notifyPage(method: String, value: String) {
        val quoted = JSONObject.quote(value)
        mainHandler.post {
            webView?.evaluateJavascript("window.NorahNativeVoice && window.NorahNativeVoice.$method($quoted)", null)
        }
    }

    private fun errorMessage(error: Int): String = when (error) {
        SpeechRecognizer.ERROR_AUDIO -> "Microphone audio error. Check your phone's microphone."
        SpeechRecognizer.ERROR_CLIENT -> "Voice input was interrupted. Tap the microphone to try again."
        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Microphone permission is required. Allow it for Norah in Android settings."
        SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Speech recognition needs a working internet connection."
        SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "I didn't catch that. Tap the microphone and try again."
        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Microphone is busy. Wait a moment and tap again."
        SpeechRecognizer.ERROR_SERVER -> "Android speech recognition is temporarily unavailable."
        else -> "Voice input failed (error $error). Tap the microphone and try again."
    }

    @JavascriptInterface
    fun startListening(): Boolean {
        if (!SpeechRecognizer.isRecognitionAvailable(appContext)) {
            notifyPage("onError", "Android speech recognition is unavailable on this phone.")
            return false
        }
        mainHandler.post {
            try {
                if (listening) recognizer?.cancel()
                if (recognizer == null) {
                    recognizer = SpeechRecognizer.createSpeechRecognizer(appContext)
                    recognizer?.setRecognitionListener(object : RecognitionListener {
                        override fun onReadyForSpeech(params: Bundle?) { listening = true; notifyPage("onListening", "") }
                        override fun onBeginningOfSpeech() {}
                        override fun onRmsChanged(rmsdB: Float) {}
                        override fun onBufferReceived(buffer: ByteArray?) {}
                        override fun onEndOfSpeech() {}
                        override fun onError(error: Int) { listening = false; notifyPage("onError", errorMessage(error)) }
                        override fun onResults(results: Bundle?) {
                            listening = false
                            val spoken = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
                            if (spoken.isNotEmpty()) notifyPage("onResult", spoken)
                            else notifyPage("onError", "I didn't catch that. Tap the microphone and try again.")
                        }
                        override fun onPartialResults(partialResults: Bundle?) {
                            val spoken = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
                            if (spoken.isNotEmpty()) notifyPage("onPartial", spoken)
                        }
                        override fun onEvent(eventType: Int, params: Bundle?) {}
                    })
                }
                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, recognitionLanguage)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, recognitionLanguage)
                    putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
                    putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, appContext.packageName)
                }
                recognizer?.startListening(intent)
            } catch (e: Exception) {
                listening = false
                notifyPage("onError", e.message ?: "Could not start the microphone.")
            }
        }
        return true
    }

    @JavascriptInterface
    fun stopListening() {
        mainHandler.post {
            try { recognizer?.cancel() } catch (_: Exception) {}
            listening = false
            notifyPage("onStopped", "")
        }
    }

    private fun configureLanguage(): Boolean {
        engine.setAudioAttributes(
            AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()
        )
        val candidates = listOf(Locale("en", "NG"), Locale.US, Locale.UK, Locale.ENGLISH, Locale.getDefault())
        val selected = candidates.firstOrNull { engine.isLanguageAvailable(it) >= TextToSpeech.LANG_AVAILABLE } ?: return false
        return engine.setLanguage(selected) >= TextToSpeech.LANG_AVAILABLE
    }

    private fun speakNow(text: String): Boolean {
        engine.setSpeechRate(speechRate)
        engine.setPitch(speechPitch)
        return engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, "norah-reply") == TextToSpeech.SUCCESS
    }

    @JavascriptInterface
    fun speak(text: String?): Boolean {
        val safe = text?.take(12000)?.trim().orEmpty()
        if (safe.isEmpty()) return false
        if (engineReady) return speakNow(safe)
        if (initializationComplete) return false
        pendingText = safe
        return true
    }


    /** Set a BCP-47 recognition locale, for example en-NG or fr-FR. */
    @JavascriptInterface
    fun setRecognitionLanguage(languageTag: String?): Boolean {
        val safe = languageTag?.trim()?.take(20).orEmpty()
        if (!safe.matches(Regex("^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$"))) return false
        recognitionLanguage = safe
        return true
    }

    /** Change speech output rate within conservative bounds. */
    @JavascriptInterface
    fun setSpeechRate(rate: Float): Boolean {
        if (!rate.isFinite() || rate < 0.5f || rate > 2.0f) return false
        speechRate = rate
        return true
    }

    /** Change speech output pitch within conservative bounds. */
    @JavascriptInterface
    fun setSpeechPitch(pitch: Float): Boolean {
        if (!pitch.isFinite() || pitch < 0.5f || pitch > 2.0f) return false
        speechPitch = pitch
        return true
    }

    /** Select an installed text-to-speech locale. */
    @JavascriptInterface
    fun setSpeechLanguage(languageTag: String?): Boolean {
        val safe = languageTag?.trim()?.take(20).orEmpty()
        if (!safe.matches(Regex("^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")) || !engineReady) return false
        val locale = Locale.forLanguageTag(safe)
        if (engine.isLanguageAvailable(locale) < TextToSpeech.LANG_AVAILABLE) return false
        return engine.setLanguage(locale) >= TextToSpeech.LANG_AVAILABLE
    }

    @JavascriptInterface
    fun stop() {
        pendingText = null
        if (engineReady) engine.stop()
    }

    override fun close() {
        pendingText = null
        mainHandler.post {
            try { recognizer?.cancel(); recognizer?.destroy() } catch (_: Exception) {}
            recognizer = null
            listening = false
        }
        if (::engine.isInitialized) {
            engine.stop()
            engine.shutdown()
            engineReady = false
            initializationComplete = true
        }
        webView = null
    }
}