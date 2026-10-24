import json,time,tkinter as tk
from pathlib import Path
import win32event,win32api
from PIL import Image
import pymupdf
from app import App,STATE_DIR
out=Path('validation/dialogs').resolve();out.mkdir(parents=True,exist_ok=True)
photo=out/'큰사진.jpg';Image.effect_noise((1000,800),70).convert('RGB').save(photo,quality=100)
pdf=out/'문서.pdf'
with pymupdf.open() as doc:
 for i in range(3):doc.new_page().insert_text((50,80),f'Page {i+1}')
 doc.save(pdf)
settings=STATE_DIR/'settings.json';before=settings.read_bytes()
root=tk.Tk();event=win32event.CreateEvent(None,True,False,None);app=App(root,event);report={}
def pump(s=.2):
 end=time.monotonic()+s
 while time.monotonic()<end:root.update();time.sleep(.02)
def all_widgets(widget):
 result=[]
 for child in widget.winfo_children():result += [child]+all_widgets(child)
 return result
def start(target, paths, values, preset='', reorder=False):
 app.set_files(paths,point=(900,500));pump()
 def fill():
  dialogs=[w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title().endswith('변환 설정')]
  dialog=dialogs[-1];widgets=all_widgets(dialog)
  entries=[w for w in widgets if w.winfo_class()=='TEntry']
  for entry,value in zip(entries,values+[preset]):entry.delete(0,'end');entry.insert(0,value)
  if reorder:
   listing=next(w for w in widgets if w.winfo_class()=='Listbox');listing.selection_clear(0,'end');listing.selection_set(1)
   next(w for w in widgets if w.winfo_class()=='TButton' and w.cget('text')=='위로 ↑').invoke()
  next(w for w in widgets if w.winfo_class()=='TButton' and w.cget('text')=='변환 시작').invoke()
 root.after(300,fill);app.convert(target)
 deadline=time.monotonic()+40
 while app.busy and time.monotonic()<deadline:pump()
 assert app.results and not app.errors,(target,app.errors)
 assert not app.popup.winfo_viewable() and not root.winfo_viewable()
 report[target]=app.results[0]
 return app.results[0]
try:
 result=start('size',[photo],['.06'],'사진 60KB');assert result['target_met']
 assert app.settings['presets'][0]['options']['max_mb']==.06
 result=start('pages',[pdf],['3,1'])
 with pymupdf.open(result['files'][0]) as doc:assert [p.get_text().strip() for p in doc]==['Page 3','Page 1']
 result=start('merge_pdf',[photo,pdf],[],reorder=True)
 with pymupdf.open(result['files'][0]) as doc:assert 'Page 1' in doc[0].get_text() and len(doc)==4
 app.settings_window();pump();dialogs=[w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title().endswith('설정')];assert dialogs
 dialogs[-1].destroy()
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Options dialog, target-size preset persistence, PDF reorder and mixed merge ordering passed')
finally:
 app.quit(force=True);settings.write_bytes(before);win32api.CloseHandle(event)
