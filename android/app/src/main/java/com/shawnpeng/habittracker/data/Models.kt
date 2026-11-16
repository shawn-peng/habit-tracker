package com.shawnpeng.habittracker.data

import androidx.compose.ui.graphics.Color
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.YearMonth
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
    @SerialName("email_verified") val emailVerified: Boolean = true,
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
    val user: UserPublic,
)

@Serializable
data class RegisterResponse(
    val message: String,
    val email: String,
    @SerialName("verification_required") val verificationRequired: Boolean = true,
    @SerialName("expires_in_minutes") val expiresInMinutes: Int = 15,
    @SerialName("dev_verification_code") val devVerificationCode: String? = null,
)

@Serializable
data class VerifyEmailRequest(
    val email: String,
    val code: String,
)

@Serializable
data class ResendVerificationRequest(
    val email: String,
)

@Serializable
data class ForgotPasswordRequest(
    val email: String,
)

@Serializable
data class ForgotPasswordResponse(
    val message: String,
    @SerialName("expires_in_minutes") val expiresInMinutes: Int = 15,
    @SerialName("dev_reset_code") val devResetCode: String? = null,
)

@Serializable
data class ResetPasswordRequest(
    val email: String,
    val code: String,
    @SerialName("new_password") val newPassword: String,
)

@Serializable
data class ChangePasswordRequest(
    @SerialName("current_password") val currentPassword: String,
    @SerialName("new_password") val newPassword: String,
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
    val mode: String = "free",
    @SerialName("remind_time") val remindTime: String? = null,
    @SerialName("force_start_time") val forceStartTime: String? = null,
    @SerialName("force_end_time") val forceEndTime: String? = null,
    val archived: Boolean = false,
    @SerialName("reminder_enabled") val reminderEnabled: Boolean = false,
    @SerialName("reminder_times") val reminderTimes: List<String> = emptyList(),
    @SerialName("reminder_mode") val reminderMode: String = "notification",
    @SerialName("reminder_snooze_minutes") val reminderSnoozeMinutes: Int = 10,
    @SerialName("reminder_message") val reminderMessage: String = "",
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
    val mode: String = "free",
    @SerialName("remind_time") val remindTime: String? = null,
    @SerialName("force_start_time") val forceStartTime: String? = null,
    @SerialName("force_end_time") val forceEndTime: String? = null,
    val archived: Boolean = false,
    @SerialName("reminder_enabled") val reminderEnabled: Boolean = false,
    @SerialName("reminder_times") val reminderTimes: List<String> = emptyList(),
    @SerialName("reminder_mode") val reminderMode: String = "notification",
    @SerialName("reminder_snooze_minutes") val reminderSnoozeMinutes: Int = 10,
    @SerialName("reminder_message") val reminderMessage: String = "",
    @SerialName("created_at") val createdAt: String = "",
    val date: String,
    @SerialName("scheduled_today") val scheduledToday: Boolean = true,
    val count: Int = 0,
    val completed: Boolean = false,
    val note: String = "",
    @SerialName("current_streak") val currentStreak: Int = 0,
    @SerialName("best_streak") val bestStreak: Int = 0,
    @SerialName("day_status") val dayStatus: String = "pending",
    @SerialName("violation_reason") val violationReason: String? = null,
    @SerialName("started_at_time") val startedAtTime: String? = null,
    @SerialName("started_on_time") val startedOnTime: Boolean = false,
    @SerialName("is_late") val isLate: Boolean = false,
    @SerialName("can_start") val canStart: Boolean = false,
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
    val mode: String = "free",
    @SerialName("remind_time") val remindTime: String? = null,
    @SerialName("force_start_time") val forceStartTime: String? = null,
    @SerialName("force_end_time") val forceEndTime: String? = null,
    @SerialName("reminder_enabled") val reminderEnabled: Boolean = false,
    @SerialName("reminder_times") val reminderTimes: List<String> = emptyList(),
    @SerialName("reminder_mode") val reminderMode: String = "notification",
    @SerialName("reminder_snooze_minutes") val reminderSnoozeMinutes: Int = 10,
    @SerialName("reminder_message") val reminderMessage: String = "",
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
    val mode: String? = null,
    @SerialName("remind_time") val remindTime: String? = null,
    @SerialName("force_start_time") val forceStartTime: String? = null,
    @SerialName("force_end_time") val forceEndTime: String? = null,
    val archived: Boolean? = null,
    @SerialName("reminder_enabled") val reminderEnabled: Boolean? = null,
    @SerialName("reminder_times") val reminderTimes: List<String>? = null,
    @SerialName("reminder_mode") val reminderMode: String? = null,
    @SerialName("reminder_snooze_minutes") val reminderSnoozeMinutes: Int? = null,
    @SerialName("reminder_message") val reminderMessage: String? = null,
)

