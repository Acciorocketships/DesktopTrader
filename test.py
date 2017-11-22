import AlgoManager as AM
import code
import datetime


class Test(AM.Algorithm):
    def initialize(self):
        self.techind = None
        self.benchmark = "QQQ"

    def run(self):
        import pdb; pdb.set_trace()
        self.techind = \
        self.percentchange(stock='QQQ', interval='daily', length=10)
        if self.techind > 0:
            self.orderpercent('QQQ', 1)
        elif self.techind < 0:
            self.orderpercent('QQQ', 0)


if __name__ == '__main__':
    algo = Test(times=['every day'])
    algoback = AM.backtester(algo)
    #algoback.start(startdate=(1, 1, 2006))
    code.interact(local=locals())