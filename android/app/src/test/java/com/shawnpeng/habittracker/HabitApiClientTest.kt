package com.shawnpeng.habittracker

import androidx.compose.ui.graphics.Color
import com.shawnpeng.habittracker.data.ApiException
import com.shawnpeng.habittracker.data.CheckinRequest
import com.shawnpeng.habittracker.data.HabitApiClient
import com.shawnpeng.habittracker.data.HabitUpdateRequest
import com.shawnpeng.habittracker.data.parseHabitColor
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
}
