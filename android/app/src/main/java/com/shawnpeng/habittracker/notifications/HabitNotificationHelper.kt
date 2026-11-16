package com.shawnpeng.habittracker.notifications

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.shawnpeng.habittracker.MainActivity
import com.shawnpeng.habittracker.R
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.data.formatTime12h
import kotlinx.serialization.json.Json

object HabitNotificationHelper {

    const val CHANNEL_REMINDERS = "habit_reminders_channel"
    const val CHANNEL_ALARMS = "habit_alarms_channel"

    private val habitJson = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    fun ensureChannels(context: Context) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager
            ?: return

        if (manager.getNotificationChannel(CHANNEL_REMINDERS) == null) {
            val reminderChannel = NotificationChannel(
                CHANNEL_REMINDERS,
                "Habit Reminders",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "Scheduled habit reminder notifications"
                enableVibration(true)
            }
            manager.createNotificationChannel(reminderChannel)
        }

        if (manager.getNotificationChannel(CHANNEL_ALARMS) == null) {
            val alarmUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            val audioAttrs = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ALARM)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
            val alarmChannel = NotificationChannel(
                CHANNEL_ALARMS,
                "Habit Alarms",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "High-priority habit alarm ringtone and vibration"
                enableVibration(true)
                vibrationPattern = longArrayOf(0L, 500L, 250L, 500L, 250L, 800L)
                setSound(alarmUri, audioAttrs)
            }
            manager.createNotificationChannel(alarmChannel)
        }
    }

    fun hasNotificationPermission(context: Context): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.POST_NOTIFICATIONS,
            ) == PackageManager.PERMISSION_GRANTED
        } else {
            NotificationManagerCompat.from(context).areNotificationsEnabled()
        }
    }

    fun notificationIdForHabit(habitId: String): Int =
        (habitId.hashCode() and 0x07FFFFFF) + 1000

    fun cancelHabitNotification(context: Context, habitId: String) {
        NotificationManagerCompat.from(context).cancel(notificationIdForHabit(habitId))
    }

    @SuppressLint("MissingPermission")
    fun showHabitNotification(
        context: Context,
        habit: Habit,
        timeLabel: String,
    ) {
        ensureChannels(context)
        if (!hasNotificationPermission(context)) return

        val appContext = context.applicationContext
        val isAlarm = habit.reminderMode == "alarm"
        val channelId = if (isAlarm) CHANNEL_ALARMS else CHANNEL_REMINDERS
        val notifId = notificationIdForHabit(habit.id)
        val encodedHabit = habitJson.encodeToString(Habit.serializer(), habit)
        val snoozeMinutes = habit.reminderSnoozeMinutes.coerceIn(1, 120)

        val messageBody = buildString {
            if (timeLabel.isNotBlank()) {
                append("Scheduled for ${formatTime12h(timeLabel)} · ")
            }
            val customMsg = habit.reminderMessage.trim()
            if (customMsg.isNotEmpty()) {
                append(customMsg)
            } else if (habit.description.isNotBlank()) {
                append(habit.description.trim())
            } else {
                append("Tap to open Habit Tracker and complete today's check-in")
            }
        }

        val openIntent = Intent(appContext, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openPendingIntent = PendingIntent.getActivity(
            appContext,
            notifId,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val checkinIntent = Intent(appContext, HabitAlarmReceiver::class.java).apply {
            action = HabitAlarmReceiver.ACTION_CHECKIN
            putExtra(HabitAlarmReceiver.EXTRA_HABIT_ID, habit.id)
            putExtra(HabitAlarmReceiver.EXTRA_HABIT_JSON, encodedHabit)
        }
        val checkinPending = PendingIntent.getBroadcast(
            appContext,
            notifId * 10 + 1,
            checkinIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val snoozeIntent = Intent(appContext, HabitAlarmReceiver::class.java).apply {
            action = HabitAlarmReceiver.ACTION_SNOOZE
            putExtra(HabitAlarmReceiver.EXTRA_HABIT_ID, habit.id)
            putExtra(HabitAlarmReceiver.EXTRA_HABIT_JSON, encodedHabit)
        }
        val snoozePending = PendingIntent.getBroadcast(
            appContext,
            notifId * 10 + 2,
            snoozeIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val primaryActionLabel = if (
            habit.mode == "strict" &&
            !habit.forceStartTime.isNullOrBlank() &&
            timeLabel.isNotBlank() &&
            timeLabel <= habit.forceStartTime
        ) {
            "Start / Check In"
        } else {
            "Check In"
        }

        val title = if (isAlarm) "⏰ Habit Alarm · ${habit.title}" else "🔔 Habit Reminder · ${habit.title}"
        val builder = NotificationCompat.Builder(appContext, channelId)
            .setSmallIcon(R.drawable.ic_stat_alarm)
            .setContentTitle(title)
            .setContentText(messageBody)
            .setStyle(NotificationCompat.BigTextStyle().bigText(messageBody))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(
                if (isAlarm) NotificationCompat.CATEGORY_ALARM else NotificationCompat.CATEGORY_REMINDER,
            )
            .setAutoCancel(!isAlarm)
            .setContentIntent(openPendingIntent)
            .addAction(0, primaryActionLabel, checkinPending)
            .addAction(0, "Snooze ${snoozeMinutes}m", snoozePending)

        if (isAlarm) {
            val dismissIntent = Intent(appContext, HabitAlarmReceiver::class.java).apply {
                action = HabitAlarmReceiver.ACTION_DISMISS
                putExtra(HabitAlarmReceiver.EXTRA_HABIT_ID, habit.id)
            }
            val dismissPending = PendingIntent.getBroadcast(
                appContext,
                notifId * 10 + 3,
                dismissIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            builder.addAction(0, "Dismiss", dismissPending)
        }

        runCatching {
            NotificationManagerCompat.from(appContext).notify(notifId, builder.build())
        }
    }
}
