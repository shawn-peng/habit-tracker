package com.shawnpeng.habittracker.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ChevronLeft
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.Today
import androidx.compose.material3.AssistChip
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.shawnpeng.habittracker.data.HabitHistory
import com.shawnpeng.habittracker.data.HabitHistoryDay
import com.shawnpeng.habittracker.data.WEEKDAY_SHORT_LABELS
import com.shawnpeng.habittracker.data.parseHabitColor
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Locale

private data class HistoryStateColors(
    val bg: Color,
    val border: Color,
    val fg: Color,
    val label: String,
)

private fun historyColorsForState(state: String): HistoryStateColors = when (state) {
    "on_time" -> HistoryStateColors(
        bg = Color(0xFFDCFCE7),
        border = Color(0xFF22C55E),
        fg = Color(0xFF15803D),
        label = "On Time",
    )
    "late_makeup" -> HistoryStateColors(
        bg = Color(0xFFFEF3C7),
        border = Color(0xFFF59E0B),
        fg = Color(0xFFB45309),
        label = "Make-up",
    )
    "missed" -> HistoryStateColors(
        bg = Color(0xFFFEE2E2),
        border = Color(0xFFEF4444),
        fg = Color(0xFFB91C1C),
        label = "Missed",
    )
    "violation" -> HistoryStateColors(
        bg = Color(0xFFFEE2E2),
        border = Color(0xFFEF4444),
        fg = Color(0xFFB91C1C),
        label = "Violation",
    )
    "in_progress" -> HistoryStateColors(
        bg = Color(0xFFDBEAFE),
        border = Color(0xFF3B82F6),
        fg = Color(0xFF1D4ED8),
        label = "In Progress",
    )
    "reminding" -> HistoryStateColors(
        bg = Color(0xFFDBEAFE),
        border = Color(0xFF3B82F6),
        fg = Color(0xFF1D4ED8),
        label = "Reminding",
    )
    "unscheduled" -> HistoryStateColors(
        bg = Color(0xFFF8FAFC),
        border = Color(0xFFE2E8F0),
        fg = Color(0xFF94A3B8),
        label = "Rest Day",
    )
    "before_created" -> HistoryStateColors(
        bg = Color(0xFFF1F5F9),
        border = Color(0xFFE2E8F0),
        fg = Color(0xFFCBD5E1),
        label = "Before Created",
    )
    "future" -> HistoryStateColors(
        bg = Color(0xFFF1F5F9),
        border = Color(0xFFE2E8F0),
        fg = Color(0xFFCBD5E1),
        label = "Upcoming",
    )
    else -> HistoryStateColors(
        bg = Color(0xFFF8FAFC),
        border = Color(0xFFCBD5E1),
        fg = Color(0xFF334155),
        label = "Pending",
    )
}

