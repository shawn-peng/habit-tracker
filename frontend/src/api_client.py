import asyncio
from datetime import date, datetime
import os
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import flet as ft
import httpx

STORAGE_TOKEN_KEY = "habit_tracker_jwt"
STORAGE_API_URL_KEY = "habit_tracker_api_url"
STORAGE_REMINDERS_MUTED_KEY = "habit_tracker_reminders_muted"
DEFAULT_API_URL = os.getenv(
    "HABIT_API_URL",
    "https://habit-tracker-api-142205380680.us-central1.run.app",
)


def _resolve_transport_base_url(base_url: str) -> str:
    """Map http://localhost to 127.0.0.1 off-browser to avoid Windows IPv6 fallback delays."""
    if sys.platform == "emscripten":
        return base_url
    parsed = urlsplit(base_url)
    if parsed.scheme.lower() != "http" or (parsed.hostname or "").lower() != "localhost":
        return base_url
    netloc = "127.0.0.1"
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username is not None:
        auth = parsed.username
        if parsed.password is not None:
            auth = f"{auth}:{parsed.password}"
        netloc = f"{auth}@{netloc}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class StorageHelper:
    """Cross-platform persistent storage wrapper compatible with Flet 1.0+."""

    def __init__(self, page: ft.Page):
        self.page = page
        self._memory: dict[str, str] = {}
        self._prefs = ft.SharedPreferences() if hasattr(ft, "SharedPreferences") else None

    async def get(self, key: str) -> str | None:
        if key in self._memory:
            return self._memory[key]
        try:
            if self._prefs is not None:
                val = await self._prefs.get(key)
                if val is not None:
                    self._memory[key] = str(val)
                    return str(val)
            elif hasattr(self.page, "client_storage"):
                val = await self.page.client_storage.get_async(key)
                if val is not None:
                    self._memory[key] = str(val)
                    return str(val)
        except Exception:
            pass
        return None

    async def set(self, key: str, value: str) -> None:
        self._memory[key] = value
        try:
            if self._prefs is not None:
                await self._prefs.set(key, value)
            elif hasattr(self.page, "client_storage"):
                await self.page.client_storage.set_async(key, value)
        except Exception:
            pass

    async def remove(self, key: str) -> None:
        self._memory.pop(key, None)
        try:
            if self._prefs is not None:
                await self._prefs.remove(key)
            elif hasattr(self.page, "client_storage"):
                await self.page.client_storage.remove_async(key)
        except Exception:
            pass


