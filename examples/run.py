from trader.AlgoManager import *
from trader.Util import *
from yavois import *
import atexit

if __name__ == '__main__':
	# Load
	loaded = loadstate()
	locals().update(loaded)
	if len(loaded)==0:
		algo = Yavois(schedule = ["0 9 * * MON-FRI", "59 15 * * MON-FRI"])
		manager = Manager()
		manager.assignstocks('all',algo)
		manager.add(algo,allocation=1)
		manager.rebalance()
	# Save at Exit
	atexit.register(savestate, locals())
	# Setup
	manager.start()
	manager.interactive(vars=locals())

# To exit:
# • manager.stop()
# • ctrl-d