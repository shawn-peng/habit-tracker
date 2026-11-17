from datetime import date, datetime, timezone

from bson import ObjectId
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.core import HabitCreate, get_current_user, get_db
from app.main import app
from test_streaks import _FakeDb


def _make_client_and_db(
    *,
    habits: list[dict] | None = None,
    checkins: list[dict] | None = None,
) -> tuple[TestClient, _FakeDb, str]:
    user_oid = ObjectId()
    user_id = str(user_oid)
    fake_db = _FakeDb(habits=habits, checkins=checkins)
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: {
        "_id": user_oid,
        "name": "Shawn",
        "email": "shawn@example.com",
        "created_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
    }
    return TestClient(app), fake_db, user_id


def test_mode_schema_validation_and_patch_switching():
    # Valid modes & HH:MM normalization
    strict_h = HabitCreate(
        title="Morning Focus",
        mode="strict",
        remind_time="8:05",
        force_start_time="08:15",
        force_end_time="09:00",
    )
    assert strict_h.remind_time == "08:05"
    assert strict_h.force_start_time == "08:15"
    assert strict_h.force_end_time == "09:00"

    # Free mode clears any stray times
    free_h = HabitCreate(
        title="Free Habit",
        mode="free",
        remind_time="08:00",
        force_start_time="09:00",
        force_end_time="10:00",
    )
    assert (free_h.remind_time, free_h.force_start_time, free_h.force_end_time) == (
        None,
        None,
        None,
    )

    # Invalid formats & ordering
    for bad_kwargs in [
        {"mode": "reminder", "remind_time": None},
        {"mode": "reminder", "remind_time": "25:00"},
        {"mode": "window", "remind_time": "09:00", "force_end_time": None},
        {"mode": "window", "remind_time": "09:00", "force_end_time": "09:00"},
        {"mode": "window", "remind_time": "10:00", "force_end_time": "09:00"},
        {
            "mode": "strict",
            "remind_time": "08:00",
            "force_start_time": "08:00",
            "force_end_time": "09:00",
        },
        {
            "mode": "strict",
            "remind_time": "08:00",
            "force_start_time": "09:30",
            "force_end_time": "09:00",
        },
        {
            "mode": "strict",
            "remind_time": "08:00",
            "force_start_time": None,
            "force_end_time": "09:00",
        },
    ]:
        with pytest.raises(ValidationError):
            HabitCreate(title="Invalid", **bad_kwargs)

    # Endpoint PATCH transitions: strict -> window -> reminder -> free clears unused fields
    client, _db, _uid = _make_client_and_db()
    try:
        res = client.post(
            "/api/habits",
            json={
                "title": "Deep Work",
                "mode": "strict",
                "remind_time": "08:30",
                "force_start_time": "08:45",
                "force_end_time": "10:00",
            },
        )
        assert res.status_code == 201
        hid = res.json()["id"]

        # Reject bad partial update against existing force_start_time (09:00 >= 08:45)
        bad_patch = client.patch(f"/api/habits/{hid}", json={"remind_time": "09:00"})
        assert bad_patch.status_code == 422

        # Switch strict -> window clears force_start_time
        to_window = client.patch(f"/api/habits/{hid}", json={"mode": "window"})
        assert to_window.status_code == 200
        w_body = to_window.json()
        assert w_body["mode"] == "window"
        assert w_body["remind_time"] == "08:30"
        assert w_body["force_start_time"] is None
        assert w_body["force_end_time"] == "10:00"

        # Switch window -> reminder clears force_end_time
        to_reminder = client.patch(f"/api/habits/{hid}", json={"mode": "reminder"})
        assert to_reminder.status_code == 200
        r_body = to_reminder.json()
        assert r_body["mode"] == "reminder"
        assert r_body["remind_time"] == "08:30"
        assert r_body["force_start_time"] is None
        assert r_body["force_end_time"] is None

        # Switch reminder -> free clears remind_time
        to_free = client.patch(f"/api/habits/{hid}", json={"mode": "free"})
        assert to_free.status_code == 200
        f_body = to_free.json()
        assert f_body["mode"] == "free"
        assert f_body["remind_time"] is None
        assert f_body["force_start_time"] is None
        assert f_body["force_end_time"] is None
    finally:
        app.dependency_overrides.clear()


