import asyncio
import calendar
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
import re
from typing import Literal

from bson import ObjectId
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core import (
    ChangePasswordRequest,
    CheckinRequest,
    DailyActivityPoint,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    HabitCreate,
    HabitHistoryOut,
    HabitOut,
    HabitStreakStat,
    HabitTodayOut,
    HabitUpdate,
    LoginRequest,
    MAX_REMINDER_TIMES,
    PeriodScheduleOut,
    RESET_MAX_ATTEMPTS,
    RESET_MAX_REQUESTS_PER_WINDOW,
    RESET_RATE_WINDOW_MINUTES,
    RegisterRequest,
    RegisterResponse,
    RemindersOverviewOut,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SliDashboardOut,
    StatsSummaryOut,
    TokenResponse,
    UserPublic,
    VerifyEmailRequest,
    build_habit_history,
    build_period_schedule,
    build_reminders_overview,
    build_sli_dashboard,
    compute_30d_completion_rate,
    compute_period_bounds,
    compute_streaks,
    create_access_token,
    ensure_indexes,
    ensure_utc,
    evaluate_habit_day_status,
    extract_habit_mode_fields,
    extract_reminder_fields,
    format_habit_created_date,
    format_habit_created_time,
    generate_reset_code,
    get_current_user,
    get_db,
    habit_sli_start_date,
    hash_password,
    hash_reset_code,
    hash_verification_code,
    is_scheduled_on,
    normalize_reminder_time,
    resolve_client_clock,
    resolve_habit_created_date,
    send_password_reset_email,
    send_registration_verification_email,
    settings,
    validate_and_normalize_mode_times,
    verify_password,
    verify_reset_code,
    verify_verification_code,
)

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tuned for scale-to-zero Cloud Run (max-instances=1, async I/O) + MongoDB Atlas M0:
    # - maxPoolSize=10: sufficient async concurrency while staying well under M0's 500-conn limit
    # - minPoolSize=0 & maxIdleTimeMS=60000: release idle sockets promptly before scale-down
    # - connectTimeoutMS=10000 & serverSelectionTimeoutMS=10000: fail fast on network/TLS issues
    async with AsyncMongoClient(
        settings.mongodb_uri,
        maxPoolSize=10,
        minPoolSize=0,
        maxIdleTimeMS=60000,
        connectTimeoutMS=10000,
        serverSelectionTimeoutMS=10000,
    ) as client:
        db = client[settings.mongodb_db_name]
        await ensure_indexes(db)
        app.state.mongodb = db
        yield


app = FastAPI(
    title="Habit & Routine Tracker API",
    version="1.0.0",
    lifespan=lifespan,
)

# Wildcard CORS with Bearer JWT headers allows Web (Pyodide), Desktop, iOS, and Android clients
allow_origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=(allow_origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _serialize_user(user_doc: dict) -> UserPublic:
    return UserPublic(
        id=str(user_doc["_id"]),
        name=user_doc["name"],
        email=user_doc["email"],
        email_verified=bool(user_doc.get("email_verified", True)),
        created_at=user_doc["created_at"],
    )


def _serialize_habit(habit_doc: dict) -> HabitOut:
    (
        reminder_enabled,
        reminder_times,
        reminder_mode,
        reminder_snooze_minutes,
        reminder_message,
    ) = extract_reminder_fields(habit_doc)
    mode, remind_time, force_start_time, force_end_time = extract_habit_mode_fields(
        habit_doc
    )
    return HabitOut(
        id=str(habit_doc["_id"]),
        title=habit_doc["title"],
        description=habit_doc.get("description", ""),
        color=habit_doc.get("color", "#6366F1"),
        icon=habit_doc.get("icon", "check_circle"),
        frequency_type=habit_doc.get("frequency_type", "daily"),
        weekdays=habit_doc.get("weekdays", [0, 1, 2, 3, 4, 5, 6]),
        monthly_mode=habit_doc.get("monthly_mode", "from_start"),
        monthly_day=habit_doc.get("monthly_day", 1),
        monthly_week=habit_doc.get("monthly_week", 1),
        monthly_weekday=habit_doc.get("monthly_weekday", 0),
        target_per_day=habit_doc.get("target_per_day", 1),
        target_slo=round(float(habit_doc.get("target_slo", 85.0)), 1),
        mode=mode,
        remind_time=remind_time,
        force_start_time=force_start_time,
        force_end_time=force_end_time,
        reminder_enabled=reminder_enabled,
        reminder_times=reminder_times,
        reminder_mode=reminder_mode,
        reminder_snooze_minutes=reminder_snooze_minutes,
        reminder_message=reminder_message,
        archived=habit_doc.get("archived", False),
        created_date=format_habit_created_date(habit_doc),
        created_time=format_habit_created_time(habit_doc),
        created_at=habit_doc["created_at"],
    )


def _parse_iso_date(raw: str | None) -> date:
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format, expected YYYY-MM-DD",
        ) from exc


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check(db: AsyncDatabase = Depends(get_db)) -> dict:
    await db.command("ping")
    return {"status": "ok", "database": "connected"}


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------
def _check_code_rate_limit(
    existing_record: dict | None,
    now: datetime,
    error_detail: str,
) -> tuple[int, datetime]:
    in_window = bool(
        existing_record
        and existing_record.get("window_started_at")
        and ensure_utc(existing_record["window_started_at"])
        > now - timedelta(minutes=RESET_RATE_WINDOW_MINUTES)
    )
    if (
        in_window
        and int(existing_record.get("send_count", 0)) >= RESET_MAX_REQUESTS_PER_WINDOW
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_detail,
        )
    send_count = (int(existing_record.get("send_count", 0)) + 1) if in_window else 1
    window_started_at = existing_record["window_started_at"] if in_window else now
    return send_count, window_started_at


