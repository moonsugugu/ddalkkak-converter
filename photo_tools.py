"""Photo edits operate on pixel copies and are published by the normal preview flow."""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance, ImageFilter, ImageColor
from image_io import oriented, save_image, MAX_PIXELS


def bounded(value, low, high, label):
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f'{label}: {low}~{high} 사이로 입력해 주세요.')
    return number


def font(size):
    for file in ('C:/Windows/Fonts/malgunbd.ttf', 'C:/Windows/Fonts/malgun.ttf'):
        if Path(file).exists():
            return ImageFont.truetype(file, size)
    return ImageFont.load_default(size=size)


def box_for(values, size):
    if len(values) != 4:
        raise ValueError('영역 좌표를 확인해 주세요.')
    x0,y0,x1,y1 = [bounded(v, 0, 1, '영역') for v in values]
    if x1 <= x0 or y1 <= y0:
        raise ValueError('드래그로 넓이가 있는 영역을 지정해 주세요.')
    w,h=size
    return (int(x0*w),int(y0*h),max(int(x0*w)+1,int(x1*w)),max(int(y0*h)+1,int(y1*h)))


def edit(image, options):
    image = image.copy().convert('RGBA')
    rotation = int(options.get('rotate', 0))
    if rotation not in {0,90,180,270}:
        raise ValueError('회전은 0·90·180·270도로 지정해 주세요.')
    if rotation:
        image = image.rotate(-rotation, expand=True)
    if options.get('flip_x'):image=ImageOps.mirror(image)
    if options.get('flip_y'):image=ImageOps.flip(image)
    if options.get('crop'):
        image = image.crop(box_for(options['crop'], image.size))
    w,h=image.size
    width=int(options.get('width') or 0);height=int(options.get('height') or 0)
    if width or height:
        if not width:width=round(w*height/h)
        if not height:height=round(h*width/w)
        if min(width,height)<1 or max(width,height)>20000 or width*height>MAX_PIXELS:
            raise ValueError('사진 크기는 최대 2만 픽셀·4천만 화소까지 지정해 주세요.')
        image=image.resize((width,height),Image.Resampling.LANCZOS)
    for key,enhancer in [('brightness',ImageEnhance.Brightness),('contrast',ImageEnhance.Contrast),
                         ('saturation',ImageEnhance.Color),('sharpness',ImageEnhance.Sharpness)]:
        image=enhancer(image).enhance(bounded(options.get(key,1),0,3,key))
    margin=int(options.get('margin') or 0)
    if not 0<=margin<=2000:raise ValueError('여백은 0~2000픽셀 사이로 지정해 주세요.')
    radius=int(options.get('radius') or 0)
    if radius:
        if not 0<=radius<=2000:raise ValueError('모서리 값은 0~2000 사이로 지정해 주세요.')
        alpha=image.getchannel('A');mask=Image.new('L',image.size)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,image.width-1,image.height-1),radius=radius,fill=255)
        from PIL import ImageChops
        image.putalpha(ImageChops.multiply(alpha,mask))
    if margin or options.get('background'):
        size=(image.width+margin*2,image.height+margin*2)
        if size[0]*size[1]>MAX_PIXELS:raise ValueError('여백을 포함한 사진 크기가 너무 커요.')
        canvas=Image.new('RGBA',size,options.get('background') or '#ffffff')
        canvas.alpha_composite(image,(margin,margin));image=canvas
    for operation in options.get('marks', []):
        kind=operation.get('kind')
        box=box_for(operation['box'],image.size)
        color=operation.get('color','#7561cf');ImageColor.getrgb(color)
        if kind in {'blur','mosaic'}:
            region=image.crop(box)
            if kind=='blur':region=region.filter(ImageFilter.GaussianBlur(max(8,min(region.size)/10)))
            else:region=region.resize((max(1,region.width//18),max(1,region.height//18))).resize(region.size,Image.Resampling.NEAREST)
            image.paste(region,box[:2])
        elif kind=='highlight':
            overlay=Image.new('RGBA',image.size)
            ImageDraw.Draw(overlay).rectangle(box,fill=(*ImageColor.getrgb(color)[:3],85))
            image=Image.alpha_composite(image,overlay)
        else:
            draw=ImageDraw.Draw(image)
            width=max(2,round(min(image.size)/150))
            if kind=='cover':draw.rectangle(box,fill=color)
            elif kind=='arrow':
                if operation.get('points'):
                    points=operation['points']
                    if len(points)!=4:raise ValueError('화살표 좌표를 확인해 주세요.')
                    points=[bounded(v,0,1,'화살표') for v in points]
                    x0,y0,x1,y1=points[0]*image.width,points[1]*image.height,points[2]*image.width,points[3]*image.height
                else:x0,y0,x1,y1=box
                draw.line((x0,y0,x1,y1),fill=color,width=width)
                angle=math.atan2(y1-y0,x1-x0);length=max(12,width*5)
                draw.polygon([(x1,y1),(x1-length*math.cos(angle-.5),y1-length*math.sin(angle-.5)),
                              (x1-length*math.cos(angle+.5),y1-length*math.sin(angle+.5))],fill=color)
            elif kind=='text':
                text=str(operation.get('text',''))[:300]
                draw.multiline_text(box[:2],text,font=font(max(12,round(image.height*.045))),fill=color,stroke_width=1)
            else:raise ValueError('지원하지 않는 사진 편집이에요.')
    return image


def perform(source, work, target, options, sources=None, quality='balanced'):
    if target=='photo_metadata':
        with __import__('image_io').open_image(source) as original:
            info={str(k):str(v)[:1200] for k,v in original.getexif().items()}
        (work/(source.stem+'_기존정보.txt')).write_text('원본의 EXIF 항목 (이 보고서에는 원본 정보가 포함됩니다)\n'+str(info),encoding='utf-8') if options.get('report') else None
        image=oriented(source)
    elif target=='photo_collage':
        paths=[Path(p).resolve(strict=True) for p in (sources or [source])]
        if not 2<=len(paths)<=100:raise ValueError('콜라주는 사진 2~100장을 선택해 주세요.')
        columns=int(options.get('columns',2));cell=int(options.get('cell',600));gap=int(options.get('gap',20))
        if not 1<=columns<=10 or not 64<=cell<=2400 or not 0<=gap<=300:raise ValueError('콜라주 크기·열·간격을 확인해 주세요.')
        rows=math.ceil(len(paths)/columns);size=(columns*cell+(columns+1)*gap,rows*cell+(rows+1)*gap)
        if size[0]*size[1]>MAX_PIXELS:raise ValueError('콜라주가 너무 커요. 한 칸 크기를 줄여 주세요.')
        image=Image.new('RGBA',size,options.get('background','#ffffff'))
        for i,path in enumerate(paths):
            tile=ImageOps.contain(oriented(path),(cell,cell),Image.Resampling.LANCZOS)
            x=gap+(i%columns)*(cell+gap)+(cell-tile.width)//2;y=gap+(i//columns)*(cell+gap)+(cell-tile.height)//2
            image.alpha_composite(tile,(x,y))
    else:image=edit(oriented(source),options)
    fmt=options.get('format','png')
    if fmt not in {'png','jpg','webp','avif','tiff'}:raise ValueError('지원하지 않는 사진 출력 형식이에요.')
    save_image(image,work/(source.stem+'_편집.'+fmt),quality)
    return {'source_files':[str(p) for p in (sources or [source])]} if target=='photo_collage' else {}
