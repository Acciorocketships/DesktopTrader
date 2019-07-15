import os, sys
import traceback
import pkg_resources
import datetime
from pytz import timezone
import time
import threading # Runs Backtest in a Thread
import json # Save and Load
import pandas as pd
import numpy as np
from empyrical import max_drawdown, alpha_beta, annual_volatility, sharpe_ratio # Risk Metrics
import math
import smtplib # Emailing
from pytrends.request import TrendReq # Google Searches
import logging
from apscheduler.schedulers.blocking import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.base import BaseTrigger
from typing import *

Date = Union[datetime.datetime, datetime.date]

broker = 'alpaca'
papertrade = True

if broker == 'alpaca':
	import alpaca_trade_api as tradeapi
	from ta import trend, volatility, momentum # Technical Indicators
else:
	logging.error("Choose a broker ('alpaca')")
	exit(-1)


creds:Dict[str,str] = {}
credential_file = pkg_resources.resource_filename(__name__, "creds.txt")
try:
	with open(credential_file, "r") as f:
		creds = json.load(f)
except IOError:
	creds['Email Address'] = input('Email Address: ')
	creds['Email Password'] = input('Email Password: ')
	if broker == 'alpaca':
		creds['Alpaca ID'] = input('Alpaca ID: ')
		creds['Alpaca Secret Key'] = input('Alpaca Secret Key: ')
		creds['Alpaca Paper ID'] = input('Alpaca ID: ')
		creds['Alpaca Paper Secret Key'] = input('Alpaca Secret Key: ')
	with open(credential_file, "w") as f:
		json.dump(creds,f)
except PermissionError:
	logging.error("Inadequate permissions to read credentials file.")
	exit(-1)

if broker == 'alpaca':
	api = tradeapi.REST(creds['Alpaca ID'] if not papertrade else creds['Alpaca Paper ID'], 
						creds['Alpaca Secret Key'] if not papertrade else creds['Alpaca Paper Secret Key'],
						base_url='https://api.alpaca.markets' if not papertrade else 'https://paper-api.alpaca.markets')
	account = api.get_account()

pytrends = TrendReq(hl='en-US', tz=360)



