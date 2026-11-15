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
import com.shawnpeng.habittracker.data.ScheduleHabitItem
import com.shawnpeng.habittracker.data.SessionPreferences
import com.shawnpeng.habittracker.data.SliDashboard
import com.shawnpeng.habittracker.data.StatsSummary
import com.shawnpeng.habittracker.data.UserPublic
import java.time.LocalDate
import java.time.format.DateTimeFormatter
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
    val snackbarMessage: String? = null,
)

class HabitViewModel(
    private val prefs: SessionPreferences,
    private val api: HabitApiClient = HabitApiClient(),
) : ViewModel() {

    private val _uiState = MutableStateFlow(HabitUiState())
    val uiState: StateFlow<HabitUiState> = _uiState.asStateFlow()

    init {
        initializeSession()
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
                _uiState.update {
                    it.copy(
                        isInitializing = false,
                        isAuthenticated = true,
                        currentUser = me,
                    )
                }
                loadTabData(_uiState.value.selectedTab)
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
                    )
                }
                loadTabData(0)
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
                        snackbarMessage = "邮箱验证成功，欢迎使用",
                    )
                }
                loadTabData(0)
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
                        snackbarMessage = "密码已重置，已自动登录",
                    )
                }
                loadTabData(0)
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
            api.authToken = null
            prefs.clearToken()
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
                )
            }
        }
    }

    fun selectTab(index: Int) {
        _uiState.update { it.copy(selectedTab = index) }
        viewModelScope.launch {
            loadTabData(index)
        }
    }

    fun shiftDate(deltaDays: Long) {
        val current = _uiState.value.selectedDate
        val candidate = current.plusDays(deltaDays)
        val today = LocalDate.now()
        if (candidate.isAfter(today)) return

        _uiState.update { it.copy(selectedDate = candidate) }
        viewModelScope.launch {
            loadTabData(0)
        }
    }

    fun jumpToToday() {
        val today = LocalDate.now()
        if (_uiState.value.selectedDate == today) return
        _uiState.update { it.copy(selectedDate = today) }
        viewModelScope.launch {
            loadTabData(0)
        }
    }

    fun refreshCurrentTab() {
        viewModelScope.launch {
            loadTabData(_uiState.value.selectedTab)
        }
    }

    fun primaryCheckin(habit: HabitToday) {
        val action = if (habit.targetPerDay == 1) "toggle" else "increment"
        performCheckin(habit.id, CheckinRequest(date = isoDate(_uiState.value.selectedDate), action = action))
    }

    fun decrementCheckin(habit: HabitToday) {
        performCheckin(habit.id, CheckinRequest(date = isoDate(_uiState.value.selectedDate), action = "decrement"))
    }

    fun updateCheckinNote(habit: HabitToday, note: String) {
        performCheckin(
            habit.id,
            CheckinRequest(
                date = isoDate(_uiState.value.selectedDate),
                action = "set",
                count = habit.count,
                note = note.trim(),
            ),
        )
    }

    fun setSchedulePeriod(period: String) {
        if (period != "week" && period != "month") return
        if (_uiState.value.schedulePeriod == period) return
        _uiState.update { it.copy(schedulePeriod = period) }
        viewModelScope.launch {
            loadTabData(1)
        }
    }

    fun shiftSchedulePeriod(delta: Long) {
        val current = _uiState.value.scheduleAnchorDate
        val next = if (_uiState.value.schedulePeriod == "month") {
            current.plusMonths(delta)
        } else {
            current.plusWeeks(delta)
        }
        _uiState.update { it.copy(scheduleAnchorDate = next) }
        viewModelScope.launch {
            loadTabData(1)
        }
    }

    fun resetScheduleToCurrent() {
        val today = LocalDate.now()
        _uiState.update { it.copy(scheduleAnchorDate = today) }
        viewModelScope.launch {
            loadTabData(1)
        }
    }

    fun schedulePrimaryCheckin(item: ScheduleHabitItem) {
        val targetDate = LocalDate.parse(item.date)
        if (targetDate.isAfter(LocalDate.now())) return
        val action = if (item.targetPerDay <= 1) "toggle" else "increment"
        performCheckin(item.habitId, CheckinRequest(date = item.date, action = action))
    }

    fun scheduleDecrementCheckin(item: ScheduleHabitItem) {
        val targetDate = LocalDate.parse(item.date)
        if (targetDate.isAfter(LocalDate.now()) || item.count <= 0) return
        performCheckin(item.habitId, CheckinRequest(date = item.date, action = "decrement"))
    }

    private fun performCheckin(habitId: String, request: CheckinRequest) {
        viewModelScope.launch {
            try {
                api.checkinHabit(habitId, request)
                loadTabData(_uiState.value.selectedTab)
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
                        ),
                    )
                    _uiState.update { it.copy(snackbarMessage = "习惯已更新") }
                } else {
                    api.createHabit(request)
                    _uiState.update { it.copy(snackbarMessage = "已创建新习惯") }
                }
                loadTabData(_uiState.value.selectedTab)
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
                _uiState.update { it.copy(snackbarMessage = msg) }
                loadTabData(_uiState.value.selectedTab)
            } catch (exc: ApiException) {
                handleAuthenticatedError(exc)
            }
        }
    }

    fun deleteHabit(habit: Habit) {
        viewModelScope.launch {
            try {
                api.deleteHabit(habit.id)
                _uiState.update { it.copy(snackbarMessage = "已删除习惯「${habit.title}」") }
                loadTabData(_uiState.value.selectedTab)
            } catch (exc: ApiException) {
                handleAuthenticatedError(exc)
            }
        }
    }

    fun toggleShowArchived(show: Boolean) {
        _uiState.update { it.copy(showArchived = show) }
        viewModelScope.launch {
            loadTabData(2)
        }
    }

    fun consumeSnackbar() {
        _uiState.update { it.copy(snackbarMessage = null) }
    }

    fun selectSliWindow(windowDays: Int) {
        if (_uiState.value.sliWindowDays == windowDays) return
        _uiState.update { it.copy(sliWindowDays = windowDays) }
        viewModelScope.launch {
            loadTabData(4)
        }
    }

    fun updateHabitTargetSlo(habitId: String, targetSlo: Double) {
        val rounded = kotlin.math.round(targetSlo * 10.0) / 10.0
        viewModelScope.launch {
            _uiState.update { it.copy(isRefreshing = true) }
            try {
                api.updateHabit(habitId, HabitUpdateRequest(targetSlo = rounded))
                _uiState.update { it.copy(snackbarMessage = "已更新目标 SLO") }
                loadTabData(_uiState.value.selectedTab)
            } catch (exc: ApiException) {
                _uiState.update { it.copy(isRefreshing = false) }
                handleAuthenticatedError(exc)
            }
        }
    }

    private suspend fun loadTabData(tabIndex: Int) {
        _uiState.update { it.copy(isRefreshing = true) }
        try {
            when (tabIndex) {
                0 -> {
                    val items = api.getTodayHabits(isoDate(_uiState.value.selectedDate))
                    _uiState.update { it.copy(isRefreshing = false, todayHabits = items) }
                }
                1 -> {
                    val state = _uiState.value
                    val schedule = api.getPeriodSchedule(
                        period = state.schedulePeriod,
                        anchorDate = isoDate(state.scheduleAnchorDate),
                        today = isoDate(LocalDate.now()),
                    )
                    _uiState.update { it.copy(isRefreshing = false, periodSchedule = schedule) }
                }
                2 -> {
                    val items = api.listHabits(includeArchived = _uiState.value.showArchived)
                    _uiState.update { it.copy(isRefreshing = false, allHabits = items) }
                }
                3 -> {
                    val summary = api.getStatsSummary(isoDate(LocalDate.now()))
                    _uiState.update { it.copy(isRefreshing = false, statsSummary = summary) }
                }
                else -> {
                    val dashboard = api.getSliDashboard(
                        today = isoDate(LocalDate.now()),
                        windowDays = _uiState.value.sliWindowDays,
                    )
                    _uiState.update { it.copy(isRefreshing = false, sliDashboard = dashboard) }
                }
            }
        } catch (exc: ApiException) {
            _uiState.update { it.copy(isRefreshing = false) }
            handleAuthenticatedError(exc)
        }
    }

    private suspend fun handleAuthenticatedError(exc: ApiException) {
        if (exc.statusCode == 401) {
            api.authToken = null
            prefs.clearToken()
            _uiState.update {
                it.copy(
                    isAuthenticated = false,
                    currentUser = null,
                    showChangePasswordDialog = false,
                    isChangingPassword = false,
                    changePasswordError = null,
                    authError = "登录状态已过期，请重新登录",
                    authInfoMessage = null,
                    resetCodeSentEmail = null,
                )
            }
        } else {
            _uiState.update { it.copy(snackbarMessage = exc.message) }
        }
    }

    private fun isoDate(date: LocalDate): String = date.format(DateTimeFormatter.ISO_LOCAL_DATE)
}

class HabitViewModelFactory(
    private val appContext: Context,
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(HabitViewModel::class.java)) {
            return HabitViewModel(SessionPreferences(appContext.applicationContext)) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class: ${modelClass.name}")
    }
}
