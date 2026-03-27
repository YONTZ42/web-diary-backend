# middleware.py
import sentry_sdk

class SentryContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        sentry_sdk.set_tag("path", request.path)
        sentry_sdk.set_tag("method", request.method)

        request_id = request.headers.get("X-Request-Id")
        if request_id:
            sentry_sdk.set_tag("request_id", request_id)

        guest_id = request.headers.get("X-Guest-Id")
        if guest_id:
            sentry_sdk.set_tag("guest_id", guest_id)

        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            sentry_sdk.set_user({"id": str(user.id)})

        return self.get_response(request)