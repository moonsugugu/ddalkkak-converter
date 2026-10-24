"""Advanced local jobs share the existing safe Office converters and atomic publishing."""
from __future__ import annotations
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps, ImageSequence

LABELS = {'size': '목표 용량', 'merge_pdf': 'PDF 합치기', 'pages': '페이지 선택',
          'ocr_txt': '글자 → TXT', 'ocr_docx': '글자 → Word', 'trim': '구간 자르기',
          'favorite': '즐겨찾기', 'save_preset': '설정 저장','scan':'스캔 보정','split_pdf':'PDF 분리'}
COLORS = {'size':'#ccefe9', 'merge_pdf':'#ffd9d3', 'pages':'#d9e5ff',
          'ocr_txt':'#e8dcff', 'ocr_docx':'#dfdeff', 'trim':'#ffe5c9',
          'favorite':'#fff0b8', 'save_preset':'#dce8f6','scan':'#e1f1e3','split_pdf':'#f4dbdd'}


def page_order(text, count):
    """1-based inclusive ranges; written order is kept, including intentional repeats."""
    if not str(text or '').strip():
        return list(range(count))
    values = []
    for token in str(text).replace(' ', '').split(','):
        bounds = token.split('-')
        if len(bounds) not in (1, 2) or any(not b.isdecimal() for b in bounds):
            raise ValueError('페이지는 1,3-5,2처럼 입력해 주세요.')
        start, end = int(bounds[0]), int(bounds[-1])
        if not 1 <= start <= count or not 1 <= end <= count:
            raise ValueError(f'페이지는 1~{count} 사이여야 해요.')
        values += list(range(start-1, end-1 + (1 if end >= start else -1), 1 if end >= start else -1))
        if len(values) > 10000:
            raise ValueError('한 번에 최대 10,000페이지까지 선택할 수 있어요.')
    return values


def timestamp(value):
    try:
        parts = str(value or '0').strip().split(':')
        if not 1 <= len(parts) <= 3:
            raise ValueError()
        numbers = [float(p) for p in parts]
        if any(not math.isfinite(n) or n < 0 for n in numbers) or any(n >= 60 for n in numbers[1:]):
            raise ValueError()
        return sum(n * 60**i for i, n in enumerate(reversed(numbers)))
    except (ValueError, TypeError):
        raise ValueError('시간은 초 또는 00:01:30 형식으로 입력해 주세요.') from None


def actions(paths):
    from converter import HANGUL, IMAGES, WORD, SHEETS, SLIDES
    from media import VIDEOS, AUDIO
    exts = {Path(p).suffix.lower() for p in paths}
    if not exts:
        return []
    result = []
    if exts <= (IMAGES | HANGUL | {'.docx', '.pptx', '.pdf'} | VIDEOS):
        result += ['size']
    if exts <= (IMAGES | HANGUL | WORD | SHEETS | SLIDES | {'.pdf', '.txt'}):
        if len(paths) > 1:
            result += ['merge_pdf']
        if not exts & IMAGES:
            result += ['pages']
    if exts <= IMAGES | {'.pdf'}:
        result += ['ocr_txt', 'ocr_docx']
    if exts <= IMAGES:result += ['scan']
    if exts == {'.pdf'}:result += ['split_pdf']
    if exts <= VIDEOS | AUDIO:
        result += ['trim']
    return result


def normalize_pdf(source, folder, quality, origin):
    from converter import IMAGES, image_convert, office_convert
    source = Path(source)
    folder.mkdir(parents=True, exist_ok=True)
    result = folder/'normalized.pdf'
    if source.suffix.lower() == '.pdf':
        shutil.copy2(source, result)
    elif source.suffix.lower() in IMAGES:
        image_convert(source, folder, 'normalized', 'pdf', quality)
    else:
        copied = folder/source.name
        shutil.copy2(source, copied)
        office_convert(copied, result, 'pdf', quality, origin)
    return result


