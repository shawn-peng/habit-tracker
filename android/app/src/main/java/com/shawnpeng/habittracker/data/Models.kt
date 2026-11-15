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
    @SerialName("monthly_mode") val monthlyMode: String = "from_start",
    @SerialName("monthly_day") val monthlyDay: Int = 1,
    @SerialName("monthly_week") val monthlyWeek: Int = 1,
    @SerialName("monthly_weekday") val monthlyWeekday: Int = 0,
    @SerialName("target_per_day") val targetPerDay: Int = 1,
    @SerialName("target_slo") val targetSlo: Double = 85.0,
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
    @SerialName("monthly_mode") val monthlyMode: String = "from_start",
    @SerialName("monthly_day") val monthlyDay: Int = 1,
    @SerialName("monthly_week") val monthlyWeek: Int = 1,
    @SerialName("monthly_weekday") val monthlyWeekday: Int = 0,
    @SerialName("target_per_day") val targetPerDay: Int = 1,
    @SerialName("target_slo") val targetSlo: Double = 85.0,
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
    @SerialName("monthly_mode") val monthlyMode: String = "from_start",
    @SerialName("monthly_day") val monthlyDay: Int = 1,
    @SerialName("monthly_week") val monthlyWeek: Int = 1,
    @SerialName("monthly_weekday") val monthlyWeekday: Int = 0,
    @SerialName("target_per_day") val targetPerDay: Int = 1,
    @SerialName("target_slo") val targetSlo: Double = 85.0,
)

