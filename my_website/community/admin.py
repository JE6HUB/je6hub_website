from django.contrib import admin
from .models import Channel, ChannelMembership, Message


@admin.register(ChannelMembership)
class ChannelMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'channel', 'role', 'status', 'invited_by', 'created_at')
    list_filter  = ('role', 'status', 'channel')
    search_fields = ('user__username', 'channel__name')

class MessageAdmin(admin.ModelAdmin):
    # 通常の管理者にはIPアドレスを見せない
    def get_list_display(self, request):
        if request.user.is_superuser:
            return ('sender', 'channel', 'text', 'ip_address', 'created_at')
        return ('sender', 'channel', 'text', 'created_at')

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:
            return ('ip_address',) # 編集不可・閲覧制限のためのベース処理
        return ()

admin.site.register(Channel)
admin.site.register(Message, MessageAdmin)