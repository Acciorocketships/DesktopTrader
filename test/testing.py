from trader.AlgoManager import *
from trader.Algorithm import *
import code
import datetime


class Test(Algorithm):
	def initialize(self):
		pass

	def run(self):
		pass

if __name__ == '__main__':
	algo = Test(times=['every day'])
	code.interact(local=locals())
