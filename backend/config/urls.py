from django.contrib import admin
from django.urls import include, path

from .auth_views import csrf_token, session_login, session_logout, session_status

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/csrf/", csrf_token, name="auth-csrf"),
    path("api/v1/auth/session/", session_status, name="auth-session"),
    path("api/v1/auth/login/", session_login, name="auth-login"),
    path("api/v1/auth/logout/", session_logout, name="auth-logout"),
    path("api/v1/videos/", include("videos.urls")),
]