@Serializable
data class CheckinRequest(
    val date: String,
    val action: String = "increment",
    val count: Int? = null,
    val note: String? = null,
    @SerialName("client_today") val clientToday: String? = null,
    @SerialName("client_time") val clientTime: String? = null,
)

@Serializable
data class DailyActivityPoint(
    val date: String,
    @SerialName("weekday_label") val weekdayLabel: String,
    @SerialName("scheduled_count") val scheduledCount: Int = 0,
    @SerialName("completed_count") val completedCount: Int = 0,
    @SerialName("late_count") val lateCount: Int = 0,
)

@Serializable
data class HabitStreakStat(
    @SerialName("habit_id") val habitId: String,
    val title: String,
    val color: String = "#6366F1",
    @SerialName("frequency_type") val frequencyType: String = "daily",
    val mode: String = "free",
    @SerialName("current_streak") val currentStreak: Int = 0,
    @SerialName("best_streak") val bestStreak: Int = 0,
    @SerialName("completion_rate_30d") val completionRate30d: Double = 0.0,
    @SerialName("total_completions") val totalCompletions: Int = 0,
    @SerialName("late_completions") val lateCompletions: Int = 0,
)

@Serializable
data class StatsSummary(
    @SerialName("active_habits_count") val activeHabitsCount: Int = 0,
    @SerialName("completed_today") val completedToday: Int = 0,
    @SerialName("scheduled_today") val scheduledToday: Int = 0,
    @SerialName("late_today") val lateToday: Int = 0,
    @SerialName("violated_today") val violatedToday: Int = 0,
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
    val mode: String = "free",
    @SerialName("remind_time") val remindTime: String? = null,
    @SerialName("force_start_time") val forceStartTime: String? = null,
    @SerialName("force_end_time") val forceEndTime: String? = null,
    @SerialName("started_on_time") val startedOnTime: Boolean = false,
    @SerialName("is_late") val isLate: Boolean = false,
    val date: String,
    val count: Int = 0,
    val completed: Boolean = false,
    val note: String = "",
    val status: String = "upcoming",
    @SerialName("reminder_enabled") val reminderEnabled: Boolean = false,
    @SerialName("reminder_times") val reminderTimes: List<String> = emptyList(),
    @SerialName("reminder_mode") val reminderMode: String = "notification",
    @SerialName("reminder_snooze_minutes") val reminderSnoozeMinutes: Int = 10,
    @SerialName("reminder_message") val reminderMessage: String = "",
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
    val mode: String = "free",
    @SerialName("remind_time") val remindTime: String? = null,
    @SerialName("force_start_time") val forceStartTime: String? = null,
    @SerialName("force_end_time") val forceEndTime: String? = null,
    @SerialName("scheduled_days") val scheduledDays: Int = 0,
    @SerialName("completed_days") val completedDays: Int = 0,
    @SerialName("remaining_days") val remainingDays: Int = 0,
    @SerialName("overdue_days") val overdueDays: Int = 0,
    @SerialName("next_due_date") val nextDueDate: String? = null,
    @SerialName("reminder_enabled") val reminderEnabled: Boolean = false,
    @SerialName("reminder_times") val reminderTimes: List<String> = emptyList(),
    @SerialName("reminder_mode") val reminderMode: String = "notification",
    @SerialName("reminder_snooze_minutes") val reminderSnoozeMinutes: Int = 10,
    @SerialName("reminder_message") val reminderMessage: String = "",
)

