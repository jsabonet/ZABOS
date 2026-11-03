import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST


@ensure_csrf_cookie
@require_GET
def csrf_token(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_GET
def session_status(request):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False})
    return JsonResponse(
        {"authenticated": True, "username": request.user.get_username()}
    )


@require_POST
def session_login(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"detail": "O pedido de autenticação é inválido."}, status=400
        )

    username = data.get("username") if isinstance(data, dict) else None
    password = data.get("password") if isinstance(data, dict) else None
    if not isinstance(username, str) or not isinstance(password, str):
        return JsonResponse(
            {"detail": "Indica o nome de utilizador e a palavra-passe."}, status=400
        )

    user = authenticate(request, username=username.strip(), password=password)
    if user is None:
        return JsonResponse({"detail": "Usuário ou senha inválido."}, status=401)

    login(request, user)
    return JsonResponse({"authenticated": True, "username": user.get_username()})


@require_POST
def session_logout(request):
    logout(request)
    return JsonResponse({"authenticated": False})
