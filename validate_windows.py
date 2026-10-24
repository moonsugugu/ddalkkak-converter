"""Opt-in live check, confined to generated fixtures and a new Explorer window."""
import json
import subprocess
import time
import tkinter as tk
from pathlib import Path

import win32api
import win32con
import win32event
import win32gui
import win32process
import ctypes
from PIL import ImageGrab
from win32com.client import Dispatch
from docx import Document

from app import App
from windows import automation, explorer_selection


def key(vk):
    win32api.keybd_event(vk, 0, 0, 0)
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)


def focus_window(hwnd):
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        key(win32con.VK_MENU)
        current = win32api.GetCurrentThreadId()
        other = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[0]
        ctypes.windll.user32.AttachThreadInput(current, other, True)
        try:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                # A real caption click gives this generated test window input focus.
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                     win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    point = (rect[2]-200, rect[1]+8)
                    hit = win32gui.WindowFromPoint(point)
                    if win32gui.GetAncestor(hit, 2) == hwnd:
                        win32api.SetCursorPos(point)
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
                        time.sleep(.1)
                finally:
                    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                         win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        finally:
            ctypes.windll.user32.AttachThreadInput(current, other, False)


def main():
    fixtures = Path('validation/explorer').resolve()
    fixtures.mkdir(parents=True, exist_ok=True)
    first = fixtures / '단축키 테스트.txt'
    second = fixtures / '두번째 문서.txt'
    first.write_text('문서큐 첫째 파일', encoding='utf-8')
    second.write_text('문서큐 둘째 파일', encoding='utf-8')
    foreground = win32gui.GetForegroundWindow()
    shell = Dispatch('Shell.Application')
    previous = {int(w.HWND) for w in shell.Windows()}
    root = tk.Tk()
    event = win32event.CreateEvent(None, True, False, None)
    app = App(root, event)
    app.settings['key'] = app.shortcut.key = 'F12'
    app.hide()
    window = None
    report = {}
    def pump(seconds):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            root.update()
            time.sleep(.025)
    try:
        for _ in range(100):
            if app.shortcut.ready.is_set():
                break
            pump(.05)
        assert app.shortcut.ready.is_set() and not app.shortcut.error, app.shortcut.error
        subprocess.Popen(['explorer.exe', '/n,', str(fixtures)])
        for _ in range(50):
            pump(.15)
            for candidate in shell.Windows():
                try:
                    if int(candidate.HWND) not in previous and Path(candidate.Document.Folder.Self.Path) == fixtures:
                        window = candidate
                        break
                except Exception:
                    pass
            if window:
                break
        assert window is not None, 'No new fixture Explorer window'
        hwnd = int(window.HWND)
        window.Document.SelectItem(window.Document.Folder.ParseName(first.name), 29)
        focus_window(hwnd)
        pump(.35)
        uia, module = automation()
        own_items = uia.ElementFromHandle(hwnd).FindAll(4, uia.CreatePropertyCondition(30003, 50007))
        for i in range(own_items.Length):
            element = own_items.GetElement(i)
            if element.CurrentName in {first.name, first.stem}:
                element.SetFocus()
                break
        pump(.15)
        report['file_focus_type'] = uia.GetFocusedElement().CurrentControlType
        report['selection'] = [str(p) for p in explorer_selection(hwnd)]
        key(win32con.VK_F12)
        pump(.65)
        assert app.files == [first], app.files
        assert app.popup.winfo_viewable(), 'F12 did not open the menu'
        assert not root.winfo_viewable(), 'Main window must stay hidden'
        report['f12_opens_correct_file'] = True
        x, y = app.popup.winfo_rootx(), app.popup.winfo_rooty()
        ImageGrab.grab((x, y, x+460, y+460)).save('validation/explorer-flow.png')

        bounds = win32gui.GetWindowRect(hwnd)
        outside = next(p for p in [(bounds[0]+140, bounds[1]+12), (bounds[2]-140, bounds[1]+12),
                                  (bounds[0]+20, bounds[3]-30)]
                       if not (x <= p[0] <= x+460 and y <= p[1] <= y+460))
        win32api.SetCursorPos(outside)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        pump(.3)
        assert not app.popup.winfo_viewable(), 'Outside click did not dismiss menu'
        report['outside_click_dismisses'] = True

        app.hide()
        focus_window(hwnd)
        key(win32con.VK_ESCAPE)
        window.Document.SelectItem(window.Document.Folder.ParseName(first.name), 29)
        list_items = uia.ElementFromHandle(hwnd).FindAll(4, uia.CreatePropertyCondition(30003, 50007))
        for i in range(list_items.Length):
            element = list_items.GetElement(i)
            if element.CurrentName in {first.name, first.stem}:
                element.SetFocus()
                break
        pump(.15)
        key(win32con.VK_F2)
        pump(.3)
        focused = uia.GetFocusedElement()
        assert focused.CurrentControlType == 50004, focused.CurrentControlType
        key(win32con.VK_F12)
        pump(.15)
        assert not app.popup.winfo_viewable(), 'F12 was intercepted during rename'
        key(ord('Q'))
        pump(.15)
        value = focused.GetCurrentPattern(10002).QueryInterface(module.IUIAutomationValuePattern).CurrentValue
        assert value.casefold() == 'q', repr(value)
        assert not app.popup.winfo_viewable(), 'Q was intercepted during rename'
        key(win32con.VK_ESCAPE)
        report['rename_q_passes_through'] = True
        assert first.exists()

        entry_window = tk.Toplevel(root)
        entry_window.title('DocQ generated input test')
        entry = tk.Entry(entry_window)
        entry.pack()
        entry_window.lift()
        entry.focus_force()
        pump(.2)
        key(ord('Q'))
        pump(.2)
        assert entry.get().casefold() == 'q', entry.get()
        entry_window.destroy()
        report['other_app_q_passes_through'] = True

        focus_window(hwnd)
        window.Document.SelectItem(window.Document.Folder.ParseName(first.name), 29)
        window.Document.SelectItem(window.Document.Folder.ParseName(second.name), 17)
        pump(.2)
        key(win32con.VK_F12)
        pump(.5)
        assert set(app.files) == {first, second}, app.files
        report['multiple_files'] = True
        # Click the actual canvas target, then wait for both worker processes.
        x, y = app.target_points['docx']
        win32api.SetCursorPos((app.popup.winfo_rootx()+round(x), app.popup.winfo_rooty()+round(y)))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
        pump(.2)
        for _ in range(120):
            if not app.busy and app.results:
                break
            pump(.1)
        assert not app.busy and len(app.results) == 2 and not app.errors, (app.results, app.errors)
        assert not app.popup.winfo_viewable() and not root.winfo_viewable(), 'Completion opened a window'
        for result in app.results:
            assert '문서큐' in Document(result['files'][0]).paragraphs[0].text
        report['gui_two_file_conversion'] = True
        report['hotkey_error'] = app.shortcut.error
        assert not app.shortcut.error
        Path('validation/windows-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        app.quit(force=True)
        win32api.CloseHandle(event)
        if window:
            window.Quit()
        try:
            win32gui.SetForegroundWindow(foreground)
        except Exception:
            pass


if __name__ == '__main__':
    main()
