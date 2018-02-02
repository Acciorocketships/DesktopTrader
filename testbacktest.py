from AlgoManager import *
import code
import datetime


class Test(Algorithm):
    def initialize(self):
        pass

    def run(self):
        print("buying ARKK")
        self.orderpercent("ARKK",0.1)
        self.history("ARKK",'daily')


if __name__ == '__main__':
    algo = backtester(Test(times=['every day']))
    algo.startbacktest((1,1,2017),(1,2,2018))
    code.interact(local=locals())