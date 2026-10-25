import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import pymupdf
from PIL import Image,ImageDraw
from converter import perform,targets
from job_output import commit_preview,discard_preview,validate_stage,path_size
from image_io import open_image


class ToolboxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.photo=self.root/'사진.jpg'
        image=Image.new('RGB',(600,400),'#f5dcae');draw=ImageDraw.Draw(image)
        for x in range(0,600,10):draw.line((x,0,600-x,399),fill=(x%256,50,160),width=3)
        exif=Image.Exif();exif[315]='PRIVATE AUTHOR';exif[305]='CAMERA SOFTWARE'
        image.save(self.photo,exif=exif)
        self.original=hashlib.sha256(self.photo.read_bytes()).hexdigest()
        self.pdf=self.root/'문서.pdf'
        with pymupdf.open() as doc:
            for i in range(3):doc.new_page(width=400,height=500).insert_text((30,50),f'PAGE {i+1}')
            doc.save(self.pdf)
    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).hexdigest(),self.original)
        self.temp.cleanup()
    def output(self,result,index=0):return Path(result['files'][index])

    def test_image_geometry_and_real_pixel_edits(self):
        result=perform(self.photo,'photo_edit',options={'rotate':90,'crop':[0,0,.5,1],'width':100,'marks':[
            {'kind':'cover','box':[0,0,.25,.25],'color':'#000000'},
            {'kind':'mosaic','box':[.3,.1,.7,.5]}, {'kind':'blur','box':[.6,.5,1,1]},
            {'kind':'arrow','box':[.1,.6,.8,.9]},{'kind':'text','box':[.1,.3,.8,.5],'text':'안내'},
            {'kind':'highlight','box':[.1,.8,.9,1],'color':'#ffff00'}]})
        with Image.open(self.output(result)) as image:
            self.assertEqual(image.size,(100,300));self.assertEqual(image.getpixel((0,0))[:3],(0,0,0))
        with self.assertRaises(ValueError):perform(self.photo,'photo_edit',options={'width':100000})
        with self.assertRaises(ValueError):perform(self.photo,'photo_edit',options={'brightness':float('nan')})

    def test_metadata_alpha_collage_and_cancel(self):
        cleared=perform(self.photo,'photo_metadata',options={'format':'jpg'})
        with Image.open(self.output(cleared)) as image:self.assertFalse(image.getexif())
        self.assertNotIn(b'PRIVATE AUTHOR',self.output(cleared).read_bytes())
        other=self.root/'다른사진.png';Image.new('RGBA',(70,120),(0,200,0,130)).save(other)
        result=perform(self.photo,'photo_collage',sources=[str(self.photo),str(other)],
                       options={'cell':100,'gap':10,'columns':2},preview=True)
        with Image.open(self.output(result)) as image:self.assertEqual(image.size,(230,120))
        stage=Path(result['_stage']);discard_preview(result);self.assertFalse(stage.exists())
        transparent=perform(other,'photo_edit',options={'radius':25,'format':'png'})
        with Image.open(self.output(transparent)) as image:self.assertEqual(image.getpixel((0,0))[3],0)

    def test_annotations_match_display_after_adding_margins(self):
        result=perform(self.photo,'photo_edit',options={'width':100,'height':100,'margin':50,
            'marks':[{'kind':'cover','box':[0,0,.2,.2],'color':'#ff0000'},
                     {'kind':'arrow','box':[.1,.6,.9,.601],'points':[.9,.6,.1,.6],'color':'#000000'}]})
        with Image.open(self.output(result)) as image:
            self.assertEqual(image.size,(200,200));self.assertEqual(image.getpixel((10,10))[:3],(255,0,0))
            self.assertEqual(image.getpixel((100,120))[:3],(0,0,0))

    def test_avif_and_svg_and_external_svg_block(self):
        avif=perform(self.photo,'avif')
        png=perform(self.output(avif),'png')
        with Image.open(self.output(png)) as image:self.assertEqual(image.size,(600,400))
        svg=self.root/'그림.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect width="120" height="80" fill="red"/></svg>')
        result=perform(svg,'png')
        with Image.open(self.output(result)) as image:self.assertEqual(image.getpixel((40,40))[:3],(255,0,0))
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///C:/private.png"/></svg>')
        with self.assertRaises(ValueError):perform(svg,'png')

    def test_pdf_order_rotation_duplicates_and_stamp(self):
        result=perform(self.pdf,'pdf_edit',options={'page_items':[{'index':2,'rotate':90},{'index':0},{'index':0}],
                                                 'page_numbers':True,'watermark':'시연용'})
        with pymupdf.open(self.output(result)) as doc:
            self.assertEqual(len(doc),3);self.assertEqual(doc[0].rotation,90)
            self.assertIn('PAGE 3',doc[0].get_text());self.assertIn('PAGE 1',doc[1].get_text())
            self.assertIn('1 / 3',doc[0].get_text());self.assertIn('시연용',doc[1].get_text().replace(' ',''))
        with self.assertRaises(ValueError):perform(self.pdf,'pdf_edit',options={'page_items':[{'index':99}]})

    def test_pdf_password_and_no_decrypted_helpers_after_save(self):
        protected=perform(self.pdf,'pdf_protect',options={'mode':'encrypt','new_password':'테스트123!'},preview=True)
        self.assertTrue(Path(protected['_after_views'][0]).is_file())
        with pymupdf.open(self.output(protected)) as doc:self.assertTrue(doc.needs_pass)
        saved=commit_preview(protected)
        self.assertEqual(len(list(Path(saved['folder']).iterdir())),1)
        encrypted=self.output(saved)
        with self.assertRaises(ValueError):perform(encrypted,'pdf_protect',options={'mode':'decrypt','password':'WRONG'})
        unlocked=perform(encrypted,'pdf_protect',options={'mode':'decrypt','password':'테스트123!'})
        with pymupdf.open(self.output(unlocked)) as doc:
            self.assertFalse(doc.needs_pass);self.assertIn('PAGE 1',doc[0].get_text())

    def test_markdown_html_epub_docx_pdf_and_cp949(self):
        source=self.root/'안내.md';source.write_text('# 체험학습\n\n안녕하세요. 준비물은 물입니다.\n\n- 필기도구\n- 도시락',encoding='utf-8')
        for target in ('html','epub','docx','pdf','txt'):
            result=perform(source,target);self.assertGreater(self.output(result).stat().st_size,20)
            if target=='pdf':
                with pymupdf.open(self.output(result)) as doc:self.assertIn('체험학습',doc[0].get_text().replace(' ',''))
            if target=='epub':
                back=perform(self.output(result),'txt');self.assertIn('도시락',self.output(back).read_text(encoding='utf-8-sig'))
                with zipfile.ZipFile(self.output(result)) as arc:self.assertEqual(arc.infolist()[0].compress_type,zipfile.ZIP_STORED)
        cp=self.root/'한글.txt';cp.write_bytes('한글 문서입니다'.encode('cp949'))
        result=perform(cp,'html');self.assertIn('한글 문서입니다',self.output(result).read_text(encoding='utf-8'))

    def test_subtitles_preserve_timing_and_text(self):
        source=self.root/'자막.srt';source.write_text('1\n00:00:01,250 --> 00:00:03,500\n안녕하세요\n\n2\n00:00:04,000 --> 00:00:06,000\n<b>두 번째</b>\n',encoding='utf-8')
        vtt=perform(source,'vtt');text=self.output(vtt).read_text(encoding='utf-8');self.assertTrue(text.startswith('WEBVTT'));self.assertIn('01.250',text)
        srt=perform(self.output(vtt),'srt');self.assertIn('00:00:03,500',self.output(srt).read_text(encoding='utf-8'))
        plain=perform(self.output(vtt),'txt');self.assertIn('두 번째',self.output(plain).read_text(encoding='utf-8'));self.assertNotIn('<b>',self.output(plain).read_text(encoding='utf-8'))

    def test_exported_html_has_no_scripts_or_remote_resources(self):
        source=self.root/'외부.md';source.write_text('# 제목\n<script>alert(1)</script>\n![image](https://example.com/pixel.png)\n[링크](javascript:alert(1))',encoding='utf-8')
        result=perform(source,'html');value=self.output(result).read_text(encoding='utf-8')
        self.assertNotIn('<script',value);self.assertNotIn('<img',value);self.assertNotIn('href=',value)
        self.assertIn('<h1>',value)

    def test_table_tsv_xlsx_ods_and_safe_cells(self):
        source=self.root/'표.tsv';source.write_text('이름\t값\n샘플\t=1+1\n다음\t쉼표,값\n',encoding='utf-8')
        result=perform(source,'xlsx')
        from openpyxl import load_workbook
        book=load_workbook(self.output(result));self.assertNotEqual(book.active['B2'].data_type,'f');book.close()
        ods=perform(source,'ods');back=perform(self.output(ods),'csv')
        value=self.output(back).read_text(encoding='utf-8-sig');self.assertIn('쉼표,값',value);self.assertIn('샘플',value)

    def test_archives_pack_unpack_nested_preview_and_guards(self):
        text=self.root/'자료.txt';text.write_text('자료',encoding='utf-8')
        for fmt in ('zip','tar','gz'):
            result=perform(text,'pack',options={'format':fmt},sources=[str(text)])
            extracted=perform(self.output(result),'unpack',preview=True)
            validate_stage(extracted);self.assertEqual(path_size(self.output(extracted)),len(text.read_bytes()))
            saved=commit_preview(extracted);self.assertEqual((self.output(saved)/text.name).read_text(encoding='utf-8'),'자료')
        archive=self.root/'악성.zip'
        for name in ('../escape.txt','C:/escape.txt','CON.txt','a/../../escape.txt'):
            with zipfile.ZipFile(archive,'w') as arc:arc.writestr(name,'NO')
            with self.assertRaises(ValueError):perform(archive,'unpack')
        with zipfile.ZipFile(archive,'w') as arc:
            arc.writestr('A.txt','a');arc.writestr('a.txt','b')
        with self.assertRaises(ValueError):perform(archive,'unpack')
        self.assertFalse((self.root.parent/'escape.txt').exists())
        self.assertFalse(list(self.root.glob('.docq-*')))


if __name__=='__main__':unittest.main()
