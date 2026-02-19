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
    GallerySerializer, ExhibitSerializer, ExhibitPublicSerializer,GalleryPublicSerializer
)

from drf_spectacular.utils import extend_schema, OpenApiResponse




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
        request=ExhibitSerializer,
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

        try:
            exhibit = Exhibit.objects.filter(gallery=gallery, slot_index=slot_index, deleted_at__isnull=True).get()
            partial = False  # 置換に寄せる
            serializer = ExhibitSerializer(exhibit, data=request.data, partial=partial, context={'request': request})
            serializer.is_valid(raise_exception=True)
        except Exhibit.DoesNotExist:
            serializer = ExhibitSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            exhibit = None

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
        qs = Exhibit.objects.filter(gallery=gallery, slot_index=slot_index, deleted_at__isnull=True)
        deleted = qs.delete()[0]
        if deleted == 0:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)

class GalleryPublicViewer(views.APIView):
    """公開閲覧用: slug から Gallery + 全Exhibit を取得して返す（is_publicのみ）"""
    permission_classes = [AllowAny]

    def get(self, request, slug: str, *args, **kwargs):
        try:
            gallery = (
                Gallery.objects
                .filter(slug=slug, is_public=True, deleted_at__isnull=True)
                .prefetch_related(models.Prefetch('exhibits', queryset=Exhibit.objects.order_by('slot_index')))
                .get()
            )
        except Gallery.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = GalleryPublicSerializer(gallery, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

# --- 6. Gallery / Exhibit API ---

class GalleryViewSet(viewsets.ModelViewSet):
    queryset = Gallery.objects.all()
    serializer_class = GallerySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Gallery.objects.filter(owner=self.request.user).order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ExhibitViewSet(viewsets.ModelViewSet):
    queryset = Exhibit.objects.all()
    serializer_class = ExhibitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 自分の Exhibit のみ（Gallery owner と Exhibit owner の二重チェック）
        return Exhibit.objects.filter(owner=self.request.user).select_related('gallery').order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)



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
                models.Prefetch('exhibits', queryset=Exhibit.objects.order_by('slot_index'))
            )
        )
