"""Local document conversions. Never modify inputs or overwrite earlier results."""
from __future__ import annotations

import csv
import json
import hashlib
import os
import shutil
import sys
import time
import tempfile
import winreg
from pathlib import Path

from media import VIDEOS, AUDIO, MediaCancelled, executable as media_executable
from extra_formats import EXTRA_INPUTS, FORMAT_LABELS, targets as extra_targets

WORD = {'.doc', '.docx', '.rtf', '.odt'}
SHEETS = {'.xls', '.xlsx', '.csv'}
SLIDES = {'.ppt', '.pptx'}
HANGUL = {'.hwp', '.hwpx'}
IMAGES = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp', '.gif', '.ico'}
IMAGES |= {'.heic','.heif','.avif','.svg'}
SUPPORTED = WORD | SHEETS | SLIDES | HANGUL | IMAGES | VIDEOS | AUDIO | {'.pdf', '.txt'} | EXTRA_INPUTS
LABELS = {'pdf': 'PDF', 'docx': 'Word', 'hwp': '한글', 'hwpx': 'HWPX',
          'xlsx': 'Excel', 'pptx': 'PPT', 'png': 'PNG', 'jpg': 'JPG',
          'txt': '텍스트', 'csv': 'CSV', 'webp': 'WebP', 'bmp': 'BMP', 'tiff': 'TIFF', 'ico': '아이콘',
          'compress': '용량\n줄이기', 'images': '사진\n꺼내기', 'mp4':'MP4', 'mov':'MOV',
          'mkv':'MKV', 'webm':'WebM', 'gif':'GIF', 'mp3':'MP3', 'wav':'WAV', 'm4a':'M4A',
          'flac':'FLAC', 'ogg':'OGG'}
LABELS.update(FORMAT_LABELS)
COLORS = {'pdf': '#ffddd7', 'docx': '#dfdfff', 'hwp': '#d7eaff',
          'hwpx': '#e0efff', 'xlsx': '#d5f0e3', 'pptx': '#ffe4c9',
          'png': '#fff1bd', 'jpg': '#ffebca', 'txt': '#ece1fa', 'csv': '#dcf2e6',
          'compress':'#d2f1e6', 'images':'#ffe0eb', 'webp':'#e5f4c9', 'bmp':'#e5e6ff',
          'tiff':'#e8e1f4', 'ico':'#d5edfb', 'mp4':'#dcdfff', 'mov':'#ffdfd6',
          'mkv':'#d7efff', 'webm':'#d4f1e7', 'gif':'#fff0bc', 'mp3':'#f5dcfa',
          'wav':'#deebff', 'm4a':'#e8def9', 'flac':'#d6eee5', 'ogg':'#ffe9ce'}


class ConversionError(Exception):
    pass


def register_hangul_module(app):
    """Use Hancom's official Automation module only in our dedicated instance."""
    source = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'vendor' / 'FilePathCheckerModuleExample.dll'
    expected = '9ac5b97c47ac8aed1e8bca27a3eef39411361d8f68c262509f0c40a8f9d21bb6'
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ConversionError('한글 연결 모듈을 찾을 수 없어요. 프로그램을 다시 설치해 주세요.')
    support = Path(os.environ['LOCALAPPDATA']) / 'Moonsunezip' / 'DocQ' / 'support'
    support.mkdir(parents=True, exist_ok=True)
    module = support / source.name
    if not module.exists() or hashlib.sha256(module.read_bytes()).hexdigest() != expected:
        shutil.copy2(source, module)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\HNC\HwpAutomation\Modules') as key:
        winreg.SetValueEx(key, 'DocQ.FilePathChecker', 0, winreg.REG_SZ, str(module))
    return bool(app.RegisterModule('FilePathCheckDLL', 'DocQ.FilePathChecker'))


