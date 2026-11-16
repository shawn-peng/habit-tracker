import asyncio
from datetime import date, datetime, timedelta, timezone
import logging
import smtplib

from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.core import (
    HabitCreate,
    HabitUpdate,
    Settings,
    build_period_schedule,
    build_reminders_overview,
    build_sli_dashboard,
    compute_30d_completion_rate,
    compute_burn_rate,
    compute_error_budget,
    compute_habit_sli,
    compute_next_reminder_occurrence,
    compute_period_bounds,
    compute_streaks,
    create_access_token,
    get_current_user,
    get_db,
    hash_password,
    hash_reset_code,
    is_scheduled_on,
    normalize_reminder_time,
    normalize_reminder_times,
    scheduled_monthly_day,
    send_password_reset_email,
    send_registration_verification_email,
)
import app.main as main_module
from app.main import _serialize_habit, app


def test_daily_streak_with_morning_grace():
    habit = {"frequency_type": "daily", "weekdays": [0, 1, 2, 3, 4, 5, 6]}
    completed = {"2026-11-11", "2026-11-12", "2026-11-13"}
    # On 2026-11-14 before checking in, streak from yesterday (3) is preserved
    curr, best = compute_streaks(habit, completed, date(2026, 11, 14))
    assert curr == 3
    assert best == 3

    # On 2026-11-15 after missing 2026-11-14 completely, current streak resets to 0
    curr_missed, best_missed = compute_streaks(habit, completed, date(2026, 11, 15))
    assert curr_missed == 0
    assert best_missed == 3


def test_weekday_schedule_streaks():
    # Scheduled Monday (0), Wednesday (2), Friday (4)
    habit = {"frequency_type": "weekdays", "weekdays": [0, 2, 4]}
    assert is_scheduled_on(habit, date(2026, 11, 9)) is True   # Monday
    assert is_scheduled_on(habit, date(2026, 11, 10)) is False  # Tuesday

    completed = {"2026-11-09", "2026-11-11", "2026-11-13"}  # Mon, Wed, Fri
    # Saturday 2026-11-14 is unscheduled, streak should remain 3!
    curr, best = compute_streaks(habit, completed, date(2026, 11, 14))
    assert curr == 3
    assert best == 3


def test_30d_completion_rate():
    habit = {
        "frequency_type": "daily",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "created_at": datetime(2026, 11, 11, tzinfo=timezone.utc),
    }
    # Created 4 days ago (Nov 11, 12, 13, 14), completed 3 out of 4 days -> 75.0%
    completed = {"2026-11-11", "2026-11-12", "2026-11-14"}
    rate = compute_30d_completion_rate(habit, completed, date(2026, 11, 14))
    assert rate == 75.0


def test_monthly_from_start_and_short_month_clamping():
    habit_15 = {
        "frequency_type": "monthly",
        "monthly_mode": "from_start",
        "monthly_day": 15,
    }
    assert scheduled_monthly_day(2026, 11, habit_15) == 15
    assert is_scheduled_on(habit_15, date(2026, 11, 15)) is True
    assert is_scheduled_on(habit_15, date(2026, 11, 14)) is False

    habit_31 = {
        "frequency_type": "monthly",
        "monthly_mode": "from_start",
        "monthly_day": 31,
    }
    assert scheduled_monthly_day(2026, 1, habit_31) == 31
    assert scheduled_monthly_day(2026, 2, habit_31) == 28
    assert scheduled_monthly_day(2028, 2, habit_31) == 29  # Leap year
    assert scheduled_monthly_day(2026, 4, habit_31) == 30
    assert is_scheduled_on(habit_31, date(2026, 2, 28)) is True
    assert is_scheduled_on(habit_31, date(2028, 2, 29)) is True
    assert is_scheduled_on(habit_31, date(2026, 4, 30)) is True


def test_monthly_from_end():
    last_day_habit = {
        "frequency_type": "monthly",
        "monthly_mode": "from_end",
        "monthly_day": 1,
    }
    assert scheduled_monthly_day(2026, 2, last_day_habit) == 28
    assert scheduled_monthly_day(2028, 2, last_day_habit) == 29
    assert scheduled_monthly_day(2026, 11, last_day_habit) == 30
    assert scheduled_monthly_day(2026, 12, last_day_habit) == 31
    assert is_scheduled_on(last_day_habit, date(2026, 11, 30)) is True
    assert is_scheduled_on(last_day_habit, date(2026, 11, 29)) is False

    third_from_end = {
        "frequency_type": "monthly",
        "monthly_mode": "from_end",
        "monthly_day": 3,
    }
    assert scheduled_monthly_day(2026, 11, third_from_end) == 28
    assert is_scheduled_on(third_from_end, date(2026, 11, 28)) is True

    offset_31 = {
        "frequency_type": "monthly",
        "monthly_mode": "from_end",
        "monthly_day": 31,
    }
    assert scheduled_monthly_day(2026, 2, offset_31) == 1
    assert is_scheduled_on(offset_31, date(2026, 2, 1)) is True


def test_monthly_nth_weekday():
    # November 2026 starts on Sunday (Nov 1 = Sun, Nov 2 = Mon, Nov 30 = Mon)
    first_mon = {
        "frequency_type": "monthly",
        "monthly_mode": "nth_weekday",
        "monthly_week": 1,
        "monthly_weekday": 0,
    }
    assert scheduled_monthly_day(2026, 11, first_mon) == 2
    assert is_scheduled_on(first_mon, date(2026, 11, 2)) is True

    second_sat = {
        "frequency_type": "monthly",
        "monthly_mode": "nth_weekday",
        "monthly_week": 2,
        "monthly_weekday": 5,
    }
    assert scheduled_monthly_day(2026, 11, second_sat) == 14
    assert is_scheduled_on(second_sat, date(2026, 11, 14)) is True

    last_mon = {
        "frequency_type": "monthly",
        "monthly_mode": "nth_weekday",
        "monthly_week": -1,
        "monthly_weekday": 0,
    }
    assert scheduled_monthly_day(2026, 11, last_mon) == 30
    assert is_scheduled_on(last_mon, date(2026, 11, 30)) is True

    last_fri = {
        "frequency_type": "monthly",
        "monthly_mode": "nth_weekday",
        "monthly_week": -1,
        "monthly_weekday": 4,
    }
    assert scheduled_monthly_day(2026, 11, last_fri) == 27
    assert is_scheduled_on(last_fri, date(2026, 11, 27)) is True

    # November 2026 only has 4 Saturdays (7, 14, 21, 28); week 5 clamps to 4th Saturday (28)
    fifth_sat = {
        "frequency_type": "monthly",
        "monthly_mode": "nth_weekday",
        "monthly_week": 5,
        "monthly_weekday": 5,
    }
    assert scheduled_monthly_day(2026, 11, fifth_sat) == 28
    assert is_scheduled_on(fifth_sat, date(2026, 11, 28)) is True


def test_monthly_streaks_and_completion_rate():
    habit_15 = {
        "frequency_type": "monthly",
        "monthly_mode": "from_start",
        "monthly_day": 15,
    }
    completed = {"2026-09-15", "2026-10-15"}

    # Unscheduled day between monthly occurrences preserves streak
    curr_mid, best_mid = compute_streaks(habit_15, completed, date(2026, 11, 14))
    assert curr_mid == 2
    assert best_mid == 2

    # Same-day grace period on scheduled monthly day before completion
    curr_due, best_due = compute_streaks(habit_15, completed, date(2026, 11, 15))
    assert curr_due == 2
    assert best_due == 2

    # After scheduled monthly day passes uncompleted, current streak resets to 0
    curr_missed, best_missed = compute_streaks(habit_15, completed, date(2026, 11, 16))
    assert curr_missed == 0
    assert best_missed == 2

    # 35-day gap between 2nd Monday of Aug 2026 (2026-08-10) and 2nd Monday of Sep 2026 (2026-09-14)
    second_mon = {
        "frequency_type": "monthly",
        "monthly_mode": "nth_weekday",
        "monthly_week": 2,
        "monthly_weekday": 0,
        "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
    }
    assert compute_30d_completion_rate(second_mon, {"2026-08-10"}, date(2026, 9, 13)) == 100.0
    assert compute_30d_completion_rate(second_mon, set(), date(2026, 9, 13)) == 0.0


