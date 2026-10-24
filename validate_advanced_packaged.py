import argparse,hashlib,json,shutil,subprocess,time
from pathlib import Path
import pymupdf
from PIL import Image,ImageDraw,ImageFont
from docx import Document
import win32api,win32con,win32gui
from win32com.client import Dispatch
from media import probe
parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path,default=Path('dist/DdalKkak.exe'));args=parser.parse_args()
exe=args.exe.resolve();folder=Path('validation/advanced-packaged').resolve();folder.mkdir(parents=True,exist_ok=True)
original=json.loads(Path('validation/upgrade-native/report.json').read_text(encoding='utf-8'))['.docx -> hwp']['files'][0]
hwp=folder/'사진 한글.hwp';shutil.copy2(original,hwp)
photo=folder/'인쇄 사진.png';im=Image.new('RGB',(1500,400),'white');ImageDraw.Draw(im).text((60,80),'딸깍변환 한글 인식 12345',font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',70),fill='black');im.save(photo)
pdf=folder/'세쪽.pdf'
with pymupdf.open() as doc:
 for i in range(3):doc.new_page().insert_text((60,80),'Page '+str(i+1))
 doc.save(pdf)
video=Path('validation/packaged-upgrade/영상 예시.mp4').resolve()
report={};before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (hwp,photo,pdf,video)}
foreground=win32gui.GetForegroundWindow();shell=Dispatch('Shell.Application');shell.MinimizeAll();time.sleep(.4)
origin=win32gui.GetForegroundWindow()
def job(source,target,**kwargs):
 request,response=folder/'request.json',folder/'response.json';response.unlink(missing_ok=True)
 request.write_text(json.dumps({'source':str(source),'target':target,'quality':'balanced','origin_hwnd':origin,**kwargs}),encoding='utf-8')
 child=subprocess.Popen([str(exe),'--worker',str(request),str(response)],creationflags=subprocess.CREATE_NO_WINDOW)
 child.wait(timeout=100)
 result=json.loads(response.read_text(encoding='utf-8'));assert result.get('ok'),result
 report[source.suffix+' -> '+target]=result
 print(source.suffix+' -> '+target+': PASS',flush=True)
 return result
try:
 result=job(hwp,'size',options={'max_mb':2});assert result['target_met'] and result['result_bytes']<result['original_bytes']
 compact=Path(result['files'][0]);text=job(compact,'txt');assert '문장' in Path(text['files'][0]).read_text(encoding='utf-8-sig')
 result=job(hwp,'pages',options={'pages':'1','format':'png'})
 with Image.open(result['files'][0]) as image:assert image.width>1000
 result=job(hwp,'merge_pdf',sources=[str(photo),str(hwp),str(pdf)])
 with pymupdf.open(result['files'][0]) as doc:assert len(doc)==5 and 'Page 1' in doc[2].get_text()
 result=job(photo,'ocr_docx');assert '12345' in '\n'.join(p.text for p in Document(result['files'][0]).paragraphs)
 result=job(pdf,'pages',options={'pages':'3,1','format':'pdf'})
 with pymupdf.open(result['files'][0]) as doc:assert [p.get_text().strip() for p in doc]==['Page 3','Page 1']
 result=job(video,'trim',options={'start':'.5','end':'1.5','format':'mp4'});assert abs(float(probe(result['files'][0])['format']['duration'])-1)<.15
 for path,digest in before.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
 report['originals_preserved']=True
 (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
finally:
 shell.UndoMinimizeALL()
 try:win32gui.SetForegroundWindow(foreground)
 except Exception:pass
