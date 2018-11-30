from trader.AlgoManager import *
from trader.Algorithm import *
import code
import datetime


class Test(Algorithm):
	def initialize(self):
		pass

	def run(self):
		val = self.macd("SPY",interval='day',length=1)[0]
		print(val)



def runback():
	algo = backtester(Test(times=['every day']))
	algo.startbacktest((2018,1,2),(2018,1,3))

def runlive():
	algo = Test(times=['every day'])
	algo.run()

if __name__ == '__main__':
	runback()
