from rest_framework import viewsets, views, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

from rest_framework.decorators import action
from django.conf import settings
from .models import UploadSession
from .serializers import (
    UploadIssueSerializer, UploadConfirmSerializer, GuestIssueResponseSerializer,
)
from drf_spectacular.utils import extend_schema, extend_schema_view

from django.utils import timezone
import boto3
import uuid
import os

# --- 2. Upload API (S3 Presigned URL) ---
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
            raise PermissionDenied("X-Guest-id required")
        return ("guest", guest_id)
    
    @extend_schema(
        request=UploadIssueSerializer,
        responses={200: UploadConfirmSerializer},
        description="S3アップロード用のURL発行または完了確認を行います。"
    )
    def post(self, request, action=None, **kwargs):
        """
        POST /api/uploads/issue/   -> URL発行
        POST /api/uploads/confirm/ -> 完了確認
        """
        if action == 'issue':
            return self.issue_upload(request)
        elif action == 'confirm':
            return self.confirm_upload(request)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def issue_upload(self, request):
        uploader_kind, uploader = self._get_uploader(request)

        serializer = UploadIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["purpose"] not in self.ALLOWED_PURPOSES:
            raise PermissionDenied("invalid purpose")

        # S3キーの生成: users/{user_id}/{purpose}/{uuid}.ext
        ext = os.path.splitext(data['filename'])[1]
        if uploader_kind == "user":
            key = f"users/{uploader.id}/{data['purpose']}/{uuid.uuid4()}{ext}"
        else:
            # guestは guest_id で名前空間を分ける
            key = f"guests/{uploader}/{data['purpose']}/{uuid.uuid4()}{ext}"


        # Presigned URL生成
        s3 = boto3.client('s3', 
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 
                'Key': key, 'ContentType': data['mime_type'],
            },
            ExpiresIn=3600
        )

        # セッション保存
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


        return Response({
            'uploadUrl': url,
            's3Key': key,
            'uploadSessionId': session.id
        })

    def confirm_upload(self, request):
        uploader_kind, uploader = self._get_uploader(request)

        serializer = UploadConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session_id = serializer.validated_data['upload_session_id']

        try:
            if uploader_kind == "user":
                session = UploadSession.objects.get(id=session_id, user=uploader)
            else:
                session = UploadSession.objects.get(id=session_id, guest_id=uploader)
        except UploadSession.DoesNotExist:
            return Response({'error': 'Session not found'}, status=404)

        # S3上の存在確認（Head Object）
        s3 = boto3.client('s3', 
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        try:
            s3.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=session.s3_key)
        except:
            return Response({'error': 'File not found in S3'}, status=400)

        session.status = 'confirmed'
        session.save()
        return Response({'status': 'confirmed'})

