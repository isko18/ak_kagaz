# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ProductViewSet, CategoryViewSet, CRMProductsWebhookAPIView

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")
router.register(r"categories", CategoryViewSet, basename="category")

urlpatterns = [
    path("", include(router.urls)),
    path("integrations/crm/products/", CRMProductsWebhookAPIView.as_view(), name="crm_products_webhook"),
]
