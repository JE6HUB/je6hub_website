from django.contrib import admin

from .models import ApiToken


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'created_at', 'last_used_at')
    search_fields = ('user__username', 'name')
    readonly_fields = ('user', 'name', 'created_at', 'last_used_at')

    def has_add_permission(self, request):
        return False
