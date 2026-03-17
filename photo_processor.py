from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import io

def convert_to_sketch(image_bytes):
    """Превращает фото в карандашный рисунок."""
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
    """Имитация аниме-стиля: резкость, насыщенность."""
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
    """Эффект сепии."""
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
    """Хард-рок: высокий контраст, резкость."""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(3.0)
    output = io.BytesIO()
    img.save(output, format='JPEG')
    output.seek(0)
    return output
