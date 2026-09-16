from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import CustomUser
from .forms import CustomUserCreationForm, CustomUserChangeForm

class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    
    # 管理画面の一覧に表示する項目
    list_display = ["username", "email", "is_staff", "is_superuser", "is_approved_for_private"]
    
    # ユーザー編集画面のフィールド構成をカスタマイズ
    fieldsets = UserAdmin.fieldsets + (
        (_('コミュニティ権限'), {'fields': ('is_approved_for_private',)}),
    )

    # ==========================================
    # セキュリティ要件: スーパーユーザーのみに権限を制限
    # ==========================================
    def has_module_permission(self, request):
        # アプリケーション自体をスーパーユーザー以外には非表示にする
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        # 閲覧権限
        return request.user.is_superuser

    def has_add_permission(self, request):
        # 追加権限
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        # 編集権限
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        # 削除権限
        return request.user.is_superuser

admin.site.register(CustomUser, CustomUserAdmin)