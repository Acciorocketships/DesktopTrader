from AlgoManager import *
import code
import datetime


class Test(Algorithm):
    def initialize(self):
    	self.x = 0

    def run(self):
        self.x += 1


if __name__ == '__main__':
	algo = Test(times=['every minute'])
	manager = Manager()
	manager.add(algo)
	manager.assignstocks("all",algo)
	manager.rebalance()
	manager.start()
	manager.interactive(locals())