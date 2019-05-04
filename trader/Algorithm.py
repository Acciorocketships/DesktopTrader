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
import requests # Used in Positions() for Robinhood
import smtplib # Emailing
from pytrends.request import TrendReq # Google Searches

broker = 'alpaca'
papertrade = True

if broker == 'robinhood':
	from Robinhood import Robinhood
	from alpha_vantage.timeseries import TimeSeries
	from alpha_vantage.techindicators import TechIndicators
elif broker == 'alpaca':
	import alpaca_trade_api as tradeapi
	from ta import * # Technical Indicators
else:
	print("Choose a broker ('robinhood' or 'alpaca')")
	exit(-1)


creds = {}
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
	if True: #broker == 'robinhood':
		creds['Robinhood Username'] = input('Robinhood Username: ')
		creds['Robinhood Password'] = input('Robinhood Password: ')
		creds['Alpha Vantage API Key'] = input('Alpha Vantage API Key: ')
	with open(credential_file, "w") as f:
		json.dump(creds,f)
except PermissionError:
	print("Inadequate permissions to read credentials file.")
	exit(-1)

if broker == 'robinhood':
	robinhood = Robinhood()
	robinhood.login(username=creds['Robinhood Username'], password=creds['Robinhood Password'])
	data = TimeSeries(key=creds['Alpha Vantage API Key'], output_format='pandas')
	tech = TechIndicators(key=creds['Alpha Vantage API Key'], output_format='pandas')
elif broker == 'alpaca':
	api = tradeapi.REST(creds['Alpaca ID'] if not papertrade else creds['Alpaca Paper ID'], 
						creds['Alpaca Secret Key'] if not papertrade else creds['Alpaca Paper Secret Key'],
						base_url='https://api.alpaca.markets' if not papertrade else 'https://paper-api.alpaca.markets')
	account = api.get_account()

