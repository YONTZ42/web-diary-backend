from rest_framework import viewsets, views, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from django.conf import settings
from .models import Schedule, User, Sticker, Page, Notebook, NotebookPage,UploadSession
from .serializers import (
    ScheduleSerializer, UserRegistrationSerializer, UserSerializer, StickerSerializer, PageSerializer, NotebookSerializer,
    UploadIssueSerializer, UploadConfirmSerializer
)
from drf_spectacular.utils import extend_schema

from django.utils import timezone
import boto3
import uuid
import os

# --- 1. User API ---
class MeView(generics.RetrieveUpdateAPIView):
    """自分のプロフィール取得・更新"""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

# --- Auth API ---
class UserRegistrationView(generics.CreateAPIView):
    """ユーザー新規登録"""
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny] # 誰でもアクセス可能


# --- 2. Upload API (S3 Presigned URL) ---
class UploadView(views.APIView):
    permission_classes = [IsAuthenticated]
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
        serializer = UploadIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # S3キーの生成: users/{user_id}/{purpose}/{uuid}.ext
        ext = os.path.splitext(data['filename'])[1]
        key = f"users/{request.user.id}/{data['purpose']}/{uuid.uuid4()}{ext}"

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
        session = UploadSession.objects.create(
            user=request.user,
            purpose=data['purpose'],
            s3_key=key,
            mime=data['mime_type'],
            expires_at=timezone.now() + timezone.timedelta(hours=1)
        )

        return Response({
            'uploadUrl': url,
            's3Key': key,
            'uploadSessionId': session.id
        })

    def confirm_upload(self, request):
        serializer = UploadConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session_id = serializer.validated_data['upload_session_id']

        try:
            session = UploadSession.objects.get(id=session_id, user=request.user)
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


# --- 3. Sticker API ---
class StickerViewSet(viewsets.ModelViewSet):
    queryset = Sticker.objects.all()
    serializer_class = StickerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 自分のステッカーのみ
        return Sticker.objects.filter(owner=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

# --- 4. Page API ---
class PageViewSet(viewsets.ModelViewSet):
    queryset = Page.objects.all()
    serializer_class = PageSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # 1. 基本のクエリセット（自分のページ）
        if self.request.user.is_authenticated:
            queryset = Page.objects.filter(owner=self.request.user)
        else:
            # デモ用（全件）
            queryset = Page.objects.all()
        
        # 2. クエリパラメータによるフィルタリング
        # ?year=2024
        year = self.request.query_params.get('year')
        if year:
            queryset = queryset.filter(date__year=year)
        # ?month=2 (yearと併用推奨だが、単独でも動作可能)
        month = self.request.query_params.get('month')
        if month:
            queryset = queryset.filter(date__month=month)
        # ?day=15
        day = self.request.query_params.get('day')
        if day:
            queryset = queryset.filter(date__day=day)

        print("Filtered queryset count:",queryset)
        # 日付順にソートして返す
        return queryset.order_by('-date')

    def perform_create(self, serializer):

        page = serializer.save(owner=self.request.user)
        
        # もし notebook_id が送られてきたら紐付ける
        notebook_id = self.request.data.get('notebook_id')
        if notebook_id:
            try:
                # Notebookを取得
                notebook = Notebook.objects.get(id=notebook_id)
                
                # 中間テーブルに登録 (末尾に追加)
                last_position = NotebookPage.objects.filter(notebook=notebook).count()
                NotebookPage.objects.create(
                    notebook=notebook,
                    page=page,
                    position=last_position
                )
                print(f"Page {page.id} added to Notebook {notebook.id}")
            except Notebook.DoesNotExist:
                print(f"Notebook {notebook_id} not found.")
            except Exception as e:
                print(f"Error linking page to notebook: {e}")


# --- Schedule API ---

class ScheduleViewSet(viewsets.ModelViewSet):
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer
    permission_classes = [IsAuthenticated] # または AllowAny

    def get_queryset(self):
        user = self.request.user if self.request.user.is_authenticated else User.objects.first()
        qs = Schedule.objects.filter(owner=user)

        # フィルタリング
        type_param = self.request.query_params.get('type')
        if type_param:
            qs = qs.filter(type=type_param)
            
        start_date = self.request.query_params.get('start_date')
        if start_date:
            qs = qs.filter(start_date=start_date)

        return qs.order_by('-start_date')

    def perform_create(self, serializer):
        # ユーザー紐付け
        user = self.request.user if self.request.user.is_authenticated else User.objects.first()
        serializer.save(owner=user)


# --- 5. Notebook API ---
class NotebookViewSet(viewsets.ModelViewSet):
    queryset = Notebook.objects.all()
    serializer_class = NotebookSerializer
    #permission_classes = [IsAuthenticated]
    permission_classes = [AllowAny] # ★一時的に全員許可
    def get_queryset(self):
        return Notebook.objects.filter(owner=self.request.user).order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # ★追加: Notebook内のPage一覧を取得するアクション
    # GET /api/notebooks/{id}/pages/
    @action(detail=True, methods=['get'])
    def pages(self, request, pk=None):
        notebook = self.get_object() # 存在確認と権限チェック込み
        
        # NotebookPageを通してPageを取得し、Pageの日付でソート
        # select_related でクエリを最適化
        pages = Page.objects.filter(
            notebookpage__notebook=notebook
        ).order_by('date')  # 日付の新しい順
        
        # PageSerializerを使ってシリアライズ
        serializer = PageSerializer(pages, many=True)
        return Response(serializer.data)
