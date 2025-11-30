# admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product",
        "product_name",
        "price",
        "quantity",
        "line_total",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # Позиции создаются только через сайт / API
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "external_id_short",
        "created_at",
        "phone",
        "person_type",
        "delivery_type",
        "status_colored",
        "total_qty",
        "total_amount",
    )
    list_filter = (
        "status",
        "person_type",
        "delivery_type",
        "created_at",
    )
    search_fields = (
        "id",
        "external_id",
        "phone",
        "email",
        "first_name",
        "last_name",
    )
    readonly_fields = (
        "external_id",
        "total_qty",
        "total_amount",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline]
    date_hierarchy = "created_at"
    list_per_page = 50

    fieldsets = (
        ("Основное", {
            "fields": (
                "status",
                "external_id",
                "user",
                "created_at",
                "updated_at",
            )
        }),
        ("Клиент", {
            "fields": (
                "first_name",
                "last_name",
                "phone",
                "extra_phone",
                "email",
                "person_type",
            )
        }),
        ("Доставка", {
            "fields": (
                "delivery_type",
                "street",
                "house",
                "flat",
                "delivery_comment",
            )
        }),
        ("Суммы", {
            "fields": (
                "total_qty",
                "total_amount",
            )
        }),
    )

    # ——— красивые колонки ———
    def external_id_short(self, obj):
        return str(obj.external_id)[:8]
    external_id_short.short_description = "Публичный №"

    def status_colored(self, obj):
        color = {
            Order.Status.NEW: "#0ea5e9",
            Order.Status.CONFIRMED: "#22c55e",
            Order.Status.PAID: "#16a34a",
            Order.Status.CANCELLED: "#ef4444",
        }.get(obj.status, "#6b7280")
        label = obj.get_status_display()
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>',
            color,
            label,
        )
    status_colored.short_description = "Статус"
    status_colored.admin_order_field = "status"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "product",
        "product_name",
        "price",
        "quantity",
        "line_total",
    )
    list_filter = ("order__status",)
    search_fields = (
        "product_name",
        "order__id",
        "order__external_id",
        "order__phone",
    )
