import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from api_client import ApiError  # noqa: E402
from main import HabitTrackerApp  # noqa: E402


def _make_mock_page() -> SimpleNamespace:
    controls: list[Any] = []
    page = SimpleNamespace(
        controls=controls,
        navigation_bar=None,
        width=900,
        update=MagicMock(),
        show_dialog=MagicMock(),
        open=MagicMock(),
        pop_dialog=MagicMock(),
        close=MagicMock(),
    )
    page.add = lambda *items: controls.extend(items)
    return page


def _collect_controls(root: object, target_type: type) -> list:
    found: list = []
    if isinstance(root, target_type):
        found.append(root)
    content = getattr(root, "content", None)
    if content is not None:
        found.extend(_collect_controls(content, target_type))
    children = getattr(root, "controls", None)
    if children:
        for child in children:
            found.extend(_collect_controls(child, target_type))
    return found


def _extract_auth_widgets(page: SimpleNamespace) -> tuple[dict[str, ft.TextField], ft.FilledButton]:
    fields: dict[str, ft.TextField] = {}
    buttons: list[ft.FilledButton] = []
    for ctrl in page.controls:
        for tf in _collect_controls(ctrl, ft.TextField):
            if tf.label:
                fields[str(tf.label)] = tf
        buttons.extend(_collect_controls(ctrl, ft.FilledButton))
    assert len(buttons) == 1, f"Expected 1 submit button, got {len(buttons)}"
    return fields, buttons[0]