def test_habit_schema_validation_and_legacy_serialization():
    # Monthly accepts empty weekdays and normalizes to all 7 days
    monthly_payload = HabitCreate(
        title="Pay Rent",
        frequency_type="monthly",
        weekdays=[],
        monthly_mode="from_end",
        monthly_day=2,
    )
    assert monthly_payload.weekdays == [0, 1, 2, 3, 4, 5, 6]
    assert monthly_payload.monthly_mode == "from_end"
    assert monthly_payload.monthly_day == 2

    # Weekdays schedule rejects empty weekdays
    with pytest.raises(ValidationError):
        HabitCreate(title="Gym", frequency_type="weekdays", weekdays=[])

    # Out-of-range monthly_day, monthly_week, monthly_weekday fail validation
    with pytest.raises(ValidationError):
        HabitCreate(title="Bad Day", frequency_type="monthly", monthly_day=32)
    with pytest.raises(ValidationError):
        HabitCreate(title="Bad Week", frequency_type="monthly", monthly_week=0)
    with pytest.raises(ValidationError):
        HabitCreate(title="Bad Weekday", frequency_type="monthly", monthly_weekday=7)

    with pytest.raises(ValidationError):
        HabitUpdate(monthly_week=6)
    with pytest.raises(ValidationError):
        HabitUpdate(frequency_type="weekdays", weekdays=[])

    upd_monthly = HabitUpdate(frequency_type="monthly", weekdays=[])
    assert upd_monthly.weekdays == [0, 1, 2, 3, 4, 5, 6]

    # Legacy DB document without monthly_* keys serializes cleanly with defaults
    legacy_doc = {
        "_id": ObjectId(),
        "title": "Drink Water",
        "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
    }
    out = _serialize_habit(legacy_doc)
    assert out.frequency_type == "daily"
    assert out.monthly_mode == "from_start"
    assert out.monthly_day == 1
    assert out.monthly_week == 1
    assert out.monthly_weekday == 0
    assert out.target_slo == 85.0


def test_habit_sli_healthy_warning_and_breached_math():
    ref = date(2026, 11, 14)
    # 20-day window of a daily habit with target_slo=80.0 -> allowed error budget = 4.0 days
    created = datetime(2026, 10, 26, tzinfo=timezone.utc)
    all_20_days = [
        (ref - timedelta(days=offset)).isoformat() for offset in range(19, -1, -1)
    ]

    # 1 miss in first 10 days -> 19/20 = 95.0% SLI, 3.0/4.0 budget left (75%), burn=0.25 -> healthy
    habit = {
        "_id": ObjectId(),
        "title": "Read 20 pages",
        "color": "#6366F1",
        "frequency_type": "daily",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "target_slo": 80.0,
        "created_at": created,
    }
    completed_healthy = set(all_20_days) - {all_20_days[2]}
    item_healthy = compute_habit_sli(habit, completed_healthy, ref, window_days=30)
    assert item_healthy.scheduled_days == 20
    assert item_healthy.completed_days == 19
    assert item_healthy.missed_days == 1
    assert item_healthy.current_sli == 95.0
    assert item_healthy.sli_delta == 15.0
    assert item_healthy.slo_met is True
    assert item_healthy.status == "healthy"
    assert item_healthy.error_budget_allowed_days == 4.0
    assert item_healthy.error_budget_used_days == 1
    assert item_healthy.error_budget_remaining_days == 3.0
    assert item_healthy.error_budget_remaining_pct == 75.0
    assert item_healthy.burn_rate == 0.25
    assert item_healthy.burn_rate_7d == 0.0

    # 3 misses in the last 7 days -> 17/20 = 85.0% (>= 80% SLO), 1.0/4.0 budget left (25.0%),
    # 7d miss rate = 3/7 -> burn_rate_7d = 2.14x -> warning
    completed_warning = set(all_20_days) - {
        all_20_days[-1],
        all_20_days[-2],
        all_20_days[-3],
    }
    item_warning = compute_habit_sli(habit, completed_warning, ref, window_days=30)
    assert item_warning.current_sli == 85.0
    assert item_warning.slo_met is True
    assert item_warning.error_budget_remaining_days == 1.0
    assert item_warning.error_budget_remaining_pct == 25.0
    assert item_warning.burn_rate == 0.75
    assert item_warning.burn_rate_7d == 2.14
    assert item_warning.status == "warning"

    # 5 misses -> 15/20 = 75.0% (< 80% SLO), -1.0d remaining (0.0%), burn=1.25x -> breached
    completed_breached = set(all_20_days) - set(all_20_days[:5])
    item_breached = compute_habit_sli(habit, completed_breached, ref, window_days=30)
    assert item_breached.current_sli == 75.0
    assert item_breached.sli_delta == -5.0
    assert item_breached.slo_met is False
    assert item_breached.error_budget_remaining_days == -1.0
    assert item_breached.error_budget_remaining_pct == 0.0
    assert item_breached.burn_rate == 1.25
    assert item_breached.status == "breached"


def test_habit_sli_100_percent_slo_finite_burn_cap():
    ref = date(2026, 11, 14)
    habit = {
        "_id": ObjectId(),
        "title": "Zero Miss Habit",
        "frequency_type": "daily",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "target_slo": 100.0,
        "created_at": datetime(2026, 11, 8, tzinfo=timezone.utc),
    }
    days_7 = {(ref - timedelta(days=i)).isoformat() for i in range(7)}

    # 0 misses at 100% SLO -> 0.0 allowed, 100.0% remaining, 0.0 burn
    allowed, rem_days, rem_pct = compute_error_budget(7, 0, 100.0)
    assert allowed == 0.0
    assert rem_days == 0.0
    assert rem_pct == 100.0
    assert compute_burn_rate(7, 0, 100.0) == 0.0
    perfect = compute_habit_sli(habit, days_7, ref, window_days=7)
    assert perfect.status == "healthy"
    assert perfect.burn_rate == 0.0
    assert perfect.error_budget_remaining_pct == 100.0

    # >=1 miss at 100% SLO -> finite burn rate cap 10.0, 0.0% budget left, breached
    missed_one = days_7 - {ref.isoformat()}
    breached = compute_habit_sli(habit, missed_one, ref, window_days=7)
    assert breached.error_budget_allowed_days == 0.0
    assert breached.error_budget_remaining_days == -1.0
    assert breached.error_budget_remaining_pct == 0.0
    assert breached.burn_rate == 10.0
    assert breached.burn_rate_7d == 10.0
    assert breached.status == "breached"