async def _verify_code_or_raise(
    collection,
    email_norm: str,
    code: str,
    now: datetime,
    verifier,
) -> None:
    record = await collection.find_one({"email": email_norm})
    if (
        not record
        or not record.get("code_hash")
        or ensure_utc(record["expires_at"]) < now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    attempts = int(record.get("attempts", 0))
    if attempts >= RESET_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many failed attempts. Please request a new verification code",
        )

    if record.get("used", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    if not verifier(email_norm, code, record["code_hash"]):
        new_attempts = attempts + 1
        await collection.update_one(
            {"email": email_norm},
            {
                "$set": {
                    "attempts": new_attempts,
                    "used": new_attempts >= RESET_MAX_ATTEMPTS,
                }
            },
        )
        detail = (
            "Too many failed attempts. Please request a new verification code"
            if new_attempts >= RESET_MAX_ATTEMPTS
            else "Invalid or expired verification code"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )


def _issue_dev_code(code: str) -> str | None:
    if not settings.smtp_host and settings.auth_dev_return_reset_code:
        return code
    return None


@app.post(
    "/api/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    db: AsyncDatabase = Depends(get_db),
) -> RegisterResponse:
    email_norm = payload.email.lower().strip()
    clean_name = payload.name.strip()
    now = datetime.now(timezone.utc)

    existing_user = await db.users.find_one({"email": email_norm})
    if existing_user and existing_user.get("email_verified", True):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    existing_verif = await db.email_verifications.find_one({"email": email_norm})
    send_count, window_started_at = _check_code_rate_limit(
        existing_verif,
        now,
        "Too many verification requests. Please wait 15 minutes before trying again.",
    )

    code = generate_reset_code()
    code_hash = hash_verification_code(email_norm, code)
    await send_registration_verification_email(
        email_norm,
        clean_name,
        code,
        settings.reset_code_expire_minutes,
    )

    password_hash = hash_password(payload.password)
    if existing_user:
        await db.users.update_one(
            {"_id": existing_user["_id"]},
            {
                "$set": {
                    "name": clean_name,
                    "password_hash": password_hash,
                    "updated_at": now,
                }
            },
        )
        user_id_str = str(existing_user["_id"])
    else:
        user_doc = {
            "name": clean_name,
            "email": email_norm,
            "password_hash": password_hash,
            "email_verified": False,
            "token_version": 0,
            "created_at": now,
        }
        try:
            res = await db.users.insert_one(user_doc)
        except DuplicateKeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from exc
        user_id_str = str(res.inserted_id)

    expires_at = now + timedelta(minutes=settings.reset_code_expire_minutes)
    await db.email_verifications.update_one(
        {"email": email_norm},
        {
            "$set": {
                "email": email_norm,
                "user_id": user_id_str,
                "code_hash": code_hash,
                "attempts": 0,
                "used": False,
                "send_count": send_count,
                "window_started_at": window_started_at,
                "created_at": now,
                "expires_at": expires_at,
            }
        },
        upsert=True,
    )

    return RegisterResponse(
        message="A 6-digit verification code has been sent to your email.",
        email=email_norm,
        verification_required=True,
        expires_in_minutes=settings.reset_code_expire_minutes,
        dev_verification_code=_issue_dev_code(code),
    )


@app.post("/api/auth/verify-email", response_model=TokenResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    db: AsyncDatabase = Depends(get_db),
) -> TokenResponse:
    email_norm = payload.email.lower().strip()
    now = datetime.now(timezone.utc)
    await _verify_code_or_raise(
        db.email_verifications,
        email_norm,
        payload.code,
        now,
        verify_verification_code,
    )

    user_doc = await db.users.find_one({"email": email_norm})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    await db.users.update_one(
        {"_id": user_doc["_id"]},
        {
            "$set": {
                "email_verified": True,
                "email_verified_at": now,
            }
        },
    )
    await db.email_verifications.delete_many({"email": email_norm})

    verified_user_doc = {**user_doc, "email_verified": True}
    token = create_access_token(
        str(user_doc["_id"]),
        email_norm,
        token_version=int(user_doc.get("token_version", 0)),
    )
    return TokenResponse(
        access_token=token,
        user=_serialize_user(verified_user_doc),
    )


@app.post("/api/auth/resend-verification", response_model=RegisterResponse)
async def resend_verification(
    payload: ResendVerificationRequest,
    db: AsyncDatabase = Depends(get_db),
) -> RegisterResponse:
    email_norm = payload.email.lower().strip()
    now = datetime.now(timezone.utc)

    user_doc = await db.users.find_one({"email": email_norm})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending registration found for this email",
        )
    if user_doc.get("email_verified", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified, please sign in",
        )

    existing_verif = await db.email_verifications.find_one({"email": email_norm})
    send_count, window_started_at = _check_code_rate_limit(
        existing_verif,
        now,
        "Too many verification requests. Please wait 15 minutes before trying again.",
    )

    code = generate_reset_code()
    code_hash = hash_verification_code(email_norm, code)
    await send_registration_verification_email(
        email_norm,
        user_doc.get("name", "User"),
        code,
        settings.reset_code_expire_minutes,
    )

    expires_at = now + timedelta(minutes=settings.reset_code_expire_minutes)
    await db.email_verifications.update_one(
        {"email": email_norm},
        {
            "$set": {
                "email": email_norm,
                "user_id": str(user_doc["_id"]),
                "code_hash": code_hash,
                "attempts": 0,
                "used": False,
                "send_count": send_count,
                "window_started_at": window_started_at,
                "created_at": now,
                "expires_at": expires_at,
            }
        },
        upsert=True,
    )

    return RegisterResponse(
        message="A new 6-digit verification code has been sent to your email.",
        email=email_norm,
        verification_required=True,
        expires_in_minutes=settings.reset_code_expire_minutes,
        dev_verification_code=_issue_dev_code(code),
    )


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncDatabase = Depends(get_db),
) -> TokenResponse:
    email_norm = payload.email.lower().strip()
    user_doc = await db.users.find_one({"email": email_norm})
    if not user_doc or not verify_password(payload.password, user_doc["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user_doc.get("email_verified", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address with the 6-digit code before signing in",
        )

    token = create_access_token(
        str(user_doc["_id"]),
        email_norm,
        token_version=int(user_doc.get("token_version", 0)),
    )
    return TokenResponse(access_token=token, user=_serialize_user(user_doc))


@app.post("/api/auth/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncDatabase = Depends(get_db),
) -> ForgotPasswordResponse:
    email_norm = payload.email.lower().strip()
    now = datetime.now(timezone.utc)
    existing_reset = await db.password_resets.find_one({"email": email_norm})
    send_count, window_started_at = _check_code_rate_limit(
        existing_reset,
        now,
        "Too many reset requests. Please wait 15 minutes before trying again.",
    )

    generic_msg = (
        "If an account exists for this email, a 6-digit verification code has been sent."
    )
    expires_at = now + timedelta(minutes=settings.reset_code_expire_minutes)

    user_doc = await db.users.find_one({"email": email_norm})
    if not user_doc:
        await db.password_resets.update_one(
            {"email": email_norm},
            {
                "$set": {
                    "email": email_norm,
                    "user_id": "",
                    "code_hash": "",
                    "attempts": 0,
                    "used": True,
                    "send_count": send_count,
                    "window_started_at": window_started_at,
                    "created_at": now,
                    "expires_at": expires_at,
                }
            },
            upsert=True,
        )
        return ForgotPasswordResponse(
            message=generic_msg,
            expires_in_minutes=settings.reset_code_expire_minutes,
        )

    code = generate_reset_code()
    code_hash = hash_reset_code(email_norm, code)

    await send_password_reset_email(
        email_norm,
        user_doc.get("name", "User"),
        code,
        settings.reset_code_expire_minutes,
    )

    await db.password_resets.update_one(
        {"email": email_norm},
        {
            "$set": {
                "email": email_norm,
                "user_id": str(user_doc["_id"]),
                "code_hash": code_hash,
                "attempts": 0,
                "used": False,
                "send_count": send_count,
                "window_started_at": window_started_at,
                "created_at": now,
                "expires_at": expires_at,
            }
        },
        upsert=True,
    )

    return ForgotPasswordResponse(
        message=generic_msg,
        expires_in_minutes=settings.reset_code_expire_minutes,
        dev_reset_code=_issue_dev_code(code),
    )


@app.post("/api/auth/reset-password", response_model=TokenResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncDatabase = Depends(get_db),
) -> TokenResponse:
    email_norm = payload.email.lower().strip()
    now = datetime.now(timezone.utc)
    await _verify_code_or_raise(
        db.password_resets,
        email_norm,
        payload.code,
        now,
        verify_reset_code,
    )

    user_doc = await db.users.find_one({"email": email_norm})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    new_ver = int(user_doc.get("token_version", 0)) + 1
    await db.users.update_one(
        {"_id": user_doc["_id"]},
        {
            "$set": {
                "password_hash": hash_password(payload.new_password),
                "token_version": new_ver,
                "email_verified": True,
                "password_updated_at": now,
            }
        },
    )
    await db.password_resets.delete_many({"email": email_norm})
    await db.email_verifications.delete_many({"email": email_norm})

    verified_user_doc = {**user_doc, "email_verified": True}
    token = create_access_token(
        str(user_doc["_id"]),
        email_norm,
        token_version=new_ver,
    )
    return TokenResponse(access_token=token, user=_serialize_user(verified_user_doc))


@app.post("/api/auth/change-password", response_model=TokenResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> TokenResponse:
    if not verify_password(payload.current_password, current_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if verify_password(payload.new_password, current_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )

    new_ver = int(current_user.get("token_version", 0)) + 1
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "password_hash": hash_password(payload.new_password),
                "token_version": new_ver,
                "password_updated_at": now,
            }
        },
    )
    await db.password_resets.delete_many({"email": current_user["email"]})

    token = create_access_token(
        str(current_user["_id"]),
        current_user["email"],
        token_version=new_ver,
    )
    return TokenResponse(access_token=token, user=_serialize_user(current_user))


