import math
import code
import trader.tradingdays
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
                if datetime.time(9, 30) in self.algo_times:
                    self.algo_times[datetime.time(9, 30)] += [algorithm]
                else:
                    self.algo_times[datetime.time(9, 30)] = [algorithm]
            elif type(time) is tuple:
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
        total_allocation = reduce(lambda x, y: x + y, list(self.algo_alloc.values()), 0)
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
                return
            if cash > self.cash:
                raise Exception("You are trying to allocate more cash than you have to an Algorithm. " + 
                                "Either sell those other stocks, transfer them into the algorithm "
                                "with assignstocks(stocks,algo), or lower your allocation.")
            newcash[algo] = (startingcapital, cash)
        for algo, (startingcapital, cash) in newcash.items():
            algo.startingcapital = startingcapital
            algo.cash = cash

    # Keep algorithm manager running and enter interactive mode
    # Allows you to view and change class attributes from the command line
    def interactive(self,vars={}):
        code.interact(local={**locals(),**vars})

    # Opens GUI of all algorithms in the manager
    def gui(self):
        desktoptrader = Man.Gui(self)
        desktoptrader.mainloop()

    # Opens the GUI to visualize the Algorithm's performance (also works with Backtests)
    @staticmethod
    def algogui(algo):
        desktoptrader = Alg.Gui(algo)
        desktoptrader.mainloop()

    # Graphs portfolio performance
    # Press 'q' to exit
    # timeframe = 'daily', '1min' (plotting resolution)
    def graph(self, timeframe='daily'):
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
        while self.running:
            time.sleep(1)
            try:
                currenttime = datetime.time(datetime.datetime.now().hour, datetime.datetime.now().minute)
                currentday = datetime.datetime.today().date()
                if len(list(tradingdays.NYSE_tradingdays(a=currentday,b=currentday+datetime.timedelta(days=1)))) > 0:
                    for algo in list(self.algo_alloc.keys()):
                        algo.updatetick()
                    self.updatetick()
                    if currenttime != lasttime:
                        lasttime = currenttime
                        for algo in list(self.algo_alloc.keys()):
                            algo.updatemin()
                        self.updatemin()
                        if currentday != lastday:
                            lastday = currentday
                            self.updateday()
                            for algo in list(self.algo_alloc.keys()):
                                algo.updateday()
                        if currenttime in self.algo_times:
                            for algo in self.algo_times[currenttime]:
                                algo.run()
            except:
                pass

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
        self.chartminute.append(self.value)
        self.chartminutetimes.append(datetime.datetime.now())
        for name, amount in positions().items():
            if amount == 0:
                self.stocks.pop(name, None)
            else:
                self.stocks[name] = amount

    # Moves stocks that you already hold into an algorithm
    # It will prevent you from trying to assign more of a stock than you actually own
    # stocks: Can be a list of symbols (moves all shares of each given stock),
    # 		a dict of {symbol: shares to have in algo}, 'all' (which allocates everything),
    # 		'none' (which removes everything), or a string of the symbol (allocates all shares)
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
            for stock, amount in stocks:
                algo.stocks[stock] = (min(amount, self.stocks[stock]) - self.numstockinalgos(stock, algo))
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

    # Private Method
    # Called at the start of every day
    def updateday(self):
        self.chartminute = []
        self.chartminutetimes = []
        self.chartday.append(self.value)
        self.chartdaytimes.append(datetime.datetime.now())



if __name__ == '__main__':
    import code; code.interact(local=locals())


# High Priority
# TODO: load and save data when closed/opened with pickle https://www.thoughtco.com/using-pickle-to-save-objects-2813661


# Medium priority
# TODO: Avoid running every second and logging when not in market hours
# TODO: Adaptive allocations
# TODO: Fix closing gui update issue


# Low Priority
# TODO: Comment functions that don't have descriptions
# TODO: Add support for more brokers
# TODO: Use daily logging close in backtest for algos that run at 3:59
# TODO: Use yahoo-finance data when alphavantage fails
# TODO: Add python3 type checking to functions
# TODO: Prevent day trades, Combine concurrent orders for same stock


