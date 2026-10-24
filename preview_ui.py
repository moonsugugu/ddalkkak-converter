"""A transient comparison window. Nothing is published until the user saves."""
import io
import tkinter as tk
from tkinter import ttk,messagebox
from pathlib import Path
import pymupdf
from PIL import Image,ImageOps,ImageTk
from job_output import commit_preview,discard_preview
from product import TITLE


def byte_label(value):
    return f'{value/1024/1024:.2f} MB' if value>=1024*1024 else f'{value/1024:.1f} KB'


def render(path,page,size):
    if not path:return None,0,''
    path=Path(path)
    if path.suffix.lower()=='.pdf':
        with pymupdf.open(path) as doc:
            if doc.needs_pass or not len(doc):return None,0,''
            index=max(0,min(page,len(doc)-1))
            sheet=doc[index]
            scale=min(size[0]/sheet.rect.width,size[1]/sheet.rect.height,2)
            pix=sheet.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
            image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
            return image,len(doc),f'{sheet.rect.width:.0f} × {sheet.rect.height:.0f} pt'
    try:
        with Image.open(path) as original:
            count=getattr(original,'n_frames',1)
            original.seek(min(page,count-1))
            image=ImageOps.exif_transpose(original).convert('RGBA')
            detail=f'{image.width} × {image.height} px'
            image.thumbnail(size,Image.Resampling.LANCZOS)
            background=Image.new('RGBA',image.size,'white');background.alpha_composite(image)
            return background.convert('RGB'),count,detail
    except (OSError,ValueError):return None,0,''


class Pane:
    def __init__(self,parent,title):
        self.frame=tk.Frame(parent,bg='#f3effa',padx=10,pady=8)
        self.frame.pack(side='left',fill='both',expand=True)
        tk.Label(self.frame,text=title,bg='#f3effa',fg='#3b3152',font=('맑은 고딕',12,'bold')).pack(pady=5)
        self.select=ttk.Combobox(self.frame,state='readonly',width=38)
        self.select.pack(fill='x',pady=4)
        self.select.bind('<<ComboboxSelected>>',lambda _:self.selected())
        self.info=tk.StringVar()
        tk.Label(self.frame,textvariable=self.info,bg='#f3effa',fg='#766d86',font=('맑은 고딕',9),wraplength=380).pack(pady=4)
        self.canvas=tk.Canvas(self.frame,bg='#e4deee',highlightthickness=0,width=380,height=360)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda _:self.draw())
        bar=tk.Frame(self.frame,bg='#f3effa');bar.pack(pady=7)
        ttk.Button(bar,text='‹ 이전 쪽',command=lambda:self.turn(-1)).pack(side='left')
        self.page_label=tk.StringVar()
        tk.Label(bar,textvariable=self.page_label,bg='#f3effa',width=12).pack(side='left')
        ttk.Button(bar,text='다음 쪽 ›',command=lambda:self.turn(1)).pack(side='left')
        self.paths=[];self.views=[];self.page=0;self.count=0;self.on_select=None

    def set(self,paths,views):
        self.paths,self.views=list(paths),list(views)
        self.select.configure(values=[Path(p).name for p in paths])
        self.select.current(0)
        self.page=0
        self.draw()

    def selected(self):
        self.page=0;self.draw()
        if self.on_select:self.on_select()

    def turn(self,delta):
        if self.count:
            self.page=(self.page+delta)%self.count
            self.draw()
            if self.on_select:self.on_select()

    def draw(self):
        if not self.paths:return
        index=max(0,self.select.current())
        path=Path(self.paths[index]);view=self.views[index] if index<len(self.views) else None
        width,height=max(100,self.canvas.winfo_width()-24),max(100,self.canvas.winfo_height()-24)
        self.canvas.delete('all')
        try:
            image,self.count,detail=render(view,self.page,(width,height))
            self.info.set(path.name+' · '+byte_label(path.stat().st_size)+(' · '+detail if detail else ''))
            if image:
                self.photo=ImageTk.PhotoImage(image)
                self.canvas.create_image((width+24)/2,(height+24)/2,image=self.photo)
            else:
                self.canvas.create_text((width+24)/2,(height+24)/2,text='이 형식은 화면 미리보기를 지원하지 않아요.\n파일 이름과 용량을 확인해 주세요.',width=width-20,justify='center',font=('맑은 고딕',10),fill='#766d86')
            self.page_label.set(f'{min(self.page+1,self.count)} / {self.count}쪽' if self.count else '화면 없음')
        except Exception as error:
            self.count=0;self.page_label.set('화면 없음')
            self.canvas.create_text((width+24)/2,(height+24)/2,text='미리보기 화면을 읽지 못했어요.\n'+str(error)[:100],width=width-20,justify='center',font=('맑은 고딕',10))


