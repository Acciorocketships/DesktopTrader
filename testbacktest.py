from AlgoManager import *
import code
import datetime


class Test(Algorithm):
    def initialize(self):
        pass

    def run(self):
        print("buying ARKK")
        self.orderpercent("ARKK",0.1)
        self.history("ARKK")


if __name__ == '__main__':
    algo = backtester(Test(times=['every minute']))
    code.interact(local=locals())