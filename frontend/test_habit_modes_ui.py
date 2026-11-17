import inspect
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
            (c.label or c.data): c
            for c in all_ctrls
            if isinstance(c, ft.TextField) and (c.label or c.data)
        }
        dropdowns = {
            c.label: c for c in all_ctrls if isinstance(c, ft.Dropdown) and c.label
        }
        meridiems = {
            c.data["name"]: c.data["toggle"]
            for c in all_ctrls
            if isinstance(c, ft.Container)
            and isinstance(getattr(c, "data", None), dict)
            and c.data.get("role") == "meridiem"
        }
        meridiem_pills = {
            (c.data["group"], c.data["meridiem_option"]): c
            for c in all_ctrls
            if isinstance(c, ft.Container)
            and isinstance(getattr(c, "data", None), dict)
            and "meridiem_option" in c.data
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

        # Time fields use concise headers instead of clipped floating labels, and 1-tap AM/PM pills replace dropdowns
        self.assertIsNone(text_fields["Remind Time (HH:MM)"].label)
        self.assertIsNone(text_fields["Force Start Time (HH:MM)"].label)
        self.assertIsNone(text_fields["Force End Time (HH:MM)"].label)
        self.assertNotIn("Remind AM/PM", dropdowns)
        self.assertNotIn("Start AM/PM", dropdowns)
        self.assertNotIn("End AM/PM", dropdowns)
        self.assertEqual(set(meridiems.keys()), {"Remind AM/PM", "Start AM/PM", "End AM/PM", "Add Time AM/PM"})

        text_fields["Habit Title"].value = "Strict Study"
        mode_dd = dropdowns["Habit Mode"]
        mode_dd.value = "strict"
        mode_dd.on_select(None)

        # Invalid time ordering rejected
        text_fields["Remind Time (HH:MM)"].value = "09:30"
        text_fields["Force Start Time (HH:MM)"].value = "09:15"
        text_fields["Force End Time (HH:MM)"].value = "10:30"
        meridiem_pills[("End AM/PM", "AM")].on_click(None)
        await save_btn.on_click(None)
        self.assertTrue(err_text.visible)
        app.api.create_habit.assert_not_awaited()

        # Valid 12h AM/PM time ordering via 1-tap pill toggle (08:30 AM < 08:45 AM < 01:30 PM -> 13:30)
        text_fields["Remind Time (HH:MM)"].value = "08:30"
        meridiem_pills[("Remind AM/PM", "AM")].on_click(None)
        text_fields["Force Start Time (HH:MM)"].value = "08:45"
        meridiem_pills[("Start AM/PM", "AM")].on_click(None)
        text_fields["Force End Time (HH:MM)"].value = "01:30"
        meridiem_pills[("End AM/PM", "PM")].on_click(None)
        self.assertEqual(meridiems["End AM/PM"].value, "PM")
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

        # Opening edit dialog pre-populates 12h values + AM/PM pill toggles cleanly
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
        edit_tf = {
            (c.label or c.data): c
            for c in edit_ctrls
            if isinstance(c, ft.TextField) and (c.label or c.data)
        }
        edit_meridiems = {
            c.data["name"]: c.data["toggle"]
            for c in edit_ctrls
            if isinstance(c, ft.Container)
            and isinstance(getattr(c, "data", None), dict)
            and c.data.get("role") == "meridiem"
        }
        self.assertEqual(edit_tf["Remind Time (HH:MM)"].value, "01:00")
        self.assertEqual(edit_meridiems["Remind AM/PM"].value, "PM")
        self.assertEqual(edit_tf["Force Start Time (HH:MM)"].value, "01:15")
        self.assertEqual(edit_meridiems["Start AM/PM"].value, "PM")
        self.assertEqual(edit_tf["Force End Time (HH:MM)"].value, "09:30")
        self.assertEqual(edit_meridiems["End AM/PM"].value, "PM")

    async def test_companion_reminder_badge_and_weekly_chips_save(self) -> None:
        # Companion reminder badge avoids duplicating remind_time shown in mode_summary
        self.assertIsNone(
            main.format_companion_reminder_badge(
                {
                    "mode": "strict",
                    "remind_time": "08:30",
                    "reminder_times": ["08:30"],
                    "reminder_mode": "notification",
                }
            )
        )
        self.assertEqual(
            main.format_companion_reminder_badge(
                {
                    "mode": "window",
                    "remind_time": "08:30",
                    "reminder_times": ["08:30"],
                    "reminder_mode": "alarm",
                }
            ),
            "⏰ Alarm",
        )
        self.assertEqual(
            main.format_companion_reminder_badge(
                {
                    "mode": "reminder",
                    "remind_time": "09:00",
                    "reminder_times": ["09:00", "20:00"],
                    "reminder_mode": "notification",
                }
            ),
            "🔔 9:00 AM, 8:00 PM",
        )

        # Weekly schedule chips & presets persist selected weekdays cleanly
        app = _make_app()
        app.api.create_habit = AsyncMock(return_value={"id": "h-wk"})
        app.refresh_current_tab = AsyncMock()  # type: ignore[method-assign]
        app._open_habit_dialog()
        dlg = app.page.dialogs[-1]  # type: ignore[attr-defined]
        all_ctrls = list(_walk_controls(dlg))
        text_fields = {
            (c.label or c.data): c
            for c in all_ctrls
            if isinstance(c, ft.TextField) and (c.label or c.data)
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

        text_fields["Habit Title"].value = "Workday Standup"
        sched_dd = dropdowns["Schedule Frequency"]
        sched_dd.value = "weekdays"
        sched_dd.on_select(None)

        chips = {
            c.label.value: c
            for c in _walk_controls(dlg)
            if isinstance(c, ft.Chip) and isinstance(getattr(c, "label", None), ft.Text)
        }
        chips["Weekdays"].on_select(None)
        # Re-read chips after rebuild and toggle Fri off -> Mon..Thu ([0, 1, 2, 3])
        chips = {
            c.label.value: c
            for c in _walk_controls(dlg)
            if isinstance(c, ft.Chip) and isinstance(getattr(c, "label", None), ft.Text)
        }
        chips["Fri"].on_select(None)

        await save_btn.on_click(None)
        app.api.create_habit.assert_awaited_once()
        payload = app.api.create_habit.await_args.args[0]
        self.assertEqual(payload["frequency_type"], "weekdays")
        self.assertEqual(payload["weekdays"], [0, 1, 2, 3])
        self.assertEqual(payload["created_date"], date.today().isoformat())

    async def test_checkin_edit_dialog_and_pre_creation_today_view(self) -> None:
        app = _make_app()
        app.selected_date = date(2026, 11, 15)
        app.today_habits = [
            {
                "id": "h-editable",
                "title": "Read 20 Pages",
                "color": "#6366F1",
                "target_per_day": 2,
                "scheduled_today": True,
                "count": 0,
                "completed": False,
                "is_late": False,
                "note": "",
                "current_streak": 0,
                "mode": "strict",
                "created_date": "2026-11-10",
                "can_edit": True,
            },
            {
                "id": "h-future-created",
                "title": "Created Tomorrow",
                "color": "#10B981",
                "target_per_day": 1,
                "scheduled_today": True,
                "count": 0,
                "completed": False,
                "is_late": False,
                "note": "",
                "current_streak": 0,
                "mode": "strict",
                "created_date": "2026-11-16",
                "can_edit": False,
            },
        ]

        updated_item = {
            **app.today_habits[0],
            "count": 2,
            "completed": True,
            "is_late": True,
            "note": "Made up",
            "day_status": "late_makeup",
        }
        app.api.checkin_habit = AsyncMock(return_value=updated_item)
        app.refresh_current_tab = AsyncMock()  # type: ignore[method-assign]

        view = app._build_today_view()
        texts = _collect_text_values(view)
        self.assertIn("0 / 1 completed", texts)
        self.assertIn("Created 2026-11-16", texts)

        edit_btns = [
            c
            for c in _walk_controls(view)
            if isinstance(c, ft.IconButton) and c.tooltip == "Edit check-in"
        ]
        self.assertEqual(len(edit_btns), 1)
        edit_btns[0].on_click(None)

        dlg = app.page.dialogs[-1]  # type: ignore[attr-defined]
        ctrls = list(_walk_controls(dlg))
        chips = {
            c.data["status_option"]: c
            for c in ctrls
            if isinstance(c, ft.Chip)
            and isinstance(getattr(c, "data", None), dict)
            and "status_option" in c.data
        }
        tf = {
            c.label: c for c in ctrls if isinstance(c, ft.TextField) and c.label
        }
        save_btn = next(
            c
            for c in ctrls
            if isinstance(c, ft.FilledButton)
            and isinstance(getattr(c, "content", None), ft.Text)
            and c.content.value == "Save"
        )

        # Selecting Overdue Make-up auto-syncs count from 0 to target (2)
        chips["late_makeup"].on_select(None)
        self.assertEqual(tf["Count"].value, "2")
        tf["Check-in Note (optional)"].value = "Made up"
        await save_btn.on_click(None)

        app.api.checkin_habit.assert_awaited_once()
        kwargs = app.api.checkin_habit.await_args.kwargs
        self.assertEqual(kwargs["habit_id"], "h-editable")
        self.assertEqual(kwargs["target_date"], "2026-11-15")
        self.assertEqual(kwargs["action"], "edit")
        self.assertEqual(kwargs["count"], 2)
        self.assertEqual(kwargs["note"], "Made up")
        self.assertEqual(kwargs["status_override"], "late_makeup")

        # Schedule row Edit check-in -> Clear Day resets count=0, note=""
        app.api.checkin_habit.reset_mock()
        row = app._build_schedule_day_item_row(
            {
                "habit_id": "h-sched",
                "title": "Deep Work",
                "date": "2026-11-14",
                "completed": True,
                "count": 1,
                "target_per_day": 1,
                "is_late": False,
                "note": "Done",
                "status": "completed",
                "mode": "free",
            },
            is_future=False,
        )
        sched_edit_btn = next(
            c
            for c in _walk_controls(row)
            if isinstance(c, ft.IconButton) and c.tooltip == "Edit check-in"
        )
        sched_edit_btn.on_click(None)
        sched_dlg = app.page.dialogs[-1]  # type: ignore[attr-defined]
        clear_btn = next(
            c
            for c in _walk_controls(sched_dlg)
            if isinstance(c, ft.TextButton)
            and isinstance(getattr(c, "content", None), ft.Text)
            and c.content.value == "Clear Day"
        )
        await clear_btn.on_click(None)
        c_kwargs = app.api.checkin_habit.await_args.kwargs
        self.assertEqual(c_kwargs["action"], "edit")
        self.assertEqual(c_kwargs["status_override"], "clear")
        self.assertEqual(c_kwargs["count"], 0)
        self.assertEqual(c_kwargs["note"], "")

    async def test_habit_history_dialog_from_habits_and_stats_live_refresh(self) -> None:
        app = _make_app()
        app.refresh_current_tab = AsyncMock()  # type: ignore[method-assign]
        app.all_habits = [
            {
                "id": "h1",
                "title": "Deep Work",
                "color": "#6366F1",
                "frequency_type": "daily",
                "target_per_day": 1,
                "target_slo": 90.0,
                "mode": "strict",
                "archived": False,
            }
        ]
        app.stats_summary = {
            "best_active_streak": 2,
            "overall_completion_rate_30d": 75.0,
            "completed_today": 1,
            "scheduled_today": 1,
            "late_today": 0,
            "violated_today": 0,
            "last_7_days": [],
            "habit_stats": [
                {
                    "habit_id": "h1",
                    "title": "Deep Work",
                    "color": "#6366F1",
                    "frequency_type": "daily",
                    "mode": "strict",
                    "current_streak": 2,
                    "best_streak": 2,
                    "completion_rate_30d": 75.0,
                    "total_completions": 3,
                    "late_completions": 0,
                }
            ],
        }

        habits_view = app._build_habits_view()
        stats_view = app._build_stats_view()
        habits_hist_btn = next(
            c
            for c in _walk_controls(habits_view)
            if isinstance(c, ft.IconButton) and c.tooltip == "Check-in history"
        )
        stats_hist_btn = next(
            c
            for c in _walk_controls(stats_view)
            if isinstance(c, ft.IconButton) and c.tooltip == "Check-in history"
        )
        # Flet requires async coroutine functions directly on on_click (never sync lambdas)
        self.assertTrue(inspect.iscoroutinefunction(habits_hist_btn.on_click))
        self.assertTrue(inspect.iscoroutinefunction(stats_hist_btn.on_click))

        initial_hist = {
            "habit": app.all_habits[0],
            "month": "2026-11",
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            "first_weekday": 6,
            "created_date": "2026-11-10",
            "today": "2026-11-16",
            "can_prev_month": False,
            "can_next_month": False,
            "current_streak": 1,
            "best_streak": 2,
            "completion_rate_30d": 71.4,
            "total_completions": 5,
            "late_completions": 0,
            "month_scheduled": 7,
            "month_completed_on_time": 5,
            "month_late_makeups": 0,
            "month_missed": 1,
            "days": [
                {
                    "date": "2026-11-09",
                    "day": 9,
                    "weekday": 0,
                    "weekday_label": "Mon",
                    "scheduled": True,
                    "editable": False,
                    "is_today": False,
                    "count": 0,
                    "completed": False,
                    "is_late": False,
                    "note": "",
                    "state": "before_created",
                },
                {
                    "date": "2026-11-13",
                    "day": 13,
                    "weekday": 4,
                    "weekday_label": "Fri",
                    "scheduled": True,
                    "editable": True,
                    "is_today": False,
                    "count": 0,
                    "completed": False,
                    "is_late": False,
                    "note": "",
                    "state": "missed",
                },
                {
                    "date": "2026-11-17",
                    "day": 17,
                    "weekday": 1,
                    "weekday_label": "Tue",
                    "scheduled": True,
                    "editable": False,
                    "is_today": False,
                    "count": 0,
                    "completed": False,
                    "is_late": False,
                    "note": "",
                    "state": "future",
                },
            ],
        }
        updated_hist = {
            **initial_hist,
            "current_streak": 4,
            "month_completed_on_time": 6,
            "month_missed": 0,
            "days": [
                initial_hist["days"][0],
                {
                    **initial_hist["days"][1],
                    "count": 1,
                    "completed": True,
                    "note": "Fixed",
                    "state": "on_time",
                },
                initial_hist["days"][2],
            ],
        }
        app.api.get_habit_history = AsyncMock(side_effect=[initial_hist, updated_hist])
        app.api.checkin_habit = AsyncMock(return_value={"id": "h1", "completed": True})

        await stats_hist_btn.on_click(None)
        history_dlg = app.page.dialogs[-1]  # type: ignore[attr-defined]

        cells = {
            c.data["history_date"]: c
            for c in _walk_controls(history_dlg)
            if isinstance(c, ft.Container)
            and isinstance(getattr(c, "data", None), dict)
            and "history_date" in c.data
        }
        self.assertIsNone(cells["2026-11-09"].on_click)
        self.assertIsNone(cells["2026-11-17"].on_click)
        self.assertIsNotNone(cells["2026-11-13"].on_click)

        # Clicking editable calendar cell opens stacked edit dialog
        cells["2026-11-13"].on_click(None)
        edit_dlg = app.page.dialogs[-1]  # type: ignore[attr-defined]
        self.assertIsNot(edit_dlg, history_dlg)

        edit_ctrls = list(_walk_controls(edit_dlg))
        on_time_chip = next(
            c
            for c in edit_ctrls
            if isinstance(c, ft.Chip)
            and isinstance(getattr(c, "data", None), dict)
            and c.data.get("status_option") == "on_time"
        )
        on_time_chip.on_select(None)
        save_btn = next(
            c
            for c in edit_ctrls
            if isinstance(c, ft.FilledButton)
            and isinstance(getattr(c, "content", None), ft.Text)
            and c.content.value == "Save"
        )
        await save_btn.on_click(None)

        self.assertEqual(app.api.get_habit_history.await_count, 2)
        self.assertIn(history_dlg, app.page.dialogs)  # type: ignore[attr-defined]
        self.assertNotIn(edit_dlg, app.page.dialogs)  # type: ignore[attr-defined]
        self.assertIn("Streak 4d", _collect_text_values(history_dlg))

        close_btn = next(
            c
            for c in _walk_controls(history_dlg)
            if isinstance(c, ft.TextButton)
            and isinstance(getattr(c, "content", None), ft.Text)
            and c.content.value == "Close"
        )
        close_btn.on_click(None)
        self.assertNotIn(history_dlg, app.page.dialogs)  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
