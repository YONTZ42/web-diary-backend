from rest_framework import serializers
from .models import  Gallery, Exhibit
from django.core.files.storage import default_storage
from storages.backends.s3boto3 import S3Boto3Storage
from drf_spectacular.utils import extend_schema_field  # これをインポート
from drf_spectacular.types import OpenApiTypes
from django.conf import settings


# -----------------------------------------------------------------------------
# 8. Digital Miniature Museum (Gallery / Exhibit)
# -----------------------------------------------------------------------------

class ExhibitSerializer(serializers.ModelSerializer):
    """展示物（編集/管理用）。画像はS3 URL（string）を想定。"""

    class Meta:
        model = Exhibit
        fields = (
            'id',
            'gallery',
            'owner',
            'guest_id',
            'slot_index',
            'image_original_url',
            'image_cutout_png_url',
            'material_params',
            'style',
            'title',
            'description',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'owner', 'guest_id', 'created_at', 'updated_at')

    def validate_slot_index(self, value: int) -> int:
        # 仕様: 0〜11（3x4=12枠）
        if value < 0 or value > 11:
            raise serializers.ValidationError("slot_index must be between 0 and 11.")
        return value

    def validate_gallery(self, gallery):
        """自分のGalleryにしか展示できない（owner or guest の二重チェック）。"""
        request = self.context.get('request')
        if not request:
            return gallery

        # user
        if request.user and request.user.is_authenticated:
            if getattr(gallery, 'owner_id', None) != request.user.id:
                raise serializers.ValidationError("You do not own this gallery.")
            return gallery

        # guest
        guest_id = request.headers.get('X-Guest-Id')
        if not guest_id:
            raise serializers.ValidationError("X-Guest-Id header is required.")
        if getattr(gallery, 'guest_id', None) != guest_id:
            raise serializers.ValidationError("This gallery is not owned by this guest.")
        return gallery


class GallerySerializer(serializers.ModelSerializer):
    """ギャラリー（編集/管理用）。retrieveではexhibitsも返す。"""
    exhibits = ExhibitSerializer(many=True, read_only=True)

    class Meta:
        model = Gallery
        fields = (
            'id',
            'slug',
            'user_style',   # "user" | "guest"（※モデル側に追加が必要）
            'owner',
            'guest_id',
            'title',
            'layout_cols',
            'layout_rows',
            'is_public',
            'cover_render_url',
            'created_at',
            'updated_at',
            'exhibits',
        )
        read_only_fields = ('id', 'owner', 'guest_id', 'created_at', 'updated_at')

    def validate_slug(self, value: str) -> str:
        if value and len(value) > 64:
            raise serializers.ValidationError("slug is too long.")
        return value

    def create(self, validated_data):
        # slugが無い場合はランダム生成（静かな公開用）
        if not validated_data.get('slug'):
            import uuid
            validated_data['slug'] = uuid.uuid4().hex[:16]
        return super().create(validated_data)


# --- Public viewer serializers (slug viewer) ---

class ExhibitPublicSerializer(serializers.ModelSerializer):
    """公開閲覧用：owner/guest_id などは返さない。"""

    class Meta:
        model = Exhibit
        fields = (
            'id',
            'slot_index',
            'image_original_url',
            'image_cutout_png_url',
            'material_params',
            'style',
            'title',
            'description',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class GalleryPublicSerializer(serializers.ModelSerializer):
    exhibits = ExhibitPublicSerializer(many=True, read_only=True)

    class Meta:
        model = Gallery
        fields = (
            'id',
            'slug',
            'title',
            'layout_cols',
            'layout_rows',
            'is_public',
            'cover_render_url',
            'created_at',
            'updated_at',
            'exhibits',
        )
        read_only_fields = fields
