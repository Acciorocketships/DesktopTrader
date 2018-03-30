import trader.Algorithm as alg
from tkinter import *
import matplotlib

matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime
import numpy as np
import code


class Gui(Frame):
    def __init__(self, algorithm=None, root=None):

        self.algo = algorithm

        if root is None:
            window = Tk()
            # Window
            window.title('Desktop Trader')
            window.geometry('{}x{}'.format(1024, 576))
            # Transparency
            window.wm_attributes("-alpha", 0.95)
            #This only works on MacOSX
            if sys.platform.startswith("darwin"):
                window.config(bg='systemTransparent')
            Frame.__init__(self, master=window, bg='sea green', width=100, height=100, padx=5, pady=5)
        else:
            Frame.__init__(self, master=root, bg='sea green', width=100, height=100, padx=5, pady=5)
        self.pack(fill=BOTH, expand=True)
        # Graph
        self.graph = None
        self.attributes = None
        self.stocks = None
        self.stats = None
        self.plotres = StringVar();
        self.plotres.set('minute')
        self.plotres.trace("u", self.update())
        # Layout
        self.layout(self)
        self.after(500, self.update())

    def update(self):
        if self.graph is not None:
            self.graph.clear()
            if isinstance(self.algo, alg.Backtester):
                self.graph.plotbenchmark(self.algo)
                self.graph.plot(self.algo.chartdaytimes, self.algo.chartday)
            elif isinstance(self.algo, alg.Algorithm):
                if self.plotres.get() == 'minute':
                    self.graph.plot(self.algo.chartminutetimes, self.algo.chartminute)
                elif self.plotres.get() == 'day':
                    self.graph.plot(self.algo.chartdaytimes, self.algo.chartday)
        if self.attributes is not None:
            self.attributes.update()
        if self.stocks is not None:
            self.stocks.update()
        if self.stats is not None:
            self.stats.update()
        self.after(500, self.update)

    def layout(self, root):
        # Graph
        graphframe = Frame(master=root, padx=5, pady=5, bg='sea green')
        add(graphframe, root, 0, 0, colspan=2)
        graphborder = Frame(master=graphframe, padx=4, pady=4, bg='black')
        graphborder.pack(fill=BOTH, expand=True)
        if not isinstance(self.algo, alg.Backtester):
            # Toolbar
            toolbar = Frame(master=graphborder)
            toolbar.pack(side=BOTTOM, fill=X)
            # Resolution buttons
            resolution = Frame(master=toolbar)
            resolution.pack(expand=True, fill=None)
            minutebutton = Radiobutton(master=resolution, text='Minute', variable=self.plotres, value='minute')
            daybutton = Radiobutton(master=resolution, text='Day', variable=self.plotres, value='day')
            minutebutton.pack(side=LEFT)
            daybutton.pack(side=LEFT)
        self.graph = Graph(graphborder)
        self.graph.widget().pack(side=TOP, fill=X, expand=True)
        # Class Attributes
        attributeframe = Frame(master=root, padx=0, pady=5, bg='sea green')
        add(attributeframe, root, 0, 2, rowspan=3, weight=6)
        attributeborder = Frame(master=attributeframe, bg='black', padx=4, pady=4)
        attributeborder.pack(fill=BOTH, expand=True)
        attributelabel = Label(master=attributeborder, text="Class Attributes", bg='sea green')
        attributelabel.pack(fill=X, side=TOP)
        self.attributes = Attributes(master=attributeborder, source=self.algo)
        self.attributes.pack(fill=BOTH, expand=True)
        # Stocks
        stockframe = Frame(master=root, padx=5, pady=5, bg='sea green', height=100, width=50)
        add(stockframe, root, 2, 1, weight=5)
        stockborder = Frame(master=stockframe, bg='black', padx=4, pady=4)
        stockborder.pack(fill=BOTH, expand=True)
        stocklabel = Label(master=stockborder, text="Stocks", bg='sea green')
        stocklabel.pack(fill=X, side=TOP)
        self.stocks = Stocks(master=stockborder, source=self.algo)
        self.stocks.pack(fill=BOTH, expand=True)
        # Statistics
        statframe = Frame(master=root, padx=5, pady=5, bg='sea green', height=100)
        add(statframe, root, 2, 0, weight=5)
        statborder = Frame(master=statframe, bg='black', padx=4, pady=4)
        statborder.pack(fill=BOTH, expand=True)
        statlabel = Label(master=statborder, text="Statistics", bg='sea green')
        statlabel.pack(fill=X, side=TOP)
        self.stats = Stats(master=statborder, source=self.algo)
        self.stats.pack(fill=BOTH, expand=True)


