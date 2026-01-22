from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.catalog'
    verbose_name='Каталог'

    def ready(self):
        # ensure signals are registered
        from . import signals  # noqa: F401
