from django.db import models
from imagekit.models import ProcessedImageField


class StaticPage(models.Model):
    class PageKey(models.TextChoices):
        ABOUT = "about", "О компании"
        CONTACTS = "contacts", "Контакты"
        CUSTOM = "custom", "Произвольная страница"

    key = models.CharField(
        max_length=50,
        choices=PageKey.choices,
        default=PageKey.CUSTOM,
        unique=True,
        verbose_name="Тип страницы",
    )
    title = models.CharField(
        max_length=255,
        verbose_name="Заголовок",
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        verbose_name="SLUG",
    )
    # новый логотип
    logo = ProcessedImageField(
        upload_to="pages/logos/",
        verbose_name="Логотип",
        blank=True,
        null=True,
        options={"quality": 100},
    )

    content = models.TextField(
        verbose_name="Содержимое",
        blank=True,
    )
    address = models.CharField(
        max_length=255,
        verbose_name="Адрес",
        blank=True,
    )
    phone = models.CharField(
        max_length=100,
        verbose_name="Телефон",
        blank=True,
    )
    email = models.EmailField(
        verbose_name="Email",
        blank=True,
    )
    map_iframe = models.TextField(
        verbose_name="Карта (iframe / ссылка)",
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна?",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Статическая страница"
        verbose_name_plural = "Статические страницы"
        ordering = ("key",)

    def __str__(self) -> str:
        return self.title



class News(models.Model):
    """
    Отдельная модель для новостей / статей.
    """

    title = models.CharField(
        max_length=255,
        verbose_name="Заголовок",
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        verbose_name="SLUG",
    )
    preview_text = models.TextField(
        verbose_name="Краткое описание",
        blank=True,
    )
    content = models.TextField(
        verbose_name="Текст новости",
    )
    image = ProcessedImageField(
        upload_to="news/",
        verbose_name="Изображение",
        blank=True,
        null=True,
        options={"quality": 90},
    )
    is_published = models.BooleanField(
        default=True,
        verbose_name="Опубликована?",
    )
    published_at = models.DateTimeField(
        verbose_name="Дата публикации",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Новость"
        verbose_name_plural = "Новости"
        ordering = ("-published_at", "-created_at")

    def __str__(self) -> str:
        return self.title