from rest_framework import viewsets, views, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

from rest_framework.decorators import action
from django.conf import settings
from .models import Schedule, User, Sticker, Page, Notebook, NotebookPage,UploadSession
from .serializers import (
    ScheduleSerializer, StickerSerializer, PageSerializer, NotebookSerializer,
)
from drf_spectacular.utils import extend_schema, extend_schema_view

from django.utils import timezone

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
    
    def perform_destroy(self, instance):
        # 物理削除ではなく、論理削除を行う
        instance.deleted_at = timezone.now()
        instance.save()

    def get_queryset(self):
        # 1. 基本のクエリセット（自分のページ）
        if self.request.user.is_authenticated:
            queryset = Page.objects.filter(owner=self.request.user)
        else:
            # デモ用（全件）
            queryset = Page.objects.all()
        
        queryset = queryset.filter(deleted_at__isnull=True)

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
    permission_classes = [IsAuthenticated]
    #permission_classes = [AllowAny] # ★一時的に全員許可
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
            notebookpage__notebook=notebook,
            deleted_at__isnull=True  # ★追加: 論理削除されたページを除外
        ).order_by('date')  # 日付の新しい順
        
        # PageSerializerを使ってシリアライズ
        serializer = PageSerializer(pages, many=True)
        return Response(serializer.data)
