from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import io

def convert_to_sketch(image_bytes):
    """Карандашный рисунок (улучшенный)"""
    img = Image.open(io.BytesIO(image_bytes)).convert('L')
    # Инвертируем
    inverted = ImageOps.invert(img)
    # Размытие
    blurred = inverted.filter(ImageFilter.GaussianBlur(radius=5))
    # Смешиваем
    final = ImageOps.invert(blurred)
    final_rgb = final.convert('RGB')
    # Немного повышаем контраст
    enhancer = ImageEnhance.Contrast(final_rgb)
    final_rgb = enhancer.enhance(1.2)
    output = io.BytesIO()
    final_rgb.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_anime(image_bytes):
    """Аниме-стиль: яркие цвета, резкость, насыщенность"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    # Повышаем контраст
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    # Повышаем насыщенность
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.4)
    # Резкость
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)
    # Лёгкое свечение (размытие и наложение)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=1))
    img = Image.blend(img, blurred, 0.2)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_sepia(image_bytes):
    """Сепия (усиленная)"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    sepia = (0.393, 0.769, 0.189, 0,
             0.349, 0.686, 0.168, 0,
             0.272, 0.534, 0.131, 0)
    img = img.convert('RGB', matrix=sepia)
    # Немного добавляем яркости
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.1)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_hard_rock(image_bytes):
    """Хард-рок: высокий контраст, резкость, зернистость"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.2)
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(3.5)
    # Добавляем лёгкое зерно (шум)
    # Создаём шумовую маску
    import random
    noise = Image.new('RGB', img.size, (0,0,0))
    noise_pixels = noise.load()
    for x in range(img.size[0]):
        for y in range(img.size[1]):
            r = random.randint(0, 20)
            noise_pixels[x,y] = (r, r, r)
    img = Image.blend(img, noise, 0.1)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_pixel(image_bytes, pixel_size=15):
    """Пикселизация (более выраженная)"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    img_small = img.resize((img.width // pixel_size, img.height // pixel_size), Image.NEAREST)
    img_pixel = img_small.resize(img.size, Image.NEAREST)
    output = io.BytesIO()
    img_pixel.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_neon(image_bytes):
    """Неоновые цвета: сильная насыщенность, контраст, свечение"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(3.0)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.8)
    # Добавляем свечение
    blurred = img.filter(ImageFilter.GaussianBlur(radius=3))
    img = Image.blend(img, blurred, 0.4)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_oil(image_bytes):
    """Масляная живопись (через ModeFilter и шум)"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    # Увеличиваем размер для лучшего эффекта
    img = img.resize((img.width*2, img.height*2), Image.BICUBIC)
    # Применяем ModeFilter
    img = img.filter(ImageFilter.ModeFilter(size=7))
    # Возвращаем к исходному размеру
    img = img.resize((img.width//2, img.height//2), Image.BICUBIC)
    # Добавляем лёгкое размытие
    img = img.filter(ImageFilter.GaussianBlur(radius=1))
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_watercolor(image_bytes):
    """Акварель: мягкие цвета, пастель"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    # Размытие
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    # Уменьшаем насыщенность
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(0.7)
    # Повышаем яркость
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.1)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output

def convert_to_cartoon(image_bytes):
    """Мультяшный: яркие цвета, чёткие края, высокая резкость"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    # Сильное повышение контраста
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.2)
    # Сильное повышение цвета
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(2.2)
    # Резкость
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)
    # Выделение краёв (лайны)
    edges = img.filter(ImageFilter.FIND_EDGES)
    edges = edges.convert('L')
    edges = edges.point(lambda x: 0 if x < 100 else 255)
    # Накладываем края на исходное изображение
    img = Image.blend(img, edges.convert('RGB'), 0.2)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output
