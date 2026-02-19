
# Create your models here.
import uuid
from django.db import models
from django.utils import timezone
#from core.models import User
from django.conf import settings
# -----------------------------------------------------------------------------
# 0. 共通 Abstract Model
# -----------------------------------------------------------------------------

class BaseModel(models.Model):
    """
    全モデル共通の基底クラス
    UUIDプライマリキーと監査ログ用フィールドを持つ
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schema_version = models.PositiveIntegerField(default=1)  # マイグレーション用
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)  # 論理削除用

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """論理削除の実装"""
        self.deleted_at = timezone.now()
        self.save()


# -----------------------------------------------------------------------------
# 7. Digital Miniature Museum (Gallery / Exhibit)
# -----------------------------------------------------------------------------

class Gallery(BaseModel):
    """ミニチュア展示室（ギャラリー）"""

    USER_STYLE_CHOICES = (
        ('user', 'User'),
        ('guest', 'Guest'),
    )

    # 認証形式（user / guest）
    user_style = models.CharField(max_length=10, choices=USER_STYLE_CHOICES, default='user', db_index=True)

    # user の場合に必須
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='galleries',
        null=True, blank=True
    )

    # guest の場合に必須（X-Guest-Id で渡される識別子）
    guest_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    slug = models.SlugField(max_length=64, unique=True, db_index=True)
    title = models.CharField(max_length=255, blank=True, default='')

    layout_cols = models.PositiveIntegerField(default=3)
    layout_rows = models.PositiveIntegerField(default=4)

    is_public = models.BooleanField(default=False)

    # 一覧用サムネ（S3 URL）
    cover_render_url = models.URLField(max_length=2048, null=True, blank=True)

    class Meta:
        db_table = 'galleries'
        indexes = [
            models.Index(fields=['user_style', 'created_at']),
            models.Index(fields=['owner', 'created_at']),
            models.Index(fields=['guest_id', 'created_at']),
            models.Index(fields=['slug']),
        ]
        constraints = [
            # user_style='user' -> owner NOT NULL & guest_id IS NULL/blank
            models.CheckConstraint(
                name='gallery_user_style_user_requires_owner',
                check=(
                    models.Q(user_style='user', owner__isnull=False) &
                    (models.Q(guest_id__isnull=True) | models.Q(guest_id=''))
                )  | models.Q(user_style='guest')
            ),
            # user_style='guest' -> guest_id NOT NULL/blank & owner IS NULL
            models.CheckConstraint(
                name='gallery_user_style_guest_requires_guest_id',
                check=(
                    models.Q(user_style='guest', owner__isnull=True) &
                    models.Q(guest_id__isnull=False) & ~models.Q(guest_id='')
                ) | models.Q(user_style='user')
            ),
        ]

    def clean(self):
        # アプリ層での安全装置（DB制約と二重化）
        if self.user_style == 'user':
            if self.owner_id is None:
                raise ValueError('Gallery.user_style="user" の場合 owner は必須です')
            if self.guest_id:
                raise ValueError('Gallery.user_style="user" の場合 guest_id は空にしてください')
        elif self.user_style == 'guest':
            if not self.guest_id:
                raise ValueError('Gallery.user_style="guest" の場合 guest_id は必須です')
            if self.owner_id is not None:
                raise ValueError('Gallery.user_style="guest" の場合 owner は null にしてください')


class Exhibit(BaseModel):
    """展示物（1ギャラリー内の1枠）"""

    USER_STYLE_CHOICES = (
        ('user', 'User'),
        ('guest', 'Guest'),
    )

    gallery = models.ForeignKey(
        Gallery, on_delete=models.CASCADE, related_name='exhibits'
    )

    # Exhibit も Gallery と同じ認証形式で管理（原則 gallery.user_style と一致させる）
    user_style = models.CharField(max_length=10, choices=USER_STYLE_CHOICES, default='user', db_index=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exhibits',
        null=True, blank=True
    )

    guest_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    slot_index = models.PositiveIntegerField()  # 0..11

    # 画像URL（S3 URL）
    image_original_url = models.URLField(max_length=2048)
    image_cutout_png_url = models.URLField(max_length=2048, null=True, blank=True)

    # WebGPU材質パラメータ（JSON）
    # 例: {"preset": "clear_sheet", "roughness": 0.2, "metalness": 0.0, ...}
    material_params = models.JSONField(default=dict, blank=True)

    style = models.CharField(max_length=50, blank=True, default='')
    title = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'exhibits'
        unique_together = ('gallery', 'slot_index')
        indexes = [
            models.Index(fields=['gallery', 'slot_index']),
            models.Index(fields=['user_style', 'created_at']),
            models.Index(fields=['owner', 'created_at']),
            models.Index(fields=['guest_id', 'created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                name='exhibit_slot_index_0_11',
                check=models.Q(slot_index__gte=0) & models.Q(slot_index__lte=11),
            ),
            models.CheckConstraint(
                name='exhibit_user_style_user_requires_owner',
                check=(
                    models.Q(user_style='user', owner__isnull=False) &
                    (models.Q(guest_id__isnull=True) | models.Q(guest_id=''))
                ) | models.Q(user_style='guest')
            ),
            models.CheckConstraint(
                name='exhibit_user_style_guest_requires_guest_id',
                check=(
                    models.Q(user_style='guest', owner__isnull=True) &
                    models.Q(guest_id__isnull=False) & ~models.Q(guest_id='')
                ) | models.Q(user_style='user')
            ),
        ]

    def clean(self):
        # gallery.user_style と一致させる（事故防止）
        if self.gallery_id and self.user_style != self.gallery.user_style:
            raise ValueError('Exhibit.user_style は Gallery.user_style と一致させてください')

        if self.user_style == 'user':
            if self.owner_id is None:
                raise ValueError('Exhibit.user_style="user" の場合 owner は必須です')
            if self.guest_id:
                raise ValueError('Exhibit.user_style="user" の場合 guest_id は空にしてください')
        elif self.user_style == 'guest':
            if not self.guest_id:
                raise ValueError('Exhibit.user_style="guest" の場合 guest_id は必須です')
            if self.owner_id is not None:
                raise ValueError('Exhibit.user_style="guest" の場合 owner は null にしてください')
