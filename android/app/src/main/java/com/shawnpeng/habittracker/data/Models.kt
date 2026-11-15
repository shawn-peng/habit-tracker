package com.shawnpeng.habittracker.data

import androidx.compose.ui.graphics.Color
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class RegisterRequest(
    val name: String,
    val email: String,
    val password: String,
)

@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
)

@Serializable
data class UserPublic(
    val id: String,
    val name: String,
    val email: String,
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
    val user: UserPublic,
)

@Serializable
data class Habit(
    val id: String,
    val title: String,
    val description: String = "",
    val color: String = "#6366F1",
    val icon: String = "check_circle",
    @SerialName("frequency_type") val frequencyType: String = "daily",
    val weekdays: List<Int> = listOf(0, 1, 2, 3, 4, 5, 6),
    @SerialName("target_per_day") val targetPerDay: Int = 1,
    val archived: Boolean = false,
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class HabitToday(
    val id: String,
    val title: String,
    val description: String = "",
    val color: String = "#6366F1",
    val icon: String = "check_circle",
    @SerialName("frequency_type") val frequencyType: String = "daily",
    val weekdays: List<Int> = listOf(0, 1, 2, 3, 4, 5, 6),
    @SerialName("target_per_day") val targetPerDay: Int = 1,
    val archived: Boolean = false,
    @SerialName("created_at") val createdAt: String = "",
    val date: String,
    @SerialName("scheduled_today") val scheduledToday: Boolean = true,
    val count: Int = 0,
    val completed: Boolean = false,
    val note: String = "",
    @SerialName("current_streak") val currentStreak: Int = 0,
    @SerialName("best_streak") val bestStreak: Int = 0,
)

@Serializable
data class HabitCreateRequest(
    val title: String,
    val description: String = "",
    val color: String = "#6366F1",
    val icon: String = "check_circle",
    @SerialName("frequency_type") val frequencyType: String = "daily",
    val weekdays: List<Int> = listOf(0, 1, 2, 3, 4, 5, 6),
    @SerialName("target_per_day") val targetPerDay: Int = 1,
)

@Serializable
data class HabitUpdateRequest(
    val title: String? = null,
    val description: String? = null,
    val color: String? = null,
    val icon: String? = null,
    @SerialName("frequency_type") val frequencyType: String? = null,
    val weekdays: List<Int>? = null,
    @SerialName("target_per_day") val targetPerDay: Int? = null,
    val archived: Boolean? = null,
)

@Serializable
data class CheckinRequest(
    val date: String,
    val action: String = "increment",
    val count: Int? = null,
    val note: String? = null,
)

@Serializable
data class DailyActivityPoint(
    val date: String,
    @SerialName("weekday_label") val weekdayLabel: String,
    @SerialName("scheduled_count") val scheduledCount: Int = 0,
    @SerialName("completed_count") val completedCount: Int = 0,
)

@Serializable
data class HabitStreakStat(
    @SerialName("habit_id") val habitId: String,
    val title: String,
    val color: String = "#6366F1",
    @SerialName("current_streak") val currentStreak: Int = 0,
    @SerialName("best_streak") val bestStreak: Int = 0,
    @SerialName("completion_rate_30d") val completionRate30d: Double = 0.0,
    @SerialName("total_completions") val totalCompletions: Int = 0,
)

@Serializable
data class StatsSummary(
    @SerialName("active_habits_count") val activeHabitsCount: Int = 0,
    @SerialName("completed_today") val completedToday: Int = 0,
    @SerialName("scheduled_today") val scheduledToday: Int = 0,
    @SerialName("best_active_streak") val bestActiveStreak: Int = 0,
    @SerialName("overall_completion_rate_30d") val overallCompletionRate30d: Double = 0.0,
    @SerialName("last_7_days") val last7Days: List<DailyActivityPoint> = emptyList(),
    @SerialName("habit_stats") val habitStats: List<HabitStreakStat> = emptyList(),
)

data class ColorSwatch(
    val hex: String,
    val label: String,
)

val HABIT_COLOR_SWATCHES = listOf(
    ColorSwatch("#6366F1", "靛蓝"),
    ColorSwatch("#10B981", "翠绿"),
    ColorSwatch("#F59E0B", "琥珀"),
    ColorSwatch("#EC4899", "玫红"),
    ColorSwatch("#0EA5E9", "天蓝"),
    ColorSwatch("#8B5CF6", "紫罗兰"),
)

val WEEKDAY_SHORT_LABELS = listOf("一", "二", "三", "四", "五", "六", "日")
val WEEKDAY_FULL_LABELS = listOf("周一", "周二", "周三", "周四", "周五", "周六", "周日")

private val DEFAULT_HABIT_COLOR = Color(0xFF6366F1)

/**
 * Pure-Kotlin hex color parser so unit tests run on JVM without android.graphics.Color.
 */
fun parseHabitColor(hex: String): Color {
    val cleaned = hex.trim().removePrefix("#")
    val parsed = cleaned.toLongOrNull(16) ?: return DEFAULT_HABIT_COLOR
    return when (cleaned.length) {
        6 -> Color(0xFF000000L or parsed)
        8 -> Color(parsed)
        else -> DEFAULT_HABIT_COLOR
    }
}

fun formatFrequencySummary(frequencyType: String, weekdays: List<Int>): String {
    if (frequencyType == "daily" || weekdays.toSet().size == 7) {
        return "每天"
    }
    val labels = weekdays
        .filter { it in 0..6 }
        .distinct()
        .sorted()
        .map { WEEKDAY_FULL_LABELS[it] }
    return if (labels.isEmpty()) "自定义" else labels.joinToString("、")
}
