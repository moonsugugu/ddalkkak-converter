"""Explorer selection and an Explorer-only, non-repeating single-key shortcut."""
import ctypes
import threading
from ctypes import wintypes
from pathlib import Path

import pythoncom
import win32api
import win32con
import win32gui
from win32com.client import Dispatch
from hotkeys import parse_hotkey, MOD_CODES


def process_ids(filename):
    class ProcessEntry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
                    ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
                    ('filename', wintypes.WCHAR * 260)]
    kernel = ctypes.windll.kernel32
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError()
    entry = ProcessEntry()
    entry.size = ctypes.sizeof(entry)
    matches = set()
    try:
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.filename.casefold() == filename.casefold():
                matches.add(entry.pid)
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        return matches
    finally:
        kernel.CloseHandle(snapshot)


def process_running(filename):
    return bool(process_ids(filename))


def automation():
    import comtypes.client
    module = comtypes.client.GetModule('UIAutomationCore.dll')
    return comtypes.client.CreateObject(module.CUIAutomation, interface=module.IUIAutomation), module


def explorer_selection(hwnd):
    """Run on a COM-initialized thread. No clipboard or synthetic Ctrl+C."""
    shell = Dispatch('Shell.Application')
    for window in shell.Windows():
        try:
            if int(window.HWND) == hwnd:
                return [Path(item.Path) for item in window.Document.SelectedItems() if not item.IsFolder]
        except Exception:
            continue
    if win32gui.GetClassName(hwnd) not in {'Progman', 'WorkerW'}:
        return []
    desktop = win32gui.FindWindow('Progman', None)
    view = win32gui.FindWindowEx(desktop, 0, 'SHELLDLL_DefView', None)
    if not view:
        views = []
        def collect(handle, _):
            child = win32gui.FindWindowEx(handle, 0, 'SHELLDLL_DefView', None)
            if child:
                views.append(child)
        win32gui.EnumWindows(collect, None)
        view = views[0] if views else 0
    listing = win32gui.FindWindowEx(view, 0, 'SysListView32', None) if view else 0
    if not listing:
        return []
    uia, module = automation()
    element = uia.ElementFromHandle(listing)
    selection = element.GetCurrentPattern(10001).QueryInterface(module.IUIAutomationSelectionPattern)
    items = selection.GetCurrentSelection()
    names = {items.GetElement(i).CurrentName for i in range(items.Length)}
    return [Path(item.Path) for item in shell.NameSpace(0).Items()
            if not item.IsFolder and (item.Name in names or Path(item.Path).name in names)]


HOTKEYS = {f'F{i}':111+i for i in range(1,25)}


