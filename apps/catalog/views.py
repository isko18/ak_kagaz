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
import os
from urllib.parse import urlparse, urljoin

import requests
from django.core.files.base import ContentFile

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

    # NurCRM: secret is SITE_WEBHOOK_SECRET (keep fallback for older name)
    secret = getattr(settings, "SITE_WEBHOOK_SECRET", "") or getattr(settings, "CRM_WEBHOOK_SECRET", "")
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


def _slug_or_hash(text: str, *, prefix: str, max_len: int = 255) -> str:
    """
    Django slugify() выкидывает кириллицу -> пустая строка.
    Чтобы категории не превращались в один и тот же slug "category", делаем стабильный slug через hash.
    """
    txt = (text or "").strip()
    s = slugify(txt)[:max_len]
    if s:
        return s
    digest = hashlib.md5(txt.encode("utf-8")).hexdigest()[:12] if txt else uuid.uuid4().hex[:12]
    return f"{prefix}-{digest}"[:max_len]


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


def _extract_image_urls(item: dict):
    images = item.get("images")
    if not images:
        return []

    urls = []
    if isinstance(images, list):
        for img in images:
            if isinstance(img, str) and img.strip():
                urls.append(img.strip())
                continue
            if isinstance(img, dict):
                url = (img.get("image_url") or img.get("image") or "").strip()
                if url:
                    urls.append(url)
    elif isinstance(images, dict):
        url = (images.get("image_url") or images.get("image") or "").strip()
        if url:
            urls.append(url)

    seen = set()
    result = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        result.append(u)
    return result


def _normalize_image_url(url: str) -> str:
    """
    NurCRM может прислать:
    - полный URL: https://app.nurcrm.kg/media/...
    - относительный путь: /media/...
    """
    u = (url or "").strip()
    if not u:
        return ""

    if u.startswith("//"):
        return "https:" + u

    if u.startswith("/"):
        base = getattr(settings, "CRM_MEDIA_BASE_URL", "") or ""
        if base:
            return urljoin(base.rstrip("/") + "/", u.lstrip("/"))
        return ""

    return u


def sync_product_images(product, images_payload):
    """
    images_payload (NurCRM):
      [
        {"image": "https://...", "image_url": "https://...", ...},
        ...
      ]

    Что делает:
    - Скачивает новые изображения и сохраняет в ProductImage (ProcessedImageField -> WEBP)
    - Не качает повторно (по source_url)
    - Удаляет изображения, которые пропали в CRM (только те, у которых source_url заполнен)
    """
    if not product or getattr(product, "pk", None) is None:
        return

    item = {"images": images_payload or []}
    incoming_urls = _extract_image_urls(item)
    max_bytes = int(getattr(settings, "CRM_WEBHOOK_MAX_IMAGE_BYTES", 10_000_000) or 10_000_000)

    stats = {"added": 0, "deleted": 0, "skipped": 0, "failed": 0}
    errors = []

    try:
        current_urls = set(
            ProductImage.objects
            .filter(product=product)
            .exclude(source_url="")
            .values_list("source_url", flat=True)
        )
    except Exception:
        logger.exception("CRM image sync failed to load existing images: product_id=%s", product.pk)
        return {"added": 0, "deleted": 0, "skipped": 0, "failed": 1}, [{"error": "db_error"}]
    incoming_set = set(incoming_urls)

    # delete removed (only CRM-synced images)
    to_delete = current_urls - incoming_set
    if to_delete:
        stats["deleted"] += len(to_delete)
        ProductImage.objects.filter(product=product, source_url__in=list(to_delete)).delete()

    # add new
    for idx, url in enumerate(incoming_urls):
        url = _normalize_image_url(url)
        if not url:
            stats["failed"] += 1
            errors.append({"url": url, "error": "empty after normalize"})
            continue

        if url in current_urls:
            stats["skipped"] += 1
            continue
        if not (url.startswith("http://") or url.startswith("https://")):
            stats["failed"] += 1
            errors.append({"url": url, "error": "unsupported scheme"})
            continue
        try:
            resp = requests.get(
                url,
                timeout=12,
                stream=True,
                headers={"User-Agent": "Ak-KagazWebhook/1.0"},
            )
            if resp.status_code >= 400:
                logger.warning("CRM image download failed: status=%s url=%s", resp.status_code, url)
                stats["failed"] += 1
                errors.append({"url": url, "error": f"http {resp.status_code}"})
                continue

            content_type = (resp.headers.get("Content-Type") or "").lower()
            if content_type and not content_type.startswith("image/"):
                logger.warning("CRM image has non-image content-type: %s url=%s", content_type, url)
                stats["failed"] += 1
                errors.append({"url": url, "error": f"content-type {content_type}"})
                continue

            content_length = resp.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        logger.warning("CRM image too large: bytes=%s url=%s", content_length, url)
                        stats["failed"] += 1
                        errors.append({"url": url, "error": "too large"})
                        continue
                except Exception:
                    pass

            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    logger.warning("CRM image exceeded max bytes while streaming: url=%s", url)
                    stats["failed"] += 1
                    errors.append({"url": url, "error": "too large"})
                    chunks = None
                    break
                chunks.append(chunk)
            if chunks is None:
                continue

            filename = _filename_from_url(url, fallback_name=f"{product.external_id or product.pk}-{idx}.img")
            pi = ProductImage(product=product, source_url=url)
            pi.image.save(filename, ContentFile(b"".join(chunks)), save=True)
            stats["added"] += 1
        except Exception as e:
            logger.exception("CRM image sync failed: url=%s product_id=%s", url, product.pk)
            stats["failed"] += 1
            errors.append({"url": url, "error": f"exception: {type(e).__name__}"})

    logger.info(
        "CRM image sync done: product_id=%s external_id=%s urls=%s added=%s deleted=%s skipped=%s failed=%s",
        product.pk,
        getattr(product, "external_id", None),
        len(incoming_urls),
        stats["added"],
        stats["deleted"],
        stats["skipped"],
        stats["failed"],
    )
    if errors:
        logger.warning("CRM image sync errors (first): product_id=%s errors=%s", product.pk, errors[:3])

    return stats, errors[:10]


