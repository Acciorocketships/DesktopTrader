import datetime
import time
import threading
from Robinhood import Robinhood
from alpha_vantage.timeseries import TimeSeries
from alpha_vantage.techindicators import TechIndicators
import code
import copy
import pandas
import tradingdays
import math
import requests
import AlgoGUI as app
import ManagerGUI as man

# https://github.com/RomelTorres/alpha_vantage
# https://github.com/Jamonek/Robinhood

creds = []
credential_file = "creds.txt"
try:
    with open(credential_file, "r") as f:
        creds = f.readlines()
except IOError:
    creds.append(raw_input('Robinhood Username: '))
    creds.append(raw_input('Robinhood Password: '))
    creds.append(raw_input('Alpha Vantage API Key: '))
    with open(credential_file, "w") as f:
        for l in creds:
            f.write(l + "\n")
except PermissionError:
    print("Cannot read credentials file.")
    exit(-1)

creds = [x.strip() for x in creds]
broker = Robinhood()
broker.login(username=creds[0], password=creds[1])

data = TimeSeries(key=creds[2], output_format='pandas')
tech = TechIndicators(key=creds[2], output_format='pandas')


class Manager:
    def __init__(self):

        # Variables that the user can change
        self.running = False
        self.algo_alloc = {}
        self.algo_times = {}
        # Private variables
        self.graphing = False
        self.portfolio = broker.portfolios()
        # Variables that change automatically
        self.value = float(self.portfolio['equity'])
        self.cash = self.portfolio['withdrawable_amount']
        self.daychangeperc = 100 * (self.value - float(self.portfolio['adjusted_equity_previous_close'])) / float(
            self.portfolio['adjusted_equity_previous_close'])
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
                    for minute in (range(30, 60) if hour == 9 else range(0, 60)):
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
        for time, algolist in self.algo_times.items():
            if algorithm in algolist:
                algolist.remove(algorithm)
                if len(self.algo_times[time]) == 0:
                    delete.append(time)
        for time in delete:
            del self.algo_times[time]

    # Starts running the algorithms
    # To stop, set self.running = False
    def start(self):
        self.running = True
        tradingthread = threading.Thread(target=self.run)
        tradingthread.start()

    # Redistributes the capital among the algorithms according to the
    # specified allocations in self.algo_alloc.
    # Funds become unbalanced when some algorithms outperform others
    # or algo_alloc is manually edited.
    # Always call this before start()
    def rebalance(self):
        total_allocation = reduce(lambda x, y: x + y, list(self.algo_alloc.values()), 0)
        if self.value * total_allocation > float(self.portfolio['withdrawable_amount']):
            print("Warning: You have allocated more than your buying power. \
				  Sell some stocks not already in your account or reduce your allocation percentages.")
            return
        newcash = {}
        for algo in self.algo_alloc:
            startingcapital = self.value * self.algo_alloc[algo]
            cash = startingcapital - (algo.value - algo.cash)
            if cash < 0:
                print("Warning: You are trying to deallocate more money than your algorithm has in cash. \
					   Sell stocks from or raise allocation of " + algo.__class__.__name__ + " and try \
					   rebalancing again")
                return
            newcash[algo] = (startingcapital, cash)
        for algo, (startingcapital, cash) in newcash:
            algo.startingcapital = startingcapital
            algo.cash = cash

    # Keep algorithm manager running and enter interactive mode
    # Allows you to view and change class attributes from the command line
    def interactive(self):
        code.interact(local=locals())

    def gui(self):
        desktoptrader = man.Gui(self)
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
            plt.title(('Portfolio: $%0.2f    Day Change: %0.2f%%' % (self.value, self.daychangeperc)))
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
        self.portfolio = broker.portfolios()
        if not (self.portfolio['extended_hours_equity'] is None):
            self.value = float(self.portfolio['extended_hours_equity'])
        else:
            self.value = float(self.portfolio['equity'])
        self.cash = self.portfolio['withdrawable_amount']
        self.daychangeperc = 100 * (self.value - float(self.portfolio['adjusted_equity_previous_close'])) / float(
            self.portfolio['adjusted_equity_previous_close'])

    # Private Method
    # Called every minute
    # Updates the data in the Manager
    # TODO: Make sure only one stock trades in a given minute
    def updatemin(self):
        self.chartminute.append(self.value)
        self.chartminutetimes.append(datetime.datetime.now())
        positions = broker.positions()['results']
        for position in positions:
            name = str(requests.get(position['instrument']).json()['symbol'])
            amount = float(position['quantity'])
            amountdiff = amount - (self.stocks[name] if name in self.stocks else 0)
            if amountdiff != 0:
                for algo in self.algo_alloc.keys():
                    if name in algo.openorders:
                        shareprice = abs((self.cash - self.lastcash) / amountdiff)
                        algo.stocks[name] += algo.openorders[name]
                        algo.cash -= shareprice * algo.openorders[name]
                        del algo.openorders[name]
            if amount == 0:
                self.stocks.pop(name, None)
            else:
                self.stocks[name] = amount
        self.lastcash = self.cash

    # Moves stocks that you already hold into an algorithm
    # It will prevent you from trying to assign more of a stock than you actually own
    # stocks: Can be a list of symbols (moves all shares of each given stock),
    # 		a dict of {symbol: shares to have in algo}, 'all' (which allocates everything),
    # 		'none' (which removes everything), or a string of the symbol (allocates all shares)
    # algo: The algorithm you are moving the stocks to
    def assignstocks(self, stocks, algo):
        if stocks == 'all':
            for stock, amount in self.stocks.iteritems():
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
            import pdb;
            pdb.set_trace()
            algo.stocks[stocks] = (self.stocks[stocks] - self.numstockinalgos(stocks, algo))

    # Helper function for assignstocks.
    # Gets the total number of a given stock in all algos (except given algo, if given)
    def numstockinalgos(self, stock, algo=None):
        numstock = 0
        for algorithm in self.algo_alloc.keys():
            numstock += (algorithm.stocks[stock] if (stock in algorithm.stocks) else 0)
        if algo != None:
            numstock -= (algo.stocks[stock] if (stock in algo.stocks) else 0)
        return numstock

    # Private Method
    # Called at the start of every day
    # TODO: Skip weekends
    def updateday(self):
        self.chartminute = []
        self.chartminutetimes = []
        self.chartday.append(self.value)
        self.chartdaytimes.append(datetime.datetime.now())