def test_strict_mode_happy_path_start_guard_and_note_preservation():
    client, db, uid = _make_client_and_db()
    today_str = "2026-11-15"
    try:
        create = client.post(
            "/api/habits",
            json={
                "title": "Code Sprint",
                "mode": "strict",
                "remind_time": "09:00",
                "force_start_time": "09:15",
                "force_end_time": "10:30",
            },
        )
        assert create.status_code == 201
        hid = create.json()["id"]

        # Seed yesterday's on-time completion so streak should climb 1 -> 2
        db.checkins.docs.append(
            {
                "_id": ObjectId(),
                "user_id": uid,
                "habit_id": hid,
                "date": "2026-11-14",
                "count": 1,
                "completed": True,
                "is_late": False,
            }
        )

        # 08:30 before remind_time -> pending, can_start=True
        early = client.get(
            "/api/habits/today",
            params={
                "target_date": today_str,
                "client_today": today_str,
                "client_time": "08:30",
            },
        )
        assert early.status_code == 200
        assert early.json()[0]["day_status"] == "pending"
        assert early.json()[0]["can_start"] is True

        # 09:05 inside remind window -> reminding, can_start=True
        rem = client.get(
            "/api/habits/today",
            params={
                "target_date": today_str,
                "client_today": today_str,
                "client_time": "09:05",
            },
        )
        assert rem.status_code == 200
        assert rem.json()[0]["day_status"] == "reminding"
        assert rem.json()[0]["can_start"] is True

        # Completing without clicking start returns 400
        blocked = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "toggle",
                "client_today": today_str,
                "client_time": "09:05",
            },
        )
        assert blocked.status_code == 400
        assert "Start Execution" in blocked.json()["detail"]

        # Note-only save while count=0 remains allowed
        note_only = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "set",
                "count": 0,
                "note": "Preparing desk",
                "client_today": today_str,
                "client_time": "09:06",
            },
        )
        assert note_only.status_code == 200
        assert note_only.json()["note"] == "Preparing desk"
        assert note_only.json()["day_status"] == "reminding"

        # Click Start Execution at exact force_start_time 09:15 -> in_progress
        started = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "start",
                "client_today": today_str,
                "client_time": "09:15",
            },
        )
        assert started.status_code == 200
        s_json = started.json()
        assert s_json["day_status"] == "in_progress"
        assert s_json["started_on_time"] is True
        assert s_json["started_at_time"] == "09:15"
        assert s_json["can_start"] is False
        assert s_json["completed"] is False

        # Complete at 10:30 (<= force_end_time) -> on_time, streak=2
        done = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "toggle",
                "client_today": today_str,
                "client_time": "10:30",
            },
        )
        assert done.status_code == 200
        d_json = done.json()
        assert d_json["completed"] is True
        assert d_json["is_late"] is False
        assert d_json["day_status"] == "on_time"
        assert d_json["current_streak"] == 2

        # Editing note later at 22:00 preserves on_time (must NOT flip to late_makeup)
        edit_note = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "set",
                "count": 1,
                "note": "Shipped feature",
                "client_today": today_str,
                "client_time": "22:00",
            },
        )
        assert edit_note.status_code == 200
        n_json = edit_note.json()
        assert n_json["day_status"] == "on_time"
        assert n_json["is_late"] is False
        assert n_json["note"] == "Shipped feature"
    finally:
        app.dependency_overrides.clear()


