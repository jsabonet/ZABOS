from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from types import SimpleNamespace

from rest_framework.exceptions import APIException

from config.exceptions import api_exception_handler


class SessionAuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="session-user",
            password="secure-test-password",
        )
        self.client = Client(enforce_csrf_checks=True)

    def csrf_token(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return response.json()["csrfToken"]

    def test_login_session_survives_a_new_request_and_can_be_logged_out(self):
        csrf = self.csrf_token()
        login_response = self.client.post(
            "/api/v1/auth/login/",
            data='{"username":"session-user","password":"secure-test-password"}',
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_ORIGIN="http://localhost:3000",
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.json()["authenticated"])
        self.assertTrue(self.client.session.get("_auth_user_id"))

        restored_client = Client()
        restored_client.cookies["sessionid"] = self.client.cookies["sessionid"].value
        session_response = restored_client.get("/api/v1/auth/session/")
        self.assertEqual(session_response.json()["username"], self.user.username)
        self.assertEqual(
            self.client.cookies["sessionid"]["httponly"],
            True,
        )

        csrf_after_login = self.csrf_token()
        logout_response = self.client.post(
            "/api/v1/auth/logout/",
            data="{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_after_login,
            HTTP_ORIGIN="http://localhost:3000",
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_login_requires_a_csrf_token(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            data='{"username":"session-user","password":"secure-test-password"}',
            content_type="application/json",
            HTTP_ORIGIN="http://localhost:3000",
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_credentials_do_not_create_a_session(self):
        csrf = self.csrf_token()
        response = self.client.post(
            "/api/v1/auth/login/",
            data='{"username":"session-user","password":"wrong-password"}',
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_ORIGIN="http://localhost:3000",
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(self.client.session.get("_auth_user_id"))


class APIExceptionLoggingTests(TestCase):
    def test_internal_exception_is_logged_and_returns_safe_request_id(self):
        request = SimpleNamespace(
            method="POST",
            path="/api/v1/videos/example/render/",
            user=SimpleNamespace(pk=7),
        )
        try:
            raise RuntimeError("private diagnostic detail")
        except RuntimeError as exc:
            with self.assertLogs("config.api", level="ERROR") as captured:
                response = api_exception_handler(
                    exc,
                    {"request": request, "view": SimpleNamespace()},
                )

        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.data["request_id"])
        self.assertNotIn("private diagnostic detail", response.data["detail"])
        self.assertIn("Traceback", "\n".join(captured.output))
        self.assertIn(response.data["request_id"], "\n".join(captured.output))

    def test_server_error_api_exception_is_logged(self):
        request = SimpleNamespace(
            method="POST",
            path="/api/v1/videos/example/render/",
            user=SimpleNamespace(pk=7),
        )
        exc = APIException("internal detail")
        exc.status_code = 500
        try:
            raise exc
        except APIException as caught:
            with self.assertLogs("config.api", level="ERROR") as captured:
                response = api_exception_handler(
                    caught,
                    {"request": request, "view": SimpleNamespace()},
                )

        self.assertEqual(response.status_code, 500)
        self.assertIn(response.data["request_id"], "\n".join(captured.output))
