from AlgoManager import *
import code
import datetime


class Test(Algorithm):
    def initialize(self):
        pass

    def run(self):
        val = self.percentchange("ARKK",interval='daily',length=10,datatype='close')
        print(val)


if __name__ == '__main__':
    algo = backtester(Test(times=['every day']))
    algo.startbacktest((1,1,2018),(1,2,2018))
    code.interact(local=locals())