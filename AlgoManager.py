import datetime
import time
import threading
from Robinhood import Robinhood
from alpha_vantage.timeseries import TimeSeries
from alpha_vantage.techindicators import TechIndicators
import code
import copy
import pandas as pd
import tradingdays
from empyrical import max_drawdown, alpha_beta, annual_volatility, sharpe_ratio
import math
import requests
from pytrends.request import TrendReq
import re
import numpy as np
import AlgoGUI as app
import ManagerGUI as man
from functools import reduce

# https://github.com/RomelTorres/alpha_vantage
# https://github.com/Jamonek/Robinhood





broker = 'robinhood'

creds = []
credential_file = "creds.txt"
try:
    with open(credential_file, "r") as f:
        creds = f.readlines()
except IOError:
    creds.append(input('Robinhood Username: '))
    creds.append(input('Robinhood Password: '))
    creds.append(input('Alpha Vantage API Key: '))
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

pytrends = TrendReq(hl='en-US', tz=360)






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







class Algorithm(object):

    def __init__(self, times=['every day']):
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
        self.cache = {}
        self.stoplosses = {}
        self.stopgains = {}
        self.limitlow = {}
        self.limithigh = {}
        self.datetime = datetime.datetime.now()
        self.alpha = None
        self.beta = None
        self.volatility = None
        self.sharpe = None
        self.maxdrawdown = None
        # User initialization
        self.initialize()

    def initialize(self):
        pass

    def run(self):
        pass


    ### PRIVATE METHODS ###


    # Update function called every second
    def updatetick(self):
        stockvalue = 0
        for stock, amount in list(self.stocks.items()):
            stockvalue += self.quote(stock) * amount
        self.value = self.cash + stockvalue
        self.value = round(self.value,2)
        self.cash = round(self.cash,2)
        self.datetime = datetime.datetime.now()

    # Update function called every minute
    def updatemin(self):
        self.chartminute.append(self.value)
        self.chartminutetimes.append(datetime.datetime.now())
        for stock in (self.stopgains.keys() | self.stoplosses.keys()):
            self.checkthresholds(stock)

    # Update function called every day
    def updateday(self):
        self.chartminute = []
        self.chartminutetimes = []
        self.chartday.append(self.value)
        self.chartdaytimes.append(datetime.datetime.now())
        self.riskmetrics()

    # Checks and executes limit/stop orders
    # TODO: Custom amounts to buy/sell
    def checkthresholds(self,stock):
        price = self.quote(stock)
        alloc = self.cash / self.value
        if (stock in self.stocks) and (stock in self.stoplosses) and (price <= self.stoplosses[stock]):
            print("Stoploss for " + stock + " kicking in.")
            del self.stoplosses[stock]
            self.orderpercent(stock,0,verbose=True)
        elif (stock in self.stocks) and (stock in self.stopgains) and (price >= self.stopgains[stock]):
            print("Stopgain for " + stock + " kicking in.")
            del self.stopgains[stock]
            self.orderpercent(stock,0,verbose=True)
        elif (stock in self.limitlow) and (price <= self.limitlow[stock]):
            print("Limit order " + stock + " activated.")
            del self.limitlow[stock]
            self.orderpercent(stock,alloc,verbose=True)
        elif (stock in self.limithigh) and (price >= self.limithigh[stock]):
            print("Limit order " + stock + " activated.")
            del self.limithigh[stock]
            self.orderpercent(stock,alloc,verbose=True)

    def riskmetrics(self):
        benchmark = self.benchmark if type(self.benchmark)==str else self.benchmark[0]
        changes = [(current - last) / last for last, current in zip(self.chartday[:-1], self.chartday[1:])]
        benchmarkchanges = self.percentchange(benchmark, length=len(changes))
        changes = pd.DataFrame({'date':benchmarkchanges._index,'changes':changes})
        changes = changes.set_index('date')['changes']
        self.alpha, self.beta = alpha_beta(changes, benchmarkchanges)
        self.alpha = round(self.alpha,3)
        self.beta = round(self.beta,3)
        self.sharpe = round(sharpe_ratio(changes),3)
        self.volatility = round(annual_volatility(changes),3)
        self.maxdrawdown = round(max_drawdown(changes),3)

    # Returns the list of datetime objects associated with the entries of a pandas dataframe
    def dateidxs(self, arr):
        return [self.extractdate(item[0]) for item in arr.iterrows()]

    # Gets datetime from string. Helper for dateidxs
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
                index = (lastchecked + i - 5) % len(dateidxs)
                if dateidxs[index] > time:
                    return index-1
            return len(dateidxs)-1
        else:
            for i in range(len(dateidxs)):
                index = (len(dateidxs) - lastchecked - i) % len(dateidxs)
                if dateidxs[index] <= time:
                    return index
        raise Exception("Datetime " + str(time) + " not found in historical data.")

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


    ### PUBLIC METHODS ###


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

    # Adds stop loss or stop gain to a particular stock until it is sold (then you need to re-add it)
    # If change == 0.05, then the stock will be sold if it goes 5% over the current price
    # If change == -0.05, then the stock will be sold if it goes 5% below the current price
    def stopsell(self,stock,change):
        if change > 0:
            self.stopgains[stock] = (1+change)*self.quote(stock)
        if change < 0:
            self.stoplosses[stock] = (1+change)*self.quote(stock)

    # Adds order for a stock when it crosses above or below a % change from the current price
    # If change == 0.05, then the stock will be bought if it goes 5% over the current price
    # If change == -0.05, then the stock will be bought if it goes 5% below the current price
    def limitbuy(self,stock,change):
        if change > 0:
            self.limithigh[stock] = (1+change)*self.quote(stock)
        if change < 0:
            self.limitlow[stock] = (1+change)*self.quote(stock)

    # stock: stock symbol (string)
    # amount: number of shares of that stock to order (+ for buy, - for sell)
    # verbose: prints out order
    def order(self, stock, amount, verbose=False):
        # Guard condition for sell
        if amount < 0 and (-amount > self.stocks.get(stock,0)):
            print(("Warning: attempting to sell more shares (" + str(amount) + ") than are owned (" + str(
                self.stocks.get(stock,0)) + ") of " + stock))
            return
        cost = self.quote(stock)
        # Guard condition for buy
        if cost * amount > 0.95 * self.cash:
            print(("Warning: not enough cash ($" + str(self.cash) + ") in algorithm to buy " + str(
                amount) + " shares of " + stock))
            return
        if amount == 0:
            return
        # Place order, block until filled, update amount and cash
        currentcash = portfoliodata()["cash"]
        currentamount = positions().get(stock,0)
        newamount = currentamount
        if self.running:    
            if amount > 0:
                buy(stock, amount)
            elif amount < 0:
                sell(stock, amount)
            for i in range(100):
                newamount = positions().get(stock,0)
                if newamount != currentamount:
                    break
                else:
                    time.sleep(0.01*i)
            newcash = portfoliodata()["cash"]
            amount = newamount - currentamount
            self.cash += (newcash - currentcash)
            self.stocks[stock] = self.stocks.get(stock,0) + amount
        else:
            self.cash -= cost * amount
            self.stocks[stock] = self.stocks.get(stock,0) + amount
        if verbose:
            if amount > 0:
                print( "Buying " + str(amount) + " shares of " + stock + " at $" + str(cost))
            elif amount < 0:
                print( "Selling " + str(amount) + " shares of " + stock + " at $" + str(cost))


    # Buy or sell to reach a target percent of the algorithm's total allocation
    def orderpercent(self, stock, percent, verbose=False):
        cost = self.quote(stock)
        currentpercent = 0.0
        if stock in self.stocks:
            currentpercent = self.stocks[stock] * cost / self.value
        percentdiff = percent - currentpercent
        if percentdiff < 0:
            # Min of (# required to reach target percent) and (# of that stock owned)
            amount = min( round(-percentdiff * self.value / cost), self.stocks.get(stock,0) )
            return self.order(stock, -amount, verbose)
        else:
            # Min of (# required to reach target percent) and (# that you can buy with 95% of your available cash)
            amount = min( math.floor(percentdiff * self.value / cost), math.floor(0.95 * self.cash / cost) )
            return self.order(stock, amount, verbose)

    # Sells all held stocks
    def sellall(self, verbose=False):
        for stock in self.stocks:
            self.orderpercent(stock,0,verbose=verbose)

    # Returns a list of symbols for high-volume stocks tradable on Robinhood
    def symbols(self):
        import simplejson
        with open('symbols.txt', 'r') as f:
            sym = simplejson.load(f)
        return sym


    ### HISTORY AND INDICATORS ###


    # Uses broker to get the current price of a stock
    # stock: stock symbol (string)
    def quote(self, stock):
        return price(stock)

    # Use Alpha Vantage to get the historical price data of a stock
    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily' (default 1min)
    # length: number of data points (default is only the last)
    # datatype: 'close','open','volume' (default close)
    def history(self, stock, interval='daily', length=1, datatype='open'):
        if 'open' in datatype:
            datatype = '1. open'
        elif 'close' in datatype:
            datatype = '4. close'
        elif 'volume' in datatype:
            datatype = '6. volume'
        elif 'high' in datatype:
            datatype = '2. high'
        elif 'low' in datatype:
            datatype = '3. low'
        if length <= 100:
            size = 'compact'
        else:
            size = 'full'
        hist = None
        while hist is None:
            try:
                if interval == 'daily':
                    hist, _ = data.get_daily_adjusted(symbol=stock, outputsize=size)
                else:
                    hist, _ = data.get_intraday(symbol=stock, interval=interval, outputsize=size)
            except ValueError as err:
                print(err)
                time.sleep(5)
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,hist)
        if length is None:
            length = len(hist)
        return hist[datatype][-length:]

    # macd line: 12 day MA - 26 day MA
    # signal line: 9 period MA of the macd line
    # macd hist: macd - signal
    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # matype: 0 for SMA, 1 for EMA, 2 for WMA (Weighted), 3 for DEMA (Double Exponential), 4 for TEMA (Triple Exponential)
    # mawindow: number of days to average in moving average
    # Returns Series of the MACD Histogram (Signal - (FastMA - SlowMA))
    def macd(self, stock, interval='daily', length=1, fastmawindow=12, slowmawindow=26, signalmawindow=9, fastmatype=1,
             slowmatype=1, signalmatype=1):
        md, _ = tech.get_macdext(stock, interval=interval, \
                                 fastperiod=fastmawindow, slowperiod=slowmawindow, signalperiod=signalmawindow, \
                                 fastmatype=fastmatype, slowmatype=slowmatype, signalmatype=signalmatype, \
                                 series_type='open')
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,md)
        if length is None:
            length = len(md)
        return md['MACD_Hist'][-length:]

    # nbdevup: multiplier for standard deviations of the top band above the middle band
    # nbdevdn: multiplier for standard deviations of the bottom band below the middle band
    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # matype: 0 for SMA, 1 for EMA, 2 for WMA (Weighted), 3 for DEMA (Double Exponential), 4 for TEMA (Triple Exponential)
    # mawindow: number of days to average in moving average
    # Returns Dataframe with 'Real Upper Band', 'Real Lower Band' and 'Real Middle Band'.
    def bollinger(self, stock, interval='daily', length=1, nbdevup=2, nbdevdn=2, matype=1, mawindow=20):
        bb, _ = tech.get_bbands(stock, interval=interval, nbdevup=nbdevup, nbdevdn=nbdevdn, matype=matype,
                                time_period=mawindow, series_type='open')
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,bb)
        if length is None:
            length = len(bb)
        return bb[-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # mawindow: number of days to average in moving average
    # Returns Series with RSI values
    def rsi(self, stock, interval='daily', length=1, mawindow=20):
        r, _ = tech.get_rsi(stock, interval=interval, time_period=mawindow, series_type='open')
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,r)
        if length is None:
            length = len(r)
        return r["RSI"][-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last)
    # mawindow: number of days to average in moving average
    # Returns Series with SMA values
    def sma(self, stock, interval='daily', length=1, mawindow=20):
        ma, _ = tech.get_sma(stock, interval=interval, time_period=mawindow, series_type='open')
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,ma)
        if length is None:
            length = len(ma)
        return ma["SMA"][-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last), or starting datetime
    # mawindow: number of days to average in moving average
    # Returns Series with EMA values
    def ema(self, stock, interval='daily', length=1, mawindow=20):
        ma, _ = tech.get_ema(stock, interval=interval, time_period=mawindow, series_type='open')
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,ma)
        if length is None:
            length = len(ma)
        return ma["EMA"][-length:]

    # Returns dataframe with "SlowD" and "SlowK"
    def stoch(self, stock, interval='daily', length=1, fastkperiod=12, 
                slowkperiod=26, slowdperiod=26, slowkmatype=0, slowdmatype=0):
        s = tech.get_stoch(stock, interval=interval, fastkperiod=fastkperiod,
                slowkperiod=slowkperiod, slowdperiod=slowdperiod, slowkmatype=slowkmatype, slowdmatype=slowdmatype, \
                series_type='open')
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,s)
        if length is None:
            length = len(s)
        return s[-length:]

    # stock: stock symbol (string)
    # interval: time interval between data points '1min','5min','15min','30min','60min','daily','weekly' (default 1min)
    # length: number of data points (default is only the last), or starting datetime
    def percentchange(self, stock, interval='daily', length=1, datatype='open'):
        # Rename inputs
        if 'open' in datatype:
            datatype = '1. open'
        elif 'close' in datatype:
            datatype = '4. close'
        elif 'volume' in datatype:
            datatype = '6. volume'
        elif 'high' in datatype:
            datatype = '2. high'
        elif 'low' in datatype:
            datatype = '3. low'
        if length < 100:
            size = 'compact'
        else:
            size = 'full'
        # Get Data
        if interval == 'daily':
            prices, _ = data.get_daily_adjusted(symbol=stock, outputsize=size)
        elif interval == 'weekly':
            prices, _ = data.get_weekly(symbol=stock)
        else:
            prices, _ = data.get_intraday(symbol=stock, interval=interval, outputsize=size)
        changes = prices[datatype].pct_change()
        # Handle Length
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,prices)
        elif length is None:
            length = len(prices)
        return changes[-length:]

    # The google trends for interest over time in a given query
    # interval: 60min, daily (changes to weekly if length is too long)
    # Returns Series of numbers from 0 to 100 for relative interest over time
    # WARNING: Data is for all days (other data is just trading days)
    def google(self, query, interval='daily', length=100, financial=True):
        enddate = self.datetime
        if isinstance(length, datetime.datetime):
            startdate = length
        else:
            length += 1
        if interval == 'daily':
            startdate = enddate - datetime.timedelta(days=length)
        elif interval == '60min' or interval == 'hourly':
            startdate = enddate - datetime.timedelta(hours=length)
        if interval == 'daily':
            startdate = startdate.strftime("%Y-%m-%d")
            enddate = enddate.strftime("%Y-%m-%d")
        elif interval == '60min' or interval == 'hourly':
            startdate = startdate.strftime("%Y-%m-%dT%H")
            enddate = enddate.strftime("%Y-%m-%dT%H")
        category = 0
        if financial:
            category=1138
        pytrends.build_payload([query], cat=category, timeframe=startdate + " " + enddate, geo='US')
        return pytrends.interest_over_time()[query]