class Algorithm(object):

	def __init__(self, schedule:Union[str,List[str]]="30 9 * * *"):
		self.setschedule(schedule)
		# Variables that change automatically
		self.startingcapital:float = 0.0
		self.value:float = 0.0
		self.cash:float = 0.0
		self.stocks:Dict[str,int] = {}
		self.chartminute:List[float] = []
		self.chartminutetimes:List[datetime.datetime] = []
		self.chartday:List[float] = []
		self.chartdaytimes:List[datetime.datetime] = []
		self.running:bool = True
		self.cache:Dict[Tuple,Any] = {}
		self.stoplosses:Dict[str,Tuple[float,float]] = {}
		self.stopgains:Dict[str,Tuple[float,float]] = {}
		self.limitlow:Dict[str,Tuple[float,float]] = {}
		self.limithigh:Dict[str,Tuple[float,float]] = {}
		self.alpha:Optional[float] = None
		self.beta:Optional[float] = None
		self.volatility:Optional[float] = None
		self.sharpe:Optional[float] = None
		self.maxdrawdown:Optional[float] = None
		self.benchmark:Union[str,List[str]] = 'SPY'
		# User initialization
		self.initialize()

	def initialize(self):
		pass

	def run(self):
		pass

	def runalgo(self):
		try:
			self.run()
		except Exception as err:
			exc_type, exc_obj, exc_tb = sys.exc_info()
			fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
			stacktrace = traceback.format_tb(exc_tb)
			logging.error('%s %s in file %s:\n'.join(stacktrace), exc_type.__name__, err, fname)

	def runner(self, block:bool=False):
		if block:
			self.scheduler = BlockingScheduler(timezone=timezone("US/Eastern"))
		else:
			self.scheduler = BackgroundScheduler(timezone=timezone("US/Eastern"))
		self.scheduler.add_job(self.runalgo, self.scheduleTrigger)
		self.scheduler.start()


	def setschedule(self,schedule):
		self.scheduleCrons:List[str]= schedule if isinstance(schedule,list) else [schedule]
		self.scheduleTrigger:BaseTrigger = OrTrigger([CronTrigger.from_crontab(cron) for cron in self.scheduleCrons])
		self.scheduler:BaseScheduler = None


	### PRIVATE METHODS ###

	# Update function called every second
	def updatetick(self):
		stockvalue = 0
		for stock, amount in list(self.stocks.items()):
			stockvalue += self.quote(stock) * amount
		self.value = self.cash + stockvalue
		self.value = round(self.value,2)
		self.cash = round(self.cash,2)

	# Update function called every minute
	def updatemin(self):
		self.updatetick() 
		self.chartminute.append(self.value)
		self.chartminutetimes.append(self.algodatetime())
		self.checkthresholds(stock)

	# Update function called every day
	def updateday(self):
		self.chartminute = []
		self.chartminutetimes = []
		self.chartday.append(self.value)
		self.chartdaytimes.append(self.algodatetime())
		self.riskmetrics()

	# returns datetime as seen by algorithm (overridden in backtester)
	def algodatetime(self) -> datetime.datetime:
		return getdatetime()

	# returns the next expected execution time of algorithm, as defined by the given schedule
	def nextruntime(self) -> datetime.datetime:
		return self.scheduleTrigger.get_next_fire_time(None, self.algodatetime()).replace(tzinfo=None)

	# Checks and executes limit/stop orders
	def checkthreshold(self, stock:str):
		# Buy/Sell all shares of the stock if its price has crossed the threshold
		price = self.quote(stock)
		if (stock in self.stocks) and (stock in self.stoplosses) and (price <= self.stoplosses[stock][0]):
			print("Stoploss for " + stock + " kicking in.")
			del self.stoplosses[stock]
			self.orderfraction(stock,self.stoplosses[stock][1],verbose=True)
		elif (stock in self.stocks) and (stock in self.stopgains) and (price >= self.stopgains[stock][0]):
			print("Stopgain for " + stock + " kicking in.")
			del self.stopgains[stock]
			self.orderfraction(stock,self.stopgains[stock][1],verbose=True)
		elif (stock in self.limitlow) and (price <= self.limitlow[stock][0]):
			print("Limit order " + stock + " activated.")
			del self.limitlow[stock]
			self.orderfraction(stock,self.limitlow[stock][1],verbose=True)
		elif (stock in self.limithigh) and (price >= self.limithigh[stock][0]):
			print("Limit order " + stock + " activated.")
			del self.limithigh[stock]
			self.orderfraction(stock,self.limithigh[stock][1],verbose=True)
		# Remove a stock once it is sold
		if (stock in self.stoplosses) and (self.stocks.get(stock,0) == 0):
			del self.stoplosses[stock]
		if stock in self.stopgains and (self.stocks.get(stock,0) == 0):
			del self.stopgains[stock]

	def checkthresholds(self):
		for stock in self.stocks:
			self.checkthreshold(stock)

	def riskmetrics(self):
		try:
			if len(self.chartday) < 2:
				return
			benchmark = self.benchmark if type(self.benchmark)==str else 'SPY'
			changes = self.fractionchange(self.chartday)
			idx = [pd.Timestamp(date.date()) for date in self.chartdaytimes[1:]]
			changes.index = idx
			if len(changes) > 0:
				benchmarkchanges = self.fractionchange(benchmark, length=len(changes))
				idx = [date.tz_convert(None).date() for date in benchmarkchanges.index]
				benchmarkchanges.index = idx
				self.alpha, self.beta = alpha_beta(changes, benchmarkchanges)
				self.alpha = round(self.alpha,3)
				self.beta = round(self.beta,3)
				self.sharpe = round(sharpe_ratio(changes),3)
				self.volatility = round(annual_volatility(changes),3)
				self.maxdrawdown = round(max_drawdown(changes),3)
		except Exception as err:
			logging.error("Error in Algorithm riskmetrics: %s", err)


	### PUBLIC METHODS ###


	# Switches from live trading to paper trading
	# If self.running is False, the algorithm will automatically paper trade
	def papertrade(self,cash:Optional[float]=None):
		if self.running:
			self.cash = cash if (cash is not None) else self.value
			self.value = self.cash
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
	# amount is given as a number between 0 and 1 (uses orderfraction)
	def stopsell(self, stock:str, change:float, amount:float=0):
		if change > 0:
			self.stopgains[stock] = ( (1+change)*self.quote(stock), amount )
		if change < 0:
			self.stoplosses[stock] = ( (1+change)*self.quote(stock), amount )


	# Adds order for a stock when it crosses above or below a % change from the current price
	# If change == 0.05, then the stock will be bought if it goes 5% over the current price
	# If change == -0.05, then the stock will be bought if it goes 5% below the current price
	# amount is given as a number between 0 and 1 (uses orderfraction)
	def limitbuy(self, stock:str, change:float, amount:float=1):
		if amount == 1:
			amount = self.cash / self.value
		if change > 0:
			self.limithigh[stock] = ( (1+change)*self.quote(stock), amount )
		if change < 0:
			self.limitlow[stock] = ( (1+change)*self.quote(stock), amount )


	# stock: stock symbol (string)
	# amount: number of shares of that stock to order (+ for buy, - for sell)
	# verbose: prints out order
	def order(self, stock:str, amount:int, ordertype:str="market", stop:Optional[float]=None, 
					limit:Optional[float]=None, verbose:bool=False, notify_address:Optional[str]=None):
		# Guard condition for sell
		if amount < 0 and (-amount > self.stocks.get(stock,0)):
			print(("Warning: attempting to sell more shares (" + str(amount) + ") than are owned (" + str(
				self.stocks.get(stock,0)) + ") of " + stock))
			return
		cost = self.quote(stock)
		# Guard condition for buy
		if cost * amount > self.cash:
			print(("Warning: not enough cash ($" + str(self.cash) + ") in algorithm to buy " + str(
				amount) + " shares of " + stock))
			return
		# Do nothing if amount is 0
		if amount == 0:
			return
		# Place order, block until filled, update amount and cash
		currentcash = portfoliodata()["cash"]
		currentamount = positions().get(stock,0)
		newamount = currentamount
		if self.running:
			# Send order  
			if amount > 0:
				buy(stock, amount, ordertype=ordertype, stop=stop, limit=limit)
			elif amount < 0:
				sell(stock, abs(amount), ordertype=ordertype, stop=stop, limit=limit)
			# Block for 5 minutes. If order still hasn't filled, continue.
			for i in range(273):
				newamount = positions().get(stock,0)
				if newamount != currentamount:
					break
				else:
					time.sleep(0.5*(i ** 0.5))
			# If order didn't go through, return.
			if (newamount - currentamount) == 0:
				print("Order for " + str(amount) + " shares of " + stock + " did not fill in time. Continuing.")
				return
			# Update algo
			newcash = portfoliodata()["cash"]
			self.cash -= (currentcash - newcash)
			self.stocks[stock] = self.stocks.get(stock,0) + (newamount - currentamount)
		else:
			self.cash -= cost * amount
			self.stocks[stock] = self.stocks.get(stock,0) + amount
		# Send Notification
		if notify_address != None:
			if amount >= 0:
				message = self.algodatetime().strftime("%Y-%m-%d %H|%M|%S") + " - " + \
						  self.__class__.__name__ + " Buying " + str(amount) + " shares of " + stock + " at $" + str(cost)
			else:
				message = self.algodatetime().strftime("%Y-%m-%d %H|%M|%S") + " - " + \
						  self.__class__.__name__ + " Selling " + str(abs(amount)) + " shares of " + stock + " at $" + str(cost)
			self.notify(message,notify_address)
		if verbose:
			if amount >= 0:
				print( "Buying " + str(amount) + " shares of " + stock + " at $" + str(round(cost,2)))
			elif amount < 0:
				print( "Selling " + str(-amount) + " shares of " + stock + " at $" + str(round(cost,2)))


	# Buy or sell to reach a target fraction of the algorithm's total allocation
	# verbose = True to print out whenever an order is made
	# notify = "example@gmail.com" to send notification when an order is made (if True, it sends to yourself)
	def orderfraction(self, stock:str, fraction:float, verbose:bool=False, notify_address:Optional[str]=None):
		cost = self.quote(stock)
		currentfraction = 0.0
		if stock in self.stocks:
			currentfraction = self.stocks[stock] * cost / self.value
		fractiondiff = fraction - currentfraction
		if fractiondiff < 0:
			# Min of (# required to reach target fraction) and (# of that stock owned)
			amount = min( round(-fractiondiff * self.value / cost), self.stocks.get(stock,0) )
			return self.order(stock, -amount, verbose=verbose, notify_address=notify_address)
		else:
			# Min of (# required to reach target fraction) and (# that you can buy with your available cash)
			amount = min( math.floor(fractiondiff * self.value / cost), math.floor(self.cash / cost) )
			return self.order(stock, amount, verbose=verbose, notify_address=notify_address)


	# Sells all held stocks
	def sellall(self, verbose:bool=False, notify_address:Optional[str]=None):
		for stock in self.stocks:
			self.orderfraction(stock, 0, verbose=verbose, notify_address=None)


	### HISTORY AND INDICATORS ###


	# Uses broker to get the current price of a stock
	# stock: stock symbol (string)
	def quote(self, stock:str):
		return price(stock)


	# Use Alpha Vantage to get the historical price data of a stock
	# stock: stock symbol (string)
	# interval: time interval between data points 'day','minute'
	# length: number of data points (default is only the last)
	# datatype: 'close','open','volume' (default close)
	def history(self, stock:str, length:Union[int,Date]=1, datatype:str='close', interval:str='day'):
		hist = None
		while hist is None:
			try:	
				# Data from Alpaca
				if broker == 'alpaca':
					nextra = 0
					end = getdatetime().date() + datetime.timedelta(days=2)
					# Find start date
					if not isdate(length):
						length = cast(int, length)
						if interval=='minute':
							start = datetime.datetime.strptime( api.get_calendar(end=(self.algodatetime()+datetime.timedelta(days=1)).strftime("%Y-%m-%d"))[-1-(length//500)-nextra].date.strftime("%Y-%m-%d"), "%Y-%m-%d").date()
						else:	
							start = datetime.datetime.strptime( api.get_calendar(end=self.algodatetime().strftime("%Y-%m-%d"))[-length-nextra].date.strftime("%Y-%m-%d"), "%Y-%m-%d").date()
					else:
						start = cast(datetime.date, length)
					limit = 2500 if interval=='day' else 10
					frames = []
					totaltime = (end-start).days
					lastsegstart = start
					for k in range(totaltime // limit):
						tempstart = start + datetime.timedelta(days=limit*k+1)
						tempend = start + datetime.timedelta(days=limit*(k+1))
						lastsegstart = tempend + datetime.timedelta(days=1)
						frames.append(api.polygon.historic_agg(interval, stock, _from=tempstart.strftime("%Y-%m-%d"), to=tempend.strftime("%Y-%m-%d")).df)
					frames.append(api.polygon.historic_agg(interval, stock, _from=lastsegstart.strftime("%Y-%m-%d"), to=end.strftime("%Y-%m-%d")).df)
					hist = pd.concat(frames)
			# Keep trying if there is a network error
			except ValueError as err:
				logging.warning("Trying to fetch historical data: %s", err)
				time.sleep(5)
		# Convert length to int
		if isdate(length):
			length = datetolength(length,hist[datatype])
		if length is None:
			length = len(hist)
		# Return desired length
		return hist[datatype][-length:]


	# macd line: 12 day MA - 26 day MA
	# signal line: 9 period MA of the macd line
	# Returns MACD Indicator: (Signal - (FastMA - SlowMA))
	def macd(self, stock:str, length:Union[int,Date]=1, 
				   fastmawindow:int=12, slowmawindow:int=26, signalmawindow:int=9, 
				   matype:int=1, datatype:str='close', interval:str='day'):
		if isdate(length):
			length = len(tradingdays(length, self.algodatetime()))
		assert isinstance(length, int)
		hist = self.history(stock,interval=interval,length=length+slowmawindow+signalmawindow,datatype=datatype)
		md = trend.macd_diff(hist, n_fast=fastmawindow, n_slow=slowmawindow, n_sign=signalmawindow, fillna=False)
		return md[-length:]


	# Returns the number of standard deviations that the price is from the moving average
	# 0 means the price is at the middle band
	# 1 means the price is at the upper band
	# -1 means the price is at the lower band
	def bollinger(self, stock, length:Union[int,Date]=1, mawindow:int=20, ndev:int=2, 
						matype:int=1, datatype:str='close', interval:str='day'):
		if isdate(length):
			length = len(tradingdays(length, self.algodatetime()))
		assert isinstance(length, int)
		hist = self.history(stock,interval=interval,length=length+mawindow,datatype=datatype)
		upper = volatility.bollinger_hband(hist,mawindow,ndev,fillna=False)
		lower = volatility.bollinger_lband(hist,mawindow,ndev,fillna=False)
		middle = (upper + lower) / 2
		dev = (upper - lower) / 2
		bb = (hist - middle) / dev
		return bb[-length:]


	# Shows market trends by looking at the average gain and loss in the window.
	# Transformed from a scale of [0,100] to [-1,1]
	# RSI > 0.2 means overbought (sell indicator), RSI < -0.2 means oversold (buy indicator)
	def rsi(self, stock:str, length:Union[int,Date]=1, window:int=20, datatype:str='close', interval:str='day'):
		if isdate(length):
			length = len(tradingdays(length, self.algodatetime()))
		assert isinstance(length, int)
		hist = self.history(stock,interval=interval,length=length+window+1,datatype=datatype)
		r = momentum.rsi(pd.Series(np.array(hist)),n=window,fillna=False)
		r = (r - 50) / 50
		r.index = hist.index
		return r[-length:]


	# Moving Average. matype = 0 means simple, matype = 1 means exponential
	# If data is given instead of a stock, then it will take the moving average of that
	def ma(self, stock:Union[str,pd.Series], length:Union[int,Date]=1, mawindow:int=12, matype:int=0, datatype:str='close', interval:str='day'):
		if isdate(length):
			length = len(tradingdays(length, self.algodatetime()))
		assert isinstance(length, int)
		if isinstance(stock,str):
			hist = self.history(stock,interval=interval,length=length+mawindow,datatype=datatype)
		else:
			hist = stock
		if matype == 0:
			ma = volatility.bollinger_mavg(hist,n=mawindow,fillna=False)
		elif matype == 1:
			ma = trend.ema_indicator(hist,n=mawindow,fillna=False)
		return ma[-length:]


	# The price compared to the low and the high within a window
	# Transformed from a scale of [0,100] to [-1,1]
	# STOCH > 0.3 means overbought (sell indicator), STOCH < -0.3 means oversold (buy indicator)
	def stoch(self, stock, length:Union[int,Date]=1, window=14, interval='day'):
		if isdate(length):
			length = len(tradingdays(length, self.algodatetime()))
		assert isinstance(length, int)
		high = self.history(stock,interval=interval,length=length+window,datatype="high")
		low = self.history(stock,interval=interval,length=length+window,datatype="low")
		close = self.history(stock,interval=interval,length=length+window,datatype="close")
		s = momentum.stoch(high=high,low=low,close=close,n=window,fillna=False)
		s = (s - 50) / 50
		return s[-length:]


	# Returns the fraction change
	# If data is given instead of a stock, it returns the fraction change of that
	def fractionchange(self, stock:Union[str,pd.Series], length:Union[int,Date]=1, 
							 datatype:str='close', interval:str='day'):
		if isdate(length):
			length = len(tradingdays(length, self.algodatetime()))
		assert isinstance(length, int)
		if isinstance(stock,str):
			hist = self.history(stock,interval=interval,length=length+1,datatype=datatype)
		else:
			hist = pd.Series(stock)
			length = len(hist)-1
		changes = hist.pct_change()
		changes = changes.rename("fraction Change")
		return changes[-length:]


	# The google trends for interest over time in a given query
	# interval: hour, day (changes to weekly if length is too long)
	# Returns Series of numbers from 0 to 100 for relative interest over time
	# WARNING: Data is for all days (other data is just trading days)
	def google(self, query:str, length:Union[int,Date]=100, financial:bool=True, interval:str='day'):
		enddate = self.algodatetime()
		if not isinstance(length, int):
			startdate = length
		else:
			length += 1
			if interval == 'day':
				startdate = enddate - datetime.timedelta(days=length)
			elif interval == 'hour':
				startdate = enddate - datetime.timedelta(hours=length)
		if interval == 'day':
			startdatestr = startdate.strftime("%Y-%m-%d")
			enddatestr = enddate.strftime("%Y-%m-%d")
		elif interval == 'hour':
			startdatestr = startdate.strftime("%Y-%m-%dT%H")
			enddatestr = enddate.strftime("%Y-%m-%dT%H")
		category = 0
		if financial:
			category=1138
		pytrends.build_payload([query], cat=category, timeframe=startdatestr + " " + enddatestr, geo='US')
		return pytrends.interest_over_time()[query]


	# Send a string or a dictionary to an email or a phone number
	def notify(self, message:str, recipient:Optional[str]=None):
		# Dont send messages in backtesting
		if isinstance(self,Backtester):
			return
		if recipient is None:
			recipient = creds['Email Address']
		# Send current state of algorithm by default
		if len(message) == 0:
			exclude = {"times","chartminute","chartminutetimes","chartday","chartdaytimes","cache","stoplosses","stopgains","limitlow","limithigh"}
			messagedict = {key: value for (key,value) in self.__dict__.items() if key not in exclude}
		if type(message) == dict:
			message = dict2string(messagedict)
		gmail_user = creds['Email Address']
		gmail_password = creds['Email Password']
		# If recipient is an email address
		if "@" in recipient:
			try:
				emailserver = smtplib.SMTP_SSL("smtp.gmail.com", 465)
				emailserver.ehlo()
				emailserver.login(gmail_user, gmail_password)
				emailserver.sendmail(gmail_user, recipient, message)
				emailserver.close()
			except Exception as err:
				logging.error("Failed to send email notification: %s", err)
		# If recipient is an phone number
		else:
			textdomains = ["@tmomail.net","@vtext.com","@mms.att.net","@pm.sprint.com"]
			try:
				textserver = smtplib.SMTP('smtp.gmail.com',587)
				textserver.starttls()
				textserver.login(gmail_user, gmail_password)
				for domain in textdomains:
					textserver.sendmail(gmail_user, recipient+domain, message)
				textserver.close()
			except Exception as err:
				logging.error("Failed to send sms notification: %s", err)


	def __str__(self):
		varsdict = self.__dict__.copy()
		del varsdict["chartminutetimes"]
		del varsdict["chartminute"]
		del varsdict["cache"]
		return dict2string(varsdict)



class Backtester(Algorithm):
	def __init__(self, capital:float=10000.0, benchmark:Union[str,List[str]]='SPY', logging:str='day'):
		super(Backtester, self).__init__()
		# Constants
		self.logging:str = logging
		self.startingcapital:float = capital
		self.cash:float = capital
		self.exptime:int = 450
		# Variables that change automatically
		self.datetime:Optional[datetime.datetime] = None
		self.alpha:Optional[float] = None
		self.beta:Optional[float] = None
		self.volatility:Optional[float] = None
		self.sharpe:Optional[float] = None
		self.maxdrawdown:Optional[float] = None
		# Variables that the user can change
		self.benchmark:Union[str,List[str]] = benchmark


	# Starts the backtest (calls startbacktest in a new thread)
	# Times can be in the form of datetime objects or tuples (day,month,year)
	def start(self, start:Union[Date,Tuple[int,int,int],str]=datetime.datetime.today().date()-datetime.timedelta(days=90),
					end:Union[Date,Tuple[int,int,int],str]=datetime.datetime.today().date(), 
					logging:str='day'):
		backtestthread = threading.Thread(target=self.backtest, args=(start, end, logging))
		backtestthread.start()


	# Starts the backtest
	def backtest(self, start:Union[Date,Sequence[int],str]=datetime.datetime.today().date()-datetime.timedelta(days=90),
					   end:Union[Date,Sequence[int],str]=datetime.datetime.today().date(), 
					   logging:str='day'):
		if isinstance(start, str):
			start = tuple([int(x) for x in start.split("-")])
		if isinstance(end,str):
			end = tuple([int(x) for x in end.split("-")])
		if isinstance(start,list) or isinstance(start,tuple):
			start = datetime.datetime(start[0], start[1], start[2], 0, 0)
		if isinstance(end,list) or isinstance(end,tuple):
			end = datetime.datetime(end[0], end[1], end[2], 23, 59)
		start = cast(Date, start)
		end = cast(Date, end)
		days = tradingdays(start=start, end=end)
		self.logging = logging
		self.datetime = cast(Optional[datetime.datetime], start)
		self.update()
		for day in days:
			if self.logging == 'minute':
				for minute in range(391):
					# Set datetime of algorithm
					self.datetime = datetime.datetime.combine(day, datetime.time(9, 30)) + datetime.timedelta(minutes=minute)
					# Exit if that datetime is in the future
					if self.algodatetime() >= getdatetime():
						break
					if self.algodatetime() == self.nextruntime():
						# Update algorithm cash and value
						self.update()
						# Run algorithm
						self.run()
					# Log algorithm cash and value
					self.updatemin()
					# Check limit order thresholds
					self.checkthresholds()
				# Log algorithm cash and value
				self.updateday()
			elif self.logging == 'day':
				checkedthresholds = False
				# While it's still the current trading day
				self.datetime = datetime.datetime.combine(day, datetime.time(0,0))
				while self.nextruntime().date() == day.date():
					# Set datetime of algorithm
					self.datetime = self.nextruntime()
					# Exit if that datetime is in the future
					if self.algodatetime() >= getdatetime():
						break
					# If algorithm is running at the end of the day, check thresholds before running it
					if self.algodatetime().time() == datetime.time(15,59):
						self.checkthresholds()
						checkedthresholds = True
					# Update algorithm cash and value
					self.update()
					# Run algorithm
					self.run()
					# Proceed to next minute
					self.datetime += datetime.timedelta(minutes=1)
				# Check limit order thresholds if it hasn't already been done
				if not checkedthresholds:
					self.checkthresholds()
				# Log algorithm cash and value
				self.updateday()
		self.riskmetrics()


	def updatemin(self):
		self.update()
		self.chartminute.append(self.value)
		self.chartminutetimes.append(self.algodatetime())


	def updateday(self):
		self.update()
		self.chartday.append(self.value)
		self.chartdaytimes.append(self.algodatetime())


	def update(self):
		stockvalue = 0
		for stock, amount in list(self.stocks.items()):
			if amount == 0:
				del self.stocks[stock]
			else:
				stockvalue += self.quote(stock) * amount
		self.value = self.cash + stockvalue
		self.value = round(self.value, 2)


	def algodatetime(self):
		if self.datetime is None:
			return getdatetime()
		return self.datetime


	def checkthreshold(self, stock:str):
		# Enforce Thresholds
		if self.logging == 'minute': # Check if the current price activates a threshold
			price = self.quote(stock)
			if (stock in self.stocks) and (stock in self.stoplosses) and (price <= self.stoplosses[stock][0]):
				print("Stoploss for " + stock + " kicking in at $" + str(round(self.stoplosses[stock][0],2)))
				self.orderfraction(stock,self.stoplosses[stock][1],verbose=True)
				del self.stoplosses[stock]
			elif (stock in self.stocks) and (stock in self.stopgains) and (price >= self.stopgains[stock][0]):
				print("Stopgain for " + stock + " kicking in at $" + str(round(self.stopgains[stock][0],2)))
				self.orderfraction(stock,self.stopgains[stock][1],verbose=True)
				del self.stopgains[stock]
			elif (stock in self.limitlow) and (price <= self.limitlow[stock][0]):
				print("Limit order " + stock + " activated at $" + str(round(self.limitlow[stock][0],2)))
				self.orderfraction(stock,self.limitlow[stock][1],verbose=True)
				del self.limitlow[stock]
			elif (stock in self.limithigh) and (price >= self.limithigh[stock][0]):
				print("Limit order " + stock + " activated at $" + str(round(self.limithigh[stock][0],2)))
				self.orderfraction(stock,self.limithigh[stock][1],verbose=True)
				del self.limithigh[stock]
		else: # Check if the day's low or high activates a threshold
			if (stock in self.stocks) and (stock in self.stoplosses) and (self.history(stock,datatype='low')[0] <= self.stoplosses[stock][0]):
				print("Stoploss for " + stock + " kicking in at $" + str(round(self.stoplosses[stock][0],2)))
				self.orderfraction(stock, self.stoplosses[stock][1], cost=self.stoplosses[stock][0], verbose=True)
				del self.stoplosses[stock]
			elif (stock in self.stocks) and (stock in self.stopgains) and (self.history(stock,datatype='high')[0] >= self.stopgains[stock][0]):
				print("Stopgain for " + stock + " kicking in at $" + str(round(self.stopgains[stock][0],2)))
				self.orderfraction(stock, self.stopgains[stock][1], cost=self.stopgains[stock][0], verbose=True)
				del self.stopgains[stock]
			elif (stock in self.limitlow) and (self.history(stock,datatype='low')[0] <= self.limitlow[stock][0]):
				print("Limit order " + stock + " activated at $" + str(round(self.limitlow[stock][0],2)))
				self.orderfraction(stock, self.limitlow[stock][1], cost=self.limitlow[stock][0], verbose=True)
				del self.limitlow[stock]
			elif (stock in self.limithigh) and (self.history(stock,datatype='high')[0] >= self.limithigh[stock][0]):
				print("Limit order " + stock + " activated at $" + str(round(self.limithigh[stock][0],2)))
				self.orderfraction(stock, self.limithigh[stock][1], cost=self.limithigh[stock][0], verbose=True)
				del self.limithigh[stock]


	def checkthresholds(self):
		for stock in self.stocks:
			self.checkthreshold(stock)


	def quote(self, stock:str):
		if self.algodatetime().time() <= datetime.time(9,30,0,0):
			return self.history(stock, interval='day', datatype='open')[0].item()
		elif self.algodatetime().time() >= datetime.time(15,59,0,0):
			return self.history(stock, interval='day', datatype='close')[0].item()
		return self.history(stock, interval=self.logging, datatype='close')[0].item()


	def history(self, stock:str, length:Union[int,Date]=1, datatype:str='close', interval:str='day'):
		key = (stock, interval)
		cache = self.cache.get(key)
		if cache is not None:
			hist, dateidx, lastidx, time = cache 
		if cache is None or (interval=='day' and (getdatetime()-time).days > 0) or (interval=='minute' and (getdatetime()-time).seconds > 120):
			hist = None
			while hist is None:
				try:
					if broker == 'alpaca': # Data from Alpaca
						nextra = 100 if interval=='day' else 1 # Number of extra samples before the desired range
						end = getdatetime().date() + datetime.timedelta(days=2)
						# Find start date
						if not isdate(length):
							length = cast(int, length)
							if interval=='minute':
								start = datetime.datetime.strptime( api.get_calendar(end=(self.algodatetime()+datetime.timedelta(days=1)).strftime("%Y-%m-%d"))[-1-(length//500)-nextra].date.strftime("%Y-%m-%d"), "%Y-%m-%d").date()
							else:	
								start = datetime.datetime.strptime( api.get_calendar(end=self.algodatetime().strftime("%Y-%m-%d"))[-length-nextra].date.strftime("%Y-%m-%d"), "%Y-%m-%d").date()
						else:
							start = cast(datetime.date, length)
						limit = 2500 if interval=='day' else 10
						frames = []
						totaltime = (end-start).days
						lastsegstart = start
						for k in range(totaltime // limit):
							tempstart = start + datetime.timedelta(days=limit*k+1)
							tempend = start + datetime.timedelta(days=limit*(k+1))
							lastsegstart = tempend + datetime.timedelta(days=1)
							frames.append(api.polygon.historic_agg(interval, stock, _from=tempstart.strftime("%Y-%m-%d"), to=tempend.strftime("%Y-%m-%d")).df)
						frames.append(api.polygon.historic_agg(interval, stock, _from=lastsegstart.strftime("%Y-%m-%d"), to=end.strftime("%Y-%m-%d")).df)
						hist = pd.concat(frames)
				# Pause and try again if there is an error
				except ValueError as err:
					logging.warning('Trying to fetch historical backtest data: %s', err)
					time.sleep(5)
			# Save To Cache
			dateidx = dateidxs(hist)
			lastidx = nearestidx(self.algodatetime(), dateidx)
			self.cache[key] = [hist, dateidx, lastidx, getdatetime()]
		# Look for current datetime in cached data
		try:
			idx = nearestidx(self.algodatetime(), dateidx, lastchecked=lastidx)
			if isdate(length):
				length = cast(Date, length)
				length = datetolength(length,dateidx,idx)
			# Convert length to int
			if length is None:
				length = len(hist)
			if idx-length+1 < 0:
				logging.error('Not enough historical data')
		except: # Happens if we request data farther back than before
			del self.cache[key]
			return self.history(stock, interval=interval, length=length, datatype=datatype)
		self.cache[key][2] = idx
		
		return hist[datatype][idx-length+1 : idx+1]
		

	def order(self, stock:str, amount:int, ordertype:str="market",
					stop:Optional[float]=None, limit:Optional[float]=None, verbose:bool=False,
					notify_address:Optional[str]=None, cost:Optional[float]=None):
		# Guard condition for sell
		if amount < 0 and (stock in self.stocks) and (-amount > self.stocks[stock]):
			print(("Warning: attempting to sell more shares (" + str(amount) + ") than are owned (" + 
				str(self.stocks.get(stock,0)) + ") of " + stock))
			return None
		if cost is None:
			cost = self.quote(stock)
		assert isinstance(cost, float)
		# Guard condition for buy
		if cost * amount > self.cash:
			print(("Warning: not enough cash ($" + str(round(self.cash,2)) + ") in algorithm to buy " + str(
				amount) + " shares of " + stock))
			return None
		if amount == 0:
			return None
		# Immediately execute market order
		if ordertype == 'market':
			self.stocks[stock] = self.stocks.get(stock, 0) + amount
			self.cash -= cost * amount
			self.cash = round(self.cash,2)
			if verbose:
				if amount >= 0:
					print( "Buying " + str(amount) + " shares of " + stock + " at $" + str(round(cost,2)))
				else:
					print( "Selling " + str(-amount) + " shares of " + stock + " at $" + str(round(cost,2)))
		# Simulate stop and limit orders
		elif ordertype == 'stop' or ordertype == 'limit':
			if limit is None and stop is None:
				logging.error("You need to specify a stop or limit price for stop/limit orders")
				return
			price = limit if (limit is not None) else stop
			assert isinstance(price, float)
			change = (price - cost) / cost
			perc = (self.stocks.get(stock,0) + amount) * cost / self.value
			if amount > 0:
				self.limitbuy(stock, change, perc)
			else:
				self.stopsell(stock, change, perc)
		# TODO: Test stop/limit orders in backtest.


	def orderfraction(self, stock, fraction, ordertype="market", stop=None, limit=None, verbose=False, notify_address=None, cost=None):
		if cost is None:
			cost = self.quote(stock)
		currentfraction = self.stocks.get(stock,0) * cost / self.value
		fractiondiff = fraction - currentfraction
		if fractiondiff < 0:
			# Min of (# required to reach target fraction) and (# of that stock owned)
			amount = min( round(-fractiondiff * self.value / cost), self.stocks.get(stock,0) )
			return self.order(stock=stock, amount=-amount, \
							  ordertype=ordertype, stop=stop, limit=limit, \
							  verbose=verbose, notify_address=notify_address, cost=cost)
		else:
			# Min of (# required to reach target fraction) and (# that you can buy with your available cash)
			amount = min( math.floor(fractiondiff * self.value / cost), math.floor(self.cash / cost) )
			return self.order(stock=stock, amount=amount, \
							  ordertype=ordertype, stop=stop, limit=limit, \
							  verbose=verbose, notify_address=notify_address, cost=cost)



### Helper Functions ###


def getdatetime() -> datetime.datetime:
	return datetime.datetime.now(timezone('US/Eastern')).replace(tzinfo=None)


# If start and end are both dates, it returns a list of trading days from the start date to the end date (not including end date)
# If start is a date and end is an int, it returns the date that is end days after start
# If start is an int and end is a date, it returns the date that is start days before end
def tradingdays(start:Union[Date,Sequence[int],str,int]=getdatetime(), 
				end:Union[Date,Sequence[int],str,int]=1):

	# Convert Date Datatypes
	if isinstance(start, str):
		start = tuple([int(x) for x in start.split("-")])
	if isinstance(end,str):
		end = tuple([int(x) for x in end.split("-")])
	if isinstance(start,list) or isinstance(start,tuple):
		start = datetime.date(start[0], start[1], start[2])
	if isinstance(end,list) or isinstance(end,tuple):
		end = datetime.date(end[0], end[1], end[2])
	start = cast(Date, start)
	end = cast(Date, end)

	if isinstance(start,int) and isinstance(end,int):
		raise TypeError("Either start or end must be a date")

	# Range of Dates
	if isdate(start) and isdate(end):
		datelist = [day.date.to_pydatetime() for day in api.get_calendar(start = start.strftime("%Y-%m-%d"), end = end.strftime("%Y-%m-%d"))]
		return datelist

	# n Days Before End
	if isinstance(start,int) and isdate(end):
		n = start
		start = end - datetime.timedelta(days=2*n)
		datelist = api.get_calendar(start = start.strftime("%Y-%m-%d"), end = end.strftime("%Y-%m-%d"))
		date = datelist[-n].date.to_pydatetime()
		return date

	# n Days After Start
	if isdate(start) and isinstance(end,int):
		n = end
		end = start + datetime.timedelta(days=2*n+5)
		datelist = api.get_calendar(start = start.strftime("%Y-%m-%d"), end = end.strftime("%Y-%m-%d"))
		date = datelist[n].date.to_pydatetime()
		return date


# Determines if variable is a datetime.datetime or datetime.date object
def isdate(var:Any) -> bool:
	return isinstance(var,datetime.datetime) or isinstance(var,datetime.date)


def datetimeequals(dt1:Union[datetime.datetime,datetime.date,datetime.time], 
				   dt2:Union[datetime.datetime,datetime.date,datetime.time]) -> bool:
	# get date and time for each input
	dt1date = None
	dt1time = None
	dt2date = None
	dt2time = None
	if isinstance(dt1, datetime.datetime):
		dt1date = dt1.date()
		dt1time = dt1.time()
	elif isinstance(dt1, datetime.date):
		dt1date = dt1
	elif isinstance(dt1, datetime.time):
		dt1time = dt1
	if isinstance(dt2, datetime.datetime):
		dt2date = dt2.date()
		dt2time = dt2.time()
	elif isinstance(dt2, datetime.date):
		dt2date = dt2
	elif isinstance(dt2, datetime.time):
		dt2time = dt2
	# if all trailing values of one time are 0, then truncate the other time as well
	# that way, 4:30 == 4:30:16:725650
	if dt1time is not None and dt2time is not None:
		if dt1time.second == 0 and dt1time.microsecond == 0:
			dt2time = dt2time.replace(second=0, microsecond=0)
		if dt2time.second == 0 and dt2time.microsecond == 0:
			dt1time = dt1time.replace(second=0, microsecond=0)
		if dt1time.microsecond == 0:
			dt2time = dt2time.replace(microsecond=0)
		if dt2time.microsecond == 0:
			dt1time = dt1time.replace(microsecond=0)
	# if only one date is provided or the dates do not match, they are not equal
	if dt1date != dt2date:
		return False
	# only fail if both times are given and they don't match. 
	if (dt1time is not None) and (dt2time is not None) and (dt1time != dt2time):
		return False
	return True


# Returns the list of datetime objects associated with the entries of a pandas dataframe
def dateidxs(arr:Union[pd.DataFrame,pd.Series]):
	try:
		return [pd.to_datetime(item[0]).replace(tzinfo=None).to_pydatetime() for item in arr.iterrows()]
	except:
		return [pd.to_datetime(item[0]).replace(tzinfo=None).to_pydatetime() for item in arr.iteritems()]


# Returns the index of the nearest element in dateidxs that occured before (or at the same time) as time.
# If lastchecked==None: Searches backward from the most recent entries
# If lastchecked>=0: Searches forward starting at lastchecked
# If lastchecked<0: Searches backward starting at -lastchecked
def nearestidx(startdate:Date, dateidx:List[Date], lastchecked:Optional[int]=None):
	if lastchecked is None:
		for i in range(len(dateidx)):
			index = len(dateidx) - i - 1
			if dateidx[index] <= startdate:
				return index
	elif lastchecked >= 0:
		for i in range(len(dateidx)):
			index = (lastchecked + i - 5) % len(dateidx)
			if dateidx[index] > startdate:
				return index-1
		return len(dateidx)-1
	else:
		for i in range(len(dateidx)):
			index = (len(dateidx) - lastchecked - i) % len(dateidx)
			if dateidx[index] <= startdate:
				return index
	logging.error("Datetime %s not found in historical data.", startdate)


# Returns the difference of the indexes of startdate and currentdateidx in dateidxs
# startdate: datetime in the past
# currentdateidx: idx of current date in dateidxs (datetime also accepted) (If None given, it will default to the last value)
# dateidx: list of datetimes (original pandas dataframe also accepted)
def datetolength(startdate:Date, dateidx:Union[List[Date],pd.DataFrame,pd.Series], currentdateidx:Optional[Union[Date,int]]=None):
	if isinstance(dateidx,pd.DataFrame) or isinstance(dateidx,pd.Series):
		dateidx = dateidxs(dateidx)
	if isdate(currentdateidx):
		currentdateidx = cast(Date, currentdateidx)
		currentdateidx = nearestidx(currentdateidx, dateidx)
	if currentdateidx is None:
		currentdateidx = len(dateidx)-1
	assert isinstance(currentdateidx, int)
	return currentdateidx - nearestidx(startdate, dateidx, lastchecked=-currentdateidx) + 1


# Converts a dictionary to a string
def dict2string(dictionary:Dict[Any,Any], spaces:int=0):
	string = ""
	if type(dictionary) == dict:
		for (key,value) in dictionary.items():
			if type(value) != dict and type(value) != list:
				string += (" " * spaces*4) + str(key) + " - " + str(value) + "\n"
			else:
				string += (" " * spaces*4) + str(key) + " - \n"
				string += dict2string(value,spaces+1)
	elif type(dictionary) == list:
		for item in dictionary:
			string += dict2string(item,spaces+1)
	else:
		string += (" " * spaces*4) + str(dictionary) + "\n"
	return string


# Converts an Algorithm to a BacktestAlgorithm, allowing you to backtest it
def backtester(algo:Algorithm, capital:Optional[float]=None, benchmark:Optional[Union[str,List[str]]]=None):
	# Convert
	BacktestAlgorithm = type('BacktestAlgorithm', (Backtester,), dict((algo.__class__).__dict__))
	algoback = BacktestAlgorithm()
	algoback.__dict__ = algo.__dict__
	# Set Capital
	if capital is None:
		if algoback.value == 0:
			algoback.cash = 10000.0
	else:
		algoback.cash = capital
	algoback.value = algoback.cash
	# Set Benchmark
	if benchmark is not None:
		algoback.benchmark = benchmark
	elif 'benchmark' in algo.__dict__:
		algoback.benchmark = algo.benchmark
	else:
		algoback.benchmark = "SPY"
	return algoback


# Input: stock symbol as a string, number of shares as an int
# ordertype: "market", "limit", "stop", "stop_limit"
def buy(stock:str, amount:int, ordertype:str='market', stop:Optional[float]=None, limit:Optional[float]=None, block:bool=True):
	if broker == 'alpaca':
		order = api.submit_order(stock, amount, side='buy', type=ordertype, time_in_force='day', limit_price=limit, stop_price=stop)
		if block:
			starttime = getdatetime()
			while (order.filled_at is None) and ((getdatetime()-starttime).seconds < 60):
				order = api.get_order(order.id)
				time.sleep(0.1)
		return order


# Input: stock symbol as a string, number of shares as an int
# ordertype: "market", "limit", "stop", "stop_limit"
def sell(stock:str, amount:int, ordertype:str='market', stop:Optional[float]=None, limit:Optional[float]=None, block:bool=True):
	if broker == 'alpaca':
		order = api.submit_order(stock, amount, side='sell', type=ordertype, time_in_force='day', limit_price=limit, stop_price=stop)
		if block:
			starttime = datetime.datetime.now()
			while (order.filled_at is None) and ((datetime.datetime.now()-starttime).seconds < 60):
				order = api.get_order(order.id)
				time.sleep(0.1)
		return order


# Input: stock symbol as a string
# Returns: share price as a float
def price(stock:str):
	if broker == 'alpaca':
		cost = float(api.polygon.last_quote(stock).askprice)
		if cost == 0:
			cost = float(api.polygon.last_trade(stock).price)
		return cost


# Returns: list of ("symbol",amount)
def positions():
	
	positions = {}
	
	if broker == 'alpaca':
		poslist = api.list_positions()
		for pos in poslist:
			positions[pos.symbol] = int(pos.qty)
	
	return positions


# Returns dictionary of
	# "value": total portfolio value as a float
	# "cash": portfolio cash as a float
	# "daychange": current day's fraction portfolio value change as a float
def portfoliodata():
	
	portfolio = {}

	if broker == 'alpaca':
		account = api.get_account()
		portfolio["value"] = float(account.portfolio_value)
		portfolio["cash"] = float(account.buying_power)
	
	portfolio["value"] = round(portfolio["value"],2)
	portfolio["cash"] = round(portfolio["cash"],2)
	return portfolio