def test_strict_mode_missed_start_violation_makeup_and_separate_accounting():
    user_oid = ObjectId()
    uid = str(user_oid)
    hid_oid = ObjectId()
    hid = str(hid_oid)
    ref = date(2026, 11, 15)
    created_at = datetime(2026, 11, 13, tzinfo=timezone.utc)

    habits = [
        {
            "_id": hid_oid,
            "user_id": uid,
            "title": "Deep Study",
            "description": "",
            "color": "#6366F1",
            "icon": "check_circle",
            "frequency_type": "daily",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "target_per_day": 1,
            "target_slo": 85.0,
            "mode": "strict",
            "remind_time": "08:00",
            "force_start_time": "08:30",
            "force_end_time": "10:00",
            "archived": False,
            "created_at": created_at,
        }
    ]
    # 2 prior on-time days (Nov 13, Nov 14)
    checkins = [
        {
            "_id": ObjectId(),
            "user_id": uid,
            "habit_id": hid,
            "date": "2026-11-13",
            "count": 1,
            "completed": True,
            "is_late": False,
        },
        {
            "_id": ObjectId(),
            "user_id": uid,
            "habit_id": hid,
            "date": "2026-11-14",
            "count": 1,
            "completed": True,
            "is_late": False,
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
        today_str = ref.isoformat()

        # At 08:31 (> force_start_time 08:30) without start -> violation & missed_start & streak=0
        today_resp = client.get(
            "/api/habits/today",
            params={
                "target_date": today_str,
                "client_today": today_str,
                "client_time": "08:31",
            },
        )
        assert today_resp.status_code == 200
        item = today_resp.json()[0]
        assert item["day_status"] == "violation"
        assert item["violation_reason"] == "missed_start"
        assert item["can_start"] is False
        assert item["current_streak"] == 0
        assert item["best_streak"] == 2

        # Stats summary reflects violated_today=1 while before makeup
        stats_violated = client.get(
            "/api/stats/summary",
            params={"today": today_str, "client_time": "08:31"},
        ).json()
        assert stats_violated["violated_today"] == 1
        assert stats_violated["late_today"] == 0
        assert stats_violated["completed_today"] == 0

        # Trying action="start" after 08:30 fails with 400
        late_start = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "start",
                "client_today": today_str,
                "client_time": "08:35",
            },
        )
        assert late_start.status_code == 400

        # 1-click toggle works directly without separate start and records late_makeup
        makeup = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "toggle",
                "client_today": today_str,
                "client_time": "08:40",
            },
        )
        assert makeup.status_code == 200
        m_json = makeup.json()
        assert m_json["completed"] is True
        assert m_json["is_late"] is True
        assert m_json["day_status"] == "late_makeup"
        assert m_json["violation_reason"] == "missed_start"
        assert m_json["current_streak"] == 0

        # Verify separate accounting in Stats & SLI
        stats = client.get(
            "/api/stats/summary",
            params={"today": today_str, "client_time": "09:00"},
        ).json()
        assert stats["completed_today"] == 0
        assert stats["scheduled_today"] == 1
        assert stats["late_today"] == 1
        assert stats["violated_today"] == 0
        assert stats["best_active_streak"] == 0
        assert stats["last_7_days"][-1]["completed_count"] == 0
        assert stats["last_7_days"][-1]["late_count"] == 1
        h_stat = stats["habit_stats"][0]
        assert h_stat["total_completions"] == 2
        assert h_stat["late_completions"] == 1
        assert h_stat["current_streak"] == 0
        assert h_stat["best_streak"] == 2
        # 2 on-time out of 3 scheduled days = 66.7% (late makeup excluded)
        assert h_stat["completion_rate_30d"] == 66.7

        sli = client.get(
            "/api/stats/sli",
            params={"today": today_str, "client_time": "09:00", "window_days": 30},
        ).json()
        assert sli["habits"][0]["completed_days"] == 2
        assert sli["habits"][0]["scheduled_days"] == 3
        assert sli["habits"][0]["missed_days"] == 1
        assert sli["habits"][0]["current_sli"] == 66.7
        assert sli["habits"][0]["current_streak"] == 0
    finally:
        app.dependency_overrides.clear()


