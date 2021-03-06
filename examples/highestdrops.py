from trader.AlgoManager import *
from trader.Algorithm import *
from queue import PriorityQueue


class Drops(Algorithm):

    def initialize(self):
        # Constants and Class Variables
        self.queue = PriorityQueue()
        self.watchlist = {0: [], 1: [], 2: []}
        self.percdiff = {}
        # Variables that the user can tune
        self.stocksymbols = ["FB","SPY","AAPL","MSFT","WMT","AMZN"] # The stocks that this algorithm will trade
        self.benchmark = self.stocksymbols
        self.swaps = {} # If you want to monitor a stock but buy the leveraged version, add swaps["normal"] = "leveraged"
        self.stockstohold = 1 # Number of stocks to hold at a time
        self.sellifbetterdeal = True # If you are holding a stock but another one drops even further, setting this to true will sell your current stock and buy the new one

    def run(self):
        for i in range(len(self.watchlist)-2,-1,-1):
            self.watchlist[i+1] = self.watchlist[i]
        self.watchlist[0] = []
        for stock in self.stocks:
            if self.macd(stock=stock, interval='day')[0] < 0:
                self.orderpercent(stock,0,verbose=True)
        for stock in self.stocksymbols:
            change = self.percentchange(stock=stock, interval='day')[0]
            self.queue.put((change, stock))
            if self.sellifbetterdeal and stock in self.stocks:
                self.percdiff[stock] = (1.0+self.percdiff[stock])*(1.0+change)-1.0
        lowest,sym = self.queue.get()
        while lowest < 0 and not self.queue.empty():
            self.watchlist[0].append(sym)
            lowest,sym = self.queue.get()
        counter = 0
        for stock in self.watchlist[0]+self.watchlist[1]+self.watchlist[2]:
            if self.macd(stock=stock, interval='day')[0] > 0.3:
                if self.sellifbetterdeal:
                    for heldstock in self.stocks:
                        if self.percentchange(stock=stock, interval='day')[0] < self.percdiff[heldstock]:
                            self.orderpercent(heldstock,0,verbose=True)
                            break
                    self.percdiff[stock] = self.percentchange(stock=stock, interval='day')[0]
                if stock in self.swaps:
                    stock = self.swaps[stock]
                counter += 1
                self.orderpercent(stock,1.0/self.stockstohold,verbose=True)
                self.stopsell(stock,-0.01)
                if counter >= self.stockstohold:
                    break


if __name__ == '__main__':
    algo = Drops(schedule='0 9 * * *')
    algoback = backtester(algo)
    algoback.start(start=(2017,1,1),end=(2019,1,1))
    Manager.algogui(algoback,thread=False)
