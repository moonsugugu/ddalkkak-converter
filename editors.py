"""Transient visual editors; return options, then the worker and Save/Cancel own output."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog,colorchooser
from PIL import Image,ImageTk
from product import TITLE

BG='#f3effa'


def finish_window(root,window):
    window.bind('<Escape>',lambda _:window.destroy())
    if root.winfo_viewable():window.transient(root)
    window.grab_set();window.lift();window.focus_force()
    root.wait_window(window)


class PhotoEditor:
    def __init__(self,root,path,target,quality):
        from image_io import oriented
        self.root=root;self.original=oriented(path);self.options={};self.marks=[];self.history=[];self.answer=None;self.quality=quality
        self.window=tk.Toplevel(root);self.window.title(TITLE+' · 사진 편집');self.window.geometry(f'1080x{min(800,root.winfo_screenheight()-80)}');self.window.minsize(900,600);self.window.configure(bg=BG)
        side=tk.Frame(self.window,bg=BG);side.pack(side='right',fill='y')
        controls=tk.Canvas(side,bg=BG,width=306,highlightthickness=0)
        scroll=ttk.Scrollbar(side,orient='vertical',command=controls.yview);scroll.pack(side='right',fill='y')
        controls.configure(yscrollcommand=scroll.set);controls.pack(side='left',fill='both',expand=True)
        panel=tk.Frame(controls,bg=BG,padx=12,pady=12)
        panel_id=controls.create_window((0,0),window=panel,anchor='nw')
        panel.bind('<Configure>',lambda _:controls.configure(scrollregion=controls.bbox('all')))
        controls.bind('<Configure>',lambda event:controls.itemconfigure(panel_id,width=event.width))
        self.window.bind('<MouseWheel>',lambda event: controls.yview_scroll(-int(event.delta/120),'units')
                         if event.x_root>=controls.winfo_rootx() and event.widget.winfo_class() not in {'TCombobox','TScale','TEntry'} else None)
        self.canvas=tk.Canvas(self.window,bg='#ded8eb',highlightthickness=0);self.canvas.pack(side='left',fill='both',expand=True,padx=12,pady=12)
        self.canvas.bind('<Configure>',lambda _:self.redraw())
        self.canvas.bind('<Button-1>',self.start);self.canvas.bind('<B1-Motion>',self.drag);self.canvas.bind('<ButtonRelease-1>',self.end)
        ttk.Label(panel,text=Path(path).name,wraplength=280).pack(anchor='w',pady=5)
        ttk.Label(panel,text='도구를 고른 뒤 사진 위를 드래그하세요.').pack(anchor='w')
        self.mode=tk.StringVar(value='모자이크' if target=='photo_redact' else '글자' if target=='photo_annotate' else '자르기')
        ttk.Combobox(panel,textvariable=self.mode,state='readonly',values=['자르기','모자이크','블러','덮기','화살표','글자','형광펜'],width=28).pack(pady=8)
        self.aspect=tk.StringVar(value='자유')
        aspect=ttk.Combobox(panel,textvariable=self.aspect,state='readonly',values=['자유','1:1','4:3','3:4','16:9','9:16'],width=28)
        aspect.pack(pady=(0,5));aspect.bind('<<ComboboxSelected>>',self.set_aspect)
        self.color='#7561cf';self.text=tk.StringVar(value='안내')
        ttk.Entry(panel,textvariable=self.text,width=29).pack(fill='x')
        ttk.Button(panel,text='글자·표시 색 선택',command=self.choose_color).pack(fill='x',pady=4)
        row=ttk.Frame(panel);row.pack(fill='x',pady=5)
        ttk.Button(row,text='90° 회전',command=self.rotate).pack(side='left')
        ttk.Button(row,text='좌우 반전',command=self.flip).pack(side='left',padx=4)
        self.width=tk.StringVar();self.height=tk.StringVar()
        ttk.Label(panel,text='크기: 폭 / 높이 (한쪽만 입력하면 비율 유지)').pack(anchor='w',pady=(8,2))
        row=ttk.Frame(panel);row.pack(fill='x')
        ttk.Entry(row,textvariable=self.width,width=12).pack(side='left');ttk.Label(row,text=' × ').pack(side='left');ttk.Entry(row,textvariable=self.height,width=12).pack(side='left')
        self.adjust={}
        for key,label in [('brightness','밝기'),('contrast','대비'),('saturation','채도'),('sharpness','선명도')]:
            value=tk.DoubleVar(value=1);self.adjust[key]=value
            ttk.Label(panel,text=label).pack(anchor='w',pady=(6,0))
            ttk.Scale(panel,from_=0,to=3,variable=value,command=lambda _:self.schedule()).pack(fill='x')
        row=ttk.Frame(panel);row.pack(fill='x',pady=8)
        self.margin=tk.StringVar(value='0');self.radius=tk.StringVar(value='0')
        ttk.Label(row,text='여백').pack(side='left');ttk.Entry(row,textvariable=self.margin,width=6).pack(side='left')
        ttk.Label(row,text=' 모서리').pack(side='left');ttk.Entry(row,textvariable=self.radius,width=6).pack(side='left')
        self.background=None
        ttk.Button(panel,text='배경색 선택',command=self.choose_background).pack(fill='x')
        self.fmt=tk.StringVar(value='png')
        ttk.Combobox(panel,textvariable=self.fmt,values=['png','jpg','webp','avif','tiff'],state='readonly').pack(fill='x',pady=8)
        row=ttk.Frame(panel);row.pack(fill='x')
        ttk.Button(row,text='표시·자르기 취소',command=self.undo).pack(side='left')
        ttk.Button(row,text='전체 초기화',command=self.reset).pack(side='right')
        ttk.Button(panel,text='입력한 크기·여백 적용',command=self.apply).pack(fill='x',pady=8)
        ttk.Label(panel,text='GPS 등 원본 메타데이터를 복사하지 않습니다.\n원본은 보존하며 다음 화면에서 저장·취소합니다.',wraplength=280).pack(anchor='w',pady=8)
        ttk.Button(panel,text='편집 완료 · 전후 미리보기',command=self.accept).pack(fill='x',pady=6)
        ttk.Button(panel,text='취소',command=self.window.destroy).pack(fill='x')
        self.pending=None;self.start_point=None;self.view=None
        self.window.after(40,self.redraw)

    def choose_color(self):
        color=colorchooser.askcolor(self.color,parent=self.window)[1]
        if color:self.color=color

    def set_aspect(self,event=None):
        if self.aspect.get()=='자유':return
        a,b=map(int,self.aspect.get().split(':'));ratio=a/b
        w,h=self.original.size
        if self.options.get('rotate',0) in {90,270}:w,h=h,w
        if w/h>ratio:
            width=h*ratio/w;self.options['crop']=[(1-width)/2,0,(1+width)/2,1]
        else:
            height=w/ratio/h;self.options['crop']=[0,(1-height)/2,1,(1+height)/2]
        self.redraw()

    def choose_background(self):
        color=colorchooser.askcolor(self.background or '#ffffff',parent=self.window)[1]
        if color:self.background=color;self.redraw()

    def collect(self):
        return {**self.options,**{k:v.get() for k,v in self.adjust.items()},'marks':list(self.marks),
                'width':self.width.get().strip(),'height':self.height.get().strip(),'format':self.fmt.get(),
                'margin':self.margin.get().strip(),'radius':self.radius.get().strip(),**({'background':self.background} if self.background else {})}

    def schedule(self):
        if self.pending:self.window.after_cancel(self.pending)
        self.pending=self.window.after(140,self.redraw)

    def apply(self):
        try:self.render_image();self.redraw()
        except (ValueError,TypeError,OverflowError) as error:messagebox.showerror(TITLE,str(error),parent=self.window)

    def render_image(self):
        from photo_tools import edit
        return edit(self.original,self.collect())

    def redraw(self):
        self.pending=None
        if not self.canvas.winfo_exists():return
        try:image=self.render_image()
        except (ValueError,TypeError,OverflowError):return
        size=(max(100,self.canvas.winfo_width()-30),max(100,self.canvas.winfo_height()-30));image.thumbnail(size,Image.Resampling.LANCZOS)
        self.photo=ImageTk.PhotoImage(image)
        x=(self.canvas.winfo_width()-image.width)//2;y=(self.canvas.winfo_height()-image.height)//2
        self.view=(x,y,image.width,image.height);self.canvas.delete('all');self.canvas.create_image(x,y,anchor='nw',image=self.photo)

    def point(self,event):
        if not self.view:return None
        x,y,w,h=self.view
        return (max(0,min(1,(event.x-x)/w)),max(0,min(1,(event.y-y)/h)))

    def start(self,event):
        if not self.view:return
        x,y,w,h=self.view
        self.start_point=self.point(event) if x<=event.x<=x+w and y<=event.y<=y+h else None

    def drag(self,event):
        if not self.start_point:return
        self.canvas.delete('selection');x,y,w,h=self.view;a,b=self.start_point;c,d=self.point(event)
        self.canvas.create_rectangle(x+a*w,y+b*h,x+c*w,y+d*h,outline='#7561cf',width=3,tags='selection')

    def end(self,event):
        if not self.start_point:return
        a,b=self.start_point;c,d=self.point(event);self.start_point=None
        if self.mode.get()=='글자' and abs(c-a)<.005 and abs(d-b)<.005:
            a,b=min(a,.99),min(b,.99);c,d=min(1,a+.3),min(1,b+.08)
        elif self.mode.get()=='화살표':
            if (c-a)**2+(d-b)**2<.000025:return
        elif abs(c-a)<.005 or abs(d-b)<.005:return
        box=[min(a,c),min(b,d),max(a,c),max(b,d)]
        box[0]=min(box[0],.999);box[1]=min(box[1],.999)
        box[2]=min(1,max(box[2],box[0]+.001));box[3]=min(1,max(box[3],box[1]+.001))
        import copy
        self.history.append((copy.deepcopy(self.options),copy.deepcopy(self.marks)))
        if self.mode.get()=='자르기':
            old=self.options.get('crop',[0,0,1,1]);x0,y0,x1,y1=old
            self.options['crop']=[x0+box[0]*(x1-x0),y0+box[1]*(y1-y0),x0+box[2]*(x1-x0),y0+box[3]*(y1-y0)]
        else:
            kinds={'모자이크':'mosaic','블러':'blur','덮기':'cover','화살표':'arrow','글자':'text','형광펜':'highlight'}
            self.marks.append({'kind':kinds[self.mode.get()],'box':box,'color':self.color,'text':self.text.get(),
                               **({'points':[a,b,c,d]} if self.mode.get()=='화살표' else {})})
        self.redraw()

    def rotate(self):self.options['rotate']=(self.options.get('rotate',0)+90)%360;self.redraw()
    def flip(self):self.options['flip_x']=not self.options.get('flip_x',False);self.redraw()
    def undo(self):
        if self.history:self.options,self.marks=self.history.pop();self.redraw()
    def reset(self):
        self.options={};self.marks=[];self.history=[];self.width.set('');self.height.set('');self.margin.set('0');self.radius.set('0');self.background=None
        for variable in self.adjust.values():variable.set(1)
        self.redraw()
    def accept(self):
        try:
            self.render_image();self.answer={'options':self.collect(),'quality':self.quality,'name':'','sources':None};self.window.destroy()
        except (ValueError,TypeError,OverflowError) as error:messagebox.showerror(TITLE,str(error),parent=self.window)


class PDFEditor:
    def __init__(self,root,path,quality):
        import pymupdf
        self.doc=pymupdf.open(path);self.password='';self.answer=None;self.quality=quality
        if self.doc.needs_pass:
            self.password=simpledialog.askstring(TITLE,'PDF 열기 암호',show='*',parent=root)
            if not self.password or not self.doc.authenticate(self.password):self.doc.close();raise ValueError('PDF 암호를 확인해 주세요.')
        if len(self.doc)>10000:self.doc.close();raise ValueError('한 번에 최대 10,000쪽까지 편집해 주세요.')
        self.items=[{'index':i,'rotate':0} for i in range(len(self.doc))];self.images={};self.dragging=None
        self.window=tk.Toplevel(root);self.window.title(TITLE+' · PDF 페이지 편집');self.window.geometry('900x720');self.window.configure(bg=BG)
        ttk.Label(self.window,text='썸네일을 드래그해 순서를 바꾸세요. 원본은 보존합니다.').pack(pady=12)
        body=ttk.Frame(self.window);body.pack(fill='both',expand=True,padx=18)
        style=ttk.Style(self.window);style.configure('Pages.Treeview',rowheight=116)
        self.tree=ttk.Treeview(body,show='tree',selectmode='browse',style='Pages.Treeview',height=3)
        scrollbar=ttk.Scrollbar(body,orient='vertical',command=self.scroll);self.scrollbar=scrollbar
        self.tree.configure(yscrollcommand=self.on_scroll);scrollbar.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True)
        self.tree.bind('<ButtonPress-1>',self.pick);self.tree.bind('<ButtonRelease-1>',self.drop)
        self.tree.bind('<<TreeviewSelect>>',lambda _:self.thumbnail_visible())
        self.tree.bind('<MouseWheel>',lambda _:self.window.after(100,self.thumbnail_visible),add='+')
        self.refresh()
        bar=ttk.Frame(self.window);bar.pack(pady=12)
        for title,command in [('위로',lambda:self.move(-1)),('아래로',lambda:self.move(1)),('90° 회전',self.rotate),('복제',self.duplicate),('삭제',self.delete)]:
            ttk.Button(bar,text=title,command=command).pack(side='left',padx=4)
        self.watermark=tk.StringVar();self.numbers=tk.BooleanVar(value=False)
        line=ttk.Frame(self.window);line.pack(pady=4)
        ttk.Label(line,text='워터마크').pack(side='left');ttk.Entry(line,textvariable=self.watermark,width=35).pack(side='left',padx=8)
        ttk.Checkbutton(line,text='쪽번호 넣기',variable=self.numbers).pack(side='left')
        ttk.Button(self.window,text='편집 완료 · 전후 미리보기',command=self.accept).pack(pady=12)
        self.window.after(80,self.thumbnail_visible)

    def selection(self):
        selected=self.tree.selection();return int(selected[0]) if selected else 0
    def refresh(self,index=0):
        self.tree.delete(*self.tree.get_children());self.images={}
        for i,item in enumerate(self.items):self.tree.insert('', 'end',iid=str(i),text=f'  원본 {item["index"]+1}쪽 · 회전 {item["rotate"]}°')
        if self.items:self.tree.selection_set(str(min(index,len(self.items)-1)));self.tree.see(str(min(index,len(self.items)-1)))
        self.window.after_idle(self.thumbnail_visible)
    def thumbnail_visible(self):
        if not self.tree.winfo_exists() or not self.items:return
        import pymupdf
        start=max(0,int(self.tree.yview()[0]*len(self.items))-1)
        if len(self.images)>100:
            for index in list(self.images):
                if index<start-24 or index>start+36:
                    self.tree.item(str(index),image='');del self.images[index]
        for i in range(start,min(len(self.items),start+12)):
            if i in self.images:continue
            item=self.items[i];page=self.doc[item['index']];scale=min(90/page.rect.width,100/page.rect.height)
            pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale).prerotate(item['rotate']),alpha=False)
            image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            self.images[i]=ImageTk.PhotoImage(image);self.tree.item(str(i),image=self.images[i])
    def scroll(self,*args):self.tree.yview(*args);self.window.after_idle(self.thumbnail_visible)
    def on_scroll(self,a,b):self.scrollbar.set(a,b)
    def pick(self,event):
        item=self.tree.identify_row(event.y);self.dragging=int(item) if item else None
    def drop(self,event):
        item=self.tree.identify_row(event.y)
        if item and self.dragging is not None and self.dragging!=int(item):
            target=int(item);self.items.insert(target,self.items.pop(self.dragging));self.refresh(target)
        self.dragging=None
    def move(self,delta):
        index=self.selection();target=index+delta
        if 0<=target<len(self.items):self.items[index],self.items[target]=self.items[target],self.items[index];self.refresh(target)
    def rotate(self):
        index=self.selection();self.items[index]['rotate']=(self.items[index]['rotate']+90)%360;self.refresh(index)
    def duplicate(self):
        index=self.selection();self.items.insert(index+1,dict(self.items[index]));self.refresh(index+1)
    def delete(self):
        if len(self.items)>1:index=self.selection();self.items.pop(index);self.refresh(index)
    def accept(self):
        self.answer={'options':{'page_items':self.items,'password':self.password,'watermark':self.watermark.get(),'page_numbers':self.numbers.get()},'quality':self.quality,'name':'','sources':None};self.window.destroy()


def ask(root,target,paths,quality):
    if target in {'photo_edit','photo_redact','photo_annotate'}:
        editor=PhotoEditor(root,paths[0],target,quality);finish_window(root,editor.window);return editor.answer
    if target=='pdf_edit':
        editor=PDFEditor(root,paths[0],quality)
        try:finish_window(root,editor.window);return editor.answer
        finally:editor.doc.close()
    window=tk.Toplevel(root);window.title(TITLE+' · 파일 도구');window.configure(bg=BG);frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
    fields={};answer=[]
    def field(key,label,default='',values=None,secret=False):
        ttk.Label(frame,text=label,wraplength=470).pack(anchor='w',pady=(8,3));value=tk.StringVar(value=default)
        widget=ttk.Combobox(frame,textvariable=value,values=values,state='readonly') if values else ttk.Entry(frame,textvariable=value,show='*' if secret else '',width=48)
        widget.pack(fill='x');fields[key]=value
    def check(key,label,default=False):
        value=tk.BooleanVar(value=default);ttk.Checkbutton(frame,text=label,variable=value).pack(anchor='w',pady=5);fields[key]=value
    if target=='photo_collage':
        field('columns','열 수','2');field('cell','한 칸 크기 (픽셀)','600');field('gap','사진 사이 간격','20');field('background','배경색','#ffffff');field('format','저장 형식','png',['png','jpg','webp','avif'])
    elif target=='photo_metadata':
        ttk.Label(frame,text='새 사진에서 EXIF·GPS·XMP와 원본 썸네일을 제거합니다.\n원본은 그대로 보존합니다.',wraplength=470).pack(anchor='w')
        field('format','저장 형식','png',['png','jpg','webp','avif','tiff'])
        check('report','원본 EXIF 정보를 별도 보고서로 저장 (위치 정보가 포함될 수 있음)')
    elif target=='pdf_protect':
        field('password','기존 PDF 암호 (암호가 없다면 빈칸)',secret=True)
        field('mode','작업','encrypt',['encrypt','decrypt'])
        ttk.Label(frame,text='encrypt: 새 열기 암호 설정 · decrypt: 기존 암호로 인증 후 해제').pack(anchor='w',pady=3)
        field('new_password','새 열기 암호 (암호 설정 시)',secret=True);field('confirmation','새 암호 다시 입력',secret=True)
    elif target=='pdf_stamp':
        field('password','기존 PDF 암호 (있을 때만)',secret=True);field('watermark','워터마크 글자');check('page_numbers','쪽번호 넣기',True);check('remove_metadata','작성자 등 PDF 메타데이터 삭제')
    elif target=='pack':
        field('format','압축 형식','zip',['zip','tar','gz']);ttk.Label(frame,text='선택 파일들을 묶습니다. GZIP은 파일 한 개만 지원합니다.').pack(pady=8)
    elif target=='unpack':ttk.Label(frame,text='ZIP·TAR·GZIP을 원본 옆 새 폴더에 풉니다.\n최대 10,000개·512MB까지 지원합니다.').pack(pady=8)
    ttk.Label(frame,text='다음 전후 미리보기에서 저장·취소합니다.').pack(pady=10)
    def accept():
        options={k:v.get() for k,v in fields.items()}
        if target=='pdf_protect' and options.get('mode')=='encrypt' and (not options.get('new_password') or options['new_password']!=options.pop('confirmation')):
            messagebox.showerror(TITLE,'새 암호를 동일하게 두 번 입력해 주세요.',parent=window);return
        options.pop('confirmation',None)
        answer.append({'options':options,'quality':quality,'name':'','sources':[str(p) for p in paths] if target in {'pack','photo_collage'} else None});window.destroy()
    ttk.Button(frame,text='작업 시작',command=accept).pack(side='right',padx=5);ttk.Button(frame,text='취소',command=window.destroy).pack(side='left')
    finish_window(root,window);return answer[0] if answer else None