def test_strict_mode_missed_end_violation_and_multi_count_makeup():
    client, _db, _uid = _make_client_and_db()
    today_str = "2026-11-15"
    try:
        res = client.post(
            "/api/habits",
            json={
                "title": "Pomodoro Sets",
                "target_per_day": 2,
                "mode": "strict",
                "remind_time": "09:00",
                "force_start_time": "09:15",
                "force_end_time": "11:00",
            },
        )
        assert res.status_code == 201
        hid = res.json()["id"]

        # Start on time + finish 1/2 before 11:00 -> still in_progress
        s = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "start",
                "client_today": today_str,
                "client_time": "09:10",
            },
        )
        assert s.status_code == 200
        inc1 = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "increment",
                "client_today": today_str,
                "client_time": "10:00",
            },
        )
        assert inc1.status_code == 200
        assert inc1.json()["day_status"] == "in_progress"
        assert inc1.json()["count"] == 1

        # Cross 11:00 without finishing 2/2 -> violation (missed_end)
        after_end = client.get(
            "/api/habits/today",
            params={
                "target_date": today_str,
                "client_today": today_str,
                "client_time": "11:05",
            },
        )
        assert after_end.status_code == 200
        assert after_end.json()[0]["day_status"] == "violation"
        assert after_end.json()[0]["violation_reason"] == "missed_end"

        # Finish 2/2 late -> late_makeup with violation_reason="missed_end"
        inc2 = client.post(
            f"/api/habits/{hid}/checkin",
            json={
                "date": today_str,
                "action": "increment",
                "client_today": today_str,
                "client_time": "11:10",
            },
        )
        assert inc2.status_code == 200
        assert inc2.json()["day_status"] == "late_makeup"
        assert inc2.json()["is_late"] is True
        assert inc2.json()["violation_reason"] == "missed_end"
    finally:
        app.dependency_overrides.clear()


def test_window_and_reminder_modes_lifecycle():
    client, _db, _uid = _make_client_and_db()
    today_str = "2026-11-15"
    yesterday_str = "2026-11-14"
    try:
        win = client.post(
            "/api/habits",
            json={
                "title": "Evening Stretch",
                "mode": "window",
                "remind_time": "19:00",
                "force_end_time": "21:00",
            },
        ).json()
        rem = client.post(
            "/api/habits",
            json={
                "title": "Vitamins",
                "mode": "reminder",
                "remind_time": "08:00",
            },
        ).json()

        # Window habit at 19:30 -> reminding, no start required
        at_1930 = client.get(
            "/api/habits/today",
            params={
                "target_date": today_str,
                "client_today": today_str,
                "client_time": "19:30",
            },
        ).json()
        win_item = next(x for x in at_1930 if x["id"] == win["id"])
        rem_item = next(x for x in at_1930 if x["id"] == rem["id"])
        assert win_item["day_status"] == "reminding"
        assert win_item["can_start"] is False
        assert rem_item["day_status"] == "reminding"

        # Action="start" is rejected on window habit
        bad_start = client.post(
            f"/api/habits/{win['id']}/checkin",
            json={
                "date": today_str,
                "action": "start",
                "client_today": today_str,
                "client_time": "19:30",
            },
        )
        assert bad_start.status_code == 400

        # Complete window habit before 21:00 -> on_time
        win_ontime = client.post(
            f"/api/habits/{win['id']}/checkin",
            json={
                "date": today_str,
                "action": "toggle",
                "client_today": today_str,
                "client_time": "20:45",
            },
        ).json()
        assert win_ontime["day_status"] == "on_time"
        assert win_ontime["is_late"] is False

        # Past date (Nov 14): window habit is violation (missed_end) -> 1-click makeup = late_makeup
        win_past = client.post(
            f"/api/habits/{win['id']}/checkin",
            json={
                "date": yesterday_str,
                "action": "toggle",
                "client_today": today_str,
                "client_time": "09:00",
            },
        ).json()
        assert win_past["day_status"] == "late_makeup"
        assert win_past["violation_reason"] == "missed_end"
        assert win_past["is_late"] is True

        # Reminder mode on past date or late evening completes on_time without violation
        rem_late = client.post(
            f"/api/habits/{rem['id']}/checkin",
            json={
                "date": yesterday_str,
                "action": "toggle",
                "client_today": today_str,
                "client_time": "23:55",
            },
        ).json()
        assert rem_late["day_status"] == "on_time"
        assert rem_late["is_late"] is False
    finally:
        app.dependency_overrides.clear()


