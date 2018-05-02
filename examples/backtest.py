from trader.AlgoManager import *
from rnnalgo import *

if __name__ == '__main__':
	algo = RNN(times=['every day'])
	start = datetime.now() - timedelta(days=60)
	algoback = backtester(algo,capital=1000)
	Manager.algogui(algoback)
	algoback.startbacktest(startdate=(start.day,start.month,start.year))
	import code; code.interact(local=locals())
