from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, views, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.decorators import action
from django.conf import settings
from django.db import models
from .models import Gallery, Exhibit
from .serializers import (
    GallerySerializer, ExhibitSerializer, ExhibitPublicSerializer,
    GalleryPublicSerializer,ExhibitUpsertSerializer)

from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.utils.text import slugify
import uuid


# --- Gallery Public Viewer (public read by slug) ---

# --- Nested Exhibit API (recommended) ---
# POST /api/galleries/{gallery_id}/exhibits/
# PUT  /api/galleries/{gallery_id}/exhibits/{slot_index}/
# DELETE /api/galleries/{gallery_id}/exhibits/{slot_index}/

class _GalleryActorMixin:
    """Galleryの所有者判定（user/guest）を共通化"""

    def _actor(self, request):
        # returns ('user', user_obj) | ('guest', guest_id) | (None, None)
        if request.user and request.user.is_authenticated:
            return ('user', request.user)
        guest_id = request.headers.get('X-Guest-Id')
        if guest_id:
            return ('guest', guest_id)
        return (None, None)

    def _get_owned_gallery_or_404(self, request, gallery_id):
        try:
            gallery = Gallery.objects.filter(id=gallery_id, deleted_at__isnull=True).get()
        except Gallery.DoesNotExist:
            raise PermissionDenied('Gallery not found.')

        mode, ident = self._actor(request)

        if gallery.user_style == 'user':
            if mode != 'user':
                raise NotAuthenticated('Login required.')
            if gallery.owner_id != ident.id:
                raise PermissionDenied('Not allowed.')
        elif gallery.user_style == 'guest':
            if mode != 'guest':
                raise NotAuthenticated('Guest authentication required.')
            if gallery.guest_id != ident:
                raise PermissionDenied('Not allowed.')
        else:
            raise PermissionDenied('Invalid gallery.user_style.')

        return gallery, (mode, ident)

