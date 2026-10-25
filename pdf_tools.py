"""Page organization, watermarking and authenticated PDF encryption on copies."""
import secrets
import pymupdf


def unlock(doc,password):
    if doc.needs_pass and not doc.authenticate(password or ''):
        raise ValueError('PDF 암호가 맞지 않아요. 올바른 암호를 입력해 주세요.')


def perform(source,work,target,options):
    destination=work/(source.stem+'_편집.pdf')
    with pymupdf.open(source) as original:
        unlock(original,options.get('password'))
        if not len(original):raise ValueError('페이지가 없는 PDF예요.')
        result=pymupdf.open()
        try:
            records=options.get('page_items') or [{'index':i,'rotate':0} for i in range(len(original))]
            if len(records)>10000:raise ValueError('한 번에 최대 10,000쪽까지 편집해 주세요.')
            order=[]
            for item in records:
                index=int(item['index']);rotation=int(item.get('rotate',0))
                if not 0<=index<len(original) or rotation not in {0,90,180,270}:raise ValueError('페이지·회전 값을 확인해 주세요.')
                result.insert_pdf(original,from_page=index,to_page=index)
                page=result[-1];page.set_rotation((original[index].rotation+rotation)%360);order.append(index)
            if not len(result):raise ValueError('최소 한 쪽을 남겨 주세요.')
            for i,page in enumerate(result):
                watermark=str(options.get('watermark','')).strip()[:100]
                if watermark:
                    size=min(30,page.rect.width/12)
                    for attempt in range(10):
                        remaining=page.insert_textbox(pymupdf.Rect(20,page.rect.height*.4,page.rect.width-20,page.rect.height*.8),
                                                    watermark,fontname='korea',fontsize=size,
                                                    color=(.5,.45,.6),align=1,fill_opacity=.25)
                        if remaining>=0:break
                        size*=.8
                    else:raise ValueError('워터마크가 페이지에 들어가지 않아요. 문구를 줄여 주세요.')
                if options.get('page_numbers'):
                    page.insert_text((page.rect.width/2-15,page.rect.height-18),f'{i+1} / {len(result)}',fontsize=10)
            new_password=str(options.get('new_password',''))
            encrypt=target=='pdf_protect' and options.get('mode','encrypt')=='encrypt'
            if encrypt and not new_password:raise ValueError('새 열기 암호를 입력해 주세요.')
            if len(new_password)>40 or len(new_password.encode('utf-8'))>127:raise ValueError('암호는 40자·UTF-8 기준 127바이트까지 지원해요.')
            if options.get('remove_metadata'):result.set_metadata({})
            else:result.set_metadata(dict(original.metadata))
            result.save(destination,garbage=4,deflate=True,
                        encryption=pymupdf.PDF_ENCRYPT_AES_256 if encrypt else pymupdf.PDF_ENCRYPT_NONE,
                        owner_pw=secrets.token_urlsafe(24) if encrypt else None,
                        user_pw=new_password if encrypt else None)
            return {'source_page_order':order}
        finally:result.close()


def prepare_secure_views(result, options):
    """Only temporary preview helpers are decrypted; Save removes these helpers."""
    from pathlib import Path
    helper=Path(result['_stage'])/'_preview';helper.mkdir(exist_ok=True)
    for key,paths,password in [('_before_views',[result['source']],options.get('password','')),
                               ('_after_views',result['files'],options.get('new_password',''))]:
        views=[]
        for i,path in enumerate(paths):
            with pymupdf.open(path) as doc:
                if doc.needs_pass:
                    unlock(doc,password)
                    destination=helper/(key+str(i)+'.pdf')
                    doc.save(destination,encryption=pymupdf.PDF_ENCRYPT_NONE)
                    views.append(str(destination))
                else:views.append(str(path))
        result[key]=views
