package com.shawnpeng.habittracker.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AddCircleOutline
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ChevronLeft
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.EditNote
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.LocalFireDepartment
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.RadioButtonUnchecked
import androidx.compose.material.icons.rounded.RemoveCircleOutline
import androidx.compose.material.icons.rounded.SelfImprovement
import androidx.compose.material.icons.rounded.Today
import androidx.compose.material.icons.rounded.WarningAmber
import androidx.compose.material3.AssistChip
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.HabitToday
import com.shawnpeng.habittracker.data.evaluateLocalHabitStatus
import com.shawnpeng.habittracker.data.extractHabitCreatedDate
import com.shawnpeng.habittracker.data.formatCompanionReminderBadge
import com.shawnpeng.habittracker.data.formatFrequencySummary
import com.shawnpeng.habittracker.data.formatHabitModeSummary
import com.shawnpeng.habittracker.data.formatTime12h
import com.shawnpeng.habittracker.data.localDateToUtcPickerMillis
import com.shawnpeng.habittracker.data.parseHabitColor
import com.shawnpeng.habittracker.data.utcPickerMillisToLocalDate
import com.shawnpeng.habittracker.ui.components.CheckinEditDialog
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun TodayScreen(
    selectedDate: LocalDate,
    habits: List<HabitToday>,
    onShiftDate: (Long) -> Unit,
    onSelectDate: (LocalDate) -> Unit,
    onJumpToday: () -> Unit,
    onStartExecution: (HabitToday) -> Unit,
    onPrimaryCheckin: (HabitToday) -> Unit,
    onDecrementCheckin: (HabitToday) -> Unit,
    onEditCheckin: (HabitToday, String, Int, String) -> Unit,
) {
    val todayDate = LocalDate.now()
    val todayIso = todayDate.format(DateTimeFormatter.ISO_LOCAL_DATE)
    val selectedIso = selectedDate.format(DateTimeFormatter.ISO_LOCAL_DATE)
    val nowTime = LocalTime.now()
    val nowHhmm = "${nowTime.hour.toString().padStart(2, '0')}:${nowTime.minute.toString().padStart(2, '0')}"

    val earliestCreated = remember(habits, todayDate) {
        habits.mapNotNull { extractHabitCreatedDate(it.createdDate, it.createdAt, todayDate) }.minOrNull()
    }
    val canStepPrev = earliestCreated == null || selectedDate.isAfter(earliestCreated)

    val isToday = selectedDate == todayDate
    val scheduledItems = remember(habits) { habits.filter { it.scheduledToday } }
    val extraItems = remember(habits) { habits.filter { !it.scheduledToday } }
    val progressItems = remember(scheduledItems, selectedDate, todayDate) {
        scheduledItems.filter { h ->
            h.canEdit && (extractHabitCreatedDate(h.createdDate, h.createdAt, todayDate)?.let { !selectedDate.isBefore(it) } ?: true)
        }
    }

    val evalById = remember(progressItems, selectedIso, todayIso, nowHhmm) {
        progressItems.associate { it.id to evaluateLocalHabitStatus(it, selectedIso, todayIso, nowHhmm) }
    }
    val doneCount = progressItems.count { evalById[it.id]?.dayStatus == "on_time" }
    val lateCount = progressItems.count { evalById[it.id]?.dayStatus == "late_makeup" }
    val violationCount = progressItems.count { evalById[it.id]?.dayStatus == "violation" }
    val remindingTitles = progressItems.filter { evalById[it.id]?.dayStatus == "reminding" }.map { it.title }
    val violatedTitles = progressItems.filter { evalById[it.id]?.dayStatus == "violation" }.map { it.title }
    val totalScheduled = progressItems.size
    val progressFraction = if (totalScheduled > 0) doneCount.toFloat() / totalScheduled.toFloat() else 0f

    var editTargetHabit by remember { mutableStateOf<HabitToday?>(null) }
    var showDatePicker by remember { mutableStateOf(false) }

    val dateFormatter = remember {
        DateTimeFormatter.ofPattern("EEE, MMM d, yyyy", Locale.ENGLISH)
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 92.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(
                        onClick = { if (canStepPrev) onShiftDate(-1) },
                        enabled = canStepPrev,
                    ) {
                        Icon(Icons.Rounded.ChevronLeft, contentDescription = "Previous day")
                    }
                    Column(
                        modifier = Modifier.clickable { showDatePicker = true },
                    ) {
                        Text(
                            text = if (isToday) "Today" else selectedDate.format(dateFormatter),
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = selectedDate.format(DateTimeFormatter.ISO_LOCAL_DATE),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    IconButton(
                        onClick = { onShiftDate(1) },
                        enabled = !isToday,
                    ) {
                        Icon(Icons.Rounded.ChevronRight, contentDescription = "Next day")
                    }
                    IconButton(onClick = { showDatePicker = true }) {
                        Icon(Icons.Rounded.CalendarMonth, contentDescription = "Jump to date")
                    }
                }

                if (!isToday) {
                    AssistChip(
                        onClick = onJumpToday,
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Rounded.Today,
                                contentDescription = null,
                                modifier = Modifier.size(16.dp),
                            )
                        },
                        label = { Text("Today") },
                    )
                }
            }
        }

        item {
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
                        Text(
                            text = "Daily Routine Progress",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                        )
                        Text(
                            text = "$doneCount / $totalScheduled completed",
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }

                    LinearProgressIndicator(
                        progress = { progressFraction },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(10.dp)
                            .clip(RoundedCornerShape(5.dp)),
                        color = MaterialTheme.colorScheme.primary,
                        trackColor = MaterialTheme.colorScheme.surface,
                        strokeCap = StrokeCap.Round,
                    )

                    if (lateCount > 0 || violationCount > 0) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (lateCount > 0) {
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = Color(0xFFFEF3C7),
                                ) {
                                    Text(
                                        text = "Overdue Make-up: $lateCount (excluded)",
                                        style = MaterialTheme.typography.labelSmall,
                                        fontWeight = FontWeight.SemiBold,
                                        color = Color(0xFFB45309),
                                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                                    )
                                }
                            }
                            if (violationCount > 0) {
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = MaterialTheme.colorScheme.errorContainer,
                                ) {
                                    Text(
                                        text = "Violations: $violationCount",
                                        style = MaterialTheme.typography.labelSmall,
                                        fontWeight = FontWeight.SemiBold,
                                        color = MaterialTheme.colorScheme.onErrorContainer,
                                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        if (violatedTitles.isNotEmpty() || remindingTitles.isNotEmpty()) {
            item {
                val hasViolation = violatedTitles.isNotEmpty()
                val bannerText = buildList {
                    if (violatedTitles.isNotEmpty()) {
                        add("⚠️ Overdue (make-up available): ${violatedTitles.take(3).joinToString(", ")}")
                    }
                    if (remindingTitles.isNotEmpty()) {
                        add("🔔 Reminding now: ${remindingTitles.take(3).joinToString(", ")}")
                    }
                }.joinToString("\n")
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = if (hasViolation) {
                            MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.7f)
                        } else {
                            Color(0xFFFEF3C7)
                        },
                    ),
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 14.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Icon(
                            imageVector = if (hasViolation) {
                                Icons.Rounded.WarningAmber
                            } else {
                                Icons.Rounded.NotificationsActive
                            },
                            contentDescription = null,
                            tint = if (hasViolation) {
                                MaterialTheme.colorScheme.error
                            } else {
                                Color(0xFFD97706)
                            },
                            modifier = Modifier.size(20.dp),
                        )
                        Text(
                            text = bannerText,
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.Medium,
                            color = if (hasViolation) {
                                MaterialTheme.colorScheme.onErrorContainer
                            } else {
                                Color(0xFF92400E)
                            },
                        )
                    }
                }
            }
        }

        if (scheduledItems.isEmpty() && extraItems.isEmpty()) {
            item {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(36.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.SelfImprovement,
                            contentDescription = null,
                            modifier = Modifier.size(48.dp),
                            tint = MaterialTheme.colorScheme.outline,
                        )
                        Text(
                            text = "No habits yet — tap + below to create your first daily routine!",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            textAlign = TextAlign.Center,
                        )
                    }
                }
            }
        } else {
            items(scheduledItems, key = { it.id }) { habit ->
                TodayHabitCard(
                    habit = habit,
                    todayIso = todayIso,
                    nowHhmm = nowHhmm,
                    onStartExecution = { onStartExecution(habit) },
                    onPrimaryCheckin = { onPrimaryCheckin(habit) },
                    onDecrementCheckin = { onDecrementCheckin(habit) },
                    onOpenEdit = { editTargetHabit = habit },
                )
            }

            if (extraItems.isNotEmpty()) {
                item {
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Unscheduled Today (Optional)",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                items(extraItems, key = { "extra_${it.id}" }) { habit ->
                    TodayHabitCard(
                        habit = habit,
                        todayIso = todayIso,
                        nowHhmm = nowHhmm,
                        onStartExecution = { onStartExecution(habit) },
                        onPrimaryCheckin = { onPrimaryCheckin(habit) },
                        onDecrementCheckin = { onDecrementCheckin(habit) },
                        onOpenEdit = { editTargetHabit = habit },
                    )
                }
            }
        }
    }

    if (showDatePicker) {
        val rawMinYear = earliestCreated?.year ?: (todayDate.year - 1)
        val minYear = minOf(rawMinYear, todayDate.year)
        val datePickerState = rememberDatePickerState(
            initialSelectedDateMillis = localDateToUtcPickerMillis(selectedDate),
            yearRange = minYear..todayDate.year,
            selectableDates = object : SelectableDates {
                override fun isSelectableDate(utcTimeMillis: Long): Boolean {
                    val d = utcPickerMillisToLocalDate(utcTimeMillis)
                    return !d.isAfter(todayDate) && (earliestCreated == null || !d.isBefore(earliestCreated))
                }

                override fun isSelectableYear(year: Int): Boolean = year in minYear..todayDate.year
            },
        )
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        datePickerState.selectedDateMillis?.let { millis ->
                            var chosen = utcPickerMillisToLocalDate(millis)
                            if (chosen.isAfter(todayDate)) chosen = todayDate
                            if (earliestCreated != null && chosen.isBefore(earliestCreated)) chosen = earliestCreated
                            onSelectDate(chosen)
                        }
                        showDatePicker = false
                    },
                ) {
                    Text("OK")
                }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) {
                    Text("Cancel")
                }
            },
        ) {
            DatePicker(state = datePickerState)
        }
    }

    editTargetHabit?.let { targetHabit ->
        CheckinEditDialog(
            title = targetHabit.title,
            dateIso = selectedIso,
            scheduled = targetHabit.scheduledToday,
            targetPerDay = targetHabit.targetPerDay,
            initialCount = targetHabit.count,
            initialCompleted = targetHabit.completed,
            initialIsLate = targetHabit.isLate,
            initialNote = targetHabit.note,
            onDismiss = { editTargetHabit = null },
            onSave = { statusOverride, count, note ->
                onEditCheckin(targetHabit, statusOverride, count, note)
                editTargetHabit = null
            },
        )
    }
}

