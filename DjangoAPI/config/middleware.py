from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class ExcludeHealthcheckFromSSLRedirectMiddleware:
    """
    SECURE_SSL_REDIRECT=True でも /healthz と /health はリダイレクトしない。
    """

    EXCLUDED_PATHS = {"/healthz", "/health"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            settings.SECURE_SSL_REDIRECT
            and request.path not in self.EXCLUDED_PATHS
            and request.META.get("HTTP_X_FORWARDED_PROTO") != "https"
        ):
            host = request.get_host()
            return HttpResponsePermanentRedirect(f"https://{host}{request.get_full_path()}")

        return self.get_response(request)