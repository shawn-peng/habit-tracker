package com.shawnpeng.habittracker.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Alarm
import androidx.compose.material.icons.rounded.NotificationsOff
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.HabitReminderItem
import com.shawnpeng.habittracker.data.RemindersOverview
import com.shawnpeng.habittracker.data.formatReminderBadge
import com.shawnpeng.habittracker.data.parseHabitColor

@Composable
fun RemindersOverviewDialog(
    overview: RemindersOverview?,
    isLoading: Boolean,
    remindersMuted: Boolean,
    onToggleMute: () -> Unit,
    onRefresh: () -> Unit,
    onEditHabit: (HabitReminderItem) -> Unit,
    onSyncSystemClock: (HabitReminderItem) -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Icon(
                        imageVector = if (remindersMuted) {
                            Icons.Rounded.NotificationsOff
                        } else {
                            Icons.Rounded.Alarm
                        },
                        contentDescription = null,
                        tint = if (remindersMuted) {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        } else {
                            MaterialTheme.colorScheme.primary
                        },
                    )
                    Text("提醒与闹钟中心", fontWeight = FontWeight.Bold)
                }
                IconButton(onClick = onRefresh, enabled = !isLoading) {
                    Icon(
                        imageVector = Icons.Rounded.Refresh,
                        contentDescription = "刷新提醒",
                    )
                }
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 460.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "暂停所有提醒与闹钟",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold,
                            )
                            Text(
                                text = if (remindersMuted) "已静音，仅保留后台设置" else "开启中，将按计划触发通知或闹钟",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Switch(
                            checked = remindersMuted,
                            onCheckedChange = { onToggleMute() },
                        )
                    }
                }

                if (overview != null) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        ReminderMetricPill(
                            label = "启用习惯",
                            value = overview.enabledHabitsCount.toString(),
                            modifier = Modifier.weight(1f),
                        )
                        ReminderMetricPill(
                            label = "闹钟模式",
                            value = overview.alarmHabitsCount.toString(),
                            modifier = Modifier.weight(1f),
                        )
                        ReminderMetricPill(
                            label = "今日待触发",
                            value = overview.pendingTodayTriggers.toString(),
                            modifier = Modifier.weight(1f),
                        )
                    }
                }

                HorizontalDivider()

                when {
                    isLoading && overview == null -> {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 24.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            CircularProgressIndicator(modifier = Modifier.size(28.dp))
                        }
                    }

                    overview == null || overview.items.isEmpty() -> {
                        Text(
                            text = "尚未为任何习惯启用提醒或闹钟。\n可在创建或编辑习惯时开启「提醒与闹钟」。",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(vertical = 12.dp),
                        )
                    }

                    else -> {
                        overview.items.forEach { item ->
                            ReminderOverviewItemCard(
                                item = item,
                                onEdit = { onEditHabit(item) },
                                onSyncSystemClock = { onSyncSystemClock(item) },
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text("关闭")
            }
        },
    )
}

@Composable
private fun ReminderMetricPill(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(10.dp),
        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.45f),
    ) {
        Column(
            modifier = Modifier.padding(vertical = 8.dp, horizontal = 6.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = value,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ReminderOverviewItemCard(
    item: HabitReminderItem,
    onEdit: () -> Unit,
    onSyncSystemClock: () -> Unit,
) {
    val accent = parseHabitColor(item.color)
    val badge = formatReminderBadge(
        enabled = item.reminderEnabled,
        times = item.reminderTimes,
        mode = item.reminderMode,
    )
    val nextTriggerText = if (item.nextTriggerDate != null && item.nextTriggerTime != null) {
        "下次触发：${item.nextTriggerDate} ${item.nextTriggerTime}"
    } else if (item.completedToday) {
        "今日打卡已完成"
    } else {
        "暂未安排近期触发"
    }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 1.dp,
    ) {
        Column(
            modifier = Modifier.padding(10.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Box(
                    modifier = Modifier
                        .width(4.dp)
                        .height(34.dp)
                        .clip(RoundedCornerShape(2.dp))
                        .background(accent),
                )
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = item.title,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    if (badge != null) {
                        Text(
                            text = "$badge · 延时 ${item.reminderSnoozeMinutes} 分钟",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
            }

            Text(
                text = nextTriggerText,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (item.reminderMessage.isNotBlank()) {
                Text(
                    text = "提示语：${item.reminderMessage}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OutlinedButton(
                    onClick = onSyncSystemClock,
                    modifier = Modifier.height(34.dp),
                ) {
                    Text("同步到系统闹钟", style = MaterialTheme.typography.labelSmall)
                }
                Spacer(modifier = Modifier.width(6.dp))
                TextButton(onClick = onEdit) {
                    Text("编辑")
                }
            }
        }
    }
}
