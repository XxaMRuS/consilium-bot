from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import io

# Существующие функции (sketch, anime, sepia, hardrock) остаются без изменений
def convert_to_sketch(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert('L')
    inverted = ImageOps.invert(img)
    blurred = inverted.filter(ImageFilter.GaussianBlur(radius=5))
    final = ImageOps.invert(blurred)
    final_rgb = final.convert('RGB')
    output = io.BytesIO()
    final_rgb.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_anime(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.3)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_sepia(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    sepia = (0.393, 0.769, 0.189, 0,
             0.349, 0.686, 0.168, 0,
             0.272, 0.534, 0.131, 0)
    img = img.convert('RGB', matrix=sepia)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_hard_rock(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(3.0)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

# === НОВЫЕ СТИЛИ ===

def convert_to_pixel(image_bytes, pixel_size=20):
    """Пикселизация (стиль Minecraft)"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    # Уменьшаем изображение
    img_small = img.resize((img.width // pixel_size, img.height // pixel_size), Image.NEAREST)
    # Растягиваем обратно с сохранением пикселей
    img_pixel = img_small.resize(img.size, Image.NEAREST)
    output = io.BytesIO()
    img_pixel.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_neon(image_bytes):
    """Неоновые цвета"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    # Повышаем насыщенность и контраст
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(2.5)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    # Добавляем свечение (размытие + наложение)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=3))
    img = Image.blend(img, blurred, 0.3)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_oil(image_bytes):
    """Имитация масляной живописи"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    # Применяем фильтр для масляного эффекта
    img = img.filter(ImageFilter.ModeFilter(size=5))
    # Добавляем зернистость
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.5)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_watercolor(image_bytes):
    """Акварельный эффект"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    # Размытие для акварельного эффекта
    img = img.filter(ImageFilter.GaussianBlur(radius=1))
    # Повышаем яркость
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.1)
    # Уменьшаем насыщенность (акварель более пастельная)
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(0.8)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_cartoon(image_bytes):
    """Мультяшный стиль (ещё ярче и резче, чем аниме)"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    # Сильное повышение контраста и цвета
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(2.0)
    # Резкость
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)
    # Добавляем контур (выделение краёв)
    edges = img.filter(ImageFilter.FIND_EDGES)
    img = Image.blend(img, edges, 0.2)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output
