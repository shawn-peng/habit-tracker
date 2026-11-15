package com.shawnpeng.habittracker.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.Insights
import androidx.compose.material.icons.rounded.LocalFireDepartment
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shawnpeng.habittracker.data.HabitSliItem
import com.shawnpeng.habittracker.data.SliDashboard
import com.shawnpeng.habittracker.data.parseHabitColor
import java.util.Locale
import kotlin.math.abs
import kotlin.math.round

private val HealthyGreen = Color(0xFF10B981)
private val WarningAmber = Color(0xFFD97706)
private val BreachedRed = Color(0xFFEF4444)
private val MutedSlate = Color(0xFF64748B)

@Composable
fun SliDashboardScreen(
    dashboard: SliDashboard?,
    selectedWindowDays: Int,
    onSelectWindow: (Int) -> Unit,
    onUpdateTargetSlo: (String, Double) -> Unit,
) {
    val dash = dashboard ?: SliDashboard(windowDays = selectedWindowDays)
    var editingHabitSlo by remember { mutableStateOf<HabitSliItem?>(null) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(
                        text = "个人习惯 SLI 看板",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                    SliStatusBadge(status = dash.overallStatus)
                }

                Text(
                    text = "基于 SRE 可靠性指标、错误预算与燃烧率的习惯达成分析",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(7, 30, 90).forEach { days ->
                        FilterChip(
                            selected = selectedWindowDays == days,
                            onClick = { onSelectWindow(days) },
                            label = { Text("$days 天") },
                        )
                    }
                }
            }
        }

        item {
            val budgetAccent = when {
                dash.overallErrorBudgetRemainingPct > 50.0 -> HealthyGreen
                dash.overallErrorBudgetRemainingPct > 25.0 -> WarningAmber
                else -> BreachedRed
            }
            val burnAccent = when {
                dash.overallBurnRate <= 1.0 -> HealthyGreen
                dash.overallBurnRate <= 1.5 -> WarningAmber
                else -> BreachedRed
            }

            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    SliKpiCard(
                        title = "整体 SLI",
                        value = "${dash.overallSli}%",
                        subtitle = "目标 ${dash.overallTargetSlo}%",
                        icon = Icons.Rounded.Speed,
                        accent = statusColor(dash.overallStatus),
                        modifier = Modifier.weight(1f),
                    )
                    SliKpiCard(
                        title = "错误预算",
                        value = "${dash.overallErrorBudgetRemainingPct}%",
                        subtitle = "${formatSignedOneDecimal(dash.overallErrorBudgetRemainingDays)}d / ${dash.overallErrorBudgetAllowedDays}d",
                        icon = Icons.Rounded.CheckCircle,
                        accent = budgetAccent,
                        modifier = Modifier.weight(1f),
                    )
                    SliKpiCard(
                        title = "燃烧率",
                        value = "${dash.overallBurnRate}x",
                        subtitle = "7d ${dash.overallBurnRate7d}x",
                        icon = Icons.Rounded.LocalFireDepartment,
                        accent = burnAccent,
                        modifier = Modifier.weight(1f),
                    )
                }

                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 14.dp, vertical = 12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = "SLO 达标概览（${dash.windowDays} 天窗口）",
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            text = "达标 ${dash.healthyCount} · 预警 ${dash.warningCount} · 违约 ${dash.breachedCount}",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        if (dash.activeHabitsCount > 0) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.45f),
                    ),
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalAlignment = Alignment.Top,
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.Insights,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(24.dp),
                        )
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(
                                text = "SRE 诊断洞察",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold,
                            )
                            val burnLine = if (!dash.topBurnHabitTitle.isNullOrBlank() && dash.topBurnRate != null) {
                                "最高燃烧率习惯：${dash.topBurnHabitTitle}（${dash.topBurnRate}x）"
                            } else {
                                "所有习惯燃烧率均为 0.0x，当前窗口无缺卡。"
                            }
                            val weakLine = if (!dash.weakestWeekday.isNullOrBlank() && dash.weakestWeekdaySli != null) {
                                "最薄弱星期：${localizeWeekdayLabel(dash.weakestWeekday)}（SLI ${dash.weakestWeekdaySli}%）"
                            } else {
                                "所有已排期星期的可靠度均达到 100%。"
                            }
                            Text(
                                text = burnLine,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurface,
                            )
                            Text(
                                text = weakLine,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
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
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = "滚动 SLI 趋势（${dash.windowDays} 天）",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = "SLO ${dash.overallTargetSlo}%",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    if (dash.trend.isEmpty()) {
                        Text(
                            text = "暂无趋势数据",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    } else {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceAround,
                            verticalAlignment = Alignment.Bottom,
                        ) {
                            dash.trend.forEach { pt ->
                                val ratio = if (pt.hasActivity) {
                                    (pt.sli / 100.0).toFloat().coerceIn(0f, 1f)
                                } else {
                                    0f
                                }
                                val barHeightDp = if (pt.hasActivity) (6f + ratio * 94f).dp else 6.dp
                                val barColor = when {
                                    !pt.hasActivity -> MaterialTheme.colorScheme.outlineVariant
                                    pt.sli >= dash.overallTargetSlo -> HealthyGreen
                                    pt.sli >= dash.overallTargetSlo - 10.0 -> WarningAmber
                                    else -> BreachedRed
                                }
                                val barWidth = if (dash.trend.size > 8) 18.dp else 24.dp

                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.spacedBy(4.dp),
                                ) {
                                    Text(
                                        text = if (pt.hasActivity) "${pt.sli.toInt()}%" else "—",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                    Box(
                                        modifier = Modifier
                                            .width(barWidth)
                                            .height(100.dp)
                                            .clip(RoundedCornerShape(6.dp))
                                            .background(MaterialTheme.colorScheme.surfaceVariant),
                                        contentAlignment = Alignment.BottomCenter,
                                    ) {
                                        Box(
                                            modifier = Modifier
                                                .width(barWidth)
                                                .height(barHeightDp)
                                                .clip(RoundedCornerShape(6.dp))
                                                .background(barColor),
                                        )
                                    }
                                    Text(
                                        text = pt.label,
                                        style = MaterialTheme.typography.labelSmall,
                                        maxLines = 1,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        if (dash.weekdaySli.isNotEmpty()) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                ) {
                    Column(
                        modifier = Modifier.padding(18.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(
                            text = "星期可靠性分布",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        dash.weekdaySli.forEach { wd ->
                            val hasSched = wd.scheduledCount > 0
                            val fraction = if (hasSched) (wd.sli / 100.0).toFloat().coerceIn(0f, 1f) else 0f
                            val barColor = when {
                                !hasSched -> MaterialTheme.colorScheme.outlineVariant
                                wd.sli >= dash.overallTargetSlo -> HealthyGreen
                                wd.sli >= dash.overallTargetSlo - 10.0 -> WarningAmber
                                else -> BreachedRed
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                Text(
                                    text = localizeWeekdayLabel(wd.label),
                                    style = MaterialTheme.typography.labelMedium,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.width(36.dp),
                                )
                                LinearProgressIndicator(
                                    progress = { fraction },
                                    modifier = Modifier
                                        .weight(1f)
                                        .height(8.dp)
                                        .clip(RoundedCornerShape(4.dp)),
                                    color = barColor,
                                    trackColor = MaterialTheme.colorScheme.surfaceVariant,
                                    strokeCap = StrokeCap.Round,
                                )
                                Text(
                                    text = if (hasSched) "${wd.sli}% (${wd.completedCount}/${wd.scheduledCount})" else "— (0/0)",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    textAlign = TextAlign.End,
                                    modifier = Modifier.width(92.dp),
                                )
                            }
                        }
                    }
                }
            }
        }

        item {
            Text(
                text = "各习惯 SLI 与错误预算明细",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
        }

        if (dash.habits.isEmpty()) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                ) {
                    Text(
                        text = "创建习惯并开始打卡后，即可查看各习惯的 SLI、目标 SLO、错误预算与燃烧率诊断。",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(24.dp),
                    )
                }
            }
        } else {
            items(dash.habits, key = { it.habitId }) { item ->
                HabitSliCard(
                    item = item,
                    windowDays = dash.windowDays,
                    onEditSlo = { editingHabitSlo = item },
                )
            }
        }
    }

    editingHabitSlo?.let { targetItem ->
        EditSloDialog(
            item = targetItem,
            onDismiss = { editingHabitSlo = null },
            onConfirm = { newSlo ->
                onUpdateTargetSlo(targetItem.habitId, newSlo)
                editingHabitSlo = null
            },
        )
    }
}

@Composable
private fun HabitSliCard(
    item: HabitSliItem,
    windowDays: Int,
    onEditSlo: () -> Unit,
) {
    val accentColor = parseHabitColor(item.color)
    val budgetColor = when {
        item.errorBudgetRemainingPct > 50.0 -> HealthyGreen
        item.errorBudgetRemainingPct > 25.0 -> WarningAmber
        else -> BreachedRed
    }
    val budgetFraction = (item.errorBudgetRemainingPct / 100.0).toFloat().coerceIn(0f, 1f)

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
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
                            .height(32.dp)
                            .clip(RoundedCornerShape(3.dp))
                            .background(accentColor),
                    )
                    Spacer(modifier = Modifier.width(10.dp))
                    Text(
                        text = item.title,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    SliStatusBadge(status = item.status)
                    IconButton(onClick = onEditSlo) {
                        Icon(
                            imageVector = Icons.Rounded.Edit,
                            contentDescription = "调整目标 SLO",
                            modifier = Modifier.size(18.dp),
                        )
                    }
                }
            }

            Text(
                text = "${windowDays}d SLI ${item.currentSli}% / SLO ${item.targetSlo}% (${formatSignedOneDecimal(item.sliDelta)}%) · 7d ${item.sli7d}% · 30d ${item.sli30d}% · 90d ${item.sli90d}%",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            LinearProgressIndicator(
                progress = { budgetFraction },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(8.dp)
                    .clip(RoundedCornerShape(4.dp)),
                color = budgetColor,
                trackColor = MaterialTheme.colorScheme.surfaceVariant,
                strokeCap = StrokeCap.Round,
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "预算剩余 ${item.errorBudgetRemainingPct}%（缺卡 ${item.errorBudgetUsedDays}/${item.errorBudgetAllowedDays}d，余 ${formatSignedOneDecimal(item.errorBudgetRemainingDays)}d）",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f),
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "燃烧 ${item.burnRate}x · 7d ${item.burnRate7d}x",
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                    color = statusColor(item.status),
                )
            }
        }
    }
}

