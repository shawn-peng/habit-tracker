package com.shawnpeng.habittracker.ui

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.shawnpeng.habittracker.data.ApiException
import com.shawnpeng.habittracker.data.CheckinRequest
import com.shawnpeng.habittracker.data.DEFAULT_EMULATOR_URL
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.data.HabitApiClient
import com.shawnpeng.habittracker.data.HabitCreateRequest
import com.shawnpeng.habittracker.data.HabitToday
import com.shawnpeng.habittracker.data.HabitUpdateRequest
import com.shawnpeng.habittracker.data.PeriodSchedule
import com.shawnpeng.habittracker.data.RemindersOverview
import com.shawnpeng.habittracker.data.ScheduleHabitItem
import com.shawnpeng.habittracker.data.SessionPreferences
import com.shawnpeng.habittracker.data.SliDashboard
import com.shawnpeng.habittracker.data.StatsSummary
import com.shawnpeng.habittracker.data.UserPublic
import com.shawnpeng.habittracker.data.toHabit
import com.shawnpeng.habittracker.notifications.AndroidHabitAlarmScheduler
import com.shawnpeng.habittracker.notifications.HabitAlarmController
import com.shawnpeng.habittracker.notifications.HabitNotificationHelper
import com.shawnpeng.habittracker.notifications.NoOpHabitAlarmController
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class HabitUiState(
    val isInitializing: Boolean = true,
    val isAuthenticated: Boolean = false,
    val isAuthSubmitting: Boolean = false,
    val isRefreshing: Boolean = false,
    val authError: String? = null,
    val authInfoMessage: String? = null,
    val pendingVerificationEmail: String? = null,
    val resetCodeSentEmail: String? = null,
    val showChangePasswordDialog: Boolean = false,
    val isChangingPassword: Boolean = false,
    val changePasswordError: String? = null,
    val serverUrl: String = DEFAULT_EMULATOR_URL,
    val currentUser: UserPublic? = null,
    val selectedTab: Int = 0,
    val selectedDate: LocalDate = LocalDate.now(),
    val todayHabits: List<HabitToday> = emptyList(),
    val schedulePeriod: String = "week",
    val scheduleAnchorDate: LocalDate = LocalDate.now(),
    val periodSchedule: PeriodSchedule? = null,
    val allHabits: List<Habit> = emptyList(),
    val showArchived: Boolean = false,
    val statsSummary: StatsSummary? = null,
    val sliWindowDays: Int = 30,
    val sliDashboard: SliDashboard? = null,
    val remindersMuted: Boolean = false,
    val showRemindersDialog: Boolean = false,
    val remindersOverview: RemindersOverview? = null,
    val isLoadingReminders: Boolean = false,
    val snackbarMessage: String? = null,
)

private const val TAB_CACHE_TTL_MS = 45_000L

private data class TabCacheEntry(
    val data: Any,
    val fetchedAtMs: Long,
    val generation: Int,
)

