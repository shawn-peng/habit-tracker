package com.shawnpeng.habittracker.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

const val DEFAULT_EMULATOR_URL = "http://10.0.2.2:8000"

private val Context.habitDataStore by preferencesDataStore(name = "habit_tracker_session")

class SessionPreferences(private val context: Context) {

    private object Keys {
        val SERVER_URL = stringPreferencesKey("server_url")
        val JWT_TOKEN = stringPreferencesKey("jwt_token")
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
}
