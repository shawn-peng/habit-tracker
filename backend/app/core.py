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
    await db.checkins.create_index(
        [
            ("user_id", ASCENDING),
            ("completed", ASCENDING),
            ("habit_id", ASCENDING),
            ("date", ASCENDING),
        ]
    )


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
ReminderMode = Literal["notification", "alarm"]
VALID_MONTHLY_WEEKS = {-1, 1, 2, 3, 4, 5}
MAX_REMINDER_TIMES = 12
_REMINDER_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?:\s*([AaPp][Mm]))?$")


def normalize_reminder_time(raw: str) -> str:
    """Validate and normalize a 24-hour (HH:MM) or 12-hour (H:MM AM/PM) time string to HH:MM."""
    cleaned = raw.strip()
    match = _REMINDER_TIME_RE.match(cleaned)
    if not match:
        raise ValueError(
            f"Invalid time '{raw}', expected HH:MM (00:00..23:59) or H:MM AM/PM"
        )
    hour = int(match.group(1))
    minute = int(match.group(2))
    meridiem = match.group(3).upper() if match.group(3) else None
    if not (0 <= minute <= 59):
        raise ValueError(
            f"Invalid time '{raw}', minute must be between 00 and 59"
        )
    if meridiem is not None:
        if not (1 <= hour <= 12):
            raise ValueError(
                f"Invalid 12-hour time '{raw}', hour must be 1..12 before {meridiem}"
            )
        if meridiem == "AM":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    elif not (0 <= hour <= 23):
        raise ValueError(
            f"Invalid time '{raw}', expected HH:MM (00:00..23:59) or H:MM AM/PM"
        )
    return f"{hour:02d}:{minute:02d}"


def normalize_reminder_times(times: list[str]) -> list[str]:
    """Normalize, deduplicate, and sort up to MAX_REMINDER_TIMES HH:MM strings."""
    normalized = sorted({normalize_reminder_time(item) for item in times})
    if len(normalized) > MAX_REMINDER_TIMES:
        raise ValueError(
            f"At most {MAX_REMINDER_TIMES} reminder times are allowed per habit"
        )
    return normalized


HabitMode = Literal["free", "strict", "window", "reminder"]
HabitDayStatus = Literal[
    "pending", "reminding", "in_progress", "on_time", "violation", "late_makeup"
]
HistoryEditStatus = Literal["on_time", "late_makeup", "clear"]
HistoryDayState = Literal[
    "on_time",
    "late_makeup",
    "missed",
    "violation",
    "in_progress",
    "reminding",
    "pending",
    "unscheduled",
    "before_created",
    "future",
]
ViolationReason = Literal["missed_start", "missed_end"]
VALID_HABIT_MODES = ("free", "strict", "window", "reminder")


def _parse_optional_iso_date(raw: object) -> date | None:
    if isinstance(raw, str) and raw.strip():
        try:
            return date.fromisoformat(raw.strip())
        except ValueError:
            return None
    return None


def resolve_habit_created_date(
    habit: dict,
    client_today_date: date | None = None,
) -> date | None:
    """Resolve a habit's creation date in client local time, respecting synthetic test dates."""
    explicit_created = _parse_optional_iso_date(habit.get("created_date"))
    if explicit_created is not None:
        return (
            min(explicit_created, client_today_date)
            if client_today_date is not None
            else explicit_created
        )

    created_at = habit.get("created_at")
    if isinstance(created_at, datetime):
        raw_date = created_at.date()
    elif isinstance(created_at, date):
        raw_date = created_at
    else:
        return None

    if client_today_date is not None:
        # Preserve synthetic tests that create habits at wall-clock now() and pass past client_today.
        if raw_date > client_today_date + timedelta(days=1):
            return None
        return min(raw_date, client_today_date)
    return raw_date


def format_habit_created_date(
    habit: dict,
    fallback_today: date | None = None,
) -> str:
    """Return YYYY-MM-DD creation date string for HabitOut serialization."""
    explicit_created = _parse_optional_iso_date(habit.get("created_date"))
    if explicit_created is not None:
        if (
            fallback_today is not None
            and explicit_created == fallback_today + timedelta(days=1)
        ):
            return fallback_today.isoformat()
        return explicit_created.isoformat()

    created_at = habit.get("created_at")
    if isinstance(created_at, datetime):
        raw_date = created_at.date()
    elif isinstance(created_at, date):
        raw_date = created_at
    else:
        return ""

    if fallback_today is not None and raw_date == fallback_today + timedelta(days=1):
        return fallback_today.isoformat()
    return raw_date.isoformat()


def format_habit_created_time(habit: dict) -> str | None:
    """Return normalized HH:MM creation time string for HabitOut serialization."""
    raw = habit.get("created_time")
    if isinstance(raw, str) and raw.strip():
        try:
            return normalize_hhmm(raw)
        except ValueError:
            return None
    return None


