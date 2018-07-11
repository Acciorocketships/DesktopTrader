import os, sys
import traceback
import pkg_resources
import datetime
from pytz import timezone
import time
import threading
import pickle
from Robinhood import Robinhood
from alpha_vantage.timeseries import TimeSeries
from alpha_vantage.techindicators import TechIndicators
import pandas as pd
import numpy as np
from empyrical import max_drawdown, alpha_beta, annual_volatility, sharpe_ratio
import math
import requests
import smtplib

import trader.tradingdays as tradingdays
from pytrends.request import TrendReq

# This is a hack, needs refactored into proper class
# https://github.com/RomelTorres/alpha_vantage
# https://github.com/Jamonek/Robinhood

broker = 'robinhood'

creds = []
credential_file = pkg_resources.resource_filename(__name__, "creds.txt")
try:
	with open(credential_file, "r") as f:
		creds = f.readlines()
except IOError:
	creds.append(input('Robinhood Username: '))
	creds.append(input('Robinhood Password: '))
	creds.append(input('Alpha Vantage API Key: '))
	email_address = input('Email Address: ')
	if '@' in email_address:
		creds.append(email_address)
		creds.append(input('Email Password: '))
	else:
		creds.append("None")
		creds.append("None")
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

	def runalgo(self):
		try:
			self.run()
		except Exception as err:
			exc_type, exc_obj, exc_tb = sys.exc_info()
			if exc_tb.tb_lineno != 99:
				fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
				print(err)
				print(exc_type, fname, exc_tb.tb_lineno)
			# traceback.print_stack()

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
		if len(changes) > 0:
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
	def order(self, stock, amount, verbose=False, notify_address=None):
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
			# Send order  
			if amount > 0:
				buy(stock, amount)
			elif amount < 0:
				sell(stock, abs(amount))
			# Block for 5 minutes. If order still hasn't filled, continue.
			for i in range(273):
				newamount = positions().get(stock,0)
				if newamount != currentamount:
					break
				else:
					time.sleep(0.1*(i ** 0.5))
			# If order didn't go through, return.
			if (newamount - currentamount) == 0:
				print("Order for " + str(amount) + " shares of " + stock + " did not fill in time. Continuing.")
				return
			# Update algo
			newcash = portfoliodata()["cash"]
			self.cash += (newcash - currentcash)
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
				print( "Buying " + str(amount) + " shares of " + stock + " at $" + str(cost))
			elif amount < 0:
				print( "Selling " + str(-amount) + " shares of " + stock + " at $" + str(cost))

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
			# Min of (# required to reach target percent) and (# that you can buy with 95% of your available cash)
			amount = min( math.floor(percentdiff * self.value / cost), math.floor(0.95 * self.cash / cost) )
			return self.order(stock, amount, verbose, notify_address)

	# Sells all held stocks
	def sellall(self, verbose=False, notify_address=None):
		for stock in self.stocks:
			self.orderpercent(stock, 0, verbose=verbose, notify_address=None)

	# Returns a list of symbols for high-volume stocks tradable on Robinhood
	def symbols(self):
		import simplejson
		symbolstxt = pkg_resources.resource_filename(__name__, 'symbols.txt')
		with open(symbolstxt, 'r') as f:
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
		md = None
		while md is None:
			try:
				md, _ = tech.get_macdext(stock, interval=interval, \
								 fastperiod=fastmawindow, slowperiod=slowmawindow, signalperiod=signalmawindow, \
								 fastmatype=fastmatype, slowmatype=slowmatype, signalmatype=signalmatype, \
								 series_type='open')
			except ValueError as err:
				print(err)
				time.sleep(5)
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
		bb = None
		while bb is None:
			try:
				bb, _ = tech.get_bbands(stock, interval=interval, nbdevup=nbdevup, nbdevdn=nbdevdn, matype=matype,
								time_period=mawindow, series_type='open')
			except ValueError as err:
				print(err)
				time.sleep(5)
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
		r = None
		while r is None:
			try:
				r, _ = tech.get_rsi(stock, interval=interval, time_period=mawindow, series_type='open')
			except ValueError as err:
				print(err)
				time.sleep(5)
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
		ma = None
		while ma is None:
			try:
				ma, _ = tech.get_sma(stock, interval=interval, time_period=mawindow, series_type='open')
			except ValueError as err:
				print(err)
				time.sleep(5)
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
		ma = None
		while ma is None:
			try:
				ma, _ = tech.get_ema(stock, interval=interval, time_period=mawindow, series_type='open')
			except ValueError as err:
				print(err)
				time.sleep(5)
		if isinstance(length,datetime.datetime):
			length = self.datetolength(length,ma)
		if length is None:
			length = len(ma)
		return ma["EMA"][-length:]

	# Returns dataframe with "SlowD" and "SlowK"
	def stoch(self, stock, interval='daily', length=1, fastkperiod=12, 
				slowkperiod=26, slowdperiod=26, slowkmatype=0, slowdmatype=0):
		s = None
		while s is None:
			try:
				s = tech.get_stoch(stock, interval=interval, fastkperiod=fastkperiod,
						slowkperiod=slowkperiod, slowdperiod=slowdperiod, slowkmatype=slowkmatype, slowdmatype=slowdmatype, \
						series_type='open')
			except ValueError as err:
				print(err)
				time.sleep(5)
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
		prices = None
		while prices is None:
			try:
				if interval == 'daily':
					prices, _ = data.get_daily_adjusted(symbol=stock, outputsize=size)
				else:
					prices, _ = data.get_intraday(symbol=stock, interval=interval, outputsize=size)
			except ValueError as err:
				print(err)
				time.sleep(5)
		changes = prices[datatype].pct_change()
		changes = changes.rename("Percent Change from Previous Day")
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


	# Send a string or a dictionary to an email or a phone number
	def notify(self, message="", recipient=""):
		# Send email to yourself by default
		if len(recipient) == 0:
			recipient = creds[3]
		# Send current state of algorithm by default
		if len(message) == 0:
			exclude = {"times","chartminute","chartminutetimes","chartday","chartdaytimes","cache","stoplosses","stopgains","limitlow","limithigh"}
			message = {key: value for (key,value) in self.__dict__.items() if key not in exclude}
		if type(message) == dict:
			message = self.dict2string(message)
		gmail_user = creds[3]
		gmail_password = creds[4]
		# If recipient is an email address
		if "@" in recipient:
			try:
				server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
				server.ehlo()
				server.login(gmail_user, gmail_password)
				server.sendmail(gmail_user, recipient, message)
				server.close()
			except:
				print("Failed to send email notification")
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



	# Converts a dictionary to a string
	def dict2string(self, dictionary, spaces=0):
		string = ""
		if type(dictionary) == dict:
			for (key,value) in dictionary.items():
				if type(value) != dict and type(value) != list:
					string += (" " * spaces*4) + str(key) + " - " + str(value) + "\n"
				else:
					string += (" " * spaces*4) + str(key) + " - \n"
					string += self.dict2string(value,spaces+1)
		elif type(dictionary) == list:
			for item in dictionary:
				string += self.dict2string(item,spaces+1)
		else:
			string += (" " * spaces*4) + str(dictionary) + "\n"
		return string


	def nexttradingday(self,startdate=datetime.datetime.today().date()+datetime.timedelta(days=1),count=1):
		return list(tradingdays.NYSE_tradingdays(a=startdate,count=count))




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
	def start(self, startdate=datetime.datetime.today().date()-datetime.timedelta(days=12),
					enddate=datetime.datetime.today().date()):
		backtestthread = threading.Thread(target=self.startbacktest, args=(startdate, enddate))
		backtestthread.start()

	# Starts the backtest
	def startbacktest(self, startdate=datetime.datetime.today().date()-datetime.timedelta(days=12),
							enddate=datetime.datetime.today().date()):
		if type(startdate) == tuple:
			startdate = datetime.date(startdate[2], startdate[1], startdate[0])
		if type(enddate) == tuple:
			enddate = datetime.date(enddate[2], enddate[1], enddate[0])
		if (datetime.datetime.today().date() - startdate) <= datetime.timedelta(days=12):
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
					if self.datetime >= self.getdatetime():
						break
					self.updatemin()
					if minute in self.times:
						self.update()
						self.run()
			elif self.logging == 'daily':
				self.datetime = datetime.datetime.combine(day, datetime.time(9, 30))
				self.minutesago = 391 * self.daysago
				if self.datetime >= self.getdatetime():
					break
				self.updatemin()
				self.update()
				self.run()
		self.riskmetrics()

	def updatemin(self):
		for stock in (self.stopgains.keys() | self.stoplosses.keys()):
			self.checkthresholds(stock)
		stockvalue = 0
		for stock, amount in list(self.stocks.items()):
			if amount == 0:
				del self.stocks[stock]
				continue
			stockvalue += self.quote(stock) * amount
		self.value = self.cash + stockvalue
		self.value = round(self.value, 2)
		self.chartminute.append(self.value)
		self.chartminutetimes.append(self.datetime)

	def update(self):
		stockvalue = 0
		for stock, amount in list(self.stocks.items()):
			if amount == 0:
				del self.stocks[stock]
				continue
			stockvalue += self.quote(stock) * amount
		self.value = self.cash + stockvalue
		self.value = round(self.value, 2)
		self.chartday.append(self.value)
		self.chartdaytimes.append(self.datetime)

	def checkthresholds(self,stock):
		if self.logging == '1min':
			price = self.quote(stock)
			alloc = self.cash / self.value
			if (stock in self.stocks) and (stock in self.stoplosses) and (price <= self.stoplosses[stock]):
				print("Stoploss for " + stock + " kicking in at $" + str(round(self.stoplosses[stock],2)))
				del self.stoplosses[stock]
				self.orderpercent(stock,0,verbose=True)
			elif (stock in self.stocks) and (stock in self.stopgains) and (price >= self.stopgains[stock]):
				print("Stopgain for " + stock + " kicking in at $" + str(round(self.stopgains[stock],2)))
				del self.stopgains[stock]
				self.orderpercent(stock,0,verbose=True)
			elif (stock in self.limitlow) and (price <= self.limitlow[stock]):
				print("Limit order " + stock + " activated at $" + str(round(self.limitlow[stock],2)))
				del self.limitlow[stock]
				self.orderpercent(stock,alloc,verbose=True)
			elif (stock in self.limithigh) and (price >= self.limithigh[stock]):
				print("Limit order " + stock + " activated at $" + str(round(self.limithigh[stock],2)))
				del self.limithigh[stock]
				self.orderpercent(stock,alloc,verbose=True)
		else:
			if (stock in self.stocks) and (stock in self.stoplosses) and (self.history(stock,datatype='3. low')[0] <= self.stoplosses[stock]):
				amount = self.stocks[stock]
				self.stocks[stock] = 0
				self.cash += self.stoplosses[stock] * amount
				print("Stoploss for " + stock + " kicking in at $" + str(round(self.stoplosses[stock],2)))
				print("Selling " + str(amount) + " shares of " + stock + " at $" + str(round(self.stoplosses[stock],2)))
				del self.stoplosses[stock]
			elif (stock in self.stocks) and (stock in self.stopgains) and (self.history(stock,datatype='2. high')[0] >= self.stopgains[stock]):
				amount = self.stocks[stock]
				self.stocks[stock] = 0
				self.cash += self.stopgains[stock] * amount
				print("Stopgain for " + stock + " kicking in at $" + str(round(self.stopgains[stock],2)))
				print("Selling " + str(amount) + " shares of " + stock + " at $" + str(round(self.stopgains[stock],2)))
				del self.stoplosses[stock]
			elif (stock in self.limitlow) and (self.history(stock,datatype='3. low')[0] <= self.limitlow[stock]):
				self.stocks[stock] = math.floor(self.cash / self.limitlow[stock])
				self.cash -= self.stocks[stock] * self.limitlow[stock]
				print("Limit order " + stock + " activated at $" + str(round(self.limitlow[stock],2)))
				print("Buying " + str(self.stocks[stock]) + " shares of " + stock + " at $" + str(round(self.limitlow[stock],2)))
				del self.limitlow[stock]
			elif (stock in self.limithigh) and (self.history(stock,datatype='2. high')[0] >= self.limithigh[stock]):
				self.stocks[stock] = math.floor(self.cash / self.limithigh[stock])
				self.cash -= self.stocks[stock] * self.limithigh[stock]
				print("Limit order " + stock + " activated at $" + str(round(self.limithigh[stock],2)))
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
		if (cache is None) or (self.getdatetime() > exp):
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
			self.cache[key] = [hist, self.getdatetime() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
		idx = self.nearestidx(self.datetime, dateidxs, lastchecked=lastidx)
		self.cache[key][3] = idx
		if isinstance(length,datetime.datetime):
			# TODO: make sure dates work
			length = self.datetolength(length,dateidxs,idx)
		if length is None:
			length = idx
		return hist[datatype][idx-length+1 : idx+1]
		

	def order(self, stock, amount, verbose=False, notify_address=None):
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
				print( "Selling " + str(-amount) + " shares of " + stock + " at $" + str(cost))

	def orderpercent(self, stock, percent, verbose=False, notify_address=None):
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
		if (cache is None) or (self.getdatetime() > exp):
			md = None
			while md is None:
				try:
					md, _ = tech.get_macdext(stock, interval=interval, \
						fastperiod=fastmawindow, slowperiod=slowmawindow, signalperiod=signalmawindow, \
						fastmatype=fastmatype, slowmatype=slowmatype, signalmatype=signalmatype, \
						series_type='open')
				except ValueError as err:
					print(err)
					time.sleep(5)
			dateidxs = self.dateidxs(md)
			lastidx = self.nearestidx(self.datetime, dateidxs)
			self.cache[key] = [md, self.getdatetime() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
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
		if (cache is None) or (self.getdatetime() > exp):
			bb = None
			while bb is None:
				try:
					bb, _ = tech.get_bbands(stock, interval=interval, nbdevup=nbdevup, nbdevdn=nbdevdn, matype=matype,
									time_period=mawindow, series_type='open')
				except ValueError as err:
					print(err)
					time.sleep(5)
			dateidxs = self.dateidxs(bb)
			lastidx = self.nearestidx(self.datetime, dateidxs)
			self.cache[key] = [bb, self.getdatetime() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
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
		if (cache is None) or (self.getdatetime() > exp): 
			r = None
			while r is None:
				try:
					r, _ = tech.get_rsi(stock, interval=interval, time_period=mawindow, series_type='open')
				except ValueError as err:
					print(err)
					time.sleep(5)
			dateidxs = self.dateidxs(r)
			lastidx = self.nearestidx(self.datetime, dateidxs)
			self.cache[key] = [r, self.getdatetime() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
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
		if (cache is None) or (self.getdatetime() > exp):
			ma = None
			while ma is None:
				try:
					ma, _ = tech.get_sma(stock, interval=interval, time_period=mawindow, series_type='open')
				except ValueError as err:
					print(err)
					time.sleep(5)
			dateidxs = self.dateidxs(ma)
			lastidx = self.nearestidx(self.datetime, dateidxs)
			self.cache[key] = [ma, self.getdatetime() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
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
		if (cache is None) or (self.getdatetime() > exp):
			ma = None
			while ma is None:
				try:
					ma, _ = tech.get_ema(stock, interval=interval, time_period=mawindow, series_type='open')
				except ValueError as err:
					print(err)
					time.sleep(5)
			dateidxs = self.dateidxs(ma)
			lastidx = self.nearestidx(self.datetime, dateidxs)
			self.cache[key] = [ma, self.getdatetime() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
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
		if (cache is None) or (self.getdatetime() > exp):
			s = None
			while s is None:
				try:
					s, _ = tech.get_stoch(stock, interval=interval, fastkperiod=fastkperiod,
						slowkperiod=slowkperiod, slowdperiod=slowdperiod, slowkmatype=slowkmatype, slowdmatype=slowdmatype, \
						series_type='open')
				except ValueError as err:
					print(err)
					time.sleep(5)
			dateidxs = self.dateidxs(s)
			lastidx = self.nearestidx(self.datetime, dateidxs)
			self.cache[key] = [s, self.getdatetime() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
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
		if (cache is None) or (self.getdatetime() > exp):
			prices = None
			while prices is None:
				try:
					if interval == 'daily':
						prices, _ = data.get_daily_adjusted(symbol=stock, outputsize='full')
					else:
						prices, _ = data.get_intraday(symbol=stock, interval=interval, outputsize='full')
				except ValueError as err:
					print(err)
					time.sleep(5)
			changes = prices[datatype].pct_change()
			changes = changes.rename("Percent Change from Previous Day")
			dateidxs = self.dateidxs(prices[1:])
			lastidx = self.nearestidx(self.datetime, dateidxs)
			self.cache[key] = [changes, self.getdatetime() + datetime.timedelta(minutes = self.exptime), dateidxs, lastidx]
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
		try:
			response = robinhood.place_buy_order(stockobj, amount)
			return response
		except Exception as e:
			print("Buy Order Failed. Are there other orders? Is there enough cash?", e)

# Input: stock symbol as a string, number of shares as an int
def sell(stock, amount):
	if broker == 'robinhood':
		stockobj = robinhood.instruments(stock)[0]
		try:
			response = robinhood.place_sell_order(stockobj, abs(amount))
			return response
		except Exception as e:
			print("Sell Order Failed.", e)

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

# Returns: list of ("symbol",amount)
def positions():
	positions = {}
	if broker == 'robinhood':
		for i in range(10):
			try:
				robinhoodpositions = robinhood.positions()['results']
				break
			except Exception as e:
				if i == 0:
					print("Could not fetch Robinhood positions data.", e)
				time.sleep(0.3*i)
		for position in robinhoodpositions:
			name = str(requests.get(position['instrument']).json()['symbol'])
			amount = float(position['quantity'])
			if amount != 0:
				positions[name] = amount
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
		portfolio["day change"] = (portfolio["value"] - float(robinhoodportfolio['adjusted_equity_previous_close'])) / \
														float(robinhoodportfolio['adjusted_equity_previous_close'])
	portfolio["value"] = round(portfolio["value"],2)
	portfolio["cash"] = round(portfolio["cash"],2)
	portfolio["day change"] = round(portfolio["day change"],2)
	return portfolio


def save_algo(algo_obj,path=None):
	if path is None:
		path = algo_obj.__class__.__name__ + "_save"
	fh = open(path,'wb')
	pickle.dump(algo_obj,path)
	return path

def load_algo(path):
	fh = open(path,'rb')
	algo = pickle.load(fh)
	return algo