def engines():
    result = {'ffmpeg': bool(media_executable())}
    for name, progid in [('word', 'Word.Application'), ('excel', 'Excel.Application'),
                         ('ppt', 'PowerPoint.Application'), ('hwp', 'HWPFrame.HwpObject')]:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r'\CLSID'):
                result[name] = True
        except OSError:
            result[name] = False
    return result


def targets(path):
    ext = Path(path).suffix.lower()
    if ext in HANGUL:
        values = ['pdf', 'png', 'docx', 'hwpx', 'hwp', 'jpg', 'xlsx', 'pptx', 'txt', 'compress', 'images']
    elif ext in WORD or ext == '.txt':
        values = ['pdf', 'docx', 'xlsx', 'pptx', 'hwp', 'hwpx', 'png', 'jpg', 'txt']
    elif ext in SHEETS:
        values = ['pdf', 'xlsx', 'csv', 'png', 'jpg', 'txt']
    elif ext in SLIDES:
        values = ['pdf', 'pptx', 'png', 'jpg', 'txt']
    elif ext == '.pdf':
        values = ['docx', 'xlsx', 'pptx', 'png', 'jpg', 'txt', 'compress', 'images']
    elif ext in IMAGES:
        values = ['png', 'jpg', 'webp', 'avif', 'bmp', 'tiff', 'ico', 'pdf', 'docx', 'pptx', 'compress']
    elif ext in VIDEOS:
        values = ['mp4', 'webm', 'mov', 'mkv', 'gif', 'mp3', 'wav', 'compress']
    elif ext in AUDIO:
        values = ['mp3', 'wav', 'm4a', 'flac', 'ogg']
    else:
        values = []
    values = list(dict.fromkeys(values + extra_targets(ext)))
    if ext in {'.docx', '.pptx'}:
        values += ['compress', 'images']
    return [v for v in values if '.' + v != ext and not (ext == '.jpeg' and v == 'jpg')
            and not (ext == '.tif' and v == 'tiff')]


def unavailable(path, target, available):
    ext = Path(path).suffix.lower()
    if ext in VIDEOS | AUDIO:
        return '' if available.get('ffmpeg') else 'FFmpeg 설치 필요'
    if ext in {'.hwpx', '.docx', '.pptx'} and target in {'compress', 'images'}:
        return ''
    if target in {'hwp', 'hwpx'} or ext in HANGUL:
        required = 'hwp'
    elif ext in WORD or (ext == '.txt' and target in {'pdf', 'png', 'jpg', 'xlsx', 'pptx'}):
        required = 'word'
    elif ext in SHEETS and target in {'pdf', 'png', 'jpg'}:
        required = 'excel'
    elif ext in SLIDES and target in {'pdf', 'png', 'jpg'}:
        required = 'ppt'
    elif ext == '.doc' or ext == '.xls' or ext == '.ppt':
        required = {'.doc': 'word', '.xls': 'excel', '.ppt': 'ppt'}[ext]
    else:
        return ''
    return '' if available.get(required) else {'hwp': '한글', 'word': 'Word',
                                                'excel': 'Excel', 'ppt': 'PowerPoint'}[required] + ' 설치 필요'