def test_normalize_reminder_time_accepts_am_pm_and_rejects_invalid():
    from app.core import normalize_reminder_time

    assert normalize_reminder_time("8:05 AM") == "08:05"
    assert normalize_reminder_time("12:00 AM") == "00:00"
    assert normalize_reminder_time("12:30 PM") == "12:30"
    assert normalize_reminder_time("9:15 pm") == "21:15"
    assert normalize_reminder_time("1:00pm") == "13:00"
    assert normalize_reminder_time("20:45") == "20:45"

    for bad in ("13:00 PM", "0:15 AM", "12:60 PM", "25:00", "invalid"):
        try:
            normalize_reminder_time(bad)
            raise AssertionError(f"Expected ValueError for {bad!r}")
        except ValueError:
            pass


def test_merged_habit_mode_and_reminders_sync():
    client, _db, _uid = _make_client_and_db()
    try:
        # 1. Strict mode automatically enables reminder_enabled & seeds reminder_times=[remind_time]
        r_strict = client.post(
            "/api/habits",
            json={
                "title": "Strict Alarm Sprint",
                "mode": "strict",
                "remind_time": "08:30",
                "force_start_time": "08:45",
                "force_end_time": "10:00",
                "reminder_mode": "alarm",
                "reminder_snooze_minutes": 15,
                "reminder_message": "Start sprint!",
            },
        )
        assert r_strict.status_code == 201
        strict_h = r_strict.json()
        assert strict_h["mode"] == "strict"
        assert strict_h["reminder_enabled"] is True
        assert strict_h["reminder_times"] == ["08:30"]
        assert strict_h["reminder_mode"] == "alarm"
        assert strict_h["reminder_snooze_minutes"] == 15

        # 2. Mode 3 ('reminder') with reminder_times and no explicit remind_time syncs remind_time=first time
        r_rem = client.post(
            "/api/habits",
            json={
                "title": "Hydrate Multi",
                "mode": "reminder",
                "reminder_times": ["20:30", "08:00"],
                "reminder_mode": "alarm",
                "reminder_snooze_minutes": 10,
                "reminder_message": "Drink water",
            },
        )
        assert r_rem.status_code == 201
        rem_h = r_rem.json()
        assert rem_h["mode"] == "reminder"
        assert rem_h["reminder_enabled"] is True
        assert rem_h["reminder_times"] == ["08:00", "20:30"]
        assert rem_h["remind_time"] == "08:00"
        assert rem_h["reminder_mode"] == "alarm"

        # Both appear in GET /api/habits/reminders with mode metadata
        ov_resp = client.get(
            "/api/habits/reminders?target_date=2026-11-16&now_time=07:30"
        )
        assert ov_resp.status_code == 200
        ov = ov_resp.json()
        assert ov["enabled_habits_count"] == 2
        assert ov["alarm_habits_count"] == 2
        by_id = {it["habit_id"]: it for it in ov["items"]}
        assert by_id[strict_h["id"]]["mode"] == "strict"
        assert by_id[strict_h["id"]]["remind_time"] == "08:30"
        assert by_id[strict_h["id"]]["force_start_time"] == "08:45"
        assert by_id[strict_h["id"]]["force_end_time"] == "10:00"
        assert by_id[rem_h["id"]]["mode"] == "reminder"
        assert by_id[rem_h["id"]]["next_trigger_time"] == "08:00"

        # 3. Switching strict -> free disables reminders and removes it from overview
        to_free = client.patch(
            f"/api/habits/{strict_h['id']}",
            json={"mode": "free"},
        )
        assert to_free.status_code == 200
        free_h = to_free.json()
        assert free_h["mode"] == "free"
        assert free_h["reminder_enabled"] is False
        assert free_h["reminder_times"] == []
        assert free_h["remind_time"] is None
        assert free_h["force_start_time"] is None
        assert free_h["force_end_time"] is None

        ov_after = client.get(
            "/api/habits/reminders?target_date=2026-11-16&now_time=07:30"
        )
        assert ov_after.status_code == 200
        assert ov_after.json()["enabled_habits_count"] == 1
        assert [it["habit_id"] for it in ov_after.json()["items"]] == [rem_h["id"]]
    finally:
        app.dependency_overrides.clear()


