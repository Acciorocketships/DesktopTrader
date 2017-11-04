import AlgoManager as AM
import code
import datetime

class Manual(AM.Algorithm):

	def initialize(self):
		self.macdval = None
		self.benchmark = "QQQ"

	def run(self):
		self.macdval = self.macd(stock='QQQ',interval='daily',fastmawindow=12,slowmawindow=26,signalmawindow=9)['macd hist'][0]
		if self.macdval > 0:
			self.orderpercent('QQQ',1)
		elif self.macdval < 0:
			self.orderpercent('QQQ',0)


class Manual2(AM.Algorithm):

	def run(self):
		self.orderpercent('QQQ',1)

if __name__ == '__main__':
	algo = Manual(times=['every day'])
	algoback = AM.backtester(algo)
	algoback.start(startdate=(1,1,2006),sleeptime=0.0)
	algoback.gui()