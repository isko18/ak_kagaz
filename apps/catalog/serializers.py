# serializers.py
from rest_framework import serializers

from .models import Category, Product, ProductImage


# ==========================
# Product: list (лайтовый)
# ==========================
class ProductListSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(source="category.id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    main_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "code",
            "name",
            "slug",
            "price",
            "old_price",
            "discount",
            "promotion",
            "is_available",
            "category_id",
            "category_name",
            "main_image",
        )

    def get_main_image(self, obj):
        """
        Берём первую картинку (мы её заранее подтянем через prefetch_related).
        Без доп. запросов к БД.
        """
        request = self.context.get("request")
        img = next(iter(getattr(obj, "images_all", obj.images.all())), None)
        if img and getattr(img.image, "url", None):
            url = img.image.url
            return request.build_absolute_uri(url) if request else url
        return None


# ==========================
# Product: images
# ==========================
class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ("id", "image", "image_url")

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and getattr(obj.image, "url", None):
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return None


# ==========================
# Category: short (для вложения)
# ==========================
class CategoryShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug")


# ==========================
# Product: detail
# ==========================
class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategoryShortSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=Category.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "code",
            "name",
            "slug",
            "description",
            "category",
            "category_id",
            "price",
            "old_price",
            "discount",
            "promotion",
            "is_active",
            "is_available",
            "created_at",
            "updated_at",
            "images",
        )
        read_only_fields = ("created_at", "updated_at")


# ==========================
# Category: базовый
# ==========================
class CategorySerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        allow_null=True,
        required=False,
    )
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "parent",
            "image",
            "image_url",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and getattr(obj.image, "url", None):
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return None


# ==========================
# Category: дерево
# ==========================
class CategoryTreeSerializer(CategorySerializer):
    children = serializers.SerializerMethodField()

    class Meta(CategorySerializer.Meta):
        fields = CategorySerializer.Meta.fields + ("children",)

    def get_children(self, obj):
        qs = obj.get_children()
        return CategoryTreeSerializer(qs, many=True, context=self.context).data