def test_checkin_history_edit_overrides_validation_and_streaks_sli():
    user_oid = ObjectId()
    uid = str(user_oid)
    strict_oid = ObjectId()
    strict_id = str(strict_oid)
    window_oid = ObjectId()
    window_id = str(window_oid)
    created_at = datetime(2026, 11, 12, 8, 0, tzinfo=timezone.utc)

    habits = [
        {
            "_id": strict_oid,
            "user_id": uid,
            "title": "Morning Focus",
            "description": "",
            "color": "#6366F1",
            "icon": "check_circle",
            "frequency_type": "daily",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "target_per_day": 1,
            "target_slo": 85.0,
            "mode": "strict",
            "remind_time": "08:00",
            "force_start_time": "08:15",
            "force_end_time": "09:30",
            "archived": False,
            "created_date": "2026-11-12",
            "created_at": created_at,
        },
        {
            "_id": window_oid,
            "user_id": uid,
            "title": "Water Glasses",
            "description": "",
            "color": "#0EA5E9",
            "icon": "check_circle",
            "frequency_type": "daily",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "target_per_day": 3,
            "target_slo": 85.0,
            "mode": "window",
            "remind_time": "09:00",
            "force_end_time": "21:00",
            "archived": False,
            "created_date": "2026-11-12",
            "created_at": created_at,
        },
    ]
    checkins = [
        {
            "_id": ObjectId(),
            "user_id": uid,
            "habit_id": strict_id,
            "date": "2026-11-12",
            "count": 1,
            "completed": True,
            "is_late": False,
        },
        {
            "_id": ObjectId(),
            "user_id": uid,
            "habit_id": strict_id,
            "date": "2026-11-13",
            "count": 1,
            "completed": True,
            "is_late": False,
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
        today_str = "2026-11-15"

        # Viewing pre-creation date returns can_edit=False and pending (no violation)
        pre_day = client.get(
            "/api/habits/today",
            params={
                "target_date": "2026-11-11",
                "client_today": today_str,
                "client_time": "10:00",
            },
        )
        assert pre_day.status_code == 200
        assert all(item["can_edit"] is False for item in pre_day.json())
        assert all(item["day_status"] == "pending" for item in pre_day.json())

        # Override missed strict day (Nov 14) to On Time & mark Nov 15 On Time -> 4-day streak
        fix_nov14 = client.post(
            f"/api/habits/{strict_id}/checkin",
            json={
                "date": "2026-11-14",
                "action": "edit",
                "count": 1,
                "note": "Forgot to log yesterday",
                "status_override": "on_time",
                "client_today": today_str,
                "client_time": "10:00",
            },
        )
        assert fix_nov14.status_code == 200
        f14 = fix_nov14.json()
        assert f14["completed"] is True
        assert f14["is_late"] is False
        assert f14["started_on_time"] is True
        assert f14["day_status"] == "on_time"
        assert f14["note"] == "Forgot to log yesterday"
        assert f14["current_streak"] == 3

        fix_nov15 = client.post(
            f"/api/habits/{strict_id}/checkin",
            json={
                "date": today_str,
                "action": "edit",
                "count": 1,
                "status_override": "on_time",
                "client_today": today_str,
                "client_time": "10:00",
            },
        )
        assert fix_nov15.status_code == 200
        assert fix_nov15.json()["current_streak"] == 4

        sli_full = client.get(
            "/api/stats/sli",
            params={"today": today_str, "client_time": "10:00", "window_days": 30},
        ).json()
        strict_sli = next(h for h in sli_full["habits"] if h["habit_id"] == strict_id)
        assert strict_sli["current_sli"] == 100.0
        assert strict_sli["current_streak"] == 4

        # Downgrade Nov 13 to Overdue Make-up -> excluded from streak & SLI
        late_nov13 = client.post(
            f"/api/habits/{strict_id}/checkin",
            json={
                "date": "2026-11-13",
                "action": "edit",
                "count": 1,
                "note": "Actually finished late",
                "status_override": "late_makeup",
                "client_today": today_str,
                "client_time": "10:00",
            },
        )
        assert late_nov13.status_code == 200
        l13 = late_nov13.json()
        assert l13["completed"] is True
        assert l13["is_late"] is True
        assert l13["day_status"] == "late_makeup"
        assert l13["note"] == "Actually finished late"

        stats_after = client.get(
            "/api/stats/summary",
            params={"today": today_str, "client_time": "10:00"},
        ).json()
        strict_stat = next(
            s for s in stats_after["habit_stats"] if s["habit_id"] == strict_id
        )
        assert strict_stat["current_streak"] == 2  # Nov 14, 15
        assert strict_stat["total_completions"] == 3  # Nov 12, 14, 15
        assert strict_stat["late_completions"] == 1  # Nov 13
        assert strict_stat["completion_rate_30d"] == 75.0

        # Multi-count edit: partial clear keeps note & count, full clear deletes document
        partial = client.post(
            f"/api/habits/{window_id}/checkin",
            json={
                "date": "2026-11-14",
                "action": "edit",
                "count": 2,
                "note": "2/3 glasses",
                "status_override": "clear",
                "client_today": today_str,
                "client_time": "10:00",
            },
        )
        assert partial.status_code == 200
        assert partial.json()["completed"] is False
        assert partial.json()["count"] == 2
        assert partial.json()["note"] == "2/3 glasses"

        cleared = client.post(
            f"/api/habits/{window_id}/checkin",
            json={
                "date": "2026-11-14",
                "action": "edit",
                "count": 0,
                "note": "",
                "status_override": "clear",
                "client_today": today_str,
                "client_time": "10:00",
            },
        )
        assert cleared.status_code == 200
        assert cleared.json()["count"] == 0
        assert not any(
            d["habit_id"] == window_id and d["date"] == "2026-11-14"
            for d in fake_db.checkins.docs
        )

        # Validation errors -> 400
        for bad_payload in [
            {
                "date": "2026-11-16",
                "action": "edit",
                "count": 1,
                "status_override": "on_time",
            },
            {
                "date": "2026-11-11",
                "action": "edit",
                "count": 1,
                "status_override": "on_time",
            },
            {
                "date": "2026-11-14",
                "action": "edit",
                "count": 2,
                "status_override": "on_time",
            },
            {
                "date": "2026-11-14",
                "action": "edit",
                "count": 0,
                "status_override": "late_makeup",
            },
            {
                "date": "2026-11-14",
                "action": "edit",
                "count": 3,
                "status_override": "clear",
            },
        ]:
            target_hid = window_id if bad_payload["count"] in (2, 3) else strict_id
            resp = client.post(
                f"/api/habits/{target_hid}/checkin",
                json={
                    **bad_payload,
                    "client_today": today_str,
                    "client_time": "10:00",
                },
            )
            assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_habit_history_endpoint_calendar_states_and_bounds():
    user_oid = ObjectId()
    uid = str(user_oid)
    hid_oid = ObjectId()
    hid = str(hid_oid)
    oct_oid = ObjectId()
    oct_id = str(oct_oid)

    habits = [
        {
            "_id": hid_oid,
            "user_id": uid,
            "title": "MWF Gym",
            "description": "",
            "color": "#10B981",
            "icon": "check_circle",
            "frequency_type": "weekdays",
            "weekdays": [0, 2, 4],  # Mon, Wed, Fri
            "target_per_day": 1,
            "target_slo": 85.0,
            "mode": "strict",
            "remind_time": "09:00",
            "force_start_time": "09:15",
            "force_end_time": "11:00",
            "archived": False,
            "created_date": "2026-11-04",
            "created_at": datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc),
        },
        {
            "_id": oct_oid,
            "user_id": uid,
            "title": "October Daily",
            "description": "",
            "color": "#6366F1",
            "icon": "check_circle",
            "frequency_type": "daily",
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "target_per_day": 1,
            "target_slo": 85.0,
            "mode": "free",
            "archived": False,
            "created_date": "2026-10-15",
            "created_at": datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc),
        },
    ]
    checkins = [
        {
            "_id": ObjectId(),
            "user_id": uid,
            "habit_id": hid,
            "date": "2026-11-04",
            "count": 1,
            "completed": True,
            "is_late": False,
        },
        {
            "_id": ObjectId(),
            "user_id": uid,
            "habit_id": hid,
            "date": "2026-11-06",
            "count": 1,
            "completed": True,
            "is_late": True,
            "violation_reason": "missed_start",
        },
        {
            "_id": ObjectId(),
            "user_id": uid,
            "habit_id": hid,
            "date": "2026-11-11",
            "count": 1,
            "completed": True,
            "is_late": False,
            "note": "Great session",
        },
        {
            "_id": ObjectId(),
            "user_id": uid,
            "habit_id": hid,
            "date": "2026-11-13",
            "count": 1,
            "completed": True,
            "is_late": False,
        },
    ]
    fake_db = _FakeDb(habits=habits, checkins=checkins)
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: {
        "_id": user_oid,
        "name": "Shawn",
        "email": "shawn@example.com",
        "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
    }

    try:
        client = TestClient(app)
        resp = client.get(
            f"/api/habits/{hid}/history",
            params={
                "month": "2026-11",
                "client_today": "2026-11-16",
                "client_time": "09:05",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_date"] == "2026-11-04"
        assert body["can_prev_month"] is False
        assert body["can_next_month"] is False
        assert body["month_scheduled"] == 6  # Nov 4, 6, 9, 11, 13, 16
        assert body["month_completed_on_time"] == 3
        assert body["month_late_makeups"] == 1
        assert body["month_missed"] == 1  # Nov 9
        assert body["total_completions"] == 3
        assert body["late_completions"] == 1
        assert body["current_streak"] == 2
        assert body["best_streak"] == 2

        by_date = {d["date"]: d for d in body["days"]}
        assert by_date["2026-11-01"]["state"] == "before_created"
        assert by_date["2026-11-01"]["editable"] is False
        assert by_date["2026-11-03"]["state"] == "before_created"
        assert by_date["2026-11-04"]["state"] == "on_time"
        assert by_date["2026-11-04"]["editable"] is True
        assert by_date["2026-11-05"]["state"] == "unscheduled"
        assert by_date["2026-11-06"]["state"] == "late_makeup"
        assert by_date["2026-11-09"]["state"] == "missed"
        assert by_date["2026-11-11"]["note"] == "Great session"
        assert by_date["2026-11-16"]["state"] == "reminding"
        assert by_date["2026-11-16"]["is_today"] is True
        assert by_date["2026-11-17"]["state"] == "future"
        assert by_date["2026-11-17"]["editable"] is False

        # Month navigation bounds for October-created habit
        nov_oct = client.get(
            f"/api/habits/{oct_id}/history",
            params={
                "month": "2026-11",
                "client_today": "2026-11-16",
                "client_time": "09:05",
            },
        ).json()
        assert nov_oct["can_prev_month"] is True
        assert nov_oct["can_next_month"] is False

        oct_oct = client.get(
            f"/api/habits/{oct_id}/history",
            params={
                "month": "2026-10",
                "client_today": "2026-11-16",
                "client_time": "09:05",
            },
        ).json()
        assert oct_oct["can_prev_month"] is False
        assert oct_oct["can_next_month"] is True

        # Invalid month format rejected
        assert (
            client.get(f"/api/habits/{hid}/history?month=2026-13").status_code == 400
        )
        assert client.get(f"/api/habits/{hid}/history?month=invalid").status_code == 400
    finally:
        app.dependency_overrides.clear()