@Composable
fun HabitHistoryDialog(
    fallbackTitle: String,
    history: HabitHistory?,
    isLoading: Boolean,
    onShiftMonth: (Long) -> Unit,
    onResetCurrentMonth: () -> Unit,
    onEditDay: (dateIso: String, statusOverride: String, count: Int, note: String) -> Unit,
    onDismiss: () -> Unit,
) {
    var editingDay by remember { mutableStateOf<HabitHistoryDay?>(null) }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth(0.94f)
                .widthIn(max = 520.dp),
            shape = RoundedCornerShape(24.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Row(
                        modifier = Modifier.weight(1f),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Box(
                            modifier = Modifier
                                .width(8.dp)
                                .height(26.dp)
                                .clip(RoundedCornerShape(4.dp))
                                .background(
                                    history?.habit?.color?.let(::parseHabitColor)
                                        ?: MaterialTheme.colorScheme.primary,
                                ),
                        )
                        Text(
                            text = "History · ${history?.habit?.title ?: fallbackTitle}",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Rounded.Close, contentDescription = "Close history")
                    }
                }

                if (isLoading && history != null) {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                }

                if (history == null) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(220.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        if (isLoading) {
                            CircularProgressIndicator()
                        } else {
                            Text(
                                text = "Unable to load check-in history.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                } else {
                    val streakUnit = if (history.habit.frequencyType == "monthly") "mo" else "d"
                    val monthTitle = remember(history.month) {
                        runCatching {
                            YearMonth.parse(history.month)
                                .format(DateTimeFormatter.ofPattern("MMMM yyyy", Locale.ENGLISH))
                        }.getOrElse { history.month }
                    }
                    val isCurrentMonth = history.month == history.today.take(7)

                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 520.dp)
                            .verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            HistoryStatPill(
                                text = "Streak ${history.currentStreak}$streakUnit",
                                bg = Color(0xFFFEF3C7),
                                fg = Color(0xFFB45309),
                            )
                            HistoryStatPill(
                                text = "Best ${history.bestStreak}$streakUnit",
                                bg = MaterialTheme.colorScheme.primaryContainer,
                                fg = MaterialTheme.colorScheme.onPrimaryContainer,
                            )
                            HistoryStatPill(
                                text = "30d ${history.completionRate30d}%",
                                bg = Color(0xFFDCFCE7),
                                fg = Color(0xFF15803D),
                            )
                            HistoryStatPill(
                                text = "On-time ${history.totalCompletions}",
                                bg = MaterialTheme.colorScheme.surfaceVariant,
                                fg = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            HistoryStatPill(
                                text = "Make-ups ${history.lateCompletions}",
                                bg = Color(0xFFFEF3C7),
                                fg = Color(0xFFB45309),
                            )
                            HistoryStatPill(
                                text = "Created ${history.createdDate}",
                                bg = MaterialTheme.colorScheme.surfaceVariant,
                                fg = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }

                        HorizontalDivider()

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                IconButton(
                                    onClick = { onShiftMonth(-1) },
                                    enabled = history.canPrevMonth && !isLoading,
                                ) {
                                    Icon(Icons.Rounded.ChevronLeft, contentDescription = "Previous month")
                                }
                                Column {
                                    Text(
                                        text = monthTitle,
                                        style = MaterialTheme.typography.titleSmall,
                                        fontWeight = FontWeight.Bold,
                                    )
                                    val statsSubtitle = buildString {
                                        append("${history.monthCompletedOnTime}/${history.monthScheduled} on-time")
                                        if (history.monthLateMakeups > 0) {
                                            append(" · ${history.monthLateMakeups} make-up")
                                        }
                                        if (history.monthMissed > 0) {
                                            append(" · ${history.monthMissed} missed")
                                        }
                                    }
                                    Text(
                                        text = statsSubtitle,
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                                IconButton(
                                    onClick = { onShiftMonth(1) },
                                    enabled = history.canNextMonth && !isLoading,
                                ) {
                                    Icon(Icons.Rounded.ChevronRight, contentDescription = "Next month")
                                }
                            }
                            if (!isCurrentMonth) {
                                AssistChip(
                                    onClick = onResetCurrentMonth,
                                    leadingIcon = {
                                        Icon(
                                            imageVector = Icons.Rounded.Today,
                                            contentDescription = null,
                                            modifier = Modifier.size(16.dp),
                                        )
                                    },
                                    label = { Text("Current") },
                                )
                            }
                        }

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            WEEKDAY_SHORT_LABELS.forEach { lbl ->
                                Text(
                                    text = lbl,
                                    style = MaterialTheme.typography.labelSmall,
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    textAlign = TextAlign.Center,
                                    modifier = Modifier.weight(1f),
                                )
                            }
                        }

                        val paddedCells: List<HabitHistoryDay?> = buildList {
                            repeat(history.firstWeekday.coerceIn(0, 6)) { add(null) }
                            addAll(history.days)
                            while (size % 7 != 0) add(null)
                        }

                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            paddedCells.chunked(7).forEach { week ->
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                                ) {
                                    week.forEach { day ->
                                        if (day == null) {
                                            Spacer(
                                                modifier = Modifier
                                                    .weight(1f)
                                                    .height(40.dp),
                                            )
                                        } else {
                                            val colors = historyColorsForState(day.state)
                                            val border = when {
                                                day.isToday -> BorderStroke(2.dp, MaterialTheme.colorScheme.primary)
                                                day.editable -> BorderStroke(1.dp, colors.border)
                                                else -> null
                                            }
                                            Surface(
                                                modifier = Modifier
                                                    .weight(1f)
                                                    .height(40.dp)
                                                    .alpha(if (day.editable) 1f else 0.55f)
                                                    .then(
                                                        if (day.editable) {
                                                            Modifier.clickable { editingDay = day }
                                                        } else {
                                                            Modifier
                                                        },
                                                    ),
                                                shape = RoundedCornerShape(8.dp),
                                                color = colors.bg,
                                                border = border,
                                            ) {
                                                Box(contentAlignment = Alignment.Center) {
                                                    Text(
                                                        text = if (day.note.isNotBlank()) "${day.day}•" else "${day.day}",
                                                        style = MaterialTheme.typography.labelMedium,
                                                        fontWeight = if (day.editable && day.scheduled) {
                                                            FontWeight.Bold
                                                        } else {
                                                            FontWeight.Normal
                                                        },
                                                        color = colors.fg,
                                                    )
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            HistoryStatPill("On Time", Color(0xFFDCFCE7), Color(0xFF15803D))
                            HistoryStatPill("Make-up", Color(0xFFFEF3C7), Color(0xFFB45309))
                            HistoryStatPill("Missed", Color(0xFFFEE2E2), Color(0xFFB91C1C))
                            HistoryStatPill("Pending", Color(0xFFF8FAFC), Color(0xFF475569))
                            HistoryStatPill("Locked", Color(0xFFF1F5F9), Color(0xFF94A3B8))
                        }

                        HorizontalDivider()

                        val logDays = remember(history.days) {
                            history.days
                                .filter { day ->
                                    day.editable && (day.scheduled || day.count > 0 || day.note.isNotBlank())
                                }
                                .reversed()
                        }
                        Text(
                            text = "Month Activity Log (${logDays.size})",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                        )
                        if (logDays.isEmpty()) {
                            Text(
                                text = "No editable scheduled days in this month.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        } else {
                            logDays.forEach { day ->
                                val colors = historyColorsForState(day.state)
                                Surface(
                                    modifier = Modifier.fillMaxWidth(),
                                    shape = RoundedCornerShape(10.dp),
                                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f),
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(horizontal = 10.dp, vertical = 8.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                    ) {
                                        Column(
                                            modifier = Modifier.weight(1f),
                                            verticalArrangement = Arrangement.spacedBy(3.dp),
                                        ) {
                                            Row(
                                                verticalAlignment = Alignment.CenterVertically,
                                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                            ) {
                                                Text(
                                                    text = "${day.date} (${day.weekdayLabel})",
                                                    style = MaterialTheme.typography.labelLarge,
                                                    fontWeight = FontWeight.SemiBold,
                                                )
                                                HistoryStatPill(
                                                    text = colors.label,
                                                    bg = colors.bg,
                                                    fg = colors.fg,
                                                )
                                            }
                                            val subtitle = buildList {
                                                if (history.habit.targetPerDay > 1 || day.count > 0) {
                                                    add("${day.count}/${history.habit.targetPerDay}")
                                                }
                                                if (day.note.isNotBlank()) {
                                                    add("Note: ${day.note}")
                                                }
                                            }.joinToString(" · ").ifBlank {
                                                "Tap edit to adjust status or note"
                                            }
                                            Text(
                                                text = subtitle,
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                maxLines = 2,
                                                overflow = TextOverflow.Ellipsis,
                                            )
                                        }
                                        IconButton(onClick = { editingDay = day }) {
                                            Icon(
                                                imageVector = Icons.Rounded.Edit,
                                                contentDescription = "Edit history entry",
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                ) {
                    TextButton(onClick = onDismiss) {
                        Text("Close")
                    }
                }
            }
        }
    }

    editingDay?.let { targetDay ->
        val habit = history?.habit
        CheckinEditDialog(
            title = habit?.title ?: fallbackTitle,
            dateIso = targetDay.date,
            scheduled = targetDay.scheduled,
            targetPerDay = habit?.targetPerDay ?: 1,
            initialCount = targetDay.count,
            initialCompleted = targetDay.completed,
            initialIsLate = targetDay.isLate,
            initialNote = targetDay.note,
            onDismiss = { editingDay = null },
            onSave = { statusOverride, count, note ->
                onEditDay(targetDay.date, statusOverride, count, note)
                editingDay = null
            },
        )
    }
}

@Composable
private fun HistoryStatPill(
    text: String,
    bg: Color,
    fg: Color,
) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = bg,
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = fg,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
        )
    }
}
