"""Recompress embedded photos without changing image dimensions or document XML."""
from __future__ import annotations

import copy
import io
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

RASTER = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tif', '.tiff'}


def optimize_image(data, quality):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if getattr(image, 'n_frames', 1) > 1:
                return data
            fmt = image.format
            buf = io.BytesIO()
            options = {k: image.info[k] for k in ('exif', 'icc_profile') if image.info.get(k)}
            q = max(10, min(95, quality)) if isinstance(quality, int) else {'small':55, 'balanced':72, 'high':88}[quality]
            if fmt == 'JPEG':
                image.save(buf, 'JPEG', quality=q,
                           optimize=True, **options)
            elif fmt == 'PNG':
                if quality != 'high' and image.mode in {'RGB', 'RGBA'}:
                    image = image.convert('RGBA').quantize(colors=max(16, int(q/100*256)) if isinstance(quality, int) else 128 if quality == 'small' else 256,
                                                         method=Image.Quantize.FASTOCTREE)
                image.save(buf, 'PNG', optimize=True, compress_level=9, **options)
            elif fmt == 'WEBP':
                image.save(buf, 'WEBP', quality=q, **options)
            else:
                return data
            smaller = buf.getvalue()
            return smaller if len(smaller) < len(data) else data
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return data


def is_picture(name):
    value = name.casefold().replace('\\', '/')
    return (value.startswith(('bindata/', 'word/media/', 'ppt/media/', 'xl/media/'))
            and PurePosixPath(value).suffix in RASTER | {'.emf', '.wmf', '.svg'})


def package(source, destination, quality, extract=False):
    count = 0
    with zipfile.ZipFile(source) as original:
        if original.testzip() is not None:
            raise ValueError('문서 내부 파일이 손상되어 있어요.')
        if any(i.flag_bits & 1 for i in original.infolist()):
            raise ValueError('암호화된 문서는 사진을 처리할 수 없어요.')
        if extract:
            for info in original.infolist():
                if is_picture(info.filename) and not info.is_dir():
                    count += 1
                    ext = PurePosixPath(info.filename).suffix.lower()
                    with original.open(info) as stream, (destination/f'사진_{count:03d}{ext}').open('wb') as output:
                        shutil.copyfileobj(stream, output)
            if not count:
                raise ValueError('문서에 저장된 사진이 없어요. 연결된 외부 사진은 포함되지 않아요.')
            return count
        with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as result:
            result.comment = original.comment
            for info in original.infolist():
                updated = copy.copy(info)
                if info.filename != 'mimetype':
                    updated.compress_type = zipfile.ZIP_DEFLATED
                if is_picture(info.filename) and info.file_size <= 128*1024*1024:
                    data = original.read(info)
                    smaller = optimize_image(data, quality)
                    count += int(smaller != data)
                    result.writestr(updated, smaller)
                else:
                    with original.open(info) as stream, result.open(updated, 'w') as output:
                        shutil.copyfileobj(stream, output)
    return count


def pdf_images(source, destination, quality, extract=False):
    import pymupdf
    count = 0
    with pymupdf.open(source) as pdf:
        if pdf.needs_pass:
            raise ValueError('암호가 걸린 PDF예요. 암호를 해제한 사본을 선택해 주세요.')
        seen = set()
        for page in pdf:
            for image in page.get_images(full=True):
                xref, mask = image[:2]
                if xref in seen:
                    continue
                seen.add(xref)
                data = pdf.extract_image(xref)
                if not data:
                    continue
                if extract:
                    count += 1
                    if mask:
                        pix = pymupdf.Pixmap(pymupdf.Pixmap(pdf, xref), pymupdf.Pixmap(pdf, mask))
                        pix.save(str(destination/f'사진_{count:03d}.png'))
                    else:
                        (destination/f'사진_{count:03d}.{data["ext"]}').write_bytes(data['image'])
                elif not mask:
                    smaller = optimize_image(data['image'], quality)
                    if smaller != data['image']:
                        page.replace_image(xref, stream=smaller)
                        count += 1
        if extract:
            if not count:
                raise ValueError('PDF 안에 꺼낼 사진이 없어요. 페이지 전체는 PNG 변환을 사용해 주세요.')
        else:
            pdf.save(destination, garbage=4, deflate=True)
    return count
