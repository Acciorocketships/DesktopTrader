import os, sys
sys.path.append(os.path.dirname(os.path.realpath("")))
from trader.AlgoManager import *
from rnnalgo import *
#from yavois import *

if __name__ == '__main__':
	#volalgo = Yavois()
	rnnalgo = RNN()
	manager = Manager()
	#manager.add(volalgo,allocation=0.5)
	manager.assignstocks('all',rnnalgo)
	manager.add(rnnalgo,allocation=1)
	manager.rebalance()
	manager.start()
	manager.gui()
	manager.interactive(vars=locals())
