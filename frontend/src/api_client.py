import os
from typing import Any
import flet as ft
import httpx

STORAGE_TOKEN_KEY = "habit_tracker_jwt"
STORAGE_API_URL_KEY = "habit_tracker_api_url"
DEFAULT_API_URL = os.getenv("HABIT_API_URL", "http://localhost:8000")


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

        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
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

    async def register(self, name: str, email: str, password: str) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/api/auth/register",
            json_body={"name": name, "email": email, "password": password},
        )
        self.token = data["access_token"]
        self.current_user = data["user"]
        await self.storage.set(STORAGE_TOKEN_KEY, self.token)
        return self.current_user

    async def login(self, email: str, password: str) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/api/auth/login",
            json_body={"email": email, "password": password},
        )
        self.token = data["access_token"]
        self.current_user = data["user"]
        await self.storage.set(STORAGE_TOKEN_KEY, self.token)
        return self.current_user

    async def get_me(self) -> dict[str, Any]:
        return await self._request("GET", "/api/auth/me")

    async def logout(self) -> None:
        self.token = None
        self.current_user = None
        await self.storage.remove(STORAGE_TOKEN_KEY)

    async def get_today_habits(self, target_date: str) -> list[dict[str, Any]]:
        return await self._request(
            "GET", "/api/habits/today", params={"target_date": target_date}
        )

    async def list_habits(self, include_archived: bool = False) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            "/api/habits",
            params={"include_archived": str(include_archived).lower()},
        )

    async def create_habit(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/api/habits", json_body=payload)

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
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"date": target_date, "action": action}
        if count is not None:
            body["count"] = count
        return await self._request(
            "POST", f"/api/habits/{habit_id}/checkin", json_body=body
        )

    async def get_stats_summary(self, today: str) -> dict[str, Any]:
        return await self._request(
            "GET", "/api/stats/summary", params={"today": today}
        )


def open_dialog(page: ft.Page, dialog: ft.AlertDialog) -> None:
    if hasattr(page, "show_dialog"):
        page.show_dialog(dialog)
    elif hasattr(page, "open"):
        page.open(dialog)


def close_dialog(page: ft.Page, dialog: ft.AlertDialog) -> None:
    if hasattr(page, "pop_dialog"):
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
