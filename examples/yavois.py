from trader.AlgoManager import *
from trader.Algorithm import *
import code
import datetime

class Yavois(Algorithm):

    def initialize(self):
        self.times = [(9,30),(15,59)]
        self.nextdaybuy = False
        self.nextdaysell = False
        self.rsi2thres = 0.5
        self.rsi7thres = -0.5
        self.long = "SVXY"
        self.hideout = None
        self.takegain = 0.05
        self.takeloss = -0.02
        self.rsi2 = None
        self.rsi7 = None

    def run(self):

        if self.datetime.time() < datetime.time(12,0,0,0):

            print("\nRunning " + str(self.datetime))

            if self.nextdaybuy:
                self.nextdaybuy = False
                if self.hideout is not None:
                    self.orderpercent(self.hideout,0,notify_address='acciorocketships@gmail.com')
                self.orderpercent(self.long,1,verbose=True,notify_address='acciorocketships@gmail.com')
                self.stopsell(self.long,self.takegain)
                self.stopsell(self.long,self.takeloss)
                return

            if self.nextdaysell:
                self.nextdaysell = False
                self.orderpercent(self.long,0,verbose=True,notify_address='acciorocketships@gmail.com')
                if self.hideout is not None:
                    self.orderpercent(self.hideout,1,verbose=True,notify_address='acciorocketships@gmail.com')
                return

        else:

            print("\nRunning " + str(self.datetime))

            self.rsi2 = self.rsi(self.long,window=2,length=2)
            self.rsi7 = self.rsi(self.long,window=7,length=2)

            print("RSI2: " + str(self.rsi2))
            print("RSI7: " + str(self.rsi7))

            # If RSI7 crosses its threshold and no current position/order, buy now
            if self.rsi7[-1] > self.rsi7thres and self.rsi7[-2] < self.rsi7thres and \
               (self.long not in self.stocks or self.stocks[self.long]==0):
                print("RSI7 Threshold, Buy Now")
                if self.hideout is not None:
                    self.orderpercent(self.hideout,0,notify_address='acciorocketships@gmail.com')
                self.orderpercent(self.long,1,verbose=True,notify_address='acciorocketships@gmail.com')
                self.stopsell(self.long,self.takegain)
                self.stopsell(self.long,self.takeloss)
                return

            # If RSI2 crosses its threshold and no current position/order, buy tomorrow
            if self.rsi2[-1] > self.rsi2thres and self.rsi2[-2] < self.rsi2thres and \
               (self.long not in self.stocks or self.stocks[self.long]==0):
                print("RSI2 Threshold, Buy Tomorrow")
                self.nextdaybuy = True
                return

            # If there are currently positions, sell tomorrow
            if (self.long in self.stocks and self.stocks[self.long]>0):
                print("Currently Holding Stocks, Sell Tomorrow")
                self.nextdaysell = True
                return

        

def backtest():
    algo = Yavois()
    algoback = backtester(algo,benchmark="SVXY",capital=1000)
    algoback.start(start=(2016,1,1))
    Manager.algogui(algoback)


def run():
    manager = Manager()
    algo = Yavois(times=[(9,30),(15,59)])
    manager.add(algo,allocation=1)
    manager.start()
    manager.interactive(vars=locals())


if __name__ == '__main__':
    backtest()

