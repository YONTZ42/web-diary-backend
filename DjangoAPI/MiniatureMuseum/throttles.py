from rest_framework.throttling import SimpleRateThrottle

class BaseUserOrGuestThrottle(SimpleRateThrottle):
    scope = "burst_user_or_guest"

    def get_cache_key(self, request, view):
        if getattr(request, "user", None) and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            guest_id = request.headers.get("X-Guest-Id")
            if guest_id:
                ident = f"guest:{guest_id}"
            else:
                ident = f"ip:{self.get_ident(request)}"
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }

class BurstUserOrGuestThrottle(BaseUserOrGuestThrottle):
    scope = "burst_user_or_guest"

class SustainedUserOrGuestThrottle(BaseUserOrGuestThrottle):
    scope = "sustained_user_or_guest"

class GuestIssueThrottle(BaseUserOrGuestThrottle):
    scope = "guest_issue"

class LoginThrottle(BaseUserOrGuestThrottle):
    scope = "login"

class UploadThrottle(BaseUserOrGuestThrottle):
    scope = "upload"

class RembgBurstThrottle(BaseUserOrGuestThrottle):
    scope = "rembg_burst"

class RembgSustainedThrottle(BaseUserOrGuestThrottle):
    scope = "rembg_sustained"