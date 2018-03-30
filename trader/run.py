from AlgoManager import *
from yavois import *

if __name__ == '__main__':
	volalgo = Yavois()
	manager = Manager()
	manager.add(volalgo,allocation=1)
	manager.assignstocks('all',volalgo)
	manager.rebalance()
	manager.start()
	manager.interactive(vars=locals())
