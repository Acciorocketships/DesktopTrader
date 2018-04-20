from trader.AlgoManager import *
from rnnalgo import *

if __name__ == '__main__':
	rnnalgo = RNN(times=[(9,35)])
	manager = Manager()
	#manager.assignstocks('all',rnnalgo)
	manager.add(rnnalgo,allocation=0.25)
	manager.rebalance()
	manager.start()
	manager.interactive(vars=locals())