@Serializable
data class HabitUpdateRequest(
    val title: String? = null,
    val description: String? = null,
    val color: String? = null,
    val icon: String? = null,
    @SerialName("frequency_type") val frequencyType: String? = null,
    val weekdays: List<Int>? = null,
    @SerialName("monthly_mode") val monthlyMode: String? = null,
    @SerialName("monthly_day") val monthlyDay: Int? = null,
    @SerialName("monthly_week") val monthlyWeek: Int? = null,
    @SerialName("monthly_weekday") val monthlyWeekday: Int? = null,
    @SerialName("target_per_day") val targetPerDay: Int? = null,
    @SerialName("target_slo") val targetSlo: Double? = null,
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
    @SerialName("frequency_type") val frequencyType: String = "daily",
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

@Serializable
data class SliTrendPoint(
    val label: String = "",
    @SerialName("start_date") val startDate: String = "",
    @SerialName("end_date") val endDate: String = "",
    @SerialName("scheduled_count") val scheduledCount: Int = 0,
    @SerialName("completed_count") val completedCount: Int = 0,
    val sli: Double = 0.0,
    @SerialName("has_activity") val hasActivity: Boolean = false,
)

@Serializable
data class WeekdaySliPoint(
    val weekday: Int = 0,
    val label: String = "",
    @SerialName("scheduled_count") val scheduledCount: Int = 0,
    @SerialName("completed_count") val completedCount: Int = 0,
    val sli: Double = 0.0,
)

@Serializable
data class HabitSliItem(
    @SerialName("habit_id") val habitId: String = "",
    val title: String = "",
    val color: String = "#6366F1",
    @SerialName("target_slo") val targetSlo: Double = 85.0,
    @SerialName("current_sli") val currentSli: Double = 100.0,
    @SerialName("sli_7d") val sli7d: Double = 100.0,
    @SerialName("sli_30d") val sli30d: Double = 100.0,
    @SerialName("sli_90d") val sli90d: Double = 100.0,
    @SerialName("sli_delta") val sliDelta: Double = 0.0,
    @SerialName("slo_met") val sloMet: Boolean = true,
    val status: String = "healthy",
    @SerialName("scheduled_days") val scheduledDays: Int = 0,
    @SerialName("completed_days") val completedDays: Int = 0,
    @SerialName("missed_days") val missedDays: Int = 0,
    @SerialName("error_budget_allowed_days") val errorBudgetAllowedDays: Double = 0.0,
    @SerialName("error_budget_used_days") val errorBudgetUsedDays: Int = 0,
    @SerialName("error_budget_remaining_days") val errorBudgetRemainingDays: Double = 0.0,
    @SerialName("error_budget_remaining_pct") val errorBudgetRemainingPct: Double = 100.0,
    @SerialName("burn_rate") val burnRate: Double = 0.0,
    @SerialName("burn_rate_7d") val burnRate7d: Double = 0.0,
    @SerialName("current_streak") val currentStreak: Int = 0,
)

@Serializable
data class SliDashboard(
    @SerialName("window_days") val windowDays: Int = 30,
    @SerialName("active_habits_count") val activeHabitsCount: Int = 0,
    @SerialName("overall_sli") val overallSli: Double = 0.0,
    @SerialName("overall_target_slo") val overallTargetSlo: Double = 85.0,
    @SerialName("overall_status") val overallStatus: String = "no_data",
    @SerialName("healthy_count") val healthyCount: Int = 0,
    @SerialName("warning_count") val warningCount: Int = 0,
    @SerialName("breached_count") val breachedCount: Int = 0,
    @SerialName("overall_error_budget_allowed_days") val overallErrorBudgetAllowedDays: Double = 0.0,
    @SerialName("overall_error_budget_used_days") val overallErrorBudgetUsedDays: Int = 0,
    @SerialName("overall_error_budget_remaining_days") val overallErrorBudgetRemainingDays: Double = 0.0,
    @SerialName("overall_error_budget_remaining_pct") val overallErrorBudgetRemainingPct: Double = 100.0,
    @SerialName("overall_burn_rate") val overallBurnRate: Double = 0.0,
    @SerialName("overall_burn_rate_7d") val overallBurnRate7d: Double = 0.0,
    @SerialName("weakest_weekday") val weakestWeekday: String? = null,
    @SerialName("weakest_weekday_sli") val weakestWeekdaySli: Double? = null,
    @SerialName("top_burn_habit_title") val topBurnHabitTitle: String? = null,
    @SerialName("top_burn_rate") val topBurnRate: Double? = null,
    val trend: List<SliTrendPoint> = emptyList(),
    @SerialName("weekday_sli") val weekdaySli: List<WeekdaySliPoint> = emptyList(),
    val habits: List<HabitSliItem> = emptyList(),
)

@Serializable
data class ScheduleHabitItem(
    @SerialName("habit_id") val habitId: String,
    val title: String,
    val description: String = "",
    val color: String = "#16A34A",
    val icon: String = "check_circle",
    @SerialName("frequency_type") val frequencyType: String = "daily",
    val weekdays: List<Int> = listOf(0, 1, 2, 3, 4, 5, 6),
    @SerialName("monthly_mode") val monthlyMode: String = "from_start",
    @SerialName("monthly_day") val monthlyDay: Int = 1,
    @SerialName("monthly_week") val monthlyWeek: Int = 1,
    @SerialName("monthly_weekday") val monthlyWeekday: Int = 0,
    @SerialName("target_per_day") val targetPerDay: Int = 1,
    val date: String,
    val count: Int = 0,
    val completed: Boolean = false,
    val note: String = "",
    val status: String = "upcoming",
)

@Serializable
data class ScheduleDay(
    val date: String,
    val weekday: Int,
    @SerialName("weekday_label") val weekdayLabel: String,
    @SerialName("is_today") val isToday: Boolean = false,
    @SerialName("is_past") val isPast: Boolean = false,
    @SerialName("is_future") val isFuture: Boolean = false,
    @SerialName("scheduled_count") val scheduledCount: Int = 0,
    @SerialName("completed_count") val completedCount: Int = 0,
    @SerialName("pending_count") val pendingCount: Int = 0,
    val items: List<ScheduleHabitItem> = emptyList(),
)

@Serializable
data class HabitPeriodSummary(
    @SerialName("habit_id") val habitId: String,
    val title: String,
    val description: String = "",
    val color: String = "#16A34A",
    val icon: String = "check_circle",
    @SerialName("frequency_type") val frequencyType: String = "daily",
    val weekdays: List<Int> = listOf(0, 1, 2, 3, 4, 5, 6),
    @SerialName("monthly_mode") val monthlyMode: String = "from_start",
    @SerialName("monthly_day") val monthlyDay: Int = 1,
    @SerialName("monthly_week") val monthlyWeek: Int = 1,
    @SerialName("monthly_weekday") val monthlyWeekday: Int = 0,
    @SerialName("target_per_day") val targetPerDay: Int = 1,
    @SerialName("scheduled_days") val scheduledDays: Int = 0,
    @SerialName("completed_days") val completedDays: Int = 0,
    @SerialName("remaining_days") val remainingDays: Int = 0,
    @SerialName("overdue_days") val overdueDays: Int = 0,
    @SerialName("next_due_date") val nextDueDate: String? = null,
)

@Serializable
data class PeriodSchedule(
    val period: String = "week",
    @SerialName("start_date") val startDate: String,
    @SerialName("end_date") val endDate: String,
    val today: String,
    @SerialName("total_scheduled") val totalScheduled: Int = 0,
    @SerialName("completed_count") val completedCount: Int = 0,
    @SerialName("remaining_count") val remainingCount: Int = 0,
    @SerialName("overdue_count") val overdueCount: Int = 0,
    @SerialName("completion_rate") val completionRate: Double = 0.0,
    @SerialName("habit_summaries") val habitSummaries: List<HabitPeriodSummary> = emptyList(),
    val days: List<ScheduleDay> = emptyList(),
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
val MONTHLY_WEEK_OPTIONS = listOf(
    1 to "第 1 周",
    2 to "第 2 周",
    3 to "第 3 周",
    4 to "第 4 周",
    5 to "第 5 周",
    -1 to "最后一周",
)

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

fun formatFrequencySummary(
    frequencyType: String,
    weekdays: List<Int> = listOf(0, 1, 2, 3, 4, 5, 6),
    monthlyMode: String = "from_start",
    monthlyDay: Int = 1,
    monthlyWeek: Int = 1,
    monthlyWeekday: Int = 0,
): String {
    if (frequencyType == "monthly") {
        return when (monthlyMode) {
            "from_end" -> if (monthlyDay == 1) "每月最后一天" else "每月倒数第 $monthlyDay 天"
            "nth_weekday" -> {
                val weekLabel = if (monthlyWeek == -1) "最后一周" else "第 $monthlyWeek 周"
                val weekdayLabel = WEEKDAY_FULL_LABELS[monthlyWeekday.mod(7)]
                "每月$weekLabel · $weekdayLabel"
            }
            else -> "每月第 $monthlyDay 天"
        }
    }
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