def normalize_hhmm(value: str | None) -> str | None:
    """Validate and normalize an optional 24-hour HH:MM string."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return normalize_reminder_time(stripped)


def validate_and_normalize_mode_times(
    mode: HabitMode,
    remind_time: str | None,
    force_start_time: str | None,
    force_end_time: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Validate mode-specific time fields and return normalized (remind, start, end)."""
    remind = normalize_hhmm(remind_time)
    start = normalize_hhmm(force_start_time)
    end = normalize_hhmm(force_end_time)

    if mode == "free":
        return (None, None, None)
    if mode == "reminder":
        if not remind:
            raise ValueError("Mode 'reminder' requires remind_time")
        return (remind, None, None)
    if mode == "window":
        if not remind or not end:
            raise ValueError("Mode 'window' requires remind_time and force_end_time")
        if remind >= end:
            raise ValueError("remind_time must be earlier than force_end_time")
        return (remind, None, end)
    if mode == "strict":
        if not remind or not start or not end:
            raise ValueError(
                "Mode 'strict' requires remind_time, force_start_time, and force_end_time"
            )
        if not (remind < start < end):
            raise ValueError(
                "Mode 'strict' requires remind_time < force_start_time < force_end_time"
            )
        return (remind, start, end)
    raise ValueError(f"Unsupported habit mode: {mode}")


def extract_habit_mode_fields(
    habit: dict,
) -> tuple[HabitMode, str | None, str | None, str | None]:
    """Safely extract (mode, remind_time, force_start_time, force_end_time) with legacy fallbacks."""
    def _safe_hhmm(raw: object) -> str | None:
        if not isinstance(raw, str):
            return None
        try:
            return normalize_hhmm(raw)
        except ValueError:
            return None

    raw_mode = habit.get("mode", "free")
    mode: HabitMode = raw_mode if raw_mode in VALID_HABIT_MODES else "free"
    if mode == "free":
        if habit.get("reminder_enabled", False):
            raw_times = habit.get("reminder_times") or []
            clean_times = (
                sorted(
                    {
                        t
                        for item in raw_times
                        if (t := _safe_hhmm(item)) is not None
                    }
                )
                if isinstance(raw_times, list)
                else []
            )
            if clean_times:
                return ("reminder", clean_times[0], None, None)
        return ("free", None, None, None)

    remind = _safe_hhmm(habit.get("remind_time"))
    if mode == "reminder" and remind is None:
        raw_times = habit.get("reminder_times") or []
        if isinstance(raw_times, list):
            clean_times = sorted(
                {t for item in raw_times if (t := _safe_hhmm(item)) is not None}
            )
            if clean_times:
                remind = clean_times[0]
    start = _safe_hhmm(habit.get("force_start_time")) if mode == "strict" else None
    end = (
        _safe_hhmm(habit.get("force_end_time"))
        if mode in ("strict", "window")
        else None
    )
    return (mode, remind, start, end)


def resolve_client_clock(
    client_today: str | None,
    client_time: str | None,
    fallback_today: date | None = None,
) -> tuple[date, str]:
    """Resolve client local date and 24-hour HH:MM time with local clock defaults."""
    now_local = datetime.now()
    if client_today is not None and client_today.strip():
        resolved_date = date.fromisoformat(client_today.strip())
    else:
        resolved_date = fallback_today or now_local.date()

    if client_time is not None and client_time.strip():
        resolved_time = normalize_hhmm(client_time)
        assert resolved_time is not None
    else:
        resolved_time = now_local.strftime("%H:%M")
    return resolved_date, resolved_time


@dataclass(frozen=True)
class HabitDayEvaluation:
    day_status: HabitDayStatus
    violation_reason: ViolationReason | None
    started_at_time: str | None
    started_on_time: bool
    is_late: bool
    can_start: bool


