package com.shawnpeng.habittracker.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

@Composable
fun CheckinEditDialog(
    title: String,
    dateIso: String,
    scheduled: Boolean,
    targetPerDay: Int,
    initialCount: Int,
    initialCompleted: Boolean,
    initialIsLate: Boolean,
    initialNote: String,
    onDismiss: () -> Unit,
    onSave: (statusOverride: String, count: Int, note: String) -> Unit,
) {
    val safeTarget = targetPerDay.coerceAtLeast(1)
    val startingCompleted = initialCompleted || initialCount >= safeTarget
    val startingStatus = when {
        startingCompleted && initialIsLate -> "late_makeup"
        startingCompleted -> "on_time"
        else -> "clear"
    }

    var selectedStatus by remember(dateIso, initialCount, initialCompleted, initialIsLate) {
        mutableStateOf(startingStatus)
    }
    var countText by remember(dateIso, initialCount) {
        mutableStateOf(initialCount.toString())
    }
    var noteText by remember(dateIso, initialNote) {
        mutableStateOf(initialNote)
    }
    var errorText by remember(dateIso) { mutableStateOf<String?>(null) }

    val statusChoices = remember {
        listOf(
            "on_time" to "On Time",
            "late_makeup" to "Overdue Make-up",
            "clear" to "Not Completed",
        )
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = "Edit Check-in · $title",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = if (scheduled) "$dateIso · Scheduled" else "$dateIso · Unscheduled day",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text(
                    text = "Completion Status",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    statusChoices.forEach { (key, label) ->
                        FilterChip(
                            selected = selectedStatus == key,
                            onClick = {
                                selectedStatus = key
                                val parsed = countText.trim().toIntOrNull() ?: 0
                                if ((key == "on_time" || key == "late_makeup") && parsed < safeTarget) {
                                    countText = safeTarget.toString()
                                } else if (key == "clear" && parsed >= safeTarget) {
                                    countText = "0"
                                }
                                errorText = null
                            },
                            label = { Text(label) },
                        )
                    }
                }
                Text(
                    text = "On Time counts toward streaks & SLI; Overdue Make-up records completion without streak credit.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    IconButton(
                        onClick = {
                            val current = countText.trim().toIntOrNull() ?: 0
                            val next = (current - 1).coerceAtLeast(0)
                            countText = next.toString()
                            if (next < safeTarget && selectedStatus != "clear") {
                                selectedStatus = "clear"
                            }
                            errorText = null
                        },
                    ) {
                        Icon(Icons.Rounded.Remove, contentDescription = "Decrease count")
                    }
                    OutlinedTextField(
                        value = countText,
                        onValueChange = { raw ->
                            countText = raw
                            val parsed = raw.trim().toIntOrNull()
                            if (parsed != null) {
                                if (parsed >= safeTarget && selectedStatus == "clear") {
                                    selectedStatus = "on_time"
                                } else if (parsed in 0 until safeTarget && selectedStatus != "clear") {
                                    selectedStatus = "clear"
                                }
                            }
                            errorText = null
                        },
                        label = { Text("Count") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.width(104.dp),
                    )
                    IconButton(
                        onClick = {
                            val current = countText.trim().toIntOrNull() ?: 0
                            val next = (current + 1).coerceAtMost(1000)
                            countText = next.toString()
                            if (next >= safeTarget && selectedStatus == "clear") {
                                selectedStatus = "on_time"
                            }
                            errorText = null
                        },
                    ) {
                        Icon(Icons.Rounded.Add, contentDescription = "Increase count")
                    }
                    Text(
                        text = "/ $safeTarget target",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }

                OutlinedTextField(
                    value = noteText,
                    onValueChange = {
                        if (it.length <= 300) {
                            noteText = it
                        }
                    },
                    label = { Text("Check-in Note (optional)") },
                    maxLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )

                errorText?.let { err ->
                    Text(
                        text = err,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val parsedCount = countText.trim().toIntOrNull()
                    if (parsedCount == null || parsedCount !in 0..1000) {
                        errorText = "Count must be between 0 and 1000"
                        return@TextButton
                    }
                    if ((selectedStatus == "on_time" || selectedStatus == "late_makeup") && parsedCount < safeTarget) {
                        errorText = "Completed status requires count >= $safeTarget"
                        return@TextButton
                    }
                    if (selectedStatus == "clear" && parsedCount >= safeTarget) {
                        errorText = "Count must be less than $safeTarget for Not Completed"
                        return@TextButton
                    }
                    onSave(selectedStatus, parsedCount, noteText.trim())
                },
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                if (initialCount > 0 || initialNote.isNotBlank()) {
                    TextButton(
                        onClick = { onSave("clear", 0, "") },
                    ) {
                        Text("Clear Day", color = MaterialTheme.colorScheme.error)
                    }
                }
                TextButton(onClick = onDismiss) {
                    Text("Cancel")
                }
            }
        },
    )
}
