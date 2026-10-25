import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from advanced import page_order, timestamp, actions
from converter import perform
from media import executable, probe
from updater import semver, validate, download
from product import APP_ID


class AdvancedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.pdf=self.root/'순서.pdf'
        with pymupdf.open() as doc:
            for i in range(1,5):
                doc.new_page().insert_text((50,70),'Page '+str(i))
            doc.save(self.pdf)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ranges_and_time_validation(self):
        self.assertEqual(page_order('4,2-3,1',4),[3,1,2,0])
        self.assertEqual(page_order('4-2',4),[3,2,1])
        for value in ['0','5','1,','1--3','abc','-1']:
            with self.assertRaises(ValueError):page_order(value,4)
        self.assertEqual(timestamp('01:02:03.5'),3723.5)
        for value in ['nan','inf','1:99','-1']:
            with self.assertRaises(ValueError):timestamp(value)

    def test_page_reorder_remove_and_selected_png(self):
        before=self.pdf.read_bytes()
        result=perform(self.pdf,'pages',options={'pages':'4,2-3','format':'pdf'})
        with pymupdf.open(result['files'][0]) as doc:
            self.assertEqual([p.get_text().strip() for p in doc],['Page 4','Page 2','Page 3'])
        result=perform(self.pdf,'pages',options={'pages':'2,4','format':'png'})
        self.assertEqual(len(result['files']),2)
        with Image.open(result['files'][0]) as image:self.assertGreater(image.width,500)
        self.assertEqual(self.pdf.read_bytes(),before)
        with self.assertRaises(ValueError):perform(self.pdf,'pages',options={'pages':'99'})
        self.assertFalse(list(self.root.glob('.docq-*')))

    def test_mixed_merge_order_and_originals(self):
        image=self.root/'사진.png'
        Image.new('RGB',(300,200),'pink').save(image)
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [self.pdf,image]}
        result=perform(self.pdf,'merge_pdf',sources=[str(image),str(self.pdf)])
        with pymupdf.open(result['files'][0]) as doc:
            self.assertEqual(len(doc),5)
            self.assertFalse(doc[0].get_text().strip())
            self.assertIn('Page 1',doc[1].get_text())
        for path,digest in before.items():self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
        self.assertIn('merge_pdf',actions([self.pdf,image]))

    def test_target_size_and_unreachable_goal(self):
        image=self.root/'큰사진.jpg'
        Image.effect_noise((1400,1000),70).convert('RGB').save(image,quality=100)
        before=image.read_bytes()
        result=perform(image,'size',options={'max_mb':.08})
        self.assertTrue(result['target_met'])
        self.assertLessEqual(Path(result['files'][0]).stat().st_size,int(.08*1024*1024))
        self.assertEqual(image.read_bytes(),before)
        result=perform(self.pdf,'size',options={'max_mb':.001})
        self.assertEqual(result['target_met'],result['result_bytes']<=result['target_bytes'])
        with pymupdf.open(result['files'][0]) as doc:self.assertIn('Page 1',doc[0].get_text())

    def test_windows_korean_ocr_photo_and_scanned_pdf(self):
        image=self.root/'한글 인쇄.png'
        picture=Image.new('RGB',(1500,400),'white')
        font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',70)
        ImageDraw.Draw(picture).text((60,70),'딸깍변환 글자 인식 시험 12345',font=font,fill='black')
        picture.save(image)
        result=perform(image,'ocr_txt')
        text=Path(result['files'][0]).read_text(encoding='utf-8-sig')
        self.assertIn('12345',text)
        self.assertIn('글자',text)
        pdf=self.root/'스캔.pdf'
        with pymupdf.open() as doc:
            page=doc.new_page(width=750,height=200)
            page.insert_image(page.rect,filename=str(image))
            doc.save(pdf)
        result=perform(pdf,'ocr_docx')
        self.assertIn('12345','\n'.join(p.text for p in Document(result['files'][0]).paragraphs))

    @unittest.skipUnless(executable(),'FFmpeg unavailable')
    def test_trim_and_target_video_size(self):
        import subprocess
        source=self.root/'clip.mp4'
        subprocess.run([executable(),'-v','error','-y','-f','lavfi','-i','testsrc2=size=320x240:rate=15',
                        '-f','lavfi','-i','sine=frequency=440','-t','3','-c:v','libx264','-crf','1',
                        '-threads','2','-c:a','aac',str(source)],check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        for fmt in ('mp4','gif','mp3'):
            result=perform(source,'trim',options={'start':'.5','end':'1.5','format':fmt})
            path=Path(result['files'][0])
            if fmt=='gif':
                with Image.open(path) as gif:self.assertGreater(gif.n_frames,3)
            else:
                duration=float(probe(path)['format']['duration'])
                self.assertAlmostEqual(duration,1,delta=.15)
        result=perform(source,'size',options={'max_mb':.09})
        self.assertEqual(result['target_met'],result['result_bytes']<=result['target_bytes'])
        with self.assertRaises(ValueError):perform(source,'trim',options={'start':9,'end':10})


class UpdateTests(unittest.TestCase):
    def metadata(self,payload=b'A'*2048):
        return {'app_id':APP_ID,'version':'3.3.0','os':'windows','arch':'x86','channel':'stable',
                'url':'https://github.com/moonsugugu/ddalkkak-converter/releases/download/v3.3.0/setup.exe',
                'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}

    def test_semver_and_platform_and_hash_required(self):
        self.assertGreater(semver('3.10.0'),semver('3.9.0'))
        self.assertGreater(semver('3.0.0'),semver('3.0.0-rc.1'))
        self.assertGreater(semver('3.0.0-rc.10'),semver('3.0.0-rc.2'))
        self.assertTrue(validate(self.metadata())['available'])
        for k,v in [('os','mac'),('arch','x64'),('sha256',''),('url','http://evil.com/a.exe'),('version','2.0')]:
            with self.assertRaises(ValueError):validate({**self.metadata(),k:v})
        self.assertFalse(validate({**self.metadata(),'version':'2.9.0'})['available'])

    def test_verified_download_and_bad_file_preserve_state(self):
        class Reply(io.BytesIO):
            url='https://release-assets.githubusercontent.com/test'
        with tempfile.TemporaryDirectory() as tmp, patch('updater.STATE_DIR',Path(tmp)):
            original=Path(tmp)/'settings.json'
            original.write_text('preserved')
            with patch('urllib.request.urlopen',return_value=Reply(b'A'*2048)):
                result=download(self.metadata())
                self.assertEqual(result.read_bytes(),b'A'*2048)
            with patch('urllib.request.urlopen',return_value=Reply(b'B'*2048)):
                with self.assertRaisesRegex(ValueError,'검증'):download(self.metadata())
            self.assertEqual(original.read_text(),'preserved')
            self.assertEqual(result.read_bytes(),b'A'*2048)
            self.assertFalse(list((Path(tmp)/'updates').glob('*.part')))


if __name__=='__main__':unittest.main()