def evaluate_habit_day_status(
    habit: dict,
    checkin: dict | None,
    target_date_str: str,
    client_today_str: str,
    client_time: str,
    scheduled: bool | None = None,
    can_edit: bool = True,
) -> HabitDayEvaluation:
    """Evaluate the mode-aware daily lifecycle status for a habit check-in."""
    mode, remind_time, force_start_time, force_end_time = extract_habit_mode_fields(
        habit
    )
    target = max(1, int(habit.get("target_per_day", 1)))

    chk = checkin or {}
    count = int(chk.get("count", 0))
    completed = bool(chk.get("completed", False)) or count >= target
    started_on_time = bool(chk.get("started_on_time", False))
    started_at_time = chk.get("started_at_time")
    stored_is_late = bool(chk.get("is_late", False))
    raw_violation = chk.get("violation_reason")
    stored_violation: ViolationReason | None = (
        raw_violation if raw_violation in ("missed_start", "missed_end") else None
    )

    if scheduled is None:
        scheduled = is_scheduled_on(habit, date.fromisoformat(target_date_str))

    if completed:
        if stored_is_late:
            return HabitDayEvaluation(
                day_status="late_makeup",
                violation_reason=stored_violation,
                started_at_time=started_at_time,
                started_on_time=started_on_time,
                is_late=True,
                can_start=False,
            )
        return HabitDayEvaluation(
            day_status="on_time",
            violation_reason=None,
            started_at_time=started_at_time,
            started_on_time=started_on_time,
            is_late=False,
            can_start=False,
        )

    if not can_edit:
        return HabitDayEvaluation(
            day_status="pending",
            violation_reason=None,
            started_at_time=started_at_time,
            started_on_time=False,
            is_late=False,
            can_start=False,
        )

    if not scheduled or target_date_str > client_today_str:
        return HabitDayEvaluation(
            day_status=(
                "in_progress" if (mode == "strict" and started_on_time) else "pending"
            ),
            violation_reason=None,
            started_at_time=started_at_time,
            started_on_time=started_on_time,
            is_late=False,
            can_start=False,
        )

    is_past_day = target_date_str < client_today_str

    if mode == "free":
        return HabitDayEvaluation(
            day_status="pending",
            violation_reason=None,
            started_at_time=started_at_time,
            started_on_time=started_on_time,
            is_late=False,
            can_start=False,
        )

    if mode == "reminder":
        day_status: HabitDayStatus = (
            "reminding"
            if (not is_past_day and remind_time and client_time >= remind_time)
            else "pending"
        )
        return HabitDayEvaluation(
            day_status=day_status,
            violation_reason=None,
            started_at_time=started_at_time,
            started_on_time=started_on_time,
            is_late=False,
            can_start=False,
        )

    if mode == "window":
        if is_past_day or (force_end_time and client_time > force_end_time):
            return HabitDayEvaluation(
                day_status="violation",
                violation_reason="missed_end",
                started_at_time=started_at_time,
                started_on_time=started_on_time,
                is_late=False,
                can_start=False,
            )
        day_status = (
            "reminding" if (remind_time and client_time >= remind_time) else "pending"
        )
        return HabitDayEvaluation(
            day_status=day_status,
            violation_reason=None,
            started_at_time=started_at_time,
            started_on_time=started_on_time,
            is_late=False,
            can_start=False,
        )

    # mode == "strict"
    if not started_on_time:
        if is_past_day or (force_start_time and client_time > force_start_time):
            return HabitDayEvaluation(
                day_status="violation",
                violation_reason="missed_start",
                started_at_time=started_at_time,
                started_on_time=False,
                is_late=False,
                can_start=False,
            )
        day_status = (
            "reminding" if (remind_time and client_time >= remind_time) else "pending"
        )
        return HabitDayEvaluation(
            day_status=day_status,
            violation_reason=None,
            started_at_time=started_at_time,
            started_on_time=False,
            is_late=False,
            can_start=True,
        )

    if is_past_day or (force_end_time and client_time > force_end_time):
        return HabitDayEvaluation(
            day_status="violation",
            violation_reason="missed_end",
            started_at_time=started_at_time,
            started_on_time=True,
            is_late=False,
            can_start=False,
        )

    return HabitDayEvaluation(
        day_status="in_progress",
        violation_reason=None,
        started_at_time=started_at_time,
        started_on_time=True,
        is_late=False,
        can_start=False,
    )


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
    mode: HabitMode = "free"
    remind_time: str | None = None
    force_start_time: str | None = None
    force_end_time: str | None = None
    reminder_enabled: bool = False
    reminder_times: list[str] = Field(
        default_factory=list,
        description="Sorted 24-hour HH:MM strings",
    )
    reminder_mode: ReminderMode = "notification"
    reminder_snooze_minutes: int = Field(default=10, ge=1, le=120)
    reminder_message: str = Field(default="", max_length=200)
    created_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    created_time: str | None = None

    @field_validator("created_date")
    @classmethod
    def validate_created_date(cls, v: str | None) -> str | None:
        if v is None:
            return None
        date.fromisoformat(v)
        return v

    @field_validator("created_time")
    @classmethod
    def validate_created_time(cls, v: str | None) -> str | None:
        return normalize_hhmm(v)

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

    @field_validator("reminder_times")
    @classmethod
    def validate_reminder_times(cls, v: list[str]) -> list[str]:
        return normalize_reminder_times(v)

    @field_validator("reminder_message")
    @classmethod
    def strip_reminder_message(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "HabitCreate":
        if self.frequency_type == "weekdays" and not self.weekdays:
            raise ValueError("At least one weekday (0..6) must be selected")
        if self.frequency_type in ("daily", "monthly") and not self.weekdays:
            self.weekdays = [0, 1, 2, 3, 4, 5, 6]

        if self.mode == "free":
            if self.reminder_enabled:
                if not self.reminder_times:
                    raise ValueError(
                        "At least one reminder time (HH:MM) is required when reminders are enabled"
                    )
                self.mode = "reminder"
                self.remind_time = self.reminder_times[0]
                self.force_start_time = None
                self.force_end_time = None
            else:
                self.remind_time = None
                self.force_start_time = None
                self.force_end_time = None
                self.reminder_enabled = False
                self.reminder_times = []
        else:
            if self.mode == "reminder" and not self.remind_time and self.reminder_times:
                self.remind_time = self.reminder_times[0]
            (
                self.remind_time,
                self.force_start_time,
                self.force_end_time,
            ) = validate_and_normalize_mode_times(
                self.mode,
                self.remind_time,
                self.force_start_time,
                self.force_end_time,
            )
            self.reminder_enabled = True
            if self.mode == "reminder":
                merged = set(self.reminder_times)
                if self.remind_time:
                    merged.add(self.remind_time)
                self.reminder_times = sorted(merged)[:MAX_REMINDER_TIMES]
                self.remind_time = self.reminder_times[0]
            else:
                if "reminder_times" not in self.model_fields_set or not self.reminder_times:
                    self.reminder_times = [self.remind_time] if self.remind_time else []
                elif self.remind_time:
                    self.reminder_times = sorted(
                        set(self.reminder_times) | {self.remind_time}
                    )[:MAX_REMINDER_TIMES]
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
    mode: HabitMode | None = None
    remind_time: str | None = None
    force_start_time: str | None = None
    force_end_time: str | None = None
    archived: bool | None = None
    reminder_enabled: bool | None = None
    reminder_times: list[str] | None = None
    reminder_mode: ReminderMode | None = None
    reminder_snooze_minutes: int | None = Field(default=None, ge=1, le=120)
    reminder_message: str | None = Field(default=None, max_length=200)

    @field_validator("remind_time", "force_start_time", "force_end_time")
    @classmethod
    def validate_optional_mode_time(cls, v: str | None) -> str | None:
        return normalize_hhmm(v)

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

    @field_validator("reminder_times")
    @classmethod
    def validate_reminder_times(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return normalize_reminder_times(v)

    @field_validator("reminder_message")
    @classmethod
    def strip_reminder_message(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip()

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "HabitUpdate":
        if self.weekdays is not None and len(self.weekdays) == 0:
            if self.frequency_type == "monthly":
                self.weekdays = [0, 1, 2, 3, 4, 5, 6]
            else:
                raise ValueError("At least one weekday (0..6) must be selected")
        if (
            self.reminder_enabled is True
            and self.reminder_times is not None
            and len(self.reminder_times) == 0
        ):
            raise ValueError(
                "At least one reminder time (HH:MM) is required when reminders are enabled"
            )
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
    mode: HabitMode = "free"
    remind_time: str | None = None
    force_start_time: str | None = None
    force_end_time: str | None = None
    reminder_enabled: bool = False
    reminder_times: list[str] = Field(default_factory=list)
    reminder_mode: ReminderMode = "notification"
    reminder_snooze_minutes: int = 10
    reminder_message: str = ""
    archived: bool
    created_date: str = ""
    created_time: str | None = None
    created_at: datetime


class HabitTodayOut(HabitOut):
    date: str
    scheduled_today: bool
    count: int
    completed: bool
    note: str = ""
    current_streak: int
    best_streak: int
    day_status: HabitDayStatus = "pending"
    violation_reason: ViolationReason | None = None
    started_at_time: str | None = None
    started_on_time: bool = False
    is_late: bool = False
    can_start: bool = False
    can_edit: bool = True


class CheckinRequest(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    action: Literal["increment", "decrement", "toggle", "set", "start", "edit"] = "increment"
    count: int | None = Field(default=None, ge=0, le=1000)
    note: str | None = Field(default=None, max_length=300)
    status_override: HistoryEditStatus | None = None
    client_today: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    client_time: str | None = None

    @field_validator("client_time")
    @classmethod
    def validate_client_time(cls, v: str | None) -> str | None:
        return normalize_hhmm(v)


class DailyActivityPoint(BaseModel):
    date: str
    weekday_label: str
    scheduled_count: int
    completed_count: int
    late_count: int = 0


class HabitStreakStat(BaseModel):
    habit_id: str
    title: str
    color: str
    frequency_type: FrequencyType = "daily"
    mode: HabitMode = "free"
    current_streak: int
    best_streak: int
    completion_rate_30d: float
    total_completions: int
    late_completions: int = 0


class StatsSummaryOut(BaseModel):
    active_habits_count: int
    completed_today: int
    scheduled_today: int
    late_today: int = 0
    violated_today: int = 0
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
    mode: HabitMode = "free"
    remind_time: str | None = None
    force_start_time: str | None = None
    force_end_time: str | None = None
    started_on_time: bool = False
    is_late: bool = False
    violation_reason: ViolationReason | None = None
    reminder_enabled: bool = False
    reminder_times: list[str] = Field(default_factory=list)
    reminder_mode: ReminderMode = "notification"
    reminder_snooze_minutes: int = 10
    reminder_message: str = ""
    created_date: str = ""
    date: str
    count: int
    completed: bool
    note: str = ""
    status: Literal["today", "upcoming", "overdue", "completed"]


class HabitHistoryDayOut(BaseModel):
    date: str
    day: int
    weekday: int
    weekday_label: str
    scheduled: bool
    editable: bool
    is_today: bool
    count: int = 0
    completed: bool = False
    is_late: bool = False
    started_on_time: bool = False
    started_at_time: str | None = None
    violation_reason: ViolationReason | None = None
    note: str = ""
    state: HistoryDayState


class HabitHistoryOut(BaseModel):
    habit: HabitOut
    month: str
    start_date: str
    end_date: str
    first_weekday: int
    created_date: str
    today: str
    can_prev_month: bool
    can_next_month: bool
    current_streak: int
    best_streak: int
    completion_rate_30d: float
    total_completions: int
    late_completions: int
    month_scheduled: int
    month_completed_on_time: int
    month_late_makeups: int
    month_missed: int
    days: list[HabitHistoryDayOut]


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
    mode: HabitMode = "free"
    remind_time: str | None = None
    force_start_time: str | None = None
    force_end_time: str | None = None
    reminder_enabled: bool = False
    reminder_times: list[str] = Field(default_factory=list)
    reminder_mode: ReminderMode = "notification"
    reminder_snooze_minutes: int = 10
    reminder_message: str = ""
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


class HabitReminderItemOut(BaseModel):
    habit_id: str
    title: str
    color: str
    icon: str
    frequency_type: FrequencyType = "daily"
    scheduled_today: bool
    completed_today: bool
    count: int = 0
    target_per_day: int = 1
    mode: HabitMode = "reminder"
    remind_time: str | None = None
    force_start_time: str | None = None
    force_end_time: str | None = None
    reminder_enabled: bool = True
    reminder_times: list[str] = Field(default_factory=list)
    reminder_mode: ReminderMode = "notification"
    reminder_snooze_minutes: int = 10
    reminder_message: str = ""
    next_trigger_date: str | None = None
    next_trigger_time: str | None = None
    due_today_times: list[str] = Field(default_factory=list)


class RemindersOverviewOut(BaseModel):
    date: str
    now_time: str | None = None
    enabled_habits_count: int
    alarm_habits_count: int
    notification_habits_count: int
    scheduled_today_count: int
    pending_today_triggers: int
    items: list[HabitReminderItemOut]


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
    today_violated: bool = False,
) -> tuple[int, int]:
    """
    Calculate (current_streak, best_streak) across scheduled days.
    Includes a same-day grace period unless today_violated is True.
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
        if today_violated:
            return 0, best_streak
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
    created_date = _habit_created_date(habit, reference_date - timedelta(days=29))
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


def extract_reminder_fields(
    habit: dict,
) -> tuple[bool, list[str], ReminderMode, int, str]:
    """Safely extract reminder fields from a habit document with legacy fallbacks."""
    enabled = bool(habit.get("reminder_enabled", False))
    raw_times = habit.get("reminder_times") or []
    clean_times: list[str] = []
    if isinstance(raw_times, list):
        for item in raw_times:
            if isinstance(item, str):
                try:
                    clean_times.append(normalize_reminder_time(item))
                except ValueError:
                    continue
    raw_habit_mode = habit.get("mode")
    if (
        raw_habit_mode in ("strict", "window", "reminder")
        and habit.get("reminder_enabled") is not False
    ):
        raw_remind = habit.get("remind_time")
        if isinstance(raw_remind, str) and raw_remind.strip():
            try:
                clean_times.append(normalize_reminder_time(raw_remind))
            except ValueError:
                pass
    clean_times = sorted(set(clean_times))[:MAX_REMINDER_TIMES]
    if (
        raw_habit_mode in ("strict", "window", "reminder")
        and habit.get("reminder_enabled") is not False
        and clean_times
    ):
        enabled = True
    raw_mode = habit.get("reminder_mode", "notification")
    mode: ReminderMode = raw_mode if raw_mode in ("notification", "alarm") else "notification"
    try:
        snooze = int(habit.get("reminder_snooze_minutes", 10))
    except (TypeError, ValueError):
        snooze = 10
    snooze = max(1, min(120, snooze))
    message = str(habit.get("reminder_message", "") or "").strip()[:200]
    return enabled, clean_times, mode, snooze, message


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
    reminder_meta_by_id: dict[str, tuple[bool, list[str], ReminderMode, int, str]] = {}
    mode_meta_by_id: dict[
        str, tuple[HabitMode, str | None, str | None, str | None]
    ] = {}
    for h in habits:
        hid = str(h["_id"])
        resolved_created = resolve_habit_created_date(h, today_date)
        if resolved_created is not None:
            effective_created[hid] = resolved_created
        else:
            raw_created = h.get("created_at")
            # Clamp UTC created_at against local today_date so evening creations count for today.
            effective_created[hid] = (
                min(raw_created.date(), today_date)
                if hasattr(raw_created, "date")
                else start_date
            )
        reminder_meta_by_id[hid] = extract_reminder_fields(h)
        mode_meta_by_id[hid] = extract_habit_mode_fields(h)
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

            r_enabled, r_times, r_mode, r_snooze, r_msg = reminder_meta_by_id[hid]
            h_mode, h_remind, h_start, h_end = mode_meta_by_id[hid]
            raw_viol = chk.get("violation_reason") if chk else None
            viol_reason: ViolationReason | None = (
                raw_viol if raw_viol in ("missed_start", "missed_end") else None
            )
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
                    mode=h_mode,
                    remind_time=h_remind,
                    force_start_time=h_start,
                    force_end_time=h_end,
                    started_on_time=bool(chk.get("started_on_time", False)) if chk else False,
                    is_late=bool(chk.get("is_late", False)) if chk else False,
                    violation_reason=viol_reason,
                    reminder_enabled=r_enabled,
                    reminder_times=r_times,
                    reminder_mode=r_mode,
                    reminder_snooze_minutes=r_snooze,
                    reminder_message=r_msg,
                    created_date=effective_created[hid].isoformat(),
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
        hid = str(h["_id"])
        r_enabled, r_times, r_mode, r_snooze, r_msg = reminder_meta_by_id[hid]
        h_mode, h_remind, h_start, h_end = mode_meta_by_id[hid]
        next_due = acc["next_upcoming"] or acc["first_overdue"]
        habit_summaries.append(
            HabitPeriodSummaryOut(
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
                mode=h_mode,
                remind_time=h_remind,
                force_start_time=h_start,
                force_end_time=h_end,
                reminder_enabled=r_enabled,
                reminder_times=r_times,
                reminder_mode=r_mode,
                reminder_snooze_minutes=r_snooze,
                reminder_message=r_msg,
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
    explicit_created = _parse_optional_iso_date(habit.get("created_date"))
    if explicit_created is not None:
        return explicit_created
    created_at = habit.get("created_at")
    if isinstance(created_at, datetime):
        return created_at.date()
    if isinstance(created_at, date):
        return created_at
    return fallback


def _habit_sli_created_date_and_time(
    habit: dict,
    reference_date: date,
    fallback: date,
) -> tuple[date, str | None]:
    explicit_created = _parse_optional_iso_date(habit.get("created_date"))
    if explicit_created is not None:
        created_d = explicit_created
    else:
        created_at = habit.get("created_at")
        if isinstance(created_at, datetime):
            raw_d = created_at.date()
            created_d = (
                reference_date
                if raw_d == reference_date + timedelta(days=1)
                else raw_d
            )
        elif isinstance(created_at, date):
            created_d = created_at
        else:
            created_d = fallback
    return created_d, format_habit_created_time(habit)


def is_creation_day_window_passed(habit: dict, created_time: str | None) -> bool:
    """Return True when a habit was added after its scheduled cutoff time on creation day."""
    if created_time is None:
        return False
    mode, remind_time, force_start_time, force_end_time = extract_habit_mode_fields(
        habit
    )
    if mode == "strict":
        return bool(force_start_time and created_time > force_start_time)
    if mode == "window":
        return bool(force_end_time and created_time > force_end_time)
    if mode == "reminder":
        _, r_times, _, _, _ = extract_reminder_fields(habit)
        latest = r_times[-1] if r_times else remind_time
        return bool(latest and created_time > latest)
    return False


def habit_sli_start_date(
    habit: dict,
    completed_dates: set[str],
    reference_date: date,
    fallback: date,
) -> date:
    """Return the first date a habit should count in SLI metrics."""
    created_d, created_t = _habit_sli_created_date_and_time(
        habit, reference_date, fallback
    )
    if (
        is_creation_day_window_passed(habit, created_t)
        and created_d.isoformat() not in completed_dates
    ):
        return created_d + timedelta(days=1)
    return created_d


def compute_window_sli_counts(
    habit: dict,
    completed_dates: set[str],
    reference_date: date,
    window_days: int,
    today_violated: bool = False,
) -> tuple[int, int]:
    """Count (scheduled_days, completed_days) over the trailing window bounded by SLI start date."""
    window_start = reference_date - timedelta(days=window_days - 1)
    sli_start = habit_sli_start_date(
        habit, completed_dates, reference_date, fallback=window_start
    )
    effective_violated = today_violated and (reference_date >= sli_start)
    effective_start = max(window_start, sli_start)

    scheduled = 0
    completed = 0
    cursor = effective_start
    while cursor <= reference_date:
        if is_scheduled_on(habit, cursor):
            is_done = cursor.isoformat() in completed_dates
            if cursor == reference_date and not is_done and not effective_violated:
                cursor += timedelta(days=1)
                continue
            scheduled += 1
            if is_done:
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
    today_violated: bool = False,
) -> HabitSliItem:
    hid = str(habit.get("_id", habit.get("id", "")))
    target_slo = round(float(habit.get("target_slo", 85.0)), 1)
    sli_start = habit_sli_start_date(
        habit,
        completed_dates,
        reference_date,
        fallback=reference_date - timedelta(days=window_days - 1),
    )
    effective_violated = today_violated and (reference_date >= sli_start)

    sched_w, comp_w = compute_window_sli_counts(
        habit,
        completed_dates,
        reference_date,
        window_days,
        today_violated=effective_violated,
    )
    sched_7, comp_7 = compute_window_sli_counts(
        habit,
        completed_dates,
        reference_date,
        7,
        today_violated=effective_violated,
    )
    sched_30, comp_30 = compute_window_sli_counts(
        habit,
        completed_dates,
        reference_date,
        30,
        today_violated=effective_violated,
    )
    sched_90, comp_90 = compute_window_sli_counts(
        habit,
        completed_dates,
        reference_date,
        90,
        today_violated=effective_violated,
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

    curr_streak, _ = compute_streaks(
        habit, completed_dates, reference_date, today_violated=effective_violated
    )

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
    violated_habit_ids: set[str] | None = None,
) -> SliDashboardOut:
    if not habits:
        empty_weekdays = [
            WeekdaySliPoint(
                weekday=wd,
                label=WEEKDAY_LABELS[wd],
                scheduled_count=0,
                completed_count=0,
                sli=0.0,
            )
            for wd in range(7)
        ]
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
            trend=[],
            weekday_sli=empty_weekdays,
            habits=[],
        )

    window_start = reference_date - timedelta(days=window_days - 1)
    habit_meta: list[tuple[str, dict, date, bool]] = []
    for h in habits:
        hid = str(h.get("_id", h.get("id", "")))
        c_dates = completed_by_habit.get(hid, set())
        sli_start = habit_sli_start_date(
            h, c_dates, reference_date, fallback=window_start
        )
        is_violated = bool(
            violated_habit_ids and hid in violated_habit_ids
        ) and (reference_date >= sli_start)
        habit_meta.append((hid, h, sli_start, is_violated))

    habit_items: list[HabitSliItem] = []
    total_sched_7 = 0
    total_comp_7 = 0

    for hid, h, _sli_start, is_violated in habit_meta:
        c_dates = completed_by_habit.get(hid, set())
        habit_items.append(
            compute_habit_sli(
                h,
                c_dates,
                reference_date,
                window_days=window_days,
                today_violated=is_violated,
            )
        )
        s7, c7 = compute_window_sli_counts(
            h, c_dates, reference_date, 7, today_violated=is_violated
        )
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

    def day_counts(target: date) -> tuple[int, int]:
        sched = 0
        comp = 0
        d_iso = target.isoformat()
        for hid, h, start_d, is_violated in habit_meta:
            if target < start_d or not is_scheduled_on(h, target):
                continue
            is_done = d_iso in completed_by_habit.get(hid, set())
            if target == reference_date and not is_done and not is_violated:
                continue
            sched += 1
            if is_done:
                comp += 1
        return sched, comp

    earliest_start = min(start_d for _, _, start_d, _ in habit_meta)
    trend_start = max(window_start, earliest_start)
    trend_dates = (
        [
            trend_start + timedelta(days=offset)
            for offset in range((reference_date - trend_start).days + 1)
        ]
        if trend_start <= reference_date
        else []
    )

    if not trend_dates:
        buckets: list[list[date]] = []
    elif len(trend_dates) <= 10:
        buckets = [[d] for d in trend_dates]
    else:
        n = len(trend_dates)
        buckets = [
            trend_dates[(i * n) // 10 : ((i + 1) * n) // 10]
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
    for d in trend_dates:
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


def compute_next_reminder_occurrence(
    habit: dict,
    target_date: date,
    now_hhmm: str | None = None,
    completed_today: bool = False,
) -> tuple[str | None, str | None]:
    """Return (YYYY-MM-DD, HH:MM) for the next upcoming reminder/alarm trigger."""
    if habit.get("archived", False):
        return None, None
    enabled, times, _, _, _ = extract_reminder_fields(habit)
    if not enabled or not times:
        return None, None

    normalized_now = normalize_reminder_time(now_hhmm) if now_hhmm else None
    for offset in range(63):
        candidate = target_date + timedelta(days=offset)
        if not is_scheduled_on(habit, candidate):
            continue
        if offset == 0:
            if completed_today:
                continue
            if normalized_now is not None:
                for hhmm in times:
                    if hhmm >= normalized_now:
                        return candidate.isoformat(), hhmm
                continue
        return candidate.isoformat(), times[0]

    return None, None


def build_reminders_overview(
    habits: list[dict],
    day_checkins: dict[str, dict],
    target_date: date,
    now_time: str | None = None,
) -> RemindersOverviewOut:
    """Build an overview of active habit reminders and alarms for target_date."""
    normalized_now = (
        normalize_reminder_time(now_time) if now_time and now_time.strip() else None
    )
    items: list[HabitReminderItemOut] = []
    alarm_count = 0
    notification_count = 0
    scheduled_today_count = 0
    pending_today_triggers = 0

    for h in habits:
        if h.get("archived", False):
            continue
        enabled, times, mode, snooze_mins, message = extract_reminder_fields(h)
        if not enabled or not times:
            continue
        h_mode, h_remind, h_start, h_end = extract_habit_mode_fields(h)
        if h_mode == "free":
            h_mode = "reminder"
            h_remind = times[0]

        hid = str(h.get("_id", h.get("id", "")))
        chk = day_checkins.get(hid)
        completed_today = bool(chk.get("completed", False)) if chk else False
        count = int(chk.get("count", 0)) if chk else 0
        scheduled_today = is_scheduled_on(h, target_date)

        due_today_times = (
            [
                hhmm
                for hhmm in times
                if normalized_now is None or hhmm >= normalized_now
            ]
            if scheduled_today and not completed_today
            else []
        )

        next_date, next_time = compute_next_reminder_occurrence(
            h,
            target_date=target_date,
            now_hhmm=normalized_now,
            completed_today=completed_today,
        )

        if mode == "alarm":
            alarm_count += 1
        else:
            notification_count += 1
        if scheduled_today:
            scheduled_today_count += 1
        pending_today_triggers += len(due_today_times)

        items.append(
            HabitReminderItemOut(
                habit_id=hid,
                title=h["title"],
                color=h.get("color", "#6366F1"),
                icon=h.get("icon", "check_circle"),
                frequency_type=h.get("frequency_type", "daily"),
                scheduled_today=scheduled_today,
                completed_today=completed_today,
                count=count,
                target_per_day=int(h.get("target_per_day", 1)),
                mode=h_mode,
                remind_time=h_remind,
                force_start_time=h_start,
                force_end_time=h_end,
                reminder_enabled=True,
                reminder_times=times,
                reminder_mode=mode,
                reminder_snooze_minutes=snooze_mins,
                reminder_message=message,
                next_trigger_date=next_date,
                next_trigger_time=next_time,
                due_today_times=due_today_times,
            )
        )

    items.sort(
        key=lambda it: (
            it.next_trigger_date is None,
            it.next_trigger_date or "9999-99-99",
            it.next_trigger_time or "99:99",
            it.title.lower(),
        )
    )

    return RemindersOverviewOut(
        date=target_date.isoformat(),
        now_time=normalized_now,
        enabled_habits_count=len(items),
        alarm_habits_count=alarm_count,
        notification_habits_count=notification_count,
        scheduled_today_count=scheduled_today_count,
        pending_today_triggers=pending_today_triggers,
        items=items,
    )


def build_habit_history(
    habit: dict,
    habit_out: HabitOut,
    month_checkins: dict[str, dict],
    completed_dates: set[str],
    late_dates: set[str],
    year: int,
    month: int,
    client_today_date: date,
    client_time: str,
    today_checkin: dict | None = None,
) -> HabitHistoryOut:
    """Build per-habit monthly check-in history calendar and summary stats."""
    first_weekday, days_in_month = calendar.monthrange(year, month)
    start_d = date(year, month, 1)
    end_d = date(year, month, days_in_month)

    created_d = resolve_habit_created_date(habit, client_today_date)
    if created_d is None:
        created_at = habit.get("created_at")
        if isinstance(created_at, datetime):
            created_d = created_at.date()
        elif isinstance(created_at, date):
            created_d = created_at
        else:
            created_d = client_today_date
    created_d = min(created_d, client_today_date)

    client_today_iso = client_today_date.isoformat()
    can_prev_month = start_d > created_d.replace(day=1)
    can_next_month = start_d < client_today_date.replace(day=1)

    days: list[HabitHistoryDayOut] = []
    month_scheduled = 0
    month_completed_on_time = 0
    month_late_makeups = 0
    month_missed = 0

    for day_num in range(1, days_in_month + 1):
        d = date(year, month, day_num)
        d_iso = d.isoformat()
        chk = month_checkins.get(d_iso)
        scheduled = is_scheduled_on(habit, d)
        editable = created_d <= d <= client_today_date

        count = int(chk.get("count", 0)) if chk else 0
        completed = bool(chk.get("completed", False)) if chk else False
        is_late = bool(chk.get("is_late", False)) if chk else False
        started_on_time = bool(chk.get("started_on_time", False)) if chk else False
        started_at_time = chk.get("started_at_time") if chk else None
        raw_viol = chk.get("violation_reason") if chk else None
        violation_reason: ViolationReason | None = (
            raw_viol if raw_viol in ("missed_start", "missed_end") else None
        )
        note = str(chk.get("note", "") or "") if chk else ""

        if d > client_today_date:
            state: HistoryDayState = "future"
        elif d < created_d:
            state = "before_created"
        else:
            ev = evaluate_habit_day_status(
                habit=habit,
                checkin=chk,
                target_date_str=d_iso,
                client_today_str=client_today_iso,
                client_time=client_time,
                scheduled=scheduled,
                can_edit=True,
            )
            is_late = ev.is_late
            violation_reason = ev.violation_reason
            started_on_time = ev.started_on_time
            started_at_time = ev.started_at_time
            if ev.day_status == "on_time":
                state = "on_time"
            elif ev.day_status == "late_makeup":
                state = "late_makeup"
            elif not scheduled:
                state = "unscheduled"
            elif d < client_today_date:
                state = "missed"
            else:
                state = ev.day_status

        if editable and scheduled:
            month_scheduled += 1
        if state == "on_time":
            month_completed_on_time += 1
        elif state == "late_makeup":
            month_late_makeups += 1
        elif state in ("missed", "violation"):
            month_missed += 1

        days.append(
            HabitHistoryDayOut(
                date=d_iso,
                day=day_num,
                weekday=d.weekday(),
                weekday_label=WEEKDAY_LABELS[d.weekday()],
                scheduled=scheduled,
                editable=editable,
                is_today=(d == client_today_date),
                count=count,
                completed=completed,
                is_late=is_late,
                started_on_time=started_on_time,
                started_at_time=started_at_time,
                violation_reason=violation_reason,
                note=note,
                state=state,
            )
        )

    today_scheduled = is_scheduled_on(habit, client_today_date)
    resolved_today_chk = (
        today_checkin
        if today_checkin is not None
        else month_checkins.get(client_today_iso)
    )
    today_ev = evaluate_habit_day_status(
        habit=habit,
        checkin=resolved_today_chk,
        target_date_str=client_today_iso,
        client_today_str=client_today_iso,
        client_time=client_time,
        scheduled=today_scheduled,
        can_edit=True,
    )
    today_violated = today_scheduled and today_ev.day_status in (
        "violation",
        "late_makeup",
    )

    curr_streak, best_streak = compute_streaks(
        habit,
        completed_dates,
        client_today_date,
        today_violated=today_violated,
    )
    rate_habit = {**habit, "created_date": created_d.isoformat()}
    rate_30d = compute_30d_completion_rate(
        rate_habit, completed_dates, client_today_date
    )

    synced_habit = habit_out.model_copy(update={"created_date": created_d.isoformat()})
    return HabitHistoryOut(
        habit=synced_habit,
        month=f"{year:04d}-{month:02d}",
        start_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
        first_weekday=first_weekday,
        created_date=created_d.isoformat(),
        today=client_today_iso,
        can_prev_month=can_prev_month,
        can_next_month=can_next_month,
        current_streak=curr_streak,
        best_streak=best_streak,
        completion_rate_30d=rate_30d,
        total_completions=len(completed_dates),
        late_completions=len(late_dates),
        month_scheduled=month_scheduled,
        month_completed_on_time=month_completed_on_time,
        month_late_makeups=month_late_makeups,
        month_missed=month_missed,
        days=days,
    )
