import json
from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe
from django.core.files.storage import default_storage
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Schedule, User, Sticker, Page, Notebook, NotebookPage, UploadSession, FriendRequest, Friendship

# User Admin (変更なし)
class MyUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "display_name")

class MyUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = '__all__'

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = MyUserCreationForm
    form = MyUserChangeForm
    list_display = ('email', 'display_name', 'is_staff', 'is_active')
    search_fields = ('email', 'display_name')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Info', {'fields': ('display_name', 'avatar')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'display_name', 'password')}),
    )

# Sticker Admin (変更なし)
class StickerAdminForm(forms.ModelForm):
    upload_file = forms.ImageField(label='Upload PNG', required=False)
    class Meta:
        model = Sticker
        fields = '__all__'
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        uploaded_file = self.cleaned_data.get('upload_file')
        if uploaded_file:
            path = default_storage.save(f"stickers/{instance.id}.png", uploaded_file)
            instance.png = {"kind": "remote", "key": path, "mime": "image/png", "width": uploaded_file.image.width, "height": uploaded_file.image.height}
            instance.width = uploaded_file.image.width
            instance.height = uploaded_file.image.height
        if commit:
            instance.save()
        return instance

@admin.register(Sticker)
class StickerAdmin(admin.ModelAdmin):
    form = StickerAdminForm
    list_display = ('name', 'owner', 'width', 'height')
    # 自動計算されるフィールドは読み取り専用にする
    readonly_fields = ('width', 'height', 'png') 

# ---------------------------------------------------------
# Page Admin (修正)
# ---------------------------------------------------------
@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'type', 'date', 'id')
    list_filter = ('type', 'date')
    
    # フォームのフィールド指定（自動入力フィールドを除外）
    fields = ('owner', 'type', 'date', 'title', 'note', 'tags', 'scene_data', 'assets')
    
    # JSONFieldの入力エラーを防ぐため、デフォルト値を空の辞書として表示
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # フォーム初期値の設定例（必要に応じて）
        return form

# ---------------------------------------------------------
# Notebook Admin (修正: Inlineの扱い)
# ---------------------------------------------------------
class NotebookPageInline(admin.TabularInline):
    model = NotebookPage
    extra = 1
    # Pageが多いと重くなるので、raw_id_fieldsを使う
    raw_id_fields = ('page',) 

@admin.register(Notebook)
class NotebookAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner')
    inlines = [NotebookPageInline]
    # 中間テーブルの管理をしやすくする
    filter_horizontal = ('pages',) # ManyToManyFieldを直接操作する場合

# ---------------------------------------------------------
# Schedule Admin (修正)
# ---------------------------------------------------------
@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'type', 'start_date')
    fields = ('owner', 'type', 'start_date', 'title', 'scene_data', 'events_data')

# Other Models
@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'purpose', 'status')

@admin.register(NotebookPage)
class NotebookPageAdmin(admin.ModelAdmin):
    list_display = ('notebook', 'page', 'position')
    raw_id_fields = ('notebook', 'page') # 必須: ドロップダウンが重すぎるのを防ぐ

admin.site.register(FriendRequest)
admin.site.register(Friendship)