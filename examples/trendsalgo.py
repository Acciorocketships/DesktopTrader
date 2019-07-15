from trader.AlgoManager import *
from trader.Algorithm import *

class TrendsAlgo(Algorithm):

	def initialize(self):
		self.stock = "SPY"

	def run(self):
		try:
			iscrashing = self.google("market crash", length=365*5)[-1] > 15
		except Exception as err:
			print(err)
			return
		if iscrashing:
			self.orderfraction(self.stock, 0, verbose=True)
		else:
			self.orderfraction(self.stock, 1, verbose=True)

def backtest():
	trendsalgo = backtester(TrendsAlgo(times='every day'))
	trendsalgo.benchmark = ["SPY"]
	trendsalgo.start(start=(2018,9,1), end=(2019,2,1))
	Manager.algogui(trendsalgo)

if __name__ == '__main__':
	backtest()