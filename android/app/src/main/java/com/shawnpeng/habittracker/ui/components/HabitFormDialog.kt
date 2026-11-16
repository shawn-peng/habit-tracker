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
import com.shawnpeng.habittracker.data.formatTime12h
import com.shawnpeng.habittracker.data.normalizeReminderTime
import com.shawnpeng.habittracker.data.normalizeReminderTimes
import com.shawnpeng.habittracker.data.parseHabitColor
import com.shawnpeng.habittracker.data.resolveTimeWithMeridiem
import com.shawnpeng.habittracker.data.split24hTo12h
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
                else -> if (existing?.reminderEnabled == true) "reminder" else "free"
            },
        )
    }
    val initialRemindPair = remember(existing) {
        val fallbackRemind = existing?.remindTime ?: existing?.reminderTimes?.firstOrNull()
        split24hTo12h(fallbackRemind, "AM")
    }
    val initialStartPair = remember(existing) { split24hTo12h(existing?.forceStartTime, "AM") }
    val initialEndPair = remember(existing) { split24hTo12h(existing?.forceEndTime, "PM") }
    var remindTimeText by remember(existing) {
        mutableStateOf(initialRemindPair.first)
    }
    var remindMeridiem by remember(existing) {
        mutableStateOf(initialRemindPair.second)
    }
    var forceStartTimeText by remember(existing) {
        mutableStateOf(initialStartPair.first)
    }
    var startMeridiem by remember(existing) {
        mutableStateOf(initialStartPair.second)
    }
    var forceEndTimeText by remember(existing) {
        mutableStateOf(initialEndPair.first)
    }
    var endMeridiem by remember(existing) {
        mutableStateOf(initialEndPair.second)
    }
    var modeTimePickerTarget by remember { mutableStateOf<String?>(null) }
    var reminderTimes by remember(existing) {
        mutableStateOf(
            normalizeReminderTimes(
                existing?.reminderTimes.orEmpty() + listOfNotNull(existing?.remindTime),
            ),
        )
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
    var customTimeMeridiem by remember { mutableStateOf("AM") }
    var showTimePickerDialog by remember { mutableStateOf(false) }
    var validationError by remember { mutableStateOf<String?>(null) }

    fun addReminderTime(raw: String, meridiem: String? = null): Boolean {
        val normalized = if (meridiem != null) {
            resolveTimeWithMeridiem(raw, meridiem)
        } else {
            normalizeReminderTime(raw)
        }
        if (normalized == null) {
            validationError = "Time must be in HH:MM or H:MM AM/PM format"
            return false
        }
        if (normalized in reminderTimes) {
            validationError = null
            return true
        }
        if (reminderTimes.size >= MAX_REMINDER_TIMES) {
            validationError = "At most $MAX_REMINDER_TIMES reminder times are allowed"
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
                text = if (existing == null) "New Habit" else "Edit Habit",
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
                    label = { Text("Habit Title") },
                    placeholder = { Text("e.g., Read 20 pages, Pay rent, Monthly review") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Notes / Motivation (optional)") },
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
                        text = if (scheduleType == "monthly") "Target Count (on due day)" else "Daily Target Count",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        FilledTonalIconButton(
                            onClick = { if (targetPerDay > 1) targetPerDay-- },
                            enabled = targetPerDay > 1,
                        ) {
                            Icon(Icons.Rounded.Remove, contentDescription = "Decrease count")
                        }
                        Text(
                            text = "${targetPerDay}x",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 12.dp),
                        )
                        FilledTonalIconButton(
                            onClick = { if (targetPerDay < 100) targetPerDay++ },
                            enabled = targetPerDay < 100,
                        ) {
                            Icon(Icons.Rounded.Add, contentDescription = "Increase count")
                        }
                    }
                }

                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = "Target SLO (%)",
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
                        label = { Text("Target SLO (%)") },
                        placeholder = { Text("1 - 100, e.g., 85.0") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }

                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = "Accent Color",
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
                        text = "Schedule Frequency",
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
                            label = { Text("Daily") },
                        )
                        FilterChip(
                            selected = scheduleType == "weekdays",
                            onClick = {
                                scheduleType = "weekdays"
                                validationError = null
                            },
                            label = { Text("Weekly") },
                        )
                        FilterChip(
                            selected = scheduleType == "monthly",
                            onClick = {
                                scheduleType = "monthly"
                                validationError = null
                            },
                            label = { Text("Monthly") },
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
                                label = { Text("Weekdays") },
                            )
                            FilterChip(
                                selected = selectedDays == weekendDays,
                                onClick = {
                                    selectedDays = weekendDays
                                    validationError = null
                                },
                                label = { Text("Weekends") },
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
                                label = { Text("From Start") },
                            )
                            FilterChip(
                                selected = monthlyMode == "from_end",
                                onClick = { monthlyMode = "from_end" },
                                label = { Text("From End") },
                            )
                            FilterChip(
                                selected = monthlyMode == "nth_weekday",
                                onClick = { monthlyMode = "nth_weekday" },
                                label = { Text("Day X on Week Y") },
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
                                    Icon(Icons.Rounded.Remove, contentDescription = "Decrease day")
                                }
                                Text(
                                    text = if (monthlyMode == "from_end") {
                                        if (monthlyDay == 1) "Last day of month" else "Day $monthlyDay from end"
                                    } else {
                                        "Day $monthlyDay of month"
                                    },
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                                FilledTonalIconButton(
                                    onClick = { if (monthlyDay < 31) monthlyDay++ },
                                    enabled = monthlyDay < 31,
                                ) {
                                    Icon(Icons.Rounded.Add, contentDescription = "Increase day")
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
                                        if (presetDay == 1) "Month end" else "-${presetDay}d"
                                    } else {
                                        "Day $presetDay"
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
                                    "1 = last day of month, 2 = 2nd-to-last, etc."
                                } else {
                                    "Clamped to month-end on shorter months (e.g., Feb 28/29)"
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
                            text = "Rule preview: ${
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
                        text = "Habit Mode & Alerts",
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
                                    if (opt.key != "free" &&
                                        Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                                        !HabitNotificationHelper.hasNotificationPermission(context)
                                    ) {
                                        notificationPermissionLauncher.launch(
                                            Manifest.permission.POST_NOTIFICATIONS,
                                        )
                                    }
                                    if (opt.key == "reminder") {
                                        val resolvedRemind =
                                            resolveTimeWithMeridiem(remindTimeText, remindMeridiem)
                                        if (resolvedRemind != null && reminderTimes.isEmpty()) {
                                            reminderTimes = listOf(resolvedRemind)
                                        }
                                        if (reminderTimes.isEmpty()) {
                                            reminderTimes = listOf("09:00")
                                        }
                                    } else if (opt.key == "strict" || opt.key == "window") {
                                        if (remindTimeText.isBlank()) {
                                            val seed = reminderTimes.firstOrNull() ?: "09:00"
                                            val pair = split24hTo12h(seed, "AM")
                                            remindTimeText = pair.first
                                            remindMeridiem = pair.second
                                        }
                                        if (opt.key == "strict") {
                                            if (forceStartTimeText.isBlank()) {
                                                forceStartTimeText = "09:15"
                                                startMeridiem = "AM"
                                            }
                                            if (forceEndTimeText.isBlank()) {
                                                forceEndTimeText = "10:30"
                                                endMeridiem = "AM"
                                            }
                                        } else if (forceEndTimeText.isBlank()) {
                                            forceEndTimeText = "09:00"
                                            endMeridiem = "PM"
                                        }
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
                    if (habitMode == "strict" || habitMode == "window") {
                        ModeTimeInputRow(
                            value = remindTimeText,
                            onValueChange = {
                                remindTimeText = it
                                validationError = null
                            },
                            meridiem = remindMeridiem,
                            onMeridiemChange = {
                                remindMeridiem = it
                                validationError = null
                            },
                            label = "Remind Time",
                            placeholder = "09:00",
                            pickerDescription = "Pick Remind Time",
                            onOpenPicker = { modeTimePickerTarget = "remind" },
                        )
                    }
                    if (habitMode == "strict") {
                        ModeTimeInputRow(
                            value = forceStartTimeText,
                            onValueChange = {
                                forceStartTimeText = it
                                validationError = null
                            },
                            meridiem = startMeridiem,
                            onMeridiemChange = {
                                startMeridiem = it
                                validationError = null
                            },
                            label = "Force Start",
                            placeholder = "09:15",
                            pickerDescription = "Pick Force Start Time",
                            onOpenPicker = { modeTimePickerTarget = "start" },
                        )
                    }
                    if (habitMode == "strict" || habitMode == "window") {
                        ModeTimeInputRow(
                            value = forceEndTimeText,
                            onValueChange = {
                                forceEndTimeText = it
                                validationError = null
                            },
                            meridiem = endMeridiem,
                            onMeridiemChange = {
                                endMeridiem = it
                                validationError = null
                            },
                            label = "Force End",
                            placeholder = "10:30",
                            pickerDescription = "Pick Force End Time",
                            onOpenPicker = { modeTimePickerTarget = "end" },
                        )
                    }
                    if (habitMode == "reminder") {
                        Text(
                            text = "Reminder Times",
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.Medium,
                        )
                        if (reminderTimes.isEmpty()) {
                            Text(
                                text = "No reminder times added yet. Pick below or enter HH:MM.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        } else {
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                verticalArrangement = Arrangement.spacedBy(4.dp),
                            ) {
                                reminderTimes.forEach { hhmm ->
                                    val displayLabel = formatTime12h(hhmm)
                                    InputChip(
                                        selected = true,
                                        onClick = {
                                            reminderTimes = reminderTimes.filterNot { it == hhmm }
                                            validationError = null
                                        },
                                        label = { Text(displayLabel) },
                                        trailingIcon = {
                                            Icon(
                                                imageVector = Icons.Rounded.Close,
                                                contentDescription = "Remove $displayLabel",
                                                modifier = Modifier.size(16.dp),
                                            )
                                        },
                                    )
                                }
                            }
                        }

                        Text(
                            text = "Quick Presets",
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
                                    label = { Text(formatTime12h(preset)) },
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
                            Text("Pick Clock Time")
                        }

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            OutlinedTextField(
                                value = customTimeText,
                                onValueChange = {
                                    customTimeText = it
                                    validationError = null
                                },
                                label = { Text("Time (HH:MM)") },
                                placeholder = { Text("08:30") },
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                            )
                            MeridiemSelector(
                                selected = customTimeMeridiem,
                                onSelect = {
                                    customTimeMeridiem = it
                                    validationError = null
                                },
                            )
                            TextButton(
                                onClick = {
                                    if (addReminderTime(customTimeText, customTimeMeridiem)) {
                                        customTimeText = ""
                                    }
                                },
                            ) {
                                Text("Add")
                            }
                        }
                    }

                    if (habitMode != "free") {
                        Text(
                            text = "Alert Delivery",
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
                                label = { Text("Notification 🔔") },
                            )
                            FilterChip(
                                selected = reminderMode == "alarm",
                                onClick = { reminderMode = "alarm" },
                                label = { Text("Alarm Ring ⏰") },
                            )
                        }

                        Text(
                            text = "Snooze Duration",
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
                                    label = { Text("${mins} min") },
                                )
                            }
                        }

                        OutlinedTextField(
                            value = reminderMessage,
                            onValueChange = { if (it.length <= 160) reminderMessage = it },
                            label = { Text("Custom Reminder Message (optional)") },
                            placeholder = { Text("e.g., Drink water or focus for 20 minutes") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
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
                        validationError = "Please enter a habit title"
                        return@TextButton
                    }
                    if (scheduleType == "weekdays" && selectedDays.isEmpty()) {
                        validationError = "Pick at least one day of the week"
                        return@TextButton
                    }
                    val parsedSlo = targetSloText.trim().toDoubleOrNull()
                    if (parsedSlo == null || parsedSlo !in 1.0..100.0) {
                        validationError = "Target SLO must be between 1 and 100"
                        return@TextButton
                    }

                    val finalRemindTime: String?
                    val finalForceStartTime: String?
                    val finalForceEndTime: String?
                    val finalReminderEnabled: Boolean
                    var finalReminderTimes: List<String>

                    when (habitMode) {
                        "free" -> {
                            finalRemindTime = null
                            finalForceStartTime = null
                            finalForceEndTime = null
                            finalReminderEnabled = false
                            finalReminderTimes = emptyList()
                        }
                        "strict", "window" -> {
                            val validatedMode = validateHabitModeTimes(
                                mode = habitMode,
                                remindRaw = remindTimeText,
                                startRaw = forceStartTimeText,
                                endRaw = forceEndTimeText,
                                remindMeridiem = remindMeridiem,
                                startMeridiem = startMeridiem,
                                endMeridiem = endMeridiem,
                            )
                            if (validatedMode.errorMessage != null) {
                                validationError = validatedMode.errorMessage
                                return@TextButton
                            }
                            finalRemindTime = validatedMode.remindTime
                            finalForceStartTime = validatedMode.forceStartTime
                            finalForceEndTime = validatedMode.forceEndTime
                            finalReminderEnabled = true
                            finalReminderTimes = listOfNotNull(validatedMode.remindTime)
                        }
                        else -> {
                            finalReminderTimes = reminderTimes
                            val pendingCustom = customTimeText.trim()
                            if (pendingCustom.isNotEmpty()) {
                                val normPending =
                                    resolveTimeWithMeridiem(pendingCustom, customTimeMeridiem)
                                if (normPending == null) {
                                    validationError = "Time must be in HH:MM or H:MM AM/PM format"
                                    return@TextButton
                                }
                                if (normPending !in finalReminderTimes) {
                                    if (finalReminderTimes.size >= MAX_REMINDER_TIMES) {
                                        validationError =
                                            "At most $MAX_REMINDER_TIMES reminder times are allowed"
                                        return@TextButton
                                    }
                                    finalReminderTimes =
                                        normalizeReminderTimes(finalReminderTimes + normPending)
                                    reminderTimes = finalReminderTimes
                                    customTimeText = ""
                                }
                            }
                            if (finalReminderTimes.isEmpty()) {
                                validationError = "Add at least one reminder time"
                                return@TextButton
                            }
                            finalReminderEnabled = true
                            finalRemindTime = finalReminderTimes.first()
                            finalForceStartTime = null
                            finalForceEndTime = null
                        }
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
                            remindTime = finalRemindTime,
                            forceStartTime = finalForceStartTime,
                            forceEndTime = finalForceEndTime,
                            reminderEnabled = finalReminderEnabled,
                            reminderTimes = finalReminderTimes,
                            reminderMode = reminderMode,
                            reminderSnoozeMinutes = reminderSnoozeMinutes,
                            reminderMessage = reminderMessage.trim(),
                        ),
                    )
                },
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
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
            is24Hour = false,
        )
        AlertDialog(
            onDismissRequest = { showTimePickerDialog = false },
            title = { Text("Pick Reminder Time", fontWeight = FontWeight.Bold) },
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
                    Text("OK")
                }
            },
            dismissButton = {
                TextButton(onClick = { showTimePickerDialog = false }) {
                    Text("Cancel")
                }
            },
        )
    }

    modeTimePickerTarget?.let { targetKey ->
        val (currentRaw, currentMeridiem) = when (targetKey) {
            "start" -> forceStartTimeText to startMeridiem
            "end" -> forceEndTimeText to endMeridiem
            else -> remindTimeText to remindMeridiem
        }
        val parts = resolveTimeWithMeridiem(currentRaw, currentMeridiem)?.split(":")
        val initHour = parts?.getOrNull(0)?.toIntOrNull() ?: 9
        val initMinute = parts?.getOrNull(1)?.toIntOrNull() ?: 0
        val modePickerState = rememberTimePickerState(
            initialHour = initHour,
            initialMinute = initMinute,
            is24Hour = false,
        )
        val dialogTitle = when (targetKey) {
            "start" -> "Pick Force Start Time"
            "end" -> "Pick Force End Time"
            else -> "Pick Remind Time"
        }
        AlertDialog(
            onDismissRequest = { modeTimePickerTarget = null },
            title = { Text(dialogTitle, fontWeight = FontWeight.Bold) },
            text = { TimePicker(state = modePickerState) },
            confirmButton = {
                TextButton(
                    onClick = {
                        val formatted24 =
                            "${modePickerState.hour.toString().padStart(2, '0')}:${modePickerState.minute.toString().padStart(2, '0')}"
                        val (time12, meridiem) = split24hTo12h(formatted24)
                        when (targetKey) {
                            "start" -> {
                                forceStartTimeText = time12
                                startMeridiem = meridiem
                            }
                            "end" -> {
                                forceEndTimeText = time12
                                endMeridiem = meridiem
                            }
                            else -> {
                                remindTimeText = time12
                                remindMeridiem = meridiem
                            }
                        }
                        validationError = null
                        modeTimePickerTarget = null
                    },
                ) {
                    Text("OK")
                }
            },
            dismissButton = {
                TextButton(onClick = { modeTimePickerTarget = null }) {
                    Text("Cancel")
                }
            },
        )
    }
}

@Composable
private fun MeridiemSelector(
    selected: String,
    onSelect: (String) -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        listOf("AM", "PM").forEach { option ->
            FilterChip(
                selected = selected.equals(option, ignoreCase = true),
                onClick = { onSelect(option) },
                label = { Text(option) },
            )
        }
    }
}

@Composable
private fun ModeTimeInputRow(
    value: String,
    onValueChange: (String) -> Unit,
    meridiem: String,
    onMeridiemChange: (String) -> Unit,
    label: String,
    placeholder: String,
    pickerDescription: String,
    onOpenPicker: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            label = { Text(label) },
            placeholder = { Text(placeholder) },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
        MeridiemSelector(
            selected = meridiem,
            onSelect = onMeridiemChange,
        )
        FilledTonalIconButton(onClick = onOpenPicker) {
            Icon(Icons.Rounded.AccessTime, contentDescription = pickerDescription)
        }
    }
}
