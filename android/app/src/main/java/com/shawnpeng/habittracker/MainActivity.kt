package com.shawnpeng.habittracker

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Logout
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.Checklist
import androidx.compose.material.icons.rounded.Insights
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Today
import androidx.compose.material.icons.rounded.Verified
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.ui.HabitUiState
import com.shawnpeng.habittracker.ui.HabitViewModel
import com.shawnpeng.habittracker.ui.HabitViewModelFactory
import com.shawnpeng.habittracker.ui.components.HabitFormDialog
import com.shawnpeng.habittracker.ui.screens.AuthScreen
import com.shawnpeng.habittracker.ui.screens.HabitsScreen
import com.shawnpeng.habittracker.ui.screens.ScheduleScreen
import com.shawnpeng.habittracker.ui.screens.SliDashboardScreen
import com.shawnpeng.habittracker.ui.screens.StatsScreen
import com.shawnpeng.habittracker.ui.screens.TodayScreen
import com.shawnpeng.habittracker.ui.theme.HabitTrackerTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            HabitTrackerTheme {
                val vm: HabitViewModel = viewModel(
                    factory = HabitViewModelFactory(applicationContext),
                )
                val uiState by vm.uiState.collectAsStateWithLifecycle()

                when {
                    uiState.isInitializing -> LoadingSplash()
                    !uiState.isAuthenticated -> AuthScreen(
                        initialServerUrl = uiState.serverUrl,
                        isSubmitting = uiState.isAuthSubmitting,
                        errorMessage = uiState.authError,
                        onLogin = vm::login,
                        onRegister = vm::register,
                    )
                    else -> MainShell(uiState = uiState, vm = vm)
                }
            }
        }
    }
}

@Composable
private fun LoadingSplash() {
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            CircularProgressIndicator()
            Text(
                text = "正在连接服务器...",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 12.dp),
            )
        }
    }
}

@Composable
private fun MainShell(
    uiState: HabitUiState,
    vm: HabitViewModel,
) {
    val snackbarHostState = remember { SnackbarHostState() }
    var showCreateDialog by remember { mutableStateOf(false) }
    var editingHabit by remember { mutableStateOf<Habit?>(null) }

    LaunchedEffect(uiState.snackbarMessage) {
        val msg = uiState.snackbarMessage
        if (!msg.isNullOrBlank()) {
            snackbarHostState.showSnackbar(msg)
            vm.consumeSnackbar()
        }
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        snackbarHost = { SnackbarHost(hostState = snackbarHostState) },
        topBar = {
            Column {
                TopAppBar(
                    title = {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.Verified,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(24.dp),
                            )
                            Column {
                                Text(
                                    text = "Habit Tracker",
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold,
                                )
                                uiState.currentUser?.name?.let { name ->
                                    Text(
                                        text = "Hi, $name",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                        }
                    },
                    actions = {
                        IconButton(onClick = vm::refreshCurrentTab) {
                            Icon(
                                imageVector = Icons.Rounded.Refresh,
                                contentDescription = "刷新",
                            )
                        }
                        IconButton(onClick = vm::logout) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Rounded.Logout,
                                contentDescription = "退出登录",
                            )
                        }
                    },
                )
                HorizontalDivider()
            }
        },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = uiState.selectedTab == 0,
                    onClick = { vm.selectTab(0) },
                    icon = { Icon(Icons.Rounded.Today, contentDescription = null) },
                    label = { Text("今日") },
                )
                NavigationBarItem(
                    selected = uiState.selectedTab == 1,
                    onClick = { vm.selectTab(1) },
                    icon = { Icon(Icons.Rounded.CalendarMonth, contentDescription = null) },
                    label = { Text("待办") },
                )
                NavigationBarItem(
                    selected = uiState.selectedTab == 2,
                    onClick = { vm.selectTab(2) },
                    icon = { Icon(Icons.Rounded.Checklist, contentDescription = null) },
                    label = { Text("习惯") },
                )
                NavigationBarItem(
                    selected = uiState.selectedTab == 3,
                    onClick = { vm.selectTab(3) },
                    icon = { Icon(Icons.Rounded.Insights, contentDescription = null) },
                    label = { Text("统计") },
                )
                NavigationBarItem(
                    selected = uiState.selectedTab == 4,
                    onClick = { vm.selectTab(4) },
                    icon = { Icon(Icons.Rounded.Speed, contentDescription = null) },
                    label = { Text("SLI") },
                )
            }
        },
        floatingActionButton = {
            if (uiState.selectedTab == 0 || uiState.selectedTab == 2) {
                FloatingActionButton(
                    onClick = {
                        editingHabit = null
                        showCreateDialog = true
                    },
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                ) {
                    Icon(Icons.Rounded.Add, contentDescription = "新建习惯")
                }
            }
        },
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding),
        ) {
            when (uiState.selectedTab) {
                0 -> TodayScreen(
                    selectedDate = uiState.selectedDate,
                    habits = uiState.todayHabits,
                    onShiftDate = vm::shiftDate,
                    onJumpToday = vm::jumpToToday,
                    onPrimaryCheckin = vm::primaryCheckin,
                    onDecrementCheckin = vm::decrementCheckin,
                    onUpdateNote = vm::updateCheckinNote,
                )
                1 -> ScheduleScreen(
                    period = uiState.schedulePeriod,
                    anchorDate = uiState.scheduleAnchorDate,
                    schedule = uiState.periodSchedule,
                    onSelectPeriod = vm::setSchedulePeriod,
                    onShiftPeriod = vm::shiftSchedulePeriod,
                    onResetCurrent = vm::resetScheduleToCurrent,
                    onPrimaryCheckin = vm::schedulePrimaryCheckin,
                    onDecrementCheckin = vm::scheduleDecrementCheckin,
                )
                2 -> HabitsScreen(
                    habits = uiState.allHabits,
                    showArchived = uiState.showArchived,
                    onToggleShowArchived = vm::toggleShowArchived,
                    onEditHabit = { habit ->
                        editingHabit = habit
                        showCreateDialog = true
                    },
                    onToggleArchive = vm::toggleArchive,
                    onDeleteHabit = vm::deleteHabit,
                )
                3 -> StatsScreen(summary = uiState.statsSummary)
                else -> SliDashboardScreen(
                    dashboard = uiState.sliDashboard,
                    selectedWindowDays = uiState.sliWindowDays,
                    onSelectWindow = vm::selectSliWindow,
                    onUpdateTargetSlo = vm::updateHabitTargetSlo,
                )
            }

            if (uiState.isRefreshing) {
                LinearProgressIndicator(
                    modifier = Modifier
                        .fillMaxWidth()
                        .align(Alignment.TopCenter),
                )
            }
        }
    }

    if (showCreateDialog) {
        HabitFormDialog(
            existing = editingHabit,
            onDismiss = {
                showCreateDialog = false
                editingHabit = null
            },
            onSave = { request ->
                vm.saveHabit(editingHabit?.id, request)
                showCreateDialog = false
                editingHabit = null
            },
        )
    }
}
