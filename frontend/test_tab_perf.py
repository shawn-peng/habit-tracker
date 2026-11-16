import asyncio
import sys
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import flet as ft

FRONTEND_SRC = Path(__file__).resolve().parent / "src"
if str(FRONTEND_SRC) not in sys.path:
    sys.path.insert(0, str(FRONTEND_SRC))

import api_client  # noqa: E402
from api_client import HabitApiClient, StorageHelper, _resolve_transport_base_url  # noqa: E402
from main import HabitTrackerApp  # noqa: E402


class _FakePage:
    def __init__(self, width: int = 900) -> None:
        self.width = width
        self.title = ""
        self.theme_mode = None
        self.bgcolor = None
        self.padding = 0
        self.on_resize = None
        self.on_disconnect = None
        self.navigation_bar = None
        self.controls: list[Any] = []
        self.overlay: list[Any] = []
        self.shared_preferences = None
        self.update_calls: list[tuple[Any, ...]] = []
        self.spawned_tasks: list[asyncio.Task[Any]] = []

    def add(self, *controls: Any) -> None:
        self.controls.extend(controls)

    def update(self, *controls: Any) -> None:
        self.update_calls.append(controls)

    def run_task(self, handler: Any, *args: Any, **kwargs: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(handler(*args, **kwargs))
        self.spawned_tasks.append(task)
        return task


def _collect_controls(root: Any) -> list[Any]:
    out: list[Any] = []
    if root is None:
        return out
    out.append(root)
    for attr in ("content", "leading", "trailing"):
        child = getattr(root, attr, None)
        if child is not None:
            out.extend(_collect_controls(child))
    for attr in ("controls", "actions"):
        children = getattr(root, attr, None)
        if isinstance(children, list):
            for child in children:
                out.extend(_collect_controls(child))
    return out


def _sample_today_habit(
    hid: str = "h1",
    *,
    count: int = 0,
    completed: bool = False,
    current_streak: int = 2,
) -> dict[str, Any]:
    return {
        "id": hid,
        "title": "Read 20 mins",
        "description": "",
        "color": "#6366F1",
        "category": "Learning",
        "target_per_day": 1,
        "frequency_type": "daily",
        "schedule_type": "daily",
        "schedule_days": [],
        "archived": False,
        "target_slo": 80.0,
        "date": date.today().isoformat(),
        "scheduled_today": True,
        "count": count,
        "completed": completed,
        "note": None,
        "current_streak": current_streak,
        "best_streak": 5,
    }


def _sample_habit(hid: str = "h1", title: str = "Read 20 mins") -> dict[str, Any]:
    return {
        "id": hid,
        "title": title,
        "description": "",
        "color": "#6366F1",
        "category": "Learning",
        "target_per_day": 1,
        "frequency_type": "daily",
        "schedule_type": "daily",
        "schedule_days": [],
        "archived": False,
        "target_slo": 80.0,
    }


def _sample_schedule() -> dict[str, Any]:
    today_iso = date.today().isoformat()
    return {
        "period": "week",
        "start_date": today_iso,
        "end_date": today_iso,
        "label": "This Week",
        "summary": {
            "total_due": 1,
            "completed": 0,
            "remaining": 1,
            "overdue": 0,
            "completion_rate": 0.0,
        },
        "overdue_items": [],
        "days": [],
    }


def _sample_stats() -> dict[str, Any]:
    return {
        "total_habits": 1,
        "completed_today": 0,
        "due_today": 1,
        "overall_adherence_7d": 50.0,
        "overall_adherence_30d": 50.0,
        "habit_stats": [],
        "daily_activity": [],
    }


def _make_authenticated_app(width: int = 900) -> tuple[HabitTrackerApp, _FakePage]:
    page = _FakePage(width=width)
    app = HabitTrackerApp(page)  # type: ignore[arg-type]
    app.api.current_user = {"id": "u1", "name": "Tester", "email": "t@example.com"}
    app.api.token = "jwt-token"
    app.api.logout = AsyncMock()
    app.api.aclose = AsyncMock()
    app.api.get_today_habits = AsyncMock(return_value=[_sample_today_habit()])
    app.api.list_habits = AsyncMock(return_value=[_sample_habit()])
    app.api.get_period_schedule = AsyncMock(return_value=_sample_schedule())
    app.api.get_stats_summary = AsyncMock(return_value=_sample_stats())
    app.api.checkin_habit = AsyncMock(
        return_value=_sample_today_habit(count=1, completed=True, current_streak=3)
    )
    return app, page


class ApiClientPerfTests(unittest.TestCase):
    def test_resolve_transport_base_url(self) -> None:
        self.assertEqual(
            _resolve_transport_base_url("http://localhost:8000"),
            "http://127.0.0.1:8000",
        )
        self.assertEqual(
            _resolve_transport_base_url("http://LOCALHOST"),
            "http://127.0.0.1",
        )
        self.assertEqual(
            _resolve_transport_base_url("http://user:pw@localhost:8080/v1"),
            "http://user:pw@127.0.0.1:8080/v1",
        )
        # Do not rewrite HTTPS URLs (SNI / cert hostname must remain intact).
        self.assertEqual(
            _resolve_transport_base_url("https://localhost:8443"),
            "https://localhost:8443",
        )
        self.assertEqual(
            _resolve_transport_base_url("https://example.com"),
            "https://example.com",
        )
        with patch.object(api_client.sys, "platform", "emscripten"):
            self.assertEqual(
                _resolve_transport_base_url("http://localhost:8000"),
                "http://localhost:8000",
            )


class ApiClientPoolAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_connection_pool_reused_and_aclose_closes_client(self) -> None:
        created_clients: list[Any] = []

        class _FakeResponse:
            status_code = 200
            content = b'{"ok": true}'

            def json(self) -> dict[str, Any]:
                return {"ok": True}

        class _FakeAsyncClient:
            def __init__(self, **_kwargs: Any) -> None:
                self.is_closed = False
                self.requests: list[tuple[str, str]] = []
                self.aclose = AsyncMock(side_effect=self._mark_closed)
                created_clients.append(self)

            async def _mark_closed(self) -> None:
                self.is_closed = True

            async def request(self, method: str, url: str, **_kwargs: Any) -> _FakeResponse:
                self.requests.append((method, url))
                return _FakeResponse()

        page = _FakePage()
        client = HabitApiClient(StorageHelper(page))  # type: ignore[arg-type]
        await client.set_base_url("http://localhost:8000")

        with patch.object(api_client.httpx, "AsyncClient", side_effect=_FakeAsyncClient):
            await client._request("GET", "/health")
            await client._request("GET", "/api/me")

            self.assertEqual(len(created_clients), 1)
            self.assertEqual(
                created_clients[0].requests,
                [
                    ("GET", "http://127.0.0.1:8000/health"),
                    ("GET", "http://127.0.0.1:8000/api/me"),
                ],
            )
            self.assertEqual(client.base_url, "http://localhost:8000")

            await client.aclose()
            created_clients[0].aclose.assert_awaited_once()
            self.assertIsNone(client._client)

            await client._request("GET", "/health")
            self.assertEqual(len(created_clients), 2)
            await client.aclose()


class TabPerfTests(unittest.IsolatedAsyncioTestCase):
    async def _flush_bg_task(self, app: HabitTrackerApp) -> None:
        task = app._bg_refresh_task
        if task is not None:
            await task

    async def test_clean_tab_switch_zero_extra_requests_and_keeps_shell_mounted(
        self,
    ) -> None:
        app, page = _make_authenticated_app()
        await app.refresh_current_tab(force=True)
        app.render_shell()

        self.assertEqual(len(page.controls), 1)
        initial_root = page.controls[0]
        self.assertEqual(app.api.get_today_habits.await_count, 1)

        # Switch 0 -> 2 (cold): shows loading view first, then loads in background.
        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=2)))
        self.assertIs(page.controls[0], initial_root)
        self.assertEqual(app.selected_tab, 2)
        await self._flush_bg_task(app)
        self.assertEqual(app.api.list_habits.await_count, 1)
        self.assertIs(page.controls[0], initial_root)

        # Patch Control.page so attached partial updates execute self.page.update(*controls).
        with patch.object(ft.Control, "page", new=property(lambda _c: page)):
            page.update_calls.clear()
            await app._on_nav_change(
                SimpleNamespace(control=SimpleNamespace(selected_index=0))
            )
            self.assertEqual(app.api.get_today_habits.await_count, 1)
            self.assertIs(page.controls[0], initial_root)
            self.assertIsNone(app._bg_refresh_task)
            self.assertEqual(len(page.update_calls), 1)
            self.assertEqual(
                page.update_calls[0], (app.content_area, app._shell_nav)
            )

            # Switch 0 -> 2 with fresh cache: 0 extra API calls, 1 partial update.
            await app._on_nav_change(
                SimpleNamespace(control=SimpleNamespace(selected_index=2))
            )
            self.assertEqual(app.api.list_habits.await_count, 1)
            self.assertIs(page.controls[0], initial_root)
            self.assertEqual(len(page.update_calls), 2)

    async def test_stale_tab_renders_cached_immediately_skips_unchanged_and_updates_changed(
        self,
    ) -> None:
        app, page = _make_authenticated_app()
        await app.refresh_current_tab(force=True)
        app.render_shell()

        # Populate Tab 2 cleanly then return to Tab 0.
        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=2)))
        await self._flush_bg_task(app)
        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=0)))

        # Expire Tab 2 cache beyond TTL; API returns identical data -> skip 2nd redraw.
        tab2_key = (2, (False,))
        data, _ts, gen = app._tab_cache[tab2_key]
        app._tab_cache[tab2_key] = (data, time.monotonic() - 120.0, gen)
        page.update_calls.clear()

        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=2)))
        self.assertEqual(len(page.update_calls), 1)
        await self._flush_bg_task(app)
        self.assertEqual(app.api.list_habits.await_count, 2)
        self.assertEqual(len(page.update_calls), 1)
        self.assertTrue(app._is_cache_fresh(tab2_key))

        # Now return to Tab 0, expire Tab 2 again, and change API data -> triggers 2nd redraw.
        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=0)))
        new_habits = [_sample_habit("h2", "Meditate")]
        app.api.list_habits = AsyncMock(return_value=new_habits)
        data, _ts, gen = app._tab_cache[tab2_key]
        app._tab_cache[tab2_key] = (data, time.monotonic() - 120.0, gen)
        page.update_calls.clear()

        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=2)))
        self.assertEqual(len(page.update_calls), 1)
        await self._flush_bg_task(app)
        self.assertEqual(len(page.update_calls), 2)
        self.assertEqual(app.all_habits, new_habits)

    async def test_rapid_tab_switching_cancels_obsolete_inflight_task(self) -> None:
        app, _page = _make_authenticated_app()
        await app.refresh_current_tab(force=True)
        app.render_shell()

        gate = asyncio.Event()
        started = asyncio.Event()
        cancelled = False

        async def slow_schedule(**_kwargs: Any) -> dict[str, Any]:
            nonlocal cancelled
            started.set()
            try:
                await gate.wait()
            except asyncio.CancelledError:
                cancelled = True
                raise
            return _sample_schedule()

        app.api.get_period_schedule = AsyncMock(side_effect=slow_schedule)

        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=1)))
        slow_task = app._bg_refresh_task
        self.assertIsNotNone(slow_task)
        await started.wait()

        # Rapidly switch to Tab 2 before Tab 1 finishes.
        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=2)))
        await self._flush_bg_task(app)
        await asyncio.sleep(0)

        self.assertTrue(cancelled)
        self.assertTrue(slow_task.cancelled())
        self.assertEqual(app.selected_tab, 2)
        self.assertIsNone(app.period_schedule)

    async def test_cold_tab_cancelled_error_clears_loading_keys(self) -> None:
        app, _page = _make_authenticated_app()
        await app.refresh_current_tab(force=True)
        app.render_shell()

        gate = asyncio.Event()
        started = asyncio.Event()

        async def slow_stats(_today: str) -> dict[str, Any]:
            started.set()
            await gate.wait()
            return _sample_stats()

        app.api.get_stats_summary = AsyncMock(side_effect=slow_stats)

        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=3)))
        tab3_key = app._current_tab_key(3)
        self.assertIn(tab3_key, app._loading_keys)
        task = app._bg_refresh_task
        self.assertIsNotNone(task)
        await started.wait()

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertNotIn(tab3_key, app._loading_keys)

    async def test_today_checkin_updates_in_place_and_leaves_tab2_clean(self) -> None:
        app, _page = _make_authenticated_app()
        await app.refresh_current_tab(force=True)
        app.render_shell()

        # Warm Tab 2 so we can confirm Tab 0 check-in does NOT dirty Tab 2.
        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=2)))
        await self._flush_bg_task(app)
        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=0)))

        checkin_buttons = [
            ctrl
            for ctrl in _collect_controls(app.content_area)
            if isinstance(ctrl, ft.IconButton) and getattr(ctrl, "tooltip", None) == "Check in"
        ]
        self.assertEqual(len(checkin_buttons), 1)
        await checkin_buttons[0].on_click(None)

        app.api.checkin_habit.assert_awaited_once()
        self.assertEqual(app.api.get_today_habits.await_count, 1)
        self.assertTrue(app.today_habits[0]["completed"])
        self.assertEqual(app.today_habits[0]["count"], 1)
        self.assertTrue(app._is_cache_fresh(app._current_tab_key(0)))
        self.assertNotIn(2, app._tab_dirty)
        self.assertTrue({1, 3, 4}.issubset(app._tab_dirty))

        # Switching back to Tab 2 makes 0 extra list_habits requests.
        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=2)))
        self.assertEqual(app.api.list_habits.await_count, 1)

    async def test_handle_resize_only_rebuilds_across_760_threshold(self) -> None:
        app, page = _make_authenticated_app(width=900)
        await app.refresh_current_tab(force=True)
        app.render_shell()
        desktop_root = page.controls[0]

        # Staying >= 760 does NOT rebuild the shell.
        page.width = 1120
        app._handle_resize(None)
        self.assertIs(page.controls[0], desktop_root)
        self.assertTrue(app._shell_wide)

        # Crossing below 760 rebuilds into mobile NavigationBar layout.
        page.width = 500
        app._handle_resize(None)
        mobile_root = page.controls[0]
        self.assertIsNot(mobile_root, desktop_root)
        self.assertFalse(app._shell_wide)
        self.assertIsInstance(page.navigation_bar, ft.NavigationBar)

        # Staying < 760 does NOT rebuild again.
        page.width = 400
        app._handle_resize(None)
        self.assertIs(page.controls[0], mobile_root)

        # Crossing back >= 760 restores wide NavigationRail layout.
        page.width = 820
        app._handle_resize(None)
        self.assertIsNot(page.controls[0], mobile_root)
        self.assertTrue(app._shell_wide)
        self.assertIsNone(page.navigation_bar)

    async def test_disconnect_cancels_bg_task_and_closes_api_client(self) -> None:
        app, _page = _make_authenticated_app()
        await app.refresh_current_tab(force=True)
        app.render_shell()

        gate = asyncio.Event()
        started = asyncio.Event()

        async def slow_stats(_today: str) -> dict[str, Any]:
            started.set()
            await gate.wait()
            return _sample_stats()

        app.api.get_stats_summary = AsyncMock(side_effect=slow_stats)
        await app._on_nav_change(SimpleNamespace(control=SimpleNamespace(selected_index=3)))
        task = app._bg_refresh_task
        await started.wait()

        await app._handle_disconnect(None)
        await asyncio.sleep(0)

        self.assertTrue(task.cancelled())
        self.assertFalse(app._shell_mounted)
        app.api.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
