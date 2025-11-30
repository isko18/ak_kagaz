# views.py
import logging

import requests
from django.conf import settings
from rest_framework.generics import CreateAPIView

from .models import Order
from .serializers import OrderSerializer
from .utils import send_order_to_telegram

logger = logging.getLogger(__name__)



class OrderCreateView(CreateAPIView):
    """
    POST /orders/
    Создаёт заказ из корзины (гость или авторизованный), потом шлёт в Telegram.
    """

    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def perform_create(self, serializer):
        order = serializer.save()
        send_order_to_telegram(order)