pytrends = TrendReq(hl='en-US', tz=360)



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
		self.datetime = self.getdatetime()
		self.alpha = 0
		self.beta = 0
		self.volatility = 0
		self.sharpe = 0
		self.maxdrawdown = 0
		self.benchmark = 'SPY'
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
			print(err)
			print(exc_type, fname, exc_tb.tb_lineno)

	### PRIVATE METHODS ###

	# Update function called every second
	def updatetick(self):
		stockvalue = 0
		for stock, amount in list(self.stocks.items()):
			stockvalue += self.quote(stock) * amount
		self.value = self.cash + stockvalue
		self.value = round(self.value,2)
		self.cash = round(self.cash,2)
		self.datetime = self.getdatetime()

	# Update function called every minute
	def updatemin(self):
		self.chartminute.append(self.value)
		self.chartminutetimes.append(self.getdatetime())
		for stock in (self.stopgains.keys() | self.stoplosses.keys()):
			self.checkthresholds(stock)

	# Update function called every day
	def updateday(self):
		self.chartminute = []
		self.chartminutetimes = []
		self.chartday.append(self.value)
		self.chartdaytimes.append(self.getdatetime())
		self.riskmetrics()

	def getdatetime(self):
		return datetime.datetime.now(timezone('US/Eastern')).replace(tzinfo=None)

	# Checks and executes limit/stop orders
	# TODO: Custom amounts to buy/sell
	def checkthresholds(self,stock):
		# Buy/Sell all shares of the stock if its price has crossed the threshold
		price = self.quote(stock)
		alloc = self.cash / self.value
		if (stock in self.stocks) and (stock in self.stoplosses) and (price <= self.stoplosses[stock][0]):
			print("Stoploss for " + stock + " kicking in.")
			del self.stoplosses[stock]
			self.orderpercent(stock,0,verbose=True)
		elif (stock in self.stocks) and (stock in self.stopgains) and (price >= self.stopgains[stock][0]):
			print("Stopgain for " + stock + " kicking in.")
			del self.stopgains[stock]
			self.orderpercent(stock,0,verbose=True)
		elif (stock in self.limitlow) and (price <= self.limitlow[stock][0]):
			print("Limit order " + stock + " activated.")
			del self.limitlow[stock]
			self.orderpercent(stock,alloc,verbose=True)
		elif (stock in self.limithigh) and (price >= self.limithigh[stock][0]):
			print("Limit order " + stock + " activated.")
			del self.limithigh[stock]
			self.orderpercent(stock,alloc,verbose=True)
		# Remove a stock once it is sold
		if (stock in self.stoplosses) and (self.stocks.get(stock,0) == 0):
			del self.stoplosses[stock]
		if stock in self.stopgains and (self.stocks.get(stock,0) == 0):
			del self.stopgains[stock]

	def riskmetrics(self):
		benchmark = self.benchmark if type(self.benchmark)==str else 'SPY'
		changes = self.percentchange(self.chartday)
		idx = [pd.Timestamp(date.date()) for date in self.chartdaytimes[1:]]
		changes.index = idx
		if len(changes) > 0:
			benchmarkchanges = self.percentchange(benchmark, length=len(changes))
			idx = [date.tz_convert(None).date() for date in benchmarkchanges.index]
			benchmarkchanges.index = idx
			self.alpha, self.beta = alpha_beta(changes, benchmarkchanges)
			self.alpha = round(self.alpha,3)
			self.beta = round(self.beta,3)
			self.sharpe = round(sharpe_ratio(changes),3)
			self.volatility = round(annual_volatility(changes),3)
			self.maxdrawdown = round(max_drawdown(changes),3)


	### PUBLIC METHODS ###


	# Switches from live trading to paper trading
	# If self.running is False, the algorithm will automatically paper trade
	def papertrade(self,cash=None):
		if self.running:
			if cash != None:
				self.cash = cash
			else:
				self.cash = self.value
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
	# amount is given as a number between 0 and 1 (uses orderpercent)
	def stopsell(self, stock, change, amount=0):
		if change > 0:
			self.stopgains[stock] = ( (1+change)*self.quote(stock), amount )
		if change < 0:
			self.stoplosses[stock] = ( (1+change)*self.quote(stock), amount )


	# Adds order for a stock when it crosses above or below a % change from the current price
	# If change == 0.05, then the stock will be bought if it goes 5% over the current price
	# If change == -0.05, then the stock will be bought if it goes 5% below the current price
	# amount is given as a number between 0 and 1 (uses orderpercent)
	def limitbuy(self, stock, change, amount=1):
		if amount == 1:
			amount = self.cash / self.value
		if change > 0:
			self.limithigh[stock] = ( (1+change)*self.quote(stock), amount )
		if change < 0:
			self.limitlow[stock] = ( (1+change)*self.quote(stock), amount )


	# stock: stock symbol (string)
	# amount: number of shares of that stock to order (+ for buy, - for sell)
	# verbose: prints out order
	def order(self, stock, amount, ordertype="market", stop=None, limit=None, verbose=False, notify_address=None):
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
				message = self.datetime.strftime("%Y-%m-%d %H|%M|%S") + " - " + self.__class__.__name__ + " Buying " + str(amount) + " shares of " + stock + " at $" + str(cost)
			else:
				message = self.datetime.strftime("%Y-%m-%d %H|%M|%S") + " - " + self.__class__.__name__ + " Selling " + str(abs(amount)) + " shares of " + stock + " at $" + str(cost)
			if type(notify_address)==str:
				self.notify(message,notify_address)
			elif notify_address:
				self.notify(message)
		if verbose:
			if amount >= 0:
				print( "Buying " + str(amount) + " shares of " + stock + " at $" + str(round(cost,2)))
			elif amount < 0:
				print( "Selling " + str(-amount) + " shares of " + stock + " at $" + str(round(cost,2)))


	# Buy or sell to reach a target percent of the algorithm's total allocation
	# verbose = True to print out whenever an order is made
	# notify = "example@gmail.com" to send notification when an order is made (if True, it sends to yourself)
	def orderpercent(self, stock, percent, verbose=False, notify_address=None):
		cost = self.quote(stock)
		currentpercent = 0.0
		if stock in self.stocks:
			currentpercent = self.stocks[stock] * cost / self.value
		percentdiff = percent - currentpercent
		if percentdiff < 0:
			# Min of (# required to reach target percent) and (# of that stock owned)
			amount = min( round(-percentdiff * self.value / cost), self.stocks.get(stock,0) )
			return self.order(stock, -amount, verbose, notify_address)
		else:
			# Min of (# required to reach target percent) and (# that you can buy with your available cash)
			amount = min( math.floor(percentdiff * self.value / cost), math.floor(self.cash / cost) )
			return self.order(stock, amount, verbose, notify_address)


	# Sells all held stocks
	def sellall(self, verbose=False, notify_address=None):
		for stock in self.stocks:
			self.orderpercent(stock, 0, verbose=verbose, notify_address=None)


	### HISTORY AND INDICATORS ###


	# Uses broker to get the current price of a stock
	# stock: stock symbol (string)
	def quote(self, stock):
		return price(stock)


	# Use Alpha Vantage to get the historical price data of a stock
	# stock: stock symbol (string)
	# interval: time interval between data points 'day','minute'
	# length: number of data points (default is only the last)
	# datatype: 'close','open','volume' (default close)
	def history(self, stock, length=1, datatype='close', interval='day'):
		hist = None
		while hist is None:
			try:	
				# Data from AlphaVantage
				if broker == 'robinhood':
					# Convert Datatype String
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
					# Get Daily or Intraday Data
					if interval == 'day':
						interval = 'daily'
						hist, _ = data.get_daily_adjusted(symbol=stock, outputsize='full')
					elif interval == 'minute':
						interval = '1min'
						hist, _ = data.get_intraday(symbol=stock, interval=interval, outputsize='full')
				# Data from Alpaca
				elif broker == 'alpaca':
					nextra = 0
					end = self.getdatetime() + datetime.timedelta(days=2)
					if not isdate(length):
						if interval=='minute':
							start = datetime.datetime.strptime( api.get_calendar(end=(self.datetime+datetime.timedelta(days=1)).strftime("%Y-%m-%d"))[-1-(length//500)-nextra].date.strftime("%Y-%m-%d"), "%Y-%m-%d")
						else:	
							start = datetime.datetime.strptime( api.get_calendar(end=self.datetime.strftime("%Y-%m-%d"))[-length-nextra].date.strftime("%Y-%m-%d"), "%Y-%m-%d")
					else:
						start = length
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
				print(err)
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
	def macd(self, stock, length=1, fastmawindow=12, slowmawindow=26, signalmawindow=9, matype=1, datatype='close', interval='day'):
		hist = None
		while hist is None:
			try:
				hist = self.history(stock,interval=interval,length=length+slowmawindow+signalmawindow,datatype=datatype)
				md = trend.macd_diff(hist, n_fast=fastmawindow, n_slow=slowmawindow, n_sign=signalmawindow, fillna=False)
			except ValueError as err:
				print(err)
				time.sleep(5)
		if isdate(length):
			length = datetolength(length,md)
		if length is None:
			length = len(md)
		return md[-length:]


	# Returns the number of standard deviations that the price is from the moving average
	# 0 means the price is at the middle band
	# 1 means the price is at the upper band
	# -1 means the price is at the lower band
	def bollinger(self, stock, length=1, mawindow=20, ndev=2, matype=1, datatype='close', interval='day'):
		hist = None
		while hist is None:
			try:
				hist = self.history(stock,interval=interval,length=length+mawindow,datatype=datatype)
				upper = volatility.bollinger_hband(hist,mawindow,ndev,fillna=False)
				lower = volatility.bollinger_lband(hist,mawindow,ndev,fillna=False)
				middle = (upper + lower) / 2
				dev = (upper - lower) / 2
				bb = (hist - middle) / dev
			except ValueError as err:
				print(err)
				time.sleep(5)
		if isdate(length):
			length = datetolength(length,bb)
		if length is None:
			length = len(bb)
		return bb[-length:]


	# Shows market trends by looking at the average gain and loss in the window.
	# Transformed from a scale of [0,100] to [-1,1]
	# RSI > 0.2 means overbought (sell indicator), RSI < -0.2 means oversold (buy indicator)
	def rsi(self, stock, length=1, window=20, datatype='close', interval='day'):
		hist = None
		while hist is None:
			try:
				hist = self.history(stock,interval=interval,length=length+window,datatype=datatype)
			except ValueError as err:
				print(err)			
				time.sleep(5)
		idx = hist.index
		r = momentum.rsi(pd.Series(np.array(hist)),n=window,fillna=False)
		r = (r - 50) / 50
		r.index = idx
		if isdate(length):
			length = datetolength(length,r)
		if length is None:
			length = len(r)
		return r[-length:]


	# Moving Average. matype = 0 means simple, matype = 1 means exponential
	# If data is given instead of a stock, then it will take the moving average of that
	def ma(self, stock, length=1, mawindow=12, matype=0, datatype='close', interval='day'):
		hist = None
		while hist is None:
			if isinstance(stock,str):
				try:
					hist = self.history(stock,interval=interval,length=length+mawindow,datatype=datatype)
				except ValueError as err:
					print(err)
					time.sleep(5)
			else:
				hist = stock
		if matype == 0:
			ma = volatility.bollinger_mavg(hist,n=mawindow,fillna=False)
		elif matype == 1:
			ma = trend.ema_indicator(hist,n=mawindow,fillna=False)
		if isdate(length):
			length = datetolength(length,ma)
		if length is None:
			length = len(ma)
		return ma[-length:]


	# The price compared to the low and the high within a window
	# Transformed from a scale of [0,100] to [-1,1]
	# STOCH > 0.3 means overbought (sell indicator), STOCH < -0.3 means oversold (buy indicator)
	def stoch(self, stock, length=1, window=14, interval='day'):
		s = None
		while s is None:
			try:
				high = self.history(stock,interval=interval,length=length+window,datatype="high")
				low = self.history(stock,interval=interval,length=length+window,datatype="low")
				close = self.history(stock,interval=interval,length=length+window,datatype="close")
				s = momentum.stoch(high=high,low=low,close=close,n=window,fillna=False)
				s = (s - 50) / 50
			except ValueError as err:
				print(err)
				time.sleep(5)
		if isdate(length):
			length = datetolength(length,s)
		if length is None:
			length = len(s)
		return s[-length:]


	# Returns the percent change
	# If data is given instead of a stock, it returns the percent change of that
	def percentchange(self, stock, length=1, datatype='close', interval='day'):
		# Get Data
		hist = None
		while hist is None:
			if isinstance(stock,str):
				try:
					hist = self.history(stock,interval=interval,length=length+1,datatype=datatype)
				except ValueError as err:
					print(err)
					time.sleep(5)
			else:
				hist = pd.Series(stock)
				length = len(hist)-1
		changes = 100 * hist.pct_change()
		changes = changes.rename("Percent Change")
		# Handle Length
		if isdate(length):
			length = datetolength(length,hist)
		elif length is None:
			length = len(hist)
		return changes[-length:]


	# The google trends for interest over time in a given query
	# interval: hour, day (changes to weekly if length is too long)
	# Returns Series of numbers from 0 to 100 for relative interest over time
	# WARNING: Data is for all days (other data is just trading days)
	def google(self, query, length=100, financial=True, interval='day'):
		enddate = self.datetime
		if isdate(length):
			startdate = length
		else:
			length += 1
		if interval == 'day':
			startdate = enddate - datetime.timedelta(days=length)
		elif interval == 'hour':
			startdate = enddate - datetime.timedelta(hours=length)
		if interval == 'day':
			startdate = startdate.strftime("%Y-%m-%d")
			enddate = enddate.strftime("%Y-%m-%d")
		elif interval == 'hour':
			startdate = startdate.strftime("%Y-%m-%dT%H")
			enddate = enddate.strftime("%Y-%m-%dT%H")
		category = 0
		if financial:
			category=1138
		pytrends.build_payload([query], cat=category, timeframe=startdate + " " + enddate, geo='US')
		return pytrends.interest_over_time()[query]


	# Send a string or a dictionary to an email or a phone number
	def notify(self, message="", recipient=""):
		# Dont send messages in backtesting
		if isinstance(self,Backtester):
			return
		# Send email to yourself by default
		if len(recipient) == 0:
			recipient = creds['Email Address']
		# Send current state of algorithm by default
		if len(message) == 0:
			exclude = {"times","chartminute","chartminutetimes","chartday","chartdaytimes","cache","stoplosses","stopgains","limitlow","limithigh"}
			message = {key: value for (key,value) in self.__dict__.items() if key not in exclude}
		if type(message) == dict:
			message = dict2string(message)
		gmail_user = creds['Email Address']
		gmail_password = creds['Email Password']
		# If recipient is an email address
		if "@" in recipient:
			try:
				server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
				server.ehlo()
				server.login(gmail_user, gmail_password)
				server.sendmail(gmail_user, recipient, message)
				server.close()
			except Exception as e:
				print(e, "Failed to send email notification")
		# If recipient is an phone number
		else:
			textdomains = ["@tmomail.net","@vtext.com","@mms.att.net","@pm.sprint.com"]
			try:
				server = smtplib.SMTP('smtp.gmail.com',587)
				server.starttls()
				server.login(gmail_user, gmail_password)
				for domain in textdomains:
					server.sendmail(gmail_user, recipient+domain, message)
				server.close()
			except Exception as e:
				print(e, "Failed to send sms notification")



# Use self.datetime to get current time (as a datetime object)
class Backtester(Algorithm):
	def __init__(self, capital=10000.0, benchmark='SPY'):
		super(Backtester, self).__init__()
		# Constants
		if self.times == ['every day']:
			self.logging = 'day'
		else:
			self.logging = 'minute'
		self.startingcapital = capital
		self.cash = capital
		self.timestorun = timestorun(self.times)
		self.exptime = 450
		# Variables that change automatically
		self.alpha = None
		self.beta = None
		self.volatility = None
		self.sharpe = None
		self.maxdrawdown = None
		# Variables that the user can change
		self.benchmark = benchmark


	# Starts the backtest (calls startbacktest in a new thread)
	# Times can be in the form of datetime objects or tuples (day,month,year)
	def start(self, start=datetime.datetime.today().date()-datetime.timedelta(days=90),
					end=datetime.datetime.today().date(), logging='day'):
		backtestthread = threading.Thread(target=self.startbacktest, args=(start, end, logging))
		backtestthread.start()


	# Starts the backtest
	def startbacktest(self, startdate=datetime.datetime.today().date()-datetime.timedelta(days=90),
							enddate=datetime.datetime.today().date(), logging='day'):
		if isinstance(startdate,str):
			startdate = tuple(startdate.split("-"))
		if isinstance(enddate,str):
			enddate = tuple(enddate.split("-"))
		if type(startdate) == tuple:
			startdate = datetime.date(startdate[0], startdate[1], startdate[2])
		if type(enddate) == tuple:
			enddate = datetime.date(enddate[0], enddate[1], enddate[2])
		days = tradingdays(start=startdate, end=enddate)
		self.logging = logging
		self.datetime = startdate
		self.update()
		for day in days:
			if self.logging == 'minute':
				for minute in range(391):
					# Set datetime of algorithm
					self.datetime = datetime.datetime.combine(day, datetime.time(9, 30)) + datetime.timedelta(minutes=minute)
					# Exit if that datetime is in the future
					if self.datetime >= self.getdatetime():
						break
					if minute in self.timestorun:
						# Update algorithm cash and value
						self.update()
						# Run algorithm
						self.run()
					# Log algorithm cash and value
					self.updatemin()
					# Check limit order thresholds
					for stock in self.stocks:
						self.checkthresholds(stock)
			elif self.logging == 'day':
				checkedthresholds = False
				for minute in sorted(self.timestorun):
					# Set datetime of algorithm
					self.datetime = datetime.datetime.combine(day, datetime.time(9, 30)) + datetime.timedelta(minutes=minute)
					# Exit if that datetime is in the future
					if self.datetime >= self.getdatetime():
						break
					# If algorithm is running at the end of the day, check thresholds before running it
					if self.datetime.time() == datetime.time(15,59):
						for stock in self.stocks:
							self.checkthresholds(stock)
						checkedthresholds = True
					# Update algorithm cash and value
					self.update()
					# Run algorithm
					self.run()
				# Check limit order thresholds if it hasn't already been done
				if not checkedthresholds:
					for stock in self.stocks:
						self.checkthresholds(stock)
				# Log algorithm cash and value
				self.datetime = datetime.datetime.combine(day, datetime.time(15, 59))
				self.updateday()
		self.riskmetrics()


	def updatemin(self):
		self.update()
		self.chartminute.append(self.value)
		self.chartminutetimes.append(self.datetime)


	def updateday(self):
		self.update()
		self.chartday.append(self.value)
		self.chartdaytimes.append(self.datetime)


	def update(self):
		stockvalue = 0
		for stock, amount in list(self.stocks.items()):
			if amount == 0:
				del self.stocks[stock]
			else:
				stockvalue += self.quote(stock) * amount
		self.value = self.cash + stockvalue
		self.value = round(self.value, 2)


	def checkthresholds(self,stock):
		# Enforce Thresholds
		if self.logging == 'minute': # Check if the current price activates a threshold
			price = self.quote(stock)
			alloc = self.cash / self.value
			if (stock in self.stocks) and (stock in self.stoplosses) and (price <= self.stoplosses[stock][0]):
				print("Stoploss for " + stock + " kicking in at $" + str(round(self.stoplosses[stock][0],2)))
				self.orderpercent(stock,self.stoplosses[stock][1],verbose=True)
				del self.stoplosses[stock]
			elif (stock in self.stocks) and (stock in self.stopgains) and (price >= self.stopgains[stock][0]):
				print("Stopgain for " + stock + " kicking in at $" + str(round(self.stopgains[stock][0],2)))
				self.orderpercent(stock,self.stopgains[stock][1],verbose=True)
				del self.stopgains[stock]
			elif (stock in self.limitlow) and (price <= self.limitlow[stock][0]):
				print("Limit order " + stock + " activated at $" + str(round(self.limitlow[stock][0],2)))
				self.orderpercent(stock,self.limitlow[stock][1],verbose=True)
				del self.limitlow[stock]
			elif (stock in self.limithigh) and (price >= self.limithigh[stock][0]):
				print("Limit order " + stock + " activated at $" + str(round(self.limithigh[stock][0],2)))
				self.orderpercent(stock,self.limithigh[stock][1],verbose=True)
				del self.limithigh[stock]
		else: # Check if the day's low or high activates a threshold
			if (stock in self.stocks) and (stock in self.stoplosses) and (self.history(stock,datatype='low')[0] <= self.stoplosses[stock][0]):
				print("Stoploss for " + stock + " kicking in at $" + str(round(self.stoplosses[stock][0],2)))
				self.orderpercent(stock, self.stoplosses[stock][1], cost=self.stoplosses[stock][0], verbose=True)
				del self.stoplosses[stock]
			elif (stock in self.stocks) and (stock in self.stopgains) and (self.history(stock,datatype='high')[0] >= self.stopgains[stock][0]):
				print("Stopgain for " + stock + " kicking in at $" + str(round(self.stopgains[stock][0],2)))
				self.orderpercent(stock, self.stopgains[stock][1], cost=self.stopgains[stock][0], verbose=True)
				del self.stoplosses[stock]
			elif (stock in self.limitlow) and (self.history(stock,datatype='low')[0] <= self.limitlow[stock][0]):
				print("Limit order " + stock + " activated at $" + str(round(self.limitlow[stock][0],2)))
				self.orderpercent(stock, self.limitlow[stock][1], cost=self.limitlow[stock][0], verbose=True)
				del self.limitlow[stock]
			elif (stock in self.limithigh) and (self.history(stock,datatype='high')[0] >= self.limithigh[stock][0]):
				print("Limit order " + stock + " activated at $" + str(round(self.limithigh[stock][0],2)))
				self.orderpercent(stock, self.limithigh[stock][1], cost=self.limithigh[stock][0], verbose=True)
				del self.limithigh[stock]


	def quote(self, stock):
		if self.datetime.time() <= datetime.time(9,30,0,0):
			return self.history(stock, interval='day', datatype='open')[0].item()
		elif self.datetime.time() >= datetime.time(15,59,0,0):
			return self.history(stock, interval='day', datatype='close')[0].item()
		return self.history(stock, interval=self.logging, datatype='close')[0].item()


	def history(self, stock, length=1, datatype='close', interval='day'):
		
		# Handle Cache
		key = (stock, interval)
		cache = self.cache.get(key)

		if cache is not None:

			hist, dateidx, lastidx, time = cache 

		if cache is None or (interval=='day' and (self.getdatetime()-time).days > 0) or (interval=='minute' and (self.getdatetime()-time).seconds > 120):

			hist = None
			
			while hist is None:

				# Convert to Datetime
				if isinstance(length,tuple):
					length = datetime.datetime(date[0],date[1],date[2])
				if isinstance(length,str):
					date = length.split("-")
					length = datetime.datetime(date[0],date[1],date[2])

				try:
					if broker == 'robinhood': # Data from AlphaVantage

						# Convert Datatype String
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

						# Get Daily or Intraday Data
						if interval == 'day':
							interval = 'daily'
							hist, _ = data.get_daily_adjusted(symbol=stock, outputsize='full')
						elif interval == 'minute':
							interval = '1min'
							hist, _ = data.get_intraday(symbol=stock, interval=interval, outputsize='full')

					elif broker == 'alpaca': # Data from Alpaca

						nextra = 100 if interval=='day' else 1 # Number of extra samples before the desired range
						end = self.getdatetime() + datetime.timedelta(days=2)
						if not isdate(length):
							if interval=='minute':
								start = datetime.datetime.strptime( api.get_calendar(end=(self.datetime+datetime.timedelta(days=1)).strftime("%Y-%m-%d"))[-1-(length//500)-nextra].date.strftime("%Y-%m-%d"), "%Y-%m-%d")
							else:	
								start = datetime.datetime.strptime( api.get_calendar(end=self.datetime.strftime("%Y-%m-%d"))[-length-nextra].date.strftime("%Y-%m-%d"), "%Y-%m-%d")
						else:
							start = length
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
					print(err)
					time.sleep(5)

			# Save To Cache
			dateidx = dateidxs(hist)
			lastidx = nearestidx(self.datetime, dateidx)
			self.cache[key] = [hist, dateidx, lastidx, self.getdatetime()]
		
		# Look for current datetime in cached data
		try:
			idx = nearestidx(self.datetime, dateidx, lastchecked=lastidx)
			if isdate(length):
				length = datetolength(length,dateidx,idx)
			# Convert length to int
			if length is None:
				length = len(hist)
			if idx-length+1 < 0:
				raise Exception('Cached data too short')
		except: # Happens if we request data farther back than before
			del self.cache[key]
			return self.history(stock, interval=interval, length=length, datatype=datatype)
		self.cache[key][2] = idx
		
		
		return hist[datatype][idx-length+1 : idx+1]
		

	def order(self, stock, amount, cost=None, ordertype="market", stop=None, limit=None, verbose=False, notify_address=None):
		# Guard condition for sell
		if amount < 0 and (stock in self.stocks) and (-amount > self.stocks[stock]):
			print(("Warning: attempting to sell more shares (" + str(amount) + ") than are owned (" + 
				str(self.stocks.get(stock,0)) + ") of " + stock))
			return None
		if cost is None:
			cost = self.quote(stock)
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
				print("You need to specify a stop or limit price")
			price = limit if (limit is not None) else stop
			change = (price - cost) / cost
			perc = (self.stocks.get(stock,0) + amount) * cost / self.value
			if amount > 0:
				self.limitbuy(stock, change, perc)
			else:
				self.stopsell(stock, change, perc)
		# TODO: Test stop/limit orders in backtest.


	def orderpercent(self, stock, percent, cost=None, ordertype="market", stop=None, limit=None, verbose=False, notify_address=None):
		if cost is None:
			cost = self.quote(stock)
		currentpercent = self.stocks.get(stock,0) * cost / self.value
		percentdiff = percent - currentpercent
		if percentdiff < 0:
			# Min of (# required to reach target percent) and (# of that stock owned)
			amount = min( round(-percentdiff * self.value / cost), self.stocks.get(stock,0) )
			return self.order(stock=stock, amount=-amount, cost=cost, \
							  ordertype=ordertype, stop=stop, limit=limit, \
							  verbose=verbose, notify_address=notify_address)
		else:
			# Min of (# required to reach target percent) and (# that you can buy with your available cash)
			amount = min( math.floor(percentdiff * self.value / cost), math.floor(self.cash / cost) )
			return self.order(stock=stock, amount=amount, cost=cost, \
							  ordertype=ordertype, stop=stop, limit=limit, \
							  verbose=verbose, notify_address=notify_address)



### Helper Functions ###


# If start and end are both dates, it returns a list of trading days from the start date to the end date (not including end date)
# If start is a date and end is an int, it returns the date that is end days after start
# If start is an int and end is a date, it returns the date that is start days before end
def tradingdays(start=datetime.datetime.today().date(), end=1):

	# Convert Date Datatypes
	if isinstance(start,str):
		start = tuple(start.split("-"))
	if isinstance(end,str):
		end = tuple(end.split("-"))
	if type(start) == tuple:
		start = datetime.date(start[0], start[1], start[2])
	if type(end) == tuple:
		end = datetime.date(end[0], end[1], end[2])

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


def isdate(var):
	return isinstance(var,datetime.datetime) or isinstance(var,datetime.date)


def timestorun(times):
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


# Returns the list of datetime objects associated with the entries of a pandas dataframe
def dateidxs(arr):
	try:
		return [pd.to_datetime(item[0]).replace(tzinfo=None).to_pydatetime() for item in arr.iterrows()]
	except:
		return [pd.to_datetime(item[0]).replace(tzinfo=None).to_pydatetime() for item in arr.iteritems()]


# Returns the index of the nearest element in dateidxs that occured before (or at the same time) as time.
# If lastchecked==None: Searches backward from the most recent entries
# If lastchecked>=0: Searches forward starting at lastchecked
# If lastchecked<0: Searches backward starting at -lastchecked
def nearestidx(time, dateidx, lastchecked=None):
	if lastchecked is None:
		for i in range(len(dateidx)):
			index = len(dateidx) - i - 1
			if dateidx[index] <= time:
				return index
	elif lastchecked >= 0:
		for i in range(len(dateidx)):
			index = (lastchecked + i - 5) % len(dateidx)
			if dateidx[index] > time:
				return index-1
		return len(dateidx)-1
	else:
		for i in range(len(dateidx)):
			index = (len(dateidx) - lastchecked - i) % len(dateidx)
			if dateidx[index] <= time:
				return index
	raise Exception("Datetime " + str(time) + " not found in historical data.")


# Returns the difference of the indexes of startdate and currentdateidx in dateidxs
# startdate: datetime in the past
# currentdateidx: idx of current date in dateidxs (datetime also accepted) (If None given, it will default to the last value)
# dateidx: list of datetimes (original pandas dataframe also accepted)
def datetolength(startdate, dateidx, currentdateidx=None):
	if isinstance(dateidx,pd.DataFrame) or isinstance(dateidx,pd.Series):
		dateidx = dateidxs(dateidx)
	if isdate(currentdateidx):
		currentdateidx = nearestidx(currentdateidx, dateidx)
	if currentdateidx is None:
		currentdateidx = len(dateidx)-1
	return currentdateidx - nearestidx(startdate, dateidx, lastchecked=-currentdateidx) + 1


# Converts a dictionary to a string
def dict2string(dictionary, spaces=0):
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


def save_algo(algo_obj,path=None):
	if path is None:
		path = algo_obj.__class__.__name__ + "_save"
	fh = open(path,'w')
	json.dump(algo_obj,fh)
	fh.close()
	return path


def load_algo(path):
	fh = open(path,'rb')
	algo = json.load(fh)
	fh.close()
	return algo


### Wrappers for Broker-Related Functions ###


def backtester(algo, capital=None, benchmark=None):
	# Convert
	BacktestAlgorithm = type('BacktestAlgorithm', (Backtester,), dict((algo.__class__).__dict__))
	algoback = BacktestAlgorithm()
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
# ordertype: "market", "limit", "stop", "stop_limit"
def buy(stock, amount, ordertype='market', stop=None, limit=None):
	if broker == 'robinhood':
		stockobj = robinhood.instruments(stock)[0]
		try:
			response = robinhood.place_buy_order(stockobj, amount)
			return response
		except Exception as e:
			print("Buy Order Failed. Are there other orders? Is there enough cash?", e)
	elif broker == 'alpaca':
		api.submit_order(stock, amount, 'buy', ordertype, 'day', limit_price=limit, stop_price=stop)


# Input: stock symbol as a string, number of shares as an int
# ordertype: "market", "limit", "stop", "stop_limit"
def sell(stock, amount, ordertype='market', stop=None, limit=None):
	if broker == 'robinhood':
		stockobj = robinhood.instruments(stock)[0]
		try:
			response = robinhood.place_sell_order(stockobj, abs(amount))
			return response
		except Exception as e:
			print("Sell Order Failed.", e)
	elif broker == 'alpaca':
		api.submit_order(stock, amount, 'sell', ordertype, 'day', limit_price=limit, stop_price=stop)


# Input: stock symbol as a string
# Returns: share price as a float
def price(stock):
	if broker == 'robinhood':
		for i in range(10):
			try:
				return float(robinhood.quote_data(stock)['last_trade_price'])
			except Exception as e:
				if i == 0:
					print("Could not fetch Robinhood quote for " + stock + ".", e)
				time.sleep(0.3*i)
	elif broker == 'alpaca':
		cost = float(api.polygon.last_quote(stock).askprice)
		if cost == 0:
			cost = float(api.polygon.last_trade(stock).price)
		return cost


# Returns: list of ("symbol",amount)
def positions():
	
	positions = {}
	
	if broker == 'robinhood':
		for i in range(10):
			try:
				robinhoodpositions = robinhood.positions()['results']
				for position in robinhoodpositions:
					name = str(requests.get(position['instrument']).json()['symbol'])
					amount = float(position['quantity'])
					if amount != 0:
						positions[name] = amount
				break
			except Exception as e:
				if i == 0:
					print("Could not fetch Robinhood positions data.", e)
				time.sleep(0.3*i)
	
	elif broker == 'alpaca':
		poslist = api.list_positions()
		for pos in poslist:
			positions[pos.symbol] = int(pos.qty)
	
	return positions


# Returns dictionary of
	# "value": total portfolio value as a float
	# "cash": portfolio cash as a float
	# "daychange": current day's percent portfolio value change as a float
def portfoliodata():
	
	portfolio = {}

	if broker == 'robinhood':
		for i in range(10):
			try:
				robinhoodportfolio = robinhood.portfolios()
				break
			except Exception as e:
				print("Could not fetch Robinhood portfolio data.", e)
				time.sleep(0.3*i)
		if robinhoodportfolio['extended_hours_equity'] is not None:
			portfolio["value"] = float(robinhoodportfolio['extended_hours_equity'])
		else:
			portfolio["value"] = float(robinhoodportfolio['equity'])
		if robinhoodportfolio['extended_hours_market_value'] is not None:
			portfolio["cash"] = portfolio["value"] - float(robinhoodportfolio['extended_hours_market_value'])
		else:
			portfolio["cash"] = portfolio["value"] - float(robinhoodportfolio['market_value'])
		
	elif broker == 'alpaca':
		account = api.get_account()
		portfolio["value"] = float(account.portfolio_value)
		portfolio["cash"] = float(account.buying_power)
	
	portfolio["value"] = round(portfolio["value"],2)
	portfolio["cash"] = round(portfolio["cash"],2)
	return portfolio