def test_build_sli_dashboard_windows_empty_and_diagnostics():
    ref = date(2026, 11, 14)

    empty_dash = build_sli_dashboard([], {}, ref, window_days=30)
    assert empty_dash.active_habits_count == 0
    assert empty_dash.overall_status == "no_data"
    assert empty_dash.overall_target_slo == 85.0
    assert len(empty_dash.trend) == 10
    assert all(not pt.has_activity for pt in empty_dash.trend)
    assert len(empty_dash.weekday_sli) == 7
    assert empty_dash.habits == []

    h_healthy = {
        "_id": "h1",
        "title": "Hydrate",
        "color": "#10B981",
        "frequency_type": "daily",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "target_slo": 80.0,
        "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
    }
    h_breached = {
        "_id": "h2",
        "title": "Deep Work",
        "color": "#6366F1",
        "frequency_type": "daily",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "target_slo": 90.0,
        "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
    }

    all_90 = [(ref - timedelta(days=i)).isoformat() for i in range(90)]
    # Hydrate: 100% completion across 90 days
    # Deep Work: miss every Friday in the 90-day window -> Friday is weakest weekday & Deep Work is top burn
    completed_by_habit = {
        "h1": set(all_90),
        "h2": {d for d in all_90 if date.fromisoformat(d).weekday() != 4},
    }

    dash_7 = build_sli_dashboard([h_healthy, h_breached], completed_by_habit, ref, window_days=7)
    assert len(dash_7.trend) == 7
    assert dash_7.trend[-1].end_date == "2026-11-14"

    dash_30 = build_sli_dashboard([h_healthy, h_breached], completed_by_habit, ref, window_days=30)
    assert len(dash_30.trend) == 10
    assert dash_30.habits[0].title == "Deep Work"
    assert dash_30.habits[0].status == "breached"
    assert dash_30.habits[1].title == "Hydrate"
    assert dash_30.habits[1].status == "healthy"
    assert dash_30.weakest_weekday == "Fri"
    assert dash_30.weakest_weekday_sli == 50.0
    assert dash_30.top_burn_habit_title == "Deep Work"
    assert dash_30.top_burn_rate is not None and dash_30.top_burn_rate > 1.0
    assert dash_30.overall_status == "breached"
    assert dash_30.breached_count == 1
    assert dash_30.healthy_count == 1

    dash_90 = build_sli_dashboard([h_healthy, h_breached], completed_by_habit, ref, window_days=90)
    assert len(dash_90.trend) == 10
    assert dash_90.trend[0].start_date == (ref - timedelta(days=89)).isoformat()
    assert dash_90.trend[-1].end_date == "2026-11-14"


class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = list(docs)

    def sort(self, field: str, direction: int = 1) -> "_FakeCursor":
        self._docs.sort(key=lambda d: d.get(field, ""), reverse=(direction < 0))
        return self

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _FakeDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class _FakeUpdateResult:
    def __init__(self, matched_count: int, upserted_id=None):
        self.matched_count = matched_count
        self.upserted_id = upserted_id


class _FakeCollection:
    def __init__(self, docs: list[dict] | None = None):
        self.docs = list(docs or [])

    def find(self, query: dict, _projection: dict | None = None) -> _FakeCursor:
        matched = [doc for doc in self.docs if self._matches(doc, query)]
        return _FakeCursor(matched)

    async def find_one(self, query: dict) -> dict | None:
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    async def insert_one(self, doc: dict) -> _FakeInsertResult:
        oid = ObjectId()
        stored = {**doc, "_id": oid}
        self.docs.append(stored)
        return _FakeInsertResult(oid)

    async def update_one(
        self, query: dict, update: dict, upsert: bool = False
    ) -> _FakeUpdateResult:
        doc = await self.find_one(query)
        if doc is not None:
            if "$set" in update:
                doc.update(update["$set"])
            return _FakeUpdateResult(matched_count=1)
        if upsert:
            new_doc = {k: v for k, v in query.items() if not isinstance(v, dict)}
            if "$set" in update:
                new_doc.update(update["$set"])
            oid = ObjectId()
            new_doc.setdefault("_id", oid)
            self.docs.append(new_doc)
            return _FakeUpdateResult(matched_count=0, upserted_id=new_doc["_id"])
        return _FakeUpdateResult(matched_count=0)

    async def delete_one(self, query: dict) -> _FakeDeleteResult:
        for idx, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(idx)
                return _FakeDeleteResult(1)
        return _FakeDeleteResult(0)

    async def delete_many(self, query: dict) -> _FakeDeleteResult:
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not self._matches(doc, query)]
        return _FakeDeleteResult(before - len(self.docs))

    async def find_one_and_update(
        self, query: dict, update: dict, return_document: bool = True
    ) -> dict | None:
        doc = await self.find_one(query)
        if not doc:
            return None
        if "$set" in update:
            doc.update(update["$set"])
        return doc if return_document else None

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict):
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                if "$gte" in expected and (actual is None or actual < expected["$gte"]):
                    return False
                if "$lte" in expected and (actual is None or actual > expected["$lte"]):
                    return False
            elif actual != expected:
                return False
        return True


class _FakeDb:
    def __init__(
        self,
        habits: list[dict] | None = None,
        checkins: list[dict] | None = None,
        users: list[dict] | None = None,
        password_resets: list[dict] | None = None,
        email_verifications: list[dict] | None = None,
    ):
        self.habits = _FakeCollection(habits)
        self.checkins = _FakeCollection(checkins)
        self.users = _FakeCollection(users)
        self.password_resets = _FakeCollection(password_resets)
        self.email_verifications = _FakeCollection(email_verifications)


