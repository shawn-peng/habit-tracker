from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import os
from typing import Literal

from bson import ObjectId
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import BaseModel, EmailStr, Field, field_validator
from pwdlib import PasswordHash
from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

load_dotenv()


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


def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def create_access_token(user_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


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
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class HabitCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)
    color: str = Field(default="#6366F1", max_length=20)
    icon: str = Field(default="check_circle", max_length=40)
    frequency_type: Literal["daily", "weekdays"] = "daily"
    weekdays: list[int] = Field(
        default_factory=lambda: [0, 1, 2, 3, 4, 5, 6],
        description="0=Monday .. 6=Sunday",
    )
    target_per_day: int = Field(default=1, ge=1, le=100)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, v: list[int]) -> list[int]:
        cleaned = sorted({d for d in v if 0 <= d <= 6})
        if not cleaned:
            raise ValueError("At least one weekday (0..6) must be selected")
        return cleaned


class HabitUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=300)
    color: str | None = Field(default=None, max_length=20)
    icon: str | None = Field(default=None, max_length=40)
    frequency_type: Literal["daily", "weekdays"] | None = None
    weekdays: list[int] | None = None
    target_per_day: int | None = Field(default=None, ge=1, le=100)
    archived: bool | None = None

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        cleaned = sorted({d for d in v if 0 <= d <= 6})
        if not cleaned:
            raise ValueError("At least one weekday (0..6) must be selected")
        return cleaned


class HabitOut(BaseModel):
    id: str
    title: str
    description: str
    color: str
    icon: str
    frequency_type: Literal["daily", "weekdays"]
    weekdays: list[int]
    target_per_day: int
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


# ---------------------------------------------------------------------------
# Streak & Completion Calculations
# ---------------------------------------------------------------------------
def is_scheduled_on(habit: dict, target: date) -> bool:
    if habit.get("frequency_type", "daily") == "daily":
        return True
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

    if scheduled == 0:
        return 0.0
    return round((completed / scheduled) * 100.0, 1)
