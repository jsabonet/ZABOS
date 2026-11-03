import logging
from uuid import uuid4

from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("config.api")


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None or response.status_code >= 500:
        request = context.get("request")
        view = context.get("view")
        request_id = uuid4().hex
        user = getattr(request, "user", None)
        user_id = getattr(user, "pk", None)
        logger.error(
            "api_unhandled_exception request_id=%s method=%s path=%s "
            "user_id=%s view=%s exception_type=%s",
            request_id,
            getattr(request, "method", "unknown"),
            getattr(request, "path", "unknown"),
            user_id,
            type(view).__name__ if view else "unknown",
            type(exc).__name__,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return Response(
            {
                "detail": "Ocorreu um erro interno ao processar o pedido.",
                "request_id": request_id,
            },
            status=500,
        )
    return response
