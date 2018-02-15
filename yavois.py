from AlgoManager import *
import code
import datetime


class Yavois(Algorithm):

    def initialize(self):
        self.times = [(9,30),(15,59)]
        self.nextdaybuy = False
        self.nextdaysell = False
        self.rsi2thres = 75
        self.rsi7thres = 25
        self.long = "SPXY"
        self.hideout = "ARKK"
        self.takegain = 0.05
        self.takeloss = -0.02
        self.rsi2 = None
        self.rsi7 = None

    def run(self):

        if self.datetime.time() < datetime.time(12,0,0,0):

            if self.nextdaybuy:
                self.nextdaybuy = False
                if self.hideout is not None:
                    self.orderpercent(self.hideout,0)
                self.orderpercent(self.long,1,verbose=True)
                self.stopsell(self.long,self.takegain)
                self.stopsell(self.long,self.takeloss)
                print("Buying", self.quote(self.long))
                return

            if self.nextdaysell:
                self.nextdaysell = False
                self.orderpercent(self.long,0)
                if self.hideout is not None:
                    self.orderpercent(self.hideout,1,verbose=True)
                return

        else:

            self.rsi2 = self.rsi(self.long,mawindow=2,length=2)
            self.rsi7 = self.rsi(self.long,mawindow=7,length=2)

            # If RSI7 crosses its threshold and no current position/order, buy now
            if self.rsi7[-1] > self.rsi7thres and self.rsi7[-2] < self.rsi7thres and \
               (self.long not in self.stocks or self.stocks[self.long]==0) and \
               self.long not in self.openorders:
                if self.hideout is not None:
                    self.orderpercent(self.hideout,0)
                self.orderpercent(self.long,1,verbose=True)
                self.stopsell(self.long,self.takegain)
                self.stopsell(self.long,self.takeloss)
                return

            # If RSI2 crosses its threshold and no current position/order, buy tomorrow
            if self.rsi2[-1] > self.rsi2thres and self.rsi2[-2] < self.rsi2thres and \
               (self.long not in self.stocks or self.stocks[self.long]==0) and \
                self.long not in self.openorders:
                self.nextdaybuy = True
                return

            # If there are currently positions, sell tomorrow
            if (self.long in self.stocks and self.stocks[self.long]>0) and \
                self.long not in self.openorders:
                self.nextdaysell = True
                return

        


if __name__ == '__main__':
    algo = Yavois(times=[(9,30),(15,59)])
    algoback = backtester(algo,benchmark="SPY",capital=1000)
    algoback.start(startdate=(5, 2, 2018))
    algoback.gui()

