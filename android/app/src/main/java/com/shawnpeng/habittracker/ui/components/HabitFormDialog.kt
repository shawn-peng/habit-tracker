package com.shawnpeng.habittracker.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.HABIT_COLOR_SWATCHES
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.data.HabitCreateRequest
import com.shawnpeng.habittracker.data.MONTHLY_WEEK_OPTIONS
import com.shawnpeng.habittracker.data.WEEKDAY_SHORT_LABELS
import com.shawnpeng.habittracker.data.formatFrequencySummary
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
    var targetSloText by remember(existing) {
        mutableStateOf((existing?.targetSlo ?: 85.0).toString())
    }
    var selectedColorHex by remember(existing) {
        mutableStateOf(existing?.color ?: HABIT_COLOR_SWATCHES.first().hex)
    }
    var scheduleType by remember(existing) {
        mutableStateOf(
            when (existing?.frequencyType) {
                "monthly" -> "monthly"
                "weekdays" -> "weekdays"
                else -> "daily"
            },
        )
    }
    var selectedDays by remember(existing) {
        mutableStateOf(
            existing?.weekdays?.toSet() ?: setOf(0, 1, 2, 3, 4, 5, 6),
        )
    }
    var monthlyMode by remember(existing) {
        mutableStateOf(existing?.monthlyMode ?: "from_start")
    }
    var monthlyDay by remember(existing) {
        mutableIntStateOf((existing?.monthlyDay ?: 1).coerceIn(1, 31))
    }
    var monthlyWeek by remember(existing) {
        mutableIntStateOf(existing?.monthlyWeek ?: 1)
    }
    var monthlyWeekday by remember(existing) {
        mutableIntStateOf((existing?.monthlyWeekday ?: 0).coerceIn(0, 6))
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
                    placeholder = { Text("例如：阅读 20 页、交房租、月度复盘") },
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
                        text = if (scheduleType == "monthly") "单次目标次数" else "每日目标次数",
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
                        text = "目标 SLO (%)",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        val parsedSlo = targetSloText.trim().toDoubleOrNull()
                        listOf(80.0, 85.0, 90.0, 95.0, 100.0).forEach { preset ->
                            FilterChip(
                                selected = parsedSlo != null && kotlin.math.abs(parsedSlo - preset) < 0.05,
                                onClick = {
                                    targetSloText = preset.toString()
                                    validationError = null
                                },
                                label = { Text("${preset.toInt()}%") },
                            )
                        }
                    }
                    OutlinedTextField(
                        value = targetSloText,
                        onValueChange = {
                            targetSloText = it
                            validationError = null
                        },
                        label = { Text("目标 SLO (%)") },
                        placeholder = { Text("1 - 100，例如 85.0") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        modifier = Modifier.fillMaxWidth(),
                    )
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
                        FilterChip(
                            selected = scheduleType == "daily",
                            onClick = {
                                scheduleType = "daily"
                                validationError = null
                            },
                            label = { Text("每天") },
                        )
                        FilterChip(
                            selected = scheduleType == "weekdays",
                            onClick = {
                                scheduleType = "weekdays"
                                validationError = null
                            },
                            label = { Text("按周") },
                        )
                        FilterChip(
                            selected = scheduleType == "monthly",
                            onClick = {
                                scheduleType = "monthly"
                                validationError = null
                            },
                            label = { Text("按月例行") },
                        )
                    }

                    if (scheduleType == "weekdays") {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            val workDays = setOf(0, 1, 2, 3, 4)
                            val weekendDays = setOf(5, 6)

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
                    } else if (scheduleType == "monthly") {
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            FilterChip(
                                selected = monthlyMode == "from_start",
                                onClick = { monthlyMode = "from_start" },
                                label = { Text("月初正数") },
                            )
                            FilterChip(
                                selected = monthlyMode == "from_end",
                                onClick = { monthlyMode = "from_end" },
                                label = { Text("月末倒数") },
                            )
                            FilterChip(
                                selected = monthlyMode == "nth_weekday",
                                onClick = { monthlyMode = "nth_weekday" },
                                label = { Text("第Y周的周X") },
                            )
                        }

                        if (monthlyMode == "from_start" || monthlyMode == "from_end") {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                FilledTonalIconButton(
                                    onClick = { if (monthlyDay > 1) monthlyDay-- },
                                    enabled = monthlyDay > 1,
                                ) {
                                    Icon(Icons.Rounded.Remove, contentDescription = "减少天数")
                                }
                                Text(
                                    text = if (monthlyMode == "from_end") {
                                        if (monthlyDay == 1) "月末最后一天" else "倒数第 $monthlyDay 天"
                                    } else {
                                        "每月第 $monthlyDay 天"
                                    },
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                                FilledTonalIconButton(
                                    onClick = { if (monthlyDay < 31) monthlyDay++ },
                                    enabled = monthlyDay < 31,
                                ) {
                                    Icon(Icons.Rounded.Add, contentDescription = "增加天数")
                                }
                            }

                            val presets = if (monthlyMode == "from_end") {
                                listOf(1, 2, 3, 7)
                            } else {
                                listOf(1, 10, 15, 25, 31)
                            }
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                verticalArrangement = Arrangement.spacedBy(4.dp),
                            ) {
                                presets.forEach { presetDay ->
                                    val presetLabel = if (monthlyMode == "from_end") {
                                        if (presetDay == 1) "月末" else "倒数${presetDay}天"
                                    } else {
                                        "${presetDay}日"
                                    }
                                    FilterChip(
                                        selected = monthlyDay == presetDay,
                                        onClick = { monthlyDay = presetDay },
                                        label = { Text(presetLabel) },
                                    )
                                }
                            }

                            Text(
                                text = if (monthlyMode == "from_end") {
                                    "1 表示当月最后一天，2 表示倒数第二天，以此类推"
                                } else {
                                    "遇到不足该天数的月份（如 2 月、小月）将自动顺延至当月最后一天"
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        } else {
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                verticalArrangement = Arrangement.spacedBy(4.dp),
                            ) {
                                MONTHLY_WEEK_OPTIONS.forEach { (weekVal, label) ->
                                    FilterChip(
                                        selected = monthlyWeek == weekVal,
                                        onClick = { monthlyWeek = weekVal },
                                        label = { Text(label) },
                                    )
                                }
                            }

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                WEEKDAY_SHORT_LABELS.forEachIndexed { idx, label ->
                                    val active = monthlyWeekday == idx
                                    Box(
                                        modifier = Modifier
                                            .size(36.dp)
                                            .clip(CircleShape)
                                            .background(
                                                if (active) MaterialTheme.colorScheme.primary
                                                else MaterialTheme.colorScheme.surfaceVariant,
                                            )
                                            .clickable { monthlyWeekday = idx },
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

                        Text(
                            text = "规则预览：${
                                formatFrequencySummary(
                                    frequencyType = "monthly",
                                    monthlyMode = monthlyMode,
                                    monthlyDay = monthlyDay,
                                    monthlyWeek = monthlyWeek,
                                    monthlyWeekday = monthlyWeekday,
                                )
                            }",
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.Medium,
                            color = MaterialTheme.colorScheme.primary,
                        )
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
                    if (scheduleType == "weekdays" && selectedDays.isEmpty()) {
                        validationError = "请至少选择一个重复日期"
                        return@TextButton
                    }
                    val parsedSlo = targetSloText.trim().toDoubleOrNull()
                    if (parsedSlo == null || parsedSlo !in 1.0..100.0) {
                        validationError = "目标 SLO 需在 1 到 100 之间"
                        return@TextButton
                    }
                    val roundedSlo = kotlin.math.round(parsedSlo * 10.0) / 10.0
                    val sortedDays = if (scheduleType == "weekdays") {
                        selectedDays.sorted()
                    } else {
                        listOf(0, 1, 2, 3, 4, 5, 6)
                    }
                    val freqType = when (scheduleType) {
                        "monthly" -> "monthly"
                        "weekdays" -> if (sortedDays.size == 7) "daily" else "weekdays"
                        else -> "daily"
                    }
                    onSave(
                        HabitCreateRequest(
                            title = trimmedTitle,
                            description = description.trim(),
                            color = selectedColorHex,
                            frequencyType = freqType,
                            weekdays = sortedDays,
                            monthlyMode = monthlyMode,
                            monthlyDay = monthlyDay,
                            monthlyWeek = monthlyWeek,
                            monthlyWeekday = monthlyWeekday,
                            targetPerDay = targetPerDay,
                            targetSlo = roundedSlo,
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
