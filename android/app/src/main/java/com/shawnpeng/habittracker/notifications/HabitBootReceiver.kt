package com.shawnpeng.habittracker.notifications

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.shawnpeng.habittracker.data.SessionPreferences
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class HabitBootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        if (action !in SUPPORTED_ACTIONS) return

        val appContext = context.applicationContext
        val pendingResult = goAsync()
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                val prefs = SessionPreferences(appContext)
                val scheduler = AndroidHabitAlarmScheduler(appContext)
                if (prefs.getToken().isNullOrBlank()) {
                    scheduler.cancelAll()
                    return@launch
                }
                val habits = prefs.getCachedReminderHabits()
                val todayIso = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE)
                val completedIds = prefs.getCompletedHabitIdsForDate(todayIso)
                val muted = prefs.getRemindersMuted()
                scheduler.syncAllHabits(
                    habits = habits,
                    completedTodayIds = completedIds,
                    muted = muted,
                )
            } finally {
                pendingResult.finish()
            }
        }
    }

    companion object {
        private val SUPPORTED_ACTIONS = setOf(
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            Intent.ACTION_TIME_CHANGED,
            Intent.ACTION_TIMEZONE_CHANGED,
        )
    }
}
