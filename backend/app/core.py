import asyncio
import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
import ssl
from typing import Literal

from bson import ObjectId
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from pwdlib import PasswordHash
from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

load_dotenv()

logger = logging.getLogger("habit_tracker.auth")

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
RESET_MAX_ATTEMPTS = 5
RESET_RATE_WINDOW_MINUTES = 15
RESET_MAX_REQUESTS_PER_WINDOW = 5


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_db_name: str = os.getenv("MONGODB_DB_NAME", "habit_tracker")
    jwt_secret: str = os.getenv(
        "JWT_SECRET", "dev-secret-change-in-production-at-least-32-bytes"
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 days
    cors_origins_raw: str = os.getenv("CORS_ORIGINS", "*")
    smtp_host: str = os.getenv("SMTP_HOST", "").strip()
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password: str = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "").strip()
    smtp_use_tls: bool = (
        os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes", "on")
    )
    smtp_use_ssl: bool = (
        os.getenv("SMTP_USE_SSL", "false").strip().lower() in ("1", "true", "yes", "on")
    )
    reset_code_expire_minutes: int = int(os.getenv("RESET_CODE_EXPIRE_MINUTES", "15"))
    auth_dev_return_reset_code: bool = (
        os.getenv("AUTH_DEV_RETURN_RESET_CODE", "false").strip().lower()
        in ("1", "true", "yes", "on")
    )

    @property
    def cors_origins(self) -> list[str]:
        raw = self.cors_origins_raw.strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


settings = Settings()


# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------
async def ensure_indexes(db: AsyncDatabase) -> None:
    await db.users.create_index([("email", ASCENDING)], unique=True)
    await db.password_resets.create_index([("email", ASCENDING)], unique=True)
    await db.password_resets.create_index(
        [("expires_at", ASCENDING)], expireAfterSeconds=0
    )
    await db.email_verifications.create_index([("email", ASCENDING)], unique=True)
    await db.email_verifications.create_index(
        [("expires_at", ASCENDING)], expireAfterSeconds=0
    )
    await db.habits.create_index([("user_id", ASCENDING), ("archived", ASCENDING)])
    await db.checkins.create_index(
        [("habit_id", ASCENDING), ("date", ASCENDING)],
        unique=True,
    )
    await db.checkins.create_index([("user_id", ASCENDING), ("date", ASCENDING)])


def get_db(request: Request) -> AsyncDatabase:
    return request.app.state.mongodb


