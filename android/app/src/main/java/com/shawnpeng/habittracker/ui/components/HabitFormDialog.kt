package com.shawnpeng.habittracker.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.HABIT_COLOR_SWATCHES
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.data.HabitCreateRequest
import com.shawnpeng.habittracker.data.WEEKDAY_SHORT_LABELS
import com.shawnpeng.habittracker.data.parseHabitColor

@Composable
fun HabitFormDialog(
    existing: Habit?,
    onDismiss: () -> Unit,
    onSave: (HabitCreateRequest) -> Unit,
) {
    var title by remember(existing) { mutableStateOf(existing?.title.orEmpty()) }
    var description by remember(existing) { mutableStateOf(existing?.description.orEmpty()) }
    var targetPerDay by remember(existing) { mutableIntStateOf(existing?.targetPerDay ?: 1) }
    var selectedColorHex by remember(existing) {
        mutableStateOf(existing?.color ?: HABIT_COLOR_SWATCHES.first().hex)
    }
    var selectedDays by remember(existing) {
        mutableStateOf(
            existing?.weekdays?.toSet() ?: setOf(0, 1, 2, 3, 4, 5, 6),
        )
    }
    var validationError by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = if (existing == null) "新建习惯" else "编辑习惯",
                fontWeight = FontWeight.Bold,
            )
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                OutlinedTextField(
                    value = title,
                    onValueChange = {
                        title = it
                        validationError = null
                    },
                    label = { Text("习惯名称") },
                    placeholder = { Text("例如：阅读 20 页、喝水、冥想") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("备注 / 激励语（选填）") },
                    singleLine = false,
                    maxLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(
                        text = "每日目标次数",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        FilledTonalIconButton(
                            onClick = { if (targetPerDay > 1) targetPerDay-- },
                            enabled = targetPerDay > 1,
                        ) {
                            Icon(Icons.Rounded.Remove, contentDescription = "减少次数")
                        }
                        Text(
                            text = "$targetPerDay 次",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 12.dp),
                        )
                        FilledTonalIconButton(
                            onClick = { if (targetPerDay < 100) targetPerDay++ },
                            enabled = targetPerDay < 100,
                        ) {
                            Icon(Icons.Rounded.Add, contentDescription = "增加次数")
                        }
                    }
                }

                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = "主题颜色",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        HABIT_COLOR_SWATCHES.forEach { swatch ->
                            val isSelected = swatch.hex.equals(selectedColorHex, ignoreCase = true)
                            val color = parseHabitColor(swatch.hex)
                            Box(
                                modifier = Modifier
                                    .size(36.dp)
                                    .clip(CircleShape)
                                    .background(color)
                                    .then(
                                        if (isSelected) {
                                            Modifier.border(2.5.dp, MaterialTheme.colorScheme.onSurface, CircleShape)
                                        } else {
                                            Modifier
                                        },
                                    )
                                    .clickable { selectedColorHex = swatch.hex },
                                contentAlignment = Alignment.Center,
                            ) {
                                if (isSelected) {
                                    Icon(
                                        imageVector = Icons.Rounded.Check,
                                        contentDescription = swatch.label,
                                        tint = Color.White,
                                        modifier = Modifier.size(18.dp),
                                    )
                                }
                            }
                        }
                    }
                }

                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = "重复周期",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        val allDays = setOf(0, 1, 2, 3, 4, 5, 6)
                        val workDays = setOf(0, 1, 2, 3, 4)
                        val weekendDays = setOf(5, 6)

                        FilterChip(
                            selected = selectedDays == allDays,
                            onClick = {
                                selectedDays = allDays
                                validationError = null
                            },
                            label = { Text("每天") },
                        )
                        FilterChip(
                            selected = selectedDays == workDays,
                            onClick = {
                                selectedDays = workDays
                                validationError = null
                            },
                            label = { Text("工作日") },
                        )
                        FilterChip(
                            selected = selectedDays == weekendDays,
                            onClick = {
                                selectedDays = weekendDays
                                validationError = null
                            },
                            label = { Text("周末") },
                        )
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        WEEKDAY_SHORT_LABELS.forEachIndexed { idx, label ->
                            val active = idx in selectedDays
                            Box(
                                modifier = Modifier
                                    .size(36.dp)
                                    .clip(CircleShape)
                                    .background(
                                        if (active) MaterialTheme.colorScheme.primary
                                        else MaterialTheme.colorScheme.surfaceVariant,
                                    )
                                    .clickable {
                                        selectedDays = if (active) {
                                            selectedDays - idx
                                        } else {
                                            selectedDays + idx
                                        }
                                        validationError = null
                                    },
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(
                                    text = label,
                                    style = MaterialTheme.typography.labelMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = if (active) MaterialTheme.colorScheme.onPrimary
                                    else MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }

                if (validationError != null) {
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = validationError.orEmpty(),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val trimmedTitle = title.trim()
                    if (trimmedTitle.isEmpty()) {
                        validationError = "请输入习惯名称"
                        return@TextButton
                    }
                    if (selectedDays.isEmpty()) {
                        validationError = "请至少选择一个重复日期"
                        return@TextButton
                    }
                    val sortedDays = selectedDays.sorted()
                    val freqType = if (sortedDays.size == 7) "daily" else "weekdays"
                    onSave(
                        HabitCreateRequest(
                            title = trimmedTitle,
                            description = description.trim(),
                            color = selectedColorHex,
                            frequencyType = freqType,
                            weekdays = sortedDays,
                            targetPerDay = targetPerDay,
                        ),
                    )
                },
            ) {
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