def note(path, target):
    ext = Path(path).suffix.lower()
    if target == 'compress':
        if ext in VIDEOS:
            return '해상도·영상 품질을 조절해요 · 원본은 유지해요'
        return '사진 품질을 낮춰 용량을 줄여요 · 원본과 문서 배치는 유지해요'
    if target == 'images':
        return '문서 속 사진을 원래 형식으로 모두 꺼내요'
    if ext in VIDEOS | AUDIO:
        return ('음성만 따로 저장해요 · 소리가 있는 파일만 가능해요' if target in {'mp3','wav','m4a','flac','ogg'}
                else '전체 영상을 GIF로 만들어요 · 긴 영상은 용량이 커질 수 있어요' if target == 'gif'
                else '영상 전체를 바꿔요 · 길이에 따라 시간이 걸려요')
    if ext in IMAGES:
        return '사진의 방향·투명도를 유지해요' if target in {'png','webp','tiff'} else '원본을 보존하고 새 파일로 저장해요'
    if ext in HANGUL | WORD | {'.txt'}:
        if target == 'xlsx':
            return '표 추출 · 표가 없는 페이지는 텍스트로 저장해요'
        if target == 'pptx':
            return '한 페이지를 한 슬라이드 이미지로 저장해요'
    if ext == '.pdf':
        return {'docx': '텍스트 중심 · 원래 배치는 유지되지 않아요',
                'xlsx': '표 추출 · 표가 없는 페이지는 텍스트로 저장해요',
                'pptx': '한 페이지를 한 슬라이드 이미지로 저장해요',
                'txt': '스캔 PDF의 글자는 인식하지 않아요'}.get(target, '페이지마다 이미지 한 장씩 저장해요')
    if target == 'csv':
        return '시트마다 CSV로 저장해요 · 수식은 글자로 보존해요'
    if target in {'png', 'jpg'}:
        return '문서는 페이지마다 이미지 한 장씩 저장해요'
    if target in {'hwp', 'hwpx', 'docx'} and ext not in IMAGES:
        return '다른 문서 형식으로 바꾸면 글꼴과 배치가 달라질 수 있어요'
    if target == 'txt':
        return '글자만 저장해요 · 그림과 서식은 제외돼요'
    return '원본 옆 새 폴더에 저장해요'


def read_text(path):
    raw = Path(path).read_bytes()
    encodings = ('utf-16',) if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'cp949')
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeError:
            pass
    raise ConversionError('텍스트 인코딩을 읽지 못했어요. UTF-8로 저장한 뒤 다시 선택해 주세요.')