@Serializable
data class HabitReminderItem(
    @SerialName("habit_id") val habitId: String,
    val title: String,
    val color: String = "#16A34A",
    val icon: String = "check_circle",
    @SerialName("frequency_type") val frequencyType: String = "daily",
    @SerialName("scheduled_today") val scheduledToday: Boolean = false,
    @SerialName("completed_today") val completedToday: Boolean = false,
    val count: Int = 0,
    @SerialName("target_per_day") val targetPerDay: Int = 1,
    @SerialName("reminder_enabled") val reminderEnabled: Boolean = false,
    @SerialName("reminder_times") val reminderTimes: List<String> = emptyList(),
    @SerialName("reminder_mode") val reminderMode: String = "notification",
    @SerialName("reminder_snooze_minutes") val reminderSnoozeMinutes: Int = 10,
    @SerialName("reminder_message") val reminderMessage: String = "",
    @SerialName("next_trigger_date") val nextTriggerDate: String? = null,
    @SerialName("next_trigger_time") val nextTriggerTime: String? = null,
    @SerialName("due_today_times") val dueTodayTimes: List<String> = emptyList(),
)

@Serializable
data class RemindersOverview(
    val date: String,
    @SerialName("now_time") val nowTime: String? = null,
    @SerialName("enabled_habits_count") val enabledHabitsCount: Int = 0,
    @SerialName("alarm_habits_count") val alarmHabitsCount: Int = 0,
    @SerialName("notification_habits_count") val notificationHabitsCount: Int = 0,
    @SerialName("scheduled_today_count") val scheduledTodayCount: Int = 0,
    @SerialName("pending_today_triggers") val pendingTodayTriggers: Int = 0,
    val items: List<HabitReminderItem> = emptyList(),
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

const val MAX_REMINDER_TIMES = 12
val REMINDER_TIME_PRESETS = listOf("07:30", "09:00", "12:30", "18:00", "21:30")
val REMINDER_SNOOZE_OPTIONS = listOf(5, 10, 15, 30, 60)

fun HabitToday.toHabit(): Habit = Habit(
    id = id,
    title = title,
    description = description,
    color = color,
    icon = icon,
    frequencyType = frequencyType,
    weekdays = weekdays,
    monthlyMode = monthlyMode,
    monthlyDay = monthlyDay,
    monthlyWeek = monthlyWeek,
    monthlyWeekday = monthlyWeekday,
    targetPerDay = targetPerDay,
    targetSlo = targetSlo,
    mode = mode,
    remindTime = remindTime,
    forceStartTime = forceStartTime,
    forceEndTime = forceEndTime,
    archived = archived,
    reminderEnabled = reminderEnabled,
    reminderTimes = reminderTimes,
    reminderMode = reminderMode,
    reminderSnoozeMinutes = reminderSnoozeMinutes,
    reminderMessage = reminderMessage,
    createdAt = createdAt,
)

fun normalizeReminderTime(raw: String): String? {
    val trimmed = raw.trim()
    val parts = trimmed.split(":")
    if (parts.size != 2) return null
    val hour = parts[0].toIntOrNull() ?: return null
    val minute = parts[1].toIntOrNull() ?: return null
    if (hour !in 0..23 || minute !in 0..59) return null
    return "${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}"
}

fun normalizeReminderTimes(
    rawTimes: List<String>,
    maxTimes: Int = MAX_REMINDER_TIMES,
): List<String> {
    val result = mutableListOf<String>()
    val seen = HashSet<String>()
    for (raw in rawTimes) {
        val norm = normalizeReminderTime(raw) ?: continue
        if (seen.add(norm)) {
            result.add(norm)
            if (result.size >= maxTimes) break
        }
    }
    return result.sorted()
}

fun formatReminderBadge(
    enabled: Boolean,
    times: List<String>,
    mode: String,
): String? {
    if (!enabled) return null
    val normalized = times.mapNotNull { normalizeReminderTime(it) }.distinct().sorted()
    if (normalized.isEmpty()) return null
    val prefix = if (mode == "alarm") "⏰" else "🔔"
    return if (normalized.size <= 2) {
        "$prefix ${normalized.joinToString(", ")}"
    } else {
        "$prefix ${normalized[0]}, ${normalized[1]} (+${normalized.size - 2})"
    }
}

fun formatReminderBadge(habit: Habit): String? =
    formatReminderBadge(habit.reminderEnabled, habit.reminderTimes, habit.reminderMode)

fun scheduledMonthlyDay(
    year: Int,
    month: Int,
    monthlyMode: String = "from_start",
    monthlyDay: Int = 1,
    monthlyWeek: Int = 1,
    monthlyWeekday: Int = 0,
): Int {
    val ym = YearMonth.of(year, month)
    val daysInMonth = ym.lengthOfMonth()
    val firstWeekday = LocalDate.of(year, month, 1).dayOfWeek.value - 1
    return when (monthlyMode) {
        "from_end" -> {
            val offset = monthlyDay.coerceIn(1, 31)
            (daysInMonth - offset + 1).coerceAtLeast(1)
        }
        "nth_weekday" -> {
            val targetWeekday = ((monthlyWeekday % 7) + 7) % 7
            if (monthlyWeek == -1) {
                val lastWeekday = (firstWeekday + daysInMonth - 1) % 7
                val back = (lastWeekday - targetWeekday + 7) % 7
                daysInMonth - back
            } else {
                val nth = monthlyWeek.coerceIn(1, 5)
                val firstOcc = 1 + ((targetWeekday - firstWeekday + 7) % 7)
                var day = firstOcc + (nth - 1) * 7
                if (day > daysInMonth) {
                    day -= 7
                }
                day
            }
        }
        else -> monthlyDay.coerceIn(1, 31).coerceAtMost(daysInMonth)
    }
}

fun isHabitScheduledOnDate(
    frequencyType: String,
    weekdays: List<Int>,
    monthlyMode: String,
    monthlyDay: Int,
    monthlyWeek: Int,
    monthlyWeekday: Int,
    date: LocalDate,
): Boolean {
    return when (frequencyType) {
        "daily" -> true
        "monthly" -> date.dayOfMonth == scheduledMonthlyDay(
            year = date.year,
            month = date.monthValue,
            monthlyMode = monthlyMode,
            monthlyDay = monthlyDay,
            monthlyWeek = monthlyWeek,
            monthlyWeekday = monthlyWeekday,
        )
        else -> {
            val dow = date.dayOfWeek.value - 1
            val active = if (weekdays.isEmpty()) listOf(0, 1, 2, 3, 4, 5, 6) else weekdays
            dow in active
        }
    }
}

fun isHabitScheduledOnDate(habit: Habit, date: LocalDate): Boolean =
    isHabitScheduledOnDate(
        frequencyType = habit.frequencyType,
        weekdays = habit.weekdays,
        monthlyMode = habit.monthlyMode,
        monthlyDay = habit.monthlyDay,
        monthlyWeek = habit.monthlyWeek,
        monthlyWeekday = habit.monthlyWeekday,
        date = date,
    )

fun computeNextTriggerDateTime(
    habit: Habit,
    fromDateTime: LocalDateTime,
    completedToday: Boolean = false,
): LocalDateTime? {
    if (habit.archived || !habit.reminderEnabled) return null
    val times = normalizeReminderTimes(habit.reminderTimes)
    if (times.isEmpty()) return null
    val startDate = fromDateTime.toLocalDate()
    for (offset in 0..90) {
        val candidateDate = startDate.plusDays(offset.toLong())
        if (!isHabitScheduledOnDate(habit, candidateDate)) continue
        if (offset == 0 && completedToday) continue
        for (hhmm in times) {
            val trigger = candidateDate.atTime(LocalTime.parse(hhmm))
            if (trigger.isAfter(fromDateTime)) {
                return trigger
            }
        }
    }
    return null
}

data class HabitModeOption(
    val key: String,
    val label: String,
    val shortLabel: String,
    val hint: String,
)

val HABIT_MODE_OPTIONS = listOf(
    HabitModeOption(
        key = "free",
        label = "自由打卡（默认）",
        shortLabel = "自由模式",
        hint = "无时间限制，当天任意时刻完成即算准时完成。",
    ),
    HabitModeOption(
        key = "strict",
        label = "模式1：严格管控",
        shortLabel = "模式1·严格管控",
        hint = "需满足 开始提醒时间 < 强制执行时间 < 强制完成时间；必须先点击「开始执行」。",
    ),
    HabitModeOption(
        key = "window",
        label = "模式2：弹性时间窗",
        shortLabel = "模式2·弹性时间窗",
        hint = "到开始提醒时间提示，在强制完成时间前完成即算准时。",
    ),
    HabitModeOption(
        key = "reminder",
        label = "模式3：定时提醒",
        shortLabel = "模式3·定时提醒",
        hint = "到达开始提醒时间触发提示，不设超时违规，完成即算准时。",
    ),
)

data class ValidatedHabitModeTimes(
    val remindTime: String? = null,
    val forceStartTime: String? = null,
    val forceEndTime: String? = null,
    val errorMessage: String? = null,
)

fun validateHabitModeTimes(
    mode: String,
    remindRaw: String?,
    startRaw: String?,
    endRaw: String?,
): ValidatedHabitModeTimes {
    if (mode == "free") {
        return ValidatedHabitModeTimes()
    }
    val remindClean = remindRaw.orEmpty().trim()
    if (remindClean.isEmpty()) {
        return ValidatedHabitModeTimes(errorMessage = "请输入开始提醒时间 (HH:MM)")
    }
    val remind = normalizeReminderTime(remindClean)
        ?: return ValidatedHabitModeTimes(errorMessage = "开始提醒时间格式需为 24 小时制 HH:MM")

    if (mode == "reminder") {
        return ValidatedHabitModeTimes(remindTime = remind)
    }

    val endClean = endRaw.orEmpty().trim()
    if (endClean.isEmpty()) {
        return ValidatedHabitModeTimes(errorMessage = "请输入强制完成时间 (HH:MM)")
    }
    val end = normalizeReminderTime(endClean)
        ?: return ValidatedHabitModeTimes(errorMessage = "强制完成时间格式需为 24 小时制 HH:MM")

    if (mode == "window") {
        return if (remind >= end) {
            ValidatedHabitModeTimes(errorMessage = "开始提醒时间必须早于强制完成时间")
        } else {
            ValidatedHabitModeTimes(remindTime = remind, forceEndTime = end)
        }
    }

    if (mode == "strict") {
        val startClean = startRaw.orEmpty().trim()
        if (startClean.isEmpty()) {
            return ValidatedHabitModeTimes(errorMessage = "请输入强制执行时间 (HH:MM)")
        }
        val start = normalizeReminderTime(startClean)
            ?: return ValidatedHabitModeTimes(errorMessage = "强制执行时间格式需为 24 小时制 HH:MM")
        if (!(remind < start && start < end)) {
            return ValidatedHabitModeTimes(
                errorMessage = "模式1需满足：开始提醒时间 < 强制执行时间 < 强制完成时间",
            )
        }
        return ValidatedHabitModeTimes(
            remindTime = remind,
            forceStartTime = start,
            forceEndTime = end,
        )
    }

    return ValidatedHabitModeTimes(errorMessage = "不支持的模式: $mode")
}

fun formatHabitModeSummary(
    mode: String,
    remindTime: String? = null,
    forceStartTime: String? = null,
    forceEndTime: String? = null,
): String? {
    if (mode == "free") return null
    val option = HABIT_MODE_OPTIONS.firstOrNull { it.key == mode }
    val label = option?.shortLabel ?: mode
    val parts = buildList {
        if (!remindTime.isNullOrBlank()) add("提醒 $remindTime")
        if (mode == "strict" && !forceStartTime.isNullOrBlank()) add("开始 $forceStartTime")
        if ((mode == "strict" || mode == "window") && !forceEndTime.isNullOrBlank()) add("完成 $forceEndTime")
    }
    return if (parts.isEmpty()) label else "$label（${parts.joinToString(" · ")}）"
}

data class LocalHabitStatus(
    val dayStatus: String,
    val violationReason: String? = null,
    val canStart: Boolean = false,
    val isLate: Boolean = false,
)

fun evaluateLocalHabitStatus(
    habit: HabitToday,
    selectedDateIso: String,
    todayIso: String,
    nowHhmm: String,
): LocalHabitStatus {
    val target = habit.targetPerDay.coerceAtLeast(1)
    val completed = habit.completed || habit.count >= target
    if (completed) {
        return if ((habit.mode == "strict" || habit.mode == "window") && habit.isLate) {
            LocalHabitStatus(
                dayStatus = "late_makeup",
                violationReason = habit.violationReason,
                canStart = false,
                isLate = true,
            )
        } else {
            LocalHabitStatus(dayStatus = "on_time")
        }
    }

    if (!habit.scheduledToday || selectedDateIso > todayIso) {
        val status = if (habit.mode == "strict" && habit.startedOnTime) "in_progress" else "pending"
        return LocalHabitStatus(dayStatus = status)
    }

    val isPast = selectedDateIso < todayIso
    return when (habit.mode) {
        "free" -> LocalHabitStatus(dayStatus = "pending")
        "reminder" -> {
            val reminding = !isPast && !habit.remindTime.isNullOrBlank() && nowHhmm >= habit.remindTime
            LocalHabitStatus(dayStatus = if (reminding) "reminding" else "pending")
        }
        "window" -> {
            if (isPast || (!habit.forceEndTime.isNullOrBlank() && nowHhmm > habit.forceEndTime)) {
                LocalHabitStatus(dayStatus = "violation", violationReason = "missed_end")
            } else if (!habit.remindTime.isNullOrBlank() && nowHhmm >= habit.remindTime) {
                LocalHabitStatus(dayStatus = "reminding")
            } else {
                LocalHabitStatus(dayStatus = "pending")
            }
        }
        "strict" -> {
            if (!habit.startedOnTime) {
                if (isPast || (!habit.forceStartTime.isNullOrBlank() && nowHhmm > habit.forceStartTime)) {
                    LocalHabitStatus(dayStatus = "violation", violationReason = "missed_start")
                } else {
                    val reminding = !habit.remindTime.isNullOrBlank() && nowHhmm >= habit.remindTime
                    LocalHabitStatus(
                        dayStatus = if (reminding) "reminding" else "pending",
                        canStart = true,
                    )
                }
            } else if (isPast || (!habit.forceEndTime.isNullOrBlank() && nowHhmm > habit.forceEndTime)) {
                LocalHabitStatus(dayStatus = "violation", violationReason = "missed_end")
            } else {
                LocalHabitStatus(dayStatus = "in_progress")
            }
        }
        else -> LocalHabitStatus(dayStatus = "pending")
    }
}