def ocr(source, out, stem, target, options, progress_path):
    from converter import IMAGES
    pictures = out/'_ocr'
    pictures.mkdir()
    images = []
    if source.suffix.lower() in IMAGES:
        with Image.open(source) as original:
            for i, frame in enumerate(ImageSequence.Iterator(original)):
                image = ImageOps.exif_transpose(frame).convert('RGB')
                image.thumbnail((3500, 3500), Image.Resampling.LANCZOS)
                path = pictures/f'{i}.png'
                image.save(path)
                images.append(str(path))
    else:
        with pymupdf.open(source) as pdf:
            if pdf.needs_pass:
                raise ValueError('암호를 해제한 PDF 사본을 선택해 주세요.')
            for i in page_order(options.get('pages'), len(pdf)):
                page = pdf[i]
                scale = min(3, 3500/max(page.rect.width, page.rect.height))
                path = pictures/f'{len(images)}.png'
                page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(path)
                images.append(str(path))
    if progress_path:
        Path(progress_path).write_text(f'{len(images)}쪽 글자 인식 중', encoding='utf-8')
    request, response = pictures/'request.json', pictures/'response.json'
    request.write_text(json.dumps({'images':images}), encoding='utf-8')
    script = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))/'ocr.ps1'
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                    '-File', str(script), '-Request', str(request), '-Response', str(response)],
                   capture_output=True, timeout=max(120, len(images)*45), creationflags=subprocess.CREATE_NO_WINDOW)
    if not response.exists():
        raise ValueError('Windows 글자 인식을 시작하지 못했어요. Windows 한국어 OCR 기능을 확인해 주세요.')
    result = json.loads(response.read_text(encoding='utf-8-sig'))
    if not result.get('ok'):
        raise ValueError('Windows OCR을 사용할 수 없어요. 설정 → 언어 → 한국어 → 광학 문자 인식을 설치해 주세요.\n'+result.get('error', ''))
    texts = result['texts']
    if not any(t.strip() for t in texts):
        raise ValueError('인식할 글자가 없어요. 글자가 선명한 인쇄 문서 사진을 선택해 주세요.')
    if target == 'ocr_txt':
        (out/f'{stem}.txt').write_text('\n\n'.join(texts), encoding='utf-8-sig')
    else:
        from docx import Document
        doc = Document()
        for i, text in enumerate(texts):
            if i:
                doc.add_page_break()
            for line in text.splitlines():
                doc.add_paragraph(line)
        doc.save(out/f'{stem}.docx')
    shutil.rmtree(pictures)
    return {'ocr_language':result.get('language'), 'pages':len(texts)}


def size_job(source, out, quality, origin, options, progress, cancel):
    from converter import IMAGES, office_convert, remove_stage
    from package_tools import package, pdf_images
    from media import VIDEOS, convert
    budget = int(float(options.get('max_mb', 5))*1024*1024)
    if not 1024 <= budget <= 100*1024**3:
        raise ValueError('목표 용량은 0.001~102400 MB 사이로 입력해 주세요.')
    destination = out/source.name
    ext = source.suffix.lower()
    if source.stat().st_size <= budget:
        shutil.copy2(source, destination)
    elif ext in VIDEOS:
        convert(source, out, source.stem, 'compress', quality, progress, cancel, {'max_bytes':budget})
        destination = out/(source.stem+'.mp4')
        if destination.stat().st_size >= source.stat().st_size:
            destination.unlink()
            destination=out/source.name
            shutil.copy2(source,destination)
    elif ext in IMAGES:
        with Image.open(source) as original:
            if getattr(original, 'n_frames', 1) > 1:
                raise ValueError('움직이는 사진은 목표 용량 대신 일반 용량 줄이기를 사용해 주세요.')
            image = ImageOps.exif_transpose(original).copy()
            fmt = original.format
        best = source.read_bytes()
        for scale in (1, .8, .6, .4, .25):
            frame = image.resize((max(1, round(image.width*scale)), max(1, round(image.height*scale))), Image.Resampling.LANCZOS)
            for q in (88, 70, 50, 30, 15):
                buf = io.BytesIO()
                if fmt == 'PNG':
                    frame.convert('RGBA').quantize(colors=max(16, int(q/100*256)), method=Image.Quantize.FASTOCTREE).save(buf, 'PNG', optimize=True)
                elif fmt in {'JPEG', 'WEBP'}:
                    frame.convert('RGB' if fmt == 'JPEG' else 'RGBA').save(buf, fmt, quality=q, optimize=True)
                else:
                    frame.save(buf, fmt)
                if len(buf.getvalue()) < len(best):
                    best = buf.getvalue()
                if len(best) <= budget:
                    break
            if len(best) <= budget:
                break
        destination.write_bytes(best)
    else:
        stage = out/'_input'
        stage.mkdir()
        normal = source
        if ext == '.hwp':
            copied = stage/source.name
            shutil.copy2(source, copied)
            normal = stage/'normalized.hwpx'
            office_convert(copied, normal, 'hwpx', quality, origin)
        best = source.read_bytes()
        for q in (88, 65, 45, 25, 12):
            candidate = stage/('candidate.pdf' if ext == '.pdf' else 'candidate'+normal.suffix)
            if ext == '.pdf':
                pdf_images(normal, candidate, q)
            else:
                package(normal, candidate, q)
            if ext == '.hwp':
                hwp = stage/'candidate.hwp'
                office_convert(candidate, hwp, 'hwp', quality, origin)
                candidate = hwp
            data = candidate.read_bytes()
            if len(data) < len(best):
                best = data
            if len(best) <= budget:
                break
        destination.write_bytes(best)
        remove_stage(stage)
    size = destination.stat().st_size
    return {'target_bytes':budget, 'target_met':size <= budget,
            'original_bytes':source.stat().st_size, 'result_bytes':size,
            'saved_percent':round((1-size/source.stat().st_size)*100, 1)}


