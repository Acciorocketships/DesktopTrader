import trader.AlgoGUI as app
from tkinter import *

class Gui(Tk):
    def __init__(self, manager, root=None):
        self.manager = manager
        Tk.__init__(self, root)
        if root is None:
            self.protocol("WM_DELETE_WINDOW",self.close)
            # Window
            self.title('Desktop Trader')
            self.geometry('{}x{}'.format(1024, 576))
            # Transparency
            self.wm_attributes("-alpha", 0.95)
            self.config(bg='systemTransparent')
        # Background
        self.background = Frame(self, root, bg='sea green', width=100, height=100, padx=5, pady=5)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.background.grid(row=0, column=0, sticky=N + E + W + S)
        # Other
        self.pages = {}
        self.activepage = StringVar();
        self.activepage.trace("u", self.changepage())
        # Layout
        self.layout(self.background, manager)

    def close(self):
        for name, algogui in self.pages.items():
            algogui.windowisopen = False
            algogui.after_cancel(algogui.afterid)
        self.destroy()
        self.quit()

    def layout(self, root, manager):
        # Navigation
        navigationframe = Frame(master=root, padx=10, pady=0, bg='sea green')
        navigationframe.pack(side=TOP, fill=X)
        navigation = Frame(master=navigationframe, bg='sea green')
        navigation.pack(fill=BOTH, expand=True)
        for algo in list(manager.algo_alloc.keys()):
            button = Radiobutton(master=navigation, text=algo.__class__.__name__, variable=self.activepage,
                                 value=algo.__class__.__name__, command=self.changepage)
            button.pack(side=LEFT)
        # Pages
        pageframe = Frame(master=root, bg='sea green')
        pageframe.pack(side=BOTTOM, expand=True, fill=BOTH)
        self.pages = {}
        for algo in list(manager.algo_alloc.keys()):
            page = app.Gui(algo, root=pageframe)
            page.place(in_=pageframe, x=0, y=0, relwidth=1, relheight=1)
            self.pages[algo.__class__.__name__] = page
            self.activepage.set(algo.__class__.__name__)
        self.changepage()

    def changepage(self):
        if self.activepage.get() in self.pages:
            self.pages[self.activepage.get()].tkraise()
