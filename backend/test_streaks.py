from datetime import date, datetime, timedelta, timezone

from bson import ObjectId
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.core import (
    HabitCreate,
    HabitUpdate,
    build_period_schedule,
    build_sli_dashboard,
    compute_30d_completion_rate,
    compute_burn_rate,
    compute_error_budget,
    compute_habit_sli,
    compute_period_bounds,
    compute_streaks,
    get_current_user,
    get_db,
    is_scheduled_on,
    scheduled_monthly_day,
)
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
    def __init__(self, habits: list[dict] | None = None, checkins: list[dict] | None = None):
        self.habits = _FakeCollection(habits)
        self.checkins = _FakeCollection(checkins)


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
