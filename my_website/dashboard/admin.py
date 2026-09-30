from django.contrib import admin

from .models import ModerationLog, Report, UserSuspension


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('kind', 'object_id', 'reason', 'status', 'reporter', 'created_at')
    list_filter = ('status', 'kind', 'reason')


@admin.register(UserSuspension)
class UserSuspensionAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_by', 'created_at')


@admin.register(ModerationLog)
class ModerationLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'target')
    list_filter = ('action',)
