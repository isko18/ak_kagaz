from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.conf import settings
from django.views.generic import TemplateView

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from apps.catalog.views import CRMProductsWebhookAPIView

schema_view = get_schema_view(
    openapi.Info(
        title="Ak-Kagaz API",
        default_version="v1",
        description="API для проекта Ak-Kagaz",
        terms_of_service="#",
        contact=openapi.Contact(email="support@Ak-Kagaz.com"),
        license=openapi.License(name="Ak-Kagaz License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # ===== API строго тут =====
    path("api/main/", include("apps.main.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/cart/", include("apps.cart.urls")),

    # ===== integrations (aliases) =====
    # Некоторые CRM/провайдеры не умеют хранить длинный URL вида /api/catalog/...
    path("integrations/crm/products/", CRMProductsWebhookAPIView.as_view(), name="crm_products_webhook_root"),
    path("integrations/crm/products", CRMProductsWebhookAPIView.as_view(), name="crm_products_webhook_root_noslash"),

    # ===== docs =====
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),

    # главная (Vite dist index.html)
    path("", TemplateView.as_view(template_name="index.html")),
]

# ===== SPA fallback (React Router refresh) =====
urlpatterns += [
    re_path(r"^(?!api/|admin/|static/|media/).*$",
            TemplateView.as_view(template_name="index.html")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
