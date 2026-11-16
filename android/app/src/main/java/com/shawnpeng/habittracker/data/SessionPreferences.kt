package com.shawnpeng.habittracker.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json

const val DEFAULT_EMULATOR_URL = "http://10.0.2.2:8000"

private val Context.habitDataStore by preferencesDataStore(name = "habit_tracker_session")

private val prefJson = Json {
    ignoreUnknownKeys = true
    encodeDefaults = true
}

class SessionPreferences(private val context: Context) {

    private object Keys {
        val SERVER_URL = stringPreferencesKey("server_url")
        val JWT_TOKEN = stringPreferencesKey("jwt_token")
        val REMINDERS_MUTED = booleanPreferencesKey("reminders_muted")
        val CACHED_REMINDER_HABITS = stringPreferencesKey("cached_reminder_habits")
        val COMPLETED_TODAY_DATE = stringPreferencesKey("completed_today_date")
        val COMPLETED_TODAY_IDS = stringPreferencesKey("completed_today_ids")
    }

    suspend fun getServerUrl(): String {
        return context.habitDataStore.data
            .map { prefs -> prefs[Keys.SERVER_URL] ?: DEFAULT_EMULATOR_URL }
            .first()
    }

    suspend fun setServerUrl(url: String) {
        context.habitDataStore.edit { prefs ->
            prefs[Keys.SERVER_URL] = url
        }
    }

    suspend fun getToken(): String? {
        return context.habitDataStore.data
            .map { prefs -> prefs[Keys.JWT_TOKEN] }
            .first()
    }

    suspend fun setToken(token: String) {
        context.habitDataStore.edit { prefs ->
            prefs[Keys.JWT_TOKEN] = token
        }
    }

    suspend fun clearToken() {
        context.habitDataStore.edit { prefs ->
            prefs.remove(Keys.JWT_TOKEN)
        }
    }

    suspend fun getRemindersMuted(): Boolean {
        return context.habitDataStore.data
            .map { prefs -> prefs[Keys.REMINDERS_MUTED] ?: false }
            .first()
    }

    suspend fun setRemindersMuted(muted: Boolean) {
        context.habitDataStore.edit { prefs ->
            prefs[Keys.REMINDERS_MUTED] = muted
        }
    }

    suspend fun getCachedReminderHabits(): List<Habit> {
        val raw = context.habitDataStore.data
            .map { prefs -> prefs[Keys.CACHED_REMINDER_HABITS] }
            .first()
            ?: return emptyList()
        return runCatching {
            prefJson.decodeFromString(ListSerializer(Habit.serializer()), raw)
        }.getOrElse { emptyList() }
    }

    suspend fun setCachedReminderHabits(habits: List<Habit>) {
        val encoded = prefJson.encodeToString(ListSerializer(Habit.serializer()), habits)
        context.habitDataStore.edit { prefs ->
            prefs[Keys.CACHED_REMINDER_HABITS] = encoded
        }
    }

    suspend fun getCompletedHabitIdsForDate(dateIso: String): Set<String> {
        val pair = context.habitDataStore.data
            .map { prefs -> prefs[Keys.COMPLETED_TODAY_DATE] to prefs[Keys.COMPLETED_TODAY_IDS] }
            .first()
        if (pair.first != dateIso || pair.second.isNullOrBlank()) return emptySet()
        return runCatching {
            prefJson.decodeFromString(ListSerializer(String.serializer()), pair.second!!).toSet()
        }.getOrElse { emptySet() }
    }

    suspend fun setCompletedHabitIdsForDate(dateIso: String, ids: Set<String>) {
        val encoded = prefJson.encodeToString(ListSerializer(String.serializer()), ids.toList())
        context.habitDataStore.edit { prefs ->
            prefs[Keys.COMPLETED_TODAY_DATE] = dateIso
            prefs[Keys.COMPLETED_TODAY_IDS] = encoded
        }
    }

    suspend fun markHabitCompletedForDate(
        dateIso: String,
        habitId: String,
        completed: Boolean = true,
    ) {
        context.habitDataStore.edit { prefs ->
            val currentIds = if (prefs[Keys.COMPLETED_TODAY_DATE] == dateIso) {
                prefs[Keys.COMPLETED_TODAY_IDS]?.let { raw ->
                    runCatching {
                        prefJson.decodeFromString(ListSerializer(String.serializer()), raw)
                    }.getOrElse { emptyList() }
                } ?: emptyList()
            } else {
                emptyList()
            }
            val updated = currentIds.toMutableSet()
            if (completed) {
                updated.add(habitId)
            } else {
                updated.remove(habitId)
            }
            prefs[Keys.COMPLETED_TODAY_DATE] = dateIso
            prefs[Keys.COMPLETED_TODAY_IDS] = prefJson.encodeToString(
                ListSerializer(String.serializer()),
                updated.toList(),
            )
        }
    }

    suspend fun clearReminderCache() {
        context.habitDataStore.edit { prefs ->
            prefs.remove(Keys.CACHED_REMINDER_HABITS)
            prefs.remove(Keys.COMPLETED_TODAY_DATE)
            prefs.remove(Keys.COMPLETED_TODAY_IDS)
        }
    }
}
