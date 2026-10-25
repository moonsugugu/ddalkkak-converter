from __future__ import annotations

import ctypes
import json
import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

if '--worker' in sys.argv:
    from converter import worker
    n = sys.argv.index('--worker')
    worker(sys.argv[n+1], sys.argv[n+2])
    sys.exit(0)

import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox

import pystray
import pythoncom
import win32api
import win32con
import win32event
import win32gui
from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageTk
from win32com.shell import shell, shellcon

from converter import COLORS, LABELS, SUPPORTED, engines, note, targets, unavailable
from media import VIDEOS, AUDIO
from windows import HOTKEYS, Shortcut, explorer_selection, setup_shortcut
from advanced import actions, LABELS as TOOL_LABELS, COLORS as TOOL_COLORS
from product import TITLE, VERSION, STATE_DIR, EXE_NAME
from hotkeys import parse_hotkey
LABELS.update(TOOL_LABELS)
COLORS.update(TOOL_COLORS)

PURPLE, INK, MUTED = '#7561cf', '#292344', '#817a94'
SIZE = 460
TRANSPARENT = '#010203'


def load_settings():
    try:
        value = json.loads((STATE_DIR / 'settings.json').read_text(encoding='utf-8'))
        try:key=parse_hotkey(value.get('key')).name if value.get('version',0)>=2 else 'F12'
        except (ValueError,TypeError):key='F12'
        settings = {'version': 3, 'key':key,
                'quality': value.get('quality', 'balanced') if value.get('quality') in
                {'small', 'balanced', 'high'} else 'balanced',
                'preview':value.get('preview',True) is not False,'tutorial_seen':value.get('tutorial_seen') is True}
        if isinstance(value.get('usage'),dict):
            settings['usage']={k:min(v,100000) for k,v in value['usage'].items() if isinstance(k,str) and isinstance(v,int) and v>=0}
        if isinstance(value.get('presets'),list):
            settings['presets']=[p for p in value['presets'] if isinstance(p,dict) and p.get('target') in LABELS
                                 and isinstance(p.get('name'),str) and 0<len(p['name'])<=20
                                 and p.get('quality') in {'small','balanced','high'} and isinstance(p.get('options'),dict)][:24]
        return settings
    except (OSError, ValueError, TypeError, AttributeError):
        return {'version': 3, 'key': 'F12', 'quality': 'balanced','preview':True,'tutorial_seen':False}


