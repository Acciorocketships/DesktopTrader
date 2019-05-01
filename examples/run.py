from trader.AlgoManager import *
from yavois import *

if __name__ == '__main__':
	algo = Yavois()
	manager = Manager()
	manager.assignstocks('all',algo)
	manager.add(algo,allocation=1)
	manager.rebalance()
	manager.start()
	manager.interactive(vars=locals())
