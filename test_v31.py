import hashlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pymupdf
from PIL import Image,ImageDraw,ImageFont
from converter import perform
from job_output import commit_preview,discard_preview
from hotkeys import parse_hotkey,event_hotkey
from scan_tools import skew_angle
from app import load_settings


class HotkeyTests(unittest.TestCase):
    def test_all_function_keys_and_exact_modifiers(self):
        for i in range(1,25):
            self.assertEqual(parse_hotkey(f'F{i}').vk,111+i)
        spec=parse_hotkey(' shift + control + p ')
        self.assertEqual(spec.name,'Ctrl+Shift+P')
        self.assertTrue(spec.matches(80,{'Ctrl','Shift'}))
        for modifiers in ({'Ctrl'},{'Ctrl','Shift','Alt'},{'Ctrl','Shift','WinLeft'}):
            self.assertFalse(spec.matches(80,modifiers))
        self.assertEqual(parse_hotkey('Alt+9').vk,57)
        self.assertEqual(parse_hotkey('space').name,'Space')
        self.assertEqual(event_hotkey(SimpleNamespace(keycode=80,state=5)),'Ctrl+Shift+P')
        self.assertEqual(event_hotkey(SimpleNamespace(keycode=80,state=13)),'Ctrl+Shift+P')
        self.assertEqual(event_hotkey(SimpleNamespace(keycode=80,state=0x20004)),'Ctrl+Alt+P')

    def test_invalid_and_reserved_input_does_not_replace_key(self):
        for key in ('','Ctrl','Ctrl+Ctrl+P','F25','Alt+F4','Ctrl+C','Win+P','F12+P','Escape'):
            with self.assertRaises(ValueError):parse_hotkey(key)

    def test_settings_migrate_and_keep_custom_shortcut_and_tutorial(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.STATE_DIR',Path(tmp)):
            self.assertEqual(load_settings()['key'],'F12')
            self.assertFalse(load_settings()['tutorial_seen'])
            file=Path(tmp)/'settings.json'
            file.write_text(json.dumps({'version':2,'key':'F9','quality':'high','presets':[]}),encoding='utf-8')
            self.assertEqual(load_settings()['key'],'F9')
            file.write_text(json.dumps({'version':3,'key':'Ctrl+Alt+K','quality':'small','tutorial_seen':True,'preview':False}),encoding='utf-8')
            saved=load_settings()
            self.assertEqual(saved['key'],'Ctrl+Alt+K');self.assertTrue(saved['tutorial_seen']);self.assertFalse(saved['preview'])
            file.write_text(json.dumps({'version':3,'key':'Ctrl+C'}),encoding='utf-8')
            self.assertEqual(load_settings()['key'],'F12')


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.photo=self.root/'원본.jpg'
        Image.effect_noise((600,450),60).convert('RGB').save(self.photo,quality=100)
        self.digest=hashlib.sha256(self.photo.read_bytes()).hexdigest()
        self.pdf=self.root/'다섯 쪽.pdf'
        with pymupdf.open() as doc:
            for i in range(5):doc.new_page().insert_text((50,80),'PAGE '+str(i+1))
            doc.save(self.pdf)

    def tearDown(self):self.tmp.cleanup()

    def test_preview_cancel_creates_no_published_folder(self):
        result=perform(self.photo,'png',preview=True)
        self.assertTrue(result['_pending'])
        self.assertFalse(list(self.root.glob('*_변환*')))
        self.assertTrue(Path(result['files'][0]).exists())
        discard_preview(result)
        self.assertFalse(list(self.root.glob('.docq-*')))
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).hexdigest(),self.digest)

    def test_preview_save_and_collision_keep_only_outputs(self):
        occupied=self.root/'원본_변환';occupied.mkdir();(occupied/'keep.txt').write_text('keep')
        result=commit_preview(perform(self.photo,'png',preview=True))
        self.assertEqual(Path(result['folder']).name,'원본_변환_2')
        self.assertEqual([p.name for p in Path(result['folder']).iterdir()],['원본.png'])
        self.assertNotIn('_pending',result)
        self.assertEqual((occupied/'keep.txt').read_text(),'keep')
        with Image.open(result['files'][0]) as image:self.assertEqual(image.size,(600,450))

    def test_cancel_rejects_foreign_directory(self):
        foreign=self.root/'user-data';foreign.mkdir();file=foreign/'precious.txt';file.write_text('keep')
        with self.assertRaises(ValueError):discard_preview({'_pending':True,'source':str(self.photo),'_stage':str(foreign),'_token':'bad','files':[str(file)]})
        self.assertEqual(file.read_text(),'keep')

    def test_split_page_counts_order_and_original_preserved(self):
        original=self.pdf.read_bytes()
        for chunk,counts in ((1,[1]*5),(2,[2,2,1]),(5,[5]),(10,[5])):
            result=perform(self.pdf,'split_pdf',options={'chunk_pages':chunk})
            found=[];actual=[]
            for path in result['files']:
                with pymupdf.open(path) as doc:
                    actual.append(len(doc));found += [page.get_text().strip() for page in doc]
            self.assertEqual(actual,counts)
            self.assertEqual(found,['PAGE '+str(i+1) for i in range(5)])
        self.assertEqual(self.pdf.read_bytes(),original)
        for value in (0,-1,1.5,'1.5',10001):
            with self.assertRaises(ValueError):perform(self.pdf,'split_pdf',options={'chunk_pages':value})

    def test_split_preview_discards_all_parts(self):
        result=perform(self.pdf,'split_pdf',options={'chunk_pages':2},preview=True)
        self.assertEqual(len(result['files']),3)
        self.assertEqual(list(result['source_page_starts'].values()),[0,2,4])
        discard_preview(result);self.assertFalse(list(self.root.glob('.docq-*')))

    def test_split_names_keep_order_past_one_thousand_pages(self):
        large=self.root/'긴 문서.pdf'
        with pymupdf.open() as doc:
            for _ in range(1001):doc.new_page()
            doc.save(large)
        result=perform(large,'split_pdf',options={'chunk_pages':500})
        self.assertEqual([Path(p).stem for p in result['files']],['긴 문서_0001-0500','긴 문서_0501-1000','긴 문서_1001'])

    def test_scan_corrects_known_angle_and_preserves_original(self):
        source=self.root/'기울어진 사진.png'
        image=Image.new('RGB',(800,1000),'#dddddd');d=ImageDraw.Draw(image)
        font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',32)
        for i in range(14):d.text((80,80+i*53),f'딸깍변환 스캔 보정 시험 문장 {i+1}',font=font,fill='#333333')
        image.rotate(6,expand=True,fillcolor='white').save(source)
        before=source.read_bytes()
        result=perform(source,'scan',options={'mode':'bw','format':'png'})
        self.assertAlmostEqual(result['scan_angles'][0],-6,delta=1)
        with Image.open(result['files'][0]) as corrected:
            self.assertLess(abs(skew_angle(corrected)),1)
            self.assertLessEqual(len(corrected.getcolors()),2)
            self.assertLess(corrected.width,image.width)
        self.assertEqual(source.read_bytes(),before)

    def test_scan_output_pdf_and_tiny_white_image(self):
        result=perform(self.photo,'scan',options={'format':'pdf','deskew':False,'trim':False,'mode':'color'})
        with pymupdf.open(result['files'][0]) as pdf:self.assertEqual(len(pdf),1)
        tiny=self.root/'tiny.png';Image.new('RGB',(2,2),'white').save(tiny)
        result=perform(tiny,'scan',options={'mode':'gray'})
        with Image.open(result['files'][0]) as image:self.assertEqual(image.size,(2,2))


if __name__=='__main__':unittest.main()
