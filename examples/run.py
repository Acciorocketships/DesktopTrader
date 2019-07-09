from trader.AlgoManager import *
from yavois import *
import atexit

if __name__ == '__main__':
	# Load
	manager = load_manager()
	if manager is None:
		algo = Yavois()
		manager = Manager()
		manager.assignstocks('all',algo)
		manager.add(algo,allocation=1)
		manager.rebalance()
	else:
		algo = list(manager.algo_alloc.keys())[0]
	# Save at Exit
	atexit.register(exit, manager)
	# Setup
	manager.start()
	manager.interactive(vars=locals())

def exit(manager):
	manager.stop()
	save_manager(manager)