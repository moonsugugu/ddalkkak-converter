import hashlib,json,time,tkinter as tk,uuid
from pathlib import Path
from unittest.mock import patch
import win32api,win32con,win32event,win32gui
from PIL import Image,ImageDraw,ImageFont,ImageGrab
import pymupdf
from app import App,load_settings
from validate_windows import focus_window
out=Path('validation/v31').resolve();out.mkdir(parents=True,exist_ok=True)
profile=out/('profile-'+uuid.uuid4().hex[:6]);profile.mkdir()
fixtures=out/('fixtures-'+uuid.uuid4().hex[:6]);fixtures.mkdir()
photo=fixtures/'기울어진 스캔.png'
im=Image.new('RGB',(800,1000),'#dddddd');d=ImageDraw.Draw(im);font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',32)
for i in range(14):d.text((80,80+i*53),f'딸깍변환 스캔 보정 시험 문장 {i+1}',font=font,fill='#333333')
im.rotate(6,expand=True,fillcolor='white').save(photo)
digest=hashlib.sha256(photo.read_bytes()).hexdigest()
pdf=fixtures/'다섯 쪽.pdf'
with pymupdf.open() as doc:
 for i in range(5):doc.new_page().insert_text((50,80),f'PAGE {i+1}')
 doc.save(pdf)
def widgets(parent):
 result=[]
 for child in parent.winfo_children():result += [child]+widgets(child)
 return result
def button(parent,text):return next(w for w in widgets(parent) if w.winfo_class()=='TButton' and w.cget('text')==text)
report={}
with patch('app.STATE_DIR',profile):
 root=tk.Tk();event=win32event.CreateEvent(None,True,False,None);app=App(root,event)
 def pump(s=.15):
  end=time.monotonic()+s
  while time.monotonic()<end:root.update();time.sleep(.015)
 def wait(fn,timeout=40):
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   if fn():return
   pump(.05)
  assert fn(),'UI did not reach expected state: '+str(app.errors)
 def screenshot(window,name):
  window.update();x,y=window.winfo_rootx(),window.winfo_rooty()
  ImageGrab.grab((x,y,x+window.winfo_width(),y+window.winfo_height())).save(out/name)
 def convert(path,target,chunk=None):
  app.set_files([path],point=(900,500));pump()
  if target in {'scan','split_pdf'}:
   def accept():
    dialogs=[w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title().endswith('변환 설정')]
    window=dialogs[-1]
    if chunk:
     entry=next(w for w in widgets(window) if w.winfo_class()=='TEntry');entry.delete(0,'end');entry.insert(0,str(chunk))
    button(window,'변환 시작').invoke()
   root.after(200,accept)
  app.convert(target)
  wait(lambda:app.review_window is not None or not app.busy)
  assert app.review_window and not app.errors,app.errors
  return app.review_window
 try:
  wait(lambda:app.setup_popup is not None,5)
  window=app.setup_popup
  assert not app.shortcut.enabled and not root.winfo_viewable()
  window.editor.arm();pump();focus_window(win32gui.GetAncestor(window.winfo_id(),2));window.editor.display.focus_force();pump(.1)
  try:
   for key in (win32con.VK_CONTROL,win32con.VK_SHIFT,ord('P')):win32api.keybd_event(key,0,0,0)
   pump(.12)
  finally:
   for key in (ord('P'),win32con.VK_SHIFT,win32con.VK_CONTROL):win32api.keybd_event(key,0,win32con.KEYEVENTF_KEYUP,0)
  pump();assert window.editor.read()=='Ctrl+Shift+P',window.editor.read()
  screenshot(window,'tutorial.png');button(window,'시작하기').invoke();pump()
  assert app.settings['tutorial_seen'] and app.shortcut.key=='Ctrl+Shift+P' and app.shortcut.enabled
  report['first_tutorial_and_actual_key_capture']=True
  review=convert(photo,'scan')
  assert app.results[0]['_pending'] and not list(fixtures.glob('*_변환*'))
  screenshot(review.window,'scan-preview.png')
  review.cancel();wait(lambda:not app.busy)
  assert not app.results and not list(fixtures.glob('.docq-*'))
  assert hashlib.sha256(photo.read_bytes()).hexdigest()==digest
  report['preview_cancel_no_published_files']=True
  review=convert(photo,'jpg');review.save();wait(lambda:not app.busy)
  assert app.results and not app.results[0].get('_pending')
  with Image.open(app.results[0]['files'][0]) as image:assert image.format=='JPEG'
  report['preview_save_commits_only_final_output']=True
  review=convert(pdf,'split_pdf',2)
  result=app.results[0];assert len(result['files'])==3
  review.after.select.current(1);review.after.selected();assert review.before.page==2
  review.after.turn(1);assert review.before.page==3
  screenshot(review.window,'pdf-split-preview.png')
  review.save();wait(lambda:not app.busy)
  counts=[]
  for path in app.results[0]['files']:
   with pymupdf.open(path) as doc:counts.append(len(doc))
  assert counts==[2,2,1]
  report['pdf_split_preview_alignment_and_save']=counts
  app.events.put(('hotkey_setup',None));wait(lambda:app.setup_popup is not None)
  app.setup_popup.editor.reset();button(app.setup_popup,'적용').invoke();pump()
  assert app.shortcut.key=='F12' and load_settings()['key']=='F12'
  report['tray_customization_and_f12_reset']=True
  app.maybe_tutorial();pump();assert app.setup_popup is None
  report['tutorial_does_not_repeat_after_completion']=True
 finally:
  app.quit(force=True);win32api.CloseHandle(event)
 root=tk.Tk();event=win32event.CreateEvent(None,True,False,None);app=App(root,event)
 try:
  pump(1);assert app.setup_popup is None and not root.winfo_viewable()
  report['restart_keeps_shortcut_and_tutorial_state']=True
 finally:app.quit(force=True);win32api.CloseHandle(event)
report['profile']=str(profile);report['fixtures']=str(fixtures)
(out/'ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