class HabitViewModel(
    private val prefs: SessionPreferences,
    private val api: HabitApiClient = HabitApiClient(),
    private val alarmController: HabitAlarmController = NoOpHabitAlarmController,
) : ViewModel() {

    private val _uiState = MutableStateFlow(HabitUiState())
    val uiState: StateFlow<HabitUiState> = _uiState.asStateFlow()

    private var tabLoadJob: Job? = null
    private val tabMutationGen = IntArray(5)
    private val tabDirty = BooleanArray(5) { true }
    private val tabCacheEntries = mutableMapOf<Pair<Int, String>, TabCacheEntry>()

    init {
        initializeSession()
    }

    private fun currentParamKey(tabIndex: Int, state: HabitUiState = _uiState.value): String =
        when (tabIndex) {
            0 -> isoDate(state.selectedDate)
            1 -> "${state.schedulePeriod}|${isoDate(state.scheduleAnchorDate)}|${isoDate(LocalDate.now())}"
            2 -> state.showArchived.toString()
            3 -> isoDate(LocalDate.now())
            else -> "${state.sliWindowDays}|${isoDate(LocalDate.now())}"
        }

    @Suppress("UNCHECKED_CAST")
    private fun applyTabData(tabIndex: Int, data: Any) {
        when (tabIndex) {
            0 -> _uiState.update { it.copy(todayHabits = data as List<HabitToday>) }
            1 -> _uiState.update { it.copy(periodSchedule = data as PeriodSchedule) }
            2 -> _uiState.update { it.copy(allHabits = data as List<Habit>) }
            3 -> _uiState.update { it.copy(statsSummary = data as StatsSummary) }
            else -> _uiState.update { it.copy(sliDashboard = data as SliDashboard) }
        }
    }

    private fun isCacheFresh(key: Pair<Int, String>): Boolean {
        val tabIndex = key.first
        if (tabDirty[tabIndex]) return false
        val entry = tabCacheEntries[key] ?: return false
        if (entry.generation != tabMutationGen[tabIndex]) return false
        return (System.currentTimeMillis() - entry.fetchedAtMs) < TAB_CACHE_TTL_MS
    }

    private fun storeCacheEntry(key: Pair<Int, String>, data: Any, generation: Int): Boolean {
        val tabIndex = key.first
        if (generation != tabMutationGen[tabIndex]) return false
        tabCacheEntries[key] = TabCacheEntry(
            data = data,
            fetchedAtMs = System.currentTimeMillis(),
            generation = generation,
        )
        tabDirty[tabIndex] = false
        return true
    }

    private fun invalidateTabs(vararg tabs: Int) {
        for (tab in tabs) {
            tabDirty[tab] = true
            tabMutationGen[tab]++
        }
    }

    private fun clearTabCache() {
        tabLoadJob?.cancel()
        tabLoadJob = null
        tabCacheEntries.clear()
        for (i in 0 until 5) {
            tabDirty[i] = true
            tabMutationGen[i]++
        }
        _uiState.update {
            it.copy(
                isRefreshing = false,
                todayHabits = emptyList(),
                allHabits = emptyList(),
                statsSummary = null,
                sliDashboard = null,
                periodSchedule = null,
            )
        }
    }

    fun initializeSession() {
        viewModelScope.launch {
            _uiState.update { it.copy(isInitializing = true, authError = null) }
            val savedUrl = prefs.getServerUrl()
            val savedToken = prefs.getToken()

            try {
                val normalized = api.setBaseUrl(savedUrl)
                _uiState.update { it.copy(serverUrl = normalized) }
            } catch (_: ApiException) {
                api.setBaseUrl(DEFAULT_EMULATOR_URL)
                _uiState.update { it.copy(serverUrl = DEFAULT_EMULATOR_URL) }
            }

            if (savedToken.isNullOrBlank()) {
                _uiState.update {
                    it.copy(isInitializing = false, isAuthenticated = false, currentUser = null)
                }
                return@launch
            }

            api.authToken = savedToken
            try {
                val me = api.getMe()
                val muted = prefs.getRemindersMuted()
                _uiState.update {
                    it.copy(
                        isInitializing = false,
                        isAuthenticated = true,
                        currentUser = me,
                        remindersMuted = muted,
                    )
                }
                invalidateTabs(0, 1, 2, 3, 4)
                tabLoadJob?.cancel()
                loadTabData(_uiState.value.selectedTab, force = true)
                viewModelScope.launch { refreshAndSyncAlarms() }
            } catch (_: ApiException) {
                api.authToken = null
                prefs.clearToken()
                _uiState.update {
                    it.copy(
                        isInitializing = false,
                        isAuthenticated = false,
                        currentUser = null,
                    )
                }
            }
        }
    }

    fun setServerUrl(url: String) {
        _uiState.update { it.copy(serverUrl = url) }
    }

    fun login(serverUrl: String, email: String, password: String) {
        val cleanEmail = email.trim()
        if (cleanEmail.isEmpty() || password.isEmpty()) {
            _uiState.update { it.copy(authError = "请输入邮箱和密码", authInfoMessage = null) }
            return
        }

        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isAuthSubmitting = true,
                    authError = null,
                    authInfoMessage = null,
                )
            }
            try {
                val normalizedUrl = api.setBaseUrl(serverUrl)
                prefs.setServerUrl(normalizedUrl)
                val tokenResp = api.login(email = cleanEmail, password = password)
                prefs.setToken(tokenResp.accessToken)
                val muted = prefs.getRemindersMuted()
                _uiState.update {
                    it.copy(
                        isAuthSubmitting = false,
                        isAuthenticated = true,
                        serverUrl = normalizedUrl,
                        currentUser = tokenResp.user,
                        selectedTab = 0,
                        selectedDate = LocalDate.now(),
                        authInfoMessage = null,
                        pendingVerificationEmail = null,
                        resetCodeSentEmail = null,
                        remindersMuted = muted,
                    )
                }
                clearTabCache()
                loadTabData(0, force = true)
                viewModelScope.launch { refreshAndSyncAlarms() }
            } catch (exc: ApiException) {
                if (exc.statusCode == 403) {
                    _uiState.update {
                        it.copy(
                            isAuthSubmitting = false,
                            pendingVerificationEmail = cleanEmail,
                            authInfoMessage = "该账号尚未完成邮箱验证，请输入 6 位验证码或点击重新发送验证码",
                            authError = null,
                        )
                    }
                } else {
                    _uiState.update {
                        it.copy(isAuthSubmitting = false, authError = exc.message)
                    }
                }
            }
        }
    }

    fun register(serverUrl: String, name: String, email: String, password: String) {
        val cleanName = name.trim()
        val cleanEmail = email.trim()
        if (cleanName.isEmpty()) {
            _uiState.update { it.copy(authError = "请输入你的名字", authInfoMessage = null) }
            return
        }
        if (cleanEmail.isEmpty() || password.length < 6) {
            _uiState.update {
                it.copy(authError = "请输入有效邮箱且密码至少 6 位", authInfoMessage = null)
            }
            return
        }

        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isAuthSubmitting = true,
                    authError = null,
                    authInfoMessage = null,
                )
            }
            try {
                val normalizedUrl = api.setBaseUrl(serverUrl)
                prefs.setServerUrl(normalizedUrl)
                val resp = api.register(
                    name = cleanName,
                    email = cleanEmail,
                    password = password,
                )
                val info = if (!resp.devVerificationCode.isNullOrBlank()) {
                    "6 位验证码已发送至 $cleanEmail（有效期 ${resp.expiresInMinutes} 分钟，开发模式验证码：${resp.devVerificationCode}）"
                } else {
                    "6 位验证码已发送至 $cleanEmail，有效期 ${resp.expiresInMinutes} 分钟，请查收邮件"
                }
                _uiState.update {
                    it.copy(
                        isAuthSubmitting = false,
                        serverUrl = normalizedUrl,
                        pendingVerificationEmail = cleanEmail,
                        authInfoMessage = info,
                        resetCodeSentEmail = null,
                    )
                }
            } catch (exc: ApiException) {
                _uiState.update {
                    it.copy(isAuthSubmitting = false, authError = exc.message)
                }
            }
        }
    }

    fun verifyRegistrationEmail(serverUrl: String, email: String, code: String) {
        val cleanEmail = email.trim()
        val cleanCode = code.trim()
        if (cleanEmail.isEmpty()) {
            _uiState.update { it.copy(authError = "请输入注册邮箱") }
            return
        }
        if (cleanCode.length != 6 || !cleanCode.all { it.isDigit() }) {
            _uiState.update { it.copy(authError = "请输入 6 位数字验证码") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isAuthSubmitting = true, authError = null) }
            try {
                val normalizedUrl = api.setBaseUrl(serverUrl)
                prefs.setServerUrl(normalizedUrl)
                val tokenResp = api.verifyEmail(email = cleanEmail, code = cleanCode)
                prefs.setToken(tokenResp.accessToken)
                val muted = prefs.getRemindersMuted()
                _uiState.update {
                    it.copy(
                        isAuthSubmitting = false,
                        isAuthenticated = true,
                        serverUrl = normalizedUrl,
                        currentUser = tokenResp.user,
                        selectedTab = 0,
                        selectedDate = LocalDate.now(),
                        authInfoMessage = null,
                        pendingVerificationEmail = null,
                        resetCodeSentEmail = null,
                        remindersMuted = muted,
                        snackbarMessage = "邮箱验证成功，欢迎使用",
                    )
                }
                clearTabCache()
                loadTabData(0, force = true)
                viewModelScope.launch { refreshAndSyncAlarms() }
            } catch (exc: ApiException) {
                _uiState.update {
                    it.copy(isAuthSubmitting = false, authError = exc.message)
                }
            }
        }
    }

    fun resendVerificationCode(serverUrl: String, email: String) {
        val cleanEmail = email.trim()
        if (cleanEmail.isEmpty()) {
            _uiState.update { it.copy(authError = "请输入注册邮箱", authInfoMessage = null) }
            return
        }

        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isAuthSubmitting = true,
                    authError = null,
                    authInfoMessage = null,
                )
            }
            try {
                val normalizedUrl = api.setBaseUrl(serverUrl)
                prefs.setServerUrl(normalizedUrl)
                val resp = api.resendVerification(email = cleanEmail)
                val info = if (!resp.devVerificationCode.isNullOrBlank()) {
                    "新验证码已发送至 $cleanEmail（有效期 ${resp.expiresInMinutes} 分钟，开发模式验证码：${resp.devVerificationCode}）"
                } else {
                    "新验证码已发送至 $cleanEmail，有效期 ${resp.expiresInMinutes} 分钟，请查收邮件"
                }
                _uiState.update {
                    it.copy(
                        isAuthSubmitting = false,
                        serverUrl = normalizedUrl,
                        pendingVerificationEmail = cleanEmail,
                        authInfoMessage = info,
                    )
                }
            } catch (exc: ApiException) {
                _uiState.update {
                    it.copy(isAuthSubmitting = false, authError = exc.message)
                }
            }
        }
    }

    fun clearAuthFeedback() {
        _uiState.update {
            it.copy(
                authError = null,
                authInfoMessage = null,
                pendingVerificationEmail = null,
                resetCodeSentEmail = null,
            )
        }
    }

    fun requestPasswordReset(serverUrl: String, email: String) {
        val cleanEmail = email.trim()
        if (cleanEmail.isEmpty()) {
            _uiState.update { it.copy(authError = "请输入注册邮箱", authInfoMessage = null) }
            return
        }

        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isAuthSubmitting = true,
                    authError = null,
                    authInfoMessage = null,
                )
            }
            try {
                val normalizedUrl = api.setBaseUrl(serverUrl)
                prefs.setServerUrl(normalizedUrl)
                val resp = api.forgotPassword(email = cleanEmail)
                val info = if (!resp.devResetCode.isNullOrBlank()) {
                    "验证码已发送（有效期 ${resp.expiresInMinutes} 分钟，开发模式验证码：${resp.devResetCode}）"
                } else {
                    "验证码已发送（若该邮箱已注册），有效期 ${resp.expiresInMinutes} 分钟"
                }
                _uiState.update {
                    it.copy(
                        isAuthSubmitting = false,
                        serverUrl = normalizedUrl,
                        resetCodeSentEmail = cleanEmail,
                        authInfoMessage = info,
                    )
                }
            } catch (exc: ApiException) {
                _uiState.update {
                    it.copy(isAuthSubmitting = false, authError = exc.message)
                }
            }
        }
    }

    fun confirmPasswordReset(
        serverUrl: String,
        email: String,
        code: String,
        newPassword: String,
        confirmPassword: String,
    ) {
        val cleanEmail = email.trim()
        val cleanCode = code.trim()
        if (cleanEmail.isEmpty()) {
            _uiState.update { it.copy(authError = "请输入注册邮箱") }
            return
        }
        if (cleanCode.length != 6 || !cleanCode.all { it.isDigit() }) {
            _uiState.update { it.copy(authError = "请输入 6 位数字验证码") }
            return
        }
        if (newPassword.length < 6) {
            _uiState.update { it.copy(authError = "新密码至少需要 6 位") }
            return
        }
        if (newPassword != confirmPassword) {
            _uiState.update { it.copy(authError = "两次输入的新密码不一致") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(isAuthSubmitting = true, authError = null) }
            try {
                val normalizedUrl = api.setBaseUrl(serverUrl)
                prefs.setServerUrl(normalizedUrl)
                val tokenResp = api.resetPassword(
                    email = cleanEmail,
                    code = cleanCode,
                    newPassword = newPassword,
                )
                prefs.setToken(tokenResp.accessToken)
                val muted = prefs.getRemindersMuted()
                _uiState.update {
                    it.copy(
                        isAuthSubmitting = false,
                        isAuthenticated = true,
                        serverUrl = normalizedUrl,
                        currentUser = tokenResp.user,
                        selectedTab = 0,
                        selectedDate = LocalDate.now(),
                        authInfoMessage = null,
                        pendingVerificationEmail = null,
                        resetCodeSentEmail = null,
                        remindersMuted = muted,
                        snackbarMessage = "密码已重置，已自动登录",
                    )
                }
                clearTabCache()
                loadTabData(0, force = true)
                viewModelScope.launch { refreshAndSyncAlarms() }
            } catch (exc: ApiException) {
                _uiState.update {
                    it.copy(isAuthSubmitting = false, authError = exc.message)
                }
            }
        }
    }

    fun openChangePasswordDialog() {
        _uiState.update {
            it.copy(
                showChangePasswordDialog = true,
                isChangingPassword = false,
                changePasswordError = null,
            )
        }
    }

    fun dismissChangePasswordDialog() {
        if (_uiState.value.isChangingPassword) return
        _uiState.update {
            it.copy(
                showChangePasswordDialog = false,
                changePasswordError = null,
            )
        }
    }

    fun changePassword(
        currentPassword: String,
        newPassword: String,
        confirmPassword: String,
    ) {
        if (currentPassword.isEmpty()) {
            _uiState.update { it.copy(changePasswordError = "请输入当前密码") }
            return
        }
        if (newPassword.length < 6) {
            _uiState.update { it.copy(changePasswordError = "新密码至少需要 6 位") }
            return
        }
        if (newPassword != confirmPassword) {
            _uiState.update { it.copy(changePasswordError = "两次输入的新密码不一致") }
            return
        }
        if (newPassword == currentPassword) {
            _uiState.update { it.copy(changePasswordError = "新密码不能与当前密码相同") }
            return
        }

        viewModelScope.launch {
            _uiState.update {
                it.copy(isChangingPassword = true, changePasswordError = null)
            }
            try {
                val tokenResp = api.changePassword(
                    currentPassword = currentPassword,
                    newPassword = newPassword,
                )
                prefs.setToken(tokenResp.accessToken)
                _uiState.update {
                    it.copy(
                        isChangingPassword = false,
                        showChangePasswordDialog = false,
                        changePasswordError = null,
                        currentUser = tokenResp.user,
                        snackbarMessage = "密码修改成功",
                    )
                }
            } catch (exc: ApiException) {
                if (exc.statusCode == 401) {
                    _uiState.update {
                        it.copy(
                            isChangingPassword = false,
                            showChangePasswordDialog = false,
                            changePasswordError = null,
                        )
                    }
                    handleAuthenticatedError(exc)
                } else {
                    _uiState.update {
                        it.copy(
                            isChangingPassword = false,
                            changePasswordError = exc.message,
                        )
                    }
                }
            }
        }
    }

    fun logout() {
        viewModelScope.launch {
            alarmController.cancelAll()
            api.authToken = null
            prefs.clearToken()
            prefs.clearReminderCache()
            clearTabCache()
            _uiState.update {
                it.copy(
                    isAuthenticated = false,
                    currentUser = null,
                    selectedTab = 0,
                    selectedDate = LocalDate.now(),
                    todayHabits = emptyList(),
                    schedulePeriod = "week",
                    scheduleAnchorDate = LocalDate.now(),
                    periodSchedule = null,
                    allHabits = emptyList(),
                    statsSummary = null,
                    sliDashboard = null,
                    authError = null,
                    authInfoMessage = null,
                    pendingVerificationEmail = null,
                    resetCodeSentEmail = null,
                    showChangePasswordDialog = false,
                    isChangingPassword = false,
                    changePasswordError = null,
                    showRemindersDialog = false,
                    remindersOverview = null,
                    isLoadingReminders = false,
                )
            }
        }
    }

    fun selectTab(index: Int) {
        _uiState.update { it.copy(selectedTab = index) }
        launchTabLoad(index)
    }

    fun shiftDate(deltaDays: Long) {
        val current = _uiState.value.selectedDate
        val candidate = current.plusDays(deltaDays)
        val today = LocalDate.now()
        if (candidate.isAfter(today)) return

        _uiState.update { it.copy(selectedDate = candidate) }
        launchTabLoad(0)
    }

    fun jumpToToday() {
        val today = LocalDate.now()
        if (_uiState.value.selectedDate == today) return
        _uiState.update { it.copy(selectedDate = today) }
        launchTabLoad(0)
    }

    fun refreshCurrentTab() {
        launchTabLoad(_uiState.value.selectedTab, force = true)
    }

    private fun launchTabLoad(tabIndex: Int, force: Boolean = false) {
        tabLoadJob?.cancel()
        val key = tabIndex to currentParamKey(tabIndex)
        val cached = tabCacheEntries[key]
        if (cached != null) {
            applyTabData(tabIndex, cached.data)
            if (!force && isCacheFresh(key)) {
                _uiState.update { it.copy(isRefreshing = false) }
                return
            }
        }
        val expectedGen = tabMutationGen[tabIndex]
        val showSpinner = cached == null || force
        tabLoadJob = viewModelScope.launch {
            loadTabData(
                tabIndex = tabIndex,
                key = key,
                expectedGen = expectedGen,
                showLoadingSpinner = showSpinner,
                force = force,
            )
        }
    }

    fun startHabitExecution(habit: HabitToday) {
        performCheckin(
            habit.id,
            CheckinRequest(
                date = isoDate(_uiState.value.selectedDate),
                action = "start",
                clientToday = isoDate(LocalDate.now()),
                clientTime = currentNowHhmm(),
            ),
        )
    }

    fun primaryCheckin(habit: HabitToday) {
        val action = if (habit.targetPerDay == 1) "toggle" else "increment"
        performCheckin(
            habit.id,
            CheckinRequest(
                date = isoDate(_uiState.value.selectedDate),
                action = action,
                clientToday = isoDate(LocalDate.now()),
                clientTime = currentNowHhmm(),
            ),
        )
    }

    fun decrementCheckin(habit: HabitToday) {
        performCheckin(
            habit.id,
            CheckinRequest(
                date = isoDate(_uiState.value.selectedDate),
                action = "decrement",
                clientToday = isoDate(LocalDate.now()),
                clientTime = currentNowHhmm(),
            ),
        )
    }

    fun updateCheckinNote(habit: HabitToday, note: String) {
        performCheckin(
            habit.id,
            CheckinRequest(
                date = isoDate(_uiState.value.selectedDate),
                action = "set",
                count = habit.count,
                note = note.trim(),
                clientToday = isoDate(LocalDate.now()),
                clientTime = currentNowHhmm(),
            ),
        )
    }

    fun setSchedulePeriod(period: String) {
        if (period != "week" && period != "month") return
        if (_uiState.value.schedulePeriod == period) return
        _uiState.update { it.copy(schedulePeriod = period) }
        launchTabLoad(1)
    }

    fun shiftSchedulePeriod(delta: Long) {
        val current = _uiState.value.scheduleAnchorDate
        val next = if (_uiState.value.schedulePeriod == "month") {
            current.plusMonths(delta)
        } else {
            current.plusWeeks(delta)
        }
        _uiState.update { it.copy(scheduleAnchorDate = next) }
        launchTabLoad(1)
    }

    fun resetScheduleToCurrent() {
        val today = LocalDate.now()
        _uiState.update { it.copy(scheduleAnchorDate = today) }
        launchTabLoad(1)
    }

    fun schedulePrimaryCheckin(item: ScheduleHabitItem) {
        val targetDate = LocalDate.parse(item.date)
        val today = LocalDate.now()
        if (targetDate.isAfter(today)) return
        val todayIso = isoDate(today)
        val nowHhmm = currentNowHhmm()
        val needsStrictStart = item.mode == "strict" &&
            item.date == todayIso &&
            !item.completed &&
            !item.startedOnTime &&
            (item.forceStartTime == null || nowHhmm <= item.forceStartTime)
        val action = when {
            needsStrictStart -> "start"
            item.targetPerDay <= 1 -> "toggle"
            else -> "increment"
        }
        performCheckin(
            item.habitId,
            CheckinRequest(
                date = item.date,
                action = action,
                clientToday = todayIso,
                clientTime = nowHhmm,
            ),
        )
    }

    fun scheduleDecrementCheckin(item: ScheduleHabitItem) {
        val targetDate = LocalDate.parse(item.date)
        val today = LocalDate.now()
        if (targetDate.isAfter(today) || item.count <= 0) return
        performCheckin(
            item.habitId,
            CheckinRequest(
                date = item.date,
                action = "decrement",
                clientToday = isoDate(today),
                clientTime = currentNowHhmm(),
            ),
        )
    }

    private fun performCheckin(habitId: String, request: CheckinRequest) {
        viewModelScope.launch {
            try {
                val updated = api.checkinHabit(habitId, request)
                val state = _uiState.value
                val todayIso = isoDate(LocalDate.now())
                if (request.date == todayIso) {
                    prefs.markHabitCompletedForDate(todayIso, updated.id, updated.completed)
                }
                if (state.selectedTab == 0 && isoDate(state.selectedDate) == request.date) {
                    tabLoadJob?.cancel()
                    val updatedList = state.todayHabits.map {
                        if (it.id == updated.id) updated else it
                    }
                    invalidateTabs(1, 3, 4)
                    tabMutationGen[0]++
                    storeCacheEntry(0 to isoDate(state.selectedDate), updatedList, tabMutationGen[0])
                    _uiState.update { it.copy(isRefreshing = false, todayHabits = updatedList) }
                    if (request.date == todayIso) {
                        val cached = prefs.getCachedReminderHabits()
                            .ifEmpty { updatedList.map { it.toHabit() } }
                        val completedIds = prefs.getCompletedHabitIdsForDate(todayIso)
                        alarmController.syncAllHabits(cached, completedIds, _uiState.value.remindersMuted)
                    }
                } else {
                    invalidateTabs(0, 1, 3, 4)
                    tabLoadJob?.cancel()
                    loadTabData(state.selectedTab, force = true)
                    if (request.date == todayIso) {
                        refreshAndSyncAlarms()
                    }
                }
            } catch (exc: ApiException) {
                handleAuthenticatedError(exc)
            }
        }
    }

    fun saveHabit(existingId: String?, request: HabitCreateRequest) {
        viewModelScope.launch {
            _uiState.update { it.copy(isRefreshing = true) }
            try {
                if (existingId != null) {
                    api.updateHabit(
                        existingId,
                        HabitUpdateRequest(
                            title = request.title,
                            description = request.description,
                            color = request.color,
                            icon = request.icon,
                            frequencyType = request.frequencyType,
                            weekdays = request.weekdays,
                            monthlyMode = request.monthlyMode,
                            monthlyDay = request.monthlyDay,
                            monthlyWeek = request.monthlyWeek,
                            monthlyWeekday = request.monthlyWeekday,
                            targetPerDay = request.targetPerDay,
                            targetSlo = request.targetSlo,
                            mode = request.mode,
                            remindTime = request.remindTime,
                            forceStartTime = request.forceStartTime,
                            forceEndTime = request.forceEndTime,
                            reminderEnabled = request.reminderEnabled,
                            reminderTimes = request.reminderTimes,
                            reminderMode = request.reminderMode,
                            reminderSnoozeMinutes = request.reminderSnoozeMinutes,
                            reminderMessage = request.reminderMessage,
                        ),
                    )
                    _uiState.update { it.copy(snackbarMessage = "习惯已更新") }
                } else {
                    api.createHabit(request)
                    _uiState.update { it.copy(snackbarMessage = "已创建新习惯") }
                }
                invalidateTabs(0, 1, 2, 3, 4)
                tabLoadJob?.cancel()
                loadTabData(_uiState.value.selectedTab, force = true)
                refreshAndSyncAlarms()
                if (_uiState.value.showRemindersDialog) {
                    refreshRemindersOverview()
                }
            } catch (exc: ApiException) {
                _uiState.update { it.copy(isRefreshing = false) }
                handleAuthenticatedError(exc)
            }
        }
    }

    fun toggleArchive(habit: Habit) {
        viewModelScope.launch {
            try {
                api.updateHabit(habit.id, HabitUpdateRequest(archived = !habit.archived))
                val msg = if (habit.archived) "已取消归档" else "已归档习惯"
                invalidateTabs(0, 1, 2, 3, 4)
                tabLoadJob?.cancel()
                _uiState.update { it.copy(snackbarMessage = msg) }
                loadTabData(_uiState.value.selectedTab, force = true)
                refreshAndSyncAlarms()
            } catch (exc: ApiException) {
                handleAuthenticatedError(exc)
            }
        }
    }

    fun deleteHabit(habit: Habit) {
        viewModelScope.launch {
            try {
                api.deleteHabit(habit.id)
                alarmController.cancelHabit(habit.id)
                invalidateTabs(0, 1, 2, 3, 4)
                tabLoadJob?.cancel()
                _uiState.update { it.copy(snackbarMessage = "已删除习惯「${habit.title}」") }
                loadTabData(_uiState.value.selectedTab, force = true)
                refreshAndSyncAlarms()
            } catch (exc: ApiException) {
                handleAuthenticatedError(exc)
            }
        }
    }

    fun openRemindersDialog() {
        _uiState.update { it.copy(showRemindersDialog = true) }
        refreshRemindersOverview()
    }

    fun dismissRemindersDialog() {
        _uiState.update { it.copy(showRemindersDialog = false) }
    }

    fun refreshRemindersOverview() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoadingReminders = true) }
            try {
                val overview = api.getRemindersOverview(
                    targetDate = isoDate(LocalDate.now()),
                    nowTime = currentNowHhmm(),
                )
                _uiState.update {
                    it.copy(
                        isLoadingReminders = false,
                        remindersOverview = overview,
                    )
                }
            } catch (exc: ApiException) {
                _uiState.update { it.copy(isLoadingReminders = false) }
                handleAuthenticatedError(exc)
            }
        }
    }

    fun toggleRemindersMuted() {
        viewModelScope.launch {
            val newMuted = !_uiState.value.remindersMuted
            prefs.setRemindersMuted(newMuted)
            _uiState.update {
                it.copy(
                    remindersMuted = newMuted,
                    snackbarMessage = if (newMuted) "已暂停所有提醒与闹钟" else "已开启提醒与闹钟",
                )
            }
            val todayIso = isoDate(LocalDate.now())
            val cached = prefs.getCachedReminderHabits()
            val completedIds = prefs.getCompletedHabitIdsForDate(todayIso)
            alarmController.syncAllHabits(cached, completedIds, newMuted)
        }
    }

    fun showSnackbar(message: String) {
        _uiState.update { it.copy(snackbarMessage = message) }
    }

    fun toggleShowArchived(show: Boolean) {
        _uiState.update { it.copy(showArchived = show) }
        launchTabLoad(2)
    }

    fun consumeSnackbar() {
        _uiState.update { it.copy(snackbarMessage = null) }
    }

    fun selectSliWindow(windowDays: Int) {
        if (_uiState.value.sliWindowDays == windowDays) return
        _uiState.update { it.copy(sliWindowDays = windowDays) }
        launchTabLoad(4)
    }

    fun updateHabitTargetSlo(habitId: String, targetSlo: Double) {
        val rounded = kotlin.math.round(targetSlo * 10.0) / 10.0
        viewModelScope.launch {
            _uiState.update { it.copy(isRefreshing = true) }
            try {
                api.updateHabit(habitId, HabitUpdateRequest(targetSlo = rounded))
                invalidateTabs(2, 4)
                tabLoadJob?.cancel()
                _uiState.update { it.copy(snackbarMessage = "已更新目标 SLO") }
                loadTabData(_uiState.value.selectedTab, force = true)
            } catch (exc: ApiException) {
                _uiState.update { it.copy(isRefreshing = false) }
                handleAuthenticatedError(exc)
            }
        }
    }

    private suspend fun loadTabData(
        tabIndex: Int,
        key: Pair<Int, String> = tabIndex to currentParamKey(tabIndex),
        expectedGen: Int = tabMutationGen[tabIndex],
        showLoadingSpinner: Boolean = true,
        force: Boolean = false,
    ) {
        val state = _uiState.value
        if (showLoadingSpinner) {
            _uiState.update { it.copy(isRefreshing = true) }
        }
        val prevEntry = tabCacheEntries[key]
        try {
            val data: Any = when (tabIndex) {
                0 -> api.getTodayHabits(
                    targetDate = isoDate(state.selectedDate),
                    clientToday = isoDate(LocalDate.now()),
                    clientTime = currentNowHhmm(),
                )
                1 -> api.getPeriodSchedule(
                    period = state.schedulePeriod,
                    anchorDate = isoDate(state.scheduleAnchorDate),
                    today = isoDate(LocalDate.now()),
                )
                2 -> api.listHabits(includeArchived = state.showArchived)
                3 -> api.getStatsSummary(
                    today = isoDate(LocalDate.now()),
                    clientTime = currentNowHhmm(),
                )
                else -> api.getSliDashboard(
                    today = isoDate(LocalDate.now()),
                    windowDays = state.sliWindowDays,
                    clientTime = currentNowHhmm(),
                )
            }
            if (!storeCacheEntry(key, data, expectedGen)) return
            if (!force && prevEntry != null && prevEntry.data == data) {
                _uiState.update { it.copy(isRefreshing = false) }
                return
            }
            if (currentParamKey(tabIndex) == key.second) {
                applyTabData(tabIndex, data)
            }
            @Suppress("UNCHECKED_CAST")
            when (tabIndex) {
                0 -> {
                    val todayIso = isoDate(LocalDate.now())
                    if (key.second == todayIso) {
                        val list = data as List<HabitToday>
                        val completedIds = list.filter { it.completed }.map { it.id }.toSet()
                        prefs.setCompletedHabitIdsForDate(todayIso, completedIds)
                        val cached = prefs.getCachedReminderHabits()
                            .ifEmpty { list.map { it.toHabit() } }
                        alarmController.syncAllHabits(cached, completedIds, _uiState.value.remindersMuted)
                    }
                }
                2 -> {
                    val list = (data as List<Habit>).filter { !it.archived }
                    prefs.setCachedReminderHabits(list)
                    val todayIso = isoDate(LocalDate.now())
                    val completedIds = prefs.getCompletedHabitIdsForDate(todayIso)
                    alarmController.syncAllHabits(list, completedIds, _uiState.value.remindersMuted)
                }
            }
            _uiState.update { it.copy(isRefreshing = false) }
        } catch (ce: CancellationException) {
            throw ce
        } catch (exc: ApiException) {
            if (expectedGen == tabMutationGen[tabIndex]) {
                _uiState.update { it.copy(isRefreshing = false) }
                handleAuthenticatedError(exc)
            }
        }
    }

    private suspend fun refreshAndSyncAlarms() {
        val todayIso = isoDate(LocalDate.now())
        val activeHabits = runCatching { api.listHabits(includeArchived = false) }.getOrNull() ?: return
        prefs.setCachedReminderHabits(activeHabits)
        val completedIds = runCatching {
            val todayItems = api.getTodayHabits(todayIso)
            val ids = todayItems.filter { it.completed }.map { it.id }.toSet()
            prefs.setCompletedHabitIdsForDate(todayIso, ids)
            ids
        }.getOrElse {
            prefs.getCompletedHabitIdsForDate(todayIso)
        }
        val muted = prefs.getRemindersMuted()
        alarmController.syncAllHabits(activeHabits, completedIds, muted)
    }

    private suspend fun handleAuthenticatedError(exc: ApiException) {
        if (exc.statusCode == 401) {
            alarmController.cancelAll()
            api.authToken = null
            prefs.clearToken()
            prefs.clearReminderCache()
            clearTabCache()
            _uiState.update {
                it.copy(
                    isAuthenticated = false,
                    currentUser = null,
                    showChangePasswordDialog = false,
                    isChangingPassword = false,
                    changePasswordError = null,
                    showRemindersDialog = false,
                    remindersOverview = null,
                    isLoadingReminders = false,
                    authError = "登录状态已过期，请重新登录",
                    authInfoMessage = null,
                    resetCodeSentEmail = null,
                )
            }
        } else {
            _uiState.update { it.copy(snackbarMessage = exc.message) }
        }
    }

    private fun currentNowHhmm(): String {
        val now = LocalTime.now()
        return "${now.hour.toString().padStart(2, '0')}:${now.minute.toString().padStart(2, '0')}"
    }

    private fun isoDate(date: LocalDate): String = date.format(DateTimeFormatter.ISO_LOCAL_DATE)
}

class HabitViewModelFactory(
    private val appContext: Context,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(HabitViewModel::class.java)) {
            val appCtx = appContext.applicationContext
            HabitNotificationHelper.ensureChannels(appCtx)
            return HabitViewModel(
                prefs = SessionPreferences(appCtx),
                alarmController = AndroidHabitAlarmScheduler(appCtx),
            ) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class: ${modelClass.name}")
    }
}
