from trader.AlgoManager import *
from yavois import *

if __name__ == '__main__':
	algo = Yavois()
	algo.papertrade(cash=500)
	manager = Manager()
	manager.add(algo,allocation=1)
	manager.start()
	#manager.gui()
	manager.interactive(vars=locals())
