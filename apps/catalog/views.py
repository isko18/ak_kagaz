# views.py
from django.db.models import Prefetch
from rest_framework import viewsets
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from .models import Product, ProductImage, Category
from .serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
)


# ===== фильтрация товаров =====
class ProductFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(field_name="category_id")
    category_in = django_filters.BaseInFilter(field_name="category_id")
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    promotion = django_filters.BooleanFilter(field_name="promotion")
    in_stock = django_filters.BooleanFilter(field_name="is_available")

    class Meta:
        model = Product
        fields = (
            "category",
            "promotion",
            "is_active",
            "is_available",
        )


# ===== пагинация =====
class ProductPagination(PageNumberPagination):
    page_size = 40
    page_size_query_param = "page_size"
    max_page_size = 200


# ===== категории =====
class CategoryViewSet(ReadOnlyModelViewSet):
    """
    GET /categories/       -> список категорий (плоский)
    GET /categories/tree/  -> дерево категорий
    GET /categories/{id}/  -> детальная категория
    """

    queryset = Category.objects.filter(is_active=True).order_by("tree_id", "lft")
    serializer_class = CategorySerializer
    filter_backends = [SearchFilter]
    search_fields = ("name", "slug")

    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request, *args, **kwargs):
        """
        Дерево категорий от корня вниз.
        """
        roots = self.get_queryset().filter(parent__isnull=True)
        serializer = CategoryTreeSerializer(
            roots,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)


# ===== товары =====
class ProductViewSet(ReadOnlyModelViewSet):
    """
    GET /products/        -> быстрый список (лайт-данные, 1 картинка)
    GET /products/{id}/   -> детальная карточка
    """

    pagination_class = ProductPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ("name", "code", "slug")
    ordering_fields = (
        "created_at",
        "price",
        "discount",
        "name",
    )
    ordering = ("-created_at",)

    def get_queryset(self):
        """
        Оптимизированный queryset:
        - select_related("category") — нет лишних запросов по категории
        - only(...) — забираем только нужные поля
        - префетч картинок разный для list и detail
        """
        base_qs = (
            Product.objects
            .filter(is_active=True, is_available=True)
            .select_related("category")
            .only(
                "id",
                "code",
                "name",
                "slug",
                "price",
                "old_price",
                "discount",
                "promotion",
                "is_available",
                "is_active",
                "created_at",
                "updated_at",
                "category__id",
                "category__name",
                "category__slug",
            )
        )

        # Для списка — только первая картинка, через to_attr="images_all"
        if getattr(self, "action", None) == "list":
            images_qs = (
                ProductImage.objects
                .only("id", "image", "product")
                .order_by("id")
            )
            base_qs = base_qs.prefetch_related(
                Prefetch("images", queryset=images_qs, to_attr="images_all")
            )
        else:
            # Для детальной карточки — все картинки
            base_qs = base_qs.prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.only("id", "image", "product"),
                )
            )

        return base_qs

    def get_serializer_class(self):
        if getattr(self, "action", None) == "list":
            return ProductListSerializer
        return ProductDetailSerializer
