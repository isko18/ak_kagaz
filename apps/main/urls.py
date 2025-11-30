# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import StaticPageViewSet, NewsViewSet

router = DefaultRouter()
router.register(r"pages", StaticPageViewSet, basename="staticpage")
router.register(r"news", NewsViewSet, basename="news")

urlpatterns = [
    path("", include(router.urls)),
]