def test_sli_endpoint_and_habit_target_slo_via_testclient():
    user_oid = ObjectId()
    user_id = str(user_oid)
    ref = date(2026, 11, 14)

    existing_habit_oid = ObjectId()
    initial_habits = [
        {
            "_id": existing_habit_oid,
            "user_id": user_id,
            "title": "Morning Run",
            "description": "",
            "color": "#10B981",
            "icon": "check_circle",
            "frequency_type": "daily",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "monthly_mode": "from_start",
            "monthly_day": 1,
            "monthly_week": 1,
            "monthly_weekday": 0,
            "target_per_day": 1,
            "target_slo": 85.0,
            "archived": False,
            "created_at": datetime(2026, 11, 5, tzinfo=timezone.utc),
        }
    ]
    # 10 days (Nov 5..Nov 14): 9 completed, Nov 13 missed -> 90.0% SLI (>= 85.0% SLO)
    checkins = [
        {
            "user_id": user_id,
            "habit_id": str(existing_habit_oid),
            "date": (ref - timedelta(days=offset)).isoformat(),
            "completed": True,
        }
        for offset in range(10)
        if (ref - timedelta(days=offset)).isoformat() != "2026-11-13"
    ]
    fake_db = _FakeDb(habits=initial_habits, checkins=checkins)

    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: {
        "_id": user_oid,
        "name": "Shawn",
        "email": "shawn@example.com",
        "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
    }
    try:
        client = TestClient(app)
        # 1. Create a habit with custom target_slo
        create_resp = client.post(
            "/api/habits",
            json={"title": "Read 20 pages", "target_slo": 92.5},
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["target_slo"] == 92.5

        # 2. Update existing habit's target_slo via PATCH
        patch_resp = client.patch(
            f"/api/habits/{existing_habit_oid}",
            json={"target_slo": 95.0},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["target_slo"] == 95.0

        # 3. Fetch SLI dashboard and verify exact snake_case JSON contract
        sli_resp = client.get(
            "/api/stats/sli",
            params={"window_days": 30, "today": "2026-11-14"},
        )
        assert sli_resp.status_code == 200
        data = sli_resp.json()

        expected_top_keys = {
            "window_days",
            "active_habits_count",
            "overall_sli",
            "overall_target_slo",
            "overall_status",
            "healthy_count",
            "warning_count",
            "breached_count",
            "overall_error_budget_allowed_days",
            "overall_error_budget_used_days",
            "overall_error_budget_remaining_days",
            "overall_error_budget_remaining_pct",
            "overall_burn_rate",
            "overall_burn_rate_7d",
            "weakest_weekday",
            "weakest_weekday_sli",
            "top_burn_habit_title",
            "top_burn_rate",
            "trend",
            "weekday_sli",
            "habits",
        }
        assert expected_top_keys.issubset(data.keys())
        assert data["window_days"] == 30
        assert data["active_habits_count"] == 2
        assert data["weakest_weekday"] == "Fri"
        assert data["top_burn_habit_title"] == "Morning Run"
        assert len(data["trend"]) == 10
        assert len(data["weekday_sli"]) == 7

        # Morning Run now has target_slo=95.0 and 9/10 = 90.0% SLI -> breached
        morning_run = next(h for h in data["habits"] if h["title"] == "Morning Run")
        assert morning_run["target_slo"] == 95.0
        assert morning_run["current_sli"] == 90.0
        assert morning_run["status"] == "breached"
        assert morning_run["slo_met"] is False
    finally:
        app.dependency_overrides.clear()


def test_compute_period_bounds_week_and_month():
    assert compute_period_bounds("week", date(2026, 11, 14)) == (
        date(2026, 11, 9),
        date(2026, 11, 15),
    )
    assert compute_period_bounds("month", date(2026, 11, 14)) == (
        date(2026, 11, 1),
        date(2026, 11, 30),
    )
    assert compute_period_bounds("month", date(2028, 2, 10)) == (
        date(2028, 2, 1),
        date(2028, 2, 29),
    )


def test_build_period_schedule_daily_weekday_monthly_and_utc_created_at():
    today_date = date(2026, 11, 14)  # Saturday
    daily_id = ObjectId()
    mwf_id = ObjectId()
    monthly_id = ObjectId()
    evening_id = ObjectId()

    habits = [
        {
            "_id": daily_id,
            "title": "Water",
            "frequency_type": "daily",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "target_per_day": 2,
            "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
        },
        {
            "_id": mwf_id,
            "title": "Gym",
            "frequency_type": "weekdays",
            "weekdays": [0, 2, 4],
            "target_per_day": 1,
            "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
        },
        {
            "_id": monthly_id,
            "title": "Pay Rent",
            "frequency_type": "monthly",
            "monthly_mode": "from_start",
            "monthly_day": 15,
            "target_per_day": 1,
            "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
        },
        {
            # UTC creation date is 2026-11-15 (ahead of US evening local today 2026-11-14)
            "_id": evening_id,
            "title": "Evening Stretch",
            "frequency_type": "daily",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "target_per_day": 1,
            "created_at": datetime(2026, 11, 15, 3, 0, tzinfo=timezone.utc),
        },
    ]

    checkins_by_key = {
        (str(daily_id), "2026-11-09"): {"count": 2, "completed": True},
        (str(daily_id), "2026-11-14"): {"count": 1, "completed": False},
        (str(mwf_id), "2026-11-09"): {"count": 1, "completed": True},
        (str(mwf_id), "2026-11-11"): {"count": 1, "completed": True},
    }

    week = build_period_schedule(
        habits=habits,
        checkins_by_key=checkins_by_key,
        period="week",
        anchor_date=today_date,
        today_date=today_date,
    )
    assert week.start_date == "2026-11-09"
    assert week.end_date == "2026-11-15"
    # Water: 7 days (Nov 9 done, Nov 10-13 overdue=4, Nov 14 today, Nov 15 upcoming)
    # Gym: 3 days (Nov 9 & 11 done, Nov 13 overdue=1)
    # Pay Rent: 1 day (Nov 15 upcoming)
    # Evening Stretch: clamped to today 2026-11-14 -> 2 days (Nov 14 today, Nov 15 upcoming), 0 fake overdue
    assert week.total_scheduled == 7 + 3 + 1 + 2
    assert week.completed_count == 3
    assert week.overdue_count == 5
    assert week.remaining_count == 5
    assert week.total_scheduled == week.completed_count + week.overdue_count + week.remaining_count

    by_id = {s.habit_id: s for s in week.habit_summaries}
    assert by_id[str(daily_id)].overdue_days == 4
    assert by_id[str(daily_id)].remaining_days == 2
    assert by_id[str(daily_id)].next_due_date == "2026-11-14"
    assert by_id[str(mwf_id)].overdue_days == 1
    assert by_id[str(mwf_id)].remaining_days == 0
    assert by_id[str(mwf_id)].next_due_date == "2026-11-13"
    assert by_id[str(monthly_id)].scheduled_days == 1
    assert by_id[str(monthly_id)].next_due_date == "2026-11-15"
    assert by_id[str(evening_id)].scheduled_days == 2
    assert by_id[str(evening_id)].overdue_days == 0

    nov14 = next(d for d in week.days if d.date == "2026-11-14")
    assert nov14.is_today is True
    nov14_statuses = {it.title: it.status for it in nov14.items}
    assert nov14_statuses == {"Water": "today", "Evening Stretch": "today"}

    nov15 = next(d for d in week.days if d.date == "2026-11-15")
    assert nov15.is_future is True
    nov15_statuses = {it.title: it.status for it in nov15.items}
    assert nov15_statuses["Pay Rent"] == "upcoming"

    month = build_period_schedule(
        habits=[habits[1]],  # Gym Mon/Wed/Fri in Nov 2026 (13 total occurrences)
        checkins_by_key=checkins_by_key,
        period="month",
        anchor_date=today_date,
        today_date=today_date,
    )
    assert month.start_date == "2026-11-01"
    assert month.end_date == "2026-11-30"
    # Nov 2026 Mon/Wed/Fri: Nov 2,4,6,9,11,13 (6 before today; 2 completed -> 4 overdue) + Nov 16,18,20,23,25,27,30 (7 remaining)
    assert month.total_scheduled == 13
    assert month.completed_count == 2
    assert month.overdue_count == 4
    assert month.remaining_count == 7


def test_schedule_endpoint_via_testclient():
    user_oid = ObjectId()
    user_id = str(user_oid)
    gym_oid = ObjectId()
    rent_oid = ObjectId()

    habits = [
        {
            "_id": gym_oid,
            "user_id": user_id,
            "title": "Gym",
            "description": "Strength training",
            "color": "#6366F1",
            "icon": "check_circle",
            "frequency_type": "weekdays",
            "weekdays": [0, 2, 4],
            "target_per_day": 1,
            "archived": False,
            "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
        },
        {
            "_id": rent_oid,
            "user_id": user_id,
            "title": "Pay Rent",
            "description": "",
            "color": "#10B981",
            "icon": "check_circle",
            "frequency_type": "monthly",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "monthly_mode": "nth_weekday",
            "monthly_day": 1,
            "monthly_week": 3,
            "monthly_weekday": 6,  # 3rd Sunday = Nov 15, 2026
            "target_per_day": 1,
            "archived": False,
            "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
        },
    ]
    checkins = [
        {
            "user_id": user_id,
            "habit_id": str(gym_oid),
            "date": "2026-11-09",
            "count": 1,
            "completed": True,
            "note": "Good session",
        },
        {
            # Outside target week (Nov 9..Nov 15); verifies $gte/$lte filter
            "user_id": user_id,
            "habit_id": str(gym_oid),
            "date": "2026-11-02",
            "count": 1,
            "completed": True,
        },
    ]
    fake_db = _FakeDb(habits=habits, checkins=checkins)
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: {
        "_id": user_oid,
        "name": "Shawn",
        "email": "shawn@example.com",
        "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
    }
    try:
        client = TestClient(app)
        week_resp = client.get(
            "/api/habits/schedule",
            params={"period": "week", "anchor_date": "2026-11-14", "today": "2026-11-14"},
        )
        assert week_resp.status_code == 200
        week_data = week_resp.json()
        assert week_data["period"] == "week"
        assert week_data["start_date"] == "2026-11-09"
        assert week_data["end_date"] == "2026-11-15"
        assert week_data["total_scheduled"] == 4  # Gym Mon/Wed/Fri + Rent Sun Nov 15
        assert week_data["completed_count"] == 1
        assert week_data["overdue_count"] == 2  # Nov 11 & Nov 13
        assert week_data["remaining_count"] == 1  # Nov 15
        rent_summary = next(
            s for s in week_data["habit_summaries"] if s["title"] == "Pay Rent"
        )
        assert rent_summary["frequency_type"] == "monthly"
        assert rent_summary["monthly_mode"] == "nth_weekday"
        assert rent_summary["monthly_week"] == 3
        assert rent_summary["monthly_weekday"] == 6
        assert rent_summary["next_due_date"] == "2026-11-15"

        month_resp = client.get(
            "/api/habits/schedule",
            params={"period": "month", "anchor_date": "2026-11-14", "today": "2026-11-14"},
        )
        assert month_resp.status_code == 200
        month_data = month_resp.json()
        assert month_data["period"] == "month"
        assert month_data["completed_count"] == 2
        assert len(month_data["days"]) == 30
    finally:
        app.dependency_overrides.clear()


def _register_and_verify_user(
    client: TestClient,
    captured_codes: list[tuple[str, str, str]],
    *,
    name: str,
    email: str,
    password: str,
) -> dict:
    reg_resp = client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": password},
    )
    assert reg_resp.status_code == 201
    assert reg_resp.json()["verification_required"] is True
    assert "access_token" not in reg_resp.json()
    code = captured_codes[-1][2]
    verify_resp = client.post(
        "/api/auth/verify-email",
        json={"email": email, "code": code},
    )
    assert verify_resp.status_code == 200
    return verify_resp.json()


def test_forgot_and_reset_password_flow_and_token_invalidation(monkeypatch):
    fake_db = _FakeDb()
    sent_reset_codes: list[tuple[str, str, str]] = []
    sent_verify_codes: list[tuple[str, str, str]] = []

    async def fake_send_reset(
        to_email: str, user_name: str, code: str, _expire_minutes: int
    ):
        sent_reset_codes.append((to_email, user_name, code))

    async def fake_send_verify(
        to_email: str, user_name: str, code: str, _expire_minutes: int
    ):
        sent_verify_codes.append((to_email, user_name, code))

    monkeypatch.setattr(main_module, "send_password_reset_email", fake_send_reset)
    monkeypatch.setattr(
        main_module, "send_registration_verification_email", fake_send_verify
    )
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)

        verified_data = _register_and_verify_user(
            client,
            sent_verify_codes,
            name="Shawn",
            email="Shawn@Example.com",
            password="oldPassword1",
        )
        old_token = verified_data["access_token"]

        # Unknown email returns generic 200 without sending an email
        unknown_resp = client.post(
            "/api/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )
        assert unknown_resp.status_code == 200
        assert "If an account exists" in unknown_resp.json()["message"]
        assert unknown_resp.json()["dev_reset_code"] is None
        assert len(sent_reset_codes) == 0

        # Registered email triggers 6-digit code email and stores only HMAC hash
        forgot_resp = client.post(
            "/api/auth/forgot-password",
            json={"email": "shawn@example.com"},
        )
        assert forgot_resp.status_code == 200
        assert len(sent_reset_codes) == 1
        sent_to, sent_name, code = sent_reset_codes[0]
        assert sent_to == "shawn@example.com"
        assert sent_name == "Shawn"
        assert len(code) == 6 and code.isdigit()

        reset_record = next(
            d for d in fake_db.password_resets.docs if d["email"] == "shawn@example.com"
        )
        assert reset_record["code_hash"]
        assert code not in str(reset_record)

        # Wrong code fails with 400 and increments attempts
        wrong_code = "000000" if code != "000000" else "111111"
        bad_reset = client.post(
            "/api/auth/reset-password",
            json={
                "email": "shawn@example.com",
                "code": wrong_code,
                "new_password": "newPassword2",
            },
        )
        assert bad_reset.status_code == 400
        assert bad_reset.json()["detail"] == "Invalid or expired verification code"
        assert reset_record["attempts"] == 1

        # Valid code succeeds, returns rotated TokenResponse, and deletes reset record
        ok_reset = client.post(
            "/api/auth/reset-password",
            json={
                "email": "SHAWN@example.com",
                "code": f" {code} ",
                "new_password": "newPassword2",
            },
        )
        assert ok_reset.status_code == 200
        new_token = ok_reset.json()["access_token"]
        assert new_token != old_token
        assert not any(
            d["email"] == "shawn@example.com" for d in fake_db.password_resets.docs
        )

        # Code cannot be reused
        reuse_resp = client.post(
            "/api/auth/reset-password",
            json={
                "email": "shawn@example.com",
                "code": code,
                "new_password": "anotherPassword3",
            },
        )
        assert reuse_resp.status_code == 400

        # Old JWT is invalidated via token_version while new JWT works
        old_me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert old_me.status_code == 401

        new_me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert new_me.status_code == 200
        assert new_me.json()["email"] == "shawn@example.com"
        assert new_me.json()["email_verified"] is True

        # Old password rejected, new password accepted
        old_login = client.post(
            "/api/auth/login",
            json={"email": "shawn@example.com", "password": "oldPassword1"},
        )
        assert old_login.status_code == 401

        new_login = client.post(
            "/api/auth/login",
            json={"email": "shawn@example.com", "password": "newPassword2"},
        )
        assert new_login.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_reset_password_attempt_lockout_and_naive_utc_expiry(monkeypatch):
    fake_db = _FakeDb()
    sent_reset_codes: list[str] = []
    sent_verify_codes: list[tuple[str, str, str]] = []

    async def fake_send_reset(
        _to_email: str, _user_name: str, code: str, _expire_minutes: int
    ):
        sent_reset_codes.append(code)

    async def fake_send_verify(
        to_email: str, user_name: str, code: str, _expire_minutes: int
    ):
        sent_verify_codes.append((to_email, user_name, code))

    monkeypatch.setattr(main_module, "send_password_reset_email", fake_send_reset)
    monkeypatch.setattr(
        main_module, "send_registration_verification_email", fake_send_verify
    )
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        _register_and_verify_user(
            client,
            sent_verify_codes,
            name="Lock",
            email="lock@example.com",
            password="password1",
        )

        assert (
            client.post("/api/auth/forgot-password", json={"email": "lock@example.com"}).status_code
            == 200
        )
        valid_code = sent_reset_codes[-1]
        wrong_code = "000000" if valid_code != "000000" else "999999"

        for i in range(5):
            r = client.post(
                "/api/auth/reset-password",
                json={
                    "email": "lock@example.com",
                    "code": wrong_code,
                    "new_password": "newPassword1",
                },
            )
            assert r.status_code == 400
            if i == 4:
                assert "Too many failed attempts" in r.json()["detail"]

        # Attempt 6 with the real code is blocked
        locked = client.post(
            "/api/auth/reset-password",
            json={
                "email": "lock@example.com",
                "code": valid_code,
                "new_password": "newPassword1",
            },
        )
        assert locked.status_code == 400
        assert "Too many failed attempts" in locked.json()["detail"]

        # Requests 2..5 succeed, 6th request within 15 min window hits 429
        for _ in range(4):
            assert (
                client.post(
                    "/api/auth/forgot-password", json={"email": "lock@example.com"}
                ).status_code
                == 200
            )
        rate_limited = client.post(
            "/api/auth/forgot-password", json={"email": "lock@example.com"}
        )
        assert rate_limited.status_code == 429

        # Naive UTC datetime (as returned by PyMongo) in expires_at compares cleanly
        latest_code = sent_reset_codes[-1]
        record = next(d for d in fake_db.password_resets.docs if d["email"] == "lock@example.com")
        record["expires_at"] = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=1
        )
        expired_resp = client.post(
            "/api/auth/reset-password",
            json={
                "email": "lock@example.com",
                "code": latest_code,
                "new_password": "newPassword1",
            },
        )
        assert expired_resp.status_code == 400
        assert expired_resp.json()["detail"] == "Invalid or expired verification code"
    finally:
        app.dependency_overrides.clear()


