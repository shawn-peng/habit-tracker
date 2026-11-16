package com.shawnpeng.habittracker.ui.components

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.material.icons.rounded.AccessTime
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.InputChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberTimePickerState
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.HABIT_COLOR_SWATCHES
import com.shawnpeng.habittracker.data.HABIT_MODE_OPTIONS
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.data.HabitCreateRequest
import com.shawnpeng.habittracker.data.MAX_REMINDER_TIMES
import com.shawnpeng.habittracker.data.MONTHLY_WEEK_OPTIONS
import com.shawnpeng.habittracker.data.REMINDER_SNOOZE_OPTIONS
import com.shawnpeng.habittracker.data.REMINDER_TIME_PRESETS
import com.shawnpeng.habittracker.data.WEEKDAY_SHORT_LABELS
import com.shawnpeng.habittracker.data.formatFrequencySummary
import com.shawnpeng.habittracker.data.normalizeReminderTime
import com.shawnpeng.habittracker.data.normalizeReminderTimes
import com.shawnpeng.habittracker.data.parseHabitColor
import com.shawnpeng.habittracker.data.validateHabitModeTimes
import com.shawnpeng.habittracker.notifications.HabitNotificationHelper

@Composable
fun HabitFormDialog(
    existing: Habit?,
    onDismiss: () -> Unit,
    onSave: (HabitCreateRequest) -> Unit,
) {
    val context = LocalContext.current
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { _ -> }

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
    var habitMode by remember(existing) {
        mutableStateOf(
            when (existing?.mode) {
                "strict", "window", "reminder" -> existing.mode
                else -> "free"
            },
        )
    }
    var remindTimeText by remember(existing) {
        mutableStateOf(existing?.remindTime.orEmpty())
    }
    var forceStartTimeText by remember(existing) {
        mutableStateOf(existing?.forceStartTime.orEmpty())
    }
    var forceEndTimeText by remember(existing) {
        mutableStateOf(existing?.forceEndTime.orEmpty())
    }
    var modeTimePickerTarget by remember { mutableStateOf<String?>(null) }
    var reminderEnabled by remember(existing) {
        mutableStateOf(existing?.reminderEnabled ?: false)
    }
    var reminderTimes by remember(existing) {
        mutableStateOf(normalizeReminderTimes(existing?.reminderTimes.orEmpty()))
    }
    var reminderMode by remember(existing) {
        mutableStateOf(
            if (existing?.reminderMode == "alarm") "alarm" else "notification",
        )
    }
    var reminderSnoozeMinutes by remember(existing) {
        mutableIntStateOf((existing?.reminderSnoozeMinutes ?: 10).coerceIn(1, 120))
    }
    var reminderMessage by remember(existing) {
        mutableStateOf(existing?.reminderMessage.orEmpty())
    }
    var customTimeText by remember { mutableStateOf("") }
    var showTimePickerDialog by remember { mutableStateOf(false) }
    var validationError by remember { mutableStateOf<String?>(null) }

    fun addReminderTime(raw: String): Boolean {
        val normalized = normalizeReminderTime(raw)
        if (normalized == null) {
            validationError = "提醒时间格式需为 HH:MM（00:00-23:59）"
            return false
        }
        if (normalized in reminderTimes) {
            validationError = null
            return true
        }
        if (reminderTimes.size >= MAX_REMINDER_TIMES) {
            validationError = "最多添加 $MAX_REMINDER_TIMES 个提醒时间"
            return false
        }
        reminderTimes = normalizeReminderTimes(reminderTimes + normalized)
        validationError = null
        return true
    }

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

                HorizontalDivider()

                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = "打卡模式",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        HABIT_MODE_OPTIONS.forEach { opt ->
                            FilterChip(
                                selected = habitMode == opt.key,
                                onClick = {
                                    habitMode = opt.key
                                    validationError = null
                                    if (opt.key != "free" && remindTimeText.isBlank()) {
                                        remindTimeText = "09:00"
                                    }
                                    if (opt.key == "strict") {
                                        if (forceStartTimeText.isBlank()) forceStartTimeText = "09:15"
                                        if (forceEndTimeText.isBlank()) forceEndTimeText = "10:30"
                                    } else if (opt.key == "window" && forceEndTimeText.isBlank()) {
                                        forceEndTimeText = "21:00"
                                    }
                                },
                                label = { Text(opt.label) },
                            )
                        }
                    }
                    val modeHint = HABIT_MODE_OPTIONS.firstOrNull { it.key == habitMode }?.hint.orEmpty()
                    if (modeHint.isNotEmpty()) {
                        Text(
                            text = modeHint,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (habitMode != "free") {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            OutlinedTextField(
                                value = remindTimeText,
                                onValueChange = {
                                    remindTimeText = it
                                    validationError = null
                                },
                                label = { Text("开始提醒时间 (HH:MM)") },
                                placeholder = { Text("09:00") },
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                            )
                            FilledTonalIconButton(onClick = { modeTimePickerTarget = "remind" }) {
                                Icon(Icons.Rounded.AccessTime, contentDescription = "选择提醒时间")
                            }
                        }
                    }
                    if (habitMode == "strict") {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            OutlinedTextField(
                                value = forceStartTimeText,
                                onValueChange = {
                                    forceStartTimeText = it
                                    validationError = null
                                },
                                label = { Text("强制执行时间 (HH:MM)") },
                                placeholder = { Text("09:15") },
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                            )
                            FilledTonalIconButton(onClick = { modeTimePickerTarget = "start" }) {
                                Icon(Icons.Rounded.AccessTime, contentDescription = "选择强制执行时间")
                            }
                        }
                    }
                    if (habitMode == "strict" || habitMode == "window") {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            OutlinedTextField(
                                value = forceEndTimeText,
                                onValueChange = {
                                    forceEndTimeText = it
                                    validationError = null
                                },
                                label = { Text("强制完成时间 (HH:MM)") },
                                placeholder = { Text("10:30") },
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                            )
                            FilledTonalIconButton(onClick = { modeTimePickerTarget = "end" }) {
                                Icon(Icons.Rounded.AccessTime, contentDescription = "选择强制完成时间")
                            }
                        }
                    }
                }

                HorizontalDivider()

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
                            imageVector = Icons.Rounded.NotificationsActive,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(20.dp),
                        )
                        Text(
                            text = "提醒与闹钟",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    Switch(
                        checked = reminderEnabled,
                        onCheckedChange = { checked ->
                            reminderEnabled = checked
                            validationError = null
                            if (checked && reminderTimes.isEmpty()) {
                                reminderTimes = listOf("09:00")
                            }
                            if (checked &&
                                Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                                !HabitNotificationHelper.hasNotificationPermission(context)
                            ) {
                                notificationPermissionLauncher.launch(
                                    Manifest.permission.POST_NOTIFICATIONS,
                                )
                            }
                        },
                    )
                }

                if (reminderEnabled) {
                    Text(
                        text = "提醒时间",
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Medium,
                    )
                    if (reminderTimes.isEmpty()) {
                        Text(
                            text = "尚未添加提醒时间，请从下方选择或输入 HH:MM",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    } else {
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            reminderTimes.forEach { hhmm ->
                                InputChip(
                                    selected = true,
                                    onClick = {
                                        reminderTimes = reminderTimes.filterNot { it == hhmm }
                                        validationError = null
                                    },
                                    label = { Text(hhmm) },
                                    trailingIcon = {
                                        Icon(
                                            imageVector = Icons.Rounded.Close,
                                            contentDescription = "移除 $hhmm",
                                            modifier = Modifier.size(16.dp),
                                        )
                                    },
                                )
                            }
                        }
                    }

                    Text(
                        text = "常用时间快捷选择",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        REMINDER_TIME_PRESETS.forEach { preset ->
                            val selected = preset in reminderTimes
                            FilterChip(
                                selected = selected,
                                onClick = {
                                    if (selected) {
                                        reminderTimes = reminderTimes.filterNot { it == preset }
                                    } else {
                                        addReminderTime(preset)
                                    }
                                },
                                label = { Text(preset) },
                            )
                        }
                    }

                    OutlinedButton(
                        onClick = { showTimePickerDialog = true },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.AccessTime,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("选择钟表时间")
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        OutlinedTextField(
                            value = customTimeText,
                            onValueChange = {
                                customTimeText = it
                                validationError = null
                            },
                            label = { Text("自定义时间 (HH:MM)") },
                            placeholder = { Text("例如 08:30") },
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                        TextButton(
                            onClick = {
                                if (addReminderTime(customTimeText)) {
                                    customTimeText = ""
                                }
                            },
                        ) {
                            Text("添加")
                        }
                    }

                    Text(
                        text = "提醒方式",
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Medium,
                    )
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        FilterChip(
                            selected = reminderMode != "alarm",
                            onClick = { reminderMode = "notification" },
                            label = { Text("普通通知 🔔") },
                        )
                        FilterChip(
                            selected = reminderMode == "alarm",
                            onClick = { reminderMode = "alarm" },
                            label = { Text("强提醒闹钟 ⏰") },
                        )
                    }

                    Text(
                        text = "贪睡延时",
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Medium,
                    )
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        REMINDER_SNOOZE_OPTIONS.forEach { mins ->
                            FilterChip(
                                selected = reminderSnoozeMinutes == mins,
                                onClick = { reminderSnoozeMinutes = mins },
                                label = { Text("${mins} 分钟") },
                            )
                        }
                    }

                    OutlinedTextField(
                        value = reminderMessage,
                        onValueChange = { if (it.length <= 160) reminderMessage = it },
                        label = { Text("自定义提醒语（选填）") },
                        placeholder = { Text("例如：别忘了喝水或开始专注 20 分钟") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
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
                    var finalReminderTimes = reminderTimes
                    val pendingCustom = customTimeText.trim()
                    if (pendingCustom.isNotEmpty()) {
                        val normPending = normalizeReminderTime(pendingCustom)
                        if (normPending == null) {
                            validationError = "提醒时间格式需为 HH:MM（00:00-23:59）"
                            return@TextButton
                        }
                        if (normPending !in finalReminderTimes) {
                            if (finalReminderTimes.size >= MAX_REMINDER_TIMES) {
                                validationError = "最多添加 $MAX_REMINDER_TIMES 个提醒时间"
                                return@TextButton
                            }
                            finalReminderTimes = normalizeReminderTimes(finalReminderTimes + normPending)
                            reminderTimes = finalReminderTimes
                            customTimeText = ""
                        }
                    }
                    if (reminderEnabled && finalReminderTimes.isEmpty()) {
                        validationError = "开启提醒后请至少设置一个提醒时间"
                        return@TextButton
                    }
                    val validatedMode = validateHabitModeTimes(
                        mode = habitMode,
                        remindRaw = remindTimeText,
                        startRaw = forceStartTimeText,
                        endRaw = forceEndTimeText,
                    )
                    if (validatedMode.errorMessage != null) {
                        validationError = validatedMode.errorMessage
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
                            mode = habitMode,
                            remindTime = validatedMode.remindTime,
                            forceStartTime = validatedMode.forceStartTime,
                            forceEndTime = validatedMode.forceEndTime,
                            reminderEnabled = reminderEnabled,
                            reminderTimes = finalReminderTimes,
                            reminderMode = reminderMode,
                            reminderSnoozeMinutes = reminderSnoozeMinutes,
                            reminderMessage = reminderMessage.trim(),
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

    if (showTimePickerDialog) {
        val firstParts = reminderTimes.firstOrNull()?.split(":")
        val initHour = firstParts?.getOrNull(0)?.toIntOrNull() ?: 9
        val initMinute = firstParts?.getOrNull(1)?.toIntOrNull() ?: 0
        val pickerState = rememberTimePickerState(
            initialHour = initHour,
            initialMinute = initMinute,
            is24Hour = true,
        )
        AlertDialog(
            onDismissRequest = { showTimePickerDialog = false },
            title = { Text("选择提醒时间", fontWeight = FontWeight.Bold) },
            text = { TimePicker(state = pickerState) },
            confirmButton = {
                TextButton(
                    onClick = {
                        val formatted =
                            "${pickerState.hour.toString().padStart(2, '0')}:${pickerState.minute.toString().padStart(2, '0')}"
                        addReminderTime(formatted)
                        showTimePickerDialog = false
                    },
                ) {
                    Text("确定")
                }
            },
            dismissButton = {
                TextButton(onClick = { showTimePickerDialog = false }) {
                    Text("取消")
                }
            },
        )
    }

    modeTimePickerTarget?.let { targetKey ->
        val currentRaw = when (targetKey) {
            "start" -> forceStartTimeText
            "end" -> forceEndTimeText
            else -> remindTimeText
        }
        val parts = normalizeReminderTime(currentRaw)?.split(":")
        val initHour = parts?.getOrNull(0)?.toIntOrNull() ?: 9
        val initMinute = parts?.getOrNull(1)?.toIntOrNull() ?: 0
        val modePickerState = rememberTimePickerState(
            initialHour = initHour,
            initialMinute = initMinute,
            is24Hour = true,
        )
        val dialogTitle = when (targetKey) {
            "start" -> "选择强制执行时间"
            "end" -> "选择强制完成时间"
            else -> "选择开始提醒时间"
        }
        AlertDialog(
            onDismissRequest = { modeTimePickerTarget = null },
            title = { Text(dialogTitle, fontWeight = FontWeight.Bold) },
            text = { TimePicker(state = modePickerState) },
            confirmButton = {
                TextButton(
                    onClick = {
                        val formatted =
                            "${modePickerState.hour.toString().padStart(2, '0')}:${modePickerState.minute.toString().padStart(2, '0')}"
                        when (targetKey) {
                            "start" -> forceStartTimeText = formatted
                            "end" -> forceEndTimeText = formatted
                            else -> remindTimeText = formatted
                        }
                        validationError = null
                        modeTimePickerTarget = null
                    },
                ) {
                    Text("确定")
                }
            },
            dismissButton = {
                TextButton(onClick = { modeTimePickerTarget = null }) {
                    Text("取消")
                }
            },
        )
    }
}
