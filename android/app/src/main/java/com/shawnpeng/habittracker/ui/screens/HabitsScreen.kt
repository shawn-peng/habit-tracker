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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Archive
import androidx.compose.material.icons.rounded.DeleteOutline
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.Unarchive
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.data.formatFrequencySummary
import com.shawnpeng.habittracker.data.formatHabitModeSummary
import com.shawnpeng.habittracker.data.formatReminderBadge
import com.shawnpeng.habittracker.data.parseHabitColor

@Composable
fun HabitsScreen(
    habits: List<Habit>,
    showArchived: Boolean,
    onToggleShowArchived: (Boolean) -> Unit,
    onEditHabit: (Habit) -> Unit,
    onToggleArchive: (Habit) -> Unit,
    onDeleteHabit: (Habit) -> Unit,
) {
    var pendingDelete by remember { mutableStateOf<Habit?>(null) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 92.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "管理习惯",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "自定义重复周期、每日目标与主题色",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        text = "已归档",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Switch(
                        checked = showArchived,
                        onCheckedChange = onToggleShowArchived,
                    )
                }
            }
        }

        if (habits.isEmpty()) {
            item {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                ) {
                    Text(
                        text = if (showArchived) {
                            "暂无习惯记录，点击右下角 + 创建一个吧！"
                        } else {
                            "暂无活跃习惯，点击右下角 + 新增，或打开「已归档」查看历史习惯。"
                        },
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(32.dp),
                    )
                }
            }
        } else {
            items(habits, key = { it.id }) { habit ->
                ManageHabitCard(
                    habit = habit,
                    onEdit = { onEditHabit(habit) },
                    onToggleArchive = { onToggleArchive(habit) },
                    onDeleteRequest = { pendingDelete = habit },
                )
            }
        }
    }

    pendingDelete?.let { target ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("确认删除习惯？", fontWeight = FontWeight.Bold) },
            text = {
                Text("将永久删除「${target.title}」及其历史打卡记录，且无法恢复。如果只是暂时暂停，建议改用归档。")
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        onDeleteHabit(target)
                        pendingDelete = null
                    },
                ) {
                    Text("永久删除", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) {
                    Text("取消")
                }
            },
        )
    }
}

@Composable
private fun ManageHabitCard(
    habit: Habit,
    onEdit: () -> Unit,
    onToggleArchive: () -> Unit,
    onDeleteRequest: () -> Unit,
) {
    val accentColor = parseHabitColor(habit.color)
    val modeSummary = formatHabitModeSummary(
        mode = habit.mode,
        remindTime = habit.remindTime,
        forceStartTime = habit.forceStartTime,
        forceEndTime = habit.forceEndTime,
    )
    val reminderBadge = formatReminderBadge(habit)
    val freqText = formatFrequencySummary(
        frequencyType = habit.frequencyType,
        weekdays = habit.weekdays,
        monthlyMode = habit.monthlyMode,
        monthlyDay = habit.monthlyDay,
        monthlyWeek = habit.monthlyWeek,
        monthlyWeekday = habit.monthlyWeekday,
    )
    val targetUnitLabel = if (habit.frequencyType == "monthly") "单次目标" else "每日目标"
    val titleSuffix = if (habit.archived) " (已归档)" else ""

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
                        text = habit.title + titleSuffix,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = "$freqText · $targetUnitLabel ${habit.targetPerDay} 次 · SLO ${habit.targetSlo}%",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (modeSummary != null) {
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.7f),
                        ) {
                            Text(
                                text = modeSummary,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
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
                    if (habit.description.isNotBlank()) {
                        Text(
                            text = habit.description,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onEdit) {
                    Icon(
                        imageVector = Icons.Rounded.Edit,
                        contentDescription = "编辑",
                    )
                }
                IconButton(onClick = onToggleArchive) {
                    Icon(
                        imageVector = if (habit.archived) {
                            Icons.Rounded.Unarchive
                        } else {
                            Icons.Rounded.Archive
                        },
                        contentDescription = if (habit.archived) "取消归档" else "归档",
                    )
                }
                IconButton(onClick = onDeleteRequest) {
                    Icon(
                        imageVector = Icons.Rounded.DeleteOutline,
                        contentDescription = "删除",
                        tint = MaterialTheme.colorScheme.error,
                    )
                }
            }
        }
    }
}
