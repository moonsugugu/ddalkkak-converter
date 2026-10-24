"""Use one temporary desktop fixture and restore the previous icon selection."""
import json
import time
import tkinter as tk
import uuid
from pathlib import Path

import win32api
import win32con
import win32event
import win32gui
from win32com.shell import shell, shellcon

from app import App
from docx import Document
from PIL import ImageGrab
from validate_windows import focus_window, key
from windows import automation, explorer_selection


def main():
    desktop_path = Path(shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0))
    fixture = desktop_path / ('문서큐_검증_' + uuid.uuid4().hex[:8] + '.txt')
    fixture.write_text('문서큐 바탕 화면 테스트', encoding='utf-8')
    foreground = win32gui.GetForegroundWindow()
    root = tk.Tk()
    event = win32event.CreateEvent(None, True, False, None)
    app = App(root, event)
    app.settings['key'] = app.shortcut.key = 'F12'
    actions = []
    original_put = app.events.put
    def record_event(value):
        actions.append(value)
        original_put(value)
    app.events.put = record_event
    app.hide()
    selected_before = []
    selection = None
    result_folder = None
    desktop_shell = __import__('win32com.client', fromlist=['Dispatch']).Dispatch('Shell.Application')
    def pump(seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            root.update()
            time.sleep(.025)
    try:
        pump(.3)
        assert not root.winfo_viewable() and not app.popup.winfo_viewable()
        assert app.tray.visible
        desktop_shell.MinimizeAll()
        pump(.4)
        desktop = win32gui.FindWindow('Progman', None)
        views = []
        def find_view(handle, _):
            view = win32gui.FindWindowEx(handle, 0, 'SHELLDLL_DefView', None)
            if view:
                views.append(view)
        win32gui.EnumWindows(find_view, None)
        listing = win32gui.FindWindowEx(views[0], 0, 'SysListView32', None)
        uia, module = automation()
        container = uia.ElementFromHandle(listing)
        pattern = container.GetCurrentPattern(10001).QueryInterface(module.IUIAutomationSelectionPattern)
        old = pattern.GetCurrentSelection()
        selected_before = [old.GetElement(i) for i in range(old.Length)]
        item = None
        for _ in range(40):
            root.update()
            children = container.FindAll(4, uia.CreatePropertyCondition(30003, 50007))
            for i in range(children.Length):
                candidate = children.GetElement(i)
                if candidate.CurrentName in {fixture.name, fixture.stem}:
                    item = candidate
                    break
            if item:
                break
            time.sleep(.1)
        assert item is not None, 'Generated desktop icon not found'
        selection = item.GetCurrentPattern(10010).QueryInterface(module.IUIAutomationSelectionItemPattern)
        selection.Select()
        win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
        key(ord('D'))
        win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
        pump(.4)
        item.SetFocus()
        rect = item.CurrentBoundingRectangle
        cursor = (int((rect.left+rect.right)/2), int((rect.top+rect.bottom)/2))
        win32api.SetCursorPos(cursor)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        pump(.2)
        assert explorer_selection(desktop) == [fixture]
        key(win32con.VK_F12)
        for _ in range(40):
            root.update()
            if app.files:
                break
            time.sleep(.05)
        assert app.files == [fixture], (app.files, actions, app.shortcut.ready.is_set(), app.shortcut.error,
            win32gui.GetClassName(win32gui.GetForegroundWindow()), uia.GetFocusedElement().CurrentControlType)
        assert app.popup.winfo_viewable() and not root.winfo_viewable()
        hwnd = win32gui.GetAncestor(app.popup.winfo_id(), 2)
        assert win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW
        assert not win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE) & win32con.WS_CAPTION
        x, y = app.popup.winfo_rootx(), app.popup.winfo_rooty()
        ImageGrab.grab((x, y, x+460, y+460)).save('validation/desktop-popup.png')
        key(win32con.VK_ESCAPE)
        pump(.2)
        assert not app.popup.winfo_viewable()
        focus_window(desktop)
        item.SetFocus()
        key(win32con.VK_F12)
        pump(.5)
        assert app.popup.winfo_viewable()
        x, y = app.target_points['docx']
        win32api.SetCursorPos((app.popup.winfo_rootx()+round(x), app.popup.winfo_rooty()+round(y)))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        pump(.2)
        assert app.busy and not app.popup.winfo_viewable()
        for _ in range(100):
            if not app.busy:
                break
            pump(.1)
        assert not app.busy and not app.errors and len(app.results) == 1, (app.results, app.errors)
        result_folder = Path(app.results[0]['folder'])
        assert '바탕 화면 테스트' in Document(app.results[0]['files'][0]).paragraphs[0].text
        assert fixture.read_text(encoding='utf-8') == '문서큐 바탕 화면 테스트'
        assert not root.winfo_viewable() and not app.popup.winfo_viewable()
        report = {'tray_only_startup':True, 'desktop_mouse_selection_f12':True,
                  'borderless_tool_popup':True, 'escape_dismiss':True,
                  'mouse_format_conversion':True, 'completion_has_no_window':True,
                  'original_preserved':True}
        Path('validation/desktop-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        try:
            if selected_before:
                for i, item in enumerate(selected_before):
                    old = item.GetCurrentPattern(10010).QueryInterface(module.IUIAutomationSelectionItemPattern)
                    old.Select() if i == 0 else old.AddToSelection()
            elif selection:
                selection.RemoveFromSelection()
        except Exception:
            pass
        app.quit(force=True)
        desktop_shell.UndoMinimizeALL()
        win32api.CloseHandle(event)
        if fixture.parent == desktop_path:
            fixture.unlink(missing_ok=True)
        if result_folder and result_folder.parent == desktop_path and result_folder.name.startswith(fixture.stem+'_변환'):
            import shutil
            shutil.rmtree(result_folder)
        try:
            win32gui.SetForegroundWindow(foreground)
        except Exception:
            pass


if __name__ == '__main__':
    main()
