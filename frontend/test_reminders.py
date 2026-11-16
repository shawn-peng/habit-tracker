import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import flet as ft

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main  # noqa: E402


class _FakePrefs:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str) -> None:
        self.store[key] = value

    async def remove(self, key: str) -> None:
        self.store.pop(key, None)


class _FakePage:
    def __init__(self) -> None:
        self.title = ""
        self.theme_mode = None
        self.padding = 0
        self.bgcolor = None
        self.width = 960
        self.controls: list[ft.Control] = []
        self.overlay: list[ft.Control] = []
        self.services: list[ft.Service] = []
        self.dialogs: list[ft.Control] = []
        self.shared_preferences = _FakePrefs()
        self.update_calls: list[tuple[ft.Control, ...]] = []

    def update(self, *controls: ft.Control) -> None:
        self.update_calls.append(controls)

    def show_dialog(self, dialog: ft.Control) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        if self.dialogs:
            self.dialogs.pop()

    def run_task(self, handler, *args, **kwargs):
        return None


def _walk_controls(root):
    if root is None:
        return
    yield root
    for attr in ("content", "title", "leading", "trailing"):
        child = getattr(root, attr, None)
        if child is not None and not isinstance(child, (str, int, float, bool)):
            yield from _walk_controls(child)
    for attr in ("controls", "actions"):
        children = getattr(root, attr, None)
        if isinstance(children, list):
            for child in children:
                yield from _walk_controls(child)


def _make_app() -> main.HabitTrackerApp:
    page = _FakePage()
    app = main.HabitTrackerApp(page)  # type: ignore[arg-type]
    app.api.current_user = {"id": "user-1", "email": "demo@example.com"}
    app.api.get_today_habits = AsyncMock(return_value=[])
    app.api.get_all_habits = AsyncMock(return_value=[])
    app.api.get_period_schedule = AsyncMock(return_value={})
    app.api.get_stats_overview = AsyncMock(return_value={})
    app.api.get_sli_overview = AsyncMock(return_value={})
    app.api.checkin_habit = AsyncMock(return_value={})
    app.api.create_habit = AsyncMock(return_value={"id": "h-new"})
    app.api.update_habit = AsyncMock(return_value={"id": "h-1"})
    app._trigger_haptic = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return app