# ---------------------------------------------------------------------------
# Password Hashing & JWT Auth
# ---------------------------------------------------------------------------
password_hasher = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def create_access_token(user_id: str, email: str, token_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "ver": int(token_version),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def generate_reset_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _hmac_digest(msg_text: str) -> str:
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        msg_text.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def hash_reset_code(email: str, code: str) -> str:
    return _hmac_digest(f"{email.lower().strip()}:{code.strip()}")


def verify_reset_code(email: str, code: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_reset_code(email, code), expected_hash)


def hash_verification_code(email: str, code: str) -> str:
    """Hash a registration email verification code with domain separation."""
    return _hmac_digest(f"verify:{email.lower().strip()}:{code.strip()}")


def verify_verification_code(email: str, code: str, expected_hash: str) -> bool:
    """Verify a registration email verification code in constant time."""
    return hmac.compare_digest(hash_verification_code(email, code), expected_hash)


def _send_smtp_sync(msg: EmailMessage, cfg: Settings) -> None:
    context = ssl.create_default_context()
    if cfg.smtp_use_ssl or cfg.smtp_port == 465:
        with smtplib.SMTP_SSL(
            cfg.smtp_host, cfg.smtp_port, timeout=10, context=context
        ) as server:
            if cfg.smtp_username:
                server.login(cfg.smtp_username, cfg.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as server:
            server.ehlo()
            if cfg.smtp_use_tls:
                server.starttls(context=context)
                server.ehlo()
            if cfg.smtp_username:
                server.login(cfg.smtp_username, cfg.smtp_password)
            server.send_message(msg)


async def _send_code_email(
    *,
    to_email: str,
    dev_tag: str,
    subject: str,
    plain_body: str,
    html_body: str,
    code: str,
    expire_minutes: int,
    log_error_label: str,
    cfg: Settings | None = None,
) -> None:
    active_cfg = cfg or settings
    if not active_cfg.smtp_host:
        logger.warning(
            "[%s] SMTP_HOST not configured. Verification code for %s: %s (expires in %d min)",
            dev_tag,
            to_email,
            code,
            expire_minutes,
        )
        return

    from_addr = (
        active_cfg.smtp_from_email
        or active_cfg.smtp_username
        or "noreply@habittracker.local"
    )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        await asyncio.to_thread(_send_smtp_sync, msg, active_cfg)
    except Exception as exc:
        logger.exception("Failed to send %s to %s", log_error_label, to_email)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send verification email. Please try again later.",
        ) from exc


async def send_password_reset_email(
    to_email: str,
    user_name: str,
    code: str,
    expire_minutes: int,
    cfg: Settings | None = None,
) -> None:
    greeting = f"Hi {user_name}," if user_name else "Hi,"
    plain_body = (
        f"{greeting}\n\n"
        f"Your Habit Tracker password reset verification code is: {code}\n\n"
        f"This code expires in {expire_minutes} minutes. If you did not request a "
        "password reset, you can safely ignore this email.\n"
    )
    html_body = f"""\
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1E293B; line-height: 1.5;">
    <p>{greeting}</p>
    <p>Your Habit Tracker password reset verification code is:</p>
    <p style="font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #4F46E5; margin: 16px 0;">{code}</p>
    <p>This code expires in <strong>{expire_minutes} minutes</strong>. If you did not request a password reset, you can safely ignore this email.</p>
  </body>
</html>
"""
    await _send_code_email(
        to_email=to_email,
        dev_tag="DEV PASSWORD RESET",
        subject=f"Habit Tracker Password Reset Code: {code}",
        plain_body=plain_body,
        html_body=html_body,
        code=code,
        expire_minutes=expire_minutes,
        log_error_label="password reset email",
        cfg=cfg,
    )


async def send_registration_verification_email(
    to_email: str,
    user_name: str,
    code: str,
    expire_minutes: int,
    cfg: Settings | None = None,
) -> None:
    """Send a 6-digit registration verification email or log in local dev."""
    greeting = f"Hi {user_name}," if user_name else "Hi,"
    plain_body = (
        f"{greeting}\n\n"
        "Welcome to Habit Tracker! Please verify your email address with the 6-digit code below:\n\n"
        f"{code}\n\n"
        f"This code expires in {expire_minutes} minutes. If you did not sign up for "
        "Habit Tracker, you can safely ignore this email.\n"
    )
    html_body = f"""\
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1E293B; line-height: 1.5;">
    <p>{greeting}</p>
    <p>Welcome to Habit Tracker! Please verify your email address with the 6-digit code below:</p>
    <p style="font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #4F46E5; margin: 16px 0;">{code}</p>
    <p>This code expires in <strong>{expire_minutes} minutes</strong>. If you did not sign up for Habit Tracker, you can safely ignore this email.</p>
  </body>
</html>
"""
    await _send_code_email(
        to_email=to_email,
        dev_tag="DEV EMAIL VERIFICATION",
        subject=f"Habit Tracker Email Verification Code: {code}",
        plain_body=plain_body,
        html_body=html_body,
        code=code,
        expire_minutes=expire_minutes,
        log_error_label="registration verification email",
        cfg=cfg,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str | None = payload.get("sub")
        if not user_id or not ObjectId.is_valid(user_id):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please sign in again",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
        )
    if int(payload.get("ver", 0)) != int(user.get("token_version", 0)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please sign in again",
        )
    if not user.get("email_verified", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address is not verified",
        )
    return user


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    id: str
    name: str
    email: EmailStr
    email_verified: bool = True
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class RegisterResponse(BaseModel):
    message: str
    email: EmailStr
    verification_required: bool = True
    expires_in_minutes: int = 15
    dev_verification_code: str | None = None


def _strip_code_value(v: object) -> object:
    if isinstance(v, str):
        return v.strip()
    return v


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("code", mode="before")
    @classmethod
    def strip_code(cls, v: object) -> object:
        return _strip_code_value(v)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    expires_in_minutes: int = 15
    dev_reset_code: str | None = None


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=6, max_length=128)

    @field_validator("code", mode="before")
    @classmethod
    def strip_code(cls, v: object) -> object:
        return _strip_code_value(v)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


FrequencyType = Literal["daily", "weekdays", "monthly"]
MonthlyMode = Literal["from_start", "from_end", "nth_weekday"]
VALID_MONTHLY_WEEKS = {-1, 1, 2, 3, 4, 5}


class HabitCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)
    color: str = Field(default="#6366F1", max_length=20)
    icon: str = Field(default="check_circle", max_length=40)
    frequency_type: FrequencyType = "daily"
    weekdays: list[int] = Field(
        default_factory=lambda: [0, 1, 2, 3, 4, 5, 6],
        description="0=Monday .. 6=Sunday",
    )
    monthly_mode: MonthlyMode = "from_start"
    monthly_day: int = Field(
        default=1,
        ge=1,
        le=31,
        description="1..31 from start or end of month",
    )
    monthly_week: int = Field(
        default=1,
        description="1..5 or -1 for last occurrence in month",
    )
    monthly_weekday: int = Field(
        default=0,
        ge=0,
        le=6,
        description="0=Monday .. 6=Sunday",
    )
    target_per_day: int = Field(default=1, ge=1, le=100)
    target_slo: float = Field(default=85.0, ge=1.0, le=100.0)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, v: list[int]) -> list[int]:
        return sorted({d for d in v if 0 <= d <= 6})

    @field_validator("monthly_week")
    @classmethod
    def validate_monthly_week(cls, v: int) -> int:
        if v not in VALID_MONTHLY_WEEKS:
            raise ValueError("monthly_week must be 1..5 or -1 (last)")
        return v

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "HabitCreate":
        if self.frequency_type == "weekdays" and not self.weekdays:
            raise ValueError("At least one weekday (0..6) must be selected")
        if self.frequency_type in ("daily", "monthly") and not self.weekdays:
            self.weekdays = [0, 1, 2, 3, 4, 5, 6]
        return self


class HabitUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=300)
    color: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=40)
    frequency_type: FrequencyType | None = None
    weekdays: list[int] | None = None
    monthly_mode: MonthlyMode | None = None
    monthly_day: int | None = Field(default=None, ge=1, le=31)
    monthly_week: int | None = None
    monthly_weekday: int | None = Field(default=None, ge=0, le=6)
    target_per_day: int | None = Field(default=None, ge=1, le=100)
    target_slo: float | None = Field(default=None, ge=1.0, le=100.0)
    archived: bool | None = None

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        return sorted({d for d in v if 0 <= d <= 6})

    @field_validator("monthly_week")
    @classmethod
    def validate_monthly_week(cls, v: int | None) -> int | None:
        if v is not None and v not in VALID_MONTHLY_WEEKS:
            raise ValueError("monthly_week must be 1..5 or -1 (last)")
        return v

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "HabitUpdate":
        if self.weekdays is not None and len(self.weekdays) == 0:
            if self.frequency_type == "monthly":
                self.weekdays = [0, 1, 2, 3, 4, 5, 6]
            else:
                raise ValueError("At least one weekday (0..6) must be selected")
        return self


class HabitOut(BaseModel):
    id: str
    title: str
    description: str
    color: str
    icon: str
    frequency_type: FrequencyType
    weekdays: list[int]
    monthly_mode: MonthlyMode = "from_start"
    monthly_day: int = 1
    monthly_week: int = 1
    monthly_weekday: int = 0
    target_per_day: int
    target_slo: float = 85.0
    archived: bool
    created_at: datetime


class HabitTodayOut(HabitOut):
    date: str
    scheduled_today: bool
    count: int
    completed: bool
    note: str = ""
    current_streak: int
    best_streak: int


