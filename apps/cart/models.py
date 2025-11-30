# models.py
from django.db import models
from django.conf import settings
import uuid


class Order(models.Model):
    class PersonType(models.TextChoices):
        INDIVIDUAL = "individual", "Физическое лицо"
        LEGAL = "legal", "Юридическое лицо"

    class DeliveryType(models.TextChoices):
        PICKUP = "pickup", "Самовывоз"
        COURIER = "courier", "Курьерская доставка"

    class Status(models.TextChoices):
        NEW = "new", "Новый"
        CONFIRMED = "confirmed", "Подтверждён"
        PAID = "paid", "Оплачен"
        CANCELLED = "cancelled", "Отменён"

    # гость/авторизованный
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Пользователь",
    )

    external_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Номер заказа (публичный)",
    )

    # блок «Оформление заказа»
    first_name = models.CharField(
        max_length=150,
        verbose_name="Имя",
        blank=True,
    )
    last_name = models.CharField(
        max_length=150,
        verbose_name="Фамилия",
        blank=True,
    )
    phone = models.CharField(
        max_length=50,
        verbose_name="Телефон",
    )
    email = models.EmailField(
        max_length=254,
        verbose_name="Email",
        blank=True,
    )
    extra_phone = models.CharField(
        max_length=50,
        verbose_name="Доп. телефон",
        blank=True,
    )

    # блок «Я»
    person_type = models.CharField(
        max_length=20,
        choices=PersonType.choices,
        default=PersonType.INDIVIDUAL,
        verbose_name="Тип лица",
    )

    # блок «Доставка»
    delivery_type = models.CharField(
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.PICKUP,
        verbose_name="Тип доставки",
    )
    street = models.CharField(
        max_length=255,
        verbose_name="Улица",
        blank=True,
    )
    house = models.CharField(
        max_length=50,
        verbose_name="Дом / офис",
        blank=True,
    )
    flat = models.CharField(
        max_length=50,
        verbose_name="Квартира / кабинет",
        blank=True,
    )
    delivery_comment = models.TextField(
        verbose_name="Комментарий к доставке",
        blank=True,
    )

    # суммы
    total_qty = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество товаров",
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Сумма заказа",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        verbose_name="Статус",
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
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Заказ #{self.id} ({self.phone})"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Заказ",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        verbose_name="Товар",
    )

    # снапшоты, чтобы не поехали, если товар изменится
    product_name = models.CharField(
        max_length=512,
        verbose_name="Название товара",
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Цена за единицу",
    )
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name="Количество",
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Сумма по позиции",
    )

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"

    def __str__(self) -> str:
        return f"{self.product_name} x {self.quantity}"
