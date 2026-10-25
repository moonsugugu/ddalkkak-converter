"""Keep preview results private until Save; cancel removes only a marked owned stage."""
import ctypes
import json
import shutil
import uuid
from pathlib import Path

MARKER='_ddalkkak_preview.json'


def path_size(path):
    path=Path(path)
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.is_dir() else path.stat().st_size


def finish_result(source,work,outputs,extra=None,preview=False):
    source,work=Path(source),Path(work)
    result={'source':str(source),'folder':str(work),'files':[str(p) for p in outputs],**(extra or {})}
    if preview:
        token=uuid.uuid4().hex
        (work/MARKER).write_text(json.dumps({'source':str(source),'token':token}),encoding='utf-8')
        ctypes.windll.kernel32.SetFileAttributesW(str(work),2)
        result.update(_pending=True,_stage=str(work),_token=token)
        return result
    return publish(source,work,result)


def publish(source,work,result):
    index=1
    while True:
        folder=source.parent/(source.stem+'_변환'+(f'_{index}' if index>1 else ''))
        try:
            work.rename(folder)
            break
        except OSError:
            if folder.exists():index+=1
            else:raise
    attributes=ctypes.windll.kernel32.GetFileAttributesW(str(folder))
    if attributes!=-1:ctypes.windll.kernel32.SetFileAttributesW(str(folder),attributes&~2)
    return {**result,'folder':str(folder),'files':[str(folder/Path(p).name) for p in result['files']]}


def validate_stage(result):
    source=Path(result['source']).absolute()
    stage=Path(result['_stage']).absolute()
    if (stage.parent.resolve()!=source.parent.resolve() or not stage.name.startswith('.docq-')
            or stage.is_symlink() or stage.is_junction() or not stage.is_dir()):
        raise ValueError('미리보기 임시 폴더를 확인할 수 없어요. 원본은 그대로 유지했어요.')
    marker=json.loads((stage/MARKER).read_text(encoding='utf-8'))
    if marker!={'source':str(source),'token':result['_token']}:
        raise ValueError('이 작업의 미리보기 폴더가 아니에요.')
    if any(Path(p).parent.absolute()!=stage or not Path(p).exists() or Path(p).is_symlink() or Path(p).is_junction() for p in result['files']):
        raise ValueError('미리보기 결과 파일을 확인할 수 없어요.')
    for path in result['files']:
        if Path(path).is_dir():
            for child in Path(path).rglob('*'):
                if child.is_symlink() or child.is_junction() or not child.resolve().is_relative_to(stage.resolve()):
                    raise ValueError('미리보기 결과에 외부 경로가 있어요.')
    return source,stage


def commit_preview(result):
    if not result.get('_pending'):return result
    source,stage=validate_stage(result)
    # Native preview PDFs and thumbnails are private helpers, never conversion outputs.
    helper=stage/'_preview'
    if helper.is_dir():shutil.rmtree(helper)
    marker=(stage/MARKER).read_bytes()
    (stage/MARKER).unlink()
    try:saved=publish(source,stage,result)
    except Exception:
        (stage/MARKER).write_bytes(marker)
        raise
    return {k:v for k,v in saved.items() if not k.startswith('_')}


def discard_preview(result):
    if not result.get('_pending'):return
    _,stage=validate_stage(result)
    shutil.rmtree(stage)


def prepare_views(result,quality='balanced',origin_hwnd=0):
    from converter import IMAGES,HANGUL,WORD,SHEETS,SLIDES,office_convert,engines
    _,stage=validate_stage(result)
    helper=stage/'_preview';helper.mkdir(exist_ok=True)
    available=engines();warnings=[]
    def view(path,tag):
        path=Path(path);ext=path.suffix.lower()
        if ext in IMAGES|{'.pdf'}:return str(path)
        engine='hwp' if ext in HANGUL else 'word' if ext in WORD|{'.txt'} else 'excel' if ext in SHEETS else 'ppt' if ext in SLIDES else None
        if not engine or not available.get(engine):return None
        folder=helper/tag;folder.mkdir()
        copied=folder/path.name;shutil.copy2(path,copied)
        pdf=folder/'view.pdf'
        try:
            office_convert(copied,pdf,'pdf',quality,origin_hwnd)
            return str(pdf)
        except Exception as error:
            warnings.append(path.name+': '+str(error)[:160])
            return None
    originals=result.get('source_files') or [result['source']]
    result['_before_views']=[view(path,'before-'+str(i)) for i,path in enumerate(originals)]
    result['_after_views']=[view(path,'after-'+str(i)) for i,path in enumerate(result['files'])]
    result['_preview_warnings']=warnings
    return result
