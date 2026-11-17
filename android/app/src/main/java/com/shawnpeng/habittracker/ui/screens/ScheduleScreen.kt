package com.shawnpeng.habittracker.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AddCircleOutline
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ChevronLeft
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.DoneAll
import androidx.compose.material.icons.rounded.EditNote
import androidx.compose.material.icons.rounded.PlayCircleOutline
import androidx.compose.material.icons.rounded.RadioButtonUnchecked
import androidx.compose.material.icons.rounded.RemoveCircleOutline
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Today
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.HabitPeriodSummary
import com.shawnpeng.habittracker.data.PeriodSchedule
import com.shawnpeng.habittracker.data.ScheduleDay
import com.shawnpeng.habittracker.data.ScheduleHabitItem
import com.shawnpeng.habittracker.data.effectiveReminderTimes
import com.shawnpeng.habittracker.data.formatCompanionReminderBadge
import com.shawnpeng.habittracker.data.formatFrequencySummary
import com.shawnpeng.habittracker.data.formatHabitModeSummary
import com.shawnpeng.habittracker.data.formatReminderBadge
import com.shawnpeng.habittracker.data.parseHabitColor
import com.shawnpeng.habittracker.ui.components.CheckinEditDialog
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Locale

private val StatusDoneGreen = Color(0xFF15803D)
private val StatusLateAmber = Color(0xFFB45309)
private val StatusTodayBlue = Color(0xFF1D4ED8)
private val StatusOverdueRed = Color(0xFFB91C1C)

