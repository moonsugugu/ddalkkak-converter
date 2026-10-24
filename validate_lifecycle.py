"""Actual NSIS lifecycle; public-release update and both Windows-list GUIs remain separate checks."""
import hashlib,json,os,shutil,subprocess,time,winreg
from pathlib import Path
from unittest.mock import patch
import win32api,win32con,win32event,win32file,win32gui
from win32com.client import Dispatch
from win32com.shell import shell,shellcon
from product import TITLE,VERSION,STATE_DIR
out=Path('validation/lifecycle').resolve();out.mkdir(parents=True,exist_ok=True)
setup=out/'Setup-under-test.exe'
installed=Path(os.environ['LOCALAPPDATA'])/'Programs/DocQ'
exe=installed/'DdalKkak.exe'
key_path=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Moonsunezip.DocQ'
desktop=Path(shell.SHGetFolderPath(0,shellcon.CSIDL_DESKTOPDIRECTORY,None,0))
startup=Path(shell.SHGetFolderPath(0,shellcon.CSIDL_STARTUP,None,0))
programs=Path(shell.SHGetFolderPath(0,shellcon.CSIDL_PROGRAMS,None,0))
settings=STATE_DIR/'settings.json';original=settings.read_bytes();(out/'original-settings.json').write_bytes(original)
report_path=out/'report.json'
resume='--resume' in __import__('sys').argv
report=json.loads(report_path.read_text(encoding='utf-8')) if resume and report_path.exists() else {}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def registry():
 try:
  with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key_path,0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
   return {n:winreg.QueryValueEx(key,n)[0] for n in ('DisplayName','DisplayVersion','DisplayIcon','InstallLocation','UninstallString','AppId')}
 except FileNotFoundError:return None
def run(path,*args,expected=0):
 process=subprocess.run([str(path),*args],timeout=150,creationflags=subprocess.CREATE_NO_WINDOW)
 assert process.returncode==expected,(path,process.returncode,expected)
 return process.returncode
def wait_for(predicate,seconds=35):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if predicate():return
  time.sleep(.1)
 assert predicate(),'Timed out waiting for installer lifecycle state'
def assert_installed():
 data=registry();assert data and data['DisplayName']==TITLE and data['DisplayVersion']==VERSION,data
 assert data['AppId']=='com.moonsunezip.docq'
 assert exe.is_file() and (installed/'Uninstall.exe').is_file()
 for link in (desktop/(TITLE+'.lnk'),programs/TITLE/(TITLE+'.lnk')):
  assert link.is_file(),link
  shortcut=Dispatch('WScript.Shell').CreateShortcut(str(link))
  assert Path(shortcut.TargetPath).resolve()==exe.resolve(),shortcut.TargetPath
  assert '.ico' in shortcut.IconLocation or '.exe' in shortcut.IconLocation
 return data
def assert_removed():
 wait_for(lambda:registry() is None and not exe.exists())
 assert registry() is None
 assert not exe.exists() and not (installed/'Uninstall.exe').exists()
 for link in (desktop/(TITLE+'.lnk'),startup/(TITLE+'.lnk'),programs/TITLE/(TITLE+'.lnk')):assert not link.exists(),link
 from windows import process_ids
 wait_for(lambda:not process_ids('DdalKkak.exe'))
 assert settings.read_bytes()==settings_with_fixture
 assert (out/'사용자 결과.txt').read_text(encoding='utf-8')=='보존해야 하는 결과'

def dialogs():
 values=[]
 def visit(hwnd,_):
  if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd)=='#32770' and TITLE in win32gui.GetWindowText(hwnd):
   buttons=[]
   def child(handle,_):
    if win32gui.GetClassName(handle)=='Button' and win32gui.IsWindowVisible(handle):buttons.append((handle,win32gui.GetWindowText(handle)))
   win32gui.EnumChildWindows(hwnd,child,None);values.append((hwnd,win32gui.GetWindowText(hwnd),buttons))
 win32gui.EnumWindows(visit,None)
 return values

def confirm_remover():
 clicked=False;deadline=time.monotonic()+35
 while time.monotonic()<deadline:
  for hwnd,title,buttons in dialogs():
   for handle,caption in buttons:
    if win32gui.IsWindowEnabled(handle) and (('제거' in caption and not clicked) or ('마침' in caption)):
     print('Uninstaller dialog:',title,caption,flush=True)
     win32gui.SendMessage(handle,win32con.BM_CLICK,0,0)
     if '제거' in caption:clicked=True
     time.sleep(.2)
  if clicked and registry() is None and not dialogs():return
  time.sleep(.1)
 assert clicked and registry() is None,dialogs()

