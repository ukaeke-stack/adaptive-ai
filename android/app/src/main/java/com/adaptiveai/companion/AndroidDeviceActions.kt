package com.adaptiveai.companion

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.MediaStore
import android.webkit.JavascriptInterface
import android.widget.Toast
import java.net.URLEncoder

/**
 * Narrow, allowlisted Android actions exposed to the trusted Adaptive AI WebView.
 * Sensitive operations open a system UI for the user to review; they are not silently executed.
 */
class AndroidDeviceActions(private val context: Context) {
    private fun launch(intent: Intent, unavailableMessage: String): Boolean {
        return try {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            true
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(context, unavailableMessage, Toast.LENGTH_LONG).show()
            false
        } catch (_: SecurityException) {
            Toast.makeText(context, "Android blocked this action. Check the app permissions and device settings.", Toast.LENGTH_LONG).show()
            false
        }
    }

    @JavascriptInterface
    fun openMusic(): Boolean {
        val music = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_APP_MUSIC)
        return if (music.resolveActivity(context.packageManager) != null) {
            launch(music, "No compatible music app was found.")
        } else {
            launch(Intent(Intent.ACTION_VIEW, MediaStore.Audio.Media.EXTERNAL_CONTENT_URI),
                "No compatible music app was found.")
        }
    }

    /** Opens the dialer for user review; does not place a call automatically. */
    @JavascriptInterface
    fun makeCall(number: String?): Boolean {
        val safeNumber = number?.trim()?.take(40).orEmpty()
        if (safeNumber.isBlank() || safeNumber.any { !(it.isDigit() || it in "+*#()- ") }) return false
        return launch(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + Uri.encode(safeNumber))),
            "No phone dialer is available.")
    }

    /** Opens the SMS composer with a recipient and optional draft text; user presses Send. */
    @JavascriptInterface
    fun sendMessage(number: String?, message: String?): Boolean {
        val safeNumber = number?.trim()?.take(40).orEmpty()
        val safeMessage = message?.trim()?.take(4000).orEmpty()
        if (safeNumber.isBlank() || safeNumber.any { !(it.isDigit() || it in "+*#()- ") }) return false
        val intent = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:" + Uri.encode(safeNumber)))
            .putExtra("sms_body", safeMessage)
        return launch(intent, "No SMS application is available.")
    }

    /** Opens the default messaging app so the user can review their inbox. */
    @JavascriptInterface
    fun openMessages(): Boolean {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_APP_MESSAGING)
        return launch(intent, "No messaging application is available.")
    }

    /** Opens the system contacts app. Android owns the contact data and picker permissions. */
    @JavascriptInterface
    fun openContacts(): Boolean =
        launch(Intent(Intent.ACTION_VIEW, android.provider.ContactsContract.Contacts.CONTENT_URI),
            "No contacts application is available.")

    /** Opens the system camera UI. Android's camera privacy controls remain in effect. */
    @JavascriptInterface
    fun takePicture(): Boolean =
        launch(Intent(MediaStore.ACTION_IMAGE_CAPTURE), "No camera application is available.")

    @JavascriptInterface
    fun recordVideo(): Boolean =
        launch(Intent(MediaStore.ACTION_VIDEO_CAPTURE), "No video recording application is available.")

    /** Opens the app's system settings so the user can manage permissions explicitly. */
    @JavascriptInterface
    fun openAppSettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            Uri.parse("package:" + context.packageName)), "Could not open app settings.")
}
