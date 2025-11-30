from decimal import Decimal
from rest_framework import serializers
from apps.catalog.models import Category, Product, ProductImage
from .models import  Order, OrderItem
# если уже импортировал Category/Product/ProductImage – просто добавь Order, OrderItem


class OrderItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ("id", "product_name", "price", "quantity", "line_total")


class OrderSerializer(serializers.ModelSerializer):
    # то, что приходит с фронта
    items = OrderItemCreateSerializer(many=True, write_only=True)

    # то, что отдаём обратно
    items_detail = OrderItemSerializer(source="items", many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "external_id",
            "first_name",
            "last_name",
            "phone",
            "email",
            "extra_phone",
            "person_type",
            "delivery_type",
            "street",
            "house",
            "flat",
            "delivery_comment",
            "total_qty",
            "total_amount",
            "status",
            "items",          # вход
            "items_detail",   # выход
            "created_at",
        )
        read_only_fields = (
            "id",
            "external_id",
            "total_qty",
            "total_amount",
            "status",
            "created_at",
        )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Корзина пуста.")
        return value

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])

        # привязываем пользователя, если авторизован — но это не обязательно
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            validated_data.setdefault("user", user)

        # подтягиваем товары одним запросом
        product_ids = [item["product_id"] for item in items_data]
        products_qs = Product.objects.filter(
            id__in=product_ids,
            is_active=True,
            is_available=True,
        )
        products_map = {p.id: p for p in products_qs}

        # проверяем, что все продукты существуют
        missing = [pid for pid in product_ids if pid not in products_map]
        if missing:
            raise serializers.ValidationError(
                {"items": f"Некоторые товары не найдены или недоступны: {missing}"}
            )

        total_qty = 0
        total_amount = Decimal("0")

        # создаём заказ
        order = Order.objects.create(**validated_data)

        items_for_bulk = []
        for item in items_data:
            product = products_map[item["product_id"]]
            qty = int(item["quantity"])
            price = product.price or Decimal("0")
            line_total = price * qty

            total_qty += qty
            total_amount += line_total

            items_for_bulk.append(
                OrderItem(
                    order=order,
                    product=product,
                    product_name=product.name,
                    price=price,
                    quantity=qty,
                    line_total=line_total,
                )
            )

        OrderItem.objects.bulk_create(items_for_bulk)

        # обновляем суммы в заказе
        order.total_qty = total_qty
        order.total_amount = total_amount
        order.save(update_fields=["total_qty", "total_amount", "updated_at"])

        return order
