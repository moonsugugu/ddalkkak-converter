"""Local image readers shared by conversion, editing, scanning and previews."""
import io
import re
import subprocess
from pathlib import Path
from PIL import Image, ImageOps

MAX_PIXELS = 40_000_000


def open_image(path):
    path = Path(path)
    ext = path.suffix.lower()
    if ext in {'.heic', '.heif'}:
        from media import executable, probe
        info = probe(path)
        streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
        if not streams or max(int(s.get('width', 0))*int(s.get('height', 0)) for s in streams) > MAX_PIXELS:
            raise ValueError('HEIC 사진을 읽지 못했거나 사진이 너무 커요. 최대 4천만 화소를 지원해요.')
        process = subprocess.run([executable(), '-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe',
                                  '-i', str(path.resolve()), '-frames:v', '1', '-f', 'image2pipe',
                                  '-vcodec', 'png', 'pipe:1'], capture_output=True, timeout=60,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        if process.returncode or not process.stdout:
            raise ValueError('HEIC의 대표 사진을 읽지 못했어요. 원본을 확인해 주세요.')
        return Image.open(io.BytesIO(process.stdout))
    if ext == '.svg':
        import xml.etree.ElementTree as ET
        import pymupdf
        data = path.read_bytes()
        if len(data) > 8*1024*1024 or re.search(br'<!DOCTYPE|<!ENTITY', data, re.I):
            raise ValueError('SVG 크기 또는 외부 정의를 확인해 주세요.')
        root = ET.fromstring(data)
        for node in root.iter():
            for name, value in node.attrib.items():
                if name.split('}')[-1] == 'href' and not value.startswith(('#', 'data:image/')):
                    raise ValueError('외부 파일을 참조하는 SVG는 지원하지 않아요. 이미지를 포함해 저장해 주세요.')
                if re.search(r'url\(\s*[\"\']?(?!#|data:)', value, re.I):
                    raise ValueError('외부 자료를 참조하는 SVG는 지원하지 않아요.')
            if node.tag.split('}')[-1] in {'script', 'foreignObject', 'style'}:
                raise ValueError('스크립트·외부 스타일이 없는 SVG를 선택해 주세요.')
        with pymupdf.open(stream=data, filetype='svg') as doc:
            page = doc[0]
            if page.rect.width*page.rect.height > MAX_PIXELS:
                raise ValueError('SVG가 너무 커요. 크기를 줄여 주세요.')
            return Image.open(io.BytesIO(page.get_pixmap(alpha=True).tobytes('png')))
    image = Image.open(path)
    if image.width*image.height > MAX_PIXELS:
        image.close()
        raise ValueError('최대 4천만 화소 사진을 지원해요. 사진 크기를 줄여 주세요.')
    return image


def oriented(path):
    with open_image(path) as image:
        return ImageOps.exif_transpose(image).convert('RGBA')


def save_image(image, destination, quality='balanced'):
    destination = Path(destination)
    ext = destination.suffix.lower()
    # Rebuild pixels, so EXIF, GPS, XMP and source thumbnails are not copied.
    clean = Image.new('RGBA', image.size)
    clean.paste(image.convert('RGBA'))
    if ext in {'.jpg', '.jpeg', '.bmp'}:
        rgb = Image.new('RGB', clean.size, 'white')
        rgb.paste(clean, mask=clean.getchannel('A'))
        clean = rgb
    options = {'quality': {'small':65, 'balanced':86, 'high':96}[quality]} if ext in {'.jpg','.jpeg','.webp','.avif'} else {}
    clean.save(destination, **options)
