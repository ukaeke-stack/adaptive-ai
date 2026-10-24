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
import android.speech.tts.UtteranceProgressListener
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
    @Volatile var overlayTextListener: ((String) -> Unit)? = null
    @Volatile var overlayListeningListener: (() -> Unit)? = null
    @Volatile var overlayTextProgressListener: ((Float) -> Unit)? = null
    @Volatile private var speakingLength = 1
    private lateinit var engine: TextToSpeech

    init {
        engine = TextToSpeech(appContext) { status ->
            engineReady = status == TextToSpeech.SUCCESS && configureLanguage()
            initializationComplete = true
            val queued = pendingText
            pendingText = null
            if (engineReady && queued != null) speakNow(queued)
        }
        engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            override fun onDone(utteranceId: String?) {
                mainHandler.post { overlayTextProgressListener?.invoke(1f) }
            }
            override fun onError(utteranceId: String?) {}
            override fun onRangeStart(utteranceId: String?, start: Int, end: Int, frame: Int) {
                val progress = (end.toFloat() / speakingLength.coerceAtLeast(1)).coerceIn(0f, 1f)
                mainHandler.post { overlayTextProgressListener?.invoke(progress) }
            }
        })
        if (SpeechRecognizer.isRecognitionAvailable(appContext)) {
            mainHandler.post {
                recognizer = SpeechRecognizer.createSpeechRecognizer(appContext).apply {
                    setRecognitionListener(object : RecognitionListener {
                        override fun onReadyForSpeech(params: Bundle?) {
                            listening = true
                            mainHandler.post { overlayListeningListener?.invoke() }
                            notifyPage("onListening", "")
                        }
                        override fun onBeginningOfSpeech() {}
                        override fun onRmsChanged(rmsdB: Float) {}
                        override fun onBufferReceived(buffer: ByteArray?) {}
                        override fun onEndOfSpeech() {
                            mainHandler.post { overlayTextListener?.invoke("Processing your speech…") }
                        }
                        override fun onError(error: Int) {
                            listening = false
                            val message = errorMessage(error)
                            mainHandler.post { overlayTextListener?.invoke(message) }
                            notifyPage("onError", message)
                        }
                        override fun onResults(results: Bundle?) {
                            listening = false
                            val spoken = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                                ?.firstOrNull()?.trim().orEmpty()
                            if (spoken.isNotEmpty()) {
                                mainHandler.post { overlayTextListener?.invoke("Heard: $spoken\nSending to Norah…") }
                                notifyPage("onResult", spoken)
                            } else {
                                val message = "I didn't catch that. Tap the robot and try again."
                                mainHandler.post { overlayTextListener?.invoke(message) }
                                notifyPage("onError", message)
                            }
                        }
                        override fun onPartialResults(partialResults: Bundle?) {
                            val spoken = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                                ?.firstOrNull()?.trim().orEmpty()
                            if (spoken.isNotEmpty()) {
                                mainHandler.post { overlayTextListener?.invoke("Hearing: $spoken") }
                                notifyPage("onPartial", spoken)
                            }
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
    fun showOverlayText(text: String?) {
        val safe = text?.take(12000)?.trim().orEmpty()
        if (safe.isEmpty()) return
        mainHandler.post { overlayTextListener?.invoke(safe) }
    }

    @JavascriptInterface
    fun startListening(): Boolean {
        if (!SpeechRecognizer.isRecognitionAvailable(appContext)) {
            notifyPage("onError", "Android speech recognition is unavailable on this phone.")
            return false
        }
        mainHandler.post {
            overlayListeningListener?.invoke()
            try {
                if (listening) recognizer?.cancel()
                if (recognizer == null) {
                    recognizer = SpeechRecognizer.createSpeechRecognizer(appContext)
                    recognizer?.setRecognitionListener(object : RecognitionListener {
                        override fun onReadyForSpeech(params: Bundle?) { listening = true; overlayListeningListener?.invoke(); notifyPage("onListening", "") }
                        override fun onBeginningOfSpeech() {}
                        override fun onRmsChanged(rmsdB: Float) {}
                        override fun onBufferReceived(buffer: ByteArray?) {}
                        override fun onEndOfSpeech() {}
                        override fun onError(error: Int) { listening = false; val message = errorMessage(error); overlayTextListener?.invoke(message); notifyPage("onError", message) }
                        override fun onResults(results: Bundle?) {
                            listening = false
                            val spoken = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
                            if (spoken.isNotEmpty()) {
                                overlayTextListener?.invoke("Heard: $spoken\nSending to Norah…")
                                notifyPage("onResult", spoken)
                            } else {
                                val message = "I didn't catch that. Tap the robot and try again."
                                overlayTextListener?.invoke(message)
                                notifyPage("onError", message)
                            }
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
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-NG")
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "en-NG")
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
        speakingLength = text.length.coerceAtLeast(1)
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
        overlayTextListener = null
        overlayTextProgressListener = null
        overlayListeningListener = null
    }
}