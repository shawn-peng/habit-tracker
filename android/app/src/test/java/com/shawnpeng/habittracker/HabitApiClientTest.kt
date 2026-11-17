package com.shawnpeng.habittracker

import androidx.compose.ui.graphics.Color
import com.shawnpeng.habittracker.data.ApiException
import com.shawnpeng.habittracker.data.CheckinRequest
import com.shawnpeng.habittracker.data.HABIT_MODE_OPTIONS
import com.shawnpeng.habittracker.data.Habit
import com.shawnpeng.habittracker.data.HabitApiClient
import com.shawnpeng.habittracker.data.HabitCreateRequest
import com.shawnpeng.habittracker.data.HabitUpdateRequest
import com.shawnpeng.habittracker.data.computeNextTriggerDateTime
import com.shawnpeng.habittracker.data.effectiveReminderTimes
import com.shawnpeng.habittracker.data.extractHabitCreatedDate
import com.shawnpeng.habittracker.data.formatCompanionReminderBadge
import com.shawnpeng.habittracker.data.formatFrequencySummary
import com.shawnpeng.habittracker.data.formatHabitModeSummary
import com.shawnpeng.habittracker.data.formatReminderBadge
import com.shawnpeng.habittracker.data.formatTime12h
import com.shawnpeng.habittracker.data.localDateToUtcPickerMillis
import com.shawnpeng.habittracker.data.normalizeReminderTime
import com.shawnpeng.habittracker.data.normalizeReminderTimes
import com.shawnpeng.habittracker.data.parseHabitColor
import com.shawnpeng.habittracker.data.resolveTimeWithMeridiem
import com.shawnpeng.habittracker.data.split24hTo12h
import com.shawnpeng.habittracker.data.utcPickerMillisToLocalDate
import com.shawnpeng.habittracker.data.validateHabitModeTimes
import java.time.LocalDate
import java.time.LocalDateTime
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class HabitApiClientTest {

    private lateinit var server: MockWebServer
    private lateinit var client: HabitApiClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        client = HabitApiClient(initialBaseUrl = server.url("/").toString())
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun normalizeBaseUrlAddsSchemeAndStripsTrailingSlash() {
        assertEquals(
            "http://192.168.1.20:8000",
            HabitApiClient.normalizeBaseUrl("  192.168.1.20:8000/  "),
        )
        assertEquals(
            "https://habits.example.com",
            HabitApiClient.normalizeBaseUrl("https://habits.example.com///"),
        )
    }

    @Test
    fun loginStoresTokenAndSendsBearerHeaderOnTodayAndCheckin() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "access_token": "jwt-abc-123",
                      "token_type": "bearer",
                      "user": {
                        "id": "u1",
                        "name": "Shawn",
                        "email": "shawn@example.com",
                        "created_at": "2026-11-14T00:00:00Z"
                      }
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    [
                      {
                        "id": "h1",
                        "title": "Read 20 pages",
                        "description": "",
                        "color": "#6366F1",
                        "icon": "check_circle",
                        "frequency_type": "daily",
                        "weekdays": [0, 1, 2, 3, 4, 5, 6],
                        "target_per_day": 1,
                        "archived": false,
                        "created_at": "2026-11-14T00:00:00Z",
                        "date": "2026-11-14",
                        "scheduled_today": true,
                        "count": 0,
                        "completed": false,
                        "note": "",
                        "current_streak": 2,
                        "best_streak": 5
                      }
                    ]
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "id": "h1",
                      "title": "Read 20 pages",
                      "description": "",
                      "color": "#6366F1",
                      "icon": "check_circle",
                      "frequency_type": "daily",
                      "weekdays": [0, 1, 2, 3, 4, 5, 6],
                      "target_per_day": 1,
                      "archived": false,
                      "created_at": "2026-11-14T00:00:00Z",
                      "date": "2026-11-14",
                      "scheduled_today": true,
                      "count": 1,
                      "completed": true,
                      "note": "Done",
                      "current_streak": 3,
                      "best_streak": 5
                    }
                    """.trimIndent(),
                ),
        )

        val tokenResp = client.login("shawn@example.com", "secret123")
        assertEquals("jwt-abc-123", tokenResp.accessToken)
        assertEquals("jwt-abc-123", client.authToken)

        val todayItems = client.getTodayHabits("2026-11-14")
        assertEquals(1, todayItems.size)
        assertEquals("Read 20 pages", todayItems.first().title)

        val checked = client.checkinHabit(
            habitId = "h1",
            request = CheckinRequest(date = "2026-11-14", action = "toggle", note = "Done"),
        )
        assertTrue(checked.completed)
        assertEquals(3, checked.currentStreak)

        val loginReq = server.takeRequest()
        assertEquals("/api/auth/login", loginReq.path)

        val todayReq = server.takeRequest()
        assertEquals("/api/habits/today?target_date=2026-11-14", todayReq.path)
        assertEquals("Bearer jwt-abc-123", todayReq.getHeader("Authorization"))

        val checkinReq = server.takeRequest()
        assertEquals("/api/habits/h1/checkin", checkinReq.path)
        assertEquals("Bearer jwt-abc-123", checkinReq.getHeader("Authorization"))
        val checkinBody = checkinReq.body.readUtf8()
        assertTrue(checkinBody.contains("\"action\":\"toggle\""))
        assertTrue(checkinBody.contains("\"note\":\"Done\""))
    }

    @Test
    fun updateHabitPatchSerializesOnlyNonNullFields() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "id": "h1",
                      "title": "Meditate",
                      "description": "",
                      "color": "#6366F1",
                      "icon": "check_circle",
                      "frequency_type": "daily",
                      "weekdays": [0, 1, 2, 3, 4, 5, 6],
                      "target_per_day": 1,
                      "archived": true,
                      "created_at": "2026-11-14T00:00:00Z"
                    }
                    """.trimIndent(),
                ),
        )

        val updated = client.updateHabit("h1", HabitUpdateRequest(archived = true))
        assertTrue(updated.archived)

        val req = server.takeRequest()
        assertEquals("PATCH", req.method)
        assertEquals("/api/habits/h1", req.path)
        val rawBody = req.body.readUtf8()
        assertEquals("{\"archived\":true}", rawBody)
        assertFalse(rawBody.contains("title"))
    }

    @Test
    fun deleteHabitHandles204NoContent() = runTest {
        server.enqueue(MockResponse().setResponseCode(204))
        client.deleteHabit("h99")

        val req = server.takeRequest()
        assertEquals("DELETE", req.method)
        assertEquals("/api/habits/h99", req.path)
    }

    @Test
    fun parseErrorDetailSupportsStringAndPydanticArrayAnd401Status() = runTest {
        assertEquals(
            "Incorrect email or password",
            HabitApiClient.parseErrorDetail("{\"detail\":\"Incorrect email or password\"}", 401),
        )
        assertEquals(
            "String should have at least 6 characters",
            HabitApiClient.parseErrorDetail(
                "{\"detail\":[{\"loc\":[\"body\",\"password\"],\"msg\":\"String should have at least 6 characters\"}]}",
                422,
            ),
        )

        server.enqueue(
            MockResponse()
                .setResponseCode(401)
                .setBody("{\"detail\":\"Session expired, please sign in again\"}"),
        )

        try {
            client.getMe()
            fail("Expected ApiException on 401")
        } catch (exc: ApiException) {
            assertEquals(401, exc.statusCode)
            assertEquals("Session expired, please sign in again", exc.message)
        }
    }

    @Test
    fun parseHabitColorHandlesValidAndInvalidHex() {
        assertEquals(Color(0xFF6366F1), parseHabitColor("#6366F1"))
        assertEquals(Color(0xFF10B981), parseHabitColor("10b981"))
        assertEquals(Color(0xFF6366F1), parseHabitColor("not-a-color"))
    }

    @Test
    fun formatFrequencySummarySupportsDailyWeekdaysAndMonthlyRules() {
        assertEquals("Every day", formatFrequencySummary("daily"))
        assertEquals("Mon, Wed, Fri", formatFrequencySummary("weekdays", listOf(0, 2, 4)))
        assertEquals(
            "Monthly • 15th day",
            formatFrequencySummary("monthly", monthlyMode = "from_start", monthlyDay = 15),
        )
        assertEquals(
            "Monthly • Last day of month",
            formatFrequencySummary("monthly", monthlyMode = "from_end", monthlyDay = 1),
        )
        assertEquals(
            "Monthly • 3rd day from end",
            formatFrequencySummary("monthly", monthlyMode = "from_end", monthlyDay = 3),
        )
        assertEquals(
            "Monthly • Mon on Week 2",
            formatFrequencySummary("monthly", monthlyMode = "nth_weekday", monthlyWeek = 2, monthlyWeekday = 0),
        )
        assertEquals(
            "Monthly • Fri on Last week",
            formatFrequencySummary("monthly", monthlyMode = "nth_weekday", monthlyWeek = -1, monthlyWeekday = 4),
        )
    }

    @Test
    fun createHabitSerializesAndDeserializesMonthlyRoutine() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(201)
                .setBody(
                    """
                    {
                      "id": "h-monthly-1",
                      "title": "Pay Rent",
                      "description": "Transfer before month end",
                      "color": "#10B981",
                      "icon": "check_circle",
                      "frequency_type": "monthly",
                      "weekdays": [0, 1, 2, 3, 4, 5, 6],
                      "monthly_mode": "from_end",
                      "monthly_day": 2,
                      "monthly_week": 1,
                      "monthly_weekday": 0,
                      "target_per_day": 1,
                      "archived": false,
                      "created_date": "2026-11-14",
                      "created_time": "14:05",
                      "created_at": "2026-11-14T00:00:00Z"
                    }
                    """.trimIndent(),
                ),
        )

        val created = client.createHabit(
            HabitCreateRequest(
                title = "Pay Rent",
                description = "Transfer before month end",
                color = "#10B981",
                frequencyType = "monthly",
                monthlyMode = "from_end",
                monthlyDay = 2,
                createdDate = "2026-11-14",
                createdTime = "14:05",
            ),
        )
        assertEquals("monthly", created.frequencyType)
        assertEquals("from_end", created.monthlyMode)
        assertEquals(2, created.monthlyDay)
        assertEquals("2026-11-14", created.createdDate)
        assertEquals("14:05", created.createdTime)

        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/api/habits", req.path)
        val rawBody = req.body.readUtf8()
        assertTrue(rawBody.contains("\"frequency_type\":\"monthly\""))
        assertTrue(rawBody.contains("\"monthly_mode\":\"from_end\""))
        assertTrue(rawBody.contains("\"monthly_day\":2"))
        assertTrue(rawBody.contains("\"monthly_week\":1"))
        assertTrue(rawBody.contains("\"monthly_weekday\":0"))
        assertTrue(rawBody.contains("\"created_date\":\"2026-11-14\""))
        assertTrue(rawBody.contains("\"created_time\":\"14:05\""))
    }

    @Test
    fun getSliDashboardParsesMetricsTrendAndErrorBudget() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "window_days": 30,
                      "active_habits_count": 1,
                      "overall_sli": 90.0,
                      "overall_target_slo": 85.0,
                      "overall_status": "healthy",
                      "healthy_count": 1,
                      "warning_count": 0,
                      "breached_count": 0,
                      "overall_error_budget_allowed_days": 4.5,
                      "overall_error_budget_used_days": 3,
                      "overall_error_budget_remaining_days": 1.5,
                      "overall_error_budget_remaining_pct": 33.3,
                      "overall_burn_rate": 0.67,
                      "overall_burn_rate_7d": 0.95,
                      "weakest_weekday": "Fri",
                      "weakest_weekday_sli": 75.0,
                      "top_burn_habit_title": "Read 20 pages",
                      "top_burn_rate": 0.67,
                      "trend": [
                        {
                          "label": "11/14",
                          "start_date": "2026-11-12",
                          "end_date": "2026-11-14",
                          "scheduled_count": 3,
                          "completed_count": 3,
                          "sli": 100.0,
                          "has_activity": true
                        }
                      ],
                      "weekday_sli": [
                        {
                          "weekday": 4,
                          "label": "Fri",
                          "scheduled_count": 4,
                          "completed_count": 3,
                          "sli": 75.0
                        }
                      ],
                      "habits": [
                        {
                          "habit_id": "h1",
                          "title": "Read 20 pages",
                          "color": "#6366F1",
                          "target_slo": 85.0,
                          "current_sli": 90.0,
                          "sli_7d": 85.7,
                          "sli_30d": 90.0,
                          "sli_90d": 90.0,
                          "sli_delta": 5.0,
                          "slo_met": true,
                          "status": "healthy",
                          "scheduled_days": 30,
                          "completed_days": 27,
                          "missed_days": 3,
                          "error_budget_allowed_days": 4.5,
                          "error_budget_used_days": 3,
                          "error_budget_remaining_days": 1.5,
                          "error_budget_remaining_pct": 33.3,
                          "burn_rate": 0.67,
                          "burn_rate_7d": 0.95,
                          "current_streak": 4
                        }
                      ]
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "id": "h1",
                      "title": "Read 20 pages",
                      "description": "",
                      "color": "#6366F1",
                      "icon": "check_circle",
                      "frequency_type": "daily",
                      "weekdays": [0, 1, 2, 3, 4, 5, 6],
                      "target_per_day": 1,
                      "target_slo": 90.0,
                      "archived": false,
                      "created_at": "2026-11-14T00:00:00Z"
                    }
                    """.trimIndent(),
                ),
        )

        val dash = client.getSliDashboard(today = "2026-11-14", windowDays = 30)
        assertEquals(30, dash.windowDays)
        assertEquals(90.0, dash.overallSli, 0.01)
        assertEquals(33.3, dash.overallErrorBudgetRemainingPct, 0.01)
        assertEquals(1, dash.trend.size)
        assertEquals(1, dash.weekdaySli.size)
        assertEquals(1, dash.habits.size)
        assertEquals("Read 20 pages", dash.habits.first().title)
        assertEquals(0.67, dash.habits.first().burnRate, 0.01)

        val updated = client.updateHabit("h1", HabitUpdateRequest(targetSlo = 90.0))
        assertEquals(90.0, updated.targetSlo, 0.01)

        val sliReq = server.takeRequest()
        assertEquals("GET", sliReq.method)
        assertEquals("/api/stats/sli?today=2026-11-14&window_days=30", sliReq.path)

        val patchReq = server.takeRequest()
        assertEquals("PATCH", patchReq.method)
        assertEquals("/api/habits/h1", patchReq.path)
        assertEquals("{\"target_slo\":90.0}", patchReq.body.readUtf8())
    }

    @Test
    fun getPeriodScheduleParsesWeekAndMonthPayloads() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "period": "week",
                      "start_date": "2026-11-09",
                      "end_date": "2026-11-15",
                      "today": "2026-11-14",
                      "total_scheduled": 3,
                      "completed_count": 1,
                      "remaining_count": 2,
                      "overdue_count": 1,
                      "completion_rate": 33.3,
                      "habit_summaries": [
                        {
                          "habit_id": "h1",
                          "title": "Monthly Review",
                          "description": "Monthly summary on the 14th",
                          "color": "#16A34A",
                          "icon": "check_circle",
                          "frequency_type": "monthly",
                          "weekdays": [0, 1, 2, 3, 4, 5, 6],
                          "monthly_mode": "nth_weekday",
                          "monthly_day": 14,
                          "monthly_week": 2,
                          "monthly_weekday": 5,
                          "target_per_day": 1,
                          "scheduled_days": 1,
                          "completed_days": 0,
                          "remaining_days": 1,
                          "overdue_days": 0,
                          "next_due_date": "2026-11-14"
                        },
                        {
                          "habit_id": "h2",
                          "title": "Morning Run",
                          "description": "",
                          "color": "#2563EB",
                          "icon": "directions_run",
                          "frequency_type": "weekdays",
                          "weekdays": [0, 2, 4],
                          "target_per_day": 2,
                          "scheduled_days": 2,
                          "completed_days": 1,
                          "remaining_days": 1,
                          "overdue_days": 1,
                          "next_due_date": null
                        }
                      ],
                      "days": [
                        {
                          "date": "2026-11-13",
                          "weekday": 4,
                          "weekday_label": "Fri",
                          "is_today": false,
                          "is_past": true,
                          "is_future": false,
                          "scheduled_count": 1,
                          "completed_count": 0,
                          "pending_count": 1,
                          "items": [
                            {
                              "habit_id": "h2",
                              "title": "Morning Run",
                              "description": "",
                              "color": "#2563EB",
                              "icon": "directions_run",
                              "frequency_type": "weekdays",
                              "weekdays": [0, 2, 4],
                              "target_per_day": 2,
                              "date": "2026-11-13",
                              "count": 1,
                              "completed": false,
                              "note": "Halfway there",
                              "status": "overdue"
                            }
                          ]
                        },
                        {
                          "date": "2026-11-14",
                          "weekday": 5,
                          "weekday_label": "Sat",
                          "is_today": true,
                          "is_past": false,
                          "is_future": false,
                          "scheduled_count": 1,
                          "completed_count": 0,
                          "pending_count": 1,
                          "items": [
                            {
                              "habit_id": "h1",
                              "title": "Monthly Review",
                              "description": "Monthly summary on the 14th",
                              "color": "#16A34A",
                              "icon": "check_circle",
                              "frequency_type": "monthly",
                              "weekdays": [0, 1, 2, 3, 4, 5, 6],
                              "monthly_mode": "nth_weekday",
                              "monthly_day": 14,
                              "monthly_week": 2,
                              "monthly_weekday": 5,
                              "target_per_day": 1,
                              "date": "2026-11-14",
                              "count": 0,
                              "completed": false,
                              "note": "",
                              "status": "today"
                            }
                          ]
                        }
                      ]
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "period": "month",
                      "start_date": "2026-11-01",
                      "end_date": "2026-11-30",
                      "today": "2026-11-14",
                      "total_scheduled": 1,
                      "completed_count": 1,
                      "remaining_count": 0,
                      "overdue_count": 0,
                      "completion_rate": 100.0,
                      "habit_summaries": [],
                      "days": [
                        {
                          "date": "2026-11-20",
                          "weekday": 4,
                          "weekday_label": "Fri",
                          "is_today": false,
                          "is_past": false,
                          "is_future": true,
                          "scheduled_count": 1,
                          "completed_count": 1,
                          "pending_count": 0,
                          "items": [
                            {
                              "habit_id": "h1",
                              "title": "Monthly Review",
                              "frequency_type": "monthly",
                              "monthly_mode": "from_end",
                              "monthly_day": 11,
                              "target_per_day": 1,
                              "date": "2026-11-20",
                              "count": 1,
                              "completed": true,
                              "note": "",
                              "status": "completed"
                            }
                          ]
                        }
                      ]
                    }
                    """.trimIndent(),
                ),
        )

        client.authToken = "jwt-schedule"
        val weekSchedule = client.getPeriodSchedule(
            period = "week",
            anchorDate = "2026-11-14",
            today = "2026-11-14",
        )
        assertEquals("week", weekSchedule.period)
        assertEquals("2026-11-09", weekSchedule.startDate)
        assertEquals(3, weekSchedule.totalScheduled)
        assertEquals(1, weekSchedule.overdueCount)
        assertEquals(33.3, weekSchedule.completionRate, 0.001)
        assertEquals(2, weekSchedule.habitSummaries.size)
        assertEquals("monthly", weekSchedule.habitSummaries[0].frequencyType)
        assertEquals("nth_weekday", weekSchedule.habitSummaries[0].monthlyMode)
        assertEquals(2, weekSchedule.habitSummaries[0].monthlyWeek)
        assertEquals(5, weekSchedule.habitSummaries[0].monthlyWeekday)
        assertEquals("2026-11-14", weekSchedule.habitSummaries[0].nextDueDate)
        assertNull(weekSchedule.habitSummaries[1].nextDueDate)
        assertEquals(2, weekSchedule.days.size)
        assertEquals("overdue", weekSchedule.days[0].items[0].status)
        assertTrue(weekSchedule.days[0].isPast)
        assertEquals("today", weekSchedule.days[1].items[0].status)
        assertTrue(weekSchedule.days[1].isToday)

        val monthSchedule = client.getPeriodSchedule(period = "month")
        assertEquals("month", monthSchedule.period)
        assertEquals("2026-11-30", monthSchedule.endDate)
        assertEquals(100.0, monthSchedule.completionRate, 0.001)
        assertTrue(monthSchedule.days[0].isFuture)
        assertEquals("from_end", monthSchedule.days[0].items[0].monthlyMode)
        assertEquals("completed", monthSchedule.days[0].items[0].status)

        val weekReq = server.takeRequest()
        assertEquals("GET", weekReq.method)
        assertEquals("/api/habits/schedule?period=week&anchor_date=2026-11-14&today=2026-11-14", weekReq.path)
        assertEquals("Bearer jwt-schedule", weekReq.getHeader("Authorization"))

        val monthReq = server.takeRequest()
        assertEquals("GET", monthReq.method)
        assertEquals("/api/habits/schedule?period=month", monthReq.path)
    }

    @Test
    fun forgotResetAndChangePasswordEndpointsSerializeAndRotateAuthToken() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "message": "If an account exists for this email, a 6-digit verification code has been sent.",
                      "expires_in_minutes": 15,
                      "dev_reset_code": "123456"
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "access_token": "jwt-reset-1",
                      "token_type": "bearer",
                      "user": {
                        "id": "u1",
                        "name": "Shawn",
                        "email": "shawn@example.com",
                        "created_at": "2026-11-14T00:00:00Z"
                      }
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "access_token": "jwt-changed-2",
                      "token_type": "bearer",
                      "user": {
                        "id": "u1",
                        "name": "Shawn",
                        "email": "shawn@example.com",
                        "created_at": "2026-11-14T00:00:00Z"
                      }
                    }
                    """.trimIndent(),
                ),
        )

        val forgotResp = client.forgotPassword("shawn@example.com")
        assertEquals(15, forgotResp.expiresInMinutes)
        assertEquals("123456", forgotResp.devResetCode)

        val resetResp = client.resetPassword("shawn@example.com", "123456", "newSecret123")
        assertEquals("jwt-reset-1", resetResp.accessToken)
        assertEquals("jwt-reset-1", client.authToken)

        val changeResp = client.changePassword("newSecret123", "newerSecret456")
        assertEquals("jwt-changed-2", changeResp.accessToken)
        assertEquals("jwt-changed-2", client.authToken)

        val forgotReq = server.takeRequest()
        assertEquals("POST", forgotReq.method)
        assertEquals("/api/auth/forgot-password", forgotReq.path)
        assertTrue(forgotReq.body.readUtf8().contains("\"email\":\"shawn@example.com\""))

        val resetReq = server.takeRequest()
        assertEquals("POST", resetReq.method)
        assertEquals("/api/auth/reset-password", resetReq.path)
        val resetBody = resetReq.body.readUtf8()
        assertTrue(resetBody.contains("\"code\":\"123456\""))
        assertTrue(resetBody.contains("\"new_password\":\"newSecret123\""))

        val changeReq = server.takeRequest()
        assertEquals("POST", changeReq.method)
        assertEquals("/api/auth/change-password", changeReq.path)
        assertEquals("Bearer jwt-reset-1", changeReq.getHeader("Authorization"))
        val changeBody = changeReq.body.readUtf8()
        assertTrue(changeBody.contains("\"current_password\":\"newSecret123\""))
        assertTrue(changeBody.contains("\"new_password\":\"newerSecret456\""))
    }

    @Test
    fun registerVerifyAndResendEmailEndpointsSerializeAndStoreToken() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(201)
                .setBody(
                    """
                    {
                      "message": "A 6-digit verification code has been sent to your email.",
                      "email": "newuser@example.com",
                      "verification_required": true,
                      "expires_in_minutes": 15,
                      "dev_verification_code": "246810"
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "message": "A new 6-digit verification code has been sent to your email.",
                      "email": "newuser@example.com",
                      "verification_required": true,
                      "expires_in_minutes": 15,
                      "dev_verification_code": "135790"
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "access_token": "jwt-verified-1",
                      "token_type": "bearer",
                      "user": {
                        "id": "u2",
                        "name": "New User",
                        "email": "newuser@example.com",
                        "email_verified": true,
                        "created_at": "2026-11-15T00:00:00Z"
                      }
                    }
                    """.trimIndent(),
                ),
        )

        val regResp = client.register("New User", "newuser@example.com", "secret123")
        assertTrue(regResp.verificationRequired)
        assertEquals("newuser@example.com", regResp.email)
        assertEquals("246810", regResp.devVerificationCode)
        assertNull(client.authToken)

        val resendResp = client.resendVerification("newuser@example.com")
        assertEquals("135790", resendResp.devVerificationCode)
        assertNull(client.authToken)

        val verifyResp = client.verifyEmail("newuser@example.com", "135790")
        assertEquals("jwt-verified-1", verifyResp.accessToken)
        assertEquals("jwt-verified-1", client.authToken)
        assertTrue(verifyResp.user.emailVerified)

        val regReq = server.takeRequest()
        assertEquals("POST", regReq.method)
        assertEquals("/api/auth/register", regReq.path)
        assertTrue(regReq.body.readUtf8().contains("\"email\":\"newuser@example.com\""))

        val resendReq = server.takeRequest()
        assertEquals("POST", resendReq.method)
        assertEquals("/api/auth/resend-verification", resendReq.path)
        assertTrue(resendReq.body.readUtf8().contains("\"email\":\"newuser@example.com\""))

        val verifyReq = server.takeRequest()
        assertEquals("POST", verifyReq.method)
        assertEquals("/api/auth/verify-email", verifyReq.path)
        val verifyBody = verifyReq.body.readUtf8()
        assertTrue(verifyBody.contains("\"email\":\"newuser@example.com\""))
        assertTrue(verifyBody.contains("\"code\":\"135790\""))
    }

    @Test
    fun reminderTimeHelpersNormalizeSortDedupeAndFormatBadge() {
        assertEquals("08:05", normalizeReminderTime("8:05"))
        assertEquals("23:59", normalizeReminderTime(" 23:59 "))
        assertEquals("08:05", normalizeReminderTime("8:05 AM"))
        assertEquals("00:00", normalizeReminderTime("12:00 AM"))
        assertEquals("12:30", normalizeReminderTime("12:30 PM"))
        assertEquals("21:15", normalizeReminderTime("9:15 pm"))
        assertNull(normalizeReminderTime("13:00 PM"))
        assertNull(normalizeReminderTime("0:15 AM"))
        assertNull(normalizeReminderTime("24:00"))
        assertNull(normalizeReminderTime("09:60"))
        assertNull(normalizeReminderTime("not-a-time"))

        assertEquals("12:05 AM", formatTime12h("00:05"))
        assertEquals("12:00 PM", formatTime12h("12:00"))
        assertEquals("1:30 PM", formatTime12h("13:30"))
        assertEquals("01:30" to "PM", split24hTo12h("13:30"))
        assertEquals("12:05" to "AM", split24hTo12h("00:05"))
        assertEquals("13:30", resolveTimeWithMeridiem("01:30", "PM"))
        assertEquals("00:00", resolveTimeWithMeridiem("12:00", "AM"))
        assertEquals("21:15", resolveTimeWithMeridiem("21:15", "AM"))

        assertEquals(
            listOf("07:15", "08:30", "21:00"),
            normalizeReminderTimes(listOf("21:00", "8:30 AM", "08:30", "bad", "07:15")),
        )

        assertNull(formatReminderBadge(enabled = false, times = listOf("09:00"), mode = "alarm"))
        assertNull(formatReminderBadge(enabled = true, times = emptyList(), mode = "notification"))
        assertEquals(
            "🔔 8:30 AM",
            formatReminderBadge(enabled = true, times = listOf("8:30"), mode = "notification"),
        )
        assertEquals(
            "⏰ 7:00 AM, 12:30 PM (+1)",
            formatReminderBadge(
                enabled = true,
                times = listOf("21:00", "07:00", "12:30"),
                mode = "alarm",
            ),
        )
    }

    @Test
    fun computeNextTriggerDateTimeHandlesDailyWeeklyMonthlyAndCompletedToday() {
        val dailyHabit = Habit(
            id = "h-daily",
            title = "Hydrate",
            frequencyType = "daily",
            reminderEnabled = true,
            reminderTimes = listOf("08:00", "20:00"),
            reminderMode = "notification",
        )
        assertEquals(
            LocalDateTime.of(2026, 4, 6, 20, 0),
            computeNextTriggerDateTime(
                habit = dailyHabit,
                fromDateTime = LocalDateTime.of(2026, 4, 6, 9, 0),
                completedToday = false,
            ),
        )
        assertEquals(
            LocalDateTime.of(2026, 4, 7, 8, 0),
            computeNextTriggerDateTime(
                habit = dailyHabit,
                fromDateTime = LocalDateTime.of(2026, 4, 6, 9, 0),
                completedToday = true,
            ),
        )

        val fridayHabit = Habit(
            id = "h-fri",
            title = "Weekly Review",
            frequencyType = "weekdays",
            weekdays = listOf(4),
            reminderEnabled = true,
            reminderTimes = listOf("09:00"),
            reminderMode = "alarm",
        )
        assertEquals(
            LocalDateTime.of(2026, 4, 10, 9, 0),
            computeNextTriggerDateTime(
                habit = fridayHabit,
                fromDateTime = LocalDateTime.of(2026, 4, 6, 7, 0),
            ),
        )

        val monthlyClampedHabit = Habit(
            id = "h-mon",
            title = "Month End Report",
            frequencyType = "monthly",
            monthlyMode = "from_start",
            monthlyDay = 31,
            reminderEnabled = true,
            reminderTimes = listOf("18:00"),
            reminderMode = "alarm",
        )
        assertEquals(
            LocalDateTime.of(2026, 4, 30, 18, 0),
            computeNextTriggerDateTime(
                habit = monthlyClampedHabit,
                fromDateTime = LocalDateTime.of(2026, 4, 29, 10, 0),
            ),
        )

        assertNull(
            computeNextTriggerDateTime(
                habit = dailyHabit.copy(archived = true),
                fromDateTime = LocalDateTime.of(2026, 4, 6, 9, 0),
            ),
        )
        assertNull(
            computeNextTriggerDateTime(
                habit = dailyHabit.copy(reminderEnabled = false),
                fromDateTime = LocalDateTime.of(2026, 4, 6, 9, 0),
            ),
        )
    }

    @Test
    fun createUpdateAndGetRemindersOverviewSerializeReminderFields() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(201)
                .setBody(
                    """
                    {
                      "id": "h-rem-1",
                      "title": "Deep Work",
                      "description": "",
                      "color": "#6366F1",
                      "icon": "check_circle",
                      "frequency_type": "daily",
                      "weekdays": [0, 1, 2, 3, 4, 5, 6],
                      "target_per_day": 1,
                      "target_slo": 90.0,
                      "archived": false,
                      "reminder_enabled": true,
                      "reminder_times": ["09:00", "14:00"],
                      "reminder_mode": "alarm",
                      "reminder_snooze_minutes": 15,
                      "reminder_message": "Phones away",
                      "created_at": "2026-04-06T00:00:00Z"
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "id": "h-rem-1",
                      "title": "Deep Work",
                      "description": "",
                      "color": "#6366F1",
                      "icon": "check_circle",
                      "frequency_type": "daily",
                      "weekdays": [0, 1, 2, 3, 4, 5, 6],
                      "target_per_day": 1,
                      "target_slo": 90.0,
                      "archived": false,
                      "reminder_enabled": true,
                      "reminder_times": ["09:30"],
                      "reminder_mode": "alarm",
                      "reminder_snooze_minutes": 20,
                      "reminder_message": "Start sprint",
                      "created_at": "2026-04-06T00:00:00Z"
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "date": "2026-04-06",
                      "now_time": "08:30",
                      "enabled_habits_count": 1,
                      "alarm_habits_count": 1,
                      "notification_habits_count": 0,
                      "scheduled_today_count": 1,
                      "pending_today_triggers": 1,
                      "items": [
                        {
                          "habit_id": "h-rem-1",
                          "title": "Deep Work",
                          "color": "#6366F1",
                          "icon": "check_circle",
                          "frequency_type": "daily",
                          "scheduled_today": true,
                          "completed_today": false,
                          "count": 0,
                          "target_per_day": 1,
                          "reminder_enabled": true,
                          "reminder_times": ["09:30"],
                          "reminder_mode": "alarm",
                          "reminder_snooze_minutes": 20,
                          "reminder_message": "Start sprint",
                          "next_trigger_date": "2026-04-06",
                          "next_trigger_time": "09:30",
                          "due_today_times": ["09:30"]
                        }
                      ]
                    }
                    """.trimIndent(),
                ),
        )

        val created = client.createHabit(
            HabitCreateRequest(
                title = "Deep Work",
                reminderEnabled = true,
                reminderTimes = listOf("09:00", "14:00"),
                reminderMode = "alarm",
                reminderSnoozeMinutes = 15,
                reminderMessage = "Phones away",
            ),
        )
        assertTrue(created.reminderEnabled)
        assertEquals(listOf("09:00", "14:00"), created.reminderTimes)
        assertEquals("alarm", created.reminderMode)
        assertEquals(15, created.reminderSnoozeMinutes)
        assertEquals("Phones away", created.reminderMessage)

        val patched = client.updateHabit(
            habitId = "h-rem-1",
            request = HabitUpdateRequest(
                reminderTimes = listOf("09:30"),
                reminderSnoozeMinutes = 20,
                reminderMessage = "Start sprint",
            ),
        )
        assertEquals(listOf("09:30"), patched.reminderTimes)
        assertEquals(20, patched.reminderSnoozeMinutes)

        val overview = client.getRemindersOverview(targetDate = "2026-04-06", nowTime = "08:30")
        assertEquals(1, overview.enabledHabitsCount)
        assertEquals(1, overview.alarmHabitsCount)
        assertEquals(1, overview.pendingTodayTriggers)
        assertEquals(1, overview.items.size)
        assertEquals("09:30", overview.items.first().nextTriggerTime)
        assertEquals(listOf("09:30"), overview.items.first().dueTodayTimes)

        val createReq = server.takeRequest()
        val createBody = createReq.body.readUtf8()
        assertTrue(createBody.contains("\"reminder_enabled\":true"))
        assertTrue(createBody.contains("\"reminder_mode\":\"alarm\""))
        assertTrue(createBody.contains("\"reminder_snooze_minutes\":15"))

        val patchReq = server.takeRequest()
        val patchBody = patchReq.body.readUtf8()
        assertTrue(patchBody.contains("\"reminder_times\":[\"09:30\"]"))
        assertTrue(patchBody.contains("\"reminder_snooze_minutes\":20"))
        assertFalse(patchBody.contains("title"))

        val overviewReq = server.takeRequest()
        assertEquals("GET", overviewReq.method)
        assertEquals("/api/habits/reminders?target_date=2026-04-06&now_time=08%3A30", overviewReq.path)
    }

    @Test
    fun habitModesValidationAndApiSerializationWork() = runTest {
        val validStrict = validateHabitModeTimes("strict", "8:30", "08:45", "10:00")
        assertNull(validStrict.errorMessage)
        assertEquals("08:30", validStrict.remindTime)
        assertEquals("08:45", validStrict.forceStartTime)
        assertEquals("10:00", validStrict.forceEndTime)

        val validStrictAmPm = validateHabitModeTimes(
            mode = "strict",
            remindRaw = "08:30",
            startRaw = "08:45",
            endRaw = "01:30",
            remindMeridiem = "AM",
            startMeridiem = "AM",
            endMeridiem = "PM",
        )
        assertNull(validStrictAmPm.errorMessage)
        assertEquals("08:30", validStrictAmPm.remindTime)
        assertEquals("08:45", validStrictAmPm.forceStartTime)
        assertEquals("13:30", validStrictAmPm.forceEndTime)

        val badStrict = validateHabitModeTimes("strict", "09:00", "08:45", "10:00")
        assertTrue(!badStrict.errorMessage.isNullOrBlank())

        assertNull(formatHabitModeSummary("free"))
        assertEquals(
            "Mode 1 · Strict (Remind 8:30 AM · Start 8:45 AM · End 10:00 AM)",
            formatHabitModeSummary("strict", "08:30", "08:45", "10:00"),
        )

        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    [
                      {
                        "id": "h-mode-1",
                        "title": "Deep Work",
                        "description": "",
                        "color": "#6366F1",
                        "icon": "check_circle",
                        "frequency_type": "daily",
                        "weekdays": [0, 1, 2, 3, 4, 5, 6],
                        "target_per_day": 1,
                        "target_slo": 85.0,
                        "mode": "strict",
                        "remind_time": "08:30",
                        "force_start_time": "08:45",
                        "force_end_time": "10:00",
                        "archived": false,
                        "created_at": "2026-11-15T00:00:00Z",
                        "date": "2026-11-15",
                        "scheduled_today": true,
                        "count": 0,
                        "completed": false,
                        "note": "",
                        "current_streak": 1,
                        "best_streak": 3,
                        "day_status": "reminding",
                        "violation_reason": null,
                        "started_at_time": null,
                        "started_on_time": false,
                        "is_late": false,
                        "can_start": true
                      }
                    ]
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "id": "h-mode-1",
                      "title": "Deep Work",
                      "description": "",
                      "color": "#6366F1",
                      "icon": "check_circle",
                      "frequency_type": "daily",
                      "weekdays": [0, 1, 2, 3, 4, 5, 6],
                      "target_per_day": 1,
                      "target_slo": 85.0,
                      "mode": "strict",
                      "remind_time": "08:30",
                      "force_start_time": "08:45",
                      "force_end_time": "10:00",
                      "archived": false,
                      "created_at": "2026-11-15T00:00:00Z",
                      "date": "2026-11-15",
                      "scheduled_today": true,
                      "count": 0,
                      "completed": false,
                      "note": "",
                      "current_streak": 1,
                      "best_streak": 3,
                      "day_status": "in_progress",
                      "violation_reason": null,
                      "started_at_time": "08:40",
                      "started_on_time": true,
                      "is_late": false,
                      "can_start": false
                    }
                    """.trimIndent(),
                ),
        )

        client.authToken = "jwt-modes"
        val todayList = client.getTodayHabits(
            targetDate = "2026-11-15",
            clientToday = "2026-11-15",
            clientTime = "08:35",
        )
        assertEquals(1, todayList.size)
        assertEquals("strict", todayList.first().mode)
        assertEquals("reminding", todayList.first().dayStatus)
        assertTrue(todayList.first().canStart)

        val started = client.checkinHabit(
            habitId = "h-mode-1",
            request = CheckinRequest(
                date = "2026-11-15",
                action = "start",
                clientToday = "2026-11-15",
                clientTime = "08:40",
            ),
        )
        assertEquals("in_progress", started.dayStatus)
        assertTrue(started.startedOnTime)
        assertEquals("08:40", started.startedAtTime)
        assertFalse(started.canStart)

        val todayReq = server.takeRequest()
        assertEquals(
            "/api/habits/today?target_date=2026-11-15&client_today=2026-11-15&client_time=08%3A35",
            todayReq.path,
        )
        val startReq = server.takeRequest()
        val startBody = startReq.body.readUtf8()
        assertTrue(startBody.contains("\"action\":\"start\""))
        assertTrue(startBody.contains("\"client_today\":\"2026-11-15\""))
        assertTrue(startBody.contains("\"client_time\":\"08:40\""))
    }

    @Test
    fun mergedHabitModeAndRemindersComputeTriggersWithoutSeparateToggle() {
        val strictHabit = Habit(
            id = "h-strict-merged",
            title = "Morning Focus",
            frequencyType = "daily",
            mode = "strict",
            remindTime = "08:30",
            forceStartTime = "08:45",
            forceEndTime = "10:00",
            reminderMode = "alarm",
        )
        assertEquals(listOf("08:30"), effectiveReminderTimes(strictHabit))
        assertEquals("⏰ 8:30 AM", formatReminderBadge(strictHabit))
        assertEquals(
            LocalDateTime.of(2026, 4, 6, 8, 30),
            computeNextTriggerDateTime(
                habit = strictHabit,
                fromDateTime = LocalDateTime.of(2026, 4, 6, 8, 0),
            ),
        )

        val windowHabit = Habit(
            id = "h-win-merged",
            title = "Workout",
            frequencyType = "daily",
            mode = "window",
            remindTime = "17:30",
            forceEndTime = "21:00",
            reminderMode = "notification",
        )
        assertEquals(listOf("17:30"), effectiveReminderTimes(windowHabit))
        assertEquals("🔔 5:30 PM", formatReminderBadge(windowHabit))

        val reminderModeHabit = Habit(
            id = "h-rem-merged",
            title = "Hydrate",
            frequencyType = "daily",
            mode = "reminder",
            remindTime = "09:00",
            reminderTimes = listOf("09:00", "20:00"),
            reminderMode = "alarm",
        )
        assertEquals(listOf("09:00", "20:00"), effectiveReminderTimes(reminderModeHabit))
        assertEquals(
            "Mode 3 · Alarm",
            formatHabitModeSummary(mode = "reminder", reminderMode = "alarm"),
        )
        assertEquals(
            LocalDateTime.of(2026, 4, 6, 20, 0),
            computeNextTriggerDateTime(
                habit = reminderModeHabit,
                fromDateTime = LocalDateTime.of(2026, 4, 6, 10, 0),
            ),
        )

        // Companion reminder badge avoids duplicating remindTime next to modeSummary
        assertEquals("⏰ Alarm", formatCompanionReminderBadge(strictHabit))
        assertNull(formatCompanionReminderBadge(windowHabit))
        assertEquals("⏰ 9:00 AM, 8:00 PM", formatCompanionReminderBadge(reminderModeHabit))
        assertEquals(
            listOf("Free Mode", "1 · Strict", "2 · Window", "3 · Reminder"),
            HABIT_MODE_OPTIONS.map { it.chipLabel },
        )
    }

    @Test
    fun editCheckinAndGetHabitHistoryRoundTrip() = runTest {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "id": "h-hist-1",
                      "title": "Deep Work",
                      "frequency_type": "daily",
                      "target_per_day": 1,
                      "mode": "strict",
                      "created_date": "2026-11-10",
                      "date": "2026-11-14",
                      "scheduled_today": true,
                      "count": 1,
                      "completed": true,
                      "note": "Fixed history",
                      "current_streak": 3,
                      "best_streak": 3,
                      "day_status": "on_time",
                      "started_on_time": true,
                      "is_late": false,
                      "can_start": false,
                      "can_edit": true
                    }
                    """.trimIndent(),
                ),
        )
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody(
                    """
                    {
                      "habit": {
                        "id": "h-hist-1",
                        "title": "Deep Work",
                        "frequency_type": "daily",
                        "target_per_day": 1,
                        "mode": "strict",
                        "created_date": "2026-11-10"
                      },
                      "month": "2026-11",
                      "start_date": "2026-11-01",
                      "end_date": "2026-11-30",
                      "first_weekday": 6,
                      "created_date": "2026-11-10",
                      "today": "2026-11-16",
                      "can_prev_month": false,
                      "can_next_month": false,
                      "current_streak": 3,
                      "best_streak": 3,
                      "completion_rate_30d": 85.7,
                      "total_completions": 6,
                      "late_completions": 0,
                      "month_scheduled": 7,
                      "month_completed_on_time": 6,
                      "month_late_makeups": 0,
                      "month_missed": 1,
                      "days": [
                        {
                          "date": "2026-11-09",
                          "day": 9,
                          "weekday": 0,
                          "weekday_label": "Mon",
                          "scheduled": true,
                          "editable": false,
                          "is_today": false,
                          "count": 0,
                          "completed": false,
                          "is_late": false,
                          "note": "",
                          "state": "before_created"
                        },
                        {
                          "date": "2026-11-14",
                          "day": 14,
                          "weekday": 5,
                          "weekday_label": "Sat",
                          "scheduled": true,
                          "editable": true,
                          "is_today": false,
                          "count": 1,
                          "completed": true,
                          "is_late": false,
                          "note": "Fixed history",
                          "state": "on_time"
                        }
                      ]
                    }
                    """.trimIndent(),
                ),
        )

        val edited = client.checkinHabit(
            habitId = "h-hist-1",
            request = CheckinRequest(
                date = "2026-11-14",
                action = "edit",
                count = 1,
                note = "Fixed history",
                statusOverride = "on_time",
                clientToday = "2026-11-16",
                clientTime = "09:00",
            ),
        )
        assertTrue(edited.completed)
        assertEquals("on_time", edited.dayStatus)
        assertEquals("Fixed history", edited.note)
        assertTrue(edited.canEdit)

        val history = client.getHabitHistory(
            habitId = "h-hist-1",
            month = "2026-11",
            clientToday = "2026-11-16",
            clientTime = "09:00",
        )
        assertEquals("2026-11-10", history.createdDate)
        assertEquals(6, history.monthCompletedOnTime)
        assertEquals(2, history.days.size)
        assertFalse(history.days[0].editable)
        assertEquals("before_created", history.days[0].state)
        assertTrue(history.days[1].editable)
        assertEquals("on_time", history.days[1].state)

        val editReq = server.takeRequest()
        val editBody = editReq.body.readUtf8()
        assertTrue(editBody.contains("\"action\":\"edit\""))
        assertTrue(editBody.contains("\"status_override\":\"on_time\""))

        val histReq = server.takeRequest()
        assertEquals(
            "/api/habits/h-hist-1/history?month=2026-11&client_today=2026-11-16&client_time=09%3A00",
            histReq.path,
        )
    }

    @Test
    fun createdDateExtractionAndUtcPickerRoundTrip() {
        val today = LocalDate.of(2026, 11, 16)
        assertEquals(
            LocalDate.of(2026, 11, 10),
            extractHabitCreatedDate("2026-11-10", "2026-11-10T23:55:00Z", today),
        )
        assertEquals(
            today,
            extractHabitCreatedDate("", "2026-11-17T03:00:00Z", today),
        )
        assertNull(
            extractHabitCreatedDate("", "2026-11-25T00:00:00Z", today),
        )

        val sample = LocalDate.of(2026, 11, 14)
        val millis = localDateToUtcPickerMillis(sample)
        assertEquals(sample, utcPickerMillisToLocalDate(millis))
    }
}
