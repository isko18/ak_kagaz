from django.db.models import Prefetch
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
import django_filters
import hmac
import hashlib
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Product, ProductImage, Category, Characteristics
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

    # 👇 фильтры по оптовой цене
    min_wholesale_price = django_filters.NumberFilter(
        field_name="wholesale_price", lookup_expr="gte"
    )
    max_wholesale_price = django_filters.NumberFilter(
        field_name="wholesale_price", lookup_expr="lte"
    )

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
    GET /categories/         -> список категорий (плоский)
    GET /categories/tree/    -> дерево категорий
    GET /categories/{slug}/  -> детальная категория по slug
    """

    queryset = Category.objects.filter(is_active=True).order_by("tree_id", "lft")
    serializer_class = CategorySerializer
    filter_backends = [SearchFilter]
    search_fields = ("name", "slug")

    # деталь по slug, а не по id
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

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
    GET /products/          -> быстрый список (лайт-данные, 1 картинка)
    GET /products/{slug}/   -> детальная карточка по slug
    """

    pagination_class = ProductPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ("name", "code", "slug")
    ordering_fields = (
        "created_at",
        "price",
        "wholesale_price",  # 👈 сортировка по опту тоже доступна
        "discount",
        "name",
    )
    ordering = ("-created_at",)

    # деталь по slug
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self):
        """
        Оптимизированный queryset:
        - select_related("category") — нет лишних запросов по категории
        - only(...) — забираем только нужные поля продукта
        - list: префетчим только первую картинку (через to_attr="images_all")
        - detail: префетчим все картинки и характеристики с key
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
                "wholesale_price", 
                "old_price",
                "discount",
                "promotion",
                "is_available",
                "is_active",
                "quantity", 
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
            # Для детальной карточки — все картинки + характеристики с key
            images_qs = ProductImage.objects.only("id", "image", "product")
            chars_qs = (
                Characteristics.objects
                .select_related("key")
                .only(
                    "id",
                    "product",
                    "key",
                    "value",
                    "key__id",
                    "key__title",
                    "key__unit",
                )
            )
            base_qs = base_qs.prefetch_related(
                Prefetch("images", queryset=images_qs),
                Prefetch("characteristics", queryset=chars_qs),
            )

        return base_qs

    def get_serializer_class(self):
        if getattr(self, "action", None) == "list":
            return ProductListSerializer
        return ProductDetailSerializer



def _verify_signature(raw_body: bytes, signature: str) -> bool:
    # signature: sha256=<hex>
    if not signature or not signature.startswith("sha256="):
        return False
    their_hex = signature.split("=", 1)[1].strip()

    secret = getattr(settings, "CRM_WEBHOOK_SECRET", "")
    if not secret:
        return False

    our_hex = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(our_hex, their_hex)


def _to_decimal(v, default=Decimal("0")):
    if v is None or v == "":
        return default
    try:
        return Decimal(str(v).replace(",", "."))
    except Exception:
        return default


def _safe_unique_slug(model, base_slug: str, slug_field="slug", max_len=512):
    base = (base_slug or "").strip()[:max_len] or "item"
    slug = base
    i = 1
    while model.objects.filter(**{slug_field: slug}).exists():
        suffix = f"-{i}"
        slug = (base[: max_len - len(suffix)] + suffix).strip("-")
        i += 1
    return slug


class CRMProductsWebhookAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw = request.body or b""
        sig = request.headers.get("X-CRM-Signature", "")
        if not _verify_signature(raw, sig):
            return Response({"detail": "Invalid signature"}, status=401)

        payload = request.data or {}
        data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload

        external_id = data.get("id") or data.get("product_id") or data.get("external_id")
        if not external_id:
            return Response({"detail": "Missing product id (id/product_id/external_id)"}, status=400)

        # 1) Категория (если прилетает)
        # Поддержка разных форматов:
        # category может быть строкой, или объектом {name, slug}, или {id, name, slug}
        category_obj = data.get("category")
        category = None
        if isinstance(category_obj, dict):
            c_slug = (category_obj.get("slug") or "").strip()
            c_name = (category_obj.get("name") or "").strip()
            if not c_slug and c_name:
                c_slug = slugify(c_name)[:255]
            if c_slug:
                category, _ = Category.objects.get_or_create(
                    slug=c_slug,
                    defaults={"name": c_name or c_slug, "is_active": True},
                )
            elif c_name:
                # если slug не смогли получить — создадим от имени
                gen_slug = _safe_unique_slug(Category, slugify(c_name)[:255])
                category = Category.objects.create(name=c_name, slug=gen_slug, is_active=True)

        elif isinstance(category_obj, str) and category_obj.strip():
            c_name = category_obj.strip()
            c_slug = slugify(c_name)[:255] or "category"
            category, _ = Category.objects.get_or_create(
                slug=c_slug,
                defaults={"name": c_name, "is_active": True},
            )

        # 2) Поля товара
        name = (data.get("name") or "").strip()
        code = (data.get("code") or "").strip()  # если в CRM есть code — используем
        barcode = (data.get("barcode") or "").strip()
        description = data.get("description") or ""
        price = _to_decimal(data.get("price"), default=Decimal("0"))
        old_price = _to_decimal(data.get("old_price"), default=None) if data.get("old_price") is not None else None
        wholesale_price = _to_decimal(data.get("wholesale_price"), default=None) if data.get("wholesale_price") is not None else None
        discount = int(data.get("discount") or 0)
        promotion = bool(data.get("promotion") or False)
        quantity = int(data.get("quantity") or 0)
        is_active = bool(data.get("is_active") if data.get("is_active") is not None else True)
        is_available = bool(data.get("is_available") if data.get("is_available") is not None else True)

        # slug: берём из CRM если есть, иначе генерим
        incoming_slug = (data.get("slug") or "").strip()
        if not incoming_slug and name:
            incoming_slug = slugify(name)[:512]

        # ВАЖНО: твой сайт требует unique code+slug.
        # Если CRM не даёт code — используем external_id как code (гарант уникальности).
        if not code:
            code = str(external_id)

        with transaction.atomic():
            # upsert по external_id
            obj = Product.objects.filter(external_id=external_id).first()

            if obj is None:
                # slug может конфликтовать — делаем безопасный
                final_slug = incoming_slug or slugify(code)[:512] or "product"
                if Product.objects.filter(slug=final_slug).exists():
                    final_slug = _safe_unique_slug(Product, final_slug, max_len=512)

                # code тоже может конфликтовать со “старыми” товарами на сайте
                final_code = code
                if Product.objects.filter(code=final_code).exists():
                    # если код конфликтует — делаем fallback на external_id
                    final_code = str(external_id)

                obj = Product.objects.create(
                    external_id=external_id,
                    code=final_code,
                    name=name or final_code,
                    slug=final_slug,
                    category=category,
                    description=description,
                    price=price,
                    old_price=old_price,
                    wholesale_price=wholesale_price,
                    discount=discount,
                    promotion=promotion,
                    quantity=quantity,
                    is_active=is_active,
                    is_available=is_available,
                )
                created = True
            else:
                # обновление
                obj.name = name or obj.name
                obj.description = description

                # обновим code только если не конфликтует
                if code and code != obj.code and not Product.objects.exclude(pk=obj.pk).filter(code=code).exists():
                    obj.code = code

                # обновим slug только если прилетел и не конфликтует
                if incoming_slug and incoming_slug != obj.slug and not Product.objects.exclude(pk=obj.pk).filter(slug=incoming_slug).exists():
                    obj.slug = incoming_slug

                obj.category = category or obj.category
                obj.price = price
                obj.old_price = old_price
                obj.wholesale_price = wholesale_price
                obj.discount = discount
                obj.promotion = promotion
                obj.quantity = quantity
                obj.is_active = is_active
                obj.is_available = is_available
                obj.save()
                created = False

        return Response({"ok": True, "created": created})