import asyncio
import calendar
from datetime import date, datetime, time as dt_time, timedelta
import re
import time
from typing import Any
import flet as ft

from api_client import (
    DEFAULT_API_URL,
    STORAGE_REMINDERS_MUTED_KEY,
    ApiError,
    HabitApiClient,
    StorageHelper,
    close_dialog,
    open_dialog,
    show_toast,
)

MAX_REMINDER_TIMES = 12
_REMINDER_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
REMINDER_TIME_PRESETS = ["07:30", "09:00", "12:30", "18:00", "21:30"]
REMINDER_SNOOZE_OPTIONS = [5, 10, 15, 30, 60]

HABIT_MODE_OPTIONS = [
    ("free", "自由打卡（默认）"),
    ("strict", "模式1：严格管控（提醒→强制开始→强制完成）"),
    ("window", "模式2：弹性时间窗（提醒→强制完成）"),
    ("reminder", "模式3：定时提醒（开始提醒时间）"),
]
HABIT_MODE_SHORT_LABELS = {
    "free": "自由模式",
    "strict": "模式1·严格管控",
    "window": "模式2·弹性时间窗",
    "reminder": "模式3·定时提醒",
}
HABIT_MODE_HINTS = {
    "free": "无时间限制，当天随时打卡均计为准时完成。",
    "strict": "需严格按 提醒时间 < 强制执行时间 < 强制完成时间 顺序；开始前不可直接完成。",
    "window": "到开始提醒时间提示打卡，在强制完成时间前完成即算准时。",
    "reminder": "到达开始提醒时间触发提示，不设超时违规，任意完成均算准时。",
}

COLOR_SWATCHES = [
    ("#6366F1", "Indigo"),
    ("#10B981", "Emerald"),
    ("#F59E0B", "Amber"),
    ("#EC4899", "Pink"),
    ("#0EA5E9", "Sky"),
    ("#8B5CF6", "Violet"),
]

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_FULL_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def format_habit_schedule(habit: dict[str, Any]) -> str:
    freq = habit.get("frequency_type", "daily")
    if freq == "daily":
        return "Every day"
    if freq == "monthly":
        mode = habit.get("monthly_mode", "from_start")
        day = int(habit.get("monthly_day", 1))
        if mode == "from_end":
            if day == 1:
                return "Monthly • Last day of month"
            return f"Monthly • {_ordinal(day)} day from end"
        if mode == "nth_weekday":
            wk = int(habit.get("monthly_week", 1))
            wd = int(habit.get("monthly_weekday", 0)) % 7
            wk_label = "Last week" if wk == -1 else f"Week {wk}"
            return f"Monthly • {WEEKDAY_LABELS[wd]} on {wk_label}"
        return f"Monthly • {_ordinal(day)} day"
    return ", ".join(
        WEEKDAY_LABELS[d] for d in habit.get("weekdays", []) if 0 <= d <= 6
    )


