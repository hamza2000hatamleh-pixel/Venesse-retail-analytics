"""Desktop launcher for the existing Venesse agent. Run with its Python environment."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from contextlib import redirect_stdout


class _ProgressStream:
    def __init__(self, events):self.events=events
    def write(self, text):
        if text:self.events.put(('log',text))
        return len(text)
    def flush(self):pass


class VenesseWindow:
    def __init__(self, root):
        self.root=root
        self.events=queue.Queue()
        self.busy=False
        self.last_report=None
        root.title('Venesse Business Agent')
        root.geometry('980x720')
        root.minsize(760,560)
        root.configure(bg='#eef2f7')
        style=ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame',background='#eef2f7')
        style.configure('TLabel',background='#eef2f7',foreground='#172033',font=('Segoe UI',11))
        style.configure('Title.TLabel',font=('Segoe UI',25,'bold'))
        style.configure('TButton',font=('Segoe UI',10),padding=8)
        frame=ttk.Frame(root,padding=26);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Venesse Business Agent',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Ask about your business. Generate reports from your existing Venesse data.').pack(anchor='w',pady=(6,20))
        toolbar=ttk.Frame(frame);toolbar.pack(fill='x')
        ttk.Label(toolbar,text='Report year').pack(side='left')
        self.year=tk.StringVar(value='2026')
        self.year_box=ttk.Spinbox(toolbar,from_=2000,to=2099,textvariable=self.year,width=7)
        self.year_box.pack(side='left',padx=10)
        shortcuts_frame=ttk.Frame(frame)
        shortcuts_frame.pack(fill='x',pady=(12,0))
        self.shortcuts=[]
        topics=[('Full dashboard','full'),('Sales','sales'),('Customers','customer'),('Retention','retention'),
                ('Products','product'),('Marketing','marketing'),('Feedback','feedback'),('Operating','operating')]
        for index,(title,topic) in enumerate(topics):
            button=ttk.Button(shortcuts_frame,text=title,command=lambda t=topic:self.shortcut(t))
            button.grid(row=index//4,column=index%4,sticky='ew',padx=3,pady=3)
            self.shortcuts.append(button)
        for column in range(4):shortcuts_frame.columnconfigure(column,weight=1)
        ttk.Label(frame,text='Your request').pack(anchor='w',pady=(22,6))
        self.request=tk.Text(frame,height=3,wrap='word',font=('Segoe UI',12),relief='solid',bd=1,padx=12,pady=10)
        self.request.pack(fill='x')
        self.request.insert('1.0','Generate full HTML report for 2026')
        self.request.bind('<Control-Return>',lambda event:self.run())
        actions=ttk.Frame(frame);actions.pack(fill='x',pady=12)
        self.run_button=ttk.Button(actions,text='Generate report',command=self.run);self.run_button.pack(side='left')
        self.open_button=ttk.Button(actions,text='Open last report',command=self.open_report,state='disabled');self.open_button.pack(side='left',padx=8)
        self.progress=ttk.Progressbar(actions,mode='indeterminate',length=170);self.progress.pack(side='right')
        self.status=tk.StringVar(value='Ready · Ctrl+Enter to run')
        ttk.Label(frame,textvariable=self.status).pack(anchor='w',pady=(0,10))
        ttk.Label(frame,text='Results and token usage').pack(anchor='w',pady=(5,6))
        container=ttk.Frame(frame);container.pack(fill='both',expand=True)
        self.results=tk.Text(container,wrap='word',font=('Consolas',10),bg='#ffffff',fg='#172033',padx=14,pady=12,state='disabled')
        scrollbar=ttk.Scrollbar(container,command=self.results.yview)
        self.results.configure(yscrollcommand=scrollbar.set)
        self.results.pack(side='left',fill='both',expand=True);scrollbar.pack(side='right',fill='y')
        ttk.Label(frame,text='January–September reporting · API credentials use your existing run configuration.').pack(anchor='w',pady=(12,0))
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)

    def append(self,text):
        self.results.configure(state='normal');self.results.insert('end',text);self.results.see('end');self.results.configure(state='disabled')

    def shortcut(self,topic):
        try:
            year=int(self.year.get())
            if not 2000<=year<=2099:raise ValueError
        except ValueError:
            messagebox.showerror('Report year','Enter a year between 2000 and 2099.');return
        self.request.delete('1.0','end');self.request.insert('1.0',f'Generate {topic} HTML report for {year}')
        self.run()

    def run(self):
        if self.busy:return
        task=self.request.get('1.0','end').strip()
        if not task:
            self.status.set('Enter a business request first.');self.request.focus_set();return
        self.busy=True
        self.run_button.configure(state='disabled')
        for button in self.shortcuts:button.configure(state='disabled')
        self.request.configure(state='disabled');self.year_box.configure(state='disabled')
        self.status.set('Generating report… Please keep this window open.')
        self.progress.start(12)
        self.append('\n'+'─'*55+'\nRequest: '+task+'\n\n')
        threading.Thread(target=self.worker,args=(task,),daemon=True).start()

    def worker(self,task):
        # The worker never touches Tk widgets; progress is delivered by queue.
        try:
            with redirect_stdout(_ProgressStream(self.events)):
                from venesse_ai_agent_edit import business_agent
                result=business_agent(task)
            self.events.put(('result',str(result)))
        except Exception as error:
            # Do not expose arbitrary exception bodies: SDK errors may contain secrets.
            self.events.put(('error',f'Report could not be completed ({type(error).__name__}). Check the Python dependencies, database connection, and API run settings.'))
        finally:self.events.put(('done',None))

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':self.append(value)
                elif kind=='result':
                    self.append(value+'\n')
                    lines=value.splitlines()
                    path=Path(lines[-1]) if lines else None
                    if 'saved successfully:' in value and path and path.suffix.lower() in ('.html','.txt') and path.is_file():
                        self.last_report=path.resolve();self.open_button.configure(state='normal')
                        self.status.set('Report saved. Use Open last report to view it again.')
                    else:self.status.set('Request completed. See results below.')
                elif kind=='error':self.append(value+'\n');self.status.set('Request failed. See results below.')
                elif kind=='done':
                    self.busy=False;self.progress.stop();self.run_button.configure(state='normal')
                    self.request.configure(state='normal');self.year_box.configure(state='normal')
                    for button in self.shortcuts:button.configure(state='normal')
        except queue.Empty:pass
        self.root.after(100,self.poll)

    def open_report(self):
        if self.last_report and self.last_report.is_file():webbrowser.open(self.last_report.as_uri())
        else:messagebox.showinfo('Report unavailable','The saved report has been moved or deleted.')

    def close(self):
        if self.busy:
            messagebox.showinfo('Report running','Wait for the current request to finish before closing.');return
        self.root.destroy()


if __name__=='__main__':
    # Keep exports and usage logs beside the project, even with another launcher cwd.
    import os
    os.chdir(Path(__file__).resolve().parent)
    app=tk.Tk()
    VenesseWindow(app)
    app.mainloop()
