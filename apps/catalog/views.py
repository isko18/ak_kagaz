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
import logging
import uuid

from .models import Product, ProductImage, Category, Characteristics
from .serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
)

logger = logging.getLogger(__name__)


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


def _to_int(v, default=0):
    if v is None or v == "":
        return default
    try:
        # handles "0.00", 0, Decimal("0.00"), etc.
        return int(Decimal(str(v).replace(",", ".")))
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


def _to_uuid(v):
    if v is None or v == "":
        return None
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v))
    except Exception:
        return None


def _extract_items(payload):
    """
    Поддерживаем разные форматы:
    1) {"data": {...}} — точечный webhook
    2) {"results": [{...}, ...]} — массовая выгрузка/страница
    3) [{...}, ...] — список объектов
    4) {...} — объект товара
    """
    if not payload:
        return []

    if isinstance(payload, dict) and "data" in payload and isinstance(payload.get("data"), dict):
        return [payload["data"]]

    if isinstance(payload, dict) and "results" in payload and isinstance(payload.get("results"), list):
        return [x for x in payload["results"] if isinstance(x, dict)]

    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if isinstance(payload, dict):
        return [payload]

    return []


def _upsert_product_from_crm_item(item):
    external_id_raw = item.get("id") or item.get("product_id") or item.get("external_id")
    external_id = _to_uuid(external_id_raw)
    if not external_id:
        raise ValueError("Invalid or missing product id (id/product_id/external_id must be UUID)")

    # 1) Категория (если прилетает)
    category_obj = item.get("category")
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
            gen_slug = _safe_unique_slug(Category, slugify(c_name)[:255])
            category = Category.objects.create(name=c_name, slug=gen_slug, is_active=True)

    elif isinstance(category_obj, str) and category_obj.strip():
        c_name = category_obj.strip()
        c_slug = slugify(c_name)[:255] or "category"
        category, _ = Category.objects.get_or_create(
            slug=c_slug,
            defaults={"name": c_name, "is_active": True},
        )

    # 2) Поля товара (поддержка формата NurCRM)
    name = (item.get("name") or "").strip()
    code = (item.get("code") or "").strip()
    barcode = (item.get("barcode") or "").strip()
    description = item.get("description") or ""
    price = _to_decimal(item.get("price"), default=Decimal("0"))

    # NurCRM: discount_percent "0.00"
    discount = _to_int(item.get("discount") or item.get("discount_percent"), default=0)

    # NurCRM: quantity "0.00" (строка)
    quantity = _to_int(item.get("quantity"), default=0)

    promotion = bool(item.get("promotion") or False)
    is_active = bool(item.get("is_active") if item.get("is_active") is not None else True)
    is_available = bool(item.get("is_available") if item.get("is_available") is not None else True)

    incoming_slug = (item.get("slug") or "").strip()
    if not incoming_slug and name:
        incoming_slug = slugify(name)[:512]

    if not code:
        code = str(external_id)

    with transaction.atomic():
        obj = Product.objects.filter(external_id=external_id).first()

        if obj is None:
            final_slug = incoming_slug or slugify(code)[:512] or "product"
            if Product.objects.filter(slug=final_slug).exists():
                final_slug = _safe_unique_slug(Product, final_slug, max_len=512)

            final_code = code
            if Product.objects.filter(code=final_code).exists():
                final_code = str(external_id)

            Product.objects.create(
                external_id=external_id,
                code=final_code,
                name=name or final_code,
                slug=final_slug,
                category=category,
                description=description,
                price=price,
                old_price=None,
                wholesale_price=None,
                discount=discount,
                promotion=promotion,
                quantity=quantity,
                is_active=is_active,
                is_available=is_available,
            )
            created = True
        else:
            obj.name = name or obj.name
            obj.description = description

            if code and code != obj.code and not Product.objects.exclude(pk=obj.pk).filter(code=code).exists():
                obj.code = code

            if incoming_slug and incoming_slug != obj.slug and not Product.objects.exclude(pk=obj.pk).filter(slug=incoming_slug).exists():
                obj.slug = incoming_slug

            obj.category = category or obj.category
            obj.price = price
            obj.old_price = None
            obj.wholesale_price = None
            obj.discount = discount
            obj.promotion = promotion
            obj.quantity = quantity
            obj.is_active = is_active
            obj.is_available = is_available
            obj.save()
            created = False

    return external_id, created


class CRMProductsWebhookAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw = request.body or b""
        sig = request.headers.get("X-CRM-Signature", "")
        if not _verify_signature(raw, sig):
            logger.warning(
                "CRM webhook invalid signature: path=%s content_type=%s body_len=%s",
                request.path,
                request.content_type,
                len(raw),
            )
            return Response({"detail": "Invalid signature"}, status=401)

        try:
            payload = request.data or {}
        except Exception:
            logger.exception("CRM webhook failed to parse request body: path=%s", request.path)
            return Response({"detail": "Invalid payload"}, status=400)

        items = _extract_items(payload)
        if not items:
            logger.warning(
                "CRM webhook payload has no items: path=%s type=%s",
                request.path,
                type(payload).__name__,
            )
            return Response({"detail": "No items found in payload"}, status=400)

        created_count = 0
        updated_count = 0
        errors = []

        for idx, item in enumerate(items):
            try:
                external_id, created = _upsert_product_from_crm_item(item)
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                logger.info(
                    "CRM webhook processed product: path=%s external_id=%s created=%s",
                    request.path,
                    external_id,
                    created,
                )
            except Exception as e:
                logger.exception("CRM webhook failed to process item #%s: path=%s", idx, request.path)
                errors.append({"index": idx, "error": str(e)})

        status_code = 200 if not errors else 207  # Multi-Status
        return Response(
            {
                "ok": len(errors) == 0,
                "created": created_count,
                "updated": updated_count,
                "errors": errors,
            },
            status=status_code,
        )

    def get(self, request, *args, **kwargs):
        return Response({"ok": True})