def office_convert(source, destination, target, quality, origin_hwnd=0):
    import pythoncom
    from win32com.client import DispatchEx
    pythoncom.CoInitialize()
    app = doc = None
    approval = None
    hwp_shared = False
    previous_document = None
    initial_id = None
    previous_ids = set()
    restore = {}
    hwp_pid = None
    before_pids = set()
    ext = source.suffix.lower()
    kind = 'hwp' if ext in HANGUL or target in {'hwp', 'hwpx'} else (
        'excel' if ext in SHEETS else 'ppt' if ext in SLIDES else 'word')
    def activate(document):
        identifier = document.DocumentID
        document.SetActive_XHwpDocument()
        # HWP 2024 switches its UI asynchronously. Opening/closing immediately can hit the old document.
        for _ in range(40):
            pythoncom.PumpWaitingMessages()
            time.sleep(.05)
            if app.XHwpDocuments.Active_XHwpDocument.DocumentID == identifier:
                time.sleep(.05)
                if app.XHwpDocuments.Active_XHwpDocument.DocumentID == identifier:
                    return
        raise ConversionError('한글 문서 창이 전환되지 않았어요. 한글의 확인 창을 닫은 뒤 다시 시도해 주세요.')
    try:
        if kind == 'hwp':
            from windows import process_ids
            before_pids = process_ids('Hwp.exe')
            import win32com.gen_py
            from win32com.client import gencache
            generated = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'vendor' / 'comgen'
            if str(generated) not in win32com.gen_py.__path__:
                win32com.gen_py.__path__.insert(0, str(generated))
            gencache.EnsureModule('{7D2B6F3C-1D95-4E0C-BF5A-5EE564186FBC}', 0, 1, 0,
                                 bValidateFile=False, bForDemand=False)
        app = DispatchEx({'hwp': 'HWPFrame.HwpObject', 'word': 'Word.Application',
                          'excel': 'Excel.Application', 'ppt': 'PowerPoint.Application'}[kind])
        if kind == 'hwp':
            import win32process
            hwp_pid = win32process.GetWindowThreadProcessId(int(app.XHwpWindows.Item(0).WindowHandle))[1]
            hwp_shared = hwp_pid in before_pids
            if hwp_shared:
                previous_document = app.XHwpDocuments.Active_XHwpDocument
                previous_ids = {app.XHwpDocuments.Item(i).DocumentID for i in range(app.XHwpDocuments.Count)}
                doc = app.XHwpDocuments.Add(False)
            else:
                doc = app.XHwpDocuments.Item(0)
            initial_id = doc.DocumentID
            activate(doc)
            own_window = app.XHwpWindows.Active_XHwpWindow
            registered = register_hangul_module(app)
            own_window.Visible = not registered
            if not registered:
                from windows import approve_conversion_paths
                approval = approve_conversion_paths(int(own_window.WindowHandle), [source, destination], origin_hwnd)
            if not app.Open(str(source), '', 'versionwarning:false;'):
                raise ConversionError('한글에서 파일을 열지 못했어요. 암호나 보안 확인 창을 확인해 주세요.')
            opened = None
            for _ in range(40):
                for i in range(app.XHwpDocuments.Count):
                    candidate = app.XHwpDocuments.Item(i)
                    if candidate.DocumentID not in previous_ids and candidate.FullName.casefold() == str(source).casefold():
                        opened = candidate
                        break
                if opened:
                    break
                pythoncom.PumpWaitingMessages()
                time.sleep(.05)
            if opened is None:
                raise ConversionError('한글에서 변환용 문서를 확인하지 못했어요. 기존 문서는 그대로 유지했어요.')
            doc = opened
            activate(doc)
            if target == 'txt':
                destination.write_text(app.GetTextFile('TEXT', ''), encoding='utf-8-sig')
            else:
                fmt = {'docx': 'OOXML', 'hwp': 'HWP', 'hwpx': 'HWPX', 'pdf': 'PDF'}[target]
                # Acknowledge only the format warning, after opening has completed.
                old_mode = app.SetMessageBoxMode(0x00000010)
                try:
                    if not app.SaveAs(str(destination), fmt, ''):
                        raise ConversionError('한글에서 저장하지 못했어요. 한글의 확인 창을 확인해 주세요.')
                finally:
                    app.SetMessageBoxMode(old_mode)
        else:
            restore['AutomationSecurity'] = app.AutomationSecurity
            app.AutomationSecurity = 3
            if kind == 'word':
                app.Visible = False
                app.DisplayAlerts = 0
                restore['UpdateLinksAtOpen'] = app.Options.UpdateLinksAtOpen
                app.Options.UpdateLinksAtOpen = False
                doc = app.Documents.Open(str(source), ConfirmConversions=False, ReadOnly=True,
                                         AddToRecentFiles=False)
                if target == 'pdf':
                    doc.ExportAsFixedFormat(str(destination), 17, False, 1 if quality == 'small' else 0)
                elif target == 'txt':
                    destination.write_text(doc.Content.Text, encoding='utf-8-sig')
                else:
                    doc.SaveAs2(str(destination), 16, AddToRecentFiles=False)
            elif kind == 'excel':
                app.Visible = False
                app.DisplayAlerts = False
                restore['AskToUpdateLinks'] = app.AskToUpdateLinks
                app.AskToUpdateLinks = False
                doc = app.Workbooks.Open(str(source), UpdateLinks=0, ReadOnly=True)
                doc.ExportAsFixedFormat(0, str(destination), 1 if quality == 'small' else 0)
            else:
                restore['DisplayAlerts'] = app.DisplayAlerts
                app.DisplayAlerts = 1
                doc = app.Presentations.Open(str(source), ReadOnly=True, Untitled=False, WithWindow=False)
                if target == 'txt':
                    text = '\n\n'.join('\n'.join(s.TextFrame.TextRange.Text for s in slide.Shapes
                                               if s.HasTextFrame) for slide in doc.Slides)
                    destination.write_text(text, encoding='utf-8-sig')
                else:
                    doc.SaveAs(str(destination), 24 if target == 'pptx' else 32)
    finally:
        if approval:
            approval.set()
        if doc is not None:
            try:
                if kind == 'hwp':
                    # HWP is a shared singleton even with DispatchEx. Close only our document.
                    own_id = doc.DocumentID
                    if own_id in previous_ids:
                        raise ConversionError('기존 문서는 닫지 않았어요.')
                    known = {initial_id, own_id}
                    hwp_shared = hwp_shared or any(app.XHwpDocuments.Item(i).DocumentID not in known
                                                  for i in range(app.XHwpDocuments.Count))
                    activate(doc)
                    doc.Close(False)
                    if own_id != initial_id:
                        for i in range(app.XHwpDocuments.Count):
                            extra = app.XHwpDocuments.Item(i)
                            if extra.DocumentID == initial_id and not extra.Modified and not extra.FullName:
                                activate(extra)
                                extra.Close(False)
                                break
                    if previous_document:
                        activate(previous_document)
                else:
                    doc.Close(False) if kind in {'word', 'excel'} else doc.Close()
            except Exception:
                if kind == 'hwp':
                    hwp_shared = True
        if app is not None:
            try:
                for name, value in restore.items():
                    if name == 'UpdateLinksAtOpen':
                        app.Options.UpdateLinksAtOpen = value
                    else:
                        setattr(app, name, value)
                if kind == 'hwp':
                    if not hwp_shared:
                        app.Quit()
                elif kind != 'ppt' or app.Presentations.Count == 0:
                    app.Quit()
            except Exception:
                pass
        if kind == 'hwp' and not hwp_shared and hwp_pid:
            # HWP shuts down asynchronously; don't let the next file attach to a dying server.
            import win32api
            import win32event
            try:
                handle = win32api.OpenProcess(0x00100000, False, hwp_pid)
                win32event.WaitForSingleObject(handle, 3000)
                win32api.CloseHandle(handle)
            except Exception:
                pass
        pythoncom.CoUninitialize()