@Composable
private fun TodayHabitCard(
    habit: HabitToday,
    todayIso: String,
    nowHhmm: String,
    onStartExecution: () -> Unit,
    onPrimaryCheckin: () -> Unit,
    onDecrementCheckin: () -> Unit,
    onOpenEdit: () -> Unit,
) {
    val accentColor = parseHabitColor(habit.color)
    val todayDate = remember(todayIso) { LocalDate.parse(todayIso) }
    val targetDate = remember(habit.date) { LocalDate.parse(habit.date) }
    val createdLocal = remember(habit.createdDate, habit.createdAt, todayDate) {
        extractHabitCreatedDate(habit.createdDate, habit.createdAt, todayDate)
    }
    val isHabitEditable = habit.canEdit && (createdLocal == null || !targetDate.isBefore(createdLocal))
    val localStatus = evaluateLocalHabitStatus(
        habit = habit.copy(canEdit = isHabitEditable),
        selectedDateIso = habit.date,
        todayIso = todayIso,
        nowHhmm = nowHhmm,
    )
    val modeSummary = formatHabitModeSummary(
        mode = habit.mode,
        remindTime = habit.remindTime,
        forceStartTime = habit.forceStartTime,
        forceEndTime = habit.forceEndTime,
        reminderMode = habit.reminderMode,
    )
    val reminderBadge = formatCompanionReminderBadge(
        mode = habit.mode,
        archived = habit.archived,
        reminderEnabled = habit.reminderEnabled,
        reminderTimes = habit.reminderTimes,
        remindTime = habit.remindTime,
        reminderMode = habit.reminderMode,
    )
    val isMonthly = habit.frequencyType == "monthly"
    val streakUnit = if (isMonthly) "mo" else "d"
    val subtitleParts = buildList {
        if (modeSummary != null) {
            add(modeSummary)
        }
        if (localStatus.dayStatus == "in_progress" && !habit.startedAtTime.isNullOrBlank()) {
            add("Started at ${formatTime12h(habit.startedAtTime)}")
        } else if (localStatus.dayStatus == "violation") {
            add(if (localStatus.violationReason == "missed_start") "Missed Start Time" else "Missed End Time")
        }
        if (isMonthly) {
            add(
                formatFrequencySummary(
                    frequencyType = habit.frequencyType,
                    weekdays = habit.weekdays,
                    monthlyMode = habit.monthlyMode,
                    monthlyDay = habit.monthlyDay,
                    monthlyWeek = habit.monthlyWeek,
                    monthlyWeekday = habit.monthlyWeekday,
                ),
            )
        }
        if (habit.targetPerDay > 1) {
            add("${habit.count} / ${habit.targetPerDay} today")
        }
        if (habit.description.isNotBlank()) {
            add(habit.description)
        }
        if (habit.note.isNotBlank()) {
            add("Note: ${habit.note}")
        }
    }
    val subtitleText = if (subtitleParts.isEmpty()) "Daily goal" else subtitleParts.joinToString(" · ")

    val statusChipSpec: Triple<String, Color, Color>? = if (
        habit.mode != "free" || localStatus.dayStatus == "violation" || localStatus.dayStatus == "late_makeup"
    ) {
        when (localStatus.dayStatus) {
            "reminding" -> Triple("Reminding", Color(0xFFDBEAFE), Color(0xFF1D4ED8))
            "in_progress" -> Triple("In Progress", Color(0xFFE0E7FF), Color(0xFF4338CA))
            "on_time" -> Triple("On Time", Color(0xFFDCFCE7), Color(0xFF15803D))
            "violation" -> Triple("Violation", Color(0xFFFEE2E2), Color(0xFFB91C1C))
            "late_makeup" -> Triple("Overdue Make-up", Color(0xFFFEF3C7), Color(0xFFB45309))
            else -> Triple(if (habit.mode == "strict") "Pending Start" else "Pending", Color(0xFFF1F5F9), Color(0xFF475569))
        }
    } else {
        null
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Row(
                modifier = Modifier.weight(1f),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    modifier = Modifier
                        .width(6.dp)
                        .height(44.dp)
                        .clip(RoundedCornerShape(3.dp))
                        .background(accentColor),
                )
                Spacer(modifier = Modifier.width(12.dp))
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(
                        text = habit.title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = subtitleText,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    if (statusChipSpec != null || reminderBadge != null) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            if (statusChipSpec != null) {
                                val (chipText, chipBg, chipFg) = statusChipSpec
                                Surface(
                                    shape = RoundedCornerShape(6.dp),
                                    color = chipBg,
                                ) {
                                    Text(
                                        text = chipText,
                                        style = MaterialTheme.typography.labelSmall,
                                        fontWeight = FontWeight.Bold,
                                        color = chipFg,
                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                    )
                                }
                            }
                            if (reminderBadge != null) {
                                Surface(
                                    shape = RoundedCornerShape(6.dp),
                                    color = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.7f),
                                ) {
                                    Text(
                                        text = reminderBadge,
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSecondaryContainer,
                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                    )
                                }
                            }
                        }
                    }
                }
            }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = if (habit.currentStreak > 0) {
                        MaterialTheme.colorScheme.tertiaryContainer
                    } else {
                        MaterialTheme.colorScheme.surfaceVariant
                    },
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 7.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(2.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.LocalFireDepartment,
                            contentDescription = "Streak",
                            modifier = Modifier.size(14.dp),
                            tint = if (habit.currentStreak > 0) {
                                MaterialTheme.colorScheme.tertiary
                            } else {
                                MaterialTheme.colorScheme.onSurfaceVariant
                            },
                        )
                        Text(
                            text = "${habit.currentStreak}$streakUnit",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                            color = if (habit.currentStreak > 0) {
                                MaterialTheme.colorScheme.onTertiaryContainer
                            } else {
                                MaterialTheme.colorScheme.onSurfaceVariant
                            },
                        )
                    }
                }

                if (!isHabitEditable) {
                    val createdLbl = createdLocal?.toString() ?: habit.createdDate
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.surfaceVariant,
                    ) {
                        Text(
                            text = if (createdLbl.isNotBlank()) "Created $createdLbl" else "Locked",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Medium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        )
                    }
                } else {
                    IconButton(onClick = onOpenEdit) {
                        Icon(
                            imageVector = Icons.Rounded.EditNote,
                            contentDescription = "Edit check-in",
                            tint = if (habit.note.isNotBlank()) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.onSurfaceVariant
                            },
                        )
                    }

                    if (habit.targetPerDay > 1 && habit.count > 0 && !localStatus.canStart) {
                        IconButton(onClick = onDecrementCheckin) {
                            Icon(
                                imageVector = Icons.Rounded.RemoveCircleOutline,
                                contentDescription = "Decrease count",
                                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }

                    when {
                        localStatus.canStart -> {
                            FilledTonalButton(
                                onClick = onStartExecution,
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                            ) {
                                Icon(
                                    imageVector = Icons.Rounded.PlayArrow,
                                    contentDescription = null,
                                    modifier = Modifier.size(16.dp),
                                )
                                Spacer(modifier = Modifier.width(2.dp))
                                Text(
                                    text = "Start",
                                    style = MaterialTheme.typography.labelMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                        }
                        localStatus.dayStatus == "violation" -> {
                            FilledTonalButton(
                                onClick = onPrimaryCheckin,
                                colors = ButtonDefaults.filledTonalButtonColors(
                                    containerColor = MaterialTheme.colorScheme.errorContainer,
                                    contentColor = MaterialTheme.colorScheme.onErrorContainer,
                                ),
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                            ) {
                                Icon(
                                    imageVector = Icons.Rounded.History,
                                    contentDescription = null,
                                    modifier = Modifier.size(16.dp),
                                )
                                Spacer(modifier = Modifier.width(2.dp))
                                Text(
                                    text = "Make-up",
                                    style = MaterialTheme.typography.labelMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                        }
                        else -> {
                            IconButton(onClick = onPrimaryCheckin) {
                                val icon = when {
                                    habit.completed -> Icons.Rounded.CheckCircle
                                    habit.targetPerDay > 1 -> Icons.Rounded.AddCircleOutline
                                    else -> Icons.Rounded.RadioButtonUnchecked
                                }
                                val tint: Color = when {
                                    localStatus.isLate -> Color(0xFFD97706)
                                    habit.completed -> accentColor
                                    else -> MaterialTheme.colorScheme.onSurfaceVariant
                                }
                                Icon(
                                    imageVector = icon,
                                    contentDescription = "Check in",
                                    tint = tint,
                                    modifier = Modifier.size(30.dp),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
