import AlgoManager as AM
import code
import datetime


class Test(AM.Algorithm):
    def initialize(self):
        pass

    def run(self):
        print "buying ARKK"
        self.orderpercent("ARKK",0.1)


if __name__ == '__main__':
    algo = Test(times=['every minute'])
    manager = AM.Manager()
    manager.add(algo,0.5)
    code.interact(local=locals())