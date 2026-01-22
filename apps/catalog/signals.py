import logging

from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Product
from .serializers import ProductSerializer
from .webhooks import send_product_webhook_data

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=Product)
def product_pre_delete_send_webhook(sender, instance: Product, using, **kwargs):
    """
    Для delete нужно сериализовать ДО удаления и отправить после commit:
      {"event":"product.deleted","data":{...}}
    """
    if instance.external_id is None:
        return

    data = ProductSerializer(instance).data

    def _after_commit():
        ok = send_product_webhook_data(data, event="product.deleted")
        if not ok:
            logger.warning("Failed to send product.deleted webhook: product_id=%s external_id=%s", instance.pk, instance.external_id)

    transaction.on_commit(_after_commit, using=using)

