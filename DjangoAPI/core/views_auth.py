from rest_framework import viewsets, views, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

from rest_framework.decorators import action
from django.conf import settings
from .serializers import (
    UserRegistrationSerializer, UserSerializer,
    GuestIssueResponseSerializer,
    GoogleLoginRequestSerializer, TokenPairSerializer
)
from drf_spectacular.utils import extend_schema, extend_schema_view

from django.utils import timezone
import boto3
import uuid
import os

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

# --- 1. User API ---
class MeView(generics.RetrieveUpdateAPIView):
    """自分のプロフィール取得・更新"""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


from MiniatureMuseum.throttles import GuestIssueThrottle, RembgBurstThrottle, RembgSustainedThrottle

# --- Auth API ---
class UserRegistrationView(generics.CreateAPIView):
    """ユーザー新規登録"""
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny] # 誰でもアクセス可能
    throttle_classes = [GuestIssueThrottle]
# --- Auth API ---
# --- Gallery Viewer (public read by slug) ---
# --- Auth: Guest ID Issue ---

class GuestIssueView(views.APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={200: GuestIssueResponseSerializer},
        operation_id="auth_guest_create",
        tags=["Auth"],
    )
    def post(self, request, *args, **kwargs):
        guest_id = uuid.uuid4().hex
        ser = GuestIssueResponseSerializer(data={"guest_id": guest_id})
        ser.is_valid(raise_exception=True)
        return Response(ser.data, status=status.HTTP_200_OK)


class GoogleLoginView(views.APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    @extend_schema(
        request=GoogleLoginRequestSerializer,
        responses={200: TokenPairSerializer},
        operation_id="auth_google_login",
        tags=["Auth"],
    )
    def post(self, request, *args, **kwargs):
        serializer = GoogleLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        print(f"Validated data: {serializer.validated_data}")
        print("Google client id", settings.GOOGLE_OAUTH_CLIENT_ID)
        raw_id_token = serializer.validated_data["id_token"]

        try:
            token_info = google_id_token.verify_oauth2_token(
                raw_id_token,
                google_requests.Request(),
                settings.GOOGLE_OAUTH_CLIENT_ID,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {"detail": "Invalid Google token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        issuer = token_info.get("iss")
        if issuer not in ["accounts.google.com", "https://accounts.google.com"]:
            return Response(
                {"detail": "Invalid token issuer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = token_info.get("email")
        email_verified = token_info.get("email_verified", False)
        display_name = token_info.get("name") or ""
        picture = token_info.get("picture") or None

        if not email:
            return Response(
                {"detail": "Google account email not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not email_verified:
            return Response(
                {"detail": "Google account email is not verified"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        UserModel = get_user_model()
        user, created = UserModel.objects.get_or_create(
            email=email,
            defaults={
                "display_name": display_name[:100],
            },
        )

        updated = False

        if (not user.display_name) and display_name:
            user.display_name = display_name[:100]
            updated = True

        if picture and not user.avatar:
            user.avatar = {
                "kind": "remote",
                "key": picture,
                "mime": "image/jpeg",
                "source": {"provider": "google"},
            }
            updated = True

        if created:
            # passwordログインさせないなら unusable password にしておく
            user.set_unusable_password()
            updated = True

        if updated:
            user.save()

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )