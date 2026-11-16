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
import androidx.compose.material.icons.rounded.CheckCircleOutline
import androidx.compose.material.icons.rounded.Insights
import androidx.compose.material.icons.rounded.LocalFireDepartment
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.HABIT_MODE_OPTIONS
import com.shawnpeng.habittracker.data.StatsSummary
import com.shawnpeng.habittracker.data.parseHabitColor

@Composable
fun StatsScreen(summary: StatsSummary?) {
    val stats = summary ?: StatsSummary()

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Text(
                text = "Streaks & Statistics",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                KpiCard(
                    title = "Best Streak",
                    value = "${stats.bestActiveStreak}d",
                    icon = Icons.Rounded.LocalFireDepartment,
                    accent = MaterialTheme.colorScheme.tertiary,
                    modifier = Modifier.weight(1f),
                )
                KpiCard(
                    title = "30d Rate",
                    value = "${stats.overallCompletionRate30d}%",
                    icon = Icons.Rounded.Insights,
                    accent = MaterialTheme.colorScheme.secondary,
                    modifier = Modifier.weight(1f),
                )
                KpiCard(
                    title = if (stats.lateToday > 0 || stats.violatedToday > 0) {
                        "Today (${stats.lateToday}L/${stats.violatedToday}V)"
                    } else {
                        "Today's Score"
                    },
                    value = "${stats.completedToday}/${stats.scheduledToday}",
                    icon = Icons.Rounded.CheckCircleOutline,
                    accent = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.weight(1f),
                )
            }
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
            ) {
                Column(
                    modifier = Modifier.padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    Text(
                        text = "Last 7 Days Activity",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )

                    if (stats.last7Days.isEmpty()) {
                        Text(
                            text = "No activity recorded in the last 7 days",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    } else {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceAround,
                            verticalAlignment = Alignment.Bottom,
                        ) {
                            stats.last7Days.forEach { point ->
                                val ratio = if (point.scheduledCount > 0) {
                                    (point.completedCount.toFloat() / point.scheduledCount.toFloat())
                                        .coerceIn(0f, 1f)
                                } else {
                                    0f
                                }
                                val barHeightDp = (8f + ratio * 92f).dp
                                val barColor = if (ratio >= 1f && point.scheduledCount > 0) {
                                    MaterialTheme.colorScheme.primary
                                } else {
                                    MaterialTheme.colorScheme.primary.copy(alpha = 0.65f)
                                }

                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.spacedBy(6.dp),
                                ) {
                                    Text(
                                        text = if (point.lateCount > 0) {
                                            "${point.completedCount}/${point.scheduledCount} (+${point.lateCount}L)"
                                        } else {
                                            "${point.completedCount}/${point.scheduledCount}"
                                        },
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                    Box(
                                        modifier = Modifier
                                            .width(24.dp)
                                            .height(100.dp)
                                            .clip(RoundedCornerShape(8.dp))
                                            .background(MaterialTheme.colorScheme.surfaceVariant),
                                        contentAlignment = Alignment.BottomCenter,
                                    ) {
                                        Box(
                                            modifier = Modifier
                                                .width(24.dp)
                                                .height(barHeightDp)
                                                .clip(RoundedCornerShape(8.dp))
                                                .background(barColor),
                                        )
                                    }
                                    Text(
                                        text = point.weekdayLabel,
                                        style = MaterialTheme.typography.labelMedium,
                                        fontWeight = FontWeight.SemiBold,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        item {
            Text(
                text = "Habit Streaks Breakdown",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
        }

        if (stats.habitStats.isEmpty()) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                ) {
                    Text(
                        text = "Start checking in to see streak rankings for each habit.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(24.dp),
                    )
                }
            }
        } else {
            items(stats.habitStats, key = { it.habitId }) { hs ->
                val accentColor = parseHabitColor(hs.color)
                val streakUnit = if (hs.frequencyType == "monthly") "mo" else "d"
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(14.dp),
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
                                    .height(36.dp)
                                    .clip(RoundedCornerShape(3.dp))
                                    .background(accentColor),
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(
                                    text = hs.title,
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.Bold,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                val modeTag = if (hs.mode != "free") {
                                    (HABIT_MODE_OPTIONS.firstOrNull { it.key == hs.mode }?.shortLabel ?: hs.mode) + " · "
                                } else {
                                    ""
                                }
                                val lateTag = if (hs.lateCompletions > 0) {
                                    " · Make-ups: ${hs.lateCompletions}"
                                } else {
                                    ""
                                }
                                Text(
                                    text = "${modeTag}30d rate: ${hs.completionRate30d}% · On-time: ${hs.totalCompletions}$lateTag",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }

                        Column(horizontalAlignment = Alignment.End) {
                            Text(
                                text = "Current: ${hs.currentStreak}$streakUnit",
                                style = MaterialTheme.typography.labelLarge,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.tertiary,
                            )
                            Text(
                                text = "Best: ${hs.bestStreak}$streakUnit",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun KpiCard(
    title: String,
    value: String,
    icon: ImageVector,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = accent,
                modifier = Modifier.size(22.dp),
            )
            Text(
                text = value,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
            )
            Text(
                text = title,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}