class Stats(Text):
    def __init__(self, master, source, bg='sea green'):
        Text.__init__(self, master, bg=bg, wrap=WORD)
        self.source = source
        self.update()

    def update(self):
        self.config(state=NORMAL)
        self.delete(1.0, END)
        if isinstance(self.source, alg.Backtester):
            self.insert(END, 'Date: ' + str(self.source.datetime) + '\n')
        else:
            self.insert(END, 'Date: ' + str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + '\n')
        self.insert(END, 'Return: ' + str(round(self.source.value / self.source.startingcapital - 1,
                                                2) if self.source.startingcapital != 0 else 0) + '\n')
        self.insert(END, 'Total Value: $' + str(self.source.value) + '\n')
        self.insert(END, 'Cash: $' + str(self.source.cash) + '\n')
        self.insert(END, 'Alpha: ' + str(self.source.alpha) + '\n')
        self.insert(END, 'Beta: ' + str(self.source.beta) + '\n')
        self.insert(END, 'Sharpe: ' + str(self.source.sharpe) + '\n')
        self.insert(END, 'Volatility: ' + str(self.source.volatility) + '\n')
        self.insert(END, 'Max Drawdown: ' + str(self.source.maxdrawdown) + '\n')
        self.config(state=DISABLED)


class Stocks(Text):
    def __init__(self, master, source, bg='sea green'):
        Text.__init__(self, master, bg=bg, wrap=WORD)
        self.source = source
        self.update()

    def update(self):
        self.config(state=NORMAL)
        self.delete(1.0, END)
        for stock, amount in self.source.stocks.items():
            if isinstance(self.source, alg.Backtester):
                self.insert(END, str(stock) + ':  ' + str(int(amount)) + '  $' + str(
                    self.source.history(stock, interval=self.source.logging)[0].item()) + '\n')
            else:
                self.insert(END, str(stock) + ':  ' + str(int(amount)) + '  $' + str(self.source.quote(stock)) + '\n')
        self.config(state=DISABLED)


class Attributes(Text):
    dontshow = set(
        ['minutesago', 'daysago', 'logging', 'chartday', 'chartdaytimes', 'chartminute', 'running', 'benchmark', \
         'chartminutetimes', 'cache', 'startingcapital', 'cash', 'value', 'stocks', 'times', 'datetime', 'openorders', \
         'stoplosses', 'stopgains', 'alpha', 'beta', 'maxdrawdown', 'volatility', 'sharpe','exptime'])

    def __init__(self, master, source, bg='sea green'):
        Text.__init__(self, master, bg=bg, wrap=WORD)
        self.source = source
        self.update()

    def update(self):
        self.config(state=NORMAL)
        self.delete(1.0, END)
        if type(self.source) == list:
            for item in source:
                self.insert(END, str(item))
        elif isinstance(self.source, alg.Algorithm):
            for name, value in self.source.__dict__.items():
                if name not in Attributes.dontshow:
                    self.insert(END, (" " + str(name) + ": " + str(value)) + "\n")
        self.config(state=DISABLED)


class Graph(FigureCanvasTkAgg):
    def __init__(self, master=None):
        plt.xkcd()
        self.fig = plt.figure(figsize=(12, 6), dpi=100)
        self.mainplot = self.fig.add_subplot(111)
        FigureCanvasTkAgg.__init__(self, self.fig, master=master)
        self.mpl_connect('key_press_event', self.keypress)
        self.draw()
        self.show()

    def keypress(self, event):
        pass

    def clear(self):
        self.mainplot.cla()

    def plotbenchmark(self, algo):
        if isinstance(algo, alg.Backtester) and algo.benchmark is not None:
            benchmarks = algo.benchmark[:]
            if type(algo.benchmark) == str:
                benchmarks = [benchmarks]
            for stock in benchmarks[::-1]:
                benchmark = algo.history(stock, interval=algo.logging, length=len(
                    algo.chartdaytimes if algo.logging == 'daily' else algo.chartminutetimes))
                benchmark = [value * algo.startingcapital / benchmark[0] for value in benchmark]
                color = 'r-' if stock==benchmarks[0] else None
                self.plot(algo.chartdaytimes, benchmark, color=color, fill=False)

    def plot(self, x, y, color='b-', fill=True):
        try:
            if len(y) != 0:
                self.mainplot.plot_date(x, y, color)
                if fill:
                    self.mainplot.fill_between(x, y, y2=y[0], color="b", alpha=0.2)
                maxy = max(y)
                self.fig.autofmt_xdate()
                self.draw()
        except:
            pass

    def widget(self):
        return self.get_tk_widget()


class Spacer(Frame):
    def __init__(self, master, width=0, height=0):
        Frame.__init__(self, master, bg=master["background"], width=width, height=height)


def add(widget, master, row, col, rowspan=1, colspan=1, sticky=N + E + W + S, padx=0, pady=0, weight=5):
    master.columnconfigure(col, weight=weight)
    master.rowconfigure(row, weight=weight)
    widget.grid(row=row, column=col, sticky=sticky, padx=padx, pady=pady, rowspan=rowspan, columnspan=colspan)
