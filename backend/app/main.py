from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from bson import ObjectId
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core import (
    CheckinRequest,
    DailyActivityPoint,
    HabitCreate,
    HabitOut,
    HabitStreakStat,
    HabitTodayOut,
    HabitUpdate,
    LoginRequest,
    PeriodScheduleOut,
    RegisterRequest,
    SliDashboardOut,
    StatsSummaryOut,
    TokenResponse,
    UserPublic,
    build_period_schedule,
    build_sli_dashboard,
    compute_30d_completion_rate,
    compute_period_bounds,
    compute_streaks,
    create_access_token,
    ensure_indexes,
    get_current_user,
    get_db,
    hash_password,
    is_scheduled_on,
    settings,
    verify_password,
)

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncMongoClient(settings.mongodb_uri) as client:
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
        created_at=user_doc["created_at"],
    )


def _serialize_habit(habit_doc: dict) -> HabitOut:
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
        archived=habit_doc.get("archived", False),
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
@app.post(
    "/api/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    db: AsyncDatabase = Depends(get_db),
) -> TokenResponse:
    email_norm = payload.email.lower().strip()
    now = datetime.now(timezone.utc)
    user_doc = {
        "name": payload.name.strip(),
        "email": email_norm,
        "password_hash": hash_password(payload.password),
        "created_at": now,
    }
    try:
        res = await db.users.insert_one(user_doc)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc

    user_doc["_id"] = res.inserted_id
    token = create_access_token(str(res.inserted_id), email_norm)
    return TokenResponse(access_token=token, user=_serialize_user(user_doc))


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

    token = create_access_token(str(user_doc["_id"]), email_norm)
    return TokenResponse(access_token=token, user=_serialize_user(user_doc))


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
        "archived": False,
        "created_at": datetime.now(timezone.utc),
    }
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
    if "target_slo" in updates:
        updates["target_slo"] = round(float(updates["target_slo"]), 1)
    if updates.get("frequency_type") == "daily":
        updates["weekdays"] = [0, 1, 2, 3, 4, 5, 6]
    elif updates.get("frequency_type") == "monthly" and "weekdays" not in updates:
        updates["weekdays"] = [0, 1, 2, 3, 4, 5, 6]

    if not updates:
        existing = await db.habits.find_one(
            {"_id": ObjectId(habit_id), "user_id": str(current_user["_id"])}
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Habit not found")
        return _serialize_habit(existing)

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
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> list[HabitTodayOut]:
    parsed_date = _parse_iso_date(target_date)
    iso_date = parsed_date.isoformat()
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

    # Fetch check-ins on target_date + all completed dates for streak calculation
    day_checkins: dict[str, dict] = {}
    async for chk in db.checkins.find(
        {"user_id": user_id, "habit_id": {"$in": habit_ids}, "date": iso_date}
    ):
        day_checkins[chk["habit_id"]] = chk

    completed_by_habit: dict[str, set[str]] = {hid: set() for hid in habit_ids}
    async for chk in db.checkins.find(
        {"user_id": user_id, "habit_id": {"$in": habit_ids}, "completed": True},
        {"habit_id": 1, "date": 1},
    ):
        completed_by_habit[chk["habit_id"]].add(chk["date"])

    results: list[HabitTodayOut] = []
    for h in habits:
        hid = str(h["_id"])
        chk = day_checkins.get(hid)
        curr_streak, best_streak = compute_streaks(
            h, completed_by_habit[hid], parsed_date
        )
        base = _serialize_habit(h)
        results.append(
            HabitTodayOut(
                **base.model_dump(),
                date=iso_date,
                scheduled_today=is_scheduled_on(h, parsed_date),
                count=chk["count"] if chk else 0,
                completed=chk["completed"] if chk else False,
                note=chk.get("note", "") if chk else "",
                current_streak=curr_streak,
                best_streak=best_streak,
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
    user_id = str(current_user["_id"])

    habit = await db.habits.find_one({"_id": ObjectId(habit_id), "user_id": user_id})
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    target = habit.get("target_per_day", 1)
    existing = await db.checkins.find_one(
        {"habit_id": habit_id, "user_id": user_id, "date": iso_date}
    )
    prev_count = existing["count"] if existing else 0
    prev_note = existing.get("note", "") if existing else ""

    if payload.action == "increment":
        new_count = prev_count + 1
    elif payload.action == "decrement":
        new_count = max(0, prev_count - 1)
    elif payload.action == "toggle":
        new_count = 0 if prev_count >= target else target
    else:  # "set"
        new_count = payload.count if payload.count is not None else target

    completed = new_count >= target
    note = payload.note if payload.note is not None else prev_note

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
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )

    completed_dates: set[str] = set()
    async for chk in db.checkins.find(
        {"user_id": user_id, "habit_id": habit_id, "completed": True},
        {"date": 1},
    ):
        completed_dates.add(chk["date"])

    curr_streak, best_streak = compute_streaks(habit, completed_dates, parsed_date)
    base = _serialize_habit(habit)
    return HabitTodayOut(
        **base.model_dump(),
        date=iso_date,
        scheduled_today=is_scheduled_on(habit, parsed_date),
        count=new_count,
        completed=completed,
        note=note,
        current_streak=curr_streak,
        best_streak=best_streak,
    )


# ---------------------------------------------------------------------------
# Analytics & Streak Summary
# ---------------------------------------------------------------------------
@app.get("/api/stats/summary", response_model=StatsSummaryOut)
async def get_stats_summary(
    today: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> StatsSummaryOut:
    ref_date = _parse_iso_date(today)
    user_id = str(current_user["_id"])

    habits = [
        doc
        async for doc in db.habits.find({"user_id": user_id, "archived": False}).sort(
            "created_at", 1
        )
    ]
    habit_ids = [str(h["_id"]) for h in habits]
    completed_by_habit: dict[str, set[str]] = {hid: set() for hid in habit_ids}

    if habit_ids:
        async for chk in db.checkins.find(
            {"user_id": user_id, "habit_id": {"$in": habit_ids}, "completed": True},
            {"habit_id": 1, "date": 1},
        ):
            completed_by_habit[chk["habit_id"]].add(chk["date"])

    # 7-day bar chart activity
    last_7_days: list[DailyActivityPoint] = []
    for offset in range(6, -1, -1):
        d = ref_date - timedelta(days=offset)
        d_iso = d.isoformat()
        sched_cnt = 0
        comp_cnt = 0
        for h in habits:
            hid = str(h["_id"])
            if is_scheduled_on(h, d):
                sched_cnt += 1
                if d_iso in completed_by_habit[hid]:
                    comp_cnt += 1
        last_7_days.append(
            DailyActivityPoint(
                date=d_iso,
                weekday_label=WEEKDAY_NAMES[d.weekday()],
                scheduled_count=sched_cnt,
                completed_count=comp_cnt,
            )
        )

    habit_stats: list[HabitStreakStat] = []
    best_active_streak = 0
    rates: list[float] = []

    for h in habits:
        hid = str(h["_id"])
        c_dates = completed_by_habit[hid]
        curr_s, best_s = compute_streaks(h, c_dates, ref_date)
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
                current_streak=curr_s,
                best_streak=best_s,
                completion_rate_30d=rate_30d,
                total_completions=len(c_dates),
            )
        )

    habit_stats.sort(key=lambda s: (s.current_streak, s.best_streak), reverse=True)
    today_point = last_7_days[-1]
    overall_rate = round(sum(rates) / len(rates), 1) if rates else 0.0

    return StatsSummaryOut(
        active_habits_count=len(habits),
        completed_today=today_point.completed_count,
        scheduled_today=today_point.scheduled_count,
        best_active_streak=best_active_streak,
        overall_completion_rate_30d=overall_rate,
        last_7_days=last_7_days,
        habit_stats=habit_stats,
    )


@app.get("/api/stats/sli", response_model=SliDashboardOut)
async def get_sli_dashboard(
    window_days: int = Query(default=30, ge=7, le=365),
    today: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> SliDashboardOut:
    ref_date = _parse_iso_date(today)
    user_id = str(current_user["_id"])

    habits = [
        doc
        async for doc in db.habits.find({"user_id": user_id, "archived": False}).sort(
            "created_at", 1
        )
    ]
    habit_ids = [str(h["_id"]) for h in habits]
    completed_by_habit: dict[str, set[str]] = {hid: set() for hid in habit_ids}

    if habit_ids:
        async for chk in db.checkins.find(
            {"user_id": user_id, "habit_id": {"$in": habit_ids}, "completed": True},
            {"habit_id": 1, "date": 1},
        ):
            completed_by_habit[chk["habit_id"]].add(chk["date"])

    return build_sli_dashboard(
        habits,
        completed_by_habit,
        ref_date,
        window_days=window_days,
    )
