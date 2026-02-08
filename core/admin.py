import json
from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe
from django.core.files.storage import default_storage
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Schedule, User, Sticker, Page, Notebook, NotebookPage, UploadSession, FriendRequest, Friendship

# ---------------------------------------------------------
# User Admin (Previous Code)
# ---------------------------------------------------------
class UserAdmin(BaseUserAdmin):
    ordering = ['email']
    list_display = ['email', 'display_name', 'is_staff', 'is_active']
    search_fields = ['email', 'display_name']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('display_name', 'avatar')}),
        ('Stripe', {'fields': ('stripe_customer_id', 'subscription_status', 'plan')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'password')}),
    )

admin.site.register(User, UserAdmin)

# ---------------------------------------------------------
# Sticker Admin (Previous Code)
# ---------------------------------------------------------
class StickerAdminForm(forms.ModelForm):
    upload_file = forms.ImageField(label='Upload PNG', required=False, help_text='自動S3アップロード用')

    class Meta:
        model = Sticker
        fields = '__all__'

    def save(self, commit=True):
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data.get('upload_file')
        if uploaded_file:
            filename = f"stickers/{instance.id}.png"
            path = default_storage.save(filename, uploaded_file)
            asset_ref = {
                "kind": "remote", "key": path, "mime": "image/png",
                "width": uploaded_file.image.width, "height": uploaded_file.image.height,
            }
            instance.png = asset_ref
            instance.width = uploaded_file.image.width
            instance.height = uploaded_file.image.height
        if commit:
            instance.save()
        return instance

@admin.register(Sticker)
class StickerAdmin(admin.ModelAdmin):
    form = StickerAdminForm
    list_display = ('name', 'owner', 'created_at', 'width', 'height')
    readonly_fields = ('width', 'height')
    search_fields = ('name',)

# ---------------------------------------------------------
# Page Admin
# ---------------------------------------------------------
@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'type', 'date', 'id')
    list_filter = ('type', 'date')
    search_fields = ('title', 'note', 'id')
    readonly_fields = ('pretty_scene_data',)

    fieldsets = (
        ('Basic', {'fields': ('owner', 'type', 'date', 'title', 'note', 'tags')}),
        ('Data', {'fields': ('pretty_scene_data', 'assets', 'used_sticker_ids')}),
        ('Preview', {'fields': ('preview', 'export')}),
    )

    def pretty_scene_data(self, instance):
        """JSONを見やすく整形して表示"""
        return mark_safe(f'<pre>{json.dumps(instance.scene_data, indent=2, ensure_ascii=False)}</pre>')
    pretty_scene_data.short_description = 'Scene Data (JSON)'

# ---------------------------------------------------------
# Schedule Admin
# ---------------------------------------------------------
@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'type', 'start_date', 'id')
    list_filter = ('type', 'start_date')
    search_fields = ('title', 'owner__email')
    readonly_fields = ('pretty_scene_data', 'pretty_events_data')

    fieldsets = (
        ('Basic', {'fields': ('owner', 'type', 'start_date', 'title')}),
        ('Data', {'fields': ('pretty_events_data', 'pretty_scene_data', 'assets')}),
        ('Preview', {'fields': ('preview',)}),
    )

    def pretty_scene_data(self, instance):
        return mark_safe(f'<pre>{json.dumps(instance.scene_data, indent=2, ensure_ascii=False)}</pre>')
    pretty_scene_data.short_description = 'Scene Data (JSON)'

    def pretty_events_data(self, instance):
        """イベントリスト（ハーフシート用データ）の整形表示"""
        return mark_safe(f'<pre>{json.dumps(instance.events_data, indent=2, ensure_ascii=False)}</pre>')
    pretty_events_data.short_description = 'Events Data (JSON)'


# ---------------------------------------------------------
# Notebook Admin with Inline Pages
# ---------------------------------------------------------

# NotebookPageの中間テーブルをインラインで表示
class NotebookPageInline(admin.TabularInline):
    model = NotebookPage
    extra = 1
    ordering = ('position',)
    autocomplete_fields = ['page'] # Pageが多い場合に検索可能にする

@admin.register(Notebook)
class NotebookAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'visibility', 'page_count')
    inlines = [NotebookPageInline]
    search_fields = ('title',)

    def page_count(self, obj):
        return obj.pages.count()
    page_count.short_description = 'Pages'

# 中間テーブル単体でも見れるように登録
@admin.register(NotebookPage)
class NotebookPageAdmin(admin.ModelAdmin):
    list_display = ('notebook', 'position', 'page', 'added_at')
    list_filter = ('notebook',)
    ordering = ('notebook', 'position')

# ---------------------------------------------------------
# Other Models
# ---------------------------------------------------------
@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'purpose', 'status', 'expires_at')
    list_filter = ('status', 'purpose')

admin.site.register(FriendRequest)
admin.site.register(Friendship)