from rest_framework import serializers
from .models import Schedule, User, UploadSession, Sticker, Page, Notebook, NotebookPage
from django.core.files.storage import default_storage
from storages.backends.s3boto3 import S3Boto3Storage
from .utils_for_cloudfront import generate_cf_signed_url
from drf_spectacular.utils import extend_schema_field  # これをインポート
from drf_spectacular.types import OpenApiTypes


#-- Asset Reference Serializers: static data information ---
class AssetRefLiteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=['local', 'remote'])
    key = serializers.CharField(help_text="localならblobURI/uuid, remoteならS3 key/URL")
    mime = serializers.CharField()
    width = serializers.IntegerField(required=False, allow_null=True)
    height = serializers.IntegerField(required=False, allow_null=True)
    sha256 = serializers.CharField(required=False, allow_null=True)

class AssetRefSerializer(AssetRefLiteSerializer):
    size = serializers.IntegerField(required=False, allow_null=True)
    filename = serializers.CharField(required=False, allow_null=True)
    variants = serializers.DictField(
        child=AssetRefLiteSerializer(), 
        required=False, 
        help_text="thumb, medium などのバリエーション"
    )
    source = serializers.DictField(required=False)

class ExcalidrawSceneDataSerializer(serializers.Serializer):
    # elements: 図形要素のリスト。中身は多様なので DictField で受ける
    elements = serializers.ListField(
        child=serializers.DictField(), 
        required=False,
        help_text="Excalidrawの図形要素（Rectangle, Arrow, Text等）の配列"
    )
    # appState: ビューの状態（ズーム、背景色など）
    appState = serializers.DictField(
        required=False,
        help_text="画面表示に関する設定（theme, scrollX, scrollY, zoom等）"
    )
    

# --- User ---
class UserSerializer(serializers.ModelSerializer):
    @extend_schema_field(AssetRefSerializer) # JSONFieldに型を付与
    def get_avatar(self, obj):
        return obj.avatar
    class Meta:
        model = User
        fields = ('id', 'email', 'display_name', 'avatar', 'stripe_customer_id', 'subscription_status', 'plan')
        read_only_fields = ('id', 'stripe_customer_id', 'subscription_status')

# --- User Registration ---
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ('email', 'password', 'display_name') # 必要に応じて avatar なども追加

    def create(self, validated_data):
        # UserManagerのcreate_userメソッドを使ってユーザーを作成（パスワードハッシュ化含む）
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            display_name=validated_data.get('display_name', '')
        )
        return user

# --- Upload (Presigned URL) ---
class UploadIssueSerializer(serializers.Serializer):
    """アップロード開始要求（クライアント→サーバー）"""
    filename = serializers.CharField()
    mime_type = serializers.CharField()
    purpose = serializers.CharField() # sticker, page_asset 等

class UploadConfirmSerializer(serializers.Serializer):
    """アップロード完了報告（クライアント→サーバー）"""
    upload_session_id = serializers.UUIDField()

# --- Sticker ---
class StickerStyleSerializer(serializers.Serializer):
    outline = serializers.DictField()
    shadow = serializers.DictField()

class StickerSerializer(serializers.ModelSerializer):
    png = AssetRefSerializer()
    thumb = AssetRefSerializer(required=False, allow_null=True)
    style = StickerStyleSerializer(required=False)
    tags = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="タグの配列"
    )
    class Meta:
        model = Sticker
        fields = '__all__'
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at', 'usage_count')





# --- Page ---
class PageSerializer(serializers.ModelSerializer):
    assets = serializers.DictField(child=AssetRefSerializer())
    preview = AssetRefSerializer(required=False, allow_null=True)
    export = serializers.DictField(required=False, allow_null=True)
    scene_data = ExcalidrawSceneDataSerializer(required=False)
    used_sticker_ids = serializers.ListField(child=serializers.UUIDField(), required=False)

    class Meta:
        model = Page
        fields = '__all__'
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at')

# --- Schedule ---
class ScheduleSerializer(serializers.ModelSerializer):
    assets = serializers.DictField(child=AssetRefSerializer())
    preview = AssetRefSerializer(required=False, allow_null=True)
    scene_data = ExcalidrawSceneDataSerializer(required=False)

    class Meta:
        model = Schedule
        fields = '__all__'
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at')


# --- Notebook ---
class NotebookSerializer(serializers.ModelSerializer):
    cover = AssetRefSerializer(required=False, allow_null=True)
    # ページIDのリストを含める（順序付き）
    page_ids = serializers.SerializerMethodField()
    class Meta:
        model = Notebook
        fields = '__all__'
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at')

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_page_ids(self, obj):
        # NotebookPage中間テーブルを使って順序通りにIDを取得
        return list(obj.notebookpage_set.filter(
            page__deleted_at__isnull=True).order_by('position').values_list('page_id', flat=True))