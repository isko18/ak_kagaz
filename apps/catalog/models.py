from django.db import models
from django.core.validators import MaxValueValidator
from mptt.models import MPTTModel, TreeForeignKey
from django.template.defaultfilters import truncatechars  # 👈 добавь этот импорт
from apps.utils import get_product_upload_path, rename_upload_file
from imagekit.models import ProcessedImageField


class Category(MPTTModel):
    name = models.CharField(
        max_length=255,
        verbose_name="Название категории",
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        verbose_name="SLUG",
    )
    parent = TreeForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Родительская категория",
    )
    image = ProcessedImageField(
        upload_to="categories/",
        verbose_name="Изображение",
        blank=True,
        null=True,
        options={"quality": 100},
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

    class MPTTMeta:
        order_insertion_by = ("name",)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ("tree_id", "lft")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if self.image:
            rename_upload_file(self.image)
        super().save(*args, **kwargs)


class Product(models.Model):
    code = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Код товара",
    )
    name = models.CharField(
        max_length=512,
        verbose_name="Название товара",
    )
    slug = models.SlugField(
        verbose_name="SLUG",
        unique=True,
        max_length=512,
    )

    category = TreeForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Категория",
    )

    description = models.TextField(
        verbose_name="Описание товара",
        blank=True,
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Цена",
    )
    old_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Старая цена",
    )
    wholesale_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Оптовая цена",
    )
    discount = models.PositiveIntegerField(
        default=0,
        verbose_name="Скидка (%)",
        validators=[MaxValueValidator(95)],
    )
    promotion = models.BooleanField(
        default=False,
        verbose_name="Акция",
    )
    quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество на складе",
    )
    is_active = models.BooleanField(
        verbose_name="Активный?",
        default=True,
    )
    is_available = models.BooleanField(
        verbose_name="Есть в наличии?",
        default=True,
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
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class ProductImage(models.Model):
    class Meta:
        verbose_name_plural = "Изображения"
        verbose_name = "Изображение"

    product = models.ForeignKey(
        to=Product,
        on_delete=models.CASCADE,
        verbose_name="Товар",
        related_name="images",
    )
    image = ProcessedImageField(
        upload_to=get_product_upload_path,
        verbose_name="Изображение",
        format="WEBP",
        options={"quality": 82},
    )

    def __str__(self) -> str:
        return self.image.name

    def save(self, *args, **kwargs):
        if self.image:
            rename_upload_file(self.image)
        super().save(*args, **kwargs)


# ====== НОВОЕ: справочник характеристик и значения для товаров ======

class CharacteristicsDict(models.Model):
    class Meta:
        verbose_name = "Описание характеристик"
        verbose_name_plural = "Описание характеристик"

    title = models.TextField(
        verbose_name="Название",
    )
    unit = models.CharField(
        max_length=255,
        verbose_name="Единица измерения",
        null=True,
        blank=True,
    )

    def __str__(self):
        return truncatechars(self.title, 30)


class Characteristics(models.Model):
    class Meta:
        verbose_name_plural = "Характеристики"
        verbose_name = "Характеристика"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name="Товар",
        related_name="characteristics",
    )
    key = models.ForeignKey(
        CharacteristicsDict,
        on_delete=models.CASCADE,
        verbose_name="Характеристика",
        related_name="values",
    )
    value = models.TextField(
        verbose_name="Значение",
    )

    def __str__(self):
        return self.key.title