class ReviewWindow:
    def __init__(self,root,results,on_decision):
        self.results,self.on_decision,self.closed=results,on_decision,False
        self.window=tk.Toplevel(root)
        self.window.title(TITLE+' · 변환 전후 미리보기')
        self.window.configure(bg='#f3effa')
        width=min(1000,root.winfo_screenwidth()-80);height=min(740,root.winfo_screenheight()-90)
        self.window.geometry(f'{width}x{height}')
        self.window.minsize(600,460)
        self.window.protocol('WM_DELETE_WINDOW',self.cancel)
        self.window.bind('<Escape>',lambda _:self.cancel())
        header=tk.Frame(self.window,bg='#f3effa',padx=20,pady=12);header.pack(fill='x')
        tk.Label(header,text='결과를 비교하고 저장하세요',bg='#f3effa',font=('맑은 고딕',16,'bold'),fg='#3b3152').pack(anchor='w')
        self.jobs=ttk.Combobox(header,state='readonly',values=[f'{i+1}. {Path(r["source"]).name}' for i,r in enumerate(results)])
        self.jobs.pack(fill='x',pady=8);self.jobs.current(0)
        self.jobs.bind('<<ComboboxSelected>>',lambda _:self.select_job())
        self.summary=tk.StringVar()
        tk.Label(header,textvariable=self.summary,bg='#f3effa',fg='#766d86',font=('맑은 고딕',10)).pack(anchor='w')
        columns=tk.Frame(self.window,bg='#f3effa');columns.pack(fill='both',expand=True,padx=10)
        self.before=Pane(columns,'원본');self.after=Pane(columns,'변환 결과 · 저장 전')
        self.after.on_select=self.align_source
        self.notice=tk.StringVar()
        tk.Label(self.window,textvariable=self.notice,bg='#f3effa',fg='#766d86',wraplength=850,font=('맑은 고딕',9)).pack(pady=4)
        buttons=tk.Frame(self.window,bg='#f3effa',padx=24,pady=14);buttons.pack(fill='x')
        ttk.Button(buttons,text='저장 안 함',command=self.cancel).pack(side='left')
        ttk.Button(buttons,text='이대로 저장',command=self.save).pack(side='right')
        tk.Label(buttons,text='원본은 항상 보존합니다.',bg='#f3effa',fg='#766d86').pack(side='right',padx=14)
        self.select_job()
        self.window.lift();self.window.focus_force()

    def select_job(self):
        result=self.results[self.jobs.current()]
        sources=result.get('source_files') or [result['source']]
        self.before.set(sources,result.get('_before_views',[None]*len(sources)))
        self.after.set(result['files'],result.get('_after_views',[None]*len(result['files'])))
        before=sum(Path(p).stat().st_size for p in sources)
        after=sum(Path(p).stat().st_size for p in result['files'])
        difference=f' · {(1-after/before)*100:.1f}% 줄어듦' if before and after<before else ''
        self.summary.set(f'{byte_label(before)} → {byte_label(after)}{difference} · 결과 {len(result["files"])}개')
        notice='저장을 누르기 전에는 결과 폴더를 만들지 않아요.'
        if result.get('scan_angles') is not None:notice+=' 기울기 보정: '+', '.join(f'{v:+.1f}°' for v in result['scan_angles'][:6])
        if result.get('_preview_warnings'):notice+=' 일부 화면은 생성하지 못했어요. 파일 이름·용량으로 확인할 수 있어요.'
        self.notice.set(notice)
        self.align_source()

    def align_source(self):
        result=self.results[self.jobs.current()]
        starts=result.get('source_page_starts',{})
        name=Path(result['files'][max(0,self.after.select.current())]).name
        if name in starts:
            self.before.page=starts[name]+self.after.page;self.before.draw()
        elif result.get('source_page_order') and len(result['files'])==1:
            order=result['source_page_order']
            self.before.page=order[min(self.after.page,len(order)-1)];self.before.draw()
        elif len(result.get('source_files') or [result['source']])==1:
            if len(result['files'])>1 and self.before.count>=len(result['files']):
                self.before.page=max(0,self.after.select.current());self.before.draw()
            elif self.before.count==self.after.count:
                self.before.page=self.after.page;self.before.draw()

    def save(self):
        try:
            for i,result in enumerate(self.results):
                self.results[i]=commit_preview(result)
        except Exception as error:
            messagebox.showerror(TITLE,'저장하지 못했어요. 다시 시도해 주세요.\n'+str(error),parent=self.window)
            return
        self.close(False)

    def cancel(self):
        try:
            for result in self.results:discard_preview(result)
        except Exception as error:
            messagebox.showerror(TITLE,'임시 결과를 정리하지 못했어요.\n'+str(error),parent=self.window)
            return
        self.results[:]=[r for r in self.results if not r.get('_pending')]
        self.close(True)

    def close(self,cancelled):
        if self.closed:return
        self.closed=True;self.window.destroy();self.on_decision(cancelled)
