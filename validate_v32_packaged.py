"""Run real packaged workers on photo/PDF/format fixtures without user documents."""
import hashlib
import json
import subprocess
from pathlib import Path
import pymupdf
from PIL import Image
from job_output import commit_preview,discard_preview
from product import VERSION

ROOT=Path(__file__).resolve().parent


def main():
    folder=ROOT/'validation'/'v32'/'packaged';folder.mkdir(parents=True,exist_ok=True)
    exe=ROOT/'dist'/'DdalKkak.exe';proof={};counter=0
    def run(source,target,options=None,sources=None,preview=True):
        nonlocal counter
        counter+=1;request=folder/f'request-{counter}.json';response=folder/f'response-{counter}.json'
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        request.write_text(json.dumps({'source':str(source),'target':target,'options':options or {},
                                       'sources':sources,'preview':preview},ensure_ascii=False),encoding='utf-8')
        process=subprocess.run([str(exe),'--worker',str(request),str(response)],timeout=100,
                               creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True)
        assert process.returncode==0,(target,process.returncode,process.stderr)
        result=json.loads(response.read_text(encoding='utf-8'))
        assert result.get('ok'),(target,result)
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        if preview:result=commit_preview(result)
        proof[target+'-'+str(counter)]={'files':[Path(p).name for p in result['files']],'source_preserved':True}
        return result
    photo=folder/'photo.jpg';exif=Image.Exif();exif[315]='PRIVATE CAMERA'
    Image.new('RGB',(640,480),'#c9f1e7').save(photo,exif=exif)
    second=folder/'second.png';Image.new('RGBA',(200,300),(150,80,200,150)).save(second)
    for target in ('avif','png'):
        result=run(photo,target)
        with Image.open(result['files'][0]) as image:assert image.size==(640,480)
    heic=ROOT/'validation'/'example.heic'
    if heic.exists():
        result=run(heic,'png')
        with Image.open(result['files'][0]) as image:assert image.size==(1280,854)
        proof['HEIC-actual-decoder']=True
    svg=folder/'drawing.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="180" height="120"><rect width="180" height="120" fill="red"/></svg>')
    run(svg,'png')
    result=run(photo,'photo_edit',{'width':320,'marks':[{'kind':'cover','box':[0,0,.2,.2],'color':'#000000'}]})
    with Image.open(result['files'][0]) as image:assert image.size==(320,240) and image.getpixel((0,0))[:3]==(0,0,0)
    run(photo,'photo_collage',{'cell':120,'columns':2},[str(photo),str(second)])
    result=run(photo,'photo_metadata',{'format':'jpg'})
    assert b'PRIVATE CAMERA' not in Path(result['files'][0]).read_bytes()
    pdf=folder/'pages.pdf'
    with pymupdf.open() as doc:
        for i in range(3):doc.new_page().insert_text((40,60),f'PAGE {i+1}')
        doc.save(pdf)
    result=run(pdf,'pdf_edit',{'page_items':[{'index':2,'rotate':90},{'index':0}],'page_numbers':True,'watermark':'검증'})
    with pymupdf.open(result['files'][0]) as doc:assert len(doc)==2 and doc[0].rotation==90 and 'PAGE 3' in doc[0].get_text()
    locked=run(pdf,'pdf_protect',{'mode':'encrypt','new_password':'test-pass'})
    result=run(Path(locked['files'][0]),'pdf_protect',{'mode':'decrypt','password':'test-pass'})
    with pymupdf.open(result['files'][0]) as doc:assert not doc.needs_pass and len(doc)==3
    source=folder/'안내.md';source.write_text('# 제목\n\n한국어 문서 내용입니다.',encoding='utf-8')
    for target in ('html','epub','pdf','docx'):
        result=run(source,target)
        if target=='epub':run(Path(result['files'][0]),'txt')
    source=folder/'표.tsv';source.write_text('이름\t값\n샘플\t12\n',encoding='utf-8')
    for target in ('xlsx','ods','csv'):run(source,target)
    source=folder/'자막.srt';source.write_text('1\n00:00:01,000 --> 00:00:02,500\n안녕하세요\n',encoding='utf-8')
    result=run(source,'vtt');run(Path(result['files'][0]),'txt')
    for fmt in ('zip','tar','gz'):
        packed=run(source,'pack',{'format':fmt},[str(source)])
        result=run(Path(packed['files'][0]),'unpack')
        assert (Path(result['files'][0])/source.name).read_bytes()==source.read_bytes()
    output={'version':VERSION,'packaged_jobs':counter,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'cases':proof}
    (folder/'proof.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'version':VERSION,'packaged_jobs':counter,'all_passed':True},ensure_ascii=False))


if __name__=='__main__':main()
