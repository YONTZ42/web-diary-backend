from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import PermissionDenied
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

from django.conf import settings
from django.utils import timezone

from .models import UploadSession
from .serializers import (
    UploadIssueSerializer,
    UploadConfirmSerializer,
)

import boto3
import uuid
import os
from urllib.parse import quote
from botocore.config import Config


class UploadView(views.APIView):
    permission_classes = [AllowAny]
    throttle_classes = [UserRateThrottle, AnonRateThrottle]

    ALLOWED_PURPOSES = {"sticker_png", "page_asset", "exhibit_image"}

    def _get_uploader(self, request):
        """
        returns: ("user", user) or ("guest", guest_id)
        """
        if request.user and request.user.is_authenticated:
            return ("user", request.user)

        guest_id = request.headers.get("X-Guest-Id")
        if not guest_id:
            raise PermissionDenied("X-Guest-Id required")
        return ("guest", guest_id)

    def _build_public_url(self, s3_key: str) -> str:
        """
        CloudFront 経由の完全URLを返す。
        CLOUDFRONT_DOMAIN は
        - dxxxxxxxx.cloudfront.net
        - https://cdn.example.com
        のどちらでも受けられるようにする。
        """
        raw_domain = getattr(settings, "CLOUDFRONT_DOMAIN", "") or os.environ.get("CLOUDFRONT_DOMAIN", "")
        if not raw_domain:
            raise RuntimeError("CLOUDFRONT_DOMAIN is not configured")

        domain = raw_domain.strip().rstrip("/")
        if not domain.startswith("http://") and not domain.startswith("https://"):
            domain = f"https://{domain}"

        encoded_key = quote(s3_key, safe="/")
        return f"{domain}/{encoded_key}"

    def _get_s3_client(self):
        return boto3.client(
            "s3",
            config=Config(signature_version="s3v4"),
            region_name=settings.AWS_S3_REGION_NAME,
        )

    def post(self, request, action=None, **kwargs):
        """
        POST /api/uploads/issue/   -> URL発行
        POST /api/uploads/confirm/ -> 完了確認
        """
        if action == "issue":
            return self.issue_upload(request)
        elif action == "confirm":
            return self.confirm_upload(request)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def issue_upload(self, request):
        uploader_kind, uploader = self._get_uploader(request)

        serializer = UploadIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["purpose"] not in self.ALLOWED_PURPOSES:
            raise PermissionDenied("invalid purpose")

        ext = os.path.splitext(data["filename"])[1]
        if uploader_kind == "user":
            key = f"users/{uploader.id}/{data['purpose']}/{uuid.uuid4()}{ext}"
        else:
            key = f"guests/{uploader}/{data['purpose']}/{uuid.uuid4()}{ext}"

        s3 = self._get_s3_client()
        presigned_upload_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": key,
                "ContentType": data["mime_type"],
            },
            ExpiresIn=3600,
        )

        session_kwargs = dict(
            purpose=data["purpose"],
            s3_key=key,
            mime=data["mime_type"],
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        if uploader_kind == "user":
            session_kwargs["user"] = uploader
        else:
            session_kwargs["guest_id"] = uploader

        session = UploadSession.objects.create(**session_kwargs)

        # ここで返す uploadUrl は「アップロード専用」
        return Response(
            {
                "uploadUrl": presigned_upload_url,
                "s3Key": key,
                "uploadSessionId": str(session.id),
            }
        )

    def confirm_upload(self, request):
        uploader_kind, uploader = self._get_uploader(request)

        serializer = UploadConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session_id = serializer.validated_data["upload_session_id"]

        try:
            if uploader_kind == "user":
                session = UploadSession.objects.get(id=session_id, user=uploader)
            else:
                session = UploadSession.objects.get(id=session_id, guest_id=uploader)
        except UploadSession.DoesNotExist:
            return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)

        s3 = self._get_s3_client()
        try:
            s3.head_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=session.s3_key,
            )
        except Exception:
            return Response({"error": "File not found in S3"}, status=status.HTTP_400_BAD_REQUEST)

        session.status = "confirmed"
        session.save(update_fields=["status", "updated_at"])

        public_url = self._build_public_url(session.s3_key)

        # ここで返す uploadUrl は「表示・保存に使う完全URL」
        return Response(
            {
                "status": "confirmed",
                "uploadSessionId": str(session.id),
                "s3Key": session.s3_key,
                "uploadUrl": public_url,
            }
        )