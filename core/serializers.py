from xxlimited import Str
from rest_framework import serializers
from .models import Schedule, User, UploadSession, Sticker, Page, Notebook, NotebookPage
from django.core.files.storage import default_storage
from storages.backends.s3boto3 import S3Boto3Storage
from .utils_for_cloudfront import generate_cf_signed_url 
# --- User ---
class UserSerializer(serializers.ModelSerializer):
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
class StickerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sticker
        fields = '__all__'
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at', 'usage_count')


# --- Page ---
class PageSerializer(serializers.ModelSerializer):
    #sceneData = serializers.JSONField(source='scene_data', required=False)
    class Meta:
        model = Page
        fields = '__all__'
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at')

# --- Schedule ---
class ScheduleSerializer(serializers.ModelSerializer):
    # CamelCase変換用（ライブラリ任せでOKだが、明示するなら記述）
    sceneData = serializers.JSONField(source='scene_data', required=False)
    eventsData = serializers.JSONField(source='events_data', required=False)

    class Meta:
        model = Schedule
        fields = '__all__'
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at')


# --- Notebook ---
class NotebookSerializer(serializers.ModelSerializer):
    # ページIDのリストを含める（順序付き）
    pageIds = serializers.SerializerMethodField()

    class Meta:
        model = Notebook
        fields = '__all__'
        read_only_fields = ('id', 'owner', 'created_at', 'updated_at')

    def get_pageIds(self, obj):
        # NotebookPage中間テーブルを使って順序通りにIDを取得
        return list(obj.notebookpage_set.order_by('position').values_list('page_id', flat=True))