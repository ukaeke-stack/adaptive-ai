package com.adaptiveai.companion

import android.content.ActivityNotFoundException
import android.app.AlarmManager
import android.app.PendingIntent
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
    
    /** Opens Android's contact picker; only the contact selected by the user is returned to Norah. */
    @JavascriptInterface
    fun pickContact(): Boolean {
        val activity = context as? android.app.Activity ?: return false
        return try {
            activity.startActivityForResult(
                Intent(Intent.ACTION_PICK, android.provider.ContactsContract.CommonDataKinds.Phone.CONTENT_URI), 907
            )
            true
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(context, "No contact picker is available.", Toast.LENGTH_LONG).show()
            false
        }
    }

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
    /** Schedules a local Android notification. Android notification permission must be granted. */
    @JavascriptInterface
    fun scheduleReminder(reminderId: String?, title: String?, timestampMillis: Long): Boolean {
        val safeId = reminderId?.trim()?.take(100).orEmpty()
        val safeTitle = title?.trim()?.take(160).orEmpty()
        if (safeId.isBlank() || safeTitle.isBlank() || timestampMillis <= System.currentTimeMillis()) return false
        if (android.os.Build.VERSION.SDK_INT >= 33 &&
            context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            Toast.makeText(context, "Allow notifications in Android settings to receive reminders.", Toast.LENGTH_LONG).show()
            return false
        }
        val intent = Intent(context, ReminderReceiver::class.java)
            .putExtra("reminder_id", safeId)
            .putExtra("reminder_title", safeTitle)
        val pending = PendingIntent.getBroadcast(
            context, safeId.hashCode() and 0x7fffffff, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val alarm = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        alarm.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, timestampMillis, pending)
        return true
    }

    /** Cancels a previously scheduled local reminder on this device. */
    @JavascriptInterface
    fun cancelReminder(reminderId: String?): Boolean {
        val safeId = reminderId?.trim()?.take(100).orEmpty()
        if (safeId.isBlank()) return false
        val intent = Intent(context, ReminderReceiver::class.java)
        val pending = PendingIntent.getBroadcast(
            context, safeId.hashCode() and 0x7fffffff, intent,
            PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
        ) ?: return false
        val alarm = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        alarm.cancel(pending)
        pending.cancel()
        return true
    }

    /** Opens map/navigation search; the user chooses the destination and route. */
    @JavascriptInterface
    fun openMaps(query: String?): Boolean {
        val safeQuery = query?.trim()?.take(300).orEmpty()
        if (safeQuery.isBlank()) return launch(Intent(Intent.ACTION_VIEW, Uri.parse("geo:0,0")), "No maps application is available.")
        return launch(Intent(Intent.ACTION_VIEW, Uri.parse("geo:0,0?q=" + Uri.encode(safeQuery))),
            "No maps application is available.")
    }

    /** Opens a web search in an installed browser; it does not submit private app data. */
    @JavascriptInterface
    fun searchWeb(query: String?): Boolean {
        val safeQuery = query?.trim()?.take(300).orEmpty()
        if (safeQuery.isBlank()) return false
        return launch(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.google.com/search?q=" + Uri.encode(safeQuery))),
            "No browser is available.")
    }

    /** Opens the email composer with a draft. The user reviews and sends it. */
    @JavascriptInterface
    fun draftEmail(address: String?, subject: String?, body: String?): Boolean {
        val safeAddress = address?.trim()?.take(254).orEmpty()
        if (safeAddress.isBlank() || !safeAddress.contains("@") || safeAddress.any { it.isWhitespace() }) return false
        val safeSubject = subject?.take(200).orEmpty()
        val safeBody = body?.take(4000).orEmpty()
        val intent = Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:" + Uri.encode(safeAddress)))
            .putExtra(Intent.EXTRA_SUBJECT, safeSubject)
            .putExtra(Intent.EXTRA_TEXT, safeBody)
        return launch(intent, "No email application is available.")
    }

    /** Shares text using Android's chooser; nothing is sent until the user selects an app and confirms. */
    @JavascriptInterface
    fun shareText(text: String?): Boolean {
        val safeText = text?.take(8000).orEmpty()
        if (safeText.isBlank()) return false
        val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, safeText)
        return launch(Intent.createChooser(send, "Share with"), "No sharing application is available.")
    }

    @JavascriptInterface
    fun openCalendar(): Boolean =
        launch(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_APP_CALENDAR),
            "No calendar application is available.")

    @JavascriptInterface
    fun openClock(): Boolean =
        launch(Intent(android.provider.AlarmClock.ACTION_SHOW_ALARMS),
            "No clock application is available.")

    @JavascriptInterface
    fun openWifiSettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_WIFI_SETTINGS), "Could not open Wi-Fi settings.")

    @JavascriptInterface
    fun openBluetoothSettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_BLUETOOTH_SETTINGS), "Could not open Bluetooth settings.")

    @JavascriptInterface
    fun openLocationSettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_LOCATION_SOURCE_SETTINGS), "Could not open location settings.")

    @JavascriptInterface
    fun openNotificationSettings(): Boolean {
        val intent = if (android.os.Build.VERSION.SDK_INT >= 26) {
            Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, context.packageName)
        } else {
            Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + context.packageName))
        }
        return launch(intent, "Could not open notification settings.")
    }

    @JavascriptInterface
    fun openFiles(): Boolean =
        launch(Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE),
            "No document picker is available.")

    @JavascriptInterface
    fun openCalculator(): Boolean {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_APP_CALCULATOR)
        return launch(intent, "No calculator application is available.")
    }

    @JavascriptInterface
    fun openPhoneDialer(): Boolean =
        launch(Intent(Intent.ACTION_DIAL), "No phone dialer is available.")

    @JavascriptInterface
    fun openEmail(): Boolean =
        launch(Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:")),
            "No email application is available.")

    @JavascriptInterface
    fun openSystemSettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_SETTINGS),
            "Could not open Android settings.")

    @JavascriptInterface
    fun openBrowser(): Boolean =
        launch(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.google.com")),
            "No browser application is available.")

    @JavascriptInterface
    fun openDownloads(): Boolean =
        launch(Intent(Intent.ACTION_VIEW, MediaStore.Downloads.EXTERNAL_CONTENT_URI),
            "No downloads viewer is available.")

    @JavascriptInterface
    fun openYouTube(): Boolean =
        launch(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.youtube.com")),
            "No compatible video app or browser is available.")

    @JavascriptInterface
    fun openBatterySettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_BATTERY_SAVER_SETTINGS),
            "Could not open battery settings.")

    @JavascriptInterface
    fun openDisplaySettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_DISPLAY_SETTINGS),
            "Could not open display settings.")

    @JavascriptInterface
    fun openSoundSettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_SOUND_SETTINGS),
            "Could not open sound settings.")

    @JavascriptInterface
    fun openAccessibilitySettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS),
            "Could not open accessibility settings.")

    @JavascriptInterface
    fun openPhotos(): Boolean =
        launch(Intent(Intent.ACTION_VIEW, MediaStore.Images.Media.EXTERNAL_CONTENT_URI),
            "No photo gallery is available.")

    @JavascriptInterface
    fun openVideoLibrary(): Boolean =
        launch(Intent(Intent.ACTION_VIEW, MediaStore.Video.Media.EXTERNAL_CONTENT_URI),
            "No video library is available.")

    @JavascriptInterface
    fun openVoiceRecorder(): Boolean =
        launch(Intent(MediaStore.Audio.Media.RECORD_SOUND_ACTION),
            "No voice recorder application is available.")

    @JavascriptInterface
    fun openStorageSettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_INTERNAL_STORAGE_SETTINGS),
            "Could not open storage settings.")

    @JavascriptInterface
    fun openPlayStore(): Boolean =
        launch(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store")),
            "No browser is available to open the Play Store website.")

    @JavascriptInterface
    fun copyToClipboard(text: String?): Boolean {
        val safeText = text?.take(12000) ?: return false
        if (safeText.isEmpty()) return false
        return try {
            val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
            clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Norah", safeText))
            Toast.makeText(context, "Text copied to clipboard.", Toast.LENGTH_SHORT).show()
            true
        } catch (_: Exception) {
            Toast.makeText(context, "Could not copy text to clipboard.", Toast.LENGTH_SHORT).show()
            false
        }
    }

    @JavascriptInterface
    fun openAlarmSettings(): Boolean =
        launch(Intent(android.provider.AlarmClock.ACTION_SHOW_ALARMS),
            "No clock application is available.")

    @JavascriptInterface
    fun openLanguageSettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_LOCALE_SETTINGS),
            "Could not open language settings.")

    @JavascriptInterface
    fun openSecuritySettings(): Boolean =
        launch(Intent(android.provider.Settings.ACTION_SECURITY_SETTINGS),
            "Could not open security settings.")

}
