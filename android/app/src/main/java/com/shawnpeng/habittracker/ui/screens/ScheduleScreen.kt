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
import com.shawnpeng.habittracker.data.formatFrequencySummary
import com.shawnpeng.habittracker.data.parseHabitColor
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val StatusDoneGreen = Color(0xFF15803D)
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
) {
    var statusFilter by remember { mutableStateOf("todo") }
    var groupBy by remember { mutableStateOf("day") }

    val todayDate = LocalDate.now()
    val isCurrentPeriod = remember(period, anchorDate, todayDate) {
        isAnchorInCurrentPeriod(period = period, anchorDate = anchorDate, todayDate = todayDate)
    }

    val periodTitle = remember(period, anchorDate, isCurrentPeriod) {
        when {
            period == "month" && isCurrentPeriod -> "本月待办"
            period == "month" -> "${anchorDate.year}年${anchorDate.monthValue}月"
            isCurrentPeriod -> "本周待办"
            else -> "周度待办"
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
                    label = { Text("本周") },
                )
                FilterChip(
                    selected = period == "month",
                    onClick = { onSelectPeriod("month") },
                    label = { Text("本月") },
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
                        label = { Text("回到当前") },
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
                    Icon(Icons.Rounded.ChevronLeft, contentDescription = "上一周期")
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
                    Icon(Icons.Rounded.ChevronRight, contentDescription = "下一周期")
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
                            text = "正在加载待办计划...",
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
                        label = { Text("待完成 (${schedule.remainingCount})") },
                    )
                }
                item {
                    FilterChip(
                        selected = statusFilter == "overdue",
                        onClick = { statusFilter = "overdue" },
                        label = { Text("漏卡 (${schedule.overdueCount})") },
                    )
                }
                item {
                    FilterChip(
                        selected = statusFilter == "all",
                        onClick = { statusFilter = "all" },
                        label = { Text("全部 (${schedule.totalScheduled})") },
                    )
                }
                item {
                    FilterChip(
                        selected = groupBy == "day",
                        onClick = { groupBy = "day" },
                        label = { Text("按日期") },
                    )
                }
                item {
                    FilterChip(
                        selected = groupBy == "habit",
                        onClick = { groupBy = "habit" },
                        label = { Text("按习惯") },
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
                    )
                }
            }
        }
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
        schedule.totalScheduled == 0 -> "本周期暂无安排任务"
        schedule.remainingCount > 0 -> "还需完成 ${schedule.remainingCount} 项"
        else -> "本周期任务已全部完成"
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
                            text = "其中漏卡 ${schedule.overdueCount} 项可补卡",
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
    val periodLabel = if (period == "month") "本月" else "本周"
    val (title, subtitle) = when {
        totalScheduled == 0 -> "暂无待办习惯" to "${periodLabel}范围内没有需要打卡的习惯安排"
        statusFilter == "todo" -> "${periodLabel}待办已清零" to "当前所有已安排的打卡任务都已经完成"
        statusFilter == "overdue" -> "没有漏卡记录" to "${periodLabel}过去日期的计划均已完成，继续保持！"
        else -> "暂无匹配记录" to "尝试切换周期或筛选条件查看"
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
                        text = "${summary.completedDays}/${summary.scheduledDays} 天",
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
                        text = "待完成 ${summary.remainingDays} 天",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (summary.overdueDays > 0) {
                        Text(
                            text = "漏卡 ${summary.overdueDays} 天",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Medium,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                    Spacer(modifier = Modifier.weight(1f))
                    if (summary.nextDueDate != null) {
                        Text(
                            text = "下次 ${summary.nextDueDate}",
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
) {
    val dayBadgeText = when {
        day.isToday -> "今天"
        day.isPast -> "已过"
        else -> "计划中"
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
) {
    val habitColor = parseHabitColor(item.color)
    val (statusLabel, statusBg, statusFg) = when (item.status) {
        "completed" -> Triple(
            "已完成",
            StatusDoneGreen.copy(alpha = 0.14f),
            StatusDoneGreen,
        )
        "overdue" -> Triple(
            "漏卡",
            StatusOverdueRed.copy(alpha = 0.14f),
            StatusOverdueRed,
        )
        "today" -> Triple(
            "今日",
            StatusTodayBlue.copy(alpha = 0.14f),
            StatusTodayBlue,
        )
        else -> Triple(
            "计划中",
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
            if (item.targetPerDay > 1 || item.note.isNotBlank()) {
                val detail = buildString {
                    if (item.targetPerDay > 1) {
                        append("进度 ${item.count}/${item.targetPerDay}")
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
                        text = "计划中",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else if (item.targetPerDay <= 1) {
            IconButton(onClick = onPrimaryCheckin) {
                Icon(
                    imageVector = if (item.completed) {
                        Icons.Rounded.CheckCircle
                    } else {
                        Icons.Rounded.RadioButtonUnchecked
                    },
                    contentDescription = if (item.completed) "取消打卡" else "完成打卡",
                    tint = if (item.completed) habitColor else MaterialTheme.colorScheme.outline,
                )
            }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(
                    onClick = onDecrementCheckin,
                    enabled = item.count > 0,
                    modifier = Modifier.size(34.dp),
                ) {
                    Icon(
                        imageVector = Icons.Rounded.RemoveCircleOutline,
                        contentDescription = "减少一次",
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
                        contentDescription = "增加一次",
                        tint = habitColor,
                        modifier = Modifier.size(20.dp),
                    )
                }
            }
        }
    }
}
