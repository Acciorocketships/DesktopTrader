from trader.AlgoManager import *
from yavois import *
import atexit

if __name__ == '__main__':
	# Load
	loaded = load_state()
	locals().update(loaded)
	if len(loaded)==0:
		algo = Yavois(schedule = ["0 9 * * MON-FRI", "59 15 * * MON-FRI"])
		manager = Manager()
		manager.assignstocks('all',algo)
		manager.add(algo,allocation=1)
		manager.rebalance()
	# Save at Exit
	atexit.register(save_state, locals())
	# Setup
	manager.start()
	manager.interactive(vars=locals())

# To exit:
# • manager.stop()
# • ctrl-d