def test_change_password_endpoint_and_session_rotation(monkeypatch):
    fake_db = _FakeDb()
    sent_verify_codes: list[tuple[str, str, str]] = []

    async def fake_send_verify(
        to_email: str, user_name: str, code: str, _expire_minutes: int
    ):
        sent_verify_codes.append((to_email, user_name, code))

    monkeypatch.setattr(
        main_module, "send_registration_verification_email", fake_send_verify
    )
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        verified_data = _register_and_verify_user(
            client,
            sent_verify_codes,
            name="Alice",
            email="alice@example.com",
            password="firstPassword",
        )
        token_v0 = verified_data["access_token"]

        # Wrong current password returns 400 (not 401)
        wrong_cur = client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {token_v0}"},
            json={"current_password": "wrongPassword", "new_password": "secondPassword"},
        )
        assert wrong_cur.status_code == 400
        assert wrong_cur.json()["detail"] == "Current password is incorrect"

        # Same password returns 400
        same_pwd = client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {token_v0}"},
            json={"current_password": "firstPassword", "new_password": "firstPassword"},
        )
        assert same_pwd.status_code == 400

        # Valid change returns rotated token and invalidates token_v0
        ok_change = client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {token_v0}"},
            json={"current_password": "firstPassword", "new_password": "secondPassword"},
        )
        assert ok_change.status_code == 200
        token_v1 = ok_change.json()["access_token"]
        assert token_v1 != token_v0

        assert (
            client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {token_v0}"}
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {token_v1}"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "alice@example.com", "password": "secondPassword"},
            ).status_code
            == 200
        )
    finally:
        app.dependency_overrides.clear()


