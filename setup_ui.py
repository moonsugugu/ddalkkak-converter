"""The same shortcut editor is used by the tray and the first-run tutorial."""
import tkinter as tk
from tkinter import ttk
from hotkeys import KEY_CODES,MODIFIERS,parse_hotkey,event_hotkey
from product import TITLE


class HotkeyEditor:
    def __init__(self,parent,value):
        spec=parse_hotkey(value)
        self.frame=tk.Frame(parent,bg='#f3effa');self.frame.pack(fill='x',pady=8)
        self.mods={m:tk.BooleanVar(value=m in spec.modifiers) for m in MODIFIERS}
        row=tk.Frame(self.frame,bg='#f3effa');row.pack(fill='x')
        for name,variable in self.mods.items():
            tk.Checkbutton(row,text=name,variable=variable,bg='#f3effa',command=self.update).pack(side='left',padx=(0,8))
        self.main=tk.StringVar(value=spec.name.split('+')[-1])
        self.keys=ttk.Combobox(row,textvariable=self.main,values=list(KEY_CODES),state='readonly',width=13,height=12)
        self.keys.pack(side='right');self.keys.bind('<<ComboboxSelected>>',lambda _:self.update())
        self.value=tk.StringVar(value=spec.name)
        self.display=ttk.Entry(self.frame,textvariable=self.value,state='readonly',font=('맑은 고딕',14,'bold'),justify='center')
        self.display.pack(fill='x',ipady=8,pady=10)
        self.display.bind('<KeyPress>',self.capture)
        self.armed=False
        ttk.Button(self.frame,text='직접 키를 눌러 지정',command=self.arm).pack(anchor='w')
        self.message=tk.StringVar(value='F1~F24, 영문·숫자와 Ctrl·Alt·Shift 조합을 사용할 수 있어요.')
        tk.Label(self.frame,textvariable=self.message,bg='#f3effa',fg='#817a94',font=('맑은 고딕',9),wraplength=480,justify='left').pack(anchor='w',pady=8)

    def arm(self):
        self.armed=True;self.display.focus_set()
        self.message.set('사용할 키 또는 조합을 지금 눌러 주세요. Esc로 입력을 취소할 수 있어요.')

    def capture(self,event):
        if not self.armed:return
        if event.keysym=='Escape':
            self.armed=False;self.update();return 'break'
        try:
            value=event_hotkey(event)
            if value:
                spec=parse_hotkey(value)
                self.main.set(value.split('+')[-1])
                for m,var in self.mods.items():var.set(m in spec.modifiers)
                self.armed=False;self.update()
        except ValueError as error:self.message.set(str(error))
        return 'break'

    def update(self):
        value='+'.join([m for m,var in self.mods.items() if var.get()]+[self.main.get()])
        self.value.set(value)
        try:
            self.read()
            self.message.set(f'바탕 화면·탐색기 파일 목록에서 {value} → 변환 메뉴\n이름 입력·검색창·다른 앱의 키 입력은 유지해요.')
        except ValueError as error:self.message.set(str(error))

    def read(self):
        return parse_hotkey(self.value.get()).name

    def reset(self):
        self.main.set('F12')
        for variable in self.mods.values():variable.set(False)
        self.update()


def show_setup(app,tutorial=False):
    existing=getattr(app,'setup_popup',None)
    if existing and existing.winfo_exists():existing.lift();return existing
    app.hide()
    window=tk.Toplevel(app.root);app.setup_popup=window
    window.title(TITLE+(' · 처음 사용 안내' if tutorial else ' · 단축키 변경'))
    window.configure(bg='#f3effa');window.resizable(False,False)
    body=tk.Frame(window,bg='#f3effa',padx=28,pady=20);body.pack(fill='both',expand=True)
    tk.Label(body,text='딸깍변환, 이렇게 사용해요' if tutorial else '내가 편한 단축키로 바꾸기',bg='#f3effa',fg='#3b3152',font=('맑은 고딕',17,'bold')).pack(anchor='w',pady=(0,12))
    if tutorial:
        for text in ('① 바탕 화면·탐색기에서 파일을 클릭해 선택해요.',
                     '② 아래에서 정한 단축키를 눌러요. 기본은 F12예요.',
                     '③ 원형 메뉴에서 형식을 골라요. 휠·좌우로 넘길 수 있어요.',
                     '④ 전후 미리보기를 확인하고 「이대로 저장」을 눌러요.'):
            tk.Label(body,text=text,bg='#f3effa',fg='#4c425f',font=('맑은 고딕',10),wraplength=490,justify='left').pack(anchor='w',pady=4)
        tk.Label(body,text='원본은 보존하고 원본 옆 새 폴더에 결과를 저장해요.\n창을 닫은 뒤에는 트레이에서 대기합니다.',bg='#f3effa',fg='#817a94',font=('맑은 고딕',9),justify='left').pack(anchor='w',pady=12)
    editor=HotkeyEditor(body,app.settings['key'])
    preview=tk.BooleanVar(value=app.settings.get('preview',True))
    tk.Checkbutton(body,text='변환 후 전후 미리보기로 확인하고 저장',variable=preview,bg='#f3effa').pack(anchor='w',pady=6)
    error=tk.StringVar();tk.Label(body,textvariable=error,bg='#f3effa',fg='#a2485e',wraplength=480).pack(anchor='w')
    def close(save):
        if save:
            try:app.apply_hotkey(editor.read())
            except ValueError as problem:error.set(str(problem));return
            app.settings['preview']=preview.get()
        if tutorial:app.settings['tutorial_seen']=True
        app.save_settings();app.shortcut.enabled=True
        app.setup_popup=None;window.destroy();app.tray.update_menu()
    buttons=tk.Frame(body,bg='#f3effa');buttons.pack(fill='x',pady=(10,0))
    ttk.Button(buttons,text='F12로 초기화',command=editor.reset).pack(side='left')
    ttk.Button(buttons,text='시작하기' if tutorial else '적용',command=lambda:close(True)).pack(side='right')
    if not tutorial:ttk.Button(buttons,text='취소',command=lambda:close(False)).pack(side='right',padx=8)
    window.protocol('WM_DELETE_WINDOW',lambda:close(False))
    window.bind('<Escape>',lambda _:close(False))
    app.shortcut.enabled=False
    window.update_idletasks()
    x=max(0,(app.root.winfo_screenwidth()-window.winfo_width())//2)
    y=max(0,(app.root.winfo_screenheight()-window.winfo_height())//2)
    window.geometry(f'+{x}+{y}')
    window.lift();window.focus_force()
    window.editor=editor
    return window