def icon_image(size=256):
    im = Image.new('RGBA', (size, size))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((3, 3, size-4, size-4), radius=size//4, fill=PURPLE, outline='#e1d9ff', width=max(1,size//40))
    d.rounded_rectangle((size*.21,size*.16,size*.71,size*.75), radius=size*.07, fill='#faf6ff')
    for y in (.32,.43,.54):
        d.rounded_rectangle((size*.31,size*y,size*.60,size*(y+.035)), radius=max(1,size*.01),fill='#b3a4ed')
    d.ellipse((size*.51,size*.55,size*.88,size*.92),fill='#c9f1e7',outline='#e7fff8',width=max(1,size//50))
    font = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', int(size*.25))
    d.text((size*.70,size*.73), '↔', fill=PURPLE, font=font, anchor='mm')
    return im


def popup_position(point, work_area, size=SIZE):
    left, top, right, bottom = work_area
    return (max(left, min(point[0]-size//2, right-size)),
            max(top, min(point[1]-size//2, bottom-size)))


def menu_choices(paths,settings):
    common=targets(paths[0]) if paths else []
    for path in paths[1:]:
        common=[t for t in common if t in targets(path)]
    priority=['pdf','png','compress','jpg','photo_edit','pdf_edit','docx','size','scan','split_pdf','photo_redact','photo_annotate','photo_collage','photo_metadata','pdf_stamp','pdf_protect','mp4','mp3','gif','webp','avif','hwp','hwpx','xlsx','pptx','txt','wav','merge_pdf','pages','ocr_txt','ocr_docx','md','html','epub','srt','vtt','tsv','ods','pack','unpack']
    usage=settings.get('usage',{})
    tools=actions(paths)
    ordered=sorted(common+tools,key=lambda t:(-min(1000,usage.get(paths[0].suffix.lower()+':'+t,0)),priority.index(t) if t in priority else 99))
    presets={'fav:'+str(i):p for i,p in enumerate(settings.get('presets',[])[:24])
             if isinstance(p,dict) and p.get('target') in common+tools and isinstance(p.get('name'),str)}
    return list(presets)+ordered+(['save_preset'] if common else []),presets


class App:
    def __init__(self, root, show_event, paths=(), close_event=None):
        self.root, self.show_event, self.close_event = root, show_event, close_event
        root.withdraw()
        root.title(TITLE)
        self.settings = load_settings()
        self.events = queue.Queue()
        self.files, self.choices, self.results, self.errors = [], [], [], []
        self.available = engines()
        self.busy = self.closing = self.stop_after_current = self.quit_after_current = False
        self.busy_event = win32event.CreateEvent(None,True,False,r'Local\Moonsunezip.DocQ.Busy')
        self.folder = None
        self.status = f'파일 선택 → {self.settings["key"]} → 형식 클릭'
        self.current_cancel_path = None
        self.current_video = False
        self.origin_hwnd = 0
        self.shortcut_error_reported = False
        self.menu_request = 0
        self.target_points = {}
        self.page = 0
        self.visible_choices = []
        self.preset_map = {}
        self.review_window=None
        self.setup_popup=None
        self.tkicon = ImageTk.PhotoImage(icon_image(128))
        root.iconphoto(True, self.tkicon)
        self.popup = tk.Toplevel(root)
        self.popup.withdraw()
        self.popup.title(TITLE + ' · 변환 메뉴')
        self.popup.overrideredirect(True)
        self.popup.attributes('-topmost', True)
        self.popup.attributes('-toolwindow', True)
        self.popup.attributes('-transparentcolor', TRANSPARENT)
        self.canvas = tk.Canvas(self.popup, width=SIZE, height=SIZE, bg=TRANSPARENT,
                                highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind('<Button-1>', self.click_target)
        self.canvas.bind('<Motion>', self.move_target)
        self.popup.bind('<Escape>', lambda _: self.hide())
        self.popup.bind('<FocusOut>', lambda _: root.after(100, self.dismiss_unfocused))
        self.popup.protocol('WM_DELETE_WINDOW', self.hide)
        self.popup.bind('<MouseWheel>', lambda e: self.change_page(-1 if e.delta > 0 else 1))
        self.popup.bind('<Left>', lambda _: self.change_page(-1))
        self.popup.bind('<Right>', lambda _: self.change_page(1))
        for i in range(1, 10):
            self.popup.bind(str(i), lambda _, index=i-1: self.convert(self.visible_choices[index])
                            if index < len(self.visible_choices) else None)
        self.shortcut = Shortcut(lambda hwnd: self.events.put(('explorer', (hwnd, win32api.GetCursorPos()))),
                                 self.settings['key'])
        menu = pystray.Menu(
            pystray.MenuItem('열기 · 파일 선택', lambda: self.events.put(('choose', None)), default=True),
            pystray.MenuItem('설정', lambda: self.events.put(('settings', None))),
            pystray.MenuItem('업데이트 확인', lambda: self.events.put(('update', True))),
            pystray.MenuItem('사용 방법', lambda: self.events.put(('help', None))),
            pystray.MenuItem('튜토리얼 다시 보기', lambda: self.events.put(('tutorial', None))),
            pystray.MenuItem('파일 직접 고르기…', lambda: self.events.put(('choose', None))),
            pystray.MenuItem('최근 결과 폴더 열기', lambda: self.events.put(('folder', None)),
                             enabled=lambda _: bool(self.folder)),
            pystray.MenuItem('최근 오류 보기', lambda: self.events.put(('errors', None)),
                             enabled=lambda _: bool(self.errors)),
            pystray.MenuItem('현재 영상·음성 변환 중지', lambda: self.events.put(('cancel', None)),
                             enabled=lambda _: self.busy and self.current_video),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('단축키 변경…',lambda:self.events.put(('hotkey_setup',None))),
            pystray.MenuItem('빠른 단축키', pystray.Menu(*[
                pystray.MenuItem(k, lambda _, item: self.events.put(('key', str(item))),
                                 checked=lambda item: self.settings['key'] == str(item), radio=True)
                for k in ('F12','F11','F10','F9','F8','F7','F6')])),
            pystray.MenuItem('변환 후 미리보기',lambda:self.events.put(('preview',None)),
                             checked=lambda _:self.settings.get('preview',True)),
            pystray.MenuItem('변환 품질', pystray.Menu(*[
                self.quality_item(value, label) for value, label in
                [('small', '가볍게'), ('balanced', '균형'), ('high', '선명하게')]])),
            pystray.MenuItem('Windows 시작할 때 실행', lambda: self.events.put(('startup', None)),
                             checked=lambda _: self.startup_link().exists()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('종료', lambda: self.events.put(('quit', None))))
        self.tray = pystray.Icon('DocQ', icon_image(64), TITLE + ' · ' + self.status, menu)
        threading.Thread(target=self.tray.run, daemon=True).start()
        self.save_settings()
        root.after(80, self.poll)
        root.after(12000, self.auto_update)
        if '--smoke' not in sys.argv and '--smoke-convert' not in sys.argv:
            root.after(650,self.maybe_tutorial)
        if paths:
            self.set_files(paths, win32api.GetCursorPos(), win32gui.GetForegroundWindow())
        if '--smoke' in sys.argv:
            root.after(3000, self.smoke_capture)
        elif '--smoke-convert' in sys.argv:
            root.after(1800, lambda: self.convert('pdf'))

    def quality_item(self, value, label):
        return pystray.MenuItem(label, lambda: self.events.put(('quality', value)),
                                checked=lambda _: self.settings['quality'] == value, radio=True)

    def text(self, x, y, content, size=11, color=INK, weight='normal', **kwargs):
        return self.canvas.create_text(x, y, text=content, fill=color,
                                       font=('맑은 고딕', size, weight), **kwargs)

    def draw(self):
        c = self.canvas
        c.delete('all')
        self.target_points.clear()
        from clay import wheel
        self.visible_choices = self.choices[self.page*8:self.page*8+8]
        background, points = wheel(self.visible_choices, COLORS, SIZE)
        self.clay_image = ImageTk.PhotoImage(background)
        c.create_image(0,0,anchor='nw',image=self.clay_image)
        self.target_points.update(points)
        kind = self.files[0].suffix[1:].upper()
        self.text(230, 171, TITLE, 9, MUTED)
        self.text(230, 199, kind, 22, PURPLE, 'bold')
        name = self.files[0].name
        if len(name) > 42:
            name = name[:20] + '…' + name[-17:]
        self.text(230, 233, name, 9, width=146)
        if len(self.files) > 1:
            self.text(230, 257, f'외 {len(self.files)-1}개', 8, PURPLE)
        self.text(230, 282, '형식을 클릭하세요', 8, MUTED, width=145, tags='hint')
        pages = max(1,math.ceil(len(self.choices)/8))
        self.text(175, 325, '‹', 24, PURPLE, tags='prev')
        self.text(230, 325, f'{self.page+1} / {pages}', 10, MUTED)
        self.text(285, 325, '›', 24, PURPLE, tags='next')
        c.tag_bind('prev','<Button-1>',lambda _:self.change_page(-1))
        c.tag_bind('next','<Button-1>',lambda _:self.change_page(1))
        self.text(230, 346, '휠로 넘기기 · Esc 닫기', 8, MUTED)
        self.text(230, 125, '×', 12, MUTED, tags='close')
        c.tag_bind('close', '<Button-1>', lambda _: self.hide())
        for i, target in enumerate(self.visible_choices):
            x,y = self.target_points[target]
            tag = 'target_' + target
            reason = self.reason(target)
            c.create_oval(x-39, y-39, x+39, y+39, fill='', outline='', tags=tag)
            special = target in TOOL_LABELS or target.startswith('fav:') or target in {'compress', 'images'}
            label = self.preset_map[target]['name'] if target in self.preset_map else LABELS[target]
            if target in self.preset_map and len(label)>8:
                label=label[:4]+'\n'+label[4:8]+'…'
            self.text(x, y-5, label, 10 if special else 13,
                      MUTED if reason else INK, 'bold', tags=tag)
            subtitle = '★ 즐겨찾기' if target.startswith('fav:') else {'compress':'원본 보존', 'images':'모든 사진',
                       'size':'MB 지정','pages':'순서·제외','merge_pdf':'여러 파일','trim':'시작·끝',
                       'ocr_txt':'글자 인식','ocr_docx':'글자 인식','save_preset':'다음에 바로',
                       'scan':'기울기·여백','split_pdf':'한 쪽·묶음'}.get(target, '편집 도구' if target in TOOL_LABELS else '.'+target)
            self.text(x, y+25 if special else y+18, '설치 필요' if reason else subtitle, 8, MUTED, tags=tag)
            c.tag_bind(tag, '<Enter>', lambda _, t=target, r=reason: self.hover(t, r))
            c.tag_bind(tag, '<Leave>', lambda _: self.leave())

    def change_page(self, delta):
        if self.choices:
            self.page = (self.page+delta) % max(1,math.ceil(len(self.choices)/8))
            self.draw()

    def click_target(self,event):
        for target,(x,y) in self.target_points.items():
            if (event.x-x)**2+(event.y-y)**2 <= 40**2:
                self.convert(target)
                return

    def move_target(self,event):
        for target,(x,y) in self.target_points.items():
            if (event.x-x)**2+(event.y-y)**2 <= 40**2:
                self.hover(target,self.reason(target))
                return
        self.leave()

    def reason(self,target):
        if target in self.preset_map:
            target = self.preset_map[target]['target']
        from extra_jobs import LABELS as EXTRA_LABELS,handles
        if target in EXTRA_LABELS or all(handles(p,target) for p in self.files):return ''
        if target in {'save_preset','ocr_txt','ocr_docx','trim','size','scan','split_pdf'}:
            return ''
        if target in {'pages','merge_pdf'}:
            target='pdf'
        return next((unavailable(p,target,self.available) for p in self.files if unavailable(p,target,self.available)), '')

    def hover(self, target, reason):
        self.canvas.configure(cursor='hand2')
        hint = {'pages':'필요한 쪽·순서를 골라요', 'size':'목표 MB로 줄여요', 'merge_pdf':'선택 파일을 하나로 합쳐요',
                'trim':'필요한 구간만 저장해요','ocr_txt':'사진의 글자를 인식해요','ocr_docx':'사진의 글자를 Word로',
                'save_preset':'변환 설정을 즐겨찾기에 저장','scan':'기울기·여백·명암 정리','split_pdf':'PDF를 여러 파일로 나눠요'}.get(target)
        self.canvas.itemconfigure('hint', text=reason or hint or ('저장된 설정으로 변환' if target in self.preset_map else note(self.files[0], target)))

    def leave(self):
        self.canvas.configure(cursor='')
        self.canvas.itemconfigure('hint', text='형식을 클릭하세요')

    def notify(self, message):
        self.tray.title = (TITLE + ' · ' + message)[:127]
        try:
            self.tray.notify(message, TITLE)
        except (NotImplementedError, OSError):
            pass

    def set_files(self, paths, point=None, origin=0):
        if self.busy:
            return
        self.files = list(dict.fromkeys(Path(p).resolve() for p in paths
                                       if Path(p).is_file() and Path(p).suffix.lower() in SUPPORTED))
        self.choices,self.preset_map=menu_choices(self.files,self.settings)
        self.page = 0
        if not self.choices:
            self.hide()
            self.notify('변환할 문서나 이미지를 선택해 주세요.' if not self.files else
                        '함께 바꿀 형식이 없어요. 같은 종류의 파일을 선택해 주세요.')
            return
        self.origin_hwnd = origin
        self.draw()
        point = point or win32api.GetCursorPos()
        monitor = win32api.MonitorFromPoint(point, win32con.MONITOR_DEFAULTTONEAREST)
        x, y = popup_position(point, win32api.GetMonitorInfo(monitor)['Work'])
        self.popup.geometry(f'{SIZE}x{SIZE}')
        self.popup.deiconify()
        self.popup.update_idletasks()
        win32gui.SetWindowPos(win32gui.GetAncestor(self.popup.winfo_id(), 2), win32con.HWND_TOPMOST,
                             x, y, SIZE, SIZE, win32con.SWP_NOACTIVATE)
        self.popup.lift()
        self.popup.focus_force()

    def hide(self):
        self.popup.withdraw()

    def dismiss_unfocused(self):
        if not self.closing and self.popup.winfo_viewable():
            focus = self.popup.focus_displayof()
            if focus is None or focus.winfo_toplevel() != self.popup:
                self.hide()

    def choose(self):
        if self.busy:
            return
        self.hide()
        files = filedialog.askopenfilenames(title='바꿀 문서·사진·영상·음성 선택', parent=self.root,
                    filetypes=[('변환 가능한 파일', ' '.join('*'+ext for ext in sorted(SUPPORTED))), ('모든 파일', '*.*')])
        if files:
            self.set_files(files)

    def convert(self, target):
        if self.busy or not self.files or target not in self.choices:
            return
        reason = self.reason(target)
        if reason:
            self.notify(reason)
            return
        options, sources, quality = {}, None, self.settings['quality']
        if target in self.preset_map:
            preset = self.preset_map[target]
            target,options,quality = preset['target'],preset.get('options',{}),preset.get('quality','balanced')
        elif target in TOOL_LABELS:
            from job_dialog import ask
            self.hide()
            formats = [t for t in self.choices if t not in TOOL_LABELS and not t.startswith('fav:')]
            self.busy=True
            win32event.SetEvent(self.busy_event)
            try:answer = ask(self.root,target,self.files,quality,formats)
            except (ValueError,OSError) as error:
                from tkinter import messagebox
                messagebox.showerror(TITLE,str(error),parent=self.root)
                return
            finally:
                self.busy=False
                win32event.ResetEvent(self.busy_event)
            if not answer:
                return
            options, sources, quality = answer['options'],answer['sources'],answer['quality']
            if target == 'save_preset':
                target=options.pop('target')
                self.add_preset(answer['name'],target,quality,options)
                self.notify('즐겨찾기에 저장했어요. 다음 F12 메뉴 첫 원에 표시돼요.')
                return
            if answer['name']:
                self.add_preset(answer['name'],target,quality,options)
        usage=self.settings.setdefault('usage',{})
        key=self.files[0].suffix.lower()+':'+target
        usage[key]=usage.get(key,0)+1
        self.save_settings()
        self.busy = True
        win32event.SetEvent(self.busy_event)
        self.stop_after_current = False
        self.results, self.errors = [], []
        owns_focus = win32gui.GetForegroundWindow() == win32gui.GetAncestor(self.popup.winfo_id(), 2)
        self.hide()
        paths, origin = list(self.files), self.origin_hwnd
        preview=self.settings.get('preview',True) and '--smoke-convert' not in sys.argv
        if target in {'merge_pdf','photo_collage','pack'}:
            sources = sources or [str(p) for p in paths]
            paths = paths[:1]
        if owns_focus and origin and win32gui.IsWindow(origin):
            try:
                win32gui.SetForegroundWindow(origin)
            except Exception:
                pass
        def run():
            for i, path in enumerate(paths):
                if self.stop_after_current:
                    break
                label = LABELS[target].replace('\n', ' ')
                prefix = f'{i+1}/{len(paths)} · {path.name} → {label}'
                self.events.put(('progress', prefix))
                with tempfile.TemporaryDirectory(prefix='docq-job-') as tmp:
                    request, response = Path(tmp)/'request.json', Path(tmp)/'response.json'
                    progress, cancel = Path(tmp)/'progress.txt', Path(tmp)/'cancel'
                    self.events.put(('job', (str(cancel), path.suffix.lower() in VIDEOS | AUDIO)))
                    request.write_text(json.dumps({'source': str(path), 'target': target,
                                                   'quality': quality, 'origin_hwnd': origin,
                                                   'progress_path': str(progress), 'cancel_path': str(cancel),
                                                   'options':options,'sources':sources,'preview':preview}), encoding='utf-8')
                    cmd = [sys.executable] + ([] if getattr(sys, 'frozen', False) else [str(Path(__file__).resolve())])
                    try:
                        process = subprocess.Popen(cmd + ['--worker', str(request), str(response)],
                                                   creationflags=subprocess.CREATE_NO_WINDOW,
                                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        while process.poll() is None:
                            time.sleep(.2)
                            try:
                                status = progress.read_text(encoding='utf-8').strip()
                                if status:
                                    self.events.put(('progress', prefix+' · '+status))
                            except OSError:
                                pass
                        result = json.loads(response.read_text(encoding='utf-8'))
                    except Exception as e:
                        result = {'ok': False, 'error': '변환 작업을 완료하지 못했어요.\n' + str(e)[:400]}
                    if result.get('ok'):
                        self.results.append(result)
                    elif result.get('cancelled'):
                        self.stop_after_current = True
                    else:
                        self.errors.append(f'{path.name}\n{result.get("error", "알 수 없는 오류")}')
            self.events.put(('done', None))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        if self.closing:
            return
        if self.close_event and win32event.WaitForSingleObject(self.close_event, 0) == win32con.WAIT_OBJECT_0:
            win32event.ResetEvent(self.close_event)
            self.quit()
            if self.closing:
                return
        if win32event.WaitForSingleObject(self.show_event, 0) == win32con.WAIT_OBJECT_0:
            win32event.ResetEvent(self.show_event)
            self.notify(f'트레이에서 실행 중입니다. 파일 선택 후 {self.settings["key"]}를 누르세요.')
        try:
            while True:
                action, value = self.events.get_nowait()
                if action == 'explorer' and not self.busy:
                    self.menu_request += 1
                    request = self.menu_request
                    def read_selection(info=value, request=request):
                        pythoncom.CoInitialize()
                        try:
                            files = explorer_selection(info[0])
                        except Exception:
                            files = []
                        finally:
                            pythoncom.CoUninitialize()
                        self.events.put(('files', (request, files, info)))
                    threading.Thread(target=read_selection, daemon=True).start()
                elif action == 'files':
                    request, files, (hwnd, point) = value
                    if request == self.menu_request and win32gui.GetForegroundWindow() == hwnd:
                        self.set_files(files, point, hwnd)
                elif action == 'choose':
                    self.choose()
                elif action == 'progress':
                    self.status = value
                    self.tray.title = (TITLE + ' · ' + value)[:127]
                elif action == 'job':
                    self.current_cancel_path, self.current_video = value
                    self.tray.update_menu()
                elif action == 'cancel' and self.current_cancel_path and self.current_video:
                    self.stop_after_current = True
                    try:
                        Path(self.current_cancel_path).touch(exist_ok=True)
                    except OSError:
                        pass  # The worker may have completed and removed its job folder.
                elif action == 'done':
                    self.current_cancel_path=None
                    self.current_video=False
                    if any(r.get('_pending') for r in self.results) and not self.quit_after_current:
                        from preview_ui import ReviewWindow
                        self.status='미리보기 확인 대기 · 저장하거나 취소해 주세요.'
                        self.tray.title=(TITLE+' · '+self.status)[:127]
                        self.tray.update_menu()
                        self.review_window=ReviewWindow(self.root,self.results,lambda cancelled:self.events.put(('review_done',cancelled)))
                    else:
                        if self.quit_after_current:
                            from job_output import discard_preview
                            for result in self.results:discard_preview(result)
                            self.results[:]=[r for r in self.results if not r.get('_pending')]
                        self.finish_jobs()
                    if self.closing:return
                elif action == 'review_done':
                    self.review_window=None
                    self.finish_jobs(value)
                    if self.closing:return
                elif action in {'key', 'quality'}:
                    if action == 'key':
                        self.apply_hotkey(value)
                    else:
                        self.settings[action] = value
                        self.save_settings()
                    self.tray.update_menu()
                elif action=='preview':
                    self.settings['preview']=not self.settings.get('preview',True)
                    self.save_settings();self.tray.update_menu()
                elif action in {'hotkey_setup','tutorial'}:
                    from setup_ui import show_setup
                    show_setup(self,action=='tutorial')
                elif action == 'startup':
                    self.toggle_startup()
                elif action == 'folder' and self.folder:
                    os.startfile(self.folder)
                elif action == 'errors':
                    self.details('최근 변환 오류', '\n\n'.join(self.errors))
                elif action == 'help':
                    self.help()
                elif action == 'settings':
                    self.settings_window()
                elif action == 'update':
                    self.check_update(value)
                elif action == 'update_result':
                    self.update_result(*value)
                elif action == 'installer_ready':
                    path,popup,status=value
                    if self.busy:
                        self.notify('설치파일 검증을 마쳤어요. 변환 완료 후 업데이트를 다시 실행해 주세요.')
                    else:
                        try:
                            subprocess.Popen([str(path)])
                        except OSError as e:
                            self.notify('업데이트 설치를 시작하지 못했어요. '+str(e)[:150])
                elif action == 'installer_error':
                    error,popup,status,button=value
                    if popup.winfo_exists():
                        status.set(error)
                        button.configure(state='normal')
                elif action == 'quit':
                    self.quit()
                    if self.closing:
                        return
        except queue.Empty:
            pass
        if self.shortcut.ready.is_set() and self.shortcut.error and not self.shortcut_error_reported:
            self.shortcut_error_reported = True
            self.notify('단축키를 등록하지 못했어요. 트레이에서 파일을 직접 고를 수 있습니다.')
        self.root.after(80, self.poll)

    def finish_jobs(self,cancelled=False):
        self.busy = False
        win32event.ResetEvent(self.busy_event)
        self.current_cancel_path = None
        self.current_video = False
        self.folder = self.results[0]['folder'] if self.results else None
        self.status = f'변환 완료 {len(self.results)}건 · 결과 {sum(len(r["files"]) for r in self.results)}개'
        if self.errors:
            self.status += f' · 실패 {len(self.errors)}개 (트레이에서 오류 확인)'
        elif self.folder:
            compact = [r for r in self.results if 'saved_percent' in r]
            if compact:
                before = sum(r['original_bytes'] for r in compact)
                after = sum(r['result_bytes'] for r in compact)
                self.status += f'\n용량 {(1-after/before)*100:.1f}% 줄임 · 원본 보존' if before and after < before else '\n이미 압축되어 더 줄지 않았어요. 원본과 같은 사본을 저장했어요.'
            else:
                self.status += '\n원본 옆 _변환 폴더에 저장했어요.'
            goals=[r for r in self.results if 'target_met' in r]
            if goals:
                self.status += '\n목표 용량 충족' if all(r['target_met'] for r in goals) else '\n목표에 도달하지 못한 파일이 있어요. 최근 결과에서 실제 용량을 확인하세요.'
        if self.stop_after_current:
            self.status += ' · 중지됨'
        if cancelled:self.status=f'저장 {len(self.results)}개 · 나머지 취소' if self.results else '저장 취소 · 원본은 그대로예요.'
        self.tray.update_menu()
        self.notify(self.status)
        if self.quit_after_current:
            self.quit(force=True)
            return
        if '--smoke-convert' in sys.argv:
            self.root.after(300, self.smoke_capture)

    def save_settings(self):
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            temporary = STATE_DIR/'settings.tmp'
            temporary.write_text(json.dumps(self.settings,ensure_ascii=False), encoding='utf-8')
            temporary.replace(STATE_DIR/'settings.json')
        except OSError as e:
            self.notify('설정을 저장하지 못했어요. ' + str(e)[:100])

    def add_preset(self,name,target,quality,options):
        presets = self.settings.setdefault('presets',[])
        presets[:] = [p for p in presets if p.get('name') != name]
        presets.insert(0,{'name':name,'target':target,'quality':quality,'options':dict(options)})
        del presets[24:]
        self.save_settings()

    def apply_hotkey(self,value):
        value=parse_hotkey(value).name
        self.shortcut.key=value
        self.settings['key']=value
        self.save_settings()
        self.tray.title=TITLE+' · 파일 선택 → '+value+' → 형식 클릭'

    def maybe_tutorial(self):
        if self.closing or self.settings.get('tutorial_seen'):return
        if self.busy or self.popup.winfo_viewable() or (self.setup_popup and self.setup_popup.winfo_exists()):
            self.root.after(1000,self.maybe_tutorial)
            return
        from setup_ui import show_setup
        show_setup(self,True)

    def settings_window(self):
        self.hide()
        popup=tk.Toplevel(self.root)
        popup.title(TITLE+' · 설정')
        popup.geometry('480x560')
        popup.configure(bg='#f3effa')
        body=tk.Frame(popup,bg='#f3effa',padx=24,pady=20)
        body.pack(fill='both',expand=True)
        tk.Label(body,text=f'{TITLE}  {VERSION}',font=('맑은 고딕',17,'bold'),bg='#f3effa',fg=INK).pack(anchor='w')
        tk.Label(body,text=f'파일 선택 → {self.settings["key"]} → 클릭\n휠·좌우 키로 원형 메뉴 넘기기',justify='left',bg='#f3effa',font=('맑은 고딕',10)).pack(anchor='w',pady=12)
        listing=tk.Listbox(body,height=6,font=('맑은 고딕',10),exportselection=False)
        listing.pack(fill='x')
        for p in self.settings.get('presets',[]):
            listing.insert('end',p['name']+' · '+LABELS.get(p['target'],p['target']).replace('\n',' '))
        def remove():
            selected=listing.curselection()
            if selected:
                del self.settings['presets'][selected[0]]
                listing.delete(selected[0])
                self.save_settings()
        ttk.Button(body,text='선택한 즐겨찾기 삭제',command=remove).pack(anchor='w',pady=8)
        def shortcut_setup():
            from setup_ui import show_setup
            show_setup(self)
        ttk.Button(body,text='단축키 변경…',command=shortcut_setup).pack(fill='x',pady=4)
        ttk.Button(body,text='업데이트 확인',command=lambda:self.check_update(True)).pack(fill='x',pady=4)
        ttk.Button(body,text='앱 제거…',command=self.uninstall).pack(fill='x',pady=4)
        tk.Label(body,text='제거해도 변환한 파일과 설정은 보존해요.\nmade by 문수네집 · moonsunezip.com',bg='#f3effa',fg=MUTED,font=('맑은 고딕',9)).pack(pady=12)
        ttk.Button(body,text='닫기',command=popup.destroy).pack()
        popup.lift()

    def uninstall(self):
        if self.busy:
            self.notify('변환이 끝난 뒤 앱 제거를 실행해 주세요.')
            return
        executable=Path(sys.executable).parent/'Uninstall.exe'
        if getattr(sys,'frozen',False) and executable.exists():
            subprocess.Popen([str(executable)],cwd=executable.parent)
        else:
            os.startfile('ms-settings:appsfeatures')

    def auto_update(self):
        self.check_update(False)
        self.root.after(6*60*60*1000,self.auto_update)

    def check_update(self,manual=True):
        if getattr(self,'checking_update',False):
            return
        self.checking_update=True
        def run():
            try:
                import updater
                self.events.put(('update_result',(manual,updater.check(),None)))
            except Exception as e:
                self.events.put(('update_result',(manual,None,str(e))))
        threading.Thread(target=run,daemon=True).start()

    def update_result(self,manual,data,error):
        self.checking_update=False
        if not manual and (error or not data['available']):
            return
        if error:
            self.details('업데이트 확인 실패',f'현재 버전 {VERSION}\n\n{error}\n\n트레이 → 업데이트 확인으로 다시 시도할 수 있어요.')
            return
        if not manual:
            self.notify('새 버전 '+data['version']+'이 있어요. 트레이에서 업데이트를 확인하세요.')
            return
        popup=tk.Toplevel(self.root)
        popup.title(TITLE+' · 업데이트')
        popup.geometry('480x320')
        tk.Label(popup,text=f'현재 {VERSION}  →  최신 {data["version"]}',font=('맑은 고딕',14,'bold')).pack(pady=18)
        tk.Label(popup,text=str(data.get('notes',''))[:2000] or ('업데이트할 수 있어요.' if data['available'] else '최신 버전이에요.'),wraplength=420,justify='left').pack(padx=20,pady=10)
        status=tk.StringVar()
        tk.Label(popup,textvariable=status,wraplength=420).pack(pady=8)
        def install():
            if self.busy:
                status.set('파일 변환이 끝난 뒤 다시 시도해 주세요.')
                return
            button.configure(state='disabled')
            status.set('설치파일 다운로드·검증 중…')
            def fetch():
                try:
                    import updater
                    result=updater.download(data)
                    self.events.put(('installer_ready',(result,popup,status)))
                except Exception as e:
                    self.events.put(('installer_error',(str(e),popup,status,button)))
            threading.Thread(target=fetch,daemon=True).start()
        if data['available']:
            button=ttk.Button(popup,text='다운로드 후 업데이트',command=install)
            button.pack(pady=8)
        ttk.Button(popup,text='닫기',command=popup.destroy).pack(pady=5)

    def startup_link(self):
        return Path(shell.SHGetFolderPath(0, shellcon.CSIDL_STARTUP, None, 0)) / (TITLE+'.lnk')

    def toggle_startup(self):
        path = self.startup_link()
        try:
            if path.exists():
                path.unlink()
            elif getattr(sys, 'frozen', False):
                setup_shortcut(path, sys.executable, '--background')
            else:
                setup_shortcut(path, sys.executable, f'"{Path(__file__).resolve()}" --background')
            self.tray.update_menu()
        except Exception as e:
            self.notify('시작 설정을 바꾸지 못했어요. ' + str(e)[:100])

    def details(self, title, content):
        self.hide()
        popup = tk.Toplevel(self.root)
        popup.title(TITLE + ' · ' + title)
        popup.geometry('510x360')
        box = scrolledtext.ScrolledText(popup, wrap='word', font=('맑은 고딕', 10), relief='flat', padx=20, pady=18)
        box.pack(fill='both', expand=True)
        box.insert('1.0', content)
        box.configure(state='disabled')
        tk.Button(popup, text='닫기', command=popup.destroy, padx=25).pack(pady=10)
        popup.lift()

    def help(self):
        self.details('사용 방법',
            TITLE+'는 창 없이 트레이에서 대기합니다.\n\n'
            '① 바탕 화면이나 탐색기에서 파일을 클릭해 선택하세요.\n'
            f'② {self.settings["key"]} 키를 한 번 누르세요.\n'
            '③ 마우스 주변 메뉴에서 바꿀 형식을 클릭하세요.\n\n'
            '결과는 원본 옆 「파일이름_변환」 폴더에 저장합니다. 원본은 보존합니다.\n'
            '여러 파일도 함께 선택할 수 있습니다.\n'
            '메뉴 바깥 클릭 또는 Esc로 닫습니다.\n\n'
            '트레이 우클릭: 단축키 변경·미리보기·품질·자동 실행·최근 결과·종료\n'
            '이름 바꾸기·검색·다른 앱의 키 입력은 그대로 전달합니다.\n\n'
            '사진·한글 → PNG / 영상 → 다른 영상·GIF·MP3·WAV\n'
            '용량 줄이기: 사진·한글·Word·PPT·PDF·영상\n'
            '사진 꺼내기: 한글·Word·PPT·PDF\n'
            '품질은 트레이 우클릭 → 변환 품질에서 조절합니다.\n'
            '한글 속 사진은 픽셀 수와 문서 배치를 유지하고 품질을 낮춥니다.\n'
            '이미 최적화된 파일은 용량이 더 줄지 않을 수 있습니다.\n\n'
            '한글·Office 문서 변환에는 해당 프로그램이 필요합니다.\n'
            'PDF → Word는 텍스트 중심, PDF → PPT는 페이지 이미지입니다.\n'
            '글자 인식 → Windows 한국어 OCR로 TXT·Word 저장\n'
            '목표 용량 / PDF 합치기 / 페이지 선택·순서 / 영상 구간 자르기\n'
            '휠 또는 좌우 화살표로 원형 메뉴를 넘깁니다.\n'
            '즐겨찾기는 첫 원에, 자주 쓴 형식은 앞쪽에 표시해요.\n\n'
            '변환 후 전후 미리보기에서 저장 또는 취소를 고를 수 있어요.\n'
            'PDF 분리: 한 쪽씩 또는 지정한 쪽수 단위로 저장해요.\n'
            '스캔 보정: 사진의 기울기·여백·명암을 정리해요.\n'
            '단축키 변경: F1~F24·영문·숫자·Ctrl/Alt/Shift 조합\n'
            '첫 실행 튜토리얼은 트레이에서 다시 볼 수 있어요.\n\n'
            'made by 문수네집 · moonsunezip.com\n'
            'Instagram: instagram.com/moonsune.zip/')

    def smoke_capture(self):
        self.root.update()
        out = (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent) / 'validation'
        out.mkdir(exist_ok=True)
        visible = bool(self.popup.winfo_viewable())
        if visible:
            x, y = self.popup.winfo_rootx(), self.popup.winfo_rooty()
            ImageGrab.grab((x, y, x+SIZE, y+SIZE)).save(out / 'ui.png')
        (out / 'smoke.json').write_text(json.dumps({'window': bool(self.root.winfo_viewable()),
                    'popup': visible, 'tray': self.tray.visible,
                    'hotkey_ready': self.shortcut.ready.is_set(), 'hotkey_error': self.shortcut.error,
                    'choices': self.choices, 'files': [str(p) for p in self.files],
                    'results': self.results, 'errors': self.errors}, ensure_ascii=False), encoding='utf-8')
        self.quit(force=True)

    def quit(self, force=False):
        if self.closing:return
        if self.review_window and not self.review_window.closed:
            self.quit_after_current=True
            self.review_window.cancel()
            if not force:return
        if self.busy and not force:
            self.stop_after_current = self.quit_after_current = True
            self.notify('현재 파일 변환을 마친 뒤 종료합니다.')
            return
        self.closing = True
        win32event.ResetEvent(self.busy_event)
        win32api.CloseHandle(self.busy_event)
        self.shortcut.stop()
        self.tray.stop()
        for callback in self.root.tk.call('after','info'):
            self.root.after_cancel(callback)
        self.root.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    mutex = win32event.CreateMutex(None, False, r'Local\Moonsunezip.DocQ')
    duplicate = win32api.GetLastError() == 183
    event = win32event.CreateEvent(None, True, False, r'Local\Moonsunezip.DocQ.Show')
    close_event = win32event.CreateEvent(None, True, False, r'Local\Moonsunezip.DocQ.Close')
    try:
        if '--exit' in sys.argv:
            win32event.SetEvent(close_event)
            return
        if duplicate:
            win32event.SetEvent(event)
            return
        root = tk.Tk()
        App(root, event, [v for v in sys.argv[1:] if not v.startswith('--')], close_event)
        root.mainloop()
    finally:
        for handle in (event, close_event, mutex):
            win32api.CloseHandle(handle)


if __name__ == '__main__':
    main()
