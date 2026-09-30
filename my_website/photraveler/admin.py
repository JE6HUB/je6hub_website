from django.contrib import admin

from .models import MapPin, PhotoComment, PinPhoto


class PhotoCommentInline(admin.TabularInline):
    model = PhotoComment
    extra = 0


class PinPhotoInline(admin.TabularInline):
    model = PinPhoto
    extra = 0


@admin.register(MapPin)
class MapPinAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'place_name', 'country', 'visited_on', 'created_at')
    list_filter  = ('user', 'country')
    search_fields = ('title', 'place_name', 'user__username')
    inlines = [PinPhotoInline, PhotoCommentInline]


@admin.register(PhotoComment)
class PhotoCommentAdmin(admin.ModelAdmin):
    list_display = ('pin', 'author_name', 'created_at')