class AuthEnterSubmitTests(unittest.IsolatedAsyncioTestCase):
    def _build_app(self) -> tuple[HabitTrackerApp, SimpleNamespace]:
        page = _make_mock_page()
        app = HabitTrackerApp(page)
        app.api.set_base_url = AsyncMock()
        app.api.login = AsyncMock(
            side_effect=lambda email, password: setattr(
                app.api, "current_user", {"name": "Test User", "email": email}
            )
            or app.api.current_user
        )
        app.api.register = AsyncMock(
            side_effect=lambda name, email, password: {
                "message": "A 6-digit verification code has been sent to your email.",
                "email": email,
                "verification_required": True,
                "expires_in_minutes": 15,
                "dev_verification_code": "654321",
            }
        )
        app.api.verify_email = AsyncMock(
            side_effect=lambda email, code: setattr(
                app.api,
                "current_user",
                {"name": "Test User", "email": email, "email_verified": True},
            )
            or app.api.current_user
        )
        app.api.resend_verification = AsyncMock(
            side_effect=lambda email: {
                "message": "A new 6-digit verification code has been sent to your email.",
                "email": email,
                "verification_required": True,
                "expires_in_minutes": 15,
                "dev_verification_code": "999888",
            }
        )
        app.api.forgot_password = AsyncMock(
            return_value={"message": "Code sent", "dev_reset_code": "123456"}
        )
        app.api.reset_password = AsyncMock(
            side_effect=lambda email, code, new_password: setattr(
                app.api, "current_user", {"name": "Test User", "email": email}
            )
            or app.api.current_user
        )
        app.api.get_today_habits = AsyncMock(return_value=[])
        return app, page

    async def test_password_enter_submits_login(self) -> None:
        app, page = self._build_app()
        app.render_auth_screen()
        fields, _submit_btn = _extract_auth_widgets(page)

        self.assertTrue(fields["Email"].autofocus)
        self.assertFalse(fields["Your Name"].autofocus)

        fields["Email"].value = "user@example.com"
        fields["Password"].value = "secret123"

        await fields["Password"].on_submit(None)

        app.api.login.assert_awaited_once_with(
            email="user@example.com", password="secret123"
        )
        app.api.get_today_habits.assert_awaited_once()
        self.assertIsNotNone(app.api.current_user)

    async def test_password_enter_submits_register(self) -> None:
        app, page = self._build_app()
        app.render_auth_screen(is_register=True)
        fields, _submit_btn = _extract_auth_widgets(page)

        self.assertTrue(fields["Your Name"].autofocus)
        self.assertFalse(fields["Email"].autofocus)

        fields["Your Name"].value = "Shawn"
        fields["Email"].value = "shawn@example.com"
        fields["Password"].value = "secret123"

        await fields["Password"].on_submit(None)

        app.api.register.assert_awaited_once_with(
            name="Shawn", email="shawn@example.com", password="secret123"
        )
        app.api.get_today_habits.assert_not_awaited()
        self.assertIsNone(app.api.current_user)

        verify_fields, _verify_btn = _extract_auth_widgets(page)
        self.assertEqual(verify_fields["Email"].value, "shawn@example.com")
        self.assertTrue(verify_fields["6-Digit Verification Code"].visible)
        self.assertTrue(verify_fields["6-Digit Verification Code"].autofocus)

        verify_fields["6-Digit Verification Code"].value = "654321"
        await verify_fields["6-Digit Verification Code"].on_submit(None)

        app.api.verify_email.assert_awaited_once_with(
            email="shawn@example.com", code="654321"
        )
        app.api.get_today_habits.assert_awaited_once()
        self.assertIsNotNone(app.api.current_user)

    async def test_unverified_login_403_transitions_to_verify_email_and_resend(self) -> None:
        app, page = self._build_app()
        app.api.login = AsyncMock(
            side_effect=ApiError(
                "Please verify your email address with the 6-digit code before signing in",
                status_code=403,
            )
        )
        app.render_auth_screen()
        fields, _submit_btn = _extract_auth_widgets(page)

        fields["Email"].value = "pending@example.com"
        fields["Password"].value = "secret123"
        await fields["Password"].on_submit(None)

        verify_fields, _verify_btn = _extract_auth_widgets(page)
        self.assertEqual(verify_fields["Email"].value, "pending@example.com")
        self.assertTrue(verify_fields["6-Digit Verification Code"].visible)

        text_buttons = _collect_controls(page.controls[0], ft.TextButton)
        resend_btn = next(
            btn
            for btn in text_buttons
            if isinstance(btn.content, ft.Text)
            and btn.content.value == "Resend Verification Code"
        )
        await resend_btn.on_click(None)
        app.api.resend_verification.assert_awaited_once_with(
            email="pending@example.com"
        )

        verify_fields["6-Digit Verification Code"].value = "999888"
        await verify_fields["6-Digit Verification Code"].on_submit(None)

        app.api.verify_email.assert_awaited_once_with(
            email="pending@example.com", code="999888"
        )
        app.api.get_today_habits.assert_awaited_once()

    async def test_email_enter_focuses_empty_password_or_submits_when_filled(self) -> None:
        app, page = self._build_app()
        app.render_auth_screen()
        fields, _submit_btn = _extract_auth_widgets(page)

        fields["Email"].value = "user@example.com"
        fields["Password"].value = ""

        with patch.object(
            fields["Password"], "focus", new_callable=AsyncMock
        ) as mock_focus:
            await fields["Email"].on_submit(None)
            mock_focus.assert_awaited_once()

        app.api.login.assert_not_awaited()

        fields["Password"].value = "secret123"
        await fields["Email"].on_submit(None)

        app.api.login.assert_awaited_once_with(
            email="user@example.com", password="secret123"
        )

    async def test_forgot_password_enter_sends_code_and_resets_password(self) -> None:
        app, page = self._build_app()
        app.render_auth_screen(auth_mode="forgot")
        fields, _submit_btn = _extract_auth_widgets(page)

        self.assertTrue(fields["Email"].autofocus)
        fields["Email"].value = "user@example.com"

        await fields["Email"].on_submit(None)

        app.api.forgot_password.assert_awaited_once_with(email="user@example.com")
        self.assertTrue(fields["6-Digit Verification Code"].visible)
        self.assertTrue(fields["New Password (min 6 chars)"].visible)
        self.assertTrue(fields["Confirm New Password"].visible)

        fields["6-Digit Verification Code"].value = "123456"
        fields["New Password (min 6 chars)"].value = "newpass123"
        fields["Confirm New Password"].value = "newpass123"

        await fields["Confirm New Password"].on_submit(None)

        app.api.reset_password.assert_awaited_once_with(
            email="user@example.com",
            code="123456",
            new_password="newpass123",
        )
        app.api.get_today_habits.assert_awaited_once()

    async def test_double_enter_ignored_while_submitting(self) -> None:
        app, page = self._build_app()
        app.render_auth_screen()
        fields, submit_btn = _extract_auth_widgets(page)

        fields["Email"].value = "user@example.com"
        fields["Password"].value = "secret123"
        submit_btn.disabled = True

        await fields["Password"].on_submit(None)

        app.api.login.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
