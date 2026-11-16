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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AddCircleOutline
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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import com.shawnpeng.habittracker.data.formatFrequencySummary
import com.shawnpeng.habittracker.data.formatHabitModeSummary
import com.shawnpeng.habittracker.data.formatReminderBadge
import com.shawnpeng.habittracker.data.parseHabitColor
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun TodayScreen(
    selectedDate: LocalDate,
    habits: List<HabitToday>,
    onShiftDate: (Long) -> Unit,
    onJumpToday: () -> Unit,
    onStartExecution: (HabitToday) -> Unit,
    onPrimaryCheckin: (HabitToday) -> Unit,
    onDecrementCheckin: (HabitToday) -> Unit,
    onUpdateNote: (HabitToday, String) -> Unit,
) {
    val todayDate = LocalDate.now()
    val todayIso = todayDate.format(DateTimeFormatter.ISO_LOCAL_DATE)
    val selectedIso = selectedDate.format(DateTimeFormatter.ISO_LOCAL_DATE)
    val nowTime = LocalTime.now()
    val nowHhmm = "${nowTime.hour.toString().padStart(2, '0')}:${nowTime.minute.toString().padStart(2, '0')}"

    val isToday = selectedDate == todayDate
    val scheduledItems = remember(habits) { habits.filter { it.scheduledToday } }
    val extraItems = remember(habits) { habits.filter { !it.scheduledToday } }

    val evalById = remember(scheduledItems, selectedIso, todayIso, nowHhmm) {
        scheduledItems.associate { it.id to evaluateLocalHabitStatus(it, selectedIso, todayIso, nowHhmm) }
    }
    val doneCount = scheduledItems.count { evalById[it.id]?.dayStatus == "on_time" }
    val lateCount = scheduledItems.count { evalById[it.id]?.dayStatus == "late_makeup" }
    val violationCount = scheduledItems.count { evalById[it.id]?.dayStatus == "violation" }
    val remindingTitles = scheduledItems.filter { evalById[it.id]?.dayStatus == "reminding" }.map { it.title }
    val violatedTitles = scheduledItems.filter { evalById[it.id]?.dayStatus == "violation" }.map { it.title }
    val totalScheduled = scheduledItems.size
    val progressFraction = if (totalScheduled > 0) doneCount.toFloat() / totalScheduled.toFloat() else 0f

    var noteTargetHabit by remember { mutableStateOf<HabitToday?>(null) }

    val dateFormatter = remember {
        DateTimeFormatter.ofPattern("yyyy年M月d日 E", Locale.CHINESE)
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
                    IconButton(onClick = { onShiftDate(-1) }) {
                        Icon(Icons.Rounded.ChevronLeft, contentDescription = "前一天")
                    }
                    Column {
                        Text(
                            text = if (isToday) "今天" else selectedDate.format(dateFormatter),
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
                        Icon(Icons.Rounded.ChevronRight, contentDescription = "后一天")
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
                        label = { Text("回到今天") },
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
                            text = "今日打卡进度",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                        )
                        Text(
                            text = "$doneCount / $totalScheduled 已完成",
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
                                        text = "超时补卡 $lateCount 项（单独统计）",
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
                                        text = "超时违规 $violationCount 项",
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
                        add("⚠️ 超时违规（支持补卡）：${violatedTitles.take(3).joinToString("、")}")
                    }
                    if (remindingTitles.isNotEmpty()) {
                        add("🔔 正在提醒：${remindingTitles.take(3).joinToString("、")}")
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
                            text = "还没有习惯记录，点击右下角 + 创建你的第一个日常习惯吧！",
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
                    onOpenNote = { noteTargetHabit = habit },
                )
            }

            if (extraItems.isNotEmpty()) {
                item {
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "今日非计划习惯（可额外打卡）",
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
                        onOpenNote = { noteTargetHabit = habit },
                    )
                }
            }
        }
    }

    noteTargetHabit?.let { targetHabit ->
        CheckinNoteDialog(
            habit = targetHabit,
            onDismiss = { noteTargetHabit = null },
            onSave = { updatedNote ->
                onUpdateNote(targetHabit, updatedNote)
                noteTargetHabit = null
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
    onOpenNote: () -> Unit,
) {
    val accentColor = parseHabitColor(habit.color)
    val localStatus = evaluateLocalHabitStatus(habit, habit.date, todayIso, nowHhmm)
    val modeSummary = formatHabitModeSummary(
        mode = habit.mode,
        remindTime = habit.remindTime,
        forceStartTime = habit.forceStartTime,
        forceEndTime = habit.forceEndTime,
    )
    val reminderBadge = formatReminderBadge(
        enabled = habit.reminderEnabled,
        times = habit.reminderTimes,
        mode = habit.reminderMode,
    )
    val isMonthly = habit.frequencyType == "monthly"
    val streakUnit = if (isMonthly) "月" else "天"
    val subtitleParts = buildList {
        if (modeSummary != null) {
            add(modeSummary)
        }
        if (localStatus.dayStatus == "in_progress" && !habit.startedAtTime.isNullOrBlank()) {
            add("已于 ${habit.startedAtTime} 开始")
        } else if (localStatus.dayStatus == "violation") {
            add(if (localStatus.violationReason == "missed_start") "未按时开始" else "未按时完成")
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
            add("${habit.count} / ${habit.targetPerDay} 次")
        }
        if (habit.description.isNotBlank()) {
            add(habit.description)
        }
        if (habit.note.isNotBlank()) {
            add("笔记: ${habit.note}")
        }
    }
    val subtitleText = if (subtitleParts.isEmpty()) "每日打卡" else subtitleParts.joinToString(" · ")

    val statusChipSpec: Triple<String, Color, Color>? = if (
        habit.mode != "free" || localStatus.dayStatus == "violation" || localStatus.dayStatus == "late_makeup"
    ) {
        when (localStatus.dayStatus) {
            "reminding" -> Triple("开始提醒中", Color(0xFFDBEAFE), Color(0xFF1D4ED8))
            "in_progress" -> Triple("执行中", Color(0xFFE0E7FF), Color(0xFF4338CA))
            "on_time" -> Triple("准时完成", Color(0xFFDCFCE7), Color(0xFF15803D))
            "violation" -> Triple("超时违规", Color(0xFFFEE2E2), Color(0xFFB91C1C))
            "late_makeup" -> Triple("超时补卡", Color(0xFFFEF3C7), Color(0xFFB45309))
            else -> Triple(if (habit.mode == "strict") "待开始" else "待打卡", Color(0xFFF1F5F9), Color(0xFF475569))
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
                            contentDescription = "连胜天数",
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

                IconButton(onClick = onOpenNote) {
                    Icon(
                        imageVector = Icons.Rounded.EditNote,
                        contentDescription = "当日备注",
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
                            contentDescription = "减少一次",
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
                                text = "开始",
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
                                text = "补卡",
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
                                contentDescription = "打卡",
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

@Composable
private fun CheckinNoteDialog(
    habit: HabitToday,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit,
) {
    var noteText by remember(habit) { mutableStateOf(habit.note) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("打卡笔记 · ${habit.title}", fontWeight = FontWeight.Bold) },
        text = {
            OutlinedTextField(
                value = noteText,
                onValueChange = { noteText = it },
                label = { Text("今日感想或记录（选填）") },
                maxLines = 4,
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            TextButton(onClick = { onSave(noteText) }) {
                Text("保存")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("取消")
            }
        },
    )
}
