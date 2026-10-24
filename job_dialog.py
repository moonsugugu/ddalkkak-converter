"""Options appear only after a user chooses an advanced operation."""
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from advanced import timestamp
from product import TITLE


def ask(root, target, paths, quality, formats):
    window = tk.Toplevel(root)
    window.title(TITLE+' · 변환 설정')
    window.configure(bg='#f3effa')
    window.resizable(False, False)
    window.attributes('-topmost', True)
    frame = tk.Frame(window, bg='#f3effa', padx=26, pady=20)
    frame.pack(fill='both', expand=True)
    def label(text):
        tk.Label(frame, text=text, font=('맑은 고딕',10), bg='#f3effa', fg='#39304f', justify='left', wraplength=450).pack(anchor='w', pady=(8,4))
    def entry(text, default=''):
        label(text)
        value = tk.StringVar(value=default)
        ttk.Entry(frame, textvariable=value, width=45).pack(fill='x', ipady=5)
        return value
    def combo(text, values, default):
        label(text)
        value = tk.StringVar(value=default)
        ttk.Combobox(frame, textvariable=value, values=values, state='readonly').pack(fill='x', ipady=4)
        return value
    label({'size':'원본을 보존하고 목표 용량에 맞춘 사본을 만들어요.',
           'pages':'남길 페이지를 원하는 순서로 입력하세요. 제외한 쪽은 사본에서 빠져요.',
           'trim':'필요한 구간만 새 파일로 저장해요.',
           'merge_pdf':'위에서부터 차례로 하나의 PDF로 합쳐요.',
           'ocr_txt':'인쇄된 글자를 읽어 텍스트로 저장해요.',
           'ocr_docx':'인쇄된 글자를 읽어 Word로 저장해요.',
           'save_preset':'다음 F12 메뉴에서 바로 쓸 변환을 저장해요.'}.get(target, '변환 설정'))
    fields = {}
    listing = None
    if target=='split_pdf':
        fields['chunk_pages']=entry('한 파일당 쪽수 · 1이면 한 장씩, 5이면 다섯 쪽씩', '1')
        label('원본의 순서를 유지해 PDF 여러 개로 나눠요. 마지막 파일은 지정한 쪽수보다 적을 수 있어요.')
    elif target=='scan':
        fields['mode']=combo('보정 방식', ['color','gray','bw'], 'color')
        label('color: 컬러 유지 · gray: 회색 · bw: 흑백\n자동 기울기는 약 ±10° 범위에서 글줄을 기준으로 보정해요.')
        fields['format']=combo('저장 형식',['png','jpg','pdf'],'png')
        for key,text in [('deskew','기울기 자동 보정'),('trim','흰 여백 정리')]:
            variable=tk.BooleanVar(value=True);fields[key]=variable
            tk.Checkbutton(frame,text=text,variable=variable,bg='#f3effa').pack(anchor='w',pady=3)
    elif target == 'size':
        fields['max_mb'] = entry('파일 한 개당 최대 용량 (MB)', '5')
        label('사진은 품질·크기가 줄어들 수 있어요. 문서의 글자와 배치는 유지해요.\n목표에 못 미치면 실제 용량과 함께 알려드려요.')
    elif target == 'pages':
        fields['pages'] = entry('페이지 · 예: 1,3-5,2 / 5-1 / 빈칸은 전체')
        fields['format'] = combo('저장 형식', ['pdf','png','jpg','docx','txt','pptx','xlsx'], 'pdf')
    elif target in {'ocr_txt', 'ocr_docx'}:
        if all(Path(p).suffix.lower() == '.pdf' for p in paths):
            fields['pages'] = entry('인식할 페이지 · 빈칸은 전체')
        label('Windows 한국어 OCR을 사용해요. 손글씨·흐린 사진은 정확도가 낮을 수 있어요.\n표와 원래 문서 배치는 재현하지 않아요.')
    elif target == 'trim':
        fields['start'] = entry('시작 · 초 또는 00:01:30', '0')
        fields['end'] = entry('끝 · 빈칸은 마지막까지')
        audio = all(Path(p).suffix.lower() in {'.mp3','.wav','.m4a','.aac','.ogg','.flac'} for p in paths)
        values = ['mp3','wav','m4a','flac','ogg'] if audio else ['mp4','webm','mov','mkv','gif','mp3','wav']
        fields['format'] = combo('저장 형식', values, values[0])
    elif target == 'merge_pdf':
        listing = tk.Listbox(frame, width=54, height=8, font=('맑은 고딕',10), exportselection=False)
        listing.pack(fill='x', pady=8)
        ordered = list(paths)
        def refresh(index=0):
            listing.delete(0,'end')
            for p in ordered:
                listing.insert('end', Path(p).name)
            if ordered:
                listing.selection_set(index)
        def move(delta):
            current = listing.curselection()
            if current and 0 <= current[0]+delta < len(ordered):
                index = current[0]
                ordered[index], ordered[index+delta] = ordered[index+delta], ordered[index]
                refresh(index+delta)
        refresh()
        row = tk.Frame(frame, bg='#f3effa')
        row.pack()
        ttk.Button(row,text='위로 ↑',command=lambda:move(-1)).pack(side='left',padx=5)
        ttk.Button(row,text='아래로 ↓',command=lambda:move(1)).pack(side='left',padx=5)
    elif target == 'save_preset':
        fields['target'] = combo('변환 기능', formats, formats[0])
    q = combo('품질', ['balanced','high','small'], quality)
    name = entry('즐겨찾기 이름 · 입력하면 이 설정 저장', '' if target != 'save_preset' else '내 변환')
    result = []
    def accept():
        try:
            options = {k:(v.get().strip() if isinstance(v.get(),str) else v.get()) for k,v in fields.items()}
            if 'chunk_pages' in options:
                options['chunk_pages']=int(options['chunk_pages'])
                if not 1<=options['chunk_pages']<=10000:raise ValueError('한 파일당 1~10,000쪽 사이로 지정해 주세요.')
            if 'max_mb' in options:
                amount = float(options['max_mb'])
                if not .001 <= amount <= 102400:
                    raise ValueError('목표 용량은 0.001~102400 MB 사이로 입력해 주세요.')
                options['max_mb'] = amount
            if target == 'trim':
                start = timestamp(options['start'])
                if options['end'] and timestamp(options['end']) <= start:
                    raise ValueError('끝 시간은 시작보다 뒤여야 해요.')
            if target == 'save_preset' and not name.get().strip():
                raise ValueError('즐겨찾기 이름을 입력해 주세요.')
            if len(name.get().strip()) > 20:
                raise ValueError('즐겨찾기 이름은 20자까지 입력해 주세요.')
            result.append({'options':options, 'quality':q.get(), 'name':name.get().strip(),
                           'sources':[str(p) for p in ordered] if listing is not None else None})
            window.destroy()
        except (ValueError, OverflowError) as e:
            messagebox.showerror(TITLE,str(e),parent=window)
    label('원본 옆 새 폴더에 저장합니다.')
    buttons = tk.Frame(frame, bg='#f3effa')
    buttons.pack(fill='x',pady=(16,0))
    ttk.Button(buttons,text='취소',command=window.destroy).pack(side='left')
    ttk.Button(buttons,text='저장' if target == 'save_preset' else '변환 시작',command=accept).pack(side='right')
    window.bind('<Escape>',lambda _:window.destroy())
    window.protocol('WM_DELETE_WINDOW',window.destroy)
    window.update_idletasks()
    window.geometry(f'+{max(0, root.winfo_screenwidth()//2-window.winfo_width()//2)}+{max(0, root.winfo_screenheight()//2-window.winfo_height()//2)}')
    window.grab_set()
    window.focus_force()
    root.wait_window(window)
    return result[0] if result else None
