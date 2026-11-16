package com.shawnpeng.habittracker.notifications

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.shawnpeng.habittracker.data.ApiException
import com.shawnpeng.habittracker.data.CheckinRequest
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.data.HabitApiClient
import com.shawnpeng.habittracker.data.SessionPreferences
import com.shawnpeng.habittracker.data.isHabitScheduledOnDate
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json

class HabitAlarmReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        val appContext = context.applicationContext
        val habitId = intent.getStringExtra(EXTRA_HABIT_ID).orEmpty()
        val habitJsonRaw = intent.getStringExtra(EXTRA_HABIT_JSON)
        val timeLabel = intent.getStringExtra(EXTRA_TIME_LABEL).orEmpty()
        val isSnooze = intent.getBooleanExtra(EXTRA_IS_SNOOZE, false)

        if (action == ACTION_DISMISS) {
            if (habitId.isNotBlank()) {
                HabitNotificationHelper.cancelHabitNotification(appContext, habitId)
            }
            return
        }

        val pendingResult = goAsync()
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                val prefs = SessionPreferences(appContext)
                val scheduler = AndroidHabitAlarmScheduler(appContext)
                val cachedHabits = prefs.getCachedReminderHabits()
                val decodedHabit = habitJsonRaw?.let { raw ->
                    runCatching { json.decodeFromString(Habit.serializer(), raw) }.getOrNull()
                }
                val targetHabit = decodedHabit ?: cachedHabits.firstOrNull { it.id == habitId }
                val effectiveHabitId = habitId.ifBlank { targetHabit?.id.orEmpty() }
                val todayIso = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE)

                when (action) {
                    ACTION_TRIGGER -> {
                        val muted = prefs.getRemindersMuted()
                        val completedIds = prefs.getCompletedHabitIdsForDate(todayIso)
                        if (!muted && targetHabit != null) {
                            val shouldNotify = isSnooze || (
                                effectiveHabitId !in completedIds &&
                                    isHabitScheduledOnDate(targetHabit, LocalDate.now())
                                )
                            if (shouldNotify) {
                                HabitNotificationHelper.showHabitNotification(
                                    context = appContext,
                                    habit = targetHabit,
                                    timeLabel = timeLabel,
                                )
                            }
                        }
                        val habitsToSync = cachedHabits.ifEmpty { listOfNotNull(targetHabit) }
                        if (habitsToSync.isNotEmpty()) {
                            scheduler.syncAllHabits(
                                habits = habitsToSync,
                                completedTodayIds = completedIds,
                                muted = muted,
                            )
                        }
                    }

                    ACTION_SNOOZE -> {
                        if (effectiveHabitId.isNotBlank()) {
                            HabitNotificationHelper.cancelHabitNotification(
                                appContext,
                                effectiveHabitId,
                            )
                        }
                        if (targetHabit != null) {
                            scheduler.scheduleSnooze(
                                habit = targetHabit,
                                snoozeMinutes = targetHabit.reminderSnoozeMinutes,
                            )
                        }
                    }

                    ACTION_CHECKIN -> {
                        if (effectiveHabitId.isNotBlank()) {
                            HabitNotificationHelper.cancelHabitNotification(
                                appContext,
                                effectiveHabitId,
                            )
                        }
                        val token = prefs.getToken()
                        if (!token.isNullOrBlank() && effectiveHabitId.isNotBlank()) {
                            val nowTime = LocalTime.now()
                            val nowHhmm =
                                "${nowTime.hour.toString().padStart(2, '0')}:${nowTime.minute.toString().padStart(2, '0')}"
                            val apiAction = if ((targetHabit?.targetPerDay ?: 1) <= 1) {
                                "toggle"
                            } else {
                                "increment"
                            }
                            val authedApi = HabitApiClient(initialBaseUrl = prefs.getServerUrl()).apply {
                                authToken = token
                            }
                            val result = runCatching {
                                try {
                                    authedApi.checkinHabit(
                                        habitId = effectiveHabitId,
                                        request = CheckinRequest(
                                            date = todayIso,
                                            action = apiAction,
                                            clientToday = todayIso,
                                            clientTime = nowHhmm,
                                        ),
                                    )
                                } catch (exc: ApiException) {
                                    if (exc.statusCode == 400 && targetHabit?.mode == "strict") {
                                        authedApi.checkinHabit(
                                            habitId = effectiveHabitId,
                                            request = CheckinRequest(
                                                date = todayIso,
                                                action = "start",
                                                clientToday = todayIso,
                                                clientTime = nowHhmm,
                                            ),
                                        )
                                    } else {
                                        throw exc
                                    }
                                }
                            }.getOrNull()
                            if (result != null) {
                                prefs.markHabitCompletedForDate(
                                    dateIso = todayIso,
                                    habitId = effectiveHabitId,
                                    completed = result.completed,
                                )
                            }
                        }
                        val updatedCompleted = prefs.getCompletedHabitIdsForDate(todayIso)
                        val muted = prefs.getRemindersMuted()
                        if (cachedHabits.isNotEmpty()) {
                            scheduler.syncAllHabits(
                                habits = cachedHabits,
                                completedTodayIds = updatedCompleted,
                                muted = muted,
                            )
                        }
                    }
                }
            } finally {
                pendingResult.finish()
            }
        }
    }

    companion object {
        const val ACTION_TRIGGER = "com.shawnpeng.habittracker.ACTION_HABIT_REMINDER"
        const val ACTION_SNOOZE = "com.shawnpeng.habittracker.ACTION_HABIT_SNOOZE"
        const val ACTION_DISMISS = "com.shawnpeng.habittracker.ACTION_HABIT_DISMISS"
        const val ACTION_CHECKIN = "com.shawnpeng.habittracker.ACTION_HABIT_CHECKIN"

        const val EXTRA_HABIT_ID = "extra_habit_id"
        const val EXTRA_HABIT_JSON = "extra_habit_json"
        const val EXTRA_TIME_LABEL = "extra_time_label"
        const val EXTRA_IS_SNOOZE = "extra_is_snooze"

        private val json = Json {
            ignoreUnknownKeys = true
            encodeDefaults = true
        }
    }
}
