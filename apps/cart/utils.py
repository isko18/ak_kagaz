from django.conf import settings
from .models import Order
import logging
import requests

logger = logging.getLogger(__name__)

def send_order_to_telegram(order: Order):
    """
    Отправляет заказ в Telegram-бота.
    Нужны TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в settings.
    """
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", None)

    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not configured")
        return

    lines = []
    lines.append(f"🛒 Новый заказ #{order.id}")
    lines.append(f"Номер: {order.external_id}")
    lines.append("")
    lines.append(f"Имя: {order.first_name} {order.last_name}".strip())
    lines.append(f"Телефон: {order.phone}")
    if order.email:
        lines.append(f"Email: {order.email}")
    if order.extra_phone:
        lines.append(f"Доп. телефон: {order.extra_phone}")
    lines.append("")
    lines.append(f"Тип клиента: {order.get_person_type_display()}")
    lines.append(f"Доставка: {order.get_delivery_type_display()}")

    if order.delivery_type == order.DeliveryType.COURIER:
        addr_parts = [order.street, order.house, order.flat]
        addr = ", ".join([p for p in addr_parts if p])
        if addr:
            lines.append(f"Адрес: {addr}")
        if order.delivery_comment:
            lines.append(f"Комментарий: {order.delivery_comment}")

    lines.append("")
    lines.append("Товары:")
    for item in order.items.all():
        lines.append(
            f"- {item.product_name} x{item.quantity} = {item.line_total} с"
        )

    lines.append("")
    lines.append(f"Итого: {order.total_qty} шт. на сумму {order.total_amount} с")

    text = "\n".join(lines)

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=5,
        )
    except Exception as e:
        logger.exception("Failed to send order to Telegram: %s", e)