def normalize_hhmm(raw: str) -> str | None:
    """Validate and normalize a 24-hour time string (H:MM or HH:MM) to HH:MM."""
    match = _REMINDER_TIME_RE.match((raw or "").strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def validate_habit_mode_times(
    mode: str,
    remind_raw: str | None,
    start_raw: str | None,
    end_raw: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Validate habit mode time inputs and return (remind, start, end, error_message)."""
    if mode == "free":
        return None, None, None, None

    def _parse(val: str | None, label: str) -> tuple[str | None, str | None]:
        cleaned = (val or "").strip()
        if not cleaned:
            return None, f"{label} 不能为空"
        norm = normalize_hhmm(cleaned)
        if norm is None:
            return None, f"{label} 格式必须为 24 小时制 HH:MM"
        return norm, None

    remind, err = _parse(remind_raw, "开始提醒时间")
    if err:
        return None, None, None, err
    if mode == "reminder":
        return remind, None, None, None

    end, err = _parse(end_raw, "强制完成时间")
    if err:
        return None, None, None, err
    if mode == "window":
        if remind >= end:  # type: ignore[operator]
            return None, None, None, "开始提醒时间必须早于强制完成时间"
        return remind, None, end, None

    if mode == "strict":
        start, err = _parse(start_raw, "强制执行时间")
        if err:
            return None, None, None, err
        if not (remind < start < end):  # type: ignore[operator]
            return (
                None,
                None,
                None,
                "模式1需满足：开始提醒时间 < 强制执行时间 < 强制完成时间",
            )
        return remind, start, end, None

    return None, None, None, f"不支持的模式: {mode}"


def format_habit_mode_summary(habit: dict[str, Any]) -> str:
    mode = habit.get("mode") or "free"
    if mode == "free":
        return ""
    label = HABIT_MODE_SHORT_LABELS.get(mode, mode)
    parts: list[str] = []
    if habit.get("remind_time"):
        parts.append(f"提醒 {habit['remind_time']}")
    if mode == "strict" and habit.get("force_start_time"):
        parts.append(f"开始 {habit['force_start_time']}")
    if mode in ("strict", "window") and habit.get("force_end_time"):
        parts.append(f"完成 {habit['force_end_time']}")
    return f"{label}（{' · '.join(parts)}）" if parts else label


def evaluate_local_habit_status(
    habit: dict[str, Any],
    target_date_iso: str,
    today_iso: str,
    now_hhmm: str,
) -> tuple[str, str | None, bool, bool]:
    """Evaluate (day_status, violation_reason, can_start, is_late) locally for live clock parity."""
    mode = habit.get("mode") or "free"
    remind_time = habit.get("remind_time")
    force_start_time = habit.get("force_start_time")
    force_end_time = habit.get("force_end_time")

    target = max(1, int(habit.get("target_per_day", 1)))
    count = int(habit.get("count", 0))
    completed = bool(habit.get("completed", False)) or count >= target
    started_on_time = bool(habit.get("started_on_time", False))
    is_late = bool(habit.get("is_late", False))
    violation_reason = habit.get("violation_reason")
    scheduled = bool(habit.get("scheduled_today", True))

    if completed:
        if mode in ("strict", "window") and is_late:
            return ("late_makeup", violation_reason, False, True)
        return ("on_time", None, False, False)

    if not scheduled or target_date_iso > today_iso:
        return (
            ("in_progress" if (mode == "strict" and started_on_time) else "pending"),
            None,
            False,
            False,
        )

    is_past = target_date_iso < today_iso

    if mode == "free":
        return ("pending", None, False, False)

    if mode == "reminder":
        status = (
            "reminding"
            if (not is_past and remind_time and now_hhmm >= remind_time)
            else "pending"
        )
        return (status, None, False, False)

    if mode == "window":
        if is_past or (force_end_time and now_hhmm > force_end_time):
            return ("violation", "missed_end", False, False)
        status = "reminding" if (remind_time and now_hhmm >= remind_time) else "pending"
        return (status, None, False, False)

    # mode == "strict"
    if not started_on_time:
        if is_past or (force_start_time and now_hhmm > force_start_time):
            return ("violation", "missed_start", False, False)
        status = "reminding" if (remind_time and now_hhmm >= remind_time) else "pending"
        return (status, None, True, False)

    if is_past or (force_end_time and now_hhmm > force_end_time):
        return ("violation", "missed_end", False, False)

    return ("in_progress", None, False, False)


def _scheduled_monthly_day(year: int, month: int, habit: dict[str, Any]) -> int:
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


def is_habit_scheduled_on_date(habit: dict[str, Any], target: date) -> bool:
    """Return True if habit is scheduled on target date."""
    freq = habit.get("frequency_type", "daily")
    if freq == "daily":
        return True
    if freq == "monthly":
        return target.day == _scheduled_monthly_day(target.year, target.month, habit)
    weekdays = habit.get("weekdays") or [0, 1, 2, 3, 4, 5, 6]
    return target.weekday() in weekdays


def format_reminder_badge(habit: dict[str, Any]) -> str | None:
    """Return a compact display label for a habit's reminders/alarms, or None."""
    if not habit.get("reminder_enabled", False):
        return None
    raw_times = habit.get("reminder_times") or []
    times = [t for t in (normalize_hhmm(str(x)) for x in raw_times) if t is not None]
    if not times:
        return None
    prefix = "⏰" if habit.get("reminder_mode") == "alarm" else "🔔"
    if len(times) <= 2:
        return f"{prefix} {', '.join(times)}"
    return f"{prefix} {times[0]}, {times[1]} (+{len(times) - 2})"


def find_due_habit_reminders(
    habits: list[dict[str, Any]],
    completed_ids: set[str],
    snoozed_until: dict[str, tuple[datetime, dict[str, Any]]],
    fired_keys: set[str],
    now_dt: datetime,
) -> list[dict[str, Any]]:
    """Return due scheduled or snoozed reminders/alarms at now_dt."""
    due: list[dict[str, Any]] = []
    seen_habit_ids: set[str] = set()

    for hid, (wake_dt, habit_snapshot) in list(snoozed_until.items()):
        if hid in completed_ids or now_dt < wake_dt:
            continue
        fire_key = f"snooze|{hid}|{wake_dt.strftime('%Y-%m-%dT%H:%M')}"
        if fire_key in fired_keys:
            continue
        mode = (
            "alarm"
            if habit_snapshot.get("reminder_mode") == "alarm"
            else "notification"
        )
        due.append(
            {
                "habit": habit_snapshot,
                "mode": mode,
                "time_label": wake_dt.strftime("%H:%M"),
                "fire_key": fire_key,
                "is_snooze": True,
            }
        )
        seen_habit_ids.add(hid)

    today_date = now_dt.date()
    today_iso = today_date.isoformat()
    now_hhmm = now_dt.strftime("%H:%M")

    for habit in habits:
        if habit.get("archived", False) or not habit.get("reminder_enabled", False):
            continue
        hid = str(habit.get("id") or habit.get("habit_id") or "")
        if not hid or hid in completed_ids or hid in seen_habit_ids:
            continue
        if not is_habit_scheduled_on_date(habit, today_date):
            continue
        times = habit.get("reminder_times") or []
        if now_hhmm not in times:
            continue
        fire_key = f"{today_iso}|{hid}|{now_hhmm}"
        if fire_key in fired_keys:
            continue
        mode = "alarm" if habit.get("reminder_mode") == "alarm" else "notification"
        due.append(
            {
                "habit": habit,
                "mode": mode,
                "time_label": now_hhmm,
                "fire_key": fire_key,
                "is_snooze": False,
            }
        )

    return due


TAB_CACHE_TTL_SECONDS = 45.0


class HabitTrackerApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.storage = StorageHelper(page)
        self.api = HabitApiClient(self.storage)

        self.selected_tab: int = 0
        self.selected_date: date = date.today()
        self.today_habits: list[dict[str, Any]] = []
        self.all_habits: list[dict[str, Any]] = []
        self.stats_summary: dict[str, Any] | None = None
        self.sli_dashboard: dict[str, Any] | None = None
        self.sli_window_days: int = 30
        self.show_archived: bool = False
        self.schedule_period: str = "week"  # "week" | "month"
        self.schedule_anchor_date: date = date.today()
        self.schedule_filter: str = "todo"  # "todo" | "overdue" | "all"
        self.schedule_group_by: str = "day"  # "day" | "habit"
        self.period_schedule: dict[str, Any] | None = None

        self.reminders_muted: bool = False
        self._fired_reminder_keys: set[str] = set()
        self._snoozed_alarms: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._notified_mode_phases: dict[str, str] = {}
        self._reminder_task: Any | None = None
        self._active_alarm_dialog: ft.AlertDialog | None = None
        self._active_alarm_habit_id: str | None = None
        self._haptic: Any | None = None

        self._cache_ttl_seconds: float = TAB_CACHE_TTL_SECONDS
        self._tab_cache: dict[
            tuple[int, tuple[Any, ...]], tuple[Any, float, int]
        ] = {}
        self._tab_dirty: set[int] = set(range(5))
        self._tab_generations: dict[int, int] = {i: 0 for i in range(5)}
        self._loading_keys: set[tuple[int, tuple[Any, ...]]] = set()
        self._bg_refresh_task: Any | None = None
        self._bg_refresh_key: tuple[int, tuple[Any, ...]] | None = None
        self._bg_req_id: int = 0

        self._shell_mounted: bool = False
        self._shell_wide: bool | None = None
        self._shell_user_name: str | None = None
        self._shell_reminders_muted: bool | None = None
        self._shell_nav: ft.NavigationRail | ft.NavigationBar | None = None
        self._shell_root: ft.Control | None = None

        self.content_area = ft.Container(expand=True, padding=20)

    async def start(self) -> None:
        self.page.title = "Habit & Routine Tracker"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = "#F8FAFC"
        self.page.padding = 0
        self.page.on_resize = self._handle_resize
        self.page.on_disconnect = self._handle_disconnect

        # Initial loading indicator while checking saved session
        self._cancel_reminder_loop()
        self._cancel_bg_refresh()
        self._unmount_shell()
        saved_mute = await self.storage.get(STORAGE_REMINDERS_MUTED_KEY)
        self.reminders_muted = saved_mute == "true"

        self.page.controls.clear()
        self.page.add(
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    [
                        ft.ProgressRing(),
                        ft.Text("Connecting to server...", color=ft.Colors.BLUE_GREY_600),
                    ],
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
            )
        )
        self.page.update()

        logged_in = await self.api.initialize()
        if logged_in:
            self._clear_tab_cache()
            await self.refresh_current_tab(force=True)
            self.render_shell()
            self._start_reminder_loop()
        else:
            self.render_auth_screen()

    def _is_wide(self) -> bool:
        width = self.page.width or 900
        return width >= 760

    def _handle_resize(self, _e: Any) -> None:
        if self.api.current_user is not None and self._shell_mounted:
            new_wide = self._is_wide()
            if self._shell_wide is None or new_wide != self._shell_wide:
                self.render_shell(force_rebuild=True)

    async def _handle_disconnect(self, _e: Any) -> None:
        self._cancel_reminder_loop()
        self._cancel_bg_refresh()
        self._unmount_shell()
        await self.api.aclose()

    def _unmount_shell(self) -> None:
        self._shell_mounted = False
        self._shell_wide = None
        self._shell_user_name = None
        self._shell_reminders_muted = None
        self._shell_nav = None
        self._shell_root = None

    # -----------------------------------------------------------------------
    # Authentication Screen (Login / Register / Verify Email / Forgot Password)
    # -----------------------------------------------------------------------
    def render_auth_screen(
        self,
        is_register: bool = False,
        auth_mode: str | None = None,
        prefill_email: str = "",
        initial_info: str = "",
    ) -> None:
        self._cancel_reminder_loop()
        self._cancel_bg_refresh()
        self._unmount_shell()
        self.page.navigation_bar = None
        self.page.controls.clear()

        mode = auth_mode or ("register" if is_register else "login")
        has_reset_code = False

        server_input = ft.TextField(
            label="Server API URL",
            value=self.api.base_url,
            prefix_icon=ft.Icons.CLOUD_OUTLINED,
            hint_text="https://habit-tracker-api-142205380680.us-central1.run.app",
        )
        name_input = ft.TextField(
            label="Your Name",
            prefix_icon=ft.Icons.PERSON_OUTLINE,
            visible=(mode == "register"),
            autofocus=(mode == "register"),
        )
        email_input = ft.TextField(
            label="Email",
            value=prefill_email,
            prefix_icon=ft.Icons.EMAIL_OUTLINED,
            keyboard_type=ft.KeyboardType.EMAIL,
            autofocus=(
                mode in ("login", "forgot")
                or (mode == "verify_email" and not prefill_email)
            ),
        )
        password_input = ft.TextField(
            label="Password",
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            password=True,
            can_reveal_password=True,
            visible=(mode in ("login", "register")),
        )
        info_text = ft.Text(initial_info, color="#047857", size=12)
        info_banner = ft.Container(
            padding=10,
            border_radius=8,
            bgcolor="#ECFDF5",
            visible=bool(initial_info),
            content=info_text,
        )
        code_input = ft.TextField(
            label="6-Digit Verification Code",
            prefix_icon=ft.Icons.PIN_OUTLINED,
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=6,
            visible=(mode == "verify_email"),
            autofocus=(mode == "verify_email" and bool(prefill_email)),
        )
        new_pwd_input = ft.TextField(
            label="New Password (min 6 chars)",
            prefix_icon=ft.Icons.LOCK_RESET_ROUNDED,
            password=True,
            can_reveal_password=True,
            visible=False,
        )
        confirm_pwd_input = ft.TextField(
            label="Confirm New Password",
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            password=True,
            can_reveal_password=True,
            visible=False,
        )
        error_text = ft.Text("", color=ft.Colors.RED_600, size=13, visible=False)
        submit_label = {
            "register": "Create Account",
            "verify_email": "Verify Email & Sign In",
            "forgot": "Send Verification Code",
        }.get(mode, "Sign In")
        submit_btn = ft.FilledButton(
            content=ft.Text(submit_label),
            width=340,
        )

        have_code_btn = ft.TextButton(
            content=ft.Text("Already have a 6-digit code?"),
            visible=(mode == "forgot"),
        )
        resend_btn = ft.TextButton(
            content=ft.Text(
                "Resend Verification Code" if mode == "verify_email" else "Resend Code"
            ),
            visible=(mode == "verify_email"),
        )

        def reveal_reset_inputs() -> None:
            nonlocal has_reset_code
            has_reset_code = True
            code_input.visible = True
            new_pwd_input.visible = True
            confirm_pwd_input.visible = True
            submit_btn.content = ft.Text("Reset Password & Sign In")
            have_code_btn.visible = False
            resend_btn.visible = True

        def format_code_message(
            resp: dict[str, Any], default_msg: str, dev_key: str
        ) -> str:
            msg = resp.get("message", default_msg)
            dev_code = resp.get(dev_key)
            if dev_code:
                msg = f"{msg}\nDev verification code: {dev_code}"
            return msg

        async def send_reset_code() -> None:
            error_text.visible = False
            email = (email_input.value or "").strip()
            if not email:
                raise ApiError("Please enter your email")
            resp = await self.api.forgot_password(email=email)
            info_text.value = format_code_message(
                resp,
                "If an account exists for this email, a 6-digit verification code has been sent.",
                "dev_reset_code",
            )
            info_banner.visible = True
            reveal_reset_inputs()

        async def send_registration_code() -> None:
            error_text.visible = False
            email = (email_input.value or "").strip()
            if not email:
                raise ApiError("Please enter your email")
            resp = await self.api.resend_verification(email=email)
            info_text.value = format_code_message(
                resp,
                "A new 6-digit verification code has been sent to your email.",
                "dev_verification_code",
            )
            info_banner.visible = True

        async def handle_submit(_e: Any = None) -> None:
            if submit_btn.disabled:
                return
            error_text.visible = False
            submit_btn.disabled = True
            self.page.update()

            await self.api.set_base_url(server_input.value or DEFAULT_API_URL)
            email = (email_input.value or "").strip()
            pwd = password_input.value or ""
            name = (name_input.value or "").strip()
            screen_replaced = False

            try:
                if mode == "register":
                    if not name:
                        raise ApiError("Please enter your name")
                    resp = await self.api.register(name=name, email=email, password=pwd)
                    msg = format_code_message(
                        resp,
                        "A 6-digit verification code has been sent to your email.",
                        "dev_verification_code",
                    )
                    screen_replaced = True
                    self.render_auth_screen(
                        auth_mode="verify_email",
                        prefill_email=email,
                        initial_info=msg,
                    )
                    return
                elif mode == "verify_email":
                    code = (code_input.value or "").strip()
                    if not email:
                        raise ApiError("Please enter your email")
                    if len(code) != 6 or not code.isdigit():
                        raise ApiError(
                            "Please enter the 6-digit numeric verification code"
                        )
                    await self.api.verify_email(email=email, code=code)
                    screen_replaced = True
                    self.selected_tab = 0
                    self._clear_tab_cache()
                    await self.refresh_current_tab(force=True)
                    self.render_shell()
                    self._start_reminder_loop()
                    show_toast(self.page, "Email verified! Welcome to Habit Tracker.")
                    return
                elif mode == "forgot":
                    if not has_reset_code:
                        await send_reset_code()
                        return
                    code = (code_input.value or "").strip()
                    new_pwd = new_pwd_input.value or ""
                    confirm_pwd = confirm_pwd_input.value or ""
                    if not email:
                        raise ApiError("Please enter your email")
                    if len(code) != 6 or not code.isdigit():
                        raise ApiError("Please enter the 6-digit numeric verification code")
                    if len(new_pwd) < 6:
                        raise ApiError("New password must be at least 6 characters")
                    if new_pwd != confirm_pwd:
                        raise ApiError("Passwords do not match")
                    await self.api.reset_password(
                        email=email, code=code, new_password=new_pwd
                    )
                    screen_replaced = True
                    self.selected_tab = 0
                    self._clear_tab_cache()
                    await self.refresh_current_tab(force=True)
                    self.render_shell()
                    self._start_reminder_loop()
                    show_toast(self.page, "Password reset successfully!")
                    return
                else:
                    await self.api.login(email=email, password=pwd)

                screen_replaced = True
                self.selected_tab = 0
                self._clear_tab_cache()
                await self.refresh_current_tab(force=True)
                self.render_shell()
                self._start_reminder_loop()
                return
            except ApiError as err:
                if mode == "login" and err.status_code == 403:
                    screen_replaced = True
                    self.render_auth_screen(
                        auth_mode="verify_email",
                        prefill_email=email,
                        initial_info="Please enter the 6-digit verification code sent to your email (or click Resend Code).",
                    )
                    return
                error_text.value = err.message
                error_text.visible = True
            finally:
                if not screen_replaced:
                    submit_btn.disabled = False
                    self.page.update()

        async def handle_resend(_e: Any) -> None:
            error_text.visible = False
            resend_btn.disabled = True
            self.page.update()
            await self.api.set_base_url(server_input.value or DEFAULT_API_URL)
            try:
                if mode == "verify_email":
                    await send_registration_code()
                else:
                    await send_reset_code()
            except ApiError as err:
                error_text.value = err.message
                error_text.visible = True
            finally:
                resend_btn.disabled = False
                self.page.update()

        def handle_have_code(_e: Any) -> None:
            error_text.visible = False
            reveal_reset_inputs()
            self.page.update()

        async def on_server_submit(_e: Any = None) -> None:
            if mode == "register" and not (name_input.value or "").strip():
                await name_input.focus()
            elif not (email_input.value or "").strip():
                await email_input.focus()
            elif mode in ("login", "register") and not (password_input.value or ""):
                await password_input.focus()
            elif mode == "verify_email":
                if not (code_input.value or "").strip():
                    await code_input.focus()
                else:
                    await handle_submit(_e)
            elif mode == "forgot" and has_reset_code:
                if not (code_input.value or "").strip():
                    await code_input.focus()
                elif not (new_pwd_input.value or ""):
                    await new_pwd_input.focus()
                elif not (confirm_pwd_input.value or ""):
                    await confirm_pwd_input.focus()
                else:
                    await handle_submit(_e)
            else:
                await handle_submit(_e)

        async def on_name_submit(_e: Any = None) -> None:
            if (name_input.value or "").strip() and not (email_input.value or "").strip():
                await email_input.focus()
            elif (name_input.value or "").strip() and not (password_input.value or ""):
                await password_input.focus()
            else:
                await handle_submit(_e)

        async def on_email_submit(_e: Any = None) -> None:
            if mode in ("login", "register"):
                if (email_input.value or "").strip() and not (password_input.value or ""):
                    await password_input.focus()
                else:
                    await handle_submit(_e)
            elif mode == "verify_email":
                if (email_input.value or "").strip() and not (code_input.value or "").strip():
                    await code_input.focus()
                else:
                    await handle_submit(_e)
            elif not has_reset_code:
                await handle_submit(_e)
            elif (email_input.value or "").strip() and not (code_input.value or "").strip():
                await code_input.focus()
            elif (email_input.value or "").strip() and not (new_pwd_input.value or ""):
                await new_pwd_input.focus()
            elif (email_input.value or "").strip() and not (confirm_pwd_input.value or ""):
                await confirm_pwd_input.focus()
            else:
                await handle_submit(_e)

        async def on_code_submit(_e: Any = None) -> None:
            if mode == "verify_email":
                await handle_submit(_e)
            elif (code_input.value or "").strip() and not (new_pwd_input.value or ""):
                await new_pwd_input.focus()
            elif (code_input.value or "").strip() and not (confirm_pwd_input.value or ""):
                await confirm_pwd_input.focus()
            else:
                await handle_submit(_e)

        async def on_new_pwd_submit(_e: Any = None) -> None:
            if (new_pwd_input.value or "") and not (confirm_pwd_input.value or ""):
                await confirm_pwd_input.focus()
            else:
                await handle_submit(_e)

        server_input.on_submit = on_server_submit
        name_input.on_submit = on_name_submit
        email_input.on_submit = on_email_submit
        password_input.on_submit = handle_submit
        code_input.on_submit = on_code_submit
        new_pwd_input.on_submit = on_new_pwd_submit
        confirm_pwd_input.on_submit = handle_submit
        submit_btn.on_click = handle_submit
        resend_btn.on_click = handle_resend
        have_code_btn.on_click = handle_have_code

        def switch_mode(next_mode: str) -> None:
            cleaned_url = (server_input.value or "").strip().rstrip("/")
            if cleaned_url:
                self.api.base_url = cleaned_url
            self.render_auth_screen(
                auth_mode=next_mode,
                prefill_email=(email_input.value or "").strip(),
            )

        footer_links: list[ft.Control] = []
        if mode == "login":
            footer_links.append(
                ft.TextButton(
                    content=ft.Text("Forgot Password?"),
                    on_click=lambda _e: switch_mode("forgot"),
                )
            )
            footer_links.append(
                ft.TextButton(
                    content=ft.Text("New here? Create an Account"),
                    on_click=lambda _e: switch_mode("register"),
                )
            )
        elif mode == "register":
            footer_links.append(
                ft.TextButton(
                    content=ft.Text("Already have a code? Verify Email"),
                    on_click=lambda _e: switch_mode("verify_email"),
                )
            )
            footer_links.append(
                ft.TextButton(
                    content=ft.Text("Already have an account? Sign In"),
                    on_click=lambda _e: switch_mode("login"),
                )
            )
        elif mode == "verify_email":
            footer_links.extend(
                [
                    resend_btn,
                    ft.TextButton(
                        content=ft.Text("Back to Sign In"),
                        on_click=lambda _e: switch_mode("login"),
                    ),
                ]
            )
        else:
            footer_links.extend(
                [
                    have_code_btn,
                    resend_btn,
                    ft.TextButton(
                        content=ft.Text("Back to Sign In"),
                        on_click=lambda _e: switch_mode("login"),
                    ),
                ]
            )

        subtitle_text = {
            "forgot": "Reset your password with a 6-digit email verification code",
            "verify_email": "Enter the 6-digit verification code sent to your email",
        }.get(
            mode,
            "Sync your daily routines across iPhone, Mac, Android & Web",
        )

        card = ft.Container(
            width=400,
            padding=28,
            bgcolor=ft.Colors.WHITE,
            border_radius=16,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.VERIFIED_ROUNDED,
                                color="#6366F1",
                                size=32,
                            ),
                            ft.Text(
                                "Habit Tracker",
                                size=24,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        subtitle_text,
                        size=13,
                        color=ft.Colors.BLUE_GREY_600,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Divider(height=16),
                    server_input,
                    name_input,
                    email_input,
                    password_input,
                    info_banner,
                    code_input,
                    new_pwd_input,
                    confirm_pwd_input,
                    error_text,
                    submit_btn,
                    *footer_links,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
                spacing=12,
            ),
        )

        self.page.add(
            ft.SafeArea(
                expand=True,
                content=ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    padding=16,
                    content=ft.Column(
                        [card],
                        tight=True,
                        scroll=ft.ScrollMode.AUTO,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
            )
        )
        self.page.update()

    # -----------------------------------------------------------------------
    # Responsive Cross-Platform Navigation Shell
    # -----------------------------------------------------------------------
    async def _on_nav_change(self, e: Any) -> None:
        new_tab = int(e.control.selected_index)
        if new_tab == self.selected_tab and self._shell_mounted:
            return
        self.selected_tab = new_tab
        self._activate_current_view()

    async def _handle_logout(self, _e: Any) -> None:
        self._cancel_reminder_loop()
        self._fired_reminder_keys.clear()
        self._snoozed_alarms.clear()
        self._notified_mode_phases.clear()
        self._active_alarm_dialog = None
        self._active_alarm_habit_id = None
        self._clear_tab_cache()
        await self.api.logout()
        self.schedule_period = "week"
        self.schedule_anchor_date = date.today()
        self.render_auth_screen()

    async def _handle_manual_refresh(self, _e: Any) -> None:
        await self.refresh_current_tab(force=True)
        self.render_shell()

    def _is_attached(self, control: ft.Control) -> bool:
        try:
            return control.page is self.page
        except Exception:
            return False

    def _safe_update(self, *controls: ft.Control) -> None:
        if controls and all(self._is_attached(c) for c in controls):
            try:
                self.page.update(*controls)
                return
            except Exception:
                pass
        self.page.update()

    def _current_tab_key(
        self, tab: int | None = None
    ) -> tuple[int, tuple[Any, ...]]:
        t = self.selected_tab if tab is None else tab
        if t == 0:
            return (0, (self.selected_date.isoformat(),))
        if t == 1:
            return (
                1,
                (
                    self.schedule_period,
                    self.schedule_anchor_date.isoformat(),
                    date.today().isoformat(),
                ),
            )
        if t == 2:
            return (2, (self.show_archived,))
        if t == 3:
            return (3, (date.today().isoformat(),))
        return (4, (date.today().isoformat(), self.sli_window_days))

    def _apply_tab_data(self, tab: int, data: Any) -> None:
        if tab == 0:
            self.today_habits = data
        elif tab == 1:
            self.period_schedule = data
        elif tab == 2:
            self.all_habits = data
        elif tab == 3:
            self.stats_summary = data
        else:
            self.sli_dashboard = data

    def _store_cache_entry(
        self,
        key: tuple[int, tuple[Any, ...]],
        data: Any,
        generation: int,
    ) -> bool:
        tab = key[0]
        if generation != self._tab_generations.get(tab, 0):
            return False
        self._tab_cache[key] = (data, time.monotonic(), generation)
        self._tab_dirty.discard(tab)
        return True

    def _is_cache_fresh(self, key: tuple[int, tuple[Any, ...]]) -> bool:
        tab = key[0]
        if tab in self._tab_dirty:
            return False
        entry = self._tab_cache.get(key)
        if entry is None:
            return False
        _, fetched_at, generation = entry
        if generation != self._tab_generations.get(tab, 0):
            return False
        return (time.monotonic() - fetched_at) < self._cache_ttl_seconds

    def _invalidate_tabs(self, tabs: Any) -> None:
        for tab in tabs:
            self._tab_dirty.add(tab)
            self._tab_generations[tab] = self._tab_generations.get(tab, 0) + 1

    def _clear_tab_cache(self) -> None:
        self._cancel_bg_refresh()
        self._tab_cache.clear()
        self._loading_keys.clear()
        self._tab_dirty = set(range(5))
        for tab in range(5):
            self._tab_generations[tab] = self._tab_generations.get(tab, 0) + 1
        self.today_habits = []
        self.all_habits = []
        self.stats_summary = None
        self.sli_dashboard = None
        self.period_schedule = None

    async def _fetch_tab_data(self, key: tuple[int, tuple[Any, ...]]) -> Any:
        tab, params = key
        if tab == 0:
            (iso_date,) = params
            return await self.api.get_today_habits(iso_date)
        if tab == 1:
            period, anchor_iso, today_iso = params
            return await self.api.get_period_schedule(
                period=period,
                anchor_date=anchor_iso,
                today=today_iso,
            )
        if tab == 2:
            (include_archived,) = params
            return await self.api.list_habits(include_archived=include_archived)
        if tab == 3:
            (today_iso,) = params
            return await self.api.get_stats_summary(today_iso)
        today_iso, window_days = params
        return await self.api.get_sli_dashboard(today_iso, window_days=window_days)

    def _cancel_bg_refresh(self) -> None:
        task = self._bg_refresh_task
        key = self._bg_refresh_key
        self._bg_refresh_task = None
        self._bg_refresh_key = None
        if key is not None:
            self._loading_keys.discard(key)
        if task is not None and not task.done():
            task.cancel()

    def _activate_current_view(self, force_refresh: bool = False) -> None:
        key = self._current_tab_key()
        self._cancel_bg_refresh()
        entry = self._tab_cache.get(key)
        if entry is not None:
            self._apply_tab_data(key[0], entry[0])
            self._loading_keys.discard(key)
            self.render_shell()
            if force_refresh or not self._is_cache_fresh(key):
                self._start_bg_refresh(key)
            return

        self._loading_keys.add(key)
        self.render_shell()
        self._start_bg_refresh(key)

    def _start_bg_refresh(self, key: tuple[int, tuple[Any, ...]]) -> None:
        self._cancel_bg_refresh()
        self._bg_req_id += 1
        req_id = self._bg_req_id
        self._bg_refresh_key = key
        expected_gen = self._tab_generations.get(key[0], 0)
        run_task = getattr(self.page, "run_task", None)
        if callable(run_task):
            self._bg_refresh_task = run_task(
                self._run_bg_refresh, key, expected_gen, req_id
            )
        else:
            self._bg_refresh_task = asyncio.create_task(
                self._run_bg_refresh(key, expected_gen, req_id)
            )

    async def _run_bg_refresh(
        self,
        key: tuple[int, tuple[Any, ...]],
        expected_gen: int,
        req_id: int,
    ) -> None:
        tab = key[0]
        try:
            data = await self._fetch_tab_data(key)
        except asyncio.CancelledError:
            if self._bg_req_id == req_id:
                self._loading_keys.discard(key)
            raise
        except ApiError as err:
            if self._bg_req_id == req_id:
                self._loading_keys.discard(key)
                if self._bg_refresh_key == key:
                    self._bg_refresh_task = None
                    self._bg_refresh_key = None
            if expected_gen != self._tab_generations.get(tab, 0):
                return
            if err.status_code == 401:
                await self.api.logout()
                self._clear_tab_cache()
                self.render_auth_screen()
                return
            if self._current_tab_key() == key:
                self.render_shell()
            show_toast(self.page, err.message, is_error=True)
            return

        if self._bg_refresh_key == key and self._bg_req_id == req_id:
            self._bg_refresh_task = None
            self._bg_refresh_key = None

        if expected_gen != self._tab_generations.get(tab, 0):
            self._loading_keys.discard(key)
            return

        was_loading = key in self._loading_keys
        self._loading_keys.discard(key)
        prev_entry = self._tab_cache.get(key)
        had_prev = prev_entry is not None
        prev_data = prev_entry[0] if prev_entry is not None else None

        if not self._store_cache_entry(key, data, expected_gen):
            return

        if self.api.current_user is None or self._current_tab_key() != key:
            return

        if not was_loading and had_prev and data == prev_data:
            return

        self._apply_tab_data(tab, data)
        self.render_shell()

    def _build_loading_view(self) -> ft.Control:
        return ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.ProgressRing(),
                    ft.Text("Loading...", color=ft.Colors.BLUE_GREY_600),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=12,
            ),
        )

    def _build_active_tab_view(self) -> ft.Control:
        if self._current_tab_key() in self._loading_keys:
            return self._build_loading_view()
        if self.selected_tab == 0:
            return self._build_today_view()
        if self.selected_tab == 1:
            return self._build_schedule_view()
        if self.selected_tab == 2:
            return self._build_habits_view()
        if self.selected_tab == 3:
            return self._build_stats_view()
        return self._build_sli_view()

    async def refresh_current_tab(self, force: bool = True) -> None:
        self._cancel_bg_refresh()
        key = self._current_tab_key()
        tab = key[0]
        if not force and self._is_cache_fresh(key):
            self._apply_tab_data(tab, self._tab_cache[key][0])
            self._loading_keys.discard(key)
            return
        expected_gen = self._tab_generations.get(tab, 0)
        try:
            data = await self._fetch_tab_data(key)
            self._loading_keys.discard(key)
            if self._store_cache_entry(key, data, expected_gen):
                self._apply_tab_data(tab, data)
        except ApiError as err:
            self._loading_keys.discard(key)
            if err.status_code == 401:
                await self.api.logout()
                self._clear_tab_cache()
                self.render_auth_screen()
                return
            show_toast(self.page, err.message, is_error=True)

    def render_shell(self, force_rebuild: bool = False) -> None:
        user_name = (self.api.current_user or {}).get("name", "User")
        wide = self._is_wide()
        self.content_area.content = self._build_active_tab_view()

        if (
            not force_rebuild
            and self._shell_mounted
            and self._shell_root is not None
            and self._shell_nav is not None
            and self._shell_root in self.page.controls
            and self._shell_wide == wide
            and self._shell_user_name == user_name
            and self._shell_reminders_muted == self.reminders_muted
        ):
            nav_changed = self._shell_nav.selected_index != self.selected_tab
            if nav_changed:
                self._shell_nav.selected_index = self.selected_tab
                self._safe_update(self.content_area, self._shell_nav)
            else:
                self._safe_update(self.content_area)
            return

        top_bar = ft.Container(
            bgcolor=ft.Colors.WHITE,
            content=ft.SafeArea(
                avoid_intrusions_bottom=False,
                content=ft.Container(
                    padding=16,
                    content=ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.VERIFIED_ROUNDED, color="#6366F1", size=26),
                                    ft.Text(
                                        "Habit Tracker",
                                        size=19,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        f"Hi, {user_name}",
                                        size=14,
                                        color=ft.Colors.BLUE_GREY_700,
                                    ),
                                    ft.IconButton(
                                        icon=(
                                            ft.Icons.NOTIFICATIONS_OFF_OUTLINED
                                            if self.reminders_muted
                                            else ft.Icons.ALARM_ROUNDED
                                        ),
                                        icon_color=(
                                            "#94A3B8"
                                            if self.reminders_muted
                                            else "#4F46E5"
                                        ),
                                        tooltip="Reminders & Alarms",
                                        on_click=self._handle_open_reminders_center,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.REFRESH_ROUNDED,
                                        tooltip="Refresh",
                                        on_click=self._handle_manual_refresh,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.KEY_ROUNDED,
                                        tooltip="Change Password",
                                        on_click=lambda _e: self._open_change_password_dialog(),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.LOGOUT_ROUNDED,
                                        tooltip="Sign Out",
                                        on_click=self._handle_logout,
                                    ),
                                ],
                                spacing=4,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ),
            ),
        )

        self.page.controls.clear()
        if wide:
            # Mac / Desktop / Wide Web layout: Left NavigationRail
            self.page.navigation_bar = None
            nav_control: ft.NavigationRail | ft.NavigationBar = ft.NavigationRail(
                selected_index=self.selected_tab,
                label_type=ft.NavigationRailLabelType.ALL,
                min_width=92,
                bgcolor=ft.Colors.WHITE,
                on_change=self._on_nav_change,
                destinations=[
                    ft.NavigationRailDestination(
                        icon=ft.Icons.TODAY_OUTLINED,
                        selected_icon=ft.Icons.TODAY_ROUNDED,
                        label="Today",
                    ),
                    ft.NavigationRailDestination(
                        icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                        selected_icon=ft.Icons.CALENDAR_MONTH_ROUNDED,
                        label="Plan",
                    ),
                    ft.NavigationRailDestination(
                        icon=ft.Icons.LIST_ALT_OUTLINED,
                        selected_icon=ft.Icons.LIST_ALT_ROUNDED,
                        label="Habits",
                    ),
                    ft.NavigationRailDestination(
                        icon=ft.Icons.INSIGHTS_OUTLINED,
                        selected_icon=ft.Icons.INSIGHTS_ROUNDED,
                        label="Stats",
                    ),
                    ft.NavigationRailDestination(
                        icon=ft.Icons.SPEED_OUTLINED,
                        selected_icon=ft.Icons.SPEED_ROUNDED,
                        label="SLI",
                    ),
                ],
            )
            shell_root: ft.Control = ft.Column(
                [
                    top_bar,
                    ft.Divider(height=1),
                    ft.Row(
                        [nav_control, ft.VerticalDivider(width=1), self.content_area],
                        expand=True,
                        spacing=0,
                    ),
                ],
                expand=True,
                spacing=0,
            )
        else:
            # iPhone / Android / Mobile Web layout: Bottom NavigationBar
            nav_control = ft.NavigationBar(
                selected_index=self.selected_tab,
                bgcolor=ft.Colors.WHITE,
                on_change=self._on_nav_change,
                destinations=[
                    ft.NavigationBarDestination(
                        icon=ft.Icons.TODAY_OUTLINED,
                        selected_icon=ft.Icons.TODAY_ROUNDED,
                        label="Today",
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                        selected_icon=ft.Icons.CALENDAR_MONTH_ROUNDED,
                        label="Plan",
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.LIST_ALT_OUTLINED,
                        selected_icon=ft.Icons.LIST_ALT_ROUNDED,
                        label="Habits",
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.INSIGHTS_OUTLINED,
                        selected_icon=ft.Icons.INSIGHTS_ROUNDED,
                        label="Stats",
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.SPEED_OUTLINED,
                        selected_icon=ft.Icons.SPEED_ROUNDED,
                        label="SLI",
                    ),
                ],
            )
            self.page.navigation_bar = nav_control
            shell_root = ft.Column(
                [top_bar, ft.Divider(height=1), self.content_area],
                expand=True,
                spacing=0,
            )

        self._shell_nav = nav_control
        self._shell_root = shell_root
        self._shell_wide = wide
        self._shell_user_name = user_name
        self._shell_reminders_muted = self.reminders_muted
        self._shell_mounted = True
        self.page.add(shell_root)
        self.page.update()

    # -----------------------------------------------------------------------
    # Reminders & Alarms Runtime Engine + Center Dialog
    # -----------------------------------------------------------------------
    def _build_reminder_badge_chip(self, habit: dict[str, Any]) -> ft.Control | None:
        badge_text = format_reminder_badge(habit)
        if not badge_text:
            return None
        is_alarm = habit.get("reminder_mode") == "alarm"
        bg = "#FEF3C7" if is_alarm else "#EEF2FF"
        fg = "#B45309" if is_alarm else "#4F46E5"
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            border_radius=8,
            bgcolor=bg,
            content=ft.Text(
                badge_text,
                size=11,
                weight=ft.FontWeight.BOLD,
                color=fg,
            ),
        )

    def _start_reminder_loop(self) -> None:
        if self.api.current_user is None:
            return
        if self._reminder_task is not None and not self._reminder_task.done():
            return
        run_task = getattr(self.page, "run_task", None)
        if callable(run_task):
            self._reminder_task = run_task(self._reminder_loop_worker)
        else:
            self._reminder_task = asyncio.create_task(self._reminder_loop_worker())

    def _cancel_reminder_loop(self) -> None:
        task = self._reminder_task
        self._reminder_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _reminder_loop_worker(self) -> None:
        while self.api.current_user is not None:
            now_dt = datetime.now()
            await self._evaluate_due_reminders(now_dt, fetch_if_empty=False)
            await self._check_mode_phase_transitions(now_dt)
            await asyncio.sleep(15.0)

    async def _check_mode_phase_transitions(self, now_dt: datetime) -> None:
        if self.api.current_user is None:
            return
        today_date = now_dt.date()
        today_iso = today_date.isoformat()
        now_hhmm = now_dt.strftime("%H:%M")

        self._notified_mode_phases = {
            k: v
            for k, v in self._notified_mode_phases.items()
            if k.startswith(f"{today_iso}|")
        }

        today_key = (0, (today_iso,))
        today_cache = self._tab_cache.get(today_key)
        items = (
            today_cache[0]
            if (today_cache is not None and isinstance(today_cache[0], list))
            else (self.today_habits if self.selected_date == today_date else [])
        )
        if not items:
            return

        changed_to_notify: list[tuple[str, bool]] = []
        for item in items:
            mode = item.get("mode") or "free"
            if mode == "free" or not item.get("scheduled_today", True):
                continue
            hid = str(item.get("id") or "")
            if not hid:
                continue
            day_status, reason, _, _ = evaluate_local_habit_status(
                item, today_iso, today_iso, now_hhmm
            )
            phase_key = f"{today_iso}|{hid}"
            prev_phase = self._notified_mode_phases.get(phase_key)
            if day_status != prev_phase:
                self._notified_mode_phases[phase_key] = day_status
                if day_status == "reminding" and not self.reminders_muted:
                    if mode == "strict":
                        msg = f"🔔「{item['title']}」已到开始提醒时间，请在 {item.get('force_start_time', '')} 前点击开始执行"
                    elif mode == "window":
                        msg = f"🔔「{item['title']}」已进入弹性打卡窗口，请在 {item.get('force_end_time', '')} 前完成"
                    else:
                        msg = f"🔔「{item['title']}」已到提醒时间（{item.get('remind_time', '')}）"
                    changed_to_notify.append((msg, False))
                elif day_status == "violation":
                    why = "未在强制执行时间前开始" if reason == "missed_start" else "未在强制完成时间前完成"
                    changed_to_notify.append(
                        (f"⚠️「{item['title']}」{why}，已记为超时违规（支持补卡）", True)
                    )

        for msg, is_err in changed_to_notify:
            show_toast(self.page, msg, is_error=is_err)

        if (
            changed_to_notify
            and self.selected_tab == 0
            and self.selected_date == today_date
            and self._shell_mounted
        ):
            self.render_shell()

    async def _trigger_haptic(self, heavy: bool = False) -> None:
        if not hasattr(ft, "HapticFeedback"):
            return
        services = getattr(self.page, "services", None)
        if not isinstance(services, list):
            return
        try:
            if self._haptic is None:
                self._haptic = ft.HapticFeedback()
            if self._haptic not in services:
                services.append(self._haptic)
            if heavy:
                await self._haptic.heavy_impact()
            else:
                await self._haptic.light_impact()
        except Exception:
            pass

    async def _evaluate_due_reminders(
        self,
        now_dt: datetime,
        fetch_if_empty: bool = True,
    ) -> list[dict[str, Any]]:
        today_iso = now_dt.date().isoformat()
        # Keep fired keys bounded to current day + snoozes
        self._fired_reminder_keys = {
            k
            for k in self._fired_reminder_keys
            if k.startswith(f"{today_iso}|") or k.startswith("snooze|")
        }

        if self.reminders_muted or self.api.current_user is None:
            return []

        today_key = (0, (today_iso,))
        today_cache = self._tab_cache.get(today_key)
        all_key = (2, (False,))
        all_cache = self._tab_cache.get(all_key)

        habits: list[dict[str, Any]] = []
        completed_ids: set[str] = set()

        if today_cache is not None and isinstance(today_cache[0], list):
            habits = today_cache[0]
        elif self.selected_date == now_dt.date() and self.today_habits:
            habits = self.today_habits
        elif all_cache is not None and isinstance(all_cache[0], list):
            habits = all_cache[0]
        elif self.all_habits:
            habits = self.all_habits
        elif fetch_if_empty:
            try:
                habits = await self.api.get_today_habits(today_iso)
                gen = self._tab_generations.get(0, 0)
                self._store_cache_entry(today_key, habits, gen)
                if self.selected_date == now_dt.date():
                    self.today_habits = habits
            except ApiError:
                return []

        completed_source = (
            today_cache[0]
            if (today_cache is not None and isinstance(today_cache[0], list))
            else (self.today_habits if self.selected_date == now_dt.date() else [])
        )
        for item in completed_source:
            if item.get("completed"):
                hid = str(item.get("id") or item.get("habit_id") or "")
                if hid:
                    completed_ids.add(hid)

        due = find_due_habit_reminders(
            habits=habits,
            completed_ids=completed_ids,
            snoozed_until=self._snoozed_alarms,
            fired_keys=self._fired_reminder_keys,
            now_dt=now_dt,
        )
        for trigger in due:
            self._fired_reminder_keys.add(trigger["fire_key"])
            habit = trigger["habit"]
            hid = str(habit.get("id") or habit.get("habit_id") or "")
            if trigger["is_snooze"]:
                self._snoozed_alarms.pop(hid, None)
            if trigger["mode"] == "alarm":
                await self._trigger_haptic(heavy=True)
                self._open_ringing_alarm_dialog(habit, trigger["time_label"])
            else:
                await self._trigger_haptic(heavy=False)
                note = (habit.get("reminder_message") or "").strip()
                suffix = f" — {note}" if note else ""
                show_toast(
                    self.page,
                    f"🔔 Reminder ({trigger['time_label']}): {habit.get('title', 'Habit')}{suffix}",
                )
        return due

    def _open_ringing_alarm_dialog(
        self,
        habit: dict[str, Any],
        time_label: str,
    ) -> None:
        hid = str(habit.get("id") or habit.get("habit_id") or "")
        title = habit.get("title", "Habit Alarm")
        color = habit.get("color", "#6366F1")
        snooze_minutes = max(1, int(habit.get("reminder_snooze_minutes", 10)))
        target = int(habit.get("target_per_day", 1))
        message = (habit.get("reminder_message") or "").strip() or (
            habit.get("description") or ""
        ).strip() or "Time to complete your scheduled habit!"

        if self._active_alarm_dialog is not None:
            close_dialog(self.page, self._active_alarm_dialog)
            self._active_alarm_dialog = None

        dialog = ft.AlertDialog(modal=True)
        self._active_alarm_dialog = dialog
        self._active_alarm_habit_id = hid

        def _clear_active() -> None:
            if self._active_alarm_dialog is dialog:
                self._active_alarm_dialog = None
                self._active_alarm_habit_id = None

        async def handle_checkin_now(_e: Any = None) -> None:
            _clear_active()
            self._snoozed_alarms.pop(hid, None)
            close_dialog(self.page, dialog)
            if not hid or hid == "__test__":
                show_toast(self.page, f"Checked in! Alarm dismissed for {title}.")
                return
            try:
                now_dt = datetime.now()
                today_iso = now_dt.date().isoformat()
                now_hhmm = now_dt.strftime("%H:%M")
                _, _, can_start, _ = evaluate_local_habit_status(
                    habit, today_iso, today_iso, now_hhmm
                )
                if habit.get("mode") == "strict" and can_start:
                    action = "start"
                    toast_msg = f"Started execution: {title}"
                else:
                    action = "toggle" if target <= 1 else "increment"
                    toast_msg = f"Checked in: {title}"
                await self.api.checkin_habit(
                    habit_id=hid,
                    target_date=today_iso,
                    action=action,
                )
                self._invalidate_tabs({0, 1, 3, 4})
                await self.refresh_current_tab(force=True)
                self.render_shell()
                show_toast(self.page, toast_msg)
            except ApiError as err:
                show_toast(self.page, err.message, is_error=True)

        async def handle_snooze(_e: Any = None) -> None:
            _clear_active()
            wake_dt = datetime.now() + timedelta(minutes=snooze_minutes)
            self._snoozed_alarms[hid] = (wake_dt, habit)
            close_dialog(self.page, dialog)
            show_toast(
                self.page,
                f"⏰ Snoozed {title} for {snooze_minutes} min (until {wake_dt.strftime('%H:%M')})",
            )

        def handle_dismiss(_e: Any = None) -> None:
            _clear_active()
            close_dialog(self.page, dialog)

        dialog.title = ft.Row(
            [
                ft.Icon(ft.Icons.ALARM_ON_ROUNDED, color=color, size=28),
                ft.Column(
                    [
                        ft.Text("Habit Alarm", size=18, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            f"Scheduled for {time_label}",
                            size=12,
                            color=ft.Colors.BLUE_GREY_500,
                        ),
                    ],
                    spacing=1,
                    tight=True,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        dialog.content = ft.Container(
            width=360,
            padding=16,
            border_radius=12,
            bgcolor="#FFFBEB",
            border=ft.Border.all(1.5, color),
            content=ft.Column(
                [
                    ft.Text(
                        title,
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_GREY_900,
                    ),
                    ft.Text(
                        message,
                        size=14,
                        color=ft.Colors.BLUE_GREY_700,
                    ),
                ],
                tight=True,
                spacing=8,
            ),
        )
        dialog.actions = [
            ft.TextButton(
                content=ft.Text("Dismiss"),
                on_click=handle_dismiss,
            ),
            ft.OutlinedButton(
                content=ft.Text(f"Snooze {snooze_minutes}m"),
                on_click=handle_snooze,
            ),
            ft.FilledButton(
                content=ft.Text("Check In Now"),
                on_click=handle_checkin_now,
            ),
        ]
        open_dialog(self.page, dialog)

    async def _handle_open_reminders_center(self, _e: Any = None) -> None:
        await self._open_reminders_center_dialog()

    async def _open_reminders_center_dialog(self) -> None:
        source_habits = self.all_habits or self.today_habits
        if not source_habits and self.api.current_user is not None:
            try:
                source_habits = await self.api.list_habits(include_archived=False)
                self.all_habits = source_habits
            except ApiError:
                source_habits = []

        reminder_habits = [
            h
            for h in source_habits
            if not h.get("archived", False) and h.get("reminder_enabled", False)
        ]
        dialog = ft.AlertDialog(modal=True)

        async def on_mute_change(e: Any) -> None:
            self.reminders_muted = bool(e.control.value)
            await self.storage.set(
                STORAGE_REMINDERS_MUTED_KEY,
                "true" if self.reminders_muted else "false",
            )
            self.render_shell(force_rebuild=True)
            show_toast(
                self.page,
                "Reminders & alarms muted on this device"
                if self.reminders_muted
                else "Reminders & alarms active on this device",
            )

        def test_notification(_e: Any) -> None:
            close_dialog(self.page, dialog)
            show_toast(
                self.page,
                "🔔 Reminder preview: Stay consistent with your daily routine!",
            )

        def test_alarm(_e: Any) -> None:
            close_dialog(self.page, dialog)
            sample = (
                reminder_habits[0]
                if reminder_habits
                else {
                    "id": "__test__",
                    "title": "Sample Habit Alarm",
                    "color": "#6366F1",
                    "target_per_day": 1,
                    "reminder_mode": "alarm",
                    "reminder_snooze_minutes": 10,
                    "reminder_message": "This is how a ringing habit alarm looks and behaves.",
                }
            )
            self._open_ringing_alarm_dialog(sample, datetime.now().strftime("%H:%M"))

        def cancel_snooze(hid: str) -> None:
            self._snoozed_alarms.pop(hid, None)
            close_dialog(self.page, dialog)
            show_toast(self.page, "Snoozed alarm cancelled")

        def open_edit(h: dict[str, Any]) -> None:
            close_dialog(self.page, dialog)
            self._open_habit_dialog(h)

        rows: list[ft.Control] = [
            ft.Switch(
                label="Mute Reminders & Alarms on this device",
                value=self.reminders_muted,
                on_change=on_mute_change,
            ),
            ft.Row(
                [
                    ft.OutlinedButton(
                        content=ft.Text("Test Notification"),
                        on_click=test_notification,
                    ),
                    ft.OutlinedButton(
                        content=ft.Text("Test Ringing Alarm"),
                        on_click=test_alarm,
                    ),
                ],
                wrap=True,
                spacing=8,
            ),
            ft.Divider(height=1),
        ]

        if self._snoozed_alarms:
            rows.append(
                ft.Text("Snoozed Alarms", size=14, weight=ft.FontWeight.BOLD)
            )
            for s_hid, (wake_dt, s_habit) in list(self._snoozed_alarms.items()):
                rows.append(
                    ft.Row(
                        [
                            ft.Text(
                                f"⏰ {s_habit.get('title', '')} → {wake_dt.strftime('%H:%M')}",
                                size=13,
                            ),
                            ft.TextButton(
                                content=ft.Text("Cancel"),
                                on_click=lambda _e, target_id=s_hid: cancel_snooze(
                                    target_id
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    )
                )
            rows.append(ft.Divider(height=1))

        rows.append(
            ft.Text(
                f"Configured Habit Alerts ({len(reminder_habits)})",
                size=14,
                weight=ft.FontWeight.BOLD,
            )
        )
        if not reminder_habits:
            rows.append(
                ft.Text(
                    "No habit reminders or alarms configured yet. Edit any habit to set reminder times and alert mode.",
                    size=13,
                    color=ft.Colors.BLUE_GREY_500,
                )
            )
        else:
            for h in reminder_habits:
                mode_label = (
                    "Alarm" if h.get("reminder_mode") == "alarm" else "Notification"
                )
                times_str = ", ".join(h.get("reminder_times") or [])
                snooze_mins = h.get("reminder_snooze_minutes", 10)
                rows.append(
                    ft.Container(
                        padding=10,
                        border_radius=10,
                        bgcolor="#F8FAFC",
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            h.get("title", ""),
                                            size=14,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        ft.Text(
                                            f"{mode_label} • {times_str} • Snooze {snooze_mins}m",
                                            size=12,
                                            color=ft.Colors.BLUE_GREY_600,
                                        ),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.EDIT_OUTLINED,
                                    tooltip="Edit reminder settings",
                                    on_click=lambda _e, target_h=h: open_edit(target_h),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    )
                )

        dialog.title = ft.Text("Reminders & Alarms")
        dialog.content = ft.Container(
            width=400,
            content=ft.Column(
                rows,
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        dialog.actions = [
            ft.TextButton(
                content=ft.Text("Close"),
                on_click=lambda _e: close_dialog(self.page, dialog),
            )
        ]
        open_dialog(self.page, dialog)

    # -----------------------------------------------------------------------
    # Tab 1: Today's Routine & Check-ins
    # -----------------------------------------------------------------------
    def _build_today_view(self) -> ft.Control:
        is_today = self.selected_date == date.today()
        date_title = (
            "Today"
            if is_today
            else self.selected_date.strftime("%a, %b %d, %Y")
        )

        async def shift_date(delta: int) -> None:
            new_date = self.selected_date + timedelta(days=delta)
            if new_date <= date.today():
                self.selected_date = new_date
                self._activate_current_view()

        async def prev_day(_e: Any) -> None:
            await shift_date(-1)

        async def next_day(_e: Any) -> None:
            await shift_date(1)

        now_dt = datetime.now()
        today_iso = now_dt.date().isoformat()
        now_hhmm = now_dt.strftime("%H:%M")
        selected_iso = self.selected_date.isoformat()

        scheduled_items = [h for h in self.today_habits if h.get("scheduled_today")]
        extra_items = [h for h in self.today_habits if not h.get("scheduled_today")]
        eval_by_id: dict[str, tuple[str, str | None, bool, bool]] = {
            str(h["id"]): evaluate_local_habit_status(
                h, selected_iso, today_iso, now_hhmm
            )
            for h in self.today_habits
        }
        done_count = sum(
            1
            for h in scheduled_items
            if eval_by_id[str(h["id"])][0] == "on_time"
        )
        late_count = sum(
            1
            for h in scheduled_items
            if eval_by_id[str(h["id"])][0] == "late_makeup"
        )
        violation_count = sum(
            1
            for h in scheduled_items
            if eval_by_id[str(h["id"])][0] == "violation"
        )
        reminding_items = [
            h
            for h in scheduled_items
            if eval_by_id[str(h["id"])][0] == "reminding"
        ]
        violated_items = [
            h
            for h in scheduled_items
            if eval_by_id[str(h["id"])][0] == "violation"
        ]
        total_sched = len(scheduled_items)
        progress_val = (done_count / total_sched) if total_sched > 0 else 0.0

        header_row = ft.Row(
            [
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.CHEVRON_LEFT_ROUNDED,
                            on_click=prev_day,
                            tooltip="Previous day",
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    date_title,
                                    size=22,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    self.selected_date.isoformat(),
                                    size=12,
                                    color=ft.Colors.BLUE_GREY_500,
                                ),
                            ],
                            spacing=2,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CHEVRON_RIGHT_ROUNDED,
                            disabled=is_today,
                            on_click=next_day,
                            tooltip="Next day",
                        ),
                    ],
                    spacing=4,
                ),
                ft.FilledButton(
                    icon=ft.Icons.ADD_ROUNDED,
                    content=ft.Text("New Habit"),
                    on_click=lambda _e: self._open_habit_dialog(),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            wrap=True,
        )

        progress_chips: list[ft.Control] = []
        if late_count > 0:
            progress_chips.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    border_radius=8,
                    bgcolor="#FEF3C7",
                    content=ft.Text(
                        f"超时补卡 {late_count} 项（不计入连胜/准时率）",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color="#B45309",
                    ),
                )
            )
        if violation_count > 0:
            progress_chips.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    border_radius=8,
                    bgcolor="#FEE2E2",
                    content=ft.Text(
                        f"超时违规 {violation_count} 项",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color="#B91C1C",
                    ),
                )
            )

        progress_col_controls: list[ft.Control] = [
            ft.Row(
                [
                    ft.Text(
                        "Daily Routine Progress",
                        weight=ft.FontWeight.BOLD,
                        size=15,
                    ),
                    ft.Text(
                        f"{done_count} / {total_sched} completed",
                        weight=ft.FontWeight.BOLD,
                        color="#4F46E5",
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.ProgressBar(
                value=progress_val,
                color="#4F46E5",
                bgcolor=ft.Colors.WHITE,
                height=10,
                border_radius=5,
            ),
        ]
        if progress_chips:
            progress_col_controls.append(
                ft.Row(progress_chips, spacing=8, wrap=True)
            )

        progress_card = ft.Container(
            padding=18,
            border_radius=14,
            bgcolor="#EEF2FF",
            content=ft.Column(
                progress_col_controls,
                spacing=10,
            ),
        )

        cards: list[ft.Control] = [header_row, progress_card]

        if violated_items or reminding_items:
            banner_parts: list[str] = []
            if violated_items:
                names = "、".join(h["title"] for h in violated_items[:3])
                banner_parts.append(f"⚠️ 超时违规（可一键补卡）：{names}")
            if reminding_items:
                names = "、".join(h["title"] for h in reminding_items[:3])
                banner_parts.append(f"🔔 正在提醒：{names}")
            is_violation_banner = bool(violated_items)
            cards.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                    border_radius=12,
                    bgcolor="#FEF2F2" if is_violation_banner else "#FFFBEB",
                    border=ft.Border.all(
                        1, "#FECACA" if is_violation_banner else "#FDE68A"
                    ),
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.WARNING_AMBER_ROUNDED
                                if is_violation_banner
                                else ft.Icons.NOTIFICATIONS_ACTIVE_ROUNDED,
                                color="#DC2626" if is_violation_banner else "#D97706",
                                size=20,
                            ),
                            ft.Text(
                                "  |  ".join(banner_parts),
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color="#991B1B" if is_violation_banner else "#92400E",
                                expand=True,
                            ),
                        ],
                        spacing=10,
                    ),
                )
            )

        if not scheduled_items and not extra_items:
            cards.append(
                ft.Container(
                    padding=36,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Column(
                        [
                            ft.Icon(
                                ft.Icons.SELF_IMPROVEMENT_ROUNDED,
                                size=48,
                                color=ft.Colors.BLUE_GREY_300,
                            ),
                            ft.Text(
                                "No habits yet — tap 'New Habit' to create your first daily routine!",
                                color=ft.Colors.BLUE_GREY_600,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                )
            )
        else:
            for item in scheduled_items:
                cards.append(self._build_today_habit_card(item))

            if extra_items:
                cards.append(
                    ft.Text(
                        "Unscheduled Today (Optional)",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_GREY_500,
                    )
                )
                for item in extra_items:
                    cards.append(self._build_today_habit_card(item))

        return ft.Column(cards, scroll=ft.ScrollMode.AUTO, expand=True, spacing=14)

    def _build_today_habit_card(self, item: dict[str, Any]) -> ft.Control:
        hid = item["id"]
        completed = item.get("completed", False)
        count = item.get("count", 0)
        target = item.get("target_per_day", 1)
        color = item.get("color", "#6366F1")
        streak = item.get("current_streak", 0)
        is_monthly = item.get("frequency_type") == "monthly"
        streak_unit = "mo" if is_monthly else "d"
        mode = item.get("mode") or "free"

        now_dt = datetime.now()
        today_iso = now_dt.date().isoformat()
        now_hhmm = now_dt.strftime("%H:%M")
        target_iso = item.get("date") or self.selected_date.isoformat()
        day_status, violation_reason, can_start, is_late = (
            evaluate_local_habit_status(item, target_iso, today_iso, now_hhmm)
        )

        async def do_checkin(action: str) -> None:
            try:
                updated = await self.api.checkin_habit(
                    habit_id=hid,
                    target_date=self.selected_date.isoformat(),
                    action=action,
                )
                key = self._current_tab_key(0)
                if isinstance(updated, dict) and updated.get("id"):
                    self.today_habits = [
                        updated if h.get("id") == updated.get("id") else h
                        for h in self.today_habits
                    ]
                    self._invalidate_tabs({1, 3, 4})
                    self._tab_generations[0] = self._tab_generations.get(0, 0) + 1
                    self._store_cache_entry(
                        key,
                        self.today_habits,
                        self._tab_generations[0],
                    )
                    self.render_shell()
                else:
                    self._invalidate_tabs({0, 1, 3, 4})
                    await self.refresh_current_tab(force=True)
                    self.render_shell()
            except ApiError as err:
                show_toast(self.page, err.message, is_error=True)

        async def on_start_tap(_e: Any) -> None:
            await do_checkin("start")

        async def on_primary_tap(_e: Any) -> None:
            if target == 1:
                await do_checkin("toggle")
            else:
                await do_checkin("increment")

        async def on_decrement(_e: Any) -> None:
            await do_checkin("decrement")

        controls_right: list[ft.Control] = [
            ft.Container(
                padding=6,
                border_radius=8,
                bgcolor="#FEF3C7" if streak > 0 else "#F1F5F9",
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                            size=16,
                            color="#D97706" if streak > 0 else ft.Colors.BLUE_GREY_400,
                        ),
                        ft.Text(
                            f"{streak}{streak_unit}",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color="#B45309" if streak > 0 else ft.Colors.BLUE_GREY_500,
                        ),
                    ],
                    spacing=3,
                    tight=True,
                ),
            )
        ]

        if target > 1 and count > 0 and not can_start:
            controls_right.append(
                ft.IconButton(
                    icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    icon_size=22,
                    tooltip="Decrease count",
                    on_click=on_decrement,
                )
            )

        if can_start:
            controls_right.append(
                ft.FilledButton(
                    content=ft.Text("开始执行"),
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    on_click=on_start_tap,
                )
            )
        elif day_status == "violation":
            controls_right.append(
                ft.FilledButton(
                    content=ft.Text("超时补卡"),
                    icon=ft.Icons.HISTORY_ROUNDED,
                    style=ft.ButtonStyle(bgcolor="#DC2626", color=ft.Colors.WHITE),
                    on_click=on_primary_tap,
                )
            )
        else:
            controls_right.append(
                ft.IconButton(
                    icon=(
                        ft.Icons.CHECK_CIRCLE_ROUNDED
                        if completed
                        else (
                            ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED
                            if target > 1
                            else ft.Icons.RADIO_BUTTON_UNCHECKED_ROUNDED
                        )
                    ),
                    icon_color=(
                        "#D97706"
                        if is_late
                        else (color if completed else ft.Colors.BLUE_GREY_400)
                    ),
                    icon_size=30,
                    tooltip="Check in",
                    on_click=on_primary_tap,
                )
            )

        subtitle_parts = []
        mode_summary = format_habit_mode_summary(item)
        if mode_summary:
            subtitle_parts.append(mode_summary)
        if day_status == "in_progress" and item.get("started_at_time"):
            subtitle_parts.append(f"已于 {item['started_at_time']} 开始")
        elif day_status == "violation":
            reason_label = (
                "未按时开始" if violation_reason == "missed_start" else "未按时完成"
            )
            subtitle_parts.append(reason_label)
        if is_monthly:
            subtitle_parts.append(format_habit_schedule(item))
        if target > 1:
            subtitle_parts.append(f"{count} / {target} today")
        if item.get("description"):
            subtitle_parts.append(item["description"])
        subtitle = " • ".join(subtitle_parts)
        reminder_badge = self._build_reminder_badge_chip(item)
        title_controls: list[ft.Control] = [
            ft.Text(
                item["title"],
                size=16,
                weight=ft.FontWeight.BOLD,
            )
        ]

        status_badge_styles = {
            "reminding": ("开始提醒中", "#DBEAFE", "#1D4ED8"),
            "in_progress": ("执行中", "#E0E7FF", "#4338CA"),
            "on_time": ("准时完成", "#DCFCE7", "#15803D"),
            "violation": ("超时违规", "#FEE2E2", "#B91C1C"),
            "late_makeup": ("超时补卡", "#FEF3C7", "#B45309"),
            "pending": ("待开始" if mode == "strict" else "待打卡", "#F1F5F9", "#475569"),
        }
        if mode != "free" or day_status in ("violation", "late_makeup"):
            st_label, st_bg, st_fg = status_badge_styles.get(
                day_status, ("待打卡", "#F1F5F9", "#475569")
            )
            title_controls.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    border_radius=8,
                    bgcolor=st_bg,
                    content=ft.Text(
                        st_label,
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=st_fg,
                    ),
                )
            )
        if reminder_badge is not None:
            title_controls.append(reminder_badge)

        return ft.Container(
            padding=16,
            bgcolor=ft.Colors.WHITE,
            border_radius=14,
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=12,
                                height=42,
                                border_radius=6,
                                bgcolor=color,
                            ),
                            ft.Column(
                                [
                                    ft.Row(
                                        title_controls,
                                        spacing=8,
                                        wrap=True,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    ),
                                    ft.Text(
                                        subtitle if subtitle else "Daily goal",
                                        size=12,
                                        color=ft.Colors.BLUE_GREY_500,
                                    ),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=12,
                    ),
                    ft.Row(controls_right, spacing=6),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

    # -----------------------------------------------------------------------
    # Tab 1: This Week / This Month Jobs To Be Done
    # -----------------------------------------------------------------------
    @staticmethod
    def _shift_month(anchor: date, delta_months: int) -> date:
        total_months = (anchor.year * 12 + (anchor.month - 1)) + delta_months
        new_year, month_zero = divmod(total_months, 12)
        new_month = month_zero + 1
        max_day = calendar.monthrange(new_year, new_month)[1]
        return date(new_year, new_month, min(anchor.day, max_day))

    def _build_schedule_view(self) -> ft.Control:
        data = self.period_schedule or {}
        today_obj = date.today()
        today_iso = today_obj.isoformat()
        period = data.get("period", self.schedule_period)
        start_str = data.get("start_date", "")
        end_str = data.get("end_date", "")

        if start_str and end_str:
            if period == "week":
                is_current = start_str <= today_iso <= end_str
                start_dt = date.fromisoformat(start_str)
                period_title = (
                    "This Week"
                    if is_current
                    else f"Week of {start_dt.strftime('%b %d, %Y')}"
                )
            else:
                is_current = start_str[:7] == today_iso[:7]
                start_dt = date.fromisoformat(start_str)
                period_title = (
                    "This Month"
                    if is_current
                    else start_dt.strftime("%B %Y")
                )
            range_subtitle = f"{start_str} – {end_str}"
        else:
            is_current = True
            period_title = "This Week" if self.schedule_period == "week" else "This Month"
            range_subtitle = ""

        async def select_period(new_period: str) -> None:
            if self.schedule_period == new_period and self.period_schedule is not None:
                return
            self.schedule_period = new_period
            self.schedule_anchor_date = date.today()
            self._activate_current_view()

        async def shift_period(delta: int) -> None:
            if self.schedule_period == "week":
                self.schedule_anchor_date = self.schedule_anchor_date + timedelta(
                    days=7 * delta
                )
            else:
                self.schedule_anchor_date = self._shift_month(
                    self.schedule_anchor_date, delta
                )
            self._activate_current_view()

        async def jump_current(_e: Any) -> None:
            self.schedule_anchor_date = date.today()
            self._activate_current_view()

        week_btn = (
            ft.FilledButton(
                content=ft.Text("This Week"),
                on_click=lambda _e: select_period("week"),
            )
            if self.schedule_period == "week"
            else ft.OutlinedButton(
                content=ft.Text("This Week"),
                on_click=lambda _e: select_period("week"),
            )
        )
        month_btn = (
            ft.FilledButton(
                content=ft.Text("This Month"),
                on_click=lambda _e: select_period("month"),
            )
            if self.schedule_period == "month"
            else ft.OutlinedButton(
                content=ft.Text("This Month"),
                on_click=lambda _e: select_period("month"),
            )
        )

        nav_controls: list[ft.Control] = [
            ft.IconButton(
                icon=ft.Icons.CHEVRON_LEFT_ROUNDED,
                tooltip="Previous period",
                on_click=lambda _e: shift_period(-1),
            ),
            ft.Column(
                [
                    ft.Text(period_title, size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        range_subtitle,
                        size=12,
                        color=ft.Colors.BLUE_GREY_500,
                        visible=bool(range_subtitle),
                    ),
                ],
                spacing=2,
            ),
            ft.IconButton(
                icon=ft.Icons.CHEVRON_RIGHT_ROUNDED,
                tooltip="Next period",
                on_click=lambda _e: shift_period(1),
            ),
        ]
        if not is_current:
            nav_controls.append(
                ft.TextButton(
                    content=ft.Text("Current"),
                    on_click=jump_current,
                )
            )

        header_row = ft.Row(
            [
                ft.Row(nav_controls, spacing=4),
                ft.Row([week_btn, month_btn], spacing=8),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            wrap=True,
        )

        total_sched = int(data.get("total_scheduled", 0))
        completed_cnt = int(data.get("completed_count", 0))
        remaining_cnt = int(data.get("remaining_count", 0))
        overdue_cnt = int(data.get("overdue_count", 0))
        comp_rate = float(data.get("completion_rate", 0.0))
        progress_val = (completed_cnt / total_sched) if total_sched > 0 else 0.0

        summary_right = f"{remaining_cnt} left"
        if overdue_cnt > 0:
            summary_right += f" • {overdue_cnt} missed"

        summary_card = ft.Container(
            padding=18,
            border_radius=14,
            bgcolor="#EEF2FF",
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Jobs To Be Done (Week)"
                                if self.schedule_period == "week"
                                else "Jobs To Be Done (Month)",
                                weight=ft.FontWeight.BOLD,
                                size=15,
                            ),
                            ft.Text(
                                summary_right,
                                weight=ft.FontWeight.BOLD,
                                color="#4F46E5",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        wrap=True,
                    ),
                    ft.ProgressBar(
                        value=progress_val,
                        color="#4F46E5",
                        bgcolor=ft.Colors.WHITE,
                        height=10,
                        border_radius=5,
                    ),
                    ft.Text(
                        f"{completed_cnt} / {total_sched} completed ({comp_rate}%)",
                        size=12,
                        color=ft.Colors.BLUE_GREY_600,
                    ),
                ],
                spacing=10,
            ),
        )

        def set_filter(val: str) -> None:
            self.schedule_filter = val
            self.render_shell()

        def set_group_by(val: str) -> None:
            self.schedule_group_by = val
            self.render_shell()

        filter_chips = ft.Row(
            [
                ft.Chip(
                    label=ft.Text(f"To Do ({remaining_cnt})"),
                    selected=(self.schedule_filter == "todo"),
                    show_checkmark=False,
                    on_select=lambda _e: set_filter("todo"),
                ),
                ft.Chip(
                    label=ft.Text(f"Missed ({overdue_cnt})"),
                    selected=(self.schedule_filter == "overdue"),
                    show_checkmark=False,
                    on_select=lambda _e: set_filter("overdue"),
                ),
                ft.Chip(
                    label=ft.Text(f"All ({total_sched})"),
                    selected=(self.schedule_filter == "all"),
                    show_checkmark=False,
                    on_select=lambda _e: set_filter("all"),
                ),
                ft.Container(width=8),
                ft.Chip(
                    label=ft.Text("By Day"),
                    selected=(self.schedule_group_by == "day"),
                    show_checkmark=False,
                    on_select=lambda _e: set_group_by("day"),
                ),
                ft.Chip(
                    label=ft.Text("By Habit"),
                    selected=(self.schedule_group_by == "habit"),
                    show_checkmark=False,
                    on_select=lambda _e: set_group_by("habit"),
                ),
            ],
            wrap=True,
            spacing=8,
            run_spacing=8,
        )

        body_controls: list[ft.Control] = [header_row, summary_card, filter_chips]

        if total_sched == 0:
            body_controls.append(
                self._schedule_empty_state(
                    "No scheduled habits in this period yet. Add or edit a habit to plan your week and month!"
                )
            )
            return ft.Column(
                body_controls, scroll=ft.ScrollMode.AUTO, expand=True, spacing=14
            )

        if self.schedule_group_by == "habit":
            summaries = data.get("habit_summaries", [])
            if self.schedule_filter == "todo":
                filtered_summaries = [
                    h for h in summaries if int(h.get("remaining_days", 0)) > 0
                ]
            elif self.schedule_filter == "overdue":
                filtered_summaries = [
                    h for h in summaries if int(h.get("overdue_days", 0)) > 0
                ]
            else:
                filtered_summaries = list(summaries)

            if not filtered_summaries:
                body_controls.append(
                    self._schedule_empty_state(
                        "Nothing pending for this filter — you are all caught up!"
                    )
                )
            else:
                for h_sum in filtered_summaries:
                    body_controls.append(
                        self._build_schedule_habit_summary_card(h_sum)
                    )
        else:
            day_cards_added = 0
            for day in data.get("days", []):
                items = day.get("items", [])
                if self.schedule_filter == "todo":
                    filtered_items = [
                        it
                        for it in items
                        if it.get("status") in ("today", "upcoming")
                    ]
                elif self.schedule_filter == "overdue":
                    filtered_items = [
                        it for it in items if it.get("status") == "overdue"
                    ]
                else:
                    filtered_items = list(items)

                if not filtered_items:
                    continue

                day_cards_added += 1
                day_dt = date.fromisoformat(day["date"])
                formatted_day = day_dt.strftime("%a, %b %d")
                is_today = bool(day.get("is_today"))
                is_future = bool(day.get("is_future"))
                day_header_title = (
                    f"Today • {formatted_day}" if is_today else formatted_day
                )

                day_rows = [
                    self._build_schedule_day_item_row(it, is_future=is_future)
                    for it in filtered_items
                ]

                body_controls.append(
                    ft.Container(
                        padding=16,
                        bgcolor=ft.Colors.WHITE,
                        border_radius=14,
                        border=(
                            ft.Border.all(1.5, "#6366F1")
                            if is_today
                            else ft.Border.all(1, "#E2E8F0")
                        ),
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            day_header_title,
                                            size=15,
                                            weight=ft.FontWeight.BOLD,
                                            color=(
                                                "#4F46E5"
                                                if is_today
                                                else ft.Colors.BLUE_GREY_900
                                            ),
                                        ),
                                        ft.Text(
                                            f"{day.get('completed_count', 0)} / {day.get('scheduled_count', 0)} done",
                                            size=12,
                                            weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.BLUE_GREY_500,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.Divider(height=1),
                                *day_rows,
                            ],
                            spacing=10,
                        ),
                    )
                )

            if day_cards_added == 0:
                body_controls.append(
                    self._schedule_empty_state(
                        "Nothing pending for this filter — you are all caught up!"
                    )
                )

        return ft.Column(
            body_controls, scroll=ft.ScrollMode.AUTO, expand=True, spacing=14
        )

    def _schedule_empty_state(self, message: str) -> ft.Control:
        return ft.Container(
            padding=32,
            bgcolor=ft.Colors.WHITE,
            border_radius=14,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Icon(
                        ft.Icons.DONE_ALL_ROUNDED,
                        size=44,
                        color=ft.Colors.BLUE_GREY_300,
                    ),
                    ft.Text(
                        message,
                        color=ft.Colors.BLUE_GREY_600,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
        )

    def _build_schedule_habit_summary_card(self, summary: dict[str, Any]) -> ft.Control:
        color = summary.get("color", "#6366F1")
        sched = int(summary.get("scheduled_days", 0))
        comp = int(summary.get("completed_days", 0))
        rem = int(summary.get("remaining_days", 0))
        ov = int(summary.get("overdue_days", 0))
        next_due = summary.get("next_due_date")
        ratio = (comp / sched) if sched > 0 else 0.0
        sched_desc = format_habit_schedule(summary)

        if rem > 0 and ov > 0:
            right_label = f"{rem}d left • {ov}d missed"
            right_color = "#B45309"
        elif rem > 0:
            right_label = f"{rem}d left"
            right_color = "#4F46E5"
        elif ov > 0:
            right_label = f"{ov}d missed"
            right_color = "#DC2626"
        else:
            right_label = "All done!"
            right_color = "#059669"

        sub_right = f"Next: {next_due}" if next_due else f"{comp}/{sched} done"
        rem_badge = format_reminder_badge(summary)
        summary_meta = f"{sched_desc} • Goal: {summary.get('target_per_day', 1)}/day"
        if rem_badge:
            summary_meta += f" • {rem_badge}"

        return ft.Container(
            padding=16,
            bgcolor=ft.Colors.WHITE,
            border_radius=14,
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=10,
                                height=54,
                                border_radius=5,
                                bgcolor=color,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        summary.get("title", ""),
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        summary_meta,
                                        size=12,
                                        color=ft.Colors.BLUE_GREY_500,
                                    ),
                                    ft.ProgressBar(
                                        value=ratio,
                                        width=220,
                                        color=color,
                                        bgcolor="#E2E8F0",
                                        height=7,
                                        border_radius=4,
                                    ),
                                ],
                                spacing=4,
                            ),
                        ],
                        spacing=12,
                        expand=True,
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                right_label,
                                size=13,
                                weight=ft.FontWeight.BOLD,
                                color=right_color,
                            ),
                            ft.Text(
                                sub_right,
                                size=12,
                                color=ft.Colors.BLUE_GREY_500,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        spacing=2,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

    def _build_schedule_day_item_row(
        self,
        item: dict[str, Any],
        is_future: bool,
    ) -> ft.Control:
        hid = item["habit_id"]
        target_date = item["date"]
        completed = bool(item.get("completed", False))
        count = int(item.get("count", 0))
        target = int(item.get("target_per_day", 1))
        color = item.get("color", "#6366F1")
        status_val = item.get("status", "today")
        mode = item.get("mode", "free")
        force_start_time = item.get("force_start_time")
        started_on_time = bool(item.get("started_on_time", False))
        is_late = bool(item.get("is_late", False))

        now_dt = datetime.now()
        today_iso = now_dt.date().isoformat()
        now_hhmm = now_dt.strftime("%H:%M")
        needs_strict_start = (
            mode == "strict"
            and target_date == today_iso
            and not completed
            and not started_on_time
            and (not force_start_time or now_hhmm <= force_start_time)
        )

        async def do_checkin(action: str) -> None:
            try:
                await self.api.checkin_habit(
                    habit_id=hid,
                    target_date=target_date,
                    action=action,
                )
                self._invalidate_tabs({0, 1, 3, 4})
                await self.refresh_current_tab(force=True)
                self.render_shell()
            except ApiError as err:
                show_toast(self.page, err.message, is_error=True)

        async def on_primary_tap(_e: Any) -> None:
            if needs_strict_start:
                await do_checkin("start")
            else:
                await do_checkin("toggle" if target == 1 else "increment")

        async def on_decrement(_e: Any) -> None:
            await do_checkin("decrement")

        status_labels = {
            "completed": "超时补卡" if is_late else "Done",
            "today": "Due today",
            "upcoming": "Upcoming",
            "overdue": "Missed",
        }
        subtitle_parts = [status_labels.get(status_val, "")]
        mode_summary = format_habit_mode_summary(item)
        if mode_summary:
            subtitle_parts.append(mode_summary)
        if target > 1:
            subtitle_parts.append(f"{count} / {target}")
        rem_badge = format_reminder_badge(item)
        if rem_badge:
            subtitle_parts.append(rem_badge)
        if item.get("description"):
            subtitle_parts.append(item["description"])
        subtitle = " • ".join(p for p in subtitle_parts if p)

        right_controls: list[ft.Control] = []
        if is_future:
            right_controls.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                    border_radius=10,
                    bgcolor="#F1F5F9",
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.SCHEDULE_ROUNDED,
                                size=14,
                                color=ft.Colors.BLUE_GREY_500,
                            ),
                            ft.Text(
                                "Upcoming",
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.BLUE_GREY_600,
                            ),
                        ],
                        spacing=4,
                        tight=True,
                    ),
                )
            )
        else:
            if target > 1 and count > 0 and not needs_strict_start:
                right_controls.append(
                    ft.IconButton(
                        icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        icon_size=20,
                        tooltip="Decrease count",
                        on_click=on_decrement,
                    )
                )
            right_controls.append(
                ft.IconButton(
                    icon=(
                        ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED
                        if needs_strict_start
                        else (
                            ft.Icons.CHECK_CIRCLE_ROUNDED
                            if completed
                            else (
                                ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED
                                if target > 1
                                else ft.Icons.RADIO_BUTTON_UNCHECKED_ROUNDED
                            )
                        )
                    ),
                    icon_color=(
                        "#D97706"
                        if is_late
                        else (
                            color
                            if completed
                            else (
                                "#4F46E5"
                                if needs_strict_start
                                else (
                                    "#DC2626"
                                    if status_val == "overdue"
                                    else ft.Colors.BLUE_GREY_400
                                )
                            )
                        )
                    ),
                    icon_size=26,
                    tooltip="开始执行" if needs_strict_start else "Check in",
                    on_click=on_primary_tap,
                )
            )

        return ft.Row(
            [
                ft.Row(
                    [
                        ft.Container(
                            width=6,
                            height=34,
                            border_radius=3,
                            bgcolor=color,
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    item["title"],
                                    size=15,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    subtitle,
                                    size=12,
                                    color=(
                                        "#DC2626"
                                        if status_val == "overdue"
                                        else ft.Colors.BLUE_GREY_500
                                    ),
                                ),
                            ],
                            spacing=2,
                        ),
                    ],
                    spacing=10,
                    expand=True,
                ),
                ft.Row(right_controls, spacing=4),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    # -----------------------------------------------------------------------
    # Tab 2: Habits Management (Create / Edit / Archive / Delete)
    # -----------------------------------------------------------------------
    def _build_habits_view(self) -> ft.Control:
        async def toggle_archived(e: Any) -> None:
            self.show_archived = bool(e.control.value)
            self._activate_current_view()

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Manage Habits", size=22, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "Customize schedules, daily targets, and colors",
                            size=13,
                            color=ft.Colors.BLUE_GREY_500,
                        ),
                    ],
                    spacing=2,
                ),
                ft.Row(
                    [
                        ft.Switch(
                            label="Show Archived",
                            value=self.show_archived,
                            on_change=toggle_archived,
                        ),
                        ft.FilledButton(
                            icon=ft.Icons.ADD_ROUNDED,
                            content=ft.Text("Add Habit"),
                            on_click=lambda _e: self._open_habit_dialog(),
                        ),
                    ],
                    spacing=12,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            wrap=True,
        )

        items: list[ft.Control] = [header]
        if not self.all_habits:
            items.append(
                ft.Container(
                    padding=32,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        "No habits found. Create one to start tracking!",
                        color=ft.Colors.BLUE_GREY_500,
                    ),
                )
            )
        else:
            for habit in self.all_habits:
                items.append(self._build_manage_habit_row(habit))

        return ft.Column(items, scroll=ft.ScrollMode.AUTO, expand=True, spacing=12)

    def _build_manage_habit_row(self, habit: dict[str, Any]) -> ft.Control:
        hid = habit["id"]
        is_archived = habit.get("archived", False)
        freq = format_habit_schedule(habit)
        goal_unit = "due day" if habit.get("frequency_type") == "monthly" else "day"

        async def toggle_archive_state(_e: Any) -> None:
            try:
                await self.api.update_habit(hid, {"archived": not is_archived})
                self._invalidate_tabs(range(5))
                await self.refresh_current_tab(force=True)
                self.render_shell()
            except ApiError as err:
                show_toast(self.page, err.message, is_error=True)

        async def remove_habit(_e: Any) -> None:
            try:
                await self.api.delete_habit(hid)
                self._invalidate_tabs(range(5))
                await self.refresh_current_tab(force=True)
                self.render_shell()
                show_toast(self.page, "Habit deleted")
            except ApiError as err:
                show_toast(self.page, err.message, is_error=True)

        rem_badge = format_reminder_badge(habit)
        mode_summary = format_habit_mode_summary(habit)
        manage_meta = (
            f"{freq} • Goal: {habit.get('target_per_day', 1)}/{goal_unit} "
            f"• SLO: {habit.get('target_slo', 85.0)}%"
        )
        if mode_summary:
            manage_meta += f" • {mode_summary}"
        if rem_badge:
            manage_meta += f" • {rem_badge}"

        return ft.Container(
            padding=16,
            bgcolor=ft.Colors.WHITE,
            border_radius=14,
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=14,
                                height=40,
                                border_radius=7,
                                bgcolor=habit.get("color", "#6366F1"),
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        habit["title"]
                                        + (" (Archived)" if is_archived else ""),
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        manage_meta,
                                        size=12,
                                        color=ft.Colors.BLUE_GREY_500,
                                    ),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=12,
                    ),
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.EDIT_OUTLINED,
                                tooltip="Edit habit",
                                on_click=lambda _e, h=habit: self._open_habit_dialog(h),
                            ),
                            ft.IconButton(
                                icon=(
                                    ft.Icons.UNARCHIVE_OUTLINED
                                    if is_archived
                                    else ft.Icons.ARCHIVE_OUTLINED
                                ),
                                tooltip="Unarchive" if is_archived else "Archive",
                                on_click=toggle_archive_state,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                icon_color=ft.Colors.RED_400,
                                tooltip="Delete permanently",
                                on_click=remove_habit,
                            ),
                        ],
                        spacing=2,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )

    def _open_habit_dialog(self, existing: dict[str, Any] | None = None) -> None:
        is_edit = existing is not None
        initial_freq = existing.get("frequency_type", "daily") if existing else "daily"
        if initial_freq not in ("daily", "weekdays", "monthly"):
            initial_freq = "daily"
        initial_mode = (
            existing.get("monthly_mode", "from_start") if existing else "from_start"
        )
        if initial_mode not in ("from_start", "from_end", "nth_weekday"):
            initial_mode = "from_start"
        initial_monthly_day = int(existing.get("monthly_day", 1)) if existing else 1
        initial_monthly_week = int(existing.get("monthly_week", 1)) if existing else 1
        initial_monthly_weekday = (
            int(existing.get("monthly_weekday", 0)) if existing else 0
        )
        initial_habit_mode = (
            str(existing.get("mode") or "free") if existing else "free"
        )
        if initial_habit_mode not in ("free", "strict", "window", "reminder"):
            initial_habit_mode = "free"
        initial_mode_remind = (
            str(existing.get("remind_time") or "09:00")
            if (existing and existing.get("remind_time"))
            else ("09:00" if initial_habit_mode != "free" else "")
        )
        initial_mode_start = (
            str(existing.get("force_start_time") or "") if existing else ""
        )
        initial_mode_end = (
            str(existing.get("force_end_time") or "") if existing else ""
        )

        title_field = ft.TextField(
            label="Habit Title",
            value=existing["title"] if existing else "",
            hint_text="e.g., Read 20 pages, Pay rent, Monthly review",
        )
        desc_field = ft.TextField(
            label="Notes / Motivation (optional)",
            value=existing.get("description", "") if existing else "",
        )
        target_field = ft.TextField(
            label=(
                "Target Count (on due day)"
                if initial_freq == "monthly"
                else "Daily Target Count"
            ),
            value=str(existing.get("target_per_day", 1)) if existing else "1",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        slo_field = ft.TextField(
            label="Target SLO (%)",
            value=str(existing.get("target_slo", 85.0)) if existing else "85.0",
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="e.g., 85, 90, 95",
        )

        selected_color = existing.get("color", "#6366F1") if existing else "#6366F1"
        color_dropdown = ft.Dropdown(
            label="Accent Color",
            value=selected_color,
            options=[
                ft.dropdown.Option(key=hex_code, text=label)
                for hex_code, label in COLOR_SWATCHES
            ],
        )

        initial_weekdays = set(
            existing.get("weekdays", [0, 1, 2, 3, 4, 5, 6])
            if existing
            else [0, 1, 2, 3, 4, 5, 6]
        )
        day_checks = [
            ft.Checkbox(label=WEEKDAY_LABELS[i], value=(i in initial_weekdays))
            for i in range(7)
        ]
        weekdays_section = ft.Column(
            [
                ft.Text("Schedule Days:", size=13, weight=ft.FontWeight.BOLD),
                ft.Row(day_checks, wrap=True, spacing=6),
            ],
            tight=True,
            spacing=6,
            visible=(initial_freq == "weekdays"),
        )

        monthly_day_field = ft.TextField(
            value=str(initial_monthly_day),
            keyboard_type=ft.KeyboardType.NUMBER,
            visible=(initial_mode in ("from_start", "from_end")),
        )

        def sync_monthly_day_labels(mode: str) -> None:
            if mode == "from_end":
                monthly_day_field.label = "Day from Month End (1–31)"
                monthly_day_field.helper = "1 = last day of month, 2 = 2nd-to-last, etc."
            else:
                monthly_day_field.label = "Day of Month (1–31)"
                monthly_day_field.helper = (
                    "Clamped to month-end on shorter months (e.g., 31 → Feb 28/29)"
                )

        sync_monthly_day_labels(initial_mode)

        monthly_week_dropdown = ft.Dropdown(
            label="Week of Month",
            value=str(initial_monthly_week),
            options=[
                ft.dropdown.Option(key="1", text="Week 1 (1st)"),
                ft.dropdown.Option(key="2", text="Week 2 (2nd)"),
                ft.dropdown.Option(key="3", text="Week 3 (3rd)"),
                ft.dropdown.Option(key="4", text="Week 4 (4th)"),
                ft.dropdown.Option(key="5", text="Week 5 (5th)"),
                ft.dropdown.Option(key="-1", text="Last week of month"),
            ],
        )
        monthly_weekday_dropdown = ft.Dropdown(
            label="Day of Week",
            value=str(initial_monthly_weekday),
            options=[
                ft.dropdown.Option(key=str(i), text=name)
                for i, name in enumerate(WEEKDAY_FULL_NAMES)
            ],
        )
        nth_weekday_row = ft.Column(
            [monthly_week_dropdown, monthly_weekday_dropdown],
            tight=True,
            spacing=10,
            visible=(initial_mode == "nth_weekday"),
        )

        def on_monthly_mode_change(_e: Any) -> None:
            mode = monthly_mode_dropdown.value or "from_start"
            sync_monthly_day_labels(mode)
            monthly_day_field.visible = mode in ("from_start", "from_end")
            nth_weekday_row.visible = mode == "nth_weekday"
            self.page.update()

        monthly_mode_dropdown = ft.Dropdown(
            label="Monthly Rule",
            value=initial_mode,
            options=[
                ft.dropdown.Option(
                    key="from_start", text="From start of month (Day 1–31)"
                ),
                ft.dropdown.Option(
                    key="from_end", text="From end of month (Last day, 2nd from end…)"
                ),
                ft.dropdown.Option(
                    key="nth_weekday", text="Day X on Week Y (e.g., Mon on Week 2)"
                ),
            ],
            on_select=on_monthly_mode_change,
        )
        monthly_section = ft.Column(
            [monthly_mode_dropdown, monthly_day_field, nth_weekday_row],
            tight=True,
            spacing=10,
            visible=(initial_freq == "monthly"),
        )

        def on_schedule_change(_e: Any) -> None:
            freq = schedule_dropdown.value or "daily"
            weekdays_section.visible = freq == "weekdays"
            monthly_section.visible = freq == "monthly"
            target_field.label = (
                "Target Count (on due day)"
                if freq == "monthly"
                else "Daily Target Count"
            )
            self.page.update()

        schedule_dropdown = ft.Dropdown(
            label="Schedule Frequency",
            value=initial_freq,
            options=[
                ft.dropdown.Option(key="daily", text="Daily (Every day)"),
                ft.dropdown.Option(key="weekdays", text="Weekly (Specific weekdays)"),
                ft.dropdown.Option(key="monthly", text="Monthly Routine Job"),
            ],
            on_select=on_schedule_change,
        )

        remind_time_field = ft.TextField(
            label="Remind Time (HH:MM)",
            value=initial_mode_remind,
            hint_text="例如 09:00",
        )
        force_start_time_field = ft.TextField(
            label="Force Start Time (HH:MM)",
            value=initial_mode_start,
            hint_text="例如 09:15",
            visible=(initial_habit_mode == "strict"),
        )
        force_end_time_field = ft.TextField(
            label="Force End Time (HH:MM)",
            value=initial_mode_end,
            hint_text="例如 10:30",
            visible=(initial_habit_mode in ("strict", "window")),
        )
        mode_hint_text = ft.Text(
            HABIT_MODE_HINTS.get(initial_habit_mode, ""),
            size=11,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        mode_times_section = ft.Column(
            [
                mode_hint_text,
                remind_time_field,
                force_start_time_field,
                force_end_time_field,
            ],
            tight=True,
            spacing=8,
            visible=(initial_habit_mode != "free"),
        )

        def on_habit_mode_change(_e: Any) -> None:
            m = habit_mode_dropdown.value or "free"
            mode_hint_text.value = HABIT_MODE_HINTS.get(m, "")
            mode_times_section.visible = m != "free"
            force_start_time_field.visible = m == "strict"
            force_end_time_field.visible = m in ("strict", "window")
            if m != "free" and not (remind_time_field.value or "").strip():
                remind_time_field.value = "09:00"
            if m == "strict":
                if not (force_start_time_field.value or "").strip():
                    force_start_time_field.value = "09:15"
                if not (force_end_time_field.value or "").strip():
                    force_end_time_field.value = "10:30"
            elif m == "window" and not (force_end_time_field.value or "").strip():
                force_end_time_field.value = "21:00"
            err_label.visible = False
            self.page.update()

        habit_mode_dropdown = ft.Dropdown(
            label="Habit Mode",
            value=initial_habit_mode,
            options=[
                ft.dropdown.Option(key=k, text=label)
                for k, label in HABIT_MODE_OPTIONS
            ],
            on_select=on_habit_mode_change,
        )

        from datetime import time as dt_time

        initial_reminder_enabled = (
            bool(existing.get("reminder_enabled", False)) if existing else False
        )
        raw_existing_times = (existing.get("reminder_times") or []) if existing else []
        reminder_times_state: list[str] = []
        for raw_item in raw_existing_times:
            norm = normalize_hhmm(str(raw_item))
            if norm and norm not in reminder_times_state:
                reminder_times_state.append(norm)
        reminder_times_state.sort()

        initial_reminder_mode = (
            str(existing.get("reminder_mode") or "notification")
            if existing
            else "notification"
        )
        if initial_reminder_mode not in ("notification", "alarm"):
            initial_reminder_mode = "notification"

        try:
            initial_snooze = (
                int(existing.get("reminder_snooze_minutes") or 10)
                if existing
                else 10
            )
        except (TypeError, ValueError):
            initial_snooze = 10
        if not (1 <= initial_snooze <= 120):
            initial_snooze = 10
        snooze_choices = sorted(set(REMINDER_SNOOZE_OPTIONS) | {initial_snooze})

        initial_reminder_msg = (
            str(existing.get("reminder_message") or "") if existing else ""
        )

        reminder_times_row = ft.Row([], wrap=True, spacing=6, run_spacing=6)
        preset_chips_row = ft.Row([], wrap=True, spacing=6, run_spacing=6)
        custom_time_input = ft.TextField(
            label="Add Time (HH:MM)",
            hint_text="e.g. 08:30",
            expand=True,
        )
        reminder_mode_dropdown = ft.Dropdown(
            label="Reminder Style",
            value=initial_reminder_mode,
            options=[
                ft.dropdown.Option(key="notification", text="Notification Banner"),
                ft.dropdown.Option(key="alarm", text="Alarm Ring (Dialog + Sound)"),
            ],
        )
        snooze_dropdown = ft.Dropdown(
            label="Snooze Duration",
            value=str(initial_snooze),
            options=[
                ft.dropdown.Option(key=str(m), text=f"{m} minutes")
                for m in snooze_choices
            ],
        )
        reminder_msg_field = ft.TextField(
            label="Custom Reminder Message (optional)",
            value=initial_reminder_msg,
            max_length=160,
        )

        def rebuild_reminder_chips() -> None:
            if reminder_times_state:
                reminder_times_row.controls = [
                    ft.Chip(
                        label=ft.Text(hhmm),
                        on_delete=lambda _e, t=hhmm: remove_reminder_time(t),
                    )
                    for hhmm in reminder_times_state
                ]
            else:
                reminder_times_row.controls = [
                    ft.Text(
                        "No reminder times configured yet",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                ]
            preset_chips_row.controls = [
                ft.Chip(
                    label=ft.Text(preset),
                    selected=(preset in reminder_times_state),
                    on_click=(
                        lambda _e, t=preset: remove_reminder_time(t)
                        if t in reminder_times_state
                        else add_reminder_time(t)
                    ),
                )
                for preset in REMINDER_TIME_PRESETS
            ]

        def add_reminder_time(raw_val: str) -> bool:
            norm = normalize_hhmm(raw_val)
            if norm is None:
                err_label.value = "Reminder time must be HH:MM (00:00-23:59)"
                err_label.visible = True
                self.page.update()
                return False
            if norm in reminder_times_state:
                err_label.visible = False
                rebuild_reminder_chips()
                self.page.update()
                return True
            if len(reminder_times_state) >= MAX_REMINDER_TIMES:
                err_label.value = (
                    f"At most {MAX_REMINDER_TIMES} reminder times are allowed"
                )
                err_label.visible = True
                self.page.update()
                return False
            reminder_times_state.append(norm)
            reminder_times_state.sort()
            err_label.visible = False
            rebuild_reminder_chips()
            self.page.update()
            return True

        def remove_reminder_time(hhmm: str) -> None:
            if hhmm in reminder_times_state:
                reminder_times_state.remove(hhmm)
            err_label.visible = False
            rebuild_reminder_chips()
            self.page.update()

        def on_add_custom_time(_e: Any) -> None:
            raw_val = (custom_time_input.value or "").strip()
            if not raw_val:
                err_label.value = "Enter a reminder time in HH:MM format"
                err_label.visible = True
                self.page.update()
                return
            if add_reminder_time(raw_val):
                custom_time_input.value = ""
                self.page.update()

        def on_pick_clock_time(_e: Any) -> None:
            if reminder_times_state:
                parts = reminder_times_state[0].split(":")
                init_time = dt_time(int(parts[0]), int(parts[1]))
            else:
                init_time = dt_time(9, 0)

            def on_picker_change(ev: Any) -> None:
                picked = getattr(ev.control, "value", None)
                if picked is not None:
                    add_reminder_time(f"{picked.hour:02d}:{picked.minute:02d}")

            picker = ft.TimePicker(
                value=init_time,
                help_text="Pick reminder time",
                on_change=on_picker_change,
            )
            open_dialog(self.page, picker)

        reminder_details_section = ft.Column(
            [
                ft.Text(
                    "Reminder Times",
                    size=12,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                reminder_times_row,
                ft.Text(
                    "Quick Presets",
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                preset_chips_row,
                ft.Row(
                    [
                        custom_time_input,
                        ft.OutlinedButton(
                            content=ft.Text("Add"),
                            on_click=on_add_custom_time,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ACCESS_TIME_ROUNDED,
                            tooltip="Pick Clock Time",
                            on_click=on_pick_clock_time,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                reminder_mode_dropdown,
                snooze_dropdown,
                reminder_msg_field,
            ],
            tight=True,
            spacing=8,
            visible=initial_reminder_enabled,
        )

        def on_reminder_toggle(_e: Any) -> None:
            enabled = bool(reminder_switch.value)
            if enabled and not reminder_times_state:
                reminder_times_state.append("09:00")
            rebuild_reminder_chips()
            reminder_details_section.visible = enabled
            err_label.visible = False
            self.page.update()

        reminder_switch = ft.Switch(
            label="Enable Reminders & Alarms",
            value=initial_reminder_enabled,
            on_change=on_reminder_toggle,
        )
        rebuild_reminder_chips()

        err_label = ft.Text("", color=ft.Colors.RED_600, size=12, visible=False)
        dialog = ft.AlertDialog(modal=True)

        async def save_habit(_e: Any) -> None:
            title = (title_field.value or "").strip()
            if not title:
                err_label.value = "Title is required"
                err_label.visible = True
                self.page.update()
                return

            freq_type = schedule_dropdown.value or "daily"
            if freq_type == "weekdays":
                chosen_days = [i for i, cb in enumerate(day_checks) if cb.value]
                if not chosen_days:
                    err_label.value = "Pick at least one day of the week"
                    err_label.visible = True
                    self.page.update()
                    return
            else:
                chosen_days = [0, 1, 2, 3, 4, 5, 6]

            monthly_mode = monthly_mode_dropdown.value or "from_start"
            monthly_day = max(1, min(31, initial_monthly_day))
            if freq_type == "monthly" and monthly_mode in ("from_start", "from_end"):
                try:
                    monthly_day = int((monthly_day_field.value or "").strip())
                except ValueError:
                    monthly_day = 0
                if not (1 <= monthly_day <= 31):
                    err_label.value = "Monthly day must be between 1 and 31"
                    err_label.visible = True
                    self.page.update()
                    return

            monthly_week = int(monthly_week_dropdown.value or "1")
            monthly_weekday = int(monthly_weekday_dropdown.value or "0")

            try:
                target_int = max(1, int(target_field.value or "1"))
            except ValueError:
                target_int = 1

            try:
                slo_val = float((slo_field.value or "").strip())
            except ValueError:
                slo_val = -1.0
            if not (1.0 <= slo_val <= 100.0):
                err_label.value = "Target SLO must be between 1 and 100"
                err_label.visible = True
                self.page.update()
                return

            reminder_enabled = bool(reminder_switch.value)
            pending_time_raw = (custom_time_input.value or "").strip()
            if pending_time_raw:
                norm_pending = normalize_hhmm(pending_time_raw)
                if norm_pending is None:
                    err_label.value = "Reminder time must be HH:MM (00:00-23:59)"
                    err_label.visible = True
                    self.page.update()
                    return
                if norm_pending not in reminder_times_state:
                    if len(reminder_times_state) >= MAX_REMINDER_TIMES:
                        err_label.value = (
                            f"At most {MAX_REMINDER_TIMES} reminder times are allowed"
                        )
                        err_label.visible = True
                        self.page.update()
                        return
                    reminder_times_state.append(norm_pending)
                    reminder_times_state.sort()
                    custom_time_input.value = ""
                    rebuild_reminder_chips()

            if reminder_enabled and not reminder_times_state:
                err_label.value = "Add at least one reminder time (HH:MM)"
                err_label.visible = True
                self.page.update()
                return

            reminder_mode = reminder_mode_dropdown.value or "notification"
            if reminder_mode not in ("notification", "alarm"):
                reminder_mode = "notification"

            try:
                snooze_val = int(snooze_dropdown.value or "10")
            except ValueError:
                snooze_val = 10
            if not (1 <= snooze_val <= 120):
                snooze_val = 10

            chosen_habit_mode = habit_mode_dropdown.value or "free"
            m_remind, m_start, m_end, mode_err = validate_habit_mode_times(
                chosen_habit_mode,
                remind_time_field.value,
                force_start_time_field.value,
                force_end_time_field.value,
            )
            if mode_err:
                err_label.value = mode_err
                err_label.visible = True
                self.page.update()
                return

            payload = {
                "title": title,
                "description": (desc_field.value or "").strip(),
                "color": color_dropdown.value or "#6366F1",
                "frequency_type": freq_type,
                "weekdays": chosen_days,
                "monthly_mode": monthly_mode,
                "monthly_day": monthly_day,
                "monthly_week": monthly_week,
                "monthly_weekday": monthly_weekday,
                "target_per_day": target_int,
                "target_slo": round(slo_val, 1),
                "mode": chosen_habit_mode,
                "remind_time": m_remind,
                "force_start_time": m_start,
                "force_end_time": m_end,
                "reminder_enabled": reminder_enabled,
                "reminder_times": list(reminder_times_state),
                "reminder_mode": reminder_mode,
                "reminder_snooze_minutes": snooze_val,
                "reminder_message": (reminder_msg_field.value or "").strip(),
            }

            try:
                if is_edit and existing:
                    await self.api.update_habit(existing["id"], payload)
                    self._snoozed_alarms.pop(existing["id"], None)
                else:
                    await self.api.create_habit(payload)
                close_dialog(self.page, dialog)
                self._invalidate_tabs(range(5))
                await self.refresh_current_tab(force=True)
                self.render_shell()
            except ApiError as err:
                err_label.value = err.message
                err_label.visible = True
                self.page.update()

        dialog.title = ft.Text("Edit Habit" if is_edit else "New Habit")
        dialog.content = ft.Container(
            width=380,
            content=ft.Column(
                [
                    title_field,
                    desc_field,
                    target_field,
                    slo_field,
                    color_dropdown,
                    schedule_dropdown,
                    weekdays_section,
                    monthly_section,
                    ft.Divider(height=1),
                    habit_mode_dropdown,
                    mode_times_section,
                    ft.Divider(height=1),
                    reminder_switch,
                    reminder_details_section,
                    err_label,
                ],
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        dialog.actions = [
            ft.TextButton(
                content=ft.Text("Cancel"),
                on_click=lambda _e: close_dialog(self.page, dialog),
            ),
            ft.FilledButton(
                content=ft.Text("Save"),
                on_click=save_habit,
            ),
        ]
        open_dialog(self.page, dialog)

    # -----------------------------------------------------------------------
    # Tab 3: Streaks & Completion Analytics
    # -----------------------------------------------------------------------
    def _build_stats_view(self) -> ft.Control:
        summary = self.stats_summary or {}
        best_active = summary.get("best_active_streak", 0)
        rate_30d = summary.get("overall_completion_rate_30d", 0.0)
        done_today = summary.get("completed_today", 0)
        sched_today = summary.get("scheduled_today", 0)
        late_today = summary.get("late_today", 0)
        violated_today = summary.get("violated_today", 0)
        score_subtext = (
            f"补卡 {late_today} · 违规 {violated_today}"
            if (late_today > 0 or violated_today > 0)
            else None
        )

        kpi_row = ft.Row(
            [
                self._kpi_card(
                    "Active Best Streak",
                    f"{best_active} days",
                    ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                    "#D97706",
                ),
                self._kpi_card(
                    "30-Day Completion",
                    f"{rate_30d}%",
                    ft.Icons.INSIGHTS_ROUNDED,
                    "#10B981",
                ),
                self._kpi_card(
                    "Today's Score",
                    f"{done_today} / {sched_today}",
                    ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED,
                    "#6366F1",
                    subtext=score_subtext,
                ),
            ],
            wrap=True,
            spacing=12,
        )

        # Visual 7-day completion bar chart (pure Flet controls for 100% Web/Mobile parity)
        bars: list[ft.Control] = []
        for pt in summary.get("last_7_days", []):
            sched = pt.get("scheduled_count", 0)
            comp = pt.get("completed_count", 0)
            late_cnt = pt.get("late_count", 0)
            ratio = (comp / sched) if sched > 0 else 0.0
            bar_height = max(8, int(ratio * 100))
            bar_col_items: list[ft.Control] = [
                ft.Text(f"{comp}/{sched}", size=11, color=ft.Colors.BLUE_GREY_600),
            ]
            if late_cnt > 0:
                bar_col_items.append(
                    ft.Text(f"+{late_cnt}补", size=10, color="#D97706")
                )
            bar_col_items.extend(
                [
                    ft.Container(
                        width=32,
                        height=100,
                        bgcolor="#E2E8F0",
                        border_radius=8,
                        alignment=ft.Alignment.BOTTOM_CENTER,
                        content=ft.Container(
                            width=32,
                            height=bar_height,
                            bgcolor="#6366F1" if ratio >= 1.0 else "#818CF8",
                            border_radius=8,
                        ),
                    ),
                    ft.Text(
                        pt.get("weekday_label", ""),
                        size=12,
                        weight=ft.FontWeight.BOLD,
                    ),
                ]
            )
            bars.append(
                ft.Column(
                    bar_col_items,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                )
            )

        chart_card = ft.Container(
            padding=20,
            bgcolor=ft.Colors.WHITE,
            border_radius=14,
            content=ft.Column(
                [
                    ft.Text("Last 7 Days Activity", size=16, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        bars,
                        alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    ),
                ],
                spacing=16,
            ),
        )

        leaderboard_items: list[ft.Control] = [
            ft.Text("Habit Streaks Breakdown", size=17, weight=ft.FontWeight.BOLD)
        ]
        for hs in summary.get("habit_stats", []):
            unit = "mo" if hs.get("frequency_type") == "monthly" else "d"
            late_total = hs.get("late_completions", 0)
            hs_mode = hs.get("mode", "free")
            meta_str = f"30d rate: {hs['completion_rate_30d']}% • On-time: {hs['total_completions']}"
            if hs_mode != "free":
                meta_str = f"{HABIT_MODE_SHORT_LABELS.get(hs_mode, hs_mode)} • {meta_str}"
            if late_total > 0:
                meta_str += f" • 超时补卡: {late_total}"
            leaderboard_items.append(
                ft.Container(
                    padding=14,
                    bgcolor=ft.Colors.WHITE,
                    border_radius=12,
                    content=ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        width=10,
                                        height=34,
                                        border_radius=5,
                                        bgcolor=hs.get("color", "#6366F1"),
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text(
                                                hs["title"],
                                                weight=ft.FontWeight.BOLD,
                                                size=15,
                                            ),
                                            ft.Text(
                                                meta_str,
                                                size=12,
                                                color=ft.Colors.BLUE_GREY_500,
                                            ),
                                        ],
                                        spacing=2,
                                    ),
                                ],
                                spacing=10,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        f"Current: {hs['current_streak']}{unit}",
                                        weight=ft.FontWeight.BOLD,
                                        color="#D97706",
                                    ),
                                    ft.Text(
                                        f"Best: {hs['best_streak']}{unit}",
                                        size=12,
                                        color=ft.Colors.BLUE_GREY_500,
                                    ),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                                spacing=2,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                )
            )

        return ft.Column(
            [
                ft.Text("Streaks & Statistics", size=22, weight=ft.FontWeight.BOLD),
                kpi_row,
                chart_card,
                *leaderboard_items,
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=14,
        )

    def _kpi_card(
        self, title: str, value: str, icon: Any, accent: str, subtext: str | None = None
    ) -> ft.Control:
        text_controls: list[ft.Control] = [
            ft.Text(title, size=12, color=ft.Colors.BLUE_GREY_500),
            ft.Text(value, size=19, weight=ft.FontWeight.BOLD),
        ]
        if subtext:
            text_controls.append(
                ft.Text(subtext, size=11, color=ft.Colors.BLUE_GREY_500)
            )
        return ft.Container(
            width=220,
            padding=16,
            bgcolor=ft.Colors.WHITE,
            border_radius=14,
            content=ft.Row(
                [
                    ft.Icon(icon, color=accent, size=30),
                    ft.Column(text_controls, spacing=2, expand=True),
                ],
                spacing=12,
            ),
        )

    # -----------------------------------------------------------------------
    # Tab 4: Personal SLI & Error Budget Analysis Dashboard
    # -----------------------------------------------------------------------
    def _build_sli_view(self) -> ft.Control:
        dash = self.sli_dashboard or {}
        window_days = dash.get("window_days", self.sli_window_days)
        active_count = dash.get("active_habits_count", 0)
        overall_sli = dash.get("overall_sli", 0.0)
        overall_slo = dash.get("overall_target_slo", 85.0)
        overall_status = dash.get("overall_status", "no_data")
        healthy_cnt = dash.get("healthy_count", 0)
        warning_cnt = dash.get("warning_count", 0)
        breached_cnt = dash.get("breached_count", 0)
        allowed_days = dash.get("overall_error_budget_allowed_days", 0.0)
        rem_days = dash.get("overall_error_budget_remaining_days", 0.0)
        rem_pct = dash.get("overall_error_budget_remaining_pct", 100.0)
        burn_rate = dash.get("overall_burn_rate", 0.0)
        burn_rate_7d = dash.get("overall_burn_rate_7d", 0.0)
        weakest_day = dash.get("weakest_weekday")
        weakest_day_sli = dash.get("weakest_weekday_sli")
        top_burn_title = dash.get("top_burn_habit_title")
        top_burn_rate = dash.get("top_burn_rate")

        status_palette = {
            "healthy": ("#10B981", "#ECFDF5", "HEALTHY"),
            "warning": ("#D97706", "#FEF3C7", "AT RISK"),
            "breached": ("#EF4444", "#FEF2F2", "BREACHED"),
            "no_data": ("#64748B", "#F1F5F9", "NO DATA"),
        }
        overall_fg, overall_bg, overall_label = status_palette.get(
            overall_status, status_palette["no_data"]
        )

        async def select_window(days: int) -> None:
            if self.sli_window_days == days:
                return
            self.sli_window_days = days
            self._activate_current_view()

        def make_window_handler(days: int):
            async def _handler(_e: Any) -> None:
                await select_window(days)

            return _handler

        window_buttons: list[ft.Control] = []
        for days in (7, 30, 90):
            if self.sli_window_days == days:
                window_buttons.append(
                    ft.FilledButton(
                        content=ft.Text(f"{days}d"),
                        on_click=make_window_handler(days),
                    )
                )
            else:
                window_buttons.append(
                    ft.OutlinedButton(
                        content=ft.Text(f"{days}d"),
                        on_click=make_window_handler(days),
                    )
                )

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "Personal SLI & Error Budget",
                                    size=22,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Container(
                                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                    border_radius=10,
                                    bgcolor=overall_bg,
                                    content=ft.Text(
                                        overall_label,
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=overall_fg,
                                    ),
                                ),
                            ],
                            spacing=10,
                            wrap=True,
                        ),
                        ft.Text(
                            "SRE reliability, error budgets, and burn-rate diagnostics",
                            size=13,
                            color=ft.Colors.BLUE_GREY_500,
                        ),
                    ],
                    spacing=2,
                ),
                ft.Row(window_buttons, spacing=8),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            wrap=True,
        )

        budget_color = (
            "#10B981" if rem_pct > 50 else ("#D97706" if rem_pct > 25 else "#EF4444")
        )
        burn_color = (
            "#10B981"
            if burn_rate <= 1.0
            else ("#D97706" if burn_rate <= 1.5 else "#EF4444")
        )

        kpi_row = ft.Row(
            [
                self._kpi_card(
                    "Overall SLI",
                    f"{overall_sli}%",
                    ft.Icons.SPEED_ROUNDED,
                    overall_fg,
                    subtext=f"Target SLO: {overall_slo}%",
                ),
                self._kpi_card(
                    "Error Budget",
                    f"{rem_pct}%",
                    ft.Icons.SHIELD_ROUNDED,
                    budget_color,
                    subtext=f"{rem_days:+.1f}d / {allowed_days}d",
                ),
                self._kpi_card(
                    "Burn Rate",
                    f"{burn_rate}x",
                    ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED,
                    burn_color,
                    subtext=f"7d fast burn: {burn_rate_7d}x",
                ),
                self._kpi_card(
                    "SLO Compliance",
                    f"{healthy_cnt} OK / {warning_cnt} Risk / {breached_cnt} Breach",
                    ft.Icons.CHECK_CIRCLE_ROUNDED,
                    "#6366F1",
                    subtext=f"Window: {window_days} days",
                ),
            ],
            wrap=True,
            spacing=12,
        )

        controls: list[ft.Control] = [header, kpi_row]

        if active_count > 0:
            if top_burn_title and top_burn_rate is not None:
                burn_diag_text = f"Highest burn: {top_burn_title} ({top_burn_rate}x)"
                burn_diag_color = "#B45309" if top_burn_rate > 1.0 else ft.Colors.BLUE_GREY_700
            else:
                burn_diag_text = "All habits are at 0.0x burn rate — zero misses in this window."
                burn_diag_color = "#047857"

            if weakest_day and weakest_day_sli is not None:
                weekday_diag_text = f"Weakest day: {weakest_day} ({weakest_day_sli}% SLI)"
                weekday_diag_color = ft.Colors.BLUE_GREY_700
            else:
                weekday_diag_text = "All scheduled weekdays are at 100% reliability."
                weekday_diag_color = "#047857"

            controls.append(
                ft.Container(
                    padding=16,
                    bgcolor=ft.Colors.WHITE,
                    border_radius=14,
                    border=ft.Border.all(1, "#E2E8F0"),
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.TIPS_AND_UPDATES_ROUNDED,
                                color="#6366F1",
                                size=24,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        "SRE Diagnostic Insights",
                                        size=14,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        burn_diag_text,
                                        size=13,
                                        color=burn_diag_color,
                                    ),
                                    ft.Text(
                                        weekday_diag_text,
                                        size=13,
                                        color=weekday_diag_color,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        spacing=12,
                    ),
                )
            )

        # Rolling SLI Trend Bar Chart
        trend_bars: list[ft.Control] = []
        for pt in dash.get("trend", []):
            has_activity = pt.get("has_activity", False)
            pt_sli = pt.get("sli", 0.0)
            bar_height = max(6, int(pt_sli)) if has_activity else 6
            if not has_activity:
                bar_color = "#CBD5E1"
                top_label = "—"
            elif pt_sli >= overall_slo:
                bar_color = "#10B981"
                top_label = f"{pt_sli}%"
            elif pt_sli >= overall_slo - 10.0:
                bar_color = "#F59E0B"
                top_label = f"{pt_sli}%"
            else:
                bar_color = "#EF4444"
                top_label = f"{pt_sli}%"

            trend_bars.append(
                ft.Column(
                    [
                        ft.Text(top_label, size=10, color=ft.Colors.BLUE_GREY_600),
                        ft.Container(
                            width=26,
                            height=100,
                            bgcolor="#E2E8F0",
                            border_radius=8,
                            alignment=ft.Alignment.BOTTOM_CENTER,
                            tooltip=(
                                f"{pt.get('start_date', '')} → {pt.get('end_date', '')}: "
                                f"{pt.get('completed_count', 0)}/{pt.get('scheduled_count', 0)}"
                            ),
                            content=ft.Container(
                                width=26,
                                height=bar_height,
                                bgcolor=bar_color,
                                border_radius=8,
                            ),
                        ),
                        ft.Text(
                            pt.get("label", ""),
                            size=11,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=5,
                )
            )

        controls.append(
            ft.Container(
                padding=20,
                bgcolor=ft.Colors.WHITE,
                border_radius=14,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    f"Rolling SLI Trend ({window_days}d)",
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    f"SLO Line: {overall_slo}%",
                                    size=12,
                                    color=ft.Colors.BLUE_GREY_500,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row(
                            trend_bars,
                            alignment=ft.MainAxisAlignment.SPACE_AROUND,
                            wrap=True,
                        )
                        if trend_bars
                        else ft.Text(
                            "No trend buckets available yet.",
                            size=13,
                            color=ft.Colors.BLUE_GREY_500,
                        ),
                    ],
                    spacing=14,
                ),
            )
        )

        # Weekday Reliability Profile
        weekday_rows: list[ft.Control] = []
        for wd in dash.get("weekday_sli", []):
            wd_sched = wd.get("scheduled_count", 0)
            wd_comp = wd.get("completed_count", 0)
            wd_sli = wd.get("sli", 0.0)
            wd_color = (
                "#CBD5E1"
                if wd_sched == 0
                else (
                    "#10B981"
                    if wd_sli >= overall_slo
                    else ("#F59E0B" if wd_sli >= overall_slo - 10.0 else "#EF4444")
                )
            )
            weekday_rows.append(
                ft.Row(
                    [
                        ft.Text(
                            wd.get("label", ""),
                            width=38,
                            size=13,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Container(
                            expand=True,
                            content=ft.ProgressBar(
                                value=(wd_sli / 100.0) if wd_sched > 0 else 0.0,
                                color=wd_color,
                                bgcolor="#E2E8F0",
                                height=8,
                                border_radius=4,
                            ),
                        ),
                        ft.Text(
                            f"{wd_sli}% ({wd_comp}/{wd_sched})"
                            if wd_sched > 0
                            else "— (0/0)",
                            width=105,
                            size=12,
                            text_align=ft.TextAlign.RIGHT,
                            color=ft.Colors.BLUE_GREY_600,
                        ),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        controls.append(
            ft.Container(
                padding=20,
                bgcolor=ft.Colors.WHITE,
                border_radius=14,
                content=ft.Column(
                    [
                        ft.Text(
                            "Weekday Reliability Profile",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                        ),
                        *weekday_rows,
                    ],
                    spacing=10,
                ),
            )
        )

        # Per-Habit SLI & Error Budget Breakdown
        controls.append(
            ft.Text(
                "Habit SLI & Error Budget Breakdown",
                size=17,
                weight=ft.FontWeight.BOLD,
            )
        )

        habit_items = dash.get("habits", [])
        if not habit_items:
            controls.append(
                ft.Container(
                    padding=28,
                    bgcolor=ft.Colors.WHITE,
                    border_radius=14,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        "Create habits and log check-ins to track personal SLIs, SLO targets, and error budgets.",
                        color=ft.Colors.BLUE_GREY_500,
                        text_align=ft.TextAlign.CENTER,
                    ),
                )
            )
        else:
            for item in habit_items:
                st_fg, st_bg, st_label = status_palette.get(
                    item.get("status", "healthy"), status_palette["healthy"]
                )
                h_rem_pct = item.get("error_budget_remaining_pct", 100.0)
                h_rem_color = (
                    "#10B981"
                    if h_rem_pct > 50
                    else ("#D97706" if h_rem_pct > 25 else "#EF4444")
                )
                controls.append(
                    ft.Container(
                        padding=16,
                        bgcolor=ft.Colors.WHITE,
                        border_radius=14,
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Row(
                                            [
                                                ft.Container(
                                                    width=10,
                                                    height=32,
                                                    border_radius=5,
                                                    bgcolor=item.get(
                                                        "color", "#6366F1"
                                                    ),
                                                ),
                                                ft.Text(
                                                    item.get("title", ""),
                                                    size=16,
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                            ],
                                            spacing=10,
                                        ),
                                        ft.Row(
                                            [
                                                ft.Container(
                                                    padding=ft.Padding.symmetric(
                                                        horizontal=10, vertical=4
                                                    ),
                                                    border_radius=10,
                                                    bgcolor=st_bg,
                                                    content=ft.Text(
                                                        st_label,
                                                        size=11,
                                                        weight=ft.FontWeight.BOLD,
                                                        color=st_fg,
                                                    ),
                                                ),
                                                ft.IconButton(
                                                    icon=ft.Icons.TUNE_ROUNDED,
                                                    tooltip="Tune Target SLO",
                                                    on_click=lambda _e, it=item: self._open_slo_dialog(
                                                        it
                                                    ),
                                                ),
                                            ],
                                            spacing=4,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.Text(
                                    f"{window_days}d SLI: {item.get('current_sli', 0.0)}% vs "
                                    f"{item.get('target_slo', 85.0)}% SLO "
                                    f"({item.get('sli_delta', 0.0):+.1f}%) • "
                                    f"7d: {item.get('sli_7d', 0.0)}% • "
                                    f"30d: {item.get('sli_30d', 0.0)}% • "
                                    f"90d: {item.get('sli_90d', 0.0)}%",
                                    size=12,
                                    color=ft.Colors.BLUE_GREY_600,
                                ),
                                ft.ProgressBar(
                                    value=max(0.0, min(1.0, h_rem_pct / 100.0)),
                                    color=h_rem_color,
                                    bgcolor="#E2E8F0",
                                    height=8,
                                    border_radius=4,
                                ),
                                ft.Row(
                                    [
                                        ft.Text(
                                            f"Budget left: {h_rem_pct}% "
                                            f"({item.get('error_budget_used_days', 0)} missed / "
                                            f"{item.get('error_budget_allowed_days', 0.0)}d allowed, "
                                            f"{item.get('error_budget_remaining_days', 0.0):+.1f}d)",
                                            size=12,
                                            color=ft.Colors.BLUE_GREY_600,
                                        ),
                                        ft.Text(
                                            f"Burn: {item.get('burn_rate', 0.0)}x ({window_days}d) • "
                                            f"{item.get('burn_rate_7d', 0.0)}x (7d)",
                                            size=12,
                                            weight=ft.FontWeight.BOLD,
                                            color=st_fg,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    wrap=True,
                                ),
                            ],
                            spacing=8,
                        ),
                    )
                )

        return ft.Column(
            controls,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=14,
        )

    def _open_slo_dialog(self, item: dict[str, Any]) -> None:
        slo_input = ft.TextField(
            label="Target SLO (%)",
            value=str(item.get("target_slo", 85.0)),
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="1.0 - 100.0",
        )
        err_text = ft.Text("", color=ft.Colors.RED_600, size=12, visible=False)
        dialog = ft.AlertDialog(modal=True)

        def apply_preset(pct: float) -> None:
            slo_input.value = str(pct)
            err_text.visible = False
            self.page.update()

        preset_row = ft.Row(
            [
                ft.OutlinedButton(
                    content=ft.Text(f"{int(p)}%"),
                    on_click=lambda _e, val=p: apply_preset(val),
                )
                for p in (80.0, 85.0, 90.0, 95.0, 100.0)
            ],
            wrap=True,
            spacing=6,
        )

        async def save_slo(_e: Any) -> None:
            try:
                val = float((slo_input.value or "").strip())
            except ValueError:
                val = -1.0
            if not (1.0 <= val <= 100.0):
                err_text.value = "Target SLO must be between 1 and 100"
                err_text.visible = True
                self.page.update()
                return

            try:
                await self.api.update_habit(
                    item["habit_id"],
                    {"target_slo": round(val, 1)},
                )
                close_dialog(self.page, dialog)
                self._invalidate_tabs({2, 4})
                await self.refresh_current_tab(force=True)
                self.render_shell()
                show_toast(self.page, f"Updated SLO for {item.get('title', 'habit')}")
            except ApiError as err:
                err_text.value = err.message
                err_text.visible = True
                self.page.update()

        dialog.title = ft.Text(f"Tune SLO · {item.get('title', '')}")
        dialog.content = ft.Container(
            width=360,
            content=ft.Column(
                [
                    ft.Text(
                        "Choose a preset or enter a custom reliability objective (1–100%).",
                        size=13,
                        color=ft.Colors.BLUE_GREY_600,
                    ),
                    preset_row,
                    slo_input,
                    err_text,
                ],
                tight=True,
                spacing=10,
            ),
        )
        dialog.actions = [
            ft.TextButton(
                content=ft.Text("Cancel"),
                on_click=lambda _e: close_dialog(self.page, dialog),
            ),
            ft.FilledButton(
                content=ft.Text("Save SLO"),
                on_click=save_slo,
            ),
        ]
        open_dialog(self.page, dialog)

    def _open_change_password_dialog(self) -> None:
        current_input = ft.TextField(
            label="Current Password",
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            password=True,
            can_reveal_password=True,
        )
        new_input = ft.TextField(
            label="New Password (min 6 chars)",
            prefix_icon=ft.Icons.LOCK_RESET_ROUNDED,
            password=True,
            can_reveal_password=True,
        )
        confirm_input = ft.TextField(
            label="Confirm New Password",
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            password=True,
            can_reveal_password=True,
        )
        err_text = ft.Text("", color=ft.Colors.RED_600, size=12, visible=False)
        dialog = ft.AlertDialog(modal=True)
        submit_btn = ft.FilledButton(content=ft.Text("Update Password"))

        async def handle_save(_e: Any) -> None:
            err_text.visible = False
            cur = current_input.value or ""
            new_pwd = new_input.value or ""
            confirm_pwd = confirm_input.value or ""

            if not cur:
                err_text.value = "Please enter your current password"
                err_text.visible = True
                self.page.update()
                return
            if len(new_pwd) < 6:
                err_text.value = "New password must be at least 6 characters"
                err_text.visible = True
                self.page.update()
                return
            if new_pwd != confirm_pwd:
                err_text.value = "New passwords do not match"
                err_text.visible = True
                self.page.update()
                return
            if new_pwd == cur:
                err_text.value = "New password must be different from current password"
                err_text.visible = True
                self.page.update()
                return

            submit_btn.disabled = True
            self.page.update()
            try:
                await self.api.change_password(
                    current_password=cur, new_password=new_pwd
                )
                close_dialog(self.page, dialog)
                show_toast(self.page, "Password updated successfully!")
                return
            except ApiError as err:
                if err.status_code == 401:
                    close_dialog(self.page, dialog)
                    self._clear_tab_cache()
                    await self.api.logout()
                    self.render_auth_screen()
                    show_toast(self.page, err.message, is_error=True)
                    return
                err_text.value = err.message
                err_text.visible = True
            finally:
                submit_btn.disabled = False
                self.page.update()

        submit_btn.on_click = handle_save

        dialog.title = ft.Text("Change Password")
        dialog.content = ft.Container(
            width=360,
            content=ft.Column(
                [
                    current_input,
                    new_input,
                    confirm_input,
                    err_text,
                ],
                tight=True,
                spacing=10,
            ),
        )
        dialog.actions = [
            ft.TextButton(
                content=ft.Text("Cancel"),
                on_click=lambda _e: close_dialog(self.page, dialog),
            ),
            submit_btn,
        ]
        open_dialog(self.page, dialog)


async def main(page: ft.Page) -> None:
    tracker = HabitTrackerApp(page)
    await tracker.start()


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