settings_data=json.loads(original);settings_data['presets']=[{'name':'설치 검증 1MB','target':'size','quality':'balanced','options':{'max_mb':1}}]
settings_with_fixture=json.dumps(settings_data,ensure_ascii=False).encode('utf-8')
settings.write_bytes(settings_with_fixture)
(out/'사용자 결과.txt').write_text('보존해야 하는 결과',encoding='utf-8')
try:
 assert setup.is_file()
 run(setup,'/S');report['migration_or_upgrade']=assert_installed()
 assert settings.read_bytes()==settings_with_fixture
 if not resume:
  os.startfile(str(desktop/(TITLE+'.lnk')))
  popup_title=TITLE+' · 변환 메뉴'
  wait_for(lambda:bool(win32gui.FindWindow(None,popup_title)))
  assert not win32gui.IsWindowVisible(win32gui.FindWindow(None,popup_title))
  run(setup,'/S');assert_installed();assert settings.read_bytes()==settings_with_fixture
  report['same_installer_repair_and_shortcut_launch_hidden']=True
  # Keep the user's automatic-start choice when repairing.
  startup_link=startup/(TITLE+'.lnk');link_bytes=startup_link.read_bytes() if startup_link.exists() else None
  startup_link.unlink(missing_ok=True)
  run(setup,'/S');assert not startup_link.exists()
  if link_bytes:startup_link.write_bytes(link_bytes)
  report['startup_disabled_preserved_on_repair']=True
  before=digest(exe)
  busy=win32event.CreateEvent(None,True,True,r'Local\Moonsunezip.DocQ.Busy')
  try:run(setup,'/S',expected=1618)
  finally:win32event.ResetEvent(busy);win32api.CloseHandle(busy)
  assert digest(exe)==before and settings.read_bytes()==settings_with_fixture
  report['busy_event_guard_existing_files_preserved']=True
  # Test the actual version guard with a 2.9.0 fixture installer; its placeholder payload is never installed.
  guard=out/'Guard-2.9.0.exe';assert guard.exists()
  run(guard,'/S',expected=1638);assert digest(exe)==before
  report['older_installer_2_9_0_rejected_over_3_0_0']=True
  # Lock one owned FFmpeg file against renaming to force the real rollback path.
  lock=win32file.CreateFile(str(installed/'tools/ffmpeg.exe'),win32con.GENERIC_READ,win32con.FILE_SHARE_READ,None,win32con.OPEN_EXISTING,0,None)
  try:run(setup,'/S',expected=1603)
  finally:lock.Close()
  assert digest(exe)==before and settings.read_bytes()==settings_with_fixture
  assert not list(installed.glob('*.new')) and not list(installed.glob('*.previous'))
  assert not list((installed/'tools').glob('*.new')) and not list((installed/'tools').glob('*.previous'))
  assert_installed();report['locked_tool_rollback_preserves_working_install']=True
 # The registered command is what Windows Settings and Control Panel invoke.
 run(installed/'Uninstall.exe','/S');assert_removed();report['registered_quiet_uninstall_and_data_preservation']=True
 run(setup,'/S');assert_installed();assert settings.read_bytes()==settings_with_fixture
 # Exercise the app Settings button against its actual installed uninstaller.
 import tkinter as tk
 import app as app_module
 root=tk.Tk();event=win32event.CreateEvent(None,True,False,None);application=app_module.App(root,event)
 def widgets(widget):
  result=[]
  for child in widget.winfo_children():result += [child]+widgets(child)
  return result
 application.settings_window();root.update()
 with patch.object(app_module.sys,'frozen',True,create=True),patch.object(app_module.sys,'executable',str(exe)):
  next(w for w in widgets(root) if w.winfo_class()=='TButton' and w.cget('text')=='앱 제거…').invoke()
 application.quit(force=True);win32api.CloseHandle(event)
 confirm_remover();assert_removed();report['app_settings_action_normal_uninstaller_confirmed']=True
 report['windows_settings_and_control_panel_list_gui']='Not individually clicked; shared registered uninstall command and metadata checked.'
 report['public_release_update']='Not published; network failure, platform/SemVer/hash and local installer transitions checked separately.'
finally:
 # Restore the real user's settings and leave a usable installed tray app.
 settings.write_bytes(original)
 if not exe.exists() or not registry():run(setup,'/S')
 settings.write_bytes(original)
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