# Use self.datetime to get current time (as a datetime object)
class Backtester(Algorithm):
    def __init__(self, capital=10000.0, times=['every day'], benchmark='SPY'):
        super(Backtester, self).__init__(times)
        # Constants
        if times == ['every day']:
            self.logging = 'daily'
        else:
            self.logging = '1min'
        self.startingcapital = capital
        self.cash = capital
        self.times = self.timestorun(times)
        self.exptime = 5
        # Variables that change automatically
        self.daysago = None
        self.minutesago = None
        self.alpha = None
        self.beta = None
        self.volatility = None
        self.sharpe = None
        self.maxdrawdown = None
        # Variables that the user can change
        self.benchmark = benchmark

    def timestorun(self, times):
        runtimes = set()
        for time in times:
            if time == 'every minute':
                for t in range(391):
                    runtimes.add(t)
            elif time == 'every hour':
                for t in range(0, 391, 60):
                    runtimes.add(t)
            elif time == 'every day':
                runtimes.add(0)
            elif type(time) is tuple or type(time) is datetime.time:
                if type(time) is datetime.time:
                    time = (time.hour, time.minute)
                runtimes.add((time[0] - 9) * 60 + (time[1] - 30))
        return runtimes

    # Starts the backtest (calls startbacktest in a new thread)
    # Times can be in the form of datetime objects or tuples (day,month,year)
    def start(self, startdate=datetime.datetime.today().date() - datetime.timedelta(days=14),
              enddate=datetime.datetime.today().date()):
        backtestthread = threading.Thread(target=self.startbacktest, args=(startdate, enddate))
        backtestthread.start()

    # Starts the backtest
    def startbacktest(self, startdate, enddate):
        if type(startdate) == tuple:
            startdate = datetime.date(startdate[2], startdate[1], startdate[0])
        if type(enddate) == tuple:
            enddate = datetime.date(enddate[2], enddate[1], enddate[0])
        if (datetime.datetime.today().date() - startdate) < datetime.timedelta(days=15):
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
                    if self.datetime >= datetime.datetime.now():
                        break
                    self.updatemin()
                    if minute in self.times:
                        self.update()
                        self.run()
            elif self.logging == 'daily':
                self.datetime = datetime.datetime.combine(day, datetime.time(9, 30))
                self.minutesago = 391 * self.daysago
                if self.datetime >= datetime.datetime.now():
                    break
                self.updatemin()
                self.update()
                self.run()
        self.riskmetrics()

    def updatemin(self):
        for stock in (self.stopgains.keys() | self.stoplosses.keys()):
            self.checkthresholds(stock)

    def update(self):
        stockvalue = 0
        for stock, amount in list(self.stocks.items()):
            if amount == 0:
                del self.stocks[stock]
                continue
            if self.logging == '1min':
                stockvalue += self.history(stock, interval='1min')[0].item() * amount
            elif self.logging == 'daily':
                stockvalue += self.history(stock, interval='daily')[0].item() * amount
        self.value = self.cash + stockvalue
        self.value = round(self.value, 2)
        self.chartday.append(self.value)
        self.chartdaytimes.append(self.datetime)

    def checkthresholds(self,stock):
        if self.logging == '1min':
            price = self.quote(stock)
            alloc = self.cash / self.value
            if (stock in self.stocks) and (stock in self.stoplosses) and (price <= self.stoplosses[stock]):
                print("Stoploss for " + stock + " kicking in.")
                del self.stoplosses[stock]
                self.orderpercent(stock,0,verbose=True)
            elif (stock in self.stocks) and (stock in self.stopgains) and (price >= self.stopgains[stock]):
                print("Stopgain for " + stock + " kicking in.")
                del self.stopgains[stock]
                self.orderpercent(stock,0,verbose=True)
            elif (stock in self.limitlow) and (price <= self.limitlow[stock]):
                print("Limit order " + stock + " activated.")
                del self.limitlow[stock]
                self.orderpercent(stock,alloc,verbose=True)
            elif (stock in self.limithigh) and (price >= self.limithigh[stock]):
                print("Limit order " + stock + " activated.")
                del self.limithigh[stock]
                self.orderpercent(stock,alloc,verbose=True)
        else:
            if (stock in self.stocks) and (stock in self.stoplosses) and (self.history(stock,datatype='3. low')[0] <= self.stoplosses[stock]):
                amount = self.stocks[stock]
                self.stocks[stock] = 0
                self.cash += self.stoplosses[stock] * amount
                print("Stoploss for " + stock + " kicking in.")
                print("Selling " + str(-amount) + " shares of " + stock + " at $" + str(round(self.stoplosses[stock],2)))
                del self.stoplosses[stock]
            elif (stock in self.stocks) and (stock in self.stopgains) and (self.history(stock,datatype='2. high')[0] >= self.stopgains[stock]):
                amount = self.stocks[stock]
                self.stocks[stock] = 0
                self.cash += self.stopgains[stock] * amount
                print("Stopgain for " + stock + " kicking in.")
                print("Selling " + str(-amount) + " shares of " + stock + " at $" + str(round(self.stopgains[stock],2)))
                del self.stoplosses[stock]
            elif (stock in self.limitlow) and (self.history(stock,datatype='3. low')[0] <= self.limitlow[stock]):
                self.stocks[stock] = math.floor(self.cash / self.limitlow[stock])
                self.cash -= self.stocks[stock] * self.limitlow[stock]
                print("Limit order " + stock + " activated.")
                print("Buying " + str(self.stocks[stock]) + " shares of " + stock + " at $" + str(round(self.limitlow[stock],2)))
                del self.limitlow[stock]
            elif (stock in self.limithigh) and (self.history(stock,datatype='2. high')[0] >= self.limithigh[stock]):
                self.stocks[stock] = math.floor(self.cash / self.limithigh[stock])
                self.cash -= self.stocks[stock] * self.limithigh[stock]
                print("Limit order " + stock + " activated.")
                print("Buying " + str(self.stocks[stock]) + " shares of " + stock + " at $" + str(round(self.limithigh[stock],2)))
                del self.limithigh[stock]
            self.cash = round(self.cash,2)

    def quote(self, stock):
        return self.history(stock, interval=self.logging, datatype='open')[0].item()

    def history(self, stock, interval='daily', length=1, datatype='open'):
        if 'open' in datatype:
            datatype = '1. open'
        elif 'close' in datatype:
            datatype = '4. close'
        elif 'volume' in datatype:
            datatype = '6. volume'
        elif 'high' in datatype:
            datatype = '2. high'
        elif 'low' in datatype:
            datatype = '3. low'
        key = ('history', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            hist, exp, dateidxs, lastidx = cache 
        if (cache is None) or (datetime.datetime.now() > exp):
            hist = None
            while hist is None:
                try:
                    if interval == 'daily':
                        hist, _ = data.get_daily_adjusted(symbol=stock, outputsize='full')
                    else:
                        hist, _ = data.get_intraday(symbol=stock, interval=interval, outputsize='full')
                except ValueError as err:
                    print(err)
                    time.sleep(5)
            dateidxs = self.dateidxs(hist)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [hist, datetime.datetime.now() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return hist[datatype][idx-length+1 : idx+1]
        

    def order(self, stock, amount, verbose=False):
        # Guard condition for sell
        if amount < 0 and (stock in self.stocks) and (-amount > self.stocks[stock]):
            print(("Warning: attempting to sell more shares (" + str(amount) + ") than are owned (" + str(
                self.stocks[stock] if stock in self.stocks else 0) + ") of " + stock))
            return None
        cost = self.quote(stock)
        # Guard condition for buy
        if cost * amount > self.cash:
            print(("Warning: not enough cash ($" + str(self.cash) + ") in algorithm to buy " + str(
                amount) + " shares of " + stock))
            return None
        if amount == 0:
            return None
        # Stage the order
        self.stocks[stock] = self.stocks.get(stock, 0) + amount
        self.cash -= cost * amount
        self.cash = round(self.cash,2)
        if verbose:
            if amount >= 0:
                print( "Buying " + str(amount) + " shares of " + stock + " at $" + str(cost))
            else:
                print( "Selling " + str(amount) + " shares of " + stock + " at $" + str(cost))

    def orderpercent(self, stock, percent, verbose=False):
        stockprice = self.quote(stock)
        currentpercent = 0.0
        if stock in self.stocks:
            currentpercent = self.stocks[stock] * stockprice / self.value
        percentdiff = percent - currentpercent
        if percentdiff < 0:
            amount = round(-percentdiff * self.value / stockprice)
            return self.order(stock, -amount, verbose)
        else:
            amount = math.floor(percentdiff * self.value / stockprice)
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
                        fastmatype=fastmatype, slowmatype=slowmatype, signalmatype=signalmatype, \
                        series_type='open')
            dateidxs = self.dateidxs(md)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [md, datetime.datetime.now() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return md['MACD_Hist'][idx-length+1 : idx+1]

    def bollinger(self, stock, interval='daily', length=1, nbdevup=2, nbdevdn=2, matype=1, mawindow=20):
        key = ('bollinger', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            bb, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp): 
            bb, _ = tech.get_bbands(stock, interval=interval, nbdevup=nbdevup, nbdevdn=nbdevdn, matype=matype,
                                    time_period=mawindow, series_type='open')
            dateidxs = self.dateidxs(bb)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [bb, datetime.datetime.now() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return bb[idx-length+1 : idx+1]

    def rsi(self, stock, interval='daily', length=1, mawindow=20):
        key = ('rsi', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            r, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp): 
            r, _ = tech.get_rsi(stock, interval=interval, time_period=mawindow, series_type='open')
            dateidxs = self.dateidxs(r)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [r, datetime.datetime.now() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return r["RSI"][idx-length+1 : idx+1]

    def sma(self, stock, interval='daily', length=1, mawindow=20):
        key = ('sma', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            ma, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp): 
            ma, _ = tech.get_sma(stock, interval=interval, time_period=mawindow, series_type='open')
            dateidxs = self.dateidxs(ma)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [ma, datetime.datetime.now() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return ma['SMA'][idx-length+1 : idx+1]

    def ema(self, stock, interval='daily', length=1, mawindow=20):
        key = ('ema', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            ma, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp):
            ma, _ = tech.get_ema(stock, interval=interval, time_period=mawindow, series_type='open')
            dateidxs = self.dateidxs(ma)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [ma, datetime.datetime.now() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return ma['EMA'][idx-length+1 : idx+1]

    def stoch(self, stock, interval='daily', length=1, fastkperiod=12, 
                slowkperiod=26, slowdperiod=26, slowkmatype=0, slowdmatype=0):
        key = ('stoch', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            s, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp):
            s, _ = tech.get_stoch(stock, interval=interval, fastkperiod=fastkperiod,
                slowkperiod=slowkperiod, slowdperiod=slowdperiod, slowkmatype=slowkmatype, slowdmatype=slowdmatype, \
                series_type='open')
            dateidxs = self.dateidxs(s)
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [s, datetime.datetime.now() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return s[idx-length+1 : idx+1]

    def percentchange(self, stock, interval='daily', length=1, datatype='open'):
        if 'open' in datatype:
            datatype = '1. open'
        elif 'close' in datatype:
            datatype = '4. close'
        elif 'volume' in datatype:
            datatype = '6. volume'
        elif 'high' in datatype:
            datatype = '2. high'
        elif 'low' in datatype:
            datatype = '3. low'
        key = ('percchng', tuple(locals().values()))
        cache = self.cache.get(key)
        exp = None
        if cache is not None: 
            changes, exp, dateidxs, lastidx = cache
        if (cache is None) or (datetime.datetime.now() > exp):
            if interval == 'daily':
                prices, _ = data.get_daily_adjusted(symbol=stock, outputsize='full')
            elif interval == 'weekly':
                prices, _ = data.get_weekly(symbol=stock)
            else:
                prices, _ = data.get_intraday(symbol=stock, interval=interval, outputsize='full')
            changes = prices[datatype].pct_change()
            dateidxs = self.dateidxs(prices[1:])
            lastidx = self.nearestidx(self.datetime, dateidxs)
            self.cache[key] = [changes, datetime.datetime.now() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
        idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
        self.cache[key][3] = idx
        if isinstance(length,datetime.datetime):
            length = self.datetolength(length,dateidxs,idx)
        if length is None:
            length = idx
        return changes[idx-length+1 : idx+1]




### Wrappers for Broker-Related Functions ###




def backtester(algo, capital=None, benchmark=None):
    # Convert
    times = algo.times
    BacktestAlgorithm = type('BacktestAlgorithm', (Backtester,), dict((algo.__class__).__dict__))
    algoback = BacktestAlgorithm(times=times)
    # Set Capital
    if capital is None:
        if algoback.value == 0:
            algoback.value = 10000
    else:
        algoback.value = capital
    # Set Benchmark
    if benchmark is not None:
        algoback.benchmark = benchmark
    elif 'benchmark' in algo.__dict__:
        algoback.benchmark = algo.benchmark
    else:
        algoback.benchmark = "SPY"
    return algoback

# Input: stock symbol as a string, number of shares as an int
def buy(stock, amount):
    if broker == 'robinhood':
        stockobj = robinhood.instruments(stock)[0]
        for tries in range(5):
            try:
                response = robinhood.place_buy_order(stockobj, amount)
                return response
            except Exception as e:
                print("Buy Order Failed", e)
                time.sleep(tries)

# Input: stock symbol as a string, number of shares as an int
def sell(stock, amount):
    if broker == 'robinhood':
        stockobj = robinhood.instruments(stock)[0]
        try:
            response = robinhood.place_sell_order(stockobj, amount)
            return response
        except Exception as e:
            print("Sell Order Failed", e)

# Input: stock symbol as a string
# Returns: share price as a float
def price(stock):
    if broker == 'robinhood':
        return float(robinhood.quote_data(stock)['last_trade_price'])

# Returns: list of ("symbol",amount)
def positions():
    positions = {}
    if broker == 'robinhood':
        robinhoodpositions = robinhood.positions()['results']
        for position in robinhoodpositions:
            name = str(requests.get(position['instrument']).json()['symbol'])
            amount = float(position['quantity'])
            positions[name] = amount
    return positions

# Returns dictionary of
    # "value": total portfolio value as a float
    # "cash": portfolio cash as a float
    # "daychange": current day's percent portfolio value change as a float
def portfoliodata():
    portfolio = {}
    if broker == 'robinhood':
        robinhoodportfolio = robinhood.portfolios()
        if robinhoodportfolio['extended_hours_equity'] is not None:
            portfolio["value"] = float(robinhoodportfolio['extended_hours_equity'])
        else:
            portfolio["value"] = float(robinhoodportfolio['equity'])
        if robinhoodportfolio['extended_hours_market_value'] is not None:
            portfolio["cash"] = portfolio["value"] - float(robinhoodportfolio['extended_hours_market_value'])
        else:
            portfolio["cash"] = portfolio["value"] - float(robinhoodportfolio['market_value'])
        portfolio["day change"] = 100 * (portfolio["value"] - float(robinhoodportfolio['adjusted_equity_previous_close'])) / \
                                                              float(robinhoodportfolio['adjusted_equity_previous_close'])
    portfolio["value"] = round(portfolio["value"],2)
    portfolio["cash"] = round(portfolio["cash"],2)
    portfolio["day change"] = round(portfolio["day change"],2)
    return portfolio


# High Priority
# TODO: TEST that it keeps placing buy order when waiting for sell to go through

# Medium priority
# TODO: Update buy function. Robinhood can only buy with 95% of your current cash
# TODO: Use yahoo-finance data when alphavantage fails
# TODO: Comment functions that don't have descriptions
# TODO: load and save data when closed/opened
# TODO: Avoid running every second and logging when not in market hours
# TODO: Use daily logging close in backtest for algos that run at 3:59

# Low Priority
# Add support for more brokers
# TODO: Add python3 type checking to functions
# TODO: Prevent day trades, Combine concurrent orders for same stock

if __name__ == '__main__':
    import code; code.interact(local=locals())
