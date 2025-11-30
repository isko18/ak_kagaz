# views.py (файл твоего приложения с страницами/новостями)
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import StaticPage, News
from .serializers import (
    StaticPageSerializer,
    NewsListSerializer,
    NewsDetailSerializer,
)


class StaticPageViewSet(ReadOnlyModelViewSet):
    """
    Статические страницы (О компании, Контакты и т.д.)
    GET /pages/           -> список всех активных страниц
    GET /pages/{slug}/    -> страница по slug (about, contacts, ...)
    """

    queryset = StaticPage.objects.filter(is_active=True)
    serializer_class = StaticPageSerializer
    lookup_field = "slug"
    lookup_url_kwarg = "slug"
    filter_backends = [SearchFilter]
    search_fields = ("title", "slug", "key")


class NewsViewSet(ReadOnlyModelViewSet):
    """
    Новости
    GET /news/          -> список новостей (лайт)
    GET /news/{slug}/   -> детальная новость
    """

    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ("title", "slug", "preview_text", "content")
    ordering_fields = ("published_at", "created_at", "title")
    ordering = ("-published_at", "-created_at")
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self):
        return (
            News.objects.filter(is_published=True)
            .order_by("-published_at", "-created_at")
        )

    def get_serializer_class(self):
        if getattr(self, "action", None) == "list":
            return NewsListSerializer
        return NewsDetailSerializer
