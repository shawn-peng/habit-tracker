package com.shawnpeng.habittracker.notifications

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.AlarmClock
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.data.computeNextTriggerDateTime
import com.shawnpeng.habittracker.data.effectiveReminderTimes
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId
import java.util.Calendar
import kotlinx.serialization.json.Json

interface HabitAlarmController {
    fun syncAllHabits(
        habits: List<Habit>,
        completedTodayIds: Set<String> = emptySet(),
        muted: Boolean = false,
    )

    fun scheduleSnooze(habit: Habit, snoozeMinutes: Int)

    fun cancelHabit(habitId: String)

    fun cancelAll()
}

object NoOpHabitAlarmController : HabitAlarmController {
    override fun syncAllHabits(
        habits: List<Habit>,
        completedTodayIds: Set<String>,
        muted: Boolean,
    ) = Unit

    override fun scheduleSnooze(habit: Habit, snoozeMinutes: Int) = Unit

    override fun cancelHabit(habitId: String) = Unit

    override fun cancelAll() = Unit
}

class AndroidHabitAlarmScheduler(context: Context) : HabitAlarmController {

    private val appContext: Context = context.applicationContext
    private val alarmManager: AlarmManager? =
        appContext.getSystemService(Context.ALARM_SERVICE) as? AlarmManager
    private val registry =
        appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    override fun syncAllHabits(
        habits: List<Habit>,
        completedTodayIds: Set<String>,
        muted: Boolean,
    ) {
        HabitNotificationHelper.ensureChannels(appContext)
        val previousIds = getRegisteredIds()
        if (muted) {
            for (id in previousIds) {
                cancelHabit(id)
            }
            for (habit in habits) {
                cancelHabit(habit.id)
            }
            saveRegisteredIds(emptySet())
            return
        }

        val now = LocalDateTime.now()
        val zoneId = ZoneId.systemDefault()
        val activeIds = HashSet<String>()

        for (habit in habits) {
            val completedToday = habit.id in completedTodayIds
            if (completedToday) {
                cancelSnoozeOnly(habit.id)
                HabitNotificationHelper.cancelHabitNotification(appContext, habit.id)
            }
            val nextTrigger = computeNextTriggerDateTime(
                habit = habit,
                fromDateTime = now,
                completedToday = completedToday,
            )
            if (nextTrigger != null) {
                val triggerMillis = nextTrigger.atZone(zoneId).toInstant().toEpochMilli()
                val timeLabel =
                    "${nextTrigger.hour.toString().padStart(2, '0')}:${nextTrigger.minute.toString().padStart(2, '0')}"
                val pending = buildTriggerPendingIntent(
                    habit = habit,
                    timeLabel = timeLabel,
                    isSnooze = false,
                    requestCode = regularRequestCode(habit.id),
                )
                scheduleExactCompat(triggerMillis, pending)
                activeIds.add(habit.id)
            } else {
                cancelRegularOnly(habit.id)
            }
        }

        for (staleId in previousIds) {
            if (staleId !in activeIds) {
                cancelRegularOnly(staleId)
            }
        }
        saveRegisteredIds(activeIds)
    }

    override fun scheduleSnooze(habit: Habit, snoozeMinutes: Int) {
        HabitNotificationHelper.ensureChannels(appContext)
        val minutes = snoozeMinutes.coerceIn(1, 120)
        val triggerMillis = System.currentTimeMillis() + minutes * 60_000L
        val wakeTime = LocalTime.now().plusMinutes(minutes.toLong())
        val label =
            "${wakeTime.hour.toString().padStart(2, '0')}:${wakeTime.minute.toString().padStart(2, '0')}"
        val pending = buildTriggerPendingIntent(
            habit = habit,
            timeLabel = label,
            isSnooze = true,
            requestCode = snoozeRequestCode(habit.id),
        )
        scheduleExactCompat(triggerMillis, pending)
        val ids = getRegisteredIds().toMutableSet()
        ids.add(habit.id)
        saveRegisteredIds(ids)
    }

    override fun cancelHabit(habitId: String) {
        cancelRegularOnly(habitId)
        cancelSnoozeOnly(habitId)
    }

    override fun cancelAll() {
        val ids = getRegisteredIds()
        for (id in ids) {
            cancelHabit(id)
            HabitNotificationHelper.cancelHabitNotification(appContext, id)
        }
        saveRegisteredIds(emptySet())
    }

    private fun cancelRegularOnly(habitId: String) {
        val intent = Intent(appContext, HabitAlarmReceiver::class.java).apply {
            action = HabitAlarmReceiver.ACTION_TRIGGER
        }
        val existing = PendingIntent.getBroadcast(
            appContext,
            regularRequestCode(habitId),
            intent,
            PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE,
        )
        if (existing != null) {
            alarmManager?.cancel(existing)
            existing.cancel()
        }
    }

