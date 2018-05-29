from trader.AlgoManager import *
from rnnalgo import *

if __name__ == '__main__':
	rnnalgo = RNN(times='every day')
	manager = Manager()
	manager.assignstocks('all',rnnalgo)
	manager.add(rnnalgo,allocation=1)
	manager.rebalance()
	manager.start()
	manager.interactive(vars=locals())
