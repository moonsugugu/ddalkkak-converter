"""Exercise the packaged tray app using one generated desktop file and real input."""
import argparse
import ctypes
import json
import math
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pymupdf
import pythoncom
import win32api
import win32con
import win32event
import win32gui
from win32com.client import Dispatch, DispatchEx, gencache
from win32com.shell import shell, shellcon
from PIL import Image, ImageDraw, ImageGrab

from validate_windows import focus_window, key
from windows import automation, process_ids
from converter import targets
from media import probe
from app import menu_choices, load_settings
from product import TITLE


def pump(seconds):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        pythoncom.PumpWaitingMessages()
        time.sleep(.025)


def click(point):
    win32api.SetCursorPos(point)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)


def main():
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:pass
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, default=Path('dist/DdalKkak.exe'))
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--preserve', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--target', default='pdf')
    parser.add_argument('--options-escape', action='store_true')
    parser.add_argument('--preview-save', action='store_true')
    args = parser.parse_args()
    desktop = Path(shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0)).resolve()
    extension = args.source.suffix if args.source else '.hwp' if args.native else '.png'
    fixture = desktop / ('딸깍변환_상주검증_'+uuid.uuid4().hex[:8]+extension)
    if args.source:
        shutil.copy2(args.source, fixture)
    elif args.native:
        source = next(Path('validation/office').glob('*_변환*/*.hwp'))
        shutil.copy2(source, fixture)
    else:
        im = Image.new('RGB', (640, 400), '#ebe5ff')
        ImageDraw.Draw(im).text((80, 180), 'DocQ tray conversion test', fill='#292344', font_size=28)
        im.save(fixture)
    shell.SHChangeNotify(shellcon.SHCNE_CREATE,shellcon.SHCNF_PATHW|shellcon.SHCNF_FLUSH,str(fixture),None)
    shell_app = Dispatch('Shell.Application')
    foreground = win32gui.GetForegroundWindow()
    selected_before, selection = [], None
    child = hwp = sentinel = previous_doc = None
    baseline_ids = set()
    own_hwp = False
    result_folder = None
    try:
        if args.native and args.preserve:
            before = process_ids('Hwp.exe')
            gencache.EnsureModule('{7D2B6F3C-1D95-4E0C-BF5A-5EE564186FBC}', 0, 1, 0)
            hwp = DispatchEx('HWPFrame.HwpObject')
            import win32process
            own_hwp = win32process.GetWindowThreadProcessId(int(hwp.XHwpWindows.Item(0).WindowHandle))[1] not in before
            previous_doc = hwp.XHwpDocuments.Active_XHwpDocument
            baseline_ids = {hwp.XHwpDocuments.Item(i).DocumentID for i in range(hwp.XHwpDocuments.Count)}
            sentinel = hwp.XHwpDocuments.Add(False)
            sentinel.SetActive_XHwpDocument()
            pump(.3)
            hwp.SetTextFile('DOCQ_TRAY_UNSAVED_SENTINEL', 'TEXT', '')
            assert 'DOCQ_TRAY_UNSAVED_SENTINEL' in (hwp.GetTextFile('TEXT', '') or ''), 'Sentinel fixture was not initialized'
            if own_hwp:
                hwp.XHwpWindows.Active_XHwpWindow.Visible = False
            print('Unsaved HWP sentinel ready', flush=True)
        shell_app.MinimizeAll()
        pump(.6)
        child = subprocess.Popen([str(args.exe.resolve())])
        popup = 0
        for _ in range(160):
            popup = win32gui.FindWindow(None, TITLE+' · 변환 메뉴')
            if popup:
                break
            pump(.05)
        assert popup and child.poll() is None, 'Tray app did not start'
        pump(1)
        tutorial=win32gui.FindWindow(None,TITLE+' · 처음 사용 안내')
        if tutorial:
            ImageGrab.grab(win32gui.GetWindowRect(tutorial)).save('validation/v31/tutorial-packaged.png')
            win32gui.SendMessage(tutorial,win32con.WM_CLOSE,0,0)
            pump(.25)
        assert not win32gui.IsWindowVisible(popup), 'Startup showed a menu'
        duplicate = subprocess.Popen([str(args.exe.resolve())])
        duplicate.wait(timeout=15)
        assert child.poll() is None and not win32gui.IsWindowVisible(popup), 'Duplicate launch showed a window'
        print('Tray app ready, startup and duplicate remain hidden', flush=True)
        views = []
        def find_view(handle, _):
            view = win32gui.FindWindowEx(handle, 0, 'SHELLDLL_DefView', None)
            if view:
                views.append(view)
        win32gui.EnumWindows(find_view, None)
        listing = win32gui.FindWindowEx(views[0], 0, 'SysListView32', None)
        desktop_hwnd = win32gui.GetAncestor(listing, 2)
        uia, module = automation()
        container = uia.ElementFromHandle(listing)
        pattern = container.GetCurrentPattern(10001).QueryInterface(module.IUIAutomationSelectionPattern)
        old = pattern.GetCurrentSelection()
        selected_before = [old.GetElement(i) for i in range(old.Length)]
        item = None
        for _ in range(200):
            elements = container.FindAll(4, uia.CreatePropertyCondition(30003, 50007))
            for i in range(elements.Length):
                candidate = elements.GetElement(i)
                if candidate.CurrentName in {fixture.name, fixture.stem}:
                    item = candidate
                    break
            if item:
                break
            pump(.1)
        assert item is not None, 'Fixture icon did not appear'
        selection = item.GetCurrentPattern(10010).QueryInterface(module.IUIAutomationSelectionItemPattern)
        selection.Select()
        win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
        key(ord('M'))
        win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
        pump(.4)
        item.SetFocus()
        rect = item.CurrentBoundingRectangle
        click((int((rect.left+rect.right)/2), int((rect.top+rect.bottom)/2)))
        pump(.4)
        current = win32gui.GetForegroundWindow()
        assert current and win32gui.GetClassName(current) in {'Progman', 'WorkerW'}, (
            current, win32gui.GetClassName(current) if current else None, rect.left, rect.top)
        key(win32con.VK_F12)
        for _ in range(60):
            if win32gui.IsWindowVisible(popup):
                break
            pump(.05)
        assert win32gui.IsWindowVisible(popup), 'Desktop F12 did not show popup'
        pump(.4)
        print('Desktop F12 popup visible', flush=True)
        left, top, right, bottom = win32gui.GetWindowRect(popup)
        assert (right-left, bottom-top) == (460, 460)
        assert win32gui.GetWindowLong(popup, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW
        tag = fixture.suffix[1:]+'-'+args.target
        ImageGrab.grab((left, top, right, bottom)).save('validation/packaged-tray-'+tag+'.png')
        choices,_ = menu_choices([fixture],load_settings())
        page=choices.index(args.target)//8
        for _ in range(page):
            key(win32con.VK_RIGHT)
            pump(.25)
        visible=choices[page*8:page*8+8]
        angle = -math.pi/2+2*math.pi*visible.index(args.target)/len(visible)
        click((left+round(230+165*math.cos(angle)), top+round(230+165*math.sin(angle))))
        pump(.3)
        assert not win32gui.IsWindowVisible(popup), 'Click did not dismiss popup'
        if args.options_escape:
            dialog=0
            for _ in range(60):
                dialog=win32gui.FindWindow(None,TITLE+' · 변환 설정')
                if dialog and win32gui.IsWindowVisible(dialog):
                    break
                pump(.05)
            assert dialog and win32gui.IsWindowVisible(dialog),'Packaged options dialog did not open'
            focus_window(dialog)
            key(win32con.VK_ESCAPE)
            pump(.3)
            assert not win32gui.IsWindow(dialog),'Escape did not cancel conversion options'
            report={'target':args.target,'packaged_options_dialog':True,'escape_cancels':True,
                    'root_stays_hidden':not win32gui.IsWindowVisible(popup)}
            Path('validation/packaged-options-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report,indent=2),flush=True)
            return
        if args.preview_save:
            review=0
            for _ in range(250):
                review=win32gui.FindWindow(None,TITLE+' · 변환 전후 미리보기')
                if review and win32gui.IsWindowVisible(review):break
                pump(.05)
            assert review and win32gui.IsWindowVisible(review),'Packaged comparison did not open'
            focus_window(review)
            pump(.3)
            review_rect=win32gui.GetWindowRect(review)
            ImageGrab.grab(review_rect).save('validation/packaged-preview.png')
            _,_,width,height=win32gui.GetClientRect(review)
            point=win32gui.ClientToScreen(review,(width-55,height-25))
            click(point)
            pump(.3)
            assert not win32gui.IsWindow(review),'Save did not close the comparison window'
        print(args.target+' clicked, waiting for conversion', flush=True)
        deadline = time.monotonic()+80
        outputs = []
        expected = fixture.suffix[1:] if args.target == 'compress' else args.target
        while time.monotonic() < deadline:
            outputs = list(desktop.glob(fixture.stem+'_변환*/*.'+expected))
            if outputs:
                break
            pump(.05)
        assert outputs, 'Conversion did not publish a result'
        result_folder = outputs[0].parent
        if args.target == 'pdf':
            with pymupdf.open(outputs[0]) as pdf:
                assert len(pdf) > 0
        elif args.target == 'png':
            for output in outputs:
                with Image.open(output) as image:
                    image.load()
                    assert image.format == 'PNG'
        elif args.target in {'mp3', 'wav', 'webm'}:
            assert float(probe(outputs[0])['format']['duration']) > 0
        elif args.target == 'compress':
            assert outputs[0].stat().st_size < fixture.stat().st_size
        assert fixture.is_file() and not win32gui.IsWindowVisible(popup)
        report = {'default_launch_hidden':True, 'duplicate_launch_hidden':True,
                  'desktop_mouse_select_f12':True, 'mouse_conversion':True,
                  'completion_stays_hidden':True, 'target':args.target,
                  'preview_saved':args.preview_save,
                  'input_bytes':fixture.stat().st_size, 'output_bytes':sum(p.stat().st_size for p in outputs)}
        if sentinel:
            sentinel.SetActive_XHwpDocument()
            pump(.4)
            assert 'DOCQ_TRAY_UNSAVED_SENTINEL' in hwp.GetTextFile('TEXT', '')
            report['unsaved_hwp_preserved'] = True
        Path('validation/packaged-tray-'+tag+'-report.json').write_text(
            json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2), flush=True)
    finally:
        if child and child.poll() is None:
            handle = win32event.OpenEvent(win32con.EVENT_MODIFY_STATE, False, r'Local\Moonsunezip.DocQ.Close')
            win32event.SetEvent(handle)
            win32api.CloseHandle(handle)
            child.wait(timeout=15)
        if sentinel:
            sentinel.SetActive_XHwpDocument()
            pump(.3)
            sentinel.Close(False)
            if previous_doc:
                previous_doc.SetActive_XHwpDocument()
            remaining = {hwp.XHwpDocuments.Item(i).DocumentID for i in range(hwp.XHwpDocuments.Count)}
            if own_hwp and remaining <= baseline_ids:
                hwp.Quit()
        try:
            for i, element in enumerate(selected_before):
                old = element.GetCurrentPattern(10010).QueryInterface(module.IUIAutomationSelectionItemPattern)
                old.Select() if i == 0 else old.AddToSelection()
            if not selected_before and selection:
                selection.RemoveFromSelection()
        except Exception:
            pass
        if fixture.parent == desktop:
            fixture.unlink(missing_ok=True)
        if result_folder and result_folder.resolve().parent == desktop and result_folder.name.startswith(fixture.stem+'_변환'):
            shutil.rmtree(result_folder)
        shell_app.UndoMinimizeALL()
        try:
            focus_window(foreground)
        except Exception:
            pass


if __name__ == '__main__':
    main()
