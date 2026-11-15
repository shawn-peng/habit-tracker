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
import androidx.compose.material.icons.rounded.LocalFireDepartment
import androidx.compose.material.icons.rounded.RadioButtonUnchecked
import androidx.compose.material.icons.rounded.RemoveCircleOutline
import androidx.compose.material.icons.rounded.SelfImprovement
import androidx.compose.material.icons.rounded.Today
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
import com.shawnpeng.habittracker.data.formatFrequencySummary
import com.shawnpeng.habittracker.data.parseHabitColor
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun TodayScreen(
    selectedDate: LocalDate,
    habits: List<HabitToday>,
    onShiftDate: (Long) -> Unit,
    onJumpToday: () -> Unit,
    onPrimaryCheckin: (HabitToday) -> Unit,
    onDecrementCheckin: (HabitToday) -> Unit,
    onUpdateNote: (HabitToday, String) -> Unit,
) {
    val isToday = selectedDate == LocalDate.now()
    val scheduledItems = remember(habits) { habits.filter { it.scheduledToday } }
    val extraItems = remember(habits) { habits.filter { !it.scheduledToday } }

    val doneCount = scheduledItems.count { it.completed }
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
    onPrimaryCheckin: () -> Unit,
    onDecrementCheckin: () -> Unit,
    onOpenNote: () -> Unit,
) {
    val accentColor = parseHabitColor(habit.color)
    val isMonthly = habit.frequencyType == "monthly"
    val streakUnit = if (isMonthly) "月" else "天"
    val subtitleParts = buildList {
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

                if (habit.targetPerDay > 1 && habit.count > 0) {
                    IconButton(onClick = onDecrementCheckin) {
                        Icon(
                            imageVector = Icons.Rounded.RemoveCircleOutline,
                            contentDescription = "减少一次",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }

                IconButton(onClick = onPrimaryCheckin) {
                    val icon = when {
                        habit.completed -> Icons.Rounded.CheckCircle
                        habit.targetPerDay > 1 -> Icons.Rounded.AddCircleOutline
                        else -> Icons.Rounded.RadioButtonUnchecked
                    }
                    val tint: Color = if (habit.completed) {
                        accentColor
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
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
