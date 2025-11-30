from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
import os
import string
import random

def get_product_upload_path(instance, filename):
    return os.path.join(
        'products',
        str(instance.product_id),
        filename
    )
    
def get_random_string(length):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))


def rename_upload_file(image, filename=None):
    new_img_obj = Image.open(image)

    name, ext = os.path.splitext(image.name)

    if ext in ['.jpg', '.JPG', '.jpeg', '.JPEG']:
        ext = 'JPEG'
        new_img_obj = new_img_obj.convert('RGB')
    else:
        ext = ext.replace('.', '')

    title = '{name}.{ext}'.format(name=get_random_string(15),
                                  ext=ext) if not filename else '{name}.{ext}'.format(name=filename, ext=ext)

    new_img_bytes = BytesIO()
    new_img_obj.save(new_img_bytes, format=str(ext))

    image.delete(save=False)
    image.save(
        title,
        content=ContentFile(new_img_bytes.getvalue()),
        save=False
    )