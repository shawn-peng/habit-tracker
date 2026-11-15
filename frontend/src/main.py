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
        self.show_archived: bool = False

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
            ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                padding=16,
                content=card,
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
        self.render_auth_screen()

    async def refresh_current_tab(self) -> None:
        try:
            if self.selected_tab == 0:
                self.today_habits = await self.api.get_today_habits(
                    self.selected_date.isoformat()
                )
            elif self.selected_tab == 1:
                self.all_habits = await self.api.list_habits(
                    include_archived=self.show_archived
                )
            elif self.selected_tab == 2:
                self.stats_summary = await self.api.get_stats_summary(
                    date.today().isoformat()
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
            self.content_area.content = self._build_habits_view()
        else:
            self.content_area.content = self._build_stats_view()

        user_name = (self.api.current_user or {}).get("name", "User")

        top_bar = ft.Container(
            bgcolor=ft.Colors.WHITE,
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
                        icon=ft.Icons.LIST_ALT_OUTLINED,
                        selected_icon=ft.Icons.LIST_ALT_ROUNDED,
                        label="Habits",
                    ),
                    ft.NavigationRailDestination(
                        icon=ft.Icons.INSIGHTS_OUTLINED,
                        selected_icon=ft.Icons.INSIGHTS_ROUNDED,
                        label="Stats",
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
                        icon=ft.Icons.LIST_ALT_OUTLINED,
                        selected_icon=ft.Icons.LIST_ALT_ROUNDED,
                        label="Habits",
                    ),
                    ft.NavigationBarDestination(
                        icon=ft.Icons.INSIGHTS_OUTLINED,
                        selected_icon=ft.Icons.INSIGHTS_ROUNDED,
                        label="Stats",
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
                            f"{streak}d",
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
        freq = (
            "Every day"
            if habit.get("frequency_type") == "daily"
            else ", ".join(WEEKDAY_LABELS[d] for d in habit.get("weekdays", []))
        )

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
                                        f"{freq} • Goal: {habit.get('target_per_day', 1)}/day",
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
        title_field = ft.TextField(
            label="Habit Title",
            value=existing["title"] if existing else "",
            hint_text="e.g., Read 20 pages, Drink water, Meditate",
        )
        desc_field = ft.TextField(
            label="Notes / Motivation (optional)",
            value=existing.get("description", "") if existing else "",
        )
        target_field = ft.TextField(
            label="Daily Target Count",
            value=str(existing.get("target_per_day", 1)) if existing else "1",
            keyboard_type=ft.KeyboardType.NUMBER,
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

        err_label = ft.Text("", color=ft.Colors.RED_600, size=12, visible=False)
        dialog = ft.AlertDialog(modal=True)

        async def save_habit(_e: Any) -> None:
            title = (title_field.value or "").strip()
            if not title:
                err_label.value = "Title is required"
                err_label.visible = True
                self.page.update()
                return

            chosen_days = [i for i, cb in enumerate(day_checks) if cb.value]
            if not chosen_days:
                err_label.value = "Pick at least one day of the week"
                err_label.visible = True
                self.page.update()
                return

            try:
                target_int = max(1, int(target_field.value or "1"))
            except ValueError:
                target_int = 1

            freq_type = "daily" if len(chosen_days) == 7 else "weekdays"
            payload = {
                "title": title,
                "description": (desc_field.value or "").strip(),
                "color": color_dropdown.value or "#6366F1",
                "frequency_type": freq_type,
                "weekdays": chosen_days,
                "target_per_day": target_int,
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
                    color_dropdown,
                    ft.Text("Schedule Days:", size=13, weight=ft.FontWeight.BOLD),
                    ft.Row(day_checks, wrap=True, spacing=6),
                    err_label,
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
                                        f"Current: {hs['current_streak']}d",
                                        weight=ft.FontWeight.BOLD,
                                        color="#D97706",
                                    ),
                                    ft.Text(
                                        f"Best: {hs['best_streak']}d",
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
        self, title: str, value: str, icon: Any, accent: str
    ) -> ft.Control:
        return ft.Container(
            width=210,
            padding=16,
            bgcolor=ft.Colors.WHITE,
            border_radius=14,
            content=ft.Row(
                [
                    ft.Icon(icon, color=accent, size=30),
                    ft.Column(
                        [
                            ft.Text(title, size=12, color=ft.Colors.BLUE_GREY_500),
                            ft.Text(value, size=19, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=12,
            ),
        )


async def main(page: ft.Page) -> None:
    tracker = HabitTrackerApp(page)
    await tracker.start()


if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)
