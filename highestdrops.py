import AlgoManager as AM
import code
import datetime
from Queue import PriorityQueue


class Drops(AM.Algorithm):

    def initialize(self):
        self.benchmark = "SPY"
        self.queue = PriorityQueue()
        self.stocksymbols = ["QQQ","FB","XIV","MSFT","ARKK"]
        self.watchlist = {0: [], 1: [], 2: []}

    def run(self):
        for i in range(len(self.watchlist)-2,-1,-1):
            self.watchlist[i+1] = self.watchlist[i]
        self.watchlist[0] = []
        for stock in self.stocks:
            if self.macd(stock=stock, interval='daily')['macd hist'][0] < 0:
                print "selling " + stock
                self.orderpercent(stock,0)
        for stock in self.stocksymbols:
            self.queue.put((self.percentchange(stock=stock, interval='daily')[0], stock))
        lowest,sym = self.queue.get()
        while lowest < 0:
            self.watchlist[0].append(sym)
            lowest,sym = self.queue.get()
        for stock in self.watchlist[0]+self.watchlist[1]+self.watchlist[2]:
            if self.macd(stock=stock, interval='daily')['macd hist'][0] > 0:
                print "buying " + stock
                self.orderpercent(stock,1)
                break


if __name__ == '__main__':
    algo = Drops(times=['every day'])
    algoback = AM.backtester(algo)
    algoback.start(startdate=(1, 8, 2017))
    algoback.gui()