class CheckinRequest(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    action: Literal["increment", "decrement", "toggle", "set"] = "increment"
    count: int | None = Field(default=None, ge=0, le=1000)
    note: str | None = Field(default=None, max_length=300)


class DailyActivityPoint(BaseModel):
    date: str
    weekday_label: str
    scheduled_count: int
    completed_count: int


class HabitStreakStat(BaseModel):
    habit_id: str
    title: str
    color: str
    frequency_type: FrequencyType = "daily"
    current_streak: int
    best_streak: int
    completion_rate_30d: float
    total_completions: int


class StatsSummaryOut(BaseModel):
    active_habits_count: int
    completed_today: int
    scheduled_today: int
    best_active_streak: int
    overall_completion_rate_30d: float
    last_7_days: list[DailyActivityPoint]
    habit_stats: list[HabitStreakStat]


class ScheduleHabitItemOut(BaseModel):
    habit_id: str
    title: str
    description: str
    color: str
    icon: str
    frequency_type: FrequencyType = "daily"
    weekdays: list[int]
    monthly_mode: MonthlyMode = "from_start"
    monthly_day: int = 1
    monthly_week: int = 1
    monthly_weekday: int = 0
    target_per_day: int
    date: str
    count: int
    completed: bool
    note: str = ""
    status: Literal["today", "upcoming", "overdue", "completed"]


class ScheduleDayOut(BaseModel):
    date: str
    weekday: int
    weekday_label: str
    is_today: bool
    is_past: bool
    is_future: bool
    scheduled_count: int
    completed_count: int
    pending_count: int
    items: list[ScheduleHabitItemOut]


class HabitPeriodSummaryOut(BaseModel):
    habit_id: str
    title: str
    description: str
    color: str
    icon: str
    frequency_type: FrequencyType = "daily"
    weekdays: list[int]
    monthly_mode: MonthlyMode = "from_start"
    monthly_day: int = 1
    monthly_week: int = 1
    monthly_weekday: int = 0
    target_per_day: int
    scheduled_days: int
    completed_days: int
    remaining_days: int
    overdue_days: int
    next_due_date: str | None = None


class PeriodScheduleOut(BaseModel):
    period: Literal["week", "month"]
    start_date: str
    end_date: str
    today: str
    total_scheduled: int
    completed_count: int
    remaining_count: int
    overdue_count: int
    completion_rate: float
    habit_summaries: list[HabitPeriodSummaryOut]
    days: list[ScheduleDayOut]


class SliTrendPoint(BaseModel):
    label: str
    start_date: str
    end_date: str
    scheduled_count: int
    completed_count: int
    sli: float
    has_activity: bool


class WeekdaySliPoint(BaseModel):
    weekday: int
    label: str
    scheduled_count: int
    completed_count: int
    sli: float


class HabitSliItem(BaseModel):
    habit_id: str
    title: str
    color: str
    target_slo: float
    current_sli: float
    sli_7d: float
    sli_30d: float
    sli_90d: float
    sli_delta: float
    slo_met: bool
    status: Literal["healthy", "warning", "breached"]
    scheduled_days: int
    completed_days: int
    missed_days: int
    error_budget_allowed_days: float
    error_budget_used_days: int
    error_budget_remaining_days: float
    error_budget_remaining_pct: float
    burn_rate: float
    burn_rate_7d: float
    current_streak: int


class SliDashboardOut(BaseModel):
    window_days: int
    active_habits_count: int
    overall_sli: float
    overall_target_slo: float
    overall_status: Literal["healthy", "warning", "breached", "no_data"]
    healthy_count: int
    warning_count: int
    breached_count: int
    overall_error_budget_allowed_days: float
    overall_error_budget_used_days: int
    overall_error_budget_remaining_days: float
    overall_error_budget_remaining_pct: float
    overall_burn_rate: float
    overall_burn_rate_7d: float
    weakest_weekday: str | None = None
    weakest_weekday_sli: float | None = None
    top_burn_habit_title: str | None = None
    top_burn_rate: float | None = None
    trend: list[SliTrendPoint]
    weekday_sli: list[WeekdaySliPoint]
    habits: list[HabitSliItem]


# ---------------------------------------------------------------------------
# Streak & Completion Calculations
# ---------------------------------------------------------------------------
def scheduled_monthly_day(year: int, month: int, habit: dict) -> int:
    first_weekday, days_in_month = calendar.monthrange(year, month)
    mode = habit.get("monthly_mode", "from_start")

    if mode == "from_end":
        offset = max(1, min(31, int(habit.get("monthly_day", 1))))
        return max(1, days_in_month - offset + 1)

    if mode == "nth_weekday":
        target_weekday = int(habit.get("monthly_weekday", 0)) % 7
        nth_week = int(habit.get("monthly_week", 1))
        if nth_week == -1:
            last_weekday = (first_weekday + days_in_month - 1) % 7
            back = (last_weekday - target_weekday) % 7
            return days_in_month - back
        nth_week = max(1, min(5, nth_week))
        first_occ = 1 + ((target_weekday - first_weekday) % 7)
        day = first_occ + (nth_week - 1) * 7
        if day > days_in_month:
            day -= 7
        return day

    day = max(1, min(31, int(habit.get("monthly_day", 1))))
    return min(day, days_in_month)


def is_scheduled_on(habit: dict, target: date) -> bool:
    freq = habit.get("frequency_type", "daily")
    if freq == "daily":
        return True
    if freq == "monthly":
        return target.day == scheduled_monthly_day(target.year, target.month, habit)
    weekdays = habit.get("weekdays") or [0, 1, 2, 3, 4, 5, 6]
    return target.weekday() in weekdays


def compute_streaks(
    habit: dict,
    completed_dates: set[str],
    reference_date: date,
) -> tuple[int, int]:
    """
    Calculate (current_streak, best_streak) across scheduled days.
    Includes a same-day grace period so an uncompleted habit today keeps its streak
    from yesterday until the day passes.
    """
    if not completed_dates:
        return 0, 0

    parsed_dates = sorted(date.fromisoformat(d) for d in completed_dates)
    earliest = parsed_dates[0]
    latest = max(reference_date, parsed_dates[-1])

    best_streak = 0
    running = 0
    cursor = earliest
    while cursor <= latest:
        if is_scheduled_on(habit, cursor):
            if cursor.isoformat() in completed_dates:
                running += 1
                if running > best_streak:
                    best_streak = running
            else:
                running = 0
        cursor += timedelta(days=1)

    current_streak = 0
    cursor = reference_date
    if is_scheduled_on(habit, cursor) and cursor.isoformat() not in completed_dates:
        cursor -= timedelta(days=1)

    while cursor >= earliest:
        if is_scheduled_on(habit, cursor):
            if cursor.isoformat() in completed_dates:
                current_streak += 1
            else:
                break
        cursor -= timedelta(days=1)

    return current_streak, best_streak


def compute_30d_completion_rate(
    habit: dict,
    completed_dates: set[str],
    reference_date: date,
) -> float:
    created_at = habit.get("created_at")
    created_date = (
        created_at.date()
        if hasattr(created_at, "date")
        else reference_date - timedelta(days=29)
    )
    start_date = max(reference_date - timedelta(days=29), created_date)

    scheduled = 0
    completed = 0
    cursor = start_date
    while cursor <= reference_date:
        if is_scheduled_on(habit, cursor):
            scheduled += 1
            if cursor.isoformat() in completed_dates:
                completed += 1
        cursor += timedelta(days=1)

    if scheduled == 0 and habit.get("frequency_type") == "monthly":
        fallback_start = max(reference_date - timedelta(days=40), created_date)
        cursor = start_date - timedelta(days=1)
        while cursor >= fallback_start:
            if is_scheduled_on(habit, cursor):
                scheduled = 1
                if cursor.isoformat() in completed_dates:
                    completed = 1
                break
            cursor -= timedelta(days=1)

    if scheduled == 0:
        return 0.0
    return round((completed / scheduled) * 100.0, 1)


def compute_period_bounds(
    period: Literal["week", "month"],
    anchor: date,
) -> tuple[date, date]:
    """Return inclusive (start_date, end_date) for the week or month containing anchor."""
    if period == "week":
        start_date = anchor - timedelta(days=anchor.weekday())
        end_date = start_date + timedelta(days=6)
        return start_date, end_date
    start_date = anchor.replace(day=1)
    last_day = calendar.monthrange(anchor.year, anchor.month)[1]
    end_date = anchor.replace(day=last_day)
    return start_date, end_date


def build_period_schedule(
    habits: list[dict],
    checkins_by_key: dict[tuple[str, str], dict],
    period: Literal["week", "month"],
    anchor_date: date,
    today_date: date,
) -> PeriodScheduleOut:
    """Build weekly or monthly scheduled occurrences, statuses, and per-habit summaries."""
    start_date, end_date = compute_period_bounds(period, anchor_date)

    effective_created: dict[str, date] = {}
    habit_acc: dict[str, dict] = {}
    for h in habits:
        hid = str(h["_id"])
        raw_created = h.get("created_at")
        # Clamp UTC created_at against local today_date so evening creations count for today.
        effective_created[hid] = (
            min(raw_created.date(), today_date)
            if hasattr(raw_created, "date")
            else start_date
        )
        habit_acc[hid] = {
            "habit": h,
            "scheduled_days": 0,
            "completed_days": 0,
            "remaining_days": 0,
            "overdue_days": 0,
            "next_upcoming": None,
            "first_overdue": None,
        }

    days: list[ScheduleDayOut] = []
    total_scheduled = 0
    completed_count = 0
    remaining_count = 0
    overdue_count = 0

    cursor = start_date
    while cursor <= end_date:
        cursor_iso = cursor.isoformat()
        day_items: list[ScheduleHabitItemOut] = []
        day_completed = 0

        for h in habits:
            if not is_scheduled_on(h, cursor):
                continue

            hid = str(h["_id"])
            chk = checkins_by_key.get((hid, cursor_iso))
            if (
                cursor < today_date
                and cursor < effective_created[hid]
                and not (chk and chk.get("count", 0) > 0)
            ):
                continue

            count = chk["count"] if chk else 0
            completed = bool(chk["completed"]) if chk else False
            note = chk.get("note", "") if chk else ""

            if completed:
                item_status: Literal["today", "upcoming", "overdue", "completed"] = "completed"
            elif cursor == today_date:
                item_status = "today"
            elif cursor > today_date:
                item_status = "upcoming"
            else:
                item_status = "overdue"

            day_items.append(
                ScheduleHabitItemOut(
                    habit_id=hid,
                    title=h["title"],
                    description=h.get("description", ""),
                    color=h.get("color", "#6366F1"),
                    icon=h.get("icon", "check_circle"),
                    frequency_type=h.get("frequency_type", "daily"),
                    weekdays=h.get("weekdays", [0, 1, 2, 3, 4, 5, 6]),
                    monthly_mode=h.get("monthly_mode", "from_start"),
                    monthly_day=h.get("monthly_day", 1),
                    monthly_week=h.get("monthly_week", 1),
                    monthly_weekday=h.get("monthly_weekday", 0),
                    target_per_day=h.get("target_per_day", 1),
                    date=cursor_iso,
                    count=count,
                    completed=completed,
                    note=note,
                    status=item_status,
                )
            )

            acc = habit_acc[hid]
            total_scheduled += 1
            acc["scheduled_days"] += 1

            if completed:
                day_completed += 1
                completed_count += 1
                acc["completed_days"] += 1
            elif cursor >= today_date:
                remaining_count += 1
                acc["remaining_days"] += 1
                if acc["next_upcoming"] is None:
                    acc["next_upcoming"] = cursor_iso
            else:
                overdue_count += 1
                acc["overdue_days"] += 1
                if acc["first_overdue"] is None:
                    acc["first_overdue"] = cursor_iso

        scheduled_cnt = len(day_items)
        days.append(
            ScheduleDayOut(
                date=cursor_iso,
                weekday=cursor.weekday(),
                weekday_label=WEEKDAY_LABELS[cursor.weekday()],
                is_today=(cursor == today_date),
                is_past=(cursor < today_date),
                is_future=(cursor > today_date),
                scheduled_count=scheduled_cnt,
                completed_count=day_completed,
                pending_count=scheduled_cnt - day_completed,
                items=day_items,
            )
        )
        cursor += timedelta(days=1)

    habit_summaries: list[HabitPeriodSummaryOut] = []
    for acc in habit_acc.values():
        if acc["scheduled_days"] == 0:
            continue
        h = acc["habit"]
        next_due = acc["next_upcoming"] or acc["first_overdue"]
        habit_summaries.append(
            HabitPeriodSummaryOut(
                habit_id=str(h["_id"]),
                title=h["title"],
                description=h.get("description", ""),
                color=h.get("color", "#6366F1"),
                icon=h.get("icon", "check_circle"),
                frequency_type=h.get("frequency_type", "daily"),
                weekdays=h.get("weekdays", [0, 1, 2, 3, 4, 5, 6]),
                monthly_mode=h.get("monthly_mode", "from_start"),
                monthly_day=h.get("monthly_day", 1),
                monthly_week=h.get("monthly_week", 1),
                monthly_weekday=h.get("monthly_weekday", 0),
                target_per_day=h.get("target_per_day", 1),
                scheduled_days=acc["scheduled_days"],
                completed_days=acc["completed_days"],
                remaining_days=acc["remaining_days"],
                overdue_days=acc["overdue_days"],
                next_due_date=next_due,
            )
        )

    habit_summaries.sort(
        key=lambda s: (
            0 if (s.remaining_days > 0 or s.overdue_days > 0) else 1,
            s.next_due_date or "9999-99-99",
        )
    )
    completion_rate = (
        round((completed_count / total_scheduled) * 100.0, 1)
        if total_scheduled > 0
        else 0.0
    )

    return PeriodScheduleOut(
        period=period,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        today=today_date.isoformat(),
        total_scheduled=total_scheduled,
        completed_count=completed_count,
        remaining_count=remaining_count,
        overdue_count=overdue_count,
        completion_rate=completion_rate,
        habit_summaries=habit_summaries,
        days=days,
    )


# ---------------------------------------------------------------------------
# Personal SLI, Error Budget & Burn Rate Analytics
# ---------------------------------------------------------------------------
def _habit_created_date(habit: dict, fallback: date) -> date:
    created_at = habit.get("created_at")
    if isinstance(created_at, datetime):
        return created_at.date()
    if isinstance(created_at, date):
        return created_at
    return fallback


def compute_window_sli_counts(
    habit: dict,
    completed_dates: set[str],
    reference_date: date,
    window_days: int,
) -> tuple[int, int]:
    """Count (scheduled_days, completed_days) over the trailing window bounded by creation date."""
    window_start = reference_date - timedelta(days=window_days - 1)
    effective_start = max(window_start, _habit_created_date(habit, window_start))

    scheduled = 0
    completed = 0
    cursor = effective_start
    while cursor <= reference_date:
        if is_scheduled_on(habit, cursor):
            scheduled += 1
            if cursor.isoformat() in completed_dates:
                completed += 1
        cursor += timedelta(days=1)
    return scheduled, completed


def compute_error_budget(
    scheduled_days: int,
    missed_days: int,
    target_slo: float,
) -> tuple[float, float, float]:
    """Return (allowed_days, remaining_days, remaining_pct) for an SLO error budget."""
    if scheduled_days <= 0:
        return 0.0, 0.0, 100.0

    allowed_raw = scheduled_days * (1.0 - target_slo / 100.0)
    allowed_days = round(allowed_raw, 1)
    remaining_raw = allowed_raw - missed_days
    remaining_days = round(remaining_raw, 1)

    if allowed_raw <= 1e-9:
        remaining_pct = 100.0 if missed_days == 0 else 0.0
    else:
        remaining_pct = round(
            max(0.0, min(100.0, (remaining_raw / allowed_raw) * 100.0)),
            1,
        )
    return allowed_days, remaining_days, remaining_pct


def compute_burn_rate(
    scheduled_days: int,
    missed_days: int,
    target_slo: float,
) -> float:
    """Compute SRE error-budget burn rate (1.0x = consuming budget right on SLO pace)."""
    if scheduled_days <= 0 or missed_days <= 0:
        return 0.0

    budget_fraction = 1.0 - (target_slo / 100.0)
    if budget_fraction <= 1e-9:
        # Avoid infinite burn rate when target_slo is 100%; cap cleanly for UI display.
        return 10.0

    return round((missed_days / scheduled_days) / budget_fraction, 2)


def _sli_percentage(scheduled: int, completed: int) -> float:
    if scheduled <= 0:
        return 100.0
    return round((completed / scheduled) * 100.0, 1)


def compute_habit_sli(
    habit: dict,
    completed_dates: set[str],
    reference_date: date,
    window_days: int = 30,
) -> HabitSliItem:
    hid = str(habit.get("_id", habit.get("id", "")))
    target_slo = round(float(habit.get("target_slo", 85.0)), 1)

    sched_w, comp_w = compute_window_sli_counts(
        habit, completed_dates, reference_date, window_days
    )
    sched_7, comp_7 = compute_window_sli_counts(
        habit, completed_dates, reference_date, 7
    )
    sched_30, comp_30 = compute_window_sli_counts(
        habit, completed_dates, reference_date, 30
    )
    sched_90, comp_90 = compute_window_sli_counts(
        habit, completed_dates, reference_date, 90
    )

    current_sli = _sli_percentage(sched_w, comp_w)
    sli_7d = _sli_percentage(sched_7, comp_7)
    sli_30d = _sli_percentage(sched_30, comp_30)
    sli_90d = _sli_percentage(sched_90, comp_90)

    missed_w = sched_w - comp_w
    allowed_days, remaining_days, remaining_pct = compute_error_budget(
        sched_w, missed_w, target_slo
    )
    burn_rate = compute_burn_rate(sched_w, missed_w, target_slo)
    burn_rate_7d = compute_burn_rate(sched_7, sched_7 - comp_7, target_slo)

    slo_met = current_sli >= target_slo
    sli_delta = round(current_sli - target_slo, 1)
    if not slo_met:
        item_status: Literal["healthy", "warning", "breached"] = "breached"
    elif sched_w > 0 and (remaining_pct <= 25.0 or burn_rate_7d > 1.5):
        item_status = "warning"
    else:
        item_status = "healthy"

    curr_streak, _ = compute_streaks(habit, completed_dates, reference_date)

    return HabitSliItem(
        habit_id=hid,
        title=habit["title"],
        color=habit.get("color", "#6366F1"),
        target_slo=target_slo,
        current_sli=current_sli,
        sli_7d=sli_7d,
        sli_30d=sli_30d,
        sli_90d=sli_90d,
        sli_delta=sli_delta,
        slo_met=slo_met,
        status=item_status,
        scheduled_days=sched_w,
        completed_days=comp_w,
        missed_days=missed_w,
        error_budget_allowed_days=allowed_days,
        error_budget_used_days=missed_w,
        error_budget_remaining_days=remaining_days,
        error_budget_remaining_pct=remaining_pct,
        burn_rate=burn_rate,
        burn_rate_7d=burn_rate_7d,
        current_streak=curr_streak,
    )


def build_sli_dashboard(
    habits: list[dict],
    completed_by_habit: dict[str, set[str]],
    reference_date: date,
    window_days: int = 30,
) -> SliDashboardOut:
    habit_items: list[HabitSliItem] = []
    total_sched_7 = 0
    total_comp_7 = 0

    for h in habits:
        hid = str(h.get("_id", h.get("id", "")))
        c_dates = completed_by_habit.get(hid, set())
        habit_items.append(
            compute_habit_sli(h, c_dates, reference_date, window_days=window_days)
        )
        s7, c7 = compute_window_sli_counts(h, c_dates, reference_date, 7)
        total_sched_7 += s7
        total_comp_7 += c7

    status_rank = {"breached": 0, "warning": 1, "healthy": 2}
    habit_items.sort(
        key=lambda item: (
            status_rank[item.status],
            -item.burn_rate,
            item.error_budget_remaining_pct,
            item.title,
        )
    )

    all_dates = [
        reference_date - timedelta(days=offset)
        for offset in range(window_days - 1, -1, -1)
    ]
    window_start = all_dates[0]
    habit_meta = [
        (
            str(h.get("_id", h.get("id", ""))),
            h,
            _habit_created_date(h, window_start),
        )
        for h in habits
    ]

    def day_counts(target: date) -> tuple[int, int]:
        sched = 0
        comp = 0
        d_iso = target.isoformat()
        for hid, h, created_d in habit_meta:
            if target >= created_d and is_scheduled_on(h, target):
                sched += 1
                if d_iso in completed_by_habit.get(hid, set()):
                    comp += 1
        return sched, comp

    if window_days <= 14:
        buckets = [[d] for d in all_dates]
    else:
        n = len(all_dates)
        buckets = [
            all_dates[(i * n) // 10 : ((i + 1) * n) // 10]
            for i in range(10)
            if (i * n) // 10 < ((i + 1) * n) // 10
        ]

    trend: list[SliTrendPoint] = []
    for bucket in buckets:
        b_sched = 0
        b_comp = 0
        for d in bucket:
            s, c = day_counts(d)
            b_sched += s
            b_comp += c
        label = (
            WEEKDAY_LABELS[bucket[0].weekday()]
            if window_days <= 7
            else bucket[-1].strftime("%m/%d")
        )
        has_activity = b_sched > 0
        trend.append(
            SliTrendPoint(
                label=label,
                start_date=bucket[0].isoformat(),
                end_date=bucket[-1].isoformat(),
                scheduled_count=b_sched,
                completed_count=b_comp,
                sli=round((b_comp / b_sched) * 100.0, 1) if has_activity else 0.0,
                has_activity=has_activity,
            )
        )

    weekday_sched = [0] * 7
    weekday_comp = [0] * 7
    for d in all_dates:
        wd = d.weekday()
        s, c = day_counts(d)
        weekday_sched[wd] += s
        weekday_comp[wd] += c

    weekday_sli: list[WeekdaySliPoint] = [
        WeekdaySliPoint(
            weekday=wd,
            label=WEEKDAY_LABELS[wd],
            scheduled_count=weekday_sched[wd],
            completed_count=weekday_comp[wd],
            sli=(
                round((weekday_comp[wd] / weekday_sched[wd]) * 100.0, 1)
                if weekday_sched[wd] > 0
                else 0.0
            ),
        )
        for wd in range(7)
    ]

    weak_candidates = [
        pt for pt in weekday_sli if pt.scheduled_count > 0 and pt.sli < 100.0
    ]
    if weak_candidates:
        weakest = min(
            weak_candidates,
            key=lambda pt: (
                pt.sli,
                -(pt.scheduled_count - pt.completed_count),
                pt.weekday,
            ),
        )
        weakest_weekday: str | None = weakest.label
        weakest_weekday_sli: float | None = weakest.sli
    else:
        weakest_weekday = None
        weakest_weekday_sli = None

    burn_candidates = [item for item in habit_items if item.burn_rate > 0.0]
    if burn_candidates:
        top_burn = max(
            burn_candidates,
            key=lambda item: (item.burn_rate, -item.error_budget_remaining_pct),
        )
        top_burn_habit_title: str | None = top_burn.title
        top_burn_rate: float | None = top_burn.burn_rate
    else:
        top_burn_habit_title = None
        top_burn_rate = None

    if not habits:
        return SliDashboardOut(
            window_days=window_days,
            active_habits_count=0,
            overall_sli=0.0,
            overall_target_slo=85.0,
            overall_status="no_data",
            healthy_count=0,
            warning_count=0,
            breached_count=0,
            overall_error_budget_allowed_days=0.0,
            overall_error_budget_used_days=0,
            overall_error_budget_remaining_days=0.0,
            overall_error_budget_remaining_pct=100.0,
            overall_burn_rate=0.0,
            overall_burn_rate_7d=0.0,
            weakest_weekday=None,
            weakest_weekday_sli=None,
            top_burn_habit_title=None,
            top_burn_rate=None,
            trend=trend,
            weekday_sli=weekday_sli,
            habits=[],
        )

    total_sched = sum(item.scheduled_days for item in habit_items)
    total_comp = sum(item.completed_days for item in habit_items)
    total_missed = total_sched - total_comp

    overall_sli = _sli_percentage(total_sched, total_comp)
    if total_sched > 0:
        overall_target_slo = round(
            sum(item.target_slo * item.scheduled_days for item in habit_items)
            / total_sched,
            1,
        )
    else:
        overall_target_slo = round(
            sum(item.target_slo for item in habit_items) / len(habit_items),
            1,
        )

    overall_allowed, overall_rem_days, overall_rem_pct = compute_error_budget(
        total_sched, total_missed, overall_target_slo
    )
    overall_burn_rate = compute_burn_rate(
        total_sched, total_missed, overall_target_slo
    )
    overall_burn_rate_7d = compute_burn_rate(
        total_sched_7, total_sched_7 - total_comp_7, overall_target_slo
    )

    healthy_count = sum(1 for item in habit_items if item.status == "healthy")
    warning_count = sum(1 for item in habit_items if item.status == "warning")
    breached_count = sum(1 for item in habit_items if item.status == "breached")

    if overall_sli < overall_target_slo or breached_count > 0:
        overall_status: Literal["healthy", "warning", "breached", "no_data"] = "breached"
    elif warning_count > 0 or (
        total_sched > 0 and (overall_rem_pct <= 25.0 or overall_burn_rate_7d > 1.5)
    ):
        overall_status = "warning"
    else:
        overall_status = "healthy"

    return SliDashboardOut(
        window_days=window_days,
        active_habits_count=len(habits),
        overall_sli=overall_sli,
        overall_target_slo=overall_target_slo,
        overall_status=overall_status,
        healthy_count=healthy_count,
        warning_count=warning_count,
        breached_count=breached_count,
        overall_error_budget_allowed_days=overall_allowed,
        overall_error_budget_used_days=total_missed,
        overall_error_budget_remaining_days=overall_rem_days,
        overall_error_budget_remaining_pct=overall_rem_pct,
        overall_burn_rate=overall_burn_rate,
        overall_burn_rate_7d=overall_burn_rate_7d,
        weakest_weekday=weakest_weekday,
        weakest_weekday_sli=weakest_weekday_sli,
        top_burn_habit_title=top_burn_habit_title,
        top_burn_rate=top_burn_rate,
        trend=trend,
        weekday_sli=weekday_sli,
        habits=habit_items,
    )
