from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
import os
import string
import random


def get_product_upload_path(instance, filename):
    return os.path.join("products", str(instance.product_id), filename)


def get_random_string(length):
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))


def rename_upload_file(image, filename=None, *, quality=82, max_side=1600):
    """
    1) Переименовывает файл
    2) Конвертирует ВСЕ изображения в WEBP (сжатие)
    """
    img = Image.open(image)

    # resize (по желанию)
    w, h = img.size
    if max(w, h) > max_side:
        if w >= h:
            new_w = max_side
            new_h = int(h * (max_side / w))
        else:
            new_h = max_side
            new_w = int(w * (max_side / h))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    # WEBP: сохраняем с альфой если есть, иначе RGB
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA" if has_alpha else "RGB")

    ext = "webp"
    name = filename or get_random_string(15)
    title = f"{name}.{ext}"

    new_img_bytes = BytesIO()
    img.save(new_img_bytes, format="WEBP", quality=quality, method=6)
    new_img_bytes.seek(0)

    # удаляем старый файл и сохраняем новый webp
    image.delete(save=False)
    image.save(title, content=ContentFile(new_img_bytes.getvalue()), save=False)
