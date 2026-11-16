import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import flet as ft

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main  # noqa: E402
from test_reminders import _FakePage, _walk_controls  # noqa: E402


def _make_app() -> main.HabitTrackerApp:
    page = _FakePage()
    app = main.HabitTrackerApp(page)  # type: ignore[arg-type]
    app.api.current_user = {"id": "u1", "name": "Shawn", "email": "s@example.com"}
    app.api.token = "tok"
    app.render_shell = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    return app


def _collect_text_values(root: ft.Control) -> list[str]:
    return [
        str(c.value)
        for c in _walk_controls(root)
        if isinstance(c, ft.Text) and c.value is not None
    ]


class HabitModesUnitTests(unittest.TestCase):
    def test_validate_habit_mode_times(self) -> None:
        self.assertEqual(
            main.validate_habit_mode_times("free", "09:00", "10:00", "11:00"),
            (None, None, None, None),
        )
        self.assertEqual(
            main.validate_habit_mode_times("strict", "8:05", "08:30", "10:00"),
            ("08:05", "08:30", "10:00", None),
        )
        _, _, _, err1 = main.validate_habit_mode_times(
            "strict", "09:00", "08:30", "10:00"
        )
        self.assertIsNotNone(err1)
        _, _, _, err2 = main.validate_habit_mode_times(
            "window", "18:00", None, "17:00"
        )
        self.assertIsNotNone(err2)
        _, _, _, err3 = main.validate_habit_mode_times(
            "reminder", "99:99", None, None
        )
        self.assertIsNotNone(err3)

    def test_evaluate_local_habit_status_all_states(self) -> None:
        today_iso = "2026-11-15"
        strict_h = {
            "id": "h1",
            "title": "Deep Work",
            "scheduled_today": True,
            "target_per_day": 1,
            "count": 0,
            "completed": False,
            "mode": "strict",
            "remind_time": "09:00",
            "force_start_time": "09:15",
            "force_end_time": "10:30",
        }
        self.assertEqual(
            main.evaluate_local_habit_status(strict_h, today_iso, today_iso, "08:30"),
            ("pending", None, True, False),
        )
        self.assertEqual(
            main.evaluate_local_habit_status(strict_h, today_iso, today_iso, "09:05"),
            ("reminding", None, True, False),
        )
        self.assertEqual(
            main.evaluate_local_habit_status(strict_h, today_iso, today_iso, "09:16"),
            ("violation", "missed_start", False, False),
        )
        started = {**strict_h, "started_on_time": True, "started_at_time": "09:10"}
        self.assertEqual(
            main.evaluate_local_habit_status(started, today_iso, today_iso, "10:00"),
            ("in_progress", None, False, False),
        )
        self.assertEqual(
            main.evaluate_local_habit_status(started, today_iso, today_iso, "10:31"),
            ("violation", "missed_end", False, False),
        )
        ontime = {**started, "completed": True, "count": 1, "is_late": False}
        self.assertEqual(
            main.evaluate_local_habit_status(ontime, today_iso, today_iso, "22:00"),
            ("on_time", None, False, False),
        )
        makeup = {
            **strict_h,
            "completed": True,
            "count": 1,
            "is_late": True,
            "violation_reason": "missed_start",
        }
        self.assertEqual(
            main.evaluate_local_habit_status(makeup, today_iso, today_iso, "22:00"),
            ("late_makeup", "missed_start", False, True),
        )


class HabitModesUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_today_view_all_modes_states_and_strict_actions(self) -> None:
        app = _make_app()
        fixed_now = datetime(2026, 11, 15, 9, 10)
        today_iso = "2026-11-15"
        app.selected_date = date(2026, 11, 15)
        app.today_habits = [
            {
                "id": "h-strict-reminding",
                "title": "Mode1 Reminding",
                "color": "#6366F1",
                "target_per_day": 1,
                "scheduled_today": True,
                "count": 0,
                "completed": False,
                "current_streak": 2,
                "mode": "strict",
                "remind_time": "09:00",
                "force_start_time": "09:15",
                "force_end_time": "10:30",
            },
            {
                "id": "h-strict-inprog",
                "title": "Mode1 Running",
                "color": "#10B981",
                "target_per_day": 1,
                "scheduled_today": True,
                "count": 0,
                "completed": False,
                "started_on_time": True,
                "started_at_time": "08:50",
                "current_streak": 3,
                "mode": "strict",
                "remind_time": "08:30",
                "force_start_time": "09:00",
                "force_end_time": "11:00",
            },
            {
                "id": "h-strict-violation",
                "title": "Mode1 Violated",
                "color": "#EF4444",
                "target_per_day": 1,
                "scheduled_today": True,
                "count": 0,
                "completed": False,
                "current_streak": 0,
                "mode": "strict",
                "remind_time": "07:00",
                "force_start_time": "07:15",
                "force_end_time": "08:00",
            },
            {
                "id": "h-window-late",
                "title": "Mode2 Makeup",
                "color": "#F59E0B",
                "target_per_day": 1,
                "scheduled_today": True,
                "count": 1,
                "completed": True,
                "is_late": True,
                "violation_reason": "missed_end",
                "current_streak": 0,
                "mode": "window",
                "remind_time": "07:00",
                "force_end_time": "08:30",
            },
            {
                "id": "h-reminder-pending",
                "title": "Mode3 Evening",
                "color": "#0EA5E9",
                "target_per_day": 1,
                "scheduled_today": True,
                "count": 0,
                "completed": False,
                "current_streak": 1,
                "mode": "reminder",
                "remind_time": "20:00",
            },
            {
                "id": "h-window-done",
                "title": "Mode2 OnTime",
                "color": "#14B8A6",
                "target_per_day": 1,
                "scheduled_today": True,
                "count": 1,
                "completed": True,
                "is_late": False,
                "current_streak": 4,
                "mode": "window",
                "remind_time": "07:00",
                "force_end_time": "09:30",
            },
            {
                "id": "h-free-done",
                "title": "Free Done",
                "color": "#8B5CF6",
                "target_per_day": 1,
                "scheduled_today": True,
                "count": 1,
                "completed": True,
                "is_late": False,
                "current_streak": 5,
                "mode": "free",
            },
        ]

        updated_started = {
            **app.today_habits[0],
            "started_on_time": True,
            "started_at_time": "09:10",
            "day_status": "in_progress",
        }
        updated_makeup = {
            **app.today_habits[2],
            "count": 1,
            "completed": True,
            "is_late": True,
            "day_status": "late_makeup",
        }
        app.api.checkin_habit = AsyncMock(side_effect=[updated_started, updated_makeup])

        with patch.object(main, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            view = app._build_today_view()
            texts = _collect_text_values(view)
            # 2 on-time completed out of 7 scheduled (late makeup excluded!)
            self.assertIn("2 / 7 completed", texts)
            self.assertTrue(any("Overdue Make-up: 1" in t for t in texts))
            self.assertTrue(any("Violations: 1" in t for t in texts))
            self.assertIn("Reminding", texts)
            self.assertIn("In Progress", texts)
            self.assertIn("Violation", texts)
            self.assertIn("Overdue Make-up", texts)
            self.assertIn("On Time", texts)
            self.assertIn("Pending", texts)

            filled_btns = [
                c
                for c in _walk_controls(view)
                if isinstance(c, ft.FilledButton)
                and isinstance(getattr(c, "content", None), ft.Text)
            ]
            start_btn = next(b for b in filled_btns if b.content.value == "Start Execution")
            makeup_btn = next(b for b in filled_btns if b.content.value == "Overdue Make-up")

            await start_btn.on_click(None)
            self.assertEqual(app.api.checkin_habit.await_args.kwargs["action"], "start")
            self.assertEqual(
                app.api.checkin_habit.await_args.kwargs["habit_id"],
                "h-strict-reminding",
            )

            await makeup_btn.on_click(None)
            self.assertEqual(
                app.api.checkin_habit.await_args.kwargs["action"], "toggle"
            )
            self.assertEqual(
                app.api.checkin_habit.await_args.kwargs["habit_id"],
                "h-strict-violation",
            )

            # Check live phase transition notification fires once when entering reminding (20:00)
            phase_now = datetime(2026, 11, 15, 20, 0)
            await app._check_mode_phase_transitions(phase_now)
            toast_count = len(app.page.dialogs)  # type: ignore[attr-defined]
            self.assertGreaterEqual(toast_count, 1)
            await app._check_mode_phase_transitions(phase_now)
            self.assertEqual(
                len(app.page.dialogs), toast_count  # type: ignore[attr-defined]
            )

    async def test_schedule_stats_sli_habits_views_and_dialog_save(self) -> None:
        app = _make_app()
        app.api.create_habit = AsyncMock(return_value={"id": "h-new"})
        app.refresh_current_tab = AsyncMock()  # type: ignore[method-assign]
        today_iso = date.today().isoformat()
        now_dt = datetime(2026, 11, 15, 9, 10)

        # Schedule row with strict habit before force_start_time -> sends action="start"
        app.api.checkin_habit = AsyncMock(return_value={"id": "h-s"})
        with patch.object(main, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                date.today().year, date.today().month, date.today().day, 9, 10
            )
            row = app._build_schedule_day_item_row(
                {
                    "habit_id": "h-s",
                    "title": "Morning Focus",
                    "date": today_iso,
                    "completed": False,
                    "count": 0,
                    "target_per_day": 1,
                    "status": "today",
                    "mode": "strict",
                    "remind_time": "09:00",
                    "force_start_time": "23:59",
                    "force_end_time": "23:59",
                    "started_on_time": False,
                    "is_late": False,
                },
                is_future=False,
            )
            start_icon = next(
                c
                for c in _walk_controls(row)
                if isinstance(c, ft.IconButton) and c.tooltip == "Start Execution"
            )
            await start_icon.on_click(None)
            self.assertEqual(app.api.checkin_habit.await_args.kwargs["action"], "start")

        # Stats, Habits, SLI views render cleanly
        app.all_habits = [
            {
                "id": "h1",
                "title": "Deep Work",
                "color": "#6366F1",
                "frequency_type": "daily",
                "target_per_day": 1,
                "target_slo": 90.0,
                "mode": "strict",
                "remind_time": "08:30",
                "force_start_time": "08:45",
                "force_end_time": "10:00",
                "archived": False,
            }
        ]
        app.stats_summary = {
            "best_active_streak": 4,
            "overall_completion_rate_30d": 80.0,
            "completed_today": 1,
            "scheduled_today": 2,
            "late_today": 1,
            "violated_today": 0,
            "last_7_days": [
                {
                    "date": today_iso,
                    "weekday_label": "Sun",
                    "scheduled_count": 2,
                    "completed_count": 1,
                    "late_count": 1,
                }
            ],
            "habit_stats": [
                {
                    "habit_id": "h1",
                    "title": "Deep Work",
                    "color": "#6366F1",
                    "frequency_type": "daily",
                    "mode": "strict",
                    "current_streak": 0,
                    "best_streak": 4,
                    "completion_rate_30d": 80.0,
                    "total_completions": 8,
                    "late_completions": 1,
                }
            ],
        }
        app.sli_dashboard = {
            "window_days": 30,
            "active_habits_count": 1,
            "overall_sli": 80.0,
            "overall_target_slo": 85.0,
            "overall_status": "warning",
            "healthy_count": 0,
            "warning_count": 1,
            "breached_count": 0,
            "overall_error_budget_allowed_days": 4.5,
            "overall_error_budget_used_days": 2,
            "overall_error_budget_remaining_days": 2.5,
            "overall_error_budget_remaining_pct": 55.6,
            "overall_burn_rate": 0.44,
            "overall_burn_rate_7d": 0.5,
            "trend": [],
            "weekday_sli": [],
            "habits": [],
        }
        habits_view = app._build_habits_view()
        stats_view = app._build_stats_view()
        sli_view = app._build_sli_view()
        self.assertTrue(
            any("Mode 1" in t for t in _collect_text_values(habits_view))
        )
        self.assertTrue(
            any("8:30 AM" in t for t in _collect_text_values(habits_view))
        )
        stats_texts = _collect_text_values(stats_view)
        self.assertIn("+1 late", stats_texts)
        self.assertTrue(any("Make-ups: 1" in t for t in stats_texts))
        self.assertIsNotNone(sli_view)

        # Habit Dialog: switch to strict mode, validate ordering, then save payload
        app._open_habit_dialog()
        dlg = app.page.dialogs[-1]  # type: ignore[attr-defined]
        all_ctrls = list(_walk_controls(dlg))
        text_fields = {
            c.label: c for c in all_ctrls if isinstance(c, ft.TextField) and c.label
        }
        dropdowns = {
            c.label: c for c in all_ctrls if isinstance(c, ft.Dropdown) and c.label
        }
        save_btn = next(
            c
            for c in all_ctrls
            if isinstance(c, ft.FilledButton)
            and isinstance(getattr(c, "content", None), ft.Text)
            and c.content.value == "Save"
        )
        err_text = next(
            c
            for c in all_ctrls
            if isinstance(c, ft.Text) and c.color == ft.Colors.RED_600
        )

        text_fields["Habit Title"].value = "Strict Study"
        mode_dd = dropdowns["Habit Mode"]
        mode_dd.value = "strict"
        mode_dd.on_select(None)

        # Invalid time ordering rejected
        text_fields["Remind Time (HH:MM)"].value = "09:30"
        text_fields["Force Start Time (HH:MM)"].value = "09:15"
        text_fields["Force End Time (HH:MM)"].value = "10:30"
        await save_btn.on_click(None)
        self.assertTrue(err_text.visible)
        app.api.create_habit.assert_not_awaited()

        # Valid 12h AM/PM time ordering accepted (08:30 AM < 08:45 AM < 01:30 PM -> 13:30)
        text_fields["Remind Time (HH:MM)"].value = "08:30"
        dropdowns["Remind AM/PM"].value = "AM"
        text_fields["Force Start Time (HH:MM)"].value = "08:45"
        dropdowns["Start AM/PM"].value = "AM"
        text_fields["Force End Time (HH:MM)"].value = "01:30"
        dropdowns["End AM/PM"].value = "PM"
        dropdowns["Reminder Style"].value = "alarm"
        await save_btn.on_click(None)
        app.api.create_habit.assert_awaited_once()
        payload = app.api.create_habit.await_args.args[0]
        self.assertEqual(payload["mode"], "strict")
        self.assertEqual(payload["remind_time"], "08:30")
        self.assertEqual(payload["force_start_time"], "08:45")
        self.assertEqual(payload["force_end_time"], "13:30")
        self.assertTrue(payload["reminder_enabled"])
        self.assertEqual(payload["reminder_times"], ["08:30"])
        self.assertEqual(payload["reminder_mode"], "alarm")

        # Opening edit dialog pre-populates 12h values + AM/PM selectors cleanly
        app._open_habit_dialog(
            {
                "id": "h-edit",
                "title": "Afternoon Strict",
                "frequency_type": "daily",
                "mode": "strict",
                "remind_time": "13:00",
                "force_start_time": "13:15",
                "force_end_time": "21:30",
            }
        )
        edit_dlg = app.page.dialogs[-1]  # type: ignore[attr-defined]
        edit_ctrls = list(_walk_controls(edit_dlg))
        edit_tf = {c.label: c for c in edit_ctrls if isinstance(c, ft.TextField) and c.label}
        edit_dd = {c.label: c for c in edit_ctrls if isinstance(c, ft.Dropdown) and c.label}
        self.assertEqual(edit_tf["Remind Time (HH:MM)"].value, "01:00")
        self.assertEqual(edit_dd["Remind AM/PM"].value, "PM")
        self.assertEqual(edit_tf["Force Start Time (HH:MM)"].value, "01:15")
        self.assertEqual(edit_dd["Start AM/PM"].value, "PM")
        self.assertEqual(edit_tf["Force End Time (HH:MM)"].value, "09:30")
        self.assertEqual(edit_dd["End AM/PM"].value, "PM")


if __name__ == "__main__":
    unittest.main()
