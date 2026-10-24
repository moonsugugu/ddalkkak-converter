"""Exercise the visible maintenance page and cancel the standard remover safely."""
import json,subprocess,time,winreg
from pathlib import Path
import win32gui,win32con
TITLE='딸깍변환'
setup=Path('dist/DdalKkak-Setup-3.0.0.exe').resolve()
key=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Moonsunezip.DocQ'
def version():
 with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key) as k:return winreg.QueryValueEx(k,'DisplayVersion')[0]
def windows(suffix):
 values=[]
 win32gui.EnumWindows(lambda h,_:values.append(h) if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h)=='#32770' and win32gui.GetWindowText(h).strip()==TITLE+' '+suffix else None,None)
 return values
def controls(hwnd):
 values=[]
 win32gui.EnumChildWindows(hwnd,lambda h,_:values.append((h,win32gui.GetClassName(h),win32gui.GetWindowText(h))) if win32gui.IsWindowVisible(h) else None,None)
 return values
def wait_for(fn):
 for _ in range(200):
  value=fn()
  if value:return value
  time.sleep(.05)
 raise AssertionError('Maintenance UI did not reach the expected page')
assert version()=='3.0.0'
p=subprocess.Popen([str(setup)])
hwnd=wait_for(lambda:windows('설치'))[0]
rows=controls(hwnd)
welcome=next(h for h,cls,text in rows if cls=='Button' and '다음' in text)
win32gui.SendMessage(welcome,win32con.BM_CLICK,0,0)
wait_for(lambda:any(text=='딸깍변환 제거' for _,_,text in controls(hwnd)))
rows=controls(hwnd)
assert any('다시 설치 / 복구' in text for _,_,text in rows)
button=win32gui.GetDlgItem(hwnd,1)
initial=win32gui.GetWindowText(button)
remove=next(h for h,cls,text in rows if cls=='Button' and text=='딸깍변환 제거')
win32gui.SendMessage(remove,win32con.BM_CLICK,0,0)
assert win32gui.GetWindowText(button)=='제거'
win32gui.SendMessage(button,win32con.BM_CLICK,0,0)
remover=wait_for(lambda:windows('제거'))[0]
assert version()=='3.0.0'
cancel=next(h for h,cls,text in controls(remover) if cls=='Button' and text=='취소')
win32gui.SendMessage(cancel,win32con.BM_CLICK,0,0)
wait_for(lambda:not windows('제거') and not windows('설치'))
assert version()=='3.0.0'
report={'same_version_repair_choice':True,'initial_action_label':initial,'remove_action_label':'제거',
        'remove_choice_launches_standard_uninstaller':True,'cancel_preserves_installation':True}
Path('validation/lifecycle/maintenance-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