class ReminderHelperTests(unittest.TestCase):
    def test_normalize_hhmm(self) -> None:
        self.assertEqual(main.normalize_hhmm("08:30"), "08:30")
        self.assertEqual(main.normalize_hhmm(" 8:05 "), "08:05")
        self.assertEqual(main.normalize_hhmm("23:59"), "23:59")
        self.assertIsNone(main.normalize_hhmm("24:00"))
        self.assertIsNone(main.normalize_hhmm("09:60"))
        self.assertIsNone(main.normalize_hhmm("not-a-time"))
        self.assertIsNone(main.normalize_hhmm(""))

    def test_format_reminder_badge(self) -> None:
        self.assertIsNone(
            main.format_reminder_badge(
                {"reminder_enabled": False, "reminder_times": ["08:00"]}
            )
        )
        self.assertIsNone(
            main.format_reminder_badge(
                {"reminder_enabled": True, "reminder_times": []}
            )
        )
        self.assertEqual(
            main.format_reminder_badge(
                {
                    "reminder_enabled": True,
                    "reminder_mode": "notification",
                    "reminder_times": ["08:30"],
                }
            ),
            "🔔 8:30 AM",
        )
        self.assertEqual(
            main.format_reminder_badge(
                {
                    "reminder_enabled": True,
                    "reminder_mode": "alarm",
                    "reminder_times": ["07:00", "12:30", "21:00"],
                }
            ),
            "⏰ 7:00 AM, 12:30 PM (+1)",
        )

    def test_is_habit_scheduled_on_date(self) -> None:
        self.assertTrue(
            main.is_habit_scheduled_on_date({"frequency_type": "daily"}, date(2026, 4, 5))
        )
        weekly = {"frequency_type": "weekdays", "weekdays": [0, 2, 4]}
        self.assertTrue(main.is_habit_scheduled_on_date(weekly, date(2026, 4, 6)))  # Mon
        self.assertFalse(main.is_habit_scheduled_on_date(weekly, date(2026, 4, 7)))  # Tue

        monthly_day = {
            "frequency_type": "monthly",
            "monthly_mode": "from_start",
            "monthly_day": 31,
        }
        # April has 30 days, so day 31 clamps to April 30
        self.assertTrue(
            main.is_habit_scheduled_on_date(monthly_day, date(2026, 4, 30))
        )
        self.assertFalse(
            main.is_habit_scheduled_on_date(monthly_day, date(2026, 4, 29))
        )

        monthly_nth = {
            "frequency_type": "monthly",
            "monthly_mode": "nth_weekday",
            "monthly_week": 1,
            "monthly_weekday": 0,  # 1st Monday
        }
        # April 2026 starts on Wednesday Apr 1 -> 1st Monday is Apr 6
        self.assertTrue(
            main.is_habit_scheduled_on_date(monthly_nth, date(2026, 4, 6))
        )
        self.assertFalse(
            main.is_habit_scheduled_on_date(monthly_nth, date(2026, 4, 13))
        )

    def test_find_due_habit_reminders_filters_and_handles_snooze(self) -> None:
        now_dt = datetime(2026, 4, 6, 9, 0)  # Monday
        habits = [
            {
                "id": "h-due",
                "title": "Water",
                "frequency_type": "daily",
                "reminder_enabled": True,
                "reminder_times": ["09:00"],
                "reminder_mode": "alarm",
            },
            {
                "id": "h-done",
                "title": "Done",
                "frequency_type": "daily",
                "reminder_enabled": True,
                "reminder_times": ["09:00"],
                "reminder_mode": "notification",
            },
            {
                "id": "h-wrong-day",
                "title": "Sunday Review",
                "frequency_type": "weekdays",
                "weekdays": [6],
                "reminder_enabled": True,
                "reminder_times": ["09:00"],
                "reminder_mode": "alarm",
            },
            {
                "id": "h-archived",
                "title": "Old",
                "archived": True,
                "frequency_type": "daily",
                "reminder_enabled": True,
                "reminder_times": ["09:00"],
            },
        ]
        snoozed = {
            "h-snooze": (
                datetime(2026, 4, 6, 8, 59),
                {
                    "id": "h-snooze",
                    "title": "Stretch",
                    "reminder_mode": "alarm",
                    "reminder_snooze_minutes": 10,
                },
            )
        }
        fired = set()
        due = main.find_due_habit_reminders(
            habits=habits,
            completed_ids={"h-done"},
            snoozed_until=snoozed,
            fired_keys=fired,
            now_dt=now_dt,
        )
        due_ids = {item["habit"]["id"]: item for item in due}
        self.assertEqual(set(due_ids.keys()), {"h-due", "h-snooze"})
        self.assertTrue(due_ids["h-snooze"]["is_snooze"])
        self.assertFalse(due_ids["h-due"]["is_snooze"])

        # Marking fire keys prevents re-triggering in the same minute
        for item in due:
            fired.add(item["fire_key"])
        due_again = main.find_due_habit_reminders(
            habits=habits,
            completed_ids={"h-done"},
            snoozed_until=snoozed,
            fired_keys=fired,
            now_dt=now_dt,
        )
        self.assertEqual(due_again, [])


class ReminderFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluate_due_reminders_muted_vs_notification_vs_alarm(self) -> None:
        app = _make_app()
        now_dt = datetime(2026, 4, 6, 9, 0)
        notif_habit = {
            "id": "h-notif",
            "title": "Drink Water",
            "frequency_type": "daily",
            "completed": False,
            "reminder_enabled": True,
            "reminder_times": ["09:00"],
            "reminder_mode": "notification",
            "reminder_message": "One full glass",
        }
        app._tab_cache[(0, ("2026-04-06",))] = ([notif_habit], 0.0, 0)

        # Muted suppresses firing
        app.reminders_muted = True
        due_muted = await app._evaluate_due_reminders(now_dt, fetch_if_empty=False)
        self.assertEqual(due_muted, [])
        self.assertEqual(app.page.dialogs, [])  # type: ignore[attr-defined]

        # Notification mode emits a SnackBar toast
        app.reminders_muted = False
        due_notif = await app._evaluate_due_reminders(now_dt, fetch_if_empty=False)
        self.assertEqual(len(due_notif), 1)
        self.assertEqual(len(app.page.dialogs), 1)  # type: ignore[attr-defined]
        snack = app.page.dialogs[-1]  # type: ignore[attr-defined]
        self.assertIsInstance(snack, ft.SnackBar)
        self.assertIn("Drink Water", snack.content.value)
        self.assertIn("One full glass", snack.content.value)

        # Alarm mode opens a ringing modal AlertDialog
        alarm_habit = {
            "id": "h-alarm",
            "title": "Morning Run",
            "frequency_type": "daily",
            "completed": False,
            "reminder_enabled": True,
            "reminder_times": ["09:05"],
            "reminder_mode": "alarm",
            "reminder_snooze_minutes": 15,
            "reminder_message": "Lace up now",
            "target_per_day": 1,
        }
        app._tab_cache[(0, ("2026-04-06",))] = ([alarm_habit], 0.0, 0)
        due_alarm = await app._evaluate_due_reminders(
            datetime(2026, 4, 6, 9, 5), fetch_if_empty=False
        )
        self.assertEqual(len(due_alarm), 1)
        dlg = app._active_alarm_dialog
        self.assertIsInstance(dlg, ft.AlertDialog)
        self.assertIn(dlg, app.page.dialogs)  # type: ignore[attr-defined]

    async def test_ringing_alarm_actions_checkin_snooze_dismiss(self) -> None:
        app = _make_app()
        habit = {
            "id": "h-alarm",
            "title": "Deep Focus",
            "color": "#6366F1",
            "target_per_day": 1,
            "reminder_enabled": True,
            "reminder_mode": "alarm",
            "reminder_snooze_minutes": 15,
            "reminder_message": "Start 45m sprint",
        }

        # 1. Dismiss
        app._open_ringing_alarm_dialog(habit, "10:00")
        dlg = app._active_alarm_dialog
        self.assertIsNotNone(dlg)
        buttons = {
            ctrl.content.value: ctrl
            for ctrl in dlg.actions
            if hasattr(ctrl, "content") and isinstance(ctrl.content, ft.Text)
        }
        buttons["Dismiss"].on_click(None)
        self.assertIsNone(app._active_alarm_dialog)
        self.assertNotIn(dlg, app.page.dialogs)  # type: ignore[attr-defined]

        # 2. Snooze
        app._open_ringing_alarm_dialog(habit, "10:00")
        dlg = app._active_alarm_dialog
        buttons = {
            ctrl.content.value: ctrl
            for ctrl in dlg.actions
            if hasattr(ctrl, "content") and isinstance(ctrl.content, ft.Text)
        }
        fixed_now = datetime(2026, 4, 6, 10, 0)
        with patch.object(main, "datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            await buttons["Snooze 15m"].on_click(None)
        self.assertIsNone(app._active_alarm_dialog)
        self.assertIn("h-alarm", app._snoozed_alarms)
        wake_dt, snap = app._snoozed_alarms["h-alarm"]
        self.assertEqual(wake_dt, fixed_now + timedelta(minutes=15))
        self.assertEqual(snap["id"], "h-alarm")

        # 3. Check In Now
        app.render_shell = lambda: None  # type: ignore[method-assign]
        app._open_ringing_alarm_dialog(habit, "10:15")
        dlg = app._active_alarm_dialog
        buttons = {
            ctrl.content.value: ctrl
            for ctrl in dlg.actions
            if hasattr(ctrl, "content") and isinstance(ctrl.content, ft.Text)
        }
        await buttons["Check In Now"].on_click(None)
        app.api.checkin_habit.assert_awaited_once()
        call_kwargs = app.api.checkin_habit.await_args.kwargs
        self.assertEqual(call_kwargs["habit_id"], "h-alarm")
        self.assertEqual(call_kwargs["action"], "toggle")
        self.assertNotIn("h-alarm", app._snoozed_alarms)
        self.assertIsNone(app._active_alarm_dialog)

    async def test_habit_dialog_saves_reminder_fields_and_validates(self) -> None:
        app = _make_app()
        app.render_shell = lambda: None  # type: ignore[method-assign]
        app._open_habit_dialog()

        dlg = app.page.dialogs[-1]  # type: ignore[attr-defined]
        self.assertIsInstance(dlg, ft.AlertDialog)

        all_ctrls = list(_walk_controls(dlg))
        text_fields = {
            c.label: c for c in all_ctrls if isinstance(c, ft.TextField) and c.label
        }
        dropdowns = {
            c.label: c for c in all_ctrls if isinstance(c, ft.Dropdown) and c.label
        }
        switches = {
            c.label: c for c in all_ctrls if isinstance(c, ft.Switch) and c.label
        }
        buttons = [
            c
            for c in all_ctrls
            if isinstance(c, (ft.FilledButton, ft.OutlinedButton, ft.TextButton))
            and isinstance(getattr(c, "content", None), ft.Text)
        ]
        save_btn = next(b for b in buttons if b.content.value == "Save")
        err_text = next(
            c
            for c in all_ctrls
            if isinstance(c, ft.Text) and c.color == ft.Colors.RED_600
        )

        text_fields["Habit Title"].value = "Evening Reading"
        self.assertNotIn("Enable Reminders & Alarms", switches)
        mode_dd = dropdowns["Habit Mode"]
        mode_dd.value = "reminder"
        mode_dd.on_select(None)

        # Invalid custom time blocks save
        text_fields["Add Time (HH:MM)"].value = "99:99"
        await save_btn.on_click(None)
        self.assertTrue(err_text.visible)
        app.api.create_habit.assert_not_awaited()

        # Valid 12h AM/PM time + alarm mode + snooze + custom message saves all fields
        text_fields["Add Time (HH:MM)"].value = "09:15"
        dropdowns["Add Time AM/PM"].value = "PM"
        dropdowns["Reminder Style"].value = "alarm"
        dropdowns["Snooze Duration"].value = "30"
        text_fields["Custom Reminder Message (optional)"].value = "Read 20 pages"

        await save_btn.on_click(None)
        app.api.create_habit.assert_awaited_once()
        payload = app.api.create_habit.await_args.args[0]
        self.assertEqual(payload["mode"], "reminder")
        self.assertEqual(payload["remind_time"], "09:00")
        self.assertTrue(payload["reminder_enabled"])
        self.assertEqual(payload["reminder_times"], ["09:00", "21:15"])
        self.assertEqual(payload["reminder_mode"], "alarm")
        self.assertEqual(payload["reminder_snooze_minutes"], 30)
        self.assertEqual(payload["reminder_message"], "Read 20 pages")

        # Strict mode habits also compute effective reminder badges & due triggers
        self.assertEqual(
            main.effective_habit_reminder_times(
                {"mode": "strict", "remind_time": "08:30"}
            ),
            ["08:30"],
        )
        self.assertEqual(
            main.format_reminder_badge(
                {"mode": "strict", "remind_time": "08:30", "reminder_mode": "alarm"}
            ),
            "⏰ 8:30 AM",
        )

        # 24h bare time input still works when AM/PM defaults to AM
        self.assertEqual(main.resolve_time_with_meridiem("21:15", "AM"), "21:15")
        self.assertEqual(main.resolve_time_with_meridiem("12:00", "AM"), "00:00")
        self.assertEqual(main.resolve_time_with_meridiem("12:30", "PM"), "12:30")


if __name__ == "__main__":
    unittest.main()