    private fun cancelSnoozeOnly(habitId: String) {
        val intent = Intent(appContext, HabitAlarmReceiver::class.java).apply {
            action = HabitAlarmReceiver.ACTION_TRIGGER
        }
        val existing = PendingIntent.getBroadcast(
            appContext,
            snoozeRequestCode(habitId),
            intent,
            PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE,
        )
        if (existing != null) {
            alarmManager?.cancel(existing)
            existing.cancel()
        }
    }

    private fun buildTriggerPendingIntent(
        habit: Habit,
        timeLabel: String,
        isSnooze: Boolean,
        requestCode: Int,
    ): PendingIntent {
        val encodedHabit = habitJson.encodeToString(Habit.serializer(), habit)
        val intent = Intent(appContext, HabitAlarmReceiver::class.java).apply {
            action = HabitAlarmReceiver.ACTION_TRIGGER
            putExtra(HabitAlarmReceiver.EXTRA_HABIT_ID, habit.id)
            putExtra(HabitAlarmReceiver.EXTRA_HABIT_JSON, encodedHabit)
            putExtra(HabitAlarmReceiver.EXTRA_TIME_LABEL, timeLabel)
            putExtra(HabitAlarmReceiver.EXTRA_IS_SNOOZE, isSnooze)
        }
        return PendingIntent.getBroadcast(
            appContext,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun scheduleExactCompat(triggerAtMillis: Long, pendingIntent: PendingIntent) {
        val manager = alarmManager ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (manager.canScheduleExactAlarms()) {
                try {
                    manager.setExactAndAllowWhileIdle(
                        AlarmManager.RTC_WAKEUP,
                        triggerAtMillis,
                        pendingIntent,
                    )
                    return
                } catch (_: SecurityException) {
                    // Fallback below if exact alarm permission is revoked dynamically.
                }
            }
            manager.setAndAllowWhileIdle(
                AlarmManager.RTC_WAKEUP,
                triggerAtMillis,
                pendingIntent,
            )
        } else {
            manager.setExactAndAllowWhileIdle(
                AlarmManager.RTC_WAKEUP,
                triggerAtMillis,
                pendingIntent,
            )
        }
    }

    private fun getRegisteredIds(): Set<String> {
        return HashSet(registry.getStringSet(KEY_REGISTERED_IDS, emptySet()) ?: emptySet())
    }

    private fun saveRegisteredIds(ids: Set<String>) {
        registry.edit().putStringSet(KEY_REGISTERED_IDS, HashSet(ids)).apply()
    }

    private fun regularRequestCode(habitId: String): Int =
        HabitNotificationHelper.notificationIdForHabit(habitId) * 10 + 4

    private fun snoozeRequestCode(habitId: String): Int =
        HabitNotificationHelper.notificationIdForHabit(habitId) * 10 + 5

    companion object {
        private const val PREFS_NAME = "habit_alarm_registry"
        private const val KEY_REGISTERED_IDS = "registered_ids"

        private val habitJson = Json {
            ignoreUnknownKeys = true
            encodeDefaults = true
        }

        private val PYTHON_TO_CALENDAR_WEEKDAY = mapOf(
            0 to Calendar.MONDAY,
            1 to Calendar.TUESDAY,
            2 to Calendar.WEDNESDAY,
            3 to Calendar.THURSDAY,
            4 to Calendar.FRIDAY,
            5 to Calendar.SATURDAY,
            6 to Calendar.SUNDAY,
        )

        fun buildSystemClockAlarmIntent(habit: Habit): Intent? {
            val firstTime = effectiveReminderTimes(habit).firstOrNull() ?: return null
            val parts = firstTime.split(":")
            val hour = parts.getOrNull(0)?.toIntOrNull() ?: return null
            val minute = parts.getOrNull(1)?.toIntOrNull() ?: return null

            return Intent(AlarmClock.ACTION_SET_ALARM).apply {
                putExtra(AlarmClock.EXTRA_HOUR, hour)
                putExtra(AlarmClock.EXTRA_MINUTES, minute)
                putExtra(
                    AlarmClock.EXTRA_MESSAGE,
                    habit.reminderMessage.trim().ifEmpty { "${habit.title} (Habit Check-in)" },
                )
                putExtra(AlarmClock.EXTRA_SKIP_UI, false)
                if (habit.frequencyType == "weekdays" && habit.weekdays.isNotEmpty()) {
                    val mappedDays = ArrayList(
                        habit.weekdays.mapNotNull { PYTHON_TO_CALENDAR_WEEKDAY[it] }.distinct(),
                    )
                    if (mappedDays.isNotEmpty()) {
                        putIntegerArrayListExtra(AlarmClock.EXTRA_DAYS, mappedDays)
                    }
                }
            }
        }
    }
}