class HabitApiClient:
    """Async HTTP client compatible across Desktop, iOS, Android, and Web (Pyodide)."""

    def __init__(self, storage: StorageHelper):
        self.storage = storage
        self.base_url: str = DEFAULT_API_URL.rstrip("/")
        self.token: str | None = None
        self.current_user: dict[str, Any] | None = None
        self._client: httpx.AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Return a pooled AsyncClient bound to the active event loop."""
        loop = asyncio.get_running_loop()
        if (
            self._client is None
            or self._client.is_closed
            or self._client_loop is not loop
        ):
            self._client = httpx.AsyncClient(timeout=12.0)
            self._client_loop = loop
        return self._client

    async def aclose(self) -> None:
        """Close the pooled HTTP client when bound to the current event loop."""
        client = self._client
        client_loop = self._client_loop
        self._client = None
        self._client_loop = None
        if client is not None and not client.is_closed:
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if client_loop is None or client_loop is running_loop:
                await client.aclose()

    async def initialize(self) -> bool:
        saved_url = await self.storage.get(STORAGE_API_URL_KEY)
        if saved_url:
            self.base_url = saved_url.rstrip("/")

        saved_token = await self.storage.get(STORAGE_TOKEN_KEY)
        if not saved_token:
            return False

        self.token = saved_token
        try:
            self.current_user = await self.get_me()
            return True
        except ApiError:
            await self.logout()
            return False

    async def set_base_url(self, url: str) -> None:
        cleaned = url.strip().rstrip("/")
        if cleaned:
            self.base_url = cleaned
            await self.storage.set(STORAGE_API_URL_KEY, cleaned)

    async def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        transport_base = _resolve_transport_base_url(self.base_url).rstrip("/")
        url = f"{transport_base}{path}"
        try:
            client = self._get_client()
            resp = await client.request(
                method=method,
                url=url,
                json=json_body,
                params=params,
                headers=headers,
            )
        except Exception as exc:
            raise ApiError(
                f"Cannot reach server at {self.base_url} ({exc})"
            ) from exc

        if resp.status_code == 204:
            return None

        if resp.status_code >= 400:
            detail = f"Server error ({resp.status_code})"
            try:
                err_data = resp.json()
                if isinstance(err_data.get("detail"), str):
                    detail = err_data["detail"]
                elif isinstance(err_data.get("detail"), list) and err_data["detail"]:
                    detail = err_data["detail"][0].get("msg", detail)
            except Exception:
                pass
            raise ApiError(detail, status_code=resp.status_code)

        return resp.json()

    async def _save_session(self, data: dict[str, Any]) -> dict[str, Any]:
        self.token = data["access_token"]
        self.current_user = data["user"]
        await self.storage.set(STORAGE_TOKEN_KEY, self.token)
        return self.current_user

    async def register(self, name: str, email: str, password: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/auth/register",
            json_body={"name": name, "email": email, "password": password},
        )

    async def verify_email(self, email: str, code: str) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/api/auth/verify-email",
            json_body={"email": email, "code": code},
        )
        return await self._save_session(data)

    async def resend_verification(self, email: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/auth/resend-verification",
            json_body={"email": email},
        )

    async def login(self, email: str, password: str) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/api/auth/login",
            json_body={"email": email, "password": password},
        )
        return await self._save_session(data)

    async def forgot_password(self, email: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/auth/forgot-password",
            json_body={"email": email},
        )

    async def reset_password(
        self, email: str, code: str, new_password: str
    ) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/api/auth/reset-password",
            json_body={
                "email": email,
                "code": code,
                "new_password": new_password,
            },
        )
        return await self._save_session(data)

    async def change_password(
        self, current_password: str, new_password: str
    ) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/api/auth/change-password",
            json_body={
                "current_password": current_password,
                "new_password": new_password,
            },
        )
        return await self._save_session(data)

    async def get_me(self) -> dict[str, Any]:
        return await self._request("GET", "/api/auth/me")

    async def logout(self) -> None:
        self.token = None
        self.current_user = None
        await self.storage.remove(STORAGE_TOKEN_KEY)

    async def get_today_habits(
        self,
        target_date: str,
        client_today: str | None = None,
        client_time: str | None = None,
    ) -> list[dict[str, Any]]:
        now_dt = datetime.now()
        return await self._request(
            "GET",
            "/api/habits/today",
            params={
                "target_date": target_date,
                "client_today": client_today or now_dt.date().isoformat(),
                "client_time": client_time or now_dt.strftime("%H:%M"),
            },
        )

    async def get_period_schedule(
        self,
        period: str = "week",
        anchor_date: str | None = None,
        today: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"period": period}
        if anchor_date:
            params["anchor_date"] = anchor_date
        if today:
            params["today"] = today
        return await self._request("GET", "/api/habits/schedule", params=params)

    async def list_habits(self, include_archived: bool = False) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            "/api/habits",
            params={"include_archived": str(include_archived).lower()},
        )

    async def create_habit(self, payload: dict[str, Any]) -> dict[str, Any]:
        now_dt = datetime.now()
        body: dict[str, Any] = {
            "created_date": now_dt.date().isoformat(),
            "created_time": now_dt.strftime("%H:%M"),
            **payload,
        }
        return await self._request("POST", "/api/habits", json_body=body)

    async def update_habit(
        self, habit_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request("PATCH", f"/api/habits/{habit_id}", json_body=payload)

    async def delete_habit(self, habit_id: str) -> None:
        await self._request("DELETE", f"/api/habits/{habit_id}")

    async def checkin_habit(
        self,
        habit_id: str,
        target_date: str,
        action: str = "increment",
        count: int | None = None,
        note: str | None = None,
        status_override: str | None = None,
        client_today: str | None = None,
        client_time: str | None = None,
    ) -> dict[str, Any]:
        now_dt = datetime.now()
        body: dict[str, Any] = {
            "date": target_date,
            "action": action,
            "client_today": client_today or now_dt.date().isoformat(),
            "client_time": client_time or now_dt.strftime("%H:%M"),
        }
        if count is not None:
            body["count"] = count
        if note is not None:
            body["note"] = note
        if status_override is not None:
            body["status_override"] = status_override
        return await self._request(
            "POST", f"/api/habits/{habit_id}/checkin", json_body=body
        )

    async def get_habit_history(
        self,
        habit_id: str,
        month: str | None = None,
        client_today: str | None = None,
        client_time: str | None = None,
    ) -> dict[str, Any]:
        now_dt = datetime.now()
        params: dict[str, Any] = {
            "client_today": client_today or now_dt.date().isoformat(),
            "client_time": client_time or now_dt.strftime("%H:%M"),
        }
        if month:
            params["month"] = month
        return await self._request(
            "GET", f"/api/habits/{habit_id}/history", params=params
        )

    async def get_stats_summary(
        self, today: str, client_time: str | None = None
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/stats/summary",
            params={
                "today": today,
                "client_time": client_time or datetime.now().strftime("%H:%M"),
            },
        )

    async def get_sli_dashboard(
        self, today: str, window_days: int = 30, client_time: str | None = None
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/stats/sli",
            params={
                "today": today,
                "window_days": window_days,
                "client_time": client_time or datetime.now().strftime("%H:%M"),
            },
        )

    async def get_reminders_overview(
        self, target_date: str, now_time: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"target_date": target_date}
        if now_time:
            params["now_time"] = now_time
        return await self._request("GET", "/api/habits/reminders", params=params)


def open_dialog(page: ft.Page, dialog: ft.AlertDialog) -> None:
    if hasattr(page, "show_dialog"):
        page.show_dialog(dialog)
    elif hasattr(page, "open"):
        page.open(dialog)


def close_dialog(page: ft.Page, dialog: ft.AlertDialog) -> None:
    if hasattr(page, "_dialogs") and getattr(dialog, "page", None) is not None:
        dialog.open = False
        dialog.update()
    elif (
        hasattr(page, "dialogs")
        and isinstance(getattr(page, "dialogs"), list)
        and dialog in page.dialogs
    ):
        page.dialogs.remove(dialog)
    elif hasattr(page, "pop_dialog"):
        page.pop_dialog()
    elif hasattr(page, "close"):
        page.close(dialog)


def show_toast(page: ft.Page, message: str, is_error: bool = False) -> None:
    bar = ft.SnackBar(
        content=ft.Text(message, color=ft.Colors.WHITE),
        bgcolor=ft.Colors.RED_600 if is_error else ft.Colors.TEAL_700,
    )
    if hasattr(page, "show_dialog"):
        page.show_dialog(bar)
    elif hasattr(page, "open"):
        page.open(bar)
