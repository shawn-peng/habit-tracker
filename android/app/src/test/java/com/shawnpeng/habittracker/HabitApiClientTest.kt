package com.shawnpeng.habittracker

import androidx.compose.ui.graphics.Color
import com.shawnpeng.habittracker.data.ApiException
import com.shawnpeng.habittracker.data.CheckinRequest
import com.shawnpeng.habittracker.data.HabitApiClient
import com.shawnpeng.habittracker.data.HabitCreateRequest
import com.shawnpeng.habittracker.data.HabitUpdateRequest
import com.shawnpeng.habittracker.data.formatFrequencySummary
import com.shawnpeng.habittracker.data.parseHabitColor
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
        assertEquals("每天", formatFrequencySummary("daily"))
        assertEquals("周一、周三、周五", formatFrequencySummary("weekdays", listOf(0, 2, 4)))
        assertEquals(
            "每月第 15 天",
            formatFrequencySummary("monthly", monthlyMode = "from_start", monthlyDay = 15),
        )
        assertEquals(
            "每月最后一天",
            formatFrequencySummary("monthly", monthlyMode = "from_end", monthlyDay = 1),
        )
        assertEquals(
            "每月倒数第 3 天",
            formatFrequencySummary("monthly", monthlyMode = "from_end", monthlyDay = 3),
        )
        assertEquals(
            "每月第 2 周 · 周一",
            formatFrequencySummary("monthly", monthlyMode = "nth_weekday", monthlyWeek = 2, monthlyWeekday = 0),
        )
        assertEquals(
            "每月最后一周 · 周五",
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
            ),
        )
        assertEquals("monthly", created.frequencyType)
        assertEquals("from_end", created.monthlyMode)
        assertEquals(2, created.monthlyDay)

        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/api/habits", req.path)
        val rawBody = req.body.readUtf8()
        assertTrue(rawBody.contains("\"frequency_type\":\"monthly\""))
        assertTrue(rawBody.contains("\"monthly_mode\":\"from_end\""))
        assertTrue(rawBody.contains("\"monthly_day\":2"))
        assertTrue(rawBody.contains("\"monthly_week\":1"))
        assertTrue(rawBody.contains("\"monthly_weekday\":0"))
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
                          "title": "月度复盘",
                          "description": "每月 14 号完成总结",
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
                          "title": "晨跑",
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
                          "weekday_label": "周五",
                          "is_today": false,
                          "is_past": true,
                          "is_future": false,
                          "scheduled_count": 1,
                          "completed_count": 0,
                          "pending_count": 1,
                          "items": [
                            {
                              "habit_id": "h2",
                              "title": "晨跑",
                              "description": "",
                              "color": "#2563EB",
                              "icon": "directions_run",
                              "frequency_type": "weekdays",
                              "weekdays": [0, 2, 4],
                              "target_per_day": 2,
                              "date": "2026-11-13",
                              "count": 1,
                              "completed": false,
                              "note": "完成一半",
                              "status": "overdue"
                            }
                          ]
                        },
                        {
                          "date": "2026-11-14",
                          "weekday": 5,
                          "weekday_label": "周六",
                          "is_today": true,
                          "is_past": false,
                          "is_future": false,
                          "scheduled_count": 1,
                          "completed_count": 0,
                          "pending_count": 1,
                          "items": [
                            {
                              "habit_id": "h1",
                              "title": "月度复盘",
                              "description": "每月 14 号完成总结",
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
                          "weekday_label": "周五",
                          "is_today": false,
                          "is_past": false,
                          "is_future": true,
                          "scheduled_count": 1,
                          "completed_count": 1,
                          "pending_count": 0,
                          "items": [
                            {
                              "habit_id": "h1",
                              "title": "月度复盘",
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
}