@Composable
private fun EditSloDialog(
    item: HabitSliItem,
    onDismiss: () -> Unit,
    onConfirm: (Double) -> Unit,
) {
    var sloText by remember(item) { mutableStateOf(item.targetSlo.toString()) }
    var errorMsg by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                text = "调整目标 SLO · ${item.title}",
                fontWeight = FontWeight.Bold,
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "选择预设目标或输入自定义可靠性目标（1% - 100%）：",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    val parsed = sloText.trim().toDoubleOrNull()
                    listOf(80.0, 85.0, 90.0, 95.0, 100.0).forEach { preset ->
                        FilterChip(
                            selected = parsed != null && abs(parsed - preset) < 0.05,
                            onClick = {
                                sloText = preset.toString()
                                errorMsg = null
                            },
                            label = { Text("${preset.toInt()}%") },
                        )
                    }
                }
                OutlinedTextField(
                    value = sloText,
                    onValueChange = {
                        sloText = it
                        errorMsg = null
                    },
                    label = { Text("目标 SLO (%)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )
                if (errorMsg != null) {
                    Text(
                        text = errorMsg.orEmpty(),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val parsed = sloText.trim().toDoubleOrNull()
                    if (parsed == null || parsed !in 1.0..100.0) {
                        errorMsg = "目标 SLO 需在 1 到 100 之间"
                        return@TextButton
                    }
                    onConfirm(round(parsed * 10.0) / 10.0)
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

@Composable
private fun SliKpiCard(
    title: String,
    value: String,
    subtitle: String,
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
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = accent,
                modifier = Modifier.size(20.dp),
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
            Text(
                text = subtitle,
                style = MaterialTheme.typography.labelSmall,
                color = accent,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun SliStatusBadge(status: String) {
    val fg = statusColor(status)
    val label = when (status) {
        "healthy" -> "达标"
        "warning" -> "预警"
        "breached" -> "违约"
        else -> "暂无数据"
    }
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = fg.copy(alpha = 0.14f),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            if (status == "warning" || status == "breached") {
                Icon(
                    imageVector = Icons.Rounded.Warning,
                    contentDescription = null,
                    tint = fg,
                    modifier = Modifier.size(12.dp),
                )
            }
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
                color = fg,
            )
        }
    }
}

private fun statusColor(status: String): Color = when (status) {
    "healthy" -> HealthyGreen
    "warning" -> WarningAmber
    "breached" -> BreachedRed
    else -> MutedSlate
}

private fun localizeWeekdayLabel(label: String): String = when (label) {
    "Mon" -> "周一"
    "Tue" -> "周二"
    "Wed" -> "周三"
    "Thu" -> "周四"
    "Fri" -> "周五"
    "Sat" -> "周六"
    "Sun" -> "周日"
    else -> label
}

private fun formatSignedOneDecimal(value: Double): String =
    String.format(Locale.US, "%+.1f", value)
