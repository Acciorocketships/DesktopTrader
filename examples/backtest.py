from trader.AlgoManager import *
from yavois import *

if __name__ == '__main__':
	algo = Yavois()
	start = datetime.datetime.now() - datetime.timedelta(days=60)
	algoback = backtester(algo,capital=1000)
	#Manager.algogui(algoback)
	#algoback.startbacktest(startdate=(start.day,start.month,start.year))
	import code; code.interact(local=locals())
