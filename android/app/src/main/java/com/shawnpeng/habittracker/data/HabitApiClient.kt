package com.shawnpeng.habittracker.data

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody

class ApiException(
    override val message: String,
    val statusCode: Int? = null,
) : Exception(message)

class HabitApiClient(
    private val httpClient: OkHttpClient = defaultHttpClient(),
    initialBaseUrl: String = DEFAULT_EMULATOR_URL,
) {
    @Volatile
    var baseUrl: String = normalizeBaseUrl(initialBaseUrl)
        private set

    @Volatile
    var authToken: String? = null

    fun setBaseUrl(rawUrl: String): String {
        val normalized = normalizeBaseUrl(rawUrl)
        baseUrl = normalized
        return normalized
    }

    suspend fun register(name: String, email: String, password: String): TokenResponse {
        val body = encodeFullJson.encodeToString(
            RegisterRequest(name = name, email = email, password = password),
        )
        val response: TokenResponse = executeJson(
            method = "POST",
            pathSegments = listOf("api", "auth", "register"),
            jsonBody = body,
        )
        authToken = response.accessToken
        return response
    }

    suspend fun login(email: String, password: String): TokenResponse {
        val body = encodeFullJson.encodeToString(
            LoginRequest(email = email, password = password),
        )
        val response: TokenResponse = executeJson(
            method = "POST",
            pathSegments = listOf("api", "auth", "login"),
            jsonBody = body,
        )
        authToken = response.accessToken
        return response
    }

    suspend fun getMe(): UserPublic {
        return executeJson(
            method = "GET",
            pathSegments = listOf("api", "auth", "me"),
        )
    }

    suspend fun getTodayHabits(targetDate: String): List<HabitToday> {
        return executeJson(
            method = "GET",
            pathSegments = listOf("api", "habits", "today"),
            queryParams = mapOf("target_date" to targetDate),
        )
    }

    suspend fun checkinHabit(habitId: String, request: CheckinRequest): HabitToday {
        val body = buildJsonObject {
            put("date", request.date)
            put("action", request.action)
            request.count?.let { put("count", it) }
            request.note?.let { put("note", it) }
        }.toString()
        return executeJson(
            method = "POST",
            pathSegments = listOf("api", "habits", habitId, "checkin"),
            jsonBody = body,
        )
    }

    suspend fun listHabits(includeArchived: Boolean = false): List<Habit> {
        return executeJson(
            method = "GET",
            pathSegments = listOf("api", "habits"),
            queryParams = mapOf("include_archived" to includeArchived.toString()),
        )
    }

    suspend fun createHabit(request: HabitCreateRequest): Habit {
        val body = encodeFullJson.encodeToString(request)
        return executeJson(
            method = "POST",
            pathSegments = listOf("api", "habits"),
            jsonBody = body,
        )
    }

    suspend fun updateHabit(habitId: String, request: HabitUpdateRequest): Habit {
        val body = encodePatchJson.encodeToString(request)
        return executeJson(
            method = "PATCH",
            pathSegments = listOf("api", "habits", habitId),
            jsonBody = body,
        )
    }

    suspend fun deleteHabit(habitId: String) {
        executeRaw(
            method = "DELETE",
            pathSegments = listOf("api", "habits", habitId),
        )
    }

    suspend fun getStatsSummary(today: String): StatsSummary {
        return executeJson(
            method = "GET",
            pathSegments = listOf("api", "stats", "summary"),
            queryParams = mapOf("today" to today),
        )
    }

    suspend fun getSliDashboard(today: String, windowDays: Int = 30): SliDashboard {
        return executeJson(
            method = "GET",
            pathSegments = listOf("api", "stats", "sli"),
            queryParams = mapOf(
                "today" to today,
                "window_days" to windowDays.toString(),
            ),
        )
    }

    suspend fun getPeriodSchedule(
        period: String = "week",
        anchorDate: String? = null,
        today: String? = null,
    ): PeriodSchedule {
        return executeJson(
            method = "GET",
            pathSegments = listOf("api", "habits", "schedule"),
            queryParams = buildMap {
                put("period", period)
                anchorDate?.let { put("anchor_date", it) }
                today?.let { put("today", it) }
            },
        )
    }

    private suspend inline fun <reified T> executeJson(
        method: String,
        pathSegments: List<String>,
        queryParams: Map<String, String> = emptyMap(),
        jsonBody: String? = null,
    ): T {
        val raw = executeRaw(method, pathSegments, queryParams, jsonBody)
        return try {
            json.decodeFromString<T>(raw)
        } catch (exc: Exception) {
            throw ApiException("响应数据解析失败: ${exc.message ?: "格式错误"}")
        }
    }

    private suspend fun executeRaw(
        method: String,
        pathSegments: List<String>,
        queryParams: Map<String, String> = emptyMap(),
        jsonBody: String? = null,
    ): String = withContext(Dispatchers.IO) {
        val url = buildUrl(pathSegments, queryParams)
        val requestBuilder = Request.Builder()
            .url(url)
            .header("Accept", "application/json")

        val token = authToken
        if (!token.isNullOrBlank()) {
            requestBuilder.header("Authorization", "Bearer $token")
        }

        val requestBody: RequestBody? = when {
            jsonBody != null -> jsonBody.toRequestBody(JSON_MEDIA_TYPE)
            method == "POST" || method == "PATCH" || method == "PUT" -> {
                ByteArray(0).toRequestBody(null)
            }
            else -> null
        }

        requestBuilder.method(method, requestBody)
        val request = requestBuilder.build()

        val response = try {
            httpClient.newCall(request).execute()
        } catch (exc: IOException) {
            throw ApiException("无法连接服务器 $baseUrl (${exc.message ?: "网络异常"})")
        }

        response.use { resp ->
            val rawBody = resp.body?.string().orEmpty()
            if (resp.code == 204) {
                return@withContext ""
            }
            if (!resp.isSuccessful) {
                throw ApiException(
                    message = parseErrorDetail(rawBody, resp.code),
                    statusCode = resp.code,
                )
            }
            return@withContext rawBody
        }
    }

    private fun buildUrl(
        pathSegments: List<String>,
        queryParams: Map<String, String>,
    ): HttpUrl {
        val builder = baseUrl.toHttpUrl().newBuilder()
        pathSegments.forEach { segment -> builder.addPathSegment(segment) }
        queryParams.forEach { (key, value) -> builder.addQueryParameter(key, value) }
        return builder.build()
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

        private val json = Json {
            ignoreUnknownKeys = true
            coerceInputValues = true
            isLenient = true
        }

        private val encodeFullJson = Json {
            encodeDefaults = true
            ignoreUnknownKeys = true
        }

        private val encodePatchJson = Json {
            encodeDefaults = false
            ignoreUnknownKeys = true
        }

        fun defaultHttpClient(): OkHttpClient {
            return OkHttpClient.Builder()
                .connectTimeout(12, TimeUnit.SECONDS)
                .readTimeout(12, TimeUnit.SECONDS)
                .writeTimeout(12, TimeUnit.SECONDS)
                .build()
        }

        fun normalizeBaseUrl(raw: String): String {
            val trimmed = raw.trim()
            if (trimmed.isEmpty()) {
                throw ApiException("请输入服务器地址")
            }
            val withScheme = if (
                trimmed.startsWith("http://", ignoreCase = true) ||
                trimmed.startsWith("https://", ignoreCase = true)
            ) {
                trimmed
            } else {
                "http://$trimmed"
            }
            val cleaned = withScheme.trimEnd('/')
            cleaned.toHttpUrlOrNull() ?: throw ApiException("服务器地址格式无效: $raw")
            return cleaned
        }

        fun parseErrorDetail(rawBody: String, statusCode: Int): String {
            if (rawBody.isBlank()) {
                return "请求失败 (HTTP $statusCode)"
            }
            return try {
                val root = json.parseToJsonElement(rawBody).jsonObject
                val detail = root["detail"]
                when {
                    detail is JsonPrimitive && detail.isString -> detail.content
                    detail is JsonArray && detail.isNotEmpty() -> {
                        val first = detail.firstOrNull()
                        if (first is JsonObject) {
                            val msg = first["msg"]
                            if (msg is JsonPrimitive && msg.isString) {
                                return msg.content
                            }
                        }
                        "请求失败 (HTTP $statusCode)"
                    }
                    else -> "请求失败 (HTTP $statusCode)"
                }
            } catch (_: Exception) {
                "请求失败 (HTTP $statusCode)"
            }
        }
    }
}