def test_send_password_reset_email_dev_log_and_smtp_mock(monkeypatch, caplog):
    # 1. Local dev fallback logs warning when SMTP_HOST is empty
    dev_cfg = Settings(smtp_host="")
    with caplog.at_level(logging.WARNING, logger="habit_tracker.auth"):
        asyncio.run(
            send_password_reset_email(
                "dev@example.com", "Dev", "654321", 15, cfg=dev_cfg
            )
        )
    assert "654321" in caplog.text
    assert "dev@example.com" in caplog.text

    # 2. SMTP path calls STARTTLS, login, and send_message
    events: list[tuple] = []

    class _FakeSmtp:
        def __init__(self, host, port, timeout=None):
            events.append(("init", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            events.append(("ehlo",))

        def starttls(self, context=None):
            events.append(("starttls", context is not None))

        def login(self, user, pwd):
            events.append(("login", user, pwd))

        def send_message(self, msg):
            events.append(("send", msg["To"], msg["Subject"]))

    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    smtp_cfg = Settings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="mailer",
        smtp_password="secret",
        smtp_from_email="noreply@example.com",
        smtp_use_tls=True,
        smtp_use_ssl=False,
    )
    asyncio.run(
        send_password_reset_email("u@example.com", "User", "123456", 15, cfg=smtp_cfg)
    )
    assert ("init", "smtp.example.com", 587, 10) in events
    assert ("starttls", True) in events
    assert ("login", "mailer", "secret") in events
    assert ("send", "u@example.com", "Habit Tracker Password Reset Code: 123456") in events

    # 3. SMTP connection failure raises HTTP 502
    def _failing_smtp(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP", _failing_smtp)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            send_password_reset_email("u@example.com", "User", "123456", 15, cfg=smtp_cfg)
        )
    assert exc_info.value.status_code == 502


def test_register_email_verification_flow_and_unverified_login_blocked(monkeypatch):
    fake_db = _FakeDb()
    sent_verify_codes: list[tuple[str, str, str]] = []

    async def fake_send_verify(
        to_email: str, user_name: str, code: str, _expire_minutes: int
    ):
        sent_verify_codes.append((to_email, user_name, code))

    monkeypatch.setattr(
        main_module, "send_registration_verification_email", fake_send_verify
    )
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)

        reg_resp = client.post(
            "/api/auth/register",
            json={
                "name": "Shawn",
                "email": "Shawn@Example.com",
                "password": "secretPassword1",
            },
        )
        assert reg_resp.status_code == 201
        reg_body = reg_resp.json()
        assert reg_body["email"] == "shawn@example.com"
        assert reg_body["verification_required"] is True
        assert reg_body["expires_in_minutes"] == 15
        assert reg_body["dev_verification_code"] is None
        assert "access_token" not in reg_body

        assert len(sent_verify_codes) == 1
        sent_to, sent_name, code = sent_verify_codes[0]
        assert sent_to == "shawn@example.com"
        assert sent_name == "Shawn"
        assert len(code) == 6 and code.isdigit()

        user_doc = next(
            u for u in fake_db.users.docs if u["email"] == "shawn@example.com"
        )
        assert user_doc["email_verified"] is False

        verif_doc = next(
            d for d in fake_db.email_verifications.docs if d["email"] == "shawn@example.com"
        )
        assert verif_doc["code_hash"]
        assert code not in str(verif_doc)
        assert verif_doc["code_hash"] != hash_reset_code("shawn@example.com", code)

        # Wrong password still returns 401
        bad_pwd = client.post(
            "/api/auth/login",
            json={"email": "shawn@example.com", "password": "wrongPassword"},
        )
        assert bad_pwd.status_code == 401

        # Right password before verification returns 403
        unverified_login = client.post(
            "/api/auth/login",
            json={"email": "shawn@example.com", "password": "secretPassword1"},
        )
        assert unverified_login.status_code == 403
        assert "verify your email" in unverified_login.json()["detail"].lower()

        # Wrong verification code returns 400 and increments attempts
        wrong_code = "000000" if code != "000000" else "111111"
        bad_verify = client.post(
            "/api/auth/verify-email",
            json={"email": "shawn@example.com", "code": wrong_code},
        )
        assert bad_verify.status_code == 400
        assert verif_doc["attempts"] == 1

        # Valid verification code activates account, clears pending records, and returns JWT
        ok_verify = client.post(
            "/api/auth/verify-email",
            json={"email": "SHAWN@example.com", "code": f" {code} "},
        )
        assert ok_verify.status_code == 200
        verify_body = ok_verify.json()
        assert verify_body["user"]["email_verified"] is True
        token = verify_body["access_token"]
        assert user_doc["email_verified"] is True
        assert not any(
            d["email"] == "shawn@example.com" for d in fake_db.email_verifications.docs
        )

        # Login and authenticated routes work after verification
        me_resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["email_verified"] is True

        ok_login = client.post(
            "/api/auth/login",
            json={"email": "shawn@example.com", "password": "secretPassword1"},
        )
        assert ok_login.status_code == 200

        # Re-registering an already verified email returns 409 Conflict
        dup_reg = client.post(
            "/api/auth/register",
            json={
                "name": "Other",
                "email": "shawn@example.com",
                "password": "anotherPassword2",
            },
        )
        assert dup_reg.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_re_register_unverified_and_resend_verification_limits_and_legacy_users(monkeypatch):
    legacy_oid = ObjectId()
    fake_db = _FakeDb(
        users=[
            {
                "_id": legacy_oid,
                "name": "Legacy User",
                "email": "legacy@example.com",
                "password_hash": hash_password("legacyPass1"),
                "token_version": 0,
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ]
    )
    sent_verify_codes: list[str] = []

    async def fake_send_verify(
        _to_email: str, _user_name: str, code: str, _expire_minutes: int
    ):
        sent_verify_codes.append(code)

    monkeypatch.setattr(
        main_module, "send_registration_verification_email", fake_send_verify
    )
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)

        # 1. Legacy user document without `email_verified` field continues working seamlessly
        legacy_login = client.post(
            "/api/auth/login",
            json={"email": "legacy@example.com", "password": "legacyPass1"},
        )
        assert legacy_login.status_code == 200
        assert legacy_login.json()["user"]["email_verified"] is True
        legacy_me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {legacy_login.json()['access_token']}"},
        )
        assert legacy_me.status_code == 200

        # 2. Register unverified user, then re-register same unverified email with new name/password
        r1 = client.post(
            "/api/auth/register",
            json={"name": "Typo Name", "email": "retry@example.com", "password": "oldPassword1"},
        )
        assert r1.status_code == 201
        first_code = sent_verify_codes[-1]

        r2 = client.post(
            "/api/auth/register",
            json={"name": "Fixed Name", "email": "retry@example.com", "password": "newPassword2"},
        )
        assert r2.status_code == 201
        second_code = sent_verify_codes[-1]
        user_doc = next(u for u in fake_db.users.docs if u["email"] == "retry@example.com")
        assert user_doc["name"] == "Fixed Name"

        # Forged/stale token for an unverified account is blocked by get_current_user with 403
        stale_jwt = create_access_token(str(user_doc["_id"]), "retry@example.com", 0)
        blocked_me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {stale_jwt}"},
        )
        assert blocked_me.status_code == 403

        # 3. Resend verification up to window limit (sends 3, 4, 5 succeed; 6th returns 429)
        for _ in range(3):
            resend_ok = client.post(
                "/api/auth/resend-verification",
                json={"email": "retry@example.com"},
            )
            assert resend_ok.status_code == 200
        resend_limited = client.post(
            "/api/auth/resend-verification",
            json={"email": "retry@example.com"},
        )
        assert resend_limited.status_code == 429

        # First code is no longer valid after re-send/re-register replaced it
        latest_code = sent_verify_codes[-1]
        if first_code != latest_code:
            assert (
                client.post(
                    "/api/auth/verify-email",
                    json={"email": "retry@example.com", "code": first_code},
                ).status_code
                == 400
            )
            # Reset attempts so 5-attempt lockout check below starts cleanly
            next(
                d for d in fake_db.email_verifications.docs if d["email"] == "retry@example.com"
            )["attempts"] = 0

        # 4. Five wrong verification attempts lock out the active code cleanly
        wrong_code = "000000" if latest_code != "000000" else "999999"
        for i in range(5):
            bad_resp = client.post(
                "/api/auth/verify-email",
                json={"email": "retry@example.com", "code": wrong_code},
            )
            assert bad_resp.status_code == 400
            if i == 4:
                assert "Too many failed attempts" in bad_resp.json()["detail"]

        locked_resp = client.post(
            "/api/auth/verify-email",
            json={"email": "retry@example.com", "code": latest_code},
        )
        assert locked_resp.status_code == 400
        assert "Too many failed attempts" in locked_resp.json()["detail"]

        # 5. Rewind rate-limit window, verify naive UTC expiry check, then verify with fresh code
        verif_doc = next(
            d for d in fake_db.email_verifications.docs if d["email"] == "retry@example.com"
        )
        verif_doc["window_started_at"] = datetime.now(timezone.utc) - timedelta(minutes=20)
        assert (
            client.post(
                "/api/auth/resend-verification", json={"email": "retry@example.com"}
            ).status_code
            == 200
        )
        fresh_code = sent_verify_codes[-1]

        verif_doc["expires_at"] = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=1
        )
        assert (
            client.post(
                "/api/auth/verify-email",
                json={"email": "retry@example.com", "code": fresh_code},
            ).status_code
            == 400
        )

        verif_doc["expires_at"] = datetime.now(timezone.utc) + timedelta(minutes=15)
        verified_resp = client.post(
            "/api/auth/verify-email",
            json={"email": "retry@example.com", "code": fresh_code},
        )
        assert verified_resp.status_code == 200

        # Resend rejects already-verified accounts
        already_verified = client.post(
            "/api/auth/resend-verification",
            json={"email": "retry@example.com"},
        )
        assert already_verified.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_send_registration_verification_email_dev_log_and_smtp_mock(monkeypatch, caplog):
    # 1. Local dev fallback logs warning when SMTP_HOST is empty
    dev_cfg = Settings(smtp_host="")
    with caplog.at_level(logging.WARNING, logger="habit_tracker.auth"):
        asyncio.run(
            send_registration_verification_email(
                "dev@example.com", "Dev", "654321", 15, cfg=dev_cfg
            )
        )
    assert "DEV EMAIL VERIFICATION" in caplog.text
    assert "654321" in caplog.text
    assert "dev@example.com" in caplog.text

    # 2. SMTP path calls STARTTLS, login, and send_message
    events: list[tuple] = []

    class _FakeSmtp:
        def __init__(self, host, port, timeout=None):
            events.append(("init", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            events.append(("ehlo",))

        def starttls(self, context=None):
            events.append(("starttls", context is not None))

        def login(self, user, pwd):
            events.append(("login", user, pwd))

        def send_message(self, msg):
            events.append(("send", msg["To"], msg["Subject"]))

    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    smtp_cfg = Settings(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="mailer",
        smtp_password="secret",
        smtp_from_email="noreply@example.com",
        smtp_use_tls=True,
        smtp_use_ssl=False,
    )
    asyncio.run(
        send_registration_verification_email(
            "u@example.com", "User", "123456", 15, cfg=smtp_cfg
        )
    )
    assert ("init", "smtp.example.com", 587, 10) in events
    assert ("starttls", True) in events
    assert ("login", "mailer", "secret") in events
    assert (
        "send",
        "u@example.com",
        "Habit Tracker Email Verification Code: 123456",
    ) in events

    # 3. SMTP failure raises HTTP 502
    def _failing_smtp(*_args, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP", _failing_smtp)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            send_registration_verification_email(
                "u@example.com", "User", "123456", 15, cfg=smtp_cfg
            )
        )
    assert exc_info.value.status_code == 502


def test_normalize_reminder_times_valid_and_invalid():
    assert normalize_reminder_time("8:05") == "08:05"
    assert normalize_reminder_time(" 23:59 ") == "23:59"
    assert normalize_reminder_times(["21:00", "7:30", "07:30", "12:15"]) == [
        "07:30",
        "12:15",
        "21:00",
    ]

    for bad in ("24:00", "08:60", "invalid", "0800", "-1:00"):
        with pytest.raises(ValueError):
            normalize_reminder_time(bad)

    too_many = [f"{h:02d}:00" for h in range(13)]
    with pytest.raises(ValueError):
        normalize_reminder_times(too_many)


def test_habit_create_and_update_reminder_validation_and_legacy_defaults():
    # Enabled reminders must specify at least one time
    with pytest.raises(ValidationError):
        HabitCreate(title="Meditate", reminder_enabled=True, reminder_times=[])

    created = HabitCreate(
        title="Morning Alarm",
        reminder_enabled=True,
        reminder_times=["7:05", "20:00", "07:05"],
        reminder_mode="alarm",
        reminder_snooze_minutes=15,
        reminder_message="  Get moving!  ",
    )
    assert created.reminder_enabled is True
    assert created.reminder_times == ["07:05", "20:00"]
    assert created.reminder_mode == "alarm"
    assert created.reminder_snooze_minutes == 15
    assert created.reminder_message == "Get moving!"

    with pytest.raises(ValidationError):
        HabitUpdate(reminder_enabled=True, reminder_times=[])
    with pytest.raises(ValidationError):
        HabitUpdate(reminder_mode="siren")
    with pytest.raises(ValidationError):
        HabitUpdate(reminder_snooze_minutes=0)

    upd = HabitUpdate(reminder_times=["6:30"])
    assert upd.reminder_times == ["06:30"]

    # Legacy document without reminder fields serializes cleanly
    legacy_doc = {
        "_id": ObjectId(),
        "title": "Legacy Habit",
        "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
    }
    serialized = _serialize_habit(legacy_doc)
    assert serialized.reminder_enabled is False
    assert serialized.reminder_times == []
    assert serialized.reminder_mode == "notification"
    assert serialized.reminder_snooze_minutes == 10
    assert serialized.reminder_message == ""


def test_compute_next_reminder_occurrence_daily_weekly_monthly():
    daily_alarm = {
        "_id": "h_daily",
        "title": "Hydrate",
        "frequency_type": "daily",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "reminder_enabled": True,
        "reminder_times": ["08:00", "20:00"],
        "reminder_mode": "alarm",
    }
    # Same day with time remaining before 20:00
    assert compute_next_reminder_occurrence(
        daily_alarm, date(2026, 11, 16), now_hhmm="09:00", completed_today=False
    ) == ("2026-11-16", "20:00")
    # Same day past all times rolls to tomorrow 08:00
    assert compute_next_reminder_occurrence(
        daily_alarm, date(2026, 11, 16), now_hhmm="21:30", completed_today=False
    ) == ("2026-11-17", "08:00")
    # Completed today skips today even before 08:00
    assert compute_next_reminder_occurrence(
        daily_alarm, date(2026, 11, 16), now_hhmm="07:00", completed_today=True
    ) == ("2026-11-17", "08:00")

    # Weekday habit: Mon (0) and Wed (2); on Tuesday Nov 17 -> next is Wed Nov 18
    weekday_habit = {
        "_id": "h_wk",
        "title": "Run",
        "frequency_type": "weekdays",
        "weekdays": [0, 2],
        "reminder_enabled": True,
        "reminder_times": ["18:30"],
    }
    assert compute_next_reminder_occurrence(
        weekday_habit, date(2026, 11, 17), now_hhmm="08:00", completed_today=False
    ) == ("2026-11-18", "18:30")

    # Monthly 15th: on Nov 16 -> rolls to Dec 15
    monthly_habit = {
        "_id": "h_mo",
        "title": "Pay Rent",
        "frequency_type": "monthly",
        "monthly_mode": "from_start",
        "monthly_day": 15,
        "reminder_enabled": True,
        "reminder_times": ["09:00"],
    }
    assert compute_next_reminder_occurrence(
        monthly_habit, date(2026, 11, 16), now_hhmm="08:00", completed_today=False
    ) == ("2026-12-15", "09:00")


def test_reminders_crud_schedule_and_overview_endpoint():
    user_oid = ObjectId()
    user_id = str(user_oid)
    fake_db = _FakeDb()

    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: {
        "_id": user_oid,
        "name": "Shawn",
        "email": "shawn@example.com",
        "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
    }
    try:
        client = TestClient(app)

        # Create notification habit and alarm habit
        r1 = client.post(
            "/api/habits",
            json={
                "title": "Take Vitamins",
                "frequency_type": "daily",
                "reminder_enabled": True,
                "reminder_times": ["8:30", "21:00"],
                "reminder_mode": "notification",
                "reminder_snooze_minutes": 10,
                "reminder_message": "With water",
            },
        )
        assert r1.status_code == 201
        h1 = r1.json()
        assert h1["reminder_enabled"] is True
        assert h1["reminder_times"] == ["08:30", "21:00"]
        assert h1["reminder_mode"] == "notification"

        r2 = client.post(
            "/api/habits",
            json={
                "title": "Stretch",
                "frequency_type": "weekdays",
                "weekdays": [0, 2, 4],  # Mon, Wed, Fri
                "reminder_enabled": True,
                "reminder_times": ["7:00"],
                "reminder_mode": "alarm",
                "reminder_snooze_minutes": 5,
                "reminder_message": "Wake up!",
            },
        )
        assert r2.status_code == 201
        h2 = r2.json()
        assert h2["reminder_mode"] == "alarm"
        assert h2["reminder_times"] == ["07:00"]
        assert h2["reminder_snooze_minutes"] == 5

        # Partial PATCH without reminder fields must keep existing alarm settings
        patch_title = client.patch(
            f"/api/habits/{h2['id']}",
            json={"title": "Morning Stretch"},
        )
        assert patch_title.status_code == 200
        assert patch_title.json()["reminder_enabled"] is True
        assert patch_title.json()["reminder_times"] == ["07:00"]
        assert patch_title.json()["reminder_mode"] == "alarm"

        # Enabling reminders on a legacy/unconfigured habit without times returns 422
        r3 = client.post("/api/habits", json={"title": "No Times Yet"})
        assert r3.status_code == 201
        h3 = r3.json()
        bad_enable = client.patch(
            f"/api/habits/{h3['id']}",
            json={"reminder_enabled": True},
        )
        assert bad_enable.status_code == 422

        # Verify today & schedule endpoints carry reminder metadata
        today_resp = client.get("/api/habits/today?target_date=2026-11-16")
        assert today_resp.status_code == 200
        today_by_id = {it["id"]: it for it in today_resp.json()}
        assert today_by_id[h2["id"]]["reminder_mode"] == "alarm"
        assert today_by_id[h2["id"]]["reminder_times"] == ["07:00"]

        sched_resp = client.get(
            "/api/habits/schedule?period=week&anchor_date=2026-11-16&today=2026-11-16"
        )
        assert sched_resp.status_code == 200
        sched_summaries = {s["habit_id"]: s for s in sched_resp.json()["habit_summaries"]}
        assert sched_summaries[h1["id"]]["reminder_enabled"] is True
        assert sched_summaries[h1["id"]]["reminder_times"] == ["08:30", "21:00"]

        # Verify /api/habits/reminders at 2026-11-16 (Monday) 09:00
        ov_resp = client.get(
            "/api/habits/reminders?target_date=2026-11-16&now_time=9:00"
        )
        assert ov_resp.status_code == 200
        ov = ov_resp.json()
        assert ov["now_time"] == "09:00"
        assert ov["enabled_habits_count"] == 2
        assert ov["alarm_habits_count"] == 1
        assert ov["notification_habits_count"] == 1
        assert ov["scheduled_today_count"] == 2
        assert ov["pending_today_triggers"] == 1
        by_hid = {it["habit_id"]: it for it in ov["items"]}
        # Take Vitamins has 21:00 left today
        assert by_hid[h1["id"]]["next_trigger_date"] == "2026-11-16"
        assert by_hid[h1["id"]]["next_trigger_time"] == "21:00"
        assert by_hid[h1["id"]]["due_today_times"] == ["21:00"]
        # Morning Stretch (07:00 on Mon/Wed/Fri) already passed 09:00 -> Wed 2026-11-18
        assert by_hid[h2["id"]]["next_trigger_date"] == "2026-11-18"
        assert by_hid[h2["id"]]["next_trigger_time"] == "07:00"

        # Invalid now_time returns 400
        bad_time = client.get("/api/habits/reminders?now_time=99:99")
        assert bad_time.status_code == 400
    finally:
        app.dependency_overrides.clear()