@Composable
fun ScheduleScreen(
    period: String,
    anchorDate: LocalDate,
    schedule: PeriodSchedule?,
    onSelectPeriod: (String) -> Unit,
    onShiftPeriod: (Long) -> Unit,
    onResetCurrent: () -> Unit,
    onPrimaryCheckin: (ScheduleHabitItem) -> Unit,
    onDecrementCheckin: (ScheduleHabitItem) -> Unit,
    onEditCheckin: (ScheduleHabitItem, String, Int, String) -> Unit,
) {
    var statusFilter by remember { mutableStateOf("todo") }
    var groupBy by remember { mutableStateOf("day") }
    var editingItem by remember { mutableStateOf<ScheduleHabitItem?>(null) }

    val todayDate = LocalDate.now()
    val isCurrentPeriod = remember(period, anchorDate, todayDate) {
        isAnchorInCurrentPeriod(period = period, anchorDate = anchorDate, todayDate = todayDate)
    }

    val periodTitle = remember(period, anchorDate, isCurrentPeriod) {
        when {
            period == "month" && isCurrentPeriod -> "This Month"
            period == "month" -> anchorDate.format(DateTimeFormatter.ofPattern("MMMM yyyy", Locale.ENGLISH))
            isCurrentPeriod -> "This Week"
            else -> "Weekly Plan"
        }
    }

    val periodRangeText = schedule?.let { "${it.startDate} ~ ${it.endDate}" }
        ?: anchorDate.format(DateTimeFormatter.ISO_LOCAL_DATE)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 92.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilterChip(
                    selected = period == "week",
                    onClick = { onSelectPeriod("week") },
                    label = { Text("Week") },
                )
                FilterChip(
                    selected = period == "month",
                    onClick = { onSelectPeriod("month") },
                    label = { Text("Month") },
                )
                Spacer(modifier = Modifier.weight(1f))
                if (!isCurrentPeriod) {
                    AssistChip(
                        onClick = onResetCurrent,
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Rounded.Today,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp),
                            )
                        },
                        label = { Text("Current") },
                    )
                }
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = { onShiftPeriod(-1) }) {
                    Icon(Icons.Rounded.ChevronLeft, contentDescription = "Previous period")
                }
                Column(
                    modifier = Modifier.weight(1f),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        text = periodTitle,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = periodRangeText,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                IconButton(onClick = { onShiftPeriod(1) }) {
                    Icon(Icons.Rounded.ChevronRight, contentDescription = "Next period")
                }
            }
        }

        if (schedule == null) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(28.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.CalendarMonth,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(36.dp),
                        )
                        Text(
                            text = "Loading schedule...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            return@LazyColumn
        }

        item {
            PeriodSummaryCard(schedule = schedule)
        }

        item {
            LazyRow(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                item {
                    FilterChip(
                        selected = statusFilter == "todo",
                        onClick = { statusFilter = "todo" },
                        label = { Text("To Do (${schedule.remainingCount})") },
                    )
                }
                item {
                    FilterChip(
                        selected = statusFilter == "overdue",
                        onClick = { statusFilter = "overdue" },
                        label = { Text("Missed (${schedule.overdueCount})") },
                    )
                }
                item {
                    FilterChip(
                        selected = statusFilter == "all",
                        onClick = { statusFilter = "all" },
                        label = { Text("All (${schedule.totalScheduled})") },
                    )
                }
                item {
                    FilterChip(
                        selected = groupBy == "day",
                        onClick = { groupBy = "day" },
                        label = { Text("By Day") },
                    )
                }
                item {
                    FilterChip(
                        selected = groupBy == "habit",
                        onClick = { groupBy = "habit" },
                        label = { Text("By Habit") },
                    )
                }
            }
        }

        if (groupBy == "habit") {
            val filteredSummaries = schedule.habitSummaries.filter { summary ->
                when (statusFilter) {
                    "todo" -> summary.remainingDays > 0
                    "overdue" -> summary.overdueDays > 0
                    else -> summary.scheduledDays > 0
                }
            }
            if (filteredSummaries.isEmpty()) {
                item {
                    ScheduleEmptyStateCard(
                        statusFilter = statusFilter,
                        period = period,
                        totalScheduled = schedule.totalScheduled,
                    )
                }
            } else {
                items(filteredSummaries, key = { it.habitId }) { summary ->
                    ScheduleHabitSummaryCard(summary = summary)
                }
            }
        } else {
            val daySections = schedule.days.mapNotNull { day ->
                val matchingItems = day.items.filter { item ->
                    when (statusFilter) {
                        "todo" -> item.status == "today" || item.status == "upcoming"
                        "overdue" -> item.status == "overdue"
                        else -> true
                    }
                }
                if (matchingItems.isEmpty()) null else day to matchingItems
            }
            if (daySections.isEmpty()) {
                item {
                    ScheduleEmptyStateCard(
                        statusFilter = statusFilter,
                        period = period,
                        totalScheduled = schedule.totalScheduled,
                    )
                }
            } else {
                items(daySections, key = { (day, _) -> day.date }) { (day, matchingItems) ->
                    ScheduleDayCard(
                        day = day,
                        items = matchingItems,
                        onPrimaryCheckin = onPrimaryCheckin,
                        onDecrementCheckin = onDecrementCheckin,
                        onEditItem = { editingItem = it },
                    )
                }
            }
        }
    }

    editingItem?.let { target ->
        CheckinEditDialog(
            title = target.title,
            dateIso = target.date,
            scheduled = true,
            targetPerDay = target.targetPerDay,
            initialCount = target.count,
            initialCompleted = target.completed,
            initialIsLate = target.isLate,
            initialNote = target.note,
            onDismiss = { editingItem = null },
            onSave = { statusOverride, count, note ->
                onEditCheckin(target, statusOverride, count, note)
                editingItem = null
            },
        )
    }
}

private fun isAnchorInCurrentPeriod(
    period: String,
    anchorDate: LocalDate,
    todayDate: LocalDate,
): Boolean {
    if (period == "month") {
        return anchorDate.year == todayDate.year && anchorDate.month == todayDate.month
    }
    val todayMonday = todayDate.minusDays((todayDate.dayOfWeek.value - 1).toLong())
    val anchorMonday = anchorDate.minusDays((anchorDate.dayOfWeek.value - 1).toLong())
    return todayMonday == anchorMonday
}