@app.get("/api/auth/me", response_model=UserPublic)
async def me(current_user: dict = Depends(get_current_user)) -> UserPublic:
    return _serialize_user(current_user)


# ---------------------------------------------------------------------------
# Habit & Check-in Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/habits", response_model=list[HabitOut])
async def list_habits(
    include_archived: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> list[HabitOut]:
    query: dict = {"user_id": str(current_user["_id"])}
    if not include_archived:
        query["archived"] = False

    cursor = db.habits.find(query).sort("created_at", 1)
    habits = [doc async for doc in cursor]
    return [_serialize_habit(h) for h in habits]


@app.post(
    "/api/habits",
    response_model=HabitOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_habit(
    payload: HabitCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> HabitOut:
    weekdays = (
        [0, 1, 2, 3, 4, 5, 6]
        if payload.frequency_type in ("daily", "monthly")
        else payload.weekdays
    )
    doc = {
        "user_id": str(current_user["_id"]),
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "color": payload.color,
        "icon": payload.icon,
        "frequency_type": payload.frequency_type,
        "weekdays": weekdays,
        "monthly_mode": payload.monthly_mode,
        "monthly_day": payload.monthly_day,
        "monthly_week": payload.monthly_week,
        "monthly_weekday": payload.monthly_weekday,
        "target_per_day": payload.target_per_day,
        "target_slo": round(float(payload.target_slo), 1),
        "mode": payload.mode,
        "remind_time": payload.remind_time,
        "force_start_time": payload.force_start_time,
        "force_end_time": payload.force_end_time,
        "reminder_enabled": payload.reminder_enabled,
        "reminder_times": payload.reminder_times,
        "reminder_mode": payload.reminder_mode,
        "reminder_snooze_minutes": payload.reminder_snooze_minutes,
        "reminder_message": payload.reminder_message,
        "archived": False,
        "created_at": datetime.now(timezone.utc),
    }
    if payload.created_date is not None:
        doc["created_date"] = payload.created_date
    if payload.created_time is not None:
        doc["created_time"] = payload.created_time
    res = await db.habits.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _serialize_habit(doc)


@app.patch("/api/habits/{habit_id}", response_model=HabitOut)
async def update_habit(
    habit_id: str,
    payload: HabitUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> HabitOut:
    if not ObjectId.is_valid(habit_id):
        raise HTTPException(status_code=400, detail="Invalid habit ID")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "title" in updates:
        updates["title"] = updates["title"].strip()
    if "description" in updates:
        updates["description"] = updates["description"].strip()
    if "target_slo" in updates:
        updates["target_slo"] = round(float(updates["target_slo"]), 1)
    if updates.get("frequency_type") == "daily":
        updates["weekdays"] = [0, 1, 2, 3, 4, 5, 6]
    elif updates.get("frequency_type") == "monthly" and "weekdays" not in updates:
        updates["weekdays"] = [0, 1, 2, 3, 4, 5, 6]

    mode_or_reminder_touched = bool(
        {
            "mode",
            "remind_time",
            "force_start_time",
            "force_end_time",
            "reminder_enabled",
            "reminder_times",
        }
        & payload.model_fields_set
    )
    if not updates or mode_or_reminder_touched:
        existing = await db.habits.find_one(
            {"_id": ObjectId(habit_id), "user_id": str(current_user["_id"])}
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Habit not found")
        if not updates and not mode_or_reminder_touched:
            return _serialize_habit(existing)

        explicit_free_mode = (
            "mode" in payload.model_fields_set
            and payload.mode == "free"
            and payload.reminder_enabled is not True
        )
        explicit_disable_reminder = (
            payload.reminder_enabled is False
            and "mode" not in payload.model_fields_set
        )
        if explicit_free_mode or explicit_disable_reminder:
            updates["mode"] = "free"
            updates["remind_time"] = None
            updates["force_start_time"] = None
            updates["force_end_time"] = None
            updates["reminder_enabled"] = False
            updates["reminder_times"] = []
        else:
            existing_mode, existing_remind, existing_start, existing_end = (
                extract_habit_mode_fields(existing)
            )
            _, existing_times, _, _, _ = extract_reminder_fields(existing)

            if (
                payload.reminder_enabled is True
                and "reminder_times" not in payload.model_fields_set
                and "remind_time" not in payload.model_fields_set
                and not existing_times
                and not existing_remind
            ):
                raise HTTPException(
                    status_code=422,
                    detail="At least one reminder time (HH:MM) is required when reminders are enabled",
                )

            if (
                "reminder_times" in payload.model_fields_set
                and payload.reminder_times is not None
                and len(payload.reminder_times) == 0
                and existing.get("reminder_enabled", False)
            ):
                raise HTTPException(
                    status_code=422,
                    detail="At least one reminder time (HH:MM) is required when reminders are enabled",
                )

            merged_mode = (
                payload.mode
                if "mode" in payload.model_fields_set and payload.mode is not None
                else existing_mode
            )
            if merged_mode == "free" and (
                payload.reminder_enabled is True
                or bool(payload.reminder_times and len(payload.reminder_times) > 0)
            ):
                merged_mode = "reminder"

            if merged_mode == "free":
                updates["mode"] = "free"
                updates["remind_time"] = None
                updates["force_start_time"] = None
                updates["force_end_time"] = None
                updates["reminder_enabled"] = False
                updates["reminder_times"] = []
            else:
                merged_remind = (
                    payload.remind_time
                    if "remind_time" in payload.model_fields_set
                    else existing_remind
                )
                if merged_mode == "reminder" and "remind_time" not in payload.model_fields_set:
                    if "reminder_times" in payload.model_fields_set and payload.reminder_times:
                        merged_remind = payload.reminder_times[0]
                    elif merged_remind is None and existing_times:
                        merged_remind = existing_times[0]

                merged_start = (
                    payload.force_start_time
                    if "force_start_time" in payload.model_fields_set
                    else existing_start
                )
                merged_end = (
                    payload.force_end_time
                    if "force_end_time" in payload.model_fields_set
                    else existing_end
                )
                try:
                    norm_remind, norm_start, norm_end = validate_and_normalize_mode_times(
                        merged_mode, merged_remind, merged_start, merged_end
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc

                updates["mode"] = merged_mode
                updates["remind_time"] = norm_remind
                updates["force_start_time"] = norm_start
                updates["force_end_time"] = norm_end
                updates["reminder_enabled"] = True

                if (
                    "reminder_times" in payload.model_fields_set
                    and payload.reminder_times is not None
                ):
                    if merged_mode == "reminder":
                        merged_t = sorted(
                            set(payload.reminder_times)
                            | (
                                {norm_remind}
                                if "remind_time" in payload.model_fields_set
                                and norm_remind
                                else set()
                            )
                        )[:MAX_REMINDER_TIMES]
                        if not merged_t:
                            raise HTTPException(
                                status_code=422,
                                detail="At least one reminder time (HH:MM) is required when reminders are enabled",
                            )
                        updates["reminder_times"] = merged_t
                        updates["remind_time"] = merged_t[0]
                    else:
                        updates["reminder_times"] = sorted(
                            set(payload.reminder_times)
                            | ({norm_remind} if norm_remind else set())
                        )[:MAX_REMINDER_TIMES]
                else:
                    if merged_mode in ("strict", "window"):
                        updates["reminder_times"] = [norm_remind] if norm_remind else []
                    else:
                        if "remind_time" in payload.model_fields_set:
                            updates["reminder_times"] = [norm_remind] if norm_remind else []
                        else:
                            updates["reminder_times"] = (
                                existing_times
                                or ([norm_remind] if norm_remind else [])
                            )

    res = await db.habits.find_one_and_update(
        {"_id": ObjectId(habit_id), "user_id": str(current_user["_id"])},
        {"$set": updates},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Habit not found")
    return _serialize_habit(res)


@app.delete("/api/habits/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit(
    habit_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> None:
    if not ObjectId.is_valid(habit_id):
        raise HTTPException(status_code=400, detail="Invalid habit ID")

    user_id = str(current_user["_id"])
    res = await db.habits.delete_one({"_id": ObjectId(habit_id), "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Habit not found")
    await db.checkins.delete_many({"habit_id": habit_id, "user_id": user_id})


@app.get("/api/habits/today", response_model=list[HabitTodayOut])
async def list_habits_for_date(
    target_date: str | None = Query(default=None),
    client_today: str | None = Query(default=None),
    client_time: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> list[HabitTodayOut]:
    try:
        client_today_date, resolved_time = resolve_client_clock(
            client_today, client_time
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_today or client_time format",
        ) from exc

    parsed_date = _parse_iso_date(target_date) if target_date else client_today_date
    iso_date = parsed_date.isoformat()
    client_today_iso = client_today_date.isoformat()
    user_id = str(current_user["_id"])

    habits = [
        doc
        async for doc in db.habits.find({"user_id": user_id, "archived": False}).sort(
            "created_at", 1
        )
    ]
    if not habits:
        return []

    habit_ids = [str(h["_id"]) for h in habits]

    # Fetch check-ins on target_date + all on-time completed dates concurrently
    async def _fetch_day_checkins() -> dict[str, dict]:
        result: dict[str, dict] = {}
        async for chk in db.checkins.find(
            {"user_id": user_id, "habit_id": {"$in": habit_ids}, "date": iso_date}
        ):
            result[chk["habit_id"]] = chk
        return result

    async def _fetch_completed_by_habit() -> dict[str, set[str]]:
        result: dict[str, set[str]] = {hid: set() for hid in habit_ids}
        async for chk in db.checkins.find(
            {"user_id": user_id, "habit_id": {"$in": habit_ids}, "completed": True},
            {"_id": 0, "habit_id": 1, "date": 1, "is_late": 1},
        ):
            if chk.get("is_late", False):
                continue
            result[chk["habit_id"]].add(chk["date"])
        return result

    day_checkins, completed_by_habit = await asyncio.gather(
        _fetch_day_checkins(),
        _fetch_completed_by_habit(),
    )

    results: list[HabitTodayOut] = []
    for h in habits:
        hid = str(h["_id"])
        chk = day_checkins.get(hid)
        scheduled = is_scheduled_on(h, parsed_date)
        min_created = resolve_habit_created_date(h, client_today_date)
        can_edit = parsed_date <= client_today_date and (
            min_created is None or parsed_date >= min_created
        )
        ev = evaluate_habit_day_status(
            habit=h,
            checkin=chk,
            target_date_str=iso_date,
            client_today_str=client_today_iso,
            client_time=resolved_time,
            scheduled=scheduled,
            can_edit=can_edit,
        )
        today_violated = (
            scheduled
            and can_edit
            and iso_date <= client_today_iso
            and ev.day_status in ("violation", "late_makeup")
        )
        curr_streak, best_streak = compute_streaks(
            h,
            completed_by_habit[hid],
            parsed_date,
            today_violated=today_violated,
        )
        base = _serialize_habit(h)
        results.append(
            HabitTodayOut(
                **base.model_dump(),
                date=iso_date,
                scheduled_today=scheduled,
                count=chk["count"] if chk else 0,
                completed=chk["completed"] if chk else False,
                note=chk.get("note", "") if chk else "",
                current_streak=curr_streak,
                best_streak=best_streak,
                day_status=ev.day_status,
                violation_reason=ev.violation_reason,
                started_at_time=ev.started_at_time,
                started_on_time=ev.started_on_time,
                is_late=ev.is_late,
                can_start=ev.can_start,
                can_edit=can_edit,
            )
        )
    return results


@app.get("/api/habits/schedule", response_model=PeriodScheduleOut)
async def get_habits_schedule(
    period: Literal["week", "month"] = Query(default="week"),
    anchor_date: str | None = Query(default=None),
    today: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> PeriodScheduleOut:
    today_date = _parse_iso_date(today)
    parsed_anchor = _parse_iso_date(anchor_date) if anchor_date else today_date
    start_date, end_date = compute_period_bounds(period, parsed_anchor)
    user_id = str(current_user["_id"])

    habits = [
        doc
        async for doc in db.habits.find({"user_id": user_id, "archived": False}).sort(
            "created_at", 1
        )
    ]
    habit_ids = [str(h["_id"]) for h in habits]
    checkins_by_key: dict[tuple[str, str], dict] = {}
    if habit_ids:
        async for chk in db.checkins.find(
            {
                "user_id": user_id,
                "habit_id": {"$in": habit_ids},
                "date": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat(),
                },
            }
        ):
            checkins_by_key[(chk["habit_id"], chk["date"])] = chk

    return build_period_schedule(
        habits=habits,
        checkins_by_key=checkins_by_key,
        period=period,
        anchor_date=parsed_anchor,
        today_date=today_date,
    )


@app.get("/api/habits/reminders", response_model=RemindersOverviewOut)
async def get_habits_reminders(
    target_date: str | None = Query(default=None),
    now_time: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> RemindersOverviewOut:
    parsed_date = _parse_iso_date(target_date)
    normalized_now: str | None = None
    if now_time is not None and now_time.strip():
        try:
            normalized_now = normalize_reminder_time(now_time)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    user_id = str(current_user["_id"])
    habits = [
        doc
        async for doc in db.habits.find({"user_id": user_id, "archived": False}).sort(
            "created_at", 1
        )
    ]
    habit_ids = [str(h["_id"]) for h in habits if extract_reminder_fields(h)[0]]
    day_checkins: dict[str, dict] = {}
    if habit_ids:
        async for chk in db.checkins.find(
            {
                "user_id": user_id,
                "habit_id": {"$in": habit_ids},
                "date": parsed_date.isoformat(),
            }
        ):
            day_checkins[chk["habit_id"]] = chk

    return build_reminders_overview(
        habits=habits,
        day_checkins=day_checkins,
        target_date=parsed_date,
        now_time=normalized_now,
    )


@app.post("/api/habits/{habit_id}/checkin", response_model=HabitTodayOut)
async def checkin_habit(
    habit_id: str,
    payload: CheckinRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> HabitTodayOut:
    if not ObjectId.is_valid(habit_id):
        raise HTTPException(status_code=400, detail="Invalid habit ID")

    parsed_date = _parse_iso_date(payload.date)
    iso_date = parsed_date.isoformat()
    try:
        client_today_date, resolved_time = resolve_client_clock(
            payload.client_today, payload.client_time
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_today or client_time format",
        ) from exc
    client_today_iso = client_today_date.isoformat()
    if iso_date > client_today_iso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot check in for a future date",
        )

    user_id = str(current_user["_id"])

    habit = await db.habits.find_one({"_id": ObjectId(habit_id), "user_id": user_id})
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    min_created = resolve_habit_created_date(habit, client_today_date)
    if min_created is not None and parsed_date < min_created:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot edit check-in history before habit creation date "
                f"({min_created.isoformat()})"
            ),
        )

    mode, _, force_start_time, force_end_time = extract_habit_mode_fields(habit)
    scheduled = is_scheduled_on(habit, parsed_date)
    target = max(1, int(habit.get("target_per_day", 1)))
    existing = await db.checkins.find_one(
        {"habit_id": habit_id, "user_id": user_id, "date": iso_date}
    )
    prev_count = existing["count"] if existing else 0
    prev_completed = bool(existing.get("completed", False)) if existing else prev_count >= target
    prev_note = existing.get("note", "") if existing else ""
    prev_started_on_time = bool(existing.get("started_on_time", False)) if existing else False
    prev_started_at_time = existing.get("started_at_time") if existing else None
    prev_is_late = bool(existing.get("is_late", False)) if existing else False
    prev_violation_reason = existing.get("violation_reason") if existing else None

    note = payload.note if payload.note is not None else prev_note

    if payload.action == "start":
        if mode != "strict":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only Mode 1 (Strict Control) supports Start Execution.",
            )
        if prev_completed or prev_count >= target:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This habit is already completed for today.",
            )
        if iso_date != client_today_iso or (
            force_start_time is not None and resolved_time > force_start_time
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Past the Force Start Time; this habit is now in violation. Please use Overdue Make-up instead.",
            )
        new_count = prev_count
        completed = False
        started_on_time = True
        started_at_time = prev_started_at_time or resolved_time
        is_late = False
        violation_reason = None
    elif payload.action == "edit" or payload.status_override is not None:
        note = payload.note.strip() if payload.note is not None else prev_note
        if payload.status_override is not None:
            effective_status = payload.status_override
        else:
            candidate_count = payload.count if payload.count is not None else prev_count
            if candidate_count >= target:
                effective_status = (
                    "late_makeup" if (prev_completed and prev_is_late) else "on_time"
                )
            else:
                effective_status = "clear"

        if effective_status == "on_time":
            if payload.count is not None and payload.count < target:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Completed status requires count >= {target}",
                )
            new_count = payload.count if payload.count is not None else max(target, prev_count)
            completed = True
            is_late = False
            violation_reason = None
            started_on_time = True if mode == "strict" else prev_started_on_time
            started_at_time = prev_started_at_time or (
                force_start_time if mode == "strict" else None
            )
        elif effective_status == "late_makeup":
            if payload.count is not None and payload.count < target:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Overdue make-up status requires count >= {target}",
                )
            new_count = payload.count if payload.count is not None else max(target, prev_count)
            completed = True
            is_late = True
            violation_reason = prev_violation_reason or (
                "missed_start"
                if (mode == "strict" and not prev_started_on_time)
                else "missed_end"
            )
            started_on_time = (
                prev_started_on_time if violation_reason == "missed_end" else False
            )
            started_at_time = prev_started_at_time if started_on_time else None
        else:  # "clear"
            if payload.count is not None and payload.count >= target:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Count must be less than {target} when status is Not Completed",
                )
            new_count = payload.count if payload.count is not None else 0
            completed = False
            is_late = False
            violation_reason = None
            started_on_time = False
            started_at_time = None
    else:
        if payload.action == "increment":
            new_count = prev_count + 1
        elif payload.action == "decrement":
            new_count = max(0, prev_count - 1)
        elif payload.action == "toggle":
            new_count = 0 if prev_count >= target else target
        else:  # "set"
            new_count = payload.count if payload.count is not None else target

        if (
            mode == "strict"
            and scheduled
            and new_count > prev_count
            and not prev_started_on_time
            and iso_date == client_today_iso
            and force_start_time is not None
            and resolved_time <= force_start_time
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mode 1 (Strict Control) requires clicking Start Execution before completing check-in.",
            )

        completed = new_count >= target
        started_on_time = prev_started_on_time
        started_at_time = prev_started_at_time

        if prev_completed and completed:
            is_late = prev_is_late
            violation_reason = prev_violation_reason
        elif completed:
            if not scheduled or mode in ("free", "reminder"):
                is_late = False
                violation_reason = None
            elif mode == "window":
                if iso_date < client_today_iso or (
                    force_end_time is not None and resolved_time > force_end_time
                ):
                    is_late = True
                    violation_reason = "missed_end"
                else:
                    is_late = False
                    violation_reason = None
            else:  # mode == "strict"
                if not prev_started_on_time:
                    is_late = True
                    violation_reason = "missed_start"
                elif iso_date < client_today_iso or (
                    force_end_time is not None and resolved_time > force_end_time
                ):
                    is_late = True
                    violation_reason = "missed_end"
                else:
                    is_late = False
                    violation_reason = None
        else:
            is_late = False
            violation_reason = None

    if new_count == 0 and not note and not started_on_time:
        await db.checkins.delete_one(
            {"habit_id": habit_id, "user_id": user_id, "date": iso_date}
        )
    else:
        await db.checkins.update_one(
            {"habit_id": habit_id, "date": iso_date},
            {
                "$set": {
                    "user_id": user_id,
                    "habit_id": habit_id,
                    "date": iso_date,
                    "count": new_count,
                    "completed": completed,
                    "note": note,
                    "started_on_time": started_on_time,
                    "started_at_time": started_at_time,
                    "is_late": is_late,
                    "violation_reason": violation_reason,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    completed_dates: set[str] = set()
    async for chk in db.checkins.find(
        {"user_id": user_id, "habit_id": habit_id, "completed": True},
        {"_id": 0, "date": 1, "is_late": 1},
    ):
        if chk.get("is_late", False):
            continue
        completed_dates.add(chk["date"])

    chk_doc = {
        "count": new_count,
        "completed": completed,
        "note": note,
        "started_on_time": started_on_time,
        "started_at_time": started_at_time,
        "is_late": is_late,
        "violation_reason": violation_reason,
    }
    ev = evaluate_habit_day_status(
        habit=habit,
        checkin=chk_doc,
        target_date_str=iso_date,
        client_today_str=client_today_iso,
        client_time=resolved_time,
        scheduled=scheduled,
    )
    today_violated = (
        scheduled
        and iso_date <= client_today_iso
        and ev.day_status in ("violation", "late_makeup")
    )
    curr_streak, best_streak = compute_streaks(
        habit, completed_dates, parsed_date, today_violated=today_violated
    )
    base = _serialize_habit(habit)
    return HabitTodayOut(
        **base.model_dump(),
        date=iso_date,
        scheduled_today=scheduled,
        count=new_count,
        completed=completed,
        note=note,
        current_streak=curr_streak,
        best_streak=best_streak,
        day_status=ev.day_status,
        violation_reason=ev.violation_reason,
        started_at_time=ev.started_at_time,
        started_on_time=ev.started_on_time,
        is_late=ev.is_late,
        can_start=ev.can_start,
        can_edit=True,
    )


@app.get("/api/habits/{habit_id}/history", response_model=HabitHistoryOut)
async def get_habit_history(
    habit_id: str,
    month: str | None = Query(default=None),
    client_today: str | None = Query(default=None),
    client_time: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> HabitHistoryOut:
    if not ObjectId.is_valid(habit_id):
        raise HTTPException(status_code=400, detail="Invalid habit ID")

    try:
        client_today_date, resolved_time = resolve_client_clock(
            client_today, client_time
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_today or client_time format",
        ) from exc

    if month is not None and month.strip():
        match = re.fullmatch(r"(\d{4})-(\d{2})", month.strip())
        if not match:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid month format, expected YYYY-MM",
            )
        year = int(match.group(1))
        mon = int(match.group(2))
        if not (1 <= mon <= 12):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid month format, expected YYYY-MM",
            )
    else:
        year = client_today_date.year
        mon = client_today_date.month

    user_id = str(current_user["_id"])
    habit = await db.habits.find_one({"_id": ObjectId(habit_id), "user_id": user_id})
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    _, last_day = calendar.monthrange(year, mon)
    start_iso = date(year, mon, 1).isoformat()
    end_iso = date(year, mon, last_day).isoformat()
    client_today_iso = client_today_date.isoformat()

    async def _fetch_month_checkins() -> dict[str, dict]:
        result: dict[str, dict] = {}
        async for chk in db.checkins.find(
            {
                "user_id": user_id,
                "habit_id": habit_id,
                "date": {"$gte": start_iso, "$lte": end_iso},
            }
        ):
            result[chk["date"]] = chk
        return result

    async def _fetch_completed_dates() -> tuple[set[str], set[str]]:
        on_time: set[str] = set()
        late: set[str] = set()
        async for chk in db.checkins.find(
            {"user_id": user_id, "habit_id": habit_id, "completed": True},
            {"_id": 0, "date": 1, "is_late": 1},
        ):
            if chk.get("is_late", False):
                late.add(chk["date"])
            else:
                on_time.add(chk["date"])
        return on_time, late

    async def _fetch_today_checkin() -> dict | None:
        if start_iso <= client_today_iso <= end_iso:
            return None
        return await db.checkins.find_one(
            {"user_id": user_id, "habit_id": habit_id, "date": client_today_iso}
        )

    month_checkins, (completed_dates, late_dates), today_chk = await asyncio.gather(
        _fetch_month_checkins(),
        _fetch_completed_dates(),
        _fetch_today_checkin(),
    )
    if start_iso <= client_today_iso <= end_iso:
        today_chk = month_checkins.get(client_today_iso)

    return build_habit_history(
        habit=habit,
        habit_out=_serialize_habit(habit),
        month_checkins=month_checkins,
        completed_dates=completed_dates,
        late_dates=late_dates,
        year=year,
        month=mon,
        client_today_date=client_today_date,
        client_time=resolved_time,
        today_checkin=today_chk,
    )


# ---------------------------------------------------------------------------
# Analytics & Streak Summary
# ---------------------------------------------------------------------------
@app.get("/api/stats/summary", response_model=StatsSummaryOut)
async def get_stats_summary(
    today: str | None = Query(default=None),
    client_time: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> StatsSummaryOut:
    ref_date = _parse_iso_date(today)
    ref_iso = ref_date.isoformat()
    try:
        _, resolved_time = resolve_client_clock(
            None, client_time, fallback_today=ref_date
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_time format",
        ) from exc

    user_id = str(current_user["_id"])

    habits = [
        doc
        async for doc in db.habits.find({"user_id": user_id, "archived": False}).sort(
            "created_at", 1
        )
    ]
    habit_ids = [str(h["_id"]) for h in habits]
    completed_by_habit: dict[str, set[str]] = {hid: set() for hid in habit_ids}
    late_by_habit: dict[str, set[str]] = {hid: set() for hid in habit_ids}
    ref_day_checkins: dict[str, dict] = {}

    if habit_ids:
        async for chk in db.checkins.find(
            {"user_id": user_id, "habit_id": {"$in": habit_ids}, "completed": True},
            {"_id": 0, "habit_id": 1, "date": 1, "is_late": 1},
        ):
            hid = chk["habit_id"]
            if chk.get("is_late", False):
                late_by_habit[hid].add(chk["date"])
            else:
                completed_by_habit[hid].add(chk["date"])

        async for chk in db.checkins.find(
            {"user_id": user_id, "habit_id": {"$in": habit_ids}, "date": ref_iso}
        ):
            ref_day_checkins[chk["habit_id"]] = chk

    # 7-day bar chart activity
    last_7_days: list[DailyActivityPoint] = []
    for offset in range(6, -1, -1):
        d = ref_date - timedelta(days=offset)
        d_iso = d.isoformat()
        sched_cnt = 0
        comp_cnt = 0
        late_cnt = 0
        for h in habits:
            hid = str(h["_id"])
            if is_scheduled_on(h, d):
                sched_cnt += 1
                if d_iso in completed_by_habit[hid]:
                    comp_cnt += 1
                elif d_iso in late_by_habit[hid]:
                    late_cnt += 1
        last_7_days.append(
            DailyActivityPoint(
                date=d_iso,
                weekday_label=WEEKDAY_NAMES[d.weekday()],
                scheduled_count=sched_cnt,
                completed_count=comp_cnt,
                late_count=late_cnt,
            )
        )

    violated_today = 0
    late_today = 0
    violated_habit_ids: set[str] = set()
    for h in habits:
        hid = str(h["_id"])
        if not is_scheduled_on(h, ref_date):
            continue
        ev = evaluate_habit_day_status(
            habit=h,
            checkin=ref_day_checkins.get(hid),
            target_date_str=ref_iso,
            client_today_str=ref_iso,
            client_time=resolved_time,
            scheduled=True,
        )
        if ev.day_status == "violation":
            violated_today += 1
            violated_habit_ids.add(hid)
        elif ev.day_status == "late_makeup":
            late_today += 1
            violated_habit_ids.add(hid)

    habit_stats: list[HabitStreakStat] = []
    best_active_streak = 0
    rates: list[float] = []

    for h in habits:
        hid = str(h["_id"])
        c_dates = completed_by_habit[hid]
        l_dates = late_by_habit[hid]
        h_mode, _, _, _ = extract_habit_mode_fields(h)
        curr_s, best_s = compute_streaks(
            h, c_dates, ref_date, today_violated=(hid in violated_habit_ids)
        )
        rate_30d = compute_30d_completion_rate(h, c_dates, ref_date)
        if curr_s > best_active_streak:
            best_active_streak = curr_s
        rates.append(rate_30d)
        habit_stats.append(
            HabitStreakStat(
                habit_id=hid,
                title=h["title"],
                color=h.get("color", "#6366F1"),
                frequency_type=h.get("frequency_type", "daily"),
                mode=h_mode,
                current_streak=curr_s,
                best_streak=best_s,
                completion_rate_30d=rate_30d,
                total_completions=len(c_dates),
                late_completions=len(l_dates),
            )
        )

    habit_stats.sort(key=lambda s: (s.current_streak, s.best_streak), reverse=True)
    today_point = last_7_days[-1]
    overall_rate = round(sum(rates) / len(rates), 1) if rates else 0.0

    return StatsSummaryOut(
        active_habits_count=len(habits),
        completed_today=today_point.completed_count,
        scheduled_today=today_point.scheduled_count,
        late_today=late_today,
        violated_today=violated_today,
        best_active_streak=best_active_streak,
        overall_completion_rate_30d=overall_rate,
        last_7_days=last_7_days,
        habit_stats=habit_stats,
    )


@app.get("/api/stats/sli", response_model=SliDashboardOut)
async def get_sli_dashboard(
    window_days: int = Query(default=30, ge=7, le=365),
    today: str | None = Query(default=None),
    client_time: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> SliDashboardOut:
    ref_date = _parse_iso_date(today)
    ref_iso = ref_date.isoformat()
    try:
        _, resolved_time = resolve_client_clock(
            None, client_time, fallback_today=ref_date
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client_time format",
        ) from exc

    user_id = str(current_user["_id"])

    habits = [
        doc
        async for doc in db.habits.find({"user_id": user_id, "archived": False}).sort(
            "created_at", 1
        )
    ]
    habit_ids = [str(h["_id"]) for h in habits]
    completed_by_habit: dict[str, set[str]] = {hid: set() for hid in habit_ids}
    ref_day_checkins: dict[str, dict] = {}

    if habit_ids:
        async for chk in db.checkins.find(
            {"user_id": user_id, "habit_id": {"$in": habit_ids}, "completed": True},
            {"_id": 0, "habit_id": 1, "date": 1, "is_late": 1},
        ):
            if chk.get("is_late", False):
                continue
            completed_by_habit[chk["habit_id"]].add(chk["date"])

        async for chk in db.checkins.find(
            {"user_id": user_id, "habit_id": {"$in": habit_ids}, "date": ref_iso}
        ):
            ref_day_checkins[chk["habit_id"]] = chk

    violated_habit_ids: set[str] = set()
    for h in habits:
        hid = str(h["_id"])
        sli_start = habit_sli_start_date(
            h, completed_by_habit[hid], ref_date, fallback=ref_date
        )
        if ref_date < sli_start or not is_scheduled_on(h, ref_date):
            continue
        ev = evaluate_habit_day_status(
            habit=h,
            checkin=ref_day_checkins.get(hid),
            target_date_str=ref_iso,
            client_today_str=ref_iso,
            client_time=resolved_time,
            scheduled=True,
        )
        if ev.day_status in ("violation", "late_makeup"):
            violated_habit_ids.add(hid)

    return build_sli_dashboard(
        habits,
        completed_by_habit,
        ref_date,
        window_days=window_days,
        violated_habit_ids=violated_habit_ids,
    )
