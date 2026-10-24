"""Local scan cleanup with conservative deskew and optional white-margin trimming."""
from PIL import Image,ImageOps,ImageFilter,ImageMath,ImageStat,ImageSequence


def skew_angle(image):
    sample=ImageOps.grayscale(image)
    sample.thumbnail((900,900),Image.Resampling.LANCZOS)
    if min(sample.size)<60:return 0.0
    margin=max(1,min(sample.size)//30)
    sample=sample.crop((margin,margin,sample.width-margin,sample.height-margin))
    ink=sample.point(lambda p:255 if p<160 else 0)
    if ImageStat.Stat(ink).mean[0]<.2:
        return 0.0
    def score(angle):
        rotated=ink.rotate(angle,Image.Resampling.NEAREST,fillcolor=0)
        rows=list(rotated.resize((1,rotated.height),Image.Resampling.BOX).tobytes())
        return sum((a-b)**2 for a,b in zip(rows,rows[1:]))/max(1,len(rows))
    baseline=score(0)
    coarse=max(((score(a/2),a/2) for a in range(-20,21)),key=lambda pair:pair[0])
    best=max(((score(coarse[1]+i/10),coarse[1]+i/10) for i in range(-5,6)),key=lambda pair:pair[0])
    return round(best[1],1) if best[0]>baseline*1.12 and best[0]>1 else 0.0


def correct_scan(original,mode='color',deskew=True,trim=True):
    if mode not in {'color','gray','bw'}:
        raise ValueError('보정 방식은 컬러·회색·흑백 중에서 선택해 주세요.')
    image=ImageOps.exif_transpose(original).convert('RGBA')
    white=Image.new('RGBA',image.size,'white');white.alpha_composite(image)
    image=white.convert('RGB')
    angle=skew_angle(image) if deskew else 0.0
    if angle:
        image=image.rotate(angle,Image.Resampling.BICUBIC,expand=True,fillcolor='white')
    gray=ImageOps.grayscale(image)
    background=gray.filter(ImageFilter.GaussianBlur(max(15,max(image.size)/35)))
    def flatten(channel):
        return ImageMath.lambda_eval(lambda a:a['im']*255/(a['bg']+1),
                                     im=channel.convert('F'),bg=background.convert('F')).convert('L')
    if mode=='color':
        image=Image.merge('RGB',tuple(ImageOps.autocontrast(flatten(c),cutoff=.2) for c in image.split()))
    else:
        image=ImageOps.autocontrast(flatten(gray),cutoff=.2)
        if mode=='bw':image=image.point(lambda p:255 if p>180 else 0)
    image=image.filter(ImageFilter.UnsharpMask(radius=1,percent=110,threshold=3))
    if trim:
        box=ImageOps.grayscale(image).point(lambda p:255 if p<180 else 0).getbbox()
        if box:
            pad=max(20,round(max(image.size)*.025))
            image=image.crop((max(0,box[0]-pad),max(0,box[1]-pad),min(image.width,box[2]+pad),min(image.height,box[3]+pad)))
    return image,angle


def scan_job(source,out,options):
    fmt=options.get('format','png')
    if fmt not in {'png','jpg','pdf'}:raise ValueError('스캔 보정은 PNG·JPG·PDF로 저장할 수 있어요.')
    pages,angles=[],[]
    with Image.open(source) as original:
        for i,frame in enumerate(ImageSequence.Iterator(original)):
            image,angle=correct_scan(frame,options.get('mode','color'),options.get('deskew',True),options.get('trim',True))
            angles.append(angle)
            if fmt=='pdf':pages.append(image.convert('RGB'))
            else:
                image.convert('RGB').save(out/f'{source.stem}_보정_{i+1:03d}.{fmt}',
                                          **({'quality':92,'optimize':True} if fmt=='jpg' else {}))
    if pages:
        pages[0].save(out/f'{source.stem}_보정.pdf',save_all=True,append_images=pages[1:],resolution=180)
    return {'scan_angles':angles,'pages':len(angles)}