# To do manual trading, just add an algorithm object to Manager
# and manually call the buy(stock,amount) and sell(stock,amount) methods
class Algorithm(object):
    def __init__(self, times=['every minute']):
        # Constants
        self.times = times
        if type(self.times) is not list:
            self.times = [self.times]
        # Variables that change automatically
        self.startingcapital = 0
        self.value = 0
        self.cash = 0
        self.stocks = {}
        self.chartminute = []
        self.chartminutetimes = []
        self.chartday = []
        self.chartdaytimes = []
        self.running = True
        self.openorders = {}
        # User initialization
        self.initialize()

    # Override this method
    def initialize(self):
        pass

    def run(self):
        pass

    # Opens the GUI to visualize the Algorithm's performance (also works with Backtests)
    def gui(self):
        desktoptrader = app.Gui(self)
        desktoptrader.mainloop()

    # Switches from live trading to paper trading
    # If self.running is False, the algorithm will automatically paper trade
    def papertrade(self):
        if self.running:
            self.startingcapital = self.value
            self.cash = self.startingcapital
            self.stocks = {}
            self.chartminute = []
            self.chartday = []
            self.running = False

    # Switches from paper trading to live trading
    def livetrade(self):
        if not self.running:
            self.value = self.startingcapital
            self.cash = self.startingcapital
            self.stocks = {}
            self.chartminute = []
            self.chartday = []
            self.running = True

    # Private Method
    def updatetick(self):
        stockvalue = 0
        for stock, amount in self.stocks.items():
            stockvalue += self.quote(stock) * amount
        self.value = self.cash + stockvalue

    # Private Method
    def updatemin(self):
        self.chartminute.append(self.value)
        self.chartminutetimes.append(datetime.datetime.now())

    # Private Method
    def updateday(self):
        self.chartminute = []
        self.chartminutetimes = []
        self.chartday.append(self.value)
        self.chartdaytimes.append(datetime.datetime.now())
        self.openorders = {}

    # stock: stock symbol (string)
    # amount: number of shares of that stock to sell (int)
    # verbose: prints out order
    # noverify: assume that the order went through at the current price,
    #			as opposed to waiting for the manager to verify it (default)
    def buy(self, stock, amount, verbose=False, noverify=False):
        stockobj = broker.instruments(stock)
        cost = self.quote(stock)
        if cost * amount > self.cash:
            print("Warning: not enough cash ($" + str(self.cash) + ") in algorithm to buy " + str(
                amount) + " shares of " + stock)
            return None
        if noverify:
            if stock in self.stocks:
                self.stocks[stock] += amount
            else:
                self.stocks[stock] = amount
            self.cash -= cost * amount
        else:
            self.openorders[stock] = amount
        if verbose:
            print("Buying " + str(amount) + " shares of " + stock)
        if self.running:
            return broker.place_buy_order(stockobj, amount)

    # stock: stock symbol (string)
    # amount: number of shares of that stock to sell (int)
    # verbose: prints out order
    # noverify: assume that the order went through at the current price,
    #			as opposed to waiting for the manager to verify it (default)
    def sell(self, stock, amount, verbose=False):
        stockobj = broker.instruments(stock)
        if (stock in self.stocks) and (amount <= self.stocks[stock]):
            if noverify:
                self.stocks[stock] -= amount
                self.cash += self.quote(stock) * amount
            else:
                self.openorders[stock] = -amount
            if verbose:
                print("Selling " + str(amount) + " shares of " + stock)
            if self.running:
                return broker.place_sell_order(stockobj, amount)
        else:
            print("Warning: attempting to sell more shares (" + str(amount) + ") than are owned (" + str(
                self.stocks[stock] if stock in self.stocks else 0) + ") of " + stock)
            return None

    # Buy or sell to reach a target percent of the algorithm's total allocation
    def orderpercent(self, stock, percent, verbose=False):
        stockprice = self.quote(stock)
        currentpercent = 0.0
        if stock in self.stocks:
            currentpercent = self.stocks[stock] * stockprice / self.value
        percentdiff = percent - currentpercent
        if percentdiff < 0:
            amount = round(-percentdiff * self.value / stockprice)
            return self.sell(stock, amount, verbose)
        else:
            amount = math.floor(percentdiff * self.value / stockprice)
            return self.buy(stock, amount, verbose)

    # Use Alpha Vantage to get the historical price data of a stock
    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # datatype: 'adjusted close','close','open','volume','high','low' (default close)
    def history(self, stock, interval='1min', length=1, datatype='close'):
        if length <= 100:
            size = 'compact'
        else:
            size = 'full'
        if interval == 'daily':
            hist, _ = data.get_daily_adjusted(symbol=stock, outputsize=size)
        elif interval == 'weekly':
            hist, _ = data.get_weekly(symbol=stock)
        else:
            hist, _ = data.get_intraday(symbol=stock, interval=interval, outputsize=size)
        return hist[datatype][-length:]

    # Uses robinhood to get the current price of a stock
    # stock: stock symbol (string)
    def quote(self, stock):
        return float(broker.quote_data(stock)['last_trade_price'])

    # macd line: 12 day MA - 26 day MA
    # signal line: 9 period MA of the macd line
    # macd hist: macd - signal
    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # matype: 0 for SMA, 1 for EMA, 2 for WMA (Weighted), 3 for DEMA (Double Exponential), 4 for TEMA (Triple Exponential)
    # mawindow: number of days to average in moving average
    # returns dict of {'macd' : macd (list), 'signal' : signal (list), 'macd hist' : macd histogram (list)}
    def macd(self, stock, interval='daily', length=1, fastmawindow=12, slowmawindow=26, signalmawindow=9, fastmatype=1,
             slowmatype=1, signalmatype=1):
        md, _ = tech.get_macdext(stock, interval=interval, \
                                 fastperiod=fastmawindow, slowperiod=slowmawindow, signalperiod=signalmawindow, \
                                 fastmatype=fastmatype, slowmatype=slowmatype, signalmatype=signalmatype)
        return {'macd': md['MACD'][-length:], 'signal': md['MACD_Signal'][-length:],
                'macd hist': md['MACD_Hist'][-length:]}

    # nbdevup: multiplier for standard deviations of the top band above the middle band
    # nbdevdn: multiplier for standard deviations of the bottom band below the middle band
    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # matype: 0 for SMA, 1 for EMA, 2 for WMA (Weighted), 3 for DEMA (Double Exponential), 4 for TEMA (Triple Exponential)
    # mawindow: number of days to average in moving average
    # Returns dict of {'top': topband (list), 'bottom': bottomband (list), 'middle': middleband (list)}
    def bollinger(self, stock, interval='daily', length=1, nbdevup=2, nbdevdn=2, matype=1, mawindow=20):
        bb, _ = tech.get_bbands(stock, interval=interval, nbdevup=nbdevup, nbdevdn=nbdevdn, matype=matype,
                                time_period=mawindow)
        return {'top': bb['Real Upper Band'][-length:], 'bottom': bb['Real Lower Band'][-length:],
                'middle': bb['Real Middle Band'][-length:]}

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # mawindow: number of days to average in moving average
    def rsi(self, stock, interval='daily', length=1, mawindow=20):
        r, _ = tech.get_rsi(stock, interval=interval, time_period=mawindow)
        return r[-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # mawindow: number of days to average in moving average
    def sma(self, stock, interval='daily', length=1, mawindow=20):
        ma, _ = tech.get_sma(stock, interval=interval, time_period=mawindow)
        return ma[-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # mawindow: number of days to average in moving average
    def ema(self, stock, interval='daily', length=1, mawindow=20):
        ma, _ = tech.get_ema(stock, interval=interval, time_period=mawindow)
        return ma[-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    def percentchange(self, stock, interval='daily', length=1):
        prices = self.history(stock, interval=interval, length=length + 1)
        changes = [(current - last) / last for last, current in zip(prices[:-1], prices[1:])]
        return changes

    # Returns a list of symbols for high-volume stocks tradable on Robinhood
    def symbols(self):
        import simplejson
        with open('symbols.txt', 'r') as f:
            sym = simplejson.load(f)
        return sym


class Backtester(Algorithm):
    def __init__(self, capital=10000.0, times=['every day']):
        super(Backtester, self).__init__(times)
        # Constants
        self.logging = 'daily'
        self.startingcapital = capital
        self.cash = capital
        self.times = self.timestorun(times)
        # Variables that change automatically
        self.datetime = None
        self.daysago = None
        self.minutesago = None
        self.storeddata = {}
        # Variables that the user can change
        self.benchmark = None

    def timestorun(self, times):
        runtimes = set()
        for time in times:
            if time == 'every minute':
                for t in xrange(391):
                    runtimes.add(t)
            elif time == 'every hour':
                for t in xrange(0, 391, 60):
                    runtimes.add(t)
            elif time == 'every day':
                runtimes.add(0)
            elif type(time) is tuple or type(time) is datetime.time:
                if type(time) is datetime.time:
                    time = (time.hour, time.minute)
                runtimes.add((time[0] - 9) * 60 + (time[1] - 30))
        return runtimes

    # Gets called immediately after run() when backtesting. Can be used to debug
    # or to graph progress of the algorithm or technical indicators
    def backtestrun(self):
        pass

    # Starts the backtest (calls startbacktest in a new thread)
    # Times can be in the form of datetime objects or tuples (day,month,year)
    def start(self, startdate=datetime.datetime.today().date() - datetime.timedelta(days=10),
              enddate=datetime.datetime.today().date(), sleeptime=0):
        backtestthread = threading.Thread(target=self.startbacktest, args=(startdate, enddate, sleeptime))
        backtestthread.start()

    def startbacktest(self, startdate, enddate, sleeptime):
        if type(startdate) == tuple:
            startdate = datetime.date(startdate[2], startdate[1], startdate[0])
        if type(enddate) == tuple:
            enddate = datetime.date(enddate[2], enddate[1], enddate[0])
        if (datetime.datetime.today().date() - startdate) < datetime.timedelta(days=10):
            self.logging = '1min'
        days = list(tradingdays.NYSE_tradingdays(a=startdate, b=enddate))
        self.daysago = len(days) + len(
            list(tradingdays.NYSE_tradingdays(a=enddate, b=datetime.datetime.today().date())))
        self.datetime = startdate
        self.update()
        for day in days:
            self.daysago -= 1
            if self.logging == '1min':
                for minute in range(391):
                    self.minutesago = 391 * self.daysago - minute
                    self.datetime = datetime.datetime.combine(day, datetime.time(9, 30)) + datetime.timedelta(
                        minutes=minute)
                    if minute in self.times:
                        time.sleep(sleeptime)
                        self.update()
                        self.run()
                        self.backtestrun()
            elif self.logging == 'daily':
                self.datetime = datetime.datetime.combine(day, datetime.time(9, 30))
                self.minutesago = 391 * self.daysago
                time.sleep(sleeptime)
                self.update()
                self.run()
                self.backtestrun()

    def update(self):
        stockvalue = 0
        for stock, amount in self.stocks.items():
            if self.logging == '1min':
                stockvalue += self.history(stock, interval='1min')[0].item() * amount
            elif self.logging == 'daily':
                stockvalue += self.history(stock, interval='daily')[0].item() * amount
        self.value = self.cash + stockvalue
        self.value = round(self.value, 2)
        self.chartday.append(self.value)
        self.chartdaytimes.append(self.datetime)

    def timetoticks(self, interval='1min'):
        if interval == '1min':
            return self.minutesago
        elif interval == '5min':
            return self.minutesago / 5
        elif interval == '15min':
            return self.minutesago / 15
        elif interval == '30min':
            return self.minutesago / 30
        elif interval == '60min':
            return self.minutesago / 60
        elif interval == 'daily':
            return self.daysago
        elif interval == 'weekly':
            return self.daysago / 5

    #TODO: Short backtests can use minute data, should not always use daily
    def quote(self, stock):
        return self.history(stock, interval="daily")[0]

    def history(self, stock, interval='1min', length=1, datatype='close'):
        name = 'history,' + stock + ',' + interval
        if name in self.storeddata:
            hist = self.storeddata[name]
        else:
            if interval == 'daily':
                hist, _ = data.get_daily_adjusted(symbol=stock, outputsize='full')
            elif interval == 'weekly':
                hist, _ = data.get_weekly(symbol=stock)
            else:
                hist, _ = data.get_intraday(symbol=stock, interval=interval, outputsize='full')
            self.storeddata[name] = hist
        return hist[datatype][
               len(hist[datatype]) - self.timetoticks(interval) - length:len(hist[datatype]) - self.timetoticks(
                   interval)]

    def buy(self, stock, amount, verbose=False):
        cost = self.history(stock, interval=self.logging)[0].item()
        if cost * amount > self.cash:
            print("Warning: not enough cash ($" + str(self.cash) + ") in algorithm to buy " + str(
                amount) + " shares of " + stock)
        if stock in self.stocks:
            self.stocks[stock] += amount
        else:
            self.stocks[stock] = amount
        self.cash -= cost * amount
        if verbose:
            print("Buying " + str(amount) + " shares of " + stock)

    def sell(self, stock, amount, verbose=False):
        if (stock in self.stocks) and (amount <= self.stocks[stock]):
            self.stocks[stock] -= amount
            self.cash += self.history(stock, interval=self.logging)[0].item() * amount
            if verbose:
                print("Selling " + str(amount) + " shares of " + stock)
        else:
            print("Warning: attempting to sell more shares (" + str(amount) + ") than are owned (" + str(
                self.stocks[stock] if stock in self.stocks else 0) + ") of " + stock)

    def orderpercent(self, stock, percent, verbose=False):
        stockprice = self.history(stock, interval=self.logging)[0].item()
        currentpercent = 0.0
        if stock in self.stocks:
            currentpercent = self.stocks[stock] * stockprice / self.value
        percentdiff = percent - currentpercent
        if percentdiff < 0:
            amount = round(-percentdiff * self.value / stockprice)
            return self.sell(stock, amount, verbose)
        else:
            amount = math.floor(percentdiff * self.value / stockprice)
            return self.buy(stock, amount, verbose)

    def macd(self, stock, interval='daily', length=1, fastmawindow=12, slowmawindow=26, signalmawindow=9, fastmatype=1,
             slowmatype=1, signalmatype=1):
        name = 'macd,' + stock + ',' + interval + ',' + str(fastmawindow) + ',' + str(slowmawindow) + ',' + str(
            signalmawindow) + ',' + str(fastmatype) + ',' + str(slowmatype) + ',' + str(signalmatype)
        if name in self.storeddata:
            md = self.storeddata[name]
        else:
            md, _ = tech.get_macdext(stock, interval=interval, \
                                     fastperiod=fastmawindow, slowperiod=slowmawindow, signalperiod=signalmawindow, \
                                     fastmatype=fastmatype, slowmatype=slowmatype, signalmatype=signalmatype)
            self.storeddata[name] = md
        return {'macd': md['MACD'][
                        len(md['MACD']) - self.timetoticks(interval) - length:len(md['MACD']) - self.timetoticks(
                            interval)], 'signal': md['MACD_Signal'][
                                                  len(md['MACD']) - self.timetoticks(interval) - length:len(
                                                      md['MACD']) - self.timetoticks(interval)],
                'macd hist': md['MACD_Hist'][
                             len(md['MACD']) - self.timetoticks(interval) - length:len(md['MACD']) - self.timetoticks(
                                 interval)]}

    def bollinger(self, stock, interval='daily', length=1, nbdevup=2, nbdevdn=2, matype=1, mawindow=20):
        name = 'bollinger,' + stock + ',' + interval + ',' + str(nbdevup) + ',' + str(nbdevdn) + ',' + str(
            matype) + ',' + str(mawindow)
        if name in self.storeddata:
            bb = self.storeddata[name]
        else:
            bb, _ = tech.get_bbands(stock, interval=interval, nbdevup=nbdevup, nbdevdn=nbdevdn, matype=matype,
                                    time_period=mawindow)
            self.storeddata[name] = bb
        return {'top': bb['Real Upper Band'][len(bb['Real Upper Band']) - self.timetoticks(interval) - length:len(
            bb['Real Upper Band']) - self.timetoticks(interval)], 'bottom': bb['Real Lower Band'][len(
            bb['Real Lower Band']) - self.timetoticks(interval) - length:len(bb['Real Lower Band']) - self.timetoticks(
            interval)], 'middle': bb['Real Middle Band'][
                                  len(bb['Real Middle Band']) - self.timetoticks(interval) - length:len(
                                      bb['Real Middle Band']) - self.timetoticks(interval)]}

    def rsi(self, stock, interval='daily', length=1, mawindow=20):
        name = 'rsi,' + stock + ',' + interval + ',' + str(mawindow)
        if name in self.storeddata:
            r = self.storeddata[name]
        else:
            r, _ = tech.get_rsi(stock, interval=interval, time_period=mawindow)
            self.storeddata[name] = r
        return r[len(r) - self.timetoticks(interval) - length:len(r) - self.timetoticks(interval)]

    def sma(self, stock, interval='daily', length=1, mawindow=20):
        name = 'sma,' + stock + ',' + interval + ',' + str(mawindow)
        if name in self.storeddata:
            ma = self.storeddata[name]
        else:
            ma, _ = tech.get_sma(stock, interval=interval, time_period=mawindow)
            self.storeddata[name] = ma
        return ma[len(ma) - self.timetoticks(interval) - length:len(ma) - self.timetoticks(interval)]

    def ema(self, stock, interval='daily', length=1, mawindow=20):
        name = 'ema,' + stock + ',' + interval + ',' + str(mawindow)
        if name in self.storeddata:
            ma = self.storeddata[name]
        else:
            ma, _ = tech.get_ema(stock, interval=interval, time_period=mawindow)
            self.storeddata[name] = ma
        return ma[len(ma) - self.timetoticks(interval) - length:len(ma) - self.timetoticks(interval)]

    def percentchange(self, stock, interval='daily', length=1):
        name = 'percentchange,' + stock + ',' + interval
        if name in self.storeddata:
            changes = self.storeddata[name]
        else:
            calclength = length + self.timetoticks(interval)
            prices = self.history(stock, interval=interval, length=calclength + 1)
            changes = [(current - last) / last for last, current in zip(prices[:-1], prices[1:])]
            self.storeddata[name] = changes
        return changes[len(changes) - self.timetoticks(interval) - length:len(changes) - self.timetoticks(interval)]


def backtester(algo, startingcapital=None):
    if startingcapital is None:
        if algo.value != 0:
            startingcapital = algo.value
        else:
            startingcapital = 10000
    times = algo.times
    BacktestAlgorithm = type('BacktestAlgorithm', (Backtester,), dict((algo.__class__).__dict__))
    algoback = BacktestAlgorithm(times=times)
    algoback.benchmark = algo.benchmark
    return algoback

# High Priority
# TODO: don't assume order went through. Get actual buy/sell price
# TODO: TEST buy/sell in real time
# TODO: TEST other technical indicators in backtesting

# Medium priority
# TODO: add liquidate algo/manager feature that sells all stocks
# TODO: Add extra plots (technical indicator, etc) to GUI
# TODO: add entire portfolio GUI section to the manager GUI
# TODO: add searching and manually buying to manager GUI
# TODO: add more buttons/options to manager GUI (add simple algo, )
# TODO: add more buttons/options to algo GUI (paper trade, backtest, )

# Low Priority
# TODO: load and save data when closed/opened
# TODO: Prevent day trades, Combine concurrent orders for same stock
