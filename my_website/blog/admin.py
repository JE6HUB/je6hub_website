from django.contrib import admin
from .models import BlogImage, Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'status', 'template', 'published_at', 'updated_at')
    list_filter = ('status', 'template')
    search_fields = ('title', 'subtitle', 'author__username')
    readonly_fields = ('body_delta', 'created_at', 'updated_at')


@admin.register(BlogImage)
class BlogImageAdmin(admin.ModelAdmin):
    list_display = ('image', 'uploader', 'created_at')
    search_fields = ('uploader__username',)
