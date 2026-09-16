from django.contrib import admin

from .models import MapPin, PhotoComment


class PhotoCommentInline(admin.TabularInline):
    model = PhotoComment
    extra = 0


@admin.register(MapPin)
class MapPinAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'latitude', 'longitude', 'created_at')
    list_filter  = ('user',)
    search_fields = ('title', 'user__username')
    inlines = [PhotoCommentInline]


@admin.register(PhotoComment)
class PhotoCommentAdmin(admin.ModelAdmin):
    list_display = ('pin', 'author_name', 'created_at')
