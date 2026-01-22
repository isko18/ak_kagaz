import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings

from .serializers import ProductSerializer

logger = logging.getLogger(__name__)


def _sign_body(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def send_product_webhook_data(data, event: str) -> bool:
    """
    Отправляет вебхук с уже готовым JSON data (нужно для delete: сериализация ДО удаления).

    Payload:
      {"event": "...", "data": {...}}

    Заголовок:
      X-CRM-Signature: sha256=<hex>, где <hex> = HMAC-SHA256(request.body, SITE_WEBHOOK_SECRET)
    """
    url = getattr(settings, "NURCRM_PRODUCTS_WEBHOOK_URL", "")
    if not url:
        logger.warning("NURCRM_PRODUCTS_WEBHOOK_URL not configured; skip product webhook (%s)", event)
        return False

    secret = getattr(settings, "SITE_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning("SITE_WEBHOOK_SECRET not configured; skip product webhook (%s)", event)
        return False

    payload = {"event": event, "data": data}
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = _sign_body(body, secret)

    try:
        resp = requests.post(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-CRM-Signature": signature,
            },
            timeout=8,
        )
    except Exception:
        logger.exception("Failed to send product webhook (%s) to %s", event, url)
        return False

    if resp.status_code >= 400:
        logger.warning(
            "Product webhook (%s) failed: status=%s url=%s body=%s",
            event,
            resp.status_code,
            url,
            (resp.text or "")[:500],
        )
        return False

    return True


def send_product_webhook(product, event: str) -> bool:
    """
    Сериализует товар и отправляет вебхук (create/update).
    Для delete используй send_product_webhook_data(...) с заранее подготовленным data.
    """
    if getattr(product, "external_id", None) is None:
        logger.warning("Product has no external_id; skip product webhook (%s) product_id=%s", event, product.pk)
        return False

    data = ProductSerializer(product).data
    return send_product_webhook_data(data, event)

