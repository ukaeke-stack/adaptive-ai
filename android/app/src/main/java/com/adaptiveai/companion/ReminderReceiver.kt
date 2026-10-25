package com.adaptiveai.companion

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val reminderId = intent.getStringExtra("reminder_id") ?: return
        val title = intent.getStringExtra("reminder_title")?.take(160)?.ifBlank { "Adaptive AI reminder" }
            ?: "Adaptive AI reminder"
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channelId = "adaptive_ai_reminders"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(NotificationChannel(
                channelId, "Reminders", NotificationManager.IMPORTANCE_DEFAULT
            ).apply { description = "Reminders you schedule in Adaptive AI" })
        }
        val openApp = PendingIntent.getActivity(
            context, reminderId.hashCode() and 0x7fffffff,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = android.app.Notification.Builder(context, channelId)
            .setSmallIcon(R.drawable.norah_launcher)
            .setContentTitle("Adaptive AI reminder")
            .setContentText(title)
            .setStyle(android.app.Notification.BigTextStyle().bigText(title))
            .setContentIntent(openApp)
            .setAutoCancel(true)
            .build()
        manager.notify(reminderId.hashCode() and 0x7fffffff, notification)
    }
}
