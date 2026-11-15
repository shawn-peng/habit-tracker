from datetime import date, datetime, timezone

from app.core import compute_30d_completion_rate, compute_streaks, is_scheduled_on


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