def perform(source, target, quality='balanced', origin_hwnd=0, progress_path=None, cancel_path=None,
            options=None, sources=None,preview=False):
    from converter import SUPPORTED, pdf_convert, remove_stage
    from media import convert
    source = Path(source).resolve(strict=True)
    if source.suffix.lower() not in SUPPORTED or not source.is_file():
        raise ValueError('지원하는 파일을 선택해 주세요.')
    if quality not in {'small', 'balanced', 'high'}:
        raise ValueError('올바른 품질을 선택해 주세요.')
    options = options or {}
    work = Path(tempfile.mkdtemp(prefix='.docq-', dir=source.parent))
    extra = {}
    retained=False
    try:
        if target=='scan':
            from scan_tools import scan_job
            extra=scan_job(source,work,options)
        elif target=='split_pdf':
            if source.suffix.lower()!='.pdf':raise ValueError('PDF 파일을 선택해 주세요.')
            raw=options.get('chunk_pages',1)
            try:
                chunk=int(raw)
                if isinstance(raw,float) and raw!=chunk:raise ValueError()
            except (ValueError,TypeError,OverflowError):raise ValueError('한 파일당 쪽수를 정수로 입력해 주세요.') from None
            if not 1<=chunk<=10000:raise ValueError('한 파일당 1~10,000쪽 사이로 지정해 주세요.')
            with pymupdf.open(source) as pdf:
                if pdf.needs_pass:raise ValueError('암호를 해제한 PDF 사본을 선택해 주세요.')
                if not len(pdf):raise ValueError('페이지가 없는 PDF예요.')
                extra['source_page_starts']={}
                digits=max(3,len(str(len(pdf))))
                for first in range(0,len(pdf),chunk):
                    last=min(len(pdf),first+chunk)-1
                    name=f'{source.stem}_{first+1:0{digits}d}'+(f'-{last+1:0{digits}d}' if last>first else '')+'.pdf'
                    with pymupdf.open() as part:
                        part.insert_pdf(pdf,from_page=first,to_page=last)
                        part.save(work/name,garbage=4,deflate=True)
                    extra['source_page_starts'][name]=first
            extra['pages']=len(extra['source_page_starts'])
        elif target == 'size':
            extra = size_job(source, work, quality, origin_hwnd, options, progress_path, cancel_path)
        elif target in {'ocr_txt', 'ocr_docx'}:
            extra = ocr(source, work, source.stem, target, options, progress_path)
        elif target == 'trim':
            convert(source, work, source.stem, options.get('format', 'mp4'), quality,
                    progress_path, cancel_path, options)
        elif target in {'merge_pdf', 'pages'}:
            stage = work/'_input'
            stage.mkdir()
            paths = sources if target == 'merge_pdf' else [source]
            if not paths:
                raise ValueError('합칠 파일을 선택해 주세요.')
            extra['source_files']=[str(Path(path).resolve()) for path in paths]
            merged = pymupdf.open()
            try:
                for i, path in enumerate(paths):
                    normalized = normalize_pdf(Path(path).resolve(strict=True), stage/str(i), quality, origin_hwnd)
                    with pymupdf.open(normalized) as pdf:
                        if pdf.needs_pass:
                            raise ValueError('암호를 해제한 PDF 사본을 선택해 주세요.')
                        order = page_order(options.get('pages'), len(pdf)) if target == 'pages' else range(len(pdf))
                        for page in order:
                            merged.insert_pdf(pdf, from_page=page, to_page=page)
                if not len(merged):
                    raise ValueError('결과 페이지가 없어요.')
                normal = stage/'selected.pdf'
                merged.save(normal, garbage=4, deflate=True)
                extra['pages'] = len(merged)
                if target=='pages':extra['source_page_order']=list(order)
            finally:
                merged.close()
            fmt = options.get('format', 'pdf') if target == 'pages' else 'pdf'
            if fmt == 'pdf':
                shutil.copy2(normal, work/(source.stem+('_합침' if target == 'merge_pdf' else '_선택')+'.pdf'))
            elif fmt in {'png','jpg','txt','docx','pptx','xlsx'}:
                pdf_convert(normal, work, source.stem, fmt, quality)
            else:
                raise ValueError('지원하지 않는 페이지 변환 형식이에요.')
            remove_stage(stage)
        else:
            raise ValueError('지원하지 않는 작업이에요.')
        outputs = sorted(work.iterdir())
        if not outputs or any(not p.is_file() or not p.stat().st_size for p in outputs):
            raise ValueError('변환 결과가 비어 있어요.')
        if target=='pages' and options.get('format','pdf') in {'png','jpg'}:
            extra['source_page_starts']={p.name:order[i] for i,p in enumerate(sorted(outputs))}
        from job_output import finish_result,prepare_views
        result=finish_result(source,work,outputs,extra,preview)
        if preview:
            if progress_path:Path(progress_path).write_text('변환 전후 화면 준비 중',encoding='utf-8')
            prepare_views(result,quality,origin_hwnd)
        retained=preview
        return result
    finally:
        if not retained and work.exists():
            shutil.rmtree(work, ignore_errors=True)
