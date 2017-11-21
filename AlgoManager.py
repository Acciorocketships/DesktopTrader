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

broker = 'robinhood'

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
    print("Inadequate permissions to read credentials file.")
    exit(-1)

creds = [x.strip() for x in creds]
robinhood = Robinhood()
robinhood.login(username=creds[0], password=creds[1])

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
        self.portfolio = robinhood.portfolios()
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
        self.portfolio = robinhood.portfolios()
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
    def updatemin(self):
        self.chartminute.append(self.value)
        self.chartminutetimes.append(datetime.datetime.now())
        positions = robinhood.positions()['results']
        for position in positions:
            name = str(requests.get(position['instrument']).json()['symbol'])
            amount = float(position['quantity'])
            amountdiff = amount - (self.stocks[name] if name in self.stocks else 0)
            self.stocks[name] = amount
            if amountdiff != 0:
                for algo in self.algo_alloc.keys():
                    if (name in algo.openorders) and (algo.openorders[name] == amountdiff):
                        shareprice = abs((self.cash - self.lastcash) / amountdiff)
                        # TODO: ^^ update shareprice to position[ last traded price ]
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
        self.cache = {}
        self.datetime = None
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
        self.datetime = datetime.datetime.now()

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
    # amount: number of shares of that stock to order (+ for buy, - for sell)
    # verbose: prints out order
    # noverify: assume that the order went through at the current price,
    #			as opposed to waiting for the manager to verify it (default off)
    def order(self, stock, amount, verbose=False, noverify=False):
        #Guard condition for sell
        if amount < 0 and (stock in self.stocks) and (-amount > self.stocks[stock]):
            print("Warning: attempting to sell more shares (" + str(amount) + ") than are owned (" + str(
                self.stocks[stock] if stock in self.stocks else 0) + ") of " + stock)
            return None

        cost = self.quote(stock)
        #Guard condition for buy
        if cost * amount > self.cash:
            print("Warning: not enough cash ($" + str(self.cash) + ") in algorithm to buy " + str(
                amount) + " shares of " + stock)
            return None

        if amount == 0:
            return None

        #Stage the order
        if noverify:
            if stock in self.stocks:
                self.stocks[stock] += amount
            else:
                self.stocks[stock] = amount
            self.cash -= cost * amount
        else:
            self.openorders[stock] = self.openorders.get(stock, 0) + amount
        if verbose:
            print("Stock buy/sell" + str(amount) + " shares of " + stock)
        if self.running:
            if amount > 0:
                return buy(stock, amount)
            elif amount < 0:
                return sell(stock, amount)

    # Buy or sell to reach a target percent of the algorithm's total allocation
    def orderpercent(self, stock, percent, verbose=False, noverify=False):
        stockprice = self.quote(stock)
        currentpercent = 0.0
        if stock in self.stocks:
            currentpercent = self.stocks[stock] * stockprice / self.value
        percentdiff = percent - currentpercent
        if percentdiff < 0:
            amount = round(-percentdiff * self.value / stockprice)
            if verbose:
                print("percentdiff: (" + stock + ", " + str(amount) + ")")
            return self.order(stock, -amount, verbose, noverify)
        else:
            amount = math.floor(percentdiff * self.value / stockprice)
            if verbose:
                print("percentdiff: (" + stock + ", " + str(amount) + ")")
            return self.order(stock, amount, verbose, noverify)

    # Returns the list of datetime objects associated with the entries of a pandas dataframe
    def dateidxs(self, arr):
        return [self.extractdate(item[0]) for item in arr.iterrows()]

    def extractdate(self,string):
        try:
            return datetime.datetime.strptime(string, "%Y-%m-%d")
        except:
            return datetime.datetime.strptime(string, "%Y-%m-%d %H:%M:%S")

    # Returns the index of the nearest element in dateidxs that occured before (or at the same time) as time.
    # If lastchecked==None: Searches backward from the most recent entries
    # If lastchecked>=0: Searches forward starting at lastchecked
    # If lastchecked<0: Searches backward starting at -lastchecked
    def nearestidx(self, time, dateidxs, lastchecked=None):
        if lastchecked is None:
            for i in range(len(dateidxs)):
                index = len(dateidxs) - i - 1
                if dateidxs[index] <= time:
                    return index
        elif lastchecked >= 0:
            for i in range(len(dateidxs)):
                index = (lastchecked + i) % len(dateidxs)
                if dateidxs[index] > time:
                    return index-1
            return len(dateidxs)-1
        else:
            for i in range(len(dateidxs)):
                index = (len(dateidxs) - lastchecked - i) % len(dateidxs)
                if dateidxs[index] <= time:
                    return index

    # Returns the difference of the indexes of startdate and currentdateidx in dateidxs
    # startdate: datetime in the past
    # currentdateidx: idx of current date in dateidxs (datetime also accepted) (If None given, it will default to the last value)
    # dateidxs: list of datetimes (original pandas dataframe also accepted)
    def datetolength(self, startdate, dateidxs, currentdateidx=None):
        if isinstance(dateidxs,pd.DataFrame):
            dateidxs = self.dateidxs(dateidxs)
        if isinstance(startdate,datetime.datetime):
            currentdateidx = self.nearestidx(currentdateidx, dateidxs)
        if currentdateidx is None:
            currentdateidx = len(dateidxs)-1
        return currentdateidx - self.nearestidx(startdate, dateidxs, lastchecked=-currentdateidx)

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
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,hist)
        if length is None:
            length = len(hist)
        return hist[datatype][-length:]

    # Uses robinhood to get the current price of a stock
    # stock: stock symbol (string)
    def quote(self, stock):
        return float(robinhood.quote_data(stock)['last_trade_price'])

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
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,md)
        if length is None:
            length = len(md)
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
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,bb)
        if length is None:
            length = len(bb)
        return {'top': bb['Real Upper Band'][-length:], 'bottom': bb['Real Lower Band'][-length:],
                'middle': bb['Real Middle Band'][-length:]}

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # mawindow: number of days to average in moving average
    def rsi(self, stock, interval='daily', length=1, mawindow=20):
        r, _ = tech.get_rsi(stock, interval=interval, time_period=mawindow)
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,r)
        if length is None:
            length = len(r)
        return r[-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # mawindow: number of days to average in moving average
    def sma(self, stock, interval='daily', length=1, mawindow=20):
        ma, _ = tech.get_sma(stock, interval=interval, time_period=mawindow)
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,ma)
        if length is None:
            length = len(ma)
        return ma[-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # mawindow: number of days to average in moving average
    def ema(self, stock, interval='daily', length=1, mawindow=20):
        ma, _ = tech.get_ema(stock, interval=interval, time_period=mawindow)
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,ma)
        if length is None:
            length = len(ma)
        return ma[-length:]

    # ADD DOCUMENTATION
    def stoch(self, stock, interval='daily', length=1, fastkperiod=12, 
                slowkperiod=26, slowdperiod=26, slowkmatype=0, slowdmatype=0):
        s = tech.get_stoch(stock, interval=interval, fastkperiod=fastkperiod,
                slowkperiod=slowkperiod, slowdperiod=slowdperiod, slowkmatype=slowkmatype, slowdmatype=slowdmatype)
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,s)
        if length is None:
            length = len(s)
        return s[-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    def percentchange(self, stock, interval='daily', length=1):
        prices = self.history(stock, interval=interval, length=None)
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,ma)
        elif length is None:
            length = len(ma)
        else:
            length += 1
        changes = [(current - last) / last for last, current in zip(prices[-length:-1], prices[-length+1:])]
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
        self.daysago = None
        self.minutesago = None
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
              enddate=datetime.datetime.today().date()):
        backtestthread = threading.Thread(target=self.startbacktest, args=(startdate, enddate))
        backtestthread.start()

    def startbacktest(self, startdate, enddate):
        if type(startdate) == tuple:
            startdate = datetime.date(startdate[2], startdate[1], startdate[0])
        if type(enddate) == tuple:
            enddate = datetime.date(enddate[2], enddate[1], enddate[0])
        if (datetime.datetime.today().date() - startdate) < datetime.timedelta(days=10):
            self.logging = '1min'
        days = list(tradingdays.NYSE_tradingdays(a=startdate, b=enddate))
        self.daysago = len(days) + len(list(tradingdays.NYSE_tradingdays(a=enddate, b=datetime.datetime.today().date())))
        self.datetime = startdate
        self.update()
        for day in days:
            self.daysago -= 1
            if self.logging == '1min':
                for minute in range(391):
                    self.minutesago = 391 * self.daysago - minute
                    self.datetime = datetime.datetime.combine(day, datetime.time(9, 30)) + datetime.timedelta(minutes=minute)
                    if minute in self.times:
                        self.update()
                        self.run()
                        self.backtestrun()
            elif self.logging == 'daily':
                self.datetime = datetime.datetime.combine(day, datetime.time(9, 30))
                self.minutesago = 391 * self.daysago
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

    def quote(self, stock):
        return self.history(stock, interval=self.logging)[0].item()

    def history(self, stock, interval='1min', length=1, datatype='close'):
        key = ('history', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            hist, exp, dateidxs, lastidx = cache 
        if (cache is None) or (datetime.datetime.now() > exp): 
            if interval == 'daily':
                hist, _ = data.get_daily_adjusted(symbol=stock, outputsize='full')
            elif interval == 'weekly':
                hist, _ = data.get_weekly(symbol=stock)
            else:
                hist, _ = data.get_intraday(symbol=stock, interval=interval, outputsize='full')
            dateidxs = self.dateidxs(hist)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [hist, datetime.datetime.now() + datetime.timedelta(minutes = 1), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return hist[datatype][idx-length: idx]

    def order(self, stock, amount, verbose=False):
        # Guard condition for sell
        if amount < 0 and (stock in self.stocks) and (-amount > self.stocks[stock]):
            print("Warning: attempting to sell more shares (" + str(amount) + ") than are owned (" + str(
                self.stocks[stock] if stock in self.stocks else 0) + ") of " + stock)
            return None
        cost = self.quote(stock)
        # Guard condition for buy
        if cost * amount > self.cash:
            print("Warning: not enough cash ($" + str(self.cash) + ") in algorithm to buy " + str(
                amount) + " shares of " + stock)
            return None
        if amount == 0:
            return None
        # Stage the order
        self.stocks[stock] = self.stocks.get(stock, 0) + amount
        self.cash -= cost * amount
        if verbose:
            print("Stock buy/sell" + str(amount) + " shares of " + stock)

    def orderpercent(self, stock, percent, verbose=False):
        stockprice = self.history(stock, interval=self.logging)[0].item()
        currentpercent = 0.0
        if stock in self.stocks:
            currentpercent = self.stocks[stock] * stockprice / self.value
        percentdiff = percent - currentpercent
        if percentdiff < 0:
            amount = round(-percentdiff * self.value / stockprice)
            if verbose:
                print("percentdiff: (" + stock + ", " + str(amount) + ")")
            return self.order(stock, -amount, verbose)
        else:
            amount = math.floor(percentdiff * self.value / stockprice)
            if verbose:
                print("percentdiff: (" + stock + ", " + str(amount) + ")")
            return self.order(stock, amount, verbose)

    def macd(self, stock, interval='daily', length=1, fastmawindow=12, slowmawindow=26, signalmawindow=9, fastmatype=1,
             slowmatype=1, signalmatype=1):
        key = ('macd', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            md, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp): 
            md, _ = tech.get_macdext(stock, interval=interval, \
                        fastperiod=fastmawindow, slowperiod=slowmawindow, signalperiod=signalmawindow, \
                        fastmatype=fastmatype, slowmatype=slowmatype, signalmatype=signalmatype)
            dateidxs = self.dateidxs(md)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [md, datetime.datetime.now() + datetime.timedelta(minutes = 1), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return {'macd': md['MACD'][idx-length : idx],
                'signal': md['MACD_Signal'][idx-length : idx],
                'macd hist': md['MACD_Hist'][idx-length : idx]}

    def bollinger(self, stock, interval='daily', length=1, nbdevup=2, nbdevdn=2, matype=1, mawindow=20):
        key = ('bollinger', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            bb, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp): 
            bb, _ = tech.get_bbands(stock, interval=interval, nbdevup=nbdevup, nbdevdn=nbdevdn, matype=matype,
                                    time_period=mawindow)
            dateidxs = self.dateidxs(bb)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [bb, datetime.datetime.now() + datetime.timedelta(minutes = 1), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return {'top': bb['Real Upper Band'][idx-length : idx],
                'bottom': bb['Real Lower Band'][idx-length : idx],
                'middle': bb['Real Middle Band'][idx-length : idx]}

    def rsi(self, stock, interval='daily', length=1, mawindow=20):
        key = ('rsi', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            r, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp): 
            r, _ = tech.get_rsi(stock, interval=interval, time_period=mawindow)
            dateidxs = self.dateidxs(r)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [r, datetime.datetime.now() + datetime.timedelta(minutes = 1), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return r[idx-length : idx]

    def sma(self, stock, interval='daily', length=1, mawindow=20):
        key = ('sma', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            ma, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp): 
            ma, _ = tech.get_sma(stock, interval=interval, time_period=mawindow)
            dateidxs = self.dateidxs(ma)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [ma, datetime.datetime.now() + datetime.timedelta(minutes = 1), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return ma[idx-length : idx]

    def ema(self, stock, interval='daily', length=1, mawindow=20):
        key = ('ema', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            ma, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp):
            ma, _ = tech.get_ema(stock, interval=interval, time_period=mawindow)
            dateidxs = self.dateidxs(ma)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [ma, datetime.datetime.now() + datetime.timedelta(minutes = 1), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return ma[idx-length : idx]

    def stoch(self, stock, interval='daily', length=1, fastkperiod=12, 
                slowkperiod=26, slowdperiod=26, slowkmatype=0, slowdmatype=0):
        key = ('stoch', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            s, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp):
            s, _ = tech.get_stoch(stock, interval=interval, fastkperiod=fastkperiod,
                slowkperiod=slowkperiod, slowdperiod=slowdperiod, slowkmatype=slowkmatype, slowdmatype=slowdmatype)
            dateidxs = self.dateidxs(s)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [s, datetime.datetime.now() + datetime.timedelta(minutes = 1), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return s[idx-length : idx]

    def percentchange(self, stock, interval='daily', length=1):
        prices = self.history(stock, interval=interval, length=None)
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,len(prices)-1)
        elif length is None:
            length = idx
        else:
            length += 1
        changes = [(current - last) / last for last, current in zip(prices[-length:-1], prices[-length+1:])]
        return changes


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


def buy(stock, amount):
    if broker == 'robinhood':
        stockobj = robinhood.instruments(stock)
        return robinhood.place_buy_order(stockobj, amount)

def sell(stock, amount):
    if broker == 'robinhood':
        stockobj = robinhood.instruments(stock)
        return robinhood.place_sell_order(stockobj, amount)

# High Priority
# TODO: Comment functions that don't have descriptions
# TODO: TEST that algorithm uses the correct buy/sell price.
# TODO: TEST buy/sell in real time
# TODO: TEST other technical indicators in backtesting. Check that they return lists of floats (perhaps switch to numpy)
# TODO: Add manager GUI
# TODO: fix jumping axes in backtest with benchmark

# Medium priority
# TODO: generalize to other brokers. write a wrapper function for everywhere it uses 'self.portfolio' now
# TODO: add liquidate algo/manager feature that sells all stocks
# TODO: Add extra plots (technical indicator, etc) to GUI
# TODO: add searching and manually buying to manager GUI
# TODO: add more buttons/options to manager GUI (add simple algo, )
# TODO: add more buttons/options to algo GUI (paper trade, backtest, )

# Low Priority
# TODO: load and save data when closed/opened
# TODO: Prevent day trades, Combine concurrent orders for same stock
