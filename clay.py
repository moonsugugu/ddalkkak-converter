"""Small raster clay surfaces; text remains sharp native canvas text."""
import math
from PIL import Image, ImageDraw, ImageFilter, ImageColor


def wheel(targets, colors, size=460):
    scale = 2
    canvas = Image.new('RGBA', (size*scale, size*scale))
    def sphere(box, color, radius=None, shadow=5):
        b = tuple(round(v*scale) for v in box)
        layer = Image.new('RGBA', canvas.size)
        d = ImageDraw.Draw(layer)
        d.ellipse((b[0]+shadow*scale, b[1]+shadow*scale, b[2]+shadow*scale, b[3]+shadow*scale), fill=(110, 92, 155, 62))
        canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(6*scale)))
        width,height=b[2]-b[0],b[3]-b[1]
        surface=Image.new('RGBA',(width,height))
        gradient=ImageDraw.Draw(surface)
        rgb=ImageColor.getrgb(color)
        for y in range(height):
            ratio=y/max(1,height-1)
            tint=(.12-ratio*.20)
            tone=tuple(round(c+(255-c)*tint) if tint>=0 else round(c*(1+tint)) for c in rgb)
            gradient.line((0,y,width,y),fill=tone)
        mask=Image.new('L',(width,height))
        ImageDraw.Draw(mask).ellipse((0,0,width-1,height-1),fill=255)
        canvas.paste(surface,(b[0],b[1]),mask)
        d = ImageDraw.Draw(canvas)
        # Soft raised highlight and shaded lower rim stay inside the same circular surface.
        d.arc((b[0]+3*scale,b[1]+3*scale,b[2]-3*scale,b[3]-3*scale), 195, 280, fill='#ffffff', width=3*scale)
    sphere((10, 6, size-14, size-18), '#f2effa', shadow=3)
    sphere((144, 139, 316, 311), '#faf8ff', shadow=4)
    points = {}
    for i, target in enumerate(targets):
        angle = -math.pi/2+2*math.pi*i/len(targets)
        x, y = size/2+165*math.cos(angle), size/2+165*math.sin(angle)
        points[target] = (x, y)
        sphere((x-40,y-40,x+40,y+40), colors.get(target, '#fff0b8'), shadow=4)
    canvas = canvas.resize((size, size), Image.Resampling.LANCZOS)
    background = Image.new('RGB', canvas.size, '#010203')
    background.paste(canvas.convert('RGB'),mask=canvas.getchannel('A').point(lambda a:255 if a>190 else 0))
    return background, points