def _filename_from_url(url: str, fallback_name: str):
    try:
        path = urlparse(url).path or ""
    except Exception:
        path = ""

    base = os.path.basename(path).strip() or fallback_name
    base = base.replace("\\", "_").replace("/", "_").replace("..", ".")
    if len(base) > 120:
        base = base[-120:]
    return base


def _upsert_product_from_crm_item(item):
    external_id_raw = item.get("id") or item.get("product_id") or item.get("external_id")
    external_id = _to_uuid(external_id_raw)
    if not external_id:
        raise ValueError("Invalid or missing product id (id/product_id/external_id must be UUID)")

    # 1) Категория (если прилетает)
    category_obj = item.get("category")
    category = None
    if isinstance(category_obj, dict):
        c_slug_raw = (category_obj.get("slug") or "").strip()
        c_name = (category_obj.get("name") or "").strip()
        c_slug = slugify(c_slug_raw)[:255] if c_slug_raw else ""
        if not c_slug and c_name:
            c_slug = _slug_or_hash(c_name, prefix="category", max_len=255)
        if not c_slug and c_slug_raw:
            c_slug = _slug_or_hash(c_slug_raw, prefix="category", max_len=255)

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
        c_slug = _slug_or_hash(c_name, prefix="category", max_len=255)
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

    webhook_update_quantity = bool(getattr(settings, "CRM_WEBHOOK_UPDATE_QUANTITY", True))

    with transaction.atomic():
        obj = Product.objects.filter(external_id=external_id).first()

        if obj is None:
            final_slug = incoming_slug or slugify(code)[:512] or "product"
            if Product.objects.filter(slug=final_slug).exists():
                final_slug = _safe_unique_slug(Product, final_slug, max_len=512)

            final_code = code
            if Product.objects.filter(code=final_code).exists():
                final_code = str(external_id)

            obj = Product.objects.create(
                external_id=external_id,
                code=final_code,
                name=name or final_code,
                slug=final_slug,
                category=category,
                description=description,
                price=price,
                discount=discount,
                promotion=promotion,
                quantity=quantity if webhook_update_quantity else 0,
                is_active=is_active,
                is_available=is_available,
            )
            created = True
            saved = True
        else:
            changed = False

            if name and name != obj.name:
                obj.name = name
                changed = True

            if description != obj.description:
                obj.description = description
                changed = True

            if code and code != obj.code and not Product.objects.exclude(pk=obj.pk).filter(code=code).exists():
                obj.code = code
                changed = True

            if incoming_slug and incoming_slug != obj.slug and not Product.objects.exclude(pk=obj.pk).filter(slug=incoming_slug).exists():
                obj.slug = incoming_slug
                changed = True

            if category and category != obj.category:
                obj.category = category
                changed = True

            if price != obj.price:
                obj.price = price
                changed = True

            if discount != obj.discount:
                obj.discount = discount
                changed = True

            if promotion != obj.promotion:
                obj.promotion = promotion
                changed = True

            if webhook_update_quantity and quantity != obj.quantity:
                obj.quantity = quantity
                changed = True

            if is_active != obj.is_active:
                obj.is_active = is_active
                changed = True

            if is_available != obj.is_available:
                obj.is_available = is_available
                changed = True

            if changed:
                obj.save()
                saved = True
            else:
                saved = False

            created = False

    image_stats = None
    image_errors = []
    if bool(getattr(settings, "CRM_WEBHOOK_SYNC_IMAGES", True)):
        images_payload = item.get("images") or []
        if images_payload:
            image_stats, image_errors = sync_product_images(obj, images_payload)

    return external_id, created, saved, image_stats, image_errors


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

        event = payload.get("event") if isinstance(payload, dict) else None
        received_images_len = None
        received_images_first = None
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            imgs = payload["data"].get("images") or []
            if isinstance(imgs, list):
                received_images_len = len(imgs)
                if imgs and isinstance(imgs[0], dict):
                    received_images_first = (imgs[0].get("image_url") or imgs[0].get("image") or None)

        logger.info(
            "CRM webhook received: path=%s event=%s content_type=%s body_len=%s images_len=%s",
            request.path,
            event,
            request.content_type,
            len(raw),
            received_images_len,
        )

        # NurCRM delete event: {"event":"product.deleted","data":{...}}
        if event == "product.deleted" and isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            item = payload["data"]
            external_id = _to_uuid(item.get("id") or item.get("product_id") or item.get("external_id"))
            if not external_id:
                return Response({"detail": "Invalid or missing product id"}, status=400)

            obj = Product.objects.filter(external_id=external_id).first()
            if not obj:
                return Response({"ok": True, "deleted": False, "reason": "not_found", "external_id": str(external_id)})

            pk = obj.pk
            obj.delete()
            logger.info("CRM webhook deleted product: external_id=%s product_id=%s", external_id, pk)
            return Response({"ok": True, "deleted": True, "external_id": str(external_id)})

        items = _extract_items(payload)
        if not items:
            logger.warning(
                "CRM webhook payload has no items: path=%s type=%s",
                request.path,
                type(payload).__name__,
            )
            return Response(
                {"detail": "No items found in payload", "event": event, "received_images_len": received_images_len},
                status=400,
            )

        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []
        images = {"added": 0, "deleted": 0, "skipped": 0, "failed": 0}
        image_errors = []

        for idx, item in enumerate(items):
            try:
                external_id, created, saved, image_stats, per_item_image_errors = _upsert_product_from_crm_item(item)
                if created:
                    created_count += 1
                elif saved:
                    updated_count += 1
                else:
                    skipped_count += 1

                if image_stats:
                    for k in images.keys():
                        images[k] += int(image_stats.get(k, 0) or 0)
                if per_item_image_errors and len(image_errors) < 20:
                    image_errors.extend(per_item_image_errors[: (20 - len(image_errors))])

                logger.info(
                    "CRM webhook processed product: path=%s external_id=%s created=%s saved=%s",
                    request.path,
                    external_id,
                    created,
                    saved,
                )
                if per_item_image_errors:
                    logger.warning(
                        "CRM webhook image errors: path=%s external_id=%s errors=%s",
                        request.path,
                        external_id,
                        per_item_image_errors[:3],
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
                "skipped": skipped_count,
                "errors": errors,
                "images": images,
                "image_errors": image_errors,
                "event": event,
                "received_images_len": received_images_len,
                "received_images_first": received_images_first,
            },
            status=status_code,
        )

    def get(self, request, *args, **kwargs):
        return Response({"ok": True})