class Shortcut:
    @property
    def key(self):
        return self.spec.name

    @key.setter
    def key(self,value):
        self.spec=parse_hotkey(value)

    def __init__(self, callback, key='F12'):
        self.callback = callback
        self.key = key
        self.enabled = True
        self.ready = threading.Event()
        self.error = None
        self.thread_id = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        pythoncom.CoInitialize()
        self.thread_id = win32api.GetCurrentThreadId()
        user = ctypes.windll.user32
        kernel = ctypes.windll.kernel32
        ptr = ctypes.c_ssize_t
        callback_type = ctypes.WINFUNCTYPE(ptr, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user.SetWindowsHookExW.restype = wintypes.HHOOK
        user.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user.CallNextHookEx.restype = ptr
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        held = set()
        try:
            uia, _ = automation()
            def hook(code, message, data):
                if code >= 0:
                    vk = ctypes.cast(data, ctypes.POINTER(wintypes.DWORD))[0]
                    if message in (win32con.WM_KEYUP, win32con.WM_SYSKEYUP):
                        if vk in held:
                            held.discard(vk)
                            return 1
                    elif vk == self.spec.vk and message in (win32con.WM_KEYDOWN,win32con.WM_SYSKEYDOWN):
                        if vk in held:
                            return 1
                        pressed={name for name,key in MOD_CODES.items() if user.GetAsyncKeyState(key)&0x8000}
                        if self.enabled and self.spec.matches(vk,pressed):
                            hwnd = win32gui.GetForegroundWindow()
                            try:
                                if win32gui.GetClassName(hwnd) in {'CabinetWClass', 'ExploreWClass', 'Progman', 'WorkerW'}:
                                    # File lists only; editing, search and other apps keep their normal keys.
                                    focus = uia.GetFocusedElement()
                                    if focus.CurrentControlType in {50007, 50008, 50028, 50029, 50036}:
                                        held.add(vk)
                                        self.callback(hwnd)
                                        return 1
                            except Exception:
                                pass
                return user.CallNextHookEx(None, code, message, data)
            self.proc = callback_type(hook)
            handle = user.SetWindowsHookExW(13, self.proc, kernel.GetModuleHandleW(None), 0)
            if not handle:
                raise ctypes.WinError()
            self.ready.set()
            msg = wintypes.MSG()
            try:
                while user.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    user.TranslateMessage(ctypes.byref(msg))
                    user.DispatchMessageW(ctypes.byref(msg))
            finally:
                user.UnhookWindowsHookEx(handle)
        except Exception as e:
            self.error = str(e)
            self.ready.set()
        finally:
            pythoncom.CoUninitialize()

    def stop(self):
        self.enabled = False
        if self.thread_id:
            win32api.PostThreadMessage(self.thread_id, win32con.WM_QUIT, 0, 0)


def setup_shortcut(destination, executable, arguments='', working_directory=''):
    shell = Dispatch('WScript.Shell')
    link = shell.CreateShortcut(str(destination))
    link.TargetPath = str(executable)
    link.Arguments = arguments
    link.WorkingDirectory = str(working_directory or Path(executable).parent)
    link.Description = '파일을 선택하고 F12 · 문수네집 문서 변환'
    link.IconLocation = str(executable)
    link.Save()


def approve_conversion_paths(hwnd, paths, origin_hwnd=0):
    """Approve only HWP's exact file-access prompt for this job's own paths."""
    import win32process
    expected = {str(Path(p).resolve()).replace('/', '\\').casefold() for p in paths}
    owner = win32process.GetWindowThreadProcessId(hwnd)[1]
    stop = threading.Event()
    def run():
        pythoncom.CoInitialize()
        try:
            uia, module = automation()
            condition = uia.CreatePropertyCondition(30003, 50000)
            while not stop.is_set():
                handles = []
                def collect(handle, _):
                    if win32gui.IsWindowVisible(handle) and win32process.GetWindowThreadProcessId(handle)[1] == owner:
                        handles.append(handle)
                win32gui.EnumWindows(collect, None)
                for handle in handles:
                    try:
                        element = uia.ElementFromHandle(handle)
                        name = element.CurrentName
                        lines = {line.strip().replace('/', '\\').casefold() for line in name.splitlines()}
                        if '파일에 접근하려는 시도' not in name or not (expected & lines):
                            continue
                        buttons = element.FindAll(4, condition)
                        for i in range(buttons.Length):
                            button = buttons.GetElement(i)
                            if button.CurrentName == '접근 허용 : ALT+Y':
                                # HWP 2024 exposes Invoke but ignores it; use its documented access key.
                                foreground = win32gui.GetForegroundWindow()
                                current_owner = win32process.GetWindowThreadProcessId(foreground)[1]
                                origin_active = foreground == origin_hwnd and win32gui.GetClassName(foreground) in {
                                    'CabinetWClass', 'ExploreWClass', 'Progman', 'WorkerW'}
                                if (current_owner != owner and not origin_active
                                        and not win32gui.GetWindowText(foreground).startswith(('문서큐', '딸깍변환'))):
                                    break
                                if any(win32api.GetAsyncKeyState(k) & 0x8000 for k in (16, 17, 18, 91, 92)):
                                    break
                                win32gui.SetForegroundWindow(handle)
                                if win32gui.GetForegroundWindow() == handle:
                                    win32api.keybd_event(18, 0, 0, 0)
                                    win32api.keybd_event(89, 0, 0, 0)
                                    win32api.keybd_event(89, 0, 2, 0)
                                    win32api.keybd_event(18, 0, 2, 0)
                                break
                    except Exception:
                        continue
                stop.wait(.15)
        finally:
            pythoncom.CoUninitialize()
    threading.Thread(target=run, daemon=True).start()
    return stop
