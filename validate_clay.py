import json,time,tkinter as tk
from pathlib import Path
import win32event,win32api,win32con
from PIL import Image,ImageGrab
from app import App,STATE_DIR
root=tk.Tk()
event=win32event.CreateEvent(None,True,False,None)
settings=STATE_DIR/'settings.json'
before=settings.read_bytes() if settings.exists() else None
out=Path('validation/clay-ui');out.mkdir(parents=True,exist_ok=True)
source=out/'사진 예시.jpg';Image.new('RGB',(600,400),'pink').save(source)
app=App(root,event)
def pump(s=.25):
 end=time.monotonic()+s
 while time.monotonic()<end:root.update();time.sleep(.02)
try:
 app.settings['presets']=[];app.settings['usage']={}
 app.set_files([source],point=(900,520));pump()
 assert not root.winfo_viewable() and app.popup.winfo_viewable()
 backdrop=tk.Toplevel(root);backdrop.overrideredirect(True);backdrop.configure(bg='#e5e0ef');backdrop.geometry(f'460x460+{app.popup.winfo_rootx()}+{app.popup.winfo_rooty()}');app.popup.lift();pump()
 assert app.visible_choices[:3]==['pdf','png','compress']
 snapshots=[]
 first=list(app.visible_choices)
 for i in range((len(app.choices)+7)//8):
  x,y=app.popup.winfo_rootx(),app.popup.winfo_rooty()
  path=out/f'menu-{i+1}.png';ImageGrab.grab((x,y,x+460,y+460)).save(path);snapshots.append(str(path.resolve()))
  app.popup.event_generate('<MouseWheel>',delta=-120);pump()
 assert app.page==0
 app.popup.event_generate('<Right>');pump();assert app.page==1
 app.popup.event_generate('<Left>');pump();assert app.page==0
 point=app.target_points['png'];x,y=app.popup.winfo_rootx(),app.popup.winfo_rooty()
 # Click well away from the label: the entire clay button must be clickable.
 win32api.SetCursorPos((x+round(point[0])+24,y+round(point[1])))
 win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,0,0);win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,0,0)
 pump();assert app.busy and not app.popup.winfo_viewable()
 deadline=time.monotonic()+25
 while app.busy and time.monotonic()<deadline:pump(.1)
 assert app.results and not app.errors,app.errors
 with Image.open(app.results[0]['files'][0]) as im:assert im.format=='PNG'
 app.add_preset('발송용 1MB','size','balanced',{'max_mb':1})
 app.set_files([source],point=(900,520));pump();assert app.visible_choices[0]=='fav:0'
 app.hide();pump();assert not app.popup.winfo_viewable()
 (out/'report.json').write_text(json.dumps({'clay':snapshots,'wheel_and_arrows':True,'full_button_click':True,'conversion':app.results,'favorites_first':True},ensure_ascii=False,indent=2),encoding='utf-8')
 print('Clay UI, paging, full-button click, PNG conversion and favorite ordering passed')
finally:
 app.quit(force=True)
 if before is not None:settings.write_bytes(before)
 win32api.CloseHandle(event)
