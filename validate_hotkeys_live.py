import json,time,tkinter as tk,uuid
from pathlib import Path
from unittest.mock import patch
import win32api,win32con,win32event,win32gui
from win32com.client import Dispatch
from win32com.shell import shell,shellcon
from PIL import Image
from app import App
from hotkeys import parse_hotkey,MOD_CODES
from windows import automation
out=Path('validation/v31').resolve();out.mkdir(exist_ok=True)
profile=out/('keys-'+uuid.uuid4().hex[:6]);profile.mkdir()
(profile/'settings.json').write_text(json.dumps({'version':3,'key':'Ctrl+Shift+P','tutorial_seen':True,'preview':False}),encoding='utf-8')
desktop=Path(shell.SHGetFolderPath(0,shellcon.CSIDL_DESKTOPDIRECTORY,None,0)).resolve()
fixture=desktop/('딸깍변환_키검증_'+uuid.uuid4().hex[:8]+'.jpg');Image.new('RGB',(50,50),'pink').save(fixture)
shell.SHChangeNotify(shellcon.SHCNE_CREATE,shellcon.SHCNF_PATHW|shellcon.SHCNF_FLUSH,str(fixture),None)
foreground=win32gui.GetForegroundWindow();shell_app=Dispatch('Shell.Application');selected_before=[];selection=None;report={}
with patch('app.STATE_DIR',profile):
 root=tk.Tk();event=win32event.CreateEvent(None,True,False,None);app=App(root,event)
 def pump(s=.2):
  until=time.monotonic()+s
  while time.monotonic()<until:root.update();time.sleep(.015)
 def press(vk):
  win32api.keybd_event(vk,0,0,0);pump(.07);win32api.keybd_event(vk,0,win32con.KEYEVENTF_KEYUP,0)
 try:
  shell_app.MinimizeAll();pump(.4)
  views=[]
  def find(handle,_):
   view=win32gui.FindWindowEx(handle,0,'SHELLDLL_DefView',None)
   if view:views.append(view)
  win32gui.EnumWindows(find,None)
  listing=win32gui.FindWindowEx(views[0],0,'SysListView32',None)
  uia,module=automation();container=uia.ElementFromHandle(listing)
  old=container.GetCurrentPattern(10001).QueryInterface(module.IUIAutomationSelectionPattern).GetCurrentSelection()
  selected_before=[old.GetElement(i) for i in range(old.Length)]
  item=None
  for _ in range(150):
   children=container.FindAll(4,uia.CreatePropertyCondition(30003,50007))
   for i in range(children.Length):
    candidate=children.GetElement(i)
    if candidate.CurrentName in {fixture.name,fixture.stem}:item=candidate;break
   if item:break
   pump(.1)
  assert item,'Fixture icon not found'
  selection=item.GetCurrentPattern(10010).QueryInterface(module.IUIAutomationSelectionItemPattern)
  def focus_file():
   app.hide();selection.Select();shell_app.MinimizeAll();pump(.15)
   item.SetFocus();rect=item.CurrentBoundingRectangle
   win32api.SetCursorPos((int((rect.left+rect.right)/2),int((rect.top+rect.bottom)/2)))
   win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,0,0);win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,0,0);pump(.1)
   assert win32gui.GetClassName(win32gui.GetForegroundWindow()) in {'Progman','WorkerW'}
  focus_file();press(win32con.VK_F12);pump(.2);assert not app.popup.winfo_viewable()
  report['previous_f12_no_longer_triggers_custom_key']=True
  for name in ('Ctrl+Shift+P','Alt+F10','F16','A'):
   app.apply_hotkey(name);focus_file();spec=parse_hotkey(name);before=app.menu_request
   try:
    for mod in spec.modifiers:win32api.keybd_event(MOD_CODES[mod],0,0,0)
    pump(.08)
    win32api.keybd_event(spec.vk,0,0,0);pump(.1)
    for _ in range(3):win32api.keybd_event(spec.vk,0,0,0)
    pump(.15)
   finally:
    win32api.keybd_event(spec.vk,0,win32con.KEYEVENTF_KEYUP,0)
    for mod in spec.modifiers:win32api.keybd_event(MOD_CODES[mod],0,win32con.KEYEVENTF_KEYUP,0)
   deadline=time.monotonic()+5
   while not app.popup.winfo_viewable() and time.monotonic()<deadline:pump(.05)
   assert app.popup.winfo_viewable() and fixture in app.files,(name,app.files,app.shortcut.error)
   assert app.menu_request==before+1,(name,app.menu_request,before)
   report[name]={'explorer_selection_menu':True,'held_repeat_suppressed':True}
  app.apply_hotkey('F16');focus_file();press(win32con.VK_F2);pump(.2)
  assert uia.GetFocusedElement().CurrentControlType==50004,'Rename editor did not open'
  press(127);pump(.2);assert not app.popup.winfo_viewable();press(win32con.VK_ESCAPE)
  assert fixture.exists();report['rename_editor_untouched']=True
  app.apply_hotkey('F12')
 finally:
  app.quit(force=True);win32api.CloseHandle(event)
  for key in (16,17,18):win32api.keybd_event(key,0,win32con.KEYEVENTF_KEYUP,0)
  try:
   for i,element in enumerate(selected_before):
    old=element.GetCurrentPattern(10010).QueryInterface(module.IUIAutomationSelectionItemPattern)
    old.Select() if i==0 else old.AddToSelection()
   if not selected_before and selection:selection.RemoveFromSelection()
  except Exception:pass
  if fixture.resolve().parent==desktop and fixture.name.startswith('딸깍변환_키검증_'):fixture.unlink(missing_ok=True)
  shell_app.UndoMinimizeALL()
  try:win32gui.SetForegroundWindow(foreground)
  except Exception:pass
(out/'hotkeys-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
