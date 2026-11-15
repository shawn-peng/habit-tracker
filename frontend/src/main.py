import calendar
from datetime import date, timedelta
from typing import Any
import flet as ft

from api_client import (
    ApiError,
    HabitApiClient,
    StorageHelper,
    close_dialog,
    open_dialog,
    show_toast,
)

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

        self.content_area = ft.Container(expand=True, padding=20)

    async def start(self) -> None:
        self.page.title = "Habit & Routine Tracker"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = "#F8FAFC"
        self.page.padding = 0
        self.page.on_resize = self._handle_resize

        # Initial loading indicator while checking saved session
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
            await self.refresh_current_tab()
            self.render_shell()
        else:
            self.render_auth_screen()

    def _is_wide(self) -> bool:
        width = self.page.width or 900
        return width >= 760

    def _handle_resize(self, _e: Any) -> None:
        if self.api.current_user is not None:
            self.render_shell()

    # -----------------------------------------------------------------------
    # Authentication Screen (Login / Register + Server URL Config)
    # -----------------------------------------------------------------------
    def render_auth_screen(self, is_register: bool = False) -> None:
        self.page.navigation_bar = None
        self.page.controls.clear()

        server_input = ft.TextField(
            label="Server API URL",
            value=self.api.base_url,
            prefix_icon=ft.Icons.CLOUD_OUTLINED,
            hint_text="http://localhost:8000 or https://your-server.com",
        )
        name_input = ft.TextField(
            label="Your Name",
            prefix_icon=ft.Icons.PERSON_OUTLINE,
            visible=is_register,
        )
        email_input = ft.TextField(
            label="Email",
            prefix_icon=ft.Icons.EMAIL_OUTLINED,
            keyboard_type=ft.KeyboardType.EMAIL,
        )
        password_input = ft.TextField(
            label="Password",
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            password=True,
            can_reveal_password=True,
        )
        error_text = ft.Text("", color=ft.Colors.RED_600, size=13, visible=False)
        submit_btn = ft.FilledButton(
            content=ft.Text("Create Account" if is_register else "Sign In"),
            width=340,
        )

        async def handle_submit(_e: Any) -> None:
            error_text.visible = False
            submit_btn.disabled = True
            self.page.update()

            await self.api.set_base_url(server_input.value or "http://localhost:8000")
            email = (email_input.value or "").strip()
            pwd = password_input.value or ""
            name = (name_input.value or "").strip()

            try:
                if is_register:
                    if not name:
                        raise ApiError("Please enter your name")
                    await self.api.register(name=name, email=email, password=pwd)
                else:
                    await self.api.login(email=email, password=pwd)

                self.selected_tab = 0
                await self.refresh_current_tab()
                self.render_shell()
                return
            except ApiError as err:
                error_text.value = err.message
                error_text.visible = True
            finally:
                submit_btn.disabled = False
                self.page.update()

        submit_btn.on_click = handle_submit

        def toggle_mode(_e: Any) -> None:
            self.render_auth_screen(is_register=not is_register)

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
                        "Sync your daily routines across iPhone, Mac, Android & Web",
                        size=13,
                        color=ft.Colors.BLUE_GREY_600,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Divider(height=16),
                    server_input,
                    name_input,
                    email_input,
                    password_input,
                    error_text,
                    submit_btn,
                    ft.TextButton(
                        content=ft.Text(
                            "Already have an account? Sign In"
                            if is_register
                            else "New here? Create an Account"
                        ),
                        on_click=toggle_mode,
                    ),
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
        self.selected_tab = int(e.control.selected_index)
        await self.refresh_current_tab()
        self.render_shell()

    async def _handle_logout(self, _e: Any) -> None:
        await self.api.logout()
        self.period_schedule = None
        self.schedule_period = "week"
        self.schedule_anchor_date = date.today()
        self.render_auth_screen()

    async def refresh_current_tab(self) -> None:
        try:
            if self.selected_tab == 0:
                self.today_habits = await self.api.get_today_habits(
                    self.selected_date.isoformat()
                )
            elif self.selected_tab == 1:
                self.period_schedule = await self.api.get_period_schedule(
                    period=self.schedule_period,
                    anchor_date=self.schedule_anchor_date.isoformat(),
                    today=date.today().isoformat(),
                )
            elif self.selected_tab == 2:
                self.all_habits = await self.api.list_habits(
                    include_archived=self.show_archived
                )
            elif self.selected_tab == 3:
                self.stats_summary = await self.api.get_stats_summary(
                    date.today().isoformat()
                )
            elif self.selected_tab == 4:
                self.sli_dashboard = await self.api.get_sli_dashboard(
                    date.today().isoformat(),
                    window_days=self.sli_window_days,
                )
        except ApiError as err:
            if err.status_code == 401:
                await self.api.logout()
                self.render_auth_screen()
                return
            show_toast(self.page, err.message, is_error=True)

    def render_shell(self) -> None:
        if self.selected_tab == 0:
            self.content_area.content = self._build_today_view()
        elif self.selected_tab == 1:
            self.content_area.content = self._build_schedule_view()
        elif self.selected_tab == 2:
            self.content_area.content = self._build_habits_view()
        elif self.selected_tab == 3:
            self.content_area.content = self._build_stats_view()
        else:
            self.content_area.content = self._build_sli_view()

        user_name = (self.api.current_user or {}).get("name", "User")

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
        if self._is_wide():
            # Mac / Desktop / Wide Web layout: Left NavigationRail
            self.page.navigation_bar = None
            rail = ft.NavigationRail(
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
            self.page.add(
                ft.Column(
                    [
                        top_bar,
                        ft.Divider(height=1),
                        ft.Row(
                            [rail, ft.VerticalDivider(width=1), self.content_area],
                            expand=True,
                            spacing=0,
                        ),
                    ],
                    expand=True,
                    spacing=0,
                )
            )
        else:
            # iPhone / Android / Mobile Web layout: Bottom NavigationBar
            self.page.navigation_bar = ft.NavigationBar(
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
            self.page.add(
                ft.Column(
                    [top_bar, ft.Divider(height=1), self.content_area],
                    expand=True,
                    spacing=0,
                )
            )
        self.page.update()

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
                await self.refresh_current_tab()
                self.render_shell()

        async def prev_day(_e: Any) -> None:
            await shift_date(-1)

        async def next_day(_e: Any) -> None:
            await shift_date(1)

        scheduled_items = [h for h in self.today_habits if h.get("scheduled_today")]
        extra_items = [h for h in self.today_habits if not h.get("scheduled_today")]
        done_count = sum(1 for h in scheduled_items if h.get("completed"))
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

        progress_card = ft.Container(
            padding=18,
            border_radius=14,
            bgcolor="#EEF2FF",
            content=ft.Column(
                [
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
                ],
                spacing=10,
            ),
        )

        cards: list[ft.Control] = [header_row, progress_card]

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

        async def do_checkin(action: str) -> None:
            try:
                await self.api.checkin_habit(
                    habit_id=hid,
                    target_date=self.selected_date.isoformat(),
                    action=action,
                )
                await self.refresh_current_tab()
                self.render_shell()
            except ApiError as err:
                show_toast(self.page, err.message, is_error=True)

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

        if target > 1 and count > 0:
            controls_right.append(
                ft.IconButton(
                    icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    icon_size=22,
                    tooltip="Decrease count",
                    on_click=on_decrement,
                )
            )

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
                icon_color=color if completed else ft.Colors.BLUE_GREY_400,
                icon_size=30,
                tooltip="Check in",
                on_click=on_primary_tap,
            )
        )

        subtitle_parts = []
        if is_monthly:
            subtitle_parts.append(format_habit_schedule(item))
        if target > 1:
            subtitle_parts.append(f"{count} / {target} today")
        if item.get("description"):
            subtitle_parts.append(item["description"])
        subtitle = " • ".join(subtitle_parts)

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
                                    ft.Text(
                                        item["title"],
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
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
            await self.refresh_current_tab()
            self.render_shell()

        async def shift_period(delta: int) -> None:
            if self.schedule_period == "week":
                self.schedule_anchor_date = self.schedule_anchor_date + timedelta(
                    days=7 * delta
                )
            else:
                self.schedule_anchor_date = self._shift_month(
                    self.schedule_anchor_date, delta
                )
            await self.refresh_current_tab()
            self.render_shell()

        async def jump_current(_e: Any) -> None:
            self.schedule_anchor_date = date.today()
            await self.refresh_current_tab()
            self.render_shell()

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
                                        f"{sched_desc} • Goal: {summary.get('target_per_day', 1)}/day",
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

        async def do_checkin(action: str) -> None:
            try:
                await self.api.checkin_habit(
                    habit_id=hid,
                    target_date=target_date,
                    action=action,
                )
                await self.refresh_current_tab()
                self.render_shell()
            except ApiError as err:
                show_toast(self.page, err.message, is_error=True)

        async def on_primary_tap(_e: Any) -> None:
            await do_checkin("toggle" if target == 1 else "increment")

        async def on_decrement(_e: Any) -> None:
            await do_checkin("decrement")

        status_labels = {
            "completed": "Done",
            "today": "Due today",
            "upcoming": "Upcoming",
            "overdue": "Missed",
        }
        subtitle_parts = [status_labels.get(status_val, "")]
        if target > 1:
            subtitle_parts.append(f"{count} / {target}")
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
            if target > 1 and count > 0:
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
                        ft.Icons.CHECK_CIRCLE_ROUNDED
                        if completed
                        else (
                            ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED
                            if target > 1
                            else ft.Icons.RADIO_BUTTON_UNCHECKED_ROUNDED
                        )
                    ),
                    icon_color=color if completed else (
                        "#DC2626" if status_val == "overdue" else ft.Colors.BLUE_GREY_400
                    ),
                    icon_size=26,
                    tooltip="Check in",
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
            await self.refresh_current_tab()
            self.render_shell()

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
                await self.refresh_current_tab()
                self.render_shell()
            except ApiError as err:
                show_toast(self.page, err.message, is_error=True)

        async def remove_habit(_e: Any) -> None:
            try:
                await self.api.delete_habit(hid)
                await self.refresh_current_tab()
                self.render_shell()
                show_toast(self.page, "Habit deleted")
            except ApiError as err:
                show_toast(self.page, err.message, is_error=True)

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
                                        f"{freq} • Goal: {habit.get('target_per_day', 1)}/{goal_unit} • SLO: {habit.get('target_slo', 85.0)}%",
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
            }

            try:
                if is_edit and existing:
                    await self.api.update_habit(existing["id"], payload)
                else:
                    await self.api.create_habit(payload)
                close_dialog(self.page, dialog)
                await self.refresh_current_tab()
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
            ratio = (comp / sched) if sched > 0 else 0.0
            bar_height = max(8, int(ratio * 100))
            bars.append(
                ft.Column(
                    [
                        ft.Text(f"{comp}/{sched}", size=11, color=ft.Colors.BLUE_GREY_600),
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
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
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
                                                f"30d rate: {hs['completion_rate_30d']}% • Total check-ins: {hs['total_completions']}",
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
            await self.refresh_current_tab()
            self.render_shell()

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
                await self.refresh_current_tab()
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


async def main(page: ft.Page) -> None:
    tracker = HabitTrackerApp(page)
    await tracker.start()


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