class GuestGalleryView(views.APIView):
    """
    Guest 用: 1ゲスト=1ギャラリー を前提にした入口

    - GET   /api/guest/gallery/ : 自分の Gallery を返す（なければ404）
    - POST  /api/guest/gallery/ : 自分の Gallery を作成（すでにあれば既存を返す）
    - PATCH /api/guest/gallery/ : 自分の Gallery を更新（title/is_public/layoutなど）
    - DELETE /api/guest/gallery/ : 自分の Gallery を論理削除（削除後は再作成可）
    """
    permission_classes = [AllowAny]

    def _require_guest_id(self, request) -> str:
        guest_id = request.headers.get('X-Guest-Id')
        if not guest_id:
            raise NotAuthenticated('Guest authentication required (X-Guest-Id).')
        return guest_id

    def _get_gallery(self, guest_id: str):
        return Gallery.objects.filter(
            user_style='guest',
            guest_id=guest_id,
            deleted_at__isnull=True,
        ).first()

    def _generate_unique_slug(self) -> str:
        # 16桁ランダム（衝突時リトライ）
        for _ in range(10):
            s = uuid.uuid4().hex[:16]
            if not Gallery.objects.filter(slug=s).exists():
                return s
        # さすがに衝突し続けない想定だが保険
        return uuid.uuid4().hex

    @extend_schema(
        request=None,
        responses={
            200: GallerySerializer,
            401: OpenApiResponse(description="Not Authenticated"),
            404: OpenApiResponse(description="Not found"),
        },
    )
    def get(self, request, *args, **kwargs):
        guest_id = self._require_guest_id(request)
        gallery = self._get_gallery(guest_id)
        if not gallery:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(GallerySerializer(gallery, context={'request': request}).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=GallerySerializer,
        responses={
            200: GallerySerializer,  # 既存返却
            201: GallerySerializer,  # 新規作成
            400: OpenApiResponse(description="Bad Request"),
            401: OpenApiResponse(description="Not Authenticated"),
        },
    )
    def post(self, request, *args, **kwargs):
        guest_id = self._require_guest_id(request)

        existing = self._get_gallery(guest_id)
        if existing:
            # すでにあれば既存を返す（UX優先）
            return Response(GallerySerializer(existing, context={'request': request}).data, status=status.HTTP_200_OK)

        # 作成（user_style/guest_id は固定）
        serializer = GallerySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        # slug は任意。未指定なら生成（Serializer.create も生成するが、ここでは衝突回避まで面倒を見る）
        slug = serializer.validated_data.get('slug') or self._generate_unique_slug()

        gallery = serializer.save(
            user_style='guest',
            owner=None,
            guest_id=guest_id,
            slug=slug,
        )
        return Response(GallerySerializer(gallery, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=GallerySerializer,
        responses={
            200: GallerySerializer,
            400: OpenApiResponse(description="Bad Request"),
            401: OpenApiResponse(description="Not Authenticated"),
            404: OpenApiResponse(description="Not found"),
        },
    )
    def patch(self, request, *args, **kwargs):
        guest_id = self._require_guest_id(request)
        gallery = self._get_gallery(guest_id)
        if not gallery:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Guest 側で更新を許可するフィールドを限定（安全）
        # ※ slug / user_style / owner / guest_id は変更不可
        allowed = {'title', 'layout_cols', 'layout_rows', 'is_public', 'cover_render_url'}
        data = {k: v for k, v in request.data.items() if k in allowed}

        serializer = GallerySerializer(gallery, data=data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(user_style='guest', owner=None, guest_id=guest_id)
        return Response(GallerySerializer(obj, context={'request': request}).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=None,
        responses={
            204: OpenApiResponse(description="Deleted"),
            401: OpenApiResponse(description="Not Authenticated"),
            404: OpenApiResponse(description="Not found"),
        },
    )
    def delete(self, request, *args, **kwargs):
        guest_id = self._require_guest_id(request)
        gallery = self._get_gallery(guest_id)
        if not gallery:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        gallery.delete()  # 論理削除
        return Response(status=status.HTTP_204_NO_CONTENT)




@extend_schema(
request=ExhibitSerializer,
responses={
    201: ExhibitSerializer,
    400: OpenApiResponse(description="Bad Request"),
    401: OpenApiResponse(description="Not Authenticated"),
    403: OpenApiResponse(description="Forbidden"),
    409: OpenApiResponse(description="Slot already occupied"),
    },
)
class GalleryExhibitCreateView(_GalleryActorMixin, views.APIView):
    """ネスト型: Exhibit追加（空枠に追加）"""
    permission_classes = [AllowAny]


    def post(self, request, gallery_id, *args, **kwargs):
        gallery, (mode, ident) = self._get_owned_gallery_or_404(request, gallery_id)

        serializer = ExhibitSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        slot_index = serializer.validated_data.get('slot_index')
        if slot_index is None:
            return Response({'detail': 'slot_index is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # 既に埋まってたら 409（POSTは追加専用）
        if Exhibit.objects.filter(gallery=gallery, slot_index=slot_index, deleted_at__isnull=True).exists():
            return Response({'detail': 'Slot already occupied.'}, status=status.HTTP_409_CONFLICT)

        save_kwargs = {'gallery': gallery}
        if gallery.user_style == 'user':
            save_kwargs.update({'user_style': 'user', 'owner': ident, 'guest_id': None})
        else:
            save_kwargs.update({'user_style': 'guest', 'guest_id': ident, 'owner': None})

        exhibit = serializer.save(**save_kwargs)
        return Response(ExhibitSerializer(exhibit, context={'request': request}).data, status=status.HTTP_201_CREATED)


class GalleryExhibitSlotUpsertView(_GalleryActorMixin, views.APIView):
    """ネスト型: slot_index 指定で作成 or 置換（推奨）"""
    permission_classes = [AllowAny]

    @extend_schema(
        request=ExhibitUpsertSerializer,
        responses={
            200: ExhibitSerializer,
            201: ExhibitSerializer,
            400: OpenApiResponse(description="Bad Request"),
            401: OpenApiResponse(description="Not Authenticated"),
            403: OpenApiResponse(description="Forbidden"),
        },
    )
    def put(self, request, gallery_id, slot_index: int, *args, **kwargs):
        gallery, (mode, ident) = self._get_owned_gallery_or_404(request, gallery_id)

        exhibit = Exhibit.objects.filter(
            gallery=gallery,
            slot_index=slot_index,
            deleted_at__isnull=True,
        ).first()

        # “置換”に寄せるなら partial=False だけど、フロントが全項目送らないと壊れる
        # まずは partial=True が安全（送ったものだけ更新）
        serializer = ExhibitUpsertSerializer(
            exhibit,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)


        save_kwargs = {'gallery': gallery, 'slot_index': slot_index}
        if gallery.user_style == 'user':
            save_kwargs.update({'user_style': 'user', 'owner': ident, 'guest_id': None})
        else:
            save_kwargs.update({'user_style': 'guest', 'guest_id': ident, 'owner': None})

        if exhibit is None:
            obj = serializer.save(**save_kwargs)
            return Response(ExhibitSerializer(obj, context={'request': request}).data, status=status.HTTP_201_CREATED)

        obj = serializer.save(**save_kwargs)
        return Response(ExhibitSerializer(obj, context={'request': request}).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=None,
        responses={
            204: OpenApiResponse(description="Deleted"),
            401: OpenApiResponse(description="Not Authenticated"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Not found"),
        },
    )
    def delete(self, request, gallery_id, slot_index: int, *args, **kwargs):
        gallery, (mode, ident) = self._get_owned_gallery_or_404(request, gallery_id)
        try:
            obj = Exhibit.objects.filter(gallery=gallery, slot_index=slot_index, deleted_at__isnull=True).get()
        except Exhibit.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()  # 論理削除
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- 6. Gallery / Exhibit API ---

class GalleryViewSet(viewsets.ModelViewSet):
    queryset = Gallery.objects.all()
    serializer_class = GallerySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Gallery.objects.filter(owner=self.request.user, deleted_at__isnull=True).order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(
            user_style='user',
            owner=self.request.user,
            guest_id=None,
        )

    def perform_destroy(self, instance):
        instance.delete()  # 論理削除


class ExhibitViewSet(viewsets.ModelViewSet):
    queryset = Exhibit.objects.all()
    serializer_class = ExhibitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 自分の Exhibit のみ（Gallery owner と Exhibit owner の二重チェック）
        return Exhibit.objects.filter(
            owner=self.request.user,
            deleted_at__isnull=True,
        ).select_related('gallery').order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(user_style='user', owner=self.request.user, guest_id=None)

    def perform_destroy(self, instance):
        instance.delete()  # 論理削除



class GalleryPublicView(generics.RetrieveAPIView):
    serializer_class = GalleryPublicSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'  # ←これを追加（安全）

    def get_queryset(self):
        return (
            Gallery.objects
            .filter(is_public=True, deleted_at__isnull=True)  # ←論理削除あるなら入れる
            .prefetch_related(
                models.Prefetch(
                    'exhibits',
                    queryset=Exhibit.objects.filter(deleted_at__isnull=True).order_by('slot_index'),
                )
            )
        )
