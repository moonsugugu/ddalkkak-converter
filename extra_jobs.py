"""Catalog and atomic jobs for the photo, PDF and additional-format toolbox."""
import shutil
import tempfile
from pathlib import Path
from extra_formats import ARCHIVES, EXTRA_INPUTS, targets as extra_targets

LABELS={'photo_edit':'사진\n편집','photo_redact':'가리기','photo_annotate':'글자·화살표',
        'photo_collage':'콜라주','photo_metadata':'사진정보\n삭제',
        'pdf_edit':'PDF\n페이지 편집','pdf_protect':'PDF\n암호','pdf_stamp':'워터마크\n쪽번호',
        'pack':'ZIP·TAR\n압축','unpack':'압축\n풀기'}
COLORS={key:('#e3dffc' if key.startswith('photo') else '#ffe0d9' if key.startswith('pdf') else '#d8efdf') for key in LABELS}
GROUP_JOBS={'photo_collage','pack'}


def actions(paths):
    from converter import IMAGES
    exts={Path(path).suffix.lower() for path in paths}
    if not exts:return []
    result=[]
    if exts<=IMAGES:
        result+=['photo_edit','photo_redact','photo_annotate','photo_metadata']
        if len(paths)>1:result+=['photo_collage']
    if exts=={'.pdf'}:
        result+=['pdf_protect','pdf_stamp']
        if len(paths)==1:result+=['pdf_edit']
    if exts<=ARCHIVES:result+=['unpack']
    return result+['pack']


def handles(source,target):
    ext=Path(source).suffix.lower()
    return target in LABELS or target in extra_targets(ext)


def perform(source,target,quality='balanced',origin_hwnd=0,progress_path=None,cancel_path=None,
            options=None,sources=None,preview=False):
    from converter import SUPPORTED
    from job_output import finish_result,prepare_views,path_size
    from extra_formats import text_job,subtitle_job,table_job,archive_job
    source=Path(source).resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in SUPPORTED:raise ValueError('지원하는 파일을 선택해 주세요.')
    if target not in LABELS and target not in extra_targets(source.suffix.lower()):raise ValueError('지원하지 않는 변환이에요.')
    if target in LABELS and target not in actions(sources or [source]):raise ValueError('선택한 파일에서 사용할 수 없는 도구예요.')
    if quality not in {'small','balanced','high'}:raise ValueError('올바른 품질을 선택해 주세요.')
    options=options or {};work=Path(tempfile.mkdtemp(prefix='.docq-',dir=source.parent));retained=False
    try:
        if progress_path:Path(progress_path).write_text('원본을 보존하고 사본 작업 중',encoding='utf-8')
        if target.startswith('photo_'):
            from photo_tools import perform as photo_job
            extra=photo_job(source,work,target,options,sources,quality)
        elif target.startswith('pdf_'):
            from pdf_tools import perform as pdf_job
            extra=pdf_job(source,work,target,options)
        elif target in {'pack','unpack'}:extra=archive_job(source,work,target,options,sources)
        elif source.suffix.lower() in {'.srt','.vtt'}:extra=subtitle_job(source,work,target)
        elif source.suffix.lower() in {'.xlsx','.csv','.tsv','.ods'}:extra=table_job(source,work,target)
        else:extra=text_job(source,work,target)
        outputs=sorted(work.iterdir())
        if not outputs or any(path_size(p)==0 for p in outputs):raise ValueError('변환 결과가 비어 있어요.')
        result=finish_result(source,work,outputs,extra,preview)
        if preview:
            if target in {'pack','unpack','photo_collage','photo_metadata'} or source.suffix.lower() in EXTRA_INPUTS:
                result['_before_views']=[str(p) if Path(p).suffix.lower() in {'.pdf','.png','.jpg','.webp','.avif'} else None for p in result.get('source_files',[str(source)])]
                result['_after_views']=[str(p) if Path(p).suffix.lower() in {'.pdf','.png','.jpg','.webp','.avif'} else None for p in result['files']]
            else:prepare_views(result,quality,origin_hwnd)
            if target.startswith('pdf_'):
                from pdf_tools import prepare_secure_views
                prepare_secure_views(result,options)
        retained=preview
        return result
    finally:
        if not retained and work.exists():shutil.rmtree(work)
