from trader.AlgoManager import *
from rnnalgo import *

if __name__ == '__main__':
	rnnalgo = RNN(times=['every day'])
	rnnalgo.papertrade(cash=500)
	manager = Manager()
	manager.add(rnnalgo,allocation=1)
	manager.start()
	#manager.gui()
	manager.interactive(vars=locals())
