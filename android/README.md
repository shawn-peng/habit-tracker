# Habit Tracker — Native Android App (Kotlin + Jetpack Compose)

The native Android client (`android/`) is built with **Kotlin**, **Jetpack Compose**, **Material 3**, **OkHttp**, **Kotlinx Serialization**, and **DataStore Preferences**, connecting directly to the **FastAPI + MongoDB** backend (`backend/`).

## Features

- **Sign In / Create Account & Server URL**: Configurable `Server API URL` (with emulator `http://10.0.2.2:8000` and LAN presets), persistent JWT auto-login, email verification, password reset/change, and automatic session-expiry handling.
- **Today (`Today`)**: Calendar date switching, real-time completion progress bar, single-tap and multi-count habits (`+` / `-`), daily check-in notes, streak badges (`🔥`), and overdue/reminding banners.
- **Schedule (`Schedule`)**: Switch between **Week** and **Month** views, page backward/forward with quick jump to **Current**, filter **To Do** / **Missed** / **All**, toggle **By Day** / **By Habit**, and check in or start execution directly from scheduled items.
- **Habit Management (`Habits`)**: Create and edit habits (title, notes, target count, target SLO, 6 accent colors, Daily / Weekly / Monthly schedules including From Start, From End, and Day X on Week Y rules, and unified Habit Mode & Alert settings), archive/unarchive, toggle archived view, and permanently delete with confirmation.
- **Unified Habit Modes, Reminders & Alarms (`AlarmManager` + Notification Channels)**: Choose `free` (Free Mode — no reminders), `strict` (Mode 1: Remind Time → Force Start → Force End with Start Execution guard and violation detection), `window` (Mode 2: Flexible Window), or `reminder` (Mode 3: Timed Reminder & Alarm with multiple **12-hour AM/PM** times), paired with Notification vs. Ringing Alarm channels, snooze intervals, custom messages, inline notification actions (**Check In** / **Start / Check In** / **Snooze** / **Dismiss**), Reminders Center with one-tap mute, System Clock handoff, and reboot/time-change rescheduling.
- **Statistics (`Stats`)**: Active Best Streak, 30-Day Completion Rate, Today's Score KPIs, Last 7 Days completion chart (with late-makeup indicators), and Habit Streaks Breakdown.
- **Personal SLI & Error Budget (`SLI`)**: SRE reliability analytics (`GET /api/stats/sli`) with `7d / 30d / 90d` windows, per-habit `target_slo` editor, error budget remaining & multi-window burn rates, rolling SLI trend chart, and weekday reliability diagnostics.

## Option 1: Download Prebuilt APK via GitHub Actions

1. Push commits to GitHub — the **`Build Cross-Platform Clients & Test Backend`** workflow automatically runs the `build-android-native` job:
   - `./gradlew testDebugUnitTest`
   - `./gradlew assembleDebug`
2. Open the workflow run under **Actions** and download **`android-native-apk`** from **Artifacts**, then extract `HabitTracker-Android-debug.apk`.

## Option 2: Build & Run Locally with Android Studio

1. Open `android/` in **Android Studio** (Ladybug / Meerkat or newer with bundled JDK 17).
2. Let Gradle sync (or run `.\gradlew.bat testDebugUnitTest assembleDebug` from `android/`).
3. Start the backend server and configure **Server API URL** on the login screen:
   - **Android Emulator**: `http://10.0.2.2:8000` (`usesCleartextTraffic="true"` is enabled for local HTTP debugging).
   - **Physical Device (same Wi-Fi)**: Your PC's LAN IP, e.g., `http://192.168.1.50:8000` (start uvicorn with `--host 0.0.0.0`).