@Composable
private fun PeriodSummaryCard(schedule: PeriodSchedule) {
    val progressFraction = if (schedule.totalScheduled > 0) {
        (schedule.completedCount.toFloat() / schedule.totalScheduled.toFloat()).coerceIn(0f, 1f)
    } else {
        0f
    }
    val rateLabel = if (schedule.completionRate % 1.0 == 0.0) {
        "${schedule.completionRate.toInt()}%"
    } else {
        String.format(Locale.US, "%.1f%%", schedule.completionRate)
    }
    val headline = when {
        schedule.totalScheduled == 0 -> "No habits scheduled this period"
        schedule.remainingCount > 0 -> "${schedule.remainingCount} remaining"
        else -> "All scheduled tasks complete"
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
        ),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(
                        text = headline,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                    if (schedule.overdueCount > 0) {
                        Text(
                            text = "${schedule.overdueCount} missed (make-up available)",
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.Medium,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                }
                Text(
                    text = "${schedule.completedCount}/${schedule.totalScheduled} ($rateLabel)",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
            }
            LinearProgressIndicator(
                progress = { progressFraction },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(8.dp)
                    .clip(RoundedCornerShape(4.dp)),
                color = MaterialTheme.colorScheme.primary,
                trackColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.55f),
                strokeCap = StrokeCap.Round,
            )
        }
    }
}

@Composable
private fun ScheduleEmptyStateCard(
    statusFilter: String,
    period: String,
    totalScheduled: Int,
) {
    val periodLabel = if (period == "month") "this month" else "this week"
    val (title, subtitle) = when {
        totalScheduled == 0 -> "No habits scheduled" to "No habits are due $periodLabel"
        statusFilter == "todo" -> "All caught up!" to "All scheduled check-ins $periodLabel are complete"
        statusFilter == "overdue" -> "No missed days" to "Past scheduled items $periodLabel are all complete — keep it up!"
        else -> "No matching tasks" to "Try switching period or filter options"
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(
                imageVector = Icons.Rounded.DoneAll,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(36.dp),
            )
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center,
            )
            Text(
                text = subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
    }
}

