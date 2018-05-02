from trader.AlgoManager import *
from rnnalgo import *

if __name__ == '__main__':
	rnnalgo = RNN(times=['every minute'])
	rnnalgo.papertrade(cash=500)
	manager = Manager()
	manager.add(rnnalgo,allocation=1)
	manager.rebalance()
	manager.start()
	manager.interactive(vars=locals())
