import time
import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

from .logging_utils import (
    bind_request_context,
    clear_request_context,
    get_logger,
)

ACCESS_LOGGER = get_logger("django.access")
AUTH_LOGGER = get_logger("django.auth")


class RequestContextMiddleware:
    """
    - X-Request-Id を採用。無ければ生成
    - request_id / guest_id / user_id / path / method を structlog contextvars に bind
    - response header に X-Request-Id を返す
    - django.access ログを出す
    """

    def __init__(self, get_response: Callable):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started_at = time.perf_counter()

        request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex}"
        guest_id = request.headers.get("X-Guest-Id")

        user_id = None
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            user_id = str(user.id)

        request.request_id = request_id
        request.guest_id = guest_id
        request.user_id = user_id

        bind_request_context(
            request_id=request_id,
            guest_id=guest_id,
            user_id=user_id,
            path=request.path,
            method=request.method,
        )

        ACCESS_LOGGER.info(
            "request started",
            component="django.access",
        )

        if not user_id and not guest_id:
            AUTH_LOGGER.warning(
                "request has neither authenticated user nor X-Guest-Id",
                component="django.auth",
                status_code=None,
            )

        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            ACCESS_LOGGER.exception(
                "request failed with unhandled exception",
                component="django.access",
                duration_ms=duration_ms,
                status_code=500,
            )
            clear_request_context()
            raise

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        response["X-Request-Id"] = request_id

        ACCESS_LOGGER.info(
            "request finished",
            component="django.access",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        clear_request_context()
        return response