@Composable
private fun ScheduleHabitSummaryCard(summary: HabitPeriodSummary) {
    val habitColor = parseHabitColor(summary.color)
    val progress = if (summary.scheduledDays > 0) {
        (summary.completedDays.toFloat() / summary.scheduledDays.toFloat()).coerceIn(0f, 1f)
    } else {
        0f
    }
    val frequencyText = formatFrequencySummary(
        frequencyType = summary.frequencyType,
        weekdays = summary.weekdays,
        monthlyMode = summary.monthlyMode,
        monthlyDay = summary.monthlyDay,
        monthlyWeek = summary.monthlyWeek,
        monthlyWeekday = summary.monthlyWeekday,
    )

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .width(5.dp)
                    .height(60.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(habitColor),
            )
            Spacer(modifier = Modifier.width(12.dp))
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = summary.title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "${summary.completedDays}/${summary.scheduledDays} d",
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        color = habitColor,
                    )
                }
                Text(
                    text = frequencyText,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                val summaryEffectiveTimes = effectiveReminderTimes(
                    mode = summary.mode,
                    reminderEnabled = summary.reminderEnabled,
                    reminderTimes = summary.reminderTimes,
                    remindTime = summary.remindTime,
                )
                val summaryReminderBadge = if (summaryEffectiveTimes.isEmpty()) {
                    null
                } else {
                    formatReminderBadge(
                        enabled = true,
                        times = summaryEffectiveTimes,
                        mode = summary.reminderMode,
                    )
                }
                if (summaryReminderBadge != null) {
                    Surface(
                        shape = RoundedCornerShape(6.dp),
                        color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.7f),
                    ) {
                        Text(
                            text = summaryReminderBadge,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSecondaryContainer,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                        )
                    }
                }
                if (summary.description.isNotBlank()) {
                    Text(
                        text = summary.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                LinearProgressIndicator(
                    progress = { progress },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(6.dp)
                        .clip(RoundedCornerShape(3.dp)),
                    color = habitColor,
                    trackColor = MaterialTheme.colorScheme.surfaceVariant,
                    strokeCap = StrokeCap.Round,
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = "${summary.remainingDays}d left",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (summary.overdueDays > 0) {
                        Text(
                            text = "${summary.overdueDays}d missed",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Medium,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                    Spacer(modifier = Modifier.weight(1f))
                    if (summary.nextDueDate != null) {
                        Text(
                            text = "Next: ${summary.nextDueDate}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ScheduleDayCard(
    day: ScheduleDay,
    items: List<ScheduleHabitItem>,
    onPrimaryCheckin: (ScheduleHabitItem) -> Unit,
    onDecrementCheckin: (ScheduleHabitItem) -> Unit,
    onEditItem: (ScheduleHabitItem) -> Unit,
) {
    val dayBadgeText = when {
        day.isToday -> "Today"
        day.isPast -> "Past"
        else -> "Upcoming"
    }
    val dayBadgeBg = when {
        day.isToday -> MaterialTheme.colorScheme.primaryContainer
        day.isPast -> MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.7f)
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
    val dayBadgeFg = when {
        day.isToday -> MaterialTheme.colorScheme.onPrimaryContainer
        day.isPast -> MaterialTheme.colorScheme.onErrorContainer
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = "${day.date} ${day.weekdayLabel}",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                )
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = dayBadgeBg,
                ) {
                    Text(
                        text = dayBadgeText,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.SemiBold,
                        color = dayBadgeFg,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                    )
                }
                Spacer(modifier = Modifier.weight(1f))
                Text(
                    text = "${day.completedCount}/${day.scheduledCount}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            items.forEachIndexed { index, item ->
                if (index > 0) {
                    HorizontalDivider(
                        color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.45f),
                    )
                }
                ScheduleDayHabitRow(
                    item = item,
                    canCheckin = !day.isFuture,
                    onPrimaryCheckin = { onPrimaryCheckin(item) },
                    onDecrementCheckin = { onDecrementCheckin(item) },
                    onEdit = { onEditItem(item) },
                )
            }
        }
    }
}

@Composable
private fun ScheduleDayHabitRow(
    item: ScheduleHabitItem,
    canCheckin: Boolean,
    onPrimaryCheckin: () -> Unit,
    onDecrementCheckin: () -> Unit,
    onEdit: () -> Unit,
) {
    val habitColor = parseHabitColor(item.color)
    val nowTime = LocalTime.now()
    val nowHhmm = "${nowTime.hour.toString().padStart(2, '0')}:${nowTime.minute.toString().padStart(2, '0')}"
    val todayIso = LocalDate.now().format(DateTimeFormatter.ISO_LOCAL_DATE)
    val needsStrictStart = item.mode == "strict" &&
        item.date == todayIso &&
        !item.completed &&
        !item.startedOnTime &&
        (item.forceStartTime == null || nowHhmm <= item.forceStartTime)
    val modeSummary = formatHabitModeSummary(
        mode = item.mode,
        remindTime = item.remindTime,
        forceStartTime = item.forceStartTime,
        forceEndTime = item.forceEndTime,
        reminderMode = item.reminderMode,
    )
    val (statusLabel, statusBg, statusFg) = when (item.status) {
        "completed" -> if (item.isLate) {
            Triple("Overdue Make-up", StatusLateAmber.copy(alpha = 0.14f), StatusLateAmber)
        } else {
            Triple("Done", StatusDoneGreen.copy(alpha = 0.14f), StatusDoneGreen)
        }
        "overdue" -> Triple(
            "Missed",
            StatusOverdueRed.copy(alpha = 0.14f),
            StatusOverdueRed,
        )
        "today" -> Triple(
            "Due today",
            StatusTodayBlue.copy(alpha = 0.14f),
            StatusTodayBlue,
        )
        else -> Triple(
            "Upcoming",
            MaterialTheme.colorScheme.surfaceVariant,
            MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .width(4.dp)
                .height(36.dp)
                .clip(RoundedCornerShape(3.dp))
                .background(habitColor),
        )
        Spacer(modifier = Modifier.width(10.dp))
        Column(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(
                    text = item.title,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                    textDecoration = if (item.completed) TextDecoration.LineThrough else TextDecoration.None,
                    color = if (item.completed) {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    } else {
                        MaterialTheme.colorScheme.onSurface
                    },
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                Surface(
                    shape = RoundedCornerShape(6.dp),
                    color = statusBg,
                ) {
                    Text(
                        text = statusLabel,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Medium,
                        color = statusFg,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                    )
                }
            }
            if (modeSummary != null || item.targetPerDay > 1 || item.note.isNotBlank()) {
                val detail = buildString {
                    if (modeSummary != null) {
                        append(modeSummary)
                    }
                    if (item.targetPerDay > 1) {
                        if (isNotEmpty()) append(" · ")
                        append("${item.count}/${item.targetPerDay}")
                    }
                    if (item.note.isNotBlank()) {
                        if (isNotEmpty()) append(" · ")
                        append(item.note)
                    }
                }
                Text(
                    text = detail,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            val itemReminderBadge = formatCompanionReminderBadge(
                mode = item.mode,
                reminderEnabled = item.reminderEnabled,
                reminderTimes = item.reminderTimes,
                remindTime = item.remindTime,
                reminderMode = item.reminderMode,
            )
            if (itemReminderBadge != null) {
                Surface(
                    shape = RoundedCornerShape(6.dp),
                    color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.7f),
                ) {
                    Text(
                        text = itemReminderBadge,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSecondaryContainer,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                    )
                }
            }
        }
        Spacer(modifier = Modifier.width(6.dp))
        if (!canCheckin) {
            Surface(
                shape = RoundedCornerShape(10.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Schedule,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(14.dp),
                    )
                    Text(
                        text = "Upcoming",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(
                    onClick = onEdit,
                    modifier = Modifier.size(34.dp),
                ) {
                    Icon(
                        imageVector = Icons.Rounded.EditNote,
                        contentDescription = "Edit check-in",
                        tint = if (item.note.isNotBlank()) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        modifier = Modifier.size(20.dp),
                    )
                }
                if (needsStrictStart || item.targetPerDay <= 1) {
                    IconButton(onClick = onPrimaryCheckin) {
                        Icon(
                            imageVector = when {
                                needsStrictStart -> Icons.Rounded.PlayCircleOutline
                                item.completed -> Icons.Rounded.CheckCircle
                                else -> Icons.Rounded.RadioButtonUnchecked
                            },
                            contentDescription = when {
                                needsStrictStart -> "Start Execution"
                                item.completed -> "Undo check-in"
                                else -> "Check in"
                            },
                            tint = when {
                                needsStrictStart -> MaterialTheme.colorScheme.primary
                                item.isLate -> StatusLateAmber
                                item.completed -> habitColor
                                else -> MaterialTheme.colorScheme.outline
                            },
                        )
                    }
                } else {
                    IconButton(
                        onClick = onDecrementCheckin,
                        enabled = item.count > 0,
                        modifier = Modifier.size(34.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.RemoveCircleOutline,
                            contentDescription = "Decrease count",
                            modifier = Modifier.size(20.dp),
                        )
                    }
                    Text(
                        text = "${item.count}/${item.targetPerDay}",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(horizontal = 2.dp),
                    )
                    IconButton(
                        onClick = onPrimaryCheckin,
                        modifier = Modifier.size(34.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.AddCircleOutline,
                            contentDescription = "Increase count",
                            tint = habitColor,
                            modifier = Modifier.size(20.dp),
                        )
                    }
                }
            }
        }
    }
}
