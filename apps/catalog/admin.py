# admin.py
from django.contrib import admin
from django.utils.safestring import mark_safe
from mptt.admin import DraggableMPTTAdmin

from .models import Category, Product, ProductImage


@admin.register(Category)
class CategoryAdmin(DraggableMPTTAdmin):
    mptt_indent_field = "name"
    list_display = (
        "tree_actions",
        "indented_title",
        "slug",
        "is_active",
        "image_preview",
        "created_at",
    )
    list_display_links = ("indented_title",)
    list_editable = ("is_active",)
    search_fields = ("name", "slug")
    list_filter = ("is_active",)

    # важно: created_at/updated_at в readonly
    readonly_fields = ("image_preview", "created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}

    fieldsets = (
        (None, {"fields": ("name", "slug", "parent")}),
        ("Изображение", {"fields": ("image", "image_preview")}),
        ("Статус", {"fields": ("is_active",)}),
        ("Служебное", {"fields": ("created_at", "updated_at")}),
    )

    def image_preview(self, obj):
        if obj.image and getattr(obj.image, "url", None):
            return mark_safe(
                f'<img src="{obj.image.url}" style="max-height:60px; border-radius:6px;" />'
            )
        return "—"

    image_preview.short_description = "Превью"


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    readonly_fields = ("image_preview",)

    def image_preview(self, obj):
        if obj.image and getattr(obj.image, "url", None):
            return mark_safe(
                f'<img src="{obj.image.url}" style="max-height:60px; border-radius:6px;" />'
            )
        return "—"

    image_preview.short_description = "Превью"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "price",
        "promotion",
        "discount",
        "is_active",
        "is_available",
        "main_image_preview",   # 👈 превью
        "created_at",
    )
    list_filter = (
        "is_active",
        "is_available",
        "promotion",
        "category",
    )
    search_fields = ("code", "name", "slug")
    list_editable = ("price", "promotion", "discount", "is_active", "is_available")
    inlines = [ProductImageInline]
    prepopulated_fields = {"slug": ("name",)}

    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("code", "name", "slug", "category")}),
        ("Цены", {"fields": ("price", "old_price", "discount", "promotion")}),
        ("Статус", {"fields": ("is_active", "is_available")}),
        ("Служебное", {"fields": ("created_at", "updated_at")}),
    )

    def main_image_preview(self, obj):
        """
        Показываем первую картинку товара в списке.
        """
        img = obj.images.first()
        if img and img.image and getattr(img.image, "url", None):
            return mark_safe(
                f'<img src="{img.image.url}" style="max-height:60px; border-radius:6px;" />'
            )
        return "—"

    main_image_preview.short_description = "Фото"
