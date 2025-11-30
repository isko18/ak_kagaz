# admin.py
from django.contrib import admin
from django.utils.safestring import mark_safe

from .models import StaticPage, News


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "key",
        "slug",
        "is_active",
        "logo_preview",
        "updated_at",
    )
    list_filter = ("key", "is_active")
    search_fields = ("title", "slug", "content", "address", "phone", "email")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("logo_preview", "created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("key", "title", "slug", "is_active"),
        }),
        ("Логотип", {
            "fields": ("logo", "logo_preview"),
        }),
        ("Контент", {
            "fields": ("content",),
        }),
        ("Контакты", {
            "fields": ("address", "phone", "email", "map_iframe"),
        }),
        ("Служебное", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def logo_preview(self, obj):
        if obj.logo and getattr(obj.logo, "url", None):
            return mark_safe(
                f'<img src="{obj.logo.url}" style="max-height:60px; border-radius:6px;" />'
            )
        return "—"

    logo_preview.short_description = "Превью логотипа"


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "is_published",
        "published_at",
        "image_preview",
        "created_at",
    )
    list_filter = ("is_published", "published_at", "created_at")
    search_fields = ("title", "slug", "preview_text", "content")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("image_preview", "created_at", "updated_at")
    date_hierarchy = "published_at"
    fieldsets = (
        (None, {
            "fields": ("title", "slug", "is_published", "published_at"),
        }),
        ("Изображение", {
            "fields": ("image", "image_preview"),
        }),
        ("Текст", {
            "fields": ("preview_text", "content"),
        }),
        ("Служебное", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def image_preview(self, obj):
        if obj.image and getattr(obj.image, "url", None):
            return mark_safe(
                f'<img src="{obj.image.url}" style="max-height:80px; border-radius:6px;" />'
            )
        return "—"

    image_preview.short_description = "Превью"
