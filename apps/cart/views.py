# views.py
import logging

import requests
from django.conf import settings
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

from .models import Order
from .serializers import OrderSerializer
from .utils import send_order_to_telegram

logger = logging.getLogger(__name__)



class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return  # отключаем CSRF для API


class OrderCreateView(CreateAPIView):
    """
    POST /orders/
    Создаёт заказ (гость или авторизованный), потом шлёт в Telegram.
    """
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    permission_classes = [AllowAny]
    authentication_classes = [CsrfExemptSessionAuthentication, BasicAuthentication]

    def perform_create(self, serializer):
        order = serializer.save()
        send_order_to_telegram(order)
