import sys, os
import math
import datetime
import pytz
import code
import pickle
from functools import reduce
import trader.AlgoGUI as Alg
import trader.ManagerGUI as Man
from trader.Algorithm import *


class Manager:
    def __init__(self):

        # Variables that the user can change
        self.running = False
        self.algo_alloc = {}
        self.algo_times = {}
        # Private variables
        self.graphing = False
        self.portfolio = portfoliodata()
        # Variables that change automatically
        self.value = self.portfolio["value"]
        self.cash = self.portfolio["cash"]
        self.chartminute = []
        self.chartminutetimes = []
        self.chartday = []
        self.chartdaytimes = []
        self.stocks = {}
        self.updatemin()

    # Adds an algorithm to the manager.
    # Allocation is the decimal proportion of the total portfolio to use for the algorithm.
    # Times is the times of the day that the algorithm's run() function will be called.
    # Use a list of: tuples (hour,minute), datetime.time(hour,minute), "every minute", "every hour", "every day"
    def add(self, algorithm, allocation=1):
        self.algo_alloc[algorithm] = allocation
        for time in algorithm.times:
            if time == 'every minute':
                for hour in range(9, 16):
                    for minute in (list(range(30, 60)) if hour == 9 else list(range(0, 60))):
                        if datetime.time(hour, minute) in self.algo_times:
                            self.algo_times[datetime.time(hour, minute)] += [algorithm]
                        else:
                            self.algo_times[datetime.time(hour, minute)] = [algorithm]
            elif time == 'every hour':
                for hour in range(10, 17):
                    if datetime.time(hour, 0) in self.algo_times:
                        self.algo_times[datetime.time(hour, 0)] += [algorithm]
                    else:
                        self.algo_times[datetime.time(hour, 0)] = [algorithm]
            elif time == 'every day':
                if datetime.time(9, 31) in self.algo_times:
                    self.algo_times[datetime.time(9, 31)] += [algorithm]
                else:
                    self.algo_times[datetime.time(9, 31)] = [algorithm]
            elif type(time) is tuple:
                if time[0] < 7:
                    time = (time[0]+12,time[1])
                if datetime.time(time[0], time[1]) in self.algo_times:
                    self.algo_times[datetime.time(time[0], time[1])] += [algorithm]
                else:
                    self.algo_times[datetime.time(time[0], time[1])] = [algorithm]
            elif type(time) is datetime.time:
                if time in self.algo_times:
                    self.algo_times[time] += [algorithm]
                else:
                    self.algo_times[time] = [algorithm]

    # Removes an algorithm from the manager
    def remove(self, algorithm):
        del self.algo_alloc[algorithm]
        delete = []
        for time, algolist in list(self.algo_times.items()):
            if algorithm in algolist:
                algolist.remove(algorithm)
                if len(self.algo_times[time]) == 0:
                    delete.append(time)
        for time in delete:
            del self.algo_times[time]

    # Starts running the algorithms
    # To stop, set self.running = False
    # Always move stocks into algos and call rebalance() before calling start()
    def start(self):
        self.running = True
        tradingthread = threading.Thread(target=self.run)
        tradingthread.start()

    # Redistributes the capital among the algorithms according to the
    # specified allocations in self.algo_alloc.
    # Funds become unbalanced when some algorithms outperform others
    # or algo_alloc is manually edited.
    def rebalance(self):
        total_allocation = 0
        for algo, alloc in self.algo_alloc.items():
            if not algo.running:
                total_allocation += alloc
        if total_allocation > 1:
            raise Exception("You have allocated more than 100%% of your portfolio")
            return
        newcash = {}
        for algo in self.algo_alloc:
            startingcapital = math.floor(self.value * self.algo_alloc[algo])
            cash = startingcapital - (algo.value - algo.cash)
            if cash < 0:
                raise Exception("You are trying to allocate less than Algorithm " + 
                                algo.__class__.__name__ + " already has in stocks.")
                continue
            if cash > self.cash and not algo.running:
                raise Exception("You are trying to allocate more cash than you have to an Algorithm. " + 
                                "Either sell those other stocks, transfer them into the algorithm "
                                "with assignstocks(stocks,algo), or lower your allocation.")
            newcash[algo] = (startingcapital, cash)
        for algo, (startingcapital, cash) in newcash.items():
            algo.startingcapital = startingcapital
            algo.cash = cash
            algo.updatetick()

    # Keep algorithm manager running and enter interactive mode
    # Allows you to view and change class attributes from the command line
    def interactive(self,vars={}):
        code.interact(local={**locals(),**vars})

    # Opens GUI of all algorithms in the manager
    def gui(self,thread=True):
        desktoptrader = Man.Gui(self)
        if thread:
            guithread = threading.Thread(target=desktoptrader.mainloop)
            guithread.start()
        else:
            desktoptrader.mainloop()

    # Opens the GUI to visualize the Algorithm's performance (also works with Backtests)
    @staticmethod
    def algogui(algo,thread=False):
        desktoptrader = Alg.Gui(algo)
        if thread:
            guithread = threading.Thread(target=desktoptrader.mainloop)
            guithread.start()
        else:
            desktoptrader.mainloop()

    # Graphs portfolio performance
    # Press 'q' to exit
    # timeframe = 'daily', '1min' (plotting resolution)
    def graph(self, timeframe='day'):
        import matplotlib.pyplot as plt
        plt.ion()
        plt.xkcd()
        cid = plt.gcf().canvas.mpl_connect('key_press_event', self.quit_figure)
        self.graphing = True
        while self.graphing:
            if timeframe == '1min':
                plt.plot(self.chartminute, 'b')
            else:
                plt.plot(self.chartday, 'b')
            plt.title(('Portfolio: $%0.2f    Day Change: %0.2f%%' % (self.value, self.portfolio["day change"])))
            plt.pause(0.05)

    # Private Method
    # Graph callback helper
    def quit_figure(self, event):
        import matplotlib.pyplot as plt
        if event.key == 'q':
            plt.close(event.canvas.figure)
            self.graphing = False

    # Private Method
    # Updates the data in each algorithm continuously
    # Runs each algorithm at the right time of day
    def run(self):
        lasttime = None
        lastday = None
        # function that returns a boolean for if the given day is a trading day
        tradingday = lambda currentday: tradingdays(start=currentday,end=currentday+datetime.timedelta(days=1))[0].date() == currentday
        # boolean trading day flag
        istradingday = tradingday(datetime.datetime.now(timezone('US/Eastern')).date())
        # Main Loop
        while self.running:
            time.sleep(1)
            try:
                # Get time and day
                currenttime = datetime.time(datetime.datetime.now(timezone('US/Eastern')).hour, datetime.datetime.now(timezone('US/Eastern')).minute)
                currentday = datetime.datetime.now(timezone('US/Eastern')).date()
                # If trading is open
                if istradingday and currenttime >= datetime.time(9,30) and currenttime <= datetime.time(16,0):
                    if currenttime != lasttime:
                        # Update minute
                        for algo in list(self.algo_alloc.keys()):
                            algo.datetime = datetime.datetime.combine(currentday, currenttime)
                            algo.updatemin()
                        self.updatemin()
                        # Update day
                        if currentday != lastday:
                            istradingday = tradingday(currentday)
                            lastday = currentday
                            self.updateday()
                            for algo in list(self.algo_alloc.keys()):
                                algo.updateday()
                        # Run algorithms
                        if lasttime != currenttime:
                            lasttime = currenttime
                            if lasttime in self.algo_times:
                                # Run all algorithms associated with that time
                                for algo in self.algo_times[currenttime]:
                                    algothread = threading.Thread(target=algo.runalgo)
                                    algothread.start()
            except Exception as err:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                print(err)
                print(exc_type, fname, exc_tb.tb_lineno)

    # Private Method
    # Called every tick
    # Updates the data in the Manager
    # Allows you to track how the portfolio is doing in real time
    def updatetick(self):
        portfolio = portfoliodata()
        self.value = portfolio["value"]
        self.cash = portfolio["cash"]

    # Private Method
    # Called every minute
    # Updates the data in the Manager
    def updatemin(self):
        portfolio = portfoliodata()
        self.value = portfolio["value"]
        self.cash = portfolio["cash"]
        self.chartminute.append(self.value)
        self.chartminutetimes.append(datetime.datetime.now(timezone('US/Eastern')))
        for name, amount in positions().items():
            if amount == 0:
                self.stocks.pop(name, None)
            else:
                self.stocks[name] = amount

    # Private Method
    # Called at the start of every day
    def updateday(self):
        self.chartminute = []
        self.chartminutetimes = []
        self.chartday.append(self.value)
        self.chartdaytimes.append(datetime.datetime.now(timezone('US/Eastern')))

    # Moves stocks that you already hold into an algorithm
    # It will prevent you from trying to assign more of a stock than you actually own
    # stocks: Can be a list of symbols (moves all shares of each given stock),
    #       a dict of {symbol: shares to have in algo}, 'all' (which allocates everything),
    #       'none' (which removes everything), or a string of the symbol (allocates all shares)
    # algo: The algorithm you are moving the stocks to
    def assignstocks(self, stocks, algo):
        # Assign stocks to the algo
        if stocks == 'all':
            for stock, amount in self.stocks.items():
                algo.stocks[stock] = (amount - self.numstockinalgos(stock, algo))
        elif stocks == 'none':
            algo.stocks = {}
        elif type(stocks) == list:
            for stock in stocks:
                algo.stocks[stock] = (self.stocks[stock] - self.numstockinalgos(stock, algo))
        elif type(stocks) == dict:
            for (stock, amount) in stocks.items():
                algo.stocks[stock] = min(amount, self.stocks[stock]-self.numstockinalgos(stock, algo))
        else:
            algo.stocks[stocks] = (self.stocks[stocks] - self.numstockinalgos(stocks, algo))
        # Update the algo's value
        value = 0
        for stock, amount in algo.stocks.items():
            value += price(stock) * amount
        algo.value = value + algo.cash

    # Helper function for assignstocks.
    # Gets the total number of a given stock in all algos (except given algo, if given)
    def numstockinalgos(self, stock, algo=None):
        numstock = 0
        for algorithm in list(self.algo_alloc.keys()):
            numstock += (algorithm.stocks[stock] if (stock in algorithm.stocks) else 0)
        if algo != None:
            numstock -= (algo.stocks[stock] if (stock in algo.stocks) else 0)
        return numstock



def save_manager(manager_obj,path='manager_save'):
    fh = open(path,'wb')
    pickle.dump(manager_obj,path)
    return path


def load_manager(path='manager_save'):
    fh = open(path,'rb')
    manager = pickle.load(fh)
    return manager


if __name__ == '__main__':
    import code; code.interact(local=locals())


# High Priority
# TODO: load and save data when closed/opened with pickle https://www.thoughtco.com/using-pickle-to-save-objects-2813661


# Medium priority
# TODO: Avoid running every second and logging when not in market hours
# TODO: Adaptive allocations
# TODO: Fix closing gui update issue
# TODO: Add benchmarks to live


# Low Priority
# TODO: Comment functions that don't have descriptions
# TODO: Add support for more brokers
# TODO: Use daily logging close in backtest for algos that run at 3:59
# TODO: Use yahoo-finance data when alphavantage fails
# TODO: Add python3 type checking to functions
# TODO: Prevent day trades, Combine concurrent orders for same stock


