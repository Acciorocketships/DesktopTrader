from trader.AlgoManager import *
from trader.Algorithm import *
import datetime
import logging

class Yavois(Algorithm):

	def initialize(self):
		self.nextdaybuy = False
		self.nextdaysell = False
		self.rsi2thres = 0.5
		self.rsi7thres = -0.5
		self.long = "SVXY"
		self.hideout = None
		self.takegain = 0.05
		self.takeloss = -0.02
		self.rsi2 = None
		self.rsi7 = None

	def run(self):

		if self.algodatetime().time() < datetime.time(12,0,0,0):

			logging.info("Running Morning. nextdaybuy: %s, nextdaysell: %s, \nrsi2: %s, \nrsi7: %s",
						 self.nextdaybuy, self.nextdaysell, self.rsi2, self.rsi7)

			if self.nextdaybuy:
				self.nextdaybuy = False
				if self.hideout is not None:
					self.orderfraction(self.hideout,0,notify_address='acciorocketships@gmail.com')
				self.orderfraction(self.long,1,verbose=True,notify_address='acciorocketships@gmail.com')
				self.stopsell(self.long,self.takegain)
				self.stopsell(self.long,self.takeloss)
				return

			if self.nextdaysell:
				self.nextdaysell = False
				self.orderfraction(self.long,0,verbose=True,notify_address='acciorocketships@gmail.com')
				if self.hideout is not None:
					self.orderfraction(self.hideout,1,verbose=True,notify_address='acciorocketships@gmail.com')
				return

		else:

			self.rsi2 = self.rsi(self.long,window=2,length=2)
			self.rsi7 = self.rsi(self.long,window=7,length=2)

			logging.info("Running Afternoon. nextdaybuy: %s, nextdaysell: %s, \nrsi2: %s, \nrsi7: %s",
						 self.nextdaybuy, self.nextdaysell, self.rsi2, self.rsi7)

			# If RSI7 crosses its threshold and no current position/order, buy now
			if self.rsi7[-1] > self.rsi7thres and self.rsi7[-2] < self.rsi7thres and \
			   (self.long not in self.stocks or self.stocks[self.long]==0):
				print("RSI7 Threshold, Buy Now")
				if self.hideout is not None:
					self.orderfraction(self.hideout,0,notify_address='acciorocketships@gmail.com')
				self.orderfraction(self.long,1,verbose=True,notify_address='acciorocketships@gmail.com')
				self.stopsell(self.long,self.takegain)
				self.stopsell(self.long,self.takeloss)
				return

			# If RSI2 crosses its threshold and no current position/order, buy tomorrow
			if self.rsi2[-1] > self.rsi2thres and self.rsi2[-2] < self.rsi2thres and \
			   (self.long not in self.stocks or self.stocks[self.long]==0):
				print("RSI2 Threshold, Buy Tomorrow")
				self.nextdaybuy = True
				return

			# If there are currently positions, sell tomorrow
			if (self.long in self.stocks and self.stocks[self.long]>0):
				print("Currently Holding Stocks, Sell Tomorrow")
				self.nextdaysell = True
				return

		

def backtest():
	algo = Yavois(schedule = ["0 9 * * MON-FRI", "59 15 * * MON-FRI"])
	algoback = backtester(algo,capital=1000)
	algoback.benchmark = ["SPY", "SVXY"]
	algoback.backtest(start=(2019,1,1))
	Manager.algogui(algoback)


def run():
	manager = Manager()
	algo = Yavois(schedule = ["0 9 * * MON-FRI", "59 15 * * MON-FRI"])
	manager.add(algo,allocation=1)
	manager.start()
	manager.interactive(vars=locals())


if __name__ == '__main__':
	backtest()

