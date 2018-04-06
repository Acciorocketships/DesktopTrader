from AlgoManager import *
from yavois import *

if __name__ == '__main__':
	volalgo = Yavois()
	rnnalgo = RNN()
	manager = Manager()
	manager.add(volalgo,allocation=0.5)
	manager.assignstocks('all',volalgo)
	manager.add(rnnalgo,allocation=0.5)
	manager.rebalance()
	manager.start()
	manager.interactive(vars=locals())