def pdf_convert(source, out, stem, target, quality):
    import pymupdf
    with pymupdf.open(source) as pdf:
        if pdf.needs_pass:
            raise ConversionError('암호가 걸린 PDF예요. 암호를 해제한 사본을 선택해 주세요.')
        if not len(pdf):
            raise ConversionError('페이지가 없는 PDF예요.')
        dpi = {'small': 120, 'balanced': 180, 'high': 240}[quality]
        dest = out / (stem + '.' + target)
        if target in {'png', 'jpg', 'pptx'}:
            if target == 'pptx':
                from pptx import Presentation
                from pptx.util import Inches
                prs = Presentation()
                first = pdf[0].rect
                prs.slide_width = Inches(10)
                prs.slide_height = Inches(10 * first.height / first.width)
            for i, page in enumerate(pdf):
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                if target == 'pptx':
                    import io
                    slide = prs.slides.add_slide(prs.slide_layouts[6])
                    scale = min(prs.slide_width / page.rect.width, prs.slide_height / page.rect.height)
                    width, height = int(page.rect.width * scale), int(page.rect.height * scale)
                    slide.shapes.add_picture(io.BytesIO(pix.tobytes('png')),
                                             (prs.slide_width - width) // 2, (prs.slide_height - height) // 2,
                                             width, height)
                else:
                    pix.save(str(out / f'{stem}_{i+1:03d}.{target}'))
            if target == 'pptx':
                prs.save(dest)
        elif target == 'xlsx':
            from openpyxl import Workbook
            wb = Workbook()
            wb.remove(wb.active)
            for i, page in enumerate(pdf):
                ws = wb.create_sheet(f'{i+1}페이지')
                tables = page.find_tables().tables
                if tables:
                    for table in tables:
                        for row in table.extract():
                            ws.append([safe_cell(v) for v in row])
                        ws.append([])
                else:
                    for line in page.get_text(sort=True).splitlines():
                        ws.append([safe_cell(line)])
                ws.column_dimensions['A'].width = 48
            wb.save(dest)
        else:
            texts = [page.get_text(sort=True) for page in pdf]
            if not any(t.strip() for t in texts):
                raise ConversionError('추출할 글자가 없어요. 스캔 PDF는 메뉴의 글자 → TXT / Word (OCR)를 선택해 주세요.')
            if target == 'txt':
                dest.write_text('\n\n'.join(texts), encoding='utf-8-sig')
            else:
                from docx import Document
                doc = Document()
                for i, text in enumerate(texts):
                    if i:
                        doc.add_page_break()
                    for line in text.splitlines():
                        doc.add_paragraph(line)
                doc.save(dest)


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def image_convert(source, out, stem, target, quality):
    from PIL import Image, ImageOps
    from image_io import open_image
    with open_image(source) as image:
        # Multi-frame TIFFs are processed sequentially to bound memory.
        frames = getattr(image, 'n_frames', 1)
        if target == 'pdf':
            import pymupdf
            pdf = pymupdf.open()
        elif target == 'docx':
            from docx import Document
            from docx.shared import Inches
            doc = Document()
        elif target == 'pptx':
            from pptx import Presentation
            prs = Presentation()
        for i in range(frames):
            image.seek(i)
            frame = ImageOps.exif_transpose(image.copy())
            if target in {'png', 'webp', 'avif', 'bmp', 'tiff', 'ico'}:
                name = f'{stem}_{i+1:03d}.{target}' if frames > 1 else f'{stem}.{target}'
                if target == 'ico':
                    frame = frame.convert('RGBA')
                    frame.thumbnail((256, 256))
                    icon = Image.new('RGBA', (256, 256))
                    icon.alpha_composite(frame, ((256-frame.width)//2, (256-frame.height)//2))
                    icon.save(out/name, sizes=[(s,s) for s in (16,32,48,64,128,256)])
                elif target in {'webp','avif'}:
                    frame.save(out/name, quality={'small':65, 'balanced':85, 'high':95}[quality])
                elif target == 'tiff':
                    frame.save(out/name, compression='tiff_deflate')
                elif target == 'bmp':
                    rgba = frame.convert('RGBA')
                    white = Image.new('RGB', frame.size, 'white')
                    white.paste(rgba, mask=rgba.getchannel('A'))
                    white.save(out/name)
                else:
                    frame.save(out/name, optimize=True)
            else:
                rgba = frame.convert('RGBA')
                rgb = Image.new('RGB', frame.size, 'white')
                rgb.paste(rgba, mask=rgba.getchannel('A'))
                if target == 'jpg':
                    rgb.save(out / (f'{stem}_{i+1:03d}.jpg' if frames > 1 else f'{stem}.jpg'),
                             quality={'small': 75, 'balanced': 88, 'high': 96}[quality])
                else:
                    import io
                    buf = io.BytesIO()
                    rgb.save(buf, format='PNG')
                    if target == 'pdf':
                        scale = min(595 / rgb.width, 842 / rgb.height)
                        page = pdf.new_page(width=rgb.width * scale, height=rgb.height * scale)
                        page.insert_image(page.rect, stream=buf.getvalue())
                    elif target == 'docx':
                        if i:
                            doc.add_page_break()
                        scale = min(6 / rgb.width, 9 / rgb.height)
                        doc.add_picture(buf, width=Inches(rgb.width * scale), height=Inches(rgb.height * scale))
                    else:
                        slide = prs.slides.add_slide(prs.slide_layouts[6])
                        scale = min(prs.slide_width / rgb.width, prs.slide_height / rgb.height)
                        w, h = int(rgb.width * scale), int(rgb.height * scale)
                        slide.shapes.add_picture(buf, (prs.slide_width-w)//2, (prs.slide_height-h)//2, w, h)
        dest = out / f'{stem}.{target}'
        if target == 'pdf':
            pdf.save(dest, deflate=True)
            pdf.close()
        elif target == 'docx':
            doc.save(dest)
        elif target == 'pptx':
            prs.save(dest)


def sheet_convert(source, out, stem, target):
    from openpyxl import Workbook, load_workbook
    if source.suffix.lower() == '.csv':
        import io
        rows = csv.reader(io.StringIO(read_text(source)))
        wb = Workbook()
        for row in rows:
            wb.active.append([safe_cell(v) for v in row])
    else:
        wb = load_workbook(source, data_only=False)
    if target == 'xlsx':
        wb.save(out / f'{stem}.xlsx')
    else:
        for i, ws in enumerate(wb.worksheets):
            dest = out / (f'{stem}_{i+1:02d}.{target}' if len(wb.worksheets)>1 else f'{stem}.{target}')
            with dest.open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f, delimiter=',' if target == 'csv' else '\t')
                for row in ws.values:
                    writer.writerow([safe_cell(v) if target == 'csv' else v for v in row])
    wb.close()


def remove_stage(stage):
    for attempt in range(30):
        try:
            shutil.rmtree(stage)
            return
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(.1)


def photos(source, work, stem, target, quality, origin_hwnd):
    from package_tools import package, pdf_images, optimize_image
    ext = source.suffix.lower()
    if ext == '.pdf':
        return pdf_images(source, work if target == 'images' else work/f'{stem}.pdf', quality,
                          extract=target == 'images')
    if ext in IMAGES:
        if ext in {'.heic','.heif','.svg','.avif'}:
            from image_io import oriented,save_image
            save_image(oriented(source),work/(stem+'.jpg'),quality)
            return 1
        (work/source.name).write_bytes(optimize_image(source.read_bytes(), quality))
        return 1
    if ext != '.hwp':
        return package(source, work if target == 'images' else work/source.name, quality,
                       extract=target == 'images')
    stage = work/'_input'
    stage.mkdir()
    copied = stage/source.name
    shutil.copy2(source, copied)
    normal = stage/f'{stem}.hwpx'
    office_convert(copied, normal, 'hwpx', quality, origin_hwnd)
    if target == 'images':
        count = package(normal, work, quality, extract=True)
    else:
        compact = stage/f'{stem}_압축.hwpx'
        count = package(normal, compact, quality)
        office_convert(compact, work/source.name, 'hwp', quality, origin_hwnd)
    remove_stage(stage)
    return count


def perform(source, target, quality='balanced', origin_hwnd=0, progress_path=None, cancel_path=None, options=None, sources=None, preview=False):
    from extra_jobs import handles,perform as extra_perform
    if handles(source,target):
        return extra_perform(source,target,quality,origin_hwnd,progress_path,cancel_path,options,sources,preview)
    if target in {'size', 'merge_pdf', 'pages', 'ocr_txt', 'ocr_docx', 'trim', 'scan', 'split_pdf'}:
        from advanced import perform as advanced_perform
        return advanced_perform(source, target, quality, origin_hwnd, progress_path, cancel_path, options, sources, preview)
    source = Path(source).resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in SUPPORTED:
        raise ConversionError('지원하는 문서나 이미지 파일을 선택해 주세요.')
    if target not in targets(source) or quality not in {'small', 'balanced', 'high'}:
        raise ConversionError('선택한 파일에서 지원하지 않는 변환이에요.')
    reason = unavailable(source, target, engines())
    if reason:
        raise ConversionError(reason)
    ext, stem = source.suffix.lower(), source.stem
    # Work beside the source so publishing the completed directory is atomic.
    work = Path(tempfile.mkdtemp(prefix='.docq-', dir=source.parent))
    extra = {}
    retained=False
    try:
        dest = work / f'{stem}.{target}'
        if ext in VIDEOS | AUDIO:
            from media import convert
            convert(source, work, stem, target, quality, progress_path, cancel_path)
        elif target in {'compress', 'images'}:
            extra['pictures_processed'] = photos(source, work, stem, target, quality, origin_hwnd)
        elif ext in IMAGES:
            image_convert(source, work, stem, target, quality)
        elif ext == '.pdf':
            pdf_convert(source, work, stem, target, quality)
        elif ext in {'.xlsx', '.csv'} and target in {'xlsx', 'csv', 'txt'}:
            sheet_convert(source, work, stem, target)
        elif ext == '.pptx' and target == 'txt':
            from pptx import Presentation
            prs = Presentation(source)
            texts = []
            for slide in prs.slides:
                lines = []
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        lines.append(shape.text)
                    elif shape.has_table:
                        lines += ['\t'.join(c.text for c in row.cells) for row in shape.table.rows]
                texts.append('\n'.join(lines))
            dest.write_text('\n\n'.join(texts), encoding='utf-8-sig')
        elif ext == '.txt' and target == 'docx':
            from docx import Document
            doc = Document()
            for line in read_text(source).splitlines():
                doc.add_paragraph(line)
            doc.save(dest)
        else:
            # Legacy formats are normalised by the installed application.
            stage = work / '_input'
            stage.mkdir()
            copied = stage / source.name
            shutil.copy2(source, copied)
            if ext == '.xls' and target in {'xlsx', 'csv', 'txt'}:
                import pythoncom
                from win32com.client import DispatchEx
                pythoncom.CoInitialize()
                app = doc = None
                normal = stage / 'normalized.xlsx'
                try:
                    app = DispatchEx('Excel.Application')
                    app.AutomationSecurity = 3
                    app.DisplayAlerts = False
                    app.AskToUpdateLinks = False
                    doc = app.Workbooks.Open(str(copied), UpdateLinks=0, ReadOnly=True)
                    doc.SaveAs(str(normal), 51)
                finally:
                    if doc is not None:
                        doc.Close(False)
                    if app is not None:
                        app.Quit()
                    pythoncom.CoUninitialize()
                if target == 'xlsx':
                    shutil.copy2(normal, dest)
                else:
                    sheet_convert(normal, work, stem, target)
            elif target in {'png', 'jpg'} or (ext in HANGUL | WORD | {'.txt'} and target in {'xlsx', 'pptx'}):
                pdf = stage / 'pages.pdf'
                office_convert(copied, pdf, 'pdf', quality, origin_hwnd)
                pdf_convert(pdf, work, stem, target, quality)
            else:
                office_convert(copied, dest, target, quality, origin_hwnd)
            remove_stage(stage)
        outputs = list(work.iterdir())
        if not outputs or any(not p.is_file() or p.stat().st_size == 0 for p in outputs):
            raise ConversionError('변환 결과가 비어 있어요. 원본 문서를 확인해 주세요.')
        if target == 'compress':
            original_bytes = source.stat().st_size
            result_bytes = sum(p.stat().st_size for p in outputs)
            if result_bytes >= original_bytes:
                for p in outputs:
                    p.unlink()
                shutil.copy2(source, work/source.name)
                outputs = [work/source.name]
                result_bytes = original_bytes
                extra['pictures_processed'] = 0
            extra.update(original_bytes=original_bytes, result_bytes=result_bytes,
                         saved_percent=round((1-result_bytes/original_bytes)*100, 1) if original_bytes else 0)
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


def worker(request_path, response_path):
    try:
        request = json.loads(Path(request_path).read_text(encoding='utf-8'))
        result = {'ok': True, **perform(**request)}
    except MediaCancelled as e:
        result = {'ok': False, 'cancelled': True, 'error': str(e)}
    except Exception as e:
        message = str(e)
        if not isinstance(e, (ConversionError, OSError, ValueError)):
            message = '변환을 완료하지 못했어요. 원본 파일과 변환 프로그램의 확인 창을 확인해 주세요.\n' + message[:400]
        result = {'ok': False, 'error': message}
    Path(response_path).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
