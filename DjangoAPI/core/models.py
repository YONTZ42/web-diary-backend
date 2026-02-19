
# Create your models here.
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone

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
# 1. User & Upload Session
# -----------------------------------------------------------------------------

class UserManager(BaseUserManager):
    """カスタムユーザーマネージャー"""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser, BaseModel):
    """カスタムユーザーモデル"""
    username = None  # username廃止
    email = models.EmailField(unique=True)
    
    # Profile
    display_name = models.CharField(max_length=100, blank=True)
    # AssetRef形式のJSON（{kind, key, variants...}）
    avatar = models.JSONField(null=True, blank=True)

    # Stripe
    stripe_customer_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    subscription_status = models.CharField(max_length=50, default='none') # active, past_due etc.
    current_period_end = models.DateTimeField(null=True, blank=True)
    plan = models.CharField(max_length=50, default='free')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = 'users'


class UploadSession(BaseModel):
    """
    S3 Presigned URL アップロード管理用
    発行(issued) -> クライアントPUT -> 確定(confirmed) のフローを管理
    """
    STATUS_CHOICES = (
        ('issued', 'Issued'),
        ('uploaded', 'Uploaded'),
        ('confirmed', 'Confirmed'),
        ('expired', 'Expired'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=50) # sticker_png, page_asset, etc.
    s3_key = models.CharField(max_length=1024)
    mime = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'upload_sessions'

# -----------------------------------------------------------------------------
# 2. Friends
# -----------------------------------------------------------------------------

class FriendRequest(BaseModel):
    requester = models.ForeignKey(User, related_name='sent_requests', on_delete=models.CASCADE)
    target = models.ForeignKey(User, related_name='received_requests', on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20, 
        choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')],
        default='pending'
    )

    class Meta:
        db_table = 'friend_requests'
        unique_together = ('requester', 'target')

class Friendship(BaseModel):
    user1 = models.ForeignKey(User, related_name='friendships1', on_delete=models.CASCADE)
    user2 = models.ForeignKey(User, related_name='friendships2', on_delete=models.CASCADE)

    class Meta:
        db_table = 'friendships'
        unique_together = ('user1', 'user2')
        indexes = [
            models.Index(fields=['user1', 'user2']),
        ]

# -----------------------------------------------------------------------------
# 3. Sticker
# -----------------------------------------------------------------------------

class Sticker(BaseModel):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stickers')
    name = models.CharField(max_length=255, blank=True)
    tags = models.JSONField(default=list)  # string[]
    
    favorite = models.BooleanField(default=False)
    last_used_at = models.DateTimeField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)
    is_system = models.BooleanField(default=False)
 
    # AssetRef JSON
    png = models.JSONField() 
    thumb = models.JSONField(null=True, blank=True)
    
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()

    # StickerStyle JSON
    style = models.JSONField(default=dict) 
    # CropSource JSON
    crop_source = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'stickers'
        indexes = [
            models.Index(fields=['owner', 'favorite']),
            models.Index(fields=['owner', 'last_used_at']),
        ]

# -----------------------------------------------------------------------------
# 4. Page
# -----------------------------------------------------------------------------

class Page(BaseModel):
    TYPE_CHOICES = (
        ('diary', 'Diary'),
        ('schedule', 'Schedule'),
        ('free', 'Free'),
    )
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pages')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='diary')
    date = models.DateField(db_index=True) # YYYY-MM-DD
    title = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True) # OCR結果や検索用テキスト
    tags = models.JSONField(default=list, blank=True)

    # Excalidraw Data
    scene_data = models.JSONField(default=dict)
    assets = models.JSONField(default=dict) # Record<fileId, AssetRef>
    used_sticker_ids = models.JSONField(default=list) # UUID[]

    # Preview & Export (AssetRef)
    preview = models.JSONField(null=True, blank=True)
    export = models.JSONField(null=True, blank=True)

    # Layout (縦書き/横書き対応)
    layout_mode = models.CharField(max_length=20, default='auto') # portrait/landscape/auto
    layout_settings = models.JSONField(default=dict)

    class Meta:
        db_table = 'pages'
        indexes = [
            models.Index(fields=['owner', 'date']),
            models.Index(fields=['owner', 'type']),
        ]

class Schedule(BaseModel):
    TYPE_CHOICES = (
        ('monthly', 'Monthly'),
        ('weekly', 'Weekly'),
        ('daily', 'Daily'), # 必要に応じて
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='schedules')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='monthly')
    
    # 対象期間 (検索・ソート用)
    # monthlyなら "2024-02-01", weeklyなら週の開始日
    start_date = models.DateField(db_index=True)
    
    title = models.CharField(max_length=255, blank=True)

    # Excalidrawデータ (巨大なので一覧では取得しない)
    scene_data = models.JSONField(default=dict, blank=True)
    assets = models.JSONField(default=dict, blank=True)

    # スケジュール詳細リスト (ハーフシート用)
    # 構造: { "2024-02-01": [{id: "uuid", text: "mtg", done: false}, ...], ... }
    # 日付をキーにしたオブジェクト、または配列で管理
    events_data = models.JSONField(default=dict, blank=True)

    # プレビュー画像
    preview = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'schedules'
        # 同じ期間・同じタイプのスケジュールは1人1つまでとする制約（任意）
        unique_together = ('owner', 'type', 'start_date')
        indexes = [
            models.Index(fields=['owner', 'type', 'start_date']),
        ]




# -----------------------------------------------------------------------------
# 5. Notebook
# -----------------------------------------------------------------------------

class Notebook(BaseModel):
    VISIBILITY_CHOICES = (
        ('private', 'Private'),
        ('friends', 'Friends Only'),
        ('public', 'Public'),
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notebooks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    cover = models.JSONField(null=True, blank=True) # AssetRef
    tags = models.JSONField(default=list, blank=True)
    
    view_settings = models.JSONField(default=dict)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='private')

    # ManyToMany with explicit through model for ordering
    pages = models.ManyToManyField(Page, through='NotebookPage', related_name='notebooks')

    class Meta:
        db_table = 'notebooks'

class NotebookPage(models.Model):
    """中間テーブル：ページ順序を管理"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE)
    page = models.ForeignKey(Page, on_delete=models.CASCADE)
    position = models.IntegerField(default=0) # 並び順
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notebook_pages'
        ordering = ['position']
        unique_together = ('notebook', 'page')
        indexes = [
            models.Index(fields=['notebook', 'position']),
        ]

# -----------------------------------------------------------------------------
# 6. Stripe Purchase (Simplified)
# -----------------------------------------------------------------------------
"""
class StripeProduct(BaseModel):
    product_type = models.CharField(max_length=50) # sticker_pack etc
    stripe_product_id = models.CharField(max_length=255)
    stripe_price_id = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = 'stripe_products'

class Purchase(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(StripeProduct, on_delete=models.SET_NULL, null=True)
    stripe_checkout_session_id = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    amount = models.IntegerField()
    currency = models.CharField(max_length=10, default='jpy')
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'purchases'

"""